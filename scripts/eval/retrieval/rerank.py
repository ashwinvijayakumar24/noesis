"""Cross-encoder reranking arm for the retrieval eval.

WHAT THIS IS
    A second stage placed after the dense first stage: retrieve ``k * oversample``
    chunks with pgvector, then re-score every (query, chunk) pair with a local
    cross-encoder (``BAAI/bge-reranker-v2-m3``) and re-order by that score.

    A bi-encoder embeds the query and the chunk independently, so the only thing
    it can compare is two points in a space that never saw them together. A
    cross-encoder concatenates them into one sequence and runs full attention
    across the pair, which is strictly more expressive -- and strictly more
    expensive, by roughly the number of candidates. That trade is the entire
    subject of this module, which is why **latency is measured here as a
    first-class result, not as a footnote**. A reranker without its latency cost
    is half a result.

WHY LOCAL
    ``BAAI/bge-reranker-v2-m3`` runs on this laptop from local weights. Spend is
    $0.00 and is *asserted* against ``app.core.llm_budget``'s counters rather than
    assumed (see ``BudgetGuard``). The query embeddings the first stage needs are
    already in ``scripts/eval/cache/retrieval_query_embeddings``, so even the
    dense leg makes no API call.

WHAT IT DOES NOT DO
    It does not truncate the candidate list to k. ``RerankingRetriever.retrieve``
    returns the WHOLE re-ordered pool. Two reasons:

    1. ``metrics.evaluate_run`` truncates at k itself, after pooling chunks up to
       the document unit, so returning the tail costs nothing and changes no
       metric at k.
    2. ``metrics.attribute_failures`` needs the untruncated run to tell a
       *ranking* failure (retrieved, ranked below k) from a *retrieval* failure
       (never in the candidate pool at all). Truncating here would relabel every
       ranking failure as a retrieval failure and destroy the one number that
       says whether a better reranker could ever help.

    "Take 10" therefore happens downstream, exactly where it happens for the
    dense control, so the two arms are scored by identical code.

THE CONFOUND THIS SEPARATES
    The existing record contains ``dense x5 (plan: index)`` at recall@10 0.2195
    and ``dense x12 (plan: seqscan)`` at 0.2227. Depth and reranking are tangled
    there: a reranker fed a deeper pool has more to work with, and a deeper pool
    also flips the Postgres plan. The sweep in ``--mode sweep`` varies ONLY the
    oversample depth with the reranker held fixed, and stamps the plan into every
    record, so a plan flip can never be read as a rerank effect.

SNAPSHOT DISCIPLINE
    Every number here is on label snapshot ``230c6ea9d9b7e8fd``. Numbers from a
    different snapshot are not comparable to these at all -- not "roughly", not
    "directionally": the ceiling itself moves. Runs assert the snapshot id and
    refuse to append a record built on a different one.

USAGE
    python3 -m scripts.eval.retrieval.rerank --mode control     # dense x5, n=338
    python3 -m scripts.eval.retrieval.rerank --mode rerank      # + rerank, n=338
    python3 -m scripts.eval.retrieval.rerank --mode sweep       # depth sweep
    python3 -m scripts.eval.retrieval.rerank --mode latency     # latency probe
    python3 -m scripts.eval.retrieval.rerank --mode cpu-probe   # CPU-only timing
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[3])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from scripts.eval.retrieval import labels as labels_mod  # noqa: E402
from scripts.eval.retrieval import queries as queries_mod  # noqa: E402
from scripts.eval.retrieval.adapters import (  # noqa: E402
    EVAL_PROJECT_ID,
    DenseRetriever,
    RetrievedDoc,
    Retriever,
    production_embed_fn,
)
from scripts.eval.retrieval.metrics import (  # noqa: E402
    UNIT_DOCUMENT,
    compute_metrics,
    percent_of_attainable,
    pool_to_unit,
    recall_ceilings,
)
from scripts.eval.retrieval.plan_probe import PLAN_UNKNOWN  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent.parent

#: The one label snapshot these arms are measured on. Asserted, never assumed.
#: A rerank delta differenced across snapshots is meaningless -- the ceiling moves
#: with the labels, so both the numerator and the yardstick change at once.
EXPECTED_LABELS_FINGERPRINT = "230c6ea9d9b7e8fd"

#: Published control on that snapshot, from docs/history/WAVE_LOG.md.
CONTROL_RECALL_AT_10 = 0.2195
CONTROL_CEILING_AT_10 = 0.5199

#: The control is deterministic, so the reproduction tolerance is tight on
#: purpose. Query embeddings are read from an on-disk cache (identical vectors
#: every run), pgvector's HNSW search is deterministic for a fixed index and a
#: fixed ef_search, and ranx's arithmetic is exact. The only slack is the 4th
#: decimal place the published figure was rounded to. Nothing here is sampled, so
#: a "run-to-run variance" band would be inventing noise that does not exist; if
#: this tolerance is ever exceeded, something changed, and that is the finding.
CONTROL_TOLERANCE = 0.0001

#: What the control actually did on 2026-07-31, with no code change between the
#: readings: 0.2195 (published) -> 0.2195 (reproduced 23:34 UTC) -> 0.2186
#: (23:47) -> 0.2200 (00:05, twice). Span 0.0014, 0.6% of the value. Cause: a
#: concurrent lane re-ingesting into the shared local pgvector database, which
#: re-created 324 of 5,948 chunks. This is NOT run-to-run noise -- the pipeline
#: is deterministic given a fixed index -- and it must never be quoted as one.
INDEX_DRIFT_OBSERVED = "0.2186-0.2200 across 40 minutes, shared-index mutation"

RERANK_MODEL = "BAAI/bge-reranker-v2-m3"

#: Cross-encoder input budget in tokens. The corpus's chunks have a median length
#: of ~6,000 characters (see RERANK.md), so 512 tokens sees roughly the first
#: third of a median chunk. That is a real limitation of this arm and it is
#: reported, not hidden: a chunk whose relevant sentence sits at character 4,000
#: is invisible to the reranker even though the bi-encoder embedded all of it.
RERANK_MAX_LENGTH = 512
RERANK_BATCH_SIZE = 32

#: Characters of chunk text handed to the tokenizer. Lossless at
#: ``max_length=512``: the shortest plausible tokenisation of English scientific
#: prose is ~3.5 characters per token, so 512 tokens can never reach past ~1,800
#: characters and 3,000 is a wide margin. Verified empirically -- the top score
#: on a 50-candidate pool is identical to six decimal places with and without
#: it. It exists only to stop the tokenizer walking 17,000-character chunks it
#: will throw away.
RERANK_TEXT_CHAR_BUDGET = 3000

#: Cross-encoder scores persist here between arms. The candidate pools nest --
#: the top-50 pool is (almost always) a subset of the top-500 pool -- so a depth
#: sweep would otherwise re-score the same pairs four times at ~4 pairs/second.
#: The cache makes the sweep affordable; it does NOT feed the latency numbers,
#: which are taken only from queries that were scored entirely from scratch.
SCORE_CACHE_DIR = EVAL_DIR / "cache" / "retrieval_rerank_scores"

DEFAULT_RESULTS_PATH = EVAL_DIR / "results" / "retrieval_eval.jsonl"


# ---------------------------------------------------------------------------
# Spend assertion
# ---------------------------------------------------------------------------


class BudgetGuard:
    """Assert that an arm spent exactly $0.00.

    "It's a local model, so it's free" is a claim about intent. This reads the
    same counter the rest of the harness bills against (``app.core.llm_budget``)
    before and after the arm and fails if a single cent, or a single unpriced
    call, appeared. The dense leg can still reach OpenAI if a query embedding is
    missing from cache, and that is exactly the leak this catches.

    If the backend module is not importable the guard reports ``checked: False``
    rather than a comfortable zero -- "we could not check" and "we checked and it
    was zero" are different claims.
    """

    def __init__(self) -> None:
        self.module = self._load()
        self.before_usd = self.module.total_spend_usd() if self.module else None
        self.before_events = len(self.module.events()) if self.module else None

    @staticmethod
    def _load():
        backend = EVAL_DIR.parent.parent / "services" / "backend"
        if str(backend) not in sys.path:
            sys.path.insert(0, str(backend))
        try:
            from app.core import llm_budget  # type: ignore
            return llm_budget
        except Exception:
            return None

    def snapshot(self) -> dict:
        if self.module is None:
            return {
                "checked": False,
                "spend_usd": None,
                "note": "app.core.llm_budget not importable; spend UNKNOWN, not zero",
            }
        after_usd = self.module.total_spend_usd()
        after_events = len(self.module.events())
        return {
            "checked": True,
            "spend_usd": round(after_usd - (self.before_usd or 0.0), 8),
            "llm_calls": after_events - (self.before_events or 0),
            "unpriced_calls": self.module.unpriced_calls(),
        }

    def assert_zero(self) -> dict:
        snap = self.snapshot()
        if snap["checked"] and (snap["spend_usd"] or snap["llm_calls"]):
            raise AssertionError(
                f"this arm was supposed to cost $0.00 and cost ${snap['spend_usd']} "
                f"across {snap['llm_calls']} LLM call(s). The cross-encoder is local; "
                "the leak is the dense leg embedding a query that was missing from "
                f"{EVAL_DIR / 'cache' / 'retrieval_query_embeddings'}."
            )
        return snap


# ---------------------------------------------------------------------------
# The cross-encoder
# ---------------------------------------------------------------------------


def resolve_device(requested: str) -> str:
    """``"auto"`` -> the fastest local device present, otherwise what was asked.

    Reported in every record. A p50 measured on the M4's GPU is not a p50 on a
    CPU-only server and the two must never be pooled.
    """
    if requested != "auto":
        return requested
    try:
        import torch  # type: ignore
        if torch.backends.mps.is_available():
            return "mps"
        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return "cpu"


def model_revision(model_name: str = RERANK_MODEL) -> str:
    """The exact weights commit this machine is running, from the HF cache.

    A model name is not a version. ``BAAI/bge-reranker-v2-m3`` has been re-pushed;
    a number produced against one revision is not reproducible against another,
    so the resolved commit sha goes into the config hash and the writeup.
    """
    try:
        from huggingface_hub import constants  # type: ignore
        cache = Path(os.environ.get("HF_HOME", constants.HF_HOME)) / "hub"
        repo = cache / ("models--" + model_name.replace("/", "--")) / "snapshots"
        revs = sorted(p.name for p in repo.iterdir()) if repo.exists() else []
        if len(revs) == 1:
            return revs[0]
        if revs:
            return "ambiguous:" + ",".join(revs)
    except Exception:
        pass
    return "unknown"


class CrossEncoderReranker:
    """``BAAI/bge-reranker-v2-m3`` behind a two-method interface.

    Loading is lazy so the module imports (and its tests collect) on a machine
    with no ``sentence-transformers`` and no 2.2 GB of weights.
    """

    def __init__(
        self,
        model_name: str = RERANK_MODEL,
        device: str = "auto",
        max_length: int = RERANK_MAX_LENGTH,
        batch_size: int = RERANK_BATCH_SIZE,
        fp16: bool = True,
    ) -> None:
        self.model_name = model_name
        self.device = resolve_device(device)
        self.max_length = max_length
        self.batch_size = batch_size
        # fp16 is a ~1.7x throughput win on MPS and changes the 4th decimal of a
        # score at most; it never changes an ordering in a way this eval can
        # resolve. Disabled on CPU, where fp16 is emulated and slower.
        self.fp16 = fp16 and self.device != "cpu"
        self._model = None
        self.pairs_scored = 0

    @property
    def revision(self) -> str:
        return model_revision(self.model_name)

    def key(self) -> str:
        """Identity of the scorer for cache keying. Changes invalidate scores."""
        return f"{self.model_name}|{self.revision}|ml{self.max_length}|fp16={self.fp16}"

    def load(self):
        if self._model is None:
            try:
                import torch  # type: ignore
                from sentence_transformers import CrossEncoder  # type: ignore
            except ImportError as exc:  # pragma: no cover - environment-dependent
                raise RuntimeError(
                    "sentence-transformers is required for the rerank arm. "
                    "Install it: python3 -m pip install -r scripts/eval/requirements.txt"
                ) from exc
            kwargs = {"torch_dtype": torch.float16} if self.fp16 else {}
            self._model = CrossEncoder(
                self.model_name,
                device=self.device,
                max_length=self.max_length,
                model_kwargs=kwargs,
            )
        return self._model

    def score(self, query: str, texts: list[str]) -> list[float]:
        """Relevance of each text to the query. Higher is better.

        Scores are sigmoid-squashed into (0, 1) by sentence-transformers for this
        single-logit model, so they are positive and safe to use directly as the
        run's scores -- ranx ranks by score and never sees the raw logits.
        """
        if not texts:
            return []
        model = self.load()
        self.pairs_scored += len(texts)
        raw = model.predict(
            [(query, t[:RERANK_TEXT_CHAR_BUDGET]) for t in texts],
            batch_size=self.batch_size,
            show_progress_bar=False,
        )
        return [float(x) for x in raw]


# ---------------------------------------------------------------------------
# The production LLM reranker, as a measurable arm
# ---------------------------------------------------------------------------


#: Mirrors ``app.services.rag_retrieval.rerank_results`` exactly: same model, same
#: prompt text, same 20-candidate window, same 500-character truncation, same
#: ``max_completion_tokens``. Kept in sync by ``test_rerank.py``, which reads that
#: file and fails if the constants drift.
LLM_RERANK_MODEL = "gpt-5-mini"
LLM_RERANK_WINDOW = 20
LLM_RERANK_CHUNK_CHARS = 500
LLM_RERANK_MAX_COMPLETION_TOKENS = 100


class LLMReranker:
    """The shipped ``gpt-5-mini`` reranker, instrumented.

    WHY THIS IS A COPY AND NOT A CALL
        ``rag_retrieval.rerank_results`` cannot be measured as written. Its
        ``except Exception`` at the bottom returns ``chunks[:top_k]`` -- the
        first stage's order, unchanged -- and records nothing anywhere. A run
        where every single call failed is indistinguishable from a run where the
        reranker had no opinion, and neither is distinguishable from success.
        It also records no usage, so its spend is invisible to
        ``app.core.llm_budget``.

        This reproduces the prompt and the parameters byte for byte and adds the
        two things that make it measurable: a **counted** fallback, so the silent
        no-op rate becomes a number, and ``record_response_usage``, so the arm
        has a dollar figure. Behaviour is otherwise identical, including the
        absence of ``response_format``, which is exactly why the JSON parse can
        fail in the first place.

    NOTE ON THE WINDOW
        Production reranks only the first 20 candidates and returns only 10.
        A 50-candidate pool therefore reaches this arm as 20 candidates; the
        other 30 are never seen. That is the shipped behaviour and it is measured
        as shipped, not as it could be.
    """

    max_length = LLM_RERANK_CHUNK_CHARS
    fp16 = False
    device = "openai-api"

    def __init__(self, model: str = LLM_RERANK_MODEL, top_k: int = 10) -> None:
        self.model_name = model
        self.top_k = top_k
        self.calls = 0
        self.parse_failures = 0
        self.noop_fallbacks = 0
        self.pairs_scored = 0
        self._client = None
        self._budget = BudgetGuard._load()
        #: Evidence for WHY a call produced no ranking. Without this the failure
        #: is indistinguishable from a model that ranked and happened to agree
        #: with the first stage, which is the exact ambiguity the shipped
        #: implementation leaves behind.
        self.last_error: str | None = None
        self.last_finish_reason: str | None = None
        self.last_completion_tokens: int | None = None
        self.last_reasoning_tokens: int | None = None
        self.empty_content_responses = 0

    @property
    def revision(self) -> str:
        return "n/a (hosted API; no pinned revision exists)"

    def key(self) -> str:
        # Deliberately unique per process: an LLM ranking is a property of the
        # whole candidate set, not of one (query, chunk) pair, so caching it
        # per pair -- as the cross-encoder cache does -- would be wrong. Arms
        # using this reranker run with cache=None.
        return f"{self.model_name}|no-cache|{id(self)}"

    def client(self):
        if self._client is None:
            from app.core.openai_client import get_openai_client  # type: ignore
            self._client = get_openai_client()
        return self._client

    def score(self, query: str, texts: list[str]) -> list[float]:
        """Return descending synthetic scores reproducing production's ordering.

        The model returns indices, not scores. Ranked candidates get strictly
        decreasing scores from 1.0; everything the model did not name keeps its
        first-stage order beneath them. That is precisely what
        ``rerank_results`` does with its "fill remaining slots" loop, expressed
        as an ordering the harness can score.
        """
        import json as _json

        window = texts[:LLM_RERANK_WINDOW]
        self.pairs_scored += len(window)
        chunk_texts = [
            f"[{i}] {t[:LLM_RERANK_CHUNK_CHARS]}" for i, t in enumerate(window)
        ]
        prompt = f"""Given this research query: "{query}"

Rank these text passages by relevance (most relevant first).

Passages:
{chr(10).join(chunk_texts)}

Return the indices of the top {self.top_k} most relevant passages as a JSON array.
Example: {{"indices": [3, 7, 1, 15, 9]}}
"""
        indices: list[int] = []
        if self._budget is not None:
            self._budget.check_llm_allowed("retrieval_eval_llm_rerank")
        self.calls += 1
        try:
            from app.core.openai_client import get_completion_params  # type: ignore

            response = self.client().chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                max_completion_tokens=LLM_RERANK_MAX_COMPLETION_TOKENS,
                **get_completion_params(),
            )
            if self._budget is not None:
                self._budget.record_response_usage(
                    response, model=self.model_name, label="retrieval_eval_llm_rerank"
                )
            choice = response.choices[0]
            self.last_finish_reason = getattr(choice, "finish_reason", None)
            usage = getattr(response, "usage", None)
            if usage is not None:
                self.last_completion_tokens = getattr(usage, "completion_tokens", None)
                details = getattr(usage, "completion_tokens_details", None)
                self.last_reasoning_tokens = getattr(details, "reasoning_tokens", None)
            if not (choice.message.content or "").strip():
                self.empty_content_responses += 1
            payload = _json.loads(choice.message.content)
            indices = [int(i) for i in payload.get("indices", [])]
        except Exception as exc:
            # The production path silently returns the unranked list here. So do
            # we -- but we count it. An uncounted no-op is how a reranker that
            # never ranked anything reads as a reranker that did not help.
            self.parse_failures += 1
            self.last_error = f"{type(exc).__name__}: {exc}"

        seen: set[int] = set()
        ranked: list[int] = []
        for i in indices[: self.top_k]:
            if 0 <= i < len(window) and i not in seen:
                seen.add(i)
                ranked.append(i)
        if not ranked:
            self.noop_fallbacks += 1

        scores = [0.0] * len(texts)
        for pos, i in enumerate(ranked):
            scores[i] = 1.0 - pos / (2 * max(self.top_k, 1))
        # Unnamed candidates keep first-stage order strictly below every named one.
        floor = 0.4
        for i in range(len(window)):
            if i not in seen:
                floor -= 1e-4
                scores[i] = floor
        for i in range(len(window), len(texts)):
            floor -= 1e-4
            scores[i] = floor
        return scores

    def health(self) -> dict:
        return {
            "calls": self.calls,
            "parse_or_api_failures": self.parse_failures,
            "empty_content_responses": self.empty_content_responses,
            "noop_fallbacks": self.noop_fallbacks,
            "noop_rate": (self.noop_fallbacks / self.calls) if self.calls else None,
            "last_error": self.last_error,
            "last_finish_reason": self.last_finish_reason,
            "last_completion_tokens": self.last_completion_tokens,
            "last_reasoning_tokens": self.last_reasoning_tokens,
        }


# ---------------------------------------------------------------------------
# Score cache
# ---------------------------------------------------------------------------


class ScoreCache:
    """Persistent ``(scorer, query, chunk) -> score`` map.

    Exists for one reason: the depth sweep re-presents the same pairs. Scoring
    500 candidates for 338 queries takes hours at ~4 pairs/second, and the
    shallower depths are subsets of the deeper ones. Without this the sweep
    is unaffordable; with it, it is the deepest arm plus change.

    It is deliberately NOT used to make latency look good -- see
    ``RerankingRetriever.latency_summary``, which reports only queries that had
    zero cache hits.
    """

    def __init__(self, path: Path, enabled: bool = True) -> None:
        self.path = path
        self.enabled = enabled
        self.data: dict[str, float] = {}
        self.hits = 0
        self.misses = 0
        self._dirty = 0
        if enabled and path.exists():
            try:
                self.data = json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                self.data = {}

    @staticmethod
    def make_key(scorer_key: str, query: str, chunk_id: str) -> str:
        payload = f"{scorer_key}\0{query}\0{chunk_id}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]

    def get(self, key: str) -> float | None:
        if not self.enabled:
            return None
        value = self.data.get(key)
        if value is None:
            self.misses += 1
            return None
        self.hits += 1
        return value

    def put(self, key: str, value: float) -> None:
        if not self.enabled:
            return
        self.data[key] = value
        self._dirty += 1
        if self._dirty >= 500:  # survive an interrupted multi-hour run
            self.flush()

    def flush(self) -> None:
        if not self.enabled or not self._dirty:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data))
        tmp.replace(self.path)  # atomic: a killed run never leaves a half file
        self._dirty = 0


# ---------------------------------------------------------------------------
# The reranking retriever
# ---------------------------------------------------------------------------


@dataclass
class _QueryTiming:
    base_s: float
    rerank_s: float
    candidates: int
    scored: int
    cache_hits: int


class RerankingRetriever:
    """A first-stage retriever plus a cross-encoder second stage.

    Satisfies the same ``Retriever`` protocol as ``DenseRetriever``, so the
    harness scores it with byte-identical code and no branch anywhere says
    "if reranked". That is the point: an arm that is scored by different code
    than its control is not a comparison.

    ``top_n`` caps how many candidates reach the cross-encoder. Candidates below
    the cap keep their first-stage order and are appended beneath every reranked
    one, with synthetic scores strictly below the smallest reranked score, so the
    tail stays available for failure attribution without ever outranking a
    scored candidate.
    """

    def __init__(
        self,
        base: Retriever,
        reranker: CrossEncoderReranker,
        top_n: int | None = None,
        cache: ScoreCache | None = None,
        name: str | None = None,
        progress_every: int = 20,
    ) -> None:
        self.base = base
        self.reranker = reranker
        self.top_n = top_n
        self.cache = cache
        self.name = name or f"{getattr(base, 'name', 'base')}+rerank"
        self.timings: list[_QueryTiming] = []
        self.progress_every = progress_every

    def plan_summary(self) -> str:
        """Delegate: the plan is a property of the FIRST stage, always.

        Recorded on the reranked arm too, because a depth sweep flips the plan
        from index to seqscan somewhere around 103 candidates, and a plan flip
        must never be mistaken for a rerank effect.
        """
        probe = getattr(self.base, "plan_summary", None)
        return probe() if callable(probe) else PLAN_UNKNOWN

    def retrieve(self, query: str, k: int) -> list[RetrievedDoc]:
        t0 = time.perf_counter()
        candidates = self.base.retrieve(query, k)
        base_s = time.perf_counter() - t0

        head = candidates if self.top_n is None else candidates[: self.top_n]
        tail = [] if self.top_n is None else candidates[self.top_n :]

        t1 = time.perf_counter()
        scores, hits = self._score(query, head)
        rerank_s = time.perf_counter() - t1

        self.timings.append(_QueryTiming(
            base_s=base_s,
            rerank_s=rerank_s,
            candidates=len(candidates),
            scored=len(head) - hits,
            cache_hits=hits,
        ))
        # A multi-hour arm with no output is indistinguishable from a hung one,
        # and the difference matters when the machine is shared with three other
        # lanes. Cheap heartbeat, every 20 queries.
        if self.progress_every and len(self.timings) % self.progress_every == 0:
            done = len(self.timings)
            scored_total = sum(t.scored for t in self.timings)
            elapsed = sum(t.rerank_s for t in self.timings)
            print(f"[rerank]   {done} queries · {scored_total} pairs scored · "
                  f"{scored_total / max(elapsed, 1e-9):.2f} pairs/s", flush=True)

        ordered = sorted(zip(head, scores), key=lambda p: (-p[1], p[0].chunk_id))
        out: list[RetrievedDoc] = []
        for i, (doc, score) in enumerate(ordered, start=1):
            out.append(RetrievedDoc(
                doc_id=doc.doc_id, chunk_id=doc.chunk_id, score=score, rank=i,
                section_id=doc.section_id, text=doc.text,
            ))
        floor = min(scores) if scores else 0.0
        for j, doc in enumerate(tail, start=1):
            out.append(RetrievedDoc(
                doc_id=doc.doc_id, chunk_id=doc.chunk_id,
                score=floor - 1e-6 * j, rank=len(out) + 1,
                section_id=doc.section_id, text=doc.text,
            ))
        return out

    def _score(self, query: str, docs: list[RetrievedDoc]) -> tuple[list[float], int]:
        """Score ``docs``, serving what the cache already knows. Returns hits too."""
        scorer_key = self.reranker.key()
        scores: list[float | None] = []
        pending: list[int] = []
        hits = 0
        for i, doc in enumerate(docs):
            cached = None
            if self.cache is not None:
                cached = self.cache.get(ScoreCache.make_key(scorer_key, query, doc.chunk_id))
            if cached is None:
                pending.append(i)
                scores.append(None)
            else:
                hits += 1
                scores.append(cached)
        if pending:
            fresh = self.reranker.score(query, [docs[i].text or "" for i in pending])
            for i, value in zip(pending, fresh):
                scores[i] = value
                if self.cache is not None:
                    self.cache.put(
                        ScoreCache.make_key(scorer_key, query, docs[i].chunk_id), value
                    )
        return [float(s or 0.0) for s in scores], hits

    # -- latency -----------------------------------------------------------

    def latency_summary(self) -> dict:
        """p50/p95 of first-stage and added rerank time, in milliseconds.

        **Only queries whose candidates were ALL scored fresh count towards the
        rerank latency.** A cache hit costs a dictionary lookup, and averaging
        those in would report a reranker that is free, which is the opposite of
        the truth. ``n_fresh`` is reported alongside so the sample behind every
        percentile is visible; if it is 0 the fields are null rather than 0.0.
        """
        base = [t.base_s * 1000 for t in self.timings]
        fresh = [t.rerank_s * 1000 for t in self.timings if t.cache_hits == 0 and t.scored]
        return {
            "device": self.reranker.device,
            "hardware": hardware_string(),
            "n_queries": len(self.timings),
            "n_fresh": len(fresh),
            "candidates_p50": _pct([t.candidates for t in self.timings], 50),
            "base_retrieval_ms_p50": _pct(base, 50),
            "base_retrieval_ms_p95": _pct(base, 95),
            "rerank_added_ms_p50": _pct(fresh, 50),
            "rerank_added_ms_p95": _pct(fresh, 95),
            "pairs_per_second": (
                round(sum(t.scored for t in self.timings)
                      / max(sum(t.rerank_s for t in self.timings), 1e-9), 2)
                if any(t.scored for t in self.timings) else None
            ),
            "cache_hits": sum(t.cache_hits for t in self.timings),
            "cache_misses": sum(t.scored for t in self.timings),
        }


def _pct(values: list[float], p: int) -> float | None:
    """Nearest-rank percentile. ``None`` for an empty sample, never 0.0."""
    if not values:
        return None
    import math

    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, math.ceil(p / 100 * len(ordered)) - 1))
    return round(ordered[idx], 3)


def index_state() -> dict:
    """Fingerprint the INDEX, not the labels: row counts and the newest write.

    The label snapshot is a property of files on disk and is already asserted.
    The *index* is a property of a shared local Postgres that other lanes write
    to. On 2026-07-31 a concurrent re-ingest re-created 324 of the 5,948 chunks
    while this arm was being measured, and the dense control moved 0.2195 ->
    0.2186 -> 0.2200 inside forty minutes with no code change at all. Nothing in
    the existing record would have shown that, because a re-chunked corpus of the
    same size has the same labels fingerprint and the same document count.

    Stamped before and after every arm. If the two stamps differ, that arm
    straddled a mutation and its delta against any control is not paired.
    """
    try:
        from scripts.eval import db  # type: ignore
        with db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT count(*), count(DISTINCT document_id), max(created_at) "
                    "FROM document_chunks"
                )
                chunks, docs, newest = cur.fetchone()
                cur.execute("SHOW hnsw.ef_search")
                ef = cur.fetchone()[0]
        return {"chunks": chunks, "documents": docs,
                "newest_chunk_at": str(newest), "hnsw_ef_search": ef}
    except Exception as exc:  # pragma: no cover - environment-dependent
        return {"error": f"{type(exc).__name__}: {exc}"}


def hardware_string() -> str:
    """One line naming the machine every latency number on this run came from."""
    cpu = platform.processor() or platform.machine()
    if sys.platform == "darwin":
        try:
            import subprocess
            cpu = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True, text=True, check=True,
            ).stdout.strip() or cpu
        except Exception:
            pass
    return f"{cpu} / {os.cpu_count()} cores / {platform.system()} {platform.release()}"


# ---------------------------------------------------------------------------
# Per-claim-type breakdown
# ---------------------------------------------------------------------------


def metrics_by_claim_type(
    query_list: list[queries_mod.Query],
    qrels: dict[str, dict[str, int]],
    raw: dict[str, list[RetrievedDoc]],
    unit: str = UNIT_DOCUMENT,
    k: int = 10,
    metrics: list[str] | None = None,
) -> dict[str, dict]:
    """Break every metric down by ``Query.claim_type``.

    ``queries.Query`` carries ``claim_type`` straight from the pipeline's claim
    extractor, so this is a real field and not a category invented here. Each
    slice gets **its own ceiling**: the ceiling is a property of how many
    references the queries in that slice inherited, and slices differ, so a
    single global ceiling would misscale every row.

    Slices with fewer than ``MIN_SLICE`` scorable queries are still reported with
    their ``n``, because hiding a thin slice is how a spurious "type X improves
    40%" gets published off four queries.
    """
    metrics = metrics or ["recall@10", "ndcg@10", "mrr", "map"]
    by_type: dict[str, list[str]] = {}
    for q in query_list:
        by_type.setdefault(q.claim_type or "unlabelled", []).append(q.query_id)

    full_runs = {qid: pool_to_unit(res, unit) for qid, res in raw.items()}
    out: dict[str, dict] = {}
    for claim_type, qids in sorted(by_type.items()):
        slice_qrels = {q: qrels[q] for q in qids if qrels.get(q)}
        if not slice_qrels:
            out[claim_type] = {"n": 0, "metrics": None, "ceilings": None}
            continue
        slice_run = {q: full_runs.get(q, {}) for q in slice_qrels}
        ks = sorted({int(m.split("@")[1]) for m in metrics if m.startswith("recall@")})
        ceilings = recall_ceilings(slice_qrels, ks)
        measured = compute_metrics(slice_qrels, slice_run, metrics)
        out[claim_type] = {
            "n": len(slice_qrels),
            "metrics": measured,
            "ceilings": ceilings,
            "percent_of_attainable": percent_of_attainable(measured, ceilings),
        }
    return out


# ---------------------------------------------------------------------------
# Query subsampling
# ---------------------------------------------------------------------------


def stratified_subsample(
    query_list: list[queries_mod.Query], n: int
) -> list[queries_mod.Query]:
    """A deterministic, topic-stratified subsample of ``n`` queries.

    Deterministic (no RNG: round-robin over topics in id order) so the sweep's
    arms are all measured on the SAME queries and their deltas are paired rather
    than confounded with which queries each arm happened to draw.

    Stratified by topic because the ceiling is a per-manuscript property -- a
    subsample drawn from three reference-heavy manuscripts would have a visibly
    different ceiling from the full set, and every "% of attainable" computed on
    it would be measuring the draw, not the retriever.
    """
    if n >= len(query_list):
        return list(query_list)
    by_topic: dict[str, list[queries_mod.Query]] = {}
    for q in sorted(query_list, key=lambda q: (q.topic, q.query_id)):
        by_topic.setdefault(q.topic, []).append(q)
    picked: list[queries_mod.Query] = []
    round_ = 0
    while len(picked) < n:
        added = False
        for topic in sorted(by_topic):
            if round_ < len(by_topic[topic]):
                picked.append(by_topic[topic][round_])
                added = True
                if len(picked) == n:
                    break
        if not added:
            break
        round_ += 1
    return sorted(picked, key=lambda q: (q.topic, q.query_id))


# ---------------------------------------------------------------------------
# Arm execution
# ---------------------------------------------------------------------------


@dataclass
class ArmSpec:
    """One measurable configuration."""

    arm: str
    oversample: int
    rerank: bool
    top_n: int | None = None
    subsample: int | None = None
    k: int = 10
    notes: str = ""
    #: Local arms must cost $0.00 and the guard enforces it. The gpt-5-mini arm
    #: is the one exception, and it has to say so explicitly rather than the
    #: assertion quietly not applying.
    expect_zero_spend: bool = True
    extra: dict = field(default_factory=dict)


def build_arm_retriever(
    spec: ArmSpec,
    reranker: CrossEncoderReranker | None,
    cache: ScoreCache | None,
    project_id: str = EVAL_PROJECT_ID,
    embed_fn=None,
) -> Retriever:
    dense = DenseRetriever(project_id=project_id, embed_fn=embed_fn)
    if not spec.rerank:
        return dense
    assert reranker is not None
    return RerankingRetriever(dense, reranker, top_n=spec.top_n, cache=cache,
                              name=f"dense_x{spec.oversample}+rerank")


def run_arm(
    spec: ArmSpec,
    label_set: labels_mod.LabelSet,
    query_list: list[queries_mod.Query],
    reranker: CrossEncoderReranker | None,
    cache: ScoreCache | None,
    project_id: str = EVAL_PROJECT_ID,
    embed_fn=None,
    results_path: Path = DEFAULT_RESULTS_PATH,
    dry_run: bool = False,
) -> dict:
    """Execute one arm end to end and append its record to the append-only sink.

    Reuses ``run_retrieval_eval.run_eval`` / ``build_record`` / ``append_result``
    unchanged. That module owns the definition of a result record; duplicating it
    here would produce a second, subtly different definition of "a retrieval
    result", which is precisely how two numbers that cannot be compared end up
    looking comparable.
    """
    from scripts.eval.retrieval import run_retrieval_eval as rre

    if label_set.fingerprint() != EXPECTED_LABELS_FINGERPRINT:
        raise RuntimeError(
            f"label snapshot is {label_set.fingerprint()}, expected "
            f"{EXPECTED_LABELS_FINGERPRINT}. These arms are defined only on that "
            "snapshot; a rerank delta measured across snapshots is meaningless "
            "because the ceiling moves with the labels. Refusing to run."
        )

    queries_used = (
        stratified_subsample(query_list, spec.subsample) if spec.subsample else query_list
    )
    guard = BudgetGuard()
    retriever = build_arm_retriever(spec, reranker, cache, project_id, embed_fn)

    index_before = index_state()
    t0 = time.perf_counter()
    run_out = rre.run_eval(
        retriever=retriever,
        query_list=queries_used,
        label_set=label_set,
        unit=UNIT_DOCUMENT,
        k=spec.k,
        chunk_oversample=spec.oversample,
        metrics=rre.DEFAULT_METRICS,
        remap_db_ids=True,
    )
    wall_s = time.perf_counter() - t0
    index_after = index_state()
    if cache is not None:
        cache.flush()

    variant = {
        "arm_kind": "rerank" if spec.rerank else "dense_control",
        "subsample_n": spec.subsample,
        **spec.extra,
    }
    if spec.rerank and reranker is not None:
        variant.update({
            "reranker_model": reranker.model_name,
            "reranker_revision": reranker.revision,
            "reranker_max_length": reranker.max_length,
            "reranker_device": reranker.device,
            "reranker_fp16": reranker.fp16,
            "rerank_top_n": spec.top_n,
        })

    record = rre.build_record(
        run_out=run_out,
        label_set=label_set,
        query_list=queries_used,
        retriever_name=getattr(retriever, "name", "dense"),
        unit=UNIT_DOCUMENT,
        k=spec.k,
        chunk_oversample=spec.oversample,
        metrics=rre.DEFAULT_METRICS,
        seed=None,
        include_misses=False,
        arm=spec.arm,
        variant=variant,
    )
    record["run_id"] = hashlib.sha256(
        f"{record['config_hash']}\0{record['timestamp']}".encode("utf-8")
    ).hexdigest()[:12]

    latency = (
        retriever.latency_summary() if isinstance(retriever, RerankingRetriever)
        else {"device": "n/a", "hardware": hardware_string(),
              "n_queries": len(queries_used), "n_fresh": 0,
              "rerank_added_ms_p50": None, "rerank_added_ms_p95": None}
    )
    record["rerank"] = {
        "notes": spec.notes,
        "index_state_before": index_before,
        "index_state_after": index_after,
        "index_stable_during_arm": index_before == index_after,
        "latency": latency,
        "wall_seconds": round(wall_s, 2),
        "spend": guard.assert_zero() if spec.expect_zero_spend else guard.snapshot(),
        "by_claim_type": metrics_by_claim_type(
            queries_used, run_out["qrels"], run_out["raw"], k=spec.k
        ),
    }
    health = getattr(reranker, "health", None)
    if spec.rerank and callable(health):
        record["rerank"]["reranker_health"] = health()

    if not dry_run:
        rre.append_result(record, results_path)
    return record


# ---------------------------------------------------------------------------
# Latency probe
# ---------------------------------------------------------------------------


def latency_probe(
    depths: list[int],
    query_list: list[queries_mod.Query],
    reranker: CrossEncoderReranker,
    n_probe: int,
    project_id: str = EVAL_PROJECT_ID,
    embed_fn=None,
) -> list[dict]:
    """Measure added rerank latency at each depth with the cache BYPASSED.

    The quality arms lean on the score cache to be affordable, which makes their
    own clocks useless at every depth but the first one measured. This probe
    exists so each depth has a latency number taken from real forward passes, on
    the same queries, with ``n`` stated. It is small on purpose -- a deeper probe
    costs hours and buys a third decimal place on a number whose spread is
    dominated by candidate count, which is fixed per depth.
    """
    probe_queries = stratified_subsample(query_list, n_probe)
    out = []
    for depth in depths:
        rr = RerankingRetriever(
            DenseRetriever(project_id=project_id, embed_fn=embed_fn),
            reranker, top_n=None, cache=None,
        )
        for q in probe_queries:
            rr.retrieve(q.text, depth)
        summary = rr.latency_summary()
        summary["candidate_depth"] = depth
        summary["n_probe"] = len(probe_queries)
        out.append(summary)
        print(f"[rerank] latency depth={depth:>3}  "
              f"p50 {summary['rerank_added_ms_p50']} ms  "
              f"p95 {summary['rerank_added_ms_p95']} ms  "
              f"(n={summary['n_fresh']}, {summary['pairs_per_second']} pairs/s, "
              f"{summary['device']})", flush=True)
    return out


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def summarise(record: dict) -> str:
    """One line per arm, always carrying n and the ceiling."""
    m = record["metrics"]
    c = record.get("recall_ceilings", {}).get("recall@10")
    pct = record.get("percent_of_attainable", {}).get("recall@10")
    lat = (record.get("rerank") or {}).get("latency") or {}
    return (
        f"{record['arm']:<28} n={record['n_queries_scored']:<4} "
        f"R@10={m['recall@10']:.4f} ceil={c:.4f} ({pct:.0%}) "
        f"NDCG@10={m['ndcg@10']:.4f} MRR={m['mrr']:.4f} MAP={m['map']:.4f} "
        f"plan={record.get('plan')} "
        f"rerank_p50={lat.get('rerank_added_ms_p50')}ms "
        f"p95={lat.get('rerank_added_ms_p95')}ms (n_fresh={lat.get('n_fresh')})"
    )


def check_control(record: dict) -> tuple[bool, str]:
    """Did the control reproduce the published 0.2195?

    A rerank delta measured against an unreproduced baseline is worthless, so
    this is a gate, not a diagnostic.

    It fails, on purpose, on an index that has moved. The tolerance stays at
    rounding width; widening it to swallow ``INDEX_DRIFT_OBSERVED`` would turn a
    measured integrity problem into a comfortable noise band and would hide the
    next one. When it fails, the arms must be bracketed by controls measured in
    the same window instead (``--mode control`` before and after), and the delta
    quoted against those, never against the published figure.
    """
    got = record["metrics"]["recall@10"]
    ceil = record["recall_ceilings"]["recall@10"]
    ok = (abs(got - CONTROL_RECALL_AT_10) <= CONTROL_TOLERANCE
          and abs(ceil - CONTROL_CEILING_AT_10) <= CONTROL_TOLERANCE
          and record["n_queries_scored"] == 338)
    msg = (
        f"control recall@10 {got:.4f} vs published {CONTROL_RECALL_AT_10} "
        f"(tolerance {CONTROL_TOLERANCE}); ceiling {ceil:.4f} vs "
        f"{CONTROL_CEILING_AT_10}; n={record['n_queries_scored']} vs 338"
    )
    if not ok:
        msg += (
            f". Index state: {record.get('rerank', {}).get('index_state_before')}. "
            f"A drift of this size ({INDEX_DRIFT_OBSERVED}) was caused by another "
            "lane re-ingesting into the shared eval database, not by this code."
        )
    return ok, msg


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--mode", default="control",
                    choices=["control", "rerank", "sweep", "latency", "cpu-probe",
                             "llm-rerank"])
    ap.add_argument("--oversample", type=int, default=5)
    ap.add_argument("--top-n", type=int, default=None,
                    help="Cap on candidates reaching the cross-encoder (default: all)")
    ap.add_argument("--subsample", type=int, default=None,
                    help="Topic-stratified query subsample size (default: all 338)")
    ap.add_argument("--sweep-depths", default="5,12,25,50",
                    help="Oversample multipliers for --mode sweep")
    ap.add_argument("--n-probe", type=int, default=10,
                    help="Queries per depth for --mode latency")
    ap.add_argument("--device", default="auto")
    ap.add_argument("--no-cache", action="store_true",
                    help="Bypass the cross-encoder score cache")
    ap.add_argument("--project-id", default=EVAL_PROJECT_ID)
    ap.add_argument("--results-path", default=str(DEFAULT_RESULTS_PATH))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    label_set, _ = labels_mod.load_or_build(labels_mod.CORPORA_DIR)
    query_list = queries_mod.build_query_set(queries_mod.EXPORTS_DIR)
    print(f"[rerank] labels {label_set.fingerprint()} · {len(query_list)} queries · "
          f"{hardware_string()}", flush=True)

    embed_fn = production_embed_fn()
    reranker = CrossEncoderReranker(device=args.device)
    cache = ScoreCache(
        SCORE_CACHE_DIR / "bge-reranker-v2-m3.json", enabled=not args.no_cache
    )
    results_path = Path(args.results_path)

    def go(spec: ArmSpec) -> dict:
        rec = run_arm(spec, label_set, query_list, reranker, cache,
                      project_id=args.project_id, embed_fn=embed_fn,
                      results_path=results_path, dry_run=args.dry_run)
        print("[rerank] " + summarise(rec), flush=True)
        return rec

    if args.mode == "control":
        rec = go(ArmSpec(arm=f"dense_x{args.oversample}_control",
                         oversample=args.oversample, rerank=False,
                         subsample=args.subsample,
                         notes="control: dense first stage only"))
        if args.subsample is None:
            ok, msg = check_control(rec)
            print(f"[rerank] control reproduction: {'OK' if ok else 'FAILED'} — {msg}")
            if not ok:
                print("[rerank] refusing to treat any rerank delta as meaningful "
                      "against an unreproduced baseline.")
                return 3

    elif args.mode == "rerank":
        go(ArmSpec(arm=f"dense_x{args.oversample}_rerank_bge_m3",
                   oversample=args.oversample, rerank=True, top_n=args.top_n,
                   subsample=args.subsample,
                   notes=f"dense x{args.oversample} -> bge-reranker-v2-m3 -> take 10"))

    elif args.mode == "llm-rerank":
        # The one arm that spends money. Cache disabled on purpose: an LLM's
        # ranking is a property of the whole candidate set, so a per-pair cache
        # would serve scores that were never produced for this pool.
        llm = LLMReranker()
        rec = run_arm(
            ArmSpec(arm=f"dense_x{args.oversample}_rerank_gpt5mini",
                    oversample=args.oversample, rerank=True,
                    top_n=LLM_RERANK_WINDOW, subsample=args.subsample,
                    expect_zero_spend=False,
                    notes="production reranker as shipped: gpt-5-mini, top-20 "
                          "window, 500-char truncation, take 10"),
            label_set, query_list, llm, None,
            project_id=args.project_id, embed_fn=embed_fn,
            results_path=results_path, dry_run=args.dry_run,
        )
        print("[rerank] " + summarise(rec), flush=True)
        print(f"[rerank] llm health: {rec['rerank'].get('reranker_health')}")
        print(f"[rerank] spend: {rec['rerank']['spend']}")

    elif args.mode == "sweep":
        depths = [int(x) for x in args.sweep_depths.split(",")]
        for depth in depths:
            go(ArmSpec(arm=f"dense_x{depth}_control_sub",
                       oversample=depth, rerank=False, subsample=args.subsample,
                       notes="depth control, no rerank"))
            go(ArmSpec(arm=f"dense_x{depth}_rerank_bge_m3_sub",
                       oversample=depth, rerank=True, subsample=args.subsample,
                       notes="depth arm, reranked"))

    elif args.mode in ("latency", "cpu-probe"):
        if args.mode == "cpu-probe":
            reranker = CrossEncoderReranker(device="cpu")
        depths = [10 * int(x) for x in args.sweep_depths.split(",")]
        probes = latency_probe(depths, query_list, reranker, args.n_probe,
                               project_id=args.project_id, embed_fn=embed_fn)
        out = SCORE_CACHE_DIR / f"latency_probe_{reranker.device}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(probes, indent=2))
        print(f"[rerank] wrote {out}")

    flush = getattr(embed_fn, "flush", None)
    if callable(flush):
        flush()
    cache.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

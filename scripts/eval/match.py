"""
Match Noesis critique items against atomized OpenReview reviewer units.

Pipeline:
1. Cache embeddings for both sides.
2. Cosine prefilter candidate pairs.
3. Cache GPT confirmation per surviving pair.

SPEND GUARDRAILS
----------------
Both network paths here (embeddings and the GPT confirmation) go through
``app.core.llm_budget``: ``check_llm_allowed()`` before the call, ``record_usage``
/ ``record_response_usage`` after. Until this was wired up, matcher calls were
invisible to every cost figure the eval harness printed and ignored
NOESIS_LLM_KILL_SWITCH / EVAL_REPLAY_ONLY / NOESIS_LLM_MAX_CALLS /
NOESIS_LLM_MAX_SPEND_USD entirely, so reported spend was a lower bound by an
unknown margin.

Why the budget functions are called directly instead of routing through
``app.services.retry_utils``: that wrapper is built for *structured output* --
it calls ``client.beta.chat.completions.parse`` and sanitises kwargs for a
Pydantic ``response_format``. The matcher deliberately uses plain
``response_format={"type": "json_object"}`` plus its own bisecting retry
(``_confirm_chunk``) to isolate a single bad pair, and the embedding path is not
a chat completion at all. Reusing retry_utils would mean rewriting both. The
guardrail contract retry_utils provides -- guard before the request, record
after -- is what matters, and it is reproduced here exactly.

REPRODUCIBILITY
---------------
``temperature=0`` is **not** a determinism guarantee, and this file no longer
implies that it is. The confirmation judge was observed returning different
verdicts for the same pair under the same config hash (a head-to-head re-run
moved the DAG arm's confirmed-unit count 56 -> 57). What makes a scoring run
reproducible here is the *cache*, not the model:

* ``_confirm_cache_key`` covers everything that can change a verdict -- the
  prompt version, the judge model, and the pair itself. A prompt or model
  change therefore misses rather than silently serving a verdict produced under
  the old one.
* A cached verdict is **authoritative** for its key. It is read, never
  re-judged, never overwritten. Two runs over a fully warm cache are equal by
  construction.
* Every run reports ``confirm_live_verdicts``. ``0`` means the run was served
  entirely from cache and is exactly reproducible; anything above ``0`` means
  it is not, and ``stats["confirm_fully_cached"]`` says which it was.

Historical keys were ``sha256(PROMPT_VERSION, noesis_text, unit_text)``, written
under exactly ``prompt_version="match_v1"`` / ``model="gpt-5.2"``. Those entries
are still valid *for that configuration only*, so ``_legacy_confirm_cache_key``
returns them under that configuration and returns ``None`` under any other. The
warm 77 MB cache survives the re-key; a prompt bump still invalidates it.

AUDITABILITY
------------
``match(..., decisions=[])`` fills the list with one row per decision: the two
texts, the cosine, the threshold in force, the judge's verdict and reason, and
whether that verdict came from cache or from a live call. Items whose best
cosine never cleared the prefilter get a row too, naming the unit they came
closest to -- otherwise "why was this finding not credited?" has no answer in
the record at all.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Callable

if Path("/app/app").exists():
    REPO_ROOT = Path("/app")
    if "/app" not in sys.path:
        sys.path.insert(0, "/app")
else:
    REPO_ROOT = Path(__file__).resolve().parent.parent.parent
    _svc = str(REPO_ROOT / "services" / "backend")
    if _svc not in sys.path:
        sys.path.insert(0, _svc)

from app.core.llm_budget import (  # noqa: E402
    LLMGuardrailError,
    check_llm_allowed,
    current_label,
    record_response_usage,
    record_usage,
)

EVAL_DIR = Path(__file__).resolve().parent
DEFAULT_CACHE_DIR = EVAL_DIR / "cache" / "match"
PROMPT_VERSION = "match_v1"

EMBED_MODEL = "text-embedding-3-small"
CONFIRM_MODEL = "gpt-5.2"

#: The uncalibrated value this matcher shipped with, kept named rather than
#: deleted: every row written before 2026-08-01 -- ``ceiling.jsonl``,
#: ``headtohead*.jsonl``, every count in ``HEADTOHEAD.md`` and ``BENCHMARKS.md``
#: -- was produced under it, and a reader needs to be able to say
#: ``COS_THRESHOLD = LEGACY_COS_THRESHOLD`` and reproduce them.
LEGACY_COS_THRESHOLD = 0.55

#: Calibrated on **n = 266** hand-labelled pairs (146 from ``CEILING.md`` §3,
#: 120 dense labels across 0.42-0.48). Recall **0.842** [0.625, 0.945],
#: precision 0.213 [0.141, 0.309]; the plateau is 0.43-0.47 and every threshold
#: in it has a recall point estimate inside 0.44's interval. The deployed 0.55
#: scored recall 0.202 [0.081, 0.424] -- worse than 0.44 on recall by a factor
#: of four and worse than 0.60 on precision. Derivation, intervals, the
#: cost asymmetry that breaks the 0.44/0.45 tie, and the judge-variance term the
#: intervals do *not* cover: ``scripts/eval/ceiling/CALIBRATION.md``.
CALIBRATED_COS_THRESHOLD = 0.44

#: Override with ``NOESIS_MATCH_COS_THRESHOLD`` (e.g. ``=0.55`` to reproduce a
#: pre-calibration row). Read once at import; callers that need to vary it
#: within a process assign to ``match.COS_THRESHOLD`` directly, as the ceiling
#: and head-to-head scorers already do.
COS_THRESHOLD = float(os.environ.get("NOESIS_MATCH_COS_THRESHOLD", CALIBRATED_COS_THRESHOLD))
CONFIRM_BATCH_SIZE = 20

Embedder = Callable[[list[str]], list[list[float]]]
Confirmer = Callable[[list[dict]], list[dict]]


def _match_label(kind: str) -> str:
    """A usage label that always begins with ``match:`` so matcher spend is separable.

    ``node_eval.score_replay`` already runs the matcher inside
    ``llm_label(f"match:{node}")``. An explicit label beats the ambient one in
    ``llm_budget._resolve_label``, so composing rather than overriding is what
    keeps the per-node attribution ("match:reviewer_panel:confirm") while still
    guaranteeing the ``match:`` prefix when the matcher is run standalone from
    ``main()`` (where the ambient label is None and the fallback would otherwise
    be the bare model name, i.e. indistinguishable from node spend).
    """
    ambient = current_label()
    if not ambient:
        return f"match:{kind}"
    if ambient.startswith("match"):
        return f"{ambient}:{kind}"
    return f"match:{ambient}:{kind}"


def _count_tokens(texts: list[str]) -> int:
    """Token count for embedding usage accounting.

    The embeddings endpoint response is reduced to ``.data`` by
    ``rag_ingest.embed_chunks``, so no usage block survives to read. Counting
    with cl100k_base -- the tokenizer text-embedding-3-* actually uses -- matches
    what ``scripts/eval/ingest.py`` already does for the same reason.
    ``disallowed_special=()`` for the same reason as rag_chunking: this is
    counting, and critique text can legitimately quote "<|endoftext|>".
    """
    import tiktoken

    enc = tiktoken.get_encoding("cl100k_base")
    return sum(len(enc.encode(text, disallowed_special=())) for text in texts)


def _stable_hash(parts: list[str]) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def _item_text(item: dict) -> str:
    for key in ("text", "problem", "description", "title", "recommendation"):
        value = item.get(key)
        if value:
            return str(value)
    return json.dumps(item, sort_keys=True)


def _embedding_cache_key(text: str) -> str:
    return _stable_hash([EMBED_MODEL, "1536", text])


#: The (prompt_version, model) pair every pre-existing confirm cache entry was
#: written under. Legacy keys omitted the model, so they are only safe to read
#: back when the current configuration is byte-identical to this one.
LEGACY_CONFIRM_KEY_CONFIG = ("match_v1", "gpt-5.2")


def _confirm_cache_key(
    noesis_text: str,
    unit_text: str,
    *,
    model: str | None = None,
    prompt_version: str | None = None,
) -> str:
    """Key a confirmation verdict on everything that can change it.

    The pair alone is not enough: the same two texts judged by a different model,
    or under a different prompt, are a different question. Keying on the pair
    alone is how a verdict from the old prompt gets served under the new one.
    """
    return _stable_hash(
        [
            "confirm",
            prompt_version or PROMPT_VERSION,
            model or CONFIRM_MODEL,
            noesis_text,
            unit_text,
        ]
    )


def _legacy_confirm_cache_key(
    noesis_text: str,
    unit_text: str,
    *,
    model: str | None = None,
    prompt_version: str | None = None,
) -> str | None:
    """The pre-model-keyed cache key, or ``None`` when it would be unsound.

    Returns a key only under the exact configuration those entries were written
    for. Under any other prompt version or judge model a legacy entry is a stale
    verdict for a different question, and the correct behaviour is a cache miss.
    """
    config = (prompt_version or PROMPT_VERSION, model or CONFIRM_MODEL)
    if config != LEGACY_CONFIRM_KEY_CONFIG:
        return None
    return _stable_hash([config[0], noesis_text, unit_text])


def _decision_provenance() -> dict[str, Any]:
    """The configuration every decision row is only interpretable under.

    Carried per row rather than once in a header: the record is append-only and
    a later run under a different threshold appends to the same file, so a row
    that does not carry its own threshold cannot be read at all.
    """
    return {
        "cos_threshold": COS_THRESHOLD,
        "embed_model": EMBED_MODEL,
        "confirm_model": CONFIRM_MODEL,
        "prompt_version": PROMPT_VERSION,
    }


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "y", "1", "confirmed"}
    return False


def _real_embed(texts: list[str]) -> list[list[float]]:
    from app.services.rag_ingest import embed_chunks

    data = embed_chunks(texts, model=EMBED_MODEL)
    return [list(item.embedding) for item in data]


def _embed_texts(
    texts: list[str],
    cache_dir: Path,
    embedder: Embedder | None,
    stats: dict[str, int] | None,
) -> list[list[float]]:
    embed_dir = cache_dir / "embed"
    embed_dir.mkdir(parents=True, exist_ok=True)
    vectors: list[list[float] | None] = []
    misses: list[tuple[int, str, Path]] = []

    for idx, text in enumerate(texts):
        path = embed_dir / f"{_embedding_cache_key(text)}.json"
        if path.exists():
            if stats is not None:
                stats["embed_cache_hits"] = stats.get("embed_cache_hits", 0) + 1
            vectors.append(json.loads(path.read_text())["embedding"])
        else:
            vectors.append(None)
            misses.append((idx, text, path))

    if misses:
        if stats is not None:
            stats["embed_calls"] = stats.get("embed_calls", 0) + 1
            stats["embedded_texts"] = stats.get("embedded_texts", 0) + len(misses)
        batch_embedder = embedder or _real_embed
        miss_texts = [text for _, text, _ in misses]
        # Guard covers the injected embedder too: the ceilings bound *calls*, and
        # a test double standing in for the network still represents one.
        label = _match_label("embed")
        check_llm_allowed(label)
        embedded = batch_embedder(miss_texts)
        record_usage(
            model=EMBED_MODEL,
            prompt_tokens=_count_tokens(miss_texts),
            label=label,
        )
        if len(embedded) != len(misses):
            raise RuntimeError("Embedder returned wrong number of vectors")
        for (idx, _text, path), vector in zip(misses, embedded):
            vector = [float(v) for v in vector]
            path.write_text(json.dumps({"embedding": vector}) + "\n")
            vectors[idx] = vector

    return [vector for vector in vectors if vector is not None]


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _real_confirm(pairs: list[dict], client: Any | None = None) -> list[dict]:
    if client is None:
        from app.core.openai_client import get_openai_client

        client = get_openai_client()

    from app.core.openai_client import get_completion_params

    response = client.chat.completions.create(
        model=CONFIRM_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You confirm whether a Noesis critique item and a human reviewer unit "
                    "raise the same underlying concern. Same topic but different concern = NO. "
                    "Return only JSON."
                ),
            },
            {
                "role": "user",
                "content": (
                    "For each pair, return {index, confirmed, reason}. "
                    f"Pairs: {json.dumps(pairs, ensure_ascii=True)}"
                ),
            },
        ],
        response_format={"type": "json_object"},
        max_completion_tokens=2000,
        temperature=0,
        **get_completion_params(),
    )
    record_response_usage(response, model=CONFIRM_MODEL, label=_match_label("confirm"))
    content = response.choices[0].message.content or "{}"
    payload = json.loads(content)
    results = payload.get("pairs") or payload.get("results") or payload.get("matches")
    if results is None and {"index", "confirmed"} <= set(payload):
        results = [payload]
    if not isinstance(results, list):
        raise RuntimeError(f"Matcher response missing pairs list: {content[:500]}")
    return results


def _confirm_pairs(
    candidate_pairs: list[dict],
    cache_dir: Path,
    confirmer: Confirmer | None,
    client: Any | None,
    stats: dict[str, int] | None,
) -> list[dict]:
    confirm_dir = cache_dir / "confirm"
    confirm_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict | None] = [None] * len(candidate_pairs)
    misses: list[dict] = []

    for idx, pair in enumerate(candidate_pairs):
        key = _confirm_cache_key(pair["noesis_text"], pair["unit_text"])
        path = confirm_dir / f"{key}.json"
        legacy_key = _legacy_confirm_cache_key(pair["noesis_text"], pair["unit_text"])
        legacy_path = confirm_dir / f"{legacy_key}.json" if legacy_key else None
        if path.exists():
            if stats is not None:
                stats["confirm_cache_hits"] = stats.get("confirm_cache_hits", 0) + 1
            results[idx] = {**json.loads(path.read_text()), "source": "cache"}
        elif legacy_path is not None and legacy_path.exists():
            # Same verdict, same question: the legacy entry was written under
            # exactly this prompt and model. Adopted under the new key so the
            # cache converges and the fallback stops being load-bearing.
            if stats is not None:
                stats["confirm_cache_hits"] = stats.get("confirm_cache_hits", 0) + 1
                stats["confirm_cache_hits_legacy"] = (
                    stats.get("confirm_cache_hits_legacy", 0) + 1
                )
            payload = json.loads(legacy_path.read_text())
            path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
            results[idx] = {**payload, "source": "cache_legacy"}
        else:
            misses.append({"index": idx, **pair})

    if misses:
        confirm = confirmer or (lambda pairs: _real_confirm(pairs, client=client))
        confirmed: list[dict] = []
        for start in range(0, len(misses), CONFIRM_BATCH_SIZE):
            confirmed.extend(_confirm_chunk(misses[start : start + CONFIRM_BATCH_SIZE], confirm, stats))
        by_index = {int(item["index"]): item for item in confirmed}
        for missed in misses:
            idx = int(missed["index"])
            item = by_index.get(idx)
            if item is None:
                raise RuntimeError(f"Missing confirmation for pair index {idx}")
            normalized = {
                "confirmed": _as_bool(item.get("confirmed")),
                "reason": str(item.get("reason") or ""),
            }
            key = _confirm_cache_key(missed["noesis_text"], missed["unit_text"])
            path = confirm_dir / f"{key}.json"
            # First writer wins. A verdict, once written, is authoritative for
            # its key -- re-judging a key that already has a verdict is exactly
            # the non-determinism this cache exists to remove.
            if not path.exists():
                path.write_text(json.dumps(normalized, indent=2, sort_keys=True) + "\n")
            if stats is not None:
                stats["confirm_live_verdicts"] = stats.get("confirm_live_verdicts", 0) + 1
            results[idx] = {**normalized, "source": "live"}

    if stats is not None:
        stats["confirm_fully_cached"] = int(not stats.get("confirm_live_verdicts", 0))

    return [result for result in results if result is not None]


def _confirm_chunk(pairs: list[dict], confirm: Confirmer, stats: dict[str, int] | None) -> list[dict]:
    if not pairs:
        return []
    if stats is not None:
        stats["confirm_calls"] = stats.get("confirm_calls", 0) + 1
    # BEFORE the network call, and before the bisect below, so a tripped
    # guardrail halts matching instead of being retried into two halves. Sits
    # here rather than inside _real_confirm so an injected confirmer is bounded
    # by the same ceilings.
    check_llm_allowed(_match_label("confirm"))
    try:
        confirmed = confirm(pairs)
    except LLMGuardrailError:
        # LLMGuardrailError subclasses RuntimeError, so without this it would be
        # swallowed by the bisect below and retried -- the opposite of halting.
        raise
    except (json.JSONDecodeError, RuntimeError) as exc:
        if len(pairs) == 1:
            raise RuntimeError(f"Matcher confirmation failed for pair index {pairs[0].get('index')}") from exc
        midpoint = len(pairs) // 2
        return _confirm_chunk(pairs[:midpoint], confirm, stats) + _confirm_chunk(pairs[midpoint:], confirm, stats)
    if stats is not None:
        stats["confirmed_pairs"] = stats.get("confirmed_pairs", 0) + len(pairs)
    return confirmed


def match(
    noesis_items: list[dict],
    review_units: list[dict],
    cache_dir: Path = DEFAULT_CACHE_DIR,
    embedder: Embedder | None = None,
    confirmer: Confirmer | None = None,
    client: Any | None = None,
    stats: dict[str, int] | None = None,
    decisions: list[dict] | None = None,
) -> list[dict]:
    """Confirmed-or-not verdicts for every candidate pair.

    Pass ``decisions=[]`` to also collect the audit trail: one row per judged
    pair plus one row per item that never cleared the cosine prefilter. See the
    module docstring's AUDITABILITY section.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    if stats is not None:
        for key in (
            "embed_cache_hits",
            "embed_calls",
            "embedded_texts",
            "confirm_cache_hits",
            "confirm_cache_hits_legacy",
            "confirm_live_verdicts",
            "confirm_calls",
            "confirmed_pairs",
        ):
            stats.setdefault(key, 0)
    noesis_texts = [_item_text(item) for item in noesis_items]
    unit_texts = [str(unit.get("text") or "") for unit in review_units]
    vectors = _embed_texts(noesis_texts + unit_texts, cache_dir, embedder, stats)
    noesis_vectors = vectors[: len(noesis_texts)]
    unit_vectors = vectors[len(noesis_texts) :]

    candidate_pairs: list[dict] = []
    total_pairs = len(noesis_items) * len(review_units)
    #: noesis_idx -> (best cosine seen, unit_idx). Kept for the items that never
    #: clear the prefilter: without it the record cannot say how close they came.
    best_below: dict[int, tuple[float, int]] = {}
    cleared: set[int] = set()
    for noesis_idx, noesis_vector in enumerate(noesis_vectors):
        for unit_idx, unit_vector in enumerate(unit_vectors):
            cosine = _cosine(noesis_vector, unit_vector)
            if cosine >= best_below.get(noesis_idx, (-2.0, -1))[0]:
                best_below[noesis_idx] = (cosine, unit_idx)
            if cosine < COS_THRESHOLD:
                continue
            cleared.add(noesis_idx)
            candidate_pairs.append(
                {
                    "noesis_index": noesis_idx,
                    "unit_index": unit_idx,
                    "noesis_id": str(noesis_items[noesis_idx].get("id") or noesis_idx),
                    "unit_id": str(review_units[unit_idx].get("unit_id") or unit_idx),
                    "noesis_text": noesis_texts[noesis_idx],
                    "unit_text": unit_texts[unit_idx],
                    "cosine": round(cosine, 6),
                }
            )

    if stats is not None:
        # Accumulated, not assigned. Every caller that scores more than one
        # manuscript passes one stats dict through a call per manuscript, so
        # assignment reported the last manuscript's pair counts as the run's --
        # which lands in the decision record's header as a wrong denominator.
        stats["total_pairs"] = stats.get("total_pairs", 0) + total_pairs
        stats["candidate_pairs"] = stats.get("candidate_pairs", 0) + len(candidate_pairs)

    confirmations = _confirm_pairs(candidate_pairs, cache_dir, confirmer, client, stats)
    matches = []
    for pair, confirmation in zip(candidate_pairs, confirmations):
        matches.append(
            {
                "noesis_id": pair["noesis_id"],
                "unit_id": pair["unit_id"],
                "cosine": pair["cosine"],
                "confirmed": confirmation["confirmed"],
                "reason": confirmation["reason"],
            }
        )
        if decisions is not None:
            decisions.append(
                {
                    **_decision_provenance(),
                    "stage": "confirmed" if confirmation["confirmed"] else "rejected",
                    "noesis_id": pair["noesis_id"],
                    "noesis_text": pair["noesis_text"],
                    "unit_id": pair["unit_id"],
                    "unit_text": pair["unit_text"],
                    "cosine": pair["cosine"],
                    "confirmed": bool(confirmation["confirmed"]),
                    "reason": confirmation["reason"],
                    "verdict_source": confirmation.get("source"),
                }
            )

    if decisions is not None:
        for noesis_idx, _text in enumerate(noesis_texts):
            if noesis_idx in cleared:
                continue
            cosine, unit_idx = best_below.get(noesis_idx, (0.0, -1))
            decisions.append(
                {
                    **_decision_provenance(),
                    "stage": "below_cosine_threshold",
                    "noesis_id": str(noesis_items[noesis_idx].get("id") or noesis_idx),
                    "noesis_text": noesis_texts[noesis_idx],
                    "unit_id": (
                        str(review_units[unit_idx].get("unit_id") or unit_idx)
                        if unit_idx >= 0
                        else None
                    ),
                    "unit_text": unit_texts[unit_idx] if unit_idx >= 0 else None,
                    "cosine": round(cosine, 6),
                    "confirmed": False,
                    # Never shown to the judge, so there is no verdict and no
                    # source. Recording "" here would read as "the judge said
                    # nothing", which is a different claim.
                    "reason": "nearest unit below cos_threshold; never sent to the confirmer",
                    "verdict_source": None,
                }
            )

    return matches


def main() -> int:
    parser = argparse.ArgumentParser(description="Match Noesis items to atomized OpenReview units.")
    parser.add_argument("--noesis-items", type=Path, required=True)
    parser.add_argument("--review-units", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument(
        "--decisions-path",
        type=Path,
        default=None,
        help=(
            "JSONL audit trail: one row per judged pair plus one per item that "
            "never cleared the prefilter. CONTAINS MANUSCRIPT-DERIVED TEXT."
        ),
    )
    args = parser.parse_args()

    noesis_items = json.loads(args.noesis_items.read_text())
    review_units = json.loads(args.review_units.read_text())
    stats: dict[str, int] = {}
    decisions: list[dict] = []
    results = match(
        noesis_items,
        review_units,
        cache_dir=args.cache_dir,
        stats=stats,
        decisions=decisions,
    )
    if args.decisions_path:
        with args.decisions_path.open("a", encoding="utf-8") as handle:
            for row in decisions:
                handle.write(json.dumps(row, sort_keys=True) + "\n")
    print(json.dumps({"matches": results, "stats": stats}, indent=2, sort_keys=True))
    # Stated rather than left to be inferred from the stats blob: a run with any
    # live verdict is not reproducible, and that is the headline, not a detail.
    if stats.get("confirm_live_verdicts"):
        print(
            f"NOT REPRODUCIBLE: {stats['confirm_live_verdicts']} verdict(s) came from a "
            f"live judge, {stats.get('confirm_cache_hits', 0)} from cache. Re-running now "
            "will serve all of them from cache and is reproducible.",
            file=sys.stderr,
        )
    else:
        print(
            f"reproducible: all {stats.get('confirm_cache_hits', 0)} verdict(s) served "
            "from cache, 0 live.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

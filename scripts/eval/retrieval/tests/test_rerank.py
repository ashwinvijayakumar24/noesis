"""Tests for the cross-encoder reranking arm.

None of these load ``bge-reranker-v2-m3``. The 2.2 GB of weights are an
environment fact, not a property of the code, and a test suite that needs them
stops being runnable on CI and stops being run at all. Every test here drives
``RerankingRetriever`` with a deterministic stand-in scorer, which is enough to
pin down everything that can silently go wrong: the ordering, the tail handling,
the cache's effect on latency accounting, the ceiling-per-slice arithmetic, and
the snapshot guard.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.eval.retrieval.adapters import RetrievedDoc
from scripts.eval.retrieval.queries import Query
from scripts.eval.retrieval.rerank import (
    CONTROL_CEILING_AT_10,
    CONTROL_RECALL_AT_10,
    CONTROL_TOLERANCE,
    EXPECTED_LABELS_FINGERPRINT,
    LLM_RERANK_CHUNK_CHARS,
    LLM_RERANK_MAX_COMPLETION_TOKENS,
    LLM_RERANK_MODEL,
    LLM_RERANK_WINDOW,
    ArmSpec,
    LLMReranker,
    RerankingRetriever,
    ScoreCache,
    _pct,
    check_control,
    metrics_by_claim_type,
    stratified_subsample,
)


# ---------------------------------------------------------------------------
# Doubles
# ---------------------------------------------------------------------------


class FakeBase:
    """A first stage that returns a fixed, descending-score candidate list."""

    name = "fake_dense"

    def __init__(self, n: int = 6, plan: str = "index") -> None:
        self.n = n
        self.plan = plan
        self.calls: list[tuple[str, int]] = []

    def plan_summary(self) -> str:
        return self.plan

    def retrieve(self, query: str, k: int) -> list[RetrievedDoc]:
        self.calls.append((query, k))
        out = []
        for i in range(1, min(k, self.n) + 1):
            out.append(RetrievedDoc(
                doc_id=f"d{i}", chunk_id=f"d{i}::c0", score=1.0 - i / 100,
                rank=i, section_id=f"d{i}::s0", text=f"text for d{i}",
            ))
        return out


class FakeReranker:
    """Scores by an explicit ``{chunk_id: score}`` table. Counts forward passes."""

    model_name = "fake/reranker"
    max_length = 512
    device = "cpu"
    fp16 = False

    def __init__(self, table: dict[str, float]) -> None:
        self.table = table
        self.pairs_scored = 0
        self.batches = 0

    @property
    def revision(self) -> str:
        return "deadbeef"

    def key(self) -> str:
        return "fake|deadbeef|ml512"

    def score(self, query: str, texts: list[str]) -> list[float]:
        self.batches += 1
        self.pairs_scored += len(texts)
        return [self.table.get(t.split()[-1], 0.0) for t in texts]


def _table(**kw: float) -> dict[str, float]:
    return dict(kw)


# ---------------------------------------------------------------------------
# Ordering
# ---------------------------------------------------------------------------


def test_rerank_reorders_by_cross_encoder_score():
    """The whole point: the second stage overrides the first stage's order."""
    base = FakeBase(n=4)
    rr = RerankingRetriever(base, FakeReranker(_table(d1=0.1, d2=0.9, d3=0.5, d4=0.2)))
    got = rr.retrieve("q", 4)
    assert [r.doc_id for r in got] == ["d2", "d3", "d4", "d1"]
    assert [r.rank for r in got] == [1, 2, 3, 4]
    assert got[0].score == pytest.approx(0.9)


def test_rerank_returns_the_whole_pool_not_just_k():
    """Truncating here would relabel every ranking failure as a retrieval failure.

    ``metrics.attribute_failures`` distinguishes "returned at rank 47" from
    "never returned" using the untruncated run. If this stage cut the list to k,
    that distinction -- the one number that says whether a better reranker could
    help at all -- would be destroyed before scoring.
    """
    base = FakeBase(n=6)
    rr = RerankingRetriever(base, FakeReranker(_table()))
    assert len(rr.retrieve("q", 6)) == 6


def test_ties_break_deterministically():
    base = FakeBase(n=3)
    rr = RerankingRetriever(base, FakeReranker(_table(d1=0.5, d2=0.5, d3=0.5)))
    first = [r.doc_id for r in rr.retrieve("q", 3)]
    second = [r.doc_id for r in RerankingRetriever(
        FakeBase(n=3), FakeReranker(_table(d1=0.5, d2=0.5, d3=0.5))
    ).retrieve("q", 3)]
    assert first == second == ["d1", "d2", "d3"]


def test_top_n_leaves_the_tail_below_every_reranked_candidate():
    """A candidate the cross-encoder never saw must not outrank one it scored.

    Otherwise an unscored tail item with a high first-stage similarity would jump
    above a reranked item and the arm would silently be a partial rerank with an
    unlabelled fusion rule.
    """
    base = FakeBase(n=5)
    rr = RerankingRetriever(
        base, FakeReranker(_table(d1=0.01, d2=0.02)), top_n=2,
    )
    got = rr.retrieve("q", 5)
    assert [r.doc_id for r in got[:2]] == ["d2", "d1"]
    # tail keeps first-stage order and sits strictly below the lowest score
    assert [r.doc_id for r in got[2:]] == ["d3", "d4", "d5"]
    assert all(r.score < min(g.score for g in got[:2]) for r in got[2:])
    assert [r.score for r in got[2:]] == sorted((r.score for r in got[2:]), reverse=True)


def test_plan_is_delegated_to_the_first_stage():
    """A plan flip must never be readable as a rerank effect."""
    rr = RerankingRetriever(FakeBase(plan="seqscan"), FakeReranker(_table()))
    assert rr.plan_summary() == "seqscan"


def test_depth_is_passed_through_untouched():
    """The harness controls depth via k*oversample; the wrapper must not clamp it."""
    base = FakeBase(n=500)
    RerankingRetriever(base, FakeReranker(_table())).retrieve("q", 250)
    assert base.calls == [("q", 250)]


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


def test_cache_serves_repeats_without_a_forward_pass(tmp_path):
    cache = ScoreCache(tmp_path / "c.json")
    reranker = FakeReranker(_table(d1=0.3, d2=0.7))
    rr = RerankingRetriever(FakeBase(n=2), reranker, cache=cache)
    rr.retrieve("q", 2)
    assert reranker.pairs_scored == 2
    RerankingRetriever(FakeBase(n=2), reranker, cache=cache).retrieve("q", 2)
    assert reranker.pairs_scored == 2  # nothing re-scored
    assert cache.hits == 2


def test_cache_survives_a_flush_and_reload(tmp_path):
    path = tmp_path / "c.json"
    cache = ScoreCache(path)
    rr = RerankingRetriever(FakeBase(n=2), FakeReranker(_table(d1=0.3, d2=0.7)), cache=cache)
    rr.retrieve("q", 2)
    cache.flush()
    assert json.loads(path.read_text())
    assert ScoreCache(path).data == cache.data


def test_cache_key_changes_with_the_scorer(tmp_path):
    """A different model, revision or max_length is a different measurement."""
    a = ScoreCache.make_key("modelA|rev1|ml512", "q", "c1")
    b = ScoreCache.make_key("modelA|rev2|ml512", "q", "c1")
    c = ScoreCache.make_key("modelA|rev1|ml256", "q", "c1")
    assert len({a, b, c}) == 3


def test_no_cache_flag_disables_both_read_and_write(tmp_path):
    cache = ScoreCache(tmp_path / "c.json", enabled=False)
    reranker = FakeReranker(_table(d1=0.3, d2=0.7))
    for _ in range(2):
        RerankingRetriever(FakeBase(n=2), reranker, cache=cache).retrieve("q", 2)
    assert reranker.pairs_scored == 4
    assert not (tmp_path / "c.json").exists()


# ---------------------------------------------------------------------------
# Latency accounting
# ---------------------------------------------------------------------------


def test_latency_excludes_cache_served_queries(tmp_path):
    """A dictionary lookup is not a reranker.

    Averaging cache hits into the latency would report a free reranker, which is
    the exact opposite of what this arm costs.
    """
    cache = ScoreCache(tmp_path / "c.json")
    reranker = FakeReranker(_table(d1=0.3, d2=0.7))
    rr = RerankingRetriever(FakeBase(n=2), reranker, cache=cache)
    rr.retrieve("q", 2)   # fresh
    rr.retrieve("q", 2)   # served from cache
    summary = rr.latency_summary()
    assert summary["n_queries"] == 2
    assert summary["n_fresh"] == 1
    assert summary["cache_hits"] == 2


def test_latency_is_null_not_zero_when_nothing_was_measured(tmp_path):
    cache = ScoreCache(tmp_path / "c.json")
    reranker = FakeReranker(_table(d1=0.3))
    RerankingRetriever(FakeBase(n=1), reranker, cache=cache).retrieve("q", 1)
    rr = RerankingRetriever(FakeBase(n=1), reranker, cache=cache)
    rr.retrieve("q", 1)
    summary = rr.latency_summary()
    assert summary["n_fresh"] == 0
    assert summary["rerank_added_ms_p50"] is None  # not 0.0
    assert summary["rerank_added_ms_p95"] is None


def test_latency_summary_names_the_hardware():
    rr = RerankingRetriever(FakeBase(n=1), FakeReranker(_table(d1=0.1)))
    rr.retrieve("q", 1)
    summary = rr.latency_summary()
    assert summary["hardware"]
    assert summary["device"] == "cpu"


def test_percentiles_are_nearest_rank_and_empty_safe():
    assert _pct([], 50) is None
    assert _pct([1.0], 95) == 1.0
    assert _pct([1, 2, 3, 4], 50) == 2
    assert _pct(list(range(1, 21)), 95) == 19


# ---------------------------------------------------------------------------
# Control gate
# ---------------------------------------------------------------------------


def _control_record(recall=CONTROL_RECALL_AT_10, ceiling=CONTROL_CEILING_AT_10, n=338):
    return {
        "metrics": {"recall@10": recall},
        "recall_ceilings": {"recall@10": ceiling},
        "n_queries_scored": n,
    }


def test_control_gate_accepts_the_published_baseline():
    ok, msg = check_control(_control_record())
    assert ok, msg


def test_control_gate_rejects_a_drifted_recall():
    ok, _ = check_control(_control_record(recall=CONTROL_RECALL_AT_10 + 0.01))
    assert not ok


def test_control_gate_rejects_a_moved_ceiling():
    """A moved ceiling means a different label snapshot, not a better retriever."""
    ok, _ = check_control(_control_record(ceiling=0.7789))
    assert not ok


def test_control_gate_rejects_a_short_query_set():
    ok, _ = check_control(_control_record(n=300))
    assert not ok


def test_control_tolerance_is_rounding_only():
    """The pipeline is deterministic; the tolerance must not become a noise band."""
    assert CONTROL_TOLERANCE <= 0.0001


def test_snapshot_id_is_pinned():
    assert EXPECTED_LABELS_FINGERPRINT == "230c6ea9d9b7e8fd"


# ---------------------------------------------------------------------------
# Subsampling
# ---------------------------------------------------------------------------


def _queries(spec: dict[str, int]) -> list[Query]:
    out = []
    for topic, n in spec.items():
        for i in range(n):
            out.append(Query(query_id=f"{topic}{i:03d}", topic=topic,
                             text=f"claim {i} from {topic}", claim_type="empirical"))
    return out


def test_subsample_is_deterministic():
    qs = _queries({"a": 10, "b": 10, "c": 10})
    assert [q.query_id for q in stratified_subsample(qs, 9)] == \
           [q.query_id for q in stratified_subsample(qs, 9)]


def test_subsample_spreads_across_topics():
    """Drawing from three manuscripts would move the ceiling, not the retriever."""
    qs = _queries({"a": 30, "b": 3, "c": 3})
    picked = stratified_subsample(qs, 9)
    assert sorted({q.topic for q in picked}) == ["a", "b", "c"]


def test_subsample_larger_than_the_set_returns_everything():
    qs = _queries({"a": 4})
    assert len(stratified_subsample(qs, 100)) == 4


def test_subsample_handles_exhausted_topics():
    qs = _queries({"a": 8, "b": 1})
    picked = stratified_subsample(qs, 6)
    assert len(picked) == 6


# ---------------------------------------------------------------------------
# Per-claim-type breakdown
# ---------------------------------------------------------------------------


def test_by_claim_type_gives_each_slice_its_own_ceiling():
    """One global ceiling would misscale every slice.

    ``methodological`` here inherits one relevant document (ceiling 1.0);
    ``empirical`` inherits twenty (ceiling 10/20). Reporting both against the
    pooled ceiling would make one look strong and the other broken for reasons
    that have nothing to do with retrieval.
    """
    qs = [
        Query(query_id="q1", topic="t", text="a", claim_type="methodological"),
        Query(query_id="q2", topic="t", text="b", claim_type="empirical"),
    ]
    qrels = {
        "q1": {"d1": 1},
        "q2": {f"d{i}": 1 for i in range(1, 21)},
    }
    raw = {
        "q1": [RetrievedDoc("d1", "d1::c", 0.9, 1)],
        "q2": [RetrievedDoc(f"d{i}", f"d{i}::c", 1.0 - i / 100, i) for i in range(1, 21)],
    }
    out = metrics_by_claim_type(qs, qrels, raw, k=10)
    assert out["methodological"]["n"] == 1
    assert out["methodological"]["ceilings"]["recall@10"] == pytest.approx(1.0)
    assert out["empirical"]["ceilings"]["recall@10"] == pytest.approx(0.5)
    assert out["empirical"]["metrics"]["recall@10"] == pytest.approx(0.5)
    assert out["empirical"]["percent_of_attainable"]["recall@10"] == pytest.approx(1.0)


def test_by_claim_type_reports_thin_slices_rather_than_hiding_them():
    qs = [Query(query_id="q1", topic="t", text="a", claim_type="rare")]
    out = metrics_by_claim_type(qs, {"q1": {"d1": 1}},
                                {"q1": [RetrievedDoc("d1", "d1::c", 0.9, 1)]}, k=10)
    assert out["rare"]["n"] == 1


def test_by_claim_type_labels_missing_types_rather_than_dropping_them():
    qs = [Query(query_id="q1", topic="t", text="a", claim_type=None)]
    out = metrics_by_claim_type(qs, {"q1": {"d1": 1}},
                                {"q1": [RetrievedDoc("d1", "d1::c", 0.9, 1)]}, k=10)
    assert "unlabelled" in out


# ---------------------------------------------------------------------------
# Arm wiring
# ---------------------------------------------------------------------------


def test_arm_spec_defaults_rerank_the_whole_pool():
    spec = ArmSpec(arm="a", oversample=5, rerank=True)
    assert spec.top_n is None
    assert spec.subsample is None


def test_local_arms_default_to_asserting_zero_spend():
    """"It's a local model so it's free" is a claim, and it is checked."""
    assert ArmSpec(arm="a", oversample=5, rerank=True).expect_zero_spend is True


# ---------------------------------------------------------------------------
# The gpt-5-mini arm mirrors the shipped code
# ---------------------------------------------------------------------------


RAG_RETRIEVAL = (
    Path(__file__).resolve().parents[4]
    / "services" / "backend" / "app" / "services" / "rag_retrieval.py"
)


def test_llm_arm_constants_match_the_shipped_reranker():
    """This arm is a copy, so drift in the original must break the build.

    ``rerank_results`` swallows its own failures and records no usage, which is
    why it is mirrored rather than called. A mirror that silently falls out of
    date measures a reranker nobody ships.
    """
    src = RAG_RETRIEVAL.read_text(encoding="utf-8")
    assert f'model="{LLM_RERANK_MODEL}"' in src
    assert f"chunks[:{LLM_RERANK_WINDOW}]" in src
    assert f"[:{LLM_RERANK_CHUNK_CHARS}]" in src
    assert f"max_completion_tokens={LLM_RERANK_MAX_COMPLETION_TOKENS}" in src


def test_shipped_reranker_still_has_the_uncounted_silent_noop():
    """Guards the finding, not the code.

    If someone fixes ``rerank_results`` to surface its failures, this test fails
    and RERANK.md's claim about an uncounted no-op has to be re-checked rather
    than left standing as a stale accusation.
    """
    src = RAG_RETRIEVAL.read_text(encoding="utf-8")
    tail = src.split("def rerank_results")[1].split("\ndef ")[0]
    assert "except Exception" in tail
    assert "return chunks[:top_k]" in tail
    assert "logger" not in tail  # nothing is logged; nothing is counted


def test_llm_reranker_orders_named_indices_first_and_counts_noops():
    """A ranking the model refused to produce must be counted, not absorbed."""
    llm = LLMReranker.__new__(LLMReranker)  # no client, no network
    llm.model_name = "gpt-5-mini"
    llm.top_k = 3
    llm.calls = llm.parse_failures = llm.noop_fallbacks = llm.pairs_scored = 0
    llm._client = None
    llm._budget = None

    class _Boom:
        def __getattr__(self, _):
            raise RuntimeError("no client")

    llm.client = lambda: _Boom()
    llm.last_error = None
    llm.last_finish_reason = None
    llm.last_completion_tokens = llm.last_reasoning_tokens = None
    llm.empty_content_responses = 0

    scores = llm.score("q", ["a", "b", "c"])
    assert llm.parse_failures == 1
    assert llm.noop_fallbacks == 1
    assert llm.health()["noop_rate"] == 1.0
    assert llm.health()["last_error"]  # the reason is kept, not swallowed
    # falls back to first-stage order, strictly descending
    assert scores == sorted(scores, reverse=True)


def test_reasoning_token_budget_makes_the_shipped_reranker_structurally_inert():
    """``max_completion_tokens=100`` on a reasoning model returns empty content.

    Measured against the live API on 2026-08-01: ``finish_reason='length'``,
    ``completion_tokens=100``, ``reasoning_tokens=100``, ``content=''``. The
    budget is consumed by reasoning before a single output token is emitted, so
    ``json.loads('')`` always raises and the reranker always falls back. This
    test pins the two constants that make that inevitable, so a fix to either
    one forces RERANK.md's claim to be re-measured.
    """
    assert LLM_RERANK_MAX_COMPLETION_TOKENS == 100
    assert LLM_RERANK_MODEL.startswith("gpt-5")

"""Metrics: a thin wrapper over ranx, plus per-miss failure attribution.

The arithmetic is ranx's, deliberately. NDCG has convention traps -- log base,
tie handling, whether ideal DCG comes from the qrels or the run, whether recall
is capped at k -- and a subtle hand-rolled bug silently invalidates every number
downstream while still producing plausible-looking output. Our job is correct
label construction and honest reporting, not re-deriving the discount function.

What ranx will not give you, and what this module adds, is **failure-mode
attribution**: for every relevant document that was not retrieved, why. That
breakdown is more actionable than the aggregate, because the three causes call
for completely different fixes.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import Enum

from ranx import Qrels, Run, evaluate

from .adapters import RetrievedDoc

DEFAULT_METRICS = [
    "recall@1",
    "recall@5",
    "recall@10",
    "recall@20",
    "mrr",
    "ndcg@10",
    "map",
]

#: Relevance units. Document is primary -- see RELEVANCE.md §2.
UNIT_DOCUMENT = "document"
UNIT_SECTION = "section"
UNIT_CHUNK = "chunk"
VALID_UNITS = (UNIT_DOCUMENT, UNIT_SECTION, UNIT_CHUNK)


class FailureMode(str, Enum):
    """Why a relevant document was not returned above k."""

    #: Never resolved to a corpus doc id -- excluded from the denominator
    #: upstream in labels.py, so this should not normally appear here.
    UNRESOLVED = "unresolved"
    #: Not in the corpus at all -- indexing/ingestion problem, not ranking.
    RETRIEVAL = "retrieval_failure"
    #: Present in the corpus and returned by the retriever, but ranked below k.
    RANKING = "ranking_failure"


@dataclass(frozen=True)
class Miss:
    query_id: str
    doc_id: str
    mode: FailureMode
    rank: int | None = None  # populated for ranking failures

    def to_dict(self) -> dict:
        return {
            "query_id": self.query_id,
            "doc_id": self.doc_id,
            "mode": self.mode.value,
            "rank": self.rank,
        }


# ---------------------------------------------------------------------------
# Pooling: chunk-level results -> the chosen relevance unit
# ---------------------------------------------------------------------------


def pool_to_unit(results: list[RetrievedDoc], unit: str) -> dict[str, float]:
    """Max-pool chunk scores up to the relevance unit.

    Max rather than sum: summing rewards a document simply for occupying more
    chunk slots, which is a length bias, not a relevance signal.

    Returns ``{unit_key: score}``. Ordering is left to ranx, which ranks by score.
    """
    if unit not in VALID_UNITS:
        raise ValueError(f"unit must be one of {VALID_UNITS}, got {unit!r}")

    pooled: dict[str, float] = {}
    for r in results:
        if unit == UNIT_DOCUMENT:
            key = r.doc_id
        elif unit == UNIT_CHUNK:
            key = r.chunk_id
        else:
            if r.section_id is None:
                raise ValueError(
                    "section-level scoring requested but the retriever returned a "
                    "result with section_id=None. Refusing to score a partial run."
                )
            key = r.section_id
        if key not in pooled or r.score > pooled[key]:
            pooled[key] = r.score
    return pooled


def truncate(pooled: dict[str, float], k: int) -> dict[str, float]:
    """Keep the top-k units. Applied AFTER pooling -- see RELEVANCE.md §3."""
    top = sorted(pooled.items(), key=lambda kv: (-kv[1], kv[0]))[:k]
    return dict(top)


def section_id_coverage(results: list[RetrievedDoc]) -> float:
    if not results:
        return 1.0
    return sum(1 for r in results if r.section_id is not None) / len(results)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def compute_metrics(
    qrels_dict: dict[str, dict[str, int]],
    run_dict: dict[str, dict[str, float]],
    metrics: list[str] | None = None,
) -> dict[str, float]:
    """Evaluate a run against qrels via ranx.

    Queries with no relevant documents are dropped: ranx cannot score them and
    including them would either crash or silently average in zeros, which
    understates every metric.
    """
    metrics = list(metrics or DEFAULT_METRICS)
    scorable = {q: rels for q, rels in qrels_dict.items() if rels}
    if not scorable:
        return {m: 0.0 for m in metrics}

    # ranx requires every qrels query to be present in the run; an empty result
    # set is a legitimate outcome (it scores 0), so materialise it explicitly.
    aligned_run = {q: (run_dict.get(q) or {"__no_result__": 0.0}) for q in scorable}

    scores = evaluate(Qrels(scorable), Run(aligned_run), metrics)
    if not isinstance(scores, dict):  # ranx returns a scalar for a single metric
        scores = {metrics[0]: scores}
    return {m: float(scores[m]) for m in metrics}


def attribute_failures(
    qrels_dict: dict[str, dict[str, int]],
    full_runs: dict[str, dict[str, float]],
    k: int,
    corpus_doc_ids: set[str],
    unresolved_count: int = 0,
) -> tuple[list[Miss], dict[str, int]]:
    """Classify every relevant document that did not appear in the top k.

    ``full_runs`` is the UNTRUNCATED pooled run per query -- the distinction
    between "the retriever never returned it" and "it returned it at rank 47"
    is exactly what separates a retrieval failure from a ranking failure, and it
    is unrecoverable from a truncated run.
    """
    misses: list[Miss] = []
    for qid, rels in qrels_dict.items():
        pooled = full_runs.get(qid, {})
        top_k = set(truncate(pooled, k))
        for doc_id in sorted(rels):
            if doc_id in top_k:
                continue
            if doc_id in pooled:
                ordered = sorted(pooled.items(), key=lambda kv: (-kv[1], kv[0]))
                rank = next(i for i, (d, _) in enumerate(ordered, 1) if d == doc_id)
                misses.append(Miss(qid, doc_id, FailureMode.RANKING, rank))
            elif doc_id not in corpus_doc_ids:
                misses.append(Miss(qid, doc_id, FailureMode.UNRESOLVED))
            else:
                misses.append(Miss(qid, doc_id, FailureMode.RETRIEVAL))

    counts = Counter(m.mode.value for m in misses)
    breakdown = {mode.value: counts.get(mode.value, 0) for mode in FailureMode}
    # References that never became corpus docs are excluded from the recall
    # denominator upstream; surfaced here so the exclusion is never invisible.
    breakdown["unresolved_references_excluded_upstream"] = unresolved_count
    breakdown["total_misses"] = len(misses)
    return misses, breakdown


@dataclass
class EvalResult:
    unit: str
    k: int
    metrics: dict[str, float]
    failure_breakdown: dict[str, int]
    misses: list[Miss]
    n_queries: int
    n_queries_scored: int
    n_relevant_total: int

    def to_dict(self, include_misses: bool = True) -> dict:
        out = {
            "relevance_unit": self.unit,
            "k": self.k,
            "metrics": self.metrics,
            "failure_breakdown": self.failure_breakdown,
            "n_queries": self.n_queries,
            "n_queries_scored": self.n_queries_scored,
            "n_relevant_total": self.n_relevant_total,
        }
        if include_misses:
            out["misses"] = [m.to_dict() for m in self.misses]
        return out


def evaluate_run(
    qrels_dict: dict[str, dict[str, int]],
    raw_results: dict[str, list[RetrievedDoc]],
    corpus_doc_ids: set[str],
    unit: str = UNIT_DOCUMENT,
    k: int = 10,
    metrics: list[str] | None = None,
    unresolved_count: int = 0,
) -> EvalResult:
    """Score raw per-query retrieval results end to end."""
    full_runs = {qid: pool_to_unit(res, unit) for qid, res in raw_results.items()}
    scorable = {q: rels for q, rels in qrels_dict.items() if rels}

    scores = compute_metrics(scorable, full_runs, metrics)
    misses, breakdown = attribute_failures(
        scorable, full_runs, k, corpus_doc_ids, unresolved_count
    )

    return EvalResult(
        unit=unit,
        k=k,
        metrics=scores,
        failure_breakdown=breakdown,
        misses=misses,
        n_queries=len(qrels_dict),
        n_queries_scored=len(scorable),
        n_relevant_total=sum(len(v) for v in scorable.values()),
    )

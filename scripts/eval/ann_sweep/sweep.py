"""Sweep orchestration: one measurement point in, one append-only record out.

APPEND-ONLY, ALWAYS
    ``scripts/eval/run_eval.py`` overwrote its scoreboard in place and destroyed
    this repo's entire eval history once already. Results here are JSONL, opened
    with mode "a", keyed by (record_type, parameters, corpus fingerprint). A
    re-run of the same point does not replace the old one -- it lands beside it,
    and a disagreement between two identical keys is then visible instead of
    silently resolved in favour of whichever ran last.

WHAT A RECORD CONTAINS AND WHY
    Parameters, corpus fingerprint, BOTH recalls (vs exact, vs labels), latency
    WITH its method, build cost, the index the planner actually used, and n. A
    record missing any of those is not comparable to another record and the
    schema makes omitting them awkward on purpose.
"""

from __future__ import annotations

import json
import platform
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence

from . import latency as latency_mod
from .grid import BuildConfig, EfSearchConfig
from .index_ops import BuildOutcome, build_hnsw_index, drop_index
from .search import (
    SearchSpec,
    explain_plan_text,
    index_used,
    measurement_txn,
    run_search,
    time_search_client,
    time_search_server,
)

EVAL_DIR = Path(__file__).resolve().parent.parent
DEFAULT_RESULTS_PATH = EVAL_DIR / "results" / "ann_sweep.jsonl"

SWEEP_VERSION = "1.0.0"

#: Retrieval depth. The retrieval baseline asks the index for k=10 x oversample 5
#: chunks and max-pools them to documents, so 50 is the depth production's
#: draft-analysis path actually exercises. ANN recall is quoted at this depth.
DEFAULT_SEARCH_K = 50

DEFAULT_REPETITIONS = 3
DEFAULT_WARMUP = 1


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class QuerySet:
    """The queries under measurement, already embedded.

    Embeddings are supplied rather than computed: the embedding model is a
    property of the system under test and re-embedding per sweep point would
    both cost money and add API jitter to a latency measurement.
    """

    query_ids: list[str]
    embeddings: list[Sequence[float]]
    fingerprint: str = ""

    def __post_init__(self):
        if len(self.query_ids) != len(self.embeddings):
            raise ValueError(
                f"query_ids ({len(self.query_ids)}) and embeddings "
                f"({len(self.embeddings)}) must be the same length"
            )

    def __len__(self) -> int:
        return len(self.query_ids)


@dataclass(frozen=True)
class CorpusFingerprint:
    """What the numbers describe. Stamped on every record; never optional."""

    documents: int
    chunks: int
    project_id: str
    table: str = "document_chunks"

    def to_dict(self) -> dict:
        return {
            "documents": self.documents,
            "chunks": self.chunks,
            "project_id": self.project_id,
            "table": self.table,
            "note": (
                "Small corpus. HNSW's asymptotic advantage does not appear at this "
                "scale; an exact scan may legitimately win here and still lose at 100x."
            ),
        }


def corpus_fingerprint(conn, spec: SearchSpec) -> CorpusFingerprint:
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT count(*) FROM {spec.schema}.{spec.table} WHERE project_id = %s::uuid",
            (spec.project_id,),
        )
        chunks = int(cur.fetchone()[0])
        cur.execute(
            f"SELECT count(DISTINCT document_id) FROM {spec.schema}.{spec.table} "
            "WHERE project_id = %s::uuid",
            (spec.project_id,),
        )
        docs = int(cur.fetchone()[0])
    return CorpusFingerprint(documents=docs, chunks=chunks, project_id=spec.project_id, table=spec.table)


# ---------------------------------------------------------------------------
# Recall against exact search
# ---------------------------------------------------------------------------


def ann_recall_vs_exact(
    approx: dict[str, list[str]], exact: dict[str, list[str]], k: int
) -> float | None:
    """Mean over queries of |approx@k ∩ exact@k| / |exact@k|.

    A property of the INDEX, not of the system: it says how much of the true
    nearest-neighbour list the approximation lost. Distinct from recall against
    citation labels, which is a property of everything.

    The denominator is |exact@k|, not k: when the corpus has fewer than k
    eligible rows, exact search returns fewer than k and dividing by k would
    report a recall below 1.0 for an index that lost nothing.
    """
    per_query = []
    for qid, exact_ids in exact.items():
        truth = exact_ids[:k]
        if not truth:
            continue
        got = set(approx.get(qid, [])[:k])
        per_query.append(len(got & set(truth)) / len(truth))
    if not per_query:
        return None
    return sum(per_query) / len(per_query)


# ---------------------------------------------------------------------------
# One measurement point
# ---------------------------------------------------------------------------


@dataclass
class PointResult:
    hits: dict[str, list]  # query_id -> list[Hit]
    chunk_ids: dict[str, list[str]]
    latency_server: latency_mod.LatencyStats
    latency_client: latency_mod.LatencyStats
    plan_index: str | None
    plan_text: str


def measure_point(
    conn,
    spec: SearchSpec,
    queries: QuerySet,
    k: int = DEFAULT_SEARCH_K,
    ef_search: int | None = None,
    keep_index: str | None = None,
    exact: bool = False,
    force_index_scan: bool = False,
    repetitions: int = DEFAULT_REPETITIONS,
    warmup: int = DEFAULT_WARMUP,
) -> PointResult:
    """Run every query at one configuration: results once, timings ``repetitions`` times.

    Order of operations is deliberate. Results are collected first, then warmup
    runs, then timed runs -- so no timed sample is ever the first touch of a
    cold index page, and the warmup count is stated rather than assumed.
    """
    if repetitions < 1:
        raise ValueError("repetitions must be >= 1")
    if warmup < 0:
        raise ValueError("warmup must be >= 0")

    with measurement_txn(
        conn, spec, ef_search=ef_search, keep_index=keep_index, exact=exact,
        force_index_scan=force_index_scan,
    ):
        hits: dict[str, list] = {}
        chunk_ids: dict[str, list[str]] = {}
        for qid, emb in zip(queries.query_ids, queries.embeddings):
            rows = run_search(conn, spec, emb, k)
            hits[qid] = rows
            chunk_ids[qid] = [r.chunk_id for r in rows]

        plan_text = ""
        plan_idx = None
        if queries.embeddings:
            plan_text = explain_plan_text(conn, spec, queries.embeddings[0], k)
            plan_idx = index_used(plan_text)

        for _ in range(warmup):
            for emb in queries.embeddings:
                time_search_server(conn, spec, emb, k)

        server_samples: list[float] = []
        client_samples: list[float] = []
        for _ in range(repetitions):
            for emb in queries.embeddings:
                server_samples.append(time_search_server(conn, spec, emb, k))
                client_samples.append(time_search_client(conn, spec, emb, k))

    n_q = len(queries)
    return PointResult(
        hits=hits,
        chunk_ids=chunk_ids,
        latency_server=latency_mod.summarise(
            server_samples, n_q, repetitions, warmup * n_q, latency_mod.CLOCK_SERVER
        ),
        latency_client=latency_mod.summarise(
            client_samples, n_q, repetitions, warmup * n_q, latency_mod.CLOCK_CLIENT,
            notes=["includes loopback round trip; comparable to the query itself on this corpus"],
        ),
        plan_index=plan_idx,
        plan_text=plan_text,
    )


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------


def make_record(
    record_type: str,
    params: dict,
    corpus: CorpusFingerprint,
    n_queries: int,
    point: PointResult | None = None,
    ann_recall: dict | None = None,
    label_metrics: dict | None = None,
    build: BuildOutcome | None = None,
    status: str = "ok",
    error: str | None = None,
    extra: dict | None = None,
) -> dict:
    """Assemble one append-only result record."""
    rec = {
        "sweep_version": SWEEP_VERSION,
        "record_type": record_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "error": error,
        "params": params,
        "corpus_fingerprint": corpus.to_dict(),
        "n_queries": n_queries,
        "n_note": f"every metric in this record is over n = {n_queries} queries",
        "ann_recall_vs_exact": ann_recall,
        "metrics_vs_labels": label_metrics,
        "build": build.to_dict() if build else None,
        "environment": {"python": platform.python_version()},
    }
    rec["index_scan_forced"] = bool((params or {}).get("index_scan_forced"))
    if point is not None:
        rec["latency_server_ms"] = point.latency_server.to_dict()
        rec["latency_client_ms"] = point.latency_client.to_dict()
        rec["latency_method"] = point.latency_server.method_statement()
        rec["plan_index_used"] = point.plan_index
        rec["plan"] = point.plan_text
    else:
        rec["latency_server_ms"] = None
        rec["latency_client_ms"] = None
        rec["latency_method"] = None
        rec["plan_index_used"] = None
        rec["plan"] = None
    if extra:
        rec.update(extra)
    return rec


def append_record(record: dict, path: Path | str = DEFAULT_RESULTS_PATH) -> Path:
    """Append one JSON record as a line. Never truncates, never rewrites."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:  # "a" -- load bearing
        fh.write(json.dumps(record, sort_keys=True, default=str) + "\n")
    return p


def read_records(path: Path | str = DEFAULT_RESULTS_PATH) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


# ---------------------------------------------------------------------------
# Sweeps
# ---------------------------------------------------------------------------


#: A scorer maps {query_id: [Hit, ...]} to a dict of label-based metrics, or None
#: when no label set is wired up. Injected so this module needs neither the
#: retrieval harness nor a corpus on disk to be tested.
Scorer = Callable[[dict], dict]


@dataclass
class SweepOutput:
    records: list[dict] = field(default_factory=list)
    created_indexes: list[str] = field(default_factory=list)


def probe_planner_choice(
    conn,
    spec: SearchSpec,
    queries: QuerySet,
    corpus: CorpusFingerprint,
    k_values: Sequence[int] = (1, 3, 5, 10, 15, 20, 25, 30, 40, 50, 100),
    ef_search: int | None = None,
    results_path: Path | str | None = DEFAULT_RESULTS_PATH,
) -> dict:
    """At each LIMIT, does the planner USE the HNSW index or decline it?

    This is the question that decides whether any of the rest of the sweep
    describes production. Postgres has no index hints, so the plan is the only
    honest answer, and the answer turns out to depend on k: an HNSW index scan
    has a high startup cost and a low per-row cost, so it wins at small LIMITs
    and loses at large ones on a corpus this small.

    Runs entirely inside a rolled-back transaction. Changes nothing.
    """
    rows = []
    with measurement_txn(conn, spec, ef_search=ef_search):
        for k in k_values:
            plan = explain_plan_text(conn, spec, queries.embeddings[0], k)
            rows.append({"k": k, "index_used": index_used(plan), "plan": plan})
    record = make_record(
        record_type="planner_choice",
        params={"k_values": list(k_values), "ef_search": ef_search},
        corpus=corpus,
        n_queries=len(queries),
        extra={
            "planner_choice_by_k": [{"k": r["k"], "index_used": r["index_used"]} for r in rows],
            "plans": {str(r["k"]): r["plan"] for r in rows},
            "note": (
                "'index_used': null means Postgres chose a sequential scan -- i.e. "
                "exact search -- and the HNSW index was not consulted at all."
            ),
        },
    )
    if results_path:
        append_record(record, results_path)
    return record


def run_exact_baseline(
    conn,
    spec: SearchSpec,
    queries: QuerySet,
    corpus: CorpusFingerprint,
    k: int = DEFAULT_SEARCH_K,
    repetitions: int = DEFAULT_REPETITIONS,
    warmup: int = DEFAULT_WARMUP,
    scorer: Scorer | None = None,
    results_path: Path | str | None = DEFAULT_RESULTS_PATH,
) -> tuple[dict[str, list[str]], dict]:
    """Exact sequential-scan search: the recall=1.0 ceiling, plus its latency.

    Returns ``(chunk_ids_per_query, record)``. The chunk ids are the ground truth
    every ANN configuration's recall is measured against; expressing ANN recall
    against another approximation would make the whole sweep circular.
    """
    point = measure_point(
        conn, spec, queries, k=k, exact=True, repetitions=repetitions, warmup=warmup
    )
    if point.plan_index is not None:
        raise RuntimeError(
            f"exact baseline used index {point.plan_index!r}; enable_indexscan=off did "
            "not take effect. Refusing to call an index scan 'exact'."
        )
    record = make_record(
        record_type="exact",
        params={"mode": "exact_sequential_scan", "k": k, "ef_search": None},
        corpus=corpus,
        n_queries=len(queries),
        point=point,
        ann_recall={"vs_exact@k": 1.0, "k": k, "note": "exact search IS the ground truth"},
        label_metrics=scorer(point.hits) if scorer else None,
        extra={"queries_fingerprint": queries.fingerprint},
    )
    if results_path:
        append_record(record, results_path)
    return point.chunk_ids, record


def run_ef_search_sweep(
    conn,
    spec: SearchSpec,
    queries: QuerySet,
    corpus: CorpusFingerprint,
    configs: list[EfSearchConfig],
    exact_chunk_ids: dict[str, list[str]] | None = None,
    k: int = DEFAULT_SEARCH_K,
    keep_index: str | None = None,
    force_index_scan: bool = False,
    repetitions: int = DEFAULT_REPETITIONS,
    warmup: int = DEFAULT_WARMUP,
    scorer: Scorer | None = None,
    results_path: Path | str | None = DEFAULT_RESULTS_PATH,
    progress: Callable[[str], None] | None = None,
) -> SweepOutput:
    """Sweep the query-time knob against the EXISTING index. No rebuilds.

    With ``force_index_scan=False`` this measures WHAT PRODUCTION EXECUTES,
    which on this corpus turns out not to involve the index at all. With it
    True it measures the index. Both are run; conflating them is the mistake
    this parameter exists to prevent.
    """
    out = SweepOutput()
    for cfg in configs:
        if progress:
            progress(f"[ef_search] {cfg.label}{' [forced index scan]' if force_index_scan else ''}")
        try:
            point = measure_point(
                conn, spec, queries, k=k, ef_search=cfg.ef_search,
                keep_index=keep_index, force_index_scan=force_index_scan,
                repetitions=repetitions, warmup=warmup,
            )
        except Exception as exc:
            out.records.append(
                make_record(
                    "ef_search",
                    {**cfg.to_dict(), "k": k, "index_scan_forced": force_index_scan},
                    corpus, len(queries),
                    status="measurement_failed", error=f"{type(exc).__name__}: {exc}",
                )
            )
            if results_path:
                append_record(out.records[-1], results_path)
            continue

        ann = None
        if exact_chunk_ids is not None:
            ann = {
                "k": k,
                f"recall@{k}": ann_recall_vs_exact(point.chunk_ids, exact_chunk_ids, k),
                "recall@10": ann_recall_vs_exact(point.chunk_ids, exact_chunk_ids, 10),
                "unit": "chunk",
                "note": "overlap with exact sequential scan; property of the index, not the system",
            }
        rec = make_record(
            "ef_search", {**cfg.to_dict(), "k": k, "index_scan_forced": force_index_scan},
            corpus, len(queries),
            point=point, ann_recall=ann,
            label_metrics=scorer(point.hits) if scorer else None,
            extra={"queries_fingerprint": queries.fingerprint},
        )
        out.records.append(rec)
        if results_path:
            append_record(rec, results_path)
    return out


def run_build_sweep(
    conn,
    spec: SearchSpec,
    queries: QuerySet,
    corpus: CorpusFingerprint,
    configs: list[BuildConfig],
    exact_chunk_ids: dict[str, list[str]] | None = None,
    k: int = DEFAULT_SEARCH_K,
    ef_search: int | None = None,
    force_index_scan: bool = True,
    repetitions: int = DEFAULT_REPETITIONS,
    warmup: int = DEFAULT_WARMUP,
    scorer: Scorer | None = None,
    results_path: Path | str | None = DEFAULT_RESULTS_PATH,
    progress: Callable[[str], None] | None = None,
    drop_after_each: bool = True,
) -> SweepOutput:
    """Build each candidate index, measure it, and drop it.

    ``force_index_scan`` defaults True here, unlike in the ef_search sweep. On a
    corpus this small the planner declines every HNSW index at k=50, so without
    forcing there is nothing to compare across m and ef_construction -- every
    row would be the same sequential scan. Build time and index size are real
    regardless; the query numbers describe the index, not production's plan.

    ``drop_after_each`` keeps at most one sweep index on the table at a time,
    which bounds the disk cost to a single extra index rather than the whole
    grid, and means an interrupted run leaves at most one stray -- which the CLI
    then names and removes.

    A configuration the database refuses to build produces a ``build_failed``
    record and the sweep continues. Losing a grid because one point was invalid
    would be an own goal.
    """
    out = SweepOutput()
    for cfg in configs:
        if progress:
            progress(f"[build] {cfg.label}")
        params = {
            **cfg.to_dict(),
            "k": k,
            "ef_search": ef_search,
            "index_scan_forced": force_index_scan,
        }
        outcome = build_hnsw_index(conn, cfg, table=spec.table, column=spec.column, schema=spec.schema)
        if not outcome.ok:
            rec = make_record(
                "build", params, corpus, len(queries),
                build=outcome, status="build_failed", error=outcome.error,
            )
            out.records.append(rec)
            if results_path:
                append_record(rec, results_path)
            continue

        out.created_indexes.append(cfg.index_name)
        try:
            point = measure_point(
                conn, spec, queries, k=k, ef_search=ef_search,
                keep_index=cfg.index_name, force_index_scan=force_index_scan,
                repetitions=repetitions, warmup=warmup,
            )
            if point.plan_index != cfg.index_name:
                raise RuntimeError(
                    f"planner used {point.plan_index!r}, not the candidate "
                    f"{cfg.index_name!r}; this point would be mislabelled"
                )
            ann = None
            if exact_chunk_ids is not None:
                ann = {
                    "k": k,
                    f"recall@{k}": ann_recall_vs_exact(point.chunk_ids, exact_chunk_ids, k),
                    "recall@10": ann_recall_vs_exact(point.chunk_ids, exact_chunk_ids, 10),
                    "unit": "chunk",
                    "note": "overlap with exact sequential scan; property of the index",
                }
            rec = make_record(
                "build", params, corpus, len(queries),
                point=point, ann_recall=ann, build=outcome,
                label_metrics=scorer(point.hits) if scorer else None,
                extra={"queries_fingerprint": queries.fingerprint},
            )
        except Exception as exc:
            rec = make_record(
                "build", params, corpus, len(queries),
                build=outcome, status="measurement_failed",
                error=f"{type(exc).__name__}: {exc}",
            )
        out.records.append(rec)
        if results_path:
            append_record(rec, results_path)

        if drop_after_each:
            drop_index(conn, cfg.index_name, spec.schema)
            out.created_indexes.remove(cfg.index_name)
    return out

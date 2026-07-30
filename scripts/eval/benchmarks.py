#!/usr/bin/env python3
"""Distil every measurement this project produces into one tracked board.

Why this exists
---------------
Five append-only measurement sinks feed this repo, and four of them are
gitignored. On a fresh clone the only surviving record of any benchmark was
hand-written prose in ``WAVE_LOG.md``. That is the same failure already fixed
once for ``run_eval.py`` -- which used to overwrite ``scoreboard.json`` in
place, destroying all eval history -- and then reintroduced one level down, at
the ``.gitignore``.

Tracking the raw sinks wholesale is the wrong fix. Record sizes are bimodal:
a retrieval summary record is ~2.7 KB, but the same record carrying its
per-query ``misses`` list is 66-99 KB, and raw spans grow without bound. So
this distils instead: one small, human-readable board plus a machine-readable
twin, both tracked, both regenerable, both byte-stable so they diff cleanly.

Honesty rules, which are the point of the tool
----------------------------------------------
1. No metric is ever printed without its ``n``. A number without a sample size
   is not a benchmark. ``_metric`` refuses rather than emitting a bare float.
2. Invalid runs never reach a headline. Retrieval records carry ``valid`` and a
   ``degradation`` block; invalid ones are excluded and listed separately with
   the reason.
3. The recall ceiling travels with the number. ``recall@k`` here is capped by
   construction -- a query inherits its manuscript's whole reference list, so a
   query with 37 relevant documents cannot exceed ``recall@10 = 10/37``. Where
   the ceiling is known, measured / ceiling / percent-of-attainable print
   together; where it is not, the row says so rather than staying silent.
4. Incomplete cost is marked. Any ``unpriced_calls > 0`` makes the total a
   lower bound and it renders as ``$0.1654 >=``, never as a clean total.
5. Every row names the file and ``run_id`` it came from.
6. Trends are only drawn between records sharing a ``config_hash``. Two
   different hashes are two different measurements and are never differenced --
   that is the entire reason the hash is recorded.

Usage::

    python3 scripts/eval/benchmarks.py            # write both outputs
    python3 scripts/eval/benchmarks.py --check    # non-zero if stale
    python3 scripts/eval/benchmarks.py --stdout   # print, write nothing
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

EVAL_DIR = Path(__file__).resolve().parent
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

MD_PATH = EVAL_DIR / "BENCHMARKS.md"
JSON_PATH = EVAL_DIR / "benchmarks.json"

#: Bumped when the shape of benchmarks.json changes incompatibly.
SCHEMA_VERSION = 1

# Source paths, relative to scripts/eval/. Every one may be absent on a fresh
# clone -- four of the five are gitignored, which is why this file exists.
SRC_RETRIEVAL = "results/retrieval_eval.jsonl"
SRC_NODE_EVAL = "results/node_eval.jsonl"
SRC_SPANS = "results/node_eval_spans.jsonl"
SRC_INGEST = "cache/ingest_manifest.jsonl"
SRC_HISTORY = "results/history.jsonl"
SRC_OPENREVIEW = "results/openreview_history.jsonl"
SRC_SWEEP = "gate_calibration/sweep_results.jsonl"

SOURCES = (
    SRC_RETRIEVAL,
    SRC_NODE_EVAL,
    SRC_SPANS,
    SRC_INGEST,
    SRC_HISTORY,
    SRC_OPENREVIEW,
    SRC_SWEEP,
)

# ---------------------------------------------------------------------------
# Recall ceilings
# ---------------------------------------------------------------------------
# recall@k is capped by the label design, not by the retriever. The ceiling is
# a property of (labels, queries), so it is keyed by the fingerprints the
# harness already stamps on every record. If either fingerprint changes, the
# ceiling for that pair is unknown and the board says "unknown" -- an
# out-of-date ceiling would be worse than none, because it makes a retriever
# look better or worse than it is.
#
# Provenance: measured in scripts/eval/retrieval/BASELINE.md §"recall@k is
# capped well below 1.0 by construction", query-count weighted, over the
# 59-query / 118-document local corpus.
KNOWN_RECALL_CEILINGS: dict[tuple[str, str], dict[int, float]] = {
    ("019bee4a06eb2d39", "1f6c584e8fd6c055"): {1: 0.1061, 5: 0.5307, 10: 0.7789, 20: 0.8798},
}


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

@dataclass
class SourceRead:
    """One measurement sink, and everything that was skipped reading it."""

    path: str
    present: bool = False
    lines: int = 0
    records: list[dict] = field(default_factory=list)
    skipped: int = 0
    #: (line number, reason) for skipped lines -- truncation included.
    skip_reasons: list[tuple[int, str]] = field(default_factory=list)

    def note_skip(self, line_no: int, reason: str) -> None:
        self.skipped += 1
        if len(self.skip_reasons) < 5:
            self.skip_reasons.append((line_no, reason))

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "present": self.present,
            "lines": self.lines,
            "records": len(self.records),
            "skipped_lines": self.skipped,
            "skip_reasons": [{"line": n, "reason": r} for n, r in self.skip_reasons],
        }


def read_jsonl(root: Path, rel: str) -> SourceRead:
    """Read one JSONL sink. A bad line is counted, never fatal.

    A truncated final line -- the process was killed mid-write -- is just a
    JSONDecodeError from here, and gets the same treatment as any other
    garbage: skipped and counted. There is deliberately no separate code path,
    because an interrupted write and a corrupt write are indistinguishable.
    """
    out = SourceRead(path=rel)
    full = root / rel
    if not full.exists():
        return out
    out.present = True
    try:
        text = full.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        out.note_skip(0, f"unreadable: {exc}")
        return out
    for line_no, raw in enumerate(text.splitlines(), start=1):
        out.lines += 1
        stripped = raw.strip()
        if not stripped:
            out.note_skip(line_no, "blank")
            continue
        try:
            payload = json.loads(stripped)
        except (ValueError, TypeError) as exc:
            out.note_skip(line_no, f"not JSON: {exc}")
            continue
        if not isinstance(payload, dict):
            out.note_skip(line_no, f"not an object: {type(payload).__name__}")
            continue
        out.records.append(payload)
    return out


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------

def _num(value: Any, places: int = 4) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int,)):
        return f"{value:,}"
    try:
        return f"{float(value):.{places}f}"
    except (TypeError, ValueError):
        return str(value)


def _metric(value: Any, n: Any, places: int = 4) -> str:
    """A metric never renders without its sample size. Rule 1.

    ``n is None`` means the source did not record one, and that is reported as
    such -- the number is withheld, because a metric whose n is unknown cannot
    be compared to anything.
    """
    if n is None:
        return "withheld (n unknown)"
    if value is None:
        return f"no data (n={n:,})"
    return f"{_num(value, places)} (n={n:,})"


def _usd(value: Any, unpriced: int) -> str:
    """Cost with an incompleteness marker. Rule 4."""
    if value is None:
        return "unknown"
    text = f"${float(value):.4f}"
    if unpriced:
        return f"{text} >= ({unpriced} unpriced call{'s' if unpriced != 1 else ''})"
    return text


def _date(stamp: Any) -> str:
    if not isinstance(stamp, str) or not stamp:
        return "unknown"
    return stamp.split("T")[0]


def _short(value: Any, width: int = 12) -> str:
    if value is None:
        return "unknown"
    text = str(value)
    return text if len(text) <= width else text[:width]


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    if not rows:
        return ["_(no rows)_"]
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join("---" for _ in headers) + "|"]
    for row in rows:
        out.append("| " + " | ".join(str(c) for c in row) + " |")
    return out


def _delta(new: Any, old: Any, places: int = 4) -> str:
    if new is None or old is None:
        return "unknown"
    diff = float(new) - float(old)
    sign = "+" if diff > 0 else ""
    return f"{sign}{diff:.{places}f}"


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------

def _ceiling_for(record: dict) -> tuple[dict[int, float] | None, str]:
    """(ceilings by k, provenance). ``None`` means unknown -- say so. Rule 3.

    A ceiling carried on the record itself always wins: if the harness ever
    starts computing it per-run, that number is authoritative and this table
    should stop being consulted.
    """
    carried = record.get("recall_ceilings") or record.get("ceilings")
    if isinstance(carried, dict) and carried:
        parsed: dict[int, float] = {}
        for key, value in carried.items():
            try:
                parsed[int(str(key).replace("recall@", ""))] = float(value)
            except (TypeError, ValueError):
                continue
        if parsed:
            return parsed, "carried on record"
    config = record.get("config") or {}
    key = (str(config.get("labels_fingerprint")), str(config.get("queries_fingerprint")))
    if key in KNOWN_RECALL_CEILINGS:
        return KNOWN_RECALL_CEILINGS[key], "retrieval/BASELINE.md (labels+queries fingerprint match)"
    return None, "unknown (no ceiling recorded for this labels/queries fingerprint)"


def _invalidation_reason(record: dict) -> str:
    reasons: list[str] = []
    for token in record.get("invalidated_by") or []:
        reasons.append(str(token))
    degradation = record.get("degradation") or {}
    if degradation.get("degraded"):
        name = degradation.get("name") or "retrieval leg"
        error = degradation.get("last_error")
        count = degradation.get("failure_count")
        detail = f"{name} degraded"
        if count:
            detail += f" ({count} failure(s))"
        if error:
            detail += f": {error}"
        reasons.append(detail)
    elif not degradation.get("checked", True):
        reasons.append("degradation not checked")
    if not reasons:
        reasons.append("valid=false, no reason recorded")
    return "; ".join(reasons)


def distil_retrieval(source: SourceRead) -> dict[str, Any]:
    valid: list[dict] = []
    invalidated: list[dict] = []

    for record in source.records:
        config = record.get("config") or {}
        ceilings, ceiling_note = _ceiling_for(record)
        metrics = record.get("metrics") or {}
        n_queries = record.get("n_queries_scored")
        if n_queries is None:
            n_queries = record.get("n_queries")

        rows: list[dict[str, Any]] = []
        for name in sorted(metrics):
            value = metrics.get(name)
            entry: dict[str, Any] = {
                "metric": name,
                "value": value,
                "n_queries": n_queries,
                "ceiling": None,
                "pct_of_attainable": None,
                # Only recall@k is capped by the label design. MAP/MRR/NDCG are
                # not, so "unknown" would be misleading for them -- they get
                # "n/a" instead, which is a different statement.
                "ceiling_applicable": name.startswith("recall@"),
            }
            if name.startswith("recall@"):
                try:
                    k = int(name.split("@", 1)[1])
                except ValueError:
                    k = None
                if k is not None and ceilings and k in ceilings:
                    ceiling = ceilings[k]
                    entry["ceiling"] = ceiling
                    if value is not None and ceiling:
                        entry["pct_of_attainable"] = float(value) / float(ceiling)
            rows.append(entry)

        summary = {
            "run_id": record.get("run_id"),
            "timestamp": record.get("timestamp"),
            "source": SRC_RETRIEVAL,
            "retriever": config.get("retriever"),
            "relevance_unit": record.get("relevance_unit"),
            "k": record.get("k"),
            "config_hash": record.get("config_hash"),
            "labels_fingerprint": config.get("labels_fingerprint"),
            "queries_fingerprint": config.get("queries_fingerprint"),
            "graded": config.get("graded"),
            "chunk_oversample": config.get("chunk_oversample"),
            "n_queries": record.get("n_queries"),
            "n_queries_scored": record.get("n_queries_scored"),
            "n_relevant_total": record.get("n_relevant_total"),
            "ceiling_provenance": ceiling_note,
            "metrics": rows,
            # The aggregate of the `misses` payload. Carried here on purpose:
            # `misses` itself is the 66-99 KB part of the record and is not
            # tracked, but its rollup is the part anyone reads.
            "failure_breakdown": record.get("failure_breakdown") or {},
            "retrieval_health": record.get("retrieval_health") or {},
            "corpus": {
                "pooled_corpus_size": (record.get("resolution_report") or {}).get("pooled_corpus_size"),
                "n_topics": (record.get("resolution_report") or {}).get("n_topics"),
                "n_topics_with_labels": (record.get("resolution_report") or {}).get("n_topics_with_labels"),
                "references_resolved": (record.get("resolution_report") or {}).get("references_resolved"),
                "references_unresolved_excluded": (record.get("resolution_report") or {}).get(
                    "references_unresolved_excluded"
                ),
                "references_unresolved_by_reason": (record.get("resolution_report") or {}).get(
                    "references_unresolved_by_reason"
                ) or {},
            },
            "has_misses_payload": "misses" in record,
        }

        if record.get("valid") is False:
            summary["invalidation_reason"] = _invalidation_reason(record)
            invalidated.append(summary)
        else:
            valid.append(summary)

    # Headline = latest valid run per config hash. Rule 6: grouping is by hash,
    # so two different configs can never be differenced against each other.
    groups: dict[str, list[dict]] = {}
    for run in valid:
        groups.setdefault(str(run.get("config_hash")), []).append(run)
    for runs in groups.values():
        runs.sort(key=lambda r: (str(r.get("timestamp") or ""), str(r.get("run_id") or "")))

    headline = [runs[-1] for _, runs in sorted(groups.items())]
    deltas = []
    for config_hash, runs in sorted(groups.items()):
        if len(runs) < 2:
            continue
        first, last = runs[0], runs[-1]
        by_name = {row["metric"]: row for row in first["metrics"]}
        rows = []
        for row in last["metrics"]:
            prior = by_name.get(row["metric"])
            if prior is None:
                continue
            rows.append({
                "metric": row["metric"],
                "first": prior["value"],
                "last": row["value"],
                "delta": (
                    None if row["value"] is None or prior["value"] is None
                    else float(row["value"]) - float(prior["value"])
                ),
                "n_queries": row["n_queries"],
            })
        deltas.append({
            "config_hash": config_hash,
            "retriever": last.get("retriever"),
            "runs": len(runs),
            "first_run_id": first.get("run_id"),
            "first_timestamp": first.get("timestamp"),
            "last_run_id": last.get("run_id"),
            "last_timestamp": last.get("timestamp"),
            "metrics": rows,
        })

    return {
        "headline": headline,
        "invalidated": invalidated,
        "deltas": deltas,
        "n_runs": len(source.records),
        "n_valid": len(valid),
        "n_invalidated": len(invalidated),
        "config_hashes": sorted(groups),
    }


# ---------------------------------------------------------------------------
# Node replay (node_eval.jsonl)
# ---------------------------------------------------------------------------

def distil_node_eval(source: SourceRead) -> dict[str, Any]:
    summaries = [r for r in source.records if r.get("record_type") == "run_summary"]
    replays = [r for r in source.records if r.get("record_type") == "replay"]

    runs = []
    for record in summaries:
        config = record.get("config") or {}
        per_node = record.get("per_node") or []
        unpriced = sum(int(p.get("unpriced_calls") or 0) for p in per_node)
        nodes = []
        for entry in sorted(per_node, key=lambda p: (str(p.get("node")), str(p.get("paper_id")), str(p.get("reviewer_type")))):
            latency = entry.get("latency_seconds") or {}
            nodes.append({
                "node": entry.get("node"),
                "paper_id": entry.get("paper_id"),
                "reviewer_type": entry.get("reviewer_type"),
                "runs": entry.get("runs"),
                "failures": entry.get("failures"),
                "llm_calls": entry.get("llm_calls"),
                "prompt_tokens": entry.get("prompt_tokens"),
                "completion_tokens": entry.get("completion_tokens"),
                "cached_tokens": entry.get("cached_tokens"),
                "estimated_usd": entry.get("estimated_usd"),
                "unpriced_calls": int(entry.get("unpriced_calls") or 0),
                "latency_mean_s": latency.get("mean"),
                "latency_median_s": latency.get("median"),
                "latency_min_s": latency.get("min"),
                "latency_max_s": latency.get("max"),
                "latency_n": latency.get("n"),
            })
        runs.append({
            "run_id": record.get("run_id"),
            "timestamp": record.get("timestamp"),
            "source": SRC_NODE_EVAL,
            "config_key": _node_config_key(record),
            "nodes_requested": list(config.get("nodes") or []),
            "papers": list(config.get("papers") or []),
            "reviewer_type": config.get("reviewer_type"),
            "repeat": config.get("repeat"),
            "with_metric": config.get("with_metric"),
            "planned_replays": record.get("planned_replays"),
            "attempted_replays": record.get("attempted_replays"),
            "completed_replays": record.get("completed_replays"),
            "failed_replays": record.get("failed_replays"),
            "halted": record.get("halted"),
            "total_llm_calls": record.get("total_llm_calls"),
            "total_estimated_usd": record.get("total_estimated_usd"),
            "unpriced_calls": unpriced,
            "cost_is_lower_bound": unpriced > 0,
            "per_node": nodes,
        })
    runs.sort(key=lambda r: (str(r.get("timestamp") or ""), str(r.get("run_id") or "")))

    # Replay-level rollup, per node. Latency here is wall_seconds straight off
    # the replay record; n is the replay count and always travels with it.
    by_node: dict[str, dict[str, Any]] = {}
    for record in replays:
        node = str(record.get("node"))
        bucket = by_node.setdefault(node, {
            "node": node,
            "replays": 0,
            "ok": 0,
            "failed": 0,
            "wall_seconds": [],
            "llm_calls": 0,
            "estimated_usd": 0.0,
            "unpriced_calls": 0,
        })
        bucket["replays"] += 1
        if record.get("status") == "ok":
            bucket["ok"] += 1
        else:
            bucket["failed"] += 1
        wall = record.get("wall_seconds")
        if isinstance(wall, (int, float)):
            bucket["wall_seconds"].append(float(wall))
        usage = record.get("usage") or {}
        bucket["llm_calls"] += int(usage.get("calls") or 0)
        bucket["estimated_usd"] += float(usage.get("estimated_usd") or 0.0)
        bucket["unpriced_calls"] += int(usage.get("unpriced_calls") or 0)

    node_rows = []
    for node in sorted(by_node):
        bucket = by_node[node]
        walls = sorted(bucket.pop("wall_seconds"))
        bucket["wall_seconds_n"] = len(walls)
        bucket["wall_seconds_mean"] = (sum(walls) / len(walls)) if walls else None
        bucket["wall_seconds_min"] = walls[0] if walls else None
        bucket["wall_seconds_max"] = walls[-1] if walls else None
        bucket["cost_is_lower_bound"] = bucket["unpriced_calls"] > 0
        node_rows.append(bucket)

    return {
        "runs": runs,
        "n_run_summaries": len(summaries),
        "n_replays": len(replays),
        "per_node": node_rows,
        "deltas": _node_deltas(runs),
    }


def _node_config_key(record: dict) -> str:
    """A stable identity for "the same node-eval measurement".

    node_eval writes no config hash of its own, so one is derived from the
    fields that decide comparability: which nodes, which papers, which reviewer
    persona, and how many repeats. Two runs sharing this key measure the same
    thing; two that do not, do not, and are never differenced.
    """
    config = record.get("config") or {}
    parts = [
        ",".join(sorted(str(n) for n in (config.get("nodes") or []))),
        ",".join(sorted(str(p) for p in (config.get("papers") or []))),
        str(config.get("reviewer_type")),
        str(config.get("repeat")),
        str(config.get("with_metric")),
    ]
    return "|".join(parts)


def _node_deltas(runs: Sequence[dict]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict]] = {}
    for run in runs:
        groups.setdefault(str(run.get("config_key")), []).append(run)
    out = []
    for key, group in sorted(groups.items()):
        if len(group) < 2:
            continue
        first, last = group[0], group[-1]
        out.append({
            "config_key": key,
            "runs": len(group),
            "first_run_id": first.get("run_id"),
            "last_run_id": last.get("run_id"),
            "first_timestamp": first.get("timestamp"),
            "last_timestamp": last.get("timestamp"),
            "first_usd": first.get("total_estimated_usd"),
            "last_usd": last.get("total_estimated_usd"),
            "usd_delta": (
                None if first.get("total_estimated_usd") is None or last.get("total_estimated_usd") is None
                else float(last["total_estimated_usd"]) - float(first["total_estimated_usd"])
            ),
            "first_llm_calls": first.get("total_llm_calls"),
            "last_llm_calls": last.get("total_llm_calls"),
            "cost_is_lower_bound": bool(first.get("cost_is_lower_bound") or last.get("cost_is_lower_bound")),
        })
    return out


# ---------------------------------------------------------------------------
# Spans -- delegated to trace_report, which already parses this format
# ---------------------------------------------------------------------------

def distil_spans(root: Path) -> dict[str, Any]:
    """Latency/cost from raw spans, via ``trace_report``.

    Deliberately no second span parser: ``trace_report.parse`` already survives
    truncated final lines, out-of-order arrival, orphans and duplicate span ids,
    and ``trace_report.metrics.Percentiles`` already refuses quantiles the
    sample cannot support. Re-implementing either would mean two things to keep
    honest instead of one.
    """
    path = root / SRC_SPANS
    if not path.exists():
        return {"present": False}
    try:
        from trace_report import metrics as M
        from trace_report import parse as P
    except ImportError as exc:  # pragma: no cover - only if the package moves
        return {"present": True, "error": f"trace_report unavailable: {exc}"}

    result = P.load_span_files([path])
    traces = list(result.traces.values())
    latency = M.node_latency(traces)
    node_costs = M.cost_by_node(traces)
    tokens = M.token_totals(traces)
    costs = M.run_costs(traces)
    unpriced = sum(c.unpriced_spans for c in costs)

    rows = []
    for row in sorted(latency, key=lambda r: r.node):
        bucket = node_costs.get(row.node)
        rows.append({
            "node": row.node,
            "executions": row.executions,
            "traces_seen": row.traces_seen,
            "wall_ms": row.wall.to_dict(),
            "self_ms": row.self_.to_dict(),
            "usd": bucket.usd if bucket else None,
            "unpriced_spans": bucket.unpriced_spans if bucket else 0,
        })

    return {
        "present": True,
        "source": SRC_SPANS,
        "traces": len(traces),
        "parse": result.stats.to_dict(),
        "nodes": rows,
        "tokens": tokens.to_dict(),
        "cost": {
            "total_usd": sum(c.usd for c in costs),
            "unpriced_spans": unpriced,
            "cost_is_lower_bound": unpriced > 0,
            "runs": len(costs),
        },
    }


# ---------------------------------------------------------------------------
# Ingest manifest
# ---------------------------------------------------------------------------

def distil_ingest(source: SourceRead) -> dict[str, Any]:
    if not source.records:
        return {"n_records": 0}

    actions: dict[str, int] = {}
    extractors: dict[str, int] = {}
    models: dict[str, int] = {}
    chunking: dict[str, int] = {}
    tokens: list[int] = []
    chunks: list[int] = []
    errors = 0
    ceiling_hits = 0
    docs: set[str] = set()

    for record in source.records:
        actions[str(record.get("action"))] = actions.get(str(record.get("action")), 0) + 1
        extractors[str(record.get("extractor"))] = extractors.get(str(record.get("extractor")), 0) + 1
        model = f"{record.get('embedding_model')}@{record.get('embedding_dimensions')}"
        models[model] = models.get(model, 0) + 1
        chunk_key = (
            f"{record.get('chunking_method')}/{record.get('chunking_splitter')}"
            f" size={record.get('chunk_size')} overlap={record.get('chunk_overlap')}"
        )
        chunking[chunk_key] = chunking.get(chunk_key, 0) + 1
        if record.get("error"):
            errors += 1
        if record.get("cost_ceiling_applied"):
            ceiling_hits += 1
        if record.get("doc_id"):
            docs.add(str(record["doc_id"]))
        if isinstance(record.get("token_count"), (int, float)):
            tokens.append(int(record["token_count"]))
        if isinstance(record.get("chunk_count"), (int, float)):
            chunks.append(int(record["chunk_count"]))

    def _stats(values: list[int]) -> dict[str, Any]:
        values = sorted(values)
        return {
            "n": len(values),
            "total": sum(values) if values else None,
            "mean": (sum(values) / len(values)) if values else None,
            "min": values[0] if values else None,
            "max": values[-1] if values else None,
        }

    return {
        "source": SRC_INGEST,
        "n_records": len(source.records),
        "n_distinct_docs": len(docs),
        "errors": errors,
        "cost_ceiling_applied": ceiling_hits,
        "actions": dict(sorted(actions.items())),
        "extractors": dict(sorted(extractors.items())),
        "embedding_models": dict(sorted(models.items())),
        "chunking_configs": dict(sorted(chunking.items())),
        "tokens": _stats(tokens),
        "chunks": _stats(chunks),
    }


# ---------------------------------------------------------------------------
# Scoreboard history (history.jsonl / openreview_history.jsonl)
# ---------------------------------------------------------------------------

def distil_history(source: SourceRead, label: str) -> dict[str, Any]:
    runs = []
    for record in source.records:
        aggregates = record.get("aggregates") or {}
        cells = record.get("cells") or []
        scored = [c for c in cells if c.get("overall") is not None]
        runs.append({
            "run_id": record.get("run_id"),
            "generated_at": record.get("generated_at"),
            "source": source.path,
            "pipeline_version": record.get("pipeline_version"),
            "mean_overall": aggregates.get("mean_overall"),
            "total_hallucinations": aggregates.get(
                "total_hallucinations",
                sum(int(c.get("hallucinations") or 0) for c in cells) if cells else None,
            ),
            "total_cells": aggregates.get("total_cells", len(cells)),
            "scored_cells": aggregates.get("scored_cells", len(scored)),
            "papers": aggregates.get("papers"),
            "config": record.get("config") or {},
        })
    runs.sort(key=lambda r: (str(r.get("generated_at") or ""), str(r.get("run_id") or "")))

    # Rule 6 again: the pipeline version is this track's config hash. Runs from
    # different pipeline versions are different measurements.
    groups: dict[str, list[dict]] = {}
    for run in runs:
        groups.setdefault(str(run.get("pipeline_version")), []).append(run)

    deltas = []
    for version, group in sorted(groups.items()):
        if len(group) < 2:
            continue
        first, last = group[0], group[-1]
        deltas.append({
            "pipeline_version": version,
            "runs": len(group),
            "first_run_id": first.get("run_id"),
            "last_run_id": last.get("run_id"),
            "first_mean_overall": first.get("mean_overall"),
            "last_mean_overall": last.get("mean_overall"),
            "mean_overall_delta": (
                None if first.get("mean_overall") is None or last.get("mean_overall") is None
                else float(last["mean_overall"]) - float(first["mean_overall"])
            ),
            "n_scored_cells": last.get("scored_cells"),
            "first_hallucinations": first.get("total_hallucinations"),
            "last_hallucinations": last.get("total_hallucinations"),
        })

    return {
        "label": label,
        "source": source.path,
        "n_runs": len(runs),
        "runs": runs,
        "pipeline_versions": sorted(groups),
        "deltas": deltas,
    }


# ---------------------------------------------------------------------------
# Gate calibration sweeps
# ---------------------------------------------------------------------------

def distil_gate(source: SourceRead) -> dict[str, Any]:
    sweeps = []
    for record in source.records:
        dataset = record.get("dataset") or {}
        gate = record.get("gate_as_shipped") or {}
        sweeps.append({
            "generated_at": record.get("generated_at"),
            "source": SRC_SWEEP,
            "n_scoreable": dataset.get("n_scoreable"),
            "n_degraded": dataset.get("n_degraded"),
            "base_rate": dataset.get("base_rate"),
            "fp_cost": record.get("fp_cost"),
            "fn_cost": record.get("fn_cost"),
            "gate_as_shipped": {
                k: v for k, v in sorted(gate.items())
                if isinstance(v, (int, float, str, bool, type(None)))
            },
            "warnings": list(record.get("warnings") or []),
        })
    sweeps.sort(key=lambda s: str(s.get("generated_at") or ""))
    return {"n_sweeps": len(sweeps), "sweeps": sweeps}


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def build(root: Path | str = EVAL_DIR) -> dict[str, Any]:
    root = Path(root)
    reads = {rel: read_jsonl(root, rel) for rel in SOURCES}
    return {
        "schema_version": SCHEMA_VERSION,
        "sources": [reads[rel].to_dict() for rel in SOURCES],
        "retrieval": distil_retrieval(reads[SRC_RETRIEVAL]),
        "node_eval": distil_node_eval(reads[SRC_NODE_EVAL]),
        "spans": distil_spans(root),
        "ingest": distil_ingest(reads[SRC_INGEST]),
        "draft_eval_history": distil_history(reads[SRC_HISTORY], "draft eval"),
        "openreview_history": distil_history(reads[SRC_OPENREVIEW], "OpenReview eval"),
        "gate_calibration": distil_gate(reads[SRC_SWEEP]),
    }


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------

_HEADER = """# Benchmarks

Every measurement this project has produced, distilled from the append-only
sinks under `scripts/eval/`. Generated by `scripts/eval/benchmarks.py`
(`make benchmarks`) -- **do not hand-edit**; regenerate instead.

Most of the sinks are gitignored (they are large and regenerable). This file
and `benchmarks.json` are the tracked, durable record: they are what survives a
fresh clone. There is no generation timestamp anywhere in either file on
purpose, so identical inputs produce byte-identical output and a rerun that
changed nothing shows an empty diff.

House rules, applied throughout:

- no metric appears without its `n`;
- runs marked `valid: false` are excluded from every headline and listed
  separately with the reason;
- `recall@k` is reported against its construction ceiling, or explicitly as
  `unknown` when no ceiling is recorded for that labels/queries fingerprint;
- a cost with any unpriced call renders as a lower bound (`$0.0000 >=`);
- every row carries the file and `run_id` it came from;
- trends are drawn only between runs sharing a config hash. Different hashes
  are different measurements and are never differenced.
"""


def _render_sources(data: dict) -> list[str]:
    rows = []
    for entry in data["sources"]:
        if entry["present"]:
            state = "present"
        else:
            state = "absent"
        skipped = str(entry["skipped_lines"])
        if entry["skip_reasons"]:
            first = entry["skip_reasons"][0]
            skipped += f" (line {first['line']}: {first['reason'][:60]})"
        rows.append([
            f"`{entry['path']}`",
            state,
            str(entry["lines"]),
            str(entry["records"]),
            skipped,
        ])
    return ["## Sources", "",
            "Absent sources are normal: four of these are gitignored and only",
            "exist on a machine that has run the harness. Skipped lines are",
            "counted, never dropped silently -- a truncated final line from an",
            "interrupted write shows up here.", ""] + _table(
        ["file", "state", "lines", "records", "skipped"], rows) + [""]


def _render_retrieval(block: dict) -> list[str]:
    out = ["## Retrieval", ""]
    if not block["n_runs"]:
        out += ["_No retrieval runs recorded._", ""]
        return out
    out += [
        f"{block['n_valid']} valid run(s), {block['n_invalidated']} invalidated, "
        f"across {len(block['config_hashes'])} config hash(es).",
        "",
        "### Headline — latest valid run per config",
        "",
    ]
    for run in block["headline"]:
        out += [
            f"**{run.get('retriever')}** · config `{run.get('config_hash')}` · "
            f"run `{run.get('run_id')}` · {_date(run.get('timestamp'))} · "
            f"`{run.get('source')}`",
            "",
            f"- relevance unit: {run.get('relevance_unit')}, k={run.get('k')}, "
            f"graded={run.get('graded')}, chunk oversample x{run.get('chunk_oversample')}",
            f"- queries scored: {run.get('n_queries_scored')} of {run.get('n_queries')} built; "
            f"relevant documents pooled: {run.get('n_relevant_total')}",
            f"- corpus: {run['corpus'].get('pooled_corpus_size')} documents across "
            f"{run['corpus'].get('n_topics')} topics "
            f"({run['corpus'].get('n_topics_with_labels')} with labels)",
            f"- ceiling source: {run.get('ceiling_provenance')}",
            "",
        ]
        rows = []
        for row in run["metrics"]:
            ceiling = row.get("ceiling")
            pct = row.get("pct_of_attainable")
            if not row.get("ceiling_applicable"):
                ceiling_cell = "n/a (not capped by label design)"
                pct_cell = "n/a"
            elif ceiling is None:
                ceiling_cell = "unknown"
                pct_cell = "unknown"
            else:
                ceiling_cell = _num(ceiling)
                pct_cell = f"{pct * 100:.0f}%" if pct is not None else "unknown"
            rows.append([
                f"`{row['metric']}`",
                _metric(row["value"], row["n_queries"]),
                ceiling_cell,
                pct_cell,
            ])
        out += _table(["metric", "measured (n = queries scored)", "ceiling", "% of attainable"], rows)
        out += [""]
        failure = run.get("failure_breakdown") or {}
        if failure:
            out += [
                "Miss attribution (rollup of the per-query `misses` payload, which "
                "is not tracked):",
                "",
            ]
            out += _table(
                ["cause", "count"],
                [[f"`{k}`", str(failure[k])] for k in sorted(failure)],
            )
            out += [""]
        health = run.get("retrieval_health") or {}
        if health:
            out += _table(
                ["retrieval health", "value"],
                [[f"`{k}`", str(health[k])] for k in sorted(health)],
            )
            out += [""]

    out += ["### Invalidated runs — excluded from every number above", ""]
    if not block["invalidated"]:
        out += ["_None. Every recorded run passed its validity check._", ""]
    else:
        rows = []
        for run in block["invalidated"]:
            rows.append([
                f"`{run.get('run_id')}`",
                _date(run.get("timestamp")),
                str(run.get("retriever")),
                f"`{run.get('config_hash')}`",
                run.get("invalidation_reason", "unknown"),
            ])
        out += _table(["run_id", "date", "retriever", "config", "reason"], rows) + [""]

    out += ["### Trend — same config hash only", ""]
    if not block["deltas"]:
        out += [
            "_No config hash has more than one valid run yet, so there is nothing "
            "to compare. Runs under different hashes are different measurements "
            "and are deliberately not differenced._",
            "",
        ]
    else:
        for delta in block["deltas"]:
            out += [
                f"**{delta.get('retriever')}** · config `{delta['config_hash']}` · "
                f"{delta['runs']} runs · "
                f"`{delta.get('first_run_id')}` ({_date(delta.get('first_timestamp'))}) "
                f"-> `{delta.get('last_run_id')}` ({_date(delta.get('last_timestamp'))})",
                "",
            ]
            rows = [
                [
                    f"`{row['metric']}`",
                    _metric(row["first"], row["n_queries"]),
                    _metric(row["last"], row["n_queries"]),
                    _delta(row["last"], row["first"]),
                ]
                for row in delta["metrics"]
            ]
            out += _table(["metric", "first", "latest", "delta"], rows) + [""]
    return out


def _render_node_eval(block: dict) -> list[str]:
    out = ["## Node replay — `node_eval.jsonl`", ""]
    if not block["n_run_summaries"] and not block["n_replays"]:
        out += ["_No node replays recorded._", ""]
        return out
    out += [
        f"{block['n_run_summaries']} run summar(ies), {block['n_replays']} replay record(s).",
        "",
        "### Runs",
        "",
    ]
    rows = []
    for run in block["runs"]:
        rows.append([
            f"`{run.get('run_id')}`",
            _date(run.get("timestamp")),
            ", ".join(run.get("nodes_requested") or []) or "unknown",
            str(len(run.get("papers") or [])),
            f"{run.get('completed_replays')}/{run.get('attempted_replays')}",
            str(run.get("total_llm_calls")),
            _usd(run.get("total_estimated_usd"), run.get("unpriced_calls") or 0),
        ])
    out += _table(
        ["run_id", "date", "nodes", "papers", "completed/attempted", "llm calls", "estimated cost"],
        rows,
    ) + [""]

    out += ["### Per node, across all replays", "",
            "Latency is `wall_seconds` off each replay record; `n` is the replay count.",
            ""]
    rows = []
    for entry in block["per_node"]:
        rows.append([
            f"`{entry['node']}`",
            str(entry["replays"]),
            f"{entry['ok']} ok / {entry['failed']} failed",
            _metric(entry["wall_seconds_mean"], entry["wall_seconds_n"], places=3),
            _num(entry["wall_seconds_min"], 3),
            _num(entry["wall_seconds_max"], 3),
            str(entry["llm_calls"]),
            _usd(entry["estimated_usd"], entry["unpriced_calls"]),
        ])
    out += _table(
        ["node", "replays", "status", "mean wall s (n = replays)", "min s", "max s", "llm calls", "cost"],
        rows,
    ) + [""]

    out += ["### Trend — same node/paper/reviewer/repeat config only", ""]
    if not block["deltas"]:
        out += [
            "_No node-eval config has been run twice yet. `node_eval.jsonl` records "
            "no config hash of its own, so comparability is keyed on "
            "(nodes, papers, reviewer_type, repeat, with_metric); runs differing in "
            "any of those are not differenced._",
            "",
        ]
    else:
        rows = []
        for delta in block["deltas"]:
            rows.append([
                f"`{delta['config_key']}`",
                str(delta["runs"]),
                _usd(delta["first_usd"], 1 if delta["cost_is_lower_bound"] else 0),
                _usd(delta["last_usd"], 1 if delta["cost_is_lower_bound"] else 0),
                _delta(delta["last_usd"], delta["first_usd"]),
            ])
        out += _table(["config", "runs", "first cost", "latest cost", "delta"], rows) + [""]
    return out


def _render_spans(block: dict) -> list[str]:
    out = ["## Spans — `node_eval_spans.jsonl`", ""]
    if not block.get("present"):
        out += ["_No span file on disk. Raw spans are not tracked (unbounded "
                "growth); the per-node cost record above is the durable part._", ""]
        return out
    if block.get("error"):
        out += [f"_Could not read spans: {block['error']}_", ""]
        return out
    parse = block["parse"]
    out += [
        f"{block['traces']} trace(s) from {parse['spans_parsed']} span(s) over "
        f"{parse['lines_read']} line(s). "
        f"Skipped: {parse['malformed_lines']} malformed, {parse['blank_lines']} blank, "
        f"{parse['duplicate_span_ids']} duplicate span id(s), "
        f"{parse['orphan_spans']} orphan(s) promoted to roots.",
        "",
        "Parsed with `trace_report.parse` and summarized with "
        "`trace_report.metrics` -- the same code the trace report uses, not a "
        "second parser. Percentiles below are refused, not guessed, when the "
        "sample is too small.",
        "",
    ]
    rows = []
    for node in block["nodes"]:
        wall = node["wall_ms"]
        p50 = wall.get("p50")
        p95 = wall.get("p95")
        rows.append([
            f"`{node['node']}`",
            str(node["executions"]),
            _metric(wall.get("mean"), wall.get("n"), places=1),
            _num(p50, 1) if p50 is not None else f"refused ({wall['refused'].get('p50', 'n/a')})",
            _num(p95, 1) if p95 is not None else f"refused ({wall['refused'].get('p95', 'n/a')})",
            _usd(node["usd"], node["unpriced_spans"]),
        ])
    out += _table(["node", "executions", "mean ms (n)", "p50 ms", "p95 ms", "cost"], rows) + [""]

    tokens = block["tokens"]
    cost = block["cost"]
    if tokens["calls"] == 0 and block["nodes"]:
        out += [
            "**No `llm_call` spans in this file.** Only node-level spans were "
            "exported, so the token and cost totals below are what the span "
            "file contains, not what the run spent -- the node replay section "
            "above is the authority on cost. A zero here means *not recorded*, "
            "not *free*.",
            "",
        ]
    out += _table(
        ["totals", "value"],
        [
            ["llm calls", str(tokens["calls"])],
            ["input tokens", f"{tokens['input_tokens']:,}"],
            ["cached input tokens", f"{tokens['cached_tokens']:,}"],
            ["output tokens", f"{tokens['output_tokens']:,}"],
            ["cache hit rate", _num(tokens["cache_hit_rate"])],
            ["calls without usage", str(tokens["calls_without_usage"])],
            ["cost", _usd(cost["total_usd"], cost["unpriced_spans"])],
        ],
    ) + [""]
    return out


def _render_ingest(block: dict) -> list[str]:
    out = ["## Ingest — `cache/ingest_manifest.jsonl`", ""]
    if not block.get("n_records"):
        out += ["_No ingest manifest on disk. Not tracked: it grows one record "
                "per document per run._", ""]
        return out
    tokens = block["tokens"]
    chunks = block["chunks"]
    out += [
        f"{block['n_records']} manifest record(s) over {block['n_distinct_docs']} "
        f"distinct document(s). Errors: {block['errors']}. "
        f"Cost ceiling applied: {block['cost_ceiling_applied']}.",
        "",
    ]
    out += _table(
        ["dimension", "breakdown"],
        [
            ["action", ", ".join(f"{k}={v}" for k, v in block["actions"].items())],
            ["extractor", ", ".join(f"{k}={v}" for k, v in block["extractors"].items())],
            ["embedding", ", ".join(f"{k}={v}" for k, v in block["embedding_models"].items())],
            ["chunking", ", ".join(f"{k} ({v})" for k, v in block["chunking_configs"].items())],
        ],
    ) + [""]
    out += _table(
        ["quantity", "total", "mean (n)", "min", "max"],
        [
            [
                "tokens",
                f"{tokens['total']:,}" if tokens["total"] is not None else "unknown",
                _metric(tokens["mean"], tokens["n"], places=1),
                _num(tokens["min"]),
                _num(tokens["max"]),
            ],
            [
                "chunks",
                f"{chunks['total']:,}" if chunks["total"] is not None else "unknown",
                _metric(chunks["mean"], chunks["n"], places=1),
                _num(chunks["min"]),
                _num(chunks["max"]),
            ],
        ],
    ) + [""]
    return out


def _render_history(block: dict) -> list[str]:
    out = [f"## {block['label']} scoreboard — `{block['source']}`", ""]
    if not block["n_runs"]:
        out += ["_No runs recorded._", ""]
        return out
    out += [f"{block['n_runs']} run(s) across "
            f"{len(block['pipeline_versions'])} pipeline version(s).", ""]
    rows = []
    for run in block["runs"]:
        rows.append([
            f"`{_short(run.get('run_id'), 12)}`",
            _date(run.get("generated_at")),
            f"`{_short(run.get('pipeline_version'), 12)}`",
            _metric(run.get("mean_overall"), run.get("scored_cells")),
            str(run.get("total_hallucinations")),
            f"{run.get('scored_cells')}/{run.get('total_cells')}",
        ])
    out += _table(
        ["run_id", "date", "pipeline", "mean overall (n = scored cells)", "hallucinations", "scored/total cells"],
        rows,
    ) + [""]

    out += ["### Trend — same pipeline version only", ""]
    if not block["deltas"]:
        out += ["_No pipeline version has more than one run, so nothing is "
                "comparable yet._", ""]
    else:
        rows = []
        for delta in block["deltas"]:
            rows.append([
                f"`{_short(delta['pipeline_version'], 12)}`",
                str(delta["runs"]),
                _metric(delta["first_mean_overall"], delta["n_scored_cells"]),
                _metric(delta["last_mean_overall"], delta["n_scored_cells"]),
                _delta(delta["last_mean_overall"], delta["first_mean_overall"]),
                f"{delta['first_hallucinations']} -> {delta['last_hallucinations']}",
            ])
        out += _table(
            ["pipeline", "runs", "first", "latest", "delta", "hallucinations"],
            rows,
        ) + [""]
    return out


def _render_gate(block: dict) -> list[str]:
    out = ["## Gate calibration — `gate_calibration/sweep_results.jsonl`", ""]
    if not block["n_sweeps"]:
        out += [
            "_No sweeps recorded. The sweep needs human labels and none exist "
            "yet, so there is no calibration number to report -- not a zero, an "
            "absence._",
            "",
        ]
        return out
    rows = []
    for sweep in block["sweeps"]:
        rows.append([
            _date(sweep.get("generated_at")),
            _metric(sweep.get("base_rate"), sweep.get("n_scoreable")),
            str(sweep.get("n_degraded")),
            f"fp={sweep.get('fp_cost')} fn={sweep.get('fn_cost')}",
            "; ".join(sweep.get("warnings") or []) or "none",
        ])
    out += _table(
        ["date", "base rate (n = scoreable)", "degraded", "costs", "warnings"],
        rows,
    ) + [""]
    return out


def render(data: dict) -> str:
    parts: list[str] = [_HEADER]
    parts.append("\n".join(_render_sources(data)))
    parts.append("\n".join(_render_retrieval(data["retrieval"])))
    parts.append("\n".join(_render_node_eval(data["node_eval"])))
    parts.append("\n".join(_render_spans(data["spans"])))
    parts.append("\n".join(_render_ingest(data["ingest"])))
    parts.append("\n".join(_render_history(data["draft_eval_history"])))
    parts.append("\n".join(_render_history(data["openreview_history"])))
    parts.append("\n".join(_render_gate(data["gate_calibration"])))
    body = "\n".join(p.rstrip() + "\n" for p in parts if p.strip())
    return body if body.endswith("\n") else body + "\n"


def render_json(data: dict) -> str:
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--root", type=Path, default=EVAL_DIR,
                        help="directory holding results/ and cache/ (default: scripts/eval)")
    parser.add_argument("--md", type=Path, default=MD_PATH)
    parser.add_argument("--json", dest="json_path", type=Path, default=JSON_PATH)
    parser.add_argument("--stdout", action="store_true", help="print the board; write nothing")
    parser.add_argument("--check", action="store_true",
                        help="exit 1 if the tracked outputs are stale")
    args = parser.parse_args(argv)

    data = build(args.root)
    markdown = render(data)
    payload = render_json(data)

    if args.stdout:
        sys.stdout.write(markdown)
        return 0

    if args.check:
        stale = []
        for path, expected in ((args.md, markdown), (args.json_path, payload)):
            actual = path.read_text(encoding="utf-8") if path.exists() else None
            if actual != expected:
                stale.append(str(path))
        if stale:
            sys.stderr.write("[benchmarks] stale: " + ", ".join(stale) + "\n")
            sys.stderr.write("[benchmarks] run `make benchmarks`\n")
            return 1
        print("[benchmarks] up to date")
        return 0

    args.md.write_text(markdown, encoding="utf-8")
    args.json_path.write_text(payload, encoding="utf-8")
    print(f"[benchmarks] wrote {args.md}")
    print(f"[benchmarks] wrote {args.json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

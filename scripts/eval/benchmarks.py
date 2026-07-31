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
#: 2 -- added the ANN sweep block, the consolidated cost block, and label
#: snapshot grouping on the retrieval block.
SCHEMA_VERSION = 2

# Source paths, relative to scripts/eval/. Every one may be absent on a fresh
# clone -- four of the five are gitignored, which is why this file exists.
SRC_RETRIEVAL = "results/retrieval_eval.jsonl"
SRC_NODE_EVAL = "results/node_eval.jsonl"
SRC_SPANS = "results/node_eval_spans.jsonl"
SRC_INGEST = "cache/ingest_manifest.jsonl"
SRC_HISTORY = "results/history.jsonl"
SRC_OPENREVIEW = "results/openreview_history.jsonl"
SRC_SWEEP = "gate_calibration/sweep_results.jsonl"
SRC_ANN = "results/ann_sweep.jsonl"

SOURCES = (
    SRC_RETRIEVAL,
    SRC_NODE_EVAL,
    SRC_SPANS,
    SRC_INGEST,
    SRC_HISTORY,
    SRC_OPENREVIEW,
    SRC_SWEEP,
    SRC_ANN,
)

# ---------------------------------------------------------------------------
# Cost
# ---------------------------------------------------------------------------
# Stated once, at the top of the cost section, because it applies to every cost
# figure this repo has ever produced and no per-record flag encodes it:
# ``match.py`` issued OpenAI calls outside the spend guardrails until recently,
# so those calls were never metered into any sink. Nothing below can see them.
COST_LOWER_BOUND_REASON = (
    "`match.py` bypassed the spend guardrails until recently, so its OpenAI "
    "calls were never recorded in any sink. Every cost figure in this project "
    "is therefore a lower bound -- including the ones whose own "
    "`unpriced_calls` counter reads zero."
)

# ---------------------------------------------------------------------------
# Recall ceilings
# ---------------------------------------------------------------------------
# recall@k is capped by the label design, not by the retriever. The ceiling is
# a property of (labels, queries, corpus), so it is keyed by the fingerprints
# the harness already stamps on every record AND by the corpus size the run
# reports. If any of the three changes, the ceiling for that pair is unknown and
# the board says "unknown" -- an out-of-date ceiling would be worse than none,
# because it makes a retriever look better or worse than it is.
#
# The corpus size is part of the key and not decoration. This corpus grew from
# 118 documents / 4 topics to 344 / 15 mid-project and the label fingerprint
# changed twice with it. recall@10 = 0.4221 (BASELINE.md, labels
# 019bee4a06eb2d39), 0.3488 (ANN sweep, labels 425df789a844f1f3) and whatever a
# 15-topic run produces are three different quantities. Applying one snapshot's
# ceiling to another's measurement is the single easiest way to publish a wrong
# "% of attainable", so it is structurally prevented here.
#
# Provenance: measured in scripts/eval/retrieval/BASELINE.md §"recall@k is
# capped well below 1.0 by construction", query-count weighted, over the
# 59-query / 118-document local corpus.
KNOWN_RECALL_CEILINGS: dict[tuple[str, str], dict[str, Any]] = {
    ("019bee4a06eb2d39", "1f6c584e8fd6c055"): {
        "corpus_documents": 118,
        "source": "retrieval/BASELINE.md",
        "ceilings": {1: 0.1061, 5: 0.5307, 10: 0.7789, 20: 0.8798},
    },
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

def _corpus_documents(record: dict) -> Any:
    return (record.get("resolution_report") or {}).get("pooled_corpus_size")


def _snapshot(record: dict) -> dict[str, Any]:
    """The (labels, queries, corpus) triple a retrieval number belongs to.

    Two runs sharing this triple measured the same target. Two that do not are
    not comparable *at all* -- not "roughly", not "close enough". The board
    groups on it and says so above every table, because the failure mode is a
    reader skimming one table, quoting 0.4221, and setting it beside 0.3488
    from another as though the retriever had got worse.
    """
    config = record.get("config") or {}
    labels = config.get("labels_fingerprint")
    queries = config.get("queries_fingerprint")
    documents = _corpus_documents(record)
    report = record.get("resolution_report") or {}
    return {
        "key": f"labels={labels or 'unknown'} queries={queries or 'unknown'} "
               f"corpus={documents if documents is not None else 'unknown'}docs",
        "labels_fingerprint": labels,
        "queries_fingerprint": queries,
        "corpus_documents": documents,
        "n_topics": report.get("n_topics"),
        "n_topics_with_labels": report.get("n_topics_with_labels"),
    }


def _ceiling_for(record: dict) -> tuple[dict[int, float] | None, str]:
    """(ceilings by k, provenance). ``None`` means unknown -- say so. Rule 3.

    A ceiling carried on the record itself always wins: if the harness ever
    starts computing it per-run, that number is authoritative and this table
    should stop being consulted.

    A ceiling from the table is only applied when the labels fingerprint, the
    queries fingerprint *and* the corpus size all match the snapshot it was
    measured on. A mismatch on any of the three returns ``None`` with the
    mismatch named, never a near-miss ceiling.
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
    entry = KNOWN_RECALL_CEILINGS.get(key)
    if entry is None:
        return None, "unknown (no ceiling recorded for this labels/queries fingerprint)"
    measured_on = entry.get("corpus_documents")
    documents = _corpus_documents(record)
    if measured_on is not None and documents is not None and int(documents) != int(measured_on):
        return None, (
            f"unknown (ceiling was measured on a {measured_on}-document label "
            f"snapshot; this run reports {documents} documents -- a ceiling is "
            f"never carried across snapshots)"
        )
    return (
        entry["ceilings"],
        f"{entry['source']} (labels+queries fingerprint and "
        f"{measured_on}-document corpus all match)",
    )


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
            "snapshot": _snapshot(record),
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

    # Headline = latest valid run per (config hash, label snapshot). Rule 6:
    # grouping is by hash, so two different configs can never be differenced
    # against each other; the snapshot is in the key as well, so that a config
    # hash that somehow survived a corpus change still cannot be differenced
    # across the change.
    groups: dict[tuple[str, str], list[dict]] = {}
    for run in valid:
        groups.setdefault((str(run.get("config_hash")), run["snapshot"]["key"]), []).append(run)
    for runs in groups.values():
        runs.sort(key=lambda r: (str(r.get("timestamp") or ""), str(r.get("run_id") or "")))

    headline = [runs[-1] for _, runs in sorted(groups.items())]
    deltas = []
    for (config_hash, snapshot_key), runs in sorted(groups.items()):
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
            "snapshot_key": snapshot_key,
            "retriever": last.get("retriever"),
            "runs": len(runs),
            "first_run_id": first.get("run_id"),
            "first_timestamp": first.get("timestamp"),
            "last_run_id": last.get("run_id"),
            "last_timestamp": last.get("timestamp"),
            "metrics": rows,
        })

    # Snapshot roll-up. Every run -- valid or not -- is counted here, because a
    # reader needs to see that more than one label snapshot exists at all before
    # they are told which numbers may sit beside which.
    snapshots: dict[str, dict[str, Any]] = {}
    for run in valid + invalidated:
        snap = run["snapshot"]
        bucket = snapshots.setdefault(snap["key"], {
            **snap,
            "n_runs": 0,
            "n_valid": 0,
            "n_invalidated": 0,
            "config_hashes": set(),
            "retrievers": set(),
            "ceiling_known": False,
        })
        bucket["n_runs"] += 1
        bucket["config_hashes"].add(str(run.get("config_hash")))
        bucket["retrievers"].add(str(run.get("retriever")))
    for run in valid:
        snapshots[run["snapshot"]["key"]]["n_valid"] += 1
        if not str(run.get("ceiling_provenance", "")).startswith("unknown"):
            snapshots[run["snapshot"]["key"]]["ceiling_known"] = True
    for run in invalidated:
        snapshots[run["snapshot"]["key"]]["n_invalidated"] += 1
    snapshot_rows = []
    for key in sorted(snapshots):
        bucket = dict(snapshots[key])
        bucket["config_hashes"] = sorted(bucket["config_hashes"])
        bucket["retrievers"] = sorted(bucket["retrievers"])
        snapshot_rows.append(bucket)

    return {
        "headline": headline,
        "invalidated": invalidated,
        "deltas": deltas,
        "n_runs": len(source.records),
        "n_valid": len(valid),
        "n_invalidated": len(invalidated),
        "config_hashes": sorted({config_hash for config_hash, _ in groups}),
        "snapshots": snapshot_rows,
        "n_snapshots": len(snapshot_rows),
        "cross_snapshot_comparison_allowed": False,
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
# ANN / HNSW parameter sweep (results/ann_sweep.jsonl)
# ---------------------------------------------------------------------------
# Two measurement modes exist in this sink and conflating them would be the
# worst thing this file could do:
#
#   planner-free  -- the query as production issues it. Postgres decides. On
#                    this 2124-chunk corpus it declines the HNSW index above a
#                    LIMIT of roughly 30-40 and runs an exact sequential scan,
#                    so a "planner-free" row at k=50 is an exact-scan result
#                    and `ef_search` is inert in it.
#   index-forced  -- `enable_seqscan = off`, every other index dropped inside a
#                    rolled-back transaction. This is the HNSW curve. It is NOT
#                    what production executes at that depth and must never be
#                    quoted as though it were.
#
# Records written before the sweep grew its `index_scan_forced` field carry no
# mode at all. They are excluded from both tables rather than guessed at.
MODE_PLANNER_FREE = "planner_free"
MODE_INDEX_FORCED = "index_forced"
MODE_UNRECORDED = "mode_unrecorded"

MODE_LABELS = {
    MODE_PLANNER_FREE: "planner-free (what production executes)",
    MODE_INDEX_FORCED: "index-forced (property of the index, NOT of production)",
    MODE_UNRECORDED: "mode not recorded",
}

#: The production HNSW index on ``document_chunks.embedding``. Candidate indexes
#: built by the sweep are named ``ann_sweep_hnsw_*``.
ANN_PRODUCTION_INDEX = "idx_document_chunks_embedding"
ANN_CANDIDATE_PREFIX = "ann_sweep_hnsw_"

#: Postgres page size. Used only to explain the flat index-size finding.
PG_PAGE_BYTES = 8192


def _is_vector_index(name: Any) -> bool:
    text = str(name or "")
    return text == ANN_PRODUCTION_INDEX or text.startswith(ANN_CANDIDATE_PREFIX)


def _ann_mode(record: dict) -> str:
    forced = record.get("index_scan_forced")
    if forced is True:
        return MODE_INDEX_FORCED
    if forced is False:
        return MODE_PLANNER_FREE
    return MODE_UNRECORDED


def _ann_point_id(record: dict) -> str:
    """Stable identity for "the same sweep point".

    This sink writes no ``run_id`` -- it is keyed by parameters plus corpus
    fingerprint, one record per configuration, appended forever. So provenance
    (rule 5) is the file plus this derived point id, and the board says as much
    rather than printing a blank run_id column.
    """
    params = record.get("params") or {}
    kind = str(record.get("record_type"))
    bits = [kind, _ann_mode(record)]
    for name in ("k", "ef_search", "m", "ef_construction"):
        if params.get(name) is not None:
            bits.append(f"{name}={params[name]}")
    if kind == "planner_choice":
        bits.append("k_values=" + ",".join(str(v) for v in (params.get("k_values") or [])))
    return "/".join(bits)


def _ann_latency(record: dict) -> dict[str, Any]:
    server = record.get("latency_server_ms") or {}
    client = record.get("latency_client_ms") or {}
    return {
        "server_p50_ms": server.get("p50_ms"),
        "server_p95_ms": server.get("p95_ms"),
        "client_p50_ms": client.get("p50_ms"),
        "n_samples": server.get("n_samples"),
        "n_queries": server.get("n_queries"),
        "clock": server.get("clock"),
        "percentile_method": server.get("percentile_method"),
    }


def _ann_row(record: dict) -> dict[str, Any]:
    params = record.get("params") or {}
    ann = record.get("ann_recall_vs_exact") or {}
    labels = record.get("metrics_vs_labels") or {}
    label_metrics = labels.get("metrics") or {}
    index_used = record.get("plan_index_used")
    row = {
        "point_id": _ann_point_id(record),
        "source": SRC_ANN,
        "run_id": None,  # this sink records none; point_id is the identity
        "record_type": record.get("record_type"),
        "timestamp": record.get("timestamp"),
        "sweep_version": record.get("sweep_version"),
        "mode": _ann_mode(record),
        "mode_label": MODE_LABELS[_ann_mode(record)],
        "k": params.get("k"),
        "ef_search": params.get("ef_search"),
        "is_production_reference": bool(params.get("is_production_reference")),
        "plan_index_used": index_used,
        "plan": "index scan" if index_used else "seq scan (exact)",
        "n_queries": record.get("n_queries"),
        "ann_recall": {k: ann[k] for k in sorted(ann) if k.startswith(("recall@", "vs_exact@"))},
        "label_metrics": {k: label_metrics[k] for k in sorted(label_metrics)},
        "label_n_queries": labels.get("n_queries_scored", labels.get("n_queries")),
        "label_ceiling": None,
        "label_ceiling_provenance": (
            "unknown (this sink records no labels fingerprint, so the ceiling "
            "for its label snapshot cannot be identified -- and a ceiling from "
            "another snapshot is never substituted)"
        ),
    }
    row.update(_ann_latency(record))
    return row


def _ann_dedupe(rows: Sequence[dict]) -> tuple[list[dict], list[dict]]:
    """Latest record per point wins; the earlier ones are named, not dropped."""
    latest: dict[str, dict] = {}
    for row in rows:
        key = row["point_id"]
        prior = latest.get(key)
        if prior is None or str(row.get("timestamp") or "") >= str(prior.get("timestamp") or ""):
            latest[key] = row
    kept, superseded = [], []
    for row in rows:
        if latest.get(row["point_id"]) is row:
            kept.append(row)
        else:
            superseded.append(dict(row, exclusion_reason=(
                "superseded by a later measurement of the same sweep point "
                f"({_date(latest[row['point_id']].get('timestamp'))})"
            )))
    return kept, superseded


def distil_ann(source: SourceRead) -> dict[str, Any]:
    if not source.records:
        return {"present": False, "n_records": 0, "source": SRC_ANN}

    corpora: dict[str, dict[str, Any]] = {}
    for record in source.records:
        fingerprint = record.get("corpus_fingerprint") or {}
        key = f"{fingerprint.get('documents')}docs/{fingerprint.get('chunks')}chunks"
        corpora.setdefault(key, {
            "documents": fingerprint.get("documents"),
            "chunks": fingerprint.get("chunks"),
            "project_id": fingerprint.get("project_id"),
            "n_records": 0,
        })["n_records"] += 1
    corpus_rows = [corpora[k] for k in sorted(corpora)]

    excluded: list[dict[str, Any]] = []
    ef_rows: list[dict] = []
    exact_rows: list[dict] = []
    build_rows: list[dict] = []
    planner_rows: list[dict] = []

    for record in source.records:
        kind = record.get("record_type")
        status = record.get("status")
        row = _ann_row(record)

        if status != "ok":
            excluded.append(dict(row, exclusion_reason=(
                f"status={status}: {record.get('error') or 'no error recorded'}"
            )))
            continue

        if kind == "planner_choice":
            planner_rows.append(dict(row, choices=[
                {"k": entry.get("k"), "index_used": entry.get("index_used")}
                for entry in (record.get("planner_choice_by_k") or [])
            ]))
            continue

        if kind == "build":
            build = record.get("build") or {}
            if not _is_vector_index(record.get("plan_index_used")) or \
                    record.get("plan_index_used") != build.get("index_name"):
                excluded.append(dict(row, exclusion_reason=(
                    f"build candidate '{build.get('index_name')}' was measured with the "
                    f"planner on '{record.get('plan_index_used')}' -- the point would be "
                    "mislabelled"
                )))
                continue
            build_rows.append(dict(row, **{
                "m": build.get("m"),
                "ef_construction": build.get("ef_construction"),
                "index_name": build.get("index_name"),
                "build_seconds": build.get("build_seconds"),
                "index_bytes": build.get("index_bytes"),
                "index_size_pretty": build.get("index_size_pretty"),
            }))
            continue

        if row["mode"] == MODE_UNRECORDED:
            excluded.append(dict(row, exclusion_reason=(
                "the sweep run predates the `index_scan_forced` field, so it is "
                "unknown whether the planner was free or the index was forced. "
                "Never guessed: an index-forced number presented as planner-free "
                "would be a claim about production that was not measured"
            )))
            continue

        if row["mode"] == MODE_INDEX_FORCED and not _is_vector_index(row["plan_index_used"]):
            excluded.append(dict(row, exclusion_reason=(
                f"'index forced' landed on '{row['plan_index_used']}', which is not "
                "an HNSW vector index -- the run measured a full scan of the wrong "
                "index and its ANN recall of 1.0 is an artefact, not a result"
            )))
            continue

        (exact_rows if kind == "exact" else ef_rows).append(row)

    ef_rows, ef_superseded = _ann_dedupe(ef_rows)
    exact_kept, exact_superseded = _ann_dedupe(exact_rows)
    build_rows, build_superseded = _ann_dedupe(build_rows)
    planner_rows, planner_superseded = _ann_dedupe(planner_rows)
    excluded += ef_superseded + build_superseded + planner_superseded

    ef_rows.sort(key=lambda r: (r["k"] or 0, r["mode"], r["ef_search"] or 0))
    build_rows.sort(key=lambda r: (r["m"] or 0, r["ef_construction"] or 0))
    planner_rows.sort(key=lambda r: str(r.get("timestamp") or ""))

    # Exact search is the recall ceiling for ANN recall (and only for that --
    # its *label* recall is capped by the label design like everything else).
    # Its repeats across runs are the machine-noise measurement, so they are
    # summarised before deduplication, not after.
    #
    # Every ok `exact` record counts here, including ones whose mode field is
    # missing: an exact scan is an exact scan (the harness refuses to record an
    # "exact" point whose plan used an index), so all repeats of it are repeats
    # of the same measurement. Mode only decides what the *ef_search* rows mean.
    noise: list[dict[str, Any]] = []
    by_k: dict[Any, list[float]] = {}
    for record in source.records:
        if record.get("record_type") != "exact" or record.get("status") != "ok":
            continue
        p50 = (record.get("latency_server_ms") or {}).get("p50_ms")
        if isinstance(p50, (int, float)):
            by_k.setdefault((record.get("params") or {}).get("k"), []).append(float(p50))
    for k in sorted(by_k, key=lambda v: (v is None, v)):
        values = sorted(by_k[k])
        mean = sum(values) / len(values)
        noise.append({
            "k": k,
            "n_runs": len(values),
            "p50_ms_min": values[0],
            "p50_ms_max": values[-1],
            "p50_ms_mean": mean,
            "spread_pct_of_mean": ((values[-1] - values[0]) / mean * 100.0) if mean else None,
            "plus_minus_pct": ((values[-1] - values[0]) / (2 * mean) * 100.0) if mean else None,
        })
    exact_kept.sort(key=lambda r: (r["k"] or 0,))

    # Finding: the planner declines the index above some LIMIT. Read off the
    # probes rather than asserted.
    highest_index_k: int | None = None
    lowest_seq_k: int | None = None
    for row in planner_rows:
        for choice in row["choices"]:
            k = choice.get("k")
            if k is None:
                continue
            if choice.get("index_used"):
                highest_index_k = k if highest_index_k is None else max(highest_index_k, k)
            else:
                lowest_seq_k = k if lowest_seq_k is None else min(lowest_seq_k, k)

    # Finding: raising ef_search past the production value flips the plan and
    # costs latency. Computed against the production reference row, per k, in
    # planner-free mode only -- the forced curve cannot show a plan flip.
    plan_flip: list[dict[str, Any]] = []
    for k in sorted({r["k"] for r in ef_rows if r["k"] is not None}):
        free = [r for r in ef_rows if r["k"] == k and r["mode"] == MODE_PLANNER_FREE]
        reference = next((r for r in free if r["is_production_reference"]), None)
        if reference is None or not isinstance(reference.get("server_p50_ms"), (int, float)):
            continue
        if not reference["plan_index_used"]:
            # Nothing to flip: the planner had already declined the index at the
            # production ef_search, so a slower row above it is not a plan flip.
            continue
        flipped = [
            r for r in free
            if (r["ef_search"] or 0) > (reference["ef_search"] or 0)
            and not r["plan_index_used"]
            and isinstance(r.get("server_p50_ms"), (int, float))
        ]
        if not flipped:
            continue
        worst = max(flipped, key=lambda r: r["server_p50_ms"])
        plan_flip.append({
            "k": k,
            "reference_ef_search": reference["ef_search"],
            "reference_p50_ms": reference["server_p50_ms"],
            "reference_plan": reference["plan"],
            "flipped_ef_search": worst["ef_search"],
            "flipped_p50_ms": worst["server_p50_ms"],
            "slowdown_x": worst["server_p50_ms"] / reference["server_p50_ms"],
            "n_samples": reference["n_samples"],
        })

    # Finding: index size does not move with m.
    sizes = sorted({r["index_bytes"] for r in build_rows if r.get("index_bytes") is not None})
    index_size = {
        "distinct_byte_values": sizes,
        "identical_at_every_point": len(sizes) == 1,
        "bytes": sizes[0] if len(sizes) == 1 else None,
        "pages": (sizes[0] // PG_PAGE_BYTES) if len(sizes) == 1 else None,
        "m_values": sorted({r["m"] for r in build_rows if r.get("m") is not None}),
        "n_points": len(build_rows),
    }
    builds = [r["build_seconds"] for r in build_rows if isinstance(r.get("build_seconds"), (int, float))]
    build_time = {
        "n_points": len(builds),
        "min_seconds": min(builds) if builds else None,
        "max_seconds": max(builds) if builds else None,
        "span_x": (max(builds) / min(builds)) if builds and min(builds) else None,
    }

    return {
        "present": True,
        "source": SRC_ANN,
        "n_records": len(source.records),
        "sweep_versions": sorted({str(r.get("sweep_version")) for r in source.records}),
        "corpora": corpus_rows,
        "modes": MODE_LABELS,
        "ef_search": ef_rows,
        "exact": exact_kept,
        "exact_repeat_noise": noise,
        "build_grid": build_rows,
        "index_size": index_size,
        "build_time": build_time,
        "planner_choice": planner_rows,
        "planner_crossover": {
            "highest_k_using_index": highest_index_k,
            "lowest_k_declining_index": lowest_seq_k,
            "n_probes": len(planner_rows),
        },
        "plan_flip": plan_flip,
        "excluded": sorted(excluded, key=lambda r: (r["point_id"], str(r.get("timestamp") or ""))),
        "n_excluded": len(excluded),
        "label_ceiling_known": False,
    }


# ---------------------------------------------------------------------------
# Cost -- consolidated, and always a lower bound
# ---------------------------------------------------------------------------

def distil_cost(node_eval: dict, spans: dict) -> dict[str, Any]:
    sinks: list[dict[str, Any]] = []

    run_usd = sum(
        float(r["total_estimated_usd"]) for r in node_eval["runs"]
        if isinstance(r.get("total_estimated_usd"), (int, float))
    )
    run_unpriced = sum(int(r.get("unpriced_calls") or 0) for r in node_eval["runs"])
    if node_eval["runs"]:
        sinks.append({
            "sink": SRC_NODE_EVAL,
            "scope": "run summaries",
            "n": len(node_eval["runs"]),
            "usd": run_usd,
            "unpriced_calls": run_unpriced,
        })

    replay_usd = sum(float(e.get("estimated_usd") or 0.0) for e in node_eval["per_node"])
    replay_unpriced = sum(int(e.get("unpriced_calls") or 0) for e in node_eval["per_node"])
    if node_eval["per_node"]:
        sinks.append({
            "sink": SRC_NODE_EVAL,
            "scope": "replay records, per node",
            "n": node_eval["n_replays"],
            "usd": replay_usd,
            "unpriced_calls": replay_unpriced,
        })

    span_cost = spans.get("cost") or {}
    if spans.get("present") and not spans.get("error"):
        sinks.append({
            "sink": SRC_SPANS,
            "scope": "raw spans",
            "n": span_cost.get("runs"),
            "usd": span_cost.get("total_usd"),
            "unpriced_calls": span_cost.get("unpriced_spans") or 0,
        })

    unpriced = sum(int(s.get("unpriced_calls") or 0) for s in sinks)
    return {
        "sinks": sinks,
        "unpriced_calls": unpriced,
        "any_unpriced_calls": unpriced > 0,
        # Not conditional on the counter. See COST_LOWER_BOUND_REASON: the
        # unrecorded match.py spend is invisible to every counter here.
        "all_costs_are_lower_bounds": True,
        "lower_bound_reason": COST_LOWER_BOUND_REASON,
        # There is deliberately no grand total: the sinks overlap (a replay's
        # cost is also inside its run summary) and adding them would double
        # count. Overlapping lower bounds do not sum into a better one.
        "grand_total_usd": None,
        "grand_total_note": "not computed -- the sinks overlap and would double count",
    }


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def build(root: Path | str = EVAL_DIR) -> dict[str, Any]:
    root = Path(root)
    reads = {rel: read_jsonl(root, rel) for rel in SOURCES}
    node_eval = distil_node_eval(reads[SRC_NODE_EVAL])
    spans = distil_spans(root)
    return {
        "schema_version": SCHEMA_VERSION,
        "sources": [reads[rel].to_dict() for rel in SOURCES],
        "cost": distil_cost(node_eval, spans),
        "retrieval": distil_retrieval(reads[SRC_RETRIEVAL]),
        "ann_sweep": distil_ann(reads[SRC_ANN]),
        "node_eval": node_eval,
        "spans": spans,
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
  `unknown` when no ceiling is recorded for that labels/queries fingerprint.
  The ceiling moves with the corpus, so one label snapshot's ceiling is never
  applied to another's measurement;
- **every cost figure in this project is a lower bound** -- see the cost
  section below for why; a cost with any unpriced call additionally renders as
  `$0.0000 >=`;
- every row carries the file and `run_id` it came from (or, where a sink
  records no run_id, the derived point identity and a note saying so);
- trends are drawn only between runs sharing a config hash. Different hashes
  are different measurements and are never differenced;
- retrieval numbers are grouped by label snapshot and **numbers from different
  snapshots are not comparable at all**.
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
        f"across {len(block['config_hashes'])} config hash(es) and "
        f"{block['n_snapshots']} label snapshot(s).",
        "",
        "> **Read this before quoting any number below.**",
        "> Every retrieval metric here is measured against a *label snapshot* —",
        "> a particular labels fingerprint, queries fingerprint and corpus size.",
        "> This corpus grew from 118 documents / 4 topics to 344 / 15 mid-project",
        "> and the label fingerprint changed twice with it. **Numbers from two",
        "> different snapshots are not comparable.** `recall@10 = 0.4221` and",
        "> `recall@10 = 0.3488` are not a regression; they are two different",
        "> questions. Each table below is scoped to one snapshot and says which.",
        "",
        "### Label snapshots present",
        "",
    ]
    snap_rows = []
    for snap in block["snapshots"]:
        snap_rows.append([
            f"`{_short(snap.get('labels_fingerprint'), 16)}`",
            f"`{_short(snap.get('queries_fingerprint'), 16)}`",
            str(snap.get("corpus_documents")),
            str(snap.get("n_topics")),
            f"{snap.get('n_valid')} valid / {snap.get('n_invalidated')} invalid",
            ", ".join(snap.get("retrievers") or []) or "unknown",
            "yes" if snap.get("ceiling_known") else "no",
        ])
    out += _table(
        ["labels fp", "queries fp", "corpus docs", "topics", "runs", "retrievers",
         "recall ceiling known"],
        snap_rows,
    ) + [""]
    if block["n_snapshots"] > 1:
        out += [
            f"**{block['n_snapshots']} snapshots are present in this file.** No "
            "delta, ratio or comparison is drawn across them anywhere in this "
            "document, and none should be drawn by hand either.",
            "",
        ]

    out += ["### Headline — latest valid run per config, grouped by label snapshot", ""]
    by_snapshot: dict[str, list[dict]] = {}
    for run in block["headline"]:
        by_snapshot.setdefault(run["snapshot"]["key"], []).append(run)
    for snapshot_key in sorted(by_snapshot):
        group = by_snapshot[snapshot_key]
        snap = group[0]["snapshot"]
        out += [
            f"#### Snapshot `{snapshot_key}`",
            "",
            f"{snap.get('corpus_documents')} documents across {snap.get('n_topics')} "
            f"topics ({snap.get('n_topics_with_labels')} with labels). "
            "Every number under this heading is comparable with every other number "
            "under this heading, and with nothing outside it.",
            "",
        ]
        out += _render_retrieval_runs(group)
    return out + _render_retrieval_tail(block)


def _render_retrieval_runs(runs: Sequence[dict]) -> list[str]:
    out: list[str] = []
    for run in runs:
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

            # Withholding the measured value but printing % of attainable would
            # leak it straight back: 54% of a published 0.7789 ceiling reconstructs
            # 0.4206. If the measurement is withheld for want of an n, everything
            # derived from it is withheld too.
            if row.get("n_queries") is None:
                pct_cell = "withheld (n unknown)"
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
    return out


def _render_retrieval_tail(block: dict) -> list[str]:
    out: list[str] = []
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
                run["snapshot"]["key"],
                run.get("invalidation_reason", "unknown"),
            ])
        out += _table(
            ["run_id", "date", "retriever", "config", "label snapshot", "reason"], rows) + [""]

    out += ["### Trend — same config hash *and* same label snapshot only", ""]
    if not block["deltas"]:
        out += [
            "_No (config hash, label snapshot) pair has more than one valid run "
            "yet, so there is nothing to compare. Runs under different hashes, or "
            "under different label snapshots, are different measurements and are "
            "deliberately not differenced._",
            "",
        ]
    else:
        for delta in block["deltas"]:
            out += [
                f"**{delta.get('retriever')}** · config `{delta['config_hash']}` · "
                f"snapshot `{delta['snapshot_key']}` · "
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


def _render_cost(block: dict) -> list[str]:
    out = ["## Cost — every figure in this project is a lower bound", ""]
    out += [
        f"> {COST_LOWER_BOUND_REASON}",
        ">",
        "> Nothing downstream can correct for this. Treat every dollar amount in "
        "this document, and every dollar amount derived from these sinks "
        "anywhere else, as a floor.",
        "",
    ]
    if not block["sinks"]:
        out += ["_No cost-bearing records on disk._", ""]
        return out
    rows = []
    for entry in block["sinks"]:
        rows.append([
            f"`{entry['sink']}`",
            entry["scope"],
            str(entry.get("n")),
            _usd(entry.get("usd"), entry.get("unpriced_calls") or 0),
            str(entry.get("unpriced_calls") or 0),
        ])
    out += _table(["sink", "scope", "records", "recorded cost", "unpriced calls"], rows) + [""]
    if block["any_unpriced_calls"]:
        out += [
            f"**{block['unpriced_calls']} call(s) carry no price** on top of the "
            "unrecorded spend above, so the totals are understated twice over and "
            "render with `>=`.",
            "",
        ]
    out += [
        f"No grand total is given: {block['grand_total_note']}.",
        "",
    ]
    return out


def _render_ann(block: dict) -> list[str]:
    out = ["## ANN / HNSW index sweep — `results/ann_sweep.jsonl`", ""]
    if not block.get("present"):
        out += [
            "_No ANN sweep on disk. Run `python3 -m ann_sweep.run_ann_sweep "
            "--what all` from `scripts/eval/` to produce it._",
            "",
        ]
        return out

    corpus = block["corpora"][0] if len(block["corpora"]) == 1 else None
    out += [
        f"{block['n_records']} record(s), sweep version(s) "
        f"{', '.join(block['sweep_versions'])}. "
        + (
            f"Corpus: {corpus['documents']} documents / {corpus['chunks']} chunks "
            f"(project `{corpus['project_id']}`)."
            if corpus else
            f"{len(block['corpora'])} distinct corpus fingerprints -- rows from "
            "different corpora are not comparable."
        ),
        "",
        "> **Two measurement modes live in this file and they answer different "
        "questions.**",
        f"> *{MODE_LABELS[MODE_PLANNER_FREE]}* is the query as production issues "
        "it, with Postgres free to choose the plan.",
        f"> *{MODE_LABELS[MODE_INDEX_FORCED]}* switches the sequential scan off "
        "and drops every competing index inside a rolled-back transaction, which "
        "is the only way to see the HNSW curve at a depth where the planner "
        "refuses the index.",
        "> **An index-forced number is never what production does.** Every row "
        "below carries its mode.",
        "",
        "This sink records no `run_id` — it is keyed by parameters plus corpus "
        "fingerprint, one record per configuration, appended forever. Provenance "
        "is therefore the file plus the derived point id shown on each row.",
        "",
    ]

    # -- the planner finding ------------------------------------------------
    cross = block["planner_crossover"]
    out += ["### Does the planner use the index at all?", ""]
    if block["planner_choice"]:
        rows = []
        for probe in block["planner_choice"]:
            for choice in probe["choices"]:
                rows.append([
                    str(choice["k"]),
                    f"`{choice['index_used']}`" if choice["index_used"]
                    else "**no index — sequential scan (exact search)**",
                    _date(probe.get("timestamp")),
                    f"`{probe['point_id']}`",
                ])
        out += _table(["LIMIT", "plan", "date", "point"], rows) + [""]
    if cross["highest_k_using_index"] is not None and cross["lowest_k_declining_index"] is not None:
        out += [
            f"**Postgres declines the HNSW index above a LIMIT of roughly "
            f"{cross['highest_k_using_index']}–{cross['lowest_k_declining_index']} "
            "and runs an exact sequential scan instead.** Not \"the index is "
            "slow\" — the index is not consulted, so `ef_search` is a parameter "
            "of a code path that never runs. Production's real call sites ask "
            "for 3–10 chunks and are below the crossover; the retrieval eval "
            "harness asks for 50 and is above it, so its \"HNSW\" dense row is "
            "in fact an exact-scan result. This is a small-corpus finding: on a "
            "10x corpus the sequential scan gets 10x more expensive and the "
            "crossover moves above any realistic k.",
            "",
        ]

    # -- exact search, the ceiling -----------------------------------------
    out += ["### Exact sequential scan — the ANN-recall ceiling", "",
            "Exact search *is* the ground truth for ANN recall, so its ANN recall "
            "is 1.0 by definition, not by measurement. Its **label** recall is a "
            "different quantity and is capped by the label design like every "
            "other label metric here.", ""]
    rows = []
    for row in block["exact"]:
        rows.append([
            str(row["k"]),
            row["mode_label"],
            _metric(row["label_metrics"].get("recall@10"), row["label_n_queries"]),
            _metric(row["label_metrics"].get("ndcg@10"), row["label_n_queries"]),
            _metric(row["server_p50_ms"], row["n_samples"], places=2),
            _num(row["server_p95_ms"], 2),
        ])
    out += _table(
        ["k", "mode", "label recall@10", "label NDCG@10",
         "server p50 ms (n = samples)", "p95 ms"],
        rows,
    ) + [""]
    out += [
        f"Label recall@10 here has ceiling: "
        f"{block['exact'][0]['label_ceiling_provenance'] if block['exact'] else 'unknown'}.",
        "",
    ]
    for entry in block["exact_repeat_noise"]:
        if entry["n_runs"] < 2:
            continue
        out += [
            f"**Machine noise bound (k={entry['k']}):** the identical exact-scan "
            f"measurement was repeated {entry['n_runs']} times across sweep runs "
            f"and its server p50 came out at {_num(entry['p50_ms_min'], 2)} / "
            f"{_num(entry['p50_ms_mean'], 2)} / {_num(entry['p50_ms_max'], 2)} ms "
            f"(min / mean / max) — a spread of "
            f"±{entry['plus_minus_pct']:.0f}% about the mean on an unchanged "
            "input. **No latency difference smaller than that is readable in "
            "this document.** Sub-2 ms rows are dominated by fixed per-query "
            "overhead, so the *ratios* between them are trustworthy and the "
            "absolute values are not.",
            "",
        ]

    # -- ef_search curve ----------------------------------------------------
    out += ["### `ef_search` curve", ""]
    ks = sorted({r["k"] for r in block["ef_search"] if r["k"] is not None})
    for k in ks:
        for mode in (MODE_PLANNER_FREE, MODE_INDEX_FORCED):
            rows_for = [r for r in block["ef_search"] if r["k"] == k and r["mode"] == mode]
            if not rows_for:
                continue
            out += [f"#### k = {k} — {MODE_LABELS[mode]}", ""]
            if mode == MODE_INDEX_FORCED:
                out += [
                    "_These rows describe the index. They are **not** what "
                    "production executes at this depth._",
                    "",
                ]
            rows = []
            for row in rows_for:
                ann = row["ann_recall"]
                rows.append([
                    ("**" + str(row["ef_search"]) + " (PROD)**") if row["is_production_reference"]
                    else str(row["ef_search"]),
                    _metric(ann.get(f"recall@{k}", ann.get("recall@10")), row["n_queries"]),
                    _metric(row["label_metrics"].get("recall@10"), row["label_n_queries"]),
                    _metric(row["server_p50_ms"], row["n_samples"], places=2),
                    _num(row["server_p95_ms"], 2),
                    row["plan"],
                    f"`{row['point_id']}`",
                ])
            out += _table(
                ["ef_search", f"ANN recall@{k} vs exact (n = queries)",
                 "label recall@10 (n = queries)", "server p50 ms (n = samples)",
                 "p95 ms", "plan", "point"],
                rows,
            ) + [""]
    for flip in block["plan_flip"]:
        out += [
            f"**Raising `ef_search` past {flip['reference_ef_search']} at k="
            f"{flip['k']} makes the query {flip['slowdown_x']:.0f}x slower**: "
            f"{_num(flip['reference_p50_ms'], 2)} ms p50 at "
            f"ef_search {flip['reference_ef_search']} with an "
            f"{flip['reference_plan']}, against "
            f"{_num(flip['flipped_p50_ms'], 2)} ms at {flip['flipped_ef_search']} "
            f"— because the cost model abandons the index and the plan flips to "
            f"a sequential scan, not because the index got slower. The "
            f"index-forced rows above show what the index alone would have done "
            f"at the same settings. n = {flip['n_samples']} latency samples per "
            f"point, and the flip is far larger than the noise bound.",
            "",
        ]

    # -- build grid ---------------------------------------------------------
    out += ["### `m` x `ef_construction` grid", "",
            f"All rows are {MODE_LABELS[MODE_INDEX_FORCED]}: the planner declines "
            "every candidate index at this depth, so without forcing, every row "
            "would be the same sequential scan. **These describe the index, not "
            "production.**", ""]
    rows = []
    for row in block["build_grid"]:
        ann = row["ann_recall"]
        rows.append([
            str(row["m"]),
            str(row["ef_construction"]),
            _num(row["build_seconds"], 2),
            f"{row['index_bytes']:,}" if row.get("index_bytes") is not None else "unknown",
            _metric(ann.get("recall@50", ann.get("recall@10")), row["n_queries"]),
            _metric(row["label_metrics"].get("recall@10"), row["label_n_queries"]),
            _metric(row["server_p50_ms"], row["n_samples"], places=2),
            f"`{row['point_id']}`",
        ])
    out += _table(
        ["m", "ef_construction", "build s", "index bytes",
         "ANN recall@50 vs exact (n = queries)", "label recall@10 (n = queries)",
         "server p50 ms (n = samples)", "point"],
        rows,
    ) + [""]

    size = block["index_size"]
    if size["identical_at_every_point"] and size["bytes"] is not None:
        out += [
            f"**Index size is identical — {size['bytes']:,} bytes — at every one "
            f"of the {size['n_points']} grid points, across m = "
            f"{', '.join(str(v) for v in size['m_values'])}.** Not approximately: "
            f"exactly. {size['bytes']:,} / {PG_PAGE_BYTES} = {size['pages']:,} "
            "pages for the chunks in this corpus, i.e. one page per vector. A "
            "1536-dimensional `float4` vector is 6 KB, so it and its neighbour "
            f"list share one {PG_PAGE_BYTES // 1024} KB page whatever `m` is. "
            "**Any claim that raising `m` costs disk is unsupported here.**",
            "",
        ]
    elif size["distinct_byte_values"]:
        out += [
            "Index size varies across the grid: "
            + ", ".join(f"{v:,}" for v in size["distinct_byte_values"]) + " bytes.",
            "",
        ]
    build_time = block["build_time"]
    if build_time["span_x"]:
        out += [
            f"Build time is the only cost that moves, and it moves modestly: "
            f"{_num(build_time['min_seconds'], 2)} s to "
            f"{_num(build_time['max_seconds'], 2)} s, a "
            f"{build_time['span_x']:.1f}x span over {build_time['n_points']} "
            "grid points.",
            "",
        ]

    # -- exclusions ---------------------------------------------------------
    out += ["### Excluded sweep points — in no table above", ""]
    if not block["excluded"]:
        out += ["_None._", ""]
    else:
        rows = [
            [f"`{row['point_id']}`", _date(row.get("timestamp")),
             row.get("mode_label", "unknown"), row["exclusion_reason"]]
            for row in block["excluded"]
        ]
        out += _table(["point", "date", "mode", "reason"], rows) + [""]
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
    parts.append("\n".join(_render_cost(data["cost"])))
    parts.append("\n".join(_render_retrieval(data["retrieval"])))
    parts.append("\n".join(_render_ann(data["ann_sweep"])))
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

"""Tests for the benchmark distiller.

The honesty rules are the product here, so most of these assert on absence:
that a number *cannot* be printed without its n, that an invalid run *cannot*
reach a headline, that an incomplete cost *cannot* render as a clean total, and
that two different config hashes *cannot* be differenced.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

EVAL_DIR = Path(__file__).resolve().parents[1]
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

import benchmarks as B  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

LABELS_FP, QUERIES_FP = next(iter(B.KNOWN_RECALL_CEILINGS))


def write_jsonl(root: Path, rel: str, records, *, truncate_last: bool = False) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(r, sort_keys=True) for r in records]
    text = "\n".join(lines)
    if truncate_last and lines:
        # Chop the tail of the final line -- exactly what a killed process
        # leaves behind.
        text = text[: -max(2, len(lines[-1]) // 2)]
    path.write_text(text + ("" if truncate_last else "\n"), encoding="utf-8")
    return path


def retrieval_record(
    *,
    run_id="r1",
    config_hash="hash-a",
    retriever="dense",
    timestamp="2026-07-30T10:00:00+00:00",
    valid=True,
    metrics=None,
    n_scored=59,
    known_fingerprints=True,
    degradation=None,
    invalidated_by=None,
):
    return {
        "run_id": run_id,
        "timestamp": timestamp,
        "config_hash": config_hash,
        "valid": valid,
        "invalidated_by": invalidated_by or [],
        "degradation": degradation or {
            "checked": True, "degraded": False, "failure_count": 0,
            "last_error": None, "name": "keyword_search_chunks",
        },
        "k": 10,
        "relevance_unit": "document",
        "n_queries": 59,
        "n_queries_scored": n_scored,
        "n_relevant_total": 903,
        "metrics": metrics or {
            "map": 0.4391, "mrr": 0.8836, "ndcg@10": 0.6526,
            "recall@1": 0.0896, "recall@5": 0.3051,
            "recall@10": 0.4221, "recall@20": 0.5299,
        },
        "failure_breakdown": {"total_misses": 600, "ranking_failure": 137},
        "retrieval_health": {"rows_returned": 16900},
        "resolution_report": {"pooled_corpus_size": 118, "n_topics": 15, "n_topics_with_labels": 12},
        "config": {
            "retriever": retriever,
            "graded": False,
            "chunk_oversample": 5,
            "labels_fingerprint": LABELS_FP if known_fingerprints else "deadbeef",
            "queries_fingerprint": QUERIES_FP if known_fingerprints else "deadbeef",
        },
    }


def node_summary(*, run_id="n1", timestamp="2026-07-30T10:00:00+00:00",
                 unpriced=0, usd=0.1654, nodes=("editor_pass_node",), papers=("p1",),
                 repeat=1, reviewer_type=None):
    return {
        "record_type": "run_summary",
        "run_id": run_id,
        "timestamp": timestamp,
        "planned_replays": 1,
        "attempted_replays": 1,
        "completed_replays": 1,
        "failed_replays": 0,
        "halted": None,
        "total_llm_calls": 1,
        "total_estimated_usd": usd,
        "config": {
            "nodes": list(nodes),
            "papers": list(papers),
            "reviewer_type": reviewer_type,
            "repeat": repeat,
            "with_metric": False,
        },
        "per_node": [{
            "node": nodes[0],
            "paper_id": papers[0],
            "reviewer_type": reviewer_type,
            "runs": 1,
            "failures": 0,
            "llm_calls": 1,
            "prompt_tokens": 877,
            "completion_tokens": 766,
            "cached_tokens": 0,
            "estimated_usd": usd,
            "unpriced_calls": unpriced,
            "latency_seconds": {"n": 1, "mean": 8.19, "median": 8.19, "min": 8.19, "max": 8.19},
        }],
    }


def node_replay(*, node="editor_pass_node", wall=8.19, unpriced=0, usd=0.0017, status="ok"):
    return {
        "record_type": "replay",
        "node": node,
        "paper_id": "p1",
        "reviewer_type": None,
        "repeat_index": 0,
        "run_id": "n1",
        "status": status,
        "trace_id": "t" * 32,
        "span_id": "s" * 32,
        "timestamp": "2026-07-30T10:00:00+00:00",
        "wall_seconds": wall,
        "metric": None,
        "usage": {
            "calls": 1, "prompt_tokens": 877, "completion_tokens": 766,
            "cached_tokens": 0, "total_tokens": 1643, "estimated_usd": usd,
            "unpriced_calls": unpriced, "by_label": {}, "by_model": {},
        },
    }


def span(*, span_id, trace_id, name="editor_pass_node", start=0.0, end=1.0):
    return {
        "name": name,
        "kind": "node",
        "trace_id": trace_id,
        "span_id": span_id,
        "parent_span_id": None,
        "status": "OK",
        "start_time": start,
        "end_time": end,
        "duration_ms": (end - start) * 1000.0,
        "attributes": {"noesis.node.name": name},
    }


def ingest_record(*, doc_id="d1", tokens=10531, chunks=7, action="ingested", error=None):
    return {
        "action": action,
        "chunk_count": chunks,
        "chunk_overlap": 250,
        "chunk_size": 1600,
        "chunking_method": "basic",
        "chunking_splitter": "pysbd",
        "cost_ceiling_applied": False,
        "doc_id": doc_id,
        "embedding_dimensions": 1536,
        "embedding_model": "text-embedding-3-large",
        "error": error,
        "extractor": "pymupdf",
        "page_count": 23,
        "rows_inserted": chunks,
        "token_count": tokens,
    }


def history_record(*, run_id="h1", version="v1", mean=7.5, generated_at="2026-07-30T10:00:00+00:00",
                   halluc=1, cells=2):
    return {
        "run_id": run_id,
        "generated_at": generated_at,
        "pipeline_version": version,
        "config": {"drafts": ["draft1.pdf"]},
        "aggregates": {
            "mean_overall": mean,
            "total_hallucinations": halluc,
            "total_cells": cells,
            "scored_cells": cells,
        },
        "cells": [{"cell_key": f"c{i}", "overall": mean, "hallucinations": 0} for i in range(cells)],
    }


# ---------------------------------------------------------------------------
# Reading / missing sources
# ---------------------------------------------------------------------------

def test_all_sources_absent_still_builds(tmp_path):
    data = B.build(tmp_path)
    assert data["schema_version"] == B.SCHEMA_VERSION
    assert all(not s["present"] for s in data["sources"])
    text = B.render(data)
    assert "_No retrieval runs recorded._" in text
    assert "_No node replays recorded._" in text
    assert "Raw spans are not tracked" in text
    assert "No ingest manifest on disk" in text
    assert "_No sweeps recorded." in text


def test_missing_source_is_not_an_error_only_a_gap(tmp_path):
    write_jsonl(tmp_path, B.SRC_RETRIEVAL, [retrieval_record()])
    data = B.build(tmp_path)
    by_path = {s["path"]: s for s in data["sources"]}
    assert by_path[B.SRC_RETRIEVAL]["present"] is True
    assert by_path[B.SRC_INGEST]["present"] is False
    assert by_path[B.SRC_INGEST]["records"] == 0
    assert data["retrieval"]["n_runs"] == 1


@pytest.mark.parametrize("rel,records", [
    (B.SRC_RETRIEVAL, [retrieval_record(run_id="a"), retrieval_record(run_id="b")]),
    (B.SRC_NODE_EVAL, [node_summary(run_id="a"), node_summary(run_id="b")]),
    (B.SRC_INGEST, [ingest_record(doc_id="a"), ingest_record(doc_id="b")]),
    (B.SRC_OPENREVIEW, [history_record(run_id="a"), history_record(run_id="b")]),
])
def test_truncated_final_line_is_skipped_and_counted(tmp_path, rel, records):
    write_jsonl(tmp_path, rel, records, truncate_last=True)
    read = B.read_jsonl(tmp_path, rel)
    assert len(read.records) == 1, "the intact record survives"
    assert read.skipped == 1, "the truncated one is counted, not silently dropped"
    assert "not JSON" in read.skip_reasons[0][1]

    text = B.render(B.build(tmp_path))
    assert f"`{rel}`" in text


def test_garbage_line_is_skipped_and_surfaced_in_the_board(tmp_path):
    path = tmp_path / B.SRC_RETRIEVAL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(retrieval_record()) + "\n" + "not json at all\n" + "[1,2,3]\n",
        encoding="utf-8",
    )
    read = B.read_jsonl(tmp_path, B.SRC_RETRIEVAL)
    assert len(read.records) == 1
    assert read.skipped == 2
    text = B.render(B.build(tmp_path))
    source_row = next(l for l in text.splitlines() if l.startswith(f"| `{B.SRC_RETRIEVAL}`"))
    assert "2 (line 2: not JSON" in source_row, source_row


def test_span_truncation_is_handled_by_trace_report(tmp_path):
    write_jsonl(
        tmp_path, B.SRC_SPANS,
        [span(span_id="a" * 32, trace_id="t1"), span(span_id="b" * 32, trace_id="t2")],
        truncate_last=True,
    )
    block = B.distil_spans(tmp_path)
    assert block["present"] is True
    assert block["parse"]["spans_parsed"] == 1
    assert block["parse"]["malformed_lines"] == 1


# ---------------------------------------------------------------------------
# Rule 1 -- no metric without n
# ---------------------------------------------------------------------------

def test_metric_helper_refuses_to_print_without_n():
    assert B._metric(0.4221, 59) == "0.4221 (n=59)"
    assert B._metric(0.4221, None) == "withheld (n unknown)"
    assert "0.4221" not in B._metric(0.4221, None)
    assert B._metric(None, 59) == "no data (n=59)"


def test_every_retrieval_metric_row_carries_its_n(tmp_path):
    write_jsonl(tmp_path, B.SRC_RETRIEVAL, [retrieval_record()])
    data = B.build(tmp_path)
    run = data["retrieval"]["headline"][0]
    assert run["metrics"]
    for row in run["metrics"]:
        assert row["n_queries"] == 59
    text = B.render(data)
    for line in text.splitlines():
        if line.startswith("| `recall@") or line.startswith("| `map`") or line.startswith("| `mrr`"):
            assert "(n=" in line, line


def test_metric_without_n_is_withheld_not_printed(tmp_path):
    record = retrieval_record()
    record["n_queries_scored"] = None
    record["n_queries"] = None
    write_jsonl(tmp_path, B.SRC_RETRIEVAL, [record])
    text = B.render(B.build(tmp_path))
    assert "withheld (n unknown)" in text
    assert "0.4221" not in text


def test_span_percentiles_are_refused_not_guessed(tmp_path):
    spans = [
        span(span_id=f"{i:032d}", trace_id=f"t{i}", start=0.0, end=1.0 + i)
        for i in range(3)
    ]
    write_jsonl(tmp_path, B.SRC_SPANS, spans)
    text = B.render(B.build(tmp_path))
    assert "refused (n=3 < 20)" in text


# ---------------------------------------------------------------------------
# Rule 2 -- invalid runs never reach a headline
# ---------------------------------------------------------------------------

def test_invalid_run_is_excluded_from_headline_and_listed_with_reason(tmp_path):
    good = retrieval_record(run_id="good", timestamp="2026-07-30T10:00:00+00:00")
    bad = retrieval_record(
        run_id="bad",
        timestamp="2026-07-30T11:00:00+00:00",  # newer -- must still not win
        valid=False,
        metrics={"recall@10": 0.9999},
        degradation={
            "checked": True, "degraded": True, "failure_count": 3,
            "last_error": "RPC keyword_search_chunks failed",
            "name": "keyword_search_chunks",
        },
    )
    write_jsonl(tmp_path, B.SRC_RETRIEVAL, [good, bad])
    data = B.build(tmp_path)
    block = data["retrieval"]

    assert [r["run_id"] for r in block["headline"]] == ["good"]
    assert block["n_valid"] == 1
    assert block["n_invalidated"] == 1
    assert block["invalidated"][0]["run_id"] == "bad"
    reason = block["invalidated"][0]["invalidation_reason"]
    assert "degraded" in reason and "keyword_search_chunks" in reason

    text = B.render(data)
    assert "0.9999" not in text, "an invalid metric never reaches the board body"
    assert "Invalidated runs — excluded from every number above" in text
    assert "RPC keyword_search_chunks failed" in text


def test_invalid_run_does_not_contribute_a_delta(tmp_path):
    good = retrieval_record(run_id="g1", timestamp="2026-07-30T10:00:00+00:00")
    bad = retrieval_record(run_id="g2", timestamp="2026-07-30T11:00:00+00:00", valid=False)
    write_jsonl(tmp_path, B.SRC_RETRIEVAL, [good, bad])
    assert B.build(tmp_path)["retrieval"]["deltas"] == []


def test_invalidated_by_tokens_are_reported(tmp_path):
    bad = retrieval_record(run_id="x", valid=False, invalidated_by=["labels_changed_mid_run"])
    write_jsonl(tmp_path, B.SRC_RETRIEVAL, [bad])
    text = B.render(B.build(tmp_path))
    assert "labels_changed_mid_run" in text


# ---------------------------------------------------------------------------
# Rule 3 -- the ceiling travels with recall@k
# ---------------------------------------------------------------------------

def test_ceiling_renders_when_fingerprints_are_known(tmp_path):
    write_jsonl(tmp_path, B.SRC_RETRIEVAL, [retrieval_record(known_fingerprints=True)])
    data = B.build(tmp_path)
    rows = {r["metric"]: r for r in data["retrieval"]["headline"][0]["metrics"]}
    assert rows["recall@10"]["ceiling"] == pytest.approx(0.7789)
    assert rows["recall@10"]["pct_of_attainable"] == pytest.approx(0.4221 / 0.7789)
    text = B.render(data)
    assert "0.7789" in text
    assert "54%" in text


def test_ceiling_is_explicitly_unknown_when_fingerprints_are_not(tmp_path):
    write_jsonl(tmp_path, B.SRC_RETRIEVAL, [retrieval_record(known_fingerprints=False)])
    data = B.build(tmp_path)
    rows = {r["metric"]: r for r in data["retrieval"]["headline"][0]["metrics"]}
    assert rows["recall@10"]["ceiling"] is None
    assert rows["recall@10"]["ceiling_applicable"] is True
    text = B.render(data)
    assert "unknown (no ceiling recorded" in text
    assert "| `recall@10` | 0.4221 (n=59) | unknown | unknown |" in text


def test_record_carried_ceiling_wins_over_the_table(tmp_path):
    record = retrieval_record(known_fingerprints=True)
    record["recall_ceilings"] = {"10": 0.5}
    write_jsonl(tmp_path, B.SRC_RETRIEVAL, [record])
    data = B.build(tmp_path)
    rows = {r["metric"]: r for r in data["retrieval"]["headline"][0]["metrics"]}
    assert rows["recall@10"]["ceiling"] == 0.5
    assert data["retrieval"]["headline"][0]["ceiling_provenance"] == "carried on record"


def test_non_recall_metrics_say_not_applicable_not_unknown(tmp_path):
    write_jsonl(tmp_path, B.SRC_RETRIEVAL, [retrieval_record()])
    data = B.build(tmp_path)
    rows = {r["metric"]: r for r in data["retrieval"]["headline"][0]["metrics"]}
    assert rows["map"]["ceiling_applicable"] is False
    text = B.render(data)
    assert "n/a (not capped by label design)" in text


# ---------------------------------------------------------------------------
# Rule 4 -- incomplete cost is a lower bound
# ---------------------------------------------------------------------------

def test_usd_helper_marks_lower_bound():
    assert B._usd(0.1654, 0) == "$0.1654"
    assert B._usd(0.1654, 2).startswith("$0.1654 >=")
    assert B._usd(None, 0) == "unknown"


def test_unpriced_calls_render_cost_as_lower_bound(tmp_path):
    write_jsonl(tmp_path, B.SRC_NODE_EVAL, [node_summary(unpriced=2, usd=0.1654)])
    data = B.build(tmp_path)
    assert data["node_eval"]["runs"][0]["cost_is_lower_bound"] is True
    assert data["node_eval"]["runs"][0]["unpriced_calls"] == 2
    text = B.render(data)
    assert "$0.1654 >=" in text


def test_fully_priced_cost_renders_clean(tmp_path):
    write_jsonl(tmp_path, B.SRC_NODE_EVAL, [node_summary(unpriced=0, usd=0.1654)])
    data = B.build(tmp_path)
    assert data["node_eval"]["runs"][0]["cost_is_lower_bound"] is False
    text = B.render(data)
    assert "$0.1654" in text
    assert "$0.1654 >=" not in text


def test_replay_level_unpriced_calls_also_mark_the_node_row(tmp_path):
    write_jsonl(tmp_path, B.SRC_NODE_EVAL, [
        node_replay(unpriced=0, usd=0.001),
        node_replay(unpriced=1, usd=0.002),
    ])
    data = B.build(tmp_path)
    entry = data["node_eval"]["per_node"][0]
    assert entry["unpriced_calls"] == 1
    assert entry["cost_is_lower_bound"] is True
    assert ">=" in B.render(data)


# ---------------------------------------------------------------------------
# Rule 5 -- provenance
# ---------------------------------------------------------------------------

def test_every_headline_row_names_its_file_and_run_id(tmp_path):
    write_jsonl(tmp_path, B.SRC_RETRIEVAL, [retrieval_record(run_id="abc123")])
    write_jsonl(tmp_path, B.SRC_NODE_EVAL, [node_summary(run_id="def456")])
    write_jsonl(tmp_path, B.SRC_OPENREVIEW, [history_record(run_id="ghi789")])
    data = B.build(tmp_path)
    assert data["retrieval"]["headline"][0]["source"] == B.SRC_RETRIEVAL
    assert data["node_eval"]["runs"][0]["source"] == B.SRC_NODE_EVAL
    assert data["openreview_history"]["runs"][0]["source"] == B.SRC_OPENREVIEW
    text = B.render(data)
    for token in ("abc123", "def456", "ghi789", B.SRC_RETRIEVAL, B.SRC_NODE_EVAL, B.SRC_OPENREVIEW):
        assert token in text


# ---------------------------------------------------------------------------
# Rule 6 -- deltas only within a config hash
# ---------------------------------------------------------------------------

def test_same_config_hash_produces_a_delta(tmp_path):
    write_jsonl(tmp_path, B.SRC_RETRIEVAL, [
        retrieval_record(run_id="r1", config_hash="same", timestamp="2026-07-30T10:00:00+00:00",
                         metrics={"recall@10": 0.40}),
        retrieval_record(run_id="r2", config_hash="same", timestamp="2026-07-30T11:00:00+00:00",
                         metrics={"recall@10": 0.45}),
    ])
    data = B.build(tmp_path)
    deltas = data["retrieval"]["deltas"]
    assert len(deltas) == 1
    assert deltas[0]["config_hash"] == "same"
    assert deltas[0]["metrics"][0]["delta"] == pytest.approx(0.05)
    # Headline keeps only the newest run of that hash.
    assert [r["run_id"] for r in data["retrieval"]["headline"]] == ["r2"]
    text = B.render(data)
    assert "+0.0500" in text


def test_different_config_hashes_are_never_differenced(tmp_path):
    write_jsonl(tmp_path, B.SRC_RETRIEVAL, [
        retrieval_record(run_id="r1", config_hash="hash-a", retriever="dense",
                         timestamp="2026-07-30T10:00:00+00:00", metrics={"recall@10": 0.40}),
        retrieval_record(run_id="r2", config_hash="hash-b", retriever="keyword",
                         timestamp="2026-07-30T11:00:00+00:00", metrics={"recall@10": 0.45}),
    ])
    data = B.build(tmp_path)
    assert data["retrieval"]["deltas"] == []
    assert len(data["retrieval"]["headline"]) == 2
    text = B.render(data)
    assert "+0.0500" not in text
    assert "different measurements" in text


def test_node_eval_deltas_key_on_derived_config(tmp_path):
    same = [
        node_summary(run_id="n1", timestamp="2026-07-30T10:00:00+00:00", usd=0.10),
        node_summary(run_id="n2", timestamp="2026-07-30T11:00:00+00:00", usd=0.12),
    ]
    write_jsonl(tmp_path, B.SRC_NODE_EVAL, same)
    deltas = B.build(tmp_path)["node_eval"]["deltas"]
    assert len(deltas) == 1
    assert deltas[0]["usd_delta"] == pytest.approx(0.02)


def test_node_eval_different_configs_are_not_differenced(tmp_path):
    write_jsonl(tmp_path, B.SRC_NODE_EVAL, [
        node_summary(run_id="n1", nodes=("editor_pass_node",), usd=0.10),
        node_summary(run_id="n2", nodes=("reviewer_panel_node",), usd=0.12,
                     timestamp="2026-07-30T11:00:00+00:00"),
    ])
    assert B.build(tmp_path)["node_eval"]["deltas"] == []


def test_history_deltas_key_on_pipeline_version(tmp_path):
    write_jsonl(tmp_path, B.SRC_OPENREVIEW, [
        history_record(run_id="h1", version="v1", mean=7.0, generated_at="2026-07-30T10:00:00+00:00"),
        history_record(run_id="h2", version="v1", mean=7.4, generated_at="2026-07-30T11:00:00+00:00"),
        history_record(run_id="h3", version="v2", mean=9.9, generated_at="2026-07-30T12:00:00+00:00"),
    ])
    block = B.build(tmp_path)["openreview_history"]
    assert len(block["deltas"]) == 1
    assert block["deltas"][0]["pipeline_version"] == "v1"
    assert block["deltas"][0]["mean_overall_delta"] == pytest.approx(0.4)


# ---------------------------------------------------------------------------
# Distillation coverage of each source
# ---------------------------------------------------------------------------

def test_ingest_manifest_is_summarized(tmp_path):
    write_jsonl(tmp_path, B.SRC_INGEST, [
        ingest_record(doc_id="d1", tokens=100, chunks=2),
        ingest_record(doc_id="d1", tokens=100, chunks=2, action="skipped"),
        ingest_record(doc_id="d2", tokens=300, chunks=6, error="boom"),
    ])
    block = B.build(tmp_path)["ingest"]
    assert block["n_records"] == 3
    assert block["n_distinct_docs"] == 2
    assert block["errors"] == 1
    assert block["actions"] == {"ingested": 2, "skipped": 1}
    assert block["extractors"] == {"pymupdf": 3}
    assert block["tokens"]["total"] == 500
    assert block["tokens"]["n"] == 3
    text = B.render(B.build(tmp_path))
    assert "text-embedding-3-large@1536" in text


def test_span_source_is_parsed_by_trace_report_not_a_second_parser(tmp_path):
    write_jsonl(tmp_path, B.SRC_SPANS, [
        span(span_id="a" * 32, trace_id="t1", end=2.0),
        span(span_id="b" * 32, trace_id="t2", end=3.0),
    ])
    block = B.build(tmp_path)["spans"]
    assert block["present"] is True
    assert block["traces"] == 2
    assert block["nodes"][0]["executions"] == 2
    assert block["nodes"][0]["wall_ms"]["n"] == 2


def test_node_eval_replays_and_summaries_both_land(tmp_path):
    write_jsonl(tmp_path, B.SRC_NODE_EVAL, [
        node_summary(run_id="n1"),
        node_replay(wall=1.0),
        node_replay(wall=3.0),
        node_replay(wall=2.0, status="error"),
    ])
    block = B.build(tmp_path)["node_eval"]
    assert block["n_run_summaries"] == 1
    assert block["n_replays"] == 3
    entry = block["per_node"][0]
    assert entry["replays"] == 3
    assert entry["ok"] == 2 and entry["failed"] == 1
    assert entry["wall_seconds_n"] == 3
    assert entry["wall_seconds_mean"] == pytest.approx(2.0)
    assert entry["wall_seconds_min"] == 1.0
    assert entry["wall_seconds_max"] == 3.0


def test_gate_calibration_absence_is_stated_not_zeroed(tmp_path):
    block = B.build(tmp_path)["gate_calibration"]
    assert block["n_sweeps"] == 0
    text = B.render(B.build(tmp_path))
    assert "not a zero, an absence" in text


def test_gate_calibration_sweep_is_distilled_when_present(tmp_path):
    write_jsonl(tmp_path, B.SRC_SWEEP, [{
        "schema_version": 1,
        "generated_at": "2026-07-30T10:00:00+00:00",
        "fp_cost": 1.0,
        "fn_cost": 5.0,
        "dataset": {"n_exports": 10, "n_scoreable": 8, "n_degraded": 3, "base_rate": 0.375},
        "warnings": ["only 8 labels"],
        "gate_as_shipped": {"precision": 0.5, "recall": 0.66},
    }])
    block = B.build(tmp_path)["gate_calibration"]
    assert block["n_sweeps"] == 1
    assert block["sweeps"][0]["n_scoreable"] == 8
    text = B.render(B.build(tmp_path))
    assert "0.3750 (n=8)" in text
    assert "only 8 labels" in text


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

def _populate(root: Path) -> None:
    write_jsonl(root, B.SRC_RETRIEVAL, [
        retrieval_record(run_id="r1", config_hash="h", timestamp="2026-07-30T10:00:00+00:00"),
        retrieval_record(run_id="r2", config_hash="h", timestamp="2026-07-30T11:00:00+00:00"),
        retrieval_record(run_id="r3", config_hash="h2", valid=False),
    ])
    write_jsonl(root, B.SRC_NODE_EVAL, [node_summary(unpriced=1), node_replay()])
    write_jsonl(root, B.SRC_SPANS, [span(span_id="a" * 32, trace_id="t1")])
    write_jsonl(root, B.SRC_INGEST, [ingest_record(), ingest_record(doc_id="d2")])
    write_jsonl(root, B.SRC_OPENREVIEW, [history_record()])


def test_regenerating_twice_is_byte_identical(tmp_path):
    _populate(tmp_path)
    first_md = B.render(B.build(tmp_path))
    first_json = B.render_json(B.build(tmp_path))
    second_md = B.render(B.build(tmp_path))
    second_json = B.render_json(B.build(tmp_path))
    assert first_md == second_md
    assert first_json == second_json


def test_no_generation_timestamp_leaks_into_the_output(tmp_path):
    """A wall-clock stamp would churn git on every run and defeat diffing."""
    _populate(tmp_path)
    payload = json.loads(B.render_json(B.build(tmp_path)))
    assert "generated_at" not in payload
    # trace_report's build_report stamps time.time(); we must not be using it.
    assert "generated_at" not in payload["spans"]


def test_cli_writes_both_outputs_and_check_detects_staleness(tmp_path):
    _populate(tmp_path)
    md = tmp_path / "BENCHMARKS.md"
    js = tmp_path / "benchmarks.json"
    argv = ["--root", str(tmp_path), "--md", str(md), "--json", str(js)]

    assert B.main(argv) == 0
    assert md.exists() and js.exists()
    before = (md.read_bytes(), js.read_bytes())

    assert B.main(argv + ["--check"]) == 0, "fresh outputs are not stale"

    assert B.main(argv) == 0
    assert (md.read_bytes(), js.read_bytes()) == before, "rerun must be byte-identical"

    # A new measurement makes the tracked outputs stale.
    write_jsonl(tmp_path, B.SRC_INGEST, [ingest_record(doc_id="d9", tokens=999)])
    assert B.main(argv + ["--check"]) == 1


def test_json_is_sorted_and_reloadable(tmp_path):
    _populate(tmp_path)
    payload = B.render_json(B.build(tmp_path))
    reloaded = json.loads(payload)
    assert reloaded["schema_version"] == B.SCHEMA_VERSION
    # sort_keys=True means the serialization is stable across dict orderings.
    assert payload == json.dumps(reloaded, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


# ---------------------------------------------------------------------------
# The real files on disk, when they exist
# ---------------------------------------------------------------------------

def test_real_repository_state_distils_without_error():
    data = B.build(EVAL_DIR)
    text = B.render(data)
    assert text.startswith("# Benchmarks")
    assert B.render(B.build(EVAL_DIR)) == text
    # Whatever is on disk, no metric may render bare.
    for line in text.splitlines():
        if line.startswith("| `recall@"):
            assert "(n=" in line, line

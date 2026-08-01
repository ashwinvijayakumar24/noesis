"""Tree reconstruction and malformed-input tolerance."""

from __future__ import annotations

import json

from trace_report import parse as P

from .conftest import llm, span, write_jsonl


def test_nested_tree_reconstruction(make_file):
    spans = [
        span("run", kind="run", start=0.0, duration_ms=1000.0),
        span("a", parent="run", start=0.0, duration_ms=400.0),
        span("b", parent="run", start=0.4, duration_ms=500.0),
        llm("l1", parent="b", start=0.4, duration_ms=450.0),
    ]
    result = P.load_span_files([make_file(spans)])
    assert result.stats.spans_parsed == 4
    assert result.stats.malformed_lines == 0
    trace = result.traces["T1"]
    assert [s.span_id for s in trace.roots()] == ["run"]
    assert [s.span_id for s in trace.children("run")] == ["a", "b"]
    assert [s.span_id for s in trace.children("b")] == ["l1"]
    assert trace.run_span().span_id == "run"


def test_out_of_order_arrival_is_irrelevant(make_file):
    """The writer emits children before parents; order must not matter."""
    ordered = [
        span("run", kind="run", start=0.0, duration_ms=1000.0),
        span("a", parent="run", start=0.0, duration_ms=400.0),
        span("b", parent="a", start=0.0, duration_ms=100.0),
    ]
    forward = P.load_span_files([make_file(ordered)])
    reverse = P.load_span_files([make_file(list(reversed(ordered)))])
    assert [s.span_id for s in forward.traces["T1"].children("run")] == \
           [s.span_id for s in reverse.traces["T1"].children("run")]
    assert reverse.traces["T1"].root_ids == ["run"]


def test_interleaved_traces_are_separated(make_file):
    spans = [
        span("r1", trace_id="TA", kind="run", start=0.0, duration_ms=100.0),
        span("r2", trace_id="TB", kind="run", start=0.0, duration_ms=100.0),
        span("a1", trace_id="TA", parent="r1", start=0.0, duration_ms=50.0),
        span("b1", trace_id="TB", parent="r2", start=0.0, duration_ms=50.0),
        span("a2", trace_id="TA", parent="r1", start=0.05, duration_ms=50.0),
    ]
    result = P.load_span_files([make_file(spans)])
    assert set(result.traces) == {"TA", "TB"}
    assert len(result.traces["TA"].spans) == 3
    assert len(result.traces["TB"].spans) == 2


def test_orphan_span_is_kept_rerooted_and_counted(make_file):
    """A span whose parent line was lost must not vanish from the numbers."""
    spans = [
        span("run", kind="run", start=0.0, duration_ms=100.0),
        span("orphan", parent="missing-parent", start=0.0, duration_ms=50.0),
    ]
    result = P.load_span_files([make_file(spans)])
    trace = result.traces["T1"]
    assert result.stats.orphan_spans == 1
    assert "orphan" in trace.root_ids
    assert trace.orphan_ids == ["orphan"]
    assert "orphan" in trace.spans  # kept, not dropped


def test_truncated_final_line_is_skipped_and_counted(tmp_path):
    spans = [
        span("run", kind="run", start=0.0, duration_ms=100.0),
        span("a", parent="run", start=0.0, duration_ms=50.0),
        span("b", parent="run", start=0.05, duration_ms=50.0),
    ]
    path = write_jsonl(tmp_path / "killed.jsonl", spans, truncate_last=True)
    result = P.load_span_files([path])
    assert result.stats.malformed_lines == 1
    assert result.stats.spans_parsed == 2
    assert "b" not in result.traces["T1"].spans


def test_malformed_lines_are_skipped_and_counted(tmp_path):
    good = span("run", kind="run", start=0.0, duration_ms=100.0)
    path = tmp_path / "messy.jsonl"
    path.write_text(
        "\n".join(
            [
                json.dumps(good),
                "not json at all",
                "[1, 2, 3]",                      # JSON, but not an object
                json.dumps({"name": "x"}),        # object, but no span_id/trace_id
                "",                               # blank line: skipped, not malformed
                json.dumps(span("a", parent="run", start=0.0, duration_ms=10.0)),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    result = P.load_span_files([path])
    assert result.stats.malformed_lines == 3
    assert result.stats.blank_lines == 1
    assert result.stats.spans_parsed == 2
    assert len(result.stats.samples) == 3


def test_duplicate_span_ids_across_files_counted_once(make_file):
    spans = [
        span("run", kind="run", start=0.0, duration_ms=100.0),
        span("a", parent="run", start=0.0, duration_ms=50.0),
    ]
    f1 = make_file(spans)
    f2 = make_file(spans)  # same run exported twice
    result = P.load_span_files([f1, f2])
    assert result.stats.spans_parsed == 2
    assert result.stats.duplicate_span_ids == 2
    assert len(result.traces["T1"].spans) == 2


def test_unreadable_file_does_not_raise(tmp_path):
    result = P.load_span_files([tmp_path / "does-not-exist.jsonl"])
    assert result.traces == {}
    assert result.stats.malformed_lines == 1


def test_missing_timing_is_none_not_zero(make_file):
    raw = span("run", kind="run", start=0.0, duration_ms=100.0)
    raw["duration_ms"] = None
    raw["end_time"] = None
    result = P.load_span_files([make_file([raw])])
    record = result.traces["T1"].spans["run"]
    assert record.wall_ms is None
    assert record.interval is None


def test_node_key_splits_reviewer_variants(make_file):
    spans = [
        span(
            "r1",
            name="reviewer_panel_node",
            attributes={"noesis.node.name": "reviewer_panel_node", "noesis.reviewer.type": "clarity"},
            start=0.0,
            duration_ms=10.0,
        )
    ]
    record = P.load_span_files([make_file(spans)]).traces["T1"].spans["r1"]
    assert record.node_key == "reviewer_panel_node[clarity]"
    assert record.base_name == "reviewer_panel_node"

"""CLI behaviour and the printing honesty rules."""

from __future__ import annotations

import json

import pytest

from trace_report import metrics as M
from trace_report import parse as P
from trace_report import report as R

from .conftest import llm, span


def synthetic_run(trace_id: str, *, scale: float = 1.0, unpriced: bool = False) -> list[dict]:
    """One run resembling the real emitted tree (18-node chain + 3-way fan-out)."""
    spans: list[dict] = []
    cursor = 0.0

    def node(name: str, seconds: float, calls: int = 1, model: str = "gpt-5.2"):
        nonlocal cursor
        start, dur = cursor, seconds * scale
        spans.append(
            span(
                f"{trace_id}_{name}",
                trace_id=trace_id,
                name=name,
                parent=f"{trace_id}_run",
                start=start,
                end=start + dur,
                attributes={"noesis.node.name": name},
            )
        )
        for i in range(calls):
            spans.append(
                llm(
                    f"{trace_id}_{name}_llm{i}",
                    trace_id=trace_id,
                    parent=f"{trace_id}_{name}",
                    model=model,
                    input_tokens=4000,
                    output_tokens=900,
                    cached_tokens=1200,
                    start=start,
                    duration_ms=dur * 900,
                )
            )
        cursor += dur

    spans.append(span(f"{trace_id}_run", trace_id=trace_id, name="draft_analysis_run", kind="run", start=0.0, end=1.0))
    node("extract_structure", 2.0)
    node("extract_claims", 3.5)
    node("citation_mapping", 1.2)

    # 3-way reviewer fan-out: concurrent siblings under the run span.
    fan_start = cursor
    for rt, dur in (("methodology", 11.0), ("literature_positioning", 9.5), ("clarity", 10.0)):
        spans.append(
            span(
                f"{trace_id}_rev_{rt}",
                trace_id=trace_id,
                name="reviewer_panel_node",
                parent=f"{trace_id}_run",
                start=fan_start,
                end=fan_start + dur * scale,
                attributes={"noesis.node.name": "reviewer_panel_node", "noesis.reviewer.type": rt},
            )
        )
        spans.append(
            llm(
                f"{trace_id}_rev_{rt}_llm",
                trace_id=trace_id,
                parent=f"{trace_id}_rev_{rt}",
                model="some-unlisted-model" if (unpriced and rt == "clarity") else "gpt-5.2",
                input_tokens=9000,
                output_tokens=2500,
                cached_tokens=3000,
                start=fan_start,
                duration_ms=dur * scale * 950,
            )
        )
    cursor = fan_start + 11.0 * scale

    node("meta_reviewer_node", 4.0)
    node("editor_pass", 2.5, model="gpt-5-mini")

    spans[0]["end_time"] = cursor
    spans[0]["duration_ms"] = cursor * 1000.0
    return spans


@pytest.fixture
def multi_run_file(tmp_path):
    spans: list[dict] = []
    for i, scale in enumerate((1.0, 1.15, 0.9, 1.3, 1.05)):
        spans.extend(synthetic_run(f"tr{i}", scale=scale, unpriced=(i == 3)))
    path = tmp_path / "traces.jsonl"
    path.write_text("\n".join(json.dumps(s) for s in spans) + "\n", encoding="utf-8")
    return path


def test_cli_runs_and_prints_a_table(multi_run_file, capsys):
    assert R.main([str(multi_run_file), "--sort", "p50"]) == 0
    out = capsys.readouterr().out
    assert "PER-NODE LATENCY" in out
    assert "reviewer_panel_node[methodology]" in out
    assert "FAN-OUT CONCURRENCY" in out
    assert "CRITICAL PATH" in out


def test_cli_never_prints_p95_without_enough_n(multi_run_file, capsys):
    R.main([str(multi_run_file)])
    out = capsys.readouterr().out
    # 5 runs is nowhere near 20; every p95 cell must say so rather than show a number.
    assert "n/a (n=5 < 20)" in out


def test_cli_reports_incomplete_cost(multi_run_file, capsys):
    R.main([str(multi_run_file)])
    out = capsys.readouterr().out
    assert "INCOMPLETE" in out
    assert "could not be priced" in out
    assert ">=" in out


def test_cli_marks_never_executed_nodes(multi_run_file, capsys):
    R.main([str(multi_run_file), "--expect-node", "diagnostic_findings_node"])
    out = capsys.readouterr().out
    assert "NEVER EXECUTED" in out
    assert "diagnostic_findings_node" in out


def test_cli_reports_parse_damage(tmp_path, capsys):
    good = synthetic_run("tr0")
    path = tmp_path / "damaged.jsonl"
    body = "\n".join(json.dumps(s) for s in good)
    path.write_text(body + "\n{\"span_id\": \"trunc\", \"trace", encoding="utf-8")
    R.main([str(path)])
    out = capsys.readouterr().out
    assert "malformed_lines=1" in out


def test_json_output_is_append_only(multi_run_file, tmp_path, capsys):
    out_path = tmp_path / "out" / "report.jsonl"
    R.main([str(multi_run_file), "--json", str(out_path)])
    R.main([str(multi_run_file), "--sort", "cost", "--json", str(out_path)])
    capsys.readouterr()
    lines = out_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2  # second run appended, did not overwrite
    first, second = json.loads(lines[0]), json.loads(lines[1])
    assert first["sort"] == "p95" and second["sort"] == "cost"
    assert "_latency_objects" not in first  # private keys stripped before serialization
    assert first["cost_summary"]["complete"] is False


def test_sort_orders_are_respected(multi_run_file):
    result = P.load_span_files([multi_run_file])
    by_total = R.build_report(result, sort="total")
    totals = [r["total_wall_ms"] for r in by_total["nodes"]]
    assert totals == sorted(totals, reverse=True)

    by_cost = R.build_report(result, sort="cost")
    costs = [by_cost["node_costs"].get(r["node"], {"usd": 0.0})["usd"] for r in by_cost["nodes"]]
    assert costs == sorted(costs, reverse=True)

    by_name = R.build_report(result, sort="name")
    names = [r["node"] for r in by_name["nodes"]]
    assert names == sorted(names)


def test_never_executed_rows_sink_to_the_bottom(multi_run_file):
    result = P.load_span_files([multi_run_file])
    report = R.build_report(result, sort="p95", expected_nodes=["ghost_node"])
    assert report["nodes"][-1]["node"] == "ghost_node"
    assert report["nodes"][-1]["never_executed"] is True


def test_fanout_visible_in_report(multi_run_file):
    result = P.load_span_files([multi_run_file])
    report = R.build_report(result)
    fanouts = report["fanouts"]
    assert fanouts, "the 3-way reviewer fan-out should be detected"
    top = fanouts[0]
    assert top["speedup"] > 1.5
    assert top["sum_ms"] > top["union_ms"]


def test_empty_input_exits_nonzero(tmp_path, capsys):
    path = tmp_path / "empty.jsonl"
    path.write_text("garbage\n", encoding="utf-8")
    assert R.main([str(path)]) == 1


def test_render_table_handles_no_rows():
    assert "no rows" in R.render_table(["a", "b"], [])

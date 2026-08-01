"""Metrics, checked against hand-computed numbers on small fixtures."""

from __future__ import annotations

import pytest

from trace_report import metrics as M
from trace_report import parse as P

from .conftest import llm, span

ALL_N1 = {"p50": 1, "p90": 1, "p95": 1, "p99": 1}


def build(spans) -> P.ParseResult:
    records, stats = P.parse_lines([__import__("json").dumps(s) for s in spans], source="mem")
    return P.build_traces(records, stats)


def trace_of(spans, trace_id: str = "T1") -> P.Trace:
    return build(spans).traces[trace_id]


# ---------------------------------------------------------------------------
# Percentiles
# ---------------------------------------------------------------------------

def test_percentiles_hand_computed():
    """Nearest-rank over [100,200,300,400,500] (n=5), rank = ceil(q*n):

        p50 -> ceil(0.50*5) = 3rd smallest = 300
        p90 -> ceil(0.90*5) = 5th smallest = 500
        p95 -> ceil(0.95*5) = 5th smallest = 500
        p99 -> ceil(0.99*5) = 5th smallest = 500
        min = 100, max = 500, mean = (100+200+300+400+500)/5 = 300
    """
    result = M.percentiles([300, 100, 500, 200, 400], min_n=ALL_N1)
    assert result.n == 5
    assert result.get("p50") == 300.0
    assert result.get("p90") == 500.0
    assert result.get("p95") == 500.0
    assert result.get("p99") == 500.0
    assert result.min == 100.0
    assert result.max == 500.0
    assert result.mean == 300.0


def test_percentiles_hand_computed_even_sample():
    """[10,20,30,40] (n=4): p50 -> ceil(2.0)=2nd = 20; p90 -> ceil(3.6)=4th = 40."""
    result = M.percentiles([40, 10, 30, 20], min_n=ALL_N1)
    assert result.get("p50") == 20.0
    assert result.get("p90") == 40.0
    assert result.mean == 25.0


def test_p95_refused_below_minimum_n():
    result = M.percentiles([1.0, 2.0, 3.0])  # default thresholds: p95 needs 20
    assert result.n == 3
    assert result.get("p95") is None
    assert result.get("p99") is None
    assert "n=3 < 20" in result.refused["p95"]
    assert "n=3 < 100" in result.refused["p99"]
    assert result.get("p50") == 2.0  # p50 at n=3 is legitimate
    assert result.label("p95") == "n/a (n=3 < 20)"


def test_p95_allowed_at_exactly_minimum_n():
    result = M.percentiles([float(i) for i in range(1, 21)])  # n=20
    assert result.n == 20
    assert result.get("p95") == 19.0  # ceil(0.95*20) = 19th smallest
    assert result.get("p99") is None  # still short of 100


def test_no_data_is_not_zero():
    empty = M.percentiles([])
    assert empty.n == 0
    assert empty.get("p50") is None
    assert empty.label("p50") == "n/a (no data)"

    zero = M.percentiles([0.0], min_n=ALL_N1)
    assert zero.n == 1
    assert zero.get("p50") == 0.0
    assert zero.label("p50") == "0.0"


# ---------------------------------------------------------------------------
# Self time vs wall time, including the fan-out
# ---------------------------------------------------------------------------

def test_self_time_subtracts_single_child():
    trace = trace_of(
        [
            span("p", start=0.0, duration_ms=1000.0),
            span("c", parent="p", start=0.2, duration_ms=600.0),
        ]
    )
    timing = M.self_time(trace, trace.spans["p"])
    assert timing.wall_ms == 1000.0
    assert timing.children_union_ms == pytest.approx(600.0)
    assert timing.self_ms == pytest.approx(400.0)
    assert timing.exact is True


def test_fanout_three_10s_reviewers_in_a_12s_parent():
    """The case the whole self-vs-wall distinction exists for.

    Three concurrent reviewers, 10s each, entirely inside a 12s parent:
      sum of child durations = 30_000 ms
      union of child intervals = 10_000 ms   <- what the parent actually waited
      parent self time = 12_000 - 10_000 = 2_000 ms (orchestration overhead)

    Subtracting the SUM would give 12_000 - 30_000 = -18_000 ms, i.e. the
    double-count this test exists to forbid.
    """
    reviewers = [
        span(
            f"rev{i}",
            name="reviewer_panel_node",
            parent="panel",
            start=0.0,
            duration_ms=10_000.0,
            attributes={
                "noesis.node.name": "reviewer_panel_node",
                "noesis.reviewer.type": kind,
            },
        )
        for i, kind in enumerate(("methodology", "literature_positioning", "clarity"))
    ]
    trace = trace_of([span("panel", start=0.0, duration_ms=12_000.0), *reviewers])

    timing = M.self_time(trace, trace.spans["panel"])
    assert timing.children_sum_ms == pytest.approx(30_000.0)
    assert timing.children_union_ms == pytest.approx(10_000.0)
    assert timing.self_ms == pytest.approx(2_000.0)
    assert timing.self_ms >= 0.0

    conc = M.sibling_concurrency(trace, trace.spans["panel"])
    assert conc.sibling_count == 3
    assert conc.sum_ms == pytest.approx(30_000.0)       # ~30s of work
    assert conc.union_ms == pytest.approx(10_000.0)     # in 10s of wall time
    assert conc.parent_wall_ms == pytest.approx(12_000.0)  # inside a 12s parent
    assert conc.speedup == pytest.approx(3.0)
    assert conc.saved_ms == pytest.approx(20_000.0)
    assert conc.overhead_ms == pytest.approx(2_000.0)


def test_fanout_staggered_overlap():
    """Staggered 10s siblings: [0,10], [1,11], [2,12] -> union 12s, speedup 2.5."""
    trace = trace_of(
        [
            span("panel", start=0.0, duration_ms=12_000.0),
            span("a", parent="panel", start=0.0, duration_ms=10_000.0),
            span("b", parent="panel", start=1.0, duration_ms=10_000.0),
            span("c", parent="panel", start=2.0, duration_ms=10_000.0),
        ]
    )
    conc = M.sibling_concurrency(trace, trace.spans["panel"])
    assert conc.sum_ms == pytest.approx(30_000.0)
    assert conc.union_ms == pytest.approx(12_000.0)
    assert conc.speedup == pytest.approx(2.5)
    assert M.self_time(trace, trace.spans["panel"]).self_ms == pytest.approx(0.0)


def test_sequential_siblings_have_no_speedup():
    trace = trace_of(
        [
            span("p", start=0.0, duration_ms=2_000.0),
            span("a", parent="p", start=0.0, duration_ms=1_000.0),
            span("b", parent="p", start=1.0, duration_ms=1_000.0),
        ]
    )
    conc = M.sibling_concurrency(trace, trace.spans["p"])
    assert conc.speedup == pytest.approx(1.0)
    assert M.fanout_concurrency(trace) == []  # filtered out: nothing was parallel


def test_overlap_groups_isolate_the_fanout_from_the_sequential_chain():
    """The real tree: sequential nodes AND the reviewer trio share one parent.

    Children of the run span: A [0,2], B [2,5], then three reviewers all
    [5,15], then C [15,17]. Only the reviewers overlap, so exactly one group of
    3 is reported -- speedup 3.0, not the ~1.8 you get by lumping the whole
    18-node chain in with them.
    """
    trace = trace_of(
        [
            span("run", kind="run", start=0.0, end=17.0),
            span("A", name="A", parent="run", start=0.0, end=2.0),
            span("B", name="B", parent="run", start=2.0, end=5.0),
            *[
                span(f"rev{i}", name="reviewer_panel_node", parent="run", start=5.0, end=15.0)
                for i in range(3)
            ],
            span("C", name="C", parent="run", start=15.0, end=17.0),
        ]
    )
    groups = M.overlap_groups(trace, trace.spans["run"])
    assert [len(g) for g in groups] == [1, 1, 3, 1]

    fanouts = M.fanout_concurrency(trace)
    assert len(fanouts) == 1
    assert fanouts[0].sibling_count == 3
    assert fanouts[0].speedup == pytest.approx(3.0)
    # The group is not all of the run's children, so "parent overhead" would be
    # measuring the sequential chain. It is withheld rather than misreported.
    assert fanouts[0].covers_all_children is False
    assert fanouts[0].overhead_ms is None

    # The all-children view still exists and is deliberately different.
    assert M.sibling_concurrency(trace, trace.spans["run"]).sibling_count == 6


def test_self_time_inexact_when_child_lacks_interval():
    raw_child = span("c", parent="p", start=0.0, duration_ms=400.0)
    raw_child["start_time"] = None
    raw_child["end_time"] = None
    trace = trace_of([span("p", start=0.0, duration_ms=1000.0), raw_child])
    timing = M.self_time(trace, trace.spans["p"])
    assert timing.exact is False
    assert timing.self_ms == pytest.approx(600.0)


# ---------------------------------------------------------------------------
# Per-node latency table
# ---------------------------------------------------------------------------

def _run(trace_id: str, node_ms: dict[str, float]) -> list[dict]:
    spans = [span("run_" + trace_id, trace_id=trace_id, kind="run", start=0.0, duration_ms=sum(node_ms.values()))]
    cursor = 0.0
    for name, ms in node_ms.items():
        spans.append(
            span(
                f"{trace_id}_{name}",
                trace_id=trace_id,
                name=name,
                parent="run_" + trace_id,
                start=cursor,
                duration_ms=ms,
                attributes={"noesis.node.name": name},
            )
        )
        cursor += ms / 1000.0
    return spans


def test_node_latency_across_runs():
    spans = []
    for i, extract_ms in enumerate((100.0, 200.0, 300.0)):
        spans.extend(_run(f"T{i}", {"extract_structure": extract_ms, "editor_pass": 50.0}))
    rows = M.node_latency(build(spans).traces.values(), min_n=ALL_N1)
    by_name = {r.node: r for r in rows}
    assert by_name["extract_structure"].executions == 3
    assert by_name["extract_structure"].traces_seen == 3
    assert by_name["extract_structure"].wall.get("p50") == 200.0
    assert by_name["extract_structure"].total_wall_ms == pytest.approx(600.0)
    assert by_name["editor_pass"].wall.get("p50") == 50.0


def test_never_executed_is_distinct_from_zero_ms():
    """The honesty rule: absent != instant."""
    spans = _run("T1", {"fast_node": 0.0})
    rows = M.node_latency(
        build(spans).traces.values(),
        expected_nodes=["fast_node", "ghost_node"],
        min_n=ALL_N1,
    )
    by_name = {r.node: r for r in rows}

    fast = by_name["fast_node"]
    assert fast.never_executed is False
    assert fast.executions == 1
    assert fast.wall.n == 1
    assert fast.wall.get("p50") == 0.0

    ghost = by_name["ghost_node"]
    assert ghost.never_executed is True
    assert ghost.executions == 0
    assert ghost.wall.n == 0
    assert ghost.wall.get("p50") is None
    assert ghost.wall.label("p50") == "n/a (no data)"


def test_merged_vs_split_reviewer_keys():
    spans = [
        span("run", kind="run", start=0.0, duration_ms=100.0),
        *[
            span(
                f"r{i}",
                name="reviewer_panel_node",
                parent="run",
                start=0.0,
                duration_ms=10.0,
                attributes={"noesis.node.name": "reviewer_panel_node", "noesis.reviewer.type": rt},
            )
            for i, rt in enumerate(("methodology", "clarity", "literature_positioning"))
        ],
    ]
    traces = list(build(spans).traces.values())
    split = {r.node for r in M.node_latency(traces, key=M.default_key)}
    merged = {r.node: r for r in M.node_latency(traces, key=M.merged_key)}
    assert split == {
        "reviewer_panel_node[methodology]",
        "reviewer_panel_node[clarity]",
        "reviewer_panel_node[literature_positioning]",
    }
    assert merged["reviewer_panel_node"].executions == 3


# ---------------------------------------------------------------------------
# Critical path
# ---------------------------------------------------------------------------

def test_critical_path_is_not_the_sum_of_the_biggest_nodes():
    """Hand-drawn graph. run [0,10] with three sequential children:

        A [0,1]   -- child A1 [0,1] covers it entirely
        B [1,9]   -- two PARALLEL children: B1 [1,8] (7s) and B2 [1,9] (8s)
        C [9,10]

    The two biggest nodes are B1 (7s) and B2 (8s), summing to 15s -- more than
    the whole run. The blocking path is A1 (1s) -> B2 (8s) -> C (1s) = 10s,
    exactly the run's wall time. B1 contributes nothing: it finished while B2
    was still running, so it never blocked anyone.
    """
    trace = trace_of(
        [
            span("run", kind="run", start=0.0, end=10.0),
            span("A", name="A", parent="run", start=0.0, end=1.0),
            span("A1", name="A1", parent="A", start=0.0, end=1.0),
            span("B", name="B", parent="run", start=1.0, end=9.0),
            span("B1", name="B1", parent="B", start=1.0, end=8.0),
            span("B2", name="B2", parent="B", start=1.0, end=9.0),
            span("C", name="C", parent="run", start=9.0, end=10.0),
        ]
    )
    path = M.critical_path(trace)
    contributions = {name: ms for _, name, ms in path.by_span()}

    assert path.total_ms == pytest.approx(10_000.0)  # == run wall time, by construction
    assert contributions["B2"] == pytest.approx(8_000.0)
    assert contributions["C"] == pytest.approx(1_000.0)
    assert contributions["A1"] == pytest.approx(1_000.0)
    assert "B1" not in contributions  # 7s of work, 0s of latency
    assert sum(contributions.values()) == pytest.approx(10_000.0)


def test_critical_path_orders_chronologically():
    trace = trace_of(
        [
            span("run", kind="run", start=0.0, end=3.0),
            span("A", name="A", parent="run", start=0.0, end=1.0),
            span("B", name="B", parent="run", start=1.0, end=3.0),
        ]
    )
    path = M.critical_path(trace)
    assert [s.name for s in path.segments] == ["A", "B"]
    assert path.total_ms == pytest.approx(3_000.0)


def test_critical_path_parent_gap_is_attributed_to_the_parent():
    """Parent [0,10] with one child [0,4]: 6s of the parent's own work."""
    trace = trace_of(
        [
            span("run", name="run", kind="run", start=0.0, end=10.0),
            span("c", name="c", parent="run", start=0.0, end=4.0),
        ]
    )
    contributions = {name: ms for _, name, ms in M.critical_path(trace).by_span()}
    assert contributions["run"] == pytest.approx(6_000.0)
    assert contributions["c"] == pytest.approx(4_000.0)


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------

def test_tokens_by_node_model_and_cache():
    trace = trace_of(
        [
            span("run", kind="run", start=0.0, end=10.0),
            span("n1", name="node_a", parent="run", start=0.0, end=5.0,
                 attributes={"noesis.node.name": "node_a"}),
            llm("l1", parent="n1", input_tokens=1000, output_tokens=200, cached_tokens=400),
            llm("l2", parent="n1", model="gpt-5-mini", input_tokens=500, output_tokens=100, cached_tokens=0),
        ]
    )
    by_node = M.tokens_by_node([trace])
    assert by_node["node_a"].calls == 2
    assert by_node["node_a"].input_tokens == 1500
    assert by_node["node_a"].cached_tokens == 400
    # Cached tokens are a SUBSET of input tokens, never added on top.
    assert by_node["node_a"].uncached_input_tokens == 1100
    assert by_node["node_a"].total_tokens == 1800

    by_model = M.tokens_by_model([trace])
    assert set(by_model) == {"gpt-5.2", "gpt-5-mini"}
    assert by_model["gpt-5.2"].cache_hit_rate == pytest.approx(0.4)
    assert by_model["gpt-5-mini"].cache_hit_rate == pytest.approx(0.0)


def test_call_without_usage_is_counted_separately():
    trace = trace_of(
        [
            span("run", kind="run", start=0.0, end=1.0),
            llm("l1", parent="run", input_tokens=None, output_tokens=None, cached_tokens=None),
        ]
    )
    total = M.token_totals([trace])
    assert total.calls == 1
    assert total.calls_without_usage == 1
    assert total.input_tokens == 0  # zero tokens recorded, and the gap is visible above


# ---------------------------------------------------------------------------
# Cost
# ---------------------------------------------------------------------------

def test_cost_recomputed_matches_llm_budget():
    from app.core.llm_budget import estimate_usd

    trace = trace_of(
        [
            span("run", kind="run", start=0.0, end=1.0),
            llm("l1", parent="run", model="gpt-5.2", input_tokens=1_000_000, output_tokens=1_000_000, cached_tokens=0),
        ]
    )
    cost = M.run_cost(trace)
    expected = estimate_usd("gpt-5.2", 1_000_000, 1_000_000, 0)
    assert cost.usd == pytest.approx(expected)
    assert cost.usd == pytest.approx(1.75 + 14.00)  # published rates per 1M
    assert cost.complete is True


def test_cost_respects_cached_subset_pricing():
    trace = trace_of(
        [
            span("run", kind="run", start=0.0, end=1.0),
            llm("l1", parent="run", model="gpt-5.2", input_tokens=1_000_000, output_tokens=0, cached_tokens=1_000_000),
        ]
    )
    # All input cached: 1M * $0.175/1M, NOT 1.75 + 0.175.
    assert M.run_cost(trace).usd == pytest.approx(0.175)


def test_recorded_span_cost_wins_over_recomputation():
    trace = trace_of(
        [
            span("run", kind="run", start=0.0, end=1.0),
            llm("l1", parent="run", cost=0.4242),
        ]
    )
    cost = M.span_cost(trace, trace.spans["l1"])
    assert cost.source == "span_attribute"
    assert cost.usd == pytest.approx(0.4242)


def test_one_unpriced_span_marks_the_run_incomplete():
    """The honesty rule: an unknown cost is a lower bound, never a zero."""
    trace = trace_of(
        [
            span("run", kind="run", start=0.0, end=1.0),
            llm("priced", parent="run", model="gpt-5.2", input_tokens=1_000_000, output_tokens=0),
            llm("mystery", parent="run", model="some-unlisted-model", input_tokens=1_000_000, output_tokens=0),
        ]
    )
    cost = M.run_cost(trace)
    assert cost.llm_spans == 2
    assert cost.priced_spans == 1
    assert cost.unpriced_spans == 1
    assert cost.complete is False
    assert cost.usd == pytest.approx(1.75)  # the priced span only
    assert "not in pricing table" in "".join(cost.unpriced_reasons)
    assert ">=" in cost.label()


def test_missing_usage_makes_a_span_unpriced_not_free():
    trace = trace_of(
        [
            span("run", kind="run", start=0.0, end=1.0),
            llm("l1", parent="run", model="gpt-5.2", input_tokens=None, output_tokens=None, cached_tokens=None),
        ]
    )
    cost = M.run_cost(trace)
    assert cost.unpriced_spans == 1
    assert cost.complete is False
    assert cost.usd == 0.0  # a floor, and `complete` is what says so


def test_cost_by_node_attributes_to_nearest_node_ancestor():
    trace = trace_of(
        [
            span("run", kind="run", start=0.0, end=1.0),
            span("n1", name="editor_pass", parent="run", start=0.0, end=1.0,
                 attributes={"noesis.node.name": "editor_pass"}),
            llm("l1", parent="n1", model="gpt-5.2", input_tokens=1_000_000, output_tokens=0),
            llm("l2", parent="n1", model="nope", input_tokens=10, output_tokens=10),
        ]
    )
    by_node = M.cost_by_node([trace])
    assert set(by_node) == {"editor_pass"}
    assert by_node["editor_pass"].usd == pytest.approx(1.75)
    assert by_node["editor_pass"].complete is False


# ---------------------------------------------------------------------------
# LLM-I/O share
# ---------------------------------------------------------------------------

def test_llm_share_union_vs_sum_under_concurrency():
    """Three concurrent 8s calls inside a 10s run: union 8s (80%), sum 24s (240%)."""
    trace = trace_of(
        [
            span("run", kind="run", start=0.0, duration_ms=10_000.0),
            span("panel", parent="run", start=0.0, duration_ms=9_000.0),
            *[
                llm(f"l{i}", parent="panel", start=0.0, duration_ms=8_000.0)
                for i in range(3)
            ],
        ]
    )
    share = M.llm_io_share(trace)
    assert share.call_count == 3
    assert share.run_wall_ms == pytest.approx(10_000.0)
    assert share.union_ms == pytest.approx(8_000.0)
    assert share.sum_ms == pytest.approx(24_000.0)
    assert share.union_share == pytest.approx(0.8)
    assert share.sum_share == pytest.approx(2.4)


def test_merge_intervals():
    assert M.merge_intervals([(0, 1), (0.5, 2), (3, 4)]) == [(0, 2), (3, 4)]
    assert M.union_seconds([(0, 1), (0, 1), (0, 1)]) == pytest.approx(1.0)
    assert M.merge_intervals([(1, 1)]) == []  # zero-length intervals contribute nothing

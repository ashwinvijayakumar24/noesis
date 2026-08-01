"""Tracing/labelling instrumentation of the draft-analysis LangGraph.

Nothing here touches the network, an LLM or a database: every node is replaced
with a trivial coroutine at the graph's own injection point, so what is under
test is the instrumentation, not the nodes.

The load-bearing test is :class:`TestReviewerFanOut` -- the three reviewer
branches cross a ``Send`` boundary, and without explicit context propagation
they come out as three orphaned trace roots instead of three siblings.
"""

import json
from unittest.mock import AsyncMock

import pytest

from app.core import llm_budget
from app.core import tracing
from app.core.tracing import (
    SpanKind,
    TRACE_CONTEXT_KEY,
    TracingAdapter,
    configure_tracing,
    reset_tracer,
)
from app.workflows.draft_analysis import graph as graph_module


# ---------------------------------------------------------------------------
# Stubbed graph
# ---------------------------------------------------------------------------

#: graph node name -> the module global holding its wrapper coroutine.
NODE_WRAPPERS = {
    "extract_structure": "_extract_structure_node_with_progress",
    "profile_manuscript": "_manuscript_profile_node_with_progress",
    "extract_references": "_extract_references_node_with_progress",
    "extract_claims": "_extract_claims_node_with_progress",
    "categorize_claims": "_categorize_claims_node_with_progress",
    "verify_citations": "_verify_citations_node_with_progress",
    "search_literature": "_literature_search_node_with_progress",
    "map_citations": "_citation_mapping_node_with_progress",
    "detect_gaps": "_detect_gaps_node_with_progress",
    "discover_external_sources": "_external_source_discovery_node_with_progress",
    "citation_judge_node": "_citation_judge_node_with_progress",
    "run_quality_diagnostics": "_diagnostic_findings_node_with_progress",
    "structural_checks": "_structural_checks_node_with_progress",
    "editor_pass_node": "_editor_pass_node_with_progress",
    "reviewer_panel_node": "_reviewer_panel_node_with_progress",
    "reviewer_judge_node": "_reviewer_judge_node_with_progress",
    "meta_reviewer_node": "_meta_reviewer_node_with_progress",
    "synthesize_report": "_synthesize_report_node_with_progress",
}


def _make_stub(node_name, seen, extra=None, raises=None):
    async def stub(state):
        seen.append((node_name, dict(state)))
        if raises is not None:
            raise raises
        if extra and node_name in extra:
            return extra[node_name](state)
        if node_name == "editor_pass_node":
            return {"editor_decision": {"proceed_to_review": True}}
        if node_name == "reviewer_panel_node":
            return {"reviewer_outputs": [{"reviewer_type": state.get("reviewer_type")}]}
        return {}

    stub.__name__ = f"stub_{node_name}"
    return stub


@pytest.fixture
def stub_graph(monkeypatch):
    """Replace every node with a stub and return (build_workflow, seen)."""
    # The preliminary publish-gate halt would short-circuit the fan-out on a
    # state with no anchors; this is exactly the escape hatch it ships with.
    monkeypatch.setenv("EVAL_DISABLE_PRE_REVIEWER_HALT", "1")
    monkeypatch.delenv("EVAL_STATE_DIR", raising=False)
    # run_draft_analysis_workflow publishes two progress events of its own; keep
    # Redis out of the test.
    monkeypatch.setattr(graph_module, "publish_progress", AsyncMock())

    seen = []

    def build(extra=None, raises_in=None):
        for node_name, attr in NODE_WRAPPERS.items():
            raises = raises_in.get(node_name) if raises_in else None
            monkeypatch.setattr(
                graph_module, attr, _make_stub(node_name, seen, extra, raises)
            )
        return graph_module.create_draft_analysis_workflow()

    return build, seen


def _initial_state():
    return {
        "draft_id": "draft-1",
        "project_id": "proj-1",
        "user_id": "user-1",
        "draft_content": "hello",
        "reviewer_outputs": [],
    }


@pytest.fixture
def jsonl_traces(tmp_path):
    """Configure the jsonl adapter; yields a reader for the emitted spans."""
    path = tmp_path / "traces.jsonl"
    configure_tracing(backend="jsonl", file_path=str(path))

    def read():
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

    try:
        yield read
    finally:
        reset_tracer()


def _by_name(spans, name):
    return [s for s in spans if s["name"] == name]


# ---------------------------------------------------------------------------
# Backend unset
# ---------------------------------------------------------------------------

class TestTracingDisabled:

    async def test_run_is_unchanged_and_no_spans_emitted(self, stub_graph, tmp_path, monkeypatch):
        monkeypatch.delenv("NOESIS_TRACING_BACKEND", raising=False)
        sink = tmp_path / "should-not-exist.jsonl"
        monkeypatch.setenv("NOESIS_TRACING_FILE", str(sink))
        reset_tracer()
        try:
            build, seen = stub_graph
            workflow = build()
            final = await workflow.ainvoke(_initial_state())

            assert tracing.get_tracer().enabled is False
            assert not sink.exists()
            # Same behaviour as before instrumentation: every node ran, the
            # fan-out still produced three reviewer outputs.
            assert [n for n, _ in seen].count("reviewer_panel_node") == 3
            assert len(final["reviewer_outputs"]) == 3
        finally:
            reset_tracer()


# ---------------------------------------------------------------------------
# Span tree
# ---------------------------------------------------------------------------

class TestSpanTree:

    async def test_one_run_span_and_one_node_span_per_executed_node(
        self, stub_graph, jsonl_traces
    ):
        build, seen = stub_graph
        build()
        await graph_module.run_draft_analysis_workflow(
            draft_id="draft-1",
            project_id="proj-1",
            user_id="user-1",
            draft_content="hello",
            checkpoint_enabled=False,
            analysis_run_id="run-42",
        )

        spans = jsonl_traces()
        runs = [s for s in spans if s["kind"] == SpanKind.RUN]
        assert len(runs) == 1
        assert runs[0]["attributes"][tracing.NOESIS_RUN_ID] == "run-42"
        assert runs[0]["attributes"][tracing.NOESIS_DRAFT_ID] == "draft-1"
        assert runs[0]["parent_span_id"] is None

        nodes = [s for s in spans if s["kind"] == SpanKind.NODE]
        executed = [n for n, _ in seen]
        assert len(nodes) == len(executed)
        assert {s["name"] for s in nodes} == set(executed)

        for span in spans:
            assert span["duration_ms"] is not None
            assert span["duration_ms"] > 0
            assert span["trace_id"] == runs[0]["trace_id"]

        # Every node hangs off the run, directly or through the fan-out parent.
        assert all(n["parent_span_id"] is not None for n in nodes)

    async def test_linear_nodes_parent_directly_to_the_run_span(
        self, stub_graph, jsonl_traces
    ):
        build, _ = stub_graph
        build()
        await graph_module.run_draft_analysis_workflow(
            draft_id="draft-1",
            project_id="proj-1",
            user_id="user-1",
            draft_content="hello",
            checkpoint_enabled=False,
        )
        spans = jsonl_traces()
        run = [s for s in spans if s["kind"] == SpanKind.RUN][0]
        first = _by_name(spans, "extract_structure")[0]
        assert first["parent_span_id"] == run["span_id"]


# ---------------------------------------------------------------------------
# The fan-out
# ---------------------------------------------------------------------------

class TestReviewerFanOut:

    async def test_three_reviewer_spans_are_siblings_of_one_parent(
        self, stub_graph, jsonl_traces
    ):
        build, _ = stub_graph
        build()
        await graph_module.run_draft_analysis_workflow(
            draft_id="draft-1",
            project_id="proj-1",
            user_id="user-1",
            draft_content="hello",
            checkpoint_enabled=False,
        )

        spans = jsonl_traces()
        reviewers = _by_name(spans, "reviewer_panel_node")
        assert len(reviewers) == 3

        # One shared parent, one shared trace, three distinct span ids.
        assert len({r["parent_span_id"] for r in reviewers}) == 1
        assert reviewers[0]["parent_span_id"] is not None
        assert len({r["trace_id"] for r in reviewers}) == 1
        assert len({r["span_id"] for r in reviewers}) == 3

        # No child is another child's parent -- that would be a chain, not a fan-out.
        child_ids = {r["span_id"] for r in reviewers}
        assert not (child_ids & {r["parent_span_id"] for r in reviewers})

        # Each branch is tagged with the persona it ran as.
        assert {r["attributes"][graph_module.NOESIS_REVIEWER_TYPE] for r in reviewers} == set(
            graph_module.REVIEWER_TYPES
        )

    def test_send_site_does_not_mutate_the_live_state(self, monkeypatch):
        """inject_context mutates in place; the Send payload must be a fresh copy."""
        monkeypatch.setenv("EVAL_DISABLE_PRE_REVIEWER_HALT", "1")
        configure_tracing(backend="jsonl", file_path="/dev/null")
        try:
            state = {
                "draft_id": "d",
                "editor_decision": {"proceed_to_review": True},
                "claims_with_citations": [],
            }
            before = dict(state)
            with tracing.start_span("parent", kind=SpanKind.RUN) as parent:
                sends = graph_module.route_to_reviewer_panel(state)

            assert state == before
            assert TRACE_CONTEXT_KEY not in state
            assert len(sends) == 3
            for send in sends:
                assert send.arg[TRACE_CONTEXT_KEY] == parent.context.to_dict()
        finally:
            reset_tracer()


# ---------------------------------------------------------------------------
# State hygiene
# ---------------------------------------------------------------------------

class TestStateHygiene:

    async def test_trace_key_reaches_reviewers_but_never_enters_state(
        self, stub_graph, jsonl_traces
    ):
        build, seen = stub_graph
        build()
        final = await graph_module.run_draft_analysis_workflow(
            draft_id="draft-1",
            project_id="proj-1",
            user_id="user-1",
            draft_content="hello",
            checkpoint_enabled=False,
        )

        by_node = {}
        for name, state in seen:
            by_node.setdefault(name, []).append(state)

        # It arrives in the Send payload...
        assert all(TRACE_CONTEXT_KEY in s for s in by_node["reviewer_panel_node"])
        # ...and LangGraph confines it there: it is not a declared channel, so it
        # never reaches a downstream node and never lands in the final state.
        assert TRACE_CONTEXT_KEY not in by_node["reviewer_judge_node"][0]
        assert TRACE_CONTEXT_KEY not in by_node["synthesize_report"][0]
        assert TRACE_CONTEXT_KEY not in final

        # Nor into the published artifact channel.
        assert final["reviewer_outputs"]
        for output in final["reviewer_outputs"]:
            assert TRACE_CONTEXT_KEY not in output


# ---------------------------------------------------------------------------
# Token attribution
# ---------------------------------------------------------------------------

class TestTokenAttribution:

    async def test_usage_recorded_in_a_node_attributes_to_that_node(
        self, stub_graph, jsonl_traces
    ):
        llm_budget.reset()

        def spend(state):
            llm_budget.record_usage(
                model="gpt-5.2", prompt_tokens=100, completion_tokens=20
            )
            return {}

        build, _ = stub_graph
        workflow = build(extra={"detect_gaps": spend})
        await workflow.ainvoke(_initial_state())

        labels = llm_budget.by_label()
        assert "detect_gaps" in labels, sorted(labels)
        assert labels["detect_gaps"]["prompt_tokens"] == 100
        assert labels["detect_gaps"]["completion_tokens"] == 20
        # The model name fallback must not have won.
        assert "gpt-5.2" not in labels
        llm_budget.reset()

    async def test_parallel_reviewers_do_not_leak_labels_to_each_other(
        self, stub_graph, jsonl_traces
    ):
        llm_budget.reset()

        def spend(state):
            llm_budget.record_usage(model="gpt-5.2", prompt_tokens=1, completion_tokens=1)
            return {"reviewer_outputs": [{"reviewer_type": state.get("reviewer_type")}]}

        build, _ = stub_graph
        workflow = build(extra={"reviewer_panel_node": spend})
        await workflow.ainvoke(_initial_state())

        labels = llm_budget.by_label()
        assert labels["reviewer_panel_node"]["calls"] == 3
        llm_budget.reset()


# ---------------------------------------------------------------------------
# Failure paths
# ---------------------------------------------------------------------------

class TestFailurePaths:

    async def test_node_exception_propagates_unchanged_and_is_recorded(
        self, stub_graph, jsonl_traces
    ):
        boom = ValueError("citation mapping blew up")
        build, _ = stub_graph
        workflow = build(raises_in={"map_citations": boom})

        with pytest.raises(ValueError) as excinfo:
            await workflow.ainvoke(_initial_state())
        assert excinfo.value is boom

        spans = _by_name(jsonl_traces(), "map_citations")
        assert len(spans) == 1
        assert spans[0]["status"] == tracing.STATUS_ERROR
        assert spans[0]["attributes"][tracing.EXCEPTION_TYPE] == "ValueError"
        assert "blew up" in spans[0]["attributes"][tracing.EXCEPTION_MESSAGE]
        assert spans[0]["duration_ms"] > 0

    async def test_a_broken_tracing_backend_does_not_break_the_run(self, stub_graph):
        class ExplodingAdapter(TracingAdapter):
            name = "exploding"

            def on_start(self, span):
                raise RuntimeError("sink is on fire")

            def on_end(self, span):
                raise RuntimeError("sink is still on fire")

        configure_tracing(adapter=ExplodingAdapter())
        try:
            build, seen = stub_graph
            workflow = build()
            final = await workflow.ainvoke(_initial_state())
            assert len(final["reviewer_outputs"]) == 3
            assert [n for n, _ in seen].count("reviewer_panel_node") == 3
        finally:
            reset_tracer()

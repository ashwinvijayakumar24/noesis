"""Tests for app/core/tracing.py.

Everything here is a synthetic harness -- the tracing module is deliberately
not wired into the graph yet, so the fan-out test reproduces the *shape* of the
``Send``-based reviewer fan-out (a payload dict crossing a real thread
boundary) rather than importing the graph.
"""

import asyncio
import builtins
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core import tracing
from app.core.tracing import (
    EXCEPTION_MESSAGE,
    EXCEPTION_TYPE,
    GEN_AI_REQUEST_MODEL,
    GEN_AI_SYSTEM,
    GEN_AI_USAGE_INPUT_TOKENS,
    GEN_AI_USAGE_OUTPUT_TOKENS,
    NOESIS_CACHED_INPUT_TOKENS,
    NOESIS_ESTIMATED_COST_USD,
    NOESIS_RETRIEVAL_DOCUMENT_IDS,
    NOESIS_RETRIEVAL_RETURNED_COUNT,
    NOESIS_RETRIEVAL_TOP_K,
    STATUS_ERROR,
    STATUS_OK,
    JsonlAdapter,
    NoopAdapter,
    Span,
    SpanContext,
    SpanKind,
    Tracer,
    TracingAdapter,
    configure_tracing,
    current_span_context,
    extract_context,
    get_tracer,
    inject_context,
    llm_call_attributes,
    reset_tracer,
    retrieval_attributes,
    run_attributes,
    use_context,
)


@pytest.fixture(autouse=True)
def _clean_tracer():
    """Never let one test's process-wide tracer leak into the next."""
    reset_tracer()
    yield
    reset_tracer()


def read_spans(path) -> list[dict]:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


# ---------------------------------------------------------------------------
# noop adapter
# ---------------------------------------------------------------------------

def test_noop_is_the_default_when_env_unset(monkeypatch):
    monkeypatch.delenv("NOESIS_TRACING_BACKEND", raising=False)
    tracer = get_tracer()
    assert isinstance(tracer.adapter, NoopAdapter)
    assert tracer.enabled is False


def test_noop_produces_no_output_and_does_not_crash(monkeypatch, capsys, tmp_path):
    monkeypatch.delenv("NOESIS_TRACING_BACKEND", raising=False)
    monkeypatch.setenv("NOESIS_TRACING_FILE", str(tmp_path / "should_not_exist.jsonl"))

    with tracing.start_span("run", kind=SpanKind.RUN) as span:
        span.set_attribute("x", 1)
        with tracing.start_span("child", kind=SpanKind.NODE):
            pass

    assert not (tmp_path / "should_not_exist.jsonl").exists()
    captured = capsys.readouterr()
    assert captured.out == ""


def test_noop_overhead_is_small(monkeypatch):
    """Rough guard, not a benchmark: a noop span must be microsecond-scale."""
    monkeypatch.delenv("NOESIS_TRACING_BACKEND", raising=False)
    get_tracer()

    iterations = 20_000
    start = time.perf_counter()
    for _ in range(iterations):
        with tracing.start_span("n", kind=SpanKind.NODE):
            pass
    per_span_us = (time.perf_counter() - start) / iterations * 1e6

    # Generous ceiling so this is not flaky on a loaded machine; the real
    # measured value is roughly 5-10us. A regression to milliseconds fails.
    assert per_span_us < 200, f"noop span overhead {per_span_us:.1f}us is too high"


def test_unknown_backend_degrades_to_noop(monkeypatch, caplog):
    monkeypatch.setenv("NOESIS_TRACING_BACKEND", "datadog")
    with caplog.at_level("WARNING"):
        tracer = get_tracer()
    assert isinstance(tracer.adapter, NoopAdapter)
    assert "unknown NOESIS_TRACING_BACKEND" in caplog.text


# ---------------------------------------------------------------------------
# jsonl adapter
# ---------------------------------------------------------------------------

def test_jsonl_writes_one_valid_json_object_per_span(monkeypatch, tmp_path):
    path = tmp_path / "traces.jsonl"
    monkeypatch.setenv("NOESIS_TRACING_BACKEND", "jsonl")
    monkeypatch.setenv("NOESIS_TRACING_FILE", str(path))

    with tracing.start_span("run", kind=SpanKind.RUN, attributes=run_attributes(
        analysis_run_id="run-1", draft_id="draft-9"
    )):
        with tracing.start_span("extract_structure", kind=SpanKind.NODE):
            pass

    spans = read_spans(path)
    assert len(spans) == 2
    for span in spans:
        assert set(span) >= {
            "name", "kind", "trace_id", "span_id", "parent_span_id",
            "status", "start_time", "end_time", "duration_ms", "attributes",
        }
    # Child closes first, root last.
    assert [s["name"] for s in spans] == ["extract_structure", "run"]


def test_jsonl_records_timing(monkeypatch, tmp_path):
    path = tmp_path / "traces.jsonl"
    monkeypatch.setenv("NOESIS_TRACING_BACKEND", "jsonl")
    monkeypatch.setenv("NOESIS_TRACING_FILE", str(path))

    with tracing.start_span("slow", kind=SpanKind.NODE):
        time.sleep(0.02)

    span = read_spans(path)[0]
    assert span["duration_ms"] >= 15.0
    assert span["end_time"] >= span["start_time"]
    assert span["status"] == STATUS_OK


def test_jsonl_captures_nesting_via_parent_ids(monkeypatch, tmp_path):
    path = tmp_path / "traces.jsonl"
    monkeypatch.setenv("NOESIS_TRACING_BACKEND", "jsonl")
    monkeypatch.setenv("NOESIS_TRACING_FILE", str(path))

    with tracing.start_span("run", kind=SpanKind.RUN) as root:
        with tracing.start_span("node", kind=SpanKind.NODE) as node:
            with tracing.start_span("llm", kind=SpanKind.LLM_CALL) as llm:
                pass

    by_name = {s["name"]: s for s in read_spans(path)}
    assert by_name["run"]["parent_span_id"] is None
    assert by_name["node"]["parent_span_id"] == root.span_id
    assert by_name["llm"]["parent_span_id"] == node.span_id
    # One trace id for the whole tree.
    assert len({s["trace_id"] for s in by_name.values()}) == 1
    assert llm.trace_id == root.trace_id


def test_jsonl_appends_rather_than_truncates(monkeypatch, tmp_path):
    path = tmp_path / "traces.jsonl"
    path.write_text('{"name": "preexisting"}\n', encoding="utf-8")
    monkeypatch.setenv("NOESIS_TRACING_BACKEND", "jsonl")
    monkeypatch.setenv("NOESIS_TRACING_FILE", str(path))

    with tracing.start_span("first", kind=SpanKind.NODE):
        pass
    # A second tracer instance (simulating a second process/run) must also append.
    reset_tracer()
    with tracing.start_span("second", kind=SpanKind.NODE):
        pass

    names = [s["name"] for s in read_spans(path)]
    assert names == ["preexisting", "first", "second"]


def test_jsonl_unwritable_path_logs_and_continues(tmp_path, caplog):
    # A directory is never writable as a file.
    bad_dir = tmp_path / "iam_a_directory"
    bad_dir.mkdir()
    configure_tracing(backend="jsonl", file_path=str(bad_dir))

    with caplog.at_level("WARNING"):
        with tracing.start_span("node", kind=SpanKind.NODE) as span:
            span.set_attribute("still", "works")
        with tracing.start_span("node2", kind=SpanKind.NODE):
            pass

    assert "not writable" in caplog.text
    # Warned exactly once, not once per span.
    assert caplog.text.count("not writable") == 1


def test_jsonl_metrics_are_computable_from_the_file_alone(monkeypatch, tmp_path):
    """The jsonl adapter must stand on its own: p50/p95, tokens, cost."""
    path = tmp_path / "traces.jsonl"
    monkeypatch.setenv("NOESIS_TRACING_BACKEND", "jsonl")
    monkeypatch.setenv("NOESIS_TRACING_FILE", str(path))

    for tokens in (100, 200, 300):
        with tracing.start_span("reviewer_panel", kind=SpanKind.NODE):
            with tracing.start_span(
                "chat",
                kind=SpanKind.LLM_CALL,
                attributes=llm_call_attributes(
                    model="gpt-5.2",
                    prompt_tokens=tokens,
                    completion_tokens=10,
                    estimated_usd=0.5,
                ),
            ):
                pass

    spans = read_spans(path)
    node_durations = sorted(s["duration_ms"] for s in spans if s["kind"] == "node")
    assert len(node_durations) == 3
    assert node_durations[1] >= 0  # p50 computable

    llm_spans = [s for s in spans if s["kind"] == "llm_call"]
    total_input = sum(s["attributes"][GEN_AI_USAGE_INPUT_TOKENS] for s in llm_spans)
    total_cost = sum(s["attributes"][NOESIS_ESTIMATED_COST_USD] for s in llm_spans)
    assert total_input == 600
    assert total_cost == pytest.approx(1.5)


# ---------------------------------------------------------------------------
# THE FAN-OUT TEST -- the important one
# ---------------------------------------------------------------------------

REVIEWER_TYPES = ("methodology", "novelty", "clarity")


def test_send_fanout_across_real_threads_shares_one_parent(monkeypatch, tmp_path):
    """Reproduce the ``Send`` fan-out: 3 branches, real threads, one parent.

    Real threads are used on purpose -- ``async_utils.run_coroutine_sync``
    spawns a plain ``threading.Thread`` per call, and contextvars do NOT
    propagate into one. This is the actual failure mode, so the test must
    exercise it rather than assume implicit propagation works.
    """
    path = tmp_path / "traces.jsonl"
    monkeypatch.setenv("NOESIS_TRACING_BACKEND", "jsonl")
    monkeypatch.setenv("NOESIS_TRACING_FILE", str(path))

    child_contexts: list[SpanContext] = []
    lock = threading.Lock()

    def reviewer_branch(payload: dict) -> None:
        # Far side of the thread boundary: no ambient context here at all.
        assert current_span_context() is None
        with use_context(extract_context(payload)):
            with tracing.start_span(
                f"reviewer_panel:{payload['reviewer_type']}", kind=SpanKind.NODE
            ) as child:
                with lock:
                    child_contexts.append(
                        SpanContext(child.trace_id, child.span_id)
                    )
                    child.set_attribute("parent", child.parent_span_id)

    with tracing.start_span("editor_pass", kind=SpanKind.NODE) as parent:
        # Exactly the shape of `Send("reviewer_panel_node", {**state, ...})`.
        payloads = [
            inject_context({"draft_id": "d1", "reviewer_type": rt})
            for rt in REVIEWER_TYPES
        ]
        threads = [
            threading.Thread(target=reviewer_branch, args=(p,)) for p in payloads
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    assert len(child_contexts) == 3
    spans = {s["name"]: s for s in read_spans(path)}
    children = [spans[f"reviewer_panel:{rt}"] for rt in REVIEWER_TYPES]

    # All three nest under the SAME parent...
    assert {c["parent_span_id"] for c in children} == {parent.span_id}
    # ...and share the root's trace id...
    assert {c["trace_id"] for c in children} == {parent.trace_id}
    # ...but are distinct spans, not nested under each other.
    child_ids = [c["span_id"] for c in children]
    assert len(set(child_ids)) == 3
    assert not set(child_ids) & {c["parent_span_id"] for c in children}


def test_send_fanout_across_asyncio_tasks_shares_one_parent(monkeypatch, tmp_path):
    """Same invariant when the branches are asyncio tasks instead of threads."""
    path = tmp_path / "traces.jsonl"
    monkeypatch.setenv("NOESIS_TRACING_BACKEND", "jsonl")
    monkeypatch.setenv("NOESIS_TRACING_FILE", str(path))

    async def reviewer_branch(payload: dict) -> None:
        with use_context(extract_context(payload)):
            with tracing.start_span(
                f"async_reviewer:{payload['reviewer_type']}", kind=SpanKind.NODE
            ):
                await asyncio.sleep(0.005)

    async def driver() -> str:
        with tracing.start_span("editor_pass", kind=SpanKind.NODE) as parent:
            payloads = [
                inject_context({"reviewer_type": rt}) for rt in REVIEWER_TYPES
            ]
            await asyncio.gather(*(reviewer_branch(p) for p in payloads))
            return parent.span_id

    parent_id = asyncio.run(driver())

    spans = {s["name"]: s for s in read_spans(path)}
    children = [spans[f"async_reviewer:{rt}"] for rt in REVIEWER_TYPES]
    assert {c["parent_span_id"] for c in children} == {parent_id}
    assert len({c["span_id"] for c in children}) == 3


def test_fanout_without_explicit_context_would_orphan_the_branches(monkeypatch, tmp_path):
    """Documents *why* the explicit mechanism exists.

    Relying on implicit contextvar propagation across a plain Thread loses the
    parent entirely -- three orphaned roots instead of three siblings.
    """
    path = tmp_path / "traces.jsonl"
    monkeypatch.setenv("NOESIS_TRACING_BACKEND", "jsonl")
    monkeypatch.setenv("NOESIS_TRACING_FILE", str(path))

    def naive_branch(rt: str) -> None:
        with tracing.start_span(f"naive:{rt}", kind=SpanKind.NODE):
            pass

    with tracing.start_span("editor_pass", kind=SpanKind.NODE):
        with ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(naive_branch, REVIEWER_TYPES))

    naive = [s for s in read_spans(path) if s["name"].startswith("naive:")]
    assert len(naive) == 3
    assert all(s["parent_span_id"] is None for s in naive)
    # And each becomes its own trace -- unjoinable.
    assert len({s["trace_id"] for s in naive}) == 3


def test_run_coroutine_sync_thread_hop_is_survivable(monkeypatch, tmp_path):
    """The real helper: capture context before the hop, restore inside it."""
    from app.services.async_utils import run_coroutine_sync

    path = tmp_path / "traces.jsonl"
    monkeypatch.setenv("NOESIS_TRACING_BACKEND", "jsonl")
    monkeypatch.setenv("NOESIS_TRACING_FILE", str(path))

    with tracing.start_span("caller", kind=SpanKind.NODE) as parent:
        captured = current_span_context()

        async def work() -> None:
            with use_context(captured):
                with tracing.start_span("in_thread", kind=SpanKind.LLM_CALL):
                    pass

        run_coroutine_sync(work())

    spans = {s["name"]: s for s in read_spans(path)}
    assert spans["in_thread"]["parent_span_id"] == parent.span_id
    assert spans["in_thread"]["trace_id"] == parent.trace_id


def test_context_roundtrip_is_json_serializable():
    ctx = SpanContext(trace_id="t", span_id="s")
    payload = inject_context({"a": 1}, ctx)
    revived = json.loads(json.dumps(payload))
    assert extract_context(revived) == ctx


def test_extract_context_tolerates_missing_or_malformed_payloads():
    assert extract_context(None) is None
    assert extract_context({}) is None
    assert extract_context("not a dict") is None
    assert extract_context({tracing.TRACE_CONTEXT_KEY: {"trace_id": "t"}}) is None


def test_inject_context_with_no_active_span_is_a_noop():
    payload = inject_context({"a": 1})
    assert payload == {"a": 1}


# ---------------------------------------------------------------------------
# Failure containment
# ---------------------------------------------------------------------------

class ExplodingAdapter(TracingAdapter):
    name = "exploding"

    def __init__(self):
        self.starts = 0
        self.ends = 0

    def on_start(self, span):
        self.starts += 1
        raise RuntimeError("adapter start blew up")

    def on_end(self, span):
        self.ends += 1
        raise RuntimeError("adapter end blew up")


def test_adapter_that_raises_does_not_propagate_to_caller(caplog):
    adapter = ExplodingAdapter()
    configure_tracing(adapter=adapter)

    with caplog.at_level("WARNING"):
        with tracing.start_span("node", kind=SpanKind.NODE) as span:
            span.set_attribute("work", "still done")
        # Caller reached this line: nothing propagated.
        result = 42

    assert result == 42
    assert adapter.starts == 1 and adapter.ends == 1
    assert "adapter start blew up" in caplog.text
    assert "adapter end blew up" in caplog.text


def test_adapter_flush_that_raises_is_contained(caplog):
    class BadFlush(TracingAdapter):
        def flush(self):
            raise RuntimeError("flush blew up")

    tracer = configure_tracing(adapter=BadFlush())
    with caplog.at_level("WARNING"):
        tracer.flush()
    assert "flush raised" in caplog.text


def test_caller_exception_is_recorded_and_re_raised(monkeypatch, tmp_path):
    path = tmp_path / "traces.jsonl"
    monkeypatch.setenv("NOESIS_TRACING_BACKEND", "jsonl")
    monkeypatch.setenv("NOESIS_TRACING_FILE", str(path))

    class ReviewerTimeout(ValueError):
        pass

    with pytest.raises(ReviewerTimeout):
        with tracing.start_span("reviewer", kind=SpanKind.NODE):
            raise ReviewerTimeout("panel took too long")

    span = read_spans(path)[0]
    assert span["status"] == STATUS_ERROR
    # Exception TYPE preserved, not flattened to "Exception".
    assert span["attributes"][EXCEPTION_TYPE] == "ReviewerTimeout"
    assert span["attributes"][EXCEPTION_MESSAGE] == "panel took too long"
    assert "ReviewerTimeout" in span["attributes"][tracing.EXCEPTION_STACKTRACE]
    # Timing still recorded on the failure path.
    assert span["duration_ms"] is not None


def test_explicit_record_error_marks_span_without_raising(monkeypatch, tmp_path):
    path = tmp_path / "traces.jsonl"
    monkeypatch.setenv("NOESIS_TRACING_BACKEND", "jsonl")
    monkeypatch.setenv("NOESIS_TRACING_FILE", str(path))

    with tracing.start_span("retrieval", kind=SpanKind.RETRIEVAL) as span:
        try:
            raise KeyError("missing_manifest")
        except KeyError as exc:
            span.record_error(exc)

    written = read_spans(path)[0]
    assert written["status"] == STATUS_ERROR
    assert written["attributes"][EXCEPTION_TYPE] == "KeyError"


# ---------------------------------------------------------------------------
# langfuse / otel degradation (never touches a real client)
# ---------------------------------------------------------------------------

def _block_import(monkeypatch, blocked_prefix: str):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == blocked_prefix or name.startswith(blocked_prefix + "."):
            raise ImportError(f"No module named '{blocked_prefix}'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)


def test_langfuse_backend_degrades_to_noop_when_not_importable(monkeypatch, caplog):
    _block_import(monkeypatch, "langfuse")
    monkeypatch.setenv("NOESIS_TRACING_BACKEND", "langfuse")

    with caplog.at_level("WARNING"):
        tracer = get_tracer()
        with tracing.start_span("node", kind=SpanKind.NODE):
            pass

    assert isinstance(tracer.adapter, NoopAdapter)
    assert "langfuse" in caplog.text.lower()
    assert "falling back to noop" in caplog.text


def test_otel_backend_degrades_to_noop_when_not_importable(monkeypatch, caplog):
    _block_import(monkeypatch, "opentelemetry")
    monkeypatch.setenv("NOESIS_TRACING_BACKEND", "otel")

    with caplog.at_level("WARNING"):
        tracer = get_tracer()
        with tracing.start_span("node", kind=SpanKind.NODE):
            pass

    assert isinstance(tracer.adapter, NoopAdapter)
    assert "opentelemetry" in caplog.text
    assert "falling back to noop" in caplog.text


def test_langfuse_is_not_a_declared_dependency():
    """Guard: this lane must not have added langfuse to requirements."""
    req = Path(__file__).resolve().parents[1] / "requirements.txt"
    if not req.exists():
        pytest.skip("no requirements.txt")
    declared = [
        line.strip().lower()
        for line in req.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    assert not any(line.startswith("langfuse") for line in declared)
    assert not any(line.startswith("opentelemetry") for line in declared)


def test_langfuse_adapter_bridges_to_a_fake_client():
    """Exercise the adapter's own logic with a stand-in, never a real client."""

    class FakeHandle:
        def __init__(self):
            self.ended = None

        def end(self, **kwargs):
            self.ended = kwargs

    class FakeClient:
        def __init__(self):
            self.spans = []
            self.handles = []
            self.flushed = False

        def span(self, **kwargs):
            self.spans.append(kwargs)
            handle = FakeHandle()
            self.handles.append(handle)
            return handle

        def flush(self):
            self.flushed = True

    client = FakeClient()
    tracer = configure_tracing(adapter=tracing.LangfuseAdapter(client))
    with tracer.start_span("node", kind=SpanKind.NODE, attributes={"a": 1}) as span:
        pass
    tracer.flush()

    assert client.spans[0]["name"] == "node"
    assert client.spans[0]["id"] == span.span_id
    assert client.spans[0]["metadata"]["kind"] == "node"
    assert client.handles[0].ended is not None
    assert client.flushed is True


def test_otel_adapter_bridges_to_a_fake_tracer():
    class FakeOtelSpan:
        def __init__(self):
            self.attrs = {}
            self.ended = False

        def set_attribute(self, key, value):
            self.attrs[key] = value

        def end(self):
            self.ended = True

    class FakeOtelTracer:
        def __init__(self):
            self.spans = []

        def start_span(self, name):
            span = FakeOtelSpan()
            span.name = name
            self.spans.append(span)
            return span

    fake = FakeOtelTracer()
    tracer = configure_tracing(adapter=tracing.OtelAdapter(fake))
    with tracer.start_span(
        "llm", kind=SpanKind.LLM_CALL,
        attributes=llm_call_attributes(model="gpt-5.2", prompt_tokens=5),
    ):
        pass

    otel_span = fake.spans[0]
    assert otel_span.ended is True
    assert otel_span.attrs[GEN_AI_REQUEST_MODEL] == "gpt-5.2"
    assert otel_span.attrs["noesis.span.kind"] == "llm_call"


# ---------------------------------------------------------------------------
# GenAI attribute naming
# ---------------------------------------------------------------------------

def test_genai_attribute_names_are_emitted_exactly(monkeypatch, tmp_path):
    path = tmp_path / "traces.jsonl"
    monkeypatch.setenv("NOESIS_TRACING_BACKEND", "jsonl")
    monkeypatch.setenv("NOESIS_TRACING_FILE", str(path))

    attrs = llm_call_attributes(
        model="gpt-5.2",
        prompt_tokens=1200,
        completion_tokens=340,
        cached_tokens=800,
        estimated_usd=0.0123,
        temperature=0.2,
        max_tokens=4096,
        response_model="gpt-5.2-2026-01-01",
        finish_reasons=["stop"],
    )
    with tracing.start_span("chat", kind=SpanKind.LLM_CALL, attributes=attrs):
        pass

    written = read_spans(path)[0]["attributes"]
    assert written["gen_ai.system"] == "openai"
    assert written["gen_ai.operation.name"] == "chat"
    assert written["gen_ai.request.model"] == "gpt-5.2"
    assert written["gen_ai.request.temperature"] == 0.2
    assert written["gen_ai.request.max_tokens"] == 4096
    assert written["gen_ai.response.model"] == "gpt-5.2-2026-01-01"
    assert written["gen_ai.response.finish_reasons"] == ["stop"]
    assert written["gen_ai.usage.input_tokens"] == 1200
    assert written["gen_ai.usage.output_tokens"] == 340
    # Namespaced extensions, documented in the module docstring.
    assert written["noesis.gen_ai.usage.cached_input_tokens"] == 800
    assert written["noesis.gen_ai.usage.estimated_cost_usd"] == 0.0123


def test_llm_call_attributes_omits_unset_values_rather_than_zeroing():
    attrs = llm_call_attributes(model=None)
    assert attrs == {GEN_AI_SYSTEM: "openai", "gen_ai.operation.name": "chat"}
    assert GEN_AI_USAGE_INPUT_TOKENS not in attrs
    assert GEN_AI_USAGE_OUTPUT_TOKENS not in attrs
    assert NOESIS_CACHED_INPUT_TOKENS not in attrs


def test_retrieval_attribute_names():
    attrs = retrieval_attributes(
        query="ablation study",
        top_k=8,
        document_ids=["doc-1", "doc-2"],
    )
    assert attrs["noesis.retrieval.query"] == "ablation study"
    assert attrs[NOESIS_RETRIEVAL_TOP_K] == 8
    assert attrs[NOESIS_RETRIEVAL_DOCUMENT_IDS] == ["doc-1", "doc-2"]
    # returned_count derived when not given -- the top_k/returned gap is the signal.
    assert attrs[NOESIS_RETRIEVAL_RETURNED_COUNT] == 2


def test_run_attribute_names():
    attrs = run_attributes(analysis_run_id="run-7", draft_id="draft-3")
    assert attrs["noesis.run.id"] == "run-7"
    assert attrs["noesis.draft.id"] == "draft-3"


def test_all_five_span_kinds_round_trip(monkeypatch, tmp_path):
    path = tmp_path / "traces.jsonl"
    monkeypatch.setenv("NOESIS_TRACING_BACKEND", "jsonl")
    monkeypatch.setenv("NOESIS_TRACING_FILE", str(path))

    for kind in SpanKind.ALL:
        with tracing.start_span(kind, kind=kind):
            pass

    assert [s["kind"] for s in read_spans(path)] == list(SpanKind.ALL)


def test_tracing_module_does_not_import_llm_budget():
    """Independent by design -- avoids a circular import between the two."""
    source = (Path(tracing.__file__)).read_text(encoding="utf-8")
    code_lines = [
        line for line in source.splitlines()
        if line.strip().startswith(("import ", "from "))
    ]
    assert not any("llm_budget" in line for line in code_lines)


def test_module_is_wired_into_the_graph():
    """Was a scope guard asserting NOTHING imported this module -- the module was
    built one wave before it was wired, and the guard kept those waves honest.

    It is now inverted rather than deleted: the graph is the consumer this module
    exists for, and an import silently disappearing (a bad merge, an over-eager
    cleanup of an "unused" import) would leave every span unrecorded while the
    whole suite stayed green. Tracing that quietly stops tracing is the failure
    mode worth a test.
    """
    backend_root = Path(__file__).resolve().parents[1] / "app"
    consumers = []
    for py in backend_root.rglob("*.py"):
        if py.name == "tracing.py":
            continue
        text = py.read_text(encoding="utf-8", errors="ignore")
        if "core.tracing" in text or "from .tracing" in text:
            consumers.append(py.name)
    assert "graph.py" in consumers, (
        f"draft_analysis graph no longer imports core.tracing; spans are silently "
        f"off. Current consumers: {consumers}"
    )

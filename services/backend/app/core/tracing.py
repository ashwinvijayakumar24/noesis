"""Backend-agnostic span tracing for the draft-analysis pipeline.

The pipeline is an 18-node LangGraph DAG with one genuine 3-way parallel
fan-out. Until now nothing measured it: progress percentages are hardcoded
constants, so "which node is slowest" and "what did this run cost" were
unanswerable. This module is the measurement primitive. It is deliberately
*not* wired into the graph -- integration is a separate change.

Design
------
* Five span kinds: ``run`` (root, keyed on ``analysis_run_id``), ``node``,
  ``llm_call``, ``retrieval``, ``tool``.
* Pluggable adapters selected by ``NOESIS_TRACING_BACKEND``:
  ``noop`` (default), ``jsonl``, ``langfuse``, ``otel``.
* **A tracing failure must never break the caller.** Every adapter call is
  wrapped; an adapter that raises is logged once and otherwise ignored.
* ``noop`` and ``jsonl`` are stdlib-only. ``jsonl`` is the guaranteed-to-work
  fallback and is self-sufficient: per-node p50/p95, token counts and cost are
  all computable from the JSONL alone, because every span line carries
  ``trace_id``/``span_id``/``parent_span_id``, ``duration_ms``, and its
  attributes.

Attribute naming
----------------
Where the OpenTelemetry GenAI semantic conventions define a term, that term is
used verbatim so the vocabulary transfers to any OTel-aware backend:

    gen_ai.system, gen_ai.operation.name, gen_ai.request.model,
    gen_ai.request.temperature, gen_ai.request.max_tokens,
    gen_ai.response.model, gen_ai.response.finish_reasons,
    gen_ai.usage.input_tokens, gen_ai.usage.output_tokens

Errors follow the OTel exception convention: ``exception.type``,
``exception.message``, ``exception.stacktrace``, plus ``status = "ERROR"``.

The conventions have **no** term for several things this pipeline cares about,
so those get a clearly-namespaced ``noesis.*`` name. The choice is documented
here rather than left implicit:

    noesis.gen_ai.usage.cached_input_tokens
        Prompt-cache hits. OTel has no cached-token attribute; the name mirrors
        the convention's ``gen_ai.usage.*`` shape so it reads as an extension
        rather than a competing vocabulary. Follows OpenAI's convention where
        cached tokens are a *subset* of input tokens, matching
        ``core.llm_budget.estimate_usd``.
    noesis.gen_ai.usage.estimated_cost_usd
        Cost is a derived, pricing-table-dependent number, not something OTel
        models. ``None`` means "pricing unknown", never "free" -- same contract
        as ``llm_budget.estimate_usd``.
    noesis.retrieval.top_k / .returned_count / .document_ids / .query
        OTel has no retrieval conventions at all. ``returned_count`` is kept
        separate from ``top_k`` on purpose: the gap between requested and
        returned is the signal that a top_k-fill floor did not fill.
    noesis.run.id, noesis.draft.id, noesis.node.name, noesis.tool.name
        Pipeline identifiers with no convention equivalent.

Cross-thread context propagation
--------------------------------
``app/services/async_utils.run_coroutine_sync`` runs each coroutine in a brand
new ``threading.Thread``. **contextvars do not propagate into a plain Thread**,
so implicit propagation silently loses the parent on the busiest path in the
codebase, and the ``Send``-based reviewer fan-out would produce three orphaned
roots instead of three siblings.

The fix is explicit and serializable. A ``SpanContext`` is just
``(trace_id, span_id)``; it can ride inside any payload dict -- including the
dict handed to ``langgraph.types.Send`` -- and be re-established on the far
side::

    with start_span("editor_pass", kind=SpanKind.NODE) as parent:
        payloads = [inject_context({**state, "reviewer_type": rt}) for rt in types]
        # ... each payload crosses a thread/task boundary ...

    # on the other side, inside the worker:
    with use_context(extract_context(payload)):
        with start_span("reviewer_panel", kind=SpanKind.NODE) as child:
            ...   # child.parent_span_id == parent.span_id, for all 3 workers

``use_context`` is also the escape hatch for any other thread hop: capture
``current_span_context()`` before the hop, restore it after.

Cooperation with ``core.llm_budget``
------------------------------------
This module does not import ``llm_budget`` (and ``llm_budget`` does not import
this) -- keeping them independent avoids a circular import and lets either be
used alone. They cooperate through data instead: ``llm_call_attributes()``
accepts the same ``(prompt, completion, cached)`` triple that
``llm_budget.extract_usage`` returns, and the same ``estimated_usd`` value, so
a caller that already records budget usage can feed the identical numbers to a
span with no second extraction.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import traceback
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Iterator, Mapping, Sequence

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Attribute name constants
# ---------------------------------------------------------------------------

# OpenTelemetry GenAI semantic conventions (used verbatim).
GEN_AI_SYSTEM = "gen_ai.system"
GEN_AI_OPERATION_NAME = "gen_ai.operation.name"
GEN_AI_REQUEST_MODEL = "gen_ai.request.model"
GEN_AI_REQUEST_TEMPERATURE = "gen_ai.request.temperature"
GEN_AI_REQUEST_MAX_TOKENS = "gen_ai.request.max_tokens"
GEN_AI_RESPONSE_MODEL = "gen_ai.response.model"
GEN_AI_RESPONSE_FINISH_REASONS = "gen_ai.response.finish_reasons"
GEN_AI_USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens"
GEN_AI_USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"

# OpenTelemetry exception conventions.
EXCEPTION_TYPE = "exception.type"
EXCEPTION_MESSAGE = "exception.message"
EXCEPTION_STACKTRACE = "exception.stacktrace"

# Noesis extensions (no convention exists -- see module docstring).
NOESIS_CACHED_INPUT_TOKENS = "noesis.gen_ai.usage.cached_input_tokens"
NOESIS_ESTIMATED_COST_USD = "noesis.gen_ai.usage.estimated_cost_usd"
NOESIS_RETRIEVAL_TOP_K = "noesis.retrieval.top_k"
NOESIS_RETRIEVAL_RETURNED_COUNT = "noesis.retrieval.returned_count"
NOESIS_RETRIEVAL_DOCUMENT_IDS = "noesis.retrieval.document_ids"
NOESIS_RETRIEVAL_QUERY = "noesis.retrieval.query"
NOESIS_RUN_ID = "noesis.run.id"
NOESIS_DRAFT_ID = "noesis.draft.id"
NOESIS_NODE_NAME = "noesis.node.name"
NOESIS_TOOL_NAME = "noesis.tool.name"

STATUS_OK = "OK"
STATUS_ERROR = "ERROR"

#: Key under which a serialized :class:`SpanContext` rides inside a payload dict.
TRACE_CONTEXT_KEY = "_noesis_span_context"


class SpanKind:
    """The five span kinds. Plain strings so they serialize trivially."""

    RUN = "run"
    NODE = "node"
    LLM_CALL = "llm_call"
    RETRIEVAL = "retrieval"
    TOOL = "tool"

    ALL = (RUN, NODE, LLM_CALL, RETRIEVAL, TOOL)


# ---------------------------------------------------------------------------
# Span context (serializable, crosses thread boundaries)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SpanContext:
    """The minimum needed to re-parent work on the far side of a thread hop."""

    trace_id: str
    span_id: str

    def to_dict(self) -> dict[str, str]:
        return {"trace_id": self.trace_id, "span_id": self.span_id}

    @classmethod
    def from_dict(cls, data: Any) -> "SpanContext | None":
        if not isinstance(data, Mapping):
            return None
        trace_id = data.get("trace_id")
        span_id = data.get("span_id")
        if not trace_id or not span_id:
            return None
        return cls(trace_id=str(trace_id), span_id=str(span_id))


_current_context: ContextVar[SpanContext | None] = ContextVar(
    "noesis_span_context", default=None
)


def current_span_context() -> SpanContext | None:
    """The active span's context, or ``None`` outside any span."""
    return _current_context.get()


@contextmanager
def use_context(context: SpanContext | None) -> Iterator[SpanContext | None]:
    """Re-establish ``context`` as the parent for spans opened inside the block.

    This is the explicit half of propagation: call it on the far side of any
    thread hop (``async_utils.run_coroutine_sync``, a ``Send`` fan-out branch,
    a ``ThreadPoolExecutor`` worker). Passing ``None`` is legal and simply
    clears the parent, so callers need no branch.
    """
    token = _current_context.set(context)
    try:
        yield context
    finally:
        _current_context.reset(token)


def inject_context(payload: dict[str, Any], context: SpanContext | None = None) -> dict[str, Any]:
    """Stamp the active (or given) span context into ``payload``, in place.

    Returns the same dict so it can be used inline in a ``Send(...)`` call.
    A ``None`` context leaves the payload untouched rather than writing a null.
    """
    ctx = context if context is not None else current_span_context()
    if ctx is not None:
        payload[TRACE_CONTEXT_KEY] = ctx.to_dict()
    return payload


def extract_context(payload: Any) -> SpanContext | None:
    """Recover a :class:`SpanContext` previously placed by :func:`inject_context`."""
    if not isinstance(payload, Mapping):
        return None
    return SpanContext.from_dict(payload.get(TRACE_CONTEXT_KEY))


# ---------------------------------------------------------------------------
# Span
# ---------------------------------------------------------------------------

def _new_id() -> str:
    return uuid.uuid4().hex


@dataclass
class Span:
    """One timed unit of work. Mutable while open, frozen once ended."""

    name: str
    kind: str
    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    status: str = STATUS_OK
    start_time: float = 0.0
    end_time: float | None = None
    duration_ms: float | None = None

    @property
    def context(self) -> SpanContext:
        return SpanContext(trace_id=self.trace_id, span_id=self.span_id)

    def set_attribute(self, key: str, value: Any) -> "Span":
        self.attributes[key] = value
        return self

    def set_attributes(self, attributes: Mapping[str, Any] | None) -> "Span":
        if attributes:
            self.attributes.update(attributes)
        return self

    def record_error(self, exc: BaseException, *, stacktrace: bool = True) -> "Span":
        """Mark the span failed, preserving the exception *type* and message."""
        self.status = STATUS_ERROR
        self.attributes[EXCEPTION_TYPE] = type(exc).__name__
        self.attributes[EXCEPTION_MESSAGE] = str(exc)
        if stacktrace:
            try:
                self.attributes[EXCEPTION_STACKTRACE] = "".join(
                    traceback.format_exception(type(exc), exc, exc.__traceback__)
                )
            except Exception:  # formatting must never be the thing that breaks
                pass
        return self

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "status": self.status,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": self.duration_ms,
            "attributes": self.attributes,
        }


# ---------------------------------------------------------------------------
# Adapters
# ---------------------------------------------------------------------------

class TracingAdapter:
    """Adapter interface. Both hooks may raise; the tracer swallows it."""

    name = "base"

    def on_start(self, span: Span) -> None:  # pragma: no cover - interface
        pass

    def on_end(self, span: Span) -> None:  # pragma: no cover - interface
        pass

    def flush(self) -> None:
        pass


class NoopAdapter(TracingAdapter):
    """Does nothing, costs nothing, needs nothing."""

    name = "noop"

    def on_start(self, span: Span) -> None:
        pass

    def on_end(self, span: Span) -> None:
        pass


class JsonlAdapter(TracingAdapter):
    """Append one JSON object per completed span to a file.

    Self-sufficient by design: every metric we care about is derivable from
    these lines alone. Append mode, never truncate, so runs accumulate. A file
    that cannot be written is logged once and then ignored -- a broken sink
    must not take the pipeline with it.
    """

    name = "jsonl"

    def __init__(self, path: str) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._warned = False

    def on_end(self, span: Span) -> None:
        line = json.dumps(span.to_dict(), default=str)
        try:
            with self._lock:
                with open(self.path, "a", encoding="utf-8") as handle:
                    handle.write(line + "\n")
        except Exception as exc:
            if not self._warned:
                self._warned = True
                logger.warning(
                    "[tracing] jsonl sink %s is not writable (%s); "
                    "spans will be dropped for the rest of this process",
                    self.path,
                    exc,
                )


class LangfuseAdapter(TracingAdapter):
    """Thin bridge to a Langfuse client.

    ``langfuse`` is NOT a declared dependency of this service. The adapter is
    only ever constructed by :func:`_build_adapter`, which checks importability
    first and falls back to :class:`NoopAdapter` with a warning, so selecting
    this backend on a machine without the package degrades instead of failing.
    """

    name = "langfuse"

    def __init__(self, client: Any) -> None:
        self._client = client
        self._open: dict[str, Any] = {}
        self._lock = threading.Lock()

    def on_start(self, span: Span) -> None:
        handle = self._client.span(
            id=span.span_id,
            trace_id=span.trace_id,
            parent_observation_id=span.parent_span_id,
            name=span.name,
            metadata={"kind": span.kind, **span.attributes},
        )
        with self._lock:
            self._open[span.span_id] = handle

    def on_end(self, span: Span) -> None:
        with self._lock:
            handle = self._open.pop(span.span_id, None)
        if handle is None:
            return
        handle.end(
            metadata={"kind": span.kind, **span.attributes},
            level="ERROR" if span.status == STATUS_ERROR else "DEFAULT",
        )

    def flush(self) -> None:
        flush = getattr(self._client, "flush", None)
        if callable(flush):
            flush()


class OtelAdapter(TracingAdapter):
    """Thin bridge to an OpenTelemetry tracer.

    Same contract as :class:`LangfuseAdapter`: ``opentelemetry`` is not a
    declared dependency, so :func:`_build_adapter` degrades to noop when the
    import fails. Attribute names already follow the GenAI conventions, so they
    pass straight through.
    """

    name = "otel"

    def __init__(self, tracer: Any) -> None:
        self._tracer = tracer
        self._open: dict[str, Any] = {}
        self._lock = threading.Lock()

    def on_start(self, span: Span) -> None:
        otel_span = self._tracer.start_span(span.name)
        with self._lock:
            self._open[span.span_id] = otel_span

    def on_end(self, span: Span) -> None:
        with self._lock:
            otel_span = self._open.pop(span.span_id, None)
        if otel_span is None:
            return
        for key, value in span.attributes.items():
            otel_span.set_attribute(key, value)
        otel_span.set_attribute("noesis.span.kind", span.kind)
        otel_span.end()


# ---------------------------------------------------------------------------
# Adapter selection
# ---------------------------------------------------------------------------

DEFAULT_JSONL_PATH = "noesis_traces.jsonl"


def _build_adapter(backend: str | None, file_path: str | None) -> TracingAdapter:
    """Resolve a backend name to an adapter, degrading to noop on any problem."""
    name = (backend or "noop").strip().lower()

    if name in ("", "noop", "none", "off", "disabled"):
        return NoopAdapter()

    if name == "jsonl":
        path = (file_path or "").strip() or DEFAULT_JSONL_PATH
        return JsonlAdapter(path)

    if name == "langfuse":
        try:
            from langfuse import Langfuse  # type: ignore[import-not-found]
        except Exception as exc:
            logger.warning(
                "[tracing] NOESIS_TRACING_BACKEND=langfuse but the 'langfuse' "
                "package is not importable (%s); falling back to noop. Install "
                "langfuse or set NOESIS_TRACING_BACKEND=jsonl.",
                exc,
            )
            return NoopAdapter()
        try:
            return LangfuseAdapter(Langfuse())
        except Exception as exc:
            logger.warning(
                "[tracing] langfuse client could not be constructed (%s); "
                "falling back to noop.",
                exc,
            )
            return NoopAdapter()

    if name == "otel":
        try:
            from opentelemetry import trace as otel_trace  # type: ignore[import-not-found]
        except Exception as exc:
            logger.warning(
                "[tracing] NOESIS_TRACING_BACKEND=otel but 'opentelemetry' is "
                "not importable (%s); falling back to noop.",
                exc,
            )
            return NoopAdapter()
        try:
            return OtelAdapter(otel_trace.get_tracer("noesis.draft_analysis"))
        except Exception as exc:
            logger.warning(
                "[tracing] otel tracer could not be obtained (%s); "
                "falling back to noop.",
                exc,
            )
            return NoopAdapter()

    logger.warning(
        "[tracing] unknown NOESIS_TRACING_BACKEND=%r; falling back to noop. "
        "Known backends: noop, jsonl, langfuse, otel.",
        backend,
    )
    return NoopAdapter()


# ---------------------------------------------------------------------------
# Tracer
# ---------------------------------------------------------------------------

class Tracer:
    """Opens spans and forwards them to one adapter. Never raises at the caller."""

    def __init__(self, adapter: TracingAdapter | None = None) -> None:
        self.adapter = adapter or NoopAdapter()

    @property
    def enabled(self) -> bool:
        return not isinstance(self.adapter, NoopAdapter)

    def _safe(self, hook: str, span: Span) -> None:
        try:
            getattr(self.adapter, hook)(span)
        except Exception as exc:
            logger.warning(
                "[tracing] adapter %s.%s raised (%s); span dropped, caller unaffected",
                type(self.adapter).__name__,
                hook,
                exc,
            )

    @contextmanager
    def start_span(
        self,
        name: str,
        *,
        kind: str = SpanKind.NODE,
        attributes: Mapping[str, Any] | None = None,
        parent: SpanContext | None = None,
    ) -> Iterator[Span]:
        """Open a timed span, nested under ``parent`` or the ambient context.

        The span is ended -- with timing recorded -- on both the success and the
        exception path. An exception propagating through the block is recorded
        on the span via :meth:`Span.record_error` and then re-raised unchanged:
        tracing observes failures, it does not swallow them.
        """
        parent_ctx = parent if parent is not None else _current_context.get()
        span = Span(
            name=str(name),
            kind=str(kind),
            trace_id=parent_ctx.trace_id if parent_ctx else _new_id(),
            span_id=_new_id(),
            parent_span_id=parent_ctx.span_id if parent_ctx else None,
            attributes=dict(attributes or {}),
            start_time=time.time(),
        )
        started = time.perf_counter()

        self._safe("on_start", span)
        token = _current_context.set(span.context)
        try:
            yield span
        except BaseException as exc:
            try:
                if isinstance(exc, Exception):
                    span.record_error(exc)
                else:
                    span.status = STATUS_ERROR
            except Exception:  # pragma: no cover - defensive
                pass
            raise
        finally:
            _current_context.reset(token)
            span.duration_ms = (time.perf_counter() - started) * 1000.0
            span.end_time = time.time()
            self._safe("on_end", span)

    def flush(self) -> None:
        try:
            self.adapter.flush()
        except Exception as exc:
            logger.warning("[tracing] adapter flush raised (%s); ignored", exc)


# ---------------------------------------------------------------------------
# Process-wide tracer
# ---------------------------------------------------------------------------

_tracer: Tracer | None = None
_tracer_lock = threading.Lock()


def get_tracer() -> Tracer:
    """The process tracer, built from the environment on first use.

    Env is read once and cached because the adapter may hold a file handle or a
    client; call :func:`configure_tracing` or :func:`reset_tracer` to rebuild
    (tests do this).
    """
    global _tracer
    if _tracer is None:
        with _tracer_lock:
            if _tracer is None:
                _tracer = Tracer(
                    _build_adapter(
                        os.getenv("NOESIS_TRACING_BACKEND"),
                        os.getenv("NOESIS_TRACING_FILE"),
                    )
                )
    return _tracer


def configure_tracing(
    backend: str | None = None,
    file_path: str | None = None,
    adapter: TracingAdapter | None = None,
) -> Tracer:
    """Rebuild the process tracer explicitly. Returns the new tracer."""
    global _tracer
    with _tracer_lock:
        _tracer = Tracer(adapter if adapter is not None else _build_adapter(backend, file_path))
        return _tracer


def reset_tracer() -> None:
    """Drop the cached tracer so the next :func:`get_tracer` re-reads the env."""
    global _tracer
    with _tracer_lock:
        _tracer = None


@contextmanager
def start_span(
    name: str,
    *,
    kind: str = SpanKind.NODE,
    attributes: Mapping[str, Any] | None = None,
    parent: SpanContext | None = None,
) -> Iterator[Span]:
    """Module-level convenience wrapper over ``get_tracer().start_span``."""
    with get_tracer().start_span(name, kind=kind, attributes=attributes, parent=parent) as span:
        yield span


# ---------------------------------------------------------------------------
# Attribute builders
# ---------------------------------------------------------------------------

def llm_call_attributes(
    *,
    model: str | None,
    system: str = "openai",
    operation: str = "chat",
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    cached_tokens: int | None = None,
    estimated_usd: float | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    response_model: str | None = None,
    finish_reasons: Sequence[str] | None = None,
) -> dict[str, Any]:
    """GenAI-convention attributes for an ``llm_call`` span.

    Takes the same numbers ``llm_budget.extract_usage`` produces, so a caller
    that already records budget usage feeds the identical values here without a
    second extraction. Omitted values are left out entirely rather than written
    as zero -- absent and zero are different facts.
    """
    attrs: dict[str, Any] = {
        GEN_AI_SYSTEM: system,
        GEN_AI_OPERATION_NAME: operation,
    }
    if model is not None:
        attrs[GEN_AI_REQUEST_MODEL] = model
    if prompt_tokens is not None:
        attrs[GEN_AI_USAGE_INPUT_TOKENS] = int(prompt_tokens)
    if completion_tokens is not None:
        attrs[GEN_AI_USAGE_OUTPUT_TOKENS] = int(completion_tokens)
    if cached_tokens is not None:
        attrs[NOESIS_CACHED_INPUT_TOKENS] = int(cached_tokens)
    if estimated_usd is not None:
        attrs[NOESIS_ESTIMATED_COST_USD] = float(estimated_usd)
    if temperature is not None:
        attrs[GEN_AI_REQUEST_TEMPERATURE] = float(temperature)
    if max_tokens is not None:
        attrs[GEN_AI_REQUEST_MAX_TOKENS] = int(max_tokens)
    if response_model is not None:
        attrs[GEN_AI_RESPONSE_MODEL] = response_model
    if finish_reasons is not None:
        attrs[GEN_AI_RESPONSE_FINISH_REASONS] = list(finish_reasons)
    return attrs


def retrieval_attributes(
    *,
    query: str | None = None,
    top_k: int | None = None,
    returned_count: int | None = None,
    document_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Attributes for a ``retrieval`` span (all ``noesis.*``; no OTel term exists)."""
    attrs: dict[str, Any] = {}
    if query is not None:
        attrs[NOESIS_RETRIEVAL_QUERY] = query
    if top_k is not None:
        attrs[NOESIS_RETRIEVAL_TOP_K] = int(top_k)
    if returned_count is not None:
        attrs[NOESIS_RETRIEVAL_RETURNED_COUNT] = int(returned_count)
    if document_ids is not None:
        ids = [str(d) for d in document_ids]
        attrs[NOESIS_RETRIEVAL_DOCUMENT_IDS] = ids
        if returned_count is None:
            attrs[NOESIS_RETRIEVAL_RETURNED_COUNT] = len(ids)
    return attrs


def run_attributes(
    *,
    analysis_run_id: str | None = None,
    draft_id: str | None = None,
) -> dict[str, Any]:
    """Attributes for the root ``run`` span."""
    attrs: dict[str, Any] = {}
    if analysis_run_id is not None:
        attrs[NOESIS_RUN_ID] = str(analysis_run_id)
    if draft_id is not None:
        attrs[NOESIS_DRAFT_ID] = str(draft_id)
    return attrs


__all__ = [
    "Span",
    "SpanContext",
    "SpanKind",
    "Tracer",
    "TracingAdapter",
    "NoopAdapter",
    "JsonlAdapter",
    "LangfuseAdapter",
    "OtelAdapter",
    "TRACE_CONTEXT_KEY",
    "start_span",
    "get_tracer",
    "configure_tracing",
    "reset_tracer",
    "current_span_context",
    "use_context",
    "inject_context",
    "extract_context",
    "llm_call_attributes",
    "retrieval_attributes",
    "run_attributes",
]

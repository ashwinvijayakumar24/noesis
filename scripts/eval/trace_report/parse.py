"""Read span JSONL files and reconstruct the trace trees.

The writer (``tracing.JsonlAdapter``) appends one JSON object per *completed*
span, so the file is naturally out of order: a parent always lands **after** its
children, and concurrent branches interleave. Nothing here may assume ordering.

Failure modes this must survive, because all of them happen in practice:

* a **truncated final line** -- the process was killed mid-write;
* an arbitrary **malformed line** -- garbage, a partial object, a non-object;
* **interleaved traces** -- several runs appending to one file;
* **out-of-order arrival** -- children before parents, always;
* an **orphan span** -- its parent line was lost (truncation, or a separate
  file that was not passed in). It is kept and promoted to a root, and counted,
  rather than dropped: dropping it would silently under-report work;
* **duplicate span ids across files** -- the same run exported twice. First
  occurrence wins; later ones are counted, not merged.

A bad line is never fatal. Every skip increments a counter on
:class:`ParseStats`, which the report prints, so "we ignored 40% of the file"
can never hide.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator

# Span kinds, mirrored from app.core.tracing.SpanKind. Duplicated as plain
# strings on purpose: parsing a file must not require the backend to be
# importable (the pricing table is a different story -- that one is imported).
KIND_RUN = "run"
KIND_NODE = "node"
KIND_LLM_CALL = "llm_call"
KIND_RETRIEVAL = "retrieval"
KIND_TOOL = "tool"

# Attribute keys used by the metrics layer.
ATTR_MODEL = "gen_ai.request.model"
ATTR_RESPONSE_MODEL = "gen_ai.response.model"
ATTR_INPUT_TOKENS = "gen_ai.usage.input_tokens"
ATTR_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
ATTR_CACHED_TOKENS = "noesis.gen_ai.usage.cached_input_tokens"
ATTR_COST_USD = "noesis.gen_ai.usage.estimated_cost_usd"
ATTR_RUN_ID = "noesis.run.id"
ATTR_DRAFT_ID = "noesis.draft.id"
ATTR_NODE_NAME = "noesis.node.name"
ATTR_REVIEWER_TYPE = "noesis.reviewer.type"
ATTR_TOP_K = "noesis.retrieval.top_k"
ATTR_RETURNED_COUNT = "noesis.retrieval.returned_count"


def _as_float(value: Any) -> float | None:
    """Numeric or ``None``. ``None`` means *absent*, never *zero*."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _as_int(value: Any) -> int | None:
    number = _as_float(value)
    return None if number is None else int(number)


@dataclass(frozen=True)
class SpanRecord:
    """One completed span, as written by the jsonl adapter."""

    span_id: str
    trace_id: str
    name: str
    kind: str
    parent_span_id: str | None = None
    status: str = "OK"
    start_time: float | None = None
    end_time: float | None = None
    duration_ms: float | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    source_file: str = ""

    # -- derived helpers ---------------------------------------------------

    @property
    def wall_ms(self) -> float | None:
        """Measured duration, or ``None`` when the span carries no timing.

        Prefers ``duration_ms`` (a ``perf_counter`` delta, monotonic) and falls
        back to the wall-clock ``end_time - start_time`` only when it is
        missing. The two differ slightly by construction; interval arithmetic
        elsewhere uses start/end because that is the only thing comparable
        across spans.
        """
        if self.duration_ms is not None:
            return self.duration_ms
        if self.start_time is not None and self.end_time is not None:
            return max(0.0, (self.end_time - self.start_time) * 1000.0)
        return None

    @property
    def interval(self) -> tuple[float, float] | None:
        """``(start, end)`` in wall-clock seconds, or ``None`` if incomplete."""
        if self.start_time is None:
            return None
        if self.end_time is not None:
            return (self.start_time, max(self.start_time, self.end_time))
        if self.duration_ms is not None:
            return (self.start_time, self.start_time + self.duration_ms / 1000.0)
        return None

    @property
    def node_key(self) -> str:
        """Grouping key: the node name, with the fan-out branch when present.

        The three reviewer branches all emit a span named ``reviewer_panel_node``
        and are told apart only by ``noesis.reviewer.type``. Callers that want
        them merged use :attr:`base_name`.
        """
        base = self.base_name
        variant = self.attributes.get(ATTR_REVIEWER_TYPE)
        return f"{base}[{variant}]" if variant else base

    @property
    def base_name(self) -> str:
        return str(self.attributes.get(ATTR_NODE_NAME) or self.name)

    @property
    def model(self) -> str | None:
        model = self.attributes.get(ATTR_RESPONSE_MODEL) or self.attributes.get(ATTR_MODEL)
        return str(model) if model else None

    @property
    def input_tokens(self) -> int | None:
        return _as_int(self.attributes.get(ATTR_INPUT_TOKENS))

    @property
    def output_tokens(self) -> int | None:
        return _as_int(self.attributes.get(ATTR_OUTPUT_TOKENS))

    @property
    def cached_tokens(self) -> int | None:
        return _as_int(self.attributes.get(ATTR_CACHED_TOKENS))

    @property
    def cost_usd(self) -> float | None:
        """Cost recorded on the span, or ``None`` for *unknown* (never 0.0)."""
        return _as_float(self.attributes.get(ATTR_COST_USD))


@dataclass
class ParseStats:
    """Everything that was skipped, so nothing is skipped silently."""

    files: list[str] = field(default_factory=list)
    lines_read: int = 0
    spans_parsed: int = 0
    blank_lines: int = 0
    malformed_lines: int = 0
    duplicate_span_ids: int = 0
    orphan_spans: int = 0
    #: (file, line number, reason) for the first few malformed lines.
    samples: list[tuple[str, int, str]] = field(default_factory=list)

    def note_malformed(self, source: str, line_no: int, reason: str) -> None:
        self.malformed_lines += 1
        if len(self.samples) < 10:
            self.samples.append((source, line_no, reason))

    @property
    def clean(self) -> bool:
        return self.malformed_lines == 0 and self.duplicate_span_ids == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "files": list(self.files),
            "lines_read": self.lines_read,
            "spans_parsed": self.spans_parsed,
            "blank_lines": self.blank_lines,
            "malformed_lines": self.malformed_lines,
            "duplicate_span_ids": self.duplicate_span_ids,
            "orphan_spans": self.orphan_spans,
            "malformed_samples": [
                {"file": f, "line": n, "reason": r} for f, n, r in self.samples
            ],
        }


@dataclass
class Trace:
    """One reconstructed trace: spans indexed by id, plus the parent/child map."""

    trace_id: str
    spans: dict[str, SpanRecord] = field(default_factory=dict)
    #: parent span id -> child span ids, in start-time order.
    _children: dict[str, list[str]] = field(default_factory=dict)
    #: spans with no parent *present in this trace* (true roots and orphans).
    root_ids: list[str] = field(default_factory=list)
    orphan_ids: list[str] = field(default_factory=list)

    def children(self, span_id: str) -> list[SpanRecord]:
        return [self.spans[c] for c in self._children.get(span_id, [])]

    def roots(self) -> list[SpanRecord]:
        return [self.spans[r] for r in self.root_ids]

    def run_span(self) -> SpanRecord | None:
        """The ``run``-kind root, if this trace has one."""
        for span in self.spans.values():
            if span.kind == KIND_RUN and span.parent_span_id not in self.spans:
                return span
        for span in self.spans.values():
            if span.kind == KIND_RUN:
                return span
        return None

    @property
    def run_id(self) -> str:
        run = self.run_span()
        if run is not None:
            value = run.attributes.get(ATTR_RUN_ID)
            if value:
                return str(value)
        return self.trace_id

    def walk(self, span_id: str | None = None) -> Iterator[SpanRecord]:
        """Depth-first over the whole trace (or one subtree)."""
        stack = list(self.root_ids) if span_id is None else [span_id]
        while stack:
            current = stack.pop()
            span = self.spans.get(current)
            if span is None:
                continue
            yield span
            stack.extend(self._children.get(current, []))

    def wall_ms(self) -> float | None:
        """The trace's wall time: its run span, else the union of its roots."""
        run = self.run_span()
        if run is not None and run.wall_ms is not None:
            return run.wall_ms
        intervals = [s.interval for s in self.roots()]
        present = [i for i in intervals if i is not None]
        if not present:
            return None
        return (max(e for _, e in present) - min(s for s, _ in present)) * 1000.0


@dataclass
class ParseResult:
    traces: dict[str, Trace]
    stats: ParseStats

    @property
    def spans(self) -> list[SpanRecord]:
        return [s for t in self.traces.values() for s in t.spans.values()]


_REQUIRED = ("span_id", "trace_id")


def parse_line(raw: str, source: str, line_no: int, stats: ParseStats) -> SpanRecord | None:
    """Parse one JSONL line. Returns ``None`` (and counts) on anything wrong.

    A truncated final line is just a JSONDecodeError -- there is no separate
    code path for it, and there should not be: an interrupted write and a
    corrupt write are indistinguishable from here and are treated identically.
    """
    text = raw.strip()
    if not text:
        stats.blank_lines += 1
        return None
    try:
        payload = json.loads(text)
    except (ValueError, TypeError) as exc:
        stats.note_malformed(source, line_no, f"not JSON: {exc}")
        return None
    if not isinstance(payload, dict):
        stats.note_malformed(source, line_no, f"not a JSON object: {type(payload).__name__}")
        return None
    missing = [k for k in _REQUIRED if not payload.get(k)]
    if missing:
        stats.note_malformed(source, line_no, f"missing {'/'.join(missing)}")
        return None

    attributes = payload.get("attributes")
    if not isinstance(attributes, dict):
        attributes = {}

    parent = payload.get("parent_span_id")
    return SpanRecord(
        span_id=str(payload["span_id"]),
        trace_id=str(payload["trace_id"]),
        name=str(payload.get("name") or "<unnamed>"),
        kind=str(payload.get("kind") or KIND_NODE),
        parent_span_id=str(parent) if parent else None,
        status=str(payload.get("status") or "OK"),
        start_time=_as_float(payload.get("start_time")),
        end_time=_as_float(payload.get("end_time")),
        duration_ms=_as_float(payload.get("duration_ms")),
        attributes=attributes,
        source_file=source,
    )


def parse_lines(lines: Iterable[str], source: str = "<stream>", stats: ParseStats | None = None):
    """Parse an iterable of raw lines into records, accumulating into ``stats``."""
    stats = stats if stats is not None else ParseStats()
    records: list[SpanRecord] = []
    for line_no, raw in enumerate(lines, start=1):
        stats.lines_read += 1
        record = parse_line(raw, source, line_no, stats)
        if record is not None:
            records.append(record)
    return records, stats


def build_traces(records: Iterable[SpanRecord], stats: ParseStats | None = None) -> ParseResult:
    """Group records by ``trace_id`` and wire up parent/child links.

    Two passes, because arrival order is meaningless: index everything first,
    then resolve parents. A parent id that resolves to nothing after the second
    pass is an orphan -- promoted to a root of its trace and counted.
    """
    stats = stats if stats is not None else ParseStats()
    traces: dict[str, Trace] = {}
    seen: dict[str, SpanRecord] = {}

    for record in records:
        if record.span_id in seen:
            # Duplicate ids happen when the same run is exported to two files.
            # First wins: merging two versions of one span would invent timing.
            stats.duplicate_span_ids += 1
            continue
        seen[record.span_id] = record
        trace = traces.setdefault(record.trace_id, Trace(trace_id=record.trace_id))
        trace.spans[record.span_id] = record
        stats.spans_parsed += 1

    for trace in traces.values():
        for span in trace.spans.values():
            parent = span.parent_span_id
            if parent and parent in trace.spans:
                trace._children.setdefault(parent, []).append(span.span_id)
            else:
                trace.root_ids.append(span.span_id)
                if parent:
                    # Parent id was recorded but its line is not here.
                    trace.orphan_ids.append(span.span_id)
                    stats.orphan_spans += 1

    # Deterministic ordering: by start time, then span id for ties/missing.
    def sort_key(span_id: str, trace: Trace) -> tuple[float, str]:
        span = trace.spans[span_id]
        return (span.start_time if span.start_time is not None else float("inf"), span.span_id)

    for trace in traces.values():
        trace.root_ids.sort(key=lambda sid: sort_key(sid, trace))
        for ids in trace._children.values():
            ids.sort(key=lambda sid: sort_key(sid, trace))

    return ParseResult(traces=traces, stats=stats)


def load_span_files(paths: Iterable[str | Path]) -> ParseResult:
    """Read one or more span JSONL files into reconstructed traces.

    A file that cannot be opened is counted as a malformed line rather than
    raising, so one bad path in a glob does not lose the whole report.
    """
    stats = ParseStats()
    records: list[SpanRecord] = []
    for path in paths:
        source = str(path)
        stats.files.append(source)
        try:
            with open(source, "r", encoding="utf-8", errors="replace") as handle:
                file_records, stats = parse_lines(handle, source=source, stats=stats)
        except OSError as exc:
            stats.note_malformed(source, 0, f"unreadable: {exc}")
            continue
        records.extend(file_records)
    return build_traces(records, stats=stats)


__all__ = [
    "ATTR_CACHED_TOKENS",
    "ATTR_COST_USD",
    "ATTR_DRAFT_ID",
    "ATTR_INPUT_TOKENS",
    "ATTR_MODEL",
    "ATTR_NODE_NAME",
    "ATTR_OUTPUT_TOKENS",
    "ATTR_RETURNED_COUNT",
    "ATTR_REVIEWER_TYPE",
    "ATTR_RUN_ID",
    "ATTR_TOP_K",
    "KIND_LLM_CALL",
    "KIND_NODE",
    "KIND_RETRIEVAL",
    "KIND_RUN",
    "KIND_TOOL",
    "ParseResult",
    "ParseStats",
    "SpanRecord",
    "Trace",
    "build_traces",
    "load_span_files",
    "parse_line",
    "parse_lines",
]

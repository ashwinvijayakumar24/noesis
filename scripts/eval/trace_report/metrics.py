"""Pure metric functions over reconstructed traces. No I/O, no globals.

Everything here takes :class:`~trace_report.parse.Trace` objects and returns
dataclasses. Three rules are baked into the types rather than left to the
caller's discipline:

1. **A percentile is never separable from its n.** :class:`Percentiles` carries
   ``n``, and p95/p99 come back as ``None`` with a stated reason below
   :data:`DEFAULT_MIN_N`. A "p95" over three runs is not a p95 and this module
   will not produce one.
2. **Unknown cost is never zero.** :class:`RunCost` has ``complete``; any span
   whose cost cannot be established (no cost attribute *and* an unpriced or
   unknown model) lands in ``unpriced_spans`` and flips ``complete`` to False.
3. **"No data" is not "zero".** A node that never ran yields ``n=0`` and
   ``None`` percentiles; a node that ran once for 0 ms yields ``n=1`` and
   ``0.0``. :func:`node_latency` accepts ``expected_nodes`` precisely so the
   never-executed rows exist and are visibly empty.

Cost uses ``app.core.llm_budget`` directly -- ``get_price`` and ``estimate_usd``
are imported, never re-implemented, so a price change in one place changes both.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Sequence

from . import parse as P
from .parse import SpanRecord, Trace

from app.core.llm_budget import estimate_usd, get_price  # noqa: E402  (path set in __init__)

# ---------------------------------------------------------------------------
# Percentiles
# ---------------------------------------------------------------------------

#: Smallest sample size at which each quantile is allowed to be reported.
#: Nearest-rank p95 over n<20 is just "the max" wearing a percentile's name;
#: p99 needs 100 samples before it means anything at all. Below these the value
#: is refused rather than printed with a caveat, because caveats get dropped
#: when numbers are copied into a slide.
DEFAULT_MIN_N: dict[str, int] = {"p50": 1, "p90": 10, "p95": 20, "p99": 100}

_QUANTILES = {"p50": 0.50, "p90": 0.90, "p95": 0.95, "p99": 0.99}


@dataclass(frozen=True)
class Percentiles:
    """A distribution summary that cannot be quoted without its sample size."""

    n: int
    min: float | None = None
    max: float | None = None
    mean: float | None = None
    values: dict[str, float | None] = field(default_factory=dict)
    #: quantile name -> why it is missing (only for refused ones)
    refused: dict[str, str] = field(default_factory=dict)

    def get(self, name: str) -> float | None:
        return self.values.get(name)

    def label(self, name: str) -> str:
        """Rendering helper: the number, or the refusal, never a bare blank."""
        if name in self.refused:
            return f"n/a ({self.refused[name]})"
        value = self.values.get(name)
        if value is None:
            return "no data"
        return f"{value:,.1f}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "n": self.n,
            "min": self.min,
            "max": self.max,
            "mean": self.mean,
            **{k: v for k, v in self.values.items()},
            "refused": dict(self.refused),
        }


def nearest_rank(sorted_values: Sequence[float], quantile: float) -> float:
    """Nearest-rank percentile: ``ceil(q*n)``-th smallest, 1-indexed.

    Chosen over linear interpolation because every reported number is then an
    actually-observed measurement, and because it is trivially checkable by
    hand -- the tests hand-compute against it.
    """
    n = len(sorted_values)
    rank = max(1, min(n, math.ceil(quantile * n)))
    return float(sorted_values[rank - 1])


def percentiles(
    values: Iterable[float],
    min_n: dict[str, int] | None = None,
) -> Percentiles:
    """Summarize ``values`` (ms), refusing quantiles the sample cannot support."""
    thresholds = DEFAULT_MIN_N if min_n is None else min_n
    data = sorted(float(v) for v in values)
    n = len(data)
    if n == 0:
        # No data is not zero: every field stays None and n stays 0.
        return Percentiles(
            n=0,
            values={k: None for k in _QUANTILES},
            refused={k: "no data" for k in _QUANTILES},
        )

    computed: dict[str, float | None] = {}
    refused: dict[str, str] = {}
    for name, q in _QUANTILES.items():
        needed = thresholds.get(name, 1)
        if n < needed:
            computed[name] = None
            refused[name] = f"n={n} < {needed}"
        else:
            computed[name] = nearest_rank(data, q)
    return Percentiles(
        n=n,
        min=data[0],
        max=data[-1],
        mean=sum(data) / n,
        values=computed,
        refused=refused,
    )


# ---------------------------------------------------------------------------
# Interval algebra (the basis for self time, concurrency and LLM share)
# ---------------------------------------------------------------------------

def merge_intervals(intervals: Iterable[tuple[float, float]]) -> list[tuple[float, float]]:
    """Union of half-open intervals, sorted and non-overlapping."""
    ordered = sorted((s, e) for s, e in intervals if e > s)
    if not ordered:
        return []
    merged = [ordered[0]]
    for start, end in ordered[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def union_seconds(intervals: Iterable[tuple[float, float]]) -> float:
    return sum(e - s for s, e in merge_intervals(intervals))


# ---------------------------------------------------------------------------
# Self time vs wall time
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SelfTime:
    """Wall time and self time for one span, kept separate on purpose.

    A span's ``duration_ms`` is its **wall time** and includes everything its
    children did. "Slowest node" is therefore ambiguous: the run span is always
    the slowest by wall time and always tells you nothing.

    **Self time** is the wall time minus the time covered by children. The
    subtraction must use the *union* of the children's intervals, not the sum
    of their durations. The reviewer fan-out is exactly why: three
    ``reviewer_panel_node`` spans of ~10s each run concurrently under one
    parent whose wall time is ~12s. Summing children gives 30s, so
    ``self = 12 - 30 = -18``, which is nonsense; the union gives ~10s, so
    ``self = ~2s``, which is the parent's own orchestration overhead. Both
    numbers are kept on this dataclass (``children_sum_ms`` and
    ``children_union_ms``) because their ratio is the real parallel speedup --
    see :func:`fanout_concurrency`.

    ``exact`` is False when a child lacked ``start_time``/``end_time`` and the
    union had to fall back to ``min(sum of child durations, wall)``. That
    fallback under-reports self time for parallel children, so it is flagged
    rather than blended in silently.
    """

    span_id: str
    name: str
    kind: str
    wall_ms: float | None
    self_ms: float | None
    children_union_ms: float | None
    children_sum_ms: float
    child_count: int
    exact: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "span_id": self.span_id,
            "name": self.name,
            "kind": self.kind,
            "wall_ms": self.wall_ms,
            "self_ms": self.self_ms,
            "children_union_ms": self.children_union_ms,
            "children_sum_ms": self.children_sum_ms,
            "child_count": self.child_count,
            "exact": self.exact,
        }


def self_time(trace: Trace, span: SpanRecord) -> SelfTime:
    """Wall/self decomposition for one span. See :class:`SelfTime`."""
    children = trace.children(span.span_id)
    wall = span.wall_ms
    child_sum = sum(c.wall_ms or 0.0 for c in children)

    if not children:
        return SelfTime(
            span_id=span.span_id,
            name=span.node_key,
            kind=span.kind,
            wall_ms=wall,
            self_ms=wall,
            children_union_ms=0.0,
            children_sum_ms=0.0,
            child_count=0,
            exact=True,
        )

    intervals = [c.interval for c in children]
    parent_interval = span.interval
    if all(i is not None for i in intervals):
        clipped: list[tuple[float, float]] = []
        for start, end in intervals:  # type: ignore[misc]
            if parent_interval is not None:
                start = max(start, parent_interval[0])
                end = min(end, parent_interval[1])
            if end > start:
                clipped.append((start, end))
        union_ms = union_seconds(clipped) * 1000.0
        exact = True
    else:
        # Degraded path: no interval for at least one child. Clamping to wall
        # keeps self_ms >= 0 but hides concurrency, hence exact=False.
        union_ms = min(child_sum, wall) if wall is not None else child_sum
        exact = False

    self_ms = None if wall is None else max(0.0, wall - union_ms)
    return SelfTime(
        span_id=span.span_id,
        name=span.node_key,
        kind=span.kind,
        wall_ms=wall,
        self_ms=self_ms,
        children_union_ms=union_ms,
        children_sum_ms=child_sum,
        child_count=len(children),
        exact=exact,
    )


# ---------------------------------------------------------------------------
# Per-node latency
# ---------------------------------------------------------------------------

def default_key(span: SpanRecord) -> str:
    """Group the fan-out branches separately (``reviewer_panel_node[clarity]``)."""
    return span.node_key


def merged_key(span: SpanRecord) -> str:
    """Group the fan-out branches together (``reviewer_panel_node``)."""
    return span.base_name


@dataclass(frozen=True)
class NodeLatency:
    node: str
    executions: int
    traces_seen: int
    wall: Percentiles
    self_: Percentiles
    total_wall_ms: float
    total_self_ms: float
    #: True when this node was asked about but never appeared in any trace.
    never_executed: bool = False
    inexact_self_spans: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "node": self.node,
            "executions": self.executions,
            "traces_seen": self.traces_seen,
            "never_executed": self.never_executed,
            "wall_ms": self.wall.to_dict(),
            "self_ms": self.self_.to_dict(),
            "total_wall_ms": self.total_wall_ms,
            "total_self_ms": self.total_self_ms,
            "inexact_self_spans": self.inexact_self_spans,
        }


def node_latency(
    traces: Iterable[Trace],
    *,
    key: Callable[[SpanRecord], str] = default_key,
    kinds: Sequence[str] = (P.KIND_NODE,),
    expected_nodes: Iterable[str] | None = None,
    min_n: dict[str, int] | None = None,
) -> list[NodeLatency]:
    """Per-node wall and self latency percentiles across every supplied trace.

    ``expected_nodes`` is how "never executed" becomes visible: any name listed
    there that produced no spans comes back with ``executions=0`` and
    ``never_executed=True``, which is a different row from a node that executed
    once in 0.0 ms.
    """
    wall_samples: dict[str, list[float]] = {}
    self_samples: dict[str, list[float]] = {}
    trace_ids: dict[str, set[str]] = {}
    executions: dict[str, int] = {}
    inexact: dict[str, int] = {}

    for trace in traces:
        for span in trace.spans.values():
            if kinds and span.kind not in kinds:
                continue
            name = key(span)
            executions[name] = executions.get(name, 0) + 1
            trace_ids.setdefault(name, set()).add(trace.trace_id)
            timing = self_time(trace, span)
            if timing.wall_ms is not None:
                wall_samples.setdefault(name, []).append(timing.wall_ms)
            if timing.self_ms is not None:
                self_samples.setdefault(name, []).append(timing.self_ms)
            if not timing.exact:
                inexact[name] = inexact.get(name, 0) + 1

    names = set(executions) | set(expected_nodes or ())
    rows: list[NodeLatency] = []
    for name in sorted(names):
        walls = wall_samples.get(name, [])
        selves = self_samples.get(name, [])
        count = executions.get(name, 0)
        rows.append(
            NodeLatency(
                node=name,
                executions=count,
                traces_seen=len(trace_ids.get(name, ())),
                wall=percentiles(walls, min_n=min_n),
                self_=percentiles(selves, min_n=min_n),
                total_wall_ms=sum(walls),
                total_self_ms=sum(selves),
                never_executed=count == 0,
                inexact_self_spans=inexact.get(name, 0),
            )
        )
    return rows


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------

@dataclass
class TokenBucket:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    #: Calls that reported no token usage at all -- not the same as zero tokens.
    calls_without_usage: int = 0

    @property
    def uncached_input_tokens(self) -> int:
        """Cached tokens are a SUBSET of input tokens (OpenAI's convention)."""
        return max(0, self.input_tokens - self.cached_tokens)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def cache_hit_rate(self) -> float | None:
        if self.input_tokens <= 0:
            return None
        return self.cached_tokens / self.input_tokens

    def to_dict(self) -> dict[str, Any]:
        return {
            "calls": self.calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cached_tokens": self.cached_tokens,
            "uncached_input_tokens": self.uncached_input_tokens,
            "total_tokens": self.total_tokens,
            "cache_hit_rate": self.cache_hit_rate,
            "calls_without_usage": self.calls_without_usage,
        }


def _owning_node(trace: Trace, span: SpanRecord) -> str:
    """Nearest ``node``-kind ancestor of ``span`` (or the span's own name)."""
    current: SpanRecord | None = span
    seen: set[str] = set()
    while current is not None and current.span_id not in seen:
        seen.add(current.span_id)
        if current.kind == P.KIND_NODE:
            return current.node_key
        parent_id = current.parent_span_id
        current = trace.spans.get(parent_id) if parent_id else None
    return span.node_key


def _fold_tokens(bucket: TokenBucket, span: SpanRecord) -> None:
    bucket.calls += 1
    if span.input_tokens is None and span.output_tokens is None:
        bucket.calls_without_usage += 1
        return
    bucket.input_tokens += span.input_tokens or 0
    bucket.output_tokens += span.output_tokens or 0
    bucket.cached_tokens += span.cached_tokens or 0


def tokens_by_node(traces: Iterable[Trace]) -> dict[str, TokenBucket]:
    out: dict[str, TokenBucket] = {}
    for trace in traces:
        for span in trace.spans.values():
            if span.kind != P.KIND_LLM_CALL:
                continue
            _fold_tokens(out.setdefault(_owning_node(trace, span), TokenBucket()), span)
    return out


def tokens_by_model(traces: Iterable[Trace]) -> dict[str, TokenBucket]:
    out: dict[str, TokenBucket] = {}
    for trace in traces:
        for span in trace.spans.values():
            if span.kind != P.KIND_LLM_CALL:
                continue
            _fold_tokens(out.setdefault(span.model or "<unknown model>", TokenBucket()), span)
    return out


def token_totals(traces: Iterable[Trace]) -> TokenBucket:
    total = TokenBucket()
    for bucket in tokens_by_model(traces).values():
        total.calls += bucket.calls
        total.input_tokens += bucket.input_tokens
        total.output_tokens += bucket.output_tokens
        total.cached_tokens += bucket.cached_tokens
        total.calls_without_usage += bucket.calls_without_usage
    return total


# ---------------------------------------------------------------------------
# Cost
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SpanCost:
    span_id: str
    node: str
    model: str | None
    usd: float | None
    source: str  # "span_attribute" | "recomputed" | "unpriced"
    reason: str | None = None


def span_cost(trace: Trace, span: SpanRecord) -> SpanCost:
    """Cost of one ``llm_call`` span. ``usd is None`` means *unknown*, not free.

    Prefers the cost the pipeline already recorded on the span. Falls back to
    recomputing from tokens via ``llm_budget.estimate_usd`` -- the same pricing
    table the runtime uses, imported rather than copied. If the model is absent
    from that table, or the span carries no usage at all, the cost stays None
    and the span is unpriced.
    """
    node = _owning_node(trace, span)
    recorded = span.cost_usd
    if recorded is not None:
        return SpanCost(span.span_id, node, span.model, recorded, "span_attribute")

    model = span.model
    if model is None:
        return SpanCost(span.span_id, node, None, None, "unpriced", "no model attribute")
    if span.input_tokens is None and span.output_tokens is None:
        return SpanCost(span.span_id, node, model, None, "unpriced", "no token usage")
    if get_price(model) is None:
        return SpanCost(span.span_id, node, model, None, "unpriced", f"model {model!r} not in pricing table")

    usd = estimate_usd(
        model,
        span.input_tokens or 0,
        span.output_tokens or 0,
        span.cached_tokens or 0,
    )
    if usd is None:
        return SpanCost(span.span_id, node, model, None, "unpriced", "incomplete rates for model")
    return SpanCost(span.span_id, node, model, usd, "recomputed")


@dataclass
class RunCost:
    """Cost of one run. ``complete`` is the whole point of this type.

    Any single unpriced span makes the run's total a **lower bound**, so
    ``complete`` goes False and ``unpriced_spans`` says how much is missing in
    span count. Callers must not print ``usd`` without ``complete``.
    """

    trace_id: str
    run_id: str
    usd: float
    priced_spans: int = 0
    unpriced_spans: int = 0
    llm_spans: int = 0
    unpriced_reasons: dict[str, int] = field(default_factory=dict)

    @property
    def complete(self) -> bool:
        return self.unpriced_spans == 0

    def label(self) -> str:
        return f"${self.usd:.4f}" + ("" if self.complete else f" (>=, {self.unpriced_spans} unpriced)")

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "run_id": self.run_id,
            "usd": self.usd,
            "complete": self.complete,
            "priced_spans": self.priced_spans,
            "unpriced_spans": self.unpriced_spans,
            "llm_spans": self.llm_spans,
            "unpriced_reasons": dict(self.unpriced_reasons),
        }


def run_cost(trace: Trace) -> RunCost:
    result = RunCost(trace_id=trace.trace_id, run_id=trace.run_id, usd=0.0)
    for span in trace.spans.values():
        if span.kind != P.KIND_LLM_CALL:
            continue
        result.llm_spans += 1
        cost = span_cost(trace, span)
        if cost.usd is None:
            result.unpriced_spans += 1
            reason = cost.reason or "unknown"
            result.unpriced_reasons[reason] = result.unpriced_reasons.get(reason, 0) + 1
        else:
            result.priced_spans += 1
            result.usd += cost.usd
    return result


def run_costs(traces: Iterable[Trace]) -> list[RunCost]:
    return [run_cost(t) for t in traces]


@dataclass
class NodeCost:
    node: str
    usd: float = 0.0
    priced_spans: int = 0
    unpriced_spans: int = 0

    @property
    def complete(self) -> bool:
        return self.unpriced_spans == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "node": self.node,
            "usd": self.usd,
            "complete": self.complete,
            "priced_spans": self.priced_spans,
            "unpriced_spans": self.unpriced_spans,
        }


def cost_by_node(traces: Iterable[Trace]) -> dict[str, NodeCost]:
    out: dict[str, NodeCost] = {}
    for trace in traces:
        for span in trace.spans.values():
            if span.kind != P.KIND_LLM_CALL:
                continue
            cost = span_cost(trace, span)
            bucket = out.setdefault(cost.node, NodeCost(node=cost.node))
            if cost.usd is None:
                bucket.unpriced_spans += 1
            else:
                bucket.priced_spans += 1
                bucket.usd += cost.usd
    return out


# ---------------------------------------------------------------------------
# Critical path
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CriticalSegment:
    span_id: str
    name: str
    kind: str
    start: float
    end: float

    @property
    def ms(self) -> float:
        return (self.end - self.start) * 1000.0


@dataclass
class CriticalPath:
    """The chain of work that actually bounded the run's wall time.

    Not "the longest chain by summed duration" -- with a partly-parallel graph
    that number is meaningless, because sibling durations overlap and summing
    the biggest nodes can exceed the run's own wall time. This is the blocking
    path: walking backwards from the run's end, at each instant exactly one
    span is the thing everything else was waiting on. Of three concurrent
    reviewers only the last-finishing one is on the path; the other two cost
    nothing in latency terms. By construction the segments tile the run
    interval exactly, so ``total_ms`` equals the run's wall time and the
    per-span attributions sum to it.
    """

    trace_id: str
    segments: list[CriticalSegment] = field(default_factory=list)
    total_ms: float = 0.0

    def by_span(self) -> list[tuple[str, str, float]]:
        """``(span_id, name, ms)`` per span, largest contribution first."""
        agg: dict[str, tuple[str, float]] = {}
        for seg in self.segments:
            name, ms = agg.get(seg.span_id, (seg.name, 0.0))
            agg[seg.span_id] = (name, ms + seg.ms)
        rows = [(sid, name, ms) for sid, (name, ms) in agg.items()]
        rows.sort(key=lambda r: r[2], reverse=True)
        return rows

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "total_ms": self.total_ms,
            "spans": [
                {"span_id": sid, "name": name, "ms": ms} for sid, name, ms in self.by_span()
            ],
        }


def _display_name(trace: Trace, span: SpanRecord) -> str:
    """Node name for node spans; ``node > span`` for the calls inside one.

    Every ``llm_call`` span is named ``openai.chat``, so a critical path listing
    raw span names is eight identical rows. Qualifying by the owning node is
    what makes the listing actionable.
    """
    if span.kind == P.KIND_NODE or span.kind == P.KIND_RUN:
        return span.node_key
    owner = _owning_node(trace, span)
    return f"{owner} > {span.name}" if owner != span.node_key else span.node_key


def _walk_critical(trace: Trace, span: SpanRecord, lo: float, hi: float, out: list[CriticalSegment]) -> None:
    cursor = hi
    children = [c for c in trace.children(span.span_id) if c.interval is not None]
    children.sort(key=lambda c: c.interval[1], reverse=True)  # type: ignore[index]
    for child in children:
        c_start, c_end = child.interval  # type: ignore[misc]
        if c_end <= lo:
            break
        end = min(c_end, cursor)
        start = max(c_start, lo)
        if end <= start:
            continue  # entirely after the cursor: it was not blocking anything
        if end < cursor:
            out.append(CriticalSegment(span.span_id, _display_name(trace, span), span.kind, end, cursor))
        _walk_critical(trace, child, start, end, out)
        cursor = start
        if cursor <= lo:
            return
    if cursor > lo:
        out.append(CriticalSegment(span.span_id, _display_name(trace, span), span.kind, lo, cursor))


def critical_path(trace: Trace) -> CriticalPath:
    """Blocking path through one trace. See :class:`CriticalPath`."""
    root = trace.run_span()
    if root is None:
        roots = [s for s in trace.roots() if s.interval is not None]
        if not roots:
            return CriticalPath(trace_id=trace.trace_id)
        root = max(roots, key=lambda s: s.interval[1] - s.interval[0])  # type: ignore[index]
    interval = root.interval
    if interval is None:
        return CriticalPath(trace_id=trace.trace_id)
    segments: list[CriticalSegment] = []
    _walk_critical(trace, root, interval[0], interval[1], segments)
    segments.reverse()  # chronological
    return CriticalPath(
        trace_id=trace.trace_id,
        segments=segments,
        total_ms=sum(s.ms for s in segments),
    )


# ---------------------------------------------------------------------------
# Fan-out concurrency
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Concurrency:
    """What the parallelism actually bought, for one set of sibling spans.

    ``sum_ms`` is the work performed; ``union_ms`` is the wall time it occupied.
    ``speedup = sum/union`` is the real parallel gain (3.0 for three perfectly
    overlapping 10s reviewers; 1.0 if they secretly ran back to back).
    ``max_ms`` is the floor -- no amount of parallelism beats the slowest
    sibling -- and ``parent_wall_ms - union_ms`` is the orchestration overhead
    the fan-out itself cost.
    """

    parent_span_id: str
    parent_name: str
    sibling_count: int
    sum_ms: float
    union_ms: float
    max_ms: float
    parent_wall_ms: float | None
    names: list[str] = field(default_factory=list)
    #: True when this group is *all* of the parent's children. Only then does
    #: ``parent_wall_ms - union_ms`` mean "orchestration overhead"; in the real
    #: tree the reviewers share the run span with a 15-node sequential chain,
    #: so that subtraction would measure the chain, not the fan-out.
    covers_all_children: bool = True

    @property
    def speedup(self) -> float | None:
        return None if self.union_ms <= 0 else self.sum_ms / self.union_ms

    @property
    def saved_ms(self) -> float:
        return max(0.0, self.sum_ms - self.union_ms)

    @property
    def overhead_ms(self) -> float | None:
        if self.parent_wall_ms is None or not self.covers_all_children:
            return None
        return max(0.0, self.parent_wall_ms - self.union_ms)

    def to_dict(self) -> dict[str, Any]:
        return {
            "parent_span_id": self.parent_span_id,
            "parent_name": self.parent_name,
            "sibling_count": self.sibling_count,
            "siblings": list(self.names),
            "covers_all_children": self.covers_all_children,
            "sum_ms": self.sum_ms,
            "union_ms": self.union_ms,
            "max_ms": self.max_ms,
            "parent_wall_ms": self.parent_wall_ms,
            "speedup": self.speedup,
            "saved_ms": self.saved_ms,
            "overhead_ms": self.overhead_ms,
        }


def _concurrency(
    trace: Trace, parent: SpanRecord, children: Sequence[SpanRecord]
) -> Concurrency:
    intervals = [c.interval for c in children if c.interval is not None]
    return Concurrency(
        parent_span_id=parent.span_id,
        parent_name=parent.node_key,
        sibling_count=len(children),
        sum_ms=sum(c.wall_ms or 0.0 for c in children),
        union_ms=union_seconds(intervals) * 1000.0,
        max_ms=max((c.wall_ms or 0.0) for c in children),
        parent_wall_ms=parent.wall_ms,
        names=[c.node_key for c in children],
        covers_all_children=len(children) == len(trace._children.get(parent.span_id, [])),
    )


def sibling_concurrency(trace: Trace, parent: SpanRecord) -> Concurrency | None:
    """Concurrency over ALL of ``parent``'s direct children, or None if <2.

    Mixes sequential and parallel children, which is fine when the caller knows
    the parent is a pure fan-out. For a parent that has both -- the run span
    owns an 18-node sequential chain *and* the 3-way reviewer fan-out -- use
    :func:`fanout_concurrency`, which isolates the group that actually
    overlapped.
    """
    children = trace.children(parent.span_id)
    if len(children) < 2:
        return None
    return _concurrency(trace, parent, children)


def overlap_groups(trace: Trace, parent: SpanRecord) -> list[list[SpanRecord]]:
    """Partition ``parent``'s children into maximal sets of overlapping spans.

    A sweep over start times: a child joins the current group if it starts
    before the group's latest end. Sequential children (``a.end <= b.start``)
    therefore land in separate groups of one, so an 18-node chain contributes
    nothing and only the genuine fan-out survives.
    """
    children = [c for c in trace.children(parent.span_id) if c.interval is not None]
    children.sort(key=lambda c: c.interval[0])  # type: ignore[index]
    groups: list[list[SpanRecord]] = []
    group_end = float("-inf")
    for child in children:
        start, end = child.interval  # type: ignore[misc]
        if groups and start < group_end:
            groups[-1].append(child)
            group_end = max(group_end, end)
        else:
            groups.append([child])
            group_end = end
    return groups


def fanout_concurrency(trace: Trace, *, min_speedup: float = 1.05) -> list[Concurrency]:
    """Every genuinely-overlapping sibling group in the trace, best speedup first.

    ``min_speedup`` drops groups whose members barely touch; only real
    parallelism is interesting.
    """
    found: list[Concurrency] = []
    for span in trace.spans.values():
        for group in overlap_groups(trace, span):
            if len(group) < 2:
                continue
            stats = _concurrency(trace, span, group)
            speedup = stats.speedup
            if speedup is not None and speedup >= min_speedup:
                found.append(stats)
    found.sort(key=lambda c: c.speedup or 0.0, reverse=True)
    return found


# ---------------------------------------------------------------------------
# LLM-I/O share of wall time
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LlmShare:
    """How much of a run's wall time was spent inside ``llm_call`` spans.

    Two numbers, because concurrent LLM calls make one of them exceed 100%:
    ``union_ms`` is the wall time during which *at least one* call was in
    flight (this is the share that can be compared to 1.0), while ``sum_ms``
    is total time-in-calls and can legitimately exceed the run's wall time.
    """

    trace_id: str
    run_wall_ms: float | None
    sum_ms: float
    union_ms: float
    call_count: int

    @property
    def union_share(self) -> float | None:
        if not self.run_wall_ms:
            return None
        return self.union_ms / self.run_wall_ms

    @property
    def sum_share(self) -> float | None:
        if not self.run_wall_ms:
            return None
        return self.sum_ms / self.run_wall_ms

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "run_wall_ms": self.run_wall_ms,
            "llm_sum_ms": self.sum_ms,
            "llm_union_ms": self.union_ms,
            "call_count": self.call_count,
            "union_share": self.union_share,
            "sum_share": self.sum_share,
        }


def llm_io_share(trace: Trace) -> LlmShare:
    calls = [s for s in trace.spans.values() if s.kind == P.KIND_LLM_CALL]
    intervals = [s.interval for s in calls if s.interval is not None]
    return LlmShare(
        trace_id=trace.trace_id,
        run_wall_ms=trace.wall_ms(),
        sum_ms=sum(s.wall_ms or 0.0 for s in calls),
        union_ms=union_seconds(intervals) * 1000.0,
        call_count=len(calls),
    )


__all__ = [
    "Concurrency",
    "CriticalPath",
    "CriticalSegment",
    "DEFAULT_MIN_N",
    "LlmShare",
    "NodeCost",
    "NodeLatency",
    "Percentiles",
    "RunCost",
    "SelfTime",
    "SpanCost",
    "TokenBucket",
    "cost_by_node",
    "critical_path",
    "default_key",
    "fanout_concurrency",
    "llm_io_share",
    "merge_intervals",
    "merged_key",
    "nearest_rank",
    "node_latency",
    "overlap_groups",
    "percentiles",
    "run_cost",
    "run_costs",
    "self_time",
    "sibling_concurrency",
    "span_cost",
    "token_totals",
    "tokens_by_model",
    "tokens_by_node",
    "union_seconds",
]

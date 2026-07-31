"""Summaries over a completed load run.

Percentiles are not reimplemented here. ``trace_report.metrics.percentiles``
already refuses p90/p95/p99 below n=10/20/100 and uses nearest rank so every
printed number is an observed measurement; importing it means the n-floor cannot
drift between the two harnesses.

Two throughput numbers, never one:

``throughput``  completed-OK requests per second over the measurement window.
``goodput``     completed-OK-**and-within-SLO** requests per second.

They are the same number at low load and diverge sharply once queueing starts.
The lambda at which throughput is still climbing while goodput has turned over
is the operating point past which the service is doing more work and delivering
less value, and reporting throughput alone hides it completely.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from trace_report.metrics import Percentiles, percentiles  # noqa: E402

from .loadmodel import LoadModel, RequestRecord, RunResult

__all__ = ["Summary", "summarize", "fmt_seconds", "table"]


@dataclass
class Summary:
    """A load-run result that cannot be quoted without its load model."""

    model: LoadModel
    n_offered: int
    n_warmup_discarded: int
    n_measured: int
    n_ok: int
    n_failed: int
    n_within_slo: int
    window_seconds: float
    throughput: float
    goodput: float
    offered_rate: float
    achieved_rate: float
    response: Percentiles          # scheduled-arrival -> completion (seconds)
    service: Percentiles           # start -> completion (seconds)
    queue: Percentiles             # scheduled-arrival -> start (seconds)
    max_in_flight: int
    mean_in_flight: float
    errors: dict[str, int] = field(default_factory=dict)
    extra: dict = field(default_factory=dict)

    @property
    def slo_attainment(self) -> float | None:
        if self.n_measured == 0:
            return None
        return self.n_within_slo / self.n_measured

    def to_dict(self) -> dict:
        return {
            "load_model": self.model.to_dict(),
            "config_hash": self.model.config_hash(),
            "load_model_description": self.model.describe(),
            "n_offered": self.n_offered,
            "n_warmup_discarded": self.n_warmup_discarded,
            "n_measured": self.n_measured,
            "n_ok": self.n_ok,
            "n_failed": self.n_failed,
            "n_within_slo": self.n_within_slo,
            "slo_attainment": self.slo_attainment,
            "window_seconds": round(self.window_seconds, 4),
            "throughput_rps": round(self.throughput, 5),
            "goodput_rps": round(self.goodput, 5),
            "offered_rate_rps": round(self.offered_rate, 5),
            "achieved_rate_rps": round(self.achieved_rate, 5),
            "response_seconds": self.response.to_dict(),
            "service_seconds": self.service.to_dict(),
            "queue_seconds": self.queue.to_dict(),
            "max_in_flight": self.max_in_flight,
            "mean_in_flight": round(self.mean_in_flight, 3),
            "errors": self.errors,
            **self.extra,
        }


def _measured(records: Sequence[RequestRecord]) -> list[RequestRecord]:
    """Warmup is excluded here and nowhere else, so it cannot be half-applied."""
    return [r for r in records if not r.warmup]


def summarize(result: RunResult, *, extra: dict | None = None) -> Summary:
    model = result.model
    measured = _measured(result.records)
    ok = [r for r in measured if r.ok]
    failed = [r for r in measured if not r.ok]

    slo = model.slo_seconds
    within = [r for r in ok if r.response_seconds <= slo]

    # Measurement window: first measured arrival to last measured completion.
    # Using arrivals rather than starts means a request that sat in a queue for
    # 40s still counts its queueing time against the window, so throughput is
    # not flattered by backlog.
    if measured:
        window = max(r.finished for r in measured) - min(r.scheduled for r in measured)
    else:
        window = 0.0
    window = max(window, 1e-9)

    if model.mode == "open" and model.rate:
        offered = float(model.rate)
    elif measured:
        offered = len(measured) / window
    else:
        offered = 0.0

    depths = [d for _, d in result.in_flight_samples]
    errors: dict[str, int] = {}
    for r in failed:
        key = (r.error or "unknown").split(":")[0]
        errors[key] = errors.get(key, 0) + 1

    return Summary(
        model=model,
        n_offered=len(result.records),
        n_warmup_discarded=len(result.records) - len(measured),
        n_measured=len(measured),
        n_ok=len(ok),
        n_failed=len(failed),
        n_within_slo=len(within),
        window_seconds=window,
        throughput=len(ok) / window,
        goodput=len(within) / window,
        offered_rate=offered,
        achieved_rate=len(measured) / window,
        response=percentiles(r.response_seconds for r in ok),
        service=percentiles(r.service_seconds for r in ok),
        queue=percentiles(r.queue_seconds for r in ok),
        max_in_flight=max(depths) if depths else 0,
        mean_in_flight=(sum(depths) / len(depths)) if depths else 0.0,
        errors=errors,
        extra=extra or {},
    )


def fmt_seconds(p: Percentiles, name: str) -> str:
    """``12.4`` or ``n/a (n=7 < 100)``. Never a bare blank, never a silent zero."""
    if name in p.refused:
        return f"n/a ({p.refused[name]})"
    v = p.get(name)
    return "no data" if v is None else f"{v:,.2f}"


_COLUMNS = [
    ("load model", 46),
    ("n", 5),
    ("ok", 5),
    ("p50", 9),
    ("p90", 9),
    ("p95", 9),
    ("p99", 15),
    ("thru/s", 8),
    ("good/s", 8),
    ("SLO%", 7),
    ("maxIF", 6),
]


def table(summaries: Sequence[Summary], *, latency: str = "response") -> str:
    """Fixed-width table. The load model is column 1 because it is not optional."""
    head = " | ".join(h.ljust(w) for h, w in _COLUMNS)
    rows = [head, "-" * len(head)]
    for s in summaries:
        p = getattr(s, latency)
        if s.model.mode == "open":
            label = f"open lam={s.model.rate:g} {s.model.llm}"
        else:
            label = f"closed c={s.model.concurrency} {s.model.llm}"
        if s.model.serial_reviewers:
            label += " serial-rev"
        att = s.slo_attainment
        cells = [
            label,
            str(s.n_measured),
            str(s.n_ok),
            fmt_seconds(p, "p50"),
            fmt_seconds(p, "p90"),
            fmt_seconds(p, "p95"),
            fmt_seconds(p, "p99"),
            f"{s.throughput:.4f}",
            f"{s.goodput:.4f}",
            "n/a" if att is None else f"{att * 100:.0f}%",
            str(s.max_in_flight),
        ]
        rows.append(" | ".join(c.ljust(w) for c, (_, w) in zip(cells, _COLUMNS)))
    return "\n".join(rows)

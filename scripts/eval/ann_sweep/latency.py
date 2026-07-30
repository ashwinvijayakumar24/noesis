"""Latency statistics, and the method statement that makes them quotable.

A latency number without its method is not a measurement, it is a rumour. Every
value this module produces travels inside a ``LatencyStats`` that carries how
many queries, how many repetitions, how many warmup runs were discarded, and
whether the clock was server-side or client-side. Nothing downstream can print
a p50 without printing where it came from.

NO p99. With 59 queries x 3 timed repetitions there are 177 samples; the 99th
percentile is the 176th of 177 values, i.e. one sample away from the maximum.
Its confidence interval is wider than the effect being measured, so quoting it
would be a fabrication dressed as precision. p50 and p95 only.

PERCENTILE CONVENTION: nearest-rank on the sorted sample, ``ceil(q * n)``, 1-based.
No interpolation. On a 177-sample set, p50 is the 89th value and p95 the 169th.
Stated because numpy's default (linear interpolation) gives a different answer
and silent disagreement between two "p95"s is worse than either.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

#: Server-side: Postgres' own EXPLAIN ANALYZE "Execution Time". Excludes planning,
#: excludes the client round trip, excludes psycopg2 result materialisation.
CLOCK_SERVER = "server_side_explain_analyze_execution_time"
#: Client-side: wall clock around cursor.execute + fetchall. Includes the loopback
#: round trip, which on this corpus is comparable to the query itself.
CLOCK_CLIENT = "client_side_round_trip"


@dataclass(frozen=True)
class LatencyStats:
    """Percentiles plus the method that produced them. Never separate the two."""

    p50_ms: float
    p95_ms: float
    mean_ms: float
    min_ms: float
    max_ms: float
    n_samples: int
    n_queries: int
    n_repetitions: int
    n_warmup_discarded: int
    clock: str
    percentile_method: str = "nearest_rank_ceil"
    #: Deliberately absent: p99. See module docstring.
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def method_statement(self) -> str:
        return (
            f"{self.n_samples} samples = {self.n_queries} queries x "
            f"{self.n_repetitions} timed repetition(s); "
            f"{self.n_warmup_discarded} warmup run(s) per query discarded; "
            f"clock = {self.clock}; percentiles = {self.percentile_method} "
            f"(no p99 -- n too small)"
        )


def percentile(samples: list[float], q: float) -> float:
    """Nearest-rank percentile. ``q`` in [0, 1].

    Nearest-rank rather than interpolated so that every reported value is an
    OBSERVED latency, not a weighted average of two observations that never
    happened.
    """
    if not samples:
        raise ValueError("percentile() of an empty sample is undefined, not 0.0")
    if not 0.0 <= q <= 1.0:
        raise ValueError(f"q must be in [0, 1], got {q}")
    ordered = sorted(samples)
    if q == 0.0:
        return float(ordered[0])
    rank = math.ceil(q * len(ordered))
    return float(ordered[min(rank, len(ordered)) - 1])


def summarise(
    samples: list[float],
    n_queries: int,
    n_repetitions: int,
    n_warmup_discarded: int,
    clock: str = CLOCK_SERVER,
    notes: list[str] | None = None,
) -> LatencyStats:
    """Build a LatencyStats from raw per-execution millisecond timings."""
    if not samples:
        raise ValueError(
            "Refusing to summarise zero latency samples. An empty sample is not "
            "a latency of 0 ms; it means the measurement did not run."
        )
    return LatencyStats(
        p50_ms=round(percentile(samples, 0.50), 4),
        p95_ms=round(percentile(samples, 0.95), 4),
        mean_ms=round(sum(samples) / len(samples), 4),
        min_ms=round(min(samples), 4),
        max_ms=round(max(samples), 4),
        n_samples=len(samples),
        n_queries=n_queries,
        n_repetitions=n_repetitions,
        n_warmup_discarded=n_warmup_discarded,
        clock=clock,
        notes=list(notes or []),
    )

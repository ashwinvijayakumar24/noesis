"""Load models and schedulers. No measurement here -- only how work arrives.

A latency number without its load model is unquotable, so the load model is a
first-class object that travels with every result and is part of the config
hash. Two models are implemented because the difference between them *is* a
result:

**Open loop.** Arrivals are a Poisson process at rate lambda, generated from a
schedule fixed before the run starts. A request is issued at its scheduled time
whether or not the previous one finished. In-flight count is unbounded. This is
what a queue in front of a service actually looks like, and it is the only one
of the two that can show a latency blow-up.

**Closed loop.** A fixed number of workers, each issuing its next request only
after its previous one returned. Offered load is therefore throttled by the
system under test: when the service slows down, the load generator politely
slows down too and the queueing delay is never sampled. That is **coordinated
omission**, and the p99 gap between the two models is the size of the lie a
closed-loop-only benchmark tells.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import random
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Literal

Mode = Literal["open", "closed"]

#: One unit of work. Takes the request index, returns anything; raising counts
#: as a failure. The scheduler never inspects the return value.
Workload = Callable[[int], Awaitable[object]]


# ---------------------------------------------------------------------------
# Arrival process
# ---------------------------------------------------------------------------

def poisson_interarrivals(rate: float, n: int, rng: random.Random) -> list[float]:
    """``n`` exponential inter-arrival gaps with mean ``1/rate`` seconds.

    Exponential gaps are the definition of a Poisson process; there is no
    separate "Poisson sampler" to get wrong. Mean gap is 1/lambda, so over a
    large sample the realized arrival rate converges on lambda.
    """
    if rate <= 0:
        raise ValueError(f"rate must be > 0, got {rate}")
    if n < 0:
        raise ValueError(f"n must be >= 0, got {n}")
    return [rng.expovariate(rate) for _ in range(n)]


def arrival_schedule(rate: float, n: int, rng: random.Random) -> list[float]:
    """Absolute arrival offsets (seconds from t=0) for ``n`` Poisson arrivals.

    The first arrival is at t=0 so a run of n=1 is not dominated by a random
    initial wait; the remaining n-1 gaps are exponential.
    """
    offsets: list[float] = []
    t = 0.0
    for gap in [0.0] + poisson_interarrivals(rate, max(0, n - 1), rng):
        t += gap
        offsets.append(t)
    return offsets


# ---------------------------------------------------------------------------
# The load model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LoadModel:
    """Everything needed to reproduce how work was offered.

    ``config_hash`` covers all of it. Results keyed by that hash cannot silently
    merge an open-loop run with a closed-loop one.
    """

    mode: Mode
    n_requests: int
    warmup_requests: int = 0
    rate: float | None = None          # open loop only, req/s
    concurrency: int | None = None     # closed loop only
    slo_seconds: float = 60.0
    seed: int = 1234
    llm: Literal["stub", "real"] = "stub"
    serial_reviewers: bool = False
    workload: str = "graph"
    notes: str = ""

    def __post_init__(self) -> None:
        if self.mode == "open":
            if not self.rate or self.rate <= 0:
                raise ValueError("open-loop load model requires rate > 0")
        elif self.mode == "closed":
            if not self.concurrency or self.concurrency < 1:
                raise ValueError("closed-loop load model requires concurrency >= 1")
        else:  # pragma: no cover - guarded by the Literal in practice
            raise ValueError(f"unknown mode {self.mode!r}")
        if self.warmup_requests >= self.n_requests:
            raise ValueError(
                f"warmup_requests={self.warmup_requests} would discard every one of "
                f"n_requests={self.n_requests}; nothing would be measured"
            )

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "n_requests": self.n_requests,
            "warmup_requests": self.warmup_requests,
            "rate": self.rate,
            "concurrency": self.concurrency,
            "slo_seconds": self.slo_seconds,
            "seed": self.seed,
            "llm": self.llm,
            "serial_reviewers": self.serial_reviewers,
            "workload": self.workload,
        }

    def config_hash(self) -> str:
        blob = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode()).hexdigest()[:12]

    def describe(self) -> str:
        """The one-line provenance string that must accompany every number."""
        if self.mode == "open":
            load = f"open-loop Poisson lambda={self.rate:g}/s"
        else:
            load = f"closed-loop concurrency={self.concurrency}"
        return (
            f"{load}, n={self.n_requests} "
            f"(warmup {self.warmup_requests} discarded), "
            f"LLM={self.llm}, reviewers={'serial' if self.serial_reviewers else 'parallel'}, "
            f"SLO={self.slo_seconds:g}s, seed={self.seed}, cfg={self.config_hash()}"
        )


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

@dataclass
class RequestRecord:
    """One offered request. ``scheduled`` is the load model's intent, ``started``
    is when the system actually picked it up; the gap is queueing delay and is
    structurally zero in closed loop."""

    index: int
    scheduled: float
    started: float
    finished: float
    ok: bool
    warmup: bool
    in_flight_at_start: int
    error: str | None = None
    detail: dict = field(default_factory=dict)

    @property
    def service_seconds(self) -> float:
        return self.finished - self.started

    @property
    def queue_seconds(self) -> float:
        """Generator-side delay: schedule slip before the request was admitted.

        Deliberately NOT the system's internal queueing. The graph is in-process
        and admits every arrival immediately, then blocks on its own semaphores
        -- so the wait lands in ``service_seconds``. This number is a health
        check on the load generator: if it is not near zero, the generator could
        not keep up and the run is void, not a result about the service.
        """
        return max(0.0, self.started - self.scheduled)

    @property
    def response_seconds(self) -> float:
        """Scheduled-arrival to completion. The only latency a user would feel.

        Open loop measures this honestly. Closed loop cannot: its ``scheduled``
        is by construction the moment a worker became free, so response time
        collapses onto service time.
        """
        return self.finished - self.scheduled

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "scheduled": round(self.scheduled, 6),
            "started": round(self.started, 6),
            "finished": round(self.finished, 6),
            "queue_s": round(self.queue_seconds, 6),
            "service_s": round(self.service_seconds, 6),
            "response_s": round(self.response_seconds, 6),
            "ok": self.ok,
            "warmup": self.warmup,
            "in_flight_at_start": self.in_flight_at_start,
            "error": self.error,
            **({"detail": self.detail} if self.detail else {}),
        }


@dataclass
class RunResult:
    model: LoadModel
    records: list[RequestRecord]
    in_flight_samples: list[tuple[float, int]]
    started_at: float
    ended_at: float

    @property
    def wall_seconds(self) -> float:
        return self.ended_at - self.started_at


# ---------------------------------------------------------------------------
# Schedulers
# ---------------------------------------------------------------------------

class _InFlight:
    """Concurrency counter plus a periodic sampler, so queue depth is observed
    rather than inferred from completion timestamps after the fact."""

    def __init__(self) -> None:
        self.value = 0
        self.peak = 0
        self.samples: list[tuple[float, int]] = []

    def enter(self) -> int:
        self.value += 1
        self.peak = max(self.peak, self.value)
        return self.value

    def exit(self) -> None:
        self.value -= 1

    async def sample_forever(self, t0: float, interval: float, stop: asyncio.Event) -> None:
        while not stop.is_set():
            self.samples.append((time.perf_counter() - t0, self.value))
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                continue


async def _invoke(
    workload: Workload,
    index: int,
    scheduled: float,
    t0: float,
    warmup: bool,
    inflight: _InFlight,
    sink: list[RequestRecord],
) -> None:
    depth = inflight.enter()
    started = time.perf_counter() - t0
    ok, err, detail = True, None, {}
    try:
        result = await workload(index)
        if isinstance(result, dict):
            detail = result
    except Exception as exc:  # a failed request is data, not a crash
        ok, err = False, f"{type(exc).__name__}: {exc}"[:400]
    finally:
        inflight.exit()
    sink.append(
        RequestRecord(
            index=index,
            scheduled=scheduled,
            started=started,
            finished=time.perf_counter() - t0,
            ok=ok,
            warmup=warmup,
            in_flight_at_start=depth,
            error=err,
            detail=detail,
        )
    )


async def run_open_loop(
    workload: Workload,
    model: LoadModel,
    *,
    sample_interval: float = 0.25,
) -> RunResult:
    """Issue requests on a pre-computed Poisson schedule, regardless of backlog.

    The schedule is fixed before the first request is issued. If the system
    cannot keep up, arrivals pile up and in-flight grows -- which is the whole
    point. Nothing here ever waits for a completion before issuing the next
    arrival.
    """
    assert model.mode == "open" and model.rate
    rng = random.Random(model.seed)
    offsets = arrival_schedule(model.rate, model.n_requests, rng)

    inflight = _InFlight()
    records: list[RequestRecord] = []
    stop = asyncio.Event()
    t0 = time.perf_counter()
    sampler = asyncio.create_task(inflight.sample_forever(t0, sample_interval, stop))

    tasks: list[asyncio.Task] = []
    for i, offset in enumerate(offsets):
        delay = offset - (time.perf_counter() - t0)
        if delay > 0:
            await asyncio.sleep(delay)
        tasks.append(
            asyncio.create_task(
                _invoke(
                    workload, i, offset, t0,
                    warmup=i < model.warmup_requests,
                    inflight=inflight, sink=records,
                )
            )
        )
    if tasks:
        await asyncio.gather(*tasks)
    stop.set()
    await sampler

    ended = time.perf_counter()
    records.sort(key=lambda r: r.index)
    return RunResult(model, records, inflight.samples, 0.0, ended - t0)


async def run_closed_loop(
    workload: Workload,
    model: LoadModel,
    *,
    sample_interval: float = 0.25,
) -> RunResult:
    """``concurrency`` workers in lockstep with the system under test.

    Each worker issues its next request the instant its previous one returns, so
    the offered rate is whatever the system happens to sustain. No arrival can
    ever queue behind another arrival from the same worker, which is exactly the
    omission this model is here to demonstrate.
    """
    assert model.mode == "closed" and model.concurrency
    inflight = _InFlight()
    records: list[RequestRecord] = []
    stop = asyncio.Event()
    t0 = time.perf_counter()
    sampler = asyncio.create_task(inflight.sample_forever(t0, sample_interval, stop))

    counter = {"next": 0}

    async def worker() -> None:
        while True:
            i = counter["next"]
            if i >= model.n_requests:
                return
            counter["next"] = i + 1
            # In closed loop the "arrival" is the moment this worker became
            # free. Recording it as `scheduled` is what makes queue delay zero.
            scheduled = time.perf_counter() - t0
            await _invoke(
                workload, i, scheduled, t0,
                warmup=i < model.warmup_requests,
                inflight=inflight, sink=records,
            )

    await asyncio.gather(*(worker() for _ in range(model.concurrency)))
    stop.set()
    await sampler

    ended = time.perf_counter()
    records.sort(key=lambda r: r.index)
    return RunResult(model, records, inflight.samples, 0.0, ended - t0)


async def run_load(workload: Workload, model: LoadModel, **kw) -> RunResult:
    if model.mode == "open":
        return await run_open_loop(workload, model, **kw)
    return await run_closed_loop(workload, model, **kw)

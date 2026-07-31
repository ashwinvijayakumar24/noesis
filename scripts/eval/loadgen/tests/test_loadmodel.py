"""The load model itself: arrivals, the two schedulers, warmup, config identity."""

from __future__ import annotations

import asyncio
import random
import statistics

import pytest

from loadgen.loadmodel import (
    LoadModel,
    arrival_schedule,
    poisson_interarrivals,
    run_closed_loop,
    run_open_loop,
)
from loadgen.workload import SyntheticGraphWorkload


# --------------------------------------------------------------------------
# Arrival process
# --------------------------------------------------------------------------

@pytest.mark.parametrize("rate", [0.5, 2.0, 10.0])
def test_poisson_sampler_realizes_the_requested_mean_rate(rate):
    """Mean gap must converge on 1/lambda -- otherwise every lambda we label a
    result with is a lie about what was actually offered."""
    gaps = poisson_interarrivals(rate, 200_000, random.Random(11))
    mean_gap = statistics.fmean(gaps)
    assert mean_gap == pytest.approx(1.0 / rate, rel=0.01)
    # Exponential has CV exactly 1; a sampler that got the mean right by
    # emitting a constant would pass the check above and fail this one.
    assert statistics.stdev(gaps) / mean_gap == pytest.approx(1.0, rel=0.02)


def test_poisson_sampler_is_seed_reproducible():
    a = poisson_interarrivals(3.0, 500, random.Random(5))
    b = poisson_interarrivals(3.0, 500, random.Random(5))
    assert a == b


def test_arrival_schedule_is_monotonic_and_starts_at_zero():
    offsets = arrival_schedule(4.0, 1000, random.Random(2))
    assert offsets[0] == 0.0
    assert all(b >= a for a, b in zip(offsets, offsets[1:]))
    assert offsets[-1] == pytest.approx(999 / 4.0, rel=0.15)


def test_rate_must_be_positive():
    with pytest.raises(ValueError):
        poisson_interarrivals(0.0, 10, random.Random(1))


# --------------------------------------------------------------------------
# Open vs closed loop on a known service time
# --------------------------------------------------------------------------

def test_open_and_closed_loop_diverge_on_a_saturated_service():
    """A capacity-1 service offered load above its capacity.

    Service time is 0.05s, capacity 1, so the service can do 20 req/s. Offer
    40 req/s open-loop and a backlog must build: response time climbs without
    bound while service time stays flat. Closed loop with 1 worker offers
    exactly 20 req/s by construction and therefore never sees the backlog --
    that difference is coordinated omission, and it must show up here or the
    whole comparison in LATENCY.md is unfounded.
    """
    service = 0.05

    open_model = LoadModel(mode="open", rate=40.0, n_requests=60, warmup_requests=0, seed=3)
    open_result = asyncio.run(
        run_open_loop(SyntheticGraphWorkload(service, capacity=1), open_model,
                      sample_interval=0.02)
    )
    closed_model = LoadModel(mode="closed", concurrency=1, n_requests=60,
                             warmup_requests=0, seed=3)
    closed_result = asyncio.run(
        run_closed_loop(SyntheticGraphWorkload(service, capacity=1), closed_model,
                        sample_interval=0.02)
    )

    open_resp = sorted(r.response_seconds for r in open_result.records)
    closed_resp = sorted(r.response_seconds for r in closed_result.records)

    # Closed loop cannot queue: response time IS service time, so its tail sits
    # on top of the true service time no matter how much load is "offered".
    assert max(closed_resp) < service * 4

    # Open loop must have built a backlog. The wait is *inside* the system under
    # test (its own semaphore), so it lands in service time rather than in
    # generator-side queue time -- but the response time a user would feel is
    # the one that blows up, and it does.
    assert max(open_resp) > max(closed_resp) * 5
    assert open_resp[-1] > service * 10
    # Generator-side queue delay must stay negligible; if it did not, the load
    # generator itself would be the bottleneck and the run would be void.
    assert max(r.queue_seconds for r in open_result.records) < service


def test_open_loop_does_not_wait_for_completions():
    """The defining property: arrivals are issued on schedule regardless of
    backlog, so in-flight exceeds the service's capacity."""
    model = LoadModel(mode="open", rate=50.0, n_requests=40, warmup_requests=0, seed=9)
    result = asyncio.run(
        run_open_loop(SyntheticGraphWorkload(0.2), model, sample_interval=0.01)
    )
    assert max(r.in_flight_at_start for r in result.records) > 5


def test_closed_loop_never_exceeds_its_worker_count():
    wl = SyntheticGraphWorkload(0.02)
    model = LoadModel(mode="closed", concurrency=3, n_requests=30, warmup_requests=0)
    asyncio.run(run_closed_loop(wl, model, sample_interval=0.005))
    assert wl.max_concurrent <= 3


def test_every_offered_request_is_recorded_exactly_once():
    model = LoadModel(mode="open", rate=200.0, n_requests=50, warmup_requests=0)
    result = asyncio.run(run_open_loop(SyntheticGraphWorkload(0.01), model))
    assert sorted(r.index for r in result.records) == list(range(50))


def test_a_raising_workload_is_a_failed_request_not_a_crash():
    async def boom(index):
        if index % 2 == 0:
            raise RuntimeError("nope")
        return {}

    model = LoadModel(mode="closed", concurrency=2, n_requests=10, warmup_requests=0)
    result = asyncio.run(run_closed_loop(boom, model))
    assert sum(1 for r in result.records if not r.ok) == 5
    assert all(r.error and "RuntimeError" in r.error for r in result.records if not r.ok)


# --------------------------------------------------------------------------
# Config identity
# --------------------------------------------------------------------------

def test_config_hash_separates_the_load_models():
    a = LoadModel(mode="open", rate=0.05, n_requests=100)
    b = LoadModel(mode="closed", concurrency=2, n_requests=100)
    c = LoadModel(mode="open", rate=0.10, n_requests=100)
    d = LoadModel(mode="open", rate=0.05, n_requests=100, serial_reviewers=True)
    e = LoadModel(mode="open", rate=0.05, n_requests=100, llm="real")
    hashes = {m.config_hash() for m in (a, b, c, d, e)}
    assert len(hashes) == 5
    assert LoadModel(mode="open", rate=0.05, n_requests=100).config_hash() == a.config_hash()


def test_describe_names_every_thing_a_quoted_number_needs():
    text = LoadModel(mode="open", rate=0.05, n_requests=120, warmup_requests=8).describe()
    for token in ("open-loop", "lambda=0.05", "n=120", "warmup 8", "LLM=stub", "SLO="):
        assert token in text


def test_warmup_cannot_consume_the_whole_run():
    with pytest.raises(ValueError, match="nothing would be measured"):
        LoadModel(mode="open", rate=1.0, n_requests=10, warmup_requests=10)


def test_open_loop_requires_a_rate_and_closed_a_concurrency():
    with pytest.raises(ValueError):
        LoadModel(mode="open", n_requests=10)
    with pytest.raises(ValueError):
        LoadModel(mode="closed", n_requests=10)

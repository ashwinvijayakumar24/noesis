"""Warmup exclusion, the percentile n-floor, and goodput vs throughput."""

from __future__ import annotations

import pytest

from loadgen.loadmodel import LoadModel, RequestRecord, RunResult
from loadgen.stats import fmt_seconds, summarize, table


def _result(model: LoadModel, latencies, *, warmup=0, scheduled=None, ok=None) -> RunResult:
    """Records whose response times are exactly ``latencies``."""
    recs = []
    t = 0.0
    for i, lat in enumerate(latencies):
        s = t if scheduled is None else scheduled[i]
        recs.append(RequestRecord(
            index=i, scheduled=s, started=s, finished=s + lat,
            ok=True if ok is None else ok[i],
            warmup=i < warmup, in_flight_at_start=1,
        ))
        t += 1.0
    return RunResult(model, recs, [(0.0, 1), (1.0, 2)], 0.0, t + max(latencies))


# --------------------------------------------------------------------------
# Warmup
# --------------------------------------------------------------------------

def test_warmup_requests_are_excluded_from_every_statistic():
    """The warmup requests here are 100x slower than the rest. If any statistic
    still sees them the numbers move enormously, so this is a sharp test."""
    model = LoadModel(mode="closed", concurrency=1, n_requests=10, warmup_requests=3)
    s = summarize(_result(model, [500.0, 500.0, 500.0] + [1.0] * 7, warmup=3))

    assert s.n_offered == 10
    assert s.n_warmup_discarded == 3
    assert s.n_measured == 7
    assert s.response.n == 7
    assert s.response.max == pytest.approx(1.0)
    assert s.response.mean == pytest.approx(1.0)


def test_a_run_with_no_warmup_discards_nothing():
    model = LoadModel(mode="closed", concurrency=1, n_requests=5)
    s = summarize(_result(model, [1.0] * 5))
    assert s.n_warmup_discarded == 0
    assert s.n_measured == 5


# --------------------------------------------------------------------------
# Percentile floor
# --------------------------------------------------------------------------

def test_p99_is_refused_below_n_100_and_says_why():
    model = LoadModel(mode="closed", concurrency=1, n_requests=99)
    s = summarize(_result(model, [float(i) for i in range(99)]))
    assert s.response.get("p99") is None
    assert s.response.refused["p99"] == "n=99 < 100"
    assert fmt_seconds(s.response, "p99") == "n/a (n=99 < 100)"
    assert "n/a (n=99 < 100)" in table([s])


def test_p99_is_reported_at_exactly_n_100():
    model = LoadModel(mode="closed", concurrency=1, n_requests=100)
    s = summarize(_result(model, [float(i) for i in range(100)]))
    # Nearest rank: ceil(0.99*100) = 99th smallest of 0..99, i.e. 98.0.
    assert s.response.get("p99") == pytest.approx(98.0)
    assert "p99" not in s.response.refused


@pytest.mark.parametrize("n,quantile,refused", [
    (9, "p90", True), (10, "p90", False),
    (19, "p95", True), (20, "p95", False),
])
def test_each_quantile_has_its_own_floor(n, quantile, refused):
    model = LoadModel(mode="closed", concurrency=1, n_requests=n)
    s = summarize(_result(model, [1.0] * n))
    assert (quantile in s.response.refused) is refused


# --------------------------------------------------------------------------
# Goodput vs throughput
# --------------------------------------------------------------------------

def test_goodput_and_throughput_diverge_when_the_slo_is_missed():
    """Constructed so the divergence is unambiguous: 20 requests all complete
    successfully inside a 10s window (throughput 2.0/s), but 15 of them breach a
    5s SLO, so goodput is 0.5/s. Reporting throughput alone would call this a
    healthy 2 req/s."""
    model = LoadModel(mode="open", rate=2.0, n_requests=20, slo_seconds=5.0)
    latencies = [1.0] * 5 + [30.0] * 15
    scheduled = [i * 0.5 for i in range(20)]
    recs = []
    for i, (lat, sch) in enumerate(zip(latencies, scheduled)):
        recs.append(RequestRecord(index=i, scheduled=sch, started=sch,
                                  finished=sch + lat, ok=True, warmup=False,
                                  in_flight_at_start=1))
    # Window: first arrival 0.0 -> last completion 9.5+30 = 39.5
    s = summarize(RunResult(model, recs, [], 0.0, 39.5))

    assert s.n_ok == 20
    assert s.n_within_slo == 5
    assert s.throughput == pytest.approx(20 / 39.5)
    assert s.goodput == pytest.approx(5 / 39.5)
    assert s.goodput < s.throughput
    assert s.slo_attainment == pytest.approx(0.25)


def test_goodput_equals_throughput_when_everything_meets_the_slo():
    model = LoadModel(mode="open", rate=1.0, n_requests=10, slo_seconds=60.0)
    s = summarize(_result(model, [2.0] * 10))
    assert s.goodput == pytest.approx(s.throughput)
    assert s.slo_attainment == 1.0


def test_a_failed_request_counts_in_neither_throughput_nor_goodput():
    model = LoadModel(mode="closed", concurrency=1, n_requests=10, slo_seconds=60.0)
    s = summarize(_result(model, [1.0] * 10, ok=[True] * 6 + [False] * 4))
    assert s.n_ok == 6
    assert s.n_failed == 4
    assert s.n_within_slo == 6


def test_summary_carries_its_load_model_into_the_serialized_record():
    model = LoadModel(mode="open", rate=0.05, n_requests=10, warmup_requests=2)
    d = summarize(_result(model, [1.0] * 10, warmup=2)).to_dict()
    assert d["load_model"]["mode"] == "open"
    assert d["load_model"]["rate"] == 0.05
    assert d["config_hash"] == model.config_hash()
    assert "open-loop" in d["load_model_description"]
    assert d["n_warmup_discarded"] == 2


def test_table_names_the_load_model_in_the_first_column():
    open_s = summarize(_result(LoadModel(mode="open", rate=0.05, n_requests=5), [1.0] * 5))
    closed_s = summarize(_result(LoadModel(mode="closed", concurrency=4, n_requests=5), [1.0] * 5))
    rendered = table([open_s, closed_s])
    assert "open lam=0.05" in rendered
    assert "closed c=4" in rendered

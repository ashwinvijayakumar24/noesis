"""Latency statistics on known inputs. Pure -- no database, no timing."""

from __future__ import annotations

import pytest

from scripts.eval.ann_sweep.latency import (
    CLOCK_CLIENT,
    CLOCK_SERVER,
    LatencyStats,
    percentile,
    summarise,
)


class TestPercentile:
    def test_nearest_rank_on_one_to_hundred(self):
        """ceil(q*n) on 1..100 is exactly q*100 -- the canonical check."""
        s = list(range(1, 101))
        assert percentile(s, 0.50) == 50
        assert percentile(s, 0.95) == 95

    def test_returns_an_observed_value_not_an_interpolation(self):
        """Every reported latency must be a latency that actually happened."""
        s = [1.0, 2.0, 3.0, 4.0]
        assert percentile(s, 0.50) in s
        assert percentile(s, 0.95) in s
        assert percentile(s, 0.50) == 2.0  # ceil(0.5*4)=2 -> 2nd value

    def test_input_order_does_not_matter(self):
        assert percentile([9, 1, 5, 3, 7], 0.5) == percentile([1, 3, 5, 7, 9], 0.5) == 5

    def test_p100_is_the_max_and_p0_is_the_min(self):
        s = [4.0, 1.0, 9.0]
        assert percentile(s, 1.0) == 9.0
        assert percentile(s, 0.0) == 1.0

    def test_single_sample(self):
        assert percentile([7.5], 0.5) == percentile([7.5], 0.95) == 7.5

    def test_177_samples_p50_is_the_89th_and_p95_the_169th(self):
        """The exact shape of a real run: 59 queries x 3 repetitions."""
        s = [float(i) for i in range(1, 178)]
        assert percentile(s, 0.50) == 89.0
        assert percentile(s, 0.95) == 169.0

    def test_empty_sample_raises_rather_than_reporting_zero(self):
        with pytest.raises(ValueError, match="empty"):
            percentile([], 0.5)

    @pytest.mark.parametrize("q", [-0.1, 1.1])
    def test_out_of_range_q_raises(self, q):
        with pytest.raises(ValueError):
            percentile([1.0], q)


class TestSummarise:
    def test_all_fields_on_a_known_input(self):
        stats = summarise([10.0, 20.0, 30.0, 40.0], n_queries=2, n_repetitions=2,
                          n_warmup_discarded=2, clock=CLOCK_SERVER)
        assert stats.p50_ms == 20.0
        assert stats.p95_ms == 40.0
        assert stats.mean_ms == 25.0
        assert stats.min_ms == 10.0
        assert stats.max_ms == 40.0
        assert stats.n_samples == 4
        assert stats.n_queries == 2
        assert stats.n_repetitions == 2
        assert stats.n_warmup_discarded == 2
        assert stats.clock == CLOCK_SERVER

    def test_empty_samples_raise_rather_than_producing_a_zero_latency(self):
        with pytest.raises(ValueError, match="not a latency of 0"):
            summarise([], n_queries=0, n_repetitions=1, n_warmup_discarded=0)

    def test_no_p99_field_exists_anywhere(self):
        """n=177 puts p99 one sample from the maximum. Refusing to compute it is
        the point, so this asserts the absence."""
        stats = summarise([1.0, 2.0], 1, 2, 0)
        assert not hasattr(stats, "p99_ms")
        assert "p99" not in stats.to_dict()
        assert all("p99" not in k for k in stats.to_dict())

    def test_method_statement_names_queries_reps_warmup_and_clock(self):
        stmt = summarise([1.0] * 6, n_queries=3, n_repetitions=2,
                         n_warmup_discarded=3, clock=CLOCK_CLIENT).method_statement()
        assert "6 samples" in stmt
        assert "3 queries" in stmt
        assert "2 timed repetition" in stmt
        assert "3 warmup" in stmt
        assert CLOCK_CLIENT in stmt
        assert "no p99" in stmt

    def test_to_dict_round_trips_into_a_record(self):
        d = summarise([1.0, 2.0, 3.0], 3, 1, 3).to_dict()
        assert set(d) >= {"p50_ms", "p95_ms", "n_samples", "clock", "percentile_method"}
        assert d["percentile_method"] == "nearest_rank_ceil"

    def test_notes_survive(self):
        stats = summarise([1.0], 1, 1, 0, notes=["includes loopback"])
        assert stats.notes == ["includes loopback"]

    def test_stats_are_frozen(self):
        stats = summarise([1.0], 1, 1, 0)
        with pytest.raises(Exception):
            stats.p50_ms = 999.0
        assert isinstance(stats, LatencyStats)

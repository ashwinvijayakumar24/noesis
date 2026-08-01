"""Tests for the end-to-end latency harness.

The instrument is the thing under test here, not the pipeline. Three
properties matter, and each has its own section below:

1. **The stages account for the wall time.** If they do not, the missing
   seconds are somewhere the harness cannot see, and the per-stage table is
   then a decomposition of something other than what the user waited for. The
   graph-level measurement found node time was 99.5% of graph wall; the same
   1% standard is applied one level up, and a breach is reported as a finding
   rather than absorbed.
2. **A number cannot escape its n.** p95 and p99 are refused below n=20 and
   n=100 by the shared `trace_report.metrics` code, and warmup runs are not
   allowed to reach a statistic.
3. **Production cannot be touched.** The loopback guard has no override.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

EVAL_DIR = Path(__file__).resolve().parents[1]
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

import e2e_latency as E  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_clock(stage_seconds: dict[str, float], wall: float) -> E.Clock:
    clock = E.Clock()
    clock.stage_seconds = dict(stage_seconds)
    clock.wall_seconds = wall
    return clock


def make_record(index: int, stage_seconds: dict[str, float], wall: float,
                *, warmup: bool = False, ok: bool = True) -> E.RunRecord:
    return E.RunRecord(
        index=index,
        ok=ok,
        warmup=warmup,
        draft_id=f"draft-{index}",
        clock=make_clock(stage_seconds, wall).to_dict(),
    )


EVEN = {"upload_request": 10.0, "ingest": 20.0, "graph": 60.0,
        "task_tail": 1.0, "first_read": 0.5}
EVEN_SUM = sum(EVEN.values())


# ---------------------------------------------------------------------------
# 1. The stages account for the wall time
# ---------------------------------------------------------------------------

class TestStageAccounting:

    def test_stages_sum_to_wall_within_tolerance(self):
        # 0.4 s of harness overhead on a 91.9 s run is 0.44%, inside 1%.
        clock = make_clock(EVEN, EVEN_SUM + 0.4)
        d = clock.to_dict()
        assert d["stages_total_seconds"] == pytest.approx(EVEN_SUM, abs=1e-3)
        assert abs(d["residual_fraction"]) < E.HARNESS_OVERHEAD_TOLERANCE

    def test_a_large_residual_is_visible_not_absorbed(self):
        """Ten seconds unaccounted for must show up as a number, not vanish."""
        clock = make_clock(EVEN, EVEN_SUM + 10.0)
        d = clock.to_dict()
        assert d["residual_seconds"] == pytest.approx(10.0, abs=1e-3)
        assert abs(d["residual_fraction"]) > E.HARNESS_OVERHEAD_TOLERANCE

    def test_stage_names_are_the_declared_ones(self):
        """A stage the harness times but STAGES does not list would be dropped
        from the sum and would silently inflate the residual."""
        clock = E.Clock()
        with clock.wall():
            for name in E.STAGES:
                with clock.stage(name):
                    pass
        assert set(clock.stage_seconds) == set(E.STAGES)
        assert abs(clock.residual) < 0.5

    def test_visible_total_excludes_the_post_visibility_tail(self):
        clock = make_clock(EVEN, EVEN_SUM)
        assert clock.visible_total == pytest.approx(EVEN_SUM - EVEN["task_tail"])
        assert "task_tail" not in E.VISIBLE_STAGES
        assert set(E.VISIBLE_STAGES) < set(E.STAGES)

    def test_stages_do_not_overlap(self):
        """Nested stages would double-count. The context manager restores the
        previous stage rather than nesting, so a real nesting attempt still
        records two disjoint durations."""
        clock = E.Clock()
        with clock.stage("graph"):
            assert clock.current == "graph"
        assert clock.current == "outside"


# ---------------------------------------------------------------------------
# 2. A number cannot escape its n
# ---------------------------------------------------------------------------

class TestSampleSizeDiscipline:

    def test_n_three_refuses_p95_and_p99(self):
        records = [make_record(i, EVEN, EVEN_SUM) for i in range(3)]
        s = E.summarize(records)
        for key in ("wall", "visible_total"):
            assert s[key]["n"] == 3
            assert s[key]["p50"] is not None
            assert s[key]["p95"] is None
            assert s[key]["p99"] is None
            assert "p95" in s[key]["refused"]

    def test_n_three_also_refuses_p90(self):
        records = [make_record(i, EVEN, EVEN_SUM) for i in range(3)]
        s = E.summarize(records)
        assert s["stages"]["graph"]["p90"] is None

    def test_warmup_runs_never_reach_a_statistic(self):
        warm = make_record(0, {**EVEN, "graph": 600.0}, 640.0, warmup=True)
        rest = [make_record(i, EVEN, EVEN_SUM) for i in range(1, 4)]
        s = E.summarize([warm] + rest)
        assert s["n_offered"] == 4
        assert s["n_warmup_discarded"] == 1
        assert s["n_runs"] == 3
        # 600 s would be the max if the warmup had leaked in.
        assert s["stages"]["graph"]["max"] == pytest.approx(EVEN["graph"])

    def test_failed_runs_are_counted_but_not_averaged(self):
        bad = make_record(9, {}, 0.0, ok=False)
        records = [make_record(i, EVEN, EVEN_SUM) for i in range(3)] + [bad]
        s = E.summarize(records)
        assert s["n_failed"] == 1
        assert s["n_ok"] == 3
        assert s["wall"]["n"] == 3

    def test_cv_needs_at_least_two_runs(self):
        assert "visible_total_cv" not in E.summarize([make_record(0, EVEN, EVEN_SUM)])
        two = [make_record(0, EVEN, EVEN_SUM),
               make_record(1, {**EVEN, "graph": 66.0}, EVEN_SUM + 6.0)]
        assert E.summarize(two)["visible_total_cv"] > 0

    def test_no_data_is_not_zero(self):
        s = E.summarize([])
        assert s["wall"]["n"] == 0
        assert s["wall"]["p50"] is None


# ---------------------------------------------------------------------------
# 3. Production cannot be touched
# ---------------------------------------------------------------------------

class TestLoopbackGuard:

    @pytest.mark.parametrize("url", [
        "https://abcdefgh.supabase.co",
        "http://db.example.com:54321",
        "https://noesis.is",
    ])
    def test_non_loopback_is_refused(self, url):
        with pytest.raises(SystemExit):
            E.assert_local_only(url)

    @pytest.mark.parametrize("url", [
        "http://127.0.0.1:54321",
        "http://localhost:54321",
    ])
    def test_loopback_is_allowed(self, url):
        E.assert_local_only(url)

    def test_the_hard_coded_target_is_loopback(self):
        E.assert_local_only(E.LOCAL_SUPABASE_URL)

    def test_bootstrap_sql_is_labelled_not_production(self):
        sql = E.bootstrap_sql()
        assert "NEVER APPLY TO PRODUCTION" in sql
        assert "reconstruction, not a copy" in sql


# ---------------------------------------------------------------------------
# 4. HTTP attribution
# ---------------------------------------------------------------------------

class TestHttpAttribution:

    def test_calls_are_attributed_to_the_stage_in_flight(self):
        clock = E.Clock()
        with clock.stage("ingest"):
            clock.db.record(clock.current, 0.5)
            clock.db.record(clock.current, 0.25)
        with clock.stage("graph"):
            clock.db.record(clock.current, 1.0)
        d = clock.db.to_dict()
        assert d["calls"] == {"graph": 1, "ingest": 2}
        assert d["seconds"]["ingest"] == pytest.approx(0.75)
        assert d["total_calls"] == 3

    def test_account_adapter_routes_to_the_active_clock(self):
        box = {"clock": None}
        acct = E._Account(lambda: box["clock"], "db")
        acct.record("graph", 1.0)  # no active clock: dropped, not crashed
        c = E.Clock()
        box["clock"] = c
        acct.record("graph", 2.0)
        assert c.db.to_dict()["total_seconds"] == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# 5. Config hashing
# ---------------------------------------------------------------------------

class TestConfigHash:

    def test_parser_change_changes_the_hash(self):
        base = {"harness": "e2e_latency", "pdf_parser": "grobid"}
        other = {**base, "pdf_parser": "docling"}
        assert E.config_hash(base) != E.config_hash(other)

    def test_hash_is_order_independent(self):
        assert E.config_hash({"a": 1, "b": 2}) == E.config_hash({"b": 2, "a": 1})


# ---------------------------------------------------------------------------
# 6. The real recorded runs, if this machine has any
# ---------------------------------------------------------------------------

class TestRecordedRuns:
    """Guards the sink itself: whatever was measured must still satisfy the
    accounting property. Skipped on a fresh clone, where the sink is absent."""

    @staticmethod
    def _records():
        path = E.DEFAULT_RESULTS
        if not path.is_file():
            pytest.skip(f"no results sink at {path}")
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

    def test_every_successful_run_accounts_for_its_wall_time(self):
        breaches = []
        for record in self._records():
            for run in record.get("runs", []):
                if not run.get("ok"):
                    continue
                frac = run.get("residual_fraction")
                if frac is None:
                    continue
                if abs(frac) > E.HARNESS_OVERHEAD_TOLERANCE:
                    breaches.append((record["run_id"], run["index"], frac))
        assert not breaches, (
            "unaccounted wall time above the stated tolerance "
            f"{E.HARNESS_OVERHEAD_TOLERANCE}: {breaches}"
        )

    def test_records_carry_their_exclusion_list(self):
        for record in self._records():
            assert record["exclusions"], record["run_id"]
            assert record["config_hash"]
            assert record["summary"]["n_ok"] is not None

    def test_spend_is_recorded_on_every_record(self):
        for record in self._records():
            assert "spend" in record
            assert record["spend"]["estimated_usd"] is not None

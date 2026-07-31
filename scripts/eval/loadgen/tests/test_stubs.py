"""The stub's fidelity, the Supabase write guard, and the dry-run guarantee."""

from __future__ import annotations

import statistics
import sys
from pathlib import Path

import pytest

from loadgen.latency_profile import LatencyProfile, NodeSpec
from loadgen.stubs import (
    SupabaseWriteAttempted,
    WriteGuardSupabase,
    synthesize,
)


# --------------------------------------------------------------------------
# The stub's latency distribution matches its input distribution
# --------------------------------------------------------------------------

@pytest.mark.parametrize("mean,cv", [(19.386, 0.14), (7.431, 0.17), (2.0, 0.5)])
def test_sampled_latency_matches_the_specified_mean_and_cv(mean, cv):
    """If the sampler does not reproduce the distribution it was handed, every
    stubbed latency in LATENCY.md is describing a distribution nobody measured."""
    spec = NodeSpec("n", mean, cv, 5, "MEASURED")
    p = LatencyProfile({"n": spec}, seed=42)
    draws = [p.sample("n") for _ in range(200_000)]
    assert statistics.fmean(draws) == pytest.approx(mean, rel=0.01)
    assert statistics.stdev(draws) / statistics.fmean(draws) == pytest.approx(cv, rel=0.02)


def test_sampled_latency_is_always_positive():
    p = LatencyProfile({"n": NodeSpec("n", 1.0, 2.0, 1, "ASSUMED")}, seed=1)
    assert all(p.sample("n") > 0 for _ in range(10_000))


def test_speedup_divides_service_time_and_preserves_cv():
    """Time compression must change absolute seconds and nothing else, or the
    ratios a compressed sweep reports are not the ratios of the real system."""
    spec = {"n": NodeSpec("n", 20.0, 0.15, 5, "MEASURED")}
    slow_p = LatencyProfile(spec, seed=3)
    slow = [slow_p.sample("n") for _ in range(50_000)]
    fast_p = LatencyProfile(spec, seed=3, speedup=20.0)
    fast = [fast_p.sample("n") for _ in range(50_000)]
    assert statistics.fmean(fast) == pytest.approx(statistics.fmean(slow) / 20.0, rel=0.01)
    assert (statistics.stdev(fast) / statistics.fmean(fast)) == pytest.approx(
        statistics.stdev(slow) / statistics.fmean(slow), rel=0.02
    )


def test_unknown_nodes_fall_back_to_a_labelled_assumption():
    p = LatencyProfile()
    spec = p.spec("a_node_that_does_not_exist")
    assert spec.source == "ASSUMED"
    assert spec.n == 0


def test_provenance_names_every_tier_and_keeps_them_separate():
    lines = "\n".join(LatencyProfile().provenance())
    assert "CALIBRATED" in lines and "ASSUMED" in lines
    assert "reviewer_panel_node" in lines
    # A node whose latency was never established must not appear above the
    # ASSUMED heading, or a reader will take an assumption for a measurement.
    above_assumed = lines.split("ASSUMED")[0]
    assert "search_literature" not in above_assumed


def test_calibration_outranks_node_replay_for_the_same_node():
    """The in-graph calibration run and the isolated node replays disagree on
    editor_pass_node (8.74s vs 7.43s). In-graph must win: the replay number was
    taken outside the graph, months earlier, on a different fixture mix."""
    calibrated = LatencyProfile().spec("editor_pass_node")
    replayed = LatencyProfile(use_calibration=False).spec("editor_pass_node")
    assert calibrated.source == "CALIBRATED"
    assert replayed.source == "MEASURED"
    assert calibrated.mean != replayed.mean


def test_calibration_covers_every_node_that_actually_calls_an_llm():
    """If a node that makes calls fell back to ASSUMED, the stub's absolute
    latency would be fiction for that node."""
    p = LatencyProfile()
    for node in ("extract_claims", "structural_checks", "editor_pass_node",
                 "reviewer_panel_node", "reviewer_judge_node", "meta_reviewer_node"):
        assert p.spec(node).source == "CALIBRATED", node


def test_measured_specs_are_recomputed_from_node_eval_jsonl(tmp_path):
    path = tmp_path / "node_eval.jsonl"
    rows = [
        '{"record_type":"replay","status":"ok","node":"editor_pass_node",'
        '"wall_seconds":%s,"usage":{"calls":1}}' % v
        for v in (10.0, 12.0, 14.0)
    ]
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    p = LatencyProfile(node_eval_path=path, use_calibration=False)
    assert p.spec("editor_pass_node").mean == pytest.approx(12.0)
    assert p.spec("editor_pass_node").n == 3
    assert p.spec("editor_pass_node").source == "MEASURED"


def test_a_truncated_results_line_is_skipped_not_fatal(tmp_path):
    path = tmp_path / "node_eval.jsonl"
    path.write_text(
        '{"record_type":"replay","status":"ok","node":"editor_pass_node",'
        '"wall_seconds":10.0,"usage":{"calls":1}}\n{"record_type":"rep',
        encoding="utf-8",
    )
    LatencyProfile(node_eval_path=path)  # must not raise


# --------------------------------------------------------------------------
# The stage_only assertion
# --------------------------------------------------------------------------

@pytest.mark.parametrize("verb", ["insert", "update", "upsert", "delete"])
def test_the_write_guard_fires_on_every_write_verb(verb):
    """This is the assertion that replaces trusting the stage_only gate."""
    guard = WriteGuardSupabase()
    with pytest.raises(SupabaseWriteAttempted, match="escaped the stage_only gate"):
        getattr(guard.table("draft_analysis"), verb)({"x": 1}).execute()
    assert guard.write_attempts == [("draft_analysis", verb)]


def test_the_write_guard_names_the_table_it_caught():
    guard = WriteGuardSupabase()
    with pytest.raises(SupabaseWriteAttempted, match="reviewer_outputs"):
        guard.table("reviewer_outputs").insert({}).execute()


def test_reads_return_empty_rather_than_raising():
    """The graph's read paths are try/except-wrapped and degrade to 'no corpus'.
    Raising on reads would turn a load test into an error-rate test."""
    guard = WriteGuardSupabase()
    r = guard.table("documents").select("id").eq("project_id", "x").limit(1).execute()
    assert r.data == []
    assert guard.reads == 1


def test_assert_no_writes_passes_on_a_clean_run_and_fails_after_one_attempt():
    from loadgen.stubs import StubControl

    guard = WriteGuardSupabase()
    control = StubControl(counters=None, guard=guard, profile=None, stubbed_llm=True)
    control.assert_no_writes()
    guard.write_attempts.append(("drafts", "update"))
    with pytest.raises(SupabaseWriteAttempted):
        control.assert_no_writes()


# --------------------------------------------------------------------------
# Structured-output synthesis
# --------------------------------------------------------------------------

def _schemas():
    sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "services" / "backend"))
    try:
        from app.workflows.draft_analysis import schemas
    except Exception:  # pragma: no cover - backend deps absent
        pytest.skip("backend app package not importable")
    return schemas


def test_synthesized_output_validates_against_the_real_node_schemas():
    s = _schemas()
    for cls in (s.EditorPassOutput, s.ReviewerOutput, s.MetaReviewOutput,
                s.ClaimExtractionOutput, s.ReviewerJudgeOutput, s.CitationJudgeOutput,
                s.DiagnosticFindingsOutput, s.ManuscriptProfileOutput):
        obj = synthesize(cls)
        assert isinstance(obj, cls)
        cls.model_validate(obj.model_dump())  # round-trips through validation


def test_bounded_numeric_fields_land_inside_their_bounds():
    s = _schemas()
    r = synthesize(s.ReviewerOutput)
    assert 1 <= r.rating <= 10
    assert 1 <= r.confidence <= 5
    for issue in r.issues:
        assert 0.0 <= issue.confidence <= 1.0


def test_editor_proceeds_so_the_reviewer_panel_is_actually_exercised():
    """A stub that desk-rejects would measure a 15-node pipeline and call it 18."""
    s = _schemas()
    assert synthesize(s.EditorPassOutput).proceed_to_review is True


def test_reviewer_id_follows_the_persona_named_in_the_prompt():
    """Without this the three fan-out branches all come back as 'methodology'
    and the panel collapses to one reviewer downstream."""
    s = _schemas()
    prompt = "You are the clarity reviewer. Focus on clarity, clarity, clarity."
    assert synthesize(s.ReviewerOutput, prompt=prompt).reviewer_id == "clarity"
    prompt2 = "You are the literature_positioning reviewer. literature_positioning."
    assert synthesize(s.ReviewerOutput, prompt=prompt2).reviewer_id == "literature_positioning"


def test_list_fields_are_populated_so_downstream_nodes_have_input():
    s = _schemas()
    out = synthesize(s.ReviewerOutput, list_len=3)
    assert len(out.issues) == 3
    assert len(out.weaknesses) == 3


def test_synthesis_terminates_on_nested_models():
    s = _schemas()
    obj = synthesize(s.DiagnosticFindingsOutput, list_len=2, max_depth=2)
    assert len(obj.findings) == 2

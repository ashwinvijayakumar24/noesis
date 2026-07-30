"""Tests pinning the corrected precision / groundedness / hallucination definitions.

The bug these exist to prevent: the old `precision` counted an item as correct if
it matched gold OR its anchor was in the PDF OR an LLM blessed it, which made
`mean_precision: 1.0` and `mean_hallucination_rate: 0.0` unfalsifiable.

Every grounder here is a stub. No test may hit the network or spend money.
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

EVAL_DIR = Path(__file__).resolve().parents[1]


def _load(name: str):
    module_path = EVAL_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"eval_{name}_for_tests", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


judge = _load("judge_openreview")


PAPER_TEXT = (
    "We evaluate on CIFAR-10 and report top-1 accuracy. "
    "The ablation in Section 4 removes the attention head. "
    "All experiments use a single random seed."
)


def _export(tmp_path: Path, tasks: list[dict]) -> Path:
    path = tmp_path / "export.json"
    path.write_text(json.dumps({"durable_revision_tasks": tasks}))
    return path


def _task(task_id: str, problem: str, anchor: str = "") -> dict:
    return {"id": task_id, "problem": problem, "anchor_text": anchor}


def _gold(units: list[dict], pdf_path: str = "") -> dict:
    return {
        "paper_id": "P1",
        "venue": "ICLR.cc/2024/Conference",
        "accepted": True,
        "pdf_path": pdf_path,
        "review_units": units,
    }


def _unit(unit_id: str, weight: float = 1.0) -> dict:
    return {"unit_id": unit_id, "severity_weight": weight, "text": "reviewer said something"}


def _match(noesis_id: str, unit_id: str, confirmed: bool = True) -> dict:
    return {"noesis_id": noesis_id, "unit_id": unit_id, "confirmed": confirmed}


def _score(tmp_path, tasks, units, matches, *, paper_text=PAPER_TEXT, grounder=None):
    """Score with _extract_pdf_text stubbed so no PDF/network access happens."""
    judge._extract_pdf_text_orig = getattr(judge, "_extract_pdf_text_orig", judge._extract_pdf_text)
    judge._extract_pdf_text = lambda gold: paper_text
    try:
        return judge.score_paper(
            _export(tmp_path, tasks),
            _gold(units),
            matches,
            cache_dir=tmp_path / "cache",
            grounder=grounder or (lambda claim, text: {"grounded": False, "reason": "stub"}),
        )
    finally:
        judge._extract_pdf_text = judge._extract_pdf_text_orig


# --------------------------------------------------------------------------
# precision against gold
# --------------------------------------------------------------------------

def test_item_matching_gold_counts_toward_precision(tmp_path):
    result = _score(
        tmp_path,
        [_task("t1", "Only one random seed is used.", "All experiments use a single random seed.")],
        [_unit("u1")],
        [_match("t1", "u1")],
    )
    assert result["precision_vs_gold"] == 1.0
    assert result["counts"]["matched_vs_gold"] == 1


def test_grounded_item_matching_no_gold_unit_does_not_count_toward_precision(tmp_path):
    """THE BUG. A verifiable anchor is groundedness, not precision against gold.

    Under the old definition this item scored precision 1.0 because its anchor is
    present in the paper, even though no human reviewer ever raised it.
    """
    result = _score(
        tmp_path,
        [_task("t1", "The ablation is under-described.", "The ablation in Section 4 removes the attention head.")],
        [_unit("u1")],
        [],  # no confirmed match against any gold review unit
    )
    assert result["precision_vs_gold"] == 0.0, "grounded-but-unmatched item leaked into precision"
    assert result["groundedness"] == 1.0, "groundedness must still credit the verifiable anchor"
    assert result["hallucination_rate"] == 0.0, "a grounded item is not a hallucination"
    assert result["counts"]["matched_vs_gold"] == 0
    assert result["counts"]["grounded_items"] == 1


def test_item_blessed_only_by_llm_does_not_count_toward_precision(tmp_path):
    """An LLM 'grounded: true' must not promote anything into precision."""
    result = _score(
        tmp_path,
        [_task("t1", "The paper ignores fairness entirely.", "no such sentence anywhere in the pdf")],
        [_unit("u1")],
        [],
        grounder=lambda claim, text: {"grounded": True, "reason": "model says yes"},
    )
    assert result["precision_vs_gold"] == 0.0, "LLM blessing leaked into precision"
    assert result["groundedness"] == 0.0, "LLM blessing leaked into groundedness"
    assert result["llm_relevance_rate"] == 1.0, "LLM verdict should still be reported separately"
    assert result["hallucination_rate"] == 1.0, "unverifiable anchor must stay a hallucination"
    assert result["counts"]["llm_relevant"] == 1


def test_precision_only_counts_confirmed_matches(tmp_path):
    result = _score(
        tmp_path,
        [_task("t1", "Only one seed.", "All experiments use a single random seed.")],
        [_unit("u1")],
        [_match("t1", "u1", confirmed=False)],
    )
    assert result["precision_vs_gold"] == 0.0


def test_old_precision_key_is_gone(tmp_path):
    """The misleading name must not survive with a new meaning attached."""
    result = _score(tmp_path, [_task("t1", "x", "")], [_unit("u1")], [])
    assert "precision" not in result
    assert "precision_vs_gold" in result


# --------------------------------------------------------------------------
# groundedness reported separately
# --------------------------------------------------------------------------

def test_groundedness_reported_separately_and_correctly(tmp_path):
    tasks = [
        _task("t1", "a", "We evaluate on CIFAR-10 and report top-1 accuracy."),  # grounded
        _task("t2", "b", "The ablation in Section 4 removes the attention head."),  # grounded
        _task("t3", "c", "a sentence that is definitely not present in this paper"),  # not
        _task("t4", "d", ""),  # no anchor at all -> not verifiable
    ]
    result = _score(tmp_path, tasks, [_unit("u1")], [])
    assert result["groundedness"] == 0.5
    assert result["anchor_quality"] == result["groundedness"], "anchor_quality alias drifted"
    assert result["counts"]["grounded_items"] == 2
    assert result["counts"]["ungrounded_items"] == 2
    assert result["precision_vs_gold"] == 0.0


def test_groundedness_is_independent_of_gold_matching(tmp_path):
    """Matching gold must not fabricate groundedness for an unverifiable anchor."""
    result = _score(
        tmp_path,
        [_task("t1", "The paper lacks a theory section.", "not in the paper at all")],
        [_unit("u1")],
        [_match("t1", "u1")],
    )
    assert result["precision_vs_gold"] == 1.0
    assert result["groundedness"] == 0.0
    assert result["hallucination_rate"] == 1.0
    # the hallucination record notes that it did match gold — a real reviewer raised
    # it, but Noesis could not point at where in the paper
    assert result["hallucinations"][0]["matched_gold"] is True


# --------------------------------------------------------------------------
# hallucination rate
# --------------------------------------------------------------------------

def test_hallucination_rate_reflects_ungrounded_items_and_is_not_one_minus_precision(tmp_path):
    tasks = [
        _task("t1", "a", "We evaluate on CIFAR-10 and report top-1 accuracy."),  # grounded
        _task("t2", "b", "We evaluate on CIFAR-10 and report top-1 accuracy."),  # grounded
        _task("t3", "c", "totally absent from the source document"),  # ungrounded
        _task("t4", "d", "also totally absent from the source document"),  # ungrounded
    ]
    # only one item matches gold -> precision 0.25 -> 1 - precision would be 0.75
    result = _score(tmp_path, tasks, [_unit("u1")], [_match("t1", "u1")])

    assert result["precision_vs_gold"] == 0.25
    assert result["hallucination_rate"] == 0.5
    assert result["ungrounded_rate"] == 0.5
    assert result["hallucination_rate"] != round(1 - result["precision_vs_gold"], 4), (
        "hallucination_rate is still just 1 - precision"
    )
    assert result["hallucination_rate"] == round(1 - result["groundedness"], 4)
    assert len(result["hallucinations"]) == 2


def test_perfect_gold_match_gives_precision_one_legitimately(tmp_path):
    tasks = [
        _task("t1", "a", "We evaluate on CIFAR-10 and report top-1 accuracy."),
        _task("t2", "b", "The ablation in Section 4 removes the attention head."),
    ]
    matches = [_match("t1", "u1"), _match("t2", "u2")]
    result = _score(tmp_path, tasks, [_unit("u1"), _unit("u2")], matches)
    assert result["precision_vs_gold"] == 1.0
    assert result["groundedness"] == 1.0
    assert result["hallucination_rate"] == 0.0
    assert result["weakness_recall"] == 1.0


# --------------------------------------------------------------------------
# degenerate inputs
# --------------------------------------------------------------------------

def test_empty_item_list_no_division_by_zero(tmp_path):
    result = _score(tmp_path, [], [_unit("u1")], [])
    assert result["precision_vs_gold"] == 0.0
    assert result["groundedness"] == 0.0
    assert result["hallucination_rate"] == 0.0
    assert result["ungrounded_rate"] == 0.0
    assert result["llm_relevance_rate"] == 0.0
    assert result["counts"]["noesis_items"] == 0


def test_empty_gold_list_no_division_by_zero(tmp_path):
    result = _score(
        tmp_path,
        [_task("t1", "a", "We evaluate on CIFAR-10 and report top-1 accuracy.")],
        [],
        [],
    )
    assert result["weakness_recall"] == 0.0
    assert result["precision_vs_gold"] == 0.0
    assert result["groundedness"] == 1.0


def test_both_empty(tmp_path):
    result = _score(tmp_path, [], [], [])
    assert result["weakness_recall"] == 0.0
    assert result["precision_vs_gold"] == 0.0
    assert result["hallucination_rate"] == 0.0


def test_empty_paper_text_skips_llm_but_still_counts_ungrounded(tmp_path):
    calls = []

    def grounder(claim, text):
        calls.append(claim)
        return {"grounded": True, "reason": "should never run"}

    result = _score(
        tmp_path,
        [_task("t1", "a", "anything")],
        [_unit("u1")],
        [],
        paper_text="",
        grounder=grounder,
    )
    assert calls == [], "LLM judge ran against an empty paper"
    assert result["groundedness"] == 0.0
    assert result["hallucination_rate"] == 1.0
    assert result["llm_relevance_rate"] == 0.0
    assert result["counts"]["llm_judged"] == 0


# --------------------------------------------------------------------------
# aggregate
# --------------------------------------------------------------------------

def test_aggregate_exposes_the_new_metric_names():
    rows = [
        {
            "field": "machine_learning", "readiness_score": 0.9, "accepted": True,
            "weakness_recall": 0.5, "precision_vs_gold": 0.4, "groundedness": 0.8,
            "llm_relevance_rate": 0.6, "ungrounded_rate": 0.2,
            "hallucination_rate": 0.2, "anchor_quality": 0.8,
        },
        {
            "field": "biology", "readiness_score": 0.1, "accepted": False,
            "weakness_recall": 0.3, "precision_vs_gold": 0.2, "groundedness": 0.4,
            "llm_relevance_rate": 0.2, "ungrounded_rate": 0.6,
            "hallucination_rate": 0.6, "anchor_quality": 0.4,
        },
    ]
    agg = judge.aggregate(rows)
    assert "mean_precision" not in agg, "the un-failable mean_precision key survived"
    assert agg["mean_precision_vs_gold"] == 0.3
    assert agg["mean_groundedness"] == 0.6
    assert agg["mean_llm_relevance_rate"] == 0.4
    assert agg["mean_ungrounded_rate"] == 0.4
    assert agg["mean_hallucination_rate"] == 0.4
    assert agg["by_field"]["biology"]["mean_precision_vs_gold"] == 0.2
    assert "mean_precision" not in agg["by_field"]["biology"]


def test_aggregate_on_empty_rows():
    agg = judge.aggregate([])
    assert agg["papers"] == 0
    assert agg["mean_precision_vs_gold"] == 0.0
    assert agg["mean_hallucination_rate"] == 0.0


# --------------------------------------------------------------------------
# no live LLM
# --------------------------------------------------------------------------

def test_kill_switch_blocks_a_live_grounding_call(monkeypatch):
    monkeypatch.setenv("NOESIS_LLM_KILL_SWITCH", "1")
    with pytest.raises(RuntimeError, match="NOESIS_LLM_KILL_SWITCH"):
        judge._real_ground_claim("claim", "paper")


def test_replay_only_blocks_a_live_grounding_call(monkeypatch):
    monkeypatch.delenv("NOESIS_LLM_KILL_SWITCH", raising=False)
    monkeypatch.setenv("EVAL_REPLAY_ONLY", "1")
    with pytest.raises(RuntimeError, match="EVAL_REPLAY_ONLY"):
        judge._real_ground_claim("claim", "paper")


def test_grounding_cache_prevents_repeat_calls(tmp_path):
    calls = []

    def grounder(claim, text):
        calls.append(claim)
        return {"grounded": False, "reason": "cached"}

    cache = tmp_path / "cache"
    judge._ground_claim("claim", "paper text", cache, grounder)
    judge._ground_claim("claim", "paper text", cache, grounder)
    assert len(calls) == 1


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))

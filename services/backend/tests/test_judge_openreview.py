import importlib.util
import json
import sys
from pathlib import Path


def _load_judge_module():
    repo_root = Path(__file__).resolve().parents[3]
    module_path = repo_root / "scripts" / "eval" / "judge_openreview.py"
    spec = importlib.util.spec_from_file_location("judge_openreview_for_tests", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["judge_openreview_for_tests"] = module
    spec.loader.exec_module(module)
    return module


judge_openreview = _load_judge_module()


def _export(tmp_path):
    export = {
        "analysis": {"analysis_metadata": {"readiness_score": 0.72}},
        "durable_revision_tasks": [
            {
                "id": "n1",
                "problem": "Missing ablation study.",
                "anchor_text": "We train the model without ablations.",
            },
            {"id": "n2", "problem": "Unsupported claim.", "anchor_text": ""},
        ],
        "reviewer_panel_outputs": [
            {"id": "panel1", "reviewer_id": "methodology", "weaknesses": ["Baseline is weak."]}
        ],
        "coverage_gaps": [{"id": "gap1", "description": "No external validation.", "text_snippet": ""}],
    }
    path = tmp_path / "export.json"
    path.write_text(json.dumps(export))
    return path


def test_extract_noesis_items_from_export_shape(tmp_path):
    items = judge_openreview.extract_noesis_items(json.loads(_export(tmp_path).read_text()))

    assert [item["id"] for item in items] == [
        "n1",
        "n2",
        "panel1::weakness::1",
        "gap1",
    ]
    assert items[0]["anchor_text"] == "We train the model without ablations."


def test_score_paper_uses_weighted_recall_and_grounding(tmp_path, monkeypatch):
    monkeypatch.setattr(
        judge_openreview,
        "_extract_pdf_text",
        lambda gold: "Intro. We train the model without ablations. Methods.",
    )
    gold = {
        "paper_id": "paper1",
        "accepted": True,
        "review_units": [
            {"unit_id": "u1", "severity_weight": 0.7},
            {"unit_id": "u2", "severity_weight": 0.3},
        ],
    }
    matches = [{"noesis_id": "n1", "unit_id": "u1", "confirmed": True}]

    def grounder(claim, paper_text):
        return {"grounded": claim == "Baseline is weak.", "reason": "test"}

    result = judge_openreview.score_paper(_export(tmp_path), gold, matches, cache_dir=tmp_path, grounder=grounder)

    assert result["weakness_recall"] == 0.7
    assert result["anchor_quality"] == 0.25
    assert result["precision"] == 0.5
    assert result["hallucination_rate"] == 0.5
    assert result["matched_unit_ids"] == ["u1"]
    assert len(result["hallucinations"]) == 2


def test_aggregate_computes_means_and_spearman():
    rows = [
        {"readiness_score": 0.9, "accepted": True, "weakness_recall": 0.5, "precision": 1, "hallucination_rate": 0, "anchor_quality": 0.5},
        {"readiness_score": 0.1, "accepted": False, "weakness_recall": 0.3, "precision": 0.5, "hallucination_rate": 0.5, "anchor_quality": 0.0},
    ]

    agg = judge_openreview.aggregate(rows)

    assert agg["papers"] == 2
    assert agg["mean_weakness_recall"] == 0.4
    assert agg["decision_spearman_rho"] == 1.0

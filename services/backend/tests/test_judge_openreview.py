import importlib.util
import json
import sys

import pytest
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


def test_extract_noesis_items_includes_task_rationale_and_action():
    export = {
        "durable_revision_tasks": [
            {
                "id": "n1",
                "problem": "The causal attribution is under-supported.",
                "why_it_matters": "The observed performance drop could be due to multiple training differences.",
                "suggested_action": "Add a controlled comparison or explain which experimental results isolate the claimed mechanism.",
            }
        ]
    }

    items = judge_openreview.extract_noesis_items(export)

    assert "causal attribution" in items[0]["text"]
    assert "performance drop" in items[0]["text"]
    assert "controlled comparison" in items[0]["text"]


def test_extract_noesis_items_strips_internal_meta_review_boilerplate():
    export = {
        "durable_revision_tasks": [
            {
                "id": "n1",
                "problem": "The theorem assumptions are not clear.",
                "why_it_matters": "Named by the meta-reviewer as a blocking item for acceptance.",
                "suggested_action": "Address the issue described above.",
            }
        ]
    }

    items = judge_openreview.extract_noesis_items(export)

    assert items[0]["text"] == "The theorem assumptions are not clear."


def test_extract_noesis_items_uses_structured_reviewer_issues_before_weaknesses():
    export = {
        "reviewer_panel_outputs": [
            {
                "id": "panel1",
                "reviewer_id": "methodology",
                "weaknesses": ["Legacy duplicate weakness."],
                "issues": [
                    {
                        "issue_type": "methodology",
                        "problem": "The baseline comparison is underspecified.",
                        "anchor_text": "We compare against the default solver.",
                    }
                ],
            }
        ]
    }

    items = judge_openreview.extract_noesis_items(export)

    assert items == [
        {
            "id": "panel1::methodology::issue::1",
            "source": "reviewer_panel_issue",
            "reviewer_id": "methodology",
            "issue_type": "methodology",
            "problem": "The baseline comparison is underspecified.",
            "text": "The baseline comparison is underspecified.",
            "anchor_text": "We compare against the default solver.",
        }
    ]


def test_score_paper_uses_weighted_recall_and_grounding(tmp_path, monkeypatch):
    monkeypatch.setattr(
        judge_openreview,
        "_extract_pdf_text",
        lambda gold: "Intro. We train the model without ablations. Methods.",
    )
    gold = {
        "paper_id": "paper1",
        "venue": "ICLR.cc/2024/Conference",
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
    assert result["field"] == "machine_learning"
    assert result["matched_unit_ids"] == ["u1"]

    # `precision` used to be OR'd across three unrelated properties: matched a
    # gold unit, OR the anchor appears in the PDF, OR an LLM says it is grounded.
    # An item no human reviewer ever raised counted as correct once a model
    # blessed it, which is why the shipped scoreboard read precision 1.0 and
    # hallucination_rate 0.0. The key is removed rather than repurposed -- a
    # same-named field with a different meaning is worse than a rename.
    assert "precision" not in result
    assert result["precision_vs_gold"] == 0.25      # matched a human unit
    assert result["groundedness"] == 0.25           # anchor found in the source
    assert result["llm_relevance_rate"] == 0.3333  # 1/3, rounded to 4dp on write

    # hallucination_rate keeps its name but now measures ungrounded items rather
    # than 1 - precision, so it can actually be nonzero.
    assert result["ungrounded_rate"] == 0.75
    assert result["hallucination_rate"] == 0.75
    assert len(result["hallucinations"]) == 3


def test_aggregate_computes_means_and_spearman():
    rows = [
        {"field": "machine_learning", "readiness_score": 0.9, "accepted": True, "weakness_recall": 0.5, "precision_vs_gold": 1, "groundedness": 0.5, "llm_relevance_rate": 1.0, "ungrounded_rate": 0.0, "hallucination_rate": 0, "anchor_quality": 0.5},
        {"field": "biology", "readiness_score": 0.1, "accepted": False, "weakness_recall": 0.3, "precision_vs_gold": 0.5, "groundedness": 0.0, "llm_relevance_rate": 0.5, "ungrounded_rate": 0.5, "hallucination_rate": 0.5, "anchor_quality": 0.0},
    ]

    agg = judge_openreview.aggregate(rows)

    assert agg["papers"] == 2
    assert agg["mean_weakness_recall"] == 0.4
    assert agg["decision_spearman_rho"] == 1.0
    assert agg["by_field"]["biology"]["mean_precision_vs_gold"] == 0.5
    assert agg["by_field"]["machine_learning"]["papers"] == 1


def test_paper_field_prefers_manifest_then_gold_then_venue():
    gold = {"paper_id": "p1", "title": "A title", "field": "biology", "venue": "ICLR.cc/2024/Conference"}

    assert judge_openreview.paper_field(gold, {"p1": "climate_science"}) == "climate_science"
    assert judge_openreview.paper_field(gold) == "biology"
    assert judge_openreview.paper_field({"venue": "ICLR.cc/2024/Conference"}) == "machine_learning"


def test_anchor_found_tolerates_pdf_extraction_artifacts():
    anchor = (
        "BoT randomly chooses the temperature from the range of [0.2, 0.4, 0.6, 0.7, 0.9, 1.1, 1.5] "
        "and the top p from the range of [0.1, 0.3, 0.5, 0.7, 0.9]."
    )
    paper_text = (
        "Methods. BoT randomly chooses the temperature from the range of [0 . 2 , 0 . 4 , 0 . 6 , "
        "0 . 7 , 0 . 9 , 1 . 1 , 1 . 5] and the top p from the range of [0 . 1 , 0 . 3 , "
        "0 . 5 , 0 . 7 , 0 . 9] . Results."
    )

    assert judge_openreview._anchor_found(anchor, paper_text)


def test_anchor_found_tolerates_math_symbol_normalization():
    anchor = "Suppose J π is Lipschitz-smooth with constant L, the gradient of J π and L att is bounded by ρ."
    paper_text = "Suppose J pi is Lipschitz-smooth with constant L, the gradient of J pi and L att is bounded by rho."

    assert judge_openreview._anchor_found(anchor, paper_text)


def test_anchor_found_does_not_accept_short_keyword_overlap():
    anchor = "no ablation"
    paper_text = "The appendix reports an ablation study and runtime analysis."

    assert not judge_openreview._anchor_found(anchor, paper_text)

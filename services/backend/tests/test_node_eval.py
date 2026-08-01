import importlib.util
import sys
from pathlib import Path


def _load_node_eval_module():
    repo_root = Path(__file__).resolve().parents[3]
    module_path = repo_root / "scripts" / "eval" / "node_eval.py"
    spec = importlib.util.spec_from_file_location("node_eval_for_tests", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["node_eval_for_tests"] = module
    spec.loader.exec_module(module)
    return module


node_eval = _load_node_eval_module()


def test_state_path_handles_reviewer_variants(tmp_path):
    assert node_eval.state_path("detect_gaps", "paper1", tmp_path) == tmp_path / "paper1" / "detect_gaps.json"
    assert (
        node_eval.state_path("reviewer_panel_node", "paper1", tmp_path, "methodology")
        == tmp_path / "paper1" / "reviewer_panel_node__methodology.json"
    )


def test_extract_node_items_for_detect_gaps_only_returns_gaps():
    state = {
        "coverage_gaps": [{"id": "g1", "description": "Missing baseline comparison."}],
        "reviewer_outputs": [{"reviewer_id": "methodology", "weaknesses": ["Reviewer issue."]}],
    }

    assert node_eval.extract_node_items("detect_gaps", state) == [
        {"id": "g1", "text": "Missing baseline comparison.", "source": "coverage_gap"}
    ]


def test_extract_node_items_for_reviewer_panel_uses_issues_before_weaknesses():
    state = {
        "reviewer_outputs": [
            {
                "reviewer_id": "methodology",
                "weaknesses": ["Weak ablation."],
                "issues": [
                    {
                        "problem": "Poor baseline.",
                        "anchor_text": "We compare to one method.",
                        "issue_type": "methodology",
                    }
                ],
            }
        ]
    }

    assert node_eval.extract_node_items("reviewer_panel_node", state) == [
        {
            "id": "methodology::issue::1",
            "problem": "Poor baseline.",
            "text": "Poor baseline.",
            "source": "reviewer_issue",
            "anchor_text": "We compare to one method.",
            "issue_type": "methodology",
            "reviewer_id": "methodology",
        },
    ]


def test_extract_node_items_for_reviewer_panel_uses_weaknesses_as_legacy_fallback():
    state = {
        "reviewer_outputs": [
            {
                "reviewer_id": "methodology",
                "weaknesses": ["Weak ablation."],
                "issues": [],
            }
        ]
    }

    assert node_eval.extract_node_items("reviewer_panel_node", state) == [
        {"id": "methodology::weakness::1", "text": "Weak ablation.", "source": "reviewer_output"},
    ]


def test_extract_node_items_includes_diagnostic_rationale_and_action():
    state = {
        "diagnostic_findings": [
            {
                "id": "d1",
                "problem": "The metric definition is unclear.",
                "why_it_matters": "Fixed subset size can change the interpretation.",
                "suggested_action": "Report sensitivity to the subset-size constant.",
            }
        ]
    }

    items = node_eval.extract_node_items("run_quality_diagnostics", state)

    assert "metric definition" in items[0]["text"]
    assert "Fixed subset size" in items[0]["text"]
    assert "Report sensitivity" in items[0]["text"]


def test_extract_node_items_strips_internal_meta_review_boilerplate():
    state = {
        "revision_tasks": [
            {
                "id": "t1",
                "problem": "The evaluation setup is under-described.",
                "why_it_matters": "Named by the meta-reviewer as a blocking item for acceptance.",
                "suggested_action": "Address the issue described above.",
            }
        ]
    }

    items = node_eval.extract_node_items("synthesize_report", state)

    assert items[0]["text"] == "The evaluation setup is under-described."


def test_extract_node_items_for_external_source_discovery():
    state = {
        "external_sources": [
            {"doi": "10.123/example", "title": "Relevant baseline", "relevance_reason": "Addresses the missing baseline."}
        ],
        "coverage_gaps": [{"id": "g1", "description": "Missing baseline comparison."}],
    }

    assert node_eval.extract_node_items("discover_external_sources", state) == [
        {"id": "10.123/example", "text": "Addresses the missing baseline.", "source": "external_source"}
    ]


def test_merge_state_appends_reviewer_outputs():
    merged = node_eval._merge_state(
        {"reviewer_outputs": [{"reviewer_id": "a"}]},
        {"reviewer_outputs": [{"reviewer_id": "b"}]},
    )

    assert merged["reviewer_outputs"] == [{"reviewer_id": "a"}, {"reviewer_id": "b"}]

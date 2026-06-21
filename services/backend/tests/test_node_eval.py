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


def test_extract_node_items_for_reviewer_panel_outputs_weaknesses_and_issues():
    state = {
        "reviewer_outputs": [
            {
                "reviewer_id": "methodology",
                "weaknesses": ["Weak ablation."],
                "issues": [{"problem": "Poor baseline."}],
            }
        ]
    }

    assert node_eval.extract_node_items("reviewer_panel_node", state) == [
        {"id": "methodology::weakness::1", "text": "Weak ablation.", "source": "reviewer_output"},
        {"id": "methodology::issue::1", "text": "Poor baseline.", "source": "reviewer_issue"},
    ]


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

import importlib.util
import sys
from pathlib import Path


def _load_mine_failures_module():
    repo_root = Path(__file__).resolve().parents[3]
    module_path = repo_root / "scripts" / "eval" / "mine_failures.py"
    spec = importlib.util.spec_from_file_location("mine_failures_for_tests", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["mine_failures_for_tests"] = module
    spec.loader.exec_module(module)
    return module


mine_failures = _load_mine_failures_module()


def test_collect_missed_units_uses_scoreboard_matched_ids(tmp_path, monkeypatch):
    gold = {
        "paper_id": "paper1",
        "review_units": [
            {"unit_id": "u1", "reviewer": "anon1", "text": "Matched issue.", "severity_weight": 0.7},
            {"unit_id": "u2", "reviewer": "anon2", "text": "Missed baseline issue.", "severity_weight": 0.9},
        ],
    }
    gold_path = tmp_path / "gold.json"
    gold_path.write_text(__import__("json").dumps(gold))
    scoreboard = {"rows": [{"paper_id": "paper1", "gold": str(gold_path), "matched_unit_ids": ["u1"]}]}

    monkeypatch.setattr(mine_failures, "_resolve_path", lambda value: Path(value))

    assert mine_failures.collect_missed_units(scoreboard) == [
        {
            "paper_id": "paper1",
            "unit_id": "u2",
            "reviewer": "anon2",
            "kind": "weakness",
            "text": "Missed baseline issue.",
            "severity_weight": 0.9,
            "accepted": False,
            "gold": str(gold_path),
        }
    ]


def test_resolve_path_maps_container_app_paths(monkeypatch):
    repo_root = Path("/repo")
    monkeypatch.setattr(mine_failures, "REPO_ROOT", repo_root)

    assert mine_failures._resolve_path("/app/scripts/eval/openreview/paper.json") == (
        repo_root / "scripts" / "eval" / "openreview" / "paper.json"
    )


def test_cluster_missed_units_groups_by_embedding_similarity(tmp_path):
    units = [
        {"text": "Need stronger baseline comparison.", "severity_weight": 0.8},
        {"text": "Baseline comparison is weak.", "severity_weight": 0.6},
        {"text": "The writing is hard to follow.", "severity_weight": 0.4},
    ]

    def embedder(texts):
        vectors = {
            "Need stronger baseline comparison.": [1.0, 0.0],
            "Baseline comparison is weak.": [0.9, 0.1],
            "The writing is hard to follow.": [0.0, 1.0],
        }
        return [vectors[text] for text in texts]

    clusters = mine_failures.cluster_missed_units(units, cache_dir=tmp_path, threshold=0.5, embedder=embedder)

    assert [cluster["count"] for cluster in clusters] == [2, 1]
    assert clusters[0]["severity_weight"] == 1.4


def test_render_markdown_includes_locus_and_exemplars():
    scoreboard = {"venue": "Venue/2024", "aggregate": {"papers": 1, "mean_weakness_recall": 0.2}}
    clusters = [
        {
            "severity_weight": 1.4,
            "count": 2,
            "units": [
                {
                    "paper_id": "paper1",
                    "unit_id": "u1",
                    "reviewer": "anon1",
                    "severity_weight": 0.8,
                    "text": "Need stronger baseline comparison.",
                }
            ],
        }
    ]
    labels = [{"name": "Experimental comparison gap", "node": "reviewer_panel_node", "proposal": "Check baselines."}]

    markdown = mine_failures.render_markdown(scoreboard, clusters, labels)

    assert "Experimental comparison gap" in markdown
    assert "Proposed locus: `reviewer_panel_node`" in markdown
    assert "Need stronger baseline comparison." in markdown

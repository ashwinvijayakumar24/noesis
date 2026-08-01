import importlib.util
import json
import sys
from pathlib import Path


def _load_atomize_module():
    repo_root = Path(__file__).resolve().parents[3]
    module_path = repo_root / "scripts" / "eval" / "atomize_reviews.py"
    spec = importlib.util.spec_from_file_location("atomize_reviews_for_tests", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["atomize_reviews_for_tests"] = module
    spec.loader.exec_module(module)
    return module


atomize_reviews = _load_atomize_module()


def _gold():
    return {
        "paper_id": "paper1",
        "meta_review": {"primary_reasons": "The method lacks ablation study evidence."},
        "reviews": [
            {
                "reviewer": "anon1",
                "rating": 3,
                "confidence": 5,
                "weaknesses": "The method lacks ablation study evidence.",
                "questions": "Why omit the baseline?",
            }
        ],
    }


def test_compute_severity_weight_is_deterministic_and_clamped():
    assert atomize_reviews.compute_severity_weight(3, 5, False) == 0.7
    assert atomize_reviews.compute_severity_weight(3, 5, True) == 1.0
    assert atomize_reviews.compute_severity_weight(10, 1, False) == 0.1


def test_atomize_paper_writes_and_reuses_cache(tmp_path, monkeypatch):
    calls = {"count": 0}

    def fake_atomize(review, client=None):
        calls["count"] += 1
        return [
            {"kind": "weakness", "text": "The method lacks ablation study evidence."},
            {"kind": "question", "text": "Why omit the baseline?"},
        ]

    monkeypatch.setattr(atomize_reviews, "_atomize_with_llm", fake_atomize)

    first_stats = {"cache_hits": 0, "llm_calls": 0}
    second_stats = {"cache_hits": 0, "llm_calls": 0}
    first = atomize_reviews.atomize_paper(_gold(), cache_dir=tmp_path, stats=first_stats)
    second = atomize_reviews.atomize_paper(_gold(), cache_dir=tmp_path, stats=second_stats)

    assert calls["count"] == 1
    assert first_stats == {"cache_hits": 0, "llm_calls": 1}
    assert second_stats == {"cache_hits": 1, "llm_calls": 0}
    assert first == second
    assert [unit["unit_id"] for unit in first] == ["paper1::anon1::01", "paper1::anon1::02"]
    assert first[0]["severity_weight"] == 1.0
    assert first[1]["severity_weight"] == 0.7
    cache_files = list(tmp_path.glob("*.json"))
    assert len(cache_files) == 1
    assert json.loads(cache_files[0].read_text())["units"][0]["kind"] == "weakness"


def test_atomize_paper_ignores_empty_units(tmp_path, monkeypatch):
    monkeypatch.setattr(
        atomize_reviews,
        "_atomize_with_llm",
        lambda review, client=None: [
            {"kind": "other", "text": ""},
            {"kind": "other", "text": "Is the baseline appropriate?"},
        ],
    )

    units = atomize_reviews.atomize_paper(_gold(), cache_dir=tmp_path)

    assert len(units) == 1
    assert units[0]["kind"] == "question"

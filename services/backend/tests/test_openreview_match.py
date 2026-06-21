import importlib.util
import sys
from pathlib import Path


def _load_match_module():
    repo_root = Path(__file__).resolve().parents[3]
    module_path = repo_root / "scripts" / "eval" / "match.py"
    spec = importlib.util.spec_from_file_location("openreview_match_for_tests", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["openreview_match_for_tests"] = module
    spec.loader.exec_module(module)
    return module


openreview_match = _load_match_module()


def _embedding_for(text):
    text = text.lower()
    if "ablation" in text:
        return [1.0, 0.0, 0.0]
    if "baseline" in text:
        return [0.0, 1.0, 0.0]
    return [0.0, 0.0, 1.0]


def test_match_prefilters_and_caches_confirmations(tmp_path):
    noesis_items = [
        {"id": "n1", "text": "The paper lacks an ablation study."},
        {"id": "n2", "text": "The baseline comparison is weak."},
    ]
    review_units = [
        {"unit_id": "u1", "text": "Missing ablation experiments."},
        {"unit_id": "u2", "text": "The writing is unclear."},
    ]
    calls = {"embed": 0, "confirm": 0}

    def embedder(texts):
        calls["embed"] += 1
        return [_embedding_for(text) for text in texts]

    def confirmer(pairs):
        calls["confirm"] += 1
        return [
            {
                "index": pair["index"],
                "confirmed": "ablation" in pair["noesis_text"].lower(),
                "reason": "same concern",
            }
            for pair in pairs
        ]

    first_stats = {}
    first = openreview_match.match(
        noesis_items,
        review_units,
        cache_dir=tmp_path,
        embedder=embedder,
        confirmer=confirmer,
        stats=first_stats,
    )
    second_stats = {}
    second = openreview_match.match(
        noesis_items,
        review_units,
        cache_dir=tmp_path,
        embedder=embedder,
        confirmer=confirmer,
        stats=second_stats,
    )

    assert calls == {"embed": 1, "confirm": 1}
    assert first == second
    assert first == [
        {
            "noesis_id": "n1",
            "unit_id": "u1",
            "cosine": 1.0,
            "confirmed": True,
            "reason": "same concern",
        }
    ]
    assert first_stats["total_pairs"] == 4
    assert first_stats["candidate_pairs"] == 1
    assert first_stats["embedded_texts"] == 4
    assert first_stats["confirmed_pairs"] == 1
    assert second_stats["embed_calls"] == 0
    assert second_stats["confirm_calls"] == 0
    assert second_stats["embed_cache_hits"] == 4
    assert second_stats["confirm_cache_hits"] == 1


def test_item_text_uses_export_like_fields():
    assert openreview_match._item_text({"problem": "Problem text"}) == "Problem text"
    assert openreview_match._item_text({"description": "Description text"}) == "Description text"


def test_as_bool_does_not_treat_false_strings_as_true():
    assert openreview_match._as_bool(True) is True
    assert openreview_match._as_bool("true") is True
    assert openreview_match._as_bool("YES") is True
    assert openreview_match._as_bool(False) is False
    assert openreview_match._as_bool("false") is False
    assert openreview_match._as_bool("NO") is False
    assert openreview_match._as_bool("") is False

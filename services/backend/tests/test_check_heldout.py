import importlib.util
import sys
from pathlib import Path


def _load_module():
    repo_root = Path(__file__).resolve().parents[3]
    module_path = repo_root / "scripts" / "eval" / "check_heldout.py"
    spec = importlib.util.spec_from_file_location("check_heldout_for_tests", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["check_heldout_for_tests"] = module
    spec.loader.exec_module(module)
    return module


check_heldout = _load_module()


def test_manifest_validates_non_ml_papers(tmp_path, monkeypatch):
    pdf = tmp_path / "paper.pdf"
    pdf.write_text("pdf")
    monkeypatch.setattr(check_heldout, "_resolve_eval_path", lambda value: pdf)

    manifest = {
        "papers": [
            {"paper_id": "p1", "field": "biology", "pdf_path": "p1.pdf"},
            {"paper_id": "p2", "field": "climate_science", "pdf_path": "p2.pdf"},
            {"paper_id": "p3", "field": "quantum_computing", "pdf_path": "p3.pdf"},
        ]
    }

    assert check_heldout.validate_manifest(manifest) == []


def test_manifest_rejects_ml_and_missing_pdf(tmp_path, monkeypatch):
    missing = tmp_path / "missing.pdf"
    monkeypatch.setattr(check_heldout, "_resolve_eval_path", lambda value: missing)
    manifest = {
        "papers": [
            {"paper_id": "p1", "field": "machine_learning", "pdf_path": "p1.pdf"},
            {"paper_id": "p2", "field": "biology", "pdf_path": "p2.pdf"},
        ]
    }

    failures = check_heldout.validate_manifest(manifest)

    assert any("3-5" in failure for failure in failures)
    assert any("ML-tagged" in failure for failure in failures)
    assert any("does not exist" in failure for failure in failures)


def test_results_guard_requires_zero_hallucination_and_anchor_within_baseline():
    manifest = {
        "papers": [
            {"paper_id": "p1", "field": "biology", "pdf_path": "p1.pdf"},
            {"paper_id": "p2", "field": "climate_science", "pdf_path": "p2.pdf"},
            {"paper_id": "p3", "field": "quantum_computing", "pdf_path": "p3.pdf"},
        ]
    }
    results = {
        "rows": [
            {"paper_id": "p1", "hallucination_rate": 0.0, "anchor_quality": 0.2},
            {"paper_id": "p2", "hallucination_rate": 0.1, "anchor_quality": 0.2},
            {"paper_id": "p3", "hallucination_rate": 0.0, "anchor_quality": 0.2},
        ]
    }
    baseline = {"aggregate": {"mean_anchor_quality": 0.5}}

    failures = check_heldout.validate_results(manifest, results, baseline)

    assert any("hallucination" in failure for failure in failures)
    assert any("anchor quality" in failure for failure in failures)

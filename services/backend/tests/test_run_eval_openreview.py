import importlib.util
import json
import sys
import types
from argparse import Namespace
from pathlib import Path


def _load_run_eval_module():
    repo_root = Path(__file__).resolve().parents[3]
    module_path = repo_root / "scripts" / "eval" / "run_eval.py"
    spec = importlib.util.spec_from_file_location("run_eval_for_tests", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["run_eval_for_tests"] = module
    spec.loader.exec_module(module)
    return module


run_eval = _load_run_eval_module()


def _write_gold(root: Path, paper_id: str) -> None:
    pdf_path = root / "pdfs" / f"{paper_id}.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(b"%PDF-1.4\n")
    gold_path = root / "openreview" / "ICLR.cc_2024_Conference" / f"{paper_id}.json"
    gold_path.parent.mkdir(parents=True, exist_ok=True)
    gold_path.write_text(
        json.dumps(
            {
                "paper_id": paper_id,
                "pdf_path": str(pdf_path.relative_to(root)),
                "reviews": [{"weaknesses": "Missing baseline."}],
            }
        )
    )


def test_run_openreview_eval_paper_ids_selects_only_requested_files(tmp_path, monkeypatch):
    for paper_id in ("a", "b", "c"):
        _write_gold(tmp_path, paper_id)

    calls = []

    def fake_harness_run(draft_path, corpus_name):
        calls.append(draft_path.stem)
        out = tmp_path / f"{draft_path.stem}.export.json"
        out.write_text(json.dumps({"reviewer_panel_outputs": []}))
        return out

    monkeypatch.setattr(run_eval, "EVAL_DIR", tmp_path)
    monkeypatch.setattr(run_eval, "RESULTS_DIR", tmp_path / "results")
    monkeypatch.setitem(sys.modules, "scripts.eval.atomize_reviews", types.SimpleNamespace(atomize_paper=lambda gold: []))
    monkeypatch.setitem(sys.modules, "scripts.eval.fetch_openreview", types.SimpleNamespace(fetch_venue=lambda *args: None))
    monkeypatch.setitem(
        sys.modules,
        "scripts.eval.judge_openreview",
        types.SimpleNamespace(
            aggregate=lambda rows: {"papers": len(rows)},
            extract_noesis_items=lambda export: [],
            paper_field=lambda gold, field_map=None: "machine_learning",
            score_paper=lambda export_path, gold, matches: {"paper_id": gold["paper_id"]},
        ),
    )
    monkeypatch.setitem(sys.modules, "scripts.eval.match", types.SimpleNamespace(match=lambda items, units: []))
    monkeypatch.setitem(sys.modules, "scripts.eval.run_harness", types.SimpleNamespace(run=fake_harness_run))

    rc = run_eval.run_openreview_eval(
        Namespace(
            venue="ICLR.cc/2024/Conference",
            limit=1,
            paper_ids="b,c",
            field_map=None,
        )
    )

    assert rc == 0
    assert calls == ["b", "c"]


def test_run_openreview_eval_paper_ids_errors_on_unknown_id(tmp_path, monkeypatch, capsys):
    _write_gold(tmp_path, "a")
    monkeypatch.setattr(run_eval, "EVAL_DIR", tmp_path)
    monkeypatch.setattr(run_eval, "RESULTS_DIR", tmp_path / "results")
    monkeypatch.setitem(sys.modules, "scripts.eval.atomize_reviews", types.SimpleNamespace(atomize_paper=lambda gold: []))
    monkeypatch.setitem(sys.modules, "scripts.eval.fetch_openreview", types.SimpleNamespace(fetch_venue=lambda *args: None))
    monkeypatch.setitem(
        sys.modules,
        "scripts.eval.judge_openreview",
        types.SimpleNamespace(
            aggregate=lambda rows: {},
            extract_noesis_items=lambda export: [],
            paper_field=lambda gold, field_map=None: "unknown",
            score_paper=lambda export_path, gold, matches: {},
        ),
    )
    monkeypatch.setitem(sys.modules, "scripts.eval.match", types.SimpleNamespace(match=lambda items, units: []))
    monkeypatch.setitem(sys.modules, "scripts.eval.run_harness", types.SimpleNamespace(run=lambda *args: None))

    rc = run_eval.run_openreview_eval(
        Namespace(
            venue="ICLR.cc/2024/Conference",
            limit=1,
            paper_ids="missing",
            field_map=None,
        )
    )

    assert rc == 1
    assert "Unknown --paper-ids: missing" in capsys.readouterr().out

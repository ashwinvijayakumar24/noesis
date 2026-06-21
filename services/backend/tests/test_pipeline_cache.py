import importlib.util
import json
import sys
from pathlib import Path


def _load_cache_module():
    repo_root = Path(__file__).resolve().parents[3]
    module_path = repo_root / "scripts" / "eval" / "pipeline_cache.py"
    spec = importlib.util.spec_from_file_location("pipeline_cache_for_tests", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["pipeline_cache_for_tests"] = module
    spec.loader.exec_module(module)
    return module


pipeline_cache = _load_cache_module()


def test_pipeline_version_ignores_pyc_files(tmp_path):
    workflow = tmp_path / "workflow"
    workflow.mkdir()
    (workflow / "node.py").write_text("print('v1')\n")
    first = pipeline_cache.pipeline_version(workflow)

    pycache = workflow / "__pycache__"
    pycache.mkdir()
    (pycache / "node.cpython-313.pyc").write_bytes(b"compiled")

    assert pipeline_cache.pipeline_version(workflow) == first


def test_default_workflow_dir_uses_repo_layout_outside_container():
    workflow_dir = pipeline_cache.default_workflow_dir()

    assert workflow_dir.name == "draft_analysis"
    assert workflow_dir.exists()


def test_cache_key_changes_with_pdf_pipeline_and_corpus(tmp_path):
    paper = tmp_path / "paper.pdf"
    paper.write_bytes(b"%PDF first")
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "ref.txt").write_text("reference")

    base = pipeline_cache.cache_key(paper, "pipeline-a")

    assert pipeline_cache.cache_key(paper, "pipeline-b") != base
    assert pipeline_cache.cache_key(paper, "pipeline-a", "corpus", corpus) != base
    paper.write_bytes(b"%PDF second")
    assert pipeline_cache.cache_key(paper, "pipeline-a") != base


def test_put_and_get_cached_export(tmp_path):
    export = tmp_path / "export.json"
    export.write_text(json.dumps({"ok": True}))

    cached = pipeline_cache.put_cached("abc123", export, cache_dir=tmp_path / "cache")

    assert cached == tmp_path / "cache" / "abc123.json"
    assert pipeline_cache.get_cached("abc123", cache_dir=tmp_path / "cache") == cached
    assert json.loads(cached.read_text()) == {"ok": True}
    assert pipeline_cache.get_cached("missing", cache_dir=tmp_path / "cache") is None

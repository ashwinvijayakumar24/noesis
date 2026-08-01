"""
Full-pipeline export cache for eval runs.

Cache keys are content based: draft bytes + draft-analysis pipeline version,
plus corpus contents when a corpus is used.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
REPO_ROOT = EVAL_DIR.parent.parent
DEFAULT_CACHE_DIR = EVAL_DIR / "cache" / "exports"


def default_workflow_dir() -> Path:
    container_path = Path("/app/app/workflows/draft_analysis")
    if container_path.exists():
        return container_path
    return REPO_ROOT / "services" / "backend" / "app" / "workflows" / "draft_analysis"


def hash_directory(path: Path) -> str:
    digest = hashlib.sha256()
    if not path.exists():
        return "missing"
    for file_path in sorted(p for p in path.rglob("*") if p.is_file()):
        rel = file_path.relative_to(path).as_posix()
        if "__pycache__/" in rel or rel.endswith(".pyc") or rel == ".DS_Store":
            continue
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def pipeline_version(workflow_dir: Path | None = None) -> str:
    workflow_dir = workflow_dir or default_workflow_dir()
    return hash_directory(workflow_dir)


def _hash_corpus(corpus_dir: Path | None) -> str:
    if corpus_dir is None:
        return "no-corpus"
    return hash_directory(corpus_dir)


def cache_key(
    paper_path: Path,
    pipeline_version: str,
    corpus_name: str | None = None,
    corpus_dir: Path | None = None,
) -> str:
    digest = hashlib.sha256()
    digest.update(paper_path.read_bytes())
    digest.update(b"\0")
    digest.update(pipeline_version.encode("utf-8"))
    digest.update(b"\0")
    digest.update((corpus_name or "no-corpus").encode("utf-8"))
    digest.update(b"\0")
    digest.update(_hash_corpus(corpus_dir).encode("utf-8"))
    return digest.hexdigest()


def get_cached(key: str, cache_dir: Path = DEFAULT_CACHE_DIR) -> Path | None:
    path = cache_dir / f"{key}.json"
    return path if path.exists() else None


def put_cached(key: str, export_path: Path, cache_dir: Path = DEFAULT_CACHE_DIR) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached_path = cache_dir / f"{key}.json"
    shutil.copy2(export_path, cached_path)
    return cached_path

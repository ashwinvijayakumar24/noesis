"""Disk-cached query embeddings.

The sweep runs the same 59 queries at ~20 configurations. Re-embedding at each
point would cost ~1200 API calls, add network jitter to a microsecond-scale
latency measurement, and -- worst -- make two sweep points differ by more than
the parameter under test. So embeddings are computed ONCE, cached to disk keyed
by (model, query_id), and reused byte-identically everywhere.

The embedder is ``retrieval.adapters.production_embed_fn``, i.e. the same
``text-embedding-3-large`` at 1536 dims that ``scripts/eval/ingest.py`` built
the index with. Querying an index with a different model than it was built with
produces numbers that look like a bad retriever and are actually a bad ruler.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parent.parent / "cache" / "ann_sweep_embeddings"
DEFAULT_MODEL = "text-embedding-3-large"


def cache_path(model: str = DEFAULT_MODEL, cache_dir: Path | None = None) -> Path:
    d = Path(cache_dir) if cache_dir else CACHE_DIR
    return d / f"{model.replace('/', '_')}.json"


def _key(query_id: str, text: str) -> str:
    return hashlib.sha256(f"{query_id}\0{text}".encode("utf-8")).hexdigest()[:24]


def load_or_embed(
    items: list[tuple[str, str]],
    embed_fn=None,
    model: str = DEFAULT_MODEL,
    cache_dir: Path | None = None,
) -> dict[str, list[float]]:
    """``[(query_id, text)] -> {query_id: embedding}``, embedding only cache misses.

    Raises rather than silently returning partial results when ``embed_fn`` is
    None and the cache is incomplete: a sweep over a subset of its queries would
    still produce plausible-looking metrics.
    """
    path = cache_path(model, cache_dir)
    cached: dict[str, list[float]] = {}
    if path.exists():
        try:
            cached = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            cached = {}

    out: dict[str, list[float]] = {}
    missing: list[tuple[str, str, str]] = []
    for qid, text in items:
        k = _key(qid, text)
        if k in cached:
            out[qid] = cached[k]
        else:
            missing.append((qid, text, k))

    if missing:
        if embed_fn is None:
            raise RuntimeError(
                f"{len(missing)} of {len(items)} query embeddings are not cached at "
                f"{path} and no embed_fn was supplied. Refusing to sweep over a "
                "subset of the query set."
            )
        for qid, text, k in missing:
            vec = [float(x) for x in embed_fn(text)]
            cached[k] = vec
            out[qid] = vec
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cached))

    return out

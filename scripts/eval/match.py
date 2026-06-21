"""
Match Noesis critique items against atomized OpenReview reviewer units.

Pipeline:
1. Cache embeddings for both sides.
2. Cosine prefilter candidate pairs.
3. Cache GPT confirmation per surviving pair.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any, Callable

if Path("/app/app").exists():
    REPO_ROOT = Path("/app")
    if "/app" not in sys.path:
        sys.path.insert(0, "/app")
else:
    REPO_ROOT = Path(__file__).resolve().parent.parent.parent
    _svc = str(REPO_ROOT / "services" / "backend")
    if _svc not in sys.path:
        sys.path.insert(0, _svc)

EVAL_DIR = Path(__file__).resolve().parent
DEFAULT_CACHE_DIR = EVAL_DIR / "cache" / "match"
PROMPT_VERSION = "match_v1"

# Initial value chosen before hand-label calibration. Phase-2 calibration target:
# 30 labeled pairs with agreement >=0.85; update this comment with precision/recall.
COS_THRESHOLD = 0.55

Embedder = Callable[[list[str]], list[list[float]]]
Confirmer = Callable[[list[dict]], list[dict]]


def _stable_hash(parts: list[str]) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def _item_text(item: dict) -> str:
    for key in ("text", "problem", "description", "title", "recommendation"):
        value = item.get(key)
        if value:
            return str(value)
    return json.dumps(item, sort_keys=True)


def _embedding_cache_key(text: str) -> str:
    return _stable_hash(["text-embedding-3-small", "1536", text])


def _confirm_cache_key(noesis_text: str, unit_text: str) -> str:
    return _stable_hash([PROMPT_VERSION, noesis_text, unit_text])


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "y", "1", "confirmed"}
    return False


def _real_embed(texts: list[str]) -> list[list[float]]:
    from app.services.rag_ingest import embed_chunks

    data = embed_chunks(texts, model="text-embedding-3-small")
    return [list(item.embedding) for item in data]


def _embed_texts(
    texts: list[str],
    cache_dir: Path,
    embedder: Embedder | None,
    stats: dict[str, int] | None,
) -> list[list[float]]:
    embed_dir = cache_dir / "embed"
    embed_dir.mkdir(parents=True, exist_ok=True)
    vectors: list[list[float] | None] = []
    misses: list[tuple[int, str, Path]] = []

    for idx, text in enumerate(texts):
        path = embed_dir / f"{_embedding_cache_key(text)}.json"
        if path.exists():
            if stats is not None:
                stats["embed_cache_hits"] = stats.get("embed_cache_hits", 0) + 1
            vectors.append(json.loads(path.read_text())["embedding"])
        else:
            vectors.append(None)
            misses.append((idx, text, path))

    if misses:
        if stats is not None:
            stats["embed_calls"] = stats.get("embed_calls", 0) + 1
            stats["embedded_texts"] = stats.get("embedded_texts", 0) + len(misses)
        batch_embedder = embedder or _real_embed
        embedded = batch_embedder([text for _, text, _ in misses])
        if len(embedded) != len(misses):
            raise RuntimeError("Embedder returned wrong number of vectors")
        for (idx, _text, path), vector in zip(misses, embedded):
            vector = [float(v) for v in vector]
            path.write_text(json.dumps({"embedding": vector}) + "\n")
            vectors[idx] = vector

    return [vector for vector in vectors if vector is not None]


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _real_confirm(pairs: list[dict], client: Any | None = None) -> list[dict]:
    if client is None:
        from app.core.openai_client import get_openai_client

        client = get_openai_client()

    from app.core.openai_client import get_completion_params

    response = client.chat.completions.create(
        model="gpt-5.2",
        messages=[
            {
                "role": "system",
                "content": (
                    "You confirm whether a Noesis critique item and a human reviewer unit "
                    "raise the same underlying concern. Same topic but different concern = NO. "
                    "Return only JSON."
                ),
            },
            {
                "role": "user",
                "content": (
                    "For each pair, return {index, confirmed, reason}. "
                    f"Pairs: {json.dumps(pairs, ensure_ascii=True)}"
                ),
            },
        ],
        response_format={"type": "json_object"},
        max_completion_tokens=2000,
        temperature=0,
        **get_completion_params(),
    )
    content = response.choices[0].message.content or "{}"
    payload = json.loads(content)
    results = payload.get("pairs") or payload.get("results") or payload.get("matches")
    if not isinstance(results, list):
        raise RuntimeError(f"Matcher response missing pairs list: {content[:500]}")
    return results


def _confirm_pairs(
    candidate_pairs: list[dict],
    cache_dir: Path,
    confirmer: Confirmer | None,
    client: Any | None,
    stats: dict[str, int] | None,
) -> list[dict]:
    confirm_dir = cache_dir / "confirm"
    confirm_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict | None] = [None] * len(candidate_pairs)
    misses: list[dict] = []

    for idx, pair in enumerate(candidate_pairs):
        key = _confirm_cache_key(pair["noesis_text"], pair["unit_text"])
        path = confirm_dir / f"{key}.json"
        if path.exists():
            if stats is not None:
                stats["confirm_cache_hits"] = stats.get("confirm_cache_hits", 0) + 1
            results[idx] = json.loads(path.read_text())
        else:
            misses.append({"index": idx, **pair})

    if misses:
        if stats is not None:
            stats["confirm_calls"] = stats.get("confirm_calls", 0) + 1
            stats["confirmed_pairs"] = stats.get("confirmed_pairs", 0) + len(misses)
        confirm = confirmer or (lambda pairs: _real_confirm(pairs, client=client))
        confirmed = confirm(misses)
        by_index = {int(item["index"]): item for item in confirmed}
        for missed in misses:
            idx = int(missed["index"])
            item = by_index.get(idx)
            if item is None:
                raise RuntimeError(f"Missing confirmation for pair index {idx}")
            normalized = {
                "confirmed": _as_bool(item.get("confirmed")),
                "reason": str(item.get("reason") or ""),
            }
            key = _confirm_cache_key(missed["noesis_text"], missed["unit_text"])
            path = confirm_dir / f"{key}.json"
            path.write_text(json.dumps(normalized, indent=2, sort_keys=True) + "\n")
            results[idx] = normalized

    return [result for result in results if result is not None]


def match(
    noesis_items: list[dict],
    review_units: list[dict],
    cache_dir: Path = DEFAULT_CACHE_DIR,
    embedder: Embedder | None = None,
    confirmer: Confirmer | None = None,
    client: Any | None = None,
    stats: dict[str, int] | None = None,
) -> list[dict]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    if stats is not None:
        for key in (
            "embed_cache_hits",
            "embed_calls",
            "embedded_texts",
            "confirm_cache_hits",
            "confirm_calls",
            "confirmed_pairs",
        ):
            stats.setdefault(key, 0)
    noesis_texts = [_item_text(item) for item in noesis_items]
    unit_texts = [str(unit.get("text") or "") for unit in review_units]
    vectors = _embed_texts(noesis_texts + unit_texts, cache_dir, embedder, stats)
    noesis_vectors = vectors[: len(noesis_texts)]
    unit_vectors = vectors[len(noesis_texts) :]

    candidate_pairs: list[dict] = []
    total_pairs = len(noesis_items) * len(review_units)
    for noesis_idx, noesis_vector in enumerate(noesis_vectors):
        for unit_idx, unit_vector in enumerate(unit_vectors):
            cosine = _cosine(noesis_vector, unit_vector)
            if cosine < COS_THRESHOLD:
                continue
            candidate_pairs.append(
                {
                    "noesis_index": noesis_idx,
                    "unit_index": unit_idx,
                    "noesis_id": str(noesis_items[noesis_idx].get("id") or noesis_idx),
                    "unit_id": str(review_units[unit_idx].get("unit_id") or unit_idx),
                    "noesis_text": noesis_texts[noesis_idx],
                    "unit_text": unit_texts[unit_idx],
                    "cosine": round(cosine, 6),
                }
            )

    if stats is not None:
        stats["total_pairs"] = total_pairs
        stats["candidate_pairs"] = len(candidate_pairs)

    confirmations = _confirm_pairs(candidate_pairs, cache_dir, confirmer, client, stats)
    matches = []
    for pair, confirmation in zip(candidate_pairs, confirmations):
        matches.append(
            {
                "noesis_id": pair["noesis_id"],
                "unit_id": pair["unit_id"],
                "cosine": pair["cosine"],
                "confirmed": confirmation["confirmed"],
                "reason": confirmation["reason"],
            }
        )
    return matches


def main() -> int:
    parser = argparse.ArgumentParser(description="Match Noesis items to atomized OpenReview units.")
    parser.add_argument("--noesis-items", type=Path, required=True)
    parser.add_argument("--review-units", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    args = parser.parse_args()

    noesis_items = json.loads(args.noesis_items.read_text())
    review_units = json.loads(args.review_units.read_text())
    stats = {
        "embed_cache_hits": 0,
        "embed_calls": 0,
        "embedded_texts": 0,
        "confirm_cache_hits": 0,
        "confirm_calls": 0,
        "confirmed_pairs": 0,
    }
    results = match(noesis_items, review_units, cache_dir=args.cache_dir, stats=stats)
    print(json.dumps({"matches": results, "stats": stats}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

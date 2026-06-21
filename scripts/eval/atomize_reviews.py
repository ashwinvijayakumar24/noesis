"""
Atomize OpenReview reviewer text into matchable weakness/question units.

One reviewer cache entry covers both weaknesses and questions. The LLM only
splits text; severity weighting is deterministic and reproducible.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

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
DEFAULT_CACHE_DIR = EVAL_DIR / "cache" / "atomize"
PROMPT_VERSION = "atomize_reviews_v1"


def _stable_hash(parts: list[str]) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def _cache_key(paper_id: str, reviewer: str, weaknesses: str, questions: str) -> str:
    return _stable_hash([PROMPT_VERSION, paper_id, reviewer, weaknesses, questions])


def _response_content(response: Any) -> str:
    return response.choices[0].message.content or ""


def _atomize_with_llm(review: dict, client: Any | None = None) -> list[dict]:
    if client is None:
        from app.core.openai_client import get_openai_client

        client = get_openai_client()

    from app.core.openai_client import get_completion_params

    prompt = {
        "reviewer": review.get("reviewer", ""),
        "weaknesses": review.get("weaknesses", ""),
        "questions": review.get("questions", ""),
    }
    response = client.chat.completions.create(
        model="gpt-5.2",
        messages=[
            {
                "role": "system",
                "content": (
                    "Split peer-review text into atomic, independently-verifiable concerns. "
                    "Do not merge distinct issues. Do not invent. Preserve reviewer wording "
                    "inside each text field. Return only JSON."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Return JSON with shape {\"units\":[{\"kind\":\"weakness|question\","
                    "\"text\":\"...\"}]}. Same topic but different concern must be separate.\n\n"
                    f"{json.dumps(prompt, ensure_ascii=True)}"
                ),
            },
        ],
        response_format={"type": "json_object"},
        max_completion_tokens=1200,
        temperature=0,
        **get_completion_params(),
    )
    payload = json.loads(_response_content(response))
    units = payload.get("units")
    if not isinstance(units, list):
        raise RuntimeError("Atomizer response missing units list")
    return units


def _token_counts(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for token in re.findall(r"[A-Za-z0-9]+", text.lower()):
        if len(token) < 3:
            continue
        counts[token] = counts.get(token, 0) + 1
    return counts


def _cosine_text(a: str, b: str) -> float:
    left = _token_counts(a)
    right = _token_counts(b)
    if not left or not right:
        return 0.0
    dot = sum(count * right.get(token, 0) for token, count in left.items())
    norm_left = math.sqrt(sum(count * count for count in left.values()))
    norm_right = math.sqrt(sum(count * count for count in right.values()))
    return dot / (norm_left * norm_right)


def _appears_in_meta(unit_text: str, meta_review: dict) -> bool:
    primary_reasons = str(meta_review.get("primary_reasons") or "")
    if not primary_reasons:
        return False
    return _cosine_text(unit_text, primary_reasons) >= 0.6


def _numeric(value: Any, default: float) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if value in ("", None):
        return default
    match = re.match(r"^-?\d+(?:\.\d+)?", str(value).strip())
    return float(match.group(0)) if match else default


def compute_severity_weight(rating: Any, confidence: Any, in_meta: bool) -> float:
    rating_value = max(0.0, min(10.0, _numeric(rating, 5.0)))
    confidence_value = max(1.0, min(5.0, _numeric(confidence, 3.0)))
    weight = (1.0 - rating_value / 10.0) * (confidence_value / 5.0)
    if in_meta:
        weight *= 1.5
    return round(max(0.1, min(1.0, weight)), 4)


def _normalize_units(raw_units: list[dict], review: dict, gold: dict) -> list[dict]:
    normalized = []
    reviewer = str(review.get("reviewer") or "anon")
    for idx, unit in enumerate(raw_units, start=1):
        text = str(unit.get("text") or "").strip()
        kind = str(unit.get("kind") or "weakness").strip().lower()
        if not text:
            continue
        if kind not in {"weakness", "question"}:
            kind = "question" if "?" in text else "weakness"
        unit_id = f"{gold['paper_id']}::{reviewer}::{idx:02d}"
        in_meta = _appears_in_meta(text, gold.get("meta_review") or {})
        normalized.append(
            {
                "unit_id": unit_id,
                "reviewer": reviewer,
                "text": text,
                "kind": kind,
                "severity_weight": compute_severity_weight(
                    review.get("rating"),
                    review.get("confidence"),
                    in_meta,
                ),
            }
        )
    return normalized


def atomize_paper(
    gold: dict,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    client: Any | None = None,
    stats: dict[str, int] | None = None,
) -> list[dict]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    paper_id = str(gold.get("paper_id") or "")
    all_units: list[dict] = []

    for review in gold.get("reviews") or []:
        reviewer = str(review.get("reviewer") or "")
        weaknesses = str(review.get("weaknesses") or "")
        questions = str(review.get("questions") or "")
        key = _cache_key(paper_id, reviewer, weaknesses, questions)
        cache_path = cache_dir / f"{key}.json"
        if cache_path.exists():
            if stats is not None:
                stats["cache_hits"] = stats.get("cache_hits", 0) + 1
            raw_units = json.loads(cache_path.read_text()).get("units", [])
        else:
            if stats is not None:
                stats["llm_calls"] = stats.get("llm_calls", 0) + 1
            raw_units = _atomize_with_llm(review, client=client)
            cache_path.write_text(json.dumps({"units": raw_units}, indent=2, sort_keys=True) + "\n")
        all_units.extend(_normalize_units(raw_units, review, gold))

    return all_units


def _gold_paths(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    return sorted(path.rglob("*.json"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Atomize OpenReview gold reviews into weakness units.")
    parser.add_argument("gold_path", type=Path, nargs="?", default=EVAL_DIR / "openreview")
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    args = parser.parse_args()

    total = 0
    stats: dict[str, int] = {"cache_hits": 0, "llm_calls": 0}
    for path in _gold_paths(args.gold_path):
        gold = json.loads(path.read_text())
        units = atomize_paper(gold, cache_dir=args.cache_dir, stats=stats)
        total += len(units)
        print(f"[atomize] {path}: {len(units)} units")
    print(
        f"[atomize] complete: {total} units "
        f"cache_hits={stats['cache_hits']} llm_calls={stats['llm_calls']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

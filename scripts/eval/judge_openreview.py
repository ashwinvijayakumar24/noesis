"""
Score Noesis exports against real OpenReview human-review gold.

This judge consumes:
- a Noesis export JSON from run_harness._export_result
- an OpenReview gold JSON from fetch_openreview.py
- matches from match.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
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
DEFAULT_CACHE_DIR = EVAL_DIR / "cache" / "grounding"
PROMPT_VERSION = "grounding_v1"

Grounder = Callable[[str, str], dict]


def _stable_hash(parts: list[str]) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def paper_field(gold: dict, field_map: dict[str, str] | None = None) -> str:
    """Return the explicit field tag for a paper, falling back to venue context."""
    paper_id = str(gold.get("paper_id") or "")
    if field_map and paper_id in field_map:
        return field_map[paper_id]
    if field_map and str(gold.get("title") or "") in field_map:
        return field_map[str(gold.get("title") or "")]

    for key in ("field", "primary_field", "subject_area", "area"):
        value = gold.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    venue = str(gold.get("venue") or "").lower()
    if "iclr" in venue or "neurips" in venue or "icml" in venue:
        return "machine_learning"
    return "unknown"


def _extract_pdf_text(gold: dict) -> str:
    pdf_path = Path(str(gold.get("pdf_path") or ""))
    if not pdf_path.is_absolute():
        pdf_path = EVAL_DIR / pdf_path
    if not pdf_path.exists():
        return ""
    try:
        import fitz

        doc = fitz.open(str(pdf_path))
        text = "\n".join(page.get_text() for page in doc)
        doc.close()
        return text
    except Exception:
        return ""


def extract_noesis_items(export: dict) -> list[dict]:
    items: list[dict] = []

    for task in export.get("durable_revision_tasks") or []:
        text = task.get("problem") or task.get("why_it_matters") or task.get("suggested_action")
        if not text:
            continue
        items.append(
            {
                "id": str(task.get("id")),
                "source": "revision_task",
                "text": str(text),
                "anchor_text": str(task.get("anchor_text") or task.get("text_snippet") or ""),
            }
        )

    for panel in export.get("reviewer_panel_outputs") or []:
        reviewer_id = str(panel.get("reviewer_id") or panel.get("id") or "reviewer")
        for idx, weakness in enumerate(panel.get("weaknesses") or [], start=1):
            items.append(
                {
                    "id": f"{panel.get('id', reviewer_id)}::weakness::{idx}",
                    "source": "reviewer_panel",
                    "text": str(weakness),
                    "anchor_text": "",
                }
            )

    for gap in export.get("coverage_gaps") or []:
        text = gap.get("description") or gap.get("reasoning")
        if not text:
            continue
        items.append(
            {
                "id": str(gap.get("id")),
                "source": "coverage_gap",
                "text": str(text),
                "anchor_text": str(gap.get("text_snippet") or ""),
            }
        )

    return items


def _readiness_score(export: dict) -> float | None:
    metadata = (export.get("analysis") or {}).get("analysis_metadata") or {}
    score = metadata.get("readiness_score")
    return float(score) if isinstance(score, (int, float)) else None


def _anchor_found(anchor_text: str, paper_text: str) -> bool:
    if not anchor_text.strip() or not paper_text:
        return False
    anchor = _norm(anchor_text)
    text = _norm(paper_text)
    if anchor in text:
        return True
    return anchor[:240] in text if len(anchor) > 240 else False


def _real_ground_claim(claim: str, paper_text: str) -> dict:
    from app.core.openai_client import get_completion_params, get_openai_client

    client = get_openai_client()
    excerpt = paper_text[:50000]
    response = client.chat.completions.create(
        model="gpt-5.2",
        messages=[
            {
                "role": "system",
                "content": (
                    "Determine whether the critique claim is grounded in the paper text. "
                    "A grounded critique may be unraised by reviewers; only mark false when "
                    "the paper text contradicts it or provides no support. Return JSON."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {"claim": claim, "paper_text_excerpt": excerpt},
                    ensure_ascii=True,
                ),
            },
        ],
        response_format={"type": "json_object"},
        max_completion_tokens=500,
        temperature=0,
        **get_completion_params(),
    )
    payload = json.loads(response.choices[0].message.content or "{}")
    return {"grounded": bool(payload.get("grounded")), "reason": str(payload.get("reason") or "")}


def _ground_claim(claim: str, paper_text: str, cache_dir: Path, grounder: Grounder | None) -> dict:
    cache_dir.mkdir(parents=True, exist_ok=True)
    paper_hash = hashlib.sha256(paper_text.encode("utf-8")).hexdigest()
    key = _stable_hash([PROMPT_VERSION, claim, paper_hash])
    path = cache_dir / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text())
    result = grounder(claim, paper_text) if grounder else _real_ground_claim(claim, paper_text)
    normalized = {"grounded": bool(result.get("grounded")), "reason": str(result.get("reason") or "")}
    path.write_text(json.dumps(normalized, indent=2, sort_keys=True) + "\n")
    return normalized


def score_paper(
    export_path: Path,
    gold: dict,
    matches: list[dict],
    cache_dir: Path = DEFAULT_CACHE_DIR,
    grounder: Grounder | None = None,
) -> dict:
    export = json.loads(export_path.read_text()) if isinstance(export_path, Path) else export_path
    noesis_items = extract_noesis_items(export)
    paper_text = _extract_pdf_text(gold)
    confirmed = [m for m in matches if m.get("confirmed")]
    matched_unit_ids = {str(m.get("unit_id")) for m in confirmed}
    matched_noesis_ids = {str(m.get("noesis_id")) for m in confirmed}

    review_units = gold.get("review_units") or []
    total_weight = sum(float(unit.get("severity_weight", 1.0)) for unit in review_units)
    matched_weight = sum(
        float(unit.get("severity_weight", 1.0))
        for unit in review_units
        if str(unit.get("unit_id")) in matched_unit_ids
    )
    weakness_recall = matched_weight / total_weight if total_weight else 0.0

    anchored = [
        item
        for item in noesis_items
        if item.get("anchor_text") and _anchor_found(str(item.get("anchor_text")), paper_text)
    ]
    anchor_quality = len(anchored) / len(noesis_items) if noesis_items else 0.0

    hallucinations = []
    grounded_count = 0
    for item in noesis_items:
        if item["id"] in matched_noesis_ids:
            grounded_count += 1
            continue
        if _anchor_found(str(item.get("anchor_text") or ""), paper_text):
            grounded_count += 1
            continue
        if not paper_text:
            continue
        grounded = _ground_claim(item["text"], paper_text, cache_dir, grounder)
        if grounded["grounded"]:
            grounded_count += 1
        else:
            hallucinations.append({"noesis_id": item["id"], "text": item["text"], "reason": grounded["reason"]})

    precision = grounded_count / len(noesis_items) if noesis_items else 0.0
    hallucination_rate = len(hallucinations) / len(noesis_items) if noesis_items else 0.0

    return {
        "paper_id": gold.get("paper_id"),
        "field": paper_field(gold),
        "accepted": bool(gold.get("accepted")),
        "readiness_score": _readiness_score(export),
        "weakness_recall": round(weakness_recall, 4),
        "precision": round(precision, 4),
        "hallucination_rate": round(hallucination_rate, 4),
        "anchor_quality": round(anchor_quality, 4),
        "matched_unit_ids": sorted(matched_unit_ids),
        "hallucinations": hallucinations,
        "counts": {
            "noesis_items": len(noesis_items),
            "review_units": len(review_units),
            "confirmed_matches": len(confirmed),
        },
    }


def _rank(values: list[float]) -> list[float]:
    indexed = sorted(enumerate(values), key=lambda pair: pair[1])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        j = i
        while j + 1 < len(indexed) and indexed[j + 1][1] == indexed[i][1]:
            j += 1
        rank = (i + j + 2) / 2.0
        for k in range(i, j + 1):
            ranks[indexed[k][0]] = rank
        i = j + 1
    return ranks


def _pearson(a: list[float], b: list[float]) -> float | None:
    if len(a) < 2 or len(a) != len(b):
        return None
    mean_a = sum(a) / len(a)
    mean_b = sum(b) / len(b)
    num = sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b))
    den_a = math.sqrt(sum((x - mean_a) ** 2 for x in a))
    den_b = math.sqrt(sum((y - mean_b) ** 2 for y in b))
    if den_a == 0 or den_b == 0:
        return None
    return num / (den_a * den_b)


def aggregate(per_paper: list[dict]) -> dict:
    scored = [row for row in per_paper if row.get("readiness_score") is not None]
    rho = None
    if len(scored) >= 2:
        readiness = [float(row["readiness_score"]) for row in scored]
        accepted = [1.0 if row.get("accepted") else 0.0 for row in scored]
        rho_val = _pearson(_rank(readiness), _rank(accepted))
        rho = round(rho_val, 4) if rho_val is not None else None

    def mean(key: str) -> float:
        values = [float(row[key]) for row in per_paper if row.get(key) is not None]
        return round(sum(values) / len(values), 4) if values else 0.0

    by_field: dict[str, dict] = {}
    fields = sorted({str(row.get("field") or "unknown") for row in per_paper})
    for field in fields:
        rows = [row for row in per_paper if str(row.get("field") or "unknown") == field]
        by_field[field] = {
            "papers": len(rows),
            "mean_weakness_recall": mean_for(rows, "weakness_recall"),
            "mean_precision": mean_for(rows, "precision"),
            "mean_hallucination_rate": mean_for(rows, "hallucination_rate"),
            "mean_anchor_quality": mean_for(rows, "anchor_quality"),
        }

    return {
        "papers": len(per_paper),
        "mean_weakness_recall": mean("weakness_recall"),
        "mean_precision": mean("precision"),
        "mean_hallucination_rate": mean("hallucination_rate"),
        "mean_anchor_quality": mean("anchor_quality"),
        "decision_spearman_rho": rho,
        "by_field": by_field,
    }


def mean_for(rows: list[dict], key: str) -> float:
    values = [float(row[key]) for row in rows if row.get(key) is not None]
    return round(sum(values) / len(values), 4) if values else 0.0


def main() -> int:
    parser = argparse.ArgumentParser(description="Score a Noesis export against OpenReview gold.")
    parser.add_argument("--export", type=Path, required=True)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--matches", type=Path, required=True)
    args = parser.parse_args()

    gold = json.loads(args.gold.read_text())
    matches = json.loads(args.matches.read_text())
    result = score_paper(args.export, gold, matches)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""
Score Noesis exports against real OpenReview human-review gold.

This judge consumes:
- a Noesis export JSON from run_harness._export_result
- an OpenReview gold JSON from fetch_openreview.py
- matches from match.py

!!! BREAKING METRIC CHANGE (2026-07-30) — read before comparing to old scoreboards !!!

The old `precision` field counted a Noesis item as "correct" if it matched a gold
review unit OR its anchor appeared in the PDF OR an LLM judged it grounded. Three
different properties were OR'd into one number, so an item that no human reviewer
ever raised still scored as a hit whenever a model blessed it. That definition
could not produce a miss: it reported `mean_precision: 1.0` and, because
`hallucination_rate` was defined as `1 - precision`, `mean_hallucination_rate: 0.0`.
Both numbers were near-tautological and must not be quoted.

Those three properties are now reported as three distinct metrics:

  precision_vs_gold   matched a human review unit / total items.
                      This is the honest precision. REPLACES `precision`.
                      The `precision` key is GONE — it was not renamed in place,
                      because a same-named field with a different meaning is worse
                      than a rename. Consumers must migrate.

  groundedness        anchor verifiable verbatim in the source PDF / total items.
                      A real property, but NOT precision. Numerically identical to
                      the pre-existing `anchor_quality`, which is retained unchanged
                      as an alias for existing consumers (check_heldout.py).

  llm_relevance_rate  fraction of LLM-adjudicated items the judge model called
                      grounded. INFORMATIONAL ONLY. It can never promote an item
                      into precision_vs_gold or into groundedness.

  ungrounded_rate     items whose anchor cannot be verified in the source / total.
                      This is what hallucination is now measured against.

`hallucination_rate` KEEPS ITS NAME BUT ITS MEANING CHANGED: it is now exactly
`ungrounded_rate` (unverifiable anchor), not the old `1 - precision`. It is kept
because check_heldout.py gates on `hallucination_rate > 0.0` and dropping the key
would silently weaken that guard to a `or 0.0` no-op. Under the new definition the
guard is strictly stronger, never weaker. `ungrounded_rate` is the unambiguous name;
prefer it in new code.

Aggregate keys follow the same migration: `mean_precision` is GONE, replaced by
`mean_precision_vs_gold`, `mean_groundedness`, `mean_llm_relevance_rate`, and
`mean_ungrounded_rate`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import unicodedata
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
    text = unicodedata.normalize("NFKC", text or "")
    text = text.replace("\u00ad", "")
    text = text.translate(
        str.maketrans(
            {
                "“": '"',
                "”": '"',
                "‘": "'",
                "’": "'",
                "–": "-",
                "—": "-",
                "−": "-",
                "∼": "~",
                "≈": "~",
                "π": "pi",
                "α": "alpha",
                "ω": "omega",
                "θ": "theta",
                "η": "eta",
                "ρ": "rho",
            }
        )
    )
    text = re.sub(r"-\s+", "", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def _compact_norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", _norm(text))


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
        text = _critique_text(task)
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
        panel_id = str(panel.get("id") or reviewer_id)
        issues = panel.get("issues") or []
        if issues:
            for idx, issue in enumerate(issues, start=1):
                if not isinstance(issue, dict):
                    continue
                text = issue.get("problem") or issue.get("description") or issue.get("title")
                if not text:
                    continue
                items.append(
                    {
                        "id": f"{panel_id}::{reviewer_id}::issue::{idx}",
                        "source": "reviewer_panel_issue",
                        "reviewer_id": reviewer_id,
                        "issue_type": str(issue.get("issue_type") or ""),
                        "problem": str(text),
                        "text": str(text),
                        "anchor_text": str(issue.get("anchor_text") or ""),
                    }
                )
        else:
            for idx, weakness in enumerate(panel.get("weaknesses") or [], start=1):
                items.append(
                    {
                        "id": f"{panel_id}::weakness::{idx}",
                        "source": "reviewer_panel",
                        "reviewer_id": reviewer_id,
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


def _critique_text(item: dict) -> str:
    parts = [
        str(item.get(key) or "").strip()
        for key in ("problem", "why_it_matters", "suggested_action")
    ]
    combined = _strip_eval_boilerplate(" ".join(part for part in parts if part))
    if combined:
        return combined
    for key in ("description", "title", "recommendation"):
        value = item.get(key)
        if value:
            return str(value)
    return ""


def _strip_eval_boilerplate(text: str) -> str:
    text = re.sub(
        r"\bNamed by the meta-reviewer as a blocking item for acceptance\.\s*",
        "",
        text or "",
    )
    text = re.sub(r"\bAddress the issue described above\.\s*", "", text)
    return re.sub(r"\s+", " ", text).strip()


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
    if len(anchor) > 240 and anchor[:240] in text:
        return True

    compact_anchor = _compact_norm(anchor_text)
    if len(compact_anchor) < 40:
        return False
    compact_text = _compact_norm(paper_text)
    if compact_anchor in compact_text:
        return True
    return compact_anchor[:240] in compact_text if len(compact_anchor) > 240 else False


def _real_ground_claim(claim: str, paper_text: str) -> dict:
    for var in ("NOESIS_LLM_KILL_SWITCH", "EVAL_REPLAY_ONLY"):
        if os.environ.get(var, "").strip().lower() not in ("", "0", "false", "no"):
            raise RuntimeError(
                f"judge_openreview grounding call blocked: {var} is set. "
                "Pass a grounder= stub or warm the grounding cache."
            )

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

    total_items = len(noesis_items)

    # --- precision against gold: matched a real human review unit. Nothing else. ---
    matched_items = [item for item in noesis_items if item["id"] in matched_noesis_ids]
    precision_vs_gold = len(matched_items) / total_items if total_items else 0.0

    # --- groundedness: anchor verifiable verbatim in the source PDF. NOT precision. ---
    grounded_items = [
        item
        for item in noesis_items
        if item.get("anchor_text") and _anchor_found(str(item.get("anchor_text")), paper_text)
    ]
    grounded_ids = {item["id"] for item in grounded_items}
    groundedness = len(grounded_items) / total_items if total_items else 0.0

    # --- ungrounded items drive hallucination rate. The LLM judge cannot rescue them. ---
    ungrounded_items = [item for item in noesis_items if item["id"] not in grounded_ids]
    ungrounded_rate = len(ungrounded_items) / total_items if total_items else 0.0

    # --- LLM-judged relevance: informational only, never promotes an item. ---
    llm_judged = 0
    llm_relevant = 0
    hallucinations = []
    for item in ungrounded_items:
        reason = "anchor not verifiable in source"
        if paper_text:
            verdict = _ground_claim(item["text"], paper_text, cache_dir, grounder)
            llm_judged += 1
            if verdict["grounded"]:
                llm_relevant += 1
            reason = f"{reason}; llm_relevance={verdict['grounded']}: {verdict['reason']}"
        hallucinations.append(
            {
                "noesis_id": item["id"],
                "text": item["text"],
                "reason": reason,
                "matched_gold": item["id"] in matched_noesis_ids,
            }
        )

    llm_relevance_rate = llm_relevant / llm_judged if llm_judged else 0.0

    return {
        "paper_id": gold.get("paper_id"),
        "field": paper_field(gold),
        "accepted": bool(gold.get("accepted")),
        "readiness_score": _readiness_score(export),
        "weakness_recall": round(weakness_recall, 4),
        # Honest precision. Replaces the old, un-failable `precision` key.
        "precision_vs_gold": round(precision_vs_gold, 4),
        # Anchor verifiable in source. Same value as anchor_quality, clearer name.
        "groundedness": round(groundedness, 4),
        # Informational only.
        "llm_relevance_rate": round(llm_relevance_rate, 4),
        "ungrounded_rate": round(ungrounded_rate, 4),
        # SAME NAME, NEW MEANING: now == ungrounded_rate, not 1 - precision.
        "hallucination_rate": round(ungrounded_rate, 4),
        "anchor_quality": round(groundedness, 4),
        "matched_unit_ids": sorted(matched_unit_ids),
        "hallucinations": hallucinations,
        "counts": {
            "noesis_items": total_items,
            "review_units": len(review_units),
            "confirmed_matches": len(confirmed),
            "matched_vs_gold": len(matched_items),
            "grounded_items": len(grounded_items),
            "ungrounded_items": len(ungrounded_items),
            "llm_judged": llm_judged,
            "llm_relevant": llm_relevant,
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
            "mean_precision_vs_gold": mean_for(rows, "precision_vs_gold"),
            "mean_groundedness": mean_for(rows, "groundedness"),
            "mean_llm_relevance_rate": mean_for(rows, "llm_relevance_rate"),
            "mean_ungrounded_rate": mean_for(rows, "ungrounded_rate"),
            "mean_hallucination_rate": mean_for(rows, "hallucination_rate"),
            "mean_anchor_quality": mean_for(rows, "anchor_quality"),
        }

    return {
        "papers": len(per_paper),
        "mean_weakness_recall": mean("weakness_recall"),
        "mean_precision_vs_gold": mean("precision_vs_gold"),
        "mean_groundedness": mean("groundedness"),
        "mean_llm_relevance_rate": mean("llm_relevance_rate"),
        "mean_ungrounded_rate": mean("ungrounded_rate"),
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

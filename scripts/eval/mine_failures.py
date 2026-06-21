"""
Mine missed OpenReview reviewer units into actionable blind-spot clusters.

Consumes results/openreview_scoreboard.json from run_eval.py and writes a
ranked Markdown report to results/blindspots.md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Callable

if Path("/app/app").exists():
    REPO_ROOT = Path("/app")
    if "/app" not in sys.path:
        sys.path.insert(0, "/app")
else:
    REPO_ROOT = Path(__file__).resolve().parent.parent.parent
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    _svc = str(REPO_ROOT / "services" / "backend")
    if _svc not in sys.path:
        sys.path.insert(0, _svc)

EVAL_DIR = Path(__file__).resolve().parent
DEFAULT_SCOREBOARD = EVAL_DIR / "results" / "openreview_scoreboard.json"
DEFAULT_OUT = EVAL_DIR / "results" / "blindspots.md"
DEFAULT_CACHE_DIR = EVAL_DIR / "cache" / "blindspots"
DEFAULT_MATCH_CACHE_DIR = EVAL_DIR / "cache" / "match"
PROMPT_VERSION = "blindspot_label_v1"
CLUSTER_THRESHOLD = 0.5

Embedder = Callable[[list[str]], list[list[float]]]
Labeler = Callable[[list[dict]], dict]


def _stable_hash(parts: list[str]) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def _resolve_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute() and path.exists():
        return path
    if path.is_absolute() and path.parts[:2] == ("/", "app"):
        return (REPO_ROOT / Path(*path.parts[2:])).resolve()
    if path.is_absolute():
        return path
    return (REPO_ROOT / path).resolve()


def _cosine(a: list[float], b: list[float]) -> float:
    from scripts.eval.match import _cosine as match_cosine

    return match_cosine(a, b)


def _embed_texts(texts: list[str], cache_dir: Path, embedder: Embedder | None) -> list[list[float]]:
    from scripts.eval.match import _embed_texts as match_embed_texts

    stats: dict[str, int] = {}
    return match_embed_texts(texts, cache_dir, embedder, stats)


def _review_units_for_gold(gold: dict) -> list[dict]:
    if gold.get("review_units"):
        return list(gold["review_units"])
    from scripts.eval.atomize_reviews import atomize_paper

    return atomize_paper(gold)


def collect_missed_units(scoreboard: dict) -> list[dict]:
    missed: list[dict] = []
    for row in scoreboard.get("rows") or []:
        gold_path = row.get("gold")
        if not gold_path:
            continue
        gold = json.loads(_resolve_path(gold_path).read_text())
        matched_unit_ids = {str(unit_id) for unit_id in row.get("matched_unit_ids") or []}
        for unit in _review_units_for_gold(gold):
            unit_id = str(unit.get("unit_id") or "")
            if unit_id in matched_unit_ids:
                continue
            text = str(unit.get("text") or "").strip()
            if not text:
                continue
            missed.append(
                {
                    "paper_id": str(row.get("paper_id") or gold.get("paper_id") or ""),
                    "unit_id": unit_id,
                    "reviewer": str(unit.get("reviewer") or ""),
                    "kind": str(unit.get("kind") or "weakness"),
                    "text": text,
                    "severity_weight": float(unit.get("severity_weight", 1.0)),
                    "accepted": bool(row.get("accepted")),
                    "gold": str(gold_path),
                }
            )
    return missed


def cluster_missed_units(
    missed_units: list[dict],
    cache_dir: Path = DEFAULT_CACHE_DIR,
    threshold: float = CLUSTER_THRESHOLD,
    embedder: Embedder | None = None,
) -> list[dict]:
    if not missed_units:
        return []
    embed_cache_dir = DEFAULT_MATCH_CACHE_DIR if cache_dir == DEFAULT_CACHE_DIR else cache_dir / "match"
    vectors = _embed_texts([unit["text"] for unit in missed_units], embed_cache_dir, embedder)
    ordered = sorted(range(len(missed_units)), key=lambda idx: missed_units[idx]["severity_weight"], reverse=True)
    clusters: list[dict] = []

    for idx in ordered:
        unit = missed_units[idx]
        vector = vectors[idx]
        best_cluster: dict | None = None
        best_score = -1.0
        for cluster in clusters:
            score = max(_cosine(vector, member["vector"]) for member in cluster["members"])
            if score > best_score:
                best_score = score
                best_cluster = cluster
        if best_cluster is None or best_score < threshold:
            clusters.append({"members": [{"unit": unit, "vector": vector}], "max_link": 1.0})
        else:
            best_cluster["members"].append({"unit": unit, "vector": vector})
            best_cluster["max_link"] = max(float(best_cluster.get("max_link", 0.0)), best_score)

    report_clusters: list[dict] = []
    for cluster in clusters:
        units = [member["unit"] for member in cluster["members"]]
        severity = sum(float(unit["severity_weight"]) for unit in units)
        report_clusters.append(
            {
                "units": units,
                "severity_weight": round(severity, 4),
                "count": len(units),
                "max_link": round(float(cluster.get("max_link", 0.0)), 4),
            }
        )
    return sorted(report_clusters, key=lambda c: (c["severity_weight"], c["count"]), reverse=True)


def _offline_label(units: list[dict]) -> dict:
    text = " ".join(unit["text"].lower() for unit in units)
    if any(word in text for word in ("baseline", "ablation", "comparison", "experiment")):
        return {
            "name": "Experimental comparison gap",
            "node": "reviewer_panel_node",
            "proposal": "Tighten the methodology reviewer to explicitly check baselines, ablations, and comparison fairness against the paper's main claims.",
        }
    if any(word in text for word in ("related work", "literature", "prior work", "novelty")):
        return {
            "name": "Literature positioning gap",
            "node": "reviewer_panel_node",
            "proposal": "Strengthen the literature-positioning reviewer to ask whether the claimed novelty is separated from closest prior work.",
        }
    if any(word in text for word in ("uncertainty", "statistical", "significance", "confidence interval")):
        return {
            "name": "Statistical evidence gap",
            "node": "run_quality_diagnostics",
            "proposal": "Add a diagnostics check for uncertainty reporting, statistical significance, and whether reported metrics support the stated claim.",
        }
    if any(word in text for word in ("clarity", "presentation", "write", "organization")):
        return {
            "name": "Presentation and clarity gap",
            "node": "reviewer_panel_node",
            "proposal": "Tune the clarity reviewer to surface ambiguous method descriptions and missing explanatory context as concrete revision tasks.",
        }
    return {
        "name": "Unclassified reviewer concern",
        "node": "reviewer_panel_node",
        "proposal": "Add a targeted reviewer-panel checklist item for the shared concern shown by the exemplars.",
    }


def _real_label_cluster(units: list[dict]) -> dict:
    from app.core.openai_client import get_completion_params, get_openai_client

    client = get_openai_client()
    exemplars = [{"text": unit["text"], "weight": unit["severity_weight"]} for unit in units[:8]]
    response = client.chat.completions.create(
        model="gpt-5.2",
        messages=[
            {
                "role": "system",
                "content": (
                    "Label a cluster of missed human-review concerns. Return JSON with "
                    "name, summary, node, proposal. The node must be one of: "
                    "detect_gaps_node, diagnostic_findings_node, reviewer_panel_node, "
                    "editor_pass_node, or new_check_node. Do not inject ML-specific content; "
                    "recommend transferable review behavior only."
                ),
            },
            {"role": "user", "content": json.dumps({"missed_units": exemplars}, ensure_ascii=True)},
        ],
        response_format={"type": "json_object"},
        max_completion_tokens=900,
        temperature=0,
        **get_completion_params(),
    )
    payload = json.loads(response.choices[0].message.content or "{}")
    return {
        "name": str(payload.get("name") or "Unclassified reviewer concern"),
        "summary": str(payload.get("summary") or ""),
        "node": str(payload.get("node") or "reviewer_panel_node"),
        "proposal": str(payload.get("proposal") or ""),
    }


def label_cluster(
    cluster: dict,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    labeler: Labeler | None = None,
    offline_labels: bool = False,
) -> dict:
    label_dir = cache_dir / "labels"
    label_dir.mkdir(parents=True, exist_ok=True)
    units = cluster["units"]
    key = _stable_hash([PROMPT_VERSION, *[unit["text"] for unit in units]])
    path = label_dir / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text())
    if labeler:
        label = labeler(units)
    elif offline_labels:
        label = _offline_label(units)
    else:
        label = _real_label_cluster(units)
    normalized = {
        "name": str(label.get("name") or "Unclassified reviewer concern"),
        "summary": str(label.get("summary") or ""),
        "node": str(label.get("node") or "reviewer_panel_node"),
        "proposal": str(label.get("proposal") or ""),
    }
    path.write_text(json.dumps(normalized, indent=2, sort_keys=True) + "\n")
    return normalized


def render_markdown(scoreboard: dict, clusters: list[dict], labels: list[dict]) -> str:
    aggregate = scoreboard.get("aggregate") or {}
    lines = [
        "# OpenReview Blind Spots",
        "",
        "Anti-overfit reminder: OpenReview is ML-heavy. Treat these as transferable review-behavior gaps, not field-content templates.",
        "",
        "## Summary",
        "",
        f"- Venue: `{scoreboard.get('venue', '')}`",
        f"- Papers: {aggregate.get('papers', len(scoreboard.get('rows') or []))}",
        f"- Mean weakness recall: {aggregate.get('mean_weakness_recall', 'n/a')}",
        f"- Missed units clustered: {sum(cluster['count'] for cluster in clusters)}",
        f"- Clusters: {len(clusters)}",
        "",
        "## Ranked Clusters",
        "",
    ]
    if not clusters:
        lines.append("No missed reviewer units found.")
        lines.append("")
        return "\n".join(lines)

    for idx, (cluster, label) in enumerate(zip(clusters, labels), start=1):
        lines.extend(
            [
                f"### {idx}. {label['name']}",
                "",
                f"- Severity weight: {cluster['severity_weight']}",
                f"- Missed units: {cluster['count']}",
                f"- Proposed locus: `{label['node']}`",
                f"- Fix proposal: {label['proposal']}",
            ]
        )
        if label.get("summary"):
            lines.append(f"- Summary: {label['summary']}")
        lines.extend(["", "Exemplars:"])
        for unit in cluster["units"][:5]:
            lines.append(
                f"- `{unit['paper_id']}` `{unit['unit_id']}` ({unit['reviewer']}, w={unit['severity_weight']:.2f}): {unit['text']}"
            )
        lines.append("")
    return "\n".join(lines)


def mine_failures(
    scoreboard_path: Path = DEFAULT_SCOREBOARD,
    out_path: Path = DEFAULT_OUT,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    threshold: float = CLUSTER_THRESHOLD,
    embedder: Embedder | None = None,
    labeler: Labeler | None = None,
    offline_labels: bool = False,
) -> dict:
    scoreboard = json.loads(scoreboard_path.read_text())
    missed = collect_missed_units(scoreboard)
    clusters = cluster_missed_units(missed, cache_dir=cache_dir, threshold=threshold, embedder=embedder)
    labels = [label_cluster(cluster, cache_dir=cache_dir, labeler=labeler, offline_labels=offline_labels) for cluster in clusters]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_markdown(scoreboard, clusters, labels) + "\n")
    return {"missed_units": len(missed), "clusters": len(clusters), "out": str(out_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Mine missed OpenReview reviewer units into blind-spot clusters.")
    parser.add_argument("--scoreboard", type=Path, default=DEFAULT_SCOREBOARD)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--threshold", type=float, default=CLUSTER_THRESHOLD)
    parser.add_argument("--offline-labels", action="store_true", help="Use deterministic labels instead of GPT labels.")
    args = parser.parse_args()

    result = mine_failures(
        scoreboard_path=args.scoreboard,
        out_path=args.out,
        cache_dir=args.cache_dir,
        threshold=args.threshold,
        offline_labels=args.offline_labels,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

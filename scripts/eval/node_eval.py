"""
Replay one draft-analysis node from a saved upstream state fixture.

State fixtures are written during OpenReview eval runs when EVAL_STATE_DIR is
set by the Makefile target.
"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import sys
import time
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
DEFAULT_STATE_DIR = EVAL_DIR / "cache" / "state"


def _node_registry() -> dict[str, Callable[[dict], Any]]:
    from app.workflows.draft_analysis.graph import _external_source_discovery_node_with_progress
    from app.workflows.draft_analysis.nodes.citation_judge import citation_judge_node
    from app.workflows.draft_analysis.nodes.citation_mapping import citation_mapping_node
    from app.workflows.draft_analysis.nodes.claim_categorization import categorize_claims_node
    from app.workflows.draft_analysis.nodes.claim_extraction import extract_claims_node
    from app.workflows.draft_analysis.nodes.diagnostic_findings import diagnostic_findings_node
    from app.workflows.draft_analysis.nodes.editor_pass import editor_pass_node
    from app.workflows.draft_analysis.nodes.extract_references import extract_references_node
    from app.workflows.draft_analysis.nodes.gap_detection import detect_gaps_node
    from app.workflows.draft_analysis.nodes.literature_search import literature_search_node
    from app.workflows.draft_analysis.nodes.manuscript_profile import manuscript_profile_node
    from app.workflows.draft_analysis.nodes.meta_reviewer import meta_reviewer_node
    from app.workflows.draft_analysis.nodes.report_synthesis import synthesize_report_node
    from app.workflows.draft_analysis.nodes.reviewer_judge import reviewer_judge_node
    from app.workflows.draft_analysis.nodes.reviewer_panel import reviewer_panel_node
    from app.workflows.draft_analysis.nodes.structural_checks import structural_checks_node
    from app.workflows.draft_analysis.nodes.structure_extraction import extract_structure_node
    from app.workflows.draft_analysis.nodes.verify_citations import verify_citations_node

    return {
        "extract_structure": extract_structure_node,
        "profile_manuscript": manuscript_profile_node,
        "extract_references": extract_references_node,
        "extract_claims": extract_claims_node,
        "categorize_claims": categorize_claims_node,
        "verify_citations": verify_citations_node,
        "search_literature": literature_search_node,
        "map_citations": citation_mapping_node,
        "detect_gaps": detect_gaps_node,
        "discover_external_sources": _external_source_discovery_node_with_progress,
        "citation_judge_node": citation_judge_node,
        "run_quality_diagnostics": diagnostic_findings_node,
        "structural_checks": structural_checks_node,
        "editor_pass_node": editor_pass_node,
        "reviewer_panel_node": reviewer_panel_node,
        "reviewer_judge_node": reviewer_judge_node,
        "meta_reviewer_node": meta_reviewer_node,
        "synthesize_report": synthesize_report_node,
    }


def state_path(node: str, paper: str, state_dir: Path = DEFAULT_STATE_DIR, reviewer_type: str | None = None) -> Path:
    filename = f"{node}__{reviewer_type}.json" if reviewer_type else f"{node}.json"
    return state_dir / paper / filename


async def _run_node(func: Callable[[dict], Any], state: dict) -> dict:
    result = func(state)
    if inspect.isawaitable(result):
        result = await result
    if not isinstance(result, dict):
        raise RuntimeError(f"Node returned non-dict result: {type(result).__name__}")
    return result


def _merge_state(state: dict, result: dict) -> dict:
    merged = dict(state)
    for key, value in result.items():
        if key == "reviewer_outputs" and isinstance(value, list):
            merged[key] = list(merged.get(key) or []) + value
        else:
            merged[key] = value
    return merged


def extract_node_items(node: str, result_state: dict) -> list[dict]:
    items: list[dict] = []

    for gap in result_state.get("coverage_gaps") or []:
        text = gap.get("description") or gap.get("reasoning")
        if text:
            items.append({"id": str(gap.get("id") or f"gap-{len(items)+1}"), "text": str(text), "source": "coverage_gap"})

    for finding in result_state.get("diagnostic_findings") or []:
        text = finding.get("problem") or finding.get("description") or finding.get("title")
        if text:
            items.append({"id": str(finding.get("id") or f"finding-{len(items)+1}"), "text": str(text), "source": "diagnostic_finding"})

    for task in result_state.get("revision_tasks") or []:
        text = task.get("problem") or task.get("description") or task.get("title")
        if text:
            items.append({"id": str(task.get("id") or f"task-{len(items)+1}"), "text": str(text), "source": "revision_task"})

    for source in result_state.get("external_sources") or []:
        text = source.get("relevance_reason") or source.get("description") or source.get("title")
        if text:
            items.append({"id": str(source.get("id") or source.get("doi") or f"source-{len(items)+1}"), "text": str(text), "source": "external_source"})

    for output in result_state.get("reviewer_outputs") or []:
        reviewer = output.get("reviewer_id") or output.get("reviewer_type") or "reviewer"
        for idx, weakness in enumerate(output.get("weaknesses") or [], start=1):
            items.append({"id": f"{reviewer}::weakness::{idx}", "text": str(weakness), "source": "reviewer_output"})
        for idx, issue in enumerate(output.get("issues") or [], start=1):
            text = issue.get("problem") or issue.get("description") or issue.get("title")
            if text:
                items.append({"id": f"{reviewer}::issue::{idx}", "text": str(text), "source": "reviewer_issue"})

    # Keep node-level reports honest: only return item families a node can produce.
    if node == "detect_gaps":
        return [item for item in items if item["source"] == "coverage_gap"]
    if node == "run_quality_diagnostics":
        return [item for item in items if item["source"] in {"diagnostic_finding", "revision_task"}]
    if node == "reviewer_panel_node":
        return [item for item in items if item["source"] in {"reviewer_output", "reviewer_issue"}]
    if node == "discover_external_sources":
        return [item for item in items if item["source"] == "external_source"]
    return items


def _default_gold_path(paper: str) -> Path:
    matches = sorted((EVAL_DIR / "openreview").glob(f"*/{paper}.json"))
    if not matches:
        raise FileNotFoundError(f"No OpenReview gold JSON found for paper {paper}")
    return matches[0]


def _recall(matches: list[dict], review_units: list[dict]) -> float:
    matched = {str(match.get("unit_id")) for match in matches if match.get("confirmed")}
    total_weight = sum(float(unit.get("severity_weight", 1.0)) for unit in review_units)
    matched_weight = sum(
        float(unit.get("severity_weight", 1.0))
        for unit in review_units
        if str(unit.get("unit_id")) in matched
    )
    return matched_weight / total_weight if total_weight else 0.0


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay one draft-analysis node from a saved eval state.")
    parser.add_argument("--node", required=True, help="Graph node name, e.g. detect_gaps")
    parser.add_argument("--paper", required=True, help="OpenReview paper id / PDF stem")
    parser.add_argument("--reviewer-type", default=None, help="Required for reviewer_panel_node fixture variants")
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE_DIR)
    parser.add_argument("--gold", type=Path, default=None)
    args = parser.parse_args()

    registry = _node_registry()
    if args.node not in registry:
        raise SystemExit(f"Unknown node {args.node!r}. Known: {', '.join(sorted(registry))}")

    fixture_path = state_path(args.node, args.paper, args.state_dir, args.reviewer_type)
    state = json.loads(fixture_path.read_text())

    started = time.monotonic()
    result = asyncio.run(_run_node(registry[args.node], state))
    elapsed = time.monotonic() - started
    result_state = _merge_state(state, result)
    items = extract_node_items(args.node, result_state)

    from scripts.eval.atomize_reviews import atomize_paper
    from scripts.eval.match import match

    gold_path = args.gold or _default_gold_path(args.paper)
    gold = json.loads(gold_path.read_text())
    review_units = atomize_paper(gold)
    stats = {
        "embed_cache_hits": 0,
        "embed_calls": 0,
        "embedded_texts": 0,
        "confirm_cache_hits": 0,
        "confirm_calls": 0,
        "confirmed_pairs": 0,
    }
    matches = match(items, review_units, stats=stats) if items else []
    report = {
        "paper_id": args.paper,
        "node": args.node,
        "state_fixture": str(fixture_path),
        "elapsed_seconds": round(elapsed, 3),
        "node_items": len(items),
        "review_units": len(review_units),
        "confirmed_matches": len([m for m in matches if m.get("confirmed")]),
        "severity_weighted_recall": round(_recall(matches, review_units), 4),
        "match_stats": stats,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

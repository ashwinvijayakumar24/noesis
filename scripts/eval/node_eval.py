"""
Replay draft-analysis nodes from saved upstream state fixtures, measuring
latency, token usage and cost per node.

State fixtures are written during OpenReview eval runs when EVAL_STATE_DIR is
set by the Makefile target. Replaying from a fixture is the only way to get a
real per-node measurement without standing up the whole Docker stack and
without touching a live draft: the node runs against exactly the upstream state
it saw in production.

Measurement
-----------
Each replay is wrapped in:

* a ``SpanKind.NODE`` span (``app.core.tracing``) -- wall time, status, and the
  fixture identity, appended to a JSONL trace file;
* an ``llm_label(node)`` block (``app.core.llm_budget``) -- so every LLM call
  made anywhere beneath the node is attributed to the node name rather than to
  the model name.

Token/cost numbers come from ``llm_budget``'s process-wide event log, sliced
around each replay, so they are the real recorded usage rather than a guess.

Cost control
------------
Replays make real, paid LLM calls. Three independent brakes:

1. ``--dry-run`` resolves the whole selection and prints the estimated call
   count without importing a node or making a single call.
2. A selection whose estimated LLM-call count exceeds ``--max-estimated-calls``
   (default 12) is refused unless ``--yes`` is passed. Node and paper lists are
   both required and repeatable -- there is deliberately no "run everything".
3. ``NOESIS_LLM_MAX_CALLS`` / ``NOESIS_LLM_MAX_SPEND_USD`` are checked before
   every replay (and inside every call by ``check_llm_allowed``). When one
   trips, the batch halts and records how far it got instead of dying.

KNOWN GAP: ``scripts/eval/match.py`` calls the OpenAI client directly rather
than through ``app.services.retry_utils``, so matcher embedding/confirmation
calls are neither recorded by ``llm_budget`` nor bounded by the ceilings above.
They are heavily disk-cached, and ``--no-metric`` skips them entirely; the
per-replay record carries ``match_stats`` so the uncounted calls are at least
visible. Fixing match.py is out of scope for this file.

Supabase
--------
Nothing here writes to Supabase. The three nodes that can persist directly
(``reviewer_panel_node``, ``reviewer_judge_node``, ``meta_reviewer_node``) gate
that path on ``not state["stage_only"]``; every fixture on disk has
``stage_only = True``, and :func:`_safe_state` re-asserts it before the replay
so a stale fixture cannot write either.

Results
-------
Append-only JSONL (``--results``). This repo has already lost its eval history
once by rewriting a results file in place; nothing here ever opens the results
file in anything but append mode.
"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import os
import re
import statistics
import sys
import time
import uuid
from datetime import datetime, timezone
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

from app.core.llm_budget import (  # noqa: E402
    LLMGuardrailError,
    check_llm_allowed,
    events as budget_events,
    llm_label,
)
from app.core.tracing import (  # noqa: E402
    NOESIS_NODE_NAME,
    SpanKind,
    configure_tracing,
    get_tracer,
)

EVAL_DIR = Path(__file__).resolve().parent
DEFAULT_STATE_DIR = EVAL_DIR / "cache" / "state"
DEFAULT_RESULTS_PATH = EVAL_DIR / "results" / "node_eval.jsonl"
DEFAULT_TRACE_PATH = EVAL_DIR / "results" / "node_eval_spans.jsonl"

#: Estimated LLM calls per replay, as ``(low, high)``; ``None`` means unknown.
#:
#: Derived on 2026-07-30 by reading each node module and the services it calls
#: for ``retry_utils.parse_chat_completion_with_retries*`` call sites. ``high``
#: counts conditional call sites (retries, domain-trigger audits) as taken.
#: This table only bounds the *pre-flight estimate* printed by ``--dry-run`` and
#: checked against ``--max-estimated-calls``; the enforced ceilings live in
#: ``llm_budget`` and are counted from real calls. An entry going stale makes
#: the estimate wrong, never the accounting.
ESTIMATED_LLM_CALLS: dict[str, tuple[int, int] | None] = {
    "extract_structure": (0, 0),
    "profile_manuscript": (0, 0),
    "extract_references": (0, 0),
    "extract_claims": (1, 1),
    "categorize_claims": (0, 0),
    "verify_citations": None,  # batched per citation; count is data-dependent
    "search_literature": (0, 0),
    "map_citations": (1, 1),
    "detect_gaps": (0, 0),
    "discover_external_sources": None,  # external APIs + LLM, data-dependent
    "citation_judge_node": (1, 1),
    "run_quality_diagnostics": (0, 0),
    "structural_checks": (1, 1),
    "editor_pass_node": (1, 1),
    "reviewer_panel_node": (1, 2),  # 1 review + 1 conditional domain audit
    "reviewer_judge_node": (0, 2),  # only fires for reviewers that failed judging
    "meta_reviewer_node": (1, 1),
    "synthesize_report": (0, 0),
}

#: What an unknown-cost node is assumed to cost when estimating a selection.
#: Deliberately pessimistic -- an unknown node should push a selection toward
#: needing ``--yes``, not sneak under the limit.
UNKNOWN_CALL_ESTIMATE = 4


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


def _safe_state(state: dict) -> dict:
    """Force the staging path so no replay can write to Supabase.

    ``reviewer_panel_node``, ``reviewer_judge_node`` and ``meta_reviewer_node``
    persist directly when ``stage_only`` is falsy. Fixtures currently all carry
    ``stage_only = True``, but a fixture is just a file on disk; asserting it
    here makes the no-writes property a property of this script rather than of
    the data it happens to be pointed at.
    """
    safe = dict(state)
    safe["stage_only"] = True
    return safe


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


def extract_node_items(node: str, result_state: dict) -> list[dict]:
    items: list[dict] = []

    for gap in result_state.get("coverage_gaps") or []:
        text = gap.get("description") or gap.get("reasoning")
        if text:
            items.append({"id": str(gap.get("id") or f"gap-{len(items)+1}"), "text": str(text), "source": "coverage_gap"})

    for finding in result_state.get("diagnostic_findings") or []:
        text = _critique_text(finding)
        if text:
            items.append({"id": str(finding.get("id") or f"finding-{len(items)+1}"), "text": str(text), "source": "diagnostic_finding"})

    for task in result_state.get("revision_tasks") or []:
        text = _critique_text(task)
        if text:
            items.append({"id": str(task.get("id") or f"task-{len(items)+1}"), "text": str(text), "source": "revision_task"})

    for source in result_state.get("external_sources") or []:
        text = source.get("relevance_reason") or source.get("description") or source.get("title")
        if text:
            items.append({"id": str(source.get("id") or source.get("doi") or f"source-{len(items)+1}"), "text": str(text), "source": "external_source"})

    for output in result_state.get("reviewer_outputs") or []:
        reviewer = output.get("reviewer_id") or output.get("reviewer_type") or "reviewer"
        issues = output.get("issues") or []
        if issues:
            for idx, issue in enumerate(issues, start=1):
                text = issue.get("problem") or issue.get("description") or issue.get("title")
                if text:
                    items.append(
                        {
                            "id": f"{reviewer}::issue::{idx}",
                            "problem": str(text),
                            "text": str(text),
                            "source": "reviewer_issue",
                            "anchor_text": str(issue.get("anchor_text") or ""),
                            "issue_type": str(issue.get("issue_type") or ""),
                            "reviewer_id": str(reviewer),
                        }
                    )
        else:
            for idx, weakness in enumerate(output.get("weaknesses") or [], start=1):
                items.append({"id": f"{reviewer}::weakness::{idx}", "text": str(weakness), "source": "reviewer_output"})

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


# ---------------------------------------------------------------------------
# Usage accounting
# ---------------------------------------------------------------------------

def _blank_usage() -> dict[str, Any]:
    return {
        "calls": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "cached_tokens": 0,
        "total_tokens": 0,
        "estimated_usd": 0.0,
        "unpriced_calls": 0,
        "by_label": {},
        "by_model": {},
    }


def _summarize_events(new_events: list[Any]) -> dict[str, Any]:
    """Fold a slice of ``llm_budget`` events into one usage dict."""
    usage = _blank_usage()
    for event in new_events:
        usage["calls"] += 1
        usage["prompt_tokens"] += event.prompt_tokens
        usage["completion_tokens"] += event.completion_tokens
        usage["cached_tokens"] += event.cached_tokens
        usage["total_tokens"] += event.prompt_tokens + event.completion_tokens
        if event.estimated_usd is None:
            usage["unpriced_calls"] += 1
        else:
            usage["estimated_usd"] += event.estimated_usd
        usage["by_label"][event.label] = usage["by_label"].get(event.label, 0) + 1
        usage["by_model"][event.model] = usage["by_model"].get(event.model, 0) + 1
    usage["estimated_usd"] = round(usage["estimated_usd"], 6)
    return usage


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------

def build_selection(
    nodes: list[str],
    papers: list[str],
    *,
    reviewer_type: str | None = None,
    state_dir: Path = DEFAULT_STATE_DIR,
) -> list[dict[str, Any]]:
    """One entry per (node, paper) pair, with fixture path and existence flag."""
    selection: list[dict[str, Any]] = []
    for node in nodes:
        for paper in papers:
            fixture = state_path(node, paper, state_dir, reviewer_type)
            selection.append(
                {
                    "node": node,
                    "paper": paper,
                    "reviewer_type": reviewer_type,
                    "fixture": str(fixture),
                    "fixture_exists": fixture.exists(),
                }
            )
    return selection


def estimate_calls(selection: list[dict[str, Any]], repeat: int) -> dict[str, Any]:
    """Estimated LLM calls for a selection, as a ``(low, high)`` band.

    Missing fixtures contribute nothing: they cannot run, so they cannot spend.
    """
    low = high = 0
    unknown_nodes: set[str] = set()
    for entry in selection:
        if not entry["fixture_exists"]:
            continue
        band = ESTIMATED_LLM_CALLS.get(entry["node"])
        if band is None:
            unknown_nodes.add(entry["node"])
            low += 0
            high += UNKNOWN_CALL_ESTIMATE
        else:
            low += band[0]
            high += band[1]
    return {
        "low": low * repeat,
        "high": high * repeat,
        "unknown_cost_nodes": sorted(unknown_nodes),
        "replays": sum(1 for e in selection if e["fixture_exists"]) * repeat,
        "missing_fixtures": sum(1 for e in selection if not e["fixture_exists"]),
    }


# ---------------------------------------------------------------------------
# Replay
# ---------------------------------------------------------------------------

def score_replay(
    node: str,
    result_state: dict,
    paper: str,
    gold_path: Path | None,
) -> dict[str, Any]:
    """The existing severity-weighted-recall metric for one replayed node.

    Runs under its own ``llm_label`` so matcher spend never lands on the node's
    token budget. NOTE: those calls bypass ``llm_budget`` entirely (see module
    docstring) -- ``match_stats`` is the only record of them.
    """
    from scripts.eval.atomize_reviews import atomize_paper
    from scripts.eval.match import match

    resolved_gold = gold_path or _default_gold_path(paper)
    gold = json.loads(resolved_gold.read_text())
    review_units = atomize_paper(gold)
    items = extract_node_items(node, result_state)
    stats = {
        "embed_cache_hits": 0,
        "embed_calls": 0,
        "embedded_texts": 0,
        "confirm_cache_hits": 0,
        "confirm_calls": 0,
        "confirmed_pairs": 0,
    }
    with llm_label(f"match:{node}"):
        matches = match(items, review_units, stats=stats) if items else []
    return {
        "gold_path": str(resolved_gold),
        "node_items": len(items),
        "review_units": len(review_units),
        "confirmed_matches": len([m for m in matches if m.get("confirmed")]),
        "severity_weighted_recall": round(_recall(matches, review_units), 4),
        "match_stats": stats,
    }


def replay_once(
    node: str,
    paper: str,
    node_func: Callable[[dict], Any],
    *,
    reviewer_type: str | None = None,
    state_dir: Path = DEFAULT_STATE_DIR,
    gold_path: Path | None = None,
    with_metric: bool = True,
    repeat_index: int = 0,
) -> dict[str, Any]:
    """Run one node once against one fixture and return its measurement record.

    Never raises for a node-level failure: a node that blows up produces a
    ``status = "error"`` record so a batch keeps going. Guardrail trips are the
    one exception -- they are re-raised so the caller can halt the batch.
    """
    fixture = state_path(node, paper, state_dir, reviewer_type)
    record: dict[str, Any] = {
        "record_type": "replay",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "node": node,
        "paper_id": paper,
        "reviewer_type": reviewer_type,
        "state_fixture": str(fixture),
        "repeat_index": repeat_index,
        "status": "ok",
    }

    # Before the node, not just inside it: a batch that has hit its ceiling
    # should stop cleanly rather than fail one call deep inside a node that may
    # swallow the exception and report a degraded result as a success.
    check_llm_allowed(node)

    state = _safe_state(json.loads(fixture.read_text()))
    events_before = len(budget_events())

    attributes = {
        NOESIS_NODE_NAME: node,
        "noesis.eval.paper_id": paper,
        "noesis.eval.fixture": str(fixture),
        "noesis.eval.repeat_index": repeat_index,
    }
    if reviewer_type:
        attributes["noesis.eval.reviewer_type"] = reviewer_type

    started = time.perf_counter()
    result_state: dict | None = None
    with get_tracer().start_span(node, kind=SpanKind.NODE, attributes=attributes) as span:
        try:
            with llm_label(node):
                result = asyncio.run(_run_node(node_func, state))
            result_state = _merge_state(state, result)
        except LLMGuardrailError:
            # A ceiling trip is a batch-level event, not a node result. Re-raise
            # so run_batch can halt and say how far it got. (Most nodes catch
            # their own LLM errors, so in practice the pre-flight
            # check_llm_allowed above is what actually stops a batch.)
            raise
        except Exception as exc:
            span.record_error(exc)
            record["status"] = "error"
            record["error_type"] = type(exc).__name__
            record["error_message"] = str(exc)[:1000]
        record["wall_seconds"] = round(time.perf_counter() - started, 4)
        record["trace_id"] = span.trace_id
        record["span_id"] = span.span_id

    record["usage"] = _summarize_events(budget_events()[events_before:])

    if result_state is not None and with_metric:
        try:
            record["metric"] = score_replay(node, result_state, paper, gold_path)
        except Exception as exc:
            record["metric"] = None
            record["metric_error"] = f"{type(exc).__name__}: {exc}"[:500]
    else:
        record["metric"] = None

    return record


# ---------------------------------------------------------------------------
# Results file (append-only)
# ---------------------------------------------------------------------------

def append_records(records: list[dict[str, Any]], path: Path) -> None:
    """Append JSONL. Open mode is ``"a"`` and nothing else, ever."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")


def load_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    return records


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def _spread(values: list[float]) -> dict[str, Any]:
    """mean/median/stdev/min/max. ``stdev`` is None for n < 2, never 0.0.

    Reporting 0.0 for a single sample would read as "perfectly stable" when the
    truth is "not measured". These nodes are genuinely non-deterministic:
    ``retry_utils`` strips ``temperature`` for every ``gpt-5.2*`` model and no
    seed is set anywhere, so run-to-run spread is a real property to report.
    """
    if not values:
        return {"n": 0, "mean": None, "median": None, "stdev": None, "min": None, "max": None}
    return {
        "n": len(values),
        "mean": round(statistics.fmean(values), 4),
        "median": round(statistics.median(values), 4),
        "stdev": round(statistics.stdev(values), 4) if len(values) > 1 else None,
        "min": round(min(values), 4),
        "max": round(max(values), 4),
    }


def aggregate(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group replay records by (node, paper, reviewer_type) and summarize."""
    groups: dict[tuple, list[dict]] = {}
    for record in records:
        if record.get("record_type") != "replay":
            continue
        key = (record["node"], record["paper_id"], record.get("reviewer_type"))
        groups.setdefault(key, []).append(record)

    summaries = []
    for (node, paper, reviewer_type), group in sorted(groups.items(), key=lambda kv: str(kv[0])):
        ok = [r for r in group if r.get("status") == "ok"]
        latencies = [float(r["wall_seconds"]) for r in ok if r.get("wall_seconds") is not None]
        recalls = [
            float(r["metric"]["severity_weighted_recall"])
            for r in ok
            if isinstance(r.get("metric"), dict)
            and r["metric"].get("severity_weighted_recall") is not None
        ]
        usage = [r.get("usage") or {} for r in ok]
        summaries.append(
            {
                "node": node,
                "paper_id": paper,
                "reviewer_type": reviewer_type,
                "runs": len(group),
                "failures": len(group) - len(ok),
                "latency_seconds": _spread(latencies),
                "severity_weighted_recall": _spread(recalls),
                "llm_calls": sum(int(u.get("calls") or 0) for u in usage),
                "prompt_tokens": sum(int(u.get("prompt_tokens") or 0) for u in usage),
                "completion_tokens": sum(int(u.get("completion_tokens") or 0) for u in usage),
                "cached_tokens": sum(int(u.get("cached_tokens") or 0) for u in usage),
                "estimated_usd": round(sum(float(u.get("estimated_usd") or 0.0) for u in usage), 6),
                "unpriced_calls": sum(int(u.get("unpriced_calls") or 0) for u in usage),
            }
        )
    return summaries


# ---------------------------------------------------------------------------
# Batch
# ---------------------------------------------------------------------------

def run_batch(
    selection: list[dict[str, Any]],
    *,
    repeat: int,
    config: dict[str, Any],
    registry: dict[str, Callable[[dict], Any]] | None = None,
    state_dir: Path = DEFAULT_STATE_DIR,
    gold_path: Path | None = None,
    with_metric: bool = True,
    results_path: Path = DEFAULT_RESULTS_PATH,
) -> dict[str, Any]:
    """Replay every entry in ``selection`` ``repeat`` times, appending as it goes.

    Records are appended after each replay rather than at the end, so a batch
    killed halfway still leaves behind every measurement it paid for.
    """
    registry = registry if registry is not None else _node_registry()
    run_id = uuid.uuid4().hex[:12]
    runnable = [entry for entry in selection if entry["fixture_exists"]]
    planned = len(runnable) * repeat

    records: list[dict[str, Any]] = []
    halted: dict[str, Any] | None = None

    for entry in runnable:
        if halted:
            break
        node = entry["node"]
        node_func = registry.get(node)
        if node_func is None:
            record = {
                "record_type": "replay",
                "run_id": run_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "node": node,
                "paper_id": entry["paper"],
                "reviewer_type": entry["reviewer_type"],
                "state_fixture": entry["fixture"],
                "repeat_index": 0,
                "status": "error",
                "error_type": "UnknownNode",
                "error_message": f"Node {node!r} is not in the registry",
                "usage": _blank_usage(),
                "metric": None,
            }
            records.append(record)
            append_records([record], results_path)
            continue

        for index in range(repeat):
            try:
                record = replay_once(
                    node,
                    entry["paper"],
                    node_func,
                    reviewer_type=entry["reviewer_type"],
                    state_dir=state_dir,
                    gold_path=gold_path,
                    with_metric=with_metric,
                    repeat_index=index,
                )
            except LLMGuardrailError as exc:
                halted = {
                    "reason": type(exc).__name__,
                    "message": str(exc)[:500],
                    "halted_at": {"node": node, "paper_id": entry["paper"], "repeat_index": index},
                }
                break
            record["run_id"] = run_id
            records.append(record)
            append_records([record], results_path)

    summaries = aggregate(records)
    completed = len([r for r in records if r.get("status") == "ok"])
    summary_record = {
        "record_type": "run_summary",
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "config": config,
        "planned_replays": planned,
        "attempted_replays": len(records),
        "completed_replays": completed,
        "failed_replays": len(records) - completed,
        "halted": halted,
        "per_node": summaries,
        "total_llm_calls": sum(s["llm_calls"] for s in summaries),
        "total_estimated_usd": round(sum(s["estimated_usd"] for s in summaries), 6),
    }
    append_records([summary_record], results_path)
    get_tracer().flush()
    return summary_record


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Replay draft-analysis nodes from saved eval state and measure them."
    )
    parser.add_argument("--node", required=True, action="append", dest="nodes",
                        help="Graph node name (repeatable), e.g. detect_gaps")
    parser.add_argument("--paper", required=True, action="append", dest="papers",
                        help="OpenReview paper id / PDF stem (repeatable)")
    parser.add_argument("--reviewer-type", default=None,
                        help="Required for reviewer_panel_node fixture variants")
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE_DIR)
    parser.add_argument("--gold", type=Path, default=None,
                        help="Gold JSON override; only valid with a single --paper")
    parser.add_argument("--repeat", type=int, default=1,
                        help="Replays per fixture, for variance (default 1)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the selection and estimated LLM calls; call nothing")
    parser.add_argument("--no-metric", action="store_true",
                        help="Skip severity-weighted-recall scoring (skips matcher LLM calls)")
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS_PATH,
                        help="Append-only JSONL results file")
    parser.add_argument("--trace-backend", default="jsonl", choices=["jsonl", "noop"])
    parser.add_argument("--trace-file", type=Path, default=DEFAULT_TRACE_PATH)
    parser.add_argument("--max-estimated-calls", type=int, default=12,
                        help="Refuse a selection estimated above this without --yes")
    parser.add_argument("--yes", action="store_true",
                        help="Confirm a selection above --max-estimated-calls")
    return parser


def _format_plan(selection: list[dict[str, Any]], estimate: dict[str, Any], repeat: int) -> str:
    lines = ["", "Selection", "---------"]
    for entry in selection:
        band = ESTIMATED_LLM_CALLS.get(entry["node"])
        cost = "?" if band is None else (str(band[0]) if band[0] == band[1] else f"{band[0]}-{band[1]}")
        mark = "ok " if entry["fixture_exists"] else "MISSING"
        variant = f" [{entry['reviewer_type']}]" if entry["reviewer_type"] else ""
        lines.append(
            f"  {mark}  {entry['node']}{variant} @ {entry['paper']}"
            f"  est_llm_calls/replay={cost}"
        )
    lines += [
        "",
        f"repeat                : {repeat}",
        f"runnable replays      : {estimate['replays']}",
        f"missing fixtures      : {estimate['missing_fixtures']}",
        f"estimated LLM calls   : {estimate['low']}-{estimate['high']}",
    ]
    if estimate["unknown_cost_nodes"]:
        lines.append(
            f"unknown-cost nodes    : {', '.join(estimate['unknown_cost_nodes'])} "
            f"(counted as {UNKNOWN_CALL_ESTIMATE}/replay for the upper bound)"
        )
    lines.append(
        "NOTE: matcher (severity-weighted recall) calls are NOT in this estimate and "
        "are NOT bounded by NOESIS_LLM_MAX_CALLS -- see module docstring."
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.gold is not None and len(args.papers) > 1:
        raise SystemExit("--gold applies to a single paper; pass one --paper or drop --gold")
    if args.repeat < 1:
        raise SystemExit("--repeat must be >= 1")

    unknown = [node for node in args.nodes if node not in ESTIMATED_LLM_CALLS]
    if unknown:
        raise SystemExit(
            f"Unknown node(s) {', '.join(sorted(unknown))}. "
            f"Known: {', '.join(sorted(ESTIMATED_LLM_CALLS))}"
        )

    selection = build_selection(
        args.nodes, args.papers, reviewer_type=args.reviewer_type, state_dir=args.state_dir
    )
    estimate = estimate_calls(selection, args.repeat)
    print(_format_plan(selection, estimate, args.repeat))

    if args.dry_run:
        print("\n--dry-run: nothing executed, no LLM calls made, no results written.")
        return 0

    if estimate["high"] > args.max_estimated_calls and not args.yes:
        print(
            f"\nREFUSED: estimated up to {estimate['high']} LLM calls, above "
            f"--max-estimated-calls={args.max_estimated_calls}. Re-run with --yes to confirm, "
            "or narrow the selection.",
        )
        return 2

    if not estimate["replays"]:
        print("\nNothing to run: no fixture in the selection exists.")
        return 1

    configure_tracing(backend=args.trace_backend, file_path=str(args.trace_file))
    config = {
        "nodes": args.nodes,
        "papers": args.papers,
        "reviewer_type": args.reviewer_type,
        "repeat": args.repeat,
        "with_metric": not args.no_metric,
        "state_dir": str(args.state_dir),
        "gold": str(args.gold) if args.gold else None,
        "trace_backend": args.trace_backend,
        "trace_file": str(args.trace_file),
        "estimated_llm_calls": {"low": estimate["low"], "high": estimate["high"]},
        "ceilings": {
            "NOESIS_LLM_MAX_CALLS": os.getenv("NOESIS_LLM_MAX_CALLS"),
            "NOESIS_LLM_MAX_SPEND_USD": os.getenv("NOESIS_LLM_MAX_SPEND_USD"),
        },
    }

    print(f"\nRunning {estimate['replays']} replay(s)...\n")
    summary = run_batch(
        selection,
        repeat=args.repeat,
        config=config,
        state_dir=args.state_dir,
        gold_path=args.gold,
        with_metric=not args.no_metric,
        results_path=args.results,
    )
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    print(f"\nAppended to {args.results} (append-only) | spans: {args.trace_file}")
    if summary.get("halted"):
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

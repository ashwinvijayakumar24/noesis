"""
Draft Analysis Workflow Graph

LangGraph workflow that orchestrates the complete draft analysis process.
"""

import functools
import json
import os
from contextlib import nullcontext
from pathlib import Path
from typing import Any

from langgraph.graph import StateGraph, END
from langgraph.types import Command, Send
from app.workflows.draft_analysis.state import DraftAnalysisState
from app.workflows.draft_analysis.checkpoints import (
    build_checkpointer,
    get_checkpoint_saver,
    interrupt_before_nodes,
)
from app.core.logging_config import get_logger
from app.core.llm_budget import llm_label
from app.core.privacy import safe_exception
from app.core.tracing import (
    NOESIS_NODE_NAME,
    SpanKind,
    extract_context,
    inject_context,
    run_attributes,
    start_span,
    use_context,
)
from app.services.progress_publisher import publish_progress

# Import all workflow nodes
from app.workflows.draft_analysis.nodes.structure_extraction import extract_structure_node
from app.workflows.draft_analysis.nodes.manuscript_profile import manuscript_profile_node
from app.workflows.draft_analysis.nodes.extract_references import extract_references_node
from app.workflows.draft_analysis.nodes.claim_extraction import extract_claims_node
from app.workflows.draft_analysis.nodes.claim_categorization import categorize_claims_node
from app.workflows.draft_analysis.nodes.literature_search import literature_search_node
from app.workflows.draft_analysis.nodes.citation_mapping import citation_mapping_node
from app.workflows.draft_analysis.nodes.gap_detection import detect_gaps_node
from app.workflows.draft_analysis.nodes.structural_checks import structural_checks_node
from app.workflows.draft_analysis.nodes.diagnostic_findings import diagnostic_findings_node
from app.workflows.draft_analysis.nodes.editor_pass import editor_pass_node
from app.workflows.draft_analysis.nodes.reviewer_panel import reviewer_panel_node
from app.workflows.draft_analysis.nodes.meta_reviewer import meta_reviewer_node
from app.workflows.draft_analysis.nodes.citation_judge import citation_judge_node
from app.workflows.draft_analysis.nodes.reviewer_judge import reviewer_judge_node
from app.workflows.draft_analysis.nodes.verify_citations import verify_citations_node
from app.workflows.draft_analysis.nodes.report_synthesis import synthesize_report_node

logger = get_logger(__name__)

#: Span attribute for the reviewer persona a ``reviewer_panel_node`` instance ran as.
#: ``core.tracing`` has no constant for it because the reviewer fan-out is specific
#: to this graph; the ``noesis.*`` prefix keeps it inside the same namespace.
NOESIS_REVIEWER_TYPE = "noesis.reviewer.type"


def _traced_node(node_name: str, fn):
    """Wrap a node callable in its NODE span and its token-attribution label.

    This is the single injection point for the whole graph: every node is
    registered through :func:`create_draft_analysis_workflow`, so wrapping here
    instruments all 18 of them without touching a single node body.

    Parenting:

    * Normal nodes inherit the ambient context (the RUN span, or an enclosing
      node span) through the contextvar -- LangGraph creates each node's task
      from the invoking context, so it propagates.
    * Fan-out branches arrive via ``Send`` with an explicitly injected
      ``SpanContext`` in their payload. ``use_context`` re-establishes it so the
      three reviewer spans are siblings under one parent rather than three
      orphaned roots. ``use_context(None)`` *clears* the parent, so it is only
      entered when a context was actually found -- otherwise a normal node would
      lose its RUN parent.

    With ``NOESIS_TRACING_BACKEND`` unset both context managers are effectively
    free (a noop adapter and two contextvar set/reset pairs).
    """

    @functools.wraps(fn)
    async def wrapper(state: DraftAnalysisState) -> DraftAnalysisState:
        parent = extract_context(state)
        attributes = {NOESIS_NODE_NAME: node_name}
        reviewer_type = state.get("reviewer_type")
        if reviewer_type:
            attributes[NOESIS_REVIEWER_TYPE] = reviewer_type
        with (
            use_context(parent) if parent is not None else nullcontext(),
            start_span(node_name, kind=SpanKind.NODE, attributes=attributes),
            llm_label(node_name),
        ):
            return await fn(state)

    return wrapper


def _dump_eval_state(node_name: str, state: DraftAnalysisState) -> None:
    """Write upstream node state for eval-only node replay when explicitly enabled."""
    state_dir = os.environ.get("EVAL_STATE_DIR", "")
    if not state_dir:
        return
    paper_id = os.environ.get("EVAL_STATE_PAPER_ID") or state.get("draft_id") or "unknown"
    reviewer_type = state.get("reviewer_type")
    filename = f"{node_name}__{reviewer_type}.json" if reviewer_type else f"{node_name}.json"
    out_dir = Path(state_dir) / str(paper_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / filename).write_text(
        json.dumps(dict(state), indent=2, ensure_ascii=False, default=str) + "\n"
    )


# ============================================
# PROGRESS-EMITTING NODE WRAPPERS
# ============================================

async def _extract_structure_node_with_progress(state: DraftAnalysisState) -> DraftAnalysisState:
    _dump_eval_state("extract_structure", state)
    draft_id = state.get("draft_id")
    if draft_id:
        await publish_progress(draft_id, "extract_structure_start", 4, "Analyzing draft structure...")
    result = extract_structure_node(state)
    if draft_id:
        await publish_progress(draft_id, "extract_structure", 10, "Draft structure analyzed")
    return result


async def _manuscript_profile_node_with_progress(state: DraftAnalysisState) -> DraftAnalysisState:
    _dump_eval_state("profile_manuscript", state)
    draft_id = state.get("draft_id")
    if draft_id:
        await publish_progress(draft_id, "manuscript_profile_start", 11, "Profiling manuscript type...")
    result = manuscript_profile_node(state)
    if draft_id:
        await publish_progress(draft_id, "manuscript_profile", 12, "Manuscript profile identified")
    return result


async def _extract_references_node_with_progress(state: DraftAnalysisState) -> DraftAnalysisState:
    _dump_eval_state("extract_references", state)
    draft_id = state.get("draft_id")
    if draft_id:
        await publish_progress(draft_id, "extract_references_start", 13, "Extracting reference list...")
    result = await extract_references_node(state)
    if draft_id:
        await publish_progress(draft_id, "extract_references", 15, "Reference list resolved")
    return result


async def _extract_claims_node_with_progress(state: DraftAnalysisState) -> DraftAnalysisState:
    _dump_eval_state("extract_claims", state)
    draft_id = state.get("draft_id")
    if draft_id:
        await publish_progress(draft_id, "extract_claims_start", 16, "Extracting research claims...")
    result = extract_claims_node(state)
    if draft_id:
        await publish_progress(draft_id, "extract_claims", 25, "Research claims extracted")
    return result


async def _categorize_claims_node_with_progress(state: DraftAnalysisState) -> DraftAnalysisState:
    _dump_eval_state("categorize_claims", state)
    draft_id = state.get("draft_id")
    if draft_id:
        await publish_progress(draft_id, "categorize_claims_start", 27, "Categorizing claims...")
    result = categorize_claims_node(state)
    if draft_id:
        await publish_progress(draft_id, "categorize_claims", 35, "Claims categorized")
    return result


async def _verify_citations_node_with_progress(state: DraftAnalysisState) -> DraftAnalysisState:
    _dump_eval_state("verify_citations", state)
    draft_id = state.get("draft_id")
    if draft_id:
        await publish_progress(draft_id, "verify_citations_start", 36, "Checking citation accuracy...")
    result = await verify_citations_node(state)
    if draft_id:
        await publish_progress(draft_id, "verify_citations", 37, "Citation accuracy checked")
    return result


async def _literature_search_node_with_progress(state: DraftAnalysisState) -> DraftAnalysisState:
    _dump_eval_state("search_literature", state)
    draft_id = state.get("draft_id")
    if draft_id:
        await publish_progress(draft_id, "search_literature_start", 38, "Searching literature...")
    result = await literature_search_node(state)
    if draft_id:
        await publish_progress(draft_id, "search_literature", 50, "Literature search complete")
    return result


async def _citation_mapping_node_with_progress(state: DraftAnalysisState) -> DraftAnalysisState:
    _dump_eval_state("map_citations", state)
    draft_id = state.get("draft_id")
    if draft_id:
        await publish_progress(draft_id, "map_citations_start", 52, "Mapping citations to claims...")
    result = await citation_mapping_node(state)
    if draft_id:
        await publish_progress(draft_id, "map_citations", 65, "Citations mapped")
    return result


async def _detect_gaps_node_with_progress(state: DraftAnalysisState) -> DraftAnalysisState:
    _dump_eval_state("detect_gaps", state)
    draft_id = state.get("draft_id")
    if draft_id:
        await publish_progress(draft_id, "detect_gaps_start", 67, "Detecting coverage gaps...")
    result = detect_gaps_node(state)
    if draft_id:
        await publish_progress(draft_id, "detect_gaps", 72, "Coverage gaps identified")
    return result


async def _external_source_discovery_node_with_progress(state: DraftAnalysisState) -> DraftAnalysisState:
    _dump_eval_state("discover_external_sources", state)
    draft_id = state.get("draft_id")
    if draft_id:
        await publish_progress(draft_id, "external_sources_start", 73, "Discovering external sources...")

    claims_with_citations = state.get("claims_with_citations", [])
    coverage_gaps = state.get("coverage_gaps", [])

    if os.environ.get("EVAL_SKIP_EXTERNAL_SOURCE_DISCOVERY") == "1":
        logger.info("[Workflow] External source discovery skipped by EVAL_SKIP_EXTERNAL_SOURCE_DISCOVERY=1")
        result: DraftAnalysisState = {
            "claims_with_citations": claims_with_citations,
            "coverage_gaps": coverage_gaps,
            "external_sources": [],
            "current_step": "External Source Discovery (Eval Skipped)",
            "progress_percentage": 74,
        }
        if draft_id:
            await publish_progress(draft_id, "external_sources", 74, "External source discovery skipped")
        return result

    try:
        from app.services.draft_external_source_discovery import (
            attach_external_sources_to_analysis,
            discover_external_sources_for_draft,
        )

        external_sources = await discover_external_sources_for_draft(
            draft_id=state["draft_id"],
            project_id=state["project_id"],
            user_id=state["user_id"],
            claims_with_citations=claims_with_citations,
            coverage_gaps=coverage_gaps,
            resolved_references=state.get("resolved_references") or [],
            manuscript_profile=state.get("manuscript_profile") or {},
        )
        attach_external_sources_to_analysis(
            claims_with_citations,
            coverage_gaps,
            external_sources,
        )
        result: DraftAnalysisState = {
            "claims_with_citations": claims_with_citations,
            "coverage_gaps": coverage_gaps,
            "external_sources": external_sources,
            "current_step": "External Source Discovery",
            "progress_percentage": 74,
        }
    except Exception as exc:
        logger.warning("[Workflow] External source discovery failed (non-fatal): %s", safe_exception(exc))
        warnings = state.get("warnings", [])
        warnings.append(f"External source discovery failed: {safe_exception(exc)}")
        result = {
            "warnings": warnings,
            "current_step": "External Source Discovery (Skipped)",
            "progress_percentage": 74,
        }

    if draft_id:
        await publish_progress(draft_id, "external_sources", 74, "External source discovery complete")
    return result


async def _citation_judge_node_with_progress(state: DraftAnalysisState) -> DraftAnalysisState:
    _dump_eval_state("citation_judge_node", state)
    draft_id = state.get("draft_id")
    if draft_id:
        await publish_progress(draft_id, "citation_judge_start", 75, "Judging citation relevance...")
    result = await citation_judge_node(state)
    if draft_id:
        await publish_progress(draft_id, "citation_judge", 76, "Citation quality assessed")
    return result


async def _reviewer_judge_node_with_progress(state: DraftAnalysisState) -> DraftAnalysisState:
    _dump_eval_state("reviewer_judge_node", state)
    draft_id = state.get("draft_id")
    if draft_id:
        await publish_progress(draft_id, "reviewer_judge_start", 88, "Judging review specificity...")
    result = await reviewer_judge_node(state)
    if draft_id:
        await publish_progress(draft_id, "reviewer_judge", 89, "Review quality assessed")
    return result


async def _structural_checks_node_with_progress(state: DraftAnalysisState) -> DraftAnalysisState:
    _dump_eval_state("structural_checks", state)
    draft_id = state.get("draft_id")
    if draft_id:
        await publish_progress(draft_id, "structural_checks_start", 79, "Running structural checks...")
    result = await structural_checks_node(state)
    if draft_id:
        await publish_progress(draft_id, "structural_checks", 80, "Structural checks complete")
    return result


async def _diagnostic_findings_node_with_progress(state: DraftAnalysisState) -> DraftAnalysisState:
    _dump_eval_state("run_quality_diagnostics", state)
    draft_id = state.get("draft_id")
    if draft_id:
        await publish_progress(draft_id, "diagnostic_findings_start", 77, "Running manuscript-specific diagnostics...")
    result = diagnostic_findings_node(state)
    if draft_id:
        await publish_progress(draft_id, "diagnostic_findings", 78, "Manuscript-specific diagnostics complete")
    return result


async def _editor_pass_node_with_progress(state: DraftAnalysisState) -> DraftAnalysisState:
    _dump_eval_state("editor_pass_node", state)
    draft_id = state.get("draft_id")
    if draft_id:
        await publish_progress(draft_id, "editor_pass_start", 81, "Running editorial desk check...")
    result = await editor_pass_node(state)
    if draft_id:
        await publish_progress(draft_id, "editor_pass", 82, "Editorial check complete")
    return result


async def _reviewer_panel_node_with_progress(state: DraftAnalysisState) -> DraftAnalysisState:
    _dump_eval_state("reviewer_panel_node", state)
    # Progress published per-reviewer inside the node; no outer wrapper needed
    return await reviewer_panel_node(state)


async def _meta_reviewer_node_with_progress(state: DraftAnalysisState) -> DraftAnalysisState:
    _dump_eval_state("meta_reviewer_node", state)
    draft_id = state.get("draft_id")
    if draft_id:
        await publish_progress(draft_id, "meta_review_start", 90, "Synthesizing reviewer panel...")
    result = await meta_reviewer_node(state)
    if draft_id:
        await publish_progress(draft_id, "meta_review", 93, "Review panel synthesis complete")
    return result


async def _synthesize_report_node_with_progress(state: DraftAnalysisState) -> DraftAnalysisState:
    _dump_eval_state("synthesize_report", state)
    draft_id = state.get("draft_id")
    if draft_id:
        await publish_progress(draft_id, "synthesize_report_start", 94, "Synthesizing report...")
    result = synthesize_report_node(state)
    if draft_id:
        await publish_progress(draft_id, "synthesize_report", 96, "Report synthesized")
    return result


# ============================================
# CONDITIONAL ROUTING FUNCTIONS
# ============================================

def route_after_claim_extraction(state: DraftAnalysisState) -> str:
    """
    Route after claim extraction based on claim count and confidence.

    Decision logic:
    - If < 3 claims: Flag for validation (but continue for now)
    - If > 50 claims: Flag for validation (but continue for now)
    - Otherwise: Proceed to categorization

    Note: In Phase 2.4, we'll add actual human validation here.
    For now, we just flag and continue.
    """
    claims = state.get("claims", [])
    should_validate = state.get("should_validate_claims", False)

    if should_validate:
        logger.warning(
            f"[Routing] Claims need validation ({len(claims)} claims), "
            f"but proceeding with analysis"
        )
        # In future: return "validate_claims"
        # For now: return "categorize_claims"

    return "categorize_claims"


def route_after_literature_search(state: DraftAnalysisState) -> str:
    """
    Route after literature search.

    Could implement iterative refinement here:
    - If search found < 50% citations: Refine and search again
    - If max iterations reached: Continue anyway
    - Otherwise: Proceed to citation mapping

    For now: Always proceed to citation mapping.
    """
    search_results = state.get("literature_search_results", [])
    search_iterations = state.get("search_iterations", 0)
    max_iterations = state.get("max_search_iterations", 1)

    # Count successful searches
    successful = sum(1 for r in search_results if r.get('result_count', 0) > 0)
    total = len(search_results)
    success_rate = successful / max(total, 1)

    logger.info(
        f"[Routing] Literature search: {successful}/{total} claims found literature "
        f"({success_rate:.1%} success rate)"
    )

    # Could add iterative refinement here in the future
    # For now, always proceed
    return "map_citations"


# ============================================
# PEER REVIEW PANEL ROUTING
# ============================================

REVIEWER_TYPES = ["methodology", "literature_positioning", "clarity"]


def _preliminary_anchor_coverage(state: DraftAnalysisState) -> float | None:
    """Fraction of mapped claims that carry a locatable anchor (page/char/coords) after
    citation mapping. Proxy for how anchorable the run is before reviewers run. Returns
    None when there are no mapped claims (don't halt on absence of data)."""
    cwc = state.get("claims_with_citations") or []
    if not cwc:
        return None
    located = 0
    for entry in cwc:
        claim = entry.get("claim") or entry
        if (
            claim.get("page_number") is not None
            or claim.get("char_start") is not None
            or entry.get("page_number") is not None
            or entry.get("char_start") is not None
        ):
            located += 1
    # No anchors at all = no evidence to make a call; skip the halt rather than
    # treating 0/N as a coverage failure (common for plaintext and fresh parses).
    if located == 0:
        return None
    return round(located / max(1, len(cwc)), 3)


def route_to_reviewer_panel(state: DraftAnalysisState):
    """
    After editor_pass: if desk-rejected route straight to synthesis,
    otherwise fan out to 4 parallel reviewers via LangGraph Send API.
    """
    editor = state.get("editor_decision") or {}
    if not editor.get("proceed_to_review", True):
        logger.info("[Routing] Editor desk-rejected — skipping reviewer panel")
        return "synthesize_report"

    # Preliminary gate (issue #12): if anchor coverage / parser quality already predict a
    # gate failure, halt BEFORE the reviewer panel + meta-review so tokens aren't burned
    # on output the publish gate would suppress. Reviewer panel runs only on parses that
    # clear this checkpoint.
    if os.environ.get("EVAL_DISABLE_PRE_REVIEWER_HALT") == "1":
        logger.info("[Routing] Preliminary reviewer halt disabled for eval")
    else:
        try:
            from app.services.draft_publish_gate import should_halt_before_reviewers
            parser_quality = state.get("parser_quality") or {}
            prelim = should_halt_before_reviewers(
                page_anchor_coverage=_preliminary_anchor_coverage(state),
                parser_quality_score=parser_quality.get("parser_quality_score"),
                parse_blocked=bool(parser_quality.get("parse_blocked")),
            )
            if prelim["halt"]:
                logger.warning(
                    "[Routing] Preliminary gate FAILED (%s) — skipping reviewer panel + meta-review",
                    "; ".join(prelim["reasons"]),
                )
                return "synthesize_report"
        except Exception as exc:  # never block the run on the preliminary gate itself
            logger.warning("[Routing] Preliminary gate check skipped: %s", safe_exception(exc))

    logger.info("[Routing] Editor approved — dispatching 3 parallel reviewers")
    # inject_context mutates its argument in place. That is safe *only* because
    # ``{**state, "reviewer_type": rt}`` is a fresh dict per branch -- never call
    # it on the live ``state``, which would stamp the trace key onto the graph's
    # own channels. Each branch carries the same parent context, so the three
    # reviewer spans come out as siblings of one parent sharing one trace_id.
    return [
        Send("reviewer_panel_node", inject_context({**state, "reviewer_type": rt}))
        for rt in REVIEWER_TYPES
    ]


# ============================================
# WORKFLOW GRAPH CONSTRUCTION
# ============================================

def create_draft_analysis_workflow(checkpointer=None) -> StateGraph:
    """
    Create the complete draft analysis workflow graph.

    Args:
        checkpointer: Optional LangGraph ``BaseCheckpointSaver``. When ``None``
            (the default, and what every existing caller passes) the graph is
            compiled with a bare ``workflow.compile()`` -- byte-for-byte the
            behaviour before checkpointing existed, with no checkpointer attached
            and no interrupt points. The branch below is deliberate rather than
            passing ``checkpointer=None`` through: it guarantees the disabled path
            cannot be perturbed by compile-time defaults.

    Workflow steps:
    1. Extract structure
    2. Extract claims
    3. (Optional) Validate claims → Currently skipped, returns to categorization
    4. Categorize claims
    5. Search literature (PARALLEL for all claims)
    6. (Optional) Refine search → Currently skipped
    7. Map citations to claims
    8. Detect coverage gaps
    9. Generate reviewer feedback
    10. Synthesize final report

    Returns:
        Compiled StateGraph ready for execution
    """
    logger.info("[Workflow] Creating draft analysis workflow graph")

    # Create the state graph
    workflow = StateGraph(DraftAnalysisState)

    # ============================================
    # ADD NODES
    # ============================================

    # Every node goes through _traced_node: one span + one token label per node,
    # applied once here instead of 18 times in the wrapper bodies.
    def add_node(name: str, fn) -> None:
        workflow.add_node(name, _traced_node(name, fn))

    add_node("extract_structure", _extract_structure_node_with_progress)
    add_node("profile_manuscript", _manuscript_profile_node_with_progress)
    add_node("extract_references", _extract_references_node_with_progress)
    add_node("extract_claims", _extract_claims_node_with_progress)
    add_node("categorize_claims", _categorize_claims_node_with_progress)
    add_node("verify_citations", _verify_citations_node_with_progress)
    add_node("search_literature", _literature_search_node_with_progress)
    add_node("map_citations", _citation_mapping_node_with_progress)
    add_node("detect_gaps", _detect_gaps_node_with_progress)
    add_node("discover_external_sources", _external_source_discovery_node_with_progress)
    add_node("citation_judge_node", _citation_judge_node_with_progress)
    add_node("run_quality_diagnostics", _diagnostic_findings_node_with_progress)
    add_node("structural_checks", _structural_checks_node_with_progress)
    add_node("editor_pass_node", _editor_pass_node_with_progress)
    add_node("reviewer_panel_node", _reviewer_panel_node_with_progress)
    add_node("reviewer_judge_node", _reviewer_judge_node_with_progress)
    add_node("meta_reviewer_node", _meta_reviewer_node_with_progress)
    add_node("synthesize_report", _synthesize_report_node_with_progress)

    # ============================================
    # ADD EDGES
    # ============================================

    # Set entry point
    workflow.set_entry_point("extract_structure")

    # Linear flow for most steps
    workflow.add_edge("extract_structure", "profile_manuscript")
    workflow.add_edge("profile_manuscript", "extract_references")
    workflow.add_edge("extract_references", "extract_claims")

    # Conditional routing after claim extraction
    workflow.add_conditional_edges(
        "extract_claims",
        route_after_claim_extraction,
        {
            "categorize_claims": "categorize_claims",
            # Future: "validate_claims": "validate_claims"
        }
    )

    # Continue with categorization → citation verification → literature search
    workflow.add_edge("categorize_claims", "verify_citations")
    workflow.add_edge("verify_citations", "search_literature")

    # Conditional routing after literature search
    workflow.add_conditional_edges(
        "search_literature",
        route_after_literature_search,
        {
            "map_citations": "map_citations",
            # Future: "refine_search": "refine_search"
        }
    )

    # citation mapping → gap detection → external sources → citation judge → diagnostics → structural checks → editor pass
    workflow.add_edge("map_citations", "detect_gaps")
    workflow.add_edge("detect_gaps", "discover_external_sources")
    workflow.add_edge("discover_external_sources", "citation_judge_node")
    workflow.add_edge("citation_judge_node", "run_quality_diagnostics")
    workflow.add_edge("run_quality_diagnostics", "structural_checks")
    workflow.add_edge("structural_checks", "editor_pass_node")

    # Editor pass → fan-out to 4 parallel reviewers OR desk-reject → synthesis
    workflow.add_conditional_edges(
        "editor_pass_node",
        route_to_reviewer_panel,
        {"synthesize_report": "synthesize_report"},
    )

    # Fan-in: all reviewer_panel_node instances → reviewer judge → meta_reviewer → synthesize
    workflow.add_edge("reviewer_panel_node", "reviewer_judge_node")
    workflow.add_edge("reviewer_judge_node", "meta_reviewer_node")
    workflow.add_edge("meta_reviewer_node", "synthesize_report")

    # End after synthesis
    workflow.add_edge("synthesize_report", END)

    # Compile the graph
    if checkpointer is None:
        compiled_workflow = workflow.compile()
    else:
        # interrupt_before is the static half of human-in-the-loop: the graph
        # durably stops before the named nodes and the run is resumed with
        # ``ainvoke(None, config)``. The dynamic half -- ``interrupt()`` raised
        # from inside a node -- needs nothing here beyond the checkpointer, since
        # LangGraph persists the interrupt against the thread. Both are
        # unreachable while the feature flag is off.
        compiled_workflow = workflow.compile(
            checkpointer=checkpointer,
            interrupt_before=interrupt_before_nodes() or None,
        )

    logger.info("[Workflow] Draft analysis workflow graph created successfully")

    return compiled_workflow


# ============================================
# WORKFLOW EXECUTION FUNCTIONS
# ============================================

async def run_draft_analysis_workflow(
    draft_id: str,
    project_id: str,
    user_id: str,
    draft_content: str,
    checkpoint_enabled: bool = True,
    paper_type: str | None = None,
    citation_style: str | None = None,
    analysis: dict | None = None,
    initial_structure: dict | None = None,
    parse_artifact: dict | None = None,
    parser_quality: dict | None = None,
    quality_retry_instruction: str | None = None,
    forced_route: str | None = None,
    analysis_run_id: str | None = None,
) -> DraftAnalysisState:
    """
    Run the complete draft analysis workflow.

    Args:
        draft_id: Unique identifier for the draft
        project_id: Project the draft belongs to
        user_id: User who owns the draft
        draft_content: Full text content of the draft
        checkpoint_enabled: Whether to save checkpoints (for resume capability)
        paper_type: Optional draft type for editor/reviewer context
        citation_style: Optional citation style for editor/reviewer context
        analysis: Existing draft_analysis.analysis payload, including Stage 1 editing feedback
        analysis_run_id: Optional draft_analysis_runs row id. Used only to key the
            root trace span; the caller may omit it, in which case the run span
            falls back to draft_id.

    Returns:
        Final workflow state with complete analysis

    The whole run is enclosed in a single RUN span, so every node span opened
    inside it inherits one trace_id and the run is one connected tree.
    """
    with start_span(
        "draft_analysis_run",
        kind=SpanKind.RUN,
        attributes=run_attributes(
            analysis_run_id=analysis_run_id or draft_id,
            draft_id=draft_id,
        ),
    ):
        return await _run_draft_analysis_workflow(
            draft_id=draft_id,
            project_id=project_id,
            user_id=user_id,
            draft_content=draft_content,
            checkpoint_enabled=checkpoint_enabled,
            paper_type=paper_type,
            citation_style=citation_style,
            analysis=analysis,
            initial_structure=initial_structure,
            parse_artifact=parse_artifact,
            parser_quality=parser_quality,
            quality_retry_instruction=quality_retry_instruction,
            forced_route=forced_route,
        )


async def _run_draft_analysis_workflow(
    draft_id: str,
    project_id: str,
    user_id: str,
    draft_content: str,
    checkpoint_enabled: bool = True,
    paper_type: str | None = None,
    citation_style: str | None = None,
    analysis: dict | None = None,
    initial_structure: dict | None = None,
    parse_artifact: dict | None = None,
    parser_quality: dict | None = None,
    quality_retry_instruction: str | None = None,
    forced_route: str | None = None,
) -> DraftAnalysisState:
    """Body of :func:`run_draft_analysis_workflow`, run inside the RUN span."""
    logger.info(f"[Workflow] ========== WORKFLOW START ==========")
    logger.info(f"[Workflow] draft_id={draft_id}")
    logger.info(f"[Workflow] project_id={project_id}")
    logger.info(f"[Workflow] user_id={user_id}")
    logger.info(f"[Workflow] draft_content length={len(draft_content)} chars")

    # Build the checkpointer BEFORE the graph, since it is a compile-time argument.
    # Returns None unless NOESIS_CHECKPOINT_ENABLED is set AND a DSN is configured,
    # so the default path is unchanged. ``rehydrate`` seeds the manuscript channels
    # that are never persisted, so a checkpoint written now can be read back within
    # this same run without a storage round-trip.
    lg_checkpointer = build_checkpointer(
        rehydrate={
            "draft_content": draft_content,
            "parse_artifact": parse_artifact or {},
            "structure": initial_structure or {},
        },
        user_id=user_id,
    )

    # Create the workflow
    logger.info(f"[Workflow] Creating workflow graph...")
    try:
        workflow = create_draft_analysis_workflow(checkpointer=lg_checkpointer)
        logger.info(f"[Workflow] Workflow graph created successfully")
    except Exception as e:
        logger.error("[Workflow] FATAL: Failed to create workflow graph: %s", safe_exception(e))
        raise

    # A thread_id is only meaningful with a checkpointer attached; passing config
    # when there is none keeps the disabled path identical to before.
    invoke_config = (
        {"configurable": {"thread_id": draft_id}} if lg_checkpointer is not None else None
    )

    # Initialize state
    logger.info(f"[Workflow] Initializing state...")
    initial_state: DraftAnalysisState = {
        "draft_id": draft_id,
        "project_id": project_id,
        "user_id": user_id,
        "draft_content": draft_content,
        "paper_type": paper_type or "journal_article",
        "citation_style": citation_style or "auto",
        "analysis": analysis or {},
        "parse_artifact": parse_artifact or {},
        "parser_quality": parser_quality or {},
        "forced_route": forced_route or "",
        "stage_only": True,
        "quality_retry_instruction": quality_retry_instruction or "",
        "current_step": "Starting",
        "progress_percentage": 0,
        "search_iterations": 0,
        "max_search_iterations": 1,
        # Must be initialised here so the Annotated reducer channel is seeded.
        "reviewer_outputs": [],
    }
    if initial_structure:
        initial_state["structure"] = initial_structure
    logger.info(f"[Workflow] State initialized: {list(initial_state.keys())}")

    try:
        # Run the workflow
        # Note: LangGraph automatically handles checkpointing if configured
        if checkpoint_enabled:
            logger.info(f"[Workflow] Saving initial checkpoint...")
            checkpoint_saver = get_checkpoint_saver()
            # Save initial checkpoint
            checkpoint_saver.save_checkpoint(
                thread_id=draft_id,
                checkpoint_data=initial_state,
                node_name="start",
                status="in_progress",
                user_id=user_id,
            )
            logger.info(f"[Workflow] Initial checkpoint saved")

        # Publish initial progress so WebSocket subscribers see movement immediately
        await publish_progress(draft_id, "start", 3, "Starting analysis...")

        # Execute workflow
        logger.info(f"[Workflow] Invoking workflow (this will execute all 8 nodes)...")
        if invoke_config is None:
            final_state = await workflow.ainvoke(initial_state)
        else:
            final_state = await workflow.ainvoke(initial_state, config=invoke_config)
        logger.info(f"[Workflow] Workflow invocation completed!")

        # Publish 98% — workflow done, post-processing (DB writes, scoring) still in progress.
        # The final 100% "complete" event is published by analyze_draft_with_langgraph()
        # AFTER draft.status='analyzed' is written to the DB, so the frontend re-fetch
        # immediately finds the draft ready to open.
        await publish_progress(draft_id, "workflow_complete", 98, "Finalizing analysis...")

        # Save final checkpoint
        if checkpoint_enabled:
            logger.info(f"[Workflow] Saving final checkpoint...")
            checkpoint_saver.save_checkpoint(
                thread_id=draft_id,
                checkpoint_data=final_state,
                node_name="end",
                status="completed",
                user_id=user_id,
            )
            logger.info(f"[Workflow] Final checkpoint saved")
            checkpoint_saver.delete_checkpoints(draft_id)
            logger.info("[Workflow] Completed checkpoints deleted for privacy minimization")

        # Eager deletion of the LangGraph checkpoint rows. The run succeeded, so
        # there is nothing left to resume and no reason to hold derived manuscript
        # text past the moment it stopped being useful. The TTL in migration 039 is
        # only the backstop for runs that never reach this line.
        if lg_checkpointer is not None:
            try:
                await lg_checkpointer.adelete_thread(draft_id)
                logger.info("[Workflow] LangGraph checkpoints deleted for %s", draft_id)
            except Exception as exc:
                logger.warning(
                    "[Workflow] Failed to delete LangGraph checkpoints (TTL will "
                    "reap them): %s",
                    safe_exception(exc),
                )
            finally:
                lg_checkpointer.close()

        logger.info(f"[Workflow] ========== WORKFLOW COMPLETE ==========")
        logger.info(f"[Workflow] Final state keys: {list(final_state.keys())}")

        return final_state

    except Exception as e:
        logger.error(f"[Workflow] ========== WORKFLOW FAILED ==========")
        logger.error(f"[Workflow] Error type: {type(e).__name__}")
        logger.error("[Workflow] Error message: %s", safe_exception(e))

        # Save error checkpoint
        if checkpoint_enabled:
            try:
                logger.info(f"[Workflow] Updating checkpoint status to 'failed'...")
                checkpoint_saver = get_checkpoint_saver()
                checkpoint_saver.update_status(draft_id, "failed")
                logger.info(f"[Workflow] Checkpoint status updated")
            except Exception as checkpoint_error:
                logger.error(f"[Workflow] Failed to update checkpoint: {checkpoint_error}")

        # NOTE: the LangGraph checkpoint rows are deliberately NOT deleted here.
        # They are the whole point of this path -- they are what
        # resume_draft_analysis_workflow() replays from. Only the connection is
        # released.
        if lg_checkpointer is not None:
            logger.info(
                "[Workflow] LangGraph checkpoints retained for thread %s; resume with "
                "resume_draft_analysis_workflow(draft_id, draft_content=...)",
                draft_id,
            )
            lg_checkpointer.close()

        # Re-raise the exception
        raise


async def resume_draft_analysis_workflow(
    draft_id: str,
    draft_content: str,
    *,
    parse_artifact: dict | None = None,
    structure: dict | None = None,
    resume_value: Any = None,
) -> DraftAnalysisState:
    """
    Resume a failed or interrupted draft analysis workflow from its last checkpoint.

    Only the nodes that had not completed are executed. Everything the graph had
    already produced -- claims, citations, gap detection, whichever reviewer
    personas finished -- is replayed from the checkpoint rather than recomputed, so
    a run that died late does not re-pay for the LLM calls that had already
    succeeded.

    Args:
        draft_id: Draft ID, used as the LangGraph ``thread_id``.
        draft_content: The manuscript. **Required, and required for a reason**: it
            is deliberately never written to a checkpoint row (see
            ``MANUSCRIPT_CHANNELS``). The caller re-reads it from Supabase Storage,
            exactly as it does on a fresh run. Passing the wrong text here would
            resume the graph against a different manuscript, so pass what the
            original run was given.
        parse_artifact: Likewise never persisted; re-supply from
            ``draft_parse_artifacts``.
        structure: Likewise never persisted. Re-supply the stored structure. If the
            original run had already run ``extract_structure`` and this is omitted,
            the load raises rather than resuming with an empty structure.
        resume_value: Value to inject when resuming from a dynamic
            ``interrupt()`` -- passed through as ``Command(resume=...)``. Leave as
            ``None`` for a plain crash-resume.

    Returns:
        Final workflow state.

    Raises:
        RuntimeError: If checkpointing is disabled, no checkpoint exists, the row
            fails its integrity check, or a scrubbed manuscript channel was not
            re-supplied. None of these fall back to a silent restart -- a resume
            that cannot be done correctly must be an explicit restart by the
            caller, not a surprise full-price rerun.
    """
    logger.info(f"[Workflow] Resuming draft analysis for draft_id={draft_id}")

    lg_checkpointer = build_checkpointer(
        rehydrate={
            "draft_content": draft_content,
            "parse_artifact": parse_artifact or {},
            "structure": structure or {},
        },
    )
    if lg_checkpointer is None:
        raise RuntimeError(
            "Cannot resume: checkpointing is disabled. Set NOESIS_CHECKPOINT_ENABLED "
            "and NOESIS_CHECKPOINT_DB_URL, or restart the analysis from the draft file."
        )

    config = {"configurable": {"thread_id": draft_id}}

    try:
        existing = await lg_checkpointer.aget_tuple(config)
        if existing is None:
            raise RuntimeError(f"No LangGraph checkpoint found for draft_id={draft_id}")

        logger.info(
            "[Workflow] Resuming thread %s from checkpoint %s (progress=%s%%)",
            draft_id,
            existing.checkpoint.get("id"),
            (existing.checkpoint.get("channel_values") or {}).get(
                "progress_percentage", 0
            ),
        )

        workflow = create_draft_analysis_workflow(checkpointer=lg_checkpointer)

        # ``None`` as the input is what tells LangGraph "continue this thread from
        # its checkpoint" rather than "start a new run with this state" -- the
        # latter is what the old implementation did, which is why it re-ran
        # everything. ``Command(resume=...)`` is the equivalent for a thread parked
        # on a dynamic interrupt.
        graph_input = Command(resume=resume_value) if resume_value is not None else None

        # Same RUN span as a fresh run, so a resumed run is one tree rather than
        # one orphaned root per node.
        with start_span(
            "draft_analysis_run",
            kind=SpanKind.RUN,
            attributes=run_attributes(analysis_run_id=draft_id, draft_id=draft_id),
        ):
            final_state = await workflow.ainvoke(graph_input, config=config)

        await lg_checkpointer.adelete_thread(draft_id)
        logger.info(f"[Workflow] Successfully resumed and completed draft_id={draft_id}")

        return final_state

    except Exception as e:
        logger.error("[Workflow] Error resuming draft_id=%s: %s", draft_id, safe_exception(e))
        raise
    finally:
        lg_checkpointer.close()


# ============================================
# HELPER FUNCTIONS
# ============================================

def get_workflow_progress(draft_id: str) -> dict:
    """
    Get the current progress of a draft analysis workflow.

    Args:
        draft_id: Draft ID to check

    Returns:
        Progress information including current step and percentage
    """
    checkpoint_saver = get_checkpoint_saver()
    checkpoint = checkpoint_saver.load_checkpoint(draft_id)

    if not checkpoint:
        return {
            "status": "not_started",
            "progress_percentage": 0,
            "current_step": "Not Started"
        }

    state = checkpoint["state"]

    return {
        "status": checkpoint["status"],
        "progress_percentage": state.get("progress_percentage", 0),
        "current_step": state.get("current_step", "Unknown"),
        "node_name": checkpoint["node_name"],
        "last_updated": checkpoint["created_at"],
        "errors": state.get("errors", []),
        "warnings": state.get("warnings", [])
    }

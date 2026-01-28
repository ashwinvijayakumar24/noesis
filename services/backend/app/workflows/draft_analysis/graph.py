"""
Draft Analysis Workflow Graph

LangGraph workflow that orchestrates the complete draft analysis process.
"""

from langgraph.graph import StateGraph, END
from app.workflows.draft_analysis.state import DraftAnalysisState
from app.workflows.draft_analysis.checkpoints import get_checkpoint_saver
from app.core.logging_config import get_logger

# Import all workflow nodes
from app.workflows.draft_analysis.nodes.structure_extraction import extract_structure_node
from app.workflows.draft_analysis.nodes.claim_extraction import extract_claims_node
from app.workflows.draft_analysis.nodes.claim_categorization import categorize_claims_node
from app.workflows.draft_analysis.nodes.literature_search import literature_search_node
from app.workflows.draft_analysis.nodes.citation_mapping import citation_mapping_node
from app.workflows.draft_analysis.nodes.gap_detection import detect_gaps_node
from app.workflows.draft_analysis.nodes.reviewer_feedback import generate_reviewer_feedback_node
from app.workflows.draft_analysis.nodes.report_synthesis import synthesize_report_node

logger = get_logger(__name__)


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
# WORKFLOW GRAPH CONSTRUCTION
# ============================================

def create_draft_analysis_workflow() -> StateGraph:
    """
    Create the complete draft analysis workflow graph.

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

    workflow.add_node("extract_structure", extract_structure_node)
    workflow.add_node("extract_claims", extract_claims_node)
    workflow.add_node("categorize_claims", categorize_claims_node)
    workflow.add_node("search_literature", literature_search_node)
    workflow.add_node("map_citations", citation_mapping_node)
    workflow.add_node("detect_gaps", detect_gaps_node)
    workflow.add_node("generate_feedback", generate_reviewer_feedback_node)
    workflow.add_node("synthesize_report", synthesize_report_node)

    # ============================================
    # ADD EDGES
    # ============================================

    # Set entry point
    workflow.set_entry_point("extract_structure")

    # Linear flow for most steps
    workflow.add_edge("extract_structure", "extract_claims")

    # Conditional routing after claim extraction
    workflow.add_conditional_edges(
        "extract_claims",
        route_after_claim_extraction,
        {
            "categorize_claims": "categorize_claims",
            # Future: "validate_claims": "validate_claims"
        }
    )

    # Continue with categorization → literature search
    workflow.add_edge("categorize_claims", "search_literature")

    # Conditional routing after literature search
    workflow.add_conditional_edges(
        "search_literature",
        route_after_literature_search,
        {
            "map_citations": "map_citations",
            # Future: "refine_search": "refine_search"
        }
    )

    # Continue with citation mapping → gap detection → feedback → synthesis
    workflow.add_edge("map_citations", "detect_gaps")
    workflow.add_edge("detect_gaps", "generate_feedback")
    workflow.add_edge("generate_feedback", "synthesize_report")

    # End after synthesis
    workflow.add_edge("synthesize_report", END)

    # Compile the graph
    compiled_workflow = workflow.compile()

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
    checkpoint_enabled: bool = True
) -> DraftAnalysisState:
    """
    Run the complete draft analysis workflow.

    Args:
        draft_id: Unique identifier for the draft
        project_id: Project the draft belongs to
        user_id: User who owns the draft
        draft_content: Full text content of the draft
        checkpoint_enabled: Whether to save checkpoints (for resume capability)

    Returns:
        Final workflow state with complete analysis
    """
    logger.info(f"[Workflow] ========== WORKFLOW START ==========")
    logger.info(f"[Workflow] draft_id={draft_id}")
    logger.info(f"[Workflow] project_id={project_id}")
    logger.info(f"[Workflow] user_id={user_id}")
    logger.info(f"[Workflow] draft_content length={len(draft_content)} chars")

    # Create the workflow
    logger.info(f"[Workflow] Creating workflow graph...")
    try:
        workflow = create_draft_analysis_workflow()
        logger.info(f"[Workflow] Workflow graph created successfully")
    except Exception as e:
        logger.error(f"[Workflow] FATAL: Failed to create workflow graph: {type(e).__name__}: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise

    # Initialize state
    logger.info(f"[Workflow] Initializing state...")
    initial_state: DraftAnalysisState = {
        "draft_id": draft_id,
        "project_id": project_id,
        "user_id": user_id,
        "draft_content": draft_content,
        "current_step": "Starting",
        "progress_percentage": 0,
        "search_iterations": 0,
        "max_search_iterations": 1  # Can be increased for iterative refinement
    }
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
                status="in_progress"
            )
            logger.info(f"[Workflow] Initial checkpoint saved")

        # Execute workflow
        logger.info(f"[Workflow] Invoking workflow (this will execute all 8 nodes)...")
        final_state = await workflow.ainvoke(initial_state)
        logger.info(f"[Workflow] Workflow invocation completed!")

        # Save final checkpoint
        if checkpoint_enabled:
            logger.info(f"[Workflow] Saving final checkpoint...")
            checkpoint_saver.save_checkpoint(
                thread_id=draft_id,
                checkpoint_data=final_state,
                node_name="end",
                status="completed"
            )
            logger.info(f"[Workflow] Final checkpoint saved")

        logger.info(f"[Workflow] ========== WORKFLOW COMPLETE ==========")
        logger.info(f"[Workflow] Final state keys: {list(final_state.keys())}")

        return final_state

    except Exception as e:
        logger.error(f"[Workflow] ========== WORKFLOW FAILED ==========")
        logger.error(f"[Workflow] Error type: {type(e).__name__}")
        logger.error(f"[Workflow] Error message: {str(e)}")
        import traceback
        logger.error(f"[Workflow] Full traceback:")
        logger.error(traceback.format_exc())

        # Save error checkpoint
        if checkpoint_enabled:
            try:
                logger.info(f"[Workflow] Updating checkpoint status to 'failed'...")
                checkpoint_saver = get_checkpoint_saver()
                checkpoint_saver.update_status(draft_id, "failed")
                logger.info(f"[Workflow] Checkpoint status updated")
            except Exception as checkpoint_error:
                logger.error(f"[Workflow] Failed to update checkpoint: {checkpoint_error}")

        # Re-raise the exception
        raise


async def resume_draft_analysis_workflow(draft_id: str) -> DraftAnalysisState:
    """
    Resume a failed or interrupted draft analysis workflow.

    Args:
        draft_id: Draft ID to resume

    Returns:
        Final workflow state

    Raises:
        Exception: If no checkpoint found or resume fails
    """
    logger.info(f"[Workflow] Resuming draft analysis for draft_id={draft_id}")

    # Load checkpoint
    checkpoint_saver = get_checkpoint_saver()
    checkpoint = checkpoint_saver.load_checkpoint(draft_id)

    if not checkpoint:
        raise Exception(f"No checkpoint found for draft_id={draft_id}")

    # Get the saved state
    saved_state = checkpoint["state"]

    logger.info(
        f"[Workflow] Resuming from checkpoint: "
        f"node={checkpoint['node_name']}, "
        f"progress={saved_state.get('progress_percentage', 0)}%"
    )

    # Create workflow and continue from saved state
    workflow = create_draft_analysis_workflow()

    try:
        # Resume execution
        # Note: LangGraph can continue from where it left off
        final_state = await workflow.ainvoke(saved_state)

        # Update checkpoint status
        checkpoint_saver.update_status(draft_id, "completed")

        logger.info(f"[Workflow] Successfully resumed and completed draft_id={draft_id}")

        return final_state

    except Exception as e:
        logger.error(f"[Workflow] Error resuming draft_id={draft_id}: {e}")
        checkpoint_saver.update_status(draft_id, "failed")
        raise


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

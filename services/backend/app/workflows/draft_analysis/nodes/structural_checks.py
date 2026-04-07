"""
Structural Checks Node

LangGraph node that runs targeted structural quality checks on the draft text,
detecting issues like abstract-body mismatches, causal overclaims, and missing SOTA.

Generates feedback items with feedback_type='structural' that are stored in
the reviewer_feedback table alongside standard feedback.
"""

import asyncio
from app.workflows.draft_analysis.state import DraftAnalysisState
from app.services.structural_review import run_structural_checks
from app.core.logging_config import get_logger

logger = get_logger(__name__)


async def structural_checks_node(state: DraftAnalysisState) -> DraftAnalysisState:
    """
    Run structural checks on the draft and produce structural feedback items.

    Runs between gap_detection and reviewer_feedback in the workflow graph.
    Results are stored in state['structural_feedback'] and later merged into
    the reviewer_feedback table in draft_analysis_langgraph.py.

    Args:
        state: Current workflow state (requires draft_content)

    Returns:
        State update with structural_feedback list
    """
    logger.info(f"[Structural Checks] Starting for draft_id={state['draft_id']}")

    draft_content = state.get("draft_content", "")

    if not draft_content:
        logger.warning("[Structural Checks] No draft content available — skipping")
        return {
            "structural_feedback": [],
            "current_step": "Structural Checks (Skipped)",
            "progress_percentage": 77,
        }

    try:
        checks = await run_structural_checks(draft_content)

        # Convert raw checks to Feedback-compatible dicts
        structural_items = []
        for check in checks:
            structural_items.append({
                "feedback_type": "structural",
                "feedback_text": check.get("feedback_text", ""),
                "severity": check.get("severity", "major"),
                "section_reference": check.get("section_reference", ""),
                "specific_issue": check.get("specific_issue", ""),
                "suggested_improvements": check.get("suggested_improvements", []),
                "check_type": check.get("check_type", ""),
            })

        logger.info(
            f"[Structural Checks] Generated {len(structural_items)} structural feedback items "
            f"for draft_id={state['draft_id']}"
        )

        return {
            "structural_feedback": structural_items,
            "current_step": "Structural Checks",
            "progress_percentage": 77,
        }

    except Exception as e:
        logger.error(f"[Structural Checks] Error: {e}")
        errors = list(state.get("errors") or [])
        errors.append(f"Structural checks failed: {str(e)}")
        return {
            "structural_feedback": [],
            "errors": errors,
            "current_step": "Structural Checks (Failed)",
            "progress_percentage": 77,
        }

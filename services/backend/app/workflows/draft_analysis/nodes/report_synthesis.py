"""
Report Synthesis Node

Synthesizes all analysis into a coherent final report.
"""

from app.workflows.draft_analysis.state import DraftAnalysisState
from app.core.logging_config import get_logger
from typing import Dict, Any
import datetime

logger = get_logger(__name__)


def synthesize_report_node(state: DraftAnalysisState) -> DraftAnalysisState:
    """
    Synthesize all analysis results into a final comprehensive report.

    The report includes:
    1. Executive summary of strengths/weaknesses
    2. Detailed feedback by section
    3. Prioritized action items
    4. Coverage gaps with severity
    5. Citation quality assessment
    6. Recommended papers to add

    Args:
        state: Current workflow state

    Returns:
        Updated state with final synthesis report
    """
    logger.info(f"[Report Synthesis] Starting for draft_id={state['draft_id']}")

    try:
        # Gather all analysis results
        structure = state.get("structure", {})
        claims = state.get("claims", [])
        claims_with_citations = state.get("claims_with_citations", [])
        gaps = state.get("coverage_gaps", [])
        feedback = state.get("reviewer_feedback", [])
        overall_assessment = state.get("overall_assessment", "")
        priority_actions = state.get("priority_actions", [])

        # Build comprehensive report
        synthesis_report: Dict[str, Any] = {
            # Executive summary
            "executive_summary": {
                "overall_assessment": overall_assessment,
                "total_claims": len(claims),
                "primary_claims": len(state.get("primary_claims", [])),
                "total_gaps": len(gaps),
                "critical_gaps": len([g for g in gaps if g['severity'] == 'critical']),
                "major_gaps": len([g for g in gaps if g['severity'] == 'major']),
                "word_count": structure.get("word_count", 0),
                "page_count": structure.get("page_count", 0),
                "analysis_timestamp": datetime.datetime.utcnow().isoformat()
            },

            # Citation quality summary
            "citation_quality": {
                "strong_support": sum(1 for c in claims_with_citations if c.get('citation_quality') == 'strong'),
                "moderate_support": sum(1 for c in claims_with_citations if c.get('citation_quality') == 'moderate'),
                "weak_support": sum(1 for c in claims_with_citations if c.get('citation_quality') == 'weak'),
                "no_support": sum(1 for c in claims_with_citations if c.get('citation_quality') == 'none'),
                "percentage_well_supported": round(
                    (sum(1 for c in claims_with_citations if c.get('citation_quality') in ['strong', 'moderate']) /
                     max(len(claims_with_citations), 1)) * 100, 1
                )
            },

            # Prioritized action items
            "priority_actions": priority_actions,

            # Detailed feedback by category
            "feedback_by_category": {
                "strengths": [f for f in feedback if f['feedback_type'] == 'strength'],
                "weaknesses": [f for f in feedback if f['feedback_type'] == 'weakness'],
                "questions": [f for f in feedback if f['feedback_type'] == 'question'],
                "suggestions": [f for f in feedback if f['feedback_type'] == 'suggestion']
            },

            # Coverage gaps by severity
            "coverage_gaps_by_severity": {
                "critical": [g for g in gaps if g['severity'] == 'critical'],
                "major": [g for g in gaps if g['severity'] == 'major'],
                "minor": [g for g in gaps if g['severity'] == 'minor']
            },

            # Claims analysis
            "claims_analysis": {
                "by_type": {
                    "empirical": len([c for c in claims if c['claim_type'] == 'empirical']),
                    "theoretical": len([c for c in claims if c['claim_type'] == 'theoretical']),
                    "methodological": len([c for c in claims if c['claim_type'] == 'methodological'])
                },
                "unsupported_claims": [
                    c['claim'] for c in claims_with_citations
                    if c.get('citation_quality') == 'none'
                ],
                "weakly_supported_claims": [
                    c['claim'] for c in claims_with_citations
                    if c.get('citation_quality') == 'weak'
                ]
            },

            # Document structure assessment
            "structure_assessment": {
                "has_key_sections": {
                    "abstract": structure.get("has_abstract", False),
                    "introduction": structure.get("has_introduction", False),
                    "methods": structure.get("has_methods", False),
                    "results": structure.get("has_results", False),
                    "discussion": structure.get("has_discussion", False),
                    "conclusion": structure.get("has_conclusion", False)
                },
                "missing_sections": [
                    section for section in ["abstract", "introduction", "methods", "results", "discussion", "conclusion"]
                    if not structure.get(f"has_{section}", False)
                ],
                "total_sections": len(structure.get("sections", []))
            },

            # Workflow metadata
            "analysis_metadata": {
                "workflow_version": "langgraph_v1",
                "total_steps_completed": 8,
                "errors_encountered": len(state.get("errors", [])),
                "warnings_encountered": len(state.get("warnings", [])),
                "completion_timestamp": datetime.datetime.utcnow().isoformat()
            }
        }

        logger.info(
            f"[Report Synthesis] Generated comprehensive report: "
            f"{len(claims)} claims, {len(gaps)} gaps, {len(feedback)} feedback items"
        )

        return {
            'synthesis_report': synthesis_report,
            'current_step': 'Report Synthesis (Complete)',
            'progress_percentage': 100
        }

    except Exception as e:
        logger.error(f"[Report Synthesis] Error: {e}")
        errors = state.get('errors', [])
        errors.append(f"Report synthesis failed: {str(e)}")

        return {
            'errors': errors,
            'current_step': 'Report Synthesis (Failed)',
            'progress_percentage': 100
        }

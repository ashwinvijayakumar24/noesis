"""
Synthesis Node

Combines all extracted information into a comprehensive analysis report.

This node synthesizes:
- Structure, claims, methods, findings into a coherent report
- Creates legacy-compatible analysis object for frontend
- Prepares data for database storage
"""

from app.workflows.document_analysis.state import DocumentAnalysisState
from app.core.logging_config import get_logger
from typing import Dict, Any
import datetime

logger = get_logger(__name__)


def synthesize_analysis_node(state: DocumentAnalysisState) -> DocumentAnalysisState:
    """
    Synthesize all extracted data into final analysis report.

    This creates a structured analysis report compatible with the frontend's
    expectations while preserving the rich structured data extracted by LangGraph.

    Args:
        state: Current workflow state

    Returns:
        Updated state with final analysis report
    """
    logger.info(f"[DOC-SYNTHESIS] Starting synthesis for document_id={state['document_id']}")

    try:
        structure = state.get("structure", {})
        claims = state.get("claims", [])
        primary_claims = state.get("primary_claims", [])
        methods = state.get("methods", [])
        findings = state.get("findings", [])
        findings_with_metrics = state.get("findings_with_metrics", [])

        # Build executive summary from primary claims and key findings
        primary_claim_texts = [c["claim_text"] for c in primary_claims[:5]]  # Top 5 primary claims
        executive_summary = "\n\n".join(primary_claim_texts) if primary_claim_texts else "Analysis complete - see detailed claims below."

        # Extract research problem (from introduction claims if available)
        intro_claims = [c for c in claims if c.get("section_type") == "introduction"]
        research_problem = intro_claims[0]["claim_text"] if intro_claims else structure.get("abstract", "")[:500]

        # Key questions (extract from theoretical and methodological claims)
        theoretical_claims = state.get("claims_by_type", {}).get("theoretical", [])
        key_questions = [c["claim_text"] for c in theoretical_claims[:5]]

        # Methodology summary
        methodology = {
            "approach": f"{len(methods)} methods identified",
            "techniques": [m["method_name"] for m in methods[:10]],
            "dataset": ", ".join(set(
                dataset
                for m in methods
                for dataset in m.get("datasets_used", [])
            ))[:200] if methods else "Not specified"
        }

        # Key findings from extracted findings
        key_findings = [f["finding_text"] for f in findings[:10]]

        # Results summary with metrics
        results = {
            "summary": f"{len(findings)} findings extracted, {len(findings_with_metrics)} with quantitative metrics",
            "metrics": [
                f"{f.get('finding_text', '')}: {f.get('metrics', {})}"
                for f in findings_with_metrics[:5]
            ]
        }

        # Limitations
        limitation_findings = [f for f in findings if f.get("finding_type") == "limitation"]
        limitations = [f["finding_text"] for f in limitation_findings[:5]]

        # Future work (can be extracted from discussion/conclusion claims)
        discussion_claims = [c for c in claims if c.get("section_type") == "discussion"]
        future_work = [c["claim_text"] for c in discussion_claims[-3:]] if discussion_claims else []

        # Key citations (top methods/baselines mentioned)
        key_citations = []
        for finding in findings_with_metrics[:5]:
            if finding.get("comparison_baseline"):
                key_citations.append({
                    "title": finding.get("comparison_baseline"),
                    "relevance": finding.get("finding_text", "")[:100]
                })

        # Build legacy-compatible analysis report
        analysis_report: Dict[str, Any] = {
            # Standard fields expected by frontend
            "executive_summary": executive_summary,
            "research_problem": research_problem,
            "key_questions": key_questions,
            "methodology": methodology,
            "key_findings": key_findings,
            "results": results,
            "limitations": limitations,
            "future_work": future_work,
            "key_citations": key_citations,

            # LangGraph-specific metadata
            "analysis_metadata": {
                "version": "v2_langgraph",
                "workflow_version": "1.0",
                "claims_extracted": len(claims),
                "methods_extracted": len(methods),
                "findings_extracted": len(findings),
                "primary_claims": len(primary_claims),
                "findings_with_metrics": len(findings_with_metrics),
                "timestamp": datetime.datetime.utcnow().isoformat()
            },

            # Rich structured data (available for future use)
            "structured_data": {
                "total_claims": len(claims),
                "claims_by_type": dict((k, len(v)) for k, v in state.get("claims_by_type", {}).items()),
                "total_methods": len(methods),
                "methods_by_type": dict((k, len(v)) for k, v in state.get("methods_by_type", {}).items()),
                "total_findings": len(findings),
                "unique_datasets": len(set(
                    dataset
                    for m in methods
                    for dataset in m.get("datasets_used", [])
                )),
                "unique_metrics": len(set(
                    metric
                    for m in methods
                    for metric in m.get("evaluation_metrics", [])
                ))
            }
        }

        logger.info(
            f"[DOC-SYNTHESIS] Synthesis complete: {len(claims)} claims, "
            f"{len(methods)} methods, {len(findings)} findings"
        )
        logger.info(f"[DOC-SYNTHESIS] Report sections: {list(analysis_report.keys())}")

        return {
            **state,
            "analysis_report": analysis_report,
            "current_step": "Synthesis (Complete)",
            "progress_percentage": 100
        }

    except Exception as e:
        logger.error(f"[DOC-SYNTHESIS] Error during synthesis: {e}")
        errors = state.get("errors", [])
        errors.append(f"Synthesis failed: {str(e)}")

        # Return minimal valid analysis report even on error
        minimal_analysis_report = {
            "executive_summary": "Analysis completed with errors. See structured data below.",
            "research_problem": "",
            "key_questions": [],
            "methodology": {
                "approach": "Analysis incomplete",
                "techniques": [],
                "dataset": ""
            },
            "key_findings": [],
            "results": {
                "summary": "Analysis incomplete",
                "metrics": []
            },
            "limitations": [],
            "future_work": [],
            "key_citations": [],
            "analysis_metadata": {
                "version": "v2_langgraph",
                "workflow_version": "1.0",
                "status": "completed_with_errors",
                "errors": errors,
                "timestamp": datetime.datetime.utcnow().isoformat()
            }
        }

        return {
            **state,
            "analysis_report": minimal_analysis_report,
            "errors": errors,
            "current_step": "Synthesis (Failed)",
            "progress_percentage": 100
        }

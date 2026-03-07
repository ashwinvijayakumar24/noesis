"""
Transparency and Traceability Service

Ensures all analysis results include transparent metadata about:
- How conclusions were reached
- Which sources were used
- What AI models were involved
- Confidence levels and reasoning

This builds trust by making the analysis process visible and traceable.

Requirements: 7.1, 7.2, 7.3
"""

import datetime
from typing import Dict, Any, List, Optional
from app.core.logging_config import get_logger

logger = get_logger(__name__)


# ============================================
# Transparency Metadata Generation
# ============================================

def add_transparency_metadata(
    analysis_result: Dict[str, Any],
    analysis_type: str,
    model_used: str,
    input_sources: List[Dict[str, Any]],
    reasoning: Optional[str] = None
) -> Dict[str, Any]:
    """
    Add transparency metadata to any analysis result.

    Enriches analysis results with information about how the analysis
    was performed, making the process transparent and traceable.

    Args:
        analysis_result: The analysis result to enrich
        analysis_type: Type of analysis (e.g., "claim_extraction", "coverage_analysis")
        model_used: AI model used for analysis (e.g., "gpt-5.2-chat-latest")
        input_sources: List of sources used in analysis
        reasoning: Optional explanation of analysis approach

    Returns:
        Analysis result with transparency metadata

    Validates: Requirement 7.1 - Transparent analysis metadata
    """
    transparency = {
        "analysis_type": analysis_type,
        "model_used": model_used,
        "analyzed_at": datetime.datetime.utcnow().isoformat(),
        "input_sources": input_sources,
        "num_sources": len(input_sources)
    }

    if reasoning:
        transparency["reasoning"] = reasoning

    # Add version information for reproducibility
    transparency["metadata_version"] = "1.0"

    # Add to result
    enriched_result = {
        **analysis_result,
        "_transparency": transparency
    }

    logger.info(f"Added transparency metadata for {analysis_type}")

    return enriched_result


def create_source_reference(
    source_id: str,
    source_type: str,
    source_title: str,
    excerpt: Optional[str] = None,
    page_number: Optional[int] = None,
    section: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a standardized source reference for traceability.

    Args:
        source_id: UUID of source (document_id or draft_id)
        source_type: Type of source ("literature", "draft", "claim", "gap")
        source_title: Human-readable source title
        excerpt: Optional text excerpt from source
        page_number: Optional page number
        section: Optional section name

    Returns:
        Standardized source reference

    Validates: Requirement 7.2 - Source traceability
    """
    reference = {
        "source_id": source_id,
        "source_type": source_type,
        "source_title": source_title,
        "reference_created_at": datetime.datetime.utcnow().isoformat()
    }

    if excerpt:
        reference["excerpt"] = excerpt[:500]  # Limit excerpt length

    if page_number:
        reference["page_number"] = page_number

    if section:
        reference["section"] = section

    return reference


# ============================================
# Feedback Traceability
# ============================================

def link_feedback_to_evidence(
    feedback: Dict[str, Any],
    evidence_sources: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Link feedback to specific evidence sources.

    Makes feedback traceable by explicitly connecting it to the
    evidence that supports the feedback.

    Args:
        feedback: Feedback item
        evidence_sources: List of evidence sources

    Returns:
        Feedback with evidence links

    Validates: Requirement 7.2 - Feedback traceability
    """
    traceable_feedback = {
        **feedback,
        "evidence": {
            "sources": evidence_sources,
            "num_sources": len(evidence_sources),
            "traced_at": datetime.datetime.utcnow().isoformat()
        }
    }

    logger.info(f"Linked feedback to {len(evidence_sources)} evidence sources")

    return traceable_feedback


def create_analysis_trail(
    analysis_steps: List[Dict[str, Any]],
    final_result: Any,
    confidence: Optional[float] = None
) -> Dict[str, Any]:
    """
    Create a complete analysis trail showing step-by-step reasoning.

    Provides full transparency into multi-step analysis processes.

    Args:
        analysis_steps: List of analysis steps performed
        final_result: Final analysis result
        confidence: Optional confidence score (0.0 to 1.0)

    Returns:
        Analysis trail with all steps documented

    Validates: Requirement 7.3 - Analysis process transparency
    """
    trail = {
        "steps": analysis_steps,
        "num_steps": len(analysis_steps),
        "final_result": final_result,
        "trail_created_at": datetime.datetime.utcnow().isoformat()
    }

    if confidence is not None:
        trail["confidence"] = confidence
        trail["confidence_level"] = categorize_confidence(confidence)

    return trail


def categorize_confidence(confidence: float) -> str:
    """
    Categorize confidence score into human-readable level.

    Args:
        confidence: Confidence score (0.0 to 1.0)

    Returns:
        Confidence level: "high", "medium", "low", "very_low"
    """
    if confidence >= 0.8:
        return "high"
    elif confidence >= 0.6:
        return "medium"
    elif confidence >= 0.4:
        return "low"
    else:
        return "very_low"


# ============================================
# Claim-to-Evidence Linking
# ============================================

def link_claim_to_citations(
    claim: Dict[str, Any],
    citations: List[Dict[str, Any]],
    draft_id: str
) -> Dict[str, Any]:
    """
    Create explicit link between claim and supporting citations.

    Args:
        claim: Claim dictionary
        citations: List of citations supporting claim
        draft_id: Draft identifier

    Returns:
        Claim with citation links

    Validates: Requirement 7.2 - Claim-citation traceability
    """
    # Create citation references
    citation_references = []
    for citation in citations:
        ref = {
            "citation_string": citation.get("citation_string"),
            "authors": citation.get("authors", []),
            "year": citation.get("year"),
            "context": citation.get("context", "")[:200],  # First 200 chars of context
            "found_in_draft": True
        }
        citation_references.append(ref)

    claim_with_links = {
        **claim,
        "citation_links": {
            "citations": citation_references,
            "num_citations": len(citation_references),
            "draft_id": draft_id,
            "linked_at": datetime.datetime.utcnow().isoformat()
        }
    }

    return claim_with_links


def link_gap_to_suggestions(
    gap: Dict[str, Any],
    suggested_papers: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Link coverage gap to suggested papers from literature database.

    Args:
        gap: Coverage gap dictionary
        suggested_papers: List of suggested papers to address gap

    Returns:
        Gap with paper suggestions linked

    Validates: Requirement 7.2 - Gap-suggestion traceability
    """
    # Create paper references
    paper_references = []
    for paper in suggested_papers:
        ref = {
            "document_id": paper.get("document_id"),
            "title": paper.get("title"),
            "authors": paper.get("authors", []),
            "year": paper.get("year"),
            "relevance_score": paper.get("relevance_score"),
            "executive_summary": paper.get("executive_summary", "")[:300]
        }
        paper_references.append(ref)

    gap_with_links = {
        **gap,
        "suggestion_links": {
            "suggested_papers": paper_references,
            "num_suggestions": len(paper_references),
            "linked_at": datetime.datetime.utcnow().isoformat()
        }
    }

    return gap_with_links


# ============================================
# Analysis Explanation Generation
# ============================================

def generate_analysis_explanation(
    analysis_type: str,
    inputs: Dict[str, Any],
    outputs: Dict[str, Any],
    method: str
) -> Dict[str, Any]:
    """
    Generate human-readable explanation of how analysis was performed.

    Args:
        analysis_type: Type of analysis performed
        inputs: Input data used
        outputs: Output results produced
        method: Method or approach used

    Returns:
        Analysis explanation

    Validates: Requirement 7.3 - Explainable analysis
    """
    explanation = {
        "what_was_analyzed": describe_inputs(analysis_type, inputs),
        "how_it_was_analyzed": method,
        "what_was_found": describe_outputs(analysis_type, outputs),
        "explained_at": datetime.datetime.utcnow().isoformat()
    }

    return explanation


def describe_inputs(analysis_type: str, inputs: Dict[str, Any]) -> str:
    """
    Generate human-readable description of analysis inputs.

    Args:
        analysis_type: Type of analysis
        inputs: Input data

    Returns:
        Input description
    """
    if analysis_type == "claim_extraction":
        return f"Analyzed draft text ({inputs.get('text_length', 0)} characters) to extract factual claims"

    elif analysis_type == "coverage_analysis":
        return f"Analyzed draft against {inputs.get('num_literature_docs', 0)} literature documents to identify gaps"

    elif analysis_type == "citation_quality":
        return f"Assessed citation quality for {inputs.get('num_claims', 0)} claims"

    elif analysis_type == "reviewer_feedback":
        return f"Generated reviewer-style feedback for draft with {inputs.get('num_sections', 0)} sections"

    else:
        return f"Performed {analysis_type} analysis on provided inputs"


def describe_outputs(analysis_type: str, outputs: Dict[str, Any]) -> str:
    """
    Generate human-readable description of analysis outputs.

    Args:
        analysis_type: Type of analysis
        outputs: Output data

    Returns:
        Output description
    """
    if analysis_type == "claim_extraction":
        return f"Identified {outputs.get('total_claims', 0)} claims across {outputs.get('num_sections', 0)} sections"

    elif analysis_type == "coverage_analysis":
        total_gaps = outputs.get('total_gaps', 0)
        high_priority = outputs.get('high_priority_gaps', 0)
        return f"Found {total_gaps} coverage gaps ({high_priority} high priority)"

    elif analysis_type == "citation_quality":
        avg_quality = outputs.get('average_quality_score', 0)
        return f"Average citation quality: {avg_quality:.2f}/1.0"

    elif analysis_type == "reviewer_feedback":
        total_items = outputs.get('total_feedback_items', 0)
        critical = outputs.get('critical_items', 0)
        return f"Generated {total_items} feedback items ({critical} critical)"

    else:
        return f"Produced analysis results for {analysis_type}"


# ============================================
# Transparency Report Generation
# ============================================

def generate_transparency_report(
    draft_id: str,
    all_analyses: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Generate comprehensive transparency report for all draft analyses.

    Consolidates transparency information from all analysis types
    into a single, user-friendly report.

    Args:
        draft_id: Draft identifier
        all_analyses: Dictionary of all analyses performed

    Returns:
        Transparency report

    Validates: Requirements 7.1, 7.2, 7.3 - Complete transparency
    """
    report = {
        "draft_id": draft_id,
        "report_generated_at": datetime.datetime.utcnow().isoformat(),
        "analyses_performed": []
    }

    # Extract transparency metadata from each analysis
    for analysis_type, analysis_result in all_analyses.items():
        if "_transparency" in analysis_result:
            transparency = analysis_result["_transparency"]

            analysis_summary = {
                "analysis_type": analysis_type,
                "model_used": transparency.get("model_used"),
                "analyzed_at": transparency.get("analyzed_at"),
                "num_sources": transparency.get("num_sources", 0),
                "reasoning": transparency.get("reasoning", "Standard analysis procedure")
            }

            report["analyses_performed"].append(analysis_summary)

    report["total_analyses"] = len(report["analyses_performed"])

    return report


def add_user_facing_explanation(
    result: Dict[str, Any],
    explanation: str
) -> Dict[str, Any]:
    """
    Add user-facing explanation to analysis result.

    Provides a plain-language explanation that users can understand
    without technical knowledge.

    Args:
        result: Analysis result
        explanation: User-friendly explanation

    Returns:
        Result with explanation

    Validates: Requirement 7.3 - User-understandable explanations
    """
    result_with_explanation = {
        **result,
        "explanation": {
            "summary": explanation,
            "added_at": datetime.datetime.utcnow().isoformat()
        }
    }

    return result_with_explanation

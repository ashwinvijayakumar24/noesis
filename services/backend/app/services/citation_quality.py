"""
Citation Quality Assessment and Pattern Detection

Enhances claim analysis with:
- Citation quality and relevance assessment
- Detection of over-reliance on single sources
- Suggestion of stronger alternatives from literature database
- Pattern analysis for citation distribution

Requirements: 3.2, 3.3, 3.4, 3.5
"""

import json
from typing import Dict, Any, List, Optional, Tuple
from openai import OpenAI
from app.core.config import settings
from app.core.supabase_client import supabase
from app.core.logging_config import get_logger
from collections import Counter
import re

logger = get_logger(__name__)

# Initialize OpenAI client
client = OpenAI(api_key=settings.OPENAI_API_KEY) if settings.OPENAI_API_KEY else None


# ============================================
# Citation Quality Assessment
# ============================================

def assess_citation_quality(
    claim: Dict[str, Any],
    citations: List[Dict[str, Any]],
    literature_database: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Assess the quality and relevance of citations supporting a claim.

    Evaluates:
    - Number of citations
    - Recency of citations
    - Diversity of sources
    - Alignment with claim type

    Args:
        claim: Claim dictionary with metadata
        citations: List of citations supporting this claim
        literature_database: Optional list of available literature for comparison

    Returns:
        Quality assessment dictionary

    Validates: Requirement 3.3 - Assess citation strength and relevance
    """
    assessment = {
        "num_citations": len(citations),
        "quality_score": 0.0,
        "issues": [],
        "recommendations": []
    }

    # No citations check
    if len(citations) == 0:
        if claim.get("requires_citation", True):
            assessment["quality_score"] = 0.0
            assessment["issues"].append("No citations provided for claim requiring support")
            assessment["recommendations"].append("Add citations from relevant literature")
        else:
            assessment["quality_score"] = 1.0  # Original contribution, no citations needed
        return assessment

    # Analyze citation recency
    years = []
    for citation in citations:
        year_str = citation.get("year", "")
        if year_str and year_str.isdigit():
            years.append(int(year_str))

    if years:
        most_recent = max(years)
        oldest = min(years)
        avg_age = 2024 - sum(years) / len(years)  # Approximate

        # Penalize if all citations are old (>10 years)
        if avg_age > 10:
            assessment["issues"].append(f"Citations are dated (average {avg_age:.0f} years old)")
            assessment["recommendations"].append("Consider adding more recent literature")

        # Bonus for recent citations
        if most_recent >= 2020:
            assessment["quality_score"] += 0.2

    # Analyze source diversity
    authors = [c.get("authors", ["Unknown"])[0] for c in citations]
    unique_authors = set(authors)

    # Penalize if all citations from same author
    if len(unique_authors) == 1 and len(citations) > 1:
        assessment["issues"].append("All citations from single author or source")
        assessment["recommendations"].append("Diversify citation sources")
        assessment["quality_score"] -= 0.3

    # Base score on number of citations
    if len(citations) == 1:
        base_score = 0.5
    elif len(citations) == 2:
        base_score = 0.7
    elif len(citations) >= 3:
        base_score = 0.9
    else:
        base_score = 0.3

    assessment["quality_score"] += base_score

    # Cap at 1.0
    assessment["quality_score"] = min(1.0, max(0.0, assessment["quality_score"]))

    # Determine overall quality level
    if assessment["quality_score"] >= 0.8:
        assessment["quality_level"] = "strong"
    elif assessment["quality_score"] >= 0.6:
        assessment["quality_level"] = "adequate"
    elif assessment["quality_score"] >= 0.3:
        assessment["quality_level"] = "weak"
    else:
        assessment["quality_level"] = "insufficient"

    return assessment


# ============================================
# Citation Pattern Detection
# ============================================

def detect_citation_patterns(
    claims: List[Dict[str, Any]],
    draft_id: str
) -> Dict[str, Any]:
    """
    Analyze citation patterns across all claims in a draft.

    Detects:
    - Over-reliance on specific sources
    - Uncited claims requiring support
    - Citation distribution across sections
    - Common citation sources

    Args:
        claims: List of all claims from draft
        draft_id: Draft identifier

    Returns:
        Pattern analysis results

    Validates: Requirement 3.4 - Detect over-reliance patterns
    """
    patterns = {
        "draft_id": draft_id,
        "total_claims": len(claims),
        "total_citations": 0,
        "uncited_claims": 0,
        "over_relied_sources": [],
        "citation_distribution": {},
        "issues": [],
        "recommendations": []
    }

    # Collect all citations
    all_citations = []
    citation_counts = Counter()

    for claim in claims:
        citations = claim.get("existing_citations", [])
        patterns["total_citations"] += len(citations)

        if len(citations) == 0 and claim.get("requires_citation", True):
            patterns["uncited_claims"] += 1

        for citation in citations:
            all_citations.append(citation)
            # Extract author from citation string
            author_match = re.match(r'([A-Za-z\s]+?)(?:\s+et\s+al\.)?\s*\(', citation)
            if author_match:
                author = author_match.group(1).strip()
                citation_counts[citation] += 1

    # Detect over-reliance (same citation appears in >30% of claims)
    if claims:
        over_reliance_threshold = len(claims) * 0.3

        for citation, count in citation_counts.most_common(10):
            if count >= over_reliance_threshold:
                patterns["over_relied_sources"].append({
                    "citation": citation,
                    "usage_count": count,
                    "percentage": (count / len(claims)) * 100
                })

        if patterns["over_relied_sources"]:
            patterns["issues"].append("Heavy reliance on few sources detected")
            patterns["recommendations"].append("Diversify citations across more sources")

    # Analyze citation distribution by section
    section_citations = {}
    for claim in claims:
        section = claim.get("section_location", "Unknown")
        if section not in section_citations:
            section_citations[section] = 0

        section_citations[section] += len(claim.get("existing_citations", []))

    patterns["citation_distribution"] = section_citations

    # Identify sections with low citation density
    for section, count in section_citations.items():
        claims_in_section = len([c for c in claims if c.get("section_location") == section])
        if claims_in_section > 0:
            avg_citations = count / claims_in_section
            if avg_citations < 1.0:
                patterns["issues"].append(f"Low citation density in {section} section")

    # Overall assessment
    if patterns["uncited_claims"] > 0:
        patterns["issues"].append(f"{patterns['uncited_claims']} claims lack citation support")
        patterns["recommendations"].append("Add citations to unsupported claims")

    return patterns


# ============================================
# Literature Database Integration
# ============================================

async def suggest_stronger_alternatives(
    claim: Dict[str, Any],
    current_citations: List[Dict[str, Any]],
    project_id: str,
    max_suggestions: int = 3
) -> List[Dict[str, Any]]:
    """
    Suggest stronger citation alternatives from the literature database.

    Uses semantic search to find relevant papers from the project's
    literature collection that could strengthen citation support.

    Args:
        claim: Claim needing citation support
        current_citations: Current citations for this claim
        project_id: Project ID to search within
        max_suggestions: Maximum number of suggestions

    Returns:
        List of suggested papers with relevance scores

    Validates: Requirement 3.5 - Suggest stronger alternatives
    """
    suggestions = []

    try:
        # Get claim text
        claim_text = claim.get("claim_text", "")

        if not claim_text:
            return suggestions

        # Embed the claim text
        from app.services.rag_ingest import embed_chunks

        embeddings = embed_chunks([claim_text])

        if not embeddings:
            logger.warning("Failed to generate embedding for claim")
            return suggestions

        claim_embedding = embeddings[0].embedding

        # Search for relevant documents in the project
        # Use the match_document_chunks function from database
        search_results = supabase.rpc(
            "match_document_chunks",
            {
                "query_embedding": claim_embedding,
                "proj_id": project_id,  # Fixed: parameter name is proj_id, not p_project_id
                "match_count": max_suggestions
            }
        ).execute()

        if not search_results.data:
            return suggestions

        # Get unique documents from results
        document_ids = list(set([result["document_id"] for result in search_results.data]))

        # Fetch document details
        for doc_id in document_ids[:max_suggestions]:
            doc_response = supabase.table("documents").select("*").eq("id", doc_id).single().execute()

            if doc_response.data:
                document = doc_response.data
                analysis = document.get("analysis", {})

                # Calculate relevance based on similarity
                relevance_score = max([
                    r["similarity"]
                    for r in search_results.data
                    if r["document_id"] == doc_id
                ])

                # Extract citation info
                citation_metadata = analysis.get("citation_metadata", {})

                suggestion = {
                    "document_id": doc_id,
                    "title": document.get("title", "Unknown"),
                    "authors": citation_metadata.get("all_authors", []),
                    "year": citation_metadata.get("year", "Unknown"),
                    "relevance_score": float(relevance_score),
                    "reason": f"Relevant to: {claim_text[:100]}...",
                    "executive_summary": analysis.get("executive_summary", "")
                }

                suggestions.append(suggestion)

        # Sort by relevance
        suggestions.sort(key=lambda x: x["relevance_score"], reverse=True)

        logger.info(f"Found {len(suggestions)} alternative citations for claim")

    except Exception as e:
        logger.error(f"Failed to suggest alternatives: {e}")

    return suggestions


# ============================================
# Citation Gap Analysis
# ============================================

def identify_citation_gaps(
    claims: List[Dict[str, Any]],
    citation_quality_assessments: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Identify claims with citation gaps that need attention.

    Prioritizes claims by:
    - Importance score
    - Current citation quality
    - Claim type

    Args:
        claims: List of all claims
        citation_quality_assessments: Quality assessments for each claim

    Returns:
        Prioritized list of claims needing citation improvements

    Validates: Requirement 3.2 - Flag claims lacking support
    """
    gaps = []

    for i, claim in enumerate(claims):
        quality = citation_quality_assessments[i] if i < len(citation_quality_assessments) else {}

        # Only flag if claim requires citation
        if not claim.get("requires_citation", True):
            continue

        quality_score = quality.get("quality_score", 0.0)
        importance = claim.get("importance_score", 0.5)

        # Calculate gap severity
        # High importance + low quality = high severity
        gap_severity = importance * (1.0 - quality_score)

        if gap_severity > 0.3:  # Threshold for flagging
            gap = {
                "claim_id": claim.get("id"),
                "claim_text": claim.get("claim_text", "")[:200],
                "section_location": claim.get("section_location"),
                "importance_score": importance,
                "quality_score": quality_score,
                "gap_severity": gap_severity,
                "current_citations": len(claim.get("existing_citations", [])),
                "issues": quality.get("issues", []),
                "recommendations": quality.get("recommendations", [])
            }

            gaps.append(gap)

    # Sort by severity (highest first)
    gaps.sort(key=lambda x: x["gap_severity"], reverse=True)

    return gaps


# ============================================
# Batch Processing
# ============================================

async def analyze_draft_citation_quality(draft_id: str, project_id: str) -> Dict[str, Any]:
    """
    Complete citation quality analysis for a draft.

    Performs:
    1. Quality assessment for each claim's citations
    2. Pattern detection across all claims
    3. Gap identification
    4. Suggestion of stronger alternatives

    Args:
        draft_id: Draft identifier
        project_id: Project identifier

    Returns:
        Comprehensive citation quality report

    Validates: Requirements 3.2, 3.3, 3.4, 3.5
    """
    try:
        logger.info(f"Starting citation quality analysis for draft_id={draft_id}")

        # Fetch all claims for draft
        claims_response = supabase.table("draft_claims").select("*").eq("draft_id", draft_id).execute()

        if not claims_response.data:
            logger.warning(f"No claims found for draft_id={draft_id}")
            return {
                "message": "No claims found for analysis",
                "draft_id": draft_id
            }

        claims = claims_response.data

        # Assess quality for each claim
        quality_assessments = []
        for claim in claims:
            citations = [
                {"citation_string": c, "authors": [c.split("(")[0].strip()], "year": c.split("(")[1].split(")")[0] if "(" in c else "Unknown"}
                for c in claim.get("existing_citations", [])
            ]

            assessment = assess_citation_quality(claim, citations)
            quality_assessments.append(assessment)

        # Detect patterns
        patterns = detect_citation_patterns(claims, draft_id)

        # Identify gaps
        gaps = identify_citation_gaps(claims, quality_assessments)

        # Summary statistics
        avg_quality = sum([a["quality_score"] for a in quality_assessments]) / len(quality_assessments) if quality_assessments else 0.0

        report = {
            "draft_id": draft_id,
            "project_id": project_id,
            "total_claims": len(claims),
            "average_quality_score": round(avg_quality, 2),
            "patterns": patterns,
            "citation_gaps": gaps[:10],  # Top 10 gaps
            "overall_assessment": {
                "quality_level": "strong" if avg_quality >= 0.8 else "adequate" if avg_quality >= 0.6 else "needs_improvement",
                "major_issues": patterns.get("issues", []),
                "recommendations": patterns.get("recommendations", [])
            }
        }

        logger.info(f"Citation quality analysis completed for draft_id={draft_id}")

        return report

    except Exception as e:
        logger.error(f"Citation quality analysis failed: {str(e)}")
        raise

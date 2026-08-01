"""
Coverage Gap Detection Service

Identifies gaps in literature coverage relative to draft content by:
- Comparing draft topics against project literature
- Identifying missing seminal papers
- Detecting methodology and theoretical framework gaps
- Generating prioritized gap reports with recommendations

Requirements: 4.1, 4.2, 4.3, 4.4, 4.5
"""

import asyncio
from typing import Dict, Any, List, Optional
from app.core.config import settings
from app.core.supabase_client import supabase
from app.core.logging_config import get_logger
from app.core.openai_client import get_openai_client
import datetime

logger = get_logger(__name__)

client = None


def _get_client():
    global client
    if client is None:
        client = get_openai_client()
    return client


# ============================================
# AI Prompts for Gap Detection
# ============================================

COVERAGE_ANALYSIS_PROMPT = """You are an expert academic reviewer analyzing research draft coverage.

Analyze this research draft and identify gaps in literature coverage. Respond with ONLY valid JSON.

Return this exact structure:
{
  "research_areas": [
    {
      "area": "Specific research area or topic",
      "coverage_level": "comprehensive|partial|minimal|absent",
      "key_topics": ["topic1", "topic2"]
    }
  ],
  "identified_gaps": [
    {
      "gap_type": "missing_seminal|methodology_gap|theoretical_gap",
      "description": "Detailed description of the gap",
      "priority": "high|medium|low",
      "reasoning": "Why this gap is important"
    }
  ],
  "methodological_assessment": {
    "approaches_covered": ["approach1", "approach2"],
    "missing_approaches": ["approach1", "approach2"],
    "framework_gaps": ["gap1", "gap2"]
  }
}

Gap Types:
- **missing_seminal**: Key foundational papers in the field not cited
- **methodology_gap**: Important methodological approaches not discussed or cited
- **theoretical_gap**: Relevant theoretical frameworks or models not addressed

Priority Levels:
- **high**: Critical gap that significantly weakens the work
- **medium**: Important gap that should be addressed for completeness
- **low**: Minor gap, optional but beneficial to address

Guidelines:
- Consider what a peer reviewer would flag
- Identify patterns in what's cited vs. what's discussed
- Look for methodologies mentioned but not properly grounded in literature
- Identify theoretical claims without theoretical foundation citations
- Be specific about what's missing and why it matters
"""


# ============================================
# Semantic Similarity Utilities
# ============================================


def categorize_citation_strength(
    similarity_score: float,
    citation_count: int,
    claim_importance: float
) -> str:
    """
    Categorize the strength of citation support for a claim.

    Args:
        similarity_score: Semantic similarity to literature (0.0 to 1.0)
        citation_count: Number of existing citations
        claim_importance: Importance score of the claim (0.0 to 1.0)

    Returns:
        Strength category: "strong", "moderate", "weak", "missing"
    """
    # High-importance claims need stronger evidence
    if claim_importance > 0.7:
        required_citations = 2
        required_similarity = 0.7
    elif claim_importance > 0.4:
        required_citations = 1
        required_similarity = 0.6
    else:
        required_citations = 1
        required_similarity = 0.5

    # Strong: Has citations AND high similarity to literature
    if citation_count >= required_citations and similarity_score >= required_similarity:
        return "strong"

    # Moderate: Has some citations OR moderate similarity
    elif citation_count >= 1 or similarity_score >= 0.6:
        return "moderate"

    # Weak: Limited support
    elif citation_count > 0 or similarity_score >= 0.4:
        return "weak"

    # Missing: No meaningful support
    else:
        return "missing"


# ============================================
# Coverage Gap Detection
# ============================================


# ============================================
# External Paper Fallback
# ============================================

_EXTERNAL_FALLBACK_THRESHOLD = 3   # trigger fallback if fewer local papers
_MAX_EXTERNAL_PAPERS = 5           # cap external results per gap


def _normalize_external_paper(raw: dict, source: str) -> dict:
    """Normalize SS/OA paper dict to match suggested_papers schema."""
    return {
        "title": raw.get("title", ""),
        "authors": raw.get("authors", []),
        "year": raw.get("year") or raw.get("publication_year"),
        "abstract": raw.get("abstract", ""),
        "relevance_score": raw.get("relevance_score", 0.5),
        "source": source,           # "semantic_scholar" | "open_access"
        "url": raw.get("url") or raw.get("paper_url") or raw.get("open_access_url", ""),
        "open_access_url": raw.get("open_access_url") or raw.get("pdf_url", ""),
        "citation_count": raw.get("citation_count") or raw.get("cited_by_count", 0),
        "external": True,           # flag to distinguish from local papers
    }


def _gap_paper_passes_domain_gate(
    paper: dict,
    manuscript_profile: dict | None,
) -> bool:
    """Lightweight domain check for gap suggested papers.

    Rejects papers with zero overlap against the manuscript's topic_terms and
    routing_domain — the same guard applied to task sources in
    draft_external_source_discovery._passes_domain_gate, reimplemented here to
    avoid a circular import. Returns True (pass) when no profile is supplied.
    """
    if not manuscript_profile:
        return True
    profile_terms: set[str] = set()
    routing_domain = str(manuscript_profile.get("routing_domain") or "").lower()
    if routing_domain:
        profile_terms.update(routing_domain.replace("_", " ").split())
    for t in manuscript_profile.get("topic_terms") or []:
        profile_terms.update(str(t).lower().split())
    for tag in manuscript_profile.get("domain_tags") or []:
        profile_terms.update(str(tag).lower().replace("_", " ").split())
    if not profile_terms:
        return True
    paper_text = " ".join(filter(None, [
        str(paper.get("title") or ""),
        str(paper.get("abstract") or ""),
    ])).lower()
    paper_words = set(paper_text.split())
    return bool(profile_terms & paper_words)


async def _fetch_external_papers_for_gap(
    gap_description: str,
    needed: int,
    max_external: int = _MAX_EXTERNAL_PAPERS,
    manuscript_profile: dict | None = None,
) -> list:
    """Semantic Scholar first, OpenAlex cascade, deduplicate by title.

    manuscript_profile is used to domain-filter results — papers with zero
    overlap against the profile's topic_terms/routing_domain are dropped before
    they can surface as gap suggestions (issue #3 under-retrieval fix).
    """
    results: list = []
    seen_titles: set = set()

    # 1. Try Semantic Scholar (sync client — wrap in thread)
    try:
        from app.services.external_apis.semantic_scholar import SemanticScholarAPI
        ss = SemanticScholarAPI()
        raw = await asyncio.to_thread(ss.search_papers, gap_description, limit=max_external)
        for p in (raw or []):
            t = (p.get("title") or "").lower().strip()
            if t and t not in seen_titles:
                normalized = _normalize_external_paper(p, "semantic_scholar")
                if _gap_paper_passes_domain_gate(normalized, manuscript_profile):
                    seen_titles.add(t)
                    results.append(normalized)
    except Exception as e:
        logger.warning(f"[EXTERNAL FALLBACK] Semantic Scholar failed: {e}")

    # 2. Backfill with OpenAlex if still short
    if len(results) < needed:
        try:
            from app.services.external_apis.openalex import find_open_access_papers_for_gap
            oa_raw = await find_open_access_papers_for_gap(gap_description, max_external)
            for p in (oa_raw or []):
                t = (p.get("title") or "").lower().strip()
                if t and t not in seen_titles:
                    normalized = _normalize_external_paper(p, "open_access")
                    if _gap_paper_passes_domain_gate(normalized, manuscript_profile):
                        seen_titles.add(t)
                        results.append(normalized)
        except Exception as e:
            logger.warning(f"[EXTERNAL FALLBACK] OpenAlex failed: {e}")

    return results[:max_external]


# ============================================
# Gap Remediation Suggestions
# ============================================

async def suggest_papers_for_gaps(
    gaps: List[Dict[str, Any]],
    project_id: str,
    max_suggestions_per_gap: int = 3,
    manuscript_profile: dict | None = None,
) -> List[Dict[str, Any]]:
    """
    Suggest specific papers to address identified gaps.

    Uses semantic search to find relevant papers from project literature.
    External fallback results are domain-filtered via manuscript_profile to
    prevent off-domain RAG contamination in gap suggestions (issue #3).

    Args:
        gaps: List of identified coverage gaps
        project_id: Project identifier
        max_suggestions_per_gap: Maximum suggestions per gap
        manuscript_profile: Manuscript profile for domain filtering of external results

    Returns:
        Gaps enhanced with paper suggestions

    Validates: Requirement 4.3 - Suggest specific papers for gaps
    """
    try:
        from app.services.rag_ingest import embed_chunks

        for gap in gaps:
            gap_description = gap.get("description", "")

            if not gap_description:
                continue

            # Embed the gap description
            embeddings = embed_chunks([gap_description])

            if not embeddings:
                logger.warning(f"Failed to embed gap description, trying external fallback")
                try:
                    gap["suggested_papers"] = await _fetch_external_papers_for_gap(
                        gap_description, _EXTERNAL_FALLBACK_THRESHOLD,
                        manuscript_profile=manuscript_profile,
                    )
                except Exception:
                    gap["suggested_papers"] = []
                continue

            gap_embedding = embeddings[0].embedding

            # Search for relevant documents
            search_results = supabase.rpc(
                "match_document_chunks",
                {
                    "query_embedding": gap_embedding,
                    "proj_id": project_id,  # Fixed: parameter name is proj_id, not p_project_id
                    "match_count": max_suggestions_per_gap * 2  # Get extra for deduplication
                }
            ).execute()

            if not search_results.data:
                external = await _fetch_external_papers_for_gap(
                    gap_description, _EXTERNAL_FALLBACK_THRESHOLD,
                    manuscript_profile=manuscript_profile,
                )
                gap["suggested_papers"] = external
                continue

            # Get unique documents
            document_ids = list(set([r["document_id"] for r in search_results.data]))

            # Fetch document details
            suggested_papers = []
            for doc_id in document_ids[:max_suggestions_per_gap]:
                doc_response = supabase.table("documents").select("*").eq("id", doc_id).neq("resolution_status", "unresolved").single().execute()

                if doc_response.data:
                    document = doc_response.data
                    analysis = document.get("analysis", {})
                    citation_metadata = analysis.get("citation_metadata", {})

                    # Get similarity score
                    similarity = max([
                        r["similarity"]
                        for r in search_results.data
                        if r["document_id"] == doc_id
                    ])

                    paper = {
                        "document_id": doc_id,
                        "title": document.get("title", "Unknown"),
                        "authors": citation_metadata.get("all_authors", []),
                        "year": citation_metadata.get("year", "Unknown"),
                        "relevance_score": float(similarity),
                        "executive_summary": analysis.get("executive_summary", ""),
                        "key_findings": analysis.get("key_findings", [])[:2]  # Top 2 findings
                    }

                    suggested_papers.append(paper)

            # External fallback: if local library is sparse, search SS + OpenAlex
            if len(suggested_papers) < _EXTERNAL_FALLBACK_THRESHOLD:
                try:
                    needed = _EXTERNAL_FALLBACK_THRESHOLD - len(suggested_papers)
                    external = await _fetch_external_papers_for_gap(
                        gap_description, needed, manuscript_profile=manuscript_profile,
                    )
                    suggested_papers.extend(external)
                except Exception as ext_err:
                    logger.warning(f"[EXTERNAL FALLBACK] Failed for gap, using local only: {ext_err}")

            gap["suggested_papers"] = suggested_papers

        logger.info(f"Generated paper suggestions for {len(gaps)} gaps")

        return gaps

    except Exception as e:
        logger.error(f"Failed to suggest papers for gaps: {e}")
        return gaps


def prioritize_gaps(gaps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Prioritize gaps by importance and urgency.

    Priority factors:
    - Gap type (missing_seminal > theoretical_gap > methodology_gap)
    - Assigned priority level
    - Availability of remediation in literature database

    Args:
        gaps: List of coverage gaps

    Returns:
        Gaps sorted by priority (highest first)

    Validates: Requirement 4.5 - Prioritized gap reports
    """
    priority_weights = {
        "high": 3,
        "medium": 2,
        "low": 1
    }

    gap_type_weights = {
        "missing_seminal": 3,
        "theoretical_gap": 2,
        "methodology_gap": 1
    }

    for gap in gaps:
        # Calculate priority score
        priority_score = priority_weights.get(gap.get("priority", "low"), 1)
        type_score = gap_type_weights.get(gap.get("gap_type", "methodology_gap"), 1)

        # Boost if we have literature to suggest
        has_suggestions = len(gap.get("suggested_papers", [])) > 0
        suggestion_bonus = 0.5 if has_suggestions else 0

        gap["priority_score"] = priority_score * type_score + suggestion_bonus

    # Sort by priority score (descending)
    gaps.sort(key=lambda x: x.get("priority_score", 0), reverse=True)

    return gaps


# ============================================
# Embedding-Based Real Gap Detection
# ============================================


# ============================================
# Complete Coverage Gap Pipeline
# ============================================

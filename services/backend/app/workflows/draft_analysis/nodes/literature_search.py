"""
Literature Search Node

Searches for supporting literature for each claim in parallel.
Uses the improved RAG retrieval system with adaptive chunking.
"""

from app.workflows.draft_analysis.state import DraftAnalysisState, Claim
from app.workflows.draft_analysis.citation_rules import needs_missing_citation_task
from app.core.logging_config import get_logger
from app.core.supabase_client import supabase
from typing import List, Dict, Any
import asyncio
import re

logger = get_logger(__name__)

# Relevance floor for the BROAD chunk fallback (Tier 2). Lower than the precise
# claim-to-claim threshold (0.7) to keep recall, but high enough that the result
# is not padded with near-random, cross-domain chunks. Tunable via env.
import os as _os
BROAD_FALLBACK_MIN_SIMILARITY = float(_os.getenv("RAG_BROAD_FALLBACK_MIN_SIMILARITY", "0.45"))


GENERIC_SOURCE_STOPWORDS = {
    "about", "across", "analysis", "article", "claim", "claims", "current",
    "draft", "evidence", "found", "from", "include", "includes", "including",
    "journal", "literature", "manuscript", "method", "methods", "paper",
    "papers", "research", "review", "section", "source", "sources", "study",
    "studies", "support", "supporting", "systematic", "that", "their",
    "these", "this", "using", "with", "without",
}


def _terms(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z][a-z0-9+-]{2,}", (text or "").lower())
        if token not in GENERIC_SOURCE_STOPWORDS and len(token) >= 3
    }


def _profile_terms(query: str, manuscript_profile: dict | None = None) -> set[str]:
    return _terms(" ".join([
        query or "",
        str((manuscript_profile or {}).get("routing_domain") or ""),
        " ".join((manuscript_profile or {}).get("domain_tags") or []),
        " ".join((manuscript_profile or {}).get("review_lenses") or []),
    ]))


def _result_text(result: dict[str, Any]) -> str:
    return " ".join(
        str(result.get(key) or "")
        for key in ("title", "document_title", "source_title", "content", "abstract", "chunk_text")
    )


def _filter_domain_contamination(
    *,
    query: str,
    results: list[dict[str, Any]],
    manuscript_profile: dict | None = None,
) -> list[dict[str, Any]]:
    query_terms = _terms(query)
    profile_terms = _profile_terms(query, manuscript_profile)
    if not query_terms and not profile_terms:
        return results
    filtered: list[dict[str, Any]] = []
    for result in results or []:
        text = _result_text(result)
        result_terms = _terms(text)
        similarity = float(result.get("similarity") or result.get("combined_score") or result.get("relevance_score") or 0.0)
        query_overlap = result_terms & query_terms
        profile_overlap = result_terms & profile_terms
        if similarity < 0.72 and not query_overlap:
            continue
        if profile_terms and similarity < 0.82 and not profile_overlap and len(query_overlap) < 2:
            continue
        filtered.append(result)
    return filtered


async def search_literature_for_claim(
    claim: Claim,
    project_id: str,
    max_results: int = 5,
    manuscript_profile: dict | None = None,
) -> Dict[str, Any]:
    """
    Search for literature supporting a single claim.

    Uses a two-tier approach:
    1. PRECISE: Claim-to-claim matching using document_claims table (30-50% better precision)
    2. FALLBACK: RAG chunk search for broad context (if claim matching yields no results)

    Args:
        claim: The claim to search for
        project_id: Project ID to search within
        max_results: Maximum number of results to return

    Returns:
        Dictionary with claim and found literature, including match metadata
    """
    from app.services.rag_retrieval import retrieve_relevant_chunks_hybrid
    from app.services.claim_analysis import find_supporting_claims

    try:
        # Use the claim text as the search query
        query = claim['claim_text']

        logger.info(f"[Literature Search] Searching for claim...")

        # TIER 1: Try claim-to-claim matching first (PRECISE)
        logger.info(f"[Literature Search] Attempting claim-to-claim matching...")
        supporting_claims = await find_supporting_claims(
            draft_claim_text=query,
            project_id=project_id,
            similarity_threshold=0.7,  # Higher threshold for quality
            max_results=max_results
        )

        if supporting_claims:
            supporting_claims = _filter_domain_contamination(
                query=query,
                results=supporting_claims,
                manuscript_profile=manuscript_profile,
            )
        if supporting_claims:
            logger.info(
                f"[Literature Search] Found {len(supporting_claims)} supporting claims "
                f"via claim-to-claim matching (PRECISE)"
            )
            return {
                'claim_id': claim['id'],
                'claim': claim,
                'results': supporting_claims,
                'result_count': len(supporting_claims),
                'match_type': 'claim_based',
                'match_quality': 'precise'
            }

        # TIER 2: Fallback to RAG chunk search (BROAD)
        logger.info(
            f"[Literature Search] No claim matches found, falling back to RAG chunks (BROAD)"
        )
        # Broad fallback still needs a relevance floor so the top_k is not filled
        # with weak, potentially cross-domain chunks that become bogus citations.
        results = retrieve_relevant_chunks_hybrid(
            project_id=project_id,
            query=query,
            limit=max_results,
            use_reranking=True,
            min_similarity=BROAD_FALLBACK_MIN_SIMILARITY,
        )
        results = _filter_domain_contamination(
            query=query,
            results=results,
            manuscript_profile=manuscript_profile,
        )

        return {
            'claim_id': claim['id'],
            'claim': claim,
            'results': results,
            'result_count': len(results),
            'match_type': 'chunk_based',
            'match_quality': 'broad'
        }

    except Exception as e:
        logger.error(f"[Literature Search] Error searching for claim {claim['id']}: {e}")
        return {
            'claim_id': claim['id'],
            'claim': claim,
            'results': [],
            'result_count': 0,
            'match_type': 'failed',
            'error': str(e)
        }


async def search_all_claims_parallel(
    claims: List[Claim],
    project_id: str,
    max_results: int = 5,
    manuscript_profile: dict | None = None,
) -> List[Dict[str, Any]]:
    """
    Search for literature for all claims in parallel.

    This is a key optimization - instead of searching sequentially,
    we search for all claims simultaneously.

    Args:
        claims: List of claims to search for
        project_id: Project ID to search within
        max_results: Maximum results per claim

    Returns:
        List of search results for each claim
    """
    logger.info(f"[Literature Search] Starting parallel search for {len(claims)} claims")

    # Create search tasks for all claims
    tasks = [
        search_literature_for_claim(claim, project_id, max_results)
        if manuscript_profile is None
        else search_literature_for_claim(claim, project_id, max_results, manuscript_profile)
        for claim in claims
    ]

    # Execute all searches in parallel
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Handle any exceptions
    successful_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"[Literature Search] Claim {i} failed: {result}")
            successful_results.append({
                'claim_id': claims[i]['id'],
                'claim': claims[i],
                'results': [],
                'result_count': 0,
                'error': str(result)
            })
        else:
            successful_results.append(result)

    logger.info(
        f"[Literature Search] Completed parallel search: "
        f"{len(successful_results)} claims searched, "
        f"{sum(r['result_count'] for r in successful_results)} total results found"
    )

    return successful_results


async def literature_search_node(state: DraftAnalysisState) -> DraftAnalysisState:
    """
    Search for literature supporting each claim (in parallel).

    This node uses the improved RAG retrieval system to find relevant papers
    from the user's library that support each claim. All claims are searched
    simultaneously for maximum performance.

    Args:
        state: Current workflow state

    Returns:
        Updated state with literature search results
    """
    logger.info(f"[Literature Search] Starting for draft_id={state['draft_id']}")

    claims = state.get("claims", [])
    project_id = state["project_id"]

    if not claims:
        logger.warning("[Literature Search] No claims to search for")
        # Return only fields to UPDATE - LangGraph merges with existing state
        return {
            'literature_search_results': [],
            'current_step': 'Literature Search (No Claims)',
            'progress_percentage': 50
        }

    # Check if documents exist in the project
    try:
        documents_response = supabase.table("documents").select("id").eq("project_id", project_id).limit(1).execute()
        if not documents_response.data:
            logger.warning(
                f"[Literature Search] No documents found in project {project_id}! "
                f"Citation suggestions will be empty. User should upload documents first."
            )
            # Return empty search results - the workflow will continue but with no citations
            # Note: Return only fields to UPDATE - LangGraph merges with existing state
            return {
                'literature_search_results': [],
                'current_step': 'Literature Search (No Documents)',
                'progress_percentage': 50
            }
    except Exception as doc_check_error:
        logger.error(f"[Literature Search] Failed to check for documents: {doc_check_error}")
        # Continue anyway - don't fail the entire workflow

    try:
        # Limit search to primary claims to save time/cost
        # Can be made configurable later
        primary_claims = [
            claim for claim in state.get("primary_claims", claims)
            if needs_missing_citation_task(claim)
        ]

        # If too many primary claims, limit to top 20 by importance
        if len(primary_claims) > 20:
            logger.warning(
                f"[Literature Search] {len(primary_claims)} primary claims found, "
                f"limiting to top 20 by importance"
            )
            primary_claims = sorted(
                primary_claims,
                key=lambda c: c['importance_score'],
                reverse=True
            )[:20]

        logger.info(f"[Literature Search] Searching for {len(primary_claims)} claims in parallel")

        # Run parallel search (this is the key optimization!)
        search_results = await search_all_claims_parallel(
            primary_claims,
            project_id,
            max_results=5,
            manuscript_profile=state.get("manuscript_profile") or {},
        )

        # Count successful searches
        successful_searches = sum(1 for r in search_results if r['result_count'] > 0)
        total_results = sum(r['result_count'] for r in search_results)

        logger.info(
            f"[Literature Search] Found literature for {successful_searches}/{len(primary_claims)} claims "
            f"({total_results} total results)"
        )

        # Store results in state for next node
        # Note: Return only fields to UPDATE - LangGraph merges with existing state
        logger.info(f"[Literature Search] Returning {len(search_results)} search results to state")
        return {
            'literature_search_results': search_results,
            'current_step': 'Literature Search',
            'progress_percentage': 50
        }

    except Exception as e:
        logger.error(f"[Literature Search] Error: {e}")
        errors = state.get('errors', [])
        errors.append(f"Literature search failed: {str(e)}")

        # Note: Return only fields to UPDATE - LangGraph merges with existing state
        return {
            'literature_search_results': [],
            'errors': errors,
            'current_step': 'Literature Search (Failed)',
            'progress_percentage': 50
        }

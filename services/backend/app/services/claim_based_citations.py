"""
Claim-Based Citation Suggestion Service

Provides precise citation suggestions by matching draft claims against
document claims using semantic similarity.

This dramatically improves citation quality compared to RAG chunk matching:
- Before: Match draft text → document text chunks (imprecise)
- After: Match draft claim → document claim (precise, contextual)
"""

from typing import List, Dict, Any, Optional
from app.core.supabase_client import supabase
from app.core.logging_config import get_logger
from openai import OpenAI
import os

logger = get_logger(__name__)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


async def find_supporting_claims(
    draft_claim_text: str,
    project_id: str,
    similarity_threshold: float = 0.7,
    max_results: int = 5,
    exclude_document_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Find document claims that support or relate to a draft claim.

    This uses the find_similar_claims() PostgreSQL function to perform
    cosine similarity search on claim embeddings.

    Args:
        draft_claim_text: The claim from the draft to find support for
        project_id: Limit search to documents in this project
        similarity_threshold: Minimum similarity score (0.0-1.0)
        max_results: Maximum number of claims to return
        exclude_document_id: Optional document ID to exclude from results

    Returns:
        List of matching claims with metadata:
        [{
            "claim_id": "...",
            "document_id": "...",
            "document_title": "...",
            "claim_text": "...",
            "claim_type": "empirical",
            "importance_score": 0.9,
            "similarity_score": 0.85,
            "section_title": "Results",
            "page_number": 5
        }]
    """
    try:
        logger.info(f"[CLAIM-CITATION] Finding supporting claims for: '{draft_claim_text[:100]}...'")

        # Generate embedding for the draft claim
        embedding_response = client.embeddings.create(
            model="text-embedding-3-small",
            input=[draft_claim_text],
            dimensions=1536
        )
        draft_claim_embedding = embedding_response.data[0].embedding

        # Use PostgreSQL find_similar_claims function
        # Note: We need to filter by project_id manually since the function doesn't do it
        query = f"""
            SELECT
                dc.id as claim_id,
                dc.document_id,
                d.title as document_title,
                dc.claim_text,
                dc.claim_type,
                dc.importance_score,
                dc.section_title,
                dc.page_number,
                ROUND((1 - (dc.embedding <=> %s::vector))::NUMERIC, 3) as similarity_score
            FROM document_claims dc
            JOIN documents d ON dc.document_id = d.id
            WHERE dc.project_id = %s
                AND (1 - (dc.embedding <=> %s::vector)) >= %s
                {f"AND dc.document_id != '{exclude_document_id}'" if exclude_document_id else ""}
            ORDER BY dc.embedding <=> %s::vector ASC
            LIMIT %s
        """

        # Execute raw SQL query (Supabase Python SDK doesn't support vector operations directly)
        # We'll use the REST API approach through rpc
        result = supabase.rpc(
            'find_similar_claims',
            {
                'query_embedding': draft_claim_embedding,
                'similarity_threshold': similarity_threshold,
                'max_results': max_results * 2,  # Get more, then filter by project_id
                'exclude_document_id': exclude_document_id
            }
        ).execute()

        # Filter by project_id
        matching_claims = []
        for claim in result.data:
            # Verify claim belongs to project
            claim_check = supabase.table("document_claims").select("project_id").eq("id", claim["claim_id"]).single().execute()
            if claim_check.data and claim_check.data["project_id"] == project_id:
                matching_claims.append(claim)
                if len(matching_claims) >= max_results:
                    break

        logger.info(f"[CLAIM-CITATION] Found {len(matching_claims)} supporting claims (threshold={similarity_threshold})")

        # Log top matches
        for i, claim in enumerate(matching_claims[:3]):
            logger.info(
                f"[CLAIM-CITATION] Match {i+1}: "
                f"similarity={claim['similarity_score']}, "
                f"type={claim.get('claim_type')}, "
                f"text='{claim['claim_text'][:80]}...'"
            )

        return matching_claims

    except Exception as e:
        logger.error(f"[CLAIM-CITATION] Error finding supporting claims: {e}")
        return []


async def suggest_citations_for_draft_claim(
    draft_claim: Dict[str, Any],
    project_id: str,
    max_suggestions: int = 3
) -> List[Dict[str, Any]]:
    """
    Generate citation suggestions for a single draft claim.

    This is the main entry point for citation suggestions during draft analysis.

    Args:
        draft_claim: Draft claim dict with at least {"claim_text": "..."}
        project_id: Project ID
        max_suggestions: Maximum number of papers to suggest

    Returns:
        List of citation suggestions:
        [{
            "document_id": "...",
            "document_title": "...",
            "relevance_score": 0.85,
            "supporting_claim": "The claim from the paper that supports this",
            "suggestion_reason": "Why this paper is relevant",
            "section_reference": "Results (p. 5)"
        }]
    """
    try:
        claim_text = draft_claim.get("claim_text", "")
        if not claim_text:
            return []

        logger.info(f"[CLAIM-CITATION] Generating citations for draft claim: '{claim_text[:100]}...'")

        # Find supporting claims
        supporting_claims = await find_supporting_claims(
            draft_claim_text=claim_text,
            project_id=project_id,
            similarity_threshold=0.65,  # Lower threshold for broader matches
            max_results=max_suggestions * 2  # Get extras to deduplicate by document
        )

        if not supporting_claims:
            logger.info(f"[CLAIM-CITATION] No supporting claims found")
            return []

        # Group by document (one suggestion per document, use best claim)
        suggestions_by_document = {}
        for claim in supporting_claims:
            doc_id = claim["document_id"]
            if doc_id not in suggestions_by_document:
                suggestions_by_document[doc_id] = {
                    "document_id": doc_id,
                    "document_title": claim["document_title"],
                    "relevance_score": float(claim["similarity_score"]),
                    "supporting_claim": claim["claim_text"],
                    "suggestion_reason": f"{claim['claim_type'].capitalize()} finding with {int(float(claim['similarity_score']) * 100)}% similarity",
                    "section_reference": f"{claim.get('section_title', 'Unknown section')}" + (f" (p. {claim['page_number']})" if claim.get('page_number') else "")
                }

        # Sort by relevance and take top N
        suggestions = sorted(
            suggestions_by_document.values(),
            key=lambda x: x["relevance_score"],
            reverse=True
        )[:max_suggestions]

        logger.info(f"[CLAIM-CITATION] Generated {len(suggestions)} citation suggestions")

        return suggestions

    except Exception as e:
        logger.error(f"[CLAIM-CITATION] Error generating citation suggestions: {e}")
        return []


async def suggest_citations_for_all_draft_claims(
    draft_claims: List[Dict[str, Any]],
    project_id: str,
    max_suggestions_per_claim: int = 2
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Generate citation suggestions for all draft claims.

    Used during draft analysis to provide comprehensive citation suggestions.

    Args:
        draft_claims: List of draft claims
        project_id: Project ID
        max_suggestions_per_claim: Max citations per claim

    Returns:
        Dict mapping claim text to list of suggestions:
        {
            "BERT improves accuracy": [
                {"document_title": "Paper X", "relevance_score": 0.9, ...},
                {"document_title": "Paper Y", "relevance_score": 0.85, ...}
            ],
            ...
        }
    """
    try:
        logger.info(f"[CLAIM-CITATION] Generating citations for {len(draft_claims)} draft claims")

        citations_by_claim = {}

        for i, claim in enumerate(draft_claims):
            claim_text = claim.get("claim_text", "")
            if not claim_text:
                continue

            logger.info(f"[CLAIM-CITATION] Processing claim {i+1}/{len(draft_claims)}")

            suggestions = await suggest_citations_for_draft_claim(
                draft_claim=claim,
                project_id=project_id,
                max_suggestions=max_suggestions_per_claim
            )

            if suggestions:
                citations_by_claim[claim_text] = suggestions

        logger.info(f"[CLAIM-CITATION] Generated citations for {len(citations_by_claim)} claims")

        return citations_by_claim

    except Exception as e:
        logger.error(f"[CLAIM-CITATION] Error generating citations for all claims: {e}")
        return {}

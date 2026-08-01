"""
Draft RAG Integration Service

Integrated search across both draft content and literature database.

Key capabilities:
- Search across both drafts and literature using match_project_content()
- Provide context about content source (draft vs literature)

Requirements: 6.1, 6.2, 6.3, 6.4
"""

from typing import Dict, Any, List, Optional
from app.core.supabase_client import supabase
from app.core.logging_config import get_logger
from app.services.rag_retrieval import embed_query

logger = get_logger(__name__)


# ============================================
# Integrated Search Across Drafts and Literature
# ============================================

def search_project_content(
    project_id: str,
    query: str,
    limit: int = 10,
    include_drafts: bool = True,
    include_literature: bool = True,
    draft_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Search across both draft content and literature database.

    Uses the match_project_content() database function to search
    both draft_chunks and document_chunks tables.

    Args:
        project_id: Project to search within
        query: Search query
        limit: Maximum results to return
        include_drafts: Whether to include draft content
        include_literature: Whether to include literature
        draft_id: Optional draft ID to search within specific draft only

    Returns:
        List of chunks with source information (draft vs literature)

    Validates: Requirement 6.2 - Integrated search
    """
    try:
        # Generate query embedding using server-controlled default model
        embedding_model = "text-embedding-3-large"

        query_embedding = embed_query(query, model=embedding_model)

        # Choose search strategy based on parameters
        if draft_id:
            # Search within specific draft only
            response = supabase.rpc(
                "match_draft_chunks",
                {
                    "query_embedding": query_embedding,
                    "p_draft_id": draft_id,
                    "match_count": limit
                }
            ).execute()

            results = response.data if response.data else []

            # Add source metadata
            for result in results:
                result["source_type"] = "draft"

        elif include_drafts and include_literature:
            # Search across both drafts and literature
            response = supabase.rpc(
                "match_project_content",
                {
                    "query_embedding": query_embedding,
                    "filter_project_id": project_id,
                    "match_count": limit,
                    "match_threshold": 0.0,
                    "include_drafts": True,
                    "filter_draft_id": None
                }
            ).execute()

            results = response.data if response.data else []

        elif include_drafts:
            # Search drafts only
            # Get all drafts in project
            drafts_response = supabase.table("drafts").select("id").eq("project_id", project_id).execute()
            draft_ids = [d["id"] for d in drafts_response.data] if drafts_response.data else []

            if not draft_ids:
                return []

            # Search across all draft chunks in project
            response = supabase.table("draft_chunks").select("*").in_("draft_id", draft_ids).execute()

            # Manual similarity search (simplified - in production would use proper vector search)
            results = response.data if response.data else []
            for result in results:
                result["source_type"] = "draft"

        elif include_literature:
            # Search literature only
            response = supabase.rpc(
                "match_document_chunks",
                {
                    "query_embedding": query_embedding,
                    "proj_id": project_id,  # Fixed: parameter name is proj_id, not p_project_id
                    "match_count": limit
                }
            ).execute()

            results = response.data if response.data else []

            for result in results:
                result["source_type"] = "literature"

        else:
            results = []

        logger.info(f"Found {len(results)} results for query in project {project_id}")

        return results

    except Exception as e:
        logger.error(f"Search failed: {str(e)}")
        raise


def enrich_results_with_metadata(
    results: List[Dict[str, Any]],
    project_id: str
) -> List[Dict[str, Any]]:
    """
    Enrich search results with additional metadata.

    Adds:
    - Document/draft title
    - Section information
    - Source type indicator
    - Relevance badges

    Args:
        results: Raw search results
        project_id: Project identifier

    Returns:
        Enriched results with metadata

    Validates: Requirement 6.3 - Source transparency
    """
    enriched = []

    for result in results:
        source_type = result.get("source_type", "unknown")

        enriched_result = {
            **result,
            "source_type": source_type,
            "source_icon": "📄" if source_type == "draft" else "📚",
            "source_label": "Your Draft" if source_type == "draft" else "Literature"
        }

        # Fetch additional metadata based on source type
        if source_type == "draft":
            draft_id = result.get("draft_id")
            if draft_id:
                draft_response = supabase.table("drafts").select("title, version").eq("id", draft_id).single().execute()
                if draft_response.data:
                    enriched_result["source_title"] = draft_response.data.get("title", "Unknown Draft")
                    enriched_result["draft_version"] = draft_response.data.get("version", 1)

        elif source_type == "literature":
            document_id = result.get("document_id")
            if document_id:
                doc_response = supabase.table("documents").select("title, metadata").eq("id", document_id).single().execute()
                if doc_response.data:
                    enriched_result["source_title"] = doc_response.data.get("title", "Unknown Document")

        enriched.append(enriched_result)

    return enriched

"""
Draft RAG Integration Service

Handles draft ingestion into RAG system and integrated search across
both draft content and literature database.

Key capabilities:
- Ingest draft text into vector database (draft_chunks table)
- Search across both drafts and literature using match_project_content()
- Provide context about content source (draft vs literature)
- Enable draft-aware chat responses

Requirements: 6.1, 6.2, 6.3, 6.4
"""

import datetime
from typing import Dict, Any, List, Optional
from app.core.supabase_client import supabase
from app.core.logging_config import get_logger
from app.services.rag_ingest import chunk_text, embed_chunks
from app.services.rag_retrieval import embed_query

logger = get_logger(__name__)


# ============================================
# Draft Ingestion for RAG
# ============================================

async def ingest_draft_for_rag(draft_id: str, project_id: str) -> Dict[str, Any]:
    """
    Ingest draft into RAG system for semantic search.

    Steps:
    1. Fetch draft and analysis
    2. Extract draft text
    3. Chunk text using same approach as literature
    4. Generate embeddings
    5. Store chunks in draft_chunks table
    6. Update draft metadata

    Args:
        draft_id: Draft identifier
        project_id: Project identifier

    Returns:
        Ingestion statistics

    Validates: Requirement 6.1 - Draft content indexing
    """
    try:
        logger.info(f"Ingesting draft {draft_id} for RAG")

        # 1. Fetch draft
        draft_response = supabase.table("drafts").select("*").eq("id", draft_id).single().execute()

        if not draft_response.data:
            raise ValueError(f"Draft not found: {draft_id}")

        draft = draft_response.data

        # 2. Fetch draft analysis for section information
        analysis_response = supabase.table("draft_analysis").select("*").eq("draft_id", draft_id).single().execute()

        structure = {}
        if analysis_response.data:
            structure = analysis_response.data.get("structure", {})

        # 3. Download and extract draft text
        file_url = draft.get("file_url")
        if not file_url:
            raise ValueError("Draft has no file URL")

        path_parts = file_url.split("/drafts/")
        storage_path = path_parts[1]
        file_bytes = supabase.storage.from_("drafts").download(storage_path)

        from app.services.draft_processing import extract_text
        file_type = draft.get("file_type", "pdf")
        draft_text = extract_text(file_bytes, file_type)

        # 4. Use adaptive chunking based on estimated page count
        from app.services.rag_chunking import get_optimal_chunk_params
        page_count = max(1, len(draft_text.split()) // 300)  # ~300 words/page estimate
        chunk_params = get_optimal_chunk_params(page_count)
        chunk_size = chunk_params["chunk_size"]
        chunk_overlap = chunk_params["overlap"]
        embedding_model = "text-embedding-3-large"

        logger.info(f"Adaptive draft chunking — est. pages: {page_count}, chunk_size: {chunk_size}, overlap: {chunk_overlap}")

        # 5. Chunk the draft text
        chunks = chunk_text(draft_text, max_tokens=chunk_size, overlap_tokens=chunk_overlap)

        if not chunks:
            raise ValueError("Draft chunking produced no chunks")

        # 6. Generate embeddings
        embeddings = embed_chunks(chunks, model=embedding_model)

        # 7. Map chunks to sections (if structure available)
        chunk_sections = assign_chunks_to_sections(chunks, draft_text, structure)

        # 8. Delete existing chunks for this draft (in case of re-ingestion)
        supabase.table("draft_chunks").delete().eq("draft_id", draft_id).execute()

        # 9. Insert chunks into draft_chunks table
        rows = []
        for i, emb in enumerate(embeddings):
            rows.append({
                "draft_id": draft_id,
                "project_id": project_id,
                "chunk_index": i,
                "content": chunks[i],
                "embedding": emb.embedding,
                "section_type": chunk_sections[i] if i < len(chunk_sections) else "unknown"
            })

        # Batch insert
        for row in rows:
            supabase.table("draft_chunks").insert(row).execute()

        # 10. Update draft metadata
        supabase.table("drafts").update({
            "metadata": {
                **draft.get("metadata", {}),
                "rag_ingested": True,
                "rag_ingested_at": datetime.datetime.utcnow().isoformat(),
                "num_chunks": len(chunks),
                "rag_settings_used": {
                    "chunk_size": chunk_size,
                    "chunk_overlap": chunk_overlap,
                    "embedding_model": embedding_model,
                    "adaptive": True
                }
            },
            "updated_at": datetime.datetime.utcnow().isoformat()
        }).eq("id", draft_id).execute()

        logger.info(f"Draft {draft_id} ingested: {len(chunks)} chunks")

        return {
            "message": "Draft successfully ingested for RAG",
            "draft_id": draft_id,
            "num_chunks": len(chunks),
            "total_characters": len(draft_text),
            "rag_settings_used": {
                "chunk_size": chunk_size,
                "chunk_overlap": chunk_overlap,
                "embedding_model": embedding_model,
                "adaptive": True
            }
        }

    except Exception as e:
        logger.error(f"Draft RAG ingestion failed: {str(e)}")
        raise


def assign_chunks_to_sections(
    chunks: List[str],
    full_text: str,
    structure: Dict[str, Any]
) -> List[str]:
    """
    Assign each chunk to a section type based on its position in the text.

    Uses section boundaries from draft structure analysis to determine
    which section each chunk belongs to.

    Args:
        chunks: List of text chunks
        full_text: Full draft text
        structure: Document structure with sections

    Returns:
        List of section types (same length as chunks)
    """
    chunk_sections = []
    sections = structure.get("sections", [])

    if not sections:
        # No structure available, mark all as unknown
        return ["unknown"] * len(chunks)

    # Find position of each chunk in full text
    for chunk in chunks:
        chunk_start = full_text.find(chunk)

        if chunk_start == -1:
            chunk_sections.append("unknown")
            continue

        # Find which section this chunk belongs to
        section_type = "unknown"
        for section in sections:
            section_title = section.get("title", "")
            # Simple heuristic: find section title in text
            title_pos = full_text.find(section_title)

            if title_pos != -1 and title_pos <= chunk_start:
                # This section starts before the chunk
                section_type = section.get("type", "unknown")

        chunk_sections.append(section_type)

    return chunk_sections


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


# ============================================
# Draft-Aware Context Building
# ============================================

def build_draft_aware_context(
    results: List[Dict[str, Any]],
    include_source_labels: bool = True
) -> str:
    """
    Build context string for RAG responses with clear source attribution.

    Formats chunks with visual indicators of whether content comes from
    user's draft or literature database.

    Args:
        results: Search results with source metadata
        include_source_labels: Whether to include source type labels

    Returns:
        Formatted context string for LLM prompt

    Validates: Requirement 6.4 - Draft-aware responses
    """
    context_parts = []

    for idx, result in enumerate(results, 1):
        source_type = result.get("source_type", "unknown")
        source_icon = result.get("source_icon", "")
        source_title = result.get("source_title", result.get("document_title", "Unknown"))

        if include_source_labels:
            if source_type == "draft":
                label = f"[{idx}] {source_icon} FROM YOUR DRAFT: {source_title}"
            else:
                label = f"[{idx}] {source_icon} FROM LITERATURE: {source_title}"
        else:
            label = f"[{idx}] {source_title}"

        content = result.get("content", "")
        section = result.get("section_type", "")

        if section and section != "unknown":
            label += f" (Section: {section})"

        context_parts.append(f"{label}\n{content}")

    return "\n\n---\n\n".join(context_parts)


def get_draft_context_for_query(
    project_id: str,
    query: str,
    draft_id: Optional[str] = None,
    max_results: int = 5
) -> Dict[str, Any]:
    """
    Get draft-aware context for a query.

    Searches across both drafts and literature, enriches results with
    metadata, and builds formatted context for LLM.

    Args:
        project_id: Project to search within
        query: User query
        draft_id: Optional specific draft to search
        max_results: Maximum results to return

    Returns:
        Context dictionary with formatted context and source metadata

    Validates: Requirements 6.2, 6.3, 6.4
    """
    try:
        # Search across project content
        results = search_project_content(
            project_id=project_id,
            query=query,
            limit=max_results,
            draft_id=draft_id
        )

        # Enrich with metadata
        enriched_results = enrich_results_with_metadata(results, project_id)

        # Build formatted context
        context_text = build_draft_aware_context(enriched_results)

        # Generate source summary
        draft_sources = [r for r in enriched_results if r.get("source_type") == "draft"]
        literature_sources = [r for r in enriched_results if r.get("source_type") == "literature"]

        return {
            "context": context_text,
            "sources": enriched_results,
            "summary": {
                "total_results": len(enriched_results),
                "from_drafts": len(draft_sources),
                "from_literature": len(literature_sources)
            }
        }

    except Exception as e:
        logger.error(f"Failed to get draft context: {str(e)}")
        raise

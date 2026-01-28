"""
RAG Retrieval Service

Handles semantic search and retrieval of relevant document chunks
using pgvector similarity search.
"""

from openai import OpenAI
from app.core.supabase_client import supabase
from app.core.config import settings
from typing import List, Dict, Any


def embed_query(query: str, model: str = "text-embedding-3-small") -> List[float]:
    """
    Generate embedding for a query string using OpenAI API.

    Args:
        query: Query text to embed
        model: OpenAI embedding model to use (must match what was used during ingestion)

    Returns:
        Embedding vector as list of floats (always 1536 dimensions)

    Note:
        Both models return 1536-dimensional embeddings for pgvector compatibility.
        text-embedding-3-large uses dimension reduction from its native 3072 dimensions.
    """
    if not settings.OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY not configured in environment variables")

    client = OpenAI(api_key=settings.OPENAI_API_KEY)

    response = client.embeddings.create(
        model=model,
        input=query,
        dimensions=1536  # Fixed at 1536 for pgvector index compatibility
    )

    return response.data[0].embedding


def retrieve_relevant_chunks(
    project_id: str,
    query: str,
    limit: int = None,
    document_id: str = None,
    similarity_threshold: float = None
) -> List[Dict[str, Any]]:
    """
    Retrieve relevant document chunks for a query using vector similarity search.

    Args:
        project_id: UUID of the project to search within
        query: User's query text
        limit: Maximum number of chunks to retrieve (if None, uses project settings)
        document_id: Optional UUID to search within a single document only
        similarity_threshold: Minimum similarity score to include (if None, uses project settings)

    Returns:
        List of matching chunks with similarity scores and document metadata
    """
    # Fetch project RAG settings
    project_record = supabase.table("projects").select("rag_settings").eq("id", project_id).single().execute()
    rag_settings = project_record.data.get("rag_settings", {}) if project_record.data else {}

    # Use provided values or fall back to project settings
    embedding_model = rag_settings.get("embedding_model", "text-embedding-3-small")
    max_chunks = limit if limit is not None else rag_settings.get("max_chunks", 5)
    min_similarity = similarity_threshold if similarity_threshold is not None else rag_settings.get("similarity_threshold", 0.0)

    # Generate embedding for the query (using same model as ingestion)
    query_embedding = embed_query(query, model=embedding_model)

    # Choose function based on whether we're searching a single doc or whole project
    if document_id:
        # Search within single document
        response = supabase.rpc(
            "match_single_document_chunks",
            {
                "query_embedding": query_embedding,
                "doc_id": document_id,
                "match_count": max_chunks
            }
        ).execute()
    else:
        # Search across all documents in project
        response = supabase.rpc(
            "match_document_chunks",
            {
                "query_embedding": query_embedding,
                "proj_id": project_id,
                "match_count": max_chunks
            }
        ).execute()

    chunks = response.data if response.data else []

    # Apply similarity threshold filter if specified
    if min_similarity > 0.0:
        chunks = [chunk for chunk in chunks if chunk.get("similarity", 0.0) >= min_similarity]

    return chunks


def retrieve_relevant_chunks_with_drafts(
    project_id: str,
    query: str,
    limit: int = 5,
    include_drafts: bool = True,
    include_literature: bool = True,
    draft_id: str = None
) -> List[Dict[str, Any]]:
    """
    Retrieve relevant chunks from both drafts and literature.

    Enhanced version of retrieve_relevant_chunks that supports draft-aware search.

    Args:
        project_id: UUID of the project to search within
        query: User's query text
        limit: Maximum number of chunks to retrieve
        include_drafts: Whether to include draft content
        include_literature: Whether to include literature
        draft_id: Optional UUID to search within a specific draft only

    Returns:
        List of matching chunks with source metadata

    Validates: Requirement 6.2 - Integrated search
    """
    from app.services.draft_rag_integration import search_project_content, enrich_results_with_metadata

    # Use integrated search if drafts are included
    if include_drafts or draft_id:
        results = search_project_content(
            project_id=project_id,
            query=query,
            limit=limit,
            include_drafts=include_drafts,
            include_literature=include_literature,
            draft_id=draft_id
        )

        # Enrich with metadata
        enriched_results = enrich_results_with_metadata(results, project_id)

        return enriched_results

    else:
        # Fall back to literature-only search
        return retrieve_relevant_chunks(
            project_id=project_id,
            query=query,
            limit=limit,
            document_id=None
        )


def generate_rag_answer(
    project_id: str,
    query: str,
    model: str = "gpt-4o",
    max_chunks: int = 5,
    document_id: str = None,
    include_drafts: bool = False,
    draft_id: str = None
) -> Dict[str, Any]:
    """
    Generate an answer to a query using RAG (Retrieval-Augmented Generation).

    Steps:
    1. Retrieve relevant chunks using vector search
    2. Build context from retrieved chunks
    3. Generate answer using OpenAI chat completion

    Args:
        project_id: UUID of the project
        query: User's question
        model: OpenAI model to use for generation (default: gpt-4o)
        max_chunks: Maximum number of chunks to use as context
        document_id: Optional UUID to search within a single document only
        include_drafts: Whether to include draft content in search (default: False for backwards compatibility)
        draft_id: Optional UUID to search within a specific draft only

    Returns:
        Dictionary with answer and context chunks

    Validates: Requirements 6.2, 6.4 - Draft-aware RAG
    """
    if not settings.OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY not configured in environment variables")

    # Retrieve relevant chunks (draft-aware if requested)
    if include_drafts or draft_id:
        chunks = retrieve_relevant_chunks_with_drafts(
            project_id=project_id,
            query=query,
            limit=max_chunks,
            include_drafts=include_drafts,
            include_literature=True,
            draft_id=draft_id
        )
    else:
        chunks = retrieve_relevant_chunks(project_id, query, limit=max_chunks, document_id=document_id)

    if not chunks:
        search_scope = "this document" if document_id else "the project documents"
        if draft_id:
            search_scope = "this draft"
        elif include_drafts:
            search_scope = "your drafts and literature"

        return {
            "answer": f"I couldn't find any relevant information in {search_scope} to answer your question.",
            "context_used": [],
            "num_chunks": 0
        }

    # Build context from chunks with document/draft attribution
    context_parts = []
    for idx, chunk in enumerate(chunks, 1):
        source_type = chunk.get("source_type", "literature")
        source_icon = chunk.get("source_icon", "📚")
        source_title = chunk.get("source_title", chunk.get("document_title", "Unknown"))

        if source_type == "draft":
            label = f"[{idx}] {source_icon} FROM YOUR DRAFT: {source_title}"
        else:
            label = f"[{idx}] {source_icon} FROM LITERATURE: {source_title}"

        context_parts.append(f"{label}\n{chunk['content']}")

    context = "\n\n---\n\n".join(context_parts)

    # Generate answer using OpenAI
    client = OpenAI(api_key=settings.OPENAI_API_KEY)

    # Adjust system prompt based on whether drafts are included
    if include_drafts or draft_id:
        system_prompt = (
            "You are a research assistant helping users with their research drafts. "
            "You have access to both the user's draft content and their literature database. "
            "Answer questions based on the provided context. "
            "IMPORTANT: When citing sources, distinguish between the user's draft and literature. "
            "Use phrases like 'In your draft...' or 'According to [Source]...' to be clear. "
            "If the context doesn't contain enough information, say so. "
            "Use citation numbers [N] to reference specific sources."
        )
    else:
        system_prompt = (
            "You are a research assistant that helps users understand their research documents. "
            "Answer questions based only on the provided context. "
            "If the context doesn't contain enough information to answer the question, say so. "
            "Always cite which parts of the context you used to formulate your answer."
        )

    completion = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": f"Context from research sources:\n\n{context}\n\n---\n\nUser question: {query}"
            }
        ],
        temperature=0.7,
        max_tokens=1000
    )

    return {
        "answer": completion.choices[0].message.content,
        "context_used": chunks,
        "num_chunks": len(chunks),
        "model": model,
        "includes_drafts": include_drafts or (draft_id is not None)
    }

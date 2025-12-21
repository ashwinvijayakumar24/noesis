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


def generate_rag_answer(
    project_id: str,
    query: str,
    model: str = "gpt-4o",
    max_chunks: int = 5,
    document_id: str = None
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

    Returns:
        Dictionary with answer and context chunks
    """
    if not settings.OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY not configured in environment variables")

    # Retrieve relevant chunks
    chunks = retrieve_relevant_chunks(project_id, query, limit=max_chunks, document_id=document_id)

    if not chunks:
        search_scope = "this document" if document_id else "the project documents"
        return {
            "answer": f"I couldn't find any relevant information in {search_scope} to answer your question.",
            "context_used": [],
            "num_chunks": 0
        }

    # Build context from chunks with document attribution
    context_parts = []
    for chunk in chunks:
        doc_title = chunk.get("document_title", "Unknown Document")
        context_parts.append(f"[From: {doc_title}]\n{chunk['content']}")

    context = "\n\n---\n\n".join(context_parts)

    # Generate answer using OpenAI
    client = OpenAI(api_key=settings.OPENAI_API_KEY)

    completion = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a research assistant that helps users understand their research documents. "
                    "Answer questions based only on the provided context. "
                    "If the context doesn't contain enough information to answer the question, say so. "
                    "Always cite which parts of the context you used to formulate your answer."
                )
            },
            {
                "role": "user",
                "content": f"Context from research documents:\n\n{context}\n\n---\n\nUser question: {query}"
            }
        ],
        temperature=0.7,
        max_tokens=1000
    )

    return {
        "answer": completion.choices[0].message.content,
        "context_used": chunks,
        "num_chunks": len(chunks),
        "model": model
    }

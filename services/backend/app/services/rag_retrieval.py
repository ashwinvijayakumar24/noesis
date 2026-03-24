"""
RAG Retrieval Service

Handles semantic search and retrieval of relevant document chunks
using pgvector similarity search.

Enhanced with:
- Hybrid search (semantic + keyword)
- Query expansion
- Result reranking
"""

from app.core.supabase_client import supabase
from app.core.config import settings
from app.core.openai_client import get_openai_client, get_completion_params
from app.services.embedding_cache import get_cached_embedding, cache_embedding
from app.services.retry_utils import retry_openai
from typing import List, Dict, Any
import json


def embed_query(query: str, model: str = "text-embedding-3-large") -> List[float]:
    """
    Generate embedding for a query string using OpenAI API.

    Uses Redis cache to avoid regenerating same embeddings.
    Includes retry logic for resilience.

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

    # Try to get from cache first
    cached = get_cached_embedding(query, model)
    if cached is not None:
        return cached

    # Generate embedding with retry logic
    @retry_openai
    def _generate():
        client = get_openai_client()
        response = client.embeddings.create(
            model=model,
            input=query,
            dimensions=1536  # Fixed at 1536 for pgvector index compatibility
        )
        return response.data[0].embedding

    embedding = _generate()

    # Cache for future use
    cache_embedding(query, embedding, model)

    return embedding


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
    # Server-controlled defaults (no user-adjustable RAG settings)
    embedding_model = "text-embedding-3-large"
    max_chunks = limit if limit is not None else 5
    min_similarity = similarity_threshold if similarity_threshold is not None else 0.0

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
    model: str = "gpt-5.2-chat-latest",
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
    client = get_openai_client()

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

    # Note: Temperature removed - GPT-5.2 models use default temperature=1.0
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
        max_completion_tokens=1000,
        **get_completion_params()  # Enable zero data retention
    )

    return {
        "answer": completion.choices[0].message.content,
        "context_used": chunks,
        "num_chunks": len(chunks),
        "model": model,
        "includes_drafts": include_drafts or (draft_id is not None)
    }


# ================================
# HYBRID SEARCH ENHANCEMENTS
# ================================

def expand_query(query: str) -> List[str]:
    """
    Expand natural language query into academic terminology

    Uses GPT-5.2-mini to generate query variations with academic terms

    Args:
        query: Original user query

    Returns:
        List of expanded query variations
    """
    client = get_openai_client()

    prompt = f"""Given this research query: "{query}"

Generate 3 academic query variations that:
1. Use domain-specific terminology
2. Include common academic phrasings
3. Cover different aspects of the query

Return as JSON array of strings.

Example:
Query: "how do transformers work"
Output: ["transformer architecture attention mechanisms", "self-attention neural networks NLP", "multi-head attention deep learning"]
"""

    try:
        # Note: Temperature removed - GPT-5.2 models use default temperature=1.0
        response = client.chat.completions.create(
            model="gpt-5-mini",
            messages=[{"role": "user", "content": prompt}],
            max_completion_tokens=200,
            **get_completion_params()
        )

        result = json.loads(response.choices[0].message.content)
        variations = result.get("queries", result.get("variations", [query]))

        return [query] + variations[:3]  # Original + 3 variations

    except Exception as e:
        # Fallback: return original query
        return [query]


def keyword_search(
    project_id: str,
    query: str,
    limit: int = 20
) -> List[Dict[str, Any]]:
    """
    Keyword-based search using PostgreSQL full-text search

    Args:
        project_id: Project to search in
        query: Search query
        limit: Maximum results

    Returns:
        List of matching chunks with keyword relevance scores
    """
    # Use PostgreSQL full-text search (ts_rank)
    response = supabase.rpc(
        "keyword_search_chunks",
        {
            "proj_id": project_id,
            "search_query": query,
            "match_count": limit
        }
    ).execute()

    chunks = response.data if response.data else []

    return chunks


def semantic_search(
    project_id: str,
    query: str,
    limit: int = 20
) -> List[Dict[str, Any]]:
    """
    Semantic search using vector similarity

    Args:
        project_id: Project to search in
        query: Search query
        limit: Maximum results

    Returns:
        List of matching chunks with similarity scores
    """
    # Use existing retrieve_relevant_chunks
    return retrieve_relevant_chunks(
        project_id=project_id,
        query=query,
        limit=limit,
        similarity_threshold=0.0  # No threshold, get top N
    )


def hybrid_search(
    project_id: str,
    query: str,
    limit: int = 5,
    semantic_weight: float = 0.7,
    keyword_weight: float = 0.3
) -> List[Dict[str, Any]]:
    """
    Hybrid search combining semantic and keyword search

    Args:
        project_id: Project to search in
        query: Search query
        limit: Final number of results
        semantic_weight: Weight for semantic scores (default 0.7)
        keyword_weight: Weight for keyword scores (default 0.3)

    Returns:
        Ranked list of chunks combining both search methods
    """
    # Expand query for better recall
    query_variations = expand_query(query)

    # Run both searches in parallel
    semantic_results = []
    keyword_results = []

    # Semantic search with query variations
    for q in query_variations:
        results = semantic_search(project_id, q, limit=10)
        semantic_results.extend(results)

    # Keyword search with original query
    keyword_results = keyword_search(project_id, query, limit=20)

    # Merge and score results
    chunk_scores: Dict[str, Dict[str, Any]] = {}

    # Process semantic results
    for chunk in semantic_results:
        chunk_id = chunk.get("id")
        if chunk_id not in chunk_scores:
            chunk_scores[chunk_id] = {
                "chunk": chunk,
                "semantic_score": 0.0,
                "keyword_score": 0.0
            }
        # Similarity score (0-1 range, higher is better)
        similarity = chunk.get("similarity", 0.0)
        chunk_scores[chunk_id]["semantic_score"] = max(
            chunk_scores[chunk_id]["semantic_score"],
            similarity
        )

    # Process keyword results
    for chunk in keyword_results:
        chunk_id = chunk.get("id")
        if chunk_id not in chunk_scores:
            chunk_scores[chunk_id] = {
                "chunk": chunk,
                "semantic_score": 0.0,
                "keyword_score": 0.0
            }
        # Keyword rank score (normalize by position)
        rank = chunk.get("rank", 0.0)
        chunk_scores[chunk_id]["keyword_score"] = max(
            chunk_scores[chunk_id]["keyword_score"],
            rank
        )

    # Calculate combined scores
    scored_results = []
    for chunk_id, scores in chunk_scores.items():
        combined_score = (
            semantic_weight * scores["semantic_score"] +
            keyword_weight * scores["keyword_score"]
        )

        chunk_data = scores["chunk"]
        chunk_data["combined_score"] = combined_score
        chunk_data["semantic_score"] = scores["semantic_score"]
        chunk_data["keyword_score"] = scores["keyword_score"]

        scored_results.append(chunk_data)

    # Sort by combined score
    scored_results.sort(key=lambda x: x["combined_score"], reverse=True)

    # Return top N
    return scored_results[:limit]


def rerank_results(
    chunks: List[Dict[str, Any]],
    query: str,
    top_k: int = 5
) -> List[Dict[str, Any]]:
    """
    Rerank search results using GPT-5.2-mini

    Takes top N results and reranks them based on relevance to query

    Args:
        chunks: List of chunks to rerank
        query: Original query
        top_k: Number of results to return

    Returns:
        Reranked list of chunks
    """
    if len(chunks) <= top_k:
        return chunks

    client = get_openai_client()

    # Prepare chunks for reranking
    chunk_texts = []
    for idx, chunk in enumerate(chunks[:20]):  # Only rerank top 20
        chunk_texts.append(f"[{idx}] {chunk['content'][:500]}")  # Truncate long chunks

    prompt = f"""Given this research query: "{query}"

Rank these text passages by relevance (most relevant first).

Passages:
{chr(10).join(chunk_texts)}

Return the indices of the top {top_k} most relevant passages as a JSON array.
Example: {{"indices": [3, 7, 1, 15, 9]}}
"""

    try:
        # Note: Temperature removed - GPT-5.2 models use default temperature=1.0
        response = client.chat.completions.create(
            model="gpt-5-mini",
            messages=[{"role": "user", "content": prompt}],
            max_completion_tokens=100,
            **get_completion_params()
        )

        result = json.loads(response.choices[0].message.content)
        indices = result.get("indices", list(range(top_k)))

        # Reorder chunks based on indices
        reranked = []
        for idx in indices[:top_k]:
            if 0 <= idx < len(chunks):
                reranked.append(chunks[idx])

        # Fill remaining slots if needed
        while len(reranked) < top_k and len(reranked) < len(chunks):
            for chunk in chunks:
                if chunk not in reranked:
                    reranked.append(chunk)
                    break

        return reranked

    except Exception as e:
        # Fallback: return original order
        return chunks[:top_k]


def retrieve_relevant_chunks_hybrid(
    project_id: str,
    query: str,
    limit: int = 5,
    use_reranking: bool = True
) -> List[Dict[str, Any]]:
    """
    Enhanced retrieval using hybrid search + reranking

    This is the recommended retrieval method for best quality

    Args:
        project_id: Project to search in
        query: Search query
        limit: Final number of results
        use_reranking: Whether to rerank results with LLM

    Returns:
        High-quality ranked results
    """
    # Step 1: Hybrid search (get top 20)
    hybrid_results = hybrid_search(
        project_id=project_id,
        query=query,
        limit=20,
        semantic_weight=0.7,
        keyword_weight=0.3
    )

    # Step 2: Rerank to get best N
    if use_reranking and len(hybrid_results) > limit:
        final_results = rerank_results(hybrid_results, query, top_k=limit)
    else:
        final_results = hybrid_results[:limit]

    return final_results

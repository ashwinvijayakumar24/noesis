"""
Enhanced RAG Retrieval Service with Hybrid Search, Reranking, and Multi-Query

This module implements the RAG pipeline optimization plan with:
- Priority 1: Hybrid retrieval (vector + keyword search)
- Priority 2: Reranking layer (Cohere API)
- Priority 3: Multi-query expansion with reciprocal rank fusion
- Priority 4: Section-aware context structuring
"""

from app.core.supabase_client import supabase
from app.core.config import settings
from app.core.openai_client import get_openai_client, get_completion_params
from typing import List, Dict, Any, Tuple, Optional
import json
import logging

logger = logging.getLogger(__name__)

# ============================================
# CONFIGURATION
# ============================================

HYBRID_SEARCH_CONFIG = {
    "enabled": True,
    "default_semantic_weight": 0.7,
    "default_keyword_weight": 0.3,
    "fallback_to_pure_semantic": True,
}

RERANKING_CONFIG = {
    "enabled": True,
    "provider": "cohere",  # Options: "cohere", "cross_encoder"
    "model": "rerank-english-v3.0",
    "rerank_candidates": 20,  # Retrieve 20, rerank to top 5
}

MULTI_QUERY_CONFIG = {
    "enabled": True,
    "num_variants": 3,
    "use_llm_expansion": True,  # LLM-based vs rule-based
    "rrf_k": 60,  # Reciprocal Rank Fusion constant
}


# ============================================
# HELPER FUNCTIONS
# ============================================

def embed_query(query: str, model: str = "text-embedding-3-large") -> List[float]:
    """
    Generate embedding for a query string using OpenAI API.

    Args:
        query: Query text to embed
        model: OpenAI embedding model to use (must match what was used during ingestion)

    Returns:
        Embedding vector as list of floats (always 1536 dimensions)
    """
    if not settings.OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY not configured in environment variables")

    client = get_openai_client()

    response = client.embeddings.create(
        model=model,
        input=query,
        dimensions=1536  # Fixed at 1536 for pgvector index compatibility
    )

    return response.data[0].embedding


def get_hybrid_weights(query: str) -> Tuple[float, float]:
    """
    Adjust semantic/keyword weights based on query characteristics.

    Returns:
        Tuple of (semantic_weight, keyword_weight)
    """
    # If query contains exact quotes, prioritize keyword search
    if '"' in query or "'" in query:
        return (0.5, 0.5)  # Equal weights

    # If query is very short (1-2 words), prioritize keyword
    if len(query.split()) <= 2:
        return (0.6, 0.4)

    # If query contains technical acronyms, boost keyword
    has_acronyms = any(word.isupper() and len(word) > 1 for word in query.split())
    if has_acronyms:
        return (0.6, 0.4)

    # Default: semantic-heavy
    return (
        HYBRID_SEARCH_CONFIG["default_semantic_weight"],
        HYBRID_SEARCH_CONFIG["default_keyword_weight"]
    )


# ============================================
# PRIORITY 1: HYBRID RETRIEVAL (VECTOR + KEYWORD)
# ============================================

def retrieve_relevant_chunks_hybrid(
    project_id: str,
    query: str,
    limit: int = 5,
    semantic_weight: float = None,
    keyword_weight: float = None,
    document_id: str = None,
    include_drafts: bool = False,
    draft_id: str = None
) -> List[Dict[str, Any]]:
    """
    Hybrid retrieval combining semantic search + keyword search.

    Args:
        project_id: UUID of the project to search within
        query: User's query text
        limit: Maximum number of chunks to retrieve (default: 5)
        semantic_weight: Weight for vector similarity (default: adaptive based on query)
        keyword_weight: Weight for keyword/BM25 rank (default: adaptive based on query)
        document_id: Optional UUID to search within a single document only
        include_drafts: Whether to include draft content in search
        draft_id: Optional UUID to search within a specific draft only

    Returns:
        List of matching chunks with hybrid scores
    """
    if not HYBRID_SEARCH_CONFIG["enabled"]:
        # Fallback to pure semantic search
        logger.info("[Hybrid Search] Disabled, falling back to pure semantic search")
        from app.services.rag_retrieval import retrieve_relevant_chunks, retrieve_relevant_chunks_with_drafts
        if include_drafts or draft_id:
            return retrieve_relevant_chunks_with_drafts(
                project_id=project_id,
                query=query,
                limit=limit,
                include_drafts=include_drafts,
                draft_id=draft_id
            )
        else:
            return retrieve_relevant_chunks(
                project_id=project_id,
                query=query,
                limit=limit,
                document_id=document_id
            )

    # Determine optimal weights based on query characteristics
    if semantic_weight is None or keyword_weight is None:
        semantic_weight, keyword_weight = get_hybrid_weights(query)

    logger.info(
        f"[Hybrid Search] Query: '{query[:50]}...' | "
        f"Weights: semantic={semantic_weight:.2f}, keyword={keyword_weight:.2f}"
    )

    # Generate query embedding for semantic search
    query_embedding = embed_query(query, model="text-embedding-3-large")

    # Get more candidates for reranking (if enabled)
    candidate_count = RERANKING_CONFIG["rerank_candidates"] if RERANKING_CONFIG["enabled"] else limit

    try:
        # Call unified hybrid search RPC function
        response = supabase.rpc(
            "hybrid_search_project_content",
            {
                "query_text": query,
                "query_embedding": query_embedding,
                "proj_id": project_id,
                "match_count": candidate_count,
                "include_drafts": include_drafts,
                "include_literature": not (draft_id is not None and not include_drafts),  # If specific draft, exclude literature
                "specific_draft_id": draft_id,
                "semantic_weight": semantic_weight,
                "keyword_weight": keyword_weight
            }
        ).execute()

        chunks = response.data if response.data else []

        # Log hybrid scores for debugging
        logger.info(
            f"[Hybrid Search] Retrieved {len(chunks)} chunks "
            f"(semantic_weight={semantic_weight}, keyword_weight={keyword_weight})"
        )
        for i, chunk in enumerate(chunks[:3], 1):
            logger.debug(
                f"  {i}. {chunk.get('source_title', 'Unknown')[:50]}... | "
                f"Semantic: {chunk.get('semantic_similarity', 0):.3f} | "
                f"Keyword: {chunk.get('keyword_rank', 0):.3f} | "
                f"Combined: {chunk.get('combined_score', 0):.3f}"
            )

        return chunks[:limit] if not RERANKING_CONFIG["enabled"] else chunks

    except Exception as e:
        logger.error(f"[Hybrid Search] Error: {e}")
        if HYBRID_SEARCH_CONFIG["fallback_to_pure_semantic"]:
            logger.info("[Hybrid Search] Falling back to pure semantic search")
            from app.services.rag_retrieval import retrieve_relevant_chunks, retrieve_relevant_chunks_with_drafts
            if include_drafts or draft_id:
                return retrieve_relevant_chunks_with_drafts(
                    project_id=project_id,
                    query=query,
                    limit=limit,
                    include_drafts=include_drafts,
                    draft_id=draft_id
                )
            else:
                return retrieve_relevant_chunks(
                    project_id=project_id,
                    query=query,
                    limit=limit,
                    document_id=document_id
                )
        else:
            raise


# ============================================
# PRIORITY 2: RERANKING LAYER
# ============================================

def rerank_chunks_cohere(
    query: str,
    chunks: List[Dict[str, Any]],
    top_n: int = 5,
    model: str = "rerank-english-v3.0"
) -> List[Dict[str, Any]]:
    """
    Rerank chunks using Cohere Rerank API.

    Args:
        query: User's query text
        chunks: List of chunk dictionaries with 'content' field
        top_n: Number of top results to return
        model: Cohere rerank model to use

    Returns:
        Reranked chunks (top_n results) with rerank_score added
    """
    if not settings.COHERE_API_KEY:
        logger.warning("[Reranking] COHERE_API_KEY not configured, skipping reranking")
        return chunks[:top_n]

    if len(chunks) <= top_n:
        logger.info(f"[Reranking] Only {len(chunks)} chunks, no reranking needed")
        return chunks

    try:
        import cohere
        co = cohere.Client(api_key=settings.COHERE_API_KEY)

        # Prepare documents for reranking
        documents = [chunk['content'] for chunk in chunks]

        logger.info(f"[Reranking] Reranking {len(documents)} chunks with Cohere {model}")

        # Call Cohere Rerank API
        results = co.rerank(
            query=query,
            documents=documents,
            top_n=top_n,
            model=model,
            return_documents=True
        )

        # Map reranked results back to original chunks
        reranked_chunks = []
        for rank, result in enumerate(results.results, 1):
            original_chunk = chunks[result.index].copy()
            original_chunk['rerank_score'] = result.relevance_score
            original_chunk['rerank_position'] = rank
            original_chunk['original_position'] = result.index + 1
            reranked_chunks.append(original_chunk)

        logger.info(
            f"[Reranking] Reranked {len(chunks)} → {len(reranked_chunks)} chunks "
            f"(top score: {reranked_chunks[0]['rerank_score']:.3f})"
        )

        # Log reranking impact
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("[Reranking] Before:")
            for i, chunk in enumerate(chunks[:3], 1):
                logger.debug(f"  {i}. {chunk.get('source_title', 'Unknown')[:40]}...")

            logger.debug("[Reranking] After:")
            for i, chunk in enumerate(reranked_chunks[:3], 1):
                logger.debug(
                    f"  {i}. {chunk.get('source_title', 'Unknown')[:40]}... "
                    f"(was #{chunk.get('original_position')})"
                )

        return reranked_chunks

    except Exception as e:
        logger.error(f"[Reranking] Error: {e}")
        logger.warning("[Reranking] Falling back to original order")
        return chunks[:top_n]


def retrieve_with_reranking(
    project_id: str,
    query: str,
    limit: int = 5,
    include_drafts: bool = False,
    draft_id: str = None
) -> List[Dict[str, Any]]:
    """
    Retrieve + rerank for maximum precision.

    Pipeline:
    1. Hybrid search retrieves top 20 candidates
    2. Reranker scores all 20 candidates
    3. Return top 5 reranked results
    """
    # Step 1: Get broader set of candidates
    candidates = retrieve_relevant_chunks_hybrid(
        project_id=project_id,
        query=query,
        limit=RERANKING_CONFIG["rerank_candidates"],
        include_drafts=include_drafts,
        draft_id=draft_id
    )

    if not RERANKING_CONFIG["enabled"] or len(candidates) <= limit:
        return candidates[:limit]

    # Step 2: Rerank candidates
    reranked_chunks = rerank_chunks_cohere(
        query=query,
        chunks=candidates,
        top_n=limit,
        model=RERANKING_CONFIG["model"]
    )

    return reranked_chunks


# ============================================
# PRIORITY 3: MULTI-QUERY EXPANSION
# ============================================

async def expand_query_llm(
    original_query: str,
    num_variants: int = 3,
    model: str = "gpt-5-mini"
) -> List[str]:
    """
    Generate query variants using LLM for multi-perspective retrieval.

    Example:
    Input: "How does BERT improve accuracy?"
    Output:
    - "BERT model performance improvements"
    - "Bidirectional encoder transformer accuracy gains"
    - "Pre-training impact on classification tasks"
    """
    client = get_openai_client()

    prompt = f"""Generate {num_variants} alternative search queries for academic literature.

Original query: "{original_query}"

Requirements:
1. Use academic terminology and synonyms
2. Rephrase with different keyword emphasis
3. Include related concepts and techniques
4. Keep queries focused and specific

Return ONLY a JSON object with a "queries" array:
{{"queries": ["variant 1", "variant 2", "variant 3"]}}"""

    try:
        # Note: Temperature removed - GPT-5.2 models use default temperature=1.0
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_completion_tokens=200,
            **get_completion_params()
        )

        result = json.loads(response.choices[0].message.content)
        variants = result.get("queries", [original_query])

        # Always include original query
        if original_query not in variants:
            variants = [original_query] + variants

        logger.info(f"[Query Expansion] Generated {len(variants)} variants: {variants}")
        return variants[:num_variants + 1]

    except Exception as e:
        logger.error(f"[Query Expansion] Error: {e}")
        return [original_query]


def expand_query_rules(
    query: str,
    max_variants: int = 3
) -> List[str]:
    """
    Rule-based query expansion using synonym dictionaries.

    Pros: Fast, no API cost, deterministic
    Cons: Limited to predefined rules
    """
    variants = [query]  # Always include original

    # Academic synonym mapping
    ACADEMIC_SYNONYMS = {
        "improve": ["enhance", "optimize", "boost"],
        "accuracy": ["performance", "effectiveness", "precision"],
        "method": ["approach", "technique", "methodology"],
        "model": ["architecture", "framework", "system"],
        "training": ["optimization", "learning", "fine-tuning"],
        "analysis": ["examination", "investigation", "assessment"],
        "data": ["dataset", "corpus", "collection"],
        "result": ["finding", "outcome", "output"],
        "evaluation": ["assessment", "validation", "testing"],
        "proposed": ["presented", "introduced", "developed"],
    }

    # Replace keywords with synonyms
    words = query.lower().split()
    for word in words:
        if word in ACADEMIC_SYNONYMS:
            for synonym in ACADEMIC_SYNONYMS[word][:2]:  # Use top 2 synonyms
                variant = query.lower().replace(word, synonym)
                if variant not in variants:
                    variants.append(variant)
                    if len(variants) >= max_variants + 1:
                        return variants

    return variants[:max_variants + 1]


async def retrieve_with_multi_query(
    project_id: str,
    query: str,
    limit: int = 5,
    num_query_variants: int = 3,
    use_llm_expansion: bool = True,
    include_drafts: bool = False,
    draft_id: str = None
) -> List[Dict[str, Any]]:
    """
    Multi-query retrieval with reciprocal rank fusion.

    Pipeline:
    1. Expand query into 3 variants
    2. Search with each variant (parallel)
    3. Merge results using reciprocal rank fusion
    4. Return top-k fused results
    """
    if not MULTI_QUERY_CONFIG["enabled"]:
        logger.info("[Multi-Query] Disabled, using single query")
        return retrieve_with_reranking(
            project_id=project_id,
            query=query,
            limit=limit,
            include_drafts=include_drafts,
            draft_id=draft_id
        )

    # Step 1: Generate query variants
    if use_llm_expansion:
        query_variants = await expand_query_llm(query, num_query_variants)
    else:
        query_variants = expand_query_rules(query, num_query_variants)

    logger.info(f"[Multi-Query] Searching with {len(query_variants)} query variants")

    # Step 2: Search with all variants
    results_per_query = []
    for variant in query_variants:
        results = retrieve_with_reranking(
            project_id=project_id,
            query=variant,
            limit=limit * 2,  # Get more candidates per query
            include_drafts=include_drafts,
            draft_id=draft_id
        )
        results_per_query.append(results)

    # Step 3: Reciprocal Rank Fusion (RRF)
    # Formula: score(chunk) = sum(1 / (k + rank_in_query_i)) for all queries
    k = MULTI_QUERY_CONFIG["rrf_k"]
    chunk_scores = {}

    for query_idx, results in enumerate(results_per_query):
        for rank, chunk in enumerate(results, start=1):
            chunk_id = chunk['id']
            rrf_score = 1 / (k + rank)

            if chunk_id not in chunk_scores:
                chunk_scores[chunk_id] = {
                    'chunk': chunk,
                    'rrf_score': 0.0,
                    'query_ranks': []
                }

            chunk_scores[chunk_id]['rrf_score'] += rrf_score
            chunk_scores[chunk_id]['query_ranks'].append((query_idx, rank))

    # Step 4: Sort by RRF score and return top-k
    fused_chunks = sorted(
        chunk_scores.values(),
        key=lambda x: x['rrf_score'],
        reverse=True
    )

    final_results = []
    for item in fused_chunks[:limit]:
        chunk = item['chunk'].copy()
        chunk['rrf_score'] = item['rrf_score']
        chunk['query_ranks'] = item['query_ranks']
        final_results.append(chunk)

    top_scores = [f"{item['rrf_score']:.3f}" for item in fused_chunks[:3]]
    logger.info(
        f"[Multi-Query] Fused {len(chunk_scores)} unique chunks → "
        f"Top {limit} results (RRF scores: {top_scores})"
    )

    return final_results


# ============================================
# PRIORITY 4: SECTION-AWARE CONTEXT STRUCTURING
# ============================================

def enrich_chunk_metadata(chunk: Dict[str, Any]) -> Dict[str, Any]:
    """Add structured metadata to chunk for context-aware prompting."""

    metadata = chunk.get('metadata', {})

    # Extract section information
    section_type = metadata.get('section_type', 'unknown')
    section_title = metadata.get('section_title', 'Unknown')

    # Determine content type based on section
    content_type = {
        'abstract': 'summary',
        'introduction': 'background',
        'methods': 'methodology',
        'methodology': 'methodology',
        'results': 'empirical_evidence',
        'discussion': 'interpretation',
        'conclusion': 'synthesis',
        'related_work': 'comparative_context',
        'literature_review': 'comparative_context'
    }.get(section_type, 'general')

    chunk['enriched_metadata'] = {
        'section_type': section_type,
        'section_title': section_title,
        'content_type': content_type,
        'source_type': chunk.get('source_type', 'literature'),
        'similarity_score': chunk.get('semantic_similarity', chunk.get('similarity', 0.0)),
        'rerank_score': chunk.get('rerank_score'),
        'combined_score': chunk.get('combined_score'),
        'rrf_score': chunk.get('rrf_score'),
        'source_title': chunk.get('source_title', chunk.get('document_title', 'Unknown'))
    }

    return chunk


def format_chunk_citation(chunk: Dict[str, Any], citation_number: int) -> str:
    """Format single chunk with structured metadata."""
    meta = chunk.get('enriched_metadata', {})

    source_label = "YOUR DRAFT" if meta.get('source_type') == 'draft' else "LITERATURE"
    source_icon = "📝" if meta.get('source_type') == 'draft' else "📚"

    # Build relevance indicator
    relevance_parts = []
    if meta.get('rerank_score'):
        relevance_parts.append(f"Rerank: {meta['rerank_score']:.3f}")
    if meta.get('rrf_score'):
        relevance_parts.append(f"RRF: {meta['rrf_score']:.3f}")
    if meta.get('combined_score'):
        relevance_parts.append(f"Score: {meta['combined_score']:.3f}")
    elif meta.get('similarity_score'):
        relevance_parts.append(f"Similarity: {meta['similarity_score']:.3f}")

    relevance_str = " | ".join(relevance_parts) if relevance_parts else "N/A"

    section_info = f"{meta.get('section_title', 'Unknown')} ({meta.get('section_type', 'unknown')})"

    return f"""[{citation_number}] {source_icon} {source_label}: {meta.get('source_title', 'Unknown')}
└─ Section: {section_info}
└─ Relevance: {relevance_str}
Content:
{chunk['content']}"""


def format_context_structured(
    query: str,
    chunks: List[Dict[str, Any]],
    task_type: str = "general_chat"
) -> str:
    """
    Format retrieved chunks with structure for LLM reasoning.

    Args:
        query: User's query
        chunks: Retrieved chunks
        task_type: "general_chat", "claim_assessment", "gap_detection", "citation_suggestion"

    Returns:
        Structured context string
    """
    # Enrich all chunks with metadata
    enriched_chunks = [enrich_chunk_metadata(chunk) for chunk in chunks]

    # Group chunks by content type
    grouped_chunks = {
        'methodology': [],
        'empirical_evidence': [],
        'background': [],
        'comparative_context': [],
        'interpretation': [],
        'summary': [],
        'synthesis': [],
        'general': []
    }

    for chunk in enriched_chunks:
        content_type = chunk['enriched_metadata'].get('content_type', 'general')
        grouped_chunks[content_type].append(chunk)

    # Build structured context
    context_parts = []

    # Header
    context_parts.append(f"=== QUERY ===\n{query}\n")

    # Methodology context (if available)
    if grouped_chunks['methodology']:
        context_parts.append("\n=== METHODOLOGY CONTEXT ===")
        for idx, chunk in enumerate(grouped_chunks['methodology'][:2], 1):
            context_parts.append(format_chunk_citation(chunk, idx))

    # Empirical evidence (if available)
    if grouped_chunks['empirical_evidence']:
        context_parts.append("\n=== EMPIRICAL EVIDENCE ===")
        for idx, chunk in enumerate(grouped_chunks['empirical_evidence'][:3], 1):
            context_parts.append(format_chunk_citation(chunk, idx + 10))

    # Background & related work
    background_chunks = grouped_chunks['background'] + grouped_chunks['comparative_context']
    if background_chunks:
        context_parts.append("\n=== BACKGROUND & RELATED WORK ===")
        for idx, chunk in enumerate(background_chunks[:2], 1):
            context_parts.append(format_chunk_citation(chunk, idx + 20))

    # Summary and synthesis
    summary_chunks = grouped_chunks['summary'] + grouped_chunks['synthesis']
    if summary_chunks:
        context_parts.append("\n=== SUMMARY & SYNTHESIS ===")
        for idx, chunk in enumerate(summary_chunks[:2], 1):
            context_parts.append(format_chunk_citation(chunk, idx + 30))

    # General context (everything else)
    other_chunks = grouped_chunks['interpretation'] + grouped_chunks['general']
    if other_chunks:
        context_parts.append("\n=== ADDITIONAL CONTEXT ===")
        for idx, chunk in enumerate(other_chunks[:2], 1):
            context_parts.append(format_chunk_citation(chunk, idx + 40))

    return "\n".join(context_parts)


# ============================================
# STRUCTURED RAG SYSTEM PROMPT
# ============================================

STRUCTURED_RAG_SYSTEM_PROMPT = """You are an expert research assistant with access to structured academic context.

The context below is organized by content type:
- **METHODOLOGY CONTEXT**: How research was conducted
- **EMPIRICAL EVIDENCE**: Experimental results and findings
- **BACKGROUND & RELATED WORK**: Prior research and comparisons
- **SUMMARY & SYNTHESIS**: High-level overviews and conclusions
- **ADDITIONAL CONTEXT**: Interpretation and discussion

When answering:
1. Reference sources using [N] citations
2. Distinguish between methodology, evidence, and interpretation
3. For claims, cite EMPIRICAL EVIDENCE preferentially
4. For methods questions, cite METHODOLOGY CONTEXT
5. Always note the section type when relevant (e.g., "According to the Results section of [3]...")

If the query asks about:
- **Methods**: Focus on METHODOLOGY CONTEXT
- **Results/Performance**: Focus on EMPIRICAL EVIDENCE
- **Related Work**: Focus on BACKGROUND & RELATED WORK
- **Interpretation**: Synthesize across all context types

Be specific and cite sources precisely."""


# ============================================
# MAIN RETRIEVAL FUNCTION (ALL OPTIMIZATIONS)
# ============================================

async def retrieve_relevant_chunks_optimized(
    project_id: str,
    query: str,
    limit: int = 5,
    enable_hybrid: bool = True,
    enable_reranking: bool = True,
    enable_multi_query: bool = True,
    include_drafts: bool = False,
    draft_id: str = None
) -> Dict[str, Any]:
    """
    Main retrieval function with all RAG optimizations enabled.

    Returns:
        Dict with:
            - chunks: Retrieved chunks
            - context_structured: Structured context string
            - system_prompt: Structured RAG system prompt
            - metadata: Retrieval metadata (timings, counts, etc.)
    """
    import time

    start_time = time.time()
    metadata = {}

    # Apply optimizations based on flags
    if enable_multi_query and MULTI_QUERY_CONFIG["enabled"]:
        chunks = await retrieve_with_multi_query(
            project_id=project_id,
            query=query,
            limit=limit,
            include_drafts=include_drafts,
            draft_id=draft_id
        )
        metadata['retrieval_method'] = 'multi_query_rrf'
    elif enable_reranking and RERANKING_CONFIG["enabled"]:
        chunks = retrieve_with_reranking(
            project_id=project_id,
            query=query,
            limit=limit,
            include_drafts=include_drafts,
            draft_id=draft_id
        )
        metadata['retrieval_method'] = 'hybrid_rerank'
    elif enable_hybrid and HYBRID_SEARCH_CONFIG["enabled"]:
        chunks = retrieve_relevant_chunks_hybrid(
            project_id=project_id,
            query=query,
            limit=limit,
            include_drafts=include_drafts,
            draft_id=draft_id
        )
        metadata['retrieval_method'] = 'hybrid_search'
    else:
        # Fallback to basic retrieval
        from app.services.rag_retrieval import retrieve_relevant_chunks_with_drafts
        chunks = retrieve_relevant_chunks_with_drafts(
            project_id=project_id,
            query=query,
            limit=limit,
            include_drafts=include_drafts,
            draft_id=draft_id
        )
        metadata['retrieval_method'] = 'semantic_only'

    # Format structured context
    context_structured = format_context_structured(query, chunks)

    retrieval_time = time.time() - start_time

    metadata.update({
        'num_chunks_retrieved': len(chunks),
        'retrieval_time_seconds': round(retrieval_time, 3),
        'hybrid_enabled': enable_hybrid and HYBRID_SEARCH_CONFIG["enabled"],
        'reranking_enabled': enable_reranking and RERANKING_CONFIG["enabled"],
        'multi_query_enabled': enable_multi_query and MULTI_QUERY_CONFIG["enabled"],
    })

    logger.info(
        f"[RAG Optimized] Retrieved {len(chunks)} chunks in {retrieval_time:.3f}s "
        f"(method: {metadata['retrieval_method']})"
    )

    return {
        'chunks': chunks,
        'context_structured': context_structured,
        'system_prompt': STRUCTURED_RAG_SYSTEM_PROMPT,
        'metadata': metadata
    }

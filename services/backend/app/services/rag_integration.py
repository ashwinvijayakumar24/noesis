"""
RAG Integration Layer - Gradual Rollout Controller

This module provides a unified interface for RAG retrieval with feature flags
to enable gradual rollout of optimizations.
"""

from app.core.config import settings
from typing import List, Dict, Any, Optional
import logging
import os

logger = logging.getLogger(__name__)

# ============================================
# FEATURE FLAGS FOR GRADUAL ROLLOUT
# ============================================

class RAGOptimizationFlags:
    """
    Feature flags for RAG optimizations.

    Set via environment variables for gradual rollout:
    - RAG_OPTIMIZATION_ENABLED: Master switch (default: True)
    - RAG_HYBRID_SEARCH_ENABLED: Hybrid search (default: True)
    - RAG_RERANKING_ENABLED: Reranking layer (default: True if COHERE_API_KEY set)
    - RAG_MULTI_QUERY_ENABLED: Multi-query expansion (default: False, expensive)
    - RAG_ROLLOUT_PERCENTAGE: Percentage of users to enable (default: 100)
    """

    @staticmethod
    def is_optimization_enabled() -> bool:
        """Check if RAG optimization is enabled globally."""
        return os.getenv("RAG_OPTIMIZATION_ENABLED", "true").lower() == "true"

    @staticmethod
    def is_hybrid_search_enabled() -> bool:
        """Check if hybrid search is enabled."""
        if not RAGOptimizationFlags.is_optimization_enabled():
            return False
        return os.getenv("RAG_HYBRID_SEARCH_ENABLED", "true").lower() == "true"

    @staticmethod
    def is_reranking_enabled() -> bool:
        """Check if reranking is enabled."""
        if not RAGOptimizationFlags.is_optimization_enabled():
            return False
        # Only enable if Cohere API key is configured
        if not settings.COHERE_API_KEY:
            return False
        return os.getenv("RAG_RERANKING_ENABLED", "true").lower() == "true"

    @staticmethod
    def is_multi_query_enabled() -> bool:
        """Check if multi-query expansion is enabled."""
        if not RAGOptimizationFlags.is_optimization_enabled():
            return False
        # Disabled by default (expensive)
        return os.getenv("RAG_MULTI_QUERY_ENABLED", "false").lower() == "true"

    @staticmethod
    def get_rollout_percentage() -> int:
        """Get rollout percentage (0-100)."""
        try:
            return int(os.getenv("RAG_ROLLOUT_PERCENTAGE", "100"))
        except ValueError:
            return 100

    @staticmethod
    def should_use_optimization_for_user(user_id: str) -> bool:
        """
        Determine if optimization should be enabled for a specific user.

        Uses consistent hashing to ensure the same user always gets the same result.
        """
        if not RAGOptimizationFlags.is_optimization_enabled():
            return False

        rollout_percentage = RAGOptimizationFlags.get_rollout_percentage()
        if rollout_percentage >= 100:
            return True
        if rollout_percentage <= 0:
            return False

        # Consistent hash-based assignment
        import hashlib
        user_hash = int(hashlib.md5(user_id.encode()).hexdigest(), 16)
        bucket = user_hash % 100

        return bucket < rollout_percentage


async def retrieve_with_optimizations(
    project_id: str,
    query: str,
    user_id: str,
    limit: int = 5,
    include_drafts: bool = False,
    draft_id: Optional[str] = None,
    force_optimization: bool = False
) -> Dict[str, Any]:
    """
    Unified RAG retrieval with automatic optimization selection.

    Args:
        project_id: UUID of the project
        query: User's query text
        user_id: UUID of the user (for rollout percentage)
        limit: Maximum number of chunks to retrieve
        include_drafts: Whether to include draft content
        draft_id: Optional specific draft ID
        force_optimization: Force use of optimizations regardless of flags

    Returns:
        Dict with:
            - chunks: Retrieved chunks
            - context: Context string (structured or simple based on optimization)
            - system_prompt: System prompt (structured or simple)
            - metadata: Retrieval metadata
            - optimization_enabled: Whether optimization was used
    """
    from app.services.rag_retrieval_enhanced import retrieve_relevant_chunks_optimized
    from app.services.rag_retrieval import retrieve_relevant_chunks_with_drafts

    # Determine if optimization should be used
    use_optimization = force_optimization or RAGOptimizationFlags.should_use_optimization_for_user(user_id)

    if use_optimization:
        logger.info(f"[RAG Integration] Using OPTIMIZED retrieval for user {user_id}")

        # Use enhanced retrieval with all optimizations
        result = await retrieve_relevant_chunks_optimized(
            project_id=project_id,
            query=query,
            limit=limit,
            enable_hybrid=RAGOptimizationFlags.is_hybrid_search_enabled(),
            enable_reranking=RAGOptimizationFlags.is_reranking_enabled(),
            enable_multi_query=RAGOptimizationFlags.is_multi_query_enabled(),
            include_drafts=include_drafts,
            draft_id=draft_id
        )

        return {
            'chunks': result['chunks'],
            'context': result['context_structured'],
            'system_prompt': result['system_prompt'],
            'metadata': result['metadata'],
            'optimization_enabled': True
        }
    else:
        logger.info(f"[RAG Integration] Using BASELINE retrieval for user {user_id}")

        # Use baseline retrieval
        chunks = retrieve_relevant_chunks_with_drafts(
            project_id=project_id,
            query=query,
            limit=limit,
            include_drafts=include_drafts,
            draft_id=draft_id
        )

        # Build simple context (existing format)
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

        # Simple system prompt
        if include_drafts or draft_id:
            system_prompt = """You are a helpful AI research assistant helping users with their research drafts. You have access to both the user's draft content and their literature database.

Answer questions based on the provided context. When citing sources, distinguish between the user's draft and literature. Use citation numbers [N] to reference specific sources."""
        else:
            system_prompt = """You are a helpful AI research assistant. Answer questions based on the provided context from research documents.

When you reference information from a source, add a citation using the format [N] where N is the source number. Always cite your sources when making specific claims."""

        return {
            'chunks': chunks,
            'context': context,
            'system_prompt': system_prompt,
            'metadata': {
                'num_chunks_retrieved': len(chunks),
                'retrieval_method': 'baseline_semantic',
                'optimization_enabled': False
            },
            'optimization_enabled': False
        }


def get_optimization_status() -> Dict[str, Any]:
    """
    Get current RAG optimization status for debugging.

    Returns:
        Dict with feature flag states and configuration
    """
    return {
        'master_enabled': RAGOptimizationFlags.is_optimization_enabled(),
        'hybrid_search': RAGOptimizationFlags.is_hybrid_search_enabled(),
        'reranking': RAGOptimizationFlags.is_reranking_enabled(),
        'multi_query': RAGOptimizationFlags.is_multi_query_enabled(),
        'rollout_percentage': RAGOptimizationFlags.get_rollout_percentage(),
        'cohere_api_key_configured': bool(settings.COHERE_API_KEY),
        'openai_api_key_configured': bool(settings.OPENAI_API_KEY),
    }

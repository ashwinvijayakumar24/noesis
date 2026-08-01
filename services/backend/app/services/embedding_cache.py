"""
Embedding Cache Service

Uses Redis to cache embedding vectors to avoid regenerating same embeddings
"""

import redis
import hashlib
import json
from typing import List, Optional
import pickle

from app.core.config import settings


# Initialize Redis client
try:
    redis_client = redis.from_url(
        settings.REDIS_URL or "redis://redis:6379",
        decode_responses=False  # We'll store binary pickle data
    )
except Exception as e:
    redis_client = None
    print(f"Warning: Redis not available for embedding cache: {str(e)}")


EMBEDDING_CACHE_TTL = 60 * 60 * 24 * 7  # 7 days


def get_cache_key(text: str, model: str = "text-embedding-3-large") -> str:
    """
    Generate cache key for embedding

    Uses SHA-256 hash of text + model

    Args:
        text: Text to embed
        model: Embedding model name

    Returns:
        Cache key string
    """
    content = f"{model}:{text}"
    return f"embedding:{hashlib.sha256(content.encode()).hexdigest()}"


def get_cached_embedding(
    text: str,
    model: str = "text-embedding-3-large"
) -> Optional[List[float]]:
    """
    Get cached embedding if available

    Args:
        text: Text to get embedding for
        model: Embedding model name

    Returns:
        Cached embedding vector or None
    """
    if not redis_client:
        return None

    try:
        cache_key = get_cache_key(text, model)
        cached = redis_client.get(cache_key)

        if cached:
            # Deserialize embedding
            embedding = pickle.loads(cached)
            return embedding

        return None

    except Exception as e:
        # Don't fail if cache read fails
        return None


def cache_embedding(
    text: str,
    embedding: List[float],
    model: str = "text-embedding-3-large",
    ttl: int = EMBEDDING_CACHE_TTL
):
    """
    Cache embedding vector

    Args:
        text: Text that was embedded
        embedding: Embedding vector
        model: Embedding model name
        ttl: Time-to-live in seconds
    """
    if not redis_client:
        return

    try:
        cache_key = get_cache_key(text, model)

        # Serialize embedding
        serialized = pickle.dumps(embedding)

        # Store in Redis with TTL
        redis_client.setex(cache_key, ttl, serialized)

    except Exception as e:
        # Don't fail if cache write fails
        pass


# Decorator to automatically cache embeddings
def cache_embeddings(func):
    """
    Decorator to automatically cache embedding generation

    Wraps any function that takes (text, model) and returns embedding vector

    Example:
        @cache_embeddings
        def generate_embedding(text, model):
            ...
    """
    def wrapper(text: str, model: str = "text-embedding-3-large", **kwargs):
        # Try to get from cache
        cached = get_cached_embedding(text, model)
        if cached is not None:
            return cached

        # Generate embedding
        embedding = func(text, model, **kwargs)

        # Cache for future use
        cache_embedding(text, embedding, model)

        return embedding

    return wrapper

"""
Centralized OpenAI client with privacy-first configuration.
Routes all AI calls through the OpenAI API and applies no-store defaults where
the endpoint supports them. Organization-level zero data retention must still
be enabled with the provider.
"""

from openai import OpenAI, AsyncOpenAI
from app.core.config import settings
from app.core.logging_config import get_logger
from typing import Optional

logger = get_logger(__name__)

# Global client instances (initialized on first use)
_client: Optional[OpenAI] = None
_async_client: Optional[AsyncOpenAI] = None


def get_openai_client() -> OpenAI:
    """
    Get configured OpenAI client with privacy-first settings.

    Returns:
        OpenAI: Configured OpenAI client instance

    Raises:
        ValueError: If OpenAI API key is not configured
    """
    global _client

    if _client is None:
        if not settings.OPENAI_API_KEY:
            raise ValueError("OpenAI API key not configured")

        _client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            organization=settings.OPENAI_ORGANIZATION_ID if settings.OPENAI_ORGANIZATION_ID else None,
        )

        logger.info(f"OpenAI client initialized (zero_retention={settings.OPENAI_ZERO_DATA_RETENTION})")

    return _client


def get_async_openai_client() -> AsyncOpenAI:
    """
    Get configured async OpenAI client with privacy-first settings.

    Returns:
        AsyncOpenAI: Configured async OpenAI client instance

    Raises:
        ValueError: If OpenAI API key is not configured
    """
    global _async_client

    if _async_client is None:
        if not settings.OPENAI_API_KEY:
            raise ValueError("OpenAI API key not configured")

        _async_client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            organization=settings.OPENAI_ORGANIZATION_ID if settings.OPENAI_ORGANIZATION_ID else None,
        )

        logger.info(f"Async OpenAI client initialized (zero_retention={settings.OPENAI_ZERO_DATA_RETENTION})")

    return _async_client


def get_completion_params(enable_zero_retention: bool = True) -> dict:
    """
    Get common parameters for chat.completions.create() calls.
    Returns dict with privacy-first defaults.

    Args:
        enable_zero_retention: Whether to enable zero data retention headers (default: True)

    Returns:
        dict: Parameters to merge into OpenAI API calls
    """
    params = {}

    if enable_zero_retention and settings.OPENAI_ZERO_DATA_RETENTION:
        # Prevent eligible Chat Completions responses from being retained for
        # optional stored-output product surfaces, distillation, or evals.
        params["store"] = False

        # Note: OpenAI's zero data retention is controlled via organization settings
        # and API tier (API data is not used for training by default for API customers).
        # We add organization header for explicit association.
        if settings.OPENAI_ORGANIZATION_ID:
            params["extra_headers"] = {
                "X-OpenAI-Organization": settings.OPENAI_ORGANIZATION_ID,
            }
        logger.debug("Zero data retention enabled for this request")

    return params

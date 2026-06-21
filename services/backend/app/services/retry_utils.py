"""
Retry utilities for resilient API calls

Uses tenacity for exponential backoff and retry logic.
"""

from __future__ import annotations

import asyncio
import functools
import logging
from copy import deepcopy
from types import SimpleNamespace
from typing import Callable, Any, TypeVar

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)
from openai import RateLimitError, APIError, APIConnectionError
from pydantic import ValidationError

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

# Shared semaphore caps concurrent OpenAI calls across the entire process.
# Prevents thundering-herd on bulk analysis jobs (Celery worker concurrency=4,
# each analysis spawns ~5 parallel LLM calls → cap at 20 total in-flight).
openai_semaphore = asyncio.Semaphore(20)


def _sanitize_structured_completion_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize kwargs for structured chat completions.

    The current GPT-5.2 structured-output endpoint rejects explicit
    `temperature=0` and only accepts the default temperature. Most draft-analysis
    nodes route through this helper, so strip that unsupported no-op at the
    boundary instead of duplicating model-specific conditionals in every node.
    """
    sanitized = dict(kwargs)
    model = str(sanitized.get("model") or "")
    if model.startswith("gpt-5.2") and sanitized.get("temperature") == 0:
        sanitized.pop("temperature", None)
    return sanitized


# Retry decorator for OpenAI API calls
retry_openai = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((RateLimitError, APIError, APIConnectionError)),
    before_sleep=before_sleep_log(logger, logging.WARNING)
)


def retry_on_validation_error(max_retries: int = 2) -> Callable[[F], F]:
    """
    Decorator for async LLM node functions that re-prompts on Pydantic ValidationError.

    Structured outputs (client.beta.chat.completions.parse) can still raise
    ValidationError if the model returns a structurally valid JSON that violates
    field constraints (e.g. rating=11 on a 1-10 field). This retries up to
    max_retries additional times before propagating the exception.

    Usage:
        @retry_on_validation_error(max_retries=2)
        async def my_node(state): ...
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: Exception | None = None
            for attempt in range(1 + max_retries):
                try:
                    return await func(*args, **kwargs)
                except ValidationError as exc:
                    last_exc = exc
                    logger.warning(
                        "[retry_on_validation_error] %s attempt %d/%d failed: %s",
                        func.__name__, attempt + 1, 1 + max_retries, exc,
                    )
            raise last_exc  # type: ignore[misc]
        return wrapper  # type: ignore[return-value]
    return decorator


async def with_openai_semaphore(coro: Any) -> Any:
    """Await a coroutine while holding the shared OpenAI semaphore."""
    async with openai_semaphore:
        return await coro


def _messages_with_validation_error(messages: list[dict[str, Any]], exc: ValidationError) -> list[dict[str, Any]]:
    retry_messages = deepcopy(messages)
    retry_messages.append({
        "role": "user",
        "content": (
            "Your previous structured response failed schema validation. "
            "Return the same requested content, but strictly conform to the schema. "
            f"Validation error:\n{exc}"
        ),
    })
    return retry_messages


def _normalize_parsed_chat_completion(response: Any) -> Any:
    """
    Return a stable object with `.parsed` for OpenAI structured chat completions.

    Different openai-python versions expose parsed structured output either as
    `response.parsed` or `response.choices[0].message.parsed`. The draft-analysis
    nodes use the stable `.parsed` surface so SDK drift cannot silently collapse
    the analysis into zero claims/feedback.
    """
    parsed = getattr(response, "parsed", None)
    if parsed is not None:
        return response

    try:
        parsed = response.choices[0].message.parsed
    except (AttributeError, IndexError, TypeError) as exc:
        raise AttributeError(
            "OpenAI structured completion did not expose parsed output"
        ) from exc

    return SimpleNamespace(parsed=parsed, raw=response)


async def parse_chat_completion_with_retries(
    client: Any,
    *,
    messages: list[dict[str, Any]],
    max_validation_retries: int = 2,
    **kwargs: Any,
) -> Any:
    """
    Async wrapper for OpenAI structured output calls.

    Applies:
    - global OpenAI semaphore
    - transient OpenAI API retries
    - validation retries that append the schema error to the prompt
    """
    current_messages = deepcopy(messages)
    sanitized_kwargs = _sanitize_structured_completion_kwargs(kwargs)
    last_exc: ValidationError | None = None

    @retry_openai
    async def _parse_once(active_messages: list[dict[str, Any]]) -> Any:
        async with openai_semaphore:
            return await client.beta.chat.completions.parse(
                messages=active_messages,
                **sanitized_kwargs,
            )

    for attempt in range(max_validation_retries + 1):
        try:
            return _normalize_parsed_chat_completion(await _parse_once(current_messages))
        except ValidationError as exc:
            last_exc = exc
            logger.warning(
                "[parse_chat_completion_with_retries] validation failed attempt %d/%d: %s",
                attempt + 1,
                max_validation_retries + 1,
                exc,
            )
            if attempt >= max_validation_retries:
                break
            current_messages = _messages_with_validation_error(current_messages, exc)

    raise last_exc  # type: ignore[misc]


def parse_chat_completion_with_retries_sync(
    client: Any,
    *,
    messages: list[dict[str, Any]],
    max_validation_retries: int = 2,
    **kwargs: Any,
) -> Any:
    """
    Sync wrapper for OpenAI structured output calls.

    This is used by legacy sync LangGraph nodes and sync services. Async nodes
    should use parse_chat_completion_with_retries().
    """
    current_messages = deepcopy(messages)
    sanitized_kwargs = _sanitize_structured_completion_kwargs(kwargs)
    last_exc: ValidationError | None = None

    @retry_openai
    def _parse_once(active_messages: list[dict[str, Any]]) -> Any:
        return client.beta.chat.completions.parse(
            messages=active_messages,
            **sanitized_kwargs,
        )

    for attempt in range(max_validation_retries + 1):
        try:
            return _normalize_parsed_chat_completion(_parse_once(current_messages))
        except ValidationError as exc:
            last_exc = exc
            logger.warning(
                "[parse_chat_completion_with_retries_sync] validation failed attempt %d/%d: %s",
                attempt + 1,
                max_validation_retries + 1,
                exc,
            )
            if attempt >= max_validation_retries:
                break
            current_messages = _messages_with_validation_error(current_messages, exc)

    raise last_exc  # type: ignore[misc]


# Retry decorator for Supabase queries
retry_supabase = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=5),
    retry=retry_if_exception_type((Exception,)),  # Retry on any exception
    before_sleep=before_sleep_log(logger, logging.WARNING)
)


# Retry decorator for external HTTP calls
retry_http = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((Exception,)),
    before_sleep=before_sleep_log(logger, logging.WARNING)
)


def with_retry(
    func: Callable,
    *args,
    max_attempts: int = 3,
    **kwargs
) -> Any:
    """
    Generic retry wrapper for any function

    Args:
        func: Function to retry
        *args: Positional arguments for function
        max_attempts: Maximum number of retry attempts
        **kwargs: Keyword arguments for function

    Returns:
        Function result

    Example:
        result = with_retry(some_api_call, arg1, arg2, max_attempts=5)
    """
    @retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        before_sleep=before_sleep_log(logger, logging.WARNING)
    )
    def _execute():
        return func(*args, **kwargs)

    return _execute()


def safe_execute(
    func: Callable,
    *args,
    fallback_value: Any = None,
    log_errors: bool = True,
    **kwargs
) -> Any:
    """
    Execute function with error handling and fallback

    Args:
        func: Function to execute
        *args: Positional arguments
        fallback_value: Value to return if function fails
        log_errors: Whether to log errors
        **kwargs: Keyword arguments

    Returns:
        Function result or fallback value

    Example:
        result = safe_execute(risky_function, arg1, fallback_value=[])
    """
    try:
        return func(*args, **kwargs)
    except Exception as e:
        if log_errors:
            logger.error(f"Error executing {func.__name__}: {str(e)}")
        return fallback_value


# Error logging decorator
def log_errors(func: Callable) -> Callable:
    """
    Decorator to log errors without failing

    Useful for non-critical operations like analytics tracking
    """
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in {func.__name__}: {str(e)}")
            return None

    return wrapper

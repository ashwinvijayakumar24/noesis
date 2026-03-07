"""
Retry utilities for resilient API calls

Uses tenacity for exponential backoff and retry logic
"""

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log
)
import logging
from openai import RateLimitError, APIError, APIConnectionError
from typing import Callable, Any

logger = logging.getLogger(__name__)


# Retry decorator for OpenAI API calls
retry_openai = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((RateLimitError, APIError, APIConnectionError)),
    before_sleep=before_sleep_log(logger, logging.WARNING)
)


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

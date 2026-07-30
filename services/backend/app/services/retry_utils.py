"""
Retry utilities for resilient API calls

Uses tenacity for exponential backoff and retry logic.
"""

from __future__ import annotations

import asyncio
import logging
from copy import deepcopy
from types import SimpleNamespace
from typing import Callable, Any

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)
from openai import RateLimitError, APIError, APIConnectionError
from pydantic import ValidationError

from contextlib import contextmanager

from app.core.llm_budget import check_llm_allowed, record_response_usage
from app.core.tracing import SpanKind, get_tracer, llm_call_attributes

logger = logging.getLogger(__name__)

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
    usage_label: str | None = None,
    **kwargs: Any,
) -> Any:
    """
    Async wrapper for OpenAI structured output calls.

    Applies:
    - global OpenAI semaphore
    - transient OpenAI API retries
    - validation retries that append the schema error to the prompt
    - LLM spend guardrails (kill switch / replay-only / ceiling) + usage recording
    """
    # Guard messaging wants *a* name; usage attribution needs to know whether a
    # label was genuinely supplied. Keep them separate: collapsing None into the
    # model name here would hide "no label given" from llm_budget, which resolves
    # label -> ambient llm_label() contextvar -> model name.
    guard_label = usage_label or str(kwargs.get("model") or "unknown")
    check_llm_allowed(guard_label)

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
            with _llm_call_span(kwargs.get("model"), attempt) as span:
                raw_response = await _parse_once(current_messages)
                event = record_response_usage(
                    raw_response, model=kwargs.get("model"), label=usage_label
                )
                _annotate_llm_span(span, kwargs.get("model"), event)
            return _normalize_parsed_chat_completion(raw_response)
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
    usage_label: str | None = None,
    **kwargs: Any,
) -> Any:
    """
    Sync wrapper for OpenAI structured output calls.

    This is used by legacy sync LangGraph nodes and sync services. Async nodes
    should use parse_chat_completion_with_retries().
    """
    # Guard messaging wants *a* name; usage attribution needs to know whether a
    # label was genuinely supplied. Keep them separate: collapsing None into the
    # model name here would hide "no label given" from llm_budget, which resolves
    # label -> ambient llm_label() contextvar -> model name.
    guard_label = usage_label or str(kwargs.get("model") or "unknown")
    check_llm_allowed(guard_label)

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
            with _llm_call_span(kwargs.get("model"), attempt) as span:
                raw_response = _parse_once(current_messages)
                event = record_response_usage(
                    raw_response, model=kwargs.get("model"), label=usage_label
                )
                _annotate_llm_span(span, kwargs.get("model"), event)
            return _normalize_parsed_chat_completion(raw_response)
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


# ---------------------------------------------------------------------------
# LLM call spans
# ---------------------------------------------------------------------------
#
# Every LLM call in the pipeline funnels through the two wrappers below, so this
# is the one place an `llm_call` span can be emitted for all of them. Without it
# the trace analyser has node spans but no token or cost data underneath them,
# and every `$/run` figure reads $0.00 -- the span kind and the attribute helper
# both existed, but nothing was emitting them.
#
# The span is opened INSIDE the validation-retry loop, so a call that is retried
# emits one span per attempt with `noesis.llm.attempt` set. Retry latency and
# retry cost are then separable, which they are not if the whole loop shares one
# span.


@contextmanager
def _llm_call_span(model: Any, attempt: int):
    """An `llm_call` span. Never lets a tracing failure break the call."""
    attrs = {"noesis.llm.attempt": attempt}
    if model:
        attrs["gen_ai.request.model"] = str(model)
    with get_tracer().start_span(
        "openai.chat", kind=SpanKind.LLM_CALL, attributes=attrs
    ) as span:
        yield span


def _annotate_llm_span(span: Any, model: Any, event: Any) -> None:
    """Copy the usage llm_budget just recorded onto the span.

    Reuses the same numbers rather than re-extracting them, so the trace and the
    budget accumulator can never disagree. A missing usage object leaves the
    attributes absent rather than zero -- absent and zero are different facts,
    and the analyser counts unpriced spans to mark a run incomplete.
    """
    if event is None:
        return
    try:
        span.set_attributes(
            llm_call_attributes(
                model=str(model) if model else None,
                prompt_tokens=getattr(event, "prompt_tokens", None),
                completion_tokens=getattr(event, "completion_tokens", None),
                cached_tokens=getattr(event, "cached_tokens", None),
                estimated_usd=getattr(event, "estimated_usd", None),
            )
        )
    except Exception:  # tracing must never break a real call
        logger.debug("[retry_utils] could not annotate llm_call span", exc_info=True)

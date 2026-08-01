"""Process-wide LLM spend accounting and guardrails.

Three jobs, no dependencies beyond the stdlib:

1. **Accounting** — every LLM call records its token usage into a thread-safe
   process-wide accumulator (this codebase spawns worker threads that each run
   their own event loop, so a plain dict is not enough).
2. **Guardrails** — a kill switch, a replay-only flag, and a cumulative spend
   ceiling. ``check_llm_allowed()`` is called *before* any network request so a
   runaway measurement run can be halted from the environment.
3. **Visibility** — an optional append-only JSONL sink so a run's usage can be
   inspected after the fact.

Environment variables (all optional):

- ``NOESIS_LLM_KILL_SWITCH``   truthy -> every LLM call raises ``LLMCallBlocked``
- ``EVAL_REPLAY_ONLY``         truthy -> every LLM call raises ``LLMCallBlocked``
                               (distinct message: eval runs must hit cache only)
- ``NOESIS_LLM_MAX_SPEND_USD`` float  -> once cumulative recorded spend exceeds
                               it, calls raise ``LLMBudgetExceeded``
- ``NOESIS_LLM_USAGE_LOG``     path   -> append one JSON object per usage event

Env vars are read at call time, not import time, so they can be toggled per
process/run (and monkeypatched in tests).
"""

from __future__ import annotations

import contextvars
import json
import logging
import os
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, asdict
from typing import Any, Iterator

logger = logging.getLogger(__name__)

_TRUTHY = {"1", "true", "yes", "on"}


# ---------------------------------------------------------------------------
# Pricing
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ModelPrice:
    """USD per 1M tokens. ``None`` means *unknown*, never *free*."""

    input_per_1m: float | None = None
    output_per_1m: float | None = None
    cached_input_per_1m: float | None = None


# PRICES BELOW WERE TRANSCRIBED FROM OPENAI'S OFFICIAL PUBLISHED API PRICING ON
# THE DATE NOTED PER ENTRY. Every rate was cross-checked against two official
# pages: the pricing index (https://developers.openai.com/api/docs/pricing) and
# that model's own page (https://developers.openai.com/api/docs/models/<model>).
#
# RE-VERIFY BEFORE QUOTING EXTERNALLY. OpenAI changes list prices without notice
# and these numbers carry a retrieval date precisely so a stale figure is
# detectable. A rate that could not be verified stays ``None`` -- never guessed,
# never interpolated. ``None`` makes ``estimate_usd()`` return None instead of a
# confidently wrong number, and those calls land in
# ``totals()["unpriced_calls"]`` so the gap is visible rather than silent.
#
# EMBEDDINGS AND ``output_per_1m``: the embeddings endpoint emits no completion
# tokens at all, so its output rate is a real, verified $0.00 -- not an unknown
# standing in as zero. Recording it as 0.0 (rather than None) is what makes an
# embedding call priced instead of being miscounted as unpriced; the alternative
# would be a special case inside ``estimate_usd``. ``cached_input_per_1m`` stays
# None for embeddings because OpenAI publishes no cached rate for them (prompt
# caching does not apply); if a response ever did report cached tokens for an
# embedding model, that call is correctly scored unpriced rather than guessed.
MODEL_PRICING_USD_PER_1M: dict[str, ModelPrice] = {
    # https://developers.openai.com/api/docs/models/gpt-5.2 -- retrieved 2026-07-30
    # input $1.75 / cached input $0.175 / output $14.00 per 1M tokens
    "gpt-5.2": ModelPrice(1.75, 14.00, 0.175),
    # https://developers.openai.com/api/docs/models/gpt-5.2-chat-latest -- retrieved 2026-07-30
    # input $1.75 / cached input $0.175 / output $14.00 per 1M tokens
    "gpt-5.2-chat-latest": ModelPrice(1.75, 14.00, 0.175),
    # https://developers.openai.com/api/docs/models/gpt-5-mini -- retrieved 2026-07-30
    # input $0.25 / cached input $0.025 / output $2.00 per 1M tokens
    "gpt-5-mini": ModelPrice(0.25, 2.00, 0.025),
    # https://developers.openai.com/api/docs/models/gpt-5-nano -- retrieved 2026-08-01
    # input $0.05 / cached input $0.005 / output $0.40 per 1M tokens
    # Added for the cascade sweep (scripts/eval/cascade_arms.py). Without an
    # entry these calls price as None: they contribute $0 to _total_usd, so
    # NOESIS_LLM_MAX_SPEND_USD cannot see them and every cost figure quoting
    # them is silently zero rather than visibly unknown.
    "gpt-5-nano": ModelPrice(0.05, 0.40, 0.005),
    # https://developers.openai.com/api/docs/models/gpt-5.1 -- retrieved 2026-08-01
    # input $1.25 / cached input $0.125 / output $10.00 per 1M tokens
    "gpt-5.1": ModelPrice(1.25, 10.00, 0.125),
    # https://developers.openai.com/api/docs/models/text-embedding-3-large -- retrieved 2026-07-30
    # $0.13 per 1M tokens; no output tokens exist, no cached rate published
    "text-embedding-3-large": ModelPrice(0.13, 0.0, None),
    # https://developers.openai.com/api/docs/models/text-embedding-3-small -- retrieved 2026-07-30
    # $0.02 per 1M tokens; no output tokens exist, no cached rate published
    "text-embedding-3-small": ModelPrice(0.02, 0.0, None),
    # ---- Anthropic ----
    # Transcribed from Anthropic's official published API pricing table:
    # https://platform.claude.com/docs/en/about-claude/pricing -- retrieved 2026-07-31
    # Row "Claude Sonnet 4.5": base input $3.00 / cache hits & refreshes $0.30 /
    # output $15.00 per 1M tokens. The key is the undated alias so that dated
    # snapshots (claude-sonnet-4-5-20250929) resolve via get_price()'s prefix match.
    #
    # NOTE ON CACHE WRITES: Anthropic prices cache WRITES above base input
    # ($3.75/1M at 5m TTL, $6.00/1M at 1h). ModelPrice has no field for that, so
    # a call that writes cache is under-estimated here. The only Anthropic caller
    # (scripts/eval/gate_calibration/llm_labeller.py) never sets cache_control, so
    # cache_creation_input_tokens is always 0; it warns on stderr if that ever
    # changes rather than silently reporting a low number.
    "claude-sonnet-4-5": ModelPrice(3.00, 15.00, 0.30),
}


def get_price(model: str | None) -> ModelPrice | None:
    """Exact match first, then longest known prefix (handles dated snapshots)."""
    if not model:
        return None
    price = MODEL_PRICING_USD_PER_1M.get(model)
    if price is not None:
        return price
    candidates = [k for k in MODEL_PRICING_USD_PER_1M if model.startswith(k)]
    if not candidates:
        return None
    return MODEL_PRICING_USD_PER_1M[max(candidates, key=len)]


def estimate_usd(
    model: str | None,
    prompt_tokens: int,
    completion_tokens: int,
    cached_tokens: int = 0,
) -> float | None:
    """Estimated cost in USD, or ``None`` when pricing is not known.

    ``prompt_tokens`` is assumed to *include* ``cached_tokens`` (OpenAI's
    convention), so cached tokens are billed at the cached rate and the
    remainder at the full input rate. If any rate needed for this call is
    unknown the whole estimate is None -- a partial number would be wrong.
    """
    price = get_price(model)
    if price is None:
        return None
    if price.input_per_1m is None or price.output_per_1m is None:
        return None

    cached = max(0, int(cached_tokens or 0))
    uncached = max(0, int(prompt_tokens or 0) - cached)

    total = uncached * price.input_per_1m / 1_000_000
    total += max(0, int(completion_tokens or 0)) * price.output_per_1m / 1_000_000
    if cached:
        if price.cached_input_per_1m is None:
            return None
        total += cached * price.cached_input_per_1m / 1_000_000
    return total


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class LLMGuardrailError(RuntimeError):
    """Base class for guardrail trips."""


class LLMCallBlocked(LLMGuardrailError):
    """An LLM call was blocked by the kill switch or by replay-only mode."""


class LLMBudgetExceeded(LLMGuardrailError):
    """Cumulative recorded spend exceeded ``NOESIS_LLM_MAX_SPEND_USD``."""


# ---------------------------------------------------------------------------
# Env helpers
# ---------------------------------------------------------------------------

def env_truthy(name: str) -> bool:
    """Match the existing convention (see draft_publish_gate.FAIL_CLOSED)."""
    return os.getenv(name, "").strip().lower() in _TRUTHY


def _env_float(name: str) -> float | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        logger.warning("[llm_budget] %s=%r is not a float; ignoring ceiling", name, raw)
        return None


def kill_switch_enabled() -> bool:
    return env_truthy("NOESIS_LLM_KILL_SWITCH")


def replay_only_enabled() -> bool:
    return env_truthy("EVAL_REPLAY_ONLY")


def max_spend_usd() -> float | None:
    return _env_float("NOESIS_LLM_MAX_SPEND_USD")


def max_calls() -> int | None:
    """Call-count ceiling.

    Originally added because the dollar ceiling was inert: with every rate in
    MODEL_PRICING_USD_PER_1M set to None, each call landed in _unpriced_calls,
    contributed 0 to _total_usd, and NOESIS_LLM_MAX_SPEND_USD could never trip.
    The table is now populated and the dollar ceiling does fire.

    This one stays, because it is the only bound that survives price drift. A
    model absent from the table, or renamed upstream, silently becomes unpriced
    again and stops counting toward spend; a call ceiling still bounds the run.
    Belt and braces, cheap to keep.
    """
    raw = os.getenv("NOESIS_LLM_MAX_CALLS", "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        logger.warning(
            "[llm_budget] NOESIS_LLM_MAX_CALLS=%r is not an int; ignoring ceiling", raw
        )
        return None


# ---------------------------------------------------------------------------
# Accumulator
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class UsageEvent:
    model: str
    label: str
    prompt_tokens: int
    completion_tokens: int
    cached_tokens: int
    estimated_usd: float | None
    timestamp: float


# ---------------------------------------------------------------------------
# Ambient label (per-node token attribution)
# ---------------------------------------------------------------------------
#
# ~20 call sites already pass a label, but they pass the *model name* (see
# retry_utils: ``label = usage_label or model``). To get per-NODE attribution
# without touching those call sites, a graph node wraps its work in
# ``with llm_label("reviewer_panel:methodology"):`` and every LLM call inside
# records under that label.
#
# NOTE ON THREADS: ``app/services/async_utils.run_coroutine_sync`` runs each
# coroutine in a brand-new ``threading.Thread``. contextvars do NOT propagate
# into a plain Thread, so that helper explicitly re-runs the target inside a
# ``contextvars.copy_context()`` snapshot taken in the calling thread. Without
# that, this label is silently lost on the busiest path in the codebase.

_current_label: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "noesis_llm_label", default=None
)

# Labels that mean "nobody actually named this call". A label equal to the
# model name is treated as absent for the same reason: that is precisely the
# fallback the existing call sites emit when no explicit label was given, and
# the ambient label must be able to win over it.
_PLACEHOLDER_LABELS = {"", "unknown", "none"}


@contextmanager
def llm_label(label: str) -> Iterator[str]:
    """Attribute every LLM call made inside this block to ``label``.

    Nesting is supported; the innermost active label wins and the outer one is
    restored on exit (including on exception). Safe under asyncio concurrency:
    each task gets its own copy of the context, so sibling tasks cannot see
    each other's labels.
    """
    token = _current_label.set(str(label))
    try:
        yield str(label)
    finally:
        _current_label.reset(token)


def current_label() -> str | None:
    """The ambient label, or None when no ``llm_label`` block is active."""
    return _current_label.get()


def _resolve_label(label: str | None, model_name: str) -> str:
    """Priority: explicit ``label=`` -> ambient contextvar -> model name.

    ``retry_utils`` passes ``label=None`` when no caller supplied one, so absence
    is genuinely distinguishable here and no heuristic is needed. Placeholder
    strings are still treated as absent, since a caller threading through a
    literal ``"unknown"`` means the same thing as passing nothing.
    """
    explicit = str(label).strip() if label is not None else ""
    if explicit and explicit.lower() not in _PLACEHOLDER_LABELS:
        return explicit
    ambient = _current_label.get()
    if ambient:
        return str(ambient)
    return model_name or "unknown"


_lock = threading.Lock()
_events: list[UsageEvent] = []
_total_usd: float = 0.0
_unpriced_calls: int = 0


def record_usage(
    *,
    model: str | None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    cached_tokens: int = 0,
    label: str | None = None,
) -> UsageEvent:
    """Record one LLM call. Never raises on accounting or sink problems.

    The recorded label is resolved as: explicit ``label=`` argument, then the
    ambient ``llm_label(...)`` contextvar, then the model name.
    """
    model_name = str(model or "unknown")
    prompt_tokens = max(0, int(prompt_tokens or 0))
    completion_tokens = max(0, int(completion_tokens or 0))
    cached_tokens = max(0, int(cached_tokens or 0))

    cost = estimate_usd(model_name, prompt_tokens, completion_tokens, cached_tokens)
    event = UsageEvent(
        model=model_name,
        label=_resolve_label(label, model_name),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cached_tokens=cached_tokens,
        estimated_usd=cost,
        timestamp=time.time(),
    )

    global _total_usd, _unpriced_calls
    with _lock:
        _events.append(event)
        if cost is None:
            _unpriced_calls += 1
        else:
            _total_usd += cost

    _append_to_sink(event)
    return event


def extract_usage(response: Any) -> tuple[int, int, int] | None:
    """Pull ``(prompt_tokens, completion_tokens, cached_tokens)`` off an SDK response.

    Accepts the response object or the usage object itself. Returns None when no
    usage information is available (caller should record an unpriced call).
    """
    if response is None:
        return None
    usage = getattr(response, "usage", None)
    if usage is None:
        # Maybe a nested/normalized wrapper kept the original under `.raw`.
        raw = getattr(response, "raw", None)
        if raw is not None:
            usage = getattr(raw, "usage", None)
    if usage is None and hasattr(response, "prompt_tokens"):
        usage = response
    if usage is None:
        return None

    def _get(obj: Any, key: str, default: int = 0) -> int:
        if isinstance(obj, dict):
            value = obj.get(key, default)
        else:
            value = getattr(obj, key, default)
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return default

    prompt = _get(usage, "prompt_tokens")
    completion = _get(usage, "completion_tokens")

    details = usage.get("prompt_tokens_details") if isinstance(usage, dict) else getattr(usage, "prompt_tokens_details", None)
    cached = _get(details, "cached_tokens") if details is not None else 0

    return prompt, completion, cached


def record_response_usage(response: Any, *, model: str | None, label: str | None = None) -> UsageEvent:
    """Record usage from an SDK response, tolerating a missing ``usage`` block."""
    extracted = extract_usage(response)
    if extracted is None:
        logger.debug("[llm_budget] no usage on response for model=%s label=%s", model, label)
        return record_usage(model=model, label=label)
    prompt, completion, cached = extracted
    return record_usage(
        model=model,
        prompt_tokens=prompt,
        completion_tokens=completion,
        cached_tokens=cached,
        label=label,
    )


def _blank_bucket() -> dict[str, Any]:
    return {
        "calls": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "cached_tokens": 0,
        "total_tokens": 0,
        "estimated_usd": 0.0,
        "unpriced_calls": 0,
    }


def _fold(bucket: dict[str, Any], event: UsageEvent) -> None:
    bucket["calls"] += 1
    bucket["prompt_tokens"] += event.prompt_tokens
    bucket["completion_tokens"] += event.completion_tokens
    bucket["cached_tokens"] += event.cached_tokens
    bucket["total_tokens"] += event.prompt_tokens + event.completion_tokens
    if event.estimated_usd is None:
        bucket["unpriced_calls"] += 1
    else:
        bucket["estimated_usd"] += event.estimated_usd


def totals() -> dict[str, Any]:
    with _lock:
        snapshot = list(_events)
    bucket = _blank_bucket()
    for event in snapshot:
        _fold(bucket, event)
    return bucket


def _group_by(key: str) -> dict[str, dict[str, Any]]:
    with _lock:
        snapshot = list(_events)
    grouped: dict[str, dict[str, Any]] = {}
    for event in snapshot:
        bucket = grouped.setdefault(getattr(event, key), _blank_bucket())
        _fold(bucket, event)
    return grouped


def by_model() -> dict[str, dict[str, Any]]:
    return _group_by("model")


def by_label() -> dict[str, dict[str, Any]]:
    return _group_by("label")


def events() -> list[UsageEvent]:
    with _lock:
        return list(_events)


def total_spend_usd() -> float:
    with _lock:
        return _total_usd


def unpriced_calls() -> int:
    with _lock:
        return _unpriced_calls


def reset() -> None:
    global _total_usd, _unpriced_calls
    with _lock:
        _events.clear()
        _total_usd = 0.0
        _unpriced_calls = 0


# ---------------------------------------------------------------------------
# Guard
# ---------------------------------------------------------------------------

def check_llm_allowed(label: str = "unknown") -> None:
    """Raise if an LLM call must not be made. Call BEFORE any network request."""
    if kill_switch_enabled():
        raise LLMCallBlocked(
            f"LLM call '{label}' blocked: NOESIS_LLM_KILL_SWITCH is set. "
            "Unset it to allow live OpenAI calls."
        )
    if replay_only_enabled():
        raise LLMCallBlocked(
            f"LLM call '{label}' blocked: EVAL_REPLAY_ONLY is set, so this run may "
            "only use cached results. A cache miss reached the live API."
        )
    call_ceiling = max_calls()
    if call_ceiling is not None:
        with _lock:
            made = len(_events)
        if made >= call_ceiling:
            raise LLMBudgetExceeded(
                f"LLM call '{label}' blocked: {made} call(s) already recorded, "
                f"reaching NOESIS_LLM_MAX_CALLS={call_ceiling}. This ceiling is "
                "pricing-independent and fires even when model pricing is unknown."
            )
    ceiling = max_spend_usd()
    if ceiling is not None:
        with _lock:
            spent = _total_usd
            unpriced = _unpriced_calls
        if spent > ceiling:
            raise LLMBudgetExceeded(
                f"LLM call '{label}' blocked: recorded spend ${spent:.4f} exceeds "
                f"NOESIS_LLM_MAX_SPEND_USD=${ceiling:.4f} "
                f"({unpriced} call(s) had unknown pricing and are NOT included)."
            )


# ---------------------------------------------------------------------------
# JSONL sink
# ---------------------------------------------------------------------------

def _append_to_sink(event: UsageEvent) -> None:
    path = os.getenv("NOESIS_LLM_USAGE_LOG", "").strip()
    if not path:
        return
    try:
        line = json.dumps(asdict(event), sort_keys=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except Exception as exc:  # sink must never break the caller
        logger.warning("[llm_budget] could not append usage to %s: %s", path, exc)

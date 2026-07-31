"""The stubbed LLM, the Supabase write guard, and the ``stage_only`` assertion.

Why stub at all
---------------
One reviewer-panel call is ~$0.043 and ~19s. A lambda sweep with 5 points and
n>=100 per point would be several thousand calls and several hundred dollars.
Queue depth, backpressure, goodput collapse and the open/closed-loop gap are all
functions of the *latency distribution* of the dependency, not of the text it
returns -- so the text is thrown away and the distribution is kept.

Where the seam is
-----------------
Every LLM call in the draft-analysis graph funnels through exactly two lines:
``retry_utils.parse_chat_completion_with_retries`` (async, line ~130) and
``parse_chat_completion_with_retries_sync`` (~186), both calling
``client.beta.chat.completions.parse``. Replacing the *client* therefore
replaces every call while leaving the retry wrapper, the LLM-budget guard, the
tracing span and -- critically -- the process-wide ``openai_semaphore(20)``
fully in play. That semaphore is a real contention point under concurrency and
stubbing above it would have hidden it.

The stage_only assertion
------------------------
Every ``insert``/``update``/``upsert``/``delete`` in the graph is supposed to sit
behind ``if not state.get("stage_only", True)``. This module does not trust
that. :class:`WriteGuardSupabase` replaces the Supabase client outright and
**raises** on any write verb. A run that completes is a run in which no write
was attempted; a run in which one was attempted fails loudly and names the
table. Reads return empty rather than raising, since the graph's read paths are
all wrapped in try/except and degrade to "no corpus".

Two writes escape the stage_only gate and are handled separately, by argument
rather than by guard -- see LATENCY.md:

* ``graph.py`` line ~754/780: ``checkpoint_saver.save_checkpoint`` writes to the
  ``workflow_checkpoints`` table before and after ``ainvoke``, gated on the
  ``checkpoint_enabled`` *parameter*, not on ``stage_only``. The harness passes
  ``checkpoint_enabled=False``.
* ``publish_progress`` writes a progress snapshot to Redis (not Supabase) on
  every node boundary. Stubbed to a no-op here; left in place it would add
  ~40 failed Redis connections per graph run to the measurement.
"""

from __future__ import annotations

import asyncio
import enum
import random
import threading
import time
import types
import typing
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from .latency_profile import LatencyProfile

__all__ = [
    "SupabaseWriteAttempted",
    "WriteGuardSupabase",
    "StubCounters",
    "synthesize",
    "install_stubs",
]

WRITE_VERBS = ("insert", "update", "upsert", "delete")


class SupabaseWriteAttempted(AssertionError):
    """A graph node tried to write to Supabase during a stage_only load run."""


# ---------------------------------------------------------------------------
# Supabase write guard
# ---------------------------------------------------------------------------

class _EmptyResult:
    def __init__(self) -> None:
        self.data: list = []
        self.count = 0


class _GuardedTable:
    def __init__(self, name: str, guard: "WriteGuardSupabase") -> None:
        self._name = name
        self._guard = guard

    def __getattr__(self, verb: str):
        if verb in WRITE_VERBS:
            def _refuse(*args, **kwargs):
                self._guard.write_attempts.append((self._name, verb))
                raise SupabaseWriteAttempted(
                    f"write escaped the stage_only gate: "
                    f"supabase.table({self._name!r}).{verb}(...)"
                )
            return _refuse

        # Every read-shaped builder verb returns self so chains terminate at
        # execute(); an unknown verb is treated as a builder rather than
        # exploding, because the point of the guard is writes, not API coverage.
        def _chain(*args, **kwargs):
            return self
        return _chain

    def execute(self) -> _EmptyResult:
        self._guard.reads += 1
        return _EmptyResult()


class WriteGuardSupabase:
    """Reads return empty; writes raise. Drop-in for ``app.core.supabase_client.supabase``."""

    def __init__(self) -> None:
        self.write_attempts: list[tuple[str, str]] = []
        self.reads = 0
        self.rpcs = 0

    def table(self, name: str) -> _GuardedTable:
        return _GuardedTable(name, self)

    def from_(self, name: str) -> _GuardedTable:  # postgrest alias
        return _GuardedTable(name, self)

    def rpc(self, name: str, params: dict | None = None) -> _GuardedTable:
        self.rpcs += 1
        return _GuardedTable(f"rpc:{name}", self)

    @property
    def storage(self):  # pragma: no cover - graph nodes never touch storage
        raise SupabaseWriteAttempted("storage access during a stage_only load run")


# ---------------------------------------------------------------------------
# Structured-output synthesis
# ---------------------------------------------------------------------------

def _bounds(field_info: Any) -> tuple[float | None, float | None]:
    lo = hi = None
    for m in getattr(field_info, "metadata", ()) or ():
        for attr, slot in (("ge", "lo"), ("gt", "lo"), ("le", "hi"), ("lt", "hi")):
            v = getattr(m, attr, None)
            if v is not None:
                if slot == "lo":
                    lo = float(v)
                else:
                    hi = float(v)
    return lo, hi


def _pick_literal(options: tuple, prompt: str) -> Any:
    """Choose the Literal option the prompt talks about most.

    This exists for one field: ``ReviewerOutput.reviewer_id``, which must come
    back matching the persona the branch was dispatched as, or the fan-out's
    three outputs collapse into one identity downstream. Counting occurrences in
    the prompt is generic enough to need no per-schema special case, and falls
    back to the first option when the prompt is silent.
    """
    if not options:
        return None
    best, best_n = options[0], -1
    low = prompt.lower()
    for opt in options:
        if not isinstance(opt, str):
            continue
        n = low.count(opt.lower())
        if n > best_n:
            best, best_n = opt, n
    return best


def synthesize(
    model_cls: type[BaseModel],
    *,
    prompt: str = "",
    rng: random.Random | None = None,
    list_len: int = 3,
    depth: int = 0,
    max_depth: int = 4,
) -> BaseModel:
    """Build a schema-valid instance of ``model_cls``.

    Schema-valid, not semantically meaningful: the strings are placeholders. The
    graph is being driven for its *shape* -- which nodes run, how many branches
    fan out, how long each waits -- and nothing downstream of a load run reads
    the text. Any output-quality claim from a stub run would be worthless and
    none is made.
    """
    rng = rng or random.Random(0)
    values: dict[str, Any] = {}
    for name, f in model_cls.model_fields.items():
        values[name] = _value_for(
            f.annotation, f, name=name, prompt=prompt, rng=rng,
            list_len=list_len, depth=depth, max_depth=max_depth,
        )
    return model_cls(**values)


def _value_for(
    ann: Any, field_info: Any, *, name: str, prompt: str, rng: random.Random,
    list_len: int, depth: int, max_depth: int,
) -> Any:
    origin = typing.get_origin(ann)
    args = typing.get_args(ann)

    if origin is typing.Literal:
        return _pick_literal(args, prompt)

    if origin in (typing.Union, types.UnionType):
        non_none = [a for a in args if a is not type(None)]
        if not non_none:
            return None
        # Optional fields get a real value rather than None: a None here would
        # take a different downstream branch than production usually takes.
        return _value_for(
            non_none[0], field_info, name=name, prompt=prompt, rng=rng,
            list_len=list_len, depth=depth, max_depth=max_depth,
        )

    if origin in (list, set, tuple):
        if depth >= max_depth or not args:
            return []
        inner = args[0]
        return [
            _value_for(inner, field_info, name=name, prompt=prompt, rng=rng,
                       list_len=list_len, depth=depth + 1, max_depth=max_depth)
            for _ in range(list_len)
        ]

    if origin is dict:
        return {}

    if isinstance(ann, type) and issubclass(ann, BaseModel):
        if depth >= max_depth:
            return ann.model_construct()
        return synthesize(ann, prompt=prompt, rng=rng, list_len=max(1, list_len - 1),
                          depth=depth + 1, max_depth=max_depth)

    if isinstance(ann, type) and issubclass(ann, enum.Enum):
        return list(ann)[0]

    lo, hi = _bounds(field_info)
    if ann is bool:
        # True by default. Nearly every bool in these schemas is a
        # proceed/keep/pass flag, and False would route the graph down the
        # desk-reject or suppress path, i.e. would measure a *shorter* pipeline
        # than the one under test.
        return True
    if ann is int:
        if lo is not None and hi is not None:
            return int((lo + hi) // 2)
        return int(lo if lo is not None else 1)
    if ann is float:
        if lo is not None and hi is not None:
            return (lo + hi) / 2.0
        return float(lo if lo is not None else 0.5)
    if ann is str:
        return f"[stubbed {name}]"
    return None


# ---------------------------------------------------------------------------
# The stub client
# ---------------------------------------------------------------------------

@dataclass
class StubCounters:
    calls: int = 0
    sleep_seconds: float = 0.0
    by_node: dict[str, int] = field(default_factory=dict)
    write_attempts: list[tuple[str, str]] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def record(self, node: str, seconds: float) -> None:
        with self.lock:
            self.calls += 1
            self.sleep_seconds += seconds
            self.by_node[node] = self.by_node.get(node, 0) + 1


class _StubResponse:
    """Shaped like an openai structured-output response, minus the usage block.

    ``usage`` is deliberately absent. ``llm_budget.record_response_usage``
    tolerates that and records a call with zero tokens and zero dollars, so a
    stub run reports **$0.00000 spend and a non-zero call count** -- which is
    exactly true and cannot be confused with a real run's spend.
    """

    def __init__(self, parsed: Any) -> None:
        self.parsed = parsed
        self.usage = None
        self.choices = [types.SimpleNamespace(message=types.SimpleNamespace(parsed=parsed))]


class _StubCompletions:
    def __init__(self, profile: LatencyProfile, counters: StubCounters,
                 rng: random.Random, list_len: int, is_async: bool) -> None:
        self._p, self._c, self._rng, self._n = profile, counters, rng, list_len
        self._async = is_async

    def _prepare(self, kwargs: dict) -> tuple[float, str, Any]:
        from app.core.llm_budget import current_label
        node = current_label() or "unknown"
        seconds = self._p.sample(node)
        model_cls = kwargs.get("response_format")
        prompt = " ".join(
            str(m.get("content", "")) for m in kwargs.get("messages", []) or []
        )
        if isinstance(model_cls, type) and issubclass(model_cls, BaseModel):
            parsed = synthesize(model_cls, prompt=prompt, rng=self._rng, list_len=self._n)
        else:
            parsed = types.SimpleNamespace()
        return seconds, node, parsed

    def parse(self, **kwargs):
        seconds, node, parsed = self._prepare(kwargs)
        if self._async:
            async def _run():
                await asyncio.sleep(seconds)
                self._c.record(node, seconds)
                return _StubResponse(parsed)
            return _run()
        # The sync path BLOCKS, on purpose. `extract_claims_node` is a plain
        # `def` called directly from an async graph wrapper (graph.py:160), and
        # `citation_mapping_node` routes through
        # `parse_chat_completion_with_retries_sync`. In production those calls
        # block the event loop thread for their full duration, stalling every
        # other in-flight graph run in the same process. A non-blocking stub
        # would erase that and report a concurrency the service does not have.
        time.sleep(seconds)
        self._c.record(node, seconds)
        return _StubResponse(parsed)


class StubOpenAIClient:
    def __init__(self, profile: LatencyProfile, counters: StubCounters, *,
                 seed: int = 0, list_len: int = 3, is_async: bool = True) -> None:
        completions = _StubCompletions(profile, counters, random.Random(seed), list_len, is_async)
        chat = types.SimpleNamespace(completions=completions)
        self.beta = types.SimpleNamespace(chat=chat)
        self.chat = chat


# ---------------------------------------------------------------------------
# Installation
# ---------------------------------------------------------------------------

@dataclass
class StubControl:
    counters: StubCounters
    guard: WriteGuardSupabase
    profile: LatencyProfile
    stubbed_llm: bool

    def assert_no_writes(self) -> None:
        if self.guard.write_attempts:
            raise SupabaseWriteAttempted(
                f"{len(self.guard.write_attempts)} write attempt(s): "
                f"{self.guard.write_attempts[:5]}"
            )


def install_stubs(
    profile: LatencyProfile,
    *,
    stub_llm: bool = True,
    seed: int = 0,
    list_len: int = 3,
) -> StubControl:
    """Install the guard/stub set. **Must run before the graph is imported.**

    ``graph.py`` and the node modules do ``from app.core.X import Y`` at module
    scope, binding the name into their own namespace. Patching the source module
    after they are imported would be a no-op, so this patches first and the
    caller imports the graph afterwards.
    """
    import app.core.supabase_client as sb
    import app.services.progress_publisher as pp

    counters = StubCounters()
    guard = WriteGuardSupabase()
    sb.supabase = guard

    async def _noop_progress(*args, **kwargs):
        return None

    pp.publish_progress = _noop_progress

    if stub_llm:
        import app.core.openai_client as oc
        oc.get_async_openai_client = lambda: StubOpenAIClient(
            profile, counters, seed=seed, list_len=list_len, is_async=True
        )
        oc.get_openai_client = lambda: StubOpenAIClient(
            profile, counters, seed=seed + 1, list_len=list_len, is_async=False
        )

    control = StubControl(counters, guard, profile, stub_llm)
    counters.write_attempts = guard.write_attempts
    return control

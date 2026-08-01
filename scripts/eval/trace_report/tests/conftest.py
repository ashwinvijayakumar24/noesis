"""Synthetic span fixtures.

Everything here is hand-built. Nothing depends on a real pipeline run, because
one may not exist yet -- and a metric that can only be tested against live data
is a metric with no test.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# scripts/eval on the path so `import trace_report` works from anywhere.
EVAL_DIR = Path(__file__).resolve().parents[2]
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))


def span(
    span_id: str,
    *,
    trace_id: str = "T1",
    name: str = "node",
    kind: str = "node",
    parent: str | None = None,
    start: float = 0.0,
    end: float | None = None,
    duration_ms: float | None = None,
    attributes: dict | None = None,
    status: str = "OK",
) -> dict:
    """One span dict in the exact shape ``JsonlAdapter`` writes."""
    if end is None and duration_ms is not None:
        end = start + duration_ms / 1000.0
    if duration_ms is None and end is not None:
        duration_ms = (end - start) * 1000.0
    return {
        "name": name,
        "kind": kind,
        "trace_id": trace_id,
        "span_id": span_id,
        "parent_span_id": parent,
        "status": status,
        "start_time": start,
        "end_time": end,
        "duration_ms": duration_ms,
        "attributes": attributes or {},
    }


def llm(
    span_id: str,
    *,
    parent: str,
    trace_id: str = "T1",
    model: str | None = "gpt-5.2",
    input_tokens: int | None = 1000,
    output_tokens: int | None = 500,
    cached_tokens: int | None = 0,
    cost: float | None = None,
    start: float = 0.0,
    duration_ms: float = 100.0,
) -> dict:
    attrs: dict = {"gen_ai.system": "openai", "gen_ai.operation.name": "chat"}
    if model is not None:
        attrs["gen_ai.request.model"] = model
    if input_tokens is not None:
        attrs["gen_ai.usage.input_tokens"] = input_tokens
    if output_tokens is not None:
        attrs["gen_ai.usage.output_tokens"] = output_tokens
    if cached_tokens is not None:
        attrs["noesis.gen_ai.usage.cached_input_tokens"] = cached_tokens
    if cost is not None:
        attrs["noesis.gen_ai.usage.estimated_cost_usd"] = cost
    return span(
        span_id,
        trace_id=trace_id,
        name="openai.chat",
        kind="llm_call",
        parent=parent,
        start=start,
        duration_ms=duration_ms,
        attributes=attrs,
    )


def write_jsonl(path: Path, spans, truncate_last: bool = False, extra_lines=()) -> Path:
    lines = [json.dumps(s) for s in spans]
    lines.extend(extra_lines)
    text = "\n".join(lines)
    if truncate_last and lines:
        text = text[: -max(1, len(lines[-1]) // 2)]
    else:
        text += "\n"
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def make_file(tmp_path):
    counter = {"n": 0}

    def _make(spans, **kwargs) -> Path:
        counter["n"] += 1
        return write_jsonl(tmp_path / f"spans{counter['n']}.jsonl", spans, **kwargs)

    return _make

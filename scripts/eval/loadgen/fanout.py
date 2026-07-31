"""Forcing the reviewer fan-out serial, so a "before" exists to compare against.

``route_to_reviewer_panel`` returns three ``Send`` objects, which LangGraph runs
as concurrent tasks. That is the *only* real parallelism in the 18-node graph --
every other edge is sequential. So "what does the fan-out buy" is answerable if
and only if a serial counterfactual can be constructed.

It can. This module wraps ``reviewer_panel_node`` in a lock keyed by
``draft_id``, so the three branches of one graph run execute one after another
while everything else -- the same three prompts, the same node bodies, the same
scheduler, the same LLM latency draws -- is untouched. Keying by ``draft_id``
rather than using a process-global lock matters under concurrent load: a global
lock would also serialize reviewers *across* graph runs and would measure
something else entirely.

What this cannot reconstruct: the historical serial implementation, whatever it
was. There is no commit in this repo that runs the reviewers sequentially, no
recorded timing from one, and no artefact anywhere claiming to be the "53s"
baseline. This is a counterfactual built today from today's code, and it should
be described that way and no other way.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict

__all__ = ["install_serial_reviewers", "restore_reviewers"]

_original = None
_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


def install_serial_reviewers() -> None:
    """Serialize the three reviewer branches within each graph run."""
    global _original
    import app.workflows.draft_analysis.graph as G

    if _original is not None:
        return
    _original = G.reviewer_panel_node

    async def _serialized(state):
        key = str(state.get("draft_id") or "global")
        async with _locks[key]:
            return await _original(state)

    # graph.py's wrapper resolves this module global at call time
    # (`result = await reviewer_panel_node(state)`), so rebinding it here takes
    # effect for runs started afterwards without touching graph.py.
    G.reviewer_panel_node = _serialized


def restore_reviewers() -> None:
    global _original
    if _original is None:
        return
    import app.workflows.draft_analysis.graph as G
    G.reviewer_panel_node = _original
    _original = None
    _locks.clear()

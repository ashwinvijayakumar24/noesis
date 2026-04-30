"""
Async helpers for synchronous worker contexts.

Celery runs with a gevent pool in local Docker, which means some worker
processes already have an active event loop context. Calling `asyncio.run()`
or `loop.run_until_complete()` directly from those sync task handlers can
raise "Cannot run the event loop while another loop is running".
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any, Coroutine, TypeVar

T = TypeVar("T")


def run_coroutine_sync(coro: Coroutine[Any, Any, T]) -> T:
    """
    Run a coroutine from synchronous code in an isolated thread.

    This avoids nested event-loop errors inside gevent-backed Celery workers
    while keeping the calling code synchronous.
    """

    result: dict[str, T] = {}
    error: dict[str, BaseException] = {}

    def _runner() -> None:
        try:
            result["value"] = asyncio.run(coro)
        except BaseException as exc:  # pragma: no cover - re-raised below
            error["value"] = exc

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    thread.join()

    if "value" in error:
        raise error["value"]

    return result["value"]

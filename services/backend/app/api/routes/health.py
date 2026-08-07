"""
Kubernetes-grade health probes.

Three probes, three different questions. Startup: "I am still booting, don't
judge me yet" — buys a slow boot a long grace window without loosening
liveness. Readiness: "don't route traffic to me right now" — a failure pulls
the pod out of the Service endpoints but never restarts it. Liveness: "I am
unrecoverable, kill me" — a failure means a restart.

Liveness therefore checks the process ONLY and never touches Redis, Supabase,
or any socket. Probing dependencies from liveness is an anti-pattern: a Redis
blip fails liveness on every replica at the same instant, K8s restarts the
whole fleet, and a recoverable dependency hiccup becomes a full outage plus a
cold-start stampede. Dependency failures belong in readiness, where the blast
radius is "stop sending traffic" instead of "destroy the fleet".
"""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

import redis.asyncio as aioredis
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.privacy import safe_exception
from app.core.supabase_client import supabase

logger = logging.getLogger(__name__)

router = APIRouter()

# Same default the rest of the app uses (see services/progress_tracking.py).
REDIS_URL = settings.REDIS_URL or "redis://redis:6379/0"

# Hard, short budgets. A readiness probe that outlives the kubelet's own
# timeoutSeconds is worse than useless.
REDIS_TIMEOUT_SECONDS = 1.0
SUPABASE_TIMEOUT_SECONDS = 2.0

# Startup completion flag, flipped once by main.py's startup hook.
_startup_complete = False


def mark_startup_complete() -> None:
    """Called from the app startup hook; flips /healthz/startup to 200."""
    global _startup_complete
    _startup_complete = True


async def _check_redis() -> None:
    client = aioredis.from_url(
        REDIS_URL,
        socket_connect_timeout=REDIS_TIMEOUT_SECONDS,
        socket_timeout=REDIS_TIMEOUT_SECONDS,
    )
    try:
        await client.ping()
    finally:
        try:
            await client.close()
        except Exception:  # pragma: no cover - close is best effort
            pass


def _supabase_probe_sync() -> None:
    # Cheapest reachability check available without a new dependency: a
    # single-row select on an existing table through the client the app
    # already holds. A raw HEAD to the REST root would skip PostgREST's
    # connection to Postgres entirely (so it would pass while the database
    # is down), and the service-role key bypasses RLS, so this cannot be
    # tripped by per-user policies. limit(1) on an indexed PK keeps it off
    # any expensive-query rate limiting.
    if supabase is None:
        raise RuntimeError("supabase client not configured")
    supabase.table("projects").select("id").limit(1).execute()


async def _check_supabase() -> None:
    # supabase-py is sync; the rest of the codebase calls it from threads.
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _supabase_probe_sync)


async def _run_check(
    name: str,
    check: Callable[[], Awaitable[None]],
    timeout: float,
) -> tuple[str, dict]:
    """Run one dependency check. Never raises, never outlives `timeout`."""
    try:
        await asyncio.wait_for(check(), timeout=timeout)
        return name, {"status": "ok"}
    except asyncio.TimeoutError:
        return name, {"status": "unhealthy", "error": "TimeoutError"}
    except Exception as exc:
        # safe_exception() yields the error class only — never provider text.
        return name, {"status": "unhealthy", "error": safe_exception(exc)}


@router.get("/live")
async def live():
    """Liveness: the process is running and the event loop is servicing requests."""
    return {"status": "alive"}


@router.get("/ready")
async def ready():
    """Readiness: every dependency needed to serve traffic right now is reachable."""
    results = await asyncio.gather(
        _run_check("redis", _check_redis, REDIS_TIMEOUT_SECONDS),
        _run_check("supabase", _check_supabase, SUPABASE_TIMEOUT_SECONDS),
    )
    checks = dict(results)
    failed = [name for name, result in checks.items() if result["status"] != "ok"]

    if failed:
        logger.warning("Readiness probe failed: %s", failed)
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "failed": failed, "checks": checks},
        )

    return {"status": "ready", "checks": checks}


@router.get("/startup")
async def startup():
    """Startup: 503 while the app is still booting, 200 once startup finished."""
    if not _startup_complete:
        return JSONResponse(
            status_code=503,
            content={"status": "starting"},
        )
    return {"status": "started"}

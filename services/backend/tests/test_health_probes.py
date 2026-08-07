"""
Tests for the Kubernetes probes in app/api/routes/health.py.

The router is mounted on a bare FastAPI app so nothing in app.main (Sentry,
security middleware, every other router) is pulled in. Zero real network:
Redis and Supabase are both monkeypatched at the module level.
"""

import asyncio
import sys
import time
import types
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# app/api/routes/__init__.py eagerly imports every route module, which drags in
# weasyprint (native libgobject). Stub it the same way tests/test_ci_api_contracts.py
# does so this file can be collected on a machine without the native libs.
if "weasyprint" not in sys.modules:
    _fake_weasyprint = types.ModuleType("weasyprint")
    _fake_weasyprint.HTML = MagicMock()
    _fake_weasyprint.CSS = MagicMock()
    sys.modules["weasyprint"] = _fake_weasyprint

from app.api.routes import health as health_routes  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(health_routes.router, prefix="/healthz")
    return TestClient(app)


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch):
    """Fail loudly if any test forgets to stub a dependency."""

    def _explode(*args, **kwargs):
        raise AssertionError("test attempted a real network call")

    monkeypatch.setattr(health_routes.aioredis, "from_url", _explode)
    monkeypatch.setattr(health_routes, "supabase", None)


def _stub_redis(monkeypatch: pytest.MonkeyPatch, check):
    monkeypatch.setattr(health_routes, "_check_redis", check)


def _stub_supabase(monkeypatch: pytest.MonkeyPatch, check):
    monkeypatch.setattr(health_routes, "_check_supabase", check)


async def _ok():
    return None


class _Boom(Exception):
    pass


async def _redis_down():
    raise _Boom("connection refused to 10.0.0.1:6379")


class _SupabaseError(Exception):
    pass


async def _supabase_down():
    raise _SupabaseError("postgrest 500 for https://xyz.supabase.co/rest/v1/projects")


async def _hangs():
    await asyncio.sleep(30)


# ---------------------------------------------------------------- liveness


def test_live_returns_200_even_when_all_deps_are_down(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    _stub_redis(monkeypatch, _redis_down)
    _stub_supabase(monkeypatch, _supabase_down)

    response = client.get("/healthz/live")

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


# --------------------------------------------------------------- readiness


def test_ready_returns_200_when_both_deps_healthy(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    _stub_redis(monkeypatch, _ok)
    _stub_supabase(monkeypatch, _ok)

    response = client.get("/healthz/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"]["redis"]["status"] == "ok"
    assert body["checks"]["supabase"]["status"] == "ok"


def test_ready_returns_503_naming_redis_when_redis_raises(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    _stub_redis(monkeypatch, _redis_down)
    _stub_supabase(monkeypatch, _ok)

    response = client.get("/healthz/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["failed"] == ["redis"]
    assert body["checks"]["redis"]["error"] == "_Boom"
    assert body["checks"]["supabase"]["status"] == "ok"
    # Error class only — no host, no raw exception text.
    assert "10.0.0.1" not in response.text


def test_ready_returns_503_naming_supabase_when_supabase_raises(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    _stub_redis(monkeypatch, _ok)
    _stub_supabase(monkeypatch, _supabase_down)

    response = client.get("/healthz/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["failed"] == ["supabase"]
    assert body["checks"]["supabase"]["error"] == "_SupabaseError"
    assert "supabase.co" not in response.text


def test_ready_returns_503_when_a_dep_hangs(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    _stub_redis(monkeypatch, _hangs)
    _stub_supabase(monkeypatch, _ok)
    monkeypatch.setattr(health_routes, "REDIS_TIMEOUT_SECONDS", 0.05)

    started = time.monotonic()
    response = client.get("/healthz/ready")
    elapsed = time.monotonic() - started

    assert response.status_code == 503
    body = response.json()
    assert body["failed"] == ["redis"]
    assert body["checks"]["redis"]["error"] == "TimeoutError"
    # The handler returned instead of hanging for the full 30s sleep.
    assert elapsed < 5


def test_ready_names_both_deps_when_both_fail(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    _stub_redis(monkeypatch, _redis_down)
    _stub_supabase(monkeypatch, _supabase_down)

    response = client.get("/healthz/ready")

    assert response.status_code == 503
    assert sorted(response.json()["failed"]) == ["redis", "supabase"]


# ----------------------------------------------------------------- startup


def test_startup_returns_503_before_flag_and_200_after(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(health_routes, "_startup_complete", False)
    before = client.get("/healthz/startup")
    assert before.status_code == 503
    assert before.json() == {"status": "starting"}

    health_routes.mark_startup_complete()
    after = client.get("/healthz/startup")
    assert after.status_code == 200
    assert after.json() == {"status": "started"}


def test_startup_flag_does_not_leak_between_tests():
    """mark_startup_complete() above was monkeypatch-scoped; confirm reset."""
    assert health_routes._startup_complete is False

import importlib
import importlib.metadata
import sys
import types
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi.middleware.cors import CORSMiddleware


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    fake_weasyprint = types.ModuleType("weasyprint")
    fake_weasyprint.HTML = MagicMock()
    monkeypatch.setitem(sys.modules, "weasyprint", fake_weasyprint)

    fake_email_validator = types.ModuleType("email_validator")
    fake_email_validator.__version__ = "2.0.0"

    class EmailNotValidError(Exception):
        pass

    def validate_email(email: str, *args, **kwargs):
        return types.SimpleNamespace(email=email, normalized=email)

    fake_email_validator.EmailNotValidError = EmailNotValidError
    fake_email_validator.validate_email = validate_email
    monkeypatch.setitem(sys.modules, "email_validator", fake_email_validator)

    original_version = importlib.metadata.version

    def fake_version(name: str) -> str:
        if name == "email-validator":
            return "2.0.0"
        return original_version(name)

    monkeypatch.setattr(importlib.metadata, "version", fake_version)
    import pydantic.networks

    monkeypatch.setattr(pydantic.networks, "version", fake_version)

    from app.core import openai_client

    monkeypatch.setattr(openai_client, "get_openai_client", lambda: MagicMock())
    monkeypatch.setattr(openai_client, "get_async_openai_client", lambda: MagicMock())

    auth_routes = importlib.import_module("app.api.routes.auth")
    documents_routes = importlib.import_module("app.api.routes.documents")
    drafts_routes = importlib.import_module("app.api.routes.drafts")
    projects_routes = importlib.import_module("app.api.routes.projects")
    quota_routes = importlib.import_module("app.api.routes.quota")
    subscriptions_routes = importlib.import_module("app.api.routes.subscriptions")
    from app.core.security_middleware import (
        SecurityHeadersMiddleware,
        InputValidationMiddleware,
        get_cors_config,
    )
    from app.core.config import settings

    fake_supabase = MagicMock()
    fake_supabase.auth.get_user.side_effect = Exception("invalid token")

    for route_module in (
        auth_routes,
        documents_routes,
        drafts_routes,
        projects_routes,
        quota_routes,
    ):
        monkeypatch.setattr(route_module, "supabase", fake_supabase)

    test_app = FastAPI(title="CI Contract Test App")
    test_app.add_middleware(SecurityHeadersMiddleware)
    test_app.add_middleware(InputValidationMiddleware)
    allowed_origins = [origin.strip() for origin in settings.CORS_ORIGINS.split(",")]
    test_app.add_middleware(CORSMiddleware, **get_cors_config(allowed_origins, settings.ENVIRONMENT))

    test_app.include_router(auth_routes.router, prefix="/auth")
    test_app.include_router(projects_routes.router, prefix="/projects")
    test_app.include_router(documents_routes.router, prefix="/documents")
    test_app.include_router(drafts_routes.router, prefix="/drafts")
    test_app.include_router(quota_routes.router, prefix="/quota")
    test_app.include_router(subscriptions_routes.router, prefix="/api")

    @test_app.get("/health")
    async def health():
        return {"status": "ok"}

    with TestClient(test_app) as test_client:
        yield test_client


@pytest.mark.unit
def test_health_route_is_public_and_has_security_headers(client: TestClient):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"


@pytest.mark.unit
def test_health_route_does_not_echo_arbitrary_origin(client: TestClient):
    response = client.get("/health", headers={"Origin": "https://evil.example.com"})

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") != "https://evil.example.com"


@pytest.mark.unit
@pytest.mark.parametrize(
    "path",
    [
        "/projects/",
        "/documents/",
        "/drafts/",
        "/quota/me",
        "/auth/quota-summary",
    ],
)
def test_protected_routes_require_auth(client: TestClient, path: str):
    response = client.get(path)

    assert response.status_code == 401
    assert "access_token" not in response.text.lower()
    assert "service_role_key" not in response.text.lower()
    assert "supabase_url" not in response.text.lower()


@pytest.mark.unit
@pytest.mark.parametrize(
    "path",
    [
        "/projects/",
        "/documents/",
        "/drafts/",
        "/quota/me",
        "/auth/quota-summary",
    ],
)
def test_invalid_token_is_rejected(client: TestClient, path: str):
    response = client.get(path, headers={"Authorization": "Bearer invalid.jwt.token"})

    assert response.status_code == 401
    assert "access_token" not in response.text.lower()


@pytest.mark.unit
def test_subscription_plans_endpoint_is_public_and_current(client: TestClient):
    response = client.get("/api/subscriptions/plans")

    assert response.status_code == 200
    data = response.json()
    plans = data["plans"]

    assert set(plans.keys()) >= {"free", "pro", "team"}
    assert any("30 PDF uploads per month total" in feature for feature in plans["free"]["features"])
    assert any("5 Literature Map refreshes per day" in feature for feature in plans["free"]["features"])
    assert plans["free"]["limits"]["project_limit"] == 3

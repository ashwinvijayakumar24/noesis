"""
E2E test fixtures for Noesis API tests.

Uses httpx AsyncClient against a running backend (http://localhost:8000).
Set TEST_USER_EMAIL and TEST_USER_PASSWORD env vars to authenticate.

Usage:
    pytest tests/e2e/ -v --timeout=120 -m "not slow"
"""

import asyncio
import io
import os
import pytest
import httpx
from typing import AsyncGenerator

BASE_URL = os.getenv("TEST_API_URL", "http://localhost:8000")
TEST_EMAIL = os.getenv("TEST_USER_EMAIL", "test@noesis.dev")
TEST_PASSWORD = os.getenv("TEST_USER_PASSWORD", "testpassword123")


@pytest.fixture(scope="session")
def event_loop():
    """Single event loop for the session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Shared async HTTP client for the test session."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=120) as client:
        yield client


@pytest.fixture(scope="session")
async def auth_headers(async_client: httpx.AsyncClient) -> dict:
    """Authenticate once and return auth headers for the whole session."""
    resp = await async_client.post(
        "/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    token = resp.json().get("access_token") or resp.json().get("session", {}).get("access_token")
    assert token, f"No access_token in login response: {resp.json()}"
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
async def test_project(async_client: httpx.AsyncClient, auth_headers: dict) -> dict:
    """Create a test project once per session, clean up after."""
    resp = await async_client.post(
        "/projects/",
        json={"title": "E2E Test Project", "description": "Automated test project"},
        headers=auth_headers,
    )
    assert resp.status_code in (200, 201), f"Project creation failed: {resp.text}"
    project = resp.json()
    yield project
    # Cleanup
    await async_client.delete(f"/projects/{project['id']}", headers=auth_headers)


@pytest.fixture
def minimal_pdf_bytes() -> bytes:
    """Returns a minimal valid PDF byte string for upload tests."""
    return (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]\n"
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
        b"4 0 obj\n<< /Length 44 >>\nstream\nBT /F1 12 Tf 100 700 Td "
        b"(E2E Test) Tj ET\nendstream\nendobj\n"
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
        b"xref\n0 6\n0000000000 65535 f \n"
        b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n0\n%%EOF\n"
    )


@pytest.fixture
def minimal_txt_bytes() -> bytes:
    """Returns minimal text content for draft upload tests."""
    return (
        b"Abstract\n\nThis paper presents a novel approach to research intelligence. "
        b"We claim that automated analysis improves academic writing quality. "
        b"Our methodology uses large language models combined with vector search. "
        b"The results demonstrate significant improvements in draft quality. "
        b"We conclude that AI-assisted peer review is viable.\n\n"
        b"Introduction\n\nResearch writing is a complex task. "
        b"Existing tools do not provide adequate feedback. "
        b"We propose a new system that addresses these limitations.\n"
    )

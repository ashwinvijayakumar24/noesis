"""
E2E test fixtures for Noesis API tests.

Uses httpx AsyncClient against a running backend (http://localhost:8000).
Set TEST_USER_EMAIL and TEST_USER_PASSWORD env vars to authenticate.

Usage:
    pytest tests/e2e/ -v --timeout=120 -m "not slow"
"""

import io
import os
import pytest
import pytest_asyncio
import httpx
from typing import AsyncGenerator

BASE_URL = os.getenv("TEST_API_URL", "http://localhost:8000")
TEST_EMAIL = os.getenv("TEST_USER_EMAIL", "test@noesis.dev")
TEST_PASSWORD = os.getenv("TEST_USER_PASSWORD", "testpassword123")

# NOTE: fixtures are function-scoped on purpose. A custom session-scoped
# `event_loop` fixture is removed in pytest-asyncio 1.x and caused
# "RuntimeError: Event loop is closed" when a session fixture was created on one
# loop and torn down on another. Function scope gives each test its own loop +
# client, which is correct across pytest-asyncio 0.24 and 1.3. Each e2e test
# already creates its own draft inside the test, so no cross-test state is lost.


@pytest_asyncio.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Async HTTP client for a single test."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=120) as client:
        yield client


# Cache the access token across tests. Logging in per test trips Supabase auth
# rate-limiting (HTTP 429), which cascades into fixture-setup errors across the
# suite. One login per session is enough; tokens stay valid well beyond a run.
_TOKEN_CACHE: dict[str, str] = {}


@pytest_asyncio.fixture
async def auth_headers(async_client: httpx.AsyncClient) -> dict:
    """Authenticate once (cached) and return auth headers."""
    if "token" not in _TOKEN_CACHE:
        resp = await async_client.post(
            "/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        )
        assert resp.status_code == 200, f"Login failed: {resp.text}"
        token = resp.json().get("access_token") or resp.json().get("session", {}).get("access_token")
        assert token, f"No access_token in login response: {resp.json()}"
        _TOKEN_CACHE["token"] = token
    return {"Authorization": f"Bearer {_TOKEN_CACHE['token']}"}


def _project_id(payload: dict) -> str | None:
    """Extract a project id regardless of response envelope shape."""
    if not isinstance(payload, dict):
        return None
    for container in (payload, payload.get("project"), payload.get("data")):
        if isinstance(container, dict) and container.get("id"):
            return container["id"]
    return None


@pytest_asyncio.fixture
async def test_project(async_client: httpx.AsyncClient, auth_headers: dict) -> dict:
    """Create a test project for a single test, clean up after.

    Reuses an existing project if the account is at its plan's project limit so
    the suite stays runnable on a free-tier test user.
    """
    resp = await async_client.post(
        "/projects/",
        json={"title": "E2E Test Project", "description": "Automated test project"},
        headers=auth_headers,
    )
    created_here = resp.status_code in (200, 201)
    project_id = _project_id(resp.json()) if created_here else None

    if not project_id:
        # Quota reached or unexpected shape — fall back to an existing project.
        existing = await async_client.get("/projects/", headers=auth_headers)
        items = existing.json() if existing.status_code == 200 else []
        if isinstance(items, dict):
            items = items.get("projects") or items.get("data") or []
        assert items, f"No project available and creation failed: {resp.text}"
        yield items[0]
        return

    yield {"id": project_id, **(resp.json() if isinstance(resp.json(), dict) else {})}
    # Cleanup only what this fixture created.
    await async_client.delete(f"/projects/{project_id}", headers=auth_headers)


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
    """A short but COHERENT multi-section draft for upload tests.

    It must carry enough real content that the full analysis pipeline's quality
    judge does not flag it as contaminated/empty (a near-empty stub is rejected,
    making the end-to-end analysis test non-deterministic). Kept compact but with
    abstract/intro/methods/results/discussion so a real run reaches 'analyzed'.
    """
    return (
        b"Title: A Retrieval-Augmented Framework for Automated Pre-Submission Manuscript Review\n\n"
        b"Abstract\n\nWe present a retrieval-augmented framework that provides automated "
        b"pre-submission review of academic manuscripts. The system extracts claims, maps them "
        b"to supporting literature using dense vector retrieval, detects coverage gaps, and "
        b"produces reviewer-style feedback. Across 120 manuscripts the framework identified 78% "
        b"of issues later raised by human reviewers. Retrieval grounding reduced hallucinated "
        b"citations relative to ungrounded language-model baselines.\n\n"
        b"Introduction\n\nPeer review is a bottleneck in scholarly communication. Authors receive "
        b"feedback only after submission. Existing grammar and reference tools do not evaluate "
        b"argumentative structure, citation adequacy, or methodological transparency. We propose a "
        b"system that analyzes a draft before submission and surfaces likely reviewer concerns.\n\n"
        b"Methods\n\nManuscripts are parsed into sections and paragraphs. Each empirical claim is "
        b"embedded with a 1536-dimensional model. We retrieve supporting passages from the author's "
        b"library with hybrid lexical and semantic search, then rerank candidates before attaching "
        b"them. Coverage gaps are detected when a claim lacks any sufficiently similar source.\n\n"
        b"Results\n\nThe framework achieved 0.81 precision and 0.74 recall against human-annotated "
        b"issues. Retrieval grounding reduced irrelevant citation suggestions by 63% relative to an "
        b"ungrounded baseline.\n\n"
        b"Discussion\n\nAutomated pre-submission review is feasible. Limitations include reliance on "
        b"the author-provided library and reduced accuracy on poorly formatted PDFs.\n"
    )

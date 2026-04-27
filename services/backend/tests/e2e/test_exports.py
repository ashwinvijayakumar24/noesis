"""
E2E tests: BibTeX export + Draft PDF export.
"""

import pytest
import httpx


@pytest.mark.integration
class TestBibTeXExport:
    async def test_bibtex_export_returns_bib_file(
        self,
        async_client: httpx.AsyncClient,
        auth_headers: dict,
        test_project: dict,
    ):
        """BibTeX export endpoint returns a .bib file or empty/valid response."""
        resp = await async_client.get(
            f"/projects/{test_project['id']}/export-bibtex",
            headers=auth_headers,
        )
        assert resp.status_code in (200, 204), f"BibTeX export failed: {resp.text}"
        if resp.status_code == 200:
            content_type = resp.headers.get("content-type", "")
            # Either text/plain, application/octet-stream, or text/x-bibtex
            assert any(
                ct in content_type
                for ct in ("text", "octet-stream", "bibtex")
            ), f"Unexpected content type: {content_type}"

    async def test_bibtex_export_requires_auth(
        self, async_client: httpx.AsyncClient, test_project: dict
    ):
        resp = await async_client.get(
            f"/projects/{test_project['id']}/export-bibtex"
        )
        assert resp.status_code in (401, 403)

    async def test_bibtex_export_wrong_project_returns_404(
        self,
        async_client: httpx.AsyncClient,
        auth_headers: dict,
    ):
        resp = await async_client.get(
            "/projects/00000000-0000-0000-0000-000000000000/export-bibtex",
            headers=auth_headers,
        )
        assert resp.status_code in (403, 404)


@pytest.mark.integration
class TestDraftPDFExport:
    async def test_draft_pdf_export_wrong_id_returns_404(
        self,
        async_client: httpx.AsyncClient,
        auth_headers: dict,
    ):
        """Non-existent draft ID returns 404."""
        resp = await async_client.get(
            "/drafts/00000000-0000-0000-0000-000000000000/export-pdf",
            headers=auth_headers,
        )
        assert resp.status_code in (403, 404)

    async def test_draft_pdf_export_requires_auth(
        self, async_client: httpx.AsyncClient
    ):
        resp = await async_client.get(
            "/drafts/00000000-0000-0000-0000-000000000000/export-pdf"
        )
        assert resp.status_code in (401, 403)


@pytest.mark.integration
class TestJSONExport:
    async def test_project_documents_json_export(
        self,
        async_client: httpx.AsyncClient,
        auth_headers: dict,
        test_project: dict,
    ):
        """Project bundle endpoint returns documents list."""
        resp = await async_client.get(
            f"/projects/{test_project['id']}/bundle",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "documents" in data

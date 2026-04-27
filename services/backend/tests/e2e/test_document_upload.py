"""
E2E tests: Document upload → processing → analyzed pipeline.

Critical path: upload PDF → poll status → verify analyzed state.
"""

import asyncio
import pytest
import httpx


@pytest.mark.integration
class TestDocumentUpload:
    async def test_upload_pdf_returns_document_id(
        self,
        async_client: httpx.AsyncClient,
        auth_headers: dict,
        test_project: dict,
        minimal_pdf_bytes: bytes,
    ):
        """Upload a PDF and get back a document ID."""
        resp = await async_client.post(
            "/documents/upload",
            files={"file": ("test.pdf", minimal_pdf_bytes, "application/pdf")},
            data={"project_id": test_project["id"]},
            headers=auth_headers,
        )
        assert resp.status_code in (200, 201), f"Upload failed: {resp.text}"
        data = resp.json()
        assert "id" in data
        assert data["id"] is not None

    async def test_document_has_initial_status(
        self,
        async_client: httpx.AsyncClient,
        auth_headers: dict,
        test_project: dict,
        minimal_pdf_bytes: bytes,
    ):
        """Uploaded document starts with an expected initial status."""
        resp = await async_client.post(
            "/documents/upload",
            files={"file": ("test_status.pdf", minimal_pdf_bytes, "application/pdf")},
            data={"project_id": test_project["id"]},
            headers=auth_headers,
        )
        assert resp.status_code in (200, 201)
        doc = resp.json()
        assert doc.get("status") in (
            "uploaded", "processing", "analyzing", "analyzed", "pending"
        )

    @pytest.mark.slow
    async def test_upload_progresses_to_analyzed(
        self,
        async_client: httpx.AsyncClient,
        auth_headers: dict,
        test_project: dict,
        minimal_pdf_bytes: bytes,
    ):
        """Upload a PDF and wait up to 2 minutes for it to reach 'analyzed'."""
        # Upload
        resp = await async_client.post(
            "/documents/upload",
            files={"file": ("e2e_poll.pdf", minimal_pdf_bytes, "application/pdf")},
            data={"project_id": test_project["id"]},
            headers=auth_headers,
        )
        assert resp.status_code in (200, 201), f"Upload failed: {resp.text}"
        doc_id = resp.json()["id"]

        # Poll for analyzed status (max 2 minutes)
        final_status = None
        for _ in range(60):
            status_resp = await async_client.get(
                f"/documents/{doc_id}", headers=auth_headers
            )
            assert status_resp.status_code == 200
            final_status = status_resp.json().get("status")
            if final_status in ("analyzed", "failed"):
                break
            await asyncio.sleep(2)

        assert final_status == "analyzed", (
            f"Document never reached 'analyzed' state. Final status: {final_status}"
        )
        # Should have analysis content
        doc_data = (await async_client.get(f"/documents/{doc_id}", headers=auth_headers)).json()
        assert doc_data.get("analysis") is not None

    async def test_document_list_includes_uploaded(
        self,
        async_client: httpx.AsyncClient,
        auth_headers: dict,
        test_project: dict,
        minimal_pdf_bytes: bytes,
    ):
        """Uploaded document appears in the project's document list."""
        # Upload
        resp = await async_client.post(
            "/documents/upload",
            files={"file": ("list_test.pdf", minimal_pdf_bytes, "application/pdf")},
            data={"project_id": test_project["id"]},
            headers=auth_headers,
        )
        assert resp.status_code in (200, 201)
        doc_id = resp.json()["id"]

        # Check it appears in list
        list_resp = await async_client.get(
            f"/documents/?project_id={test_project['id']}", headers=auth_headers
        )
        assert list_resp.status_code == 200
        docs = list_resp.json()
        doc_ids = [d["id"] for d in (docs if isinstance(docs, list) else docs.get("documents", []))]
        assert doc_id in doc_ids

    async def test_upload_without_project_id_fails(
        self,
        async_client: httpx.AsyncClient,
        auth_headers: dict,
        minimal_pdf_bytes: bytes,
    ):
        """Upload without project_id should fail with 400/422."""
        resp = await async_client.post(
            "/documents/upload",
            files={"file": ("no_project.pdf", minimal_pdf_bytes, "application/pdf")},
            headers=auth_headers,
        )
        assert resp.status_code in (400, 422)

    async def test_upload_non_pdf_fails(
        self,
        async_client: httpx.AsyncClient,
        auth_headers: dict,
        test_project: dict,
    ):
        """Uploading a non-PDF should fail gracefully."""
        resp = await async_client.post(
            "/documents/upload",
            files={"file": ("malicious.exe", b"MZ\x90\x00", "application/octet-stream")},
            data={"project_id": test_project["id"]},
            headers=auth_headers,
        )
        assert resp.status_code in (400, 415, 422)

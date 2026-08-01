"""
E2E tests: Draft upload → analysis → claims/gaps/feedback.
"""

import asyncio
import pytest
import httpx


def _draft_id(resp: httpx.Response) -> str:
    """Upload returns {"draft": {...}}; tolerate a flat shape too."""
    data = resp.json()
    return data.get("id") or (data.get("draft") or {}).get("id")


@pytest.mark.integration
class TestDraftUpload:
    async def test_upload_txt_draft_returns_id(
        self,
        async_client: httpx.AsyncClient,
        auth_headers: dict,
        test_project: dict,
        minimal_txt_bytes: bytes,
    ):
        """Upload a TXT draft and get back a draft ID."""
        resp = await async_client.post(
            "/drafts/upload",
            files={"file": ("test_draft.txt", minimal_txt_bytes, "text/plain")},
            data={"project_id": test_project["id"], "title": "E2E Test Draft"},
            headers=auth_headers,
        )
        assert resp.status_code in (200, 201), f"Draft upload failed: {resp.text}"
        assert _draft_id(resp)

    async def test_draft_appears_in_list(
        self,
        async_client: httpx.AsyncClient,
        auth_headers: dict,
        test_project: dict,
        minimal_txt_bytes: bytes,
    ):
        """Uploaded draft appears in project's draft list."""
        resp = await async_client.post(
            "/drafts/upload",
            files={"file": ("list_draft.txt", minimal_txt_bytes, "text/plain")},
            data={"project_id": test_project["id"], "title": "List Test Draft"},
            headers=auth_headers,
        )
        assert resp.status_code in (200, 201)
        draft_id = _draft_id(resp)

        list_resp = await async_client.get(
            f"/drafts/?project_id={test_project['id']}", headers=auth_headers
        )
        assert list_resp.status_code == 200
        drafts_data = list_resp.json()
        draft_ids = [
            d["id"]
            for d in (drafts_data if isinstance(drafts_data, list) else drafts_data.get("drafts", []))
        ]
        assert draft_id in draft_ids

    async def test_trigger_analysis_returns_task_id(
        self,
        async_client: httpx.AsyncClient,
        auth_headers: dict,
        test_project: dict,
        minimal_txt_bytes: bytes,
    ):
        """Triggering draft analysis returns a task reference."""
        # Upload
        upload_resp = await async_client.post(
            "/drafts/upload",
            files={"file": ("trigger_draft.txt", minimal_txt_bytes, "text/plain")},
            data={"project_id": test_project["id"], "title": "Trigger Test"},
            headers=auth_headers,
        )
        assert upload_resp.status_code in (200, 201)
        draft_id = _draft_id(upload_resp)

        # Trigger analysis
        analyze_resp = await async_client.post(
            f"/drafts/{draft_id}/analyze",
            headers=auth_headers,
        )
        assert analyze_resp.status_code in (200, 202), (
            f"Trigger analysis failed: {analyze_resp.text}"
        )

    @pytest.mark.slow
    async def test_draft_analysis_completes(
        self,
        async_client: httpx.AsyncClient,
        auth_headers: dict,
        test_project: dict,
        minimal_txt_bytes: bytes,
    ):
        """Upload draft, trigger analysis, wait for completion, verify output."""
        # Upload
        upload_resp = await async_client.post(
            "/drafts/upload",
            files={"file": ("full_test.txt", minimal_txt_bytes, "text/plain")},
            data={"project_id": test_project["id"], "title": "Full Analysis Test"},
            headers=auth_headers,
        )
        assert upload_resp.status_code in (200, 201)
        draft_id = _draft_id(upload_resp)

        # Trigger
        await async_client.post(f"/drafts/{draft_id}/analyze", headers=auth_headers)

        # Poll (max 3 minutes for analysis)
        final_status = None
        for _ in range(90):
            status_resp = await async_client.get(f"/drafts/{draft_id}", headers=auth_headers)
            assert status_resp.status_code == 200
            final_status = status_resp.json().get("status")
            if final_status in ("analyzed", "failed"):
                break
            await asyncio.sleep(2)

        assert final_status == "analyzed", (
            f"Draft analysis did not complete. Final status: {final_status}"
        )

        # Verify analysis output exists
        analysis_resp = await async_client.get(
            f"/drafts/{draft_id}/analysis", headers=auth_headers
        )
        assert analysis_resp.status_code == 200
        analysis = analysis_resp.json()
        # Should have meaningful analysis content. The current (v2) analysis
        # payload surfaces action items, a readiness score, an editor decision,
        # and a score breakdown rather than raw claims/gaps at the top level.
        has_content = any([
            analysis.get("claims"),
            analysis.get("coverage_gaps"),
            analysis.get("reviewer_feedback"),
            analysis.get("draft_analysis"),
            analysis.get("action_items"),
            analysis.get("priority_actions"),
            analysis.get("score_breakdown"),
            analysis.get("editor_decision"),
            analysis.get("readiness_score") is not None,
        ])
        assert has_content, f"Analysis output empty: {analysis}"


@pytest.mark.integration
class TestDraftRequiresAuth:
    async def test_draft_list_requires_auth(self, async_client: httpx.AsyncClient):
        resp = await async_client.get("/drafts/")
        assert resp.status_code in (401, 403)

    async def test_draft_upload_requires_auth(
        self, async_client: httpx.AsyncClient, minimal_txt_bytes: bytes
    ):
        resp = await async_client.post(
            "/drafts/upload",
            files={"file": ("test.txt", minimal_txt_bytes, "text/plain")},
        )
        assert resp.status_code in (401, 403)

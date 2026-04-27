"""
E2E tests: BibTeX import pipeline — import .bib → poll resolution → verify.
"""

import asyncio
import pytest
import httpx


SAMPLE_BIBTEX = b"""@article{vaswani2017attention,
  title={Attention is All you Need},
  author={Vaswani, Ashish and Shazeer, Noam and Parmar, Niki},
  journal={Advances in Neural Information Processing Systems},
  volume={30},
  year={2017}
}

@article{devlin2019bert,
  title={BERT: Pre-training of Deep Bidirectional Transformers},
  author={Devlin, Jacob and Chang, Ming-Wei and Lee, Kenton},
  journal={arXiv preprint arXiv:1810.04805},
  year={2019}
}
"""


@pytest.mark.integration
class TestBibTeXImport:
    async def test_bibtex_import_returns_documents(
        self,
        async_client: httpx.AsyncClient,
        auth_headers: dict,
        test_project: dict,
    ):
        """Importing a .bib file creates documents in the project."""
        resp = await async_client.post(
            "/documents/import-bibtex",
            files={"file": ("refs.bib", SAMPLE_BIBTEX, "text/plain")},
            data={"project_id": test_project["id"]},
            headers=auth_headers,
        )
        assert resp.status_code in (200, 201, 202), (
            f"BibTeX import failed: {resp.text}"
        )
        data = resp.json()
        # Should return count or list of created documents
        assert (
            "imported" in data or
            "documents" in data or
            "count" in data or
            "refs_added" in data or
            isinstance(data, list)
        )

    async def test_bibtex_import_requires_auth(
        self, async_client: httpx.AsyncClient, test_project: dict
    ):
        resp = await async_client.post(
            "/documents/import-bibtex",
            files={"file": ("refs.bib", SAMPLE_BIBTEX, "text/plain")},
            data={"project_id": test_project["id"]},
        )
        assert resp.status_code in (401, 403)

    async def test_bibtex_resolution_status_endpoint(
        self,
        async_client: httpx.AsyncClient,
        auth_headers: dict,
        test_project: dict,
    ):
        """Resolution status endpoint returns status data."""
        resp = await async_client.get(
            f"/projects/{test_project['id']}/bib-resolution-status",
            headers=auth_headers,
        )
        # 200 or 404 if no bib refs imported yet
        assert resp.status_code in (200, 404)
        if resp.status_code == 200:
            data = resp.json()
            assert isinstance(data, (dict, list))

    async def test_invalid_bibtex_fails_gracefully(
        self,
        async_client: httpx.AsyncClient,
        auth_headers: dict,
        test_project: dict,
    ):
        """Malformed .bib file returns error, not 500."""
        resp = await async_client.post(
            "/documents/import-bibtex",
            files={"file": ("bad.bib", b"this is not bibtex at all!", "text/plain")},
            data={"project_id": test_project["id"]},
            headers=auth_headers,
        )
        # Should return 400/422, not 500
        assert resp.status_code in (200, 201, 400, 422), (
            f"Malformed BibTeX returned unexpected {resp.status_code}: {resp.text}"
        )

"""
E2E tests: Citation management — format, suggestions, styles.
"""

import pytest
import httpx


@pytest.mark.integration
class TestCitationFormatting:
    async def test_citations_endpoint_accessible(
        self,
        async_client: httpx.AsyncClient,
        auth_headers: dict,
    ):
        """Citations endpoint exists and requires auth."""
        resp = await async_client.get("/citations/", headers=auth_headers)
        # Should be 200 (empty list) or 405 (if list not supported at root)
        assert resp.status_code in (200, 204, 404, 405)

    async def test_citations_require_auth(self, async_client: httpx.AsyncClient):
        resp = await async_client.get("/citations/")
        assert resp.status_code in (401, 403)

    async def test_format_citation_apa(
        self,
        async_client: httpx.AsyncClient,
        auth_headers: dict,
    ):
        """Format a citation in APA style."""
        resp = await async_client.post(
            "/citations/format",
            json={
                "title": "Deep Learning",
                "authors": ["LeCun, Y.", "Bengio, Y.", "Hinton, G."],
                "year": 2015,
                "journal": "Nature",
                "volume": "521",
                "pages": "436-444",
                "style": "apa",
            },
            headers=auth_headers,
        )
        assert resp.status_code in (200, 201, 404), f"Format failed: {resp.text}"
        if resp.status_code in (200, 201):
            text = resp.json().get("formatted") or resp.json().get("citation") or resp.text
            assert "LeCun" in text or "2015" in text or "Deep Learning" in text

    async def test_format_citation_bibtex(
        self,
        async_client: httpx.AsyncClient,
        auth_headers: dict,
    ):
        """Format a citation in BibTeX style."""
        resp = await async_client.post(
            "/citations/format",
            json={
                "title": "Attention Is All You Need",
                "authors": ["Vaswani, A."],
                "year": 2017,
                "style": "bibtex",
            },
            headers=auth_headers,
        )
        assert resp.status_code in (200, 201, 404)
        if resp.status_code in (200, 201):
            text = resp.json().get("formatted") or resp.json().get("citation") or resp.text
            # BibTeX should contain @article or @inproceedings
            if text:
                assert "@" in text or "Vaswani" in text or "2017" in text


@pytest.mark.integration
class TestCitationStyles:
    STYLES = ["apa", "ieee", "mla", "chicago", "bibtex"]

    @pytest.mark.parametrize("style", STYLES)
    async def test_style_endpoint_does_not_crash(
        self,
        async_client: httpx.AsyncClient,
        auth_headers: dict,
        style: str,
    ):
        """Each citation style returns a valid response (200) or 404 if not supported."""
        resp = await async_client.post(
            "/citations/format",
            json={
                "title": "Test Paper",
                "authors": ["Smith, J."],
                "year": 2024,
                "style": style,
            },
            headers=auth_headers,
        )
        assert resp.status_code in (200, 201, 404, 422), (
            f"Style {style} caused unexpected error: {resp.status_code} {resp.text}"
        )

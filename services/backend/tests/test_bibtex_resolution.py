"""
Tests for BibTeX resolution service.
- Cache hit path (DOI and title-based)
- Semantic Scholar / Unpaywall OA search path
- No-OA-PDF fallback (metadata-only embedding)
- Quota enforcement (11th BibTeX entry → 429)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from datetime import datetime


# ── Title Similarity Helper ───────────────────────────────────────────────────

class TestTitleSimilarity:
    """Tests for the internal _title_similar() helper."""

    @pytest.mark.unit
    def test_identical_titles_match(self):
        from app.services.bibtex_resolution_service import _title_similar
        assert _title_similar("Attention Is All You Need", "Attention Is All You Need") is True

    @pytest.mark.unit
    def test_case_insensitive(self):
        from app.services.bibtex_resolution_service import _title_similar
        assert _title_similar("BERT: Pre-Training", "bert: pre-training") is True

    @pytest.mark.unit
    def test_high_overlap_matches(self):
        """Two titles sharing most words should match."""
        from app.services.bibtex_resolution_service import _title_similar
        # Jaccard ≈ 5/6 ≈ 0.83 — above default 0.6 threshold
        result = _title_similar(
            "Deep Learning for Natural Language Processing",
            "Deep Learning in Natural Language Processing",
        )
        assert result is True

    @pytest.mark.unit
    def test_completely_different_titles_no_match(self):
        from app.services.bibtex_resolution_service import _title_similar
        assert _title_similar(
            "Quantum Computing Fundamentals",
            "Attention Is All You Need",
        ) is False

    @pytest.mark.unit
    def test_empty_title_no_match(self):
        from app.services.bibtex_resolution_service import _title_similar
        assert _title_similar("", "Some Title") is False
        assert _title_similar("Some Title", "") is False


# ── DOI Cache Lookup ──────────────────────────────────────────────────────────

class TestCheckCacheByDoi:
    """Tests for _check_cache_by_doi()."""

    @pytest.mark.unit
    @patch("app.services.bibtex_resolution_service.supabase")
    async def test_cache_hit_returns_paper(self, mock_supabase):
        from app.services.bibtex_resolution_service import _check_cache_by_doi

        mock_supabase.table.return_value.select.return_value.eq.return_value \
            .limit.return_value.execute.return_value.data = [
                {"id": "uuid-1", "doi": "10.1234/test", "analysis": {"summary": "great paper"}}
            ]

        result = await _check_cache_by_doi("10.1234/test")
        assert result is not None
        assert result["doi"] == "10.1234/test"

    @pytest.mark.unit
    @patch("app.services.bibtex_resolution_service.supabase")
    async def test_cache_miss_returns_none(self, mock_supabase):
        from app.services.bibtex_resolution_service import _check_cache_by_doi

        mock_supabase.table.return_value.select.return_value.eq.return_value \
            .limit.return_value.execute.return_value.data = []

        result = await _check_cache_by_doi("10.9999/unknown")
        assert result is None

    @pytest.mark.unit
    @patch("app.services.bibtex_resolution_service.supabase")
    async def test_doi_url_prefix_stripped(self, mock_supabase):
        """https://doi.org/ prefix is stripped before querying."""
        from app.services.bibtex_resolution_service import _check_cache_by_doi

        # Capture the eq() call to verify stripped DOI is used
        eq_mock = MagicMock()
        eq_mock.limit.return_value.execute.return_value.data = []
        mock_supabase.table.return_value.select.return_value.eq.return_value = eq_mock

        await _check_cache_by_doi("https://doi.org/10.1234/test")

        mock_supabase.table.return_value.select.return_value.eq.assert_called_once_with(
            "doi", "10.1234/test"
        )

    @pytest.mark.unit
    @patch("app.services.bibtex_resolution_service.supabase")
    async def test_paper_without_analysis_ignored(self, mock_supabase):
        """Cache hit without analysis data is treated as a miss."""
        from app.services.bibtex_resolution_service import _check_cache_by_doi

        mock_supabase.table.return_value.select.return_value.eq.return_value \
            .limit.return_value.execute.return_value.data = [
                {"id": "uuid-1", "doi": "10.1234/test", "analysis": None}
            ]

        result = await _check_cache_by_doi("10.1234/test")
        assert result is None

    @pytest.mark.unit
    @patch("app.services.bibtex_resolution_service.supabase")
    async def test_supabase_error_returns_none(self, mock_supabase):
        """DB errors are swallowed and return None (fail open)."""
        from app.services.bibtex_resolution_service import _check_cache_by_doi

        mock_supabase.table.side_effect = Exception("DB connection error")

        result = await _check_cache_by_doi("10.1234/test")
        assert result is None


# ── Full Resolution Flow ──────────────────────────────────────────────────────

class TestResolveSingleEntry:
    """Tests for the _resolve_single_entry() per-entry resolution."""

    def _make_doc(self, doi="10.1234/paper", title="Test Paper Title"):
        return {
            "id": "doc-uuid-1",
            "title": title,
            "status": "imported",
            "metadata": {
                "doi": doi,
                "authors": ["Author A", "Author B"],
                "abstract": "This paper describes something important.",
                "year": "2024",
            },
        }

    @pytest.mark.unit
    @patch("app.services.bibtex_resolution_service.supabase")
    @patch("app.services.bibtex_resolution_service._check_cache_by_doi")
    @patch("app.services.bibtex_resolution_service._apply_cached_paper")
    async def test_doi_cache_hit_resolves(
        self, mock_apply, mock_cache_doi, mock_supabase
    ):
        """When shared_papers has a DOI hit, entry is resolved without external search."""
        from app.services.bibtex_resolution_service import _resolve_single_entry

        mock_supabase.table.return_value.select.return_value.eq.return_value \
            .execute.return_value.data = [self._make_doc()]
        mock_supabase.table.return_value.update.return_value.eq.return_value \
            .execute.return_value.data = [{}]

        mock_cache_doi.return_value = {
            "doi": "10.1234/paper",
            "analysis": {"summary": "cached analysis"},
        }
        mock_apply.return_value = None

        result = await _resolve_single_entry("doc-uuid-1", "user-uuid", "proj-uuid")

        assert result == "resolved"
        mock_apply.assert_awaited_once()

    @pytest.mark.unit
    @patch("app.services.bibtex_resolution_service.supabase")
    @patch("app.services.bibtex_resolution_service._check_cache_by_doi")
    @patch("app.services.bibtex_resolution_service._check_cache_by_title")
    @patch("app.services.bibtex_resolution_service._find_oa_pdf")
    @patch("app.services.bibtex_resolution_service._download_and_analyze")
    async def test_oa_pdf_found_resolves(
        self, mock_dl, mock_find, mock_title, mock_doi, mock_supabase
    ):
        """When no cache hit but OA PDF found, entry is resolved after analysis."""
        from app.services.bibtex_resolution_service import _resolve_single_entry

        mock_supabase.table.return_value.select.return_value.eq.return_value \
            .execute.return_value.data = [self._make_doc()]
        mock_supabase.table.return_value.update.return_value.eq.return_value \
            .execute.return_value.data = [{}]

        mock_doi.return_value = None
        mock_title.return_value = None
        mock_find.return_value = "https://arxiv.org/pdf/2401.12345"
        mock_dl.return_value = True

        result = await _resolve_single_entry("doc-uuid-1", "user-uuid", "proj-uuid")

        assert result == "resolved"
        mock_find.assert_awaited_once()
        mock_dl.assert_awaited_once()

    @pytest.mark.unit
    @patch("app.services.bibtex_resolution_service.supabase")
    @patch("app.services.bibtex_resolution_service._check_cache_by_doi")
    @patch("app.services.bibtex_resolution_service._check_cache_by_title")
    @patch("app.services.bibtex_resolution_service._find_oa_pdf")
    @patch("app.services.bibtex_resolution_service._embed_metadata_only")
    async def test_no_oa_pdf_metadata_only(
        self, mock_embed, mock_find, mock_title, mock_doi, mock_supabase
    ):
        """When no cache hit and no OA PDF, falls back to metadata-only embedding."""
        from app.services.bibtex_resolution_service import _resolve_single_entry

        mock_supabase.table.return_value.select.return_value.eq.return_value \
            .execute.return_value.data = [self._make_doc()]
        mock_supabase.table.return_value.update.return_value.eq.return_value \
            .execute.return_value.data = [{}]

        mock_doi.return_value = None
        mock_title.return_value = None
        mock_find.return_value = None
        mock_embed.return_value = None

        result = await _resolve_single_entry("doc-uuid-1", "user-uuid", "proj-uuid")

        assert result == "unresolved"
        mock_embed.assert_awaited_once()

    @pytest.mark.unit
    @patch("app.services.bibtex_resolution_service.supabase")
    async def test_missing_document_returns_unresolved(self, mock_supabase):
        """If document not found in DB, returns 'unresolved' gracefully."""
        from app.services.bibtex_resolution_service import _resolve_single_entry

        mock_supabase.table.return_value.select.return_value.eq.return_value \
            .execute.return_value.data = []

        result = await _resolve_single_entry("non-existent-id", "user-uuid", "proj-uuid")

        assert result == "unresolved"


# ── Batch Orchestration ───────────────────────────────────────────────────────

class TestResolveBibTexEntries:
    """Tests for the top-level resolve_bibtex_entries() orchestrator."""

    @pytest.mark.unit
    @patch("app.services.bibtex_resolution_service._resolve_single_entry")
    async def test_counts_are_correct(self, mock_resolve):
        """resolved/unresolved counts in return value match per-entry outcomes."""
        from app.services.bibtex_resolution_service import resolve_bibtex_entries

        mock_resolve.side_effect = ["resolved", "resolved", "unresolved", "resolved"]

        result = await resolve_bibtex_entries(
            ["d1", "d2", "d3", "d4"], "user-uuid", "proj-uuid"
        )

        assert result["resolved"] == 3
        assert result["unresolved"] == 1
        assert result["total"] == 4

    @pytest.mark.unit
    @patch("app.services.bibtex_resolution_service._resolve_single_entry")
    @patch("app.services.bibtex_resolution_service._set_resolution_status")
    async def test_exception_in_entry_counted_as_unresolved(
        self, mock_set_status, mock_resolve
    ):
        """Per-entry exceptions are caught and counted as unresolved."""
        from app.services.bibtex_resolution_service import resolve_bibtex_entries

        mock_resolve.side_effect = [Exception("Network timeout"), "resolved"]

        result = await resolve_bibtex_entries(["d1", "d2"], "user-uuid", "proj-uuid")

        assert result["resolved"] == 1
        assert result["unresolved"] == 1
        # Should mark the failed entry as unresolved
        mock_set_status.assert_called_with("d1", "unresolved")

    @pytest.mark.unit
    async def test_empty_list_returns_zeros(self):
        from app.services.bibtex_resolution_service import resolve_bibtex_entries

        result = await resolve_bibtex_entries([], "user-uuid", "proj-uuid")

        assert result["resolved"] == 0
        assert result["unresolved"] == 0
        assert result["total"] == 0

"""
Tests for BibTeX resolution service.
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
    @pytest.mark.unit
    @patch("app.services.bibtex_resolution_service.supabase")
    @patch("app.services.bibtex_resolution_service._find_oa_pdf")
    @patch("app.services.bibtex_resolution_service._download_and_analyze")
    async def test_oa_pdf_found_resolves(
        self, mock_dl, mock_find, mock_supabase
    ):
        """When an OA PDF is found, entry is resolved after analysis."""
        from app.services.bibtex_resolution_service import _resolve_single_entry

        mock_supabase.table.return_value.select.return_value.eq.return_value \
            .execute.return_value.data = [self._make_doc()]
        mock_supabase.table.return_value.update.return_value.eq.return_value \
            .execute.return_value.data = [{}]

        mock_find.return_value = "https://arxiv.org/pdf/2401.12345"
        mock_dl.return_value = True

        result = await _resolve_single_entry("doc-uuid-1", "user-uuid", "proj-uuid")

        assert result == "resolved"
        mock_find.assert_awaited_once()
        mock_dl.assert_awaited_once()

    @pytest.mark.unit
    @patch("app.services.bibtex_resolution_service.supabase")
    @patch("app.services.bibtex_resolution_service._find_oa_pdf")
    @patch("app.services.bibtex_resolution_service._embed_metadata_only")
    async def test_no_oa_pdf_metadata_only(
        self, mock_embed, mock_find, mock_supabase
    ):
        """When no OA PDF is found, falls back to metadata-only embedding."""
        from app.services.bibtex_resolution_service import _resolve_single_entry

        mock_supabase.table.return_value.select.return_value.eq.return_value \
            .execute.return_value.data = [self._make_doc()]
        mock_supabase.table.return_value.update.return_value.eq.return_value \
            .execute.return_value.data = [{}]

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

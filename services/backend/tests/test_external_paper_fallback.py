"""
Unit tests for external paper fallback in coverage_analysis.

Tests:
- _normalize_external_paper: field mapping for SS and OA papers
- _fetch_external_papers_for_gap: SS-first, OA-cascade, dedup, caps
- suggest_papers_for_gaps: threshold-based fallback triggering
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SS_PAPER = {
    "title": "Attention Is All You Need",
    "authors": ["Ashish Vaswani", "Noam Shazeer"],
    "year": 2017,
    "abstract": "We propose the Transformer architecture.",
    "paper_url": "https://www.semanticscholar.org/paper/abc123",
    "pdf_url": "https://arxiv.org/pdf/1706.03762",
    "citation_count": 50000,
}

OA_PAPER = {
    "title": "BERT: Pre-training of Deep Bidirectional Transformers",
    "authors": ["Jacob Devlin", "Ming-Wei Chang"],
    "year": 2019,
    "abstract": "We introduce BERT.",
    "open_access_url": "https://arxiv.org/pdf/1810.04805",
    "cited_by_count": 60000,
}


def _make_embedding():
    mock_emb = MagicMock()
    mock_emb.embedding = [0.1] * 1536
    return mock_emb


def _make_gap(description: str = "missing transformer coverage") -> dict:
    return {"description": description, "gap_type": "missing_seminal", "priority": "high"}


# ---------------------------------------------------------------------------
# _normalize_external_paper
# ---------------------------------------------------------------------------

class TestNormalizeExternalPaper:

    @pytest.mark.unit
    def test_normalize_semantic_scholar_paper(self):
        """Semantic Scholar paper maps to correct fields."""
        from app.services.coverage_analysis import _normalize_external_paper

        result = _normalize_external_paper(SS_PAPER, "semantic_scholar")

        assert result["title"] == "Attention Is All You Need"
        assert result["authors"] == ["Ashish Vaswani", "Noam Shazeer"]
        assert result["year"] == 2017
        assert result["source"] == "semantic_scholar"
        assert result["citation_count"] == 50000
        # pdf_url maps to open_access_url
        assert result["open_access_url"] == "https://arxiv.org/pdf/1706.03762"
        # paper_url maps to url
        assert result["url"] == "https://www.semanticscholar.org/paper/abc123"

    @pytest.mark.unit
    def test_normalize_openalex_paper(self):
        """OpenAlex paper maps to correct fields."""
        from app.services.coverage_analysis import _normalize_external_paper

        result = _normalize_external_paper(OA_PAPER, "open_access")

        assert result["title"] == "BERT: Pre-training of Deep Bidirectional Transformers"
        assert result["authors"] == ["Jacob Devlin", "Ming-Wei Chang"]
        assert result["year"] == 2019
        assert result["source"] == "open_access"
        assert result["open_access_url"] == "https://arxiv.org/pdf/1810.04805"
        # cited_by_count maps to citation_count
        assert result["citation_count"] == 60000

    @pytest.mark.unit
    def test_normalize_sets_external_true(self):
        """external flag is always True regardless of source."""
        from app.services.coverage_analysis import _normalize_external_paper

        assert _normalize_external_paper(SS_PAPER, "semantic_scholar")["external"] is True
        assert _normalize_external_paper(OA_PAPER, "open_access")["external"] is True

    @pytest.mark.unit
    def test_normalize_missing_fields_defaults(self):
        """Empty dict produces safe defaults — no KeyError raised."""
        from app.services.coverage_analysis import _normalize_external_paper

        result = _normalize_external_paper({}, "semantic_scholar")

        assert result["title"] == ""
        assert result["authors"] == []
        assert result["year"] is None
        assert result["abstract"] == ""
        assert result["relevance_score"] == 0.5
        assert result["citation_count"] == 0
        assert result["url"] == ""
        assert result["open_access_url"] == ""
        assert result["external"] is True


# ---------------------------------------------------------------------------
# _fetch_external_papers_for_gap
# ---------------------------------------------------------------------------

class TestFetchExternalPapersForGap:

    @pytest.mark.unit
    @patch("app.services.coverage_analysis.asyncio.to_thread")
    async def test_fetch_returns_ss_results(self, mock_to_thread):
        """When SS returns enough papers, OA is never called."""
        from app.services.coverage_analysis import _fetch_external_papers_for_gap

        ss_papers = [{**SS_PAPER, "title": f"SS Paper {i}"} for i in range(3)]
        mock_to_thread.return_value = ss_papers  # to_thread is awaited by asyncio

        # Wrap the mock to return a coroutine
        async def fake_to_thread(fn, *args, **kwargs):
            return ss_papers

        with patch("app.services.coverage_analysis.asyncio.to_thread", side_effect=fake_to_thread), \
             patch("app.services.external_apis.openalex.find_open_access_papers_for_gap") as mock_oa:

            results = await _fetch_external_papers_for_gap("transformer models", needed=3)

        mock_oa.assert_not_called()
        assert len(results) == 3
        assert all(r["source"] == "semantic_scholar" for r in results)

    @pytest.mark.unit
    async def test_fetch_cascades_to_openalex(self):
        """When SS returns 0 papers, OA is called as fallback."""
        from app.services.coverage_analysis import _fetch_external_papers_for_gap

        oa_papers = [{**OA_PAPER, "title": f"OA Paper {i}"} for i in range(2)]

        async def fake_to_thread(fn, *args, **kwargs):
            return []  # SS returns empty

        with patch("app.services.coverage_analysis.asyncio.to_thread", side_effect=fake_to_thread), \
             patch("app.services.external_apis.openalex.find_open_access_papers_for_gap",
                   new=AsyncMock(return_value=oa_papers)):

            results = await _fetch_external_papers_for_gap("transformer models", needed=2)

        assert len(results) == 2
        assert all(r["source"] == "open_access" for r in results)

    @pytest.mark.unit
    async def test_fetch_deduplicates_by_title(self):
        """Same title from SS and OA appears only once in results."""
        from app.services.coverage_analysis import _fetch_external_papers_for_gap

        shared_title = "Attention Is All You Need"
        ss_paper = {**SS_PAPER, "title": shared_title}
        oa_paper = {**OA_PAPER, "title": shared_title}

        async def fake_to_thread(fn, *args, **kwargs):
            return [ss_paper]

        with patch("app.services.coverage_analysis.asyncio.to_thread", side_effect=fake_to_thread), \
             patch("app.services.external_apis.openalex.find_open_access_papers_for_gap",
                   new=AsyncMock(return_value=[oa_paper])):

            # needed=2 so OA cascade triggers (SS gave 1 < 2)
            results = await _fetch_external_papers_for_gap(shared_title, needed=2)

        titles = [r["title"] for r in results]
        assert titles.count(shared_title) == 1

    @pytest.mark.unit
    async def test_fetch_caps_at_max_external(self):
        """Results are capped at max_external even if APIs return more."""
        from app.services.coverage_analysis import _fetch_external_papers_for_gap

        ss_papers = [{**SS_PAPER, "title": f"Unique Paper {i}"} for i in range(10)]

        async def fake_to_thread(fn, *args, **kwargs):
            return ss_papers

        with patch("app.services.coverage_analysis.asyncio.to_thread", side_effect=fake_to_thread):
            results = await _fetch_external_papers_for_gap("topic", needed=3, max_external=5)

        assert len(results) == 5

    @pytest.mark.unit
    async def test_fetch_ss_failure_falls_back_gracefully(self):
        """SS exception is caught and OA is still attempted."""
        from app.services.coverage_analysis import _fetch_external_papers_for_gap

        oa_papers = [{**OA_PAPER, "title": "OpenAlex Only Paper"}]

        async def fake_to_thread(fn, *args, **kwargs):
            raise Exception("SS network error")

        with patch("app.services.coverage_analysis.asyncio.to_thread", side_effect=fake_to_thread), \
             patch("app.services.external_apis.openalex.find_open_access_papers_for_gap",
                   new=AsyncMock(return_value=oa_papers)):

            results = await _fetch_external_papers_for_gap("transformer", needed=1)

        assert len(results) == 1
        assert results[0]["source"] == "open_access"

    @pytest.mark.unit
    async def test_fetch_both_fail_returns_empty_list(self):
        """Both SS and OA failing returns [] without raising."""
        from app.services.coverage_analysis import _fetch_external_papers_for_gap

        async def fake_to_thread(fn, *args, **kwargs):
            raise Exception("SS down")

        with patch("app.services.coverage_analysis.asyncio.to_thread", side_effect=fake_to_thread), \
             patch("app.services.external_apis.openalex.find_open_access_papers_for_gap",
                   new=AsyncMock(side_effect=Exception("OA down"))):

            results = await _fetch_external_papers_for_gap("topic", needed=3)

        assert results == []


# ---------------------------------------------------------------------------
# suggest_papers_for_gaps — threshold-based fallback triggering
# ---------------------------------------------------------------------------

def _setup_supabase_mock(mock_sb, doc_ids: list[str]):
    """Helper: configure supabase mock to return N docs from vector search."""
    mock_search = MagicMock()
    mock_search.data = [{"document_id": d, "similarity": 0.85} for d in doc_ids]
    mock_sb.rpc.return_value.execute.return_value = mock_search

    def make_doc(doc_id):
        m = MagicMock()
        m.data = {
            "id": doc_id,
            "title": f"Local Paper {doc_id[-1]}",
            "analysis": {
                "citation_metadata": {"all_authors": [], "year": "2021"},
                "executive_summary": "",
                "key_findings": [],
            },
        }
        return m

    mock_sb.table.return_value.select.return_value.eq.return_value \
        .single.return_value.execute.side_effect = [make_doc(d) for d in doc_ids]


class TestSuggestPapersForGaps:

    @pytest.mark.unit
    @patch("app.services.coverage_analysis.supabase")
    @patch("app.services.coverage_analysis._fetch_external_papers_for_gap")
    @patch("app.services.rag_ingest.embed_chunks")
    async def test_suggest_papers_no_fallback_when_enough_local(
        self, mock_embed, mock_ext, mock_sb
    ):
        """4 local papers (above threshold=3) → external fallback not triggered."""
        from app.services.coverage_analysis import suggest_papers_for_gaps

        mock_embed.return_value = [_make_embedding()]
        mock_ext.return_value = []

        doc_ids = [f"doc-{i}" for i in range(4)]
        _setup_supabase_mock(mock_sb, doc_ids)

        gaps = [_make_gap()]
        await suggest_papers_for_gaps(gaps, "proj-1", max_suggestions_per_gap=4)

        mock_ext.assert_not_called()

    @pytest.mark.unit
    @patch("app.services.coverage_analysis.supabase")
    @patch("app.services.coverage_analysis._fetch_external_papers_for_gap")
    @patch("app.services.rag_ingest.embed_chunks")
    async def test_suggest_papers_triggers_fallback_below_threshold(
        self, mock_embed, mock_ext, mock_sb
    ):
        """1 local paper (below threshold=3) → external fallback is called."""
        from app.services.coverage_analysis import suggest_papers_for_gaps

        mock_embed.return_value = [_make_embedding()]
        mock_ext.return_value = []

        _setup_supabase_mock(mock_sb, ["doc-1"])

        gaps = [_make_gap()]
        await suggest_papers_for_gaps(gaps, "proj-1", max_suggestions_per_gap=3)

        mock_ext.assert_called_once()

    @pytest.mark.unit
    @patch("app.services.coverage_analysis.supabase")
    @patch("app.services.coverage_analysis._fetch_external_papers_for_gap")
    @patch("app.services.rag_ingest.embed_chunks")
    async def test_suggest_papers_external_appended_to_local(
        self, mock_embed, mock_ext, mock_sb
    ):
        """Local paper + 2 external papers → all present in suggested_papers."""
        from app.services.coverage_analysis import suggest_papers_for_gaps

        mock_embed.return_value = [_make_embedding()]

        external_papers = [
            {**OA_PAPER, "title": f"External {i}", "external": True,
             "source": "open_access", "open_access_url": "", "url": "",
             "citation_count": 100, "relevance_score": 0.5, "abstract": ""}
            for i in range(2)
        ]
        mock_ext.return_value = external_papers

        _setup_supabase_mock(mock_sb, ["doc-1"])

        gaps = [_make_gap()]
        result = await suggest_papers_for_gaps(gaps, "proj-1", max_suggestions_per_gap=3)

        papers = result[0]["suggested_papers"]
        local = [p for p in papers if not p.get("external")]
        ext = [p for p in papers if p.get("external")]

        assert len(local) == 1
        assert len(ext) == 2
        assert local[0]["title"] == "Local Paper 1"

    @pytest.mark.unit
    @patch("app.services.coverage_analysis.supabase")
    @patch("app.services.coverage_analysis._fetch_external_papers_for_gap",
           new_callable=AsyncMock)
    @patch("app.services.rag_ingest.embed_chunks")
    async def test_suggest_papers_fallback_fails_silently(
        self, mock_embed, mock_ext, mock_sb
    ):
        """External fetch raises → local papers still returned, no exception."""
        from app.services.coverage_analysis import suggest_papers_for_gaps

        mock_embed.return_value = [_make_embedding()]
        mock_ext.side_effect = Exception("external API down")

        _setup_supabase_mock(mock_sb, ["doc-1"])

        gaps = [_make_gap()]
        # Should not raise
        result = await suggest_papers_for_gaps(gaps, "proj-1", max_suggestions_per_gap=3)

        assert result[0]["suggested_papers"] is not None
        local = [p for p in result[0]["suggested_papers"] if not p.get("external")]
        assert len(local) == 1

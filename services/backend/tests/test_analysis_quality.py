"""
Tests for analysis quality improvements:
- OpenAlex API client
- Evidence-grounded reviewer feedback
- Embedding-based gap detection
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


# ── OpenAlex API Client Tests ─────────────────────────────────────────────────

class TestOpenAlexClient:
    """Tests for the OpenAlex API client."""

    @pytest.mark.unit
    def test_reconstruct_abstract_basic(self):
        """Test abstract reconstruction from inverted index."""
        from app.services.external_apis.openalex import _reconstruct_abstract

        inverted = {
            "The": [0],
            "quick": [1],
            "brown": [2],
            "fox": [3],
        }
        result = _reconstruct_abstract(inverted)
        assert result == "The quick brown fox"

    @pytest.mark.unit
    def test_reconstruct_abstract_none(self):
        """Test abstract reconstruction with None input."""
        from app.services.external_apis.openalex import _reconstruct_abstract

        assert _reconstruct_abstract(None) is None
        assert _reconstruct_abstract({}) is None

    @pytest.mark.unit
    def test_format_paper_basic(self):
        """Test paper formatting from OpenAlex work object."""
        from app.services.external_apis.openalex import _format_paper

        work = {
            "id": "https://openalex.org/W123",
            "display_name": "Attention Is All You Need",
            "publication_year": 2017,
            "doi": "https://doi.org/10.48550/arXiv.1706.03762",
            "authorships": [
                {"author": {"display_name": "Ashish Vaswani"}},
                {"author": {"display_name": "Noam Shazeer"}},
            ],
            "open_access": {"is_oa": True, "oa_url": "https://arxiv.org/pdf/1706.03762"},
            "primary_location": {
                "source": {"display_name": "arXiv"}
            },
            "cited_by_count": 50000,
            "concepts": [
                {"display_name": "Transformer", "score": 0.9},
                {"display_name": "Attention mechanism", "score": 0.85},
            ],
            "abstract_inverted_index": {"Transformers": [0], "are": [1], "great": [2]},
        }

        paper = _format_paper(work)

        assert paper["title"] == "Attention Is All You Need"
        assert paper["year"] == 2017
        assert paper["doi"] == "10.48550/arXiv.1706.03762"  # URL stripped
        assert paper["open_access_url"] == "https://arxiv.org/pdf/1706.03762"
        assert paper["is_open_access"] is True
        assert "Ashish Vaswani" in paper["authors"]
        assert paper["cited_by_count"] == 50000
        assert "Transformer" in paper["concepts"]

    @pytest.mark.unit
    @patch("aiohttp.ClientSession")
    async def test_search_works_success(self, mock_session_cls):
        """Test search_works returns formatted papers."""
        from app.services.external_apis.openalex import search_works

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "results": [
                {
                    "id": "W1",
                    "display_name": "Test Paper",
                    "publication_year": 2024,
                    "doi": "https://doi.org/10.1234/test",
                    "authorships": [{"author": {"display_name": "Jane Doe"}}],
                    "open_access": {"is_oa": False, "oa_url": None},
                    "primary_location": None,
                    "cited_by_count": 10,
                    "concepts": [],
                    "abstract_inverted_index": None,
                }
            ]
        })

        # Set up async context manager
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session.get.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_session_cls.return_value = mock_session

        results = await search_works("transformer attention", per_page=5)

        assert len(results) == 1
        assert results[0]["title"] == "Test Paper"

    @pytest.mark.unit
    @patch("aiohttp.ClientSession")
    async def test_search_works_timeout_returns_empty(self, mock_session_cls):
        """Test that timeout returns empty list (doesn't raise)."""
        import aiohttp
        from app.services.external_apis.openalex import search_works

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.get.side_effect = asyncio.TimeoutError()
        mock_session_cls.return_value = mock_session

        results = await search_works("test query")
        assert results == []

    @pytest.mark.unit
    @patch("aiohttp.ClientSession")
    async def test_find_open_access_papers_for_gap(self, mock_session_cls):
        """Test that gap paper finder only returns papers with OA URLs."""
        from app.services.external_apis.openalex import find_open_access_papers_for_gap

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "results": [
                {
                    "id": "W1",
                    "display_name": "OA Paper",
                    "publication_year": 2024,
                    "doi": "https://doi.org/10.1234/oa",
                    "authorships": [],
                    "open_access": {"is_oa": True, "oa_url": "https://arxiv.org/pdf/test"},
                    "primary_location": None,
                    "cited_by_count": 5,
                    "concepts": [],
                    "abstract_inverted_index": None,
                },
                {
                    "id": "W2",
                    "display_name": "Paywalled Paper",
                    "publication_year": 2024,
                    "doi": "https://doi.org/10.1234/paywalled",
                    "authorships": [],
                    "open_access": {"is_oa": False, "oa_url": None},
                    "primary_location": None,
                    "cited_by_count": 50,
                    "concepts": [],
                    "abstract_inverted_index": None,
                },
            ]
        })

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session.get.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_session_cls.return_value = mock_session

        papers = await find_open_access_papers_for_gap("machine learning methods", limit=3)

        # Should only return the OA paper
        assert len(papers) == 1
        assert papers[0]["open_access_url"] == "https://arxiv.org/pdf/test"


# ── Reviewer Feedback Node Tests ──────────────────────────────────────────────

class TestReviewerFeedbackNode:
    """Tests for evidence-grounded reviewer feedback generation."""

    @pytest.mark.unit
    def test_build_literature_context_empty(self):
        """Empty search results produce empty context string."""
        from app.workflows.draft_analysis.nodes.reviewer_feedback import _build_literature_context

        result = _build_literature_context([])
        assert result == ""

    @pytest.mark.unit
    def test_build_literature_context_basic(self):
        """Literature context includes paper titles and excerpts."""
        from app.workflows.draft_analysis.nodes.reviewer_feedback import _build_literature_context

        search_results = [
            {
                "claim_id": "c1",
                "results": [
                    {
                        "document_title": "Attention Is All You Need",
                        "authors": "Vaswani et al.",
                        "year": "2017",
                        "content": "We propose a new simple network architecture, the Transformer.",
                        "similarity": 0.85,
                    }
                ]
            }
        ]

        context = _build_literature_context(search_results)

        assert "Attention Is All You Need" in context
        assert "RETRIEVED LITERATURE" in context
        assert "Transformer" in context

    @pytest.mark.unit
    def test_build_literature_context_deduplication(self):
        """Same paper title is deduplicated across claim results."""
        from app.workflows.draft_analysis.nodes.reviewer_feedback import _build_literature_context

        # Same paper appears in two different claim searches
        search_results = [
            {
                "claim_id": "c1",
                "results": [{"document_title": "Paper A", "content": "Content A", "similarity": 0.8}]
            },
            {
                "claim_id": "c2",
                "results": [{"document_title": "Paper A", "content": "Content A again", "similarity": 0.75}]
            },
        ]

        context = _build_literature_context(search_results)

        # "Paper A" should appear only once
        assert context.count("Paper A") == 1

    @pytest.mark.unit
    def test_build_literature_context_top_5(self):
        """Context includes at most 5 papers."""
        from app.workflows.draft_analysis.nodes.reviewer_feedback import _build_literature_context

        search_results = [
            {
                "claim_id": f"c{i}",
                "results": [{"document_title": f"Paper {i}", "content": f"Content {i}", "similarity": 0.9 - i * 0.05}]
            }
            for i in range(10)  # 10 different papers
        ]

        context = _build_literature_context(search_results)

        # Count occurrences of "Paper " — should be at most 5
        paper_count = sum(1 for i in range(10) if f"Paper {i}" in context)
        assert paper_count <= 5


# ── Coverage Analysis Tests ───────────────────────────────────────────────────

class TestCoverageAnalysis:
    """Tests for embedding-based coverage gap detection."""

    @pytest.mark.unit
    def test_categorize_citation_strength_strong(self):
        """Strong citations: high similarity + multiple citations."""
        from app.services.coverage_analysis import categorize_citation_strength

        result = categorize_citation_strength(
            similarity_score=0.85,
            citation_count=3,
            claim_importance=0.8
        )
        assert result == "strong"

    @pytest.mark.unit
    def test_categorize_citation_strength_missing(self):
        """Missing citations: low similarity + no existing citations."""
        from app.services.coverage_analysis import categorize_citation_strength

        result = categorize_citation_strength(
            similarity_score=0.2,
            citation_count=0,
            claim_importance=0.8
        )
        assert result == "missing"

    @pytest.mark.unit
    def test_prioritize_gaps_sorting(self):
        """Gaps are sorted by priority: missing_seminal > others."""
        from app.services.coverage_analysis import prioritize_gaps

        gaps = [
            {"gap_type": "methodology_gap", "priority": "low", "suggested_papers": []},
            {"gap_type": "missing_seminal", "priority": "high", "suggested_papers": []},
            {"gap_type": "theoretical_gap", "priority": "medium", "suggested_papers": []},
        ]

        sorted_gaps = prioritize_gaps(gaps)

        assert sorted_gaps[0]["gap_type"] == "missing_seminal"

    @pytest.mark.unit
    def test_prioritize_gaps_suggestion_bonus(self):
        """Gaps with suggested papers get a priority boost."""
        from app.services.coverage_analysis import prioritize_gaps

        gaps = [
            {"gap_type": "methodology_gap", "priority": "high", "suggested_papers": []},
            {"gap_type": "methodology_gap", "priority": "high", "suggested_papers": [{"title": "Paper A"}]},
        ]

        sorted_gaps = prioritize_gaps(gaps)

        # Gap with suggestions should rank first
        assert sorted_gaps[0]["suggested_papers"] == [{"title": "Paper A"}]

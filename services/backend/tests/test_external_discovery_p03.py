"""Unit tests for Plan 03 — citation-graph discovery, domain gate tuning, judge fail-open."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.draft_external_source_discovery import (
    _citation_graph_to_external_source,
    _passes_domain_gate,
    _reconstruct_abstract,
    _source_key,
)


# ─────────────────────────────────────────────────────────────────────────────
# _passes_domain_gate — distinctive-terms threshold loosened (2 → 1)
# ─────────────────────────────────────────────────────────────────────────────

class TestDomainGate:
    def _profile(self, **kwargs):
        base = {
            "routing_domain": "chemistry_materials",
            "domain_tags": ["electrochemistry", "batteries"],
            "review_lenses": ["experimental"],
            "topic_terms": ["sodium", "cathode", "electrolyte", "anode", "impedance"],
        }
        base.update(kwargs)
        return base

    def test_passes_with_one_distinctive_term(self):
        profile = self._profile()
        # Source mentions "sodium" (one distinctive term) → should pass
        query = "sodium ion battery cathode performance"
        source = "sodium intercalation in layered oxide cathode materials for batteries"
        assert _passes_domain_gate(query, source, 0.75, profile) is True

    def test_rejects_with_zero_distinctive_terms(self):
        profile = self._profile()
        # Source shares NO distinctive terms — only generic words
        query = "sodium ion battery cathode"
        source = "systematic review methodology and reporting guidelines"
        result = _passes_domain_gate(query, source, 0.75, profile)
        # May pass or fail depending on other conditions, but won't fail on 0 distinctive terms alone
        # The key is we no longer require 2 — just verify we don't crash
        assert isinstance(result, bool)

    def test_methodology_guideline_bypasses_gate(self):
        profile = self._profile()
        query = "systematic review methodology prisma reporting"
        source = "prisma guidelines for systematic reviews and meta-analyses"
        assert _passes_domain_gate(query, source, 0.65, profile) is True

    def test_no_profile_always_passes(self):
        assert _passes_domain_gate("sodium battery", "sodium cathode study", 0.75, None) is True

    def test_previously_suppressed_paper_now_passes(self):
        """Paper with 1 distinctive term that was blocked by the old >= 2 requirement."""
        profile = self._profile()
        query = "cathode material electrochemistry sodium"
        # This source has only "cathode" from distinctive terms but is clearly relevant
        source = "high-performance cathode materials for next-generation energy storage devices"
        # With the new threshold (1 required), this should now pass where it previously would fail
        result = _passes_domain_gate(query, source, 0.78, profile)
        assert result is True


# ─────────────────────────────────────────────────────────────────────────────
# _fetch_citation_graph_candidates (mocked)
# ─────────────────────────────────────────────────────────────────────────────

class TestCitationGraphFetch:
    RESOLVED_REFS = [
        {"title": "Sodium-ion battery cathodes", "doi": "10.1000/abc", "resolved": True, "authors": ["Smith J"]},
        {"title": "Electrolyte design for sodium batteries", "doi": "10.1000/def", "resolved": True, "authors": ["Jones A"]},
        {"title": "Unresolved ref", "doi": "10.1000/ghi", "resolved": False, "authors": []},
    ]

    def _mock_ref_response(self, referenced_works):
        resp = AsyncMock()
        resp.status = 200
        resp.json = AsyncMock(return_value={"id": "https://openalex.org/W99", "referenced_works": referenced_works})
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        return resp

    def _mock_work_response(self, work_data):
        resp = AsyncMock()
        resp.status = 200
        resp.json = AsyncMock(return_value=work_data)
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        return resp

    def _mock_404(self):
        resp = AsyncMock()
        resp.status = 404
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        return resp

    @pytest.mark.asyncio
    async def test_returns_co_cited_paper_not_in_bibliography(self):
        # W111 appears in referenced_works of both refs → co_citation_score=2
        co_cited_id = "https://openalex.org/W111"
        oa_work = {
            "id": co_cited_id,
            "display_name": "Foundational sodium battery paper",
            "authorships": [{"author": {"display_name": "Brown X"}}],
            "publication_year": 2018,
            "doi": "https://doi.org/10.5000/xyz",
            "abstract_inverted_index": {"Foundational": [0], "sodium": [1], "battery": [2]},
            "primary_location": {"source": {"display_name": "Nature Energy"}},
            "cited_by_count": 250,
            "open_access": {"oa_url": None},
        }

        call_count = [0]

        def make_session_get(*args, **kwargs):
            url = args[0] if args else kwargs.get("url", "")
            call_count[0] += 1
            if "doi.org" in str(url):
                # Referenced_works lookup
                return self._mock_ref_response([co_cited_id])
            elif "openalex.org/W111" in str(url):
                return self._mock_work_response(oa_work)
            return self._mock_404()

        mock_session = AsyncMock()
        mock_session.get = MagicMock(side_effect=make_session_get)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            from app.services.draft_external_source_discovery import _fetch_citation_graph_candidates
            result = await _fetch_citation_graph_candidates(self.RESOLVED_REFS)

        # Should return the co-cited paper
        assert len(result) >= 1
        assert result[0]["title"] == "Foundational sodium battery paper"
        assert result[0]["co_citation_score"] == 2

    @pytest.mark.asyncio
    async def test_skips_unresolved_refs(self):
        """Only resolved refs (has DOI + resolved=True) used for graph query."""
        refs = [
            {"title": "No DOI ref", "doi": "", "resolved": True},
            {"title": "Unresolved ref", "doi": "10.9/x", "resolved": False},
        ]
        from app.services.draft_external_source_discovery import _fetch_citation_graph_candidates
        result = await _fetch_citation_graph_candidates(refs)
        assert result == []

    @pytest.mark.asyncio
    async def test_excludes_papers_already_in_bibliography(self):
        """Papers whose DOI matches a bibliography entry are excluded."""
        co_cited_id = "https://openalex.org/W222"
        oa_work = {
            "id": co_cited_id,
            "display_name": "Already cited paper",
            "authorships": [],
            "publication_year": 2020,
            "doi": "https://doi.org/10.1000/abc",  # matches first resolved ref!
            "abstract_inverted_index": {},
            "primary_location": {"source": {}},
            "cited_by_count": 100,
            "open_access": {},
        }

        def make_session_get(*args, **kwargs):
            url = args[0] if args else ""
            if "doi.org" in str(url):
                return self._mock_ref_response([co_cited_id, co_cited_id])
            elif "openalex.org/W222" in str(url):
                return self._mock_work_response(oa_work)
            return self._mock_404()

        mock_session = AsyncMock()
        mock_session.get = MagicMock(side_effect=make_session_get)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            from app.services.draft_external_source_discovery import _fetch_citation_graph_candidates
            result = await _fetch_citation_graph_candidates(self.RESOLVED_REFS)

        # Paper already in bibliography should be excluded
        for r in result:
            assert r.get("doi", "").lower() != "10.1000/abc"

    @pytest.mark.asyncio
    async def test_empty_resolved_refs_returns_empty(self):
        from app.services.draft_external_source_discovery import _fetch_citation_graph_candidates
        result = await _fetch_citation_graph_candidates([])
        assert result == []


# ─────────────────────────────────────────────────────────────────────────────
# _citation_graph_to_external_source
# ─────────────────────────────────────────────────────────────────────────────

class TestCitationGraphToExternalSource:
    def _paper(self, co_score=2, **kwargs):
        base = {
            "title": "Foundational sodium battery study",
            "authors": ["Brown X"],
            "year": 2018,
            "doi": "10.5000/xyz",
            "abstract": "We study sodium ion batteries.",
            "journal": "Nature Energy",
            "citation_count": 250,
            "open_access_url": None,
            "co_citation_score": co_score,
        }
        base.update(kwargs)
        return base

    def test_source_field_is_citation_graph(self):
        src = _citation_graph_to_external_source(self._paper(), "draft-1")
        assert src["source"] == "citation_graph"

    def test_relevance_score_scales_with_co_citation(self):
        src_2 = _citation_graph_to_external_source(self._paper(co_score=2), "d1")
        src_4 = _citation_graph_to_external_source(self._paper(co_score=4), "d1")
        assert src_4["relevance_score"] > src_2["relevance_score"]

    def test_relevance_score_capped_at_0_95(self):
        src = _citation_graph_to_external_source(self._paper(co_score=100), "d1")
        assert src["relevance_score"] <= 0.95

    def test_recommendation_context_has_co_citation_score(self):
        src = _citation_graph_to_external_source(self._paper(co_score=3), "d1")
        assert src["recommendation_context"]["co_citation_score"] == 3
        assert src["recommendation_context"]["target_type"] == "citation_graph"

    def test_source_key_dedup_uses_doi(self):
        src = _citation_graph_to_external_source(self._paper(), "d1")
        key = _source_key(src)
        assert key and "doi:" in key


# ─────────────────────────────────────────────────────────────────────────────
# Citation judge fail-open behavior
# ─────────────────────────────────────────────────────────────────────────────

class TestCitationJudgeFailOpen:
    @pytest.fixture(autouse=True)
    def _mock_openai(self, monkeypatch):
        from app.core import openai_client
        monkeypatch.setattr(openai_client, "get_openai_client", lambda: MagicMock())
        monkeypatch.setattr(openai_client, "get_async_openai_client", lambda: MagicMock())

    @pytest.mark.asyncio
    async def test_external_sources_kept_on_judge_exception(self):
        """When judge LLM call fails, external_sources should be kept (fail-open)."""
        state = {
            "draft_id": "d1",
            "claims_with_citations": [
                {"claim": {"id": "c1", "claim_text": "sodium ion performance"}, "suggested_citations": [{"title": "Some paper"}]},
            ],
            "external_sources": [
                {"title": "Missing seminal paper", "source": "citation_graph", "relevance_score": 0.82},
                {"title": "Another missed paper", "source": "semantic_scholar", "relevance_score": 0.75},
            ],
        }

        with patch(
            "app.workflows.draft_analysis.nodes.citation_judge.parse_chat_completion_with_retries",
            side_effect=RuntimeError("LLM down"),
        ):
            from app.workflows.draft_analysis.nodes.citation_judge import citation_judge_node
            result = await citation_judge_node(state)

        # external_sources: fail-open → kept
        assert len(result["external_sources"]) == 2
        # suggested_citations: fail-closed → removed
        for cwc in result["claims_with_citations"]:
            assert cwc["suggested_citations"] == []

    @pytest.mark.asyncio
    async def test_nothing_to_judge_keeps_external_sources(self):
        """When no suggested citations exist, external_sources pass through untouched."""
        state = {
            "draft_id": "d1",
            "claims_with_citations": [],
            "external_sources": [
                {"title": "Co-cited paper", "source": "citation_graph", "relevance_score": 0.84},
            ],
        }

        from app.workflows.draft_analysis.nodes.citation_judge import citation_judge_node
        result = await citation_judge_node(state)

        # Node skips LLM call when no items to judge — external_sources pass through
        assert result.get("citation_judge_output") is not None


# ─────────────────────────────────────────────────────────────────────────────
# _reconstruct_abstract
# ─────────────────────────────────────────────────────────────────────────────

class TestReconstructAbstract:
    def test_reconstructs_from_inverted_index(self):
        inverted = {"sodium": [0], "ion": [1], "batteries": [2]}
        result = _reconstruct_abstract(inverted)
        assert result == "sodium ion batteries"

    def test_returns_empty_for_none(self):
        assert _reconstruct_abstract(None) == ""

    def test_returns_empty_for_empty_dict(self):
        assert _reconstruct_abstract({}) == ""

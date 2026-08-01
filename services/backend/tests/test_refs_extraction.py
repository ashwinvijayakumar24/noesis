"""Unit tests for Plan 02 — draft reference extraction, resolution, unused detection."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.draft_reference_extraction import (
    detect_unused_refs,
    extract_refs_from_parse_artifact,
    suggest_refs_for_weak_claims,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

GROBID_REFS = [
    {"title": "Sodium-ion battery cathode materials", "authors": ["John Smith", "Alice Wang"], "year": "2021", "doi": "10.1000/abc"},
    {"title": "Electrochemical impedance of solid electrolytes", "authors": ["Bob Chen"], "year": "2019", "doi": ""},
    {"title": "A review of anode materials for sodium ion", "authors": ["Carol Lee"], "year": "2022", "doi": "10.2000/def"},
]

PARSE_ARTIFACT_WITH_REFS = {
    "parser_metadata": {
        "references": GROBID_REFS,
    }
}

PARSE_ARTIFACT_EMPTY = {"parser_metadata": {}}

RESOLVED_REFS = [
    {
        "title": "Sodium-ion battery cathode materials",
        "authors": ["John Smith", "Alice Wang"],
        "year": 2021,
        "doi": "10.1000/abc",
        "abstract": "We study sodium ion cathode materials for next-generation batteries.",
        "journal": "Journal of Power Sources",
        "resolved": True,
        "raw_ref": GROBID_REFS[0],
    },
    {
        "title": "Electrochemical impedance of solid electrolytes",
        "authors": ["Bob Chen"],
        "year": 2019,
        "doi": "",
        "abstract": "Impedance spectroscopy reveals ionic conductivity in solid electrolytes.",
        "journal": "Electrochimica Acta",
        "resolved": True,
        "raw_ref": GROBID_REFS[1],
    },
    {
        "title": "A review of anode materials for sodium ion",
        "authors": ["Carol Lee"],
        "year": 2022,
        "doi": "10.2000/def",
        "abstract": "",  # unresolved
        "journal": "",
        "resolved": False,
        "raw_ref": GROBID_REFS[2],
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# extract_refs_from_parse_artifact
# ─────────────────────────────────────────────────────────────────────────────

class TestExtractRefs:
    def test_returns_refs_with_title(self):
        refs = extract_refs_from_parse_artifact(PARSE_ARTIFACT_WITH_REFS)
        assert len(refs) == 3
        assert all(r.get("title") for r in refs)

    def test_drops_refs_without_title(self):
        artifact = {
            "parser_metadata": {
                "references": [
                    {"authors": ["Nobody"], "year": "2020"},  # no title
                    {"title": "Valid paper", "authors": ["Someone"]},
                ]
            }
        }
        refs = extract_refs_from_parse_artifact(artifact)
        assert len(refs) == 1
        assert refs[0]["title"] == "Valid paper"

    def test_empty_parse_artifact_returns_empty(self):
        assert extract_refs_from_parse_artifact({}) == []
        assert extract_refs_from_parse_artifact(PARSE_ARTIFACT_EMPTY) == []

    def test_caps_at_max_refs(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.draft_reference_extraction.MAX_REFS", 2
        )
        refs = extract_refs_from_parse_artifact(PARSE_ARTIFACT_WITH_REFS)
        assert len(refs) == 2

    def test_reads_reference_map_key_as_fallback(self):
        artifact = {
            "parser_metadata": {
                "reference_map": [{"title": "Fallback paper"}]
            }
        }
        refs = extract_refs_from_parse_artifact(artifact)
        assert len(refs) == 1

    def test_none_parse_artifact_returns_empty(self):
        assert extract_refs_from_parse_artifact(None) == []


# ─────────────────────────────────────────────────────────────────────────────
# detect_unused_refs
# ─────────────────────────────────────────────────────────────────────────────

class TestDetectUnusedRefs:
    def test_cited_author_year_not_flagged_as_unused(self):
        draft = "As shown by Smith (2021), sodium-ion cathodes have high capacity."
        unused = detect_unused_refs(RESOLVED_REFS, draft)
        titles = [r["title"] for r in unused]
        assert "Sodium-ion battery cathode materials" not in titles

    def test_uncited_ref_flagged_as_unused(self):
        draft = "As shown by Smith (2021), sodium-ion cathodes have high capacity."
        unused = detect_unused_refs(RESOLVED_REFS, draft)
        titles = [r["title"] for r in unused]
        # Chen 2019 not cited in draft
        assert "Electrochemical impedance of solid electrolytes" in titles

    def test_all_uncited_returns_all(self):
        draft = "This paper has no inline citations at all."
        unused = detect_unused_refs(RESOLVED_REFS, draft)
        assert len(unused) == len(RESOLVED_REFS)

    def test_empty_refs_returns_empty(self):
        draft = "Smith (2021) showed important results."
        assert detect_unused_refs([], draft) == []

    def test_empty_draft_flags_all_as_unused(self):
        unused = detect_unused_refs(RESOLVED_REFS, "")
        assert len(unused) == len(RESOLVED_REFS)

    def test_title_keyword_fallback_catches_citation(self):
        # No author-year match, but title keywords present in draft
        refs = [
            {
                "title": "Sodium impedance spectroscopy analysis",
                "authors": [],
                "year": "",
                "abstract": "",
                "resolved": False,
            }
        ]
        draft = "We applied sodium impedance spectroscopy analysis to validate our results."
        unused = detect_unused_refs(refs, draft)
        assert len(unused) == 0  # found via title keywords


# ─────────────────────────────────────────────────────────────────────────────
# suggest_refs_for_weak_claims
# ─────────────────────────────────────────────────────────────────────────────

class TestSuggestRefsForWeakClaims:
    def _cwc(self, claim_text: str, quality: str = "weak", cid: str = "c1") -> dict:
        return {
            "claim": {"id": cid, "claim_text": claim_text},
            "citation_quality": quality,
        }

    def test_weak_claim_matched_to_own_ref(self):
        cwc = [self._cwc("sodium ion cathode materials show high capacity")]
        sugg = suggest_refs_for_weak_claims(cwc, RESOLVED_REFS)
        assert len(sugg) >= 1
        assert sugg[0]["claim_id"] == "c1"
        assert len(sugg[0]["suggested_refs"]) >= 1

    def test_strong_claim_not_included(self):
        cwc = [self._cwc("sodium ion cathode materials", quality="strong")]
        sugg = suggest_refs_for_weak_claims(cwc, RESOLVED_REFS)
        assert len(sugg) == 0

    def test_none_quality_included(self):
        cwc = [self._cwc("sodium ion battery cathode", quality="none")]
        sugg = suggest_refs_for_weak_claims(cwc, RESOLVED_REFS)
        assert len(sugg) >= 1

    def test_no_refs_with_abstract_returns_empty(self):
        refs_no_abstract = [
            {**r, "abstract": "", "resolved": False}
            for r in RESOLVED_REFS
        ]
        cwc = [self._cwc("sodium ion cathode materials")]
        sugg = suggest_refs_for_weak_claims(cwc, refs_no_abstract)
        assert sugg == []

    def test_max_three_refs_per_claim(self):
        refs = [
            {
                "title": f"Sodium ion study {i}",
                "abstract": "sodium ion battery cathode electrochemical study materials",
                "resolved": True,
                "authors": [],
                "year": 2020,
                "doi": "",
                "journal": "",
                "raw_ref": {},
            }
            for i in range(10)
        ]
        cwc = [self._cwc("sodium ion battery cathode electrochemical materials")]
        sugg = suggest_refs_for_weak_claims(cwc, refs)
        if sugg:
            assert len(sugg[0]["suggested_refs"]) <= 3

    def test_claim_text_truncated_to_200_chars(self):
        long_text = "sodium ion " * 30  # 330 chars
        cwc = [self._cwc(long_text)]
        sugg = suggest_refs_for_weak_claims(cwc, RESOLVED_REFS)
        if sugg:
            assert len(sugg[0]["claim_text"]) <= 200


# ─────────────────────────────────────────────────────────────────────────────
# resolve_all_refs (mocked aiohttp)
# ─────────────────────────────────────────────────────────────────────────────

class TestResolveAllRefs:
    @pytest.mark.asyncio
    async def test_resolves_by_doi_when_available(self):
        oa_work = {
            "display_name": "Sodium-ion battery cathode materials",
            "authorships": [{"author": {"display_name": "John Smith"}}],
            "publication_year": 2021,
            "doi": "https://doi.org/10.1000/abc",
            "abstract_inverted_index": {"We": [0], "study": [1], "sodium": [2]},
            "primary_location": {"source": {"display_name": "Journal of Power Sources"}},
        }

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=oa_work)
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            from app.services.draft_reference_extraction import resolve_all_refs
            result = await resolve_all_refs([GROBID_REFS[0]])

        assert len(result) == 1
        assert result[0]["resolved"] is True
        assert result[0]["abstract"] == "We study sodium"

    @pytest.mark.asyncio
    async def test_empty_refs_returns_empty(self):
        from app.services.draft_reference_extraction import resolve_all_refs
        result = await resolve_all_refs([])
        assert result == []

    @pytest.mark.asyncio
    async def test_failed_lookup_returns_unresolved_entry(self):
        mock_resp = AsyncMock()
        mock_resp.status = 404
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            from app.services.draft_reference_extraction import resolve_all_refs
            result = await resolve_all_refs([GROBID_REFS[1]])

        assert len(result) == 1
        assert result[0]["resolved"] is False
        assert result[0]["abstract"] == ""
        assert result[0]["title"] == GROBID_REFS[1]["title"]


# ─────────────────────────────────────────────────────────────────────────────
# extract_references_node (graph node)
# ─────────────────────────────────────────────────────────────────────────────

class TestExtractReferencesNode:
    @pytest.fixture(autouse=True)
    def _mock_openai(self, monkeypatch):
        from app.core import openai_client
        monkeypatch.setattr(openai_client, "get_openai_client", lambda: MagicMock())
        monkeypatch.setattr(openai_client, "get_async_openai_client", lambda: MagicMock())

    @pytest.mark.asyncio
    async def test_node_returns_resolved_and_unused(self):
        state = {
            "draft_id": "d1",
            "project_id": "p1",
            "user_id": "u1",
            "draft_content": "Smith (2021) showed results.",
            "parse_artifact": PARSE_ARTIFACT_WITH_REFS,
            "warnings": [],
        }

        with patch(
            "app.services.draft_reference_extraction.resolve_all_refs",
            new_callable=AsyncMock,
            return_value=RESOLVED_REFS,
        ):
            from app.workflows.draft_analysis.nodes.extract_references import (
                extract_references_node,
            )
            result = await extract_references_node(state)

        assert "resolved_references" in result
        assert "unused_references" in result
        assert len(result["resolved_references"]) == 3
        assert result["progress_percentage"] == 13

    @pytest.mark.asyncio
    async def test_node_non_fatal_on_exception(self):
        state = {
            "draft_id": "d1",
            "project_id": "p1",
            "user_id": "u1",
            "draft_content": "",
            "parse_artifact": {},
            "warnings": [],
        }

        with patch(
            "app.services.draft_reference_extraction.resolve_all_refs",
            new_callable=AsyncMock,
            side_effect=RuntimeError("network down"),
        ):
            from app.workflows.draft_analysis.nodes.extract_references import (
                extract_references_node,
            )
            result = await extract_references_node(state)

        assert result["resolved_references"] == []
        assert result["unused_references"] == []
        assert any("Reference extraction failed" in w for w in result.get("warnings", []))

    @pytest.mark.asyncio
    async def test_node_empty_parse_artifact_returns_empty_lists(self):
        state = {
            "draft_id": "d1",
            "project_id": "p1",
            "user_id": "u1",
            "draft_content": "",
            "parse_artifact": {},
            "warnings": [],
        }

        from app.workflows.draft_analysis.nodes.extract_references import (
            extract_references_node,
        )
        result = await extract_references_node(state)
        assert result["resolved_references"] == []
        assert result["unused_references"] == []

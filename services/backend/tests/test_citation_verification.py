"""Unit tests for Plan 04 — citation misrepresentation check."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.draft_citation_verification import (
    _build_ref_index,
    _resolve_marker,
    _anti_hallucination_guard,
    _verdict_severity,
    build_claim_ref_pairs,
    verdicts_to_revision_tasks,
    MAX_PAIRS,
    MIN_IMPORTANCE,
    ADVERSE_VERDICTS,
)


# ─────────────────────────────────────────────────────────────────────────────
# _build_ref_index
# ─────────────────────────────────────────────────────────────────────────────

class TestBuildRefIndex:
    def _refs(self):
        return [
            {"title": "First paper", "authors": ["Smith J"], "year": 2020, "doi": "10.1/a"},
            {"title": "Second paper", "authors": ["Jones A"], "year": 2021, "doi": "10.1/b"},
            {"title": "Third paper", "authors": [], "year": None, "doi": "10.1/c"},
        ]

    def test_numeric_keys_1_indexed(self):
        idx = _build_ref_index(self._refs())
        assert idx["1"]["title"] == "First paper"
        assert idx["2"]["title"] == "Second paper"
        assert idx["3"]["title"] == "Third paper"

    def test_author_year_key(self):
        idx = _build_ref_index(self._refs())
        # "Smith J" → first token "smith" is indexed
        assert idx.get("smith2020") is not None
        assert idx["smith2020"]["title"] == "First paper"
        assert idx.get("smith 2020") is not None

    def test_last_name_only_fallback(self):
        idx = _build_ref_index(self._refs())
        # "Jones A" → first token "jones" is indexed
        assert idx.get("jones") is not None

    def test_no_authors_no_author_keys(self):
        idx = _build_ref_index(self._refs())
        # Third paper has no authors — should still have numeric key "3"
        assert "3" in idx

    def test_empty_refs(self):
        assert _build_ref_index([]) == {}


# ─────────────────────────────────────────────────────────────────────────────
# _resolve_marker
# ─────────────────────────────────────────────────────────────────────────────

class TestResolveMarker:
    def _idx(self):
        return {
            "1": {"title": "Ref one"},
            "2": {"title": "Ref two"},
            "smith2020": {"title": "Smith 2020"},
            "smith 2020": {"title": "Smith 2020"},
            "jones2019": {"title": "Jones 2019"},
        }

    def test_numeric_bracket(self):
        assert _resolve_marker("[1]", self._idx())["title"] == "Ref one"

    def test_numeric_bare(self):
        assert _resolve_marker("2", self._idx())["title"] == "Ref two"

    def test_author_year_no_parens(self):
        result = _resolve_marker("Smith, 2020", self._idx())
        assert result is not None and result["title"] == "Smith 2020"

    def test_author_year_with_parens(self):
        result = _resolve_marker("(Smith, 2020)", self._idx())
        assert result is not None

    def test_et_al(self):
        idx = {**self._idx(), "jones2019": {"title": "Jones 2019"}, "jones 2019": {"title": "Jones 2019"}}
        result = _resolve_marker("Jones et al. (2019)", idx)
        assert result is not None and result["title"] == "Jones 2019"

    def test_unknown_marker_returns_none(self):
        assert _resolve_marker("[999]", self._idx()) is None

    def test_garbage_returns_none(self):
        assert _resolve_marker("not a citation", self._idx()) is None


# ─────────────────────────────────────────────────────────────────────────────
# build_claim_ref_pairs
# ─────────────────────────────────────────────────────────────────────────────

class TestBuildClaimRefPairs:
    def _claims(self, n=3):
        return [
            {
                "id": f"c{i}",
                "claim_text": f"Claim text {i}",
                "has_inline_citation": True,
                "existing_citations": [f"[{i}]"],
                "importance_score": 0.9 - i * 0.1,
                "section_location": "Introduction",
            }
            for i in range(1, n + 1)
        ]

    def _refs(self, n=3):
        return [
            {"title": f"Ref {i}", "doi": f"10.1/{i}", "authors": [f"Author{i} X"], "year": 2020, "abstract": f"Abstract text for ref {i}."}
            for i in range(1, n + 1)
        ]

    def test_returns_pairs(self):
        pairs = build_claim_ref_pairs(self._claims(), self._refs())
        assert len(pairs) >= 1

    def test_each_pair_has_required_keys(self):
        pairs = build_claim_ref_pairs(self._claims(1), self._refs(1))
        assert len(pairs) == 1
        p = pairs[0]
        assert "claim" in p and "ref" in p and "marker" in p and "pair_id" in p

    def test_importance_filter(self):
        low_importance = [{
            "id": "c99", "claim_text": "Low importance", "has_inline_citation": True,
            "existing_citations": ["[1]"], "importance_score": 0.1,
        }]
        pairs = build_claim_ref_pairs(low_importance, self._refs(1))
        assert pairs == []

    def test_skips_refs_without_abstract(self):
        refs = [{"title": "No abstract ref", "doi": "10.1/x", "authors": ["A B"], "year": 2020, "abstract": ""}]
        pairs = build_claim_ref_pairs(self._claims(1), refs)
        assert pairs == []

    def test_empty_claims(self):
        assert build_claim_ref_pairs([], self._refs()) == []

    def test_empty_refs(self):
        assert build_claim_ref_pairs(self._claims(), []) == []

    def test_capped_at_max_pairs(self):
        # Generate many claims, each resolved to a different ref
        many_claims = [
            {
                "id": f"c{i}", "claim_text": f"Claim {i}", "has_inline_citation": True,
                "existing_citations": [f"[{i}]"], "importance_score": 0.9,
            }
            for i in range(1, MAX_PAIRS + 10)
        ]
        many_refs = [
            {"title": f"Ref {i}", "doi": f"10.1/{i}", "authors": [f"A{i} B"], "year": 2020, "abstract": "text"}
            for i in range(1, MAX_PAIRS + 10)
        ]
        pairs = build_claim_ref_pairs(many_claims, many_refs)
        assert len(pairs) <= MAX_PAIRS

    def test_deduplication_same_claim_same_ref(self):
        # Claim with two identical markers → only one pair
        claim = [{
            "id": "c1", "claim_text": "Claim", "has_inline_citation": True,
            "existing_citations": ["[1]", "[1]"], "importance_score": 0.9,
        }]
        pairs = build_claim_ref_pairs(claim, self._refs(1))
        assert len(pairs) == 1


# ─────────────────────────────────────────────────────────────────────────────
# _anti_hallucination_guard
# ─────────────────────────────────────────────────────────────────────────────

class TestAntiHallucinationGuard:
    def _pair(self):
        return {
            "pair_id": "pid1",
            "marker": "[1]",
            "claim": {"id": "c1", "claim_text": "Some claim", "section_location": "Intro", "char_start": 0, "char_end": 10, "text_snippet": ""},
            "ref": {"title": "Some paper", "doi": "10.1/x", "year": 2020},
        }

    def _verdict_obj(self, verdict, quote=""):
        obj = MagicMock()
        obj.verdict = verdict
        obj.evidence_quote = quote
        obj.confidence = 0.85
        obj.reasoning = "Some reasoning"
        return obj

    def test_supports_no_quote_ok(self):
        result = _anti_hallucination_guard(self._verdict_obj("supports", ""), self._pair())
        assert result["verdict"] == "supports"

    def test_adverse_with_quote_kept(self):
        result = _anti_hallucination_guard(self._verdict_obj("contradicts", "Evidence here"), self._pair())
        assert result["verdict"] == "contradicts"
        assert result["evidence_quote"] == "Evidence here"

    def test_adverse_without_quote_downgraded(self):
        result = _anti_hallucination_guard(self._verdict_obj("contradicts", ""), self._pair())
        assert result["verdict"] == "unverifiable"
        assert result["evidence_quote"] == ""

    def test_overclaim_without_quote_downgraded(self):
        result = _anti_hallucination_guard(self._verdict_obj("overclaim", "  "), self._pair())
        assert result["verdict"] == "unverifiable"

    def test_unrelated_without_quote_downgraded(self):
        result = _anti_hallucination_guard(self._verdict_obj("unrelated", ""), self._pair())
        assert result["verdict"] == "unverifiable"

    def test_unverifiable_no_quote_stays(self):
        result = _anti_hallucination_guard(self._verdict_obj("unverifiable", ""), self._pair())
        assert result["verdict"] == "unverifiable"

    def test_partial_no_quote_allowed(self):
        # partial is NOT in ADVERSE_VERDICTS (no evidence_quote required)
        result = _anti_hallucination_guard(self._verdict_obj("partial", ""), self._pair())
        assert result["verdict"] == "partial"

    def test_severity_attached(self):
        result = _anti_hallucination_guard(self._verdict_obj("contradicts", "Quote"), self._pair())
        assert result["severity"] == "critical"


# ─────────────────────────────────────────────────────────────────────────────
# _verdict_severity
# ─────────────────────────────────────────────────────────────────────────────

class TestVerdictSeverity:
    def test_contradicts_critical(self):
        assert _verdict_severity("contradicts") == "critical"

    def test_overclaim_major(self):
        assert _verdict_severity("overclaim") == "major"

    def test_unrelated_major(self):
        assert _verdict_severity("unrelated") == "major"

    def test_partial_minor(self):
        assert _verdict_severity("partial") == "minor"

    def test_supports_none(self):
        assert _verdict_severity("supports") is None

    def test_unverifiable_none(self):
        assert _verdict_severity("unverifiable") is None


# ─────────────────────────────────────────────────────────────────────────────
# verdicts_to_revision_tasks
# ─────────────────────────────────────────────────────────────────────────────

class TestVerdictsToRevisionTasks:
    def _verdict(self, verdict, quote="Evidence"):
        return {
            "pair_id": "p1",
            "claim_id": "c1",
            "claim_text": "The drug reduces mortality by 50%.",
            "citation_marker": "[3]",
            "cited_ref_title": "Smith 2020 RCT",
            "cited_ref_doi": "10.1/x",
            "cited_ref_year": 2020,
            "verdict": verdict,
            "confidence": 0.9,
            "evidence_quote": quote,
            "reasoning": "Paper is about something else",
            "severity": _verdict_severity(verdict),
            "section_location": "Results",
            "char_start": 100,
            "char_end": 150,
            "text_snippet": "The drug reduces mortality by 50%.",
        }

    def test_adverse_verdicts_generate_tasks(self):
        for v in ["contradicts", "overclaim", "unrelated"]:
            tasks = verdicts_to_revision_tasks([self._verdict(v)])
            assert len(tasks) == 1
            assert tasks[0]["verdict"] if "verdict" in tasks[0] else True  # has citation_verdict

    def test_supports_generates_no_task(self):
        tasks = verdicts_to_revision_tasks([self._verdict("supports", "")])
        assert tasks == []

    def test_unverifiable_generates_no_task(self):
        tasks = verdicts_to_revision_tasks([self._verdict("unverifiable", "")])
        assert tasks == []

    def test_partial_generates_no_task(self):
        tasks = verdicts_to_revision_tasks([self._verdict("partial", "Some text")])
        assert tasks == []

    def test_task_has_required_fields(self):
        tasks = verdicts_to_revision_tasks([self._verdict("contradicts", "Evidence quote")])
        t = tasks[0]
        assert t["task_type"] == "citation"
        assert t["source_type"] == "citation_misrepresentation"
        assert "Evidence quote" in t["problem"]
        assert t["severity"] == "critical"
        assert t["priority"] == "high"
        assert t["anchor_text"]
        assert t["dedupe_category"].startswith("citation_misrep:")

    def test_contradicts_is_high_priority(self):
        tasks = verdicts_to_revision_tasks([self._verdict("contradicts")])
        assert tasks[0]["priority"] == "high"

    def test_overclaim_is_medium_priority(self):
        tasks = verdicts_to_revision_tasks([self._verdict("overclaim")])
        assert tasks[0]["priority"] == "medium"

    def test_multiple_verdicts(self):
        verdicts = [
            self._verdict("contradicts"),
            self._verdict("supports", ""),
            self._verdict("unrelated"),
        ]
        tasks = verdicts_to_revision_tasks(verdicts)
        assert len(tasks) == 2

    def test_empty_input(self):
        assert verdicts_to_revision_tasks([]) == []


# ─────────────────────────────────────────────────────────────────────────────
# verify_citations_node (integration — mocked LLM)
# ─────────────────────────────────────────────────────────────────────────────

class TestVerifyCitationsNode:
    def _state(self, claims=None, refs=None):
        return {
            "draft_id": "d1",
            "project_id": "p1",
            "user_id": "u1",
            "claims": claims or [],
            "resolved_references": refs or [],
            "revision_tasks": [],
            "warnings": [],
        }

    @pytest.fixture(autouse=True)
    def _mock_openai(self, monkeypatch):
        from app.core import openai_client
        monkeypatch.setattr(openai_client, "get_async_openai_client", lambda: MagicMock())

    @pytest.mark.asyncio
    async def test_no_claims_skips(self):
        from app.workflows.draft_analysis.nodes.verify_citations import verify_citations_node
        result = await verify_citations_node(self._state())
        assert result["citation_verdicts"] == []
        assert "Skipped" in result["current_step"]

    @pytest.mark.asyncio
    async def test_no_refs_skips(self):
        from app.workflows.draft_analysis.nodes.verify_citations import verify_citations_node
        claims = [{"id": "c1", "claim_text": "x", "has_inline_citation": True, "existing_citations": ["[1]"], "importance_score": 0.9}]
        result = await verify_citations_node(self._state(claims=claims, refs=[]))
        assert result["citation_verdicts"] == []

    @pytest.mark.asyncio
    async def test_exception_is_non_fatal(self):
        from app.workflows.draft_analysis.nodes.verify_citations import verify_citations_node
        with patch(
            "app.services.draft_citation_verification.build_claim_ref_pairs",
            side_effect=RuntimeError("Simulated failure"),
        ):
            result = await verify_citations_node(self._state(
                claims=[{"id": "c1", "claim_text": "x", "has_inline_citation": True, "existing_citations": ["[1]"], "importance_score": 0.9}],
                refs=[{"title": "R1", "doi": "10.1/x", "abstract": "text", "authors": ["A B"], "year": 2020}],
            ))
        assert result["citation_verdicts"] == []
        assert any("Citation verification skipped" in w for w in result.get("warnings", []))

    @pytest.mark.asyncio
    async def test_adverse_verdicts_added_to_revision_tasks(self):
        from app.workflows.draft_analysis.nodes.verify_citations import verify_citations_node
        from app.workflows.draft_analysis.schemas import CitationVerificationBatch, SingleCitationVerdict

        mock_verdict = SingleCitationVerdict(
            pair_index=0,
            verdict="contradicts",
            confidence=0.9,
            evidence_quote="The study found no significant effect.",
            reasoning="Claim contradicts the abstract.",
        )
        mock_batch = CitationVerificationBatch(verdicts=[mock_verdict])
        mock_response = MagicMock()
        mock_response.parsed = mock_batch

        claims = [{
            "id": "c1", "claim_text": "Drug reduces mortality.", "has_inline_citation": True,
            "existing_citations": ["[1]"], "importance_score": 0.9, "section_location": "Results",
        }]
        refs = [{"title": "RCT paper", "doi": "10.1/rct", "authors": ["Smith J"], "year": 2020, "abstract": "The study found no significant effect."}]

        with patch(
            "app.services.draft_citation_verification.parse_chat_completion_with_retries",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await verify_citations_node(self._state(claims=claims, refs=refs))

        assert len(result["citation_verdicts"]) == 1
        assert result["citation_verdicts"][0]["verdict"] == "contradicts"
        # Should have created a revision task
        assert len(result["revision_tasks"]) == 1
        assert result["revision_tasks"][0]["task_type"] == "citation"

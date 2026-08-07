"""
Tests for Phase 3 (peer review panel) and Phase 4 (LLM-as-a-judge) nodes.

Covers:
  - editor_pass_node: desk check output, failure fallback
  - reviewer_panel_node: structured output, idempotency guard, failure fallback
  - meta_reviewer_node: synthesis, legacy feedback rows, idempotency guard
  - citation_judge_node: filters keep=False suggestions + external sources
  - reviewer_judge_node: quality scoring, retry on low-specificity reviewer
  - graph topology: new nodes present, edge wiring correct
  - schemas: all Phase 3+4 Pydantic models importable and valid
  - API: citation_judge + reviewer_judge fields present in analyzed response
"""

import pytest
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch, call


# ── Schema smoke tests ────────────────────────────────────────────────────────

class TestPhase34Schemas:

    def test_phase3_schemas_import(self):
        from app.workflows.draft_analysis.schemas import (
            EditorPassOutput,
            ReviewerOutput,
            MetaReviewOutput,
        )
        assert EditorPassOutput is not None
        assert ReviewerOutput is not None
        assert MetaReviewOutput is not None

    def test_phase4_schemas_import(self):
        from app.workflows.draft_analysis.schemas import (
            SuggestedCitationVerdict,
            ExternalSourceVerdict,
            CitationJudgeOutput,
            ReviewerJudgeScore,
            ReviewerJudgeOutput,
        )
        assert CitationJudgeOutput is not None
        assert ReviewerJudgeOutput is not None

    def test_editor_pass_output_defaults(self):
        from app.workflows.draft_analysis.schemas import EditorPassOutput
        out = EditorPassOutput()
        assert out.proceed_to_review is True
        assert out.fatal_flaws == []
        assert out.scope_appropriate is True

    def test_reviewer_output_rating_bounds(self):
        from app.workflows.draft_analysis.schemas import ReviewerOutput
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            ReviewerOutput(
                reviewer_id="literature_positioning",
                summary="test",
                rating=11,  # out of range
                confidence=3,
                recommendation="accept",
            )

    def test_absence_verifier_drops_issue_contradicted_later_in_manuscript(self):
        from app.workflows.draft_analysis.nodes.reviewer_panel import _filter_contradicted_absence_issues
        from app.workflows.draft_analysis.schemas import ReviewerIssue

        draft = (
            "Introduction. " + ("filler " * 5000) +
            "Appendix B. Hyperparameters. We use Adam with learning rate 1e-4, "
            "batch size 32, weight decay 0.01, and train for 20 epochs."
        )
        issue = ReviewerIssue(
            issue_type="reproducibility",
            section_reference="Methods",
            anchor_text="",
            problem="The manuscript lacks concrete hyperparameters for training.",
            why_it_matters="Reviewers cannot reproduce the experiments.",
            suggested_action="Specify learning rate, batch size, optimizer, and epochs.",
            confidence=0.8,
        )

        assert _filter_contradicted_absence_issues([issue], draft) == []

    def test_absence_verifier_drops_consolidated_definition_false_absence(self):
        from app.workflows.draft_analysis.nodes.reviewer_panel import _filter_contradicted_absence_issues
        from app.workflows.draft_analysis.schemas import ReviewerIssue

        draft = (
            "Methods. Step-1 introduces the model. Step-4. The formal complete "
            "description of how the final model implements the retrieval module is as follows: "
            "z = R(E(x), K, V), y = P(z)."
        )
        issue = ReviewerIssue(
            issue_type="clarity",
            section_reference="Architecture",
            anchor_text="",
            problem="There is no single consolidated definition or full forward-pass equation of the final model.",
            why_it_matters="The architecture is scattered across incremental steps.",
            suggested_action="Add a consolidated algorithm box or complete model definition.",
            confidence=0.8,
        )

        assert _filter_contradicted_absence_issues([issue], draft) == []

    def test_absence_verifier_drops_related_work_false_absence(self):
        from app.workflows.draft_analysis.nodes.reviewer_panel import _filter_contradicted_absence_issues
        from app.workflows.draft_analysis.schemas import ReviewerIssue

        draft = (
            "Related Work. Classic neighbor-based and kernel methods are retrieval-based "
            "tabular models. kNN is the simplest example of local learning. We also discuss "
            "deep kernel learning and DNNR as close conceptual neighbors."
        )
        issue = ReviewerIssue(
            issue_type="positioning",
            section_reference="Related Work",
            anchor_text="",
            problem="The related work gives limited discussion of classical kernel regression and learned metric kNN as conceptual neighbors.",
            why_it_matters="The novelty may be overstated without these comparisons.",
            suggested_action="Discuss kernel regression, kNN, and related neighbor-based methods.",
            confidence=0.8,
        )

        assert _filter_contradicted_absence_issues([issue], draft) == []

    def test_absence_verifier_drops_seed_uncertainty_false_absence(self):
        from app.workflows.draft_analysis.nodes.reviewer_panel import _filter_contradicted_absence_issues
        from app.workflows.draft_analysis.schemas import ReviewerIssue

        draft = (
            "Results. All main-text metrics are averaged over 15 seeds. "
            "Appendix E reports standard deviations for each benchmark and ablation."
        )
        issue = ReviewerIssue(
            issue_type="methodology",
            section_reference="Ablations",
            anchor_text="",
            problem="The ablation is discussed without reporting uncertainty across seeds.",
            why_it_matters="The importance of the component may be overstated without variability estimates.",
            suggested_action="Report mean and standard deviation across random seeds.",
            confidence=0.8,
        )

        assert _filter_contradicted_absence_issues([issue], draft) == []

    def test_citation_judge_output_defaults(self):
        from app.workflows.draft_analysis.schemas import CitationJudgeOutput
        out = CitationJudgeOutput()
        assert out.citation_verdicts == []
        assert out.external_source_verdicts == []
        assert out.overall_citation_quality == "medium"

    def test_reviewer_judge_output_retry_ids_default_empty(self):
        from app.workflows.draft_analysis.schemas import ReviewerJudgeOutput, ReviewerJudgeScore
        score = ReviewerJudgeScore(reviewer_id="literature_positioning", specificity_score=0.8, quality_pass=True)
        out = ReviewerJudgeOutput(reviewer_scores=[score])
        assert out.retry_reviewer_ids == []
        assert out.panel_quality == "medium"

    def test_eval_can_disable_pre_reviewer_halt(self, monkeypatch):
        from app.workflows.draft_analysis.graph import route_to_reviewer_panel

        state = {
            "editor_decision": {"proceed_to_review": True},
            "claims_with_citations": [{"claim": {"claim_text": "x"}}],
            "parser_quality": {"parser_quality_score": 0.4},
        }

        assert route_to_reviewer_panel(state) == "synthesize_report"

        monkeypatch.setenv("EVAL_DISABLE_PRE_REVIEWER_HALT", "1")
        routed = route_to_reviewer_panel(state)

        assert isinstance(routed, list)
        assert len(routed) == 3

    def test_methodology_context_includes_empirical_diagnostics(self):
        from app.workflows.draft_analysis.nodes.reviewer_panel import _build_methodology_context

        context = _build_methodology_context({
            "claims_with_citations": [],
            "structural_feedback": [],
            "diagnostic_findings": [{
                "finding_type": "methodology",
                "severity": "major",
                "section_reference": "Evaluation",
                "problem": "The evaluation depends on prompt sensitivity over generated datasets.",
            }],
        })

        assert "PROFILE-AWARE DIAGNOSTICS" in context
        assert "prompt sensitivity" in context

    def test_state_has_judge_fields(self):
        from app.workflows.draft_analysis.state import DraftAnalysisState
        # Both judge fields are NotRequired — valid state without them
        state: DraftAnalysisState = {
            "draft_id": "d1",
            "project_id": "p1",
            "user_id": "u1",
            "draft_content": "text",
            "current_step": "start",
            "progress_percentage": 0,
        }
        assert state.get("citation_judge_output") is None
        assert state.get("reviewer_judge_output") is None


# ── Editor Pass Node ──────────────────────────────────────────────────────────

class TestEditorPassNode:

    @pytest.mark.unit
    @patch("app.workflows.draft_analysis.nodes.editor_pass.client")
    def test_editor_pass_returns_decision(self, mock_client):
        from app.workflows.draft_analysis.nodes.editor_pass import editor_pass_node
        from app.workflows.draft_analysis.schemas import EditorPassOutput

        fake_decision = EditorPassOutput(
            proceed_to_review=True,
            fatal_flaws=[],
            scope_appropriate=True,
            writing_quality="needs_revision",
            notes="Looks reviewable.",
        )
        mock_client.beta.chat.completions.parse = AsyncMock(
            return_value=SimpleNamespace(parsed=fake_decision)
        )

        state = {
            "draft_id": "d1", "project_id": "p1", "user_id": "u1",
            "draft_content": "Introduction. Methods. Results. Discussion.",
            "current_step": "editor_pass", "progress_percentage": 79,
            "structure": {"sections": [{"type": "introduction"}, {"type": "methods"}], "word_count": 4000},
        }
        result = asyncio.run(editor_pass_node(state))

        assert result["editor_decision"]["proceed_to_review"] is True
        assert result["editor_decision"]["writing_quality"] == "needs_revision"
        assert result["progress_percentage"] == 80
        _, kwargs = mock_client.beta.chat.completions.parse.call_args
        assert kwargs["max_completion_tokens"] == 2500

    @pytest.mark.unit
    @patch("app.workflows.draft_analysis.nodes.editor_pass.client")
    def test_editor_pass_failure_defaults_to_proceed(self, mock_client):
        from app.workflows.draft_analysis.nodes.editor_pass import editor_pass_node

        mock_client.beta.chat.completions.parse = AsyncMock(side_effect=Exception("API down"))

        state = {
            "draft_id": "d1", "project_id": "p1", "user_id": "u1",
            "draft_content": "text", "current_step": "editor_pass", "progress_percentage": 79,
        }
        result = asyncio.run(editor_pass_node(state))

        # Must default to proceed=True so analysis never gets blocked by editor crash
        assert result["editor_decision"]["proceed_to_review"] is True
        assert "unavailable" in result["editor_decision"]["notes"].lower() or \
               "api down" in result["editor_decision"]["notes"].lower()

    @pytest.mark.unit
    @patch("app.workflows.draft_analysis.nodes.editor_pass.client")
    def test_editor_pass_desk_reject_sets_flag(self, mock_client):
        from app.workflows.draft_analysis.nodes.editor_pass import editor_pass_node
        from app.workflows.draft_analysis.schemas import EditorPassOutput

        fake_decision = EditorPassOutput(
            proceed_to_review=False,
            fatal_flaws=["No methods section present"],
            scope_appropriate=True,
            writing_quality="major_revision",
            notes="Missing core sections.",
        )
        mock_client.beta.chat.completions.parse = AsyncMock(
            return_value=SimpleNamespace(parsed=fake_decision)
        )

        state = {
            "draft_id": "d1", "project_id": "p1", "user_id": "u1",
            "draft_content": "Just an abstract.", "current_step": "editor_pass", "progress_percentage": 79,
        }
        result = asyncio.run(editor_pass_node(state))

        assert result["editor_decision"]["proceed_to_review"] is False
        assert len(result["editor_decision"]["fatal_flaws"]) == 1


# ── Reviewer Panel Node ───────────────────────────────────────────────────────

class TestReviewerPanelNode:

    def _make_reviewer_output(self, reviewer_id="literature_positioning"):
        from app.workflows.draft_analysis.schemas import ReviewerOutput
        return ReviewerOutput(
            reviewer_id=reviewer_id,
            summary="This paper presents a novel approach.",
            strengths=["Clear contribution"],
            weaknesses=["Section 3 lacks baselines"],
            questions_to_authors=["Can you compare to method X?"],
            limitations_to_address=["Generalizability not discussed"],
            rating=6,
            confidence=3,
            recommendation="minor_revision",
        )

    @pytest.mark.unit
    @patch("app.workflows.draft_analysis.nodes.reviewer_panel.supabase")
    @patch("app.workflows.draft_analysis.nodes.reviewer_panel.client")
    def test_reviewer_panel_returns_output(self, mock_client, mock_supabase):
        from app.workflows.draft_analysis.nodes.reviewer_panel import reviewer_panel_node

        # No existing row in DB
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value \
            = MagicMock(data=[])
        mock_supabase.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[{}])

        fake_output = self._make_reviewer_output("literature_positioning")
        mock_client.beta.chat.completions.parse = AsyncMock(
            return_value=SimpleNamespace(parsed=fake_output)
        )

        state = {
            "draft_id": "d1", "project_id": "p1", "user_id": "u1",
            "draft_content": "Paper text here.",
            "reviewer_type": "literature_positioning",
            "current_step": "reviewer_panel", "progress_percentage": 82,
        }
        result = asyncio.run(reviewer_panel_node(state))

        assert len(result["reviewer_outputs"]) == 1
        ro = result["reviewer_outputs"][0]
        assert ro["reviewer_id"] == "literature_positioning"
        assert ro["rating"] == 6
        assert ro["recommendation"] == "minor_revision"

    @pytest.mark.unit
    @patch("app.workflows.draft_analysis.nodes.reviewer_panel.supabase")
    @patch("app.workflows.draft_analysis.nodes.reviewer_panel.client")
    def test_reviewer_panel_regenerates_existing_output(self, mock_client, mock_supabase):
        from app.workflows.draft_analysis.nodes.reviewer_panel import reviewer_panel_node

        fake_output = self._make_reviewer_output("methodology")
        fake_output.rating = 5
        fake_output.recommendation = "major_revision"
        mock_client.beta.chat.completions.parse = AsyncMock(
            return_value=SimpleNamespace(parsed=fake_output)
        )
        table_mock = mock_supabase.table.return_value
        table_mock.delete.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        table_mock.insert.return_value.execute.return_value = MagicMock(data=[{}])

        state = {
            "draft_id": "d1", "project_id": "p1", "user_id": "u1",
            "draft_content": "Paper text.",
            "reviewer_type": "methodology",
            "current_step": "reviewer_panel", "progress_percentage": 82,
        }
        result = asyncio.run(reviewer_panel_node(state))

        mock_client.beta.chat.completions.parse.assert_called_once()
        assert len(result["reviewer_outputs"]) == 1
        assert result["reviewer_outputs"][0]["summary"] == fake_output.summary
        assert result["reviewer_outputs"][0]["rating"] == 5

    @pytest.mark.unit
    @patch("app.workflows.draft_analysis.nodes.reviewer_panel.supabase")
    @patch("app.workflows.draft_analysis.nodes.reviewer_panel.client")
    def test_reviewer_panel_failure_returns_empty_list(self, mock_client, mock_supabase):
        from app.workflows.draft_analysis.nodes.reviewer_panel import reviewer_panel_node

        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value \
            = MagicMock(data=[])
        mock_client.beta.chat.completions.parse = AsyncMock(side_effect=Exception("GPT error"))

        state = {
            "draft_id": "d1", "project_id": "p1", "user_id": "u1",
            "draft_content": "text", "reviewer_type": "literature_positioning",
            "current_step": "reviewer_panel", "progress_percentage": 82,
        }
        result = asyncio.run(reviewer_panel_node(state))

        # Empty list — meta_reviewer handles missing reviewers gracefully
        assert result["reviewer_outputs"] == []

    @pytest.mark.unit
    def test_three_reviewer_types_have_prompts(self):
        from app.workflows.draft_analysis.nodes.reviewer_panel import REVIEWER_PROMPTS
        for rt in ("methodology", "literature_positioning", "clarity"):
            assert rt in REVIEWER_PROMPTS
            assert len(REVIEWER_PROMPTS[rt]) > 100

    @pytest.mark.unit
    def test_build_reviewer_context_includes_draft_metadata(self):
        from app.workflows.draft_analysis.nodes.reviewer_panel import build_reviewer_context
        state = {
            "draft_id": "d1", "project_id": "p1", "user_id": "u1",
            "draft_content": "Abstract. Introduction. Methods. Results.",
            "paper_type": "empirical",
            "structure": {"sections": [{"type": "introduction"}], "word_count": 3500},
        }
        ctx = build_reviewer_context(state, "literature_positioning")
        assert "empirical" in ctx
        assert "3500" in ctx

    @pytest.mark.unit
    def test_methodology_reviewer_includes_transferable_model_audit(self):
        from app.workflows.draft_analysis.nodes.reviewer_panel import REVIEWER_PROMPTS, build_reviewer_context
        state = {
            "draft_id": "d1", "project_id": "p1", "user_id": "u1",
            "draft_content": "Methods. We train a model on simulated data.",
            "paper_type": "empirical",
            "structure": {"sections": [{"type": "methods"}], "word_count": 1200},
            "manuscript_profile": {},
        }

        assert "chosen modeling formalism" in REVIEWER_PROMPTS["methodology"]
        ctx = build_reviewer_context(state, "methodology")
        assert "TRANSFERABLE MODEL/METHOD AUDIT" in ctx
        assert "target variables" in ctx


# ── Meta-Reviewer Node ────────────────────────────────────────────────────────

class TestMetaReviewerNode:

    def _reviewer_outputs(self):
        return [
            {"reviewer_id": "literature_positioning", "rating": 6, "confidence": 3,
             "recommendation": "minor_revision", "summary": "Novel enough.",
             "strengths": ["Clear contribution"], "weaknesses": ["Section 3 weak"],
             "questions_to_authors": ["Clarify RQ1?"], "limitations_to_address": []},
            {"reviewer_id": "methodology", "rating": 5, "confidence": 4,
             "recommendation": "major_revision", "summary": "Baselines missing.",
             "strengths": [], "weaknesses": ["No SOTA comparison"],
             "questions_to_authors": [], "limitations_to_address": ["Add ablation"]},
        ]

    @pytest.mark.unit
    @patch("app.workflows.draft_analysis.nodes.meta_reviewer.supabase")
    @patch("app.workflows.draft_analysis.nodes.meta_reviewer.client")
    def test_meta_reviewer_synthesizes_output(self, mock_client, mock_supabase):
        from app.workflows.draft_analysis.nodes.meta_reviewer import meta_reviewer_node
        from app.workflows.draft_analysis.schemas import MetaReviewOutput

        # No existing meta review
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value \
            = MagicMock(data=[])
        mock_supabase.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[{}])
        mock_supabase.table.return_value.delete.return_value.eq.return_value.execute.return_value \
            = MagicMock(data=[])

        fake_meta = MetaReviewOutput(
            overall_recommendation="major_revision",
            decision_rationale="Methodology needs work before acceptance.",
            must_address=["Add SOTA baselines", "Ablation study"],
            nice_to_address=["Improve figure captions"],
            consensus_strengths=["Novel framing"],
            consensus_weaknesses=["Weak baselines"],
            reviewer_agreement_level="medium",
        )
        mock_client.beta.chat.completions.parse = AsyncMock(
            return_value=SimpleNamespace(parsed=fake_meta)
        )

        state = {
            "draft_id": "d1", "project_id": "p1", "user_id": "u1",
            "draft_content": "text", "current_step": "meta_reviewer",
            "progress_percentage": 90, "reviewer_outputs": self._reviewer_outputs(),
        }
        result = asyncio.run(meta_reviewer_node(state))

        assert result["meta_review"]["overall_recommendation"] == "major_revision"
        assert "Add SOTA baselines" in result["meta_review"]["must_address"]
        assert result["progress_percentage"] == 93

    @pytest.mark.unit
    @patch("app.workflows.draft_analysis.nodes.meta_reviewer.supabase")
    @patch("app.workflows.draft_analysis.nodes.meta_reviewer.client")
    def test_meta_reviewer_skips_when_no_reviewer_outputs(self, mock_client, mock_supabase):
        from app.workflows.draft_analysis.nodes.meta_reviewer import meta_reviewer_node

        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value \
            = MagicMock(data=[])

        state = {
            "draft_id": "d1", "project_id": "p1", "user_id": "u1",
            "draft_content": "text", "current_step": "meta_reviewer",
            "progress_percentage": 90, "reviewer_outputs": [],
        }
        result = asyncio.run(meta_reviewer_node(state))

        mock_client.beta.chat.completions.parse.assert_not_called()
        assert result["meta_review"] is None

    @pytest.mark.unit
    @patch("app.workflows.draft_analysis.nodes.meta_reviewer.supabase")
    @patch("app.workflows.draft_analysis.nodes.meta_reviewer.client")
    def test_meta_reviewer_regenerates_existing_output(self, mock_client, mock_supabase):
        from app.workflows.draft_analysis.nodes.meta_reviewer import meta_reviewer_node
        from app.workflows.draft_analysis.schemas import MetaReviewOutput

        fake_meta = MetaReviewOutput(
            overall_recommendation="major_revision",
            decision_rationale="Regenerated from current reviewer panel.",
            must_address=["Fix current issue"],
            nice_to_address=[],
            consensus_strengths=[],
            consensus_weaknesses=["Current weakness"],
            reviewer_agreement_level="medium",
        )
        mock_client.beta.chat.completions.parse = AsyncMock(
            return_value=SimpleNamespace(parsed=fake_meta)
        )
        table_mock = mock_supabase.table.return_value
        table_mock.delete.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        table_mock.insert.return_value.execute.return_value = MagicMock(data=[{}])

        state = {
            "draft_id": "d1", "project_id": "p1", "user_id": "u1",
            "draft_content": "text", "current_step": "meta_reviewer",
            "progress_percentage": 90, "reviewer_outputs": self._reviewer_outputs(),
        }
        result = asyncio.run(meta_reviewer_node(state))

        mock_client.beta.chat.completions.parse.assert_called_once()
        assert result["meta_review"]["overall_recommendation"] == "major_revision"

    def test_synthesize_legacy_feedback_generates_rows(self):
        from app.workflows.draft_analysis.nodes.meta_reviewer import _synthesize_legacy_feedback
        from app.workflows.draft_analysis.schemas import MetaReviewOutput

        meta = MetaReviewOutput(
            overall_recommendation="major_revision",
            decision_rationale="Needs work.",
            must_address=["Fix baseline", "Add ablation"],
            nice_to_address=["Better figures"],
            consensus_strengths=["Novel idea"],
            consensus_weaknesses=["Weak methods"],
            reviewer_agreement_level="low",
        )
        rows = _synthesize_legacy_feedback(meta, self._reviewer_outputs())

        types = {r["feedback_type"] for r in rows}
        assert "weakness" in types
        assert "strength" in types
        personas = {r["reviewer_persona"] for r in rows}
        assert personas <= {"reviewer_1", "reviewer_2"}
        assert any(r.get("reviewer_id") == "area_chair" for r in rows)
        # Must-address items map to critical weakness
        critical = [r for r in rows if r["severity"] == "critical"]
        assert len(critical) == 2


# ── Citation Judge Node ───────────────────────────────────────────────────────

class TestCitationJudgeNode:

    @pytest.mark.unit
    @patch("app.workflows.draft_analysis.nodes.citation_judge.client")
    def test_citation_judge_filters_low_relevance_suggestions(self, mock_client):
        from app.workflows.draft_analysis.nodes.citation_judge import citation_judge_node
        from app.workflows.draft_analysis.schemas import (
            CitationJudgeOutput, SuggestedCitationVerdict, ExternalSourceVerdict,
        )

        # Snippets must match exactly claim_text[:80] as used in _apply_verdicts lookup
        claim_text_a = "We show that transformer models outperform RNNs"
        claim_text_b = "Our method reduces latency by 40%"

        fake_output = CitationJudgeOutput(
            citation_verdicts=[
                SuggestedCitationVerdict(
                    claim_text_snippet=claim_text_a[:80],
                    citation_title="Deep Learning Survey",
                    relevance_score=0.3,
                    keep=False,
                    reason="Generic survey, not specific to this claim.",
                ),
                SuggestedCitationVerdict(
                    claim_text_snippet=claim_text_b[:80],
                    citation_title="FastTransformer 2023",
                    relevance_score=0.9,
                    keep=True,
                    reason="Directly compares latency on same benchmark.",
                ),
            ],
            external_source_verdicts=[
                ExternalSourceVerdict(
                    source_title="Unrelated Biology Paper",
                    supports_which="missing baseline comparison",
                    relevance_score=0.1,
                    keep=False,
                    reason="Wrong domain entirely.",
                ),
            ],
            overall_citation_quality="medium",
        )
        mock_client.beta.chat.completions.parse = AsyncMock(
            return_value=SimpleNamespace(parsed=fake_output)
        )

        state = {
            "draft_id": "d1", "project_id": "p1", "user_id": "u1",
            "draft_content": "text", "current_step": "citation_judge", "progress_percentage": 76,
            "claims_with_citations": [
                {
                    "claim": {"claim_text": claim_text_a, "claim_type": "empirical"},
                    "citations": [],
                    "citation_quality": "weak",
                    "suggested_citations": [{"title": "Deep Learning Survey", "source": "semantic_scholar"}],
                },
                {
                    "claim": {"claim_text": claim_text_b, "claim_type": "empirical"},
                    "citations": [],
                    "citation_quality": "none",
                    "suggested_citations": [{"title": "FastTransformer 2023", "source": "semantic_scholar"}],
                },
            ],
            "external_sources": [
                {"title": "Unrelated Biology Paper", "gap_description": "missing baseline comparison"},
            ],
        }

        result = asyncio.run(citation_judge_node(state))

        # First claim's suggestion filtered out
        cwc0 = result["claims_with_citations"][0]
        assert cwc0["suggested_citations"] == []

        # Second claim's suggestion kept
        cwc1 = result["claims_with_citations"][1]
        assert len(cwc1["suggested_citations"]) == 1
        assert cwc1["suggested_citations"][0]["title"] == "FastTransformer 2023"

        # External source filtered
        assert result["external_sources"] == []

        # Judge output stored in state
        assert result["citation_judge_output"]["overall_citation_quality"] == "medium"

    @pytest.mark.unit
    @patch("app.workflows.draft_analysis.nodes.citation_judge.client")
    def test_citation_judge_skips_when_nothing_to_judge(self, mock_client):
        from app.workflows.draft_analysis.nodes.citation_judge import citation_judge_node

        state = {
            "draft_id": "d1", "project_id": "p1", "user_id": "u1",
            "draft_content": "text", "current_step": "citation_judge", "progress_percentage": 76,
            "claims_with_citations": [
                {"claim": {"claim_text": "Some claim"}, "citations": [], "suggested_citations": []},
            ],
            "external_sources": [],
        }
        result = asyncio.run(citation_judge_node(state))

        mock_client.beta.chat.completions.parse.assert_not_called()
        assert "Skipped" in result["current_step"]

    @pytest.mark.unit
    @patch("app.workflows.draft_analysis.nodes.citation_judge.client")
    def test_citation_judge_failure_is_nonfatal(self, mock_client):
        from app.workflows.draft_analysis.nodes.citation_judge import citation_judge_node

        mock_client.beta.chat.completions.parse = AsyncMock(side_effect=Exception("API error"))

        state = {
            "draft_id": "d1", "project_id": "p1", "user_id": "u1",
            "draft_content": "text", "current_step": "citation_judge", "progress_percentage": 76,
            "claims_with_citations": [
                {
                    "claim": {"claim_text": "Claim X"},
                    "citations": [],
                    "suggested_citations": [{"title": "Paper A"}],
                },
            ],
            "external_sources": [{"title": "External B"}],
        }
        result = asyncio.run(citation_judge_node(state))

        # Failure must be non-fatal; suggested_citations fail-closed, external_sources fail-open.
        assert "Failed" in result["current_step"]
        assert "error" in result["citation_judge_output"]
        assert result["citation_judge_output"]["overall_citation_quality"] == "low"
        assert result["citation_judge_output"]["fail_closed"] is True
        # external_sources are pre-filtered upstream, so kept on judge failure
        assert result["external_sources"] == [{"title": "External B"}]
        assert result["claims_with_citations"][0]["suggested_citations"] == []

    def test_citation_judge_drops_items_when_no_verdicts_returned(self):
        """suggested_citations fail-closed on empty verdicts; external_sources fail-open."""
        from app.workflows.draft_analysis.nodes.citation_judge import _apply_verdicts
        from app.workflows.draft_analysis.schemas import CitationJudgeOutput

        empty_output = CitationJudgeOutput()
        state = {
            "claims_with_citations": [
                {
                    "claim": {"claim_text": "Claim A"},
                    "suggested_citations": [{"title": "Paper X"}],
                }
            ],
            "external_sources": [{"title": "External Y"}],
        }
        filtered_cwc, filtered_ext = _apply_verdicts(state, empty_output, [], [])
        assert filtered_cwc[0]["suggested_citations"] == []
        # external_sources: fail-open (pre-filtered upstream, only drop on explicit reject)
        assert filtered_ext == [{"title": "External Y"}]


# ── Reviewer Judge Node ───────────────────────────────────────────────────────

class TestReviewerJudgeNode:

    def _reviewer_outputs(self):
        return [
            {
                "reviewer_id": "literature_positioning",
                "summary": "Good literature positioning overall.",
                "strengths": ["Clear contribution in Section 2"],
                "weaknesses": ["The authors should clarify methodology"],  # vague
                "questions_to_authors": ["Can you provide more details?"],  # vague
                "limitations_to_address": [],
                "rating": 6, "confidence": 3, "recommendation": "minor_revision",
            },
            {
                "reviewer_id": "methodology",
                "summary": "Section 4.2 lacks SOTA baselines.",
                "strengths": ["Table 2 results are strong"],
                "weaknesses": ["Figure 3 shows no error bars — Equation 5 not reproducible"],
                "questions_to_authors": ["Why was method X from Smith et al. 2023 excluded?"],
                "limitations_to_address": ["Ablation for hyperparameter λ needed"],
                "rating": 5, "confidence": 4, "recommendation": "major_revision",
            },
        ]

    @pytest.mark.unit
    @patch("app.workflows.draft_analysis.nodes.reviewer_judge.supabase")
    @patch("app.workflows.draft_analysis.nodes.reviewer_judge.client")
    def test_reviewer_judge_passes_high_quality_panel(self, mock_client, mock_supabase):
        from app.workflows.draft_analysis.nodes.reviewer_judge import reviewer_judge_node
        from app.workflows.draft_analysis.schemas import ReviewerJudgeOutput, ReviewerJudgeScore

        fake_judge = ReviewerJudgeOutput(
            reviewer_scores=[
                ReviewerJudgeScore(reviewer_id="literature_positioning", specificity_score=0.8, quality_pass=True),
                ReviewerJudgeScore(reviewer_id="methodology", specificity_score=0.9, quality_pass=True),
            ],
            panel_quality="high",
            retry_reviewer_ids=[],
        )
        mock_client.beta.chat.completions.parse = AsyncMock(
            return_value=SimpleNamespace(parsed=fake_judge)
        )

        state = {
            "draft_id": "d1", "project_id": "p1", "user_id": "u1",
            "draft_content": "text", "current_step": "reviewer_judge", "progress_percentage": 85,
            "reviewer_outputs": self._reviewer_outputs(),
        }
        result = asyncio.run(reviewer_judge_node(state))

        assert result["reviewer_judge_output"]["panel_quality"] == "high"
        assert result["reviewer_judge_output"]["retry_reviewer_ids"] == []
        # No retry calls — parse called exactly once (for the judge)
        assert mock_client.beta.chat.completions.parse.call_count == 1

    @pytest.mark.unit
    @patch("app.workflows.draft_analysis.nodes.reviewer_judge.supabase")
    @patch("app.workflows.draft_analysis.nodes.reviewer_judge.client")
    def test_reviewer_judge_retries_low_specificity_reviewer(self, mock_client, mock_supabase):
        from app.workflows.draft_analysis.nodes.reviewer_judge import reviewer_judge_node
        from app.workflows.draft_analysis.schemas import ReviewerJudgeOutput, ReviewerJudgeScore, ReviewerOutput

        fake_judge = ReviewerJudgeOutput(
            reviewer_scores=[
                ReviewerJudgeScore(
                    reviewer_id="literature_positioning",
                    specificity_score=0.2,
                    vague_items=["The authors should clarify", "more details needed"],
                    quality_pass=False,
                ),
            ],
            panel_quality="low",
            retry_reviewer_ids=["literature_positioning"],
        )
        retried_output = ReviewerOutput(
            reviewer_id="literature_positioning",
            summary="Section 2.1 contribution over Smith et al. 2022 is clear.",
            strengths=["Theorem 1 proof is rigorous"],
            weaknesses=["Equation 3 has no ablation in Section 4"],
            questions_to_authors=["Is Figure 2 normalized by dataset size?"],
            limitations_to_address=["Generalization beyond benchmark X"],
            rating=6, confidence=3, recommendation="minor_revision",
        )

        # First call = judge, second call = retry generation
        mock_client.beta.chat.completions.parse = AsyncMock(side_effect=[
            SimpleNamespace(parsed=fake_judge),
            SimpleNamespace(parsed=retried_output),
        ])
        mock_supabase.table.return_value.delete.return_value.eq.return_value.eq.return_value \
            .execute.return_value = MagicMock(data=[])
        mock_supabase.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[{}])

        state = {
            "draft_id": "d1", "project_id": "p1", "user_id": "u1",
            "draft_content": "text", "current_step": "reviewer_judge", "progress_percentage": 85,
            "reviewer_outputs": self._reviewer_outputs()[:1],  # only literature_positioning
        }
        result = asyncio.run(reviewer_judge_node(state))

        # parse called twice: 1 judge + 1 retry
        assert mock_client.beta.chat.completions.parse.call_count == 2
        # Updated output stored in judged_reviewer_outputs (not reviewer_outputs — that has additive reducer)
        assert result["judged_reviewer_outputs"][0]["summary"] == retried_output.summary
        assert result["reviewer_judge_output"]["retry_reviewer_ids"] == ["literature_positioning"]

    @pytest.mark.unit
    @patch("app.workflows.draft_analysis.nodes.reviewer_judge.client")
    def test_reviewer_judge_failure_is_nonfatal(self, mock_client):
        from app.workflows.draft_analysis.nodes.reviewer_judge import reviewer_judge_node

        mock_client.beta.chat.completions.parse = AsyncMock(side_effect=Exception("GPT down"))

        state = {
            "draft_id": "d1", "project_id": "p1", "user_id": "u1",
            "draft_content": "text", "current_step": "reviewer_judge", "progress_percentage": 85,
            "reviewer_outputs": self._reviewer_outputs(),
        }
        result = asyncio.run(reviewer_judge_node(state))

        assert "Failed" in result["current_step"]
        assert "error" in result["reviewer_judge_output"]

    @pytest.mark.unit
    @patch("app.workflows.draft_analysis.nodes.reviewer_judge.client")
    def test_reviewer_judge_skips_when_no_outputs(self, mock_client):
        from app.workflows.draft_analysis.nodes.reviewer_judge import reviewer_judge_node

        state = {
            "draft_id": "d1", "project_id": "p1", "user_id": "u1",
            "draft_content": "text", "current_step": "reviewer_judge", "progress_percentage": 85,
            "reviewer_outputs": [],
        }
        result = asyncio.run(reviewer_judge_node(state))

        mock_client.beta.chat.completions.parse.assert_not_called()
        assert "Skipped" in result["current_step"]

    @pytest.mark.unit
    @patch("app.workflows.draft_analysis.nodes.reviewer_judge.supabase")
    @patch("app.workflows.draft_analysis.nodes.reviewer_judge.client")
    def test_reviewer_judge_retry_failure_keeps_original(self, mock_client, mock_supabase):
        """If retry GPT call fails, original reviewer output is preserved."""
        from app.workflows.draft_analysis.nodes.reviewer_judge import reviewer_judge_node
        from app.workflows.draft_analysis.schemas import ReviewerJudgeOutput, ReviewerJudgeScore

        fake_judge = ReviewerJudgeOutput(
            reviewer_scores=[
                ReviewerJudgeScore(reviewer_id="literature_positioning", specificity_score=0.1, quality_pass=False),
            ],
            panel_quality="low",
            retry_reviewer_ids=["literature_positioning"],
        )
        mock_client.beta.chat.completions.parse = AsyncMock(side_effect=[
            SimpleNamespace(parsed=fake_judge),
            Exception("Retry also failed"),
        ])
        mock_supabase.table.return_value.delete.return_value.eq.return_value.eq.return_value \
            .execute.return_value = MagicMock(data=[])

        original_summary = self._reviewer_outputs()[0]["summary"]
        state = {
            "draft_id": "d1", "project_id": "p1", "user_id": "u1",
            "draft_content": "text", "current_step": "reviewer_judge", "progress_percentage": 85,
            "reviewer_outputs": self._reviewer_outputs()[:1],
        }
        result = asyncio.run(reviewer_judge_node(state))

        # Original output preserved in judged_reviewer_outputs on retry failure
        assert result["judged_reviewer_outputs"][0]["summary"] == original_summary


# ── Graph Topology ────────────────────────────────────────────────────────────

class TestGraphTopology:

    def test_graph_compiles_without_error(self):
        from app.workflows.draft_analysis.graph import create_draft_analysis_workflow
        workflow = create_draft_analysis_workflow()
        assert workflow is not None

    def test_graph_has_citation_judge_node(self):
        from app.workflows.draft_analysis.graph import create_draft_analysis_workflow
        workflow = create_draft_analysis_workflow()
        assert "citation_judge_node" in workflow.get_graph().nodes

    def test_graph_has_reviewer_judge_node(self):
        from app.workflows.draft_analysis.graph import create_draft_analysis_workflow
        workflow = create_draft_analysis_workflow()
        assert "reviewer_judge_node" in workflow.get_graph().nodes

    def test_citation_judge_before_diagnostics_and_structural_checks(self):
        """citation_judge_node must sit before diagnostics and structural_checks."""
        from app.workflows.draft_analysis.graph import create_draft_analysis_workflow
        workflow = create_draft_analysis_workflow()
        graph = workflow.get_graph()
        edges = {(e.source, e.target) for e in graph.edges}
        assert ("discover_external_sources", "citation_judge_node") in edges
        assert ("citation_judge_node", "run_quality_diagnostics") in edges
        assert ("run_quality_diagnostics", "structural_checks") in edges

    def test_reviewer_judge_between_reviewer_panel_and_meta_reviewer(self):
        """reviewer_judge_node must sit between reviewer_panel_node and meta_reviewer_node."""
        from app.workflows.draft_analysis.graph import create_draft_analysis_workflow
        workflow = create_draft_analysis_workflow()
        graph = workflow.get_graph()
        edges = {(e.source, e.target) for e in graph.edges}
        assert ("reviewer_panel_node", "reviewer_judge_node") in edges
        assert ("reviewer_judge_node", "meta_reviewer_node") in edges

    def test_route_to_reviewer_panel_fan_out(self):
        from app.workflows.draft_analysis.graph import route_to_reviewer_panel, REVIEWER_TYPES
        from langgraph.types import Send

        state = {"editor_decision": {"proceed_to_review": True}, "draft_id": "d1"}
        result = route_to_reviewer_panel(state)
        assert isinstance(result, list)
        assert len(result) == 3
        assert all(isinstance(s, Send) for s in result)
        sent_types = [s.node for s in result]
        assert all(n == "reviewer_panel_node" for n in sent_types)

    def test_route_to_reviewer_panel_desk_reject(self):
        from app.workflows.draft_analysis.graph import route_to_reviewer_panel
        state = {"editor_decision": {"proceed_to_review": False}}
        result = route_to_reviewer_panel(state)
        assert result == "synthesize_report"

    def test_route_to_reviewer_panel_missing_editor_decision_defaults_to_fanout(self):
        """Missing editor_decision should default to proceeding with review."""
        from app.workflows.draft_analysis.graph import route_to_reviewer_panel
        from langgraph.types import Send
        state = {}
        result = route_to_reviewer_panel(state)
        assert isinstance(result, list)
        assert len(result) == 3


# ── API response fields ───────────────────────────────────────────────────────

class TestAPIResponseFields:
    """Smoke-check that drafts route exposes Phase 3+4 fields."""

    def test_analyzed_response_includes_judge_fields(self):
        """
        Verify the drafts GET route source references Phase 3+4 response keys.
        Uses direct file read to avoid triggering weasyprint/libgobject at import time.
        """
        import os
        route_path = os.path.join(
            os.path.dirname(__file__),
            "..", "app", "api", "routes", "drafts.py",
        )
        with open(os.path.abspath(route_path)) as f:
            source = f.read()

        for field in ("citation_judge", "reviewer_judge", "reviewer_panel", "meta_review", "editor_decision"):
            assert field in source, f"Missing field '{field}' in drafts.py response"

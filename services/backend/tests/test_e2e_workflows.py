"""
End-to-end workflow tests using mocked external dependencies.

These tests verify the complete LangGraph workflow nodes work together
without making real API calls or database writes.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


# ── LangGraph Workflow State Tests ────────────────────────────────────────────

class TestDraftAnalysisState:
    """Tests for the DraftAnalysisState schema."""

    @pytest.mark.unit
    def test_state_schema_imports(self):
        """DraftAnalysisState and related types can be imported."""
        from app.workflows.draft_analysis.state import (
            DraftAnalysisState,
            Claim,
            Gap,
            Feedback,
        )
        assert DraftAnalysisState is not None

    @pytest.mark.unit
    def test_minimal_state_creation(self):
        """Minimal state dict satisfies DraftAnalysisState requirements."""
        from app.workflows.draft_analysis.state import DraftAnalysisState

        state: DraftAnalysisState = {
            "draft_id": "draft-123",
            "project_id": "proj-456",
            "user_id": "user-789",
            "draft_content": "This is a test draft.",
            "current_step": "initialization",
            "progress_percentage": 0,
        }

        assert state["draft_id"] == "draft-123"
        assert state["progress_percentage"] == 0


# ── Reviewer Feedback Node E2E Tests ─────────────────────────────────────────

class TestReviewerFeedbackNodeE2E:
    """End-to-end tests for reviewer feedback node."""

    @pytest.mark.unit
    @patch("app.workflows.draft_analysis.nodes.reviewer_feedback.supabase")
    @patch("app.workflows.draft_analysis.nodes.reviewer_feedback.client")
    def test_generate_feedback_with_literature_context(self, mock_client, mock_supabase):
        """Feedback node passes literature context to GPT."""
        from app.workflows.draft_analysis.nodes.reviewer_feedback import generate_reviewer_feedback_node

        # No existing feedback in DB
        mock_supabase.table.return_value.select.return_value\
            .eq.return_value.execute.return_value.data = []

        # GPT response
        mock_response = MagicMock()
        mock_response.choices[0].message.content = """{
            "feedback_items": [
                {
                    "feedback_type": "weakness",
                    "feedback_text": "The claim about BERT lacks citation support. Consider citing 'Attention Is All You Need' (Vaswani et al., 2017) which directly supports this.",
                    "severity": "major",
                    "section_reference": "Methods"
                }
            ],
            "overall_assessment": "Strong paper with minor gaps.",
            "priority_actions": ["Add citations for key claims", "Expand methodology section"]
        }"""
        mock_client.chat.completions.create.return_value = mock_response

        state = {
            "draft_id": "draft-123",
            "project_id": "proj-456",
            "user_id": "user-789",
            "draft_content": "We propose a novel approach...",
            "current_step": "citation_mapping",
            "progress_percentage": 75,
            "structure": {"word_count": 5000, "page_count": 10},
            "claims": [{"id": "c1", "claim_text": "Our model outperforms BERT", "claim_type": "empirical", "section_location": "Methods", "importance_score": 0.9}],
            "claims_with_citations": [],
            "coverage_gaps": [],
            "primary_claims": [],
            "supporting_claims": [],
            "literature_search_results": [
                {
                    "claim_id": "c1",
                    "results": [
                        {
                            "document_title": "Attention Is All You Need",
                            "authors": "Vaswani et al.",
                            "content": "The Transformer architecture...",
                            "similarity": 0.87,
                        }
                    ]
                }
            ]
        }

        result = generate_reviewer_feedback_node(state)

        assert "reviewer_feedback" in result
        assert len(result["reviewer_feedback"]) == 1

        # Verify literature context was sent to GPT
        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs.get("messages") or call_args.args[0] if call_args.args else None
        if messages is None and call_args.kwargs:
            messages = call_args.kwargs.get("messages", [])

        # Find user message content
        user_msg = next(
            (m["content"] for m in (messages or []) if m.get("role") == "user"),
            ""
        )
        assert "Attention Is All You Need" in user_msg

    @pytest.mark.unit
    @patch("app.workflows.draft_analysis.nodes.reviewer_feedback.supabase")
    @patch("app.workflows.draft_analysis.nodes.reviewer_feedback.client")
    def test_generate_feedback_skips_if_existing(self, mock_client, mock_supabase):
        """Feedback node skips generation if feedback already in DB."""
        from app.workflows.draft_analysis.nodes.reviewer_feedback import generate_reviewer_feedback_node

        # Existing feedback in DB
        mock_supabase.table.return_value.select.return_value\
            .eq.return_value.execute.return_value.data = [
                {
                    "id": "fb-1",
                    "feedback_type": "weakness",
                    "feedback_text": "Cached feedback",
                    "severity": "major",
                    "section_reference": "Introduction"
                }
            ]

        state = {
            "draft_id": "draft-with-existing-feedback",
            "project_id": "proj-456",
            "user_id": "user-789",
            "draft_content": "...",
            "current_step": "citation_mapping",
            "progress_percentage": 75,
        }

        result = generate_reviewer_feedback_node(state)

        # Should not call GPT if feedback already exists
        mock_client.chat.completions.create.assert_not_called()
        assert "reviewer_feedback" in result
        assert result["current_step"] == "Reviewer Feedback (Cached)"


# ── Gap Detection Node E2E Tests ──────────────────────────────────────────────

class TestGapDetectionNodeE2E:
    """End-to-end tests for the gap detection node."""

    @pytest.mark.unit
    @patch("app.workflows.draft_analysis.nodes.gap_detection.supabase")
    def test_detect_gaps_no_citation_data(self, mock_supabase):
        """Gap detection returns early when no citation data available."""
        from app.workflows.draft_analysis.nodes.gap_detection import detect_gaps_node

        # No existing gaps
        mock_supabase.table.return_value.select.return_value\
            .eq.return_value.execute.return_value.data = []

        state = {
            "draft_id": "draft-123",
            "project_id": "proj-456",
            "user_id": "user-789",
            "draft_content": "...",
            "current_step": "citation_mapping",
            "progress_percentage": 65,
            "claims_with_citations": [],  # Empty — triggers early return
        }

        result = detect_gaps_node(state)

        assert result["current_step"] == "Gap Detection (No Data)"

    @pytest.mark.unit
    @patch("app.workflows.draft_analysis.nodes.gap_detection.supabase")
    def test_detect_gaps_missing_evidence(self, mock_supabase):
        """Claims with no citations generate missing_evidence gaps."""
        from app.workflows.draft_analysis.nodes.gap_detection import detect_gaps_node

        # No existing gaps in DB
        mock_supabase.table.return_value.select.return_value\
            .eq.return_value.execute.return_value.data = []

        state = {
            "draft_id": "draft-123",
            "project_id": "proj-456",
            "user_id": "user-789",
            "draft_content": "...",
            "current_step": "citation_mapping",
            "progress_percentage": 65,
            "claims_with_citations": [
                {
                    "claim": {
                        "id": "c1",
                        "claim_text": "Our approach outperforms all baselines",
                        "claim_type": "empirical",
                        "section_location": "Results",
                        "importance_score": 0.9,
                    },
                    "citations": [],
                    "citation_quality": "none",
                    "gaps": [],
                }
            ],
            "claims_by_type": {},
        }

        result = detect_gaps_node(state)

        assert "coverage_gaps" in result
        gaps = result["coverage_gaps"]
        assert len(gaps) > 0
        assert any(g["gap_type"] == "missing_evidence" for g in gaps)
        # High importance + no citations = critical
        critical_gaps = [g for g in gaps if g["severity"] == "critical"]
        assert len(critical_gaps) > 0


# ── Literature Search Node Tests ──────────────────────────────────────────────

class TestLiteratureSearchNode:
    """Tests for the literature search node."""

    @pytest.mark.unit
    @patch("app.workflows.draft_analysis.nodes.literature_search.supabase")
    def test_search_returns_empty_when_no_documents(self, mock_supabase):
        """Search returns empty when project has no documents."""
        from app.workflows.draft_analysis.nodes.literature_search import literature_search_node

        # No claims
        state = {
            "draft_id": "draft-123",
            "project_id": "proj-456",
            "user_id": "user-789",
            "draft_content": "...",
            "current_step": "claim_categorization",
            "progress_percentage": 40,
            "claims": [],  # No claims
        }

        result = asyncio.run(literature_search_node(state))

        assert result["literature_search_results"] == []
        assert "No Claims" in result["current_step"]

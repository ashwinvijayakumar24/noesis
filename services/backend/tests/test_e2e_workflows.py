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


# ── Gap Detection Node E2E Tests ──────────────────────────────────────────────

class TestGapDetectionNodeE2E:
    """End-to-end tests for the gap detection node."""

    @pytest.mark.unit
    def test_detect_gaps_no_citation_data(self):
        """Gap detection returns early when no citation data available."""
        from app.workflows.draft_analysis.nodes.gap_detection import detect_gaps_node

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
    def test_detect_gaps_missing_evidence(self):
        """Claims with no citations generate missing_evidence gaps."""
        from app.workflows.draft_analysis.nodes.gap_detection import detect_gaps_node

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

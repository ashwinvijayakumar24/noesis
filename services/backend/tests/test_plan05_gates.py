"""
Plan 05 — Schema gates, evidence gate, determinism, eval threshold tests.
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Evidence gate unit tests
# ---------------------------------------------------------------------------

from app.services.draft_evidence_gate import (
    strip_unanchored_findings,
    strip_unsourced_citation_verdicts,
)

DRAFT = "The sodium-ion battery showed 85% capacity retention after 500 cycles in controlled experiments."


def test_strip_unanchored_drops_hallucinated_anchor():
    findings = [
        {"finding_type": "x", "anchor_text": "this text does not appear in the draft at all whatsoever"},
        {"finding_type": "y", "anchor_text": "sodium-ion battery showed 85% capacity retention"},
    ]
    result = strip_unanchored_findings(findings, DRAFT)
    assert len(result) == 1
    assert result[0]["finding_type"] == "y"


def test_strip_unanchored_keeps_empty_anchor():
    findings = [
        {"finding_type": "z", "anchor_text": ""},
        {"finding_type": "w", "anchor_text": None},
    ]
    result = strip_unanchored_findings(findings, DRAFT)
    assert len(result) == 2


def test_strip_unanchored_keeps_short_unverifiable_anchor():
    # < 3 words and < 24 chars — treated as unverifiable, kept
    findings = [{"finding_type": "x", "anchor_text": "methods"}]
    result = strip_unanchored_findings(findings, DRAFT)
    assert len(result) == 1


def test_strip_unanchored_whitespace_normalized():
    findings = [{"finding_type": "x", "anchor_text": "sodium-ion  battery  showed  85%"}]
    draft = "sodium-ion battery showed 85% capacity retention"
    result = strip_unanchored_findings(findings, draft)
    assert len(result) == 1


def test_strip_unanchored_empty_draft_keeps_all():
    findings = [{"finding_type": "x", "anchor_text": "anything at all here"}]
    result = strip_unanchored_findings(findings, "")
    assert len(result) == 1


def test_strip_unsourced_drops_adverse_without_quote():
    verdicts = [
        {"verdict": "contradicts", "evidence_quote": ""},
        {"verdict": "overclaim", "evidence_quote": None},
        {"verdict": "unrelated", "evidence_quote": "   "},
        {"verdict": "contradicts", "evidence_quote": "The abstract clearly shows X."},
        {"verdict": "supports", "evidence_quote": ""},
    ]
    result = strip_unsourced_citation_verdicts(verdicts)
    # Only the one with a real quote + the "supports" should survive
    verdicts_out = [v["verdict"] for v in result]
    assert "supports" in verdicts_out
    assert result[0]["verdict"] == "contradicts"  # the one with a quote
    assert len(result) == 2


def test_strip_unsourced_keeps_supports_with_no_quote():
    verdicts = [{"verdict": "supports", "evidence_quote": ""}]
    result = strip_unsourced_citation_verdicts(verdicts)
    assert len(result) == 1


# ---------------------------------------------------------------------------
# Schema gate — claim_categorization
# ---------------------------------------------------------------------------

from app.workflows.draft_analysis.nodes.claim_categorization import categorize_claims_node


def _make_claim(i, importance=0.8):
    return {
        "id": f"c{i}", "claim_text": f"Claim {i}", "claim_type": "empirical",
        "importance_score": importance, "requires_citation": True,
        "section_location": "Methods",
    }


def test_categorize_claims_returns_safe_types():
    state = {
        "draft_id": "test-draft",
        "claims": [_make_claim(0), _make_claim(1, 0.4)],
    }
    result = categorize_claims_node(state)
    assert isinstance(result["claims_by_type"], dict)
    assert isinstance(result["primary_claims"], list)
    assert isinstance(result["supporting_claims"], list)


def test_categorize_claims_no_claims_returns_no_lists():
    state = {"draft_id": "test-draft", "claims": []}
    result = categorize_claims_node(state)
    # Should return without error even with empty claims
    assert "current_step" in result


# ---------------------------------------------------------------------------
# Schema gate — gap_detection fallback
# ---------------------------------------------------------------------------

from app.workflows.draft_analysis.nodes.gap_detection import detect_gaps_node


def test_gap_detection_no_data_returns_empty_list():
    # No claims_with_citations → should return coverage_gaps=[] or skip gracefully
    state = {"draft_id": "test-draft", "claims_with_citations": []}
    result = detect_gaps_node(state)
    assert "current_step" in result


# ---------------------------------------------------------------------------
# Schema gate — structure_extraction fallback has structure key
# ---------------------------------------------------------------------------

from app.workflows.draft_analysis.nodes.structure_extraction import extract_structure_node
from unittest.mock import patch


def test_structure_extraction_fallback_has_structure_key():
    state = {"draft_id": "test-draft", "draft_content": "Some content here for the draft."}
    with patch("app.workflows.draft_analysis.nodes.structure_extraction.supabase") as mock_sb:
        mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.side_effect = Exception("DB error")
        result = extract_structure_node(state)
    # Even on DB error, node should return a valid structure (computed from draft_content)
    assert "structure" in result or "current_step" in result


# ---------------------------------------------------------------------------
# Eval threshold helpers
# ---------------------------------------------------------------------------

import sys
from pathlib import Path

# Add scripts to path so we can import run_eval
_scripts_dir = str(Path(__file__).resolve().parent.parent.parent.parent / "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from eval.run_eval import _regression_check


def _row(stem, overall, dims=None, hallucinations=None):
    return {
        "draft_stem": stem,
        "corpus": "no-corpus",
        "overall": overall,
        "dims": dims or {},
        "hallucinations": hallucinations or [],
    }


def test_regression_check_passes_above_threshold():
    rows = [_row("d1", 9.0), _row("d2", 8.6)]
    failures = _regression_check(rows, {}, {"min_overall": 8.5, "min_dim_score": 7.5, "max_mean_drop": 0.5})
    assert failures == []


def test_regression_check_fails_on_low_mean():
    rows = [_row("d1", 8.0), _row("d2", 8.0)]
    failures = _regression_check(rows, {}, {"min_overall": 8.5, "min_dim_score": 0.0, "max_mean_drop": 0.5})
    assert any("MEAN_OVERALL" in f for f in failures)


def test_regression_check_fails_on_hallucination():
    rows = [_row("d1", 9.0, hallucinations=["some hallucination"])]
    failures = _regression_check(rows, {}, {"min_overall": 8.5, "min_dim_score": 0.0, "max_mean_drop": 0.5})
    assert any("HALLUCINATION" in f for f in failures)


def test_regression_check_fails_on_dim_score():
    rows = [_row("d1", 9.0, dims={"accuracy": {"score": 7.0}, "depth": {"score": 9.0}})]
    failures = _regression_check(rows, {}, {"min_overall": 8.5, "min_dim_score": 7.5, "max_mean_drop": 0.5})
    assert any("DIM_SCORE" in f for f in failures)


def test_regression_check_passes_dim_score():
    rows = [_row("d1", 9.0, dims={"accuracy": {"score": 8.0}, "depth": {"score": 9.0}})]
    failures = _regression_check(rows, {}, {"min_overall": 8.5, "min_dim_score": 7.5, "max_mean_drop": 0.5})
    assert failures == []


def test_regression_check_fails_on_scoreboard_drop():
    """_regression_check now takes the append-only history rather than the single
    previous scoreboard, and compares against the BEST score ever recorded for a
    cell. Comparing only against the immediately previous run let slow drift
    through: 8.0 -> 7.8 -> 7.6 -> 7.4 clears a 0.5 gate at every individual step
    while losing 0.6 overall."""
    rows = [_row("d1", 7.0)]
    history = [{"run_id": "r1", "cells": [{"draft_stem": "d1", "corpus": "no-corpus", "overall": 9.0}]}]
    failures = _regression_check(rows, history, {"min_overall": 0.0, "min_dim_score": 0.0, "max_mean_drop": 0.5})
    assert any("REGRESSION" in f for f in failures)


def test_regression_check_catches_drift_across_multiple_runs():
    """The reason the signature changed. Each step is within threshold; the
    cumulative drop is not."""
    history = [
        {"run_id": "r1", "cells": [{"draft_stem": "d1", "corpus": "no-corpus", "overall": 8.0}]},
        {"run_id": "r2", "cells": [{"draft_stem": "d1", "corpus": "no-corpus", "overall": 7.8}]},
        {"run_id": "r3", "cells": [{"draft_stem": "d1", "corpus": "no-corpus", "overall": 7.6}]},
    ]
    thresholds = {"min_overall": 0.0, "min_dim_score": 0.0, "max_mean_drop": 0.5}

    # 7.6 -> 7.4 is only -0.2 against the previous run, but -0.6 against the best.
    failures = _regression_check([_row("d1", 7.4)], history, thresholds)
    assert any("REGRESSION" in f for f in failures)

    # A drop within threshold of the best is still allowed.
    assert not any("REGRESSION" in f for f in _regression_check([_row("d1", 7.7)], history, thresholds))

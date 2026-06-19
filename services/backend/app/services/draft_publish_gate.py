"""Deterministic publish gate for draft analysis runs.

The LLM quality judge can reason but is fail-open. This gate adds a cheap,
deterministic check so a run is not presented as high-confidence when the
grounding is weak: low parser quality, insufficient page-anchor coverage on a
PDF, or source contamination. It records a verdict (``gate_status``,
``publishable``, ``confidence``, ``reasons``) rather than dropping feedback, so
the user still sees the analysis but is not misled about its reliability.

Thresholds are configurable via environment variables so they can be tuned
without code changes.
"""

from __future__ import annotations

import os
from typing import Any

_PDF_TYPES = {"pdf", "application/pdf"}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "").strip() or default)
    except (TypeError, ValueError):
        return default


# Minimum share of durable tasks that must carry a page/coordinate anchor on a
# PDF before the run is considered high-confidence.
PDF_PAGE_ANCHOR_COVERAGE_MIN = _env_float("DRAFT_PDF_PAGE_ANCHOR_COVERAGE_MIN", 0.75)
# Minimum parser quality score before a run is considered high-confidence.
PARSER_QUALITY_MIN = _env_float("DRAFT_PARSER_QUALITY_MIN", 0.55)

# When True, a non-publishable gate verdict HARD-FAILS the run (marked failed, no
# artifacts published) instead of the default soft behaviour (publish with a
# low-confidence label). Off by default so production keeps shipping feedback.
FAIL_CLOSED = os.getenv("DRAFT_ANALYSIS_FAIL_CLOSED", "").strip().lower() in {"1", "true", "yes", "on"}


# Preliminary (pre-reviewer) gate thresholds. If anchor coverage or parser quality is
# predictably below these early in the pipeline, the reviewer panel + meta-review are
# skipped entirely so tokens aren't burned on output the publish gate would suppress
# anyway (issue #12 — prevention, not cleanup).
PRELIM_PAGE_ANCHOR_MIN = _env_float("DRAFT_PRELIM_ANCHOR_MIN", 0.7)
PRELIM_PARSER_MIN = _env_float("DRAFT_PRELIM_PARSER_MIN", 0.6)


def should_halt_before_reviewers(
    *,
    page_anchor_coverage: float | None,
    parser_quality_score: float | None,
    parse_blocked: bool = False,
) -> dict[str, Any]:
    """Preliminary gate evaluated AFTER citation mapping / anchor scoring but BEFORE the
    reviewer panel. Returns {"halt": bool, "reasons": [...], "observed": {...}}.

    Halts when parser quality or page-anchor coverage predicts the publish gate will
    fail, so the expensive reviewer/meta LLM calls never run on a doomed parse."""
    reasons: list[str] = []
    if parse_blocked:
        reasons.append("parser halted extraction (parse_blocked)")
    if parser_quality_score is not None and float(parser_quality_score) < PRELIM_PARSER_MIN:
        reasons.append(
            f"parser_quality_score={parser_quality_score} < {PRELIM_PARSER_MIN}"
        )
    if page_anchor_coverage is not None and float(page_anchor_coverage) < PRELIM_PAGE_ANCHOR_MIN:
        reasons.append(
            f"page_anchor_coverage={page_anchor_coverage} < {PRELIM_PAGE_ANCHOR_MIN}"
        )
    return {
        "halt": bool(reasons),
        "reasons": reasons,
        "observed": {
            "page_anchor_coverage": page_anchor_coverage,
            "parser_quality_score": parser_quality_score,
            "parse_blocked": parse_blocked,
        },
    }


def _is_pdf(file_type: str | None) -> bool:
    return (file_type or "").lower() in _PDF_TYPES


def evaluate_publish_gate(
    *,
    file_type: str | None,
    revision_quality_metrics: dict[str, Any] | None,
    parser_quality: dict[str, Any] | None,
    source_safety_metrics: dict[str, Any] | None = None,
    contamination_flags: list[str] | None = None,
) -> dict[str, Any]:
    """Return a deterministic publish verdict.

    ``gate_status`` is one of ``ok`` | ``ok_sources_pruned`` | ``needs_retry`` | ``needs_parser_review``.
    ``publishable`` stays True for ``ok`` and ``ok_sources_pruned``; otherwise the run
    should be marked as low confidence (and optionally retried) rather than shipped as
    high-quality.

    ``ok_sources_pruned``: parser and page-anchor checks passed; contamination flags were
    recorded but sources are already stripped upstream — analysis is retained as-is.
    """
    metrics = revision_quality_metrics or {}
    parser = parser_quality or {}
    safety = source_safety_metrics or {}
    contamination_flags = [str(flag) for flag in (contamination_flags or []) if flag]

    reasons: list[str] = []
    gate_status = "ok"
    confidence = "high"
    publishable = True

    parser_score = parser.get("parser_quality_score")
    parse_blocked = bool(parser.get("parse_blocked"))
    parser_flags = list(parser.get("parser_quality_flags") or [])

    page_coverage = metrics.get("page_anchor_coverage")
    total_tasks = int(metrics.get("total_tasks") or 0)

    # 1. Parser quality is the strongest signal — bad text means bad analysis.
    if parse_blocked or (parser_score is not None and float(parser_score) < PARSER_QUALITY_MIN):
        gate_status = "needs_parser_review"
        publishable = False
        confidence = "low"
        detail = f"parser_quality_score={parser_score}"
        if parser_flags:
            detail += f" flags={parser_flags}"
        reasons.append(f"Low parser quality ({detail}); manuscript text may be incomplete or garbled.")

    # 2. Page-anchor coverage only applies to PDFs with at least one task.
    elif _is_pdf(file_type) and total_tasks > 0 and page_coverage is not None and float(page_coverage) < PDF_PAGE_ANCHOR_COVERAGE_MIN:
        gate_status = "needs_retry"
        publishable = False
        confidence = "low"
        reasons.append(
            f"Page-anchor coverage {page_coverage} below threshold {PDF_PAGE_ANCHOR_COVERAGE_MIN}; "
            "too many tasks cannot be located in the PDF."
        )

    # 3. Source contamination: flags are informational — sources are already pruned upstream
    # by sanitize_revision_task_sources before the gate runs. Record the flags and note
    # confidence as low-ish, but DO NOT fail the run when parser + anchor checks passed.
    # If a real hard-fail (parser / page-anchor) already set publishable=False, leave that
    # verdict untouched — contamination must not rescue a genuine failure either.
    if contamination_flags:
        reasons.append(
            f"Off-domain sources detected and pruned; analysis retained. "
            f"Contamination flags: {contamination_flags}"
        )
        if publishable:
            # Contamination-only path: analysis is clean, sources were already stripped.
            gate_status = "ok_sources_pruned"
            confidence = "low"
            # publishable remains True

    return {
        "gate_status": gate_status,
        "publishable": publishable,
        "confidence": confidence,
        "reasons": reasons,
        "thresholds": {
            "pdf_page_anchor_coverage_min": PDF_PAGE_ANCHOR_COVERAGE_MIN,
            "parser_quality_min": PARSER_QUALITY_MIN,
        },
        "observed": {
            "parser_quality_score": parser_score,
            "parse_blocked": parse_blocked,
            "page_anchor_coverage": page_coverage,
            "verbatim_anchor_coverage": metrics.get("verbatim_anchor_coverage"),
            "total_tasks": total_tasks,
            "sources_pruned": safety.get("sources_pruned"),
        },
    }

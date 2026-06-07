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

    ``gate_status`` is one of ``ok`` | ``needs_retry`` | ``needs_parser_review``.
    ``publishable`` stays True for ``ok``; otherwise the run should be marked as
    low confidence (and optionally retried) rather than shipped as high-quality.
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

    # 3. Source contamination is independent of the above — always downgrade.
    if contamination_flags:
        confidence = "low"
        publishable = False
        if gate_status == "ok":
            gate_status = "needs_retry"
        reasons.append(f"Source contamination flags present: {contamination_flags}")

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

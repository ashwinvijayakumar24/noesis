"""Privacy helpers for avoiding manuscript content in logs and checkpoints."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


SENSITIVE_CONTENT_KEYS = {
    "abstract",
    "anchor",
    "anchor_text",
    "analysis_text",
    "checkpoint_data",
    "claim",
    "claim_text",
    "content",
    "description",
    "draft_content",
    "feedback_text",
    "file_url",
    "full_text",
    "manuscript",
    "message",
    "paper_text",
    "prompt",
    "query",
    "section_text",
    "snippet",
    "specific_issue",
    "storage_path",
    "suggested_action",
    "text",
    "text_snippet",
    "title",
}


def safe_exception(exc: BaseException) -> str:
    """Return an exception label without serializing provider/request payloads."""
    return type(exc).__name__


def redacted_value(value: Any) -> str:
    """Return a non-content placeholder that preserves only coarse size metadata."""
    if value is None:
        return "[REDACTED]"
    try:
        return f"[REDACTED {type(value).__name__} len={len(value)}]"
    except Exception:
        return f"[REDACTED {type(value).__name__}]"


def sanitize_for_persistence(value: Any, *, max_depth: int = 5) -> Any:
    """
    Recursively remove manuscript-like content from diagnostic persistence.

    This is intentionally conservative. It keeps IDs, statuses, counts, scores,
    and timestamps while replacing text-bearing fields with placeholders.
    """
    if max_depth < 0:
        return redacted_value(value)

    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_str = str(key)
            key_lower = key_str.lower()
            if key_lower in SENSITIVE_CONTENT_KEYS or any(
                token in key_lower
                for token in ("content", "snippet", "anchor", "prompt", "message", "query", "text")
            ):
                sanitized[key_str] = redacted_value(item)
            else:
                sanitized[key_str] = sanitize_for_persistence(item, max_depth=max_depth - 1)
        return sanitized

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [sanitize_for_persistence(item, max_depth=max_depth - 1) for item in value[:50]]

    return value


def minimize_workflow_checkpoint(state: Mapping[str, Any]) -> dict[str, Any]:
    """Keep only non-content workflow progress for checkpoint persistence."""
    return {
        "draft_id": state.get("draft_id"),
        "project_id": state.get("project_id"),
        "user_id": state.get("user_id"),
        "paper_type": state.get("paper_type"),
        "citation_style": state.get("citation_style"),
        "current_step": state.get("current_step"),
        "progress_percentage": state.get("progress_percentage"),
        "search_iterations": state.get("search_iterations"),
        "max_search_iterations": state.get("max_search_iterations"),
        "counts": {
            "claims": len(state.get("claims") or []),
            "claims_with_citations": len(state.get("claims_with_citations") or []),
            "coverage_gaps": len(state.get("coverage_gaps") or []),
            "reviewer_feedback": len(state.get("reviewer_feedback") or []),
            "reviewer_outputs": len(state.get("reviewer_outputs") or []),
            "revision_tasks": len(state.get("revision_tasks") or []),
        },
        "errors": [
            safe_exception(error) if isinstance(error, BaseException) else "Error"
            for error in (state.get("errors") or [])[:10]
        ],
        "privacy_minimized": True,
    }


def strip_manuscript_content_from_structure(structure: Mapping[str, Any]) -> dict[str, Any]:
    """
    Remove raw section/paragraph text from a draft structure before DB storage.

    The original file remains in storage for the authenticated viewer and the
    analysis outputs keep short anchors. The structure table should not become
    a second full-manuscript store.
    """
    sanitized = dict(structure or {})
    sections = []
    for section in sanitized.get("sections") or []:
        if not isinstance(section, Mapping):
            continue
        section_copy = dict(section)
        section_copy.pop("content", None)
        section_copy.pop("paragraphs", None)
        if section.get("content") and "word_count" not in section_copy:
            section_copy["word_count"] = len(str(section.get("content")).split())
        sections.append(section_copy)
    sanitized["sections"] = sections
    return sanitized

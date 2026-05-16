"""
Draft anchoring and reviewer feedback QA helpers.

These utilities are intentionally bounded and side-effect free. They locate
draft snippets with deterministic fallbacks, then evaluate whether reviewer
feedback is specific, actionable, grounded, and anchored to the draft.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Tuple


ACTION_VERBS = {
    "add",
    "clarify",
    "compare",
    "cite",
    "define",
    "discuss",
    "explain",
    "include",
    "justify",
    "quantify",
    "report",
    "specify",
    "state",
    "test",
}

GENERIC_ISSUES = {
    "needs improvement",
    "unclear",
    "weak",
    "missing citation",
    "unsupported claim",
    "general feedback",
}


def _normalize_char(char: str) -> str:
    replacements = {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u00a0": " ",
    }
    return replacements.get(char, char).lower()


def normalize_for_match(text: str) -> str:
    """Normalize text for robust matching while preserving word order."""
    return re.sub(r"\s+", " ", "".join(_normalize_char(c) for c in text)).strip()


def _build_normalized_index(text: str) -> Tuple[str, List[int]]:
    """
    Build a normalized text string plus normalized-index to original-index map.

    Consecutive whitespace becomes one normalized space mapped to the first
    original whitespace character in that run.
    """
    normalized: List[str] = []
    index_map: List[int] = []
    pending_space = False
    pending_space_index: Optional[int] = None

    for original_index, char in enumerate(text):
        norm = _normalize_char(char)
        if norm.isspace():
            if not pending_space:
                pending_space = True
                pending_space_index = original_index
            continue

        if pending_space and normalized:
            normalized.append(" ")
            index_map.append(pending_space_index if pending_space_index is not None else original_index)
        pending_space = False
        pending_space_index = None

        normalized.append(norm)
        index_map.append(original_index)

    return "".join(normalized), index_map


def _line_location(draft_text: str, start: int, end: int) -> Dict[str, Optional[int]]:
    line_start = draft_text.rfind("\n", 0, start) + 1
    return {
        "line_number": draft_text[:start].count("\n") + 1,
        "char_start": start - line_start,
        "char_end": end - line_start,
    }


def _snippet(draft_text: str, start: int, end: int, radius: int) -> str:
    snippet_start = max(0, start - radius)
    snippet_end = min(len(draft_text), end + radius)
    return draft_text[snippet_start:snippet_end].strip()


def _find_normalized(needle: str, haystack: str) -> Optional[Tuple[int, int]]:
    normalized_haystack, index_map = _build_normalized_index(haystack)
    normalized_needle = normalize_for_match(needle)
    if not normalized_needle:
        return None

    normalized_start = normalized_haystack.find(normalized_needle)
    if normalized_start < 0:
        return None

    normalized_end = normalized_start + len(normalized_needle) - 1
    if normalized_start >= len(index_map) or normalized_end >= len(index_map):
        return None

    return index_map[normalized_start], index_map[normalized_end] + 1


def _candidate_sentences(text: str) -> Iterable[str]:
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        sentence = sentence.strip()
        if len(sentence) >= 30:
            yield sentence


def _candidate_windows(text: str) -> Iterable[str]:
    words = text.split()
    for window_size in (14, 10, 7):
        if len(words) < window_size:
            continue
        for index in range(0, len(words) - window_size + 1):
            candidate = " ".join(words[index:index + window_size])
            if len(candidate) >= 35:
                yield candidate


def _section_candidates(
    sections: Optional[List[Dict[str, Any]]],
    section_reference: Optional[str],
) -> Iterable[Dict[str, Any]]:
    if not sections:
        return

    normalized_ref = normalize_for_match(section_reference or "")
    for section in sections:
        title = normalize_for_match(str(section.get("title") or section.get("heading") or ""))
        content = normalize_for_match(str(section.get("content") or ""))
        if not normalized_ref or normalized_ref in title or normalized_ref in content:
            yield section


def _find_sentence_coords(
    sentences: List[Dict[str, Any]],
    paragraph_text: str,
    char_offset_in_paragraph: int,
) -> Optional[Dict[str, Any]]:
    """
    Find the sentence bounding box that contains the given char offset within a paragraph.
    Returns the sentence's `coords` dict, or None if no sentence match found.
    """
    cursor = 0
    for sent in sentences:
        text = str(sent.get("text") or "").strip()
        if not text:
            continue
        pos = paragraph_text.find(text, cursor)
        if pos < 0:
            continue
        end = pos + len(text)
        cursor = end
        if pos <= char_offset_in_paragraph <= end:
            coords = sent.get("coords")
            if coords and coords.get("page"):
                return coords
    return None


def _section_metadata(
    draft_text: str,
    sections: Optional[List[Dict[str, Any]]],
    section_reference: Optional[str],
    start: int,
) -> Dict[str, Any]:
    for section in _section_candidates(sections, section_reference):
        content = section.get("content") or ""
        section_start = draft_text.find(content) if content else -1
        section_end = section_start + len(content) if section_start >= 0 else -1
        if section_start >= 0 and section_start <= start <= section_end:
            char_offset_from_section = start - section_start
            metadata: Dict[str, Any] = {
                "section_id": section.get("id"),
                "char_offset_from_section": char_offset_from_section,
            }
            best_coords = None
            search_cursor = 0
            for paragraph in section.get("paragraphs") or []:
                paragraph_text = str(paragraph.get("text") or "").strip()
                if not paragraph_text:
                    continue
                paragraph_start = content.find(paragraph_text, search_cursor)
                if paragraph_start < 0:
                    continue
                paragraph_end = paragraph_start + len(paragraph_text)
                search_cursor = paragraph_end
                if paragraph_start <= char_offset_from_section <= paragraph_end:
                    # Try sentence-level coords first (finest granularity)
                    sentence_coords = _find_sentence_coords(
                        paragraph.get("sentences") or [],
                        paragraph_text,
                        char_offset_from_section - paragraph_start,
                    )
                    best_coords = sentence_coords or paragraph.get("coordinates")
                    break

            if best_coords:
                metadata["pdf_coordinates"] = best_coords
            elif section.get("coordinates"):
                metadata["pdf_coordinates"] = section.get("coordinates")
            return metadata
    return {}


def _anchor_result(
    draft_text: str,
    start: int,
    end: int,
    strategy: str,
    confidence: float,
    sections: Optional[List[Dict[str, Any]]],
    section_reference: Optional[str],
    radius: int,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "found": True,
        "strategy": strategy,
        "start_index": start,
        "end_index": end,
        "text_snippet": _snippet(draft_text, start, end, radius),
        "match_confidence": confidence,
    }
    result.update(_line_location(draft_text, start, end))
    result.update(_section_metadata(draft_text, sections, section_reference, start))
    return result


def locate_text_snippet(
    snippet: str,
    draft_text: str,
    *,
    sections: Optional[List[Dict[str, Any]]] = None,
    section_reference: Optional[str] = None,
    context_radius: int = 80,
) -> Dict[str, Any]:
    """
    Locate a snippet in draft text.

    Strategy order:
    1. Exact match
    2. Normalized match
    3. Sentence and word-window match
    4. Section fallback
    """
    snippet = (snippet or "").strip()
    if not snippet or not draft_text:
        return {
            "found": False,
            "strategy": "empty",
            "match_confidence": 0.0,
            "text_snippet": snippet[:150],
        }

    exact_start = draft_text.find(snippet)
    if exact_start >= 0:
        return _anchor_result(
            draft_text,
            exact_start,
            exact_start + len(snippet),
            "exact",
            0.95,
            sections,
            section_reference,
            context_radius,
        )

    normalized_match = _find_normalized(snippet, draft_text)
    if normalized_match:
        start, end = normalized_match
        return _anchor_result(
            draft_text,
            start,
            end,
            "normalized",
            0.88,
            sections,
            section_reference,
            context_radius,
        )

    for sentence in _candidate_sentences(snippet):
        sentence_match = _find_normalized(sentence, draft_text)
        if sentence_match:
            start, end = sentence_match
            return _anchor_result(
                draft_text,
                start,
                end,
                "sentence_window",
                0.74,
                sections,
                section_reference,
                context_radius,
            )

    for window in _candidate_windows(snippet):
        window_match = _find_normalized(window, draft_text)
        if window_match:
            start, end = window_match
            return _anchor_result(
                draft_text,
                start,
                end,
                "sentence_window",
                0.66,
                sections,
                section_reference,
                context_radius,
            )

    for section in _section_candidates(sections, section_reference):
        content = section.get("content") or ""
        section_match = _find_normalized(snippet, content)
        if section_match and content:
            section_start = draft_text.find(content)
            if section_start >= 0:
                rel_start, rel_end = section_match
                return _anchor_result(
                    draft_text,
                    section_start + rel_start,
                    section_start + rel_end,
                    "section_content",
                    0.62,
                    sections,
                    section_reference,
                    context_radius,
                )

        title = section.get("title") or section.get("heading") or section_reference
        if title:
            title_start = draft_text.find(str(title))
            if title_start >= 0:
                result = _anchor_result(
                    draft_text,
                    title_start,
                    title_start + len(str(title)),
                    "section_fallback",
                    0.46,
                    sections,
                    section_reference,
                    context_radius,
                )
                result["section_id"] = section.get("id")
                if section.get("coordinates"):
                    result["pdf_coordinates"] = section.get("coordinates")
                return result

    if section_reference:
        section_start = draft_text.lower().find(section_reference.lower())
        if section_start >= 0:
            return _anchor_result(
                draft_text,
                section_start,
                section_start + len(section_reference),
                "section_fallback",
                0.42,
                sections,
                section_reference,
                context_radius,
            )

    return {
        "found": False,
        "strategy": "not_found",
        "match_confidence": 0.0,
        "text_snippet": snippet[:150],
    }


def _claim_maps(claims: List[Dict[str, Any]]) -> Tuple[Dict[str, Dict[str, Any]], List[Dict[str, Any]]]:
    claim_map: Dict[str, Dict[str, Any]] = {}
    for index, claim in enumerate(claims, 1):
        claim_id = str(claim.get("id") or claim.get("claim_id") or index)
        claim_map[claim_id] = claim
        claim_map[f"claim_{index}"] = claim
    return claim_map, claims


def _gap_maps(gaps: List[Dict[str, Any]]) -> Tuple[Dict[str, Dict[str, Any]], List[Dict[str, Any]]]:
    gap_map: Dict[str, Dict[str, Any]] = {}
    for index, gap in enumerate(gaps, 1):
        gap_id = str(gap.get("id") or gap.get("gap_id") or index)
        gap_map[gap_id] = gap
        gap_map[f"gap_{index}"] = gap
    return gap_map, gaps


def _has_actionable_suggestion(feedback: Dict[str, Any]) -> bool:
    suggestions = (
        feedback.get("suggested_improvements")
        or feedback.get("suggestions")
        or feedback.get("action_items")
        or []
    )
    if isinstance(suggestions, str):
        suggestions = [suggestions]
    if not isinstance(suggestions, list):
        suggestions = []

    for suggestion in suggestions:
        text = normalize_for_match(str(suggestion))
        if len(text) < 20:
            continue
        first_word = text.split(" ", 1)[0]
        if first_word in ACTION_VERBS or any(f"{verb} " in text for verb in ACTION_VERBS):
            return True

    feedback_text = normalize_for_match(str(feedback.get("feedback_text") or ""))
    return any(f"{verb} " in feedback_text for verb in ACTION_VERBS)


def _specific_issue_ok(feedback: Dict[str, Any]) -> bool:
    issue = normalize_for_match(str(feedback.get("specific_issue") or ""))
    if len(issue) < 12:
        return False
    return issue not in GENERIC_ISSUES


def _source_grounding_ok(feedback: Dict[str, Any]) -> bool:
    grounding = feedback.get("source_grounding")
    cited_papers = feedback.get("cited_papers") or feedback.get("suggested_papers") or []
    if grounding:
        return True
    return isinstance(cited_papers, list) and len(cited_papers) > 0


def _infer_target_from_text(
    feedback: Dict[str, Any],
    claims: List[Dict[str, Any]],
    gaps: List[Dict[str, Any]],
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    text = normalize_for_match(
        " ".join(
            str(feedback.get(key) or "")
            for key in ("feedback_text", "specific_issue", "section_reference")
        )
    )
    for claim in claims:
        claim_text = normalize_for_match(str(claim.get("claim_text") or ""))
        if claim_text and (claim_text[:80] in text or text[:80] in claim_text):
            return claim, None
    for gap in gaps:
        gap_text = normalize_for_match(str(gap.get("description") or ""))
        if gap_text and (gap_text[:80] in text or text[:80] in gap_text):
            return None, gap
    return None, None


def evaluate_feedback_item(
    feedback: Dict[str, Any],
    draft_text: str,
    *,
    claims: Optional[List[Dict[str, Any]]] = None,
    gaps: Optional[List[Dict[str, Any]]] = None,
    sections: Optional[List[Dict[str, Any]]] = None,
    source_grounding_expected: bool = False,
    min_anchor_confidence: float = 0.45,
) -> Dict[str, Any]:
    """Evaluate one reviewer feedback item for specificity, actionability, grounding, and anchoring."""
    claims = claims or []
    gaps = gaps or []
    claim_map, claim_list = _claim_maps(claims)
    gap_map, gap_list = _gap_maps(gaps)
    failed_checks: List[str] = []
    warnings: List[str] = []

    target_claim_id = feedback.get("target_claim_id")
    target_gap_id = feedback.get("target_gap_id")
    target_claim = claim_map.get(str(target_claim_id)) if target_claim_id else None
    target_gap = gap_map.get(str(target_gap_id)) if target_gap_id else None

    if not target_claim and not target_gap:
        target_claim, target_gap = _infer_target_from_text(feedback, claim_list, gap_list)
        if target_claim:
            target_claim_id = target_claim.get("id") or target_claim.get("claim_id")
        if target_gap:
            target_gap_id = target_gap.get("id") or target_gap.get("gap_id")

    if feedback.get("feedback_type") != "strength" and not (target_claim or target_gap):
        failed_checks.append("missing_target_claim_or_gap")

    if not _specific_issue_ok(feedback) and feedback.get("feedback_type") != "strength":
        failed_checks.append("missing_specific_issue")

    if not _has_actionable_suggestion(feedback) and feedback.get("feedback_type") != "strength":
        failed_checks.append("missing_actionable_suggestion")

    if source_grounding_expected and feedback.get("feedback_type") != "strength" and not _source_grounding_ok(feedback):
        failed_checks.append("missing_source_grounding")

    anchor_source = (
        (target_claim or {}).get("claim_text")
        or (target_gap or {}).get("description")
        or feedback.get("specific_issue")
        or feedback.get("section_reference")
        or feedback.get("feedback_text")
        or ""
    )
    anchor = locate_text_snippet(
        str(anchor_source),
        draft_text,
        sections=sections,
        section_reference=feedback.get("section_reference"),
    )
    if not anchor.get("found") or anchor.get("match_confidence", 0.0) < min_anchor_confidence:
        failed_checks.append("weak_anchor")
    elif anchor.get("match_confidence", 0.0) < 0.65:
        warnings.append("low_confidence_anchor")

    return {
        "passed": len(failed_checks) == 0,
        "failed_checks": failed_checks,
        "warnings": warnings,
        "target_claim_id": target_claim_id,
        "target_gap_id": target_gap_id,
        "anchor": anchor,
    }


def evaluate_feedback_items(
    feedback_items: List[Dict[str, Any]],
    draft_text: str,
    *,
    claims: Optional[List[Dict[str, Any]]] = None,
    gaps: Optional[List[Dict[str, Any]]] = None,
    sections: Optional[List[Dict[str, Any]]] = None,
    source_grounding_expected: bool = False,
) -> List[Dict[str, Any]]:
    """Evaluate a batch of reviewer feedback items."""
    return [
        evaluate_feedback_item(
            item,
            draft_text,
            claims=claims,
            gaps=gaps,
            sections=sections,
            source_grounding_expected=source_grounding_expected,
        )
        for item in feedback_items
    ]


def attach_feedback_qa(
    feedback_items: List[Dict[str, Any]],
    draft_text: str,
    *,
    claims: Optional[List[Dict[str, Any]]] = None,
    gaps: Optional[List[Dict[str, Any]]] = None,
    sections: Optional[List[Dict[str, Any]]] = None,
    source_grounding_expected: bool = False,
) -> List[Dict[str, Any]]:
    """
    Return feedback items annotated with `qa_result` and anchor fields.

    The original list items are shallow-copied so callers can safely decide
    whether to persist these diagnostics.
    """
    evaluations = evaluate_feedback_items(
        feedback_items,
        draft_text,
        claims=claims,
        gaps=gaps,
        sections=sections,
        source_grounding_expected=source_grounding_expected,
    )
    annotated: List[Dict[str, Any]] = []
    for item, evaluation in zip(feedback_items, evaluations):
        next_item = dict(item)
        next_item["qa_result"] = evaluation
        anchor = evaluation.get("anchor") or {}
        if anchor.get("found"):
            for key in (
                "line_number",
                "char_start",
                "char_end",
                "text_snippet",
                "section_id",
                "char_offset_from_section",
                "pdf_coordinates",
                "match_confidence",
            ):
                if key in anchor and next_item.get(key) is None:
                    next_item[key] = anchor[key]
        if evaluation.get("target_claim_id") and not next_item.get("target_claim_id"):
            next_item["target_claim_id"] = evaluation["target_claim_id"]
        if evaluation.get("target_gap_id") and not next_item.get("target_gap_id"):
            next_item["target_gap_id"] = evaluation["target_gap_id"]
        annotated.append(next_item)
    return annotated


def select_failed_feedback_for_retry(
    feedback_items: List[Dict[str, Any]],
    evaluations: Optional[List[Dict[str, Any]]] = None,
    *,
    max_items: int = 5,
) -> List[Dict[str, Any]]:
    """
    Select only failed feedback items for conservative retry/regeneration.

    This does not call the model. It returns a small payload a caller can use
    to regenerate only failed items.
    """
    retry_payload: List[Dict[str, Any]] = []
    evaluations = evaluations or [item.get("qa_result", {}) for item in feedback_items]
    for item, evaluation in zip(feedback_items, evaluations):
        if evaluation.get("passed", False):
            continue
        retry_payload.append({
            "feedback": item,
            "failed_checks": evaluation.get("failed_checks", []),
            "anchor": evaluation.get("anchor"),
        })
        if len(retry_payload) >= max_items:
            break
    return retry_payload

"""Programmatic citation gates shared by draft-analysis nodes."""

from __future__ import annotations

import re
from typing import Any


AUTHOR_YEAR_RE = re.compile(
    r"(?:\([A-Z][A-Za-z-]+(?:\s+et\s+al\.)?,?\s+\d{4}[a-z]?\)|\b[A-Z][A-Za-z-]+(?:\s+et\s+al\.)?\s+\(\d{4}[a-z]?\))"
)
BRACKETED_NUMERIC_RE = re.compile(r"\[\s*([0-9]{1,3}(?:\s*[-,;]\s*[0-9]{1,3}){0,12})\s*\]")
COMPACT_NUMERIC_RE = re.compile(r"(?<!\d)(?<=[\]\)\.])\s*([0-9]{1,3}(?:\s*[-,;]\s*[0-9]{1,3}){0,12})(?![0-9])")
SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[])")


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(key)
    return result


def _normalize_numeric_group(value: str) -> list[str]:
    cleaned = re.sub(r"\s+", "", value or "")
    if not cleaned:
        return []
    parts = re.split(r"[,;]", cleaned)
    citations: list[str] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if re.fullmatch(r"\d{4}", part):
            continue
        if re.fullmatch(r"\d{1,3}-\d{1,3}", part):
            citations.append(part)
        elif re.fullmatch(r"\d{1,3}", part):
            citations.append(part)
    return citations


def normalize_citation_values(values: Any) -> list[str]:
    if not values:
        return []
    if isinstance(values, str):
        values = [values]
    citations: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        if AUTHOR_YEAR_RE.fullmatch(text):
            citations.append(text)
            continue
        numeric_matches = []
        numeric_matches.extend(match.group(1) for match in BRACKETED_NUMERIC_RE.finditer(text))
        numeric_matches.extend(match.group(1) for match in COMPACT_NUMERIC_RE.finditer(text))
        if numeric_matches:
            for group in numeric_matches:
                citations.extend(_normalize_numeric_group(group))
            continue
        if re.fullmatch(r"\d{1,3}(?:\s*[-,;]\s*\d{1,3}){0,12}", text):
            citations.extend(_normalize_numeric_group(text))
            continue
        citations.append(text)
    return _dedupe(citations)


def _find_fuzzy_fragment(haystack: str, words: list[str]) -> tuple[int, int] | None:
    if not haystack or not words:
        return None
    pattern = r"\b" + r"\W+".join(re.escape(word) for word in words) + r"\b"
    match = re.search(pattern, haystack, flags=re.IGNORECASE)
    if not match:
        return None
    return match.start(), match.end()


def extract_citations_from_text(text: str) -> list[str]:
    if not text:
        return []
    citations: list[str] = []
    citations.extend(match.group(0).strip() for match in AUTHOR_YEAR_RE.finditer(text))
    for match in BRACKETED_NUMERIC_RE.finditer(text):
        citations.extend(_normalize_numeric_group(match.group(1)))
    for match in COMPACT_NUMERIC_RE.finditer(text):
        value = match.group(1)
        # Avoid treating ordinary years or quantities as citation references.
        if re.fullmatch(r"\d{4}", value.strip()):
            continue
        citations.extend(_normalize_numeric_group(value))
    return _dedupe(citations)


def sentence_bounds_around_span(text: str, start: int, end: int) -> tuple[int, int]:
    start = max(0, start)
    end = max(start, min(len(text), end))
    left = start
    while left > 0:
        if text[left - 1] in ".!?" and (left >= len(text) or text[left:left + 1].isspace()):
            break
        if text[left - 1] == "\n" and text[max(0, left - 2):left] == "\n\n":
            break
        left -= 1
    right = end
    while right < len(text):
        ch = text[right]
        right += 1
        if ch in ".!?":
            while right < len(text) and text[right].isspace():
                right += 1
            while right < len(text) and re.match(r"[\[\]0-9,;\-\s]", text[right]):
                right += 1
            break
        if ch == "\n" and text[right:right + 1] == "\n":
            break
    return left, right


def citations_near_claim(
    claim_text: str,
    source_text: str,
    *,
    char_start: int | None = None,
    char_end: int | None = None,
) -> list[str]:
    if not claim_text or not source_text:
        return []

    start = char_start
    end = char_end
    if start is None or end is None or start < 0 or end <= start or end > len(source_text):
        idx = source_text.lower().find(claim_text.lower()[:120])
        if idx < 0:
            # Use the most distinctive trailing fragment for claims extracted
            # without the sentence lead-in.
            words = re.findall(r"[a-z0-9]+", claim_text.lower())
            for size in (18, 14, 10, 7, 4):
                if len(words) >= size:
                    fragment_span = _find_fuzzy_fragment(source_text, words[-size:])
                    if fragment_span:
                        start, end = fragment_span
                        break
        else:
            start = idx
            end = idx + len(claim_text)

    if end is None:
        return []

    sentence_start, sentence_end = sentence_bounds_around_span(source_text, start or end, end)
    window_start = max(0, min(sentence_start, end - 40))
    window_end = min(len(source_text), max(sentence_end, end) + 100)
    window = source_text[window_start:window_end]
    claim_offset = max(0, end - window_start)
    citations: list[str] = []
    for match in AUTHOR_YEAR_RE.finditer(window):
        if _citation_match_near_claim(window, claim_offset, match.start()):
            citations.append(match.group(0).strip())
    for pattern in (BRACKETED_NUMERIC_RE, COMPACT_NUMERIC_RE):
        for match in pattern.finditer(window):
            if not _citation_match_near_claim(window, claim_offset, match.start()):
                continue
            citations.extend(_normalize_numeric_group(match.group(1)))
    return _dedupe(citations)


def _citation_match_near_claim(window: str, claim_offset: int, match_start: int) -> bool:
    if match_start < max(0, claim_offset - 25):
        return False
    if match_start > claim_offset + 110:
        return False
    between = window[claim_offset:match_start]
    if len(between) > 140 or SENTENCE_BOUNDARY_RE.search(between):
        return False
    return True


def existing_citations(claim: dict[str, Any]) -> list[str]:
    return normalize_citation_values(claim.get("existing_citations") or [])


def has_existing_citation(claim: dict[str, Any]) -> bool:
    return bool(existing_citations(claim)) or bool(claim.get("has_inline_citation"))


def needs_missing_citation_task(claim: dict[str, Any]) -> bool:
    return claim.get("requires_citation") is True and not has_existing_citation(claim)


def apply_existing_citation_gate(claim: dict[str, Any]) -> dict[str, Any]:
    """Suppress missing-citation handling when the source text already cites the claim."""
    if not existing_citations(claim) and claim.get("text_snippet"):
        parsed = citations_near_claim(
            claim.get("claim_text", ""),
            claim.get("text_snippet", ""),
        )
        if parsed:
            claim["existing_citations"] = parsed
            claim["has_inline_citation"] = True
    if has_existing_citation(claim):
        claim["existing_citations"] = existing_citations(claim)
        claim["has_inline_citation"] = True
        claim["requires_citation"] = False
    return claim

"""Private parse artifacts for draft PDF grounding.

This module keeps a compact paragraph/section anchor map separate from the
public draft analysis payload. It avoids storing a second full manuscript copy
while preserving enough parser output to validate anchors and detect parser
quality failures before LLM review.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Mapping

from app.core.logging_config import get_logger
from app.core.privacy import safe_exception
from app.core.supabase_client import supabase

logger = get_logger(__name__)


class ParseQualityError(ValueError):
    """Raised when a PDF parse is too unreliable for analysis."""


def normalize_anchor_text(text: str) -> str:
    text = (text or "").replace("\u00ad", "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _snippet(text: str, limit: int = 700) -> str:
    normalized = normalize_anchor_text(text)
    if len(normalized) <= limit:
        return normalized
    clipped = normalized[:limit].rstrip()
    boundary = max(clipped.rfind("."), clipped.rfind(";"), clipped.rfind(","), clipped.rfind(" "))
    if boundary >= max(80, limit - 160):
        clipped = clipped[:boundary].rstrip(" ,;.")
    return f"{clipped.rstrip()}..."


def _hash_text(text: str) -> str:
    return hashlib.sha256(normalize_anchor_text(text).lower().encode("utf-8")).hexdigest()


def _section_type(title: str, section_type: str | None = None) -> str:
    if section_type and section_type != "other":
        return section_type
    lowered = (title or "").lower()
    if "abstract" in lowered or "summary" in lowered:
        return "abstract"
    if "introduction" in lowered or "background" in lowered:
        return "introduction"
    if "method" in lowered or "experimental" in lowered or "materials" in lowered:
        return "methods"
    if "result" in lowered or "finding" in lowered:
        return "results"
    if "discussion" in lowered:
        return "discussion"
    if "conclusion" in lowered:
        return "conclusion"
    if "significance" in lowered:
        return "abstract"
    return section_type or "other"


def build_structure_from_extracted_data(extracted_data: Mapping[str, Any]) -> dict[str, Any]:
    """Build the internal structure shape from GROBID extraction."""
    raw_sections = list(extracted_data.get("sections") or [])
    sections: list[dict[str, Any]] = []

    abstract = normalize_anchor_text(str(extracted_data.get("abstract") or ""))
    if abstract:
        abstract_paragraphs = extracted_data.get("abstract_paragraphs") or [{
            "id": "abstract-para-0",
            "text": abstract,
            "coordinates": {},
            "sentences": [],
        }]
        sections.append({
            "id": "abstract",
            "title": "Abstract",
            "type": "abstract",
            "content": abstract,
            "coordinates": {},
            "paragraphs": abstract_paragraphs,
            "paragraph_count": len(abstract_paragraphs) or 1,
            "start_position": 0,
            "word_count": len(abstract.split()),
            "has_subsections": False,
        })

    for idx, section in enumerate(raw_sections):
        content = normalize_anchor_text(str(section.get("content") or ""))
        paragraphs = section.get("paragraphs") or []
        if not content and paragraphs:
            content = "\n\n".join(
                normalize_anchor_text(str(paragraph.get("text") or ""))
                for paragraph in paragraphs
                if paragraph.get("text")
            )
        if not content:
            continue
        title = section.get("title") or "Untitled Section"
        section_type = _section_type(title, section.get("type"))
        sections.append({
            "id": section.get("id") or f"section-{idx}",
            "title": title,
            "type": section_type,
            "content": content,
            "coordinates": section.get("coordinates") or {},
            "paragraphs": paragraphs,
            "paragraph_count": len(paragraphs) or len(re.split(r"\n\s*\n", content)),
            "start_position": 0,
            "word_count": len(content.split()),
            "has_subsections": False,
        })

    section_types = {section.get("type") for section in sections}
    full_text = normalize_anchor_text(str(extracted_data.get("full_text") or ""))
    metadata = dict(extracted_data.get("metadata") or {})
    is_docling = (metadata.get("parser") or "").lower() == "docling"
    return {
        "sections": sections,
        "word_count": len(full_text.split()),
        "page_count": metadata.get("page_count", 0),
        "has_abstract": "abstract" in section_types,
        "has_introduction": "introduction" in section_types,
        "has_methods": "methods" in section_types,
        "has_results": "results" in section_types,
        "has_discussion": "discussion" in section_types,
        "has_conclusion": "conclusion" in section_types,
        "document_metadata": {
            "has_abstract": "abstract" in section_types,
            "has_introduction": "introduction" in section_types,
            "has_conclusion": "conclusion" in section_types,
            "appears_complete": len(sections) >= 3,
            "primary_structure": "docling" if is_docling else "standard",
            "grobid_extracted": not is_docling,
            "docling_extracted": is_docling,
        },
    }


def build_local_fallback_structure(full_text: str) -> dict[str, Any]:
    """Build a conservative section/paragraph map from extracted text.

    This is used only when a parser returns usable text but weak structural
    metadata. It favors stable anchors over sophisticated section inference.
    """
    normalized = normalize_anchor_text(full_text)
    raw_lines = [line.strip() for line in (full_text or "").splitlines()]
    heading_pattern = re.compile(
        r"^(\d+(\.\d+)*\.?\s+)?(abstract|introduction|background|methods?|materials and methods|results?|discussion|conclusion|limitations?|references|works cited|significance|implications)\b",
        flags=re.IGNORECASE,
    )
    sections: list[dict[str, Any]] = []
    current_title = "Manuscript"
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_lines, current_title
        content = normalize_anchor_text("\n".join(current_lines))
        if not content:
            current_lines = []
            return
        paragraphs = [
            {
                "id": f"fallback-section-{len(sections)}-para-{idx}",
                "text": normalize_anchor_text(paragraph),
                "coordinates": {},
                "sentences": [],
            }
            for idx, paragraph in enumerate(re.split(r"\n\s*\n|(?<=[.!?])\s{2,}", "\n".join(current_lines)))
            if normalize_anchor_text(paragraph)
        ]
        sections.append({
            "id": f"fallback-section-{len(sections)}",
            "title": current_title,
            "type": _section_type(current_title),
            "content": content,
            "coordinates": {},
            "paragraphs": paragraphs or [{
                "id": f"fallback-section-{len(sections)}-para-0",
                "text": content,
                "coordinates": {},
                "sentences": [],
            }],
            "paragraph_count": len(paragraphs) or 1,
            "start_position": 0,
            "word_count": len(content.split()),
            "has_subsections": False,
        })
        current_lines = []

    for line in raw_lines:
        if not line:
            current_lines.append("")
            continue
        is_heading = bool(heading_pattern.match(line)) and len(line.split()) <= 8
        if is_heading and current_lines:
            flush()
            current_title = line.rstrip(":")
            continue
        if is_heading and not current_lines:
            current_title = line.rstrip(":")
            continue
        current_lines.append(line)
    flush()

    if not sections and normalized:
        chunk_words = normalized.split()
        for idx in range(0, len(chunk_words), 450):
            content = " ".join(chunk_words[idx: idx + 450])
            sections.append({
                "id": f"fallback-section-{len(sections)}",
                "title": "Manuscript",
                "type": "other",
                "content": content,
                "coordinates": {},
                "paragraphs": [{
                    "id": f"fallback-section-{len(sections)}-para-0",
                    "text": content,
                    "coordinates": {},
                    "sentences": [],
                }],
                "paragraph_count": 1,
                "start_position": idx,
                "word_count": len(content.split()),
                "has_subsections": False,
            })

    section_types = {section.get("type") for section in sections}
    return {
        "sections": sections,
        "word_count": len(normalized.split()),
        "page_count": 0,
        "has_abstract": "abstract" in section_types,
        "has_introduction": "introduction" in section_types,
        "has_methods": "methods" in section_types,
        "has_results": "results" in section_types,
        "has_discussion": "discussion" in section_types,
        "has_conclusion": "conclusion" in section_types,
        "document_metadata": {
            "has_abstract": "abstract" in section_types,
            "has_introduction": "introduction" in section_types,
            "has_conclusion": "conclusion" in section_types,
            "appears_complete": len(sections) >= 3,
            "primary_structure": "fallback_text",
            "grobid_extracted": False,
            "local_text_fallback": True,
        },
    }


def build_anchor_map(structure: Mapping[str, Any]) -> list[dict[str, Any]]:
    anchors: list[dict[str, Any]] = []
    for section_index, section in enumerate(structure.get("sections") or []):
        paragraphs = section.get("paragraphs") or []
        if not paragraphs and section.get("content"):
            paragraphs = [
                {"id": f"{section.get('id') or section_index}-para-{idx}", "text": text}
                for idx, text in enumerate(re.split(r"\n\s*\n", str(section.get("content"))))
                if normalize_anchor_text(text)
            ]
        for paragraph_index, paragraph in enumerate(paragraphs):
            text = normalize_anchor_text(str(paragraph.get("text") or ""))
            if not text:
                continue
            coords = paragraph.get("coordinates") or {}
            if not coords:
                for sentence in paragraph.get("sentences") or []:
                    coords = sentence.get("coords") or sentence.get("coordinates") or {}
                    if coords:
                        break
            anchors.append({
                "section_id": section.get("id") or f"section-{section_index}",
                "section_title": section.get("title") or "",
                "section_type": section.get("type") or "other",
                "paragraph_index": paragraph_index + 1,
                "page_number": coords.get("page"),
                "coordinates": coords,
                "text_snippet": _snippet(text),
                "text_hash": _hash_text(text),
                "word_count": len(text.split()),
            })
    return anchors


def assess_parse_quality(
    *,
    full_text: str,
    structure: Mapping[str, Any],
    anchor_map: list[dict[str, Any]],
    file_type: str,
) -> dict[str, Any]:
    flags: list[str] = []
    score = 1.0
    sections = structure.get("sections") or []
    normalized = normalize_anchor_text(full_text)

    metadata = structure.get("document_metadata", {}) or {}
    if (
        file_type == "pdf"
        and not metadata.get("grobid_extracted")
        and not metadata.get("docling_extracted")
        and not metadata.get("local_text_fallback")
    ):
        flags.append("not_grobid_pdf_parse")
        score -= 0.35
    if len(normalized) < 1000:
        flags.append("very_short_extracted_text")
        score -= 0.35
    if len(sections) < 3:
        flags.append("low_section_count")
        score -= 0.25
    if file_type == "pdf" and not anchor_map:
        flags.append("missing_anchor_map")
        score -= 0.30
    if "abstract" in normalized[:2500].lower() and not structure.get("has_abstract"):
        flags.append("abstract_text_detected_but_not_structured")
        score -= 0.20
    # Domain-agnostic spacing-artifact heuristic: an alphanumeric token followed by
    # a space and a lone "+" (e.g. "CD34 +" that should read "CD34+"). This is a
    # general PDF-extraction artifact, not specific to any field's nomenclature.
    if any(
        re.search(r"\b[A-Za-z][A-Za-z0-9]{1,}\s+\+(?:\s|$|[^+])", anchor.get("text_snippet", ""))
        for anchor in anchor_map
    ):
        flags.append("possible_pdf_spacing_artifacts")
        score -= 0.05

    # Repeated section headings are a general signal of a malformed parse
    # (e.g. nested-div duplication) rather than a real document structure.
    titles = [
        normalize_anchor_text(str(section.get("title") or "")).lower()
        for section in sections
        if normalize_anchor_text(str(section.get("title") or "")).lower()
        not in {"", "untitled section", "manuscript"}
    ]
    if titles:
        duplicate_titles = len(titles) - len(set(titles))
        if duplicate_titles >= 2 and duplicate_titles >= len(titles) * 0.25:
            flags.append("duplicate_section_headings")
            score -= 0.15

    score = max(0.0, round(score, 3))
    blocking_flags = {
        "not_grobid_pdf_parse",
        "very_short_extracted_text",
        "missing_anchor_map",
    }
    return {
        "parser_name": "docling" if metadata.get("docling_extracted") else "grobid" if metadata.get("grobid_extracted") else "local_text_fallback" if metadata.get("local_text_fallback") else "fallback",
        "parser_quality_score": score,
        "parser_quality_flags": flags,
        "parse_blocked": bool(blocking_flags & set(flags)) or score < 0.55,
        "parse_blocked_reason": ", ".join(flags) if (blocking_flags & set(flags)) or score < 0.55 else "",
    }


def persist_parse_artifact(
    *,
    draft_id: str,
    parser_name: str,
    parser_metadata: Mapping[str, Any],
    anchor_map: list[dict[str, Any]],
    structure: Mapping[str, Any],
    quality: Mapping[str, Any],
) -> str | None:
    payload = {
        "draft_id": draft_id,
        "parser_name": parser_name,
        "parser_version": str(parser_metadata.get("grobid_version") or parser_metadata.get("version") or ""),
        "parser_metadata": dict(parser_metadata or {}),
        "parser_quality_score": quality.get("parser_quality_score"),
        "parser_quality_flags": quality.get("parser_quality_flags") or [],
        "section_map": [
            {
                "id": section.get("id"),
                "title": section.get("title"),
                "type": section.get("type"),
                "word_count": section.get("word_count"),
                "coordinates": section.get("coordinates") or {},
            }
            for section in structure.get("sections") or []
        ],
        "anchor_map": anchor_map,
    }
    try:
        supabase.table("draft_parse_artifacts").delete().eq("draft_id", draft_id).execute()
        res = supabase.table("draft_parse_artifacts").insert(payload).execute()
        if res.data:
            return res.data[0].get("id")
    except Exception as exc:
        logger.warning("[ParseArtifacts] Persist skipped/failed: %s", safe_exception(exc))
    return None


def parse_artifact_metrics(artifact: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return stable counts regardless of public/export field naming."""
    artifact = artifact or {}
    parser_metadata = artifact.get("parser_metadata") or {}
    section_map = artifact.get("section_map") or artifact.get("sections") or []
    anchor_map = artifact.get("anchor_map") or []
    references = (
        parser_metadata.get("references")
        or parser_metadata.get("reference_map")
        or []
    )
    reference_count = (
        parser_metadata.get("grobid_references_count")
        or parser_metadata.get("reference_count")
        or (len(references) if isinstance(references, list) else 0)
    )
    return {
        "parser_name": artifact.get("parser_name"),
        "parser_quality_score": artifact.get("parser_quality_score"),
        "parser_quality_flags": artifact.get("parser_quality_flags") or [],
        "section_count": len(section_map) if isinstance(section_map, list) else 0,
        "anchor_count": len(anchor_map) if isinstance(anchor_map, list) else 0,
        "reference_count": int(reference_count or 0),
    }


def load_parse_artifact(draft_id: str) -> dict[str, Any] | None:
    try:
        res = (
            supabase.table("draft_parse_artifacts")
            .select("*")
            .eq("draft_id", draft_id)
            .limit(1)
            .execute()
        )
        if res.data:
            return res.data[0]
    except Exception as exc:
        logger.debug("[ParseArtifacts] Load failed: %s", safe_exception(exc))
    return None

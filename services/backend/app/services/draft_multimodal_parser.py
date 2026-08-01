"""Multimodal PDF fallback extraction for parser-risky drafts.

GROBID remains the primary parser. This module only extracts a compact set of
layout-sensitive evidence when the text parser is likely to miss tables,
protocol identifiers, or two-column content needed by downstream reviewers.
"""

from __future__ import annotations

import base64
import json
import re
from io import BytesIO
from typing import Any

import fitz

from app.core.logging_config import get_logger
from app.core.openai_client import get_completion_params, get_openai_client
from app.core.privacy import safe_exception

logger = get_logger(__name__)


MULTIMODAL_EVIDENCE_PROMPT = """You are a layout-aware scientific PDF parser.

Extract only evidence that text parsers often miss. Return JSON only:
{
  "evidence_sections": [
    {
      "title": "Protocol registration / Table 1 / Search strategy / Methods / References",
      "text": "verbatim or near-verbatim extracted text",
      "page_number": 1
    }
  ],
  "detected_tables": [
    {"caption": "Table caption", "text": "table contents", "page_number": 1}
  ],
  "parser_notes": ["short note"]
}

Prioritize: PROSPERO/registration identifiers, PRISMA text, database names,
Boolean search strings, inclusion/exclusion criteria, narrative synthesis or
meta-analysis justification, references/citations, tables, and figure captions.
Do not summarize or critique the manuscript."""


def should_run_multimodal_fallback(
    *,
    file_type: str,
    full_text: str,
    extracted_data: dict[str, Any],
    parse_quality: dict[str, Any],
) -> bool:
    if file_type.lower() != "pdf":
        return False

    flags = set(parse_quality.get("parser_quality_flags") or [])
    score = float(parse_quality.get("parser_quality_score") or 0.0)
    sections = extracted_data.get("sections") or []
    references = extracted_data.get("references") or []
    lower = (full_text or "").lower()

    systematic_signals = sum(
        1
        for term in (
            "systematic review",
            "prisma",
            "prospero",
            "search strategy",
            "risk of bias",
            "meta-analysis",
            "included studies",
            "eligibility criteria",
        )
        if term in lower
    )
    table_risk = bool(re.search(r"\btable\s+1\b|\bboolean\b|\b(search string|search terms?)\b", lower))

    # If GROBID already produced a high-quality, well-structured parse, do NOT run
    # the multimodal fallback even when tables/systematic signals are present.
    # The fallback exists to RECOVER content a weak parse missed; running it on a
    # good parse only risks appending duplicate section headings (which downstream
    # reviewers then wrongly flag as author formatting errors). Table text is
    # already present in full_text via GROBID, so the evidence manifest still sees
    # search strings etc. without the fallback.
    deficiency_flags = flags & {
        "low_section_count",
        "abstract_text_detected_but_not_structured",
        "very_short_extracted_text",
        "not_grobid_pdf_parse",
        "missing_anchor_map",
    }
    if score >= 0.85 and len(sections) >= 6 and not deficiency_flags:
        return False

    return (
        score < 0.78
        or "low_section_count" in flags
        or "abstract_text_detected_but_not_structured" in flags
        or (systematic_signals >= 2 and (len(sections) < 4 or len(references) < 5 or table_risk))
    )


def _page_images(file_bytes: bytes, *, max_pages: int = 12) -> list[dict[str, Any]]:
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    pages: list[dict[str, Any]] = []
    try:
        for idx, page in enumerate(doc[:max_pages]):
            # 1.7x is enough for table text while keeping payload size bounded.
            pix = page.get_pixmap(matrix=fitz.Matrix(1.7, 1.7), alpha=False)
            png = pix.tobytes("png")
            pages.append({
                "page_number": idx + 1,
                "data_url": "data:image/png;base64," + base64.b64encode(png).decode("ascii"),
            })
    finally:
        doc.close()
    return pages


def _parse_json_response(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE | re.DOTALL).strip()
    try:
        parsed = json.loads(text)
    except Exception:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        parsed = json.loads(match.group(0)) if match else {}
    if not isinstance(parsed, dict):
        return {}
    return parsed


async def extract_multimodal_pdf_evidence(file_bytes: bytes) -> dict[str, Any]:
    pages = _page_images(file_bytes)
    if not pages:
        return {"evidence_sections": [], "detected_tables": [], "parser_notes": ["no pages rendered"]}

    content: list[dict[str, Any]] = [{"type": "text", "text": MULTIMODAL_EVIDENCE_PROMPT}]
    for page in pages:
        content.append({"type": "text", "text": f"Page {page['page_number']}"})
        content.append({"type": "image_url", "image_url": {"url": page["data_url"]}})

    try:
        client = get_openai_client()
        response = client.chat.completions.create(
            model="gpt-5.2-chat-latest",
            messages=[{"role": "user", "content": content}],
            max_completion_tokens=2500,
            **get_completion_params(),
        )
        parsed = _parse_json_response(response.choices[0].message.content or "")
    except Exception as exc:
        logger.warning("[MultimodalParser] Fallback extraction failed: %s", safe_exception(exc))
        return {
            "evidence_sections": [],
            "detected_tables": [],
            "parser_notes": [f"multimodal fallback failed: {safe_exception(exc)}"],
            "fallback_error": safe_exception(exc),
        }

    evidence_sections = [
        item for item in parsed.get("evidence_sections") or []
        if isinstance(item, dict) and str(item.get("text") or "").strip()
    ]
    detected_tables = [
        item for item in parsed.get("detected_tables") or []
        if isinstance(item, dict) and str(item.get("text") or "").strip()
    ]
    return {
        "evidence_sections": evidence_sections[:12],
        "detected_tables": detected_tables[:8],
        "parser_notes": parsed.get("parser_notes") or [],
    }


def merge_multimodal_evidence(
    extracted_data: dict[str, Any],
    multimodal: dict[str, Any],
) -> dict[str, Any]:
    """Append compact multimodal evidence to structured text/sections."""
    evidence_sections = multimodal.get("evidence_sections") or []
    detected_tables = multimodal.get("detected_tables") or []
    if not evidence_sections and not detected_tables:
        return extracted_data

    merged = dict(extracted_data)
    sections = list(merged.get("sections") or [])
    text_blocks: list[str] = []

    # Dedup multimodal sections against GROBID's existing sections so we never
    # append a second "Search strategy"/"Eligibility criteria"/"Results" that the
    # text parser already produced — that duplication was being mis-flagged as an
    # author formatting error.
    def _norm_title(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()

    existing_titles = {_norm_title(s.get("title")) for s in sections if s.get("title")}
    appended_sections = 0

    for idx, item in enumerate(evidence_sections):
        text = re.sub(r"\s+", " ", str(item.get("text") or "")).strip()
        if not text:
            continue
        title = str(item.get("title") or "Multimodal Evidence").strip()
        norm = _norm_title(title)
        if norm and norm in existing_titles:
            # GROBID already has this section; skip to avoid a duplicate heading.
            continue
        existing_titles.add(norm)
        appended_sections += 1
        page = item.get("page_number")
        sections.append({
            "id": f"multimodal-evidence-{idx}",
            "title": title,
            "type": "methods" if re.search(r"search|protocol|prospero|prisma|eligibility|database", title, re.I) else "other",
            "content": text,
            "coordinates": {"page": page} if page else {},
            "paragraphs": [{
                "id": f"multimodal-evidence-{idx}-para-0",
                "text": text,
                "coordinates": {"page": page} if page else {},
                "sentences": [],
            }],
            "paragraph_count": 1,
        })
        text_blocks.append(f"{title}: {text}")

    appended_tables = 0
    for idx, item in enumerate(detected_tables):
        text = re.sub(r"\s+", " ", str(item.get("text") or "")).strip()
        if not text:
            continue
        caption = str(item.get("caption") or f"Table {idx + 1}").strip()
        norm = _norm_title(caption)
        if norm and norm in existing_titles:
            continue
        existing_titles.add(norm)
        appended_tables += 1
        page = item.get("page_number")
        sections.append({
            "id": f"multimodal-table-{idx}",
            "title": caption,
            "type": "methods",
            "content": text,
            "coordinates": {"page": page} if page else {},
            "paragraphs": [{
                "id": f"multimodal-table-{idx}-para-0",
                "text": text,
                "coordinates": {"page": page} if page else {},
                "sentences": [],
            }],
            "paragraph_count": 1,
        })
        text_blocks.append(f"{caption}: {text}")

    merged["sections"] = sections
    if text_blocks:
        appendix = "\n\n[Layout-aware multimodal parser evidence]\n" + "\n\n".join(text_blocks)
        merged["full_text"] = (merged.get("full_text") or "") + appendix
    metadata = dict(merged.get("metadata") or {})
    metadata.update({
        "multimodal_fallback_used": True,
        "multimodal_evidence_sections": appended_sections,
        "multimodal_detected_tables": appended_tables,
        "multimodal_sections_deduped": (len(evidence_sections) - appended_sections)
        + (len(detected_tables) - appended_tables),
        "multimodal_parser_notes": multimodal.get("parser_notes") or [],
    })
    merged["metadata"] = metadata
    return merged

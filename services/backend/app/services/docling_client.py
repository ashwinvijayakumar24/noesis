"""Docling parser client (sidecar) for PDF body + coordinate extraction.

Docling returns a layout-faithful document where EVERY text block carries a page
number and bounding box — unlike GROBID, whose coordinates are near-empty on real
PDFs (the cause of `page None` / failed anchoring). This module:

  - POSTs a PDF to a docling-serve sidecar and
  - maps the returned DoclingDocument JSON into the same ``extracted_data`` shape
    that ``draft_parse_artifacts.build_structure_from_extracted_data`` already
    consumes (sections → paragraphs with per-block ``coordinates``).

The mapper is a pure function (``map_docling_to_extracted_data``) so it is unit
tested without the sidecar. References are left to GROBID (its strength); Docling
supplies body + structure + coordinates.
"""

from __future__ import annotations

import re
from typing import Any

import httpx

from app.core.config import settings
from app.core.logging_config import get_logger
from app.core.privacy import safe_exception

logger = get_logger(__name__)

_HEADING_LABELS = {"section_header", "title", "subtitle-level-1"}
_SKIP_LABELS = {"page_header", "page_footer", "footnote"}
_REFS_TITLE_RE = re.compile(r"^\s*(references|bibliography|works cited|literature cited)\b", re.IGNORECASE)


def _coords_from_prov(prov: list[dict] | None) -> dict[str, Any]:
    """Map a Docling prov entry to the {page,x,y,width,height} coords shape."""
    if not prov:
        return {}
    p = prov[0] or {}
    coords: dict[str, Any] = {}
    page = p.get("page_no")
    if page is not None:
        coords["page"] = int(page)
    bb = p.get("bbox") or {}
    l, t, r, b = bb.get("l"), bb.get("t"), bb.get("r"), bb.get("b")
    if None not in (l, t, r, b):
        coords.update({
            "x": float(l),
            "y": float(t),
            "width": abs(float(r) - float(l)),
            "height": abs(float(t) - float(b)),
            "bbox": bb,
            "coord_origin": bb.get("coord_origin"),
        })
    return coords


def map_docling_to_extracted_data(doc: dict[str, Any]) -> dict[str, Any]:
    """Map a DoclingDocument dict (export_to_dict / docling-serve json_content)
    into Noesis's ``extracted_data`` shape."""
    texts = doc.get("texts") or []
    sections: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    full_parts: list[str] = []
    references: list[dict[str, Any]] = []
    abstract_parts: list[str] = []
    in_refs = False
    in_abstract = False
    pages_seen: set[int] = set()

    def _new_section(title: str, prov: list[dict] | None) -> dict[str, Any]:
        return {
            "id": f"docling-section-{len(sections)}",
            "title": title or "Untitled Section",
            "type": "",
            "content": "",
            "coordinates": _coords_from_prov(prov),
            "paragraphs": [],
        }

    for item in texts:
        label = (item.get("label") or "").lower()
        if label in _SKIP_LABELS:
            continue
        text = re.sub(r"\s+", " ", str(item.get("text") or "")).strip()
        if not text:
            continue
        prov = item.get("prov") or []
        if prov and prov[0].get("page_no") is not None:
            pages_seen.add(int(prov[0]["page_no"]))

        if label in _HEADING_LABELS:
            full_parts.append(text)
            in_refs = bool(_REFS_TITLE_RE.match(text))
            in_abstract = bool(re.match(r"^\s*abstract\b", text, re.IGNORECASE))
            current = _new_section(text, prov)
            sections.append(current)
            continue

        if in_refs:
            references.append({"raw": text})
            continue

        full_parts.append(text)
        if in_abstract:
            abstract_parts.append(text)
        if current is None:
            current = _new_section("", None)
            sections.append(current)
        idx = len(current["paragraphs"])
        current["paragraphs"].append({
            "id": f"{current['id']}-para-{idx}",
            "text": text,
            "coordinates": _coords_from_prov(prov),
            "sentences": [],
        })

    for s in sections:
        s["content"] = "\n\n".join(p["text"] for p in s["paragraphs"])
    # Drop empty heading-only sections that never accrued paragraphs AND have no title use.
    sections = [s for s in sections if s["content"] or s["paragraphs"] or s["title"] != "Untitled Section"]

    page_count = (max(pages_seen) if pages_seen else 0)
    return {
        "title": (sections[0]["title"] if sections and sections[0]["title"] != "Untitled Section" else ""),
        "abstract": " ".join(abstract_parts),
        "abstract_paragraphs": [],
        "sections": sections,
        "references": references,
        "full_text": "\n\n".join(full_parts),
        "metadata": {
            "parser": "docling",
            "page_count": page_count,
            "docling_text_items": len(texts),
        },
    }


def _extract_doc_dict(payload: dict[str, Any]) -> dict[str, Any] | None:
    """docling-serve nests the DoclingDocument under varying keys by version."""
    if not isinstance(payload, dict):
        return None
    doc = payload.get("document") or payload
    if isinstance(doc, dict):
        # json_content holds the DoclingDocument in docling-serve responses.
        return doc.get("json_content") or (doc if "texts" in doc else None)
    return None


async def extract_with_docling(file_bytes: bytes, *, filename: str = "draft.pdf") -> dict[str, Any] | None:
    """Call the docling-serve sidecar and return mapped extracted_data, or None on failure."""
    base = (getattr(settings, "DOCLING_URL", None) or "").rstrip("/")
    if not base:
        logger.warning("[Docling] DOCLING_URL not configured")
        return None
    try:
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(
                f"{base}/v1/convert/file",
                files={"files": (filename, file_bytes, "application/pdf")},
                data={"to_formats": "json", "image_export_mode": "placeholder"},
            )
        if resp.status_code != 200:
            logger.warning("[Docling] convert returned HTTP %s", resp.status_code)
            return None
        doc = _extract_doc_dict(resp.json())
        if not doc or not doc.get("texts"):
            logger.warning("[Docling] response had no document/texts")
            return None
        extracted = map_docling_to_extracted_data(doc)
        logger.info(
            "[Docling] extracted sections=%s paragraphs=%s pages=%s",
            len(extracted["sections"]),
            sum(len(s["paragraphs"]) for s in extracted["sections"]),
            extracted["metadata"]["page_count"],
        )
        return extracted
    except Exception as exc:
        logger.warning("[Docling] extraction failed: %s", safe_exception(exc))
        return None

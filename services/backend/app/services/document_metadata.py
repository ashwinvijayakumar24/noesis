"""
Document metadata normalization and enrichment for literature cards.

This module keeps display metadata separate from the heavier paper-analysis
pipeline. Metadata updates are best-effort and must never block draft analysis.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any, Dict, Iterable, Optional

from app.core.logging_config import get_logger
from app.core.supabase_client import supabase

logger = get_logger(__name__)


DOI_PREFIX_RE = re.compile(r"^https?://(?:dx\.)?doi\.org/", re.IGNORECASE)
FILENAME_EXT_RE = re.compile(r"\.(pdf|docx?|txt)$", re.IGNORECASE)
PDF_ID_RE = re.compile(r"^[a-z]?\d{3,}[-_.]\d{2,}[-_.]\d{2,}", re.IGNORECASE)


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def normalize_doi(value: Any) -> str:
    doi = _clean_text(value)
    if not doi:
        return ""
    return DOI_PREFIX_RE.sub("", doi).strip().rstrip(".")


def _year_from_value(value: Any) -> str:
    text = _clean_text(value)
    match = re.search(r"\b(19|20)\d{2}\b", text)
    return match.group(0) if match else ""


def _author_to_name(author: Any) -> str:
    if isinstance(author, str):
        return _clean_text(author)
    if not isinstance(author, dict):
        return ""

    if author.get("name"):
        return _clean_text(author.get("name"))
    if author.get("display_name"):
        return _clean_text(author.get("display_name"))

    parts = [
        author.get("first_name"),
        author.get("middle_name"),
        author.get("last_name"),
    ]
    return _clean_text(" ".join(str(part) for part in parts if part))


def normalize_authors(authors: Any, *, limit: int = 20) -> list[str]:
    if not isinstance(authors, Iterable) or isinstance(authors, (str, bytes, dict)):
        return []

    names: list[str] = []
    seen: set[str] = set()
    for author in authors:
        name = _author_to_name(author)
        if not name:
            continue
        key = name.casefold()
        if key in seen:
            continue
        names.append(name)
        seen.add(key)
        if len(names) >= limit:
            break
    return names


def is_filename_like_title(title: str, original_filename: Optional[str] = None) -> bool:
    normalized = _clean_text(title)
    if not normalized:
        return True

    without_ext = FILENAME_EXT_RE.sub("", normalized).strip()
    if original_filename:
        original_without_ext = FILENAME_EXT_RE.sub("", _clean_text(original_filename)).strip()
        if without_ext.casefold() == original_without_ext.casefold():
            return True

    if normalized != without_ext:
        return True
    if PDF_ID_RE.match(without_ext):
        return True
    if "_" in without_ext and " " not in without_ext:
        return True
    return False


def normalize_grobid_metadata(structured_data: Dict[str, Any]) -> Dict[str, Any]:
    metadata = structured_data.get("metadata") or {}
    title = _clean_text(structured_data.get("title") or metadata.get("title"))
    abstract = _clean_text(structured_data.get("abstract"))
    doi = normalize_doi(metadata.get("doi"))
    journal = _clean_text(metadata.get("journal") or metadata.get("venue"))
    year = _year_from_value(metadata.get("publication_date") or metadata.get("year"))
    authors = normalize_authors(structured_data.get("authors") or metadata.get("authors"))

    normalized = {
        "extracted_title": title,
        "title": title,
        "authors": authors,
        "year": year,
        "journal": journal,
        "doi": doi,
        "abstract": abstract,
        "metadata_status": "extracted",
        "metadata_source": "grobid",
        "metadata_confidence": 0.82 if title else 0.45,
    }
    return {k: v for k, v in normalized.items() if v not in ("", [], None)}


def normalize_external_paper(paper: Dict[str, Any], source: str) -> Dict[str, Any]:
    journal = paper.get("journal") or paper.get("journal_name") or paper.get("venue")
    url = paper.get("paper_url") or paper.get("url") or paper.get("open_access_url")
    normalized = {
        "extracted_title": _clean_text(paper.get("title")),
        "title": _clean_text(paper.get("title")),
        "authors": normalize_authors(paper.get("authors")),
        "year": _year_from_value(paper.get("year") or paper.get("publication_year")),
        "journal": _clean_text(journal),
        "doi": normalize_doi(paper.get("doi")),
        "url": _clean_text(url),
        "abstract": _clean_text(paper.get("abstract")),
        "metadata_status": "enriched",
        "metadata_source": source,
        "metadata_confidence": 0.9 if paper.get("doi") else 0.72,
    }
    return {k: v for k, v in normalized.items() if v not in ("", [], None)}


def merge_metadata(existing: Dict[str, Any] | None, candidate: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(existing or {})
    for key, value in candidate.items():
        if value in ("", [], None):
            continue
        if key in {"metadata_status", "metadata_source", "metadata_confidence"}:
            merged[key] = value
            continue
        if not merged.get(key):
            merged[key] = value
    return merged


def _title_tokens(title: str) -> set[str]:
    stop = {"the", "and", "for", "with", "from", "into", "using", "study", "paper"}
    return {
        token
        for token in re.findall(r"[a-z0-9]+", title.lower())
        if len(token) > 2 and token not in stop
    }


def title_similarity(title_a: str, title_b: str) -> float:
    a = _title_tokens(title_a)
    b = _title_tokens(title_b)
    if not a or not b:
        return 0.0
    return len(a & b) / max(len(a), len(b))


async def enrich_metadata_from_external(metadata: Dict[str, Any]) -> Dict[str, Any]:
    doi = normalize_doi(metadata.get("doi"))
    title = _clean_text(metadata.get("extracted_title") or metadata.get("title"))

    if doi:
        try:
            from app.services.external_apis.openalex import get_work_by_doi

            paper = await get_work_by_doi(doi)
            if paper:
                return normalize_external_paper(paper, "openalex")
        except Exception as exc:
            logger.warning("[DocMetadata] OpenAlex DOI enrichment failed: %s", exc)

    if title:
        try:
            from app.services.external_apis.openalex import search_works

            papers = await search_works(title, per_page=3)
            for paper in papers:
                if title_similarity(title, paper.get("title", "")) >= 0.72:
                    return normalize_external_paper(paper, "openalex")
        except Exception as exc:
            logger.warning("[DocMetadata] OpenAlex title enrichment failed: %s", exc)

        try:
            from app.services.external_apis.semantic_scholar import SemanticScholarAPI

            api = SemanticScholarAPI()
            papers = await asyncio.to_thread(api.search_papers, title, 3)
            for paper in papers:
                if title_similarity(title, paper.get("title", "")) >= 0.72:
                    return normalize_external_paper(paper, "semantic_scholar")
        except Exception as exc:
            logger.warning("[DocMetadata] Semantic Scholar enrichment failed: %s", exc)

    return {}


def build_document_update(
    current_title: str,
    existing_metadata: Dict[str, Any] | None,
    candidate_metadata: Dict[str, Any],
) -> Dict[str, Any]:
    existing = dict(existing_metadata or {})
    merged = merge_metadata(existing, candidate_metadata)

    update: Dict[str, Any] = {"metadata": merged}
    extracted_title = _clean_text(merged.get("extracted_title") or merged.get("title"))
    original_filename = existing.get("original_filename")
    if extracted_title and is_filename_like_title(current_title, original_filename):
        update["title"] = extracted_title

    return update


async def enrich_and_persist_document_metadata(
    document_id: str,
    *,
    current_title: str,
    existing_metadata: Dict[str, Any] | None,
    structured_data: Dict[str, Any],
) -> Dict[str, Any]:
    local_metadata = normalize_grobid_metadata(structured_data)
    if not local_metadata:
        local_metadata = {
            "metadata_status": "failed",
            "metadata_source": "grobid",
            "metadata_confidence": 0,
        }

    merged = merge_metadata(existing_metadata, local_metadata)
    external_metadata = await enrich_metadata_from_external(merged)
    if external_metadata:
        merged = merge_metadata(merged, external_metadata)

    update = build_document_update(current_title, existing_metadata, merged)
    try:
        supabase.table("documents").update(update).eq("id", document_id).execute()
    except Exception as exc:
        logger.warning("[DocMetadata] Failed to persist metadata for %s: %s", document_id, exc)
    return update

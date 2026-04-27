"""
BibTeX Resolution Service

For each newly imported BibTeX document, this service attempts to find its
open-access PDF, then runs the full analysis pipeline (GROBID → GPT-5.2 → embed).

Resolution algorithm per entry:
  1. Check shared_papers cache by DOI / title similarity
  2. If cache hit → reuse analysis, still run RAG ingest → 'resolved'
  3. If cache miss → search arXiv / Semantic Scholar for OA PDF
  4. If OA PDF found → download → GROBID → analyze → embed → cache → 'resolved'
  5. If no OA PDF → embed title+abstract only → 'unresolved'

This runs as a Celery background task (non-blocking).
"""

import asyncio
import os
import io
import logging
from typing import List, Optional, Dict, Any

from app.core.supabase_client import supabase
from app.core.logging_config import get_logger

logger = get_logger(__name__)

# Title similarity threshold to accept a cache/search result as a match
TITLE_SIMILARITY_THRESHOLD = 0.85


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point (called by Celery task)
# ─────────────────────────────────────────────────────────────────────────────

def resolve_bibtex_entries_sync(
    document_ids: List[str],
    user_id: str,
    project_id: str,
) -> Dict[str, Any]:
    """
    Synchronous wrapper for Celery — runs the async pipeline in a new event loop.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(
            resolve_bibtex_entries(document_ids, user_id, project_id)
        )
    finally:
        loop.close()


async def resolve_bibtex_entries(
    document_ids: List[str],
    user_id: str,
    project_id: str,
) -> Dict[str, Any]:
    """
    Attempt open-access PDF resolution for a list of bibtex_import document IDs.

    Processes entries sequentially to avoid hammering external APIs.
    Updates each document's resolution_status in the DB as it progresses.
    """
    resolved = 0
    unresolved = 0

    for doc_id in document_ids:
        try:
            outcome = await _resolve_single_entry(doc_id, user_id, project_id)
            if outcome == "resolved":
                resolved += 1
            else:
                unresolved += 1
        except Exception as e:
            logger.error(f"[BibResolution] Failed to resolve {doc_id}: {e}", exc_info=True)
            _set_resolution_status(doc_id, "unresolved")
            unresolved += 1

    logger.info(
        f"[BibResolution] Done. resolved={resolved}, unresolved={unresolved}, "
        f"total={len(document_ids)}"
    )
    return {"resolved": resolved, "unresolved": unresolved, "total": len(document_ids)}


# ─────────────────────────────────────────────────────────────────────────────
# Per-entry resolution
# ─────────────────────────────────────────────────────────────────────────────

async def _resolve_single_entry(doc_id: str, user_id: str, project_id: str) -> str:
    """
    Attempt to resolve a single BibTeX document. Returns 'resolved' or 'unresolved'.
    """
    # 1. Fetch document metadata
    doc_res = supabase.table("documents").select("*").eq("id", doc_id).execute()
    if not doc_res.data:
        logger.warning(f"[BibResolution] Document {doc_id} not found")
        return "unresolved"

    doc = doc_res.data[0]
    meta = doc.get("metadata") or {}
    title = doc.get("title") or meta.get("title") or ""
    doi = meta.get("doi") or ""
    authors = meta.get("authors") or []
    abstract = meta.get("abstract") or ""

    logger.info(f"[BibResolution] Resolving: '{title[:60]}'")

    # Mark as resolving — also flip status to "analyzing" so the UI shows pulsing badge
    try:
        supabase.table("documents").update({
            "status": "analyzing",
            "resolution_status": "resolving",
            "updated_at": _now(),
        }).eq("id", doc_id).execute()
    except Exception as e:
        logger.warning(f"[BibResolution] Failed to set initial analyzing state: {e}")

    # 2. Check shared_papers cache by DOI
    if doi:
        cached = await _check_cache_by_doi(doi)
        if cached:
            logger.info(f"[BibResolution] Cache HIT by DOI: {doi}")
            await _apply_cached_paper(doc_id, project_id, cached, title, abstract)
            return "resolved"

    # 3. Check shared_papers cache by title similarity
    if title:
        cached = await _check_cache_by_title(title)
        if cached:
            logger.info(f"[BibResolution] Cache HIT by title: '{title[:60]}'")
            await _apply_cached_paper(doc_id, project_id, cached, title, abstract)
            return "resolved"

    # 4. Try known PDF URL from metadata first (e.g. arXiv papers always have one)
    known_pdf_url = meta.get("pdf_url") or ""
    if known_pdf_url:
        logger.info(f"[BibResolution] Trying known pdf_url: {known_pdf_url}")
        success = await _download_and_analyze(doc_id, user_id, project_id, known_pdf_url, title, doi)
        if success:
            return "resolved"
        logger.info(f"[BibResolution] Known pdf_url failed, falling back to external search")

    # 5. Search external sources for OA PDF
    pdf_url = await _find_oa_pdf(title, doi, authors)

    if pdf_url:
        logger.info(f"[BibResolution] Found OA PDF for '{title[:60]}': {pdf_url}")
        success = await _download_and_analyze(doc_id, user_id, project_id, pdf_url, title, doi)
        if success:
            return "resolved"

    # 6. No OA PDF — embed title+abstract only
    logger.info(f"[BibResolution] No OA PDF for '{title[:60]}' — metadata only")
    await _embed_metadata_only(doc_id, project_id, title, abstract)
    _set_resolution_status(doc_id, "unresolved")
    return "unresolved"


# ─────────────────────────────────────────────────────────────────────────────
# Cache lookup helpers
# ─────────────────────────────────────────────────────────────────────────────

async def _check_cache_by_doi(doi: str) -> Optional[Dict[str, Any]]:
    """Check shared_papers table for a paper by exact DOI match."""
    try:
        doi_clean = doi.replace("https://doi.org/", "").replace("http://doi.org/", "").strip()
        res = supabase.table("shared_papers").select("*").eq("doi", doi_clean).limit(1).execute()
        if res.data and res.data[0].get("analysis"):
            return res.data[0]
    except Exception as e:
        logger.warning(f"[BibResolution] DOI cache lookup failed: {e}")
    return None


async def _check_cache_by_title(title: str) -> Optional[Dict[str, Any]]:
    """
    Check shared_papers for a title match using cosine similarity.
    Returns the paper if similarity >= TITLE_SIMILARITY_THRESHOLD.
    """
    try:
        from app.services.shared_paper_cache import find_similar_papers
        results = await find_similar_papers(title, limit=1, similarity_threshold=TITLE_SIMILARITY_THRESHOLD)
        if results and results[0].get("analysis"):
            return results[0]
    except Exception as e:
        logger.warning(f"[BibResolution] Title cache lookup failed: {e}")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Cache hit → apply to document
# ─────────────────────────────────────────────────────────────────────────────

async def _apply_cached_paper(
    doc_id: str,
    project_id: str,
    cached: Dict[str, Any],
    title: str,
    abstract: str,
) -> None:
    """
    Use a cached paper's analysis. Tries to copy full-text chunks and structured
    data from the source document; falls back to title+abstract embedding.
    """
    try:
        analysis = cached.get("analysis")

        # Update document with cached analysis
        supabase.table("documents").update({
            "status": "analyzed",
            "analysis": analysis,
            "resolution_status": "resolved",
            "updated_at": _now(),
        }).eq("id", doc_id).execute()

        # Try to find a source document with full-text chunks (by DOI)
        chunks_copied = False
        cached_doi = cached.get("doi")
        if cached_doi:
            source_doc = supabase.table("documents").select("id")\
                .eq("metadata->>doi", cached_doi)\
                .neq("id", doc_id)\
                .limit(1).execute()

            if source_doc.data:
                source_id = source_doc.data[0]["id"]
                # Check if source has full-text chunks (more than just title+abstract)
                chunk_count_res = supabase.table("document_chunks").select("id", count="exact")\
                    .eq("document_id", source_id).execute()
                chunk_count = chunk_count_res.count if chunk_count_res.count is not None else 0

                if chunk_count > 2:
                    # Copy full-text chunks with new document_id and project_id
                    logger.info(
                        f"[BibResolution] Copying {chunk_count} chunks from "
                        f"source doc {source_id}"
                    )
                    source_chunks = supabase.table("document_chunks").select("*")\
                        .eq("document_id", source_id).execute()
                    for chunk in (source_chunks.data or []):
                        new_chunk = {
                            k: v for k, v in chunk.items()
                            if k not in ("id", "created_at")
                        }
                        new_chunk["document_id"] = doc_id
                        new_chunk["project_id"] = project_id
                        supabase.table("document_chunks").insert(new_chunk).execute()
                    chunks_copied = True
                    logger.info(f"[BibResolution] Copied {chunk_count} full-text chunks")

                    # Also copy structured data (claims, methods, findings)
                    try:
                        from app.services.structured_data_storage import copy_structured_data
                        copy_structured_data(source_id, doc_id, project_id)
                    except Exception as e:
                        logger.warning(
                            f"[BibResolution] Failed to copy structured data: {e}"
                        )

        if not chunks_copied:
            # Fallback: embed title+abstract only
            await _embed_metadata_only(
                doc_id, project_id, title, abstract, skip_status_update=True
            )

        logger.info(f"[BibResolution] Applied cached analysis to {doc_id}")
    except Exception as e:
        logger.error(f"[BibResolution] Failed to apply cache to {doc_id}: {e}")
        _set_resolution_status(doc_id, "unresolved")


# ─────────────────────────────────────────────────────────────────────────────
# External OA PDF search
# ─────────────────────────────────────────────────────────────────────────────

async def _find_oa_pdf(
    title: str,
    doi: str,
    authors: List[str],
) -> Optional[str]:
    """
    Search external sources for an open-access PDF URL.
    Priority: Semantic Scholar → arXiv direct (if arXiv paper).
    """
    # Try Semantic Scholar first (covers arXiv, PubMed, etc.)
    ss_url = await _search_semantic_scholar(title, doi)
    if ss_url:
        return ss_url

    # Try Unpaywall for DOI-based OA lookup
    if doi:
        unpaywall_url = await _search_unpaywall(doi)
        if unpaywall_url:
            return unpaywall_url

    return None


async def _search_semantic_scholar(title: str, doi: Optional[str]) -> Optional[str]:
    """Search Semantic Scholar for an OA PDF URL."""
    import aiohttp

    headers = {"User-Agent": "Noesis/1.0 (contact@noesis.is)"}
    fields = "title,openAccessPdf,externalIds"

    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            # Try DOI lookup first
            if doi:
                doi_clean = doi.replace("https://doi.org/", "").replace("http://doi.org/", "").strip()
                url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi_clean}"
                async with session.get(url, params={"fields": fields},
                                       timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        oa = data.get("openAccessPdf") or {}
                        if oa.get("url"):
                            return oa["url"]

            # Title search fallback
            if title:
                url = "https://api.semanticscholar.org/graph/v1/paper/search"
                params = {"query": title[:200], "limit": 3, "fields": fields}
                async with session.get(url, params=params,
                                       timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for paper in data.get("data", []):
                            # Simple title similarity check
                            if _title_similar(title, paper.get("title", "")):
                                oa = paper.get("openAccessPdf") or {}
                                if oa.get("url"):
                                    return oa["url"]
    except Exception as e:
        logger.warning(f"[BibResolution] Semantic Scholar search failed: {e}")

    return None


async def _search_unpaywall(doi: str) -> Optional[str]:
    """Query Unpaywall for a free PDF URL given a DOI."""
    import aiohttp

    doi_clean = doi.replace("https://doi.org/", "").replace("http://doi.org/", "").strip()
    email = os.getenv("UNPAYWALL_EMAIL", "contact@noesis.is")
    url = f"https://api.unpaywall.org/v2/{doi_clean}?email={email}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    best = data.get("best_oa_location") or {}
                    pdf_url = best.get("url_for_pdf")
                    if pdf_url:
                        return pdf_url
    except Exception as e:
        logger.warning(f"[BibResolution] Unpaywall search failed: {e}")

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Download → GROBID → Analyze → Embed → Cache
# ─────────────────────────────────────────────────────────────────────────────

async def _download_and_analyze(
    doc_id: str,
    user_id: str,
    project_id: str,
    pdf_url: str,
    title: str,
    doi: Optional[str],
) -> bool:
    """
    Download OA PDF and run the full analysis pipeline.
    Returns True on success, False on failure.
    """
    import aiohttp

    # 1. Download PDF
    logger.info(f"[BibResolution] Downloading PDF: {pdf_url}")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                pdf_url,
                timeout=aiohttp.ClientTimeout(total=60),
                headers={"User-Agent": "Noesis/1.0 (contact@noesis.is)"},
            ) as resp:
                if resp.status != 200:
                    logger.warning(f"[BibResolution] PDF download returned {resp.status}")
                    return False
                content_type = resp.headers.get("content-type", "")
                if "pdf" not in content_type and not pdf_url.endswith(".pdf"):
                    logger.warning(f"[BibResolution] Unexpected content-type: {content_type}")
                    # Allow it anyway — some servers send wrong content-type
                pdf_bytes = await resp.read()
    except Exception as e:
        logger.warning(f"[BibResolution] PDF download failed: {e}")
        return False

    if len(pdf_bytes) < 5000:
        logger.warning(f"[BibResolution] PDF too small ({len(pdf_bytes)} bytes), skipping")
        return False

    logger.info(f"[BibResolution] Downloaded {len(pdf_bytes)} bytes")

    # 2. Upload to Supabase Storage
    import uuid
    storage_path = f"{user_id}/{doc_id}_resolved.pdf"
    file_url = None  # Initialize before the try block so it is always defined
    try:
        supabase.storage.from_("documents").upload(
            path=storage_path,
            file=pdf_bytes,
            file_options={"content-type": "application/pdf"}
        )
        file_url = supabase.storage.from_("documents").get_public_url(storage_path)
        supabase.table("documents").update({
            "file_url": file_url,
            "file_type": "application/pdf",
            "updated_at": _now(),
        }).eq("id", doc_id).execute()
        logger.info(f"[BibResolution] Stored PDF at {storage_path}")
    except Exception as e:
        logger.warning(f"[BibResolution] Storage upload failed: {e}")
        # Non-fatal — we can still analyze from memory.
        # Explicitly persist file_url=None so the DB column is not left stale.
        try:
            supabase.table("documents").update({
                "file_url": None,
                "updated_at": _now(),
            }).eq("id", doc_id).execute()
        except Exception as db_err:
            logger.warning(f"[BibResolution] Failed to persist file_url=None after storage failure: {db_err}")

    # 3. Extract text (GROBID + fallback)
    paper_text = ""
    try:
        from app.services.grobid_client import GrobidClient
        grobid_result = await GrobidClient().process_pdf(pdf_bytes)
        paper_text = grobid_result.get("full_text") or ""
        logger.info(f"[BibResolution] GROBID extracted {len(paper_text)} chars")
    except Exception as e:
        logger.warning(f"[BibResolution] GROBID extraction failed, using fallback: {e}")

    if len(paper_text) < 200:
        try:
            from app.services.rag_ingest import extract_text_from_pdf_fallback
            paper_text = extract_text_from_pdf_fallback(pdf_bytes)
            logger.info(f"[BibResolution] Fallback extracted {len(paper_text)} chars")
        except Exception as e:
            logger.warning(f"[BibResolution] Text extraction fallback failed: {e}")

    if len(paper_text) < 100:
        logger.warning(f"[BibResolution] Could not extract usable text from PDF")
        return False

    # 4. Run GPT-5.2 analysis
    logger.info(f"[BibResolution] Running GPT-5.2 analysis for {doc_id}")
    try:
        from app.services.document_analysis import analyze_paper_text
        from app.services.rag_ingest import get_pdf_page_count
        page_count = get_pdf_page_count(pdf_bytes)
        analysis = analyze_paper_text(paper_text, page_count=page_count, model="gpt-5.2-chat-latest")
        logger.info(f"[BibResolution] Analysis complete for {doc_id}")
    except Exception as e:
        logger.error(f"[BibResolution] GPT analysis failed: {e}")
        return False

    # 5. Run LangGraph workflow for structured extraction (claims, methods, findings)
    logger.info(f"[BibResolution] Running LangGraph structured extraction for {doc_id}")
    try:
        from app.workflows.document_analysis.graph import run_document_analysis_workflow
        from app.services.structured_data_storage import store_structured_data

        final_state = await run_document_analysis_workflow(
            document_id=doc_id,
            project_id=project_id,
            document_text=paper_text,
            page_count=page_count,
        )
        struct_counts = store_structured_data(doc_id, project_id, final_state)
        logger.info(
            f"[BibResolution] LangGraph done: {struct_counts['claims']} claims, "
            f"{struct_counts['methods']} methods, {struct_counts['findings']} findings"
        )
    except Exception as e:
        logger.warning(f"[BibResolution] LangGraph extraction failed (non-fatal): {e}")

    # 6. Run RAG ingest (user-scoped chunks + embeddings)
    logger.info(f"[BibResolution] Ingesting {doc_id} into RAG")
    try:
        from app.services.rag_ingest import ingest_document
        # file_url may be empty string if storage upload failed — ingest handles it
        current_doc = supabase.table("documents").select("file_url").eq("id", doc_id).execute()
        current_file_url = (current_doc.data[0].get("file_url") if current_doc.data else "") or ""
        ingest_document(doc_id, current_file_url, project_id)
        logger.info(f"[BibResolution] RAG ingest complete for {doc_id}")
    except Exception as e:
        logger.warning(f"[BibResolution] RAG ingest failed (non-fatal): {e}")

    # 6. Update document status
    # Use "resolved_no_pdf" when storage upload failed so the frontend can surface
    # a clear explanation instead of silently returning a 404 on file access.
    final_resolution = "resolved" if file_url else "resolved_no_pdf"
    supabase.table("documents").update({
        "status": "analyzed",
        "analysis": analysis,
        "resolution_status": final_resolution,
        "file_url": file_url,  # explicitly persist (even if None)
        "updated_at": _now(),
    }).eq("id", doc_id).execute()

    # 7. Write to shared_papers cache
    try:
        from app.services.shared_paper_cache import store_paper
        doc_meta = supabase.table("documents").select("*").eq("id", doc_id).execute()
        if doc_meta.data:
            m = doc_meta.data[0].get("metadata") or {}
            await store_paper({
                "doi": doi,
                "title": title,
                "authors": m.get("authors", []),
                "year": m.get("year"),
                "abstract": m.get("abstract"),
                "journal": m.get("journal"),
                "pdf_url": pdf_url,
                "analysis": analysis,
                "source": "bibtex_resolution",
            })
    except Exception as e:
        logger.warning(f"[BibResolution] Failed to write to shared cache: {e}")

    return True


# ─────────────────────────────────────────────────────────────────────────────
# Metadata-only embedding (fallback)
# ─────────────────────────────────────────────────────────────────────────────

async def _embed_metadata_only(
    doc_id: str,
    project_id: str,
    title: str,
    abstract: str,
    skip_status_update: bool = False,
) -> None:
    """Embed title + abstract for RAG search (no full PDF available)."""
    try:
        from app.services.rag_ingest import embed_imported_document
        # Run in thread to avoid blocking event loop
        await asyncio.to_thread(
            embed_imported_document,
            document_id=doc_id,
            project_id=project_id,
            title=title,
            abstract=abstract,
        )
        logger.info(f"[BibResolution] Metadata-only embedding complete for {doc_id}")
    except Exception as e:
        logger.warning(f"[BibResolution] Metadata embedding failed for {doc_id}: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────────────────────────────────────

def _set_resolution_status(doc_id: str, status: str) -> None:
    """Update resolution_status (and reset doc status so it never stays stuck at 'analyzing')."""
    try:
        # When resolution ends without full analysis, reset status to 'imported'
        # so the UI doesn't show the document stuck in an analyzing/processing state.
        doc_status = "imported" if status in ("unresolved", "resolved_no_pdf") else None
        update = {"resolution_status": status, "updated_at": _now()}
        if doc_status:
            update["status"] = doc_status
        supabase.table("documents").update(update).eq("id", doc_id).execute()
    except Exception as e:
        logger.warning(f"[BibResolution] Failed to set resolution_status={status}: {e}")


def _now() -> str:
    from datetime import datetime
    return datetime.utcnow().isoformat()


def _title_similar(title_a: str, title_b: str) -> bool:
    """
    Simple title similarity check using token overlap.
    Returns True if titles share enough significant words.
    """
    if not title_a or not title_b:
        return False

    stopwords = {"a", "an", "the", "of", "in", "on", "and", "or", "for", "to", "with"}

    def tokens(t: str):
        import re
        words = re.sub(r"[^\w\s]", "", t.lower()).split()
        return {w for w in words if w not in stopwords and len(w) > 2}

    ta = tokens(title_a)
    tb = tokens(title_b)

    if not ta or not tb:
        return False

    intersection = ta & tb
    union = ta | tb
    jaccard = len(intersection) / len(union)
    return jaccard >= 0.6  # 60% word overlap

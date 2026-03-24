"""
Shared Paper Cache

Global cache of scholarly papers stored in the shared_papers table.
Papers fetched from external APIs (Semantic Scholar, OpenAlex, arXiv) are
stored once and reused across all users — avoiding redundant API calls and
enabling cross-user discovery.

Usage:
    from app.services.shared_paper_cache import get_or_fetch_paper, find_similar_papers

    # Returns cached paper or fetches fresh from Semantic Scholar
    paper = await get_or_fetch_paper(doi="10.1145/3290605.3300683")

    # Semantic search over all globally cached papers
    results = await find_similar_papers("transformer attention mechanism", limit=10)
"""

import asyncio
from typing import Dict, Any, Optional, List
from app.core.supabase_client import supabase
from app.core.logging_config import get_logger

logger = get_logger(__name__)


# ────────────────────────────────────────────────────────────────────────────
# Internal Helpers
# ────────────────────────────────────────────────────────────────────────────

def _embed_text(text: str) -> Optional[List[float]]:
    """Generate a 1536-dim embedding for a text string."""
    try:
        from app.services.rag_ingest import embed_chunks
        results = embed_chunks([text])
        if results:
            return results[0].embedding
        return None
    except Exception as e:
        logger.warning(f"[SharedPaperCache] Embedding failed: {e}")
        return None


def _normalize_doi(doi: Optional[str]) -> Optional[str]:
    """Strip URL prefix from DOI."""
    if not doi:
        return None
    return doi.replace("https://doi.org/", "").replace("http://doi.org/", "").strip()


# ────────────────────────────────────────────────────────────────────────────
# Core Cache Functions
# ────────────────────────────────────────────────────────────────────────────

async def get_or_fetch_paper(
    doi: Optional[str] = None,
    title: Optional[str] = None,
    arxiv_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Return a paper from the shared cache, or fetch and cache it from external APIs.

    Lookup priority:
    1. Check shared_papers by DOI (exact match)
    2. Check shared_papers by arxiv_id (exact match)
    3. Fetch from Semantic Scholar → OpenAlex fallback
    4. Cache result and return

    Args:
        doi: DOI string (with or without https://doi.org/ prefix)
        title: Paper title (used as last-resort search)
        arxiv_id: arXiv ID (e.g., "2301.07041")

    Returns:
        Paper dict or None if not found anywhere
    """
    doi = _normalize_doi(doi)

    # 1. Check cache by DOI
    if doi:
        try:
            res = supabase.table("shared_papers")\
                .select("*")\
                .eq("doi", doi)\
                .limit(1)\
                .execute()
            if res.data:
                paper = res.data[0]
                # Update access tracking
                supabase.table("shared_papers")\
                    .update({"last_accessed": "now()", "download_count": paper.get("download_count", 0) + 1})\
                    .eq("id", paper["id"])\
                    .execute()
                logger.info(f"[SharedPaperCache] Cache HIT for DOI: {doi}")
                return paper
        except Exception as e:
            logger.warning(f"[SharedPaperCache] DOI lookup failed: {e}")

    # 2. Check cache by arxiv_id
    if arxiv_id:
        try:
            arxiv_clean = arxiv_id.replace("arxiv:", "").strip()
            res = supabase.table("shared_papers")\
                .select("*")\
                .eq("arxiv_id", arxiv_clean)\
                .limit(1)\
                .execute()
            if res.data:
                logger.info(f"[SharedPaperCache] Cache HIT for arXiv: {arxiv_clean}")
                return res.data[0]
        except Exception as e:
            logger.warning(f"[SharedPaperCache] arXiv lookup failed: {e}")

    # 3. Fetch from external APIs
    paper_data = None

    # Try Semantic Scholar first (has full metadata + PDF links)
    if doi or title:
        paper_data = await _fetch_from_semantic_scholar(doi=doi, title=title)

    # Fallback to OpenAlex
    if not paper_data and doi:
        from app.services.external_apis.openalex import get_work_by_doi
        paper_data = await get_work_by_doi(doi)

    if not paper_data:
        logger.warning(f"[SharedPaperCache] Could not find paper: doi={doi}, title={title}")
        return None

    # 4. Store in cache
    cached = await store_paper(paper_data)
    if cached:
        logger.info(f"[SharedPaperCache] Cached new paper: {paper_data.get('title', '')[:60]}")
    return paper_data


async def _fetch_from_semantic_scholar(
    doi: Optional[str] = None,
    title: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Fetch paper metadata from Semantic Scholar API."""
    import aiohttp

    headers = {"User-Agent": "Noesis/1.0 (contact@noesis.is)"}

    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            if doi:
                url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}"
                params = {"fields": "title,authors,year,abstract,externalIds,openAccessPdf,venue,citationCount"}
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return _format_semantic_scholar_paper(data)

            if title:
                url = "https://api.semanticscholar.org/graph/v1/paper/search"
                params = {
                    "query": title[:200],
                    "limit": 1,
                    "fields": "title,authors,year,abstract,externalIds,openAccessPdf,venue,citationCount"
                }
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        papers = data.get("data", [])
                        if papers:
                            return _format_semantic_scholar_paper(papers[0])

    except Exception as e:
        logger.warning(f"[SharedPaperCache] Semantic Scholar fetch failed: {e}")

    return None


def _format_semantic_scholar_paper(data: Dict[str, Any]) -> Dict[str, Any]:
    """Convert Semantic Scholar API response to shared_papers format."""
    authors = [a.get("name", "") for a in data.get("authors", [])[:5]]
    external_ids = data.get("externalIds", {})
    oa_pdf = data.get("openAccessPdf", {})

    return {
        "title": data.get("title", "Untitled"),
        "authors": authors,
        "year": data.get("year"),
        "abstract": data.get("abstract"),
        "journal": data.get("venue", ""),
        "doi": external_ids.get("DOI"),
        "arxiv_id": external_ids.get("ArXiv"),
        "pubmed_id": external_ids.get("PubMed"),
        "semantic_scholar_id": data.get("paperId"),
        "pdf_url": oa_pdf.get("url") if oa_pdf else None,
        "source": "semantic_scholar",
        "cited_by_count": data.get("citationCount", 0),
    }


async def store_paper(paper_data: Dict[str, Any]) -> Optional[str]:
    """
    Save a paper to the shared_papers table.

    Generates an embedding from title + abstract for semantic search.
    Skips if DOI or arXiv ID already exists.

    Args:
        paper_data: Paper dict with title, authors, year, abstract, doi, etc.

    Returns:
        New paper UUID, or None if storage failed
    """
    doi = _normalize_doi(paper_data.get("doi"))
    arxiv_id = paper_data.get("arxiv_id")
    title = paper_data.get("title", "")

    if not title:
        logger.warning("[SharedPaperCache] Cannot store paper without title")
        return None

    # Build text for embedding: title + abstract
    embed_text = title
    if paper_data.get("abstract"):
        embed_text += f"\n{paper_data['abstract'][:500]}"

    # Generate embedding in thread to avoid blocking event loop
    embedding = await asyncio.to_thread(_embed_text, embed_text)

    record = {
        "title": title,
        "authors": paper_data.get("authors", []),
        "year": paper_data.get("year"),
        "abstract": paper_data.get("abstract"),
        "journal": paper_data.get("journal", ""),
        "doi": doi,
        "arxiv_id": arxiv_id.replace("arxiv:", "").strip() if arxiv_id else None,
        "pubmed_id": paper_data.get("pubmed_id"),
        "semantic_scholar_id": paper_data.get("semantic_scholar_id"),
        "openalex_id": paper_data.get("external_ids", {}).get("openalex_id"),
        "pdf_url": paper_data.get("pdf_url") or paper_data.get("open_access_url"),
        "source": paper_data.get("source", "unknown"),
        "embedding": embedding,
        "download_count": 0,
    }

    # Remove None values (Supabase handles nulls, but cleaner without them)
    record = {k: v for k, v in record.items() if v is not None}

    try:
        res = supabase.table("shared_papers").insert(record).execute()
        if res.data:
            return res.data[0]["id"]
    except Exception as e:
        # Likely a duplicate DOI/arXiv constraint — that's fine
        if "duplicate" in str(e).lower() or "unique" in str(e).lower():
            logger.debug(f"[SharedPaperCache] Paper already cached: {title[:60]}")
        else:
            logger.error(f"[SharedPaperCache] Failed to store paper: {e}")

    return None


async def find_similar_papers(
    query: str,
    limit: int = 10,
    similarity_threshold: float = 0.5,
) -> List[Dict[str, Any]]:
    """
    Semantic search over all globally cached papers.

    Embeds the query and runs pgvector cosine similarity against shared_papers.embedding.

    Args:
        query: Natural language search query
        limit: Max results to return
        similarity_threshold: Min cosine similarity (0-1)

    Returns:
        List of paper dicts with similarity scores
    """
    embedding = await asyncio.to_thread(_embed_text, query)
    if not embedding:
        logger.warning("[SharedPaperCache] Failed to embed search query")
        return []

    try:
        res = supabase.rpc(
            "match_shared_papers",
            {
                "query_embedding": embedding,
                "match_count": limit,
                "similarity_threshold": similarity_threshold,
            }
        ).execute()

        results = res.data or []
        logger.info(f"[SharedPaperCache] Semantic search returned {len(results)} results")
        return results

    except Exception as e:
        logger.error(f"[SharedPaperCache] Semantic search failed: {e}")
        return []

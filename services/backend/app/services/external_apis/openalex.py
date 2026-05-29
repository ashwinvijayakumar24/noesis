"""
OpenAlex API Client

Free, open scholarly database. No authentication required.
Rate limits: 100K requests/day (polite pool: include email in requests).

Covers 250M+ scholarly works across all disciplines.
Key advantage: open_access.oa_url field provides free PDF links.
"""

import aiohttp
import asyncio
from typing import List, Dict, Any, Optional
from app.core.logging_config import get_logger

logger = get_logger(__name__)

# Polite pool: include your email to get better rate limits
OPENALEX_BASE = "https://api.openalex.org"
CONTACT_EMAIL = "contact@noesis.is"


def _polite_params(extra: Dict[str, Any] = None) -> Dict[str, Any]:
    """Add polite pool email to any param dict."""
    params = {"mailto": CONTACT_EMAIL}
    if extra:
        params.update(extra)
    return params


def _format_paper(work: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize an OpenAlex work object into a standard paper dict.

    Returns:
        {
            title, authors, year, doi, abstract,
            journal, open_access_url, source, external_ids,
            cited_by_count, concepts
        }
    """
    # Authors
    authorships = work.get("authorships", [])
    authors = [
        a.get("author", {}).get("display_name", "Unknown")
        for a in authorships[:5]  # Cap at 5
    ]

    # Open access URL
    oa_info = work.get("open_access", {})
    oa_url = oa_info.get("oa_url") if oa_info else None

    # DOI (strip URL prefix)
    doi_raw = work.get("doi", "")
    doi = doi_raw.replace("https://doi.org/", "").replace("http://doi.org/", "") if doi_raw else None

    # Abstract (OpenAlex stores as inverted index — reconstruct)
    abstract = _reconstruct_abstract(work.get("abstract_inverted_index"))

    # Journal / venue
    primary_location = work.get("primary_location") or {}
    source = primary_location.get("source") or {}
    journal = source.get("display_name", "")

    # Concepts / keywords
    concepts = [
        c.get("display_name", "")
        for c in (work.get("concepts") or [])[:10]
        if c.get("score", 0) > 0.3
    ]

    return {
        "title": work.get("display_name") or work.get("title", "Untitled"),
        "authors": authors,
        "year": work.get("publication_year"),
        "doi": doi,
        "abstract": abstract,
        "journal": journal,
        "open_access_url": oa_url,
        "source": "openalex",
        "external_ids": {
            "openalex_id": work.get("id", ""),
            "doi": doi,
        },
        "cited_by_count": work.get("cited_by_count", 0),
        "concepts": concepts,
        "is_open_access": oa_info.get("is_oa", False) if oa_info else False,
    }


def _reconstruct_abstract(inverted_index: Optional[Dict[str, List[int]]]) -> Optional[str]:
    """
    Reconstruct abstract from OpenAlex inverted index format.

    OpenAlex stores abstracts as { "word": [position, position, ...], ... }
    """
    if not inverted_index:
        return None
    try:
        positions = {}
        for word, pos_list in inverted_index.items():
            for pos in pos_list:
                positions[pos] = word
        if not positions:
            return None
        words = [positions[i] for i in sorted(positions.keys())]
        return " ".join(words)
    except Exception:
        return None


async def search_works(
    query: str,
    per_page: int = 10,
    open_access_only: bool = False,
    year_from: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Search OpenAlex for scholarly works.

    Args:
        query: Search query string
        per_page: Number of results (max 200)
        open_access_only: If True, only return papers with free PDF
        year_from: Only return papers from this year onward

    Returns:
        List of formatted paper dicts
    """
    params = _polite_params({
        "search": query,
        "per-page": min(per_page, 50),
        "select": "id,display_name,title,authorships,publication_year,doi,abstract_inverted_index,open_access,primary_location,cited_by_count,concepts",
    })

    if open_access_only:
        params["filter"] = "open_access.is_oa:true"

    if year_from:
        existing_filter = params.get("filter", "")
        year_filter = f"publication_year:>{year_from - 1}"
        params["filter"] = f"{existing_filter},{year_filter}" if existing_filter else year_filter

    try:
        async with aiohttp.ClientSession() as session:
            url = f"{OPENALEX_BASE}/works"
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    logger.warning("[OpenAlex] Search returned %s", resp.status)
                    return []

                data = await resp.json()
                results = data.get("results", [])

                papers = [_format_paper(w) for w in results]
                logger.info("[OpenAlex] Found %s results", len(papers))
                return papers

    except asyncio.TimeoutError:
        logger.warning("[OpenAlex] Search timed out")
        return []
    except Exception as e:
        logger.error(f"[OpenAlex] Search error: {e}")
        return []


async def get_work_by_doi(doi: str) -> Optional[Dict[str, Any]]:
    """
    Fetch a specific work by DOI.

    Args:
        doi: DOI string (with or without https://doi.org/ prefix)

    Returns:
        Formatted paper dict, or None if not found
    """
    # Normalize DOI
    doi_clean = doi.replace("https://doi.org/", "").replace("http://doi.org/", "").strip()

    params = _polite_params({
        "filter": f"doi:https://doi.org/{doi_clean}",
        "select": "id,display_name,title,authorships,publication_year,doi,abstract_inverted_index,open_access,primary_location,cited_by_count,concepts",
    })

    try:
        async with aiohttp.ClientSession() as session:
            url = f"{OPENALEX_BASE}/works"
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                results = data.get("results", [])
                if results:
                    return _format_paper(results[0])
                return None

    except Exception as e:
        logger.error(f"[OpenAlex] get_work_by_doi error for {doi}: {e}")
        return None


async def search_concepts(topic: str, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Find related academic concepts for a topic (useful for query expansion).

    Args:
        topic: Topic string to find concepts for
        limit: Max concepts to return

    Returns:
        List of concept dicts: { id, display_name, description, level }
    """
    params = _polite_params({
        "search": topic,
        "per-page": limit,
        "select": "id,display_name,description,level,works_count",
    })

    try:
        async with aiohttp.ClientSession() as session:
            url = f"{OPENALEX_BASE}/concepts"
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                return [
                    {
                        "id": c.get("id", ""),
                        "display_name": c.get("display_name", ""),
                        "description": c.get("description", ""),
                        "level": c.get("level", 0),
                        "works_count": c.get("works_count", 0),
                    }
                    for c in data.get("results", [])
                ]
    except Exception as e:
        logger.error(f"[OpenAlex] search_concepts error: {e}")
        return []


async def find_open_access_papers_for_gap(
    gap_description: str,
    limit: int = 3,
) -> List[Dict[str, Any]]:
    """
    Find open-access papers relevant to a coverage gap.

    Used to auto-suggest external papers for identified gaps.
    Only returns papers with a free PDF URL.

    Args:
        gap_description: Description of the coverage gap
        limit: Max papers to return

    Returns:
        List of paper dicts (only those with open_access_url)
    """
    papers = await search_works(
        query=gap_description,
        per_page=limit * 3,  # Fetch extra in case some aren't OA
        open_access_only=True,
    )

    # Filter to only papers with actual PDF links
    oa_papers = [p for p in papers if p.get("open_access_url")][:limit]

    logger.info(
        f"[OpenAlex] Found {len(oa_papers)} open-access papers for gap: {gap_description[:60]}"
    )
    return oa_papers

"""
Draft Analysis External Source Discovery

Finds externally indexed papers for weak/unsupported high-importance draft
claims and serious coverage gaps. Results are cached globally in shared_papers,
also surfaced in paper_recommendations, and returned in a normalized shape for
reviewer feedback context.
"""

import asyncio
import re
from typing import Any, Dict, List, Optional

from app.core.logging_config import get_logger
from app.core.supabase_client import supabase
from app.services.external_apis.semantic_scholar import SemanticScholarAPI
from app.services.external_apis.openalex import search_works
from app.services.shared_paper_cache import store_paper

logger = get_logger(__name__)


MIN_IMPORTANCE_SCORE = 0.6
MAX_TARGETS = 8
MIN_CANDIDATES = 10
MAX_CANDIDATES = 20
PER_SOURCE_LIMIT = 8


def _clean_identifier(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return (
        str(value)
        .replace("https://doi.org/", "")
        .replace("http://doi.org/", "")
        .replace("arxiv:", "")
        .strip()
    ) or None


def _normalize_title(title: Optional[str]) -> str:
    if not title:
        return ""
    return re.sub(r"\s+", " ", title).strip().lower()


def _paper_key(paper: Dict[str, Any]) -> Optional[str]:
    doi = _clean_identifier(paper.get("doi"))
    arxiv_id = _clean_identifier(paper.get("arxiv_id"))
    title = _normalize_title(paper.get("title"))

    if doi:
        return f"doi:{doi.lower()}"
    if arxiv_id:
        return f"arxiv:{arxiv_id.lower()}"
    if title:
        return f"title:{title}"
    return None


def _target_id(target: Dict[str, Any]) -> str:
    return _target_key(target.get("target_type"), target.get("target_id"), target.get("text"))


def _target_key(
    target_type: Optional[str],
    target_id: Optional[str],
    target_text: Optional[str],
) -> str:
    return f"{target_type}:{target_id or _normalize_title(target_text)[:80]}"


def _target_context(target: Dict[str, Any]) -> Dict[str, Any]:
    context = {
        "draft_id": target["draft_id"],
        "target_type": target["target_type"],
        "target_id": target.get("target_id"),
        "target_text": target.get("text", "")[:500],
        "citation_quality": target.get("citation_quality"),
        "importance_score": target.get("importance_score"),
        "severity": target.get("severity"),
    }
    return {k: v for k, v in context.items() if v is not None}


def _select_claim_targets(
    draft_id: str,
    claims_with_citations: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    targets: List[Dict[str, Any]] = []

    for cwc in claims_with_citations or []:
        quality = cwc.get("citation_quality")
        claim = cwc.get("claim") or {}
        importance = claim.get("importance_score", 0) or 0
        claim_text = (claim.get("claim_text") or "").strip()

        if quality not in {"weak", "none"}:
            continue
        if importance < MIN_IMPORTANCE_SCORE or not claim_text:
            continue

        gap_text = " ".join((cwc.get("gaps") or [])[:2]).strip()
        targets.append(
            {
                "draft_id": draft_id,
                "target_type": "claim",
                "target_id": claim.get("id"),
                "text": claim_text,
                "search_query": f"{claim_text} {gap_text}".strip(),
                "citation_quality": quality,
                "importance_score": importance,
                "rank": importance + (0.2 if quality == "none" else 0.1),
            }
        )

    targets.sort(key=lambda t: t["rank"], reverse=True)
    return targets


def _select_gap_targets(
    draft_id: str,
    coverage_gaps: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    severity_rank = {
        "critical": 1.0,
        "high": 0.9,
        "major": 0.85,
        "important": 0.75,
        "medium": 0.55,
    }
    targets: List[Dict[str, Any]] = []

    for gap in coverage_gaps or []:
        description = (gap.get("description") or "").strip()
        severity = gap.get("severity") or gap.get("priority") or "medium"
        rank = severity_rank.get(str(severity).lower(), 0.0)

        if rank < 0.75 or not description:
            continue

        targets.append(
            {
                "draft_id": draft_id,
                "target_type": "gap",
                "target_id": gap.get("id"),
                "text": description,
                "search_query": description,
                "severity": severity,
                "rank": rank,
            }
        )

    targets.sort(key=lambda t: t["rank"], reverse=True)
    return targets


def _select_targets(
    draft_id: str,
    claims_with_citations: List[Dict[str, Any]],
    coverage_gaps: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    combined = _select_claim_targets(draft_id, claims_with_citations) + _select_gap_targets(
        draft_id,
        coverage_gaps,
    )

    seen: set[str] = set()
    targets: List[Dict[str, Any]] = []
    for target in combined:
        key = _target_id(target)
        if key in seen:
            continue
        seen.add(key)
        targets.append(target)
        if len(targets) >= MAX_TARGETS:
            break
    return targets


def _normalize_candidate(
    paper: Dict[str, Any],
    target: Dict[str, Any],
    source: str,
) -> Optional[Dict[str, Any]]:
    title = (paper.get("title") or "").strip()
    if not title:
        return None

    authors = paper.get("authors") or []
    if isinstance(authors, str):
        authors = [authors]

    citation_count = paper.get("citation_count")
    if citation_count is None:
        citation_count = paper.get("cited_by_count")

    paper_url = paper.get("paper_url") or paper.get("url")
    pdf_url = paper.get("pdf_url") or paper.get("open_access_url")
    journal_name = paper.get("journal_name") or paper.get("journal") or ""
    arxiv_id = _clean_identifier(paper.get("arxiv_id"))
    doi = _clean_identifier(paper.get("doi"))
    if doi and arxiv_id and doi.lower() == arxiv_id.lower():
        doi = None

    target_text = target.get("text", "")
    query_terms = {
        token
        for token in re.findall(r"[A-Za-z][A-Za-z0-9-]{3,}", target_text.lower())
    }
    paper_text = f"{title} {paper.get('abstract') or ''}".lower()
    overlap = sum(1 for term in list(query_terms)[:30] if term in paper_text)
    overlap_score = min(0.6, overlap * 0.06)
    citation_score = min(0.2, (citation_count or 0) / 500)
    access_score = 0.1 if (pdf_url or paper_url or doi or arxiv_id) else 0
    target_score = min(0.1, (target.get("rank") or 0) / 10)
    relevance_score = round(min(1.0, 0.25 + overlap_score + citation_score + access_score + target_score), 3)

    return {
        "title": title,
        "abstract": paper.get("abstract"),
        "authors": authors[:10],
        "year": paper.get("year") or paper.get("publication_year"),
        "doi": doi,
        "arxiv_id": arxiv_id,
        "pubmed_id": paper.get("pubmed_id"),
        "semantic_scholar_id": paper.get("semantic_scholar_id"),
        "openalex_id": (paper.get("external_ids") or {}).get("openalex_id"),
        "source": source,
        "paper_url": paper_url,
        "pdf_url": pdf_url,
        "citation_count": citation_count or 0,
        "journal_name": journal_name,
        "publication_type": paper.get("publication_type"),
        "fields_of_study": paper.get("fields_of_study") or paper.get("concepts") or [],
        "relevance_score": relevance_score,
        "relevance_reason": (
            f"External source for {target['target_type']} needing stronger support; "
            f"matched {overlap} query terms"
        ),
        "matched_keywords": sorted(list(query_terms))[:8],
        "addresses_gaps": [target.get("target_type", "draft_analysis")],
        "search_query": target["search_query"],
        "recommendation_context": _target_context(target),
    }


async def _search_semantic_scholar(query: str, limit: int) -> List[Dict[str, Any]]:
    api = SemanticScholarAPI()
    return await asyncio.to_thread(api.search_papers, query=query, limit=limit)


async def _fetch_candidates_for_target(target: Dict[str, Any]) -> List[Dict[str, Any]]:
    query = target["search_query"][:300]
    candidates: List[Dict[str, Any]] = []

    try:
        ss_papers = await _search_semantic_scholar(query, PER_SOURCE_LIMIT)
        for paper in ss_papers or []:
            normalized = _normalize_candidate(paper, target, "semantic_scholar")
            if normalized:
                candidates.append(normalized)
    except Exception as exc:
        logger.warning(f"[DraftExternalDiscovery] Semantic Scholar failed: {exc}")

    if len(candidates) < MIN_CANDIDATES:
        try:
            oa_papers = await search_works(query=query, per_page=PER_SOURCE_LIMIT, open_access_only=False)
            for paper in oa_papers or []:
                normalized = _normalize_candidate(paper, target, "openalex")
                if normalized:
                    candidates.append(normalized)
        except Exception as exc:
            logger.warning(f"[DraftExternalDiscovery] OpenAlex failed: {exc}")

    return candidates


def _deduplicate_candidates(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: set[str] = set()
    unique: List[Dict[str, Any]] = []

    for candidate in sorted(candidates, key=lambda c: c.get("relevance_score", 0), reverse=True):
        key = _paper_key(candidate)
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
        if len(unique) >= MAX_CANDIDATES:
            break

    return unique


def _load_existing_recommendation_keys(project_id: str, user_id: str) -> Dict[str, str]:
    try:
        res = (
            supabase.table("paper_recommendations")
            .select("id, doi, arxiv_id, title")
            .eq("project_id", project_id)
            .eq("user_id", user_id)
            .execute()
        )
    except Exception as exc:
        logger.warning(f"[DraftExternalDiscovery] Existing recommendation lookup failed: {exc}")
        return {}

    keys: Dict[str, str] = {}
    for row in res.data or []:
        key = _paper_key(row)
        if key:
            keys[key] = row["id"]
    return keys


async def _lookup_shared_paper_id(paper: Dict[str, Any]) -> Optional[str]:
    try:
        query = supabase.table("shared_papers").select("id").limit(1)
        if paper.get("doi"):
            query = query.eq("doi", paper["doi"])
        elif paper.get("arxiv_id"):
            query = query.eq("arxiv_id", paper["arxiv_id"])
        elif paper.get("title"):
            query = query.eq("title", paper["title"])
        else:
            return None

        res = query.execute()
        if res.data:
            return res.data[0].get("id")
    except Exception as exc:
        logger.debug(f"[DraftExternalDiscovery] shared_papers id lookup failed: {exc}")
    return None


async def _store_shared_paper(candidate: Dict[str, Any]) -> Optional[str]:
    shared_id = await store_paper(
        {
            "title": candidate["title"],
            "authors": candidate.get("authors", []),
            "year": candidate.get("year"),
            "abstract": candidate.get("abstract"),
            "journal": candidate.get("journal_name"),
            "doi": candidate.get("doi"),
            "arxiv_id": candidate.get("arxiv_id"),
            "pubmed_id": candidate.get("pubmed_id"),
            "semantic_scholar_id": candidate.get("semantic_scholar_id"),
            "external_ids": {"openalex_id": candidate.get("openalex_id")},
            "pdf_url": candidate.get("pdf_url"),
            "source": candidate.get("source", "unknown"),
        }
    )
    if shared_id:
        return shared_id
    return await _lookup_shared_paper_id(candidate)


def _recommendation_insert_payload(
    project_id: str,
    user_id: str,
    candidate: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "project_id": project_id,
        "user_id": user_id,
        "discovery_type": "draft_analysis",
        "search_query": candidate.get("search_query"),
        "bib_saved": False,
        "status": "new",
        "title": candidate["title"],
        "abstract": candidate.get("abstract"),
        "authors": candidate.get("authors", []),
        "year": candidate.get("year"),
        "doi": candidate.get("doi"),
        "arxiv_id": candidate.get("arxiv_id"),
        "pubmed_id": candidate.get("pubmed_id"),
        "semantic_scholar_id": candidate.get("semantic_scholar_id"),
        "source": candidate.get("source", "unknown"),
        "paper_url": candidate.get("paper_url"),
        "pdf_url": candidate.get("pdf_url"),
        "citation_count": candidate.get("citation_count", 0),
        "journal_name": candidate.get("journal_name"),
        "publication_type": candidate.get("publication_type"),
        "fields_of_study": candidate.get("fields_of_study", []),
        "relevance_score": candidate.get("relevance_score", 0.0),
        "relevance_reason": candidate.get("relevance_reason"),
        "matched_keywords": candidate.get("matched_keywords", []),
        "addresses_gaps": candidate.get("addresses_gaps", []),
        "recommendation_context": candidate.get("recommendation_context", {}),
    }


def _store_recommendation(
    project_id: str,
    user_id: str,
    candidate: Dict[str, Any],
    existing_keys: Dict[str, str],
) -> Optional[str]:
    key = _paper_key(candidate)
    if key and key in existing_keys:
        return existing_keys[key]

    payload = _recommendation_insert_payload(project_id, user_id, candidate)
    try:
        res = supabase.table("paper_recommendations").insert(payload).execute()
    except Exception as exc:
        # Older local schemas may not have every Discover column yet.
        optional_columns = ["recommendation_context", "discovery_type", "search_query", "bib_saved"]
        if not any(column in str(exc) for column in optional_columns):
            logger.warning(f"[DraftExternalDiscovery] recommendation insert failed: {exc}")
            return None
        fallback = dict(payload)
        fallback.pop("recommendation_context", None)
        fallback.pop("discovery_type", None)
        fallback.pop("search_query", None)
        fallback.pop("bib_saved", None)
        try:
            res = supabase.table("paper_recommendations").insert(fallback).execute()
        except Exception as fallback_exc:
            logger.warning(f"[DraftExternalDiscovery] fallback recommendation insert failed: {fallback_exc}")
            return None

    if res.data:
        recommendation_id = res.data[0].get("id")
        if key and recommendation_id:
            existing_keys[key] = recommendation_id
        return recommendation_id
    return None


def _external_source_record(
    candidate: Dict[str, Any],
    shared_paper_id: Optional[str],
    recommendation_id: Optional[str],
) -> Dict[str, Any]:
    return {
        "type": "external_source",
        "title": candidate["title"],
        "authors": candidate.get("authors", []),
        "year": candidate.get("year"),
        "abstract": candidate.get("abstract"),
        "source": candidate.get("source"),
        "doi": candidate.get("doi"),
        "arxiv_id": candidate.get("arxiv_id"),
        "paper_url": candidate.get("paper_url"),
        "pdf_url": candidate.get("pdf_url"),
        "citation_count": candidate.get("citation_count", 0),
        "journal_name": candidate.get("journal_name"),
        "relevance_score": candidate.get("relevance_score", 0.0),
        "relevance_reason": candidate.get("relevance_reason"),
        "search_query": candidate.get("search_query"),
        "recommendation_context": candidate.get("recommendation_context", {}),
        "shared_paper_id": shared_paper_id,
        "recommendation_id": recommendation_id,
    }


def attach_external_sources_to_analysis(
    claims_with_citations: List[Dict[str, Any]],
    coverage_gaps: List[Dict[str, Any]],
    external_sources: List[Dict[str, Any]],
) -> None:
    """Attach normalized external sources back to matching in-memory claims/gaps."""
    by_target: Dict[str, List[Dict[str, Any]]] = {}
    for source in external_sources:
        context = source.get("recommendation_context") or {}
        key = _target_key(
            context.get("target_type"),
            context.get("target_id"),
            context.get("target_text"),
        )
        by_target.setdefault(key, []).append(source)

    for cwc in claims_with_citations or []:
        claim = cwc.get("claim") or {}
        key = _target_key("claim", claim.get("id"), claim.get("claim_text"))
        sources = by_target.get(key, [])[:5]
        if not sources:
            continue
        cwc["external_sources"] = sources
        cwc["suggested_citations"] = [
            {
                "title": source["title"],
                "authors": source.get("authors", []),
                "year": source.get("year"),
                "display": _format_source_display(source),
                "url": source.get("paper_url") or source.get("pdf_url"),
                "source": source.get("source"),
                "recommendation_id": source.get("recommendation_id"),
                "shared_paper_id": source.get("shared_paper_id"),
            }
            for source in sources
        ]

    for gap in coverage_gaps or []:
        key = _target_key("gap", gap.get("id"), gap.get("description"))
        sources = by_target.get(key, [])[:5]
        if sources:
            existing = gap.get("suggested_papers") or []
            gap["external_sources"] = sources
            gap["suggested_papers"] = existing + sources


def _format_source_display(source: Dict[str, Any]) -> str:
    authors = source.get("authors") or []
    first_author = authors[0] if authors else ""
    year = source.get("year")
    title = source.get("title", "Untitled")
    source_label = "Semantic Scholar" if source.get("source") == "semantic_scholar" else "OpenAlex"

    if first_author and year:
        return f"{first_author} et al. ({year}) · {source_label}"
    if first_author:
        return f"{first_author} et al. · {source_label}"
    return f"{title} · {source_label}"


async def discover_external_sources_for_draft(
    *,
    draft_id: str,
    project_id: str,
    user_id: str,
    claims_with_citations: List[Dict[str, Any]],
    coverage_gaps: List[Dict[str, Any]],
    min_candidates: int = MIN_CANDIDATES,
    max_candidates: int = MAX_CANDIDATES,
) -> List[Dict[str, Any]]:
    """
    Discover, validate, persist, and normalize external papers for draft analysis.

    Targets weak/unsupported high-importance claims plus high-priority gaps.
    Returns normalized external_source records suitable for reviewer feedback.
    """
    if not draft_id or not project_id or not user_id:
        return []

    targets = _select_targets(draft_id, claims_with_citations, coverage_gaps)
    if not targets:
        logger.info("[DraftExternalDiscovery] No weak/none high-importance claims or serious gaps")
        return []

    all_candidates: List[Dict[str, Any]] = []
    for target in targets:
        all_candidates.extend(await _fetch_candidates_for_target(target))
        if len(_deduplicate_candidates(all_candidates)) >= min_candidates:
            break

    candidates = _deduplicate_candidates(all_candidates)[:max_candidates]
    if not candidates:
        return []

    existing_keys = _load_existing_recommendation_keys(project_id, user_id)
    external_sources: List[Dict[str, Any]] = []

    for candidate in candidates:
        shared_paper_id = await _store_shared_paper(candidate)
        recommendation_id = _store_recommendation(project_id, user_id, candidate, existing_keys)
        if shared_paper_id or recommendation_id:
            external_sources.append(
                _external_source_record(candidate, shared_paper_id, recommendation_id)
            )

    logger.info(
        "[DraftExternalDiscovery] Stored %s external sources from %s targets",
        len(external_sources),
        len(targets),
    )
    return external_sources

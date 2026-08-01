"""
Draft Analysis External Source Discovery

Finds externally indexed papers for weak/unsupported high-importance draft
claims and serious coverage gaps. Results are returned in a normalized shape for
reviewer feedback context. Optional project-level recommendation persistence is
kept separate from the analysis payload.
"""

import asyncio
import re
from typing import Any, Dict, List, Optional

import aiohttp

from app.core.logging_config import get_logger
from app.core.supabase_client import supabase
from app.services.external_apis.semantic_scholar import SemanticScholarAPI
from app.services.external_apis.pubmed import PubMedAPI
from app.services.external_apis.openalex import search_works

logger = get_logger(__name__)

_OA_BASE = "https://api.openalex.org"
_OA_EMAIL = "contact@noesis.is"
_OA_FIELDS_CG = (
    "id,display_name,title,authorships,publication_year,doi,"
    "abstract_inverted_index,open_access,primary_location,cited_by_count"
)


def _reconstruct_abstract(inverted: dict | None) -> str:
    if not inverted:
        return ""
    try:
        pos: dict[int, str] = {}
        for word, positions in inverted.items():
            for p in positions:
                pos[p] = word
        return " ".join(pos[i] for i in sorted(pos))
    except Exception:
        return ""


MIN_IMPORTANCE_SCORE = 0.6
MAX_TARGETS = 8
MIN_CANDIDATES = 10
MAX_CANDIDATES = 20
PER_SOURCE_LIMIT = 8
MIN_RELEVANCE_SCORE = 0.72
MIN_INTERNAL_TASK_SOURCE_SIMILARITY = 0.68
MIN_TASK_EXTERNAL_RELEVANCE_SCORE = 0.70
MIN_HUMANITIES_TASK_EXTERNAL_RELEVANCE_SCORE = 0.56
PERSIST_DRAFT_EXTERNAL_RECOMMENDATIONS = False

GENERIC_TARGET_PATTERNS = (
    "no supporting literature found in your library",
    "no supporting citations found",
    "no matching evidence in library or online",
    "no matching evidence",
    "current support is insufficient",
)

STOPWORDS = {
    "about", "above", "after", "again", "against", "also", "because", "been",
    "being", "between", "cannot", "claim", "claims", "could", "current",
    "draft", "evidence", "found", "from", "have", "into", "library", "literature",
    "missing", "more", "needs", "paper", "papers", "section", "should", "study",
    "studies", "support", "supported", "supporting", "that", "their", "there",
    "these", "this", "those", "through", "using", "with", "without", "would",
}

GENERIC_RELEVANCE_TERMS = {
    "analysis", "article", "data", "database", "databases", "domain", "field",
    "fields", "framework", "gray", "grey", "health", "implementation",
    "intervention", "interventions", "method", "methods", "methodology",
    "organization", "organizational", "practice", "protocol", "public",
    "registration", "report", "reporting", "research", "sector",
    "review", "reviews", "risk", "search", "source", "sources", "strategy",
    "strategies", "systematic",
}

METHODOLOGY_GUIDELINE_TERMS = {
    "prisma", "consort", "strobe", "moose", "robins-i", "robins",
    "cochrane handbook", "reporting guideline", "risk of bias tool",
}

SOURCE_WORTHY_TASK_TYPES = {
    "citation",
    "literature_positioning",
    "framework_validation",
}


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
        "draft_id": target.get("draft_id"),
        "target_type": target.get("target_type"),
        "target_id": target.get("target_id"),
        "target_text": target.get("text", "")[:500],
        "citation_quality": target.get("citation_quality"),
        "importance_score": target.get("importance_score"),
        "severity": target.get("severity"),
    }
    return {k: v for k, v in context.items() if v is not None}


def _is_generic_target_text(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", (text or "").strip().lower())
    if not normalized:
        return True
    return any(normalized == pattern or normalized.startswith(pattern) for pattern in GENERIC_TARGET_PATTERNS)


def _meaningful_terms(text: str) -> List[str]:
    terms: List[str] = []
    for token in re.findall(r"[A-Za-z][A-Za-z0-9-]{3,}", (text or "").lower()):
        token = token.strip("-")
        if token in STOPWORDS or len(token) < 4:
            continue
        if token not in terms:
            terms.append(token)
    return terms


def _profile_terms(manuscript_profile: Dict[str, Any] | None = None) -> set[str]:
    profile = manuscript_profile or {}
    return {
        term for term in _meaningful_terms(" ".join([
            str(profile.get("routing_domain") or "").lower(),
            *[str(item).lower() for item in profile.get("domain_tags") or []],
            *[str(item).lower() for item in profile.get("review_lenses") or []],
        ]))
        if term not in GENERIC_RELEVANCE_TERMS
    }


def _topic_terms(text: str) -> set[str]:
    return {term for term in _meaningful_terms(text) if term not in GENERIC_RELEVANCE_TERMS}


def _distinctive_topic_terms(manuscript_profile: Dict[str, Any] | None = None) -> set[str]:
    """The manuscript's SUBJECT vocabulary (e.g. {social, media, screen}) — its
    title/abstract topic_terms minus the broad domain-tag terms. A topical source
    must share at least one of these to be on-topic; a paper that only shares generic
    domain words (adolescent, mental, health) is NOT about the same subject.
    """
    profile = manuscript_profile or {}
    topic = {t for t in (profile.get("topic_terms") or []) if t not in GENERIC_RELEVANCE_TERMS}
    return topic - _profile_terms(profile)


def _is_methodology_guideline_source(source_text: str) -> bool:
    lower = (source_text or "").lower()
    return any(term in lower for term in METHODOLOGY_GUIDELINE_TERMS)


def _is_methodology_task(query_text: str) -> bool:
    lower = (query_text or "").lower()
    return bool(re.search(
        r"\b(methodology|methods?|reporting|protocol|registration|prisma|search strateg|risk of bias|meta-analysis|systematic review|guideline)\b",
        lower,
        flags=re.IGNORECASE,
    ))


def _passes_domain_gate(query_text: str, source_text: str, score: float, manuscript_profile: Dict[str, Any] | None = None) -> bool:
    source_terms = set(_meaningful_terms(source_text))
    query_terms = set(_meaningful_terms(query_text))
    topic_query_terms = _topic_terms(query_text)
    profile_terms = _profile_terms(manuscript_profile)
    query_overlap = source_terms & query_terms
    topic_overlap = source_terms & topic_query_terms
    profile_overlap = source_terms & profile_terms

    if _is_methodology_task(query_text) and _is_methodology_guideline_source(source_text):
        return True

    # Topic gate: a topical (non-methodology) source must share >=2 of the
    # manuscript's distinctive subject terms. This rejects papers that only share
    # generic domain words or a single shared outcome (e.g. a child-maltreatment
    # paper sharing "depression" with a social-media review). NOT bypassed by a high
    # relevance_score — that score is inflated by citation count + methodology-term
    # overlap, so an off-topic high-citation systematic review can hit 1.0 without
    # being on-topic. Legitimate methodology guidelines are already bypassed above.
    # Only applied when we have enough topic signal (>=3 distinctive terms).
    # Require at least 1 distinctive topic term overlap (was 2 — too aggressive).
    # Papers sharing ANY of the manuscript's distinctive subject terms pass.
    distinctive = _distinctive_topic_terms(manuscript_profile)
    if len(distinctive) >= 3 and not (source_terms & distinctive):
        return False

    if score < MIN_TASK_EXTERNAL_RELEVANCE_SCORE and len(query_overlap) < 2:
        return False
    if manuscript_profile and not (profile_overlap or topic_overlap):
        return False
    if profile_terms and not profile_overlap and len(topic_overlap) < 1 and score < 0.82:
        return False
    return bool(topic_overlap or profile_overlap or score >= 0.86)


def _build_search_query(*parts: str) -> str:
    terms = _meaningful_terms(" ".join(part for part in parts if part))
    return " ".join(terms[:14])


def _is_biomedical_query(query_terms: set[str]) -> bool:
    biomedical_general_terms = {
        "clinical", "patient", "patients", "hospital", "medicine", "medical",
        "health", "healthcare", "therapy", "diagnosis", "treatment", "trial",
        "disease", "mortality", "cohort", "risk", "bias",
    }
    return len(query_terms & biomedical_general_terms) >= 2


def _is_task_source_worthy(task: Dict[str, Any]) -> bool:
    if (task.get("task_type") or "") in SOURCE_WORTHY_TASK_TYPES:
        return True
    severity = str(task.get("severity") or "").lower()
    if severity in {"critical", "major"} and (task.get("task_type") or "") in {
        "methodology",
        "causal_claim",
        "reproducibility",
    }:
        return True
    text = f"{task.get('problem', '')} {task.get('suggested_action', '')}".lower()
    if re.search(
        r"\b("
        r"citation|cite|source|sources|literature|prior work|related work|"
        r"benchmark|comparison|external validation|validation|framework|"
        r"methodology|methods?|protocol|registration|search strateg|database|"
        r"risk of bias|reporting|replication|reproducib|evidence|empirical|"
        r"theory|theoretical|mechanism|causal|causality|generalizability"
        r")\b",
        text,
    ):
        return True
    return False


def _task_source_query(task: Dict[str, Any]) -> str:
    return _build_search_query(
        task.get("problem", ""),
        task.get("suggested_action", ""),
        task.get("anchor_text", ""),
    )


def _select_task_targets(
    draft_id: str,
    revision_tasks: List[Dict[str, Any]],
    *,
    max_targets: int = MAX_TARGETS,
    manuscript_profile: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    severity_rank = {"critical": 1.0, "major": 0.85, "minor": 0.35, "suggestion": 0.2}
    priority_rank = {"high": 0.2, "medium": 0.1, "low": 0.0}
    targets: List[Dict[str, Any]] = []

    for task in revision_tasks or []:
        if task.get("suggested_sources"):
            continue
        if not _is_task_source_worthy(task):
            continue
        search_query = _task_source_query(task)
        if not search_query:
            continue
        rank = severity_rank.get(str(task.get("severity", "")).lower(), 0.5) + priority_rank.get(str(task.get("priority", "")).lower(), 0.0)
        targets.append({
            "draft_id": draft_id,
            "target_type": "revision_task",
            "target_id": task.get("id"),
            "text": f"{task.get('problem', '')} {task.get('suggested_action', '')}".strip(),
            "search_query": _build_search_query(
                " ".join(str(value) for value in [
                    (manuscript_profile or {}).get("routing_domain"),
                    *((manuscript_profile or {}).get("domain_tags") or []),
                    *((manuscript_profile or {}).get("review_lenses") or []),
                ]),
                search_query,
            ),
            "severity": task.get("severity"),
            "task_type": task.get("task_type"),
            "dedupe_category": task.get("dedupe_category"),
            "manuscript_profile": manuscript_profile or {},
            "rank": rank,
        })

    targets.sort(key=lambda t: t["rank"], reverse=True)
    return targets[:max_targets]


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

        if claim.get("requires_citation") is False:
            continue
        if quality not in {None, "unknown", "weak", "none"}:
            continue
        if importance < MIN_IMPORTANCE_SCORE or not claim_text:
            continue

        gap_text = " ".join(
            gap for gap in (cwc.get("gaps") or [])[:2]
            if isinstance(gap, str) and not _is_generic_target_text(gap)
        ).strip()
        search_query = _build_search_query(claim_text, gap_text)
        if not search_query:
            continue
        targets.append(
            {
                "draft_id": draft_id,
                "target_type": "claim",
                "target_id": claim.get("id"),
                "text": claim_text,
                "search_query": search_query,
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
        if _is_generic_target_text(description):
            continue

        search_query = _build_search_query(description)
        if not search_query:
            continue

        targets.append(
            {
                "draft_id": draft_id,
                "target_type": "gap",
                "target_id": gap.get("id"),
                "text": description,
                "search_query": search_query,
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

    query_text = target.get("search_query") or target.get("text", "")
    query_terms = set(_meaningful_terms(query_text))
    if len(query_terms) < 2:
        return None

    paper_text = f"{title} {paper.get('abstract') or ''}".lower()
    matched_terms = sorted(term for term in query_terms if term in paper_text)
    overlap = len(matched_terms)
    biomedical_query = _is_biomedical_query(query_terms)
    manuscript_profile = target.get("manuscript_profile") or {}
    paper_terms = set(_meaningful_terms(paper_text))
    profile_overlap = paper_terms & _profile_terms(manuscript_profile)
    topic_overlap = paper_terms & _topic_terms(query_text)
    methodology_exception = _is_methodology_task(query_text) and _is_methodology_guideline_source(paper_text)
    if overlap < 2:
        return None
    if overlap == 2 and not (profile_overlap or methodology_exception or (citation_count or 0) >= 25):
        return None
    if manuscript_profile and not (profile_overlap or topic_overlap or methodology_exception):
        return None
    if manuscript_profile and not profile_overlap and not methodology_exception and overlap < 3:
        return None

    overlap_score = min(0.65, overlap * 0.08)
    citation_score = min(0.2, (citation_count or 0) / 500)
    access_score = 0.1 if (pdf_url or paper_url or doi or arxiv_id) else 0
    target_score = min(0.1, (target.get("rank") or 0) / 10)
    field_score = 0.08 if (profile_overlap or methodology_exception or biomedical_query) else 0
    relevance_score = round(min(1.0, overlap_score + citation_score + access_score + target_score + field_score), 3)
    min_score = MIN_TASK_EXTERNAL_RELEVANCE_SCORE if target.get("target_type") == "revision_task" else MIN_RELEVANCE_SCORE
    route_key = str((manuscript_profile or {}).get("routing_domain") or "").lower()
    if route_key in {"humanities_education", "humanities_theory", "computer_science_conceptual"} and target.get("target_type") == "revision_task":
        min_score = MIN_HUMANITIES_TASK_EXTERNAL_RELEVANCE_SCORE
    if relevance_score < min_score:
        logger.info(
            "[DraftExternalDiscovery] Dropping low-confidence source score=%s matched_terms=%s",
            relevance_score,
            matched_terms[:8],
        )
        return None
    if not _passes_domain_gate(query_text, paper_text, relevance_score, manuscript_profile):
        return None

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
            f"matched {overlap} task/profile terms"
        ),
        "matched_keywords": matched_terms[:8],
        "addresses_gaps": [target.get("target_type", "draft_analysis")],
        "search_query": target["search_query"],
        "recommendation_context": _target_context(target),
    }


async def _fetch_citation_graph_candidates(
    resolved_refs: List[Dict[str, Any]],
    max_refs_to_use: int = 8,
    max_output: int = 12,
) -> List[Dict[str, Any]]:
    """
    Find papers co-cited by ≥2 of the author's own references (OpenAlex).

    Strategy: for each resolved ref (has DOI + abstract), fetch its
    referenced_works list from OpenAlex. Count how many of the author's refs
    each candidate appears in. Papers in 2+ lists are foundational work the
    author likely missed. Papers already in the author's bibliography are excluded.
    """
    resolved = [r for r in (resolved_refs or []) if r.get("doi") and r.get("resolved")]
    if not resolved:
        logger.info("[CitGraph] No resolved refs with DOI — skipping citation-graph path")
        return []

    known_dois: set[str] = {
        (_clean_identifier(r.get("doi") or "") or "").lower()
        for r in resolved_refs
        if r.get("doi")
    }

    # Step 1: fetch referenced_works for each resolved ref
    co_cited_counts: dict[str, int] = {}

    async with aiohttp.ClientSession() as session:
        for ref in resolved[:max_refs_to_use]:
            doi_clean = _clean_identifier(ref.get("doi") or "") or ""
            if not doi_clean:
                continue
            try:
                async with session.get(
                    f"{_OA_BASE}/works/https://doi.org/{doi_clean}",
                    params={"mailto": _OA_EMAIL, "select": "id,referenced_works"},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for ref_id in (data.get("referenced_works") or []):
                            co_cited_counts[ref_id] = co_cited_counts.get(ref_id, 0) + 1
            except Exception as exc:
                logger.debug("[CitGraph] ref lookup failed: %s", exc)
            await asyncio.sleep(0.05)

    # Step 2: keep papers co-cited by ≥2 of the author's refs
    co_cited_pairs = sorted(
        [(oa_id, cnt) for oa_id, cnt in co_cited_counts.items() if cnt >= 2],
        key=lambda x: x[1],
        reverse=True,
    )
    score_map = {oa_id: cnt for oa_id, cnt in co_cited_pairs}
    top_ids = [oa_id for oa_id, _ in co_cited_pairs[:max_output]]

    if not top_ids:
        logger.info("[CitGraph] No papers co-cited by >=2 of the author's references")
        return []

    logger.info("[CitGraph] %d papers co-cited by >=2 refs; fetching metadata", len(top_ids))

    # Step 3: fetch metadata for each co-cited paper
    async def _fetch_one(session: aiohttp.ClientSession, oa_id: str) -> dict | None:
        try:
            async with session.get(
                oa_id,
                params={"mailto": _OA_EMAIL, "select": _OA_FIELDS_CG},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    work = await resp.json()
                    doi_raw = work.get("doi") or ""
                    doi_norm = (_clean_identifier(doi_raw) or "").lower()
                    if doi_norm and doi_norm in known_dois:
                        return None  # already in bibliography
                    abstract = _reconstruct_abstract(work.get("abstract_inverted_index"))
                    authors = [
                        a.get("author", {}).get("display_name", "")
                        for a in (work.get("authorships") or [])[:5]
                    ]
                    return {
                        "title": work.get("display_name") or work.get("title") or "",
                        "abstract": abstract,
                        "authors": authors,
                        "year": work.get("publication_year"),
                        "doi": _clean_identifier(doi_raw) if doi_raw else "",
                        "journal": (
                            ((work.get("primary_location") or {}).get("source") or {})
                            .get("display_name") or ""
                        ),
                        "citation_count": work.get("cited_by_count", 0),
                        "open_access_url": (work.get("open_access") or {}).get("oa_url"),
                        "co_citation_score": score_map.get(oa_id, 1),
                    }
        except Exception as exc:
            logger.debug("[CitGraph] metadata fetch failed for %s: %s", oa_id, exc)
        return None

    papers: List[Dict[str, Any]] = []
    async with aiohttp.ClientSession() as session:
        results = await asyncio.gather(
            *[_fetch_one(session, oa_id) for oa_id in top_ids],
            return_exceptions=True,
        )
        for r in results:
            if isinstance(r, dict) and r and r.get("title"):
                papers.append(r)

    papers.sort(key=lambda x: x.get("co_citation_score", 0), reverse=True)
    logger.info("[CitGraph] %d co-cited papers fetched (excluding bibliography)", len(papers))
    return papers[:max_output]


def _citation_graph_to_external_source(paper: dict, draft_id: str) -> Dict[str, Any]:
    """Convert a citation-graph paper to the external_source record shape."""
    co_score = paper.get("co_citation_score", 1)
    relevance_score = round(min(0.95, 0.68 + co_score * 0.08), 3)
    return {
        "type": "external_source",
        "title": paper["title"],
        "authors": paper.get("authors", []),
        "year": paper.get("year"),
        "abstract": paper.get("abstract"),
        "source": "citation_graph",
        "doi": paper.get("doi"),
        "arxiv_id": None,
        "paper_url": paper.get("open_access_url"),
        "pdf_url": paper.get("open_access_url"),
        "citation_count": paper.get("citation_count", 0),
        "journal_name": paper.get("journal", ""),
        "relevance_score": relevance_score,
        "relevance_reason": (
            f"Co-cited by {co_score} of the author's own references "
            "— likely foundational work missing from the bibliography"
        ),
        "search_query": "citation_graph",
        "recommendation_context": {
            "draft_id": draft_id,
            "target_type": "citation_graph",
            "target_id": "citation_graph",
            "co_citation_score": co_score,
        },
        "shared_paper_id": None,
        "recommendation_id": None,
    }


async def _search_semantic_scholar(query: str, limit: int) -> List[Dict[str, Any]]:
    api = SemanticScholarAPI()
    return await asyncio.to_thread(api.search_papers, query=query, limit=limit)


async def _search_pubmed(query: str, limit: int) -> List[Dict[str, Any]]:
    api = PubMedAPI()
    return await asyncio.to_thread(api.search_papers, query=query, limit=limit)


async def _fetch_candidates_for_target(target: Dict[str, Any]) -> List[Dict[str, Any]]:
    query = target["search_query"][:300]
    candidates: List[Dict[str, Any]] = []
    query_terms = set(_meaningful_terms(query))

    if _is_biomedical_query(query_terms):
        try:
            pubmed_papers = await _search_pubmed(query, PER_SOURCE_LIMIT)
            for paper in pubmed_papers or []:
                normalized = _normalize_candidate(paper, target, "pubmed")
                if normalized:
                    candidates.append(normalized)
        except Exception as exc:
            logger.warning(f"[DraftExternalDiscovery] PubMed failed: {exc}")

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
            oa_papers = await search_works(query=query, per_page=PER_SOURCE_LIMIT, open_access_only=True)
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


def _source_key(source: Dict[str, Any]) -> Optional[str]:
    doi = _clean_identifier(source.get("doi"))
    title = _normalize_title(source.get("title") or source.get("document_title"))
    url = source.get("url") or source.get("paper_url") or source.get("pdf_url")
    document_id = source.get("document_id")
    if document_id:
        return f"document:{document_id}"
    if doi:
        return f"doi:{doi.lower()}"
    if url:
        return f"url:{url}"
    if title:
        return f"title:{title}"
    return None


def _deduplicate_sources(sources: List[Dict[str, Any]], limit: int = 3) -> List[Dict[str, Any]]:
    seen: set[str] = set()
    deduped: List[Dict[str, Any]] = []
    for source in sorted(sources, key=lambda s: float(s.get("similarity") or s.get("relevance_score") or 0.0), reverse=True):
        key = _source_key(source)
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(source)
        if len(deduped) >= limit:
            break
    return deduped


def _task_source_payload(source: Dict[str, Any]) -> Dict[str, Any]:
    title = source.get("document_title") or source.get("title")
    return {
        "document_id": source.get("document_id") or source.get("shared_paper_id"),
        "document_title": title,
        "title": title,
        "display": source.get("display") or _format_source_display(source),
        "content": source.get("content") or source.get("abstract") or "",
        "similarity": source.get("similarity") or source.get("relevance_score") or 0.0,
        "source": source.get("source", "library"),
        "doi": source.get("doi"),
        "url": source.get("url") or source.get("paper_url") or source.get("pdf_url"),
        "recommendation_id": source.get("recommendation_id"),
        "shared_paper_id": source.get("shared_paper_id"),
    }


def _normalize_internal_task_source(chunk: Dict[str, Any], target: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    title = (
        chunk.get("document_title")
        or chunk.get("source_title")
        or chunk.get("title")
        or ""
    )
    content = (chunk.get("content") or "").strip()
    similarity = float(chunk.get("similarity") or chunk.get("combined_score") or 0.0)
    if not title or title.strip().lower() in {"unknown", "untitled", "untitled document"}:
        return None
    if similarity < MIN_INTERNAL_TASK_SOURCE_SIMILARITY:
        return None
    if not content:
        return None

    query_terms = set(_meaningful_terms(target.get("search_query") or target.get("text") or ""))
    source_text = f"{title} {content}".lower()
    matched_terms = sorted(term for term in query_terms if term in source_text)
    if len(matched_terms) < 2:
        return None
    if not _passes_domain_gate(
        target.get("search_query") or target.get("text") or "",
        source_text,
        similarity,
        target.get("manuscript_profile") or {},
    ):
        return None

    return {
        "document_id": chunk.get("document_id"),
        "document_title": title,
        "title": title,
        "display": chunk.get("display") or f"{title} · Library",
        "content": content,
        "similarity": round(similarity, 3),
        "source": "library",
        "doi": chunk.get("doi"),
        "url": chunk.get("url") or chunk.get("paper_url") or chunk.get("pdf_url"),
        "matched_keywords": matched_terms[:8],
    }


async def _fetch_internal_sources_for_task(
    project_id: str,
    target: Dict[str, Any],
    *,
    limit: int = 6,
) -> List[Dict[str, Any]]:
    try:
        from app.services.rag_retrieval import retrieve_relevant_chunks

        chunks = await asyncio.to_thread(
            retrieve_relevant_chunks,
            project_id,
            target["search_query"],
            limit,
            None,
            MIN_INTERNAL_TASK_SOURCE_SIMILARITY,
        )
    except Exception as exc:
        logger.warning(f"[DraftExternalDiscovery] Internal task-source search failed: {exc}")
        return []

    sources = []
    for chunk in chunks or []:
        normalized = _normalize_internal_task_source(chunk, target)
        if normalized:
            sources.append(normalized)
    return sources


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
                "doi": source.get("doi"),
                "content": source.get("abstract") or "",
                "relevance_score": source.get("relevance_score", 0.0),
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
    if source.get("source") == "semantic_scholar":
        source_label = "Semantic Scholar"
    elif source.get("source") == "pubmed":
        source_label = "PubMed"
    else:
        source_label = "OpenAlex"

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
    resolved_references: Optional[List[Dict[str, Any]]] = None,
    manuscript_profile: Optional[Dict[str, Any]] = None,
    min_candidates: int = MIN_CANDIDATES,
    max_candidates: int = MAX_CANDIDATES,
) -> List[Dict[str, Any]]:
    """
    Discover external papers for draft analysis via two paths:
    1. Keyword-based (Semantic Scholar / PubMed / OpenAlex) for weak claims + gaps.
    2. Citation-graph (OpenAlex co-citation) using the draft's own bibliography.

    Returns normalized external_source records for the citation judge + reviewer panel.
    """
    if not draft_id or not project_id or not user_id:
        return []

    targets = _select_targets(draft_id, claims_with_citations, coverage_gaps)

    # ── Stage 1: keyword-based search ────────────────────────────────────────
    logger.info(
        "[DraftExternalDiscovery] Stage 1: %d targets selected for keyword search",
        len(targets),
    )

    all_candidates: List[Dict[str, Any]] = []
    for target in targets:
        new = await _fetch_candidates_for_target(target)
        all_candidates.extend(new)
        if len(_deduplicate_candidates(all_candidates)) >= min_candidates:
            break

    candidates = _deduplicate_candidates(all_candidates)[:max_candidates]
    logger.info(
        "[DraftExternalDiscovery] Stage 2: %d candidates after keyword search + dedup",
        len(candidates),
    )

    existing_keys = (
        _load_existing_recommendation_keys(project_id, user_id)
        if PERSIST_DRAFT_EXTERNAL_RECOMMENDATIONS
        else {}
    )
    external_sources: List[Dict[str, Any]] = []

    for candidate in candidates:
        if not PERSIST_DRAFT_EXTERNAL_RECOMMENDATIONS:
            external_sources.append(_external_source_record(candidate, None, None))
            continue
        recommendation_id = _store_recommendation(project_id, user_id, candidate, existing_keys)
        if recommendation_id:
            external_sources.append(
                _external_source_record(candidate, None, recommendation_id)
            )

    keyword_count = len(external_sources)
    logger.info(
        "[DraftExternalDiscovery] Stage 2 complete: %d keyword-based sources",
        keyword_count,
    )

    # ── Stage 3: citation-graph discovery ────────────────────────────────────
    graph_count = 0
    if resolved_references:
        try:
            graph_papers = await _fetch_citation_graph_candidates(resolved_references)
            logger.info(
                "[DraftExternalDiscovery] Stage 3 (citation-graph): %d co-cited papers before dedup",
                len(graph_papers),
            )
            seen_keys = {_source_key(s) for s in external_sources if _source_key(s)}
            for paper in graph_papers:
                if not paper.get("title"):
                    continue
                src = _citation_graph_to_external_source(paper, draft_id)
                key = _source_key(src)
                if key and key in seen_keys:
                    continue
                if key:
                    seen_keys.add(key)
                external_sources.append(src)
                graph_count += 1
        except Exception as exc:
            logger.warning(
                "[DraftExternalDiscovery] Citation-graph discovery failed (non-fatal): %s", exc
            )

    logger.info(
        "[DraftExternalDiscovery] Stage 3 complete: %d graph sources added "
        "(total pre-judge: %d = %d keyword + %d graph)",
        graph_count, len(external_sources), keyword_count, graph_count,
    )
    return external_sources


async def enrich_revision_tasks_with_sources(
    *,
    draft_id: str,
    project_id: str,
    user_id: str,
    revision_tasks: List[Dict[str, Any]],
    manuscript_profile: Dict[str, Any] | None = None,
    max_targets: int = 8,
    max_sources_per_task: int = 3,
) -> List[Dict[str, Any]]:
    """
    Attach vetted internal/external sources to durable revision tasks.

    This is deliberately task-level rather than claim-only, so literature
    positioning and methodology tasks can show useful supporting papers even
    when no extracted claim requires a missing-citation fix.
    """
    if not draft_id or not project_id or not user_id or not revision_tasks:
        return revision_tasks

    targets = _select_task_targets(
        draft_id,
        revision_tasks,
        max_targets=max_targets,
        manuscript_profile=manuscript_profile,
    )
    if not targets:
        logger.info("[DraftExternalDiscovery] No revision tasks eligible for source surfacing")
        return revision_tasks

    sources_by_task: Dict[str, List[Dict[str, Any]]] = {}
    status_by_task: Dict[str, str] = {}
    for target in targets:
        task_sources: List[Dict[str, Any]] = []

        internal_sources = await _fetch_internal_sources_for_task(project_id, target)
        task_sources.extend(_task_source_payload(source) for source in internal_sources)

        if not task_sources:
            candidates = _deduplicate_candidates(await _fetch_candidates_for_target(target))
            task_sources.extend(
                _task_source_payload(_external_source_record(candidate, None, None))
                for candidate in candidates
            )

        if task_sources:
            sources_by_task[target["target_id"]] = _deduplicate_sources(
                task_sources,
                limit=max_sources_per_task,
            )
            status_by_task[target["target_id"]] = "found"
        else:
            status_by_task[target["target_id"]] = "no_results"

    enriched: List[Dict[str, Any]] = []
    for task in revision_tasks:
        task_copy = dict(task)
        task_sources = sources_by_task.get(task.get("id")) or []
        if task_sources:
            existing = task_copy.get("suggested_sources") or []
            task_copy["suggested_sources"] = _deduplicate_sources(
                list(existing) + task_sources,
                limit=max_sources_per_task,
            )
            task_copy["source_search_status"] = "found"
        elif task.get("id") in status_by_task:
            task_copy["source_search_status"] = status_by_task[task.get("id")]
        enriched.append(task_copy)

    logger.info(
        "[DraftExternalDiscovery] Added task-level sources to %s/%s eligible revision tasks",
        sum(1 for task in enriched if task.get("suggested_sources")),
        len(targets),
    )
    return enriched

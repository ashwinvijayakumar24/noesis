"""
Citation Mapping Node

Maps found literature to specific claims and assesses citation quality.
Uses parallel processing for significant speedup (30-60s → 5-10s).

B2: After citation quality assessment, discovers papers (library + Semantic Scholar)
for top weak/none claims and stores them as suggested_citations.
"""

from app.workflows.draft_analysis.state import DraftAnalysisState, ClaimWithCitation
from app.core.logging_config import get_logger
from app.core.openai_client import get_openai_client, get_completion_params
import json
import asyncio

logger = get_logger(__name__)

# Initialize OpenAI client
client = get_openai_client()


CITATION_QUALITY_PROMPT = """You are an expert academic reviewer. Assess the quality of citations for a research claim.

Given:
1. A claim from a research draft
2. Literature found that potentially supports this claim

Assess each citation's quality as:
- "strong": Directly validates the claim with clear evidence
- "moderate": Partially validates or provides related evidence
- "weak": Tangentially related or only provides context
- "contradicts": Actually contradicts the claim (important!)

Also identify any gaps:
- What specific evidence is missing?
- What perspectives are not covered?
- What baselines or comparisons are absent?

Return ONLY a valid JSON object:
{
  "overall_quality": "strong" | "moderate" | "weak" | "none",
  "citations": [
    {
      "document_id": "id",
      "document_title": "title",
      "relevance": "strong" | "moderate" | "weak" | "contradicts",
      "reasoning": "Why this citation quality assessment"
    }
  ],
  "gaps": [
    "Specific gap 1",
    "Specific gap 2"
  ],
  "recommendation": "What the author should do"
}
"""


async def assess_citation_quality(
    claim: dict,
    literature_results: list
) -> dict:
    """
    Assess the quality of citations for a claim using GPT.

    Args:
        claim: The claim dictionary
        literature_results: Literature search results for this claim

    Returns:
        Citation quality assessment
    """
    try:
        context = f"""
Claim: {claim['claim_text']}
Claim Type: {claim['claim_type']}
Importance: {claim['importance_score']}

Found Literature:
"""
        for i, result in enumerate(literature_results[:5]):  # Top 5 results
            context += f"""
{i+1}. Document: {result.get('document_title', 'Unknown')}
   Content: {result.get('content', '')[:500]}...
   Similarity: {result.get('similarity', 'N/A')}
"""

        response = client.chat.completions.create(
            model="gpt-5.2-chat-latest",
            messages=[
                {"role": "system", "content": CITATION_QUALITY_PROMPT},
                {"role": "user", "content": context}
            ],
            max_completion_tokens=800,
            **get_completion_params()
        )

        return json.loads(response.choices[0].message.content)

    except Exception as e:
        logger.error(f"[Citation Quality] Error assessing quality: {e}")
        return {
            "overall_quality": "unknown",
            "citations": [],
            "gaps": [],
            "recommendation": "Manual review needed"
        }


async def _process_single_claim_citation(search_result: dict) -> ClaimWithCitation:
    """Process a single claim's citation quality asynchronously."""
    claim = search_result['claim']
    results = search_result.get('results', [])

    if not results:
        return {
            'claim': claim,
            'citations': [],
            'citation_quality': 'none',
            'gaps': ['No supporting literature found in your library'],
            'suggested_citations': []
        }

    quality_assessment = await assess_citation_quality(claim, results)

    return {
        'claim': claim,
        'citations': results,
        'citation_quality': quality_assessment.get('overall_quality', 'unknown'),
        'gaps': quality_assessment.get('gaps', []),
        'suggested_citations': []
    }


def _format_paper_chip(p: dict, source_label: str) -> dict:
    """Convert a paper dict to citation chip format."""
    _bad_year = {"Unknown", "unknown", "n.d.", "", None}
    authors = p.get("authors", [])
    year = p.get("year")

    first_author = ""
    if authors:
        a = str(authors[0])
        first_author = (a.split(",")[0] if "," in a else a).strip()

    year_clean = str(year) if year and str(year) not in _bad_year else None
    title_str = (p.get("title") or "")[:50]

    if first_author:
        author_str = f"{first_author} et al." if len(authors) > 1 else first_author
        display = f"{author_str} ({year_clean}) · {source_label}" if year_clean else f"{author_str} · {source_label}"
    else:
        display = f"{title_str} · {source_label}" if title_str else f"[Untitled] · {source_label}"

    return {
        "title": p.get("title", ""),
        "authors": authors,
        "year": year,
        "display": display,
        "url": p.get("url") or p.get("pdf_url") or p.get("open_access_url"),
    }


async def _discover_papers_for_claim(claim_text: str, project_id: str) -> list:
    """
    B2: Discover papers from project library and Semantic Scholar for a weak/unsupported claim.

    Flow:
    1. Check shared_papers global DB (semantic search — no external API call)
    2. Fall back to suggest_papers_for_gaps() (library + Semantic Scholar)
    3. Store any new external results back into shared_papers for future reuse

    Args:
        claim_text: The claim text to search for
        project_id: Project ID for library search

    Returns:
        List of suggested_citation dicts with display, source, title, authors, year
    """
    try:
        # 1. Check shared_papers global cache first
        from app.services.shared_paper_cache import find_similar_papers, store_paper
        cached = await find_similar_papers(claim_text, limit=3, similarity_threshold=0.55)
        if cached:
            logger.info(f"[Citation Mapping] Using shared_papers cache ({len(cached)} hits) for claim")
            return [
                {**_format_paper_chip(p, "Global library"), "source": "global_library"}
                for p in cached
            ]

        # 2. External fallback via project library + Semantic Scholar
        from app.services.coverage_analysis import suggest_papers_for_gaps
        mock_gap = {"description": claim_text, "suggested_papers": []}
        enriched = await suggest_papers_for_gaps([mock_gap], project_id, max_suggestions_per_gap=3)
        papers = enriched[0].get("suggested_papers", []) if enriched else []

        result = []
        for p in papers[:3]:
            source = "library" if p.get("document_id") else "semantic_scholar"
            source_label = "In your library" if source == "library" else "Semantic Scholar"
            chip = _format_paper_chip(p, source_label)
            chip["source"] = source
            chip["document_id"] = p.get("document_id")
            result.append(chip)

        # 3. Store external (non-library) results in shared_papers (fire-and-forget)
        for p in papers:
            if not p.get("document_id") and (p.get("title") or p.get("doi") or p.get("arxiv_id")):
                asyncio.create_task(store_paper({
                    "title": p.get("title", ""),
                    "authors": p.get("authors", []),
                    "year": p.get("year"),
                    "abstract": p.get("abstract", ""),
                    "arxiv_id": p.get("arxiv_id"),
                    "doi": p.get("doi"),
                    "pdf_url": p.get("url") or p.get("open_access_url"),
                    "source": p.get("source", "semantic_scholar"),
                }))

        return result

    except Exception as e:
        logger.warning(f"[Citation Mapping] Paper discovery failed for claim: {e}")
        return []


async def citation_mapping_node(state: DraftAnalysisState) -> DraftAnalysisState:
    """
    Map literature to claims and assess citation quality.

    Phase 1: Parallel citation quality assessment for all claims.
    Phase 2 (B2): Discover papers for top weak/none high-importance claims.

    Args:
        state: Current workflow state

    Returns:
        Updated state with citation mappings, quality assessments, and suggested_citations
    """
    logger.info(f"[Citation Mapping] Starting for draft_id={state['draft_id']}")

    search_results = state.get("literature_search_results", [])

    if not search_results:
        logger.warning("[Citation Mapping] No search results to map")
        return {
            'claims_with_citations': [],
            'current_step': 'Citation Mapping (No Results)',
            'progress_percentage': 60
        }

    try:
        # ── Phase 1: Parallel citation quality assessment ──
        logger.info(f"[Citation Mapping] Phase 1: PARALLEL assessment of {len(search_results)} claims...")

        tasks = [_process_single_claim_citation(sr) for sr in search_results]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        claims_with_citations: list[ClaimWithCitation] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning(f"[Citation Mapping] Assessment {i} failed: {result}")
                claim = search_results[i]['claim']
                claims_with_citations.append({
                    'claim': claim,
                    'citations': search_results[i].get('results', []),
                    'citation_quality': 'unknown',
                    'gaps': [],
                    'suggested_citations': []
                })
            else:
                claims_with_citations.append(result)

        quality_counts = {
            'strong': sum(1 for c in claims_with_citations if c.get('citation_quality') == 'strong'),
            'moderate': sum(1 for c in claims_with_citations if c.get('citation_quality') == 'moderate'),
            'weak': sum(1 for c in claims_with_citations if c.get('citation_quality') == 'weak'),
            'none': sum(1 for c in claims_with_citations if c.get('citation_quality') == 'none')
        }

        logger.info(
            f"[Citation Mapping] Phase 1 complete: "
            f"strong={quality_counts['strong']}, moderate={quality_counts['moderate']}, "
            f"weak={quality_counts['weak']}, none={quality_counts['none']}"
        )

        # ── Phase 2 (B2): Discover papers for top weak/none high-importance claims ──
        project_id = state.get("project_id", "")
        if project_id:
            # Select top 5 weak/none claims by importance score
            discovery_candidates = [
                cwc for cwc in claims_with_citations
                if cwc.get('citation_quality') in ['none', 'weak']
                and cwc.get('claim', {}).get('importance_score', 0) >= 0.6
            ]
            discovery_candidates.sort(
                key=lambda c: c.get('claim', {}).get('importance_score', 0),
                reverse=True
            )
            top_candidates = discovery_candidates[:10]

            if top_candidates:
                logger.info(
                    f"[Citation Mapping] Phase 2: Discovering papers for "
                    f"{len(top_candidates)} weak/none high-importance claims..."
                )

                try:
                    disc_tasks = [
                        _discover_papers_for_claim(
                            cwc['claim']['claim_text'],
                            project_id
                        )
                        for cwc in top_candidates
                    ]
                    discovery_results = await asyncio.gather(*disc_tasks, return_exceptions=True)
                    discovered_count = 0
                    for cwc, disc_result in zip(top_candidates, discovery_results):
                        if not isinstance(disc_result, Exception) and disc_result:
                            cwc['suggested_citations'] = disc_result
                            discovered_count += 1
                    logger.info(
                        f"[Citation Mapping] Phase 2 complete: "
                        f"discovered papers for {discovered_count}/{len(top_candidates)} claims"
                    )
                except Exception as e:
                    logger.warning(f"[Citation Mapping] Phase 2 discovery failed (non-fatal): {e}")
            else:
                logger.info("[Citation Mapping] Phase 2: No weak/none high-importance claims to discover for")

        return {
            'claims_with_citations': claims_with_citations,
            'current_step': 'Citation Mapping',
            'progress_percentage': 60
        }

    except Exception as e:
        logger.error(f"[Citation Mapping] Error: {e}")
        errors = state.get('errors', [])
        errors.append(f"Citation mapping failed: {str(e)}")

        return {
            'claims_with_citations': [],
            'errors': errors,
            'current_step': 'Citation Mapping (Failed)',
            'progress_percentage': 60
        }

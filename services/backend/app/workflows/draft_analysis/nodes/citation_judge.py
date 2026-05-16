"""
Citation Judge Node

Runs after discover_external_sources, before structural_checks.

Judges:
  1. suggested_citations per claim — is this paper genuinely relevant to THIS specific claim,
     or is it a keyword-match false positive?
  2. external_sources — does this source address a named gap/claim, or is it noise?

Low-relevance items (keep=False) are filtered from state before the reviewer panel
sees them, so the coverage reviewer's context is already clean.

Judge verdicts are stored in analysis_metadata for frontend quality indicators.
"""

from __future__ import annotations

import json

from app.workflows.draft_analysis.state import DraftAnalysisState
from app.workflows.draft_analysis.schemas import CitationJudgeOutput
from app.core.logging_config import get_logger
from app.core.openai_client import get_async_openai_client, get_completion_params
from app.services.retry_utils import parse_chat_completion_with_retries

logger = get_logger(__name__)
client = None


def _get_client():
    global client
    if client is None:
        client = get_async_openai_client()
    return client

CITATION_JUDGE_PROMPT = """You are a senior academic editor judging the quality of citation and source suggestions.

You are given:
- A list of (claim, suggested_citation) pairs: citations suggested for unsupported claims
- A list of external sources discovered to address literature gaps

Your job: determine which suggestions are genuinely useful vs. superficial keyword matches.

KEEP a suggested_citation if:
- The paper directly addresses the specific claim (not just the same broad topic)
- It provides evidence, methodology, or theoretical grounding the claim needs
- A reviewer would cite it as "you should cite X here"

REJECT a suggested_citation if:
- It matches on keywords but doesn't address the claim's actual content
- It is a general survey/review when a specific empirical paper is needed
- It would be weird to cite it for this specific claim

KEEP an external_source if:
- It directly fills the named gap (missing baseline, missing perspective, conflicting evidence)
- A coverage reviewer would specifically name it as "you missed this paper"

REJECT an external_source if:
- It is tangentially related to the topic but doesn't address the gap
- It duplicates a paper already in the author's library
- The gap description and source are only loosely connected

Be strict. A relevance_score below 0.5 should almost always be keep=False.
Return verdicts for every item provided."""


def _build_judge_context(state: DraftAnalysisState) -> tuple[str, list[dict], list[dict]]:
    """
    Build judge context. Returns (context_str, citation_items, external_items)
    so we can match verdicts back to original objects.
    """
    claims_with_citations = state.get("claims_with_citations") or []
    external_sources = state.get("external_sources") or []

    citation_items: list[dict] = []
    lines = ["=== SUGGESTED CITATIONS (claim → suggested paper) ===\n"]

    for cwc in claims_with_citations:
        claim = cwc.get("claim") or {}
        claim_text = str(claim.get("claim_text", ""))[:80]
        for sc in cwc.get("suggested_citations") or []:
            title = sc.get("title") or sc.get("display") or "Untitled"
            citation_items.append({"claim_text_snippet": claim_text, "citation_title": title, "obj": sc, "cwc": cwc})
            lines.append(f"CLAIM: {claim_text}")
            lines.append(f"  SUGGESTED: {title}")
            lines.append(f"  SOURCE: {sc.get('source', 'unknown')}\n")

    lines.append("\n=== EXTERNAL SOURCES (gap/claim → external paper) ===\n")
    external_items: list[dict] = []

    for src in external_sources:
        title = src.get("title") or src.get("document_title") or "Untitled"
        gap_desc = str(src.get("gap_description") or src.get("claim_text") or "")[:80]
        external_items.append({"source_title": title, "supports_which": gap_desc, "obj": src})
        lines.append(f"GAP/CLAIM: {gap_desc}")
        lines.append(f"  SOURCE: {title}\n")

    return "\n".join(lines), citation_items, external_items


def _apply_verdicts(
    state: DraftAnalysisState,
    output: CitationJudgeOutput,
    citation_items: list[dict],
    external_items: list[dict],
) -> tuple[list, list]:
    """
    Apply judge verdicts to filter claims_with_citations and external_sources.
    Returns (filtered_claims_with_citations, filtered_external_sources).
    """
    # Build lookup: (claim_snippet, title) → verdict
    citation_lookup: dict[tuple[str, str], bool] = {}
    for v in output.citation_verdicts:
        key = (v.claim_text_snippet[:80], v.citation_title)
        citation_lookup[key] = v.keep

    external_lookup: dict[str, bool] = {}
    for v in output.external_source_verdicts:
        external_lookup[v.source_title] = v.keep

    # Filter suggested_citations per claim
    claims_with_citations = state.get("claims_with_citations") or []
    filtered_cwc = []
    removed_citations = 0
    for cwc in claims_with_citations:
        claim = cwc.get("claim") or {}
        claim_snippet = str(claim.get("claim_text", ""))[:80]
        suggested = cwc.get("suggested_citations") or []
        kept = []
        for sc in suggested:
            title = sc.get("title") or sc.get("display") or "Untitled"
            key = (claim_snippet, title)
            # If no verdict, default keep=True
            if citation_lookup.get(key, True):
                kept.append(sc)
            else:
                removed_citations += 1
        new_cwc = dict(cwc)
        new_cwc["suggested_citations"] = kept
        filtered_cwc.append(new_cwc)

    # Filter external_sources
    external_sources = state.get("external_sources") or []
    filtered_ext = []
    removed_sources = 0
    for src in external_sources:
        title = src.get("title") or src.get("document_title") or "Untitled"
        if external_lookup.get(title, True):
            filtered_ext.append(src)
        else:
            removed_sources += 1

    logger.info(
        f"[CitationJudge] Filtered: {removed_citations} suggested citations, "
        f"{removed_sources} external sources removed"
    )
    return filtered_cwc, filtered_ext


async def citation_judge_node(state: DraftAnalysisState) -> dict:
    """
    Judge quality of suggested citations and external sources.
    Filters low-relevance items from state before reviewer panel sees them.
    """
    draft_id = state.get("draft_id", "")
    logger.info(f"[CitationJudge] Starting for draft_id={draft_id}")

    context_str, citation_items, external_items = _build_judge_context(state)

    # Nothing to judge
    if not citation_items and not external_items:
        logger.info("[CitationJudge] No suggested citations or external sources — skipping")
        return {
            "citation_judge_output": {"overall_citation_quality": "low", "citation_verdicts": [], "external_source_verdicts": []},
            "current_step": "Citation Judge (Skipped — nothing to judge)",
            "progress_percentage": 77,
        }

    try:
        response = await parse_chat_completion_with_retries(
            _get_client(),
            model="gpt-5.2-chat-latest",
            messages=[
                {"role": "system", "content": CITATION_JUDGE_PROMPT},
                {"role": "user", "content": context_str[:6000]},  # cap context
            ],
            max_completion_tokens=1500,
            response_format=CitationJudgeOutput,
            **get_completion_params(),
        )

        output = response.parsed

        filtered_cwc, filtered_ext = _apply_verdicts(state, output, citation_items, external_items)

        judge_dict = output.model_dump()
        # Strip obj refs — already used for filtering
        logger.info(
            f"[CitationJudge] Complete: quality={output.overall_citation_quality}, "
            f"citation_verdicts={len(output.citation_verdicts)}, "
            f"external_verdicts={len(output.external_source_verdicts)}"
        )

        return {
            "claims_with_citations": filtered_cwc,
            "external_sources": filtered_ext,
            "citation_judge_output": judge_dict,
            "current_step": "Citation Judge",
            "progress_percentage": 77,
        }

    except Exception as exc:
        logger.warning(f"[CitationJudge] Failed (non-fatal, passing through unfiltered): {exc}")
        return {
            "citation_judge_output": {"error": str(exc), "overall_citation_quality": "medium"},
            "current_step": "Citation Judge (Failed)",
            "progress_percentage": 77,
        }

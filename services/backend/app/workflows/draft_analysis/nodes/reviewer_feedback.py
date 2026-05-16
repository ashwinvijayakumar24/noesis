"""
Reviewer Feedback Generation Node

Generates expert academic reviewer-style feedback based on the analysis.
B1: Evidence-grounded per-claim context — passes per-claim citation quality,
specific papers found, and specific gaps to GPT so feedback names exact claims.
B4: Hard output constraints to prevent generic advice.
"""

from app.workflows.draft_analysis.state import DraftAnalysisState, Feedback
from app.workflows.draft_analysis.schemas import ReviewerFeedbackOutput
from app.core.logging_config import get_logger
from app.core.supabase_client import supabase
from app.core.openai_client import get_openai_client, get_completion_params
from app.services.draft_anchor_qa import attach_feedback_qa, select_failed_feedback_for_retry
from app.services.retry_utils import parse_chat_completion_with_retries_sync
import json

logger = get_logger(__name__)

client = None


def _get_client():
    global client
    if client is None:
        client = get_openai_client()
    return client


# B4: Hard constraints added to require specific, anchored feedback
REVIEWER_FEEDBACK_PROMPT = """You are an expert academic reviewer providing constructive feedback on a research draft.

You have been given:
1. The draft structure
2. A DETAILED PER-CLAIM ANALYSIS showing exactly which claims are weak, unsupported, or problematic
3. The specific papers found (or not found) for each claim

Based on this analysis, generate reviewer feedback that:
1. Identifies strengths — factual observations about what is done well
2. Identifies weaknesses — each weakness must anchor to a SPECIFIC CLAIM from the analysis
3. Asks clarifying questions — each question must reference a SPECIFIC CLAIM or section
4. Suggests specific improvements — name the specific paper that would fix the issue

REQUIRED OUTPUT RULES (violations will cause this feedback to be useless):
- Every weakness MUST quote or paraphrase a specific claim from the "DETAILED CLAIM ANALYSIS" section
- Every suggestion MUST name a specific paper when literature is available (e.g., "add McMahan et al. (2017) to support Claim 1")
- Every question MUST identify which claim or section it addresses
- DO NOT write generic advice like "consider adding more citations" — always anchor to the specific claim
- Strengths must be factual (e.g., "§3 correctly specifies ε=1.0 differential privacy budget") not vague meta-praise ("the structure is clear")
- If a claim has citation_quality NONE and suggested papers exist — name those papers in the weakness

Return ONLY a valid JSON object:
{
  "feedback_items": [
    {
      "feedback_type": "strength" | "weakness" | "question" | "suggestion",
      "feedback_text": "Specific feedback referencing the exact claim and/or paper by name",
      "severity": "critical" | "major" | "minor" | "suggestion",
      "section_reference": "Section name (e.g., Results, Introduction)",
      "target_claim_id": "Exact claim ID from the DETAILED CLAIM ANALYSIS, or null",
      "target_gap_id": "Exact gap ID from CRITICAL COVERAGE GAPS, or null",
      "specific_issue": "One concrete issue tied to the target claim/gap; empty only for strengths",
      "suggested_improvements": ["Concrete action 1", "Concrete action 2"],
      "cited_papers": ["Paper title 1", "Paper title 2"]
    }
  ],
  "overall_assessment": "Brief overall assessment",
  "priority_actions": [
    "Action 1: Fix [specific claim] by adding [specific paper]",
    "Action 2: ...",
    "Action 3: ..."
  ]
}

Severity levels:
- "critical": Must be fixed before publication
- "major": Should be addressed for significant improvement
- "minor": Optional improvements
- "suggestion": General enhancement suggestions
"""


def _build_literature_context(search_results: list) -> str:
    """
    Build a retrieved-literature context string from literature search results.

    Deduplicates papers by title (same paper may appear in multiple claim searches)
    and caps at 5 papers to keep context focused.

    Args:
        search_results: List of {claim_id, results: [{document_title, content, ...}]}

    Returns:
        Formatted string listing retrieved papers, or "" if none.
    """
    if not search_results:
        return ""

    seen_titles: set = set()
    papers: list = []

    for result in search_results:
        for paper in result.get("results", []):
            title = paper.get("document_title") or paper.get("title") or ""
            if title and title not in seen_titles:
                seen_titles.add(title)
                papers.append(paper)
                if len(papers) >= 5:
                    break
        if len(papers) >= 5:
            break

    if not papers:
        return ""

    lines = ["RETRIEVED LITERATURE:"]
    for paper in papers:
        title = paper.get("document_title") or paper.get("title") or "Unknown"
        authors = paper.get("authors", "")
        year = paper.get("year", "")
        content = (paper.get("content") or "")[:200]

        line = f"- {title}"
        if authors or year:
            meta = ", ".join(filter(None, [authors, str(year) if year else ""]))
            line += f" ({meta})"
        if content:
            line += f": {content}"
        lines.append(line)

    return "\n".join(lines)


def _format_external_sources_for_context(sources: list, limit: int = 3) -> str:
    if not sources:
        return ""

    paper_strs = []
    for source in sources[:limit]:
        title = source.get("title") or "Unknown"
        authors = source.get("authors") or []
        first_author = authors[0] if authors else ""
        year = source.get("year")
        if first_author and year:
            paper_strs.append(f"{title} ({first_author} et al., {year})")
        elif year:
            paper_strs.append(f"{title} ({year})")
        else:
            paper_strs.append(title)

    return "; ".join(paper_strs)


def _best_source_grounding_for_claim(cwc: dict) -> dict | None:
    """Build a stable source_grounding payload from the best uploaded-literature match."""
    citations = cwc.get("citations") or []
    if not citations:
        return None

    best = max(citations, key=lambda c: float(c.get("similarity", 0) or 0))
    document_id = best.get("document_id")
    title = best.get("document_title") or best.get("title")
    if not document_id and not title:
        return None

    return {
        "document_id": document_id,
        "document_title": title,
        "title": title,
        "excerpt": best.get("content", ""),
        "similarity": best.get("similarity", 0.0),
        "chunk_index": best.get("chunk_index"),
        "section": best.get("section", ""),
        "source": "uploaded_literature",
    }


def _attach_source_grounding_to_feedback(
    feedback_items: list[dict],
    claims_with_citations: list[dict],
) -> list[dict]:
    """Attach best uploaded-literature grounding to feedback items with target_claim_id."""
    grounding_by_claim_id = {}
    for cwc in claims_with_citations or []:
        claim = cwc.get("claim") or {}
        claim_id = claim.get("id")
        grounding = _best_source_grounding_for_claim(cwc)
        if claim_id and grounding:
            grounding_by_claim_id[str(claim_id)] = grounding

    for feedback in feedback_items:
        if feedback.get("source_grounding"):
            continue
        target_claim_id = feedback.get("target_claim_id")
        if target_claim_id and str(target_claim_id) in grounding_by_claim_id:
            feedback["source_grounding"] = grounding_by_claim_id[str(target_claim_id)]

    return feedback_items


def _build_per_claim_context(
    claims_with_citations: list,
    coverage_gaps: list,
    structure: dict
) -> str:
    """
    B1: Build a per-claim context string for GPT.

    Instead of aggregate counts ("3 strong, 4 weak"), passes the actual
    claim text, section, citation quality, papers found, and specific gaps
    so GPT can produce specific, anchored feedback.

    Only includes HIGH and MEDIUM importance claims (importance >= 0.5)
    to keep context focused. Sorted by importance descending.
    """
    if not claims_with_citations:
        return ""

    # Filter to high/medium importance and sort by importance desc
    relevant = [
        cwc for cwc in claims_with_citations
        if cwc.get('claim', {}).get('importance_score', 0) >= 0.5
    ]
    relevant.sort(key=lambda cwc: cwc.get('claim', {}).get('importance_score', 0), reverse=True)
    relevant = relevant[:15]  # Cap at 15 to avoid context overflow

    if not relevant:
        return ""

    lines = ["DETAILED CLAIM ANALYSIS (sorted by importance):"]
    lines.append("")

    # Build a map from claim_id to gap descriptions for cross-referencing
    claim_gap_map: dict = {}
    for gap in coverage_gaps:
        for claim_id in gap.get('affected_claims', []):
            if claim_id not in claim_gap_map:
                claim_gap_map[claim_id] = []
            claim_gap_map[claim_id].append(gap.get('description', ''))

    for i, cwc in enumerate(relevant, 1):
        claim = cwc.get('claim', {})
        quality = cwc.get('citation_quality', 'unknown')
        citations = cwc.get('citations', [])
        gaps = cwc.get('gaps', [])
        claim_id = claim.get('id', '')

        claim_text = claim.get('claim_text', '')
        section = claim.get('section_location', 'Unknown')
        importance = claim.get('importance_score', 0)
        claim_type = claim.get('claim_type', 'unknown')

        # Citation quality display
        quality_label = {
            'strong': 'STRONG ✓',
            'moderate': 'MODERATE (adequate but could be stronger)',
            'weak': 'WEAK (tangential support only)',
            'none': 'NONE — no supporting papers found',
            'unknown': 'UNKNOWN',
        }.get(quality, quality.upper())

        lines.append(f"Claim {i} [target_claim_id={claim_id}]: \"{claim_text[:120]}{'...' if len(claim_text) > 120 else ''}\"")
        lines.append(f"  Section: {section}  |  Importance: {int(importance * 100)}%  |  Type: {claim_type}")
        lines.append(f"  Citation quality: {quality_label}")

        if citations:
            # Show top 3 papers found
            top_cits = citations[:3]
            paper_strs = []
            for c in top_cits:
                title = c.get('document_title', c.get('title', 'Unknown'))
                sim = c.get('similarity', 0)
                paper_strs.append(f"{title} ({int(sim * 100)}% match)")
            lines.append(f"  Library papers found: {'; '.join(paper_strs)}")
        else:
            lines.append("  Library papers found: NONE")

        external_sources = cwc.get("external_sources") or cwc.get("suggested_citations") or []
        external_source_context = _format_external_sources_for_context(external_sources)
        if external_source_context:
            lines.append(f"  External sources found: {external_source_context}")

        # Specific gaps identified during citation quality assessment
        gap_lines = gaps[:2] if gaps else []
        # Also pull from coverage_gaps cross-reference
        cross_gaps = claim_gap_map.get(claim_id, [])[:1]
        all_gaps = gap_lines + [g for g in cross_gaps if g not in gap_lines]

        if all_gaps:
            lines.append(f"  Specific gap: {'; '.join(all_gaps[:2])}")

        # Action hint for GPT
        if quality == 'none':
            lines.append("  → NEEDS: citation or evidence (critical gap if high importance)")
        elif quality == 'weak':
            lines.append("  → NEEDS: stronger/more direct citation support")
        elif quality == 'strong':
            lines.append("  → Well-supported, may note as strength")

        lines.append("")

    return "\n".join(lines)


def generate_reviewer_feedback_node(state: DraftAnalysisState) -> DraftAnalysisState:
    """
    Generate expert reviewer feedback based on the complete analysis.

    B1: Passes per-claim detail (citation quality, specific papers, gaps) to GPT
    instead of aggregate counts, enabling specific anchored feedback.
    B4: Hard prompt constraints prevent generic advice.

    Args:
        state: Current workflow state

    Returns:
        Updated state with reviewer feedback
    """
    logger.info(f"[Reviewer Feedback] Starting for draft_id={state['draft_id']}")

    draft_id = state["draft_id"]

    try:
        # Skip generation if feedback already exists in DB (idempotency guard)
        existing_feedback = supabase.table("reviewer_feedback").select("*").eq("draft_id", draft_id).execute()
        if existing_feedback.data:
            logger.info(f"[Reviewer Feedback] Found cached feedback for draft_id={draft_id}, skipping generation")
            cached_items = [
                Feedback(
                    feedback_type=item.get("feedback_type", "suggestion"),
                    feedback_text=item.get("feedback_text", ""),
                    severity=item.get("severity", "minor"),
                    section_reference=item.get("section_reference"),
                )
                for item in existing_feedback.data
            ]
            return {
                "reviewer_feedback": cached_items,
                "current_step": "Reviewer Feedback (Cached)",
            }

        structure = state.get("structure", {})
        claims_with_citations = state.get("claims_with_citations", [])
        gaps = state.get("coverage_gaps", [])
        literature_search_results = state.get("literature_search_results", [])

        # B1: Build per-claim context instead of aggregate counts
        per_claim_context = _build_per_claim_context(claims_with_citations, gaps, structure)

        # Also build a retrieved-literature context from raw search results
        # (used when claims_with_citations is empty, e.g. no documents uploaded)
        literature_context = _build_literature_context(literature_search_results)

        if per_claim_context:
            logger.info(
                f"[Reviewer Feedback] Built per-claim context for "
                f"{len(claims_with_citations)} claims"
            )
        else:
            logger.warning(
                "[Reviewer Feedback] No per-claim context available — "
                "feedback will be generic (user may not have uploaded documents)"
            )

        # Build overall context
        context = f"""
DRAFT STRUCTURE:
- Word count: {structure.get('word_count', 'Unknown')}
- Has abstract: {structure.get('has_abstract', False)}
- Has introduction: {structure.get('has_introduction', False)}
- Has methods: {structure.get('has_methods', False)}
- Has results: {structure.get('has_results', False)}
- Has discussion: {structure.get('has_discussion', False)}
"""

        # B1: Per-claim context replaces aggregate counts
        if per_claim_context:
            context += f"\n{per_claim_context}\n"
        else:
            # Fallback: aggregate summary if no per-claim data
            claims = state.get("claims", [])
            quality_counts = {
                'strong': sum(1 for c in claims_with_citations if c.get('citation_quality') == 'strong'),
                'moderate': sum(1 for c in claims_with_citations if c.get('citation_quality') == 'moderate'),
                'weak': sum(1 for c in claims_with_citations if c.get('citation_quality') == 'weak'),
                'none': sum(1 for c in claims_with_citations if c.get('citation_quality') == 'none')
            }
            context += f"""
CITATION QUALITY SUMMARY (no library documents uploaded):
- Strong support: {quality_counts['strong']} claims
- Weak/no support: {quality_counts['weak'] + quality_counts['none']} claims
- Total claims: {len(claims)}
"""

        # Append retrieved literature context when available
        if literature_context:
            context += f"\n{literature_context}\n"

        # Add top coverage gaps for additional context
        critical_gaps = [g for g in gaps if g.get('severity') == 'critical']
        if critical_gaps:
            context += "\nCRITICAL COVERAGE GAPS:\n"
            gap_ids = {
                id(gap): gap.get("id") or f"gap_{gap_index}"
                for gap_index, gap in enumerate(gaps, 1)
            }
            for gap in critical_gaps[:3]:
                gap_id = gap_ids[id(gap)]
                context += f"  * [target_gap_id={gap_id}] {gap['description']}\n"
                external_source_context = _format_external_sources_for_context(
                    gap.get("external_sources") or gap.get("suggested_papers") or []
                )
                if external_source_context:
                    context += f"    External sources found: {external_source_context}\n"

        # B4: B5 token limit increased to 6000 for detailed per-claim feedback
        response = parse_chat_completion_with_retries_sync(
            _get_client(),
            model="gpt-5.2-chat-latest",
            messages=[
                {"role": "system", "content": REVIEWER_FEEDBACK_PROMPT},
                {"role": "user", "content": f"Generate reviewer feedback based on this analysis:\n\n{context}"}
            ],
            max_completion_tokens=6000,
            response_format=ReviewerFeedbackOutput,
            **get_completion_params()
        )

        result = response.parsed

        # Convert to typed Feedback objects
        feedback_items: list[Feedback] = []
        for item in result.feedback_items:
            feedback: Feedback = {
                'feedback_type': item.feedback_type,
                'feedback_text': item.feedback_text,
                'severity': item.severity,
                'section_reference': item.section_reference,
                'reviewer_persona': 'reviewer_2',
                'target_claim_id': item.target_claim_id,
                'target_gap_id': item.target_gap_id,
                'specific_issue': item.specific_issue,
                'suggestions': item.suggested_improvements,
                'suggested_improvements': item.suggested_improvements,
                'cited_papers': item.cited_papers,
            }
            feedback_items.append(feedback)

        feedback_items = _attach_source_grounding_to_feedback(
            feedback_items,
            claims_with_citations,
        )

        qa_claims = [
            cwc.get("claim", {})
            for cwc in claims_with_citations
            if cwc.get("claim")
        ] or state.get("claims", [])
        feedback_items = attach_feedback_qa(
            feedback_items,
            state.get("draft_content", ""),
            claims=qa_claims,
            gaps=gaps,
            sections=structure.get("sections", []),
            source_grounding_expected=bool(literature_context or literature_search_results),
        )
        failed_retry_payload = select_failed_feedback_for_retry(feedback_items)
        if failed_retry_payload:
            logger.info(
                f"[Reviewer Feedback] QA marked {len(failed_retry_payload)} items "
                "eligible for targeted retry"
            )

        strengths = sum(1 for f in feedback_items if f['feedback_type'] == 'strength')
        weaknesses = sum(1 for f in feedback_items if f['feedback_type'] == 'weakness')
        questions = sum(1 for f in feedback_items if f['feedback_type'] == 'question')
        suggestions = sum(1 for f in feedback_items if f['feedback_type'] == 'suggestion')

        logger.info(
            f"[Reviewer Feedback] Generated {len(feedback_items)} feedback items: "
            f"strengths={strengths}, weaknesses={weaknesses}, "
            f"questions={questions}, suggestions={suggestions}"
        )

        priority_actions = result.priority_actions

        # Persist priority_actions to draft_analysis.analysis_metadata
        try:
            existing = supabase.table("draft_analysis")\
                .select("analysis_metadata")\
                .eq("draft_id", draft_id)\
                .execute()

            if existing.data:
                metadata = existing.data[0].get("analysis_metadata") or {}
                metadata["priority_actions"] = priority_actions
                supabase.table("draft_analysis")\
                    .update({"analysis_metadata": metadata})\
                    .eq("draft_id", draft_id)\
                    .execute()
                logger.info(f"[Reviewer Feedback] Saved {len(priority_actions)} priority_actions to draft_analysis")
        except Exception as persist_err:
            logger.warning(f"[Reviewer Feedback] Could not persist priority_actions: {persist_err}")

        return {
            'reviewer_feedback': feedback_items,
            'overall_assessment': result.overall_assessment,
            'priority_actions': priority_actions,
            'reviewer_feedback_retry_items': failed_retry_payload,
            'current_step': 'Reviewer Feedback',
            'progress_percentage': 85
        }

    except Exception as e:
        logger.error(f"[Reviewer Feedback] Error: {e}")
        errors = state.get('errors', [])
        errors.append(f"Reviewer feedback generation failed: {str(e)}")

        return {
            'errors': errors,
            'current_step': 'Reviewer Feedback (Failed)',
            'progress_percentage': 85
        }

"""
Reviewer Feedback Generation Node

Generates expert academic reviewer-style feedback based on the analysis.
B1: Evidence-grounded per-claim context — passes per-claim citation quality,
specific papers found, and specific gaps to GPT so feedback names exact claims.
B4: Hard output constraints to prevent generic advice.
"""

from app.workflows.draft_analysis.state import DraftAnalysisState, Feedback
from app.core.logging_config import get_logger
from app.core.supabase_client import supabase
from app.core.openai_client import get_openai_client, get_completion_params
import json

logger = get_logger(__name__)

# Initialize OpenAI client
client = get_openai_client()


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

        lines.append(f"Claim {i}: \"{claim_text[:120]}{'...' if len(claim_text) > 120 else ''}\"")
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

    # OPTIMIZATION: Check if feedback already exists in database (from Phase 1)
    try:
        existing_feedback_res = supabase.table("reviewer_feedback")\
            .select("id, feedback_type, feedback_text, severity, section_reference")\
            .eq("draft_id", draft_id)\
            .execute()

        if existing_feedback_res.data and len(existing_feedback_res.data) > 0:
            logger.info(f"[Reviewer Feedback] Found {len(existing_feedback_res.data)} existing feedback items - SKIPPING re-generation")

            feedback_items: list[Feedback] = []
            for db_fb in existing_feedback_res.data:
                feedback: Feedback = {
                    "feedback_type": db_fb["feedback_type"],
                    "feedback_text": db_fb["feedback_text"],
                    "severity": db_fb["severity"],
                    "section_reference": db_fb.get("section_reference", "")
                }
                feedback_items.append(feedback)

            strengths = sum(1 for f in feedback_items if f['feedback_type'] == 'strength')
            weaknesses = sum(1 for f in feedback_items if f['feedback_type'] == 'weakness')
            logger.info(f"[Reviewer Feedback] Reusing {len(feedback_items)} existing: strengths={strengths}, weaknesses={weaknesses}")

            return {
                'reviewer_feedback': feedback_items,
                'overall_assessment': '',
                'priority_actions': [],
                'current_step': 'Reviewer Feedback (Cached)',
                'progress_percentage': 85
            }

    except Exception as db_error:
        logger.warning(f"[Reviewer Feedback] Could not check for existing feedback: {db_error}")

    try:
        structure = state.get("structure", {})
        claims_with_citations = state.get("claims_with_citations", [])
        gaps = state.get("coverage_gaps", [])

        # B1: Build per-claim context instead of aggregate counts
        per_claim_context = _build_per_claim_context(claims_with_citations, gaps, structure)

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

        # Add top coverage gaps for additional context
        critical_gaps = [g for g in gaps if g.get('severity') == 'critical']
        if critical_gaps:
            context += "\nCRITICAL COVERAGE GAPS:\n"
            for gap in critical_gaps[:3]:
                context += f"  * {gap['description']}\n"

        # B4: B5 token limit increased to 6000 for detailed per-claim feedback
        response = client.chat.completions.create(
            model="gpt-5.2-chat-latest",
            messages=[
                {"role": "system", "content": REVIEWER_FEEDBACK_PROMPT},
                {"role": "user", "content": f"Generate reviewer feedback based on this analysis:\n\n{context}"}
            ],
            max_completion_tokens=6000,
            **get_completion_params()
        )

        result = json.loads(response.choices[0].message.content)

        # Convert to typed Feedback objects
        feedback_items: list[Feedback] = []
        for item in result.get("feedback_items", []):
            feedback: Feedback = {
                'feedback_type': item['feedback_type'],
                'feedback_text': item['feedback_text'],
                'severity': item['severity'],
                'section_reference': item.get('section_reference', '')
            }
            feedback_items.append(feedback)

        strengths = sum(1 for f in feedback_items if f['feedback_type'] == 'strength')
        weaknesses = sum(1 for f in feedback_items if f['feedback_type'] == 'weakness')
        questions = sum(1 for f in feedback_items if f['feedback_type'] == 'question')
        suggestions = sum(1 for f in feedback_items if f['feedback_type'] == 'suggestion')

        logger.info(
            f"[Reviewer Feedback] Generated {len(feedback_items)} feedback items: "
            f"strengths={strengths}, weaknesses={weaknesses}, "
            f"questions={questions}, suggestions={suggestions}"
        )

        priority_actions = result.get('priority_actions', [])

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
            'overall_assessment': result.get('overall_assessment', ''),
            'priority_actions': priority_actions,
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

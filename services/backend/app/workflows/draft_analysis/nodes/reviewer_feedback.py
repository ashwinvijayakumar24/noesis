"""
Reviewer Feedback Generation Node

Generates expert academic reviewer-style feedback based on the analysis.
Evidence-grounded: passes retrieved literature excerpts into GPT so feedback
cites specific papers rather than speaking in generalities.
"""

from app.workflows.draft_analysis.state import DraftAnalysisState, Feedback
from app.core.logging_config import get_logger
from app.core.supabase_client import supabase
from app.core.openai_client import get_openai_client, get_completion_params
import json

logger = get_logger(__name__)

# Initialize OpenAI client
client = get_openai_client()


REVIEWER_FEEDBACK_PROMPT = """You are an expert academic reviewer providing constructive feedback on a research draft.

You have been given:
1. The draft structure and claim analysis
2. **Retrieved passages from the project's literature library** — use these to ground your feedback

Based on the analysis provided, generate reviewer feedback that:
1. Identifies strengths (what's done well)
2. Identifies weaknesses (what needs improvement, referencing specific literature)
3. Asks clarifying questions grounded in the retrieved papers
4. Suggests specific improvements, naming papers from the retrieved literature

**CRITICAL: When retrieved_literature is provided, cite specific papers by title when making suggestions.**
Example: "Consider citing [Paper Title] (Author et al., Year) which directly supports this claim."

Return ONLY a valid JSON object:
{
  "feedback_items": [
    {
      "feedback_type": "strength" | "weakness" | "question" | "suggestion",
      "feedback_text": "Specific, actionable feedback referencing literature by name",
      "severity": "critical" | "major" | "minor" | "suggestion",
      "section_reference": "Section name (if applicable)",
      "cited_papers": ["Paper title 1", "Paper title 2"]
    }
  ],
  "overall_assessment": "Brief overall assessment of the draft",
  "priority_actions": [
    "Most important action 1 (cite specific paper if relevant)",
    "Most important action 2",
    "Most important action 3"
  ]
}

Severity levels:
- "critical": Must be fixed before publication (blocking issues)
- "major": Should be addressed for significant improvement
- "minor": Optional improvements, minor issues
- "suggestion": General suggestions for enhancement

Guidelines:
- Be specific - reference exact claims and sections
- Be constructive - always suggest how to improve
- Be actionable - provide clear next steps
- Cite specific papers from the retrieved literature when suggesting additions
- Focus on high-impact feedback first
"""


def _build_literature_context(literature_search_results: list) -> str:
    """
    Build a condensed literature context string from search results.

    Picks top papers across all claim searches, deduplicates by document title,
    and returns up to 3 papers × 2 passages each as grounding context.
    """
    if not literature_search_results:
        return ""

    # Collect all results across claims, deduplicate by title
    seen_titles = set()
    top_papers = []

    for claim_result in literature_search_results:
        for result in claim_result.get("results", []):
            title = (
                result.get("document_title")
                or result.get("title")
                or result.get("metadata", {}).get("title", "")
            )
            if not title or title in seen_titles:
                continue
            seen_titles.add(title)

            # Extract key passage
            content = result.get("content", result.get("text", ""))
            passage = content[:300].strip() if content else ""

            authors = (
                result.get("authors")
                or result.get("metadata", {}).get("authors", "")
                or ""
            )
            year = (
                result.get("year")
                or result.get("metadata", {}).get("year", "")
                or ""
            )

            top_papers.append({
                "title": title,
                "authors": str(authors)[:80] if authors else "",
                "year": str(year) if year else "",
                "passage": passage,
                "similarity": result.get("similarity", 0),
            })

    if not top_papers:
        return ""

    # Sort by similarity, take top 5
    top_papers.sort(key=lambda p: p.get("similarity", 0), reverse=True)
    top_papers = top_papers[:5]

    lines = ["RETRIEVED LITERATURE (from project library):"]
    for i, paper in enumerate(top_papers, 1):
        ref = paper["title"]
        if paper["authors"]:
            ref += f" ({paper['authors']})"
        if paper["year"]:
            ref += f", {paper['year']}"
        lines.append(f"\n[{i}] {ref}")
        if paper["passage"]:
            lines.append(f'    Excerpt: "{paper["passage"]}"')

    return "\n".join(lines)


def generate_reviewer_feedback_node(state: DraftAnalysisState) -> DraftAnalysisState:
    """
    Generate expert reviewer feedback based on the complete analysis.

    Now evidence-grounded: pulls retrieved literature from state and includes
    it in the GPT prompt so feedback names specific papers.

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
        # Gather analysis context
        structure = state.get("structure", {})
        claims = state.get("claims", [])
        claims_with_citations = state.get("claims_with_citations", [])
        gaps = state.get("coverage_gaps", [])

        # ── NEW: Build literature grounding from search results ──
        literature_search_results = state.get("literature_search_results", [])
        literature_context = _build_literature_context(literature_search_results)

        if literature_context:
            logger.info(
                f"[Reviewer Feedback] Including literature context from "
                f"{len(literature_search_results)} claim searches"
            )
        else:
            logger.warning(
                "[Reviewer Feedback] No literature context available — "
                "feedback will be generic (user may not have uploaded documents)"
            )

        # Build context for GPT
        context = f"""
Draft Structure:
- Word count: {structure.get('word_count', 'Unknown')}
- Page count: {structure.get('page_count', 'Unknown')}
- Has abstract: {structure.get('has_abstract', False)}
- Has introduction: {structure.get('has_introduction', False)}
- Has methods: {structure.get('has_methods', False)}
- Has results: {structure.get('has_results', False)}
- Has discussion: {structure.get('has_discussion', False)}

Claims Analysis:
- Total claims: {len(claims)}
- Primary claims: {len(state.get('primary_claims', []))}
- Supporting claims: {len(state.get('supporting_claims', []))}
"""
        # Citation quality summary
        quality_counts = {
            'strong': sum(1 for c in claims_with_citations if c.get('citation_quality') == 'strong'),
            'moderate': sum(1 for c in claims_with_citations if c.get('citation_quality') == 'moderate'),
            'weak': sum(1 for c in claims_with_citations if c.get('citation_quality') == 'weak'),
            'none': sum(1 for c in claims_with_citations if c.get('citation_quality') == 'none')
        }
        context += f"""
Citation Quality:
- Strong support: {quality_counts['strong']} claims
- Moderate support: {quality_counts['moderate']} claims
- Weak support: {quality_counts['weak']} claims
- No support: {quality_counts['none']} claims

Coverage Gaps:
"""
        # Top gaps
        critical_gaps = [g for g in gaps if g['severity'] == 'critical']
        major_gaps = [g for g in gaps if g['severity'] == 'major']

        context += f"- Critical gaps: {len(critical_gaps)}\n"
        for gap in critical_gaps[:3]:
            context += f"  * {gap['description']}\n"

        context += f"- Major gaps: {len(major_gaps)}\n"
        for gap in major_gaps[:3]:
            context += f"  * {gap['description']}\n"

        # ── Append literature grounding ──
        if literature_context:
            context += f"\n\n{literature_context}\n"

        # Generate feedback using GPT-5.2-chat-latest
        response = client.chat.completions.create(
            model="gpt-5.2-chat-latest",
            messages=[
                {"role": "system", "content": REVIEWER_FEEDBACK_PROMPT},
                {"role": "user", "content": f"Generate reviewer feedback based on:\n\n{context}"}
            ],
            max_completion_tokens=2500,
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

"""
Reviewer Feedback Generation Node

Generates expert academic reviewer-style feedback based on the analysis.
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

Based on the analysis provided, generate reviewer feedback that:
1. Identifies strengths (what's done well)
2. Identifies weaknesses (what needs improvement)
3. Asks clarifying questions
4. Suggests specific improvements

Be constructive, specific, and actionable. Reference specific claims and gaps.

Return ONLY a valid JSON object:
{
  "feedback_items": [
    {
      "feedback_type": "strength" | "weakness" | "question" | "suggestion",
      "feedback_text": "Specific, actionable feedback",
      "severity": "critical" | "major" | "minor" | "suggestion",
      "section_reference": "Section name (if applicable)"
    }
  ],
  "overall_assessment": "Brief overall assessment of the draft",
  "priority_actions": [
    "Most important action 1",
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
- Focus on high-impact feedback first
"""


def generate_reviewer_feedback_node(state: DraftAnalysisState) -> DraftAnalysisState:
    """
    Generate expert reviewer feedback based on the complete analysis.

    This node synthesizes all previous analysis (claims, citations, gaps) into
    actionable reviewer feedback that mimics what an expert academic reviewer
    would provide.

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
            logger.info(f"[Reviewer Feedback] Found {len(existing_feedback_res.data)} existing feedback items in database - SKIPPING re-generation")

            # Convert database records to Feedback objects
            feedback_items: list[Feedback] = []
            for db_fb in existing_feedback_res.data:
                feedback: Feedback = {
                    "feedback_type": db_fb["feedback_type"],
                    "feedback_text": db_fb["feedback_text"],
                    "severity": db_fb["severity"],
                    "section_reference": db_fb.get("section_reference", "")
                }
                feedback_items.append(feedback)

            # Count feedback by type
            strengths = sum(1 for f in feedback_items if f['feedback_type'] == 'strength')
            weaknesses = sum(1 for f in feedback_items if f['feedback_type'] == 'weakness')
            questions = sum(1 for f in feedback_items if f['feedback_type'] == 'question')
            suggestions = sum(1 for f in feedback_items if f['feedback_type'] == 'suggestion')

            logger.info(
                f"[Reviewer Feedback] Reusing {len(feedback_items)} existing feedback: "
                f"strengths={strengths}, weaknesses={weaknesses}, "
                f"questions={questions}, suggestions={suggestions}"
            )

            return {
                'reviewer_feedback': feedback_items,
                'overall_assessment': '',  # Not stored in DB
                'priority_actions': [],  # Not stored in DB
                'current_step': 'Reviewer Feedback (Cached)',
                'progress_percentage': 85
            }

    except Exception as db_error:
        logger.warning(f"[Reviewer Feedback] Could not check for existing feedback: {db_error}")
        # Continue with generation if database check fails

    try:
        # Gather analysis context
        structure = state.get("structure", {})
        claims = state.get("claims", [])
        claims_with_citations = state.get("claims_with_citations", [])
        gaps = state.get("coverage_gaps", [])

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
- Claims by type: {state.get('claims_by_type', {}).keys()}
- Primary claims: {len(state.get('primary_claims', []))}
- Supporting claims: {len(state.get('supporting_claims', []))}

Citation Quality:
"""
        # Add citation quality summary
        quality_counts = {
            'strong': sum(1 for c in claims_with_citations if c.get('citation_quality') == 'strong'),
            'moderate': sum(1 for c in claims_with_citations if c.get('citation_quality') == 'moderate'),
            'weak': sum(1 for c in claims_with_citations if c.get('citation_quality') == 'weak'),
            'none': sum(1 for c in claims_with_citations if c.get('citation_quality') == 'none')
        }
        context += f"""
- Strong support: {quality_counts['strong']} claims
- Moderate support: {quality_counts['moderate']} claims
- Weak support: {quality_counts['weak']} claims
- No support: {quality_counts['none']} claims

Coverage Gaps:
"""
        # Add top gaps
        critical_gaps = [g for g in gaps if g['severity'] == 'critical']
        major_gaps = [g for g in gaps if g['severity'] == 'major']

        context += f"- Critical gaps: {len(critical_gaps)}\n"
        for gap in critical_gaps[:3]:
            context += f"  * {gap['description']}\n"

        context += f"- Major gaps: {len(major_gaps)}\n"
        for gap in major_gaps[:3]:
            context += f"  * {gap['description']}\n"

        # Generate feedback using GPT-5.2-chat-latest
        # Note: GPT-5.2-chat-latest only supports temperature=1.0 (default)
        response = client.chat.completions.create(
            model="gpt-5.2-chat-latest",
            messages=[
                {"role": "system", "content": REVIEWER_FEEDBACK_PROMPT},
                {"role": "user", "content": f"Generate reviewer feedback based on:\n\n{context}"}
            ],
            max_completion_tokens=2000,
            **get_completion_params()  # Enable zero data retention
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

        # Count feedback by type
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

        # Persist priority_actions to draft_analysis.analysis_metadata so the UI can surface them
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

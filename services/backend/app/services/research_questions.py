"""
Research Question Generation Service

Generates research questions from project insights using GPT-4.
"""

import json
from typing import List, Dict, Any
from app.core.logging_config import get_logger
from app.core.openai_client import get_openai_client, get_completion_params

logger = get_logger(__name__)


def generate_research_questions(insights: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Generate research questions from project insights.

    Args:
        insights: Project insights containing research gaps, themes, etc.

    Returns:
        List of research questions with rationale and methodology suggestions
    """

    # Extract relevant insight data
    research_gaps = insights.get('research_gaps', [])
    common_themes = insights.get('common_themes', [])
    conflicting_findings = insights.get('conflicting_findings', [])
    key_insights = insights.get('key_insights', [])

    # Build context for GPT-4
    context_parts = []

    if research_gaps:
        context_parts.append("## Research Gaps Identified:\n")
        for gap in research_gaps:
            context_parts.append(f"- **{gap.get('category', 'Unknown')}**: {gap.get('description', '')}")
            if gap.get('evidence'):
                context_parts.append(f"  Evidence: {gap.get('evidence')}")
            context_parts.append("")

    if common_themes:
        context_parts.append("## Common Themes Across Papers:\n")
        for theme in common_themes:
            context_parts.append(f"- {theme.get('theme', '')}: {theme.get('description', '')}")
        context_parts.append("")

    if conflicting_findings:
        context_parts.append("## Conflicting Findings:\n")
        for conflict in conflicting_findings:
            context_parts.append(f"- {conflict.get('topic', '')}: {conflict.get('description', '')}")
        context_parts.append("")

    if key_insights:
        context_parts.append("## Key Insights:\n")
        for insight in key_insights[:3]:  # Top 3 insights
            context_parts.append(f"- {insight}")
        context_parts.append("")

    context = "\n".join(context_parts)

    # GPT-4 prompt for research question generation
    system_prompt = """You are an expert research methodology consultant helping researchers identify meaningful research questions.

Given the literature analysis below, generate 5-10 specific, actionable research questions that:
1. Address identified gaps in the literature
2. Are specific enough to be answerable
3. Build on existing themes and findings
4. Resolve conflicting findings where applicable
5. Are original and contribute to the field

For each research question, provide:
- question: The research question itself (clear, specific, answerable)
- rationale: Why this question matters and how it addresses gaps (2-3 sentences)
- suggested_methodology: Recommended research approach (e.g., "Systematic Literature Review", "Mixed Methods Study", "Experimental Study", "Case Study Analysis")
- gap_category: Which gap category this addresses (methodological, population, theoretical, temporal, or null if not applicable)

Return ONLY a JSON object with a "questions" array. No markdown, no explanations outside the JSON."""

    user_prompt = f"""Based on this literature analysis, generate research questions:

{context}

Return a JSON object with a "questions" array in the format:
{{
  "questions": [
    {{
      "question": "How does X affect Y in Z context?",
      "rationale": "This question addresses the methodological gap...",
      "suggested_methodology": "Mixed Methods Study",
      "gap_category": "methodological"
    }}
  ]
}}"""

    logger.info("Generating research questions from insights")

    try:
        client = get_openai_client()
        # Note: Temperature removed - GPT-5.2 models use default temperature=1.0
        response = client.chat.completions.create(
            model="gpt-5.2-chat-latest",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_completion_tokens=2000,
            **get_completion_params()  # Enable zero data retention
        )

        result_text = response.choices[0].message.content
        logger.info("Received response from GPT-4")

        # Parse JSON response
        result = json.loads(result_text)

        # Handle both array and object with array format
        if isinstance(result, list):
            questions = result
        elif isinstance(result, dict) and 'questions' in result:
            questions = result['questions']
        elif isinstance(result, dict) and 'research_questions' in result:
            questions = result['research_questions']
        elif isinstance(result, dict) and 'question' in result and 'rationale' in result:
            # Single question object - wrap in array
            questions = [result]
        else:
            # If it's an object, try to extract the first array value
            for value in result.values():
                if isinstance(value, list):
                    questions = value
                    break
            else:
                raise ValueError(f"Unexpected response format: {result}")

        logger.info(f"Generated {len(questions)} research questions")

        # Validate each question has required fields
        valid_questions = []
        for q in questions:
            if 'question' in q and 'rationale' in q:
                # Ensure all fields exist
                valid_q = {
                    'question': q.get('question', '').strip(),
                    'rationale': q.get('rationale', '').strip(),
                    'suggested_methodology': q.get('suggested_methodology', 'Literature Review').strip(),
                    'gap_category': q.get('gap_category', None)
                }
                # Validate gap_category
                valid_categories = ['methodological', 'population', 'theoretical', 'temporal']
                if valid_q['gap_category'] and valid_q['gap_category'] not in valid_categories:
                    valid_q['gap_category'] = None

                valid_questions.append(valid_q)

        logger.info(f"Validated {len(valid_questions)} questions")
        return valid_questions

    except Exception as e:
        logger.error(f"Error generating research questions: {type(e).__name__}: {str(e)}")
        raise Exception(f"Failed to generate research questions: {str(e)}")

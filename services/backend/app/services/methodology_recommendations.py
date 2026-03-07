"""
Methodology Recommendations Service

Generates detailed methodology recommendations for research questions using GPT-4.
"""

import json
from typing import Dict, Any, Optional, List
from app.core.logging_config import get_logger
from app.core.openai_client import get_openai_client, get_completion_params

logger = get_logger(__name__)

client = get_openai_client()


def generate_methodology_recommendations(
    question: str,
    project_context: Optional[Dict[str, Any]] = None,
    insights: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Generate detailed methodology recommendations for a research question.

    Args:
        question: The research question to generate recommendations for
        project_context: Optional project context (themes, papers, etc.)
        insights: Optional project insights for additional context

    Returns:
        Dictionary containing methodology recommendations with detailed guidance
    """

    # Build context from project data
    context_parts = [f"Research Question: {question}\n"]

    if project_context:
        if project_context.get('num_papers'):
            context_parts.append(f"\nProject has {project_context['num_papers']} analyzed papers.")

        if project_context.get('common_themes'):
            context_parts.append("\nProject Themes:")
            for theme in project_context.get('common_themes', [])[:3]:
                context_parts.append(f"- {theme.get('theme', '')}")

    if insights:
        if insights.get('key_insights'):
            context_parts.append("\nKey Insights from Literature:")
            for insight in insights.get('key_insights', [])[:3]:
                context_parts.append(f"- {insight}")

    context = "\n".join(context_parts)

    # GPT-4 prompt for methodology recommendations
    system_prompt = """You are an expert research methodologist and academic advisor with deep knowledge of research design across multiple disciplines.

Given a research question and project context, provide detailed, actionable methodology recommendations that will help a researcher design and execute their study.

Your recommendations should be:
1. Specific to the research question
2. Practically implementable
3. Academically rigorous
4. Realistic about resources and timeline
5. Aware of common pitfalls and how to avoid them

Provide comprehensive guidance covering methodology selection, data collection, analysis, and validation."""

    user_prompt = f"""{context}

Based on this research question and context, provide detailed methodology recommendations.

Return a JSON object with this exact structure:
{{
  "primary_methodology": {{
    "name": "The primary recommended methodology (e.g., 'Mixed Methods Study', 'Systematic Literature Review')",
    "fit_score": 9,
    "rationale": "2-3 sentences explaining why this methodology is best suited for answering this research question",
    "approach": ["Step 1: Detailed step", "Step 2: Detailed step", "Step 3: Detailed step", "..."],
    "required_resources": ["Resource 1: Description", "Resource 2: Description", "..."],
    "timeline": "Estimated timeline (e.g., '6-12 months', '3-6 months')",
    "challenges": ["Challenge 1: Description and mitigation", "Challenge 2: Description and mitigation"],
    "example_studies": ["Brief description of example study 1", "Brief description of example study 2"]
  }},
  "alternative_methodologies": [
    {{
      "name": "Alternative methodology name",
      "fit_score": 7,
      "rationale": "Why this is a viable alternative",
      "when_to_use": "When to prefer this over the primary methodology"
    }},
    {{
      "name": "Another alternative",
      "fit_score": 6,
      "rationale": "Why this could work",
      "when_to_use": "Specific scenarios where this is preferred"
    }}
  ],
  "data_collection": {{
    "strategy": "Detailed description of data collection approach",
    "sources": ["Source 1 with details", "Source 2 with details", "..."],
    "tools": ["Tool 1: Purpose", "Tool 2: Purpose", "..."],
    "sample_size": "Recommended sample size or data scope with justification"
  }},
  "analysis_techniques": [
    "Technique 1: Description of how to apply it",
    "Technique 2: Description of how to apply it",
    "..."
  ],
  "validation_approach": "Detailed description of how to validate findings and ensure rigor"
}}

Make all recommendations specific and actionable. Include at least 2 alternative methodologies."""

    logger.info(f"Generating methodology recommendations for question")

    try:
        # Note: Temperature removed - GPT-5.2 models use default temperature=1.0
        response = client.chat.completions.create(
            model="gpt-5.2-chat-latest",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            **get_completion_params()  # Enable zero data retention
        )

        result_text = response.choices[0].message.content
        logger.info(f"Received response from GPT-4")

        # Parse JSON response
        recommendations = json.loads(result_text)

        # Validate structure
        required_keys = ['primary_methodology', 'alternative_methodologies', 'data_collection',
                        'analysis_techniques', 'validation_approach']

        for key in required_keys:
            if key not in recommendations:
                raise ValueError(f"Missing required key in response: {key}")

        # Validate primary methodology structure
        primary = recommendations['primary_methodology']
        required_primary_keys = ['name', 'fit_score', 'rationale', 'approach',
                                'required_resources', 'timeline', 'challenges']

        for key in required_primary_keys:
            if key not in primary:
                raise ValueError(f"Missing required key in primary_methodology: {key}")

        logger.info(f"Successfully generated recommendations for: {primary['name']}")

        return recommendations

    except Exception as e:
        logger.info(f"ERROR: {type(e).__name__}: {str(e)}")
        raise Exception(f"Failed to generate methodology recommendations: {str(e)}")

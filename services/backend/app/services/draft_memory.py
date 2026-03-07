"""
Cross-Draft Memory Service

Identifies recurring feedback patterns across multiple draft versions in a project.
Helps researchers understand persistent weaknesses that span multiple revisions.
"""

import json
import asyncio
from typing import Dict, Any, List
from collections import defaultdict

from app.core.supabase_client import supabase
from app.core.openai_client import get_openai_client, get_completion_params
from app.core.logging_config import get_logger

logger = get_logger(__name__)


PATTERN_SYNTHESIS_PROMPT = """You are an expert academic mentor analyzing recurring issues across multiple versions of a research draft.

Given a list of recurring feedback items (each seen in 2+ draft versions), synthesize them into clear patterns.

Return ONLY valid JSON:
{
  "patterns": [
    {
      "pattern_name": "Short, descriptive name for this recurring issue",
      "frequency": 3,
      "root_cause": "Why this issue keeps recurring (1-2 sentences)",
      "targeted_advice": "Specific, actionable advice to permanently resolve this pattern (2-3 sentences)"
    }
  ],
  "overall_observation": "One sentence about the draft's most persistent challenge"
}

Focus on patterns that truly recur — not one-off issues.
"""


async def identify_recurring_patterns(project_id: str, user_id: str) -> Dict[str, Any]:
    """
    Identify recurring feedback patterns across all analyzed drafts in a project.

    Only meaningful when 3+ analyzed drafts exist.

    Args:
        project_id: Project to analyze
        user_id: User ID (for authorization)

    Returns:
        Dict with patterns list and overall_observation
    """
    try:
        # Fetch all analyzed drafts in project
        drafts_res = supabase.table("drafts")\
            .select("id, version")\
            .eq("project_id", project_id)\
            .eq("user_id", user_id)\
            .eq("status", "analyzed")\
            .order("version", desc=False)\
            .execute()

        drafts = drafts_res.data or []

        if len(drafts) < 3:
            return {
                "patterns": [],
                "overall_observation": None,
                "message": "Need at least 3 analyzed drafts to identify patterns"
            }

        # Collect all feedback items across all drafts
        all_feedback: List[Dict] = []
        for draft in drafts:
            fb_res = supabase.table("reviewer_feedback")\
                .select("feedback_text, feedback_type, severity, section_reference")\
                .eq("draft_id", draft["id"])\
                .execute()

            for fb in (fb_res.data or []):
                fb["draft_version"] = draft["version"]
                all_feedback.append(fb)

        if not all_feedback:
            return {"patterns": [], "overall_observation": None, "message": "No feedback found"}

        # Group by normalized feedback text to find recurrences
        # Use first 80 chars as grouping key (crude but avoids embeddings overhead)
        occurrence_map: Dict[str, List[Dict]] = defaultdict(list)
        for fb in all_feedback:
            key = fb.get("feedback_text", "")[:80].lower().strip()
            if key:
                occurrence_map[key].append(fb)

        # Keep only items that appear in 2+ drafts
        recurring = [
            {
                "feedback_text": items[0].get("feedback_text", ""),
                "feedback_type": items[0].get("feedback_type", ""),
                "severity": items[0].get("severity", ""),
                "section_reference": items[0].get("section_reference", ""),
                "frequency": len(items),
                "versions_seen": sorted(set(i["draft_version"] for i in items))
            }
            for items in occurrence_map.values()
            if len(items) >= 2
        ]

        if not recurring:
            return {
                "patterns": [],
                "overall_observation": "Good progress — no recurring issues detected across versions.",
                "message": "No recurring patterns found"
            }

        # Sort by frequency descending, take top 8
        recurring.sort(key=lambda x: x["frequency"], reverse=True)
        top_recurring = recurring[:8]

        # Synthesize with GPT
        client = get_openai_client()
        context = "Recurring feedback items (appearing in 2+ draft versions):\n\n"
        for item in top_recurring:
            context += (
                f"- [{item['severity'].upper()}] {item['feedback_text'][:150]}\n"
                f"  Seen in versions: {item['versions_seen']} ({item['frequency']} times)\n\n"
            )

        def _sync_call():
            response = client.chat.completions.create(
                model="gpt-5.2-chat-latest",
                messages=[
                    {"role": "system", "content": PATTERN_SYNTHESIS_PROMPT},
                    {"role": "user", "content": f"Synthesize these recurring patterns:\n\n{context}"}
                ],
                max_completion_tokens=1200,
                **get_completion_params()
            )
            return json.loads(response.choices[0].message.content)

        result = await asyncio.to_thread(_sync_call)
        logger.info(f"Identified {len(result.get('patterns', []))} recurring patterns for project {project_id}")
        return result

    except Exception as e:
        logger.error(f"Recurring pattern identification failed: {e}")
        raise

"""Reviewer 1 strengths generation for draft analysis."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from app.core.logging_config import get_logger
from app.core.openai_client import get_completion_params, get_openai_client

logger = get_logger(__name__)

REVIEWER_1_SYSTEM = """You are Reviewer 1 at a top academic journal. Your sole task: identify the strongest aspects of this research draft.

Focus on:
- Most novel contributions and their significance to the field
- Strongest arguments and their supporting evidence
- Best-structured sections
- Clear methodological strengths
- Well-supported empirical or theoretical claims

Return valid JSON in exactly this format:
{
  "strengths": [
    {
      "aspect": "brief title of this strength",
      "section_reference": "section name or 'Overall'",
      "detail": "specific explanation grounded in draft content",
      "significance": "high|medium|low"
    }
  ]
}

Rules:
- Be specific: reference exact sections, claims, or figures by name
- No suggestions or critiques; only genuine strengths
- Return minimum 3 and maximum 8 strengths
- If the draft has serious weaknesses, still identify relative strengths
- Each strength must reference actual content from the draft"""


def _extract_json_object(raw_content: str) -> dict[str, Any]:
    content = (raw_content or "").strip()
    if content.startswith("```"):
        lines = content.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        content = "\n".join(lines).strip()

    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("Reviewer 1 response did not contain JSON")
    return json.loads(content[start:end + 1])


async def generate_reviewer1_feedback(
    draft_id: str,
    draft_content: str,
    structure: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Generate positive strengths feedback without blocking the rest of analysis."""
    client = get_openai_client()
    if not client or not draft_content.strip():
        return []

    structure_summary = json.dumps(structure or {}, ensure_ascii=True)[:3000]
    user_prompt = (
        f"Draft ID: {draft_id}\n"
        f"Structure summary: {structure_summary}\n\n"
        f"Analyze this draft and identify its strongest aspects:\n\n{draft_content[:12000]}"
    )

    def _sync_call() -> list[dict[str, Any]]:
        response = client.chat.completions.create(
            model="gpt-5.2",
            messages=[
                {"role": "system", "content": REVIEWER_1_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            max_completion_tokens=1500,
            **get_completion_params(),
        )
        parsed = _extract_json_object(response.choices[0].message.content or "")
        strengths = parsed.get("strengths", [])
        items: list[dict[str, Any]] = []
        for strength in strengths[:8]:
            aspect = (strength.get("aspect") or "Notable strength").strip()
            detail = (strength.get("detail") or "").strip()
            if not detail:
                continue
            significance = (strength.get("significance") or "medium").lower()
            items.append(
                {
                    "feedback_type": "strength",
                    "feedback_text": f"{aspect}: {detail}",
                    "severity": "suggestion",
                    "section_reference": strength.get("section_reference") or "Overall",
                    "reviewer_persona": "reviewer_1",
                    "suggestions": [],
                    "confidence_level": "high" if significance == "high" else "medium",
                    "specific_issue": aspect,
                }
            )
        return items

    try:
        return await asyncio.to_thread(_sync_call)
    except Exception as exc:
        logger.warning("[Reviewer1] Strength generation failed for draft %s: %s", draft_id, exc)
        return []

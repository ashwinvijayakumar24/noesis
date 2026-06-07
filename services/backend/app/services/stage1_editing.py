"""Stage 1 mechanical editing checks for draft analysis."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from app.core.logging_config import get_logger
from app.core.openai_client import get_completion_params, get_openai_client
from app.services.retry_utils import parse_chat_completion_with_retries_sync
from app.workflows.draft_analysis.schemas import Stage1EditingOutput

logger = get_logger(__name__)

STAGE1_SYSTEM = """You are an academic copy editor. Perform a mechanical editing check on this draft.

Paper type: {paper_type}
Citation style: {citation_style}

Check for:
1. Grammar and spelling errors (note the section and problematic text)
2. Citation style violations (wrong format for {citation_style}, missing required fields, inconsistent formatting)
3. Formatting issues (inconsistent heading levels, bullet style, table/figure caption format)
4. Structural notes for {paper_type} (e.g., abstract too long, missing section, wrong section order)

Return valid JSON:
{{
  "grammar_issues": [{{"text": "...", "issue": "...", "suggestion": "...", "section": "..."}}],
  "citation_issues": [{{"text": "...", "issue": "...", "suggestion": "..."}}],
  "formatting_issues": [{{"issue": "...", "location": "...", "suggestion": "..."}}],
  "structural_notes": [{{"note": "...", "severity": "minor|suggestion"}}]
}}

Return max 15 items per category. Focus on patterns, not every individual instance.
If citation style is auto, infer the likely field convention from the manuscript.
For materials science, chemistry, and engineering drafts, numbered bracket citations like [1,2] are acceptable and should not be flagged as APA violations.
If the draft looks clean in a category, return an empty list for that category."""


def _default_stage1_payload() -> dict[str, list[dict[str, Any]]]:
    return {
        "grammar_issues": [],
        "citation_issues": [],
        "formatting_issues": [],
        "structural_notes": [],
    }


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
        raise ValueError("Stage 1 response did not contain JSON")
    return json.loads(content[start:end + 1])


async def run_stage1_editing(
    draft_content: str,
    citation_style: str = "auto",
    paper_type: str = "journal_article",
) -> dict[str, list[dict[str, Any]]]:
    """Run the mechanical editing pass and return a stable payload shape."""
    client = get_openai_client()
    if not client or not draft_content.strip():
        return _default_stage1_payload()

    user_prompt = f"Run the editing pass on this draft:\n\n{draft_content[:14000]}"

    def _sync_call() -> dict[str, list[dict[str, Any]]]:
        response = parse_chat_completion_with_retries_sync(
            client,
            model="gpt-5.2-chat-latest",
            messages=[
                {
                    "role": "system",
                    "content": STAGE1_SYSTEM.format(
                        paper_type=paper_type,
                        citation_style=citation_style,
                    ),
                },
                {"role": "user", "content": user_prompt},
            ],
            max_completion_tokens=4096,
            response_format=Stage1EditingOutput,
            **get_completion_params(),
        )
        parsed = response.parsed
        return {
            "grammar_issues": [i.model_dump() for i in parsed.grammar_issues[:15]],
            "citation_issues": [i.model_dump() for i in parsed.citation_issues[:15]],
            "formatting_issues": [i.model_dump() for i in parsed.formatting_issues[:15]],
            "structural_notes": [i.model_dump() for i in parsed.structural_notes[:15]],
        }

    try:
        return await asyncio.to_thread(_sync_call)
    except Exception as exc:
        logger.warning("[Stage1Editing] Mechanical editing failed: %s", exc)
        return _default_stage1_payload()

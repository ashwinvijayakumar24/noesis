"""Final LLM judge for domain alignment and manuscript-specificity."""

from __future__ import annotations

import re
from typing import Any

from app.core.logging_config import get_logger
from app.core.openai_client import get_async_openai_client, get_completion_params
from app.core.privacy import safe_exception
from app.services.retry_utils import parse_chat_completion_with_retries
from app.workflows.draft_analysis.domain_routing import domain_context_block
from app.workflows.draft_analysis.schemas import AnalysisQualityJudgeOutput

logger = get_logger(__name__)
client = None


def _get_client():
    global client
    if client is None:
        client = get_async_openai_client()
    return client


ANALYSIS_QUALITY_JUDGE_PROMPT = """You are Noesis's final analysis quality judge.

Your job is not to review the manuscript. Your job is to judge whether Noesis's
analysis is about the uploaded manuscript and whether the routed domain itself
matches the manuscript's actual genre, discipline, and evidence mode.

Pass the analysis if:
- The feedback is mostly about the uploaded manuscript's topic and claims.
- The review standards match the manuscript's actual genre and evidence mode,
  not merely the current route label.
- Minor generic wording or isolated cross-domain words do not change the substance.

Fail the analysis if:
- The recommendations are mostly about a different field or different manuscript.
- The analysis applies inappropriate standards from another domain.
- The comments would be obviously absurd to the manuscript's author.
- The actionable task list is dominated by duplicates, lacks usable anchors, or leaves major citation/evidence tasks without any source-search result.

Set reroute_required=true if the manuscript's actual genre/discipline conflicts
with the current route and a corrected route would likely rescue the run. Example:
a composition pedagogy or humanities article about generative AI must not be
approved under empirical ML standards just because it mentions algorithms.

If reroute_required=true, set quality_pass=false, publish_allowed=false, and
suggested_route to the best route key, such as humanities_education,
computer_science_conceptual, public_health_psychology,
social_science_qualitative, law_policy, business_management,
environmental_ecology, mechanical_civil_engineering, math_statistics,
neuroscience_cognitive_science, education_empirical, chemistry_materials,
biology, biomedical, or generic_academic.

Do not fail because of one isolated word. Fail only for substantive wrong-domain analysis."""


def _clip(value: Any, limit: int = 7000) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit]


def _format_reviewer_outputs(outputs: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for output in outputs:
        lines.append(f"Reviewer {output.get('reviewer_id', 'unknown')}: {output.get('summary', '')}")
        for issue in (output.get("issues") or [])[:4]:
            lines.append(
                f"- {issue.get('problem', '')} Action: {issue.get('suggested_action', '')}"
            )
    return "\n".join(lines)


async def judge_analysis_quality(
    *,
    draft_title: str,
    draft_excerpt: str,
    manuscript_profile: dict[str, Any],
    reviewer_outputs: list[dict[str, Any]],
    meta_review: dict[str, Any] | None,
    revision_tasks: list[dict[str, Any]],
    revision_quality_metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = f"""DRAFT TITLE:
{draft_title or "Unknown"}

DRAFT EXCERPT:
{_clip(draft_excerpt, 5000)}

{domain_context_block(manuscript_profile)}

MANUSCRIPT PROFILE:
{_clip(manuscript_profile, 3000)}

REVIEWER OUTPUTS:
{_clip(_format_reviewer_outputs(reviewer_outputs), 7000)}

META REVIEW:
{_clip(meta_review, 3500)}

REVISION TASKS:
{_clip(revision_tasks, 7000)}

REVISION QUALITY METRICS:
{_clip(revision_quality_metrics, 1500)}
"""

    try:
        response = await parse_chat_completion_with_retries(
            _get_client(),
            model="gpt-5.2-chat-latest",
            messages=[
                {"role": "system", "content": ANALYSIS_QUALITY_JUDGE_PROMPT},
                {"role": "user", "content": context},
            ],
            max_completion_tokens=1200,
            response_format=AnalysisQualityJudgeOutput,
            **get_completion_params(),
        )
        result = response.parsed.model_dump()
        logger.info(
            "[AnalysisQualityJudge] pass=%s domain=%.2f specificity=%.2f retry=%s",
            result.get("quality_pass"),
            result.get("domain_alignment_score", 0),
            result.get("manuscript_specificity_score", 0),
            result.get("retry_recommended"),
        )
        return result
    except Exception as exc:
        logger.warning("[AnalysisQualityJudge] Failed open: %s", safe_exception(exc))
        return {
            "quality_pass": True,
            "domain_alignment_score": 0.5,
            "manuscript_specificity_score": 0.5,
            "wrong_domain_flags": [],
            "retry_recommended": False,
            "reroute_required": False,
            "suggested_route": "",
            "invalid_review_standards": [],
            "source_contamination_flags": [],
            "publish_allowed": True,
            "failure_reason": "",
            "judge_rationale": f"Judge unavailable; analysis allowed through: {safe_exception(exc)}",
        }

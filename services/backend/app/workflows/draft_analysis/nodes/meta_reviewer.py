"""
Meta-Reviewer Node (Area Chair)

Runs after all parallel reviewer_panel_node calls complete (LangGraph fan-in).
Synthesizes ReviewerOutput objects into a decisive MetaReviewOutput.

Also writes a flat list to reviewer_feedback table for backwards compatibility
with the existing frontend.
"""

from __future__ import annotations

from app.workflows.draft_analysis.state import DraftAnalysisState
from app.workflows.draft_analysis.schemas import MetaReviewOutput
from app.workflows.draft_analysis.domain_routing import domain_context_block
from app.core.logging_config import get_logger
from app.core.openai_client import get_async_openai_client, get_completion_params
from app.core.supabase_client import supabase
from app.services.retry_utils import parse_chat_completion_with_retries

logger = get_logger(__name__)

VALID_REVIEWER_PERSONAS = {"reviewer_1", "reviewer_2"}


def _normalize_reviewer_persona(value: str | None, fallback: str = "reviewer_2") -> str:
    if value in VALID_REVIEWER_PERSONAS:
        return value
    if fallback in VALID_REVIEWER_PERSONAS:
        return fallback
    return "reviewer_2"
client = None


def _get_client():
    global client
    if client is None:
        client = get_async_openai_client()
    return client

META_REVIEWER_PROMPT = """You are an Area Chair (meta-reviewer) synthesizing the reports of three specialist reviewers.

Your job: produce a decisive recommendation that the authors can act on.

Guidelines:
- Do NOT average ratings — synthesize qualitatively
- Use manuscript profile and diagnostic findings as first-class evidence when they reveal paper-type-specific review risks
- Explicitly surface reviewer conflicts ("Reviewer A rates novelty strong; Reviewer C flags a key missing citation that undermines this claim")
- When reviewers disagree, resolve the conflict using the manuscript profile's high-risk checks and the diagnostic findings as the tie-breaker — NOT a majority vote
- decision_rationale must be an executive judgment that weighs the single heaviest flaw against the contribution; do NOT just restate each reviewer's summary
- must_address = blocking items that, if fixed, could change the recommendation
- nice_to_address = non-blocking suggestions
- Be decisive. "borderline with clear path to acceptance" is acceptable.
  "it depends on reviewer preference" is not a meta-review.
- consensus_strengths = things ALL reviewers agree are strong
- consensus_weaknesses = things multiple reviewers flag as weak

RECOMMENDATION SCALE:
- accept: Paper can be accepted with only minor polish
- minor_revision: Clear path to acceptance; authors can address in 2-4 weeks
- major_revision: Significant work needed; 2-3 month revision cycle
- reject: Fundamental issues that cannot be addressed in a revision cycle

Return a structured meta-review."""


def _format_reviewer_outputs_for_context(reviewer_outputs: list[dict]) -> str:
    lines = []
    for ro in reviewer_outputs:
        rid = ro.get("reviewer_id", "unknown")
        rating = ro.get("rating", "?")
        confidence = ro.get("confidence", "?")
        rec = ro.get("recommendation", "?")
        lines.append(f"\n=== REVIEWER {rid.upper()} (Rating: {rating}/10, Confidence: {confidence}/5, Recommendation: {rec}) ===")
        lines.append(f"Summary: {ro.get('summary', '')}")

        strengths = ro.get("strengths") or []
        if strengths:
            lines.append("Strengths:")
            for s in strengths:
                lines.append(f"  + {s}")

        weaknesses = ro.get("weaknesses") or []
        if weaknesses:
            lines.append("Weaknesses:")
            for w in weaknesses:
                lines.append(f"  - {w}")

        issues = ro.get("issues") or []
        if issues:
            lines.append("Structured issues:")
            for issue in issues[:5]:
                lines.append(
                    "  ! "
                    f"{issue.get('section_reference', 'Unknown')}: "
                    f"{issue.get('problem', '')} "
                    f"Action: {issue.get('suggested_action', '')}"
                )

        questions = ro.get("questions_to_authors") or []
        if questions:
            lines.append("Questions to authors:")
            for q in questions:
                lines.append(f"  ? {q}")

    return "\n".join(lines)


def _synthesize_legacy_feedback(meta: MetaReviewOutput, reviewer_outputs: list[dict]) -> list[dict]:
    """
    Convert panel output into the flat reviewer_feedback table format
    for backwards compatibility with the existing frontend.
    """
    items = []

    # Meta-review must-address → critical weaknesses
    for item in meta.must_address:
        items.append({
            "feedback_type": "weakness",
            "feedback_text": item,
            "severity": "critical",
            "section_reference": "",
            "reviewer_persona": "reviewer_2",
            "reviewer_id": "area_chair",
            "suggestions": [],
        })

    # Consensus strengths → strengths
    for s in meta.consensus_strengths[:3]:
        items.append({
            "feedback_type": "strength",
            "feedback_text": s,
            "severity": "suggestion",
            "section_reference": "",
            "reviewer_persona": "reviewer_1",
            "reviewer_id": "area_chair",
            "suggestions": [],
        })

    # Nice-to-address → suggestions
    for item in meta.nice_to_address[:4]:
        items.append({
            "feedback_type": "suggestion",
            "feedback_text": item,
            "severity": "minor",
            "section_reference": "",
            "reviewer_persona": "reviewer_2",
            "reviewer_id": "area_chair",
            "suggestions": [],
        })

    # Per-reviewer questions → questions
    for ro in reviewer_outputs:
        for q in (ro.get("questions_to_authors") or [])[:2]:
            items.append({
                "feedback_type": "question",
                "feedback_text": q,
                "severity": "major",
                "section_reference": "",
                "reviewer_persona": _normalize_reviewer_persona(ro.get("reviewer_persona")),
                "reviewer_id": ro.get("reviewer_id", "reviewer"),
                "suggestions": [],
            })

    return items


async def meta_reviewer_node(state: DraftAnalysisState) -> dict:
    """
    Synthesize all reviewer outputs into a meta-review.
    Also populates reviewer_feedback table for legacy frontend.
    """
    draft_id = state.get("draft_id", "")
    # Prefer judged/retried outputs written by reviewer_judge_node; fall back to raw fan-in outputs.
    reviewer_outputs = state.get("judged_reviewer_outputs") or state.get("reviewer_outputs") or []

    logger.info(
        f"[MetaReviewer] Starting draft_id={draft_id}, "
        f"reviewer_outputs received: {len(reviewer_outputs)}"
    )

    # Quality-v2 regenerates meta-review rows on each analysis run because
    # diagnostic findings and reviewer retries can change for the same draft_id.

    if not reviewer_outputs:
        logger.warning(f"[MetaReviewer] No reviewer outputs — skipping meta review")
        return {
            "meta_review": None,
            "current_step": "Meta Review (Skipped — no reviewer outputs)",
            "progress_percentage": 93,
        }

    profile = state.get("manuscript_profile") or {}
    diagnostics = state.get("diagnostic_findings") or []
    diagnostic_lines = []
    for finding in diagnostics[:10]:
        diagnostic_lines.append(
            f"- [{finding.get('severity', 'major')}] {finding.get('finding_type', 'diagnostic')}: "
            f"{finding.get('problem', '')} Action: {finding.get('suggested_action', '')}"
        )

    context = f"""PAPER TYPE: {state.get('paper_type', 'unknown')}
MANUSCRIPT PROFILE: {profile}
{domain_context_block(profile)}

PROFILE-AWARE DIAGNOSTIC FINDINGS:
{chr(10).join(diagnostic_lines) if diagnostic_lines else "None"}

REVIEWER REPORTS:
{_format_reviewer_outputs_for_context(reviewer_outputs)}

Based on these specialist reviews and the canonical diagnostics, produce your area chair meta-review."""

    try:
        response = await parse_chat_completion_with_retries(
            _get_client(),
            model="gpt-5.2-chat-latest",
            messages=[
                {"role": "system", "content": META_REVIEWER_PROMPT},
                {"role": "user", "content": context},
            ],
            max_completion_tokens=2000,
            temperature=0,
            response_format=MetaReviewOutput,
            **get_completion_params(),
        )

        meta = response.parsed

        # Build score_summary from reviewer_outputs (fill any missing from meta)
        score_summary: dict[str, int] = {}
        for ro in reviewer_outputs:
            rid = ro.get("reviewer_id")
            rating = ro.get("rating")
            if rid and rating:
                score_summary[rid] = rating

        meta_dict = meta.model_dump()
        meta_dict["score_summary"] = score_summary or meta_dict.get("score_summary", {})

        if not state.get("stage_only", True):
            # Legacy direct persist path. Normal draft analysis publishes atomically later.
            supabase.table("meta_reviews").delete().eq("draft_id", draft_id).execute()
            supabase.table("meta_reviews").insert({
                "draft_id": draft_id,
                **meta_dict,
            }).execute()

            supabase.table("reviewer_feedback").delete().eq("draft_id", draft_id).execute()
            legacy_items = _synthesize_legacy_feedback(meta, reviewer_outputs)
            if legacy_items:
                supabase.table("reviewer_feedback").insert([
                    {"draft_id": draft_id, **item}
                    for item in legacy_items
                ]).execute()
                logger.info(f"[MetaReviewer] Wrote {len(legacy_items)} legacy feedback rows")

        logger.info(
            f"[MetaReviewer] Complete: "
            f"recommendation={meta.overall_recommendation}, "
            f"agreement={meta.reviewer_agreement_level}"
        )

        return {
            "meta_review": meta_dict,
            "current_step": "Meta Review",
            "progress_percentage": 93,
        }

    except Exception as exc:
        logger.error(f"[MetaReviewer] Failed: {exc}")
        errors = state.get("errors") or []
        errors.append(f"Meta review failed: {exc}")
        return {
            "errors": errors,
            "meta_review": None,
            "current_step": "Meta Review (Failed)",
            "progress_percentage": 93,
        }

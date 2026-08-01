"""
Reviewer Judge Node

Runs after reviewer_panel_node calls fan-in, before meta_reviewer_node.

For each reviewer output:
  - Scores specificity: does the feedback name actual sections, figures, equations,
    or claims from THIS paper — or is it boilerplate that applies to any submission?
  - Flags individual vague items
  - If specificity_score < 0.45, regenerates that reviewer's output with a stricter
    prompt that demands manuscript-specific references (one retry, then passes regardless)

Retried outputs overwrite the original DB rows so meta_reviewer sees clean inputs.
Judge verdicts stored in state as reviewer_judge_output for analysis_metadata.
"""

from __future__ import annotations

import asyncio

from app.workflows.draft_analysis.state import DraftAnalysisState
from app.workflows.draft_analysis.schemas import ReviewerJudgeOutput, ReviewerOutput
from app.workflows.draft_analysis.nodes.reviewer_panel import (
    REVIEWER_PROMPTS,
    build_reviewer_context,
)
from app.core.logging_config import get_logger
from app.core.openai_client import get_async_openai_client, get_completion_params
from app.core.supabase_client import supabase
from app.core.privacy import safe_exception
from app.services.retry_utils import parse_chat_completion_with_retries

logger = get_logger(__name__)
client = None


def _get_client():
    global client
    if client is None:
        client = get_async_openai_client()
    return client

SPECIFICITY_THRESHOLD = 0.45

REVIEWER_JUDGE_PROMPT = """You are a senior program chair evaluating the quality of peer reviews.

A high-quality review:
- Names specific sections by title or number ("In Section 3.2, the authors claim...")
- References actual figures, tables, equations, or algorithms from the paper
- Quotes or closely paraphrases specific claims from the manuscript
- Identifies a limitation that is uniquely true of this paper's design or methodology
- Asks questions that can only be answered by the authors of THIS paper

A low-quality (boilerplate) review:
- Uses phrases like "the authors should clarify their methodology"
- Says "more experiments are needed" without naming which experiments
- Mentions "related work is incomplete" without naming any specific missing papers
- Asks "can you provide more details?" without specifying which details
- Any weakness/question that could be copy-pasted into any other paper's review

For each reviewer, evaluate their output and identify vague items.
specificity_score: 0.0 = entire review is boilerplate; 1.0 = every item is manuscript-specific.
quality_pass = True if specificity_score >= 0.45.
retry_reviewer_ids = list of reviewer_ids whose quality_pass is False."""

RETRY_PREFIX = """IMPORTANT: Your previous review was too generic. Every weakness, question, and limitation
you identify MUST reference specific content from this manuscript:
- Name the exact section (e.g. "Section 4, Experimental Setup")
- Quote or closely paraphrase a specific sentence or claim from the paper
- Name specific figures, tables, or equations if relevant
- If citing missing papers, name the papers explicitly (author, year)

Do NOT write anything that could apply to any other paper. Be specific to THIS manuscript."""


def _format_reviewer_for_judge(ro: dict) -> str:
    lines = [
        f"\n=== REVIEWER: {ro.get('reviewer_id', '?').upper()} ===",
        f"Summary: {ro.get('summary', '')}",
    ]
    for w in (ro.get("weaknesses") or []):
        lines.append(f"  WEAKNESS: {w}")
    for q in (ro.get("questions_to_authors") or []):
        lines.append(f"  QUESTION: {q}")
    for l in (ro.get("limitations_to_address") or []):
        lines.append(f"  LIMITATION: {l}")
    for issue in (ro.get("issues") or []):
        lines.append(
            f"  STRUCTURED ISSUE: {issue.get('section_reference', '')}: "
            f"{issue.get('problem', '')} Action: {issue.get('suggested_action', '')}"
        )
    return "\n".join(lines)


async def _retry_reviewer(state: DraftAnalysisState, reviewer_id: str) -> dict | None:
    """
    Regenerate a single reviewer output with a stricter specificity prompt.
    Returns the new reviewer output dict, or None on failure.
    """
    draft_id = state.get("draft_id", "")
    logger.info(f"[ReviewerJudge] Retrying reviewer={reviewer_id} for draft_id={draft_id}")

    base_prompt = REVIEWER_PROMPTS.get(reviewer_id, "")
    strict_prompt = f"{RETRY_PREFIX}\n\n{base_prompt}"
    context = build_reviewer_context(state, reviewer_id)

    try:
        response = await parse_chat_completion_with_retries(
            _get_client(),
            model="gpt-5.2-chat-latest",
            messages=[
                {"role": "system", "content": strict_prompt},
                {"role": "user", "content": f"Review this paper:\n\n{context}"},
            ],
            max_completion_tokens=2500,
            temperature=0,
            response_format=ReviewerOutput,
            **get_completion_params(),
        )

        output = response.parsed
        for issue in output.issues:
            if issue.problem and issue.problem not in output.weaknesses:
                output.weaknesses.append(issue.problem)

        new_row = {
            "draft_id": draft_id,
            "reviewer_id": reviewer_id,
            "summary": output.summary,
            "strengths": output.strengths,
            "weaknesses": output.weaknesses,
            "questions_to_authors": output.questions_to_authors,
            "limitations_to_address": output.limitations_to_address,
            "issues": [issue.model_dump() for issue in output.issues],
            "rating": output.rating,
            "confidence": output.confidence,
            "recommendation": output.recommendation,
        }

        if not state.get("stage_only", True):
            # Legacy direct persist path. Normal draft analysis publishes atomically later.
            supabase.table("reviewer_panel_outputs") \
                .delete() \
                .eq("draft_id", draft_id) \
                .eq("reviewer_id", reviewer_id) \
                .execute()
            try:
                supabase.table("reviewer_panel_outputs").insert(new_row).execute()
            except Exception as issues_err:
                if "issues" not in str(issues_err).lower():
                    raise
                fallback_row = dict(new_row)
                fallback_row.pop("issues", None)
                supabase.table("reviewer_panel_outputs").insert(fallback_row).execute()

        logger.info(f"[ReviewerJudge] Retry complete for {reviewer_id}: rating={output.rating}")
        return output.model_dump()

    except Exception as exc:
        logger.warning(f"[ReviewerJudge] Retry failed for {reviewer_id}: {exc}")
        return None


async def reviewer_judge_node(state: DraftAnalysisState) -> dict:
    """
    Judge the reviewer outputs for specificity.
    Retry any that fall below threshold, then pass all to meta_reviewer_node.
    """
    draft_id = state.get("draft_id", "")
    reviewer_outputs = state.get("reviewer_outputs") or []

    logger.info(
        f"[ReviewerJudge] Starting for draft_id={draft_id}, "
        f"reviewing {len(reviewer_outputs)} reviewer outputs"
    )

    if not reviewer_outputs:
        logger.warning("[ReviewerJudge] No reviewer outputs — skipping")
        return {
            "reviewer_judge_output": {"panel_quality": "low", "reviewer_scores": [], "retry_reviewer_ids": []},
            "current_step": "Reviewer Judge (Skipped)",
            "progress_percentage": 88,
        }

    # Build context for judge
    context_lines = [
        f"PAPER TYPE: {state.get('paper_type', 'unknown')}",
        f"DRAFT (first 500 chars): {state.get('draft_content', '')[:500]}",
        "\nREVIEWER OUTPUTS TO EVALUATE:",
    ]
    for ro in reviewer_outputs:
        context_lines.append(_format_reviewer_for_judge(ro))
    context = "\n".join(context_lines)

    try:
        response = await parse_chat_completion_with_retries(
            _get_client(),
            model="gpt-5.2-chat-latest",
            messages=[
                {"role": "system", "content": REVIEWER_JUDGE_PROMPT},
                {"role": "user", "content": context[:6000]},
            ],
            max_completion_tokens=1500,
            temperature=0,
            response_format=ReviewerJudgeOutput,
            **get_completion_params(),
        )

        judge_output = response.parsed

        logger.info(
            f"[ReviewerJudge] Scores: "
            + ", ".join(
                f"{s.reviewer_id}={s.specificity_score:.2f}({'PASS' if s.quality_pass else 'FAIL'})"
                for s in judge_output.reviewer_scores
            )
        )

        # Retry failing reviewers in parallel (max 1 retry per reviewer)
        retry_ids = [rid for rid in judge_output.retry_reviewer_ids if rid in
                     {ro.get("reviewer_id") for ro in reviewer_outputs}]

        updated_outputs = list(reviewer_outputs)

        if retry_ids:
            logger.info(f"[ReviewerJudge] Retrying {retry_ids}")
            retry_tasks = [_retry_reviewer(state, rid) for rid in retry_ids]
            retry_results = await asyncio.gather(*retry_tasks, return_exceptions=True)

            for rid, result in zip(retry_ids, retry_results):
                if isinstance(result, Exception) or result is None:
                    logger.warning(f"[ReviewerJudge] Retry for {rid} failed — keeping original")
                    continue
                # Replace the original output for this reviewer_id
                updated_outputs = [
                    result if ro.get("reviewer_id") == rid else ro
                    for ro in updated_outputs
                ]

        judge_dict = judge_output.model_dump()

        logger.info(
            f"[ReviewerJudge] Complete: panel_quality={judge_output.panel_quality}, "
            f"retried={retry_ids}"
        )

        # Write to judged_reviewer_outputs (plain field, no reducer) not reviewer_outputs
        # (which has an additive reducer and would double-append the list).
        return {
            "judged_reviewer_outputs": updated_outputs,
            "reviewer_judge_output": judge_dict,
            "current_step": "Reviewer Judge",
            "progress_percentage": 88,
        }

    except Exception as exc:
        logger.warning("[ReviewerJudge] Failed (non-fatal, passing through): %s", safe_exception(exc))
        return {
            "reviewer_judge_output": {"error": safe_exception(exc), "panel_quality": "medium"},
            "current_step": "Reviewer Judge (Failed)",
            "progress_percentage": 88,
        }

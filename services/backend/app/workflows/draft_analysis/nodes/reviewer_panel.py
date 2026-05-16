"""
Reviewer Panel Node

Single async node called 4 times in parallel via LangGraph Send API.
Each call receives a different reviewer_type in state and produces one
ReviewerOutput that is accumulated via the fan-in reducer.

Reviewer types:
  novelty       — contribution clarity, novelty over prior work
  methodology   — experimental design, baselines, statistical validity, reproducibility
  coverage      — literature gaps, missing citations, positioning
  clarity       — writing quality, figure/table, reproducibility from paper alone
"""

from __future__ import annotations

from app.workflows.draft_analysis.state import DraftAnalysisState
from app.workflows.draft_analysis.schemas import ReviewerOutput
from app.core.logging_config import get_logger
from app.core.openai_client import get_async_openai_client, get_completion_params
from app.core.supabase_client import supabase
from app.services.retry_utils import parse_chat_completion_with_retries

logger = get_logger(__name__)
client = None


def _get_client():
    global client
    if client is None:
        client = get_async_openai_client()
    return client

# ---------------------------------------------------------------------------
# Rating calibration block (appended to every reviewer system prompt)
# ---------------------------------------------------------------------------

RATING_CALIBRATION = """
RATING CALIBRATION — use the full scale honestly:
- 10: Award quality, exceptional contribution
- 8-9: Strong accept — clear contribution, solid execution, ready to publish
- 6-7: Weak accept — above threshold but has notable issues
- 5: Borderline — compelling but with a fundamental concern
- 3-4: Weak reject — below threshold, significant issues
- 1-2: Strong reject — fundamental flaws, out of scope, or incomplete

At major venues (ICLR, NeurIPS, CHI), roughly:
- 10-15% of papers reviewed score 8+
- 20-30% score 6-7
- 40-50% score 4-5
- 15-20% score 1-3

If you are inclined to give a 6, ask yourself: would this paper be accepted at the target venue as-is?
If not, it is a 5 or below. Do not default to 6-7. Be honest.

CONFIDENCE SCALE:
- 5: You are an expert in this exact subfield
- 4: Strong familiarity with this research area
- 3: Familiar with related work
- 2: Adjacent area, limited expertise
- 1: Outside your area of expertise
"""

# ---------------------------------------------------------------------------
# Reviewer system prompts
# ---------------------------------------------------------------------------

REVIEWER_PROMPTS: dict[str, str] = {
    "novelty": f"""You are Reviewer A: Novelty & Significance expert.

Your focus: contribution clarity, novelty over prior work, venue appropriateness,
whether claimed contributions actually match the work done.

Key questions to answer:
- Is the core contribution clearly stated and justified?
- Is this incremental improvement or a significant advance?
- Does the paper adequately compare to and position against closely related work?
- Would acceptance of this paper advance the field?

Context you are given: paper type, draft content, claim list.
Do NOT comment on statistical methods or literature gaps — those are other reviewers' jobs.

{RATING_CALIBRATION}""",

    "methodology": f"""You are Reviewer B: Methodology & Technical Soundness expert.

Your focus: experimental design, statistical validity, baseline selection, ablation studies,
reproducibility, and confounds.

Key questions to answer:
- Are baselines appropriate and up-to-date? Are SOTA methods compared?
- Are results statistically significant with proper reporting (p-values, confidence intervals, effect sizes)?
- Are ablations present to justify design choices?
- Can experiments be reproduced? (hyperparameters, seeds, dataset splits, code availability)
- Are there confounds or threats to validity that are unaddressed?

Context you are given: empirical claims, citation quality per claim, structural checks.
Do NOT comment on novelty or literature coverage — those are other reviewers' jobs.

{RATING_CALIBRATION}""",

    "coverage": f"""You are Reviewer C: Related Work & Literature Coverage expert.

Your focus: literature gaps, missing key citations, positioning accuracy,
and whether conflicting evidence in prior work is acknowledged.

Key questions to answer:
- Are important related papers missing? Name them specifically if you know them.
- Is the paper's positioning relative to prior work accurate?
- Are there papers that directly contradict or challenge the claims? Are they discussed?
- Does the related work section adequately distinguish this work from others?

Context you are given: coverage gap analysis, external sources found, claim citation quality.
This gap analysis is the output of automated literature review — your job is to voice it as a human reviewer would.
Do NOT comment on writing clarity or experimental design.

{RATING_CALIBRATION}""",

    "clarity": f"""You are Reviewer D: Clarity, Presentation & Reproducibility expert.

Your focus: writing clarity, figure/table quality, abstract accuracy,
limitations section honesty, and whether the paper is reproducible from text alone.

Key questions to answer:
- Is the abstract an accurate summary of the paper? Does it oversell?
- Are figures and tables self-contained with clear captions?
- Does the paper have a limitations section that is honest (not just one sentence)?
- Can experiments be reproduced without contacting the authors?
- Is technical terminology consistent throughout?

Context you are given: paper structure, word count, section list.
Do NOT comment on novelty, methodology soundness, or literature gaps.

{RATING_CALIBRATION}""",
}

# ---------------------------------------------------------------------------
# Context builders (each reviewer gets tailored context slice)
# ---------------------------------------------------------------------------

def _build_novelty_context(state: DraftAnalysisState) -> str:
    claims = state.get("claims") or []
    contribution_claims = [c for c in claims if c.get("claim_type") in ("theoretical", "methodological")][:8]
    lines = ["\nCONTRIBUTION CLAIMS:"]
    for c in contribution_claims:
        lines.append(f"  • [{c.get('claim_type')}] {c.get('claim_text', '')}")
    return "\n".join(lines)


def _build_methodology_context(state: DraftAnalysisState) -> str:
    claims_with_citations = state.get("claims_with_citations") or []
    empirical = [
        cwc for cwc in claims_with_citations
        if cwc.get("claim", {}).get("claim_type") == "empirical"
    ][:6]
    structural = state.get("structural_feedback") or []

    lines = ["\nEMPIRICAL CLAIMS + CITATION QUALITY:"]
    for cwc in empirical:
        claim = cwc.get("claim", {})
        quality = cwc.get("citation_quality", "unknown")
        lines.append(f"  • [{quality}] {claim.get('claim_text', '')}")

    if structural:
        lines.append("\nSTRUCTURAL CHECKS:")
        for s in structural[:4]:
            lines.append(f"  • {s.get('feedback_text', '')}")

    return "\n".join(lines)


def _build_coverage_context(state: DraftAnalysisState) -> str:
    gaps = state.get("coverage_gaps") or []
    external = state.get("external_sources") or []

    lines = ["\nCOVERAGE GAPS DETECTED:"]
    for g in gaps[:6]:
        severity = g.get("severity", "minor")
        lines.append(f"  • [{severity}] {g.get('description', '')}")

    if external:
        lines.append("\nEXTERNAL SOURCES FOUND (not in author's library):")
        for s in external[:5]:
            lines.append(f"  • {s.get('title', s.get('document_title', ''))}")

    return "\n".join(lines)


def _build_clarity_context(state: DraftAnalysisState) -> str:
    structure = state.get("structure") or {}
    sections = structure.get("sections") or []
    editing = {}
    analysis = state.get("analysis") or {}
    if isinstance(analysis, dict):
        editing = (analysis.get("editing_feedback") or {})

    section_titles = [s.get("title", s.get("type", "?")) for s in sections]
    has_limitations = any(
        "limit" in t.lower() for t in section_titles
    )

    lines = [
        f"\nSTRUCTURE:",
        f"  Sections: {', '.join(section_titles) or 'unknown'}",
        f"  Has limitations section: {has_limitations}",
        f"  Word count: {structure.get('word_count', 'unknown')}",
    ]

    if editing.get("formatting_issues"):
        lines.append("\nFORMATTING ISSUES (Stage 1):")
        for issue in editing["formatting_issues"][:4]:
            lines.append(f"  • {issue.get('issue', '')}")

    return "\n".join(lines)


def build_reviewer_context(state: DraftAnalysisState, reviewer_type: str) -> str:
    structure = state.get("structure") or {}
    sections = structure.get("sections") or []
    section_types = [s.get("type", "?") for s in sections]

    base = f"""DRAFT METADATA:
- Paper type: {state.get('paper_type', 'unknown')}
- Word count: {structure.get('word_count', 'unknown')}
- Sections present: {', '.join(section_types) or 'unknown'}

DRAFT CONTENT (first 4000 chars):
{state.get('draft_content', '')[:4000]}
"""

    builders = {
        "novelty": _build_novelty_context,
        "methodology": _build_methodology_context,
        "coverage": _build_coverage_context,
        "clarity": _build_clarity_context,
    }
    return base + builders[reviewer_type](state)


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------

async def reviewer_panel_node(state: DraftAnalysisState) -> dict:
    """
    Single reviewer node — called 4× in parallel via LangGraph Send API.
    reviewer_type injected into state by Send: {"reviewer_type": "novelty"} etc.
    Returns {"reviewer_outputs": [ReviewerOutput]} which the reducer appends.
    """
    reviewer_type = state.get("reviewer_type", "novelty")
    draft_id = state.get("draft_id", "")

    logger.info(f"[ReviewerPanel] Starting reviewer_type={reviewer_type} draft_id={draft_id}")

    # Idempotency: skip if already generated for this reviewer_type
    try:
        existing = (
            supabase.table("reviewer_panel_outputs")
            .select("id")
            .eq("draft_id", draft_id)
            .eq("reviewer_id", reviewer_type)
            .execute()
        )
        if existing.data:
            logger.info(f"[ReviewerPanel] {reviewer_type} already in DB — skipping")
            # Re-fetch and return cached output
            cached = (
                supabase.table("reviewer_panel_outputs")
                .select("*")
                .eq("draft_id", draft_id)
                .eq("reviewer_id", reviewer_type)
                .single()
                .execute()
            )
            if cached.data:
                return {"reviewer_outputs": [cached.data]}
    except Exception:
        pass  # DB check non-fatal

    system_prompt = REVIEWER_PROMPTS[reviewer_type]
    context = build_reviewer_context(state, reviewer_type)

    try:
        response = await parse_chat_completion_with_retries(
            _get_client(),
            model="gpt-5.2-chat-latest",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Review this paper:\n\n{context}"},
            ],
            max_completion_tokens=2500,
            response_format=ReviewerOutput,
            **get_completion_params(),
        )

        output = response.parsed

        # Persist to DB
        try:
            supabase.table("reviewer_panel_outputs").insert({
                "draft_id": draft_id,
                "reviewer_id": reviewer_type,
                "summary": output.summary,
                "strengths": output.strengths,
                "weaknesses": output.weaknesses,
                "questions_to_authors": output.questions_to_authors,
                "limitations_to_address": output.limitations_to_address,
                "rating": output.rating,
                "confidence": output.confidence,
                "recommendation": output.recommendation,
            }).execute()
        except Exception as db_err:
            logger.warning(f"[ReviewerPanel] DB persist failed for {reviewer_type}: {db_err}")

        logger.info(
            f"[ReviewerPanel] {reviewer_type} complete: "
            f"rating={output.rating}, recommendation={output.recommendation}"
        )

        return {"reviewer_outputs": [output.model_dump()]}

    except Exception as exc:
        logger.error(f"[ReviewerPanel] {reviewer_type} failed: {exc}")
        # Return empty — meta_reviewer handles missing reviewers gracefully
        return {"reviewer_outputs": []}

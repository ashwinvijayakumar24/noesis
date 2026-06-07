"""
Reviewer Panel Node

Single async node called 4 times in parallel via LangGraph Send API.
Each call receives a different reviewer_type in state and produces one
ReviewerOutput that is accumulated via the fan-in reducer.

Reviewer types:
  methodology             — study design, evidence synthesis, statistical validity
  literature_positioning  — contribution, missing literature, positioning
  clarity                 — writing quality, figure/table, reproducibility from text
"""

from __future__ import annotations

import re

from app.workflows.draft_analysis.state import DraftAnalysisState
from app.workflows.draft_analysis.schemas import ReviewerOutput
from app.workflows.draft_analysis.domain_routing import domain_context_block
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

OUTPUT QUALITY REQUIREMENTS:
- Every weakness and question must be specific to this manuscript.
- Prefer section references and short quoted/paraphrased anchors over generic advice.
- Populate the structured `issues` array for the most important 2-5 problems.
- Each issue must include why it matters for acceptance and a concrete author action.
- Obey the manuscript profile's forbidden review standards. Do not demand empirical
  ML, clinical, laboratory, or quantitative standards unless the profile says that
  evidence mode applies to this manuscript.
"""

# ---------------------------------------------------------------------------
# Reviewer system prompts
# ---------------------------------------------------------------------------

REVIEWER_PROMPTS: dict[str, str] = {
    "literature_positioning": f"""You are Reviewer A: Literature, Positioning & Contribution expert.

Your focus: contribution clarity, novelty over prior work, missing key papers,
positioning accuracy, and whether conflicting evidence is acknowledged.

Key questions to answer:
- Is the core contribution clearly stated and justified?
- Is this incremental improvement or a significant advance?
- Does the paper adequately compare to and position against closely related work?
- Would acceptance of this paper advance the field?
- Are important related papers, frameworks, or controversies missing?
- Are claims about prior literature accurate and appropriately qualified?

Context you are given: paper type, draft content, claim list.
Do NOT comment on protocol registration, risk of bias, pooling, or study-design validity — those belong to Reviewer B.

{RATING_CALIBRATION}""",

    "methodology": f"""You are Reviewer B: Methodology & Evidence Soundness expert.

Your focus: study design, evidence synthesis, statistical validity, reproducibility, and confounds.

Key questions to answer:
- Is the manuscript using the right methodological standard for its paper type?
- If the manuscript is conceptual, theoretical, humanities, pedagogy, or essayistic,
  evaluate operational clarity, argumentative support, classroom/artifact specificity,
  and scope conditions instead of demanding datasets, baselines, ablations, or metrics.
- For systematic reviews, are search strategy, eligibility criteria, extraction, risk of bias, heterogeneity, and synthesis handled rigorously?
- For primary empirical/model papers, are baselines appropriate and up-to-date? Are SOTA methods compared?
- Are results statistically significant with proper reporting (p-values, confidence intervals, effect sizes)?
- Are ablations present when this is a model-development paper?
- Can experiments be reproduced? (hyperparameters, seeds, dataset splits, code availability)
- Are there confounds or threats to validity that are unaddressed?

Context you are given: empirical claims, citation quality per claim, structural checks.
Do NOT comment on novelty or literature coverage — those are other reviewers' jobs.

{RATING_CALIBRATION}""",

    "clarity": f"""You are Reviewer D: Clarity, Presentation & Reproducibility expert.

Your focus: writing clarity, figure/table quality, abstract accuracy,
limitations/caveat honesty, and whether the paper is reproducible from text alone.

Key questions to answer:
- Is the abstract an accurate summary of the paper? Does it oversell?
- Are figures and tables self-contained with clear captions?
- Are limitations and caveats honestly discussed? Do not require a dedicated "Limitations" heading for short-letter formats such as PNAS, Nature, or Science.
- Can experiments be reproduced without contacting the authors?
- Is technical terminology consistent throughout?

Context you are given: paper structure, word count, section list.
Do NOT comment on novelty, literature positioning, protocol registration, risk of bias, or statistical methodology.

{RATING_CALIBRATION}""",
}

# ---------------------------------------------------------------------------
# Context builders (each reviewer gets tailored context slice)
# ---------------------------------------------------------------------------

def _build_literature_positioning_context(state: DraftAnalysisState) -> str:
    claims = state.get("claims") or []
    contribution_claims = [c for c in claims if c.get("claim_type") in ("theoretical", "methodological")][:8]
    gaps = state.get("coverage_gaps") or []
    external = state.get("external_sources") or []
    lines = ["\nCONTRIBUTION AND POSITIONING CLAIMS:"]
    for c in contribution_claims:
        lines.append(f"  • [{c.get('claim_type')}] {c.get('claim_text', '')}")
    lines.append("\nCOVERAGE GAPS DETECTED:")
    for g in gaps[:6]:
        severity = g.get("severity", "minor")
        lines.append(f"  • [{severity}] {g.get('description', '')}")

    if external:
        lines.append("\nEXTERNAL SOURCES FOUND (not in author's library):")
        for s in external[:5]:
            lines.append(f"  • {s.get('title', s.get('document_title', ''))}")

    diagnostics = [
        f for f in state.get("diagnostic_findings") or []
        if f.get("finding_type") in {"literature_positioning", "framework_validation"}
    ]
    if diagnostics:
        lines.append("\nDIAGNOSTIC POSITIONING ISSUES:")
        for finding in diagnostics[:8]:
            lines.append(
                f"  • [{finding.get('severity', 'major')}] "
                f"{finding.get('problem', '')} Action: {finding.get('suggested_action', '')}"
            )

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

    diagnostics = [
        f for f in state.get("diagnostic_findings") or []
        if f.get("finding_type") in {"systematic_review", "clinical_ai", "causal_inference"}
    ]
    if diagnostics:
        lines.append("\nPROFILE-AWARE DIAGNOSTICS:")
        for finding in diagnostics[:8]:
            lines.append(
                f"  • [{finding.get('severity', 'major')}] "
                f"{finding.get('section_reference', 'Unknown')}: {finding.get('problem', '')}"
            )

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


def _section_excerpts(draft_content: str, max_chars: int = 1400) -> str:
    """Return compact excerpts from the sections reviewers most need."""
    wanted = [
        "introduction",
        "background",
        "methods",
        "materials and methods",
        "search strategy",
        "results",
        "discussion",
        "conclusions",
        "conclusion",
        "limitations",
    ]
    pattern = re.compile(r"^\s*(#{1,3}\s*)?([A-Z][A-Z /&-]{3,}|[A-Z][A-Za-z /&-]{3,})\s*$", re.MULTILINE)
    matches = list(pattern.finditer(draft_content or ""))
    excerpts: list[str] = []
    for i, match in enumerate(matches):
        title = match.group(2).strip()
        title_norm = title.lower()
        if not any(w in title_norm for w in wanted):
            continue
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(draft_content)
        body = re.sub(r"\s+", " ", draft_content[start:end]).strip()
        if body:
            excerpts.append(f"\n[{title}]\n{body[:max_chars]}")
        if len(excerpts) >= 7:
            break
    if excerpts:
        return "\n".join(excerpts)
    return (draft_content or "")[:5000]


def _profile_context(state: DraftAnalysisState) -> str:
    profile = state.get("manuscript_profile") or {}
    diagnostics = state.get("diagnostic_findings") or []
    lines = [
        "\nMANUSCRIPT PROFILE:",
        f"  Genre: {profile.get('genre', 'unknown')}",
        f"  Study design: {profile.get('study_design', 'unknown')}",
        f"  Domain tags: {', '.join(profile.get('domain_tags') or []) or 'unknown'}",
        f"  Review lenses: {', '.join(profile.get('review_lenses') or []) or 'none'}",
        f"  High-risk checks: {', '.join(profile.get('high_risk_checks') or []) or 'none'}",
    ]
    lines.append(domain_context_block(profile))
    retry_instruction = state.get("quality_retry_instruction")
    if retry_instruction:
        lines.append(f"\nQUALITY RETRY INSTRUCTION:\n{retry_instruction}\n")
    if diagnostics:
        lines.append("\nTOP DIAGNOSTIC FINDINGS:")
        for finding in diagnostics[:10]:
            lines.append(
                f"  • [{finding.get('severity', 'major')}] "
                f"{finding.get('finding_type', 'diagnostic')}: {finding.get('problem', '')}"
            )
    return "\n".join(lines)


def build_reviewer_context(state: DraftAnalysisState, reviewer_type: str) -> str:
    structure = state.get("structure") or {}
    sections = structure.get("sections") or []
    section_types = [s.get("type", "?") for s in sections]

    base = f"""DRAFT METADATA:
- Paper type: {state.get('paper_type', 'unknown')}
- Word count: {structure.get('word_count', 'unknown')}
- Sections present: {', '.join(section_types) or 'unknown'}

{_profile_context(state)}

DRAFT SECTION EXCERPTS:
{_section_excerpts(state.get('draft_content', ''))}
"""

    builders = {
        "literature_positioning": _build_literature_positioning_context,
        "methodology": _build_methodology_context,
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

    # Quality-v2 regenerates panel rows on each analysis run because profile and
    # diagnostic context can change even when draft_id stays the same.

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
        for issue in output.issues:
            if issue.problem and issue.problem not in output.weaknesses:
                output.weaknesses.append(issue.problem)

        if not state.get("stage_only", True):
            # Legacy direct persist path. Normal draft analysis publishes atomically later.
            supabase.table("reviewer_panel_outputs") \
                .delete() \
                .eq("draft_id", draft_id) \
                .eq("reviewer_id", reviewer_type) \
                .execute()
            panel_row = {
                "draft_id": draft_id,
                "reviewer_id": reviewer_type,
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
            try:
                supabase.table("reviewer_panel_outputs").insert(panel_row).execute()
            except Exception as issues_err:
                if "issues" not in str(issues_err).lower():
                    raise
                panel_row.pop("issues", None)
                supabase.table("reviewer_panel_outputs").insert(panel_row).execute()
        else:
            panel_row = None

        logger.info(
            f"[ReviewerPanel] {reviewer_type} complete: "
            f"rating={output.rating}, recommendation={output.recommendation}"
        )

        return {"reviewer_outputs": [output.model_dump()]}

    except Exception as exc:
        logger.error(f"[ReviewerPanel] {reviewer_type} failed: {exc}")
        # Return empty — meta_reviewer handles missing reviewers gracefully
        return {"reviewer_outputs": []}

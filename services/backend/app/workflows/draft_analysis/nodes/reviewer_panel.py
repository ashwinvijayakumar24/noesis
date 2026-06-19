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
from app.workflows.draft_analysis.schemas import (
    ReviewerOutput,
    ReviewerIssue,
    TriggerAuditOutput,
)
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
- Ignore PDF-extraction artifacts: fused words ("crosssectional"), broken hyphenation,
  kerning/spacing glitches, and stray characters are parser noise, NOT author errors —
  never raise them as typos or formatting weaknesses.
- Do not over-index on isolated word choices or a single throwaway sentence. Every
  weakness must be substantive and affect the manuscript's claims, methods, or
  contribution — not stylistic nitpicks.
- anchor_text MUST be an exact, contiguous, copy-paste substring of the manuscript
  (<=200 chars). Do NOT paraphrase, summarize, stitch with ellipses, or fix typos
  in the anchor — copy verbatim.

GROUNDING RULE: The FULL manuscript text is provided below. Before you state that
something is missing/absent/not reported, or demand an experiment, method, or detail —
search the ENTIRE provided text first. If the manuscript already addresses it anywhere
(even briefly, in any section including Methods/Supplement), DO NOT raise it. Only raise
genuinely absent items. Quote the exact sentence you are critiquing.
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

YOUR LANE ONLY: introduction, related work, discussion — contribution and positioning.
FORBIDDEN: Do NOT comment on protocol registration, risk of bias, pooling, statistical
methods, or study-design validity (Reviewer B's lane). Do NOT comment on writing quality,
grammar, or figure clarity (Reviewer D's lane). If a methodology issue also affects
positioning, name it once in one sentence and defer to Reviewer B. Your critiques must be
about novelty, prior-work coverage, and contribution — not method soundness or prose.

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

YOUR LANE ONLY: methods, results interpretation, statistical and study-design validity.
FORBIDDEN: Do NOT comment on novelty, literature coverage, or positioning (Reviewer A's
lane). Do NOT comment on writing clarity, grammar, or exposition (Reviewer D's lane).
Your critiques must be about method soundness and evidence validity — not contribution or prose.

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

YOUR LANE ONLY: exposition, argument structure, reporting completeness, terminology consistency.
FORBIDDEN: Do NOT make causal or statistical claims about the evidence, and do NOT comment
on novelty, literature positioning, protocol registration, risk of bias, or statistical
methodology (other reviewers' lanes). Your job is communication quality, not the science.

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

    # Field-standard audit triggers — domain-specific checks general reviewers miss
    # (issue #19/#20: Sepsis-2->3 definition drift, alert fatigue). Injected ONLY into
    # the methodology reviewer (empirical lane), not all reviewers.
    profile = state.get("manuscript_profile") or {}
    triggers = profile.get("domain_audit_triggers") or []
    if triggers:
        lines.append("\nDOMAIN-SPECIFIC AUDIT CHECKLIST (you MUST evaluate each that applies):")
        for trigger in triggers:
            lines.append(f"  • {trigger}")

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

FULL MANUSCRIPT TEXT (search this entire text before claiming anything is missing):
{(state.get('draft_content', '') or '')[:24000]}
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

# Lane ownership for cross-reviewer dedup: which reviewer "owns" a shared critique.
_LANE_KEYWORDS = {
    "methodology": ("method", "statistic", "sample size", "control", "bias", "design",
                    "confound", "reproducib", "validity", "power", "replicat"),
    "literature_positioning": ("novelty", "contribution", "prior work", "positioning",
                               "related work", "literature", "citation", "seminal", "gap"),
    "clarity": ("clarity", "writing", "exposition", "structure", "terminology",
                "figure", "caption", "readability", "flow", "transition"),
}


def _critique_lane(text: str) -> str | None:
    t = (text or "").lower()
    best, best_hits = None, 0
    for lane, kws in _LANE_KEYWORDS.items():
        hits = sum(1 for kw in kws if kw in t)
        if hits > best_hits:
            best, best_hits = lane, hits
    return best


def deduplicate_cross_reviewer_critiques(reviewer_outputs: list[dict]) -> list[dict]:
    """If two reviewers emit essentially the same critique (text similarity > 0.85),
    keep it only in the reviewer whose lane it belongs to and annotate the duplicate
    out of the other (issue #5: reviewers converge on the same points). Deterministic;
    no LLM call. Mutates copies, returns new list."""
    import re as _re
    from difflib import SequenceMatcher

    def _norm(s: str) -> str:
        return _re.sub(r"[^a-z0-9 ]+", " ", (s or "").lower()).strip()

    outputs = [dict(o) for o in reviewer_outputs or []]
    # Flatten (reviewer_idx, weakness) and find cross-reviewer near-duplicates.
    for i, out_i in enumerate(outputs):
        kept_weaknesses: list[str] = []
        for w in out_i.get("weaknesses") or []:
            wn = _norm(w)
            duplicate_owner = None
            for j, out_j in enumerate(outputs):
                if j == i:
                    continue
                for w2 in out_j.get("weaknesses") or []:
                    if SequenceMatcher(None, wn, _norm(w2)).ratio() > 0.85:
                        lane = _critique_lane(w)
                        owner = lane or out_j.get("reviewer_id") or out_i.get("reviewer_id")
                        # The lane owner keeps it; a non-owner drops it.
                        if owner and out_i.get("reviewer_id") != owner and out_j.get("reviewer_id") == owner:
                            duplicate_owner = owner
                        break
                if duplicate_owner:
                    break
            if duplicate_owner:
                continue  # drop from this non-owner reviewer
            kept_weaknesses.append(w)
        out_i["weaknesses"] = kept_weaknesses
    return outputs


def _trigger_label(trigger: str) -> str:
    """Label = text before the first colon ('protein-level validation: IF ...')."""
    head = (trigger or "").split(":", 1)[0].strip()
    return head or (trigger or "")[:60]


async def audit_domain_triggers(
    triggers: list[str], draft_content: str
) -> list[dict]:
    """Deterministic present/absent checklist over profile-derived audit triggers.

    A single narrow call evaluates ONLY the selected triggers against the full
    manuscript. This decouples trigger detection from the broad methodology
    reviewer (which drops triggers under attention load) — the source of the
    protein-validation appears-1/5-runs variance. Returns the verdict dicts for
    triggers judged ABSENT, so the caller can emit a deterministic issue.
    """
    if not triggers or not (draft_content or "").strip():
        return []

    checklist = "\n".join(f"  - {_trigger_label(t)}: {t}" for t in triggers)
    system = (
        "You are a meticulous methods auditor. For EACH checklist item, decide if the "
        "manuscript already contains the required evidence. Verdict 'present' ONLY if you "
        "can quote verbatim text from the manuscript that satisfies it — otherwise 'absent'. "
        "Use 'not_applicable' only if the item genuinely does not apply to this study type. "
        "Echo the item's label exactly. Do not invent quotes."
    )
    user = (
        f"CHECKLIST (evaluate every item):\n{checklist}\n\n"
        f"MANUSCRIPT:\n{(draft_content or '')[:24000]}"
    )
    try:
        response = await parse_chat_completion_with_retries(
            _get_client(),
            model="gpt-5.2-chat-latest",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_completion_tokens=1800,
            temperature=0,
            response_format=TriggerAuditOutput,
            **get_completion_params(),
        )
        verdicts = response.parsed.verdicts
    except Exception as exc:
        logger.error(f"[TriggerAudit] failed: {exc}")
        return []

    # A 'present' verdict is only trusted if its evidence quote actually appears
    # in the manuscript. Otherwise the model hallucinated coverage — downgrade to
    # absent. This removes the false-present that left protein-validation missing
    # in ~1/5 runs even with the audit in place.
    def _quote_grounded(v) -> bool:
        q = re.sub(r"\s+", " ", (v.evidence_quote or "").strip()).lower()
        if len(q) < 12:
            return False
        return q in re.sub(r"\s+", " ", (draft_content or "")).lower()

    absent = [
        v.model_dump()
        for v in verdicts
        if v.verdict == "absent" or (v.verdict == "present" and not _quote_grounded(v))
    ]
    logger.info(
        f"[TriggerAudit] {len(verdicts)} verdicts, {len(absent)} treated-absent: "
        f"{[v.get('trigger_label') for v in absent]}"
    )
    return absent


# Generic words that appear across many critiques — they must NOT drive trigger
# coverage matching (e.g. 'level'/'validation' wrongly bound 'protein-level
# validation' to a colony-count issue, leaving the real protein issue unprotected).
_TRIGGER_GENERIC_TOKENS = {
    "level", "validation", "risk", "analysis", "study", "data", "assessment",
    "comparison", "specific", "testing", "control", "design", "method", "methods",
    "result", "results", "issue", "concern",
}


def _trigger_covering_issue(label: str, issues: list):
    """Return the existing reviewer issue that BEST matches this trigger, else None.

    Matches on discriminating (non-generic) tokens and binds the issue with the
    most hits — never the first incidental match.
    """
    key_tokens = {
        w for w in re.split(r"[^a-z0-9]+", (label or "").lower())
        if len(w) > 3 and w not in _TRIGGER_GENERIC_TOKENS
    }
    if not key_tokens:
        return None
    best_issue, best_hits = None, 0
    for issue in issues or []:
        text = (
            f"{getattr(issue, 'problem', '')} {getattr(issue, 'suggested_action', '')}"
        ).lower()
        hits = sum(1 for tok in key_tokens if tok in text)
        if hits > best_hits:
            best_hits, best_issue = hits, issue
    return best_issue if best_hits >= 1 else None


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
            temperature=0,
            response_format=ReviewerOutput,
            **get_completion_params(),
        )

        output = response.parsed

        # Deterministic domain-trigger audit (methodology lane only). The broad
        # reviewer above inconsistently surfaces profile-derived triggers; a narrow
        # checklist pass forces a present/absent verdict per trigger and emits a
        # finding for any ABSENT one the reviewer missed. Kills the run-to-run
        # variance (e.g. protein-level validation appearing in only ~1/5 runs).
        if reviewer_type == "methodology":
            triggers = (state.get("manuscript_profile") or {}).get("domain_audit_triggers") or []
            absent = await audit_domain_triggers(triggers, state.get("draft_content", "") or "")
            label_to_trigger = {_trigger_label(t): t for t in triggers}
            for verdict in absent:
                label = verdict.get("trigger_label", "")
                trigger = label_to_trigger.get(label, label)
                covering = _trigger_covering_issue(label, output.issues)
                if covering is not None:
                    # The broad reviewer already raised this trigger. Protect ITS
                    # issue from the downstream LLM absence-verifier (which otherwise
                    # downgrades/drops it) instead of emitting a duplicate.
                    covering.audit_grounded = True
                    continue
                output.issues.append(
                    ReviewerIssue(
                        issue_type="methodology",
                        section_reference="Methods",
                        anchor_text="",
                        problem=f"{label}: the manuscript does not provide the required evidence. {verdict.get('rationale', '')}".strip(),
                        why_it_matters=(
                            "Field-standard methodological requirement that, if unaddressed, "
                            "blocks acceptance. " + (trigger.split(":", 1)[-1].strip() if ":" in trigger else "")
                        ).strip(),
                        suggested_action=f"Provide {label}, or explicitly justify its absence.",
                        confidence=0.85,
                        audit_grounded=True,
                    )
                )

        # Lane enforcement (persona homogeneity): the clarity reviewer keeps drifting
        # into methodology/literature critiques (Gemini eval: clarity reviewer raised
        # T7E1 limits + replication numbers + search methodology). Drop clarity issues
        # whose content clearly belongs to another reviewer's lane — the owning reviewer
        # already covers them. Conservative: only drop when the foreign lane strictly
        # dominates and clarity itself has no signal.
        if reviewer_type == "clarity":
            kept_issues = []
            for issue in output.issues:
                text = f"{issue.problem} {issue.suggested_action}"
                lane = _critique_lane(text)
                clarity_hits = sum(1 for kw in _LANE_KEYWORDS["clarity"] if kw in text.lower())
                if lane in ("methodology", "literature_positioning") and clarity_hits == 0:
                    continue
                kept_issues.append(issue)
            output.issues = kept_issues

        # Evidence gate: drop issues whose anchor_text is non-empty but not verbatim
        try:
            from app.services.draft_evidence_gate import strip_unanchored_findings
            draft_content = state.get("draft_content") or ""
            issue_dicts = [i.model_dump() for i in output.issues]
            filtered = strip_unanchored_findings(issue_dicts, draft_content)
            kept_ids = {id(d) for d in filtered}
            output.issues = [
                issue for issue, d in zip(output.issues, issue_dicts)
                if id(d) in kept_ids
            ]
        except Exception as _gate_exc:
            logger.warning("[ReviewerPanel] Evidence gate skipped: %s", _gate_exc)

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

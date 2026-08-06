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

import asyncio
import os
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
from app.services.progress_publisher import publish_progress
from app.services.retry_utils import parse_chat_completion_with_retries
from app.workflows.draft_analysis.model_routing import model_for

logger = get_logger(__name__)
client = None
REVIEWER_TIMEOUT_SECONDS = int(os.getenv("DRAFT_REVIEWER_TIMEOUT_SECONDS", "180"))


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

TRANSFERABLE REVIEW CHECKLIST:
- Evaluation adequacy: dataset/sample/task coverage must match the claim's scope.
- Baseline and ablation fairness: compare against current relevant alternatives, keep
  runtime/resource/comparison conditions consistent, and ask for ablations only when
  they fit the manuscript's evidence mode.
- Practical applicability: deployment path, user/sample realism, expert effort, and
  operational constraints should be clear when the paper makes practical claims.
- Method clarity: notation, topology/state variables, figures, and tables should be
  self-contained enough for readers to reconstruct the argument or method.
- Limitations: scope constraints, scalability, failure modes, and marginal gains should
  be acknowledged in proportion to the paper's claims.
"""

# ---------------------------------------------------------------------------
# Reviewer persona blocks
#
# PROMPT ORDERING / PREFIX CACHING
# --------------------------------
# OpenAI's automatic prompt cache keys on an exact *token prefix*. The three
# panel calls for one draft share ~95% of their text (calibration block + the
# full manuscript + profile context) and differ only in the persona block and a
# small per-persona context slice. To let that shared text be cached once and
# reused by the other two calls, everything invariant must come FIRST and
# everything persona-specific LAST:
#
#   system : SHARED_REVIEWER_PREAMBLE  (byte-identical for all three personas)
#   user   : shared base context       (metadata + profile + manuscript)
#            then the persona block    (REVIEWER_PERSONAS[reviewer_type])
#            then the persona context  (_build_*_context)
#
# Nothing in the shared prefix may vary per call or per run: no timestamps, no
# uuid/run ids, no set/dict iteration whose order is not fixed. See
# tests/test_prompt_cache_structure.py, which asserts these properties.
# ---------------------------------------------------------------------------

REVIEWER_PERSONAS: dict[str, str] = {
    "literature_positioning": """You are Reviewer A: Literature, Positioning & Contribution expert.

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
""",

    "methodology": """You are Reviewer B: Methodology & Evidence Soundness expert.

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
- For primary empirical/model/mechanistic papers, is the chosen modeling formalism
  justified by the data structure and assumptions, rather than merely applied because
  it is available? Check whether graph/topology, state variables, simulation setup,
  target leakage, unavailable ground-truth parameters, and scope limits are explained
  well enough to support the central claim.
- Do the comparisons test the claimed advantage, not just generic performance? If
  the paper focuses on a restricted regime such as steady state, pooled averages, or
  simplified simulations, does it make that scope constraint explicit in the claims?
- Can experiments be reproduced? (hyperparameters, seeds, dataset splits, code availability)
- Are there confounds or threats to validity that are unaddressed?

Context you are given: empirical claims, citation quality per claim, structural checks.

YOUR LANE ONLY: methods, results interpretation, statistical and study-design validity.
FORBIDDEN: Do NOT comment on novelty, literature coverage, or positioning (Reviewer A's
lane). Do NOT comment on writing clarity, grammar, or exposition (Reviewer D's lane).
Your critiques must be about method soundness and evidence validity — not contribution or prose.
""",

    "clarity": """You are Reviewer D: Clarity, Presentation & Reproducibility expert.

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
""",
}

#: Invariant system prompt for every panel call. Byte-identical across the three
#: personas on purpose — this is the cacheable prefix. Do not interpolate the
#: reviewer type, the draft id, a timestamp, or anything else per-call in here.
SHARED_REVIEWER_PREAMBLE = f"""You are one reviewer on a pre-submission peer-review panel for an academic
manuscript. Your specific reviewer assignment and lane are stated at the END of
the user message — read the manuscript first, then apply your assignment.
{RATING_CALIBRATION}"""

#: Persona block joined with the calibration block, kept for callers that need a
#: single standalone reviewer system prompt (``reviewer_judge``). The panel node
#: itself does NOT use this — it splits the two halves so the calibration text
#: can sit in the shared cacheable prefix.
REVIEWER_PROMPTS: dict[str, str] = {
    reviewer_type: f"{persona}\n{RATING_CALIBRATION}"
    for reviewer_type, persona in REVIEWER_PERSONAS.items()
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

    lines.append("\nTRANSFERABLE MODEL/METHOD AUDIT:")
    lines.append("  • Is the modeling formalism justified by the paper's data structure and assumptions?")
    lines.append("  • Are topology/state variables/simulation parameters described enough to reproduce the method?")
    lines.append("  • Could target variables, unavailable ground-truth parameters, or synthetic setup choices leak the answer?")
    lines.append("  • Do comparisons test the claimed advantage and stated scope constraints?")

    diagnostics = [
        f for f in state.get("diagnostic_findings") or []
        if f.get("finding_type") in {
            "systematic_review",
            "clinical_ai",
            "causal_inference",
            "causal_claim",
            "methodology",
            "deployment",
        }
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


#: Outer cap applied to the compacted manuscript when compaction is enabled.
REVIEWER_MANUSCRIPT_MAX_CHARS = int(
    os.getenv("DRAFT_REVIEWER_MANUSCRIPT_MAX_CHARS", "24000")
)


def reviewer_compaction_enabled() -> bool:
    """True when the reviewer manuscript should be compacted to section excerpts.

    OFF by default. Enabling it cuts reviewer input tokens substantially but the
    reviewers then no longer see the full text, which weakens the GROUNDING RULE
    (they can no longer verify that something really is absent). It is a real
    token/quality trade, not a free win. Read at call time so it can be toggled
    per process and in tests.
    """
    return os.getenv("DRAFT_REVIEWER_COMPACT_MANUSCRIPT", "").strip().lower() in {
        "1", "true", "yes", "on",
    }


def _reviewer_manuscript_text(draft_content: str) -> str:
    if not reviewer_compaction_enabled():
        return draft_content or ""
    return _section_excerpts(draft_content or "")[:REVIEWER_MANUSCRIPT_MAX_CHARS]


# ---------------------------------------------------------------------------
# Per-reviewer section scoping  —  DRAFT_REVIEWER_SCOPED_PANEL
#
# Today all three personas read one manuscript block, and when compaction is on
# that block is a head-first truncation at REVIEWER_MANUSCRIPT_MAX_CHARS. A
# head-first cut removes the *tail* of the paper — which is exactly where the
# discussion and conclusion sit, and those are Reviewer A's declared lane. The
# scoped path spends the same per-persona budget on the sections that persona is
# accountable for instead of on the first 24k chars of the document.
#
# Two properties this must not break:
#   * COVERAGE. Every span of the manuscript must reach at least one persona.
#     A section nobody sees is a regression, not a saving. Sections claimed by
#     no persona therefore go to *every* persona; sections claimed by several
#     are shared.
#
#     THIS PROPERTY DOES NOT HOLD AT THE CURRENT BUDGET, AND THE FLAG IS OFF
#     PARTLY BECAUSE OF IT. Routing unclaimed spans to all three personas is
#     what was supposed to guarantee coverage, and it is the very thing that
#     breaks it: that text is bought three times out of three separate 24k
#     budgets, so distinct capacity collapses toward 24k instead of growing to
#     72k. Measured on the eval corpus, 7 of 15 manuscripts lose text; coverage
#     runs 41%-100% and the median loser sits near 65%. `scoped_coverage_report`
#     computes this exactly and `log_scoped_coverage` records it per run, so the
#     shortfall is never silent. Anyone reviving this needs a rule that does not
#     triple-count unclaimed text — not a larger budget, which would only change
#     the experiment.
#   * CACHEABLE PREFIX. Scoping makes the manuscript block differ per persona,
#     which is the one thing the cross-persona prompt cache cannot tolerate. So
#     the manuscript block is pushed as late as it can go: the system preamble,
#     the draft metadata and the profile block stay byte-identical and remain
#     cacheable, and only the manuscript block onwards diverges.
# ---------------------------------------------------------------------------

SCOPED_PANEL_ENV = "DRAFT_REVIEWER_SCOPED_PANEL"

#: Never let a span that a persona is given collapse to nothing — a 0-char span
#: is an uncovered span.
SCOPED_MIN_SPAN_CHARS = 400

#: Fraction of the budget held back for spans no persona claims, used only when
#: a persona's *own* claimed lane already exceeds the whole budget.
SCOPED_UNCLAIMED_RESERVE_DIVISOR = 10


def scoped_panel_enabled() -> bool:
    """True when each persona should be shown its own lane's sections.

    OFF by default. Read at call time (not at import) so it can be toggled per
    process and per test, matching ``CHUNK_CEILING_GEOMETRY`` and
    ``DRAFT_VALIDATION_CHEAP_PARSE``.
    """
    return (os.getenv(SCOPED_PANEL_ENV) or "").strip().lower() in {
        "1", "true", "yes", "on",
    }


#: Canonical lane -> the personas that declared it in their own prompt text.
#:
#: Derived from ``REVIEWER_PERSONAS`` above, not invented here:
#:   A/literature_positioning — "YOUR LANE ONLY: introduction, related work,
#:     discussion", plus the abstract, where the contribution statement it is
#:     graded on actually lives.
#:   B/methodology — "YOUR LANE ONLY: methods, results interpretation,
#:     statistical and study-design validity".
#:   D/clarity — "YOUR LANE ONLY: exposition, argument structure, reporting
#:     completeness". Only two lanes are *sections* for D: the abstract ("Is the
#:     abstract an accurate summary... does it oversell?") and limitations ("Are
#:     limitations and caveats honestly discussed?"). D's remaining duties are
#:     cross-cutting rather than sectional, so D is carried mostly by the
#:     unclaimed-goes-to-everybody rule below.
SECTION_LANE_OWNERS: dict[str, frozenset[str]] = {
    "abstract": frozenset({"literature_positioning", "clarity"}),
    "introduction": frozenset({"literature_positioning"}),
    "related_work": frozenset({"literature_positioning"}),
    "methods": frozenset({"methodology"}),
    "results": frozenset({"methodology"}),
    "discussion": frozenset({"literature_positioning"}),
    "conclusion": frozenset({"literature_positioning"}),
    "limitations": frozenset({"methodology", "clarity"}),
    "references": frozenset({"literature_positioning"}),
}

#: A span whose lane no persona claims is shown to all of them. This is what
#: makes union coverage total by construction.
UNCLAIMED_LANE_OWNERS = frozenset(REVIEWER_PERSONAS)

#: Section *titles* classify far more reliably than ``structure.sections[].type``
#: does. On the eval corpus the parser types only ~4 of 15 sections usefully and
#: labels the rest ``other`` — "3 GENERALIZATION-IMPROVING MODEL", "4 ALGORITHM
#: AND TRAINING", "5.3 ABLATION EXPERIMENT" all arrive as ``other``. So title
#: patterns are tried first and ``type`` is only the fallback. Order matters:
#: the first pattern that matches wins.
_LANE_TITLE_PATTERNS: tuple[tuple[re.Pattern, str], ...] = tuple(
    (re.compile(pattern, re.IGNORECASE), lane)
    for pattern, lane in (
        (r"limitation|threats?\s+to\s+validity", "limitations"),
        (r"related\s+work|prior\s+work|literature\s+review", "related_work"),
        (r"\babstract\b", "abstract"),
        (r"\bintroduction\b|\bmotivation\b", "introduction"),
        (r"\bbackground\b|\bpreliminar", "introduction"),
        (
            r"method|experimental\s+set|\bsetup\b|implementation|training|"
            r"algorithm|architecture|model\s+structure|materials|"
            r"search\s+strategy|protocol|dataset|data\s+collection|study\s+design",
            "methods",
        ),
        (r"result|experiment|evaluation|ablation|comparison|finding|performance", "results"),
        (r"discussion", "discussion"),
        (r"conclusion|concluding|future\s+work", "conclusion"),
        (r"reference|bibliograph", "references"),
    )
)

#: Fallback classifier for parsers that do emit a usable ``type``.
_TYPE_TO_LANE: dict[str, str] = {
    "abstract": "abstract",
    "introduction": "introduction",
    "related_work": "related_work",
    "methods": "methods",
    "results": "results",
    "discussion": "discussion",
    "conclusion": "conclusion",
    "references": "references",
}


def section_lane(title: str, section_type: str | None = None) -> str | None:
    """Canonical lane for one section, or None when no persona claims it."""
    for pattern, lane in _LANE_TITLE_PATTERNS:
        if pattern.search(title or ""):
            return lane
    return _TYPE_TO_LANE.get((section_type or "").strip().lower())


def manuscript_spans(state: DraftAnalysisState) -> list[dict]:
    """Partition ``draft_content`` into labelled spans, losing not one byte.

    Section *text* is deliberately taken from ``draft_content`` rather than from
    ``structure.sections[].content``: ``core.privacy.sanitize_draft_structure``
    strips ``content`` (and ``paragraphs``) before the structure is stored, so a
    DB-restored structure carries titles and types but no text. Titles, though,
    survive that strip and are locatable in ``draft_content`` — on the eval
    corpus 94-99% of section titles appear verbatim in the draft, against 55-100%
    for ``content``. So the structure supplies the *labels* and the draft
    supplies the *text*.

    Spans tile the document end to end: everything before the first located
    title is one unlabelled span, then each title runs to the next one. The
    concatenation of the spans is ``draft_content`` exactly, which is what makes
    the coverage invariant checkable rather than approximate.

    Returns [] when the structure is unusable, which is the caller's signal to
    fall back to today's unscoped behaviour.
    """
    draft = state.get("draft_content") or ""
    sections = (state.get("structure") or {}).get("sections") or []
    if not draft or not sections:
        return []

    # Titles are matched in document order with a monotonic cursor. That both
    # keeps the spans well ordered and silently drops the duplicate section rows
    # some parsers emit (docling repeats the abstract under two ids).
    marks: list[tuple[int, str, str | None]] = []
    cursor = 0
    for section in sections:
        if not isinstance(section, dict):
            continue
        title = (section.get("title") or "").strip()
        if len(title) < 3:
            continue
        index = draft.find(title, cursor)
        if index < 0:
            continue
        marks.append((index, title, section.get("type")))
        cursor = index + len(title)

    if len(marks) < 2:
        return []

    spans: list[dict] = []
    if marks[0][0] > 0:
        spans.append({
            "title": "",
            "lane": None,
            "owners": UNCLAIMED_LANE_OWNERS,
            "text": draft[: marks[0][0]],
        })
    for i, (start, title, section_type) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(draft)
        lane = section_lane(title, section_type)
        spans.append({
            "title": title,
            "lane": lane,
            "owners": SECTION_LANE_OWNERS.get(lane) if lane else UNCLAIMED_LANE_OWNERS,
            "text": draft[start:end],
        })
    return spans


def _allocate_span_budget(lengths: list[int], budget: int) -> list[int]:
    """Split ``budget`` over spans by size, never zeroing a span.

    Each span first gets a floor (or its full length if shorter), then the
    remainder is shared out in proportion to what each span still wants. This is
    the whole point of the change: a head-first ``[:budget]`` spends everything
    on whatever happens to come first, so the tail is dropped entirely.
    """
    if budget <= 0 or not lengths:
        return [0] * len(lengths)
    if sum(lengths) <= budget:
        return list(lengths)

    floor = min(SCOPED_MIN_SPAN_CHARS, budget // len(lengths))
    base = [min(length, floor) for length in lengths]
    remaining = budget - sum(base)
    residual = [length - b for length, b in zip(lengths, base)]
    residual_total = sum(residual)
    if remaining <= 0 or residual_total <= 0:
        return base
    return [
        b + int(remaining * r / residual_total)
        for b, r in zip(base, residual)
    ]


def persona_demand(spans: list[dict], reviewer_type: str) -> int:
    """Chars this persona would need to see every span assigned to it."""
    return sum(len(s["text"]) for s in spans if reviewer_type in s["owners"])


def persona_allowance(spans: list[dict], reviewer_type: str) -> dict[int, int] | None:
    """Chars of each span (by index) this persona is budgeted, or None if none.

    Budget is the same ``REVIEWER_MANUSCRIPT_MAX_CHARS`` every persona gets
    today; it is spent on this persona's lane rather than on the head of the
    document. Claimed spans are funded before unclaimed ones, so a reviewer's
    own lane is never cut in order to show it text outside that lane.

    Truncation is always a prefix cut, so an allowance of *n* means the first
    *n* chars of the span reach this persona. That is what makes union coverage
    exactly computable — see ``scoped_coverage_report``.
    """
    mine = [i for i, s in enumerate(spans) if reviewer_type in s["owners"]]
    if not mine:
        return None

    budget = REVIEWER_MANUSCRIPT_MAX_CHARS
    claimed = [i for i in mine if spans[i]["lane"] is not None]
    unclaimed = [i for i in mine if spans[i]["lane"] is None]
    claimed_total = sum(len(spans[i]["text"]) for i in claimed)

    if claimed_total >= budget:
        reserve = min(
            sum(len(spans[i]["text"]) for i in unclaimed),
            budget // SCOPED_UNCLAIMED_RESERVE_DIVISOR,
        )
        claimed_budget = budget - reserve
    else:
        reserve = budget - claimed_total
        claimed_budget = claimed_total

    allowance: dict[int, int] = {}
    for group, group_budget in ((claimed, claimed_budget), (unclaimed, reserve)):
        sizes = _allocate_span_budget(
            [len(spans[i]["text"]) for i in group], group_budget
        )
        for index, size in zip(group, sizes):
            allowance[index] = size
    return allowance


def scoped_coverage_report(state: DraftAnalysisState) -> dict | None:
    """How much of the manuscript the whole panel actually sees. None if unscoped.

    THE BUDGET DOES NOT ADD UP, AND THIS IS WHERE THAT BECOMES VISIBLE.
    Three personas x 24k is 72k of *slots*, not 72k of distinct manuscript: a
    span claimed by two personas is paid for twice, and a span claimed by nobody
    goes to all three and is paid for three times. Since the unclaimed-goes-to-
    everybody rule is exactly what most manuscripts trigger most often (the
    parser labels the majority of real sections ``other``), distinct capacity
    collapses toward a single 24k budget rather than expanding to 72k. On the
    eval corpus, 7 of 15 manuscripts lose text, the worst covering 41% of its
    141k chars.

    That is a property of the design, not a bug in the arithmetic, and the fix
    is not a bigger budget — it is a scoping rule that does not triple-count the
    text nobody claims. Until then this report exists so the loss is recorded
    rather than silently absorbed into a plausible-looking review.

    Because truncation is always a prefix cut, the union across personas of what
    is seen of a span is just the largest single allowance for it, so
    ``covered_chars`` is exact, not an estimate.
    """
    spans = manuscript_spans(state)
    if not spans:
        return None

    best: list[int] = [0] * len(spans)
    for reviewer_type in REVIEWER_PERSONAS:
        allowance = persona_allowance(spans, reviewer_type)
        if not allowance:
            continue
        for index, size in allowance.items():
            best[index] = max(best[index], min(size, len(spans[index]["text"])))

    dropped = [
        {
            "title": spans[i]["title"],
            "lane": spans[i]["lane"],
            "dropped_chars": len(spans[i]["text"]) - best[i],
        }
        for i in range(len(spans))
        if best[i] < len(spans[i]["text"])
    ]
    manuscript_chars = sum(len(s["text"]) for s in spans)
    covered_chars = sum(best)
    return {
        "manuscript_chars": manuscript_chars,
        "covered_chars": covered_chars,
        "dropped_chars": manuscript_chars - covered_chars,
        "coverage_ratio": (covered_chars / manuscript_chars) if manuscript_chars else 1.0,
        "spans": len(spans),
        "dropped_spans": dropped,
    }


def log_scoped_coverage(state: DraftAnalysisState, reviewer_type: str) -> dict | None:
    """Record any manuscript text the scoped panel drops. Never silent.

    Text vanishing between the parser and the reviewer is the same class of
    defect as a swallowed exception: the run still produces a confident-looking
    review, from an input nobody was told was incomplete.
    """
    report = scoped_coverage_report(state)
    if not report:
        return None
    if report["dropped_chars"] <= 0:
        logger.info(
            "[ReviewerPanel] scoped coverage complete: %s spans, %s chars, reviewer=%s",
            report["spans"], report["manuscript_chars"], reviewer_type,
        )
        return report
    worst = sorted(
        report["dropped_spans"], key=lambda d: d["dropped_chars"], reverse=True
    )[:5]
    logger.warning(
        "[ReviewerPanel] SCOPED COVERAGE SHORTFALL reviewer=%s: %.1f%% of the "
        "manuscript reaches the panel (%s of %s chars); %s of %s spans truncated "
        "for every reviewer. Largest losses: %s",
        reviewer_type,
        100 * report["coverage_ratio"],
        report["covered_chars"],
        report["manuscript_chars"],
        len(report["dropped_spans"]),
        report["spans"],
        ", ".join(
            f"{d['title'][:40]!r}[{d['lane']}] -{d['dropped_chars']}c" for d in worst
        ),
    )
    return report


def scoped_manuscript_text(
    state: DraftAnalysisState, reviewer_type: str
) -> str | None:
    """This persona's manuscript block, or None when scoping cannot apply."""
    spans = manuscript_spans(state)
    if not spans:
        return None
    allowance = persona_allowance(spans, reviewer_type)
    if allowance is None:
        return None

    parts: list[str] = []
    for index in sorted(allowance):  # document order
        size = allowance[index]
        text = spans[index]["text"]
        if size >= len(text):
            parts.append(text)
        elif size > 0:
            parts.append(f"{text[:size]}\n[... section truncated ...]")
    return "".join(parts)


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


def build_cacheable_reviewer_head(state: DraftAnalysisState) -> str:
    """Everything before the manuscript block: metadata and profile.

    Byte-identical for all three personas under either flag setting — this is
    the part of the prefix the cross-persona prompt cache keeps even when
    scoping is on. Must stay free of anything that varies per call or per run.
    """
    structure = state.get("structure") or {}
    sections = structure.get("sections") or []
    section_types = [s.get("type", "?") for s in sections]

    return f"""DRAFT METADATA:
- Paper type: {state.get('paper_type', 'unknown')}
- Word count: {structure.get('word_count', 'unknown')}
- Sections present: {', '.join(section_types) or 'unknown'}

{_profile_context(state)}

"""


#: Header for the unscoped manuscript block. Byte-for-byte what it has always
#: been — the flag-off path must reproduce today's message exactly.
_FULL_MANUSCRIPT_HEADER = (
    "FULL MANUSCRIPT TEXT (search this entire text before claiming anything is missing):\n"
)

#: Header for a scoped block. The system preamble's GROUNDING RULE still says
#: "the FULL manuscript text is provided below", and it cannot be edited without
#: breaking the byte-identical system message the cache keys on — so the caveat
#: is stated here instead, on the persona-specific side of the boundary, where
#: it costs no shared prefix.
_SCOPED_MANUSCRIPT_HEADER = (
    "MANUSCRIPT TEXT — THE SECTIONS ASSIGNED TO YOUR LANE (the remaining sections\n"
    "are assigned to the other reviewers on this panel; do NOT report something as\n"
    "missing from the manuscript merely because it is not in the text below):\n"
)


def build_manuscript_block(
    state: DraftAnalysisState, reviewer_type: str | None = None
) -> str:
    """The manuscript block. Scoped to this persona's lane only when enabled.

    Falls back to the shared unscoped block whenever scoping cannot apply —
    no reviewer_type, flag off, or a structure that yields no usable spans.
    """
    if reviewer_type is not None and scoped_panel_enabled():
        scoped = scoped_manuscript_text(state, reviewer_type)
        if scoped is not None:
            return f"{_SCOPED_MANUSCRIPT_HEADER}{scoped}\n"
    manuscript = _reviewer_manuscript_text(state.get("draft_content", "") or "")
    return f"{_FULL_MANUSCRIPT_HEADER}{manuscript}\n"


def build_shared_reviewer_prefix(
    state: DraftAnalysisState, reviewer_type: str | None = None
) -> str:
    """Cacheable head plus the manuscript block.

    With ``reviewer_type`` omitted, or with ``DRAFT_REVIEWER_SCOPED_PANEL`` off,
    this returns exactly the string it always has.
    """
    return build_cacheable_reviewer_head(state) + build_manuscript_block(
        state, reviewer_type
    )


_CONTEXT_BUILDERS = {
    "literature_positioning": _build_literature_positioning_context,
    "methodology": _build_methodology_context,
    "clarity": _build_clarity_context,
}


def build_reviewer_context(state: DraftAnalysisState, reviewer_type: str) -> str:
    """Shared prefix first, then this reviewer's tailored context slice."""
    return build_shared_reviewer_prefix(state, reviewer_type) + _CONTEXT_BUILDERS[reviewer_type](state)


def build_reviewer_messages(
    state: DraftAnalysisState, reviewer_type: str
) -> list[dict[str, str]]:
    """Assemble the panel call's messages with the variable persona block LAST.

    Everything before ``YOUR REVIEWER ASSIGNMENT`` — the system preamble, the
    draft metadata, the profile block and the manuscript — is byte-identical for
    all three personas, so calls 2 and 3 hit the prompt cache for it.

    With ``DRAFT_REVIEWER_SCOPED_PANEL`` on the manuscript block varies per
    persona, so the cacheable boundary moves back to the end of the profile
    block (``build_cacheable_reviewer_head``). Everything before that is still
    byte-identical; the traded-away discount is exactly the manuscript.
    """
    return [
        {"role": "system", "content": SHARED_REVIEWER_PREAMBLE},
        {
            "role": "user",
            "content": (
                f"Review this paper:\n\n{build_reviewer_context(state, reviewer_type)}"
                f"\n\nYOUR REVIEWER ASSIGNMENT:\n{REVIEWER_PERSONAS[reviewer_type]}"
            ),
        },
    ]


_ABSENCE_PATTERNS = (
    r"\bmissing\b",
    r"\bnot specified\b",
    r"\bnot reported\b",
    r"\bnot provided\b",
    r"\bnot described\b",
    r"\bnot stated\b",
    r"\bwithout reporting\b",
    r"\bno concrete\b",
    r"\bno explicit\b",
    r"\bno single\b",
    r"\bno ablation\b",
    r"\bno baseline\b",
    r"\blimited discussion\b",
    r"\binsufficient discussion\b",
    r"\blacks?\b",
    r"\bdoes not include\b",
    r"\bdoesn't include\b",
    r"\bfails to include\b",
    r"\babsent\b",
)

_CONTRADICTION_TERMS = {
    "hyperparameter": (
        "hyperparameter", "learning rate", "batch size", "epochs", "optimizer",
        "dropout", "weight decay", "seed", "random seed",
    ),
    "ablation": ("ablation study", "ablation results", "we ablate", "we perform ablation", "ablated"),
    "baseline": ("baseline model", "baseline method", "compared against", "comparison method", "state-of-the-art baseline"),
    "runtime": ("runtime", "running time", "wall-clock", "latency", "throughput", "gpu hours"),
    "scalability": ("scalability", "scales to", "scaling behavior", "computational complexity", "asymptotic"),
    "limitation": ("limitation", "limitations", "threats to validity"),
    "dataset": ("dataset", "datasets", "sample", "participants", "corpus", "benchmark"),
    "code": ("code", "implementation", "repository", "github", "artifact"),
    "notation": ("notation", "variables", "symbols", "state variables", "topology"),
    "deployment": ("deployment", "deploy", "practical", "real-world", "operator", "user study"),
    "seed_uncertainty_reporting": (
        "uncertainty", "variability", "variance", "standard deviation",
        "standard deviations", "std", "mean", "averaged over", "seeds",
        "random seeds",
    ),
    "consolidated_definition": (
        "single consolidated definition", "full forward-pass equation",
        "algorithm box", "complete model definition", "formal complete description",
        "complete description", "final model", "as follows",
    ),
    "neighbor_kernel_related_work": (
        "classical kernel", "kernel regression", "learned metric knn", "knn",
        "neighbor-based", "kernel methods", "deep kernel learning", "dknr",
        "dnnr", "local learning",
    ),
}

_ANYWHERE_CONTRADICTION_FAMILIES = {
    "consolidated_definition",
    "neighbor_kernel_related_work",
    "seed_uncertainty_reporting",
}


def _norm_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _is_absence_style_claim(text: str) -> bool:
    normalized = _norm_text(text)
    return any(re.search(pattern, normalized) for pattern in _ABSENCE_PATTERNS)


def _contradiction_families(text: str) -> list[str]:
    normalized = _norm_text(text)
    families: list[str] = []
    for family, terms in _CONTRADICTION_TERMS.items():
        if any(term in normalized for term in terms):
            families.append(family)
    return families


def _issue_contradicted_by_full_manuscript(issue: ReviewerIssue, draft_content: str) -> tuple[bool, str]:
    issue_text = " ".join(
        part for part in (issue.problem, issue.why_it_matters, issue.suggested_action)
        if part
    )
    if getattr(issue, "audit_grounded", False) or not _is_absence_style_claim(issue_text):
        return False, ""

    families = _contradiction_families(issue_text)
    if not families:
        return False, ""

    full_text = _norm_text(draft_content)
    head_text = _norm_text((draft_content or "")[:24000])
    later_text = _norm_text((draft_content or "")[24000:])
    for family in families:
        terms = _CONTRADICTION_TERMS[family]
        if any(term in full_text for term in terms):
            if family in _ANYWHERE_CONTRADICTION_FAMILIES:
                return True, f"absence claim contradicted by manuscript text mentioning {family}"
            location = "later manuscript text" if any(term in later_text for term in terms) else "manuscript text"
            if any(term in later_text for term in terms) or not any(term in head_text for term in terms):
                return True, f"absence claim contradicted by {location} mentioning {family}"
    return False, ""


def _filter_contradicted_absence_issues(issues: list[ReviewerIssue], draft_content: str) -> list[ReviewerIssue]:
    kept: list[ReviewerIssue] = []
    for issue in issues or []:
        contradicted, reason = _issue_contradicted_by_full_manuscript(issue, draft_content)
        if contradicted:
            logger.info("[ReviewerPanel] Dropped absence-style issue: %s", reason)
            continue
        kept.append(issue)
    return kept


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


def _fallback_reviewer_output(reviewer_type: str, reason: str) -> ReviewerOutput:
    return ReviewerOutput(
        reviewer_id=reviewer_type,
        summary=(
            "This reviewer could not complete within the analysis deadline. "
            "The final report is based on the completed reviewer lanes and deterministic checks."
        ),
        strengths=[],
        weaknesses=[reason],
        questions_to_authors=[],
        limitations_to_address=[],
        issues=[],
        rating=5,
        confidence=1,
        recommendation="major_revision",
    )


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
        f"MANUSCRIPT:\n{draft_content or ''}"
    )
    try:
        response = await parse_chat_completion_with_retries(
            _get_client(),
            model=model_for("reviewer_panel", "gpt-5.2-chat-latest"),
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
    if draft_id:
        try:
            await publish_progress(
                draft_id,
                "reviewer_panel",
                84,
                f"Reviewer panel running: {reviewer_type.replace('_', ' ')}",
            )
        except Exception:
            pass

    # Quality-v2 regenerates panel rows on each analysis run because profile and
    # diagnostic context can change even when draft_id stays the same.

    # Invariant system prompt + shared-prefix-first user message so the three
    # parallel panel calls share a cacheable token prefix. See the ordering note
    # above REVIEWER_PERSONAS.
    messages = build_reviewer_messages(state, reviewer_type)

    # Scoping can drop manuscript text that reaches no reviewer at all. Record
    # it before the call so a shortfall is on the record next to the review it
    # produced, rather than inferred later from a suspiciously thin report.
    if scoped_panel_enabled():
        try:
            log_scoped_coverage(state, reviewer_type)
        except Exception as _coverage_exc:  # never block the panel on telemetry
            logger.warning(
                "[ReviewerPanel] scoped coverage accounting failed: %s", _coverage_exc
            )

    try:
        response = await asyncio.wait_for(
            parse_chat_completion_with_retries(
                _get_client(),
                model=model_for("reviewer_panel", "gpt-5.2-chat-latest"),
                messages=messages,
                max_completion_tokens=2500,
                temperature=0,
                response_format=ReviewerOutput,
                **get_completion_params(),
            ),
            timeout=REVIEWER_TIMEOUT_SECONDS,
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

        output.issues = _filter_contradicted_absence_issues(
            output.issues,
            state.get("draft_content") or "",
        )

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
        if draft_id:
            try:
                await publish_progress(
                    draft_id,
                    "reviewer_panel",
                    87,
                    f"Reviewer complete: {reviewer_type.replace('_', ' ')}",
                )
            except Exception:
                pass

        return {"reviewer_outputs": [output.model_dump()]}

    except asyncio.TimeoutError:
        reason = f"{reviewer_type} reviewer timed out after {REVIEWER_TIMEOUT_SECONDS}s"
        logger.error("[ReviewerPanel] %s", reason)
        if draft_id:
            try:
                await publish_progress(
                    draft_id,
                    "reviewer_panel",
                    87,
                    f"Reviewer timed out: {reviewer_type.replace('_', ' ')}; continuing degraded",
                )
            except Exception:
                pass
        output = _fallback_reviewer_output(reviewer_type, reason)
        return {"reviewer_outputs": [output.model_dump()]}

    except Exception as exc:
        logger.error(f"[ReviewerPanel] {reviewer_type} failed: {exc}")
        output = _fallback_reviewer_output(reviewer_type, f"{reviewer_type} reviewer failed")
        return {"reviewer_outputs": [output.model_dump()]}

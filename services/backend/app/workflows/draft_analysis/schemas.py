"""
Pydantic v2 output schemas for all LangGraph draft-analysis nodes.

Use with OpenAI structured outputs:
    result = await client.beta.chat.completions.parse(
        response_format=SomeOutputModel, ...
    )
    parsed = result.parsed  # fully typed, zero parse failures
"""

from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class StrictOutputModel(BaseModel):
    """Base class for OpenAI structured outputs; reject model drift loudly."""
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Stage 1 — mechanical editing (stage1_editing.py)
# ---------------------------------------------------------------------------

class AbsenceVerdict(StrictOutputModel):
    """One verdict for a single absence-claiming revision task (Prong B LLM verifier)."""
    index: int
    verdict: Literal["addressed", "partial", "absent"]
    evidence: str = ""


class AbsenceVerification(StrictOutputModel):
    """Batched LLM entailment output for false-absence detection."""
    items: list[AbsenceVerdict]


class AnchorSpan(StrictOutputModel):
    """One repaired anchor: the exact verbatim manuscript span for a task, or 'GLOBAL'."""
    index: int
    verbatim_span: str


class AnchorRepair(StrictOutputModel):
    """Batched LLM anchor-repair output (verbatim-anchor real fix)."""
    items: list[AnchorSpan]


class TaskClusters(StrictOutputModel):
    """Batched LLM semantic-dedup output: each inner list is a cluster of task indices
    that address the SAME underlying flaw and should consolidate into one revision."""
    clusters: list[list[int]]


class GrammarIssue(StrictOutputModel):
    text: str
    issue: str
    suggestion: str
    section: str = ""


class CitationIssue(StrictOutputModel):
    text: str
    issue: str
    suggestion: str


class FormattingIssue(StrictOutputModel):
    issue: str
    location: str
    suggestion: str


class StructuralNote(StrictOutputModel):
    note: str
    severity: Literal["minor", "suggestion"] = "minor"


class Stage1EditingOutput(StrictOutputModel):
    grammar_issues: list[GrammarIssue] = Field(default_factory=list)
    citation_issues: list[CitationIssue] = Field(default_factory=list)
    formatting_issues: list[FormattingIssue] = Field(default_factory=list)
    structural_notes: list[StructuralNote] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Claim extraction node
# ---------------------------------------------------------------------------

class ExtractedClaim(StrictOutputModel):
    claim_text: str
    claim_type: Literal["empirical", "theoretical", "methodological"]
    section_location: str
    rhetorical_role: Literal[
        "background_claim",
        "prior_work_claim",
        "method_claim",
        "result_finding",
        "discussion_synthesis",
        "conclusion_summary",
    ] = "background_claim"
    importance_score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    requires_citation: bool = True
    weakness_reason: str = ""


class ClaimExtractionOutput(StrictOutputModel):
    claims: list[ExtractedClaim] = Field(default_factory=list)
    total_claims: int = 0
    extraction_notes: str = ""


# ---------------------------------------------------------------------------
# Manuscript profile and diagnostic findings
# ---------------------------------------------------------------------------

class ManuscriptProfileOutput(StrictOutputModel):
    genre: Literal[
        "systematic_review",
        "empirical_study",
        "methods_paper",
        "theory_framework",
        "theoretical_article",
        "methods_article",
        "legal_policy_analysis",
        "pedagogical_conceptual",
        "conceptual_article",
        "case_study",
        "review_article",
        "literature_review",
        "unknown",
    ] = "unknown"
    study_design: str = ""
    domain_tags: list[str] = Field(default_factory=list)
    contribution_types: list[str] = Field(default_factory=list)
    review_lenses: list[str] = Field(default_factory=list)
    retrieval_domains: list[str] = Field(default_factory=list)
    high_risk_checks: list[str] = Field(default_factory=list)
    rationale: str = ""


class DiagnosticFinding(StrictOutputModel):
    finding_type: Literal[
        "systematic_review",
        "clinical_ai",
        "framework_validation",
        "causal_inference",
        "literature_positioning",
        "materials_literature_positioning",
        "materials_degradation",
        "materials_evidence",
        "reproducibility",
        "clarity",
    ]
    severity: Literal["critical", "major", "minor"]
    section_reference: str = ""
    anchor_text: str = ""
    problem: str
    why_it_matters: str
    suggested_action: str
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)


class DiagnosticFindingsOutput(StrictOutputModel):
    findings: list[DiagnosticFinding] = Field(default_factory=list)
    summary: str = ""


class RevisionTask(StrictOutputModel):
    id: str
    source_type: Literal["diagnostic", "reviewer_issue", "claim", "gap", "structural"]
    task_type: Literal[
        "citation",
        "methodology",
        "literature_positioning",
        "causal_claim",
        "framework_validation",
        "clarity",
        "reproducibility",
        "deployment",
        "other",
    ] = "other"
    severity: Literal["critical", "major", "minor", "suggestion"] = "major"
    priority: Literal["high", "medium", "low"] = "medium"
    section: str = ""
    anchor_text: str = ""
    line_number: Optional[int] = None
    page_number: Optional[int] = None
    paragraph_index: Optional[int] = None
    char_start: Optional[int] = None
    char_end: Optional[int] = None
    problem: str
    why_it_matters: str = ""
    suggested_action: str
    source_ids: list[str] = Field(default_factory=list)
    suggested_sources: list[dict] = Field(default_factory=list)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    status: Literal["new", "saved", "dismissed"] = "new"


# ---------------------------------------------------------------------------
# Citation mapping node  (assess_citation_quality)
# ---------------------------------------------------------------------------

class CitationEntry(StrictOutputModel):
    document_id: str
    document_title: str
    relevance: Literal["strong", "moderate", "weak", "contradicts"]
    reasoning: str


class CitationMappingOutput(StrictOutputModel):
    overall_quality: Literal["strong", "moderate", "weak", "none", "unknown"] = "unknown"
    citations: list[CitationEntry] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    recommendation: str = ""


# ---------------------------------------------------------------------------
# Gap detection node
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Reviewer feedback node
# ---------------------------------------------------------------------------

class FeedbackItem(StrictOutputModel):
    feedback_type: Literal["strength", "weakness", "question", "suggestion"]
    feedback_text: str
    severity: Literal["critical", "major", "minor", "suggestion"]
    section_reference: str = ""
    target_claim_id: Optional[str] = None
    target_gap_id: Optional[str] = None
    specific_issue: str = ""
    suggested_improvements: list[str] = Field(default_factory=list)
    cited_papers: list[str] = Field(default_factory=list)


class StructuralCheckItem(StrictOutputModel):
    check_type: Literal[
        "abstract_body_mismatch",
        "causal_overclaim",
        "statistical_incompleteness",
        "missing_sota",
        "methods_reproducibility",
        "weak_limitations",
    ]
    severity: Literal["critical", "major", "minor"]
    section_reference: str = ""
    specific_issue: str
    feedback_text: str
    suggested_improvements: list[str] = Field(default_factory=list)


class StructuralChecksOutput(StrictOutputModel):
    checks: list[StructuralCheckItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Phase 3 — peer review panel
# ---------------------------------------------------------------------------

class EditorPassOutput(StrictOutputModel):
    proceed_to_review: bool = True
    fatal_flaws: list[str] = Field(default_factory=list)
    scope_appropriate: bool = True
    writing_quality: Literal["publishable", "needs_revision", "major_revision"] = "needs_revision"
    notes: str = ""


class ReviewerIssue(StrictOutputModel):
    issue_type: Literal[
        "methodology",
        "coverage",
        "causal_claim",
        "positioning",
        "framework_validation",
        "reproducibility",
        "clarity",
        "deployment",
        "other",
    ] = "other"
    section_reference: str = ""
    anchor_text: str = ""
    problem: str
    why_it_matters: str
    suggested_action: str
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    audit_grounded: bool = Field(
        default=False,
        description="True for deterministic domain-trigger audit findings (already grounded-entailment verified; exempt from re-verification).",
    )


class ReviewerOutput(StrictOutputModel):
    reviewer_id: Literal[
        "methodology",
        "clarity",
        "literature_positioning",
        "novelty",
        "coverage",
    ]
    summary: str = Field(description="2-3 sentence summary from this reviewer's POV")
    strengths: list[str] = Field(default_factory=list, description="Genuine strengths, not filler praise")
    weaknesses: list[str] = Field(default_factory=list, description="Specific weaknesses with section references")
    questions_to_authors: list[str] = Field(default_factory=list, description="Questions reviewer NEEDS answered")
    limitations_to_address: list[str] = Field(default_factory=list)
    issues: list[ReviewerIssue] = Field(default_factory=list, description="Structured, anchored, actionable reviewer issues")
    rating: int = Field(ge=1, le=10, description="ICLR scale: 1-2=strong reject, 3-4=weak reject, 5=borderline, 6-7=weak accept, 8-9=strong accept, 10=award")
    confidence: int = Field(ge=1, le=5, description="1=not my area, 5=expert in this exact area")
    recommendation: Literal["accept", "minor_revision", "major_revision", "reject"] = "major_revision"


class TriggerVerdict(StrictOutputModel):
    """Present/absent verdict for one profile-derived domain audit trigger.

    Decouples trigger detection from the broad methodology reviewer (which drops
    triggers under attention load) — a narrow, single-purpose checklist call is
    far more consistent run-to-run.
    """
    trigger_label: str = Field(description="Short label identifying the trigger, e.g. 'protein-level validation'")
    verdict: Literal["present", "absent", "not_applicable"]
    evidence_quote: str = Field(default="", description="Verbatim quote from the manuscript supporting the verdict (required when present)")
    rationale: str = Field(default="", description="One sentence on why absent/applicable")


class TriggerAuditOutput(StrictOutputModel):
    verdicts: list[TriggerVerdict] = Field(default_factory=list)


class MetaReviewOutput(StrictOutputModel):
    overall_recommendation: Literal["accept", "minor_revision", "major_revision", "reject"]
    decision_rationale: str
    must_address: list[str] = Field(default_factory=list, description="Blocking items required for acceptance")
    nice_to_address: list[str] = Field(default_factory=list, description="Non-blocking suggestions")
    consensus_strengths: list[str] = Field(default_factory=list)
    consensus_weaknesses: list[str] = Field(default_factory=list)
    reviewer_agreement_level: Literal["high", "medium", "low"] = "medium"


# ---------------------------------------------------------------------------
# Phase 4 — LLM-as-a-judge
# ---------------------------------------------------------------------------

class SuggestedCitationVerdict(StrictOutputModel):
    claim_text_snippet: str = Field(description="First 80 chars of the claim text this citation was suggested for")
    citation_title: str
    relevance_score: float = Field(ge=0.0, le=1.0, description="1.0 = directly relevant to this specific claim; 0.0 = unrelated")
    keep: bool = Field(description="False = filter out before displaying to user")
    reason: str = Field(description="One sentence justifying the verdict")


class ExternalSourceVerdict(StrictOutputModel):
    source_title: str
    supports_which: str = Field(description="The gap or claim text this source addresses")
    relevance_score: float = Field(ge=0.0, le=1.0)
    keep: bool
    reason: str


class SingleCitationVerdict(StrictOutputModel):
    pair_index: int = Field(description="0-based index matching the input pair list")
    verdict: Literal["supports", "partial", "unrelated", "contradicts", "overclaim", "unverifiable"]
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence_quote: str = Field(
        default="",
        description="Verbatim quote from the SOURCE ABSTRACT proving the verdict. REQUIRED for contradicts/overclaim/unrelated. Empty only for 'supports' or 'unverifiable'.",
    )
    reasoning: str = Field(default="", description="Brief explanation of the verdict (1-2 sentences)")


class CitationVerificationBatch(StrictOutputModel):
    verdicts: list[SingleCitationVerdict] = Field(default_factory=list)


class CitationJudgeOutput(StrictOutputModel):
    citation_verdicts: list[SuggestedCitationVerdict] = Field(default_factory=list)
    external_source_verdicts: list[ExternalSourceVerdict] = Field(default_factory=list)
    overall_citation_quality: Literal["high", "medium", "low"] = "medium"


class ReviewerJudgeScore(StrictOutputModel):
    reviewer_id: str
    specificity_score: float = Field(
        ge=0.0, le=1.0,
        description="1.0 = all feedback names specific sections/figures/equations from this paper; 0.0 = pure generic boilerplate",
    )
    vague_items: list[str] = Field(
        default_factory=list,
        description="Exact text of generic/boilerplate feedback items that apply to any paper",
    )
    quality_pass: bool = Field(description="True if reviewer output meets the bar for display")


class ReviewerJudgeOutput(StrictOutputModel):
    reviewer_scores: list[ReviewerJudgeScore]
    panel_quality: Literal["high", "medium", "low"] = "medium"
    retry_reviewer_ids: list[str] = Field(
        default_factory=list,
        description="reviewer_ids whose output should be regenerated with a stricter specificity prompt",
    )


class AnalysisQualityJudgeOutput(StrictOutputModel):
    quality_pass: bool
    domain_alignment_score: float = Field(ge=0.0, le=1.0)
    manuscript_specificity_score: float = Field(ge=0.0, le=1.0)
    wrong_domain_flags: list[str] = Field(default_factory=list)
    retry_recommended: bool = False
    reroute_required: bool = False
    suggested_route: str = ""
    invalid_review_standards: list[str] = Field(default_factory=list)
    source_contamination_flags: list[str] = Field(default_factory=list)
    publish_allowed: bool = True
    failure_reason: str = ""
    judge_rationale: str = ""

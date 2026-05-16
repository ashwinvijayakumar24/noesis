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
    importance_score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    weakness_reason: str = ""


class ClaimExtractionOutput(StrictOutputModel):
    claims: list[ExtractedClaim] = Field(default_factory=list)
    total_claims: int = 0
    extraction_notes: str = ""


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

class GapItem(StrictOutputModel):
    gap_type: str
    description: str
    severity: Literal["critical", "important", "minor"] = "minor"
    affected_claims: list[str] = Field(default_factory=list)
    suggested_papers: list[str] = Field(default_factory=list)


class GapDetectionOutput(StrictOutputModel):
    gaps: list[GapItem] = Field(default_factory=list)
    summary: str = ""


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


class ReviewerFeedbackOutput(StrictOutputModel):
    feedback_items: list[FeedbackItem] = Field(default_factory=list)
    overall_assessment: str = ""
    priority_actions: list[str] = Field(default_factory=list)


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


class Reviewer1StrengthItem(StrictOutputModel):
    aspect: str
    section_reference: str = "Overall"
    detail: str
    significance: Literal["high", "medium", "low"] = "medium"


class Reviewer1StrengthsOutput(StrictOutputModel):
    strengths: list[Reviewer1StrengthItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Phase 3 — peer review panel
# ---------------------------------------------------------------------------

class EditorPassOutput(StrictOutputModel):
    proceed_to_review: bool = True
    fatal_flaws: list[str] = Field(default_factory=list)
    scope_appropriate: bool = True
    writing_quality: Literal["publishable", "needs_revision", "major_revision"] = "needs_revision"
    notes: str = ""


class ReviewerOutput(StrictOutputModel):
    reviewer_id: Literal["novelty", "methodology", "coverage", "clarity"]
    summary: str = Field(description="2-3 sentence summary from this reviewer's POV")
    strengths: list[str] = Field(default_factory=list, description="Genuine strengths, not filler praise")
    weaknesses: list[str] = Field(default_factory=list, description="Specific weaknesses with section references")
    questions_to_authors: list[str] = Field(default_factory=list, description="Questions reviewer NEEDS answered")
    limitations_to_address: list[str] = Field(default_factory=list)
    rating: int = Field(ge=1, le=10, description="ICLR scale: 1-2=strong reject, 3-4=weak reject, 5=borderline, 6-7=weak accept, 8-9=strong accept, 10=award")
    confidence: int = Field(ge=1, le=5, description="1=not my area, 5=expert in this exact area")
    recommendation: Literal["accept", "minor_revision", "major_revision", "reject"] = "major_revision"


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

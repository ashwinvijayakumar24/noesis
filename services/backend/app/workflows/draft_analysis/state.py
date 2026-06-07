"""
Draft Analysis State Schema

Defines the state structure for the draft analysis workflow.
The state is passed through all nodes and updated as the workflow progresses.
"""

from typing import TypedDict, List, Dict, Any, Optional, Annotated
from typing_extensions import NotRequired
from operator import add


class Claim(TypedDict):
    """A single claim extracted from the draft."""
    id: str
    claim_text: str
    claim_type: str  # empirical, theoretical, methodological
    section_location: str
    importance_score: float
    confidence: NotRequired[float]
    requires_citation: NotRequired[bool]  # Whether this claim needs citation support
    rhetorical_role: NotRequired[str]  # background_claim, result_finding, discussion_synthesis, etc.
    weakness_reason: NotRequired[str]
    existing_citations: NotRequired[List[str]]
    has_inline_citation: NotRequired[bool]
    page_number: NotRequired[int]
    paragraph_index: NotRequired[int]
    suggested_sources: NotRequired[List[Dict[str, Any]]]


class ClaimWithCitation(TypedDict):
    """A claim with its supporting citations."""
    claim: Claim
    citations: List[Dict[str, Any]]
    citation_quality: NotRequired[str]  # strong, moderate, weak
    gaps: NotRequired[List[str]]
    suggested_citations: NotRequired[List[Dict[str, Any]]]  # B2: discovered papers for weak/none claims
    external_sources: NotRequired[List[Dict[str, Any]]]


class Gap(TypedDict):
    """A coverage gap in the draft."""
    id: NotRequired[str]
    gap_type: str  # missing_evidence, missing_perspectives, missing_baselines
    description: str
    severity: str  # critical, important, minor
    affected_claims: List[str]
    suggested_papers: NotRequired[List[Dict[str, Any]]]
    external_sources: NotRequired[List[Dict[str, Any]]]


class Feedback(TypedDict):
    """Reviewer feedback on the draft."""
    feedback_type: str  # strength, weakness, question, suggestion
    feedback_text: str
    severity: str  # critical, important, minor
    section_reference: NotRequired[str]
    reviewer_persona: NotRequired[str]
    target_claim_id: NotRequired[str]
    target_gap_id: NotRequired[str]
    specific_issue: NotRequired[str]
    suggestions: NotRequired[List[str]]
    suggested_improvements: NotRequired[List[str]]
    cited_papers: NotRequired[List[str]]
    qa_result: NotRequired[Dict[str, Any]]
    line_number: NotRequired[int]
    char_start: NotRequired[int]
    char_end: NotRequired[int]
    text_snippet: NotRequired[str]
    section_id: NotRequired[str]
    char_offset_from_section: NotRequired[int]
    pdf_coordinates: NotRequired[Dict[str, Any]]
    match_confidence: NotRequired[float]
    suggested_fix: NotRequired[str]
    source_grounding: NotRequired[Dict[str, Any]]
    qa_status: NotRequired[str]
    qa_notes: NotRequired[List[str]]


class DraftStructure(TypedDict):
    """Document structure information."""
    sections: List[Dict[str, Any]]
    word_count: int
    page_count: int
    has_abstract: bool
    has_introduction: bool
    has_methods: bool
    has_results: bool
    has_discussion: bool
    has_conclusion: bool


class ProgressUpdate(TypedDict):
    """Progress update information."""
    current_step: str
    progress_percentage: int
    message: str
    timestamp: str


class DraftAnalysisState(TypedDict):
    """
    Complete state for draft analysis workflow.

    This state is passed through all nodes in the workflow and updated
    as each step completes.
    """
    # Input
    draft_id: str
    project_id: str
    user_id: str
    draft_content: str
    paper_type: NotRequired[str]
    citation_style: NotRequired[str]
    analysis: NotRequired[Dict[str, Any]]
    parse_artifact: NotRequired[Dict[str, Any]]
    parser_quality: NotRequired[Dict[str, Any]]
    forced_route: NotRequired[str]
    stage_only: NotRequired[bool]

    # Structure analysis
    structure: NotRequired[DraftStructure]
    manuscript_profile: NotRequired[Dict[str, Any]]

    # Claim extraction and categorization
    claims: NotRequired[List[Claim]]
    claims_by_type: NotRequired[Dict[str, List[Claim]]]
    primary_claims: NotRequired[List[Claim]]
    supporting_claims: NotRequired[List[Claim]]

    # Literature search (intermediate results before citation mapping)
    literature_search_results: NotRequired[List[Dict[str, Any]]]

    # Citation mapping
    claims_with_citations: NotRequired[List[ClaimWithCitation]]

    # Gap detection
    coverage_gaps: NotRequired[List[Gap]]

    # Literature recommendations
    literature_recommendations: NotRequired[List[Dict[str, Any]]]
    external_sources: NotRequired[List[Dict[str, Any]]]
    feedback_qa_failures: NotRequired[List[Dict[str, Any]]]

    # Reviewer feedback
    reviewer_feedback: NotRequired[List[Feedback]]
    reviewer_feedback_retry_items: NotRequired[List[Dict[str, Any]]]

    # Structural checks feedback (merged into reviewer_feedback table with feedback_type='structural')
    structural_feedback: NotRequired[List[Dict[str, Any]]]
    diagnostic_findings: NotRequired[List[Dict[str, Any]]]
    revision_tasks: NotRequired[List[Dict[str, Any]]]

    # Final report
    synthesis_report: NotRequired[Dict[str, Any]]

    # Workflow metadata
    current_step: str
    progress_percentage: int
    progress_history: NotRequired[List[ProgressUpdate]]
    errors: NotRequired[List[str]]
    warnings: NotRequired[List[str]]

    # Conditional routing decisions
    should_validate_claims: NotRequired[bool]
    needs_human_review: NotRequired[bool]
    search_iterations: NotRequired[int]
    max_search_iterations: NotRequired[int]

    # Phase 3 — peer review panel
    # reviewer_type is injected per-node by LangGraph Send API
    reviewer_type: NotRequired[str]
    editor_decision: NotRequired[Dict[str, Any]]
    # Annotated at top level (not inside NotRequired) so LangGraph recognises the reducer.
    # Each parallel reviewer_panel_node appends its output; reducer accumulates them.
    reviewer_outputs: Annotated[List[Dict[str, Any]], add]
    meta_review: NotRequired[Dict[str, Any]]

    # Phase 4 — LLM-as-a-judge
    citation_judge_output: NotRequired[Dict[str, Any]]
    reviewer_judge_output: NotRequired[Dict[str, Any]]
    analysis_quality_judge: NotRequired[Dict[str, Any]]
    quality_retry_instruction: NotRequired[str]
    # Judged/retried reviewer outputs written by reviewer_judge_node.
    # Separate from reviewer_outputs (which uses an additive reducer) so we can
    # replace/store the final set without double-appending via the reducer.
    judged_reviewer_outputs: NotRequired[List[Dict[str, Any]]]


class ValidationState(TypedDict):
    """State for human validation steps."""
    validation_type: str  # claim_validation, gap_validation
    items_to_validate: List[Dict[str, Any]]
    validated_items: NotRequired[List[Dict[str, Any]]]
    validation_status: str  # pending, approved, rejected
    user_feedback: NotRequired[str]

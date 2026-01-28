"""
Draft Analysis State Schema

Defines the state structure for the draft analysis workflow.
The state is passed through all nodes and updated as the workflow progresses.
"""

from typing import TypedDict, List, Dict, Any, Optional
from typing_extensions import NotRequired


class Claim(TypedDict):
    """A single claim extracted from the draft."""
    id: str
    claim_text: str
    claim_type: str  # empirical, theoretical, methodological
    section_location: str
    importance_score: float
    confidence: NotRequired[float]
    requires_citation: NotRequired[bool]  # Whether this claim needs citation support


class ClaimWithCitation(TypedDict):
    """A claim with its supporting citations."""
    claim: Claim
    citations: List[Dict[str, Any]]
    citation_quality: NotRequired[str]  # strong, moderate, weak
    gaps: NotRequired[List[str]]


class Gap(TypedDict):
    """A coverage gap in the draft."""
    gap_type: str  # missing_evidence, missing_perspectives, missing_baselines
    description: str
    severity: str  # critical, important, minor
    affected_claims: List[str]
    suggested_papers: NotRequired[List[Dict[str, Any]]]


class Feedback(TypedDict):
    """Reviewer feedback on the draft."""
    feedback_type: str  # strength, weakness, question, suggestion
    feedback_text: str
    severity: str  # critical, important, minor
    section_reference: NotRequired[str]


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

    # Structure analysis
    structure: NotRequired[DraftStructure]

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

    # Reviewer feedback
    reviewer_feedback: NotRequired[List[Feedback]]

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


class ValidationState(TypedDict):
    """State for human validation steps."""
    validation_type: str  # claim_validation, gap_validation
    items_to_validate: List[Dict[str, Any]]
    validated_items: NotRequired[List[Dict[str, Any]]]
    validation_status: str  # pending, approved, rejected
    user_feedback: NotRequired[str]

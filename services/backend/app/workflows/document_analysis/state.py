"""
Document Analysis State Schema

Defines the state structure for the document analysis LangGraph workflow.
"""

from typing import TypedDict, List, Dict, Any, Optional


class Claim(TypedDict):
    """A single extracted claim from the document."""
    claim_text: str
    claim_type: str  # empirical, theoretical, methodological, comparative, causal
    section_title: Optional[str]
    section_type: Optional[str]  # intro, methods, results, discussion, conclusion
    page_number: Optional[int]
    importance_score: float  # 0.0 to 1.0
    confidence_score: float  # 0.0 to 1.0
    supports_primary_thesis: bool


class Method(TypedDict):
    """A methodology/technique used in the research."""
    method_name: str
    method_type: Optional[str]  # algorithm, experimental_design, data_collection, statistical_analysis
    description: str
    parameters: Optional[Dict[str, Any]]  # Hyperparameters, settings
    section_title: Optional[str]
    page_number: Optional[int]
    datasets_used: List[str]
    evaluation_metrics: List[str]


class Finding(TypedDict):
    """A quantitative result or key finding."""
    finding_text: str
    finding_type: Optional[str]  # performance_metric, statistical_result, qualitative_insight, limitation
    metrics: Optional[Dict[str, Any]]  # {"accuracy": 0.92, "F1": 0.89}
    comparison_baseline: Optional[str]
    improvement_over_baseline: Optional[str]
    section_title: Optional[str]
    page_number: Optional[int]
    table_or_figure_reference: Optional[str]
    statistical_significance: Optional[bool]
    confidence_score: float


class DocumentStructure(TypedDict):
    """Document structure information."""
    title: str
    authors: List[str]
    abstract: str
    sections: List[Dict[str, Any]]  # [{"title": "...", "type": "...", "content": "..."}]
    word_count: int
    page_count: int
    has_abstract: bool
    has_introduction: bool
    has_methods: bool
    has_results: bool
    has_discussion: bool
    has_conclusion: bool


class DocumentAnalysisState(TypedDict):
    """
    Complete state for the document analysis LangGraph workflow.

    This state is passed between nodes and accumulates analysis results.
    """
    # Document identification
    document_id: str
    project_id: str

    # Document content
    document_text: str
    page_count: int

    # Extracted structure
    structure: DocumentStructure

    # Extracted claims (for citation matching)
    claims: List[Claim]
    claims_by_type: Dict[str, List[Claim]]  # Grouped by claim_type
    primary_claims: List[Claim]  # Most important claims

    # Extracted methodology
    methods: List[Method]
    methods_by_type: Dict[str, List[Method]]

    # Extracted findings
    findings: List[Finding]
    findings_with_metrics: List[Finding]  # Only findings with quantitative metrics

    # Final analysis report (for legacy compatibility with frontend)
    analysis_report: Dict[str, Any]

    # Workflow metadata
    current_step: str
    progress_percentage: int
    errors: List[str]
    warnings: List[str]

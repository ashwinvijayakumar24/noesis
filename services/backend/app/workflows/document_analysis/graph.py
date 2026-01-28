"""
Document Analysis LangGraph Workflow

Orchestrates the complete document analysis pipeline:
1. Structure Extraction → Identify sections and document layout
2. Claim Extraction → Extract claims for citation matching
3. Methodology Extraction → Extract methods, datasets, metrics
4. Findings Extraction → Extract quantitative results
5. Synthesis → Combine into final analysis report

This workflow enables structured knowledge extraction from research papers,
dramatically improving citation suggestion quality compared to RAG chunks.
"""

from langgraph.graph import StateGraph, END
from app.workflows.document_analysis.state import DocumentAnalysisState
from app.workflows.document_analysis.nodes import (
    extract_structure_node,
    extract_claims_node,
    extract_methodology_node,
    extract_findings_node,
    synthesize_analysis_node
)
from app.core.logging_config import get_logger

logger = get_logger(__name__)


def create_document_analysis_workflow():
    """
    Create and compile the document analysis LangGraph workflow.

    Workflow structure:
        START
          ↓
        Structure Extraction (20%)
          ↓
        Claim Extraction (40%)
          ↓
        Methodology Extraction (60%)
          ↓
        Findings Extraction (80%)
          ↓
        Synthesis (100%)
          ↓
        END

    Returns:
        Compiled LangGraph workflow ready for invocation
    """
    logger.info("[DOC-WORKFLOW] Creating document analysis workflow")

    # Create state graph
    workflow = StateGraph(DocumentAnalysisState)

    # Add nodes
    workflow.add_node("structure_extraction", extract_structure_node)
    workflow.add_node("claim_extraction", extract_claims_node)
    workflow.add_node("methodology_extraction", extract_methodology_node)
    workflow.add_node("findings_extraction", extract_findings_node)
    workflow.add_node("synthesis", synthesize_analysis_node)

    # Define edges (linear flow for now, can add conditional routing later)
    workflow.set_entry_point("structure_extraction")
    workflow.add_edge("structure_extraction", "claim_extraction")
    workflow.add_edge("claim_extraction", "methodology_extraction")
    workflow.add_edge("methodology_extraction", "findings_extraction")
    workflow.add_edge("findings_extraction", "synthesis")
    workflow.add_edge("synthesis", END)

    # Compile workflow
    app = workflow.compile()

    logger.info("[DOC-WORKFLOW] Workflow compiled successfully")
    logger.info("[DOC-WORKFLOW] Flow: structure → claims → methods → findings → synthesis")

    return app


async def run_document_analysis_workflow(
    document_id: str,
    project_id: str,
    document_text: str,
    page_count: int
) -> dict:
    """
    Execute the complete document analysis workflow.

    Args:
        document_id: UUID of the document
        project_id: UUID of the project
        document_text: Full text content of the document
        page_count: Number of pages in the document

    Returns:
        Final state containing all extracted data and analysis report

    Raises:
        Exception: If workflow execution fails
    """
    logger.info(f"[DOC-WORKFLOW] Starting workflow for document_id={document_id}")

    try:
        # Create workflow
        app = create_document_analysis_workflow()

        # Initialize state
        initial_state: DocumentAnalysisState = {
            "document_id": document_id,
            "project_id": project_id,
            "document_text": document_text,
            "page_count": page_count,
            "structure": {},  # type: ignore
            "claims": [],
            "claims_by_type": {},
            "primary_claims": [],
            "methods": [],
            "methods_by_type": {},
            "findings": [],
            "findings_with_metrics": [],
            "analysis_report": {},
            "current_step": "Starting",
            "progress_percentage": 0,
            "errors": [],
            "warnings": []
        }

        # Run workflow
        logger.info("[DOC-WORKFLOW] Invoking workflow...")
        final_state = await app.ainvoke(initial_state)

        # Check for errors
        if final_state.get("errors"):
            logger.warning(f"[DOC-WORKFLOW] Workflow completed with errors: {final_state['errors']}")
        else:
            logger.info("[DOC-WORKFLOW] ✓ Workflow completed successfully")

        # Log final stats
        logger.info(
            f"[DOC-WORKFLOW] Final stats: "
            f"{len(final_state.get('claims', []))} claims, "
            f"{len(final_state.get('methods', []))} methods, "
            f"{len(final_state.get('findings', []))} findings"
        )

        return final_state

    except Exception as e:
        logger.error(f"[DOC-WORKFLOW] Workflow execution failed: {e}")
        raise

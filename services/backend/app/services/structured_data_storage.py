"""
Structured Data Storage Service

Stores LangGraph-extracted claims, methods, and findings in the database.
Shared by both document upload analysis (documents.py) and BibTeX/discovered
paper resolution (bibtex_resolution_service.py).
"""

import logging
from typing import Dict, Any, List

from app.core.supabase_client import supabase
from app.core.openai_client import get_openai_client

logger = logging.getLogger(__name__)


def store_structured_data(
    document_id: str,
    project_id: str,
    workflow_state: Dict[str, Any],
) -> Dict[str, int]:
    """
    Store claims, methods, and findings from a LangGraph workflow state.

    Clears existing structured data for the document first (safe for re-analysis).

    Args:
        document_id: The document UUID
        project_id: The project UUID
        workflow_state: The final LangGraph state dict with 'claims', 'methods', 'findings'

    Returns:
        Dict with counts: {'claims': N, 'methods': N, 'findings': N}
    """
    logger.info(f"[StructuredStorage] Storing structured data for doc={document_id}")

    # Clear existing structured data to avoid constraint violations on re-analysis
    supabase.table("document_claims").delete().eq("document_id", document_id).execute()
    supabase.table("document_methods").delete().eq("document_id", document_id).execute()
    supabase.table("document_findings").delete().eq("document_id", document_id).execute()

    counts = {"claims": 0, "methods": 0, "findings": 0}

    # Store claims with embeddings
    claims = workflow_state.get("claims", [])
    if claims:
        client = get_openai_client()
        claim_texts = [c["claim_text"] for c in claims]
        embeddings_response = client.embeddings.create(
            model="text-embedding-3-large",
            input=claim_texts,
            dimensions=1536
        )

        for i, claim in enumerate(claims):
            claim_row = {
                "document_id": document_id,
                "project_id": project_id,
                "claim_text": claim["claim_text"],
                "claim_type": claim["claim_type"],
                "section_title": claim.get("section_title"),
                "section_type": claim.get("section_type"),
                "page_number": claim.get("page_number"),
                "importance_score": claim["importance_score"],
                "confidence_score": claim["confidence_score"],
                "supports_primary_thesis": claim["supports_primary_thesis"],
                "embedding": embeddings_response.data[i].embedding
            }
            supabase.table("document_claims").insert(claim_row).execute()

        counts["claims"] = len(claims)
        logger.info(f"[StructuredStorage] Stored {len(claims)} claims")

    # Store methods
    methods = workflow_state.get("methods", [])
    if methods:
        for method in methods:
            method_row = {
                "document_id": document_id,
                "project_id": project_id,
                "method_name": method["method_name"],
                "method_type": method.get("method_type"),
                "description": method["description"],
                "parameters": method.get("parameters", {}),
                "section_title": method.get("section_title"),
                "page_number": method.get("page_number"),
                "datasets_used": method.get("datasets_used", []),
                "evaluation_metrics": method.get("evaluation_metrics", [])
            }
            supabase.table("document_methods").insert(method_row).execute()

        counts["methods"] = len(methods)
        logger.info(f"[StructuredStorage] Stored {len(methods)} methods")

    # Store findings
    findings = workflow_state.get("findings", [])
    if findings:
        for finding in findings:
            finding_row = {
                "document_id": document_id,
                "project_id": project_id,
                "finding_text": finding["finding_text"],
                "finding_type": finding.get("finding_type"),
                "metrics": finding.get("metrics", {}),
                "comparison_baseline": finding.get("comparison_baseline"),
                "improvement_over_baseline": finding.get("improvement_over_baseline"),
                "section_title": finding.get("section_title"),
                "page_number": finding.get("page_number"),
                "table_or_figure_reference": finding.get("table_or_figure_reference"),
                "statistical_significance": finding.get("statistical_significance"),
                "confidence_score": finding["confidence_score"]
            }
            supabase.table("document_findings").insert(finding_row).execute()

        counts["findings"] = len(findings)
        logger.info(f"[StructuredStorage] Stored {len(findings)} findings")

    logger.info(
        f"[StructuredStorage] Done: {counts['claims']} claims, "
        f"{counts['methods']} methods, {counts['findings']} findings"
    )
    return counts

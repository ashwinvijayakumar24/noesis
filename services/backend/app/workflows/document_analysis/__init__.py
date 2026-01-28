"""
Document Analysis LangGraph Workflow

Structured analysis of research papers using LangGraph for:
- Claim extraction
- Methodology extraction
- Findings extraction
- Citation-based suggestions

This workflow enables precise citation matching by extracting structured
claims from documents, rather than relying on text chunk similarity.
"""

from .graph import create_document_analysis_workflow
from .state import DocumentAnalysisState

__all__ = ["create_document_analysis_workflow", "DocumentAnalysisState"]

"""
Structure Extraction Node

Analyzes document text to extract structural information:
- Title, authors, abstract
- Section identification and classification
- Overall document characteristics
"""

from typing import Dict, Any
from app.workflows.document_analysis.state import DocumentAnalysisState, DocumentStructure
from app.core.logging_config import get_logger
from openai import OpenAI
import os
import json

logger = get_logger(__name__)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


STRUCTURE_EXTRACTION_PROMPT = """You are an expert at analyzing research paper structure.

Analyze the provided document text and extract:
1. Title (if present)
2. Authors (if present)
3. Abstract (if present)
4. Section structure (identify major sections and classify them)
5. Key structural characteristics

Return ONLY a valid JSON object:
{
  "title": "Extracted title or empty string",
  "authors": ["Author 1", "Author 2"],
  "abstract": "Extracted abstract or empty string",
  "sections": [
    {
      "title": "Introduction",
      "type": "introduction",
      "estimated_word_count": 500
    },
    {
      "title": "Methodology",
      "type": "methods",
      "estimated_word_count": 800
    }
  ],
  "has_abstract": true,
  "has_introduction": true,
  "has_methods": true,
  "has_results": true,
  "has_discussion": true,
  "has_conclusion": true
}

Section types should be one of: introduction, background, related_work, methods,
results, discussion, conclusion, references, appendix, other

Be thorough in identifying sections even if they use non-standard names.
For example, "Experimental Setup" is "methods", "Findings" is "results", etc.
"""


def extract_structure_node(state: DocumentAnalysisState) -> DocumentAnalysisState:
    """
    Extract document structure including sections, title, abstract.

    This node analyzes the full document text to identify its structural
    components, which helps later nodes focus on the right sections.

    Args:
        state: Current workflow state

    Returns:
        Updated state with structure information
    """
    logger.info(f"[DOC-STRUCTURE] Starting structure extraction for document_id={state['document_id']}")

    try:
        document_text = state["document_text"]
        page_count = state["page_count"]

        # Calculate word count
        word_count = len(document_text.split())
        logger.info(f"[DOC-STRUCTURE] Document has {word_count} words across {page_count} pages")

        # Use first 8000 characters for structure analysis (to stay within token limits)
        analysis_text = document_text[:8000]

        # Call GPT-4o to extract structure
        logger.info(f"[DOC-STRUCTURE] Calling GPT-4o for structure extraction...")
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": STRUCTURE_EXTRACTION_PROMPT},
                {"role": "user", "content": f"Analyze this document:\n\n{analysis_text}"}
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
            max_tokens=2000
        )

        result = json.loads(response.choices[0].message.content)
        logger.info(f"[DOC-STRUCTURE] ✓ Structure extracted: {len(result.get('sections', []))} sections found")

        # Build structure object
        structure: DocumentStructure = {
            "title": result.get("title", ""),
            "authors": result.get("authors", []),
            "abstract": result.get("abstract", ""),
            "sections": result.get("sections", []),
            "word_count": word_count,
            "page_count": page_count,
            "has_abstract": result.get("has_abstract", False),
            "has_introduction": result.get("has_introduction", False),
            "has_methods": result.get("has_methods", False),
            "has_results": result.get("has_results", False),
            "has_discussion": result.get("has_discussion", False),
            "has_conclusion": result.get("has_conclusion", False),
        }

        # Log structure summary
        section_types = [s["type"] for s in structure["sections"]]
        logger.info(f"[DOC-STRUCTURE] Section types found: {section_types}")
        logger.info(f"[DOC-STRUCTURE] Has abstract: {structure['has_abstract']}, Has methods: {structure['has_methods']}")

        return {
            **state,
            "structure": structure,
            "current_step": "Structure Extraction",
            "progress_percentage": 20
        }

    except Exception as e:
        logger.error(f"[DOC-STRUCTURE] Error extracting structure: {e}")
        errors = state.get("errors", [])
        errors.append(f"Structure extraction failed: {str(e)}")

        return {
            **state,
            "errors": errors,
            "current_step": "Structure Extraction (Failed)",
            "progress_percentage": 20
        }

"""
Structure Extraction Node

Analyzes the draft's document structure including sections, word count, and organization.
"""

from app.workflows.draft_analysis.state import DraftAnalysisState, DraftStructure
from app.core.logging_config import get_logger
import re

logger = get_logger(__name__)


def extract_structure_node(state: DraftAnalysisState) -> DraftAnalysisState:
    """
    Extract document structure from the draft.

    This node analyzes the draft to identify:
    - Sections (Introduction, Methods, Results, Discussion, etc.)
    - Word count and page count
    - Presence of key sections

    Args:
        state: Current workflow state

    Returns:
        Updated state with structure information
    """
    logger.info(f"[Structure Extraction] ========== NODE START ==========")
    logger.info(f"[Structure Extraction] draft_id={state['draft_id']}")

    draft_content = state.get("draft_content", "")
    logger.info(f"[Structure Extraction] draft_content length={len(draft_content)} chars")

    try:
        # Basic structure analysis
        word_count = len(draft_content.split())
        # Estimate page count (assuming ~250 words per page)
        page_count = max(1, word_count // 250)

        # Detect sections by looking for common section headers
        sections = []
        section_patterns = [
            (r'\b(abstract|summary)\b', 'abstract'),
            (r'\b(introduction|background)\b', 'introduction'),
            (r'\b(methods?|methodology|materials? and methods?|experimental)\b', 'methods'),
            (r'\b(results?|findings?)\b', 'results'),
            (r'\b(discussion|analysis)\b', 'discussion'),
            (r'\b(conclusion|conclusions?|concluding remarks?)\b', 'conclusion'),
            (r'\b(related work|literature review|prior work)\b', 'related_work'),
            (r'\b(references?|bibliography)\b', 'references')
        ]

        # Find all section headers
        for pattern, section_type in section_patterns:
            matches = re.finditer(pattern, draft_content, re.IGNORECASE)
            for match in matches:
                sections.append({
                    'type': section_type,
                    'position': match.start(),
                    'text': match.group()
                })

        # Sort sections by position
        sections.sort(key=lambda x: x['position'])

        # Check for key sections
        section_types = {s['type'] for s in sections}

        structure: DraftStructure = {
            'sections': sections,
            'word_count': word_count,
            'page_count': page_count,
            'has_abstract': 'abstract' in section_types,
            'has_introduction': 'introduction' in section_types,
            'has_methods': 'methods' in section_types,
            'has_results': 'results' in section_types,
            'has_discussion': 'discussion' in section_types,
            'has_conclusion': 'conclusion' in section_types
        }

        logger.info(
            f"[Structure Extraction] Extracted structure: "
            f"{word_count} words, {page_count} pages, {len(sections)} sections"
        )

        # Update state
        return {
            'structure': structure,
            'current_step': 'Structure Extraction',
            'progress_percentage': 10
        }

    except Exception as e:
        logger.error(f"[Structure Extraction] Error: {e}")
        errors = state.get('errors', [])
        errors.append(f"Structure extraction failed: {str(e)}")

        return {
            'errors': errors,
            'current_step': 'Structure Extraction (Failed)',
            'progress_percentage': 10
        }

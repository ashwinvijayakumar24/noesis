"""
Coverage Gap Detection Node

Analyzes citation mappings to identify coverage gaps in the draft.
"""

from app.workflows.draft_analysis.state import DraftAnalysisState, Gap
from app.core.logging_config import get_logger
from app.core.supabase_client import supabase
from typing import List

logger = get_logger(__name__)


def detect_gaps_node(state: DraftAnalysisState) -> DraftAnalysisState:
    """
    Detect coverage gaps in the draft based on citation analysis.

    Gap types:
    - missing_evidence: Claims without supporting citations
    - weak_support: Claims with only weak citations
    - contradicting_evidence: Claims with contradicting citations
    - methodological_gaps: Missing baseline comparisons, ablation studies
    - perspective_gaps: Missing viewpoints or alternative approaches

    Args:
        state: Current workflow state

    Returns:
        Updated state with detected gaps
    """
    logger.info(f"[Gap Detection] Starting for draft_id={state['draft_id']}")

    draft_id = state["draft_id"]

    # OPTIMIZATION: Check if gaps already exist in database (from Phase 1)
    try:
        existing_gaps_res = supabase.table("coverage_gaps")\
            .select("id, gap_type, description, priority, suggested_papers, reasoning")\
            .eq("draft_id", draft_id)\
            .execute()

        if existing_gaps_res.data and len(existing_gaps_res.data) > 0:
            logger.info(f"[Gap Detection] Found {len(existing_gaps_res.data)} existing gaps in database - SKIPPING re-detection")

            # Convert database records to Gap objects
            gaps: List[Gap] = []
            for db_gap in existing_gaps_res.data:
                gap: Gap = {
                    "id": db_gap["id"],
                    "gap_type": db_gap["gap_type"],
                    "description": db_gap["description"],
                    "severity": db_gap.get("priority", "major"),  # Map priority -> severity
                    "affected_claims": [],
                    "suggested_papers": db_gap.get("suggested_papers", []),
                    "reasoning": db_gap.get("reasoning", "")
                }
                gaps.append(gap)

            return {
                'coverage_gaps': gaps,
                'current_step': 'Gap Detection (Cached)',
                'progress_percentage': 70
            }

    except Exception as db_error:
        logger.warning(f"[Gap Detection] Could not check for existing gaps: {db_error}")
        # Continue with detection if database check fails

    claims_with_citations = state.get("claims_with_citations", [])

    if not claims_with_citations:
        logger.warning("[Gap Detection] No citation mappings to analyze")
        return {
            'current_step': 'Gap Detection (No Data)',
            'progress_percentage': 70
        }

    try:
        gaps: List[Gap] = []

        # 1. Detect missing evidence gaps
        for claim_citation in claims_with_citations:
            claim = claim_citation['claim']
            quality = claim_citation.get('citation_quality', 'unknown')
            claim_gaps = claim_citation.get('gaps', [])
            claim_gaps = [
                gap_desc for gap_desc in claim_gaps
                if isinstance(gap_desc, str) and not gap_desc.lower().startswith('assessment failed:')
            ]

            if quality == 'none':
                # B3: Specific description with section, claim fragment, and gap detail
                claim_text_short = claim['claim_text'][:80]
                section = claim.get('section_location', 'Unknown section')
                gap_detail = claim_gaps[0] if claim_gaps else 'no matching evidence in library or online'
                gap: Gap = {
                    'gap_type': 'missing_evidence',
                    'description': (
                        f"Claim in {section}: '{claim_text_short}...' — "
                        f"no supporting citations found. {gap_detail}."
                    ),
                    'severity': 'critical' if claim['importance_score'] >= 0.7 else 'major',
                    'affected_claims': [claim['id']]
                }
                gaps.append(gap)

            # 2. Detect weak support gaps
            elif quality == 'weak':
                claim_text_short = claim['claim_text'][:80]
                section = claim.get('section_location', 'Unknown section')
                gap_detail = claim_gaps[0] if claim_gaps else 'current support is insufficient'
                gap: Gap = {
                    'gap_type': 'weak_support',
                    'description': (
                        f"Claim in {section}: '{claim_text_short}...' — "
                        f"only weak citation support found. {gap_detail}."
                    ),
                    'severity': 'major' if claim['importance_score'] >= 0.7 else 'minor',
                    'affected_claims': [claim['id']]
                }
                gaps.append(gap)

            # 3. Add specific gaps identified during citation quality assessment
            for gap_desc in claim_gaps:
                gap: Gap = {
                    'gap_type': 'missing_perspectives',
                    'description': gap_desc,
                    'severity': 'major',
                    'affected_claims': [claim['id']]
                }
                gaps.append(gap)

        # 4. Detect methodological gaps by analyzing claim types
        claims_by_type = state.get("claims_by_type", {})
        methodological_claims = claims_by_type.get('methodological', [])

        # Check for missing baseline comparisons
        has_baseline_comparison = any(
            'baseline' in claim['claim_text'].lower() or
            'compared' in claim['claim_text'].lower()
            for claim in methodological_claims
        )

        if not has_baseline_comparison and methodological_claims:
            gap: Gap = {
                'gap_type': 'methodological_gaps',
                'description': "No baseline comparisons mentioned for methodology",
                'severity': 'major',
                'affected_claims': [c['id'] for c in methodological_claims]
            }
            gaps.append(gap)

        # Categorize gaps by severity
        critical_gaps = [g for g in gaps if g['severity'] == 'critical']
        major_gaps = [g for g in gaps if g['severity'] == 'major']
        minor_gaps = [g for g in gaps if g['severity'] == 'minor']

        logger.info(
            f"[Gap Detection] Detected {len(gaps)} gaps: "
            f"critical={len(critical_gaps)}, "
            f"major={len(major_gaps)}, "
            f"minor={len(minor_gaps)}"
        )

        return {
            'coverage_gaps': gaps,
            'current_step': 'Gap Detection',
            'progress_percentage': 70
        }

    except Exception as e:
        logger.error(f"[Gap Detection] Error: {e}")
        errors = state.get('errors', [])
        errors.append(f"Gap detection failed: {str(e)}")

        return {
            'errors': errors,
            'current_step': 'Gap Detection (Failed)',
            'progress_percentage': 70
        }

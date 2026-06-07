"""
Coverage Gap Detection Node

Analyzes citation mappings to identify coverage gaps in the draft.
"""

from app.workflows.draft_analysis.state import DraftAnalysisState, Gap
from app.core.logging_config import get_logger
from typing import List
import re

logger = get_logger(__name__)


GENERIC_GAP_PATTERNS = (
    "no supporting literature found in your library",
    "no supporting citations found",
    "no matching evidence in library or online",
    "no matching evidence",
    "assessment failed:",
)


def _is_generic_gap_text(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", (text or "").strip().lower())
    if not normalized:
        return True
    return any(normalized == pattern or normalized.startswith(pattern) for pattern in GENERIC_GAP_PATTERNS)


def _is_systematic_review(state: DraftAnalysisState) -> bool:
    profile = state.get("manuscript_profile") or {}
    lenses = set(profile.get("review_lenses") or [])
    if profile:
        return profile.get("genre") == "systematic_review" or "systematic_review_methods" in lenses
    paper_type = (state.get("paper_type") or "").lower()
    draft_content = (state.get("draft_content") or "")[:6000]
    return (
        "systematic" in paper_type
        or bool(re.search(r"\bsystematic review\b|\bPRISMA\b|\bmeta[- ]analysis\b", draft_content, flags=re.IGNORECASE))
    )


def _expects_baseline_comparisons(state: DraftAnalysisState) -> bool:
    profile = state.get("manuscript_profile") or {}
    evidence_mode = str(profile.get("evidence_mode") or "").lower()
    routing_domain = str(profile.get("routing_domain") or "").lower()
    if evidence_mode in {"conceptual", "pedagogical", "theoretical"}:
        return False
    if routing_domain in {
        "humanities_education",
        "humanities_theory",
        "social_science_qualitative",
        "computer_science_conceptual",
        "law_policy",
        "business_management",
        "environmental_ecology",
        "math_statistics",
        "neuroscience_cognitive_science",
    }:
        return False
    if evidence_mode in {"empirical_ml", "empirical"}:
        return True
    return routing_domain in {"computer_science_ml", "electrical_engineering"}


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

    # Always recompute gaps for the current run. Reusing rows here can carry stale
    # issues from a previous analysis before the final persistence layer replaces
    # draft-scoped rows.

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
            if claim.get("requires_citation") is False:
                continue

            quality = claim_citation.get('citation_quality', 'unknown')
            claim_gaps = claim_citation.get('gaps', [])
            claim_gaps = [
                gap_desc for gap_desc in claim_gaps
                if isinstance(gap_desc, str) and not _is_generic_gap_text(gap_desc)
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
                if _is_generic_gap_text(gap_desc):
                    continue
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

        if (
            _expects_baseline_comparisons(state)
            and not _is_systematic_review(state)
            and not has_baseline_comparison
            and methodological_claims
        ):
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

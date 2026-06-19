"""
Claim Categorization Node

Categorizes and groups claims by type, importance, and relationships.
Identifies primary vs supporting claims.
"""

from app.workflows.draft_analysis.state import DraftAnalysisState, Claim
from app.core.logging_config import get_logger
from typing import Dict, List

logger = get_logger(__name__)


def categorize_claims_node(state: DraftAnalysisState) -> DraftAnalysisState:
    """
    Categorize and group extracted claims.

    This node:
    1. Groups claims by type (empirical, theoretical, methodological)
    2. Identifies primary claims (high importance) vs supporting claims
    3. Prepares claims for parallel literature search

    Args:
        state: Current workflow state

    Returns:
        Updated state with categorized claims
    """
    logger.info(f"[Claim Categorization] Starting for draft_id={state['draft_id']}")

    claims = state.get("claims", [])

    if not claims:
        logger.warning("[Claim Categorization] No claims to categorize")
        return {
            'current_step': 'Claim Categorization (No Claims)',
            'progress_percentage': 35
        }

    try:
        # Group claims by type
        claims_by_type: Dict[str, List[Claim]] = {
            'empirical': [],
            'theoretical': [],
            'methodological': []
        }

        for claim in claims:
            claim_type = claim['claim_type']
            if claim_type in claims_by_type:
                claims_by_type[claim_type].append(claim)

        # Identify primary vs supporting claims
        # Primary claims: importance_score >= 0.7
        # Supporting claims: importance_score < 0.7
        primary_claims = [c for c in claims if c['importance_score'] >= 0.7]
        supporting_claims = [c for c in claims if c['importance_score'] < 0.7]

        logger.info(
            f"[Claim Categorization] Categorized {len(claims)} claims: "
            f"empirical={len(claims_by_type['empirical'])}, "
            f"theoretical={len(claims_by_type['theoretical'])}, "
            f"methodological={len(claims_by_type['methodological'])}, "
            f"primary={len(primary_claims)}, supporting={len(supporting_claims)}"
        )

        # Schema gate: ensure all output fields are the expected types
        if not isinstance(claims_by_type, dict):
            raise ValueError(f"claims_by_type is {type(claims_by_type)}, expected dict")
        if not isinstance(primary_claims, list):
            raise ValueError(f"primary_claims is {type(primary_claims)}, expected list")
        if not isinstance(supporting_claims, list):
            raise ValueError(f"supporting_claims is {type(supporting_claims)}, expected list")

        return {
            'claims_by_type': claims_by_type,
            'primary_claims': primary_claims,
            'supporting_claims': supporting_claims,
            'current_step': 'Claim Categorization',
            'progress_percentage': 35
        }

    except Exception as e:
        logger.error(f"[Claim Categorization] Error: {e}")
        warnings = list(state.get('warnings') or [])
        warnings.append(f"Claim categorization failed: {str(e)}")
        return {
            'claims_by_type': {'empirical': [], 'theoretical': [], 'methodological': []},
            'primary_claims': [],
            'supporting_claims': list(state.get('claims') or []),
            'warnings': warnings,
            'current_step': 'Claim Categorization (Failed)',
            'progress_percentage': 35
        }

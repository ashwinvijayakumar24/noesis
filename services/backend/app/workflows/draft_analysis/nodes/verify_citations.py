"""
Citation Misrepresentation Verification Node (Plan 04).

Runs after categorize_claims, before search_literature.
Takes claims that have inline citation markers, resolves which paper each
marker refers to via the resolved_references list, then asks GPT-5.2 whether
the cited paper's abstract actually supports the claim.

Adverse verdicts (contradicts / overclaim / unrelated) become revision tasks.
Node is non-fatal — any exception returns empty results and a warning.
"""

from __future__ import annotations

from app.workflows.draft_analysis.state import DraftAnalysisState
from app.core.logging_config import get_logger

logger = get_logger(__name__)


async def verify_citations_node(state: DraftAnalysisState) -> dict:
    """Non-fatal citation verification node."""
    draft_id = state.get("draft_id", "")
    logger.info("[VerifyCitations] Starting for draft_id=%s", draft_id)

    try:
        from app.services.draft_citation_verification import (
            build_claim_ref_pairs,
            verify_citation_pairs,
            verdicts_to_revision_tasks,
        )

        claims = state.get("claims") or []
        resolved_refs = state.get("resolved_references") or []

        if not claims or not resolved_refs:
            logger.info(
                "[VerifyCitations] Nothing to verify (claims=%d, resolved_refs=%d)",
                len(claims), len(resolved_refs),
            )
            return {
                "citation_verdicts": [],
                "current_step": "Citation Verification (Skipped — no data)",
                "progress_percentage": 36,
            }

        pairs = build_claim_ref_pairs(claims, resolved_refs)
        logger.info("[VerifyCitations] Built %d (claim, ref) pairs to verify", len(pairs))

        if not pairs:
            return {
                "citation_verdicts": [],
                "current_step": "Citation Verification (Skipped — no resolvable pairs)",
                "progress_percentage": 36,
            }

        verdicts = await verify_citation_pairs(pairs)

        # Evidence gate: defence-in-depth drop of adverse verdicts with no quote
        try:
            from app.services.draft_evidence_gate import strip_unsourced_citation_verdicts
            verdicts = strip_unsourced_citation_verdicts(verdicts)
        except Exception as _gate_exc:
            logger.warning("[VerifyCitations] Evidence gate skipped: %s", _gate_exc)

        revision_tasks = verdicts_to_revision_tasks(verdicts)

        n_adverse = sum(
            1 for v in verdicts
            if v["verdict"] in {"contradicts", "overclaim", "unrelated"}
        )
        logger.info(
            "[VerifyCitations] Done: %d verdicts, %d adverse, %d revision tasks",
            len(verdicts), n_adverse, len(revision_tasks),
        )

        # Merge citation misrepresentation revision tasks into existing revision_tasks list
        existing_tasks = list(state.get("revision_tasks") or [])
        existing_tasks.extend(revision_tasks)

        return {
            "citation_verdicts": verdicts,
            "revision_tasks": existing_tasks,
            "current_step": "Citation Verification",
            "progress_percentage": 36,
        }

    except Exception as exc:
        logger.warning("[VerifyCitations] Failed (non-fatal): %s", exc)
        warnings = list(state.get("warnings") or [])
        warnings.append(f"Citation verification skipped: {exc}")
        return {
            "citation_verdicts": [],
            "warnings": warnings,
            "current_step": "Citation Verification (Failed)",
            "progress_percentage": 36,
        }

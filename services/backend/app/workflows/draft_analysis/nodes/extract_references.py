"""Graph node: extract and resolve the draft's own reference list."""

import time

from app.core.logging_config import get_logger
from app.core.privacy import safe_exception
from app.workflows.draft_analysis.state import DraftAnalysisState

logger = get_logger(__name__)


async def extract_references_node(state: DraftAnalysisState) -> DraftAnalysisState:
    """
    Pull references from parse_artifact (GROBID structured refs),
    resolve metadata + abstracts from OpenAlex (no PDF downloads),
    and detect unused references.
    Non-fatal: failures return empty lists + a warning.
    """
    parse_artifact = state.get("parse_artifact") or {}
    draft_content = state.get("draft_content") or ""

    try:
        from app.services.draft_reference_extraction import (
            detect_unused_refs,
            extract_refs_from_parse_artifact,
            resolve_all_refs,
        )

        t0 = time.monotonic()
        raw_refs = extract_refs_from_parse_artifact(parse_artifact)
        logger.info("[ExtractRefs] %d raw refs found in parse_artifact", len(raw_refs))

        resolved = await resolve_all_refs(raw_refs)
        unused = detect_unused_refs(resolved, draft_content)

        logger.info(
            "[ExtractRefs] Done in %.1fs — %d resolved, %d unused",
            time.monotonic() - t0,
            sum(1 for r in resolved if r["resolved"]),
            len(unused),
        )

        return {
            "resolved_references": resolved,
            "unused_references": unused,
            "current_step": "References extracted",
            "progress_percentage": 13,
        }

    except Exception as exc:
        logger.warning("[ExtractRefs] Failed (non-fatal): %s", safe_exception(exc))
        warnings = list(state.get("warnings") or [])
        warnings.append(f"Reference extraction failed: {safe_exception(exc)}")
        return {
            "resolved_references": [],
            "unused_references": [],
            "warnings": warnings,
            "current_step": "References extracted (skipped)",
            "progress_percentage": 13,
        }

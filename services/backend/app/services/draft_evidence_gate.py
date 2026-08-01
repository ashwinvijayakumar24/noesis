"""
Evidence gate — shared validators that ensure findings and verdicts carry
verbatim draft evidence before they propagate downstream.

Rule 1: a finding with a non-empty anchor_text/text_snippet that is NOT a
verbatim substring of the draft is dropped (hallucinated or paraphrased quote).

Rule 2: an adverse citation verdict (contradicts/overclaim/unrelated) with an
empty evidence_quote is dropped. The service layer already applies
_anti_hallucination_guard; this is defence-in-depth at the node boundary.
"""
from __future__ import annotations

import re
from typing import Any

ADVERSE_VERDICTS = {"contradicts", "overclaim", "unrelated"}


def _is_verbatim(anchor: str, draft_content: str) -> bool:
    """True iff anchor is a substantial (≥3 words or ≥24 chars) verbatim substring of draft."""
    anchor = (anchor or "").strip()
    if not draft_content or not anchor:
        return False
    # Short fragments are unverifiable — keep them (don't false-drop)
    if len(anchor.split()) < 3 and len(anchor) < 24:
        return True
    if anchor in draft_content:
        return True
    norm_anchor = re.sub(r"\s+", " ", anchor)
    norm_draft = re.sub(r"\s+", " ", draft_content)
    return norm_anchor in norm_draft


def strip_unanchored_findings(
    findings: list[dict[str, Any]], draft_content: str
) -> list[dict[str, Any]]:
    """Drop findings whose anchor_text/text_snippet is non-empty but not verbatim in draft."""
    if not draft_content:
        return findings or []
    kept = []
    dropped = 0
    for f in findings or []:
        anchor = (f.get("anchor_text") or f.get("text_snippet") or "").strip()
        if anchor and not _is_verbatim(anchor, draft_content):
            dropped += 1
            continue
        kept.append(f)
    if dropped:
        import logging
        logging.getLogger(__name__).warning(
            "[EvidenceGate] Dropped %d unanchored findings", dropped
        )
    return kept


def strip_unsourced_citation_verdicts(
    verdicts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Drop adverse verdicts (contradicts/overclaim/unrelated) with empty evidence_quote."""
    kept = []
    dropped = 0
    for v in verdicts or []:
        if v.get("verdict") in ADVERSE_VERDICTS and not (v.get("evidence_quote") or "").strip():
            dropped += 1
            continue
        kept.append(v)
    if dropped:
        import logging
        logging.getLogger(__name__).warning(
            "[EvidenceGate] Dropped %d unsourced adverse verdicts", dropped
        )
    return kept

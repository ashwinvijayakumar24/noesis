"""Citation misrepresentation verification (Plan 04).

For each claim that has inline citation markers, resolve which paper is cited
and ask GPT-5.2 whether the paper's abstract actually supports the claim.

Anti-hallucination rule: adverse verdicts (contradicts / overclaim / unrelated)
MUST carry a verbatim evidence_quote from the cited source. Any adverse verdict
without a quote is downgraded to 'unverifiable'.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from app.core.logging_config import get_logger
from app.core.openai_client import get_async_openai_client, get_completion_params
from app.services.retry_utils import parse_chat_completion_with_retries
from app.workflows.draft_analysis.schemas import CitationVerificationBatch

logger = get_logger(__name__)

MAX_PAIRS = 20      # cost guardrail: max (claim, ref) pairs to verify per run
BATCH_SIZE = 5      # pairs per GPT call
MIN_IMPORTANCE = 0.5

ADVERSE_VERDICTS = {"contradicts", "overclaim", "unrelated"}

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = get_async_openai_client()
    return _client


VERIFY_SYSTEM_PROMPT = """You are an expert academic fact-checker verifying whether a cited paper actually supports the claim it is attached to.

You will receive a numbered list of (CLAIM, SOURCE ABSTRACT) pairs.
For each pair return a verdict using ONLY the abstract provided.

Verdicts:
- supports   : The abstract clearly supports the claim as stated.
- partial    : The abstract is related but only weakly or partially supports it.
- unrelated  : The abstract is about a different topic; this citation is misplaced.
- contradicts: The abstract presents evidence that contradicts the claim.
- overclaim  : The claim overstates or exaggerates what the abstract actually says.
- unverifiable: The abstract is too vague, absent, or in a language you cannot assess.

CRITICAL ANTI-HALLUCINATION RULE:
For every verdict other than "supports" or "unverifiable", you MUST provide an
evidence_quote — a short verbatim excerpt (≤60 words) copied directly from the
abstract that justifies your verdict. If you cannot find such a quote, use verdict
"unverifiable" instead. Never fabricate or paraphrase the quote.

Be precise. A paper that discusses the same broad topic but does not address the
specific claim should be "unrelated", not "partial"."""


def _build_ref_index(resolved_refs: list[dict]) -> dict[str, dict]:
    """Build lookup: numeric key ("1","2",...) and author-year keys → ref dict.

    Handles both "Smith J" (Last Initials) and "John Smith" (First Last) formats
    by indexing both first and last tokens as candidate name keys.
    """
    index: dict[str, dict] = {}
    for i, ref in enumerate(resolved_refs, start=1):
        index[str(i)] = ref
        authors = ref.get("authors") or []
        year = str(ref.get("year") or "")
        if authors:
            tokens = authors[0].split()
            if not tokens:
                continue
            # Index both first and last token — covers "Smith J" and "John Smith" formats
            candidates = {tokens[0].lower().strip(".,;"), tokens[-1].lower().strip(".,;")}
            for name_key in candidates:
                if not name_key:
                    continue
                if year:
                    index[f"{name_key}{year}"] = ref
                    index[f"{name_key} {year}"] = ref
                index[name_key] = ref
    return index


def _resolve_marker(marker: str, ref_index: dict[str, dict]) -> dict | None:
    """Map a single citation marker string to a resolved ref, or None if no match."""
    marker = marker.strip()

    # Numeric: "[5]" or bare "5"
    m = re.match(r"^\[?(\d{1,3})\]?$", marker)
    if m:
        return ref_index.get(m.group(1))

    # Author-year: "Smith (2020)", "(Smith, 2020)", "Smith et al. (2020)"
    m = re.match(
        r"\(?([A-Z][A-Za-z\-]+)(?:\s+et\s+al\.)?[,\s\(]+(\d{4}[a-z]?)\)?",
        marker,
    )
    if m:
        last = m.group(1).lower()
        year = m.group(2)[:4]
        return (
            ref_index.get(f"{last}{year}")
            or ref_index.get(f"{last} {year}")
            or ref_index.get(last)
        )

    return None


def build_claim_ref_pairs(
    claims: list[dict],
    resolved_refs: list[dict],
) -> list[dict]:
    """
    For each claim with inline citations, pair it with the resolved reference.
    Returns [{claim, ref, marker, pair_id}] sorted by claim importance desc.
    Capped at MAX_PAIRS.
    """
    if not claims or not resolved_refs:
        return []

    ref_index = _build_ref_index(resolved_refs)
    pairs: list[dict] = []
    seen_pairs: set[tuple[str, str]] = set()

    eligible = sorted(
        [c for c in claims if c.get("has_inline_citation") and c.get("existing_citations")],
        key=lambda c: c.get("importance_score", 0),
        reverse=True,
    )

    for claim in eligible:
        if (claim.get("importance_score") or 0) < MIN_IMPORTANCE:
            continue
        for marker in (claim.get("existing_citations") or []):
            ref = _resolve_marker(marker, ref_index)
            if not ref or not ref.get("abstract"):
                continue
            dedup_key = (claim.get("id", ""), ref.get("doi") or ref.get("title", ""))
            if dedup_key in seen_pairs:
                continue
            seen_pairs.add(dedup_key)
            pairs.append({
                "claim": claim,
                "ref": ref,
                "marker": marker,
                "pair_id": str(uuid.uuid4()),
            })
            if len(pairs) >= MAX_PAIRS:
                return pairs

    return pairs


def _build_batch_prompt(pairs: list[dict]) -> str:
    lines = []
    for i, pair in enumerate(pairs):
        claim_text = (pair["claim"].get("claim_text") or "")[:300]
        abstract = (pair["ref"].get("abstract") or "")[:600]
        ref_title = (pair["ref"].get("title") or "")[:120]
        lines.append(
            f"--- PAIR {i} ---\n"
            f"CLAIM: {claim_text}\n"
            f"CITED PAPER: {ref_title}\n"
            f"SOURCE ABSTRACT: {abstract}"
        )
    return "\n\n".join(lines)


def _anti_hallucination_guard(verdict_obj: Any, pair: dict) -> dict:
    """Downgrade adverse verdicts lacking an evidence_quote to 'unverifiable'."""
    verdict = verdict_obj.verdict
    quote = (verdict_obj.evidence_quote or "").strip()
    if verdict in ADVERSE_VERDICTS and not quote:
        logger.warning(
            "[CitVerify] Adverse verdict '%s' lacked evidence_quote → downgraded to unverifiable "
            "(claim: %.60s, ref: %.60s)",
            verdict,
            pair["claim"].get("claim_text", ""),
            pair["ref"].get("title", ""),
        )
        verdict = "unverifiable"
        quote = ""

    return {
        "pair_id": pair["pair_id"],
        "claim_id": pair["claim"].get("id"),
        "claim_text": (pair["claim"].get("claim_text") or "")[:300],
        "citation_marker": pair["marker"],
        "cited_ref_title": pair["ref"].get("title"),
        "cited_ref_doi": pair["ref"].get("doi"),
        "cited_ref_year": pair["ref"].get("year"),
        "verdict": verdict,
        "confidence": round(verdict_obj.confidence, 3),
        "evidence_quote": quote,
        "reasoning": (verdict_obj.reasoning or "")[:400],
        "severity": _verdict_severity(verdict),
        # Anchoring fields from claim
        "section_location": pair["claim"].get("section_location"),
        "char_start": pair["claim"].get("char_start"),
        "char_end": pair["claim"].get("char_end"),
        "text_snippet": pair["claim"].get("text_snippet"),
    }


def _verdict_severity(verdict: str) -> str | None:
    return {
        "contradicts": "critical",
        "overclaim": "major",
        "unrelated": "major",
        "partial": "minor",
    }.get(verdict)


async def _verify_batch(pairs: list[dict]) -> list[dict]:
    """Run one GPT call for a batch of pairs. Returns verdict dicts."""
    if not pairs:
        return []

    user_content = _build_batch_prompt(pairs)
    try:
        response = await parse_chat_completion_with_retries(
            _get_client(),
            model="gpt-5.2-chat-latest",
            messages=[
                {"role": "system", "content": VERIFY_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            max_completion_tokens=1200,
            response_format=CitationVerificationBatch,
            **get_completion_params(),
        )
        output = response.parsed
    except Exception as exc:
        logger.warning("[CitVerify] Batch GPT call failed: %s", exc)
        # Return unverifiable for all pairs in this batch (never fail the pipeline)
        return [
            {
                "pair_id": p["pair_id"],
                "claim_id": p["claim"].get("id"),
                "claim_text": (p["claim"].get("claim_text") or "")[:300],
                "citation_marker": p["marker"],
                "cited_ref_title": p["ref"].get("title"),
                "cited_ref_doi": p["ref"].get("doi"),
                "cited_ref_year": p["ref"].get("year"),
                "verdict": "unverifiable",
                "confidence": 0.0,
                "evidence_quote": "",
                "reasoning": f"Verification failed: {exc}",
                "severity": None,
                "section_location": p["claim"].get("section_location"),
                "char_start": p["claim"].get("char_start"),
                "char_end": p["claim"].get("char_end"),
                "text_snippet": p["claim"].get("text_snippet"),
            }
            for p in pairs
        ]

    # Match verdicts back to pairs by pair_index
    results: list[dict] = []
    verdict_by_index = {v.pair_index: v for v in output.verdicts}
    for i, pair in enumerate(pairs):
        v = verdict_by_index.get(i)
        if v is None:
            logger.warning("[CitVerify] No verdict for pair %d — treating as unverifiable", i)
            results.append({
                "pair_id": pair["pair_id"],
                "claim_id": pair["claim"].get("id"),
                "claim_text": (pair["claim"].get("claim_text") or "")[:300],
                "citation_marker": pair["marker"],
                "cited_ref_title": pair["ref"].get("title"),
                "cited_ref_doi": pair["ref"].get("doi"),
                "cited_ref_year": pair["ref"].get("year"),
                "verdict": "unverifiable",
                "confidence": 0.0,
                "evidence_quote": "",
                "reasoning": "No verdict returned by model",
                "severity": None,
                "section_location": pair["claim"].get("section_location"),
                "char_start": pair["claim"].get("char_start"),
                "char_end": pair["claim"].get("char_end"),
                "text_snippet": pair["claim"].get("text_snippet"),
            })
        else:
            results.append(_anti_hallucination_guard(v, pair))
    return results


async def verify_citation_pairs(pairs: list[dict]) -> list[dict]:
    """
    Verify all (claim, ref) pairs in batches of BATCH_SIZE.
    Returns list of verdict dicts.
    """
    import asyncio

    if not pairs:
        return []

    import time
    t0 = time.monotonic()
    all_verdicts: list[dict] = []

    for i in range(0, len(pairs), BATCH_SIZE):
        batch = pairs[i: i + BATCH_SIZE]
        verdicts = await _verify_batch(batch)
        all_verdicts.extend(verdicts)

    n_adverse = sum(1 for v in all_verdicts if v["verdict"] in ADVERSE_VERDICTS)
    n_unverifiable = sum(1 for v in all_verdicts if v["verdict"] == "unverifiable")
    logger.info(
        "[CitVerify] Verified %d pairs in %.1fs — %d adverse, %d unverifiable",
        len(all_verdicts), time.monotonic() - t0, n_adverse, n_unverifiable,
    )
    return all_verdicts


def verdicts_to_revision_tasks(verdicts: list[dict]) -> list[dict]:
    """
    Convert high/medium severity citation verdicts into revision tasks.
    Only for contradicts, overclaim, unrelated (not partial, supports, unverifiable).
    """
    tasks: list[dict] = []
    for v in verdicts:
        if v["verdict"] not in ADVERSE_VERDICTS:
            continue
        severity = v.get("severity") or "major"
        cited_title = v.get("cited_ref_title") or "cited paper"
        marker = v.get("citation_marker") or ""
        reasoning = v.get("reasoning") or ""
        quote = v.get("evidence_quote") or ""

        problem = (
            f"Citation misrepresentation ({v['verdict']}): "
            f"the claim cites {cited_title!r} [{marker}] but the cited source "
            f"does not support it as stated."
        )
        if quote:
            problem += f' Source says: "{quote}"'

        tasks.append({
            "id": str(uuid.uuid4()),
            "source_type": "citation_misrepresentation",
            "task_type": "citation",
            "problem": problem,
            "suggested_action": (
                "Revise the claim to match what the cited source actually states, "
                "replace the citation with a more appropriate source, or remove the citation."
            ),
            "severity": severity,
            "priority": "high" if severity == "critical" else "medium",
            "anchor_text": v.get("claim_text") or "",
            "section_location": v.get("section_location") or "",
            "char_start": v.get("char_start"),
            "char_end": v.get("char_end"),
            "text_snippet": v.get("text_snippet") or "",
            "citation_verdict": v["verdict"],
            "cited_ref_title": v.get("cited_ref_title"),
            "evidence_quote": quote,
            "dedupe_category": f"citation_misrep:{v.get('cited_ref_doi') or v.get('cited_ref_title', '')[:60]}",
        })
    return tasks

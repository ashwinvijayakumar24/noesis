"""Extract, resolve, and analyse a draft's own reference list.

No PDF downloads — metadata + abstracts only via OpenAlex.
"""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any

import aiohttp

from app.core.logging_config import get_logger

logger = get_logger(__name__)

MAX_REFS = 40
_OA_BASE = "https://api.openalex.org"
_OA_EMAIL = "contact@noesis.is"
_OA_FIELDS = (
    "id,display_name,title,authorships,publication_year,doi,"
    "abstract_inverted_index,open_access,primary_location"
)


# ─────────────────────────────────────────────────────────────────────────────
# Extraction from parse_artifact
# ─────────────────────────────────────────────────────────────────────────────

def extract_refs_from_parse_artifact(parse_artifact: dict) -> list[dict]:
    """Return raw reference list from GROBID parser_metadata (already in state)."""
    if not parse_artifact:
        return []
    pm = parse_artifact.get("parser_metadata") or {}
    refs = pm.get("references") or pm.get("reference_map") or []
    if not isinstance(refs, list):
        return []
    return [r for r in refs if r.get("title")][:MAX_REFS]


# ─────────────────────────────────────────────────────────────────────────────
# OpenAlex resolution (metadata + abstract only)
# ─────────────────────────────────────────────────────────────────────────────

def _polite(extra: dict | None = None) -> dict:
    params = {"mailto": _OA_EMAIL, "select": _OA_FIELDS}
    if extra:
        params.update(extra)
    return params


def _title_match(a: str, b: str) -> bool:
    def words(s: str) -> set[str]:
        return {w.lower() for w in re.findall(r"\w+", s) if len(w) > 3}
    wa, wb = words(a), words(b)
    if not wa or not wb:
        return False
    return len(wa & wb) / min(len(wa), len(wb)) >= 0.6


def _abstract(inverted: dict | None) -> str:
    if not inverted:
        return ""
    try:
        pos: dict[int, str] = {}
        for word, positions in inverted.items():
            for p in positions:
                pos[p] = word
        return " ".join(pos[i] for i in sorted(pos))
    except Exception:
        return ""


def _format_work(raw_ref: dict, work: dict) -> dict:
    authors = [
        a.get("author", {}).get("display_name", "")
        for a in (work.get("authorships") or [])[:5]
    ]
    doi_raw = work.get("doi") or ""
    doi = (
        doi_raw.replace("https://doi.org/", "").replace("http://doi.org/", "")
        if doi_raw else raw_ref.get("doi") or ""
    )
    abstract = _abstract(work.get("abstract_inverted_index"))
    journal = (
        ((work.get("primary_location") or {}).get("source") or {}).get("display_name")
        or raw_ref.get("venue") or ""
    )
    return {
        "title": work.get("display_name") or work.get("title") or raw_ref.get("title"),
        "authors": authors or raw_ref.get("authors") or [],
        "year": work.get("publication_year") or raw_ref.get("year"),
        "doi": doi,
        "abstract": abstract,
        "journal": journal,
        "resolved": bool(abstract),
        "raw_ref": raw_ref,
    }


async def _by_doi(session: aiohttp.ClientSession, doi: str) -> dict | None:
    doi_clean = doi.replace("https://doi.org/", "").replace("http://doi.org/", "").strip()
    try:
        async with session.get(
            f"{_OA_BASE}/works/https://doi.org/{doi_clean}",
            params=_polite(),
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status == 200:
                return await resp.json()
    except Exception as exc:
        logger.debug("[RefExtract] DOI lookup failed: %s", exc)
    return None


async def _by_title(session: aiohttp.ClientSession, title: str) -> dict | None:
    try:
        async with session.get(
            f"{_OA_BASE}/works",
            params=_polite({"search": title[:200], "per-page": 3}),
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                for work in data.get("results") or []:
                    candidate = work.get("display_name") or work.get("title") or ""
                    if _title_match(title, candidate):
                        return work
    except Exception as exc:
        logger.debug("[RefExtract] Title search failed: %s", exc)
    return None


async def resolve_all_refs(raw_refs: list[dict]) -> list[dict]:
    """Resolve up to MAX_REFS refs against OpenAlex. No PDF downloads."""
    if not raw_refs:
        return []

    resolved: list[dict] = []
    t0 = time.monotonic()

    async with aiohttp.ClientSession() as session:
        for ref in raw_refs[:MAX_REFS]:
            title = ref.get("title") or ""
            doi = ref.get("doi") or ""
            work = None

            if doi:
                work = await _by_doi(session, doi)
            if not work and title:
                work = await _by_title(session, title)

            if work:
                resolved.append(_format_work(ref, work))
            else:
                resolved.append({
                    "title": title,
                    "authors": ref.get("authors") or [],
                    "year": ref.get("year"),
                    "doi": doi,
                    "abstract": "",
                    "journal": ref.get("venue") or "",
                    "resolved": False,
                    "raw_ref": ref,
                })

            await asyncio.sleep(0.05)  # polite rate limit

    n_resolved = sum(1 for r in resolved if r["resolved"])
    logger.info(
        "[RefExtract] Resolved %d/%d refs with abstracts in %.1fs",
        n_resolved, len(resolved), time.monotonic() - t0,
    )
    return resolved


# ─────────────────────────────────────────────────────────────────────────────
# Unused reference detection
# ─────────────────────────────────────────────────────────────────────────────

def detect_unused_refs(resolved_refs: list[dict], draft_content: str) -> list[dict]:
    """
    Find refs in the bibliography with no inline citation marker in the body.
    Heuristic: first-author last name + year appearing within 40 chars of each other.
    """
    content_lower = draft_content.lower()
    unused: list[dict] = []

    for ref in resolved_refs:
        authors = ref.get("authors") or []
        year = str(ref.get("year") or "")
        title = ref.get("title") or ""
        cited = False

        if authors and year:
            last = authors[0].split()[-1].lower() if authors[0] else ""
            if len(last) > 2:
                pattern = rf"\b{re.escape(last)}\b.{{0,40}}\b{re.escape(year)}\b"
                if re.search(pattern, content_lower):
                    cited = True

        if not cited and title:
            key_words = [w for w in re.findall(r"\w+", title) if len(w) > 5][:4]
            if key_words and all(w.lower() in content_lower for w in key_words):
                cited = True

        if not cited:
            unused.append(ref)

    return unused


# ─────────────────────────────────────────────────────────────────────────────
# Own-reference suggestions for weak claims
# ─────────────────────────────────────────────────────────────────────────────

def suggest_refs_for_weak_claims(
    claims_with_citations: list[dict],
    resolved_refs: list[dict],
) -> list[dict[str, Any]]:
    """
    For claims with weak/no citation support, find refs from the draft's own
    bibliography that could support them (keyword overlap on title + abstract).
    Returns [{claim_id, claim_text, suggested_refs}].
    """
    suggestions: list[dict] = []
    refs_with_abstract = [r for r in resolved_refs if r.get("abstract")]
    if not refs_with_abstract:
        return []

    for entry in claims_with_citations:
        claim = entry.get("claim") or entry
        quality = entry.get("citation_quality") or "unknown"
        if quality not in ("weak", "none", "unknown"):
            continue

        claim_text = claim.get("claim_text") or ""
        if not claim_text:
            continue

        claim_words = {w.lower() for w in re.findall(r"\w+", claim_text) if len(w) > 4}
        if not claim_words:
            continue

        matches: list[dict] = []
        for ref in refs_with_abstract:
            ref_bag = f"{ref.get('title', '')} {ref.get('abstract', '')}"
            ref_words = {w.lower() for w in re.findall(r"\w+", ref_bag) if len(w) > 4}
            if not ref_words:
                continue
            overlap = len(claim_words & ref_words) / min(len(claim_words), len(ref_words))
            if overlap >= 0.25:
                matches.append({"ref": ref, "overlap": round(overlap, 3)})

        if matches:
            matches.sort(key=lambda x: x["overlap"], reverse=True)
            suggestions.append({
                "claim_id": claim.get("id"),
                "claim_text": claim_text[:200],
                "suggested_refs": [m["ref"] for m in matches[:3]],
            })

    return suggestions

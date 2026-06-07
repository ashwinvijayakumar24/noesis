"""Domain-agnostic evidence manifest for draft manuscripts.

Extracts general, verifiable manuscript facts (protocol IDs, search dates,
databases, eligibility criteria, risk-of-bias / quality-assessment tools,
synthesis method, study counts, funding/COI, limitations, references) directly
from the extracted manuscript text using deterministic lexical detectors.

The manifest is built once per run and consumed by:
  - the missingness verifier (``draft_task_evidence``), so a task cannot claim an
    element is missing when the manuscript plainly contains it, and
  - diagnostic/reviewer prompting, so reviewers check facts before asserting
    absence.

This is intentionally LLM-free: facts are presence/label/snippet tuples backed
by verbatim text, which keeps the manifest cheap, deterministic, and auditable.

It is deliberately discipline-neutral. Instrument and database names below are
standard methodological vocabulary (not tied to any specific test manuscript);
adding a name here generalizes detection across papers rather than overfitting
to one.
"""

from __future__ import annotations

import re
from typing import Any

# --- shared text helpers -----------------------------------------------------


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("­", "")).strip()


def _find_snippets(text: str, pattern: str, *, max_snippets: int = 2, window: int = 160) -> list[str]:
    """Return up to ``max_snippets`` short verbatim windows around matches."""
    snippets: list[str] = []
    for match in re.finditer(pattern, text, flags=re.IGNORECASE | re.DOTALL):
        start = max(0, match.start() - window // 2)
        end = min(len(text), match.end() + window // 2)
        snippet = _norm(text[start:end])
        if snippet and snippet not in snippets:
            snippets.append(snippet)
        if len(snippets) >= max_snippets:
            break
    return snippets


def _labels_found(text: str, vocab: dict[str, str]) -> list[str]:
    """Return canonical labels whose patterns appear in ``text`` (order-stable)."""
    found: list[str] = []
    for canonical, pattern in vocab.items():
        if re.search(pattern, text, flags=re.IGNORECASE):
            if canonical not in found:
                found.append(canonical)
    return found


# --- vocabularies (standard methodological terms, discipline-neutral) --------

# Risk-of-bias / quality-assessment instruments across disciplines.
QUALITY_ASSESSMENT_TOOLS: dict[str, str] = {
    "NIH Quality Assessment Tool": r"\bNIH\b.{0,40}\bquality assessment\b|\bNational Institutes of Health\b.{0,40}\bquality assessment\b",
    "Cochrane RoB 2": r"\bRoB\s*2\b|\bRoB-?2\b|cochrane risk[- ]of[- ]bias",
    "ROBINS-I": r"\bROBINS[- ]?I\b",
    "ROBINS-E": r"\bROBINS[- ]?E\b",
    "ROBIS": r"\bROBIS\b",
    "Newcastle-Ottawa Scale": r"newcastle[- ]ottawa|\bNOS\b",
    "JBI Critical Appraisal": r"\bJBI\b|joanna briggs",
    "AMSTAR": r"\bAMSTAR\s*2?\b",
    "GRADE": r"\bGRADE\b(?![- ]?\d)|grading of recommendations",
    "QUADAS": r"\bQUADAS[- ]?2?\b",
    "QUIPS": r"\bQUIPS\b",
    "PEDro scale": r"\bPEDro\b",
    "CASP checklist": r"\bCASP\b|critical appraisal skills programme",
    "Downs and Black": r"downs and black|downs & black",
    "Jadad scale": r"\bJadad\b",
    "MMAT": r"\bMMAT\b|mixed methods appraisal",
    "Cochrane Collaboration tool": r"cochrane collaboration.{0,30}tool",
    "SYRCLE": r"\bSYRCLE\b",
    "QualSyst": r"\bQualSyst\b",
}

# Bibliographic databases / search platforms.
DATABASES: dict[str, str] = {
    "PubMed": r"\bPubMed\b",
    "MEDLINE": r"\bMEDLINE\b",
    "Embase": r"\bEmbase\b",
    "Scopus": r"\bScopus\b",
    "Web of Science": r"web of science|\bWoS\b|\bSSCI\b|\bSCI-?E\b",
    "CINAHL": r"\bCINAHL\b",
    "PsycINFO": r"\bPsyc(?:INFO|ARTICLES)\b",
    "Cochrane Library": r"cochrane (?:library|central)|\bCENTRAL\b",
    "IEEE Xplore": r"IEEE\s*Xplore",
    "ACM Digital Library": r"ACM digital library",
    "Google Scholar": r"google scholar",
    "Scholar/arXiv": r"\barXiv\b|\bbioRxiv\b|\bmedRxiv\b|\bSSRN\b",
    "ERIC": r"\bERIC\b",
    "JSTOR": r"\bJSTOR\b",
    "ProQuest": r"\bProQuest\b",
    "Science Direct": r"science\s*direct",
    "Compendex": r"\bCompendex\b|\bInspec\b",
}

# Study-design vocabulary (informational; not used for suppression).
STUDY_DESIGNS: dict[str, str] = {
    "randomized controlled trial": r"randomi[sz]ed controlled trial|\bRCT\b",
    "cohort study": r"\bcohort study|cohort studies\b",
    "case-control": r"case[- ]control",
    "cross-sectional": r"cross[- ]sectional",
    "qualitative": r"\bqualitative\b",
    "case study/series": r"case (?:study|series|report)",
    "observational": r"\bobservational\b",
}


# --- individual fact detectors ----------------------------------------------


def _fact(present: bool, *, labels: list[str] | None = None, evidence: list[str] | None = None, **extra: Any) -> dict[str, Any]:
    fact: dict[str, Any] = {"present": bool(present), "evidence": evidence or []}
    if labels is not None:
        fact["labels"] = labels
    fact.update(extra)
    return fact


def _detect_protocol_registration(text: str) -> dict[str, Any]:
    pattern = (
        r"\bPROSPERO\b|\bCRD\s*\d{6,}\b|registered protocol|protocol (?:was )?registered"
        r"|registration number|\bNCT\d{6,}\b|\bISRCTN\d{6,}\b|\bDRKS\d{6,}\b"
        r"|osf\.io/[a-z0-9]+|open science framework.{0,40}regist"
    )
    snippets = _find_snippets(text, pattern)
    return _fact(bool(snippets), evidence=snippets)


def _detect_databases(text: str) -> dict[str, Any]:
    labels = _labels_found(text, DATABASES)
    return _fact(bool(labels), labels=labels, evidence=_find_snippets(text, r"search(?:ed|ing)?\b|databases?\b"))


def _detect_search_strategy(text: str) -> dict[str, Any]:
    boolean = bool(
        re.search(r"\b(AND|OR|NOT)\b.{0,160}\b(AND|OR|NOT)\b", text)
        or re.search(r'["“][^"”]{3,40}["”]\s*(AND|OR)\b', text, flags=re.IGNORECASE)
    )
    has_db = bool(_labels_found(text, DATABASES))
    mentions_strategy = bool(re.search(r"search (?:strateg|string|terms?|syntax)", text, flags=re.IGNORECASE))
    table_strategy = bool(
        re.search(r"\bTable\s+\d\b.{0,500}\b(search (?:string|terms?)|Boolean)", text, flags=re.IGNORECASE | re.DOTALL)
    )
    present = (boolean and (has_db or mentions_strategy)) or table_strategy or (mentions_strategy and has_db)
    return _fact(
        present,
        evidence=_find_snippets(text, r"search (?:strateg|string|terms?|syntax)|\b(AND|OR|NOT)\b.{0,80}\b(AND|OR|NOT)\b"),
        boolean=boolean,
    )


def _detect_search_dates(text: str) -> dict[str, Any]:
    pattern = (
        r"(?:from\s+inception|inception)\s*(?:to|until|through|up to)\s*[A-Za-z0-9 ,]{3,30}"
        r"|searched\b.{0,60}\b(?:from|between|up to|until|through)\b.{0,40}\d{4}"
        r"|(?:between|from)\s+\d{4}\s+(?:and|to|through|until)\s+\d{4}"
        r"|(?:up to|until|through)\s+[A-Za-z]+\s+\d{4}"
        r"|search(?:es)?\s+(?:were\s+)?(?:conducted|performed|run|updated)\b.{0,60}\d{4}"
    )
    snippets = _find_snippets(text, pattern, max_snippets=3)
    years = [int(y) for y in re.findall(r"\b(?:19|20)\d{2}\b", " ".join(snippets))]
    return _fact(
        bool(snippets),
        evidence=snippets,
        latest_year=max(years) if years else None,
        years=sorted(set(years)),
    )


def _detect_eligibility_criteria(text: str) -> dict[str, Any]:
    pattern = (
        r"\b(inclusion|exclusion|eligibility) criteria\b"
        r"|studies (?:were )?(?:included|excluded) if\b"
        r"|\bPICO[ST]?\b|population.{0,20}intervention.{0,20}comparison.{0,20}outcome"
        r"|eligible studies\b"
    )
    snippets = _find_snippets(text, pattern, max_snippets=3)
    return _fact(bool(snippets), evidence=snippets)


def _detect_quality_assessment(text: str) -> dict[str, Any]:
    labels = _labels_found(text, QUALITY_ASSESSMENT_TOOLS)
    # Generic mentions count as present for the gate, but labels drive rewrites.
    generic = bool(
        re.search(r"risk[- ]of[- ]bias|quality (?:assessment|appraisal)|methodological quality", text, flags=re.IGNORECASE)
    )
    present = bool(labels) or generic
    evidence = _find_snippets(text, r"risk[- ]of[- ]bias|quality (?:assessment|appraisal)") if generic else []
    if labels:
        evidence = _find_snippets(text, "|".join(QUALITY_ASSESSMENT_TOOLS[label] for label in labels)) + evidence
    return _fact(present, labels=labels, evidence=evidence[:3], named=bool(labels))


def _detect_synthesis_method(text: str) -> dict[str, Any]:
    meta = bool(re.search(r"meta[- ]analy[sz]", text, flags=re.IGNORECASE))
    narrative = bool(re.search(r"narrative (?:synthesis|review)|qualitative synthesis|thematic synthesis", text, flags=re.IGNORECASE))
    no_pool_justified = bool(
        re.search(
            r"(?:unable|not possible|could not|did not|inappropriate)\b.{0,120}(?:meta[- ]analy|pool)"
            r"|(?:heterogeneity|outcome measures|study designs?)\b.{0,160}(?:precluded|prevented|varied|too (?:great|diverse)).{0,160}(?:meta[- ]analy|pool|narrative)",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
    )
    present = meta or narrative
    return _fact(
        present,
        evidence=_find_snippets(text, r"meta[- ]analy[sz]|narrative (?:synthesis|review)"),
        meta_analysis=meta,
        narrative_synthesis=narrative,
        no_pooling_justified=no_pool_justified,
    )


def _detect_study_counts(text: str) -> dict[str, Any]:
    pattern = (
        r"\b\d{1,4}\s+(?:studies|articles|records|papers|trials|reports)\s+(?:were\s+)?(?:included|identified|screened|retrieved|eligible)"
        r"|(?:included|identified|screened)\b.{0,20}\b\d{1,4}\s+(?:studies|articles|records|papers|trials)"
        r"|\bn\s*=\s*\d{2,6}\b"
        r"|total of\s+\d{1,4}\s+(?:studies|participants|articles)"
    )
    snippets = _find_snippets(text, pattern, max_snippets=3)
    return _fact(bool(snippets), evidence=snippets)


def _detect_funding_coi(text: str) -> dict[str, Any]:
    pattern = (
        r"\bfund(?:ed|ing)\b|grant (?:number|no)|conflict[s]? of interest|competing interests?"
        r"|no (?:competing|conflict)|declaration of interest|financial disclosure"
    )
    snippets = _find_snippets(text, pattern, max_snippets=2)
    return _fact(bool(snippets), evidence=snippets)


def _detect_limitations(text: str) -> dict[str, Any]:
    pattern = r"\blimitation[s]?\b|a limitation of (?:this|our)|this (?:study|review) (?:has|is) (?:not without )?limit"
    snippets = _find_snippets(text, pattern, max_snippets=2)
    return _fact(bool(snippets), evidence=snippets)


def _detect_references(text: str) -> dict[str, Any]:
    pattern = r"\breferences\b|\bbibliography\b|\bworks cited\b"
    # Author-year or numeric citation density as a presence signal.
    citation_count = len(re.findall(r"\([A-Z][A-Za-z&.,\s-]{1,60}\d{4}[a-z]?\)|\[\d{1,3}\]", text))
    present = bool(re.search(pattern, text, flags=re.IGNORECASE)) or citation_count >= 5
    return _fact(present, evidence=[], citation_count=citation_count)


def _detect_study_designs(text: str) -> dict[str, Any]:
    labels = _labels_found(text, STUDY_DESIGNS)
    return _fact(bool(labels), labels=labels, evidence=[])


# --- public API --------------------------------------------------------------


def build_evidence_manifest(full_text: str, *, extra_text: str = "") -> dict[str, Any]:
    """Build the domain-agnostic evidence manifest from manuscript text.

    ``extra_text`` may carry supplementary table/figure-caption text that is not
    part of ``full_text`` (e.g. multimodal table evidence persisted separately).
    """
    text = _norm(full_text)
    if extra_text:
        text = f"{text}\n{_norm(extra_text)}"

    return {
        "protocol_registration": _detect_protocol_registration(text),
        "databases_searched": _detect_databases(text),
        "search_strategy": _detect_search_strategy(text),
        "search_dates": _detect_search_dates(text),
        "eligibility_criteria": _detect_eligibility_criteria(text),
        "quality_assessment_tools": _detect_quality_assessment(text),
        "synthesis_method": _detect_synthesis_method(text),
        "study_counts": _detect_study_counts(text),
        "funding_coi": _detect_funding_coi(text),
        "limitations": _detect_limitations(text),
        "references": _detect_references(text),
        "study_designs": _detect_study_designs(text),
    }


def stale_search_task(
    manifest: dict[str, Any] | None,
    reference_year: int | None,
    *,
    max_gap_years: int = 2,
) -> dict[str, Any] | None:
    """Domain-agnostic stale-search-window critique.

    If the manifest's latest detected search year is >= ``max_gap_years`` before
    ``reference_year`` (e.g. the submission/current year), return a durable-task
    dict; otherwise None. Applies to any field — the value is purely the gap
    between the last search and now.
    """
    sd = (manifest or {}).get("search_dates") or {}
    latest = sd.get("latest_year")
    if not sd.get("present") or not latest or not reference_year:
        return None
    try:
        gap = int(reference_year) - int(latest)
    except (TypeError, ValueError):
        return None
    if gap < max_gap_years:
        return None
    snippet = (sd.get("evidence") or [""])[0][:500]
    return {
        "id": f"stale_search_{latest}",
        "source_type": "evidence_manifest",
        "task_type": "methodology",
        "severity": "major",
        "priority": "high",
        "section": "Methods/Search Strategy",
        "problem": (
            f"The literature search appears current only through {latest}, a {gap}-year gap "
            f"relative to {reference_year}."
        ),
        "why_it_matters": (
            "A multi-year gap between the last search and submission can miss recent evidence and "
            "weaken the review's currency, especially in fast-moving fields."
        ),
        "suggested_action": (
            f"Update the search to capture literature published since {latest}, or add a prominent "
            f"limitation explaining how the {gap}-year gap affects the review's currency and "
            "generalizability."
        ),
        "anchor_text": snippet,
        "text_snippet": snippet,
        "status": "new",
        "issue_family": "search_currency",
        "dedupe_category": "search_currency",
        "confidence": 0.9,
        "merged_from_task_ids": [f"stale_search_{latest}"],
        "duplicate_count": 0,
    }


def manifest_summary(manifest: dict[str, Any] | None) -> dict[str, Any]:
    """Compact present/absent view for logging and prompt injection."""
    manifest = manifest or {}
    summary: dict[str, Any] = {}
    for key, fact in manifest.items():
        if not isinstance(fact, dict):
            continue
        entry: dict[str, Any] = {"present": bool(fact.get("present"))}
        if fact.get("labels"):
            entry["labels"] = fact["labels"]
        summary[key] = entry
    return summary

"""
Canonical revision task synthesis for draft analysis.

This collapses diagnostics, reviewer issues, claims, and gaps into one
deduplicated action queue so the UI does not show the same critique in three
different shapes.
"""

from __future__ import annotations

import hashlib
import re
from difflib import SequenceMatcher
from typing import Any

from app.workflows.draft_analysis.citation_rules import apply_existing_citation_gate, needs_missing_citation_task


SEVERITY_PRIORITY = {
    "critical": "high",
    "major": "medium",
    "high": "high",
    "medium": "medium",
    "minor": "low",
    "low": "low",
    "suggestion": "low",
}

ISSUE_TYPE_TO_TASK_TYPE = {
    "methodology": "methodology",
    "coverage": "literature_positioning",
    "positioning": "literature_positioning",
    "causal_claim": "causal_claim",
    "framework_validation": "framework_validation",
    "reproducibility": "reproducibility",
    "clarity": "clarity",
    "deployment": "deployment",
    "clinical_ai": "deployment",
    "systematic_review": "methodology",
    "literature_positioning": "literature_positioning",
}

CATEGORY_PATTERNS: list[tuple[str, str, str]] = [
    ("epic_sepsis_positioning", r"\b(epic sepsis|wong|external validation failure|external validation failures|deployment controvers|major controversies|deployed sepsis prediction)\b", "literature_positioning"),
    ("review_reporting_transparency", r"\b(prisma|flowchart|flow diagram|search strings?|database coverage|database names?|date ranges?|exclusion reason|excluded studies|full-text exclusion|flow accounting|replicable search)\b", "methodology"),
    ("protocol_registration", r"\b(prospero|protocol registration|registered protocol|prospectively registered|timestamped protocol)\b", "methodology"),
    ("search_scope_bias", r"\b(gray literature|grey literature|white paper|quality.improvement report|implementation report|health system report|regulatory submission|conference proceeding|vendor report|preprint|registries|english.language|published in english|titles? and abstracts?.{0,80}english|language restriction)\b", "methodology"),
    ("rob_tool_mismatch", r"\b(rob 2|robins-i|risk.of.bias tool|tool choice)\b", "methodology"),
    ("commercial_bias_conflicts", r"\b(conflict.of.interest|commercial bias|vendor|industry sponsor|funding source|developer.evaluat|commercial conflict)\b", "methodology"),
    ("qualitative_synthesis_reproducibility", r"\b(coding framework|inter-rater|interrater|kappa|qualitative analysis|thematic analysis|audit trail|barriers, enablers|barriers/enablers)\b", "methodology"),
    ("lead_time_clinical_relevance", r"\b(lead time|alert.{0,80}antibiotic|clinical significance|time.to.antibiotic|minutes earlier|hours earlier)\b", "deployment"),
    ("algorithmic_fairness_gap", r"\b(fairness|algorithmic bias|demographic|subgroup|equity|racial|calibration drift|health disparities)\b", "deployment"),
    ("sepsis_definition_heterogeneity", r"\b(sepsis definitions?|sepsis-1|sepsis-2|sepsis-3|twenty-six different definitions|26 different definitions|definition heterogeneity)\b", "methodology"),
    ("causal_mortality_overstatement", r"\b(mortality|causal|causation|confounding|before.after|observational)\b", "causal_claim"),
    ("framework_generalizability", r"\b(salient|framework validation|ai.task agnostic|generalizability|companion paper|cfir|nasss|re-aim|decide-ai|necessary and sufficient)\b", "framework_validation"),
    ("ehr_pipeline_specificity", r"\b(ehr|electronic health record|hl7|fhir|data pipeline|live data|near-live|latency|compute)\b", "deployment"),
]


def _norm(text: str) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", (text or "").lower())
    tokens = [
        token for token in text.split()
        if token not in {
            "the", "and", "or", "but", "with", "that", "this", "from",
            "into", "your", "draft", "paper", "manuscript", "study",
        }
    ]
    return " ".join(tokens)


def _fingerprint(*parts: str) -> str:
    normalized = _norm(" ".join(part for part in parts if part))[:220]
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]


def _dedupe_category(problem: str, suggested_action: str, task_type: str) -> str:
    if task_type == "citation":
        return f"citation:{_fingerprint(problem, suggested_action)}"
    text = f"{problem} {suggested_action}".lower()
    for category, pattern, _canonical_type in CATEGORY_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL):
            return category
    return f"{task_type}:{_fingerprint(problem, suggested_action)}"


def _canonical_task_type(category: str, fallback: str) -> str:
    for cat, _pattern, canonical_type in CATEGORY_PATTERNS:
        if cat == category:
            return canonical_type
    return fallback


def _score_task_text(task: dict[str, Any]) -> tuple[int, int]:
    problem = task.get("problem", "")
    action = task.get("suggested_action", "")
    return (len(problem), len(action))


def _merge_task(existing: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    severity_rank = {"critical": 3, "major": 2, "minor": 1, "suggestion": 0}
    priority_rank = {"high": 3, "medium": 2, "low": 1}
    merged = dict(existing)
    if severity_rank.get(candidate.get("severity"), 0) > severity_rank.get(existing.get("severity"), 0):
        merged["severity"] = candidate.get("severity")
    if priority_rank.get(candidate.get("priority"), 0) > priority_rank.get(existing.get("priority"), 0):
        merged["priority"] = candidate.get("priority")
    if _score_task_text(candidate) > _score_task_text(existing):
        for key in ("problem", "why_it_matters", "suggested_action", "anchor_text", "text_snippet", "section"):
            if candidate.get(key):
                merged[key] = candidate[key]
    source_ids = list(dict.fromkeys((existing.get("source_ids") or []) + (candidate.get("source_ids") or [])))
    merged["source_ids"] = source_ids
    suggested_sources = list((existing.get("suggested_sources") or []) + (candidate.get("suggested_sources") or []))
    seen_sources: set[str] = set()
    deduped_sources = []
    for source in suggested_sources:
        key = str(source.get("document_id") or source.get("doi") or source.get("url") or source.get("title") or source.get("document_title"))
        if not key or key in seen_sources:
            continue
        seen_sources.add(key)
        deduped_sources.append(source)
    if deduped_sources:
        merged["suggested_sources"] = deduped_sources[:5]
    for key in ("page_number", "paragraph_index", "line_number", "char_start", "char_end", "pdf_coordinates", "match_confidence"):
        if merged.get(key) is None and candidate.get(key) is not None:
            merged[key] = candidate[key]
    return merged


def _is_duplicate(candidate: dict[str, Any], existing: list[dict[str, Any]]) -> bool:
    cand = _norm(f"{candidate.get('problem', '')} {candidate.get('suggested_action', '')}")
    if not cand:
        return True
    for task in existing:
        current = _norm(f"{task.get('problem', '')} {task.get('suggested_action', '')}")
        if not current:
            continue
        if cand == current:
            return True
        if SequenceMatcher(None, cand, current).ratio() >= 0.82:
            return True
    return False


def _priority(severity: str) -> str:
    return SEVERITY_PRIORITY.get((severity or "").lower(), "medium")


def _task_type(value: str) -> str:
    return ISSUE_TYPE_TO_TASK_TYPE.get((value or "").lower(), "other")


def _clean_problem(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _clip_text(text: str, limit: int) -> str:
    cleaned = _clean_problem(text)
    if len(cleaned) <= limit:
        return cleaned
    clipped = cleaned[:limit].rstrip()
    boundary = max(clipped.rfind("."), clipped.rfind(";"), clipped.rfind(","), clipped.rfind(" "))
    if boundary >= max(60, limit - 120):
        clipped = clipped[:boundary].rstrip(" ,;.")
    else:
        clipped = clipped.rstrip(" ,;.")
    return f"{clipped}..."


def _is_valid_text(text: str) -> bool:
    normalized = _clean_problem(text).lower()
    if len(normalized) < 18:
        return False
    if normalized.startswith("assessment failed:"):
        return False
    return True


def _is_low_value_formatting_task(problem: str, suggested_action: str) -> bool:
    text = f"{problem} {suggested_action}".lower()
    has_formatting_only_signal = bool(re.search(r"\b(all caps|capitalization|hyphenation|typograph|heading format|section heading)\b", text))
    has_substantive_signal = bool(re.search(r"\b(figure|table|caption|legend|reference|citation|readability|methods|results|prisma)\b", text))
    return has_formatting_only_signal and not has_substantive_signal


def _base_task(
    *,
    source_type: str,
    task_type: str,
    severity: str,
    section: str,
    anchor_text: str,
    problem: str,
    why_it_matters: str,
    suggested_action: str,
    source_ids: list[str] | None = None,
    suggested_sources: list[dict[str, Any]] | None = None,
    confidence: float = 0.8,
    source: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    problem = _clean_problem(problem)
    suggested_action = _clean_problem(suggested_action)
    if not _is_valid_text(problem) or not _is_valid_text(suggested_action):
        return None
    if task_type == "clarity" and _is_low_value_formatting_task(problem, suggested_action):
        return None

    source = source or {}
    severity = (severity or "major").lower()
    dedupe_category = _dedupe_category(problem, suggested_action, task_type)
    task_type = _canonical_task_type(dedupe_category, task_type)
    task = {
        "id": f"task_{_fingerprint(dedupe_category)}",
        "dedupe_category": dedupe_category,
        "source_type": source_type,
        "task_type": task_type,
        "severity": severity if severity in {"critical", "major", "minor", "suggestion"} else "major",
        "priority": _priority(severity),
        "section": section or "",
        "anchor_text": _clip_text(anchor_text or "", 700),
        "line_number": source.get("line_number"),
        "char_start": source.get("char_start"),
        "char_end": source.get("char_end"),
        "page_number": source.get("page_number"),
        "paragraph_index": source.get("paragraph_index"),
        "text_snippet": _clip_text(source.get("text_snippet") or anchor_text, 900),
        "pdf_coordinates": source.get("pdf_coordinates"),
        "match_confidence": source.get("match_confidence"),
        "problem": problem,
        "why_it_matters": _clean_problem(why_it_matters),
        "suggested_action": suggested_action,
        "source_ids": [sid for sid in (source_ids or []) if sid],
        "suggested_sources": suggested_sources or source.get("suggested_sources") or [],
        "confidence": max(0.0, min(float(confidence or 0.8), 1.0)),
        "status": "new",
    }
    return {k: v for k, v in task.items() if v is not None}


def build_revision_tasks(
    *,
    diagnostic_findings: list[dict[str, Any]],
    reviewer_outputs: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    gaps: list[dict[str, Any]],
    structural_feedback: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    tasks_by_category: dict[str, dict[str, Any]] = {}

    def add(task: dict[str, Any] | None) -> None:
        if not task:
            return
        category = task.get("dedupe_category")
        if category in tasks_by_category:
            tasks_by_category[category] = _merge_task(tasks_by_category[category], task)
            return
        if _is_duplicate(task, tasks):
            return
        tasks_by_category[category] = task
        tasks.append(task)

    for finding in diagnostic_findings or []:
        add(_base_task(
            source_type="diagnostic",
            task_type=_task_type(finding.get("finding_type", "")),
            severity=finding.get("severity", "major"),
            section=finding.get("section_reference", ""),
            anchor_text=finding.get("anchor_text", ""),
            problem=finding.get("problem", ""),
            why_it_matters=finding.get("why_it_matters", ""),
            suggested_action=finding.get("suggested_action", ""),
            confidence=finding.get("confidence", 0.85),
            source=finding,
        ))

    for reviewer in reviewer_outputs or []:
        reviewer_id = reviewer.get("reviewer_id", "reviewer")
        for issue in reviewer.get("issues") or []:
            add(_base_task(
                source_type="reviewer_issue",
                task_type=_task_type(issue.get("issue_type", "")),
                severity="major",
                section=issue.get("section_reference", ""),
                anchor_text=issue.get("anchor_text", ""),
                problem=issue.get("problem", ""),
                why_it_matters=issue.get("why_it_matters", ""),
                suggested_action=issue.get("suggested_action", ""),
                source_ids=[reviewer_id],
                confidence=issue.get("confidence", 0.8),
                source=issue,
            ))

    for claim in claims or []:
        claim = apply_existing_citation_gate(dict(claim))
        if not needs_missing_citation_task(claim):
            continue
        suggested_sources = claim.get("suggested_sources") or []
        add(_base_task(
            source_type="claim",
            task_type="citation",
            severity="critical" if (claim.get("importance_score") or 0) >= 0.75 else "major",
            section=claim.get("section_location", ""),
            anchor_text=claim.get("text_snippet") or claim.get("claim_text", ""),
            problem=f"Claim lacks a verified supporting citation: {claim.get('claim_text', '')}",
            why_it_matters="A reviewer may treat this as an unsupported background or prior-work claim unless the cited evidence is explicit and relevant.",
            suggested_action="Add or verify a source directly supporting this statement, or revise the wording to match the evidence already cited.",
            source_ids=[claim.get("id", "")],
            suggested_sources=suggested_sources,
            confidence=claim.get("confidence", claim.get("confidence_score", 0.75)),
            source=claim,
        ))

    for gap in gaps or []:
        add(_base_task(
            source_type="gap",
            task_type=_task_type(gap.get("gap_type", "")),
            severity=gap.get("severity") or gap.get("priority") or "major",
            section=gap.get("section_reference") or gap.get("section_type") or "",
            anchor_text=gap.get("text_snippet") or gap.get("description", ""),
            problem=gap.get("description", ""),
            why_it_matters=gap.get("reasoning", ""),
            suggested_action="Address this coverage gap with a specific citation, qualification, or discussion in the relevant section.",
            source_ids=[gap.get("id", "")],
            confidence=0.75,
            source=gap,
        ))

    for fb in structural_feedback or []:
        add(_base_task(
            source_type="structural",
            task_type=_task_type(fb.get("feedback_type") or fb.get("check_type") or ""),
            severity=fb.get("severity", "major"),
            section=fb.get("section_reference", ""),
            anchor_text=fb.get("text_snippet") or fb.get("specific_issue", ""),
            problem=fb.get("specific_issue") or fb.get("feedback_text", ""),
            why_it_matters=fb.get("feedback_text", ""),
            suggested_action=" ".join(fb.get("suggestions") or fb.get("suggested_improvements") or []) or fb.get("suggested_fix", ""),
            source_ids=[fb.get("id", "")],
            confidence=fb.get("match_confidence", 0.7),
            source=fb,
        ))

    order = {"high": 0, "medium": 1, "low": 2}
    final_tasks = list(tasks_by_category.values())
    return sorted(final_tasks, key=lambda t: (order.get(t.get("priority"), 1), t.get("section", ""), t.get("problem", "")))


def calculate_revision_task_readiness_score(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    critical = sum(1 for task in tasks if task.get("severity") == "critical")
    major = sum(1 for task in tasks if task.get("severity") == "major")
    minor = sum(1 for task in tasks if task.get("severity") == "minor")
    citation_without_source = sum(
        1 for task in tasks
        if task.get("task_type") == "citation" and not task.get("suggested_sources")
    )
    deductions = critical * 8 + major * 3 + minor + citation_without_source * 4
    score = max(0, min(100, 100 - deductions))
    guardrail = None
    if critical >= 3 or major >= 8:
        score = min(score, 69)
        guardrail = "critical_or_major_volume"
    elif critical > 0:
        score = min(score, 84)
        guardrail = "critical_issue_present"

    if score >= 85:
        verdict = "Strong Submission"
    elif score >= 70:
        verdict = "Minor Revisions"
    elif score >= 50:
        verdict = "Needs Work"
    else:
        verdict = "Major Revisions"

    return {
        "readiness_score": score,
        "verdict": verdict,
        "score_breakdown": {
            "critical_tasks": critical,
            "major_tasks": major,
            "minor_tasks": minor,
            "citation_tasks_without_sources": citation_without_source,
            "total_deductions": deductions,
            "guardrail": guardrail,
        },
    }

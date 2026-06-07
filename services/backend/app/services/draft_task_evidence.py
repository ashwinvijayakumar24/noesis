"""Deterministic evidence checks for draft revision tasks.

These checks run after LLM task generation and before persistence. They do not
try to review the paper; they prevent high-trust failures where the final task
claims an element is missing even though it is plainly present in the extracted
manuscript/table evidence.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

from app.services.draft_evidence_manifest import build_evidence_manifest


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\u00ad", "")).strip()


def _lower(text: str) -> str:
    return _norm(text).lower()


def _has(text: str, pattern: str) -> bool:
    return bool(re.search(pattern, text or "", flags=re.IGNORECASE | re.DOTALL))


def _task_text(task: dict[str, Any]) -> str:
    return " ".join(
        str(task.get(key) or "")
        for key in ("problem", "why_it_matters", "suggested_action", "anchor_text", "text_snippet", "section")
    )


def _has_protocol_registration(text: str) -> bool:
    return _has(text, r"\b(PROSPERO|CRD\s*\d{6,}|registered protocol|protocol registration)\b")


def _has_boolean_search_strategy(text: str) -> bool:
    return (
        _has(text, r"\b(AND|OR|NOT)\b.{0,160}\b(AND|OR|NOT)\b")
        and _has(text, r"\b(search strateg|database|Medline|Embase|PsycINFO|CINAHL|Scopus|Web of Science|SSCI|PubMed)\b")
    ) or _has(text, r"\bTable\s+1\b.{0,500}\b(search string|search terms?|Boolean|Medline|Embase|PsycINFO)\b")


def _has_narrative_synthesis_justification(text: str) -> bool:
    return _has(
        text,
        r"(unable|not possible|could not).{0,120}(meta-analysis|meta analysis|pool|pooled)"
        r"|narrative synthesis.{0,160}(conducted|performed|undertaken|used)"
        r"|(outcome measures|heterogeneity).{0,160}(varied|different).{0,160}(narrative synthesis|meta-analysis|pool)",
    )


def _has_inline_author_year_near_anchor(task: dict[str, Any], full_text: str) -> bool:
    anchor = _norm(str(task.get("anchor_text") or task.get("text_snippet") or ""))
    if not anchor:
        return False
    citation_re = r"\([A-Z][A-Za-z&.,\s-]{1,80}\d{4}[a-z]?\)|\b[A-Z][A-Za-z-]+\s+\(\d{4}[a-z]?\)"
    if _has(anchor, citation_re):
        return True
    words = re.findall(r"[A-Za-z0-9]+", anchor)
    if len(words) < 4:
        return False
    needle = " ".join(words[:10]).lower()
    idx = _lower(full_text).find(needle)
    if idx < 0:
        return False
    window = full_text[max(0, idx - 120): idx + len(anchor) + 180]
    return _has(window, citation_re)


def _is_missing_protocol_task(task_text: str) -> bool:
    return _has(task_text, r"\b(no|not|missing|lacks?|unclear whether).{0,120}(registered|registration|PROSPERO|protocol)\b")


def _is_missing_search_task(task_text: str) -> bool:
    return _has(task_text, r"\b(no|not|missing|lacks?|does not provide).{0,140}(search string|search strateg|Boolean|database syntax|full search)\b")


def _is_missing_meta_justification_task(task_text: str) -> bool:
    return _has(task_text, r"\b(no|not|missing|lacks?|does not).{0,160}(meta-analysis|meta analysis|narrative synthesis|pooling justification|no-pooling)\b")


def _is_missing_inline_citation_task(task_text: str) -> bool:
    return _has(
        task_text,
        r"\b(missing|lacks?|unsupported|no verified|without citation|no direct citation)\b"
        r".{0,120}\b(citation|cite|source|support|reference|evidence)\b"
        r"|\b(citation|cite|source|support|reference|evidence)\b"
        r".{0,120}\b(missing|lacks?|unsupported|no verified|without citation|no direct citation)\b",
    )


def _is_missing_quality_tool_task(task_text: str) -> bool:
    return _has(
        task_text,
        r"\b(no|not|missing|lacks?|without|does not (?:report|use|apply|employ|describe)|absence of|fail(?:s|ed)? to)\b"
        r".{0,140}\b(risk[- ]of[- ]bias|quality assessment|quality appraisal|methodological quality|"
        r"critical appraisal|standardi[sz]ed (?:tool|instrument)|\bRoB\b tool|bias (?:tool|assessment))\b",
    )


def _is_missing_eligibility_task(task_text: str) -> bool:
    return _has(
        task_text,
        r"\b(no|not|missing|lacks?|unclear|does not (?:define|state|report|specify))\b"
        r".{0,140}\b(inclusion|exclusion|eligibility) criteria\b",
    )


def _is_missing_databases_task(task_text: str) -> bool:
    return _has(
        task_text,
        r"\b(no|not|missing|lacks?|does not (?:list|name|report|specify))\b"
        r".{0,140}\b(databases?|sources searched|search sources)\b",
    )


def _rewrite_task(task: dict[str, Any], *, problem: str, suggested_action: str, reason: str) -> dict[str, Any]:
    rewritten = dict(task)
    rewritten["problem"] = problem
    rewritten["suggested_action"] = suggested_action
    rewritten["evidence_rebuttal_status"] = "rewritten"
    rewritten["evidence_rebuttal_reason"] = reason
    return rewritten


def _quality_tool_label(manifest: dict[str, Any]) -> str:
    labels = ((manifest or {}).get("quality_assessment_tools") or {}).get("labels") or []
    if labels:
        return labels[0] if len(labels) == 1 else f"{', '.join(labels[:-1])} and {labels[-1]}"
    return "a risk-of-bias/quality-assessment tool"


def _maybe_rebut_missing_task(
    task: dict[str, Any],
    full_text: str,
    manifest: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    text = _task_text(task)
    lower_text = text.lower()

    if _is_missing_protocol_task(text) and _has_protocol_registration(full_text):
        return _rewrite_task(
            task,
            problem="Protocol registration is present, but protocol deviations are not clearly reported.",
            suggested_action=(
                "Keep the PROSPERO/registry identifier visible and add a sentence stating whether any "
                "deviations from the registered protocol occurred; if deviations occurred, list and justify them."
            ),
            reason="protocol_registration_found",
        ), {"reason": "protocol_registration_found", "action": "rewritten", "task_id": task.get("id")}

    if _is_missing_search_task(text) and _has_boolean_search_strategy(full_text):
        return _rewrite_task(
            task,
            problem="A search strategy is present, but reproducibility across all databases may still be incomplete.",
            suggested_action=(
                "Retain the existing Boolean search table and add exact translated strategies, platforms, "
                "date ranges, filters, and syntax for each secondary database in an appendix or supplement."
            ),
            reason="boolean_search_strategy_found",
        ), {"reason": "boolean_search_strategy_found", "action": "rewritten", "task_id": task.get("id")}

    if _is_missing_meta_justification_task(text) and _has_narrative_synthesis_justification(full_text):
        return None, {"reason": "narrative_synthesis_justification_found", "action": "dropped", "task_id": task.get("id")}

    if (
        (_is_missing_inline_citation_task(text) or "claim lacks a verified supporting citation" in lower_text)
        and _has_inline_author_year_near_anchor(task, full_text)
    ):
        return None, {"reason": "inline_citation_found", "action": "dropped", "task_id": task.get("id")}

    if _is_missing_quality_tool_task(text) and (manifest.get("quality_assessment_tools") or {}).get("present"):
        tool = _quality_tool_label(manifest)
        return _rewrite_task(
            task,
            problem=(
                f"The manuscript reports {tool}, but does not explain how the resulting ratings affected "
                "study selection, weighting, or the synthesis."
            ),
            suggested_action=(
                f"Reference the {tool} ratings explicitly and add a sentence or table describing how high/low "
                "risk-of-bias (or good/fair/poor quality) studies were handled in the synthesis and any "
                "sensitivity analyses."
            ),
            reason="quality_assessment_tool_found",
        ), {"reason": "quality_assessment_tool_found", "action": "rewritten", "task_id": task.get("id")}

    if _is_missing_eligibility_task(text) and (manifest.get("eligibility_criteria") or {}).get("present"):
        return _rewrite_task(
            task,
            problem="Eligibility criteria are stated, but their application to borderline studies is not fully transparent.",
            suggested_action=(
                "Keep the inclusion/exclusion criteria and add the number of studies excluded at each stage with "
                "primary reasons, so the screening decisions are reproducible."
            ),
            reason="eligibility_criteria_found",
        ), {"reason": "eligibility_criteria_found", "action": "rewritten", "task_id": task.get("id")}

    if _is_missing_databases_task(text) and (manifest.get("databases_searched") or {}).get("present"):
        dbs = ", ".join((manifest.get("databases_searched") or {}).get("labels") or []) or "the named databases"
        return _rewrite_task(
            task,
            problem=f"Databases searched are reported ({dbs}), but the search dates and platform per database may be incomplete.",
            suggested_action=(
                "Retain the database list and add, for each database, the platform/interface, the date the search "
                "was run, and any date-range or language filters applied."
            ),
            reason="databases_found",
        ), {"reason": "databases_found", "action": "rewritten", "task_id": task.get("id")}

    return task, None


def _same_anchor(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_anchor = _lower(str(left.get("anchor_text") or left.get("text_snippet") or ""))
    right_anchor = _lower(str(right.get("anchor_text") or right.get("text_snippet") or ""))
    if not left_anchor or not right_anchor:
        return False
    if left_anchor == right_anchor:
        return True
    shorter, longer = sorted((left_anchor, right_anchor), key=len)
    return len(shorter) >= 40 and shorter in longer


def _contradictory_citation_pair(left: dict[str, Any], right: dict[str, Any]) -> bool:
    text_left = _lower(_task_text(left))
    text_right = _lower(_task_text(right))
    missing_left = _has(text_left, r"\b(missing|lacks?|no verified|unsupported|without citation)\b")
    missing_right = _has(text_right, r"\b(missing|lacks?|no verified|unsupported|without citation)\b")
    weak_left = _has(text_left, r"\b(weak|low-quality|advocacy|gray literature|grey literature|relies on|source quality)\b")
    weak_right = _has(text_right, r"\b(weak|low-quality|advocacy|gray literature|grey literature|relies on|source quality)\b")
    return (missing_left and weak_right) or (missing_right and weak_left)


def reconcile_tasks_against_evidence(
    tasks: list[dict[str, Any]],
    *,
    full_text: str,
    manuscript_profile: dict[str, Any] | None = None,
    manifest: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if manifest is None:
        manifest = build_evidence_manifest(full_text)
    kept: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []

    for task in tasks or []:
        next_task, event = _maybe_rebut_missing_task(task, full_text, manifest)
        if event:
            events.append(event)
        if next_task:
            kept.append(next_task)

    dropped_indices: set[int] = set()
    contradiction_events: list[dict[str, Any]] = []
    for idx, task in enumerate(kept):
        if idx in dropped_indices:
            continue
        for prior_idx in range(idx):
            prior = kept[prior_idx]
            if prior_idx in dropped_indices:
                continue
            if not (_same_anchor(task, prior) or SequenceMatcher(None, _lower(_task_text(task))[:400], _lower(_task_text(prior))[:400]).ratio() >= 0.68):
                continue
            if _contradictory_citation_pair(task, prior):
                task_text = _lower(_task_text(task))
                prior_text = _lower(_task_text(prior))
                drop_idx = idx if "missing" in task_text and "weak" in prior_text else prior_idx
                dropped_indices.add(drop_idx)
                contradiction_events.append({
                    "reason": "missing_vs_weak_citation_contradiction",
                    "action": "dropped_weaker_contradictory_task",
                    "task_id": kept[drop_idx].get("id"),
                })
                break

    reconciled = [task for idx, task in enumerate(kept) if idx not in dropped_indices]
    metrics = {
        "tasks_checked": len(tasks or []),
        "tasks_kept": len(reconciled),
        "tasks_dropped": len(tasks or []) - len(reconciled),
        "tasks_rewritten": sum(1 for event in events if event.get("action") == "rewritten"),
        "contradictions_resolved": len(contradiction_events),
        "events": events + contradiction_events,
        "profile_domain": (manuscript_profile or {}).get("routing_domain"),
    }
    return reconciled, metrics

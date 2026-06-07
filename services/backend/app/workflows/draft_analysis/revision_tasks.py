"""
Canonical revision task synthesis for draft analysis.

This collapses diagnostics, reviewer issues, claims, and gaps into one
deduplicated action queue so the UI does not show the same critique in three
different shapes.
"""

from __future__ import annotations

import hashlib
import math
import os
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
    "materials_literature_positioning": "literature_positioning",
    "materials_degradation": "literature_positioning",
    "materials_evidence": "causal_claim",
}

CATEGORY_PATTERNS: list[tuple[str, str, str]] = [
    ("crispr_nature_clinical_trial_overstatement", r"\b(nature.{0,80}clinical trial|clinical trial.{0,80}nature|germline hpfh|naturally occurring.{0,80}hpfh|somatic.{0,80}(crispr|genome editing)|observational human genotypes?)\b", "causal_claim"),
    ("crispr_delivery_modality", r"\b(plasmid|rnp|ribonucleoprotein|electroporat|transfect).{0,180}\b(cd34|hspc|hematopoietic|stem and progenitor)\b|\b(cd34|hspc|hematopoietic|stem and progenitor).{0,180}\b(plasmid|rnp|ribonucleoprotein|electroporat|transfect)\b", "methodology"),
    ("crispr_off_target_assay", r"\b(t7e1|off[- ]target|guide[- ]seq|circle[- ]seq|change[- ]seq|site[- ]seq|unbiased genome[- ]wide|translocation|large deletion|genotoxicity)\b", "methodology"),
    ("crispr_translational_positioning", r"\b(bcl11a|hbf|fetal hemoglobin|globin|sickle|thalassemia|engraftment|repopulation)\b", "literature_positioning"),
    ("battery_phase_taxonomy", r"\b(p2|o3|p3|phase famil|phase type|phase types|phase transition|stacking|slab gliding|deep desodiation|degradation pathways?)\b", "literature_positioning"),
    ("battery_commercial_benchmark", r"\b(commercial viability|commercially viable|promising alternative|cost[- ]?per[- ]?kwh|wh/kg|wh/l|energy density|lfp|nmc|grid storage|ev applications?)\b", "literature_positioning"),
    ("battery_cei_electrolyte", r"\b(cei|cathode[- ]electrolyte interphase|surface decomposition|surface degradation|electrolyte|fec|fluoroethylene carbonate|passivat|interphase chemistry)\b", "literature_positioning"),
    ("battery_characterization_causality", r"\b(operando|in situ|ex situ|post[- ]mortem|tem|xrd|xps|raman|beam damage|characterization|causal claims?|causal overstatement)\b", "causal_claim"),
    ("battery_moisture_manufacturing", r"\b(air sensitivity|moisture sensitivity|dry room|dry-room|slurry|manufactur|industrial scalab|environmental controls?)\b", "literature_positioning"),
    ("battery_transition_metal_costs", r"\b(transition metal|nickel|cobalt|ni[- ]rich|co[- ]rich|high[- ]ni|precursor cost|elemental cost)\b", "literature_positioning"),
    ("figure_caption_permissions", r"\b(figure|caption|legend|reproduced|adapted|permission|copyright|image credit)\b", "clarity"),
    ("materials_review_methodology", r"\b(sodium[- ]ion|na[- ]ion|battery|batteries|layered oxide|cathode|materials?)\b.{0,220}\b(systematic review|search strateg|search strings?|database|screening criteria|inclusion criteria|exclusion criteria|benchmarking|methodolog)\b|\b(systematic review|search strateg|search strings?|database|screening criteria|inclusion criteria|exclusion criteria|benchmarking|methodolog)\b.{0,220}\b(sodium[- ]ion|na[- ]ion|battery|batteries|layered oxide|cathode|materials?)\b", "methodology"),
    ("pedagogy_boundary_conditions", r"\b(limitations?|boundary conditions?|constraints?|institutional polic|digital literacy|access inequ|guardrails?|rlhf|safety guardrails?|student agency|dialogic authority|practical constraints?)\b", "framework_validation"),
    ("pedagogy_operationalization", r"\b(heuristic|operationali[sz]e|classroom artifacts?|sample assignment|rubric|assessment|grading|checklist|step[- ]by[- ]step|teaching activity|curricular artifact)\b", "methodology"),
    ("ai_technical_precision", r"\b(data dump|knowledge cutoff|model version|chatgpt version|parameters? reset|new dialogue|new chat|technical language|training data cutoff)\b", "clarity"),
    ("authorship_agency_theory", r"\b(authorship|ownership|posthuman|distributed agency|agency|student ownership|human[- ]ai collaboration|rhetorical agency)\b", "literature_positioning"),
    ("foundational_theory_positioning", r"\b(process theory|post[- ]process|composition theory|rhetorical theory|digital rhetoric|writing studies|foundational theor)\b", "literature_positioning"),
    ("deployment_validation_positioning", r"\b(external validation failure|external validation failures|transportability failure|deployment controvers|major controversies|deployed prediction|model generalizability|model transportability)\b", "literature_positioning"),
    ("review_reporting_transparency", r"\b(prisma|flowchart|flow diagram|search strings?|database coverage|database names?|date ranges?|exclusion reason|excluded studies|full-text exclusion|flow accounting|replicable search)\b", "methodology"),
    ("protocol_registration", r"\b(prospero|protocol registration|registered protocol|prospectively registered|timestamped protocol)\b", "methodology"),
    ("search_scope_bias", r"\b(gray literature|grey literature|white paper|quality.improvement report|implementation report|health system report|regulatory submission|conference proceeding|vendor report|preprint|registries|english.language|published in english|titles? and abstracts?.{0,80}english|language restriction)\b", "methodology"),
    ("rob_tool_mismatch", r"\b(rob 2|robins-i|risk.of.bias tool|tool choice)\b", "methodology"),
    ("commercial_bias_conflicts", r"\b(conflict.of.interest|commercial bias|vendor|industry sponsor|funding source|developer.evaluat|commercial conflict)\b", "methodology"),
    ("qualitative_synthesis_reproducibility", r"\b(coding framework|inter-rater|interrater|kappa|qualitative analysis|thematic analysis|audit trail|barriers, enablers|barriers/enablers)\b", "methodology"),
    ("lead_time_clinical_relevance", r"\b(lead time|alert.{0,80}antibiotic|clinical significance|time.to.antibiotic|minutes earlier|hours earlier)\b", "deployment"),
    ("algorithmic_fairness_gap", r"\b(fairness|algorithmic bias|demographic|subgroup|equity|racial|calibration drift|health disparities)\b", "deployment"),
    ("definition_heterogeneity", r"\b(definition heterogeneity|definitional heterogeneity|(?:different|differing|varying|multiple|several|inconsistent|competing|heterogeneous)\s+(?:[\w-]+\s+){0,2}definitions?|definitions?\s+(?:varied|differed|were inconsistent))\b", "methodology"),
    ("causal_mortality_overstatement", r"\b(mortality|causal|causation|confounding|before.after|observational)\b", "causal_claim"),
    ("framework_generalizability", r"\b(framework validation|framework generalizability|ai.task agnostic|task[- ]agnostic|generalizability|companion paper|cfir|nasss|re-aim|decide-ai|necessary and sufficient)\b", "framework_validation"),
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


def _token_set(text: str) -> set[str]:
    return set(_norm(text).split())


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / max(1, len(left | right))


def _section_key(task: dict[str, Any]) -> str:
    """Normalized section identity: lowercase first segment before '/' or ';'."""
    raw = str(task.get("section") or "").lower().strip()
    return re.split(r"[/;,]", raw, maxsplit=1)[0].strip()


def _fingerprint(*parts: str) -> str:
    normalized = _norm(" ".join(part for part in parts if part))[:220]
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]


def _dedupe_category(problem: str, suggested_action: str, task_type: str) -> str:
    text = f"{problem} {suggested_action}".lower()
    for category, pattern, _canonical_type in CATEGORY_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL):
            return category
    if task_type == "citation":
        return f"citation:{_fingerprint(problem, suggested_action)}"
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


def _source_key(source: dict[str, Any]) -> str:
    return str(
        source.get("document_id")
        or source.get("doi")
        or source.get("url")
        or source.get("paper_url")
        or source.get("pdf_url")
        or source.get("title")
        or source.get("document_title")
        or ""
    ).strip().lower()


def _merge_task(existing: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    severity_rank = {"critical": 3, "major": 2, "minor": 1, "suggestion": 0}
    priority_rank = {"high": 3, "medium": 2, "low": 1}
    merged = dict(existing)
    merged_from = list(dict.fromkeys(
        (existing.get("merged_from_task_ids") or [existing.get("id")])
        + (candidate.get("merged_from_task_ids") or [candidate.get("id")])
    ))
    merged["merged_from_task_ids"] = [task_id for task_id in merged_from if task_id]
    merged["duplicate_count"] = int(existing.get("duplicate_count") or 0) + int(candidate.get("duplicate_count") or 0) + 1
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
        key = _source_key(source)
        if not key or key in seen_sources:
            continue
        seen_sources.add(key)
        deduped_sources.append(source)
    if deduped_sources:
        merged["suggested_sources"] = deduped_sources[:5]
    for key in ("page_number", "paragraph_index", "line_number", "char_start", "char_end", "pdf_coordinates", "match_confidence"):
        if merged.get(key) is None and candidate.get(key) is not None:
            merged[key] = candidate[key]
    merged["issue_family"] = existing.get("issue_family") or candidate.get("issue_family") or existing.get("dedupe_category")
    return merged


def _issue_family(problem: str, suggested_action: str, task_type: str) -> str:
    text = f"{problem} {suggested_action}".lower()
    for category, pattern, _canonical_type in CATEGORY_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL):
            return category
    if task_type == "citation":
        return f"citation:{_fingerprint(problem, suggested_action)}"
    return f"{task_type or 'other'}:{_fingerprint(problem, suggested_action)}"


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


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)


def _task_similarity_text(task: dict[str, Any]) -> str:
    return _clip_text(
        " ".join(
            str(task.get(key) or "")
            for key in ("problem", "why_it_matters", "suggested_action", "anchor_text", "section")
        ),
        1800,
    )


def _embedding_clusters(tasks: list[dict[str, Any]], threshold: float = 0.85) -> dict[int, int]:
    """Return candidate->cluster-index links using embeddings when available."""
    if len(tasks) < 2 or not os.getenv("OPENAI_API_KEY") or os.getenv("PYTEST_CURRENT_TEST"):
        return {}
    try:
        from app.services.rag_ingest import embed_chunks

        embeddings = embed_chunks(
            [_task_similarity_text(task) for task in tasks],
            model="text-embedding-3-small",
        )
        vectors = [item.embedding for item in embeddings or []]
        if len(vectors) != len(tasks):
            return {}
    except Exception:
        return {}

    parent: dict[int, int] = {}
    for idx in range(len(tasks)):
        for prior in range(idx):
            if _cosine_similarity(vectors[idx], vectors[prior]) >= threshold:
                parent[idx] = parent.get(prior, prior)
                break
    return parent


def _task_merge_text(task: dict[str, Any]) -> str:
    return " ".join(
        str(task.get(key) or "")
        for key in ("problem", "why_it_matters", "suggested_action")
    )


def _anchor_overlap(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_anchor = _norm(str(left.get("anchor_text") or left.get("text_snippet") or ""))
    right_anchor = _norm(str(right.get("anchor_text") or right.get("text_snippet") or ""))
    if not left_anchor or not right_anchor:
        return False
    if left_anchor == right_anchor:
        return True
    shorter, longer = sorted((left_anchor, right_anchor), key=len)
    return len(shorter) >= 32 and shorter in longer


def _should_merge_tasks(candidate: dict[str, Any], existing: dict[str, Any]) -> bool:
    """Conservatively merge duplicate critiques across async agents.

    The first-pass dedupe keys are intentionally precise. This second pass is
    allowed to be semantic: same anchor, same issue family, or high lexical
    overlap should collapse even when one agent labels the task as citation and
    another labels it clarity/methodology.
    """
    if candidate.get("issue_family") and candidate.get("issue_family") == existing.get("issue_family"):
        return True

    candidate_text = _norm(_task_merge_text(candidate))
    existing_text = _norm(_task_merge_text(existing))
    if not candidate_text or not existing_text:
        return False

    sequence_ratio = SequenceMatcher(None, candidate_text, existing_text).ratio()
    token_overlap = _jaccard(set(candidate_text.split()), set(existing_text.split()))
    same_anchor = _anchor_overlap(candidate, existing)

    if sequence_ratio >= 0.72:
        return True
    if token_overlap >= 0.50:
        return True
    if same_anchor and (sequence_ratio >= 0.46 or token_overlap >= 0.30):
        return True

    # Cross-agent duplicates often share the same concrete noun phrase but use
    # different labels. Require a strong overlap to avoid collapsing unrelated
    # issues within the same section.
    if candidate.get("section") and candidate.get("section") == existing.get("section"):
        return token_overlap >= 0.42 and sequence_ratio >= 0.55

    # Two tasks of the SAME task_type targeting the SAME section (normalized) are
    # very likely the same underlying critique phrased differently (e.g. two
    # "search terms are too restrictive" methodology tasks). The task_type+section
    # match lets us merge at a more permissive overlap without collapsing distinct
    # issues (different type or section will not reach here).
    same_section = _section_key(candidate) and _section_key(candidate) == _section_key(existing)
    same_type = candidate.get("task_type") and candidate.get("task_type") == existing.get("task_type")
    if same_section and same_type:
        # Use containment (shared / smaller set) rather than Jaccard: paraphrases of
        # the same critique often differ in length, which deflates Jaccard but not
        # containment. Distinct same-section issues share few content words, so
        # containment stays low for them.
        ctoks, etoks = set(candidate_text.split()), set(existing_text.split())
        containment = len(ctoks & etoks) / max(1, min(len(ctoks), len(etoks)))
        if containment >= 0.5 or token_overlap >= 0.34 or sequence_ratio >= 0.50:
            return True
    return False


def consolidate_revision_tasks(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Second-pass task consolidation for paraphrased duplicates across agents."""
    if not tasks:
        return []

    embedding_links = _embedding_clusters(tasks)
    consolidated: list[dict[str, Any]] = []
    family_index: dict[str, int] = {}
    original_to_consolidated: dict[int, int] = {}
    order = {"high": 0, "medium": 1, "low": 2}

    for idx, task in enumerate(tasks):
        next_task = dict(task)
        family = next_task.get("issue_family") or _issue_family(
            next_task.get("problem", ""),
            next_task.get("suggested_action", ""),
            next_task.get("task_type", "other"),
        )
        next_task["issue_family"] = family
        next_task.setdefault("merged_from_task_ids", [next_task.get("id")])
        next_task.setdefault("duplicate_count", 0)

        linked_original_index = embedding_links.get(idx)
        target_index = (
            original_to_consolidated.get(linked_original_index)
            if linked_original_index is not None
            else None
        )
        if target_index is None and family in family_index:
            target_index = family_index[family]
        if target_index is None:
            for existing_index, existing in enumerate(consolidated):
                if _should_merge_tasks(next_task, existing):
                    target_index = existing_index
                    break

        if target_index is None:
            family_index[family] = len(consolidated)
            consolidated.append(next_task)
            original_to_consolidated[idx] = len(consolidated) - 1
            continue

        consolidated[target_index] = _merge_task(consolidated[target_index], next_task)
        family_index[family] = target_index
        original_to_consolidated[idx] = target_index

    return sorted(
        consolidated,
        key=lambda t: (order.get(t.get("priority"), 1), t.get("section", ""), t.get("problem", "")),
    )


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
    has_formatting_only_signal = bool(re.search(r"\b(all caps|capitalization|hyphenation|typograph|heading format|section heading|conversational subheadings?|informal headings?|tone policing)\b", text))
    has_substantive_signal = bool(re.search(r"\b(figure|table|caption|legend|reference|citation|readability|methods|results|prisma)\b", text))
    return has_formatting_only_signal and not has_substantive_signal


def _is_parser_artifact_task(
    problem: str,
    suggested_action: str,
    *,
    structure: dict[str, Any] | None = None,
    parser_quality: dict[str, Any] | None = None,
) -> bool:
    text = f"{problem} {suggested_action}".lower()
    structure = structure or {}
    flags = set((parser_quality or {}).get("parser_quality_flags") or [])

    if re.search(r"\b(no|missing|lacks?).{0,80}\babstract\b|\babstract section\b.{0,80}\b(not listed|missing|absent)\b", text):
        return bool(structure.get("has_abstract") or flags)
    if re.search(r"\b(truncated|missing|abbreviated).{0,80}\bmethods?\b|\bmethods?.{0,80}(truncated|missing|absent)\b", text):
        return bool(structure.get("has_methods") or flags)
    if re.search(r"\b(repeated headings?|disorganized structure|spacing inconsistenc|cd34\s*\+|gfp\s*\+|mcherry\s*\+|truncated phrases?|concatenated words?|embedded mid[- ]sentence|reading order|figure references?.{0,80}(inconsistent|malformed|unclear))\b", text):
        return bool(flags or structure.get("document_metadata", {}).get("grobid_extracted"))
    if re.search(r"\b(no|missing|lacks?).{0,80}\blimitations? section\b", text):
        # Short-letter journals often omit a dedicated Limitations heading. Keep
        # real limitation-content critiques from reviewers, suppress heading-only tasks.
        return "dedicated" in text or "clearly labeled" in text
    return False


def _profile_route_keys(manuscript_profile: dict[str, Any] | None) -> set[str]:
    if not manuscript_profile:
        return set()
    keys = {
        str(manuscript_profile.get("routing_domain") or "").lower(),
        str(manuscript_profile.get("genre") or "").lower(),
        str(manuscript_profile.get("evidence_mode") or "").lower(),
    }
    keys |= {str(item).lower() for item in manuscript_profile.get("domain_tags") or []}
    keys |= {str(item).lower() for item in manuscript_profile.get("review_lenses") or []}
    return {key for key in keys if key}


def _is_low_value_common_knowledge_citation(
    claim: dict[str, Any],
    manuscript_profile: dict[str, Any] | None,
) -> bool:
    """Avoid turning everyday software-use observations into citation tasks.

    The same text can still be critiqued by reviewers as technical precision,
    but conceptual/humanities papers should not be flooded with formal source
    demands for ordinary product-behavior statements.
    """
    route_keys = _profile_route_keys(manuscript_profile)
    if not route_keys & {"humanities_education", "humanities_theory", "computer_science_conceptual", "pedagogical", "pedagogical_conceptual", "conceptual"}:
        return False
    text = str(claim.get("claim_text") or claim.get("text_snippet") or "").lower()
    if not text:
        return False
    return bool(re.search(
        r"\b(new chat|new dialogue|dialogue is opened|conversation is opened|parameters? (are )?reset|knowledge cutoff|data dump|training data cutoff)\b",
        text,
    ))


def _is_internal_gap_leak(problem: str, suggested_action: str, *, source_type: str) -> bool:
    """Suppress machine-readable coverage gaps that were never written for users."""
    if source_type != "gap":
        return False
    text = problem.lower()
    leak_patterns = (
        r"^claim in .{0,220}(no supporting citations found|no matching evidence)",
        r"\bno matching evidence in library or online\b",
        r"^no baseline comparisons mentioned for methodology$",
        r"^no baseline comparisons mentioned for methodology\b",
    )
    return any(re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL) for pattern in leak_patterns)


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
    structure: dict[str, Any] | None = None,
    parser_quality: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    problem = _clean_problem(problem)
    suggested_action = _clean_problem(suggested_action)
    if not _is_valid_text(problem) or not _is_valid_text(suggested_action):
        return None
    if _is_internal_gap_leak(problem, suggested_action, source_type=source_type):
        return None
    if task_type == "clarity" and _is_low_value_formatting_task(problem, suggested_action):
        return None
    if _is_parser_artifact_task(
        problem,
        suggested_action,
        structure=structure,
        parser_quality=parser_quality,
    ):
        return None

    source = source or {}
    severity = (severity or "major").lower()
    anchor_source = anchor_text or source.get("text_snippet") or source.get("anchor_text") or section or problem
    dedupe_category = _dedupe_category(problem, suggested_action, task_type)
    if task_type != "citation":
        task_type = _canonical_task_type(dedupe_category, task_type)
    issue_family = _issue_family(problem, suggested_action, task_type)
    task = {
        "id": f"task_{_fingerprint(dedupe_category)}",
        "dedupe_category": dedupe_category,
        "issue_family": issue_family,
        "source_type": source_type,
        "task_type": task_type,
        "severity": severity if severity in {"critical", "major", "minor", "suggestion"} else "major",
        "priority": _priority(severity),
        "section": section or "",
        "anchor_text": _clip_text(anchor_source, 700),
        "line_number": source.get("line_number"),
        "char_start": source.get("char_start"),
        "char_end": source.get("char_end"),
        "page_number": source.get("page_number"),
        "paragraph_index": source.get("paragraph_index"),
        "text_snippet": _clip_text(source.get("text_snippet") or anchor_source, 900),
        "pdf_coordinates": source.get("pdf_coordinates"),
        "match_confidence": source.get("match_confidence"),
        "problem": problem,
        "why_it_matters": _clean_problem(why_it_matters),
        "suggested_action": suggested_action,
        "source_ids": [sid for sid in (source_ids or []) if sid],
        "suggested_sources": suggested_sources or source.get("suggested_sources") or [],
        "confidence": max(0.0, min(float(confidence or 0.8), 1.0)),
        "status": "new",
        "merged_from_task_ids": [f"task_{_fingerprint(dedupe_category)}"],
        "duplicate_count": 0,
    }
    return {k: v for k, v in task.items() if v is not None}


def build_revision_tasks(
    *,
    diagnostic_findings: list[dict[str, Any]],
    reviewer_outputs: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    gaps: list[dict[str, Any]],
    structural_feedback: list[dict[str, Any]],
    structure: dict[str, Any] | None = None,
    parser_quality: dict[str, Any] | None = None,
    manuscript_profile: dict[str, Any] | None = None,
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
            structure=structure,
            parser_quality=parser_quality,
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
                structure=structure,
                parser_quality=parser_quality,
            ))

    for claim in claims or []:
        claim = apply_existing_citation_gate(dict(claim))
        if not needs_missing_citation_task(claim):
            continue
        if _is_low_value_common_knowledge_citation(claim, manuscript_profile):
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
            structure=structure,
            parser_quality=parser_quality,
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
            structure=structure,
            parser_quality=parser_quality,
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
            structure=structure,
            parser_quality=parser_quality,
        ))

    order = {"high": 0, "medium": 1, "low": 2}
    final_tasks = list(tasks_by_category.values())
    sorted_tasks = sorted(final_tasks, key=lambda t: (order.get(t.get("priority"), 1), t.get("section", ""), t.get("problem", "")))
    return consolidate_revision_tasks(sorted_tasks)


def _scoring_policy(manuscript_profile: dict[str, Any] | None) -> dict[str, Any]:
    route_keys = _profile_route_keys(manuscript_profile)
    if route_keys & {"humanities_education", "humanities_theory", "social_science_qualitative", "pedagogical", "conceptual", "pedagogical_conceptual"}:
        return {
            "name": "conceptual_pedagogical",
            "critical_weight": 5.0,
            "major_weight": 2.0,
            "minor_weight": 0.5,
            "citation_without_source_weight": 1.5,
            "volume_major_threshold": 10,
            "volume_critical_threshold": 4,
        }
    if route_keys & {"computer_science_ml", "empirical_ml", "clinical_ai"}:
        return {
            "name": "empirical_computational",
            "critical_weight": 9.0,
            "major_weight": 4.0,
            "minor_weight": 1.0,
            "citation_without_source_weight": 4.0,
            "volume_major_threshold": 7,
            "volume_critical_threshold": 3,
        }
    if route_keys & {"biology", "biomedical", "medicine", "chemistry_materials", "physics", "engineering"}:
        return {
            "name": "scientific_empirical",
            "critical_weight": 8.0,
            "major_weight": 3.5,
            "minor_weight": 1.0,
            "citation_without_source_weight": 3.0,
            "volume_major_threshold": 8,
            "volume_critical_threshold": 3,
        }
    return {
        "name": "general_journal_article",
        "critical_weight": 8.0,
        "major_weight": 3.0,
        "minor_weight": 1.0,
        "citation_without_source_weight": 4.0,
        "volume_major_threshold": 8,
        "volume_critical_threshold": 3,
    }


def calculate_revision_task_readiness_score(
    tasks: list[dict[str, Any]],
    manuscript_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    critical = sum(1 for task in tasks if task.get("severity") == "critical")
    major = sum(1 for task in tasks if task.get("severity") == "major")
    minor = sum(1 for task in tasks if task.get("severity") == "minor")
    citation_without_source = sum(
        1 for task in tasks
        if task.get("task_type") == "citation" and not task.get("suggested_sources")
    )
    duplicate_count = sum(int(task.get("duplicate_count") or 0) for task in tasks)
    policy = _scoring_policy(manuscript_profile)
    deductions = (
        critical * policy["critical_weight"]
        + major * policy["major_weight"]
        + minor * policy["minor_weight"]
        + citation_without_source * policy["citation_without_source_weight"]
    )
    score = max(0, min(100, round(100 - deductions)))
    guardrail = None
    if critical >= policy["volume_critical_threshold"] or major >= policy["volume_major_threshold"]:
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
            "merged_duplicate_tasks": duplicate_count,
            "total_deductions": round(deductions, 2),
            "guardrail": guardrail,
            "domain_scoring_policy": policy["name"],
            "scoring_weights": {
                "critical": policy["critical_weight"],
                "major": policy["major_weight"],
                "minor": policy["minor_weight"],
                "citation_without_source": policy["citation_without_source_weight"],
            },
        },
    }

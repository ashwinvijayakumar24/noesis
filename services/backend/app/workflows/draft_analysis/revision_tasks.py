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

# A1: Review-genre manuscripts are excluded from claim→citation task generation
# (dense citation prose makes nearly all "missing citation" signals false positives).
_REVIEW_GENRES: frozenset[str] = frozenset(
    {"literature_review", "systematic_review", "review", "narrative_review"}
)

# A1: For non-review manuscripts, a corroborating string must express citation/evidence
# intent — not merely share topic tokens — before a citation task is emitted.
_CITATION_INTENT_RE = re.compile(
    r"\b(uncited|unsupported|missing citation|needs? (?:a )?citation|without (?:a )?(?:source|citation|reference)"
    r"|lacks? (?:a )?(?:(?:supporting|verif\w+|primary|direct)\s+)?(?:citation|source|reference)"
    r"|no (?:supporting )?(?:citation|source|reference)"
    r"|requires? (?:a )?(?:citation|source|reference)|citation needed"
    r"|add (?:a )?(?:citation|source|reference)|provide (?:a )?(?:citation|source|reference)"
    r"|add (?:a )?(?:primary|direct|supporting) source)\b",
    re.I,
)

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
    # Materials-characterization terms ONLY — the generic "characterization"/"causal
    # claims" terms were removed because they bled this battery label onto non-materials
    # drafts (issue: battery->sepsis label bleed). Generic causal critiques fall to
    # causal_mortality_overstatement / causal_claim instead.
    ("battery_characterization_causality", r"\b(operando|in situ|ex situ|post[- ]mortem|xrd|xps|raman|beam damage|galvanostatic|coulombic efficiency)\b", "causal_claim"),
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
    # Domain-agnostic "how was the literature selected/searched" family — a catch-all for
    # generic methodology critiques that don't mention the subject domain. Placed AFTER
    # the specific PRISMA-reporting + search-scope families so those match first (first-
    # match wins); this only catches the generic leftovers. Unified with
    # materials_review_methodology via _SUPER_FAMILY so a domain-specific and a generic
    # "describe your literature selection" critique collapse into one task.
    ("literature_selection_reporting", r"\b(literature (?:selection|search)|search strateg(?:y|ies)|search method|inclusion criteria|exclusion criteria|inclusion[- /]and[- /]exclusion|selection criteria|screening (?:criteria|process)|how (?:the )?(?:literature|studies|papers|sources) (?:were|was) (?:selected|collected|searched|identified|chosen|filtered)|scope of (?:the|this) review|databases? (?:searched|queried|used))\b", "methodology"),
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


# Coarse super-families so CLOSELY-related issue families collapse into one cohesive
# directive — kept narrow to avoid flattening genuinely distinct methodological
# points (PRISMA reporting stays separate from search scope; both are distinct from
# risk-of-bias). Stale-search joins search-scope (both "search coverage is limited");
# risk-of-bias tool + conflicts-of-interest + reproducibility join one quality pass.
_SUPER_FAMILY = {
    "search_currency": "search_scope_bias",
    "rob_tool_mismatch": "risk_of_bias_extraction",
    "commercial_bias_conflicts": "risk_of_bias_extraction",
    "qualitative_synthesis_reproducibility": "risk_of_bias_extraction",
    # A domain-specific methodology critique and a generic literature-selection critique
    # are the same underlying point ("describe how the literature was selected") — merge
    # them so two paraphrased methodology tasks don't ship as separate, contradictory
    # entries. PRISMA-flow reporting (review_reporting_transparency) stays separate.
    "materials_review_methodology": "literature_selection_reporting",
}


def _super_family(family: str) -> str:
    return _SUPER_FAMILY.get(family, family)


def _resolve_search_contradictions(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop the 'search dates incomplete' task when a stale-search task is present.

    The stale-search critique (search_currency) confirms the manuscript DID report a
    search date (and it's old); a separate task claiming the dates 'may be incomplete'
    directly contradicts it. Keep the evidence-backed stale-search critique.
    """
    has_stale_search = any(
        (t.get("issue_family") == "search_currency" or t.get("dedupe_category") == "search_currency")
        for t in tasks
    )
    if not has_stale_search:
        return tasks
    kept: list[dict[str, Any]] = []
    for t in tasks:
        if t.get("issue_family") == "search_currency" or t.get("dedupe_category") == "search_currency":
            kept.append(t)
            continue
        reason = str(t.get("evidence_rebuttal_reason") or "")
        text = f"{t.get('problem', '')} {t.get('suggested_action', '')}".lower()
        contradicts = reason == "databases_found" or bool(
            re.search(r"search dates?.{0,40}(incomplete|missing|not (?:clearly )?reported|per database)", text)
        )
        if not contradicts:
            kept.append(t)
    return kept


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


# Diagnostic categories that must NEVER be dropped by clustering, regardless of
# similarity score (issue #18): a sepsis-model fairness finding was caught by the
# diagnostic engine but merged away into a generic deployment task.
# Tight: bare "bias" is NOT undroppable — "publication bias", "risk of bias",
# "language bias" are routine systematic-review methodology, not safety/ethics. Only
# genuine fairness/demographic/safety/ethics critiques are undroppable.
_UNDROPPABLE_FINDING_RE = re.compile(
    r"\b(fairness|equity|demographic|disparit|discrimination|"
    r"algorithmic bias|racial bias|gender bias|sex bias|"
    r"health equit|patient safety|ethical|ethics|harm to patients)\b",
    re.IGNORECASE,
)

_SEVERITY_RANK = {"critical": 3, "major": 2, "minor": 1, "suggestion": 0, "high": 3, "medium": 2, "low": 1}


def _finding_text(finding: dict[str, Any]) -> str:
    return " ".join(
        str(finding.get(key) or "")
        for key in ("problem", "why_it_matters", "suggested_action", "finding_type")
    )


def _task_covers_finding(task: dict[str, Any], finding_tokens: set[str], finding_text: str) -> bool:
    """A final task covers a finding if their problem text overlaps strongly."""
    task_text = _task_merge_text(task)
    task_tokens = _token_set(task_text)
    if not task_tokens or not finding_tokens:
        return False
    overlap = len(task_tokens & finding_tokens) / max(1, len(finding_tokens))
    if overlap >= 0.6:
        return True
    return SequenceMatcher(None, _norm(task_text), _norm(finding_text)).ratio() >= 0.75


def rescue_critical_diagnostics(
    tasks: list[dict[str, Any]],
    diagnostic_findings: list[dict[str, Any]] | None,
    *,
    structure: dict[str, Any] | None = None,
    parser_quality: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Promote any critical/major diagnostic finding not represented in the final task
    list back to a standalone task (issue #18). Fairness/bias/safety/ethics findings are
    undroppable regardless of similarity — they must never be merged into a generic task."""
    if not diagnostic_findings:
        return tasks
    rescued = list(tasks)
    existing_families = {_super_family(str(t.get("issue_family") or "")) for t in rescued}
    existing_categories = {str(t.get("dedupe_category") or "") for t in rescued}
    for finding in diagnostic_findings:
        severity = (finding.get("severity") or "").lower()
        if severity not in {"critical", "major"}:
            continue
        ftext = _finding_text(finding)
        is_undroppable = bool(_UNDROPPABLE_FINDING_RE.search(ftext))
        promoted = _base_task(
            source_type="diagnostic_rescue",
            task_type=_task_type(finding.get("finding_type", "")),
            severity=severity,
            section=finding.get("section_reference", ""),
            anchor_text=finding.get("anchor_text", ""),
            problem=finding.get("problem", ""),
            why_it_matters=finding.get("why_it_matters", ""),
            suggested_action=finding.get("suggested_action", ""),
            confidence=finding.get("confidence", 0.85),
            source=finding,
            structure=structure,
            parser_quality=parser_quality,
        )
        if not promoted:
            continue
        promoted["issue_family"] = _super_family(str(promoted.get("issue_family") or ""))
        cand_family = promoted["issue_family"]
        cand_category = str(promoted.get("dedupe_category") or "")
        # Covered if a final task shares the finding's issue family / dedupe category
        # (it was merged in during clustering), would merge with it under the standard
        # dedup rules, or strongly overlaps its text.
        ftokens = _token_set(ftext)
        covered = (
            cand_family in existing_families
            or cand_category in existing_categories
            or any(_should_merge_tasks(promoted, t) for t in rescued)
            or any(_task_covers_finding(t, ftokens, ftext) for t in rescued)
        )
        # Undroppable categories (fairness/bias/safety/ethics) must appear as their OWN
        # durable task even if a generic task loosely covers them — but only promote
        # one per category so we don't spam duplicates.
        if covered and not is_undroppable:
            continue
        if is_undroppable and any(
            t.get("rescued_from_finding") and _UNDROPPABLE_FINDING_RE.search(_task_merge_text(t))
            for t in rescued
        ):
            continue
        promoted["rescued_from_finding"] = True
        promoted["undroppable"] = is_undroppable
        promoted["priority"] = _priority(severity)
        rescued.append(promoted)
        existing_families.add(cand_family)
        existing_categories.add(cand_category)
    order = {"high": 0, "medium": 1, "low": 2}
    return sorted(rescued, key=lambda t: (order.get(t.get("priority"), 1), t.get("section", ""), t.get("problem", "")))


def final_pairwise_dedup(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Final deterministic pairwise pass over surviving tasks (issue #20). For any pair
    with high text similarity in the SAME section/topic cluster, keep the stronger task
    (higher severity -> more specific anchor -> longer action) and merge the other's
    anchor into ``related_anchors``. Undroppable rescued tasks are never merged away."""
    if len(tasks) < 2:
        return tasks
    survivors: list[dict[str, Any]] = []
    for cand in tasks:
        cand_text = _norm(_task_merge_text(cand))
        cand_tokens = set(cand_text.split())
        merged_into_existing = False
        for i, keep in enumerate(survivors):
            # Only collapse within the same section/topic cluster (don't merge a
            # methodology critique with a literature-positioning one even if text overlaps).
            same_cluster = (
                _section_key(cand) == _section_key(keep)
                or (cand.get("issue_family") and cand.get("issue_family") == keep.get("issue_family"))
                or (cand.get("task_type") and cand.get("task_type") == keep.get("task_type"))
            )
            if not same_cluster:
                continue
            keep_text = _norm(_task_merge_text(keep))
            ratio = SequenceMatcher(None, cand_text, keep_text).ratio()
            overlap = _jaccard(cand_tokens, set(keep_text.split()))
            if ratio < 0.82 and overlap < 0.7:
                continue
            if keep.get("undroppable") or cand.get("undroppable"):
                # Never merge an undroppable task — its specificity is the value.
                continue
            stronger, weaker = _pick_stronger(keep, cand)
            merged = dict(stronger)
            anchors = list(merged.get("related_anchors") or [])
            weak_anchor = weaker.get("anchor_text") or weaker.get("text_snippet")
            if weak_anchor and weak_anchor not in anchors:
                anchors.append(weak_anchor)
            if anchors:
                merged["related_anchors"] = anchors
            merged["merged_from_task_ids"] = list(dict.fromkeys(
                (keep.get("merged_from_task_ids") or [keep.get("id")])
                + (cand.get("merged_from_task_ids") or [cand.get("id")])
            ))
            merged["duplicate_count"] = int(keep.get("duplicate_count") or 0) + int(cand.get("duplicate_count") or 0) + 1
            survivors[i] = merged
            merged_into_existing = True
            break
        if not merged_into_existing:
            survivors.append(cand)
    return survivors


def merge_anchor_collisions(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge tasks that point at the SAME verbatim anchor into one multi-part task.

    Two separate major tasks lighting up the identical block of text (Gemini eval:
    Na-ion Tasks 7 & 8 shared an 87-word anchor) induce UI fatigue. Keep the stronger
    task and fold the other's problem into its suggested_action as an added point.
    Undroppable/audit-grounded tasks are never folded away (kept standalone)."""
    if len(tasks) < 2:
        return tasks
    by_anchor: dict[str, int] = {}
    survivors: list[dict[str, Any]] = []
    for task in tasks:
        anchor = _norm((task.get("anchor_text") or "").strip())
        # Only collide on substantial shared anchors; null/short anchors don't collide.
        if not anchor or len(anchor.split()) < 4 or task.get("undroppable") or task.get("audit_grounded"):
            survivors.append(task)
            continue
        if anchor in by_anchor:
            keep = survivors[by_anchor[anchor]]
            if keep.get("undroppable") or keep.get("audit_grounded"):
                survivors.append(task)
                continue
            stronger, weaker = _pick_stronger(keep, task)
            merged = dict(stronger)
            extra = (weaker.get("problem") or "").strip()
            if extra and extra not in (merged.get("suggested_action") or ""):
                merged["suggested_action"] = (
                    (merged.get("suggested_action") or "").rstrip()
                    + f" Additionally, address a distinct point at the same location: {extra}"
                )
            merged["duplicate_count"] = int(keep.get("duplicate_count") or 0) + int(task.get("duplicate_count") or 0) + 1
            survivors[by_anchor[anchor]] = merged
        else:
            by_anchor[anchor] = len(survivors)
            survivors.append(task)
    return survivors


def _pick_stronger(a: dict[str, Any], b: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (stronger, weaker): higher severity, then more specific anchor, then longer action."""
    ra, rb = _SEVERITY_RANK.get((a.get("severity") or "").lower(), 0), _SEVERITY_RANK.get((b.get("severity") or "").lower(), 0)
    if ra != rb:
        return (a, b) if ra > rb else (b, a)
    # More specific anchor = locatable page anchor present.
    a_anchored = a.get("page_number") is not None
    b_anchored = b.get("page_number") is not None
    if a_anchored != b_anchored:
        return (a, b) if a_anchored else (b, a)
    if len(str(a.get("suggested_action") or "")) >= len(str(b.get("suggested_action") or "")):
        return a, b
    return b, a


def consolidate_revision_tasks(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Second-pass task consolidation for paraphrased duplicates across agents."""
    if not tasks:
        return []

    tasks = _resolve_search_contradictions(tasks)
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
        family = _super_family(family)
        next_task["issue_family"] = family
        next_task.setdefault("merged_from_task_ids", [next_task.get("id")])
        next_task.setdefault("duplicate_count", 0)

        # Undroppable / audit-grounded tasks are never merged away here — keep them
        # standalone (this pass has no undroppable guard, unlike final_pairwise_dedup
        # and llm_dedupe_tasks, and was silently absorbing the protein-validation task
        # into a same-family methodology task). Not registered as a family leader so
        # nothing else folds into it either.
        if next_task.get("undroppable") or next_task.get("audit_grounded"):
            consolidated.append(next_task)
            original_to_consolidated[idx] = len(consolidated) - 1
            continue

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


_LLM_DEDUP_SYSTEM_PROMPT = (
    "You consolidate a reviewer's revision tasks. Group tasks that address the SAME "
    "underlying flaw, even when worded differently (e.g. 'P-values without stating # "
    "independent colonies' and 'P-values without stating # biological replicates' are the "
    "same statistical-independence flaw; 'CD34+ HSPC modification details missing' and "
    "'CD34+ HSPC transfection conditions missing' are the same methods-detail flaw). Only "
    "group tasks a reviewer would consolidate into ONE revision. Do NOT group merely "
    "related-but-distinct critiques (different flaws in the same section stay separate). "
    "Only merge tasks that address the IDENTICAL underlying flaw. A SPECIFIC critique "
    "(e.g. pseudoreplication — treating colonies from one donor as independent n) is NOT "
    "the same as a GENERIC one (e.g. 'report sample sizes') — keep the specific one "
    "distinct. When in doubt, do NOT merge. "
    "Return clusters of the given task indices; singletons may be omitted."
)


async def llm_dedupe_tasks(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """LLM semantic-dedup pass for same-critique-different-words pairs that survive
    lexical AND embedding dedup (within-domain paraphrases score ~0.6 cosine, below any
    safe threshold). ONE batched gpt-5.2 call returns clusters of task indices; each
    cluster of >1 is merged into one task via the existing `_merge_task` helper (highest
    severity, most specific anchor, longest action, union of sources). Singletons and
    original order are preserved.

    On ANY failure (no client, parse error, malformed clusters) returns tasks unchanged.
    """
    all_tasks = list(tasks or [])
    if len(all_tasks) < 2:
        return all_tasks

    try:
        from app.core.openai_client import get_async_openai_client, get_completion_params
        from app.services.retry_utils import parse_chat_completion_with_retries
        from app.workflows.draft_analysis.schemas import TaskClusters

        lines = []
        for idx, task in enumerate(all_tasks):
            lines.append(
                f"[{idx}]\n"
                f"  problem: {task.get('problem') or ''}\n"
                f"  suggested_action: {task.get('suggested_action') or ''}\n"
                f"  task_type: {task.get('task_type') or ''}"
            )
        user_content = (
            "Revision tasks (group indices that address the same underlying flaw):\n"
            + "\n".join(lines)
        )

        response = await parse_chat_completion_with_retries(
            get_async_openai_client(),
            model="gpt-5.2-chat-latest",
            messages=[
                {"role": "system", "content": _LLM_DEDUP_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            max_completion_tokens=1000,
            response_format=TaskClusters,
            **get_completion_params(),
        )
        clusters = response.parsed.clusters or []

        # Distinct high-value critiques must never be merged away into a vaguer task.
        # An undroppable / rescued / meta-must-address task is kept standalone: it is
        # excluded from every cluster before merging.
        def _is_protected(task: dict[str, Any]) -> bool:
            return bool(
                task.get("undroppable")
                or task.get("rescued_from_finding")
                or task.get("source_type") == "meta_must_address"
            )

        protected_indices = {i for i, t in enumerate(all_tasks) if _is_protected(t)}

        # Map each index to its cluster leader (lowest index in the cluster). Ignore
        # out-of-range / duplicate indices so a malformed cluster never drops a task.
        leader_of: dict[int, int] = {}
        for cluster in clusters:
            members = sorted({
                i for i in cluster
                if isinstance(i, int) and 0 <= i < len(all_tasks) and i not in protected_indices
            })
            if len(members) < 2:
                continue
            leader = members[0]
            for i in members:
                # First assignment wins so an index is never re-merged into two clusters.
                leader_of.setdefault(i, leader)

        if not leader_of:
            return all_tasks

        # Merge in original order: each leader accumulates its followers via _merge_task.
        merged_by_leader: dict[int, dict[str, Any]] = {
            i: dict(all_tasks[i]) for i in set(leader_of.values())
        }
        for idx, task in enumerate(all_tasks):
            leader = leader_of.get(idx)
            if leader is not None and leader != idx:
                merged_by_leader[leader] = _merge_task(merged_by_leader[leader], task)

        # Emit in original order: singletons as-is, each leader once (merged), followers skipped.
        final: list[dict[str, Any]] = []
        for idx, task in enumerate(all_tasks):
            leader = leader_of.get(idx)
            if leader is None:
                final.append(task)
            elif leader == idx:
                final.append(merged_by_leader[idx])
        return final
    except Exception:
        # Never crash the pipeline on an LLM failure.
        return all_tasks


# Methodological-validity issues are never trivial for empirical work — missing
# replication, controls, statistical independence, risk-of-bias, safety/validation, or
# search/selection reporting must not ship as `minor` (issue #10: a missing-biological-
# replicates task was tagged minor on the CRISPR run).
_CRITICAL_METHODOLOGY_SIGNALS = re.compile(
    r"\b(biological replicate|technical replicate|replicat|pseudoreplicat|"
    r"control group|negative control|sample size|statistical (?:independence|power|test)|"
    r"risk of bias|off[- ]target|safety assay|orthogonal validation|"
    r"reproducib|search strateg|literature (?:selection|search)|inclusion criteria)\b",
    re.IGNORECASE,
)


def _floor_methodology_severity(task: dict[str, Any]) -> dict[str, Any]:
    """Raise a methodological-validity task tagged minor/suggestion to at least 'major'.
    These gaps are reject-level in empirical work; tagging them minor is misleading
    prioritization. Conservative: floors to 'major', never auto-escalates to 'critical'."""
    if (task.get("severity") or "").lower() in {"minor", "suggestion"}:
        text = f"{task.get('problem', '')} {task.get('suggested_action', '')}"
        if _CRITICAL_METHODOLOGY_SIGNALS.search(text):
            task["severity"] = "major"
            task["priority"] = _priority("major")
            task["severity_driver"] = "methodology_validity_floor"
    return task


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
    has_formatting_only_signal = bool(re.search(
        r"\b(all caps|capitalization|hyphenation|typograph|heading format|section heading"
        r"|conversational subheadings?|informal headings?|tone policing"
        r"|grammatical|grammar|awkward(?:ly)?|imprecise|phrasing|word choice|wording"
        r"|sentence structure|verb tense|typo)\b",
        text,
    ))
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

    # B3 — Docling inline-figure-callout / truncated-sentence parser artifacts.
    # Suppress when the critique is specifically about the text being broken or interrupted
    # by a figure callout (e.g. "...modified CD34 + Fig. 3" mid-sentence glitch).
    # Guard: must have a truncation/interruption signal AND a figure/text-break indicator —
    # never suppress substantive content critiques.
    _TRUNCATION_SIGNAL = re.compile(
        r"truncated sentence|incomplete sentence|sentence\s+(?:is\s+)?cut\s+off"
        r"|interrupted\s+(?:by|mid)"
        r"|interrupted\s+by\s+fig"
        r"|fragmented\s+(?:text|sentence)"
        r"|abruptly\s+ends"
        r"|mid[- ]sentence\s+(?:insertion|break|interrupt)"
        # B3 strengthen: catch the "incomplete and truncated" / bare "truncated"
        # description-of-the-text scolds the reviewer raises for parser glitches.
        r"|incomplete\s+and\s+truncated"
        r"|\b(?:is|are|appears?|seems?)\s+(?:incomplete|truncated)\b"
        r"|description\s+is\s+(?:incomplete|truncated)"
        r"|\btruncated\b.{0,40}(?:sentence|text|description|mid)",
        re.IGNORECASE,
    )
    _FIGURE_CALLOUT_SIGNAL = re.compile(
        r"\bfig(?:ure)?\.?\s*\d+\b.{0,60}(?:interrupt|mid[- ]sentence|inserted|breaks?|broken|splits?)"
        r"|interrupted\s+by\s+fig(?:ure)?\.?\s*\d+"
        # B3 strengthen: generic inline-callout join glitch — any "<word> + Fig. N"
        # (Docling/GROBID splices a figure callout into the text stream, e.g.
        # "modified CD34 + Fig. 3"). Real prose almost never writes "word + Fig N".
        r"|\b\w+\s*\+\s*fig(?:ure)?\.?\s*\d+"
        r"|obscur\w*\s+(?:the\s+)?(?:intended\s+)?meaning",
        re.IGNORECASE,
    )
    if _TRUNCATION_SIGNAL.search(text) or _FIGURE_CALLOUT_SIGNAL.search(text):
        # Only suppress when this is clearly about broken/truncated text, not
        # substantive clarity issues (e.g. "sentence is unclear" is not suppressed).
        return True

    return False


_DEDUCTIVE_FRAMING_RE = re.compile(
    r"^\s*(therefore|thus|hence|in short|in summary|in conclusion|overall|generally|"
    r"as a result|consequently|up to now|so far|actually|in fact|evidently|clearly|"
    r"importantly|notably|in other words|to summari[sz]e|taken together)\b",
    re.IGNORECASE,
)
_RHETORICAL_FRAMING_RE = re.compile(
    r"\b("
    r"play(?:s|ing)?\s+(?:an?\s+)?(?:important|key|significant|crucial|vital|central|major)\s+role"
    r"|(?:evident|obvious|clear|numerous|various)\s+advantages"
    r"|(?:great|huge|enormous|significant)\s+(?:prospects?|potential|promise|importance)"
    r"|widely\s+(?:regarded|recognized|considered|used)"
    r"|(?:is|are)\s+(?:essential|crucial|vital|important|necessary)\s+(?:to|for)"
    r"|attracted?\s+(?:much|considerable|increasing|growing)\s+(?:attention|interest)"
    r")\b",
    re.IGNORECASE,
)


def _is_deductive_framing_claim(claim_text: str) -> bool:
    """Author framing/transition sentences are NOT citable empirical claims.

    Gemini eval: a citation was demanded for 'Sodium-ion batteries ... play an
    important commercial role due to their evident advantages.' Penalizing
    rhetorical/deductive framing as a missing-citation degrades perceived
    intelligence. Suppress sentences that open with a deductive marker OR consist
    of vague evaluative framing rather than a specific factual assertion."""
    t = (claim_text or "").strip()
    if not t:
        return False
    if _DEDUCTIVE_FRAMING_RE.search(t):
        return True
    # Vague evaluative framing AND no specific number/comparator that would warrant a source.
    if _RHETORICAL_FRAMING_RE.search(t) and not re.search(r"\d|%|\bvs\.?\b|compared", t):
        return True
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


def _is_author_self_referential(claim_text: str, author_coined_terms: list[str] | None) -> bool:
    """True if the claim is about the authors' own framework/model/contribution.

    You cannot demand an external citation for the authors' own thesis (issue #17:
    the SALIENT-framework false positive). Matches the coined term as a whole word so
    a short acronym doesn't match inside an unrelated word."""
    if not author_coined_terms:
        return False
    text = (claim_text or "").lower()
    if not text:
        return False
    for term in author_coined_terms:
        term = (term or "").strip().lower()
        if len(term) < 2:
            continue
        if re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text):
            return True
    return False


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


_MANUFACTURER_CUE = re.compile(
    r"manufacturer'?s? (?:instructions?|protocol|recommendations?)"
    r"|per the manufacturer"
    r"|according to the manufacturer"
    r"|as recommended by the (?:manufacturer|supplier|vendor)",
    re.IGNORECASE,
)

# Micro-parameter demands (volumes, times, concentrations, temps) that are
# legitimately deferred to a commercial kit's manufacturer protocol.
_MICRO_PARAMETER_DEMAND = re.compile(
    r"\bincubation time"
    r"|\bbuffer volume"
    r"|\breagent (?:amount|volume|quantit)"
    r"|\b(?:exact|specific|precise)\s+(?:volume|amount|concentration|temperature)"
    r"|\bvolumes?\b"
    r"|\bconcentrations?\b"
    r"|\btemperatures?\b"
    r"|\bincubation\b",
    re.IGNORECASE,
)

# Substantive methodology critiques that must NEVER be dropped even if a
# manufacturer cue and a parameter word co-occur.
_SUBSTANTIVE_METHOD_SIGNAL = re.compile(
    r"\bdelivery (?:modality|method|route)"
    r"|\breplicat"
    r"|\bpseudoreplicat"
    r"|\bbiological (?:replicate|donor)"
    r"|\bcontrols?\b"
    r"|\bsample size"
    r"|\brandomiz"
    r"|\bblind(?:ing|ed)?\b",
    re.IGNORECASE,
)


def _is_manufacturer_protocol_nitpick(
    problem: str,
    suggested_action: str,
    anchor_text: str,
) -> bool:
    """True for pedantic micro-parameter demands already covered by a kit's
    manufacturer protocol (Task 7 pedantry).

    Drops ONLY when the task is a micro-parameter demand AND a manufacturer cue
    is present in the anchor/snippet AND it is not a substantive methodology
    critique (delivery modality, replication, controls)."""
    request = f"{problem} {suggested_action}"
    if not _MICRO_PARAMETER_DEMAND.search(request):
        return False
    if _SUBSTANTIVE_METHOD_SIGNAL.search(request):
        return False
    if not _MANUFACTURER_CUE.search(anchor_text or ""):
        return False
    return True


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
    # HOTFIX 3: the reviewer sometimes collapses problem and suggested_action into the
    # same text. Don't drop the task (it may be a real issue) — replace the duplicate
    # action with a neutral pointer so the payload never shows twin identical fields.
    if _norm(problem) == _norm(suggested_action) or (
        SequenceMatcher(None, _norm(problem), _norm(suggested_action)).ratio() >= 0.92
    ):
        suggested_action = "Address the issue described above."
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
    # FIX 4a: drop pedantic micro-parameter demands already covered by a kit's
    # manufacturer protocol (only methodology/reproducibility tasks).
    if task_type in {"methodology", "reproducibility"}:
        cue_text = " ".join(
            t for t in (
                anchor_text,
                (source or {}).get("text_snippet"),
                (source or {}).get("anchor_text"),
            ) if t
        )
        if _is_manufacturer_protocol_nitpick(problem, suggested_action, cue_text):
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


def _must_address_covering_task(
    must_item: str, tasks: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Return the task that covers must_item, or None if uncovered.

    Deterministic check used when embeddings are unavailable (test env / no key).
    Mirrors scripts/proof_meta_owns_tasks.py exactly:
    - token overlap (must_item tokens ∩ task tokens / must tokens) >= 0.5
    - OR SequenceMatcher ratio >= 0.55
    Empty items are treated as covered (returns first task, or None if no tasks).
    """
    must_tokens = _token_set(must_item)
    must_norm = _norm(must_item)
    if not must_tokens:
        return tasks[0] if tasks else None
    for task in tasks:
        task_text = _task_merge_text(task)
        task_tokens = _token_set(task_text)
        task_norm = _norm(task_text)
        if task_tokens:
            overlap = len(must_tokens & task_tokens) / max(1, len(must_tokens))
            if overlap >= 0.5:
                return task
        if must_norm and task_norm:
            if SequenceMatcher(None, must_norm, task_norm).ratio() >= 0.55:
                return task
    return None


def _must_address_covered_fallback(must_item: str, tasks: list[dict[str, Any]]) -> bool:
    """Bool wrapper around _must_address_covering_task (kept for existing callers)."""
    return _must_address_covering_task(must_item, tasks) is not None


def ensure_must_address_coverage(
    tasks: list[dict[str, Any]],
    must_address: list[str],
    reviewer_outputs: list[dict[str, Any]],
    *,
    structure: dict[str, Any] | None = None,
    parser_quality: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Guarantee every meta-reviewer must_address item has a durable task.

    For each must_address item, determine if it is already covered by any existing
    task. Uncovered items are promoted to tasks with undroppable=True.

    Coverage check:
    - PRIMARY: embedding cosine >= 0.60 (skipped in test env / no API key).
    - FALLBACK: token overlap >= 0.5 OR SequenceMatcher ratio >= 0.55
      (mirrors scripts/proof_meta_owns_tasks.py).
    """
    if not must_address:
        return tasks

    use_embeddings = bool(
        os.getenv("OPENAI_API_KEY") and not os.getenv("PYTEST_CURRENT_TEST")
    )

    # Build embedding vectors for coverage check if possible.
    must_vectors: list[list[float]] = []
    task_vectors: list[list[float]] = []
    embeddings_ok = False

    if use_embeddings and tasks:
        try:
            from app.services.rag_ingest import embed_chunks

            all_texts = list(must_address) + [_task_similarity_text(t) for t in tasks]
            results = embed_chunks(all_texts, model="text-embedding-3-small")
            vectors = [item.embedding for item in results or []]
            if len(vectors) == len(all_texts):
                must_vectors = vectors[: len(must_address)]
                task_vectors = vectors[len(must_address):]
                embeddings_ok = True
        except Exception:
            embeddings_ok = False

    new_tasks: list[dict[str, Any]] = []

    for idx, must_item in enumerate(must_address):
        if not (must_item or "").strip():
            continue

        # Determine coverage AND which task covers it. When covered, we must
        # protect the covering task from downstream dedup (otherwise embedding
        # noise on the 0.60 boundary makes the item appear/vanish run-to-run —
        # the source of the protein-validation 2/5 variance).
        covering_task: dict[str, Any] | None = None
        if embeddings_ok and must_vectors and task_vectors:
            best_cos = 0.0
            for tpos, tvec in enumerate(task_vectors):
                cos = _cosine_similarity(must_vectors[idx], tvec)
                if cos >= 0.60 and cos > best_cos:
                    best_cos = cos
                    covering_task = tasks[tpos] if tpos < len(tasks) else None

        if covering_task is None:
            covering_task = _must_address_covering_task(must_item, tasks)

        if covering_task is not None:
            # Pin the covering task so dedup can never merge it away.
            covering_task["undroppable"] = True
            covering_task.setdefault("meta_must_address_covered", True)
            continue

        # Borrow anchor_text from the reviewer issue with highest token overlap.
        anchor_text = ""
        best_overlap = 0.0
        must_tokens = _token_set(must_item)
        for reviewer in reviewer_outputs or []:
            for issue in reviewer.get("issues") or []:
                issue_anchor = str(issue.get("anchor_text") or issue.get("problem") or "")
                if not issue_anchor:
                    continue
                issue_tokens = _token_set(issue_anchor)
                if must_tokens and issue_tokens:
                    overlap = len(must_tokens & issue_tokens) / max(1, len(must_tokens))
                    if overlap > best_overlap:
                        best_overlap = overlap
                        anchor_text = issue_anchor
        if best_overlap <= 0.2:
            anchor_text = ""

        # Infer task_type from keywords in the must_address item.
        item_lower = must_item.lower()
        if any(kw in item_lower for kw in ("method", "statistical", "protocol", "procedure", "analysis", "design")):
            inferred_type = "methodology"
        elif any(kw in item_lower for kw in ("literature", "citation", "reference", "prior work", "related work", "position")):
            inferred_type = "literature_positioning"
        elif any(kw in item_lower for kw in ("clarity", "unclear", "ambiguous", "confus", "explain")):
            inferred_type = "clarity"
        elif any(kw in item_lower for kw in ("causal", "causality", "overstat", "claim")):
            inferred_type = "causal_claim"
        else:
            inferred_type = "other"

        task = _base_task(
            source_type="meta_must_address",
            task_type=inferred_type,
            severity="major",
            section="",
            anchor_text=anchor_text,
            problem=must_item,
            why_it_matters="Named by the meta-reviewer as a blocking item for acceptance.",
            suggested_action=must_item,
            structure=structure,
            parser_quality=parser_quality,
        )
        if task is None:
            continue
        task["undroppable"] = True
        task["priority"] = _priority("major")
        new_tasks.append(task)

    return tasks + new_tasks


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
    meta_review: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    tasks_by_category: dict[str, dict[str, Any]] = {}

    def add(task: dict[str, Any] | None) -> None:
        if not task:
            return
        # Deterministic domain-trigger audit findings (and other undroppable tasks)
        # must never be merged away or dropped here — the category-merge keeps the
        # EXISTING task and discards the candidate's text, which silently lost the
        # protein-validation catch. Append standalone; later near-duplicates of it
        # are dropped by the _is_duplicate check below (it stays the canonical task).
        if task.get("audit_grounded") or task.get("undroppable"):
            # Register under a UNIQUE key so it is included in tasks_by_category.values()
            # (the actual output source) and never collides into a merge.
            tasks_by_category[f"__undroppable__{len(tasks_by_category)}__{id(task)}"] = task
            tasks.append(task)
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
            # A3: clarity-lane issues default minor; all other issue types stay major.
            _issue_severity = "minor" if issue.get("issue_type", "").lower() == "clarity" else "major"
            _issue_task = _base_task(
                source_type="reviewer_issue",
                task_type=_task_type(issue.get("issue_type", "")),
                severity=_issue_severity,
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
            )
            # Deterministic domain-trigger audit findings are already grounded-entailment
            # verified — flag them so the downstream LLM absence-verifier never
            # re-litigates and drops them (the source of the protein-validation variance).
            if _issue_task is not None and issue.get("audit_grounded"):
                _issue_task["audit_grounded"] = True
                _issue_task["undroppable"] = True
            add(_issue_task)

    author_coined_terms = (manuscript_profile or {}).get("author_coined_terms") or []

    # Phase 2a / A1: build a corroboration corpus ONCE before iterating claims.
    # A citation task is only emitted when a reviewer or must_address item explicitly
    # flags the same claim — uncorroborated claims are still staged to citation_suggestions.
    # Corpus is (string, is_reviewer_issue) so the intent check applies only to reviewer
    # strings (must_address items are already high-priority signals and bypass intent gate).
    must_address_local = (meta_review or {}).get("must_address") or []
    _corroboration_corpus: list[tuple[str, bool]] = []
    for _rev in reviewer_outputs or []:
        for _issue in _rev.get("issues") or []:
            _at = _issue.get("anchor_text") or ""
            _pb = _issue.get("problem") or ""
            if _at:
                _corroboration_corpus.append((_at, True))
            if _pb:
                _corroboration_corpus.append((_pb, True))
    for _ma in must_address_local:
        if _ma:
            _corroboration_corpus.append((_ma, False))

    def _claim_is_corroborated(claim_text: str, text_snippet: str) -> bool:
        """Return True if any corroboration string overlaps this claim at ≥0.3 token ratio
        OR shares a verbatim anchor segment, AND at least one of those overlapping strings
        also expresses explicit citation/evidence intent (A1 non-review guard).
        Must_address items count as overlap only when paired with a reviewer intent hit."""
        if not _corroboration_corpus:
            return False
        claim_tokens = _token_set(claim_text) | _token_set(text_snippet)
        if not claim_tokens:
            return False
        claim_dict = {"anchor_text": text_snippet or claim_text}
        for corr, is_reviewer_issue in _corroboration_corpus:
            token_match = False
            corr_tokens = _token_set(corr)
            if corr_tokens:
                overlap_ratio = len(claim_tokens & corr_tokens) / len(claim_tokens)
                if overlap_ratio >= 0.3:
                    token_match = True
            anchor_match = _anchor_overlap(claim_dict, {"anchor_text": corr})
            if (token_match or anchor_match) and is_reviewer_issue and _CITATION_INTENT_RE.search(corr):
                return True
        return False

    # Determine if the manuscript is a review genre (A1).
    _genre = str((manuscript_profile or {}).get("genre") or "").lower()
    _is_review_genre = _genre in _REVIEW_GENRES

    for claim in claims or []:
        claim = apply_existing_citation_gate(dict(claim))
        if not needs_missing_citation_task(claim):
            continue
        if _is_low_value_common_knowledge_citation(claim, manuscript_profile):
            continue
        # Don't demand citations for rhetorical/deductive framing sentences.
        if _is_deductive_framing_claim(claim.get("claim_text", "")):
            continue
        # Issue #17: never demand a citation for the authors' own framework/model thesis.
        if _is_author_self_referential(claim.get("claim_text", ""), author_coined_terms):
            continue
        # A1: review-genre manuscripts skip claim→citation task generation entirely.
        # Reviews cite densely; "missing citation" on their prose is ~always a false positive.
        # (Claims still go to citation_suggestions via the separate path.)
        if _is_review_genre:
            continue
        # Phase 2a / A1: require corroboration with citation intent from reviewer issues
        # or must_address before emitting a durable citation task.
        if not _claim_is_corroborated(
            claim.get("claim_text", ""), claim.get("text_snippet", "")
        ):
            continue
        suggested_sources = claim.get("suggested_sources") or []
        add(_base_task(
            source_type="claim",
            task_type="citation",
            # Threshold aligned with gap_detection (>= 0.7) so the same claim never gets
            # a different severity from the gap path vs the citation path.
            severity="critical" if (claim.get("importance_score") or 0) >= 0.7 else "major",
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
    final_tasks = [_floor_methodology_severity(t) for t in tasks_by_category.values()]
    sorted_tasks = sorted(final_tasks, key=lambda t: (order.get(t.get("priority"), 1), t.get("section", ""), t.get("problem", "")))
    consolidated = consolidate_revision_tasks(sorted_tasks)
    # Rescue high-value diagnostics dropped by clustering (issue #18), then a final
    # deterministic pairwise pass to collapse near-duplicate survivors (issue #20).
    consolidated = rescue_critical_diagnostics(
        consolidated, diagnostic_findings, structure=structure, parser_quality=parser_quality
    )
    # Guarantee every meta-reviewer must_address priority has a durable task.
    must_address = (meta_review or {}).get("must_address") or []
    consolidated = ensure_must_address_coverage(
        consolidated,
        must_address,
        reviewer_outputs or [],
        structure=structure,
        parser_quality=parser_quality,
    )
    consolidated = final_pairwise_dedup(consolidated)
    consolidated = merge_anchor_collisions(consolidated)

    # BACKSTOP: guarantee every audit-grounded reviewer issue (deterministic
    # domain-trigger finding) has a surviving task. Multiple merge/consolidate
    # passes can still absorb one; re-inject any that vanished. This is the single
    # source of truth for trigger consistency regardless of upstream dedup.
    for reviewer in reviewer_outputs or []:
        for issue in reviewer.get("issues") or []:
            if not issue.get("audit_grounded"):
                continue
            problem = (issue.get("problem") or "").strip()
            if not problem:
                continue
            ptoks = _token_set(problem)
            survived = any(
                _token_set(t.get("problem", "")) and ptoks
                and len(ptoks & _token_set(t.get("problem", ""))) / max(1, len(ptoks)) >= 0.6
                for t in consolidated
            )
            if survived:
                continue
            backstop = _base_task(
                source_type="reviewer_issue",
                task_type=_task_type(issue.get("issue_type", "")),
                severity="major",
                section=issue.get("section_reference", ""),
                anchor_text=issue.get("anchor_text", ""),
                problem=problem,
                why_it_matters=issue.get("why_it_matters", ""),
                suggested_action=issue.get("suggested_action", ""),
                source_ids=[reviewer.get("reviewer_id", "reviewer")],
                confidence=issue.get("confidence", 0.85),
                source=issue,
                structure=structure,
                parser_quality=parser_quality,
            )
            if backstop is None:
                # _base_task suppressors must not silence an audit-grounded finding.
                backstop = {
                    "id": f"task_audit_{abs(hash(problem)) % (10**8)}",
                    "source_type": "reviewer_issue",
                    "task_type": _task_type(issue.get("issue_type", "")),
                    "severity": "major",
                    "priority": _priority("major"),
                    "section": issue.get("section_reference", "") or "",
                    "anchor_text": issue.get("anchor_text", "") or "",
                    "problem": problem,
                    "why_it_matters": issue.get("why_it_matters", "") or "",
                    "suggested_action": issue.get("suggested_action", "") or "Address the issue described above.",
                    "source_ids": [reviewer.get("reviewer_id", "reviewer")],
                    "confidence": issue.get("confidence", 0.85),
                    "status": "new",
                }
            backstop["audit_grounded"] = True
            backstop["undroppable"] = True
            consolidated.append(backstop)

    # Guarantee unique task ids before persist. Audit/undroppable tasks bypass the
    # dedupe-category merge, so two can share a `task_{fingerprint(category)}` id and
    # trip the DB unique constraint (Error 23505 -> the whole run fails to persist).
    _seen_ids: set[str] = set()
    for t in consolidated:
        tid = t.get("id") or ""
        if tid in _seen_ids:
            suffix = 1
            new_id = f"{tid}_{suffix}"
            while new_id in _seen_ids:
                suffix += 1
                new_id = f"{tid}_{suffix}"
            t["id"] = new_id
            tid = new_id
        _seen_ids.add(tid)

    return consolidated


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

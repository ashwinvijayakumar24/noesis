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


# Phrases that assert something is ABSENT from the manuscript. A task carrying one of
# these is making a falsifiable claim about the body text — verify it before shipping
# at full severity (issue #2: the biggest trust-killer is "X is missing" when X is there).
_ABSENCE_MARKERS = (
    "is missing", "are missing", "is absent", "are absent", "does not address",
    "do not address", "not mentioned", "fails to", "fail to", "not discussed",
    "no mention", "lacks", "lack of", "omits", "omit ", "not provided",
    "not compared", "not described", "not reported", "does not provide",
    "does not discuss", "does not include", "without any", "no discussion of",
    # B2 extended markers — vocabulary mismatch in earlier lexical fallback defeated these
    "not detailed", "does not specify", "not specified", "is not described",
    "are not described", "without", "no quantitative", "not quantified",
    "is unclear", "are unclear", "incompletely described", "not fully specified",
)

_DOWNGRADE = {"critical": "major", "major": "minor", "minor": "minor", "suggestion": "suggestion"}
_PRIORITY_FROM_SEVERITY = {"critical": "high", "major": "medium", "minor": "low", "suggestion": "low"}

# Generic words that carry no topical signal when matching a task against the body.
_GROUNDING_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "for", "with", "is",
    "are", "was", "were", "be", "been", "this", "that", "these", "those", "it", "its",
    "not", "no", "does", "do", "any", "their", "there", "which", "should", "would",
    "manuscript", "paper", "study", "review", "author", "authors", "section", "discuss",
    "discussed", "address", "addressed", "missing", "absent", "lacks", "lack", "provide",
    "provided", "mention", "mentioned", "report", "reported", "include", "included",
}


def _content_terms(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z][a-z0-9-]{2,}", (text or "").lower()) if t not in _GROUNDING_STOPWORDS]


def _split_paragraphs(text: str) -> list[str]:
    paras = re.split(r"\n\s*\n", text or "")
    return [p for p in (_norm(p) for p in paras) if len(p) >= 40]


def _best_paragraph_match(query_terms: list[str], paragraphs: list[str]) -> tuple[float, str]:
    """Return (score in 0..1, best paragraph). Uses rank_bm25 when available, else a
    deterministic term-coverage proxy (fraction of distinct query terms present)."""
    if not query_terms or not paragraphs:
        return 0.0, ""
    q = list(dict.fromkeys(query_terms))
    try:
        from rank_bm25 import BM25Okapi  # optional; falls back below if unavailable
        tokenized = [_content_terms(p) for p in paragraphs]
        bm25 = BM25Okapi(tokenized)
        scores = bm25.get_scores(q)
        best_i = max(range(len(scores)), key=lambda i: scores[i])
        # Normalize BM25 against an idealized self-match so the threshold is interpretable.
        ideal = max(bm25.get_scores(_content_terms(paragraphs[best_i]))[best_i], 1e-9)
        return min(1.0, float(scores[best_i]) / float(ideal)), paragraphs[best_i]
    except Exception:
        qset = set(q)
        best_score, best_para = 0.0, ""
        for para in paragraphs:
            pset = set(_content_terms(para))
            if not pset:
                continue
            coverage = len(qset & pset) / max(1, len(qset))
            if coverage > best_score:
                best_score, best_para = coverage, para
        return best_score, best_para


def _prefix_stems(terms: list[str], min_prefix: int = 5) -> set[str]:
    """Return a set of prefixes (length >= min_prefix) for morphological tolerance.

    "cytokine" and "cytokines" share the stem "cytoki"; "culture" and "cultured"
    share "cultu". Matching on 5-char prefixes catches common inflections without
    a full stemmer dependency.
    """
    return {t[:min_prefix] for t in terms if len(t) >= min_prefix}


def _self_anchor_contradicts(task: dict[str, Any]) -> bool:
    """B1: Return True when the task's own anchor/snippet already answers the critique.

    A 'X is missing' task whose quoted anchor_text contains the claimed-missing
    content terms is a guaranteed false positive — the task contradicts its own
    evidence. We require a substantial fraction (>= 0.5 of query terms OR >= 3
    distinct matched terms) to avoid over-suppression on short anchors.

    Matching uses 5-char prefix stems so inflectional variants ("cytokine" /
    "cytokines", "culture" / "cultured") are treated as the same term.
    """
    anchor_blob = " ".join(filter(None, [
        str(task.get("anchor_text") or ""),
        str(task.get("text_snippet") or ""),
    ]))
    if not anchor_blob.strip():
        return False
    problem = str(task.get("problem") or "")
    action = str(task.get("suggested_action") or "")
    query_terms = _content_terms(f"{action} {problem}")
    if not query_terms:
        return False
    anchor_stems = _prefix_stems(list(_content_terms(anchor_blob)))
    query_unique = list(dict.fromkeys(query_terms))
    query_stems_unique = list(dict.fromkeys(t[:5] for t in query_unique if len(t) >= 5))
    matched = [s for s in query_stems_unique if s in anchor_stems]
    total_unique = len(query_stems_unique) or len(set(query_terms))
    fraction = len(matched) / max(1, total_unique)
    return fraction >= 0.5 or len(matched) >= 3


def _self_anchor_contradicts_semantic(task: dict[str, Any], threshold: float = 0.60) -> bool:
    """B1 semantic path: True when the task's own anchor answers the critique.

    Embeds the claimed-missing text (problem + suggested_action) against the task's
    own anchor_text/text_snippet. A cosine >= threshold means the anchor semantically
    supplies what the critique says is missing (e.g. "StemSpan SFEM / SCF / Tpo" vs
    "culture medium / cytokine conditions") even when no stems lexically overlap.

    Only used when embeddings are available; callers fall back to the lexical check.
    """
    anchor_blob = " ".join(filter(None, [
        str(task.get("anchor_text") or ""),
        str(task.get("text_snippet") or ""),
    ])).strip()
    claimed = f"{task.get('problem') or ''} {task.get('suggested_action') or ''}".strip()
    if not anchor_blob or not claimed:
        return False
    return _semantic_max_cosine(claimed, [anchor_blob]) >= threshold


def _embeddings_available() -> bool:
    """True when we may make a real embedding call (key present, not under pytest)."""
    import os
    return bool(os.environ.get("OPENAI_API_KEY")) and not os.environ.get("PYTEST_CURRENT_TEST")


def _cosine(vec_a: list[float], vec_b: list[float]) -> float:
    import math
    norm_a = math.sqrt(sum(x * x for x in vec_a)) or 1.0
    norm_b = math.sqrt(sum(x * x for x in vec_b)) or 1.0
    return sum(a * b for a, b in zip(vec_a, vec_b)) / (norm_a * norm_b)


def _semantic_max_cosine(query_text: str, candidate_texts: list[str]) -> float:
    """Embed query_text + candidates in one batch; return the max cosine vs query.

    Only called when embeddings are available. Returns -1.0 on any error/empty input.
    The first returned vector is the query; the rest are candidates. `embed_chunks`
    yields objects with a `.embedding` attribute (list[float]).
    """
    candidates = [c for c in candidate_texts if c and c.strip()]
    if not query_text or not query_text.strip() or not candidates:
        return -1.0
    try:
        from app.services.rag_ingest import embed_chunks  # reuse project embedder
        results = embed_chunks([query_text] + candidates[:50], model="text-embedding-3-small")
        if not results or len(results) < 2:
            return -1.0
        vectors = [r.embedding for r in results]
        query_vec = vectors[0]
        return max((_cosine(query_vec, cv) for cv in vectors[1:]), default=-1.0)
    except Exception:
        return -1.0


def _semantic_body_score(claimed_missing_text: str, paragraphs: list[str]) -> float:
    """B2 primary path: embed claimed-missing text + paragraphs and return max cosine.

    Only called when OPENAI_API_KEY is available and we are NOT inside a test run.
    Falls back silently (returns -1.0) on any error.
    """
    if not _embeddings_available():
        return -1.0
    return _semantic_max_cosine(claimed_missing_text, paragraphs[:50])


def verify_absence_claims(
    tasks: list[dict[str, Any]],
    draft_content: str,
    *,
    threshold: float = 0.7,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Pre-emit grounding check (issue #2 / Prong B) — SYNC, no-LLM fallback.

    For any task asserting X is missing/absent:

    B1 (self-anchor contradiction — highest precision, DROP):
        LEXICAL stem-prefix match (>= 0.5 fraction OR >= 3 distinct matches) between the
        claimed-missing text and the task's own anchor_text/text_snippet → DROP. The
        critique contradicts its own evidence.

    B2 (body grounding — DOWNGRADE + flag, never drop):
        LEXICAL _best_paragraph_match with lower threshold ~0.5 → downgrade.

    NOTE: embedding-cosine paths were removed (empirically disproven — see
    llm_verify_absence_claims). Both B1 and B2 here are high-precision/low-recall
    lexical checks that are SAFE (they do not match off-target / protein-validation /
    statistics negatives). The real false-absence fix is the async LLM entailment
    verifier below; this sync function is the no-LLM fallback only.

    Returns (tasks, metrics).
    """
    paragraphs = _split_paragraphs(draft_content)
    downgraded = 0
    self_contradiction_dropped = 0
    out: list[dict[str, Any]] = []

    for task in tasks or []:
        problem = str(task.get("problem") or "")
        # Domain-trigger audit findings are already grounded-entailment verified.
        if task.get("audit_grounded"):
            out.append(task)
            continue
        if not any(marker in problem.lower() for marker in _ABSENCE_MARKERS):
            out.append(task)
            continue

        # B1 — self-anchor contradiction check (DROP, highest precision).
        # LEXICAL stem-prefix matching only (the semantic cosine path was disproven and
        # removed: real off-target/protein issues scored AT/ABOVE the false positives).
        if _self_anchor_contradicts(task):
            self_contradiction_dropped += 1
            continue  # task dropped — do not add to out

        # B2 — body grounding (DOWNGRADE only, not drop). LEXICAL term-coverage only.
        query = _content_terms(f"{task.get('suggested_action', '')} {problem}")
        lex_threshold = min(threshold, 0.5)
        score, para = _best_paragraph_match(query, paragraphs)
        if score < lex_threshold:
            out.append(task)
            continue

        # Downgrade severity but leave `problem` CLEAN — the verifier note goes in a
        # separate field (verification_note) so internal text never leaks into the
        # user-facing problem string (HOTFIX 1).
        updated = dict(task)
        sev = (updated.get("severity") or "major").lower()
        updated["severity"] = _DOWNGRADE.get(sev, sev)
        updated["priority"] = _PRIORITY_FROM_SEVERITY.get(updated["severity"], updated.get("priority", "medium"))
        excerpt = para[:160] + ("..." if len(para) > 160 else "")
        updated["verification_status"] = "partially_addressed"
        updated["verification_note"] = excerpt
        updated["grounding_flag"] = "possibly_addressed_in_text"
        updated["grounding_match_score"] = round(score, 3)
        out.append(updated)
        downgraded += 1

    return out, {
        "absence_tasks_downgraded": downgraded,
        "self_contradiction_dropped": self_contradiction_dropped,
    }


_LLM_ABSENCE_SYSTEM_PROMPT = (
    "You verify whether a manuscript ALREADY provides what each critique claims is "
    "missing. For each item decide: 'addressed' (the manuscript/anchor already provides "
    "it — the critique is a false positive), 'partial' (related info present but the "
    "specific ask is genuinely incomplete), or 'absent' (genuinely missing). Be strict: "
    "mRNA is NOT protein validation; a T7E1 assay does NOT satisfy a demand for "
    "genome-wide GUIDE-seq; listing reagents (e.g. StemSpan SFEM, SCF, Tpo) DOES satisfy "
    "a demand to detail cytokine/culture conditions. Quote the evidence when "
    "addressed/partial."
)


async def llm_verify_absence_claims(
    tasks: list[dict[str, Any]],
    draft_content: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """LLM entailment verifier for false-absence claims (the real Prong B fix).

    Embedding-cosine and lexical similarity both fail to distinguish a false absence
    (critique vs anchor cosine 0.48-0.59) from a real one (off-target 0.61,
    protein-validation 0.64): the positives score LOWER than the negatives, so no
    threshold works. Only LLM entailment separates them.

    Batches ALL absence-marked tasks into ONE gpt-5.2 call. Verdicts:
      - addressed → DROP the task (false positive).
      - partial   → downgrade one severity + prepend a "Verify: partially addressed"
                    note with the quoted evidence + grounding_flag="llm_partial".
      - absent    → keep unchanged.

    On ANY failure (no client, parse error, etc.) falls back to the SYNC lexical
    verify_absence_claims so a model hiccup never crashes the pipeline.

    Returns (kept_tasks, metrics).
    """
    all_tasks = list(tasks or [])
    selected = [
        (i, t) for i, t in enumerate(all_tasks)
        if not t.get("audit_grounded")
        and any(marker in str(t.get("problem") or "").lower() for marker in _ABSENCE_MARKERS)
    ]
    if not selected:
        return all_tasks, {}

    try:
        from app.core.openai_client import get_async_openai_client, get_completion_params
        from app.services.retry_utils import parse_chat_completion_with_retries
        from app.workflows.draft_analysis.schemas import AbsenceVerification

        body = (draft_content or "")[:40000]
        lines = []
        for idx, (_orig_i, task) in enumerate(selected):
            anchor = str(task.get("anchor_text") or task.get("text_snippet") or "")
            lines.append(
                f"[{idx}]\n"
                f"  critique: {task.get('problem') or ''}\n"
                f"  claimed_missing: {task.get('suggested_action') or ''}\n"
                f"  anchor_text: {anchor}"
            )
        user_content = (
            "Manuscript body (truncated):\n"
            f"{body}\n\n"
            "Items to verify (return one verdict per index):\n"
            + "\n".join(lines)
        )

        response = await parse_chat_completion_with_retries(
            get_async_openai_client(),
            model="gpt-5.2-chat-latest",
            messages=[
                {"role": "system", "content": _LLM_ABSENCE_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            max_completion_tokens=1500,
            response_format=AbsenceVerification,
            **get_completion_params(),
        )
        verification = response.parsed

        verdict_by_idx: dict[int, Any] = {}
        for item in verification.items:
            if 0 <= item.index < len(selected):
                verdict_by_idx[item.index] = item

        kept: list[dict[str, Any]] = []
        addressed_dropped = 0
        partial_downgraded = 0

        selected_by_orig = {orig_i: sel_idx for sel_idx, (orig_i, _t) in enumerate(selected)}

        for orig_i, task in enumerate(all_tasks):
            sel_idx = selected_by_orig.get(orig_i)
            if sel_idx is None:
                kept.append(task)
                continue
            item = verdict_by_idx.get(sel_idx)
            if item is None or item.verdict == "absent":
                kept.append(task)
                continue
            if item.verdict == "addressed":
                addressed_dropped += 1
                continue  # DROP
            # partial — downgrade one severity; keep `problem` CLEAN and record the
            # evidence in separate fields so verifier text never leaks into the
            # user-facing problem string (HOTFIX 1).
            updated = dict(task)
            sev = (updated.get("severity") or "major").lower()
            updated["severity"] = _DOWNGRADE.get(sev, sev)
            updated["priority"] = _PRIORITY_FROM_SEVERITY.get(updated["severity"], updated.get("priority", "medium"))
            evidence = (item.evidence or "").strip()
            updated["verification_status"] = "partially_addressed"
            updated["verification_note"] = evidence
            updated["grounding_flag"] = "llm_partial"
            kept.append(updated)
            partial_downgraded += 1

        return kept, {
            "llm_addressed_dropped": addressed_dropped,
            "llm_partial_downgraded": partial_downgraded,
        }
    except Exception:
        # Never crash the pipeline on an LLM failure — fall back to sync lexical.
        return verify_absence_claims(all_tasks, draft_content)


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


# ---------------------------------------------------------------------------
# Anchor repair — deterministic, no LLM
# ---------------------------------------------------------------------------

def _norm_ws(text: str) -> str:
    """Collapse all whitespace (including non-breaking space / soft-hyphen) to single space."""
    return re.sub(r"\s+", " ", re.sub(r"[­ ]", " ", text)).strip()


def _lcs_in_raw(anchor: str, raw_text: str, min_len: int = 40) -> str | None:
    """Return the longest exact raw substring that also appears in anchor (>=min_len chars)."""
    best = ""
    la, lr = len(anchor), len(raw_text)
    # Build suffix-array-style LCS via SequenceMatcher (O(n*m) but anchor is <=200 chars)
    sm = SequenceMatcher(None, anchor, raw_text, autojunk=False)
    for block in sm.get_matching_blocks():
        n = block.size
        if n >= min_len and n > len(best):
            best = raw_text[block.b : block.b + n]
    return best if best else None


def repair_anchor(task: dict[str, Any], raw_text: str) -> dict[str, Any]:
    """Deterministically repair a non-verbatim anchor without calling any LLM.

    Strategy (in order):
    1. Already verbatim — return unchanged.
    2. Whitespace/glyph-normalized match — locate exact span in raw_text and replace.
    3. Longest-common-substring >=40 chars in raw_text — replace with that span.
    4. Irreparable — set anchor_type="global" AND null the generative anchor_text
       (section name is an acceptable non-quote locator; never the critique prose) so
       the task is exempt from coverage AND carries no fake "quote" (anchor honesty).
    """
    anchor = (task.get("anchor_text") or task.get("text_snippet") or "").strip()
    if not anchor or not raw_text:
        return task

    # 1. Already verbatim
    if anchor in raw_text:
        return task

    task = dict(task)  # shallow copy — do not mutate caller's dict

    # 2. Normalized match
    norm_anchor = _norm_ws(anchor)
    norm_raw = _norm_ws(raw_text)
    idx = norm_raw.find(norm_anchor)
    if idx != -1:
        # Map normalized index back to raw.  Walk raw_text tracking normalized position.
        pos = 0  # normalized position
        raw_start = 0
        i = 0
        while i < len(raw_text) and pos < idx:
            ch = raw_text[i]
            norm_ch = re.sub(r"\s+", " ", re.sub(r"[­ ]", " ", ch))
            # whitespace runs collapse to one space in normalized; track properly
            if re.match(r"\s", ch) or ch in ("­", " "):
                # skip additional whitespace that was collapsed
                while i + 1 < len(raw_text) and re.match(r"[\s­ ]", raw_text[i + 1]):
                    i += 1
                pos += 1
            else:
                pos += len(norm_ch)
            i += 1
            raw_start = i

        # Extract span of same normalized length
        norm_len = len(norm_anchor)
        pos2 = 0
        raw_end = raw_start
        j = raw_start
        while j < len(raw_text) and pos2 < norm_len:
            ch = raw_text[j]
            if re.match(r"[\s­ ]", ch):
                while j + 1 < len(raw_text) and re.match(r"[\s­ ]", raw_text[j + 1]):
                    j += 1
                pos2 += 1
            else:
                pos2 += 1
            j += 1
            raw_end = j

        candidate = raw_text[raw_start:raw_end].strip()
        if candidate and _norm_ws(candidate) == norm_anchor:
            task["anchor_text"] = candidate
            return task
        # Fallback: use a simpler scan via re.search on normalized
        m = re.search(re.escape(norm_anchor), norm_raw)
        if m:
            # Count raw chars up to norm match start
            raw_substr = _extract_raw_span(raw_text, norm_raw, m.start(), len(norm_anchor))
            if raw_substr:
                task["anchor_text"] = raw_substr
                return task

    # 3. Longest common substring >= 40 chars
    lcs = _lcs_in_raw(anchor, raw_text, min_len=40)
    if lcs:
        task["anchor_text"] = lcs
        return task

    # 4. Irreparable — global scope, no fake quote. Keep section as a non-quote locator
    # if present; otherwise null. NEVER leave the generative critique text in anchor_text.
    task["anchor_type"] = "global"
    task["anchor_text"] = task.get("section") or None
    if not _is_verbatim_substring(str(task.get("text_snippet") or ""), raw_text):
        task["text_snippet"] = None
    return task


def _extract_raw_span(raw_text: str, norm_text: str, norm_start: int, norm_length: int) -> str | None:
    """Given a match position in the normalized string, extract the corresponding raw span."""
    # Build a position map: norm_pos -> raw_pos
    norm_pos = 0
    raw_pos = 0
    start_raw = None
    i = 0
    while i < len(raw_text):
        if norm_pos == norm_start and start_raw is None:
            start_raw = i
        if norm_pos >= norm_start + norm_length:
            return raw_text[start_raw:i].strip() if start_raw is not None else None
        ch = raw_text[i]
        if re.match(r"[\s­ ]", ch):
            # consume all contiguous whitespace as one norm space
            while i + 1 < len(raw_text) and re.match(r"[\s­ ]", raw_text[i + 1]):
                i += 1
            norm_pos += 1
        else:
            norm_pos += 1
        i += 1
    if start_raw is not None:
        return raw_text[start_raw:].strip()
    return None


def _is_verbatim_substring(anchor: str, raw_text: str) -> bool:
    """True iff anchor is an exact substring of raw_text (whitespace-normalized)."""
    anchor = (anchor or "").strip()
    if not anchor or not raw_text:
        return False
    if anchor in raw_text:
        return True
    return _norm_ws(anchor) in _norm_ws(raw_text)


_LLM_ANCHOR_REPAIR_SYSTEM_PROMPT = (
    "You map each critique to the EXACT verbatim sentence or span it refers to in the "
    "manuscript. For each item, return the verbatim_span COPIED CHARACTER-FOR-CHARACTER "
    "from the provided manuscript text (it MUST be a literal substring of that text). If "
    "the critique is a whole-document point with no single locatable sentence, return the "
    "literal string 'GLOBAL'. Never paraphrase; never invent text not present verbatim."
)


async def llm_repair_anchors(
    tasks: list[dict[str, Any]],
    draft_content: str,
) -> list[dict[str, Any]]:
    """Repair non-verbatim (paraphrase) anchors into real manuscript quotes via one
    batched gpt-5.2 call, with an honest fallthrough (verbatim-anchor real fix, 4a).

    Per task:
      1. Try the deterministic `repair_anchor` first; if it produces a verbatim anchor,
         keep it and skip the LLM for that task.
      2. For the rest, ask the LLM (ONE batched call) for the exact verbatim span.
         - returned span IS a substring → set anchor_text to the exact raw span,
           anchor_type="local" (a HIT).
         - returned "GLOBAL" → anchor_type="global" (LLM-confirmed document scope) AND
           null the generative anchor_text (keep section as a non-quote locator if any).
         - returned a non-substring (hallucination) → anchor_type="global" AND null the
           generative anchor_text — never leave a fake "quote" in the payload (honesty).

    Anchor honesty invariant: on return, every task either has an anchor_text that is a
    verbatim substring of the manuscript, OR anchor_text is None (or a bare section name).
    No task carries generative critique prose in anchor_text/text_snippet.

    On ANY failure, leaves tasks unchanged.
    """
    all_tasks = list(tasks or [])
    if not all_tasks or not (draft_content or "").strip():
        return all_tasks

    # 1. Deterministic repair first; collect tasks still non-verbatim.
    repaired: list[dict[str, Any]] = []
    still_broken: list[tuple[int, dict[str, Any]]] = []
    for i, task in enumerate(all_tasks):
        anchor = (task.get("anchor_text") or task.get("text_snippet") or "").strip()
        if _is_verbatim_substring(anchor, draft_content):
            repaired.append(task)
            continue
        det = repair_anchor(task, draft_content)
        det_anchor = (det.get("anchor_text") or det.get("text_snippet") or "").strip()
        if det.get("anchor_type") != "global" and _is_verbatim_substring(det_anchor, draft_content):
            repaired.append(det)
            continue
        # repair_anchor may have set anchor_type="global" deterministically; we will let
        # the LLM decide instead, so reset to the original task for the LLM pass.
        repaired.append(task)
        still_broken.append((i, task))

    if not still_broken:
        return repaired

    try:
        from app.core.openai_client import get_async_openai_client, get_completion_params
        from app.services.retry_utils import parse_chat_completion_with_retries
        from app.workflows.draft_analysis.schemas import AnchorRepair

        body = (draft_content or "")[:40000]
        lines = []
        for sel_idx, (_orig_i, task) in enumerate(still_broken):
            anchor = str(task.get("anchor_text") or task.get("text_snippet") or "")
            lines.append(
                f"[{sel_idx}]\n"
                f"  critique: {task.get('problem') or ''}\n"
                f"  current_anchor (paraphrase): {anchor}"
            )
        user_content = (
            "Manuscript body (truncated):\n"
            f"{body}\n\n"
            "Items (return one verbatim_span per index — an exact substring of the body "
            "above, or 'GLOBAL'):\n"
            + "\n".join(lines)
        )

        response = await parse_chat_completion_with_retries(
            get_async_openai_client(),
            model="gpt-5.2-chat-latest",
            messages=[
                {"role": "system", "content": _LLM_ANCHOR_REPAIR_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            max_completion_tokens=2000,
            response_format=AnchorRepair,
            **get_completion_params(),
        )
        repair = response.parsed

        span_by_sel: dict[int, str] = {}
        for item in repair.items:
            if 0 <= item.index < len(still_broken):
                span_by_sel[item.index] = item.verbatim_span or ""

        sel_by_orig = {orig_i: sel_idx for sel_idx, (orig_i, _t) in enumerate(still_broken)}

        out: list[dict[str, Any]] = []
        for orig_i, task in enumerate(repaired):
            sel_idx = sel_by_orig.get(orig_i)
            if sel_idx is None:
                out.append(task)
                continue
            span = (span_by_sel.get(sel_idx) or "").strip()
            updated = dict(task)
            if span and span != "GLOBAL" and _is_verbatim_substring(span, draft_content):
                # Locate the exact raw span (preserve original whitespace) when possible.
                exact = span if span in draft_content else None
                if exact is None:
                    m = re.search(re.escape(_norm_ws(span)), _norm_ws(draft_content))
                    if m:
                        exact = _extract_raw_span(
                            draft_content, _norm_ws(draft_content), m.start(), len(_norm_ws(span))
                        )
                updated["anchor_text"] = exact or span
                updated["anchor_type"] = "local"
            else:
                # GLOBAL or hallucinated/empty → no locatable verbatim quote. Mark global
                # and NULL the generative anchor_text so no fake "quote" reaches the user
                # (keep a bare section name as a non-quote locator if present).
                updated["anchor_type"] = "global"
                updated["anchor_text"] = updated.get("section") or None
                if not _is_verbatim_substring(str(updated.get("text_snippet") or ""), draft_content):
                    updated["text_snippet"] = None
            out.append(updated)
        return out
    except Exception:
        # Never crash the pipeline — leave tasks unchanged.
        return all_tasks


def _candidate_source_text(source: dict[str, Any]) -> str:
    """Topic text for a suggested source/paper: title + abstract/content."""
    return " ".join(
        str(source.get(key) or "")
        for key in ("title", "document_title", "abstract", "content")
    ).strip()


def filter_sources_by_manuscript_relevance(
    tasks: list[dict[str, Any]],
    gaps: list[dict[str, Any]],
    draft_content: str,
    *,
    threshold: float | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Drop off-domain suggested sources by embedding relevance to THIS manuscript.

    Belt-and-suspenders layer on top of the existing topic-term/domain gates. The
    manuscript defines its own domain via ``draft_content[:3000]`` (title+abstract+intro
    region). Each candidate source attached to a task's ``suggested_sources`` or a gap's
    ``suggested_papers`` is embedded once (one batched call) and dropped if its cosine vs
    the manuscript reference falls below ``threshold``.

    No keyword/MeSH lists — relevance is purely vs the manuscript embedding.

    No-op fallback (inputs returned unchanged) when embeddings are unavailable
    (no key / under pytest) or any error occurs. Never crashes the pipeline.
    """
    import os

    if threshold is None:
        try:
            threshold = float(os.environ.get("DRAFT_SOURCE_RELEVANCE_MIN", "0.42"))
        except (TypeError, ValueError):
            threshold = 0.42

    tasks = tasks or []
    gaps = gaps or []
    metrics = {
        "sources_checked": 0,
        "sources_dropped_offdomain": 0,
        "relevance_threshold": threshold,
    }

    manuscript_ref = (draft_content or "")[:3000].strip()
    if not manuscript_ref:
        return tasks, gaps, metrics
    if not os.environ.get("OPENAI_API_KEY") or os.environ.get("PYTEST_CURRENT_TEST"):
        return tasks, gaps, metrics

    # Collect every unique candidate source text across tasks + gaps.
    unique_texts: list[str] = []
    seen: set[str] = set()

    def _register(sources: list[dict[str, Any]] | None) -> None:
        for src in sources or []:
            text = _candidate_source_text(src)
            if text and text not in seen:
                seen.add(text)
                unique_texts.append(text)

    for task in tasks:
        _register(task.get("suggested_sources"))
    for gap in gaps:
        _register(gap.get("suggested_papers"))

    if not unique_texts:
        return tasks, gaps, metrics

    try:
        from app.services.rag_ingest import embed_chunks  # reuse project embedder
        results = embed_chunks([manuscript_ref] + unique_texts, model="text-embedding-3-small")
        if not results or len(results) < 2:
            return tasks, gaps, metrics
        vectors = [r.embedding for r in results]
        ref_vec = vectors[0]
        scores = {
            text: _cosine(ref_vec, vec)
            for text, vec in zip(unique_texts, vectors[1:])
        }
    except Exception:
        # Embed failure → no-op fallback, inputs unchanged.
        return tasks, gaps, metrics

    def _keep(src: dict[str, Any]) -> bool:
        text = _candidate_source_text(src)
        if not text or text not in scores:
            return True  # unscored (empty) → keep, don't drop blindly
        metrics["sources_checked"] += 1
        if scores[text] < threshold:
            metrics["sources_dropped_offdomain"] += 1
            return False
        return True

    for task in tasks:
        sources = task.get("suggested_sources")
        if sources:
            task["suggested_sources"] = [s for s in sources if _keep(s)]
    for gap in gaps:
        papers = gap.get("suggested_papers")
        if papers:
            gap["suggested_papers"] = [p for p in papers if _keep(p)]

    return tasks, gaps, metrics

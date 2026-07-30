"""
Draft Analysis Service (LangGraph Version)

Integrates the LangGraph workflow into the existing draft analysis system.
This replaces the old sequential approach with an intelligent, adaptive workflow.
"""

from app.workflows.draft_analysis.graph import run_draft_analysis_workflow
from app.workflows.draft_analysis.revision_tasks import (
    build_revision_tasks,
    calculate_revision_task_readiness_score,
    consolidate_revision_tasks,
    llm_dedupe_tasks,
)
from app.workflows.draft_analysis.citation_rules import apply_existing_citation_gate, has_existing_citation
from app.workflows.draft_analysis.nodes.analysis_quality_judge import judge_analysis_quality
from app.workflows.draft_analysis.domain_routing import ROUTING_DOMAINS
from app.services.progress_publisher import publish_progress
from app.services.draft_analysis_runs import (
    active_run_filter,
    create_analysis_run,
    mark_analysis_run,
    publish_analysis_artifacts,
)
from app.services.draft_task_evidence import reconcile_tasks_against_evidence, repair_anchor
from app.services.draft_evidence_manifest import build_evidence_manifest, manifest_summary, stale_search_task
from app.services.draft_publish_gate import evaluate_publish_gate, FAIL_CLOSED as PUBLISH_GATE_FAIL_CLOSED
from app.core.supabase_client import supabase
from app.core.logging_config import get_logger
from app.core.privacy import safe_exception, strip_manuscript_content_from_structure
import datetime
import asyncio
import re
from difflib import SequenceMatcher

logger = get_logger(__name__)


ANCHOR_DB_FIELDS = ("line_number", "char_start", "char_end", "text_snippet")
VALID_REVIEWER_PERSONAS = {"reviewer_1", "reviewer_2"}
MIN_CITATION_SUGGESTION_SIMILARITY = 0.50
MIN_DISPLAY_SOURCE_SIMILARITY = 0.66

SOURCE_STOPWORDS = {
    "about", "above", "after", "again", "against", "also", "because", "been",
    "being", "between", "cannot", "claim", "claims", "could", "current",
    "draft", "evidence", "found", "from", "have", "into", "library", "literature",
    "missing", "more", "needs", "paper", "papers", "section", "should", "study",
    "studies", "support", "supported", "supporting", "that", "their", "there",
    "these", "this", "those", "through", "using", "with", "without", "would",
    "safety", "therapeutic", "approach", "clinical", "scientific",
    "public", "health", "implementation", "organization", "organizational",
    "sector", "type", "practice",
}

FAIL_CLOSED_SOURCE_ROUTES = {
    "humanities_education",
    "humanities_theory",
    "social_science_qualitative",
    "computer_science_conceptual",
    "public_health_psychology",
    "behavioral_health",
    "law_policy",
    "business_management",
    "environmental_ecology",
    "mechanical_civil_engineering",
    "math_statistics",
    "neuroscience_cognitive_science",
    "education_empirical",
}

METHODOLOGY_GUIDELINE_TERMS = {
    "prisma", "consort", "strobe", "moose", "robins-i", "robins",
    "cochrane handbook", "reporting guideline", "risk of bias tool",
}


def _normalize_reviewer_persona(value: str | None, fallback: str = "reviewer_2") -> str:
    if value in VALID_REVIEWER_PERSONAS:
        return value
    if fallback in VALID_REVIEWER_PERSONAS:
        return fallback
    return "reviewer_2"


def _anchor_fields(item: dict) -> dict:
    """Return anchor fields supported by the current draft_claims/coverage_gaps schema."""
    return {
        key: item.get(key)
        for key in ANCHOR_DB_FIELDS
        if item.get(key) is not None
    }


def _valid_citation_result(citation: dict) -> bool:
    title = str(citation.get("document_title") or citation.get("title") or "").strip()
    content = str(citation.get("content") or "").strip()
    similarity = float(citation.get("similarity") or citation.get("relevance_score") or 0.0)
    if not title or title.lower() in {"unknown", "untitled", "untitled document"}:
        return False
    if similarity < MIN_CITATION_SUGGESTION_SIMILARITY:
        return False
    if not content and not citation.get("doi") and not citation.get("url") and not citation.get("paper_url") and not citation.get("pdf_url"):
        return False
    return True


def _clear_analysis_outputs(draft_id: str) -> None:
    for table_name in (
        "reviewer_panel_outputs",
        "meta_reviews",
        "reviewer_feedback",
        "draft_revision_tasks",
        "draft_claims",
        "coverage_gaps",
        "citation_suggestions",
    ):
        try:
            supabase.table(table_name).delete().eq("draft_id", draft_id).execute()
        except Exception as err:
            logger.warning(
                "[LangGraph Draft Analysis] Failed to clear %s for contaminated run: %s",
                table_name,
                safe_exception(err),
            )

def _suggested_source_payload(citation: dict, display: str | None = None) -> dict:
    return {
        "document_id": citation.get("document_id"),
        "document_title": citation.get("document_title") or citation.get("title"),
        "title": citation.get("title") or citation.get("document_title"),
        "display": display or citation.get("display") or citation.get("document_title") or citation.get("title"),
        "content": citation.get("content", ""),
        "similarity": citation.get("similarity") or citation.get("relevance_score") or 0.0,
        "source": citation.get("source", "library"),
        "doi": citation.get("doi"),
        "url": citation.get("url") or citation.get("paper_url") or citation.get("pdf_url"),
    }


def _source_terms(text: str) -> set[str]:
    terms: list[str] = []
    for token in re.findall(r"[A-Za-z][A-Za-z0-9-]{2,}", (text or "").lower()):
        token = token.strip("-")
        if token in SOURCE_STOPWORDS or len(token) < 3:
            continue
        if token not in terms:
            terms.append(token)
    return set(terms)


def _source_text(source: dict) -> str:
    return " ".join(
        str(source.get(key) or "")
        for key in (
            "title",
            "document_title",
            "display",
            "content",
            "abstract",
            "journal_name",
            "source",
        )
    )


def _route_keys(manuscript_profile: dict | None) -> list[str]:
    profile = manuscript_profile or {}
    keys = [
        str(profile.get("routing_domain") or "").lower(),
        *[str(item).lower() for item in (profile.get("secondary_domains") or [])],
        *[str(item).lower() for item in (profile.get("domain_tags") or [])],
    ]
    normalized: list[str] = []
    for key in keys:
        if not key:
            continue
        if "material" in key or "battery" in key:
            key = "chemistry_materials"
        elif key in {"biomedical", "medicine", "biology", "clinical_ai", "crispr"}:
            pass
        elif key in {"humanities_education", "humanities_theory", "social_science_qualitative", "computer_science_conceptual", "public_health_psychology", "behavioral_health"}:
            pass
        if key not in normalized:
            normalized.append(key)
    return normalized or ["generic_academic"]


def _judge_flag_terms(analysis_quality_judge: dict | None) -> set[str]:
    judge = analysis_quality_judge or {}
    flagged = " ".join(
        str(item)
        for item in [
            *(judge.get("wrong_domain_flags") or []),
            *(judge.get("source_contamination_flags") or []),
        ]
    )
    return _source_terms(flagged)


def _profile_source_terms(manuscript_profile: dict | None) -> set[str]:
    profile = manuscript_profile or {}
    return _source_terms(" ".join([
        str(profile.get("routing_domain") or ""),
        " ".join(str(item) for item in (profile.get("secondary_domains") or [])),
        " ".join(str(item) for item in (profile.get("domain_tags") or [])),
        " ".join(str(item) for item in (profile.get("review_lenses") or [])),
        " ".join(str(item) for item in (profile.get("high_risk_checks") or [])),
    ]))


def _is_methodology_guideline_source(source_text: str) -> bool:
    lower = (source_text or "").lower()
    return any(term in lower for term in METHODOLOGY_GUIDELINE_TERMS)


def _is_methodology_task(task: dict) -> bool:
    text = " ".join(
        str(task.get(key) or "")
        for key in ("task_type", "problem", "suggested_action", "section", "dedupe_category", "issue_family")
    ).lower()
    return bool(re.search(
        r"\b(methodology|methods?|reporting|protocol|registration|prisma|search strateg|risk of bias|meta-analysis|systematic review|guideline)\b",
        text,
        flags=re.IGNORECASE,
    ))


def _source_rejection_reason(
    *,
    task: dict,
    source: dict,
    manuscript_profile: dict | None,
    analysis_quality_judge: dict | None,
) -> str | None:
    source_text = _source_text(source)
    source_terms = _source_terms(source_text)
    task_terms = _source_terms(
        " ".join(
            str(task.get(key) or "")
            for key in ("problem", "suggested_action", "anchor_text", "text_snippet", "section")
        )
    )
    similarity = float(source.get("similarity") or source.get("relevance_score") or 0.0)
    if similarity and similarity < MIN_DISPLAY_SOURCE_SIMILARITY:
        return "low_similarity"

    flagged_terms = _judge_flag_terms(analysis_quality_judge)
    flagged_overlap = source_terms & flagged_terms
    if len(flagged_overlap) >= 2:
        return "judge_wrong_domain_flag"

    route_keys = _route_keys(manuscript_profile)
    profile_terms = _profile_source_terms(manuscript_profile)
    profile_overlap = source_terms & profile_terms
    task_overlap = source_terms & task_terms
    if _is_methodology_task(task) and _is_methodology_guideline_source(source_text):
        return None

    # Distinctive-topic gate: a single broad shared term ("materials" from a materials
    # profile) is NOT enough to keep a source on-topic — that is exactly how a "phenol
    # wastewater treatment" review survived for a sodium-ion battery manuscript. Require
    # the source to share the manuscript's DISTINCTIVE subject vocabulary (topic_terms
    # minus broad domain tags), reusing the same gate the retrieval layer applies.
    try:
        from app.services.draft_external_source_discovery import _passes_domain_gate
        query_text = " ".join(
            str(task.get(key) or "")
            for key in ("problem", "suggested_action", "anchor_text", "text_snippet", "section")
        )
        if manuscript_profile and not _passes_domain_gate(query_text, source_text, similarity, manuscript_profile):
            return "off_topic_distinctive"
    except Exception:
        pass

    if set(route_keys) & FAIL_CLOSED_SOURCE_ROUTES:
        if not profile_overlap:
            return "missing_profile_overlap"
        if len(task_overlap) < 2 and similarity < 0.82:
            return "low_task_overlap"

    if len(task_overlap) < 2 and not profile_overlap:
        return "low_task_overlap"
    return None


def sanitize_revision_task_sources(
    tasks: list[dict],
    *,
    manuscript_profile: dict | None,
    analysis_quality_judge: dict | None,
) -> tuple[list[dict], dict]:
    """Return display-safe tasks and internal source-pruning metadata."""
    sanitized: list[dict] = []
    pruned_sources: list[dict] = []
    checked = kept = 0
    reason_counts: dict[str, int] = {}

    for task in tasks or []:
        task_copy = dict(task)
        safe_sources: list[dict] = []
        for source in task_copy.get("suggested_sources") or []:
            checked += 1
            if not isinstance(source, dict):
                reason = "malformed_source"
            else:
                reason = _source_rejection_reason(
                    task=task_copy,
                    source=source,
                    manuscript_profile=manuscript_profile,
                    analysis_quality_judge=analysis_quality_judge,
                )
            if reason:
                reason_counts[reason] = reason_counts.get(reason, 0) + 1
                pruned_sources.append({
                    "task_id": task_copy.get("id"),
                    "task_type": task_copy.get("task_type"),
                    "reason": reason,
                    "title": source.get("title") or source.get("document_title") if isinstance(source, dict) else str(source)[:180],
                    "source": source.get("source") if isinstance(source, dict) else None,
                    "similarity": source.get("similarity") or source.get("relevance_score") if isinstance(source, dict) else None,
                    "doi": source.get("doi") if isinstance(source, dict) else None,
                })
                continue
            safe_sources.append(source)
            kept += 1
        task_copy["suggested_sources"] = safe_sources
        if not safe_sources and task_copy.get("source_search_status") == "found":
            task_copy["source_search_status"] = "pruned_all"
        sanitized.append(task_copy)

    metrics = {
        "sources_checked": checked,
        "sources_kept": kept,
        "sources_pruned": len(pruned_sources),
        "pruned_by_reason": reason_counts,
    }
    return sanitized, {
        "pruned_sources": pruned_sources,
        "source_safety_metrics": metrics,
    }


def _merge_source_safety(first: dict, second: dict) -> dict:
    """Combine two sanitize passes' source-safety payloads (pruned lists + counts)."""
    first = first or {}
    second = second or {}
    m1 = first.get("source_safety_metrics") or {}
    m2 = second.get("source_safety_metrics") or {}
    reasons: dict[str, int] = dict(m1.get("pruned_by_reason") or {})
    for reason, count in (m2.get("pruned_by_reason") or {}).items():
        reasons[reason] = reasons.get(reason, 0) + count
    return {
        "pruned_sources": (first.get("pruned_sources") or []) + (second.get("pruned_sources") or []),
        "source_safety_metrics": {
            "sources_checked": (m1.get("sources_checked") or 0) + (m2.get("sources_checked") or 0),
            "sources_kept": m2.get("sources_kept", m1.get("sources_kept", 0)),
            "sources_pruned": (m1.get("sources_pruned") or 0) + (m2.get("sources_pruned") or 0),
            "pruned_by_reason": reasons,
        },
    }


def suppress_unreliable_task_artifacts(task_rows: list[dict]) -> tuple[list[dict], dict]:
    """When the publish gate marks a run unpublishable (parse/anchor failure), don't ship
    the parts most likely to be wrong: drop durable tasks
    that can't be located in the manuscript (``page_number is None`` — they'd break UI
    highlighting and are the least trustworthy) and clear ``suggested_sources`` from the
    rest (sources are the contaminated surface). The reviewer panel + meta-review +
    claims carry the scholarly value and are kept by the caller.

    Returns (kept_rows, summary).
    """
    kept = [row for row in (task_rows or []) if row.get("page_number") is not None]
    for row in kept:
        row["suggested_sources"] = []
    return kept, {
        "dropped_unanchored_tasks": len(task_rows or []) - len(kept),
        "sources_cleared": True,
    }


def _normalize_page_search_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\u00ad", "")).lower().strip()


def _candidate_needles(text: str) -> list[str]:
    normalized = _normalize_page_search_text(text)
    if len(normalized) < 20:
        return []
    candidates = [normalized[:180], normalized[:120], normalized[:80]]
    words = normalized.split()
    if len(words) > 20:
        candidates.append(" ".join(words[8:28]))
        candidates.append(" ".join(words[len(words) // 2: len(words) // 2 + 20]))
    return [candidate for candidate in dict.fromkeys(candidates) if len(candidate) >= 20]


def _page_block_texts(page) -> list[str]:
    """Return layout-block text variants for two-column PDF anchor search."""
    blocks = []
    for block in page.get_text("blocks") or []:
        if len(block) < 5:
            continue
        x0, y0, x1, _y1, text = block[:5]
        normalized = _normalize_page_search_text(text)
        if normalized:
            blocks.append((float(x0), float(y0), float(x1), normalized))
    if not blocks:
        return []

    page_width = max((x1 for _x0, _y0, x1, _text in blocks), default=0.0)
    midpoint = page_width / 2 if page_width else 0.0
    reading_order = [text for _x0, _y0, _x1, text in sorted(blocks, key=lambda item: (item[1], item[0]))]
    column_order = [
        text
        for _x0, _y0, _x1, text in sorted(
            blocks,
            key=lambda item: (0 if midpoint and item[0] < midpoint else 1, item[1], item[0]),
        )
    ]
    return [
        "\n\n".join(reading_order),
        "\n\n".join(column_order),
        *reading_order,
    ]


_ANCHOR_STOPWORDS = {
    "the", "and", "for", "that", "this", "with", "from", "are", "was", "were", "has",
    "have", "had", "not", "but", "their", "there", "which", "while", "such", "into",
    "than", "then", "they", "these", "those", "been", "also", "more", "most", "some",
    "study", "studies", "paper", "manuscript", "review", "authors", "results", "data",
}


def _anchor_content_tokens(text: str) -> set[str]:
    """Content-word token set for fuzzy anchor matching (len>=4, minus stopwords)."""
    return {
        tok
        for tok in re.findall(r"[a-z0-9][a-z0-9-]{3,}", (text or "").lower())
        if tok not in _ANCHOR_STOPWORDS
    }


def _map_revision_task_pages(draft_id: str, tasks: list[dict]) -> list[dict]:
    """Best-effort page-number enrichment using PyMuPDF page text search."""
    if not tasks:
        return tasks
    try:
        draft_res = supabase.table("drafts").select("file_url, file_type").eq("id", draft_id).limit(1).execute()
        if not draft_res.data:
            return tasks
        draft = draft_res.data[0]
        file_url = draft.get("file_url") or ""
        if (draft.get("file_type") or "").lower() not in {"pdf", "application/pdf"} and not file_url.lower().endswith(".pdf?") and ".pdf" not in file_url.lower():
            return tasks
        if "/drafts/" not in file_url:
            return tasks
        storage_path = file_url.split("/drafts/", 1)[1]
        file_bytes = supabase.storage.from_("drafts").download(storage_path)
        if not file_bytes:
            return tasks

        import fitz

        doc = fitz.open(stream=file_bytes, filetype="pdf")
        page_texts = [_normalize_page_search_text(page.get_text("text")) for page in doc]
        page_block_texts = [_page_block_texts(page) for page in doc]
        page_paragraphs = [
            [_normalize_page_search_text(p) for p in re.split(r"\n\s*\n", page.get_text("text")) if p.strip()]
            for page in doc
        ]
        for task in tasks:
            if task.get("page_number"):
                continue
            sources = [
                task.get("anchor_text", ""),
                task.get("text_snippet", ""),
                task.get("problem", ""),
            ]
            for source in sources:
                matched = False
                for needle in _candidate_needles(source):
                    for idx, page_text in enumerate(page_texts):
                        if needle in page_text:
                            task["page_number"] = idx + 1
                            paragraphs = page_paragraphs[idx]
                            for pidx, paragraph in enumerate(paragraphs):
                                if needle[:60] in paragraph:
                                    task["paragraph_index"] = pidx + 1
                                    break
                            matched = True
                            break
                        for block_idx, block_text in enumerate(page_block_texts[idx]):
                            if needle in block_text:
                                task["page_number"] = idx + 1
                                if "\n\n" not in block_text:
                                    task["paragraph_index"] = max(1, block_idx - 1)
                                matched = True
                                break
                        if matched:
                            break
                    if matched:
                        break
                if matched:
                    break
            if not task.get("page_number"):
                logger.info(
                    "[LangGraph Draft Analysis] Page anchor miss task_id=%s type=%s section=%s anchor_len=%s",
                    task.get("id"),
                    task.get("task_type"),
                    task.get("section"),
                    len(task.get("anchor_text") or task.get("text_snippet") or ""),
                )
    except Exception as exc:
        logger.warning("[LangGraph Draft Analysis] Page anchor mapping skipped: %s", safe_exception(exc))
    return tasks


def _apply_parse_artifact_anchors(draft_id: str, tasks: list[dict], artifact: dict | None = None) -> list[dict]:
    if not tasks:
        return tasks
    try:
        from app.services.draft_parse_artifacts import load_parse_artifact, normalize_anchor_text

        artifact = artifact or load_parse_artifact(draft_id)
        anchor_map = (artifact or {}).get("anchor_map") or []
        if not anchor_map:
            return tasks

        normalized_anchors = []
        section_page_map: dict[str, dict] = {}
        for anchor in anchor_map:
            text = normalize_anchor_text(anchor.get("text_snippet") or "")
            # Section→page map: first page seen per section, for a section-level
            # fallback anchor when no paragraph-level quote matches.
            sect = (anchor.get("section_title") or "").strip().lower()
            page = anchor.get("page_number") or (anchor.get("coordinates") or {}).get("page")
            if sect and page and sect not in section_page_map:
                section_page_map[sect] = {"page": page, "section_title": anchor.get("section_title")}
            if len(text) < 30:
                continue
            normalized_anchors.append((anchor, text, text.lower(), _anchor_content_tokens(text)))

        for task in tasks:
            # Match the task's QUOTE fields against the evidence store — NOT the
            # `problem` critique text (it describes the issue, it isn't manuscript
            # text, so it never matches a paragraph and only adds noise).
            candidates = [
                normalize_anchor_text(task.get("anchor_text") or ""),
                normalize_anchor_text(task.get("text_snippet") or ""),
            ]
            candidates = [candidate for candidate in candidates if len(candidate) >= 20]
            best_anchor = None
            best_score = 0.0
            best_status = "unresolved"
            for candidate in candidates:
                candidate_lower = candidate.lower()
                cand_tokens = _anchor_content_tokens(candidate)
                for anchor, text, text_lower, anchor_tokens in normalized_anchors:
                    # 1) Verbatim substring (either direction) → exact.
                    if candidate_lower in text_lower or text_lower[:220] in candidate_lower:
                        score, status = 0.98, "exact"
                    else:
                        # 2) Token containment: fraction of the candidate's content
                        # words present in this paragraph. Robust to length and
                        # paraphrase (a one-sentence quote inside a 700-char snippet,
                        # or a lightly reworded anchor, still scores high).
                        containment = (
                            len(cand_tokens & anchor_tokens) / len(cand_tokens)
                            if len(cand_tokens) >= 4 else 0.0
                        )
                        seq = SequenceMatcher(None, candidate_lower[:500], text_lower[:500]).ratio()
                        score = max(containment, seq)
                        status = "fuzzy"
                    if score > best_score:
                        best_score = score
                        best_anchor = anchor
                        best_status = "exact" if score >= 0.96 else "fuzzy"

            if best_anchor and best_score >= 0.55:
                task["anchor_status"] = best_status
                task["anchor_source"] = "parse_artifact"
                task["anchor_confidence"] = round(best_score, 3)
                task["anchor_text"] = best_anchor.get("text_snippet") or task.get("anchor_text")
                task["text_snippet"] = best_anchor.get("text_snippet") or task.get("text_snippet")
                task["section"] = task.get("section") or best_anchor.get("section_title")
                coords = best_anchor.get("coordinates") or {}
                task["paragraph_index"] = task.get("paragraph_index") or best_anchor.get("paragraph_index")
                task["page_number"] = task.get("page_number") or best_anchor.get("page_number") or coords.get("page")
                if best_anchor.get("coordinates"):
                    task["pdf_coordinates"] = task.get("pdf_coordinates") or best_anchor.get("coordinates")
                task["match_confidence"] = max(float(task.get("match_confidence") or 0.0), best_score)
            else:
                # No paragraph-level match. Fall back to a section-level page when
                # the task is scoped to a section the parser located — the user
                # still lands on the right page even without a paragraph anchor.
                task_section = (task.get("section") or "").strip().lower()
                section_hit = section_page_map.get(task_section)
                if not section_hit and task_section:
                    section_hit = next(
                        (v for k, v in section_page_map.items() if k and (k in task_section or task_section in k)),
                        None,
                    )
                if section_hit and not task.get("page_number"):
                    task["page_number"] = section_hit["page"]
                    task["section"] = task.get("section") or section_hit["section_title"]
                    task["anchor_status"] = "section_only"
                    task["anchor_source"] = "parse_artifact_section"
                    task["anchor_confidence"] = task.get("anchor_confidence") or 0.3
                else:
                    task["anchor_status"] = task.get("anchor_status") or "section_only"
                    task["anchor_source"] = task.get("anchor_source") or "task_generated"
                    task["anchor_confidence"] = task.get("anchor_confidence") or 0.0
    except Exception as exc:
        logger.warning("[LangGraph Draft Analysis] Parse artifact anchor validation skipped: %s", safe_exception(exc))
    return tasks


def _is_verbatim_anchor(anchor_text: str, draft_content: str) -> bool:
    """True iff anchor_text is a substantial (>=4 words or >=30 chars) verbatim
    substring of the draft. Bare section headers ("Methods") are not useful anchors
    and do not count as verbatim coverage."""
    anchor = (anchor_text or "").strip()
    if not draft_content:
        return False
    if len(anchor.split()) < 3 and len(anchor) < 24:
        return False
    if anchor in draft_content:
        return True
    norm_anchor = re.sub(r"\s+", " ", anchor)
    norm_draft = re.sub(r"\s+", " ", draft_content)
    return norm_anchor in norm_draft


def _classify_task_anchors(tasks: list[dict], draft_content: str) -> None:
    """Tag each task with anchor_verbatim + anchor_type (local vs global).

    A task is GLOBAL when something upstream (llm_repair_anchors, or the deterministic
    repair_anchor fallback) explicitly set anchor_type="global" because the LLM confirmed
    it is a whole-document point with no locatable quote — OR when anchor_text is now None
    (anchor honesty: a missing/unlocatable critique now carries NO fake quote, so it has
    no verbatim locus to score). A non-verbatim LOCAL anchor (real quote present) is still
    an honest MISS, not an exemption."""
    for task in tasks or []:
        anchor = task.get("anchor_text") or task.get("text_snippet") or ""
        verbatim = _is_verbatim_anchor(anchor, draft_content) or (
            task.get("anchor_source") == "parse_artifact"
            and task.get("anchor_status") in {"exact", "fuzzy"}
        )
        task["anchor_verbatim"] = bool(verbatim)
        # A null anchor_text means there is NO locus to verify — it is global (no fake
        # quote), exempt from coverage. Otherwise keep whatever repair set (default local).
        if task.get("anchor_text") is None:
            task["anchor_type"] = "global"
        else:
            task.setdefault("anchor_type", "local")


def _revision_quality_metrics(tasks: list[dict], draft_content: str = "") -> dict:
    if draft_content:
        _classify_task_anchors(tasks, draft_content)
    total = len(tasks or [])
    if not total:
        return {
            "total_tasks": 0,
            "merged_duplicate_tasks": 0,
            "tasks_with_duplicate_merges": 0,
            "anchor_coverage": 0.0,
            "page_anchor_coverage": 0.0,
            "verbatim_anchor_coverage": 0.0,
            "citation_source_coverage": 1.0,
            "citation_tasks": 0,
            "citation_tasks_with_sources": 0,
        }
    merged_duplicate_tasks = sum(int(task.get("duplicate_count") or 0) for task in tasks)
    tasks_with_duplicate_merges = sum(1 for task in tasks if int(task.get("duplicate_count") or 0) > 0)
    anchored = sum(1 for task in tasks if task.get("anchor_text") or task.get("text_snippet") or task.get("section"))
    page_anchored = sum(1 for task in tasks if task.get("page_number") or task.get("paragraph_index") or task.get("pdf_coordinates") or task.get("char_start") is not None)
    # Honest verbatim coverage (anchor honesty):
    #   numerator   = tasks whose non-null anchor_text is an exact substring (or parse-
    #                 artifact-backed) of the manuscript.
    #   denominator = tasks that HAVE a non-null anchor_text.
    # Tasks with a null anchor (global / unlocatable — no fake quote) are excluded from
    # BOTH; they carry no verbatim locus to verify. This makes the metric honest AND the
    # payload honest (no generative "quotes" anywhere).
    anchored_tasks = [t for t in tasks if t.get("anchor_text") is not None]
    verbatim_anchored = sum(
        1 for task in anchored_tasks
        if task.get("anchor_verbatim")
        or (task.get("anchor_source") == "parse_artifact" and task.get("anchor_status") in {"exact", "fuzzy"})
    )
    verbatim_denominator = len(anchored_tasks)
    global_tasks_count = sum(1 for t in tasks if t.get("anchor_text") is None)
    citation_tasks = [
        task for task in tasks
        if task.get("task_type") == "citation"
        or task.get("source_type") == "claim"
        or "citation" in str(task.get("problem", "")).lower()
        or "source" in str(task.get("suggested_action", "")).lower()
    ]
    citation_tasks_with_sources = sum(1 for task in citation_tasks if task.get("suggested_sources"))
    return {
        "total_tasks": total,
        "merged_duplicate_tasks": merged_duplicate_tasks,
        "tasks_with_duplicate_merges": tasks_with_duplicate_merges,
        "anchor_coverage": round(anchored / total, 3),
        "page_anchor_coverage": round(page_anchored / total, 3),
        "verbatim_anchor_coverage": round(verbatim_anchored / verbatim_denominator, 3) if verbatim_denominator else 1.0,
        "global_tasks_count": global_tasks_count,
        "global_tasks_exempted": global_tasks_count,
        "citation_source_coverage": (
            round(citation_tasks_with_sources / len(citation_tasks), 3)
            if citation_tasks else 1.0
        ),
        "citation_tasks": len(citation_tasks),
        "citation_tasks_with_sources": citation_tasks_with_sources,
    }


_TASK_TYPE_SECTION_FALLBACK = {
    "methodology": "Methods",
    "reproducibility": "Methods",
    "causal_claim": "Discussion",
    "literature_positioning": "Introduction / Related Work",
    "citation": "Introduction / Related Work",
    "clarity": "Discussion",
}


def _revision_task_row(draft_id: str, task: dict) -> dict:
    """Map canonical in-memory revision task shape to the durable DB row."""
    # A null anchor (honest global/absence critique) must still carry a `section` so
    # the UI has a navigation target — never ship null anchor AND null section
    # (that left a task with "Page unknown / Anchor None" the frontend can't place).
    section = task.get("section")
    if not section and task.get("anchor_text") is None:
        section = _TASK_TYPE_SECTION_FALLBACK.get(task.get("task_type", ""), "General")
    return {
        "id": task["id"],
        "draft_id": draft_id,
        "source_type": task.get("source_type", "unknown"),
        "task_type": task.get("task_type", "other"),
        "severity": task.get("severity", "major"),
        "priority": task.get("priority", "medium"),
        "section": section or None,
        # Anchor honesty: anchor_text is a verbatim manuscript substring or None — NEVER
        # the section/problem generative fallback (which the UI would try to highlight as a
        # fake "quote"). The column is nullable.
        "anchor_text": task.get("anchor_text"),
        "line_number": task.get("line_number"),
        "page_number": task.get("page_number"),
        "paragraph_index": task.get("paragraph_index"),
        "char_start": task.get("char_start"),
        "char_end": task.get("char_end"),
        "text_snippet": task.get("text_snippet") or task.get("anchor_text") or None,
        "pdf_coordinates": task.get("pdf_coordinates"),
        "match_confidence": task.get("match_confidence"),
        # NOTE: anchor_type/anchor_verbatim are intentionally NOT persisted per-row yet —
        # the draft_revision_tasks table lacks those columns (see migration 035, unapplied).
        # The honest verbatim_anchor_coverage metric is computed from the in-memory flags
        # and stored in analysis_metadata, so observability is preserved without the columns.
        "problem": task.get("problem", ""),
        "why_it_matters": task.get("why_it_matters") or None,
        "suggested_action": task.get("suggested_action", ""),
        "source_ids": task.get("source_ids") or [],
        "suggested_sources": task.get("suggested_sources") or [],
        "confidence": task.get("confidence"),
        "status": task.get("status", "new"),
        "created_at": datetime.datetime.utcnow().isoformat(),
        "updated_at": datetime.datetime.utcnow().isoformat(),
    }


def apply_meta_review_readiness_guardrail(
    readiness_result: dict,
    meta_review: dict | None,
) -> dict:
    """Bind displayed readiness verdict to the area-chair recommendation."""
    if not meta_review:
        return readiness_result

    recommendation = str(meta_review.get("overall_recommendation") or "").strip().lower()
    policy = {
        "accept": (85, 100, "Strong Submission"),
        "minor_revision": (70, 84, "Minor Revisions"),
        "major_revision": (35, 69, "Major Revisions"),
        "reject": (0, 39, "Reject"),
    }
    if recommendation not in policy:
        return readiness_result

    lower, upper, verdict = policy[recommendation]
    original_score = int(readiness_result.get("readiness_score") or 0)
    score = max(lower, min(original_score, upper))
    score_breakdown = dict(readiness_result.get("score_breakdown") or {})
    score_breakdown.update({
        "base_readiness_score": original_score,
        "base_verdict": readiness_result.get("verdict"),
        "meta_review_recommendation": recommendation,
        "editorial_recommendation": recommendation,
        "meta_review_guardrail": True,
    })
    return {
        **readiness_result,
        "readiness_score": score,
        "verdict": verdict,
        "score_breakdown": score_breakdown,
    }


_PARSER_PREREVIEW_BLOCKING_FLAGS = {"not_grobid_pdf_parse", "very_short_extracted_text", "missing_anchor_map"}


def _parser_prereview_blocked(parser_quality: dict | None) -> tuple[bool, str]:
    """Decide whether a parse is too broken to spend the reviewer panel on.

    Only trips on unambiguous catastrophic-parse signals so a normal (even
    imperfect) PDF parse proceeds. Returns (blocked, reason).
    """
    pq = parser_quality or {}
    flags = set(pq.get("parser_quality_flags") or [])
    hit = flags & _PARSER_PREREVIEW_BLOCKING_FLAGS
    if pq.get("parse_blocked"):
        return True, (pq.get("parse_blocked_reason") or "parse_blocked")
    if hit:
        return True, f"parser_quality_flags={sorted(hit)}"
    return False, ""


async def analyze_draft_with_langgraph(
    draft_id: str,
    project_id: str,
    user_id: str,
    draft_content: str,
    initial_structure: dict | None = None,
    parse_artifact: dict | None = None,
    parser_quality: dict | None = None,
    forced_route: str | None = None,
    reroute_count: int = 0,
) -> dict:
    """
    Analyze a draft using the LangGraph workflow.

    This function:
    1. Runs the complete LangGraph workflow
    2. Extracts and stores all analysis results in the database
    3. Returns a summary of the analysis

    Args:
        draft_id: Draft ID
        project_id: Project ID
        user_id: User ID
        draft_content: Full draft text

    Returns:
        Analysis summary

    Raises:
        Exception: If analysis fails
    """
    logger.info(f"[LangGraph Draft Analysis] ========== STARTING ANALYSIS ==========")
    logger.info(f"[LangGraph Draft Analysis] draft_id={draft_id}")
    logger.info(f"[LangGraph Draft Analysis] project_id={project_id}")
    logger.info(f"[LangGraph Draft Analysis] user_id={user_id}")
    logger.info(f"[LangGraph Draft Analysis] draft_content length={len(draft_content)} chars")

    analysis_run_id = None
    try:
        draft_context_res = supabase.table("drafts")\
            .select("title, paper_type, citation_style, file_type, active_analysis_run_id")\
            .eq("id", draft_id)\
            .limit(1)\
            .execute()
        draft_context = draft_context_res.data[0] if draft_context_res.data else {}
        active_run_id = draft_context.get("active_analysis_run_id")
        existing_analysis_res = active_run_filter(
            supabase.table("draft_analysis")
            .select("analysis, analysis_metadata")
            .eq("draft_id", draft_id)
            .limit(1),
            active_run_id,
        ).execute()
        existing_analysis = {}
        existing_metadata = {}
        if existing_analysis_res.data:
            existing_analysis = existing_analysis_res.data[0].get("analysis") or {}
            existing_metadata = existing_analysis_res.data[0].get("analysis_metadata") or {}

        paper_type = draft_context.get("paper_type") or existing_metadata.get("paper_type")
        citation_style = draft_context.get("citation_style") or existing_metadata.get("citation_style")
        analysis_run_id = create_analysis_run(
            draft_id=draft_id,
            project_id=project_id,
            user_id=user_id,
            attempt_number=reroute_count + 1,
            forced_route=forced_route,
        )

        # Pre-review parser-quality halt: if the parser fundamentally failed, do not
        # spend the reviewer panel + LLM budget reviewing unreliable text. Fail fast
        # and flag for parser review. Only trips on unambiguous catastrophic-parse
        # signals, so a normal (even imperfect) PDF parse proceeds as before.
        from app.services.draft_parse_artifacts import load_parse_artifact as _load_parse_artifact
        _pq = parser_quality or parse_artifact or _load_parse_artifact(draft_id) or {}
        _halt, reason = _parser_prereview_blocked(_pq)
        if _halt:
            _pq_flags = set(_pq.get("parser_quality_flags") or [])
            logger.warning(
                "[LangGraph Draft Analysis] Pre-review parser halt for draft %s: %s",
                draft_id,
                reason,
            )
            mark_analysis_run(
                analysis_run_id,
                status="failed",
                quality_gate_results={"parser_prereview_halt": {
                    "halted": True,
                    "parser_quality_score": _pq.get("parser_quality_score"),
                    "parser_quality_flags": sorted(_pq_flags),
                    "reason": reason,
                }},
                failure_reason=f"parser_quality_too_low_for_review: {reason}",
            )
            raise ValueError(f"Parser quality too low to review reliably: {reason}")

        # Run the LangGraph workflow
        logger.info(f"[LangGraph Draft Analysis] Calling run_draft_analysis_workflow...")
        final_state = await run_draft_analysis_workflow(
            draft_id=draft_id,
            project_id=project_id,
            user_id=user_id,
            draft_content=draft_content,
            paper_type=paper_type,
            citation_style=citation_style,
            analysis=existing_analysis,
            initial_structure=initial_structure,
            parse_artifact=parse_artifact,
            parser_quality=parser_quality,
            forced_route=forced_route,
            checkpoint_enabled=True,
            # Keys the root trace span to the same id the durable artifacts use,
            # so a span tree joins to draft_analysis_runs without a second lookup.
            analysis_run_id=analysis_run_id,
        )
        logger.info(f"[LangGraph Draft Analysis] Workflow completed, processing results...")

        # Extract results from final state
        structure = final_state.get("structure", {})
        manuscript_profile = final_state.get("manuscript_profile", {})
        claims = final_state.get("claims", [])
        claims_with_citations = final_state.get("claims_with_citations", [])
        gaps = final_state.get("coverage_gaps", [])
        feedback = final_state.get("reviewer_feedback", [])
        structural_feedback = final_state.get("structural_feedback", [])
        diagnostic_findings = final_state.get("diagnostic_findings", [])
        synthesis_report = final_state.get("synthesis_report", {})
        errors = final_state.get("errors", [])

        all_feedback = list(feedback)

        logger.info(
            f"[LangGraph Draft Analysis] Workflow completed: "
            f"{len(claims)} claims, {len(gaps)} gaps, "
            f"{len(feedback)} feedback + {len(structural_feedback)} structural items + "
            f"{len(diagnostic_findings)} diagnostic findings"
        )

        # ============================================================
        # PRE-STORAGE: Enrich claims with citation display strings + suggested_citations
        # ============================================================
        # Build claim_text -> best citation mapping + suggested_citations from B2
        claim_citation_map: dict = {}
        claim_suggestions_map: dict = {}  # B2: suggested citations from paper discovery
        all_doc_ids: set = set()
        for cwc in (claims_with_citations or []):
            cit_claim = cwc.get("claim", {})
            apply_existing_citation_gate(cit_claim)
            citations = [
                citation for citation in (cwc.get("citations", []) or [])
                if _valid_citation_result(citation)
            ]
            cwc["citations"] = citations
            suggested_cits = cwc.get("suggested_citations", [])
            claim_key = cit_claim.get("claim_text", "")
            if citations:
                best = max(citations, key=lambda c: float(c.get("similarity", 0)))
                doc_id = best.get("document_id")
                if doc_id:
                    claim_citation_map[claim_key] = {
                        "doc_id": doc_id,
                        "similarity": float(best.get("similarity", 0)),
                        "doc_title": best.get("document_title", ""),
                    }
                    all_doc_ids.add(doc_id)
            if suggested_cits:
                claim_suggestions_map[claim_key] = suggested_cits

        for claim in claims:
            apply_existing_citation_gate(claim)

        # Batch-fetch document metadata (authors + year) for citation display
        import re as _re
        _ARXIV_ID_RE = _re.compile(r'^\d{4}\.\d{4,5}(v\d+)?$')
        _bad_year = {"Unknown", "unknown", "n.d.", "", None}
        doc_display_map: dict = {}
        if all_doc_ids:
            try:
                docs_res = supabase.table("documents")\
                    .select("id, title, analysis, metadata")\
                    .neq("resolution_status", "unresolved")\
                    .in_("id", list(all_doc_ids))\
                    .execute()
                # First pass: build display map from user/project document metadata only.
                for doc in (docs_res.data or []):
                    citation_meta = (doc.get("analysis") or {}).get("citation_metadata", {})
                    doc_meta = doc.get("metadata") or {}
                    # Authors: prefer GROBID-analysed citation_metadata, fall back to BibTeX metadata
                    authors = citation_meta.get("all_authors", []) or doc_meta.get("authors", [])
                    # Year: same priority
                    year = citation_meta.get("year") or doc_meta.get("year")
                    title = (doc.get("title") or "Untitled document")
                    if authors:
                        first_last = (str(authors[0]).split(",")[0] if "," in str(authors[0]) else str(authors[0])).strip()
                        author_str = f"{first_last} et al." if len(authors) > 1 else first_last
                        year_clean = str(year) if year and str(year) not in _bad_year else None
                        doc_display_map[doc["id"]] = f"{author_str} ({year_clean})" if year_clean else author_str
                    else:
                        # No authors anywhere — check if title is a raw arxiv ID
                        clean = title.strip()
                        if _ARXIV_ID_RE.match(clean):
                            arxiv_id = _re.sub(r'v\d+$', '', clean)
                            doc_display_map[doc["id"]] = f"arXiv:{arxiv_id}"  # safe fallback
                        else:
                            doc_display_map[doc["id"]] = title[:50]
            except Exception as doc_err:
                logger.warning(
                    "[LangGraph Draft Analysis] Could not fetch doc metadata for display: %s",
                    safe_exception(doc_err),
                )

        # ============================================================
        # 1. Store draft_analysis (structure and initial metadata)
        # ============================================================
        draft_analysis_data = {
            "draft_id": draft_id,
            "structure": strip_manuscript_content_from_structure(structure),
            "word_count": structure.get("word_count", 0),
            "analysis": existing_analysis,
            "analysis_metadata": {
                **existing_metadata,
                "workflow_type": "langgraph",
                "total_claims": len(claims),
                "total_gaps": len(gaps),
                "total_feedback": len(all_feedback) + len(structural_feedback),
                "total_diagnostic_findings": len(diagnostic_findings),
                "errors": errors,
                "timestamp": datetime.datetime.utcnow().isoformat(),
                "paper_type": draft_context.get("paper_type", existing_metadata.get("paper_type")),
                "citation_style": draft_context.get("citation_style", existing_metadata.get("citation_style")),
                "manuscript_profile": manuscript_profile,
                "diagnostic_findings": diagnostic_findings,
            },
            "created_at": datetime.datetime.utcnow().isoformat()
        }

        staged_draft_analysis_row = draft_analysis_data

        # ============================================================
        # 2. Stage draft_claims
        # ============================================================
        claims_data = []
        if claims:
            for claim in claims:
                claim_key = claim.get("claim_text", "")
                citation_info = claim_citation_map.get(claim_key)
                suggested_cits = claim_suggestions_map.get(claim_key, [])
                suggested_sources = []

                if citation_info:
                    base_display = doc_display_map.get(citation_info["doc_id"], "")
                    similarity_pct = int(citation_info["similarity"] * 100)
                    if base_display:
                        display_str = f"{base_display} · {similarity_pct}% match"
                    elif citation_info.get("doc_title"):
                        short_title = citation_info["doc_title"][:45] + ("…" if len(citation_info["doc_title"]) > 45 else "")
                        display_str = f"{short_title} · {similarity_pct}% match"
                    else:
                        display_str = f"Library document · {similarity_pct}% match"
                    supporting_lit = {
                        "top_match": {
                            "document_id": citation_info["doc_id"],
                            "document_title": citation_info["doc_title"],
                            "similarity": citation_info["similarity"],
                            "display": display_str,
                        },
                        "suggested_citations": suggested_cits,
                    }
                    suggested_sources.append(_suggested_source_payload({
                        "document_id": citation_info["doc_id"],
                        "document_title": citation_info["doc_title"],
                        "similarity": citation_info["similarity"],
                    }, display_str))
                else:
                    supporting_lit = {
                        "top_match": None,
                        "suggested_citations": suggested_cits,
                    }
                for suggested in suggested_cits:
                    if _valid_citation_result(suggested):
                        suggested_sources.append(_suggested_source_payload(suggested))
                if suggested_sources:
                    claim["suggested_sources"] = suggested_sources[:5]

                claims_data.append({
                    "draft_id": draft_id,
                    "claim_text": claim["claim_text"],
                    "claim_type": claim["claim_type"],
                    "section_location": claim["section_location"],
                    "importance_score": claim["importance_score"],
                    "requires_citation": False if has_existing_citation(claim) else claim.get("requires_citation", True),
                    "existing_citations": claim.get("existing_citations", []),
                    "max_similarity": citation_info["similarity"] if citation_info else 0.0,
                    "supporting_literature": supporting_lit,
                    **_anchor_fields(claim),
                    "created_at": datetime.datetime.utcnow().isoformat()
                })

            logger.info(f"[LangGraph Draft Analysis] Staged {len(claims)} claims")

        # ============================================================
        # 3. Stage coverage_gaps
        # ============================================================
        gaps_data = []
        if gaps:
            _severity_map = {
                "critical": "high", "major": "high",
                "minor": "low", "high": "high", "medium": "medium", "low": "low"
            }
            for gap in gaps:
                raw_priority = gap.get("severity", gap.get("priority", "medium"))
                db_priority = _severity_map.get(raw_priority, "medium")
                gaps_data.append({
                    "draft_id": draft_id,
                    "gap_type": gap["gap_type"],
                    "description": gap["description"],
                    "priority": db_priority,
                    "suggested_papers": gap.get("suggested_papers", []),
                    "reasoning": gap.get("reasoning", ""),
                    **_anchor_fields(gap),
                    "created_at": datetime.datetime.utcnow().isoformat()
                })

            logger.info(f"[LangGraph Draft Analysis] Staged {len(gaps)} coverage gaps")

        # ============================================================
        # 4. Stage reviewer_feedback rows
        #    with full anchor/QA fields from draft_anchor_qa.py
        # ============================================================
        def _fb_row(fb: dict, persona: str = "reviewer_2") -> dict:
            qa = fb.get("qa_result") or {}
            anchor = qa.get("anchor") or {}
            qa_passed = qa.get("passed")
            failed_checks = qa.get("failed_checks", [])
            return {
                "draft_id": draft_id,
                "feedback_type": fb.get("feedback_type", "general"),
                "feedback_text": fb.get("feedback_text", ""),
                "severity": fb.get("severity", "minor"),
                "reviewer_persona": _normalize_reviewer_persona(fb.get("reviewer_persona"), persona),
                "section_reference": fb.get("section_reference", ""),
                "specific_issue": fb.get("specific_issue", ""),
                "suggestions": fb.get("suggestions", []),
                "source_grounding": fb.get("source_grounding"),
                # Anchor fields (migration 020)
                "target_claim_id": fb.get("target_claim_id") or qa.get("target_claim_id"),
                "target_gap_id": fb.get("target_gap_id") or qa.get("target_gap_id"),
                "line_number": fb.get("line_number") or anchor.get("line_number"),
                "text_snippet": fb.get("text_snippet") or anchor.get("text_snippet"),
                "char_start": fb.get("char_start") or anchor.get("char_start"),
                "char_end": fb.get("char_end") or anchor.get("char_end"),
                "match_confidence": fb.get("match_confidence") or anchor.get("match_confidence"),
                "qa_status": "passed" if qa_passed else ("failed" if qa_passed is False else "skipped"),
                "qa_notes": failed_checks,
                "created_at": datetime.datetime.utcnow().isoformat(),
            }

        def _dedupe_feedback_rows(rows: list[dict]) -> list[dict]:
            seen = set()
            deduped = []
            for row in rows:
                normalized_text = " ".join((row.get("feedback_text") or "").lower().split())
                if not normalized_text:
                    continue
                key = (row.get("feedback_type"), row.get("severity"), normalized_text)
                if key in seen:
                    continue
                seen.add(key)
                deduped.append(row)
            return deduped

        feedback_data = [_fb_row(fb) for fb in all_feedback if fb.get("feedback_text")]

        # Structural feedback always reflects current draft state
        for fb in structural_feedback:
            feedback_data.append({
                "draft_id": draft_id,
                "feedback_type": "structural",
                "feedback_text": fb.get("feedback_text", ""),
                "severity": fb.get("severity", "major"),
                "reviewer_persona": "reviewer_2",
                "section_reference": fb.get("section_reference", ""),
                "specific_issue": fb.get("specific_issue", ""),
                "qa_status": "skipped",
                "qa_notes": [],
                "created_at": datetime.datetime.utcnow().isoformat(),
            })

        feedback_data = _dedupe_feedback_rows(feedback_data)

        if feedback_data:
            logger.info(f"[LangGraph Draft Analysis] Staged {len(feedback_data)} feedback items")

        # Reviewer 1 strengths are intentionally not inserted into the
        # actionable feedback queue; strengths belong in panel/meta-review.
        r1_items = []
        r1_rows = []

        # ============================================================
        # 5. Stage citation_suggestions
        # ============================================================
        stored_citation_suggestion_count = 0
        citation_suggestions_data = []
        if claims_with_citations:
            for claim_with_citation in claims_with_citations:
                claim = claim_with_citation.get("claim", {})
                if claim.get("requires_citation") is not True:
                    continue
                if has_existing_citation(claim):
                    continue
                citations = claim_with_citation.get("citations", [])
                citation_quality = claim_with_citation.get("citation_quality", "unknown")
                claim_gaps = claim_with_citation.get("gaps", [])

                for citation in citations:
                    if not _valid_citation_result(citation):
                        continue
                    if citation_quality == "none":
                        suggestion_type, impact_level, priority_score = "missing_citation", "critical", 1.0
                    elif citation_quality == "weak":
                        suggestion_type, impact_level, priority_score = "weak_citation", "high", 0.8
                    elif citation_quality == "moderate":
                        suggestion_type, impact_level, priority_score = "alternative_source", "medium", 0.5
                    else:
                        suggestion_type, impact_level, priority_score = "supporting_citation", "low", 0.3

                    reasoning_parts = []
                    if citation_quality == "none":
                        reasoning_parts.append("No supporting citations found for this claim.")
                    elif citation_quality == "weak":
                        reasoning_parts.append("Current citation support is weak.")
                    if claim_gaps:
                        reasoning_parts.append("Gaps identified: " + "; ".join(claim_gaps))
                    reasoning = " ".join(reasoning_parts) or "Citation suggestion based on literature search"

                    citation_suggestions_data.append({
                        "draft_id": draft_id,
                        "user_id": user_id,
                        "claim_text": claim.get("claim_text", ""),
                        "section_location": claim.get("section_location", ""),
                        "suggestion_type": suggestion_type,
                        "suggested_paper": {
                            "document_id": citation.get("document_id"),
                            "document_title": citation.get("document_title", "Unknown"),
                            "content": citation.get("content", ""),
                            "similarity": citation.get("similarity", 0.0),
                            "chunk_index": citation.get("chunk_index"),
                            "section": citation.get("section", "")
                        },
                        "confidence_score": citation.get("similarity", 0.0),
                        "relevance_score": citation.get("similarity", 0.0),
                        "priority_score": priority_score,
                        "impact_level": impact_level,
                        "reasoning": reasoning,
                        "status": "pending",
                        "created_at": datetime.datetime.utcnow().isoformat()
                    })

            stored_citation_suggestion_count = len(citation_suggestions_data)
            if citation_suggestions_data:
                logger.info(f"[LangGraph Draft Analysis] Staged {len(citation_suggestions_data)} citation suggestions")

        revision_tasks = build_revision_tasks(
            diagnostic_findings=diagnostic_findings,
            reviewer_outputs=final_state.get("judged_reviewer_outputs") or final_state.get("reviewer_outputs") or [],
            claims=claims,
            gaps=gaps,
            structural_feedback=structural_feedback,
            structure=structure,
            parser_quality=final_state.get("parser_quality") or existing_metadata,
            manuscript_profile=manuscript_profile,
            meta_review=final_state.get("meta_review") or {},
        )
        revision_tasks = _apply_parse_artifact_anchors(draft_id, revision_tasks, final_state.get("parse_artifact") or {})
        revision_tasks = _map_revision_task_pages(draft_id, revision_tasks)
        evidence_manifest = build_evidence_manifest(draft_content)
        final_state["evidence_manifest"] = evidence_manifest
        logger.info(
            "[LangGraph Draft Analysis] Evidence manifest: %s",
            manifest_summary(evidence_manifest),
        )
        # Domain-agnostic stale-search-window critique (evidence-driven): if the
        # last search year is well before submission, surface it. Compared to the
        # current (submission) year; threshold in stale_search_task.
        _stale_task = stale_search_task(evidence_manifest, datetime.datetime.utcnow().year)
        if _stale_task and not any(
            t.get("dedupe_category") == "search_currency" for t in revision_tasks
        ):
            revision_tasks.append(_stale_task)
            logger.info(
                "[LangGraph Draft Analysis] Added stale-search critique (latest=%s)",
                _stale_task.get("id"),
            )
        revision_tasks, evidence_rebuttal = reconcile_tasks_against_evidence(
            revision_tasks,
            full_text=draft_content,
            manuscript_profile=manuscript_profile,
            manifest=evidence_manifest,
        )
        final_state["evidence_rebuttal"] = evidence_rebuttal
        if evidence_rebuttal.get("tasks_dropped") or evidence_rebuttal.get("tasks_rewritten"):
            logger.warning(
                "[LangGraph Draft Analysis] Evidence rebuttal adjusted tasks dropped=%s rewritten=%s contradictions=%s",
                evidence_rebuttal.get("tasks_dropped"),
                evidence_rebuttal.get("tasks_rewritten"),
                evidence_rebuttal.get("contradictions_resolved"),
            )
        try:
            from app.services.draft_external_source_discovery import enrich_revision_tasks_with_sources
            revision_tasks = await enrich_revision_tasks_with_sources(
                draft_id=draft_id,
                project_id=project_id,
                user_id=user_id,
                revision_tasks=revision_tasks,
                manuscript_profile=manuscript_profile,
            )
        except Exception as task_source_err:
            logger.warning(
                "[LangGraph Draft Analysis] Task-level source surfacing failed (non-fatal): %s",
                safe_exception(task_source_err),
            )
        # Sanitize sources (drop off-domain / low-overlap citations) BEFORE the quality
        # judge runs, so the judge evaluates the cleaned task list. Otherwise an
        # off-domain source that sanitize would remove anyway (e.g. a "phenol wastewater
        # treatment" review for a sodium-ion claim) still gets flagged by the judge and
        # needlessly trips the publish gate. analysis_quality_judge is not available yet
        # at this point, so the judge-flag rejection path is skipped here — the
        # deterministic task/profile-overlap checks still remove the off-domain source.
        revision_tasks, source_safety = sanitize_revision_task_sources(
            revision_tasks,
            manuscript_profile=manuscript_profile,
            analysis_quality_judge=None,
        )
        revision_tasks = [repair_anchor(t, draft_content) for t in revision_tasks]

        # Evidence gate: drop revision tasks whose anchor is non-empty but not verbatim
        try:
            from app.services.draft_evidence_gate import strip_unanchored_findings
            revision_tasks = strip_unanchored_findings(revision_tasks, draft_content)
        except Exception as _ev_gate_exc:
            logger.warning("[LangGraph Draft Analysis] Revision task evidence gate skipped: %s", safe_exception(_ev_gate_exc))

        final_state["revision_tasks"] = revision_tasks
        revision_quality_metrics = _revision_quality_metrics(revision_tasks, draft_content)
        final_state["revision_quality_metrics"] = revision_quality_metrics
        logger.info(
            "[LangGraph Draft Analysis] Synthesized %s canonical revision tasks metrics=%s",
            len(revision_tasks),
            revision_quality_metrics,
        )

        analysis_quality_judge = await judge_analysis_quality(
            draft_title=draft_context.get("title", ""),
            draft_excerpt=draft_content[:8000],
            manuscript_profile=manuscript_profile,
            reviewer_outputs=final_state.get("judged_reviewer_outputs") or final_state.get("reviewer_outputs") or [],
            meta_review=final_state.get("meta_review") or {},
            revision_tasks=revision_tasks,
            revision_quality_metrics=revision_quality_metrics,
        )
        final_state["analysis_quality_judge"] = analysis_quality_judge
        suggested_route = str(analysis_quality_judge.get("suggested_route") or "").strip()
        if (
            analysis_quality_judge.get("reroute_required")
            and reroute_count < 1
            and suggested_route in ROUTING_DOMAINS
            and suggested_route != manuscript_profile.get("routing_domain")
        ):
            logger.warning(
                "[LangGraph Draft Analysis] Quality judge requested reroute %s -> %s; discarding current run",
                manuscript_profile.get("routing_domain"),
                suggested_route,
            )
            mark_analysis_run(
                analysis_run_id,
                status="rerouted",
                manuscript_profile=manuscript_profile,
                quality_gate_results={"analysis_quality_judge": analysis_quality_judge},
                reroute_from=manuscript_profile.get("routing_domain"),
                reroute_to=suggested_route,
            )
            return await analyze_draft_with_langgraph(
                draft_id=draft_id,
                project_id=project_id,
                user_id=user_id,
                draft_content=draft_content,
                initial_structure=initial_structure,
                parse_artifact=parse_artifact,
                parser_quality=parser_quality,
                forced_route=suggested_route,
                reroute_count=reroute_count + 1,
            )
        # A quality_pass=False is a HARD failure (user gets nothing) — reserve it for a
        # genuinely wrong-domain / garbage analysis. If the analysis is on-domain
        # (domain_alignment high) and the only problem is an off-domain SUGGESTED SOURCE,
        # don't nuke the whole run: downgrade to the soft path so the publish gate flags
        # needs_retry and the suppression step drops the bad source while keeping the
        # reviewer panel + meta-review. (A stray wastewater source on a battery review
        # must not delete a good analysis.)
        domain_aligned = float(analysis_quality_judge.get("domain_alignment_score") or 0.0) >= 0.6
        contamination_only = (
            domain_aligned
            and not analysis_quality_judge.get("reroute_required")
            and bool(analysis_quality_judge.get("source_contamination_flags"))
        )
        if not analysis_quality_judge.get("quality_pass", True) and not contamination_only:
            mark_analysis_run(
                analysis_run_id,
                status="failed",
                manuscript_profile=manuscript_profile,
                quality_gate_results={"analysis_quality_judge": analysis_quality_judge},
                failure_reason=analysis_quality_judge.get("failure_reason") or analysis_quality_judge.get("judge_rationale"),
            )
            raise ValueError(
                "Analysis quality judge rejected output: "
                f"{analysis_quality_judge.get('failure_reason') or analysis_quality_judge.get('judge_rationale')}"
            )
        if not analysis_quality_judge.get("quality_pass", True) and contamination_only:
            logger.warning(
                "[LangGraph Draft Analysis] Quality judge fail downgraded to soft (on-domain "
                "analysis, source-contamination only) — gate+suppression will handle: %s",
                analysis_quality_judge.get("source_contamination_flags"),
            )

        # Second sanitize pass now that the judge has run — this one CAN act on the
        # judge's wrong-domain flags to catch anything the deterministic pre-judge pass
        # missed. Merge the pruning metrics from both passes.
        revision_tasks, source_safety_2 = sanitize_revision_task_sources(
            revision_tasks,
            manuscript_profile=manuscript_profile,
            analysis_quality_judge=analysis_quality_judge,
        )
        source_safety = _merge_source_safety(source_safety, source_safety_2)
        revision_tasks, final_evidence_rebuttal = reconcile_tasks_against_evidence(
            revision_tasks,
            full_text=draft_content,
            manuscript_profile=manuscript_profile,
            manifest=final_state.get("evidence_manifest"),
        )
        if final_evidence_rebuttal.get("events"):
            combined_events = list((final_state.get("evidence_rebuttal") or {}).get("events") or [])
            combined_events.extend(final_evidence_rebuttal.get("events") or [])
            final_state["evidence_rebuttal"] = {
                **(final_state.get("evidence_rebuttal") or {}),
                "final_pass": final_evidence_rebuttal,
                "events": combined_events,
            }
        revision_tasks = consolidate_revision_tasks(revision_tasks)
        # Pre-emit grounding check (issue #2): downgrade + flag any "X is missing" task
        # whose X is actually already addressed in the body. Never drops — user decides.
        try:
            import os
            from app.services.draft_task_evidence import (
                llm_verify_absence_claims,
                verify_absence_claims,
            )
            if os.environ.get("OPENAI_API_KEY") and not os.environ.get("PYTEST_CURRENT_TEST"):
                # PRIMARY: LLM entailment verifier (only reliable false-absence detector).
                revision_tasks, grounding_metrics = await llm_verify_absence_claims(
                    revision_tasks, draft_content
                )
            else:
                # FALLBACK (no key / under pytest): sync lexical check.
                revision_tasks, grounding_metrics = verify_absence_claims(
                    revision_tasks, draft_content
                )
            if grounding_metrics.get("llm_addressed_dropped"):
                logger.info(
                    "[LangGraph Draft Analysis] LLM verifier DROPPED %s addressed absence task(s)",
                    grounding_metrics["llm_addressed_dropped"],
                )
            if grounding_metrics.get("llm_partial_downgraded"):
                logger.info(
                    "[LangGraph Draft Analysis] LLM verifier downgraded %s partial absence task(s)",
                    grounding_metrics["llm_partial_downgraded"],
                )
            if grounding_metrics.get("absence_tasks_downgraded"):
                logger.info(
                    "[LangGraph Draft Analysis] Grounding check downgraded %s absence task(s)",
                    grounding_metrics["absence_tasks_downgraded"],
                )
            if grounding_metrics.get("self_contradiction_dropped"):
                logger.info(
                    "[LangGraph Draft Analysis] Grounding check DROPPED %s self-contradicting absence task(s) (B1)",
                    grounding_metrics["self_contradiction_dropped"],
                )
        except Exception as grounding_err:
            logger.warning(
                "[LangGraph Draft Analysis] grounding check failed (non-fatal): %s",
                safe_exception(grounding_err),
            )
        # Verbatim anchor repair (real fix, 4b): with a key (and not under pytest), use
        # the LLM repairer which can turn paraphrase anchors into real quotes and honestly
        # mark whole-document points as global. Otherwise fall back to the deterministic
        # repair loop. anchor_type set here drives the honest coverage metric below.
        if os.environ.get("OPENAI_API_KEY") and not os.environ.get("PYTEST_CURRENT_TEST"):
            from app.services.draft_task_evidence import llm_repair_anchors
            revision_tasks = await llm_repair_anchors(revision_tasks, draft_content)
        else:
            revision_tasks = [repair_anchor(t, draft_content) for t in revision_tasks]
        # LLM semantic dedup (FIX 2): collapse same-critique-different-words pairs that
        # survive lexical + embedding dedup (within-domain paraphrases ~0.6 cosine).
        # After anchor repair so merges keep the most-specific verbatim anchor; before the
        # final metric so coverage reflects the deduped set. Falls back to no-op on failure.
        if os.environ.get("OPENAI_API_KEY") and not os.environ.get("PYTEST_CURRENT_TEST"):
            revision_tasks = await llm_dedupe_tasks(revision_tasks)
        # Anchor-collision merge AFTER repair: llm_repair_anchors can assign two distinct
        # tasks the same verbatim span (Gemini eval: two major tasks lighting up the
        # identical block). Collapse them here, once the final anchors are set.
        from app.workflows.draft_analysis.revision_tasks import merge_anchor_collisions
        revision_tasks = merge_anchor_collisions(revision_tasks)
        final_state["revision_tasks"] = revision_tasks
        revision_quality_metrics = _revision_quality_metrics(revision_tasks, draft_content)
        final_state["revision_quality_metrics"] = revision_quality_metrics
        final_state["source_safety"] = source_safety
        if source_safety["source_safety_metrics"].get("sources_pruned"):
            logger.warning(
                "[LangGraph Draft Analysis] Pruned %s unsafe suggested sources before persistence",
                source_safety["source_safety_metrics"].get("sources_pruned"),
            )

        logger.info(f"[LangGraph Draft Analysis] Staged {len(revision_tasks)} durable revision tasks")

        # ============================================================
        # 6. Post-workflow enrichment (paper suggestions, score, action items)
        # ============================================================

        # 6a. Suggest external papers for coverage gaps
        enriched_gaps = list(gaps)
        try:
            from app.services.coverage_analysis import suggest_papers_for_gaps
            logger.info("[LangGraph Draft Analysis] Running suggest_papers_for_gaps...")
            enriched_gaps = await suggest_papers_for_gaps(
                list(gaps), project_id, manuscript_profile=manuscript_profile
            )
            for idx, enriched_gap in enumerate(enriched_gaps or []):
                if idx < len(gaps_data):
                    gaps_data[idx]["suggested_papers"] = enriched_gap.get(
                        "suggested_papers",
                        gaps_data[idx].get("suggested_papers", []),
                    )
            logger.info(f"[LangGraph Draft Analysis] External paper suggestions applied to {len(enriched_gaps)} gaps")
        except Exception as suggestion_err:
            logger.warning(
                "[LangGraph Draft Analysis] suggest_papers_for_gaps failed (non-fatal): %s",
                safe_exception(suggestion_err),
            )

        # 6a-bis. Embedding relevance filter (RAG contamination guard). Additional layer
        # on top of the topic-term/domain gates: drop any suggested source whose embedding
        # cosine vs THIS manuscript falls below DRAFT_SOURCE_RELEVANCE_MIN. The manuscript
        # defines its own domain — no keyword/MeSH lists. No-op under pytest / no key.
        relevance_metrics = {}
        if os.environ.get("OPENAI_API_KEY") and not os.environ.get("PYTEST_CURRENT_TEST"):
            try:
                from app.services.draft_task_evidence import filter_sources_by_manuscript_relevance
                revision_tasks, gaps_data, relevance_metrics = filter_sources_by_manuscript_relevance(
                    revision_tasks, gaps_data, draft_content
                )
                if relevance_metrics.get("sources_dropped_offdomain"):
                    logger.warning(
                        "[LangGraph Draft Analysis] Dropped %s off-domain suggested sources "
                        "(relevance < %s)",
                        relevance_metrics.get("sources_dropped_offdomain"),
                        relevance_metrics.get("relevance_threshold"),
                    )
            except Exception as relevance_err:
                logger.warning(
                    "[LangGraph Draft Analysis] source relevance filter failed (non-fatal): %s",
                    safe_exception(relevance_err),
                )

        # Stage durable rows AFTER source-relevance filtering so off-domain
        # suggested_sources are excluded from persistence.
        task_rows = [_revision_task_row(draft_id, task) for task in revision_tasks]

        # 6b. Calculate deterministic readiness score from canonical tasks
        readiness_result = calculate_revision_task_readiness_score(
            revision_tasks,
            manuscript_profile=manuscript_profile,
        )
        readiness_result = apply_meta_review_readiness_guardrail(
            readiness_result,
            final_state.get("meta_review") or {},
        )
        logger.info(
            f"[LangGraph Draft Analysis] Readiness score: {readiness_result['readiness_score']} "
            f"({readiness_result['verdict']})"
        )

        # 6c. action_items removed — revision tasks are the canonical to-do list;
        # synthesize_action_items duplicated them and bypassed the deductive filter.
        action_items: list = []

        # 6d. Publish staged artifacts for this validated run
        total_feedback = len(feedback_data) + len(r1_rows)
        total_feedback = len(revision_tasks)
        enriched_metadata = {
            **existing_metadata,
            "workflow_type": "langgraph",
            "analysis_run_id": analysis_run_id,
            "total_claims": len(claims),
            "total_gaps": len(gaps),
            "total_feedback": len(revision_tasks),
            "total_diagnostic_findings": len(diagnostic_findings),
            "errors": errors,
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "paper_type": draft_context.get("paper_type", existing_metadata.get("paper_type")),
            "citation_style": draft_context.get("citation_style", existing_metadata.get("citation_style")),
            "manuscript_profile": manuscript_profile,
            "diagnostic_findings": diagnostic_findings,
            "revision_quality_metrics": final_state.get("revision_quality_metrics"),
            "source_safety_metrics": {
                **final_state.get("source_safety", {}).get("source_safety_metrics", {}),
                **relevance_metrics,
            },
            "pruned_sources": final_state.get("source_safety", {}).get("pruned_sources", []),
            "evidence_rebuttal_metrics": final_state.get("evidence_rebuttal", {}),
            "readiness_score": readiness_result.get("readiness_score"),
            "verdict": readiness_result.get("verdict"),
            "score_breakdown": readiness_result.get("score_breakdown", {}),
            "editorial_recommendation": (final_state.get("meta_review") or {}).get("overall_recommendation"),
            "action_items": action_items,
            "citation_judge": final_state.get("citation_judge_output"),
            "reviewer_judge": final_state.get("reviewer_judge_output"),
            "analysis_quality_judge": final_state.get("analysis_quality_judge"),
            "editor_decision": final_state.get("editor_decision"),
            "synthesis_report": synthesis_report,
        }
        staged_draft_analysis_row["analysis_metadata"] = enriched_metadata

        reviewer_panel_rows = []
        for output in final_state.get("judged_reviewer_outputs") or final_state.get("reviewer_outputs") or []:
            reviewer_panel_rows.append({
                "draft_id": draft_id,
                "reviewer_id": output.get("reviewer_id"),
                "summary": output.get("summary"),
                "strengths": output.get("strengths") or [],
                "weaknesses": output.get("weaknesses") or [],
                "questions_to_authors": output.get("questions_to_authors") or [],
                "limitations_to_address": output.get("limitations_to_address") or [],
                "issues": output.get("issues") or [],
                "rating": output.get("rating"),
                "confidence": output.get("confidence"),
                "recommendation": output.get("recommendation"),
            })

        meta_review_rows = []
        if final_state.get("meta_review"):
            meta_review_rows.append({
                "draft_id": draft_id,
                **(final_state.get("meta_review") or {}),
            })

        publish_gate = evaluate_publish_gate(
            file_type=draft_context.get("file_type"),
            revision_quality_metrics=final_state.get("revision_quality_metrics"),
            parser_quality=parser_quality or final_state.get("parser_quality") or existing_metadata,
            source_safety_metrics=final_state.get("source_safety", {}).get("source_safety_metrics", {}),
            contamination_flags=(analysis_quality_judge or {}).get("source_contamination_flags"),
        )
        final_state["publish_gate"] = publish_gate
        enriched_metadata["publish_gate"] = publish_gate
        enriched_metadata["analysis_confidence"] = publish_gate["confidence"]
        # Authoritative publish signals so consumers don't have to reconcile the
        # internal editor routing flag (editor_decision.proceed_to_review, which only
        # means "was it worth sending to reviewers") against the gate verdict. The
        # gate is the single source of truth for whether to trust/ship this analysis.
        enriched_metadata["publishable"] = publish_gate["publishable"]
        enriched_metadata["needs_retry"] = not publish_gate["publishable"]
        if not publish_gate["publishable"]:
            logger.warning(
                "[LangGraph Draft Analysis] Publish gate flagged run %s status=%s reasons=%s",
                analysis_run_id,
                publish_gate["gate_status"],
                publish_gate["reasons"],
            )
            if PUBLISH_GATE_FAIL_CLOSED:
                # Hard fail-closed: refuse to publish misleading low-confidence
                # feedback. Mark the run failed and abort before publishing.
                mark_analysis_run(
                    analysis_run_id,
                    status="failed",
                    manuscript_profile=manuscript_profile,
                    quality_gate_results={
                        "analysis_quality_judge": analysis_quality_judge,
                        "revision_quality_metrics": final_state.get("revision_quality_metrics"),
                        "publish_gate": publish_gate,
                    },
                    source_safety_metrics=final_state.get("source_safety", {}).get("source_safety_metrics", {}),
                    failure_reason=f"publish_gate:{publish_gate['gate_status']}: " + "; ".join(publish_gate["reasons"]),
                )
                raise ValueError(
                    f"Publish gate ({publish_gate['gate_status']}) blocked low-confidence analysis: "
                    + "; ".join(publish_gate["reasons"])
                )

            # Soft path (fail-closed off): ship the trustworthy parts only. Drop the
            # un-anchored durable tasks + all suggested sources (the contaminated /
            # unlocatable surface), but keep the reviewer panel + meta-review + claims.
            task_rows, suppression = suppress_unreliable_task_artifacts(task_rows)
            enriched_metadata["analysis_status"] = "needs_reparse"
            enriched_metadata["suppressed_artifacts"] = {
                "reason": publish_gate["gate_status"],
                **suppression,
            }
            logger.warning(
                "[LangGraph Draft Analysis] publishable=False — suppressed %s un-anchored "
                "tasks + cleared suggested sources; kept reviewer panel/meta/claims",
                suppression["dropped_unanchored_tasks"],
            )

        mark_analysis_run(
            analysis_run_id,
            status="passed",
            manuscript_profile=manuscript_profile,
            quality_gate_results={
                "analysis_quality_judge": analysis_quality_judge,
                "revision_quality_metrics": final_state.get("revision_quality_metrics"),
                "publish_gate": publish_gate,
            },
            source_safety_metrics=final_state.get("source_safety", {}).get("source_safety_metrics", {}),
        )
        publish_counts = publish_analysis_artifacts(
            run_id=analysis_run_id,
            draft_id=draft_id,
            artifacts={
                "draft_analysis": [staged_draft_analysis_row],
                "draft_claims": claims_data,
                "coverage_gaps": gaps_data,
                "reviewer_feedback": feedback_data,
                "reviewer_panel_outputs": reviewer_panel_rows,
                "meta_reviews": meta_review_rows,
                "citation_suggestions": citation_suggestions_data,
                "draft_revision_tasks": task_rows,
            },
        )
        logger.info("[LangGraph Draft Analysis] Published artifacts for run %s counts=%s", analysis_run_id, publish_counts)

        # Publish 100% AFTER status='analyzed' is written to DB.
        # This ensures the frontend re-fetches and finds the draft ready to open.
        await publish_progress(draft_id, "complete", 100, "Analysis complete")

        # Count total citation suggestions stored
        total_citation_suggestions = stored_citation_suggestion_count

        # Return summary
        return {
            "message": "Draft analysis completed successfully",
            "draft_id": draft_id,
            "workflow_type": "langgraph",
            "results": {
                "total_claims": len(claims),
                "claims_by_type": {
                    "empirical": sum(1 for c in claims if c.get("claim_type") == "empirical"),
                    "theoretical": sum(1 for c in claims if c.get("claim_type") == "theoretical"),
                    "methodological": sum(1 for c in claims if c.get("claim_type") == "methodological")
                },
                "total_gaps": len(gaps),
                "total_feedback": total_feedback,
                "total_citation_suggestions": total_citation_suggestions,
                "readiness_score": readiness_result.get("readiness_score"),
                "verdict": readiness_result.get("verdict"),
                "action_items": action_items,
                "synthesis_report": synthesis_report
            },
            "errors": errors
        }

    except Exception as e:
        logger.error("[LangGraph Draft Analysis] Error: %s", safe_exception(e))
        if analysis_run_id:
            try:
                mark_analysis_run(
                    analysis_run_id,
                    status="failed",
                    failure_reason=safe_exception(e),
                )
            except Exception as run_err:
                logger.warning("[LangGraph Draft Analysis] Failed to mark run failed: %s", safe_exception(run_err))

        # Update draft status to 'failed'
        supabase.table("drafts").update({
            "status": "failed",
            "updated_at": datetime.datetime.utcnow().isoformat()
        }).eq("id", draft_id).execute()

        raise

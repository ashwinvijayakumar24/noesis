#!/usr/bin/env python3
"""Export the latest analyzed Noesis draft as JSON and Markdown.

This script is intentionally read-only. It pulls the active analyzed draft and
its active analysis-run artifacts from Supabase, then writes evaluation-friendly
exports under the repository's exports directory.
"""

from __future__ import annotations

import datetime as dt
import argparse
import copy
import json
import os
import re
from pathlib import Path
from typing import Any

from supabase import create_client


ROOT = Path(__file__).resolve().parents[1]
EXPORT_DIR = ROOT / "exports"


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def get_supabase_client():
    env = {
        **load_env_file(ROOT / ".env.local"),
        **load_env_file(ROOT / "services/backend/.env"),
        **os.environ,
    }
    url = env.get("SUPABASE_URL") or env.get("VITE_SUPABASE_URL")
    key = env.get("SUPABASE_SERVICE_ROLE_KEY") or env.get("SUPABASE_ANON_KEY") or env.get("VITE_SUPABASE_ANON_KEY")
    if not url or not key:
        raise RuntimeError("Missing Supabase URL/key in env files")
    return create_client(url, key)


def safe_select(client, table: str, **filters: Any) -> list[dict[str, Any]]:
    try:
        query = client.table(table).select("*")
        for field, value in filters.items():
            query = query.eq(field, value)
        response = query.execute()
        return response.data or []
    except Exception:
        return []


def select_related(client, table: str, draft_id: str, analysis_run_id: str | None) -> list[dict[str, Any]]:
    if analysis_run_id:
        return safe_select(client, table, draft_id=draft_id, analysis_run_id=analysis_run_id)
    return safe_select(client, table, draft_id=draft_id)


def latest_analyzed_draft(client) -> dict[str, Any]:
    response = (
        client.table("drafts")
        .select("*")
        .eq("status", "analyzed")
        .order("updated_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = response.data or []
    if not rows:
        raise RuntimeError("No analyzed drafts found")
    return rows[0]


def draft_by_id(client, draft_id: str) -> dict[str, Any]:
    response = (
        client.table("drafts")
        .select("*")
        .eq("id", draft_id)
        .limit(1)
        .execute()
    )
    rows = response.data or []
    if not rows:
        raise RuntimeError(f"Draft not found: {draft_id}")
    return rows[0]


def latest_analysis_row(client, draft_id: str, analysis_run_id: str | None) -> dict[str, Any]:
    if analysis_run_id:
        rows = safe_select(client, "draft_analysis", draft_id=draft_id, analysis_run_id=analysis_run_id)
        return rows[0] if rows else {}
    response = (
        client.table("draft_analysis")
        .select("*")
        .eq("draft_id", draft_id)
        .order("updated_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = response.data or []
    return rows[0] if rows else {}


def sanitize_analysis_row_for_export(analysis: dict[str, Any]) -> dict[str, Any]:
    """Remove legacy duplicated analysis fields that are no longer canonical."""
    cleaned = copy.deepcopy(analysis or {})
    metadata = cleaned.get("analysis_metadata")
    if isinstance(metadata, dict):
        metadata.pop("revision_tasks", None)
    return cleaned


def table_count(rows: list[dict[str, Any]]) -> int:
    return len(rows or [])


def parser_metrics(parse_artifact: dict[str, Any] | None, analysis: dict[str, Any]) -> dict[str, Any]:
    parse_artifact = parse_artifact or {}
    metadata = analysis.get("analysis_metadata") or {}
    parser_metadata = parse_artifact.get("parser_metadata") or {}
    section_map = parse_artifact.get("section_map") or []
    anchor_map = parse_artifact.get("anchor_map") or []
    return {
        "persisted_parse_artifact_available": bool(parse_artifact),
        "parser_name": parse_artifact.get("parser_name") or metadata.get("parser_name"),
        "parser_quality_flags": parse_artifact.get("parser_quality_flags") or metadata.get("parser_quality_flags") or [],
        "parser_quality_score": parse_artifact.get("parser_quality_score") or metadata.get("parser_quality_score"),
        "section_count": len(section_map),
        "anchor_count": len(anchor_map),
        "grobid_sections_count": (
            parser_metadata.get("grobid_sections_count")
            or metadata.get("grobid_sections_count")
            or len(section_map)
        ),
        "grobid_references_count": (
            parser_metadata.get("grobid_references_count")
            or metadata.get("grobid_references_count")
            or 0
        ),
    }


def location(task: dict[str, Any]) -> str:
    page = task.get("page_number")
    paragraph = task.get("paragraph_index")
    page_label = f"Page {page}" if page is not None else "Page unknown"
    paragraph_label = f"Paragraph {paragraph}" if paragraph is not None else "Paragraph unknown"
    return f"{page_label}, {paragraph_label}"


def block_json(value: Any) -> str:
    return "```json\n" + json.dumps(value or {}, indent=2, ensure_ascii=False) + "\n```"


def clean_filename(text: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", text or "latest_draft_analysis").strip("_").lower()
    return cleaned[:80] or "latest_draft_analysis"


DOMAIN_TITLE_TERMS: dict[str, set[str]] = {
    "biology": {
        "biology", "biomedical", "clinical", "gene", "genetic", "genome", "editing",
        "crispr", "cas9", "sickle", "cell", "hemoglobin", "globin", "hbf", "hbg",
        "hbb", "hspc", "hematopoietic", "therapy", "therapeutic", "thalassemia",
        "transplant", "stem", "bcl11a",
    },
    "chemistry_materials": {
        "chemistry", "materials", "battery", "batteries", "sodium", "ion", "cathode",
        "anode", "electrolyte", "oxide", "layered", "degradation", "cycling",
    },
    "humanities_education": {
        "humanities", "education", "pedagogy", "composition", "writing", "rhetoric",
        "classroom", "literacy", "teaching", "social", "justice", "ai", "algorithm",
    },
    "computer_science_ml": {
        "machine", "learning", "model", "algorithm", "neural", "dataset", "benchmark",
        "classification", "prediction", "deep", "ai", "artificial", "intelligence",
    },
    "public_health_psychology": {
        "social", "media", "adolescent", "adolescents", "teen", "youth", "anxiety",
        "depression", "mental", "health", "psychology", "psychological", "wellbeing",
        "well-being", "systematic", "review", "prisma", "risk", "bias",
    },
    "law_policy": {
        "law", "legal", "court", "statute", "statutory", "regulation", "regulatory",
        "constitutional", "privacy", "liability", "governance", "compliance",
        "jurisdiction", "policy", "case",
    },
    "business_management": {
        "business", "management", "strategy", "firm", "firms", "organizational",
        "operations", "marketing", "entrepreneurship", "supply", "chain", "market",
        "customer", "competitive", "performance",
    },
    "environmental_ecology": {
        "environmental", "ecology", "ecological", "climate", "carbon", "biodiversity",
        "conservation", "ecosystem", "sustainability", "sustainable", "habitat",
        "species", "remote", "sensing",
    },
    "mechanical_civil_engineering": {
        "mechanical", "civil", "engineering", "structural", "finite", "element",
        "fea", "cfd", "fluid", "manufacturing", "concrete", "bridge",
        "transportation", "robotics", "design",
    },
    "math_statistics": {
        "math", "mathematics", "statistics", "statistical", "theorem", "proof",
        "lemma", "estimator", "asymptotic", "identifiability", "bayesian",
        "regression", "inference", "monte", "carlo",
    },
    "neuroscience_cognitive_science": {
        "neuroscience", "cognitive", "cognition", "brain", "fmri", "eeg",
        "neural", "memory", "attention", "perception", "behavioral",
        "neuroimaging", "psychophysics",
    },
    "education_empirical": {
        "education", "educational", "learning", "student", "teacher", "classroom",
        "intervention", "assessment", "achievement", "pretest", "posttest",
        "quasi", "experimental", "rubric",
    },
}


def _doc_title(document: dict[str, Any]) -> str:
    metadata = document.get("metadata") or {}
    return (
        document.get("title")
        or document.get("document_title")
        or metadata.get("title")
        or metadata.get("extracted_title")
        or "Untitled"
    )


def _profile_terms(profile: dict[str, Any]) -> set[str]:
    routing_domain = str(profile.get("routing_domain") or "").lower()
    terms = set(DOMAIN_TITLE_TERMS.get(routing_domain, set()))
    for key in ("domain_tags", "retrieval_domains", "review_lenses", "secondary_domains"):
        for value in profile.get(key) or []:
            terms.update(re.findall(r"[a-z0-9]+", str(value).lower()))
    return {term for term in terms if len(term) >= 3}


def project_literature_summary(
    documents: list[dict[str, Any]],
    profile: dict[str, Any],
) -> dict[str, Any]:
    """Return a compact project-library summary without raw document bodies."""
    terms = _profile_terms(profile)
    included_titles: list[str] = []
    for document in documents:
        title = _doc_title(document)
        haystack = " ".join([
            title,
            str((document.get("metadata") or {}).get("abstract") or ""),
        ]).lower()
        if terms and not any(term in haystack for term in terms):
            continue
        included_titles.append(title)

    return {
        "total_documents": len(documents),
        "included_relevant_title_count": len(included_titles),
        "excluded_from_export_count": max(len(documents) - len(included_titles), 0),
        "raw_documents_omitted": True,
        "included_relevant_titles": included_titles[:20],
    }


def build_markdown(payload: dict[str, Any]) -> str:
    draft = payload["draft"]
    metadata = payload["analysis"].get("analysis_metadata") or {}
    profile = metadata.get("manuscript_profile") or {}
    tasks = payload["durable_revision_tasks"]
    parser = payload["parser_metadata"]
    counts = payload["summary_counts"]

    lines: list[str] = [
        "# Noesis Draft Analysis Export",
        "",
        "## Draft",
        f"- Title: {draft.get('title')}",
        f"- Draft ID: {draft.get('id')}",
        f"- Project ID: {draft.get('project_id')}",
        f"- Status: {draft.get('status')}",
        f"- Active analysis run ID: {draft.get('active_analysis_run_id')}",
        f"- Updated at: {draft.get('updated_at')}",
        "",
        "## Routing And Quality Metadata",
        f"- Routing niche: {profile.get('routing_domain')}",
        f"- Routing confidence: {profile.get('routing_confidence')}",
        f"- Genre: {profile.get('genre')}",
        f"- Secondary domains: {profile.get('secondary_domains')}",
        f"- Domain tags: {profile.get('domain_tags')}",
        f"- Retrieval domains: {profile.get('retrieval_domains')}",
        f"- Review lenses: {profile.get('review_lenses')}",
        f"- Routing rationale: {profile.get('routing_rationale')}",
        f"- Readiness score: {metadata.get('readiness_score')}",
        f"- Verdict: {metadata.get('verdict')}",
        f"- Editorial recommendation: {metadata.get('editorial_recommendation')}",
        "",
        "### Analysis Quality Judge",
        block_json(metadata.get("analysis_quality_judge")),
        "",
        "### Revision Quality Metrics",
        block_json(metadata.get("revision_quality_metrics")),
        "",
        "### Source Safety Metrics",
        block_json(metadata.get("source_safety_metrics")),
        "",
        "## Parser Metadata",
        f"- Persisted parse artifact available: {parser['persisted_parse_artifact_available']}",
        f"- Parser: {parser.get('parser_name')}",
        f"- Quality flags: {parser.get('parser_quality_flags')}",
        f"- Quality score: {parser.get('parser_quality_score')}",
        f"- Section map count: {parser.get('section_count')}",
        f"- Anchor map count: {parser.get('anchor_count')}",
        f"- GROBID sections count: {parser.get('grobid_sections_count')}",
        f"- GROBID references count: {parser.get('grobid_references_count')}",
        "",
        "## Summary Counts",
    ]

    for key, value in counts.items():
        lines.append(f"- {key}: {value}")

    lines.extend(["", "## Durable Revision Tasks"])
    for idx, task in enumerate(tasks, 1):
        lines.extend([
            "",
            f"### {idx}. {task.get('id')}",
            f"- Type: {task.get('task_type')}",
            f"- Severity: {task.get('severity')}",
            f"- Priority: {task.get('priority')}",
            f"- Location: {location(task)}",
            f"- Anchor: {task.get('anchor_text')}",
            f"- Problem: {task.get('problem')}",
            f"- Why it matters: {task.get('why_it_matters')}",
            f"- Suggested action: {task.get('suggested_action')}",
        ])
        sources = task.get("suggested_sources") or []
        if sources:
            lines.append("- Suggested sources:")
            for source in sources:
                lines.append(f"  - {source.get('title') or source.get('document_title')} ({source.get('source')}, similarity={source.get('similarity') or source.get('relevance_score')})")

    meta_reviews = payload.get("meta_reviews") or []
    if meta_reviews:
        lines.extend(["", "## Meta Review"])
        lines.append(block_json(meta_reviews[0]))

    reviewer_outputs = payload.get("reviewer_panel_outputs") or []
    if reviewer_outputs:
        lines.extend(["", "## Reviewer Panel Outputs"])
        for reviewer in reviewer_outputs:
            lines.extend([
                "",
                f"### {reviewer.get('reviewer_id') or reviewer.get('persona') or reviewer.get('id')}",
                block_json(reviewer),
            ])

    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export a Noesis draft analysis as JSON and Markdown.")
    parser.add_argument(
        "--draft-id",
        help="Export a specific draft instead of the latest analyzed draft.",
    )
    parser.add_argument(
        "--no-latest-alias",
        action="store_true",
        help="Do not update exports/latest_draft_analysis.{json,md}.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    client = get_supabase_client()
    draft = draft_by_id(client, args.draft_id) if args.draft_id else latest_analyzed_draft(client)
    draft_id = draft["id"]
    project_id = draft["project_id"]
    analysis_run_id = draft.get("active_analysis_run_id")
    analysis = sanitize_analysis_row_for_export(
        latest_analysis_row(client, draft_id, analysis_run_id)
    )
    metadata = analysis.get("analysis_metadata") or {}
    profile = metadata.get("manuscript_profile") or {}

    parse_artifacts = safe_select(client, "draft_parse_artifacts", draft_id=draft_id)
    parse_artifact = parse_artifacts[0] if parse_artifacts else {}
    durable_revision_tasks = select_related(client, "draft_revision_tasks", draft_id, analysis_run_id)
    project_documents = safe_select(client, "documents", project_id=project_id)
    literature_summary = project_literature_summary(project_documents, profile)

    payload = {
        "export_metadata": {
            "generated_at": dt.datetime.utcnow().isoformat() + "Z",
            "source": "noesis_backend_active_analysis_run",
            "latest_analyzed_draft_id": draft_id,
            "analysis_row_id": analysis.get("id"),
            "active_analysis_run_id": analysis_run_id,
        },
        "draft": draft,
        "analysis": analysis,
        "analysis_run": safe_select(client, "draft_analysis_runs", id=analysis_run_id)[0] if analysis_run_id else {},
        "parser_metadata": parser_metrics(parse_artifact, analysis),
        "durable_revision_tasks": durable_revision_tasks,
        "claims": select_related(client, "draft_claims", draft_id, analysis_run_id),
        "coverage_gaps": select_related(client, "coverage_gaps", draft_id, analysis_run_id),
        "reviewer_feedback": select_related(client, "reviewer_feedback", draft_id, analysis_run_id),
        "reviewer_panel_outputs": select_related(client, "reviewer_panel_outputs", draft_id, analysis_run_id),
        "meta_reviews": select_related(client, "meta_reviews", draft_id, analysis_run_id),
        "citation_suggestions": select_related(client, "citation_suggestions", draft_id, analysis_run_id),
        "project_literature_summary": literature_summary,
    }
    payload["summary_counts"] = {
        "durable_revision_tasks": table_count(payload["durable_revision_tasks"]),
        "claims": table_count(payload["claims"]),
        "coverage_gaps": table_count(payload["coverage_gaps"]),
        "reviewer_feedback": table_count(payload["reviewer_feedback"]),
        "reviewer_panel_outputs": table_count(payload["reviewer_panel_outputs"]),
        "meta_reviews": table_count(payload["meta_reviews"]),
        "citation_suggestions": table_count(payload["citation_suggestions"]),
        "project_literature_documents_total": literature_summary["total_documents"],
        "project_literature_titles_included": literature_summary["included_relevant_title_count"],
        "project_literature_documents_omitted_from_export": literature_summary["excluded_from_export_count"],
        "pruned_sources": len((analysis.get("analysis_metadata") or {}).get("pruned_sources") or []),
    }

    EXPORT_DIR.mkdir(exist_ok=True)
    stem = clean_filename(f"{draft.get('title') or 'latest'}_{draft_id[:8]}")
    json_path = EXPORT_DIR / f"{stem}_analysis.json"
    md_path = EXPORT_DIR / f"{stem}_analysis.md"
    latest_json_path = EXPORT_DIR / "latest_draft_analysis.json"
    latest_md_path = EXPORT_DIR / "latest_draft_analysis.md"

    json_text = json.dumps(payload, indent=2, ensure_ascii=False, default=str)
    md_text = build_markdown(payload)
    outputs = [(json_path, json_text), (md_path, md_text)]
    if not args.no_latest_alias:
        outputs.extend([(latest_json_path, json_text), (latest_md_path, md_text)])

    for path, text in outputs:
        path.write_text(text)

    print(json.dumps({
        "draft_id": draft_id,
        "title": draft.get("title"),
        "updated_at": draft.get("updated_at"),
        "analysis_run_id": analysis_run_id,
        "json_path": str(json_path),
        "markdown_path": str(md_path),
        "latest_json_path": str(latest_json_path),
        "latest_markdown_path": str(latest_md_path),
        "summary_counts": payload["summary_counts"],
        "routing_domain": ((analysis.get("analysis_metadata") or {}).get("manuscript_profile") or {}).get("routing_domain"),
    }, indent=2))


if __name__ == "__main__":
    main()

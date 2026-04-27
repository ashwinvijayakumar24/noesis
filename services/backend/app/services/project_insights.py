"""
Project insights analysis service.

Builds a cross-paper literature map from analyzed project documents.
"""

from collections import Counter
import json
import re
from typing import Any, Dict, List, Optional

from app.core.openai_client import get_completion_params, get_openai_client
from app.services.retry_utils import retry_openai

VALID_GAP_CATEGORIES = {"methodological", "population", "theoretical", "temporal"}


@retry_openai
def _create_chat_completion(**kwargs):
    client = get_openai_client()
    return client.chat.completions.create(**kwargs)

INSIGHTS_SYSTEM_PROMPT = """You are an expert research analyst producing a literature map for a research project.

Return ONLY valid JSON with this structure:
{
  "summary": "2-3 sentence synthesis of the evidence base",
  "key_insight_details": [
    {
      "statement": "A concrete, evidence-grounded takeaway",
      "source_papers": ["Exact Paper Title 1", "Exact Paper Title 2"],
      "rationale": "Why the cited papers support this statement"
    }
  ],
  "key_insights": [
    "Same insight statements as plain strings for backwards compatibility"
  ],
  "research_gaps": [
    {
      "category": "methodological" | "population" | "theoretical" | "temporal",
      "title": "Short gap title",
      "description": "Specific description of the missing evidence",
      "supporting_evidence": ["Evidence drawn from the papers"],
      "suggested_directions": ["Actionable next research step"],
      "source_papers": ["Exact Paper Title 1", "Exact Paper Title 2"]
    }
  ],
  "common_themes": [
    {
      "theme": "Theme name",
      "frequency": 2,
      "description": "How this theme appears across papers",
      "paper_titles": ["Exact Paper Title 1", "Exact Paper Title 2"],
      "source_papers": ["Exact Paper Title 1", "Exact Paper Title 2"]
    }
  ],
  "methodological_patterns": [
    {
      "methodology": "Method name",
      "usage_count": 2,
      "description": "How the method is used across papers",
      "variations": ["Variation A"],
      "source_papers": ["Exact Paper Title 1", "Exact Paper Title 2"]
    }
  ],
  "conflicting_findings": [
    {
      "topic": "Conflict topic",
      "side_a": {
        "position": "First position",
        "papers": ["Exact Paper Title 1"],
        "evidence": "Why these papers support side A"
      },
      "side_b": {
        "position": "Second position",
        "papers": ["Exact Paper Title 2"],
        "evidence": "Why these papers support side B"
      },
      "resolution": "Most plausible explanation for the disagreement",
      "source_papers": ["Exact Paper Title 1", "Exact Paper Title 2"]
    }
  ],
  "timeline": [
    {
      "period": "Time period",
      "development": "What changed",
      "papers": ["Exact Paper Title 1"]
    }
  ],
  "citation_patterns": [
    {
      "cited_work": "Frequently cited work",
      "frequency": 2,
      "context": "Why it matters",
      "papers_citing": ["Exact Paper Title 1"]
    }
  ]
}

Rules:
1. Every key insight, gap, theme, methodology pattern, and conflict must cite supporting papers using exact titles from the provided context.
2. Only identify claims that are clearly grounded in the evidence provided.
3. Common themes and methodological patterns should appear in at least 2 papers when possible.
4. If a section has no grounded items, return [].
5. Do not invent papers, methods, venues, or findings.
"""


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _normalize_text_list(items: Any) -> List[str]:
    normalized: List[str] = []
    for item in _safe_list(items):
        if item is None:
            continue
        text = str(item).strip()
        if text:
            normalized.append(text)
    return normalized


def _extract_year(*candidates: Any) -> Optional[int]:
    for candidate in candidates:
        if candidate is None:
            continue
        if isinstance(candidate, int):
            if 1900 <= candidate <= 2100:
                return candidate
            continue
        match = re.search(r"\b(19|20)\d{2}\b", str(candidate))
        if match:
            return int(match.group(0))
    return None


def _join_bullets(title: str, items: List[str]) -> str:
    if not items:
        return ""
    return f"{title}:\n" + "\n".join(f"- {item}" for item in items)


def _top_counter_items(counter: Counter, limit: int = 4) -> List[Dict[str, Any]]:
    return [{"label": label, "count": count} for label, count in counter.most_common(limit)]


def _build_coverage_snapshot(document_analyses: List[Dict[str, Any]]) -> Dict[str, Any]:
    years: List[int] = []
    method_counter: Counter = Counter()
    venue_counter: Counter = Counter()
    context_counter: Counter = Counter()

    for doc in document_analyses:
        analysis = doc.get("analysis") or {}
        metadata = doc.get("metadata") or {}
        citation_metadata = analysis.get("citation_metadata") or {}
        year = _extract_year(
            citation_metadata.get("year"),
            metadata.get("year"),
            analysis.get("publication_year"),
        )
        if year:
            years.append(year)

        for method in _safe_list(doc.get("structured_methods")):
            method_name = (method.get("method_name") or "").strip()
            method_type = (method.get("method_type") or "").strip()
            label = method_name or method_type
            if label:
                method_counter[label] += 1

        venue = (
            citation_metadata.get("venue")
            or citation_metadata.get("journal")
            or citation_metadata.get("booktitle")
            or metadata.get("journal")
            or metadata.get("venue")
        )
        if venue:
            venue_counter[str(venue).strip()] += 1

        contexts = []
        contexts.extend(_safe_list(metadata.get("fields_of_study")))
        contexts.extend(_safe_list(analysis.get("domains")))
        contexts.extend(_safe_list(analysis.get("study_contexts")))
        for context in contexts:
            label = str(context).strip()
            if label:
                context_counter[label] += 1

    return {
        "paper_count": len(document_analyses),
        "year_range": {
            "min": min(years) if years else None,
            "max": max(years) if years else None,
        },
        "top_methods": _top_counter_items(method_counter),
        "top_venues": _top_counter_items(venue_counter),
        "top_contexts": _top_counter_items(context_counter),
    }


def _fetch_structured_support(document_id: str) -> Dict[str, Any]:
    from app.core.supabase_client import supabase

    claims: List[str] = []
    methods: List[Dict[str, Any]] = []
    findings: List[str] = []
    chunk_excerpts: List[str] = []

    try:
        claims_res = (
            supabase.table("document_claims")
            .select("claim_text, claim_type, importance_score")
            .eq("document_id", document_id)
            .order("importance_score", desc=True)
            .limit(8)
            .execute()
        )
        claims = [
            f"{row['claim_text']} [{row.get('claim_type', 'claim')}]"
            for row in (claims_res.data or [])
            if row.get("claim_text")
        ]

        methods_res = (
            supabase.table("document_methods")
            .select("method_name, method_type, description, datasets_used, evaluation_metrics")
            .eq("document_id", document_id)
            .limit(8)
            .execute()
        )
        methods = methods_res.data or []

        findings_res = (
            supabase.table("document_findings")
            .select("finding_text, finding_type, metrics, comparison_baseline, confidence_score")
            .eq("document_id", document_id)
            .order("confidence_score", desc=True)
            .limit(8)
            .execute()
        )
        for row in findings_res.data or []:
            if not row.get("finding_text"):
                continue
            finding = row["finding_text"]
            if row.get("metrics"):
                finding += f" (Metrics: {row['metrics']})"
            if row.get("comparison_baseline"):
                finding += f" vs. {row['comparison_baseline']}"
            findings.append(finding)

        chunks_res = (
            supabase.table("document_chunks")
            .select("content, chunk_index")
            .eq("document_id", document_id)
            .order("chunk_index")
            .limit(5)
            .execute()
        )
        for row in chunks_res.data or []:
            content = (row.get("content") or "").strip()
            if content:
                chunk_excerpts.append(content[:800])
    except Exception as exc:
        print(f"[INSIGHTS] Warning: failed to fetch structured support for {document_id}: {exc}")

    return {
        "claims": claims,
        "methods": methods,
        "findings": findings,
        "chunk_excerpts": chunk_excerpts,
    }


def _format_method(method: Dict[str, Any]) -> str:
    method_name = (method.get("method_name") or "").strip()
    method_type = (method.get("method_type") or "").strip()
    description = (method.get("description") or "").strip()
    datasets = _normalize_text_list(method.get("datasets_used"))
    metrics = _normalize_text_list(method.get("evaluation_metrics"))

    parts = [part for part in [method_name or method_type, f"Type: {method_type}" if method_name and method_type else None] if part]
    if description:
        parts.append(description)
    if datasets:
        parts.append(f"Datasets: {', '.join(datasets[:3])}")
    if metrics:
        parts.append(f"Metrics: {', '.join(metrics[:3])}")
    return " | ".join(parts)


def _build_paper_context(index: int, doc: Dict[str, Any]) -> str:
    title = doc.get("title", f"Document {index}")
    analysis = doc.get("analysis") or {}
    citation_metadata = analysis.get("citation_metadata") or {}
    metadata = doc.get("metadata") or {}

    structured_claims = _normalize_text_list(doc.get("structured_claims"))
    structured_findings = _normalize_text_list(doc.get("structured_findings"))
    structured_methods = [_format_method(method) for method in _safe_list(doc.get("structured_methods")) if _format_method(method)]
    chunk_excerpts = _normalize_text_list(doc.get("chunk_excerpts"))

    fallback_methods = []
    methodology = analysis.get("methodology") or {}
    if methodology.get("approach"):
        fallback_methods.append(f"Approach: {methodology['approach']}")
    if methodology.get("techniques"):
        fallback_methods.append(f"Techniques: {', '.join(_normalize_text_list(methodology.get('techniques'))[:5])}")
    if methodology.get("dataset"):
        fallback_methods.append(f"Dataset: {methodology['dataset']}")

    fallback_findings = _normalize_text_list(analysis.get("key_findings"))
    fallback_claims = _normalize_text_list(analysis.get("future_work"))[:3]

    sections = [
        f"Paper {index}: {title}",
        f"Publication Year: {_extract_year(citation_metadata.get('year'), metadata.get('year')) or 'Unknown'}",
        f"Venue/Context: {citation_metadata.get('venue') or citation_metadata.get('journal') or metadata.get('journal') or 'Unknown'}",
        _join_bullets("Structured Claims", structured_claims),
        _join_bullets("Structured Methods", structured_methods),
        _join_bullets("Structured Findings", structured_findings),
        _join_bullets("Supporting Excerpts", chunk_excerpts),
    ]

    if not structured_claims:
        sections.append(_join_bullets("Fallback Narrative Claims", fallback_claims))
    if not structured_methods:
        sections.append(_join_bullets("Fallback Method Summary", fallback_methods))
    if not structured_findings:
        sections.append(_join_bullets("Fallback Narrative Findings", fallback_findings))

    executive_summary = (analysis.get("executive_summary") or "").strip()
    if executive_summary and not (structured_claims or structured_findings):
        sections.append(f"Fallback Executive Summary:\n{executive_summary}")

    limitations = _normalize_text_list(analysis.get("limitations"))
    if limitations:
        sections.append(_join_bullets("Limitations", limitations[:4]))

    citations = []
    for citation in _safe_list(analysis.get("key_citations"))[:3]:
        title_part = citation.get("title") or "Unknown Title"
        author_part = citation.get("authors") or "Unknown"
        year_part = citation.get("year") or "N/A"
        citations.append(f"{author_part} ({year_part}): {title_part}")
    if citations:
        sections.append(_join_bullets("Frequently Referenced Works", citations))

    return "\n\n".join(section for section in sections if section)


def analyze_project_insights(document_analyses: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not document_analyses:
        raise ValueError("No document analyses provided")

    enriched_docs: List[Dict[str, Any]] = []
    for doc in document_analyses:
        enriched_doc = dict(doc)
        support = _fetch_structured_support(doc["id"]) if doc.get("id") else {
            "claims": [],
            "methods": [],
            "findings": [],
            "chunk_excerpts": [],
        }
        enriched_doc["structured_claims"] = support["claims"]
        enriched_doc["structured_methods"] = support["methods"]
        enriched_doc["structured_findings"] = support["findings"]
        enriched_doc["chunk_excerpts"] = support["chunk_excerpts"]
        enriched_docs.append(enriched_doc)

    papers_context = [_build_paper_context(index, doc) for index, doc in enumerate(enriched_docs, start=1)]
    full_context = "\n\n" + ("\n\n" + ("=" * 80) + "\n\n").join(papers_context)

    response = _create_chat_completion(
        model="gpt-5.2-chat-latest",
        messages=[
            {"role": "system", "content": INSIGHTS_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Analyze these {len(enriched_docs)} research papers and identify cross-paper insights:\n{full_context}",
            },
        ],
        max_completion_tokens=3000,
        **get_completion_params(),
    )

    insights_json = (response.choices[0].message.content or "").strip()
    if insights_json.startswith("```"):
        insights_json = re.sub(r"^```(?:json)?\s*\n?", "", insights_json)
        insights_json = re.sub(r"\n?```\s*$", "", insights_json).strip()

    insights = json.loads(insights_json)
    insights["coverage_snapshot"] = _build_coverage_snapshot(enriched_docs)
    insights["analysis_metadata"] = {
        "num_papers_analyzed": len(enriched_docs),
        "model": "gpt-5.2-chat-latest",
        "enhanced_with_langgraph": True,
        "timestamp": None,
    }

    validate_insights(insights)
    return insights


def _normalize_source_papers(item: Dict[str, Any]) -> None:
    item["source_papers"] = _normalize_text_list(item.get("source_papers"))


def validate_insights(insights: Dict[str, Any]) -> None:
    required_fields = [
        "research_gaps",
        "common_themes",
        "methodological_patterns",
        "conflicting_findings",
        "key_insights",
        "summary",
    ]

    for field in required_fields:
        if field not in insights:
            print(f"[INSIGHTS] Warning: missing field '{field}', defaulting to empty")
            insights[field] = "" if field == "summary" else []

    insights.setdefault("timeline", [])
    insights.setdefault("citation_patterns", [])
    insights.setdefault("coverage_snapshot", {
        "paper_count": 0,
        "year_range": {"min": None, "max": None},
        "top_methods": [],
        "top_venues": [],
        "top_contexts": [],
    })
    insights.setdefault("key_insight_details", [])

    if insights.get("research_gaps"):
        for gap in insights["research_gaps"]:
            gap.setdefault("category", "methodological")
            gap.setdefault("title", "")
            gap.setdefault("description", "")
            gap["supporting_evidence"] = _normalize_text_list(gap.get("supporting_evidence"))
            gap["suggested_directions"] = _normalize_text_list(gap.get("suggested_directions"))
            _normalize_source_papers(gap)
            if gap["category"] not in VALID_GAP_CATEGORIES:
                print(f"[INSIGHTS] Warning: unknown gap category '{gap['category']}', normalising to 'methodological'")
                gap["category"] = "methodological"

    if insights.get("common_themes"):
        for theme in insights["common_themes"]:
            theme.setdefault("theme", "")
            theme.setdefault("frequency", 1)
            theme.setdefault("description", "")
            theme["paper_titles"] = _normalize_text_list(theme.get("paper_titles"))
            _normalize_source_papers(theme)

    if insights.get("methodological_patterns"):
        for pattern in insights["methodological_patterns"]:
            pattern.setdefault("methodology", "")
            pattern.setdefault("usage_count", 1)
            pattern.setdefault("description", "")
            pattern["variations"] = _normalize_text_list(pattern.get("variations"))
            _normalize_source_papers(pattern)

    if insights.get("conflicting_findings"):
        for conflict in insights["conflicting_findings"]:
            conflict.setdefault("topic", "")
            conflict.setdefault("resolution", "")
            _normalize_source_papers(conflict)
            for side_key in ("side_a", "side_b"):
                side = conflict.setdefault(side_key, {})
                side.setdefault("position", "")
                side.setdefault("evidence", "")
                side["papers"] = _normalize_text_list(side.get("papers"))

    normalized_details = []
    for detail in _safe_list(insights.get("key_insight_details")):
        normalized_detail = {
            "statement": str(detail.get("statement") or "").strip(),
            "source_papers": _normalize_text_list(detail.get("source_papers")),
            "rationale": str(detail.get("rationale") or "").strip(),
        }
        if normalized_detail["statement"]:
            normalized_details.append(normalized_detail)
    insights["key_insight_details"] = normalized_details

    if not _safe_list(insights.get("key_insights")) and normalized_details:
        insights["key_insights"] = [detail["statement"] for detail in normalized_details]
    else:
        insights["key_insights"] = _normalize_text_list(insights.get("key_insights"))

    coverage_snapshot = insights.get("coverage_snapshot") or {}
    coverage_snapshot.setdefault("paper_count", 0)
    coverage_snapshot.setdefault("year_range", {"min": None, "max": None})
    coverage_snapshot["top_methods"] = _safe_list(coverage_snapshot.get("top_methods"))
    coverage_snapshot["top_venues"] = _safe_list(coverage_snapshot.get("top_venues"))
    coverage_snapshot["top_contexts"] = _safe_list(coverage_snapshot.get("top_contexts"))
    insights["coverage_snapshot"] = coverage_snapshot

    print(
        f"[INSIGHTS] Validation passed. Found {len(insights.get('research_gaps', []))} gaps, "
        f"{len(insights.get('common_themes', []))} themes"
    )

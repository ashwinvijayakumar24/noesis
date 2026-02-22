"""
Coverage Gap Detection Service

Identifies gaps in literature coverage relative to draft content by:
- Comparing draft topics against project literature
- Identifying missing seminal papers
- Detecting methodology and theoretical framework gaps
- Generating prioritized gap reports with recommendations

Requirements: 4.1, 4.2, 4.3, 4.4, 4.5
"""

import json
import time
from typing import Dict, Any, List, Optional
from app.core.config import settings
from app.core.supabase_client import supabase
from app.core.logging_config import get_logger
from app.core.openai_client import get_openai_client, get_completion_params
import datetime

logger = get_logger(__name__)

# Initialize OpenAI client
client = get_openai_client()


# ============================================
# AI Prompts for Gap Detection
# ============================================

COVERAGE_ANALYSIS_PROMPT = """You are an expert academic reviewer analyzing research draft coverage.

Analyze this research draft and identify gaps in literature coverage. Respond with ONLY valid JSON.

Return this exact structure:
{
  "research_areas": [
    {
      "area": "Specific research area or topic",
      "coverage_level": "comprehensive|partial|minimal|absent",
      "key_topics": ["topic1", "topic2"]
    }
  ],
  "identified_gaps": [
    {
      "gap_type": "missing_seminal|methodology_gap|theoretical_gap",
      "description": "Detailed description of the gap",
      "priority": "high|medium|low",
      "reasoning": "Why this gap is important"
    }
  ],
  "methodological_assessment": {
    "approaches_covered": ["approach1", "approach2"],
    "missing_approaches": ["approach1", "approach2"],
    "framework_gaps": ["gap1", "gap2"]
  }
}

Gap Types:
- **missing_seminal**: Key foundational papers in the field not cited
- **methodology_gap**: Important methodological approaches not discussed or cited
- **theoretical_gap**: Relevant theoretical frameworks or models not addressed

Priority Levels:
- **high**: Critical gap that significantly weakens the work
- **medium**: Important gap that should be addressed for completeness
- **low**: Minor gap, optional but beneficial to address

Guidelines:
- Consider what a peer reviewer would flag
- Identify patterns in what's cited vs. what's discussed
- Look for methodologies mentioned but not properly grounded in literature
- Identify theoretical claims without theoretical foundation citations
- Be specific about what's missing and why it matters
"""


# ============================================
# Coverage Gap Detection
# ============================================

async def analyze_literature_coverage(
    draft_id: str,
    project_id: str
) -> Dict[str, Any]:
    """
    Analyze literature coverage gaps for a draft.

    Compares draft content against project's literature database to identify:
    - Missing seminal papers
    - Uncovered methodological approaches
    - Theoretical framework gaps

    Args:
        draft_id: Draft identifier
        project_id: Project identifier

    Returns:
        Coverage analysis with identified gaps

    Validates: Requirement 4.1 - Identify research areas covered
    """
    try:
        logger.info(f"Starting coverage analysis for draft_id={draft_id}")

        # 1. Fetch draft and its analysis
        draft_response = supabase.table("drafts").select("*").eq("id", draft_id).single().execute()

        if not draft_response.data:
            raise ValueError(f"Draft not found: {draft_id}")

        draft = draft_response.data

        # 2. Fetch draft text
        file_url = draft.get("file_url")
        if not file_url:
            raise ValueError("Draft has no file URL")

        # Download draft
        path_parts = file_url.split("/drafts/")
        if len(path_parts) < 2:
            raise ValueError(f"Invalid file URL: {file_url}")

        storage_path = path_parts[1]
        file_bytes = supabase.storage.from_("drafts").download(storage_path)

        # Extract text
        from app.services.draft_processing import extract_text

        file_type = draft.get("file_type", "pdf")
        extracted_data = await extract_text(file_bytes, file_type)
        draft_text = extracted_data["full_text"]

        # 3. Use AI to identify coverage and gaps
        coverage_analysis = await detect_coverage_gaps(draft_text)

        # 4. Cross-reference with project literature
        literature_comparison = await compare_with_literature_database(
            coverage_analysis,
            project_id
        )

        # 5. Combine results
        result = {
            **coverage_analysis,
            **literature_comparison,
            "draft_id": draft_id,
            "project_id": project_id
        }

        logger.info(f"Coverage analysis completed for draft_id={draft_id}")

        return result

    except Exception as e:
        logger.error(f"Coverage analysis failed: {str(e)}")
        raise


async def detect_coverage_gaps(draft_text: str) -> Dict[str, Any]:
    """
    Use AI to detect coverage gaps in draft.

    Args:
        draft_text: Full text of research draft

    Returns:
        Coverage analysis with identified gaps

    Validates: Requirements 4.1, 4.2, 4.4
    """
    if not client:
        raise ValueError("OpenAI API key not configured")

    start_time = time.time()

    try:
        logger.info(f"Detecting coverage gaps (text length: {len(draft_text)} chars)")

        # Analyze first 8000 characters (captures most important content)
        analysis_text = draft_text[:8000]

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": COVERAGE_ANALYSIS_PROMPT},
                {
                    "role": "user",
                    "content": f"Analyze this research draft for literature coverage gaps:\n\n{analysis_text}"
                }
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
            max_tokens=2000,
            **get_completion_params()  # Enable zero data retention
        )

        coverage_json = response.choices[0].message.content
        coverage_analysis = json.loads(coverage_json)

        processing_time = time.time() - start_time
        logger.info(f"Coverage gap detection completed in {processing_time:.2f}s")

        return coverage_analysis

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse coverage analysis JSON: {e}")
        raise Exception(f"Coverage analysis returned invalid JSON: {e}")

    except Exception as e:
        logger.error(f"Coverage gap detection failed: {e}")
        raise


async def compare_with_literature_database(
    coverage_analysis: Dict[str, Any],
    project_id: str
) -> Dict[str, Any]:
    """
    Compare identified gaps against project's literature database.

    Enhanced to use:
    - Project insights (known research gaps, methodological patterns, conflicting findings)
    - Document methods table (methodology comparison)
    - Document findings table (baseline comparisons)
    - Document claims table (claim-level coverage)

    Args:
        coverage_analysis: Initial coverage analysis from AI
        project_id: Project to search within

    Returns:
        Enhanced analysis with literature database insights

    Validates: Requirement 4.2 - Identify missing seminal papers
    """
    try:
        # 1. Fetch project insights (research gaps, methodological patterns, conflicting findings)
        project_response = supabase.table("projects")\
            .select("insights, insights_status")\
            .eq("id", project_id)\
            .single()\
            .execute()

        project_insights = {}
        if project_response.data and project_response.data.get("insights"):
            project_insights = project_response.data["insights"]
            logger.info(
                f"Loaded project insights: "
                f"{len(project_insights.get('research_gaps', []))} known gaps, "
                f"{len(project_insights.get('methodological_patterns', []))} methodological patterns"
            )

        # 2. Fetch document methods (methodology comparison)
        methods_response = supabase.table("document_methods")\
            .select("method_name, method_type, description, datasets_used, evaluation_metrics")\
            .eq("project_id", project_id)\
            .execute()

        covered_methods = methods_response.data or []
        covered_method_names = {m["method_name"].lower() for m in covered_methods}
        covered_datasets = set()
        covered_metrics = set()

        for method in covered_methods:
            if method.get("datasets_used"):
                covered_datasets.update(method["datasets_used"])
            if method.get("evaluation_metrics"):
                covered_metrics.update(method["evaluation_metrics"])

        logger.info(
            f"Found {len(covered_methods)} methods, "
            f"{len(covered_datasets)} datasets, "
            f"{len(covered_metrics)} metrics in project"
        )

        # 3. Fetch document findings (baseline comparisons)
        findings_response = supabase.table("document_findings")\
            .select("finding_text, metrics, comparison_baseline, improvement_over_baseline")\
            .eq("project_id", project_id)\
            .execute()

        covered_findings = findings_response.data or []
        baseline_comparisons = {
            f.get("comparison_baseline", "").lower()
            for f in covered_findings
            if f.get("comparison_baseline")
        }

        logger.info(
            f"Found {len(covered_findings)} findings, "
            f"{len(baseline_comparisons)} baseline comparisons"
        )

        # 4. Fetch all documents for topic coverage
        docs_response = supabase.table("documents")\
            .select("id, title, analysis")\
            .eq("project_id", project_id)\
            .eq("status", "analyzed")\
            .execute()

        documents = docs_response.data or []

        # Extract research areas from documents
        covered_topics = set()
        covered_methodologies = set()

        for doc in documents:
            analysis = doc.get("analysis", {})

            # Extract topics from key findings
            findings = analysis.get("key_findings", [])
            for finding in findings:
                covered_topics.add(finding[:50])  # First 50 chars as topic proxy

            # Extract methodologies
            methodology = analysis.get("methodology", {})
            techniques = methodology.get("techniques", [])
            covered_methodologies.update(techniques)

        # 5. Enhance gaps with literature availability and cross-references
        identified_gaps = coverage_analysis.get("identified_gaps", [])

        for gap in identified_gaps:
            gap["has_relevant_literature"] = False
            gap["relevant_methods"] = []
            gap["related_insights"] = []
            gap["missing_baselines"] = []

            gap_desc = gap.get("description", "").lower()
            gap_type = gap.get("gap_type", "")

            # Check topic coverage
            for topic in covered_topics:
                if any(word in gap_desc for word in topic.lower().split()[:3]):
                    gap["has_relevant_literature"] = True
                    gap["note"] = "Relevant literature available in project database"
                    break

            # Check methodology gaps against document_methods
            if gap_type == "methodology_gap":
                # Extract mentioned methods from gap description
                for method in covered_method_names:
                    if method in gap_desc:
                        gap["relevant_methods"].append({
                            "method_name": method,
                            "note": "Method discussed in literature but not cited in draft"
                        })
                        gap["has_relevant_literature"] = True

            # Cross-reference with project insights research gaps
            if project_insights.get("research_gaps"):
                for insight_gap in project_insights["research_gaps"]:
                    insight_title = insight_gap.get("title", "").lower()
                    insight_desc = insight_gap.get("description", "").lower()

                    # Check for overlap
                    if any(word in gap_desc for word in insight_title.split()[:3]):
                        gap["related_insights"].append({
                            "source": "project_insights",
                            "title": insight_gap.get("title"),
                            "description": insight_gap.get("description"),
                            "supporting_evidence": insight_gap.get("supporting_evidence", [])
                        })

            # Check for missing baseline comparisons
            if gap_type == "methodology_gap":
                # Identify baselines mentioned in gap but not in literature
                common_baselines = ["lstm", "bert", "transformer", "svm", "random forest", "baseline"]
                for baseline in common_baselines:
                    if baseline in gap_desc and baseline not in baseline_comparisons:
                        gap["missing_baselines"].append({
                            "baseline": baseline,
                            "note": "Baseline comparison expected but not found in literature"
                        })

        return {
            "literature_database_size": len(documents),
            "covered_methodologies": list(covered_methodologies),
            "covered_methods": list(covered_method_names),
            "covered_datasets": list(covered_datasets),
            "covered_metrics": list(covered_metrics),
            "baseline_comparisons": list(baseline_comparisons),
            "project_insights_available": bool(project_insights),
            "known_research_gaps": len(project_insights.get("research_gaps", [])),
            "gap_analysis_enhanced": True
        }

    except Exception as e:
        logger.error(f"Literature database comparison failed: {e}")
        return {}


# ============================================
# Gap Remediation Suggestions
# ============================================

async def suggest_papers_for_gaps(
    gaps: List[Dict[str, Any]],
    project_id: str,
    max_suggestions_per_gap: int = 3
) -> List[Dict[str, Any]]:
    """
    Suggest specific papers to address identified gaps.

    Uses semantic search to find relevant papers from project literature.

    Args:
        gaps: List of identified coverage gaps
        project_id: Project identifier
        max_suggestions_per_gap: Maximum suggestions per gap

    Returns:
        Gaps enhanced with paper suggestions

    Validates: Requirement 4.3 - Suggest specific papers for gaps
    """
    try:
        from app.services.rag_ingest import embed_chunks

        for gap in gaps:
            gap_description = gap.get("description", "")

            if not gap_description:
                continue

            # Embed the gap description
            embeddings = embed_chunks([gap_description])

            if not embeddings:
                logger.warning(f"Failed to embed gap description")
                continue

            gap_embedding = embeddings[0].embedding

            # Search for relevant documents
            search_results = supabase.rpc(
                "match_document_chunks",
                {
                    "query_embedding": gap_embedding,
                    "proj_id": project_id,  # Fixed: parameter name is proj_id, not p_project_id
                    "match_count": max_suggestions_per_gap * 2  # Get extra for deduplication
                }
            ).execute()

            if not search_results.data:
                gap["suggested_papers"] = []
                continue

            # Get unique documents
            document_ids = list(set([r["document_id"] for r in search_results.data]))

            # Fetch document details
            suggested_papers = []
            for doc_id in document_ids[:max_suggestions_per_gap]:
                doc_response = supabase.table("documents").select("*").eq("id", doc_id).single().execute()

                if doc_response.data:
                    document = doc_response.data
                    analysis = document.get("analysis", {})
                    citation_metadata = analysis.get("citation_metadata", {})

                    # Get similarity score
                    similarity = max([
                        r["similarity"]
                        for r in search_results.data
                        if r["document_id"] == doc_id
                    ])

                    paper = {
                        "document_id": doc_id,
                        "title": document.get("title", "Unknown"),
                        "authors": citation_metadata.get("all_authors", []),
                        "year": citation_metadata.get("year", "Unknown"),
                        "relevance_score": float(similarity),
                        "executive_summary": analysis.get("executive_summary", ""),
                        "key_findings": analysis.get("key_findings", [])[:2]  # Top 2 findings
                    }

                    suggested_papers.append(paper)

            gap["suggested_papers"] = suggested_papers

        logger.info(f"Generated paper suggestions for {len(gaps)} gaps")

        return gaps

    except Exception as e:
        logger.error(f"Failed to suggest papers for gaps: {e}")
        return gaps


def prioritize_gaps(gaps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Prioritize gaps by importance and urgency.

    Priority factors:
    - Gap type (missing_seminal > theoretical_gap > methodology_gap)
    - Assigned priority level
    - Availability of remediation in literature database

    Args:
        gaps: List of coverage gaps

    Returns:
        Gaps sorted by priority (highest first)

    Validates: Requirement 4.5 - Prioritized gap reports
    """
    priority_weights = {
        "high": 3,
        "medium": 2,
        "low": 1
    }

    gap_type_weights = {
        "missing_seminal": 3,
        "theoretical_gap": 2,
        "methodology_gap": 1
    }

    for gap in gaps:
        # Calculate priority score
        priority_score = priority_weights.get(gap.get("priority", "low"), 1)
        type_score = gap_type_weights.get(gap.get("gap_type", "methodology_gap"), 1)

        # Boost if we have literature to suggest
        has_suggestions = len(gap.get("suggested_papers", [])) > 0
        suggestion_bonus = 0.5 if has_suggestions else 0

        gap["priority_score"] = priority_score * type_score + suggestion_bonus

    # Sort by priority score (descending)
    gaps.sort(key=lambda x: x.get("priority_score", 0), reverse=True)

    return gaps


# ============================================
# Complete Coverage Gap Pipeline
# ============================================

async def generate_coverage_gap_report(
    draft_id: str,
    project_id: str
) -> Dict[str, Any]:
    """
    Generate comprehensive coverage gap report for a draft.

    Complete pipeline:
    1. Analyze draft for coverage gaps
    2. Compare with literature database
    3. Suggest specific papers for gaps
    4. Prioritize gaps by importance
    5. Store gaps in database

    Args:
        draft_id: Draft identifier
        project_id: Project identifier

    Returns:
        Comprehensive gap report

    Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5
    """
    try:
        logger.info(f"Generating coverage gap report for draft_id={draft_id}")

        # 1. Analyze coverage
        coverage = await analyze_literature_coverage(draft_id, project_id)

        # 2. Get identified gaps
        gaps = coverage.get("identified_gaps", [])

        if not gaps:
            logger.info("No coverage gaps identified")
            return {
                "draft_id": draft_id,
                "project_id": project_id,
                "message": "No significant coverage gaps identified",
                "gaps": []
            }

        # 3. Suggest papers for each gap
        gaps = await suggest_papers_for_gaps(gaps, project_id)

        # 4. Prioritize gaps
        gaps = prioritize_gaps(gaps)

        # 5. Store gaps in database with line positioning
        gap_records = []
        for gap in gaps:
            # Try to locate gap description in draft_text for line positioning
            description = gap.get("description", "")
            line_number = None
            char_start = None
            char_end = None
            text_snippet = None

            # Extract a key phrase from the description to search in draft
            # (descriptions are AI-generated, so we look for related claims)
            related_section = gap.get("section", "")
            if related_section and related_section in draft_text:
                section_start = draft_text.find(related_section)
                if section_start >= 0:
                    text_before = draft_text[:section_start]
                    line_number = text_before.count('\n') + 1  # 1-indexed

                    # Find line start
                    line_start_pos = draft_text.rfind('\n', 0, section_start) + 1
                    char_start = section_start - line_start_pos
                    char_end = char_start + len(related_section)

                    # Extract snippet
                    snippet_start = max(0, section_start - 50)
                    snippet_end = min(len(draft_text), section_start + len(related_section) + 50)
                    text_snippet = draft_text[snippet_start:snippet_end].strip()

            gap_record = {
                "draft_id": draft_id,
                "gap_type": gap.get("gap_type", "methodology_gap"),
                "description": description,
                "priority": gap.get("priority", "medium"),
                "suggested_papers": gap.get("suggested_papers", []),
                # Line positioning fields
                "line_number": line_number,
                "char_start": char_start,
                "char_end": char_end,
                "text_snippet": text_snippet or description[:150]  # Fallback to description
            }
            gap_records.append(gap_record)

        # Batch insert
        if gap_records:
            supabase.table("coverage_gaps").insert(gap_records).execute()

        logger.info(f"Coverage gap report generated with {len(gaps)} gaps")

        # Generate report
        report = {
            "draft_id": draft_id,
            "project_id": project_id,
            "total_gaps": len(gaps),
            "gaps_by_priority": {
                "high": len([g for g in gaps if g.get("priority") == "high"]),
                "medium": len([g for g in gaps if g.get("priority") == "medium"]),
                "low": len([g for g in gaps if g.get("priority") == "low"])
            },
            "gaps_by_type": {
                "missing_seminal": len([g for g in gaps if g.get("gap_type") == "missing_seminal"]),
                "theoretical_gap": len([g for g in gaps if g.get("gap_type") == "theoretical_gap"]),
                "methodology_gap": len([g for g in gaps if g.get("gap_type") == "methodology_gap"])
            },
            "gaps": gaps[:10],  # Top 10 prioritized gaps
            "research_areas": coverage.get("research_areas", []),
            "methodological_assessment": coverage.get("methodological_assessment", {})
        }

        return report

    except Exception as e:
        logger.error(f"Coverage gap report generation failed: {str(e)}")
        raise

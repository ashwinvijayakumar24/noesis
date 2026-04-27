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
import asyncio
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
# Semantic Similarity Utilities
# ============================================

async def compute_claim_literature_similarity(
    claim_text: str,
    project_id: str,
    top_k: int = 5
) -> List[Dict[str, Any]]:
    """
    Compute semantic similarity between a claim and project literature.

    Uses embedding cosine similarity to find the most relevant literature
    chunks that support or relate to this claim.

    Args:
        claim_text: The claim text to analyze
        project_id: Project identifier
        top_k: Number of top similar chunks to return

    Returns:
        List of literature chunks with similarity scores
    """
    try:
        from app.services.rag_ingest import embed_chunks

        # Generate embedding for claim
        embeddings = embed_chunks([claim_text])
        if not embeddings or len(embeddings) == 0:
            logger.warning(f"Failed to generate embedding for claim")
            return []

        claim_embedding = embeddings[0].embedding

        # Search for similar chunks in literature
        search_results = supabase.rpc(
            "match_document_chunks",
            {
                "query_embedding": claim_embedding,
                "proj_id": project_id,
                "match_count": top_k
            }
        ).execute()

        if not search_results.data:
            return []

        # Format results with similarity scores
        similar_chunks = []
        for result in search_results.data:
            similar_chunks.append({
                "document_id": result.get("document_id"),
                "chunk_content": result.get("content"),
                "similarity_score": float(result.get("similarity", 0)),
                "metadata": result.get("metadata", {})
            })

        return similar_chunks

    except Exception as e:
        logger.error(f"Similarity computation failed: {e}")
        return []


def categorize_citation_strength(
    similarity_score: float,
    citation_count: int,
    claim_importance: float
) -> str:
    """
    Categorize the strength of citation support for a claim.

    Args:
        similarity_score: Semantic similarity to literature (0.0 to 1.0)
        citation_count: Number of existing citations
        claim_importance: Importance score of the claim (0.0 to 1.0)

    Returns:
        Strength category: "strong", "moderate", "weak", "missing"
    """
    # High-importance claims need stronger evidence
    if claim_importance > 0.7:
        required_citations = 2
        required_similarity = 0.7
    elif claim_importance > 0.4:
        required_citations = 1
        required_similarity = 0.6
    else:
        required_citations = 1
        required_similarity = 0.5

    # Strong: Has citations AND high similarity to literature
    if citation_count >= required_citations and similarity_score >= required_similarity:
        return "strong"

    # Moderate: Has some citations OR moderate similarity
    elif citation_count >= 1 or similarity_score >= 0.6:
        return "moderate"

    # Weak: Limited support
    elif citation_count > 0 or similarity_score >= 0.4:
        return "weak"

    # Missing: No meaningful support
    else:
        return "missing"


async def enhance_claims_with_literature_mapping(
    claims: List[Dict[str, Any]],
    project_id: str
) -> List[Dict[str, Any]]:
    """
    Enhance claims with semantic similarity to literature and citation strength.

    For each claim:
    1. Compute semantic similarity to project literature
    2. Identify most relevant supporting literature
    3. Assess citation strength (strong/moderate/weak/missing)
    4. Flag unsupported claims

    Args:
        claims: List of extracted claims
        project_id: Project identifier

    Returns:
        Enhanced claims with literature mapping and citation strength
    """
    try:
        logger.info(f"Enhancing {len(claims)} claims with literature mapping")

        for claim in claims:
            claim_text = claim.get("claim_text", "")
            importance = claim.get("importance_score", 0.5)
            citation_count = len(claim.get("existing_citations", []))
            requires_citation = claim.get("requires_citation", True)

            if not claim_text or not requires_citation:
                # Skip if no text or doesn't require citation
                claim["citation_strength"] = "original_contribution"
                claim["supporting_literature"] = []
                claim["max_similarity"] = 0.0
                claim["unsupported"] = False
                continue

            # Find similar literature
            similar_chunks = await compute_claim_literature_similarity(
                claim_text,
                project_id,
                top_k=5
            )

            # Get maximum similarity score
            max_similarity = max(
                [chunk["similarity_score"] for chunk in similar_chunks],
                default=0.0
            )

            # Categorize citation strength
            citation_strength = categorize_citation_strength(
                max_similarity,
                citation_count,
                importance
            )

            # Flag as unsupported if missing or weak
            unsupported = citation_strength in ["missing", "weak"] and importance > 0.5

            # Add to claim
            claim["citation_strength"] = citation_strength
            claim["supporting_literature"] = similar_chunks
            claim["max_similarity"] = max_similarity
            claim["unsupported"] = unsupported

        # Count unsupported claims
        unsupported_count = sum(1 for c in claims if c.get("unsupported", False))
        if unsupported_count > 0:
            logger.warning(f"Found {unsupported_count} unsupported claims")

        return claims

    except Exception as e:
        logger.error(f"Literature mapping enhancement failed: {e}")
        return claims


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
    Use AI to detect coverage gaps in draft using 3-window parallel analysis.

    Runs 3 concurrent GPT calls covering intro, methods, and discussion/conclusion
    sections so no part of the paper is missed. Results are merged and deduplicated.

    Args:
        draft_text: Full text of research draft

    Returns:
        Coverage analysis with identified gaps

    Validates: Requirements 4.1, 4.2, 4.4
    """
    if not client:
        raise ValueError("OpenAI API key not configured")

    import asyncio
    start_time = time.time()

    try:
        text_len = len(draft_text)
        window_size = 8000

        logger.info(f"Detecting coverage gaps with 3-window analysis (text length: {text_len} chars)")

        # Build 3 windows: intro, methods, discussion/conclusion
        windows = [("introduction/abstract", draft_text[:window_size])]

        if text_len > window_size:
            mid_start = max(0, text_len // 2 - window_size // 2)
            windows.append(("methods/results", draft_text[mid_start:mid_start + window_size]))

        if text_len > window_size * 2:
            end_start = max(0, text_len - window_size)
            windows.append(("discussion/conclusion", draft_text[end_start:]))

        async def analyze_window(window_label: str, window_text: str) -> Dict[str, Any]:
            def _sync_call():
                response = client.chat.completions.create(
                    model="gpt-5.2-chat-latest",
                    messages=[
                        {"role": "system", "content": COVERAGE_ANALYSIS_PROMPT},
                        {
                            "role": "user",
                            "content": f"Analyze the {window_label} section of this research draft for literature coverage gaps:\n\n{window_text}"
                        }
                    ],
                    max_completion_tokens=2000,
                    **get_completion_params()
                )
                return json.loads(response.choices[0].message.content)

            return await asyncio.to_thread(_sync_call)

        # Run all windows in parallel
        results = await asyncio.gather(
            *[analyze_window(label, text) for label, text in windows],
            return_exceptions=True
        )

        # Merge and deduplicate results
        all_research_areas: list = []
        all_gaps: list = []
        all_approaches: list = []
        all_missing_approaches: list = []
        all_framework_gaps: list = []
        seen_gap_keys: set = set()
        seen_area_keys: set = set()

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning(f"Window {i} analysis failed: {result}")
                continue

            for area in result.get("research_areas", []):
                area_key = area.get("area", "")[:50].lower().strip()
                if area_key and area_key not in seen_area_keys:
                    seen_area_keys.add(area_key)
                    all_research_areas.append(area)

            for gap in result.get("identified_gaps", []):
                gap_key = gap.get("description", "")[:80].lower().strip()
                if gap_key and gap_key not in seen_gap_keys:
                    seen_gap_keys.add(gap_key)
                    all_gaps.append(gap)

            methodological = result.get("methodological_assessment", {})
            all_approaches.extend(methodological.get("approaches_covered", []))
            all_missing_approaches.extend(methodological.get("missing_approaches", []))
            all_framework_gaps.extend(methodological.get("framework_gaps", []))

        processing_time = time.time() - start_time
        logger.info(
            f"3-window coverage gap detection completed in {processing_time:.2f}s "
            f"({len(windows)} windows, {len(all_gaps)} unique gaps)"
        )

        return {
            "research_areas": all_research_areas[:10],
            "identified_gaps": all_gaps[:15],
            "methodological_assessment": {
                "approaches_covered": list(dict.fromkeys(all_approaches))[:10],
                "missing_approaches": list(dict.fromkeys(all_missing_approaches))[:10],
                "framework_gaps": list(dict.fromkeys(all_framework_gaps))[:10]
            }
        }

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
            .neq("resolution_status", "unresolved")\
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
# External Paper Fallback
# ============================================

_EXTERNAL_FALLBACK_THRESHOLD = 3   # trigger fallback if fewer local papers
_MAX_EXTERNAL_PAPERS = 5           # cap external results per gap


def _normalize_external_paper(raw: dict, source: str) -> dict:
    """Normalize SS/OA paper dict to match suggested_papers schema."""
    return {
        "title": raw.get("title", ""),
        "authors": raw.get("authors", []),
        "year": raw.get("year") or raw.get("publication_year"),
        "abstract": raw.get("abstract", ""),
        "relevance_score": raw.get("relevance_score", 0.5),
        "source": source,           # "semantic_scholar" | "open_access"
        "url": raw.get("url") or raw.get("paper_url") or raw.get("open_access_url", ""),
        "open_access_url": raw.get("open_access_url") or raw.get("pdf_url", ""),
        "citation_count": raw.get("citation_count") or raw.get("cited_by_count", 0),
        "external": True,           # flag to distinguish from local papers
    }


async def _fetch_external_papers_for_gap(
    gap_description: str,
    needed: int,
    max_external: int = _MAX_EXTERNAL_PAPERS,
) -> list:
    """Semantic Scholar first, OpenAlex cascade, deduplicate by title."""
    results: list = []
    seen_titles: set = set()

    # 1. Try Semantic Scholar (sync client — wrap in thread)
    try:
        from app.services.external_apis.semantic_scholar import SemanticScholarAPI
        ss = SemanticScholarAPI()
        raw = await asyncio.to_thread(ss.search_papers, gap_description, limit=max_external)
        for p in (raw or []):
            t = (p.get("title") or "").lower().strip()
            if t and t not in seen_titles:
                seen_titles.add(t)
                results.append(_normalize_external_paper(p, "semantic_scholar"))
    except Exception as e:
        logger.warning(f"[EXTERNAL FALLBACK] Semantic Scholar failed: {e}")

    # 2. Backfill with OpenAlex if still short
    if len(results) < needed:
        try:
            from app.services.external_apis.openalex import find_open_access_papers_for_gap
            oa_raw = await find_open_access_papers_for_gap(gap_description, max_external)
            for p in (oa_raw or []):
                t = (p.get("title") or "").lower().strip()
                if t and t not in seen_titles:
                    seen_titles.add(t)
                    results.append(_normalize_external_paper(p, "open_access"))
        except Exception as e:
            logger.warning(f"[EXTERNAL FALLBACK] OpenAlex failed: {e}")

    return results[:max_external]


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
                logger.warning(f"Failed to embed gap description, trying external fallback")
                try:
                    gap["suggested_papers"] = await _fetch_external_papers_for_gap(
                        gap_description, _EXTERNAL_FALLBACK_THRESHOLD
                    )
                except Exception:
                    gap["suggested_papers"] = []
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
                external = await _fetch_external_papers_for_gap(
                    gap_description, _EXTERNAL_FALLBACK_THRESHOLD
                )
                gap["suggested_papers"] = external
                continue

            # Get unique documents
            document_ids = list(set([r["document_id"] for r in search_results.data]))

            # Fetch document details
            suggested_papers = []
            for doc_id in document_ids[:max_suggestions_per_gap]:
                doc_response = supabase.table("documents").select("*").eq("id", doc_id).neq("resolution_status", "unresolved").single().execute()

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

            # External fallback: if local library is sparse, search SS + OpenAlex
            if len(suggested_papers) < _EXTERNAL_FALLBACK_THRESHOLD:
                try:
                    needed = _EXTERNAL_FALLBACK_THRESHOLD - len(suggested_papers)
                    external = await _fetch_external_papers_for_gap(gap_description, needed)
                    suggested_papers.extend(external)
                except Exception as ext_err:
                    logger.warning(f"[EXTERNAL FALLBACK] Failed for gap, using local only: {ext_err}")

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
# Embedding-Based Real Gap Detection
# ============================================

async def analyze_coverage_with_embeddings(
    draft_id: str,
    project_id: str,
    similarity_threshold: float = 0.65,
) -> List[Dict[str, Any]]:
    """
    Detect REAL coverage gaps by comparing draft sections against project literature.

    Unlike GPT-only gap detection, this compares actual embeddings so we detect
    sections with no matching literature in the project (instead of hallucinating gaps).

    Steps:
    1. Fetch draft structure (section headings + first paragraph each)
    2. Embed each section
    3. Compare against document_chunks embeddings via pgvector
    4. Sections with max similarity < threshold = real gap (no matching literature)
    5. For high-priority real gaps, query OpenAlex for open-access external papers

    Args:
        draft_id: Draft identifier
        project_id: Project identifier
        similarity_threshold: Below this = no supporting literature (default 0.65)

    Returns:
        List of gap dicts with external_paper_suggestions where found
    """
    import asyncio
    from app.services.rag_ingest import embed_chunks
    from app.services.external_apis.openalex import find_open_access_papers_for_gap

    try:
        # 1. Fetch draft analysis to get section structure
        analysis_resp = supabase.table("draft_analysis")\
            .select("structure")\
            .eq("draft_id", draft_id)\
            .execute()

        if not analysis_resp.data:
            logger.warning(f"[EmbeddingGapDetection] No draft analysis for draft_id={draft_id}")
            return []

        structure = analysis_resp.data[0].get("structure", {})
        sections = structure.get("sections", [])

        if not sections:
            logger.warning("[EmbeddingGapDetection] No sections in draft structure")
            return []

        # 2. Check if project has any literature at all
        chunks_check = supabase.table("document_chunks")\
            .select("id")\
            .eq("project_id", project_id)\
            .limit(1)\
            .execute()

        if not chunks_check.data:
            logger.warning(f"[EmbeddingGapDetection] No document chunks in project {project_id}")
            return []

        # 3. Embed each section (title + content snippet)
        section_texts = []
        section_metas = []
        for section in sections:
            title = section.get("title", "")
            content = section.get("content", section.get("text", ""))
            if not title:
                continue
            # Use title + first 400 chars of content as search query
            search_text = f"{title}: {content[:400]}" if content else title
            section_texts.append(search_text)
            section_metas.append({"title": title, "type": section.get("type", "other")})

        if not section_texts:
            return []

        embeddings = embed_chunks(section_texts)
        if not embeddings or len(embeddings) != len(section_texts):
            logger.warning("[EmbeddingGapDetection] Failed to embed sections")
            return []

        # 4. For each section, find max similarity to any project chunk
        real_gaps = []

        for i, emb in enumerate(embeddings):
            section_meta = section_metas[i]
            embedding_vector = emb.embedding

            search_result = supabase.rpc(
                "match_document_chunks",
                {
                    "query_embedding": embedding_vector,
                    "proj_id": project_id,
                    "match_count": 3,
                }
            ).execute()

            if search_result.data:
                max_sim = max(float(r.get("similarity", 0)) for r in search_result.data)
            else:
                max_sim = 0.0

            if max_sim < similarity_threshold:
                # This section has no good literature match — real gap
                real_gaps.append({
                    "section_title": section_meta["title"],
                    "section_type": section_meta["type"],
                    "max_similarity": round(max_sim, 3),
                    "gap_type": "missing_literature",
                    "description": (
                        f"Section '{section_meta['title']}' has no closely matching literature "
                        f"in your project library (best match similarity: {max_sim:.0%}). "
                        f"Consider adding papers that address this topic."
                    ),
                    "severity": "critical" if max_sim < 0.40 else "major",
                    "external_paper_suggestions": [],
                })

        logger.info(
            f"[EmbeddingGapDetection] Found {len(real_gaps)} real gaps "
            f"(out of {len(sections)} sections) below threshold {similarity_threshold}"
        )

        if not real_gaps:
            return []

        # 5. For high-priority gaps, search OpenAlex for open-access papers
        async def enrich_gap_with_external_papers(gap: Dict[str, Any]) -> None:
            try:
                papers = await find_open_access_papers_for_gap(
                    gap_description=f"{gap['section_title']} {gap['description'][:200]}",
                    limit=3,
                )
                gap["external_paper_suggestions"] = [
                    {
                        "title": p["title"],
                        "authors": ", ".join(p["authors"][:3]) if p["authors"] else "",
                        "year": p.get("year"),
                        "open_access_url": p.get("open_access_url"),
                        "relevance": (
                            f"Open-access paper covering {gap['section_title']} "
                            f"— may help address this gap"
                        ),
                    }
                    for p in papers
                    if p.get("open_access_url")
                ]
            except Exception as ext_err:
                logger.warning(f"[EmbeddingGapDetection] External paper search failed: {ext_err}")

        # Enrich critical and major gaps only (save API calls)
        enrichment_tasks = [
            enrich_gap_with_external_papers(g)
            for g in real_gaps
            if g["severity"] in ("critical", "major")
        ]
        await asyncio.gather(*enrichment_tasks, return_exceptions=True)

        return real_gaps

    except Exception as e:
        logger.error(f"[EmbeddingGapDetection] Error: {e}")
        return []


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

        # 4b. Enrich with external papers from OpenAlex via embedding-based gap detection
        try:
            embedding_gaps = await analyze_coverage_with_embeddings(draft_id, project_id)
            for eg in embedding_gaps:
                external_papers = eg.get("external_paper_suggestions", [])
                if external_papers:
                    gaps.append({
                        "gap_type": "missing_literature",
                        "description": eg["description"],
                        "priority": "high" if eg.get("severity") == "critical" else "medium",
                        "suggested_papers": [
                            {
                                "title": p.get("title", ""),
                                "authors": p.get("authors", ""),
                                "year": p.get("year"),
                                "open_access_url": p.get("open_access_url"),
                                "source": "openalex",
                                "relevance_score": 0.8,
                            }
                            for p in external_papers
                        ],
                        "section": eg.get("section_title", ""),
                    })
            logger.info(f"[CoverageGap] Embedding detection added {len(embedding_gaps)} section gaps")
        except Exception as emb_err:
            logger.warning(f"[CoverageGap] Embedding gap detection failed (non-fatal): {emb_err}")

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

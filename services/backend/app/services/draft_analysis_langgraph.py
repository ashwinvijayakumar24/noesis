"""
Draft Analysis Service (LangGraph Version)

Integrates the LangGraph workflow into the existing draft analysis system.
This replaces the old sequential approach with an intelligent, adaptive workflow.
"""

from app.workflows.draft_analysis.graph import run_draft_analysis_workflow
from app.services.progress_publisher import publish_progress
from app.core.supabase_client import supabase
from app.core.logging_config import get_logger
import datetime
import asyncio

logger = get_logger(__name__)


async def analyze_draft_with_langgraph(
    draft_id: str,
    project_id: str,
    user_id: str,
    draft_content: str
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

    try:
        # Run the LangGraph workflow
        logger.info(f"[LangGraph Draft Analysis] Calling run_draft_analysis_workflow...")
        final_state = await run_draft_analysis_workflow(
            draft_id=draft_id,
            project_id=project_id,
            user_id=user_id,
            draft_content=draft_content,
            checkpoint_enabled=True
        )
        logger.info(f"[LangGraph Draft Analysis] Workflow completed, processing results...")

        # Extract results from final state
        structure = final_state.get("structure", {})
        claims = final_state.get("claims", [])
        claims_with_citations = final_state.get("claims_with_citations", [])
        gaps = final_state.get("coverage_gaps", [])
        feedback = final_state.get("reviewer_feedback", [])
        structural_feedback = final_state.get("structural_feedback", [])
        synthesis_report = final_state.get("synthesis_report", {})
        errors = final_state.get("errors", [])

        # Merge structural feedback into total feedback list for readiness scoring
        all_feedback = list(feedback) + list(structural_feedback)

        logger.info(
            f"[LangGraph Draft Analysis] Workflow completed: "
            f"{len(claims)} claims, {len(gaps)} gaps, "
            f"{len(feedback)} feedback + {len(structural_feedback)} structural items"
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
            citations = cwc.get("citations", [])
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
                # First pass: build display map; collect arxiv IDs for fallback lookup
                arxiv_lookup: dict = {}  # clean_arxiv_id -> doc_id
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
                            # Strip version suffix and queue for shared_papers lookup
                            arxiv_id = _re.sub(r'v\d+$', '', clean)
                            arxiv_lookup[arxiv_id] = doc["id"]
                            doc_display_map[doc["id"]] = f"arXiv:{arxiv_id}"  # safe fallback
                        else:
                            doc_display_map[doc["id"]] = title[:50]

                # Second pass: resolve arxiv IDs via shared_papers (batch)
                if arxiv_lookup:
                    try:
                        sp_res = supabase.table("shared_papers")\
                            .select("arxiv_id, title, authors, year")\
                            .in_("arxiv_id", list(arxiv_lookup.keys()))\
                            .execute()
                        for sp in (sp_res.data or []):
                            doc_id = arxiv_lookup.get(sp["arxiv_id"])
                            if not doc_id:
                                continue
                            sp_authors = sp.get("authors") or []
                            sp_year = sp.get("year")
                            sp_title = sp.get("title") or ""
                            if sp_authors:
                                first = (str(sp_authors[0]).split(",")[0]).strip()
                                author_str = f"{first} et al." if len(sp_authors) > 1 else first
                                year_clean = str(sp_year) if sp_year and str(sp_year) not in _bad_year else None
                                doc_display_map[doc_id] = f"{author_str} ({year_clean})" if year_clean else author_str
                            elif sp_title:
                                doc_display_map[doc_id] = sp_title[:50]
                    except Exception as sp_err:
                        logger.warning(f"[LangGraph Draft Analysis] shared_papers arxiv lookup failed: {sp_err}")
            except Exception as doc_err:
                logger.warning(f"[LangGraph Draft Analysis] Could not fetch doc metadata for display: {doc_err}")

        existing_analysis_res = supabase.table("draft_analysis")\
            .select("analysis, analysis_metadata")\
            .eq("draft_id", draft_id)\
            .limit(1)\
            .execute()
        existing_analysis = {}
        existing_metadata = {}
        if existing_analysis_res.data:
            existing_analysis = existing_analysis_res.data[0].get("analysis") or {}
            existing_metadata = existing_analysis_res.data[0].get("analysis_metadata") or {}

        draft_context_res = supabase.table("drafts")\
            .select("paper_type, citation_style")\
            .eq("id", draft_id)\
            .limit(1)\
            .execute()
        draft_context = draft_context_res.data[0] if draft_context_res.data else {}

        # ============================================================
        # 1. Store draft_analysis (structure and initial metadata)
        # ============================================================
        draft_analysis_data = {
            "draft_id": draft_id,
            "structure": structure,
            "word_count": structure.get("word_count", 0),
            "analysis": existing_analysis,
            "analysis_metadata": {
                **existing_metadata,
                "workflow_type": "langgraph",
                "total_claims": len(claims),
                "total_gaps": len(gaps),
                "total_feedback": len(all_feedback),
                "errors": errors,
                "timestamp": datetime.datetime.utcnow().isoformat(),
                "paper_type": draft_context.get("paper_type", existing_metadata.get("paper_type")),
                "citation_style": draft_context.get("citation_style", existing_metadata.get("citation_style")),
            },
            "created_at": datetime.datetime.utcnow().isoformat()
        }

        analysis_response = supabase.table("draft_analysis").upsert(draft_analysis_data).execute()

        if not analysis_response.data:
            logger.error("[LangGraph Draft Analysis] Failed to store draft_analysis")
            raise Exception("Failed to store draft analysis")

        # ============================================================
        # 2. Store draft_claims — delete stale rows, insert fresh
        # ============================================================
        if claims:
            supabase.table("draft_claims").delete().eq("draft_id", draft_id).execute()
            claims_data = []
            for claim in claims:
                claim_key = claim.get("claim_text", "")
                citation_info = claim_citation_map.get(claim_key)
                suggested_cits = claim_suggestions_map.get(claim_key, [])

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
                else:
                    supporting_lit = {
                        "top_match": None,
                        "suggested_citations": suggested_cits,
                    }

                claims_data.append({
                    "draft_id": draft_id,
                    "claim_text": claim["claim_text"],
                    "claim_type": claim["claim_type"],
                    "section_location": claim["section_location"],
                    "importance_score": claim["importance_score"],
                    "requires_citation": claim.get("requires_citation", True),
                    "max_similarity": citation_info["similarity"] if citation_info else 0.0,
                    "supporting_literature": supporting_lit,
                    "created_at": datetime.datetime.utcnow().isoformat()
                })

            supabase.table("draft_claims").insert(claims_data).execute()
            logger.info(f"[LangGraph Draft Analysis] Stored {len(claims)} claims (replaced stale)")

        # ============================================================
        # 3. Store coverage_gaps — delete stale rows, insert fresh
        # ============================================================
        if gaps:
            supabase.table("coverage_gaps").delete().eq("draft_id", draft_id).execute()
            _severity_map = {
                "critical": "high", "major": "high",
                "minor": "low", "high": "high", "medium": "medium", "low": "low"
            }
            gaps_data = []
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
                    "created_at": datetime.datetime.utcnow().isoformat()
                })

            insert_res = supabase.table("coverage_gaps").insert(gaps_data).execute()
            logger.info(f"[LangGraph Draft Analysis] Stored {len(gaps)} coverage gaps (replaced stale)")
            # Backfill DB-assigned IDs into in-memory gaps so enrichment step can update them
            if insert_res.data:
                for i, row in enumerate(insert_res.data):
                    if i < len(gaps):
                        gaps[i]["id"] = row.get("id")

        # ============================================================
        # 4. Store reviewer_feedback — delete all stale rows, insert fresh
        #    with full anchor/QA fields from draft_anchor_qa.py
        # ============================================================
        supabase.table("reviewer_feedback").delete().eq("draft_id", draft_id).execute()

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
                "reviewer_persona": fb.get("reviewer_persona", persona),
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

        if feedback_data:
            supabase.table("reviewer_feedback").insert(feedback_data).execute()
            logger.info(f"[LangGraph Draft Analysis] Stored {len(feedback_data)} feedback items (replaced stale)")

        # Reviewer 1 strengths — generated fresh each run (no skip guard)
        try:
            from app.services.reviewer1_feedback import generate_reviewer1_feedback
            r1_items = await generate_reviewer1_feedback(
                draft_id=draft_id,
                draft_content=draft_content,
                structure=structure,
            )
            r1_rows = [
                _fb_row(item, persona="reviewer_1")
                for item in r1_items
                if item.get("feedback_text")
            ]
            if r1_rows:
                supabase.table("reviewer_feedback").insert(r1_rows).execute()
                logger.info(f"[LangGraph Draft Analysis] Stored {len(r1_rows)} Reviewer 1 strengths")
        except Exception as r1_err:
            logger.warning(f"[LangGraph Draft Analysis] Reviewer 1 strengths failed (non-fatal): {r1_err}")

        # ============================================================
        # 5. Store citation_suggestions — delete stale, insert fresh
        # ============================================================
        supabase.table("citation_suggestions").delete().eq("draft_id", draft_id).execute()
        if claims_with_citations:
            citation_suggestions_data = []
            for claim_with_citation in claims_with_citations:
                claim = claim_with_citation.get("claim", {})
                citations = claim_with_citation.get("citations", [])
                citation_quality = claim_with_citation.get("citation_quality", "unknown")
                claim_gaps = claim_with_citation.get("gaps", [])

                for citation in citations:
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

            if citation_suggestions_data:
                try:
                    supabase.table("citation_suggestions").insert(citation_suggestions_data).execute()
                    logger.info(f"[LangGraph Draft Analysis] Stored {len(citation_suggestions_data)} citation suggestions")
                except Exception as citation_error:
                    logger.error(f"[LangGraph Draft Analysis] Failed to store citation suggestions: {citation_error}")

        # ============================================================
        # 6. Post-workflow enrichment (paper suggestions, score, action items)
        # ============================================================

        # 6a. Suggest external papers for coverage gaps
        enriched_gaps = list(gaps)
        try:
            from app.services.coverage_analysis import suggest_papers_for_gaps
            logger.info("[LangGraph Draft Analysis] Running suggest_papers_for_gaps...")
            enriched_gaps = await suggest_papers_for_gaps(list(gaps), project_id)
            # Update coverage_gaps rows with enriched suggested_papers
            for gap in enriched_gaps:
                gap_id = gap.get("id")
                enriched_papers = gap.get("suggested_papers", [])
                if gap_id and enriched_papers:
                    try:
                        supabase.table("coverage_gaps").update(
                            {"suggested_papers": enriched_papers}
                        ).eq("id", gap_id).execute()
                    except Exception:
                        pass
            logger.info(f"[LangGraph Draft Analysis] External paper suggestions applied to {len(enriched_gaps)} gaps")
        except Exception as suggestion_err:
            logger.warning(f"[LangGraph Draft Analysis] suggest_papers_for_gaps failed (non-fatal): {suggestion_err}")

        # 6b. Calculate readiness score
        readiness_result = {"readiness_score": None, "verdict": None, "score_breakdown": {}}
        try:
            from app.services.reviewer_feedback import calculate_readiness_score
            # Fetch stored claims + feedback from DB for accurate scoring (includes Phase 1 items)
            stored_claims_res = supabase.table("draft_claims").select("*").eq("draft_id", draft_id).execute()
            stored_gaps_res = supabase.table("coverage_gaps").select("*").eq("draft_id", draft_id).execute()
            stored_feedback_res = supabase.table("reviewer_feedback").select("*").eq("draft_id", draft_id).execute()

            scoring_claims = stored_claims_res.data or claims
            scoring_gaps = stored_gaps_res.data or enriched_gaps
            scoring_feedback = stored_feedback_res.data or all_feedback

            readiness_result = calculate_readiness_score(scoring_claims, scoring_gaps, scoring_feedback)
            logger.info(
                f"[LangGraph Draft Analysis] Readiness score: {readiness_result['readiness_score']} "
                f"({readiness_result['verdict']})"
            )
        except Exception as score_err:
            logger.warning(f"[LangGraph Draft Analysis] calculate_readiness_score failed (non-fatal): {score_err}")

        # 6c. Synthesize action items
        action_items: list = []
        try:
            from app.services.reviewer_feedback import synthesize_action_items
            scoring_claims = locals().get("scoring_claims", claims)
            scoring_gaps = locals().get("scoring_gaps", enriched_gaps)
            scoring_feedback = locals().get("scoring_feedback", all_feedback)
            action_items = synthesize_action_items(scoring_claims, scoring_gaps, scoring_feedback)
            logger.info(f"[LangGraph Draft Analysis] Synthesized {len(action_items)} action items")
        except Exception as action_err:
            logger.warning(f"[LangGraph Draft Analysis] synthesize_action_items failed (non-fatal): {action_err}")

        # 6d. Update draft_analysis.analysis_metadata with enriched data
        try:
            total_feedback = len(scoring_feedback) if "scoring_feedback" in locals() else len(all_feedback) + len(r1_items)
            enriched_metadata = {
                **existing_metadata,
                "workflow_type": "langgraph",
                "total_claims": len(claims),
                "total_gaps": len(gaps),
                "total_feedback": total_feedback,
                "errors": errors,
                "timestamp": datetime.datetime.utcnow().isoformat(),
                "paper_type": draft_context.get("paper_type", existing_metadata.get("paper_type")),
                "citation_style": draft_context.get("citation_style", existing_metadata.get("citation_style")),
                # New enrichment fields
                "readiness_score": readiness_result.get("readiness_score"),
                "verdict": readiness_result.get("verdict"),
                "score_breakdown": readiness_result.get("score_breakdown", {}),
                "action_items": action_items,
            }
            supabase.table("draft_analysis").update(
                {"analysis_metadata": enriched_metadata}
            ).eq("draft_id", draft_id).execute()
            logger.info("[LangGraph Draft Analysis] Updated analysis_metadata with readiness score + action items")
        except Exception as meta_err:
            logger.warning(f"[LangGraph Draft Analysis] Failed to update enriched metadata (non-fatal): {meta_err}")

        # ============================================================
        # 7. Update draft status to 'analyzed'
        # ============================================================
        update_response = supabase.table("drafts").update({
            "status": "analyzed",
            "updated_at": datetime.datetime.utcnow().isoformat()
        }).eq("id", draft_id).execute()

        if not update_response.data:
            logger.warning("[LangGraph Draft Analysis] Failed to update draft status")

        # Publish 100% AFTER status='analyzed' is written to DB.
        # This ensures the frontend re-fetches and finds the draft ready to open.
        await publish_progress(draft_id, "complete", 100, "Analysis complete")

        # Count total citation suggestions stored
        total_citation_suggestions = sum(
            len(cwc.get("citations", [])) for cwc in (claims_with_citations or [])
        )

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
                "total_feedback": len(all_feedback),
                "total_citation_suggestions": total_citation_suggestions,
                "readiness_score": readiness_result.get("readiness_score"),
                "verdict": readiness_result.get("verdict"),
                "action_items": action_items,
                "synthesis_report": synthesis_report
            },
            "errors": errors
        }

    except Exception as e:
        logger.error(f"[LangGraph Draft Analysis] Error: {e}")

        # Update draft status to 'failed'
        supabase.table("drafts").update({
            "status": "failed",
            "updated_at": datetime.datetime.utcnow().isoformat()
        }).eq("id", draft_id).execute()

        raise

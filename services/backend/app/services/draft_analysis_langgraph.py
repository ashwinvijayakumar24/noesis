"""
Draft Analysis Service (LangGraph Version)

Integrates the LangGraph workflow into the existing draft analysis system.
This replaces the old sequential approach with an intelligent, adaptive workflow.
"""

from app.workflows.draft_analysis.graph import run_draft_analysis_workflow
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
        synthesis_report = final_state.get("synthesis_report", {})
        errors = final_state.get("errors", [])

        logger.info(
            f"[LangGraph Draft Analysis] Workflow completed: "
            f"{len(claims)} claims, {len(gaps)} gaps, {len(feedback)} feedback items"
        )

        # Store results in database
        # 1. Store draft_analysis (structure and metadata)
        draft_analysis_data = {
            "draft_id": draft_id,
            "structure": structure,
            "word_count": structure.get("word_count", 0),
            "analysis_metadata": {
                "workflow_type": "langgraph",
                "total_claims": len(claims),
                "total_gaps": len(gaps),
                "total_feedback": len(feedback),
                "errors": errors,
                "timestamp": datetime.datetime.utcnow().isoformat()
            },
            "created_at": datetime.datetime.utcnow().isoformat()
        }

        analysis_response = supabase.table("draft_analysis").upsert(draft_analysis_data).execute()

        if not analysis_response.data:
            logger.error("[LangGraph Draft Analysis] Failed to store draft_analysis")
            raise Exception("Failed to store draft analysis")

        # 2. Store draft_claims (only if not already stored by Phase 1)
        if claims:
            # Check if claims already exist (from Phase 1 ingest_draft -> analyze_draft_claims)
            existing_claims_res = supabase.table("draft_claims")\
                .select("id")\
                .eq("draft_id", draft_id)\
                .limit(1)\
                .execute()

            if existing_claims_res.data and len(existing_claims_res.data) > 0:
                logger.info(f"[LangGraph Draft Analysis] Claims already exist - SKIPPING insertion (Phase 1 already stored them)")
            else:
                claims_data = []
                for claim in claims:
                    claim_record = {
                        "draft_id": draft_id,
                        "claim_text": claim["claim_text"],
                        "claim_type": claim["claim_type"],
                        "section_location": claim["section_location"],
                        "importance_score": claim["importance_score"],
                        "requires_citation": claim.get("requires_citation", True),
                        "created_at": datetime.datetime.utcnow().isoformat()
                    }
                    claims_data.append(claim_record)

                # Batch insert claims
                claims_response = supabase.table("draft_claims").insert(claims_data).execute()
                logger.info(f"[LangGraph Draft Analysis] Stored {len(claims)} claims")

        # 3. Store coverage_gaps (only if not already stored by Phase 1)
        if gaps:
            # Check if gaps already exist (from Phase 1 ingest_draft -> generate_coverage_gap_report)
            existing_gaps_res = supabase.table("coverage_gaps")\
                .select("id")\
                .eq("draft_id", draft_id)\
                .limit(1)\
                .execute()

            if existing_gaps_res.data and len(existing_gaps_res.data) > 0:
                logger.info(f"[LangGraph Draft Analysis] Coverage gaps already exist - SKIPPING insertion (Phase 1 already stored them)")
            else:
                gaps_data = []
                for gap in gaps:
                    gap_record = {
                        "draft_id": draft_id,
                        "gap_type": gap["gap_type"],
                        "description": gap["description"],
                        "priority": gap.get("severity", gap.get("priority", "medium")),
                        "suggested_papers": gap.get("suggested_papers", []),
                        "reasoning": gap.get("reasoning", ""),
                        "created_at": datetime.datetime.utcnow().isoformat()
                    }
                    gaps_data.append(gap_record)

                # Batch insert gaps
                gaps_response = supabase.table("coverage_gaps").insert(gaps_data).execute()
                logger.info(f"[LangGraph Draft Analysis] Stored {len(gaps)} coverage gaps")

        # 4. Store reviewer_feedback (only if not already stored by Phase 1)
        if feedback:
            # Check if feedback already exists (from Phase 1 ingest_draft -> generate_reviewer_feedback)
            existing_feedback_res = supabase.table("reviewer_feedback")\
                .select("id")\
                .eq("draft_id", draft_id)\
                .limit(1)\
                .execute()

            if existing_feedback_res.data and len(existing_feedback_res.data) > 0:
                logger.info(f"[LangGraph Draft Analysis] Reviewer feedback already exists - SKIPPING insertion (Phase 1 already stored them)")
            else:
                feedback_data = []
                for fb in feedback:
                    feedback_record = {
                        "draft_id": draft_id,
                        "feedback_type": fb["feedback_type"],
                        "feedback_text": fb["feedback_text"],
                        "severity": fb["severity"],
                        "section_reference": fb.get("section_reference", ""),
                        "created_at": datetime.datetime.utcnow().isoformat()
                    }
                    feedback_data.append(feedback_record)

                # Batch insert feedback
                feedback_response = supabase.table("reviewer_feedback").insert(feedback_data).execute()
                logger.info(f"[LangGraph Draft Analysis] Stored {len(feedback)} feedback items")

        # 5. Store citation_suggestions (only if not already stored by Phase 1)
        # Check if suggestions already exist (from Phase 1 ingest_draft -> generate_citation_suggestions)
        existing_suggestions_res = supabase.table("citation_suggestions")\
            .select("id")\
            .eq("draft_id", draft_id)\
            .limit(1)\
            .execute()

        if existing_suggestions_res.data and len(existing_suggestions_res.data) > 0:
            logger.info(f"[LangGraph Draft Analysis] Citation suggestions already exist - SKIPPING insertion (Phase 1 already stored them)")
        elif claims_with_citations:
            citation_suggestions_data = []
            for claim_with_citation in claims_with_citations:
                claim = claim_with_citation.get("claim", {})
                citations = claim_with_citation.get("citations", [])
                citation_quality = claim_with_citation.get("citation_quality", "unknown")
                gaps = claim_with_citation.get("gaps", [])

                # Create citation suggestions for each found citation
                for citation in citations:
                    # Determine suggestion type based on quality
                    if citation_quality == "none":
                        suggestion_type = "missing_citation"
                        impact_level = "critical"
                        priority_score = 1.0
                    elif citation_quality == "weak":
                        suggestion_type = "weak_citation"
                        impact_level = "high"
                        priority_score = 0.8
                    elif citation_quality == "moderate":
                        suggestion_type = "alternative_source"
                        impact_level = "medium"
                        priority_score = 0.5
                    else:  # strong
                        suggestion_type = "supporting_citation"
                        impact_level = "low"
                        priority_score = 0.3

                    # Extract paper metadata from citation
                    suggested_paper = {
                        "document_id": citation.get("document_id"),
                        "document_title": citation.get("document_title", "Unknown"),
                        "content": citation.get("content", ""),
                        "similarity": citation.get("similarity", 0.0),
                        "chunk_index": citation.get("chunk_index"),
                        "section": citation.get("section", "")
                    }

                    # Build reasoning from gaps
                    reasoning_parts = []
                    if citation_quality == "none":
                        reasoning_parts.append("No supporting citations found for this claim.")
                    elif citation_quality == "weak":
                        reasoning_parts.append("Current citation support is weak.")

                    if gaps:
                        reasoning_parts.append("Gaps identified: " + "; ".join(gaps))

                    reasoning = " ".join(reasoning_parts) if reasoning_parts else "Citation suggestion based on literature search"

                    citation_suggestion = {
                        "draft_id": draft_id,
                        "user_id": user_id,
                        "claim_text": claim.get("claim_text", ""),
                        "section_location": claim.get("section_location", ""),
                        "suggestion_type": suggestion_type,
                        "suggested_paper": suggested_paper,
                        "confidence_score": citation.get("similarity", 0.0),
                        "relevance_score": citation.get("similarity", 0.0),
                        "priority_score": priority_score,
                        "impact_level": impact_level,
                        "reasoning": reasoning,
                        "status": "pending",
                        "created_at": datetime.datetime.utcnow().isoformat()
                    }
                    citation_suggestions_data.append(citation_suggestion)

            # Batch insert citation suggestions
            if citation_suggestions_data:
                try:
                    citations_response = supabase.table("citation_suggestions").insert(citation_suggestions_data).execute()
                    logger.info(f"[LangGraph Draft Analysis] Stored {len(citation_suggestions_data)} citation suggestions")
                except Exception as citation_error:
                    logger.error(f"[LangGraph Draft Analysis] Failed to store citation suggestions: {citation_error}")
                    # Don't fail the entire analysis if citation storage fails
            else:
                logger.warning("[LangGraph Draft Analysis] No citation suggestions to store")

        # 6. Update draft status to 'analyzed'
        update_response = supabase.table("drafts").update({
            "status": "analyzed",
            "updated_at": datetime.datetime.utcnow().isoformat()
        }).eq("id", draft_id).execute()

        if not update_response.data:
            logger.warning("[LangGraph Draft Analysis] Failed to update draft status")

        # Count total citation suggestions stored
        total_citation_suggestions = 0
        if claims_with_citations:
            for cwc in claims_with_citations:
                total_citation_suggestions += len(cwc.get("citations", []))

        # Return summary
        return {
            "message": "Draft analysis completed successfully",
            "draft_id": draft_id,
            "workflow_type": "langgraph",
            "results": {
                "total_claims": len(claims),
                "claims_by_type": {
                    "empirical": sum(1 for c in claims if c['claim_type'] == 'empirical'),
                    "theoretical": sum(1 for c in claims if c['claim_type'] == 'theoretical'),
                    "methodological": sum(1 for c in claims if c['claim_type'] == 'methodological')
                },
                "total_gaps": len(gaps),
                "gaps_by_severity": {
                    "critical": sum(1 for g in gaps if g['severity'] == 'critical'),
                    "important": sum(1 for g in gaps if g['severity'] == 'important'),
                    "minor": sum(1 for g in gaps if g['severity'] == 'minor')
                },
                "total_feedback": len(feedback),
                "feedback_by_type": {
                    "strengths": sum(1 for f in feedback if f['feedback_type'] == 'strength'),
                    "weaknesses": sum(1 for f in feedback if f['feedback_type'] == 'weakness'),
                    "questions": sum(1 for f in feedback if f['feedback_type'] == 'question'),
                    "suggestions": sum(1 for f in feedback if f['feedback_type'] == 'suggestion')
                },
                "total_citation_suggestions": total_citation_suggestions,
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

"""
Draft Comparison Service

Compares two draft versions using embedding-based similarity matching and
GPT-5.2 narrative generation to produce deep, actionable comparisons.
"""

import json
import asyncio
from typing import Dict, Any, List, Optional

from app.core.supabase_client import get_supabase_client
from app.core.openai_client import get_openai_client, get_completion_params
from app.core.logging_config import get_logger

logger = get_logger(__name__)


COMPARISON_NARRATIVE_PROMPT = """You are an expert academic mentor reviewing the evolution of a research draft.

You are comparing two versions of a research draft based on changes to claims, reviewer feedback, and coverage gaps.

Given the comparison data below, generate a structured narrative that:
1. Summarizes how the draft has evolved (one paragraph)
2. Highlights specific improvements made
3. Identifies what still needs work
4. Assesses reviewer-readiness

Return ONLY valid JSON:
{
  "evolution_summary": "One paragraph describing what changed and why it matters academically",
  "key_improvements": ["Improvement 1", "Improvement 2"],
  "remaining_gaps": ["Still needs work: item 1", "Still needs work: item 2"],
  "reviewer_readiness": "not_ready" | "partially_ready" | "ready"
}
"""


async def _embed_text(text: str) -> Optional[List[float]]:
    """Generate embedding for a text using OpenAI."""
    try:
        client = get_openai_client()
        response = client.embeddings.create(
            model="text-embedding-3-small",
            input=text[:8000]
        )
        return response.data[0].embedding
    except Exception as e:
        logger.warning(f"Embedding generation failed: {e}")
        return None


def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if not vec1 or not vec2:
        return 0.0
    dot = sum(a * b for a, b in zip(vec1, vec2))
    mag1 = sum(a * a for a in vec1) ** 0.5
    mag2 = sum(b * b for b in vec2) ** 0.5
    if mag1 == 0 or mag2 == 0:
        return 0.0
    return dot / (mag1 * mag2)


async def _are_semantically_similar(
    text1: str,
    text2: str,
    threshold: float = 0.75
) -> bool:
    """Check if two texts are semantically similar using embedding cosine similarity."""
    if not text1 or not text2:
        return False

    # Fast path: identical short strings
    if text1.strip()[:100] == text2.strip()[:100]:
        return True

    emb1, emb2 = await asyncio.gather(
        _embed_text(text1[:500]),
        _embed_text(text2[:500]),
        return_exceptions=True
    )

    if isinstance(emb1, Exception) or isinstance(emb2, Exception):
        # Fallback to word overlap
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        union = len(words1 | words2)
        if union == 0:
            return False
        return (len(words1 & words2) / union) >= 0.8

    return _cosine_similarity(emb1, emb2) >= threshold


async def generate_comparison_narrative(
    comparison_result: Dict[str, Any],
    improvement_score: float
) -> Dict[str, Any]:
    """
    Generate an AI narrative for the comparison using GPT-5.2.

    Args:
        comparison_result: The structured comparison result
        improvement_score: Overall improvement score (0-100)

    Returns:
        Narrative dict with evolution_summary, key_improvements, remaining_gaps, reviewer_readiness
    """
    client = get_openai_client()

    context = f"""
Improvement Score: {improvement_score}/100

Claims Added: {len(comparison_result.get("claims_added", []))}
Claims Removed: {len(comparison_result.get("claims_removed", []))}
Claims Improved: {len(comparison_result.get("claims_improved", []))}
Claims Worsened: {len(comparison_result.get("claims_worsened", []))}
Feedback Addressed: {len(comparison_result.get("feedback_addressed", []))}
Gaps Resolved: {len(comparison_result.get("gaps_resolved", []))}

Feedback with Resolution Status:
"""
    for item in comparison_result.get("feedback_tracked", [])[:10]:
        status = item.get("resolution_status", "unknown")
        context += f"- [{status.upper()}] {item.get('feedback_text', '')[:120]}\n"

    try:
        def _sync_call():
            response = client.chat.completions.create(
                model="gpt-5.2-chat-latest",
                messages=[
                    {"role": "system", "content": COMPARISON_NARRATIVE_PROMPT},
                    {"role": "user", "content": f"Generate comparison narrative:\n\n{context}"}
                ],
                max_completion_tokens=1000,
                **get_completion_params()
            )
            return json.loads(response.choices[0].message.content)

        narrative = await asyncio.to_thread(_sync_call)
        return narrative

    except Exception as e:
        logger.warning(f"Narrative generation failed: {e}")
        return {
            "evolution_summary": generate_comparison_summary(comparison_result, improvement_score),
            "key_improvements": [f"{len(comparison_result.get('feedback_addressed', []))} issues addressed"],
            "remaining_gaps": [f"{len(comparison_result.get('claims_worsened', []))} areas need attention"],
            "reviewer_readiness": "partially_ready" if improvement_score >= 55 else "not_ready"
        }


async def compare_drafts(
    draft_v1_id: str,
    draft_v2_id: str,
    project_id: str,
    user_id: str
) -> Dict[str, Any]:
    """
    Compare two draft versions using embedding similarity + GPT narrative.

    Analyzes:
    - Claims added/removed/improved/worsened (embedding-based matching)
    - Feedback addressed vs still pending
    - Coverage gaps resolved
    - Overall improvement score
    - AI-generated narrative

    Args:
        draft_v1_id: Earlier draft version
        draft_v2_id: Later draft version
        project_id: Project ID
        user_id: User ID

    Returns:
        Comparison results with detailed analysis and narrative
    """
    supabase = get_supabase_client()

    try:
        # Fetch both drafts with their analyses
        draft_v1 = supabase.table("drafts").select("*").eq("id", draft_v1_id).execute()
        draft_v2 = supabase.table("drafts").select("*").eq("id", draft_v2_id).execute()

        if not draft_v1.data or not draft_v2.data:
            raise ValueError("One or both drafts not found")

        # Get claims for both drafts
        claims_v1 = supabase.table("draft_claims").select("*").eq("draft_id", draft_v1_id).execute()
        claims_v2 = supabase.table("draft_claims").select("*").eq("draft_id", draft_v2_id).execute()

        # Get feedback for both drafts
        feedback_v1 = supabase.table("reviewer_feedback").select("*").eq("draft_id", draft_v1_id).execute()
        feedback_v2 = supabase.table("reviewer_feedback").select("*").eq("draft_id", draft_v2_id).execute()

        # Get coverage gaps for both drafts
        gaps_v1 = supabase.table("coverage_gaps").select("*").eq("draft_id", draft_v1_id).execute()
        gaps_v2 = supabase.table("coverage_gaps").select("*").eq("draft_id", draft_v2_id).execute()

        # Analyze changes using embedding similarity
        comparison_result = await analyze_changes(
            claims_v1=claims_v1.data or [],
            claims_v2=claims_v2.data or [],
            feedback_v1=feedback_v1.data or [],
            feedback_v2=feedback_v2.data or [],
            gaps_v1=gaps_v1.data or [],
            gaps_v2=gaps_v2.data or []
        )

        # Calculate improvement score
        improvement_score = calculate_improvement_score(comparison_result)

        # Generate AI narrative
        narrative = await generate_comparison_narrative(comparison_result, improvement_score)

        # Store comparison in database
        comparison_data = {
            "project_id": project_id,
            "user_id": user_id,
            "draft_v1_id": draft_v1_id,
            "draft_v2_id": draft_v2_id,
            "comparison_result": comparison_result,
            "improvement_score": improvement_score,
            "claims_added": len(comparison_result.get("claims_added", [])),
            "claims_removed": len(comparison_result.get("claims_removed", [])),
            "claims_improved": len(comparison_result.get("claims_improved", [])),
            "claims_worsened": len(comparison_result.get("claims_worsened", [])),
            "feedback_addressed": len(comparison_result.get("feedback_addressed", [])),
            "gaps_resolved": len(comparison_result.get("gaps_resolved", [])),
            "metadata": {"narrative": narrative}
        }

        result = supabase.table("draft_comparisons").insert(comparison_data).execute()

        return {
            "comparison_id": result.data[0]["id"] if result.data else None,
            "improvement_score": improvement_score,
            "summary": generate_comparison_summary(comparison_result, improvement_score),
            "narrative": narrative,
            **comparison_result
        }

    except Exception as e:
        raise Exception(f"Failed to compare drafts: {str(e)}")


async def analyze_changes(
    claims_v1: List[Dict],
    claims_v2: List[Dict],
    feedback_v1: List[Dict],
    feedback_v2: List[Dict],
    gaps_v1: List[Dict],
    gaps_v2: List[Dict]
) -> Dict[str, Any]:
    """
    Analyze changes between draft versions using embedding similarity.
    """
    claims_v1_texts = [c.get("claim_text", "") for c in claims_v1]
    claims_v2_texts = [c.get("claim_text", "") for c in claims_v2]
    feedback_v2_texts = [f.get("feedback_text", "") for f in feedback_v2]
    gaps_v2_descriptions = [g.get("description", "") for g in gaps_v2]

    claims_added = []
    claims_removed = []
    claims_improved = []
    claims_worsened = []

    # Check each v2 claim against v1 (added if no semantic match found)
    for claim in claims_v2:
        claim_text = claim.get("claim_text", "")
        matched = False
        for v1_text in claims_v1_texts:
            if await _are_semantically_similar(claim_text, v1_text):
                matched = True
                break
        if not matched:
            claims_added.append({
                "claim_text": claim_text,
                "claim_type": claim.get("claim_type"),
                "importance_score": claim.get("importance_score")
            })

    # Check each v1 claim against v2 (removed if no semantic match found)
    for claim in claims_v1:
        claim_text = claim.get("claim_text", "")
        matched = False
        for v2_text in claims_v2_texts:
            if await _are_semantically_similar(claim_text, v2_text):
                matched = True
                break
        if not matched:
            claims_removed.append({
                "claim_text": claim_text,
                "claim_type": claim.get("claim_type")
            })

    # Track resolution status for each v1 feedback item
    feedback_addressed = []
    feedback_tracked = []

    for fb in feedback_v1:
        fb_text = fb.get("feedback_text", "")
        severity = fb.get("severity", "")

        # Check if this feedback still appears in v2
        still_present = False
        for v2_text in feedback_v2_texts:
            if await _are_semantically_similar(fb_text, v2_text, threshold=0.70):
                still_present = True
                break

        if still_present:
            resolution_status = "still_pending"
        else:
            resolution_status = "resolved"
            if severity in ("critical", "major"):
                feedback_addressed.append({
                    "feedback_text": fb_text,
                    "severity": severity
                })

        feedback_tracked.append({
            "feedback_text": fb_text,
            "severity": severity,
            "section_reference": fb.get("section_reference", ""),
            "resolution_status": resolution_status
        })

    # Check resolved gaps
    gaps_resolved = []
    for gap in gaps_v1:
        gap_desc = gap.get("description", "")
        resolved = True
        for v2_desc in gaps_v2_descriptions:
            if await _are_semantically_similar(gap_desc, v2_desc, threshold=0.72):
                resolved = False
                break
        if resolved:
            gaps_resolved.append({
                "description": gap_desc,
                "gap_type": gap.get("gap_type"),
                "priority": gap.get("priority")
            })

    return {
        "claims_added": claims_added,
        "claims_removed": claims_removed,
        "claims_improved": claims_improved,
        "claims_worsened": claims_worsened,
        "feedback_addressed": feedback_addressed,
        "feedback_tracked": feedback_tracked,
        "gaps_resolved": gaps_resolved,
        "metadata": {
            "claims_v1_count": len(claims_v1),
            "claims_v2_count": len(claims_v2),
            "feedback_v1_count": len(feedback_v1),
            "feedback_v2_count": len(feedback_v2),
            "gaps_v1_count": len(gaps_v1),
            "gaps_v2_count": len(gaps_v2)
        }
    }


def calculate_improvement_score(comparison_result: Dict[str, Any]) -> float:
    """
    Calculate overall improvement score (0-100).

    Weighted scoring:
    - Claims added: +5 points each
    - Claims improved: +10 points each
    - Claims worsened: -10 points each
    - Feedback addressed: +15 points each
    - Gaps resolved: +10 points each
    """
    score = 50  # Start at neutral

    score += len(comparison_result.get("claims_added", [])) * 5
    score += len(comparison_result.get("claims_improved", [])) * 10
    score -= len(comparison_result.get("claims_worsened", [])) * 10
    score += len(comparison_result.get("feedback_addressed", [])) * 15
    score += len(comparison_result.get("gaps_resolved", [])) * 10

    return round(max(0, min(100, score)), 2)


def generate_comparison_summary(
    comparison_result: Dict[str, Any],
    improvement_score: float
) -> str:
    """Generate human-readable summary of comparison."""
    claims_added = len(comparison_result.get("claims_added", []))
    claims_improved = len(comparison_result.get("claims_improved", []))
    feedback_addressed = len(comparison_result.get("feedback_addressed", []))
    gaps_resolved = len(comparison_result.get("gaps_resolved", []))

    if improvement_score >= 75:
        rating = "Excellent improvement"
    elif improvement_score >= 60:
        rating = "Good improvement"
    elif improvement_score >= 50:
        rating = "Moderate improvement"
    elif improvement_score >= 40:
        rating = "Minor improvement"
    else:
        rating = "Needs more work"

    summary = f"{rating} (Score: {improvement_score}/100). "
    changes = []
    if claims_added > 0:
        changes.append(f"{claims_added} new claims added")
    if claims_improved > 0:
        changes.append(f"{claims_improved} claims strengthened")
    if feedback_addressed > 0:
        changes.append(f"{feedback_addressed} issues addressed")
    if gaps_resolved > 0:
        changes.append(f"{gaps_resolved} coverage gaps resolved")

    if changes:
        summary += ", ".join(changes) + "."
    else:
        summary += "No significant changes detected."

    return summary

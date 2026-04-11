"""
Section Mapping Service

Maps draft content sections to standardized section types for section-based navigation
and feedback organization.

This service provides:
- Detection of section types from GROBID/GPT-4 extracted structure
- Assignment of section types to existing feedback (claims, gaps, feedback)
- Auto-migration for existing drafts without section assignments
- Fuzzy matching between section locations and standardized types

Purpose: Enable section-based navigation in the redesigned draft analysis UI
"""

import re
from typing import Dict, Any, List, Optional
from app.core.supabase_client import supabase
from app.core.logging_config import get_logger

logger = get_logger(__name__)

# ============================================
# Section Type Detection Patterns
# ============================================

# Keywords for each section type (lowercase, stemmed)
SECTION_KEYWORDS = {
    'abstract': [
        'abstract', 'summary', 'overview', 'executive summary'
    ],
    'introduction': [
        'introduction', 'background', 'motivation', 'overview',
        'problem statement', 'context', 'rationale'
    ],
    'literature_review': [
        'literature', 'related work', 'prior work', 'previous work',
        'state of the art', 'sota', 'background', 'review',
        'theoretical framework', 'conceptual framework'
    ],
    'methodology': [
        'method', 'approach', 'design', 'procedure', 'implementation',
        'experimental setup', 'materials', 'techniques', 'framework',
        'architecture', 'algorithm', 'model', 'protocol'
    ],
    'results': [
        'result', 'finding', 'experiment', 'evaluation', 'performance',
        'analysis', 'outcome', 'observation', 'measurement', 'data'
    ],
    'discussion': [
        'discussion', 'analysis', 'interpretation', 'implication',
        'limitation', 'comparison', 'insight', 'reflection'
    ],
    'conclusion': [
        'conclusion', 'concluding remarks', 'final remarks', 'summary',
        'future work', 'future directions', 'closing', 'wrap-up',
        'takeaways', 'recommendations'
    ],
    'references': [
        'reference', 'bibliography', 'works cited', 'citation',
        'literature cited', 'sources'
    ]
}


def detect_section_type(section_title: str, section_type_hint: Optional[str] = None) -> str:
    """
    Detect standardized section type from section title or type hint.

    Uses keyword matching with fuzzy logic to map various section headings
    to our 8 standardized section types.

    Args:
        section_title: Section heading from the document (e.g., "3. Methods and Materials")
        section_type_hint: Type hint from GROBID or GPT-4 (e.g., "methods", "introduction")

    Returns:
        One of: abstract, introduction, literature_review, methodology,
                results, discussion, conclusion, references
        Defaults to 'introduction' if no match found (most common)
    """
    # Clean and normalize input
    title_lower = section_title.lower().strip() if section_title else ""
    hint_lower = section_type_hint.lower().strip() if section_type_hint else ""

    # Remove numbering (e.g., "3.1 Methods" -> "methods")
    title_cleaned = re.sub(r'^[\d\.\s]+', '', title_lower)

    # Direct type hint matching (from GROBID/GPT-4)
    if hint_lower:
        # Map common GROBID types to our enum
        direct_mapping = {
            'abstract': 'abstract',
            'introduction': 'introduction',
            'related work': 'literature_review',
            'literature': 'literature_review',
            'methods': 'methodology',
            'methodology': 'methodology',
            'results': 'results',
            'discussion': 'discussion',
            'conclusion': 'conclusion',
            'conclusions': 'conclusion',
            'references': 'references',
            'bibliography': 'references'
        }
        if hint_lower in direct_mapping:
            return direct_mapping[hint_lower]

    # Keyword-based matching with scoring
    best_match = None
    best_score = 0

    for section_type, keywords in SECTION_KEYWORDS.items():
        score = 0
        for keyword in keywords:
            # Exact match in title
            if keyword == title_cleaned:
                score += 10
            # Keyword appears in title
            elif keyword in title_cleaned:
                score += 5
            # Keyword appears in type hint
            elif hint_lower and keyword in hint_lower:
                score += 3

        if score > best_score:
            best_score = score
            best_match = section_type

    # Return best match if confident (score >= 3)
    if best_score >= 3:
        return best_match

    # Default to introduction (most common first section)
    logger.warning(
        f"Could not determine section type for '{section_title}' "
        f"(hint: '{section_type_hint}'). Defaulting to 'introduction'."
    )
    return 'introduction'


def detect_section_type_from_location(section_location: str) -> str:
    """
    Detect section type from free-form section_location string.

    Used for auto-migration of existing drafts where section_location
    contains strings like "Introduction section" or "Methods (page 5)".

    Args:
        section_location: Free-form section location string

    Returns:
        Detected section type enum value
    """
    if not section_location:
        return 'introduction'

    return detect_section_type(section_title=section_location, section_type_hint=None)


async def assign_section_types_to_feedback(draft_id: str) -> Dict[str, Any]:
    """
    Assign section types to all feedback items for a draft.

    Main entry point for section type assignment. This function:
    1. Loads draft structure from draft_analysis table
    2. Maps each feedback item to its corresponding section
    3. Updates all feedback tables with section_type assignments

    Args:
        draft_id: UUID of the draft

    Returns:
        Dictionary with assignment statistics:
        {
            "claims_updated": 10,
            "gaps_updated": 5,
            "feedback_updated": 8,
            "sections_identified": 7,
            "unassigned": 2
        }
    """
    logger.info(f"Assigning section types for draft {draft_id}")

    try:
        # 1. Load draft structure
        analysis_response = (
            supabase.table("draft_analysis")
            .select("structure")
            .eq("draft_id", draft_id)
            .execute()
        )

        if not analysis_response.data:
            logger.warning(f"No draft_analysis found for draft {draft_id}")
            return {
                "error": "Draft analysis not found",
                "claims_updated": 0,
                "gaps_updated": 0,
                "feedback_updated": 0
            }

        structure = analysis_response.data[0]["structure"]
        sections = structure.get("sections", [])

        if not sections:
            logger.warning(f"No sections found in draft structure for {draft_id}")
            # Fall back to using section_location for detection
            return await assign_section_types_from_location(draft_id)

        logger.info(f"Found {len(sections)} sections in draft structure")

        # 2. Build section mapping: section title -> section_type
        section_mapping = {}
        for section in sections:
            title = section.get("title", "")
            type_hint = section.get("type", "")
            section_type = detect_section_type(title, type_hint)
            section_mapping[title.lower()] = section_type
            logger.debug(f"Mapped '{title}' -> {section_type}")

        # 3. Update claims
        claims_updated = await update_claims_section_types(draft_id, section_mapping)

        # 4. Update coverage gaps
        gaps_updated = await update_gaps_section_types(draft_id, section_mapping)

        # 5. Update reviewer feedback
        feedback_updated = await update_feedback_section_types(draft_id, section_mapping)

        logger.info(
            f"Section type assignment complete: "
            f"{claims_updated} claims, {gaps_updated} gaps, {feedback_updated} feedback"
        )

        return {
            "claims_updated": claims_updated,
            "gaps_updated": gaps_updated,
            "feedback_updated": feedback_updated,
            "sections_identified": len(sections),
            "unassigned": 0
        }

    except Exception as e:
        logger.error(f"Failed to assign section types for draft {draft_id}: {e}")
        raise


async def assign_section_types_from_location(draft_id: str) -> Dict[str, Any]:
    """
    Fallback: Assign section types based on section_location field.

    Used when draft structure is not available (e.g., older drafts, TXT files).
    Parses section_location strings like "Introduction section" to detect type.

    Args:
        draft_id: UUID of the draft

    Returns:
        Dictionary with assignment statistics
    """
    logger.info(f"Using section_location fallback for draft {draft_id}")

    claims_updated = 0
    gaps_updated = 0
    feedback_updated = 0

    try:
        # Update claims based on section_location
        claims_response = (
            supabase.table("draft_claims")
            .select("id, section_location")
            .eq("draft_id", draft_id)
            .is_("section_type", "null")
            .execute()
        )

        for claim in claims_response.data:
            section_type = detect_section_type_from_location(claim.get("section_location", ""))
            supabase.table("draft_claims").update(
                {"section_type": section_type}
            ).eq("id", claim["id"]).execute()
            claims_updated += 1

        # Update gaps based on section_location
        gaps_response = (
            supabase.table("coverage_gaps")
            .select("id, description")
            .eq("draft_id", draft_id)
            .is_("section_type", "null")
            .execute()
        )

        for gap in gaps_response.data:
            # Gaps don't have section_location, use description heuristic
            section_type = detect_section_type_from_location(gap.get("description", ""))
            supabase.table("coverage_gaps").update(
                {"section_type": section_type}
            ).eq("id", gap["id"]).execute()
            gaps_updated += 1

        # Update feedback based on section_reference
        feedback_response = (
            supabase.table("reviewer_feedback")
            .select("id, section_reference")
            .eq("draft_id", draft_id)
            .is_("section_type", "null")
            .execute()
        )

        for feedback in feedback_response.data:
            section_type = detect_section_type_from_location(feedback.get("section_reference", ""))
            supabase.table("reviewer_feedback").update(
                {"section_type": section_type}
            ).eq("id", feedback["id"]).execute()
            feedback_updated += 1

        logger.info(
            f"Fallback assignment complete: "
            f"{claims_updated} claims, {gaps_updated} gaps, {feedback_updated} feedback"
        )

        return {
            "claims_updated": claims_updated,
            "gaps_updated": gaps_updated,
            "feedback_updated": feedback_updated,
            "sections_identified": 0,
            "unassigned": 0
        }

    except Exception as e:
        logger.error(f"Fallback section assignment failed for draft {draft_id}: {e}")
        raise


async def update_claims_section_types(
    draft_id: str,
    section_mapping: Dict[str, str]
) -> int:
    """
    Update section_type for all claims in a draft.

    Matches claim section_location to section titles in mapping.

    Args:
        draft_id: UUID of the draft
        section_mapping: Dict of {section_title_lower: section_type}

    Returns:
        Number of claims updated
    """
    claims_response = (
        supabase.table("draft_claims")
        .select("id, section_location")
        .eq("draft_id", draft_id)
        .execute()
    )

    updated_count = 0

    for claim in claims_response.data:
        section_location = claim.get("section_location", "").lower()

        # Try exact match first
        section_type = section_mapping.get(section_location)

        # Try fuzzy match if exact fails
        if not section_type:
            for title, stype in section_mapping.items():
                if title in section_location or section_location in title:
                    section_type = stype
                    break

        # Fallback to detection
        if not section_type:
            section_type = detect_section_type_from_location(section_location)

        # Update claim — only section_type, preserve user's saved/dismissed status
        supabase.table("draft_claims").update(
            {"section_type": section_type}
        ).eq("id", claim["id"]).execute()
        updated_count += 1

    logger.debug(f"Updated section_type for {updated_count} claims")
    return updated_count


async def update_gaps_section_types(
    draft_id: str,
    section_mapping: Dict[str, str]
) -> int:
    """
    Update section_type for all coverage gaps in a draft.

    Coverage gaps may not have explicit section_location, so we use
    heuristics based on gap_type and description.

    Args:
        draft_id: UUID of the draft
        section_mapping: Dict of {section_title_lower: section_type}

    Returns:
        Number of gaps updated
    """
    gaps_response = (
        supabase.table("coverage_gaps")
        .select("id, gap_type, description")
        .eq("draft_id", draft_id)
        .execute()
    )

    updated_count = 0

    for gap in gaps_response.data:
        gap_type = gap.get("gap_type", "").lower()
        description = gap.get("description", "") or ""

        # Heuristic: methodology gaps -> methodology section
        if "method" in gap_type:
            section_type = 'methodology'
        # Theoretical/literature gaps -> literature review
        elif "theoretical" in gap_type or "literature" in gap_type or "seminal" in gap_type:
            section_type = 'literature_review'
        else:
            # Try to parse embedded section from B3-format descriptions:
            # "Claim in {section}: '...' — ..." or "Claim '{...}' in {section} ..."
            section_match = re.match(r"claim in (.+?):", description, re.IGNORECASE)
            if section_match:
                extracted_section = section_match.group(1).strip()
                section_type = detect_section_type_from_location(extracted_section)
            else:
                # Fall back to keyword detection on description (old behavior)
                section_type = detect_section_type_from_location(description)

        # Update gap — only section_type, preserve user's saved/dismissed status
        supabase.table("coverage_gaps").update(
            {"section_type": section_type}
        ).eq("id", gap["id"]).execute()
        updated_count += 1

    logger.debug(f"Updated section_type for {updated_count} gaps")
    return updated_count


async def update_feedback_section_types(
    draft_id: str,
    section_mapping: Dict[str, str]
) -> int:
    """
    Update section_type for all reviewer feedback in a draft.

    Uses section_reference field to match against section titles.

    Args:
        draft_id: UUID of the draft
        section_mapping: Dict of {section_title_lower: section_type}

    Returns:
        Number of feedback items updated
    """
    feedback_response = (
        supabase.table("reviewer_feedback")
        .select("id, section_reference, feedback_type")
        .eq("draft_id", draft_id)
        .execute()
    )

    updated_count = 0

    for feedback in feedback_response.data:
        section_reference = feedback.get("section_reference", "").lower()
        feedback_type = feedback.get("feedback_type", "").lower()

        # Try exact match first
        section_type = section_mapping.get(section_reference)

        # Try fuzzy match if exact fails
        if not section_type:
            for title, stype in section_mapping.items():
                if title in section_reference or section_reference in title:
                    section_type = stype
                    break

        # Heuristic based on feedback_type
        if not section_type:
            if "method" in feedback_type:
                section_type = 'methodology'
            elif "coverage" in feedback_type or "literature" in feedback_type:
                section_type = 'literature_review'
            elif "position" in feedback_type:
                section_type = 'introduction'
            else:
                section_type = detect_section_type_from_location(section_reference)

        # Update feedback — only section_type, preserve user's saved/dismissed status
        supabase.table("reviewer_feedback").update(
            {"section_type": section_type}
        ).eq("id", feedback["id"]).execute()
        updated_count += 1

    logger.debug(f"Updated section_type for {updated_count} feedback items")
    return updated_count


async def auto_migrate_existing_draft(draft_id: str) -> Dict[str, Any]:
    """
    Auto-migrate an existing draft to use section-based navigation.

    This is called when a user opens an old draft for the first time
    after the section-based redesign. No re-analysis is needed - we
    just assign section types based on existing data.

    Args:
        draft_id: UUID of the draft

    Returns:
        Migration result with statistics
    """
    logger.info(f"Auto-migrating existing draft {draft_id} to section-based view")

    try:
        # Check if already migrated (section_type AND status both set)
        claims_check = (
            supabase.table("draft_claims")
            .select("id")
            .eq("draft_id", draft_id)
            .not_.is_("section_type", "null")
            .not_.is_("status", "null")
            .limit(1)
            .execute()
        )

        if claims_check.data:
            logger.info(f"Draft {draft_id} already migrated")
            return {
                "already_migrated": True,
                "claims_updated": 0,
                "gaps_updated": 0,
                "feedback_updated": 0
            }

        # Perform migration
        result = await assign_section_types_to_feedback(draft_id)
        result["already_migrated"] = False

        logger.info(f"Auto-migration complete for draft {draft_id}")
        return result

    except Exception as e:
        logger.error(f"Auto-migration failed for draft {draft_id}: {e}")
        raise

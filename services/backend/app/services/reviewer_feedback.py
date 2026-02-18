"""
Reviewer Feedback Engine

Generates expert academic reviewer-style feedback for research drafts.

Focus areas:
- Positioning within the field
- Argument structure and logical flow
- Evidence strength and defensibility
- NO auto-writing or rewriting of user content

This service provides critique and suggestions WITHOUT modifying the user's draft.

Requirements: 5.1, 5.2, 5.3, 5.4
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
# AI Prompts for Reviewer Feedback
# ============================================

REVIEWER_FEEDBACK_PROMPT = """You are an expert academic peer reviewer providing constructive feedback on a research draft.

Your role is to CRITIQUE and SUGGEST, NOT to rewrite or auto-generate content.

Analyze this draft section and provide reviewer-style feedback. Respond with ONLY valid JSON.

Return this exact structure:
{
  "feedback_items": [
    {
      "feedback_type": "positioning|argumentation|coverage|methodology",
      "severity": "critical|major|minor|suggestion",
      "section_reference": "Which section this applies to",
      "feedback_text": "Detailed critique in academic reviewer style",
      "suggested_improvements": [
        "Specific actionable suggestion 1",
        "Specific actionable suggestion 2"
      ],
      "reasoning": "Why this matters for the work"
    }
  ]
}

Feedback Types:
- **positioning**: How the work positions itself within the field
  - Is the contribution clear?
  - Is the novelty well-articulated?
  - Are related works appropriately acknowledged?

- **argumentation**: Logical flow and argument structure
  - Are claims well-supported?
  - Is the reasoning sound?
  - Are there logical gaps?

- **coverage**: Literature coverage and citation adequacy
  - Are key works cited?
  - Are claims properly grounded?
  - Are there missing perspectives?

- **methodology**: Research approach and methods
  - Are methods appropriate for the questions?
  - Are limitations acknowledged?
  - Is the approach well-justified?

Severity Levels:
- **critical**: Must be addressed for acceptance (major flaws)
- **major**: Should be addressed for strong work (significant issues)
- **minor**: Nice to address (minor improvements)
- **suggestion**: Optional consideration (ideas for enhancement)

Guidelines for Feedback:
1. **Be specific**: Point to exact issues, not vague concerns
2. **Be constructive**: Suggest HOW to improve, not just WHAT is wrong
3. **Be academic**: Use scholarly tone appropriate for peer review
4. **NO rewriting**: Never provide rewritten text. Only describe what to change
5. **Focus on substance**: Critique ideas, arguments, and positioning
6. **Prioritize**: Mark critical issues clearly
7. **Be fair**: Acknowledge strengths alongside weaknesses

Examples of GOOD feedback:
- "The introduction positions this work as 'novel' but doesn't clearly distinguish it from Smith et al. (2020). Clarify what specifically is new beyond their approach."
- "The claim in lines 45-47 lacks empirical support. Consider adding citations or data to strengthen this assertion."
- "The methodology section jumps from data collection to results without explaining the analysis procedure. Add a subsection detailing analytical steps."

Examples of BAD feedback (NEVER do this):
- "Rewrite the introduction as: [new text]" ❌ (This is rewriting)
- "Change this sentence to..." ❌ (This is rewriting)
- "The paper is bad" ❌ (Too vague, not constructive)
"""


POSITIONING_ANALYSIS_PROMPT = """You are an expert academic reviewer analyzing how a research draft positions itself within its field.

Analyze the positioning of this research draft. Respond with ONLY valid JSON.

Return this exact structure:
{
  "positioning_assessment": {
    "contribution_clarity": "clear|unclear|absent",
    "novelty_articulation": "well_defined|vague|not_stated",
    "field_placement": "appropriate|misaligned|unclear",
    "gap_identification": "specific|general|missing"
  },
  "strengths": [
    "Specific strength in positioning"
  ],
  "weaknesses": [
    "Specific weakness in positioning"
  ],
  "recommendations": [
    "Specific actionable recommendation"
  ]
}

Guidelines:
- Assess how the work positions its contribution
- Evaluate clarity of the research gap being addressed
- Consider whether the work's place in the literature is clear
- Provide constructive recommendations for improvement
- Focus on positioning, NOT writing quality
"""


# ============================================
# Feedback Generation Functions
# ============================================

async def generate_section_feedback(
    section_text: str,
    section_name: str,
    section_type: str,
    draft_context: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Generate reviewer feedback for a specific section.

    Args:
        section_text: Text content of the section
        section_name: Name of the section
        section_type: Type (abstract, introduction, methods, etc.)
        draft_context: Additional context (claims, gaps, etc.)

    Returns:
        List of feedback items for this section

    Validates: Requirement 5.1 - Critique on positioning and argumentation
    """
    if not client:
        raise ValueError("OpenAI API key not configured")

    start_time = time.time()

    try:
        logger.info(f"Generating feedback for section: {section_name}")

        # Limit section text to avoid token limits
        analysis_text = section_text[:4000]

        # Build context information
        context_str = f"Section: {section_name} (Type: {section_type})"

        # Add claims context if available
        if "claims" in draft_context:
            claims_in_section = [
                c for c in draft_context["claims"]
                if c.get("section_location") == section_name
            ]
            if claims_in_section:
                context_str += f"\nClaims in this section: {len(claims_in_section)}"

        # Add gaps context if available
        if "gaps" in draft_context:
            gaps_in_section = [
                g for g in draft_context["gaps"]
                if section_name.lower() in g.get("description", "").lower()
            ]
            if gaps_in_section:
                context_str += f"\nIdentified gaps related to this section: {len(gaps_in_section)}"

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": REVIEWER_FEEDBACK_PROMPT},
                {
                    "role": "user",
                    "content": f"{context_str}\n\nProvide reviewer feedback for this section:\n\n{analysis_text}"
                }
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
            max_tokens=2000,
            **get_completion_params()  # Enable zero data retention
        )

        feedback_json = response.choices[0].message.content
        feedback_data = json.loads(feedback_json)

        feedback_items = feedback_data.get("feedback_items", [])

        # Ensure section_reference is set
        for item in feedback_items:
            if not item.get("section_reference"):
                item["section_reference"] = section_name

        processing_time = time.time() - start_time
        logger.info(f"Generated {len(feedback_items)} feedback items for {section_name} in {processing_time:.2f}s")

        return feedback_items

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse feedback JSON: {e}")
        raise Exception(f"Feedback generation returned invalid JSON: {e}")

    except Exception as e:
        logger.error(f"Feedback generation failed: {e}")
        raise


async def analyze_positioning(
    draft_text: str,
    structure: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Analyze how the draft positions itself within its field.

    Args:
        draft_text: Full draft text
        structure: Document structure

    Returns:
        Positioning analysis with recommendations

    Validates: Requirement 5.1 - Critique on positioning
    """
    if not client:
        raise ValueError("OpenAI API key not configured")

    try:
        logger.info("Analyzing draft positioning")

        # Focus on introduction and abstract for positioning
        intro_text = draft_text[:6000]  # First 6000 chars typically capture intro

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": POSITIONING_ANALYSIS_PROMPT},
                {
                    "role": "user",
                    "content": f"Analyze the positioning of this research draft:\n\n{intro_text}"
                }
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=1500,
            **get_completion_params()  # Enable zero data retention
        )

        positioning_json = response.choices[0].message.content
        positioning = json.loads(positioning_json)

        logger.info("Positioning analysis completed")

        return positioning

    except Exception as e:
        logger.error(f"Positioning analysis failed: {e}")
        raise


async def assess_argument_structure(
    claims: List[Dict[str, Any]],
    structure: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Assess the logical flow and argument structure of the draft.

    Analyzes:
    - Claim progression and coherence
    - Evidence support for claims
    - Logical gaps in argumentation
    - Section flow

    Args:
        claims: Extracted claims from draft
        structure: Document structure

    Returns:
        Argument structure assessment

    Validates: Requirement 5.2 - Identify weaknesses in logical flow
    """
    assessment = {
        "total_claims": len(claims),
        "claims_by_section": {},
        "structural_issues": [],
        "recommendations": []
    }

    # Group claims by section
    for claim in claims:
        section = claim.get("section_location", "Unknown")
        if section not in assessment["claims_by_section"]:
            assessment["claims_by_section"][section] = []
        assessment["claims_by_section"][section].append(claim)

    # Check for argumentative coherence
    unsupported_claims = [c for c in claims if c.get("requires_citation") and not c.get("existing_citations")]

    if unsupported_claims:
        assessment["structural_issues"].append(
            f"{len(unsupported_claims)} claims lack citation support"
        )
        assessment["recommendations"].append(
            "Strengthen argument by providing citations for unsupported claims"
        )

    # Check claim importance distribution
    high_importance_claims = [c for c in claims if c.get("importance_score", 0) > 0.7]

    if not high_importance_claims:
        assessment["structural_issues"].append(
            "No high-importance claims identified - core argument may be unclear"
        )
        assessment["recommendations"].append(
            "Clarify the main argument and key contributions"
        )

    # Check section balance
    sections = structure.get("sections", [])
    if len(sections) > 0:
        claims_per_section = {
            s.get("title", "Unknown"): len([
                c for c in claims
                if c.get("section_location") == s.get("title")
            ])
            for s in sections
        }

        # Results/Discussion should have substantive claims
        for section_type in ["results", "discussion"]:
            matching_sections = [
                s for s in sections
                if s.get("type") == section_type
            ]
            if matching_sections:
                section_title = matching_sections[0].get("title")
                if claims_per_section.get(section_title, 0) < 2:
                    assessment["structural_issues"].append(
                        f"Limited argumentation in {section_title} section"
                    )

    logger.info("Argument structure assessment completed")

    return assessment


async def evaluate_evidence_strength(
    claims: List[Dict[str, Any]],
    citation_quality: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Evaluate the strength of evidence supporting claims.

    Args:
        claims: Extracted claims
        citation_quality: Citation quality analysis results

    Returns:
        Evidence strength evaluation

    Validates: Requirement 5.4 - Assess evidence strength
    """
    evaluation = {
        "overall_strength": "strong",
        "weak_claims": [],
        "recommendations": []
    }

    # Identify claims with weak evidence
    for claim in claims:
        importance = claim.get("importance_score", 0.5)
        citations = claim.get("existing_citations", [])
        requires_citation = claim.get("requires_citation", True)

        # High-importance claims need strong evidence
        if importance > 0.7 and requires_citation:
            if len(citations) == 0:
                evaluation["weak_claims"].append({
                    "claim_text": claim.get("claim_text", "")[:100],
                    "issue": "No citations for high-importance claim",
                    "severity": "critical"
                })
            elif len(citations) == 1:
                evaluation["weak_claims"].append({
                    "claim_text": claim.get("claim_text", "")[:100],
                    "issue": "Single citation for high-importance claim",
                    "severity": "major"
                })

    # Overall strength assessment
    if len(evaluation["weak_claims"]) > len(claims) * 0.3:
        evaluation["overall_strength"] = "weak"
        evaluation["recommendations"].append(
            "Significant portion of claims lack adequate evidence support"
        )
    elif len(evaluation["weak_claims"]) > 0:
        evaluation["overall_strength"] = "moderate"
        evaluation["recommendations"].append(
            "Some high-importance claims need stronger evidence"
        )

    logger.info(f"Evidence strength evaluation: {evaluation['overall_strength']}")

    return evaluation


# ============================================
# Feedback Validation and Quality Assurance
# ============================================

def categorize_feedback_severity(impact_score: float, importance: float) -> str:
    """
    Categorize feedback severity based on impact and importance.

    Args:
        impact_score: Impact of the issue (0.0 to 1.0)
        importance: Importance of the affected section (0.0 to 1.0)

    Returns:
        Severity category: "critical", "major", "minor", "suggestion"

    Validates: Requirement 5.4 - Severity classification
    """
    # Calculate combined severity score
    severity_score = (impact_score + importance) / 2

    if impact_score > 0.8 and importance > 0.8:
        return "critical"
    elif severity_score > 0.6:
        return "major"
    elif severity_score > 0.4:
        return "minor"
    else:
        return "suggestion"


def ensure_no_rewriting_in_feedback(feedback_text: str) -> Dict[str, Any]:
    """
    Validate that feedback does not contain rewriting or prescriptive text.

    Checks for forbidden phrases that indicate the feedback is providing
    rewritten content rather than critique and suggestions.

    Args:
        feedback_text: The feedback text to validate

    Returns:
        Validation result: {valid: bool, violation_type: str, details: str}

    Validates: Requirement 5.3 - No auto-rewriting
    """
    forbidden_phrases = [
        "rewrite as:",
        "change to:",
        "replace with:",
        "here is the rewritten",
        "corrected version:",
        "new text:",
        "revised paragraph:",
        "updated text:",
        "better version:",
        "improved text:"
    ]

    feedback_lower = feedback_text.lower()

    for phrase in forbidden_phrases:
        if phrase in feedback_lower:
            return {
                "valid": False,
                "violation_type": "rewriting_detected",
                "details": f"Feedback contains rewriting phrase: '{phrase}'"
            }

    return {
        "valid": True,
        "violation_type": None,
        "details": "Feedback contains only critique and suggestions"
    }


def validate_feedback_content(feedback: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate that feedback meets quality standards.

    Checks:
    - Has required fields
    - Contains no rewriting
    - Has actionable improvements
    - Uses appropriate severity

    Args:
        feedback: Feedback dictionary to validate

    Returns:
        Validation result: {valid: bool, issues: List[str]}

    Validates: Requirements 5.1, 5.2, 5.3, 5.4
    """
    issues = []

    # Check required fields
    required_fields = ["feedback_type", "severity", "feedback_text", "suggested_improvements"]
    for field in required_fields:
        if field not in feedback:
            issues.append(f"Missing required field: {field}")

    if issues:
        return {"valid": False, "issues": issues}

    # Check feedback type is valid
    valid_types = ["positioning", "argumentation", "coverage", "methodology", "evidence"]
    if feedback["feedback_type"] not in valid_types:
        issues.append(f"Invalid feedback_type: {feedback['feedback_type']}")

    # Check severity is valid
    valid_severities = ["critical", "major", "minor", "suggestion"]
    if feedback["severity"] not in valid_severities:
        issues.append(f"Invalid severity: {feedback['severity']}")

    # Check no rewriting in feedback text
    rewrite_check = ensure_no_rewriting_in_feedback(feedback["feedback_text"])
    if not rewrite_check["valid"]:
        issues.append(f"Feedback contains rewriting: {rewrite_check['details']}")

    # Check suggested improvements is non-empty list
    improvements = feedback.get("suggested_improvements", [])
    if not isinstance(improvements, list) or len(improvements) == 0:
        issues.append("Feedback must include suggested improvements")

    # Check improvements don't contain rewriting
    for improvement in improvements:
        improvement_check = ensure_no_rewriting_in_feedback(improvement)
        if not improvement_check["valid"]:
            issues.append(f"Improvement contains rewriting: {improvement_check['details']}")

    return {
        "valid": len(issues) == 0,
        "issues": issues
    }


# ============================================
# Complete Reviewer Feedback Pipeline
# ============================================

async def generate_reviewer_feedback(draft_id: str) -> Dict[str, Any]:
    """
    Generate comprehensive reviewer-style feedback for a draft.

    Complete pipeline:
    1. Fetch draft, structure, claims, and gaps
    2. Analyze positioning within field
    3. Assess argument structure and logical flow
    4. Evaluate evidence strength
    5. Generate section-specific feedback
    6. Store feedback in database

    Args:
        draft_id: Draft identifier

    Returns:
        Comprehensive reviewer feedback report

    Validates: Requirements 5.1, 5.2, 5.3, 5.4
    """
    try:
        logger.info(f"Generating reviewer feedback for draft_id={draft_id}")

        # 1. Fetch draft
        draft_response = supabase.table("drafts").select("*").eq("id", draft_id).single().execute()

        if not draft_response.data:
            raise ValueError(f"Draft not found: {draft_id}")

        draft = draft_response.data

        # 2. Fetch draft analysis (structure)
        analysis_response = supabase.table("draft_analysis").select("*").eq("draft_id", draft_id).single().execute()

        if not analysis_response.data:
            raise ValueError(f"Draft analysis not found. Run structural analysis first.")

        analysis = analysis_response.data
        structure = analysis.get("structure", {})

        # 3. Fetch claims
        claims_response = supabase.table("draft_claims").select("*").eq("draft_id", draft_id).execute()
        claims = claims_response.data or []

        # 4. Fetch coverage gaps
        gaps_response = supabase.table("coverage_gaps").select("*").eq("draft_id", draft_id).execute()
        gaps = gaps_response.data or []

        # 5. Download draft text
        file_url = draft.get("file_url")
        if not file_url:
            raise ValueError("Draft has no file URL")

        path_parts = file_url.split("/drafts/")
        storage_path = path_parts[1]
        file_bytes = supabase.storage.from_("drafts").download(storage_path)

        from app.services.draft_processing import extract_text
        file_type = draft.get("file_type", "pdf")
        extracted_data = await extract_text(file_bytes, file_type)
        draft_text = extracted_data["full_text"]

        # Get sections from extracted data (available for PDFs via GROBID)
        grobid_sections = extracted_data.get("sections", [])

        # Build context for feedback generation
        draft_context = {
            "claims": claims,
            "gaps": gaps,
            "structure": structure
        }

        # 6. Analyze positioning
        positioning = await analyze_positioning(draft_text, structure)

        # 7. Assess argument structure
        argument_assessment = await assess_argument_structure(claims, structure)

        # 8. Evaluate evidence strength
        from app.services.citation_quality import analyze_draft_citation_quality
        citation_quality = await analyze_draft_citation_quality(draft_id, draft.get("project_id"))

        evidence_evaluation = await evaluate_evidence_strength(claims, citation_quality)

        # 9. Generate section-specific feedback
        all_feedback = []
        sections = structure.get("sections", [])

        for section in sections[:5]:  # Limit to first 5 sections for token economy
            section_title = section.get("title", "Unknown")
            section_type = section.get("type", "other")

            # Extract section text (simplified - would use proper extraction in production)
            section_feedback = await generate_section_feedback(
                draft_text[:2000],  # Simplified
                section_title,
                section_type,
                draft_context
            )

            all_feedback.extend(section_feedback)

        # 10. Add high-level feedback based on positioning and argument analysis
        if positioning:
            # Add positioning feedback
            positioning_assessment = positioning.get("positioning_assessment", {})

            if positioning_assessment.get("contribution_clarity") in ["unclear", "absent"]:
                all_feedback.append({
                    "feedback_type": "positioning",
                    "severity": "critical",
                    "section_reference": "Introduction",
                    "feedback_text": "The contribution of this work is not clearly stated. " +
                                   "Readers need explicit articulation of what is novel and why it matters.",
                    "suggested_improvements": positioning.get("recommendations", []),
                    "reasoning": "Clear contribution statement is essential for acceptance"
                })

        if argument_assessment:
            issues = argument_assessment.get("structural_issues", [])
            if issues:
                all_feedback.append({
                    "feedback_type": "argumentation",
                    "severity": "major",
                    "section_reference": "Overall Structure",
                    "feedback_text": "Argument structure issues identified: " + "; ".join(issues),
                    "suggested_improvements": argument_assessment.get("recommendations", []),
                    "reasoning": "Logical flow is critical for persuasive research"
                })

        # 11. Store feedback in database with line positioning
        feedback_records = []
        for feedback in all_feedback:
            # Extract section reference text for line positioning
            section_ref = feedback.get("section_reference", "")
            line_number = None
            char_start = None
            char_end = None
            text_snippet = None
            section_id = None
            char_offset_from_section = None
            pdf_coordinates = None
            match_confidence = None

            # Try to locate section in draft_text for line positioning
            if section_ref and section_ref in draft_text:
                section_start = draft_text.find(section_ref)
                if section_start >= 0:
                    text_before = draft_text[:section_start]
                    line_number = text_before.count('\n') + 1  # 1-indexed

                    # Find line start
                    line_start_pos = draft_text.rfind('\n', 0, section_start) + 1
                    char_start = section_start - line_start_pos
                    char_end = char_start + len(section_ref)

                    # Extract snippet
                    snippet_start = max(0, section_start - 50)
                    snippet_end = min(len(draft_text), section_start + len(section_ref) + 50)
                    text_snippet = draft_text[snippet_start:snippet_end].strip()

                    # NEW: Section-based location tracking (multi-strategy)
                    if grobid_sections:
                        # Find matching section
                        for section in grobid_sections:
                            if section_ref in section.get("content", ""):
                                section_id = section.get("id")

                                # Calculate offset from section start
                                section_content = section.get("content", "")
                                section_content_start = draft_text.find(section_content)
                                if section_content_start >= 0:
                                    char_offset_from_section = section_start - section_content_start
                                    match_confidence = 0.9  # High confidence

                                # Add PDF coordinates if available
                                if section.get("coordinates"):
                                    pdf_coordinates = section.get("coordinates")
                                    match_confidence = max(match_confidence or 0, 0.8)

                                break

                        if not section_id:
                            # Section found in text but not in GROBID sections - use line-based
                            match_confidence = 0.6
                    else:
                        # No GROBID sections - use line-based fallback
                        match_confidence = 0.6

            record = {
                "draft_id": draft_id,
                "feedback_type": feedback.get("feedback_type", "argumentation"),
                "feedback_text": feedback.get("feedback_text", ""),
                "severity": feedback.get("severity", "minor"),
                "section_reference": section_ref,
                "suggestions": feedback.get("suggested_improvements", []),
                # EXISTING: Line positioning fields
                "line_number": line_number,
                "char_start": char_start,
                "char_end": char_end,
                "text_snippet": text_snippet,
                # NEW: Multi-strategy location tracking
                "section_id": section_id,
                "char_offset_from_section": char_offset_from_section,
                "pdf_coordinates": pdf_coordinates,
                "match_confidence": match_confidence
            }
            feedback_records.append(record)

        if feedback_records:
            supabase.table("reviewer_feedback").insert(feedback_records).execute()

        logger.info(f"Generated {len(all_feedback)} feedback items")

        # 12. Generate summary report
        report = {
            "draft_id": draft_id,
            "total_feedback_items": len(all_feedback),
            "feedback_by_severity": {
                "critical": len([f for f in all_feedback if f.get("severity") == "critical"]),
                "major": len([f for f in all_feedback if f.get("severity") == "major"]),
                "minor": len([f for f in all_feedback if f.get("severity") == "minor"]),
                "suggestion": len([f for f in all_feedback if f.get("severity") == "suggestion"])
            },
            "feedback_by_type": {
                "positioning": len([f for f in all_feedback if f.get("feedback_type") == "positioning"]),
                "argumentation": len([f for f in all_feedback if f.get("feedback_type") == "argumentation"]),
                "coverage": len([f for f in all_feedback if f.get("feedback_type") == "coverage"]),
                "methodology": len([f for f in all_feedback if f.get("feedback_type") == "methodology"])
            },
            "positioning_analysis": positioning,
            "argument_assessment": argument_assessment,
            "evidence_evaluation": evidence_evaluation,
            "feedback_items": all_feedback[:20]  # Top 20 items in response
        }

        return report

    except Exception as e:
        logger.error(f"Reviewer feedback generation failed: {str(e)}")
        raise

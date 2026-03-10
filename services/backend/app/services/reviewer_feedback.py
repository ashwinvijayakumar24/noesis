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
      "feedback_type": "positioning|argumentation|coverage|methodology|evidence|clarity|logic",
      "severity": "critical|major|minor|suggestion",
      "section_reference": "Which section this applies to",
      "line_reference": "Specific line number or paragraph location (e.g., 'Line 45-47', 'Paragraph 3', 'Introduction, para 2')",
      "feedback_text": "Detailed critique in academic reviewer style",
      "specific_issue": "The exact problem identified (e.g., 'Unsupported claim', 'Missing citation', 'Weak methodology justification')",
      "suggested_improvements": [
        "Concrete, actionable suggestion 1 with specific guidance",
        "Concrete, actionable suggestion 2 with specific guidance",
        "Concrete, actionable suggestion 3 with specific guidance"
      ],
      "example_fix": "Brief example of how to address this (NOT a rewrite, but a directional example)",
      "reasoning": "Why this matters for the work and potential reviewer concerns"
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
1. **Be ultra-specific**: Include exact line numbers, paragraph locations, or section markers
2. **Be constructive**: Provide 2-4 concrete, actionable suggestions per issue
3. **Be academic**: Use scholarly tone appropriate for peer review
4. **NO rewriting**: Never provide rewritten text. Only describe what to change
5. **Focus on substance**: Critique ideas, arguments, and positioning
6. **Prioritize**: Mark critical issues clearly with severity levels
7. **Be fair**: Acknowledge strengths alongside weaknesses
8. **Provide context**: Explain why each issue matters for peer review acceptance
9. **Give examples**: Provide brief directional examples (not rewrites) where helpful

Examples of EXCELLENT feedback:

**Example 1: Unsupported Claim (Critical)**
```json
{
  "feedback_type": "evidence",
  "severity": "critical",
  "section_reference": "Results",
  "line_reference": "Paragraph 2, lines 45-47",
  "feedback_text": "The claim that 'our model outperforms all existing approaches' lacks empirical support. No baseline comparisons, metrics, or statistical significance tests are provided.",
  "specific_issue": "Unsupported comparative claim without quantitative evidence",
  "suggested_improvements": [
    "Add a comparison table showing your model vs. 3-5 recent baselines (SOTA methods from 2022-2024)",
    "Include standard metrics (accuracy, F1, precision/recall) with confidence intervals or standard deviations",
    "Report statistical significance tests (t-test, Wilcoxon) with p-values < 0.05",
    "Cite the baseline methods being compared against"
  ],
  "example_fix": "For instance, you could add: 'Our model achieved 95.2% accuracy (±1.1%), significantly outperforming BERT (92.3%, p<0.01) and GPT-3 (93.1%, p<0.05) on the test set.'",
  "reasoning": "Reviewers will reject claims of superiority without rigorous empirical validation. Comparative claims are the most scrutinized in peer review."
}
```

**Example 2: Positioning Issue (Major)**
```json
{
  "feedback_type": "positioning",
  "severity": "major",
  "section_reference": "Introduction",
  "line_reference": "Paragraph 1",
  "feedback_text": "The introduction does not clearly articulate the research gap this work addresses. It jumps directly from describing the general problem to proposing your solution.",
  "specific_issue": "Missing explicit gap identification and novelty statement",
  "suggested_improvements": [
    "Add a paragraph explicitly stating what prior work has NOT done",
    "Use transition phrases like 'However, existing approaches fail to...', 'Despite progress, a key limitation remains...'",
    "Clearly state your specific contribution that fills this gap",
    "Position your work relative to 2-3 most related recent papers (2023-2024)"
  ],
  "example_fix": "For example: 'While Smith et al. (2023) addressed X and Jones et al. (2024) improved Y, neither approach handles Z due to [limitation]. Our work is the first to...'",
  "reasoning": "Reviewers need to immediately understand the gap and your unique contribution. Without this, they may question the novelty and significance of your work."
}
```

**Example 3: Methodology Gap (Major)**
```json
{
  "feedback_type": "methodology",
  "severity": "major",
  "section_reference": "Methods",
  "line_reference": "Section 3.2, after data collection description",
  "feedback_text": "The methodology section describes data collection but provides no detail on the analysis procedure. Reviewers cannot assess rigor or reproduce your work.",
  "specific_issue": "Missing analytical pipeline and reproducibility details",
  "suggested_improvements": [
    "Add a subsection (3.3 Analytical Procedure) detailing step-by-step analysis",
    "Specify preprocessing steps (cleaning, normalization, feature extraction)",
    "Describe model architecture, hyperparameters, and training procedure",
    "Include validation strategy (cross-validation, train-test split ratios)",
    "Mention tools/libraries used (scikit-learn 1.2.0, PyTorch 2.0, etc.)"
  ],
  "example_fix": "Add a flow diagram: Data Collection → Preprocessing (remove outliers, normalize) → Feature Extraction (TF-IDF) → Model Training (5-fold CV) → Evaluation (accuracy, F1)",
  "reasoning": "Methodological transparency is essential for peer review. Reviewers need to assess whether your approach is sound and whether results are reproducible."
}
```

**Example 4: Literature Coverage (Minor)**
```json
{
  "feedback_type": "coverage",
  "severity": "minor",
  "section_reference": "Related Work",
  "line_reference": "Section 2, paragraph 3",
  "feedback_text": "The related work discusses transformer-based approaches but omits recent state-of-the-art models from 2024 (e.g., LLaMA 3, Claude 3, Gemini 1.5).",
  "specific_issue": "Incomplete literature coverage - missing recent SOTA models",
  "suggested_improvements": [
    "Add a paragraph on 2024 large language models and their relevant contributions",
    "Compare your approach to these recent models (even if just conceptually)",
    "Explain why your approach differs from or improves upon these baselines",
    "Cite 3-5 key papers from 2024 in your domain"
  ],
  "example_fix": "For instance: 'Recent models like LLaMA 3 (Meta, 2024) and Claude 3 (Anthropic, 2024) have shown X, but our approach uniquely addresses Y by...'",
  "reasoning": "Reviewers expect awareness of cutting-edge work. Missing recent papers suggests the work may be outdated or the authors are not engaged with the latest research."
}
```

Examples of BAD feedback (NEVER do this):
- "Rewrite the introduction as: [new text]" ❌ (This is rewriting)
- "Change this sentence to: [exact new sentence]" ❌ (This is rewriting)
- "The paper is bad" ❌ (Too vague, not constructive, no specifics)
- "Fix the methodology" ❌ (No line reference, no concrete suggestions)
- "This needs improvement" ❌ (Generic, not actionable)

Remember: Your feedback should feel like it came from a senior researcher who carefully read the paper and wants to help improve it for publication.
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
# Helper Functions
# ============================================

def map_severity_to_priority(severity: str) -> str:
    """
    Map severity level to priority level for UI display.

    Severity (from AI reviewer feedback):
    - critical, major -> high priority (must address)
    - minor -> medium priority (should address)
    - suggestion -> low priority (consider addressing)

    Args:
        severity: Severity level (critical, major, minor, suggestion)

    Returns:
        Priority level (high, medium, low)
    """
    severity_lower = severity.lower()

    if severity_lower in ['critical', 'major']:
        return 'high'
    elif severity_lower == 'minor':
        return 'medium'
    else:  # suggestion or other
        return 'low'


# ============================================
# Feedback Generation Functions
# ============================================

def _extract_section_text(section_title: str, grobid_sections: list, draft_text: str) -> str:
    """
    Extract actual text for a section.

    Tries in order:
    1. GROBID section content (most accurate, available for PDFs)
    2. Position-based extraction using heading regex
    3. Fallback to a portion of the full text near the heading
    """
    # 1. GROBID section content
    if grobid_sections:
        for gs in grobid_sections:
            if gs.get("title", "").strip().lower() == section_title.strip().lower():
                content = gs.get("content", "")
                if content:
                    return content[:4000]

    # 2. Position-based extraction: find heading, take text until next heading
    heading_pattern = re.compile(
        r'(?:^|\n)(' + re.escape(section_title) + r')\s*\n(.*?)(?=\n[A-Z][^\n]{3,60}\n|\Z)',
        re.IGNORECASE | re.DOTALL
    )
    match = heading_pattern.search(draft_text)
    if match:
        return match.group(2)[:4000]

    # 3. Find heading position and grab following text
    title_lower = section_title.lower()
    text_lower = draft_text.lower()
    pos = text_lower.find(title_lower)
    if pos >= 0:
        start = pos + len(section_title)
        return draft_text[start:start + 4000]

    # 4. Last resort: return first 2000 chars (same as before, better than nothing)
    return draft_text[:2000]


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

        # Note: Temperature removed - GPT-5.2 models use default temperature=1.0
        response = client.chat.completions.create(
            model="gpt-5.2-chat-latest",
            messages=[
                {"role": "system", "content": REVIEWER_FEEDBACK_PROMPT},
                {
                    "role": "user",
                    "content": f"{context_str}\n\nProvide reviewer feedback for this section:\n\n{analysis_text}"
                }
            ],
            max_completion_tokens=2000,
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

        # Note: Temperature removed - GPT-5.2 models use default temperature=1.0
        response = client.chat.completions.create(
            model="gpt-5.2-chat-latest",
            messages=[
                {"role": "system", "content": POSITIONING_ANALYSIS_PROMPT},
                {
                    "role": "user",
                    "content": f"Analyze the positioning of this research draft:\n\n{intro_text}"
                }
            ],
            max_completion_tokens=1500,
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

def _get_source_grounding(feedback_text: str, project_id: str) -> Optional[Dict[str, Any]]:
    """
    Find the most relevant literature passage that grounds this feedback item.

    Returns the top matching chunk from the project's literature with:
    - document_title: Source paper name
    - excerpt: Relevant passage (up to 300 chars)
    - similarity: Cosine similarity score (0-1)
    """
    try:
        from app.services.rag_retrieval import retrieve_relevant_chunks
        chunks = retrieve_relevant_chunks(
            project_id=project_id,
            query=feedback_text[:500],  # Use first 500 chars as search query
            limit=1,
            similarity_threshold=0.25,
        )
        if chunks:
            chunk = chunks[0]
            similarity = chunk.get("similarity", 0.0)
            return {
                "document_title": chunk.get("document_title") or chunk.get("title", "Unknown source"),
                "excerpt": chunk.get("content", "")[:300].strip(),
                "similarity": round(float(similarity), 3),
                "chunk_index": chunk.get("chunk_index", 0),
            }
        return None
    except Exception as e:
        logger.debug(f"Source grounding lookup skipped: {e}")
        return None


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

        for section in sections:  # Process all sections
            section_title = section.get("title", "Unknown")
            section_type = section.get("type", "other")

            # Extract actual section content: prefer GROBID content, fallback to position-based slicing
            section_text = _extract_section_text(section_title, grobid_sections, draft_text)

            section_feedback = await generate_section_feedback(
                section_text,
                section_title,
                section_type,
                draft_context
            )

            all_feedback.extend(section_feedback)

        # 10. Add methodology comparison feedback (uses document_methods table)
        project_id = draft.get("project_id")
        if project_id:
            from app.services.section_analysis import compare_methodology_to_literature, analyze_results_section

            # Compare methodology against literature
            methodology_feedback = await compare_methodology_to_literature(draft_id, project_id)
            if methodology_feedback:
                logger.info(f"Added {len(methodology_feedback)} methodology comparison feedback items")
                all_feedback.extend(methodology_feedback)

            # Analyze results section against literature findings
            results_feedback = await analyze_results_section(draft_id, project_id)
            if results_feedback:
                logger.info(f"Added {len(results_feedback)} results section feedback items")
                all_feedback.extend(results_feedback)

        # 11. Add high-level feedback based on positioning and argument analysis
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

        # 11b. Enrich feedback items with source grounding from literature
        if project_id:
            for feedback_item in all_feedback:
                grounding = _get_source_grounding(
                    feedback_item.get("feedback_text", ""),
                    project_id
                )
                feedback_item["source_grounding"] = grounding
                # Set confidence level based on grounding similarity
                if grounding:
                    sim = grounding.get("similarity", 0)
                    if sim >= 0.65:
                        feedback_item["confidence_level"] = "high"
                    elif sim >= 0.45:
                        feedback_item["confidence_level"] = "medium"
                    else:
                        feedback_item["confidence_level"] = "low"
                else:
                    feedback_item["confidence_level"] = "medium"

        # 12. Store feedback in database with line positioning
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

            severity = feedback.get("severity", "minor")
            priority = map_severity_to_priority(severity)

            record = {
                "draft_id": draft_id,
                "feedback_type": feedback.get("feedback_type", "argumentation"),
                "feedback_text": feedback.get("feedback_text", ""),
                "severity": severity,
                "priority": priority,  # Priority mapping (high/medium/low)
                "section_reference": section_ref,
                "suggestions": feedback.get("suggested_improvements", []),
                # NEW: Enhanced feedback fields
                "line_reference": feedback.get("line_reference"),  # Specific line/para reference
                "specific_issue": feedback.get("specific_issue"),  # Exact problem identified
                "example_fix": feedback.get("example_fix"),  # Directional example
                "reasoning": feedback.get("reasoning"),  # Why this matters
                # EXISTING: Line positioning fields
                "line_number": line_number,
                "char_start": char_start,
                "char_end": char_end,
                "text_snippet": text_snippet,
                # NEW: Multi-strategy location tracking
                "section_id": section_id,
                "char_offset_from_section": char_offset_from_section,
                "pdf_coordinates": pdf_coordinates,
                "match_confidence": match_confidence,
                # Source grounding: literature passage that informed this feedback
                "source_grounding": feedback.get("source_grounding"),
                "confidence_level": feedback.get("confidence_level", "medium"),
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

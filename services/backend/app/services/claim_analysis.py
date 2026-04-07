"""
Claim Analysis Service

Identifies and extracts claims from research drafts, categorizes them by type,
and maps them to existing citations.

This service provides:
- AI-powered claim identification
- Claim categorization (empirical, theoretical, methodological)
- Citation extraction from draft text
- Importance scoring for claims
- Distinction between original contributions and claims requiring support

Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 3.1
"""

import json
import time
import re
from typing import Dict, Any, List, Optional, Tuple
from app.core.config import settings
from app.core.supabase_client import supabase
from app.core.logging_config import get_logger
from app.core.openai_client import get_openai_client, get_completion_params
import datetime

logger = get_logger(__name__)

# Initialize OpenAI client
client = get_openai_client()


# ============================================
# AI Prompts for Claim Extraction
# ============================================

CLAIM_EXTRACTION_PROMPT = """You are an expert academic reviewer analyzing research drafts with deep expertise in identifying substantive claims.

Extract ALL meaningful claims, hypotheses, and assertions from this research draft section.
Be thorough - aim to extract 15-25 claims per 10-page draft, capturing both primary and supporting arguments.

Respond with ONLY valid JSON.

Return this exact structure:
{
  "claims": [
    {
      "claim_text": "The exact text of the claim as it appears in the draft",
      "claim_type": "empirical|theoretical|methodological",
      "claim_subtype": "factual|causal|comparative|normative|descriptive",
      "claim_level": "thesis|main|supporting|contextual",
      "evidence_type": "experimental|observational|theoretical|computational|qualitative|mixed",
      "confidence_level": "definitive|tentative|exploratory|speculative",
      "section_location": "section name where claim appears",
      "importance_score": 0.0-1.0,
      "confidence_score": 0.0-1.0,
      "requires_citation": true|false,
      "existing_citations": ["Author (Year)", "Author et al. (Year)"],
      "reasoning": "Detailed explanation of claim type, importance, and evidence requirements"
    }
  ]
}

Confidence Score (0.0 to 1.0):
- 1.0: Very confident this is a substantive claim
- 0.7-0.9: Confident this is a claim
- 0.4-0.6: Somewhat confident (borderline case)
- 0.0-0.3: Low confidence (may not be a claim)
- Claims with confidence < 0.6 will be hidden by default to reduce hallucinations

Claim Types (Primary Classification):
- **empirical**: Data-based claims about observations, measurements, or experimental results
  Example: "The system achieved 95% accuracy on the test dataset"

- **theoretical**: Conceptual claims about frameworks, models, or explanations
  Example: "Attention mechanisms enable better long-range dependencies"

- **methodological**: Claims about approaches, techniques, or procedures
  Example: "We employed a mixed-methods approach combining surveys and interviews"

Claim Subtypes (Secondary Classification):
- **factual**: States a fact or observation ("X exists", "Y was measured at Z")
- **causal**: Claims a cause-effect relationship ("X causes Y", "X leads to Y")
- **comparative**: Compares entities or methods ("X is better than Y", "X differs from Y in Z")
- **normative**: Makes a value judgment or recommendation ("X should be done", "Y is important")
- **descriptive**: Describes a phenomenon or pattern ("X exhibits property Y")

Claim Levels (Hierarchy):
- **thesis**: Core thesis claim, primary research question or contribution (1-3 per paper)
- **main**: Major findings or key supporting claims (5-10 per paper)
- **supporting**: Supporting details or secondary arguments (10-20 per paper)
- **contextual**: Background information or minor details (numerous)

Evidence Types:
- **experimental**: Based on controlled experiments with data
- **observational**: Based on observations without manipulation
- **theoretical**: Based on logical reasoning or mathematical proof
- **computational**: Based on simulations or computational analysis
- **qualitative**: Based on interviews, surveys, case studies
- **mixed**: Combines multiple evidence types

Confidence Levels (Author's Certainty):
- **definitive**: Strongly stated, presented as established fact
- **tentative**: Cautiously stated, acknowledges uncertainty
- **exploratory**: Presented as preliminary or investigative
- **speculative**: Presented as conjecture or hypothesis

Importance Score (0.0 to 1.0):
- 1.0: Core thesis claim, primary research question
- 0.7-0.9: Major finding or key supporting claim
- 0.4-0.6: Supporting detail or contextual claim
- 0.1-0.3: Minor detail or background information

Requires Citation:
- true: Claim builds on prior work and needs literature support
- false: Original contribution by the author(s)

Existing Citations:
- Extract any citation references found near this claim
- Format: "Author (Year)" or "Author et al. (Year)"
- Empty array if no citations found

Guidelines for Comprehensive Extraction:
1. **Be thorough**: Extract 15-25 claims per 10-page section (vs previous 5-15)
2. **Capture hierarchy**: Identify thesis-level claims, main claims, and supporting claims
3. **Look for nuance**: Distinguish between definitive vs tentative claims
4. **Identify patterns**: Spot factual, causal, comparative, and normative claims
5. **Context matters**: Consider how claims relate to each other (main vs supporting)
6. **Evidence assessment**: Identify what type of evidence supports each claim
7. **Citation needs**: Be specific about which claims MUST have citations
8. **Exact wording**: Extract claims as they appear in the text

Examples of Claims to Extract:

**Thesis-level (importance: 1.0)**:
- "We propose a novel attention mechanism that reduces computational complexity by 40%"
- "This study demonstrates that X causes Y in previously unexplored contexts"

**Main claims (importance: 0.7-0.9)**:
- "Our model achieves 95% accuracy on benchmark dataset Z"
- "The results show a significant correlation between X and Y (p < 0.01)"
- "Previous work has not adequately addressed limitation Z"

**Supporting claims (importance: 0.4-0.6)**:
- "Dataset X contains 10,000 labeled examples"
- "We used a train-test split of 80-20"
- "The attention mechanism was inspired by transformer architecture"

**Contextual claims (importance: 0.1-0.3)**:
- "Machine learning has applications in healthcare"
- "Data quality is important for model performance"

Be precise, be thorough, and extract the full argumentative structure of the draft.
"""


CITATION_EXTRACTION_PROMPT = """You are an expert at extracting citations from academic text.

Extract all citation references from this text segment. Respond with ONLY valid JSON.

Return this exact structure:
{
  "citations": [
    {
      "citation_string": "Author (Year)",
      "authors": ["Author"],
      "year": "Year",
      "context": "Brief snippet of text surrounding the citation"
    }
  ]
}

Guidelines:
- Extract citations in any format: (Author, Year), Author (Year), Author et al. (Year), [1], [Author2023]
- Normalize to "Author (Year)" or "Author et al. (Year)" format
- Include the immediate context (10-20 words) around each citation
- Handle multiple citation formats
- Return empty array if no citations found
"""


# ============================================
# Claim Extraction Functions
# ============================================

def extract_claims_from_section(
    section_text: str,
    section_name: str,
    model: str = "gpt-5.2-chat-latest"
) -> List[Dict[str, Any]]:
    """
    Extract claims from a single document section using AI.

    Args:
        section_text: Text content of the section
        section_name: Name of the section (e.g., "Introduction", "Methods")
        model: OpenAI model to use

    Returns:
        List of extracted claims with metadata

    Raises:
        Exception: If extraction fails
    """
    if not client:
        raise ValueError("OpenAI API key not configured")

    start_time = time.time()

    try:
        logger.info(f"Extracting claims from section: {section_name} (length: {len(section_text)} chars)")

        # Use first 6000 characters of section to stay within token limits
        analysis_text = section_text[:6000]

        # Note: Temperature removed - GPT-5.2 models use default temperature=1.0
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": CLAIM_EXTRACTION_PROMPT},
                {
                    "role": "user",
                    "content": f"Extract claims from this {section_name} section:\n\n{analysis_text}"
                }
            ],
            max_completion_tokens=2000,
            **get_completion_params()  # Enable zero data retention
        )

        claims_json = response.choices[0].message.content
        claims_data = json.loads(claims_json)

        # Add section_location to each claim
        claims = claims_data.get("claims", [])
        for claim in claims:
            claim["section_location"] = section_name

        processing_time = time.time() - start_time
        logger.info(f"Extracted {len(claims)} claims from {section_name} in {processing_time:.2f}s")

        return claims

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse claims JSON: {e}")
        raise Exception(f"Claim extraction returned invalid JSON: {e}")

    except Exception as e:
        logger.error(f"Claim extraction failed: {e}")
        raise Exception(f"Failed to extract claims: {str(e)}")


def extract_claims_from_draft(
    draft_text: str,
    structure: Dict[str, Any],
    model: str = "gpt-5.2-chat-latest",
    sections_with_content: Optional[List[Dict[str, Any]]] = None
) -> List[Dict[str, Any]]:
    """
    Extract claims from entire draft using document structure.

    Processes each section independently and combines results.

    Args:
        draft_text: Full text of the draft
        structure: Document structure from draft_analysis
        model: OpenAI model to use

    Returns:
        List of all extracted claims across all sections

    Raises:
        Exception: If extraction fails
    """
    all_claims = []

    # Get sections from structure
    sections = structure.get("sections", [])

    if not sections:
        # If no structured sections, extract from full text
        logger.warning("No sections found in structure, analyzing full text")
        claims = extract_claims_from_section(draft_text, "Full Document", model)
        all_claims.extend(claims)
        return all_claims

    # Build content lookup from sections_with_content (GROBID sections have full text)
    content_by_title: Dict[str, str] = {}
    if sections_with_content:
        for s in sections_with_content:
            title = s.get("title", "")
            content = s.get("content", "")
            if title and content:
                content_by_title[title] = content

    # Process each section
    for section in sections:
        section_title = section.get("title", "Unknown Section")
        section_type = section.get("type", "other")

        # Skip abstract for claim extraction (usually summarizes claims from other sections)
        if section_type == "abstract":
            continue

        # Use actual section content when available; fall back to full draft text
        section_text = content_by_title.get(section_title) or draft_text

        try:
            claims = extract_claims_from_section(section_text, section_title, model)
            all_claims.extend(claims)

        except Exception as e:
            logger.error(f"Failed to extract claims from {section_title}: {e}")
            # Continue with other sections

    logger.info(f"Total claims extracted: {len(all_claims)}")
    return all_claims


# ============================================
# Citation Extraction Functions
# ============================================

def extract_citations_from_text(text: str) -> List[Dict[str, Any]]:
    """
    Extract citation references from text using regex patterns.

    Supports common citation formats:
    - (Author, Year)
    - Author (Year)
    - Author et al. (Year)
    - [1], [2], etc.

    Args:
        text: Text to extract citations from

    Returns:
        List of citation dictionaries with author, year, and context
    """
    citations = []

    # Pattern 1: Author (Year) or Author et al. (Year)
    pattern1 = r'\b([A-Z][a-z]+(?:\s+et\s+al\.)?)\s+\((\d{4})\)'

    # Pattern 2: (Author, Year) or (Author et al., Year)
    pattern2 = r'\(([A-Z][a-z]+(?:\s+et\s+al\.)?)(?:,\s+)?(\d{4})\)'

    # Pattern 3: [1], [Author2023], etc.
    pattern3 = r'\[(\d+|[A-Z][a-z]+\d{4})\]'

    for pattern in [pattern1, pattern2, pattern3]:
        matches = re.finditer(pattern, text)

        for match in matches:
            if pattern == pattern3:
                # Numerical or compact citation
                ref = match.group(1)
                citation = {
                    "citation_string": f"[{ref}]",
                    "authors": ["Ref " + ref],
                    "year": ref[-4:] if len(ref) > 4 else "Unknown",
                    "context": text[max(0, match.start() - 50):min(len(text), match.end() + 50)]
                }
            else:
                author = match.group(1)
                year = match.group(2)
                citation = {
                    "citation_string": f"{author} ({year})",
                    "authors": [author],
                    "year": year,
                    "context": text[max(0, match.start() - 50):min(len(text), match.end() + 50)]
                }

            citations.append(citation)

    logger.info(f"Extracted {len(citations)} citations from text")
    return citations


def map_citations_to_claims(
    claims: List[Dict[str, Any]],
    draft_text: str,
    sections: List[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Enhance claims with multi-strategy location information.

    Strategy Priority:
    1. Section ID + char offset (90% confidence) - works for all formats
    2. PDF coordinates from GROBID (80% confidence) - PDFs only
    3. Line number + fuzzy text match (60% confidence) - fallback

    Args:
        claims: List of extracted claims
        draft_text: Full draft text
        sections: Optional GROBID sections with IDs and coordinates

    Returns:
        Claims enhanced with citation mappings and multi-strategy location data
    """
    # Split text into lines for line number calculation
    lines = draft_text.split('\n')

    for claim in claims:
        claim_text = claim.get("claim_text", "")

        # Find claim location in draft
        claim_start = draft_text.find(claim_text)

        if claim_start >= 0:
            # Calculate line number and character position
            text_before_claim = draft_text[:claim_start]
            line_number = text_before_claim.count('\n') + 1  # 1-indexed

            # Find the start of the current line
            line_start_pos = draft_text.rfind('\n', 0, claim_start) + 1
            char_start = claim_start - line_start_pos
            char_end = char_start + len(claim_text)

            # Extract 100-200 char snippet for fuzzy matching
            snippet_start = max(0, claim_start - 50)
            snippet_end = min(len(draft_text), claim_start + len(claim_text) + 50)
            text_snippet = draft_text[snippet_start:snippet_end].strip()

            # EXISTING: Line-based positioning (Strategy 3 - fallback)
            claim["line_number"] = line_number
            claim["char_start"] = char_start
            claim["char_end"] = char_end
            claim["text_snippet"] = text_snippet

            # NEW: Section-based anchoring (Strategy 1 - best)
            if sections:
                section = find_section_for_claim(claim_text, sections, draft_text)
                if section:
                    claim["section_id"] = section["id"]

                    # Calculate offset from section start
                    section_start = draft_text.find(section["content"])
                    if section_start >= 0:
                        claim["char_offset_from_section"] = claim_start - section_start
                        claim["match_confidence"] = 0.9  # High confidence

                    # NEW: PDF coordinates if available (Strategy 2)
                    if section.get("coordinates"):
                        claim["pdf_coordinates"] = section["coordinates"]
                        claim["match_confidence"] = max(claim.get("match_confidence", 0), 0.8)
                else:
                    # Section not found - use line-based fallback
                    claim["match_confidence"] = 0.6
            else:
                # No sections provided - use line-based fallback
                claim["match_confidence"] = 0.6

            logger.debug(f"Claim located at line {line_number}, chars {char_start}-{char_end}, confidence: {claim.get('match_confidence', 0.6)}")

            # Get surrounding context (500 chars before and after)
            context_start = max(0, claim_start - 500)
            context_end = min(len(draft_text), claim_start + len(claim_text) + 500)
            context = draft_text[context_start:context_end]

            # Extract citations from context
            citations = extract_citations_from_text(context)

            # Update claim with found citations
            if citations:
                citation_strings = [c["citation_string"] for c in citations]
                claim["existing_citations"] = citation_strings
                claim["citation_details"] = citations
            else:
                claim["existing_citations"] = claim.get("existing_citations", [])
                claim["citation_details"] = []
        else:
            # Claim text not found in draft (might be paraphrased by AI)
            # Set defaults for positioning
            claim["line_number"] = None
            claim["char_start"] = None
            claim["char_end"] = None
            claim["text_snippet"] = claim_text[:150]  # Use claim text itself as snippet
            claim["match_confidence"] = 0.3  # Low confidence - no match
            logger.warning(f"Could not locate claim text in draft: {claim_text[:100]}...")

    return claims


def find_section_for_claim(
    claim_text: str,
    sections: List[Dict[str, Any]],
    draft_text: str
) -> Optional[Dict[str, Any]]:
    """
    Find which section contains this claim.

    Args:
        claim_text: The claim text to locate
        sections: List of sections with content
        draft_text: Full draft text

    Returns:
        Section dictionary if found, None otherwise
    """
    for section in sections:
        section_content = section.get("content", "")
        if claim_text in section_content:
            return section
    return None


# ============================================
# Main Claim Analysis Pipeline
# ============================================

async def analyze_draft_claims(draft_id: str) -> Dict[str, Any]:
    """
    Complete claim analysis pipeline for a draft.

    Steps:
    1. Fetch draft and its structural analysis
    2. Extract claims from each section
    3. Map citations to claims
    4. Categorize and score claims
    5. Store claims in database

    Args:
        draft_id: UUID of the draft

    Returns:
        Summary of claim analysis results

    Raises:
        Exception: If analysis fails
    """
    try:
        logger.info(f"Starting claim analysis for draft_id={draft_id}")

        # 1. Fetch draft and analysis
        draft_response = supabase.table("drafts").select("*").eq("id", draft_id).single().execute()

        if not draft_response.data:
            raise ValueError(f"Draft ID {draft_id} not found")

        draft = draft_response.data

        # Fetch draft analysis (structure)
        analysis_response = supabase.table("draft_analysis").select("*").eq("draft_id", draft_id).single().execute()

        if not analysis_response.data:
            raise ValueError(f"Draft analysis not found for draft_id={draft_id}. Run structural analysis first.")

        analysis = analysis_response.data
        structure = analysis.get("structure", {})

        # Download draft text from storage
        file_url = draft.get("file_url")
        if not file_url:
            raise ValueError("Draft has no file URL")

        # Extract storage path and download
        path_parts = file_url.split("/drafts/")
        if len(path_parts) < 2:
            raise ValueError(f"Invalid file URL format: {file_url}")

        storage_path = path_parts[1]
        file_bytes = supabase.storage.from_("drafts").download(storage_path)

        # Extract text based on file type
        from app.services.draft_processing import extract_text

        file_type = draft.get("file_type", "pdf")
        extracted_data = await extract_text(file_bytes, file_type)
        draft_text = extracted_data["full_text"]

        # Get sections from extracted data (available for PDFs via GROBID)
        sections = extracted_data.get("sections", [])

        # 2. Extract claims
        logger.info("Extracting claims from draft")
        claims = extract_claims_from_draft(draft_text, structure, model="gpt-5.2-chat-latest", sections_with_content=sections)

        # 3. Map citations to claims with sections for location tracking
        logger.info("Mapping citations to claims with section-based location tracking")
        claims = map_citations_to_claims(claims, draft_text, sections=sections)

        # 4. Enhance claims with semantic similarity to literature
        logger.info("Enhancing claims with literature mapping and citation strength analysis")
        from app.services.coverage_analysis import enhance_claims_with_literature_mapping
        project_id = draft.get("project_id")
        if project_id:
            claims = await enhance_claims_with_literature_mapping(claims, project_id)

        # 4. Store claims in database
        logger.info(f"Storing {len(claims)} claims in database")
        claim_records = []

        for claim in claims:
            # Get confidence score and determine if should be hidden
            confidence_score = claim.get("confidence_score", 0.8)  # Default to 0.8 if not provided
            hidden = confidence_score < 0.6  # Hide low-confidence claims to reduce hallucinations

            claim_record = {
                "draft_id": draft_id,
                "claim_text": claim.get("claim_text", ""),
                "claim_type": claim.get("claim_type", "empirical"),
                "section_location": claim.get("section_location"),
                "importance_score": claim.get("importance_score", 0.5),
                "confidence_score": confidence_score,  # AI extraction confidence
                "hidden": hidden,  # Hide low-confidence claims by default
                "requires_citation": claim.get("requires_citation", True),
                "existing_citations": claim.get("existing_citations", []),
                "reasoning": claim.get("reasoning", ""),  # AI reasoning for transparency
                # NEW: Enhanced claim categorization
                "claim_subtype": claim.get("claim_subtype"),  # factual, causal, comparative, normative
                "claim_level": claim.get("claim_level"),  # thesis, main, supporting, contextual
                "evidence_type": claim.get("evidence_type"),  # experimental, theoretical, etc.
                "confidence_level": claim.get("confidence_level"),  # definitive, tentative, exploratory
                # NEW: Citation strength analysis
                "citation_strength": claim.get("citation_strength"),  # strong, moderate, weak, missing
                "max_similarity": claim.get("max_similarity", 0.0),  # Max similarity to literature
                "unsupported": claim.get("unsupported", False),  # Flag for unsupported claims
                "supporting_literature": claim.get("supporting_literature", []),  # Top similar literature
                # EXISTING: Line positioning fields
                "line_number": claim.get("line_number"),
                "char_start": claim.get("char_start"),
                "char_end": claim.get("char_end"),
                "text_snippet": claim.get("text_snippet"),
                # NEW: Multi-strategy location tracking
                "section_id": claim.get("section_id"),
                "char_offset_from_section": claim.get("char_offset_from_section"),
                "pdf_coordinates": claim.get("pdf_coordinates"),
                "match_confidence": claim.get("match_confidence")
            }
            claim_records.append(claim_record)

        # Log hidden claims count
        hidden_count = sum(1 for record in claim_records if record.get("hidden"))
        if hidden_count > 0:
            logger.info(f"Hiding {hidden_count} low-confidence claims (confidence < 0.6)")

        # Batch insert claims
        if claim_records:
            supabase.table("draft_claims").insert(claim_records).execute()

        logger.info(f"Claim analysis completed for draft_id={draft_id}")

        # Return summary
        return {
            "message": "Claim analysis completed",
            "draft_id": draft_id,
            "total_claims": len(claims),
            "claims_by_type": {
                "empirical": len([c for c in claims if c.get("claim_type") == "empirical"]),
                "theoretical": len([c for c in claims if c.get("claim_type") == "theoretical"]),
                "methodological": len([c for c in claims if c.get("claim_type") == "methodological"])
            },
            "claims_requiring_citation": len([c for c in claims if c.get("requires_citation")])
        }

    except Exception as e:
        logger.error(f"Claim analysis failed: {str(e)}")
        raise


def categorize_claim_strength(
    claim: Dict[str, Any],
    num_citations: int
) -> str:
    """
    Assess strength of citation support for a claim.

    Args:
        claim: Claim dictionary
        num_citations: Number of citations supporting this claim

    Returns:
        Strength category: "strong", "adequate", "weak", "unsupported"
    """
    requires_citation = claim.get("requires_citation", True)
    importance = claim.get("importance_score", 0.5)

    if not requires_citation:
        return "original_contribution"

    if num_citations == 0:
        return "unsupported"
    elif num_citations == 1:
        # Single citation is weak for high-importance claims
        if importance > 0.7:
            return "weak"
        else:
            return "adequate"
    elif num_citations == 2:
        return "adequate"
    else:  # 3+ citations
        return "strong"

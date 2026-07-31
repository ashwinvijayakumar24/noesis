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

import re
from typing import Dict, Any, List, Optional, Tuple
from app.core.config import settings
from app.core.supabase_client import supabase
from app.core.logging_config import get_logger
from app.core.openai_client import get_openai_client, get_async_openai_client
from app.services.draft_anchor_qa import locate_text_snippet
from app.workflows.draft_analysis.citation_rules import extract_citations_from_text as extract_citation_tokens
import datetime

logger = get_logger(__name__)

# Initialize OpenAI client
client = get_openai_client()
async_client = get_async_openai_client()


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
    for token in extract_citation_tokens(text):
        context_start = max(0, text.find(token) - 50) if token in text else 0
        context_end = min(len(text), context_start + 120)
        year_match = re.search(r"\b(19|20)\d{2}[a-z]?\b", token)
        is_numeric = bool(re.fullmatch(r"\d{1,3}(?:-\d{1,3})?", token))
        citations.append({
            "citation_string": f"[{token}]" if is_numeric else token,
            "authors": [f"Ref {token}"] if is_numeric else [token],
            "year": year_match.group(0) if year_match else "Unknown",
            "context": text[context_start:context_end],
        })

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

        # Find claim location in draft (exact → normalized → sentence-window → section fallback)
        anchor = locate_text_snippet(
            claim_text,
            draft_text,
            sections=sections,
            section_reference=claim.get("section_location"),
            context_radius=50,
        )

        if anchor.get("found"):
            claim_start = anchor["start_index"]
            claim_end = anchor["end_index"]

            # EXISTING: Line-based positioning (Strategy 3 - fallback)
            claim["line_number"] = anchor.get("line_number")
            claim["char_start"] = anchor.get("char_start")
            claim["char_end"] = anchor.get("char_end")
            claim["text_snippet"] = anchor.get("text_snippet")

            # NEW: Section-based anchoring (Strategy 1 - best) + PDF coordinates
            if anchor.get("section_id"):
                claim["section_id"] = anchor.get("section_id")
            if anchor.get("char_offset_from_section") is not None:
                claim["char_offset_from_section"] = anchor.get("char_offset_from_section")
            if anchor.get("pdf_coordinates"):
                claim["pdf_coordinates"] = anchor.get("pdf_coordinates")
            claim["match_confidence"] = anchor.get("match_confidence", 0.6)

            logger.debug(
                f"Claim located at line {claim.get('line_number')}, "
                f"chars {claim.get('char_start')}-{claim.get('char_end')}, "
                f"strategy={anchor.get('strategy')}, "
                f"confidence: {claim.get('match_confidence', 0.6)}"
            )

            # Get surrounding context (500 chars before and after)
            context_start = max(0, claim_start - 500)
            context_end = min(len(draft_text), claim_end + 500)
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


# ============================================
# Main Claim Analysis Pipeline
# ============================================


async def find_supporting_claims(
    draft_claim_text: str,
    project_id: str,
    similarity_threshold: float = 0.7,
    max_results: int = 5,
    exclude_document_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Find document claims in this project that support or relate to a draft claim.

    Uses the existing find_similar_claims RPC and filters the results back down to
    the current project because the RPC itself is global across documents.
    """
    try:
        logger.info("[CLAIM-ANALYSIS] Finding supporting claims for draft claim")

        embedding_response = await async_client.embeddings.create(
            model="text-embedding-3-large",
            input=[draft_claim_text],
            dimensions=1536,
        )
        draft_claim_embedding = embedding_response.data[0].embedding

        result = supabase.rpc(
            "find_similar_claims",
            {
                "query_embedding": draft_claim_embedding,
                "similarity_threshold": similarity_threshold,
                "max_results": max_results * 2,
                "exclude_document_id": exclude_document_id,
            },
        ).execute()

        matching_claims: List[Dict[str, Any]] = []
        for claim in result.data or []:
            claim_check = (
                supabase.table("document_claims")
                .select("project_id")
                .eq("id", claim["claim_id"])
                .single()
                .execute()
            )
            if claim_check.data and claim_check.data["project_id"] == project_id:
                matching_claims.append(claim)
                if len(matching_claims) >= max_results:
                    break

        logger.info(
            "[CLAIM-ANALYSIS] Found %s supporting claims (threshold=%s)",
            len(matching_claims),
            similarity_threshold,
        )
        return matching_claims
    except Exception as exc:
        logger.error(f"[CLAIM-ANALYSIS] Error finding supporting claims: {exc}")
        return []

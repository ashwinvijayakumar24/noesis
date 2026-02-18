"""
Claim Extraction Node

Extracts structured claims from research papers for citation matching.

This is the KEY node for improving citation suggestions - it extracts
specific claims that can be matched against draft claims using semantic similarity.
"""

from typing import List
from app.workflows.document_analysis.state import DocumentAnalysisState, Claim
from app.core.logging_config import get_logger
from app.core.openai_client import get_openai_client, get_completion_params
import json

logger = get_logger(__name__)
client = get_openai_client()


CLAIM_EXTRACTION_PROMPT = """You are an expert at extracting research claims from academic papers.

Extract ALL significant claims from the provided document. A claim is an assertion or statement that:
- Presents a finding, result, or conclusion
- Proposes a theoretical contribution
- Describes a methodological approach or technique
- Makes a comparison with prior work
- Establishes a causal relationship

For each claim, extract:
1. The claim text (exact or paraphrased from the paper)
2. Claim type (empirical, theoretical, methodological, comparative, causal)
3. Section where it appears (if identifiable)
4. Importance score (0.0 to 1.0): how central is this claim to the paper's contribution?
5. Whether it supports the paper's primary thesis

Return ONLY a valid JSON object:
{
  "claims": [
    {
      "claim_text": "BERT achieves 92% accuracy on sentiment classification",
      "claim_type": "empirical",
      "section_title": "Results",
      "section_type": "results",
      "importance_score": 0.9,
      "supports_primary_thesis": true,
      "confidence_score": 0.95
    },
    {
      "claim_text": "Transformer architecture is more effective than RNNs for long sequences",
      "claim_type": "comparative",
      "section_title": "Discussion",
      "section_type": "discussion",
      "importance_score": 0.7,
      "supports_primary_thesis": true,
      "confidence_score": 0.9
    }
  ]
}

Claim types:
- empirical: Data-driven finding based on experiments/observations
- theoretical: Conceptual contribution, framework, or theory
- methodological: New approach, technique, or algorithm
- comparative: Comparison with baseline or prior work
- causal: Cause-and-effect relationship

Extract 10-30 claims depending on document length. Focus on primary contributions.
Confidence score: How confident are you this is accurately extracted (0.0-1.0).
"""


def extract_claims_node(state: DocumentAnalysisState) -> DocumentAnalysisState:
    """
    Extract structured claims from the document.

    This node is critical for citation matching - it extracts specific
    claims that can be semantically matched against draft claims.

    Args:
        state: Current workflow state

    Returns:
        Updated state with extracted claims
    """
    logger.info(f"[DOC-CLAIMS] Starting claim extraction for document_id={state['document_id']}")

    try:
        document_text = state["document_text"]
        structure = state.get("structure", {})
        page_count = state.get("page_count", 1)

        # Determine how much of the document to analyze based on page count
        if page_count <= 10:
            # Short paper: analyze full text (up to 15000 chars)
            analysis_text = document_text[:15000]
            target_claims = "10-20"
        elif page_count <= 30:
            # Medium paper: analyze first 25000 chars
            analysis_text = document_text[:25000]
            target_claims = "15-25"
        else:
            # Long paper: analyze first 30000 chars
            analysis_text = document_text[:30000]
            target_claims = "20-30"

        logger.info(f"[DOC-CLAIMS] Analyzing {len(analysis_text)} characters for {target_claims} claims")

        # Call GPT-4o to extract claims
        logger.info(f"[DOC-CLAIMS] Calling GPT-4o for claim extraction...")
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": CLAIM_EXTRACTION_PROMPT},
                {
                    "role": "user",
                    "content": f"Extract {target_claims} claims from this document:\n\nTitle: {structure.get('title', 'Unknown')}\n\n{analysis_text}"
                }
            ],
            response_format={"type": "json_object"},
            temperature=0.4,
            max_tokens=3000,
            **get_completion_params()  # Enable zero data retention
        )

        result = json.loads(response.choices[0].message.content)
        claims_data = result.get("claims", [])

        logger.info(f"[DOC-CLAIMS] ✓ Extracted {len(claims_data)} claims")

        # Convert to typed Claim objects
        claims: List[Claim] = []
        for claim_data in claims_data:
            claim: Claim = {
                "claim_text": claim_data.get("claim_text", ""),
                "claim_type": claim_data.get("claim_type", "empirical"),
                "section_title": claim_data.get("section_title"),
                "section_type": claim_data.get("section_type"),
                "page_number": claim_data.get("page_number"),
                "importance_score": float(claim_data.get("importance_score", 0.5)),
                "confidence_score": float(claim_data.get("confidence_score", 0.8)),
                "supports_primary_thesis": claim_data.get("supports_primary_thesis", False)
            }
            claims.append(claim)

        # Group claims by type
        claims_by_type = {}
        for claim in claims:
            claim_type = claim["claim_type"]
            if claim_type not in claims_by_type:
                claims_by_type[claim_type] = []
            claims_by_type[claim_type].append(claim)

        # Identify primary claims (high importance)
        primary_claims = [c for c in claims if c["importance_score"] >= 0.7]

        # Log summary
        logger.info(f"[DOC-CLAIMS] Claims by type: {dict((k, len(v)) for k, v in claims_by_type.items())}")
        logger.info(f"[DOC-CLAIMS] Primary claims (importance >= 0.7): {len(primary_claims)}")

        return {
            **state,
            "claims": claims,
            "claims_by_type": claims_by_type,
            "primary_claims": primary_claims,
            "current_step": "Claim Extraction",
            "progress_percentage": 40
        }

    except Exception as e:
        logger.error(f"[DOC-CLAIMS] Error extracting claims: {e}")
        errors = state.get("errors", [])
        errors.append(f"Claim extraction failed: {str(e)}")

        return {
            **state,
            "errors": errors,
            "current_step": "Claim Extraction (Failed)",
            "progress_percentage": 40
        }

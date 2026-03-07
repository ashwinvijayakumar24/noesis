"""
Claim Extraction Node

Extracts claims from the draft using AI analysis.
Each claim is categorized by type (empirical, theoretical, methodological) and importance.
"""

from app.workflows.draft_analysis.state import DraftAnalysisState, Claim
from app.core.logging_config import get_logger
from app.core.supabase_client import supabase
from app.core.openai_client import get_openai_client, get_completion_params
import json
import uuid

logger = get_logger(__name__)

# Initialize OpenAI client
client = get_openai_client()


CLAIM_EXTRACTION_PROMPT = """You are an expert academic reviewer. Analyze this research draft and ONLY extract claims that appear WEAK, UNSUPPORTED, or PROBLEMATIC in the context of the paper.

DO NOT extract all claims - only those that need improvement or additional support.

Identify claims that are weak because they:
- Lack sufficient evidence or supporting data
- Are overly broad or sweeping without qualification
- Contradict or are inconsistent with other parts of the paper
- Make causal claims without proper justification
- Lack citations when prior work is clearly relevant
- Are stated too confidently given the evidence presented
- Make novelty claims without proper comparison to existing work
- Have methodological issues that undermine the claim

For each WEAK claim, determine:
1. The exact claim text
2. Claim type:
   - "empirical": Claims about observed data or experimental results
   - "theoretical": Claims about theories, models, or conceptual frameworks
   - "methodological": Claims about methods, approaches, or techniques
3. Section location (e.g., "Introduction", "Methods", "Results")
4. Importance score (0.0-1.0): How central is this claim to the paper's contribution?
5. Confidence (0.0-1.0): How confidently stated is this claim (paradoxically, overconfident claims are often weak)
6. Why it's weak (brief explanation)

Return ONLY a valid JSON object with this structure:
{
  "claims": [
    {
      "claim_text": "The exact claim as stated in the draft",
      "claim_type": "empirical" | "theoretical" | "methodological",
      "section_location": "Section name",
      "importance_score": 0.0 to 1.0,
      "confidence": 0.0 to 1.0,
      "weakness_reason": "Brief explanation of why this claim is weak"
    }
  ],
  "total_claims": number,
  "extraction_notes": "Summary of weak claims found"
}

Focus ONLY on problematic claims that need attention.

Ignore well-supported, properly cited, and appropriately qualified claims.
"""


def extract_claims_node(state: DraftAnalysisState) -> DraftAnalysisState:
    """
    Extract claims from the draft using GPT-4o-mini.

    This node first checks if claims were already extracted in Phase 1 (draft_processing.py).
    If claims exist in the database, it reuses them to avoid duplicate extraction.

    Args:
        state: Current workflow state

    Returns:
        Updated state with extracted claims
    """
    logger.info(f"[Claim Extraction] Starting for draft_id={state['draft_id']}")

    draft_id = state["draft_id"]

    # OPTIMIZATION: Check if claims already exist in database (from Phase 1)
    try:
        existing_claims_res = supabase.table("draft_claims")\
            .select("id, claim_text, claim_type, section_location, importance_score, confidence_score, requires_citation")\
            .eq("draft_id", draft_id)\
            .execute()

        if existing_claims_res.data and len(existing_claims_res.data) > 0:
            logger.info(f"[Claim Extraction] Found {len(existing_claims_res.data)} existing claims in database - SKIPPING re-extraction")

            # Convert database records to Claim objects
            claims: list[Claim] = []
            for db_claim in existing_claims_res.data:
                claim: Claim = {
                    "id": db_claim["id"],
                    "claim_text": db_claim["claim_text"],
                    "claim_type": db_claim["claim_type"],
                    "section_location": db_claim.get("section_location", "Unknown"),
                    "importance_score": db_claim.get("importance_score", 0.5),
                    "confidence": db_claim.get("confidence_score", 0.8),
                    "requires_citation": db_claim.get("requires_citation", True)
                }
                claims.append(claim)

            logger.info(
                f"[Claim Extraction] Reusing {len(claims)} existing claims "
                f"(empirical: {sum(1 for c in claims if c['claim_type'] == 'empirical')}, "
                f"theoretical: {sum(1 for c in claims if c['claim_type'] == 'theoretical')}, "
                f"methodological: {sum(1 for c in claims if c['claim_type'] == 'methodological')})"
            )

            return {
                'claims': claims,
                'should_validate_claims': False,  # Already validated in Phase 1
                'current_step': 'Claim Extraction (Cached)',
                'progress_percentage': 25
            }

    except Exception as db_error:
        logger.warning(f"[Claim Extraction] Could not check for existing claims: {db_error}")
        # Continue with extraction if database check fails

    draft_content = state["draft_content"]

    try:
        # Use gpt-5.2-chat-latest for higher quality claim extraction
        # Note: Removing temperature to use model defaults
        response = client.chat.completions.create(
            model="gpt-5.2-chat-latest",
            messages=[
                {"role": "system", "content": CLAIM_EXTRACTION_PROMPT},
                {"role": "user", "content": f"Extract claims from this draft:\n\n{draft_content}"}
            ],
            max_completion_tokens=4000,
            **get_completion_params()  # Enable zero data retention
        )

        result = json.loads(response.choices[0].message.content)

        # Convert to typed Claim objects with unique IDs
        claims: list[Claim] = []
        for claim_data in result.get("claims", []):
            claim: Claim = {
                "id": str(uuid.uuid4()),
                "claim_text": claim_data["claim_text"],
                "claim_type": claim_data["claim_type"],
                "section_location": claim_data["section_location"],
                "importance_score": claim_data["importance_score"],
                "confidence": claim_data.get("confidence", 0.8),
                "requires_citation": True  # All extracted claims should have citation support checked
            }
            claims.append(claim)

        logger.info(
            f"[Claim Extraction] Extracted {len(claims)} claims "
            f"(empirical: {sum(1 for c in claims if c['claim_type'] == 'empirical')}, "
            f"theoretical: {sum(1 for c in claims if c['claim_type'] == 'theoretical')}, "
            f"methodological: {sum(1 for c in claims if c['claim_type'] == 'methodological')})"
        )

        # Check if we should validate (too many or too few claims)
        should_validate = len(claims) < 3 or len(claims) > 50

        if len(claims) < 3:
            logger.warning(f"[Claim Extraction] Only {len(claims)} claims found - may need validation")
        elif len(claims) > 50:
            logger.warning(f"[Claim Extraction] {len(claims)} claims found - may be over-extraction")

        # Update state
        return {
            'claims': claims,
            'should_validate_claims': should_validate,
            'current_step': 'Claim Extraction',
            'progress_percentage': 25
        }

    except Exception as e:
        logger.error(f"[Claim Extraction] Error: {e}")
        errors = state.get('errors', [])
        errors.append(f"Claim extraction failed: {str(e)}")

        return {
            'errors': errors,
            'current_step': 'Claim Extraction (Failed)',
            'progress_percentage': 25
        }

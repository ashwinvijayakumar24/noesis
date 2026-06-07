"""
Claim Extraction Node

Extracts claims from the draft using AI analysis.
Each claim is categorized by type (empirical, theoretical, methodological) and importance.
"""

from app.workflows.draft_analysis.state import DraftAnalysisState, Claim
from app.workflows.draft_analysis.schemas import ClaimExtractionOutput
from app.workflows.draft_analysis.citation_rules import (
    apply_existing_citation_gate,
    citations_near_claim,
)
from app.core.logging_config import get_logger
from app.core.supabase_client import supabase
from app.core.openai_client import get_openai_client, get_completion_params
from app.services.retry_utils import parse_chat_completion_with_retries_sync
import uuid
import re

logger = get_logger(__name__)

client = None


def _get_client():
    global client
    if client is None:
        client = get_openai_client()
    return client


INTERNAL_SYNTHESIS_ROLES = {"result_finding", "discussion_synthesis", "conclusion_summary"}
def _infer_rhetorical_role(claim_text: str, section_location: str) -> str:
    """Heuristic backstop for cached/older claims that lack rhetorical-role metadata."""
    text = (claim_text or "").strip().lower()
    section = (section_location or "").strip().lower()

    if any(label in section for label in ("result", "finding")):
        return "result_finding"
    if any(label in section for label in ("discussion", "conclusion")):
        if re.search(r"\b(our|this)\s+(study|review|analysis|findings|results|systematic review)\b", text):
            return "conclusion_summary" if "conclusion" in section else "discussion_synthesis"
        if re.search(r"\b(we found|we show|we demonstrate|we observed|we identified|indicates that)\b", text):
            return "conclusion_summary" if "conclusion" in section else "discussion_synthesis"
    if any(label in section for label in ("method", "materials")):
        return "method_claim"
    if re.search(r"\b(prior|previous|existing|recent|literature|studies have|has been shown)\b", text):
        return "prior_work_claim"
    return "background_claim"


def _claim_requires_external_citation(
    claim_text: str,
    section_location: str,
    rhetorical_role: str | None,
    model_requires_citation: bool = True,
) -> bool:
    """
    Decide whether the claim should be sent down the citation-support pipeline.

    Authors' own findings/conclusions should still be eligible for reviewer critique,
    but they should not be labeled "unsupported because no external citation was found."
    """
    role = rhetorical_role or _infer_rhetorical_role(claim_text, section_location)
    text = (claim_text or "").lower()

    causal_overstatement = bool(
        re.search(r"\b(causes?|caused|causal|definitive|proves?|leads? to|resulted in)\b", text)
    )
    if role in INTERNAL_SYNTHESIS_ROLES and not causal_overstatement:
        return False

    return bool(model_requires_citation)


def _inline_citations_near_claim(
    claim_text: str,
    draft_content: str,
    *,
    char_start: int | None = None,
    char_end: int | None = None,
) -> list[str]:
    """
    Detect nearby inline citations after an extracted claim.

    PDF extraction often strips superscript styling, so this accepts bracketed
    numeric ranges, author-year citations, and compact numeric runs immediately
    after the sentence.
    """
    if not claim_text or not draft_content:
        return []

    return citations_near_claim(
        claim_text,
        draft_content,
        char_start=char_start,
        char_end=char_end,
    )


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
3. Rhetorical role:
   - "background_claim": field/context statements that need prior-work support
   - "prior_work_claim": statements about what existing studies/literature show
   - "method_claim": claims about the paper's methods or workflow
   - "result_finding": the authors' own reported findings/results
   - "discussion_synthesis": the authors' own interpretation of their results
   - "conclusion_summary": the authors' own conclusion from this paper/review
4. Whether the claim requires an EXTERNAL citation. Do not require external citations for the authors' own results, discussion synthesis, or conclusion summaries unless they make an overbroad general field claim or a causal claim stronger than their evidence supports.
5. Section location (e.g., "Introduction", "Methods", "Results")
6. Importance score (0.0-1.0): How central is this claim to the paper's contribution?
7. Confidence (0.0-1.0): How confidently stated is this claim (paradoxically, overconfident claims are often weak)
8. Why it's weak (brief explanation)

Return ONLY a valid JSON object with this structure:
{
  "claims": [
    {
      "claim_text": "The exact claim as stated in the draft",
      "claim_type": "empirical" | "theoretical" | "methodological",
      "rhetorical_role": "background_claim" | "prior_work_claim" | "method_claim" | "result_finding" | "discussion_synthesis" | "conclusion_summary",
      "section_location": "Section name",
      "importance_score": 0.0 to 1.0,
      "confidence": 0.0 to 1.0,
      "requires_citation": true | false,
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
        if state.get("stage_only", True):
            raise RuntimeError("Skipping draft_claims cache during staged analysis run")
        existing_claims_res = supabase.table("draft_claims")\
            .select("id, claim_text, claim_type, section_location, importance_score, confidence_score, requires_citation, existing_citations, line_number, char_start, char_end, text_snippet, match_confidence")\
            .eq("draft_id", draft_id)\
            .execute()

        if existing_claims_res.data and len(existing_claims_res.data) > 0:
            logger.info(f"[Claim Extraction] Found {len(existing_claims_res.data)} existing claims in database - SKIPPING re-extraction")

            # Convert database records to Claim objects
            claims: list[Claim] = []
            for db_claim in existing_claims_res.data:
                role = db_claim.get("rhetorical_role") or _infer_rhetorical_role(
                    db_claim.get("claim_text", ""),
                    db_claim.get("section_location", "Unknown"),
                )
                claim: Claim = {
                    "id": db_claim["id"],
                    "claim_text": db_claim["claim_text"],
                    "claim_type": db_claim["claim_type"],
                    "section_location": db_claim.get("section_location", "Unknown"),
                    "importance_score": db_claim.get("importance_score", 0.5),
                    "confidence": db_claim.get("confidence_score", 0.8),
                    "requires_citation": _claim_requires_external_citation(
                        db_claim.get("claim_text", ""),
                        db_claim.get("section_location", "Unknown"),
                        role,
                        db_claim.get("requires_citation", True),
                    ),
                    "rhetorical_role": role,
                }
                for key in ("line_number", "char_start", "char_end", "text_snippet", "match_confidence"):
                    if db_claim.get(key) is not None:
                        claim[key] = db_claim[key]
                existing_citations = db_claim.get("existing_citations") or _inline_citations_near_claim(
                    db_claim.get("claim_text", ""),
                    state.get("draft_content", ""),
                    char_start=db_claim.get("char_start"),
                    char_end=db_claim.get("char_end"),
                )
                if existing_citations:
                    claim["existing_citations"] = existing_citations
                    claim["has_inline_citation"] = True
                apply_existing_citation_gate(claim)
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
        response = parse_chat_completion_with_retries_sync(
            _get_client(),
            model="gpt-5.2-chat-latest",
            messages=[
                {"role": "system", "content": CLAIM_EXTRACTION_PROMPT},
                {"role": "user", "content": f"Extract claims from this draft:\n\n{draft_content}"}
            ],
            max_completion_tokens=8000,
            response_format=ClaimExtractionOutput,
            **get_completion_params()  # Enable zero data retention
        )

        result = response.parsed

        # Convert to typed Claim objects with unique IDs
        claims: list[Claim] = []
        for claim_data in result.claims:
            role = claim_data.rhetorical_role or _infer_rhetorical_role(
                claim_data.claim_text,
                claim_data.section_location,
            )
            claim: Claim = {
                "id": str(uuid.uuid4()),
                "claim_text": claim_data.claim_text,
                "claim_type": claim_data.claim_type,
                "section_location": claim_data.section_location,
                "importance_score": claim_data.importance_score,
                "confidence": claim_data.confidence,
                "requires_citation": _claim_requires_external_citation(
                    claim_data.claim_text,
                    claim_data.section_location,
                    role,
                    claim_data.requires_citation,
                ),
                "rhetorical_role": role,
                "weakness_reason": claim_data.weakness_reason,
            }
            claims.append(claim)

        try:
            from app.services.draft_anchor_qa import locate_text_snippet

            sections = state.get("structure", {}).get("sections", [])
            for claim in claims:
                anchor = locate_text_snippet(
                    claim.get("claim_text", ""),
                    draft_content,
                    sections=sections,
                    section_reference=claim.get("section_location"),
                    context_radius=50,
                )
                if anchor.get("found"):
                    for key in (
                        "line_number",
                        "char_start",
                        "char_end",
                        "text_snippet",
                        "section_id",
                        "char_offset_from_section",
                        "pdf_coordinates",
                        "match_confidence",
                    ):
                        if key in anchor:
                            claim[key] = anchor[key]
                    existing_citations = _inline_citations_near_claim(
                        claim.get("claim_text", ""),
                        draft_content,
                        char_start=anchor.get("char_start"),
                        char_end=anchor.get("char_end"),
                    )
                    if existing_citations:
                        claim["existing_citations"] = existing_citations
                        claim["has_inline_citation"] = True
                        apply_existing_citation_gate(claim)
        except Exception as anchor_error:
            logger.warning(f"[Claim Extraction] Claim anchoring failed (non-fatal): {anchor_error}")

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

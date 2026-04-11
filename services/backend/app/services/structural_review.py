"""
Structural Review Service

Performs lightweight structural checks on a research draft to detect common issues
that peer reviewers universally flag:
- Abstract-body mismatch
- Causal overclaiming
- Statistical incompleteness
- Missing SOTA comparison
- Methods reproducibility gaps
- Weak limitations section

These checks complement the standard reviewer_feedback by catching specific
rhetorical and structural anti-patterns before submission.
"""

import json
from typing import List, Dict, Any
from app.core.openai_client import get_openai_client, get_completion_params
from app.core.logging_config import get_logger

logger = get_logger(__name__)
client = get_openai_client()


STRUCTURAL_CHECKS_PROMPT = """You are an expert peer reviewer performing targeted structural quality checks on a research draft.

Analyze the draft text for the following specific issue types. ONLY flag issues that you can ground concretely in the text.

Respond with ONLY valid JSON in this exact structure:
{
  "checks": [
    {
      "check_type": "abstract_body_mismatch | causal_overclaim | statistical_incompleteness | missing_sota | methods_reproducibility | weak_limitations",
      "severity": "critical | major | minor",
      "section_reference": "Abstract | Introduction | Methods | Results | Discussion | Conclusion",
      "specific_issue": "One sentence describing the specific problem found in the text",
      "feedback_text": "Detailed reviewer-style explanation of why this is a problem and how it affects acceptance",
      "suggested_improvements": [
        "Specific actionable suggestion 1",
        "Specific actionable suggestion 2"
      ]
    }
  ]
}

Check Types to Evaluate:

1. **abstract_body_mismatch**: A number, percentage, or conclusion stated in the Abstract differs from or is entirely absent from the body sections. Example: "Abstract states 97% accuracy; Section 4.2 only reports 91.4%."

2. **causal_overclaim**: Causal language ("demonstrates," "proves," "X causes Y," "shows that," "because of X, Y occurs") is used in an observational, correlational, or computational study where causal inference has not been established.

3. **statistical_incompleteness**: A statistical result (e.g., p-value, mean, accuracy) is reported without necessary context: missing effect size, confidence interval, sample size, or variance measure that reviewers require.

4. **missing_sota**: A contribution or performance improvement is claimed but no comparison to existing state-of-the-art methods or competitive baselines is provided. If any comparison table or baseline citation is present, do NOT flag this.

5. **methods_reproducibility**: Details needed for replication are missing: sample size justification, hyperparameters, random seeds, dataset version/citation, software version, or ethics approval statement (when human subjects are involved).

6. **weak_limitations**: The limitations section is absent, trivially brief (fewer than 2–3 substantive sentences), or only acknowledges minor stylistic issues while avoiding real constraints on generalizability.

Guidelines:
- Only flag issues concretely grounded in the text. Do NOT speculate about what might be missing if the topic isn't addressed in the draft at all.
- If a check passes cleanly, omit it from the output entirely.
- Target 2–6 checks total. Do not manufacture issues.
- Keep `specific_issue` to one concrete sentence tied to actual text content.
- Keep `feedback_text` to 2–4 sentences, academic reviewer tone.
"""


async def run_structural_checks(draft_text: str) -> List[Dict[str, Any]]:
    """
    Run structural quality checks on a draft using GPT-5.2.

    Args:
        draft_text: Full draft content (will be truncated to 24k chars)

    Returns:
        List of structural check result dicts, each with check_type, severity,
        section_reference, specific_issue, feedback_text, suggested_improvements.
    """
    try:
        # Truncate to ~6000 tokens (24000 chars) to stay well within context window
        truncated = draft_text[:24000] if len(draft_text) > 24000 else draft_text

        response = client.chat.completions.create(
            model="gpt-5.2-chat-latest",
            messages=[
                {"role": "system", "content": STRUCTURAL_CHECKS_PROMPT},
                {"role": "user", "content": f"Research draft to analyze:\n\n{truncated}"}
            ],
            max_completion_tokens=1500,
            **get_completion_params()
        )

        raw = response.choices[0].message.content.strip()

        # Strip markdown fences if present
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1] if len(parts) > 1 else raw
            if raw.startswith("json"):
                raw = raw[4:].strip()

        result = json.loads(raw)
        checks = result.get("checks", [])

        logger.info(f"[Structural Review] Identified {len(checks)} structural issues")
        return checks

    except json.JSONDecodeError as e:
        logger.error(f"[Structural Review] JSON parse error: {e}")
        return []
    except Exception as e:
        logger.error(f"[Structural Review] Error running checks: {e}")
        return []

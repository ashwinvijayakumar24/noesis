"""
Findings Extraction Node

Extracts quantitative results and key findings from research papers:
- Performance metrics and numbers
- Statistical results
- Comparisons with baselines
- Key qualitative insights
- Limitations

This enables quantitative comparison across papers and evidence strength assessment.
"""

from typing import List
from app.workflows.document_analysis.state import DocumentAnalysisState, Finding
from app.core.logging_config import get_logger
from openai import OpenAI
import os
import json

logger = get_logger(__name__)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


FINDINGS_EXTRACTION_PROMPT = """You are an expert at extracting research findings and results from academic papers.

Extract ALL significant findings, results, and outcomes from the provided document:
- Quantitative performance metrics (accuracy, F1, BLEU, etc.)
- Statistical results (p-values, confidence intervals, effect sizes)
- Comparisons with baselines or prior work
- Key qualitative insights
- Important limitations

Return ONLY a valid JSON object:
{
  "findings": [
    {
      "finding_text": "BERT achieves 92% accuracy on IMDB sentiment classification",
      "finding_type": "performance_metric",
      "metrics": {
        "accuracy": 0.92,
        "F1": 0.89,
        "precision": 0.91,
        "recall": 0.87
      },
      "comparison_baseline": "Random Forest baseline",
      "improvement_over_baseline": "+15% accuracy",
      "section_title": "Results",
      "table_or_figure_reference": "Table 3",
      "statistical_significance": true,
      "confidence_score": 0.95
    },
    {
      "finding_text": "Model training time reduced from 24 hours to 6 hours",
      "finding_type": "performance_metric",
      "metrics": {
        "training_time_hours": 6,
        "speedup": 4.0
      },
      "comparison_baseline": "Standard BERT training",
      "improvement_over_baseline": "4x faster",
      "section_title": "Efficiency Analysis",
      "statistical_significance": null,
      "confidence_score": 0.9
    },
    {
      "finding_text": "Increasing dataset size beyond 10K samples showed diminishing returns",
      "finding_type": "qualitative_insight",
      "metrics": {},
      "comparison_baseline": null,
      "improvement_over_baseline": null,
      "section_title": "Discussion",
      "statistical_significance": null,
      "confidence_score": 0.85
    },
    {
      "finding_text": "Model performance degrades on out-of-domain data",
      "finding_type": "limitation",
      "metrics": {},
      "comparison_baseline": null,
      "improvement_over_baseline": null,
      "section_title": "Limitations",
      "statistical_significance": null,
      "confidence_score": 0.9
    }
  ]
}

Finding types:
- performance_metric: Quantitative performance numbers (accuracy, speed, etc.)
- statistical_result: Statistical test results, significance tests
- qualitative_insight: Non-numeric but important observations
- limitation: Acknowledged limitations or weaknesses

Extract 10-25 findings. Include metrics as structured JSON when available.
Confidence score: How confident are you this finding is accurately extracted (0.0-1.0).
"""


def extract_findings_node(state: DocumentAnalysisState) -> DocumentAnalysisState:
    """
    Extract findings and results from the document.

    Args:
        state: Current workflow state

    Returns:
        Updated state with extracted findings
    """
    logger.info(f"[DOC-FINDINGS] Starting findings extraction for document_id={state['document_id']}")

    try:
        document_text = state["document_text"]
        structure = state.get("structure", {})
        page_count = state.get("page_count", 1)

        # Focus on results and discussion sections
        has_results = structure.get("has_results", False)
        has_discussion = structure.get("has_discussion", False)

        # Determine analysis scope
        if has_results or has_discussion:
            analysis_text = document_text[:20000]
            logger.info(f"[DOC-FINDINGS] Has results/discussion, analyzing {len(analysis_text)} chars")
        else:
            analysis_text = document_text[:15000]
            logger.info(f"[DOC-FINDINGS] No explicit results section, analyzing {len(analysis_text)} chars")

        # Call GPT-4o to extract findings
        logger.info(f"[DOC-FINDINGS] Calling GPT-4o for findings extraction...")
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": FINDINGS_EXTRACTION_PROMPT},
                {
                    "role": "user",
                    "content": f"Extract findings from this document:\n\nTitle: {structure.get('title', 'Unknown')}\n\n{analysis_text}"
                }
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
            max_tokens=3000
        )

        result = json.loads(response.choices[0].message.content)
        findings_data = result.get("findings", [])

        logger.info(f"[DOC-FINDINGS] ✓ Extracted {len(findings_data)} findings")

        # Convert to typed Finding objects
        findings: List[Finding] = []
        for finding_data in findings_data:
            finding: Finding = {
                "finding_text": finding_data.get("finding_text", ""),
                "finding_type": finding_data.get("finding_type"),
                "metrics": finding_data.get("metrics", {}),
                "comparison_baseline": finding_data.get("comparison_baseline"),
                "improvement_over_baseline": finding_data.get("improvement_over_baseline"),
                "section_title": finding_data.get("section_title"),
                "page_number": finding_data.get("page_number"),
                "table_or_figure_reference": finding_data.get("table_or_figure_reference"),
                "statistical_significance": finding_data.get("statistical_significance"),
                "confidence_score": float(finding_data.get("confidence_score", 0.8))
            }
            findings.append(finding)

        # Identify findings with metrics (most valuable for comparison)
        findings_with_metrics = [f for f in findings if f.get("metrics") and len(f["metrics"]) > 0]

        # Log summary
        finding_types = {}
        for finding in findings:
            f_type = finding.get("finding_type", "unknown")
            finding_types[f_type] = finding_types.get(f_type, 0) + 1

        logger.info(f"[DOC-FINDINGS] Findings by type: {finding_types}")
        logger.info(f"[DOC-FINDINGS] Findings with metrics: {len(findings_with_metrics)}")

        return {
            **state,
            "findings": findings,
            "findings_with_metrics": findings_with_metrics,
            "current_step": "Findings Extraction",
            "progress_percentage": 80
        }

    except Exception as e:
        logger.error(f"[DOC-FINDINGS] Error extracting findings: {e}")
        errors = state.get("errors", [])
        errors.append(f"Findings extraction failed: {str(e)}")

        return {
            **state,
            "errors": errors,
            "current_step": "Findings Extraction (Failed)",
            "progress_percentage": 80
        }

"""
Section-Specific Analysis Service

Provides specialized analysis functions for specific paper sections, leveraging
structured data from document_methods, document_findings, and document_claims tables.

This service enables:
- Methodology comparison and gap identification
- Baseline comparison detection
- Alternative approach suggestions
- Section-specific quality assessment

Used by the draft analysis workflow to provide deeper, more precise feedback
than general RAG chunk matching.
"""

from typing import Dict, Any, List, Optional
from app.core.supabase_client import supabase
from app.core.logging_config import get_logger

logger = get_logger(__name__)


async def compare_methodology_to_literature(
    draft_id: str,
    project_id: str
) -> List[Dict[str, Any]]:
    """
    Compare draft methodology against project literature.

    Identifies:
    1. Missing baseline comparisons (methods mentioned but not compared)
    2. Alternative approaches not discussed (methods used in literature but not cited)
    3. Missing evaluation metrics (metrics used in literature but not in draft)
    4. Dataset gaps (datasets used in literature but not mentioned)

    Args:
        draft_id: UUID of the draft
        project_id: UUID of the project

    Returns:
        List of reviewer feedback items with type='methodology'
    """
    try:
        logger.info(f"Comparing methodology for draft {draft_id} against project {project_id}")

        # 1. Fetch draft methodology claims
        draft_claims_response = supabase.table("draft_claims")\
            .select("*")\
            .eq("draft_id", draft_id)\
            .eq("claim_type", "methodological")\
            .execute()

        draft_claims = draft_claims_response.data or []
        logger.info(f"Found {len(draft_claims)} methodological claims in draft")

        # Extract mentioned methods and metrics from draft claims
        draft_methods = set()
        draft_metrics = set()
        draft_datasets = set()

        for claim in draft_claims:
            claim_text_lower = claim.get("claim_text", "").lower()
            # Simple keyword extraction (can be enhanced with NLP)
            draft_methods.add(claim_text_lower)

            # Extract common metrics
            common_metrics = ["accuracy", "precision", "recall", "f1", "bleu", "rouge", "rmse", "mae"]
            for metric in common_metrics:
                if metric in claim_text_lower:
                    draft_metrics.add(metric)

        # 2. Fetch document_methods from project literature
        methods_response = supabase.table("document_methods")\
            .select("*")\
            .eq("project_id", project_id)\
            .execute()

        literature_methods = methods_response.data or []
        logger.info(f"Found {len(literature_methods)} methods in project literature")

        # 3. Fetch document_findings for baseline comparisons
        findings_response = supabase.table("document_findings")\
            .select("*")\
            .eq("project_id", project_id)\
            .execute()

        literature_findings = findings_response.data or []
        logger.info(f"Found {len(literature_findings)} findings in project literature")

        # Analyze gaps
        feedback_items = []

        # 3.1 Missing baseline comparisons
        baselines_in_literature = set()
        for finding in literature_findings:
            baseline = finding.get("comparison_baseline")
            if baseline:
                baselines_in_literature.add(baseline.lower())

        mentioned_but_not_compared = []
        for baseline in baselines_in_literature:
            # Check if baseline is mentioned in draft but not as a comparison
            mentioned_in_draft = any(baseline in claim.get("claim_text", "").lower() for claim in draft_claims)
            has_comparison = any(
                baseline in claim.get("claim_text", "").lower() and
                ("compared" in claim.get("claim_text", "").lower() or
                 "vs" in claim.get("claim_text", "").lower() or
                 "versus" in claim.get("claim_text", "").lower())
                for claim in draft_claims
            )

            if mentioned_in_draft and not has_comparison:
                mentioned_but_not_compared.append(baseline)

        if mentioned_but_not_compared:
            feedback_items.append({
                "feedback_type": "methodology",
                "severity": "major",
                "priority": "high",
                "feedback_text": f"Missing baseline comparisons: The draft mentions {', '.join(mentioned_but_not_compared[:3])} but does not provide quantitative comparisons. Literature in your project includes performance comparisons with these baselines.",
                "suggestions": [
                    f"Add quantitative comparison with {baseline}" for baseline in mentioned_but_not_compared[:3]
                ],
                "section_reference": "Methodology or Results section"
            })

        # 3.2 Alternative approaches not discussed
        literature_method_names = {m.get("method_name", "").lower() for m in literature_methods if m.get("method_name")}
        literature_method_types = {m.get("method_type", "").lower() for m in literature_methods if m.get("method_type")}

        # Find methods in literature but not mentioned in draft
        missing_alternatives = []
        for method in literature_method_names:
            if method and not any(method in claim.get("claim_text", "").lower() for claim in draft_claims):
                # Find which papers use this method
                papers_using_method = [
                    m for m in literature_methods
                    if m.get("method_name", "").lower() == method
                ]
                if papers_using_method:
                    missing_alternatives.append({
                        "method": method,
                        "type": papers_using_method[0].get("method_type", "unknown"),
                        "count": len(papers_using_method)
                    })

        if missing_alternatives:
            top_missing = sorted(missing_alternatives, key=lambda x: x["count"], reverse=True)[:3]
            feedback_items.append({
                "feedback_type": "methodology",
                "severity": "minor",
                "priority": "medium",
                "feedback_text": f"Alternative approaches from literature not discussed: {', '.join([m['method'] for m in top_missing])}. These methods appear in {sum(m['count'] for m in top_missing)} papers in your project but are not mentioned in your methodology discussion.",
                "suggestions": [
                    f"Discuss why {m['method']} ({m['type']}) was not chosen as an alternative"
                    for m in top_missing
                ],
                "section_reference": "Methodology section - Related Work or Approach Justification"
            })

        # 3.3 Missing evaluation metrics
        literature_metrics = set()
        for method in literature_methods:
            metrics = method.get("evaluation_metrics", [])
            if metrics:
                literature_metrics.update([m.lower() for m in metrics])

        for finding in literature_findings:
            metrics_dict = finding.get("metrics", {})
            if isinstance(metrics_dict, dict):
                literature_metrics.update([k.lower() for k in metrics_dict.keys()])

        # Find metrics in literature but not in draft
        missing_metrics = literature_metrics - draft_metrics

        if missing_metrics and len(missing_metrics) > 0:
            # Filter to common/important metrics only
            common_important = ["f1", "precision", "recall", "accuracy", "bleu", "rouge", "rmse", "mae", "auc"]
            important_missing = [m for m in missing_metrics if m in common_important]

            if important_missing:
                feedback_items.append({
                    "feedback_type": "methodology",
                    "severity": "minor",
                    "priority": "medium",
                    "feedback_text": f"Evaluation metrics from literature not used: {', '.join(important_missing[:3])}. These metrics are commonly used in your field (based on project literature) but are not reported in your evaluation.",
                    "suggestions": [
                        f"Consider reporting {metric} for comparison with prior work"
                        for metric in important_missing[:3]
                    ],
                    "section_reference": "Results or Evaluation section"
                })

        # 3.4 Dataset coverage
        literature_datasets = set()
        for method in literature_methods:
            datasets = method.get("datasets_used", [])
            if datasets:
                literature_datasets.update([d.lower() for d in datasets])

        # Check if common datasets from literature are mentioned in draft
        missing_datasets = []
        for dataset in literature_datasets:
            if dataset and not any(dataset in claim.get("claim_text", "").lower() for claim in draft_claims):
                # Count how many papers use this dataset
                papers_using_dataset = sum(
                    1 for m in literature_methods
                    if dataset in [d.lower() for d in (m.get("datasets_used") or [])]
                )
                if papers_using_dataset >= 2:  # Only flag if 2+ papers use it
                    missing_datasets.append({
                        "dataset": dataset,
                        "paper_count": papers_using_dataset
                    })

        if missing_datasets:
            top_missing_datasets = sorted(missing_datasets, key=lambda x: x["paper_count"], reverse=True)[:2]
            dataset_names = ', '.join([d['dataset'] for d in top_missing_datasets])
            dataset_details = ', '.join([f"{d['dataset']} ({d['paper_count']} papers)" for d in top_missing_datasets])
            feedback_items.append({
                "feedback_type": "methodology",
                "severity": "suggestion",
                "priority": "low",
                "feedback_text": f"Common benchmark datasets not used: {dataset_names}. These datasets appear in multiple papers in your project ({dataset_details}) but are not used in your evaluation.",
                "suggestions": [
                    f"Consider evaluating on {d['dataset']} for better comparison with prior work"
                    for d in top_missing_datasets
                ],
                "section_reference": "Experimental Setup or Datasets section"
            })

        logger.info(f"Generated {len(feedback_items)} methodology comparison feedback items")
        return feedback_items

    except Exception as e:
        logger.error(f"Methodology comparison failed for draft {draft_id}: {e}")
        return []


async def analyze_results_section(
    draft_id: str,
    project_id: str
) -> List[Dict[str, Any]]:
    """
    Analyze results section against project findings.

    Identifies:
    1. Missing statistical significance tests
    2. Results that contradict or confirm literature findings
    3. Missing error bars or confidence intervals
    4. Incomplete result reporting

    Args:
        draft_id: UUID of the draft
        project_id: UUID of the project

    Returns:
        List of reviewer feedback items with type='results'
    """
    try:
        logger.info(f"Analyzing results section for draft {draft_id}")

        # Fetch draft claims from results section
        draft_claims_response = supabase.table("draft_claims")\
            .select("*")\
            .eq("draft_id", draft_id)\
            .eq("section_type", "results")\
            .execute()

        draft_claims = draft_claims_response.data or []

        # Fetch literature findings
        findings_response = supabase.table("document_findings")\
            .select("*")\
            .eq("project_id", project_id)\
            .execute()

        literature_findings = findings_response.data or []

        feedback_items = []

        # Check for statistical significance reporting
        has_significance_test = any(
            "p-value" in claim.get("claim_text", "").lower() or
            "p <" in claim.get("claim_text", "").lower() or
            "significant" in claim.get("claim_text", "").lower() or
            "statistically" in claim.get("claim_text", "").lower()
            for claim in draft_claims
        )

        literature_has_significance = any(
            finding.get("statistical_significance") for finding in literature_findings
        )

        if literature_has_significance and not has_significance_test:
            feedback_items.append({
                "feedback_type": "results",
                "severity": "major",
                "priority": "high",
                "feedback_text": "Missing statistical significance tests: Literature in your project reports statistical significance (p-values, confidence intervals), but your results section does not include significance testing.",
                "suggestions": [
                    "Add statistical significance tests (e.g., t-test, ANOVA, chi-square)",
                    "Report p-values or confidence intervals for key findings",
                    "Discuss whether improvements are statistically significant"
                ],
                "section_reference": "Results section"
            })

        logger.info(f"Generated {len(feedback_items)} results section feedback items")
        return feedback_items

    except Exception as e:
        logger.error(f"Results section analysis failed for draft {draft_id}: {e}")
        return []

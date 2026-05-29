"""
Manuscript Profile Node

Classifies the draft so downstream reviewers use the right standards for the
paper type instead of defaulting to generic ML-conference expectations.
"""

from __future__ import annotations

import re

from app.core.logging_config import get_logger
from app.workflows.draft_analysis.state import DraftAnalysisState

logger = get_logger(__name__)


BIOMEDICAL_TERMS = {
    "sepsis", "clinical", "patient", "patients", "hospital", "mortality",
    "ehr", "electronic health record", "icu", "emergency department",
    "antibiotic", "care bundle", "diagnosis", "healthcare",
}

CLINICAL_AI_TERMS = {
    "machine learning", "algorithm", "prediction", "predictive", "ai",
    "artificial intelligence", "deployment", "implemented", "implementation",
    "alert", "alerts", "silent trial", "real-world", "clinical workflow",
    "mla", "mlas",
}

SYSTEMATIC_REVIEW_TERMS = {
    "systematic review", "prisma", "search strategy", "study selection",
    "data extraction", "risk of bias", "meta-analysis", "included studies",
}

FRAMEWORK_TERMS = {
    "framework", "salient", "cfir", "nasss", "re-aim", "implementation science",
    "mapped to", "validated", "necessary and sufficient", "companion paper",
}


def _contains_any(text: str, terms: set[str]) -> bool:
    return any(term in text for term in terms)


def build_manuscript_profile(state: DraftAnalysisState) -> dict:
    text = (state.get("draft_content") or "").lower()
    paper_type = (state.get("paper_type") or "").lower()

    is_systematic = (
        "systematic" in paper_type
        or "review" in paper_type
        or _contains_any(text, SYSTEMATIC_REVIEW_TERMS)
    )
    is_clinical_ai = _contains_any(text, BIOMEDICAL_TERMS) and _contains_any(text, CLINICAL_AI_TERMS)
    is_framework = _contains_any(text, FRAMEWORK_TERMS)

    if is_systematic:
        genre = "systematic_review"
        study_design = "evidence synthesis"
    elif is_framework:
        genre = "theory_framework"
        study_design = "framework validation"
    else:
        genre = "empirical_study" if "method" in text and "result" in text else "unknown"
        study_design = "unknown"

    domain_tags: list[str] = []
    if is_clinical_ai:
        domain_tags.extend(["clinical_ai", "biomedical", "implementation"])
    if "sepsis" in text:
        domain_tags.append("sepsis")
    if "machine learning" in text or "algorithm" in text:
        domain_tags.append("machine_learning")

    contribution_types: list[str] = []
    if is_systematic:
        contribution_types.append("systematic_review")
    if is_framework:
        contribution_types.append("framework_mapping")
    if "barrier" in text and "enabler" in text:
        contribution_types.append("implementation_barrier_synthesis")

    review_lenses: list[str] = []
    high_risk_checks: list[str] = []
    if is_systematic:
        review_lenses.extend(["systematic_review_methods", "evidence_synthesis", "risk_of_bias"])
        high_risk_checks.extend([
            "meta_analysis_justification",
            "heterogeneity",
            "risk_of_bias_integration",
            "protocol_registration",
            "publication_bias",
        ])
    if is_clinical_ai:
        review_lenses.extend(["clinical_ai_deployment", "causal_inference", "workflow_integration"])
        high_risk_checks.extend([
            "causal_chain",
            "post_deployment_performance",
            "ehr_data_pipeline",
            "workflow_adoption",
            "definition_heterogeneity",
        ])
    if is_framework:
        review_lenses.extend(["framework_validation", "implementation_science_positioning"])
        high_risk_checks.extend([
            "circular_framework_validation",
            "companion_paper_dependency",
            "framework_comparison",
            "generalizability_overclaim",
        ])

    retrieval_domains = ["semantic_scholar"]
    if is_clinical_ai:
        retrieval_domains = ["pubmed", "semantic_scholar"]

    profile = {
        "genre": genre,
        "study_design": study_design,
        "domain_tags": sorted(set(domain_tags)),
        "contribution_types": sorted(set(contribution_types)),
        "review_lenses": sorted(set(review_lenses)),
        "retrieval_domains": retrieval_domains,
        "high_risk_checks": sorted(set(high_risk_checks)),
        "rationale": "Heuristic profile inferred from manuscript text and upload context.",
    }

    logger.info(
        "[ManuscriptProfile] genre=%s domain_tags=%s high_risk_checks=%s",
        profile["genre"],
        profile["domain_tags"],
        len(profile["high_risk_checks"]),
    )
    return profile


def manuscript_profile_node(state: DraftAnalysisState) -> DraftAnalysisState:
    return {
        "manuscript_profile": build_manuscript_profile(state),
        "current_step": "Manuscript Profile",
        "progress_percentage": 12,
    }

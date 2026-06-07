"""
Manuscript Profile Node

Classifies the draft so downstream reviewers use the right standards for the
paper type instead of defaulting to generic ML-conference expectations.
"""

from __future__ import annotations

import re

from app.core.logging_config import get_logger
from app.workflows.draft_analysis.state import DraftAnalysisState
from app.workflows.draft_analysis.domain_routing import infer_domain_route

logger = get_logger(__name__)


BIOMEDICAL_PATTERNS = (
    r"\bsepsis\b",
    r"\bclinical\b",
    r"\bpatients?\b",
    r"\bhospitals?\b",
    r"\bmortality\b",
    r"\bEHR\b",
    r"\belectronic health records?\b",
    r"\bICU\b",
    r"\bemergency department\b",
    r"\bantibiotics?\b",
    r"\bcare bundles?\b",
    r"\bhealthcare\b",
)

CLINICAL_AI_PATTERNS = (
    r"\bmachine learning\b",
    r"\balgorithms?\b",
    r"\bpredicti(?:on|ve)\b",
    r"\bAI\b",
    r"\bartificial intelligence\b",
    r"\bdeployment\b",
    r"\bimplemented\b",
    r"\bimplementation\b",
    r"\balerts?\b",
    r"\bsilent trial\b",
    r"\breal[- ]world\b",
    r"\bclinical workflow\b",
    r"\bMLAs?\b",
)

SYSTEMATIC_REVIEW_PATTERNS = (
    r"\bsystematic review\b",
    r"\bPRISMA\b",
    r"\bsearch strategy\b",
    r"\bstudy selection\b",
    r"\bdata extraction\b",
    r"\brisk of bias\b",
    r"\bmeta-analysis\b",
    r"\bincluded studies\b",
    r"\beligibility criteria\b",
    r"\bdatabase search(?:es)?\b",
)

FRAMEWORK_PATTERNS = (
    r"\bSALIENT\b",
    r"\bCFIR\b",
    r"\bNASSS\b",
    r"\bRE-AIM\b",
    r"\bimplementation science\b",
    r"\bmapped to\b",
    r"\bnecessary and sufficient\b",
    r"\bcompanion paper\b",
)

MATERIALS_BATTERY_PATTERNS = (
    r"\bsodium[- ]ion batter(?:y|ies)\b",
    r"\bNa[- ]ion batter(?:y|ies)\b",
    r"\bSIBs?\b",
    r"\bcathodes?\b",
    r"\blayered oxides?\b",
    r"\bNa[xₓ]?[A-Za-z0-9().-]*O2\b",
    r"\bdesodiation\b",
    r"\bJahn[- ]Teller\b",
    r"\bP2\b",
    r"\bO3\b",
    r"\bprismatic\b",
    r"\bXRD\b",
    r"\bSEM\b",
    r"\belectrolyte\b",
    r"\bsolid electrolyte interphase\b",
    r"\bSEI\b",
    r"\bcathode electrolyte interphase\b",
    r"\bCEI\b",
)

HUMANITIES_EDUCATION_PATTERNS = (
    r"\bComputers and Composition\b",
    r"\bcomposition\b",
    r"\brhetoric\b",
    r"\bpedagog(?:y|ical)\b",
    r"\bclassroom\b",
    r"\bstudents?\b",
    r"\bwriting\b",
    r"\bteaching\b",
    r"\bcurriculum\b",
    r"\bliteracy\b",
    r"\bsocial justice\b",
    r"\bdigital rhetoric\b",
    r"\bcritical pedagogy\b",
    r"\bwriting classroom\b",
)

EMPIRICAL_ML_PATTERNS = (
    r"\bdataset\b",
    r"\bbenchmark\b",
    r"\bbaseline\b",
    r"\bablation\b",
    r"\btraining set\b",
    r"\btest set\b",
    r"\bvalidation set\b",
    r"\bAUC\b",
    r"\bF1\b",
    r"\baccuracy\b",
    r"\bprecision\b",
    r"\brecall\b",
    r"\bhyperparameters?\b",
    r"\bmodel architecture\b",
)

CONCEPTUAL_AI_PATTERNS = (
    r"\bgenerative AI\b",
    r"\bChat[- ]?GPT\b",
    r"\bartificial intelligence\b",
    r"\balgorithms?\b",
    r"\bAI ethics\b",
    r"\bsocial justice\b",
    r"\balgorithmic bias\b",
    r"\bhuman[- ]AI\b",
)

PUBLIC_HEALTH_PSYCH_PATTERNS = (
    r"\bmental health\b",
    r"\banxiety\b",
    r"\bdepression\b",
    r"\bpsychological distress\b",
    r"\badolescents?\b",
    r"\bteenagers?\b",
    r"\byouth\b",
    r"\bsocial media\b",
    r"\bscreen time\b",
    r"\bwell[- ]?being\b",
    r"\bpublic health\b",
    r"\bpsycholog(?:y|ical)\b",
)

LAW_POLICY_PATTERNS = (
    r"\blaw\b",
    r"\blegal\b",
    r"\bcourt\b",
    r"\bstatut(?:e|ory)\b",
    r"\bregulat(?:ion|ory)\b",
    r"\bconstitutional\b",
    r"\bprivacy\b",
    r"\bliability\b",
    r"\bgovernance\b",
    r"\bcompliance\b",
    r"\bcase law\b",
    r"\bjurisdiction\b",
)

BUSINESS_MANAGEMENT_PATTERNS = (
    r"\bbusiness\b",
    r"\bstrategic management\b",
    r"\bbusiness strategy\b",
    r"\bfirm\b",
    r"\bfirms\b",
    r"\borganizational performance\b",
    r"\boperations management\b",
    r"\bmarketing\b",
    r"\bentrepreneur(?:ship|ial)\b",
    r"\bsupply chain\b",
    r"\bmarket share\b",
    r"\bcompetitive advantage\b",
    r"\bcustomer\b",
)

ENVIRONMENTAL_ECOLOGY_PATTERNS = (
    r"\becolog(?:y|ical)\b",
    r"\bclimate\b",
    r"\bcarbon\b",
    r"\bbiodiversity\b",
    r"\bconservation\b",
    r"\becosystem\b",
    r"\bsustainab(?:ility|le)\b",
    r"\bhabitat\b",
    r"\bspecies richness\b",
    r"\bremote sensing\b",
    r"\blife cycle assessment\b",
    r"\bLCA\b",
)

MECHANICAL_CIVIL_PATTERNS = (
    r"\bmechanical\b",
    r"\bcivil engineering\b",
    r"\bstructural\b",
    r"\bfinite element\b",
    r"\bFEA\b",
    r"\bCFD\b",
    r"\bfluid dynamics\b",
    r"\bmanufacturing\b",
    r"\badditive manufacturing\b",
    r"\bconcrete\b",
    r"\bbridge\b",
    r"\btransportation\b",
    r"\bHVAC\b",
    r"\brobotics\b",
)

MATH_STATISTICS_PATTERNS = (
    r"\btheorem\b",
    r"\bproof\b",
    r"\blemma\b",
    r"\bcorollary\b",
    r"\bestimator\b",
    r"\basymptotic\b",
    r"\bidentifiability\b",
    r"\bBayesian\b",
    r"\bregression\b",
    r"\binference\b",
    r"\bMonte Carlo\b",
    r"\bconfidence interval\b",
)

NEURO_COGSCI_PATTERNS = (
    r"\bneuroscience\b",
    r"\bcognitive\b",
    r"\bcognition\b",
    r"\bbrain\b",
    r"\bfMRI\b",
    r"\bEEG\b",
    r"\bneural activity\b",
    r"\bworking memory\b",
    r"\battention\b",
    r"\bperception\b",
    r"\bbehavioral task\b",
    r"\bneuroimaging\b",
    r"\bpsychophysics\b",
)

EDUCATION_EMPIRICAL_PATTERNS = (
    r"\blearning outcomes?\b",
    r"\beducational intervention\b",
    r"\bstudent achievement\b",
    r"\bteacher\b",
    r"\bclassroom trial\b",
    r"\brandomized classroom\b",
    r"\bquasi[- ]experimental\b",
    r"\bpretest\b",
    r"\bposttest\b",
    r"\bassessment rubric\b",
    r"\blearning sciences?\b",
    r"\beducation policy\b",
)


def _count_matches(text: str, patterns: tuple[str, ...]) -> int:
    return sum(1 for pattern in patterns if re.search(pattern, text, flags=re.IGNORECASE))


def _has(text: str, pattern: str) -> bool:
    return bool(re.search(pattern, text, flags=re.IGNORECASE))


def _is_actual_systematic_review(text: str, paper_type: str) -> bool:
    if "systematic" in paper_type or paper_type in {"review", "systematic_review"}:
        return True
    signal_count = _count_matches(text, SYSTEMATIC_REVIEW_PATTERNS)
    has_review_phrase = _has(text, r"\bsystematic review\b|\bscoping review\b")
    has_methods_signal = signal_count >= 3 and _has(
        text,
        r"\b(search strategy|study selection|data extraction|eligibility criteria|included studies|PRISMA)\b",
    )
    negated_review_need = _has(
        text,
        r"\b(no|not|without|absent|lacking|lacks|needed|need for|need)\b.{0,80}\bsystematic review\b"
        r"|\bsystematic review\b.{0,80}\b(absent|lacking|needed|need|not available)\b",
    )
    return has_review_phrase and has_methods_signal and not negated_review_need


def _is_clinical_ai(text: str) -> bool:
    biomedical_score = _count_matches(text, BIOMEDICAL_PATTERNS)
    ai_score = _count_matches(text, CLINICAL_AI_PATTERNS)
    has_clinical_context = _has(text, r"\b(clinical|patients?|hospitals?|healthcare|EHR|sepsis|ICU)\b")
    return biomedical_score >= 2 and ai_score >= 2 and has_clinical_context


def _is_implementation_framework(text: str) -> bool:
    if not _count_matches(text, FRAMEWORK_PATTERNS):
        return False
    return _has(
        text,
        r"\b(implementation science|clinical|healthcare|AI task|SALIENT|CFIR|NASSS|RE-AIM|DECIDE-AI)\b",
    )


def _route_with_override(route, *, routing_domain: str, confidence: float, rationale: str):
    return type(route)(
        routing_domain=routing_domain,
        routing_confidence=confidence,
        secondary_domains=[
            domain for domain in [route.routing_domain, *route.secondary_domains]
            if domain != routing_domain
        ][:3],
        routing_rationale=rationale,
    )


def build_manuscript_profile(state: DraftAnalysisState) -> dict:
    text = state.get("draft_content") or ""
    paper_type = (state.get("paper_type") or "").lower()
    route = infer_domain_route(text, paper_type)

    is_systematic = _is_actual_systematic_review(text, paper_type)
    is_clinical_ai = _is_clinical_ai(text)
    is_framework = _is_implementation_framework(text)
    is_materials_battery = _count_matches(text, MATERIALS_BATTERY_PATTERNS) >= 3
    humanities_education_score = _count_matches(text, HUMANITIES_EDUCATION_PATTERNS)
    empirical_ml_score = _count_matches(text, EMPIRICAL_ML_PATTERNS)
    conceptual_ai_score = _count_matches(text, CONCEPTUAL_AI_PATTERNS)
    public_health_psych_score = _count_matches(text, PUBLIC_HEALTH_PSYCH_PATTERNS)
    law_policy_score = _count_matches(text, LAW_POLICY_PATTERNS)
    business_management_score = _count_matches(text, BUSINESS_MANAGEMENT_PATTERNS)
    environmental_ecology_score = _count_matches(text, ENVIRONMENTAL_ECOLOGY_PATTERNS)
    mechanical_civil_score = _count_matches(text, MECHANICAL_CIVIL_PATTERNS)
    math_statistics_score = _count_matches(text, MATH_STATISTICS_PATTERNS)
    neuro_cogsci_score = _count_matches(text, NEURO_COGSCI_PATTERNS)
    education_empirical_score = _count_matches(text, EDUCATION_EMPIRICAL_PATTERNS)
    is_humanities_education = humanities_education_score >= 3
    is_empirical_ml = empirical_ml_score >= 3 and _has(text, r"\b(methods?|results?|experiment|evaluation)\b")
    is_conceptual_ai = conceptual_ai_score >= 2 and not is_empirical_ml
    is_public_health_psych = public_health_psych_score >= 3 and not is_clinical_ai
    is_law_policy = law_policy_score >= 3
    is_business_management = business_management_score >= 3
    is_environmental_ecology = environmental_ecology_score >= 3
    is_mechanical_civil = mechanical_civil_score >= 3
    is_math_statistics = math_statistics_score >= 3
    is_neuro_cogsci = neuro_cogsci_score >= 3
    is_education_empirical = education_empirical_score >= 3 and _has(
        text,
        r"\b(methods?|results?|intervention|trial|quasi[- ]experimental|pretest|posttest|assessment)\b",
    )

    forced_route = (state.get("forced_route") or "").strip()
    if forced_route:
        route = _route_with_override(
            route,
            routing_domain=forced_route,
            confidence=0.82,
            rationale=f"Forced reroute after quality gate selected {forced_route}.",
        )
    elif is_education_empirical:
        route = _route_with_override(
            route,
            routing_domain="education_empirical",
            confidence=0.84 if education_empirical_score >= 5 else 0.72,
            rationale="Matched empirical education or learning-sciences signals, including intervention/assessment context.",
        )
    elif is_neuro_cogsci:
        route = _route_with_override(
            route,
            routing_domain="neuroscience_cognitive_science",
            confidence=0.84 if neuro_cogsci_score >= 5 else 0.72,
            rationale="Matched neuroscience/cognitive-science signals with neural, cognitive, or behavioral-task context.",
        )
    elif is_environmental_ecology:
        route = _route_with_override(
            route,
            routing_domain="environmental_ecology",
            confidence=0.84 if environmental_ecology_score >= 5 else 0.72,
            rationale="Matched environmental science or ecology signals with ecosystem, climate, conservation, or sustainability context.",
        )
    elif is_mechanical_civil:
        route = _route_with_override(
            route,
            routing_domain="mechanical_civil_engineering",
            confidence=0.84 if mechanical_civil_score >= 5 else 0.72,
            rationale="Matched mechanical/civil engineering signals around design, structures, fluids, manufacturing, or infrastructure.",
        )
    elif is_math_statistics:
        route = _route_with_override(
            route,
            routing_domain="math_statistics",
            confidence=0.84 if math_statistics_score >= 5 else 0.72,
            rationale="Matched mathematics/statistics signals around proofs, estimators, inference, or identifiability.",
        )
    elif is_law_policy:
        route = _route_with_override(
            route,
            routing_domain="law_policy",
            confidence=0.84 if law_policy_score >= 5 else 0.72,
            rationale="Matched legal, regulatory, governance, or policy-analysis signals.",
        )
    elif is_business_management:
        route = _route_with_override(
            route,
            routing_domain="business_management",
            confidence=0.84 if business_management_score >= 5 else 0.72,
            rationale="Matched business, strategy, management, operations, or market-analysis signals.",
        )
    elif is_humanities_education:
        route = _route_with_override(
            route,
            routing_domain="humanities_education",
            confidence=0.86 if humanities_education_score >= 5 else 0.74,
            rationale=(
                "Matched composition/pedagogy/humanities education signals; "
                "AI terminology is treated as manuscript topic, not evidence that this is an ML paper."
            ),
        )
    elif is_public_health_psych:
        route = _route_with_override(
            route,
            routing_domain="public_health_psychology",
            confidence=0.84 if public_health_psych_score >= 5 else 0.72,
            rationale=(
                "Matched behavioral-health, psychology, adolescent, or social-media signals; "
                "health terminology is treated as public-health/psychology evidence, not clinical-AI deployment."
            ),
        )
    elif route.routing_domain == "computer_science_ml" and is_conceptual_ai:
        route = _route_with_override(
            route,
            routing_domain="computer_science_conceptual",
            confidence=max(0.58, min(route.routing_confidence, 0.72)),
            rationale="AI terminology appears in a conceptual/sociotechnical context without empirical ML-study signals.",
        )

    if is_systematic:
        genre = "systematic_review"
        study_design = "evidence synthesis"
    elif is_materials_battery:
        genre = "literature_review" if _has(text, r"\breview\b") else "journal_article"
        study_design = "materials science review"
    elif is_framework:
        genre = "theory_framework"
        study_design = "framework validation"
    elif is_education_empirical:
        genre = "empirical_study"
        study_design = "education intervention or assessment study"
    elif is_neuro_cogsci:
        genre = "empirical_study"
        study_design = "neuroscience or cognitive science study"
    elif is_environmental_ecology:
        genre = "empirical_study"
        study_design = "environmental or ecological study"
    elif is_mechanical_civil:
        genre = "empirical_study"
        study_design = "engineering design, model, or validation study"
    elif is_math_statistics:
        genre = "theoretical_article" if _has(text, r"\b(theorem|proof|lemma|corollary)\b") else "methods_article"
        study_design = "mathematical/statistical methods"
    elif is_law_policy:
        genre = "legal_policy_analysis"
        study_design = "doctrinal, regulatory, or policy analysis"
    elif is_business_management:
        genre = "empirical_study" if _has(text, r"\b(methods?|results?|survey|interviews?|regression|case stud)\b") else "conceptual_article"
        study_design = "business or management study"
    elif is_humanities_education:
        genre = "pedagogical_conceptual"
        study_design = "conceptual pedagogy"
    elif is_conceptual_ai:
        genre = "conceptual_article"
        study_design = "conceptual analysis"
    else:
        lower = text.lower()
        genre = "empirical_study" if "method" in lower and "result" in lower else "unknown"
        study_design = "unknown"

    if is_empirical_ml:
        evidence_mode = "empirical_ml"
    elif is_systematic:
        evidence_mode = "evidence_synthesis"
    elif is_education_empirical:
        evidence_mode = "empirical_education"
    elif is_math_statistics and genre == "theoretical_article":
        evidence_mode = "theoretical"
    elif is_law_policy:
        evidence_mode = "conceptual" if genre == "legal_policy_analysis" else "empirical"
    elif is_humanities_education:
        evidence_mode = "pedagogical"
    elif is_framework or is_conceptual_ai:
        evidence_mode = "conceptual"
    elif genre == "empirical_study":
        evidence_mode = "empirical"
    else:
        evidence_mode = "unknown"

    domain_tags: list[str] = []
    if is_clinical_ai:
        domain_tags.extend(["clinical_ai", "biomedical", "implementation"])
    if is_public_health_psych:
        domain_tags.extend(["public_health", "psychology", "behavioral_health", "adolescent_mental_health"])
    if is_law_policy:
        domain_tags.extend(["law", "policy", "governance"])
    if is_business_management:
        domain_tags.extend(["business", "management", "strategy"])
    if is_environmental_ecology:
        domain_tags.extend(["environmental_science", "ecology", "sustainability"])
    if is_mechanical_civil:
        domain_tags.extend(["mechanical_engineering", "civil_engineering", "engineering_design"])
    if is_math_statistics:
        domain_tags.extend(["mathematics", "statistics", "methods"])
    if is_neuro_cogsci:
        domain_tags.extend(["neuroscience", "cognitive_science", "behavioral_methods"])
    if is_education_empirical:
        domain_tags.extend(["education", "learning_sciences", "empirical_education"])
    if _has(text, r"\bsepsis\b"):
        domain_tags.append("sepsis")
    if _has(text, r"\b(machine learning|algorithms?)\b"):
        domain_tags.append("machine_learning")
    if is_humanities_education:
        domain_tags.extend(["humanities", "education", "composition_pedagogy"])
    if is_conceptual_ai:
        domain_tags.extend(["ai_ethics", "sociotechnical_ai"])
    if is_materials_battery:
        domain_tags.extend(["materials_science", "battery", "sodium_ion"])

    contribution_types: list[str] = []
    if is_systematic:
        contribution_types.append("systematic_review")
    if is_framework:
        contribution_types.append("framework_mapping")
    if is_humanities_education:
        contribution_types.append("pedagogical_conceptual")
    if is_conceptual_ai:
        contribution_types.append("conceptual_ai")
    if is_materials_battery:
        contribution_types.append("materials_review")
    if is_law_policy:
        contribution_types.append("legal_policy_analysis")
    if is_business_management:
        contribution_types.append("management_research")
    if is_environmental_ecology:
        contribution_types.append("environmental_ecology_study")
    if is_mechanical_civil:
        contribution_types.append("engineering_validation")
    if is_math_statistics:
        contribution_types.append("mathematical_statistical_method")
    if is_neuro_cogsci:
        contribution_types.append("neurocognitive_study")
    if is_education_empirical:
        contribution_types.append("education_empirical_study")
    lower = text.lower()
    if "barrier" in lower and "enabler" in lower:
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
    if is_public_health_psych:
        review_lenses.extend(["behavioral_health", "psychology_methods", "causal_inference"])
        high_risk_checks.extend([
            "cross_sectional_causal_language",
            "self_report_measurement",
            "longitudinal_evidence",
            "sampling_generalizability",
            "effect_size_reporting",
        ])
    if is_law_policy:
        review_lenses.extend(["legal_doctrinal_analysis", "policy_implementation", "governance"])
        high_risk_checks.extend([
            "jurisdictional_scope",
            "authority_grounding",
            "normative_assumptions",
            "implementation_feasibility",
        ])
    if is_business_management:
        review_lenses.extend(["management_theory", "construct_validity", "managerial_implications"])
        high_risk_checks.extend([
            "construct_measurement",
            "identification_or_case_logic",
            "external_validity",
            "managerial_overclaim",
        ])
    if is_environmental_ecology:
        review_lenses.extend(["ecological_methods", "environmental_measurement", "policy_relevance"])
        high_risk_checks.extend([
            "spatial_temporal_scale",
            "sampling_design",
            "uncertainty_quantification",
            "causal_ecological_overclaim",
        ])
    if is_mechanical_civil:
        review_lenses.extend(["engineering_design", "model_validation", "safety_reliability"])
        high_risk_checks.extend([
            "boundary_conditions",
            "validation_against_measurement",
            "safety_factor_reporting",
            "constructability_or_manufacturability",
        ])
    if is_math_statistics:
        review_lenses.extend(["mathematical_rigor", "statistical_inference", "assumption_checking"])
        high_risk_checks.extend([
            "proof_gap",
            "assumption_identifiability",
            "simulation_validation",
            "uncertainty_reporting",
        ])
    if is_neuro_cogsci:
        review_lenses.extend(["neurocognitive_methods", "behavioral_task_design", "statistical_inference"])
        high_risk_checks.extend([
            "construct_validity",
            "multiple_comparisons",
            "sample_size_power",
            "neural_claim_overreach",
        ])
    if is_education_empirical:
        review_lenses.extend(["education_methods", "assessment_validity", "classroom_context"])
        high_risk_checks.extend([
            "comparison_condition",
            "implementation_fidelity",
            "effect_size_reporting",
            "equity_and_context",
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
    if is_humanities_education:
        review_lenses.extend(["composition_pedagogy", "humanities_argument", "classroom_translation"])
        high_risk_checks.extend([
            "pedagogical_artifact_specificity",
            "theoretical_grounding",
            "ai_system_claim_accuracy",
            "classroom_boundary_conditions",
        ])
    elif is_conceptual_ai:
        review_lenses.extend(["ai_ethics", "sociotechnical_positioning", "conceptual_rigor"])
        high_risk_checks.extend([
            "technical_overclaim",
            "conceptual_operationalization",
            "current_ai_landscape",
        ])
    if is_materials_battery:
        review_lenses.extend(["materials_degradation", "battery_cathode", "electrochemistry"])
        high_risk_checks.extend([
            "phase_specific_degradation",
            "electrolyte_interface_scope",
            "commercial_viability_overclaim",
            "characterization_evidence",
        ])

    retrieval_domains = ["semantic_scholar"]
    if is_clinical_ai or is_public_health_psych:
        retrieval_domains = ["pubmed", "semantic_scholar"]

    profile = {
        "genre": genre,
        "study_design": study_design,
        "evidence_mode": evidence_mode,
        "routing_domain": route.routing_domain,
        "routing_confidence": route.routing_confidence,
        "secondary_domains": route.secondary_domains,
        "routing_rationale": route.routing_rationale,
        "route_conflicts": [
            "ai_terms_in_humanities_context"
            for _ in [0]
            if is_humanities_education and conceptual_ai_score >= 1 and route.routing_domain != "computer_science_ml"
        ],
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

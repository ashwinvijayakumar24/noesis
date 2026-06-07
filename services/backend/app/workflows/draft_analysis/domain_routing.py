"""Broad domain routing and prompt packs for draft analysis."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


ROUTING_DOMAINS = {
    "biomedical",
    "biology",
    "chemistry_materials",
    "physics",
    "electrical_engineering",
    "computer_science_ml",
    "computer_science_conceptual",
    "public_health_psychology",
    "social_science_economics",
    "social_science_qualitative",
    "law_policy",
    "business_management",
    "environmental_ecology",
    "mechanical_civil_engineering",
    "math_statistics",
    "neuroscience_cognitive_science",
    "education_empirical",
    "humanities_education",
    "humanities_theory",
    "generic_academic",
}


@dataclass(frozen=True)
class DomainRoute:
    routing_domain: str
    routing_confidence: float
    secondary_domains: list[str]
    routing_rationale: str


DOMAIN_PATTERNS: dict[str, tuple[str, ...]] = {
    "biomedical": (
        r"\bclinical\b", r"\bpatients?\b", r"\bhospitals?\b", r"\bcohort\b",
        r"\bmortality\b", r"\bdiagnos(?:is|tic)\b", r"\bhealthcare\b",
        r"\belectronic health records?\b", r"\bEHR\b", r"\bICU\b", r"\btrial\b",
    ),
    "biology": (
        r"\bgene\b", r"\bprotein\b", r"\bcell(?:ular)?\b", r"\becology\b",
        r"\borganism\b", r"\bgenome\b", r"\bRNA\b", r"\bDNA\b", r"\benzyme\b",
        r"\bphenotype\b", r"\bevolution\b",
    ),
    "chemistry_materials": (
        r"\bchemistry\b", r"\bcatalyst\b", r"\bsynthesis\b", r"\bmaterials?\b",
        r"\bpolymers?\b", r"\bbatter(?:y|ies)\b", r"\bcathodes?\b", r"\banodes?\b",
        r"\belectrolyte\b", r"\bXRD\b", r"\bSEM\b", r"\bTEM\b", r"\bcrystal\b",
        r"\bsodium[- ]ion\b", r"\blithium[- ]ion\b", r"\blayered oxide\b",
    ),
    "physics": (
        r"\bquantum\b", r"\bparticle\b", r"\brelativity\b", r"\bcosmology\b",
        r"\boptics\b", r"\bphonon\b", r"\bspin\b", r"\bHamiltonian\b",
        r"\bfield theory\b", r"\bthermodynamics\b",
    ),
    "electrical_engineering": (
        r"\bcircuit\b", r"\bCMOS\b", r"\bFPGA\b", r"\bantenna\b", r"\bsignal\b",
        r"\bpower electronics\b", r"\bcontrol system\b", r"\bsensor\b",
        r"\bsemiconductor device\b", r"\bVLSI\b",
    ),
    "computer_science_ml": (
        r"\bmachine learning\b", r"\bdeep learning\b", r"\bneural network\b",
        r"\btransformer\b", r"\balgorithm\b", r"\bdataset\b", r"\bbenchmark\b",
        r"\bclassification\b", r"\bAUC\b", r"\baccuracy\b", r"\bF1\b",
    ),
    "computer_science_conceptual": (
        r"\bartificial intelligence\b", r"\bgenerative AI\b", r"\bChat[- ]?GPT\b",
        r"\blarge language models?\b", r"\balgorithmic bias\b", r"\bAI ethics\b",
        r"\bresponsible AI\b", r"\bhuman[- ]AI\b",
    ),
    "public_health_psychology": (
        r"\bmental health\b", r"\banxiety\b", r"\bdepression\b",
        r"\badolescents?\b", r"\bteenagers?\b", r"\byouth\b",
        r"\bsocial media\b", r"\bpsycholog(?:y|ical)\b",
        r"\bwellbeing\b", r"\bwell-being\b", r"\bpublic health\b",
    ),
    "social_science_economics": (
        r"\beconom(?:y|ics|etric)\b", r"\bsurvey\b", r"\bregression\b",
        r"\bpolicy\b", r"\blabor market\b", r"\bGDP\b", r"\binflation\b",
        r"\bsocial\b", r"\bqualitative interviews?\b",
    ),
    "social_science_qualitative": (
        r"\bqualitative\b", r"\binterviews?\b", r"\bethnograph(?:y|ic)\b",
        r"\bcase stud(?:y|ies)\b", r"\bthematic analysis\b", r"\bparticipatory\b",
        r"\bcritical race\b", r"\bsocial justice\b", r"\bequity\b",
    ),
    "law_policy": (
        r"\blaw\b", r"\blegal\b", r"\bcourt\b", r"\bstatut(?:e|ory)\b",
        r"\bregulat(?:ion|ory)\b", r"\bconstitutional\b", r"\bprivacy\b",
        r"\bliability\b", r"\bgovernance\b", r"\bcompliance\b",
        r"\bjurisdiction\b", r"\bcase law\b", r"\bpolicy analysis\b",
    ),
    "business_management": (
        r"\bbusiness\b", r"\bstrategic management\b", r"\bbusiness strategy\b",
        r"\bfirm\b", r"\bfirms\b", r"\borganizational performance\b",
        r"\boperations management\b", r"\bmarketing\b",
        r"\bentrepreneur(?:ship|ial)\b", r"\bcustomer\b", r"\bmarket share\b",
        r"\bsupply chain\b", r"\bcompetitive advantage\b", r"\bROI\b",
    ),
    "environmental_ecology": (
        r"\becolog(?:y|ical)\b", r"\bclimate\b", r"\bcarbon\b",
        r"\bbiodiversity\b", r"\bconservation\b", r"\becosystem\b",
        r"\bsustainab(?:ility|le)\b", r"\bhabitat\b", r"\bspecies richness\b",
        r"\bremote sensing\b", r"\blife cycle assessment\b", r"\bLCA\b",
    ),
    "mechanical_civil_engineering": (
        r"\bmechanical\b", r"\bcivil engineering\b", r"\bstructural\b",
        r"\bfinite element\b", r"\bFEA\b", r"\bCFD\b", r"\bfluid dynamics\b",
        r"\bmanufacturing\b", r"\badditive manufacturing\b", r"\bconcrete\b",
        r"\bbridge\b", r"\btransportation\b", r"\bHVAC\b", r"\brobotics\b",
    ),
    "math_statistics": (
        r"\btheorem\b", r"\bproof\b", r"\blemma\b", r"\bcorollary\b",
        r"\bestimator\b", r"\basymptotic\b", r"\bidentifiability\b",
        r"\bBayesian\b", r"\bregression\b", r"\binference\b",
        r"\bMonte Carlo\b", r"\bconfidence interval\b", r"\bp[- ]value\b",
    ),
    "neuroscience_cognitive_science": (
        r"\bneuroscience\b", r"\bcognitive\b", r"\bcognition\b",
        r"\bbrain\b", r"\bfMRI\b", r"\bEEG\b", r"\bneural activity\b",
        r"\bworking memory\b", r"\battention\b", r"\bperception\b",
        r"\bbehavioral task\b", r"\bneuroimaging\b", r"\bpsychophysics\b",
    ),
    "education_empirical": (
        r"\blearning outcomes?\b", r"\beducational intervention\b",
        r"\bteacher\b", r"\bstudent achievement\b", r"\bclassroom trial\b",
        r"\brandomized classroom\b", r"\bquasi[- ]experimental\b",
        r"\bpretest\b", r"\bposttest\b", r"\bassessment rubric\b",
        r"\blearning sciences?\b", r"\beducation policy\b",
    ),
    "humanities_education": (
        r"\bcomposition\b", r"\brhetoric\b", r"\bpedagog(?:y|ical)\b",
        r"\bclassroom\b", r"\bstudents?\b", r"\bwriting\b", r"\bteaching\b",
        r"\bcurriculum\b", r"\bliteracy\b", r"\bComputers and Composition\b",
        r"\bdigital rhetoric\b", r"\bcritical pedagogy\b", r"\bsocial justice\b",
    ),
    "humanities_theory": (
        r"\bphilosophy\b", r"\bliterary\b", r"\bhistorical\b", r"\bethics\b",
        r"\btheory\b", r"\barchive\b", r"\btextual\b", r"\binterpretation\b",
        r"\bcritical analysis\b",
    ),
}


DOMAIN_PROMPT_PACKS: dict[str, str] = {
    "biomedical": (
        "Review as biomedical or clinical research. Prioritize study design, cohort definition, "
        "endpoints, bias/confounding, statistical reporting, clinical relevance, ethics, protocol "
        "or reporting standards only when appropriate to the manuscript type, and whether claims "
        "about health outcomes are causally supported."
    ),
    "biology": (
        "Review as biology research. Prioritize biological mechanism, experimental controls, "
        "sample size/replication, assay validity, organism/cell-model relevance, statistical support, "
        "and whether mechanistic claims are matched to evidence."
    ),
    "chemistry_materials": (
        "Review as chemistry/materials research. Prioritize mechanism, synthesis or processing "
        "details, characterization evidence, structure-property relationships, electrochemical or "
        "materials performance metrics, degradation pathways, reproducibility, and whether practical "
        "or commercial claims are properly qualified."
    ),
    "physics": (
        "Review as physics research. Prioritize assumptions, derivations, dimensional consistency, "
        "experimental setup, uncertainty analysis, agreement with theory/prior measurements, and "
        "whether conclusions follow from the model or data."
    ),
    "electrical_engineering": (
        "Review as electrical engineering research. Prioritize system/circuit design, signal or "
        "power constraints, hardware feasibility, implementation detail, benchmark comparisons, "
        "measurement setup, reliability, and reproducibility."
    ),
    "computer_science_ml": (
        "Review as computer science or ML research. Prioritize datasets, baselines, metrics, "
        "ablations, leakage risks, statistical reliability, reproducibility, compute/implementation "
        "details, and positioning against current methods. Apply these empirical ML expectations "
        "only when the manuscript is actually an empirical/model-development paper."
    ),
    "computer_science_conceptual": (
        "Review as conceptual computer science, AI ethics, or human-AI scholarship. Prioritize "
        "conceptual precision, sociotechnical framing, engagement with AI ethics/HCI literature, "
        "scope conditions, and whether technical claims about AI systems are accurate. Do not demand "
        "benchmarks, ablations, or datasets unless the manuscript claims empirical ML evaluation."
    ),
    "public_health_psychology": (
        "Review as public-health, psychology, or behavioral-health scholarship. Prioritize "
        "measurement validity, population/sampling, confounding, causal language, longitudinal "
        "versus cross-sectional evidence, risk of bias, evidence-synthesis transparency where "
        "relevant, and whether mental-health claims are proportionate to the data."
    ),
    "social_science_economics": (
        "Review as social science/economics research. Prioritize identification strategy, sampling, "
        "measurement validity, confounding, robustness checks, external validity, policy relevance, "
        "and whether causal language is justified."
    ),
    "social_science_qualitative": (
        "Review as qualitative social science scholarship. Prioritize research question clarity, "
        "sampling or case rationale, positionality, data collection transparency, coding/thematic "
        "rigor, triangulation, ethics, and whether interpretive claims are grounded in evidence."
    ),
    "law_policy": (
        "Review as legal, regulatory, or policy scholarship. Prioritize doctrinal accuracy, "
        "statutory and case-law grounding, jurisdictional scope, policy mechanism clarity, "
        "normative assumptions, implementation feasibility, and whether legal or governance "
        "claims are supported by appropriate authorities."
    ),
    "business_management": (
        "Review as business or management scholarship. Prioritize theory contribution, construct "
        "validity, identification or case logic, managerial implications, market or organizational "
        "context, robustness, and whether strategy or performance claims are proportionate to the evidence."
    ),
    "environmental_ecology": (
        "Review as environmental science or ecology research. Prioritize spatial and temporal scale, "
        "sampling design, measurement validity, uncertainty, confounding, ecosystem or climate "
        "mechanisms, reproducibility, and whether policy or sustainability claims follow from the data."
    ),
    "mechanical_civil_engineering": (
        "Review as mechanical or civil engineering research. Prioritize design assumptions, load or "
        "boundary conditions, model validation, measurement setup, safety factors, reliability, "
        "manufacturability or constructability, standards compliance, and benchmark comparisons."
    ),
    "math_statistics": (
        "Review as mathematics or statistics scholarship. Prioritize definitions, assumptions, "
        "proof validity, identifiability, estimator properties, simulation or empirical validation "
        "where relevant, uncertainty quantification, and whether claims follow from the stated results."
    ),
    "neuroscience_cognitive_science": (
        "Review as neuroscience or cognitive science research. Prioritize task design, construct "
        "validity, neural or behavioral measurement, preprocessing/statistical choices, multiple "
        "comparisons, sample size, confounding, and whether cognitive or neural claims are overextended."
    ),
    "education_empirical": (
        "Review as empirical education or learning-sciences research. Prioritize intervention design, "
        "assessment validity, classroom/context description, sampling, comparison condition, fidelity, "
        "effect sizes, equity implications, and whether learning claims are supported by the study design."
    ),
    "humanities_education": (
        "Review as humanities, rhetoric/composition, and education scholarship. Prioritize thesis "
        "clarity, pedagogical usefulness, classroom artifacts, theoretical grounding, rhetorical "
        "and composition literature, ethical framing, and conceptual contribution. Do not demand "
        "ML datasets, baselines, ablations, control groups, or benchmark metrics unless the paper "
        "explicitly presents itself as an empirical ML evaluation."
    ),
    "humanities_theory": (
        "Review as humanities/theory scholarship. Prioritize thesis clarity, engagement with primary "
        "and secondary sources, interpretive rigor, conceptual distinctions, argumentative structure, "
        "and contribution to the scholarly debate."
    ),
    "generic_academic": (
        "Review as a general academic manuscript. Prioritize contribution clarity, fit between claims "
        "and evidence, method transparency, literature positioning, citation adequacy, limitations, "
        "structure, and concrete revisions that would improve publishability."
    ),
}


FORBIDDEN_REVIEW_STANDARDS: dict[str, tuple[str, ...]] = {
    "humanities_education": (
        "Do not require datasets, ML baselines, ablations, control groups, AUC/F1 metrics, "
        "or benchmark comparisons unless the manuscript explicitly claims empirical ML evaluation."
    ),
    "humanities_theory": (
        "Do not require laboratory experiments, clinical protocols, or ML benchmark standards "
        "unless the manuscript explicitly claims those forms of evidence."
    ),
    "social_science_qualitative": (
        "Do not require randomized trials, ML baselines, or quantitative effect-size reporting "
        "unless the manuscript explicitly presents that design."
    ),
    "law_policy": (
        "Do not require laboratory, clinical, or ML benchmark evidence for doctrinal, normative, "
        "or policy-analysis claims unless the manuscript explicitly presents empirical evaluation."
    ),
    "business_management": (
        "Do not require ML benchmarks or clinical trial standards. For conceptual strategy papers, "
        "do not demand econometric identification unless the manuscript makes causal empirical claims."
    ),
    "math_statistics": (
        "Do not require domain experiments for purely theoretical results, but do require simulations "
        "or applied validation when the manuscript claims practical empirical performance."
    ),
    "education_empirical": (
        "Do not apply humanities essay standards to empirical education studies, and do not apply "
        "ML benchmark standards unless the manuscript evaluates an ML system."
    ),
    "computer_science_conceptual": (
        "Do not require empirical model-development reporting unless the manuscript claims to "
        "build, train, or evaluate an ML system."
    ),
    "public_health_psychology": (
        "Do not apply clinical-AI deployment, EHR vendor, hospital workflow, or medical-device "
        "standards unless the manuscript explicitly studies those systems."
    ),
    "generic_academic": (
        "Use broad scholarly standards and avoid discipline-specific checklists unless the draft "
        "clearly signals that discipline and evidence mode."
    ),
}


def get_forbidden_review_standards(profile: dict[str, Any] | None) -> str:
    profile = profile or {}
    domain = profile.get("routing_domain") or "generic_academic"
    standards = list(FORBIDDEN_REVIEW_STANDARDS.get(domain, ()))
    evidence_mode = str(profile.get("evidence_mode") or "").lower()
    if evidence_mode in {"conceptual", "theoretical", "pedagogical"}:
        standards.append(
            "Because this manuscript is not classified as empirical/model-development work, "
            "do not convert conceptual or pedagogical weaknesses into demands for ML experiments."
        )
    return " ".join(standards)


def _count_matches(text: str, patterns: tuple[str, ...]) -> int:
    return sum(1 for pattern in patterns if re.search(pattern, text or "", flags=re.IGNORECASE))


def infer_domain_route(text: str, paper_type: str = "") -> DomainRoute:
    scores = {
        domain: _count_matches(text, patterns)
        for domain, patterns in DOMAIN_PATTERNS.items()
    }
    if "review" in (paper_type or "").lower():
        # Paper type should not dominate the domain, but it is useful context.
        scores["generic_academic"] = scores.get("generic_academic", 0) + 1

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best_domain, best_score = ranked[0] if ranked else ("generic_academic", 0)
    if best_score <= 1:
        return DomainRoute(
            routing_domain="generic_academic",
            routing_confidence=0.35,
            secondary_domains=[],
            routing_rationale="No broad domain had enough evidence; using the general academic review route.",
        )

    secondary = [domain for domain, score in ranked[1:4] if score >= 2]
    confidence = min(0.95, 0.45 + best_score * 0.08)
    return DomainRoute(
        routing_domain=best_domain,
        routing_confidence=round(confidence, 2),
        secondary_domains=secondary,
        routing_rationale=f"Matched {best_score} broad-domain signals for {best_domain}.",
    )


def get_domain_prompt_pack(profile: dict[str, Any] | None) -> str:
    profile = profile or {}
    domain = profile.get("routing_domain") or "generic_academic"
    return DOMAIN_PROMPT_PACKS.get(domain, DOMAIN_PROMPT_PACKS["generic_academic"])


def domain_context_block(profile: dict[str, Any] | None) -> str:
    profile = profile or {}
    domain = profile.get("routing_domain") or "generic_academic"
    secondary = ", ".join(profile.get("secondary_domains") or []) or "none"
    forbidden = get_forbidden_review_standards(profile)
    return (
        "\nBROAD REVIEW ROUTE:\n"
        f"- Routing domain: {domain}\n"
        f"- Routing confidence: {profile.get('routing_confidence', 'unknown')}\n"
        f"- Secondary domains: {secondary}\n"
        f"- Genre: {profile.get('genre', 'unknown')}\n"
        f"- Evidence mode: {profile.get('evidence_mode', 'unknown')}\n"
        f"- Internal rationale: {profile.get('routing_rationale', '')}\n"
        f"- Domain review priorities: {get_domain_prompt_pack(profile)}\n"
        f"- Forbidden review standards: {forbidden or 'none'}\n"
    )

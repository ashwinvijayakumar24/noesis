"""
Profile-Aware Diagnostic Findings Node

Adds manuscript-type checks that generic claim/gap extraction misses, especially
for systematic reviews, clinical AI deployment papers, and framework-validation
manuscripts.
"""

from __future__ import annotations

import re
from typing import Any

from app.core.logging_config import get_logger
from app.workflows.draft_analysis.state import DraftAnalysisState

logger = get_logger(__name__)


def _clip_anchor(text: str, limit: int = 500) -> str:
    normalized = re.sub(r"\s+", " ", (text or "")).strip()
    if len(normalized) <= limit:
        return normalized
    clipped = normalized[:limit].rstrip()
    boundary = max(clipped.rfind("."), clipped.rfind(";"), clipped.rfind(","), clipped.rfind(" "))
    if boundary >= max(60, limit - 90):
        clipped = clipped[:boundary].rstrip(" ,;.")
    else:
        clipped = clipped.rstrip(" ,;.")
    return f"{clipped}..."


def _snippet(text: str, pattern: str, fallback: str = "") -> str:
    match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return fallback
    start = max(0, match.start() - 80)
    end = min(len(text), match.end() + 120)
    return _clip_anchor(text[start:end], 500)


def _has_any(text: str, terms: list[str]) -> bool:
    lowered = text.lower()
    return any(term.lower() in lowered for term in terms)


def _finding(
    *,
    finding_type: str,
    severity: str,
    section_reference: str,
    anchor_text: str,
    problem: str,
    why_it_matters: str,
    suggested_action: str,
    confidence: float = 0.85,
) -> dict[str, Any]:
    return {
        "finding_type": finding_type,
        "severity": severity,
        "section_reference": section_reference,
        "anchor_text": _clip_anchor(anchor_text, 500),
        "problem": problem,
        "why_it_matters": why_it_matters,
        "suggested_action": suggested_action,
        "confidence": confidence,
    }


def _systematic_review_findings(text: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    lower = text.lower()

    if "systematic review" in lower and not _has_any(lower, ["prospero", "registered protocol", "protocol registration"]):
        findings.append(_finding(
            finding_type="systematic_review",
            severity="major",
            section_reference="Methods",
            anchor_text=_snippet(text, r"systematic review|PRISMA|Search strategy", "systematic review methods"),
            problem="The review describes PRISMA-style methods but does not clearly report protocol registration.",
            why_it_matters="Systematic-review readers expect registration status or an explicit statement that no protocol was registered; without it, selective outcome and method changes are harder to rule out.",
            suggested_action="State whether the review was registered, provide the registry identifier if available, or explicitly say no protocol was registered and justify that choice.",
        ))

    if _has_any(lower, ["prisma", "flow diagram", "flowchart", "figure 1"]) and not _has_any(lower, ["excluded because", "exclusion reasons", "reasons for exclusion", "full-text exclusions"]):
        findings.append(_finding(
            finding_type="systematic_review",
            severity="major",
            section_reference="Methods/Results",
            anchor_text=_snippet(text, r"PRISMA|Figure 1|flow diagram|screening", "PRISMA screening flow"),
            problem="The PRISMA flow is referenced but exclusion reasons are not sufficiently transparent in the manuscript text.",
            why_it_matters="Systematic-review readers need enough screening detail to judge whether exclusions were reproducible and whether relevant study classes were selectively removed.",
            suggested_action="Add the full-text exclusion breakdown in the Results or a table, including counts and specific reasons for excluded studies.",
        ))

    english_only = re.search(
        r"(titles?\s+and\s+abstracts?|abstracts?).{0,80}(english)|english.{0,80}(titles?\s+and\s+abstracts?|abstracts?)",
        lower,
        flags=re.DOTALL,
    )
    if english_only or _has_any(lower, ["english-language", "english language only", "published in english"]):
        findings.append(_finding(
            finding_type="systematic_review",
            severity="major",
            section_reference="Methods/Limitations",
            anchor_text=_snippet(text, r"English.{0,160}(title|abstract|language)|title.{0,160}abstract.{0,160}English", ""),
            problem="The search appears restricted to English-language titles or abstracts, but the limitation is not sufficiently handled.",
            why_it_matters="Language restrictions can bias systematic reviews by under-representing relevant work published in other languages or in internationally focused venues.",
            suggested_action="Explicitly acknowledge the English-language search restriction in the Limitations section and discuss how it may affect completeness and generalizability.",
        ))

    # Gray-literature / source-breadth check — domain-agnostic. Applies to any
    # applied/real-world systematic review, not just clinical ones.
    if (
        _has_any(lower, ["systematic review", "implementation", "deployed", "real-world", "real world", "applied", "in practice"])
        and not _has_any(lower, ["gray literature", "grey literature", "white paper", "quality improvement report", "technical report", "vendor report", "preprint", "registries", "registry"])
    ):
        findings.append(_finding(
            finding_type="systematic_review",
            severity="major",
            section_reference="Methods/Search Strategy",
            anchor_text=_snippet(text, r"database.{0,180}search|searched.{0,260}(PubMed|Embase|Scopus|Web of Science|CINAHL|PsycINFO)|PubMed.{0,260}(Embase|Web of Science|Scopus|CINAHL)", ""),
            problem="The search strategy may not capture relevant sources beyond peer-reviewed journals (e.g. registries, preprints, gray literature, or reports).",
            why_it_matters="Relevant evidence is often reported outside peer-reviewed articles — in registries, preprints, theses, or organizational/technical reports — and omitting these sources can bias a systematic review.",
            suggested_action="State whether gray literature, registries, preprints, and other relevant reports were searched; if not, justify this as a limitation.",
        ))

    if _has_any(lower, ["mortality", "relative risk", "odds ratio", "hazard ratio", "effect estimate"]) and not _has_any(lower, ["meta-analysis", "pooled", "i2", "heterogeneity statistic", "forest plot"]):
        findings.append(_finding(
            finding_type="systematic_review",
            severity="critical",
            section_reference="Results/Discussion",
            anchor_text=_snippet(text, r"(mortality|relative risk|odds ratio|hazard ratio).{0,300}(reduction|reduced|decreased|increase|association)", "quantitative effect synthesis"),
            problem="The manuscript interprets quantitative effect estimates (e.g. mortality or relative-risk changes) but does not provide a formal synthesis or a rigorous no-pooling justification.",
            why_it_matters="A reviewer will want extracted absolute/relative effects, confidence intervals, and heterogeneity reasoning before accepting quantitative impact or mortality claims.",
            suggested_action="Either perform a meta-analysis where defensible, or add a no-pooling justification with a forest plot or structured table of effect sizes, study design, adjustment, and risk of bias.",
        ))

    if _has_any(lower, ["risk of bias", "robins-i", "rob 2"]) and not _has_any(lower, ["grade", "certainty", "sensitivity analysis", "inter-rater", "kappa"]):
        findings.append(_finding(
            finding_type="systematic_review",
            severity="major",
            section_reference="Quality assessment/Discussion",
            anchor_text=_snippet(text, r"risk.of.bias|ROBINS-I|RoB 2", "risk-of-bias assessment"),
            problem="Risk of bias is assessed but not strongly integrated into certainty of conclusions.",
            why_it_matters="Risk-of-bias tables alone are not enough; reviewers expect biased studies to change the interpretation of clinical impact claims.",
            suggested_action="Add a structured certainty paragraph or table explaining how risk-of-bias ratings affect each main conclusion, especially mortality and adoption claims.",
        ))

    if _has_any(lower, ["rob 2", "cochrane rob 2"]) and _has_any(lower, ["before-after", "observational", "nonrandomized", "cohort", "case studies"]):
        findings.append(_finding(
            finding_type="systematic_review",
            severity="major",
            section_reference="Quality assessment",
            anchor_text=_snippet(text, r"RoB 2|ROBINS-I|risk.of.bias", "risk-of-bias tool selection"),
            problem="The risk-of-bias tool choice needs clearer matching to study design, especially where RoB 2 is mentioned alongside mostly observational or before-after evidence.",
            why_it_matters="RoB 2 is intended for randomized trials; nonrandomized and before-after studies require tools such as ROBINS-I or an explicit design-specific rationale.",
            suggested_action="Clarify exactly which studies were assessed with RoB 2 versus ROBINS-I, and justify any tool choice for nonrandomized or before-after designs.",
        ))

    # General definitional-heterogeneity check (domain-agnostic): the manuscript
    # reports multiple/varying definitions of its core construct but does not tie
    # that to comparability of synthesized metrics. Catches the case regardless of
    # the specific condition (sepsis, depression, "engagement", etc.).
    if re.search(
        r"\b(?:\d+|several|multiple|many|various|varying|differing|different|heterogeneous|inconsistent|competing)\b"
        r"[\w\s,/.-]{0,40}\bdefinitions?\b",
        lower,
    ) or _has_any(lower, ["definition heterogeneity", "definitional heterogeneity", "inconsistent definitions", "competing definitions"]):
        findings.append(_finding(
            finding_type="systematic_review",
            severity="critical",
            section_reference="Results/Discussion",
            anchor_text=_snippet(
                text,
                r"(?:\d+|several|multiple|various|varying|differing|different|heterogeneous|inconsistent|competing)[\w\s,/.-]{0,40}definitions?[\w\s,/.-]{0,80}",
                "definitional heterogeneity",
            ),
            problem="The draft notes heterogeneous definitions of its core construct but does not fully connect this to the comparability of reported metrics and outcome claims.",
            why_it_matters="Mixing different operational definitions can materially change case mix and performance metrics, undermining cross-study synthesis and any pooling.",
            suggested_action="Add a dedicated heterogeneity subsection explaining how the differing definitions affect comparability of results and whether they preclude pooling.",
        ))

    return findings


def _clinical_ai_findings(text: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    lower = text.lower()
    lower_flat = re.sub(r"\s+", " ", lower)

    if (
        _has_any(lower, ["systematic review", "implementation", "deployed", "real-world", "real world"])
        and _has_any(lower, ["clinical", "hospital", "ehr", "electronic health record", "algorithm", "machine learning"])
        and not _has_any(lower, ["conflict of interest", "funding source", "industry sponsor", "vendor", "commercial conflict", "developer evaluated"])
    ):
        findings.append(_finding(
            finding_type="clinical_ai",
            severity="major",
            section_reference="Methods/Quality Assessment",
            anchor_text=_snippet(text, r"included studies|implementation studies|deployed.{0,160}(algorithm|model|system)|machine learning.{0,160}(algorithm|model)", ""),
            problem="The review does not clearly extract funding sources, conflicts of interest, or commercial/vendor involvement for included clinical AI studies.",
            why_it_matters="Clinical AI implementation evidence is vulnerable to commercial and developer-evaluator bias, especially when EHR vendors or model developers evaluate their own systems.",
            suggested_action="Add funding, conflict-of-interest, and vendor/developer-involvement extraction fields, then discuss how these risks affect confidence in positive deployment findings.",
        ))

    if _has_any(lower, ["potential to reduce mortality", "reduced mortality", "mortality reduction"]) and _has_any(lower, ["observational", "before-after", "confounding", "nonrandomized"]):
        findings.append(_finding(
            finding_type="causal_inference",
            severity="critical",
            section_reference="Discussion/Conclusion",
            anchor_text=_snippet(text, r"potential to reduce mortality|reduced mortality|confounding bias", "mortality causal claim"),
            problem="The mortality benefit claim remains vulnerable to causal overstatement despite acknowledged observational confounding.",
            why_it_matters="Clinical reviewers will separate the algorithm's effect from concurrent care-process changes, awareness campaigns, staffing, and baseline patient differences.",
            suggested_action="Rewrite the conclusion around association and plausibility, and add a causal chain table separating algorithm performance, clinician adoption, process change, and patient outcomes.",
        ))

    if (
        _has_any(lower, ["external validation", "externally validated", "transportability", "model generalizability", "deployment controversy", "deployment controversies"])
        and _has_any(lower, ["clinical", "patient", "hospital", "ehr", "electronic health record", "prediction model", "machine learning"])
    ):
        findings.append(_finding(
            finding_type="literature_positioning",
            severity="major",
            section_reference="Related Work/Discussion",
            anchor_text=_snippet(text, r"external validation|externally validated|transportability|model generalizability|deployment controvers", "external validation and deployment controversy"),
            problem="The manuscript needs a sharper synthesis of external validation failures and deployment controversies around clinical prediction models.",
            why_it_matters="This is central context for clinical ML deployment and affects how readers interpret implementation success versus model transportability failures.",
            suggested_action="Add a paragraph contrasting positive deployment findings with external validation and transportability failures, then explain what this manuscript adds.",
        ))

    has_pipeline_context = _has_any(
        lower,
        ["data pipeline", "live data", "near-live data", "electronic health record", "ehr"],
    )
    has_operational_detail = _has_any(
        lower,
        ["hl7", "fhir", "cloud", "compute cost", "interface engine", "data latency"],
    )
    has_negated_operational_detail = _has_any(
        lower_flat,
        [
            "does not mention hl7",
            "does not mention fhir",
            "does not mention data latency",
            "does not mention cloud compute",
            "does not mention interface engine",
            "does not discuss hl7",
            "does not discuss fhir",
            "under-specifies",
        ],
    )
    if has_pipeline_context and (not has_operational_detail or has_negated_operational_detail):
        findings.append(_finding(
            finding_type="clinical_ai",
            severity="major",
            section_reference="Methods/Discussion",
            anchor_text=_snippet(text, r"live or near-live data|data pipeline|electronic health record|EHR", "live-data deployment description"),
            problem="The deployment discussion mentions live or near-live data but under-specifies the operational data-pipeline burden.",
            why_it_matters="Real-time EHR integration, HL7/FHIR interfaces, latency, monitoring, and compute ownership are often decisive implementation constraints for hospital AI.",
            suggested_action="Add a deployment-reality subsection covering EHR integration, data latency, interface standards, monitoring, staffing, and cost/ownership assumptions.",
        ))

    if (
        _has_any(lower, ["deployment", "implementation", "real-world", "real world", "clinical ai", "machine learning algorithm"])
        and not _has_any(lower, ["fairness", "algorithmic bias", "demographic", "subgroup", "equity", "racial", "sex-specific", "calibration by", "health disparities"])
    ):
        findings.append(_finding(
            finding_type="clinical_ai",
            severity="major",
            section_reference="Discussion/Limitations",
            anchor_text=_snippet(text, r"deployment|implementation|real-world|clinical AI|machine learning algorithm", "clinical AI deployment discussion"),
            problem="The deployment framework discussion does not sufficiently address algorithmic fairness, subgroup performance, or demographic bias.",
            why_it_matters="Fairness and subgroup calibration are central safety concerns for clinical AI deployment, especially when algorithms are moved across hospitals, populations, and EHR workflows.",
            suggested_action="Add a fairness and equity limitation covering subgroup performance, calibration drift, demographic representativeness, and governance responsibilities for monitoring bias after deployment.",
        ))

    if _has_any(lower, ["lead time", "alert to first antibiotic", "time to antibiotic", "antibiotic administration"]):
        findings.append(_finding(
            finding_type="clinical_ai",
            severity="major",
            section_reference="Results/Discussion",
            anchor_text=_snippet(text, r"lead time.{0,220}(antibiotic|alert|treatment)|alert.{0,180}antibiotic|time to antibiotic", ""),
            problem="The manuscript mentions alert lead time or time-to-antibiotic metrics without clearly judging clinical relevance.",
            why_it_matters="A statistically earlier alert may not be clinically meaningful if it moves antibiotic delivery by minutes rather than a practice-changing interval.",
            suggested_action="Report the actual alert-to-treatment lead times, distinguish minutes versus hours, and state what threshold would be clinically meaningful for sepsis care.",
        ))

    return findings


def _framework_findings(text: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    lower = text.lower()

    if "companion paper" in lower:
        findings.append(_finding(
            finding_type="framework_validation",
            severity="major",
            section_reference="Introduction/Background",
            anchor_text=_snippet(text, r"companion paper.{0,250}framework|framework.{0,250}companion paper|companion paper", "companion-paper dependency"),
            problem="The framework is reported in a companion paper, raising a salami-slicing and interpretability concern.",
            why_it_matters="Reviewers may not be able to judge whether this manuscript independently validates the framework or depends on unpublished/parallel framework derivation.",
            suggested_action="Explain the companion paper's status, what content is duplicated or excluded, and why framework derivation and validation are appropriately separated.",
        ))

    if re.search(r"validated (?:the|our|this|a|its)\s+[\w\s'-]{0,40}framework", lower) or _has_any(
        lower, ["necessary and sufficient", "ai-task agnostic", "ai task agnostic", "task-agnostic", "potential application to other", "apply to other", "generalizes to other"]
    ):
        findings.append(_finding(
            finding_type="framework_validation",
            severity="critical",
            section_reference="Discussion/Conclusion",
            anchor_text=_snippet(text, r"validated (?:the|our|this|a|its)\s+[\w\s'-]{0,40}framework|necessary and sufficient|task[- ]agnostic|application to other", "framework validation/generalizability claim"),
            problem="The manuscript overstates the framework's validation and generalizability from a single-domain mapping exercise.",
            why_it_matters="Mapping review findings onto a framework is not independent validation, and broad task-agnostic claims require cross-domain evidence or explicit qualification.",
            suggested_action="Reframe the framework claims as preliminary applicability evidence, compare directly with established frameworks (e.g. CFIR/NASSS/RE-AIM/Decide-AI), and define what future evidence would validate or falsify it.",
        ))

    if "framework" in lower and not _has_any(lower, ["cfir", "nasss", "re-aim", "re aim"]):
        findings.append(_finding(
            finding_type="literature_positioning",
            severity="major",
            section_reference="Background/Discussion",
            anchor_text=_snippet(text, r"implementation framework|[\w'-]+\s+framework|framework", "framework positioning"),
            problem="The framework contribution is not positioned tightly enough against established implementation science frameworks.",
            why_it_matters="Without a direct comparison, readers cannot tell whether the framework adds distinct explanatory power or repackages existing implementation constructs.",
            suggested_action="Add a comparison table against established frameworks (e.g. CFIR, NASSS, RE-AIM, Decide-AI, CONSORT-AI, TRIPOD-AI), naming what this framework uniquely adds.",
        ))

    return findings


def _materials_battery_findings(text: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    lower = text.lower()

    is_battery = _has_any(lower, ["sodium-ion", "sodium ion", "na-ion", "cathode", "layered oxide", "battery"])
    if not is_battery:
        return findings

    if (
        _has_any(lower, ["commercial viability", "commercially viable", "promising alternative", "low cost", "cost-effective"])
        and not _has_any(lower, ["wh/kg", "energy density", "cost per kwh", "cost-per-kwh", "precursor cost", "techno-economic"])
    ):
        findings.append(_finding(
            finding_type="materials_literature_positioning",
            severity="major",
            section_reference="Introduction/Discussion",
            anchor_text=_snippet(text, r"commercial.{0,120}viab|promising alternative|low[- ]cost|cost[- ]effective", "commercial viability claim"),
            problem="The draft claims commercial viability for sodium layered oxide cathodes without enough techno-economic or energy-density qualification.",
            why_it_matters="Battery reviewers will expect the cost advantage of sodium-ion chemistry to be weighed against lower practical energy-density ceilings and application-specific requirements.",
            suggested_action="Add a short comparison of practical Wh/kg and cost-per-kWh tradeoffs versus LFP and NMC, distinguishing grid-storage use cases from EV use cases.",
        ))

    mentions_o3_p2 = _has_any(lower, ["o3", "p2"])
    if mentions_o3_p2 and not _has_any(lower, ["o3-type", "p2-type", "deep desodiation", "phase transition severity"]):
        findings.append(_finding(
            finding_type="materials_degradation",
            severity="major",
            section_reference="Introduction/Framework",
            anchor_text=_snippet(text, r"\b(O3|P2)\b.{0,240}(phase|layered|degradation)|layered oxide.{0,240}\b(O3|P2)\b", "P2/O3 phase discussion"),
            problem="The degradation framing mentions layered oxide phase families but does not clearly separate P2 and O3 degradation pathways early enough.",
            why_it_matters="P2 and O3 sodium layered oxides differ in stacking, sodium coordination, phase-transition severity, and failure modes during deep desodiation.",
            suggested_action="Introduce an early organizing paragraph or table separating P2 and O3 cathodes, then map later degradation mechanisms back to that taxonomy.",
        ))

    if (
        _has_any(lower, ["surface decomposition", "surface degradation", "cei", "sei", "electrolyte"])
        and not _has_any(lower, ["fec", "fluoroethylene carbonate", "additive", "passivation", "interphase chemistry"])
    ):
        findings.append(_finding(
            finding_type="materials_degradation",
            severity="major",
            section_reference="Discussion",
            anchor_text=_snippet(text, r"surface.{0,140}(decomposition|degradation)|electrolyte.{0,180}(interface|decomposition)|\bCEI\b|\bSEI\b", "surface/electrolyte degradation discussion"),
            problem="The draft discusses surface decomposition but under-specifies electrolyte formulation and interphase effects.",
            why_it_matters="Electrolyte salts, solvents, and additives can materially change CEI/SEI composition, transition-metal dissolution, oxygen activity, and cycling stability.",
            suggested_action="Add a focused paragraph on electrolyte and additive effects, including whether FEC or other passivating additives alter the degradation mechanisms described.",
        ))

    if (
        _has_any(lower, ["xrd", "sem", "tem", "xps", "raman", "ex situ", "in situ", "operando"])
        and not _has_any(lower, ["operando", "in situ", "ex situ", "complementary characterization", "multi-modal"])
    ):
        findings.append(_finding(
            finding_type="materials_evidence",
            severity="minor",
            section_reference="Methods/Discussion",
            anchor_text=_snippet(text, r"\b(XRD|SEM|TEM|XPS|Raman)\b", "characterization evidence"),
            problem="The characterization discussion could more clearly distinguish structural, surface, and morphological evidence streams.",
            why_it_matters="Layered oxide degradation claims are stronger when phase evolution, surface chemistry, and particle morphology are tied to the appropriate characterization method.",
            suggested_action="Group evidence by method class and note which degradation mechanisms require operando/in situ support versus post-mortem characterization.",
        ))

    if (
        _has_any(lower, ["commercial viability", "commercially viable", "promising alternative", "low cost", "cost-effective"])
        and _has_any(lower, ["air sensitivity", "moisture sensitivity", "air-sensitive", "moisture-sensitive", "air sensitive", "moisture sensitive", "hygroscopic"])
        and not _has_any(lower, ["dry room", "dry-room", "slurry", "manufacturing cost", "environmental control", "industrial scalability"])
    ):
        findings.append(_finding(
            finding_type="materials_literature_positioning",
            severity="major",
            section_reference="Discussion/Commercialization",
            anchor_text=_snippet(text, r"air.{0,80}sensitiv|moisture.{0,80}sensitiv|hygroscopic|commercial.{0,120}viab|low[- ]cost", "air/moisture sensitivity and commercial claim"),
            problem="The draft mentions air or moisture sensitivity but does not connect it to manufacturing cost and industrial scalability.",
            why_it_matters="Strict dry-room handling, slurry-processing controls, and storage requirements can erode the cost advantage often claimed for sodium-ion layered oxides.",
            suggested_action="Add a commercialization paragraph explaining how moisture sensitivity affects electrode processing, dry-room needs, storage, and the net cost advantage versus lithium-ion cathodes.",
        ))

    if (
        _has_any(lower, ["low cost", "cost-effective", "cost advantage", "commercial viability", "promising alternative"])
        and _has_any(lower, ["nickel", "cobalt", "ni-rich", "co-rich", "high-ni", "high nickel", "high cobalt"])
        and not _has_any(lower, ["transition metal cost", "precursor cost", "nickel cost", "cobalt cost", "elemental abundance tradeoff"])
    ):
        findings.append(_finding(
            finding_type="materials_literature_positioning",
            severity="major",
            section_reference="Discussion/Commercialization",
            anchor_text=_snippet(text, r"nickel|cobalt|Ni[- ]rich|Co[- ]rich|low[- ]cost|cost advantage|commercial.{0,120}viab", "transition-metal cost claim"),
            problem="The draft's sodium-ion cost argument does not account for nickel and cobalt transition-metal cost drivers in layered oxide cathodes.",
            why_it_matters="Replacing lithium with sodium does not guarantee low cost if the cathode chemistry still depends on expensive or supply-constrained transition metals.",
            suggested_action="Qualify the cost claim by distinguishing Ni/Co-rich layered oxides from Mn/Fe-rich alternatives and discuss precursor-cost tradeoffs explicitly.",
        ))

    if (
        _has_any(lower, ["figure", "fig.", "fig "])
        and _has_any(lower, ["reproduced", "adapted", "modified from", "permission", "copyright"])
    ):
        findings.append(_finding(
            finding_type="clarity",
            severity="minor",
            section_reference="Figures/Captions",
            anchor_text=_snippet(text, r"(figure|fig\.).{0,200}(reproduced|adapted|modified from|permission|copyright)|(reproduced|adapted|modified from).{0,200}(figure|fig\.)", "figure permission/caption statement"),
            problem="Reproduced or adapted figures need explicit permission and attribution checks before submission.",
            why_it_matters="Battery review articles often rely on adapted schematics and micrographs; unclear permissions can cause journal production delays or legal review.",
            suggested_action="For each reproduced or adapted figure, verify permission requirements and add complete attribution in the caption using the target journal's wording.",
        ))

    return findings


def _public_health_psych_findings(text: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    lower = text.lower()
    has_funding_reporting = _has_any(lower, ["funding source", "conflict of interest", "industry sponsor", "platform funding", "commercial interest"])
    has_negated_funding_reporting = _has_any(
        lower,
        [
            "do not mention funding",
            "does not mention funding",
            "no funding source",
            "not report funding",
            "do not mention conflict",
            "does not mention conflict",
            "no conflict of interest extraction",
            "not report conflict",
        ],
    )

    if (
        _has_any(lower, ["social media", "facebook", "instagram", "twitter", "tiktok", "youtube", "snapchat"])
        and _has_any(lower, ["systematic review", "included studies", "risk of bias", "data extraction"])
        and (not has_funding_reporting or has_negated_funding_reporting)
    ):
        findings.append(_finding(
            finding_type="systematic_review",
            severity="major",
            section_reference="Methods/Quality Assessment",
            anchor_text=_snippet(text, r"social media.{0,220}(included studies|risk of bias|data extraction)|included studies.{0,220}social media", "social media evidence synthesis"),
            problem="The review does not clearly extract funding sources, conflicts of interest, or social-media platform involvement for included studies.",
            why_it_matters="Research on social media and mental health can be affected by platform sponsorship, data-access arrangements, or commercial conflicts that shape study design and interpretation.",
            suggested_action="Add funding, conflict-of-interest, and platform/data-access extraction fields for included studies, then discuss whether these risks affect confidence in the synthesized findings.",
        ))

    if (
        _has_any(lower, ["cross-sectional", "cross sectional", "association", "correlation"])
        and _has_any(lower, ["influence of social media", "impact of social media", "social media influence"])
    ):
        findings.append(_finding(
            finding_type="causal_inference",
            severity="major",
            section_reference="Title/Discussion",
            anchor_text=_snippet(text, r"(influence|impact).{0,80}social media|social media.{0,80}(influence|impact)", "social media causal language"),
            problem="Directional language about social media influence may overstate what mostly cross-sectional evidence can support.",
            why_it_matters="Behavioral-health reviewers will distinguish association, prediction, and causal influence, especially when exposure and outcomes are self-reported.",
            suggested_action="Align the title, abstract, and conclusion with the underlying study designs by using association-focused language unless longitudinal or experimental evidence supports causal wording.",
        ))

    if (
        _has_any(lower, ["facebook", "instagram", "twitter"])
        and not _has_any(lower, ["tiktok", "snapchat", "youtube"])
    ):
        findings.append(_finding(
            finding_type="systematic_review",
            severity="major",
            section_reference="Methods/Search Strategy",
            anchor_text=_snippet(text, r"Facebook|Instagram|Twitter|search strateg|Table 1", "platform search terms"),
            problem="The platform search terms may be too restrictive for adolescent social-media exposure.",
            why_it_matters="Missing platform-specific terms can bias a social-media review toward older platforms and under-represent adolescent use patterns.",
            suggested_action="Explain the platform-term strategy and consider adding or justifying omitted platform terms such as Snapchat, YouTube, and TikTok where date-appropriate.",
        ))

    return findings


def diagnostic_findings_node(state: DraftAnalysisState) -> DraftAnalysisState:
    profile = state.get("manuscript_profile") or {}
    text = state.get("draft_content") or ""
    lower = text.lower()
    findings: list[dict[str, Any]] = []

    lenses = set(profile.get("review_lenses") or [])
    domain_tags = set(profile.get("domain_tags") or [])

    if (
        (
            profile.get("genre") == "systematic_review"
            or "systematic_review_methods" in lenses
            or "systematic review" in lower
            or "prisma" in lower
        )
        and "materials_science" not in domain_tags
    ):
        findings.extend(_systematic_review_findings(text))
    if "clinical_ai" in domain_tags or "clinical_ai_deployment" in lenses:
        findings.extend(_clinical_ai_findings(text))
    if "behavioral_health" in lenses or "public_health" in domain_tags or "psychology" in domain_tags:
        findings.extend(_public_health_psych_findings(text))
    if "framework_validation" in lenses or "framework_mapping" in set(profile.get("contribution_types") or []):
        findings.extend(_framework_findings(text))
    if "materials_science" in domain_tags or "materials_degradation" in lenses:
        findings.extend(_materials_battery_findings(text))

    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for finding in findings:
        key = (finding["finding_type"], finding["problem"].lower())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(finding)

    logger.info("[DiagnosticFindings] Generated %s profile-aware findings", len(deduped))
    return {
        "diagnostic_findings": deduped,
        "current_step": "Diagnostic Findings",
        "progress_percentage": 78,
    }

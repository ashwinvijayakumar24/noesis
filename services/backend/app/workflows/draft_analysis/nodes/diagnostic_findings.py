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
            why_it_matters="Language restrictions can bias systematic reviews, especially for international clinical AI deployments that may be reported outside English-language venues.",
            suggested_action="Explicitly acknowledge the English-language search restriction in the Limitations section and discuss how it may affect completeness and generalizability.",
        ))

    if (
        _has_any(lower, ["systematic review", "implementation", "deployed", "real-world", "real world"])
        and _has_any(lower, ["clinical", "hospital", "ehr", "electronic health record", "algorithm"])
        and not _has_any(lower, ["gray literature", "grey literature", "white paper", "quality improvement report", "vendor report", "preprint"])
    ):
        findings.append(_finding(
            finding_type="systematic_review",
            severity="major",
            section_reference="Methods/Search Strategy",
            anchor_text=_snippet(text, r"database.{0,180}search|searched.{0,260}(PubMed|Embase|Scopus|Web of Science|CINAHL)|PubMed.{0,260}(Embase|Web of Science|Scopus|CINAHL)", ""),
            problem="The search strategy does not clearly include gray literature, registries, or implementation reports for real-world clinical AI deployments.",
            why_it_matters="Implemented clinical systems are often described in trial registries, hospital quality-improvement reports, technical white papers, or preprints rather than peer-reviewed articles alone.",
            suggested_action="State whether gray literature, registries, preprints, vendor reports, or hospital implementation reports were searched; if not, justify this as a limitation.",
        ))

    if (
        _has_any(lower, ["systematic review", "implementation", "deployed", "real-world", "real world"])
        and _has_any(lower, ["clinical", "hospital", "ehr", "electronic health record", "algorithm", "machine learning"])
        and not _has_any(lower, ["conflict of interest", "funding source", "industry sponsor", "vendor", "commercial conflict", "developer evaluated"])
    ):
        findings.append(_finding(
            finding_type="systematic_review",
            severity="major",
            section_reference="Methods/Quality Assessment",
            anchor_text=_snippet(text, r"included studies|implementation studies|deployed.{0,160}(algorithm|model|system)|machine learning.{0,160}(algorithm|model)", ""),
            problem="The review does not clearly extract funding sources, conflicts of interest, or commercial/vendor involvement for included clinical AI studies.",
            why_it_matters="Clinical AI implementation evidence is vulnerable to commercial and developer-evaluator bias, especially when EHR vendors or model developers evaluate their own systems.",
            suggested_action="Add funding, conflict-of-interest, and vendor/developer-involvement extraction fields, then discuss how these risks affect confidence in positive deployment findings.",
        ))

    if _has_any(lower, ["mortality", "effect size", "reduction"]) and not _has_any(lower, ["meta-analysis", "pooled", "i2", "heterogeneity statistic", "forest plot"]):
        findings.append(_finding(
            finding_type="systematic_review",
            severity="critical",
            section_reference="Results/Discussion",
            anchor_text=_snippet(text, r"mortality.{0,300}(reduction|reduced|decreased)|reduced.{0,200}mortality", "mortality outcome synthesis"),
            problem="The manuscript interprets mortality reductions but does not provide a formal quantitative synthesis or a rigorous no-pooling justification.",
            why_it_matters="A reviewer will want extracted absolute/relative effects, confidence intervals, and heterogeneity reasoning before accepting claims about mortality impact.",
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

    if _has_any(lower, ["different definitions of sepsis", "sepsis-1", "sepsis-3", "twenty-six different definitions", "26 different definitions"]):
        findings.append(_finding(
            finding_type="systematic_review",
            severity="critical",
            section_reference="Results/Discussion",
            anchor_text=_snippet(text, r"(26|twenty-six).{0,80}definitions of sepsis|Sepsis-1.{0,250}Sepsis-3", "sepsis definition heterogeneity"),
            problem="The draft notes heterogeneous sepsis definitions but does not fully connect this to comparability of AUROC, specificity, and mortality claims.",
            why_it_matters="Mixing Sepsis-1, severe sepsis, septic shock, and Sepsis-3 can materially change case mix and performance metrics, undermining cross-study synthesis.",
            suggested_action="Add a dedicated heterogeneity subsection explaining how sepsis definitions affect diagnostic/prognostic comparability and whether they preclude pooling.",
        ))

    return findings


def _clinical_ai_findings(text: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    lower = text.lower()
    lower_flat = re.sub(r"\s+", " ", lower)

    if _has_any(lower, ["potential to reduce mortality", "reduced mortality", "mortality reduction"]) and _has_any(lower, ["observational", "before-after", "confounding", "nonrandomized"]):
        findings.append(_finding(
            finding_type="causal_inference",
            severity="critical",
            section_reference="Discussion/Conclusion",
            anchor_text=_snippet(text, r"potential to reduce mortality|reduced mortality|confounding bias", "mortality causal claim"),
            problem="The mortality benefit claim remains vulnerable to causal overstatement despite acknowledged observational confounding.",
            why_it_matters="Clinical reviewers will separate algorithm effect from concurrent sepsis-awareness campaigns, care bundles, staffing, and baseline patient differences.",
            suggested_action="Rewrite the conclusion around association and plausibility, and add a causal chain table separating algorithm performance, clinician adoption, process change, and patient outcomes.",
        ))

    if _has_any(lower, ["epic", "wong", "external validation", "proprietary sepsis prediction model"]):
        findings.append(_finding(
            finding_type="literature_positioning",
            severity="major",
            section_reference="Related Work/Discussion",
            anchor_text=_snippet(text, r"Epic|Wong.{0,200}sepsis|external validation.{0,200}sepsis", "Epic Sepsis Model validation controversy"),
            problem="The manuscript needs a sharper synthesis of Epic Sepsis Model external validation failures and controversies around deployed sepsis prediction.",
            why_it_matters="This is central domain context for clinical ML deployment and affects how readers interpret implementation success versus model transportability failures.",
            suggested_action="Add a paragraph contrasting positive deployment studies with external validation failures such as the Epic Sepsis Model, explaining what this review adds.",
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
            anchor_text=_snippet(text, r"companion paper.{0,250}SALIENT|SALIENT.{0,250}companion paper", "SALIENT companion-paper dependency"),
            problem="The framework is reported in a companion paper, raising a salami-slicing and interpretability concern.",
            why_it_matters="Reviewers may not be able to judge whether this manuscript independently validates SALIENT or depends on unpublished/parallel framework derivation.",
            suggested_action="Explain the companion paper's status, what content is duplicated or excluded, and why framework derivation and validation are appropriately separated.",
        ))

    if _has_any(lower, ["validated the salient framework", "necessary and sufficient", "ai-task agnostic", "potential application to other"]):
        findings.append(_finding(
            finding_type="framework_validation",
            severity="critical",
            section_reference="Discussion/Conclusion",
            anchor_text=_snippet(text, r"validated the SALIENT|necessary and sufficient|AI-task agnostic|application to other", "SALIENT validation/generalizability claim"),
            problem="The manuscript overstates framework validation and generalizability from a single-domain mapping exercise.",
            why_it_matters="Mapping review findings onto a framework is not independent validation, and broad AI-task-agnostic claims require cross-domain evidence or explicit qualification.",
            suggested_action="Reframe SALIENT claims as preliminary applicability evidence, compare directly with CFIR/NASSS/RE-AIM/Decide-AI, and define what future evidence would validate or falsify the framework.",
        ))

    if "framework" in lower and not _has_any(lower, ["cfir", "nasss", "re-aim", "re aim"]):
        findings.append(_finding(
            finding_type="literature_positioning",
            severity="major",
            section_reference="Background/Discussion",
            anchor_text=_snippet(text, r"implementation framework|SALIENT framework", "implementation framework positioning"),
            problem="The framework contribution is not positioned tightly enough against established implementation science frameworks.",
            why_it_matters="Without a direct comparison, readers cannot tell whether SALIENT adds distinct explanatory power or repackages existing implementation constructs.",
            suggested_action="Add a comparison table against CFIR, NASSS, RE-AIM, Decide-AI, CONSORT-AI, and TRIPOD-AI, naming what SALIENT uniquely adds.",
        ))

    return findings


def diagnostic_findings_node(state: DraftAnalysisState) -> DraftAnalysisState:
    profile = state.get("manuscript_profile") or {}
    text = state.get("draft_content") or ""
    findings: list[dict[str, Any]] = []

    lenses = set(profile.get("review_lenses") or [])
    domain_tags = set(profile.get("domain_tags") or [])

    if profile.get("genre") == "systematic_review" or "systematic_review_methods" in lenses:
        findings.extend(_systematic_review_findings(text))
    if "clinical_ai" in domain_tags or "clinical_ai_deployment" in lenses:
        findings.extend(_clinical_ai_findings(text))
    if "framework_validation" in lenses or "framework_mapping" in set(profile.get("contribution_types") or []):
        findings.extend(_framework_findings(text))

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

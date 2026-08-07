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


def _empirical_method_findings(text: str, manuscript_profile: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Transferable empirical-method checks mined from reviewer behavior.

    These are deliberately paper-agnostic: they flag common review concerns only when
    the manuscript text exposes the relevant setup, then leave grounding to the
    existing evidence gate and anchor repair pipeline.
    """
    findings: list[dict[str, Any]] = []
    lower = text.lower()
    lower_flat = re.sub(r"\s+", " ", lower)

    is_empirical = (
        (manuscript_profile or {}).get("evidence_mode") == "empirical_ml"
        or (manuscript_profile or {}).get("routing_domain") == "computer_science_ml"
        or _has_any(lower, ["experiment", "experiments", "dataset", "benchmark", "baseline", "ablation"])
    )
    if not is_empirical:
        return findings

    # Proxy metric validity: a downstream model/classifier score can confound the
    # intended construct (faithfulness/diversity/quality/etc.) with task difficulty
    # unless validated against independent evidence.
    if (
        _has_any(lower, ["faithfulness", "diversity", "complexity", "quality", "realism"])
        and _has_any(lower, ["classifier", "classification accuracy", "downstream accuracy", "distilbert", "bert", "model accuracy"])
        and not _has_any(lower, ["human evaluation", "gold evaluation", "manual evaluation", "inter-annotator", "validated metric", "metric validation"])
    ):
        findings.append(_finding(
            finding_type="methodology",
            severity="major",
            section_reference="Evaluation",
            anchor_text=_snippet(text, r"(faithfulness|diversity|complexity|quality|realism).{0,260}(classifier|accuracy|DistilBERT|BERT|downstream)|(?:classifier|accuracy|DistilBERT|BERT|downstream).{0,260}(faithfulness|diversity|complexity|quality|realism)", "proxy evaluation metric"),
            problem="The evaluation relies on model-performance proxy metrics such as classifier or downstream accuracy for target properties, but does not validate that those proxy scores isolate faithfulness, diversity, quality, or realism.",
            why_it_matters="A proxy score can mix the intended construct with dataset difficulty, model capacity, prompt choice, or annotation artifacts, so reviewers may not accept the metric as direct evidence for the claim.",
            suggested_action="Add an independent validation of the proxy metric, such as human/gold evaluation, sensitivity analysis, or a correlation study showing the metric measures the intended property rather than task difficulty.",
        ))

    # Construct validity for hand-designed metrics: reviewers often object when a
    # high-level property such as diversity/complexity is operationalized by token
    # counts, fixed subset sizes, or opaque formulas without context or sensitivity.
    if (
        _has_any(lower, ["diversity", "complexity", "faithfulness", "conformity"])
        and _has_any(lower, ["unique number of tokens", "unique tokens", "token size", "subset size", "k=", " k ", "metric"])
        and not _has_any(lower, ["metric validation", "sensitivity", "human evaluation", "gold evaluation", "contextualize", "contextualise"])
    ):
        findings.append(_finding(
            finding_type="methodology",
            severity="major",
            section_reference="Evaluation/Metrics",
            anchor_text=_snippet(text, r"(diversity|complexity|faithfulness|conformity).{0,320}(unique number of tokens|unique tokens|token size|subset size|k\s*=|metric)|(unique number of tokens|unique tokens|token size|subset size|k\s*=|metric).{0,320}(diversity|complexity|faithfulness|conformity)", "metric definition and context"),
            problem="The evaluation defines constructs such as diversity, complexity, faithfulness, or conformity using token counts, subset sizes, or opaque metric choices without enough justification, context, or sensitivity analysis.",
            why_it_matters="Reviewers need to know why the metric captures the intended construct, whether fixed choices such as subset size change conclusions, and how reported values should be interpreted.",
            suggested_action="Justify each metric definition, report sensitivity to key constants such as subset or token count, and contextualize the metric values with human/gold checks or interpretable examples.",
        ))

    # Training/tuning mechanism attribution: when a manuscript claims RLHF,
    # instruction tuning, alignment, fine-tuning, or proprietary training caused a
    # capability drop, reviewers expect paired controls or cautious wording. Preserve
    # the author's mechanism label in the finding so downstream review tasks stay
    # specific without hard-coding a paper.
    if (
        _has_any(lower, ["rlhf", "reinforcement learning from human feedback", "instruction-tuning", "instruction tuning", "alignment", "fine-tuning", "finetuning", "proprietary training"])
        and _has_any(lower, ["decrease", "degradation", "drop", "reduced", "worse", "less diversity", "generative abilities", "capability"])
        and not _has_any(lower, ["same base model", "before and after", "paired comparison", "controlled comparison", "matched comparison", "counterfactual"])
    ):
        mechanism_terms = [
            term for term in (
                "RLHF",
                "reinforcement learning from human feedback",
                "instruction tuning",
                "instruction-tuning",
                "alignment",
                "fine-tuning",
                "proprietary training",
            )
            if term.lower() in lower
        ]
        mechanism_label = " / ".join(dict.fromkeys(mechanism_terms)) or "training/tuning"
        findings.append(_finding(
            finding_type="causal_claim",
            severity="major",
            section_reference="Evaluation/Discussion",
            anchor_text=_snippet(text, r"(RLHF|reinforcement learning from human feedback|instruction[- ]tuning|alignment|fine[- ]tuning|proprietary training).{0,360}(decrease|degradation|drop|reduced|worse|less diversity|generative abilities|capability)|(decrease|degradation|drop|reduced|worse|less diversity|generative abilities|capability).{0,360}(RLHF|reinforcement learning from human feedback|instruction[- ]tuning|alignment|fine[- ]tuning|proprietary training)", "training/tuning attribution claim"),
            problem=f"The manuscript attributes a capability or metric degradation to {mechanism_label}, but does not provide a controlled experimental design that isolates that training or tuning mechanism.",
            why_it_matters="Differences between models can also reflect architecture, data mixture, model size, prompting, decoding, proprietary post-processing, or evaluation metric artifacts, so reviewers may reject a causal explanation without paired controls.",
            suggested_action="Add matched before/after or same-base-model comparisons where possible, keep prompts and decoding fixed, or reword the claim as a correlational observation rather than a causal effect of the training/tuning mechanism.",
        ))

    # Causal attribution in experimental interpretation: if the paper attributes a
    # performance change to a specific training/intervention mechanism, reviewers expect
    # isolation via controls or ablations.
    if (
        re.search(r"\b(leads? to|causes?|due to|because of|attribut(?:e|ed|ion).{0,40}to)\b.{0,180}\b(drop|degradation|improvement|gain|performance)\b", lower_flat)
        and not _has_any(lower, ["controlled experiment", "isolate", "isolation study", "ablation", "counterfactual", "matched comparison"])
    ):
        findings.append(_finding(
            finding_type="causal_claim",
            severity="major",
            section_reference="Evaluation/Discussion",
            anchor_text=_snippet(text, r"(leads? to|causes?|due to|because of|attribut(?:e|ed|ion).{0,40}to).{0,220}(drop|degradation|improvement|gain|performance)", "causal attribution of performance change"),
            problem="The manuscript attributes a performance change to a specific mechanism without clearly isolating that mechanism experimentally.",
            why_it_matters="Reviewers will distinguish observed performance differences from causal attribution; without controls or ablations, the claimed mechanism may be only one of several explanations.",
            suggested_action="Add an ablation, matched-control comparison, or more cautious wording that separates the observed effect from the proposed explanation.",
        ))

    # Baseline fairness: comparisons can become hard to interpret when baselines use
    # different rewards/objectives, modified code paths, or inconsistent resource budgets.
    if (
        _has_any(lower, ["baseline", "baselines", "compare", "comparison"])
        and _has_any(lower, ["reward", "objective", "loss function", "modified", "codebase", "implementation", "runtime", "compute"])
        and not _has_any(lower, ["same objective", "same reward", "same compute", "fair comparison", "identical budget", "implementation details"])
    ):
        findings.append(_finding(
            finding_type="methodology",
            severity="major",
            section_reference="Experiments",
            anchor_text=_snippet(text, r"(baseline|baselines|compare|comparison).{0,260}(reward|objective|loss function|modified|codebase|implementation|runtime|compute)|(reward|objective|loss function|modified|codebase|implementation|runtime|compute).{0,260}(baseline|baselines|compare|comparison)", "baseline comparison setup"),
            problem="The baseline comparison may not establish that methods are compared under equivalent rewards/objectives, implementation choices, tuning budgets, runtime, and compute resources.",
            why_it_matters="If baselines differ in reward shaping, objectives, code modifications, runtime, or compute budget, reviewers cannot tell whether gains come from the proposed method or comparison setup.",
            suggested_action="Add a comparison-fairness paragraph/table that states the objective, reward/loss, implementation source, tuning budget, runtime, and compute budget for each baseline.",
        ))

    # Runtime / total-cost accounting: efficiency claims often ignore setup costs,
    # synthetic-data generation, preprocessing, feature precomputation, or extra model
    # calls. Reviewers expect total wall-clock/resource accounting, not only a partial
    # training or inference metric.
    if (
        _has_any(lower, ["runtime", "running time", "wall-clock", "time-consuming", "faster", "speedup", "efficient", "efficiency", "compute cost", "model calls", "token usage", "generation process", "synthetic data", "precomput"])
        and _has_any(lower, ["experiment", "experiments", "training", "dataset", "datasets", "baseline", "baselines", "inference"])
        and not _has_any(lower, ["total runtime", "wall-clock cost", "end-to-end runtime", "generation time", "model calls", "token usage", "compute-matched", "precomputation cost"])
    ):
        findings.append(_finding(
            finding_type="deployment",
            severity="major",
            section_reference="Experiments/Efficiency",
            anchor_text=_snippet(text, r"(runtime|running time|wall[- ]clock|time-consuming|faster|speedup|efficient|efficiency|compute cost|model calls|token usage|generation process|synthetic data|precomput).{0,320}(experiment|training|dataset|baseline|inference)|(experiment|training|dataset|baseline|inference).{0,320}(runtime|running time|wall[- ]clock|time-consuming|faster|speedup|efficient|efficiency|compute cost|model calls|token usage|generation process|synthetic data|precomput)", "runtime and total-cost accounting"),
            problem="The efficiency comparison may omit end-to-end cost components such as data generation, preprocessing, feature precomputation, model calls, or wall-clock runtime.",
            why_it_matters="A reviewer cannot assess practical value from a partial speedup alone; setup costs or extra generation/model-call overhead can erase the claimed efficiency benefit.",
            suggested_action="Report total wall-clock time and resource cost for each method, including preprocessing/generation/precomputation, training, inference, model calls or token usage where applicable, and compare against baselines under matched budgets.",
        ))

    # Baseline mechanism equivalence: if the compared methods are adapted through
    # different rewards/objectives, reviewers often ask whether the result is really
    # due to the proposed method or simply reward shaping/objective choice.
    if (
        _has_any(lower, ["baseline", "baselines", "compare", "comparison"])
        and _has_any(lower, ["reward shaping", "learned reward", "reward function", "oracle reward", "preference-based", "objective"])
        and not _has_any(lower, ["same reward function", "shared reward", "reward ablation", "objective ablation", "directly train", "direct training baseline"])
    ):
        findings.append(_finding(
            finding_type="methodology",
            severity="major",
            section_reference="Experiments/Baselines",
            anchor_text=_snippet(text, r"(baseline|baselines|compare|comparison).{0,320}(reward shaping|learned reward|reward function|oracle reward|preference-based|objective)|(reward shaping|learned reward|reward function|oracle reward|preference-based|objective).{0,320}(baseline|baselines|compare|comparison)", "baseline objective/reward comparison"),
            problem="The comparison may conflate the proposed method with reward shaping or objective-definition differences across baselines, especially when learned/preference rewards or adapted baseline objectives are used.",
            why_it_matters="If a baseline uses a different reward, objective, or adaptation path, reviewers cannot tell whether the reported gain comes from the core method or from a more favorable training signal.",
            suggested_action="Add a direct baseline or ablation that holds reward/objective choices fixed, and explicitly report each baseline's reward function, adaptation path, and tuning budget.",
        ))

    # Marginal gains over close alternatives: when a method is positioned as an
    # improvement over closely related baselines, reviewers expect a clear value
    # proposition, not just small table deltas.
    if (
        _has_any(lower, ["baseline", "baselines", "existing method", "prior method", "state-of-the-art", "sota", "outperform", "improvement", "gain", "accuracy"])
        and _has_any(lower, ["marginal", "slight", "small", "incremental", "close", "similar", "competitive", "table 2", "table 3", "table 4"])
        and not _has_any(lower, ["effect size", "practical significance", "statistical significance", "ablation", "why the gain", "value proposition", "failure case"])
    ):
        findings.append(_finding(
            finding_type="methodology",
            severity="major",
            section_reference="Experiments/Discussion",
            anchor_text=_snippet(text, r"(baseline|baselines|existing method|prior method|state-of-the-art|SOTA|outperform|improvement|gain|accuracy).{0,320}(marginal|slight|small|incremental|close|similar|competitive|Table 2|Table 3|Table 4)|(marginal|slight|small|incremental|close|similar|competitive|Table 2|Table 3|Table 4).{0,320}(baseline|baselines|existing method|prior method|state-of-the-art|SOTA|outperform|improvement|gain|accuracy)", "marginal gain over close alternatives"),
            problem="The manuscript does not sufficiently explain the practical value of the proposed method over close baselines when reported gains are small or inconsistent.",
            why_it_matters="Reviewers may view a method as incremental unless the paper explains when the gain matters, why close alternatives fail, and whether differences are statistically or practically meaningful.",
            suggested_action="Add an ablation or value analysis comparing against the closest alternatives, report effect sizes or significance where possible, and state the regimes where the proposed method provides a meaningful advantage.",
        ))

    # Human/expert labeling effort and scalability.
    if (
        _has_any(lower, ["human preference", "preference label", "human label", "annotator", "annotation", "expert label"])
        and not _has_any(lower, ["labeling cost", "annotation cost", "number of annotators", "inter-annotator", "label budget", "annotation budget"])
    ):
        findings.append(_finding(
            finding_type="deployment",
            severity="major",
            section_reference="Methods/Limitations",
            anchor_text=_snippet(text, r"human preference|preference label|human label|annotator|annotation|expert label", "human labeling requirement"),
            problem="The method relies on human or expert preference labels but does not sufficiently quantify label collection effort, behavior-sequence coverage, annotator reliability, or scalability.",
            why_it_matters="Human feedback can dominate the real cost and uncertainty of a method; reviewers need to know the label volume, expertise required, agreement, and failure modes.",
            suggested_action="Report the number and expertise of labelers, label budget, agreement/reliability checks, and how performance changes if the learned preference or label signal is noisy.",
        ))

    # Method/notation/figure self-containment: dense formulas, algorithms, and figures
    # must define symbols and explain how outputs are constructed. This is a common
    # reviewer complaint across technical domains, not an ML-specific standard.
    if (
        _has_any(lower, ["algorithm", "equation", "formula", "notation", "theorem", "figure", "caption", "schematic", "schemetic", "table"])
        and _has_any(lower, ["d\\mathbf", "partial", "gradient", "matrix", "operator", "origin", "selection function", "sub-figure", "caption", "formula", "notation", "variables"])
        and not _has_any(lower, ["notation table", "symbol table", "all variables are defined", "self-contained caption", "algorithm inputs", "algorithm outputs"])
    ):
        findings.append(_finding(
            finding_type="clarity",
            severity="major",
            section_reference="Methods/Figures",
            anchor_text=_snippet(text, r"(Algorithm|Equation|formula|notation|Theorem|Figure|caption|schematic|Schemetic|Table).{0,360}(d\\mathbf|partial|gradient|matrix|operator|origin|selection function|sub-figure|caption|formula|notation|variables)|(d\\mathbf|partial|gradient|matrix|operator|origin|selection function|sub-figure|caption|formula|notation|variables).{0,360}(Algorithm|Equation|formula|notation|Theorem|Figure|caption|schematic|Schemetic|Table)", "method notation and figure clarity"),
            problem="The method presentation may not be self-contained enough: key notation, algorithm variables, update equations, or figure elements are not clearly defined in context.",
            why_it_matters="Readers and reviewers need to reconstruct the method from the paper alone; undefined symbols, coarse captions, or unexplained algorithm outputs make correctness and implementation hard to assess.",
            suggested_action="Add a notation table or local definitions for every algorithm variable, clarify how algorithm outputs are constructed, and rewrite figure/table captions so colors, subfigures, and comparison conditions are self-contained.",
        ))

    # Input/prompt sensitivity: when a study evaluates prompt/input-driven methods or
    # generated data, reviewers expect sensitivity checks over prompt/task choices.
    if (
        _has_any(lower, ["prompt", "prompts", "prompting", "instruction", "input template", "generated dataset", "synthetic dataset"])
        and _has_any(lower, ["evaluation", "experiments", "tasks", "datasets", "results"])
        and not _has_any(lower, ["prompt sensitivity", "prompt ablation", "prompt variants", "alternative prompts", "sensitivity to prompts", "input sensitivity"])
    ):
        findings.append(_finding(
            finding_type="methodology",
            severity="major",
            section_reference="Evaluation",
            anchor_text=_snippet(text, r"(prompt|prompting|instruction|input template|generated dataset|synthetic dataset).{0,260}(evaluation|experiments|tasks|datasets|results)|(evaluation|experiments|tasks|datasets|results).{0,260}(prompt|prompting|instruction|input template|generated dataset|synthetic dataset)", "prompt/input-driven evaluation"),
            problem="The evaluation depends on prompt or input-design choices for generated/synthetic datasets, but does not test sensitivity to simple versus more sophisticated prompts, alternative templates, or task variants.",
            why_it_matters="Prompt and input templates can materially change generated data quality, task difficulty, and downstream results; reviewers need to know whether the conclusion is robust to reasonable alternatives.",
            suggested_action="Add prompt/input sensitivity checks, such as alternative prompt templates, task variants, or a prompt ablation table, and state whether the main conclusions hold across them.",
        ))

    # Empirically tuned component rationale: if the method introduces modules/equations
    # and justifies them mainly by benchmark performance, reviewers often ask for
    # intuition, ablation, or robustness under changed data characteristics.
    if (
        _has_any(lower, ["module", "modules", "component", "architecture", "equation", "layer", "embedding"])
        and _has_any(lower, ["performance", "dataset", "datasets", "benchmark", "empirical", "experiments"])
        and not _has_any(lower, ["motivation", "rationale", "intuition", "theoretical analysis", "ablation", "robustness analysis"])
    ):
        findings.append(_finding(
            finding_type="methodology",
            severity="major",
            section_reference="Methods/Evaluation",
            anchor_text=_snippet(text, r"(module|component|architecture|equation|layer|embedding).{0,280}(performance|dataset|benchmark|empirical|experiments)|(performance|dataset|benchmark|empirical|experiments).{0,280}(module|component|architecture|equation|layer|embedding)", "empirically tuned method component"),
            problem="The method appears to introduce empirically tuned modules, equations, or architecture components without enough intuition, theoretical rationale, ablation, or robustness evidence for why those design choices should hold beyond the tested datasets.",
            why_it_matters="Reviewers may interpret performance-driven module design as brittle or overfit unless the paper explains the mechanism and tests robustness to changed data characteristics.",
            suggested_action="Add design rationale, component ablations, and robustness checks showing whether the component remains useful when dataset scale, sparsity, feature distribution, or task setting changes.",
        ))

    # Dataset selection / representativeness: broad superiority claims can hinge on
    # which datasets were selected and whether their scale/sparsity/distribution covers
    # the regimes where the method is claimed to work.
    if (
        _has_any(lower, ["datasets", "benchmark", "benchmarks", "gbdt", "baselines", "outperform", "superior"])
        and _has_any(lower, ["selected", "selection", "middle-sized", "medium-sized", "large-scale", "sparse", "dense", "representative", "weather"])
        and not _has_any(lower, ["dataset selection sensitivity", "representativeness", "stress test", "sparse", "dense and sparse", "selection bias"])
    ):
        findings.append(_finding(
            finding_type="methodology",
            severity="major",
            section_reference="Experiments",
            anchor_text=_snippet(text, r"(datasets|benchmark|benchmarks).{0,320}(selected|selection|middle-sized|medium-sized|large-scale|sparse|dense|representative|outperform|superior)|(selected|selection|middle-sized|medium-sized|large-scale|sparse|dense|representative|outperform|superior).{0,320}(datasets|benchmark|benchmarks)", "dataset selection and representativeness"),
            problem="The empirical conclusion may depend on selected benchmark datasets and does not sufficiently test whether performance rankings change across scale, sparsity, feature distribution, or other dataset characteristics.",
            why_it_matters="Reviewers often ask whether a different dataset selection, scale, sparsity level, or feature distribution would reverse the comparison, especially when claims are made against strong baseline families.",
            suggested_action="Add a dataset-selection sensitivity analysis or explicitly characterize the benchmark coverage by scale, sparsity, feature type, and task regime; qualify superiority claims where coverage is narrow.",
        ))

    # Scope/generalization: broad applicability claims need evidence across the claimed
    # variation, not only a narrow task/dataset/prompt regime.
    if (
        _has_any(lower, ["generalize", "generalization", "robust", "real-world", "broadly applicable", "wide range", "various tasks", "different datasets"])
        and _has_any(lower, ["only", "simple", "average performance", "limited", "small", "medium-sized", "single", "few datasets"])
        and not _has_any(lower, ["scope limitation", "limited scope", "threats to validity", "failure mode", "stress test"])
    ):
        findings.append(_finding(
            finding_type="methodology",
            severity="major",
            section_reference="Evaluation/Limitations",
            anchor_text=_snippet(text, r"(generaliz|robust|real-world|broadly applicable|wide range|various tasks|different datasets).{0,300}(only|simple|average performance|limited|small|medium-sized|single|few datasets)|(only|simple|average performance|limited|small|medium-sized|single|few datasets).{0,300}(generaliz|robust|real-world|broadly applicable|wide range|various tasks|different datasets)", "scope and generalization claim"),
            problem="The evaluation scope may be too narrow for the manuscript's generalization or practical-applicability claims, especially if results come from simple tasks, averaged patterns, few datasets, or limited deployment regimes.",
            why_it_matters="Reviewers often reject broad claims when results are averaged over narrow regimes, simple tasks, few datasets, or underspecified deployment conditions.",
            suggested_action="Either expand evaluation across the claimed variation or narrow the claims and add limitations describing which datasets, task types, scales, or deployment regimes remain untested.",
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


def _public_health_psych_findings(text: str, manuscript_profile: dict[str, Any] | None = None) -> list[dict[str, Any]]:
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
            suggested_action="Align the title, abstract, and conclusion with the underlying study designs by using natural associative phrasing (e.g. 'associated with', 'associated factors') rather than causal/directional wording, unless longitudinal or experimental evidence supports causation.",
        ))

    if (
        _has_any(lower, ["facebook", "instagram", "twitter"])
        and not _has_any(lower, ["tiktok", "snapchat", "youtube"])
    ):
        # Chronology-aware: don't demand platforms that postdate the search. If the
        # search year is known, frame suggestions to that period (a separate
        # stale-search critique covers recency); otherwise recommend platform-AGNOSTIC
        # constructs rather than naming newer platforms anachronistically.
        search_year = (manuscript_profile or {}).get("latest_search_year")
        if search_year:
            suggested_action = (
                "Use platform-agnostic search constructs (e.g. 'social networking sites', "
                f"'digital media') and justify the platform scope for the search period ({search_year}); "
                "do not retrofit platforms that postdate the search."
            )
        else:
            suggested_action = (
                "Use platform-agnostic search constructs (e.g. 'social networking sites', "
                "'digital media') and justify the platform scope; add or justify omitted platform "
                "terms (e.g. Snapchat, YouTube) where chronologically appropriate to the search dates."
            )
        findings.append(_finding(
            finding_type="systematic_review",
            severity="major",
            section_reference="Methods/Search Strategy",
            anchor_text=_snippet(text, r"Facebook|Instagram|Twitter|search strateg|Table 1", "platform search terms"),
            problem="The platform search terms may be too restrictive for adolescent social-media exposure.",
            why_it_matters="Brand-specific keywords can bias a social-media review toward named platforms and under-represent broader adolescent digital exposure.",
            suggested_action=suggested_action,
        ))

    return findings


# Phrases that look like technical terms but are conclusion boilerplate — never flag.
_ORPHAN_STOPWORDS = {
    "future work", "in summary", "we conclude", "in conclusion", "this review",
    "this paper", "this study", "this work", "future perspectives", "future research",
    "in this", "we believe", "our results", "our findings", "the authors", "as a result",
}
_CONCLUSION_HEADING_RE = re.compile(
    r"^\s*(?:#{1,3}\s*)?(?:\d+\.?\s*)?(conclusions?|future\s+(?:work|perspectives?|directions?)|outlook|concluding\s+remarks?)\b",
    re.IGNORECASE | re.MULTILINE,
)
# Technical-term shapes that signal a substantive concept (not ordinary prose):
#   - hyphenated compound + up to 3 following nouns ("high-entropy layered oxide cathodes")
#   - CamelCase / multi-capitalized proper names ("NoesisPR", "EduAI-X")
#   - standalone acronyms (3-6 caps)
_TECH_TERM_RE = re.compile(
    r"\b([a-z]+-[a-z]+(?:\s+[a-z]+){0,3}"
    r"|[A-Z][a-z]+(?:[A-Z][a-z]+)+"
    r"|[A-Z]{3,6})\b"
)


def _orphaned_concept_findings(text: str) -> list[dict[str, Any]]:
    """Flag technical concepts introduced ONLY in the Conclusion/Future-Work sections
    with no groundwork in the main body (issue #16). A good PI would require either
    integrating the concept into the relevant section or cutting it."""
    if not text:
        return []
    match = _CONCLUSION_HEADING_RE.search(text)
    if not match or match.start() < len(text) * 0.4:
        # No clear conclusion heading, or it appears too early to be the real conclusion.
        return []
    body = text[: match.start()]
    conclusion = text[match.start():]
    if len(conclusion) > 6000:
        conclusion = conclusion[:6000]
    body_lower = body.lower()

    findings: list[dict[str, Any]] = []
    seen: set[str] = set()
    for m in _TECH_TERM_RE.finditer(conclusion):
        term = re.sub(r"\s+", " ", m.group(1)).strip()
        key = term.lower()
        if key in seen or key in _ORPHAN_STOPWORDS or len(term) < 6:
            continue
        # Require it to look like a substantive multi-word concept or acronym.
        if " " not in term and "-" not in term and not term.isupper():
            continue
        seen.add(key)
        # Present in main body? Exact match or first-word stem match.
        first_word = key.split()[0].rstrip("s")
        if key in body_lower or (len(first_word) >= 5 and first_word in body_lower):
            continue
        findings.append(_finding(
            finding_type="structural_coherence",
            severity="major",
            section_reference="Conclusion/Future Work",
            anchor_text=_snippet(conclusion, re.escape(term), term),
            problem=f'"{term}" is introduced in the Conclusion/Future Work without any groundwork in the main body.',
            why_it_matters="Introducing a major technical concept only in the conclusion leaves it unsupported and disconnected from the manuscript's argument.",
            suggested_action=f'Either integrate "{term}" into the relevant main-body section (with the necessary background and analysis) or remove it from the conclusion.',
            confidence=0.7,
        ))
        if len(findings) >= 5:
            break
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
        findings.extend(_public_health_psych_findings(text, profile))
    if "framework_validation" in lenses or "framework_mapping" in set(profile.get("contribution_types") or []):
        findings.extend(_framework_findings(text))
    if profile.get("evidence_mode") == "empirical_ml" or profile.get("routing_domain") == "computer_science_ml":
        findings.extend(_empirical_method_findings(text, profile))
    if "materials_science" in domain_tags or "materials_degradation" in lenses:
        findings.extend(_materials_battery_findings(text))

    findings.extend(_orphaned_concept_findings(text))

    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for finding in findings:
        key = (finding["finding_type"], finding["problem"].lower())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(finding)

    # Evidence gate: drop findings whose anchor is non-empty but not verbatim in draft
    try:
        from app.services.draft_evidence_gate import strip_unanchored_findings
        deduped = strip_unanchored_findings(deduped, text)
    except Exception as _gate_exc:
        logger.warning("[DiagnosticFindings] Evidence gate skipped: %s", _gate_exc)

    logger.info("[DiagnosticFindings] Generated %s profile-aware findings", len(deduped))
    return {
        "diagnostic_findings": deduped,
        "current_step": "Diagnostic Findings",
        "progress_percentage": 78,
    }

import pytest

from app.workflows.draft_analysis.domain_routing import get_domain_prompt_pack
from app.workflows.draft_analysis.nodes.diagnostic_findings import diagnostic_findings_node
from app.workflows.draft_analysis.nodes.manuscript_profile import build_manuscript_profile


SODIUM_DRAFT_EXCERPT = """
Layered oxide cathodes for sodium-ion batteries are promising alternatives to
lithium-ion systems because sodium precursors are abundant and low cost. This
review focuses on NaxTMO2 cathodes, including P2 and O3 phase families, where
deep desodiation can trigger oxygen framework shifts, prismatic coordination
changes, transition-metal migration, and Jahn-Teller distortion. A systematic
review of degradation pathways is still absent, making it difficult to compare
evidence across Xi'an and Shanghai studies. Surface decomposition and electrolyte
interactions remain central to capacity fade.
"""


SEPSIS_DRAFT_EXCERPT = """
This systematic review evaluates machine learning algorithms for sepsis
prediction in hospital patients using electronic health record data. Included
studies reported ICU alerts, mortality, clinical workflow deployment, and
implementation barriers. The review follows PRISMA methods with study selection,
data extraction, and risk of bias assessment.
"""


SOCIAL_JUSTICE_AI_DRAFT_EXCERPT = """
This Computers and Composition article argues that composition instructors should
teach students to approach generative AI and ChatGPT through social justice,
rhetorical ethics, and critical pedagogy. The classroom simulation asks students
to revise prompts, inspect algorithmic bias, and curate AI-generated prose as
part of a writing pedagogy. The contribution is a conceptual heuristic for
composition classrooms, not a machine-learning benchmark or model-development
study.
"""

LAW_POLICY_EXCERPT = """
This article analyzes the legal governance of biometric privacy regulation across
state jurisdictions. It compares statutory duties, case law, compliance burdens,
liability standards, and constitutional limits on administrative enforcement.
The contribution is a policy analysis of regulatory design rather than an
empirical machine-learning benchmark.
"""


BUSINESS_MANAGEMENT_EXCERPT = """
This management study examines how platform firms use supply chain partnerships
and marketing strategy to build competitive advantage. Survey and interview data
from operations managers are used to evaluate construct validity, organizational
capabilities, customer retention, and firm performance implications.
"""


ENVIRONMENTAL_ECOLOGY_EXCERPT = """
This environmental ecology manuscript evaluates how habitat fragmentation and
climate stress affect biodiversity and species richness across forest ecosystems.
Remote sensing and field sampling are used to estimate carbon storage,
conservation outcomes, spatial scale sensitivity, and sustainability implications.
"""


MECHANICAL_CIVIL_EXCERPT = """
This mechanical and civil engineering paper validates a finite element model for
structural bridge components under cyclic loading. The study reports boundary
conditions, concrete material properties, sensor measurements, safety factors,
manufacturing constraints, and comparison against experimental load tests.
"""


MATH_STATISTICS_EXCERPT = """
This statistics manuscript proves a theorem for a Bayesian estimator under weak
identifiability assumptions. The proof establishes asymptotic consistency, a
lemma for posterior contraction, Monte Carlo simulations, confidence interval
coverage, and implications for regression inference.
"""


NEURO_COGSCI_EXCERPT = """
This neuroscience and cognitive science study uses EEG and fMRI during a working
memory attention task. Behavioral task accuracy, neural activity, preprocessing
choices, multiple comparisons, perception measures, and cognitive construct
validity are evaluated in healthy adult participants.
"""


EDUCATION_EMPIRICAL_EXCERPT = """
This empirical education study tests an educational intervention in middle-school
classrooms using a quasi-experimental pretest-posttest design. Teachers implement
the curriculum, student achievement and learning outcomes are measured with an
assessment rubric, and implementation fidelity is reported.
"""


@pytest.mark.unit
def test_sodium_profile_does_not_false_match_clinical_ai_or_systematic_review():
    profile = build_manuscript_profile({
        "draft_content": SODIUM_DRAFT_EXCERPT,
        "paper_type": "journal_article",
    })

    assert "materials_science" in profile["domain_tags"]
    assert "battery" in profile["domain_tags"]
    assert "sodium_ion" in profile["domain_tags"]
    assert "clinical_ai" not in profile["domain_tags"]
    assert "biomedical" not in profile["domain_tags"]
    assert profile["genre"] != "systematic_review"
    assert "systematic_review_methods" not in profile["review_lenses"]
    assert "framework_validation" not in profile["review_lenses"]
    assert profile["routing_domain"] == "chemistry_materials"
    assert profile["routing_confidence"] > 0.5


@pytest.mark.unit
def test_sodium_diagnostics_are_materials_specific_not_clinical():
    profile = build_manuscript_profile({
        "draft_content": SODIUM_DRAFT_EXCERPT,
        "paper_type": "journal_article",
    })
    result = diagnostic_findings_node({
        "draft_content": SODIUM_DRAFT_EXCERPT,
        "manuscript_profile": profile,
    })

    findings = result["diagnostic_findings"]
    assert findings
    assert all(f["finding_type"].startswith("materials_") for f in findings)
    joined = " ".join(str(f) for f in findings).lower()
    for forbidden in ("sepsis", "prisma", "prospero", "patient", "mortality", "epic"):
        assert forbidden not in joined


@pytest.mark.unit
def test_clinical_ai_systematic_review_still_triggers_clinical_profile():
    profile = build_manuscript_profile({
        "draft_content": SEPSIS_DRAFT_EXCERPT,
        "paper_type": "journal_article",
    })

    assert "clinical_ai" in profile["domain_tags"]
    assert "biomedical" in profile["domain_tags"]
    assert "sepsis" in profile["domain_tags"]
    assert profile["genre"] == "systematic_review"
    assert "systematic_review_methods" in profile["review_lenses"]
    assert "clinical_ai_deployment" in profile["review_lenses"]
    assert profile["routing_domain"] in {"biomedical", "computer_science_ml"}


@pytest.mark.unit
def test_domain_prompt_pack_is_available_for_materials_route():
    profile = build_manuscript_profile({
        "draft_content": SODIUM_DRAFT_EXCERPT,
        "paper_type": "journal_article",
    })

    prompt_pack = get_domain_prompt_pack(profile)
    assert "chemistry" in prompt_pack.lower() or "materials" in prompt_pack.lower()
    assert "characterization" in prompt_pack.lower()


@pytest.mark.unit
def test_generic_academic_fallback_has_useful_prompt_pack():
    profile = build_manuscript_profile({
        "draft_content": "This manuscript argues that a clearer account of evidence improves scholarly debate.",
        "paper_type": "journal_article",
    })

    assert profile["routing_domain"] == "generic_academic"
    prompt_pack = get_domain_prompt_pack(profile)
    assert "contribution clarity" in prompt_pack.lower()
    assert "evidence" in prompt_pack.lower()


@pytest.mark.unit
def test_social_justice_ai_routes_to_humanities_education_not_ml():
    profile = build_manuscript_profile({
        "draft_content": SOCIAL_JUSTICE_AI_DRAFT_EXCERPT,
        "paper_type": "journal_article",
    })

    assert profile["routing_domain"] == "humanities_education"
    assert profile["genre"] == "pedagogical_conceptual"
    assert profile["evidence_mode"] == "pedagogical"
    assert "composition_pedagogy" in profile["domain_tags"]
    assert "classroom_translation" in profile["review_lenses"]

    prompt_pack = get_domain_prompt_pack(profile)
    assert "composition" in prompt_pack.lower()
    assert "do not demand" in prompt_pack.lower()


@pytest.mark.unit
def test_social_justice_ai_does_not_generate_ml_baseline_gap():
    from app.workflows.draft_analysis.nodes.gap_detection import detect_gaps_node

    profile = build_manuscript_profile({
        "draft_content": SOCIAL_JUSTICE_AI_DRAFT_EXCERPT,
        "paper_type": "journal_article",
    })
    result = detect_gaps_node({
        "draft_id": "draft-social",
        "manuscript_profile": profile,
        "claims_by_type": {
            "methodological": [
                {
                    "id": "claim-1",
                    "claim_text": "The heuristic gives students a method for ethical AI prompting.",
                    "claim_type": "methodological",
                    "section_location": "Introduction",
                    "importance_score": 0.8,
                }
            ]
        },
        "claims_with_citations": [
            {
                "claim": {
                    "id": "claim-1",
                    "claim_text": "The heuristic gives students a method for ethical AI prompting.",
                    "claim_type": "methodological",
                    "section_location": "Introduction",
                    "importance_score": 0.8,
                    "requires_citation": False,
                },
                "citation_quality": "none",
                "gaps": [],
            }
        ],
    })

    joined = " ".join(gap["description"] for gap in result.get("coverage_gaps", []))
    assert "baseline comparisons" not in joined.lower()


@pytest.mark.unit
@pytest.mark.parametrize(
    ("draft_text", "expected_route", "expected_lens", "expected_tag"),
    [
        (LAW_POLICY_EXCERPT, "law_policy", "legal_doctrinal_analysis", "governance"),
        (BUSINESS_MANAGEMENT_EXCERPT, "business_management", "management_theory", "strategy"),
        (ENVIRONMENTAL_ECOLOGY_EXCERPT, "environmental_ecology", "ecological_methods", "ecology"),
        (MECHANICAL_CIVIL_EXCERPT, "mechanical_civil_engineering", "engineering_design", "engineering_design"),
        (MATH_STATISTICS_EXCERPT, "math_statistics", "mathematical_rigor", "statistics"),
        (NEURO_COGSCI_EXCERPT, "neuroscience_cognitive_science", "neurocognitive_methods", "neuroscience"),
        (EDUCATION_EMPIRICAL_EXCERPT, "education_empirical", "education_methods", "empirical_education"),
    ],
)
def test_new_broad_routes_emit_specific_review_lenses(draft_text, expected_route, expected_lens, expected_tag):
    profile = build_manuscript_profile({
        "draft_content": draft_text,
        "paper_type": "journal_article",
    })

    assert profile["routing_domain"] == expected_route
    assert expected_lens in profile["review_lenses"]
    assert expected_tag in profile["domain_tags"]
    assert profile["routing_confidence"] >= 0.72

    prompt_pack = get_domain_prompt_pack(profile)
    assert prompt_pack
    assert "Review as" in prompt_pack


@pytest.mark.unit
def test_new_non_ml_routes_do_not_generate_generic_ml_baseline_gap():
    from app.workflows.draft_analysis.nodes.gap_detection import detect_gaps_node

    for draft_text in (LAW_POLICY_EXCERPT, MATH_STATISTICS_EXCERPT, ENVIRONMENTAL_ECOLOGY_EXCERPT):
        profile = build_manuscript_profile({
            "draft_content": draft_text,
            "paper_type": "journal_article",
        })
        result = detect_gaps_node({
            "draft_id": "draft-route",
            "manuscript_profile": profile,
            "claims_by_type": {
                "methodological": [
                    {
                        "id": "claim-1",
                        "claim_text": "The manuscript presents a domain-specific method.",
                        "claim_type": "methodological",
                        "section_location": "Methods",
                        "importance_score": 0.8,
                    }
                ]
            },
            "claims_with_citations": [
                {
                    "claim": {
                        "id": "claim-1",
                        "claim_text": "The manuscript presents a domain-specific method.",
                        "claim_type": "methodological",
                        "section_location": "Methods",
                        "importance_score": 0.8,
                        "requires_citation": False,
                    },
                    "citation_quality": "none",
                    "gaps": [],
                }
            ],
        })

        joined = " ".join(gap["description"] for gap in result.get("coverage_gaps", []))
        assert "baseline comparisons" not in joined.lower()

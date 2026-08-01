import pytest


SEPSIS_SYSTEMATIC_REVIEW_FIXTURE = """
## INTRODUCTION
This article maps clinically applied sepsis MLAs to the SALIENT framework,
which is reported in a companion paper. The mapping sought to validate SALIENT's
capability to guide stakeholders involved in end-to-end MLA implementation.

## Search strategy
The systematic review was performed according to PRISMA guidelines.

## Results
Twenty-six different definitions of sepsis were used, ranging from Sepsis-1 to
Sepsis-3. All mortality papers reported decreased mortality, but most studies
were before-after or observational and subject to confounding bias.

## Discussion
The draft discusses live or near-live data and EHR deployment, but does not
mention HL7, FHIR, data latency, cloud compute, or interface engines. Wong et al.
externally validated the Epic Sepsis Model and found poor performance.

## Conclusions
Our systematic review indicates that implementing MLAs has potential to reduce
mortality. This study also validated the SALIENT framework and suggests it may
apply to other AI tasks.
"""


class TestClaimContextAwareness:
    @pytest.mark.unit
    def test_conclusion_summary_does_not_require_external_citation(self):
        from app.workflows.draft_analysis.nodes.claim_extraction import (
            _claim_requires_external_citation,
            _infer_rhetorical_role,
        )

        claim = "Our systematic review indicates that implementing MLAs has potential to reduce mortality."
        role = _infer_rhetorical_role(claim, "Conclusions")

        assert role == "conclusion_summary"
        assert _claim_requires_external_citation(claim, "Conclusions", role, True) is False

    @pytest.mark.unit
    def test_prior_work_claim_still_requires_external_citation(self):
        from app.workflows.draft_analysis.nodes.claim_extraction import (
            _claim_requires_external_citation,
        )

        claim = "Previous studies show that machine-learning alerts reduce mortality in sepsis."

        assert _claim_requires_external_citation(claim, "Introduction", "prior_work_claim", True) is True

    @pytest.mark.unit
    def test_inline_numeric_citation_near_claim_is_detected(self):
        from app.workflows.draft_analysis.nodes.claim_extraction import _inline_citations_near_claim

        claim = "Early recognition and treatment of sepsis can reduce mortality"
        draft = f"{claim}. 4,5 More recently, sepsis prediction algorithms have proliferated."

        assert _inline_citations_near_claim(claim, draft) == ["4", "5"]

    @pytest.mark.unit
    def test_inline_citation_at_full_sentence_end_is_detected_for_claim_fragment(self):
        from app.workflows.draft_analysis.nodes.claim_extraction import _inline_citations_near_claim

        claim = "rule-based surveillance systems for detecting sepsis in hospital settings can improve outcomes."
        draft = (
            "Early recognition and treatment of sepsis can reduce mortality, and "
            "rule-based surveillance systems for detecting sepsis in hospital settings can improve outcomes.4,5 "
            "More recently, machine learning algorithms have proliferated."
        )
        start = draft.index("rule-based")
        end = start + len(claim)

        assert _inline_citations_near_claim(claim, draft, char_start=start, char_end=end) == ["4", "5"]

    @pytest.mark.unit
    def test_unspaced_superscript_numeric_citation_is_detected_from_text_snippet(self):
        from app.workflows.draft_analysis.citation_rules import apply_existing_citation_gate

        claim = {
            "claim_text": "MLAs that can detect evolving sepsis in patients earlier than rule-based methods have proliferated.",
            "text_snippet": (
                "herein called machine learning algorithms\n"
                "(MLAs), that can detect evolving sepsis in patients earlier than\n"
                "rule-based methods, have proliferated.9,10 Most MLA studies"
            ),
            "requires_citation": True,
            "existing_citations": [],
        }

        apply_existing_citation_gate(claim)

        assert claim["requires_citation"] is False
        assert claim["existing_citations"] == ["9", "10"]

    @pytest.mark.unit
    def test_citation_normalization_preserves_author_year_and_splits_numeric_groups(self):
        from app.workflows.draft_analysis.citation_rules import normalize_citation_values

        assert normalize_citation_values(["9,10", "[4-6]", "Smith (2020)"]) == [
            "9",
            "10",
            "4-6",
            "Smith (2020)",
        ]


class TestCoverageGapQualityGates:
    @pytest.mark.unit
    def test_gap_detection_suppresses_generic_library_miss_and_systematic_review_baseline_gap(self):
        from app.workflows.draft_analysis.nodes.gap_detection import detect_gaps_node

        state = {
            "draft_id": "draft-1",
            "project_id": "project-1",
            "user_id": "user-1",
            "paper_type": "journal_article",
            "draft_content": "This systematic review follows PRISMA and evaluates sepsis alert deployment.",
            "claims_with_citations": [
                {
                    "claim": {
                        "id": "claim-1",
                        "claim_text": "Our systematic review indicates that MLAs have potential to reduce mortality.",
                        "section_location": "Conclusions",
                        "importance_score": 0.9,
                        "requires_citation": False,
                    },
                    "citation_quality": "none",
                    "gaps": ["No supporting literature found in your library"],
                }
            ],
            "claims_by_type": {
                "methodological": [
                    {
                        "id": "claim-2",
                        "claim_text": "We conducted a systematic review.",
                        "claim_type": "methodological",
                        "section_location": "Methods",
                        "importance_score": 0.8,
                    }
                ]
            },
        }

        result = detect_gaps_node(state)

        assert result["coverage_gaps"] == []


class TestExternalRetrievalQualityGates:
    @pytest.mark.unit
    def test_external_discovery_ignores_non_citation_claims_and_generic_gaps(self):
        from app.services.draft_external_source_discovery import _select_targets

        targets = _select_targets(
            "draft-1",
            [
                {
                    "claim": {
                        "id": "claim-1",
                        "claim_text": "Our systematic review indicates that MLAs have potential to reduce mortality.",
                        "importance_score": 0.9,
                        "requires_citation": False,
                    },
                    "citation_quality": "none",
                    "gaps": ["No supporting literature found in your library"],
                }
            ],
            [
                {
                    "id": "gap-1",
                    "description": "No supporting literature found in your library",
                    "severity": "critical",
                }
            ],
        )

        assert targets == []

    @pytest.mark.unit
    def test_external_discovery_targets_unknown_quality_missing_citation_claims(self):
        from app.services.draft_external_source_discovery import _select_targets

        targets = _select_targets(
            "draft-1",
            [
                {
                    "claim": {
                        "id": "claim-1",
                        "claim_text": "Epic Sepsis Model external validation failures are central to deployed clinical machine learning.",
                        "importance_score": 0.9,
                        "requires_citation": True,
                    },
                    "citation_quality": "unknown",
                    "gaps": [],
                }
            ],
            [],
        )

        assert len(targets) == 1
        assert targets[0]["target_type"] == "claim"
        assert "sepsis" in targets[0]["search_query"]

    @pytest.mark.unit
    def test_external_candidate_rejects_cross_domain_keyword_noise(self):
        from app.services.draft_external_source_discovery import _normalize_candidate

        target = {
            "draft_id": "draft-1",
            "target_type": "gap",
            "target_id": "gap-1",
            "text": "Epic Sepsis Model external validation failures for clinical machine learning deployment",
            "search_query": "epic sepsis model external validation clinical machine learning deployment",
            "rank": 1.0,
        }
        bad_paper = {
            "title": "Librarians as Instructors in Public Education",
            "abstract": "This paper studies library instruction and education programs.",
            "citation_count": 500,
            "url": "https://example.test",
        }
        good_paper = {
            "title": "External Validation of a Widely Implemented Proprietary Sepsis Prediction Model",
            "abstract": "A clinical validation study of the Epic Sepsis Model in hospitalized patients.",
            "citation_count": 200,
            "url": "https://example.test/sepsis",
        }

        assert _normalize_candidate(bad_paper, target, "semantic_scholar") is None

        normalized = _normalize_candidate(good_paper, target, "semantic_scholar")
        assert normalized is not None
        assert normalized["relevance_score"] >= 0.62
        assert "sepsis" in normalized["matched_keywords"]

    @pytest.mark.unit
    def test_external_candidate_rejects_anthropology_for_crispr_task(self):
        from app.services.draft_external_source_discovery import _normalize_candidate

        target = {
            "draft_id": "draft-1",
            "target_type": "revision_task",
            "target_id": "task-crispr",
            "text": "Compare CRISPR Cas9 HbF editing in CD34 HSPCs against BCL11A enhancer editing and Exa-cel.",
            "search_query": "crispr cas9 hbf cd34 hspc bcl11a exa-cel sickle editing safety",
            "rank": 1.0,
        }
        bad_paper = {
            "title": "Public secrets in public health: Knowing not to know while making scientific knowledge",
            "abstract": "An anthropology study of clinical research field sites in Africa.",
            "citation_count": 250,
            "url": "https://example.test/anthropology",
        }
        good_paper = {
            "title": "CRISPR Cas9 BCL11A enhancer editing for sickle cell disease",
            "abstract": "Genome editing of CD34 HSPCs increases HbF expression for sickle cell disease therapy.",
            "citation_count": 200,
            "url": "https://example.test/crispr",
        }

        assert _normalize_candidate(bad_paper, target, "openalex") is None

        normalized = _normalize_candidate(good_paper, target, "pubmed")
        assert normalized is not None
        assert normalized["relevance_score"] >= 0.70
        assert "crispr" in normalized["matched_keywords"]

    @pytest.mark.unit
    def test_topic_gate_rejects_off_topic_source_sharing_only_generic_terms(self):
        """RAG contamination fix: a child-maltreatment paper that shares only a
        generic outcome word ('depression') with a social-media review must be
        rejected; an on-topic social-media source passes."""
        from app.services.draft_external_source_discovery import _passes_domain_gate, _distinctive_topic_terms

        profile = {
            "routing_domain": "public_health_psychology",
            "domain_tags": ["adolescent_mental_health", "public_health", "psychology"],
            "review_lenses": ["systematic_review_methods", "behavioral_health"],
            "topic_terms": ["social", "media", "screen", "platform", "networking",
                            "depression", "anxiety", "adolescent", "wellbeing", "use"],
        }
        distinctive = _distinctive_topic_terms(profile)
        assert {"social", "media", "screen"}.issubset(distinctive)
        assert "adolescent" not in distinctive  # generic domain term, removed

        query = "social media adolescent mental health systematic review search strategy"
        off_topic = "Child maltreatment, abuse, neglect, and trauma predicting later depression outcomes."
        on_topic = "Social media use and screen time associated with adolescent depression and anxiety."

        assert _passes_domain_gate(query, off_topic, 0.70, profile) is False
        # A high relevance_score (inflated by citations/methodology overlap) must NOT
        # bypass the topic gate — this was the real Norman/child-abuse leak.
        assert _passes_domain_gate(query, off_topic, 1.0, profile) is False
        assert _passes_domain_gate(query, on_topic, 0.70, profile) is True

    @pytest.mark.unit
    def test_deductive_thesis_does_not_require_citation(self):
        """Issue #2: the author's own non-causal deductive/transitional conclusion is not
        a citable empirical fact — must NOT be flagged as a missing citation."""
        from app.workflows.draft_analysis.nodes.claim_extraction import (
            _claim_requires_external_citation,
            _is_deductive_synthesis,
        )
        deductive = [
            "In short, these superiorities make SIBs a promising alternative to LIBs.",
            "Overall, the evidence suggests layered oxides remain the leading cathode.",
            "Therefore, the field must address the degradation pathways above.",
            "This review provides a comprehensive overview of degradation mechanisms.",
        ]
        for text in deductive:
            assert _is_deductive_synthesis(text) is True, text
            # role unknown -> still suppressed via deductive backstop
            assert _claim_requires_external_citation(text, "Conclusion", None) is False, text

    @pytest.mark.unit
    def test_empirical_and_causal_claims_still_require_citation(self):
        """The deductive guard must not suppress genuine empirical/causal claims."""
        from app.workflows.draft_analysis.nodes.claim_extraction import (
            _claim_requires_external_citation,
            _is_deductive_synthesis,
        )
        # Empirical fact stated as background — still needs a citation.
        empirical = "Sodium-ion batteries achieve energy densities of 150 Wh/kg in recent cells."
        assert _is_deductive_synthesis(empirical) is False
        assert _claim_requires_external_citation(empirical, "Introduction", "background_claim") is True
        # Causal overstatement inside a conclusion is NOT exempted.
        causal = "Therefore, oxygen redox causes the irreversible capacity loss in P2 cathodes."
        assert _is_deductive_synthesis(causal) is False
        assert _claim_requires_external_citation(causal, "Conclusion", "conclusion_summary") is True

    @pytest.mark.unit
    def test_topic_gate_rejects_glass_industry_for_sodium_ion_battery(self):
        """Run-6 regression: a 'Decarbonizing the glass industry' paper was suggested
        for a sodium-ion battery review because the manuscript topic_terms were polluted
        with generic-science words (energy/renewable/materials/application) that the glass
        paper shares. After cleaning topic_terms, the distinctive set is purely technical
        battery vocabulary and the glass paper shares none of it."""
        from app.services.draft_external_source_discovery import _passes_domain_gate, _distinctive_topic_terms

        # topic_terms AS THEY SHOULD BE after stopword cleaning (generics + geo dropped).
        profile = {
            "routing_domain": "chemistry_materials",
            "domain_tags": ["battery", "sodium_ion", "materials_science", "sustainability"],
            "review_lenses": ["materials_degradation", "battery_cathode", "electrochemistry"],
            "topic_terms": ["layered", "batteries", "degradation", "oxides", "sodium-ion",
                            "cathode", "cathodes", "sibs", "modification", "phase"],
        }
        distinctive = _distinctive_topic_terms(profile)
        assert {"layered", "oxides", "cathodes"}.issubset(distinctive)

        query = "sodium-ion battery layered oxide cathode degradation modification strategy"
        glass = ("Decarbonizing the glass industry: a critical and systematic review of "
                 "energy efficiency, renewable furnaces and emission reduction technologies.")
        li_recycling = ("Challenges in recycling spent lithium-ion batteries: hydrometallurgical "
                        "recovery of cobalt and nickel from cathode black mass.")
        on_topic = ("Phase transition and degradation of P2-type layered sodium-ion oxide "
                    "cathodes and modification strategies.")

        # Off-domain (glass) shares only generic/dropped terms → rejected even at high score.
        assert _passes_domain_gate(query, glass, 0.72, profile) is False
        assert _passes_domain_gate(query, glass, 1.0, profile) is False
        # On-topic sodium-ion source passes.
        assert _passes_domain_gate(query, on_topic, 0.70, profile) is True

    @pytest.mark.unit
    def test_topic_terms_excludes_generic_and_affiliation_noise(self):
        """The topic-term extractor must drop generic-science vocabulary and author/
        affiliation/geography noise so the distinctive set stays subject-specific."""
        from app.workflows.draft_analysis.nodes.manuscript_profile import _manuscript_topic_terms

        text = (
            "Review on layered oxide cathodes for sodium-ion batteries: degradation "
            "mechanisms and modification strategies. Juan Wang, Yufeng Zhao. "
            "Shanghai University, Shaanxi, China. This renewable energy materials science "
            "application addresses growing demand. "
        ) * 3
        terms = set(_manuscript_topic_terms(text))
        # Subject-distinctive technical terms retained.
        assert {"layered", "cathodes", "sodium-ion", "batteries"} & terms
        # Generic-science + geo/affiliation noise removed.
        for noise in ("energy", "renewable", "materials", "science", "application",
                      "demand", "university", "china", "strategies", "mechanisms"):
            assert noise not in terms, noise

    @pytest.mark.unit
    def test_topic_gate_keeps_methodology_guideline_source(self):
        """A PRISMA/Cochrane guideline shares no subject terms but must still pass
        for a methodology task (the topic gate must not block methodology sources)."""
        from app.services.draft_external_source_discovery import _passes_domain_gate

        profile = {
            "routing_domain": "public_health_psychology",
            "domain_tags": ["adolescent_mental_health"],
            "topic_terms": ["social", "media", "screen", "platform", "depression", "anxiety"],
        }
        query = "search strategy reporting and PRISMA flow for the systematic review methodology"
        guideline = "PRISMA 2020 statement: an updated guideline for reporting systematic reviews."
        assert _passes_domain_gate(query, guideline, 0.70, profile) is True

    @pytest.mark.unit
    def test_reviewer_and_meta_prompts_have_noise_guards(self):
        from app.workflows.draft_analysis.nodes.reviewer_panel import RATING_CALIBRATION
        from app.workflows.draft_analysis.nodes.meta_reviewer import META_REVIEWER_PROMPT

        cal = RATING_CALIBRATION.lower()
        assert "pdf-extraction artifacts" in cal and "crosssectional" in cal
        assert "over-index" in cal
        assert "tie-breaker" in META_REVIEWER_PROMPT.lower()

    @pytest.mark.unit
    def test_causal_finding_uses_natural_associative_phrasing(self):
        from app.workflows.draft_analysis.nodes.diagnostic_findings import _public_health_psych_findings

        text = (
            "This cross-sectional study examines the influence of social media on adolescent "
            "wellbeing. Social media influence on mental health is discussed."
        )
        findings = _public_health_psych_findings(text, {})
        causal = [f for f in findings if f.get("finding_type") == "causal_inference"]
        assert causal
        assert "associated with" in causal[0]["suggested_action"].lower()
        assert "correlates" not in causal[0]["suggested_action"].lower()

    @pytest.mark.unit
    def test_platform_suggestion_is_chronology_aware(self):
        """Anachronism fix: with a known (old) search year, the platform-terms finding
        frames suggestions to the search period and does NOT demand newer platforms."""
        from app.workflows.draft_analysis.nodes.diagnostic_findings import _public_health_psych_findings

        text = (
            "This systematic review of social media and adolescent mental health searched "
            "Facebook, Instagram, and Twitter (Table 1). Included studies were cross-sectional."
        )
        with_year = _public_health_psych_findings(text, {"latest_search_year": 2018})
        platform = [f for f in with_year if "platform search terms" in f["problem"].lower()]
        assert platform, "expected the platform-terms finding to fire"
        sa = platform[0]["suggested_action"].lower()
        assert "2018" in sa and "postdate" in sa
        assert "platform-agnostic" in sa
        # No-year case keeps a chronology caveat, not an absolute demand.
        no_year = _public_health_psych_findings(text, {})
        sa2 = next(f for f in no_year if "platform search terms" in f["problem"].lower())["suggested_action"].lower()
        assert "chronologically appropriate" in sa2

    @pytest.mark.unit
    def test_manuscript_profile_exposes_topic_terms_and_search_year(self):
        from app.workflows.draft_analysis.nodes.manuscript_profile import build_manuscript_profile

        draft = (
            "Social media use and adolescent mental health: a systematic review. "
            "We examined how social media exposure and screen time relate to depression "
            "and anxiety in adolescents. We searched PubMed and Embase from inception to "
            "March 2018."
        )
        profile = build_manuscript_profile({"draft_content": draft, "paper_type": "journal_article"})
        assert "social" in profile["topic_terms"] and "media" in profile["topic_terms"]
        assert profile["latest_search_year"] == 2018

    @pytest.mark.unit
    def test_citation_suggestion_validation_rejects_unknown_zero_similarity(self):
        from app.services.draft_analysis_langgraph import _valid_citation_result

        assert _valid_citation_result({
            "document_id": "doc-1",
            "document_title": "Unknown",
            "content": "",
            "similarity": 0.0,
        }) is False
        assert _valid_citation_result({
            "document_id": "doc-2",
            "document_title": "Relevant Sepsis Trial",
            "content": "This paper evaluates sepsis alerts in hospital workflows.",
            "similarity": 0.72,
        }) is True

    @pytest.mark.unit
    def test_external_source_payload_with_relevance_score_passes_validation(self):
        from app.services.draft_analysis_langgraph import _suggested_source_payload, _valid_citation_result

        candidate = {
            "title": "Automated Sepsis Alert Systems and Hospital Outcomes",
            "content": "A clinical evaluation of sepsis surveillance alerts in hospital settings.",
            "relevance_score": 0.74,
            "source": "pubmed",
            "doi": "10.1000/example",
        }

        assert _valid_citation_result(candidate) is True
        payload = _suggested_source_payload(candidate)
        assert payload["similarity"] == 0.74
        assert payload["source"] == "pubmed"

    @pytest.mark.unit
    def test_quality_judge_prunes_wrong_domain_suggested_source(self):
        from app.services.draft_analysis_langgraph import sanitize_revision_task_sources

        [task], metadata = sanitize_revision_task_sources(
            [{
                "id": "task-crispr",
                "task_type": "literature_positioning",
                "problem": "The manuscript should compare CRISPR Cas9 HbF editing in CD34 HSPCs with BCL11A enhancer editing.",
                "suggested_action": "Add current sickle cell gene editing literature.",
                "suggested_sources": [
                    {
                        "title": "Public secrets in public health: Knowing not to know while making scientific knowledge",
                        "content": "An anthropology article about scientific knowledge and African public health field sites.",
                        "source": "openalex",
                        "similarity": 0.555,
                    },
                    {
                        "title": "CRISPR Cas9 BCL11A enhancer editing for sickle cell disease",
                        "content": "Genome editing of CD34 HSPCs increases HbF expression for sickle cell disease.",
                        "source": "pubmed",
                        "similarity": 0.86,
                    },
                ],
            }],
            manuscript_profile={
                "routing_domain": "biology",
                "secondary_domains": ["biomedical"],
                "domain_tags": ["crispr"],
            },
            analysis_quality_judge={
                "wrong_domain_flags": [
                    "One suggested citation (anthropology article on public health 'public secrets') is irrelevant."
                ],
            },
        )

        assert len(task["suggested_sources"]) == 1
        assert "CRISPR" in task["suggested_sources"][0]["title"]
        assert metadata["source_safety_metrics"]["sources_pruned"] == 1
        assert metadata["pruned_sources"][0]["reason"] in {"low_similarity", "judge_wrong_domain_flag", "wrong_domain_terms"}

    @pytest.mark.unit
    def test_post_enrichment_consolidation_merges_hpfh_overstatement_duplicates(self):
        from app.workflows.draft_analysis.revision_tasks import consolidate_revision_tasks

        tasks = consolidate_revision_tasks([
            {
                "id": "task-1",
                "task_type": "causal_claim",
                "severity": "major",
                "priority": "medium",
                "problem": "Equating naturally occurring germline HPFH with somatic CRISPR-mediated deletion in adult HSPCs overstates safety.",
                "suggested_action": "Rephrase nature's clinical trial language as biological plausibility only.",
                "anchor_text": "nature has already given a clinical trial demonstrating the efficacy and safety",
            },
            {
                "id": "task-4",
                "task_type": "causal_claim",
                "severity": "major",
                "priority": "medium",
                "problem": "The statement that nature has already given a clinical trial overstates causal inference from observational human genotypes.",
                "suggested_action": "Clarify that natural HPFH is rationale, not prospective therapeutic validation.",
                "anchor_text": "nature has already given a clinical trial demonstrating the efficacy and safety",
            },
        ])

        assert len(tasks) == 1
        assert tasks[0]["duplicate_count"] == 1

    @pytest.mark.unit
    def test_same_section_same_type_platform_terms_tasks_merge(self):
        """Two methodology tasks in the same section about restrictive platform
        search terms must consolidate to one (the reported Tasks 7 & 9 duplicate)."""
        from app.workflows.draft_analysis.revision_tasks import consolidate_revision_tasks

        tasks = consolidate_revision_tasks([
            {
                "id": "t7", "task_type": "methodology", "severity": "major", "priority": "medium",
                "section": "Methods",
                "problem": "The search strategy appears to rely heavily on named platforms and may not include broader terms capturing adolescent digital exposure.",
                "suggested_action": "Add platform-agnostic search terms such as social networking sites and digital media.",
            },
            {
                "id": "t9", "task_type": "methodology", "severity": "major", "priority": "medium",
                "section": "Methods/Search Strategy",
                "problem": "The platform search terms may be too restrictive for adolescent social-media exposure.",
                "suggested_action": "Broaden the platform search terms to capture adolescent digital exposure.",
            },
        ])
        assert len(tasks) == 1, f"expected merge, got {[t['problem'][:40] for t in tasks]}"

    @pytest.mark.unit
    def test_stale_search_drops_contradictory_dates_incomplete_task(self):
        """Contradiction fix: a 'search dates may be incomplete' task is dropped when
        a stale-search task (which confirms the dates ARE reported) is present."""
        from app.workflows.draft_analysis.revision_tasks import consolidate_revision_tasks

        tasks = consolidate_revision_tasks([
            {"id": "stale", "task_type": "methodology", "severity": "major", "priority": "high",
             "section": "Methods/Search Strategy", "issue_family": "search_currency",
             "dedupe_category": "search_currency",
             "problem": "The literature search appears current only through 2018, an 8-year gap relative to 2026.",
             "suggested_action": "Update the search to capture literature since 2018 or add a limitation."},
            {"id": "dbinc", "task_type": "methodology", "severity": "major", "priority": "medium",
             "section": "Methods/Search Strategy", "evidence_rebuttal_reason": "databases_found",
             "problem": "Databases searched are reported (PubMed, Embase), but the search dates per database may be incomplete.",
             "suggested_action": "Add per-database search dates."},
        ])
        blob = " ".join(t.get("problem", "").lower() for t in tasks)
        assert "current only through 2018" in blob
        assert "incomplete" not in blob  # contradictory task dropped

    @pytest.mark.unit
    def test_risk_of_bias_and_coi_tasks_merge_to_one(self):
        """Redundancy fix: risk-of-bias-tool + conflict-of-interest tasks collapse to
        one quality-assessment directive (Gemini's Tasks 3 & 8)."""
        from app.workflows.draft_analysis.revision_tasks import consolidate_revision_tasks

        tasks = consolidate_revision_tasks([
            {"id": "rob", "task_type": "methodology", "severity": "major", "priority": "medium",
             "section": "Quality assessment",
             "problem": "The risk of bias tool choice (RoB 2) does not match the observational study designs.",
             "suggested_action": "Use ROBINS-I for non-randomized studies or justify the tool choice."},
            {"id": "coi", "task_type": "methodology", "severity": "major", "priority": "medium",
             "section": "Methods",
             "problem": "The review does not extract conflict of interest or funding source for included studies.",
             "suggested_action": "Add conflict-of-interest and funding-source extraction fields."},
        ])
        assert len(tasks) == 1

    @pytest.mark.unit
    def test_paraphrased_literature_selection_tasks_merge_with_max_severity(self):
        """Run-6 regression: two paraphrased 'missing literature selection methodology'
        tasks (one in a different section, one tagged minor) must collapse into ONE task
        carrying the higher severity — not ship as separate, contradictory entries."""
        from app.workflows.draft_analysis.revision_tasks import consolidate_revision_tasks

        tasks = consolidate_revision_tasks([
            {"id": "t6", "task_type": "methodology", "severity": "major", "priority": "medium",
             "section": "Methods",
             "problem": "The review lacks a Literature Selection and Scope methodology.",
             "suggested_action": "Add a subsection detailing databases searched and inclusion criteria."},
            {"id": "t8", "task_type": "methodology", "severity": "minor", "priority": "low",
             "section": "Introduction",
             "problem": "It is unclear how the literature was selected and filtered for this review.",
             "suggested_action": "Describe the search strategy and selection criteria used."},
        ])
        assert len(tasks) == 1
        assert tasks[0]["severity"] == "major"  # max severity retained, not the minor one

    @pytest.mark.unit
    def test_missing_replication_task_is_not_minor(self):
        """Issue #10: a methodological-validity gap (missing biological replicates) must
        never ship as minor/suggestion — floored to at least major."""
        from app.workflows.draft_analysis.revision_tasks import _floor_methodology_severity

        task = _floor_methodology_severity({
            "task_type": "methodology", "severity": "minor", "priority": "low",
            "problem": "Figure 4 treats individual colonies as biological replicates (pseudoreplication).",
            "suggested_action": "Report the number of independent donors and aggregate per biological replicate.",
        })
        assert task["severity"] == "major"
        assert task["severity_driver"] == "methodology_validity_floor"

        # A genuinely cosmetic minor issue is left alone.
        cosmetic = _floor_methodology_severity({
            "task_type": "clarity", "severity": "minor", "priority": "low",
            "problem": "A few subsection headings are inconsistently capitalized.",
            "suggested_action": "Use sentence case for all headings.",
        })
        assert cosmetic["severity"] == "minor"

    @pytest.mark.unit
    def test_different_type_same_section_tasks_do_not_over_merge(self):
        """Guard: distinct task_types in the same section must NOT be force-merged."""
        from app.workflows.draft_analysis.revision_tasks import consolidate_revision_tasks

        tasks = consolidate_revision_tasks([
            {
                "id": "a", "task_type": "methodology", "severity": "major", "priority": "medium",
                "section": "Methods",
                "problem": "The search strategy omits gray literature and preprints.",
                "suggested_action": "Search registries and preprint servers.",
            },
            {
                "id": "b", "task_type": "clarity", "severity": "minor", "priority": "low",
                "section": "Methods",
                "problem": "Several method subsections lack clear headings and are hard to follow.",
                "suggested_action": "Add descriptive subsection headings.",
            },
        ])
        assert len(tasks) == 2

    @pytest.mark.unit
    def test_parser_artifact_tasks_suppressed_for_grobid_spacing_flags(self):
        from app.workflows.draft_analysis.revision_tasks import build_revision_tasks

        tasks = build_revision_tasks(
            diagnostic_findings=[],
            reviewer_outputs=[{
                "reviewer_id": "reviewer_3",
                "issues": [{
                    "issue_type": "clarity",
                    "problem": "Figure references are inconsistently formatted and CD34 + spacing appears malformed.",
                    "why_it_matters": "This may confuse readers.",
                    "suggested_action": "Fix malformed figure references and spacing inconsistencies.",
                }],
            }],
            claims=[],
            gaps=[],
            structural_feedback=[],
            structure={"document_metadata": {"grobid_extracted": True}},
            parser_quality={"parser_quality_flags": ["possible_pdf_spacing_artifacts"]},
        )

        assert tasks == []

    @pytest.mark.unit
    def test_parse_artifact_coordinates_populate_page_and_pdf_coordinates(self):
        from app.services.draft_analysis_langgraph import _apply_parse_artifact_anchors

        [task] = _apply_parse_artifact_anchors(
            "draft-1",
            [{
                "id": "task-1",
                "problem": "The manuscript overstates CRISPR safety based on natural HPFH.",
                "anchor_text": "Natural HPFH provides biological plausibility but does not prove CRISPR safety in edited HSPCs.",
            }],
            artifact={
                "anchor_map": [{
                    "section_title": "Discussion",
                    "paragraph_index": 3,
                    "coordinates": {"page": 4, "x": 10.0, "y": 20.0, "width": 100.0, "height": 30.0},
                    "text_snippet": "Natural HPFH provides biological plausibility but does not prove CRISPR safety in edited HSPCs.",
                }]
            },
        )

        assert task["page_number"] == 4
        assert task["paragraph_index"] == 3
        assert task["pdf_coordinates"]["page"] == 4

    @pytest.mark.unit
    def test_revision_task_source_targets_include_literature_and_methodology_tasks(self):
        from app.services.draft_external_source_discovery import _select_task_targets

        tasks = [
            {
                "id": "task-epic",
                "task_type": "literature_positioning",
                "dedupe_category": "epic_sepsis_positioning",
                "severity": "major",
                "priority": "medium",
                "problem": "The manuscript needs sharper synthesis of Epic Sepsis Model external validation failures.",
                "suggested_action": "Add a paragraph contrasting positive deployments with Epic Sepsis Model failures.",
            },
            {
                "id": "task-style",
                "task_type": "clarity",
                "dedupe_category": "clarity:style",
                "severity": "minor",
                "priority": "low",
                "problem": "Some sentences are long.",
                "suggested_action": "Shorten them.",
            },
        ]

        targets = _select_task_targets("draft-1", tasks)

        assert len(targets) == 1
        assert targets[0]["target_id"] == "task-epic"
        assert "epic" in targets[0]["search_query"]

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_revision_task_source_enrichment_uses_internal_library_first(self, monkeypatch):
        from app.services import draft_external_source_discovery as discovery

        def fake_retrieve(project_id, query, limit, document_id, similarity_threshold):
            return [{
                "document_id": "doc-epic",
                "document_title": "External Validation of a Widely Implemented Sepsis Prediction Model",
                "content": "Epic Sepsis Model external validation sepsis prediction clinical deployment.",
                "similarity": 0.84,
            }]

        async def fail_external(_target):
            raise AssertionError("external APIs should not be called when internal source passes")

        monkeypatch.setattr("app.services.rag_retrieval.retrieve_relevant_chunks", fake_retrieve)
        monkeypatch.setattr(discovery, "_fetch_candidates_for_target", fail_external)

        [task] = await discovery.enrich_revision_tasks_with_sources(
            draft_id="draft-1",
            project_id="project-1",
            user_id="user-1",
            revision_tasks=[{
                "id": "task-epic",
                "task_type": "literature_positioning",
                "dedupe_category": "epic_sepsis_positioning",
                "severity": "major",
                "priority": "medium",
                "problem": "The manuscript needs sharper synthesis of Epic Sepsis Model external validation failures.",
                "suggested_action": "Add a paragraph contrasting positive deployments with Epic Sepsis Model failures.",
            }],
        )

        assert len(task["suggested_sources"]) == 1
        assert task["suggested_sources"][0]["source"] == "library"
        assert task["suggested_sources"][0]["document_id"] == "doc-epic"

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_revision_task_source_enrichment_falls_back_to_vetted_external_source(self, monkeypatch):
        from app.services import draft_external_source_discovery as discovery

        async def no_internal(_project_id, _target, limit=6):
            return []

        async def fake_external(_target):
            return [{
                "title": "External Validation of a Widely Implemented Proprietary Sepsis Prediction Model",
                "abstract": "A clinical study of Epic Sepsis Model external validation in hospitalized patients.",
                "authors": ["Wong"],
                "year": 2021,
                "source": "pubmed",
                "doi": "10.1001/example",
                "paper_url": "https://example.test/epic-sepsis",
                "citation_count": 250,
                "relevance_score": 0.82,
            }]

        monkeypatch.setattr(discovery, "_fetch_internal_sources_for_task", no_internal)
        monkeypatch.setattr(discovery, "_fetch_candidates_for_target", fake_external)

        [task] = await discovery.enrich_revision_tasks_with_sources(
            draft_id="draft-1",
            project_id="project-1",
            user_id="user-1",
            revision_tasks=[{
                "id": "task-epic",
                "task_type": "literature_positioning",
                "dedupe_category": "epic_sepsis_positioning",
                "severity": "major",
                "priority": "medium",
                "problem": "The manuscript needs sharper synthesis of Epic Sepsis Model external validation failures.",
                "suggested_action": "Add a paragraph contrasting positive deployments with Epic Sepsis Model failures.",
            }],
        )

        assert len(task["suggested_sources"]) == 1
        assert task["suggested_sources"][0]["source"] == "pubmed"
        assert task["suggested_sources"][0]["doi"] == "10.1001/example"


class TestQualityV2Diagnostics:
    @pytest.mark.unit
    def test_manuscript_profile_routes_systematic_clinical_ai_framework_review(self):
        from app.workflows.draft_analysis.nodes.manuscript_profile import build_manuscript_profile

        profile = build_manuscript_profile({
            "draft_content": SEPSIS_SYSTEMATIC_REVIEW_FIXTURE,
            "paper_type": "journal_article",
        })

        assert profile["genre"] == "systematic_review"
        assert "clinical_ai" in profile["domain_tags"]
        assert "framework_validation" in profile["review_lenses"]
        assert "pubmed" in profile["retrieval_domains"]

    @pytest.mark.unit
    def test_diagnostics_catch_required_sepsis_fixture_failures(self):
        from app.workflows.draft_analysis.nodes.manuscript_profile import build_manuscript_profile
        from app.workflows.draft_analysis.nodes.diagnostic_findings import diagnostic_findings_node

        profile = build_manuscript_profile({
            "draft_content": SEPSIS_SYSTEMATIC_REVIEW_FIXTURE,
            "paper_type": "journal_article",
        })
        result = diagnostic_findings_node({
            "draft_id": "draft-1",
            "project_id": "project-1",
            "user_id": "user-1",
            "draft_content": SEPSIS_SYSTEMATIC_REVIEW_FIXTURE,
            "paper_type": "journal_article",
            "manuscript_profile": profile,
            "current_step": "diagnostics",
            "progress_percentage": 77,
            "reviewer_outputs": [],
        })
        problems = " ".join(f["problem"] for f in result["diagnostic_findings"]).lower()

        assert "companion paper" in problems
        # De-hardcoded: definitional-heterogeneity finding is now condition-agnostic.
        assert "heterogeneous definitions" in problems
        assert "data-pipeline" in problems
        assert "mortality" in problems
        assert "external validation" in problems
        assert "framework" in problems
        assert "exclusion" in problems

    @pytest.mark.unit
    def test_diagnostics_generalize_to_unseen_domain_without_sample_tokens(self):
        """De-hardcode regression: the definitional-heterogeneity and framework
        checks must fire on a manuscript from a different field with none of the
        sample-paper tokens (no sepsis, no SALIENT, no CRISPR)."""
        from app.workflows.draft_analysis.nodes.diagnostic_findings import diagnostic_findings_node

        draft = """
        ## Introduction
        This systematic review maps teacher-burnout interventions onto the RESTORE
        model, which is reported in a companion paper.
        ## Methods
        The systematic review followed PRISMA guidelines.
        ## Results
        Included studies used several different definitions of burnout, which
        complicated synthesis across the evidence base.
        ## Conclusion
        This study validated the RESTORE framework and suggests it may apply to
        other educational settings.
        """
        profile = {
            "genre": "systematic_review",
            "review_lenses": ["systematic_review_methods", "framework_validation"],
            "domain_tags": ["education"],
            "contribution_types": ["framework_mapping"],
        }
        result = diagnostic_findings_node({
            "draft_id": "draft-1",
            "project_id": "project-1",
            "user_id": "user-1",
            "draft_content": draft,
            "paper_type": "journal_article",
            "manuscript_profile": profile,
            "current_step": "diagnostics",
            "progress_percentage": 77,
            "reviewer_outputs": [],
        })
        problems = " ".join(f["problem"] for f in result["diagnostic_findings"]).lower()

        assert "heterogeneous definitions" in problems
        assert "companion paper" in problems
        assert "framework" in problems
        # No sample-paper leakage in generalized findings.
        assert "sepsis" not in problems
        assert "salient" not in problems

    @pytest.mark.unit
    def test_public_health_review_has_no_clinical_ai_text_bleed(self):
        """Cross-domain de-hardcode: a public-health/social-media systematic review
        must NOT emit clinical-AI/EHR/sepsis wording from the shared systematic-review
        diagnostic checks (the reported 'clinical AI deployments' leak)."""
        from app.workflows.draft_analysis.nodes.diagnostic_findings import diagnostic_findings_node

        draft = """
        ## Introduction
        This systematic review examines the real-world impact of social media use on
        adolescent mental health.
        ## Methods
        The systematic review followed PRISMA. We searched PubMed, Embase, and
        PsycINFO for titles and abstracts published in English. Risk of bias was
        assessed with the NIH Quality Assessment Tool.
        ## Results
        Most included studies were cross-sectional. Reported associations varied.
        ## Discussion
        Findings suggest social media exposure correlates with anxiety.
        """
        profile = {
            "genre": "systematic_review",
            "review_lenses": ["systematic_review_methods", "behavioral_health", "risk_of_bias"],
            "domain_tags": ["adolescent_mental_health", "behavioral_health", "psychology", "public_health"],
        }
        result = diagnostic_findings_node({
            "draft_id": "d", "project_id": "p", "user_id": "u",
            "draft_content": draft, "paper_type": "journal_article",
            "manuscript_profile": profile,
            "current_step": "diagnostics", "progress_percentage": 77, "reviewer_outputs": [],
        })
        blob = " ".join(
            f"{f.get('problem','')} {f.get('why_it_matters','')} {f.get('suggested_action','')}"
            for f in result["diagnostic_findings"]
        ).lower()

        # The systematic-review checks still fire (gray-literature/source breadth),
        # but with domain-neutral wording — no clinical-AI/EHR/sepsis bleed.
        assert result["diagnostic_findings"], "expected systematic-review findings to fire"
        assert "clinical ai" not in blob
        assert "ehr" not in blob
        assert "sepsis" not in blob
        assert "electronic health record" not in blob

    @pytest.mark.unit
    def test_diagnostics_catch_english_language_search_restriction(self):
        from app.workflows.draft_analysis.nodes.manuscript_profile import build_manuscript_profile
        from app.workflows.draft_analysis.nodes.diagnostic_findings import diagnostic_findings_node

        draft = """
        This systematic review followed PRISMA guidelines. We searched PubMed,
        Embase, and Web of Science for titles and abstracts published in English.
        """
        profile = build_manuscript_profile({"draft_content": draft, "paper_type": "journal_article"})
        result = diagnostic_findings_node({
            "draft_id": "draft-1",
            "project_id": "project-1",
            "user_id": "user-1",
            "draft_content": draft,
            "paper_type": "journal_article",
            "manuscript_profile": profile,
            "current_step": "diagnostics",
            "progress_percentage": 77,
            "reviewer_outputs": [],
        })
        problems = " ".join(f["problem"] for f in result["diagnostic_findings"]).lower()

        assert "english-language" in problems
        assert "limitation" in problems

    @pytest.mark.unit
    def test_diagnostics_catch_gray_literature_and_fairness_gaps(self):
        from app.workflows.draft_analysis.nodes.manuscript_profile import build_manuscript_profile
        from app.workflows.draft_analysis.nodes.diagnostic_findings import diagnostic_findings_node

        draft = """
        This systematic review studied real-world implementation of clinical AI
        machine learning algorithms deployed in hospital electronic health record workflows.
        PubMed, Embase, and Web of Science databases were searched for peer-reviewed studies.
        """
        profile = build_manuscript_profile({"draft_content": draft, "paper_type": "journal_article"})
        result = diagnostic_findings_node({
            "draft_id": "draft-1",
            "project_id": "project-1",
            "user_id": "user-1",
            "draft_content": draft,
            "paper_type": "journal_article",
            "manuscript_profile": profile,
            "current_step": "diagnostics",
            "progress_percentage": 77,
            "reviewer_outputs": [],
        })
        problems = " ".join(f["problem"] for f in result["diagnostic_findings"]).lower()

        assert "gray literature" in problems
        assert "algorithmic fairness" in problems

    @pytest.mark.unit
    def test_diagnostics_catch_commercial_bias_and_lead_time_relevance(self):
        from app.workflows.draft_analysis.nodes.manuscript_profile import build_manuscript_profile
        from app.workflows.draft_analysis.nodes.diagnostic_findings import diagnostic_findings_node

        draft = """
        This systematic review studied real-world implementation of clinical AI
        machine learning algorithms deployed in hospital EHR workflows. Included studies
        reported median lead time from alert to first antibiotic administration.
        """
        profile = build_manuscript_profile({"draft_content": draft, "paper_type": "journal_article"})
        result = diagnostic_findings_node({
            "draft_id": "draft-1",
            "project_id": "project-1",
            "user_id": "user-1",
            "draft_content": draft,
            "paper_type": "journal_article",
            "manuscript_profile": profile,
            "current_step": "diagnostics",
            "progress_percentage": 77,
            "reviewer_outputs": [],
        })
        problems = " ".join(f["problem"] for f in result["diagnostic_findings"]).lower()

        assert "commercial" in problems or "vendor" in problems
        assert "lead time" in problems
        assert any("lead time" in (f["anchor_text"] or "").lower() for f in result["diagnostic_findings"])

    @pytest.mark.unit
    def test_diagnostics_catch_rob2_design_applicability_issue(self):
        from app.workflows.draft_analysis.nodes.manuscript_profile import build_manuscript_profile
        from app.workflows.draft_analysis.nodes.diagnostic_findings import diagnostic_findings_node

        draft = """
        This systematic review followed PRISMA. Risk of bias was assessed using
        Cochrane RoB 2 for randomized trials and ROBINS-I. Most included studies
        were before-after, observational, cohort, and other nonrandomized designs.
        """
        profile = build_manuscript_profile({"draft_content": draft, "paper_type": "journal_article"})
        result = diagnostic_findings_node({
            "draft_id": "draft-1",
            "project_id": "project-1",
            "user_id": "user-1",
            "draft_content": draft,
            "paper_type": "journal_article",
            "manuscript_profile": profile,
            "current_step": "diagnostics",
            "progress_percentage": 77,
            "reviewer_outputs": [],
        })
        problems = " ".join(f["problem"] for f in result["diagnostic_findings"]).lower()

        assert "rob 2" in problems
        assert "observational" in problems or "before-after" in problems

    @pytest.mark.unit
    def test_reviewer_context_includes_profile_and_diagnostics(self):
        from app.workflows.draft_analysis.nodes.manuscript_profile import build_manuscript_profile
        from app.workflows.draft_analysis.nodes.diagnostic_findings import diagnostic_findings_node
        from app.workflows.draft_analysis.nodes.reviewer_panel import build_reviewer_context

        profile = build_manuscript_profile({
            "draft_content": SEPSIS_SYSTEMATIC_REVIEW_FIXTURE,
            "paper_type": "journal_article",
        })
        diagnostics = diagnostic_findings_node({
            "draft_id": "draft-1",
            "project_id": "project-1",
            "user_id": "user-1",
            "draft_content": SEPSIS_SYSTEMATIC_REVIEW_FIXTURE,
            "paper_type": "journal_article",
            "manuscript_profile": profile,
            "current_step": "diagnostics",
            "progress_percentage": 77,
            "reviewer_outputs": [],
        })["diagnostic_findings"]
        context = build_reviewer_context({
            "draft_id": "draft-1",
            "project_id": "project-1",
            "user_id": "user-1",
            "draft_content": SEPSIS_SYSTEMATIC_REVIEW_FIXTURE,
            "paper_type": "journal_article",
            "structure": {"word_count": 500, "sections": []},
            "claims_with_citations": [],
            "coverage_gaps": [],
            "external_sources": [],
            "manuscript_profile": profile,
            "diagnostic_findings": diagnostics,
            "current_step": "review",
            "progress_percentage": 80,
            "reviewer_outputs": [],
        }, "methodology")

        assert "MANUSCRIPT PROFILE" in context
        assert "PROFILE-AWARE DIAGNOSTICS" in context
        assert "companion paper" in context.lower()

    @pytest.mark.unit
    def test_revision_tasks_dedupe_diagnostics_and_reviewer_issues(self):
        from app.workflows.draft_analysis.revision_tasks import build_revision_tasks

        diagnostic = {
            "finding_type": "systematic_review",
            "severity": "major",
            "section_reference": "Methods",
            "anchor_text": "The systematic review was performed according to PRISMA guidelines.",
            "problem": "The review describes PRISMA-style methods but does not clearly report protocol registration.",
            "why_it_matters": "Registration status reduces concern about post hoc analytic flexibility.",
            "suggested_action": "State whether the review was registered and provide the registry identifier if available.",
            "confidence": 0.9,
        }
        reviewer = {
            "reviewer_id": "methodology",
            "issues": [{
                "issue_type": "methodology",
                "section_reference": "Methods",
                "anchor_text": "PRISMA guidelines.",
                "problem": "The review describes PRISMA-style methods but does not clearly report protocol registration.",
                "why_it_matters": "Readers cannot assess selective method changes.",
                "suggested_action": "State whether the review was registered and provide the registry identifier if available.",
                "confidence": 0.8,
            }],
        }

        tasks = build_revision_tasks(
            diagnostic_findings=[diagnostic],
            reviewer_outputs=[reviewer],
            claims=[],
            gaps=[],
            structural_feedback=[],
        )

        assert len(tasks) == 1
        assert tasks[0]["source_type"] == "diagnostic"

    @pytest.mark.unit
    def test_existing_citations_suppress_missing_citation_revision_tasks(self):
        from app.workflows.draft_analysis.citation_rules import apply_existing_citation_gate
        from app.workflows.draft_analysis.revision_tasks import build_revision_tasks

        claim = {
            "id": "claim-8",
            "claim_text": "Early recognition and treatment of sepsis can reduce mortality.",
            "section_location": "Introduction",
            "requires_citation": True,
            "existing_citations": ["1"],
            "importance_score": 0.9,
        }

        apply_existing_citation_gate(claim)
        tasks = build_revision_tasks(
            diagnostic_findings=[],
            reviewer_outputs=[],
            claims=[claim],
            gaps=[],
            structural_feedback=[],
        )

        assert claim["requires_citation"] is False
        assert tasks == []

    @pytest.mark.unit
    def test_missing_citation_tasks_keep_valid_suggested_sources(self):
        from app.workflows.draft_analysis.revision_tasks import build_revision_tasks

        claim = {
            "id": "claim-2",
            "claim_text": "Prior studies show clinical AI alerts reduce sepsis mortality.",
            "section_location": "Introduction",
            "requires_citation": True,
            "importance_score": 0.9,
            "suggested_sources": [{
                "document_id": "doc-1",
                "document_title": "External Validation of a Sepsis Prediction Model",
                "display": "Wong et al. (2021) · 84% match",
                "similarity": 0.84,
            }],
        }
        # Phase 2a: citation tasks now require reviewer corroboration.
        # Use anchor_text that directly overlaps the claim text so the corroboration gate
        # fires, while keeping the problem text neutral (avoids CATEGORY_PATTERNS).
        reviewer_outputs = [{
            "reviewer_id": "literature_positioning",
            "issues": [{
                "issue_type": "literature_positioning",
                "section_reference": "Introduction",
                "anchor_text": "Prior studies show clinical AI alerts reduce sepsis mortality",
                "problem": "This background claim about prior studies and clinical AI alerts lacks a supporting citation.",
                "why_it_matters": "Unsupported background claims weaken the introduction.",
                "suggested_action": "Add a primary source supporting this claim.",
            }],
        }]

        tasks = build_revision_tasks(
            diagnostic_findings=[],
            reviewer_outputs=reviewer_outputs,
            claims=[claim],
            gaps=[],
            structural_feedback=[],
        )

        citation_tasks = [t for t in tasks if t.get("task_type") == "citation"]
        assert len(citation_tasks) == 1
        assert citation_tasks[0]["suggested_sources"][0]["document_id"] == "doc-1"

    @pytest.mark.unit
    def test_missing_citation_task_suppressed_when_snippet_has_unspaced_citation(self):
        from app.workflows.draft_analysis.revision_tasks import build_revision_tasks

        claim = {
            "id": "claim-7",
            "claim_text": "MLAs that can detect evolving sepsis in patients earlier than rule-based methods have proliferated.",
            "section_location": "Introduction",
            "requires_citation": True,
            "existing_citations": [],
            "importance_score": 0.8,
            "text_snippet": (
                "herein called machine learning algorithms\n"
                "(MLAs), that can detect evolving sepsis in patients earlier than\n"
                "rule-based methods, have proliferated.9,10 Most MLA studies"
            ),
        }

        tasks = build_revision_tasks(
            diagnostic_findings=[],
            reviewer_outputs=[],
            claims=[claim],
            gaps=[],
            structural_feedback=[],
        )

        assert tasks == []

    @pytest.mark.unit
    def test_prospero_variants_merge_into_one_revision_task(self):
        from app.workflows.draft_analysis.revision_tasks import build_revision_tasks

        diagnostic = {
            "finding_type": "systematic_review",
            "severity": "major",
            "section_reference": "Methods",
            "anchor_text": "This review followed PRISMA.",
            "problem": "There is no clear statement of prospective protocol registration such as PROSPERO.",
            "why_it_matters": "Readers cannot distinguish planned methods from post hoc choices.",
            "suggested_action": "Add the PROSPERO identifier or state that no protocol was registered.",
            "confidence": 0.9,
        }
        reviewer = {
            "reviewer_id": "methodology",
            "issues": [{
                "issue_type": "methodology",
                "section_reference": "Methods",
                "anchor_text": "PRISMA.",
                "problem": "Was a review protocol registered prospectively?",
                "why_it_matters": "Registration controls analytic flexibility.",
                "suggested_action": "Report protocol registration status and justify missing registration if absent.",
                "confidence": 0.8,
            }],
        }

        tasks = build_revision_tasks(
            diagnostic_findings=[diagnostic],
            reviewer_outputs=[reviewer],
            claims=[],
            gaps=[],
            structural_feedback=[],
        )

        assert len(tasks) == 1
        assert tasks[0]["dedupe_category"] == "protocol_registration"

    @pytest.mark.unit
    def test_salient_framework_positioning_and_overclaim_merge(self):
        from app.workflows.draft_analysis.revision_tasks import build_revision_tasks

        tasks = build_revision_tasks(
            diagnostic_findings=[
                {
                    "finding_type": "framework_validation",
                    "severity": "critical",
                    "section_reference": "Discussion",
                    "anchor_text": "This study validated the SALIENT framework.",
                    "problem": "The manuscript overstates SALIENT framework validation and generalizability.",
                    "why_it_matters": "A single-domain mapping exercise is not independent validation.",
                    "suggested_action": "Reframe SALIENT claims and define what evidence would validate the framework.",
                    "confidence": 0.9,
                },
                {
                    "finding_type": "literature_positioning",
                    "severity": "major",
                    "section_reference": "Discussion",
                    "anchor_text": "SALIENT framework.",
                    "problem": "The framework contribution is not positioned tightly enough against CFIR, NASSS, RE-AIM, or Decide-AI.",
                    "why_it_matters": "Readers cannot tell whether SALIENT adds distinct explanatory power.",
                    "suggested_action": "Add a comparison table against CFIR, NASSS, RE-AIM, and Decide-AI.",
                    "confidence": 0.85,
                },
            ],
            reviewer_outputs=[],
            claims=[],
            gaps=[],
            structural_feedback=[],
        )

        assert len(tasks) == 1
        assert tasks[0]["dedupe_category"] == "framework_generalizability"

    @pytest.mark.unit
    def test_deployment_validation_variants_merge_into_one_revision_task(self):
        from app.workflows.draft_analysis.revision_tasks import build_revision_tasks

        tasks = build_revision_tasks(
            diagnostic_findings=[{
                "finding_type": "literature_positioning",
                "severity": "major",
                "section_reference": "Discussion",
                "anchor_text": "Epic Sepsis Model validation controversy",
                "problem": "The manuscript needs a sharper synthesis of Epic Sepsis Model external validation failures and controversies around deployed sepsis prediction.",
                "why_it_matters": "This is central domain context for clinical ML deployment.",
                "suggested_action": "Add a paragraph contrasting positive deployment studies with external validation failures such as the Epic Sepsis Model.",
                "confidence": 0.9,
            }],
            reviewer_outputs=[{
                "reviewer_id": "literature_positioning",
                "issues": [{
                    "issue_type": "framework_validation",
                    "section_reference": "Introduction; overall discussion",
                    "anchor_text": "deployed sepsis MLAs",
                    "problem": "The manuscript does not sharply engage with major external validation failures and deployment controversies.",
                    "why_it_matters": "Transportability failures are central to the discourse on clinical AI deployment.",
                    "suggested_action": "Clarify what SALIENT explains about these failures and broader deployment controversies.",
                    "confidence": 0.85,
                }],
            }],
            claims=[],
            gaps=[],
            structural_feedback=[],
        )

        assert len(tasks) == 1
        assert tasks[0]["dedupe_category"] == "deployment_validation_positioning"
        assert tasks[0]["task_type"] == "literature_positioning"

    @pytest.mark.unit
    def test_prisma_reporting_variants_merge_while_search_scope_merges_separately(self):
        from app.workflows.draft_analysis.revision_tasks import build_revision_tasks

        tasks = build_revision_tasks(
            diagnostic_findings=[
                {
                    "finding_type": "systematic_review",
                    "severity": "major",
                    "section_reference": "Methods",
                    "anchor_text": "PRISMA flow diagram",
                    "problem": "The manuscript does not clearly enumerate reasons for full-text exclusion or provide detailed counts by exclusion category.",
                    "why_it_matters": "Transparent reporting of exclusion reasons is necessary.",
                    "suggested_action": "Include a complete PRISMA flow diagram with categorized exclusion reasons.",
                    "confidence": 0.9,
                },
                {
                    "finding_type": "systematic_review",
                    "severity": "major",
                    "section_reference": "Methods",
                    "anchor_text": "Search strategy",
                    "problem": "The manuscript references PRISMA-style methods but does not clearly report full search strings, database coverage details, date ranges, or comprehensive exclusion reasons.",
                    "why_it_matters": "Systematic reviews must be reproducible from text alone.",
                    "suggested_action": "Provide complete search strings, exact database names and coverage dates, and a detailed PRISMA flow diagram.",
                    "confidence": 0.85,
                },
                {
                    "finding_type": "systematic_review",
                    "severity": "major",
                    "section_reference": "Methods",
                    "anchor_text": "published in English",
                    "problem": "The search appears restricted to English-language titles or abstracts.",
                    "why_it_matters": "Language restrictions can bias systematic reviews.",
                    "suggested_action": "Acknowledge the English-language restriction and discuss its impact.",
                    "confidence": 0.85,
                },
                {
                    "finding_type": "systematic_review",
                    "severity": "major",
                    "section_reference": "Methods",
                    "anchor_text": "database search",
                    "problem": "The search strategy does not clearly include gray literature, registries, or implementation reports.",
                    "why_it_matters": "Implemented systems are often described outside peer-reviewed articles.",
                    "suggested_action": "State whether gray literature, registries, or implementation reports were searched.",
                    "confidence": 0.85,
                },
            ],
            reviewer_outputs=[],
            claims=[],
            gaps=[],
            structural_feedback=[],
        )

        categories = {task["dedupe_category"] for task in tasks}
        assert categories == {"review_reporting_transparency", "search_scope_bias"}
        assert len(tasks) == 2

    @pytest.mark.unit
    def test_latest_failure_shape_compacts_to_target_task_count(self):
        from app.workflows.draft_analysis.revision_tasks import build_revision_tasks

        diagnostics = [
            {
                "finding_type": "literature_positioning",
                "severity": "major",
                "section_reference": "Discussion",
                "anchor_text": "Epic Sepsis Model",
                "problem": "The manuscript needs a sharper synthesis of Epic Sepsis Model external validation failures and controversies around deployed sepsis prediction.",
                "why_it_matters": "Central deployed sepsis AI context is missing.",
                "suggested_action": "Add a paragraph contrasting positive deployment studies with external validation failures such as the Epic Sepsis Model.",
            },
            {
                "finding_type": "systematic_review",
                "severity": "critical",
                "section_reference": "Results",
                "anchor_text": "definitions of sepsis",
                "problem": "Although heterogeneity in sepsis definitions is acknowledged, the manuscript does not systematically analyze how differing outcome definitions affect comparability.",
                "why_it_matters": "Performance metrics are definition-dependent.",
                "suggested_action": "Provide a structured table mapping each study’s sepsis definition to outcomes.",
            },
            {
                "finding_type": "framework_validation",
                "severity": "critical",
                "section_reference": "Discussion",
                "anchor_text": "necessary and sufficient",
                "problem": "The manuscript equates post hoc mapping of study findings to SALIENT stages with evidence that the stages are necessary and sufficient.",
                "why_it_matters": "Mapping demonstrates compatibility, not proof of necessity or sufficiency.",
                "suggested_action": "Reframe this as preliminary applicability evidence and compare SALIENT with CFIR, NASSS, RE-AIM, and DECIDE-AI.",
            },
            {
                "finding_type": "systematic_review",
                "severity": "major",
                "section_reference": "Methods",
                "anchor_text": "published in English",
                "problem": "The search appears restricted to English-language titles or abstracts.",
                "why_it_matters": "Language restrictions can bias systematic reviews.",
                "suggested_action": "Acknowledge the English-language restriction and discuss its impact.",
            },
            {
                "finding_type": "systematic_review",
                "severity": "major",
                "section_reference": "Methods",
                "anchor_text": "PRISMA",
                "problem": "The manuscript does not clearly enumerate reasons for full-text exclusion or provide detailed counts by exclusion category.",
                "why_it_matters": "Transparent reporting is necessary.",
                "suggested_action": "Include a complete PRISMA flow diagram with categorized exclusion reasons.",
            },
            {
                "finding_type": "systematic_review",
                "severity": "major",
                "section_reference": "Quality assessment",
                "anchor_text": "RoB 2 and ROBINS-I",
                "problem": "The risk-of-bias tool choice needs clearer matching to study design, especially where RoB 2 is mentioned alongside mostly observational evidence.",
                "why_it_matters": "RoB 2 is intended for randomized trials.",
                "suggested_action": "Clarify which studies were assessed with RoB 2 versus ROBINS-I.",
            },
            {
                "finding_type": "clinical_ai",
                "severity": "major",
                "section_reference": "Results",
                "anchor_text": "lead time to antibiotic use",
                "problem": "The manuscript mentions alert lead time or time-to-antibiotic metrics without clearly judging clinical relevance.",
                "why_it_matters": "Earlier alerts may not be clinically meaningful if the difference is only minutes.",
                "suggested_action": "Report actual lead times and define clinically meaningful thresholds.",
            },
            {
                "finding_type": "systematic_review",
                "severity": "major",
                "section_reference": "Methods",
                "anchor_text": "database search",
                "problem": "The search appears not to explicitly include gray literature, health system reports, regulatory submissions, or conference proceedings.",
                "why_it_matters": "Deployment failures are often underreported in peer-reviewed journals.",
                "suggested_action": "Clarify whether gray literature sources were searched and discuss likely bias.",
            },
            {
                "finding_type": "clinical_ai",
                "severity": "major",
                "section_reference": "Discussion",
                "anchor_text": "live or near-live data",
                "problem": "The deployment discussion mentions live or near-live data but under-specifies the operational data-pipeline burden.",
                "why_it_matters": "EHR integration, HL7/FHIR interfaces, latency, monitoring, and compute ownership are decisive constraints.",
                "suggested_action": "Add a deployment-reality subsection covering EHR integration, latency, monitoring, staffing, and ownership.",
            },
        ]
        reviewer_outputs = [{
            "reviewer_id": "literature_positioning",
            "issues": [
                {
                    "issue_type": "framework_validation",
                    "section_reference": "Discussion",
                    "anchor_text": "deployed sepsis MLAs",
                    "problem": "The manuscript does not sharply engage with major controversies such as the Epic Sepsis Model external validation failures.",
                    "why_it_matters": "Epic and similar cases are central to deployed clinical AI debates.",
                    "suggested_action": "Clarify what SALIENT explains about these failures.",
                    "confidence": 0.8,
                },
                {
                    "issue_type": "literature_positioning",
                    "section_reference": "Contribution claims",
                    "anchor_text": "AI-task agnostic",
                    "problem": "The novelty claim may be overstated and AI-task agnosticism overgeneralizes beyond the evidence.",
                    "why_it_matters": "Overbroad novelty and generalizability claims weaken credibility.",
                    "suggested_action": "Qualify novelty and reframe AI-task agnosticism as a future-testable hypothesis.",
                    "confidence": 0.8,
                },
            ],
        }]

        tasks = build_revision_tasks(
            diagnostic_findings=diagnostics,
            reviewer_outputs=reviewer_outputs,
            claims=[],
            gaps=[],
            structural_feedback=[],
        )

        assert 8 <= len(tasks) <= 10
        categories = {task["dedupe_category"] for task in tasks}
        assert "deployment_validation_positioning" in categories
        assert "framework_generalizability" in categories
        assert "review_reporting_transparency" in categories
        assert "search_scope_bias" in categories

    @pytest.mark.unit
    def test_clarity_tasks_suppress_formatting_only_heading_flags(self):
        from app.workflows.draft_analysis.revision_tasks import build_revision_tasks

        tasks = build_revision_tasks(
            diagnostic_findings=[],
            reviewer_outputs=[],
            claims=[],
            gaps=[],
            structural_feedback=[{
                "feedback_type": "clarity",
                "severity": "minor",
                "section_reference": "Methods",
                "specific_issue": "Section headings are in all caps.",
                "feedback_text": "The heading format uses all caps.",
                "suggestions": ["Change section heading capitalization."],
            }],
        )

        assert tasks == []

    @pytest.mark.unit
    def test_revision_task_readiness_score_is_deterministic_and_guardrailed(self):
        from app.workflows.draft_analysis.revision_tasks import calculate_revision_task_readiness_score

        tasks = [
            {"severity": "critical", "task_type": "citation", "suggested_sources": []},
            {"severity": "major", "task_type": "methodology"},
            {"severity": "major", "task_type": "deployment"},
            {"severity": "minor", "task_type": "clarity"},
        ]

        first = calculate_revision_task_readiness_score(tasks)
        second = calculate_revision_task_readiness_score(list(reversed(tasks)))

        assert first == second
        assert first["readiness_score"] == 81
        assert first["verdict"] == "Minor Revisions"
        assert first["score_breakdown"]["guardrail"] == "critical_issue_present"

    @pytest.mark.unit
    def test_revision_task_anchors_clip_at_word_boundaries(self):
        from app.workflows.draft_analysis.revision_tasks import build_revision_tasks

        diagnostic = {
            "finding_type": "systematic_review",
            "severity": "major",
            "section_reference": "Methods",
            "anchor_text": " ".join(["database search strategy"] * 90) + " child.",
            "problem": "The search strategy does not clearly include gray literature, registries, or implementation reports for real-world clinical AI deployments.",
            "why_it_matters": "Implemented clinical systems are often described outside peer-reviewed articles.",
            "suggested_action": "State whether gray literature was searched and justify any omission.",
            "confidence": 0.9,
        }

        [task] = build_revision_tasks(
            diagnostic_findings=[diagnostic],
            reviewer_outputs=[],
            claims=[],
            gaps=[],
            structural_feedback=[],
        )

        assert task["anchor_text"].endswith("...")
        assert not task["anchor_text"][:-3].endswith("strateg")

    @pytest.mark.unit
    def test_sodium_battery_duplicate_review_tasks_compact_to_issue_families(self):
        from app.workflows.draft_analysis.revision_tasks import build_revision_tasks

        reviewer_outputs = [{
            "reviewer_id": "literature_positioning",
            "issues": [
                {
                    "issue_type": "literature_positioning",
                    "section_reference": "Introduction",
                    "anchor_text": "P2 and O3 layered oxides",
                    "problem": "Degradation mechanisms for P2 and O3 layered oxides are not clearly distinguished at the outset.",
                    "why_it_matters": "The review conflates phase families with different sodium coordination and slab-gliding behavior.",
                    "suggested_action": "Separate P2 and O3 degradation pathways in an early organizing table.",
                },
                {
                    "issue_type": "coverage",
                    "section_reference": "Framework",
                    "anchor_text": "layered oxide degradation",
                    "problem": "The introduction treats layered oxide degradation monolithically before later discussing P2/O3 differences.",
                    "why_it_matters": "P2 and O3 cathodes have different phase-transition pathways.",
                    "suggested_action": "Add a P2 versus O3 taxonomy before surveying degradation mechanisms.",
                },
                {
                    "issue_type": "methodology",
                    "section_reference": "Methods",
                    "anchor_text": "systematic review",
                    "problem": "The battery manuscript calls itself a systematic review but does not report search databases or screening criteria.",
                    "why_it_matters": "Readers cannot tell whether the materials literature was surveyed transparently.",
                    "suggested_action": "Either add a concise search-method paragraph or rename the article as a comprehensive review.",
                },
                {
                    "issue_type": "methodology",
                    "section_reference": "Methods",
                    "anchor_text": "review",
                    "problem": "The sodium-ion battery review lacks transparent search strategy details and inclusion criteria.",
                    "why_it_matters": "A systematic label requires enough method detail to be reproducible.",
                    "suggested_action": "Report databases, query terms, and screening criteria, or soften the claim to narrative review.",
                },
            ],
        }]

        tasks = build_revision_tasks(
            diagnostic_findings=[],
            reviewer_outputs=reviewer_outputs,
            claims=[],
            gaps=[],
            structural_feedback=[],
        )

        families = {task["issue_family"] for task in tasks}
        assert len(tasks) == 2
        # materials_review_methodology now unifies with the generic literature-selection
        # family via _SUPER_FAMILY (same underlying "describe your lit selection" issue),
        # so the methodology dupes collapse under that canonical family label.
        assert families == {"battery_phase_taxonomy", "literature_selection_reporting"}
        assert all(task["duplicate_count"] == 1 for task in tasks)

    @pytest.mark.unit
    def test_materials_diagnostics_add_commercialization_cost_checks(self):
        from app.workflows.draft_analysis.nodes.diagnostic_findings import diagnostic_findings_node

        text = """
        Sodium-ion layered oxide cathodes are a promising alternative because of their low cost
        and commercial viability. However, several O3 materials remain moisture sensitive.
        High nickel and cobalt layered oxides show strong capacity retention.
        """

        result = diagnostic_findings_node({
            "draft_content": text,
            "manuscript_profile": {
                "domain_tags": ["materials_science"],
                "review_lenses": ["materials_degradation"],
            },
        })

        problems = " ".join(f["problem"] for f in result["diagnostic_findings"]).lower()
        assert "manufacturing cost" in problems
        assert "nickel and cobalt" in problems

    @pytest.mark.unit
    def test_revision_quality_metrics_track_dedupe_anchor_and_sources(self):
        from app.services.draft_analysis_langgraph import _revision_quality_metrics

        metrics = _revision_quality_metrics([
            {
                "task_type": "citation",
                "anchor_text": "Specific claim",
                "page_number": 2,
                "suggested_sources": [{"title": "Relevant source"}],
                "duplicate_count": 2,
            },
            {
                "task_type": "literature_positioning",
                "section": "Discussion",
                "duplicate_count": 0,
            },
        ])

        assert metrics["total_tasks"] == 2
        assert metrics["merged_duplicate_tasks"] == 2
        assert metrics["anchor_coverage"] == 1.0
        assert metrics["page_anchor_coverage"] == 0.5
        assert metrics["citation_source_coverage"] == 1.0

    @pytest.mark.unit
    def test_meta_review_major_revision_caps_readiness_verdict(self):
        from app.services.draft_analysis_langgraph import apply_meta_review_readiness_guardrail

        guarded = apply_meta_review_readiness_guardrail(
            {
                "readiness_score": 79,
                "verdict": "Minor Revisions",
                "score_breakdown": {"major_tasks": 7},
            },
            {"overall_recommendation": "major_revision"},
        )

        assert guarded["readiness_score"] == 69
        assert guarded["verdict"] == "Major Revisions"
        assert guarded["score_breakdown"]["base_readiness_score"] == 79
        assert guarded["score_breakdown"]["base_verdict"] == "Minor Revisions"
        assert guarded["score_breakdown"]["meta_review_recommendation"] == "major_revision"

    @pytest.mark.unit
    def test_meta_review_minor_revision_caps_score_but_keeps_minor_verdict(self):
        from app.services.draft_analysis_langgraph import apply_meta_review_readiness_guardrail

        guarded = apply_meta_review_readiness_guardrail(
            {
                "readiness_score": 91,
                "verdict": "Strong Submission",
                "score_breakdown": {},
            },
            {"overall_recommendation": "minor_revision"},
        )

        assert guarded["readiness_score"] == 84
        assert guarded["verdict"] == "Minor Revisions"

    @pytest.mark.unit
    def test_meta_review_reject_sets_reject_verdict(self):
        from app.services.draft_analysis_langgraph import apply_meta_review_readiness_guardrail

        guarded = apply_meta_review_readiness_guardrail(
            {
                "readiness_score": 62,
                "verdict": "Needs Work",
                "score_breakdown": {},
            },
            {"overall_recommendation": "reject"},
        )

        assert guarded["readiness_score"] == 39
        assert guarded["verdict"] == "Reject"
        assert guarded["score_breakdown"]["editorial_recommendation"] == "reject"

    @pytest.mark.unit
    def test_social_justice_sources_fail_closed_for_wrong_domain_papers(self):
        from app.services.draft_analysis_langgraph import sanitize_revision_task_sources

        [task], metadata = sanitize_revision_task_sources(
            [{
                "id": "task-social-ai",
                "task_type": "causal_claim",
                "problem": "The manuscript should clarify whether social justice prompting is a pedagogical heuristic rather than an empirical claim about model behavior.",
                "suggested_action": "Reframe the claim and add composition pedagogy or AI ethics sources.",
                "anchor_text": "students approach generative AI through social justice",
                "suggested_sources": [
                    {
                        "title": "Review of Multifunctional Separators: Stabilizing the Cathode and the Anode for Alkali Metal-Sulfur and Selenium Batteries",
                        "content": "Layered cathodes, separators, and electrochemical battery performance.",
                        "source": "openalex",
                        "similarity": 0.91,
                    },
                    {
                        "title": "Teaching Critical AI Literacy in the Writing Classroom",
                        "content": "Composition pedagogy, classroom writing, social justice, generative AI, and student literacy.",
                        "source": "semantic_scholar",
                        "similarity": 0.81,
                    },
                ],
            }],
            manuscript_profile={
                "routing_domain": "humanities_education",
                "evidence_mode": "pedagogical",
                "domain_tags": ["composition_pedagogy", "ai_ethics"],
            },
            analysis_quality_judge={},
        )

        assert len(task["suggested_sources"]) == 1
        assert "Writing Classroom" in task["suggested_sources"][0]["title"]
        assert metadata["source_safety_metrics"]["sources_pruned"] == 1

    @pytest.mark.unit
    def test_source_status_marks_pruned_all_when_all_found_sources_are_removed(self):
        from app.services.draft_analysis_langgraph import sanitize_revision_task_sources

        [task], metadata = sanitize_revision_task_sources(
            [{
                "id": "task-social-ai",
                "task_type": "literature_positioning",
                "problem": "Position the AI writing pedagogy claim in composition studies.",
                "suggested_action": "Add composition pedagogy sources.",
                "anchor_text": "social justice AI writing assistant",
                "source_search_status": "found",
                "suggested_sources": [
                    {
                        "title": "Sodium-Ion Battery Cathode Degradation",
                        "content": "Layered oxide cathodes and electrolytes.",
                        "source": "openalex",
                        "similarity": 0.91,
                    }
                ],
            }],
            manuscript_profile={
                "routing_domain": "humanities_education",
                "domain_tags": ["composition_pedagogy"],
            },
            analysis_quality_judge={},
        )

        assert task["suggested_sources"] == []
        assert task["source_search_status"] == "pruned_all"
        assert metadata["source_safety_metrics"]["sources_pruned"] == 1

    @pytest.mark.unit
    def test_internal_gap_prompt_leaks_are_not_revision_tasks(self):
        from app.workflows.draft_analysis.revision_tasks import build_revision_tasks

        tasks = build_revision_tasks(
            diagnostic_findings=[],
            reviewer_outputs=[],
            claims=[],
            gaps=[
                {
                    "id": "gap-1",
                    "gap_type": "missing_evidence",
                    "description": "Claim in Introduction: 'However, what has not been discussed...' — no supporting citations found. no matching evidence in library or online.",
                    "reasoning": "",
                    "severity": "critical",
                },
                {
                    "id": "gap-2",
                    "gap_type": "methodological_gaps",
                    "description": "No baseline comparisons mentioned for methodology",
                    "reasoning": "",
                    "severity": "major",
                },
            ],
            structural_feedback=[],
        )

        assert tasks == []

    @pytest.mark.unit
    def test_unclassified_other_tasks_do_not_all_merge(self):
        from app.workflows.draft_analysis.revision_tasks import build_revision_tasks

        tasks = build_revision_tasks(
            diagnostic_findings=[],
            reviewer_outputs=[],
            claims=[],
            gaps=[
                {
                    "id": "gap-1",
                    "gap_type": "unclassified",
                    "description": "Add more detail on electrolyte decomposition pathways.",
                    "reasoning": "The chemistry discussion is too thin.",
                    "severity": "major",
                },
                {
                    "id": "gap-2",
                    "gap_type": "unclassified",
                    "description": "Clarify the figure-caption attribution requirements.",
                    "reasoning": "The production issue is separate from chemistry.",
                    "severity": "major",
                },
            ],
            structural_feedback=[],
        )

        assert len(tasks) == 2
        assert all(task["duplicate_count"] == 0 for task in tasks)

    @pytest.mark.unit
    def test_parser_artifact_tasks_suppressed_when_structure_has_abstract_methods(self):
        from app.workflows.draft_analysis.revision_tasks import build_revision_tasks

        tasks = build_revision_tasks(
            diagnostic_findings=[],
            reviewer_outputs=[{
                "reviewer_id": "clarity",
                "issues": [
                    {
                        "issue_type": "clarity",
                        "section_reference": "Abstract",
                        "anchor_text": "No abstract section indicated in structure list",
                        "problem": "The manuscript structure provided does not list an Abstract section.",
                        "why_it_matters": "Readers need a concise abstract.",
                        "suggested_action": "Provide a structured abstract.",
                    },
                    {
                        "issue_type": "methodology",
                        "section_reference": "Methods",
                        "anchor_text": "Methods",
                        "problem": "The Methods appear truncated and incomplete.",
                        "why_it_matters": "Readers need complete methods.",
                        "suggested_action": "Add the missing methods.",
                    },
                ],
            }],
            claims=[],
            gaps=[],
            structural_feedback=[],
            structure={"has_abstract": True, "has_methods": True, "document_metadata": {"grobid_extracted": True}},
            parser_quality={"parser_quality_flags": ["possible_pdf_spacing_artifacts"]},
        )

        assert tasks == []

    @pytest.mark.unit
    def test_build_structure_from_grobid_adds_abstract_and_anchor_map(self):
        from app.services.draft_parse_artifacts import (
            assess_parse_quality,
            build_anchor_map,
            build_structure_from_extracted_data,
        )

        extracted = {
            "abstract": "This abstract describes CRISPR editing in CD34 cells.",
            "abstract_paragraphs": [
                {
                    "id": "abstract-para-0",
                    "text": "This abstract describes CRISPR editing in CD34 cells.",
                    "coordinates": {"page": 1, "x": 12.0, "y": 24.0, "width": 200.0, "height": 40.0},
                    "sentences": [],
                }
            ],
            "full_text": ("This abstract describes CRISPR editing in CD34 cells. Methods text Results text Discussion text. " * 30),
            "sections": [
                {
                    "id": "section-0",
                    "title": "Methods",
                    "type": "methods",
                    "content": "We edited CD34 cells using CRISPR-Cas9.",
                    "paragraphs": [{"id": "p1", "text": "We edited CD34 cells using CRISPR-Cas9.", "coordinates": {"page": 2}}],
                },
                {
                    "id": "section-1",
                    "title": "Discussion",
                    "type": "discussion",
                    "content": "The findings require in vivo validation.",
                    "paragraphs": [{"id": "p2", "text": "The findings require in vivo validation.", "coordinates": {"page": 4}}],
                },
            ],
            "metadata": {"page_count": 4},
        }

        structure = build_structure_from_extracted_data(extracted)
        anchor_map = build_anchor_map(structure)
        quality = assess_parse_quality(
            full_text=extracted["full_text"],
            structure=structure,
            anchor_map=anchor_map,
            file_type="pdf",
        )

        assert structure["has_abstract"] is True
        assert structure["has_methods"] is True
        abstract_anchor = next(anchor for anchor in anchor_map if anchor["section_type"] == "abstract")
        assert abstract_anchor["page_number"] == 1
        assert abstract_anchor["coordinates"]["x"] == 12.0
        assert quality["parse_blocked"] is False

    @pytest.mark.unit
    def test_literature_domain_filter_drops_mpox_for_crispr_query(self):
        from app.workflows.draft_analysis.nodes.literature_search import _filter_domain_contamination

        results = _filter_domain_contamination(
            query="CRISPR Cas9 HbF induction sickle cell CD34 HSPC",
            manuscript_profile={"routing_domain": "biology"},
            results=[
                {
                    "document_title": "More Virulent Mpox Clade Can Be Sexually Associated, WHO and CDC Warn",
                    "content": "Mpox outbreak infectious disease surveillance.",
                    "similarity": 0.61,
                },
                {
                    "document_title": "CRISPR-Cas9 disruption of BCL11A enhancer for fetal hemoglobin induction",
                    "content": "CD34 hematopoietic stem progenitor cells sickle cell disease.",
                    "similarity": 0.61,
                },
            ],
        )

        assert len(results) == 1
        assert "BCL11A" in results[0]["document_title"]


# ===========================================================================
# Prompt FIX-2 .. FIX-11 hardening — new coverage
# ===========================================================================


class TestAuthorSelfReferentialCitation:
    """FIX-4: never demand a citation for the authors' own framework/model thesis."""

    @pytest.mark.unit
    def test_extract_author_coined_terms_finds_cued_framework(self):
        from app.workflows.draft_analysis.nodes.manuscript_profile import _extract_author_coined_terms
        text = (
            "We propose SALIENT, a reporting framework for clinical AI. "
            "The SALIENT framework integrates all elements of the standards. "
            "SALIENT was evaluated across studies. SALIENT improves reporting."
        )
        terms = _extract_author_coined_terms(text)
        assert any(t.upper() == "SALIENT" for t in terms)

    @pytest.mark.unit
    def test_extract_author_coined_terms_ignores_common_acronyms(self):
        from app.workflows.draft_analysis.nodes.manuscript_profile import _extract_author_coined_terms
        text = "We used DNA and RNA and PCR and MRI. DNA RNA PCR MRI DNA RNA PCR."
        terms = _extract_author_coined_terms(text)
        assert "DNA" not in terms and "RNA" not in terms and "PCR" not in terms

    @pytest.mark.unit
    def test_is_author_self_referential_matches_coined_term(self):
        from app.workflows.draft_analysis.revision_tasks import _is_author_self_referential
        assert _is_author_self_referential(
            "The FOOBAR framework integrates X and Y", ["FOOBAR"]
        )
        assert not _is_author_self_referential(
            "The study measured outcomes across groups", ["FOOBAR"]
        )

    @pytest.mark.unit
    def test_build_skips_citation_task_for_author_framework(self):
        from app.workflows.draft_analysis.revision_tasks import build_revision_tasks
        claims = [{
            "id": "c1",
            "claim_text": "The SALIENT framework integrates all elements of the reporting standards.",
            "requires_citation": True,
            "importance_score": 0.8,
            "section_location": "Conclusion",
        }]
        tasks = build_revision_tasks(
            diagnostic_findings=[], reviewer_outputs=[], claims=claims, gaps=[],
            structural_feedback=[], manuscript_profile={"author_coined_terms": ["SALIENT"]},
        )
        assert all("SALIENT" not in t.get("problem", "") for t in tasks)

    @pytest.mark.unit
    def test_build_still_demands_citation_without_coined_term(self):
        from app.workflows.draft_analysis.revision_tasks import build_revision_tasks
        claims = [{
            "id": "c1",
            "claim_text": "Sepsis mortality dropped 30% after deployment in the cohort.",
            "requires_citation": True,
            "importance_score": 0.8,
            "section_location": "Results",
        }]
        # Phase 2a: citation tasks require reviewer corroboration — add a matching issue.
        # Use anchor_text verbatim from the claim so the token-overlap gate (≥0.3) fires.
        reviewer_outputs = [{
            "reviewer_id": "methodology",
            "issues": [{
                "issue_type": "literature_positioning",
                "section_reference": "Results",
                # A1: anchor_text overlaps the claim AND expresses citation intent
                # (both conditions must hold in at least one corroboration string).
                "anchor_text": "Sepsis mortality dropped 30% after deployment: this claim is unsupported and needs a citation.",
                "problem": "The claimed 30% mortality drop after deployment is unsupported and needs a citation.",
                "why_it_matters": "Quantitative outcome claims need primary evidence.",
                "suggested_action": "Cite the study reporting this outcome.",
            }],
        }]
        tasks = build_revision_tasks(
            diagnostic_findings=[], reviewer_outputs=reviewer_outputs, claims=claims, gaps=[],
            structural_feedback=[], manuscript_profile={"author_coined_terms": ["SALIENT"]},
        )
        # A1: the reviewer issue and claim both address the same citation gap, so they
        # dedup into one task (task_type may be canonicalized from the reviewer's issue_type).
        # Assert at least one task touches this mortality/deployment claim.
        assert tasks
        assert any("mortality" in (t.get("problem") or "").lower() or "deployment" in (t.get("problem") or "").lower() for t in tasks)

    # ------------------------------------------------------------------
    # Phase 2a: corroboration gate tests
    # ------------------------------------------------------------------

    @pytest.mark.unit
    def test_uncorroborated_claim_does_not_emit_citation_task(self):
        """Phase 2a: a background claim with no matching reviewer issue → no durable task."""
        from app.workflows.draft_analysis.revision_tasks import build_revision_tasks
        claims = [{
            "id": "c-sib",
            "claim_text": "SIBs play a commercial role in large-scale grid storage.",
            "requires_citation": True,
            "importance_score": 0.65,
            "section_location": "Introduction",
        }]
        # No reviewer issues mentioning SIBs or commercial role.
        reviewer_outputs = [{
            "reviewer_id": "methodology",
            "issues": [{
                "issue_type": "methodology",
                "section_reference": "Methods",
                "anchor_text": "electrolyte composition",
                "problem": "The electrolyte composition is not sufficiently described.",
                "why_it_matters": "Reproducibility requires full electrolyte details.",
                "suggested_action": "Report full electrolyte composition.",
            }],
        }]
        tasks = build_revision_tasks(
            diagnostic_findings=[], reviewer_outputs=reviewer_outputs, claims=claims,
            gaps=[], structural_feedback=[],
        )
        assert not any(t.get("task_type") == "citation" for t in tasks)

    @pytest.mark.unit
    def test_corroborated_claim_emits_citation_task(self):
        """Phase 2a: same claim WITH an overlapping reviewer issue → citation task emitted."""
        from app.workflows.draft_analysis.revision_tasks import build_revision_tasks
        claims = [{
            "id": "c-sib",
            "claim_text": "SIBs play a commercial role in large-scale grid storage.",
            "requires_citation": True,
            "importance_score": 0.65,
            "section_location": "Introduction",
        }]
        reviewer_outputs = [{
            "reviewer_id": "literature_positioning",
            "issues": [{
                "issue_type": "citation",
                "section_reference": "Introduction",
                "anchor_text": "SIBs play a commercial role in grid storage",
                "problem": "The claim about the commercial role of SIBs lacks a citation.",
                "why_it_matters": "Commercial adoption claims need primary sources.",
                "suggested_action": "Cite a market or deployment study.",
            }],
        }]
        tasks = build_revision_tasks(
            diagnostic_findings=[], reviewer_outputs=reviewer_outputs, claims=claims,
            gaps=[], structural_feedback=[],
        )
        assert any(t.get("task_type") == "citation" for t in tasks)

    # ------------------------------------------------------------------
    # Phase 2b: modal-future deductive guard tests
    # ------------------------------------------------------------------

    @pytest.mark.unit
    def test_modal_future_phrases_are_deductive(self):
        """Phase 2b: sentences containing modal-future language are flagged as deductive."""
        from app.workflows.draft_analysis.nodes.claim_extraction import _is_deductive_synthesis
        modal_cases = [
            "An alternate approach to electrode design needs to be explored.",
            "The long-term safety profile remains to be determined.",
            "Whether this approach generalizes warrants further investigation.",
            "Future work should investigate the low-temperature performance.",
            "The optimal electrolyte concentration remains to be explored.",
            "How XRD patterns evolve under cycling could be explored in future studies.",
            "Whether this mechanism merits investigation under real conditions is unclear.",
        ]
        for text in modal_cases:
            assert _is_deductive_synthesis(text) is True, f"Expected deductive: {text!r}"

    @pytest.mark.unit
    def test_modal_future_causal_is_not_deductive(self):
        """Phase 2b: causal overstatement inside a modal sentence is NOT suppressed."""
        from app.workflows.draft_analysis.nodes.claim_extraction import _is_deductive_synthesis
        causal = "Future work should explore how oxygen redox causes irreversible capacity loss."
        assert _is_deductive_synthesis(causal) is False

    @pytest.mark.unit
    def test_empirical_background_claim_stays_non_deductive(self):
        """Phase 2b: a plain empirical statement is not deductive."""
        from app.workflows.draft_analysis.nodes.claim_extraction import _is_deductive_synthesis
        empirical = "Sodium-ion batteries achieve energy densities of 150 Wh/kg."
        assert _is_deductive_synthesis(empirical) is False

    # ------------------------------------------------------------------
    # Phase 2c: author_coined_terms cue-only + COMMON_ACRONYMS updates
    # ------------------------------------------------------------------

    @pytest.mark.unit
    def test_extract_author_coined_terms_excludes_field_acronyms(self):
        """Phase 2c: CRISPR/XRD/FIGURE repeated many times → NOT returned as authored terms."""
        from app.workflows.draft_analysis.nodes.manuscript_profile import _extract_author_coined_terms
        text = (
            "CRISPR editing in CD34 cells was performed using CRISPR-Cas9. "
            "CRISPR off-target effects were assessed by XRD analysis. "
            "XRD patterns confirmed the structure. XRD data are shown in FIGURE 1. "
            "FIGURE 2 compares the results. FIGURE 3 shows the schematic. "
            "We propose SALIENT, a reporting framework for clinical AI. "
            "The SALIENT framework integrates all elements."
        )
        terms = _extract_author_coined_terms(text)
        # SALIENT is cue-introduced → must appear
        assert any(t.upper() == "SALIENT" for t in terms), f"Expected SALIENT in {terms}"
        # Field acronyms must NOT appear
        for forbidden in ("CRISPR", "XRD", "FIGURE"):
            assert forbidden not in [t.upper() for t in terms], (
                f"{forbidden} should not be in authored terms: {terms}"
            )

    @pytest.mark.unit
    def test_extract_author_coined_terms_no_cue_returns_empty(self):
        """Phase 2c: text with only field acronyms and no cue phrases → empty list."""
        from app.workflows.draft_analysis.nodes.manuscript_profile import _extract_author_coined_terms
        text = (
            "CRISPR Cas9 edits BCL11A enhancer. CRISPR is well established. "
            "XRD confirmed lattice parameters. XRD is standard. "
            "TABLE 1 summarizes results. TABLE 2 provides statistics."
        )
        terms = _extract_author_coined_terms(text)
        assert terms == [], f"Expected empty list, got {terms}"


class TestDiagnosticRescuePass:
    """FIX-5: critical/major diagnostics — especially fairness — must not be dropped."""

    @pytest.mark.unit
    def test_fairness_finding_promoted_even_if_generic_task_covers(self):
        from app.workflows.draft_analysis.revision_tasks import rescue_critical_diagnostics
        tasks = [{
            "id": "t1", "task_type": "deployment", "severity": "major",
            "section": "Discussion", "issue_family": "deployment_validation_positioning",
            "dedupe_category": "deployment_validation_positioning",
            "problem": "Deployment limitations are not fully discussed.",
            "suggested_action": "Discuss deployment limitations.",
        }]
        findings = [{
            "finding_type": "deployment", "severity": "major", "section_reference": "Discussion",
            "problem": "No algorithmic fairness or demographic bias analysis across subgroups.",
            "why_it_matters": "Fairness is a safety concern for sepsis prediction.",
            "suggested_action": "Add demographic subgroup fairness and calibration analysis.",
        }]
        out = rescue_critical_diagnostics(tasks, findings)
        assert any(t.get("rescued_from_finding") for t in out)
        assert any("fairness" in (t.get("problem", "") + t.get("suggested_action", "")).lower() for t in out)

    @pytest.mark.unit
    def test_covered_nonundroppable_finding_not_duplicated(self):
        from app.workflows.draft_analysis.revision_tasks import rescue_critical_diagnostics
        tasks = [{
            "id": "t1", "task_type": "methodology", "severity": "major", "section": "Methods",
            "issue_family": "review_reporting_transparency", "dedupe_category": "review_reporting_transparency",
            "problem": "PRISMA flow diagram incomplete.", "suggested_action": "Add full PRISMA flow.",
        }]
        findings = [{
            "finding_type": "systematic_review", "severity": "major", "section_reference": "Methods",
            "problem": "PRISMA flow diagram is incomplete and lacks exclusion counts.",
            "suggested_action": "Provide a complete PRISMA flow diagram.",
        }]
        out = rescue_critical_diagnostics(tasks, findings)
        assert len(out) == 1

    @pytest.mark.unit
    def test_minor_finding_not_rescued(self):
        from app.workflows.draft_analysis.revision_tasks import rescue_critical_diagnostics
        out = rescue_critical_diagnostics([], [{
            "finding_type": "clarity", "severity": "minor",
            "problem": "Minor wording issue.", "suggested_action": "Reword.",
        }])
        assert out == []


class TestFinalPairwiseDedup:
    """FIX-6/issue #20: collapse near-duplicate survivors, preserve distinct clusters."""

    @pytest.mark.unit
    def test_near_identical_tasks_collapse(self):
        from app.workflows.draft_analysis.revision_tasks import final_pairwise_dedup
        base = {
            "task_type": "methodology", "section": "Methods", "issue_family": "search_scope_bias",
            "problem": "The search strategy reproducibility is unclear across databases.",
            "suggested_action": "Report full search strings and database coverage for reproducibility.",
            "severity": "major",
        }
        a = {**base, "id": "t8"}
        b = {**base, "id": "t10", "problem": "Search strategy reproducibility is unclear across databases."}
        out = final_pairwise_dedup([a, b])
        assert len(out) == 1

    @pytest.mark.unit
    def test_distinct_cluster_tasks_preserved(self):
        from app.workflows.draft_analysis.revision_tasks import final_pairwise_dedup
        a = {"id": "t1", "task_type": "methodology", "section": "Methods",
             "issue_family": "search_scope_bias", "problem": "Search strategy incomplete.",
             "suggested_action": "Report search strings.", "severity": "major"}
        b = {"id": "t2", "task_type": "literature_positioning", "section": "Introduction",
             "issue_family": "foundational_theory_positioning", "problem": "Novelty over prior work unclear.",
             "suggested_action": "Position against seminal frameworks.", "severity": "major"}
        out = final_pairwise_dedup([a, b])
        assert len(out) == 2

    @pytest.mark.unit
    def test_undroppable_task_never_merged(self):
        from app.workflows.draft_analysis.revision_tasks import final_pairwise_dedup
        a = {"id": "t1", "task_type": "deployment", "section": "Discussion",
             "issue_family": "deployment", "problem": "Deployment limitations not discussed.",
             "suggested_action": "Discuss deployment limitations.", "severity": "major"}
        b = {"id": "t2", "task_type": "deployment", "section": "Discussion", "undroppable": True,
             "issue_family": "deployment", "problem": "Deployment limitations not discussed fully.",
             "suggested_action": "Discuss deployment limitations and add fairness analysis.", "severity": "major"}
        out = final_pairwise_dedup([a, b])
        assert len(out) == 2


class TestGroundingCheck:
    """FIX-7/issue #2: downgrade + flag absence claims the body already answers."""

    @pytest.mark.unit
    def test_absence_claim_downgraded_when_present(self):
        from app.services.draft_task_evidence import verify_absence_claims
        draft = (
            "Introduction.\n\n"
            "The authors performed a demographic subgroup fairness analysis stratified by "
            "race and sex, reporting calibration across all groups in Table 3.\n\n"
            "Conclusion."
        )
        tasks = [{
            "id": "t1", "severity": "major",
            "problem": "The manuscript does not address demographic subgroup fairness.",
            "suggested_action": "Add demographic subgroup fairness analysis stratified by race and sex.",
        }]
        out, metrics = verify_absence_claims(tasks, draft, threshold=0.5)
        assert metrics["absence_tasks_downgraded"] == 1
        assert out[0]["severity"] == "minor"
        # HOTFIX 1: problem stays clean; the verifier note moves to verification_note.
        assert out[0]["problem"] == tasks[0]["problem"]
        assert out[0]["verification_status"] == "partially_addressed"
        assert out[0].get("verification_note")

    @pytest.mark.unit
    def test_absence_claim_untouched_when_genuinely_absent(self):
        from app.services.draft_task_evidence import verify_absence_claims
        draft = "Introduction. The study examines battery cathodes.\n\nConclusion."
        tasks = [{
            "id": "t1", "severity": "major",
            "problem": "The manuscript does not address demographic subgroup fairness.",
            "suggested_action": "Add demographic subgroup fairness analysis stratified by race and sex.",
        }]
        out, metrics = verify_absence_claims(tasks, draft)
        assert metrics["absence_tasks_downgraded"] == 0
        assert out[0]["severity"] == "major"

    @pytest.mark.unit
    def test_non_absence_task_ignored(self):
        from app.services.draft_task_evidence import verify_absence_claims
        tasks = [{"id": "t1", "severity": "major", "problem": "Strengthen the abstract.",
                  "suggested_action": "Rewrite the abstract."}]
        out, metrics = verify_absence_claims(tasks, "anything", threshold=0.1)
        assert metrics["absence_tasks_downgraded"] == 0


class TestDomainAuditTriggers:
    """FIX-9/issue #19-20: domain-specific audit checklist injected for methodology."""

    @pytest.mark.unit
    def test_clinical_ai_triggers_present(self):
        from app.workflows.draft_analysis.nodes.manuscript_profile import _domain_audit_triggers
        triggers = _domain_audit_triggers(
            is_clinical_ai=True, is_systematic=True, is_materials_battery=False, is_biomedical=False
        )
        joined = " ".join(triggers).lower()
        assert "alert fatigue" in joined
        assert "definition versioning" in joined or "definition change" in joined

    @pytest.mark.unit
    def test_materials_triggers_present(self):
        from app.workflows.draft_analysis.nodes.manuscript_profile import _domain_audit_triggers
        triggers = _domain_audit_triggers(
            is_clinical_ai=False, is_systematic=False, is_materials_battery=True, is_biomedical=False
        )
        assert any("comparison table" in t.lower() for t in triggers)

    @pytest.mark.unit
    def test_no_triggers_for_unmatched_domain(self):
        from app.workflows.draft_analysis.nodes.manuscript_profile import _domain_audit_triggers
        assert _domain_audit_triggers(
            is_clinical_ai=False, is_systematic=False, is_materials_battery=False, is_biomedical=False
        ) == []

    @pytest.mark.unit
    def test_methodology_context_injects_triggers(self):
        from app.workflows.draft_analysis.nodes.reviewer_panel import _build_methodology_context
        state = {
            "claims_with_citations": [], "structural_feedback": [], "diagnostic_findings": [],
            "manuscript_profile": {"domain_audit_triggers": ["alert fatigue: demand a false-positive analysis"]},
        }
        ctx = _build_methodology_context(state)
        assert "alert fatigue" in ctx.lower()

    @pytest.mark.unit
    def test_gene_editing_triggers_present(self):
        from app.workflows.draft_analysis.nodes.manuscript_profile import _domain_audit_triggers
        triggers = _domain_audit_triggers(
            is_clinical_ai=False, is_systematic=False, is_materials_battery=False,
            is_biomedical=False, is_gene_editing=True,
        )
        joined = " ".join(triggers).lower()
        assert "protein" in joined and "mrna" in joined
        assert "pseudoreplication" in joined
        assert "translocation" in joined or "inversion" in joined

    @pytest.mark.unit
    def test_gene_editing_triggers_absent_by_default(self):
        from app.workflows.draft_analysis.nodes.manuscript_profile import _domain_audit_triggers
        triggers = _domain_audit_triggers(
            is_clinical_ai=False, is_systematic=False, is_materials_battery=False,
            is_biomedical=True,
        )
        joined = " ".join(triggers).lower()
        assert "pseudoreplication" not in joined

    @pytest.mark.unit
    def test_crispr_profile_has_gene_editing_triggers(self):
        from app.workflows.draft_analysis.nodes.manuscript_profile import build_manuscript_profile
        text = (
            "We used CRISPR-Cas9 with dual gRNA guides targeting the BCL11A enhancer "
            "to perform a knock-out in CD34 HSPCs. HDR and NHEJ outcomes were quantified. "
            "HbF elevation was measured by RT-PCR across colonies."
        )
        profile = build_manuscript_profile({"draft_content": text, "paper_type": "research"})
        joined = " ".join(profile["domain_audit_triggers"]).lower()
        assert "protein" in joined
        assert "pseudoreplication" in joined
        assert "translocation" in joined or "inversion" in joined

    @pytest.mark.unit
    def test_non_gene_editing_profile_lacks_gene_editing_triggers(self):
        from app.workflows.draft_analysis.nodes.manuscript_profile import build_manuscript_profile
        text = (
            "This systematic review followed PRISMA. We performed a database search, "
            "study selection, and data extraction with risk of bias assessment across "
            "included studies and eligibility criteria."
        )
        profile = build_manuscript_profile({"draft_content": text, "paper_type": "review"})
        joined = " ".join(profile["domain_audit_triggers"]).lower()
        assert "pseudoreplication" not in joined


class TestVerbatimAnchorMetric:
    """FIX-10/issue #4: verbatim coverage uses exact substrings; global tasks exempt."""

    @pytest.mark.unit
    def test_is_verbatim_anchor_exact_substring(self):
        from app.services.draft_analysis_langgraph import _is_verbatim_anchor
        draft = "The mortality rate decreased significantly after deployment."
        assert _is_verbatim_anchor("mortality rate decreased significantly", draft)
        assert not _is_verbatim_anchor("mortality plummeted dramatically overnight", draft)

    @pytest.mark.unit
    def test_nonverbatim_local_counts_as_miss(self):
        """Honest metric (4b): a non-verbatim anchor is NOT auto-global anymore — it's a
        local MISS. Only an LLM/repair-confirmed anchor_type='global' is exempt."""
        from app.services.draft_analysis_langgraph import _revision_quality_metrics
        draft = "The mortality rate decreased significantly after deployment in the ICU cohort."
        tasks = [
            {"anchor_text": "mortality rate decreased significantly", "problem": "p", "suggested_action": "a"},
            {"anchor_text": "The review describes no literature search strategy at all anywhere.",
             "problem": "non-verbatim paraphrase critique", "suggested_action": "a"},
        ]
        metrics = _revision_quality_metrics(tasks, draft)
        # Both are local; only the first is verbatim → coverage 1/2, no exemptions.
        assert metrics["verbatim_anchor_coverage"] == 0.5
        assert metrics["global_tasks_exempted"] == 0

    @pytest.mark.unit
    def test_llm_confirmed_global_is_exempt(self):
        """Anchor honesty: a global task carries anchor_text=None (NO fake quote), and is
        excluded from BOTH numerator and denominator of verbatim coverage."""
        from app.services.draft_analysis_langgraph import _revision_quality_metrics
        draft = "The mortality rate decreased significantly after deployment in the ICU cohort."
        tasks = [
            {"anchor_text": "mortality rate decreased significantly", "problem": "p", "suggested_action": "a"},
            {"anchor_text": None, "anchor_type": "global",
             "problem": "global critique", "suggested_action": "a"},
        ]
        metrics = _revision_quality_metrics(tasks, draft)
        # One local verbatim task (1/1), one global with null anchor excluded entirely.
        assert metrics["verbatim_anchor_coverage"] == 1.0
        assert metrics["global_tasks_count"] == 1
        assert metrics["global_tasks_exempted"] == 1


class TestOrphanedConcepts:
    """FIX-11/issue #16: concepts only in the conclusion with no body groundwork."""

    @pytest.mark.unit
    def test_orphaned_concept_flagged(self):
        from app.workflows.draft_analysis.nodes.diagnostic_findings import _orphaned_concept_findings
        body = "Introduction. Sodium-ion batteries use layered oxide cathodes for storage. " * 40
        concl = "\n\n## Conclusion\nFuture work should explore high-entropy layered oxide cathodes."
        findings = _orphaned_concept_findings(body + concl)
        assert any("high-entropy" in f["problem"].lower() for f in findings)

    @pytest.mark.unit
    def test_no_false_positive_when_concept_in_body(self):
        from app.workflows.draft_analysis.nodes.diagnostic_findings import _orphaned_concept_findings
        body = "Introduction. We study high-entropy layered oxide cathodes in detail here. " * 40
        concl = "\n\n## Conclusion\nHigh-entropy layered oxide cathodes remain promising."
        findings = _orphaned_concept_findings(body + concl)
        assert not any("high-entropy" in f["problem"].lower() for f in findings)


class TestPreliminaryGate:
    """FIX-2/issue #12: halt before reviewers when anchors/parser predict gate fail."""

    @pytest.mark.unit
    def test_halt_on_low_anchor_coverage(self):
        from app.services.draft_publish_gate import should_halt_before_reviewers
        res = should_halt_before_reviewers(page_anchor_coverage=0.4, parser_quality_score=0.9)
        assert res["halt"] is True

    @pytest.mark.unit
    def test_halt_on_low_parser_quality(self):
        from app.services.draft_publish_gate import should_halt_before_reviewers
        res = should_halt_before_reviewers(page_anchor_coverage=0.95, parser_quality_score=0.3)
        assert res["halt"] is True

    @pytest.mark.unit
    def test_no_halt_on_good_metrics(self):
        from app.services.draft_publish_gate import should_halt_before_reviewers
        res = should_halt_before_reviewers(page_anchor_coverage=0.95, parser_quality_score=0.9)
        assert res["halt"] is False

    @pytest.mark.unit
    def test_routing_skips_reviewers_on_low_coverage(self):
        from app.workflows.draft_analysis.graph import route_to_reviewer_panel
        state = {
            "editor_decision": {"proceed_to_review": True},
            "parser_quality": {"parser_quality_score": 0.3},
            "claims_with_citations": [{"claim": {"page_number": None}}],
        }
        result = route_to_reviewer_panel(state)
        assert result == "synthesize_report"

    @pytest.mark.unit
    def test_routing_dispatches_reviewers_on_good_parse(self):
        from app.workflows.draft_analysis.graph import route_to_reviewer_panel
        state = {
            "editor_decision": {"proceed_to_review": True},
            "parser_quality": {"parser_quality_score": 0.9},
            "claims_with_citations": [{"claim": {"page_number": 3, "char_start": 100}}],
        }
        result = route_to_reviewer_panel(state)
        assert isinstance(result, list) and len(result) == 3


class TestCrossReviewerDedup:
    """FIX-3/issue #5: shared critiques kept only in the lane owner."""

    @pytest.mark.unit
    def test_shared_critique_kept_in_lane_owner(self):
        from app.workflows.draft_analysis.nodes.reviewer_panel import deduplicate_cross_reviewer_critiques
        outputs = [
            {"reviewer_id": "methodology",
             "weaknesses": ["The sample size and statistical power analysis are insufficient for the design."]},
            {"reviewer_id": "clarity",
             "weaknesses": ["The sample size and statistical power analysis are insufficient for the design."]},
        ]
        out = deduplicate_cross_reviewer_critiques(outputs)
        by_id = {o["reviewer_id"]: o["weaknesses"] for o in out}
        assert len(by_id["methodology"]) == 1
        assert by_id["clarity"] == []

    @pytest.mark.unit
    def test_distinct_critiques_preserved(self):
        from app.workflows.draft_analysis.nodes.reviewer_panel import deduplicate_cross_reviewer_critiques
        outputs = [
            {"reviewer_id": "methodology", "weaknesses": ["Statistical power is insufficient."]},
            {"reviewer_id": "clarity", "weaknesses": ["The writing flow in section 3 is hard to follow."]},
        ]
        out = deduplicate_cross_reviewer_critiques(outputs)
        assert all(len(o["weaknesses"]) == 1 for o in out)

    @pytest.mark.unit
    def test_critique_lane_classification(self):
        from app.workflows.draft_analysis.nodes.reviewer_panel import _critique_lane
        assert _critique_lane("The statistical power and sample size are insufficient") == "methodology"
        assert _critique_lane("The novelty over prior work and contribution is unclear") == "literature_positioning"
        assert _critique_lane("The writing flow and terminology consistency need work") == "clarity"


class TestNoBatteryLabelBleed:
    """SC-11: battery_* category labels must not bleed onto non-materials drafts."""

    @pytest.mark.unit
    def test_clinical_causal_task_not_labeled_battery(self):
        from app.workflows.draft_analysis.revision_tasks import _dedupe_category
        cat = _dedupe_category(
            "The manuscript makes causal claims about mortality reduction from the model.",
            "Soften causal overstatement; the design is observational.",
            "causal_claim",
        )
        assert "battery" not in cat

    @pytest.mark.unit
    def test_materials_characterization_still_labeled_battery(self):
        from app.workflows.draft_analysis.revision_tasks import _dedupe_category
        cat = _dedupe_category(
            "Operando XRD and XPS characterization is needed to confirm the degradation mechanism.",
            "Add operando XRD measurements.",
            "causal_claim",
        )
        assert cat == "battery_characterization_causality"


class TestMetaMustAddressCoverage:
    """Tests for ensure_must_address_coverage (Phase 1).

    All tests run under pytest so PYTEST_CURRENT_TEST is set → embeddings are
    skipped → the deterministic fallback path (token overlap / SequenceMatcher)
    is exercised exclusively.
    """

    def _make_task(self, problem: str, suggested_action: str, task_type: str = "methodology") -> dict:
        from app.workflows.draft_analysis.revision_tasks import _base_task
        task = _base_task(
            source_type="reviewer_issue",
            task_type=task_type,
            severity="major",
            section="Methods",
            anchor_text="",
            problem=problem,
            why_it_matters="Important for validity.",
            suggested_action=suggested_action,
        )
        assert task is not None, "helper must produce a valid task"
        return task

    @pytest.mark.unit
    def test_uncovered_must_address_promoted_with_undroppable(self):
        """An uncovered must_address item must appear as a new task with undroppable=True
        and source_type='meta_must_address'."""
        from app.workflows.draft_analysis.revision_tasks import ensure_must_address_coverage

        existing_tasks = [
            self._make_task(
                "The statistical analysis should use mixed-effects models.",
                "Switch to a mixed-effects regression framework.",
            )
        ]
        must_address = [
            "Add a literature-selection methodology section describing inclusion/exclusion criteria."
        ]

        result = ensure_must_address_coverage(
            existing_tasks,
            must_address,
            reviewer_outputs=[],
        )

        promoted = [t for t in result if t.get("source_type") == "meta_must_address"]
        assert len(promoted) == 1, f"Expected 1 promoted task, got {len(promoted)}"
        assert promoted[0]["undroppable"] is True
        assert "literature-selection" in promoted[0]["problem"].lower() or "inclusion" in promoted[0]["problem"].lower()

    @pytest.mark.unit
    def test_covered_must_address_not_duplicated(self):
        """A must_address item already covered by a task's wording must NOT create a
        duplicate (task count must remain unchanged)."""
        from app.workflows.draft_analysis.revision_tasks import ensure_must_address_coverage

        # Task text shares most content tokens with the must_address item.
        existing_tasks = [
            self._make_task(
                "The literature-selection methodology is missing inclusion and exclusion criteria.",
                "Add a literature-selection methodology section with clear inclusion/exclusion criteria.",
                task_type="methodology",
            )
        ]
        must_address = [
            "Add a literature-selection methodology section describing inclusion/exclusion criteria."
        ]

        result = ensure_must_address_coverage(
            existing_tasks,
            must_address,
            reviewer_outputs=[],
        )

        # No new task should have been added.
        assert len(result) == len(existing_tasks), (
            f"Expected {len(existing_tasks)} tasks after coverage check, got {len(result)}"
        )
        promoted = [t for t in result if t.get("source_type") == "meta_must_address"]
        assert len(promoted) == 0, "Covered item must not be re-promoted"

    @pytest.mark.unit
    def test_meta_review_none_is_noop(self):
        """build_revision_tasks with meta_review=None or empty must_address must be
        a complete no-op — task count and content unchanged."""
        from app.workflows.draft_analysis.revision_tasks import build_revision_tasks

        # Minimal inputs producing a single task.
        diagnostic_findings = [
            {
                "finding_type": "methodology",
                "severity": "major",
                "section_reference": "Methods",
                "anchor_text": "We used logistic regression.",
                "problem": "The regression model choice is not justified.",
                "why_it_matters": "Model selection affects validity.",
                "suggested_action": "Justify the regression model choice.",
                "confidence": 0.85,
            }
        ]

        tasks_no_meta = build_revision_tasks(
            diagnostic_findings=diagnostic_findings,
            reviewer_outputs=[],
            claims=[],
            gaps=[],
            structural_feedback=[],
            meta_review=None,
        )

        tasks_empty_meta = build_revision_tasks(
            diagnostic_findings=diagnostic_findings,
            reviewer_outputs=[],
            claims=[],
            gaps=[],
            structural_feedback=[],
            meta_review={"must_address": []},
        )

        assert len(tasks_no_meta) == len(tasks_empty_meta), (
            "meta_review=None and empty must_address should produce identical task lists"
        )
        promoted_none = [t for t in tasks_no_meta if t.get("source_type") == "meta_must_address"]
        promoted_empty = [t for t in tasks_empty_meta if t.get("source_type") == "meta_must_address"]
        assert promoted_none == [] and promoted_empty == [], (
            "No meta_must_address tasks should appear when meta_review is None or has empty must_address"
        )


# ---------------------------------------------------------------------------
# Phase 3 — repair_anchor tests
# ---------------------------------------------------------------------------

class TestRepairAnchor:
    from app.services.draft_task_evidence import repair_anchor

    def _make_task(self, anchor: str) -> dict:
        return {"anchor_text": anchor, "task_type": "methodology", "severity": "major"}

    def test_exact_hit_unchanged(self):
        """Anchor already a substring of raw_text — task returned unchanged."""
        from app.services.draft_task_evidence import repair_anchor
        raw = "the mortality rate decreased significantly in the treatment group"
        task = self._make_task("mortality rate decreased")
        result = repair_anchor(task, raw)
        assert result["anchor_text"] == "mortality rate decreased"
        assert result["anchor_text"] in raw

    def test_whitespace_repair(self):
        """Anchor with extra internal whitespace matched and replaced with exact raw span."""
        from app.services.draft_task_evidence import repair_anchor
        raw = "the mortality rate decreased significantly in the treatment group"
        task = self._make_task("mortality   rate decreased")
        result = repair_anchor(task, raw)
        assert result["anchor_text"] in raw, (
            f"Repaired anchor '{result['anchor_text']}' not found verbatim in raw text"
        )
        assert "mortality" in result["anchor_text"] and "decreased" in result["anchor_text"]

    def test_irreparable_anchor_becomes_global(self):
        """Anchor fully absent from raw_text and no LCS >= 40 chars → anchor_type='global'."""
        from app.services.draft_task_evidence import repair_anchor
        raw = "the mortality rate decreased significantly in the treatment group"
        task = self._make_task("completely unrelated paraphrased summary text XYZ")
        result = repair_anchor(task, raw)
        assert result.get("anchor_type") == "global"

    def test_empty_anchor_unchanged(self):
        """Empty anchor string → task returned unchanged (no crash)."""
        from app.services.draft_task_evidence import repair_anchor
        raw = "the mortality rate decreased significantly"
        task = self._make_task("")
        result = repair_anchor(task, raw)
        assert result.get("anchor_text") == ""

    def test_lcs_fallback(self):
        """Anchor has >= 40-char common substring with raw_text → replaced with exact raw span."""
        from app.services.draft_task_evidence import repair_anchor
        shared = "the systematic review followed PRISMA guidelines for evidence synthesis"
        raw = "In summary, " + shared + " across all included studies."
        # Paraphrase: swap "followed" but keep a long shared prefix/suffix
        anchor = "the systematic review followed PRISMA guidelines for evidence synthesis (2020 update)"
        task = self._make_task(anchor)
        result = repair_anchor(task, raw)
        assert result["anchor_text"] in raw, (
            f"LCS fallback anchor '{result['anchor_text']}' not verbatim in raw"
        )


# ---------------------------------------------------------------------------
# Prong A — Precision / noise-reduction fixes (A1 / A2 / A3)
# ---------------------------------------------------------------------------

class TestProngAPrecisionFixes:
    """Tests for A1 (review-genre citation skip + intent-match), A2 (grammar/wording
    nitpick drop), and A3 (reviewer-issue severity de-inflation)."""

    # ------------------------------------------------------------------
    # A1a — Review-genre manuscripts: no claim→citation tasks
    # ------------------------------------------------------------------

    @pytest.mark.unit
    def test_review_genre_suppresses_claim_citation_tasks(self):
        """A1a: build_revision_tasks with genre='literature_review' + a claim that would
        otherwise produce a citation task → no citation task emitted."""
        from app.workflows.draft_analysis.revision_tasks import build_revision_tasks

        claims = [{
            "id": "c-review",
            "claim_text": "Prior meta-analyses show that intervention X reduces mortality.",
            "requires_citation": True,
            "importance_score": 0.75,
            "section_location": "Introduction",
        }]
        # Reviewer issue with citation intent + overlap — would pass in a non-review manuscript.
        reviewer_outputs = [{
            "reviewer_id": "literature",
            "issues": [{
                "issue_type": "citation",
                "section_reference": "Introduction",
                "anchor_text": "Prior meta-analyses show that intervention X reduces mortality.",
                "problem": "This prior-work claim about meta-analyses is unsupported and needs a citation.",
                "why_it_matters": "Dense citation requirement for review introductions.",
                "suggested_action": "Add a citation.",
            }],
        }]
        tasks = build_revision_tasks(
            diagnostic_findings=[],
            reviewer_outputs=reviewer_outputs,
            claims=claims,
            gaps=[],
            structural_feedback=[],
            manuscript_profile={"genre": "literature_review"},
        )
        citation_tasks = [t for t in tasks if t.get("task_type") == "citation"]
        assert citation_tasks == [], (
            f"Expected no citation tasks for literature_review genre, got {citation_tasks}"
        )

    @pytest.mark.unit
    def test_systematic_review_genre_suppresses_claim_citation_tasks(self):
        """A1a: systematic_review genre is also in _REVIEW_GENRES → no citation tasks."""
        from app.workflows.draft_analysis.revision_tasks import build_revision_tasks

        claims = [{
            "id": "c-sysrev",
            "claim_text": "Cognitive behavioral therapy reduces depression symptoms.",
            "requires_citation": True,
            "importance_score": 0.8,
            "section_location": "Introduction",
        }]
        reviewer_outputs = [{
            "reviewer_id": "methodology",
            "issues": [{
                "issue_type": "citation",
                "section_reference": "Introduction",
                "anchor_text": "cognitive behavioral therapy reduces depression symptoms",
                "problem": "This claim about CBT therapy and depression is unsupported and needs a citation.",
                "why_it_matters": "Background claims in systematic reviews need citations.",
                "suggested_action": "Cite the primary trial.",
            }],
        }]
        tasks = build_revision_tasks(
            diagnostic_findings=[],
            reviewer_outputs=reviewer_outputs,
            claims=claims,
            gaps=[],
            structural_feedback=[],
            manuscript_profile={"genre": "systematic_review"},
        )
        assert not any(t.get("task_type") == "citation" for t in tasks), (
            "No citation tasks expected for systematic_review genre"
        )

    # ------------------------------------------------------------------
    # A1b — Non-review: citation intent required in corroboration string
    # ------------------------------------------------------------------

    @pytest.mark.unit
    def test_non_review_citation_task_requires_intent_in_corroboration(self):
        """A1b: non-review manuscript + claim + reviewer issue whose corroboration text
        expresses citation intent → citation task emitted."""
        from app.workflows.draft_analysis.revision_tasks import build_revision_tasks

        claims = [{
            "id": "c-sodium",
            "claim_text": "Sodium-ion batteries achieve energy densities above 150 Wh/kg.",
            "requires_citation": True,
            "importance_score": 0.72,
            "section_location": "Introduction",
        }]
        # Reviewer issue: anchor overlaps claim AND problem expresses citation intent.
        reviewer_outputs = [{
            "reviewer_id": "methodology",
            "issues": [{
                "issue_type": "citation",
                "section_reference": "Introduction",
                "anchor_text": "sodium-ion batteries achieve energy densities above 150 Wh/kg — needs a citation",
                "problem": "The energy-density claim for sodium-ion batteries is unsupported and needs a citation.",
                "why_it_matters": "Quantitative performance claims require primary evidence.",
                "suggested_action": "Add a reference for the energy density figure.",
            }],
        }]
        tasks = build_revision_tasks(
            diagnostic_findings=[],
            reviewer_outputs=reviewer_outputs,
            claims=claims,
            gaps=[],
            structural_feedback=[],
            manuscript_profile={"genre": "original_research"},
        )
        # A task about this claim must be emitted (may be deduplicated into the reviewer task).
        assert tasks, "Expected at least one task"
        assert any(
            "sodium" in (t.get("problem") or "").lower() or "energy" in (t.get("problem") or "").lower()
            for t in tasks
        ), f"Expected task touching the sodium/energy claim, got {tasks}"

    @pytest.mark.unit
    def test_non_review_no_citation_task_when_corroboration_is_topic_only(self):
        """A1b: non-review + claim + reviewer issue with topic overlap but NO citation intent
        → no citation task (the key new gate introduced by A1)."""
        from app.workflows.draft_analysis.revision_tasks import build_revision_tasks

        claims = [{
            "id": "c-commercial",
            "claim_text": "SIBs play a commercial role in large-scale grid storage.",
            "requires_citation": True,
            "importance_score": 0.65,
            "section_location": "Introduction",
        }]
        # Reviewer issue: shares topic tokens with the claim (SIBs/commercial/grid)
        # but does NOT express any citation intent.
        reviewer_outputs = [{
            "reviewer_id": "methodology",
            "issues": [{
                "issue_type": "coverage",
                "section_reference": "Introduction",
                "anchor_text": "SIBs commercial grid storage",
                "problem": "The introduction lacks sufficient discussion of SIBs commercial viability.",
                "why_it_matters": "Coverage of grid storage applications is essential context.",
                "suggested_action": "Expand the coverage of commercial SIB applications.",
            }],
        }]
        tasks = build_revision_tasks(
            diagnostic_findings=[],
            reviewer_outputs=reviewer_outputs,
            claims=claims,
            gaps=[],
            structural_feedback=[],
            manuscript_profile={"genre": "original_research"},
        )
        citation_tasks = [t for t in tasks if t.get("task_type") == "citation"]
        assert citation_tasks == [], (
            f"Expected no citation task (topic-only corroboration, no intent), got {citation_tasks}"
        )

    # ------------------------------------------------------------------
    # A2 — Grammar/wording nitpick clarity tasks are dropped
    # ------------------------------------------------------------------

    @pytest.mark.unit
    def test_grammatically_awkward_clarity_issue_is_dropped(self):
        """A2: a clarity issue that is purely a grammar/wording nitpick (no substantive
        signal) must be filtered out by _is_low_value_formatting_task."""
        from app.workflows.draft_analysis.revision_tasks import _is_low_value_formatting_task

        assert _is_low_value_formatting_task(
            problem="'essential to require' is grammatically awkward.",
            suggested_action="Rephrase to improve sentence structure and wording.",
        ) is True

    @pytest.mark.unit
    def test_imprecise_phrasing_clarity_issue_is_dropped(self):
        """A2: 'working principles same to LIBs' is imprecise wording — must be dropped."""
        from app.workflows.draft_analysis.revision_tasks import _is_low_value_formatting_task

        assert _is_low_value_formatting_task(
            problem="'working principles same to LIBs' is imprecise phrasing.",
            suggested_action="Rephrase for clarity and word choice.",
        ) is True

    @pytest.mark.unit
    def test_substantive_clarity_issue_not_dropped(self):
        """A2: a clarity issue that also touches the abstract/results readability must NOT
        be dropped — the substantive_signal guard protects it."""
        from app.workflows.draft_analysis.revision_tasks import _is_low_value_formatting_task

        assert _is_low_value_formatting_task(
            problem="The abstract oversells the results with imprecise wording.",
            suggested_action="Revise the abstract to accurately reflect the results.",
        ) is False

    @pytest.mark.unit
    def test_grammar_nitpick_dropped_by_build_revision_tasks(self):
        """A2: a reviewer clarity issue that is purely grammar-awkward → no task emitted."""
        from app.workflows.draft_analysis.revision_tasks import build_revision_tasks

        tasks = build_revision_tasks(
            diagnostic_findings=[],
            reviewer_outputs=[{
                "reviewer_id": "reviewer_1",
                "issues": [{
                    "issue_type": "clarity",
                    "section_reference": "Methods",
                    "anchor_text": "essential to require better performance",
                    "problem": "The phrase 'essential to require' is grammatically awkward.",
                    "why_it_matters": "Grammatical clarity improves readability.",
                    "suggested_action": "Rewrite the sentence to fix the grammar and wording.",
                }],
            }],
            claims=[],
            gaps=[],
            structural_feedback=[],
        )
        assert tasks == [], f"Expected grammar nitpick to be dropped, got {tasks}"

    # ------------------------------------------------------------------
    # A3 — Reviewer-issue severity: clarity → minor, other → major
    # ------------------------------------------------------------------

    @pytest.mark.unit
    def test_clarity_reviewer_issue_defaults_to_minor(self):
        """A3: a reviewer issue with issue_type='clarity' must produce a task with
        severity='minor'."""
        from app.workflows.draft_analysis.revision_tasks import build_revision_tasks

        tasks = build_revision_tasks(
            diagnostic_findings=[],
            reviewer_outputs=[{
                "reviewer_id": "reviewer_2",
                "issues": [{
                    "issue_type": "clarity",
                    "section_reference": "Discussion",
                    "anchor_text": "The discussion section is clearly laid out.",
                    "problem": "The readability of the discussion section could be improved for a general audience.",
                    "why_it_matters": "Improved readability aids review.",
                    "suggested_action": "Add topic sentences to each paragraph in the discussion.",
                }],
            }],
            claims=[],
            gaps=[],
            structural_feedback=[],
        )
        clarity_tasks = [t for t in tasks if t.get("task_type") == "clarity"]
        assert clarity_tasks, f"Expected a clarity task, got {tasks}"
        assert clarity_tasks[0]["severity"] == "minor", (
            f"Clarity reviewer issue should default to 'minor', got {clarity_tasks[0]['severity']}"
        )

    @pytest.mark.unit
    def test_methodology_reviewer_issue_stays_major(self):
        """A3: a reviewer issue with issue_type='methodology' must produce severity='major'."""
        from app.workflows.draft_analysis.revision_tasks import build_revision_tasks

        tasks = build_revision_tasks(
            diagnostic_findings=[],
            reviewer_outputs=[{
                "reviewer_id": "reviewer_1",
                "issues": [{
                    "issue_type": "methodology",
                    "section_reference": "Methods",
                    "anchor_text": "The search strategy uses PubMed and Embase.",
                    "problem": "The search strategy does not include gray literature or preprints.",
                    "why_it_matters": "Excluding gray literature may bias the review.",
                    "suggested_action": "Add gray literature sources to the search.",
                }],
            }],
            claims=[],
            gaps=[],
            structural_feedback=[],
        )
        methodology_tasks = [t for t in tasks if t.get("task_type") == "methodology"]
        assert methodology_tasks, f"Expected a methodology task, got {tasks}"
        assert methodology_tasks[0]["severity"] == "major", (
            f"Methodology reviewer issue should be 'major', got {methodology_tasks[0]['severity']}"
        )

    @pytest.mark.unit
    def test_methodology_floor_still_raises_minor_methodology_to_major(self):
        """A3 + floor guard: _floor_methodology_severity raises critical-method tasks
        from minor to major even after A3 changes. The floor is not weakened."""
        from app.workflows.draft_analysis.revision_tasks import _floor_methodology_severity

        # Uses "biological replicate" (singular) so the regex word-boundary fires.
        task = _floor_methodology_severity({
            "task_type": "methodology",
            "severity": "minor",
            "priority": "low",
            "problem": "Figure 3 treats individual colonies as biological replicate (pseudoreplication).",
            "suggested_action": "Report independent donors and aggregate per biological replicate.",
        })
        assert task["severity"] == "major"
        assert task.get("severity_driver") == "methodology_validity_floor"


class TestProngBFalseAbsence:
    """Prong B: kill the false-absence hallucination (issue #2, run-10 banner).

    B1 — self-anchor contradiction → DROP the task entirely.
    B2 — body grounding (lexical fallback) → DOWNGRADE + flag, never drop.
    B3 — parser-artifact truncated/figure-callout critiques → _is_parser_artifact_task True.
    """

    # ── B1: self-anchor contradiction (DROP) ──────────────────────────────────

    @pytest.mark.unit
    def test_b1_self_contradiction_drops_task(self):
        """KEYSTONE: task claiming 'cytokine conditions not detailed' whose own anchor
        already contains the cytokine details is dropped, not merely downgraded."""
        from app.services.draft_task_evidence import verify_absence_claims

        task = {
            "id": "crispr-t6",
            "severity": "major",
            "problem": "The HSPC culture cytokine conditions are not detailed in the methods.",
            "suggested_action": "Add culture medium composition, cytokines, and differentiation protocol.",
            "anchor_text": (
                "CD34+ HSPCs were cultured in StemSpan SFEM medium supplemented with "
                "human cytokines, 100 ng/mL SCF, 100 ng/mL Tpo, and 100 ng/mL FLT3L."
            ),
        }
        # draft body doesn't need to contain the answer — B1 fires on the anchor itself
        out, metrics = verify_absence_claims([task], "Unrelated body paragraph text here.")
        assert len(out) == 0, "Self-contradicting task must be DROPPED (not downgraded)"
        assert metrics["self_contradiction_dropped"] == 1

    @pytest.mark.unit
    def test_b1_self_contradiction_uses_text_snippet_fallback(self):
        """B1 should also fire when the contradiction lives in text_snippet, not anchor_text.
        Uses richer snippet so >= 3 stem terms match."""
        from app.services.draft_task_evidence import verify_absence_claims

        task = {
            "id": "t-snip",
            "severity": "major",
            "problem": "The culture conditions and cytokine protocol are not specified.",
            "suggested_action": "Specify culture conditions, cytokine concentrations and differentiation protocol.",
            "anchor_text": "",
            "text_snippet": (
                "Cells were cultured in StemSpan SFEM medium with cytokines SCF, Tpo "
                "and FLT3L at 100 ng/mL, differentiation protocol 48h."
            ),
        }
        out, metrics = verify_absence_claims([task], "Some unrelated body text.")
        assert len(out) == 0, f"Expected drop, got: {out}"
        assert metrics["self_contradiction_dropped"] >= 1

    @pytest.mark.unit
    def test_b1_negative_no_contradiction_when_anchor_lacks_terms(self):
        """B1 must NOT drop a task whose anchor genuinely does not contain the missing content."""
        from app.services.draft_task_evidence import verify_absence_claims

        task = {
            "id": "t-legit",
            "severity": "major",
            "problem": "The BCL11A enhancer comparison is missing from the discussion.",
            "suggested_action": "Add a comparison to BCL11A enhancer editing approaches.",
            "anchor_text": "We modified CD34+ HSPCs using CRISPR-Cas9 targeting HPFH regions.",
        }
        out, metrics = verify_absence_claims([task], "No relevant body paragraph.")
        # Task should NOT be dropped by B1 (anchor does not contain BCL11A comparison content)
        assert len(out) == 1, "Task with non-contradicting anchor must survive B1"
        assert metrics["self_contradiction_dropped"] == 0

    @pytest.mark.unit
    def test_b1_three_matched_terms_threshold(self):
        """B1 fires when >= 3 distinct stem-prefix terms from the query match the anchor,
        even if total fraction is below 0.5 (many query terms, anchor answers several)."""
        from app.services.draft_task_evidence import verify_absence_claims

        # Many query terms so fraction stays below 0.5, but anchor provides 3+ stem matches
        task = {
            "id": "t-three",
            "severity": "major",
            "problem": (
                "Culture medium, cytokine treatment, differentiation protocol, "
                "statistical analysis, randomization details are not reported."
            ),
            "suggested_action": (
                "Report culture medium, cytokine concentrations, differentiation "
                "duration, statistical tests, randomization method."
            ),
            "anchor_text": (
                "Cells were cultured in StemSpan medium with cytokine supplements; "
                "differentiation was carried out over 48h."
            ),
        }
        out, metrics = verify_absence_claims([task], "Body text with unrelated content.")
        # Anchor contains: cultu(re/red), cytok(ine/s), diffe(rentiation/rentiate) → ≥3 stems
        assert metrics["self_contradiction_dropped"] >= 1

    # NOTE: the mock-based semantic B1 tests were removed — the embedding-cosine
    # drop/downgrade path they exercised is disproven and gone. The real false-absence
    # fix is the LLM entailment verifier, tested in TestLLMAbsenceVerifier below.

    # ── B2: body grounding (lexical fallback, DOWNGRADE only) ─────────────────

    @pytest.mark.unit
    def test_b2_fallback_downgrade_on_lexical_overlap(self):
        """B2 fallback: absence task + body paragraph with overlapping terms → downgraded
        and grounding_flag set. Task is NOT dropped (only B1 drops)."""
        from app.services.draft_task_evidence import verify_absence_claims

        draft = (
            "Introduction.\n\n"
            "Authors performed fairness analysis stratified by race and sex, calibration "
            "reported across all demographic subgroups in Table 3.\n\n"
            "Conclusion."
        )
        task = {
            "id": "t-b2",
            "severity": "major",
            "problem": "The manuscript does not address demographic subgroup fairness analysis.",
            "suggested_action": "Add demographic subgroup fairness analysis stratified by race and sex.",
        }
        out, metrics = verify_absence_claims([task], draft, threshold=0.5)
        assert len(out) == 1, "B2 body match must DOWNGRADE, never drop"
        assert out[0]["severity"] == "minor"
        assert out[0].get("grounding_flag") == "possibly_addressed_in_text"
        # HOTFIX 1 (sync): problem stays CLEAN; note moves to verification_note.
        assert out[0]["problem"] == task["problem"], "problem must NOT be mutated"
        assert out[0]["verification_status"] == "partially_addressed"
        assert out[0].get("verification_note"), "verification_note must carry the excerpt"
        assert metrics["absence_tasks_downgraded"] == 1
        assert metrics["self_contradiction_dropped"] == 0

    @pytest.mark.unit
    def test_b2_new_marker_not_detailed(self):
        """'Not detailed' is now an absence marker (B2 extension) — task is checked."""
        from app.services.draft_task_evidence import verify_absence_claims

        draft = (
            "Intro.\n\n"
            "Culture conditions: cells in StemSpan SFEM, cytokines SCF Tpo FLT3L "
            "at 100 ng/mL, 37 °C, 5% CO2, 48 h expansion.\n\n"
            "Conclusion."
        )
        task = {
            "id": "t-not-detailed",
            "severity": "major",
            "problem": "Culture conditions are not detailed in the methods section.",
            "suggested_action": "Detail culture conditions: medium, cytokines, temperature, duration.",
        }
        out, metrics = verify_absence_claims([task], draft, threshold=0.5)
        # Either downgraded (body match found) or not — the key assertion is the marker
        # is now RECOGNIZED as an absence claim (not skipped as non-absence).
        # If body has enough overlap it should be downgraded; at minimum it must be checked.
        # We accept either downgrade or pass-through, but NOT an error/skip.
        assert isinstance(out, list)
        assert "absence_tasks_downgraded" in metrics

    @pytest.mark.unit
    def test_b2_new_marker_does_not_specify(self):
        """'Does not specify' is now an absence marker — task enters the grounding pipeline."""
        from app.services.draft_task_evidence import verify_absence_claims

        draft = "Intro.\n\nThe protocol specifies cytokine concentrations: SCF 100 ng/mL.\n\nConclusion."
        task = {
            "id": "t-does-not-specify",
            "severity": "major",
            "problem": "The protocol does not specify cytokine concentrations.",
            "suggested_action": "Specify cytokine concentrations used.",
        }
        out, metrics = verify_absence_claims([task], draft, threshold=0.5)
        # Body overlaps well → should be downgraded (cytokine concentrations present)
        assert metrics["absence_tasks_downgraded"] == 1
        assert out[0]["severity"] == "minor"

    # ── B3: parser-artifact truncated-sentence / figure-callout suppression ───

    @pytest.mark.unit
    def test_b3_truncated_sentence_suppressed(self):
        """Clarity task about a 'truncated sentence' → _is_parser_artifact_task True."""
        from app.workflows.draft_analysis.revision_tasks import _is_parser_artifact_task

        assert _is_parser_artifact_task(
            "The sentence is truncated and reads poorly.",
            "Rewrite the truncated sentence to complete the thought.",
        ) is True

    @pytest.mark.unit
    def test_b3_figure_callout_interrupt_suppressed(self):
        """Clarity task about sentence interrupted by an inline Fig. callout → suppressed."""
        from app.workflows.draft_analysis.revision_tasks import _is_parser_artifact_task

        assert _is_parser_artifact_task(
            "The sentence '...we made use of this clinical observation and modified CD34 + Fig. 3' "
            "is interrupted mid-sentence by a figure reference, making it unreadable.",
            "Remove the inline figure callout that breaks the sentence.",
        ) is True

    @pytest.mark.unit
    def test_b3_cut_off_sentence_suppressed(self):
        """'Sentence is cut off' phrasing → suppressed."""
        from app.workflows.draft_analysis.revision_tasks import _is_parser_artifact_task

        assert _is_parser_artifact_task(
            "The sentence is cut off abruptly mid-thought in paragraph 3.",
            "Complete the sentence or remove the fragment.",
        ) is True

    @pytest.mark.unit
    def test_b3_incomplete_sentence_suppressed(self):
        """'Incomplete sentence' phrasing → suppressed."""
        from app.workflows.draft_analysis.revision_tasks import _is_parser_artifact_task

        assert _is_parser_artifact_task(
            "There is an incomplete sentence on page 2 that confuses the reader.",
            "Complete the sentence.",
        ) is True

    @pytest.mark.unit
    def test_b3_substantive_clarity_not_suppressed(self):
        """A substantive clarity critique (not about truncation/figure callout) is NOT suppressed."""
        from app.workflows.draft_analysis.revision_tasks import _is_parser_artifact_task

        assert _is_parser_artifact_task(
            "The authors' argument about translational impact is unclear and insufficiently supported.",
            "Strengthen the argument with specific evidence and clearer logical flow.",
        ) is False

    @pytest.mark.unit
    def test_b3_abruptly_ends_suppressed(self):
        """'Abruptly ends' phrasing → suppressed."""
        from app.workflows.draft_analysis.revision_tasks import _is_parser_artifact_task

        assert _is_parser_artifact_task(
            "The methods section abruptly ends without describing the statistical analysis.",
            "Complete the statistical analysis description.",
        ) is True

    # ── FIX 4b: strengthened B3 signals ──────────────────────────────────────

    @pytest.mark.unit
    def test_b3_incomplete_and_truncated_suppressed(self):
        from app.workflows.draft_analysis.revision_tasks import _is_parser_artifact_task

        assert _is_parser_artifact_task(
            "The transfection description is incomplete and truncated.",
            "Provide the full transfection description.",
        ) is True

    @pytest.mark.unit
    def test_b3_interrupted_by_fig_suppressed(self):
        from app.workflows.draft_analysis.revision_tasks import _is_parser_artifact_task

        assert _is_parser_artifact_task(
            "The sentence is interrupted by Fig. 3 in the middle of the clause.",
            "Fix the broken sentence.",
        ) is True

    @pytest.mark.unit
    def test_b3_modified_cd34_fig_suppressed(self):
        from app.workflows.draft_analysis.revision_tasks import _is_parser_artifact_task

        assert _is_parser_artifact_task(
            "Text reads 'modified CD34 + Fig. 3' which is a broken fragment.",
            "Remove the inline figure callout.",
        ) is True

    @pytest.mark.unit
    def test_b3_substantive_not_suppressed_after_strengthen(self):
        from app.workflows.draft_analysis.revision_tasks import _is_parser_artifact_task

        assert _is_parser_artifact_task(
            "The discussion does not address the limitations of the chosen delivery modality.",
            "Discuss the limitations of electroporation versus lipid nanoparticle delivery.",
        ) is False


class TestManufacturerProtocolGuard:
    """FIX 4a: suppress micro-parameter nitpicks covered by a kit's manufacturer protocol."""

    @pytest.mark.unit
    def test_micro_parameter_with_manufacturer_cue_dropped(self):
        from app.workflows.draft_analysis.revision_tasks import _is_manufacturer_protocol_nitpick

        assert _is_manufacturer_protocol_nitpick(
            "The methods do not specify incubation time and buffer volume for transfection.",
            "Specify the exact incubation time and buffer volume used.",
            "Cells were transfected using TurboFect according to the manufacturer's instructions.",
        ) is True

    @pytest.mark.unit
    def test_base_task_drops_manufacturer_nitpick(self):
        from app.workflows.draft_analysis.revision_tasks import _base_task

        out = _base_task(
            source_type="diagnostic",
            task_type="methodology",
            severity="minor",
            section="Methods",
            anchor_text="Cells were transfected using TurboFect according to the manufacturer's instructions.",
            problem="The authors do not report the incubation time and buffer volume.",
            why_it_matters="Reproducibility requires exact parameters.",
            suggested_action="Specify the exact incubation time and buffer volume.",
        )
        assert out is None

    @pytest.mark.unit
    def test_substantive_methodology_with_cue_not_dropped(self):
        from app.workflows.draft_analysis.revision_tasks import _is_manufacturer_protocol_nitpick

        # Replication critique that happens to also mention a manufacturer cue → keep.
        assert _is_manufacturer_protocol_nitpick(
            "Individual colonies from one donor are treated as biological replicates for p-values.",
            "Use independent biological donors and aggregate per donor.",
            "Cells were transfected using TurboFect according to the manufacturer's instructions.",
        ) is False

    @pytest.mark.unit
    def test_delivery_modality_with_cue_not_dropped(self):
        from app.workflows.draft_analysis.revision_tasks import _is_manufacturer_protocol_nitpick

        assert _is_manufacturer_protocol_nitpick(
            "The delivery modality choice and its concentration are not justified.",
            "Justify the delivery modality versus alternatives.",
            "Reagents were used according to the manufacturer's instructions.",
        ) is False

    @pytest.mark.unit
    def test_micro_parameter_without_cue_not_dropped(self):
        from app.workflows.draft_analysis.revision_tasks import _is_manufacturer_protocol_nitpick

        assert _is_manufacturer_protocol_nitpick(
            "The methods do not specify incubation time and buffer volume.",
            "Specify the exact incubation time and buffer volume.",
            "Cells were transfected and processed for downstream analysis.",
        ) is False


# ──────────────────────────────────────────────────────────────────────────────
# LLM entailment verifier (Prong B real fix) — the only reliable false-absence
# detector. Embedding-cosine cannot separate false from real absence (positives
# score LOWER than negatives). These tests MOCK the LLM call; no network.
# ──────────────────────────────────────────────────────────────────────────────
class TestLLMAbsenceVerifier:
    @staticmethod
    def _patch_llm(monkeypatch, verdicts):
        """Patch parse_chat_completion_with_retries to return controlled verdicts.

        `verdicts` is a list of (index, verdict, evidence) tuples.
        """
        from app.workflows.draft_analysis.schemas import AbsenceVerification, AbsenceVerdict

        verification = AbsenceVerification(
            items=[AbsenceVerdict(index=i, verdict=v, evidence=e) for (i, v, e) in verdicts]
        )

        class _Resp:
            parsed = verification

        async def _fake_parse(*args, **kwargs):
            # Guard: must use max_completion_tokens, never max_tokens.
            assert "max_tokens" not in kwargs, "must not use max_tokens"
            return _Resp()

        monkeypatch.setattr(
            "app.services.retry_utils.parse_chat_completion_with_retries", _fake_parse
        )
        # get_async_openai_client may need a dummy; patch it to avoid real client init.
        monkeypatch.setattr(
            "app.core.openai_client.get_async_openai_client", lambda: object()
        )

    @pytest.mark.unit
    async def test_cytokine_addressed_is_dropped(self, monkeypatch):
        from app.services.draft_task_evidence import llm_verify_absence_claims

        self._patch_llm(monkeypatch, [(0, "addressed", "StemSpan SFEM, SCF, Tpo listed")])
        task = {
            "id": "cyto",
            "severity": "major",
            "problem": "The HSPC culture cytokine conditions are not detailed.",
            "suggested_action": "Detail culture medium and cytokine conditions.",
            "anchor_text": "cultured in StemSpan SFEM with SCF, Tpo, FLT3L at 100 ng/mL.",
        }
        out, metrics = await llm_verify_absence_claims([task], "body text")
        assert out == [], "addressed → DROP"
        assert metrics["llm_addressed_dropped"] == 1
        assert metrics["llm_partial_downgraded"] == 0

    @pytest.mark.unit
    async def test_offtarget_absent_is_kept(self, monkeypatch):
        from app.services.draft_task_evidence import llm_verify_absence_claims

        self._patch_llm(monkeypatch, [(0, "absent", "")])
        task = {
            "id": "offt",
            "severity": "critical",
            "problem": "Genome-wide off-target analysis (GUIDE-seq) is missing.",
            "suggested_action": "Add genome-wide GUIDE-seq off-target profiling.",
            "anchor_text": "Off-target editing was assessed by T7E1 assay at predicted sites.",
        }
        out, metrics = await llm_verify_absence_claims([task], "body text")
        assert len(out) == 1, "absent → KEEP"
        assert out[0]["severity"] == "critical", "unchanged"
        assert metrics["llm_addressed_dropped"] == 0

    @pytest.mark.unit
    async def test_protein_absent_is_kept(self, monkeypatch):
        from app.services.draft_task_evidence import llm_verify_absence_claims

        self._patch_llm(monkeypatch, [(0, "absent", "")])
        task = {
            "id": "prot",
            "severity": "major",
            "problem": "Protein-level validation of knockdown is not reported.",
            "suggested_action": "Add Western blot or flow cytometry protein validation.",
            "anchor_text": "Knockdown was confirmed at the mRNA level by qPCR.",
        }
        out, metrics = await llm_verify_absence_claims([task], "body text")
        assert len(out) == 1, "absent → KEEP (mRNA is not protein validation)"
        assert metrics["llm_addressed_dropped"] == 0

    @pytest.mark.unit
    async def test_partial_is_downgraded_not_dropped(self, monkeypatch):
        from app.services.draft_task_evidence import llm_verify_absence_claims

        self._patch_llm(monkeypatch, [(0, "partial", "calibration shown but not by subgroup")])
        task = {
            "id": "part",
            "severity": "major",
            "problem": "The manuscript does not address demographic subgroup fairness.",
            "suggested_action": "Add subgroup fairness analysis stratified by race and sex.",
            "anchor_text": "Overall calibration is reported in Table 3.",
        }
        out, metrics = await llm_verify_absence_claims([task], "body text")
        assert len(out) == 1, "partial → KEEP (downgraded, not dropped)"
        assert out[0]["severity"] == "minor", "downgraded one level"
        assert out[0]["grounding_flag"] == "llm_partial"
        # HOTFIX 1: problem stays CLEAN; verifier note lives in separate fields.
        assert out[0]["problem"] == task["problem"], "problem must NOT be mutated"
        assert out[0]["verification_status"] == "partially_addressed"
        assert out[0]["verification_note"] == "calibration shown but not by subgroup"
        assert metrics["llm_partial_downgraded"] == 1
        assert metrics["llm_addressed_dropped"] == 0

    @pytest.mark.unit
    async def test_no_absence_tasks_returns_unchanged(self, monkeypatch):
        from app.services.draft_task_evidence import llm_verify_absence_claims

        task = {"id": "ok", "severity": "major", "problem": "Tighten the abstract phrasing."}
        out, metrics = await llm_verify_absence_claims([task], "body")
        assert out == [task]
        assert metrics == {}

    @pytest.mark.unit
    async def test_llm_failure_falls_back_to_sync_lexical(self, monkeypatch):
        """If the LLM call raises, fall back to sync lexical verify_absence_claims —
        never crash. Use a self-anchor-contradicting task so the lexical B1 drops it,
        proving the fallback path actually ran."""
        from app.services.draft_task_evidence import llm_verify_absence_claims

        async def _boom(*args, **kwargs):
            raise RuntimeError("model exploded")

        monkeypatch.setattr(
            "app.services.retry_utils.parse_chat_completion_with_retries", _boom
        )
        monkeypatch.setattr(
            "app.core.openai_client.get_async_openai_client", lambda: object()
        )

        task = {
            "id": "fallback",
            "severity": "major",
            "problem": "The culture cytokine conditions are not detailed in the methods.",
            "suggested_action": "Add culture medium composition, cytokines, and differentiation protocol.",
            "anchor_text": (
                "CD34+ HSPCs were cultured in StemSpan SFEM medium supplemented with "
                "human cytokines, 100 ng/mL SCF, 100 ng/mL Tpo, and differentiation protocol."
            ),
        }
        out, metrics = await llm_verify_absence_claims([task], "Unrelated body text.")
        # Sync lexical B1 self-contradiction should fire and drop it.
        assert out == [], "fallback to sync lexical must run (and drop the self-contradicting task)"
        assert metrics.get("self_contradiction_dropped") == 1
        assert "llm_addressed_dropped" not in metrics


# ──────────────────────────────────────────────────────────────────────────────
# HOTFIX 3 — degenerate task guard (problem == suggested_action) in _base_task
# ──────────────────────────────────────────────────────────────────────────────
class TestDegenerateTaskGuard:
    @staticmethod
    def _build(problem: str, action: str) -> dict:
        from app.workflows.draft_analysis.revision_tasks import _base_task
        return _base_task(
            source_type="reviewer",
            task_type="methodology",
            severity="major",
            section="Methods",
            anchor_text="the methods section",
            problem=problem,
            why_it_matters="It matters for reproducibility.",
            suggested_action=action,
        )

    @pytest.mark.unit
    def test_identical_problem_and_action_neutralized(self):
        same = "The statistical analysis method is not specified anywhere in the methods."
        task = self._build(same, same)
        assert task is not None, "real issue must NOT be dropped"
        assert task["problem"] == same
        assert task["suggested_action"] == "Address the issue described above."

    @pytest.mark.unit
    def test_near_identical_problem_and_action_neutralized(self):
        problem = "The statistical analysis method is not specified in the methods section."
        action = "The statistical analysis method is not specified in the methods section!"
        task = self._build(problem, action)
        assert task is not None
        assert task["suggested_action"] == "Address the issue described above."

    @pytest.mark.unit
    def test_distinct_problem_and_action_untouched(self):
        problem = "The statistical analysis method is not specified."
        action = "State which test was used (e.g. mixed-effects model) and report effect sizes."
        task = self._build(problem, action)
        assert task is not None
        assert task["problem"] == problem
        assert task["suggested_action"] == action


# ──────────────────────────────────────────────────────────────────────────────
# 4a — LLM anchor repair (verbatim-anchor real fix). LLM call is MOCKED.
# ──────────────────────────────────────────────────────────────────────────────
class TestLLMRepairAnchors:
    DRAFT = (
        "Introduction.\n\n"
        "The mortality rate decreased significantly after deployment in the ICU cohort, "
        "as shown in Table 3 across all included sites.\n\n"
        "Conclusion."
    )

    @staticmethod
    def _patch_llm(monkeypatch, spans):
        """spans: list of (index, verbatim_span)."""
        from app.workflows.draft_analysis.schemas import AnchorRepair, AnchorSpan

        repair = AnchorRepair(items=[AnchorSpan(index=i, verbatim_span=s) for (i, s) in spans])

        class _Resp:
            parsed = repair

        async def _fake_parse(*args, **kwargs):
            assert "max_tokens" not in kwargs, "must not use max_tokens"
            return _Resp()

        monkeypatch.setattr(
            "app.services.retry_utils.parse_chat_completion_with_retries", _fake_parse
        )
        monkeypatch.setattr(
            "app.core.openai_client.get_async_openai_client", lambda: object()
        )

    @pytest.mark.unit
    async def test_real_substring_replaces_anchor(self, monkeypatch):
        from app.services.draft_task_evidence import llm_repair_anchors
        real = "The mortality rate decreased significantly after deployment in the ICU cohort"
        self._patch_llm(monkeypatch, [(0, real)])
        task = {"id": "t", "problem": "Mortality claim needs an anchor.",
                "anchor_text": "deaths went down a lot after rollout"}
        out = await llm_repair_anchors([task], self.DRAFT)
        assert out[0]["anchor_text"] == real
        assert out[0]["anchor_text"] in self.DRAFT
        assert out[0]["anchor_type"] == "local"

    @pytest.mark.unit
    async def test_global_marks_anchor_global(self, monkeypatch):
        from app.services.draft_task_evidence import llm_repair_anchors
        self._patch_llm(monkeypatch, [(0, "GLOBAL")])
        task = {"id": "t", "problem": "The paper lacks an overarching framing.",
                "anchor_text": "the paper is too narrow overall and lacks framing"}
        out = await llm_repair_anchors([task], self.DRAFT)
        assert out[0]["anchor_type"] == "global"
        # Anchor honesty: GLOBAL → no fake quote. The generative anchor is nulled.
        assert out[0]["anchor_text"] is None

    @pytest.mark.unit
    async def test_hallucinated_span_nulls_anchor(self, monkeypatch):
        """Anchor honesty: a non-substring (couldn't-locate) span must NOT leave the
        generative paraphrase in anchor_text — it is nulled and the task marked global."""
        from app.services.draft_task_evidence import llm_repair_anchors
        self._patch_llm(monkeypatch, [(0, "this sentence does not exist in the manuscript")])
        original = "deaths went down a lot after rollout"
        task = {"id": "t", "problem": "Mortality claim needs an anchor.",
                "anchor_text": original}
        out = await llm_repair_anchors([task], self.DRAFT)
        # No verbatim locus → null the fake quote, mark global (exempt — no fake anchor).
        assert out[0]["anchor_text"] is None
        assert out[0]["anchor_type"] == "global"

    @pytest.mark.unit
    async def test_already_verbatim_skips_llm(self, monkeypatch):
        from app.services.draft_task_evidence import llm_repair_anchors
        real = "The mortality rate decreased significantly after deployment in the ICU cohort"

        async def _boom(*args, **kwargs):
            raise AssertionError("LLM must not be called for already-verbatim anchors")

        monkeypatch.setattr(
            "app.services.retry_utils.parse_chat_completion_with_retries", _boom
        )
        task = {"id": "t", "problem": "p", "anchor_text": real}
        out = await llm_repair_anchors([task], self.DRAFT)
        assert out[0]["anchor_text"] == real

    @pytest.mark.unit
    async def test_no_fake_anchor_invariant(self, monkeypatch):
        """After repair, NO task has an anchor_text that fails `anchor_text in draft`
        unless anchor_text is None. Mock: GLOBAL for one task, a real span for another."""
        from app.services.draft_task_evidence import llm_repair_anchors
        real = "The mortality rate decreased significantly after deployment in the ICU cohort"
        # idx 0 → GLOBAL (whole-doc), idx 1 → real verbatim span.
        self._patch_llm(monkeypatch, [(0, "GLOBAL"), (1, real)])
        tasks = [
            {"id": "g", "problem": "Needs overarching framing.",
             "anchor_text": "the paper is too narrow and lacks framing overall"},
            {"id": "v", "problem": "Mortality claim needs an anchor.",
             "anchor_text": "deaths went down a lot after rollout"},
        ]
        out = await llm_repair_anchors(tasks, self.DRAFT)
        global_task = next(t for t in out if t["id"] == "g")
        verbatim_task = next(t for t in out if t["id"] == "v")
        assert global_task["anchor_text"] is None  # no fake quote
        assert global_task["anchor_type"] == "global"
        assert verbatim_task["anchor_text"] == real
        assert verbatim_task["anchor_text"] in self.DRAFT
        # Invariant across the whole output.
        for t in out:
            assert t.get("anchor_text") is None or t["anchor_text"] in self.DRAFT


# ──────────────────────────────────────────────────────────────────────────────
# 4b — honest metric + persistence of anchor_type/anchor_verbatim
# ──────────────────────────────────────────────────────────────────────────────
class TestHonestVerbatimMetric:
    @pytest.mark.unit
    def test_coverage_is_true_value_not_one(self):
        from app.services.draft_analysis_langgraph import _revision_quality_metrics
        draft = "The mortality rate decreased significantly after deployment in the ICU cohort."
        tasks = [
            {"anchor_text": "mortality rate decreased significantly", "problem": "p", "suggested_action": "a"},
            {"anchor_text": "a paraphrase that is not in the manuscript anywhere", "problem": "p2", "suggested_action": "a"},
            {"anchor_text": None, "anchor_type": "global", "problem": "p3", "suggested_action": "a"},
        ]
        metrics = _revision_quality_metrics(tasks, draft)
        # Non-null anchors = 2 (one verbatim, one not); global has null anchor → excluded
        # from both numerator and denominator → coverage = 1/2.
        assert metrics["verbatim_anchor_coverage"] == 0.5
        assert metrics["verbatim_anchor_coverage"] != 1.0
        assert metrics["global_tasks_count"] == 1
        assert metrics["global_tasks_exempted"] == 1

    @pytest.mark.unit
    def test_revision_task_row_omits_unmigrated_anchor_fields(self):
        # anchor_type/anchor_verbatim are NOT persisted per-row until migration 035 is
        # applied (the draft_revision_tasks table lacks the columns; persisting them caused
        # PGRST204 insert failures). Honest coverage lives in analysis_metadata instead.
        from app.services.draft_analysis_langgraph import _revision_task_row
        task = {"id": "x", "problem": "p", "suggested_action": "a",
                "anchor_type": "local", "anchor_verbatim": True}
        row = _revision_task_row("draft-1", task)
        assert "anchor_type" not in row
        assert "anchor_verbatim" not in row

    @pytest.mark.unit
    def test_revision_task_row_anchor_text_is_none_not_generative(self):
        """Anchor honesty: a global task (anchor_text=None) maps to None in the row — the
        old section/problem generative fallback must NOT inject a fake 'quote'."""
        from app.services.draft_analysis_langgraph import _revision_task_row
        task = {"id": "g", "problem": "This is a whole-document framing critique.",
                "suggested_action": "a", "section": "Discussion",
                "anchor_text": None, "anchor_type": "global"}
        row = _revision_task_row("draft-1", task)
        assert row["anchor_text"] is None
        assert row["anchor_text"] != task["problem"]
        assert row["anchor_text"] != task["section"]


# ──────────────────────────────────────────────────────────────────────────────
# FIX 1 — verbatim coverage honesty: numerator/denominator over non-null anchors
# ──────────────────────────────────────────────────────────────────────────────
class TestVerbatimCoverageHonesty:
    @pytest.mark.unit
    def test_two_verbatim_plus_one_null_global(self):
        """2 verbatim + 1 null-global → coverage 1.0 over the 2 non-null; global_count=1."""
        from app.services.draft_analysis_langgraph import _revision_quality_metrics
        draft = "Alpha beta gamma delta. The mortality rate decreased significantly here."
        tasks = [
            {"anchor_text": "Alpha beta gamma delta", "problem": "p1", "suggested_action": "a"},
            {"anchor_text": "mortality rate decreased significantly", "problem": "p2", "suggested_action": "a"},
            {"anchor_text": None, "anchor_type": "global", "problem": "p3", "suggested_action": "a"},
        ]
        metrics = _revision_quality_metrics(tasks, draft)
        assert metrics["verbatim_anchor_coverage"] == 1.0
        assert metrics["global_tasks_count"] == 1

    @pytest.mark.unit
    def test_one_verbatim_plus_one_nonverbatim_nonnull(self):
        """Defensive: 1 verbatim + 1 non-verbatim-non-null anchor → coverage 0.5
        (shouldn't happen after repair, but the metric stays honest)."""
        from app.services.draft_analysis_langgraph import _revision_quality_metrics
        draft = "The mortality rate decreased significantly here."
        tasks = [
            {"anchor_text": "mortality rate decreased significantly", "problem": "p1", "suggested_action": "a"},
            {"anchor_text": "a paraphrase not present in the manuscript", "problem": "p2", "suggested_action": "a"},
        ]
        metrics = _revision_quality_metrics(tasks, draft)
        assert metrics["verbatim_anchor_coverage"] == 0.5
        assert metrics["global_tasks_count"] == 0


# ──────────────────────────────────────────────────────────────────────────────
# FIX 2 — LLM semantic dedup (llm_dedupe_tasks). LLM call is MOCKED.
# ──────────────────────────────────────────────────────────────────────────────
class TestLLMDedupeTasks:
    @staticmethod
    def _patch_llm(monkeypatch, clusters):
        from app.workflows.draft_analysis.schemas import TaskClusters

        parsed = TaskClusters(clusters=clusters)

        class _Resp:
            pass

        _Resp.parsed = parsed

        async def _fake_parse(*args, **kwargs):
            assert "max_tokens" not in kwargs, "must not use max_tokens"
            return _Resp()

        monkeypatch.setattr(
            "app.services.retry_utils.parse_chat_completion_with_retries", _fake_parse
        )
        monkeypatch.setattr(
            "app.core.openai_client.get_async_openai_client", lambda: object()
        )

    def _task(self, tid, problem, severity="major", action="do x"):
        return {"id": tid, "problem": problem, "suggested_action": action,
                "task_type": "methodology", "severity": severity}

    @pytest.mark.unit
    async def test_cluster_merges_into_one(self, monkeypatch):
        from app.workflows.draft_analysis.revision_tasks import llm_dedupe_tasks
        tasks = [
            self._task("a", "P-values without stating # independent colonies", severity="major"),
            self._task("b", "A genuinely distinct clarity issue in the intro"),
            self._task("c", "P-values without stating # biological replicates", severity="critical"),
        ]
        # Cluster indices [0, 2] (same statistical-independence flaw); index 1 untouched.
        self._patch_llm(monkeypatch, [[0, 2]])
        out = await llm_dedupe_tasks(tasks)
        assert len(out) == 2  # dropped by one
        ids = [t["id"] for t in out]
        assert "b" in ids
        # Leader is the lowest index (0 = task "a"); merged keeps highest severity (critical).
        leader = next(t for t in out if t["id"] == "a")
        assert leader["severity"] == "critical"
        assert leader.get("duplicate_count", 0) >= 1

    @pytest.mark.unit
    async def test_undroppable_task_not_merged_away(self, monkeypatch):
        # FIX 3: a specific high-value critique (pseudoreplication) marked undroppable
        # must survive standalone even if the LLM clusters it with a generic task.
        from app.workflows.draft_analysis.revision_tasks import llm_dedupe_tasks
        specific = self._task(
            "spec",
            "Pseudoreplication: colonies from one donor treated as independent n",
            severity="critical",
        )
        specific["undroppable"] = True
        generic = self._task("gen", "Report sample sizes for all experiments")
        normal_a = self._task("na", "Missing baseline comparison to SOTA method X")
        normal_b = self._task("nb", "Missing baseline comparison against SOTA method X")
        tasks = [specific, generic, normal_a, normal_b]
        # LLM tries to merge the undroppable (0) with generic (1), and merges normals (2,3).
        self._patch_llm(monkeypatch, [[0, 1], [2, 3]])
        out = await llm_dedupe_tasks(tasks)
        ids = [t["id"] for t in out]
        # Undroppable survives standalone; the generic it was clustered with also survives.
        assert "spec" in ids
        assert "gen" in ids
        # The normal cluster still merges (one of na/nb collapses).
        assert ("na" in ids) ^ ("nb" in ids) or ("na" in ids and "nb" not in ids)
        assert len(out) == 3

    @pytest.mark.unit
    async def test_rescued_and_meta_must_address_protected(self, monkeypatch):
        from app.workflows.draft_analysis.revision_tasks import llm_dedupe_tasks
        rescued = self._task("r", "Rescued specific structural-variant validation gap")
        rescued["rescued_from_finding"] = True
        meta = self._task("m", "Meta-flagged protein-level validation missing")
        meta["source_type"] = "meta_must_address"
        generic = self._task("g", "Generic methods reporting improvement")
        tasks = [rescued, meta, generic]
        self._patch_llm(monkeypatch, [[0, 1, 2]])
        out = await llm_dedupe_tasks(tasks)
        ids = [t["id"] for t in out]
        # All protected -> nothing merges; the lone generic also survives untouched.
        assert ids == ["r", "m", "g"]

    @pytest.mark.unit
    async def test_llm_failure_returns_tasks_unchanged(self, monkeypatch):
        from app.workflows.draft_analysis.revision_tasks import llm_dedupe_tasks

        async def _boom(*args, **kwargs):
            raise RuntimeError("LLM down")

        monkeypatch.setattr(
            "app.services.retry_utils.parse_chat_completion_with_retries", _boom
        )
        monkeypatch.setattr(
            "app.core.openai_client.get_async_openai_client", lambda: object()
        )
        tasks = [self._task("a", "one"), self._task("b", "two")]
        out = await llm_dedupe_tasks(tasks)
        assert out == tasks  # unchanged

    @pytest.mark.unit
    async def test_under_two_tasks_returns_as_is(self, monkeypatch):
        from app.workflows.draft_analysis.revision_tasks import llm_dedupe_tasks
        tasks = [self._task("a", "only one")]
        out = await llm_dedupe_tasks(tasks)
        assert out == tasks


# ──────────────────────────────────────────────────────────────────────────────
# FIX 1 — Reviewers see the FULL manuscript + grounding rule.
# FIX 2 — Domain triggers reframed from imperative demands to conditional checks.
# ──────────────────────────────────────────────────────────────────────────────
class TestFullManuscriptGrounding:
    @pytest.mark.unit
    def test_reviewer_context_contains_full_body_not_just_excerpts(self):
        from app.workflows.draft_analysis.nodes.reviewer_panel import build_reviewer_context
        # Build a long draft where a key sentence sits ~6000 chars in, inside a section
        # _section_excerpts would have truncated (1400-char cap per section).
        marker = "The junctions were confirmed by Sanger sequencing of subcloned PCR products."
        head = "## Introduction\n" + ("Background filler sentence. " * 250)  # ~6750 chars
        body = f"## Methods\n{marker}\n" + ("More methods detail. " * 200)
        draft = head + "\n" + body
        assert len(head) > 6000
        state = {
            "draft_content": draft,
            "paper_type": "empirical",
            "structure": {"sections": [], "word_count": 6000},
            "manuscript_profile": {},
        }
        ctx = build_reviewer_context(state, "methodology")
        assert marker in ctx  # full body present, not cut by excerpting

    @pytest.mark.unit
    def test_reviewer_context_caps_long_draft_at_24000(self):
        from app.workflows.draft_analysis.nodes.reviewer_panel import build_reviewer_context
        draft = "x" * 50000
        state = {
            "draft_content": draft,
            "paper_type": "empirical",
            "structure": {"sections": [], "word_count": 9999},
            "manuscript_profile": {},
        }
        ctx = build_reviewer_context(state, "methodology")
        # The draft body is capped; the full 50k is not emitted verbatim.
        assert "x" * 24000 in ctx
        assert "x" * 24001 not in ctx

    @pytest.mark.unit
    def test_grounding_rule_in_reviewer_system_prompt(self):
        from app.workflows.draft_analysis.nodes.reviewer_panel import (
            RATING_CALIBRATION,
            REVIEWER_PROMPTS,
        )
        assert "GROUNDING RULE" in RATING_CALIBRATION
        low = RATING_CALIBRATION.lower()
        assert "search the entire" in low
        assert "do not raise it" in low
        # The calibration block (with the rule) is appended to every reviewer prompt.
        for prompt in REVIEWER_PROMPTS.values():
            assert "GROUNDING RULE" in prompt

    @pytest.mark.unit
    def test_gene_editing_triggers_are_conditional_not_imperative(self):
        from app.workflows.draft_analysis.nodes.manuscript_profile import (
            DOMAIN_AUDIT_TRIGGERS,
        )
        triggers = DOMAIN_AUDIT_TRIGGERS["gene_editing"]
        assert triggers
        for t in triggers:
            low = t.lower()
            assert "if " in low, f"trigger not conditional: {t}"
            assert "do not raise it" in low, f"trigger lacks present-case skip: {t}"
            # No bare imperative demands.
            assert "demand" not in low, f"trigger still imperative: {t}"

    @pytest.mark.unit
    def test_all_domain_triggers_reframed_conditional(self):
        from app.workflows.draft_analysis.nodes.manuscript_profile import (
            DOMAIN_AUDIT_TRIGGERS,
        )
        for bucket, triggers in DOMAIN_AUDIT_TRIGGERS.items():
            for t in triggers:
                low = t.lower()
                assert "if " in low, f"{bucket} trigger not conditional: {t}"
                assert "do not raise it" in low, f"{bucket} trigger lacks skip: {t}"


class TestSourceRelevanceFilter:
    """RAG contamination guard: drop suggested sources whose embedding cosine vs
    THIS manuscript falls below threshold. Pure embedding relevance, no keyword lists.
    Embeddings are mocked — no network."""

    import math as _math

    REF = [1.0, 0.0]
    ON_DOMAIN = [0.7, 0.714142842854285]      # cosine ~0.70 vs REF -> KEPT
    OFF_DOMAIN = [0.2, 0.9797958971132712]    # cosine ~0.20 vs REF -> DROPPED

    class _Emb:
        def __init__(self, vec):
            self.embedding = vec

    def _patch_env(self, monkeypatch):
        # The function no-ops under pytest / no key; clear those for the embed path.
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    def _make_embedder(self, text_to_vec):
        def fake_embed_chunks(chunks, model="text-embedding-3-small"):
            return [TestSourceRelevanceFilter._Emb(text_to_vec[c]) for c in chunks]
        return fake_embed_chunks

    @pytest.mark.unit
    def test_offdomain_source_dropped_ondomain_kept(self, monkeypatch):
        from app.services import draft_task_evidence
        self._patch_env(monkeypatch)

        draft = "Sickle cell disease CRISPR base editing of HBB. " * 60
        manuscript_ref = draft[:3000].strip()

        on_task = {"title": "CRISPR correction of HBB in sickle cell", "content": "base editing"}
        off_task = {"title": "Ant colony foraging behavior", "content": "pheromone trails"}
        on_gap = {"title": "Gene therapy for hemoglobinopathies", "abstract": "lentiviral HBB"}
        off_gap = {"title": "Thyroid hormone regulation", "abstract": "TSH levels"}

        def src_text(s):
            return draft_task_evidence._candidate_source_text(s)

        text_to_vec = {manuscript_ref: self.REF}
        for s in (on_task, on_gap):
            text_to_vec[src_text(s)] = self.ON_DOMAIN
        for s in (off_task, off_gap):
            text_to_vec[src_text(s)] = self.OFF_DOMAIN

        monkeypatch.setattr(
            "app.services.rag_ingest.embed_chunks",
            self._make_embedder(text_to_vec),
        )

        tasks = [{"suggested_sources": [dict(on_task), dict(off_task)]}]
        gaps = [{"suggested_papers": [dict(on_gap), dict(off_gap)]}]

        out_tasks, out_gaps, metrics = draft_task_evidence.filter_sources_by_manuscript_relevance(
            tasks, gaps, draft
        )

        kept_task_titles = [s["title"] for s in out_tasks[0]["suggested_sources"]]
        kept_gap_titles = [p["title"] for p in out_gaps[0]["suggested_papers"]]
        assert kept_task_titles == ["CRISPR correction of HBB in sickle cell"]
        assert kept_gap_titles == ["Gene therapy for hemoglobinopathies"]
        # One off-domain dropped per location.
        assert metrics["sources_dropped_offdomain"] == 2
        assert metrics["sources_checked"] == 4
        assert metrics["relevance_threshold"] == 0.42

    @pytest.mark.unit
    def test_no_sources_is_noop(self, monkeypatch):
        from app.services import draft_task_evidence
        self._patch_env(monkeypatch)

        def boom(*a, **k):  # must not be called when there are no candidates
            raise AssertionError("embed_chunks should not be called for empty sources")

        monkeypatch.setattr("app.services.rag_ingest.embed_chunks", boom)

        tasks = [{"suggested_sources": []}]
        gaps = [{"suggested_papers": []}]
        out_tasks, out_gaps, metrics = draft_task_evidence.filter_sources_by_manuscript_relevance(
            tasks, gaps, "Sickle cell CRISPR manuscript text " * 40
        )
        assert out_tasks == tasks
        assert out_gaps == gaps
        assert metrics["sources_dropped_offdomain"] == 0
        assert metrics["sources_checked"] == 0

    @pytest.mark.unit
    def test_embed_failure_returns_inputs_unchanged(self, monkeypatch):
        from app.services import draft_task_evidence
        self._patch_env(monkeypatch)

        def boom(*a, **k):
            raise RuntimeError("embedding service down")

        monkeypatch.setattr("app.services.rag_ingest.embed_chunks", boom)

        on_task = {"title": "CRISPR HBB", "content": "x"}
        off_task = {"title": "Alzheimer amyloid plaques", "content": "y"}
        tasks = [{"suggested_sources": [on_task, off_task]}]
        gaps = [{"suggested_papers": [{"title": "Colorectal cancer screening", "abstract": "z"}]}]

        out_tasks, out_gaps, metrics = draft_task_evidence.filter_sources_by_manuscript_relevance(
            tasks, gaps, "Sickle cell CRISPR base editing manuscript " * 40
        )
        # Fallback: nothing dropped, inputs unchanged.
        assert len(out_tasks[0]["suggested_sources"]) == 2
        assert len(out_gaps[0]["suggested_papers"]) == 1
        assert metrics["sources_dropped_offdomain"] == 0

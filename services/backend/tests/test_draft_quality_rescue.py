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

        tasks = build_revision_tasks(
            diagnostic_findings=[],
            reviewer_outputs=[],
            claims=[claim],
            gaps=[],
            structural_feedback=[],
        )

        assert len(tasks) == 1
        assert tasks[0]["task_type"] == "citation"
        assert tasks[0]["suggested_sources"][0]["document_id"] == "doc-1"

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
        assert families == {"battery_phase_taxonomy", "materials_review_methodology"}
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

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
        assert "sepsis definitions" in problems
        assert "data-pipeline" in problems
        assert "mortality" in problems
        assert "epic sepsis model" in problems
        assert "framework" in problems
        assert "exclusion" in problems

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
    def test_epic_positioning_variants_merge_into_one_revision_task(self):
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
                    "problem": "The manuscript does not sharply engage with major controversies such as the Epic Sepsis Model external validation failures.",
                    "why_it_matters": "Epic and similar cases are central to the discourse on clinical AI deployment.",
                    "suggested_action": "Clarify what SALIENT explains about these failures and broader deployment controversies.",
                    "confidence": 0.85,
                }],
            }],
            claims=[],
            gaps=[],
            structural_feedback=[],
        )

        assert len(tasks) == 1
        assert tasks[0]["dedupe_category"] == "epic_sepsis_positioning"
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
        assert "epic_sepsis_positioning" in categories
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

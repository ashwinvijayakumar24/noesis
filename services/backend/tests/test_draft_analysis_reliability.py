from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _mock_openai_client(monkeypatch):
    from app.core import openai_client

    monkeypatch.setattr(openai_client, "get_openai_client", lambda: MagicMock())
    monkeypatch.setattr(openai_client, "get_async_openai_client", lambda: MagicMock())


class FakeResponse:
    def __init__(self, data=None, count=None):
        self.data = data
        self.count = count if count is not None else (len(data) if isinstance(data, list) else None)


class FakeTable:
    def __init__(self, supabase, name):
        self.supabase = supabase
        self.name = name
        self.action = "select"
        self.filters = []
        self.negative_filters = []
        self.in_filters = []
        self.payload = None
        self._limit = None
        self._single = False

    def _rows(self):
        return self.supabase.tables.setdefault(self.name, [])

    def select(self, *_args, **_kwargs):
        self.action = "select"
        return self

    def insert(self, payload):
        self.action = "insert"
        self.payload = payload
        return self

    def upsert(self, payload, *args, **kwargs):
        self.action = "upsert"
        self.payload = payload
        return self

    def update(self, payload):
        self.action = "update"
        self.payload = payload
        return self

    def delete(self):
        self.action = "delete"
        return self

    def eq(self, field, value):
        self.filters.append((field, value))
        return self

    def neq(self, field, value):
        self.negative_filters.append((field, value))
        return self

    def in_(self, field, values):
        self.in_filters.append((field, set(values)))
        return self

    def limit(self, value):
        self._limit = value
        return self

    def single(self):
        self._single = True
        return self

    def _matches(self, row):
        return (
            all(row.get(field) == value for field, value in self.filters)
            and all(row.get(field) != value for field, value in self.negative_filters)
            and all(row.get(field) in values for field, values in self.in_filters)
        )

    def _filtered_rows(self):
        rows = [row for row in self._rows() if self._matches(row)]
        if self._limit is not None:
            rows = rows[: self._limit]
        return rows

    def _row_with_id(self, payload):
        return {"id": payload.get("id") or f"{self.name}-{len(self._rows()) + 1}", **payload}

    def execute(self):
        rows = self._filtered_rows()

        if self.action == "select":
            if self._single:
                return FakeResponse(rows[0] if rows else None, count=len(rows))
            return FakeResponse(rows, count=len(rows))

        if self.action == "insert":
            payloads = self.payload if isinstance(self.payload, list) else [self.payload]
            inserted = []
            for payload in payloads:
                row = self._row_with_id(payload)
                self._rows().append(row)
                inserted.append(row)
            return FakeResponse(inserted, count=len(inserted))

        if self.action == "upsert":
            payload = self.payload
            match_field = "draft_id" if "draft_id" in payload else "id"
            for row in self._rows():
                if row.get(match_field) == payload.get(match_field):
                    row.update(payload)
                    return FakeResponse([row], count=1)
            row = self._row_with_id(payload)
            self._rows().append(row)
            return FakeResponse([row], count=1)

        if self.action == "update":
            updated = []
            for row in self._rows():
                if self._matches(row):
                    row.update(self.payload)
                    updated.append(row)
            return FakeResponse(updated, count=len(updated))

        if self.action == "delete":
            deleted = rows
            self.supabase.tables[self.name] = [row for row in self._rows() if not self._matches(row)]
            return FakeResponse(deleted, count=len(deleted))

        return FakeResponse([])


class FakeSupabase:
    def __init__(self, tables=None):
        self.tables = tables or {}

    def table(self, name):
        return FakeTable(self, name)


class TestDraftClaimAnchoring:
    @pytest.mark.unit
    def test_map_citations_to_claims_exact_anchor_sets_high_confidence_with_section(self):
        from app.services.claim_analysis import map_citations_to_claims

        draft_text = (
            "Introduction\n"
            "Federated learning improves privacy for hospital models.\n"
            "Methods\n"
            "We evaluate three baselines."
        )
        claim_text = "Federated learning improves privacy for hospital models."

        claims = [{"claim_text": claim_text, "section_location": "Introduction"}]
        sections = [
            {
                "id": "sec-intro",
                "title": "Introduction",
                "content": "Introduction\nFederated learning improves privacy for hospital models.",
                "coordinates": [{"page": 1, "x": 10, "y": 20}],
            }
        ]

        [claim] = map_citations_to_claims(claims, draft_text, sections)

        assert claim["line_number"] == 2
        assert claim["section_id"] == "sec-intro"
        assert claim["char_offset_from_section"] >= 0
        assert claim["pdf_coordinates"] == [{"page": 1, "x": 10, "y": 20}]
        assert claim["match_confidence"] == 0.95
        assert claim_text in claim["text_snippet"]

    @pytest.mark.unit
    def test_map_citations_to_claims_fuzzy_sentence_fallback_sets_line_confidence(self):
        from app.services.claim_analysis import map_citations_to_claims

        draft_text = (
            "Abstract\n"
            "Our system reduces annotation time by 37.5% across three datasets.\n"
            "Conclusion\n"
        )
        claims = [
            {
                "claim_text": (
                    "Our system reduces annotation time by 37.5% across three datasets. "
                    "This longer extracted claim includes generated framing not present verbatim."
                ),
                "section_location": "Abstract",
            }
        ]

        [claim] = map_citations_to_claims(claims, draft_text, sections=None)

        assert claim["line_number"] == 2
        assert claim["char_start"] == 0
        assert claim["match_confidence"] == 0.74
        assert "Our system reduces annotation time by 37.5%" in claim["text_snippet"]


class TestExternalSourceNormalizationReliability:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_external_fetch_deduplicates_titles_case_and_whitespace_insensitively(self):
        from app.services.coverage_analysis import _fetch_external_papers_for_gap

        async def fake_to_thread(_fn, *_args, **_kwargs):
            return [{"title": "  Attention Is All You Need  ", "authors": ["Vaswani"], "year": 2017}]

        oa_papers = [
            {
                "title": "attention is all you need",
                "authors": ["Vaswani"],
                "publication_year": 2017,
                "open_access_url": "https://arxiv.org/pdf/1706.03762",
            },
            {"title": "BERT", "authors": ["Devlin"], "year": 2019},
        ]

        with patch("app.services.coverage_analysis.asyncio.to_thread", side_effect=fake_to_thread), \
             patch(
                 "app.services.external_apis.openalex.find_open_access_papers_for_gap",
                 new=AsyncMock(return_value=oa_papers),
             ):
            papers = await _fetch_external_papers_for_gap("transformers", needed=2, max_external=5)

        normalized_titles = [paper["title"].strip().lower() for paper in papers]
        assert normalized_titles.count("attention is all you need") == 1
        assert "bert" in normalized_titles
        assert all(paper["external"] is True for paper in papers)


class TestFeedbackQualityAssurance:
    @pytest.mark.unit
    def test_evaluate_feedback_item_rejects_generic_feedback_without_target(self):
        from app.services.draft_anchor_qa import evaluate_feedback_item

        result = evaluate_feedback_item(
            {
                "feedback_type": "coverage",
                "severity": "major",
                "feedback_text": "Consider adding more citations and improving the argument.",
                "suggested_improvements": ["Add more references to strengthen the paper."],
                "specific_issue": "Missing citation",
            },
            "Introduction\nFederated learning improves privacy for hospital models.",
            claims=[
                {
                    "id": "claim-1",
                    "claim_text": "Federated learning improves privacy for hospital models.",
                }
            ],
        )

        assert result["passed"] is False


class TestRevisionTaskReliability:
    @pytest.mark.unit
    def test_consolidate_revision_tasks_merges_cross_agent_semantic_duplicates(self):
        from app.workflows.draft_analysis.revision_tasks import consolidate_revision_tasks

        tasks = [
            {
                "id": "task-a",
                "task_type": "framework_validation",
                "severity": "major",
                "priority": "medium",
                "section": "Discussion",
                "anchor_text": "While the heuristic empowers students, it does not address practical constraints.",
                "problem": "The manuscript lacks a limitations or boundary-conditions section for institutional constraints.",
                "why_it_matters": "Readers need to understand when the classroom heuristic may fail.",
                "suggested_action": "Add a limitations subsection covering digital literacy, institutional AI policy, and guardrails.",
            },
            {
                "id": "task-b",
                "task_type": "methodology",
                "severity": "major",
                "priority": "medium",
                "section": "Discussion",
                "anchor_text": "While the heuristic empowers students, it does not address practical constraints.",
                "problem": "Boundary conditions are missing; practical constraints such as digital literacy and AI policy are not discussed.",
                "why_it_matters": "The argument overstates classroom portability.",
                "suggested_action": "Create a dedicated limitations section with institutional policy, student access, and LLM guardrail constraints.",
            },
            {
                "id": "task-c",
                "task_type": "citation",
                "severity": "major",
                "priority": "medium",
                "section": "Introduction",
                "anchor_text": "ChatGPT's data dump in September 2021",
                "problem": "Claim lacks a verified supporting citation: ChatGPT's data dump in September 2021.",
                "why_it_matters": "The technical claim may be outdated.",
                "suggested_action": "Revise the wording to use precise model-version language or cite a source on model cutoff behavior.",
            },
            {
                "id": "task-d",
                "task_type": "clarity",
                "severity": "minor",
                "priority": "low",
                "section": "Introduction",
                "anchor_text": "ChatGPT's data dump in September 2021",
                "problem": "The data-dump phrasing is technically imprecise and outdated.",
                "why_it_matters": "Imprecise AI terminology weakens credibility.",
                "suggested_action": "Replace data dump with model-specific knowledge cutoff or training data language.",
            },
        ]

        consolidated = consolidate_revision_tasks(tasks)

        assert len(consolidated) == 2
        assert sum(task.get("duplicate_count", 0) for task in consolidated) == 2
        families = {task.get("issue_family") for task in consolidated}
        assert "pedagogy_boundary_conditions" in families
        assert "ai_technical_precision" in families

    @pytest.mark.unit
    def test_readiness_score_is_calibrated_by_manuscript_profile(self):
        from app.workflows.draft_analysis.revision_tasks import calculate_revision_task_readiness_score

        tasks = [
            {"severity": "major", "task_type": "methodology", "suggested_sources": []},
            {"severity": "major", "task_type": "literature_positioning", "suggested_sources": []},
            {"severity": "major", "task_type": "citation", "suggested_sources": []},
            {"severity": "minor", "task_type": "clarity", "suggested_sources": []},
        ]

        humanities = calculate_revision_task_readiness_score(
            tasks,
            manuscript_profile={
                "routing_domain": "humanities_education",
                "genre": "pedagogical_conceptual",
                "evidence_mode": "pedagogical",
            },
        )
        empirical = calculate_revision_task_readiness_score(
            tasks,
            manuscript_profile={"routing_domain": "computer_science_ml", "evidence_mode": "empirical_ml"},
        )

        assert humanities["readiness_score"] > empirical["readiness_score"]
        assert humanities["score_breakdown"]["domain_scoring_policy"] == "conceptual_pedagogical"
        assert empirical["score_breakdown"]["domain_scoring_policy"] == "empirical_computational"

    @pytest.mark.unit
    def test_meta_review_major_revision_guardrail_uses_realistic_band(self):
        from app.services.draft_analysis_langgraph import apply_meta_review_readiness_guardrail

        result = apply_meta_review_readiness_guardrail(
            {"readiness_score": 18, "verdict": "Major Revisions", "score_breakdown": {}},
            {"overall_recommendation": "major_revision"},
        )

        assert result["readiness_score"] == 35
        assert result["verdict"] == "Major Revisions"

    @pytest.mark.unit
    def test_common_software_behavior_claim_does_not_create_humanities_citation_task(self):
        from app.workflows.draft_analysis.revision_tasks import build_revision_tasks

        tasks = build_revision_tasks(
            diagnostic_findings=[],
            reviewer_outputs=[],
            claims=[
                {
                    "id": "claim-1",
                    "claim_text": "Parameters are reset every time a new dialogue is opened.",
                    "section_location": "Introduction",
                    "importance_score": 0.8,
                    "requires_citation": True,
                    "citation_quality": "none",
                }
            ],
            gaps=[],
            structural_feedback=[],
            manuscript_profile={"routing_domain": "humanities_education", "evidence_mode": "pedagogical"},
        )

        assert tasks == []


class TestRagGateReliability:
    @pytest.mark.unit
    def test_humanities_external_source_gate_keeps_relevant_rhetoric_source(self):
        from app.services.draft_external_source_discovery import _normalize_candidate

        target = {
            "draft_id": "draft-1",
            "target_type": "revision_task",
            "target_id": "task-1",
            "text": "Operationalize the AI writing heuristic into classroom rubrics and assessment artifacts.",
            "search_query": "composition pedagogy classroom assignment rubric assessment writing instruction generative AI",
            "rank": 1.0,
        }
        paper = {
            "title": "Writing Assessment Rubrics in Composition Pedagogy",
            "abstract": "This article studies classroom writing assessment, composition pedagogy, student agency, and rubric design.",
            "authors": ["Scholar"],
            "year": 2024,
            "citation_count": 35,
            "paper_url": "https://example.test/paper",
        }

        normalized = _normalize_candidate(paper, target, "openalex")

        assert normalized is not None
        assert normalized["relevance_score"] >= 0.62

    @pytest.mark.unit
    def test_humanities_external_source_gate_rejects_wrong_domain_source(self):
        from app.services.draft_external_source_discovery import _normalize_candidate

        target = {
            "draft_id": "draft-1",
            "target_type": "revision_task",
            "target_id": "task-1",
            "text": "Operationalize the AI writing heuristic into classroom rubrics and assessment artifacts.",
            "search_query": "composition pedagogy classroom assignment rubric assessment writing instruction generative AI",
            "rank": 1.0,
        }
        paper = {
            "title": "Sodium-Ion Battery Cathode Electrolyte Interphase Degradation",
            "abstract": "Layered oxide cathode materials and electrolyte degradation in sodium-ion batteries.",
            "authors": ["Scholar"],
            "year": 2024,
            "citation_count": 100,
        }

        assert _normalize_candidate(paper, target, "openalex") is None


class TestParseArtifactReliability:
    @pytest.mark.unit
    def test_parse_artifact_metrics_counts_persisted_section_and_anchor_maps(self):
        from app.services.draft_parse_artifacts import parse_artifact_metrics

        metrics = parse_artifact_metrics(
            {
                "parser_name": "grobid",
                "parser_quality_score": 0.9,
                "section_map": [{"id": "s1"}, {"id": "s2"}],
                "anchor_map": [{"text_snippet": "one"}, {"text_snippet": "two"}, {"text_snippet": "three"}],
                "parser_metadata": {"grobid_references_count": 7},
            }
        )

        assert metrics["section_count"] == 2
        assert metrics["anchor_count"] == 3
        assert metrics["reference_count"] == 7

    @pytest.mark.unit
    def test_local_fallback_structure_builds_anchor_map_from_plain_pdf_text(self):
        from app.services.draft_parse_artifacts import (
            assess_parse_quality,
            build_anchor_map,
            build_local_fallback_structure,
        )

        text = (
            "Abstract\nThis conceptual paper studies writing pedagogy and AI.\n\n"
            "Introduction\nStudents use generative AI in composition classrooms.\n\n"
            "Discussion\nThe heuristic needs assessment rubrics and limitations.\n\n"
            "Conclusion\nThe paper contributes to AI writing pedagogy."
        )

        structure = build_local_fallback_structure(text)
        anchors = build_anchor_map(structure)
        quality = assess_parse_quality(
            full_text=text,
            structure=structure,
            anchor_map=anchors,
            file_type="pdf",
        )

        assert len(structure["sections"]) >= 3
        assert anchors
        assert "not_grobid_pdf_parse" not in quality["parser_quality_flags"]

    @pytest.mark.unit
    def test_evaluate_feedback_item_rejects_missing_target_even_when_actionable(self):
        from app.services.draft_anchor_qa import evaluate_feedback_item

        result = evaluate_feedback_item(
            {
                "feedback_type": "evidence",
                "severity": "critical",
                "feedback_text": "The paper lacks baseline evidence for its central performance claim.",
                "specific_issue": "Unsupported comparative claim",
                "suggested_improvements": ["Add baseline comparisons for the central performance claim."],
            },
            "Results\nOur system reduces annotation time by 37.5% across three datasets.",
            claims=[
                {
                    "id": "claim-1",
                    "claim_text": "Our system reduces annotation time by 37.5% across three datasets.",
                }
            ],
        )

        assert result["passed"] is False
        assert "missing_target_claim_or_gap" in result["failed_checks"]

    @pytest.mark.unit
    def test_multimodal_fallback_triggers_for_risky_systematic_review_pdf(self):
        from app.services.draft_multimodal_parser import should_run_multimodal_fallback

        assert should_run_multimodal_fallback(
            file_type="pdf",
            full_text=(
                "This systematic review follows PRISMA. Table 1 contains the search strategy. "
                "Risk of bias was assessed across included studies."
            ),
            extracted_data={"sections": [{"title": "Intro"}], "references": []},
            parse_quality={"parser_quality_score": 0.7, "parser_quality_flags": ["low_section_count"]},
        ) is True


class TestBehavioralHealthRoutingAndDiagnostics:
    @pytest.mark.unit
    def test_social_media_anxiety_review_routes_to_public_health_psychology(self):
        from app.workflows.draft_analysis.nodes.manuscript_profile import build_manuscript_profile

        profile = build_manuscript_profile({
            "draft_content": (
                "This systematic review examines social media use, anxiety, depression, "
                "and mental health outcomes among adolescents and youth. PRISMA methods "
                "and risk of bias assessment were used."
            ),
            "paper_type": "journal_article",
        })

        assert profile["routing_domain"] == "public_health_psychology"
        assert "behavioral_health" in profile["domain_tags"]
        assert "clinical_ai" not in profile["domain_tags"]

    @pytest.mark.unit
    def test_public_health_systematic_review_does_not_emit_ehr_vendor_diagnostic(self):
        from app.workflows.draft_analysis.nodes.diagnostic_findings import diagnostic_findings_node

        state = {
            "draft_id": "draft-1",
            "manuscript_profile": {
                "genre": "systematic_review",
                "routing_domain": "public_health_psychology",
                "domain_tags": ["public_health", "psychology", "behavioral_health"],
                "review_lenses": ["systematic_review_methods", "behavioral_health"],
            },
            "draft_content": (
                "This systematic review studies social media use and anxiety in adolescents. "
                "The authors extracted included studies and assessed risk of bias, but do not "
                "mention funding source or conflict of interest extraction."
            ),
        }

        result = diagnostic_findings_node(state)
        problems = " ".join(item["problem"] for item in result["diagnostic_findings"])
        assert "EHR vendors" not in problems
        assert "clinical AI studies" not in problems
        assert "social-media platform involvement" in problems


class TestEvidenceRebuttal:
    @pytest.mark.unit
    def test_rewrites_false_missing_prospero_and_search_string_tasks(self):
        from app.services.draft_task_evidence import reconcile_tasks_against_evidence

        full_text = (
            "The protocol was registered with PROSPERO (CRD42018102770). "
            "Table 1. Search strategy: adolescen* OR teen OR youth AND social media "
            "AND anxiety OR depression. Medline, Embase, PsycINFO, CINAHL and SSCI were searched."
        )
        tasks = [
            {
                "id": "t1",
                "problem": "The review does not clearly report protocol registration.",
                "suggested_action": "State whether the review was registered in PROSPERO.",
            },
            {
                "id": "t2",
                "problem": "The manuscript does not provide full Boolean search strings.",
                "suggested_action": "Add complete search strings.",
            },
        ]

        reconciled, metrics = reconcile_tasks_against_evidence(tasks, full_text=full_text)

        assert metrics["tasks_rewritten"] == 2
        assert "Protocol registration is present" in reconciled[0]["problem"]
        assert "search strategy is present" in reconciled[1]["problem"]

    @pytest.mark.unit
    def test_drops_false_missing_narrative_synthesis_and_erikson_tasks(self):
        from app.services.draft_task_evidence import reconcile_tasks_against_evidence

        full_text = (
            "Erikson (1950) is used to frame identity development. "
            "As outcome measures varied across the studies, we were unable to perform meta-analysis. "
            "Instead, narrative synthesis was conducted."
        )
        tasks = [
            {
                "id": "t1",
                "problem": "Missing direct citation or summary of the identity-development framing.",
                "anchor_text": "Erikson (1950) is used to frame identity development.",
                "suggested_action": "Add a direct citation.",
            },
            {
                "id": "t2",
                "problem": "The authors do not justify narrative synthesis instead of meta-analysis.",
                "suggested_action": "Justify no pooling.",
            },
        ]

        reconciled, metrics = reconcile_tasks_against_evidence(tasks, full_text=full_text)

        assert reconciled == []
        assert metrics["tasks_dropped"] == 2

    @pytest.mark.unit
    def test_drops_missing_citation_task_when_inline_author_year_exists(self):
        from app.services.draft_task_evidence import reconcile_tasks_against_evidence

        task = {
            "id": "t1",
            "problem": "Claim lacks a verified supporting citation for the prevalence increase.",
            "anchor_text": "According to a national report (2017), rates increased substantially.",
            "suggested_action": "Add a citation.",
        }

        reconciled, metrics = reconcile_tasks_against_evidence([task], full_text=task["anchor_text"])

        assert reconciled == []
        assert metrics["tasks_dropped"] == 1

    @pytest.mark.unit
    def test_rewrites_false_missing_risk_of_bias_when_named_tool_present(self):
        from app.services.draft_task_evidence import reconcile_tasks_against_evidence

        full_text = (
            "Methodological quality was appraised using the National Institutes of Health "
            "(NIH) Quality Assessment Tool for observational cohort studies. Studies were "
            "rated as good, fair, or poor."
        )
        tasks = [
            {
                "id": "t1",
                "problem": "The review does not report a standardized risk-of-bias or quality-assessment tool.",
                "suggested_action": "Add a standardized risk-of-bias instrument.",
            }
        ]

        reconciled, metrics = reconcile_tasks_against_evidence(tasks, full_text=full_text)

        assert metrics["tasks_rewritten"] == 1
        assert len(reconciled) == 1
        # The rewritten task must acknowledge the tool exists, not claim it is missing.
        assert "NIH Quality Assessment Tool" in reconciled[0]["problem"]
        assert "does not explain how" in reconciled[0]["problem"]
        assert reconciled[0]["evidence_rebuttal_reason"] == "quality_assessment_tool_found"

    @pytest.mark.unit
    def test_keeps_missing_risk_of_bias_task_when_no_tool_present(self):
        from app.services.draft_task_evidence import reconcile_tasks_against_evidence

        full_text = (
            "We screened studies and extracted outcomes. The synthesis was narrative. "
            "No formal appraisal of study credibility was undertaken."
        )
        tasks = [
            {
                "id": "t1",
                "problem": "The review does not report any risk-of-bias or quality-assessment tool.",
                "suggested_action": "Add a standardized risk-of-bias instrument.",
            }
        ]

        reconciled, metrics = reconcile_tasks_against_evidence(tasks, full_text=full_text)

        assert metrics["tasks_rewritten"] == 0
        assert reconciled[0]["problem"] == tasks[0]["problem"]


class TestEvidenceManifest:
    @pytest.mark.unit
    def test_manifest_detects_named_quality_tools(self):
        from app.services.draft_evidence_manifest import build_evidence_manifest

        text = (
            "Risk of bias was assessed with the Cochrane RoB 2 tool and the "
            "Newcastle-Ottawa Scale for non-randomized studies."
        )
        manifest = build_evidence_manifest(text)
        fact = manifest["quality_assessment_tools"]
        assert fact["present"] is True
        assert "Cochrane RoB 2" in fact["labels"]
        assert "Newcastle-Ottawa Scale" in fact["labels"]

    @pytest.mark.unit
    def test_manifest_detects_protocol_databases_and_dates(self):
        from app.services.draft_evidence_manifest import build_evidence_manifest

        text = (
            "Registered in PROSPERO (CRD42020112233). PubMed, Embase and Scopus were "
            "searched from inception to March 2023."
        )
        manifest = build_evidence_manifest(text)
        assert manifest["protocol_registration"]["present"] is True
        assert {"PubMed", "Embase", "Scopus"}.issubset(set(manifest["databases_searched"]["labels"]))
        assert manifest["search_dates"]["present"] is True
        assert manifest["search_dates"]["latest_year"] == 2023

    @pytest.mark.unit
    def test_manifest_absent_facts_are_false(self):
        from app.services.draft_evidence_manifest import build_evidence_manifest

        manifest = build_evidence_manifest("A short essay about a topic with no methods.")
        assert manifest["quality_assessment_tools"]["present"] is False
        assert manifest["protocol_registration"]["present"] is False
        assert manifest["databases_searched"]["present"] is False


class TestPublishGate:
    @pytest.mark.unit
    def test_low_parser_quality_blocks_high_confidence(self):
        from app.services.draft_publish_gate import evaluate_publish_gate

        verdict = evaluate_publish_gate(
            file_type="pdf",
            revision_quality_metrics={"total_tasks": 5, "page_anchor_coverage": 0.9},
            parser_quality={"parser_quality_score": 0.3, "parser_quality_flags": ["very_short_extracted_text"]},
        )
        assert verdict["publishable"] is False
        assert verdict["gate_status"] == "needs_parser_review"
        assert verdict["confidence"] == "low"

    @pytest.mark.unit
    def test_low_page_anchor_coverage_blocks_pdf(self):
        from app.services.draft_publish_gate import evaluate_publish_gate

        verdict = evaluate_publish_gate(
            file_type="pdf",
            revision_quality_metrics={"total_tasks": 8, "page_anchor_coverage": 0.4},
            parser_quality={"parser_quality_score": 0.9},
        )
        assert verdict["publishable"] is False
        assert verdict["gate_status"] == "needs_retry"

    @pytest.mark.unit
    def test_low_coverage_does_not_block_non_pdf(self):
        from app.services.draft_publish_gate import evaluate_publish_gate

        verdict = evaluate_publish_gate(
            file_type="txt",
            revision_quality_metrics={"total_tasks": 8, "page_anchor_coverage": 0.0},
            parser_quality={"parser_quality_score": 0.9},
        )
        assert verdict["publishable"] is True
        assert verdict["gate_status"] == "ok"

    @pytest.mark.unit
    def test_contamination_flags_downgrade_confidence(self):
        from app.services.draft_publish_gate import evaluate_publish_gate

        verdict = evaluate_publish_gate(
            file_type="pdf",
            revision_quality_metrics={"total_tasks": 5, "page_anchor_coverage": 0.95},
            parser_quality={"parser_quality_score": 0.9},
            contamination_flags=["cross_domain_source"],
        )
        assert verdict["publishable"] is False
        assert verdict["confidence"] == "low"

    @pytest.mark.unit
    def test_good_run_publishes_high_confidence(self):
        from app.services.draft_publish_gate import evaluate_publish_gate

        verdict = evaluate_publish_gate(
            file_type="pdf",
            revision_quality_metrics={"total_tasks": 6, "page_anchor_coverage": 0.83, "verbatim_anchor_coverage": 0.8},
            parser_quality={"parser_quality_score": 0.92},
        )
        assert verdict["publishable"] is True
        assert verdict["gate_status"] == "ok"
        assert verdict["confidence"] == "high"

    @pytest.mark.unit
    def test_zero_tasks_does_not_trip_coverage_gate(self):
        from app.services.draft_publish_gate import evaluate_publish_gate

        verdict = evaluate_publish_gate(
            file_type="pdf",
            revision_quality_metrics={"total_tasks": 0, "page_anchor_coverage": 0.0},
            parser_quality={"parser_quality_score": 0.9},
        )
        assert verdict["publishable"] is True

    @pytest.mark.unit
    def test_fail_closed_flag_reads_env(self, monkeypatch):
        import importlib
        import app.services.draft_publish_gate as gate

        monkeypatch.setenv("DRAFT_ANALYSIS_FAIL_CLOSED", "true")
        reloaded = importlib.reload(gate)
        assert reloaded.FAIL_CLOSED is True

        monkeypatch.setenv("DRAFT_ANALYSIS_FAIL_CLOSED", "false")
        reloaded = importlib.reload(gate)
        assert reloaded.FAIL_CLOSED is False

        monkeypatch.delenv("DRAFT_ANALYSIS_FAIL_CLOSED", raising=False)
        importlib.reload(gate)  # restore default (off)


class TestDoclingMapper:
    @pytest.mark.unit
    def test_maps_docling_doc_to_extracted_data_with_coordinates(self):
        from app.services.docling_client import map_docling_to_extracted_data

        doc = {
            "texts": [
                {"label": "section_header", "text": "Methods",
                 "prov": [{"page_no": 2, "bbox": {"l": 50, "t": 700, "r": 300, "b": 688, "coord_origin": "BOTTOMLEFT"}}]},
                {"label": "text", "text": "We searched PubMed and Embase.",
                 "prov": [{"page_no": 2, "bbox": {"l": 50, "t": 680, "r": 320, "b": 660}}]},
                {"label": "text", "text": "Studies were screened in duplicate.",
                 "prov": [{"page_no": 3, "bbox": {"l": 50, "t": 700, "r": 320, "b": 680}}]},
                {"label": "section_header", "text": "References",
                 "prov": [{"page_no": 4, "bbox": {"l": 50, "t": 700, "r": 300, "b": 688}}]},
                {"label": "text", "text": "Smith J. A study. Journal. 2020.",
                 "prov": [{"page_no": 4, "bbox": {"l": 50, "t": 680, "r": 320, "b": 660}}]},
            ]
        }
        ex = map_docling_to_extracted_data(doc)
        paras = [p for s in ex["sections"] for p in s["paragraphs"]]
        # Every body paragraph carries a page (the whole point — vs GROBID's 0.0).
        assert paras and all(p["coordinates"].get("page") is not None for p in paras)
        # References split out of the body, not treated as paragraphs.
        assert len(ex["references"]) == 1
        assert "PubMed" in ex["full_text"]
        methods = next(s for s in ex["sections"] if s["title"] == "Methods")
        assert len(methods["paragraphs"]) == 2
        assert ex["metadata"]["parser"] == "docling"
        assert ex["metadata"]["page_count"] == 4

    @pytest.mark.unit
    def test_docling_parse_labeled_and_not_penalized(self):
        from app.services.draft_parse_artifacts import (
            build_structure_from_extracted_data,
            build_anchor_map,
            assess_parse_quality,
        )
        from app.services.docling_client import map_docling_to_extracted_data

        doc = {"texts": [
            {"label": "section_header", "text": "Introduction",
             "prov": [{"page_no": 1, "bbox": {"l": 50, "t": 700, "r": 300, "b": 688}}]},
            {"label": "text", "text": "This is a sufficiently long introduction paragraph " * 6,
             "prov": [{"page_no": 1, "bbox": {"l": 50, "t": 680, "r": 320, "b": 660}}]},
            {"label": "section_header", "text": "Methods",
             "prov": [{"page_no": 1, "bbox": {"l": 50, "t": 640, "r": 300, "b": 628}}]},
            {"label": "text", "text": "We did a thing and measured another thing carefully. " * 6,
             "prov": [{"page_no": 2, "bbox": {"l": 50, "t": 700, "r": 320, "b": 680}}]},
        ]}
        ex = map_docling_to_extracted_data(doc)
        structure = build_structure_from_extracted_data(ex)
        anchors = build_anchor_map(structure)
        q = assess_parse_quality(full_text=ex["full_text"] * 5, structure=structure, anchor_map=anchors, file_type="pdf")
        assert structure["document_metadata"]["docling_extracted"] is True
        assert structure["document_metadata"]["grobid_extracted"] is False
        assert q["parser_name"] == "docling"
        assert "not_grobid_pdf_parse" not in q["parser_quality_flags"]
        assert q["parse_blocked"] is False


class TestAnchorMatchingRepair:
    @pytest.mark.unit
    def test_paraphrased_task_anchor_links_to_store_and_inherits_page(self):
        from app.services.draft_analysis_langgraph import _apply_parse_artifact_anchors

        artifact = {"anchor_map": [{
            "text_snippet": "Adolescent social media use was associated with increased anxiety and depression across twelve cross-sectional studies.",
            "page_number": 4,
            "coordinates": {"page": 4, "x": 50, "y": 600},
            "section_title": "Results",
            "paragraph_index": 3,
        }]}
        tasks = [{
            "id": "t1",
            "problem": "The causal phrasing overstates the evidence.",
            # paraphrase / shares content words with the store snippet (not verbatim)
            "anchor_text": "social media use associated with increased anxiety and depression in adolescents",
            "section": "Results",
        }]
        out = _apply_parse_artifact_anchors("draft-x", tasks, artifact)
        t = out[0]
        assert t["anchor_status"] in ("exact", "fuzzy")
        assert t["anchor_source"] == "parse_artifact"
        assert t["page_number"] == 4
        # anchor_text repaired to the verbatim store snippet
        assert t["anchor_text"].startswith("Adolescent social media use")

    @pytest.mark.unit
    def test_unrelated_task_anchor_stays_unmatched(self):
        from app.services.draft_analysis_langgraph import _apply_parse_artifact_anchors

        artifact = {"anchor_map": [{
            "text_snippet": "Adolescent social media use was associated with increased anxiety and depression across studies.",
            "page_number": 4, "coordinates": {"page": 4}, "section_title": "Results",
        }]}
        tasks = [{"id": "t2", "problem": "Funding not disclosed.",
                  "anchor_text": "the funding sources conflicts disclosure statement appears entirely absent", "section": "Methods"}]
        out = _apply_parse_artifact_anchors("draft-x", tasks, artifact)
        assert out[0]["anchor_status"] in ("section_only", "unresolved")
        assert out[0].get("page_number") in (None, "", 0) or out[0].get("anchor_source") == "task_generated"

    @pytest.mark.unit
    def test_section_scoped_task_inherits_section_page(self):
        from app.services.draft_analysis_langgraph import _apply_parse_artifact_anchors

        artifact = {"anchor_map": [
            {"text_snippet": "We registered the protocol and defined eligibility criteria in detail here.",
             "page_number": 5, "coordinates": {"page": 5}, "section_title": "Methods"},
        ]}
        # Task scoped to Methods but its anchor doesn't quote any paragraph.
        tasks = [{"id": "t3", "problem": "Report the screening counts.",
                  "anchor_text": "screening flow counts and reasons for exclusion are not enumerated",
                  "section": "Methods"}]
        out = _apply_parse_artifact_anchors("draft-x", tasks, artifact)
        assert out[0]["page_number"] == 5
        assert out[0]["anchor_source"] == "parse_artifact_section"


class TestStaleSearchDiagnostic:
    @pytest.mark.unit
    def test_stale_search_emitted_when_gap_large(self):
        from app.services.draft_evidence_manifest import build_evidence_manifest, stale_search_task

        m = build_evidence_manifest(
            "We searched PubMed and Embase from inception to March 2018 for studies."
        )
        task = stale_search_task(m, reference_year=2026)
        assert task is not None
        assert task["dedupe_category"] == "search_currency"
        assert "2018" in task["problem"]
        assert task["task_type"] == "methodology"

    @pytest.mark.unit
    def test_no_stale_search_when_recent_or_absent(self):
        from app.services.draft_evidence_manifest import build_evidence_manifest, stale_search_task

        recent = build_evidence_manifest("Searches were conducted in 2025 across PubMed.")
        assert stale_search_task(recent, reference_year=2026) is None  # 1-year gap < 2

        none = build_evidence_manifest("A short essay with no search dates.")
        assert stale_search_task(none, reference_year=2026) is None


class TestParserPrereviewHalt:
    @pytest.mark.unit
    def test_halts_on_parse_blocked(self):
        from app.services.draft_analysis_langgraph import _parser_prereview_blocked
        blocked, reason = _parser_prereview_blocked({"parse_blocked": True, "parse_blocked_reason": "very_short_extracted_text"})
        assert blocked is True
        assert "very_short" in reason

    @pytest.mark.unit
    def test_halts_on_catastrophic_flag(self):
        from app.services.draft_analysis_langgraph import _parser_prereview_blocked
        blocked, _ = _parser_prereview_blocked({"parser_quality_flags": ["missing_anchor_map"]})
        assert blocked is True

    @pytest.mark.unit
    def test_does_not_halt_on_clean_or_minor_parse(self):
        from app.services.draft_analysis_langgraph import _parser_prereview_blocked
        assert _parser_prereview_blocked({"parser_quality_score": 1.0, "parser_quality_flags": []})[0] is False
        # A non-catastrophic flag (e.g. low section count) must NOT halt the review.
        assert _parser_prereview_blocked({"parser_quality_flags": ["low_section_count"]})[0] is False
        assert _parser_prereview_blocked(None)[0] is False


class TestVerbatimAnchorCoverage:
    @pytest.mark.unit
    def test_only_parse_artifact_matches_count_as_verbatim(self):
        from app.services.draft_analysis_langgraph import _revision_quality_metrics

        tasks = [
            {"anchor_source": "parse_artifact", "anchor_status": "exact", "anchor_text": "a"},
            {"anchor_source": "parse_artifact", "anchor_status": "fuzzy", "anchor_text": "b"},
            {"anchor_source": "task_generated", "anchor_status": "section_only", "anchor_text": "c"},
            {"anchor_source": "task_generated", "anchor_status": "unresolved", "anchor_text": "d"},
        ]
        metrics = _revision_quality_metrics(tasks)
        assert metrics["verbatim_anchor_coverage"] == 0.5


class TestGrobidNestedDivDedup:
    @pytest.mark.unit
    def test_nested_subsection_paragraphs_not_duplicated(self):
        import xml.etree.ElementTree as ET
        from app.services.grobid_client import GrobidClient

        tei = (
            '<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body>'
            '<div><head>Methods</head><p>Parent paragraph about the design.</p>'
            '<div><head>Participants</head><p>Nested paragraph about participants.</p></div>'
            '</div>'
            '</body></text></TEI>'
        )
        client = GrobidClient(base_url="http://localhost:8070")
        sections = client._extract_sections(ET.fromstring(tei))

        # All section content concatenated: each paragraph must appear exactly once.
        all_content = "\n".join(s["content"] for s in sections)
        assert all_content.count("Nested paragraph about participants.") == 1
        assert all_content.count("Parent paragraph about the design.") == 1
        # The parent Methods section must NOT absorb the nested paragraph.
        methods = next(s for s in sections if s["title"] == "Methods")
        assert "Nested paragraph about participants." not in methods["content"]


class TestParserQualityDuplicateHeadings:
    @pytest.mark.unit
    def test_duplicate_headings_flagged(self):
        from app.services.draft_parse_artifacts import assess_parse_quality

        structure = {
            "sections": [
                {"title": "Methods", "type": "methods"},
                {"title": "Methods", "type": "methods"},
                {"title": "Results", "type": "results"},
                {"title": "Results", "type": "results"},
            ],
            "document_metadata": {"grobid_extracted": True},
        }
        quality = assess_parse_quality(
            full_text="x" * 2000,
            structure=structure,
            anchor_map=[{"text_snippet": "y" * 100}],
            file_type="pdf",
        )
        assert "duplicate_section_headings" in quality["parser_quality_flags"]


class TestMultimodalFallbackGating:
    @pytest.mark.unit
    def test_high_quality_grobid_parse_skips_multimodal_even_with_tables(self):
        from app.services.draft_multimodal_parser import should_run_multimodal_fallback

        # Systematic review with Table 1 + Boolean (table_risk True) but a clean,
        # high-quality, well-sectioned GROBID parse → must NOT run the fallback.
        run = should_run_multimodal_fallback(
            file_type="pdf",
            full_text="This systematic review followed PRISMA. Table 1 lists Boolean search strings. PROSPERO registered.",
            extracted_data={"sections": [{"title": f"S{i}"} for i in range(30)], "references": [{}] * 20},
            parse_quality={"parser_quality_score": 1.0, "parser_quality_flags": []},
        )
        assert run is False

    @pytest.mark.unit
    def test_low_quality_parse_still_runs_multimodal(self):
        from app.services.draft_multimodal_parser import should_run_multimodal_fallback

        run = should_run_multimodal_fallback(
            file_type="pdf",
            full_text="garbled text",
            extracted_data={"sections": [{"title": "x"}], "references": []},
            parse_quality={"parser_quality_score": 0.4, "parser_quality_flags": ["low_section_count"]},
        )
        assert run is True

    @pytest.mark.unit
    def test_merge_dedups_sections_against_existing_grobid_titles(self):
        from app.services.draft_multimodal_parser import merge_multimodal_evidence

        extracted = {
            "sections": [
                {"title": "Search strategy", "content": "grobid version"},
                {"title": "Eligibility criteria", "content": "grobid version"},
            ],
            "full_text": "body",
            "metadata": {},
        }
        multimodal = {
            "evidence_sections": [
                {"title": "Search strategy", "text": "dup from vision", "page_number": 3},
                {"title": "Protocol and registration", "text": "new content", "page_number": 2},
            ],
            "detected_tables": [],
            "parser_notes": [],
        }
        merged = merge_multimodal_evidence(extracted, multimodal)
        titles = [s["title"] for s in merged["sections"]]
        # "Search strategy" not duplicated; the genuinely new section is appended.
        assert titles.count("Search strategy") == 1
        assert "Protocol and registration" in titles
        assert merged["metadata"]["multimodal_evidence_sections"] == 1
        assert merged["metadata"]["multimodal_sections_deduped"] == 1


class TestRagTopKFill:
    @pytest.mark.unit
    def test_floor_drops_weak_matches_without_padding(self, monkeypatch):
        import app.services.rag_retrieval as rr

        chunks = [
            {"id": "1", "semantic_score": 0.82, "content": "a"},
            {"id": "2", "semantic_score": 0.61, "content": "b"},
            {"id": "3", "semantic_score": 0.31, "content": "c"},
            {"id": "4", "semantic_score": 0.10, "content": "d"},
        ]
        monkeypatch.setattr(rr, "hybrid_search", lambda **kwargs: list(chunks))

        results = rr.retrieve_relevant_chunks_hybrid(
            project_id="p", query="q", limit=5, use_reranking=True, min_similarity=0.5
        )
        # Only the two chunks above the floor survive; result is NOT padded to limit.
        assert len(results) == 2
        assert all(c["semantic_score"] >= 0.5 for c in results)

    @pytest.mark.unit
    def test_zero_floor_preserves_prior_behavior(self, monkeypatch):
        import app.services.rag_retrieval as rr

        chunks = [{"id": str(i), "semantic_score": 0.1 * i, "content": "x"} for i in range(4)]
        monkeypatch.setattr(rr, "hybrid_search", lambda **kwargs: list(chunks))

        results = rr.retrieve_relevant_chunks_hybrid(
            project_id="p", query="q", limit=5, use_reranking=True, min_similarity=0.0
        )
        assert len(results) == 4

    @pytest.mark.unit
    def test_all_weak_returns_empty_not_filled(self, monkeypatch):
        import app.services.rag_retrieval as rr

        chunks = [{"id": str(i), "semantic_score": 0.05, "content": "x"} for i in range(4)]
        monkeypatch.setattr(rr, "hybrid_search", lambda **kwargs: list(chunks))

        results = rr.retrieve_relevant_chunks_hybrid(
            project_id="p", query="q", limit=5, use_reranking=True, min_similarity=0.45
        )
        assert results == []


class TestBehavioralHealthSourceGating:
    @pytest.mark.unit
    def test_public_health_psychology_rejects_unrelated_methodology_intervention_sources(self):
        from app.services.draft_external_source_discovery import _normalize_candidate

        target = {
            "target_type": "revision_task",
            "search_query": "public_health_psychology behavioral_health social media adolescent anxiety systematic review gray literature",
            "text": "Search gray literature for adolescent social media anxiety systematic review.",
            "rank": 1.0,
            "manuscript_profile": {
                "routing_domain": "public_health_psychology",
                "domain_tags": ["public_health", "psychology", "behavioral_health"],
                "review_lenses": ["systematic_review_methods"],
            },
        }
        paper = {
            "title": "Water fluoridation for the prevention of dental caries",
            "abstract": "A systematic review protocol for health interventions.",
            "authors": ["Scholar"],
            "year": 2020,
            "citation_count": 500,
        }

        assert _normalize_candidate(paper, target, "openalex") is None


class TestLangGraphPersistenceGrounding:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_langgraph_claim_persistence_exposes_grounding_fields(self, monkeypatch):
        from app.core import openai_client

        monkeypatch.setattr(openai_client, "get_openai_client", lambda: MagicMock())

        from app.services import draft_analysis_langgraph as langgraph_service

        fake_supabase = FakeSupabase(
            {
                "draft_analysis": [
                    {"draft_id": "draft-1", "analysis": {"editing_feedback": {}}, "analysis_metadata": {}}
                ],
                "drafts": [{"id": "draft-1", "paper_type": "conference_paper", "citation_style": "ieee"}],
                "documents": [
                    {
                        "id": "doc-1",
                        "title": "Federated Optimization",
                        "analysis": {"citation_metadata": {"all_authors": ["McMahan, Brendan"], "year": "2017"}},
                        "metadata": {},
                        "resolution_status": "resolved",
                    }
                ],
                "draft_claims": [],
                "coverage_gaps": [],
                "reviewer_feedback": [],
                "citation_suggestions": [],
            }
        )
        final_state = {
            "structure": {"word_count": 1200},
            "claims": [
                {
                    "id": "claim-1",
                    "claim_text": "Federated learning improves privacy.",
                    "claim_type": "empirical",
                    "section_location": "Introduction",
                    "importance_score": 0.9,
                    "requires_citation": True,
                }
            ],
            "claims_with_citations": [
                {
                    "claim": {
                        "claim_text": "Federated learning improves privacy.",
                        "section_location": "Introduction",
                    },
                    "citations": [
                        {
                            "document_id": "doc-1",
                            "document_title": "Federated Optimization",
                            "similarity": 0.87,
                            "content": "Federated optimization trains models without centralizing data.",
                            "chunk_index": 2,
                            "section": "Methods",
                        }
                    ],
                    "citation_quality": "strong",
                    "suggested_citations": [
                        {
                            "title": "Communication-Efficient Learning of Deep Networks from Decentralized Data",
                            "source": "semantic_scholar",
                        }
                    ],
                }
            ],
            "coverage_gaps": [],
            "reviewer_feedback": [],
            "structural_feedback": [],
            "synthesis_report": {},
            "errors": [],
        }

        async def fake_workflow(**_kwargs):
            return final_state

        with patch.object(langgraph_service, "supabase", fake_supabase), \
             patch("app.services.draft_analysis_runs.supabase", fake_supabase), \
             patch.object(langgraph_service, "run_draft_analysis_workflow", new=AsyncMock(side_effect=fake_workflow)), \
             patch.object(langgraph_service, "publish_progress", new=AsyncMock()), \
             patch("app.services.coverage_analysis.suggest_papers_for_gaps", new=AsyncMock(side_effect=lambda gaps, _project_id: gaps)), \
             patch("app.services.reviewer_feedback.calculate_readiness_score", return_value={"readiness_score": 80, "verdict": "ready", "score_breakdown": {}}), \
             patch("app.services.reviewer_feedback.synthesize_action_items", return_value=["Add one grounding citation."]), \
             patch("app.services.reviewer1_feedback.generate_reviewer1_feedback", new=AsyncMock(return_value=[])):
            result = await langgraph_service.analyze_draft_with_langgraph(
                draft_id="draft-1",
                project_id="project-1",
                user_id="user-1",
                draft_content="Federated learning improves privacy.",
            )

        assert result["workflow_type"] == "langgraph"
        [claim_row] = fake_supabase.tables["draft_claims"]
        supporting = claim_row["supporting_literature"]
        assert supporting["top_match"] == {
            "document_id": "doc-1",
            "document_title": "Federated Optimization",
            "similarity": 0.87,
            "display": "McMahan (2017) · 87% match",
        }
        assert supporting["suggested_citations"][0]["source"] == "semantic_scholar"
        assert claim_row["max_similarity"] == 0.87


class TestStructuredOutputRetryUtils:
    @pytest.mark.unit
    def test_sync_parse_helper_normalizes_sdk_choice_message_parsed(self):
        from app.services.retry_utils import parse_chat_completion_with_retries_sync

        parsed = SimpleNamespace(value="ok")
        client = MagicMock()
        client.beta.chat.completions.parse.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(parsed=parsed))]
        )

        response = parse_chat_completion_with_retries_sync(
            client,
            model="gpt-5.2",
            messages=[{"role": "user", "content": "Return structured output"}],
            response_format=object,
        )

        assert response.parsed is parsed
        assert response.raw.choices[0].message.parsed is parsed


class TestDraftAnalysisRunIsolation:
    @pytest.mark.unit
    def test_active_run_filter_scopes_to_published_active_run(self):
        from app.services.draft_analysis_runs import active_run_filter

        fake_supabase = FakeSupabase({"draft_claims": []})
        query = active_run_filter(fake_supabase.table("draft_claims").select("*"), "run-2")

        assert ("analysis_run_id", "run-2") in query.filters
        assert ("is_published", True) in query.filters

    @pytest.mark.unit
    def test_active_run_row_assertion_rejects_mismatched_rows(self):
        from app.services.draft_analysis_runs import assert_active_run_rows

        with pytest.raises(ValueError, match="analysis_run_id"):
            assert_active_run_rows(
                table="draft_claims",
                draft_id="draft-1",
                active_run_id="run-2",
                rows=[
                    {
                        "id": "claim-1",
                        "draft_id": "draft-1",
                        "analysis_run_id": "run-1",
                        "is_published": True,
                    }
                ],
            )

        with pytest.raises(ValueError, match="is_published"):
            assert_active_run_rows(
                table="draft_claims",
                draft_id="draft-1",
                active_run_id="run-2",
                rows=[
                    {
                        "id": "claim-1",
                        "draft_id": "draft-1",
                        "analysis_run_id": "run-2",
                        "is_published": False,
                    }
                ],
            )

    @pytest.mark.unit
    def test_publish_marks_only_new_run_visible_and_activates_draft(self, monkeypatch):
        from app.services import draft_analysis_runs

        fake_supabase = FakeSupabase({
            "drafts": [{"id": "draft-1", "status": "analyzed", "active_analysis_run_id": "run-1"}],
            "draft_analysis": [
                {
                    "id": "analysis-1",
                    "draft_id": "draft-1",
                    "analysis_run_id": "run-1",
                    "is_published": True,
                    "analysis_metadata": {"analysis_run_id": "run-1"},
                }
            ],
            "draft_claims": [
                {
                    "id": "claim-1",
                    "draft_id": "draft-1",
                    "analysis_run_id": "run-1",
                    "is_published": True,
                    "claim_text": "old",
                }
            ],
        })
        monkeypatch.setattr(draft_analysis_runs, "supabase", fake_supabase)

        draft_analysis_runs.publish_analysis_artifacts(
            run_id="run-2",
            draft_id="draft-1",
            artifacts={
                "draft_analysis": [{
                    "draft_id": "draft-1",
                    "analysis_metadata": {"analysis_run_id": "run-2"},
                }],
                "draft_claims": [{
                    "draft_id": "draft-1",
                    "claim_text": "new",
                }],
            },
        )

        assert fake_supabase.tables["drafts"][0]["active_analysis_run_id"] == "run-2"
        assert fake_supabase.tables["draft_analysis"][0]["analysis_run_id"] == "run-2"
        old_claim = next(row for row in fake_supabase.tables["draft_claims"] if row["claim_text"] == "old")
        new_claim = next(row for row in fake_supabase.tables["draft_claims"] if row["claim_text"] == "new")
        assert old_claim["is_published"] is False
        assert new_claim["analysis_run_id"] == "run-2"
        assert new_claim["is_published"] is True

    @pytest.mark.unit
    def test_publish_restores_previous_draft_analysis_if_activation_fails(self, monkeypatch):
        from app.services import draft_analysis_runs

        class FailingDraftUpdateTable(FakeTable):
            def execute(self):
                if self.name == "drafts" and self.action == "update":
                    raise RuntimeError("draft activation failed")
                return super().execute()

        class FailingDraftUpdateSupabase(FakeSupabase):
            def table(self, name):
                return FailingDraftUpdateTable(self, name)

        previous_row = {
            "id": "analysis-1",
            "draft_id": "draft-1",
            "analysis_run_id": "run-1",
            "is_published": True,
            "analysis_metadata": {"analysis_run_id": "run-1"},
        }
        fake_supabase = FailingDraftUpdateSupabase({
            "drafts": [{"id": "draft-1", "status": "analyzed", "active_analysis_run_id": "run-1"}],
            "draft_analysis": [dict(previous_row)],
            "draft_claims": [],
            "draft_analysis_runs": [{"id": "run-2", "draft_id": "draft-1", "status": "running"}],
        })
        monkeypatch.setattr(draft_analysis_runs, "supabase", fake_supabase)

        with pytest.raises(RuntimeError, match="draft activation failed"):
            draft_analysis_runs.publish_analysis_artifacts(
                run_id="run-2",
                draft_id="draft-1",
                artifacts={
                    "draft_analysis": [{
                        "draft_id": "draft-1",
                        "analysis_run_id": "run-2",
                        "analysis_metadata": {"analysis_run_id": "run-2"},
                    }],
                    "draft_claims": [{
                        "draft_id": "draft-1",
                        "claim_text": "new",
                    }],
                },
            )

        assert fake_supabase.tables["draft_analysis"] == [previous_row]
        assert fake_supabase.tables["draft_claims"] == []
        assert fake_supabase.tables["drafts"][0]["active_analysis_run_id"] == "run-1"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_async_parse_helper_normalizes_sdk_choice_message_parsed(self):
        from app.services.retry_utils import parse_chat_completion_with_retries

        parsed = SimpleNamespace(value="ok")
        client = SimpleNamespace(
            beta=SimpleNamespace(
                chat=SimpleNamespace(
                    completions=SimpleNamespace(
                        parse=AsyncMock(
                            return_value=SimpleNamespace(
                                choices=[SimpleNamespace(message=SimpleNamespace(parsed=parsed))]
                            )
                        )
                    )
                )
            )
        )

        response = await parse_chat_completion_with_retries(
            client,
            model="gpt-5.2",
            messages=[{"role": "user", "content": "Return structured output"}],
            response_format=object,
        )

        assert response.parsed is parsed
        assert response.raw.choices[0].message.parsed is parsed

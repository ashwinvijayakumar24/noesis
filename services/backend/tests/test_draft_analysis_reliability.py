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

    def upsert(self, payload):
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
        assert "missing_target_claim_or_gap" in result["failed_checks"]
        assert "missing_specific_issue" in result["failed_checks"]

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

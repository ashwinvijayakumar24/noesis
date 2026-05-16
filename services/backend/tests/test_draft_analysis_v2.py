import importlib.util
import io
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.datastructures import Headers, UploadFile
from starlette.requests import Request


class FakeResponse:
    def __init__(self, data=None, count=None):
        self.data = data
        self.count = count


class FakeStorageBucket:
    def __init__(self):
        self.uploads = {}

    def upload(self, path, file, file_options=None):
        self.uploads[path] = {
            "file": file,
            "file_options": file_options or {},
        }
        return {"path": path}

    def get_public_url(self, path):
        return f"https://storage.example/drafts/{path}"

    def create_signed_url(self, path, expires_in):
        return {"signedURL": f"https://signed.example/{path}?exp={expires_in}"}


class FakeStorage:
    def __init__(self):
        self.bucket = FakeStorageBucket()

    def from_(self, _name):
        return self.bucket


class FakeTable:
    def __init__(self, supabase, name):
        self.supabase = supabase
        self.name = name
        self.action = "select"
        self.filters = []
        self.payload = None
        self._limit = None
        self._order = None
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

    def order(self, field, desc=False):
        self._order = (field, desc)
        return self

    def limit(self, value):
        self._limit = value
        return self

    def single(self):
        self._single = True
        return self

    def or_(self, _value):
        return self

    def _filtered_rows(self):
        rows = [
            row for row in self._rows()
            if all(row.get(field) == value for field, value in self.filters)
        ]
        if self._order:
            key, desc = self._order
            rows = sorted(rows, key=lambda row: row.get(key) or "", reverse=desc)
        if self._limit is not None:
            rows = rows[:self._limit]
        return rows

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
                row = {"id": payload.get("id") or f"{self.name}-{len(self._rows()) + 1}", **payload}
                self._rows().append(row)
                inserted.append(row)
            return FakeResponse(inserted, count=len(inserted))

        if self.action == "update":
            updated = []
            for row in self._rows():
                if all(row.get(field) == value for field, value in self.filters):
                    row.update(self.payload)
                    updated.append(row)
            return FakeResponse(updated, count=len(updated))

        if self.action == "delete":
            remaining = []
            deleted = []
            for row in self._rows():
                if all(row.get(field) == value for field, value in self.filters):
                    deleted.append(row)
                else:
                    remaining.append(row)
            self.supabase.tables[self.name] = remaining
            return FakeResponse(deleted, count=len(deleted))

        return FakeResponse([])


class FakeSupabase:
    def __init__(self, tables=None):
        self.tables = tables or {}
        self.storage = FakeStorage()

    def table(self, name):
        return FakeTable(self, name)


def _load_module(path_parts, module_name: str):
    module_path = Path(__file__).resolve().parents[1]
    for part in path_parts:
        module_path = module_path / part
    if module_name in sys.modules:
        del sys.modules[module_name]

    if path_parts[-1] == "drafts.py":
        draft_export_stub = SimpleNamespace(export_draft_analysis_as_pdf=lambda *_args, **_kwargs: b"pdf")
        sys.modules["app.services.draft_export"] = draft_export_stub

    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _request() -> Request:
    return Request({"type": "http", "method": "POST", "headers": []})


class TestDraftAnalysisRouteV2:
    @pytest.mark.unit
    def test_get_draft_analysis_exposes_editing_feedback_and_revision_metadata(self):
        route = _load_module(["app", "api", "routes", "drafts.py"], "drafts_route_v2_test")
        fake_supabase = FakeSupabase(
            {
                "drafts": [
                    {
                        "id": "draft-1",
                        "user_id": "user-1",
                        "title": "Draft",
                        "status": "analyzed",
                        "paper_type": "conference_paper",
                        "citation_style": "ieee",
                    }
                ],
                "draft_analysis": [
                    {
                        "draft_id": "draft-1",
                        "analysis": {
                            "editing_feedback": {
                                "grammar_issues": [{"text": "teh", "issue": "typo", "suggestion": "the", "section": "Intro"}],
                                "citation_issues": [],
                                "formatting_issues": [],
                                "structural_notes": [],
                            }
                        },
                        "analysis_metadata": {
                            "priority_actions": ["Fix citations"],
                            "readiness_score": 72,
                            "verdict": "partially_ready",
                            "score_breakdown": {"coverage": 20},
                            "action_items": ["Add baseline"],
                        },
                    }
                ],
                "draft_comparisons": [
                    {
                        "id": "cmp-1",
                        "user_id": "user-1",
                        "draft_v1_id": "draft-0",
                        "draft_v2_id": "draft-1",
                        "improvement_score": 81,
                        "feedback_addressed": 3,
                        "gaps_resolved": 1,
                        "comparison_result": {
                            "feedback_carryover": [
                                {
                                    "feedback_id": "fb-2",
                                    "previous_feedback_id": "fb-1",
                                    "previous_feedback_text": "Clarify baseline comparison",
                                }
                            ]
                        },
                        "created_at": "2026-04-21T10:00:00Z",
                    }
                ],
            }
        )

        with patch.object(route, "supabase", fake_supabase):
            payload = route.get_draft_analysis("draft-1", "user-1")

        assert payload["editing_feedback"]["grammar_issues"][0]["issue"] == "typo"
        assert payload["paper_type"] == "conference_paper"
        assert payload["citation_style"] == "ieee"
        assert payload["revision_metadata"]["has_previous_version"] is True
        assert payload["revision_metadata"]["feedback_carryover_count"] == 1

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_all_feedback_adds_persona_defaults_and_carryover_metadata(self):
        route = _load_module(["app", "api", "routes", "drafts.py"], "drafts_route_v2_test")
        fake_supabase = FakeSupabase(
            {
                "drafts": [{"id": "draft-1", "user_id": "user-1"}],
                "draft_claims": [
                    {"id": "claim-1", "draft_id": "draft-1", "requires_citation": True, "importance_score": 0.9}
                ],
                "coverage_gaps": [
                    {"id": "gap-1", "draft_id": "draft-1", "priority": "high"}
                ],
                "reviewer_feedback": [
                    {
                        "id": "fb-2",
                        "draft_id": "draft-1",
                        "feedback_type": "argumentation",
                        "severity": "major",
                        "feedback_text": "Clarify baseline comparison",
                    }
                ],
                "draft_analysis": [
                    {
                        "draft_id": "draft-1",
                        "analysis_metadata": {
                            "readiness_score": 65,
                            "verdict": "partially_ready",
                            "score_breakdown": {"logic": 12},
                        }
                    }
                ],
                "draft_comparisons": [
                    {
                        "id": "cmp-1",
                        "user_id": "user-1",
                        "draft_v1_id": "draft-0",
                        "draft_v2_id": "draft-1",
                        "improvement_score": 74,
                        "feedback_addressed": 2,
                        "gaps_resolved": 1,
                        "comparison_result": {
                            "feedback_carryover": [
                                {
                                    "feedback_id": "fb-2",
                                    "previous_feedback_id": "fb-1",
                                    "previous_feedback_text": "Clarify baseline comparison",
                                }
                            ]
                        },
                        "created_at": "2026-04-21T10:00:00Z",
                    }
                ],
            }
        )

        with patch.object(route, "supabase", fake_supabase):
            payload = await route.get_all_feedback("draft-1", True, "new", "user-1")

        assert payload["feedback"][0]["reviewer_persona"] == "reviewer_2"
        assert payload["feedback"][0]["carryover_from_previous_version"] is True
        assert payload["feedback"][0]["previous_feedback_id"] == "fb-1"
        assert payload["revision_metadata"]["feedback_carryover_count"] == 1

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_upload_draft_stores_paper_type_and_citation_style(self):
        route = _load_module(["app", "api", "routes", "drafts.py"], "drafts_route_v2_test")
        fake_supabase = FakeSupabase({"drafts": []})
        upload_file = UploadFile(
            file=io.BytesIO(b"short academic draft content " * 20),
            filename="draft.txt",
            headers=Headers({"content-type": "text/plain"}),
        )
        task_result = SimpleNamespace(id="task-1")

        upload_impl = getattr(route.upload_draft, "__wrapped__", route.upload_draft)
        with patch.object(route, "supabase", fake_supabase), \
             patch.object(route, "validate_file_format", AsyncMock(return_value={"valid": True, "can_extract_text": True})), \
             patch("app.tasks.draft_analysis.analyze_draft_task.delay", return_value=task_result):
            response = await upload_impl(
                _request(),
                file=upload_file,
                project_id="project-1",
                title="My Draft",
                paper_type="thesis",
                citation_style="chicago",
                user_id="user-1",
            )

        assert response["draft"]["paper_type"] == "thesis"
        assert response["draft"]["citation_style"] == "chicago"
        assert fake_supabase.tables["drafts"][0]["paper_type"] == "thesis"
        assert fake_supabase.tables["drafts"][0]["citation_style"] == "chicago"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_find_papers_for_gap_updates_gap_cache(self):
        route = _load_module(["app", "api", "routes", "drafts.py"], "drafts_route_v2_test")
        fake_supabase = FakeSupabase(
            {
                "drafts": [{"id": "draft-1", "user_id": "user-1", "project_id": "project-1"}],
                "coverage_gaps": [
                    {"id": "gap-1", "draft_id": "draft-1", "description": "federated learning privacy accounting", "suggested_papers": []}
                ],
                "paper_recommendations": [],
            }
        )
        papers = [{"title": "Paper A", "doi": "10.1000/a"}]

        with patch.object(route, "supabase", fake_supabase), \
             patch("app.services.paper_recommendations.search_papers_by_query", return_value=papers):
            payload = await route.find_papers_for_gap("draft-1", "gap-1", "user-1")

        assert payload["count"] == 1
        assert payload["query"] == "federated learning privacy accounting"
        assert fake_supabase.tables["coverage_gaps"][0]["suggested_papers"][0]["title"] == "Paper A"


class TestReviewerAndStage1Services:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_generate_reviewer1_feedback_parses_strengths(self):
        service = _load_module(["app", "services", "reviewer1_feedback.py"], "reviewer1_feedback_v2_test")
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content='{"strengths":[{"aspect":"Novel contribution","section_reference":"Introduction","detail":"Introduces a new benchmark","significance":"high"}]}'
                    )
                )
            ]
        )

        with patch.object(service, "get_openai_client", return_value=fake_client):
            payload = await service.generate_reviewer1_feedback("draft-1", "Draft text", {"sections": []})

        assert payload[0]["reviewer_persona"] == "reviewer_1"
        assert payload[0]["feedback_type"] == "strength"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_run_stage1_editing_returns_stable_payload(self):
        service = _load_module(["app", "services", "stage1_editing.py"], "stage1_editing_v2_test")
        from app.workflows.draft_analysis.schemas import Stage1EditingOutput, GrammarIssue
        fake_parsed = Stage1EditingOutput(
            grammar_issues=[GrammarIssue(text="teh", issue="typo", suggestion="the", section="Intro")],
            citation_issues=[],
            formatting_issues=[],
            structural_notes=[],
        )
        fake_client = MagicMock()
        fake_client.beta.chat.completions.parse.return_value = SimpleNamespace(parsed=fake_parsed)

        with patch.object(service, "get_openai_client", return_value=fake_client):
            payload = await service.run_stage1_editing("Draft text", citation_style="apa", paper_type="journal_article")

        assert payload["grammar_issues"][0]["suggestion"] == "the"
        assert payload["citation_issues"] == []

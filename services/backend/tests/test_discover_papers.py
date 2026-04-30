import importlib.util
from pathlib import Path
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class FakeRedisPipeline:
    def __init__(self, redis_client):
        self.redis_client = redis_client

    def incr(self, key):
        self.redis_client.values[key] = int(self.redis_client.values.get(key, 0)) + 1
        return self

    def expire(self, _key, _ttl):
        return self

    def execute(self):
        return True


class FakeRedis:
    def __init__(self, initial=None):
        self.values = initial or {}

    def get(self, key):
        return self.values.get(key, 0)

    def pipeline(self):
        return FakeRedisPipeline(self)


class FakeResponse:
    def __init__(self, data=None, count=None):
        self.data = data or []
        self.count = count


def _load_route_module(filename: str, module_name: str):
    module_path = Path(__file__).resolve().parents[1] / "app" / "api" / "routes" / filename
    if module_name in sys.modules:
        return sys.modules[module_name]

    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class FakeRecommendationTable:
    def __init__(self, supabase):
        self.supabase = supabase
        self.action = "select"
        self.filters = {}
        self.payload = None
        self.range_start = None
        self.range_end = None

    def select(self, *_args, **_kwargs):
        self.action = "select"
        return self

    def eq(self, field, value):
        self.filters[field] = value
        return self

    def order(self, *_args, **_kwargs):
        return self

    def range(self, start, end):
        self.range_start = start
        self.range_end = end
        return self

    def update(self, payload):
        self.action = "update"
        self.payload = payload
        return self

    def delete(self):
        self.action = "delete"
        return self

    def insert(self, payload):
        self.action = "insert"
        self.payload = payload
        return self

    def execute(self):
        if self.action == "select":
            rows = [
                row for row in self.supabase.recommendations
                if all(row.get(field) == value for field, value in self.filters.items())
            ]
            if self.range_start is not None and self.range_end is not None:
                rows = rows[self.range_start:self.range_end + 1]
            count = len([
                row for row in self.supabase.recommendations
                if all(row.get(field) == value for field, value in self.filters.items())
            ])
            return FakeResponse(rows, count=count)

        if self.action == "update":
            for row in self.supabase.recommendations:
                if all(row.get(field) == value for field, value in self.filters.items()):
                    row.update(self.payload)
                    return FakeResponse([row])
            return FakeResponse([])

        if self.action == "insert":
            row = {"id": f"rec-{len(self.supabase.recommendations) + 1}", **self.payload}
            self.supabase.recommendations.append(row)
            return FakeResponse([row])

        if self.action == "delete":
            kept = []
            deleted = []
            for row in self.supabase.recommendations:
                if all(row.get(field) == value for field, value in self.filters.items()):
                    deleted.append(row)
                else:
                    kept.append(row)
            self.supabase.recommendations = kept
            return FakeResponse(deleted)

        return FakeResponse([])


class FakeProjectTable:
    def __init__(self, supabase):
        self.supabase = supabase
        self.action = "select"
        self.filters = {}
        self.payload = None

    def select(self, *_args, **_kwargs):
        self.action = "select"
        return self

    def eq(self, field, value):
        self.filters[field] = value
        return self

    def update(self, payload):
        self.action = "update"
        self.payload = payload
        return self

    def execute(self):
        if self.action == "select":
            rows = [
                row for row in self.supabase.projects
                if all(row.get(field) == value for field, value in self.filters.items())
            ]
            return FakeResponse(rows)

        if self.action == "update":
            for row in self.supabase.projects:
                if all(row.get(field) == value for field, value in self.filters.items()):
                    row.update(self.payload)
                    return FakeResponse([row])
            return FakeResponse([])

        return FakeResponse([])


class FakeDocumentsTable:
    def __init__(self, supabase):
        self.supabase = supabase
        self.action = "select"
        self.filters = {}
        self.payload = None

    def select(self, *_args, **_kwargs):
        self.action = "select"
        return self

    def eq(self, field, value):
        self.filters[field] = value
        return self

    def insert(self, payload):
        self.action = "insert"
        self.payload = payload
        return self

    def execute(self):
        if self.action == "select":
            rows = [
                row for row in self.supabase.documents
                if all(row.get(field) == value for field, value in self.filters.items())
            ]
            return FakeResponse(rows, count=len(rows))

        if self.action == "insert":
            row = {"id": "doc-1", **self.payload}
            self.supabase.documents.append(row)
            return FakeResponse([row])

        return FakeResponse([])


class FakeResearchQuestionsTable:
    def __init__(self):
        self.action = "select"

    def select(self, *_args, **_kwargs):
        self.action = "select"
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def delete(self):
        self.action = "delete"
        return self

    def insert(self, _payload):
        self.action = "insert"
        return self

    def execute(self):
        return FakeResponse([])


class FakeSupabase:
    def __init__(self, recommendations=None, projects=None, documents=None):
        self.recommendations = recommendations or []
        self.projects = projects or []
        self.documents = documents or []

    def table(self, name):
        if name == "paper_recommendations":
            return FakeRecommendationTable(self)
        if name == "projects":
            return FakeProjectTable(self)
        if name == "documents":
            return FakeDocumentsTable(self)
        if name == "research_questions":
            return FakeResearchQuestionsTable()
        raise AssertionError(f"Unhandled table: {name}")


class TestDiscoverQuotaAndPagination:
    @pytest.mark.unit
    def test_unified_quota_blocks_sixth_free_action(self):
        from fastapi import HTTPException

        route = _load_route_module("paper_recommendations.py", "paper_recommendations_route_discover_test")
        with patch.object(route, "_get_redis_client", return_value=FakeRedis({
            "daily_discover_actions:user-1:2026-04-22": 5,
        })), patch.object(route, "date") as mock_date:
            mock_date.today.return_value.isoformat.return_value = "2026-04-22"

            with pytest.raises(HTTPException) as exc_info:
                route._check_and_increment_discover_quota("user-1", "free")

        assert exc_info.value.detail["limit"] == 5
        assert exc_info.value.detail["used"] == 5

    @pytest.mark.unit
    def test_quota_status_returns_unified_shape(self):
        route = _load_route_module("paper_recommendations.py", "paper_recommendations_route_discover_test")
        fake_supabase = FakeSupabase(
            recommendations=[
                {"id": "rec-1", "project_id": "project-1", "user_id": "user-1", "status": "new"},
                {"id": "rec-2", "project_id": "project-1", "user_id": "user-1", "status": "new"},
            ]
        )

        with patch.object(route, "supabase", fake_supabase), \
             patch.object(route, "_get_redis_client", return_value=FakeRedis({
                 "daily_discover_actions:user-1:2026-04-22": 2,
             })), \
             patch.object(route, "date") as mock_date:
            mock_date.today.return_value.isoformat.return_value = "2026-04-22"
            status = route._build_quota_status("project-1", "user-1", "free")

        assert status == {
            "actions_used": 2,
            "actions_limit": 5,
            "total_held": 2,
            "max_pool": 30,
        }

    @pytest.mark.unit
    def test_list_recommendations_paginates(self):
        route = _load_route_module("paper_recommendations.py", "paper_recommendations_route_discover_test")
        fake_supabase = FakeSupabase(
            recommendations=[
                {"id": f"rec-{index}", "project_id": "project-1", "user_id": "user-1", "status": "new", "relevance_score": 1.0 - index / 100}
                for index in range(7)
            ],
            projects=[{"id": "project-1", "user_id": "user-1"}],
        )

        with patch.object(route, "supabase", fake_supabase):
            payload = route.get_paper_recommendations(
                project_id="project-1",
                status=None,
                limit=5,
                offset=0,
                user_id="user-1",
            )

        assert len(payload["papers"]) == 5
        assert payload["total_new"] == 7


class TestDiscoverSaveFlow:
    @pytest.mark.unit
    async def test_save_does_not_touch_removed_daily_save_quota(self):
        route = _load_route_module("paper_recommendations.py", "paper_recommendations_route_discover_test")
        fake_supabase = FakeSupabase(
            recommendations=[{
                "id": "rec-1",
                "project_id": "project-1",
                "user_id": "user-1",
                "title": "Recommended Paper",
                "authors": ["Ada Lovelace"],
                "year": 2025,
                "doi": "10.1234/example",
                "arxiv_id": None,
                "pubmed_id": None,
                "abstract": "Abstract",
                "journal_name": "Nature",
                "pdf_url": "https://example.com/paper.pdf",
                "paper_url": "https://example.com/paper",
                "citation_count": 42,
                "source": "semantic_scholar",
                "fields_of_study": ["Machine Learning"],
                "bib_saved": False,
            }]
        )

        with patch.object(route, "supabase", fake_supabase), \
             patch.object(route, "_get_redis_client") as mock_redis, \
             patch("app.services.quota_management.check_quota", AsyncMock()), \
             patch("app.services.quota_management.increment_quota_usage", AsyncMock()), \
             patch("app.tasks.bibtex_resolution_task.resolve_bibtex_task.delay") as mock_delay:
            response = await route.save_discovered_paper("project-1", "rec-1", "user-1")

        assert response["success"] is True
        assert fake_supabase.documents[0]["source_type"] == "discovered"
        mock_redis.assert_not_called()
        mock_delay.assert_called_once()


class TestInsightsAutoSeed:
    @pytest.mark.unit
    def test_insights_generates_discover_seed_inline_when_no_recommendations_exist(self):
        projects_route = _load_route_module("projects.py", "projects_route_discover_test")
        fake_supabase = FakeSupabase(
            projects=[{"id": "project-1", "user_id": "user-1"}],
            documents=[{
                "id": "doc-1",
                "project_id": "project-1",
                "user_id": "user-1",
                "title": "Paper 1",
                "status": "analyzed",
                "analysis": {"summary": "A"},
                "metadata": {},
            }],
        )
        fake_paper_recommendations_module = types.SimpleNamespace(
            _generate_and_store_recommendations=MagicMock(return_value={"count": 2})
        )

        with patch.object(projects_route, "supabase", fake_supabase), \
             patch("app.services.project_insights.analyze_project_insights", return_value={"summary": "", "research_gaps": [], "common_themes": [], "methodological_patterns": [], "conflicting_findings": [], "key_insights": [], "analysis_metadata": {}}), \
             patch("app.services.project_insights.validate_insights"), \
             patch("app.services.research_questions.generate_research_questions", return_value=[]), \
             patch.dict(sys.modules, {"app.api.routes.paper_recommendations": fake_paper_recommendations_module}):
            projects_route._run_insights_analysis_task("project-1", "user-1")

        fake_paper_recommendations_module._generate_and_store_recommendations.assert_called_once_with(
            project_id="project-1",
            user_id="user-1",
            discovery_type="recommended",
            search_query=None,
        )

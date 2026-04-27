import importlib.util
from pathlib import Path
import pytest
import sys
from unittest.mock import AsyncMock, MagicMock, patch


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


class FakeTable:
    def __init__(self, supabase, name):
        self.supabase = supabase
        self.name = name
        self.action = "select"
        self.payload = None
        self.filters = {}

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

    def update(self, payload):
        self.action = "update"
        self.payload = payload
        return self

    def delete(self):
        self.action = "delete"
        return self

    def execute(self):
        if self.name == "paper_recommendations" and self.action == "select":
            rec_id = self.filters.get("id")
            rows = [
                rec for rec in self.supabase.recommendations
                if all(rec.get(field) == value for field, value in self.filters.items())
            ]
            if rec_id:
                rows = [rec for rec in rows if rec["id"] == rec_id]
            return FakeResponse(rows)

        if self.name == "documents" and self.action == "insert":
            document = {"id": "doc-123", **self.payload}
            self.supabase.documents.append(document)
            return FakeResponse([document])

        if self.name == "paper_recommendations" and self.action == "update":
            for recommendation in self.supabase.recommendations:
                if all(recommendation.get(field) == value for field, value in self.filters.items()):
                    recommendation.update(self.payload)
                    return FakeResponse([recommendation])
            return FakeResponse([])

        return FakeResponse([])


class FakeSupabase:
    def __init__(self, recommendations):
        self.recommendations = recommendations
        self.documents = []

    def table(self, name):
        return FakeTable(self, name)


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


class TestLiteratureMapInsights:
    @pytest.mark.unit
    def test_validate_insights_defaults_new_optional_fields(self):
        from app.services.project_insights import validate_insights

        insights = {
            "research_gaps": [{"title": "Need more field studies", "description": "Few papers study deployment."}],
            "common_themes": [{"theme": "Evaluation", "description": "Most papers benchmark extensively."}],
            "methodological_patterns": [],
            "conflicting_findings": [],
            "key_insights": [],
            "summary": "Summary",
        }

        validate_insights(insights)

        assert insights["coverage_snapshot"]["paper_count"] == 0
        assert insights["key_insight_details"] == []
        assert insights["research_gaps"][0]["category"] == "methodological"
        assert insights["research_gaps"][0]["source_papers"] == []

    @pytest.mark.unit
    def test_group_recommendations_by_context_is_deterministic(self):
        projects_route = _load_route_module("projects.py", "projects_route_test")

        grouped = projects_route._group_recommendations_by_context([
            {
                "id": "r1",
                "title": "Paper A",
                "status": "new",
                "recommendation_context": {
                    "gap_titles": ["Gap A"],
                    "conflict_topics": ["Topic A"],
                },
            },
            {
                "id": "r2",
                "title": "Paper B",
                "status": "dismissed",
                "recommendation_context": {
                    "gap_titles": ["Gap A"],
                    "conflict_topics": ["Topic A"],
                },
            },
            {
                "id": "r3",
                "title": "Paper C",
                "status": "new",
                "recommendation_context": {
                    "gap_titles": ["Gap B"],
                    "conflict_topics": [],
                },
            },
        ])

        assert [record["id"] for record in grouped["summary_recommendations"]] == ["r1", "r3"]
        assert [record["id"] for record in grouped["gap_recommendations_by_title"]["Gap A"]] == ["r1"]
        assert [record["id"] for record in grouped["conflict_recommendations_by_topic"]["Topic A"]] == ["r1"]

    @pytest.mark.unit
    def test_build_insights_staleness_uses_count_and_timestamps(self):
        projects_route = _load_route_module("projects.py", "projects_route_test")

        count_only = projects_route._build_insights_staleness(
            insights_updated_at="2026-04-20T10:00:00",
            insights_doc_count=2,
            current_analyzed_count=3,
            latest_document_updated_at="2026-04-20T09:00:00",
        )
        timestamp_only = projects_route._build_insights_staleness(
            insights_updated_at="2026-04-20T10:00:00",
            insights_doc_count=2,
            current_analyzed_count=2,
            latest_document_updated_at="2026-04-20T11:00:00",
        )

        assert count_only == {"is_stale": True, "stale_reason": "document_count_changed"}
        assert timestamp_only == {"is_stale": True, "stale_reason": "documents_changed"}

    @pytest.mark.unit
    def test_free_plan_refresh_quota_blocks_sixth_run(self):
        from fastapi import HTTPException

        projects_route = _load_route_module("projects.py", "projects_route_test")
        mock_redis_client = MagicMock()

        mock_redis_client.return_value = FakeRedis({
            "daily_insights:user-1:2026-04-22": 5,
        })

        with patch.object(projects_route, "_get_redis_client", mock_redis_client), \
             patch.object(projects_route, "date") as mock_date:
            mock_date.today.return_value.isoformat.return_value = "2026-04-22"
            with pytest.raises(HTTPException) as exc_info:
                projects_route._enforce_insights_refresh_quota("user-1", "free")

        detail = exc_info.value.detail
        assert detail["used"] == 5
        assert detail["limit"] == 5
        assert detail["remaining"] == 0

    @pytest.mark.unit
    def test_paid_plan_refresh_quota_is_unlimited(self):
        projects_route = _load_route_module("projects.py", "projects_route_test")
        mock_redis_client = MagicMock()

        mock_redis_client.return_value = FakeRedis()
        with patch.object(projects_route, "_get_redis_client", mock_redis_client):
            quota = projects_route._enforce_insights_refresh_quota("user-1", "pro")

        assert quota["is_unlimited"] is True
        assert quota["limit"] is None


class TestLiteratureMapSavePath:
    @pytest.mark.unit
    async def test_save_discovered_paper_reuses_existing_document_flow(
        self,
    ):
        paper_recommendations_route = _load_route_module(
            "paper_recommendations.py",
            "paper_recommendations_route_test",
        )

        fake_supabase = FakeSupabase([
            {
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
            }
        ])
        mock_supabase = MagicMock()
        mock_supabase.table.side_effect = fake_supabase.table
        mock_check_quota = AsyncMock()
        mock_increment_quota_usage = AsyncMock()

        with patch.object(paper_recommendations_route, "supabase", mock_supabase), \
             patch.object(paper_recommendations_route, "_get_redis_client", return_value=FakeRedis()), \
             patch.object(paper_recommendations_route, "date") as mock_date, \
             patch("app.services.quota_management.check_quota", mock_check_quota), \
             patch("app.services.quota_management.increment_quota_usage", mock_increment_quota_usage), \
             patch("app.tasks.bibtex_resolution_task.resolve_bibtex_task.delay") as mock_delay:
            mock_date.today.return_value.isoformat.return_value = "2026-04-22"

            response = await paper_recommendations_route.save_discovered_paper("project-1", "rec-1", "user-1")

        assert response["success"] is True
        assert fake_supabase.documents[0]["status"] == "imported"
        assert fake_supabase.documents[0]["resolution_status"] == "resolving"
        assert fake_supabase.documents[0]["source_type"] == "discovered"
        assert fake_supabase.recommendations[0]["bib_saved"] is True
        mock_check_quota.assert_awaited_once_with("user-1", "document")
        mock_increment_quota_usage.assert_awaited_once_with("user-1", "document")
        mock_delay.assert_called_once()

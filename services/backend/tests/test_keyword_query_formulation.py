"""The keyword leg has to be able to match a sentence, not just a noun phrase.

THE FINDING (measured, not assumed -- docs/MEASUREMENTS.md §Keyword query formulation)
    ``keyword_search_chunks`` builds its query with ``plainto_tsquery``, which
    ANDs every lemma. The queries this system actually issues are manuscript
    claims averaging ~20 words, so a chunk has to contain all ~20 lemmas to match
    at all. Against the local eval database (118 docs / 2124 chunks):

        keyword_search_chunks(<proj>, 'job shop scheduling', 50)   -> 38 rows
        keyword_search_chunks(<proj>, '<20-word claim>', 50)       ->  0 rows

    55 of 59 eval queries returned zero rows; recall@10 was 0.0026 against dense
    at 0.4221. Migration 038 adds ``keyword_search_chunks_v2``, which ORs the
    query's lemmas and ranks with ``ts_rank(..., 1|32)``: 0 of 59 queries empty,
    recall@10 0.2841, precision@10 0.4339.

WHAT THESE TESTS CAN AND CANNOT DO
    They mock Supabase, so they cannot re-measure retrieval quality -- that lives
    in the eval harness against a real Postgres, and the numbers above are its
    output. What they pin down is the plumbing that the measurement depends on:
    which RPC gets called, that the degradation flag still fires and clears on
    BOTH paths, that odd queries do not blow up, and that the row shape
    ``hybrid_search`` consumes is unchanged. ``_AndOrSupabase`` encodes the
    measured AND/OR behaviour of the two RPCs so the flag can be tested against
    something with the right shape; it is a stand-in for the database, and the
    database is the source of truth.
"""

import re
from pathlib import Path

import pytest

from app.services import rag_retrieval
from app.services.rag_retrieval import (
    KEYWORD_SEARCH_DEGRADED,
    KEYWORD_SEARCH_RPC_LEGACY,
    KEYWORD_SEARCH_RPC_V2,
    KEYWORD_SEARCH_V2_ENV,
    keyword_search,
    keyword_search_rpc_name,
)

PROJECT_ID = "00000000-0000-0000-0000-000000000000"

#: A real eval query. 20 words, and no chunk in the corpus contains all of them.
LONG_CLAIM = (
    "we highlight the superior generalizability of our approach, as it maintains "
    "strong performance on large-scale instances even when trained on small-scale instances"
)
SHORT_QUERY = "job shop scheduling"

MIGRATION = (
    Path(__file__).resolve().parents[1] / "migrations" / "038_keyword_search_websearch.sql"
)

STOPWORDS = {
    "we", "the", "of", "our", "as", "it", "on", "even", "when", "a", "an", "is",
    "and", "to", "for", "in", "that", "this", "with", "by", "are", "be",
}


def _lemmas(text: str) -> set:
    """Crude stand-in for to_tsvector('english', ...): tokens minus stopwords."""
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOPWORDS}


class _Response:
    def __init__(self, data):
        self.data = data


class _AndOrSupabase:
    """Fake Supabase whose two RPCs differ exactly the way the real ones do.

    ``keyword_search_chunks`` requires EVERY query lemma to be present in a chunk
    (plainto_tsquery's AND). ``keyword_search_chunks_v2`` requires at least one
    (migration 038's OR). Rows carry the real column set: id, document_id,
    content, rank.
    """

    #: Two chunks that share vocabulary with the claim but contain neither all of
    #: its lemmas nor all of the short query's.
    CHUNKS = [
        {
            "id": "chunk-a",
            "document_id": "doc-1",
            "content": "job shop scheduling with reinforcement learning on large-scale instances",
        },
        {
            "id": "chunk-b",
            "document_id": "doc-2",
            "content": "we evaluate generalizability of the approach across problem sizes",
        },
    ]

    def __init__(self):
        self.calls = []

    def rpc(self, name, params):
        self.calls.append((name, params))
        outer = self

        class _Query:
            def execute(self):
                terms = _lemmas(params["search_query"] or "")
                rows = []
                if terms:
                    for i, chunk in enumerate(outer.CHUNKS):
                        content = _lemmas(chunk["content"])
                        hit = (
                            terms <= content
                            if name == KEYWORD_SEARCH_RPC_LEGACY
                            else bool(terms & content)
                        )
                        if hit:
                            rows.append({**chunk, "rank": round(0.5 - 0.1 * i, 4)})
                return _Response(rows[: params["match_count"]])

        return _Query()


class _RaisingSupabase:
    def __init__(self, exc):
        self.exc = exc
        self.calls = []

    def rpc(self, name, params):
        self.calls.append((name, params))
        outer = self

        class _Query:
            def execute(self):
                raise outer.exc

        return _Query()


@pytest.fixture(autouse=True)
def _clean_flag_and_env(monkeypatch):
    monkeypatch.delenv(KEYWORD_SEARCH_V2_ENV, raising=False)
    KEYWORD_SEARCH_DEGRADED.clear()
    yield
    KEYWORD_SEARCH_DEGRADED.clear()


# ---------------------------------------------------------------------------
# The flag selects the path
# ---------------------------------------------------------------------------


class TestFlagSelectsPath:
    def test_default_is_the_legacy_rpc(self, monkeypatch):
        """Default OFF. 59 queries from 4 manuscripts is not enough evidence to
        change what every production retrieval call does."""
        fake = _AndOrSupabase()
        monkeypatch.setattr(rag_retrieval, "supabase", fake)

        keyword_search(PROJECT_ID, SHORT_QUERY)

        assert keyword_search_rpc_name() == KEYWORD_SEARCH_RPC_LEGACY
        assert fake.calls[0][0] == KEYWORD_SEARCH_RPC_LEGACY

    @pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on", " On "])
    def test_truthy_values_select_v2(self, monkeypatch, value):
        monkeypatch.setenv(KEYWORD_SEARCH_V2_ENV, value)
        fake = _AndOrSupabase()
        monkeypatch.setattr(rag_retrieval, "supabase", fake)

        keyword_search(PROJECT_ID, SHORT_QUERY)

        assert fake.calls[0][0] == KEYWORD_SEARCH_RPC_V2

    @pytest.mark.parametrize("value", ["", "0", "false", "no", "off", "maybe"])
    def test_anything_else_stays_on_legacy(self, monkeypatch, value):
        monkeypatch.setenv(KEYWORD_SEARCH_V2_ENV, value)
        fake = _AndOrSupabase()
        monkeypatch.setattr(rag_retrieval, "supabase", fake)

        keyword_search(PROJECT_ID, SHORT_QUERY)

        assert fake.calls[0][0] == KEYWORD_SEARCH_RPC_LEGACY

    def test_flag_is_read_per_call_not_at_import(self, monkeypatch):
        """Flipping the env in a running process takes effect immediately --
        otherwise an eval run would have to reload the module to compare paths."""
        fake = _AndOrSupabase()
        monkeypatch.setattr(rag_retrieval, "supabase", fake)

        keyword_search(PROJECT_ID, SHORT_QUERY)
        monkeypatch.setenv(KEYWORD_SEARCH_V2_ENV, "1")
        keyword_search(PROJECT_ID, SHORT_QUERY)

        assert [c[0] for c in fake.calls] == [
            KEYWORD_SEARCH_RPC_LEGACY,
            KEYWORD_SEARCH_RPC_V2,
        ]

    def test_rpc_parameters_are_identical_on_both_paths(self, monkeypatch):
        """v2 keeps the (proj_id, search_query, match_count) signature, so the
        call site does not fork -- only the function name changes."""
        fake = _AndOrSupabase()
        monkeypatch.setattr(rag_retrieval, "supabase", fake)
        keyword_search(PROJECT_ID, SHORT_QUERY, limit=7)
        monkeypatch.setenv(KEYWORD_SEARCH_V2_ENV, "1")
        keyword_search(PROJECT_ID, SHORT_QUERY, limit=7)

        assert fake.calls[0][1] == fake.calls[1][1] == {
            "proj_id": PROJECT_ID,
            "search_query": SHORT_QUERY,
            "match_count": 7,
        }


# ---------------------------------------------------------------------------
# The finding itself
# ---------------------------------------------------------------------------


class TestLongClaimMatching:
    def test_long_claim_returns_nothing_on_the_legacy_path(self, monkeypatch):
        """The bug, in one assertion. Measured against real Postgres as 0 rows
        for 55 of 59 eval queries."""
        monkeypatch.setattr(rag_retrieval, "supabase", _AndOrSupabase())

        assert keyword_search(PROJECT_ID, LONG_CLAIM) == []

    def test_long_claim_returns_rows_on_v2(self, monkeypatch):
        monkeypatch.setenv(KEYWORD_SEARCH_V2_ENV, "1")
        monkeypatch.setattr(rag_retrieval, "supabase", _AndOrSupabase())

        rows = keyword_search(PROJECT_ID, LONG_CLAIM)

        assert rows, "v2 must match a long claim on partial lemma overlap"
        assert {r["id"] for r in rows} == {"chunk-a", "chunk-b"}

    def test_short_query_still_works_on_both_paths(self, monkeypatch):
        """v2 is not a replacement that breaks the case the old one handled."""
        monkeypatch.setattr(rag_retrieval, "supabase", _AndOrSupabase())
        legacy = keyword_search(PROJECT_ID, SHORT_QUERY)

        monkeypatch.setenv(KEYWORD_SEARCH_V2_ENV, "1")
        v2 = keyword_search(PROJECT_ID, SHORT_QUERY)

        assert legacy and v2
        assert {r["id"] for r in legacy} <= {r["id"] for r in v2}

    def test_empty_result_is_not_a_degradation_on_either_path(self, monkeypatch):
        """"Matched nothing" and "the RPC is broken" must stay distinguishable.
        Conflating them is what hid the original failure for the life of the
        feature."""
        monkeypatch.setattr(rag_retrieval, "supabase", _AndOrSupabase())
        assert keyword_search(PROJECT_ID, LONG_CLAIM) == []
        assert KEYWORD_SEARCH_DEGRADED.degraded is False

        monkeypatch.setenv(KEYWORD_SEARCH_V2_ENV, "1")
        assert keyword_search(PROJECT_ID, "zzzz-no-such-term") == []
        assert KEYWORD_SEARCH_DEGRADED.degraded is False


# ---------------------------------------------------------------------------
# Degenerate queries
# ---------------------------------------------------------------------------


DEGENERATE = [
    pytest.param("", id="empty"),
    pytest.param("   ", id="whitespace"),
    pytest.param("the of and a an is", id="stopwords-only"),
    pytest.param("!!! & | <-> '' \\ ( ) ;", id="tsquery-operators"),
    pytest.param("'; DROP TABLE document_chunks; --", id="sql-ish"),
    pytest.param("O'Reilly's C:\\path\\to \"quoted\"", id="quotes-and-backslashes"),
]


class TestDegenerateQueries:
    @pytest.mark.parametrize("query", DEGENERATE)
    @pytest.mark.parametrize("v2", [False, True])
    def test_no_exception_and_no_false_degradation(self, monkeypatch, query, v2):
        if v2:
            monkeypatch.setenv(KEYWORD_SEARCH_V2_ENV, "1")
        monkeypatch.setattr(rag_retrieval, "supabase", _AndOrSupabase())

        rows = keyword_search(PROJECT_ID, query)

        assert isinstance(rows, list)
        assert KEYWORD_SEARCH_DEGRADED.degraded is False

    def test_stopword_only_query_returns_nothing_rather_than_everything(self, monkeypatch):
        """An OR query over an empty lemma set would otherwise match the whole
        project. Migration 038 returns early instead."""
        monkeypatch.setenv(KEYWORD_SEARCH_V2_ENV, "1")
        monkeypatch.setattr(rag_retrieval, "supabase", _AndOrSupabase())

        assert keyword_search(PROJECT_ID, "the of and a an is") == []


# ---------------------------------------------------------------------------
# Degradation, on both paths
# ---------------------------------------------------------------------------


class TestDegradationOnBothPaths:
    @pytest.mark.parametrize("v2", [False, True])
    def test_failure_records_and_still_returns_empty(self, monkeypatch, v2):
        if v2:
            monkeypatch.setenv(KEYWORD_SEARCH_V2_ENV, "1")
        monkeypatch.setattr(
            rag_retrieval, "supabase", _RaisingSupabase(RuntimeError("42883 undefined function"))
        )

        assert keyword_search(PROJECT_ID, LONG_CLAIM) == []

        snap = KEYWORD_SEARCH_DEGRADED.snapshot()
        assert snap["degraded"] is True
        assert snap["failure_count"] == 1
        assert "42883" in snap["last_error"]

    @pytest.mark.parametrize("v2", [False, True])
    def test_success_clears_a_previous_failure(self, monkeypatch, v2):
        if v2:
            monkeypatch.setenv(KEYWORD_SEARCH_V2_ENV, "1")
        monkeypatch.setattr(rag_retrieval, "supabase", _RaisingSupabase(RuntimeError("boom")))
        keyword_search(PROJECT_ID, SHORT_QUERY)
        assert KEYWORD_SEARCH_DEGRADED.degraded is True

        monkeypatch.setattr(rag_retrieval, "supabase", _AndOrSupabase())
        keyword_search(PROJECT_ID, SHORT_QUERY)
        assert KEYWORD_SEARCH_DEGRADED.degraded is False

    def test_missing_v2_function_is_loud_not_silent(self, monkeypatch, caplog):
        """A deployment where 038 has not been applied but the flag is on must
        surface as a recorded degradation naming the RPC, not as thin results."""
        import logging

        monkeypatch.setenv(KEYWORD_SEARCH_V2_ENV, "1")
        monkeypatch.setattr(
            rag_retrieval,
            "supabase",
            _RaisingSupabase(RuntimeError('function keyword_search_chunks_v2 does not exist')),
        )

        with caplog.at_level(logging.ERROR, logger=rag_retrieval.__name__):
            keyword_search(PROJECT_ID, SHORT_QUERY)

        errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert errors and KEYWORD_SEARCH_RPC_V2 in errors[0].getMessage()
        assert errors[0].exc_info is not None


# ---------------------------------------------------------------------------
# The row shape hybrid_search actually consumes
# ---------------------------------------------------------------------------


class TestHybridSearchContract:
    """``hybrid_search`` reads exactly two keys off a keyword row: ``id`` (line
    ~469) and ``rank`` (line ~477). Migration 038 returns
    ``(id, document_id, content, rank)`` -- the same four columns as the legacy
    function -- so the fusion code needs no change. These tests hold that."""

    def test_keyword_rank_reaches_the_combined_score(self, monkeypatch):
        monkeypatch.setenv(KEYWORD_SEARCH_V2_ENV, "1")
        monkeypatch.setattr(rag_retrieval, "supabase", _AndOrSupabase())
        monkeypatch.setattr(rag_retrieval, "expand_query", lambda q: [q])
        monkeypatch.setattr(rag_retrieval, "semantic_search", lambda *a, **k: [])

        results = rag_retrieval.hybrid_search(PROJECT_ID, LONG_CLAIM, limit=5)

        assert results, "keyword-only rows must still make it into the fusion"
        top = results[0]
        assert top["keyword_score"] == pytest.approx(0.5)
        assert top["semantic_score"] == 0.0
        assert top["combined_score"] == pytest.approx(0.3 * 0.5)

    def test_only_id_and_rank_are_required_of_a_keyword_row(self, monkeypatch):
        """Pin the contract: a row carrying nothing but id and rank still fuses.
        If a future migration drops a column, this is the test that says whether
        it mattered."""
        rows = [{"id": "chunk-a", "rank": 0.42}]

        class _Bare:
            def rpc(self, name, params):
                class _Q:
                    def execute(self):
                        return _Response(rows)
                return _Q()

        monkeypatch.setattr(rag_retrieval, "supabase", _Bare())
        monkeypatch.setattr(rag_retrieval, "expand_query", lambda q: [q])
        monkeypatch.setattr(rag_retrieval, "semantic_search", lambda *a, **k: [])

        results = rag_retrieval.hybrid_search(PROJECT_ID, SHORT_QUERY, limit=5)

        assert [r["id"] for r in results] == ["chunk-a"]
        assert results[0]["keyword_score"] == pytest.approx(0.42)


# ---------------------------------------------------------------------------
# Migration 038 must not disturb the function another lane is measuring
# ---------------------------------------------------------------------------


class TestMigrationLeavesTheOriginalAlone:
    def test_migration_exists(self):
        assert MIGRATION.exists(), f"missing {MIGRATION}"

    def test_it_never_drops_or_replaces_keyword_search_chunks(self):
        """The retrieval-eval lane measures against the existing RPC. Changing it
        underneath a run would corrupt those numbers and destroy the before/after
        comparison 038 exists to justify."""
        sql = MIGRATION.read_text()
        touched = re.findall(
            r"(?:DROP\s+FUNCTION|CREATE(?:\s+OR\s+REPLACE)?\s+FUNCTION)"
            r"(?:\s+IF\s+EXISTS)?\s+(?:public\.)?(\w+)",
            sql,
            re.IGNORECASE,
        )
        assert touched, "migration defines no function?"
        assert set(touched) == {"keyword_search_chunks_v2"}

    def test_it_ors_the_lemmas_and_bounds_the_rank(self):
        sql = MIGRATION.read_text()
        assert "' | '" in sql, "v2 must OR the query's lemmas"
        assert "ts_rank(dc.content_tsvector, q, 1|32)" in sql
        body = sql.split("$function$")[1]
        code = "\n".join(re.sub(r"--.*", "", line) for line in body.splitlines())
        assert "plainto_tsquery" not in code, (
            "the AND-ing tsquery constructor must not appear in the executable body"
        )

    def test_it_returns_the_columns_hybrid_search_reads(self):
        sql = MIGRATION.read_text()
        assert "RETURNS TABLE(id uuid, document_id uuid, content text, rank real)" in sql

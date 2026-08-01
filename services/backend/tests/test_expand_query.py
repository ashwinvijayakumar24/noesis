"""expand_query response-shape handling (app/services/rag_retrieval.py).

The prompt asks the model for a bare JSON array, but the old code did
`json.loads(...).get("queries", ...)`. A compliant array response therefore hit
`list.get` -> AttributeError -> the blanket `except` -> `[query]`. The
documented 4x fan-out in hybrid_search was a permanent no-op: one LLM call,
one search. These tests pin both accepted shapes and the failure fallback.
"""

import json
from types import SimpleNamespace

import pytest

from app.services import rag_retrieval
from app.services.rag_retrieval import expand_query

QUERY = "how do transformers work"
THREE = [
    "transformer architecture attention mechanisms",
    "self-attention neural networks NLP",
    "multi-head attention deep learning",
]


class _FakeClient:
    """Returns a canned message body. Never touches the network."""

    def __init__(self, content):
        self.calls = 0
        self._content = content
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create)
        )

    def _create(self, **kwargs):
        self.calls += 1
        self.last_kwargs = kwargs
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self._content))]
        )


@pytest.fixture
def fake_llm(monkeypatch):
    def _install(content):
        client = _FakeClient(content)
        monkeypatch.setattr(rag_retrieval, "get_openai_client", lambda: client)
        monkeypatch.setattr(rag_retrieval, "get_completion_params", lambda: {})
        return client

    return _install


class TestBareArrayShape:
    """The shape the prompt actually asks for -- and the one that used to break."""

    def test_bare_array_returns_all_queries(self, fake_llm):
        fake_llm(json.dumps(THREE))
        assert expand_query(QUERY) == [QUERY] + THREE

    def test_bare_array_is_capped_at_three_variations(self, fake_llm):
        fake_llm(json.dumps(THREE + ["a fourth one", "a fifth one"]))
        result = expand_query(QUERY)
        assert len(result) == 4
        assert result == [QUERY] + THREE

    def test_bare_array_with_fewer_than_three(self, fake_llm):
        fake_llm(json.dumps(THREE[:1]))
        assert expand_query(QUERY) == [QUERY, THREE[0]]


class TestObjectShape:
    def test_queries_key(self, fake_llm):
        fake_llm(json.dumps({"queries": THREE}))
        assert expand_query(QUERY) == [QUERY] + THREE

    def test_variations_key(self, fake_llm):
        fake_llm(json.dumps({"variations": THREE}))
        assert expand_query(QUERY) == [QUERY] + THREE

    def test_single_unknown_key_wrapping_a_list(self, fake_llm):
        fake_llm(json.dumps({"expansions": THREE}))
        assert expand_query(QUERY) == [QUERY] + THREE

    def test_ambiguous_multi_list_object_falls_back(self, fake_llm):
        fake_llm(json.dumps({"a": THREE, "b": ["other"]}))
        # Two candidate lists, no way to know which -- refuse to guess.
        assert expand_query(QUERY) == [QUERY]


class TestFallbacks:
    """Genuine failures must degrade to [query], never raise."""

    @pytest.mark.parametrize(
        "content",
        [
            "Sure! Here are three variations for you:",
            "not json at all",
            "",
            "null",
            "42",
            '"just a string"',
            '{"queries": "not a list"}',
            "{unclosed",
        ],
    )
    def test_garbage_falls_back_without_raising(self, fake_llm, content):
        fake_llm(content)
        assert expand_query(QUERY) == [QUERY]

    def test_none_content_falls_back(self, fake_llm):
        fake_llm(None)
        assert expand_query(QUERY) == [QUERY]

    def test_api_call_exception_falls_back(self, monkeypatch):
        def boom(**kwargs):
            raise RuntimeError("openai is down")

        client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=boom))
        )
        monkeypatch.setattr(rag_retrieval, "get_openai_client", lambda: client)
        monkeypatch.setattr(rag_retrieval, "get_completion_params", lambda: {})
        assert expand_query(QUERY) == [QUERY]

    def test_empty_array_returns_original_query_only(self, fake_llm):
        """CHOSEN BEHAVIOUR: an empty array is a valid, well-formed 'I have no
        variations' answer, so it is honoured -- the original query is still
        searched, no error, no synthetic filler. Same for an empty object."""
        fake_llm(json.dumps([]))
        assert expand_query(QUERY) == [QUERY]

    def test_empty_object_returns_original_query_only(self, fake_llm):
        fake_llm(json.dumps({"queries": []}))
        assert expand_query(QUERY) == [QUERY]

    def test_non_string_items_are_dropped(self, fake_llm):
        fake_llm(json.dumps(["good query", 5, None, {"x": 1}, "  ", "another good one"]))
        assert expand_query(QUERY) == [QUERY, "good query", "another good one"]


class TestRegressionAgainstOldCode:
    """Fails against the pre-fix implementation.

    Old body was:
        result = json.loads(...)
        variations = result.get("queries", result.get("variations", [query]))
        return [query] + variations[:3]
    With a list `result`, `result.get` raises AttributeError, the blanket
    `except` swallows it, and the function returns `[query]`. This test pins
    that the array case now fans out for real.
    """

    def test_array_response_no_longer_collapses_to_single_query(self, fake_llm):
        client = fake_llm(json.dumps(THREE))
        result = expand_query(QUERY)

        assert result != [QUERY], "regressed: array response collapsed to no-op"
        assert len(result) == 4
        assert client.calls == 1

    def test_old_implementation_would_have_collapsed(self, fake_llm):
        """Executes the old logic verbatim to prove the bug was real."""
        parsed = json.loads(json.dumps(THREE))
        with pytest.raises(AttributeError):
            parsed.get("queries", parsed.get("variations", [QUERY]))


class TestCoerceVariations:
    @pytest.mark.parametrize(
        "payload,expected",
        [
            (["a", "b"], ["a", "b"]),
            ({"queries": ["a"]}, ["a"]),
            ({"variations": ["a"]}, ["a"]),
            ({}, []),
            ([], []),
            ("prose", []),
            (None, []),
            (5, []),
            ([" padded "], ["padded"]),
        ],
    )
    def test_shapes(self, payload, expected):
        assert rag_retrieval._coerce_variations(payload) == expected

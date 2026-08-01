"""The LLM reranker must never fail invisibly again.

Background, so the next reader does not have to rediscover it.

``rerank_results`` calls ``gpt-5-mini`` with ``max_completion_tokens=100``.
gpt-5-mini is a *reasoning* model: reasoning tokens are drawn from that budget
before a single visible character is emitted. Measured against the live API,
that call returned ``finish_reason="length"``, ``content=""`` and
``reasoning_tokens=100`` -- the whole budget spent thinking, nothing left to
answer with. ``json.loads("")`` raised, and a bare ``except`` returned the
unranked list.

So the reranker failed on **every** call, and nothing recorded it. The eval
caught it only by arithmetic: a rerank arm produced recall@10, NDCG@10 and MRR
*bit-identical* to the unranked control -- 0.22000627228526437 against
0.22000627228526437 -- at n=338 and again at n=100. No working reranker can
reproduce a control to 17 significant figures on three rank-sensitive metrics.

These tests pin the two properties that would have made it visible on day one:
the failure is counted, and the empty-body case is distinguishable from a parse
failure. They deliberately do **not** assert the token number itself -- that is
a tuning parameter and will change. What must not change is that a reranker
which does not rerank says so.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import rag_retrieval  # noqa: E402


def _chunks(n: int = 10):
    return [{"id": f"c{i}", "content": f"passage {i}"} for i in range(n)]


def _response(content: str, finish_reason: str = "stop"):
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = content
    response.choices[0].finish_reason = finish_reason
    response.usage.completion_tokens = 100
    return response


@pytest.fixture(autouse=True)
def _reset_stats():
    for key in rag_retrieval._RERANK_STATS:
        rag_retrieval._RERANK_STATS[key] = 0
    yield


def test_an_empty_response_is_counted_not_swallowed():
    """The exact production failure: budget exhausted, empty body, no reorder.

    The fallback is correct behaviour -- a reranker that takes down retrieval is
    worse than one that declines to reorder. What was wrong was that it was
    silent, so "ran and changed nothing" and "never ran" looked identical from
    outside.
    """
    with patch.object(rag_retrieval, "get_openai_client") as client:
        client.return_value.chat.completions.create.return_value = _response("", "length")
        out = rag_retrieval.rerank_results(_chunks(), "a query", top_k=5)

    assert len(out) == 5, "the fallback must still return usable results"
    stats = rag_retrieval.rerank_stats()
    assert stats["empty_response"] == 1, "an empty body must be counted"
    assert stats["reranked"] == 0, "nothing was reranked, and it must not claim otherwise"


def test_an_empty_body_is_distinguishable_from_a_parse_failure():
    """Different causes, different fixes: a budget too small vs a bad answer."""
    with patch.object(rag_retrieval, "get_openai_client") as client:
        client.return_value.chat.completions.create.return_value = _response("not json at all")
        rag_retrieval.rerank_results(_chunks(), "a query", top_k=5)

    stats = rag_retrieval.rerank_stats()
    assert stats["failed"] == 1
    assert stats["empty_response"] == 0, (
        "a parse failure must not be filed as an empty response, or the counter "
        "stops pointing at the cause"
    )


def test_a_successful_rerank_reorders_and_is_counted():
    with patch.object(rag_retrieval, "get_openai_client") as client:
        client.return_value.chat.completions.create.return_value = _response(
            '{"indices": [7, 2, 0, 9, 4]}'
        )
        out = rag_retrieval.rerank_results(_chunks(), "a query", top_k=5)

    assert [c["id"] for c in out] == ["c7", "c2", "c0", "c9", "c4"]
    assert rag_retrieval.rerank_stats() == {
        "reranked": 1,
        "failed": 0,
        "empty_response": 0,
    }


def test_the_request_asks_for_json_and_funds_its_own_reasoning():
    """Two parameters, both of which the production failure turned on.

    Asserted as properties rather than exact values: the budget must be large
    enough that reasoning cannot plausibly consume all of it, and the response
    format must be constrained since the prompt asks for JSON. A future tuning
    change should be free to move the number without failing this.
    """
    with patch.object(rag_retrieval, "get_openai_client") as client:
        create = client.return_value.chat.completions.create
        create.return_value = _response('{"indices": [1, 2, 3, 4, 5]}')
        rag_retrieval.rerank_results(_chunks(), "a query", top_k=5)

    kwargs = create.call_args.kwargs
    assert kwargs["response_format"] == {"type": "json_object"}
    assert kwargs["max_completion_tokens"] >= 500, (
        "a reasoning model spends this budget on reasoning first; 100 left "
        "nothing for the answer and produced an empty body on every call"
    )

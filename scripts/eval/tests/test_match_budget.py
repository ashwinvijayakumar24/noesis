"""Spend guardrails for the OpenReview matcher (scripts/eval/match.py).

Before this, match.py called `client.chat.completions.create` directly: its
calls were invisible to `llm_budget`, unbounded by NOESIS_LLM_MAX_CALLS /
NOESIS_LLM_MAX_SPEND_USD, and unaffected by NOESIS_LLM_KILL_SWITCH /
EVAL_REPLAY_ONLY. A measured run reporting $0.22 had made six additional
uncounted matcher calls, so every cost figure was a lower bound.

Every "LLM call" here is a MagicMock; several tests assert it was NEVER called,
which is the only way to prove a guardrail actually blocks rather than merely
records.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

EVAL_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = EVAL_DIR.parents[1] / "services" / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

from app.core import llm_budget  # noqa: E402
from app.core.llm_budget import LLMBudgetExceeded, LLMCallBlocked, llm_label  # noqa: E402

import match  # noqa: E402


#: Env that must not leak in from the developer's shell. A stray
#: NOESIS_LLM_KILL_SWITCH would make every "was it blocked" assertion pass for
#: the wrong reason, and a stray ceiling would break the accounting tests.
_AMBIENT_ENV = (
    "NOESIS_LLM_KILL_SWITCH",
    "EVAL_REPLAY_ONLY",
    "NOESIS_LLM_MAX_CALLS",
    "NOESIS_LLM_MAX_SPEND_USD",
    "NOESIS_LLM_USAGE_LOG",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in _AMBIENT_ENV:
        monkeypatch.delenv(name, raising=False)
    llm_budget.reset()
    yield
    llm_budget.reset()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _vector(seed: float) -> list[float]:
    """Two near-identical unit-ish vectors so the cosine prefilter keeps pairs."""
    return [1.0, seed, 0.0]


def fake_embedder(n_calls: list[int] | None = None):
    def embed(texts: list[str]) -> list[list[float]]:
        if n_calls is not None:
            n_calls.append(len(texts))
        return [_vector(0.01 * i) for i in range(len(texts))]

    return embed


ITEMS = [{"id": "n1", "text": "The evaluation lacks a baseline comparison."}]
UNITS = [{"unit_id": "u1", "text": "No baseline is reported in the evaluation."}]


def make_client(n_pairs: int = 1, prompt_tokens: int = 1200, completion_tokens: int = 300):
    """A mock OpenAI client returning a well-formed matcher response with usage."""
    payload = {
        "pairs": [
            {"index": i, "confirmed": True, "reason": "same concern"}
            for i in range(n_pairs)
        ]
    }
    message = MagicMock()
    message.content = json.dumps(payload)
    choice = MagicMock()
    choice.message = message
    usage = MagicMock()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = completion_tokens
    usage.prompt_tokens_details = None
    response = MagicMock()
    response.choices = [choice]
    response.usage = usage

    client = MagicMock(name="openai_client")
    client.chat.completions.create.return_value = response
    return client


def run_match(tmp_path, client=None, embedder=None, stats=None):
    return match.match(
        ITEMS,
        UNITS,
        cache_dir=tmp_path / "cache",
        embedder=embedder or fake_embedder(),
        client=client if client is not None else make_client(),
        stats=stats,
    )


# ---------------------------------------------------------------------------
# Blocking
# ---------------------------------------------------------------------------

def test_kill_switch_blocks_matcher_call(tmp_path, monkeypatch):
    monkeypatch.setenv("NOESIS_LLM_KILL_SWITCH", "1")
    client = make_client()
    with pytest.raises(LLMCallBlocked) as exc:
        run_match(tmp_path, client=client)
    assert "NOESIS_LLM_KILL_SWITCH" in str(exc.value)
    client.chat.completions.create.assert_not_called()


def test_replay_only_blocks_matcher_call_with_distinct_message(tmp_path, monkeypatch):
    monkeypatch.setenv("EVAL_REPLAY_ONLY", "1")
    client = make_client()
    with pytest.raises(LLMCallBlocked) as exc:
        run_match(tmp_path, client=client)
    message = str(exc.value)
    assert "EVAL_REPLAY_ONLY" in message
    assert "cached results" in message
    assert "NOESIS_LLM_KILL_SWITCH" not in message
    client.chat.completions.create.assert_not_called()


def test_kill_switch_blocks_before_the_embedding_call(tmp_path, monkeypatch):
    """The embedding path is guarded too, and it is the FIRST network call --
    so a blocked run never reaches the embedder at all."""
    monkeypatch.setenv("NOESIS_LLM_KILL_SWITCH", "1")
    embed_calls: list[int] = []
    with pytest.raises(LLMCallBlocked):
        run_match(tmp_path, embedder=fake_embedder(embed_calls))
    assert embed_calls == []


def test_call_ceiling_halts_matching(tmp_path, monkeypatch):
    """One embedding call fills the ceiling; the confirmation call is refused."""
    monkeypatch.setenv("NOESIS_LLM_MAX_CALLS", "1")
    client = make_client()
    with pytest.raises(LLMBudgetExceeded) as exc:
        run_match(tmp_path, client=client)
    assert "NOESIS_LLM_MAX_CALLS=1" in str(exc.value)
    client.chat.completions.create.assert_not_called()
    # The one call that did happen (the embedding) was recorded.
    assert llm_budget.totals()["calls"] == 1


def test_ceiling_trip_is_not_swallowed_by_the_bisect_retry(tmp_path, monkeypatch):
    """`_confirm_chunk` bisects on RuntimeError, and LLMGuardrailError subclasses
    RuntimeError -- a tripped ceiling must halt, not be retried in halves."""
    monkeypatch.setenv("NOESIS_LLM_MAX_CALLS", "1")
    confirmer = MagicMock(name="confirmer")
    with pytest.raises(LLMBudgetExceeded):
        match.match(
            ITEMS,
            UNITS,
            cache_dir=tmp_path / "cache",
            embedder=fake_embedder(),
            confirmer=confirmer,
        )
    confirmer.assert_not_called()


def test_spend_ceiling_halts_matching(tmp_path, monkeypatch):
    monkeypatch.setenv("NOESIS_LLM_MAX_SPEND_USD", "0.0000001")
    client = make_client()
    with pytest.raises(LLMBudgetExceeded):
        run_match(tmp_path, client=client)
    client.chat.completions.create.assert_not_called()


# ---------------------------------------------------------------------------
# Accounting
# ---------------------------------------------------------------------------

def test_completed_matcher_call_is_recorded_under_its_own_label(tmp_path):
    client = make_client()
    matches = run_match(tmp_path, client=client)
    assert matches and matches[0]["confirmed"] is True
    client.chat.completions.create.assert_called_once()

    by_label = llm_budget.by_label()
    assert "match:confirm" in by_label
    confirm = by_label["match:confirm"]
    assert confirm["calls"] == 1
    assert confirm["prompt_tokens"] == 1200
    assert confirm["completion_tokens"] == 300
    assert confirm["estimated_usd"] > 0
    # Nothing landed on a bare model name, which is what would silently blend
    # matcher spend into a node's cost.
    assert all(label.startswith("match") for label in by_label)


def test_embedding_calls_are_accounted(tmp_path):
    run_match(tmp_path, client=make_client())
    by_label = llm_budget.by_label()
    assert "match:embed" in by_label
    embed = by_label["match:embed"]
    assert embed["calls"] == 1
    # Both sides of the comparison were embedded in a single batch.
    assert embed["prompt_tokens"] == match._count_tokens(
        [ITEMS[0]["text"], UNITS[0]["text"]]
    )
    assert embed["estimated_usd"] > 0
    assert llm_budget.by_model()["text-embedding-3-small"]["calls"] == 1


def test_cache_hits_cost_nothing(tmp_path):
    cache = tmp_path / "cache"
    match.match(ITEMS, UNITS, cache_dir=cache, embedder=fake_embedder(),
                client=make_client())
    first = llm_budget.totals()["calls"]
    llm_budget.reset()

    embed_calls: list[int] = []
    client = make_client()
    match.match(ITEMS, UNITS, cache_dir=cache, embedder=fake_embedder(embed_calls),
                client=client)
    assert first == 2  # one embed batch + one confirm
    assert embed_calls == []
    client.chat.completions.create.assert_not_called()
    assert llm_budget.totals()["calls"] == 0


def test_ambient_node_label_is_composed_not_overridden(tmp_path):
    """node_eval wraps the matcher in llm_label('match:<node>'). Per-node
    attribution must survive, and the 'match' prefix must too."""
    with llm_label("match:reviewer_panel"):
        run_match(tmp_path, client=make_client())
    labels = set(llm_budget.by_label())
    assert labels == {"match:reviewer_panel:embed", "match:reviewer_panel:confirm"}


def test_label_prefix_survives_a_non_match_ambient_label(tmp_path):
    with llm_label("reviewer_panel"):
        run_match(tmp_path, client=make_client())
    assert all(label.startswith("match:") for label in llm_budget.by_label())


def test_matcher_spend_is_separable_from_node_spend(tmp_path):
    """The whole point of the label: a report can subtract matcher cost."""
    llm_budget.record_usage(model="gpt-5.2", prompt_tokens=5000,
                            completion_tokens=1000, label="reviewer_panel")
    run_match(tmp_path, client=make_client())

    by_label = llm_budget.by_label()
    matcher = sum(v["estimated_usd"] for k, v in by_label.items() if k.startswith("match"))
    node = by_label["reviewer_panel"]["estimated_usd"]
    assert matcher > 0
    assert node > 0
    assert llm_budget.total_spend_usd() == pytest.approx(matcher + node)

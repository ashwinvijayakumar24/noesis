"""Reproducibility and auditability of the matcher (scripts/eval/match.py).

Two defects motivate this file.

**The confirmation judge is not deterministic.** A head-to-head re-run under the
same config hash moved the DAG arm's confirmed-unit count 56 -> 57 with
``temperature=0`` set throughout. Reproducibility therefore has to come from the
cache being complete, not from the model being well-behaved -- so the tests below
prove the cache is *authoritative* (a written verdict is never re-judged, even
by a confirmer that would answer differently) and that a run says out loud
whether it was served entirely from cache.

**Matcher decisions could not be audited.** ``eval/results/headtohead.jsonl``
persisted metrics and no texts, so nobody could check which finding was credited
against which review unit. ``match(decisions=[])`` is that record, and the tests
pin its two hard cases: a credited pair, and an item that never cleared the
cosine prefilter -- which produces no pair at all and so used to leave no trace.

Every "LLM call" here is a stub. None of these tests touch the network.
"""

import json
import sys
from pathlib import Path

import pytest

EVAL_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = EVAL_DIR.parents[1] / "services" / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

from app.core import llm_budget  # noqa: E402

import match  # noqa: E402


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


ITEMS = [
    {"id": "n1", "text": "The evaluation lacks a baseline comparison."},
    {"id": "n2", "text": "The paper is enjoyable and the figures are pretty."},
]
UNITS = [{"unit_id": "u1", "text": "No baseline is reported in the evaluation."}]


def embedder(texts):
    """n1 and u1 are near-parallel; n2 is orthogonal to both.

    Hand-built rather than mocked at random so the prefilter outcome is a fact
    about the fixture, not about whichever vectors a stub happened to return:
    n1.u1 is ~1.0 and clears 0.55, n2.u1 is 0.0 and cannot.
    """
    table = {
        ITEMS[0]["text"]: [1.0, 0.02, 0.0],
        ITEMS[1]["text"]: [0.0, 0.0, 1.0],
        UNITS[0]["text"]: [1.0, 0.0, 0.0],
    }
    return [table[text] for text in texts]


def confirmer(verdict: bool, reason: str, calls: list | None = None):
    def confirm(pairs):
        if calls is not None:
            calls.append(len(pairs))
        return [
            {"index": p["index"], "confirmed": verdict, "reason": reason} for p in pairs
        ]

    return confirm


def run(cache_dir, confirm, decisions=None, stats=None):
    return match.match(
        ITEMS,
        UNITS,
        cache_dir=cache_dir,
        embedder=embedder,
        confirmer=confirm,
        decisions=decisions,
        stats=stats,
    )


# ---------------------------------------------------------------------------
# Cache key covers everything that changes a verdict
# ---------------------------------------------------------------------------


def test_cache_key_changes_with_the_judge_model():
    """The old key was (prompt_version, pair) only, so swapping the judge served
    the previous model's verdict as if it were the new one's."""
    base = match._confirm_cache_key("a", "b")
    assert match._confirm_cache_key("a", "b", model="gpt-4o") != base


def test_cache_key_changes_with_the_prompt_version():
    base = match._confirm_cache_key("a", "b")
    assert match._confirm_cache_key("a", "b", prompt_version="match_v2") != base


def test_cache_key_changes_with_the_pair():
    base = match._confirm_cache_key("a", "b")
    assert match._confirm_cache_key("a", "c") != base
    assert match._confirm_cache_key("c", "b") != base


def test_legacy_key_is_offered_only_under_the_config_that_wrote_it():
    """The 2000-odd pre-existing entries were written under match_v1/gpt-5.2 and
    are valid for that and nothing else."""
    assert match._legacy_confirm_cache_key("a", "b") is not None
    assert match._legacy_confirm_cache_key("a", "b", model="gpt-4o") is None
    assert match._legacy_confirm_cache_key("a", "b", prompt_version="match_v2") is None


def test_legacy_entry_is_adopted_rather_than_re_judged(tmp_path):
    """The warm cache must survive the re-key, or fixing the key costs a re-spend
    of every verdict in it."""
    confirm_dir = tmp_path / "confirm"
    confirm_dir.mkdir(parents=True)
    legacy = match._legacy_confirm_cache_key(ITEMS[0]["text"], UNITS[0]["text"])
    (confirm_dir / f"{legacy}.json").write_text(
        json.dumps({"confirmed": True, "reason": "legacy verdict"})
    )

    calls: list = []
    stats: dict = {}
    matches = run(tmp_path, confirmer(False, "fresh", calls), stats=stats)

    assert calls == []  # no live judge call at all
    assert matches[0]["reason"] == "legacy verdict"
    assert stats["confirm_cache_hits_legacy"] == 1
    assert stats["confirm_live_verdicts"] == 0
    # Adopted under the new key, so the fallback stops being load-bearing.
    new_key = match._confirm_cache_key(ITEMS[0]["text"], UNITS[0]["text"])
    assert (confirm_dir / f"{new_key}.json").exists()


# ---------------------------------------------------------------------------
# A written verdict is authoritative
# ---------------------------------------------------------------------------


def test_two_runs_agree_even_when_the_judge_would_not(tmp_path):
    """The determinism proof in miniature: the second run's confirmer answers the
    opposite, and the counts are identical anyway because it is never asked."""
    first = run(tmp_path, confirmer(True, "same concern"))
    calls: list = []
    second = run(tmp_path, confirmer(False, "flipped"), stats={}, decisions=None)

    assert first == second
    assert sum(1 for m in first if m["confirmed"]) == 1
    assert calls == []


def test_cached_verdict_is_not_overwritten_by_a_later_live_one(tmp_path):
    confirm_dir = tmp_path / "confirm"
    run(tmp_path, confirmer(True, "same concern"))
    key = match._confirm_cache_key(ITEMS[0]["text"], UNITS[0]["text"])
    before = (confirm_dir / f"{key}.json").read_text()
    run(tmp_path, confirmer(False, "flipped"))
    assert (confirm_dir / f"{key}.json").read_text() == before


def test_run_reports_cache_versus_live_counts(tmp_path):
    cold: dict = {}
    run(tmp_path, confirmer(True, "same concern"), stats=cold)
    assert cold["confirm_live_verdicts"] == 1
    assert cold["confirm_cache_hits"] == 0
    assert cold["confirm_fully_cached"] == 0

    warm: dict = {}
    run(tmp_path, confirmer(True, "same concern"), stats=warm)
    assert warm["confirm_live_verdicts"] == 0
    assert warm["confirm_cache_hits"] == 1
    assert warm["confirm_fully_cached"] == 1


def test_a_changed_prompt_version_does_not_serve_the_old_verdict(tmp_path, monkeypatch):
    run(tmp_path, confirmer(True, "same concern"))
    monkeypatch.setattr(match, "PROMPT_VERSION", "match_v2")
    stats: dict = {}
    matches = run(tmp_path, confirmer(False, "re-judged under v2"), stats=stats)
    assert stats["confirm_live_verdicts"] == 1
    assert stats["confirm_cache_hits"] == 0
    assert matches[0]["confirmed"] is False


# ---------------------------------------------------------------------------
# The decision record
# ---------------------------------------------------------------------------


def test_decisions_record_a_credited_pair_with_both_texts(tmp_path):
    decisions: list = []
    run(tmp_path, confirmer(True, "both say the baseline is missing"), decisions=decisions)
    credited = [d for d in decisions if d["stage"] == "confirmed"]
    assert len(credited) == 1
    row = credited[0]
    assert row["noesis_text"] == ITEMS[0]["text"]
    assert row["unit_text"] == UNITS[0]["text"]
    assert row["unit_id"] == "u1"
    assert row["reason"] == "both say the baseline is missing"
    assert row["cosine"] >= row["cos_threshold"]
    assert row["verdict_source"] == "live"
    assert row["confirm_model"] == match.CONFIRM_MODEL
    assert row["prompt_version"] == match.PROMPT_VERSION


def test_decisions_record_a_rejection_by_the_judge(tmp_path):
    decisions: list = []
    run(tmp_path, confirmer(False, "same topic, different concern"), decisions=decisions)
    rejected = [d for d in decisions if d["stage"] == "rejected"]
    assert len(rejected) == 1
    assert rejected[0]["reason"] == "same topic, different concern"
    assert rejected[0]["cosine"] >= rejected[0]["cos_threshold"]


def test_decisions_record_items_that_never_reached_the_judge(tmp_path):
    """Without this row an uncredited finding is simply absent from the record,
    which is indistinguishable from never having been scored."""
    decisions: list = []
    run(tmp_path, confirmer(True, "y"), decisions=decisions)
    below = [d for d in decisions if d["stage"] == "below_cosine_threshold"]
    assert [d["noesis_id"] for d in below] == ["n2"]
    row = below[0]
    assert row["noesis_text"] == ITEMS[1]["text"]
    assert row["unit_id"] == "u1"  # the nearest unit, named
    assert row["cosine"] < row["cos_threshold"]
    assert row["confirmed"] is False
    assert row["verdict_source"] is None


def test_every_item_appears_in_the_record(tmp_path):
    decisions: list = []
    run(tmp_path, confirmer(True, "y"), decisions=decisions)
    assert {d["noesis_id"] for d in decisions} == {"n1", "n2"}


def test_decision_rows_are_json_serialisable(tmp_path):
    """The record is written as JSONL by two callers in another repo; a row that
    cannot be encoded would take the audit trail down with it."""
    decisions: list = []
    run(tmp_path, confirmer(True, "y"), decisions=decisions)
    for row in decisions:
        assert json.loads(json.dumps(row, sort_keys=True)) == row


def test_decisions_are_identical_across_two_runs(tmp_path):
    first: list = []
    run(tmp_path, confirmer(True, "same concern"), decisions=first)
    second: list = []
    run(tmp_path, confirmer(False, "flipped"), decisions=second)
    # verdict_source is the one field that legitimately differs -- live, then
    # cache. Everything a recall number depends on is byte-identical.
    strip = lambda rows: [  # noqa: E731
        {k: v for k, v in row.items() if k != "verdict_source"} for row in rows
    ]
    assert strip(first) == strip(second)
    assert [d["verdict_source"] for d in first] == ["live", None]
    assert [d["verdict_source"] for d in second] == ["cache", None]

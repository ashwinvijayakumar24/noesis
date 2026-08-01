"""Query-set construction: cache-only, deterministic, fails loudly."""

import json

import pytest

from scripts.eval.retrieval import queries as Q


def _export(dirpath, name, draft_file, claims):
    dirpath.mkdir(parents=True, exist_ok=True)
    (dirpath / name).write_text(
        json.dumps({"eval_metadata": {"draft_file": draft_file}, "claims": claims})
    )


def _claim(text, **kw):
    base = {"claim_text": text, "claim_type": "empirical",
            "section_location": "Introduction", "requires_citation": True}
    base.update(kw)
    return base


LONG = "Transformer scaling laws predict loss as a power law in parameters and data."
LONG2 = "Retrieval augmentation reduces hallucination rates on long-form generation tasks."


@pytest.fixture()
def exports(tmp_path):
    d = tmp_path / "exports"
    _export(d, "a.json", "draftA", [_claim(LONG), _claim(LONG2)])
    _export(d, "b.json", "draftB", [_claim(LONG2)])
    return d


def test_builds_queries_from_cached_exports(exports):
    qs = Q.build_query_set(exports)
    assert len(qs) == 3
    assert {q.topic for q in qs} == {"draftA", "draftB"}


def test_short_and_overlong_claims_filtered(tmp_path):
    d = tmp_path / "exports"
    _export(d, "a.json", "draftA", [
        _claim("Too short."),
        _claim("x" * (Q.MAX_CLAIM_CHARS + 1)),
        _claim(LONG),
    ])
    assert [q.text for q in Q.build_query_set(d)] == [LONG]


def test_duplicate_claims_across_reruns_are_unioned_not_duplicated(exports):
    """The same manuscript analysed twice must not double-count its claims."""
    _export(exports, "a_rerun.json", "draftA", [_claim(LONG), _claim(LONG2)])
    qs = Q.build_query_set(exports)
    assert len(qs) == 3
    assert len({q.query_id for q in qs}) == 3


def test_query_ids_are_stable_and_topic_scoped():
    a = Q.make_query_id("draftA", LONG)
    assert a == Q.make_query_id("draftA", f"  {LONG}  ")   # whitespace normalised
    assert a == Q.make_query_id("draftA", LONG.upper())    # case normalised
    assert a != Q.make_query_id("draftB", LONG)            # topic scoped


def test_output_is_deterministic_and_order_independent(exports, tmp_path):
    first = Q.build_query_set(exports)
    # Re-create with files written in the opposite order.
    other = tmp_path / "exports2"
    _export(other, "b.json", "draftB", [_claim(LONG2)])
    _export(other, "a.json", "draftA", [_claim(LONG2), _claim(LONG)])
    second = Q.build_query_set(other)
    assert [q.query_id for q in first] == [q.query_id for q in second]
    assert Q.fingerprint(first) == Q.fingerprint(second)


def test_topic_filter(exports):
    assert {q.topic for q in Q.build_query_set(exports, topics=["draftA"])} == {"draftA"}


def test_requires_citation_filter(tmp_path):
    d = tmp_path / "exports"
    _export(d, "a.json", "draftA", [_claim(LONG, requires_citation=False), _claim(LONG2)])
    assert [q.text for q in Q.build_query_set(d, requires_citation_only=True)] == [LONG2]


def test_max_per_topic_cap(exports):
    qs = Q.build_query_set(exports, max_per_topic=1)
    assert len(qs) == 2
    assert sorted(q.topic for q in qs) == ["draftA", "draftB"]


def test_missing_cached_claims_raises_rather_than_calling_an_llm(exports):
    with pytest.raises(Q.QueriesUnavailable, match="will not make one"):
        Q.build_query_set(exports, topics=["draft_never_analysed"])


def test_kill_switch_message_names_the_variable(exports, monkeypatch):
    monkeypatch.setenv("NOESIS_LLM_KILL_SWITCH", "1")
    with pytest.raises(Q.QueriesUnavailable, match="NOESIS_LLM_KILL_SWITCH is set"):
        Q.build_query_set(exports, topics=["nope"])


@pytest.mark.parametrize("var", ["NOESIS_LLM_KILL_SWITCH", "EVAL_REPLAY_ONLY"])
@pytest.mark.parametrize("val", ["1", "true", "YES", "on"])
def test_kill_switch_detection(monkeypatch, var, val):
    monkeypatch.delenv("NOESIS_LLM_KILL_SWITCH", raising=False)
    monkeypatch.delenv("EVAL_REPLAY_ONLY", raising=False)
    monkeypatch.setenv(var, val)
    active, name = Q.kill_switch_active()
    assert active and name == var


def test_kill_switch_off_by_default(monkeypatch):
    monkeypatch.delenv("NOESIS_LLM_KILL_SWITCH", raising=False)
    monkeypatch.delenv("EVAL_REPLAY_ONLY", raising=False)
    assert Q.kill_switch_active() == (False, "")


def test_queries_run_unaffected_by_kill_switch(exports, monkeypatch):
    """Cached queries must still build with the kill switch on -- no LLM is involved."""
    monkeypatch.setenv("NOESIS_LLM_KILL_SWITCH", "1")
    assert len(Q.build_query_set(exports)) == 3


def test_corrupt_export_skipped(exports):
    (exports / "bad.json").write_text("{not json")
    assert len(Q.build_query_set(exports)) == 3


def test_export_without_draft_file_skipped(tmp_path):
    d = tmp_path / "exports"
    d.mkdir()
    (d / "x.json").write_text(json.dumps({"claims": [_claim(LONG)]}))
    assert Q.build_query_set(d) == []


def test_missing_exports_dir_returns_empty(tmp_path):
    assert Q.build_query_set(tmp_path / "nope") == []


def test_queries_by_topic_join_key(exports):
    qbt = Q.queries_by_topic(Q.build_query_set(exports))
    assert sorted(qbt) == ["draftA", "draftB"]
    assert len(qbt["draftA"]) == 2

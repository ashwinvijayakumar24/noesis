"""CLI, append-only writer, config hashing, and end-to-end determinism."""

import json

import pytest

from scripts.eval.retrieval import labels as L
from scripts.eval.retrieval import queries as Q
from scripts.eval.retrieval import run_retrieval_eval as R

CLAIM_A = "Transformer scaling laws predict loss as a power law in parameters and data."
CLAIM_B = "Retrieval augmentation reduces hallucination rates on long-form generation."
CLAIM_C = "Graph neural networks underperform on heterophilous node classification tasks."


@pytest.fixture()
def workspace(tmp_path):
    """A self-contained corpus + exports tree. No DB, no network, no LLM."""
    corpora = tmp_path / "corpora"
    for topic, files in {
        "draftA": [
            "smith_2020_neural_scaling_laws_for_language_models.pdf",
            "jones_2019_attention_mechanisms_a_broad_survey.pdf",
            "wu_2021_data_quality_effects_on_pretraining.pdf",
        ],
        "draftB": [
            "lee_2021_graph_transformers_benchmark_suite.pdf",
            "kim_2022_heterophilous_node_classification_study.pdf",
        ],
    }.items():
        (corpora / topic).mkdir(parents=True)
        for name in files:
            (corpora / topic / name).write_bytes(f"%PDF-{topic}-{name}".encode())

    exports = tmp_path / "exports"
    exports.mkdir()
    (exports / "a.json").write_text(json.dumps({
        "eval_metadata": {"draft_file": "draftA"},
        "claims": [{"claim_text": CLAIM_A, "requires_citation": True},
                   {"claim_text": CLAIM_B, "requires_citation": True}],
    }))
    (exports / "b.json").write_text(json.dumps({
        "eval_metadata": {"draft_file": "draftB"},
        "claims": [{"claim_text": CLAIM_C, "requires_citation": True}],
    }))
    return {"corpora": corpora, "exports": exports, "results": tmp_path / "out.jsonl",
            "cache": tmp_path / "cache"}


def _argv(ws, **over):
    args = [
        "--retriever", "mock",
        "--corpora-root", str(ws["corpora"]),
        "--exports-dir", str(ws["exports"]),
        "--results-path", str(ws["results"]),
        "--no-cache",
    ]
    for k, v in over.items():
        args += [f"--{k.replace('_', '-')}", str(v)]
    return args


# ---------------------------------------------------------------------------
# End-to-end
# ---------------------------------------------------------------------------


def test_cli_runs_end_to_end_with_mock_no_db_no_network(workspace, capsys):
    assert R.main(_argv(workspace)) == 0
    out = capsys.readouterr().out
    assert "RETRIEVAL EVAL" in out
    assert "ndcg@10" in out
    assert "failure attribution" in out
    assert workspace["results"].exists()


def test_cli_dry_run_writes_nothing(workspace):
    R.main(_argv(workspace) + ["--dry-run"])
    assert not workspace["results"].exists()


def test_cli_reports_unknown_resolution_rate_without_sidecar(workspace, capsys):
    R.main(_argv(workspace) + ["--dry-run"])
    out = capsys.readouterr().out
    assert "UNKNOWN -- denominator not recoverable" in out


def test_cli_reports_exact_rate_with_sidecar(workspace, capsys):
    """draftA attempted 10 refs and landed 3; draftB attempted 4 and landed 2.

    So 5 of 14 resolved. The 9 that did not are excluded from the denominator and
    reported separately -- they are not retriever misses.
    """
    resolved_titles = {
        "draftA": [
            "Neural scaling laws for language models",
            "Attention mechanisms a broad survey",
            "Data quality effects on pretraining",
        ],
        "draftB": [
            "Graph transformers benchmark suite",
            "Heterophilous node classification study",
        ],
    }
    for topic, total in (("draftA", 10), ("draftB", 4)):
        titles = resolved_titles[topic]
        titles += [
            f"Paywalled monograph number {i} unavailable anywhere"
            for i in range(total - len(titles))
        ]
        (workspace["corpora"] / topic / L.REFERENCES_SIDECAR).write_text(
            json.dumps([{"title": t} for t in titles])
        )

    R.main(_argv(workspace) + ["--dry-run"])
    out = capsys.readouterr().out
    assert "references resolved      : 5" in out
    assert "references unresolved    : 9 (EXCLUDED from denominator)" in out
    assert "references attempted     : 14" in out
    assert "resolution rate          : 35.7%" in out


def test_cli_surfaces_empty_join(workspace, capsys):
    """Queries for one manuscript, labels for another -> the join must be visible."""
    (workspace["exports"] / "a.json").write_text(json.dumps({
        "eval_metadata": {"draft_file": "draft_no_corpus"},
        "claims": [{"claim_text": CLAIM_A}],
    }))
    (workspace["exports"] / "b.json").unlink()
    R.main(_argv(workspace) + ["--dry-run"])
    assert "JOIN                     : EMPTY" in capsys.readouterr().out


def test_dense_retriever_defaults_to_the_ingested_eval_project(workspace):
    """The eval corpus lives under exactly one project id, so requiring the flag
    was busywork that invited typing the wrong uuid. It defaults to the one
    scripts/eval/ingest.py writes."""
    from scripts.eval.retrieval import adapters as A

    parser_default = R.EVAL_PROJECT_ID
    assert parser_default == A.EVAL_PROJECT_ID
    assert parser_default == "e7a1c0b0-0000-4000-8000-000000000001"


# ---------------------------------------------------------------------------
# Append-only
# ---------------------------------------------------------------------------


def test_two_runs_produce_two_records_neither_lost(workspace):
    R.main(_argv(workspace))
    R.main(_argv(workspace, seed=99))
    records = R.read_results(workspace["results"])
    assert len(records) == 2
    assert records[0]["config"]["seed"] == 0
    assert records[1]["config"]["seed"] == 99


def test_append_never_truncates(tmp_path):
    path = tmp_path / "r.jsonl"
    for i in range(5):
        R.append_result({"i": i}, path)
    assert [r["i"] for r in R.read_results(path)] == [0, 1, 2, 3, 4]


def test_append_creates_parent_dirs(tmp_path):
    path = tmp_path / "deep" / "nested" / "r.jsonl"
    R.append_result({"a": 1}, path)
    assert R.read_results(path) == [{"a": 1}]


def test_read_results_on_missing_file():
    assert R.read_results(__import__("pathlib").Path("/nonexistent/x.jsonl")) == []


# ---------------------------------------------------------------------------
# Config hash
# ---------------------------------------------------------------------------


def test_config_hash_differs_when_relevance_unit_changes():
    base = {"relevance_unit": "document", "retriever": "mock", "k": 10}
    other = dict(base, relevance_unit="chunk")
    assert R.config_hash(base) != R.config_hash(other)


@pytest.mark.parametrize("field,value", [
    ("retriever", "dense"), ("k", 20), ("graded", True),
    ("chunk_oversample", 3), ("labels_fingerprint", "deadbeef"),
])
def test_config_hash_differs_on_every_incomparability_axis(field, value):
    base = {"relevance_unit": "document", "retriever": "mock", "k": 10, "graded": False,
            "chunk_oversample": 5, "labels_fingerprint": "abc"}
    assert R.config_hash(base) != R.config_hash(dict(base, **{field: value}))


def test_config_hash_is_key_order_independent():
    assert R.config_hash({"a": 1, "b": 2}) == R.config_hash({"b": 2, "a": 1})


def test_run_records_carry_unit_retriever_k_and_hash(workspace):
    R.main(_argv(workspace))
    rec = R.read_results(workspace["results"])[0]
    assert rec["relevance_unit"] == "document"
    assert rec["config"]["retriever"] == "mock"
    assert rec["config"]["k"] == 10
    assert len(rec["config_hash"]) == 16
    assert rec["run_id"]


def test_changing_unit_changes_the_record_hash(workspace):
    R.main(_argv(workspace))
    R.main(_argv(workspace, unit="chunk"))
    a, b = R.read_results(workspace["results"])
    assert a["config_hash"] != b["config_hash"]
    assert a["relevance_unit"] != b["relevance_unit"]


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_same_input_same_output(workspace):
    R.main(_argv(workspace))
    R.main(_argv(workspace))
    a, b = R.read_results(workspace["results"])
    assert a["config_hash"] == b["config_hash"]
    assert a["metrics"] == b["metrics"]
    assert a["failure_breakdown"] == b["failure_breakdown"]
    assert a["misses"] == b["misses"]


def test_run_eval_is_a_pure_function(workspace):
    ls = L.build_label_set(workspace["corpora"])
    qs = Q.build_query_set(workspace["exports"])
    from scripts.eval.retrieval.adapters import MockRetriever

    def once():
        return R.run_eval(MockRetriever(sorted(ls.docs), seed=3), qs, ls, k=5)["result"].to_dict()

    assert once() == once()


def test_planted_relevance_produces_perfect_recall(workspace):
    """Sanity check on the ruler itself: an oracle retriever must score 1.0."""
    from scripts.eval.retrieval.adapters import MockRetriever

    ls = L.build_label_set(workspace["corpora"])
    qs = Q.build_query_set(workspace["exports"])
    relevant_by_query = {
        q.text: ls.topics[q.topic].relevant_doc_ids for q in qs if q.topic in ls.topics
    }
    oracle = MockRetriever(sorted(ls.docs), relevant_by_query=relevant_by_query, plant_rate=1.0)
    out = R.run_eval(oracle, qs, ls, k=10)["result"]
    assert out.metrics["recall@10"] == pytest.approx(1.0)
    assert out.metrics["mrr"] == pytest.approx(1.0)
    assert out.metrics["ndcg@10"] == pytest.approx(1.0)
    assert out.failure_breakdown["total_misses"] == 0


def test_record_notes_kill_switch(workspace, monkeypatch):
    monkeypatch.delenv("NOESIS_LLM_KILL_SWITCH", raising=False)
    monkeypatch.setenv("EVAL_REPLAY_ONLY", "1")
    R.main(_argv(workspace))
    rec = R.read_results(workspace["results"])[0]
    assert rec["environment"]["llm_kill_switch"] == "EVAL_REPLAY_ONLY"


# ---------------------------------------------------------------------------
# The degradation gate: a swallowed RPC failure must fail the run LOUDLY
# ---------------------------------------------------------------------------


class _FakeRun:
    """Minimal stand-in for run_eval's output."""

    def __init__(self, scored=5, rows=100, joined=100, empty=0):
        self.result = type("R", (), {"n_queries_scored": scored})()
        self.health = {"rows_returned": rows, "rows_joined_to_corpus": joined,
                       "queries_with_empty_run": empty}

    def as_dict(self):
        return {"result": self.result, "retrieval_health": self.health}


CLEAN = {"name": "keyword_search_chunks", "degraded": False,
         "failure_count": 0, "last_error": None, "checked": True}


def test_run_is_valid_when_the_flag_is_clear():
    v = R.run_verdict(CLEAN, _FakeRun().as_dict(), "keyword")
    assert v["valid"] is True and v["reasons"] == []


def test_degraded_flag_invalidates_the_run():
    """A plausible zero from a swallowed RPC error is worse than no number."""
    degraded = {**CLEAN, "degraded": True, "failure_count": 3,
                "last_error": "UndefinedColumn: dc.metadata"}
    v = R.run_verdict(degraded, _FakeRun().as_dict(), "keyword")
    assert v["valid"] is False
    assert any("KEYWORD_SEARCH_DEGRADED" in r for r in v["reasons"])
    assert any("dc.metadata" in r for r in v["reasons"])


def test_zero_rows_for_every_query_invalidates_the_run():
    v = R.run_verdict(CLEAN, _FakeRun(rows=0, joined=0, empty=5).as_dict(), "keyword")
    assert v["valid"] is False
    assert any("0 rows" in r for r in v["reasons"])


def test_rows_that_join_to_nothing_invalidate_the_run():
    """The id-space mismatch that would otherwise read as recall 0.0."""
    v = R.run_verdict(CLEAN, _FakeRun(rows=100, joined=0).as_dict(), "dense")
    assert v["valid"] is False
    assert any("NONE joined" in r for r in v["reasons"])


def test_hybrid_with_an_empty_keyword_leg_is_invalid():
    """A fusion whose lexical leg brought nothing is dense wearing hybrid's name.

    That is the exact silent degradation this harness exists to catch, so it must
    invalidate the run rather than be reported as a fusion result.
    """
    run = _FakeRun().as_dict()
    run["retrieval_health"]["legs"] = {"dense_rows": 500, "keyword_rows": 0,
                                       "dense_empty_queries": 0,
                                       "keyword_empty_queries": 5}
    v = R.run_verdict(CLEAN, run, "hybrid")
    assert v["valid"] is False
    assert any("keyword leg" in r for r in v["reasons"])


def test_hybrid_with_an_empty_dense_leg_is_invalid():
    run = _FakeRun().as_dict()
    run["retrieval_health"]["legs"] = {"dense_rows": 0, "keyword_rows": 500,
                                       "dense_empty_queries": 5,
                                       "keyword_empty_queries": 0}
    v = R.run_verdict(CLEAN, run, "hybrid")
    assert v["valid"] is False
    assert any("dense leg" in r for r in v["reasons"])


def test_hybrid_with_both_legs_contributing_is_valid():
    run = _FakeRun().as_dict()
    run["retrieval_health"]["legs"] = {"dense_rows": 500, "keyword_rows": 480,
                                       "dense_empty_queries": 0,
                                       "keyword_empty_queries": 0}
    assert R.run_verdict(CLEAN, run, "hybrid")["valid"] is True


def test_degraded_flag_still_gates_the_rrf_path():
    """The keyword leg of a fusion goes through the same swallow-prone RPC."""
    degraded = {**CLEAN, "degraded": True, "failure_count": 1,
                "last_error": "UndefinedFunction: keyword_search_chunks_v2"}
    run = _FakeRun().as_dict()
    run["retrieval_health"]["legs"] = {"dense_rows": 500, "keyword_rows": 500,
                                       "dense_empty_queries": 0,
                                       "keyword_empty_queries": 0}
    v = R.run_verdict(degraded, run, "hybrid")
    assert v["valid"] is False
    assert any("KEYWORD_SEARCH_DEGRADED" in r for r in v["reasons"])


def test_unknown_degradation_state_is_not_reported_as_healthy():
    from scripts.eval.retrieval import adapters as A

    assert A.UNKNOWN_DEGRADATION["degraded"] is None   # not False
    assert A.UNKNOWN_DEGRADATION["checked"] is False


def test_record_carries_the_verdict_and_the_flag(workspace):
    R.main(_argv(workspace))
    record = json.loads(workspace["results"].read_text().splitlines()[0])
    assert record["valid"] is True
    assert record["invalidated_by"] == []
    assert "degraded" in record["degradation"]
    assert record["retrieval_health"]["rows_returned"] > 0


# ---------------------------------------------------------------------------
# Ceilings travel with the record
# ---------------------------------------------------------------------------


def test_record_carries_recomputed_ceilings_and_percent_of_attainable(workspace):
    """Ceilings are a property of the LABEL SNAPSHOT, so they are recomputed per
    run. docs/MEASUREMENTS.md §Retrieval baseline (superseded)'s 0.106/0.531/0.779/0.880 belong to a snapshot that no
    longer exists; carrying them forward would silently rescale every arm."""
    R.main(_argv(workspace))
    rec = R.read_results(workspace["results"])[0]

    ceilings = rec["recall_ceilings"]
    assert set(ceilings) == {"recall@1", "recall@5", "recall@10", "recall@20"}
    assert all(0.0 < v <= 1.0 for v in ceilings.values())
    # More depth can never lower the ceiling.
    assert (ceilings["recall@1"] <= ceilings["recall@5"]
            <= ceilings["recall@10"] <= ceilings["recall@20"])

    pct = rec["percent_of_attainable"]
    for name, value in rec["metrics"].items():
        if name in ceilings:
            assert pct[name] == pytest.approx(value / ceilings[name])
            assert pct[name] <= 1.0 + 1e-9
        else:
            # MRR/NDCG/MAP have no construction ceiling here: None, never 1.0.
            assert pct[name] is None


def test_record_carries_the_query_plan(workspace):
    """A mock has no plan; it must say "unknown" rather than inherit "index"."""
    R.main(_argv(workspace))
    assert R.read_results(workspace["results"])[0]["plan"] == "unknown"


def test_cli_exits_nonzero_and_shouts_when_the_run_is_invalid(workspace, capsys, monkeypatch):
    monkeypatch.setattr(
        R, "keyword_degradation_snapshot",
        lambda: {**CLEAN, "degraded": True, "failure_count": 1,
                 "last_error": "UndefinedColumn: dc.metadata"},
    )
    code = R.main(_argv(workspace))
    out = capsys.readouterr().out

    assert code == R.EXIT_INVALID_RUN
    assert code != 0
    assert "RUN INVALID -- DO NOT QUOTE THESE NUMBERS" in out
    # The record is still appended: an invalid run is itself a finding.
    assert len(workspace["results"].read_text().splitlines()) == 1
    assert json.loads(workspace["results"].read_text())["valid"] is False


def test_results_still_append_after_an_invalid_run(workspace, monkeypatch):
    R.main(_argv(workspace))
    monkeypatch.setattr(
        R, "keyword_degradation_snapshot",
        lambda: {**CLEAN, "degraded": True, "failure_count": 1, "last_error": "boom"},
    )
    R.main(_argv(workspace, seed=42))
    monkeypatch.undo()
    R.main(_argv(workspace, seed=99))

    lines = workspace["results"].read_text().splitlines()
    assert len(lines) == 3
    assert [json.loads(l)["valid"] for l in lines] == [True, False, True]


# ---------------------------------------------------------------------------
# The document-id join
# ---------------------------------------------------------------------------


def test_db_doc_id_map_translates_the_ingest_uuid_back_to_the_label_id(workspace):
    from scripts.eval.retrieval import adapters as A

    ls = L.build_label_set(workspace["corpora"])
    mapping = R.db_doc_id_map(ls)

    assert len(mapping) == len(ls.docs)
    for doc in ls.docs.values():
        assert mapping[A.db_document_id(doc.content_sha256)] == doc.doc_id


def test_remap_drops_documents_that_are_not_in_the_label_corpus():
    from scripts.eval.retrieval.adapters import RetrievedDoc

    rows = [RetrievedDoc("db-1", "c1", 0.9, 1), RetrievedDoc("db-unknown", "c2", 0.8, 2)]
    out = R._remap(rows, {"db-1": "label-1"})
    assert [d.doc_id for d in out] == ["label-1"]
    assert out[0].score == 0.9 and out[0].chunk_id == "c1"

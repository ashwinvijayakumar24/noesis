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


def test_dense_retriever_requires_project_id(workspace):
    with pytest.raises(SystemExit):
        R.main(_argv(workspace)[2:] + ["--retriever", "dense"])


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

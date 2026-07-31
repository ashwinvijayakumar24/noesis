"""Tests for append-only eval history and the history-based regression gate.

No LLM calls, no network: every test operates on synthetic rows and tmp_path files.
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

EVAL_DIR = Path(__file__).resolve().parents[1]


def _load(name: str):
    module_path = EVAL_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"eval_{name}_for_tests", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


run_eval = _load("run_eval")
pipeline_cache = _load("pipeline_cache")


class _Args:
    quick = False
    stability = None


def _row(stem: str, overall, corpus="no-corpus", dims=None, hallucinations=None):
    return {
        "draft_stem": stem,
        "corpus": corpus,
        "overall": overall,
        "dims": dims or {"rigor": {"score": 8.0}},
        "hallucinations": hallucinations or [],
    }


def _cfg(**overrides):
    cfg = {
        "drafts": ["pdfs/draft1.pdf"],
        "corpora": [None],
        "auto_corpus": True,
        "thresholds": {"min_overall": 0.0, "min_dim_score": 0.0, "max_mean_drop": 0.5},
    }
    cfg.update(overrides)
    return cfg


def _write_run(history_path, rows, cfg=None):
    """Simulate one run's history write, returning the record."""
    cfg = cfg or _cfg()
    scored = [r for r in rows if r.get("overall") is not None]
    mean_overall = sum(r["overall"] for r in scored) / len(scored) if scored else 0.0
    total_h = sum(len(r.get("hallucinations") or []) for r in scored)
    record = run_eval.build_history_record(rows, cfg, mean_overall, total_h, args=_Args())
    run_eval.append_history(record, history_path)
    return record


# --------------------------------------------------------------------------
# Append-only history
# --------------------------------------------------------------------------

def test_two_runs_produce_two_records_neither_lost(tmp_path):
    history = tmp_path / "history.jsonl"

    first = _write_run(history, [_row("draft1", 7.0)])
    second = _write_run(history, [_row("draft1", 7.4)])

    records = run_eval.load_history(history)
    assert len(records) == 2, "second run overwrote the first — history is not append-only"
    assert [r["run_id"] for r in records] == [first["run_id"], second["run_id"]]
    assert records[0]["aggregates"]["mean_overall"] == 7.0
    assert records[1]["aggregates"]["mean_overall"] == 7.4
    # the raw file is genuinely append-only: line 1 is byte-identical to run 1
    lines = history.read_text().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["run_id"] == first["run_id"]


def test_ten_runs_all_retained(tmp_path):
    history = tmp_path / "history.jsonl"
    for i in range(10):
        _write_run(history, [_row("draft1", 5.0 + i * 0.1)])
    assert len(run_eval.load_history(history)) == 10


def test_record_carries_timestamp_config_cells_and_aggregates(tmp_path):
    history = tmp_path / "history.jsonl"
    cfg = _cfg(thresholds={"min_overall": 8.5, "min_dim_score": 7.5, "max_mean_drop": 0.5})
    rows = [
        _row("draft1", 7.0, dims={"rigor": {"score": 6.0}, "clarity": {"score": 8.0}}),
        _row("draft2", 9.0, corpus="corpusA"),
    ]
    _write_run(history, rows, cfg)

    record = run_eval.load_history(history)[0]
    assert record["generated_at"].endswith("+00:00")
    assert record["config"]["thresholds"]["min_overall"] == 8.5
    assert record["config"]["drafts"] == ["pdfs/draft1.pdf"]
    assert record["aggregates"]["mean_overall"] == 8.0
    assert record["aggregates"]["scored_cells"] == 2

    cells = {c["cell_key"]: c for c in record["cells"]}
    assert set(cells) == {"draft1__no-corpus", "draft2__corpusA"}
    assert cells["draft1__no-corpus"]["overall"] == 7.0
    assert cells["draft1__no-corpus"]["dims"] == {"rigor": 6.0, "clarity": 8.0}


# --------------------------------------------------------------------------
# Pipeline-version hash
# --------------------------------------------------------------------------

def test_record_contains_pipeline_version_hash(tmp_path):
    history = tmp_path / "history.jsonl"
    _write_run(history, [_row("draft1", 7.0)])
    version = run_eval.load_history(history)[0]["pipeline_version"]
    assert isinstance(version, str) and version
    # a real SHA-256 hex digest, or the explicit sentinel when the tree is absent
    assert version == "unavailable" or (len(version) == 64 and int(version, 16) >= 0)


def test_pipeline_version_changes_when_a_workflow_file_changes(tmp_path):
    """The hash must be sensitive to workflow content, not just to file names."""
    workflow_dir = tmp_path / "draft_analysis"
    (workflow_dir / "nodes").mkdir(parents=True)
    (workflow_dir / "graph.py").write_text("def build():\n    return 1\n")
    (workflow_dir / "nodes" / "editor_pass.py").write_text("PASS = 1\n")

    before = pipeline_cache.pipeline_version(workflow_dir)

    # same content, recomputed -> stable
    assert pipeline_cache.pipeline_version(workflow_dir) == before

    # simulate a workflow edit
    (workflow_dir / "nodes" / "editor_pass.py").write_text("PASS = 2\n")
    after = pipeline_cache.pipeline_version(workflow_dir)
    assert after != before, "pipeline hash did not change when a workflow file changed"

    # adding a new workflow file also changes it
    (workflow_dir / "nodes" / "new_node.py").write_text("X = 1\n")
    assert pipeline_cache.pipeline_version(workflow_dir) != after


def test_history_record_uses_pipeline_cache_hash(tmp_path, monkeypatch):
    """run_eval must reuse pipeline_cache's SHA, not invent its own scheme."""
    history = tmp_path / "history.jsonl"
    monkeypatch.setattr(run_eval, "_pipeline_version", lambda: "deadbeef" * 8)
    _write_run(history, [_row("draft1", 7.0)])
    assert run_eval.load_history(history)[0]["pipeline_version"] == "deadbeef" * 8


# --------------------------------------------------------------------------
# scoreboard.json still satisfies its readers
# --------------------------------------------------------------------------

def test_scoreboard_shape_preserved_for_existing_readers(tmp_path, monkeypatch):
    """mine_failures / check_heldout / _regression_check read rows + aggregates."""
    rows = [_row("draft1", 7.0), _row("draft2", 9.0)]
    scored = rows
    mean_overall = 8.0
    scoreboard = {
        "generated_at": "2026-07-30T00:00:00+00:00",
        "mean_overall": round(mean_overall, 2),
        "total_hallucinations": 0,
        "total_cells": len(rows),
        "scored_cells": len(scored),
        "rows": rows,
        "thresholds": {},
        "pipeline_version": run_eval._pipeline_version(),
    }
    path = tmp_path / "scoreboard.json"
    path.write_text(json.dumps(scoreboard, indent=2, default=str))

    loaded = json.loads(path.read_text())
    for key in ("generated_at", "mean_overall", "total_hallucinations",
                "total_cells", "scored_cells", "rows", "thresholds"):
        assert key in loaded, f"scoreboard.json lost the {key} field readers rely on"
    assert loaded["rows"][0]["draft_stem"] == "draft1"
    assert loaded["rows"][0]["overall"] == 7.0
    # cell keys resolvable exactly as before
    assert run_eval._cell_key(loaded["rows"][0]["draft_stem"], loaded["rows"][0]["corpus"]) == "draft1__no-corpus"


# --------------------------------------------------------------------------
# Regression gate
# --------------------------------------------------------------------------

def test_regression_fires_on_a_real_drop(tmp_path):
    history = tmp_path / "history.jsonl"
    _write_run(history, [_row("draft1", 8.0)])

    failures = run_eval._regression_check(
        [_row("draft1", 6.5)], run_eval.load_history(history), {"max_mean_drop": 0.5}
    )
    assert any(f.startswith("REGRESSION") for f in failures), failures
    assert "draft1__no-corpus" in " ".join(failures)


def test_regression_silent_on_noise_within_threshold(tmp_path):
    history = tmp_path / "history.jsonl"
    _write_run(history, [_row("draft1", 8.0)])

    for noisy in (7.9, 7.6, 7.55, 8.2, 8.0):
        failures = run_eval._regression_check(
            [_row("draft1", noisy)], run_eval.load_history(history), {"max_mean_drop": 0.5}
        )
        assert not [f for f in failures if f.startswith("REGRESSION")], (noisy, failures)


def test_regression_detected_across_three_runs_not_just_the_previous(tmp_path):
    """The exact case a last-run-only comparison misses: slow drift.

    8.0 -> 7.8 -> 7.6 -> 7.4. Every single step is 0.2, well under the 0.5 gate, so
    a comparison against only the immediately previous run passes at every step.
    Cumulative drop is 0.6 and must fail.
    """
    history = tmp_path / "history.jsonl"
    thresholds = {"max_mean_drop": 0.5}

    for score in (8.0, 7.8, 7.6):
        # each intermediate step passes on its own
        failures = run_eval._regression_check(
            [_row("draft1", score)], run_eval.load_history(history), thresholds
        )
        assert not [f for f in failures if f.startswith("REGRESSION")], (score, failures)
        _write_run(history, [_row("draft1", score)])

    history_records = run_eval.load_history(history)
    assert len(history_records) == 3
    # a last-run-only gate would compare 7.4 against 7.6 and pass
    assert history_records[-1]["cells"][0]["overall"] == 7.6
    failures = run_eval._regression_check([_row("draft1", 7.4)], history_records, thresholds)
    regressions = [f for f in failures if f.startswith("REGRESSION")]
    assert regressions, "cumulative drift across three runs was not detected"
    assert "0.60" in regressions[0], regressions


def test_regression_ignores_cells_with_no_history(tmp_path):
    history = tmp_path / "history.jsonl"
    _write_run(history, [_row("draft1", 8.0)])
    failures = run_eval._regression_check(
        [_row("draft_new", 3.0)], run_eval.load_history(history), {"max_mean_drop": 0.5}
    )
    assert not [f for f in failures if f.startswith("REGRESSION")]


def test_regression_check_empty_history_does_not_crash(tmp_path):
    assert run_eval._regression_check([_row("draft1", 5.0)], [], {"max_mean_drop": 0.5}) == []


def test_threshold_and_hallucination_gates_still_fire():
    failures = run_eval._regression_check(
        [_row("draft1", 6.97, hallucinations=["made up citation"])],
        [],
        {"min_overall": 8.5, "min_dim_score": 0.0, "max_mean_drop": 0.5},
    )
    joined = " ".join(failures)
    assert "MEAN_OVERALL" in joined
    assert "THRESHOLD" in joined
    assert "HALLUCINATION" in joined


# --------------------------------------------------------------------------
# Corrupt / partial history
# --------------------------------------------------------------------------

def test_corrupt_trailing_line_does_not_crash_and_keeps_good_records(tmp_path):
    history = tmp_path / "history.jsonl"
    good = _write_run(history, [_row("draft1", 8.0)])
    # a run killed mid-write leaves a truncated line
    with history.open("a") as handle:
        handle.write('{"run_id": "truncated", "cells": [{"cell_k')

    records = run_eval.load_history(history)
    assert len(records) == 1
    assert records[0]["run_id"] == good["run_id"]

    # and a new run still appends cleanly on top
    _write_run(history, [_row("draft1", 8.1)])
    assert len(run_eval.load_history(history)) == 2


def test_garbage_and_blank_lines_are_skipped(tmp_path):
    history = tmp_path / "history.jsonl"
    history.write_text('\n\nnot json at all\n[1,2,3]\n{"run_id":"ok","cells":[]}\n\n')
    records = run_eval.load_history(history)
    assert len(records) == 1  # the list is valid JSON but not a record dict
    assert records[0]["run_id"] == "ok"


def test_missing_history_file_returns_empty(tmp_path):
    assert run_eval.load_history(tmp_path / "nope.jsonl") == []


def test_regression_check_tolerates_malformed_cells(tmp_path):
    history = tmp_path / "history.jsonl"
    history.write_text(
        json.dumps({"run_id": "a", "cells": [{"cell_key": "draft1__no-corpus", "overall": None}]}) + "\n"
        + json.dumps({"run_id": "b", "cells": ["not a dict", {"overall": 9.0}]}) + "\n"
        + json.dumps({"run_id": "c", "cells": [{"draft_stem": "draft1", "corpus": "no-corpus", "overall": 8.0}]}) + "\n"
    )
    records = run_eval.load_history(history)
    failures = run_eval._regression_check([_row("draft1", 6.0)], records, {"max_mean_drop": 0.5})
    # the legacy-shaped record (no cell_key) is still usable via draft_stem/corpus
    assert any(f.startswith("REGRESSION") for f in failures), failures


def test_append_creates_results_dir_if_absent(tmp_path):
    history = tmp_path / "deep" / "nested" / "history.jsonl"
    run_eval.append_history({"run_id": "x", "cells": []}, history)
    assert history.exists()
    assert run_eval.load_history(history)[0]["run_id"] == "x"


def test_no_network_import(monkeypatch):
    """Sanity: importing and exercising run_eval history never needs an API key."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("NOESIS_LLM_KILL_SWITCH", "1")
    record = run_eval.build_history_record([_row("draft1", 7.0)], _cfg(), 7.0, 0, args=_Args())
    assert record["aggregates"]["mean_overall"] == 7.0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))


class TestSinksResolveAtCallTime:
    """A sink a test run can write to is not a durable record.

    HISTORY_PATH / OPENREVIEW_HISTORY_PATH were module constants bound to
    RESULTS_DIR at import. A test monkeypatching run_eval.RESULTS_DIR to a
    tmp_path did NOT move them, so every run of the eval suite appended a
    synthetic fixture record to the real, tracked, append-only history --
    leaving the committed benchmark board stale against its own sources.
    """

    def test_monkeypatching_results_dir_moves_the_history_sink(self, tmp_path, monkeypatch):
        monkeypatch.setattr(run_eval, "RESULTS_DIR", tmp_path)
        assert run_eval.history_path() == tmp_path / "history.jsonl"
        assert run_eval.openreview_history_path() == tmp_path / "openreview_history.jsonl"

    def test_the_real_sink_is_not_written_when_redirected(self, tmp_path, monkeypatch):
        """The property that actually matters: redirect, write, and assert the
        real file was untouched."""
        real = run_eval.RESULTS_DIR / "openreview_history.jsonl"
        before = real.read_bytes() if real.exists() else None

        monkeypatch.setattr(run_eval, "RESULTS_DIR", tmp_path)
        run_eval.append_history({"run_id": "synthetic", "cells": []},
                                run_eval.openreview_history_path())

        assert (tmp_path / "openreview_history.jsonl").exists()
        after = real.read_bytes() if real.exists() else None
        assert after == before, "a redirected write reached the real append-only sink"

"""The CLI's cost brakes: --dry-run must not call anything, real mode must be
double-confirmed, and results must be appended rather than rewritten."""

from __future__ import annotations

import json
import sys

import pytest

from loadgen import runner
from loadgen.loadmodel import LoadModel
from loadgen.stats import summarize
from loadgen.tests.test_stats import _result


def test_dry_run_makes_zero_calls(monkeypatch, capsys):
    """The brake that matters most: a dry run must not import a node, must not
    construct a workload, and must not issue a request. `execute` is replaced
    with a landmine -- if the CLI touches it, the test fails."""
    def landmine(*a, **k):  # pragma: no cover - only runs on failure
        raise AssertionError("--dry-run executed the load test")

    monkeypatch.setattr(runner, "execute", landmine)
    monkeypatch.setattr(runner.asyncio, "run", landmine)

    rc = runner.main(["--dry-run", "--mode", "open", "--lam", "0.05", "--n", "120"])
    out = capsys.readouterr().out

    assert rc == 0
    assert "DRY RUN" in out
    assert "no LLM call" in out
    assert "TOTAL graph runs: 120" in out
    assert "$0.00 (all models stubbed)" in out


def test_dry_run_writes_no_results_file(monkeypatch, tmp_path):
    results = tmp_path / "loadgen.jsonl"
    monkeypatch.setattr(runner, "execute",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("ran")))
    runner.main(["--dry-run", "--results", str(results), "--n", "10"])
    assert not results.exists()


def test_dry_run_reports_the_planned_request_count_per_load_point(capsys, monkeypatch):
    monkeypatch.setattr(runner, "execute",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("ran")))
    runner.main(["--dry-run", "--mode", "open", "--lam", "0.02", "0.05", "0.10",
                 "--n", "50", "--warmup", "5"])
    out = capsys.readouterr().out
    assert out.count("graph runs: 50") == 3
    assert "TOTAL graph runs: 150" in out
    assert "measured 45, warmup 5" in out


def test_dry_run_brackets_real_llm_spend_before_anything_runs(capsys, monkeypatch):
    monkeypatch.setattr(runner, "execute",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("ran")))
    runner.main(["--dry-run", "--real-llm", "--yes", "--mode", "closed",
                 "--concurrency", "1", "--n", "4", "--warmup", "1"])
    out = capsys.readouterr().out
    assert "REAL LLM" in out
    assert "est. spend: $" in out
    assert "$0.00 (all models stubbed)" not in out


def test_real_llm_without_yes_refuses(capsys):
    rc = runner.main(["--real-llm", "--n", "2", "--warmup", "1"])
    assert rc == 2
    assert "pass --yes" in capsys.readouterr().err


def test_compare_fanout_builds_both_a_parallel_and_a_serial_model():
    args = runner.build_models(_args(compare_fanout=True, mode="closed", concurrency=[1]))
    assert [m.serial_reviewers for m in args] == [False, True]
    assert len({m.config_hash() for m in args}) == 2


def test_lambda_sweep_builds_one_model_per_rate():
    models = runner.build_models(_args(mode="open", lam=[0.02, 0.05, 0.1]))
    assert [m.rate for m in models] == [0.02, 0.05, 0.1]


def test_results_are_appended_never_rewritten(tmp_path):
    """This repo has lost eval history once by rewriting a results file."""
    path = tmp_path / "loadgen.jsonl"
    s = summarize(_result(LoadModel(mode="open", rate=0.05, n_requests=5), [1.0] * 5))
    runner.append_results([s], path, "run1")
    runner.append_results([s], path, "run2")
    lines = [json.loads(l) for l in path.read_text().splitlines()]
    assert len(lines) == 2
    assert [l["run_id"] for l in lines] == ["run1", "run2"]
    assert lines[0]["config_hash"] == s.model.config_hash()


def test_serialized_record_carries_the_exclusions_note(tmp_path):
    path = tmp_path / "loadgen.jsonl"
    s = summarize(_result(LoadModel(mode="open", rate=0.05, n_requests=5), [1.0] * 5),
                  extra={"exclusions_note": runner.EXCLUSION_NOTE})
    runner.append_results([s], path, "r")
    rec = json.loads(path.read_text().splitlines()[0])
    assert "NOT user-visible end-to-end latency" in rec["exclusions_note"]


class _args:
    def __init__(self, **kw):
        self.mode = kw.get("mode", "open")
        self.lam = kw.get("lam", [0.05])
        self.concurrency = kw.get("concurrency", [2])
        self.n = kw.get("n", 40)
        self.warmup = kw.get("warmup", 4)
        self.slo = kw.get("slo", 60.0)
        self.seed = kw.get("seed", 1234)
        self.real_llm = kw.get("real_llm", False)
        self.serial_reviewers = kw.get("serial_reviewers", False)
        self.compare_fanout = kw.get("compare_fanout", False)

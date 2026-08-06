"""Tests for the eval integrity gate.

Every test builds a throwaway git repo on disk. Nothing here touches the network,
a database, or an API key -- and one test asserts that by breaking sockets.
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ci_gate  # noqa: E402


# ---------------------------------------------------------------------------
# Fixture repo
# ---------------------------------------------------------------------------


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _write(repo: Path, rel: str, text: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _board(sources: list[dict], **extra) -> str:
    payload = {"schema_version": 2, "sources": sources}
    payload.update(extra)
    return json.dumps(payload, indent=1, sort_keys=True)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    _git(r, "config", "user.email", "t@example.com")
    _git(r, "config", "user.name", "Test")

    _write(r, "scripts/eval/results/node_eval.jsonl",
           '{"run_id": "a", "wall_seconds": 1}\n{"run_id": "b", "wall_seconds": 2}\n')
    _write(r, "scripts/eval/results/history.jsonl", '{"run_id": "h1"}\n')
    _write(r, "docs/benchmarks.json", _board([
        {"path": "results/node_eval.jsonl", "lines": 2, "present": True},
        {"path": "results/history.jsonl", "lines": 1, "present": True},
        {"path": "results/retrieval_eval.jsonl", "lines": 9, "present": True},
    ]))
    _write(r, "docs/BENCHMARKS.md", "# Benchmarks\n")
    # Stand-in for the real generator: the gate only cares about its exit code.
    _write(r, "scripts/eval/benchmarks.py",
           "import sys\nsys.exit(0 if '--check' in sys.argv else 0)\n")
    _write(r, "scripts/eval/config.yaml",
           "drafts:\n  - a.pdf\n\nthresholds:\n  min_overall: 8.5\n  min_dim_score: 7.5\n")
    _write(r, "docs/EVAL_GUIDE.md", "# CI\n\n## Threshold change log\n\n(none yet)\n")
    _write(r, "scripts/eval/BASELINE.md",
           "# Baseline\n\nDense retrieval reached recall@10 = 0.4221 over 59 queries.\n")
    _git(r, "add", "-A")
    _git(r, "commit", "-qm", "base")
    return r


def _run(repo: Path, base: str = "HEAD"):
    return {r.name: r for r in ci_gate.run_checks(repo, base)}


# ---------------------------------------------------------------------------
# Board staleness
# ---------------------------------------------------------------------------


def test_fresh_board_passes(repo: Path):
    res = _run(repo)["board-tracked-sources"]
    assert res.status == ci_gate.PASS, res.detail


def test_stale_board_detected(repo: Path):
    # A record was appended to a tracked sink without regenerating the board.
    with (repo / "scripts/eval/results/node_eval.jsonl").open("a") as fh:
        fh.write('{"run_id": "c", "wall_seconds": 3}\n')
    res = _run(repo)["board-tracked-sources"]
    assert res.status == ci_gate.FAIL
    assert "node_eval.jsonl" in " ".join(res.items)
    assert "board records 2 lines, file has 3" in " ".join(res.items)
    assert "make benchmarks" in res.remedy


def test_missing_board_is_a_failure(repo: Path):
    (repo / "docs/benchmarks.json").unlink()
    assert _run(repo)["board-tracked-sources"].status == ci_gate.FAIL


def test_board_regeneration_skips_when_sinks_are_absent(repo: Path):
    # retrieval_eval.jsonl is declared present in the board but gitignored, so a
    # clean checkout cannot regenerate the board. That is a SKIP, never a FAIL.
    res = _run(repo)["board-regenerates"]
    assert res.status == ci_gate.SKIP
    assert "retrieval_eval.jsonl" in res.detail
    assert "make benchmarks-check" in res.remedy


def test_board_regeneration_runs_and_passes_when_every_sink_is_present(repo: Path):
    _write(repo, "scripts/eval/results/retrieval_eval.jsonl", "{}\n")
    res = _run(repo)["board-regenerates"]
    assert res.status == ci_gate.PASS


def test_board_regeneration_fails_when_the_generator_reports_stale(repo: Path):
    _write(repo, "scripts/eval/results/retrieval_eval.jsonl", "{}\n")
    _write(repo, "scripts/eval/benchmarks.py",
           "import sys\nsys.stderr.write('[benchmarks] stale: BENCHMARKS.md\\n')\nsys.exit(1)\n")
    res = _run(repo)["board-regenerates"]
    assert res.status == ci_gate.FAIL
    assert "stale" in res.detail
    assert "make benchmarks" in res.remedy


# ---------------------------------------------------------------------------
# Append-only
# ---------------------------------------------------------------------------


def test_appended_file_passes(repo: Path):
    base = repo.name and ci_gate.git(repo, "rev-parse", "HEAD").strip()
    with (repo / "scripts/eval/results/history.jsonl").open("a") as fh:
        fh.write('{"run_id": "h2"}\n')
    res = _run(repo, base)["append-only"]
    assert res.status == ci_gate.PASS, res.items


def test_truncated_file_detected(repo: Path):
    base = ci_gate.git(repo, "rev-parse", "HEAD").strip()
    _write(repo, "scripts/eval/results/node_eval.jsonl", '{"run_id": "a", "wall_seconds": 1}\n')
    res = _run(repo, base)["append-only"]
    assert res.status == ci_gate.FAIL
    assert "shrank from 2 to 1 lines" in " ".join(res.items)


def test_rewritten_line_detected(repo: Path):
    base = ci_gate.git(repo, "rev-parse", "HEAD").strip()
    _write(repo, "scripts/eval/results/node_eval.jsonl",
           '{"run_id": "a", "wall_seconds": 999}\n'
           '{"run_id": "b", "wall_seconds": 2}\n'
           '{"run_id": "c", "wall_seconds": 3}\n')
    res = _run(repo, base)["append-only"]
    assert res.status == ci_gate.FAIL
    joined = " ".join(res.items)
    assert "line 1 was rewritten" in joined
    assert "git show" in res.remedy  # tells you exactly how to recover


def test_deleted_append_only_file_detected(repo: Path):
    base = ci_gate.git(repo, "rev-parse", "HEAD").strip()
    (repo / "scripts/eval/results/history.jsonl").unlink()
    _git(repo, "rm", "-q", "--cached", "scripts/eval/results/history.jsonl")
    res = _run(repo, base)["append-only"]
    assert res.status == ci_gate.FAIL
    assert "DELETED" in " ".join(res.items)


def test_unresolvable_base_ref_skips_rather_than_fails(repo: Path):
    res = _run(repo, "origin/does-not-exist")["append-only"]
    assert res.status == ci_gate.SKIP
    assert "fetch-depth" in res.detail


# ---------------------------------------------------------------------------
# Invalid runs quoted
# ---------------------------------------------------------------------------


def _add_invalid_run(repo: Path) -> None:
    _write(repo, "scripts/eval/results/retrieval_eval.jsonl",
           json.dumps({"run_id": "deadbeef01", "valid": False,
                       "invalidated_by": ["keyword leg returned 0 rows"]}) + "\n")


def test_document_quoting_invalid_run_detected(repo: Path):
    _add_invalid_run(repo)
    _write(repo, "scripts/eval/BASELINE.md",
           "# Baseline\n\nHybrid reached recall@10 = 0.9100 in run deadbeef01 "
           "over 59 queries.\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "quote")
    res = _run(repo)["invalid-run-quoted"]
    assert res.status == ci_gate.FAIL
    assert "deadbeef01" in " ".join(res.items)


def test_invalid_run_quoted_with_marker_passes(repo: Path):
    _add_invalid_run(repo)
    _write(repo, "scripts/eval/BASELINE.md",
           "# Baseline\n\nRUN INVALID -- DO NOT QUOTE:\n"
           "run deadbeef01 reported recall@10 = 0.9100 over 59 queries.\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "marked")
    assert _run(repo)["invalid-run-quoted"].status == ci_gate.PASS


def test_invalid_runs_are_read_from_the_tracked_board_too(repo: Path):
    """CI cannot see the gitignored sinks, so the board carries the registry."""
    _write(repo, "docs/benchmarks.json", _board(
        [{"path": "results/node_eval.jsonl", "lines": 2, "present": True}],
        retrieval={"invalidated": [{"run_id": "cafe1234"}]},
    ))
    _write(repo, "scripts/eval/BASELINE.md", "recall@10 = 0.7 from run cafe1234\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "board registry")
    res = _run(repo)["invalid-run-quoted"]
    assert res.status == ci_gate.FAIL
    assert "benchmarks.json" in " ".join(res.items)


def test_gold_documents_are_not_scanned(repo: Path):
    _add_invalid_run(repo)
    _write(repo, "scripts/eval/gold/draft1.gold.md",
           "recall@10 = 0.9100 in run deadbeef01\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "gold")
    assert _run(repo)["invalid-run-quoted"].status == ci_gate.PASS


# ---------------------------------------------------------------------------
# metric-without-n
# ---------------------------------------------------------------------------


def test_metric_with_n_passes(repo: Path):
    assert _run(repo)["metric-without-n"].status == ci_gate.PASS


def test_metric_without_n_warns_and_does_not_block(repo: Path):
    _write(repo, "scripts/eval/BASELINE.md", "# Baseline\n\nrecall@10 = 0.4221.\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "no n")
    results = ci_gate.run_checks(repo, "HEAD")
    by_name = {r.name: r for r in results}
    assert by_name["metric-without-n"].status == ci_gate.WARN
    assert ci_gate.exit_code(results, strict=False) == ci_gate.EXIT_OK
    assert ci_gate.exit_code(results, strict=True) == ci_gate.EXIT_WARN_STRICT


def test_table_with_an_n_column_is_not_warned_about(repo: Path):
    _write(repo, "scripts/eval/BASELINE.md",
           "# Baseline\n\n"
           "| metric | value | n |\n|---|---|---|\n| recall@10 | 0.4221 | 59 |\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "table")
    assert _run(repo)["metric-without-n"].status == ci_gate.PASS


# ---------------------------------------------------------------------------
# Threshold notes
# ---------------------------------------------------------------------------


def test_threshold_change_without_note_warns(repo: Path):
    base = ci_gate.git(repo, "rev-parse", "HEAD").strip()
    _write(repo, "scripts/eval/config.yaml",
           "drafts:\n  - a.pdf\n\nthresholds:\n  min_overall: 6.0\n  min_dim_score: 7.5\n")
    results = ci_gate.run_checks(repo, base)
    res = {r.name: r for r in results}["threshold-note"]
    assert res.status == ci_gate.WARN
    assert "min_overall: 8.5 -> 6.0" in " ".join(res.items)
    assert ci_gate.exit_code(results, strict=False) == ci_gate.EXIT_OK


def test_threshold_change_with_note_passes(repo: Path):
    base = ci_gate.git(repo, "rev-parse", "HEAD").strip()
    _write(repo, "scripts/eval/config.yaml",
           "drafts:\n  - a.pdf\n\nthresholds:\n  min_overall: 6.0\n  min_dim_score: 7.5\n")
    _write(repo, "docs/EVAL_GUIDE.md",
           "# CI\n\n## Threshold change log\n\n- min_overall 8.5 -> 6.0: matches "
           "measured reality; the old value was aspirational.\n")
    res = _run(repo, base)["threshold-note"]
    assert res.status == ci_gate.PASS


def test_unchanged_thresholds_pass(repo: Path):
    base = ci_gate.git(repo, "rev-parse", "HEAD").strip()
    assert _run(repo, base)["threshold-note"].status == ci_gate.PASS


def test_threshold_parser_ignores_comments_and_other_blocks():
    text = (
        "drafts:\n  - a.pdf\n"
        "thresholds:\n"
        "  min_overall: 8.5       # mean overall\n"
        "  max_mean_drop: 0.5\n"
        "other:\n  min_overall: 1.0\n"
    )
    assert ci_gate._parse_thresholds(text) == {"min_overall": "8.5", "max_mean_drop": "0.5"}


# ---------------------------------------------------------------------------
# metric-regression
# ---------------------------------------------------------------------------

#: A cut-down `regression:` block. Real tolerances live in scripts/eval/config.yaml
#: and are justified there from the observed spread; these only have to exercise
#: both directions and both tolerance kinds.
_REGRESSION_BLOCK = (
    "\nregression:\n"
    "  total_hallucinations:  0     up_is_bad\n"
    "  scored_cells:          0     down_is_bad\n"
    "  ndcg@10:               0.005 down_is_bad\n"
    "  total_estimated_usd:   25%   up_is_bad\n"
)

_OR_CONFIG = {"limit": 1, "paper_ids": "b,c", "venue": "ICLR.cc/2024/Conference"}


def _openreview(run_id: str, hallucinations=(0, 0), config: dict | None = None) -> str:
    return json.dumps({
        "run_id": run_id,
        "config": config if config is not None else _OR_CONFIG,
        "aggregates": {"papers": len(hallucinations)},
        "cells": [
            {"cell_key": str(i), "hallucinations": h}
            for i, h in enumerate(hallucinations)
        ],
    }) + "\n"


def _node_summary(run_id: str, usd: float, failed: int = 0) -> str:
    return json.dumps({
        "record_type": "run_summary",
        "run_id": run_id,
        "config": {"nodes": ["editor_pass_node"], "papers": ["p1"],
                   "reviewer_type": None, "repeat": 1, "with_metric": False,
                   "state_dir": "/machine/specific/path"},
        "failed_replays": failed,
        "total_estimated_usd": usd,
    }) + "\n"


def _embedding(ndcg: float, config_hash: str = "f20b55d4") -> str:
    return json.dumps({
        "n": 338,
        "arms": [{
            "arm": "control_1536_vector",
            "config_hash": config_hash,
            "metrics": {"map": 0.232, "mrr": 0.7335, "ndcg@10": ndcg,
                        "recall@10": 0.2199},
        }],
    }) + "\n"


@pytest.fixture()
def sinks(repo: Path) -> Path:
    """The `repo` fixture plus every sink C7 knows about, with one baseline each.

    All six are present so no test picks up an incidental "sink absent" note --
    absence is its own test.
    """
    _write(repo, "scripts/eval/config.yaml",
           "drafts:\n  - a.pdf\n\nthresholds:\n  min_overall: 8.5\n"
           "  min_dim_score: 7.5\n" + _REGRESSION_BLOCK)
    _write(repo, "scripts/eval/results/openreview_history.jsonl", _openreview("r1"))
    _write(repo, "scripts/eval/results/node_eval.jsonl", _node_summary("n1", 0.10))
    _write(repo, "scripts/eval/results/embedding_arms.jsonl", _embedding(0.5196))
    _write(repo, "scripts/eval/results/panel_arms.jsonl",
           json.dumps({"config_hash": "155353393c1d", "n_errors": 0,
                       "score": {"recall_addressable": 0.2895},
                       "unverified_quotes": {"rate": 0.0},
                       "usd_per_verified_finding": 0.0198}) + "\n")
    _write(repo, "scripts/eval/gate_calibration/sweep_results.jsonl",
           json.dumps({"schema_version": 1, "seed": 0,
                       "dataset": {"n_scoreable": 76, "base_rate": 0.039},
                       "gate_as_shipped": {"precision": 0.16, "recall": 0.66, "f1": 0.26},
                       "joint": {"best_f1": {"f1": 0.8}}}) + "\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "regression baseline")
    return repo


def _head(repo: Path) -> str:
    return ci_gate.git(repo, "rev-parse", "HEAD").strip()


def _regression(repo: Path, base: str):
    return _run(repo, base)["metric-regression"]


def test_unchanged_sinks_are_not_a_failure(sinks: Path):
    res = _regression(sinks, _head(sinks))
    assert res.status == ci_gate.PASS, res.items
    assert "no tracked eval sink changed" in res.detail


def test_quality_regression_beyond_tolerance_fails(sinks: Path):
    base = _head(sinks)
    with (sinks / "scripts/eval/results/openreview_history.jsonl").open("a") as fh:
        fh.write(_openreview("r2", hallucinations=(0, 3)))
    res = _regression(sinks, base)
    assert res.status == ci_gate.FAIL, res.detail
    joined = " ".join(res.items)
    assert "openreview_history.jsonl: total_hallucinations  0 -> 3" in joined
    assert "tolerance 0 up_is_bad" in joined


def test_quality_regression_within_tolerance_passes(sinks: Path):
    base = _head(sinks)
    # 0.5196 -> 0.5160 is a drop of 0.0036, inside the 0.005 tolerance.
    with (sinks / "scripts/eval/results/embedding_arms.jsonl").open("a") as fh:
        fh.write(_embedding(0.5160))
    res = _regression(sinks, base)
    assert res.status == ci_gate.PASS, res.items
    assert "within tolerance" in res.detail


def test_cost_rising_beyond_tolerance_fails(sinks: Path):
    """Direction is declared, not inferred: cost going *up* is the regression."""
    base = _head(sinks)
    with (sinks / "scripts/eval/results/node_eval.jsonl").open("a") as fh:
        fh.write(_node_summary("n2", 0.20))  # +100% against a 25% tolerance
    res = _regression(sinks, base)
    assert res.status == ci_gate.FAIL, res.detail
    joined = " ".join(res.items)
    assert "node_eval.jsonl: total_estimated_usd  0.1 -> 0.2" in joined
    assert "tolerance 25% up_is_bad" in joined


def test_cost_falling_is_never_a_regression(sinks: Path):
    base = _head(sinks)
    with (sinks / "scripts/eval/results/node_eval.jsonl").open("a") as fh:
        fh.write(_node_summary("n2", 0.001))
    assert _regression(sinks, base).status == ci_gate.PASS


def test_improvement_passes_regardless_of_magnitude(sinks: Path):
    base = _head(sinks)
    with (sinks / "scripts/eval/results/embedding_arms.jsonl").open("a") as fh:
        fh.write(_embedding(0.9000))  # +0.38, far outside tolerance, but the good way
    res = _regression(sinks, base)
    assert res.status == ci_gate.PASS, res.items


def test_new_config_identity_skips_rather_than_passes(sinks: Path):
    base = _head(sinks)
    other = dict(_OR_CONFIG, venue="NeurIPS.cc/2025/Conference")
    with (sinks / "scripts/eval/results/openreview_history.jsonl").open("a") as fh:
        fh.write(_openreview("r2", hallucinations=(9, 9), config=other))
    res = _regression(sinks, base)
    assert res.status == ci_gate.SKIP, res.detail
    joined = " ".join(res.items)
    assert "NEW config identity" in joined
    assert "not passed" in joined


def test_absent_sink_skips_rather_than_passes(sinks: Path):
    base = _head(sinks)
    (sinks / "scripts/eval/results/panel_arms.jsonl").unlink()
    _git(sinks, "rm", "-q", "--cached", "scripts/eval/results/panel_arms.jsonl")
    res = _regression(sinks, base)
    assert res.status == ci_gate.SKIP, res.detail
    assert "panel_arms.jsonl: absent from this checkout" in " ".join(res.items)
    assert "not passed" in " ".join(res.items)


def test_malformed_record_never_crashes_and_never_silently_passes(sinks: Path):
    base = _head(sinks)
    with (sinks / "scripts/eval/results/openreview_history.jsonl").open("a") as fh:
        fh.write('{"run_id": "r2", "cells": [{"halluc\n')  # killed mid-write
    res = _regression(sinks, base)
    assert res.status == ci_gate.SKIP, res.detail
    assert "unparseable JSON" in " ".join(res.items)


def test_a_regression_in_one_sink_outranks_a_skip_in_another(sinks: Path):
    base = _head(sinks)
    (sinks / "scripts/eval/results/panel_arms.jsonl").unlink()
    _git(sinks, "rm", "-q", "--cached", "scripts/eval/results/panel_arms.jsonl")
    with (sinks / "scripts/eval/results/openreview_history.jsonl").open("a") as fh:
        fh.write(_openreview("r2", hallucinations=(0, 3)))
    res = _regression(sinks, base)
    assert res.status == ci_gate.FAIL
    assert ci_gate.exit_code(ci_gate.run_checks(sinks, base), strict=False) == ci_gate.EXIT_FAIL


def test_regression_check_skips_when_no_tolerances_are_declared(repo: Path):
    """The stock fixture has no `regression:` block at all."""
    res = _regression(repo, _head(repo))
    assert res.status == ci_gate.SKIP
    assert "no `regression:` block" in res.detail


def test_regression_config_parser_reads_both_tolerance_kinds():
    parsed = ci_gate._parse_regression_config(
        "thresholds:\n  min_overall: 8.5\n"
        "regression:\n"
        "  ndcg@10:              0.005 down_is_bad   # spread 0.0000\n"
        "  total_estimated_usd:  25%   up_is_bad\n"
        "other:\n  ndcg@10: 9 down_is_bad\n"
    )
    assert set(parsed) == {"ndcg@10", "total_estimated_usd"}
    assert parsed["ndcg@10"] == ci_gate.Tolerance(0.005, False, ci_gate.DOWN_IS_BAD)
    assert parsed["total_estimated_usd"].relative
    assert parsed["total_estimated_usd"].allowance(0.10) == pytest.approx(0.025)


def test_moving_a_regression_tolerance_needs_a_note_too(sinks: Path):
    """C6 watches the tolerances as well: a widened tolerance is a lowered bar."""
    base = _head(sinks)
    _write(sinks, "scripts/eval/config.yaml",
           (sinks / "scripts/eval/config.yaml").read_text(encoding="utf-8")
           .replace("ndcg@10:               0.005", "ndcg@10:               0.500"))
    results = ci_gate.run_checks(sinks, base)
    res = {r.name: r for r in results}["threshold-note"]
    assert res.status == ci_gate.WARN
    assert "regression.ndcg@10: 0.005 -> 0.5" in " ".join(res.items)
    # C6 stays a warning; widening a tolerance is not itself a blocking event.
    assert res.status != ci_gate.FAIL


# ---------------------------------------------------------------------------
# Exit codes / CLI
# ---------------------------------------------------------------------------


def test_exit_codes_are_distinct(repo: Path, capsys):
    ok = [ci_gate.CheckResult("a", ci_gate.PASS)]
    warn = [ci_gate.CheckResult("a", ci_gate.WARN)]
    fail = [ci_gate.CheckResult("a", ci_gate.FAIL)]
    assert ci_gate.exit_code(ok, False) == 0
    assert ci_gate.exit_code(fail, False) == 1
    assert ci_gate.exit_code(warn, True) == 2
    assert ci_gate.exit_code(warn, False) == 0
    # fail beats warn
    assert ci_gate.exit_code(warn + fail, True) == 1
    assert len({0, 1, 2, ci_gate.EXIT_CANNOT_RUN}) == 4


def test_cli_returns_3_when_not_a_repo(tmp_path: Path, capsys):
    assert ci_gate.main(["--repo", str(tmp_path)]) == ci_gate.EXIT_CANNOT_RUN
    assert "not a git repository" in capsys.readouterr().err


def test_cli_passes_on_a_clean_repo(repo: Path, capsys):
    assert ci_gate.main(["--repo", str(repo)]) == ci_gate.EXIT_OK
    assert "[ci-gate] PASSED." in capsys.readouterr().out


def test_cli_failure_output_names_the_reproduction_command(repo: Path, capsys):
    with (repo / "scripts/eval/results/node_eval.jsonl").open("a") as fh:
        fh.write('{"run_id": "c"}\n')
    assert ci_gate.main(["--repo", str(repo)]) == ci_gate.EXIT_FAIL
    out = capsys.readouterr().out
    assert "python3 scripts/eval/ci_gate.py" in out
    assert "Reproduce locally" in out


def test_cli_json_report(repo: Path, capsys):
    ci_gate.main(["--repo", str(repo), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["exit_code"] == 0
    names = {c["check"] for c in payload["checks"]}
    assert names == {
        "board-tracked-sources", "board-regenerates", "append-only",
        "invalid-run-quoted", "metric-regression", "metric-without-n",
        "threshold-note",
    }


# ---------------------------------------------------------------------------
# No database, no API key, no network
# ---------------------------------------------------------------------------


def test_gate_runs_with_no_credentials_and_makes_zero_network_calls(
    repo: Path, monkeypatch, capsys
):
    for var in ("OPENAI_API_KEY", "SUPABASE_URL", "SUPABASE_ANON_KEY",
                "DATABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "NOESIS_LLM_MAX_SPEND_USD"):
        monkeypatch.delenv(var, raising=False)

    class NoNetwork(AssertionError):
        pass

    def _boom(*args, **kwargs):
        raise NoNetwork("the gate attempted a network call")

    monkeypatch.setattr(socket, "socket", _boom)
    monkeypatch.setattr(socket, "create_connection", _boom)
    monkeypatch.setattr(socket, "getaddrinfo", _boom)

    # Honest caveat: this patch cannot reach inside the one subprocess the gate
    # spawns (benchmarks.py). test_benchmarks_generator_is_offline covers that.
    assert ci_gate.main(["--repo", str(repo)]) == ci_gate.EXIT_OK
    assert "PASSED" in capsys.readouterr().out


def test_benchmarks_generator_is_offline():
    """The only subprocess the gate spawns must not reach the network either."""
    generator = Path(ci_gate.__file__).with_name("benchmarks.py")
    if not generator.exists():
        pytest.skip("benchmarks.py is not present in this checkout")
    source = generator.read_text(encoding="utf-8")
    for forbidden in ("import openai", "import requests", "import httpx",
                      "urllib.request", "import socket", "psycopg"):
        assert forbidden not in source, f"benchmarks.py must not depend on {forbidden}"


def test_gate_imports_nothing_that_talks_to_a_service():
    source = Path(ci_gate.__file__).read_text(encoding="utf-8")
    for forbidden in ("import openai", "import requests", "import httpx",
                      "supabase", "psycopg", "urllib.request"):
        assert forbidden not in source, f"ci_gate.py must not depend on {forbidden}"

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
        "invalid-run-quoted", "metric-without-n", "threshold-note",
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

#!/usr/bin/env python3
"""Integrity gate for the Noesis eval artefacts.

This gate is deliberately narrow. Almost every real measurement in this project
costs OpenAI money and needs a Postgres/pgvector database; a GitHub PR runner
has neither. So this file checks only things that are *free, deterministic and
offline*, and it refuses to pretend anything else can gate a merge.

WHAT IT GATES (blocking, runs on any checkout):
  board-tracked-sources  the tracked benchmark board (benchmarks.json) still
                         agrees with the eval sinks that are tracked in git.
  append-only            an append-only results file was appended to, not
                         shrunk and not rewritten in place. This project already
                         destroyed its eval history once by overwriting
                         scoreboard.json.
  invalid-run-quoted     no tracked markdown quotes a metric from a run that was
                         recorded `valid: false`.

WHAT IT GATES ONLY WHERE THE SINKS EXIST (skips on a clean CI checkout):
  board-regenerates      full `benchmarks.py --check`. Four of the eight sinks
                         it reads are gitignored, so on a fresh clone the board
                         cannot be regenerated and this check SKIPS rather than
                         failing on absent data. Run it locally with
                         `make benchmarks-check`.

WHAT IT WARNS ABOUT (never blocks unless --strict):
  metric-without-n       a headline metric stated in a tracked doc with no
                         sample size anywhere near it. Heuristic: a markdown
                         table can carry `n` in a column this check cannot see.
  threshold-note         scripts/eval/config.yaml thresholds moved without a
                         line in the threshold change log in scripts/eval/CI.md.

WHAT IT CANNOT GATE, EVER, ON A PR (see CI.md):
  running the eval, retrieval metrics, node replay, judge agreement. Money and a
  database. Those live in .github/workflows/eval-nightly.yml.

Exit codes:
  0  all checks passed (warnings may have been printed)
  1  at least one blocking check FAILED
  2  warnings present and --strict was given
  3  the gate itself could not run (bad repo, git unavailable, bad arguments)

Usage:
  python3 scripts/eval/ci_gate.py                    # gate the working tree vs HEAD
  python3 scripts/eval/ci_gate.py --base origin/master
  python3 scripts/eval/ci_gate.py --json             # machine-readable report

This module makes no network calls and reads no credentials.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

EVAL_DIR = Path(__file__).resolve().parent
REPO_ROOT = EVAL_DIR.parent.parent

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_WARN_STRICT = 2
EXIT_CANNOT_RUN = 3

BOARD_JSON = "scripts/eval/benchmarks.json"
BOARD_MD = "scripts/eval/BENCHMARKS.md"
CONFIG_YAML = "scripts/eval/config.yaml"
CI_DOC = "scripts/eval/CI.md"

#: Files that are only ever appended to. Two of these are the *only* durable
#: record this repo has of its own eval scores (see the .gitignore negations
#: around scripts/eval/results/). Rewriting a line here silently rewrites
#: history, which is why it is a blocking check and not a warning.
APPEND_ONLY = (
    "scripts/eval/results/history.jsonl",
    "scripts/eval/results/openreview_history.jsonl",
    "scripts/eval/results/node_eval.jsonl",
)

#: Tracked docs that state measurements. gold/*.md are reference critiques, not
#: measurement reports, so they are excluded.
def _is_measurement_doc(rel: str) -> bool:
    return (
        rel.startswith("scripts/eval/")
        and rel.endswith(".md")
        and "/gold/" not in rel
        and not rel.endswith("/CI.md")
    )


METRIC_RE = re.compile(
    r"\b(recall@\d+|ndcg@\d+|mrr|precision@\d+|hit@\d+|mean[ _]overall)\b", re.I
)
NUMBER_RE = re.compile(r"\b\d+\.\d+\b")
N_CUE_RE = re.compile(
    r"\b(n\s*=\s*\d+"
    r"|\d+\s+(queries|records|runs|papers|drafts|documents|cells|spans|calls|reviews|nodes)"
    r"|over\s+\d+"
    r"|sample\s+size)\b",
    re.I,
)
N_COLUMN_RE = re.compile(r"\|\s*n(\s*=|\s*\)|_|\s|queries|runs)?\s*\|", re.I)
INVALID_MARKER_RE = re.compile(
    r"(invalid|invalidated|do not quote|not quotable|discard)", re.I
)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

PASS, FAIL, WARN, SKIP = "PASS", "FAIL", "WARN", "SKIP"


@dataclass
class CheckResult:
    name: str
    status: str
    detail: str = ""
    remedy: str = ""
    items: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "check": self.name,
            "status": self.status,
            "detail": self.detail,
            "remedy": self.remedy,
            "items": self.items,
        }


# ---------------------------------------------------------------------------
# git helpers (offline; subprocess only)
# ---------------------------------------------------------------------------


class GitError(RuntimeError):
    pass


def git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise GitError(f"git {' '.join(args)}: {proc.stderr.strip()}")
    return proc.stdout


def git_ok(repo: Path, *args: str) -> bool:
    try:
        git(repo, *args)
        return True
    except GitError:
        return False


def tracked_files(repo: Path) -> list[str]:
    return [p for p in git(repo, "ls-files").splitlines() if p]


def blob_at(repo: Path, ref: str, rel: str) -> str | None:
    """File content at ``ref``, or None if it did not exist there."""
    try:
        return git(repo, "show", f"{ref}:{rel}")
    except GitError:
        return None


def current_content(repo: Path, rel: str) -> str | None:
    """Working-tree content.

    Falls back to the HEAD blob only when the path is still in the index -- a
    file that is gone from disk *and* gone from the index has been deleted, and
    must not be resurrected from HEAD or the append-only check would miss it.
    """
    path = repo / rel
    if path.exists():
        return path.read_text(encoding="utf-8", errors="replace")
    try:
        staged = git(repo, "ls-files", "--", rel).strip()
    except GitError:
        staged = ""
    if not staged:
        return None
    return blob_at(repo, "HEAD", rel)


# ---------------------------------------------------------------------------
# C1 -- the tracked board still agrees with the tracked sinks
# ---------------------------------------------------------------------------


def check_board_tracked_sources(repo: Path) -> CheckResult:
    name = "board-tracked-sources"
    remedy = "run `make benchmarks` and commit BENCHMARKS.md + benchmarks.json"
    board_path = repo / BOARD_JSON
    if not board_path.exists():
        return CheckResult(
            name,
            FAIL,
            f"{BOARD_JSON} is missing. It is a tracked, generated artefact.",
            remedy,
        )
    try:
        board = json.loads(board_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return CheckResult(name, FAIL, f"{BOARD_JSON} is not valid JSON: {exc}", remedy)

    tracked = set(tracked_files(repo))
    problems: list[str] = []
    checked = 0
    for src in board.get("sources") or []:
        rel_to_eval = src.get("path")
        if not rel_to_eval:
            continue
        rel = f"scripts/eval/{rel_to_eval}"
        if rel not in tracked:
            continue  # gitignored sink -- not visible to CI, see C2
        checked += 1
        text = current_content(repo, rel) or ""
        actual = len([ln for ln in text.splitlines() if ln.strip()])
        recorded = int(src.get("lines") or 0)
        if actual != recorded:
            problems.append(
                f"{rel}: board records {recorded} lines, file has {actual}"
            )
    if problems:
        return CheckResult(
            name,
            FAIL,
            "the tracked benchmark board disagrees with tracked eval sinks; "
            "a drifted board is a lying board",
            remedy,
            problems,
        )
    if checked == 0:
        return CheckResult(
            name,
            SKIP,
            "no tracked eval sinks are listed in the board",
            remedy,
        )
    return CheckResult(name, PASS, f"{checked} tracked sink(s) agree with the board")


# ---------------------------------------------------------------------------
# C2 -- full board regeneration (needs the gitignored sinks)
# ---------------------------------------------------------------------------


def check_board_regenerates(repo: Path) -> CheckResult:
    name = "board-regenerates"
    remedy = "run `make benchmarks` and commit BENCHMARKS.md + benchmarks.json"
    board_path = repo / BOARD_JSON
    eval_dir = repo / "scripts" / "eval"
    if not board_path.exists() or not (eval_dir / "benchmarks.py").exists():
        return CheckResult(name, SKIP, "benchmarks.py or the board is absent", remedy)

    try:
        board = json.loads(board_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return CheckResult(name, SKIP, f"{BOARD_JSON} is not valid JSON (see {name})", remedy)

    missing = [
        src["path"]
        for src in (board.get("sources") or [])
        if src.get("present") and not (eval_dir / src["path"]).exists()
    ]
    if missing:
        return CheckResult(
            name,
            SKIP,
            "sinks the board was built from are gitignored and absent here: "
            + ", ".join(sorted(missing)),
            "run `make benchmarks-check` on a machine that has the sinks",
        )

    proc = subprocess.run(
        [sys.executable, str(eval_dir / "benchmarks.py"), "--check"],
        capture_output=True,
        text=True,
        cwd=str(repo),
    )
    if proc.returncode == 0:
        return CheckResult(name, PASS, "board regenerates byte-identically")
    detail = (proc.stderr or proc.stdout).strip().replace("\n", " | ")
    return CheckResult(
        name,
        FAIL,
        f"benchmarks.py --check says the tracked board is stale: {detail}",
        remedy,
    )


# ---------------------------------------------------------------------------
# C3 -- append-only files were appended to
# ---------------------------------------------------------------------------


def _first_divergence(base: list[str], now: list[str]) -> int | None:
    for i, line in enumerate(base):
        if i >= len(now) or now[i] != line:
            return i
    return None


def check_append_only(repo: Path, base_ref: str) -> CheckResult:
    name = "append-only"
    remedy = (
        "these files are append-only. Re-derive the file by appending to the "
        f"version at {base_ref} instead of rewriting it: "
        f"`git show {base_ref}:<path> > <path>` then append the new records."
    )
    if not git_ok(repo, "rev-parse", "--verify", f"{base_ref}^{{commit}}"):
        return CheckResult(
            name,
            SKIP,
            f"base ref '{base_ref}' is not resolvable in this checkout "
            "(shallow clone? set fetch-depth: 0)",
            remedy,
        )

    problems: list[str] = []
    checked = 0
    for rel in APPEND_ONLY:
        base_text = blob_at(repo, base_ref, rel)
        if base_text is None:
            continue  # did not exist at base -- nothing to preserve
        now_text = current_content(repo, rel)
        if now_text is None:
            problems.append(f"{rel}: existed at {base_ref} and is now DELETED")
            continue
        checked += 1
        base_lines = base_text.splitlines()
        now_lines = now_text.splitlines()
        if len(now_lines) < len(base_lines):
            problems.append(
                f"{rel}: shrank from {len(base_lines)} to {len(now_lines)} lines"
            )
            continue
        idx = _first_divergence(base_lines, now_lines)
        if idx is not None:
            problems.append(
                f"{rel}: line {idx + 1} was rewritten "
                f"(was {base_lines[idx][:80]!r}, now {now_lines[idx][:80]!r})"
            )
    if problems:
        return CheckResult(
            name,
            FAIL,
            "an append-only eval history was rewritten rather than appended to",
            remedy,
            problems,
        )
    if checked == 0:
        return CheckResult(
            name, SKIP, f"none of the append-only files exist at {base_ref}", remedy
        )
    return CheckResult(name, PASS, f"{checked} append-only file(s) grew by append")


# ---------------------------------------------------------------------------
# C4 -- invalid runs are not quoted
# ---------------------------------------------------------------------------


def invalid_run_ids(repo: Path) -> dict[str, str]:
    """run_id -> where it was found, for every run recorded ``valid: false``.

    Two sources: the tracked board (visible in CI) and any jsonl sink present in
    the checkout (visible locally, gitignored in CI). The CI view is a subset,
    which is stated in CI.md rather than papered over.
    """
    found: dict[str, str] = {}
    board_path = repo / BOARD_JSON
    if board_path.exists():
        try:
            board = json.loads(board_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            board = {}
        for block in board.values() if isinstance(board, dict) else []:
            if not isinstance(block, dict):
                continue
            for run in block.get("invalidated") or []:
                rid = run.get("run_id") if isinstance(run, dict) else None
                if rid:
                    found[str(rid)] = BOARD_JSON

    eval_dir = repo / "scripts" / "eval"
    if eval_dir.exists():
        for sink in sorted(eval_dir.rglob("*.jsonl")):
            try:
                lines = sink.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for line in lines:
                line = line.strip()
                if not line or '"valid"' not in line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(rec, dict) and rec.get("valid") is False and rec.get("run_id"):
                    found.setdefault(
                        str(rec["run_id"]), str(sink.relative_to(repo))
                    )
    return found


def check_invalid_run_quoted(repo: Path) -> CheckResult:
    name = "invalid-run-quoted"
    remedy = (
        "either delete the number or label the run invalid next to it. "
        "Reproduce with: python3 scripts/eval/ci_gate.py"
    )
    registry = invalid_run_ids(repo)
    if not registry:
        return CheckResult(name, PASS, "no runs are recorded valid: false")

    docs = [r for r in tracked_files(repo) if _is_measurement_doc(r)]
    problems: list[str] = []
    for rel in docs:
        text = current_content(repo, rel)
        if text is None:
            continue
        lines = text.splitlines()
        for i, line in enumerate(lines):
            for rid, origin in registry.items():
                if rid not in line:
                    continue
                if not NUMBER_RE.search(line) and not METRIC_RE.search(line):
                    continue
                context = "\n".join(lines[max(0, i - 3): i + 4])
                if INVALID_MARKER_RE.search(context):
                    continue
                problems.append(
                    f"{rel}:{i + 1} quotes run {rid} (recorded valid:false in "
                    f"{origin}) with no invalidation marker within 3 lines"
                )
    if problems:
        return CheckResult(
            name,
            FAIL,
            "a tracked document quotes a metric from an invalidated run",
            remedy,
            problems,
        )
    return CheckResult(
        name, PASS, f"{len(registry)} invalidated run(s), none quoted unmarked"
    )


# ---------------------------------------------------------------------------
# C5 -- metric without n (warning)
# ---------------------------------------------------------------------------


def _table_header_has_n(lines: list[str], i: int) -> bool:
    """True if line ``i`` sits in a markdown table whose header names an n column."""
    if not lines[i].lstrip().startswith("|"):
        return False
    for j in range(i - 1, max(-1, i - 40), -1):
        stripped = lines[j].lstrip()
        if not stripped.startswith("|"):
            return False
        if set(stripped) <= set("|-: \t"):  # the ---|--- separator
            header = lines[j - 1] if j >= 1 else ""
            return bool(N_COLUMN_RE.search(header))
    return False


def check_metric_without_n(repo: Path) -> CheckResult:
    name = "metric-without-n"
    remedy = (
        "state the sample size on or beside the metric (`n=59 queries`). "
        "Reproduce with: python3 scripts/eval/ci_gate.py"
    )
    docs = [r for r in tracked_files(repo) if _is_measurement_doc(r)]
    problems: list[str] = []
    for rel in docs:
        text = current_content(repo, rel)
        if text is None:
            continue
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if not (METRIC_RE.search(line) and NUMBER_RE.search(line)):
                continue
            context = "\n".join(lines[max(0, i - 2): i + 3])
            if N_CUE_RE.search(context) or _table_header_has_n(lines, i):
                continue
            problems.append(f"{rel}:{i + 1}: {line.strip()[:110]}")
    if problems:
        return CheckResult(
            name,
            WARN,
            f"{len(problems)} metric statement(s) with no sample size nearby "
            "(heuristic: an n stated far from the number reads as absent)",
            remedy,
            problems,
        )
    return CheckResult(name, PASS, "every metric statement has an n nearby")


# ---------------------------------------------------------------------------
# C6 -- threshold changes are noted (warning)
# ---------------------------------------------------------------------------


def _parse_thresholds(text: str) -> dict[str, str]:
    """Read the `thresholds:` block without importing yaml (not a CI dependency)."""
    out: dict[str, str] = {}
    in_block = False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if re.match(r"^thresholds\s*:", line):
            in_block = True
            continue
        if in_block:
            if not line.startswith((" ", "\t")):
                break
            m = re.match(r"\s+([A-Za-z0-9_]+)\s*:\s*(\S+)", line)
            if m:
                out[m.group(1)] = m.group(2)
    return out


def check_threshold_note(repo: Path, base_ref: str) -> CheckResult:
    name = "threshold-note"
    remedy = (
        f"add a line to the threshold change log in {CI_DOC} naming the new "
        "value and why it moved"
    )
    if not git_ok(repo, "rev-parse", "--verify", f"{base_ref}^{{commit}}"):
        return CheckResult(name, SKIP, f"base ref '{base_ref}' is not resolvable", remedy)
    base_text = blob_at(repo, base_ref, CONFIG_YAML)
    now_text = current_content(repo, CONFIG_YAML)
    if base_text is None or now_text is None:
        return CheckResult(name, SKIP, f"{CONFIG_YAML} absent at {base_ref} or here", remedy)

    before = _parse_thresholds(base_text)
    after = _parse_thresholds(now_text)
    changed = {
        k: (before.get(k), after.get(k))
        for k in set(before) | set(after)
        if before.get(k) != after.get(k)
    }
    if not changed:
        return CheckResult(name, PASS, "thresholds unchanged")

    note_text = current_content(repo, CI_DOC) or ""
    undocumented = [
        f"{k}: {old} -> {new}"
        for k, (old, new) in sorted(changed.items())
        if not (new and new in note_text and k in note_text)
    ]
    if undocumented:
        return CheckResult(
            name,
            WARN,
            f"{CONFIG_YAML} thresholds moved with no note in {CI_DOC}",
            remedy,
            undocumented,
        )
    return CheckResult(
        name,
        PASS,
        f"{len(changed)} threshold change(s), all noted in {CI_DOC}",
    )


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def run_checks(repo: Path, base_ref: str) -> list[CheckResult]:
    return [
        check_board_tracked_sources(repo),
        check_board_regenerates(repo),
        check_append_only(repo, base_ref),
        check_invalid_run_quoted(repo),
        check_metric_without_n(repo),
        check_threshold_note(repo, base_ref),
    ]


_ICON = {PASS: "✓", FAIL: "✗", WARN: "!", SKIP: "-"}


def render(results: Sequence[CheckResult], base_ref: str) -> str:
    out: list[str] = ["", f"[ci-gate] eval integrity gate (base ref: {base_ref})", ""]
    for r in results:
        out.append(f"  {_ICON[r.status]} {r.status:<4} {r.name}: {r.detail}")
        for item in r.items[:25]:
            out.append(f"        - {item}")
        if len(r.items) > 25:
            out.append(f"        ... and {len(r.items) - 25} more")
        if r.status in (FAIL, WARN) and r.remedy:
            out.append(f"        fix: {r.remedy}")
    fails = [r for r in results if r.status == FAIL]
    warns = [r for r in results if r.status == WARN]
    out.append("")
    if fails:
        out.append(f"[ci-gate] FAILED: {len(fails)} blocking check(s).")
        out.append("[ci-gate] Reproduce locally, from the repo root:")
        out.append("[ci-gate]   python3 scripts/eval/ci_gate.py")
        out.append(f"[ci-gate]   python3 scripts/eval/ci_gate.py --base {base_ref}")
    elif warns:
        out.append(f"[ci-gate] PASSED with {len(warns)} warning(s) (non-blocking).")
    else:
        out.append("[ci-gate] PASSED.")
    out.append("")
    return "\n".join(out)


def exit_code(results: Sequence[CheckResult], strict: bool) -> int:
    if any(r.status == FAIL for r in results):
        return EXIT_FAIL
    if strict and any(r.status == WARN for r in results):
        return EXIT_WARN_STRICT
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Free, offline integrity gate for the Noesis eval artefacts.",
        epilog="exit codes: 0 pass, 1 blocking failure, 2 warnings under --strict, "
               "3 the gate could not run",
    )
    parser.add_argument("--repo", type=Path, default=REPO_ROOT, help="repository root")
    parser.add_argument(
        "--base",
        default="HEAD",
        help="git ref to diff append-only files and thresholds against "
             "(CI should pass the PR base sha)",
    )
    parser.add_argument("--strict", action="store_true", help="treat warnings as failures")
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="emit a machine-readable report on stdout")
    args = parser.parse_args(argv)

    repo = args.repo.resolve()
    if not (repo / ".git").exists():
        sys.stderr.write(f"[ci-gate] not a git repository: {repo}\n")
        return EXIT_CANNOT_RUN
    if not git_ok(repo, "rev-parse", "--git-dir"):
        sys.stderr.write("[ci-gate] git is unavailable or the repo is unreadable\n")
        return EXIT_CANNOT_RUN

    results = run_checks(repo, args.base)
    code = exit_code(results, args.strict)
    if args.as_json:
        print(json.dumps(
            {
                "base_ref": args.base,
                "exit_code": code,
                "checks": [r.to_dict() for r in results],
            },
            indent=2,
            sort_keys=True,
        ))
    else:
        sys.stdout.write(render(results, args.base))
    return code


if __name__ == "__main__":
    raise SystemExit(main())

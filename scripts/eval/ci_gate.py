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
  metric-regression      a metric in a *tracked* eval sink moved the wrong way,
                         beyond the tolerance declared in the `regression:`
                         block of scripts/eval/config.yaml. Only sinks that
                         changed in this diff are looked at, and a record is
                         only ever compared against an earlier record carrying
                         the same config identity -- two identities are two
                         different measurements and are never differenced. A
                         new identity, an absent sink or an unparseable record
                         SKIPs; none of them pass.

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
                         line in the threshold change log in docs/EVAL_GUIDE.md.

WHAT IT CANNOT GATE, EVER, ON A PR (see docs/EVAL_GUIDE.md):
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
from typing import Any, Callable, Sequence

EVAL_DIR = Path(__file__).resolve().parent
REPO_ROOT = EVAL_DIR.parent.parent

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_WARN_STRICT = 2
EXIT_CANNOT_RUN = 3

BOARD_JSON = "docs/benchmarks.json"
BOARD_MD = "docs/BENCHMARKS.md"
CONFIG_YAML = "scripts/eval/config.yaml"
#: The threshold change log lives in the "CI and the eval gate" section of the
#: consolidated eval guide.
CI_DOC = "docs/EVAL_GUIDE.md"

#: Files that are only ever appended to. Two of these are the *only* durable
#: record this repo has of its own eval scores (see the .gitignore negations
#: around scripts/eval/results/). Rewriting a line here silently rewrites
#: history, which is why it is a blocking check and not a warning.
APPEND_ONLY = (
    "scripts/eval/results/history.jsonl",
    "scripts/eval/results/openreview_history.jsonl",
    "scripts/eval/results/node_eval.jsonl",
)

#: Tracked docs that state measurements. Two roots are scanned: docs/, where the
#: consolidated measurement docs now live, and scripts/eval/, which no longer
#: holds any but is kept so a stray measurement doc dropped back beside the
#: harness is still gated. gold/*.md are reference critiques, not measurement
#: reports, so they are excluded. So is private/, the author's working notes,
#: that state their numbers as they were written and are never edited again, and
#: CI_DOC, this gate's own documentation, which quotes metrics as examples of
#: what it flags.
_DOC_ROOTS = ("docs/", "scripts/eval/")


def _is_measurement_doc(rel: str) -> bool:
    return (
        rel.startswith(_DOC_ROOTS)
        and rel.endswith(".md")
        and "/gold/" not in rel
        and not rel.startswith("private/")
        and rel != CI_DOC
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
    which is stated in docs/EVAL_GUIDE.md rather than papered over.
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


#: A declared tolerance: `<metric>: <amount>[%] <direction>`. Metric names carry
#: `.` and `@` (`ndcg@10`), so the key charset is wider than in `thresholds:`.
_REGRESSION_LINE_RE = re.compile(
    r"^\s+([A-Za-z0-9_.@]+)\s*:\s*(\d+(?:\.\d+)?)(%?)\s+(up_is_bad|down_is_bad)\s*$"
)

UP_IS_BAD, DOWN_IS_BAD = "up_is_bad", "down_is_bad"


@dataclass(frozen=True)
class Tolerance:
    """How far a metric may move, and which way counts as a regression.

    ``relative`` tolerances are a fraction of the baseline; cost varies with
    prompt-token counts, so an absolute dollar figure is either meaninglessly
    tight on a cheap config or useless on an expensive one.
    """

    amount: float
    relative: bool
    direction: str

    def allowance(self, baseline: float) -> float:
        return abs(baseline) * self.amount if self.relative else self.amount

    def rendered(self) -> str:
        return f"{self.amount * 100:g}%" if self.relative else f"{self.amount:g}"


def _parse_regression_config(text: str) -> dict[str, Tolerance]:
    """Read the `regression:` block without importing yaml (not a CI dependency).

    Same shape as :func:`_parse_thresholds`, and for the same reason: the PR
    runner installs pytest and nothing else.
    """
    out: dict[str, Tolerance] = {}
    in_block = False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if re.match(r"^regression\s*:", line):
            in_block = True
            continue
        if in_block:
            if not line.startswith((" ", "\t")):
                break
            m = _REGRESSION_LINE_RE.match(line)
            if m:
                out[m.group(1)] = Tolerance(
                    amount=float(m.group(2)) / (100.0 if m.group(3) else 1.0),
                    relative=bool(m.group(3)),
                    direction=m.group(4),
                )
    return out


def _gated_settings(text: str) -> dict[str, str]:
    """Every config value whose movement needs a documented line (C6).

    Both the `thresholds:` block and the per-metric regression tolerances: a
    tolerance quietly widened is a gate quietly switched off.
    """
    out = dict(_parse_thresholds(text))
    for metric, tol in _parse_regression_config(text).items():
        out[f"regression.{metric}"] = tol.rendered()
        out[f"regression.{metric}.direction"] = tol.direction
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

    before = _gated_settings(base_text)
    after = _gated_settings(now_text)
    changed = {
        k: (before.get(k), after.get(k))
        for k in set(before) | set(after)
        if before.get(k) != after.get(k)
    }
    if not changed:
        return CheckResult(name, PASS, "thresholds and regression tolerances unchanged")

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
            f"{CONFIG_YAML} thresholds/tolerances moved with no note in {CI_DOC}",
            remedy,
            undocumented,
        )
    return CheckResult(
        name,
        PASS,
        f"{len(changed)} threshold/tolerance change(s), all noted in {CI_DOC}",
    )


# ---------------------------------------------------------------------------
# C7 -- a tracked metric moved the wrong way
# ---------------------------------------------------------------------------

#: One measurement pulled out of one sink record: what was measured (identity)
#: and what came out (metrics). A single record can carry several -- an
#: embedding_arms record holds one entry per arm, each with its own config hash.
Entry = tuple[str, dict[str, float]]


def _num(value: Any) -> float | None:
    """A metric value, or None. Bools are not metrics; NaN is not a number."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return None if value != value else value


def _dig(record: Any, *path: str) -> Any:
    for key in path:
        if not isinstance(record, dict):
            return None
        record = record.get(key)
    return record


def _identity(*parts: Any) -> str:
    return "|".join("" if p is None else str(p) for p in parts)


def _entries_history(record: dict) -> list[Entry]:
    """results/history.jsonl -- the run_eval scoreboard log."""
    config = record.get("config")
    if not isinstance(config, dict):
        return []
    agg = record.get("aggregates") or {}
    metrics = {
        k: v
        for k, v in (
            ("mean_overall", _num(agg.get("mean_overall"))),
            ("total_hallucinations", _num(agg.get("total_hallucinations"))),
            ("scored_cells", _num(agg.get("scored_cells"))),
        )
        if v is not None
    }
    return [(json.dumps(config, sort_keys=True), metrics)] if metrics else []


def _entries_openreview(record: dict) -> list[Entry]:
    """results/openreview_history.jsonl -- same log, OpenReview track.

    Its aggregates block carries only a paper count, so the metrics are rolled
    up from the cells: how many were scored, and how many hallucinations the
    judge found across them.
    """
    config = record.get("config")
    cells = record.get("cells")
    if not isinstance(config, dict) or not isinstance(cells, list):
        return []
    hallucinations = sum(
        _num(c.get("hallucinations")) or 0.0 for c in cells if isinstance(c, dict)
    )
    metrics = {
        "scored_cells": float(len(cells)),
        "total_hallucinations": hallucinations,
    }
    return [(json.dumps(config, sort_keys=True), metrics)]


def _entries_node_eval(record: dict) -> list[Entry]:
    """results/node_eval.jsonl -- only the run summaries carry totals.

    node_eval writes no config hash, so the identity is derived from the fields
    that decide comparability. This mirrors ``_node_config_key`` in
    benchmarks.py deliberately rather than importing it: the gate must stay a
    standalone stdlib module, and benchmarks.py is only ever subprocessed.
    ``state_dir`` is excluded on purpose -- it is an absolute path and would
    make every machine its own identity.
    """
    if record.get("record_type") != "run_summary":
        return []
    config = record.get("config") or {}
    identity = _identity(
        ",".join(sorted(str(n) for n in (config.get("nodes") or []))),
        ",".join(sorted(str(p) for p in (config.get("papers") or []))),
        config.get("reviewer_type"),
        config.get("repeat"),
        config.get("with_metric"),
    )
    metrics = {
        k: v
        for k, v in (
            ("total_estimated_usd", _num(record.get("total_estimated_usd"))),
            ("failed_replays", _num(record.get("failed_replays"))),
        )
        if v is not None
    }
    return [(identity, metrics)] if metrics else []


def _entries_sweep(record: dict) -> list[Entry]:
    """gate_calibration/sweep_results.jsonl -- publish-gate calibration.

    Identity is the schema, the seed and the labelled set the sweep ran over;
    a sweep over a different label set is a different measurement.
    """
    dataset = record.get("dataset")
    shipped = record.get("gate_as_shipped")
    if not isinstance(dataset, dict) or not isinstance(shipped, dict):
        return []
    identity = _identity(
        record.get("schema_version"),
        record.get("seed"),
        dataset.get("n_scoreable"),
        dataset.get("base_rate"),
    )
    metrics = {
        k: v
        for k, v in (
            ("precision", _num(shipped.get("precision"))),
            ("recall", _num(shipped.get("recall"))),
            ("f1", _num(shipped.get("f1"))),
            ("best_f1", _num(_dig(record, "joint", "best_f1", "f1"))),
        )
        if v is not None
    }
    return [(identity, metrics)] if metrics else []


def _entries_panel_arms(record: dict) -> list[Entry]:
    """results/panel_arms.jsonl -- one arm of the reviewer-panel experiment."""
    identity = record.get("config_hash")
    if not identity:
        return []
    metrics = {
        k: v
        for k, v in (
            ("recall_addressable", _num(_dig(record, "score", "recall_addressable"))),
            ("usd_per_verified_finding", _num(record.get("usd_per_verified_finding"))),
            ("unverified_quote_rate", _num(_dig(record, "unverified_quotes", "rate"))),
            ("n_errors", _num(record.get("n_errors"))),
        )
        if v is not None
    }
    return [(str(identity), metrics)] if metrics else []


def _entries_embedding_arms(record: dict) -> list[Entry]:
    """results/embedding_arms.jsonl -- one record, several arms, one hash each."""
    out: list[Entry] = []
    for arm in record.get("arms") or []:
        if not isinstance(arm, dict) or not arm.get("config_hash"):
            continue
        raw = arm.get("metrics") or {}
        metrics = {
            k: v
            for k, v in (
                ("map", _num(raw.get("map"))),
                ("mrr", _num(raw.get("mrr"))),
                ("ndcg@10", _num(raw.get("ndcg@10"))),
                ("recall@10", _num(raw.get("recall@10"))),
                ("latency_p50_ms", _num(_dig(arm, "latency_ms", "p50"))),
            )
            if v is not None
        }
        if metrics:
            out.append((str(arm["config_hash"]), metrics))
    return out


#: The sinks this check may look at: tracked in git, therefore present on a
#: clean PR runner, therefore gate-able. Everything else this project measures
#: -- retrieval_eval, ann_sweep, node_eval_spans, the ingest manifest,
#: cascade_arms -- is gitignored, costs money or needs a live vector database,
#: and is not gated here. See the module docstring.
REGRESSION_SINKS: tuple[tuple[str, Callable[[dict], list[Entry]]], ...] = (
    ("scripts/eval/results/history.jsonl", _entries_history),
    ("scripts/eval/results/openreview_history.jsonl", _entries_openreview),
    ("scripts/eval/results/node_eval.jsonl", _entries_node_eval),
    ("scripts/eval/gate_calibration/sweep_results.jsonl", _entries_sweep),
    ("scripts/eval/results/panel_arms.jsonl", _entries_panel_arms),
    ("scripts/eval/results/embedding_arms.jsonl", _entries_embedding_arms),
)


def _violates(tol: Tolerance, baseline: float, new: float) -> bool:
    delta = new - baseline
    allowed = tol.allowance(baseline)
    if tol.direction == UP_IS_BAD:
        return delta > allowed
    return -delta > allowed


def _short(identity: str, width: int = 60) -> str:
    return identity if len(identity) <= width else identity[: width - 3] + "..."


def check_metric_regression(repo: Path, base_ref: str) -> CheckResult:
    name = "metric-regression"
    remedy = (
        "either the change is a real regression and belongs in the diff no "
        "further, or the movement is understood -- in which case say so in the "
        f"run's own notes and, if the bar itself has moved, widen the metric's "
        f"line in the `regression:` block of {CONFIG_YAML} (which needs its own "
        f"note in {CI_DOC}). Reproduce with: "
        f"python3 scripts/eval/ci_gate.py --base {base_ref}"
    )
    if not git_ok(repo, "rev-parse", "--verify", f"{base_ref}^{{commit}}"):
        return CheckResult(
            name,
            SKIP,
            f"base ref '{base_ref}' is not resolvable in this checkout "
            "(shallow clone? set fetch-depth: 0)",
            remedy,
        )

    config_text = current_content(repo, CONFIG_YAML)
    if config_text is None:
        return CheckResult(name, SKIP, f"{CONFIG_YAML} is absent; no tolerances to read", remedy)
    tolerances = _parse_regression_config(config_text)
    if not tolerances:
        return CheckResult(
            name,
            SKIP,
            f"{CONFIG_YAML} declares no `regression:` block, so nothing is gated",
            remedy,
        )

    violations: list[str] = []
    notes: list[str] = []
    compared = 0
    changed_sinks = 0

    for rel, extract in REGRESSION_SINKS:
        now_text = current_content(repo, rel)
        if now_text is None:
            notes.append(f"{rel}: absent from this checkout -- NOT CHECKED, not passed")
            continue
        base_text = blob_at(repo, base_ref, rel)
        if base_text is not None and base_text == now_text:
            continue  # untouched by this diff; nothing to regress
        changed_sinks += 1

        lines = [ln for ln in now_text.splitlines() if ln.strip()]
        if not lines:
            notes.append(f"{rel}: changed but holds no records -- NOT CHECKED")
            continue

        records: list[dict | None] = []
        for i, line in enumerate(lines):
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                notes.append(
                    f"{rel}:{i + 1}: unparseable JSON (truncated tail? hand edit?) "
                    "-- NOT CHECKED, not passed"
                )
                records.append(None)
                continue
            records.append(rec if isinstance(rec, dict) else None)

        if records[-1] is None:
            notes.append(f"{rel}: the newest record is unreadable -- NOT CHECKED, not passed")
            continue

        history: dict[str, dict[str, float]] = {}
        for rec in records[:-1]:
            if rec is None:
                continue
            for identity, metrics in extract(rec):
                history[identity] = metrics

        newest = extract(records[-1])
        if not newest:
            notes.append(
                f"{rel}: the newest record carries no gate-able measurement "
                "-- NOT CHECKED, not passed"
            )
            continue

        for identity, metrics in newest:
            baseline = history.get(identity)
            if baseline is None:
                notes.append(
                    f"{rel}: newest record is a NEW config identity "
                    f"'{_short(identity)}' with no earlier run to compare against "
                    "-- NOT CHECKED, not passed"
                )
                continue
            for metric, new_value in sorted(metrics.items()):
                tol = tolerances.get(metric)
                if tol is None:
                    continue  # not declared in config.yaml, so not gated
                old_value = baseline.get(metric)
                if old_value is None:
                    notes.append(
                        f"{rel}: '{metric}' is absent from the baseline record for "
                        f"'{_short(identity)}' -- NOT CHECKED, not passed"
                    )
                    continue
                compared += 1
                if _violates(tol, old_value, new_value):
                    violations.append(
                        f"{rel}: {metric}  {old_value:g} -> {new_value:g}  "
                        f"(tolerance {tol.rendered()} {tol.direction})  "
                        f"[{_short(identity)}]"
                    )

    if violations:
        return CheckResult(
            name,
            FAIL,
            f"{len(violations)} metric(s) in a tracked eval sink moved the wrong "
            "way by more than the declared tolerance",
            remedy,
            violations,
        )
    if notes:
        return CheckResult(
            name,
            SKIP,
            f"{compared} metric(s) compared cleanly, but {len(notes)} record(s) "
            "or sink(s) could not be compared at all -- a skip is missing data, "
            "not a pass",
            remedy,
            notes,
        )
    if changed_sinks == 0:
        return CheckResult(name, PASS, "no tracked eval sink changed in this diff")
    return CheckResult(
        name,
        PASS,
        f"{compared} metric(s) across {changed_sinks} changed sink(s) are within "
        "tolerance of their same-config baseline",
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
        check_metric_regression(repo, base_ref),
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

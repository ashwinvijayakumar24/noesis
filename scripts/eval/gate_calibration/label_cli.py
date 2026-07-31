#!/usr/bin/env python3
"""Blind, resumable labelling tool for publish-gate calibration.

Presents one analysis-run export at a time — the critique a user would actually
receive — and records a human ``degraded`` / ``ok`` / ``unsure`` judgement.

The gate's verdict and all three candidate predictor scores
(``parser_quality_score``, ``page_anchor_coverage``, ``verbatim_anchor_coverage``)
are **withheld from the display**. That is the entire point: a label that has
seen the gate's opinion is correlated with the gate by construction, and scoring
the gate against it measures nothing. See ``docs/gate_rubric.md`` section 0.

Usage::

    python3 label_cli.py --stats
    python3 label_cli.py --labeller viji
    python3 label_cli.py --relabel cXs5md5wAq__no-corpus__2026-06-21T03-59-08

Labels are appended to ``labels.jsonl``. The file is append-only: a correction
is a new record, never an edit, so the labelling history stays auditable.
"""

from __future__ import annotations

import argparse
import collections
import datetime as _dt
import getpass
import json
import os
import sys
from pathlib import Path
from typing import Any, Iterator

PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_RESULTS_DIR = PACKAGE_DIR.parent / "results"
DEFAULT_LABELS_PATH = PACKAGE_DIR / "labels.jsonl"
OPENREVIEW_DIR = PACKAGE_DIR.parent / "openreview"

VALID_LABELS = ("degraded", "ok", "unsure")

# Files in the results directory that are aggregates, not per-run exports.
_NON_EXPORT_STEMS = {"scoreboard", "openreview_scoreboard"}


# --------------------------------------------------------------------------
# export loading
# --------------------------------------------------------------------------


class MalformedExport(Exception):
    """Raised when an export cannot be parsed into a labellable record."""


def _get(d: Any, *path, default=None):
    cur = d
    for key in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
        if cur is None:
            return default
    return cur


def load_export(path: Path) -> dict[str, Any]:
    """Parse one export into a normalised record.

    Raises :class:`MalformedExport` for anything that is not a per-run export —
    aggregate scoreboards, truncated JSON, exports missing the analysis block.
    Callers are expected to catch it and skip; a bad file must never take the
    labelling session down mid-batch.
    """
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise MalformedExport(f"unreadable JSON: {exc}") from exc

    if not isinstance(raw, dict):
        raise MalformedExport("top level is not an object")
    if "eval_metadata" not in raw:
        raise MalformedExport("no eval_metadata (aggregate file, not a run export)")
    if not isinstance(raw.get("analysis"), dict):
        raise MalformedExport("no analysis block")

    meta = raw.get("analysis_metadata") if isinstance(raw.get("analysis_metadata"), dict) else None
    meta = meta or _get(raw, "analysis", "analysis_metadata", default={})
    rqm = meta.get("revision_quality_metrics") or {}
    gate = meta.get("publish_gate") or {}
    parser = raw.get("parser_metadata") or {}

    tasks = raw.get("durable_revision_tasks") or []
    if not isinstance(tasks, list):
        raise MalformedExport("durable_revision_tasks is not a list")

    meta_reviews = raw.get("meta_reviews") or []
    meta_review = meta_reviews[0] if isinstance(meta_reviews, list) and meta_reviews else {}

    return {
        "run_id": path.stem,
        "path": str(path),
        "analysis_run_id": _get(raw, "eval_metadata", "analysis_run_id"),
        "draft_file": _get(raw, "eval_metadata", "draft_file"),
        "corpus": _get(raw, "eval_metadata", "corpus"),
        "generated_at": _get(raw, "eval_metadata", "generated_at"),
        # ---- shown to the labeller ----
        "title": _get(raw, "draft", "title") or path.stem,
        "file_type": _get(raw, "draft", "file_type"),
        "word_count": _get(raw, "analysis", "word_count"),
        "page_count": _get(raw, "analysis", "structure", "page_count"),
        "sections": [
            s.get("title") or s.get("name") or s.get("section_type") or "?"
            for s in (_get(raw, "analysis", "structure", "sections", default=[]) or [])
            if isinstance(s, dict)
        ],
        "tasks": [t for t in tasks if isinstance(t, dict)],
        "reviewer_feedback": [
            f for f in (raw.get("reviewer_feedback") or []) if isinstance(f, dict)
        ],
        "meta_review": meta_review if isinstance(meta_review, dict) else {},
        # ---- HIDDEN from the labeller; consumed only by sweep.py ----
        "_hidden": {
            "gate_status": gate.get("gate_status"),
            "publishable": gate.get("publishable"),
            "confidence": gate.get("confidence"),
            "parser_quality_score": _first_not_none(
                _get(gate, "observed", "parser_quality_score"),
                parser.get("parser_quality_score"),
            ),
            "page_anchor_coverage": rqm.get("page_anchor_coverage"),
            "verbatim_anchor_coverage": rqm.get("verbatim_anchor_coverage"),
            "anchor_coverage": rqm.get("anchor_coverage"),
            "total_tasks": rqm.get("total_tasks"),
            "parse_blocked": _get(gate, "observed", "parse_blocked"),
            "analysis_status": meta.get("analysis_status"),
            "readiness_score": meta.get("readiness_score"),
        },
    }


def _first_not_none(*vals):
    for v in vals:
        if v is not None:
            return v
    return None


def iter_exports(results_dir: Path, verbose: bool = True) -> Iterator[dict[str, Any]]:
    """Yield every loadable export in ``results_dir``, in filename order.

    Unloadable files are reported on stderr and skipped.
    """
    if not results_dir.is_dir():
        raise SystemExit(f"results dir not found: {results_dir}")
    for path in sorted(results_dir.glob("*.json")):
        if path.stem in _NON_EXPORT_STEMS:
            continue
        try:
            yield load_export(path)
        except MalformedExport as exc:
            if verbose:
                print(f"[skip] {path.name}: {exc}", file=sys.stderr)


# --------------------------------------------------------------------------
# label store (append-only jsonl)
# --------------------------------------------------------------------------


def read_labels(labels_path: Path) -> list[dict[str, Any]]:
    """All label records in file order. Malformed lines are skipped, not fatal."""
    if not labels_path.exists():
        return []
    out: list[dict[str, Any]] = []
    for lineno, line in enumerate(labels_path.read_text().splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            print(f"[skip] {labels_path.name}:{lineno}: unparseable label line", file=sys.stderr)
            continue
        if isinstance(rec, dict) and rec.get("run_id"):
            out.append(rec)
    return out


def latest_labels(labels_path: Path) -> dict[str, dict[str, Any]]:
    """Current label per run: the **last** record wins, so a relabel supersedes."""
    current: dict[str, dict[str, Any]] = {}
    for rec in read_labels(labels_path):
        current[rec["run_id"]] = rec
    return current


def append_label(
    labels_path: Path,
    run_id: str,
    label: str,
    labeller: str,
    note: str = "",
    superseded: bool = False,
) -> dict[str, Any]:
    """Append one label record. Never rewrites existing lines."""
    if label not in VALID_LABELS:
        raise ValueError(f"label must be one of {VALID_LABELS}, got {label!r}")
    rec = {
        "run_id": run_id,
        "label": label,
        "note": note or "",
        "labeller": labeller,
        "timestamp": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "is_relabel": bool(superseded),
    }
    labels_path.parent.mkdir(parents=True, exist_ok=True)
    with labels_path.open("a") as fh:
        fh.write(json.dumps(rec) + "\n")
    return rec


# --------------------------------------------------------------------------
# presentation (gate verdict and all three scores deliberately absent)
# --------------------------------------------------------------------------


def _wrap(text: str, width: int = 96, indent: str = "      ") -> str:
    import textwrap

    return "\n".join(
        textwrap.fill(para, width=width, initial_indent=indent, subsequent_indent=indent)
        for para in str(text).split("\n")
        if para.strip()
    )


def paper_id_from_run_id(run_id: str) -> str:
    """``cXs5md5wAq__no-corpus__2026-06-21T03-59-08`` -> ``cXs5md5wAq``.

    The run id is the only place the source paper survives; ``eval_metadata.
    draft_file`` was not enough to tell which manuscript a run belonged to.
    """
    return str(run_id).split("__", 1)[0]


def resolve_pdf_path(run_id: str, openreview_dir: Path = OPENREVIEW_DIR) -> Path | None:
    """The manuscript PDF for a run, or None if it is not on disk.

    Venue directory is not encoded in the run id, so this globs one level:
    ``openreview/<venue>/<paper_id>.pdf``.
    """
    paper_id = paper_id_from_run_id(run_id)
    if not paper_id:
        return None
    for candidate in sorted(openreview_dir.glob(f"*/{paper_id}.pdf")):
        return candidate
    return None


def render_run(rec: dict[str, Any], max_tasks: int = 40) -> str:
    """Human-readable presentation of one run. Contains no gate scores by design."""
    lines: list[str] = []
    lines.append("=" * 100)
    lines.append(f"RUN: {rec['run_id']}")
    paper_id = paper_id_from_run_id(rec["run_id"])
    pdf = resolve_pdf_path(rec["run_id"])
    lines.append(f"PAPER: {paper_id}")
    lines.append(f"PDF  : {pdf if pdf is not None else '(not found under openreview/)'}")
    lines.append(f"Title: {rec.get('title')}")
    lines.append(
        f"Type: {rec.get('file_type')}   Words: {rec.get('word_count')}   "
        f"Pages: {rec.get('page_count')}   Sections: {len(rec.get('sections') or [])}"
    )
    secs = rec.get("sections") or []
    if secs:
        lines.append("Section headings: " + " | ".join(str(s) for s in secs[:24]))
    lines.append("-" * 100)

    tasks = rec.get("tasks") or []
    lines.append(f"DURABLE REVISION TASKS ({len(tasks)})")
    if not tasks:
        lines.append("      (none — see rubric tie-break T4)")
    order = {"critical": 0, "major": 1, "minor": 2}
    for i, t in enumerate(
        sorted(tasks, key=lambda t: order.get(str(t.get("severity")).lower(), 3))[:max_tasks],
        start=1,
    ):
        lines.append("")
        lines.append(
            f"  [{i}] severity={t.get('severity')}  type={t.get('task_type')}  "
            f"section={t.get('section')}  page={t.get('page_number')}"
        )
        if t.get("problem"):
            lines.append("    problem:")
            lines.append(_wrap(t["problem"]))
        if t.get("why_it_matters"):
            lines.append("    why it matters:")
            lines.append(_wrap(t["why_it_matters"]))
        if t.get("suggested_action"):
            lines.append("    suggested action:")
            lines.append(_wrap(t["suggested_action"]))
        if t.get("anchor_text"):
            lines.append("    anchor quote:")
            lines.append(_wrap(f"“{t['anchor_text']}”"))

    fb = rec.get("reviewer_feedback") or []
    if fb:
        lines.append("")
        lines.append("-" * 100)
        lines.append(f"REVIEWER FEEDBACK ({len(fb)})")
        for f in fb[:10]:
            lines.append(
                f"  - [{f.get('severity')}] {f.get('feedback_type')} / {f.get('section_reference')}"
            )
            if f.get("feedback_text"):
                lines.append(_wrap(f["feedback_text"]))

    mr = rec.get("meta_review") or {}
    if mr:
        lines.append("")
        lines.append("-" * 100)
        lines.append("META REVIEW")
        lines.append(f"  recommendation: {mr.get('overall_recommendation')}")
        for key in ("must_address", "nice_to_address", "consensus_weaknesses"):
            items = mr.get(key) or []
            if items:
                lines.append(f"  {key}:")
                for it in items[:6]:
                    lines.append(_wrap(f"- {it}"))
    lines.append("=" * 100)
    return "\n".join(lines)


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------


def cmd_stats(results_dir: Path, labels_path: Path) -> int:
    exports = list(iter_exports(results_dir))
    current = latest_labels(labels_path)
    export_ids = {e["run_id"] for e in exports}

    counts = collections.Counter(
        rec["label"] for rid, rec in current.items() if rid in export_ids
    )
    labelled = sum(counts.values())
    total_records = len(read_labels(labels_path))
    orphans = [rid for rid in current if rid not in export_ids]

    print(f"results dir : {results_dir}")
    print(f"labels file : {labels_path}{'' if labels_path.exists() else '  (does not exist yet)'}")
    print(f"exports available : {len(exports)}")
    print(f"runs labelled     : {labelled}")
    print(f"runs remaining    : {len(export_ids) - labelled}")
    print(f"label records on disk (incl. superseded relabels): {total_records}")
    print("")
    print("label distribution:")
    for lab in VALID_LABELS:
        n = counts.get(lab, 0)
        pct = (100.0 * n / labelled) if labelled else 0.0
        print(f"  {lab:<9} {n:>4}  ({pct:5.1f}%)")
    scored = counts.get("degraded", 0) + counts.get("ok", 0)
    if scored:
        print(f"\nusable for metrics (degraded+ok): {scored}")
        print(f"observed degraded base rate     : {counts.get('degraded', 0) / scored:.3f}")
    if labelled and counts.get("unsure", 0) / labelled > 0.15:
        print("\nWARNING: unsure rate above 15% — rubric may be underspecified (see docs/gate_rubric.md s4)")
    if scored and scored < 30:
        print(f"\nWARNING: only {scored} scoreable labels; metrics will be very noisy (want >= 30)")
    if orphans:
        print(f"\nnote: {len(orphans)} labelled run_id(s) have no matching export in {results_dir}")
    by_labeller = collections.Counter(
        rec.get("labeller", "?") for rec in current.values() if rec["run_id"] in export_ids
    )
    if by_labeller:
        print("\nby labeller: " + ", ".join(f"{k}={v}" for k, v in sorted(by_labeller.items())))
    return 0


def _prompt_label(prompt: str = "label") -> tuple[str | None, bool]:
    """Return ``(label_or_None, quit_requested)``."""
    while True:
        try:
            raw = input(
                f"{prompt} [d]egraded / [o]k / [u]nsure / [s]kip / [q]uit > "
            ).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("")
            return None, True
        if raw in ("d", "degraded"):
            return "degraded", False
        if raw in ("o", "ok"):
            return "ok", False
        if raw in ("u", "unsure"):
            return "unsure", False
        if raw in ("s", "skip", ""):
            return None, False
        if raw in ("q", "quit", "exit"):
            return None, True
        print("  unrecognised — enter d, o, u, s or q")


def _prompt_note() -> str:
    try:
        return input("note (optional, enter to skip) > ").strip()
    except (EOFError, KeyboardInterrupt):
        return ""


def cmd_label(
    results_dir: Path, labels_path: Path, labeller: str, limit: int | None
) -> int:
    done = set(latest_labels(labels_path))
    pending = [e for e in iter_exports(results_dir) if e["run_id"] not in done]
    if not pending:
        print("Nothing left to label. Run --stats for the distribution.")
        return 0
    if limit is not None:
        pending = pending[:limit]

    print(f"{len(pending)} run(s) to label as '{labeller}'.")
    print("Reminder: you are judging the CRITIQUE, not the paper. Gate scores are hidden")
    print("on purpose — do not go look them up. See docs/gate_rubric.md.\n")

    n = 0
    for i, rec in enumerate(pending, start=1):
        print(f"\n({i}/{len(pending)})")
        print(render_run(rec))
        label, quit_now = _prompt_label()
        if quit_now:
            break
        if label is None:
            print("  skipped (not recorded — it will come round again)")
            continue
        note = _prompt_note()
        append_label(labels_path, rec["run_id"], label, labeller, note)
        n += 1
        print(f"  recorded: {label}")

    print(f"\n{n} label(s) appended to {labels_path}")
    return 0


def cmd_relabel(results_dir: Path, labels_path: Path, run_id: str, labeller: str) -> int:
    existing = latest_labels(labels_path).get(run_id)
    if existing is None:
        print(f"{run_id!r} has no existing label; use the normal labelling flow.", file=sys.stderr)
        return 1

    rec = None
    for e in iter_exports(results_dir, verbose=False):
        if e["run_id"] == run_id:
            rec = e
            break
    if rec is None:
        print(f"no export found for run_id {run_id!r} in {results_dir}", file=sys.stderr)
        return 1

    print(render_run(rec))
    print(
        f"\nCurrent label: {existing['label']} "
        f"(by {existing.get('labeller')} at {existing.get('timestamp')})"
    )
    if existing.get("note"):
        print(f"Current note : {existing['note']}")
    label, quit_now = _prompt_label(prompt="new label")
    if quit_now or label is None:
        print("unchanged.")
        return 0
    note = _prompt_note()
    append_label(labels_path, run_id, label, labeller, note, superseded=True)
    print(f"appended relabel: {existing['label']} -> {label} (history preserved)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Blind, resumable labelling tool for publish-gate calibration.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    p.add_argument("--labels", type=Path, default=DEFAULT_LABELS_PATH)
    p.add_argument("--labeller", default=os.getenv("GATE_LABELLER") or _default_user())
    p.add_argument("--stats", action="store_true", help="show progress and label distribution")
    p.add_argument("--relabel", metavar="RUN_ID", help="append a corrected label for one run")
    p.add_argument("--limit", type=int, default=None, help="label at most N runs this session")
    return p


def _default_user() -> str:
    try:
        return getpass.getuser()
    except Exception:  # pragma: no cover - platform dependent
        return "unknown"


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    results_dir = args.results_dir.expanduser().resolve()
    labels_path = args.labels.expanduser().resolve()

    if args.stats:
        return cmd_stats(results_dir, labels_path)
    if args.relabel:
        return cmd_relabel(results_dir, labels_path, args.relabel, args.labeller)
    return cmd_label(results_dir, labels_path, args.labeller, args.limit)


if __name__ == "__main__":
    raise SystemExit(main())

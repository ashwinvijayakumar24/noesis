"""
Eval loop: run all drafts × corpora from config.yaml → judge → scoreboard.

Usage:
    python scripts/eval/run_eval.py                  # full run
    python scripts/eval/run_eval.py --quick          # first 3 drafts only
    python scripts/eval/run_eval.py --stability 3    # run each cell 3x, check variance

Must run inside the backend container.

Regression gate: exits non-zero if mean overall drops >0.5 vs the best previously
recorded score for that cell, or any new hallucination appears.

Results are APPEND-ONLY (changed 2026-07-30). Before this change every run
overwrote results/scoreboard.json in place, so each run destroyed the previous one
and no before/after comparison existed anywhere in the project's history.

  results/scoreboard.json             current-state pointer, still overwritten.
                                      Same shape as before — existing readers are
                                      unaffected.
  results/history.jsonl               immutable append-only log, one JSON object
                                      per run. Never rewritten.
  results/openreview_history.jsonl    same, for the --openreview track.

Each history record carries generated_at, run_id, the pipeline version hash from
pipeline_cache.pipeline_version() (a SHA over every draft_analysis workflow file —
reused, not reinvented), the config in force, aggregates, and per-cell scores.

The regression gate reads history.jsonl, not just the last scoreboard, so slow
multi-run drift is caught: a cell that loses 0.3 per run for three runs now fails
even though no single step exceeded max_mean_drop.
"""

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

if Path("/app/app").exists():
    REPO_ROOT = Path("/app")
    if "/app" not in sys.path:
        sys.path.insert(0, "/app")
else:
    REPO_ROOT = Path(__file__).resolve().parent.parent.parent
    _svc = str(REPO_ROOT / "services" / "backend")
    if _svc not in sys.path:
        sys.path.insert(0, _svc)

EVAL_DIR = Path(__file__).resolve().parent
RESULTS_DIR = EVAL_DIR / "results"
CONFIG_PATH = EVAL_DIR / "config.yaml"
HISTORY_PATH = RESULTS_DIR / "history.jsonl"
OPENREVIEW_HISTORY_PATH = RESULTS_DIR / "openreview_history.jsonl"


def _pipeline_version() -> str:
    """SHA over every draft_analysis workflow file. Reuses pipeline_cache."""
    try:
        from scripts.eval.pipeline_cache import pipeline_version
    except ImportError:
        try:
            from pipeline_cache import pipeline_version  # type: ignore[no-redef]
        except ImportError:
            return "unavailable"
    try:
        return pipeline_version()
    except Exception:
        return "unavailable"


def append_history(record: dict, path: Path = HISTORY_PATH) -> Path:
    """Append one immutable JSON line. Never truncates or rewrites."""
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, default=str, sort_keys=True)
    # A run killed mid-write leaves a truncated line with no newline. Start a fresh
    # line so the new record is not concatenated onto the corrupt tail (which would
    # make BOTH unreadable and lose this run too).
    needs_newline = False
    if path.exists() and path.stat().st_size:
        with path.open("rb") as handle:
            handle.seek(-1, 2)
            needs_newline = handle.read(1) != b"\n"
    with path.open("a", encoding="utf-8") as handle:
        if needs_newline:
            handle.write("\n")
        handle.write(line + "\n")
    return path


def load_history(path: Path = HISTORY_PATH) -> list[dict]:
    """Read history, skipping corrupt/partial lines rather than crashing the run."""
    if not path.exists():
        return []
    records: list[dict] = []
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue  # truncated tail from a killed run, or hand-editing
        if isinstance(record, dict):
            records.append(record)
    return records


def build_history_record(
    rows: list[dict],
    cfg: dict,
    mean_overall: float,
    total_hallucinations: int,
    *,
    args: argparse.Namespace | None = None,
) -> dict:
    scored_rows = [r for r in rows if r.get("overall") is not None]
    return {
        "run_id": uuid.uuid4().hex,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pipeline_version": _pipeline_version(),
        "config": {
            "drafts": cfg.get("drafts", []),
            "corpora": cfg.get("corpora", []),
            "auto_corpus": cfg.get("auto_corpus", False),
            "thresholds": cfg.get("thresholds", {}),
            "quick": bool(getattr(args, "quick", False)),
            "stability": getattr(args, "stability", None),
        },
        "aggregates": {
            "mean_overall": round(mean_overall, 4),
            "total_hallucinations": total_hallucinations,
            "total_cells": len(rows),
            "scored_cells": len(scored_rows),
        },
        "cells": [
            {
                "cell_key": _cell_key(r.get("draft_stem", "?"), r.get("corpus", "?")),
                "draft_stem": r.get("draft_stem"),
                "corpus": r.get("corpus"),
                "overall": r.get("overall"),
                "dims": {
                    dim: (dval.get("score") if isinstance(dval, dict) else dval)
                    for dim, dval in (r.get("dims") or {}).items()
                },
                "hallucinations": len(r.get("hallucinations") or []),
                "error": r.get("error"),
            }
            for r in rows
        ],
    }


def _load_config() -> dict:
    try:
        import yaml
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f)
    except ImportError:
        # Parse minimal YAML by hand (no pyyaml dep in container)
        import re
        cfg: dict = {"drafts": [], "corpora": [], "thresholds": {}}
        text = CONFIG_PATH.read_text()
        for line in text.splitlines():
            m = re.match(r"^\s*-\s*(.+)", line)
            if m:
                val = m.group(1).strip().strip('"').strip("'")
                if "." in val or "/" in val:
                    if any(val.endswith(x) for x in (".pdf", ".txt", ".docx")):
                        cfg["drafts"].append(val)
                    else:
                        cfg["corpora"].append(val)
            m2 = re.match(r"^\s*(\w+):\s*([0-9.]+)", line)
            if m2:
                cfg["thresholds"][m2.group(1)] = float(m2.group(2))
        return cfg


def _cell_key(draft: str, corpus: str) -> str:
    return f"{Path(draft).stem}__{corpus}"


def _print_table(rows: list[dict]) -> None:
    if not rows:
        print("[eval] No results.")
        return
    header = f"{'Draft':<30} {'Corpus':<15} {'Overall':>8} {'Halluc':>7} {'Worst dim':<22} {'Score':>6}"
    print("\n" + "=" * len(header))
    print(header)
    print("-" * len(header))
    for r in rows:
        worst_dim = min(r.get("dims", {}).items(), key=lambda kv: kv[1].get("score", 10), default=("?", {"score": "?"}))
        print(
            f"{r['draft_stem']:<30} {r['corpus']:<15} {r['overall']:>8.2f} "
            f"{len(r.get('hallucinations', [])):>7} {worst_dim[0]:<22} {worst_dim[1].get('score','?'):>6}"
        )
    print("=" * len(header))


def _history_best_by_cell(history: list[dict]) -> dict[str, tuple[float, str]]:
    """Best previously recorded overall per cell, with the run that produced it.

    Uses the best (not merely the most recent) so that drift spread over several
    runs is still caught: three consecutive -0.3 steps sum to -0.9 and fail a
    max_mean_drop of 0.5, where a last-run-only comparison would pass every step.
    """
    best: dict[str, tuple[float, str]] = {}
    for record in history:
        if not isinstance(record, dict):
            continue
        run_id = str(record.get("run_id") or record.get("generated_at") or "?")
        for cell in record.get("cells") or []:
            if not isinstance(cell, dict):
                continue
            overall = cell.get("overall")
            if not isinstance(overall, (int, float)):
                continue
            key = cell.get("cell_key")
            if not key:
                if not cell.get("draft_stem"):
                    continue
                key = _cell_key(str(cell["draft_stem"]), str(cell.get("corpus")))
            key = str(key)
            if key not in best or float(overall) > best[key][0]:
                best[key] = (float(overall), run_id)
    return best


def _regression_check(current_rows: list[dict], history: list[dict], thresholds: dict) -> list[str]:
    failures = []
    min_overall = thresholds.get("min_overall", 0.0)
    min_dim_score = thresholds.get("min_dim_score", 0.0)
    max_mean_drop = thresholds.get("max_mean_drop", 0.5)

    # Mean overall gate
    scored = [r for r in current_rows if r.get("overall") is not None]
    if scored and min_overall > 0.0:
        mean_overall = sum(r["overall"] for r in scored) / len(scored)
        if mean_overall < min_overall:
            failures.append(f"MEAN_OVERALL: {mean_overall:.2f} < {min_overall} threshold")

    # Per-dimension mean gate
    if min_dim_score > 0.0 and scored:
        dim_totals: dict[str, list[float]] = {}
        for r in scored:
            for dim, dval in (r.get("dims") or {}).items():
                score = dval.get("score") if isinstance(dval, dict) else None
                if isinstance(score, (int, float)):
                    dim_totals.setdefault(dim, []).append(float(score))
        for dim, scores in dim_totals.items():
            mean_dim = sum(scores) / len(scores)
            if mean_dim < min_dim_score:
                failures.append(f"DIM_SCORE: dim '{dim}' mean {mean_dim:.2f} < {min_dim_score}")

    # Per-cell hallucination and absolute threshold
    for r in current_rows:
        if r.get("overall") is not None and r["overall"] < min_overall:
            failures.append(f"THRESHOLD: {r['draft_stem']} overall {r['overall']:.2f} < {min_overall}")
        if r.get("hallucinations"):
            failures.append(f"HALLUCINATION: {r['draft_stem']}/{r['corpus']}: {r['hallucinations']}")

    # Regression vs the best score ever recorded for that cell, across all history.
    best_map = _history_best_by_cell(history)
    for r in current_rows:
        if r.get("overall") is None:
            continue
        key = _cell_key(r["draft_stem"], r["corpus"])
        if key not in best_map:
            continue
        best_overall, run_id = best_map[key]
        drop = best_overall - r["overall"]
        if drop > max_mean_drop:
            failures.append(
                f"REGRESSION: {key} dropped {drop:.2f} "
                f"(best {best_overall:.2f} in run {run_id}, now {r['overall']:.2f})"
            )

    return failures


def _high_severity_finding_keys(export_path: str | None) -> frozenset[str]:
    """Return a frozenset of 'type::problem_hash' for critical/major findings in the export."""
    if not export_path:
        return frozenset()
    try:
        import hashlib
        data = json.loads(Path(export_path).read_text())
        keys: set[str] = set()
        for source in ("diagnostic_findings", "revision_tasks"):
            for f in (data.get(source) or []):
                sev = f.get("severity") or f.get("priority") or ""
                if sev not in ("critical", "major", "high"):
                    continue
                ftype = f.get("finding_type") or f.get("task_type") or f.get("type") or ""
                problem = f.get("problem") or f.get("description") or f.get("title") or ""
                digest = hashlib.md5(problem[:200].encode()).hexdigest()[:8]
                keys.add(f"{ftype}::{digest}")
        return frozenset(keys)
    except Exception:
        return frozenset()


def _check_finding_stability(cell_results: list[dict], best: dict) -> None:
    """Assert high-severity findings are identical across all stability runs."""
    finding_sets = [
        _high_severity_finding_keys(r.get("export"))
        for r in cell_results
    ]
    non_empty = [s for s in finding_sets if s]
    if len(non_empty) < 2:
        return  # nothing to compare
    reference = non_empty[0]
    mismatches = [s for s in non_empty[1:] if s != reference]
    if mismatches:
        print(f"[eval] STABILITY FAIL: high-severity findings differ across runs")
        for i, s in enumerate(non_empty):
            only_in_ref = reference - s
            only_in_run = s - reference
            if only_in_ref or only_in_run:
                print(f"  run {i+1}: missing={only_in_ref} extra={only_in_run}")
        best["stability_finding_fail"] = True
    else:
        print(f"[eval] Stability findings: identical across {len(non_empty)} runs ✓")


def run_cell(draft_path: Path, corpus_name: str | None, gold_dir: Path) -> dict | None:
    from scripts.eval.run_harness import run as harness_run
    from scripts.eval.judge import score as judge_score

    corpus_label = corpus_name or "no-corpus"
    stem = draft_path.stem

    # Find gold
    gold_path = gold_dir / f"{stem}.gold.md"
    has_gold = gold_path.exists()

    print(f"\n[eval] Running: {stem} × {corpus_label}")
    try:
        export_path = harness_run(draft_path, corpus_name)
    except Exception as e:
        print(f"[eval] HARNESS FAILED for {stem}/{corpus_label}: {e}")
        return {"draft_stem": stem, "corpus": corpus_label, "overall": 0.0, "dims": {}, "hallucinations": [], "error": str(e)}

    if not has_gold:
        print(f"[eval] No gold file at {gold_path} — skipping judge, export only")
        return {"draft_stem": stem, "corpus": corpus_label, "overall": None, "dims": {}, "hallucinations": [], "export": str(export_path), "no_gold": True}

    try:
        result = judge_score(export_path, gold_path)
        result["draft_stem"] = stem
        result["corpus"] = corpus_label
        result["export"] = str(export_path)
        return result
    except Exception as e:
        print(f"[eval] JUDGE FAILED for {stem}/{corpus_label}: {e}")
        return {"draft_stem": stem, "corpus": corpus_label, "overall": 0.0, "dims": {}, "hallucinations": [], "error": str(e)}


def run_openreview_eval(args: argparse.Namespace) -> int:
    from scripts.eval.atomize_reviews import atomize_paper
    from scripts.eval.fetch_openreview import fetch_venue
    from scripts.eval.judge_openreview import aggregate, extract_noesis_items, paper_field, score_paper
    from scripts.eval.match import match
    from scripts.eval.run_harness import run as harness_run

    RESULTS_DIR.mkdir(exist_ok=True)
    openreview_dir = EVAL_DIR / "openreview"
    venue_slug = args.venue.replace("/", "_")
    gold_dir = openreview_dir / venue_slug
    field_map = _load_json_map(args.field_map) if args.field_map else {}

    gold_paths = sorted(gold_dir.glob("*.json")) if gold_dir.exists() else []
    if len(gold_paths) < args.limit:
        print(f"[eval-openreview] Fetching gold: venue={args.venue} limit={args.limit}")
        fetch_venue(args.venue, args.limit, openreview_dir)
        gold_paths = sorted(gold_dir.glob("*.json"))
    if not gold_paths:
        print("[eval-openreview] No OpenReview gold files available.")
        return 1

    if args.paper_ids:
        requested = [paper_id.strip() for paper_id in args.paper_ids.split(",") if paper_id.strip()]
        by_id = {path.stem: path for path in gold_paths}
        missing = [paper_id for paper_id in requested if paper_id not in by_id]
        if missing:
            available = ", ".join(sorted(by_id)[:20])
            print(
                "[eval-openreview] Unknown --paper-ids: "
                f"{', '.join(missing)}. Available examples: {available}"
            )
            return 1
        gold_paths = [by_id[paper_id] for paper_id in requested]
        print(f"[eval-openreview] --paper-ids: selected {len(gold_paths)} papers")
    else:
        gold_paths = gold_paths[:args.limit]

    rows: list[dict] = []
    for gold_path in gold_paths:
        gold = json.loads(gold_path.read_text())
        review_units = atomize_paper(gold)
        gold["review_units"] = review_units
        draft_path = EVAL_DIR / str(gold["pdf_path"])
        print(f"[eval-openreview] Running pipeline for {gold['paper_id']}: {draft_path}")
        export_path = harness_run(draft_path, None)
        export = json.loads(export_path.read_text())
        noesis_items = extract_noesis_items(export)
        matches = match(noesis_items, review_units)
        row = score_paper(export_path, gold, matches)
        row["field"] = paper_field(gold, field_map)
        row["export"] = str(export_path)
        row["gold"] = str(gold_path)
        rows.append(row)

    scoreboard = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "venue": args.venue,
        "limit": args.limit,
        "pipeline_version": _pipeline_version(),
        "aggregate": aggregate(rows),
        "rows": rows,
    }
    scoreboard_path = RESULTS_DIR / "openreview_scoreboard.json"
    scoreboard_path.write_text(json.dumps(scoreboard, indent=2, default=str) + "\n")

    record = {
        "run_id": uuid.uuid4().hex,
        "generated_at": scoreboard["generated_at"],
        "pipeline_version": scoreboard["pipeline_version"],
        "config": {"venue": args.venue, "limit": args.limit, "paper_ids": args.paper_ids},
        "aggregates": scoreboard["aggregate"],
        "cells": [
            {
                "cell_key": str(row.get("paper_id")),
                "paper_id": row.get("paper_id"),
                "field": row.get("field"),
                "weakness_recall": row.get("weakness_recall"),
                "precision_vs_gold": row.get("precision_vs_gold"),
                "groundedness": row.get("groundedness"),
                "llm_relevance_rate": row.get("llm_relevance_rate"),
                "ungrounded_rate": row.get("ungrounded_rate"),
                "hallucinations": len(row.get("hallucinations") or []),
            }
            for row in rows
        ],
    }
    append_history(record, OPENREVIEW_HISTORY_PATH)

    print(f"[eval-openreview] Scoreboard: {scoreboard_path}")
    print(f"[eval-openreview] History (append-only): {OPENREVIEW_HISTORY_PATH}  run_id={record['run_id']}")
    print(json.dumps(scoreboard["aggregate"], indent=2, sort_keys=True))
    return 0


def _load_json_map(path: str | Path) -> dict[str, str]:
    raw = json.loads(Path(path).read_text())
    if isinstance(raw, dict) and all(isinstance(value, str) for value in raw.values()):
        return {str(key): value for key, value in raw.items()}
    if isinstance(raw, dict) and isinstance(raw.get("papers"), list):
        mapping: dict[str, str] = {}
        for paper in raw["papers"]:
            if not isinstance(paper, dict):
                continue
            field = paper.get("field")
            if not isinstance(field, str) or not field.strip():
                continue
            for key in ("paper_id", "title"):
                value = paper.get(key)
                if isinstance(value, str) and value.strip():
                    mapping[value] = field.strip()
        return mapping
    raise ValueError(f"Unsupported field map shape: {path}")


def main(args: argparse.Namespace) -> int:
    if args.openreview:
        return run_openreview_eval(args)

    RESULTS_DIR.mkdir(exist_ok=True)
    cfg = _load_config()

    drafts_cfg: list[str] = cfg.get("drafts", [])
    corpora_cfg: list[str] = cfg.get("corpora", [None])  # type: ignore[arg-type]
    thresholds: dict = cfg.get("thresholds", {})

    if not drafts_cfg:
        print("[eval] No drafts in config.yaml — add at least one draft path.")
        return 1

    if args.quick:
        drafts_cfg = drafts_cfg[:3]
        print(f"[eval] --quick: limiting to {len(drafts_cfg)} drafts")

    gold_dir = EVAL_DIR / "gold"

    # Full history for regression check (not just the immediately previous run).
    scoreboard_path = RESULTS_DIR / "scoreboard.json"
    history = load_history(HISTORY_PATH)
    if history:
        print(f"[eval] History: {len(history)} prior run(s) in {HISTORY_PATH.name}")

    rows: list[dict] = []

    auto_corpus: bool = cfg.get("auto_corpus", False)

    for draft_str in drafts_cfg:
        draft_path = (REPO_ROOT / draft_str).resolve()
        if not draft_path.exists():
            print(f"[eval] Draft not found, skipping: {draft_path}")
            continue

        # auto_corpus: use <draft_stem> corpus if dir exists, otherwise no-corpus
        if auto_corpus:
            own_corpus = draft_path.stem
            own_corpus_dir = EVAL_DIR / "corpora" / own_corpus
            corpora_for_draft = [own_corpus] if own_corpus_dir.exists() and list(own_corpus_dir.glob("*.pdf")) else [None]
        else:
            corpora_for_draft = corpora_cfg

        for corpus in corpora_for_draft:
            if args.stability and args.stability > 1:
                cell_results = []
                for run_i in range(args.stability):
                    print(f"[eval] Stability run {run_i+1}/{args.stability}")
                    r = run_cell(draft_path, corpus, gold_dir)
                    if r:
                        cell_results.append(r)
                if cell_results:
                    overalls = [r["overall"] for r in cell_results if r.get("overall") is not None]
                    variance = (max(overalls) - min(overalls)) if len(overalls) > 1 else 0.0
                    best = max(cell_results, key=lambda r: r.get("overall") or 0)
                    best["stability_variance"] = variance
                    best["stability_runs"] = len(cell_results)
                    print(f"[eval] Stability variance: {variance:.2f} across {len(cell_results)} runs")
                    if variance > 0.5:
                        print(f"[eval] STABILITY FAIL: variance {variance:.2f} exceeds 0.5")
                        best["stability_fail"] = f"variance {variance:.2f} > 0.5"

                    # Check identical high-severity findings across all runs
                    _check_finding_stability(cell_results, best)

                    rows.append(best)
            else:
                r = run_cell(draft_path, corpus, gold_dir)
                if r:
                    rows.append(r)

    # Write scoreboard
    scored_rows = [r for r in rows if r.get("overall") is not None]
    mean_overall = sum(r["overall"] for r in scored_rows) / len(scored_rows) if scored_rows else 0.0
    total_hallucinations = sum(len(r.get("hallucinations") or []) for r in scored_rows)

    scoreboard = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mean_overall": round(mean_overall, 2),
        "total_hallucinations": total_hallucinations,
        "total_cells": len(rows),
        "scored_cells": len(scored_rows),
        "rows": rows,
        "thresholds": thresholds,
    }
    scoreboard["pipeline_version"] = _pipeline_version()
    scoreboard_path.write_text(json.dumps(scoreboard, indent=2, default=str))

    # Append-only history. Written BEFORE the gate so a failing run is still recorded.
    record = build_history_record(rows, cfg, mean_overall, total_hallucinations, args=args)
    append_history(record, HISTORY_PATH)

    _print_table(scored_rows)
    print(f"\n[eval] Mean overall: {mean_overall:.2f}/10   Hallucinations: {total_hallucinations}")
    print(f"[eval] Scoreboard: {scoreboard_path}")
    print(f"[eval] History (append-only): {HISTORY_PATH}  run_id={record['run_id']}")

    # Stability failures
    stability_failures = [
        r for r in rows
        if r.get("stability_fail") or r.get("stability_finding_fail")
    ]
    if stability_failures:
        print("\n[eval] STABILITY GATE FAILURES:")
        for r in stability_failures:
            print(f"  ✗ {r['draft_stem']}/{r['corpus']}: {r.get('stability_fail', '')} finding_mismatch={r.get('stability_finding_fail', False)}")

    # Regression gate
    failures = _regression_check(scored_rows, history, thresholds)
    if failures:
        print("\n[eval] REGRESSION GATE FAILURES:")
        for f in failures:
            print(f"  ✗ {f}")

    all_failures = stability_failures or failures
    if all_failures:
        return 1

    print("[eval] ✓ All checks passed")
    return 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Noesis eval loop")
    p.add_argument("--quick", action="store_true", help="Run only first 3 drafts from config")
    p.add_argument("--stability", type=int, default=None, metavar="N", help="Run each cell N times to check variance")
    p.add_argument("--openreview", action="store_true", help="Run OpenReview human-review eval")
    p.add_argument("--venue", default="ICLR.cc/2024/Conference", help="OpenReview venue id")
    p.add_argument("--limit", type=int, default=15, help="OpenReview paper limit")
    p.add_argument("--paper-ids", default=None, help="Comma-separated OpenReview paper ids to eval")
    p.add_argument("--field-map", default=None, help="Optional JSON map from OpenReview paper_id/title to field")
    return p.parse_args()


if __name__ == "__main__":
    sys.exit(main(parse_args()))

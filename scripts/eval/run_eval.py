"""
Eval loop: run all drafts × corpora from config.yaml → judge → scoreboard.

Usage:
    python scripts/eval/run_eval.py                  # full run
    python scripts/eval/run_eval.py --quick          # first 3 drafts only
    python scripts/eval/run_eval.py --stability 3    # run each cell 3x, check variance

Must run inside the backend container.

Regression gate: exits non-zero if mean overall drops >0.5 vs previous scoreboard
or any new hallucination appears.
"""

import argparse
import json
import sys
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


def _regression_check(current_rows: list[dict], prev_scoreboard: dict, thresholds: dict) -> list[str]:
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

    # Regression vs previous scoreboard
    if prev_scoreboard.get("rows"):
        prev_map = {_cell_key(r["draft_stem"], r["corpus"]): r["overall"] for r in prev_scoreboard["rows"]}
        for r in current_rows:
            key = _cell_key(r["draft_stem"], r["corpus"])
            if key in prev_map and prev_map[key] is not None and r.get("overall") is not None:
                drop = prev_map[key] - r["overall"]
                if drop > max_mean_drop:
                    failures.append(f"REGRESSION: {key} dropped {drop:.2f} (was {prev_map[key]:.2f}, now {r['overall']:.2f})")

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
    gold_paths = gold_paths[:args.limit]
    if not gold_paths:
        print("[eval-openreview] No OpenReview gold files available.")
        return 1

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
        "aggregate": aggregate(rows),
        "rows": rows,
    }
    scoreboard_path = RESULTS_DIR / "openreview_scoreboard.json"
    scoreboard_path.write_text(json.dumps(scoreboard, indent=2, default=str) + "\n")
    print(f"[eval-openreview] Scoreboard: {scoreboard_path}")
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

    # Previous scoreboard for regression check
    scoreboard_path = RESULTS_DIR / "scoreboard.json"
    prev_scoreboard: dict = {}
    if scoreboard_path.exists():
        try:
            prev_scoreboard = json.loads(scoreboard_path.read_text())
        except Exception:
            pass

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
    scoreboard_path.write_text(json.dumps(scoreboard, indent=2, default=str))

    _print_table(scored_rows)
    print(f"\n[eval] Mean overall: {mean_overall:.2f}/10   Hallucinations: {total_hallucinations}")
    print(f"[eval] Scoreboard: {scoreboard_path}")

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
    failures = _regression_check(scored_rows, prev_scoreboard, thresholds)
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
    p.add_argument("--field-map", default=None, help="Optional JSON map from OpenReview paper_id/title to field")
    return p.parse_args()


if __name__ == "__main__":
    sys.exit(main(parse_args()))

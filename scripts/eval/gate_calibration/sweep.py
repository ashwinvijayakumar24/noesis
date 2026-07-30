#!/usr/bin/env python3
"""Threshold sweep for the draft publish gate.

Joins human labels (``labels.jsonl``) to the run exports, then measures how well
each candidate predictor separates degraded runs from acceptable ones, and where
the two a-priori thresholds actually sit on that curve.

The gate ships with ``PARSER_QUALITY_MIN = 0.55`` and
``PDF_PAGE_ANCHOR_COVERAGE_MIN = 0.75``, both chosen without labelled data. There
is also ``verbatim_anchor_coverage``, computed on every run and compared against
no threshold at all; it is swept here as a third candidate.

Orientation note. The gate's predictors are "higher is better" — it fails a run
when the value falls *below* a threshold. ``metrics.py`` assumes "higher means
more likely positive", so every predictor is negated before it goes in, and the
thresholds are negated with it. One consequence: the sweep's decision rule is
``value <= t`` where the gate's is ``value < t``. They differ only on exact ties
at the threshold, which is called out in the report when it bites.

Usage::

    python3 sweep.py                       # symmetric costs
    python3 sweep.py --fn-cost 4           # shipping a bad critique 4x worse
    python3 sweep.py --labels /tmp/l.jsonl --results-dir /tmp/exports
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np

try:  # script or module
    from . import metrics as M
    from .label_cli import DEFAULT_LABELS_PATH, DEFAULT_RESULTS_DIR, iter_exports, latest_labels
except ImportError:  # pragma: no cover - direct `python3 sweep.py`
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from gate_calibration import metrics as M
    from gate_calibration.label_cli import (
        DEFAULT_LABELS_PATH,
        DEFAULT_RESULTS_DIR,
        iter_exports,
        latest_labels,
    )

PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_SWEEP_OUT = PACKAGE_DIR / "sweep_results.jsonl"

# Predictor key -> (human name, the gate's a-priori threshold or None)
PREDICTORS: dict[str, tuple[str, float | None]] = {
    "parser_quality_score": ("parser quality", 0.55),
    "page_anchor_coverage": ("page-anchor coverage", 0.75),
    "verbatim_anchor_coverage": ("verbatim-anchor coverage", None),
}

MIN_LABELS_FOR_AUC = 10
MIN_LABELS_FOR_CONFIDENCE = 30


# --------------------------------------------------------------------------
# join
# --------------------------------------------------------------------------


def build_dataset(results_dir: Path, labels_path: Path) -> dict[str, Any]:
    """Join labels to exports.

    Returns ``{"rows": [...], "unsure": n, "unmatched": [...], "n_exports": n}``.
    Each row carries ``run_id``, ``y`` (1 = degraded), and the raw predictor
    values (possibly None).
    """
    labels = latest_labels(labels_path)
    rows: list[dict[str, Any]] = []
    unsure = 0
    n_exports = 0
    seen: set[str] = set()

    for rec in iter_exports(results_dir, verbose=False):
        n_exports += 1
        lab = labels.get(rec["run_id"])
        if lab is None:
            continue
        seen.add(rec["run_id"])
        if lab["label"] == "unsure":
            unsure += 1
            continue
        h = rec["_hidden"]
        rows.append(
            {
                "run_id": rec["run_id"],
                "y": 1 if lab["label"] == "degraded" else 0,
                "labeller": lab.get("labeller"),
                "gate_status": h.get("gate_status"),
                "gate_publishable": h.get("publishable"),
                **{k: h.get(k) for k in PREDICTORS},
            }
        )

    unmatched = sorted(set(labels) - seen)
    return {"rows": rows, "unsure": unsure, "unmatched": unmatched, "n_exports": n_exports}


def _vectors(rows: list[dict], key: str) -> tuple[np.ndarray, np.ndarray, int]:
    """``(y, negated_values, n_dropped)`` for rows where the predictor is present."""
    y, v = [], []
    dropped = 0
    for r in rows:
        val = r.get(key)
        if val is None:
            dropped += 1
            continue
        y.append(r["y"])
        v.append(-float(val))  # negate: low value => high degradation score
    return np.asarray(y, dtype=float), np.asarray(v, dtype=float), dropped


# --------------------------------------------------------------------------
# single-predictor sweep
# --------------------------------------------------------------------------


def sweep_predictor(
    rows: list[dict], key: str, fp_cost: float, fn_cost: float, seed: int = 0
) -> dict[str, Any]:
    y, s, dropped = _vectors(rows, key)
    name, apriori = PREDICTORS[key]
    out: dict[str, Any] = {
        "predictor": key,
        "name": name,
        "apriori_threshold": apriori,
        "n": int(y.size),
        "n_missing": dropped,
        "n_positive": int(np.sum(y == 1)) if y.size else 0,
        "distinct_values": int(np.unique(-s).size) if s.size else 0,
    }
    if y.size == 0:
        out["error"] = "no rows with this predictor present"
        return out
    if out["n_positive"] == 0:
        out["error"] = "no degraded labels — precision/recall undefined"
        return out
    if out["distinct_values"] < 2:
        out["error"] = (
            f"zero variance: every run has {key}={-s[0]:.4g}. "
            "A constant cannot separate anything; this predictor is uninformative "
            "on the current corpus regardless of threshold."
        )
        return out

    out["auc_pr"] = M.auc_pr(y, s)
    out["base_rate"] = M.base_rate(y)
    out["lift_over_base_rate"] = (
        out["auc_pr"] / out["base_rate"] if out["base_rate"] else float("nan")
    )
    if y.size >= MIN_LABELS_FOR_AUC:
        out["auc_pr_ci"] = M.bootstrap_ci(y, s, M.auc_pr, seed=seed)

    # Every achievable operating point, reported in original (un-negated) units.
    # The extra threshold above max(s) is the "never fire" point — a gate set so
    # loose it withholds nothing. Without it in the table the cost-optimal search
    # cannot choose "don't gate at all", and can end up reporting an operating
    # point that costs more than the a-priori one.
    table = []
    for t in list(sorted(np.unique(s))) + [float(np.max(s)) + 1.0]:
        pm = M.point_metrics(y, s, float(t))
        pm["value_threshold"] = float(-t)  # "fail the run when value <= this"
        pm["cost"] = M.expected_cost(y, s, float(t), fp_cost, fn_cost)
        table.append(pm)
    out["operating_points"] = table

    valid_f1 = [p for p in table if not math.isnan(p["f1"])]
    if valid_f1:
        out["best_f1"] = max(valid_f1, key=lambda p: p["f1"])
    out["best_cost"] = min(table, key=lambda p: p["cost"])

    if apriori is not None:
        out["at_apriori"] = _evaluate_at_value(y, s, apriori, fp_cost, fn_cost)
        if out.get("best_cost"):
            out["cost_gap_vs_apriori"] = out["at_apriori"]["cost"] - out["best_cost"]["cost"]
    return out


def _evaluate_at_value(
    y: np.ndarray, s: np.ndarray, value_threshold: float, fp_cost: float, fn_cost: float
) -> dict[str, Any]:
    """Metrics for the rule 'fail when value < value_threshold'.

    In negated space that is ``score > -value_threshold``. metrics.py uses ``>=``,
    so nudge the threshold by a hair to keep the strict inequality faithful.
    """
    t = -value_threshold + 1e-12
    pm = M.point_metrics(y, s, t)
    pm["value_threshold"] = float(value_threshold)
    pm["cost"] = M.expected_cost(y, s, t, fp_cost, fn_cost)
    return pm


# --------------------------------------------------------------------------
# joint sweep (the gate's actual OR semantics)
# --------------------------------------------------------------------------


def sweep_joint(
    rows: list[dict], fp_cost: float, fn_cost: float, max_grid: int = 40
) -> dict[str, Any]:
    """Grid over (parser threshold, page-anchor threshold) with the gate's OR rule.

    The live gate fails a run when parser quality is low **or** page-anchor
    coverage is low, so the joint sweep must use the same composition — sweeping
    them independently would understate the false-positive rate of the pair.
    """
    usable = [
        r
        for r in rows
        if r.get("parser_quality_score") is not None and r.get("page_anchor_coverage") is not None
    ]
    out: dict[str, Any] = {"n": len(usable), "n_dropped": len(rows) - len(usable)}
    if not usable:
        out["error"] = "no rows with both predictors present"
        return out

    y = np.asarray([r["y"] for r in usable], dtype=float)
    pq = np.asarray([float(r["parser_quality_score"]) for r in usable])
    pac = np.asarray([float(r["page_anchor_coverage"]) for r in usable])
    if int(np.sum(y == 1)) == 0:
        out["error"] = "no degraded labels"
        return out

    def grid(vals: np.ndarray) -> np.ndarray:
        u = np.unique(vals)
        if u.size <= max_grid:
            return u
        return np.quantile(u, np.linspace(0, 1, max_grid))

    cells = []
    for t_pq in grid(pq):
        for t_pac in grid(pac):
            pred = (pq < t_pq) | (pac < t_pac)
            tp = int(np.sum(pred & (y == 1)))
            fp = int(np.sum(pred & (y == 0)))
            tn = int(np.sum(~pred & (y == 0)))
            fn = int(np.sum(~pred & (y == 1)))
            p = tp / (tp + fp) if tp + fp else float("nan")
            r = tp / (tp + fn) if tp + fn else float("nan")
            f = (
                0.0
                if (not math.isnan(p) and not math.isnan(r) and p + r == 0)
                else (2 * p * r / (p + r) if not (math.isnan(p) or math.isnan(r)) else float("nan"))
            )
            cells.append(
                {
                    "parser_threshold": float(t_pq),
                    "page_anchor_threshold": float(t_pac),
                    "tp": tp, "fp": fp, "tn": tn, "fn": fn,
                    "precision": p, "recall": r, "f1": f,
                    "cost": float(fp_cost * fp + fn_cost * fn),
                }
            )

    out["n_cells"] = len(cells)
    valid = [c for c in cells if not math.isnan(c["f1"])]
    if valid:
        out["best_f1"] = max(valid, key=lambda c: c["f1"])
    out["best_cost"] = min(cells, key=lambda c: c["cost"])
    out["at_apriori"] = next(
        (
            c
            for c in cells
            if abs(c["parser_threshold"] - 0.55) < 1e-9
            and abs(c["page_anchor_threshold"] - 0.75) < 1e-9
        ),
        None,
    )
    if out["at_apriori"] is None:
        pred = (pq < 0.55) | (pac < 0.75)
        tp = int(np.sum(pred & (y == 1)))
        fp = int(np.sum(pred & (y == 0)))
        tn = int(np.sum(~pred & (y == 0)))
        fn = int(np.sum(~pred & (y == 1)))
        out["at_apriori"] = {
            "parser_threshold": 0.55,
            "page_anchor_threshold": 0.75,
            "tp": tp, "fp": fp, "tn": tn, "fn": fn,
            "precision": tp / (tp + fp) if tp + fp else float("nan"),
            "recall": tp / (tp + fn) if tp + fn else float("nan"),
            "cost": float(fp_cost * fp + fn_cost * fn),
            "note": "off-grid; computed directly",
        }
    return out


# --------------------------------------------------------------------------
# gate-as-shipped
# --------------------------------------------------------------------------


def evaluate_gate_as_shipped(rows: list[dict], fp_cost: float, fn_cost: float) -> dict[str, Any]:
    """Score the gate's own recorded verdict against the labels.

    This is the number that matters: not "could a threshold work" but "does the
    thing currently in production agree with a human".
    """
    usable = [r for r in rows if r.get("gate_publishable") is not None]
    if not usable:
        return {"error": "no rows carry a recorded gate verdict"}
    y = np.asarray([r["y"] for r in usable], dtype=float)
    pred = np.asarray([0.0 if r["gate_publishable"] else 1.0 for r in usable])
    return {
        "n": len(usable),
        **M.point_metrics(y, pred, 0.5),
        "cost": M.expected_cost(y, pred, 0.5, fp_cost, fn_cost),
    }


# --------------------------------------------------------------------------
# calibration of the predictors read as probabilities
# --------------------------------------------------------------------------


def calibration_block(rows: list[dict], key: str) -> dict[str, Any]:
    """ECE / Brier for ``1 - value`` read as P(degraded). Diagnostic, not a claim."""
    y, s, _ = _vectors(rows, key)
    if y.size == 0:
        return {"error": "no data"}
    probs = np.clip(1.0 + s, 0.0, 1.0)  # s == -value, so 1 + s == 1 - value
    return {
        "n": int(y.size),
        "ece": M.expected_calibration_error(y, probs, n_bins=10),
        "brier": M.brier_score(y, probs),
        "reliability": M.reliability_diagram(y, probs, n_bins=10),
    }


# --------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------


def _fmt(x, nd=4):
    if x is None:
        return "n/a"
    if isinstance(x, float) and math.isnan(x):
        return "undef"
    if isinstance(x, float):
        return f"{x:.{nd}f}"
    return str(x)


def render_report(result: dict[str, Any]) -> str:
    L: list[str] = []
    ds = result["dataset"]
    L.append("=" * 92)
    L.append("PUBLISH-GATE THRESHOLD CALIBRATION")
    L.append("=" * 92)
    L.append(f"exports scanned      : {ds['n_exports']}")
    L.append(f"labelled & scoreable : {ds['n_scoreable']}  (degraded={ds['n_degraded']}, ok={ds['n_ok']})")
    L.append(f"labelled 'unsure'    : {ds['unsure']}  (excluded)")
    L.append(f"degraded base rate   : {_fmt(ds['base_rate'])}")
    L.append(f"error costs          : FP={result['fp_cost']}  FN={result['fn_cost']}")
    if ds["unmatched"]:
        L.append(f"labels with no export: {len(ds['unmatched'])}")
    for w in result["warnings"]:
        L.append(f"!! {w}")
    L.append("")

    L.append("-" * 92)
    L.append("GATE AS SHIPPED (recorded publish_gate verdict vs human label)")
    g = result["gate_as_shipped"]
    if "error" in g:
        L.append(f"  {g['error']}")
    else:
        L.append(
            f"  n={g['n']}  precision={_fmt(g['precision'])}  recall={_fmt(g['recall'])}  "
            f"f1={_fmt(g['f1'])}"
        )
        L.append(
            f"  tp={int(g['tp'])} fp={int(g['fp'])} tn={int(g['tn'])} fn={int(g['fn'])}  "
            f"fp_rate={_fmt(g['fp_rate'])} fn_rate={_fmt(g['fn_rate'])} cost={_fmt(g['cost'],2)}"
        )
    L.append("")

    L.append("-" * 92)
    L.append("PREDICTOR COMPARISON BY AUC-PR (PR not ROC: degraded is the rare class)")
    for key, r in result["predictors"].items():
        if "error" in r:
            L.append(f"  {r['name']:<26} SKIPPED — {r['error']}")
            continue
        if r.get("auc_withheld"):
            L.append(f"  {r['name']:<26} AUC-PR WITHHELD — {r['auc_withheld']}")
            continue
        ci = r.get("auc_pr_ci")
        ci_s = f"  95% CI [{_fmt(ci['lo'],3)}, {_fmt(ci['hi'],3)}]" if ci else "  (CI withheld: too few labels)"
        L.append(
            f"  {r['name']:<26} AUC-PR={_fmt(r['auc_pr'])}  base={_fmt(r['base_rate'],3)}  "
            f"lift={_fmt(r['lift_over_base_rate'],2)}x{ci_s}"
        )
    L.append("")

    for key, r in result["predictors"].items():
        L.append("-" * 92)
        L.append(f"{r['name'].upper()}  ({key})")
        if "error" in r:
            L.append(f"  {r['error']}")
            L.append("")
            continue
        L.append(f"  n={r['n']} (missing {r['n_missing']}), distinct values={r['distinct_values']}")
        if r.get("at_apriori"):
            a = r["at_apriori"]
            L.append(
                f"  A-PRIORI THRESHOLD {a['value_threshold']}: "
                f"precision={_fmt(a['precision'])} recall={_fmt(a['recall'])} f1={_fmt(a['f1'])} "
                f"cost={_fmt(a['cost'],2)}  [tp={int(a['tp'])} fp={int(a['fp'])} fn={int(a['fn'])} tn={int(a['tn'])}]"
            )
            if a["tp"] + a["fp"] == 0:
                L.append(
                    "    -> this threshold fires on ZERO runs in the labelled set; it is inert here, "
                    "not validated."
                )
        else:
            L.append("  A-PRIORI THRESHOLD: none — this predictor is computed but never compared.")
        if r.get("best_f1"):
            b = r["best_f1"]
            L.append(
                f"  F1-OPTIMAL   value<{_fmt(b['value_threshold'],4)}: "
                f"precision={_fmt(b['precision'])} recall={_fmt(b['recall'])} f1={_fmt(b['f1'])}"
            )
        c = r["best_cost"]
        where = (
            "DISABLE THE GATE (never fire)"
            if c["tp"] + c["fp"] == 0
            else f"value<{_fmt(c['value_threshold'],4)}"
        )
        L.append(
            f"  COST-OPTIMAL {where} @ FP={result['fp_cost']}/FN={result['fn_cost']}: "
            f"cost={_fmt(c['cost'],2)} precision={_fmt(c['precision'])} recall={_fmt(c['recall'])}"
        )
        if r.get("cost_gap_vs_apriori") is not None:
            L.append(f"  cost left on the table by the a-priori value: {_fmt(r['cost_gap_vs_apriori'],2)}")
        cal = result["calibration"].get(key, {})
        if "error" not in cal:
            L.append(f"  calibration of (1 - value) as P(degraded): ECE={_fmt(cal['ece'])} Brier={_fmt(cal['brier'])}")
        L.append("")

    L.append("-" * 92)
    L.append("JOINT SWEEP (gate semantics: fail when parser < t1 OR page-anchor < t2)")
    j = result["joint"]
    if "error" in j:
        L.append(f"  {j['error']}")
    else:
        L.append(f"  n={j['n']} over {j['n_cells']} grid cells")
        a = j["at_apriori"]
        L.append(
            f"  A-PRIORI (0.55, 0.75): precision={_fmt(a['precision'])} recall={_fmt(a['recall'])} "
            f"cost={_fmt(a['cost'],2)}  [tp={a['tp']} fp={a['fp']} fn={a['fn']} tn={a['tn']}]"
        )
        if j.get("best_f1"):
            b = j["best_f1"]
            L.append(
                f"  F1-OPTIMAL ({_fmt(b['parser_threshold'],3)}, {_fmt(b['page_anchor_threshold'],3)}): "
                f"f1={_fmt(b['f1'])} precision={_fmt(b['precision'])} recall={_fmt(b['recall'])}"
            )
        c = j["best_cost"]
        L.append(
            f"  COST-OPTIMAL ({_fmt(c['parser_threshold'],3)}, {_fmt(c['page_anchor_threshold'],3)}): "
            f"cost={_fmt(c['cost'],2)} precision={_fmt(c['precision'])} recall={_fmt(c['recall'])}"
        )
    L.append("=" * 92)
    return "\n".join(L)


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------


def run_sweep(
    results_dir: Path,
    labels_path: Path,
    fp_cost: float,
    fn_cost: float,
    seed: int = 0,
) -> dict[str, Any]:
    ds = build_dataset(results_dir, labels_path)
    rows = ds["rows"]
    n = len(rows)
    n_deg = sum(r["y"] for r in rows)

    warnings: list[str] = []
    if n == 0:
        warnings.append("NO SCOREABLE LABELS. Run label_cli.py first; everything below is empty.")
    elif n < MIN_LABELS_FOR_AUC:
        warnings.append(
            f"Only {n} scoreable labels (< {MIN_LABELS_FOR_AUC}). AUC-PR is REFUSED — with this "
            "many points the curve is an artefact of which runs happened to get labelled."
        )
    elif n < MIN_LABELS_FOR_CONFIDENCE:
        warnings.append(
            f"Only {n} scoreable labels (< {MIN_LABELS_FOR_CONFIDENCE}). Every number below is "
            "provisional; confidence intervals will be wide and the optimal threshold will move "
            "with the next dozen labels. Do NOT change a production threshold on this."
        )
    if n and n_deg == 0:
        warnings.append("No 'degraded' labels at all — nothing to detect; all metrics undefined.")
    if n and n_deg == n:
        warnings.append("Every label is 'degraded' — no negatives; precision is trivially 1.")

    predictors: dict[str, Any] = {}
    calibration: dict[str, Any] = {}
    for key in PREDICTORS:
        r = sweep_predictor(rows, key, fp_cost, fn_cost, seed=seed) if rows else {
            "predictor": key, "name": PREDICTORS[key][0], "error": "no labelled rows"
        }
        if n < MIN_LABELS_FOR_AUC and "error" not in r:
            # Withhold the AUC only. The confusion counts at a given threshold
            # are still a fact about the labelled runs and worth seeing; it is
            # the ranking summary that is meaningless at this sample size.
            r.pop("auc_pr", None)
            r.pop("auc_pr_ci", None)
            r.pop("lift_over_base_rate", None)
            r["auc_withheld"] = f"only {n} labels (need >= {MIN_LABELS_FOR_AUC})"
        predictors[key] = r
        calibration[key] = calibration_block(rows, key) if rows else {"error": "no labelled rows"}

    return {
        "schema_version": 1,
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "results_dir": str(results_dir),
        "labels_path": str(labels_path),
        "fp_cost": fp_cost,
        "fn_cost": fn_cost,
        "seed": seed,
        "dataset": {
            "n_exports": ds["n_exports"],
            "n_scoreable": n,
            "n_degraded": int(n_deg),
            "n_ok": int(n - n_deg),
            "unsure": ds["unsure"],
            "unmatched": ds["unmatched"],
            "base_rate": (n_deg / n) if n else float("nan"),
        },
        "warnings": warnings,
        "gate_as_shipped": evaluate_gate_as_shipped(rows, fp_cost, fn_cost) if rows else {"error": "no labelled rows"},
        "predictors": predictors,
        "calibration": calibration,
        "joint": sweep_joint(rows, fp_cost, fn_cost) if rows else {"error": "no labelled rows"},
    }


def append_result(out_path: Path, result: dict[str, Any]) -> None:
    """Append one sweep to the results file. Never truncates.

    Append-only on purpose: this repo has already lost eval history once to a
    writer that opened its output with mode 'w'. A sweep is a dated observation,
    not a current-state file.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("a") as fh:
        fh.write(json.dumps(result, default=str) + "\n")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Sweep publish-gate thresholds against human labels.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    p.add_argument("--labels", type=Path, default=DEFAULT_LABELS_PATH)
    p.add_argument("--out", type=Path, default=DEFAULT_SWEEP_OUT, help="append-only JSONL sink")
    p.add_argument(
        "--fp-cost",
        type=float,
        default=1.0,
        help="cost of withholding a good critique (false positive). Default 1.0",
    )
    p.add_argument(
        "--fn-cost",
        type=float,
        default=1.0,
        help="cost of shipping a degraded critique (false negative). Default 1.0; "
        "set > 1 if a bad critique costs more trust than a withheld good one",
    )
    p.add_argument("--seed", type=int, default=0, help="bootstrap seed (determinism)")
    p.add_argument("--json", action="store_true", help="print the raw result instead of the report")
    p.add_argument("--no-write", action="store_true", help="do not append to the results file")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.fp_cost <= 0 or args.fn_cost <= 0:
        print("costs must be positive", file=sys.stderr)
        return 2

    result = run_sweep(
        args.results_dir.expanduser().resolve(),
        args.labels.expanduser().resolve(),
        args.fp_cost,
        args.fn_cost,
        seed=args.seed,
    )
    if not args.no_write:
        append_result(args.out.expanduser().resolve(), result)

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(render_report(result))
        if not args.no_write:
            print(f"\nappended to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

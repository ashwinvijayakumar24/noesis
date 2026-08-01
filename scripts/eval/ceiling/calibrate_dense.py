"""Densify the matcher calibration around the proposed operating point.

``CEILING.md`` §3 proposes moving ``match.COS_THRESHOLD`` from 0.55 to
0.44--0.45 and records why that proposal is thin:

    the ``[0.40, 0.45)`` bin holds 1065 pairs and contributed **1** positive out
    of 20 labelled. That single label carries an estimated weight of 53
    positives, ~18% of all estimated true matches, and it is the entire reason
    recall falls from 1.00 to 0.82 across 0.42->0.44.

This module adds a second, denser stratified draw across ``0.42--0.48`` -- four
sub-bins, 30 new pairs each -- and recomputes the curve over the **union** of
both label sets. CEIL's 146 labels (``pair_labels.json``) are read, never
written; the new labels live in ``hand_labels_dense.json``.

Three things this module does that ``calibrate_matcher.py`` does not
------------------------------------------------------------------
1. **Re-strata.** The union is re-weighted against a finer partition
   (``UNION_BINS``) that splits CEIL's coarse ``[0.40,0.45)`` and
   ``[0.45,0.50)`` bins at the dense edges. Each labelled pair -- from either
   draw -- stands for ``stratum_population / stratum_labelled`` matrix pairs.
   Both draws are uniform within their bin, so both are uniform within any
   sub-bin of it, and pooling them inside a stratum is a simple random sample of
   that stratum (drawn without replacement; the dense draw excludes anything
   CEIL already labelled).
2. **Intervals.** Every precision and recall carries a Wilson score interval at
   95%. Because the estimates are ratio estimators over unequal weights, the
   interval is computed on Kish's effective sample size
   ``n_eff = (sum w)^2 / sum w^2`` rather than the raw count -- a bin whose
   estimate rests on one heavily-weighted label gets the wide interval it
   deserves, which is precisely the failure mode this module exists to expose.
3. **Blind labelling.** ``--emit-sample`` writes the pairs with the producing
   system stripped. Knowing whether the DAG or the agent wrote a finding cannot
   inform whether it expresses a reviewer's concern, and can only bias the
   calibration toward whichever system the labeller favours.

Everything except ``--confirm`` is free and deterministic.
"""

from __future__ import annotations

import argparse
import atexit
import json
import math
import random
import sys
from pathlib import Path

CEILING_DIR = Path(__file__).resolve().parent
if str(CEILING_DIR.parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(CEILING_DIR.parent.parent.parent))

from scripts.eval.ceiling import calibrate_matcher as cm  # noqa: E402

#: CEIL's labels. Read-only -- this module never writes to it.
BASE_LABELS = CEILING_DIR / "pair_labels.json"
#: This module's labels.
DENSE_LABELS = CEILING_DIR / "hand_labels_dense.json"
DENSE_OUT = CEILING_DIR / "sweep_dense.json"

#: The dense draw. Four bins across the span CEIL's single positive decided.
DENSE_BINS = ((0.42, 0.435), (0.435, 0.45), (0.45, 0.465), (0.465, 0.48))
DENSE_PER_BIN = 30
DENSE_SEED = 20260802

#: Strata for the union analysis. CEIL's coarse bins split at the dense edges.
UNION_BINS = (
    (0.00, 0.30),
    (0.30, 0.40),
    (0.40, 0.42),
    (0.42, 0.435),
    (0.435, 0.45),
    (0.45, 0.465),
    (0.465, 0.48),
    (0.48, 0.50),
    (0.50, 0.55),
    (0.55, 0.60),
    (0.60, 0.70),
    (0.70, 1.01),
)

Z95 = 1.959963984540054


def stratum_of(cosine: float) -> str | None:
    """Stratum label, or ``None`` for pairs outside the sampled population.

    A handful of matrix pairs have negative cosine. CEIL's ``BINS`` start at
    0.00 and so never drew from them; they are excluded here too, for exactly
    the same reason it does not matter -- every threshold considered is >= 0.40,
    so those pairs are true negatives under every row of the sweep and enter no
    precision or recall denominator.
    """
    for low, high in UNION_BINS:
        if low <= cosine < high:
            return f"[{low:.3f},{high:.3f})"
    return None


def wilson(successes: float, n_eff: float, z: float = Z95) -> tuple[float, float]:
    """Wilson score interval, tolerant of a fractional (effective) ``n``.

    ``successes`` is ``p_hat * n_eff``; passing the weighted proportion through
    an effective sample size is what keeps a one-label bin from reporting a
    confident number.
    """
    if n_eff <= 0:
        return (float("nan"), float("nan"))
    p = min(max(successes / n_eff, 0.0), 1.0)
    denom = 1 + z * z / n_eff
    centre = (p + z * z / (2 * n_eff)) / denom
    half = z * math.sqrt(p * (1 - p) / n_eff + z * z / (4 * n_eff * n_eff)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def _n_eff(weights: list[float]) -> float:
    """Kish's effective sample size for a weighted ratio estimator."""
    total = sum(weights)
    sq = sum(w * w for w in weights)
    return (total * total / sq) if sq else 0.0


def load_base_labels() -> list[dict]:
    return json.loads(BASE_LABELS.read_text())["pairs"]


def load_dense_labels() -> list[dict]:
    if not DENSE_LABELS.exists():
        return []
    return json.loads(DENSE_LABELS.read_text())["pairs"]


def dense_sample(pairs: list[dict], already: set[tuple[str, str]],
                 per_bin: int = DENSE_PER_BIN, seed: int = DENSE_SEED) -> list[dict]:
    """Stratified draw across ``DENSE_BINS``, excluding pairs already labelled.

    If a bin holds fewer than ``per_bin`` unlabelled candidates the whole bin is
    taken and ``exhausted`` is set -- the bin is never widened to hit a target.
    """
    rng = random.Random(seed)
    out: list[dict] = []
    for low, high in DENSE_BINS:
        bucket = [
            p for p in pairs
            if low <= p["cosine"] < high and (p["finding_id"], p["unit_id"]) not in already
        ]
        bucket.sort(key=lambda p: (p["finding_id"], p["unit_id"]))
        drawn = bucket if len(bucket) <= per_bin else rng.sample(bucket, per_bin)
        drawn.sort(key=lambda p: (p["finding_id"], p["unit_id"]))
        for pair in drawn:
            out.append(
                {
                    "pair_id": f"{pair['finding_id']}~{pair['unit_id']}",
                    "finding_id": pair["finding_id"],
                    "unit_id": pair["unit_id"],
                    "dense_bin": f"[{low:.3f},{high:.3f})",
                    "bin_candidates_unlabelled": len(bucket),
                    "bin_drawn": len(drawn),
                    "exhausted": len(bucket) <= per_bin,
                    "cosine": pair["cosine"],
                    "finding_text": pair["finding_text"],
                    "unit_text": pair["unit_text"],
                }
            )
    return out


def union_labels(base: list[dict], dense: list[dict], cosines: dict[tuple[str, str], float]) -> list[dict]:
    """Merge both label sets and re-weight against ``UNION_BINS``."""
    merged: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for source, rows in (("ceil", base), ("dense", dense)):
        for row in rows:
            key = (row["finding_id"], row["unit_id"])
            if key in seen:
                continue
            seen.add(key)
            merged.append(
                {
                    "finding_id": row["finding_id"],
                    "unit_id": row["unit_id"],
                    "source": source,
                    "label": int(row["label"]),
                    "cosine": cosines[key],
                    "finding_text": row["finding_text"],
                    "unit_text": row["unit_text"],
                }
            )
    return merged


def apply_union_weights(merged: list[dict], pairs: list[dict]) -> list[dict]:
    populations: dict[str, int] = {}
    for pair in pairs:
        stratum = stratum_of(pair["cosine"])
        if stratum is not None:
            populations[stratum] = populations.get(stratum, 0) + 1
    drawn: dict[str, int] = {}
    for row in merged:
        row["stratum"] = stratum_of(row["cosine"])
        drawn[row["stratum"]] = drawn.get(row["stratum"], 0) + 1
    for row in merged:
        row["stratum_population"] = populations[row["stratum"]]
        row["stratum_labelled"] = drawn[row["stratum"]]
        row["weight"] = populations[row["stratum"]] / drawn[row["stratum"]]
    return merged


def sweep_with_intervals(merged: list[dict], thresholds: list[float]) -> list[dict]:
    rows = []
    for threshold in thresholds:
        tp = fp = fn = tn = 0.0
        pred_pos_w: list[float] = []
        pred_pos_hit: list[float] = []
        act_pos_w: list[float] = []
        act_pos_hit: list[float] = []
        for row in merged:
            w = row["weight"]
            predicted = row["cosine"] >= threshold
            actual = bool(row["label"])
            if predicted and actual:
                tp += w
            elif predicted and not actual:
                fp += w
            elif not predicted and actual:
                fn += w
            else:
                tn += w
            if predicted:
                pred_pos_w.append(w)
                pred_pos_hit.append(w if actual else 0.0)
            if actual:
                act_pos_w.append(w)
                act_pos_hit.append(w if predicted else 0.0)

        prec = (sum(pred_pos_hit) / sum(pred_pos_w)) if pred_pos_w else float("nan")
        rec = (sum(act_pos_hit) / sum(act_pos_w)) if act_pos_w else float("nan")
        n_prec = _n_eff(pred_pos_w)
        n_rec = _n_eff(act_pos_w)
        prec_lo, prec_hi = wilson(prec * n_prec, n_prec) if pred_pos_w else (float("nan"),) * 2
        rec_lo, rec_hi = wilson(rec * n_rec, n_rec) if act_pos_w else (float("nan"),) * 2
        f1 = 2 * prec * rec / (prec + rec) if pred_pos_w and act_pos_w and (prec + rec) else 0.0

        rows.append(
            {
                "threshold": round(threshold, 3),
                "precision": None if math.isnan(prec) else round(prec, 4),
                "precision_ci": [None if math.isnan(prec_lo) else round(prec_lo, 4),
                                 None if math.isnan(prec_hi) else round(prec_hi, 4)],
                "recall": None if math.isnan(rec) else round(rec, 4),
                "recall_ci": [None if math.isnan(rec_lo) else round(rec_lo, 4),
                              None if math.isnan(rec_hi) else round(rec_hi, 4)],
                "f1": round(f1, 4),
                "n_labelled_at_or_above": len(pred_pos_w),
                "n_positives_labelled": len(act_pos_w),
                "n_eff_precision": round(n_prec, 2),
                "n_eff_recall": round(n_rec, 2),
                "candidates_est": round(tp + fp, 1),
                "tp": round(tp, 1),
                "fp": round(fp, 1),
                "fn": round(fn, 1),
                "tn": round(tn, 1),
            }
        )
    return rows


def judge_variance(merged: list[dict], n: int = 80, seed: int = DENSE_SEED) -> dict:
    """Judge the same pairs twice against two cold caches, and report the spread.

    The intervals elsewhere in this module cover **sampling** error only. This
    measures the other error term: the ``gpt-5.2`` confirmer at ``temperature=0``
    does not return the same verdict twice. Sampled from the decision band,
    because that is where a flipped verdict changes a unit count.
    """
    import tempfile

    from scripts.eval import match

    rng = random.Random(seed)
    band = [r for r in merged if 0.42 <= r["cosine"] < 0.60]
    subset = band if len(band) <= n else rng.sample(band, n)
    payload = [{"noesis_text": r["finding_text"], "unit_text": r["unit_text"]} for r in subset]

    runs: list[list[int]] = []
    for _ in range(2):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            (cache / "confirm").mkdir()
            results = match._confirm_pairs(payload, cache, None, None, {})
            runs.append([1 if r["confirmed"] else 0 for r in results])
    a, b = runs
    hand = [r["label"] for r in subset]
    return {
        "n": len(a),
        "run_a_positives": sum(a),
        "run_b_positives": sum(b),
        "disagreements": sum(1 for x, y in zip(a, b) if x != y),
        "disagreement_rate": round(sum(1 for x, y in zip(a, b) if x != y) / len(a), 4),
        "kappa_judge_vs_itself": round(cm.cohens_kappa(a, b), 4),
        "kappa_hand_vs_run_a": round(cm.cohens_kappa(hand, a), 4),
        "kappa_hand_vs_run_b": round(cm.cohens_kappa(hand, b), 4),
    }


def _report_spend() -> None:
    try:
        from app.core.llm_budget import total_spend_usd

        print(f"[spend] ${total_spend_usd():.4f}", flush=True)
    except Exception:  # pragma: no cover - reporting must never fail a run
        pass


atexit.register(_report_spend)


def build_matrix() -> list[dict]:
    units = cm.load_units()
    findings = cm.load_findings()
    vecs = cm.embed_all([u["text"] for u in units] + [f["text"] for f in findings])
    return cm.cosine_matrix(units, findings, vecs)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--emit-sample", type=Path, default=None, metavar="PATH",
                        help="write the blind dense sample to PATH as JSON and stop")
    parser.add_argument("--confirm", action="store_true",
                        help="run the gpt-5.2 judge over the union and report kappa (paid)")
    parser.add_argument("--judge-variance", action="store_true",
                        help="judge 80 band pairs twice against cold caches and report the spread (paid)")
    args = parser.parse_args(argv)

    pairs = build_matrix()
    cosines = {(p["finding_id"], p["unit_id"]): p["cosine"] for p in pairs}
    base = load_base_labels()

    if args.emit_sample:
        already = {(p["finding_id"], p["unit_id"]) for p in base}
        sample = dense_sample(pairs, already)
        # Blind: the producing system is deliberately absent from every row.
        args.emit_sample.write_text(
            json.dumps({"n": len(sample), "seed": DENSE_SEED, "pairs": sample}, indent=1) + "\n"
        )
        print(f"[sample] {len(sample)} pairs -> {args.emit_sample}")
        return 0

    dense = load_dense_labels()
    merged = apply_union_weights(union_labels(base, dense, cosines), pairs)
    thresholds = [round(0.40 + 0.01 * i, 2) for i in range(21)]
    rows = sweep_with_intervals(merged, thresholds)

    judge = None
    if args.confirm:
        verdicts = cm.confirm_labelled(
            [{"finding_text": r["finding_text"], "unit_text": r["unit_text"],
              "finding_id": r["finding_id"], "unit_id": r["unit_id"]} for r in merged]
        )
        hand = [r["label"] for r in merged]
        dense_idx = [i for i, r in enumerate(merged) if r["source"] == "dense"]
        tp = sum(1 for h, v in zip(hand, verdicts) if h and v)
        fp = sum(1 for h, v in zip(hand, verdicts) if not h and v)
        fn = sum(1 for h, v in zip(hand, verdicts) if h and not v)
        judge = {
            "n": len(hand),
            "kappa_union": round(cm.cohens_kappa(hand, verdicts), 4),
            "kappa_dense_only": round(
                cm.cohens_kappa([hand[i] for i in dense_idx], [verdicts[i] for i in dense_idx]), 4
            ),
            "n_dense": len(dense_idx),
            "judge_precision_vs_hand": round(tp / (tp + fp), 4) if (tp + fp) else None,
            "judge_recall_vs_hand": round(tp / (tp + fn), 4) if (tp + fn) else None,
            "judge_positives": sum(verdicts),
            "hand_positives": sum(hand),
        }

    variance = judge_variance(merged) if args.judge_variance else None

    by_source: dict[str, int] = {}
    for row in merged:
        by_source[row["source"]] = by_source.get(row["source"], 0) + 1
    # Carry forward whatever the last paid run measured, so a free re-run does
    # not silently blank the numbers CALIBRATION.md quotes.
    previous = json.loads(DENSE_OUT.read_text()) if DENSE_OUT.exists() else {}
    judge = judge if judge is not None else previous.get("judge_vs_hand")
    variance = variance if variance is not None else previous.get("judge_variance")

    payload = {
        "n_pairs_matrix": len(pairs),
        "n_labelled_union": len(merged),
        "n_labelled_by_source": by_source,
        "n_positive_union": sum(r["label"] for r in merged),
        "dense_seed": DENSE_SEED,
        "dense_bins": [f"[{a:.3f},{b:.3f})" for a, b in DENSE_BINS],
        "union_strata": [f"[{a:.3f},{b:.3f})" for a, b in UNION_BINS],
        "judge_vs_hand": judge,
        "judge_variance": variance,
        # The weighted union, so the curve reproduces offline -- no embeddings,
        # no cache, no model. This is what makes the sweep auditable.
        "labels": [
            {k: r[k] for k in
             ("finding_id", "unit_id", "source", "label", "cosine",
              "stratum", "stratum_population", "stratum_labelled", "weight")}
            for r in sorted(merged, key=lambda r: (r["cosine"], r["finding_id"], r["unit_id"]))
        ],
        "sweep": rows,
        "at_0.45": next(r for r in rows if r["threshold"] == 0.45),
        "at_0.55": next(r for r in rows if r["threshold"] == 0.55),
    }
    DENSE_OUT.write_text(json.dumps(payload, indent=1) + "\n")
    print(json.dumps({k: payload[k] for k in
                      ("n_labelled_union", "n_labelled_by_source", "n_positive_union",
                       "at_0.45", "at_0.55", "judge_vs_hand", "judge_variance")}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

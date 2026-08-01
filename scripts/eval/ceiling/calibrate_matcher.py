"""The matcher calibration ``match.py:65-66`` specifies and never got.

``COS_THRESHOLD = 0.55`` carries this comment::

    # Initial value chosen before hand-label calibration. Phase-2 calibration
    # target: 30 labeled pairs with agreement >=0.85; update this comment with
    # precision/recall.

It was never run, and the number it guards decides the headline of
``HEADTOHEAD.md``: relaxing it to 0.45 moved DAG pooled recall 0.0815 -> 0.2807.
A prefilter that can more than triple the metric is not a detail.

What this module does
---------------------
1. Rebuilds the 212 label units and the finding corpus (``corpus.py``).
2. Embeds every text with the same model and the same cache key as ``match.py``,
   so warm entries in either project's match cache are reused at $0.
3. Computes the full within-manuscript cosine matrix -- no model calls.
4. Draws a **stratified** sample of pairs across cosine bins with a fixed seed,
   which is then hand-labelled (``pair_labels.json``). Stratification is what
   makes recall estimable at all: an unstratified draw from a matrix that is
   >99% non-matches would contain almost no positives.
5. Sweeps the threshold and reports precision and recall of the *prefilter*
   against the hand labels, and of the *full pipeline* (prefilter + gpt-5.2
   confirmation) where confirmations are available.

Everything except step 5's confirmation calls is free and deterministic.

Operating point
---------------
The cost asymmetry is stated in ``CEILING.md`` and implemented in
``choose_operating_point``: this threshold is a **prefilter for a downstream
judge**, not a decision. A false negative here is unrecoverable -- the pair is
never shown to the confirmer, and the unit is scored as missed forever. A false
positive costs one more line in a batched confirmation call, roughly $0.0002.
Recall is therefore worth far more than precision, and the operating point is
the lowest threshold whose confirmation cost is still bounded.
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

from scripts.eval.ceiling.corpus import load_findings, load_units  # noqa: E402

PAIR_LABELS = CEILING_DIR / "pair_labels.json"
SWEEP_OUT = CEILING_DIR / "sweep.json"

#: Bin edges for the stratified draw. Dense where the decision boundary lives.
BINS = ((0.0, 0.30), (0.30, 0.40), (0.40, 0.45), (0.45, 0.50), (0.50, 0.55), (0.55, 0.60), (0.60, 0.70), (0.70, 1.01))
PER_BIN = 20
SEED = 20260801


def embed_all(texts: list[str]) -> dict[str, list[float]]:
    """Embed via ``match._embed_texts`` so the cache key and the model match exactly."""
    from scripts.eval import match

    caches = [
        CEILING_DIR.parent / "cache" / "match",
        CEILING_DIR.parent.parent.parent.parent.parent / "reviewer-agent" / "eval" / "results" / ".matchcache",
    ]
    unique = sorted(set(texts))
    # Warm the ceiling cache from whatever either project already paid for.
    own = CEILING_DIR / "cache"
    (own / "embed").mkdir(parents=True, exist_ok=True)
    for cache in caches:
        src = cache / "embed"
        if not src.exists():
            continue
        for text in unique:
            key = match._embedding_cache_key(text)
            dst = own / "embed" / f"{key}.json"
            if not dst.exists() and (src / f"{key}.json").exists():
                dst.write_text((src / f"{key}.json").read_text())
    stats: dict[str, int] = {}
    vectors = match._embed_texts(unique, own, None, stats)
    print(f"[embed] {len(unique)} texts, cache_hits={stats.get('embed_cache_hits', 0)} "
          f"new={stats.get('embedded_texts', 0)}")
    return dict(zip(unique, vectors))


def cosine_matrix(units: list[dict], findings: list[dict], vecs: dict[str, list[float]]) -> list[dict]:
    """Every within-manuscript (finding, unit) pair with its cosine."""
    from scripts.eval.match import _cosine

    by_draft: dict[str, list[dict]] = {}
    for unit in units:
        by_draft.setdefault(unit["draft_id"], []).append(unit)
    pairs = []
    for finding in findings:
        fv = vecs[finding["text"]]
        for unit in by_draft.get(finding["draft_id"], []):
            pairs.append(
                {
                    "finding_id": finding["finding_id"],
                    "system": finding["system"],
                    "unit_id": unit["unit_id"],
                    "draft_id": finding["draft_id"],
                    "cosine": round(_cosine(fv, vecs[unit["text"]]), 6),
                    "finding_text": finding["text"],
                    "unit_text": unit["text"],
                }
            )
    return pairs


def stratified_sample(pairs: list[dict], per_bin: int = PER_BIN, seed: int = SEED) -> list[dict]:
    rng = random.Random(seed)
    sample: list[dict] = []
    for low, high in BINS:
        bucket = [p for p in pairs if low <= p["cosine"] < high]
        bucket.sort(key=lambda p: (p["finding_id"], p["unit_id"]))
        drawn = bucket if len(bucket) <= per_bin else rng.sample(bucket, per_bin)
        for pair in drawn:
            row = dict(pair)
            row["bin"] = f"[{low:.2f},{high:.2f})"
            row["bin_population"] = len(bucket)
            row["bin_drawn"] = len(drawn)
            sample.append(row)
    sample.sort(key=lambda p: (p["bin"], p["finding_id"], p["unit_id"]))
    return sample


def _weighted_counts(labelled: list[dict], threshold: float) -> dict[str, float]:
    """Population-weighted confusion counts.

    Each labelled pair stands for ``bin_population / bin_drawn`` pairs of the
    matrix. Without that weight the sample's precision would be meaningless --
    the high-cosine bins are oversampled by three orders of magnitude.
    """
    tp = fp = fn = tn = 0.0
    for pair in labelled:
        w = pair["bin_population"] / pair["bin_drawn"]
        predicted = pair["cosine"] >= threshold
        actual = bool(pair["label"])
        if predicted and actual:
            tp += w
        elif predicted and not actual:
            fp += w
        elif not predicted and actual:
            fn += w
        else:
            tn += w
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn}


def sweep(labelled: list[dict], thresholds: list[float]) -> list[dict]:
    rows = []
    for threshold in thresholds:
        c = _weighted_counts(labelled, threshold)
        precision = c["tp"] / (c["tp"] + c["fp"]) if (c["tp"] + c["fp"]) else float("nan")
        recall = c["tp"] / (c["tp"] + c["fn"]) if (c["tp"] + c["fn"]) else float("nan")
        f1 = 2 * precision * recall / (precision + recall) if precision and recall and not math.isnan(precision) else 0.0
        rows.append(
            {
                "threshold": round(threshold, 3),
                "precision": round(precision, 4) if not math.isnan(precision) else None,
                "recall": round(recall, 4) if not math.isnan(recall) else None,
                "f1": round(f1, 4),
                "candidates_est": round(c["tp"] + c["fp"], 1),
                **{k: round(v, 1) for k, v in c.items()},
            }
        )
    return rows


def confirm_labelled(labelled: list[dict]) -> list[int]:
    """Run ``match``'s own gpt-5.2 confirmation judge over the hand-labelled pairs.

    This is the only paid step in the module. It exists so the judge can be
    scored against the hand labels with Cohen's kappa -- the prefilter and the
    judge are two different failure modes and conflating them would hide which
    one is losing the units.
    """
    from scripts.eval import match

    own = CEILING_DIR / "cache"
    (own / "confirm").mkdir(parents=True, exist_ok=True)
    for other in (
        CEILING_DIR.parent / "cache" / "match" / "confirm",
        CEILING_DIR.parent.parent.parent.parent.parent / "reviewer-agent" / "eval" / "results" / ".matchcache" / "confirm",
    ):
        if not other.exists():
            continue
        for pair in labelled:
            key = match._confirm_cache_key(pair["finding_text"], pair["unit_text"])
            dst = own / "confirm" / f"{key}.json"
            if not dst.exists() and (other / f"{key}.json").exists():
                dst.write_text((other / f"{key}.json").read_text())

    pairs = [{"noesis_text": p["finding_text"], "unit_text": p["unit_text"]} for p in labelled]
    stats: dict[str, int] = {}
    results = match._confirm_pairs(pairs, own, None, None, stats)
    print(f"[confirm] cache_hits={stats.get('confirm_cache_hits', 0)} calls={stats.get('confirm_calls', 0)}")
    return [1 if r["confirmed"] else 0 for r in results]


def cohens_kappa(a: list[int], b: list[int]) -> float:
    n = len(a)
    if n == 0:
        return float("nan")
    agree = sum(1 for x, y in zip(a, b) if x == y) / n
    pa1 = sum(a) / n
    pb1 = sum(b) / n
    chance = pa1 * pb1 + (1 - pa1) * (1 - pb1)
    return (agree - chance) / (1 - chance) if chance != 1 else float("nan")


def choose_operating_point(rows: list[dict], max_candidates_per_finding: float, n_findings: int) -> dict:
    """Lowest threshold whose estimated candidate volume stays inside budget.

    Recall-first, because a prefilter false negative is unrecoverable and a
    false positive costs one line in a batched confirmation call.
    """
    budget = max_candidates_per_finding * n_findings
    feasible = [r for r in rows if r["candidates_est"] <= budget and r["recall"] is not None]
    if not feasible:
        return rows[0]
    return min(feasible, key=lambda r: r["threshold"])


def _report_spend() -> None:
    """Every entry point in this directory prints its own spend, to 4 decimals.

    ``llm_budget`` accounting is process-local, so a number that is not printed
    before the process exits is unrecoverable afterwards.
    """
    try:
        from app.core.llm_budget import total_spend_usd

        print(f"[spend] ${total_spend_usd():.4f}", flush=True)
    except Exception:  # pragma: no cover - reporting must never fail a run
        pass


atexit.register(_report_spend)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--emit-sample", action="store_true", help="write the unlabelled stratified sample and stop")
    parser.add_argument("--sample-path", type=Path, default=CEILING_DIR / "pair_sample.json")
    parser.add_argument("--confirm", action="store_true", help="also run the gpt-5.2 judge and report kappa")
    args = parser.parse_args()

    units = load_units()
    findings = load_findings()
    vecs = embed_all([u["text"] for u in units] + [f["text"] for f in findings])
    pairs = cosine_matrix(units, findings, vecs)
    print(f"[matrix] {len(pairs)} within-manuscript pairs from {len(findings)} findings x {len(units)} units")

    if args.emit_sample:
        sample = stratified_sample(pairs)
        args.sample_path.write_text(json.dumps({"n": len(sample), "seed": SEED, "pairs": sample}, indent=1) + "\n")
        print(f"[sample] {len(sample)} pairs -> {args.sample_path}")
        return 0

    labelled = json.loads(PAIR_LABELS.read_text())["pairs"]
    by_key = {(p["finding_id"], p["unit_id"]): p for p in pairs}
    for pair in labelled:
        pair["cosine"] = by_key[(pair["finding_id"], pair["unit_id"])]["cosine"]

    thresholds = [round(0.30 + 0.01 * i, 2) for i in range(46)]
    rows = sweep(labelled, thresholds)
    op = choose_operating_point(rows, max_candidates_per_finding=6.0, n_findings=len(findings))

    judge: dict | None = None
    if args.confirm:
        verdicts = confirm_labelled(labelled)
        hand = [int(p["label"]) for p in labelled]
        above = [i for i, p in enumerate(labelled) if p["cosine"] >= 0.55]
        tp = sum(1 for h, v in zip(hand, verdicts) if h and v)
        fp = sum(1 for h, v in zip(hand, verdicts) if not h and v)
        fn = sum(1 for h, v in zip(hand, verdicts) if h and not v)
        judge = {
            "n": len(hand),
            "kappa_all": round(cohens_kappa(hand, verdicts), 4),
            "kappa_above_0.55": round(
                cohens_kappa([hand[i] for i in above], [verdicts[i] for i in above]), 4
            ),
            "n_above_0.55": len(above),
            "judge_precision_vs_hand": round(tp / (tp + fp), 4) if (tp + fp) else None,
            "judge_recall_vs_hand": round(tp / (tp + fn), 4) if (tp + fn) else None,
            "judge_positives": sum(verdicts),
            "hand_positives": sum(hand),
        }

    payload = {
        "judge_vs_hand": judge,
        "n_pairs_matrix": len(pairs),
        "n_pairs_labelled": len(labelled),
        "n_findings": len(findings),
        "n_units": len(units),
        "seed": SEED,
        "bins": [f"[{a:.2f},{b:.2f})" for a, b in BINS],
        "sweep": rows,
        "operating_point": op,
        "at_0.55": next(r for r in rows if r["threshold"] == 0.55),
        "at_0.45": next(r for r in rows if r["threshold"] == 0.45),
    }
    SWEEP_OUT.write_text(json.dumps(payload, indent=1) + "\n")
    print(json.dumps({k: payload[k] for k in ("operating_point", "at_0.55", "at_0.45", "judge_vs_hand")}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

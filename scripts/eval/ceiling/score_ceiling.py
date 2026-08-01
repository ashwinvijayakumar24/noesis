"""Cross the hand taxonomy with what the two systems actually match.

Produces the deliverable numbers: how many units are addressable, how many of
those either system reaches, and both systems' recall re-expressed against the
addressable subset instead of all 212.

Runs the *real* matcher -- ``match.match`` with ``COS_THRESHOLD`` monkeypatched
per threshold, so the prefilter and the gpt-5.2 confirmation are exactly the
ones the head-to-head used. The finding corpus pools every recorded run of each
system on these three manuscripts, which makes the "found" set a **best case**:
it is the union over replicates, not one run. A ceiling question deserves the
generous reading of what the systems have demonstrated.

Append-only sink at ``ceiling.jsonl``, keyed by a config hash over the label
snapshot, the finding corpus, the threshold and the prompt version.
"""

from __future__ import annotations

import argparse
import atexit
import collections
import hashlib
import json
import sys
from pathlib import Path

CEILING_DIR = Path(__file__).resolve().parent
if str(CEILING_DIR.parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(CEILING_DIR.parent.parent.parent))

from scripts.eval.ceiling.corpus import load_findings, load_units  # noqa: E402
from scripts.eval.ceiling.taxonomy import (  # noqa: E402
    ADDRESSABLE,
    ADDRESSABLE_INCLUDING_SURFACE,
    ADDRESSABLE_WITH_RETRIEVAL,
    CATEGORIES,
    UNMATCHABLE,
)

SINK = CEILING_DIR / "ceiling.jsonl"


def _hash(parts: list[str]) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()[:16]


def run(threshold: float, systems: tuple[str, ...] = ("dag", "agent")) -> dict:
    from scripts.eval import match

    units = load_units()
    findings = [f for f in load_findings() if f["system"] in systems]
    labels = {r["unit_id"]: r for r in json.loads((CEILING_DIR / "hand_labels.json").read_text())["labels"]}

    original = match.COS_THRESHOLD
    match.COS_THRESHOLD = threshold
    cache = CEILING_DIR / "cache"
    matched: dict[str, set[str]] = {s: set() for s in systems}
    try:
        for system in systems:
            for draft_id in sorted({u["draft_id"] for u in units}):
                items = [
                    {"id": f["finding_id"], "text": f["text"]}
                    for f in findings
                    if f["system"] == system and f["draft_id"] == draft_id
                ]
                targets = [u for u in units if u["draft_id"] == draft_id]
                if not items:
                    continue
                stats: dict[str, int] = {}
                for m in match.match(items, targets, cache_dir=cache, stats=stats):
                    if m["confirmed"]:
                        matched[system].add(m["unit_id"])
                print(
                    f"[score] t={threshold} {system} {draft_id}: "
                    f"cand={stats.get('candidate_pairs')} hits={stats.get('confirm_cache_hits')} "
                    f"calls={stats.get('confirm_calls')} matched={len(matched[system])}",
                    flush=True,
                )
    finally:
        match.COS_THRESHOLD = original

    weights = {u["unit_id"]: u["severity_weight"] for u in units}
    total_weight = sum(weights.values())
    by_cat = collections.Counter(r["category"] for r in labels.values())
    weight_by_cat = collections.Counter()
    for uid, r in labels.items():
        weight_by_cat[r["category"]] += weights[uid]

    def subset(cats) -> set[str]:
        return {uid for uid, r in labels.items() if r["category"] in cats}

    result = {
        "threshold": threshold,
        "n_units": len(units),
        "n_findings": len(findings),
        "total_severity_weight": round(total_weight, 4),
        "category_counts": {c: by_cat[c] for c in CATEGORIES},
        "category_weight": {c: round(weight_by_cat[c], 4) for c in CATEGORIES},
        "requires_non_text": sum(1 for r in labels.values() if r["requires_non_text"]),
        "systems": {},
    }
    both = set().union(*matched.values()) if matched else set()
    for name, hits in list(matched.items()) + [("union", both)]:
        row = {
            "units_matched": len(hits),
            "recall_all_212": round(len(hits) / len(units), 4),
            "severity_recall_all_212": round(sum(weights[u] for u in hits) / total_weight, 4),
            "matched_by_category": {c: sum(1 for u in hits if labels[u]["category"] == c) for c in CATEGORIES},
        }
        for label, cats in (
            ("addressable", ADDRESSABLE),
            ("addressable_with_retrieval", ADDRESSABLE_WITH_RETRIEVAL),
            ("addressable_incl_surface", ADDRESSABLE_INCLUDING_SURFACE),
        ):
            denom = subset(cats)
            hit = hits & denom
            row[f"recall_vs_{label}"] = round(len(hit) / len(denom), 4) if denom else None
            row[f"severity_recall_vs_{label}"] = (
                round(sum(weights[u] for u in hit) / sum(weights[u] for u in denom), 4) if denom else None
            )
            row[f"n_{label}"] = len(denom)
        row["matched_in_unmatchable"] = len(hits & subset(UNMATCHABLE))
        result["systems"][name] = row
    result["config_hash"] = _hash(
        [
            "ceiling_v1",
            str(threshold),
            match.PROMPT_VERSION,
            _hash(sorted(u["unit_id"] + u["text"] for u in units)),
            _hash(sorted(f["text"] for f in findings)),
        ]
    )
    return result


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
    parser.add_argument("--threshold", type=float, action="append", default=None)
    args = parser.parse_args()
    thresholds = args.threshold or [0.55, 0.45]
    for threshold in thresholds:
        result = run(threshold)
        with SINK.open("a") as fh:
            fh.write(json.dumps(result, sort_keys=True) + "\n")
        print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

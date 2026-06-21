"""Validate the non-ML held-out transfer guardrail for OpenReview eval work."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


EVAL_DIR = Path(__file__).resolve().parent
DEFAULT_MANIFEST = EVAL_DIR / "heldout" / "manifest.json"
DEFAULT_BASELINE = EVAL_DIR / "results" / "openreview_scoreboard.json"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def _resolve_eval_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else EVAL_DIR / path


def validate_manifest(manifest: dict) -> list[str]:
    failures: list[str] = []
    papers = manifest.get("papers")
    if not isinstance(papers, list):
        return ["manifest.papers must be a list"]
    if not 3 <= len(papers) <= 5:
        failures.append(f"manifest must contain 3-5 held-out papers, found {len(papers)}")

    for idx, paper in enumerate(papers, start=1):
        if not isinstance(paper, dict):
            failures.append(f"papers[{idx}] must be an object")
            continue
        paper_id = str(paper.get("paper_id") or "").strip()
        field = str(paper.get("field") or "").strip().lower()
        pdf_path = str(paper.get("pdf_path") or "").strip()
        if not paper_id:
            failures.append(f"papers[{idx}] missing paper_id")
        if not field:
            failures.append(f"{paper_id or f'papers[{idx}]'} missing field")
        if field in {"ml", "machine_learning", "machine learning", "artificial_intelligence"}:
            failures.append(f"{paper_id} is ML-tagged; held-out transfer set must be non-ML")
        if not pdf_path:
            failures.append(f"{paper_id or f'papers[{idx}]'} missing pdf_path")
        elif not _resolve_eval_path(pdf_path).exists():
            failures.append(f"{paper_id} pdf_path does not exist: {pdf_path}")
    return failures


def validate_results(manifest: dict, results: dict, baseline: dict | None) -> list[str]:
    failures: list[str] = []
    manifest_ids = {str(paper.get("paper_id")) for paper in manifest.get("papers", [])}
    rows = results.get("rows") if isinstance(results.get("rows"), list) else []
    heldout_rows = [row for row in rows if str(row.get("paper_id")) in manifest_ids]
    if len(heldout_rows) != len(manifest_ids):
        found = {str(row.get("paper_id")) for row in heldout_rows}
        failures.append(f"held-out results missing papers: {sorted(manifest_ids - found)}")

    hallucinated = [
        row
        for row in heldout_rows
        if float(row.get("hallucination_rate") or 0.0) > 0.0
        or len(row.get("hallucinations") or []) > 0
    ]
    if hallucinated:
        failures.append(
            "held-out hallucination guard failed: "
            + ", ".join(str(row.get("paper_id")) for row in hallucinated)
        )

    if baseline and heldout_rows:
        baseline_anchor = float((baseline.get("aggregate") or {}).get("mean_anchor_quality") or 0.0)
        heldout_anchor = sum(float(row.get("anchor_quality") or 0.0) for row in heldout_rows) / len(heldout_rows)
        if heldout_anchor + 0.10 < baseline_anchor:
            failures.append(
                f"held-out anchor quality {heldout_anchor:.4f} is more than 0.10 below baseline {baseline_anchor:.4f}"
            )

    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Phase 6 non-ML held-out guardrails.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--results", type=Path, default=None, help="Optional held-out result JSON to validate")
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE, help="OpenReview scoreboard baseline")
    args = parser.parse_args()

    manifest = _load_json(args.manifest)
    failures = validate_manifest(manifest)

    if args.results:
        baseline = _load_json(args.baseline) if args.baseline.exists() else None
        failures.extend(validate_results(manifest, _load_json(args.results), baseline))

    if failures:
        print("[heldout] FAIL")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print(f"[heldout] OK manifest={args.manifest}")
    if not args.results:
        print("[heldout] Results not supplied; manifest-only guard passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

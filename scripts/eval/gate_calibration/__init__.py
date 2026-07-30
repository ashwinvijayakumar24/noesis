"""Publish-gate threshold calibration.

Self-contained: no database, no Docker, no LLM calls. Reads the JSON exports in
``scripts/eval/results/`` plus a human label file, and measures how well the
draft publish gate's a-priori thresholds actually separate degraded runs from
acceptable ones.

Modules:
    rubric.md     operational definition of "degraded" (read before labelling)
    label_cli.py  blind, resumable labelling tool
    metrics.py    pure metric functions (numpy/stdlib only)
    sweep.py      threshold sweep + cost-optimal operating point
"""

LABELS_FILENAME = "labels.jsonl"
SWEEP_RESULTS_FILENAME = "sweep_results.jsonl"

VALID_LABELS = ("degraded", "ok", "unsure")

__all__ = ["LABELS_FILENAME", "SWEEP_RESULTS_FILENAME", "VALID_LABELS"]

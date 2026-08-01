"""End-to-end latency under concurrent load for the 18-node draft-analysis graph.

This package answers a question the project has never answered: *how long does
one draft analysis take when more than one is running at a time, and how does
that degrade as offered load rises.* Every prior measurement in `scripts/eval/`
is a single-node replay -- a per-node cost and wall time, never a user-facing
duration and never under concurrency.

What is measured
----------------
``run_draft_analysis_workflow`` from entry to return: all 18 nodes, real
LangGraph scheduling, the real ``Send`` fan-out to three reviewer personas, the
real process-wide ``retry_utils.openai_semaphore``.

What is NOT measured -- restated in every output this package produces
---------------------------------------------------------------------
* PDF upload and Supabase Storage download
* PDF parsing (Docling / GROBID)
* the publish path and its Supabase writes (suppressed by ``stage_only=True``)
* checkpoint writes (suppressed by ``checkpoint_enabled=False``)

Parsing in particular is a large and highly variable share of what a user
actually waits for. **A number from this harness is a graph-level latency and
must never be labelled end-to-end user-visible latency.**

Modules
-------
``loadmodel``       Poisson arrival sampling, open- and closed-loop schedulers,
                    warmup accounting, config hashing.
``stats``           Summaries. Percentiles come from ``trace_report.metrics``
                    so the n-floor discipline is literally the same code.
``latency_profile`` Per-LLM-call service-time distributions, each tagged
                    MEASURED or ASSUMED with its n.
``stubs``           The stubbed LLM, the Supabase write guard, and the
                    ``stage_only`` assertion.
``workload``        The unit of work: one real graph run, or a synthetic one.
``runner``          CLI.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Mirror node_eval.py / trace_report's bootstrap: the backend app package must be
# importable, and `scripts/eval` must be on the path so `trace_report` resolves.
if Path("/app/app").exists():  # pragma: no cover - container-only branch
    REPO_ROOT = Path("/app")
    if "/app" not in sys.path:
        sys.path.insert(0, "/app")
    EVAL_DIR = Path("/app/scripts/eval")
else:
    REPO_ROOT = Path(__file__).resolve().parents[3]
    _SVC = str(REPO_ROOT / "services" / "backend")
    if _SVC not in sys.path:
        sys.path.insert(0, _SVC)
    EVAL_DIR = Path(__file__).resolve().parents[1]

if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

#: Everything this harness does not measure. Printed with every result table.
EXCLUSIONS = (
    "upload",
    "Supabase Storage download",
    "PDF parsing (Docling/GROBID)",
    "publish writes",
    "checkpoint writes",
)

EXCLUSION_NOTE = (
    "GRAPH-LEVEL latency only. Excluded: "
    + "; ".join(EXCLUSIONS)
    + ". This is NOT user-visible end-to-end latency."
)

__all__ = ["REPO_ROOT", "EVAL_DIR", "EXCLUSIONS", "EXCLUSION_NOTE"]

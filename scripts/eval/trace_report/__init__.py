"""Turn emitted trace spans into per-node latency, cost and concurrency numbers.

Reads the JSONL written by ``app.core.tracing.JsonlAdapter`` (selected with
``NOESIS_TRACING_BACKEND=jsonl``, path from ``NOESIS_TRACING_FILE``) and answers
the two questions the pipeline has never been able to answer: *which node is
slowest* and *what does one run cost*.

Three modules:

``parse``    JSONL -> span records -> reconstructed trees. Tolerant of a
             truncated final line, out-of-order arrival, interleaved traces,
             orphaned spans and duplicate span ids across files. Never crashes
             on a bad line; counts it instead.
``metrics``  Pure functions, no I/O. Percentiles, self-vs-wall time, tokens,
             cost, critical path, fan-out concurrency, LLM-I/O share.
``report``   CLI: a readable table plus an append-only machine-readable JSONL.

Honesty rules enforced throughout (see ``metrics``):

1. No percentile is ever reported without its ``n``, and p95/p99 are refused
   outright below a minimum sample size.
2. An unknown cost is never treated as zero; a run containing an unpriced span
   is marked ``complete=False`` with the unpriced span count carried along.
3. "Never executed" and "took 0 ms" are different rows, never merged.
"""

from __future__ import annotations

import sys
from pathlib import Path

# The cost model must come from ``app.core.llm_budget`` -- the pricing table is
# never duplicated here. Mirror node_eval.py's path bootstrap so this works both
# inside the /app container and from a checkout.
if Path("/app/app").exists():  # pragma: no cover - container-only branch
    _REPO_ROOT = Path("/app")
    if "/app" not in sys.path:
        sys.path.insert(0, "/app")
else:
    _REPO_ROOT = Path(__file__).resolve().parents[3]
    _SVC = str(_REPO_ROOT / "services" / "backend")
    if _SVC not in sys.path:
        sys.path.insert(0, _SVC)

__all__ = ["parse", "metrics", "report"]

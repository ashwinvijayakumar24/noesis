"""Service-time distributions for the stubbed LLM, tagged by provenance.

The stub replaces one thing and one thing only: the wall time of a call to
``client.beta.chat.completions.parse``. Everything else in the graph -- node
Python, LangGraph scheduling, the ``Send`` fan-out, the process-wide
``retry_utils.openai_semaphore`` -- runs for real.

Provenance is carried per node and printed with every stub run, because the
honest position is uncomfortable: **only two nodes have ever had their latency
measured.** ``scripts/eval/results/node_eval.jsonl`` contains replay wall times
for ``editor_pass_node``, ``reviewer_panel_node`` and ``run_quality_diagnostics``
and for nothing else. Every other LLM node's distribution here is an assumption,
labelled ASSUMED, and a stub run's absolute p50 is only as good as that
assumption. The open/closed-loop gap and the fan-out speedup are far more robust
to it than the absolute numbers are, because they are ratios taken under the
same assumption.

Distribution: lognormal, parameterised by mean and coefficient of variation.
Lognormal because request latency is positive, right-skewed and multiplicative
in nature; mean/CV because those are the two things the measurements actually
give (docs/MEASUREMENTS.md §Node replay cost: reviewer replays mean 19.286s, CV 15.0% at n=5).
"""

from __future__ import annotations

import json
import math
import os
import random
import statistics
from dataclasses import dataclass
from pathlib import Path

from . import EVAL_DIR

__all__ = ["NodeSpec", "LatencyProfile", "MEASURED_FALLBACK", "ASSUMED"]

DEFAULT_NODE_EVAL = EVAL_DIR / "results" / "node_eval.jsonl"


@dataclass(frozen=True)
class NodeSpec:
    """Per-LLM-call service time for one node."""

    node: str
    mean: float
    cv: float
    n: int
    source: str  # "MEASURED" | "ASSUMED" | "CALIBRATED"
    note: str = ""

    def label(self) -> str:
        return f"{self.node}: mean={self.mean:.2f}s cv={self.cv:.0%} [{self.source} n={self.n}]"


#: Frozen copy of what node_eval.jsonl held on 2026-07-30, so the profile is
#: reproducible even if the results file is regenerated or absent. Values are
#: node wall time; both nodes make exactly one LLM call per invocation
#: (`node_eval.py`'s per-node call table and the recorded `usage.calls`), so node
#: wall time IS per-call latency for them.
MEASURED_FALLBACK: dict[str, NodeSpec] = {
    "editor_pass_node": NodeSpec(
        "editor_pass_node", 7.431, 0.170, 6, "MEASURED",
        "node_eval.jsonl replays; 1 LLM call/invocation",
    ),
    "reviewer_panel_node": NodeSpec(
        "reviewer_panel_node", 19.386, 0.140, 12, "MEASURED",
        "node_eval.jsonl replays across 3 personas; 1 LLM call/invocation",
    ),
}

#: Every other node that makes an LLM call. There is no measurement for any of
#: them. The value is deliberately the same for all of them and deliberately
#: round, so nobody mistakes it for data: it is the midpoint between the one
#: fast measured node (editor, 7.4s) and the one slow one (reviewer, 19.4s),
#: with a wider CV than either measured node to avoid understating tail risk.
ASSUMED_MEAN = 8.0
ASSUMED_CV = 0.35

ASSUMED_LLM_NODES = (
    "extract_claims",
    "profile_manuscript",
    "map_citations",
    "citation_judge_node",
    "reviewer_judge_node",
    "meta_reviewer_node",
    "verify_citations",
    "detect_gaps",
    "structural_checks",
    "run_quality_diagnostics",
    "synthesize_report",
    "search_literature",
    "extract_references",
    "extract_structure",
    "categorize_claims",
    "discover_external_sources",
)

ASSUMED: dict[str, NodeSpec] = {
    node: NodeSpec(node, ASSUMED_MEAN, ASSUMED_CV, 0, "ASSUMED",
                   "no measurement exists for this node")
    for node in ASSUMED_LLM_NODES
}


#: Written by the real-LLM calibration run (see docs/MEASUREMENTS.md §Graph latency). This is the only
#: source that covers every LLM-calling node in one consistent graph execution,
#: so it outranks the node-replay MEASURED numbers -- which cover two nodes,
#: were taken months apart, and were taken in isolation rather than in-graph.
CALIBRATION_PATH = Path(__file__).resolve().parent / "calibration.json"


def _load_calibration(path: Path | None = None) -> dict[str, NodeSpec]:
    p = Path(path or CALIBRATION_PATH)
    if not p.is_file():
        return {}
    try:
        blob = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    note = str(blob.get("source", ""))[:120]
    return {
        node: NodeSpec(node, float(v["mean"]), float(v["cv"]), int(v["n"]),
                       "CALIBRATED", note)
        for node, v in (blob.get("nodes") or {}).items()
        if v.get("mean", 0) > 0
    }


def _load_measured(path: Path) -> dict[str, NodeSpec]:
    """Recompute MEASURED specs from node_eval.jsonl if it is readable.

    Falls back to :data:`MEASURED_FALLBACK` per node rather than wholesale, so a
    partially-populated results file cannot silently drop a node.
    """
    if not path.is_file():
        return dict(MEASURED_FALLBACK)
    samples: dict[str, list[float]] = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue  # tolerate a truncated tail, same as trace_report.parse
            if rec.get("record_type") != "replay" or rec.get("status") != "ok":
                continue
            node, wall = rec.get("node"), rec.get("wall_seconds")
            calls = (rec.get("usage") or {}).get("calls", 0)
            if not node or not isinstance(wall, (int, float)) or calls < 1:
                continue
            samples.setdefault(node, []).append(float(wall) / calls)
    except OSError:
        return dict(MEASURED_FALLBACK)

    out = dict(MEASURED_FALLBACK)
    for node, vals in samples.items():
        if len(vals) < 2:
            continue
        mean = statistics.fmean(vals)
        if mean <= 0:
            continue
        out[node] = NodeSpec(
            node, mean, statistics.stdev(vals) / mean, len(vals), "MEASURED",
            f"recomputed from {path.name}",
        )
    return out


class LatencyProfile:
    """Samples a per-LLM-call latency for a node, and says where it came from."""

    def __init__(
        self,
        specs: dict[str, NodeSpec] | None = None,
        *,
        seed: int = 7,
        node_eval_path: Path | None = None,
        assumed_mean: float | None = None,
        assumed_cv: float | None = None,
        speedup: float = 1.0,
        use_calibration: bool = True,
    ):
        if specs is None:
            assumed = dict(ASSUMED)
            if assumed_mean is not None or assumed_cv is not None:
                m = ASSUMED_MEAN if assumed_mean is None else assumed_mean
                c = ASSUMED_CV if assumed_cv is None else assumed_cv
                assumed = {
                    k: NodeSpec(k, m, c, 0, "ASSUMED", "operator-overridden assumption")
                    for k in ASSUMED
                }
            specs = {
                **assumed,
                **_load_measured(node_eval_path or DEFAULT_NODE_EVAL),
                **(_load_calibration() if use_calibration else {}),
            }
        self.specs = specs
        #: Wall-clock compression. `speedup=20` runs a sweep in 1/20th the time
        #: with the identical *shape*: every service time is divided, so all
        #: ratios (open/closed gap, fan-out speedup, goodput knee as a multiple
        #: of capacity) are preserved while absolute seconds are not. Any run
        #: with speedup != 1 must have its absolute latencies labelled as
        #: time-compressed.
        self.speedup = speedup
        self._rng = random.Random(seed)
        self.default = NodeSpec(
            "__default__", ASSUMED_MEAN, ASSUMED_CV, 0, "ASSUMED",
            "node not in the profile table",
        )
        self.draws: list[tuple[str, float]] = []

    def spec(self, node: str | None) -> NodeSpec:
        return self.specs.get(node or "", self.default)

    def sample(self, node: str | None) -> float:
        """One lognormal draw with the spec's mean and CV, divided by speedup."""
        s = self.spec(node)
        sigma2 = math.log(1.0 + s.cv * s.cv)
        mu = math.log(s.mean) - 0.5 * sigma2
        value = math.exp(self._rng.gauss(mu, math.sqrt(sigma2))) / self.speedup
        self.draws.append((s.node, value))
        return value

    def provenance(self) -> list[str]:
        lines: list[str] = []
        for tier in ("CALIBRATED", "MEASURED"):
            group = [s for s in self.specs.values() if s.source == tier]
            if not group:
                continue
            lines.append(f"{tier} ({len(group)} nodes):")
            lines += [f"  {s.label()}" for s in sorted(group, key=lambda x: x.node)]
        assumed = [s for s in self.specs.values() if s.source == "ASSUMED"]
        if assumed:
            lines.append(
                f"ASSUMED ({len(assumed)} nodes, mean={assumed[0].mean:.2f}s "
                f"cv={assumed[0].cv:.0%}) -- none of these made an LLM call on the "
                "no-corpus path, so the assumption is unexercised here: "
                + ", ".join(sorted(s.node for s in assumed))
            )
        if self.speedup != 1.0:
            lines.append(
                f"TIME-COMPRESSED: every service time divided by {self.speedup:g}. "
                "Absolute seconds below are NOT real seconds; ratios are preserved."
            )
        return lines

    def to_dict(self) -> dict:
        return {
            "speedup": self.speedup,
            "specs": {
                k: {"mean": v.mean, "cv": v.cv, "n": v.n, "source": v.source}
                for k, v in sorted(self.specs.items())
            },
        }


def env_profile(**kw) -> LatencyProfile:
    """Profile with `NOESIS_LOADGEN_*` overrides applied (used by the CLI)."""
    def _f(name: str) -> float | None:
        raw = os.environ.get(name, "").strip()
        return float(raw) if raw else None

    kw.setdefault("assumed_mean", _f("NOESIS_LOADGEN_ASSUMED_MEAN"))
    kw.setdefault("assumed_cv", _f("NOESIS_LOADGEN_ASSUMED_CV"))
    return LatencyProfile(**kw)

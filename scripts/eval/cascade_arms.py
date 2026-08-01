"""Where is the cost/quality cliff? Sweep one node at a time down the tiers.

Nine of the ten LLM call sites in the draft-analysis pipeline run
``gpt-5.2-chat-latest``; only ``editor_pass`` runs ``gpt-5-mini``, and it does
so because someone once decided it should, not because anything measured it.
This script measures it: for one node at a time, with every other node held at
its production model, it replays that node on a cheaper tier and reports what
that costs and what it breaks.

Per-node, not global. The deliverable is *which* nodes tolerate a cheaper model,
which a single blended pipeline number cannot express -- a global swap that
looks acceptable on average can be one catastrophic node hiding behind six
indifferent ones.

What this instrument can and cannot resolve
-------------------------------------------
It detects **cliffs, not margins**. Three independent reasons:

* quality CV is ~95% at n=5 -- ``temperature`` is stripped for ``gpt-5.2*``
  (and rejected outright by the cheap tiers, see ``retry_utils``) and there is
  no seed, so the same arm run twice does not produce the same findings;
* the confirmation judge disagrees with *itself* at kappa 0.75-0.85, so every
  unit count here carries a +/-10% band and is printed as ``N +/- b``, never
  as a bare integer;
* only 76 of the 212 hand-labelled review units are ``defect_addressable`` at
  all, so both denominators are always reported and neither is quoted alone.

Therefore this script never claims "no quality loss". It claims **"no
detectable loss at n=N"**, which is a different and much weaker statement. A
node where the cheap model is catastrophically worse shows up unmistakably; a
node where it is 10% worse does not show up at all, and the report says so
rather than implying the measurement covered it.

Structural failure outranks quality
-----------------------------------
At these tiers the interesting failure is not a slightly worse review, it is no
review at all. A reasoning model given too small a completion budget spends it
on reasoning tokens and returns an empty string; this repo has been bitten by
that exact shape three times (``max_tokens`` -> ``max_completion_tokens``, the
stripped ``temperature``, the reranker's 100-token budget). So every arm is
probed at the SDK boundary -- ``finish_reason``, refusal, content length and
whether structured parsing yielded ``None`` -- for every call, and a node that
returns zero findings is reported as broken rather than as scoring zero.

Two failures found this way before a dollar was spent on scoring:

* ``gpt-5-mini`` and ``gpt-5-nano`` reject ``temperature=0`` outright (400).
  ``reviewer_panel`` and ``meta_reviewer`` both pass it, so both would have
  failed every call on every cheap arm. Fixed in ``retry_utils`` rather than
  measured as a quality result.
* ``gpt-5-nano`` spends hundreds of reasoning tokens on a trivial prompt, so
  it is the tier most likely to exhaust a node's ``max_completion_tokens``.
  ``finish_reason == "length"`` is counted per arm for exactly this reason.

Cost
----
``NOESIS_LLM_MAX_SPEND_USD`` bounds the run. Note that the ledger *under-reports*
against a corpus that tokenizes at ~3.4 chars/token, so budget against the true
figure. Node calls here record real SDK usage blocks (``record_response_usage``),
which is the accurate path; the estimating path is elsewhere.

Identity
--------
Append-only JSONL at ``results/cascade_arms.jsonl``, keyed by a config hash that
includes **the per-node model assignment**. Two arms that differ only in which
model a node ran cannot collide -- this repo has had seven incidents of two
different things sharing one identity, and an arms file is the obvious eighth.
"""

from __future__ import annotations

import argparse
import collections
import contextlib
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

EVAL_DIR = Path(__file__).resolve().parent
REPO_ROOT = EVAL_DIR.parents[1]
for _p in (str(REPO_ROOT), str(REPO_ROOT / "services" / "backend")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

DEFAULT_SINK = EVAL_DIR / "results" / "cascade_arms.jsonl"
DEFAULT_STATE_DIR = EVAL_DIR / "cache" / "state"

#: The 3 papers the 212-unit hand-labelled gold covers. Scoring against a paper
#: outside this set is not scoring against anything.
GOLD_PAPERS = ("10eQ4Cfh8p", "kKRbAY4CXv", "cXs5md5wAq")

PERSONAS = ("literature_positioning", "methodology", "clarity")

#: node name (as ``node_eval`` knows it) -> routing site key (as
#: ``model_routing`` knows it). A node absent here has no override seam and
#: cannot be swept.
NODE_SITES: dict[str, str] = {
    "reviewer_panel_node": "reviewer_panel",
    "extract_claims": "extract_claims",
    "structural_checks": "structural_checks",
    "meta_reviewer_node": "meta_reviewer",
}

#: ``max_completion_tokens`` at each node's call site, recorded so a
#: ``finish_reason == "length"`` can be read against the budget that caused it.
NODE_COMPLETION_BUDGET: dict[str, int] = {
    "reviewer_panel_node": 2500,
    "extract_claims": 8000,
    "structural_checks": 1500,
    "meta_reviewer_node": 2000,
}

#: Nodes whose output is critique text, and so is scorable against the review
#: units. ``extract_claims`` emits *claims*, not critiques: matching them
#: against reviewer complaints measures nothing, so it is swept for cost and
#: structural integrity only and its quality is reported as unmeasured.
SCORABLE_NODES = frozenset({"reviewer_panel_node", "structural_checks", "meta_reviewer_node"})

CONTROL = "control"

#: Bumped to 2 when the ``meta_reviewer`` and ``extract_claims`` findings
#: extractors were corrected: version 1 read key names that those nodes never
#: write, so every v1 arm for those two nodes reported zero findings and zero
#: matched units regardless of model. The version is part of the config hash, so
#: the wrong rows stay in the append-only sink and stay distinguishable from the
#: right ones rather than silently averaging with them.
HARNESS_VERSION = 2


# ---------------------------------------------------------------------------
# Bands. A bare integer here would be a lie about the instrument.
# ---------------------------------------------------------------------------

def band(count: int) -> int:
    """+/-10%, rounded up, minimum 1. Mirrors ``panel_arms.band``."""
    import math

    return max(1, math.ceil(abs(int(count)) * 0.10))


def banded(count: int) -> dict[str, Any]:
    b = band(count)
    return {"value": int(count), "band": b, "display": f"{int(count)} ± {b}"}


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------

def arm_config(
    node: str,
    model: str,
    *,
    papers: tuple[str, ...],
    repeats: int,
    threshold: float,
    personas: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """The full identity of one arm, including the per-node model assignment.

    ``model_assignment`` is the whole routing map, not just the one node that
    moved. An arm is defined by what *every* node ran, so a future sweep that
    moves two nodes at once cannot collide with a single-node arm that happens
    to share a name.
    """
    from app.workflows.draft_analysis.model_routing import ROUTED_SITES

    assignment = dict(ROUTED_SITES)
    if model != CONTROL:
        assignment[NODE_SITES[node]] = model
    return {
        "harness": "cascade_arms",
        "harness_version": HARNESS_VERSION,
        "node": node,
        "swept_site": NODE_SITES[node],
        "arm_model": model,
        # The load-bearing field: identity includes what every node ran.
        "model_assignment": dict(sorted(assignment.items())),
        "papers": list(papers),
        "personas": list(personas) if personas else None,
        "repeats": repeats,
        "cos_threshold": threshold,
        "scorable": node in SCORABLE_NODES,
    }


def config_hash(cfg: dict) -> str:
    blob = json.dumps(cfg, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Structural probe: finish_reason / refusal / emptiness, at the SDK boundary
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def structural_probe(sink: list[dict[str, Any]]):
    """Record the shape of every structured completion made inside the block.

    Patched on the SDK classes rather than on ``retry_utils``: the nodes do
    ``from ... import parse_chat_completion_with_retries``, so a module-level
    patch would miss every node that had already been imported. Patching
    ``Completions.parse`` catches the call wherever it was reached from.

    Records only shape, never prompt or completion text -- these fixtures are
    real manuscripts.
    """
    from openai.resources.chat.completions import completions as _c

    orig_sync = _c.Completions.parse
    orig_async = _c.AsyncCompletions.parse

    def _observe(model: Any, response: Any) -> None:
        try:
            choice = response.choices[0]
            message = getattr(choice, "message", None)
            content = getattr(message, "content", None) or ""
            usage = getattr(response, "usage", None)
            sink.append(
                {
                    "model": str(model),
                    "finish_reason": getattr(choice, "finish_reason", None),
                    "content_chars": len(content),
                    "content_empty": len(content.strip()) == 0,
                    "refusal": bool(getattr(message, "refusal", None)),
                    "parsed_is_none": getattr(message, "parsed", None) is None,
                    "completion_tokens": getattr(usage, "completion_tokens", None),
                    "prompt_tokens": getattr(usage, "prompt_tokens", None),
                }
            )
        except Exception as exc:  # never let the probe break the measurement
            sink.append({"model": str(model), "probe_error": f"{type(exc).__name__}: {exc}"[:200]})

    def sync_parse(self, *args, **kwargs):
        try:
            response = orig_sync(self, *args, **kwargs)
        except Exception as exc:
            sink.append(
                {
                    "model": str(kwargs.get("model")),
                    "api_error": type(exc).__name__,
                    "api_error_message": str(exc)[:300],
                }
            )
            raise
        _observe(kwargs.get("model"), response)
        return response

    async def async_parse(self, *args, **kwargs):
        try:
            response = await orig_async(self, *args, **kwargs)
        except Exception as exc:
            sink.append(
                {
                    "model": str(kwargs.get("model")),
                    "api_error": type(exc).__name__,
                    "api_error_message": str(exc)[:300],
                }
            )
            raise
        _observe(kwargs.get("model"), response)
        return response

    _c.Completions.parse = sync_parse
    _c.AsyncCompletions.parse = async_parse
    try:
        yield sink
    finally:
        _c.Completions.parse = orig_sync
        _c.AsyncCompletions.parse = orig_async


def summarize_structure(calls: list[dict[str, Any]], node: str) -> dict[str, Any]:
    """Fold per-call shape records into the arm's structural verdict.

    ``broken`` is deliberately generous about what counts as broken: an API
    error, a refusal, a truncation, an empty body, or a failure to parse into
    the schema. Any one of those means the node produced nothing usable, which
    is a different and worse outcome than producing a weaker review.
    """
    budget = NODE_COMPLETION_BUDGET.get(node)
    api_errors = [c for c in calls if c.get("api_error")]
    truncated = [c for c in calls if c.get("finish_reason") == "length"]
    empty = [c for c in calls if c.get("content_empty")]
    refusals = [c for c in calls if c.get("refusal")]
    unparsed = [c for c in calls if c.get("parsed_is_none")]
    completions = [c["completion_tokens"] for c in calls if c.get("completion_tokens") is not None]
    return {
        "calls_observed": len(calls),
        "api_errors": len(api_errors),
        "api_error_types": sorted({c["api_error"] for c in api_errors}),
        "api_error_sample": (api_errors[0].get("api_error_message") if api_errors else None),
        "finish_length": len(truncated),
        "content_empty": len(empty),
        "refusals": len(refusals),
        "parsed_is_none": len(unparsed),
        "completion_budget": budget,
        "max_completion_tokens_seen": max(completions) if completions else None,
        "finish_reasons": dict(collections.Counter(
            c.get("finish_reason") for c in calls if c.get("finish_reason")
        )),
        "structurally_broken": bool(api_errors or truncated or empty or refusals or unparsed),
    }


# ---------------------------------------------------------------------------
# Findings extraction, per node
# ---------------------------------------------------------------------------

def _text(*values: Any) -> str:
    for v in values:
        if v and str(v).strip():
            return str(v).strip()
    return ""


def findings_from_state(node: str, state: dict[str, Any]) -> list[dict[str, Any]]:
    """The critique texts a node produced, for matching against review units.

    Each node writes a different key with a different shape; there is no shared
    "findings" surface in the pipeline, so this is per-node by necessity rather
    than by choice.
    """
    out: list[dict[str, Any]] = []

    if node == "reviewer_panel_node":
        for output in state.get("reviewer_outputs") or []:
            persona = output.get("reviewer_type") or output.get("reviewer_id") or "reviewer"
            for issue in output.get("issues") or []:
                t = _text(issue.get("problem"), issue.get("description"), issue.get("title"))
                if t:
                    out.append({"text": t, "persona": persona})
            for weakness in output.get("weaknesses") or []:
                t = _text(weakness)
                if t:
                    out.append({"text": t, "persona": persona})

    elif node == "structural_checks":
        for item in state.get("structural_feedback") or []:
            t = _text(item.get("feedback_text"), item.get("specific_issue"))
            if t:
                out.append({"text": t, "persona": "structural"})

    elif node == "meta_reviewer_node":
        # Keys are MetaReviewOutput's, checked against the schema rather than
        # guessed: an extractor that reads keys the node never writes returns
        # zero findings for every arm, which reads as "all arms identical"
        # instead of "the measurement is broken". That happened here on the
        # first pass -- hence harness_version 2.
        meta = state.get("meta_review") or {}
        if isinstance(meta, dict):
            for key in ("must_address", "nice_to_address", "consensus_weaknesses"):
                for entry in meta.get(key) or []:
                    if isinstance(entry, dict):
                        t = _text(entry.get("problem"), entry.get("description"),
                                  entry.get("title"), entry.get("text"))
                    else:
                        t = _text(entry)
                    if t:
                        out.append({"text": t, "persona": "meta"})

    elif node == "extract_claims":
        # Claims, not critiques -- collected for a count only. Never scored.
        for claim in state.get("claims") or []:
            t = _text(claim.get("claim_text") if isinstance(claim, dict) else claim)
            if t:
                out.append({"text": t, "persona": "claim"})

    return out


# ---------------------------------------------------------------------------
# Scoring an arm against both denominators
# ---------------------------------------------------------------------------

def score_arm(
    findings_by_paper: dict[str, list[dict[str, Any]]],
    threshold: float,
    *,
    cache_dir: Path | None = None,
    match_kwargs: dict[str, Any] | None = None,
    units: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Match one arm's pooled findings against the 212 units, both denominators.

    Same label set, same taxonomy, same matcher and same monkeypatched
    ``COS_THRESHOLD`` as ``ceiling.score_ceiling`` and ``panel_arms.score_arm``,
    so the numbers are comparable to the ones already in the repo. Pooled per
    arm rather than per replay: pooling dedupes finding texts across replicates
    first, which cuts the matcher's confirmation calls substantially.

    ``units`` is an injection seam -- ``load_units()`` atomizes the OpenReview
    gold and falls through to a live LLM call on a cache miss, which is fine
    inside a scoring run and not fine inside a unit test.
    """
    from scripts.eval import match as match_mod
    from scripts.eval.ceiling.corpus import load_units
    from scripts.eval.ceiling.taxonomy import ADDRESSABLE

    units = load_units() if units is None else units
    labels = {
        r["unit_id"]: r
        for r in json.loads((EVAL_DIR / "ceiling" / "hand_labels.json").read_text())["labels"]
    }
    weights = {u["unit_id"]: float(u["severity_weight"]) for u in units}
    total_weight = sum(weights.values())
    addressable = {uid for uid, r in labels.items() if r["category"] in ADDRESSABLE}

    matched: set[str] = set()
    original = match_mod.COS_THRESHOLD
    match_mod.COS_THRESHOLD = threshold
    stats_total: collections.Counter = collections.Counter()
    try:
        for paper, findings in sorted(findings_by_paper.items()):
            targets = [u for u in units if u["draft_id"] == paper]
            if not findings or not targets:
                continue
            texts = sorted({(f.get("text") or "").strip() for f in findings if (f.get("text") or "").strip()})
            items = [{"id": f"{paper}-{i:04d}", "text": t} for i, t in enumerate(texts)]
            stats: dict[str, int] = {}
            kwargs = dict(match_kwargs or {})
            if cache_dir is not None:
                kwargs["cache_dir"] = cache_dir
            for m in match_mod.match(items, targets, stats=stats, **kwargs):
                if m.get("confirmed"):
                    matched.add(str(m["unit_id"]))
            stats_total.update({k: v for k, v in stats.items() if isinstance(v, int)})
    finally:
        match_mod.COS_THRESHOLD = original

    def _weight(ids: set[str]) -> float:
        return sum(weights.get(u, 0.0) for u in ids)

    addr_hits = matched & addressable
    addr_weight = _weight(addressable)
    return {
        "threshold": threshold,
        "n_units_total": len(units),
        "n_units_addressable": len(addressable),
        "units_matched_all_212": banded(len(matched)),
        "units_matched_addressable_76": banded(len(addr_hits)),
        "recall_all_212": round(len(matched) / len(units), 4) if units else None,
        "recall_addressable": round(len(addr_hits) / len(addressable), 4) if addressable else None,
        "severity_recall_all_212": round(_weight(matched) / total_weight, 4) if total_weight else None,
        "severity_recall_addressable": round(_weight(addr_hits) / addr_weight, 4) if addr_weight else None,
        "match_stats": dict(stats_total),
    }


# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------

def summarize_usage(records: list[dict[str, Any]], n_runs: int) -> dict[str, Any]:
    """Absolute and per-run cost/token figures for one arm."""
    usd = sum((r.get("usage") or {}).get("estimated_usd", 0.0) or 0.0 for r in records)
    prompt = sum((r.get("usage") or {}).get("prompt_tokens", 0) or 0 for r in records)
    completion = sum((r.get("usage") or {}).get("completion_tokens", 0) or 0 for r in records)
    cached = sum((r.get("usage") or {}).get("cached_tokens", 0) or 0 for r in records)
    calls = sum((r.get("usage") or {}).get("calls", 0) or 0 for r in records)
    unpriced = sum((r.get("usage") or {}).get("unpriced_calls", 0) or 0 for r in records)
    models: collections.Counter = collections.Counter()
    for r in records:
        for model, n in ((r.get("usage") or {}).get("by_model") or {}).items():
            models[model] += n
    return {
        "n_runs": n_runs,
        "calls": calls,
        "unpriced_calls": unpriced,
        "usd_total": round(usd, 6),
        "usd_per_run": round(usd / n_runs, 6) if n_runs else None,
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "cached_tokens": cached,
        "tokens_per_run": round((prompt + completion) / n_runs, 1) if n_runs else None,
        "models_seen": dict(models),
    }


# ---------------------------------------------------------------------------
# Running one arm
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def routed(site: str, model: str | None):
    """Set (and restore) the per-node model override for one arm."""
    from app.workflows.draft_analysis.model_routing import env_var_for

    var = env_var_for(site)
    previous = os.environ.get(var)
    if model is None:
        os.environ.pop(var, None)
    else:
        os.environ[var] = model
    try:
        yield var
    finally:
        if previous is None:
            os.environ.pop(var, None)
        else:
            os.environ[var] = previous


def run_arm(
    node: str,
    model: str,
    *,
    papers: tuple[str, ...],
    repeats: int,
    state_dir: Path = DEFAULT_STATE_DIR,
    personas: tuple[str, ...] = PERSONAS,
    replay: Callable[..., dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    """Replay ``node`` across the papers on one model. Returns (records, findings, calls).

    Every other node stays on its production model: only one override is set,
    so a difference between arms cannot be attributed to anything else.
    """
    from scripts.eval import node_eval

    replay = replay or node_eval.replay_once
    registry = node_eval._node_registry()
    node_func = registry[node]

    records: list[dict[str, Any]] = []
    findings_by_paper: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    calls: list[dict[str, Any]] = []

    variants = personas if node == "reviewer_panel_node" else (None,)
    site = NODE_SITES[node]

    with routed(site, None if model == CONTROL else model):
        with structural_probe(calls):
            for rep in range(repeats):
                for paper in papers:
                    for variant in variants:
                        captured: dict[str, Any] = {}

                        def _wrapped(state, _f=node_func, _c=captured):
                            result = _f(state)
                            if hasattr(result, "__await__"):
                                async def _await(r=result, c=_c):
                                    value = await r
                                    c["result"] = value
                                    return value
                                return _await()
                            _c["result"] = result
                            return result

                        record = replay(
                            node,
                            paper,
                            _wrapped,
                            reviewer_type=variant,
                            state_dir=state_dir,
                            with_metric=False,
                            repeat_index=rep,
                        )
                        record["arm"] = model
                        record["persona"] = variant

                        node_findings: list[dict[str, Any]] = []
                        if record.get("status") == "ok" and isinstance(captured.get("result"), dict):
                            fixture = node_eval.state_path(node, paper, state_dir, variant)
                            base = json.loads(fixture.read_text()) if fixture.exists() else {}
                            merged = node_eval._merge_state(base, captured["result"])
                            node_findings = findings_from_state(node, merged)
                        record["n_findings"] = len(node_findings)
                        findings_by_paper[paper].extend(node_findings)
                        records.append(record)

    return records, dict(findings_by_paper), calls


# ---------------------------------------------------------------------------
# Sink
# ---------------------------------------------------------------------------

def append_records(records: list[dict[str, Any]], path: Path = DEFAULT_SINK) -> None:
    """Append-only, always. This repo has lost an eval history to a rewrite."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")


def assert_hashes_distinct(arm_records: list[dict[str, Any]]) -> None:
    """Two arms must never share a config hash.

    Checked rather than assumed: the hash is what makes the results file
    readable months from now, and a collision would silently merge two arms
    into one row.
    """
    seen: dict[str, dict[str, Any]] = {}
    for record in arm_records:
        h = record["config_hash"]
        if h in seen:
            raise AssertionError(
                f"config hash collision {h}: "
                f"{seen[h]['config']['node']}/{seen[h]['config']['arm_model']} vs "
                f"{record['config']['node']}/{record['config']['arm_model']}"
            )
        seen[h] = record


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--node", action="append", required=True, choices=sorted(NODE_SITES),
                   help="Node to sweep. Repeatable.")
    p.add_argument("--arm", action="append", required=True,
                   help=f"Model per arm. '{CONTROL}' leaves the node on its production model. Repeatable.")
    p.add_argument("--paper", action="append", default=None,
                   help=f"Paper id. Defaults to the {len(GOLD_PAPERS)} gold-labelled papers.")
    p.add_argument("--repeats", type=int, default=1)
    p.add_argument("--threshold", type=float, default=0.44, help="Calibrated cosine threshold.")
    p.add_argument("--results", type=Path, default=DEFAULT_SINK)
    p.add_argument("--state-dir", type=Path, default=DEFAULT_STATE_DIR)
    p.add_argument("--no-score", action="store_true",
                   help="Skip matching entirely; cost and structural integrity only.")
    p.add_argument("--dry-run", action="store_true", help="Print the plan and spend nothing.")
    return p


def main(argv: list[str] | None = None) -> int:
    from scripts.eval.env import load_backend_env

    load_backend_env()
    args = build_parser().parse_args(argv)
    papers = tuple(args.paper or GOLD_PAPERS)

    if not os.environ.get("NOESIS_LLM_MAX_SPEND_USD"):
        print("refusing to run without NOESIS_LLM_MAX_SPEND_USD set", file=sys.stderr)
        return 2

    plan = [(n, a) for n in args.node for a in args.arm]
    n_variants = lambda n: len(PERSONAS) if n == "reviewer_panel_node" else 1  # noqa: E731
    total = sum(len(papers) * args.repeats * n_variants(n) for n, _ in plan)
    print(f"plan: {len(plan)} arms, {total} replays, papers={list(papers)}, repeats={args.repeats}")
    for node, arm in plan:
        cfg = arm_config(node, arm, papers=papers, repeats=args.repeats, threshold=args.threshold,
                         personas=PERSONAS if node == "reviewer_panel_node" else None)
        print(f"  {node:22s} {arm:20s} hash={config_hash(cfg)}")
    if args.dry_run:
        return 0

    from app.core.llm_budget import totals

    arm_records: list[dict[str, Any]] = []
    for node, arm in plan:
        print(f"\n=== {node} / {arm} ===", flush=True)
        records, findings, calls = run_arm(
            node, arm, papers=papers, repeats=args.repeats, state_dir=args.state_dir
        )
        structure = summarize_structure(calls, node)
        usage = summarize_usage(records, len(records))

        # Replays are appended BEFORE scoring, and scoring is not allowed to
        # kill the run. The first pass lost a paid-for reviewer_panel arm when
        # match.py raised `Missing confirmation for pair index 101` after every
        # replay had already been billed: the records existed only in memory, so
        # the crash discarded the measurement and kept the charge. A scoring
        # failure is now a field on the record, not the end of the batch.
        append_records(records, args.results)

        score = None
        score_error = None
        if not args.no_score and node in SCORABLE_NODES:
            try:
                score = score_arm(findings, args.threshold)
            except Exception as exc:
                score_error = f"{type(exc).__name__}: {exc}"[:500]
                print(f"  scoring FAILED: {score_error}", flush=True)

        cfg = arm_config(node, arm, papers=papers, repeats=args.repeats, threshold=args.threshold,
                         personas=PERSONAS if node == "reviewer_panel_node" else None)
        arm_record = {
            "record_type": "arm",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "config": cfg,
            "config_hash": config_hash(cfg),
            "n_replays": len(records),
            "n_ok": sum(1 for r in records if r.get("status") == "ok"),
            "findings_total": sum(r.get("n_findings", 0) for r in records),
            "findings_per_run": (
                round(sum(r.get("n_findings", 0) for r in records) / len(records), 2)
                if records else None
            ),
            "structure": structure,
            "usage": usage,
            "score": score,
            "score_error": score_error,
            "score_note": (
                None if node in SCORABLE_NODES
                else "not scorable: node emits claims, not critiques; cost and structure only"
            ),
        }
        arm_records.append(arm_record)
        append_records([arm_record], args.results)

        print(f"  replays={len(records)} ok={arm_record['n_ok']} "
              f"findings/run={arm_record['findings_per_run']}")
        print(f"  ${usage['usd_total']:.4f} total, ${usage['usd_per_run'] or 0:.4f}/run, "
              f"{usage['tokens_per_run']} tok/run, models={usage['models_seen']}")
        print(f"  structural_broken={structure['structurally_broken']} "
              f"api_errors={structure['api_errors']} length={structure['finish_length']} "
              f"empty={structure['content_empty']} unparsed={structure['parsed_is_none']}")
        if score:
            print(f"  addressable/76: {score['units_matched_addressable_76']['display']}  "
                  f"all/212: {score['units_matched_all_212']['display']}")

    assert_hashes_distinct(arm_records)
    print(f"\nledger total: ${totals()['estimated_usd']:.4f}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

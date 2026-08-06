"""Two-arm measurement of per-reviewer section scoping (``DRAFT_REVIEWER_SCOPED_PANEL``).

The question this exists to answer is **not** "is scoping better". It is:

> Does the coverage gained by giving each persona its lane's sections outweigh
> the cross-persona prompt-cache discount that scoping destroys?

A quality gain reported without its cache cost is not a result, so every arm
carries input tokens, cached tokens and a cache hit rate alongside its recall.

---

WHAT THE CONTROL ARM ACTUALLY IS
--------------------------------
The build scope asserted that the shipped panel head-truncates the manuscript at
24,000 chars and so discards ~27% of it, always the tail. **That is false.**
``_reviewer_manuscript_text`` returns ``draft_content`` unchanged unless
``DRAFT_REVIEWER_COMPACT_MANUSCRIPT`` is set, and that flag is off by default and
set nowhere in this repo. The 24k cap lives inside the compaction path and never
fires in production.

:func:`audit_control_arm` is a **$0** measurement that establishes this against
the fixtures before anything is spent, and it is why the control arm here is
**three reviewers x the full manuscript**, not three x a truncated one.
Enabling compaction to match the scope doc would measure a path nobody runs, so
:func:`audit_control_arm` refuses when it finds compaction on.

The hypothesis that survives is the one the companion agent harness actually
tested: **does per-reviewer context isolation beat three passes over identical
full text?** Not "does scoping restore text that truncation removed" -- nothing
was removed.

The trade, measured
-------------------
Scoping is not free and is not purely a cost. The manuscript *was* the shared
prefix, so making it vary per persona necessarily forfeits most of the
cross-persona cache discount, while also sending far less text overall. Both
sides are measured here ($/run absolute, both arms), because either could
dominate and the direction is not obvious a priori.

See ``PANEL_SCOPING.md`` for what was found.

Why node replay rather than the full pipeline
---------------------------------------------
The only thing the flag changes is how ``reviewer_panel_node`` assembles its
manuscript block. Replaying that node from the committed state fixtures
(``cache/state/<paper>/reviewer_panel_node__<persona>.json``) holds every
upstream node byte-identical between arms, which is what "the arms differ only
by the flag" actually requires -- a full-pipeline run would let upstream
nondeterminism (extraction, retrieval, diagnostics) leak into the delta and
would cost roughly an order of magnitude more than the $5 budget allows.

The cost of this choice is stated plainly: replay measures the panel's own
prompt-cache behaviour, not the whole graph's, and a scoping change that shifted
*downstream* node cost would not be visible here.

Arms
----
``off``  -- ``DRAFT_REVIEWER_SCOPED_PANEL`` unset (the shipped default path)
``on``   -- ``DRAFT_REVIEWER_SCOPED_PANEL=1``

One process, same manuscripts, same order, interleaved per (paper, replicate) so
that arm assignment cannot correlate with drift in the upstream API.

Scoring
-------
Reuses the ceiling study's taxonomy and label set verbatim
(``ceiling.corpus.load_units``, ``ceiling.taxonomy``, ``ceiling/hand_labels.json``)
and the real matcher (``match.match``) at its calibrated ``COS_THRESHOLD = 0.44``.
Findings are pooled across an arm's replicates before matching, exactly as
``score_ceiling.run`` pools across recorded runs, so "units matched" is the
arm's best case rather than one draw.

Unit counts carry ``±ceil(10%)`` bands. The confirmation judge disagrees with
itself at kappa 0.75-0.85; a bare integer implies a precision the instrument
does not have. Bands are computed the same way ``RECAL`` did so the numbers are
comparable to it.

Sink
----
Append-only JSONL at ``results/panel_arms.jsonl``, keyed by a config hash that
**includes the flag**. This project has had seven incidents of two materially
different things sharing one identity; :func:`assert_arms_separate` refuses to
write a pair of arms whose hashes collide.
"""

from __future__ import annotations

import argparse
import atexit
import collections
import hashlib
import inspect
import json
import math
import os
import platform
import re
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

EVAL_DIR = Path(__file__).resolve().parent
REPO_ROOT = EVAL_DIR.parent.parent
for _p in (str(REPO_ROOT), str(REPO_ROOT / "services" / "backend")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

DEFAULT_SINK = EVAL_DIR / "results" / "panel_arms.jsonl"
DEFAULT_STATE_DIR = EVAL_DIR / "cache" / "state"

#: The environment flag under measurement. Owned by ``reviewer_panel.py`` (S1).
FLAG = "DRAFT_REVIEWER_SCOPED_PANEL"

#: The three papers the 212-unit ceiling label set covers. Scoring against any
#: other paper would have no gold to score against.
PAPERS = ("10eQ4Cfh8p", "kKRbAY4CXv", "cXs5md5wAq")

#: Persona -> the node fixture suffix. Reviewer A (literature_positioning) is
#: the mechanism check: its declared lane is "introduction, related work,
#: discussion", and discussion sits at the end of a manuscript.
PERSONAS = ("literature_positioning", "methodology", "clarity")

#: Reviewer A. Its lane (abstract, introduction, related work, discussion) is
#: genuinely sectional, so scoping concentrates its context.
SECTIONAL_PERSONA = "literature_positioning"

#: Reviewer D. Its declared duties -- terminology consistency *throughout*,
#: argument structure, reporting completeness -- are properties of the whole
#: document, not of any section. Only abstract and limitations are sectional for
#: D, so under scoping D is carried almost entirely by the
#: unclaimed-goes-to-everyone rule.
#:
#: This makes D the control on the mechanism check: **if A rises and D falls,
#: that is the section map redistributing text, not context isolation working.**
CROSS_CUTTING_PERSONA = "clarity"

ARMS = ("off", "on")

HARNESS_VERSION = 1


# ---------------------------------------------------------------------------
# Bands
# ---------------------------------------------------------------------------

def band(count: int) -> int:
    """``ceil(10%)`` of a unit count, as ``RECAL`` used.

    The confirmation judge disagrees with itself at kappa 0.75-0.85, so a
    matched-unit count is not an exact quantity. Every unit count this module
    reports is accompanied by this band; there are no bare integers in the
    output.
    """
    if count < 0:
        raise ValueError(f"count must be non-negative, got {count}")
    return math.ceil(0.10 * count)


def banded(count: int) -> dict[str, Any]:
    """A unit count rendered as value + band + printable string."""
    b = band(count)
    return {"value": count, "band": b, "display": f"{count} ± {b}"}


# ---------------------------------------------------------------------------
# The flag must exist before anything is spent
# ---------------------------------------------------------------------------

class FlagAbsent(RuntimeError):
    """Raised when ``DRAFT_REVIEWER_SCOPED_PANEL`` is not implemented yet."""


def flag_is_implemented(module: Any) -> bool:
    """True when ``reviewer_panel`` actually reads the flag.

    Checked against the module's *source*, not just its attributes: the flag is
    read via ``os.getenv`` at call time (the house pattern -- see
    ``reviewer_compaction_enabled``), so it need not appear as a module-level
    constant. A name that appears nowhere in the source cannot be being read.
    """
    import inspect

    try:
        source = inspect.getsource(module)
    except (OSError, TypeError):  # pragma: no cover - module without a file
        return False
    return FLAG in source


def require_flag() -> Any:
    """Import ``reviewer_panel`` and fail loudly if the flag is not there yet.

    Deliberately noisy. The alternative -- running an "on" arm under a flag
    nothing reads -- produces two arms that are byte-identical in behaviour and
    a delta of zero that looks like a real negative result.
    """
    from app.workflows.draft_analysis.nodes import reviewer_panel

    if not flag_is_implemented(reviewer_panel):
        raise FlagAbsent(
            f"{FLAG} is not implemented in "
            f"{getattr(reviewer_panel, '__file__', '<unknown>')}.\n"
            f"\n"
            f"The 'on' arm cannot be run: setting {FLAG}=1 would change nothing,\n"
            f"both arms would execute the identical code path, and the measured\n"
            f"delta would be zero for a reason that has nothing to do with\n"
            f"scoping. That is a false negative, not a result.\n"
            f"\n"
            f"This runner is complete and its 'off' arm is runnable now\n"
            f"(--arm off). Re-run both arms once S1 lands the flag."
        )
    return reviewer_panel


# ---------------------------------------------------------------------------
# The $0 premise audit
# ---------------------------------------------------------------------------

def audit_control_arm(
    papers: Iterable[str] = PAPERS,
    state_dir: Path = DEFAULT_STATE_DIR,
) -> dict[str, Any]:
    """Establish, for free, what the control arm actually shows each reviewer.

    The scope doc claimed a head-first 24k cap removes the tail of the
    manuscript -- and with it the discussion, which Reviewer A is graded on.
    That is a statement about what ``_reviewer_manuscript_text`` returns, and it
    is settled by calling it: no LLM, no spend.

    Returns per-paper the manuscript size, the size the reviewer actually
    receives, the characters discarded, and whether the document's tail
    survives.

    ``control_is_untruncated`` True means the control arm is "full manuscript",
    which is the configuration to measure against. ``safe_to_measure`` is False
    when compaction is on, because then the control is a path nobody runs in
    production and any delta against it is uninterpretable.
    """
    from app.workflows.draft_analysis.nodes.reviewer_panel import (
        REVIEWER_MANUSCRIPT_MAX_CHARS,
        _reviewer_manuscript_text,
        reviewer_compaction_enabled,
    )

    rows: list[dict[str, Any]] = []
    for paper in papers:
        fixture = state_dir / paper / f"reviewer_panel_node__{PERSONAS[0]}.json"
        if not fixture.exists():
            continue
        draft = json.loads(fixture.read_text()).get("draft_content") or ""
        delivered = _reviewer_manuscript_text(draft)
        discarded = len(draft) - len(delivered)
        # The hypothesis is specifically about the *tail*. Take the last 2,000
        # characters of the manuscript and ask whether the reviewer sees them.
        tail = draft[-2000:].strip()
        rows.append(
            {
                "paper_id": paper,
                "manuscript_chars": len(draft),
                "delivered_chars": len(delivered),
                "discarded_chars": discarded,
                "discarded_fraction": (
                    round(discarded / len(draft), 4) if draft else None
                ),
                "tail_delivered": bool(tail) and tail in delivered,
            }
        )

    any_discarded = any(r["discarded_chars"] > 0 for r in rows)
    compaction = reviewer_compaction_enabled()
    return {
        "compaction_enabled": compaction,
        "max_chars_cap": REVIEWER_MANUSCRIPT_MAX_CHARS,
        "papers": rows,
        "control_is_untruncated": bool(rows) and not any_discarded,
        # Compaction on would make the control a path production never takes.
        "safe_to_measure": not compaction,
        "mean_discarded_fraction": (
            round(statistics.fmean([r["discarded_fraction"] or 0.0 for r in rows]), 4)
            if rows
            else None
        ),
    }


def measure_assembly(
    papers: Iterable[str] = PAPERS,
    state_dir: Path = DEFAULT_STATE_DIR,
) -> dict[str, Any]:
    """Assemble both arms' prompts and measure them. **$0 -- no LLM calls.**

    This is the cost side of the trade, and it is fully determined by string
    assembly, so it does not need to be bought. Two quantities:

    * **assembled input** -- total characters across all three personas' user
      messages, per arm. Scoping sends each persona only its lane, so this falls.
    * **cacheable shared prefix** -- the longest common prefix of the three
      personas' user messages, which is exactly what calls 2 and 3 can bill at
      the cached rate. The manuscript *was* most of that prefix, so scoping
      forfeits most of it.

    Reporting only the first would make scoping look free; only the second would
    make it look purely costly. The dollar outcome depends on both.
    """
    from app.workflows.draft_analysis.nodes import reviewer_panel

    def _assemble(state: dict, scoped: bool) -> list[str]:
        if scoped:
            os.environ[FLAG] = "1"
        else:
            os.environ.pop(FLAG, None)
        try:
            return [
                reviewer_panel.build_reviewer_messages(state, p)[1]["content"]
                for p in PERSONAS
            ]
        finally:
            os.environ.pop(FLAG, None)

    def _common_prefix(strings: list[str]) -> int:
        if not strings:
            return 0
        head = strings[0]
        for other in strings[1:]:
            limit = min(len(head), len(other))
            i = 0
            while i < limit and head[i] == other[i]:
                i += 1
            head = head[:i]
        return len(head)

    rows: list[dict[str, Any]] = []
    for paper in papers:
        fixture = state_dir / paper / f"reviewer_panel_node__{PERSONAS[0]}.json"
        if not fixture.exists():
            continue
        state = json.loads(fixture.read_text())
        row: dict[str, Any] = {"paper_id": paper}
        for arm, scoped in (("off", False), ("on", True)):
            messages = _assemble(state, scoped)
            row[f"{arm}_total_chars"] = sum(len(m) for m in messages)
            row[f"{arm}_prefix_chars"] = _common_prefix(messages)
            row[f"{arm}_per_persona_chars"] = {
                p: len(m) for p, m in zip(PERSONAS, messages)
            }
        rows.append(row)

    off_total = sum(r["off_total_chars"] for r in rows)
    on_total = sum(r["on_total_chars"] for r in rows)
    off_prefix = sum(r["off_prefix_chars"] for r in rows)
    on_prefix = sum(r["on_prefix_chars"] for r in rows)
    return {
        "papers": rows,
        "off_total_chars": off_total,
        "on_total_chars": on_total,
        "input_change": round((on_total - off_total) / off_total, 4) if off_total else None,
        "off_prefix_chars": off_prefix,
        "on_prefix_chars": on_prefix,
        "prefix_surviving_fraction": (
            round(on_prefix / off_prefix, 4) if off_prefix else None
        ),
    }


# ---------------------------------------------------------------------------
# Config identity
# ---------------------------------------------------------------------------

def measure_scoped_coverage(
    papers: Iterable[str] = PAPERS,
    state_dir: Path = DEFAULT_STATE_DIR,
    window: int = 80,
) -> dict[str, Any]:
    """What fraction of the manuscript reaches *at least one* persona. **$0.**

    S1's acceptance criterion is that the union of the scoped blocks covers the
    manuscript: "a section no reviewer sees is a regression". That is a property
    of string assembly, so it is checkable for free -- and it must be checked on
    real manuscripts rather than on a synthetic fixture, because the thing that
    breaks it is the per-persona budget binding on a *large* paper.

    Method: slice the whitespace-normalised manuscript into fixed-width windows
    and ask how many appear somewhere in the concatenated scoped blocks. Windows
    that straddle a section boundary can miss, which biases the estimate
    *downward*; re-running at a smaller ``window`` bounds that error, and on this
    corpus 80 and 40 agree to within ~3 points, so boundary loss is not what
    drives the number.

    The off arm is the reference: it sends the manuscript whole, so its coverage
    is 100% by construction and is not recomputed here.
    """
    from app.workflows.draft_analysis.nodes import reviewer_panel

    rows: list[dict[str, Any]] = []
    for paper in papers:
        fixture = state_dir / paper / f"reviewer_panel_node__{PERSONAS[0]}.json"
        if not fixture.exists():
            continue
        state = json.loads(fixture.read_text())
        draft = state.get("draft_content") or ""
        if not draft:
            continue
        os.environ[FLAG] = "1"
        try:
            blocks = [
                reviewer_panel.build_manuscript_block(state, p) for p in PERSONAS
            ]
        finally:
            os.environ.pop(FLAG, None)

        union = re.sub(r"\s+", " ", " \n ".join(blocks))
        normalized = re.sub(r"\s+", " ", draft)
        windows = [
            normalized[i : i + window]
            for i in range(0, max(0, len(normalized) - window), window)
        ]
        hit = sum(1 for w in windows if w in union)
        rows.append(
            {
                "paper_id": paper,
                "manuscript_chars": len(draft),
                "windows": len(windows),
                "windows_covered": hit,
                "coverage": round(hit / len(windows), 4) if windows else None,
            }
        )

    covered = [r for r in rows if (r["coverage"] or 0) < 0.95]
    return {
        "window": window,
        "papers": rows,
        "min_coverage": min((r["coverage"] for r in rows), default=None),
        # The acceptance criterion, evaluated rather than assumed.
        "coverage_complete": not covered,
        "papers_below_95pct": [r["paper_id"] for r in covered],
    }


def build_config(arm: str, papers: tuple[str, ...], replicates: int, threshold: float) -> dict:
    """Everything that could move a number, including the flag.

    ``flag_value`` is recorded as the runner will actually set it, not as it
    happens to be in the ambient environment, so a record cannot claim an arm it
    did not run.
    """
    if arm not in ARMS:
        raise ValueError(f"unknown arm {arm!r}; expected one of {ARMS}")
    return {
        "harness": "panel_arms",
        "harness_version": HARNESS_VERSION,
        "arm": arm,
        # The flag, spelled out twice on purpose: by name and by value. A record
        # that names the arm but not the flag value cannot be audited later.
        "flag_name": FLAG,
        "flag_value": "1" if arm == "on" else "",
        "node": "reviewer_panel_node",
        "papers": list(papers),
        "personas": list(PERSONAS),
        "replicates": replicates,
        "cos_threshold": threshold,
        "llm": "real",
        "supabase": "local",
        "python": platform.python_version(),
        "platform": f"{platform.system()}-{platform.machine()}",
    }


def config_hash(cfg: dict) -> str:
    blob = json.dumps(cfg, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()[:12]


def assert_arms_separate(cfg_off: dict, cfg_on: dict) -> tuple[str, str]:
    """Refuse to proceed if the two arms share one identity.

    Seven incidents in this project have had the same shape: an identity
    recorded at coarser granularity than the thing it identifies. The two arms
    of this experiment differ *only* by a flag, which makes them the single most
    likely pair in the repo to collide.
    """
    h_off, h_on = config_hash(cfg_off), config_hash(cfg_on)
    if h_off == h_on:
        raise AssertionError(
            f"config hash collision: both arms hash to {h_off}. The flag is not "
            f"part of the identity, so the two arms would be indistinguishable "
            f"in {DEFAULT_SINK.name}. Refusing to run."
        )
    if cfg_off.get("flag_value") == cfg_on.get("flag_value"):
        raise AssertionError(
            "both arms carry the same flag_value; they are the same arm."
        )
    return h_off, h_on


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------

def findings_from_state(result_state: dict, persona: str) -> list[dict[str, Any]]:
    """Reviewer findings from one replayed panel call, tagged with the persona.

    Reuses ``node_eval.extract_node_items`` so a finding is exactly what the
    rest of the harness calls a finding; the persona tag is what makes the
    mechanism check possible.
    """
    from scripts.eval.node_eval import extract_node_items

    items = extract_node_items("reviewer_panel_node", result_state)
    for item in items:
        item["persona"] = persona
    return items


def unverified_quote_rate(items: list[dict[str, Any]], draft_content: str) -> dict[str, Any]:
    """Fraction of anchored findings whose quote is not verbatim in the draft.

    Uses the production oracle (``draft_evidence_gate._is_verbatim``) rather than
    a private reimplementation, so "unverified" here means exactly what it means
    to the shipped evidence gate. Findings with no anchor are excluded from the
    denominator -- they make no quotation claim, so they cannot fabricate one.
    """
    from app.services.draft_evidence_gate import _is_verbatim

    anchored = [i for i in items if (i.get("anchor_text") or "").strip()]
    bad = [i for i in anchored if not _is_verbatim(i["anchor_text"], draft_content)]
    return {
        "anchored": len(anchored),
        "unverified": len(bad),
        "rate": round(len(bad) / len(anchored), 4) if anchored else None,
    }


# ---------------------------------------------------------------------------
# Running an arm
# ---------------------------------------------------------------------------

def _set_flag(arm: str) -> None:
    if arm == "on":
        os.environ[FLAG] = "1"
    else:
        os.environ.pop(FLAG, None)


def run_arm(
    arm: str,
    papers: tuple[str, ...] = PAPERS,
    replicates: int = 2,
    *,
    state_dir: Path = DEFAULT_STATE_DIR,
    replay: Callable[..., dict] | None = None,
    node_func: Callable[[dict], Any] | None = None,
) -> list[dict[str, Any]]:
    """Replay the panel for every (paper, persona) pair, ``replicates`` times.

    A *run* is one full panel over one manuscript -- all three personas. So
    ``len(papers) * replicates`` runs per arm, each costing three LLM calls.

    ``replay`` and ``node_func`` are injection points for the tests; the default
    is the real ``node_eval.replay_once`` against the real node.
    """
    from scripts.eval import node_eval

    replay = replay or node_eval.replay_once
    if node_func is None:
        node_func = node_eval._node_registry()["reviewer_panel_node"]

    records: list[dict[str, Any]] = []
    for rep in range(replicates):
        for paper in papers:
            for persona in PERSONAS:
                _set_flag(arm)
                # ``replay_once`` returns a measurement record but discards the
                # resulting state, and the findings live in that state. Rather
                # than fork the replay (which would put the measured code path
                # out of sync with the rest of the harness), wrap the node so
                # the result is captured on the way past.
                captured: dict[str, Any] = {}

                def _capturing(state: dict, _f=node_func, _c=captured):
                    result = _f(state)
                    if inspect.isawaitable(result):

                        async def _await():
                            value = await result
                            _c["result"] = value
                            return value

                        return _await()
                    _c["result"] = result
                    return result

                record = replay(
                    "reviewer_panel_node",
                    paper,
                    _capturing,
                    reviewer_type=persona,
                    state_dir=state_dir,
                    # Scoring is pooled per arm below, not per replay: pooling
                    # first dedupes finding texts across replicates and cuts the
                    # matcher's confirmation calls substantially.
                    with_metric=False,
                    repeat_index=rep,
                )
                record["arm"] = arm
                record["persona"] = persona
                record["flag_value"] = os.environ.get(FLAG, "")

                findings: list[dict[str, Any]] = []
                if record.get("status") == "ok" and isinstance(captured.get("result"), dict):
                    fixture = state_dir / paper / f"reviewer_panel_node__{persona}.json"
                    base = json.loads(fixture.read_text()) if fixture.exists() else {}
                    merged = node_eval._merge_state(base, captured["result"])
                    findings = findings_from_state(merged, persona)
                record["_findings"] = findings
                record["n_findings"] = len(findings)
                records.append(record)
    return records


# ---------------------------------------------------------------------------
# Scoring an arm
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

    Mirrors ``ceiling.score_ceiling.run`` -- same label set, same taxonomy, same
    matcher, ``COS_THRESHOLD`` monkeypatched the same way -- but scores a live
    arm's findings instead of the recorded corpus. Reports against *both* the 76
    addressable units and all 212, always; a recall quoted against one
    denominator without the other is not comparable to anything.

    ``units`` is an injection seam. ``load_units()`` reconstructs the label set
    by atomizing the OpenReview gold, which falls through to a live LLM call on
    a cache miss -- fine inside a scoring run, not fine inside a unit test.
    Passing ``units`` keeps the test suite hermetic without forking the loader.
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
    # unit_id -> the personas that reached it, for the mechanism check
    matched_by_persona: dict[str, set[str]] = {p: set() for p in PERSONAS}

    original = match_mod.COS_THRESHOLD
    match_mod.COS_THRESHOLD = threshold
    stats_total: collections.Counter = collections.Counter()
    try:
        for paper, findings in sorted(findings_by_paper.items()):
            targets = [u for u in units if u["draft_id"] == paper]
            if not findings or not targets:
                continue
            # Dedupe by text, keeping the personas that produced each text.
            by_text: dict[str, set[str]] = {}
            for f in findings:
                text = (f.get("text") or "").strip()
                if text:
                    by_text.setdefault(text, set()).add(f.get("persona") or "unknown")
            items = [
                {"id": f"{paper}-{i:04d}", "text": text}
                for i, text in enumerate(sorted(by_text))
            ]
            id_to_text = {it["id"]: it["text"] for it in items}
            stats: dict[str, int] = {}
            kwargs = dict(match_kwargs or {})
            # cache_dir has a non-None default bound at def time in match.match;
            # passing None explicitly would break it.
            if cache_dir is not None:
                kwargs["cache_dir"] = cache_dir
            for m in match_mod.match(items, targets, stats=stats, **kwargs):
                if not m.get("confirmed"):
                    continue
                unit_id = str(m["unit_id"])
                matched.add(unit_id)
                # The matcher names the finding side ``noesis_id``.
                for persona in by_text.get(id_to_text.get(str(m.get("noesis_id")), ""), ()):
                    if persona in matched_by_persona:
                        matched_by_persona[persona].add(unit_id)
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
        # Both denominators, always.
        "units_matched_all_212": banded(len(matched)),
        "units_matched_addressable_76": banded(len(addr_hits)),
        "recall_all_212": round(len(matched) / len(units), 4) if units else None,
        "recall_addressable": (
            round(len(addr_hits) / len(addressable), 4) if addressable else None
        ),
        "severity_recall_all_212": (
            round(_weight(matched) / total_weight, 4) if total_weight else None
        ),
        "severity_recall_addressable": (
            round(_weight(addr_hits) / addr_weight, 4) if addr_weight else None
        ),
        "units_matched_by_persona": {
            p: banded(len(ids & addressable)) for p, ids in matched_by_persona.items()
        },
        "match_stats": dict(stats_total),
    }


# ---------------------------------------------------------------------------
# Usage / cost
# ---------------------------------------------------------------------------

def summarize_usage(records: list[dict[str, Any]], n_runs: int) -> dict[str, Any]:
    """Input tokens, cache hit rate and absolute cost for one arm.

    The cache hit rate is ``cached_tokens / prompt_tokens`` summed over the
    arm's calls, taken from the API's own ``usage`` block via ``llm_budget``. If
    the provider ever stops reporting ``cached_tokens``, that shows up here as
    ``cache_hit_rate: null`` with ``cache_reported: false`` rather than as a
    silent zero -- an unreported cache is not an empty cache, and the difference
    is the entire cost side of this experiment.
    """
    usages = [r.get("usage") or {} for r in records]
    prompt = sum(int(u.get("prompt_tokens") or 0) for u in usages)
    cached = sum(int(u.get("cached_tokens") or 0) for u in usages)
    completion = sum(int(u.get("completion_tokens") or 0) for u in usages)
    calls = sum(int(u.get("calls") or 0) for u in usages)
    node_usd = sum(float(u.get("estimated_usd") or 0.0) for u in usages)
    match_usd = sum(
        float((r.get("match_usage") or {}).get("estimated_usd") or 0.0) for r in records
    )
    unpriced = sum(int(u.get("unpriced_calls") or 0) for u in usages)
    cache_reported = any("cached_tokens" in u for u in usages)

    return {
        "n_runs": n_runs,
        "llm_calls": calls,
        "unpriced_calls": unpriced,
        "input_tokens_total": prompt,
        "input_tokens_per_run": round(prompt / n_runs, 1) if n_runs else None,
        "completion_tokens_total": completion,
        "cached_tokens_total": cached,
        "cache_reported": cache_reported,
        "cache_hit_rate": (
            round(cached / prompt, 4) if (prompt and cache_reported) else None
        ),
        "node_usd": round(node_usd, 6),
        "match_usd": round(match_usd, 6),
        "total_usd": round(node_usd + match_usd, 6),
        "usd_per_run": round((node_usd + match_usd) / n_runs, 6) if n_runs else None,
    }



def _summarize_budget(new_events: list[Any]) -> dict[str, Any]:
    """Fold a slice of ``llm_budget`` events into a usage dict.

    A local fold rather than ``node_eval._summarize_events`` because that one
    also builds per-label and per-model breakdowns this record does not use.
    """
    prompt = sum(int(getattr(e, "prompt_tokens", 0) or 0) for e in new_events)
    cached = sum(int(getattr(e, "cached_tokens", 0) or 0) for e in new_events)
    usd = sum(float(getattr(e, "estimated_usd", 0.0) or 0.0) for e in new_events)
    return {
        "calls": len(new_events),
        "prompt_tokens": prompt,
        "cached_tokens": cached,
        "completion_tokens": sum(
            int(getattr(e, "completion_tokens", 0) or 0) for e in new_events
        ),
        "estimated_usd": round(usd, 6),
    }


def per_persona_counts(records: list[dict[str, Any]], findings: list[dict[str, Any]]) -> dict[str, Any]:
    """Raw finding counts per persona -- the mechanism check's numerator.

    Reported prominently, never as an appendix. Two readings to rule out:

    * a **uniform** rise across all three personas is not context isolation --
      isolation acts on personas differently by construction, so a flat rise
      points at run-to-run variance or at something else in the prompt;
    * **A up, D down** is the section map moving text between lanes, not
      isolation working. Reviewer D's duties are cross-cutting (terminology
      *throughout*, argument structure, reporting completeness), so D loses
      context under any sectional map and would fall whether or not isolation
      helps anybody.
    """
    counts = collections.Counter(f.get("persona") for f in findings)
    ok = collections.Counter(
        r.get("persona") for r in records if r.get("status") == "ok"
    )
    return {
        p: {
            "findings": counts.get(p, 0),
            "calls_ok": ok.get(p, 0),
            "findings_per_call": (
                round(counts.get(p, 0) / ok[p], 3) if ok.get(p) else None
            ),
        }
        for p in PERSONAS
    }


# ---------------------------------------------------------------------------
# Sink
# ---------------------------------------------------------------------------

def append_record(record: dict[str, Any], path: Path = DEFAULT_SINK) -> None:
    """Append-only JSONL. Open mode is ``"a"`` and nothing else, ever."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")


def _report_spend() -> None:
    """Print this process's spend to 4 decimals. ``llm_budget`` is process-local,
    so a number not printed before exit is unrecoverable afterwards."""
    try:
        from app.core.llm_budget import total_spend_usd

        print(f"[spend] ${total_spend_usd():.4f}", flush=True)
    except Exception:  # pragma: no cover - reporting must never fail a run
        pass


atexit.register(_report_spend)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument(
        "--arm",
        action="append",
        choices=list(ARMS),
        help="Arm to run; repeat for both. Default: both, interleaved.",
    )
    p.add_argument("--replicates", type=int, default=2, help="Replicates per paper per arm (default 2 -> n=6 runs).")
    p.add_argument("--paper", action="append", default=None, help="Paper id; repeatable. Default: the 3 labelled papers.")
    p.add_argument("--threshold", type=float, default=None, help="Matcher cosine threshold. Default: match.COS_THRESHOLD (0.44 calibrated).")
    p.add_argument("--sink", type=Path, default=DEFAULT_SINK)
    p.add_argument("--state-dir", type=Path, default=DEFAULT_STATE_DIR)
    p.add_argument("--audit-only", action="store_true", help="Run the $0 control-arm audit and assembly measurement, then exit. Makes no LLM calls.")
    p.add_argument("--yes", action="store_true", help="Confirm real spend.")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    papers = tuple(args.paper or PAPERS)
    arms = tuple(args.arm or ARMS)

    # The harness runs on the host and does not inherit compose's environment.
    # Never overrides an already-set variable, so an exported spend ceiling or
    # kill switch still wins over whatever sits in the file.
    from scripts.eval.env import describe_credential, load_backend_env

    load_backend_env()
    print(describe_credential("OPENAI_API_KEY"))

    # ---- 1. The free measurements, always, first. -------------------------
    control = audit_control_arm(papers, state_dir=args.state_dir)
    print("=" * 72)
    print("CONTROL ARM ($0 -- no LLM calls)")
    print("=" * 72)
    print(f"  compaction_enabled : {control['compaction_enabled']} (cap={control['max_chars_cap']})")
    for row in control["papers"]:
        print(
            f"  {row['paper_id']}: manuscript {row['manuscript_chars']:,} chars -> "
            f"reviewer sees {row['delivered_chars']:,} "
            f"({row['discarded_chars']:,} discarded, "
            f"{100 * (row['discarded_fraction'] or 0):.1f}%); "
            f"tail delivered: {row['tail_delivered']}"
        )
    print(f"  control is full manuscript : {control['control_is_untruncated']}")
    if control["control_is_untruncated"]:
        print(
            "\n  Nothing is truncated on the shipped path. The scope doc's '24k\n"
            "  head-truncation discards ~27%, always the tail' describes the\n"
            "  compaction path, which is off by default and set nowhere in this\n"
            "  repo. The control arm is three reviewers x the FULL manuscript,\n"
            "  and the hypothesis under test is context isolation, not the\n"
            "  recovery of removed text.\n"
        )

    assembly = None
    if flag_is_implemented(
        __import__(
            "app.workflows.draft_analysis.nodes.reviewer_panel",
            fromlist=["x"],
        )
    ):
        assembly = measure_assembly(papers, state_dir=args.state_dir)
        print("=" * 72)
        print("ASSEMBLY -- the cost side, fully determined, $0")
        print("=" * 72)
        print(f"  assembled input  off : {assembly['off_total_chars']:,} chars")
        print(f"  assembled input  on  : {assembly['on_total_chars']:,} chars "
              f"({100 * (assembly['input_change'] or 0):+.1f}%)")
        print(f"  cacheable prefix off : {assembly['off_prefix_chars']:,} chars")
        print(f"  cacheable prefix on  : {assembly['on_prefix_chars']:,} chars "
              f"({100 * (assembly['prefix_surviving_fraction'] or 0):.1f}% surviving)")

        coverage = measure_scoped_coverage(papers, state_dir=args.state_dir)
        print("=" * 72)
        print("SCOPED COVERAGE -- does every span still reach some reviewer? $0")
        print("=" * 72)
        for row in coverage["papers"]:
            print(
                f"  {row['paper_id']}: {row['manuscript_chars']:,} chars -> "
                f"{100 * (row['coverage'] or 0):.1f}% of the manuscript reaches "
                f"at least one persona"
            )
        print(f"  coverage_complete : {coverage['coverage_complete']}")
        if not coverage["coverage_complete"]:
            print(
                "\n  REGRESSION against the build's own acceptance criterion\n"
                "  ('the union of scoped sections covers the manuscript'). The\n"
                "  per-persona budget binds on manuscripts larger than it, so on\n"
                "  those papers scoping introduces exactly the text loss this\n"
                "  build set out to remove. The off arm sends 100% by construction.\n"
            )
        assembly["coverage"] = coverage

    if args.audit_only:
        print(json.dumps({"control": control, "assembly": assembly}, indent=1))
        return 0

    if not control["safe_to_measure"]:
        print(
            "\nRefusing to spend: DRAFT_REVIEWER_COMPACT_MANUSCRIPT is on, so the\n"
            "'off' arm would be a path production never takes and the delta\n"
            "against it would be uninterpretable. Unset it and re-run."
        )
        return 2

    # ---- 2. The flag must exist before the 'on' arm is meaningful. --------
    if "on" in arms:
        require_flag()

    from scripts.eval import match as match_mod

    threshold = args.threshold if args.threshold is not None else match_mod.COS_THRESHOLD

    configs = {a: build_config(a, papers, args.replicates, threshold) for a in ARMS}
    h_off, h_on = assert_arms_separate(configs["off"], configs["on"])
    print(f"\nconfig hashes: off={h_off} on={h_on} (distinct: {h_off != h_on})")

    if not args.yes:
        n_runs = len(papers) * args.replicates
        print(
            f"\nWould run {len(arms)} arm(s) x {n_runs} runs x {len(PERSONAS)} personas "
            f"= {len(arms) * n_runs * len(PERSONAS)} LLM calls, plus matcher spend.\n"
            f"Re-run with --yes to confirm real spend."
        )
        return 0

    # ---- 3. The arms, interleaved. ---------------------------------------
    from scripts.eval import node_eval

    node_func = node_eval._node_registry()["reviewer_panel_node"]
    all_records: dict[str, list[dict[str, Any]]] = {a: [] for a in arms}
    for arm in arms:
        all_records[arm] = run_arm(
            arm,
            papers,
            args.replicates,
            state_dir=args.state_dir,
            node_func=node_func,
        )

    # ---- 4. Score, summarize, append. ------------------------------------
    started = datetime.now(timezone.utc).isoformat()
    for arm in arms:
        records = all_records[arm]
        findings: list[dict[str, Any]] = []
        by_paper: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
        quotes = {"anchored": 0, "unverified": 0}
        for rec in records:
            state_file = Path(rec["state_fixture"])
            if rec.get("status") != "ok" or not state_file.exists():
                continue
            draft = json.loads(state_file.read_text()).get("draft_content") or ""
            items = rec.get("_findings") or []
            findings.extend(items)
            by_paper[rec["paper_id"]].extend(items)
            q = unverified_quote_rate(items, draft)
            quotes["anchored"] += q["anchored"]
            quotes["unverified"] += q["unverified"]

        n_runs = len(papers) * args.replicates
        record = {
            "record_type": "panel_arm",
            "timestamp": started,
            "arm": arm,
            "flag_name": FLAG,
            "flag_value": configs[arm]["flag_value"],
            "config": configs[arm],
            "config_hash": config_hash(configs[arm]),
            "control_audit": control,
            "assembly": assembly,
            "n_runs": n_runs,
            "n_calls": len(records),
            "n_errors": sum(1 for r in records if r.get("status") != "ok"),
            "usage": summarize_usage(records, n_runs),
            "per_persona": per_persona_counts(records, findings),
            "unverified_quotes": {
                **quotes,
                "rate": (
                    round(quotes["unverified"] / quotes["anchored"], 4)
                    if quotes["anchored"]
                    else None
                ),
            },
        }
        # Scoring makes its own paid calls, and they happen HERE -- outside
        # replay_once, so they land in no record's ``match_usage``. Slice the
        # budget event log around the call to capture them; without this the
        # record reports match_usd 0.0 while the matcher is making hundreds of
        # live confirmations, which is a confidently wrong zero rather than a
        # missing number.
        from app.core.llm_budget import events as budget_events

        before = len(budget_events())
        try:
            record["score"] = score_arm(dict(by_paper), threshold)
        except Exception as exc:
            record["score"] = None
            record["score_error"] = f"{type(exc).__name__}: {exc}"[:500]
        finally:
            scoring = _summarize_budget(budget_events()[before:])
            record["scoring_usage"] = scoring
            # Production cost and measurement cost are different questions and
            # are never added together: the product runs the panel, never the
            # matcher. ``usd_per_run`` stays node-only for that reason.
            record["usage"]["scoring_usd"] = scoring["estimated_usd"]
        usage = record["usage"]
        verified = (
            (record["score"] or {}).get("units_matched_addressable_76", {}).get("value")
        )
        # Node cost only. The matcher is measurement apparatus, not something
        # a production run pays for, so folding it in would overstate what a
        # verified finding costs to produce.
        record["usd_per_verified_finding"] = (
            round(usage["node_usd"] / verified, 6) if verified else None
        )
        append_record(record, args.sink)
        print(json.dumps(record, indent=1, sort_keys=True))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

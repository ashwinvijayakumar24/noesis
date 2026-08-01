"""Deterministic loaders for the ceiling study's two corpora.

Two things have to be reconstructible at $0 for any of this to be auditable:

1. **The 212 label units.** Rebuilt from Noesis's own OpenReview gold plus the
   warm ``cache/atomize`` entries. This reproduces the head-to-head label set
   exactly -- 79 / 72 / 61 units, total severity weight 85.4, matching
   ``HEADTOHEAD.md`` §1 -- and every unit text is present in the head-to-head
   embedding cache, which is independent proof the reconstruction is the same
   label set and not a lookalike.

2. **A finding corpus.** This one is *not* byte-exact to the head-to-head arms,
   and that is a finding in itself: ``eval/results/headtohead.jsonl`` persists
   metrics but never the finding texts, and the ``--detail-path`` dump was not
   written on the recorded run. Of the 56 agent and 99 DAG findings behind the
   published recall numbers, **0 and 2** respectively can be recovered from any
   committed artefact (probe: hash each candidate text with
   ``match._embedding_cache_key`` and test membership of
   ``eval/results/.matchcache/embed``). So the matcher calibration here runs on
   a *re-derived* corpus of the same two systems' output on the same three
   manuscripts: the DAG's canonical revision tasks and coverage gaps from
   Noesis's committed eval exports, and the agent's findings from
   ``eval/results/matched.trace.jsonl``. The threshold curve is a property of
   the matcher and the text distributions, not of which particular replicate
   produced them.
"""

from __future__ import annotations

import glob
import json
import os
import sys
from pathlib import Path

CEILING_DIR = Path(__file__).resolve().parent
EVAL_DIR = CEILING_DIR.parent
REPO_ROOT = EVAL_DIR.parent.parent
REVIEWER_AGENT = REPO_ROOT.parent.parent / "reviewer-agent"

DRAFT_IDS = ("10eQ4Cfh8p", "kKRbAY4CXv", "cXs5md5wAq")
GOLD_DIR = EVAL_DIR / "openreview" / "ICLR.cc_2024_Conference"

for _p in (str(REPO_ROOT), str(REPO_ROOT / "services" / "backend")):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def load_units() -> list[dict]:
    """The 212 head-to-head label units, in a stable order."""
    from scripts.eval.atomize_reviews import atomize_paper

    units: list[dict] = []
    for draft_id in DRAFT_IDS:
        gold = json.loads((GOLD_DIR / f"{draft_id}.json").read_text())
        for unit in atomize_paper(gold):
            unit["draft_id"] = draft_id
            units.append(unit)
    return units


def load_findings() -> list[dict]:
    """The re-derived finding corpus. See the module docstring for its status."""
    from scripts.eval import judge_openreview as jo

    findings: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for draft_id in DRAFT_IDS:
        for path in sorted(glob.glob(str(EVAL_DIR / "results" / f"{draft_id}__*.json"))):
            export = json.loads(Path(path).read_text())
            for task in export.get("durable_revision_tasks") or []:
                text = jo._critique_text(task)
                if text and (draft_id, text) not in seen:
                    seen.add((draft_id, text))
                    findings.append(
                        {
                            "system": "dag",
                            "draft_id": draft_id,
                            "text": text,
                            "source": "revision_task",
                            "origin": os.path.basename(path),
                        }
                    )
            for gap in export.get("coverage_gaps") or []:
                text = gap.get("description") or gap.get("reasoning")
                text = str(text) if text else ""
                if text and (draft_id, text) not in seen:
                    seen.add((draft_id, text))
                    findings.append(
                        {
                            "system": "dag",
                            "draft_id": draft_id,
                            "text": text,
                            "source": "coverage_gap",
                            "origin": os.path.basename(path),
                        }
                    )

    trace = REVIEWER_AGENT / "eval" / "results" / "matched.trace.jsonl"
    if trace.exists():
        for line in trace.read_text().splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            draft_id = row["draft_id"]
            for text in row.get("findings") or []:
                if (draft_id, text) in seen:
                    continue
                seen.add((draft_id, text))
                findings.append(
                    {
                        "system": "agent",
                        "draft_id": draft_id,
                        "text": text,
                        "source": "agent_finding",
                        "origin": "matched.trace.jsonl",
                    }
                )

    findings.sort(key=lambda f: (f["system"], f["draft_id"], f["text"]))
    for idx, finding in enumerate(findings):
        finding["finding_id"] = f"{finding['system']}-{idx:03d}"
    return findings

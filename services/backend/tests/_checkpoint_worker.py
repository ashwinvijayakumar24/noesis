"""
Out-of-process driver for the durable-checkpoint tests and benchmark.

WHY THIS IS A SEPARATE PROCESS AND NOT A FIXTURE
------------------------------------------------
``tests/test_checkpoint_resume.py`` already proves in-process recovery: raise
inside a node, resume in the same interpreter, assert the completed prefix is not
re-executed. That is necessary but it is *not* the property the harness's approval
gate needs. An in-process exception leaves the Python objects, the LangGraph
``Pregel`` loop and the checkpointer's own connection alive; a resume that quietly
leaned on any of them would still pass. The claim being made is stronger:

    a run killed with SIGKILL -- no unwinding, no ``finally``, no flush, no
    graceful shutdown of any kind -- resumes in a **different interpreter** from
    what is physically in Postgres.

Only a real process boundary can test that, so this module exists to be spawned.

The underscore prefix keeps pytest from collecting it: it is a script, not a test.

WHAT IT RUNS
------------
The **real** 18-node topology from ``create_draft_analysis_workflow`` -- real
conditional edges, real ``Send`` fan-out to the three reviewer personas, real
``_traced_node`` wrappers -- with every node *body* replaced by a counting stub.
Stubbing the bodies is deliberate: the property under test is the checkpoint
machinery, and real bodies would make the test cost money, need Supabase, GROBID
and OpenAI, and take minutes. Stubbing the *topology* instead would have been the
mistake, because the fan-out and the conditional edges are exactly where a
checkpointer's task bookkeeping is most likely to be wrong.

THE LEDGER
----------
Every stub appends one line to ``--ledger`` and ``fsync``s it before returning.
fsync is the whole point: SIGKILL discards userspace buffers, so a ledger written
through normal buffered I/O would lose the last few entries and make the resume
look better than it was. The ledger is append-only across both processes, so the
parent can count executions per node across the death boundary.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any

# Allow ``python3 tests/_checkpoint_worker.py`` from the backend root as well as
# from an arbitrary cwd, since the test spawns it by absolute path.
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


#: A sentinel with no legitimate reason to appear in a checkpoint row. The
#: privacy assertions grep the raw BYTEA for it.
MANUSCRIPT = "SECRET_UNPUBLISHED_MANUSCRIPT_BODY_TEXT_DO_NOT_PERSIST"

#: The 18 nodes in ``create_draft_analysis_workflow``, in execution order, paired
#: with the module-level name in ``graph.py`` that each is registered under.
#: Order matters: the benchmark treats index i as "crashed at the i-th node".
NODE_ORDER: list[tuple[str, str]] = [
    ("extract_structure", "_extract_structure_node_with_progress"),
    ("profile_manuscript", "_manuscript_profile_node_with_progress"),
    ("extract_references", "_extract_references_node_with_progress"),
    ("extract_claims", "_extract_claims_node_with_progress"),
    ("categorize_claims", "_categorize_claims_node_with_progress"),
    ("verify_citations", "_verify_citations_node_with_progress"),
    ("search_literature", "_literature_search_node_with_progress"),
    ("map_citations", "_citation_mapping_node_with_progress"),
    ("detect_gaps", "_detect_gaps_node_with_progress"),
    ("discover_external_sources", "_external_source_discovery_node_with_progress"),
    ("citation_judge_node", "_citation_judge_node_with_progress"),
    ("run_quality_diagnostics", "_diagnostic_findings_node_with_progress"),
    ("structural_checks", "_structural_checks_node_with_progress"),
    ("editor_pass_node", "_editor_pass_node_with_progress"),
    ("reviewer_panel_node", "_reviewer_panel_node_with_progress"),
    ("reviewer_judge_node", "_reviewer_judge_node_with_progress"),
    ("meta_reviewer_node", "_meta_reviewer_node_with_progress"),
    ("synthesize_report", "_synthesize_report_node_with_progress"),
]

NODE_NAMES = [name for name, _ in NODE_ORDER]


def _append_ledger(path: str, record: dict[str, Any]) -> None:
    """Append one durable line. Buffered I/O would be lost to SIGKILL."""
    with open(path, "a") as fh:
        fh.write(json.dumps(record) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def _stub_returns(node: str, state: dict) -> dict:
    """The minimum state delta each node must produce to keep routing intact.

    Only three nodes matter to the routers:

    * ``editor_pass_node`` must set ``proceed_to_review`` or the graph
      desk-rejects straight to synthesis and the fan-out is never exercised;
    * ``reviewer_panel_node`` writes into the reducer-backed ``reviewer_outputs``
      channel, which is the one channel where the fan-in ordering could go wrong;
    * every node bumps ``progress_percentage``, which is what a resumed run reads
      back to prove the prefix's writes actually survived.
    """
    if node == "reviewer_panel_node":
        # Only the reducer-backed channel. The three fan-out branches run in one
        # superstep, so writing any non-Annotated channel from here is an
        # InvalidUpdateError -- a property of the graph, not of checkpointing.
        return {
            "reviewer_outputs": [
                {"reviewer_type": state.get("reviewer_type") or "unknown", "feedback": []}
            ]
        }
    idx = NODE_NAMES.index(node) if node in NODE_NAMES else 0
    delta: dict[str, Any] = {
        "current_step": node,
        "progress_percentage": int(round(100 * (idx + 1) / len(NODE_NAMES))),
    }
    if node == "editor_pass_node":
        delta["editor_decision"] = {"proceed_to_review": True}
    return delta


def _install_stubs(
    ledger: str,
    kill_at: str | None,
    fail_at: str | None,
    node_delay: float,
) -> None:
    """Replace the 18 node bodies in ``graph.py`` with counting stubs.

    Patching the module globals rather than the compiled graph is what keeps the
    real ``add_node``/``_traced_node`` wiring in play -- the graph is built
    afterwards and picks the stubs up by name.
    """
    from app.workflows.draft_analysis import graph as graph_module

    def make(node: str):
        async def stub(state: dict) -> dict:
            # The manuscript is never persisted, so a node touching it proves
            # rehydration worked. If it were broken this raises rather than
            # silently analysing an empty string.
            assert state.get("draft_content") == MANUSCRIPT, (
                f"{node} saw a manuscript of len "
                f"{len(state.get('draft_content') or '')} -- rehydration failed"
            )
            _append_ledger(
                ledger,
                {
                    "node": node,
                    "pid": os.getpid(),
                    "reviewer_type": state.get("reviewer_type"),
                    "t": time.time(),
                },
            )
            # Stand-in for the node's real work. It is not cosmetic: LangGraph
            # SUBMITS ``aput`` concurrently rather than awaiting it inline, so a
            # node that returns in microseconds can finish several supersteps
            # ahead of the checkpoint writer. A crash then loses the checkpoints
            # that had not landed. Real nodes take seconds (see the measured
            # per-node wall times in scripts/eval/CHECKPOINT_RESUME.md) against a
            # single-digit-millisecond write, so the write always wins -- this
            # knob is how that regime gets reproduced deterministically.
            if node_delay:
                await asyncio.sleep(node_delay)
            if kill_at == node:
                # SIGKILL, not sys.exit and not an exception: nothing runs after
                # this line. No atexit, no finally, no connection close, no flush.
                os.kill(os.getpid(), signal.SIGKILL)
            if fail_at == node:
                raise RuntimeError(f"induced failure in {node}")
            return _stub_returns(node, state)

        stub.__name__ = f"stub_{node}"
        return stub

    for node, attr in NODE_ORDER:
        setattr(graph_module, attr, make(node))


def _initial_state(thread_id: str) -> dict:
    return {
        "draft_id": thread_id,
        "project_id": "bench-project",
        "user_id": None,
        "draft_content": MANUSCRIPT,
        "paper_type": "journal_article",
        "citation_style": "auto",
        "analysis": {},
        "parse_artifact": {},
        "parser_quality": {},
        "forced_route": "",
        "stage_only": True,
        "current_step": "Starting",
        "progress_percentage": 0,
        "search_iterations": 0,
        "max_search_iterations": 1,
        "reviewer_outputs": [],
    }


async def _amain(args) -> int:
    # Set before importing the graph: the preliminary publish-gate halt would
    # otherwise route around the reviewer fan-out for a stub state that has no
    # anchors, and the fan-out is the interesting half of the topology.
    os.environ.setdefault("EVAL_DISABLE_PRE_REVIEWER_HALT", "1")

    from app.workflows.draft_analysis.checkpoints import (
        MANUSCRIPT_CHANNELS,
        NoesisPostgresSaver,
    )
    from app.workflows.draft_analysis.graph import create_draft_analysis_workflow

    _install_stubs(args.ledger, args.kill_at, args.fail_at, args.node_delay)

    saver = NoesisPostgresSaver(
        args.dsn,
        rehydrate={ch: MANUSCRIPT if ch == "draft_content" else {} for ch in MANUSCRIPT_CHANNELS},
    )
    config = {"configurable": {"thread_id": args.thread}}
    try:
        workflow = create_draft_analysis_workflow(checkpointer=saver)
        started = time.time()
        if args.mode == "run":
            final = await workflow.ainvoke(_initial_state(args.thread), config=config)
        else:
            # ``None`` is what tells LangGraph "continue this thread from its
            # checkpoint". Passing a state dict instead is what the old
            # implementation did, and is why it re-ran everything.
            final = await workflow.ainvoke(None, config=config)
        elapsed = time.time() - started
        print(
            json.dumps(
                {
                    "ok": True,
                    "mode": args.mode,
                    "wall_seconds": round(elapsed, 4),
                    "progress_percentage": final.get("progress_percentage"),
                    "reviewer_outputs": len(final.get("reviewer_outputs") or []),
                }
            )
        )
        return 0
    except Exception as exc:  # noqa: BLE001 -- the parent needs the reason verbatim
        print(json.dumps({"ok": False, "mode": args.mode, "error": repr(exc)}))
        return 3
    finally:
        saver.close()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dsn", required=True)
    p.add_argument("--thread", required=True)
    p.add_argument("--ledger", required=True)
    p.add_argument("--mode", choices=["run", "resume"], default="run")
    p.add_argument(
        "--kill-at",
        default=None,
        help=(
            "SIGKILL from inside this node. Useful for measuring the uncontrolled "
            "case; the tests instead kill from the PARENT once a chosen number of "
            "checkpoints is durable, which is timing-independent."
        ),
    )
    p.add_argument("--fail-at", default=None, help="raise inside this node instead")
    p.add_argument(
        "--node-delay",
        type=float,
        default=0.0,
        help="seconds each stub sleeps, standing in for the node's real work",
    )
    args = p.parse_args(argv)
    return asyncio.run(_amain(args))


if __name__ == "__main__":
    raise SystemExit(main())

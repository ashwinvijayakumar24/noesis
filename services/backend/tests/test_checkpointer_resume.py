"""
Cross-process durability tests for the LangGraph checkpointer.

``test_checkpoint_resume.py`` covers the in-process story: raise inside a node,
resume in the same interpreter, assert the completed prefix is not re-executed.
This file exists because that is not sufficient evidence for the claim the
checkpointer is being built to support -- a durable human-in-the-loop approval
gate. An in-process recovery leaves the interpreter, the ``Pregel`` loop, the
compiled graph and the saver's own psycopg2 connection alive; a resume that
quietly depended on any of them would still pass.

So every test here spans a real process boundary:

* the run is a **subprocess**, killed with **SIGKILL from the parent** -- no
  unwinding, no ``finally``, no ``atexit``, no flush, no cooperation of any kind
  from the process being killed;
* the resume is a **second, fresh subprocess** that shares nothing with the first
  except the rows in Postgres.

WHY THE PARENT PICKS THE MOMENT, AND WHY THAT IS NOT THE TEST CHEATING
----------------------------------------------------------------------
LangGraph does not await ``aput`` inline -- it submits it to a background
executor and chains it on the previous write (``langgraph/pregel/loop.py:705``).
"The node returned" and "the checkpoint is on disk" are therefore two different
events, and a crash in between correctly loses that superstep.

That makes wall-clock a nuisance variable: on this machine a commit against
Dockerised Postgres has a median of ~42 ms and a p90 of ~149 ms, so stub nodes
returning in milliseconds outrun the writer and a fixed sleep would only ever be
tuned until the flake stopped. Instead the parent watches ``noesis_lg_checkpoints``
and kills the child once a chosen number of checkpoints is **durable**. The
assertions are then stated against what is actually on disk -- "no node at or
before the last durable step re-executes" -- which is timing-independent by
construction. The uncontrolled variant is measured, not hidden: see the
durability-lag sweep in ``scripts/eval/checkpoint_resume_bench.py``.

The graph under test is the real 18-node ``create_draft_analysis_workflow``
topology -- real conditional edges, real 3-way ``Send`` fan-out, real
``_traced_node`` wrappers -- with stubbed node bodies (see
``tests/_checkpoint_worker.py`` for why that split is the right one).

Requires a local Postgres. Skips cleanly when there is none, so the suite stays
runnable without Docker.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from collections import Counter
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

WORKER = BACKEND_ROOT / "tests" / "_checkpoint_worker.py"
MIGRATION = BACKEND_ROOT / "migrations" / "039_langgraph_checkpoints.sql"

from tests._checkpoint_worker import MANUSCRIPT, NODE_NAMES  # noqa: E402

#: Candidate local databases, in preference order. Neither is production; the
#: remote Supabase project is deliberately unreachable from here and must stay so.
#: The first that answers wins.
CANDIDATE_DSNS = [
    os.environ.get("NOESIS_TEST_CHECKPOINT_DSN"),
    "postgresql://postgres:postgres@127.0.0.1:54322/postgres",
    "postgresql://noesis_local:noesis_local_dev_only@localhost:5433/noesis_eval",
]

#: Stands in for the work a real node does (measured: 3-18 s for the six nodes
#: that call an LLM). Kept small because the crash point is chosen by durable
#: checkpoint count, not by racing this sleep against the writer.
NODE_DELAY = 0.15


def _resolve_dsn() -> str | None:
    import psycopg2

    for dsn in CANDIDATE_DSNS:
        if not dsn:
            continue
        try:
            conn = psycopg2.connect(dsn, connect_timeout=3)
        except Exception:
            continue
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT to_regclass('public.noesis_lg_checkpoints')")
                if cur.fetchone()[0] is None:
                    # Bootstrap from the checked-in migration so a fresh database
                    # is a clean run rather than a missing-relation error.
                    cur.execute(MIGRATION.read_text())
                    conn.commit()
            return dsn
        except Exception:
            continue
        finally:
            conn.close()
    return None


DSN = _resolve_dsn()

requires_postgres = pytest.mark.skipif(
    DSN is None,
    reason=(
        "no local Postgres reachable on 127.0.0.1:54322 (supabase start) or "
        "localhost:5433 (infra pgvector)"
    ),
)


# ---------------------------------------------------------------------------
# Driving the worker
# ---------------------------------------------------------------------------


def _cmd(thread: str, ledger: Path, mode: str, **flags) -> list[str]:
    cmd = [
        sys.executable,
        str(WORKER),
        "--dsn", DSN,
        "--thread", thread,
        "--ledger", str(ledger),
        "--mode", mode,
        "--node-delay", str(NODE_DELAY),
    ]
    for key, value in flags.items():
        if value is not None:
            cmd += [f"--{key.replace('_', '-')}", str(value)]
    return cmd


def _run_worker(thread: str, ledger: Path, mode: str, **flags):
    return subprocess.run(
        _cmd(thread, ledger, mode, **flags),
        capture_output=True,
        text=True,
        cwd=str(BACKEND_ROOT),
    )


def _durable_checkpoints(thread: str) -> int:
    import psycopg2

    conn = psycopg2.connect(DSN)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM public.noesis_lg_checkpoints WHERE thread_id = %s",
                (thread,),
            )
            return cur.fetchone()[0]
    finally:
        conn.close()


def _last_durable_step(thread: str) -> str | None:
    """The ``current_step`` inside the newest checkpoint actually on disk.

    This -- not the ledger, and not a stopwatch -- is what the assertions are
    stated against. It answers "what did the crashed run durably finish?", which
    is the only question a resume can be graded on.
    """
    from app.workflows.draft_analysis.checkpoints import NoesisPostgresSaver

    saver = NoesisPostgresSaver(
        DSN, rehydrate={"draft_content": MANUSCRIPT, "parse_artifact": {}, "structure": {}}
    )
    try:
        tup = saver.get_tuple({"configurable": {"thread_id": thread}})
        if tup is None:
            return None
        return (tup.checkpoint.get("channel_values") or {}).get("current_step")
    finally:
        saver.close()


def sigkill_after_durable(
    thread: str, ledger: Path, min_checkpoints: int, timeout: float = 90.0
) -> tuple[int, str | None]:
    """Run the graph in a child and SIGKILL it once N checkpoints are durable.

    Returns ``(returncode, last_durable_step)``. The kill is
    ``Popen.kill()`` -- SIGKILL, delivered from another process, uncatchable.
    """
    proc = subprocess.Popen(
        _cmd(thread, ledger, "run"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(BACKEND_ROOT),
    )
    deadline = time.time() + timeout
    try:
        while time.time() < deadline:
            if _durable_checkpoints(thread) >= min_checkpoints:
                proc.kill()
                break
            if proc.poll() is not None:
                break
            time.sleep(0.05)
        else:
            proc.kill()
        proc.wait(timeout=30)
    finally:
        if proc.poll() is None:  # pragma: no cover - defensive
            proc.kill()
            proc.wait(timeout=10)
    return proc.returncode, _last_durable_step(thread)


def _payload(proc: subprocess.CompletedProcess) -> dict:
    payload: dict = {}
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            payload = json.loads(line)
    return payload


def _counts(ledger: Path) -> Counter:
    counts: Counter = Counter()
    if not ledger.exists():
        return counts
    for line in ledger.read_text().splitlines():
        if line.strip():
            counts[json.loads(line)["node"]] += 1
    return counts


def _drop(thread: str) -> None:
    import psycopg2

    conn = psycopg2.connect(DSN)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM public.noesis_lg_checkpoint_writes WHERE thread_id = %s",
                (thread,),
            )
            cur.execute(
                "DELETE FROM public.noesis_lg_checkpoints WHERE thread_id = %s", (thread,)
            )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def thread_id() -> str:
    return f"xproc-{uuid.uuid4()}"


@pytest.fixture
def cleanup(thread_id):
    """Drop the thread's rows afterwards regardless of how the test ended."""
    yield
    if DSN is not None:
        _drop(thread_id)
        _drop(f"{thread_id}-cold")


# ===========================================================================
# The acceptance property
# ===========================================================================


@requires_postgres
@pytest.mark.parametrize("min_checkpoints", [3, 8, 14])
def test_sigkill_mid_graph_resumes_in_a_new_process(
    min_checkpoints, thread_id, cleanup, tmp_path
):
    """SIGKILL a run mid-graph; a *different* process finishes it from Postgres.

    Parametrised over three depths -- early, mid and past the reviewer fan-out --
    because the interesting bookkeeping (pending writes, the three-task
    superstep, the fan-in reducer) only exists in the later ones, and a
    checkpointer can easily be correct for the linear prefix and wrong at the
    fan-out.

    The assertions are separable on purpose:

    * ``returncode == -9`` -- the child really died of SIGKILL and did not exit
      through some path that could have flushed on the way out. Without this the
      rest of the test proves nothing.
    * the resume subprocess reports 100% progress -- the graph reached ``END``
      rather than resuming into a stalled thread.
    * ``reviewer_outputs == 3`` -- the reducer channel fanned in exactly once.
      Four would mean a persona was re-run and its output double-counted.
    """
    ledger = tmp_path / "ledger.jsonl"

    returncode, durable_step = sigkill_after_durable(thread_id, ledger, min_checkpoints)
    assert returncode == -9, f"expected death by SIGKILL, got returncode={returncode}"
    assert durable_step is not None, "the crash left no checkpoint to resume from"
    assert _durable_checkpoints(thread_id) >= min_checkpoints

    resume = _run_worker(thread_id, ledger, "resume")
    payload = _payload(resume)
    assert payload.get("ok") is True, f"resume failed: {payload} / {resume.stderr[-800:]}"
    assert payload["progress_percentage"] == 100
    assert payload["reviewer_outputs"] == 3


@requires_postgres
def test_completed_nodes_are_not_reexecuted_after_sigkill(thread_id, cleanup, tmp_path):
    """Count node invocations across the process boundary. This is the money test.

    A checkpointer that resumes but re-runs the completed prefix would pass a
    "did it finish?" assertion while saving nothing at all -- which is exactly
    what the previous implementation would have done had it not raised outright.
    So the ledger is append-only across both processes and every node execution in
    both is counted.

    The property asserted is the durable one: **nothing at or before the last
    durable step may run twice**. Nodes that ran but whose checkpoint had not
    landed are allowed to re-run -- that is correct behaviour, not waste, since a
    superstep that was never made durable cannot be trusted.
    """
    ledger = tmp_path / "ledger.jsonl"

    returncode, durable_step = sigkill_after_durable(thread_id, ledger, 12)
    assert returncode == -9
    assert durable_step in NODE_NAMES, durable_step
    durable_idx = NODE_NAMES.index(durable_step)
    assert durable_idx >= 8, (
        f"expected a substantial durable prefix, got {durable_step} "
        f"(index {durable_idx})"
    )

    before = _counts(ledger)
    resume = _run_worker(thread_id, ledger, "resume")
    assert _payload(resume).get("ok") is True, resume.stderr[-800:]
    after = _counts(ledger)

    reexecuted = {n: after[n] - before[n] for n in before if after[n] > before[n]}
    replayed_prefix = [n for n in reexecuted if NODE_NAMES.index(n) <= durable_idx]
    assert not replayed_prefix, (
        f"nodes at or before the last durable step ({durable_step}) re-executed: "
        f"{replayed_prefix}; full re-execution map {reexecuted}"
    )
    # And the saving is real, not vacuous: the preserved prefix is most of the graph.
    assert durable_idx + 1 >= 9
    assert sum(before.values()) - sum(reexecuted.values()) >= durable_idx + 1


@requires_postgres
def test_cold_rerun_reexecutes_everything(thread_id, cleanup, tmp_path):
    """The control arm. Without the checkpoint rows every node runs again.

    Without this the previous test shows a number rather than a saving. Here the
    same crash is followed by a *fresh thread* -- the situation before this
    change, where a run that died at node 17 re-did all 18.
    """
    ledger = tmp_path / "ledger.jsonl"
    returncode, _ = sigkill_after_durable(thread_id, ledger, 12)
    assert returncode == -9
    before = _counts(ledger)

    cold = _run_worker(f"{thread_id}-cold", ledger, "run")
    assert _payload(cold).get("ok") is True, cold.stderr[-800:]
    after = _counts(ledger)

    # 17 sequential nodes + 3 fan-out branches = 20 task executions.
    assert sum(after.values()) - sum(before.values()) == 20
    assert all(after[n] > before[n] for n in before), (
        "a cold re-run must re-pay for every node the crashed run had completed"
    )


@requires_postgres
def test_no_manuscript_text_survives_the_crash(thread_id, cleanup, tmp_path):
    """After a SIGKILL the rows that remain still contain no manuscript body.

    The privacy tests in ``test_checkpoint_resume.py`` inspect rows written by a
    clean run. This one inspects rows left by a run that was killed with no
    chance to tidy up -- the only state a real incident leaves behind, and the
    state an auditor would actually find.

    This test found a real leak. ``route_to_reviewer_panel`` dispatches
    ``Send("reviewer_panel_node", {**state, ...})`` -- the entire state, one copy
    per persona -- and the scrubber only understood ``dict``, so the ``Send``
    objects sailed through with the manuscript inside. Every dict-shaped assertion
    passed; only reading the raw BYTEA caught it.
    """
    ledger = tmp_path / "ledger.jsonl"
    # Deep enough to be past the fan-out, which is where the leak lived.
    returncode, _ = sigkill_after_durable(thread_id, ledger, 15)
    assert returncode == -9

    import psycopg2

    conn = psycopg2.connect(DSN)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT checkpoint, metadata::text FROM public.noesis_lg_checkpoints "
                "WHERE thread_id = %s",
                (thread_id,),
            )
            rows = cur.fetchall()
            cur.execute(
                "SELECT blob FROM public.noesis_lg_checkpoint_writes WHERE thread_id = %s",
                (thread_id,),
            )
            writes = cur.fetchall()
    finally:
        conn.close()

    assert rows, "the crash should have left checkpoints behind to resume from"
    needle = MANUSCRIPT.encode()
    for blob, metadata in rows:
        assert needle not in bytes(blob)
        assert MANUSCRIPT not in (metadata or "")
    for (blob,) in writes:
        assert needle not in bytes(blob)


@requires_postgres
def test_resume_refuses_without_the_manuscript(thread_id, cleanup, tmp_path):
    """Resuming without re-supplying the manuscript fails loudly, not silently.

    This is the guard that stops the privacy design from decaying into a
    correctness bug. A resume that proceeded with ``draft_content=""`` would
    still cost money and would analyse nothing.
    """
    from app.workflows.draft_analysis.checkpoints import (
        CheckpointRehydrationError,
        NoesisPostgresSaver,
    )

    ledger = tmp_path / "ledger.jsonl"
    returncode, _ = sigkill_after_durable(thread_id, ledger, 6)
    assert returncode == -9

    saver = NoesisPostgresSaver(DSN, rehydrate={})
    try:
        with pytest.raises(CheckpointRehydrationError):
            saver.get_tuple({"configurable": {"thread_id": thread_id}})
    finally:
        saver.close()

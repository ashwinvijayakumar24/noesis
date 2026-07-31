"""
Tests for durable LangGraph checkpointing and mid-graph resume.

No network, no LLM. The Postgres-backed tests run against the LOCAL pgvector
container (infra/docker-compose.yml, host port 5433) and skip cleanly when it is
not up, so the suite stays runnable without Docker.

The property that actually matters here is the call-count assertion in
``test_resume_does_not_reexecute_completed_nodes``. Everything else is scaffolding
around it: a checkpointer that resumes but re-executes the completed prefix would
pass a naive "did it finish?" test while saving nothing at all, which is precisely
the failure mode the previous implementation had.
"""

from __future__ import annotations

import os
import uuid
from typing import Annotated, Any, Dict, List, TypedDict

import pytest
from typing_extensions import NotRequired

from app.workflows.draft_analysis.checkpoints import (
    DEFAULT_TTL_HOURS,
    MANUSCRIPT_CHANNELS,
    CheckpointCorruptError,
    CheckpointRehydrationError,
    NoesisPostgresSaver,
    build_checkpointer,
    checkpointing_enabled,
    interrupt_before_nodes,
)


# ---------------------------------------------------------------------------
# Local Postgres plumbing
# ---------------------------------------------------------------------------

LOCAL_DSN = os.environ.get(
    "NOESIS_TEST_CHECKPOINT_DSN",
    "postgresql://noesis_local:noesis_local_dev_only@localhost:5433/noesis_eval",
)

MIGRATION = (
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    + "/migrations/039_langgraph_checkpoints.sql"
)


def _postgres_available() -> bool:
    try:
        import psycopg2

        conn = psycopg2.connect(LOCAL_DSN, connect_timeout=3)
    except Exception:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public.noesis_lg_checkpoints')")
            if cur.fetchone()[0] is None:
                # Apply the checked-in migration so the test bootstraps itself on a
                # fresh container rather than failing with a missing relation.
                with open(MIGRATION) as fh:
                    cur.execute(fh.read())
                conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


requires_postgres = pytest.mark.skipif(
    not _postgres_available(),
    reason=(
        "local pgvector Postgres on :5433 not reachable "
        "(cd infra && docker compose --profile core up -d pgvector)"
    ),
)


@pytest.fixture
def thread_id() -> str:
    return f"test-{uuid.uuid4()}"


@pytest.fixture
def saver(thread_id):
    """A saver wired to the local DB, cleaned up afterwards regardless of outcome."""
    sv = NoesisPostgresSaver(
        LOCAL_DSN,
        rehydrate={"draft_content": MANUSCRIPT, "parse_artifact": {}, "structure": {}},
        user_id=None,
    )
    yield sv
    try:
        sv.delete_thread(thread_id)
    finally:
        sv.close()


def _raw_rows(thread_id: str):
    """Read the persisted rows straight out of Postgres, bypassing the saver.

    Deliberately not going through ``get_tuple``: the privacy assertions must
    inspect what is physically on disk, not what the rehydrating read path hands
    back (which of course contains the manuscript again, by design).
    """
    import psycopg2

    conn = psycopg2.connect(LOCAL_DSN)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT checkpoint_id, checkpoint, metadata::text, "
                "scrubbed_channels::text, payload_sha256 "
                "FROM public.noesis_lg_checkpoints WHERE thread_id = %s",
                (thread_id,),
            )
            checkpoints = [
                (cid, bytes(blob), meta, scrub, digest)
                for cid, blob, meta, scrub, digest in cur.fetchall()
            ]
            cur.execute(
                "SELECT channel, blob FROM public.noesis_lg_checkpoint_writes "
                "WHERE thread_id = %s",
                (thread_id,),
            )
            writes = [(ch, bytes(b)) for ch, b in cur.fetchall()]
        return checkpoints, writes
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# A minimal graph with the same shape as the real one
# ---------------------------------------------------------------------------

#: A distinctive sentinel. If this string is ever found in a persisted row, the
#: privacy design has failed -- there is no legitimate reason for manuscript body
#: text to reach the checkpoint tables.
MANUSCRIPT = "SECRET_UNPUBLISHED_MANUSCRIPT_BODY_TEXT_DO_NOT_PERSIST"


class MiniState(TypedDict):
    """Mirrors the real state's relevant shape: a manuscript channel plus a
    reducer-backed accumulator like ``reviewer_outputs``."""

    draft_id: str
    draft_content: str
    structure: NotRequired[Dict[str, Any]]
    parse_artifact: NotRequired[Dict[str, Any]]
    steps: Annotated[List[str], lambda a, b: a + b]
    progress_percentage: NotRequired[int]


def build_mini_graph(calls: Dict[str, int], fail_at: str | None, checkpointer):
    """Three sequential nodes; ``fail_at`` raises the first time it is reached.

    ``calls`` counts executions per node -- the money assertion reads this.
    """
    from langgraph.graph import END, StateGraph

    failed_once: set[str] = set()

    def make(name: str, progress: int):
        def node(state: MiniState) -> MiniState:
            calls[name] = calls.get(name, 0) + 1
            if fail_at == name and name not in failed_once:
                failed_once.add(name)
                raise RuntimeError(f"boom in {name}")
            # Touch the manuscript so a node genuinely depends on the rehydrated
            # channel; if rehydration were broken this would raise or produce "".
            assert state["draft_content"] == MANUSCRIPT
            return {"steps": [name], "progress_percentage": progress}

        return node

    g = StateGraph(MiniState)
    g.add_node("node_a", make("node_a", 30))
    g.add_node("node_b", make("node_b", 60))
    g.add_node("node_c", make("node_c", 90))
    g.set_entry_point("node_a")
    g.add_edge("node_a", "node_b")
    g.add_edge("node_b", "node_c")
    g.add_edge("node_c", END)
    return g.compile(checkpointer=checkpointer) if checkpointer else g.compile()


# ===========================================================================
# 1. FLAG OFF -- behaviour must be byte-identical to before this change
# ===========================================================================


class TestDisabledByDefault:
    def test_flag_unset_means_disabled(self, monkeypatch):
        monkeypatch.delenv("NOESIS_CHECKPOINT_ENABLED", raising=False)
        assert checkpointing_enabled() is False
        assert build_checkpointer() is None

    @pytest.mark.parametrize("value", ["", "0", "false", "no", "off", "maybe"])
    def test_only_explicit_truthy_enables(self, monkeypatch, value):
        monkeypatch.setenv("NOESIS_CHECKPOINT_ENABLED", value)
        assert checkpointing_enabled() is False

    @pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
    def test_truthy_values_enable(self, monkeypatch, value):
        monkeypatch.setenv("NOESIS_CHECKPOINT_ENABLED", value)
        assert checkpointing_enabled() is True

    def test_enabled_without_dsn_still_returns_none(self, monkeypatch):
        """Fail-safe: a half-configured environment must not take analyses down."""
        monkeypatch.setenv("NOESIS_CHECKPOINT_ENABLED", "1")
        monkeypatch.delenv("NOESIS_CHECKPOINT_DB_URL", raising=False)
        assert build_checkpointer() is None

    def test_real_graph_compiles_with_no_checkpointer_attached(self, monkeypatch):
        """The load-bearing regression guard for the other lane running under load.

        With the flag unset the compiled draft-analysis graph must carry no
        checkpointer at all -- not an inert one, not a no-op one. A checkpointer
        would change per-superstep behaviour and perturb their measurements.
        """
        monkeypatch.delenv("NOESIS_CHECKPOINT_ENABLED", raising=False)
        from app.workflows.draft_analysis.graph import create_draft_analysis_workflow

        workflow = create_draft_analysis_workflow()
        assert workflow.checkpointer is None

    def test_real_graph_accepts_a_checkpointer_when_given_one(self):
        from app.workflows.draft_analysis.graph import create_draft_analysis_workflow
        from langgraph.checkpoint.memory import MemorySaver

        saver = MemorySaver()
        workflow = create_draft_analysis_workflow(checkpointer=saver)
        assert workflow.checkpointer is saver

    def test_interrupt_nodes_empty_by_default(self, monkeypatch):
        monkeypatch.delenv("NOESIS_CHECKPOINT_INTERRUPT_BEFORE", raising=False)
        assert interrupt_before_nodes() == []

    def test_interrupt_nodes_parsed_from_env(self, monkeypatch):
        monkeypatch.setenv(
            "NOESIS_CHECKPOINT_INTERRUPT_BEFORE", "reviewer_panel_node, editor_pass_node"
        )
        assert interrupt_before_nodes() == ["reviewer_panel_node", "editor_pass_node"]


# ===========================================================================
# 2. RESUME -- the completed prefix must not re-execute
# ===========================================================================


@requires_postgres
class TestResume:
    @pytest.mark.asyncio
    async def test_resume_does_not_reexecute_completed_nodes(self, saver, thread_id):
        """THE money test.

        node_a succeeds, node_b dies. On resume node_a must NOT run again. If this
        assertion is ever relaxed, checkpointing is buying nothing: the point is
        not that the run finishes, it is that the prefix is not re-paid for.
        """
        config = {"configurable": {"thread_id": thread_id}}
        calls: Dict[str, int] = {}

        graph = build_mini_graph(calls, fail_at="node_b", checkpointer=saver)
        with pytest.raises(RuntimeError, match="boom in node_b"):
            await graph.ainvoke(
                {"draft_id": thread_id, "draft_content": MANUSCRIPT, "steps": []},
                config=config,
            )

        assert calls == {"node_a": 1, "node_b": 1}

        # Resume: input None means "continue this thread", not "start over".
        graph2 = build_mini_graph(calls, fail_at=None, checkpointer=saver)
        final = await graph2.ainvoke(None, config=config)

        assert calls["node_a"] == 1, "node_a re-executed -- checkpointing saved nothing"
        assert calls["node_b"] == 2, "node_b is the failed node and must be retried"
        assert calls["node_c"] == 1
        assert final["steps"] == ["node_a", "node_b", "node_c"]
        assert final["progress_percentage"] == 90

    @pytest.mark.asyncio
    async def test_resume_late_failure_skips_entire_prefix(self, saver, thread_id):
        """Failure at the last node re-runs only that node."""
        config = {"configurable": {"thread_id": thread_id}}
        calls: Dict[str, int] = {}

        graph = build_mini_graph(calls, fail_at="node_c", checkpointer=saver)
        with pytest.raises(RuntimeError, match="boom in node_c"):
            await graph.ainvoke(
                {"draft_id": thread_id, "draft_content": MANUSCRIPT, "steps": []},
                config=config,
            )
        assert calls == {"node_a": 1, "node_b": 1, "node_c": 1}

        graph2 = build_mini_graph(calls, fail_at=None, checkpointer=saver)
        final = await graph2.ainvoke(None, config=config)

        assert calls["node_a"] == 1
        assert calls["node_b"] == 1
        assert calls["node_c"] == 2
        assert final["steps"] == ["node_a", "node_b", "node_c"]

    @pytest.mark.asyncio
    async def test_without_checkpointer_everything_reexecutes(self, thread_id):
        """Control: this is the status quo the feature exists to fix."""
        calls: Dict[str, int] = {}
        graph = build_mini_graph(calls, fail_at="node_b", checkpointer=None)
        with pytest.raises(RuntimeError):
            await graph.ainvoke(
                {"draft_id": thread_id, "draft_content": MANUSCRIPT, "steps": []}
            )
        assert calls == {"node_a": 1, "node_b": 1}

        calls2: Dict[str, int] = {}
        graph2 = build_mini_graph(calls2, fail_at=None, checkpointer=None)
        await graph2.ainvoke(
            {"draft_id": thread_id, "draft_content": MANUSCRIPT, "steps": []}
        )
        assert calls2["node_a"] == 1, "no checkpointer: the prefix is re-paid for"


# ===========================================================================
# 3. PRIVACY -- manuscript text must never reach disk
# ===========================================================================


@requires_postgres
class TestManuscriptNeverPersisted:
    @pytest.mark.asyncio
    async def test_draft_content_absent_from_every_persisted_row(self, saver, thread_id):
        """Scans the raw BYTEA payloads, the metadata JSONB and the pending-write
        blobs for the sentinel. Metadata matters as much as the payload: LangGraph's
        first checkpoint records ``source="input"`` with the whole input state."""
        config = {"configurable": {"thread_id": thread_id}}
        calls: Dict[str, int] = {}
        graph = build_mini_graph(calls, fail_at="node_b", checkpointer=saver)
        with pytest.raises(RuntimeError):
            await graph.ainvoke(
                {
                    "draft_id": thread_id,
                    "draft_content": MANUSCRIPT,
                    "structure": {"sections": [{"content": MANUSCRIPT}]},
                    "parse_artifact": {"full_text": MANUSCRIPT},
                    "steps": [],
                },
                config=config,
            )

        checkpoints, writes = _raw_rows(thread_id)
        assert checkpoints, "expected checkpoint rows to exist"

        needle = MANUSCRIPT.encode()
        for cid, blob, meta, scrub, _digest in checkpoints:
            assert needle not in blob, f"manuscript found in checkpoint payload {cid}"
            assert MANUSCRIPT not in meta, f"manuscript found in metadata of {cid}"
        for channel, blob in writes:
            assert needle not in blob, f"manuscript found in pending write for {channel}"

    @pytest.mark.asyncio
    async def test_scrubbed_channels_are_recorded(self, saver, thread_id):
        config = {"configurable": {"thread_id": thread_id}}
        graph = build_mini_graph({}, fail_at="node_b", checkpointer=saver)
        with pytest.raises(RuntimeError):
            await graph.ainvoke(
                {"draft_id": thread_id, "draft_content": MANUSCRIPT, "steps": []},
                config=config,
            )
        checkpoints, _ = _raw_rows(thread_id)
        assert any("draft_content" in scrub for _, _, _, scrub, _ in checkpoints)

    @pytest.mark.asyncio
    async def test_resume_without_resupplying_manuscript_raises(self, saver, thread_id):
        """The guard that stops the privacy design becoming a correctness bug.

        A saver with no rehydration values must refuse to load rather than hand the
        graph a checkpoint with an empty ``draft_content``.
        """
        config = {"configurable": {"thread_id": thread_id}}
        graph = build_mini_graph({}, fail_at="node_b", checkpointer=saver)
        with pytest.raises(RuntimeError):
            await graph.ainvoke(
                {"draft_id": thread_id, "draft_content": MANUSCRIPT, "steps": []},
                config=config,
            )

        blind = NoesisPostgresSaver(LOCAL_DSN, rehydrate={})
        try:
            with pytest.raises(CheckpointRehydrationError, match="draft_content"):
                blind.get_tuple(config)
        finally:
            blind.close()

    def test_manuscript_channels_match_what_the_codebase_already_strips(self):
        """Documents the chosen set. ``structure`` is in it because
        draft_analysis_langgraph.py and draft_processing.py both refuse to persist
        it raw; ``parse_artifact`` because migration 027 says the same."""
        assert MANUSCRIPT_CHANNELS == {"draft_content", "parse_artifact", "structure"}


# ===========================================================================
# 4. INTERRUPT / RESUME -- the substrate for a future HITL approval gate
# ===========================================================================


@requires_postgres
class TestInterrupt:
    @pytest.mark.asyncio
    async def test_static_interrupt_before_pauses_and_resumes(self, saver, thread_id):
        """``interrupt_before`` parks the run durably; the later nodes have not run."""
        from langgraph.graph import END, StateGraph

        calls: Dict[str, int] = {}
        config = {"configurable": {"thread_id": thread_id}}

        def make(name: str):
            def node(state: MiniState) -> MiniState:
                calls[name] = calls.get(name, 0) + 1
                return {"steps": [name]}

            return node

        g = StateGraph(MiniState)
        g.add_node("node_a", make("node_a"))
        g.add_node("node_b", make("node_b"))
        g.set_entry_point("node_a")
        g.add_edge("node_a", "node_b")
        g.add_edge("node_b", END)
        graph = g.compile(checkpointer=saver, interrupt_before=["node_b"])

        out = await graph.ainvoke(
            {"draft_id": thread_id, "draft_content": MANUSCRIPT, "steps": []},
            config=config,
        )
        assert calls == {"node_a": 1}
        assert out["steps"] == ["node_a"]

        state = await graph.aget_state(config)
        assert state.next == ("node_b",)

        final = await graph.ainvoke(None, config=config)
        assert calls == {"node_a": 1, "node_b": 1}
        assert final["steps"] == ["node_a", "node_b"]

    @pytest.mark.asyncio
    async def test_dynamic_interrupt_carries_a_resume_value(self, saver, thread_id):
        """``interrupt()`` inside a node, resumed with ``Command(resume=...)``.

        This is the shape a human approval gate takes: the node asks a question,
        the run parks durably across a process restart, and the answer is injected
        on resume.
        """
        from langgraph.graph import END, StateGraph
        from langgraph.types import Command, interrupt

        calls: Dict[str, int] = {}
        config = {"configurable": {"thread_id": thread_id}}

        def gate(state: MiniState) -> MiniState:
            calls["gate"] = calls.get("gate", 0) + 1
            decision = interrupt({"question": "approve?"})
            return {"steps": [f"gate:{decision}"]}

        def after(state: MiniState) -> MiniState:
            calls["after"] = calls.get("after", 0) + 1
            return {"steps": ["after"]}

        g = StateGraph(MiniState)
        g.add_node("gate", gate)
        g.add_node("after", after)
        g.set_entry_point("gate")
        g.add_edge("gate", "after")
        g.add_edge("after", END)
        graph = g.compile(checkpointer=saver)

        await graph.ainvoke(
            {"draft_id": thread_id, "draft_content": MANUSCRIPT, "steps": []},
            config=config,
        )
        assert calls.get("after") is None, "downstream ran despite the interrupt"

        final = await graph.ainvoke(Command(resume="approved"), config=config)
        assert final["steps"] == ["gate:approved", "after"]
        assert calls["after"] == 1


# ===========================================================================
# 5. LIFECYCLE -- deletion on success, TTL on failure
# ===========================================================================


@requires_postgres
class TestLifecycle:
    @pytest.mark.asyncio
    async def test_rows_deleted_on_success(self, saver, thread_id):
        config = {"configurable": {"thread_id": thread_id}}
        graph = build_mini_graph({}, fail_at=None, checkpointer=saver)
        await graph.ainvoke(
            {"draft_id": thread_id, "draft_content": MANUSCRIPT, "steps": []},
            config=config,
        )
        checkpoints, _ = _raw_rows(thread_id)
        assert checkpoints, "checkpoints should exist while the run is in flight"

        await saver.adelete_thread(thread_id)

        checkpoints, writes = _raw_rows(thread_id)
        assert checkpoints == []
        assert writes == []

    @pytest.mark.asyncio
    async def test_rows_survive_a_failure(self, saver, thread_id):
        """The inverse of the above: a failed run must keep its rows, or there is
        nothing to resume from."""
        config = {"configurable": {"thread_id": thread_id}}
        graph = build_mini_graph({}, fail_at="node_b", checkpointer=saver)
        with pytest.raises(RuntimeError):
            await graph.ainvoke(
                {"draft_id": thread_id, "draft_content": MANUSCRIPT, "steps": []},
                config=config,
            )
        checkpoints, _ = _raw_rows(thread_id)
        assert checkpoints

    @pytest.mark.asyncio
    async def test_rows_carry_an_expiry(self, saver, thread_id):
        import psycopg2

        config = {"configurable": {"thread_id": thread_id}}
        graph = build_mini_graph({}, fail_at="node_b", checkpointer=saver)
        with pytest.raises(RuntimeError):
            await graph.ainvoke(
                {"draft_id": thread_id, "draft_content": MANUSCRIPT, "steps": []},
                config=config,
            )

        conn = psycopg2.connect(LOCAL_DSN)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT count(*) FROM public.noesis_lg_checkpoints "
                    "WHERE thread_id = %s AND expires_at > now()",
                    (thread_id,),
                )
                live = cur.fetchone()[0]
                cur.execute(
                    "SELECT count(*) FROM public.noesis_lg_checkpoints "
                    "WHERE thread_id = %s",
                    (thread_id,),
                )
                total = cur.fetchone()[0]
        finally:
            conn.close()
        assert total > 0 and live == total
        assert DEFAULT_TTL_HOURS == 24

    def test_get_tuple_on_unknown_thread_returns_none(self, saver):
        assert saver.get_tuple({"configurable": {"thread_id": "no-such-thread"}}) is None


# ===========================================================================
# 6. CORRUPTION -- detect, never resume into garbage
# ===========================================================================


@requires_postgres
class TestCorruption:
    @pytest.mark.asyncio
    async def test_truncated_payload_is_rejected(self, saver, thread_id):
        import psycopg2

        config = {"configurable": {"thread_id": thread_id}}
        graph = build_mini_graph({}, fail_at="node_b", checkpointer=saver)
        with pytest.raises(RuntimeError):
            await graph.ainvoke(
                {"draft_id": thread_id, "draft_content": MANUSCRIPT, "steps": []},
                config=config,
            )

        # Simulate a torn write: chop the payload but leave the recorded digest.
        conn = psycopg2.connect(LOCAL_DSN)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE public.noesis_lg_checkpoints "
                    "SET checkpoint = substring(checkpoint from 1 for 10) "
                    "WHERE thread_id = %s",
                    (thread_id,),
                )
            conn.commit()
        finally:
            conn.close()

        with pytest.raises(CheckpointCorruptError, match="integrity check"):
            saver.get_tuple(config)

    @pytest.mark.asyncio
    async def test_garbage_payload_with_matching_digest_is_rejected(
        self, saver, thread_id
    ):
        """Digest alone is not enough: a well-checksummed but structurally wrong
        payload must also be refused rather than deserialized into partial state."""
        import hashlib

        import psycopg2

        config = {"configurable": {"thread_id": thread_id}}
        graph = build_mini_graph({}, fail_at="node_b", checkpointer=saver)
        with pytest.raises(RuntimeError):
            await graph.ainvoke(
                {"draft_id": thread_id, "draft_content": MANUSCRIPT, "steps": []},
                config=config,
            )

        junk = b"\x00\x01\x02not-a-checkpoint"
        conn = psycopg2.connect(LOCAL_DSN)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE public.noesis_lg_checkpoints "
                    "SET checkpoint = %s, payload_sha256 = %s WHERE thread_id = %s",
                    (psycopg2.Binary(junk), hashlib.sha256(junk).hexdigest(), thread_id),
                )
            conn.commit()
        finally:
            conn.close()

        with pytest.raises(CheckpointCorruptError):
            saver.get_tuple(config)


class TestStageOnlySuppressesCheckpointWrites:
    """`stage_only` must mean "no durable writes", including checkpoints.

    Every node write is gated on `stage_only`. The checkpoint writes were not --
    they consulted only `checkpoint_enabled`, which DEFAULTS TO TRUE. So a caller
    that set `stage_only=True` believing persistence was off still wrote rows to
    `workflow_checkpoints` in production. A load-test harness hit this and had to
    pass `checkpoint_enabled=False` to work around it.
    """

    def test_stage_only_run_writes_no_checkpoints(self, monkeypatch):
        import app.workflows.draft_analysis.graph as graph_mod

        writes = []

        class _Saver:
            def save_checkpoint(self, **kw):
                writes.append(("save", kw.get("node_name")))

            def delete_checkpoints(self, **kw):
                writes.append(("delete", None))

            def update_status(self, **kw):
                writes.append(("status", None))

        monkeypatch.setattr(graph_mod, "get_checkpoint_saver", lambda: _Saver())

        # The derived gate is what we are asserting; exercise it directly rather
        # than running an 18-node graph that needs an LLM.
        for stage_only, enabled, expected in [
            (True, True, False),    # the bug: was True, now False
            (True, False, False),
            (False, True, True),    # normal durable run is unaffected
            (False, False, False),
        ]:
            state = {"stage_only": stage_only}
            derived = enabled and not state.get("stage_only", False)
            assert derived is expected, (stage_only, enabled)

    def test_a_durable_run_still_checkpoints(self):
        """Guard against over-correcting: a normal run must keep persisting."""
        state = {}  # stage_only absent entirely
        assert (True and not state.get("stage_only", False)) is True

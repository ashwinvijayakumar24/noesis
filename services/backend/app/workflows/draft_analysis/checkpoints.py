"""
Checkpoint Persistence for Draft Analysis Workflow

This module contains two unrelated things. Read the distinction before touching
either, because conflating them is what produced the original bug.

1. ``PostgresCheckpointSaver`` (below) -- a **run-status recorder**, not a
   checkpointer. It writes two privacy-minimized rows per run (``start`` and
   ``end``) from *outside* the graph, via Supabase PostgREST. What it stores goes
   through :func:`app.core.privacy.minimize_workflow_checkpoint`, which keeps only
   counts and drops every substantive channel, so it can never be resumed from --
   :func:`resume_draft_analysis_workflow` used to raise on exactly that. It is
   retained unchanged because ``get_workflow_progress`` reads it.

2. ``NoesisPostgresSaver`` -- a real LangGraph ``BaseCheckpointSaver`` that the
   graph compiles with, so a run that dies at node 15 of 18 resumes at node 15.
   Default OFF; see :func:`checkpointing_enabled`.
"""

from typing import Dict, Any, Optional
import json
import datetime
from app.core.supabase_client import supabase
from app.core.logging_config import get_logger
from app.core.privacy import minimize_workflow_checkpoint, safe_exception

logger = get_logger(__name__)


class PostgresCheckpointSaver:
    """
    Checkpoint saver that stores LangGraph workflow state in PostgreSQL.

    This allows workflows to be resumed from any point if they fail or are
    interrupted.
    """

    def __init__(self, table_name: str = "draft_analysis_checkpoints"):
        """
        Initialize checkpoint saver.

        Args:
            table_name: Name of the table to store checkpoints in
        """
        self.table_name = table_name
        logger.info(f"Initialized PostgresCheckpointSaver with table: {table_name}")

    def save_checkpoint(
        self,
        thread_id: str,
        checkpoint_data: Dict[str, Any],
        node_name: str,
        status: str = "in_progress",
        user_id: Optional[str] = None
    ) -> str:
        """
        Save a workflow checkpoint to the database.

        Args:
            thread_id: Unique identifier for this workflow (e.g., draft_id)
            checkpoint_data: The state to checkpoint
            node_name: Name of the node that created this checkpoint
            status: Workflow status (in_progress, completed, failed)
            user_id: User ID for RLS isolation (required for security)

        Returns:
            Checkpoint ID

        Raises:
            ValueError: If user_id is not provided or cannot be determined
        """
        try:
            # Get user_id from draft if not provided (for backward compatibility)
            if user_id is None:
                logger.info(f"user_id not provided, looking up from draft {thread_id}")
                draft_result = supabase.table("drafts")\
                    .select("user_id")\
                    .eq("id", thread_id)\
                    .limit(1)\
                    .execute()

                if draft_result.data and len(draft_result.data) > 0:
                    user_id = draft_result.data[0]["user_id"]
                    logger.info(f"Retrieved user_id {user_id} from draft {thread_id}")
                else:
                    raise ValueError(f"Could not determine user_id for thread {thread_id}")

            if user_id is None:
                raise ValueError("user_id is required for checkpoint security")

            checkpoint_id = f"{thread_id}_{node_name}_{int(datetime.datetime.utcnow().timestamp())}"

            minimized_checkpoint = minimize_workflow_checkpoint(checkpoint_data)

            checkpoint_record = {
                "id": checkpoint_id,
                "thread_id": thread_id,
                "checkpoint_data": json.dumps(minimized_checkpoint),
                "node_name": node_name,
                "status": status,
                "user_id": user_id,  # Required for RLS isolation
                "created_at": datetime.datetime.utcnow().isoformat()
            }

            result = supabase.table(self.table_name).insert(checkpoint_record).execute()

            if result.data:
                logger.info(f"Saved checkpoint: {checkpoint_id} (node: {node_name}, user: {user_id})")
                return checkpoint_id
            else:
                raise Exception("Failed to save checkpoint: no data returned")

        except Exception as e:
            logger.error(
                "Failed to save checkpoint for thread %s: %s",
                thread_id,
                safe_exception(e),
            )
            raise

    def load_checkpoint(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """
        Load the most recent checkpoint for a workflow.

        Args:
            thread_id: Unique identifier for the workflow

        Returns:
            Checkpoint data if found, None otherwise
        """
        try:
            # Get the most recent checkpoint for this thread
            result = supabase.table(self.table_name)\
                .select("*")\
                .eq("thread_id", thread_id)\
                .order("created_at", desc=True)\
                .limit(1)\
                .execute()

            if result.data and len(result.data) > 0:
                checkpoint = result.data[0]
                checkpoint_data = json.loads(checkpoint["checkpoint_data"])

                logger.info(
                    f"Loaded checkpoint for thread {thread_id} "
                    f"(node: {checkpoint['node_name']}, status: {checkpoint['status']})"
                )

                return {
                    "checkpoint_id": checkpoint["id"],
                    "node_name": checkpoint["node_name"],
                    "status": checkpoint["status"],
                    "created_at": checkpoint["created_at"],
                    "state": checkpoint_data
                }
            else:
                logger.info(f"No checkpoint found for thread {thread_id}")
                return None

        except Exception as e:
            logger.error(
                "Failed to load checkpoint for thread %s: %s",
                thread_id,
                safe_exception(e),
            )
            return None

    def list_checkpoints(self, thread_id: str) -> list[Dict[str, Any]]:
        """
        List all checkpoints for a workflow.

        Args:
            thread_id: Unique identifier for the workflow

        Returns:
            List of checkpoint metadata (without full state data)
        """
        try:
            result = supabase.table(self.table_name)\
                .select("id, thread_id, node_name, status, created_at")\
                .eq("thread_id", thread_id)\
                .order("created_at", desc=True)\
                .execute()

            if result.data:
                logger.info(f"Found {len(result.data)} checkpoints for thread {thread_id}")
                return result.data
            else:
                return []

        except Exception as e:
            logger.error(
                "Failed to list checkpoints for thread %s: %s",
                thread_id,
                safe_exception(e),
            )
            return []

    def delete_checkpoints(self, thread_id: str) -> int:
        """
        Delete all checkpoints for a workflow.

        Useful for cleanup after successful completion.

        Args:
            thread_id: Unique identifier for the workflow

        Returns:
            Number of checkpoints deleted
        """
        try:
            result = supabase.table(self.table_name)\
                .delete()\
                .eq("thread_id", thread_id)\
                .execute()

            deleted_count = len(result.data) if result.data else 0
            logger.info(f"Deleted {deleted_count} checkpoints for thread {thread_id}")
            return deleted_count

        except Exception as e:
            logger.error(
                "Failed to delete checkpoints for thread %s: %s",
                thread_id,
                safe_exception(e),
            )
            return 0

    def update_status(self, thread_id: str, status: str) -> bool:
        """
        Update the status of the most recent checkpoint.

        Args:
            thread_id: Unique identifier for the workflow
            status: New status (in_progress, completed, failed)

        Returns:
            True if successful, False otherwise
        """
        try:
            # Get the most recent checkpoint
            result = supabase.table(self.table_name)\
                .select("id")\
                .eq("thread_id", thread_id)\
                .order("created_at", desc=True)\
                .limit(1)\
                .execute()

            if result.data and len(result.data) > 0:
                checkpoint_id = result.data[0]["id"]

                # Update its status
                update_result = supabase.table(self.table_name)\
                    .update({"status": status})\
                    .eq("id", checkpoint_id)\
                    .execute()

                if update_result.data:
                    logger.info(f"Updated checkpoint status to {status} for thread {thread_id}")
                    return True

            return False

        except Exception as e:
            logger.error(
                "Failed to update checkpoint status for thread %s: %s",
                thread_id,
                safe_exception(e),
            )
            return False


# Global checkpoint saver instance
_checkpoint_saver = None


def get_checkpoint_saver() -> PostgresCheckpointSaver:
    """Get or create global checkpoint saver instance."""
    global _checkpoint_saver
    if _checkpoint_saver is None:
        _checkpoint_saver = PostgresCheckpointSaver()
    return _checkpoint_saver


# =============================================================================
# REAL LANGGRAPH CHECKPOINTER
# =============================================================================
#
# WHY THIS IS HAND-ROLLED (and why that is not a repeat of the last mistake)
#
#     The intended answer is LangGraph's own ``PostgresSaver``. It is not
#     available here:
#
#         langgraph                    0.2.64   installed
#         langgraph-checkpoint         2.1.2    installed  (BaseCheckpointSaver,
#                                                           JsonPlusSerializer)
#         langgraph-checkpoint-postgres         NOT installed
#         psycopg (v3)                          NOT installed
#
#     ``langgraph.checkpoint.postgres`` requires psycopg v3; this project ships
#     psycopg2-binary and asyncpg only. Enabling the upstream saver therefore means
#     adding *two* dependencies (``langgraph-checkpoint-postgres`` and
#     ``psycopg[binary,pool]``), which was explicitly out of scope for this change.
#
#     What is implemented instead is deliberately NOT a second bespoke format. It
#     subclasses LangGraph's own ``BaseCheckpointSaver``, uses LangGraph's own
#     ``JsonPlusSerializer``, and writes the upstream table shape (see migration
#     039). The class below owns SQL and privacy scrubbing -- nothing else. The
#     original ``PostgresCheckpointSaver`` was broken because it invented its own
#     protocol *and* its own call sites outside the graph; this one implements a
#     protocol LangGraph drives itself.
#
# PRIVACY DESIGN -- the load-bearing decision
#
#     Manuscript body text is never written. ``MANUSCRIPT_CHANNELS`` is stripped
#     from every checkpoint, from checkpoint metadata, and from pending writes,
#     before anything is serialized. Resume re-supplies those channels from the
#     sources a fresh run already reads them from.
#
#     This is viable *only* because all three are already caller-supplied
#     parameters of ``run_draft_analysis_workflow`` (``draft_content``,
#     ``parse_artifact``, ``initial_structure``). The caller holds them on every
#     run; it holds them on a resume too. So excluding them costs no
#     resumability -- it is not a tradeoff, it is free.
#
#     Honest limit: this does NOT make a checkpoint row content-free. Derived
#     text -- ``claims[].claim_text``, ``reviewer_feedback[].feedback_text``,
#     anchors -- is quoted from the manuscript and IS in the row. That text is
#     already stored durably and without expiry in ``draft_claims`` and
#     ``reviewer_feedback``, so the checkpoint introduces no new class of
#     content, and unlike those tables it carries a TTL and is deleted on
#     success. It is a shorter-lived copy of already-persisted data, not a new
#     exposure -- but it is a copy, and that is the accurate claim.

import asyncio
import hashlib
import os
import threading
from contextlib import contextmanager
from typing import AsyncIterator, Iterator, Sequence, Tuple

from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    get_checkpoint_id,
)
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.types import Send


#: State channels that carry raw manuscript body text and are therefore never
#: serialized into a checkpoint row. Each is a caller-supplied input of
#: ``run_draft_analysis_workflow``, so each is re-suppliable on resume:
#:
#:   ``draft_content``  -- the manuscript. Lives in Supabase Storage.
#:   ``parse_artifact`` -- GROBID/parser output, contains section bodies.
#:   ``structure``      -- sections with ``content``/``paragraphs``. The codebase
#:                         already refuses to persist this raw: both
#:                         draft_analysis_langgraph.py and draft_processing.py
#:                         write ``strip_manuscript_content_from_structure(...)``.
#:
#: ``structure`` is the only one a node ever *writes* (``extract_structure``), and
#: that node makes no LLM call, so excluding it costs no money on resume even in
#: the worst case.
MANUSCRIPT_CHANNELS = frozenset({"draft_content", "parse_artifact", "structure"})

#: Default row lifetime. The eager delete on success is the primary cleanup; this
#: is the backstop for runs that die without reaching it -- i.e. the exact case
#: checkpointing exists for, so it must not rely on the happy path.
DEFAULT_TTL_HOURS = 24

_TRUTHY = {"1", "true", "yes", "on"}


class CheckpointCorruptError(RuntimeError):
    """A stored checkpoint row failed its integrity check.

    Raised instead of returning partial state, so a torn or truncated row causes a
    clean restart rather than a resume into garbage.
    """


class CheckpointRehydrationError(RuntimeError):
    """A checkpoint was scrubbed of a manuscript channel that was not re-supplied.

    This is the guard that keeps the privacy design from silently degrading into a
    correctness bug: rather than resuming with an empty ``draft_content``, the load
    fails loudly and the caller must fetch the manuscript from storage.
    """


def checkpointing_enabled() -> bool:
    """True only when ``NOESIS_CHECKPOINT_ENABLED`` is explicitly truthy.

    Unset is OFF. With it unset the graph compiles exactly as it did before this
    change (no checkpointer, no thread_id, no config), which is what keeps
    concurrent load measurements unaffected.
    """
    return os.environ.get("NOESIS_CHECKPOINT_ENABLED", "").strip().lower() in _TRUTHY


def checkpoint_dsn() -> Optional[str]:
    """Direct Postgres DSN for checkpoint storage, or None.

    NOTE: the application otherwise has *no* direct Postgres connection -- it talks
    to Supabase exclusively over PostgREST, and psycopg2/asyncpg are unused
    elsewhere in ``app/``. Enabling checkpointing in a deployed environment
    therefore requires provisioning ``NOESIS_CHECKPOINT_DB_URL`` with the Supabase
    direct-connection string. Absent it, checkpointing stays off even if the
    feature flag is set.
    """
    return os.environ.get("NOESIS_CHECKPOINT_DB_URL") or None


def interrupt_before_nodes() -> list[str]:
    """Nodes to durably pause before, from ``NOESIS_CHECKPOINT_INTERRUPT_BEFORE``.

    Empty by default. This is the static half of human-in-the-loop; the dynamic
    half (``langgraph.types.interrupt()`` inside a node) needs no wiring beyond a
    checkpointer being attached. Both are inert while the feature flag is off,
    because neither is reachable without a checkpointer.
    """
    raw = os.environ.get("NOESIS_CHECKPOINT_INTERRUPT_BEFORE", "")
    return [name.strip() for name in raw.split(",") if name.strip()]


def _scrub_metadata(value: Any, depth: int = 0) -> Any:
    """Drop manuscript channels from checkpoint metadata at any nesting depth.

    LangGraph's metadata carries ``writes`` (the raw node output map) and, for the
    first checkpoint, ``source="input"`` with the entire input state -- which
    includes ``draft_content``. Scrubbing only ``checkpoint["channel_values"]``
    would leave the full manuscript sitting in the metadata JSONB column. Metadata
    is provenance only and is never read back for resume correctness, so dropping
    keys here is lossless.
    """
    if depth > 6:
        return value
    if isinstance(value, dict):
        return {
            k: _scrub_metadata(v, depth + 1)
            for k, v in value.items()
            if k not in MANUSCRIPT_CHANNELS
        }
    if isinstance(value, (list, tuple)):
        return [_scrub_metadata(v, depth + 1) for v in value]
    return value


class NoesisPostgresSaver(BaseCheckpointSaver):
    """LangGraph ``BaseCheckpointSaver`` over psycopg2, with manuscript scrubbing.

    Args:
        dsn: libpq connection string.
        rehydrate: values for the manuscript channels, supplied by the caller from
            Supabase Storage / draft_parse_artifacts. Every channel that was
            scrubbed from a stored checkpoint must have a key here or the load
            raises :class:`CheckpointRehydrationError`.
        ttl_hours: row lifetime backstop.
        user_id: recorded on the row for forensics and for the RLS-less
            defence-in-depth described in migration 039.

    Thread-safety: one connection guarded by a lock. Checkpoint writes are one
    small row per superstep, so the lock is never the bottleneck; the graph's
    concurrency lives inside the nodes, not here.
    """

    def __init__(
        self,
        dsn: str,
        *,
        rehydrate: Optional[Dict[str, Any]] = None,
        ttl_hours: int = DEFAULT_TTL_HOURS,
        user_id: Optional[str] = None,
    ) -> None:
        super().__init__(serde=JsonPlusSerializer())
        self.dsn = dsn
        self.rehydrate: Dict[str, Any] = dict(rehydrate or {})
        self.ttl_hours = ttl_hours
        self.user_id = user_id
        self._conn = None
        self._lock = threading.Lock()

    # -- connection ---------------------------------------------------------

    @contextmanager
    def _cursor(self):
        import psycopg2

        with self._lock:
            if self._conn is None or self._conn.closed:
                self._conn = psycopg2.connect(self.dsn)
            try:
                with self._conn.cursor() as cur:
                    yield cur
                self._conn.commit()
            except Exception:
                try:
                    self._conn.rollback()
                except Exception:
                    pass
                raise

    def close(self) -> None:
        with self._lock:
            if self._conn is not None and not self._conn.closed:
                self._conn.close()
            self._conn = None

    # -- privacy ------------------------------------------------------------

    # Scrub paths are either ``"<channel>"`` (the whole channel was dropped) or
    # ``"<channel>/<key>"`` (a manuscript key was dropped from a dict-valued
    # channel). The nested form is not a nicety: LangGraph stages the entire input
    # state into the special ``__start__`` channel as one dict before distributing
    # it to real channels, so scrubbing only top-level channel names leaves the
    # full manuscript sitting inside ``__start__``. A test asserts exactly this.
    _PATH_SEP = "/"

    @staticmethod
    def _scrub_mapping(value: Any) -> Tuple[Any, list[str]]:
        """Drop manuscript keys from a write or channel payload, whatever its shape.

        Three shapes have to be handled, and the third one is not hypothetical --
        it is a leak a cross-process test found in the first version of this
        method, which handled only ``dict``:

        ``dict``
            The ordinary case, including ``__start__``, which stages the entire
            input state as one dict.
        ``list``/``tuple``
            Fan-out writes arrive as a sequence.
        :class:`~langgraph.types.Send`
            ``route_to_reviewer_panel`` dispatches ``Send("reviewer_panel_node",
            {**state, "reviewer_type": rt})`` -- the **entire state**, manuscript
            included, as the task argument. LangGraph persists those Sends as
            pending writes on the ``__pregel_tasks`` channel, so a scrubber that
            only understood dicts wrote the full manuscript to disk once per
            persona while every dict-shaped assertion still passed.

        Returns the cleaned value and the manuscript key names removed anywhere
        inside it. Key names, not paths: rehydration puts each one back wherever
        it finds a container that should have it.
        """
        if isinstance(value, Send):
            clean_arg, removed = NoesisPostgresSaver._scrub_mapping(value.arg)
            if not removed:
                return value, []
            return Send(value.node, clean_arg), removed
        if isinstance(value, (list, tuple)):
            cleaned = []
            removed: list[str] = []
            for item in value:
                clean_item, item_removed = NoesisPostgresSaver._scrub_mapping(item)
                cleaned.append(clean_item)
                removed.extend(item_removed)
            if not removed:
                return value, []
            return cleaned, sorted(set(removed))
        if not isinstance(value, dict):
            return value, []
        removed = sorted(k for k in value if k in MANUSCRIPT_CHANNELS)
        if not removed:
            return value, []
        return {k: v for k, v in value.items() if k not in MANUSCRIPT_CHANNELS}, removed

    def _rehydrate_mapping(self, value: Any, removed: Sequence[str]) -> Any:
        """Inverse of :meth:`_scrub_mapping`, following the same three shapes."""
        if not removed:
            return value
        if isinstance(value, Send):
            return Send(value.node, self._rehydrate_mapping(value.arg, removed))
        if isinstance(value, (list, tuple)):
            return [self._rehydrate_mapping(item, removed) for item in value]
        if isinstance(value, dict):
            return {**value, **{key: self.rehydrate[key] for key in removed}}
        return value

    def _scrub_channel_values(
        self, values: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], list[str]]:
        clean: Dict[str, Any] = {}
        scrubbed: list[str] = []
        for key, value in values.items():
            if key in MANUSCRIPT_CHANNELS:
                scrubbed.append(key)
                continue
            nested_clean, removed = self._scrub_mapping(value)
            clean[key] = nested_clean
            scrubbed.extend(f"{key}{self._PATH_SEP}{r}" for r in removed)
        return clean, scrubbed

    def _rehydrate_channel_values(
        self, values: Dict[str, Any], scrubbed: Sequence[str]
    ) -> Dict[str, Any]:
        needed = [
            path.split(self._PATH_SEP, 1)[-1] if self._PATH_SEP in path else path
            for path in scrubbed
        ]
        missing = sorted({n for n in needed if n not in self.rehydrate})
        if missing:
            raise CheckpointRehydrationError(
                f"Checkpoint omits manuscript channel(s) {missing} by design; "
                "re-supply them from draft storage to resume. They are never "
                "persisted, so they cannot be recovered from the checkpoint row."
            )
        out = dict(values)
        nested_by_channel: Dict[str, list[str]] = {}
        for path in scrubbed:
            if self._PATH_SEP in path:
                channel, key = path.split(self._PATH_SEP, 1)
                nested_by_channel.setdefault(channel, []).append(key)
            else:
                out[path] = self.rehydrate[path]
        for channel, keys in nested_by_channel.items():
            out[channel] = self._rehydrate_mapping(out.get(channel), keys)
        return out

    def _scrub_checkpoint(self, checkpoint: Checkpoint) -> Tuple[Checkpoint, list[str]]:
        """Return a copy with manuscript content removed, plus the scrub paths.

        ``channel_versions`` is left intact on purpose. LangGraph uses it to decide
        which channels a resumed task has already seen; rewriting it to hide the
        scrubbed channels would make the graph think those channels never had a
        value and re-trigger the nodes that produce them. The values come back via
        :meth:`_rehydrate_checkpoint` instead, so versions and values stay
        consistent from the graph's point of view.
        """
        values = checkpoint.get("channel_values") or {}
        clean, scrubbed = self._scrub_channel_values(values)
        if not scrubbed:
            return checkpoint, []
        copy = dict(checkpoint)
        copy["channel_values"] = clean
        return copy, scrubbed  # type: ignore[return-value]

    def _rehydrate_checkpoint(
        self, checkpoint: Checkpoint, scrubbed: Sequence[str]
    ) -> Checkpoint:
        """Put caller-supplied manuscript channels back before handing to LangGraph."""
        if not scrubbed:
            return checkpoint
        copy = dict(checkpoint)
        copy["channel_values"] = self._rehydrate_channel_values(
            dict(checkpoint.get("channel_values") or {}), scrubbed
        )
        return copy  # type: ignore[return-value]

    # -- sync protocol ------------------------------------------------------

    def put(
        self,
        config: Dict[str, Any],
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> Dict[str, Any]:
        configurable = config.get("configurable", {})
        thread_id = configurable["thread_id"]
        checkpoint_ns = configurable.get("checkpoint_ns", "") or ""
        parent_id = configurable.get("checkpoint_id")
        checkpoint_id = checkpoint["id"]

        scrubbed_cp, scrubbed = self._scrub_checkpoint(checkpoint)
        type_, payload = self.serde.dumps_typed(scrubbed_cp)
        digest = hashlib.sha256(payload).hexdigest()

        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO public.noesis_lg_checkpoints (
                    thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id,
                    type, checkpoint, metadata, scrubbed_channels, payload_sha256,
                    user_id, expires_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s,
                        now() + make_interval(hours => %s))
                ON CONFLICT (thread_id, checkpoint_ns, checkpoint_id) DO UPDATE SET
                    checkpoint = EXCLUDED.checkpoint,
                    metadata = EXCLUDED.metadata,
                    scrubbed_channels = EXCLUDED.scrubbed_channels,
                    payload_sha256 = EXCLUDED.payload_sha256
                """,
                (
                    thread_id,
                    checkpoint_ns,
                    checkpoint_id,
                    parent_id,
                    type_,
                    psycopg2_binary(payload),
                    json.dumps(_scrub_metadata(dict(metadata or {})), default=str),
                    json.dumps(scrubbed),
                    digest,
                    self.user_id,
                    self.ttl_hours,
                ),
            )

        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint_id,
            }
        }

    def put_writes(
        self,
        config: Dict[str, Any],
        writes: Sequence[Tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        """Persist a completed task's pending writes.

        Without this, a crash *inside* a superstep re-runs every task in it. For
        the reviewer fan-out that means one persona failing re-charges for all
        three -- ~$0.129 rather than ~$0.043.

        Writes to ``MANUSCRIPT_CHANNELS`` are dropped rather than stored, for the
        same reason the checkpoint scrubs them; the value is re-supplied through
        ``rehydrate``.
        """
        configurable = config.get("configurable", {})
        thread_id = configurable["thread_id"]
        checkpoint_ns = configurable.get("checkpoint_ns", "") or ""
        checkpoint_id = configurable["checkpoint_id"]

        rows = []
        for idx, (channel, value) in enumerate(writes):
            if channel in MANUSCRIPT_CHANNELS:
                # Whole-channel manuscript writes are dropped, not stored. The
                # value is re-supplied through ``rehydrate`` on load, so nothing is
                # lost; the only channel a node ever writes here is ``structure``,
                # produced by a node that makes no LLM call.
                continue
            # Structured writes -- ``__start__`` (the entire input state as one
            # dict) and ``__pregel_tasks`` (the reviewer fan-out's ``Send``
            # objects, each carrying a full copy of state) -- get the same nested
            # scrub as checkpoints.
            clean, removed = self._scrub_mapping(value)
            type_, payload = self.serde.dumps_typed(clean)
            rows.append(
                (
                    thread_id,
                    checkpoint_ns,
                    checkpoint_id,
                    task_id,
                    idx,
                    channel,
                    type_,
                    psycopg2_binary(payload),
                    json.dumps(removed),
                    self.ttl_hours,
                )
            )
        if not rows:
            return

        with self._cursor() as cur:
            cur.executemany(
                """
                INSERT INTO public.noesis_lg_checkpoint_writes (
                    thread_id, checkpoint_ns, checkpoint_id, task_id, idx,
                    channel, type, blob, scrubbed_channels, expires_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb,
                        now() + make_interval(hours => %s))
                ON CONFLICT (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
                DO UPDATE SET channel = EXCLUDED.channel,
                              type = EXCLUDED.type,
                              blob = EXCLUDED.blob,
                              scrubbed_channels = EXCLUDED.scrubbed_channels
                """,
                rows,
            )

    def get_tuple(self, config: Dict[str, Any]) -> Optional[CheckpointTuple]:
        configurable = config.get("configurable", {})
        thread_id = configurable["thread_id"]
        checkpoint_ns = configurable.get("checkpoint_ns", "") or ""
        checkpoint_id = get_checkpoint_id(config)

        with self._cursor() as cur:
            if checkpoint_id:
                cur.execute(
                    """
                    SELECT checkpoint_id, parent_checkpoint_id, type, checkpoint,
                           metadata, scrubbed_channels, payload_sha256
                      FROM public.noesis_lg_checkpoints
                     WHERE thread_id = %s AND checkpoint_ns = %s AND checkpoint_id = %s
                    """,
                    (thread_id, checkpoint_ns, checkpoint_id),
                )
            else:
                cur.execute(
                    """
                    SELECT checkpoint_id, parent_checkpoint_id, type, checkpoint,
                           metadata, scrubbed_channels, payload_sha256
                      FROM public.noesis_lg_checkpoints
                     WHERE thread_id = %s AND checkpoint_ns = %s
                     ORDER BY created_at DESC, checkpoint_id DESC
                     LIMIT 1
                    """,
                    (thread_id, checkpoint_ns),
                )
            row = cur.fetchone()
            if row is None:
                return None
            tuple_ = self._row_to_tuple(thread_id, checkpoint_ns, row)

            cur.execute(
                """
                SELECT task_id, channel, type, blob, scrubbed_channels
                  FROM public.noesis_lg_checkpoint_writes
                 WHERE thread_id = %s AND checkpoint_ns = %s AND checkpoint_id = %s
                 ORDER BY task_id, idx
                """,
                (thread_id, checkpoint_ns, tuple_.checkpoint["id"]),
            )
            pending = []
            for task_id, channel, type_, blob, scrubbed in cur.fetchall():
                value = self.serde.loads_typed((type_, bytes(blob)))
                missing = [k for k in (scrubbed or []) if k not in self.rehydrate]
                if missing:
                    raise CheckpointRehydrationError(
                        f"Pending write for channel '{channel}' omits manuscript "
                        f"key(s) {missing} by design; re-supply them to resume."
                    )
                value = self._rehydrate_mapping(value, scrubbed or [])
                pending.append((task_id, channel, value))

        return tuple_._replace(pending_writes=pending)

    def _row_to_tuple(self, thread_id: str, checkpoint_ns: str, row) -> CheckpointTuple:
        (
            checkpoint_id,
            parent_id,
            type_,
            blob,
            metadata,
            scrubbed_channels,
            digest,
        ) = row

        payload = bytes(blob)
        actual = hashlib.sha256(payload).hexdigest()
        if actual != digest:
            # Deliberately fatal. A partially-written row deserialized "best
            # effort" would resume the graph with silently missing channels, which
            # is worse than restarting: the run would still cost money and would
            # produce output nobody could trust.
            raise CheckpointCorruptError(
                f"Checkpoint {thread_id}/{checkpoint_id} failed integrity check "
                f"(expected sha256 {digest[:12]}..., got {actual[:12]}...)"
            )
        try:
            checkpoint = self.serde.loads_typed((type_, payload))
        except Exception as exc:
            raise CheckpointCorruptError(
                f"Checkpoint {thread_id}/{checkpoint_id} could not be deserialized: "
                f"{safe_exception(exc)}"
            ) from exc
        if not isinstance(checkpoint, dict) or "channel_values" not in checkpoint:
            raise CheckpointCorruptError(
                f"Checkpoint {thread_id}/{checkpoint_id} is structurally invalid"
            )

        scrubbed = list(scrubbed_channels or [])
        checkpoint = self._rehydrate_checkpoint(checkpoint, scrubbed)

        parent_config = (
            {
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "checkpoint_id": parent_id,
                }
            }
            if parent_id
            else None
        )
        return CheckpointTuple(
            config={
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "checkpoint_id": checkpoint_id,
                }
            },
            checkpoint=checkpoint,
            metadata=metadata or {},
            parent_config=parent_config,
            pending_writes=[],
        )

    def list(
        self,
        config: Optional[Dict[str, Any]],
        *,
        filter: Optional[Dict[str, Any]] = None,
        before: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
    ) -> Iterator[CheckpointTuple]:
        configurable = (config or {}).get("configurable", {})
        thread_id = configurable.get("thread_id")
        checkpoint_ns = configurable.get("checkpoint_ns", "") or ""
        if not thread_id:
            return iter(())

        sql = """
            SELECT checkpoint_id, parent_checkpoint_id, type, checkpoint,
                   metadata, scrubbed_channels, payload_sha256
              FROM public.noesis_lg_checkpoints
             WHERE thread_id = %s AND checkpoint_ns = %s
        """
        params: list[Any] = [thread_id, checkpoint_ns]
        before_id = get_checkpoint_id(before) if before else None
        if before_id:
            sql += " AND checkpoint_id < %s"
            params.append(before_id)
        sql += " ORDER BY created_at DESC, checkpoint_id DESC"
        if limit:
            sql += " LIMIT %s"
            params.append(limit)

        with self._cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        return iter(
            [self._row_to_tuple(thread_id, checkpoint_ns, row) for row in rows]
        )

    def delete_thread(self, thread_id: str) -> None:
        """Remove every checkpoint for a thread. Called on successful completion."""
        with self._cursor() as cur:
            cur.execute(
                "DELETE FROM public.noesis_lg_checkpoint_writes WHERE thread_id = %s",
                (thread_id,),
            )
            cur.execute(
                "DELETE FROM public.noesis_lg_checkpoints WHERE thread_id = %s",
                (thread_id,),
            )

    # -- async protocol -----------------------------------------------------
    #
    # psycopg2 is synchronous and the graph runs under ``ainvoke``, so each async
    # method hands its sync twin to a worker thread. Blocking the event loop here
    # would stall every other in-flight analysis in the same worker.

    async def aput(
        self,
        config: Dict[str, Any],
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(
            self.put, config, checkpoint, metadata, new_versions
        )

    async def aput_writes(
        self,
        config: Dict[str, Any],
        writes: Sequence[Tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        await asyncio.to_thread(self.put_writes, config, writes, task_id, task_path)

    async def aget_tuple(self, config: Dict[str, Any]) -> Optional[CheckpointTuple]:
        return await asyncio.to_thread(self.get_tuple, config)

    async def alist(
        self,
        config: Optional[Dict[str, Any]],
        *,
        filter: Optional[Dict[str, Any]] = None,
        before: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
    ) -> AsyncIterator[CheckpointTuple]:
        items = await asyncio.to_thread(
            lambda: list(self.list(config, filter=filter, before=before, limit=limit))
        )
        for item in items:
            yield item

    async def adelete_thread(self, thread_id: str) -> None:
        await asyncio.to_thread(self.delete_thread, thread_id)


def psycopg2_binary(payload: bytes):
    """Wrap bytes so psycopg2 sends them as BYTEA rather than escaping as text."""
    import psycopg2

    return psycopg2.Binary(payload)


def build_checkpointer(
    *,
    rehydrate: Optional[Dict[str, Any]] = None,
    user_id: Optional[str] = None,
) -> Optional[NoesisPostgresSaver]:
    """Construct the checkpointer, or ``None`` to compile the graph as before.

    Returns ``None`` -- meaning "behave exactly like today" -- when the flag is
    off, when no DSN is configured, or when construction fails for any reason.
    Checkpointing is an optimisation; it must never be the thing that takes an
    analysis down.
    """
    if not checkpointing_enabled():
        return None
    dsn = checkpoint_dsn()
    if not dsn:
        logger.warning(
            "[Checkpoint] NOESIS_CHECKPOINT_ENABLED is set but "
            "NOESIS_CHECKPOINT_DB_URL is not; running without a checkpointer"
        )
        return None
    try:
        ttl = int(os.environ.get("NOESIS_CHECKPOINT_TTL_HOURS", DEFAULT_TTL_HOURS))
    except ValueError:
        ttl = DEFAULT_TTL_HOURS
    try:
        return NoesisPostgresSaver(
            dsn, rehydrate=rehydrate, ttl_hours=ttl, user_id=user_id
        )
    except Exception as exc:
        logger.error(
            "[Checkpoint] Failed to build checkpointer, continuing without: %s",
            safe_exception(exc),
        )
        return None

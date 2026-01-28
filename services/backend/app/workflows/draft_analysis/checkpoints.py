"""
Checkpoint Persistence for Draft Analysis Workflow

Implements PostgreSQL-based checkpoint storage for LangGraph workflows.
This allows workflows to be paused, resumed, and recovered from failures.

Checkpoints are stored in the database with the following information:
- thread_id: Unique identifier for the workflow (e.g., draft_id)
- checkpoint_data: Serialized state at the checkpoint
- timestamp: When the checkpoint was created
- node_name: Which node created the checkpoint
- status: Current workflow status
"""

from typing import Dict, Any, Optional
import json
import datetime
from app.core.supabase_client import supabase
from app.core.logging_config import get_logger

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
        status: str = "in_progress"
    ) -> str:
        """
        Save a workflow checkpoint to the database.

        Args:
            thread_id: Unique identifier for this workflow (e.g., draft_id)
            checkpoint_data: The state to checkpoint
            node_name: Name of the node that created this checkpoint
            status: Workflow status (in_progress, completed, failed)

        Returns:
            Checkpoint ID
        """
        try:
            checkpoint_id = f"{thread_id}_{node_name}_{int(datetime.datetime.utcnow().timestamp())}"

            checkpoint_record = {
                "id": checkpoint_id,
                "thread_id": thread_id,
                "checkpoint_data": json.dumps(checkpoint_data),
                "node_name": node_name,
                "status": status,
                "created_at": datetime.datetime.utcnow().isoformat()
            }

            result = supabase.table(self.table_name).insert(checkpoint_record).execute()

            if result.data:
                logger.info(f"Saved checkpoint: {checkpoint_id} (node: {node_name})")
                return checkpoint_id
            else:
                raise Exception("Failed to save checkpoint: no data returned")

        except Exception as e:
            logger.error(f"Failed to save checkpoint for thread {thread_id}: {e}")
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
            logger.error(f"Failed to load checkpoint for thread {thread_id}: {e}")
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
            logger.error(f"Failed to list checkpoints for thread {thread_id}: {e}")
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
            logger.error(f"Failed to delete checkpoints for thread {thread_id}: {e}")
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
            logger.error(f"Failed to update checkpoint status for thread {thread_id}: {e}")
            return False


# Global checkpoint saver instance
_checkpoint_saver = None


def get_checkpoint_saver() -> PostgresCheckpointSaver:
    """Get or create global checkpoint saver instance."""
    global _checkpoint_saver
    if _checkpoint_saver is None:
        _checkpoint_saver = PostgresCheckpointSaver()
    return _checkpoint_saver

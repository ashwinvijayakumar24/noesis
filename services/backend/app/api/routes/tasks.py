"""
Celery task status endpoints for monitoring background task progress.

Phase 3.4: Production-ready task status tracking.
"""

from fastapi import APIRouter, HTTPException, Depends, Header
from app.core.supabase_client import supabase
from app.core.security_middleware import SecureAuthValidator
from app.celery_app import celery_app
from celery.result import AsyncResult
import logging

router = APIRouter(prefix="/tasks", tags=["tasks"])
logger = logging.getLogger(__name__)


# Helper to extract user info from token
def get_current_user(authorization: str = Header(None)):
    if supabase is None:
        raise HTTPException(
            status_code=500,
            detail="Supabase not configured"  # Don't expose environment details
        )

    # Use secure token validator
    token = SecureAuthValidator.validate_bearer_token(authorization)

    try:
        user = supabase.auth.get_user(token)
        return user.user.id
    except Exception as e:
        logger.warning(f"Token validation failed: {str(e)}")
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token"  # Don't expose error details
        )


@router.get("/{task_id}/status")
async def get_task_status(task_id: str, user_id: str = Depends(get_current_user)):
    """
    Get the status of a Celery background task.

    Returns:
        - state: PENDING, STARTED, SUCCESS, FAILURE, RETRY, REVOKED
        - info: Task result or error information
        - progress: Task progress metadata (if available)

    States:
        - PENDING: Task is waiting to be executed
        - STARTED: Task has started executing
        - SUCCESS: Task completed successfully
        - FAILURE: Task failed (will retry or give up)
        - RETRY: Task is being retried
        - REVOKED: Task was cancelled

    Example response (success):
    {
        "task_id": "abc123",
        "state": "SUCCESS",
        "info": {
            "status": "success",
            "document_id": "xyz",
            "task_id": "abc123",
            "retries": 0
        },
        "ready": true,
        "successful": true,
        "failed": false
    }

    Example response (failure):
    {
        "task_id": "abc123",
        "state": "FAILURE",
        "info": {
            "error": "ValueError: Document not found",
            "error_type": "ValueError"
        },
        "ready": true,
        "successful": false,
        "failed": true,
        "retries": 3
    }
    """
    print(f"[TASK-STATUS] Checking status for task_id={task_id}, user_id={user_id}")

    try:
        # Get task result from Celery
        task_result = AsyncResult(task_id, app=celery_app)

        # Build response with task state and metadata
        response = {
            "task_id": task_id,
            "state": task_result.state,
            "info": None,
            "ready": task_result.ready(),
            "successful": task_result.successful() if task_result.ready() else False,
            "failed": task_result.failed() if task_result.ready() else False,
        }

        # Add task result/error info
        if task_result.state == "PENDING":
            response["info"] = {"message": "Task is waiting to start"}
        elif task_result.state == "STARTED":
            response["info"] = {"message": "Task is running"}
        elif task_result.state == "SUCCESS":
            response["info"] = task_result.result
        elif task_result.state == "FAILURE":
            # Get exception info
            exc_info = task_result.info
            response["info"] = {
                "error": str(exc_info),
                "error_type": type(exc_info).__name__ if exc_info else "Unknown"
            }
        elif task_result.state == "RETRY":
            response["info"] = {
                "message": "Task is being retried",
                "retries": task_result.info.get("retries", 0) if task_result.info else 0
            }
        elif task_result.state == "REVOKED":
            response["info"] = {"message": "Task was cancelled"}
        else:
            # Custom state or unknown state
            response["info"] = task_result.info

        print(f"[TASK-STATUS] Task {task_id} state: {task_result.state}")
        return response

    except Exception as e:
        print(f"[TASK-STATUS] ERROR: Failed to get task status: {type(e).__name__}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve task status: {str(e)}"
        )


@router.post("/{task_id}/cancel")
async def cancel_task(task_id: str, user_id: str = Depends(get_current_user)):
    """
    Cancel a running Celery task.

    Note: This sends a revoke signal to the task. If the task has already started,
    it may not stop immediately. Tasks are configured to terminate when possible.

    Returns:
        - message: Confirmation message
        - task_id: The cancelled task ID
        - revoked: True if revoke signal sent successfully
    """
    print(f"[TASK-CANCEL] Cancelling task_id={task_id}, user_id={user_id}")

    try:
        # Revoke the task (terminate=True kills the worker process if already started)
        celery_app.control.revoke(task_id, terminate=True, signal='SIGKILL')

        print(f"[TASK-CANCEL] Task {task_id} revoked successfully")

        return {
            "message": "Task cancelled successfully",
            "task_id": task_id,
            "revoked": True
        }

    except Exception as e:
        print(f"[TASK-CANCEL] ERROR: Failed to cancel task: {type(e).__name__}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to cancel task: {str(e)}"
        )


@router.get("/active")
async def get_active_tasks(user_id: str = Depends(get_current_user)):
    """
    Get all active tasks across all workers.

    Returns a list of currently executing tasks with their IDs and names.

    Note: This requires Celery workers to be running with task events enabled.
    """
    print(f"[TASK-ACTIVE] Fetching active tasks for user_id={user_id}")

    try:
        # Get active tasks from all workers
        inspect = celery_app.control.inspect()
        active_tasks = inspect.active()

        if not active_tasks:
            return {
                "message": "No active tasks or workers not responding",
                "tasks": [],
                "worker_count": 0
            }

        # Flatten tasks from all workers
        all_tasks = []
        for worker_name, tasks in active_tasks.items():
            for task in tasks:
                all_tasks.append({
                    "task_id": task.get("id"),
                    "task_name": task.get("name"),
                    "worker": worker_name,
                    "args": task.get("args", []),
                    "kwargs": task.get("kwargs", {})
                })

        print(f"[TASK-ACTIVE] Found {len(all_tasks)} active tasks across {len(active_tasks)} workers")

        return {
            "tasks": all_tasks,
            "worker_count": len(active_tasks),
            "total_tasks": len(all_tasks)
        }

    except Exception as e:
        print(f"[TASK-ACTIVE] ERROR: Failed to get active tasks: {type(e).__name__}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve active tasks: {str(e)}"
        )


@router.get("/stats")
async def get_task_stats(user_id: str = Depends(get_current_user)):
    """
    Get Celery worker statistics and queue information.

    Returns:
        - workers: Number of active workers
        - queues: Queue names and message counts
        - stats: Worker statistics (processed, active, etc.)
    """
    print(f"[TASK-STATS] Fetching Celery statistics for user_id={user_id}")

    try:
        inspect = celery_app.control.inspect()

        # Get worker stats
        stats = inspect.stats()
        active = inspect.active()
        reserved = inspect.reserved()
        scheduled = inspect.scheduled()

        if not stats:
            return {
                "message": "No workers available",
                "workers": 0,
                "stats": {}
            }

        # Build response
        response = {
            "workers": len(stats),
            "worker_details": {},
            "total_active": sum(len(tasks) for tasks in (active or {}).values()),
            "total_reserved": sum(len(tasks) for tasks in (reserved or {}).values()),
            "total_scheduled": sum(len(tasks) for tasks in (scheduled or {}).values()),
        }

        # Add per-worker details
        for worker_name, worker_stats in stats.items():
            response["worker_details"][worker_name] = {
                "pool": worker_stats.get("pool", {}),
                "total_processed": worker_stats.get("total", {}),
                "active_tasks": len((active or {}).get(worker_name, [])),
                "reserved_tasks": len((reserved or {}).get(worker_name, [])),
                "scheduled_tasks": len((scheduled or {}).get(worker_name, [])),
            }

        print(f"[TASK-STATS] Found {len(stats)} active workers")
        return response

    except Exception as e:
        print(f"[TASK-STATS] ERROR: Failed to get task stats: {type(e).__name__}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve task statistics: {str(e)}"
        )

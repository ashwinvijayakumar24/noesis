"""
Background Task Manager
Simple ThreadPoolExecutor for running long-running tasks in background.
"""

from concurrent.futures import ThreadPoolExecutor
import threading

# Global thread pool executor (4 workers for concurrent analysis)
_executor = None
_lock = threading.Lock()


def get_executor() -> ThreadPoolExecutor:
    """
    Get or create the global ThreadPoolExecutor.
    Thread-safe singleton pattern.
    """
    global _executor
    if _executor is None:
        with _lock:
            if _executor is None:  # Double-check locking
                _executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="bg-task")
                print("[BACKGROUND] ThreadPoolExecutor initialized with 4 workers")
    return _executor


def submit_task(func, *args, **kwargs):
    """
    Submit a task to run in the background.

    Args:
        func: The function to execute
        *args: Positional arguments for the function
        **kwargs: Keyword arguments for the function

    Returns:
        Future object representing the pending execution
    """
    executor = get_executor()
    future = executor.submit(func, *args, **kwargs)
    print(f"[BACKGROUND] Submitted task: {func.__name__}")
    return future


def shutdown(wait=True):
    """
    Shutdown the executor gracefully.
    Should be called on application shutdown.
    """
    global _executor
    if _executor:
        print(f"[BACKGROUND] Shutting down executor (wait={wait})")
        _executor.shutdown(wait=wait)
        _executor = None

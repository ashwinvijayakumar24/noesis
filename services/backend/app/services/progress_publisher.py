"""
Progress Publisher — Redis pub/sub for draft analysis progress events
"""
import json
import logging
import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

REDIS_URL = "redis://redis:6379/0"


async def publish_progress(draft_id: str, step: str, percent: int, message: str) -> None:
    """Publish a progress event to the Redis pub/sub channel for a draft."""
    try:
        r = aioredis.from_url(REDIS_URL)
        event = json.dumps({"type": "progress", "step": step, "progress": percent, "message": message})
        await r.publish(f"progress:{draft_id}", event)
        await r.aclose()
    except Exception as e:
        logger.warning(f"Failed to publish progress for draft {draft_id}: {e}")

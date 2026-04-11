"""
Progress Publisher — Redis pub/sub for draft analysis progress events
"""
import json
import logging
import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

REDIS_URL = "redis://redis:6379/0"


async def publish_progress(draft_id: str, step: str, percent: int, message: str) -> None:
    """Publish a progress event to the Redis pub/sub channel for a draft.

    Also writes the latest progress to a key so late WebSocket subscribers
    can retrieve the current state immediately on connect.
    """
    try:
        r = aioredis.from_url(REDIS_URL)
        event = json.dumps({"type": "progress", "step": step, "progress": percent, "message": message})
        # Pub/sub for live subscribers
        await r.publish(f"progress:{draft_id}", event)
        # Key-value for late subscribers (30 min TTL)
        await r.set(f"progress:{draft_id}:latest", event, ex=1800)
        await r.close()
    except Exception as e:
        logger.warning(f"Failed to publish progress for draft {draft_id}: {e}")

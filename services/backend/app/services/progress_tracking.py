"""
Shared progress snapshot helpers.

Draft analysis already uses live pub/sub over Redis. Task 09 extends the same
snapshot pattern to document analysis and Literature Map so the frontend can
poll one latest-known progress payload without adding new transports.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

import redis as redis_lib
import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

REDIS_URL = "redis://redis:6379/0"
PROGRESS_TTL_SECONDS = 7200


def _snapshot_key(resource_type: str, resource_id: str) -> str:
    if resource_type == "draft":
        return f"progress:{resource_id}:latest"
    return f"progress:{resource_type}:{resource_id}:latest"


def _channel_key(resource_type: str, resource_id: str) -> str:
    if resource_type == "draft":
        return f"progress:{resource_id}"
    return f"progress:{resource_type}:{resource_id}"


def _build_event(
    *,
    resource_type: str,
    resource_id: str,
    step: str,
    percent: int,
    message: str,
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    payload = {
        "type": "progress",
        "resource_type": resource_type,
        "resource_id": resource_id,
        "stage": step,
        "step": step,
        "label": message,
        "message": message,
        "percent": percent,
        "progress": percent,
    }
    if extra:
        payload.update(extra)
    return payload


def store_progress_snapshot(
    resource_type: str,
    resource_id: str,
    step: str,
    percent: int,
    message: str,
    extra: Optional[dict[str, Any]] = None,
) -> None:
    try:
        redis_conn = redis_lib.from_url(REDIS_URL, decode_responses=True)
        event = json.dumps(
            _build_event(
                resource_type=resource_type,
                resource_id=resource_id,
                step=step,
                percent=percent,
                message=message,
                extra=extra,
            )
        )
        redis_conn.set(_snapshot_key(resource_type, resource_id), event, ex=PROGRESS_TTL_SECONDS)
        redis_conn.close()
    except Exception as exc:
        logger.warning(
            "Failed to store progress snapshot for %s %s: %s",
            resource_type,
            resource_id,
            exc,
        )


async def publish_progress_event(
    resource_type: str,
    resource_id: str,
    step: str,
    percent: int,
    message: str,
    *,
    publish_live: bool = False,
    extra: Optional[dict[str, Any]] = None,
) -> None:
    try:
        redis_conn = aioredis.from_url(REDIS_URL)
        event = json.dumps(
            _build_event(
                resource_type=resource_type,
                resource_id=resource_id,
                step=step,
                percent=percent,
                message=message,
                extra=extra,
            )
        )
        if publish_live:
            await redis_conn.publish(_channel_key(resource_type, resource_id), event)
        await redis_conn.set(_snapshot_key(resource_type, resource_id), event, ex=PROGRESS_TTL_SECONDS)
        await redis_conn.close()
    except Exception as exc:
        logger.warning(
            "Failed to publish progress for %s %s: %s",
            resource_type,
            resource_id,
            exc,
        )


async def publish_progress(draft_id: str, step: str, percent: int, message: str) -> None:
    await publish_progress_event(
        "draft",
        draft_id,
        step,
        percent,
        message,
        publish_live=True,
    )


def get_progress_snapshot(resource_type: str, resource_id: str) -> Optional[dict[str, Any]]:
    try:
        redis_conn = redis_lib.from_url(REDIS_URL, decode_responses=True)
        raw_value = redis_conn.get(_snapshot_key(resource_type, resource_id))
        redis_conn.close()
        if not raw_value:
            return None
        return json.loads(raw_value)
    except Exception as exc:
        logger.warning(
            "Failed to read progress snapshot for %s %s: %s",
            resource_type,
            resource_id,
            exc,
        )
        return None


def clear_progress_snapshot(resource_type: str, resource_id: str) -> None:
    try:
        redis_conn = redis_lib.from_url(REDIS_URL, decode_responses=True)
        redis_conn.delete(_snapshot_key(resource_type, resource_id))
        redis_conn.close()
    except Exception as exc:
        logger.warning(
            "Failed to clear progress snapshot for %s %s: %s",
            resource_type,
            resource_id,
            exc,
        )

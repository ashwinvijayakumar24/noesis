"""
Shared API error helpers for trust-sensitive frontend surfaces.
"""

from typing import Any, Optional

from fastapi import HTTPException


def build_error_detail(
    *,
    code: str,
    title: str,
    message: str,
    details: Optional[Any] = None,
    next_action: Optional[str] = None,
    retryable: Optional[bool] = None,
    **extras: Any,
) -> dict[str, Any]:
    detail: dict[str, Any] = {
        "code": code,
        "title": title,
        "message": message,
    }

    if details not in (None, [], {}):
        detail["details"] = details
    if next_action:
        detail["next_action"] = next_action
    if retryable is not None:
        detail["retryable"] = retryable

    for key, value in extras.items():
        if value is not None:
            detail[key] = value

    return detail


def raise_api_error(status_code: int, **kwargs: Any) -> None:
    raise HTTPException(status_code=status_code, detail=build_error_detail(**kwargs))

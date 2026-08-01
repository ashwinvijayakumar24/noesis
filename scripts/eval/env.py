"""Load `services/backend/.env` for eval scripts.

The eval harness runs on the host, not in the container, so it never inherits
the environment `docker-compose` injects into the backend. Nothing in
`scripts/eval/` loaded a `.env` file, and nothing in `app/` does either -- the
container gets its variables from compose, so the gap only shows up on the host.

The failure mode is quiet rather than loud, which is why this exists: a missing
`OPENALEX_API_KEY` does not raise, it silently drops the caller onto the $0.10/day
unauthenticated tier instead of the $1.00/day authenticated one. A missing
`OPENAI_API_KEY` fails later and further away, inside a client constructor.

Deliberately does NOT override a variable that is already set. An explicit
`export` in the shell, or a value passed by a test harness, must win over a file
on disk -- otherwise `NOESIS_LLM_KILL_SWITCH=1 python3 ...` could be silently
undone by whatever happens to sit in `.env`.
"""

from __future__ import annotations

import os
from pathlib import Path

BACKEND_ENV = Path(__file__).resolve().parents[2] / "services" / "backend" / ".env"


def load_backend_env(path: Path | None = None, *, override: bool = False) -> list[str]:
    """Load the backend `.env` into `os.environ`.

    Returns the NAMES of the variables it set -- never the values, so a caller
    can log what happened without leaking a credential.
    """
    env_path = Path(path) if path is not None else BACKEND_ENV
    if not env_path.is_file():
        return []

    try:
        from dotenv import dotenv_values
    except ImportError:  # pragma: no cover - dotenv is in requirements
        return []

    applied: list[str] = []
    for key, value in dotenv_values(env_path).items():
        if value is None:
            continue
        if not override and os.environ.get(key):
            continue
        os.environ[key] = value
        applied.append(key)
    return applied


def describe_credential(name: str) -> str:
    """`name=set` / `name=unset`, for logging. Never returns the value."""
    return f"{name}={'set' if os.environ.get(name) else 'unset'}"

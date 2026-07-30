"""Shared fixtures. Everything DB-backed SKIPS (never fails) without Docker.

The suite must stay green on a machine with no database, otherwise CI teaches
people to ignore red, which is worse than having no CI.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _db_module():
    try:
        from scripts.eval import db  # noqa

        return db
    except Exception:
        return None


eval_db = _db_module()
DB_UP = bool(eval_db and eval_db.healthcheck())

requires_db = pytest.mark.skipif(
    not DB_UP,
    reason="local pgvector unreachable; run `cd infra && docker compose --profile core up -d pgvector`",
)


@pytest.fixture
def conn():
    with eval_db.get_connection() as connection:
        connection.autocommit = False
        yield connection

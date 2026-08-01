"""Authorization tests for the draft-creation endpoints' ``project_id``.

Sibling of ``test_draft_ws_authz.py``. Same bug class, opposite direction: the
WebSocket let an authenticated stranger *read* a draft they did not own; these
two endpoints let an authenticated stranger *write* a draft into a project they
did not own. ``POST /drafts/upload`` and ``POST /drafts/analyze-from-extension``
both took ``project_id`` from the request and filed the row against it without
ever asking whose project it was.

Plus an existence oracle: the version-number probe inside ``/upload`` queried
``drafts`` by ``project_id`` + ``title`` with no ``user_id`` filter, so a
guessed project id and a guessed title reported another user's version count.

Same properties as the socket fix: ownership looked up rather than claimed,
deny by default, one client-visible message for every cause, every decision
logged.
"""

import asyncio
import sys
import types
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

if "weasyprint" not in sys.modules:
    _fake_weasyprint = types.ModuleType("weasyprint")
    _fake_weasyprint.HTML = MagicMock()
    sys.modules["weasyprint"] = _fake_weasyprint

from app.api.routes import drafts as drafts_routes


OWNER = "user-a-owner"
ATTACKER = "user-b-attacker"
PROJECT = "project-belonging-to-a"
MISSING = "project-that-does-not-exist"


# --- doubles ---------------------------------------------------------------


class _Result:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    """Records every filter applied, so a test can assert on the scoping of a
    read rather than only on its result."""

    def __init__(self, table, store):
        self.table = table
        self.store = store
        self.filters: dict = {}
        self.op = None
        self.payload = None

    def select(self, *_a, **_kw):
        self.op = "select"
        return self

    def insert(self, payload):
        self.op = "insert"
        self.payload = payload
        return self

    def upsert(self, payload, **_kw):
        self.op = "upsert"
        self.payload = payload
        return self

    def eq(self, column, value):
        self.filters[column] = value
        return self

    def order(self, *_a, **_kw):
        return self

    def limit(self, _n):
        return self

    def single(self):
        return self

    def execute(self):
        self.store.queries.append(self)
        if self.op in ("insert", "upsert"):
            self.store.writes.append((self.table, self.payload))
            row = dict(self.payload)
            row.setdefault("id", "new-row-id")
            return _Result([row])
        rows = [
            row
            for row in self.store.rows.get(self.table, [])
            if all(row.get(k) == v for k, v in self.filters.items())
        ]
        return _Result(rows)


class FakeStore:
    def __init__(self, rows):
        self.rows = rows
        self.writes: list = []
        self.queries: list = []


class FakeStorageBucket:
    def __init__(self, store):
        self._store = store

    def upload(self, path, file, file_options=None):
        self._store.writes.append(("storage", path))
        return {"path": path}

    def get_public_url(self, path):
        return f"https://example.invalid/{path}"

    def remove(self, _paths):
        return None


class FakeStorage:
    def __init__(self, store):
        self._store = store

    def from_(self, _bucket):
        return FakeStorageBucket(self._store)


class FakeSupabase:
    def __init__(self, store):
        self.store = store
        self.storage = FakeStorage(store)

    def table(self, name):
        return FakeQuery(name, self.store)


@pytest.fixture
def store(monkeypatch):
    s = FakeStore(
        {
            "projects": [{"id": PROJECT, "user_id": OWNER}],
            "drafts": [
                # Owner's draft, so the version probe has something to find --
                # and so a foreign prober has something to be denied sight of.
                {
                    "id": "existing-draft",
                    "user_id": OWNER,
                    "project_id": PROJECT,
                    "title": "Secret Manuscript",
                    "version": 7,
                },
            ],
        }
    )
    fake = FakeSupabase(s)
    monkeypatch.setattr(drafts_routes, "supabase", fake)
    return s


@pytest.fixture(autouse=True)
def no_rate_limit(monkeypatch):
    """``/upload`` is wrapped in slowapi's 5/minute limiter, which insists on a
    real starlette Request and would refuse the sixth call in this module.
    Rate limiting is orthogonal to authorization; switch it off (restored by
    monkeypatch) so these tests exercise the auth gate and nothing else."""
    monkeypatch.setattr(drafts_routes.limiter, "enabled", False)


@pytest.fixture
def no_celery(monkeypatch):
    """Stop the analysis task from being dispatched, and record if it is."""
    dispatched: list = []

    fake_task = types.SimpleNamespace(
        delay=lambda *a, **kw: dispatched.append((a, kw))
        or types.SimpleNamespace(id="task-1")
    )
    fake_module = types.ModuleType("app.tasks.draft_analysis")
    fake_module.analyze_draft_task = fake_task
    monkeypatch.setitem(sys.modules, "app.tasks.draft_analysis", fake_module)
    return dispatched


class FakeUpload:
    def __init__(self, filename="paper.txt", content=b"x" * 400):
        self.filename = filename
        self.content_type = "text/plain"
        self._content = content

    async def read(self):
        return self._content


@pytest.fixture
def valid_file(monkeypatch):
    async def _ok(_content, _ext):
        return {"valid": True, "can_extract_text": True, "errors": [], "suggestions": []}

    monkeypatch.setattr(drafts_routes, "validate_file_format", _ok)
    return FakeUpload()


def extension_body(project_id):
    return drafts_routes.ExtensionAnalyzeRequest(
        content="A" * 400, title="Overleaf Draft", project_id=project_id
    )


def call_extension(project_id, user_id):
    return asyncio.run(
        drafts_routes.analyze_draft_from_extension(
            body=extension_body(project_id), user_id=user_id
        )
    )


def call_upload(project_id, user_id, upload, title="Secret Manuscript"):
    return asyncio.run(
        drafts_routes.upload_draft(
            request=MagicMock(),
            file=upload,
            project_id=project_id,
            title=title,
            paper_type="journal_article",
            citation_style="auto",
            user_id=user_id,
        )
    )


def drafts_written(store):
    return [payload for table, payload in store.writes if table == "drafts"]


# --- 1. analyze-from-extension ---------------------------------------------


def test_extension_cannot_write_into_another_users_project(store, no_celery):
    with pytest.raises(HTTPException) as exc:
        call_extension(PROJECT, ATTACKER)

    assert exc.value.status_code == 404
    assert exc.value.detail == drafts_routes.PROJECT_ACCESS_DENIAL
    # The point of the test: no row landed in the victim's project, and no blob
    # landed in storage. A status code alone would not have shown this.
    assert drafts_written(store) == []
    assert store.writes == []
    assert no_celery == []


def test_extension_owner_still_works(store, no_celery):
    result = call_extension(PROJECT, OWNER)

    assert result["project_id"] == PROJECT
    assert result["status"] == "processing"
    written = drafts_written(store)
    assert len(written) == 1
    assert written[0]["user_id"] == OWNER
    assert written[0]["project_id"] == PROJECT
    assert len(no_celery) == 1


def test_extension_without_project_id_still_uses_default_project(store, no_celery):
    """The unspecified-project path is untouched: it must still fall back to
    the caller's own most recent project."""
    store.rows["projects"].append({"id": "owners-other-project", "user_id": OWNER})

    result = call_extension(None, OWNER)

    assert result["project_id"] in {PROJECT, "owners-other-project"}
    assert drafts_written(store)[0]["user_id"] == OWNER


def test_extension_unknown_project_denial_is_byte_identical(store, no_celery):
    with pytest.raises(HTTPException) as foreign:
        call_extension(PROJECT, ATTACKER)
    with pytest.raises(HTTPException) as missing:
        call_extension(MISSING, ATTACKER)

    assert (missing.value.status_code, missing.value.detail) == (
        foreign.value.status_code,
        foreign.value.detail,
    )
    assert store.writes == []


# --- 2. upload --------------------------------------------------------------


def test_upload_cannot_write_into_another_users_project(store, no_celery, valid_file):
    with pytest.raises(HTTPException) as exc:
        call_upload(PROJECT, ATTACKER, valid_file)

    assert exc.value.status_code == 404
    assert exc.value.detail == drafts_routes.PROJECT_ACCESS_DENIAL
    assert drafts_written(store) == []
    # Refused before the file was read or stored, so nothing was left behind.
    assert store.writes == []
    assert no_celery == []


def test_upload_owner_still_works(store, no_celery, valid_file):
    result = call_upload(PROJECT, OWNER, valid_file)

    assert "draft" in result
    written = drafts_written(store)
    assert len(written) == 1
    assert written[0]["project_id"] == PROJECT
    assert written[0]["user_id"] == OWNER
    assert len(no_celery) == 1


def test_upload_without_project_id_still_works(store, no_celery, valid_file):
    """Primary ingestion path with no project selected must be unaffected."""
    result = call_upload(None, OWNER, valid_file)

    assert "draft" in result
    assert drafts_written(store)[0]["project_id"] is None


def test_upload_unknown_project_denial_is_byte_identical(store, no_celery, valid_file):
    with pytest.raises(HTTPException) as foreign:
        call_upload(PROJECT, ATTACKER, valid_file)
    with pytest.raises(HTTPException) as missing:
        call_upload(MISSING, ATTACKER, valid_file)

    assert (missing.value.status_code, missing.value.detail) == (
        foreign.value.status_code,
        foreign.value.detail,
    )


# --- 3. the version-number oracle ------------------------------------------


def test_version_probe_is_scoped_to_the_caller(store, no_celery, valid_file):
    """The probe must not read rows belonging to other users.

    Setup: a project the attacker legitimately owns, which also contains a
    draft owned by someone else at version 7 -- the shape you get from a shared
    or legacy project. The attacker uploads a same-titled draft. It must start
    at version 1. An unscoped probe answers 8, and that 8 is the disclosure: it
    reports that another user's identically-titled draft exists and has been
    revised seven times.

    Note this is defence in depth. With the ``/upload`` project gate in place a
    caller cannot reach the probe with a project they do not own at all; this
    closes the case where they can reach it legitimately.
    """
    store.rows["projects"].append({"id": "project-b", "user_id": ATTACKER})
    store.rows["drafts"].append(
        {
            "id": "someone-elses-draft",
            "user_id": OWNER,
            "project_id": "project-b",
            "title": "Secret Manuscript",
            "version": 7,
        }
    )

    call_upload("project-b", ATTACKER, valid_file, title="Secret Manuscript")

    written = drafts_written(store)
    assert len(written) == 1
    assert written[0]["version"] == 1, "version probe leaked another user's draft history"

    # And structurally: every read of `drafts` was scoped by user_id.
    draft_reads = [q for q in store.queries if q.table == "drafts" and q.op == "select"]
    assert draft_reads, "expected the version probe to have run"
    for q in draft_reads:
        assert q.filters.get("user_id") == ATTACKER, f"unscoped read: {q.filters}"


def test_owner_version_probe_still_increments(store, no_celery, valid_file):
    """Not broken for the legitimate case: the owner re-uploading the same
    title still gets version 8."""
    call_upload(PROJECT, OWNER, valid_file, title="Secret Manuscript")

    assert drafts_written(store)[0]["version"] == 8


# --- the shared authorization decision -------------------------------------


class ClaimingActor(str):
    """An actor id that self-reports ownership. ``owns()`` raises, so any code
    path that consults the caller's account of its rights fails loudly."""

    owner = True
    is_owner = True
    user_id = OWNER

    def owns(self, *_a, **_kw):
        raise AssertionError("authorization consulted the caller's claim, not the lookup")


def test_self_reported_ownership_is_ignored_and_the_lookup_decides(store):
    claimant = ClaimingActor(ATTACKER)

    allowed, reason = drafts_routes.authorize_project_write(claimant, PROJECT)

    assert allowed is False
    assert "looked up" in reason
    assert OWNER not in reason
    # Provably from the lookup: the projects table was queried, for this id.
    project_reads = [q for q in store.queries if q.table == "projects"]
    assert [q.filters.get("id") for q in project_reads] == [PROJECT]


def test_unknown_project_denies(store):
    allowed, _reason = drafts_routes.authorize_project_write(OWNER, MISSING)
    assert allowed is False


def test_ownerless_project_denies(store):
    store.rows["projects"].append({"id": "orphan", "user_id": None})
    allowed, _reason = drafts_routes.authorize_project_write(OWNER, "orphan")
    assert allowed is False


def test_lookup_failure_denies(monkeypatch, store):
    def _boom(_name):
        raise Exception("supabase unreachable")

    monkeypatch.setattr(drafts_routes.supabase, "table", _boom)
    allowed, _reason = drafts_routes.authorize_project_write(OWNER, PROJECT)
    assert allowed is False


def test_missing_actor_denies(store):
    allowed, _reason = drafts_routes.authorize_project_write(None, PROJECT)
    assert allowed is False


def test_every_decision_is_logged(store, caplog):
    with caplog.at_level("INFO", logger=drafts_routes.logger.name):
        drafts_routes.authorize_project_write(OWNER, PROJECT)
        drafts_routes.authorize_project_write(ATTACKER, PROJECT)

    lines = [r.getMessage() for r in caplog.records if "project-write authz" in r.getMessage()]
    assert len(lines) == 2
    assert any("verdict=allow" in l for l in lines)
    assert any("verdict=deny" in l for l in lines)
    for line in lines:
        assert f"resource={PROJECT}" in line
        assert "action=draft.create" in line

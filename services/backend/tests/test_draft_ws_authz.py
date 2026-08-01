"""Authorization tests for the draft-analysis progress WebSocket.

The bug these exist for: the endpoint validated the caller's token and then
streamed whatever ``draft_id`` the caller named. Authentication is not
authorization; proving you are *someone* is not proving you are the owner of
*this* draft. The payload is analysis of unpublished research, so an
authenticated stranger reading it is a real disclosure.

Ported in spirit from ``harness/policy.py`` in the reviewer-agent repo:
ownership is looked up and never taken from the request, deny is the default,
denial reasons do not name the owner, and every decision is logged.
"""

import asyncio
import json
import sys
import types
from unittest.mock import MagicMock

import pytest

# drafts.py -> draft_export -> weasyprint, which needs native libs this test
# does not. Same stub the API-contract tests use.
if "weasyprint" not in sys.modules:
    _fake_weasyprint = types.ModuleType("weasyprint")
    _fake_weasyprint.HTML = MagicMock()
    sys.modules["weasyprint"] = _fake_weasyprint

from app.api.routes import drafts as drafts_routes


OWNER = "user-a-owner"
ATTACKER = "user-b-attacker"
DRAFT = "draft-belonging-to-a"


# --- doubles ---------------------------------------------------------------


class FakeWebSocket:
    """Records everything the endpoint does to a connection.

    ``sent`` is the load-bearing assertion surface: a denial that returns the
    right close code while still having emitted one progress frame is not a
    fixed vulnerability.
    """

    def __init__(self):
        self.accepted = False
        self.sent: list[str] = []
        self.close_code: int | None = None
        self.close_reason: str | None = None
        self.closed = False

    async def accept(self):
        self.accepted = True

    async def send_text(self, data: str):
        assert self.accepted, "sent before accept"
        assert not self.closed, "sent after close"
        self.sent.append(data)

    async def close(self, code: int = 1000, reason: str | None = None):
        self.closed = True
        self.close_code = code
        self.close_reason = reason


class _User:
    def __init__(self, user_id):
        self.id = user_id


class _AuthResponse:
    def __init__(self, user):
        self.user = user


class _Result:
    def __init__(self, data):
        self.data = data


class FakeTable:
    """Minimal Supabase query-builder stand-in over an in-memory ownership map."""

    def __init__(self, rows_by_id: dict[str, dict], calls: list):
        self._rows_by_id = rows_by_id
        self._calls = calls
        self._id = None

    def select(self, *_a, **_kw):
        return self

    def eq(self, column, value):
        if column == "id":
            self._id = value
        return self

    def limit(self, _n):
        return self

    def execute(self):
        self._calls.append(self._id)
        row = self._rows_by_id.get(self._id)
        return _Result([row] if row else [])


class FakeSupabase:
    def __init__(self, rows_by_id, token_to_user):
        self._rows_by_id = rows_by_id
        self._token_to_user = token_to_user
        self.lookup_calls: list = []
        self.auth = self

    # auth.get_user(token)
    def get_user(self, token):
        user_id = self._token_to_user.get(token)
        if user_id is None:
            raise Exception("invalid token")
        return _AuthResponse(_User(user_id))

    def table(self, _name):
        return FakeTable(self._rows_by_id, self.lookup_calls)


class FakePubSub:
    def __init__(self, events):
        self._events = events

    async def subscribe(self, _channel):
        return None

    async def unsubscribe(self, _channel):
        return None

    async def listen(self):
        for event in self._events:
            yield {"type": "message", "data": json.dumps(event)}


class FakeRedis:
    """Streams a canned progress sequence. If the endpoint reaches this at all
    for an unauthorized caller, the fix has failed."""

    def __init__(self, events, latest=None):
        self._events = events
        self._latest = latest

    async def get(self, _key):
        return self._latest

    def pubsub(self):
        return FakePubSub(self._events)

    async def close(self):
        return None


@pytest.fixture
def supa(monkeypatch):
    fake = FakeSupabase(
        rows_by_id={DRAFT: {"user_id": OWNER}},
        token_to_user={"tok-owner": OWNER, "tok-attacker": ATTACKER},
    )
    monkeypatch.setattr(drafts_routes, "supabase", fake)
    return fake


@pytest.fixture
def redis_streaming(monkeypatch):
    """Bind a Redis that would happily stream analysis if it were reached."""
    events = [
        {"progress": 40, "stage": "reviewer_feedback", "detail": "SECRET-ANALYSIS"},
        {"progress": 100, "stage": "done"},
    ]

    class _Factory:
        @staticmethod
        def from_url(_url):
            return FakeRedis(events, latest=json.dumps({"progress": 5, "detail": "SECRET-LATEST"}))

    monkeypatch.setattr(drafts_routes, "aioredis", _Factory)
    return events


def run_stream(ws, token, draft_id=DRAFT):
    asyncio.run(
        drafts_routes.draft_analysis_stream(draft_id=draft_id, websocket=ws, token=token)
    )


# --- the IDOR ---------------------------------------------------------------


def test_other_user_cannot_stream_someone_elses_draft(supa, redis_streaming):
    """User B, fully authenticated, connects to user A's draft."""
    ws = FakeWebSocket()
    run_stream(ws, "tok-attacker")

    # The point of the test: not merely "a code came back", but that no byte of
    # the analysis ever left the server.
    assert ws.sent == [], f"analysis payload leaked to non-owner: {ws.sent}"
    assert ws.closed
    assert ws.close_code == drafts_routes.WS_UNAUTHORIZED


def test_denial_does_not_name_the_owner(supa, redis_streaming):
    ws = FakeWebSocket()
    run_stream(ws, "tok-attacker")
    assert OWNER not in (ws.close_reason or "")


# --- the owner still works --------------------------------------------------


def test_owner_streams_their_own_draft(supa, redis_streaming):
    ws = FakeWebSocket()
    run_stream(ws, "tok-owner")

    assert ws.accepted
    assert ws.close_code != drafts_routes.WS_UNAUTHORIZED
    payloads = [json.loads(s) for s in ws.sent]
    assert any(p.get("detail") == "SECRET-LATEST" for p in payloads), payloads
    assert any(p.get("progress") == 100 for p in payloads), payloads


# --- unknown resource -------------------------------------------------------


def test_unknown_draft_denied_without_revealing_existence(supa, redis_streaming):
    missing = FakeWebSocket()
    run_stream(missing, "tok-attacker", draft_id="draft-that-does-not-exist")

    foreign = FakeWebSocket()
    run_stream(foreign, "tok-attacker", draft_id=DRAFT)

    assert missing.sent == []
    assert missing.close_code == drafts_routes.WS_UNAUTHORIZED
    # Indistinguishable from "exists but is not yours" -- otherwise the denial
    # is an oracle for which draft ids are real.
    assert (missing.close_code, missing.close_reason) == (
        foreign.close_code,
        foreign.close_reason,
    )


# --- unauthenticated is a different thing -----------------------------------


def test_unauthenticated_is_4001_and_distinguishable(supa, redis_streaming):
    ws = FakeWebSocket()
    run_stream(ws, "tok-garbage")

    assert ws.sent == []
    assert ws.close_code == drafts_routes.WS_UNAUTHENTICATED
    assert drafts_routes.WS_UNAUTHENTICATED != drafts_routes.WS_UNAUTHORIZED
    # Unauthenticated is refused before the handshake; unauthorized after it.
    assert ws.accepted is False


# --- the claim test (ported from harness/policy.py) -------------------------


class ClaimingActor(str):
    """An actor id that also insists it owns things.

    ``owns()`` raises: if the endpoint ever consults the caller's own account
    of its rights instead of the ownership table, this test fails loudly rather
    than passing quietly. Subclasses ``str`` so it flows through the code path
    exactly as a real user id would.
    """

    owner = True
    is_owner = True
    user_id = OWNER  # the claim: "I am the owner of that draft"

    def owns(self, *_a, **_kw):
        raise AssertionError("authorization consulted the caller's claim, not the lookup")


def test_self_reported_ownership_is_ignored_and_the_lookup_decides(supa):
    """A caller that self-reports ownership is still denied, and the denial
    provably came from the lookup table."""
    claimant = ClaimingActor(ATTACKER)

    allowed, reason = drafts_routes.authorize_draft_stream(claimant, DRAFT)

    assert allowed is False
    # Provably from the lookup: the ownership table was queried, for this draft.
    assert supa.lookup_calls == [DRAFT]
    assert "looked up" in reason
    assert OWNER not in reason


def test_lookup_failure_denies(monkeypatch, supa):
    """Deny by default: a lookup that cannot answer has not established ownership."""

    def _boom(_name):
        raise Exception("supabase unreachable")

    monkeypatch.setattr(supa, "table", _boom)
    allowed, _reason = drafts_routes.authorize_draft_stream(OWNER, DRAFT)
    assert allowed is False


def test_ownerless_draft_denies(monkeypatch, supa):
    supa._rows_by_id["orphan"] = {"user_id": None}
    allowed, _reason = drafts_routes.authorize_draft_stream(OWNER, "orphan")
    assert allowed is False


def test_missing_actor_denies(supa):
    allowed, _reason = drafts_routes.authorize_draft_stream(None, DRAFT)
    assert allowed is False


def test_every_decision_is_logged(supa, caplog):
    with caplog.at_level("INFO", logger=drafts_routes.logger.name):
        drafts_routes.authorize_draft_stream(OWNER, DRAFT)
        drafts_routes.authorize_draft_stream(ATTACKER, DRAFT)

    lines = [r.getMessage() for r in caplog.records if "draft-stream authz" in r.getMessage()]
    assert len(lines) == 2
    assert any("verdict=allow" in l for l in lines)
    assert any("verdict=deny" in l for l in lines)
    for line in lines:
        assert f"resource={DRAFT}" in line
        assert "action=analysis.stream" in line

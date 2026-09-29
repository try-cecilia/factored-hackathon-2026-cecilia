"""A restart, a refresh or a second process must not lose a session or a conversation in flight.

Two Orchestrators over one STATE_DB_PATH stand for the process before and after a restart.
"""
from __future__ import annotations

import json
import sqlite3

import pytest

from agent.core.orchestrator import ConversationStore, Orchestrator
from agent.session.auth import ExpiredSession, InvalidSession, SessionStore
from eval.fake_llm import FakeLLMClient, tool_call_response

ATTRS = {"segment": "Student", "country": "México", "customer_status": "Active"}


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("TRACE_REQUESTS_PATH", str(tmp_path / "traces.jsonl"))
    monkeypatch.setenv("HUMAN_QUEUE_PATH", str(tmp_path / "queue.jsonl"))
    return str(tmp_path / "state.sqlite")


def process(db_path, *responses):
    fake = FakeLLMClient(list(responses))
    return Orchestrator(SessionStore(ttl_seconds=900, db_path=db_path), llm=lambda: fake,
                        conversations=ConversationStore(db_path=db_path))


def test_a_session_survives_a_restart_and_only_its_hash_is_on_disk(db):
    token = SessionStore(db_path=db).issue("CLI-FIX0004", ATTRS).token
    after = SessionStore(db_path=db)
    assert after.validate(token).customer_id == "CLI-FIX0004"
    assert token not in "".join(map(str, sqlite3.connect(db).execute("SELECT * FROM sessions").fetchall()))


def test_revoked_and_expired_sessions_stay_dead_after_a_restart(db):
    store = SessionStore(db_path=db)
    revoked, expired = store.issue("CLI-FIX0004").token, store.issue("CLI-FIX0004").token
    store.revoke(revoked)
    store.expire(expired)
    after = SessionStore(db_path=db)
    with pytest.raises(InvalidSession):
        after.validate(revoked)
    with pytest.raises(ExpiredSession):
        after.validate(expired)


def test_a_trace_proposed_before_a_restart_is_confirmed_after_it(db):
    before = process(db, tool_call_response("request_trace", {}))
    token = before.session_store.issue("CLI-FIX0004", ATTRS).token
    assert before.handle_message(token, "hice una transferencia que todavía no llega").policy_rule == "action:trace_proposed"

    after = process(db)  # a new process: empty memory, the same file, and no model call is needed for a plain yes
    r = after.handle_message(token, "sí")
    assert r.policy_rule == "action:trace_opened"


def test_a_conversation_belongs_to_its_session_and_stale_ones_are_purged(db):
    store = ConversationStore(db_path=db)
    conv = store.get("ref-a")
    conv.requests.append("hola")
    store.save("ref-a")
    assert ConversationStore(db_path=db).get("ref-a").requests == ["hola"]
    assert ConversationStore(db_path=db).get("ref-b").requests == []
    with sqlite3.connect(db) as c:
        c.execute("UPDATE conversations SET updated_at = 0")
    assert ConversationStore(db_path=db).get("ref-a").requests == []  # older than the retention window

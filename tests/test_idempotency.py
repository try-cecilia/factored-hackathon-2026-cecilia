"""POST /chat with an Idempotency-Key: a retry after a lost answer gets the stored reply and does not run the turn
again, so it cannot file a second ticket or confirm a second action. Fixture: CLI-FIX0001 reports a cloned card
(a handoff), CLI-FIX0004 has one pending transfer."""
from __future__ import annotations

import threading
import time

import pytest
from fastapi.testclient import TestClient

from agent.session.auth import default_store
from api import idempotency, main
from tests.test_api import login

CLONED = "Me clonaron la tarjeta"
ADMIN = {"X-Admin-Key": "test-admin-key"}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main, "login_limiter", main.RateLimiter(50, 60))
    monkeypatch.setattr(main, "chat_limiter", main.RateLimiter(50, 60))
    monkeypatch.setattr(idempotency, "default", idempotency.IdempotencyStore())
    return TestClient(main.app)


def token(client, cid="CLI-FIX0001") -> str:
    return login(client, cid=cid).json()["token"]


def chat(client, tok, message, key=None):
    headers = {"Idempotency-Key": key} if key else {}
    return client.post("/chat", json={"session_token": tok, "message": message}, headers=headers)


def tickets(client) -> int:
    return len(client.get("/admin/human_queue?limit=200", headers=ADMIN).json())


def test_a_retry_with_the_same_key_gets_the_same_reply_and_files_no_second_ticket(client):
    tok = token(client)
    before = tickets(client)
    first = chat(client, tok, CLONED, key="msg-0001-aaaa")
    assert first.status_code == 200 and first.json()["ticket_id"]
    retry = chat(client, tok, CLONED, key="msg-0001-aaaa")
    assert retry.status_code == 200 and retry.json() == first.json()
    assert retry.headers["Idempotent-Replayed"] == "true" and "Idempotent-Replayed" not in first.headers
    assert tickets(client) == before + 1


def test_without_a_key_or_with_another_one_the_turn_runs_again(client):
    tok = token(client)
    before = tickets(client)
    assert chat(client, tok, CLONED).status_code == 200
    assert chat(client, tok, CLONED).status_code == 200
    assert chat(client, tok, CLONED, key="msg-0002-aaaa").status_code == 200
    assert chat(client, tok, CLONED, key="msg-0003-aaaa").status_code == 200
    assert tickets(client) == before + 4


def test_the_same_key_with_another_text_is_refused_and_runs_nothing(client):
    tok = token(client)
    before = tickets(client)
    assert chat(client, tok, "¿Cuál es mi saldo?", key="msg-0004-aaaa").status_code == 200
    refused = chat(client, tok, CLONED, key="msg-0004-aaaa")
    assert refused.status_code == 422
    assert tickets(client) == before


def test_a_key_only_replays_inside_its_own_session(client):
    before = tickets(client)
    a, b = token(client), token(client)
    ra = chat(client, a, CLONED, key="msg-0005-aaaa")
    rb = chat(client, b, CLONED, key="msg-0005-aaaa")
    assert ra.json()["ticket_id"] != rb.json()["ticket_id"]
    assert tickets(client) == before + 2


def test_a_replay_does_not_count_against_the_chat_limit(client, monkeypatch):
    monkeypatch.setattr(main, "chat_limiter", main.RateLimiter(1, 60))
    tok = token(client)
    assert chat(client, tok, "¿Cuál es mi saldo?", key="msg-0006-aaaa").status_code == 200
    assert chat(client, tok, "¿Cuál es mi saldo?", key="msg-0006-aaaa").status_code == 200  # replay
    assert chat(client, tok, "¿Cuál es mi saldo?", key="msg-0007-aaaa").status_code == 429  # a new turn


def test_a_confirmation_retried_with_its_key_opens_one_trace(client, monkeypatch, tmp_path):
    monkeypatch.setenv("TRACE_REQUESTS_PATH", str(tmp_path / "trace_requests.jsonl"))
    tok = token(client, "CLI-FIX0004")
    # The proposal needs the model to pick the tool; the yes that follows is decided in code, never by the model.
    from agent.core.orchestrator import default_orchestrator
    from eval.fake_llm import FakeLLMClient, tool_call_response

    fake = FakeLLMClient([tool_call_response("request_trace", {})])
    monkeypatch.setattr(default_orchestrator, "_llm", lambda: fake)
    assert chat(client, tok, "hice una transferencia que todavía no llega").json()["category"] == "confirm_action"
    yes = chat(client, tok, "sí", key="msg-0008-aaaa")
    retry = chat(client, tok, "sí", key="msg-0008-aaaa")
    assert yes.json()["category"] == "resolved"
    assert retry.json() == yes.json()
    lines = (tmp_path / "trace_requests.jsonl").read_text().splitlines()
    assert len(lines) == 1


@pytest.mark.parametrize("key", ["short", "x" * 65, "bad key with spaces!"])
def test_a_malformed_key_is_a_422(client, key):
    assert chat(client, token(client), "hola", key=key).status_code == 422


def test_an_expired_session_reply_is_not_kept(client):
    first = chat(client, "not-a-real-token", "hola", key="msg-0009-aaaa")
    assert first.json()["disposition"] == "REAUTH_REQUIRED"
    assert idempotency.default.count() == 0


def test_an_entry_lives_as_long_as_the_session_it_belongs_to(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(idempotency.time, "time", lambda: now[0])
    store = idempotency.IdempotencyStore()
    with store.guard("ref", "key-00000001", "hola", expires_at=1900.0) as slot:
        assert slot.replay is None
        slot.save('{"a": 1}')
    now[0] += 601  # longer than the old fixed 10 minutes, shorter than the session
    with store.guard("ref", "key-00000001", "hola", expires_at=1900.0) as slot:
        assert slot.replay == '{"a": 1}'
    now[0] = 1901  # the session is over: nothing is kept for it
    with store.guard("ref", "key-00000001", "hola", expires_at=2800.0) as slot:
        assert slot.replay is None and not slot.processed
    assert store.count() == 0


def test_a_retry_well_after_ten_minutes_still_gets_the_same_reply_and_no_second_ticket(client, monkeypatch):
    tok = token(client)
    before = tickets(client)
    first = chat(client, tok, CLONED, key="msg-0013-aaaa")
    real = idempotency.time.time
    monkeypatch.setattr(idempotency.time, "time", lambda: real() + 601)  # the session lasts 900 s
    retry = chat(client, tok, CLONED, key="msg-0013-aaaa")
    assert retry.json() == first.json() and retry.headers["Idempotent-Replayed"] == "true"
    assert tickets(client) == before + 1


def test_when_space_runs_out_the_oldest_replies_are_dropped_but_their_keys_are_remembered(monkeypatch):
    store = idempotency.IdempotencyStore(max_entries=4)
    for n in range(6):
        with store.guard("ref", f"key-0000000{n}", "hola", expires_at=9e9) as slot:
            slot.save(f'{{"n": {n}}}')
    with store.guard("ref", "key-00000000", "hola", expires_at=9e9) as slot:
        assert slot.replay is None and slot.processed  # already ran; its reply is no longer kept
    with store.guard("ref", "key-00000005", "hola", expires_at=9e9) as slot:
        assert slot.replay == '{"n": 5}'
    with pytest.raises(idempotency.KeyReused):
        with store.guard("ref", "key-00000000", "otro texto", expires_at=9e9):
            pass


def test_a_key_that_ran_but_lost_its_reply_is_a_409_and_runs_nothing(client, monkeypatch):
    monkeypatch.setattr(idempotency, "default", idempotency.IdempotencyStore(max_entries=4))
    tok = token(client)
    before = tickets(client)
    for n in range(6):
        assert chat(client, tok, CLONED, key=f"msg-1000-aaa{n}").status_code == 200
    refused = chat(client, tok, CLONED, key="msg-1000-aaa0")
    assert refused.status_code == 409 and "already processed" in refused.json()["detail"]
    assert tickets(client) == before + 6

def test_a_retry_that_arrives_while_the_first_still_runs_waits_for_its_answer():
    store = idempotency.IdempotencyStore()
    started, release, seen = threading.Event(), threading.Event(), []

    def first():
        with store.guard("ref", "key-00000002", "hola", expires_at=9e9) as slot:
            started.set()
            release.wait(5)
            slot.save('{"n": 1}')

    def retry():
        started.wait(5)
        with store.guard("ref", "key-00000002", "hola", expires_at=9e9) as slot:
            seen.append(slot.replay)

    t1, t2 = threading.Thread(target=first), threading.Thread(target=retry)
    t1.start(); t2.start()
    started.wait(5)
    assert seen == []  # the retry is waiting, not running a second turn
    release.set()
    t1.join(5); t2.join(5)
    assert seen == ['{"n": 1}']


def test_a_stored_reply_survives_a_restart_when_state_is_on_disk(tmp_path):
    db = str(tmp_path / "state.db")
    with idempotency.IdempotencyStore(db_path=db).guard("ref", "key-00000003", "hola", expires_at=9e9) as slot:
        slot.save('{"kept": true}')
    with idempotency.IdempotencyStore(db_path=db).guard("ref", "key-00000003", "hola", expires_at=9e9) as slot:
        assert slot.replay == '{"kept": true}'


def test_a_replay_is_not_delivered_once_the_session_is_over(client):
    """Logging out, or letting the session run out, ends what the stored reply may be shown to."""
    tok = token(client)
    before = tickets(client)
    first = chat(client, tok, CLONED, key="msg-0010-aaaa")
    assert first.json()["disposition"] == "ESCALATE"
    assert client.delete("/auth/session", headers={"X-Session-Token": tok}).status_code == 204
    again = chat(client, tok, CLONED, key="msg-0010-aaaa")
    assert again.json()["disposition"] == "REAUTH_REQUIRED" and again.json()["ticket_id"] is None
    assert "Idempotent-Replayed" not in again.headers
    assert tickets(client) == before + 1

    other = token(client)
    chat(client, other, "¿Cuál es mi saldo?", key="msg-0011-aaaa")
    default_store.expire(other)
    assert chat(client, other, "¿Cuál es mi saldo?", key="msg-0011-aaaa").json()["disposition"] == "REAUTH_REQUIRED"


def test_a_retry_that_waited_for_the_first_turn_is_checked_again_when_its_turn_comes(client, monkeypatch):
    tok = token(client)
    started, release, out = threading.Event(), threading.Event(), {}
    real = main._run_turn

    def slow(req):
        reply = real(req)  # the turn has run; the reply is not yet saved or delivered
        started.set()
        release.wait(5)
        return reply

    monkeypatch.setattr(main, "_run_turn", slow)

    def retry():
        started.wait(5)
        out["retry"] = chat(TestClient(main.app), tok, "¿Cuál es mi saldo?", key="msg-0012-aaaa")

    first = threading.Thread(target=lambda: out.setdefault("first", chat(TestClient(main.app), tok, "¿Cuál es mi saldo?", key="msg-0012-aaaa")))
    second = threading.Thread(target=retry)
    first.start(); second.start()
    started.wait(5)
    time.sleep(0.2)  # the retry is now waiting on the key's lock
    default_store.revoke(tok)  # the session ends while it waits
    release.set()
    first.join(5); second.join(5)
    assert out["first"].json()["disposition"] == "AUTO_RESOLVE"
    assert out["retry"].json()["disposition"] == "REAUTH_REQUIRED"


def test_a_reply_stored_in_demo_mode_does_not_leak_demo_fields_when_replayed_outside_it(client, monkeypatch):
    tok = token(client)
    monkeypatch.setenv("DEMO_MODE", "1")
    first = chat(client, tok, CLONED, key="msg-0014-aaaa").json()
    assert first["why"] and first["policy_rule"]  # the sandbox shows them

    monkeypatch.setenv("DEMO_MODE", "0")
    replay = chat(client, tok, CLONED, key="msg-0014-aaaa")
    assert replay.headers["Idempotent-Replayed"] == "true"
    body = replay.json()
    assert body["why"] is None and body["policy_rule"] == ""
    assert {k: v for k, v in body.items() if k not in ("why", "policy_rule")} == {
        k: v for k, v in first.items() if k not in ("why", "policy_rule")}

    monkeypatch.setenv("DEMO_MODE", "1")  # and back in the sandbox the stored explanation is shown again
    assert chat(client, tok, CLONED, key="msg-0014-aaaa").json()["why"] == first["why"]


def test_a_full_table_refuses_new_turns_and_never_forgets_a_live_session_key(client, monkeypatch):
    """Capacity is the table's, not the sessions': when it is full a new turn is refused before it runs, and no key
    of a live session is dropped to make room."""
    monkeypatch.setattr(idempotency, "default", idempotency.IdempotencyStore(max_entries=2, max_marks=3))
    tok = token(client)
    before = tickets(client)
    for n in range(3):
        assert chat(client, tok, CLONED, key=f"msg-2000-aaa{n}").status_code == 200
    assert tickets(client) == before + 3

    refused = chat(client, tok, CLONED, key="msg-2000-aaa9")
    assert refused.status_code == 503 and int(refused.headers["Retry-After"]) >= 1
    assert tickets(client) == before + 3  # refused before it ran: no ticket, nothing changed

    for n in range(3):  # the old keys are all still known: none is run again
        again = chat(client, tok, CLONED, key=f"msg-2000-aaa{n}")
        assert again.status_code in (200, 409)
    assert tickets(client) == before + 3


def test_a_turn_that_fails_gives_its_reservation_back(client, monkeypatch):
    monkeypatch.setattr(main, "chat_limiter", main.RateLimiter(1, 60))
    tok = token(client)
    assert chat(client, tok, "¿Cuál es mi saldo?", key="msg-2001-aaaa").status_code == 200
    limited = chat(client, tok, "¿Cuál es mi saldo?", key="msg-2001-bbbb")
    assert limited.status_code == 429
    assert idempotency.default.count() == 1  # only the turn that ran holds a place
    monkeypatch.setattr(main, "chat_limiter", main.RateLimiter(20, 60))
    assert chat(client, tok, "¿Cuál es mi saldo?", key="msg-2001-bbbb").status_code == 200  # not "already processed"


def test_a_reservation_is_taken_together_with_the_capacity_check():
    store = idempotency.IdempotencyStore(max_marks=1)
    with store.guard("ref", "key-00000001", "hola", expires_at=9e9) as first:
        with pytest.raises(idempotency.CapacityFull):  # the first turn is still running: its place is already held
            with store.guard("ref", "key-00000002", "hola", expires_at=9e9):
                pass
        first.save('{"n": 1}')


def test_the_first_version_of_the_table_is_dropped_not_migrated(tmp_path):
    """It only ever existed on this unmerged branch, with keys stored as they came and no expiry tied to the session."""
    import sqlite3

    db = str(tmp_path / "state.db")
    old = sqlite3.connect(db)
    old.execute("CREATE TABLE idempotency (session_ref TEXT NOT NULL, key TEXT NOT NULL, message_hash TEXT NOT NULL, "
                "response TEXT NOT NULL, created_at REAL NOT NULL, PRIMARY KEY (session_ref, key))")
    old.execute("INSERT INTO idempotency VALUES ('ref', 'plain-key-0001', 'h', '{}', 1.0)")
    old.commit()
    old.close()

    idempotency.IdempotencyStore(db_path=db)
    names = {r[0] for r in sqlite3.connect(db).execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert "idempotency" not in names and "idempotency_keys" in names


def test_a_turn_that_fails_after_it_started_is_never_run_again_by_a_retry(client, monkeypatch):
    """The ticket is filed, then the turn fails: the customer gets a 500, but the effect happened. The retry must be
    told so (409), not file a second ticket."""
    tok = token(client)
    before = tickets(client)
    run_turn = main._run_turn

    def files_then_fails(req):
        run_turn(req)
        raise OSError("disk full")

    crashing = TestClient(main.app, raise_server_exceptions=False)
    with monkeypatch.context() as m:
        m.setattr(main, "_run_turn", files_then_fails)
        assert chat(crashing, tok, CLONED, key="msg-3000-aaaa").status_code == 500
    assert tickets(client) == before + 1  # the ticket was filed before the failure

    retry = chat(client, tok, CLONED, key="msg-3000-aaaa")
    assert retry.status_code == 409 and "already processed" in retry.json()["detail"]
    assert tickets(client) == before + 1
    assert idempotency.default.count() == 1  # the mark stays until the session ends; the error is not kept as a reply


def test_a_trace_log_that_cannot_be_written_still_answers_and_a_retry_replays(client, monkeypatch):
    """A failed trace write no longer loses the confirmed reply, so it is stored and a retry gets it back."""
    from agent.tools.audit import default_trace_log

    tok = token(client)
    before = tickets(client)
    with monkeypatch.context() as m:
        m.setattr(default_trace_log, "write", lambda trace: (_ for _ in ()).throw(OSError("disk full")))
        first = chat(client, tok, CLONED, key="msg-3002-aaaa")
    assert first.status_code == 200 and tickets(client) == before + 1

    retry = chat(client, tok, CLONED, key="msg-3002-aaaa")
    assert retry.status_code == 200 and retry.headers.get("Idempotent-Replayed") == "true"
    assert retry.json()["trace_id"] == first.json()["trace_id"] and tickets(client) == before + 1


def test_a_failure_while_saving_the_reply_keeps_the_mark_too(client, monkeypatch):
    tok = token(client)
    before = tickets(client)
    def broken(self):
        raise OSError("state file is read-only")

    crashing = TestClient(main.app, raise_server_exceptions=False)
    with monkeypatch.context() as m:
        m.setattr(idempotency.IdempotencyStore, "_make_room", broken)
        assert chat(crashing, tok, CLONED, key="msg-3001-aaaa").status_code == 500
    assert chat(client, tok, CLONED, key="msg-3001-aaaa").status_code == 409
    assert tickets(client) == before + 1


def test_a_refusal_before_the_turn_starts_gives_the_place_back(client, monkeypatch):
    """A 429 ran nothing: the same key may be sent again once the limit allows it."""
    monkeypatch.setattr(main, "chat_limiter", main.RateLimiter(0, 60))
    tok = token(client)
    assert chat(client, tok, "¿Cuál es mi saldo?", key="msg-3002-aaaa").status_code == 429
    assert idempotency.default.count() == 0
    monkeypatch.setattr(main, "chat_limiter", main.RateLimiter(20, 60))
    assert chat(client, tok, "¿Cuál es mi saldo?", key="msg-3002-aaaa").status_code == 200

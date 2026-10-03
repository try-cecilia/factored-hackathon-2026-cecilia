"""GET /chat/history: the live session's conversation, as the customer saw it, so a reload does not empty the chat.

It returns what the API rendered (the customer's words with card numbers masked, the replies, the case number) and nothing
of the turn's inner workings; it belongs to the session whose token asks and to no other. Fixture: CLI-FIX0001 reports a
cloned card (a handoff); with no model key a plain balance question is answered in limited mode.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agent.core.orchestrator import MAX_TRANSCRIPT, ConversationStore, Orchestrator, _Conversation
from agent.session.auth import SessionStore
from api import idempotency, main
from tests.test_api import login

CLONED = "Me clonaron la tarjeta"
BALANCE = "¿Cuál es mi saldo?"
INTERNALS = {"policy_rule", "why", "verified_facts", "model_input", "tool_calls", "provider", "model", "usage", "cost_usd"}


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


def history(client, tok):
    return client.get("/chat/history", headers={"X-Session-Token": tok})


def test_a_new_session_has_an_empty_history(client):
    response = history(client, token(client))
    assert response.status_code == 200 and response.json() == {"turns": [], "cases": []}


def test_history_returns_the_turns_as_rendered_oldest_first(client):
    tok = token(client)
    first = chat(client, tok, CLONED).json()
    second = chat(client, tok, BALANCE).json()
    turns = history(client, tok).json()["turns"]
    assert [t["role"] for t in turns] == ["user", "assistant", "user", "assistant"]
    assert [t["text"] for t in turns if t["role"] == "user"] == [CLONED, BALANCE]
    assert turns[1]["text"] == first["response_text"] and turns[3]["text"] == second["response_text"]
    assert (turns[1]["disposition"], turns[1]["ticket_id"], turns[1]["trace_id"]) == ("ESCALATE", first["ticket_id"], first["trace_id"])
    assert turns[1]["language"] == first["language"] and turns[1]["category"] == first["category"]
    assert turns[0]["at"] <= turns[1]["at"] <= turns[2]["at"] <= turns[3]["at"]


def test_history_carries_no_internals_even_in_the_demo(client, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "1")
    tok = token(client)
    assert "why" in chat(client, tok, CLONED).json()  # the live reply does explain itself in the sandbox...
    for turn in history(client, tok).json()["turns"]:  # ...the history never does
        assert not INTERNALS & set(turn), turn


def test_the_customers_words_come_back_with_card_numbers_masked(client):
    tok = token(client)
    chat(client, tok, "Me clonaron la tarjeta 4111 1111 1111 1111")
    user = history(client, tok).json()["turns"][0]
    assert "4111 1111 1111 1111" not in user["text"] and "4111111111111111" not in user["text"]
    assert "1111" in user["text"]  # the last four stay, as in the ticket's copy


def test_another_session_cannot_read_it_not_even_the_same_customers(client):
    mine = token(client)
    chat(client, mine, CLONED)
    same_customer = token(client)
    other_customer = token(client, "CLI-FIX0004")
    assert history(client, same_customer).json()["turns"] == []
    assert history(client, other_customer).json()["turns"] == []
    assert len(history(client, mine).json()["turns"]) == 2  # and it was not disturbed


@pytest.mark.parametrize("headers", [{}, {"X-Session-Token": "not-a-real-token"}, {"X-Session-Token": "0" * 24}])
def test_without_a_live_session_there_is_nothing_to_read(client, headers):
    assert client.get("/chat/history", headers=headers).status_code == 401


def test_an_expired_or_revoked_session_reads_nothing(client):
    from agent.session.auth import default_store

    expired = token(client)
    chat(client, expired, CLONED)
    default_store.expire(expired)
    assert history(client, expired).status_code == 401
    revoked = token(client)
    chat(client, revoked, CLONED)
    assert client.delete("/auth/session", headers={"X-Session-Token": revoked}).status_code == 204
    assert history(client, revoked).status_code == 401


def test_logging_out_forgets_what_was_shown(client):
    """The figures in the replies are not kept for the rest of the retention window once the customer leaves."""
    tok = token(client)
    chat(client, tok, BALANCE)
    conversations = main.default_orchestrator.conversations
    from agent.session.auth import session_ref

    ref = session_ref(tok)
    assert conversations.get(ref).transcript
    client.delete("/auth/session", headers={"X-Session-Token": tok})
    assert conversations.get(ref).transcript == []


def test_a_replayed_turn_is_not_recorded_twice(client):
    tok = token(client)
    first = chat(client, tok, CLONED, key="msg-0001-aaaa")
    replay = chat(client, tok, CLONED, key="msg-0001-aaaa")
    assert replay.headers["Idempotent-Replayed"] == "true" and replay.json() == first.json()
    assert len(history(client, tok).json()["turns"]) == 2


def test_a_session_that_ended_before_the_turn_records_nothing(client):
    """REAUTH_REQUIRED is not a conversation turn."""
    assert chat(client, "0" * 24, CLONED).json()["disposition"] == "REAUTH_REQUIRED"
    assert main.default_orchestrator.conversations.get("0" * 24).transcript == []


def test_limited_mode_is_flagged_in_the_reply_and_in_the_history(client):
    tok = token(client)
    limited = chat(client, tok, BALANCE).json()
    handoff = chat(client, tok, CLONED).json()
    assert limited["degraded"] is True and handoff["degraded"] is False
    assert [t["degraded"] for t in history(client, tok).json()["turns"] if t["role"] == "assistant"] == [True, False]


def test_the_history_is_bounded(client):
    tok = token(client)
    for _ in range(MAX_TRANSCRIPT // 2 + 3):
        chat(client, tok, BALANCE)
    assert len(history(client, tok).json()["turns"]) == MAX_TRANSCRIPT


def test_the_history_survives_a_restart_and_an_older_conversation_still_loads(tmp_path):
    db = str(tmp_path / "state.db")
    store = ConversationStore(db_path=db)
    conv = store.get("ref-1")
    store.record_turn(conv, "hola", type("R", (), {"response_text": "Hola", "trace_id": "t1", "disposition": "AUTO_RESOLVE",
                                                   "category": "none", "language": "es", "ticket_id": None, "degraded": False, "choice": None,
                                                   "trace_receipt": None})())
    store.save("ref-1")
    assert [t["text"] for t in ConversationStore(db_path=db).get("ref-1").transcript] == ["hola", "Hola"]
    assert _Conversation(**{"messages": [], "requests": [], "language": "es"}).transcript == []  # saved before this field existed


def test_the_orchestrator_reads_only_its_own_sessions_conversation():
    orch = Orchestrator(SessionStore(ttl_seconds=900))
    attrs = {"segment": "Student", "country": "México", "customer_status": "Active"}
    a, b = orch.session_store.issue("CLI-FIX0001", attrs).token, orch.session_store.issue("CLI-FIX0001", attrs).token
    orch.handle_message(a, CLONED)
    assert len(orch.history(a)) == 2 and orch.history(b) == []


# --- retention: what the API keeps in memory follows what it keeps on disk -------------------------------------------------

def _rows(db) -> int:
    import sqlite3

    with sqlite3.connect(db) as c:
        return c.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]


def test_a_conversation_purged_from_the_database_is_not_served_from_memory(tmp_path, monkeypatch):
    """The retention job deletes rows from another process; the API's copy in memory must not outlive it."""
    import sqlite3

    monkeypatch.setattr(ConversationStore, "VERIFY_SECONDS", 0)  # look at the file on every read
    db = str(tmp_path / "state.db")
    store = ConversationStore(db_path=db)
    conv = store.get("ref-a")
    store.record_turn(conv, "hola", type("R", (), {"response_text": "Hola", "trace_id": "t", "disposition": "AUTO_RESOLVE",
                                                   "category": "none", "language": "es", "ticket_id": None, "degraded": False, "choice": None,
                                                   "trace_receipt": None})())
    store.save("ref-a")
    with sqlite3.connect(db) as c:
        c.execute("DELETE FROM conversations")  # what ops/retention.py does to a stale row
    assert store.get("ref-a").transcript == []


def test_a_conversation_in_memory_expires_with_the_retention_window(tmp_path, monkeypatch):
    import time

    db = str(tmp_path / "state.db")
    store = ConversationStore(db_path=db)
    conv = store.get("ref-a")
    conv.requests.append("hola")
    store.save("ref-a")
    later = time.time() + ConversationStore.RETENTION_SECONDS + 60
    monkeypatch.setattr("agent.core.orchestrator.time.time", lambda: later)
    assert store.get("ref-a").requests == []  # neither the memory copy nor the (not yet purged) row is served past the window


def test_a_turn_of_a_session_that_is_over_saves_nothing(tmp_path):
    """REAUTH_REQUIRED must not write the conversation back: it would revive a purged row and refresh its age."""
    db = str(tmp_path / "state.db")
    orch = Orchestrator(SessionStore(ttl_seconds=900, db_path=db), conversations=ConversationStore(db_path=db))
    attrs = {"segment": "Student", "country": "México", "customer_status": "Active"}
    tok = orch.session_store.issue("CLI-FIX0001", attrs).token
    orch.handle_message(tok, CLONED)
    assert _rows(db) == 1
    import sqlite3

    with sqlite3.connect(db) as c:
        c.execute("DELETE FROM conversations")  # purged by retention
    orch.session_store.expire(tok)
    assert orch.handle_message(tok, BALANCE).disposition == "REAUTH_REQUIRED"
    assert _rows(db) == 0
    orch.session_store.revoke(tok)
    assert orch.handle_message(tok, BALANCE).disposition == "REAUTH_REQUIRED"
    assert _rows(db) == 0


def test_the_cases_of_a_session_outlive_the_bounded_history(client):
    """After more turns than the history keeps, a case opened in the first one is still in the sidebar's list."""
    tok = token(client)
    ticket = chat(client, tok, CLONED).json()["ticket_id"]
    for _ in range(MAX_TRANSCRIPT // 2 + 5):
        chat(client, tok, BALANCE)
    body = history(client, tok).json()
    assert len(body["turns"]) == MAX_TRANSCRIPT and all(t.get("ticket_id") != ticket for t in body["turns"])  # the turn itself is gone
    assert [c["ticket_id"] for c in body["cases"]] == [ticket]
    assert body["cases"][0]["category"] == "theft" and body["cases"][0]["at"] > 0


def test_the_case_index_is_the_sessions_own_and_never_carries_anything_else(client):
    mine = token(client)
    chat(client, mine, CLONED)
    assert history(client, token(client)).json()["cases"] == []
    assert set(history(client, mine).json()["cases"][0]) == {"ticket_id", "category", "at"}
    client.delete("/auth/session", headers={"X-Session-Token": mine})
    assert history(client, mine).status_code == 401


def test_a_conversation_saved_before_the_index_existed_still_loads():
    assert _Conversation(**{"messages": [], "requests": [], "language": "es", "transcript": []}).case_index == []


def test_a_conversation_saved_before_language_set_keeps_the_language_it_had_learned(tmp_path):
    """The flag is new: a row without it must not forget a language the session already had, or the case panel would read the
    ticket's language while the chat (which reads `language`) keeps the session's. A row with no turns and the default language
    has nothing to preserve and stays unset."""
    import json
    import sqlite3

    db = str(tmp_path / "state.db")
    store = ConversationStore(db_path=db)
    spoke_pt, spoke_es, silent = store.get("pt"), store.get("es"), store.get("silent")
    spoke_pt.language = "pt"                            # a language other than the default can only have come from the customer
    spoke_es.requests.append("hola")                    # turns, in the default language: it was heard, not assumed
    for key in ("pt", "es", "silent"):
        store.save(key)
    with sqlite3.connect(db) as conn:
        for key, data in conn.execute("SELECT key, data FROM conversations").fetchall():
            saved = json.loads(data)
            del saved["language_set"]
            conn.execute("UPDATE conversations SET data = ? WHERE key = ?", (json.dumps(saved), key))
    reloaded = ConversationStore(db_path=db)
    assert (reloaded.get("pt").language_set, reloaded.get("es").language_set, reloaded.get("silent").language_set) == (True, True, False)


def test_a_clarification_says_what_its_options_are_in_the_reply_and_in_the_history(client, monkeypatch):
    """The screen sends a name for a product and a number for a movement: the API says which, instead of the screen reading it
    off the words of the reply."""
    from agent.core.orchestrator import default_orchestrator
    from eval.fake_llm import FakeLLMClient, tool_call_response

    fake = FakeLLMClient([tool_call_response("list_transactions", {"product_id": "Cuenta Ahorro"}), tool_call_response("get_account_summary", {})])
    monkeypatch.setattr(default_orchestrator, "_llm", lambda: fake)
    tok = token(client)
    asked = chat(client, tok, "movimientos de mi cuenta de ahorros").json()
    assert asked["disposition"] == "CLARIFY" and asked["choice"] == "product"
    assert chat(client, tok, "mis saldos").json()["choice"] is None
    turns = [t for t in history(client, tok).json()["turns"] if t["role"] == "assistant"]
    assert turns[0]["choice"] == "product" and "choice" not in turns[1]

"""The customer's context beside a case: products, latest movements and the customer's other cases and traces, read-only.

It answers only to the admin key (what the queue already reads with), leaves the desk and the queue untouched, sends account numbers
as their last four digits, and, when the warehouse does not answer, says so and still gives what the files hold.
"""
from __future__ import annotations

import json
import logging

import pytest
from fastapi.testclient import TestClient

from agent import observability
from agent.policy import router
from agent.policy.desk import default_desk
from agent.policy.escalation import escalate
from agent.tools import account_tools
from agent.tools.traces import default_traces
from api import customer_context, main

ADMIN = {"X-Admin-Key": "ctx-admin-key-0123456789-abcdefgh"}
OPERATOR = {"X-Operator-Key": "ctx-ana-key-0123456789-abcdefgh"}
CUSTOMER = "CLI-FIX0004"  # has products of several kinds and the fixture's one pending transfer (TXN-FIX0006)


@pytest.fixture(autouse=True)
def stores(tmp_path, monkeypatch):
    for var, name in (("HUMAN_QUEUE_PATH", "queue"), ("HUMAN_DESK_PATH", "desk"), ("TRACE_REQUESTS_PATH", "traces"), ("AUDIT_LOG_PATH", "audit")):
        monkeypatch.setenv(var, str(tmp_path / f"{name}.jsonl"))
    monkeypatch.setenv("ADMIN_API_KEY", ADMIN["X-Admin-Key"])
    monkeypatch.setenv("OPERATOR_KEYS", f"ana={OPERATOR['X-Operator-Key']}")
    monkeypatch.setattr(main, "operator_fail_limiter", main.RateLimiter(100, 60))


def file_ticket(customer: str = CUSTOMER, request: str = "no llegó") -> str:
    return escalate(router.trace_review("older_than_review_threshold"), customer, "ref", request, "es", [], [], [], {}, None).ticket_id


def context(ticket_id: str, headers=ADMIN):
    return TestClient(main.app).get(f"/admin/tickets/{ticket_id}/customer_context", headers=headers)


def test_it_lists_the_customers_products_masked_and_the_movements_with_the_pending_one_marked():
    body = context(file_ticket()).json()
    assert body["warehouse"]["available"] is True and body["warehouse"]["as_of"]
    assert body["warehouse"]["source"] == "account_warehouse"
    assert body["warehouse"]["freshness"] == "current"
    from datetime import datetime
    assert datetime.fromisoformat(body["warehouse"]["queried_at"])
    assert body["products"], "the customer has products"
    assert {p["currency"] for p in body["products"]} >= {"USD"}
    assert {tuple(sorted(p)) for p in body["products"]} == {("currency", "last4", "product_id", "status", "type")}
    assert all(len(p["last4"]) == 4 for p in body["products"])
    pending = [m for m in body["movements"] if m["pending"]]
    assert [m["transaction_id"] for m in pending] == ["TXN-FIX0006"]
    assert {m["status"] for m in pending} == {"Pending"}
    assert all(set(m) == {"transaction_id", "date", "product_id", "type", "amount", "currency", "merchant", "status", "pending"} for m in body["movements"])
    assert [m["date"] for m in body["movements"]] == sorted((m["date"] for m in body["movements"]), reverse=True)


def test_no_full_account_or_card_number_leaves_the_api():
    body = context(file_ticket()).text
    for number in ("4000000001", "4000000002", "5000000004", "4000000003"):
        assert number not in body
    assert "product_number" not in body


def test_it_holds_nothing_of_other_customers():
    body = context(file_ticket()).json()
    owned = {p["product_id"] for p in body["products"]}
    assert owned and all(m["product_id"] in owned for m in body["movements"])
    assert "CLI-FIX0001" not in json.dumps(body)


def test_the_other_cases_of_the_same_customer_are_listed_with_their_state_and_this_one_is_not():
    mine, older, other_customer = file_ticket(), file_ticket(request="otra vez"), file_ticket("CLI-FIX0001")
    default_desk.act(older, "claim", "ana")
    cases = context(mine).json()["cases"]
    assert [c["ticket_id"] for c in cases] == [older]
    assert cases[0]["status"] == "claimed" and set(cases[0]) == {"ticket_id", "category", "queue", "priority", "created_at", "status"}
    assert other_customer not in json.dumps(cases)


def test_the_customers_traces_are_listed_and_only_theirs():
    default_traces.open(CUSTOMER, "TXN-FIX0006", "PRD-FIX0010", "ref")
    default_traces.open("CLI-FIX0001", "TXN-FIX0001", "PRD-FIX0001", "ref")
    traces = context(file_ticket()).json()["traces"]
    assert [(t["transaction_id"], t["status"]) for t in traces] == [("TXN-FIX0006", "open")]
    assert set(traces[0]) == {"trace_id", "transaction_id", "status", "created_at"}


def test_only_the_admin_key_reads_it_and_a_ticket_that_does_not_exist_is_a_404():
    ticket_id = file_ticket()
    client = TestClient(main.app)
    path = f"/admin/tickets/{ticket_id}/customer_context"
    assert client.get(path).status_code == 401
    assert client.get(path, headers=OPERATOR).status_code == 401  # the operator key acts, it does not read
    assert client.get(path, headers={"X-Session-Token": "0" * 24}).status_code == 401
    assert client.get("/admin/tickets/T-0000-nope/customer_context", headers=ADMIN).status_code == 404
    assert client.get(path, headers=ADMIN).status_code == 200


def test_reading_it_changes_nothing():
    ticket_id = file_ticket()
    before = (default_desk.state(ticket_id), main.default_queue.path.read_text(encoding="utf-8"))
    context(ticket_id)
    assert (default_desk.state(ticket_id), main.default_queue.path.read_text(encoding="utf-8")) == before


def test_when_the_warehouse_does_not_answer_it_says_so_and_still_gives_the_cases_and_traces(monkeypatch, caplog):
    mine, older = file_ticket(), file_ticket(request="otra vez")
    default_traces.open(CUSTOMER, "TXN-FIX0006", "PRD-FIX0010", "ref")

    def down(*args, **kwargs):
        raise OSError("connection to /secret/path/bank.duckdb lost, customer CLI-FIX0004")

    monkeypatch.setattr(account_tools, "_rows", down)
    before = observability.failure_counts().get("customer_context_unavailable", 0)
    with caplog.at_level(logging.WARNING):
        response = context(mine)
    body = response.json()
    assert response.status_code == 200
    assert body["warehouse"]["available"] is False
    assert body["warehouse"]["source"] == "account_warehouse"
    assert body["warehouse"]["freshness"] == "unavailable"
    assert body["warehouse"]["as_of"] == "2024-01-16"
    from datetime import datetime
    assert datetime.fromisoformat(body["warehouse"]["queried_at"])
    assert body["products"] == [] and body["movements"] == []
    assert [c["ticket_id"] for c in body["cases"]] == [older] and len(body["traces"]) == 1
    assert observability.failure_counts()["customer_context_unavailable"] == before + 1
    # The exception's message names a path and a customer: it stays out of the response and out of the log.
    assert "secret" not in response.text and "secret" not in caplog.text and "OSError" in caplog.text


def test_a_failure_inside_the_warehouse_leaves_no_message_in_the_audit_log_or_its_endpoint(monkeypatch):
    """The tools write `str(error)` to the audit log, and /admin/audit_log serves it: the context must not read through them."""
    ticket_id = file_ticket()

    def down(*args, **kwargs):
        raise OSError("CANARY-PRIVATE /secret/customer-sensitive/bank.duckdb")

    monkeypatch.setattr(account_tools, "_rows", down)
    assert context(ticket_id).json()["warehouse"]["available"] is False
    client = TestClient(main.app)
    served = client.get("/admin/audit_log?limit=500", headers=ADMIN).text
    on_disk = main.default_audit_log.path.read_text(encoding="utf-8") if main.default_audit_log.path.exists() else ""
    assert "CANARY" not in served and "CANARY" not in on_disk and "secret" not in served + on_disk


def test_every_read_leaves_a_record_of_the_read_with_the_ticket_and_the_outcome_only(monkeypatch):
    ticket_id = file_ticket()
    context(ticket_id)
    events = [e for e in main.default_audit_log.recent() if e.get("event") == "customer_context_read"]
    assert events and events[-1]["ticket_id"] == ticket_id and events[-1]["warehouse"] == "ok"
    assert CUSTOMER not in json.dumps(events[-1])  # the ticket names the customer; the record does not

    def down(*args, **kwargs):
        raise OSError("CANARY")

    monkeypatch.setattr(account_tools, "_rows", down)
    context(ticket_id)
    last = [e for e in main.default_audit_log.recent() if e.get("event") == "customer_context_read"][-1]
    assert last["warehouse"] == "unavailable" and last["error_type"] == "OSError" and "CANARY" not in json.dumps(last)


def test_a_warehouse_that_knows_no_such_customer_is_the_same_unavailable_answer(monkeypatch):
    ticket_id = file_ticket("CLI-NOBODY")
    body = context(ticket_id).json()
    assert body["warehouse"]["available"] is False and body["products"] == []


@pytest.fixture
def busy_customer(tmp_path, monkeypatch):
    """A copy of the fixture warehouse where CLI-FIX0004 has ten recent approved movements and, older than all of them, eleven more
    pending ones (twelve with the fixture's own): more pending than any page would hold."""
    import shutil

    import duckdb

    from agent.tools import db

    copy = tmp_path / "busy.duckdb"
    shutil.copy(db.duckdb_path(), copy)
    con = duckdb.connect(str(copy))
    rows = [(f"TXN-NEW-A{n:02d}", f"2024-06-{n + 1:02d} 10:00:00", "Purchase", "Approved") for n in range(10)]
    rows += [(f"TXN-NEW-P{n:02d}", f"2023-0{n % 9 + 1}-15 10:00:00", "Transfer", "Pending") for n in range(11)]
    for txn, when, kind, status in rows:
        con.execute("INSERT INTO transactions (transaction_id, transaction_date, process_date, product_id, customer_id, transaction_type, amount, currency, transaction_status) "
                    "VALUES (?, CAST(? AS TIMESTAMP), CAST(? AS DATE), 'PRD-FIX0010', ?, ?, 25, 'USD', ?)", [txn, when, when[:10], CUSTOMER, kind, status])
    con.close()
    db.close_all()
    monkeypatch.setenv("DUCKDB_PATH", str(copy))
    yield
    db.close_all()


def test_every_pending_movement_is_listed_however_many_and_however_old(busy_customer):
    body = context(file_ticket()).json()
    pending = [m for m in body["movements"] if m["pending"]]
    assert len(pending) == 12 and {m["transaction_id"] for m in pending} >= {f"TXN-NEW-P{n:02d}" for n in range(11)} | {"TXN-FIX0006"}
    assert len(body["movements"]) == 22 and body["pending_omitted"] == 0
    assert [m["date"] for m in body["movements"]] == sorted((m["date"] for m in body["movements"]), reverse=True)


def test_past_the_explicit_cap_the_response_says_how_many_pending_were_left_out(busy_customer, monkeypatch):
    monkeypatch.setattr(customer_context, "PENDING_SHOWN", 5)
    body = context(file_ticket()).json()
    assert len([m for m in body["movements"] if m["pending"]]) == 5 and body["pending_omitted"] == 7


def test_without_pending_movements_nothing_is_left_out():
    assert context(file_ticket("CLI-FIX0001")).json()["pending_omitted"] == 0


def test_with_freshness_enforced_a_warehouse_older_than_its_limit_is_unavailable_not_current(monkeypatch, caplog):
    """The tools refuse stale data when FRESHNESS_ENFORCE=1; reading around them must keep that: the fixture's data is from 2024."""
    ticket_id = file_ticket()
    monkeypatch.setenv("FRESHNESS_ENFORCE", "1")
    monkeypatch.setenv("FRESHNESS_SLO_HOURS", "36")
    with caplog.at_level(logging.WARNING):
        body = context(ticket_id).json()
    assert body["warehouse"]["available"] is False
    assert body["warehouse"]["as_of"] == "2024-01-16"
    assert body["warehouse"]["freshness"] == "stale"
    assert body["warehouse"]["source"] == "account_warehouse"
    from datetime import datetime
    assert datetime.fromisoformat(body["warehouse"]["queried_at"])
    assert body["products"] == [] and body["movements"] == []
    last = [e for e in main.default_audit_log.recent() if e.get("event") == "customer_context_read"][-1]
    assert last["warehouse"] == "unavailable" and last["error_type"] == "DataUnavailable"
    assert "exceeds freshness" not in json.dumps(last) + caplog.text  # the type only, not the message
    monkeypatch.delenv("FRESHNESS_ENFORCE")
    assert context(ticket_id).json()["warehouse"]["available"] is False

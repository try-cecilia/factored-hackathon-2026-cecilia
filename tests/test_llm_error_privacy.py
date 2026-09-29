"""What a provider error may leave behind: the exception's type, the HTTP status and a code from a fixed list, never a
message or a body. Providers echo prompts in errors (a 400 quotes the input that it rejected), and the prompt holds
what the customer typed, so nothing they wrote can be allowed into a trace record or a log line."""
from __future__ import annotations

import json
import logging
import os
from types import SimpleNamespace

import pytest

from agent.core.orchestrator import Orchestrator
from agent.llm.client import LLMClient, LLMUnavailable, Provider, safe_error
from agent.session.auth import SessionStore
from tests.test_local_llm import FakeOllama

SECRET = "CLI-FIX0001 cuenta 5000000001 saldo 12,345.67 Ana Pérez"


@pytest.fixture(autouse=True)
def stores(tmp_path, monkeypatch):
    for var in ("TRACE_REQUESTS_PATH", "HUMAN_QUEUE_PATH", "AUDIT_LOG_PATH", "TRACE_LOG_PATH"):
        monkeypatch.setenv(var, str(tmp_path / f"{var}.jsonl"))
    monkeypatch.setenv("P1_KEY", "k")


def failing(error, calls=None):
    def create(**kwargs):
        raise error

    sdk = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return Provider("p1", "m", "P1_KEY", lambda key, timeout: sdk)


def leaks(text: str) -> bool:
    return any(part in text for part in ("CLI-FIX0001", "5000000001", "12,345.67", "Ana", "Pérez"))


class SdkError(Exception):
    def __init__(self, message, status_code=None, body=None):
        super().__init__(message)
        self.status_code, self.body = status_code, body


def test_an_exception_message_with_a_sensitive_id_never_reaches_the_attempt_log_or_the_logs(caplog):
    client = LLMClient([failing(SdkError(f"could not parse: {SECRET}", status_code=503))], sleep=lambda s: None)
    with caplog.at_level(logging.DEBUG), pytest.raises(LLMUnavailable) as e:
        client.chat([{"role": "user", "content": "hola"}])
    assert not leaks(json.dumps(e.value.attempts)) and not leaks(caplog.text) and not leaks(str(e.value))
    assert e.value.attempts[0]["error"] == "SdkError status=503"


@pytest.mark.parametrize("status", [400, 401, 422, 429, 500, 503])
def test_a_provider_body_with_data_is_never_kept_whatever_the_status(status, tmp_path, monkeypatch, caplog):
    server = FakeOllama([(status, {"error": {"message": f"invalid input: {SECRET}", "type": "invalid_request_error",
                                             "code": "context_length_exceeded", "param": SECRET}}, 0)])
    monkeypatch.setenv("LLM_PROVIDERS", "local")
    monkeypatch.setenv("LOCAL_LLM_BASE_URL", server.url)
    try:
        with caplog.at_level(logging.DEBUG), pytest.raises(LLMUnavailable) as e:
            LLMClient(sleep=lambda s: None, max_attempts_per_provider=2).chat([{"role": "user", "content": "hola"}])
    finally:
        server.close()
    errors = [a["error"] for a in e.value.attempts if a["outcome"] == "error"]
    assert errors and all(err.startswith("HTTPStatusError status=") and f"status={status}" in err for err in errors)
    assert not leaks(json.dumps(e.value.attempts)) and not leaks(caplog.text)


def test_only_a_code_from_the_fixed_list_is_kept_and_a_free_text_code_is_not():
    known = SdkError("x", status_code=429, body={"error": {"code": "rate_limit_exceeded", "message": SECRET}})
    unknown = SdkError("x", status_code=400, body={"error": {"code": SECRET, "message": SECRET}})
    assert safe_error(known) == "SdkError status=429 code=rate_limit_exceeded"
    assert safe_error(unknown) == "SdkError status=400" and not leaks(safe_error(unknown))
    assert safe_error(ValueError(SECRET)) == "ValueError"


def test_a_turn_whose_model_failed_leaves_no_customer_data_in_its_trace_record(caplog):
    client = LLMClient([failing(SdkError(f"echo: {SECRET}", status_code=500, body={"error": {"message": SECRET}}))], sleep=lambda s: None)
    orch = Orchestrator(SessionStore(ttl_seconds=900), llm=lambda: client)
    tok = orch.session_store.issue("CLI-FIX0001", {"segment": "Premium", "country": "México", "customer_status": "Active"}).token
    with caplog.at_level(logging.DEBUG):
        r = orch.handle_message(tok, "movimientos de mi tarjeta")
    assert r.category == "llm_unavailable"
    record = open(os.environ["TRACE_LOG_PATH"], encoding="utf-8").read()
    ticket = open(os.environ["HUMAN_QUEUE_PATH"], encoding="utf-8").read()
    assert not leaks(record) and not leaks(caplog.text) and "status=500" in record
    assert not leaks(ticket.replace('"customer_id": "CLI-FIX0001"', ""))  # the ticket names its own customer, nothing else of it

"""Prometheus metrics: what the service reports about itself at GET /metrics (docs/operations.md, "Monitoring").

Two kinds, both with bounded label sets (never a customer, a session, a ticket or a free-text value):
- events, counted where they happen: every turn's trace record (agent/tools/audit.py calls `observe_turn` when it writes
  one), every tool call, every HTTP request, every rate-limit hit and login outcome;
- state, read at scrape time by `RuntimeCollector`: sessions, the model budget, each provider's circuit breaker, the
  age of the data against its SLO, the pipeline's last quality results and when retention last ran.
A scrape never fails because one source does: that source is skipped and counted in
`cecilai_scrape_errors_total{source}`, so a broken gauge is itself visible.

The alert rules in ops/alerts.yml are written against these names; tests/test_metrics.py fails if a rule uses a metric
this module does not expose.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from prometheus_client import CollectorRegistry, Counter, Histogram
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily
from prometheus_client.exposition import generate_latest

logger = logging.getLogger(__name__)

# Buckets in seconds. 8 is the p95 alert threshold's own edge: histogram_quantile is exact only at a bucket boundary.
TURN_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1, 2, 3, 5, 8, 12, 20, 30)
STAGE_BUCKETS = (0.001, 0.005, 0.025, 0.1, 0.25, 0.5, 1, 2, 4, 8, 12, 25)
HTTP_BUCKETS = (0.005, 0.025, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30)
MAX_PENDING_TRACES = 4096  # trace ids waiting for their turn's record, so their tool time can be added up
CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"


def _model_seconds(record: dict) -> float:
    """Time the turn spent on the model when the record has no stage spans: what each successful step says, and for a step that
    ended in failure (no provider answered, so no latency) the sum of its attempts' durations plus any backoff they record."""
    total = 0.0
    for step in record.get("llm_steps") or []:
        if step.get("latency_ms") is not None:
            total += float(step["latency_ms"]) / 1000
        else:
            total += sum((float(a.get("ms") or 0) + float(a.get("wait_ms") or 0)) for a in step.get("attempts") or []) / 1000
    return total


class Metrics:
    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        r = self.registry
        self.turns = Counter("cecilai_turns_total", "Conversation turns by outcome.", ["disposition", "category"], registry=r)
        self.escalations = Counter("cecilai_escalations_total", "Turns handed to a person, by category.", ["category"], registry=r)
        self.handoff_unverified = Counter(
            "cecilai_handoff_unverified_total", "Escalations whose ticket did not read back: the customer was told to call.",
            registry=r)
        self.foreign_product_refs = Counter(
            "cecilai_foreign_product_references_total", "Turns naming a product owned by another customer.", registry=r)
        self.degraded_turns = Counter("cecilai_degraded_turns_total", "Turns answered in degraded mode (model down or over budget).", registry=r)
        self.llm_unavailable_turns = Counter(
            "cecilai_llm_unavailable_turns_total", "Turns escalated because no model provider answered.", registry=r)
        self.model_refusals = Counter("cecilai_model_refusals_total", "Model answers that were a refusal.", ["provider"], registry=r)
        self.llm_attempts = Counter(
            "cecilai_llm_attempts_total", "Model provider attempts: outcome ok, error (reason = transient/permanent) or skipped "
            "(reason = why: circuit_open, budget, key missing...).", ["provider", "outcome", "reason"], registry=r)
        self.llm_tokens = Counter("cecilai_llm_tokens_total", "Model tokens by kind (prompt, completion, cache_read, cache_write).",
                                  ["provider", "model", "kind"], registry=r)
        self.llm_cost = Counter("cecilai_llm_cost_usd_total", "Model spend in USD at the assumed list prices (agent/llm/pricing.py).",
                                ["provider", "model"], registry=r)
        self.llm_unpriced = Counter("cecilai_llm_unpriced_calls_total", "Model calls whose price is unknown.", ["provider", "model"], registry=r)
        self.tool_calls = Counter("cecilai_tool_calls_total", "Tool calls a turn made, by outcome.", ["tool", "outcome", "error_type"], registry=r)
        self.turn_latency = Histogram("cecilai_turn_latency_seconds", "Whole turn, from message to reply.", buckets=TURN_BUCKETS, registry=r)
        self.stage_latency = Histogram(
            "cecilai_stage_latency_seconds", "Time per turn in each stage: llm (model calls), tools (tool calls), "
            "policy_render (guards, routing, rendering: the rest).", ["stage"], buckets=STAGE_BUCKETS, registry=r)
        self.tool_latency = Histogram("cecilai_tool_call_seconds", "One tool call.", ["tool"], buckets=STAGE_BUCKETS, registry=r)
        self.http_requests = Counter("cecilai_http_requests_total", "HTTP requests by route template and status.",
                                     ["method", "route", "status"], registry=r)
        self.http_latency = Histogram("cecilai_http_request_seconds", "HTTP request duration by route template.", ["route"],
                                      buckets=HTTP_BUCKETS, registry=r)
        self.rate_limited = Counter("cecilai_rate_limit_hits_total", "Requests refused by a limiter.", ["limiter"], registry=r)
        self.logins = Counter("cecilai_logins_total", "Session requests by result (ok, invalid, locked_out, rate_limited, unavailable).",
                              ["result"], registry=r)
        self.scrape_errors = Counter("cecilai_scrape_errors_total", "A state source that could not be read at scrape time.", ["source"], registry=r)
        self._tool_seconds: OrderedDict[str, float] = OrderedDict()
        self._lock = threading.Lock()
        r.register(RuntimeCollector(self))

    # --- events ---------------------------------------------------------------------------------------------------

    def observe_tool_call(self, tool: str, seconds: float | None, trace_id: str | None) -> None:
        if seconds is None:
            return
        self.tool_latency.labels(tool).observe(seconds)
        if trace_id:
            with self._lock:
                self._tool_seconds[trace_id] = self._tool_seconds.get(trace_id, 0.0) + seconds
                while len(self._tool_seconds) > MAX_PENDING_TRACES:
                    self._tool_seconds.popitem(last=False)

    def observe_turn(self, record: dict) -> None:
        """One turn's trace record (the fields orchestrator.handle_message writes)."""
        disposition, category = str(record.get("disposition") or "unknown"), str(record.get("category") or "none")
        rule = str(record.get("policy_rule") or "")
        self.turns.labels(disposition, category).inc()
        if disposition == "ESCALATE":
            self.escalations.labels(category).inc()
        if rule.endswith("|handoff_unverified"):
            self.handoff_unverified.inc()
        if rule == "reference_to_foreign_product":
            self.foreign_product_refs.inc()
        if rule.startswith("degraded:"):
            self.degraded_turns.inc()
        if rule.startswith("llm_unavailable"):
            self.llm_unavailable_turns.inc()

        total = float(record.get("latency_ms") or 0) / 1000
        llm_s, stage_tools_s = _model_seconds(record), None
        spans = record.get("stages")
        if spans:  # the turn's own timings, when the orchestrator records them: one span per step, with its duration
            llm_s = sum(float(sp.get("ms") or 0) for sp in spans if sp.get("stage") == "llm") / 1000
            tool_spans = [sp for sp in spans if str(sp.get("stage")).startswith("tool:") or sp.get("stage") == "trace_service"]
            if tool_spans:  # a path without tool spans (the degraded balance read) still has its audited tool time
                stage_tools_s = sum(float(sp.get("ms") or 0) for sp in tool_spans) / 1000
        for step in record.get("llm_steps") or []:
            for attempt in step.get("attempts") or []:
                outcome = str(attempt.get("outcome") or "unknown")
                reason = str(attempt.get("kind") or attempt.get("reason") or "")
                provider = str(attempt.get("provider") or "unknown")
                self.llm_attempts.labels(provider, outcome, reason).inc()
                if str(attempt.get("error") or "").startswith("ModelRefusal"):
                    self.model_refusals.labels(provider).inc()
        with self._lock:
            audited_tools_s = self._tool_seconds.pop(str(record.get("trace_id")), 0.0)
        tools_s = audited_tools_s if stage_tools_s is None else stage_tools_s
        self.turn_latency.observe(total)
        self.stage_latency.labels("llm").observe(llm_s)
        self.stage_latency.labels("tools").observe(tools_s)
        self.stage_latency.labels("policy_render").observe(max(0.0, total - llm_s - tools_s))

        for call in record.get("tool_calls") or []:
            ok = call.get("success") is not False
            self.tool_calls.labels(str(call.get("tool") or "unknown"), "ok" if ok else "error",
                                   "" if ok else str(call.get("error_type") or "unknown")).inc()

        if record.get("llm_calls"):
            provider, model = str(record.get("provider") or "unknown"), str(record.get("model") or "unknown")
            usage = record.get("usage") or {}
            for kind, key in (("prompt", "prompt_tokens"), ("completion", "completion_tokens"),
                              ("cache_read", "cache_read_tokens"), ("cache_write", "cache_write_tokens")):
                if usage.get(key):
                    self.llm_tokens.labels(provider, model, kind).inc(usage[key])
            cost = record.get("cost_usd")
            if cost is None:
                self.llm_unpriced.labels(provider, model).inc()
            elif cost:
                self.llm_cost.labels(provider, model).inc(cost)

    def observe_http(self, method: str, route: str, status: int, seconds: float) -> None:
        self.http_requests.labels(method, route, str(status)).inc()
        self.http_latency.labels(route).observe(seconds)

    # --- exposition -----------------------------------------------------------------------------------------------

    def render(self) -> bytes:
        return generate_latest(self.registry)


class RuntimeCollector:
    """State read when Prometheus scrapes: it changes without any event to hook."""

    def __init__(self, owner: Metrics) -> None:
        self._owner = owner

    def describe(self) -> Iterable:  # a collector without describe() is called once at registration: not wanted here
        return []

    def collect(self):
        for source in (self._service, self._llm, self._data, self._pipeline, self._retention, self._capacity):
            try:
                yield from source()
            except Exception:  # noqa: BLE001 - a scrape must not fail because one source did
                logger.exception("metrics source %s failed", source.__name__)
                self._owner.scrape_errors.labels(source.__name__.lstrip("_")).inc()

    @staticmethod
    def _gauge(name: str, doc: str, value: float, labels: dict[str, str] | None = None) -> GaugeMetricFamily:
        g = GaugeMetricFamily(name, doc, labels=list(labels or {}))
        g.add_metric(list((labels or {}).values()), value)
        return g

    def _service(self):
        from agent.llm import prompts
        from agent.policy import intent_guard
        from agent.session.auth import default_store

        info = GaugeMetricFamily("cecilai_build_info", "Which build is running (value is always 1).", labels=["prompt_version", "git_sha"])
        info.add_metric([str(prompts.PROMPT_VERSION), os.environ.get("GIT_SHA", "unknown")], 1)
        yield info
        yield self._gauge("cecilai_active_sessions", "Sessions in the store (live or not yet pruned).", len(default_store))
        yield self._gauge("cecilai_intent_classifier_loaded", "1 if the pre-model intent classifier loaded.",
                          1 if intent_guard.read("hola").model_available else 0)

    def _capacity(self):
        from agent import observability
        from agent.resilience import bounded_ops_stats

        failures = CounterMetricFamily("cecilai_record_failures", "Records that could not be written after their effects happened, "
                                       "and handoff writes that finished after their budget, by kind.", labels=["kind"])
        for kind, n in sorted(observability.failure_counts().items()):
            failures.add_metric([kind], n)
        yield failures
        inflight = GaugeMetricFamily("cecilai_bounded_ops_inflight", "Background work still running after its caller gave up, by pool.", labels=["pool"])
        limit = GaugeMetricFamily("cecilai_bounded_ops_limit", "The most a pool may run at once.", labels=["pool"])
        rejected = CounterMetricFamily("cecilai_bounded_ops_rejected", "Work refused because its pool was full.", labels=["pool"])
        for pool, st in bounded_ops_stats().items():
            inflight.add_metric([pool], st["inflight"])
            limit.add_metric([pool], st["limit"])
            rejected.add_metric([pool], st["rejected"])
        yield from (inflight, limit, rejected)

    def _llm(self):
        from agent.llm.budget import default_budget
        from agent.llm.client import get_default_client

        budget = default_budget
        yield self._gauge("cecilai_llm_budget_spent_usd", "Model spend so far in the UTC day.", budget.spent_today())
        yield self._gauge("cecilai_llm_budget_limit_usd", "LLM_DAILY_BUDGET_USD (0 = no cap).", budget.limit_usd or 0)
        yield self._gauge("cecilai_llm_budget_exhausted", "1 once the daily budget is spent: the assistant runs degraded.",
                          1 if budget.exhausted() else 0)
        now = time.time()
        client = get_default_client()
        open_g = GaugeMetricFamily("cecilai_llm_circuit_open", "1 while a provider's circuit breaker is open (skipped).", labels=["provider"])
        fail_g = GaugeMetricFamily("cecilai_llm_consecutive_failures", "Failures since the provider's last success.", labels=["provider"])
        keyed = GaugeMetricFamily("cecilai_llm_provider_configured", "1 if the provider's API key is set.", labels=["provider"])
        for p in client.providers:
            open_g.add_metric([p.name], 1 if client._down_until.get(p.name, 0) > now else 0)
            fail_g.add_metric([p.name], client._failures.get(p.name, 0))
            keyed.add_metric([p.name], 1 if os.environ.get(p.api_key_env) else 0)
        yield from (open_g, fail_g, keyed)

    def _data(self):
        from agent.tools import account_tools

        as_of = account_tools.data_as_of()
        enforced = 1 if account_tools.freshness_enforced() else 0
        yield self._gauge("cecilai_data_freshness_slo_hours", "FRESHNESS_SLO_HOURS.", account_tools.freshness_slo_hours())
        yield self._gauge("cecilai_data_freshness_enforced", "1 if a stale warehouse makes the tools refuse (FRESHNESS_ENFORCE).", enforced)
        if as_of is None:
            return
        stamp = datetime(as_of.year, as_of.month, as_of.day, tzinfo=timezone.utc).timestamp()
        yield self._gauge("cecilai_data_as_of_timestamp_seconds", "The warehouse's as-of date (00:00 UTC).", stamp)
        yield self._gauge("cecilai_data_age_hours", "Hours since the as-of date, the number the freshness SLO is checked against.",
                          (time.time() - stamp) / 3600)

    def _pipeline(self):
        from agent.tools.db import get_connection

        con = get_connection()
        present = {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables").fetchall()}
        if not {"_ingestion_log", "_dq_results"} <= present:
            return
        failed_runs = con.execute(
            "SELECT count(*) FROM (SELECT status FROM _ingestion_log QUALIFY row_number() OVER "
            "(PARTITION BY table_name ORDER BY started_at DESC) = 1) WHERE status <> 'success'").fetchone()[0]
        failed_checks = con.execute(
            "SELECT count(*) FROM _dq_results d JOIN (SELECT run_id, table_name FROM _ingestion_log WHERE status = 'success' "
            "QUALIFY row_number() OVER (PARTITION BY table_name ORDER BY finished_at DESC) = 1) l USING (run_id, table_name) "
            "WHERE d.severity = 'error' AND d.passed = false").fetchone()[0]
        yield self._gauge("cecilai_ingestion_failed_tables", "Tables whose latest ingestion attempt failed.", failed_runs)
        yield self._gauge("cecilai_dq_failed_error_checks", "Error-level quality checks that failed in the latest successful loads.", failed_checks)

    def _retention(self):
        from ops import retention

        enabled = 1 if float(os.environ.get("RETENTION_INTERVAL_HOURS") or 24) > 0 else 0
        yield self._gauge("cecilai_retention_enabled", "1 if a purge is scheduled (RETENTION_INTERVAL_HOURS > 0).", enabled)
        interval = float(os.environ.get("RETENTION_INTERVAL_HOURS") or 24)
        yield self._gauge("cecilai_retention_interval_hours", "Hours between scheduled purges.", interval)
        path = Path(retention.status_path())
        last, failed, dropped = 0.0, 0, {}
        if path.exists():
            status = json.loads(path.read_text(encoding="utf-8"))
            last, failed = float(status.get("last_run") or 0), len(status.get("failed") or [])
            dropped = {o["name"]: o["dropped"] for o in status.get("outcomes", [])}
        yield self._gauge("cecilai_retention_last_run_timestamp_seconds", "When the last purge finished (0 = never).", last)
        yield self._gauge("cecilai_retention_failed_stores", "Stores the last purge could not prune.", failed)
        g = GaugeMetricFamily("cecilai_retention_last_dropped_records", "Records the last purge deleted, by data type.", labels=["store"])
        for name, n in dropped.items():
            g.add_metric([name], n)
        yield g


default = Metrics()

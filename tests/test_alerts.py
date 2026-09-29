"""The alert rules (ops/alerts.yml) are well formed, use only metrics the service exposes, and match the runbook table."""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from agent.metrics import Metrics

ROOT = Path(__file__).resolve().parent.parent
RULES = yaml.safe_load((ROOT / "ops" / "alerts.yml").read_text(encoding="utf-8"))
ALERTS = [rule for group in RULES["groups"] for rule in group["rules"]]
DOC = (ROOT / "docs" / "operations.md").read_text(encoding="utf-8")
SEVERITIES = {"critical", "warning", "info"}
SUFFIX = re.compile(r"_(total|bucket|sum|count|created)$")


def base(name: str) -> str:
    return SUFFIX.sub("", name)


def exposed_metrics() -> set[str]:
    """Every metric family a scrape of the service exposes (families, so a counter with no sample yet still counts)."""
    text = Metrics().render().decode()
    return {base(m.group(1)) for m in re.finditer(r"^# TYPE (\S+) ", text, re.M)}


def headings() -> set[str]:
    """The anchors GitHub gives the headings of docs/operations.md."""
    return {re.sub(r"[^a-z0-9 \-]", "", h.lower()).strip().replace(" ", "-") for h in re.findall(r"^#+ (.+)$", DOC, re.M)}


def test_the_rules_are_well_formed():
    assert len(ALERTS) >= 20
    names = [a["alert"] for a in ALERTS]
    assert len(names) == len(set(names)) and all(re.fullmatch(r"Cecilai[A-Za-z0-9]+", n) for n in names)
    for a in ALERTS:
        assert a["expr"].strip(), a["alert"]
        assert a["labels"]["severity"] in SEVERITIES and a["labels"]["signal"], a["alert"]
        assert {"summary", "description", "runbook"} <= set(a["annotations"]), a["alert"]


def test_every_runbook_link_points_at_a_section_that_exists():
    for a in ALERTS:
        path, _, anchor = a["annotations"]["runbook"].partition("#")
        assert path == "docs/operations.md" and anchor in headings(), f'{a["alert"]}: {a["annotations"]["runbook"]}'


def test_every_metric_a_rule_names_is_exposed_by_the_service():
    # /metrics is scraped with the fixture warehouse behind it, so the state gauges are present
    from fastapi.testclient import TestClient
    from api import main

    scraped = TestClient(main.app).get("/metrics", headers={"X-Admin-Key": "test-admin-key"}).text
    exposed = exposed_metrics() | {base(m.group(1)) for m in re.finditer(r"^# TYPE (\S+) ", scraped, re.M)}
    for a in ALERTS:
        used = {base(m) for m in re.findall(r"\bcecilai_[a-z0-9_]+", a["expr"])}
        assert used or a["expr"].startswith("up{"), a["alert"]  # the availability rule reads Prometheus' own `up`
        assert used <= exposed, f'{a["alert"]} uses {sorted(used - exposed)}, which the service does not expose'


def test_the_rules_only_use_labels_the_metrics_carry():
    label_values = {"category", "disposition", "status", "error_type", "limiter", "result", "provider", "source", "le", "job"}
    for a in ALERTS:
        for match in re.findall(r"\{([^}]*)\}", a["expr"]):
            if "=" not in match:
                continue
            for label in re.findall(r"([a-z_]+)\s*(?:=~|!=|=)", match):
                assert label in label_values, f'{a["alert"]}: unknown label {label}'


def test_the_runbook_table_and_the_rules_list_the_same_alerts():
    monitoring = DOC[DOC.index("## Monitoring"):DOC.index("## Access control")]
    in_docs = set(re.findall(r"`(Cecilai[A-Za-z0-9]+)`", monitoring))
    assert in_docs == {a["alert"] for a in ALERTS}, (sorted(in_docs ^ {a["alert"] for a in ALERTS}))


def test_the_promtool_unit_tests_only_name_alerts_that_exist():
    tests = yaml.safe_load((ROOT / "ops" / "alerts_test.yml").read_text(encoding="utf-8"))
    names = {a["alert"] for a in ALERTS}
    tested = {t["alertname"] for case in tests["tests"] for t in case["alert_rule_test"]}
    assert tested <= names and len(tested) >= 9


def test_the_dashboard_queries_only_metrics_the_service_exposes():
    import json

    from fastapi.testclient import TestClient
    from api import main

    dashboard = json.loads((ROOT / "ops" / "grafana" / "dashboards" / "cecilai.json").read_text(encoding="utf-8"))
    scraped = TestClient(main.app).get("/metrics", headers={"X-Admin-Key": "test-admin-key"}).text
    exposed = exposed_metrics() | {base(m.group(1)) for m in re.finditer(r"^# TYPE (\S+) ", scraped, re.M)}
    exprs = [t["expr"] for p in dashboard["panels"] for t in p["targets"]]
    assert len(exprs) >= 15
    for expr in exprs:
        for name in re.findall(r"\bcecilai_[a-z0-9_]+", expr):
            assert base(name) in exposed, f"{expr}: {name}"

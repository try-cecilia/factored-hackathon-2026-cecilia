"""The HTTP load test measures what it says it measures: each scenario checks the disposition of every 200 and, for
handoffs, that a ticket was written for each of them."""
from __future__ import annotations

import subprocess
import sys

import pytest


def sections(text: str) -> dict[str, list[dict]]:
    out, current = {}, None
    for line in text.splitlines():
        if line.startswith("## "):
            current = out.setdefault(line[3:].strip(), [])
        elif current is not None and line.startswith("|") and not line.startswith("|---"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if cells[0] == "clients":
                header = cells
            elif "header" in locals():
                current.append(dict(zip(header, cells)))
    return out


@pytest.fixture(scope="module")
def report(tmp_path_factory):
    out = tmp_path_factory.mktemp("lt") / "report.md"
    subprocess.run([sys.executable, "-m", "ops.loadtest", "--http", "--levels", "4", "--requests", "12", "--llm-ms", "20", "--out", str(out)],
                   check=True, capture_output=True, timeout=180)
    return sections(out.read_text(encoding="utf-8"))


def test_the_report_separates_a_degraded_resolution_from_a_real_handoff(report):
    assert {"Model answering", "Model down: degraded resolution", "Model down: handoff"} <= set(report)


def test_every_answered_request_had_the_outcome_its_scenario_expects_and_handoffs_wrote_their_ticket(report):
    for title, rows in report.items():
        if not title.startswith("Model"):
            continue
        for row in rows:
            assert row["wrong_outcome"] == "0", (title, row)
            assert int(row["ok"]) > 0
            expected_tickets = row["ok"] if title.endswith("handoff") else "0"
            assert row["tickets_written"] == expected_tickets, (title, row)

"""docs/DATA.md is rendered from the committed reports and the fixture: the committed page must be what they give today,
its traced row must be the fixture's bytes, and every link on it must resolve."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

from eval import data_page

ROOT = data_page.ROOT
LINK = re.compile(r"\]\(([^)\s]+)\)")


@pytest.fixture(scope="module")
def example(tmp_path_factory):
    return data_page.collect_example(tmp_path_factory.mktemp("data_page"))


def _slug(heading: str) -> str:
    """GitHub's anchor for a heading: lower case, punctuation dropped, spaces to hyphens."""
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


def test_the_committed_page_is_what_the_reports_render_today(example):
    committed = (ROOT / data_page.OUT).read_text(encoding="utf-8")
    assert committed == data_page.render(*data_page.inputs(example)), (
        "docs/DATA.md is stale: a report, the fixture or the code it reads changed. Run `python -m eval.data_page` and commit it")


def test_the_traced_row_is_a_line_of_the_fixture_file_with_the_hash_the_page_shows(example):
    source = ROOT / data_page.FIXTURE / example["source_file"]
    assert hashlib.sha256(source.read_bytes()).hexdigest() == example["sha256"]
    assert source.stat().st_size == example["bytes"]
    assert source.read_text(encoding="utf-8").splitlines()[example["line_no"] - 1] == example["line"]
    page = (ROOT / data_page.OUT).read_text(encoding="utf-8")
    assert example["sha256"] in page and example["line"] in page


def test_the_traced_row_passed_every_error_rule_and_reached_both_transaction_marts(example):
    assert all(ok for _, _, severity, ok in example["rules"] if severity == "error")
    assert example["gold_daily_activity"]["n_transactions"] >= 1
    assert example["gold_customer_summary"]["n_transactions"] >= 1


def test_every_link_on_the_page_resolves():
    page = (ROOT / data_page.OUT).read_text(encoding="utf-8")
    links = [link for link in LINK.findall(page) if not link.startswith(("http://", "https://"))]
    assert links
    for link in links:
        path, _, anchor = link.partition("#")
        target = (ROOT / data_page.OUT).parent / path
        assert target.exists(), f"{link} does not exist"
        if anchor:
            headings = [line.lstrip("#") for line in target.read_text(encoding="utf-8").splitlines() if line.startswith("#")]
            assert anchor in {_slug(h) for h in headings}, f"{link}: no such heading"


def test_the_readme_links_the_page():
    assert "(docs/DATA.md)" in (ROOT / "README.md").read_text(encoding="utf-8")


def test_a_reader_is_found_whatever_the_case_of_its_sql(tmp_path):
    (tmp_path / "agent").mkdir()
    (tmp_path / "agent" / "tools.py").write_text('SQL = "select amount from transactions where customer_id = ?"\n', encoding="utf-8")
    (tmp_path / "analysis").mkdir()
    (tmp_path / "analysis" / "report.py").write_text('SQL = "SELECT 1 FROM customers c Join products p USING (customer_id)"\n', encoding="utf-8")
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "demo.py").write_text('NAME = "the transactions_daily view"\n', encoding="utf-8")
    found = data_page.readers(["transactions", "products", "branches"], root=tmp_path)
    assert found == {"transactions": ["agent/tools.py"], "products": ["analysis/report.py"], "branches": []}

"""The README's headline figures match the generated reports (eval/check_readme.py)."""
from __future__ import annotations

from pathlib import Path

import pytest

from eval import check_readme


@pytest.mark.skipif(not Path("eval/reports/system_eval.json").exists(), reason="per-case reports are not in the public copy")
def test_the_readme_figures_match_the_reports(capsys):
    assert check_readme.main() == 0, capsys.readouterr().out


def test_cells_read_decimal_points_and_thousands_commas():
    assert check_readme.numbers("**95.0%** [86.3–98.3], 3,425 of 6,701 (4 missed)") == [95.0, 86.3, 98.3, 3425, 6701, 4]


REPORTS_HERE = pytest.mark.skipif(not Path("eval/reports/system_eval.json").exists(), reason="per-case reports are not in the public copy")
NON_LLM = "| Latency p50 / p95 per case (non-LLM, local) |"
OLD = {"EVALUATION.md": [("| Handling time |", "| Handling time | 221 s (≈3.7 min) | 6.5 ms per case (p95 31 ms) | 15.5 ms per case (p95 61 ms) **excluding the LLM** |"),
                         (NON_LLM, NON_LLM + " 6.5 / 31.3 ms | 15.5 / 60.8 ms | 23.1 / 57.7 ms |"),
                         ("| Total per inquiry |", "| Total per inquiry | **≈341 s (≈5.7 min)** | milliseconds | **1.9 s p50, 4.2 s p95 per case with Claude Sonnet 5** (held-out live run) |")],
       "docs/slides_outline.md": [("| p50 / p95 latency per case |", "| p50 / p95 latency per case | 6.5 / 31.3 ms | 1.9 / 4.2 s | 1.1 / 4.2 s |")]}


def _docs(tmp_path) -> Path:
    for doc in {d for d, _, _ in check_readme.LATENCY_ROWS}:
        (tmp_path / doc).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / doc).write_text(Path(doc).read_text(encoding="utf-8"), encoding="utf-8")
    return tmp_path


def _replace_row(path: Path, start: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    old = next(ln for ln in text.split("\n") if ln.startswith(start))
    path.write_text(text.replace(old, new), encoding="utf-8")


@REPORTS_HERE
def test_a_latency_left_behind_by_a_regeneration_fails(tmp_path):
    """The offline latencies change with the machine that regenerates the reports; the docs kept citing the old ones."""
    root = _docs(tmp_path)
    assert check_readme.check_latencies(root) == []
    _replace_row(root / "EVALUATION.md", NON_LLM, OLD["EVALUATION.md"][1][1])
    found = check_readme.check_latencies(root)
    assert len(found) == 3 and all("non-LLM" in f and "the report says" in f for f in found)


@REPORTS_HERE
@pytest.mark.parametrize("row,why", [
    (NON_LLM + " 2.4 / 8.5 ms | 5.0 / 17.5 ms |", "2 cells, expected 3"),                    # a column removed
    (NON_LLM + " |", "1 cells, expected 3"),                                                 # every column removed (one empty cell left)
    (NON_LLM + " 2.4 / 8.5 ms | 5.0 / 17.5 ms | 5.2 / 21.7 ms | 1 / 2 ms |", "4 cells, expected 3"),  # a column added
    (NON_LLM + " 2.4 / 8.5 s | 5.0 / 17.5 ms | 5.2 / 21.7 ms |", "(unit ms)"),               # ms changed to s
])
def test_a_latency_row_with_other_columns_or_another_unit_fails(tmp_path, row, why):
    root = _docs(tmp_path)
    _replace_row(root / "EVALUATION.md", NON_LLM, row)
    assert any(why in f for f in check_readme.check_latencies(root)), check_readme.check_latencies(root)


@REPORTS_HERE
def test_a_live_latency_in_ms_instead_of_seconds_fails(tmp_path):
    root = _docs(tmp_path)
    _replace_row(root / "docs/slides_outline.md", "| p50 / p95 latency per case |", "| p50 / p95 latency per case | 2.4 / 8.5 ms | 1.2 / 2.6 ms | 1.0 / 3.8 s |")
    assert [f for f in check_readme.check_latencies(root) if "(unit s)" in f]


@REPORTS_HERE
def test_writing_the_latencies_fixes_old_figures_and_touches_nothing_else(tmp_path):
    root = _docs(tmp_path)
    current = {doc: (root / doc).read_text(encoding="utf-8") for doc in OLD}
    for doc, rows in OLD.items():
        for start, old in rows:
            _replace_row(root / doc, start, old)
    assert len(check_readme.check_latencies(root)) == 9
    assert check_readme.latencies(root, write=True) == []
    assert check_readme.check_latencies(root) == []
    assert {doc: (root / doc).read_text(encoding="utf-8") for doc in OLD} == current  # every other cell and line as it was


@REPORTS_HERE
def test_checking_writes_nothing(tmp_path):
    root = _docs(tmp_path)
    _replace_row(root / "EVALUATION.md", NON_LLM, OLD["EVALUATION.md"][1][1])
    before = (root / "EVALUATION.md").read_text(encoding="utf-8")
    check_readme.check_latencies(root)
    assert (root / "EVALUATION.md").read_text(encoding="utf-8") == before

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


@pytest.mark.skipif(not Path("eval/reports/system_eval.json").exists(), reason="per-case reports are not in the public copy")
def test_a_latency_left_behind_by_a_regeneration_fails(tmp_path):
    """The offline latencies change with the machine that regenerates the reports; the docs kept citing the old ones."""
    for doc in {d for d, _, _ in check_readme.LATENCY_ROWS}:
        (tmp_path / doc).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / doc).write_text(Path(doc).read_text(encoding="utf-8"), encoding="utf-8")
    assert check_readme.check_latencies(tmp_path) == []
    evaluation = tmp_path / "EVALUATION.md"
    text = evaluation.read_text(encoding="utf-8")
    old = next(ln for ln in text.splitlines() if ln.startswith("| Latency p50 / p95 per case (non-LLM, local) |"))
    evaluation.write_text(text.replace(old, "| Latency p50 / p95 per case (non-LLM, local) | 6.5 / 31.3 ms | 15.5 / 60.8 ms | 23.1 / 57.7 ms |"), encoding="utf-8")
    found = check_readme.check_latencies(tmp_path)
    assert len(found) == 3 and all("non-LLM" in f for f in found)

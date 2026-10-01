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

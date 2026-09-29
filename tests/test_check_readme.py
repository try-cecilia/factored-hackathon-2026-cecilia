"""The README's headline figures match the generated reports (eval/check_readme.py)."""
from __future__ import annotations

from pathlib import Path

import pytest

from eval import check_readme

pytestmark = pytest.mark.skipif(not Path("eval/reports/system_eval.json").exists(), reason="per-case reports are not in the public copy")


def test_the_readme_figures_match_the_reports(capsys):
    assert check_readme.main() == 0, capsys.readouterr().out

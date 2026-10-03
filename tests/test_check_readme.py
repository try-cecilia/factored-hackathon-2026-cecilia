"""The README's headline figures match the generated reports (eval/check_readme.py)."""
from __future__ import annotations

import copy
import json
import re
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
    for doc in {d for d, _, _ in check_readme.LATENCY_ROWS} | {str(check_readme.LANDING)}:
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


# The landing's machine-dependent figures (web/src/landing/figures.ts): the offline latencies and the day of the offline run.
LANDING_HERE = pytest.mark.skipif(not (Path("eval/reports/system_eval.json").exists() and check_readme.LANDING.exists()),
                                  reason="per-case reports or the landing are not in this copy")
OLD_LANDING = {
    "keywordLatencyP50": "4.1", "keywordLatencyP95": "13.3", "idealLatencyP50": "7.8",
    "idealLatencyP95": "29.2", "adversarialLatencyP50": "7.0", "adversarialLatencyP95": "23.1",
}


def _landing(root: Path) -> Path:
    return root / check_readme.LANDING


def _set_value(path: Path, name: str, value: str) -> None:
    """The figure `name` with another value and nothing else changed (its digits, source and binding as they were)."""
    text = path.read_text(encoding="utf-8")
    line = next(ln for ln in text.split("\n") if ln.startswith(f"  {name}: "))
    path.write_text(text.replace(line, re.sub(r"\((\d+(?:\.\d+)?),", f"({value},", line, count=1)), encoding="utf-8")


def _set_day(path: Path, iso: str) -> None:
    text = path.read_text(encoding="utf-8")
    path.write_text(re.sub(r"(export const offlineRunDate: Day = \{ iso: ')[\d-]+'", rf"\g<1>{iso}'", text), encoding="utf-8")


@LANDING_HERE
def test_writing_fixes_the_landings_old_latencies_and_day_and_nothing_else(tmp_path):
    root = _docs(tmp_path)
    current = _landing(root).read_text(encoding="utf-8")
    for name, old in OLD_LANDING.items():
        _set_value(_landing(root), name, old)
    _set_day(_landing(root), "2026-10-02")
    found = check_readme.landing(root)
    assert len(found) == 7 and all(f.startswith(str(check_readme.LANDING)) for f in found), found
    assert check_readme.landing(root, write=True) == []
    assert check_readme.landing(root) == []
    assert _landing(root).read_text(encoding="utf-8") == current  # byte for byte: only those values changed back


@LANDING_HERE
def test_the_landing_writer_never_touches_a_figure_outside_its_list(tmp_path):
    """The live figures and the security ones are bound to reports too, but they do not depend on the machine."""
    root = _docs(tmp_path)
    for name, other in (("sonnetP50", "9.9"), ("haikuCost", "0.1234"), ("sessionTokenBits", "1"), ("liveCases", "1")):
        _set_value(_landing(root), name, other)
    _set_value(_landing(root), "keywordLatencyP50", "4.1")
    before = _landing(root).read_text(encoding="utf-8")
    assert check_readme.landing(root, write=True) == []
    after = _landing(root).read_text(encoding="utf-8")
    changed = [(a, b) for a, b in zip(before.split("\n"), after.split("\n")) if a != b]
    assert len(changed) == 1 and changed[0][1].startswith("  keywordLatencyP50: json(2.4,"), changed
    for name in ("sonnetP50: json(9.9,", "haikuCost: json(0.1234,", "sessionTokenBits: fig(1,", "liveCases: json(1,"):
        assert f"  {name}" in after, name  # left as it was: outside the list, never written


@LANDING_HERE
@pytest.mark.parametrize("edit,why", [
    (lambda t: t.replace("  idealLatencyP95: json(", "  idealLatencyP95x: json("), "0 lines start with 'idealLatencyP95:'"),  # renamed
    (lambda t: t.replace("  keywordLatencyP50: json(2.4, 1, OFFLINE, [...KEYWORD, 'latency_ms_p50']),",
                         "  keywordLatencyP50: json(2.4, 1, OFFLINE, [...KEYWORD, 'latency_ms_p50']),\n  keywordLatencyP50: json(2.4, 1, OFFLINE, [...KEYWORD, 'latency_ms_p50']),"),
     "2 lines start with 'keywordLatencyP50:'"),                                                                       # duplicated
    (lambda t: t.replace("[...KEYWORD, 'latency_ms_p95']", "[...IDEAL, 'latency_ms_p95']"), "expected system_eval › baseline › latency_ms_p95"),  # other system
    (lambda t: t.replace("json(17.5, 1, OFFLINE, [...IDEAL, 'latency_ms_p95'])", "json(17.5, 1, OFFLINE, [...IDEAL, 'latency_ms_p50'])"), "expected system_eval › proposed (scripted) › latency_ms_p95"),  # other field
    (lambda t: t.replace("adversarialLatencyP50: json(", "adversarialLatencyP50: fig("), "is not shaped as expected"),  # another binding
    (lambda t: re.sub(r"(offlineRunDate: Day = \{ iso: '[\d-]+', source: )OFFLINE", r"\g<1>LIVE", t), "cites LIVE, expected the report system_eval"),  # another report for the day
])
def test_an_unexpected_landing_writes_nothing(tmp_path, edit, why):
    root = _docs(tmp_path)
    path = _landing(root)
    _set_value(path, "adversarialLatencyP95", "23.1")  # a figure the writer could fix, if the file were as expected
    path.write_text(edit(path.read_text(encoding="utf-8")), encoding="utf-8")
    before = path.read_text(encoding="utf-8")
    problems = check_readme.landing(root, write=True)
    assert any(why in p for p in problems), problems
    assert path.read_text(encoding="utf-8") == before  # not even the figures it could have fixed


@LANDING_HERE
def test_checking_the_landing_writes_nothing(tmp_path):
    root = _docs(tmp_path)
    _set_value(_landing(root), "idealLatencyP50", "7.8")
    before = _landing(root).read_text(encoding="utf-8")
    assert [f for f in check_readme.check_latencies(root) if "idealLatencyP50" in f]
    assert _landing(root).read_text(encoding="utf-8") == before


# One rounding for every written figure: the cases web/src/landing/rounding.test.ts checks too.
ROUNDING = json.loads(Path("web/src/landing/rounding-cases.json").read_text(encoding="utf-8"))["cases"] if Path("web/src/landing/rounding-cases.json").exists() else []


@pytest.mark.skipif(not ROUNDING, reason="the landing is not in this copy")
@pytest.mark.parametrize("case", ROUNDING, ids=lambda c: f"{c['value']}-{c['digits']}-{c.get('shift', 0)}")
def test_the_rounding_matches_the_landings_shared_cases(case):
    assert check_readme._fixed(case["value"], case["digits"], case.get("shift", 0)) == case["expected"]


def _with_latency(monkeypatch, value: float) -> None:
    """The reports as they are, but the keyword bot's offline p50 is `value`."""
    real = check_readme.load
    def load(name: str) -> dict:
        systems = copy.deepcopy(real(name))
        if name == "system_eval":
            systems["baseline"]["latency_ms_p50"] = value
        return systems
    monkeypatch.setattr(check_readme, "load", load)


@LANDING_HERE
# Latencies are never negative: the sign is the shared cases' business, not the documents'.
@pytest.mark.parametrize("case", [c for c in ROUNDING if c["digits"] == 1 and not c.get("shift") and c["value"] >= 0], ids=lambda c: str(c["value"]))
def test_evaluation_the_slides_and_the_landing_round_a_latency_the_same(tmp_path, monkeypatch, case):
    root = _docs(tmp_path)
    _with_latency(monkeypatch, case["value"])
    assert check_readme.latencies(root, write=True) == [] and check_readme.landing(root, write=True) == []
    assert check_readme.check_latencies(root) == []
    want = case["expected"]
    evaluation = (root / "EVALUATION.md").read_text(encoding="utf-8").split("\n")
    slides = (root / "docs/slides_outline.md").read_text(encoding="utf-8").split("\n")
    assert next(ln for ln in evaluation if ln.startswith("| Handling time |")).split("|")[3].strip().startswith(f"{want} ms per case")
    assert next(ln for ln in evaluation if ln.startswith(NON_LLM)).split("|")[2].strip().startswith(f"{want} / ")
    assert next(ln for ln in slides if ln.startswith("| p50 / p95 latency per case |")).split("|")[2].strip().startswith(f"{want} / ")
    assert f"  keywordLatencyP50: json({want}, 1, OFFLINE," in _landing(root).read_text(encoding="utf-8")


def _crlf(path: Path) -> bytes:
    data = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    path.write_bytes(data)
    return data


@LANDING_HERE
def test_a_crlf_landing_keeps_every_byte_but_the_value(tmp_path):
    root = _docs(tmp_path)
    current = _crlf(_landing(root))
    _set_value_bytes(_landing(root), b"keywordLatencyP50: json(2.4,", b"keywordLatencyP50: json(4.1,")
    assert check_readme.landing(root, write=True) == []
    assert _landing(root).read_bytes() == current  # 259-odd CRLF endings kept, only the value back


@REPORTS_HERE
def test_a_crlf_document_keeps_every_byte_but_the_cells(tmp_path):
    root = _docs(tmp_path)
    current = _crlf(root / "EVALUATION.md")
    _set_value_bytes(root / "EVALUATION.md", NON_LLM.encode() + b" 2.4 / 8.5 ms", NON_LLM.encode() + b" 6.5 / 31.3 ms")
    assert check_readme.latencies(root, write=True) == []
    assert (root / "EVALUATION.md").read_bytes() == current


def _set_value_bytes(path: Path, old: bytes, new: bytes) -> None:
    data = path.read_bytes()
    assert data.count(old) == 1, old
    path.write_bytes(data.replace(old, new))

"""The labeling page of the human set: every message as text next to its situation, no network, and a CSV that
`agreement` reads as is.

Every message here is **fake data written to test the page**, not an answer of the form.
"""
from __future__ import annotations

import csv
import json
import re
import shutil
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

import pytest

from eval.human_set import classifier_eval as ce
from eval.human_set import labeling

ROOT = Path(__file__).resolve().parent.parent
ROWS = [
    {"message_id": "3:fx", "situation": "fx", "language": "es", "message": "a cuanto esta el dolar hoy?"},
    {"message_id": "1:fraud", "situation": "fraud", "language": "pt",
     "message": 'tem uma compra "estranha" no cartão 1234, não fui eu\r\nme ajuda'},
    {"message_id": "2:balance_all", "situation": "balance_all", "language": "es",
     "message": "<script>alert('x')</script> & <b>cuánto</b> tengo, en total?"},
    {"message_id": "2:family_account", "situation": "family_account", "language": "es",
     "message": "cuanta plata tiene mi mama en su cuenta https://example.com/x.png"},
]
LABELS = {"3:fx": "matches", "1:fraud": "ambiguous", "2:balance_all": "something_else", "2:family_account": "matches"}


class Page(HTMLParser):
    """The text of each card's situation and message, the embedded sheet, and every attribute that could load something."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.messages, self.situations, self.loads, self.scripts, self._into = [], [], [], [], None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.loads += [(tag, k, v) for k, v in attrs.items() if k in ("src", "href", "action", "formaction", "srcset", "poster", "data")]
        if tag == "p" and attrs.get("class") in ("msg", "sit"):
            self._into = self.messages if attrs["class"] == "msg" else self.situations
            self._into.append("")
        elif tag == "script":
            self._into = self.scripts
            self.scripts.append({"type": attrs.get("type"), "id": attrs.get("id"), "text": ""})

    def handle_endtag(self, tag):
        if tag in ("p", "script"):
            self._into = None

    def handle_data(self, data):
        if self._into is self.scripts:
            self.scripts[-1]["text"] += data
        elif self._into is not None:
            self._into[-1] += data


def sheet_of(tmp_path, rows=ROWS) -> Path:
    path = tmp_path / "human_labeling_sheet.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["message_id", "situation", "language", "message", "label"])
        w.writerows([[r["message_id"], r["situation"], r["language"], r["message"], ""] for r in rows])
    return path


def parse(path: Path) -> Page:
    page = Page()
    page.feed(path.read_text(encoding="utf-8"))
    return page


def test_the_situations_are_the_ten_of_the_form_in_its_own_spanish():
    texts = labeling.situations()
    assert set(texts) == set(ce.SITUATION_INTENT)
    worker = (ROOT / "eval/human_set/worker.js").read_text(encoding="utf-8")
    assert all(f'"{text}"' in worker for text in texts.values())
    assert texts["fx"] == "Saber a cuánto está hoy el dólar."


def test_the_page_shows_every_message_as_text_next_to_its_situation_and_embeds_the_sheet(tmp_path):
    [path] = labeling.write_pages(["Ana María"], sheet_of(tmp_path))
    assert path == tmp_path / "human_labeling_Ana_Maria.html"
    page, raw = parse(path), path.read_text(encoding="utf-8")
    lf = lambda text: text.replace("\r\n", "\n")  # noqa: E731 - a browser shows a CRLF as one line break
    assert [lf(m) for m in page.messages] == [lf(r["message"]) for r in ROWS]
    texts = labeling.situations()
    assert [s.split(" ", 1)[1] for s in page.situations] == [texts[r["situation"]] for r in ROWS]
    assert "<script>alert" not in raw and "<b>cuánto</b>" not in raw  # rendered as text, never as HTML
    data = next(s for s in page.scripts if s["id"] == "sheet")
    assert data["type"] == "application/json" and "<" not in data["text"]  # nothing in it can close the script element
    embedded = json.loads(data["text"])
    assert embedded["rows"] == ROWS and embedded["labeler"] == "Ana_Maria" and len(embedded["hash"]) == 16
    assert 'lang="es"' in raw and "Coincide" in raw and "Ambiguo" in raw and "Otra cosa" in raw


def test_the_page_loads_nothing_from_anywhere_and_forbids_network_calls(tmp_path):
    [path] = labeling.write_pages(["ana"], sheet_of(tmp_path))
    page, raw = parse(path), path.read_text(encoding="utf-8")
    assert page.loads == []  # no src, no href: the URL in a message is text
    assert not re.search(r"(?i)https?:", raw.replace("https://example.com/x.png", ""))  # only as that message's text
    assert "default-src 'none'" in raw and "@import" not in raw and "url(" not in raw
    module = next(s for s in page.scripts if s["type"] == "module")["text"]
    assert module.strip() == labeling.LOGIC_JS.read_text(encoding="utf-8").strip()  # the tested file, inlined as is


def test_the_hash_follows_the_sheet_so_saved_progress_never_lands_on_another_sheet(tmp_path):
    first = json.loads(next(s for s in parse(labeling.write_pages(["ana"], sheet_of(tmp_path))[0]).scripts if s["id"] == "sheet")["text"])
    other = tmp_path / "other"
    other.mkdir()
    second = json.loads(next(s for s in parse(labeling.write_pages(["ana"], sheet_of(other, ROWS[:3]))[0]).scripts
                             if s["id"] == "sheet")["text"])
    assert first["hash"] != second["hash"]


def test_labelers_get_their_own_file_and_bad_names_or_sheets_are_refused(tmp_path):
    sheet = sheet_of(tmp_path)
    assert [p.name for p in labeling.write_pages(["ana", "beto"], sheet)] == ["human_labeling_ana.html", "human_labeling_beto.html"]
    with pytest.raises(ValueError, match="same file"):
        labeling.write_pages(["Ana", "ana!"], sheet)
    with pytest.raises(ValueError, match="letters or digits"):
        labeling.write_pages(["¡!"], sheet)
    with pytest.raises(ValueError, match="situation"):
        labeling.write_pages(["ana"], sheet_of(tmp_path, [{**ROWS[0], "situation": "weather"}]))


def test_the_third_person_gets_only_the_disagreements(tmp_path):
    [path] = labeling.write_pages(["carla"], sheet_of(tmp_path), only={"1:fraud", "2:balance_all"})
    assert [r["message_id"] for r in json.loads(next(s for s in parse(path).scripts if s["id"] == "sheet")["text"])["rows"]] == \
        ["1:fraud", "2:balance_all"]


def test_the_page_command_writes_the_pages_and_the_third_persons_page(tmp_path, monkeypatch):
    sheet = sheet_of(tmp_path)
    agreement = tmp_path / "agreement.json"
    agreement.write_text(json.dumps({"disagreements": [{"message_id": "3:fx"}]}), encoding="utf-8")
    monkeypatch.setattr(ce, "SHEET", sheet)
    monkeypatch.setattr(ce, "AGREEMENT", agreement)
    monkeypatch.setattr(ce, "RAW", tmp_path / "missing.jsonl")  # the page needs the sheet only
    monkeypatch.setattr(sys, "argv", ["classifier_eval", "page", "--labeler", "ana", "--labeler", "beto"])
    ce.main()
    monkeypatch.setattr(sys, "argv", ["classifier_eval", "page", "--labeler", "carla", "--only-disagreements"])
    ce.main()
    third = json.loads(next(s for s in parse(tmp_path / "human_labeling_carla.html").scripts if s["id"] == "sheet")["text"])
    assert (tmp_path / "human_labeling_ana.html").exists() and (tmp_path / "human_labeling_beto.html").exists()
    assert [r["message_id"] for r in third["rows"]] == ["3:fx"]


NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_the_page_logic_passes_its_node_tests():
    done = subprocess.run([NODE, "--test", "eval/human_set/labeling_page.test.mjs"], cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8")
    assert done.returncode == 0, done.stdout + done.stderr


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_the_csv_the_page_downloads_is_read_back_by_agreement(tmp_path):
    """The page's own code writes the file (run with node), and `read_labels` reads it as the labeler sends it."""
    script = (f"import {{ toCsv }} from {json.dumps(labeling.LOGIC_JS.as_uri())};\n"
              "let input = ''; for await (const chunk of process.stdin) input += chunk;\n"
              "const { rows, labels } = JSON.parse(input); process.stdout.write(toCsv(rows, labels));\n")
    done = subprocess.run([NODE, "--input-type=module", "-e", script], input=json.dumps({"rows": ROWS, "labels": LABELS}).encode(),
                          capture_output=True, check=True)
    path = tmp_path / "human_labels_ana.csv"
    path.write_bytes(done.stdout)
    assert ce.read_labels(path) == LABELS
    with open(path, newline="", encoding="utf-8") as f:
        back = list(csv.DictReader(f))
    assert list(back[0]) == ["message_id", "situation", "language", "message", "label"]
    assert [{k: r[k] for k in ("message_id", "situation", "language", "message")} for r in back] == ROWS
    other = dict(LABELS, **{"3:fx": "something_else"})
    path_b = tmp_path / "human_labels_beto.csv"
    path_b.write_bytes(subprocess.run([NODE, "--input-type=module", "-e", script], capture_output=True, check=True,
                                      input=json.dumps({"rows": ROWS, "labels": other}).encode()).stdout)
    rep = ce.agreement(ce.read_labels(path), ce.read_labels(path_b))
    assert rep["n"] == 4 and [d["message_id"] for d in rep["disagreements"]] == ["3:fx"]

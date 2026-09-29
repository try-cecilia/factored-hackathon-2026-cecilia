"""La herramienta del set humano: hoja de etiquetado, acuerdo (kappa) y puntuación del clasificador congelado.

Todos los mensajes de estos tests son **datos falsos escritos para probar la herramienta**: no son respuestas reales
del formulario ni prueban nada sobre el clasificador.
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import pytest

from eval.human_set import classifier_eval as ce

PHRASES = {
    "balance_all": "cuanto dinero tengo en total en mis cuentas",
    "transactions": "muestrame los ultimos movimientos de mi tarjeta de debito",
    "payment_ok": "estoy al dia con el pago de mi tarjeta de credito",
    "fx": "a cuanto esta el dolar hoy",
    "fraud": "hay una compra en mi tarjeta que yo no hice, es un fraude",
    "out_of_scope": "quiero cambiar mi direccion porque me mude",
    "trace": "hice una transferencia hace unos dias y todavia no llego",
}


def write_raw(path: Path, people: int, saw_system: int = 0) -> None:
    rows = [{"id": i, "created_at": "2026-09-29", "lang": "es" if i % 2 else "pt", "country": "Argentina",
             "saw_system": 0, "consent_version": "x", "answers": dict(PHRASES)} for i in range(1, people + 1)]
    rows += [{"id": 1000 + i, "created_at": "2026-09-29", "lang": "es", "country": "Argentina", "saw_system": 1,
              "consent_version": "x", "answers": {"balance_all": "no debería contar"}} for i in range(saw_system)]
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def all_match(messages):
    return {m["message_id"]: ("matches", "agreed") for m in messages}


def agreement_of(messages):
    labels = {m["message_id"]: "matches" for m in messages}
    return ce.agreement(labels, dict(labels))


def test_the_sheet_leaves_out_people_who_saw_the_system_and_carries_no_system_output(tmp_path):
    raw = tmp_path / "raw.jsonl"
    write_raw(raw, people=3, saw_system=2)
    messages, counts = ce.read_messages(raw)
    assert counts == {"submissions": 3, "left_out_saw_system": 2} and len(messages) == 3 * len(PHRASES)
    out = tmp_path / "sheet.csv"
    ce.write_sheet(messages, out)
    rows = list(csv.DictReader(open(out, encoding="utf-8")))
    assert list(rows[0].keys()) == ["message_id", "situation", "language", "message", "label"]
    assert all(r["label"] == "" and not r["message_id"].startswith("100") for r in rows)
    ce.write_sheet(messages, tmp_path / "again.csv")
    assert (tmp_path / "again.csv").read_text(encoding="utf-8") == out.read_text(encoding="utf-8")  # fixed seed


def test_kappa_matches_a_value_worked_out_by_hand():
    a = ["matches"] * 5 + ["ambiguous"] * 5
    b = ["matches"] * 3 + ["ambiguous"] * 2 + ["ambiguous"] * 3 + ["matches"] * 2
    # agreement 6 of 10 = 0.6; chance = 0.5 * 0.5 + 0.5 * 0.5 = 0.5; kappa = (0.6 - 0.5) / (1 - 0.5) = 0.2
    assert ce.cohen_kappa(a, b) == 0.2
    assert ce.cohen_kappa(a, a) == 1.0
    assert ce.cohen_kappa(["matches"] * 4, ["matches"] * 4) is None  # undefined: one label only


def test_agreement_reports_kappa_before_settling_and_a_third_person_settles_only_the_disagreements():
    a = {"1": "matches", "2": "matches", "3": "ambiguous", "4": "something_else"}
    b = {"1": "matches", "2": "ambiguous", "3": "ambiguous", "4": "matches"}
    alone = ce.agreement(a, b)
    settled = ce.agreement(a, b, third={"2": "matches", "4": "something_else"})
    assert alone["kappa"] == settled["kappa"]  # settling a disagreement never changes the agreement between the first two
    assert (alone["unresolved"], settled["unresolved"], settled["resolved_by_third"]) == (2, 0, 2)
    assert settled["final"]["1"] == ("matches", "agreed") and settled["final"]["2"] == ("matches", "resolved")
    assert alone["final"]["4"] == (None, "unresolved")


def test_sheets_that_do_not_label_the_same_messages_or_use_unknown_labels_are_refused(tmp_path):
    with pytest.raises(ValueError, match="do not label the same messages"):
        ce.agreement({"1": "matches"}, {"2": "matches"})
    bad = tmp_path / "bad.csv"
    bad.write_text("message_id,label\n1,maybe\n", encoding="utf-8")
    with pytest.raises(ValueError, match="not one of"):
        ce.read_labels(bad)


def test_below_the_floor_the_report_says_it_is_not_a_result(tmp_path):
    raw = tmp_path / "raw.jsonl"
    write_raw(raw, people=7)  # 49 messages from 7 people: under 60 and under 8
    messages, counts = ce.read_messages(raw)
    rep = ce.score(messages, all_match(messages), counts, agreement_of(messages))
    assert rep["floor"]["below_floor"] and rep["verdict"].startswith("NOT A RESULT")
    assert "NOT A RESULT" in ce.to_markdown(rep)


def test_above_the_floor_it_counts_what_it_drops_and_scores_only_what_two_people_called_a_match(tmp_path):
    raw = tmp_path / "raw.jsonl"
    write_raw(raw, people=9)  # 63 messages from 9 people
    messages, counts = ce.read_messages(raw)
    final = all_match(messages)
    ids = [m["message_id"] for m in messages]
    final[ids[0]], final[ids[1]], final[ids[2]] = ("ambiguous", "agreed"), ("something_else", "agreed"), (None, "unresolved")
    rep = ce.score(messages, final, counts, agreement_of(messages))
    assert rep["verdict"] == "reported" and rep["counts"]["labeled_matches"] == 60
    assert rep["counts"]["dropped"] == {"ambiguous": 1, "something_else": 1, "unresolved": 1}
    assert rep["frozen"]["variant"] and len(rep["frozen"]["model_sha256"]) == 64
    assert rep["trace_requests"]["n"] <= 9 and rep["leakage"]["n"] == 60
    assert "kappa" in ce.to_markdown(rep) and "never change the classifier" in ce.to_markdown(rep)
    assert json.loads(ce.dump(rep))["counts"]["labeled_matches"] == 60  # the model returns NumPy ints: it must still serialize


def test_it_refuses_to_score_a_model_that_was_trained_on_different_data(tmp_path):
    changed = tmp_path / "train.csv"
    changed.write_text(Path(ce.TRAIN).read_text(encoding="utf-8") + "extra,balance_inquiry,es,x\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="training data changed"):
        ce.frozen_evidence(train=str(changed))
    assert ce.frozen_evidence()["train_sha256"]  # the real pair is consistent


def test_the_situation_mapping_covers_exactly_the_situations_of_the_form():
    js = Path("eval/human_set/worker.js").read_text(encoding="utf-8")
    block = js[js.index("const SITUATIONS = ["):js.index("];", js.index("const SITUATIONS = ["))]
    assert set(re.findall(r'^\s*\["(\w+)",', block, flags=re.M)) == set(ce.SITUATION_INTENT)

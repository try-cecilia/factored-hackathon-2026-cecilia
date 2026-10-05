"""What the public export removes from every commit (ops/export_public.py), matched as git-filter-repo matches it."""
from __future__ import annotations

from ops.export_public import KEPT_PDF, found, removed


def test_every_file_with_human_messages_or_customer_ids_is_removed_at_the_root_and_under_any_folder():
    """The consent lets the report quote some messages, not publish them all; the case files carry customer ids."""
    for path in ("eval/workload/human_raw.jsonl", "eval/workload/human_labeling_sheet.csv", "eval/workload/human_labeling_ana.html",
                 "eval/workload/human_labels_ana.csv", "eval/workload/human_labels_final.csv", "eval/workload/human_cases.jsonl",
                 "eval/workload/human_cases_meta.json", "eval/workload/cases_test.jsonl", "eval/reports/human_set_agreement.json",
                 "eval/reports/system_eval_cases_human_cases_live.json", "eval/reports/system_eval.json"):
        assert removed(path) and removed(f"x-payments-agent/{path}"), path


def test_the_team_console_keys_are_removed():
    """The scan by shape does not see KEY=value without quotes, so only the path keeps these keys out."""
    assert removed("CLAVES_CONSOLA.md") and removed("x-payments-agent/CLAVES_CONSOLA.md")


def test_every_pdf_but_the_team_deck_is_removed():
    """The organizer's PDFs carry their AWS keys as compressed text the scan cannot read; the deck is the team's own."""
    for path in ("LATAM_Bank_Complete_Data_Dictionary (1).pdf", "x-payments-agent/docs/dictionary.pdf", "docs/OTHER.PDF",
                 "docs/demo/final-demo-v10-2026-10-04/other.pdf", f"x-payments-agent/{KEPT_PDF}", f"{KEPT_PDF}.pdf"):
        assert removed(path), path
    assert not removed(KEPT_PDF)


def test_only_the_invented_ids_pass_the_real_id_scan():
    """The ids the team made up are not the organizer's; any other id of that shape still stops the export. The one
    below is built at run time so that the scan does not find it in this file."""
    assert found("real_dataset_id", "PRD-AB12CD34EF56, CLI-AB12CD34EF56, PRD-ZZ99ZZ99ZZ99, PRD-00AB12CD, PRD-FIX0001") == set()
    other = "CLI-" + "ZZ00ZZ00ZZ01"
    assert found("real_dataset_id", f"cliente {other}") == {other}


def test_the_reports_and_the_code_stay():
    for path in ("eval/reports/HUMAN_SET.md", "eval/reports/human_set.json", "eval/reports/SYSTEM_EVAL_cases_human_cases_LIVE.md",
                 "eval/reports/SYSTEM_EVAL.md", "eval/workload.py", "eval/human_set/cases.py", "eval/human_set/labeling_page.mjs",
                 "docs/human_set.md"):
        assert not removed(path), path

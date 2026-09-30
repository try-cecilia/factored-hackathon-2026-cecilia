"""What the public export removes from every commit (ops/export_public.py), matched as git-filter-repo's --path-glob
matches it: fnmatch, whose * crosses "/"."""
from __future__ import annotations

from fnmatch import fnmatch

from ops.export_public import REMOVE_GLOBS


def removed(path: str) -> bool:
    return any(fnmatch(path, glob) for glob in REMOVE_GLOBS)


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


def test_the_reports_and_the_code_stay():
    for path in ("eval/reports/HUMAN_SET.md", "eval/reports/human_set.json", "eval/reports/SYSTEM_EVAL_cases_human_cases_LIVE.md",
                 "eval/reports/SYSTEM_EVAL.md", "eval/workload.py", "eval/human_set/cases.py", "eval/human_set/labeling_page.mjs",
                 "docs/human_set.md"):
        assert not removed(path), path

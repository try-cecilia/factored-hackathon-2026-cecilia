"""La huella de las políticas: igual con otros saltos de línea, distinta si el código cambia."""
from __future__ import annotations

from eval import fingerprint

FILES = ("agent/policy/router.py", "agent/tools/account_tools.py", "agent/core/orchestrator.py")


def tree(root, content: bytes):
    for rel in FILES:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return root


def test_the_fingerprint_ignores_line_endings_and_changes_with_the_code(tmp_path):
    lf = tree(tmp_path / "lf", b"x = 1\ny = 2\n")
    crlf = tree(tmp_path / "crlf", b"x = 1\r\ny = 2\r\n")
    edited = tree(tmp_path / "edited", b"x = 1\ny = 3\n")
    assert fingerprint.policy_fingerprint(lf) == fingerprint.policy_fingerprint(crlf)
    assert fingerprint.policy_fingerprint(lf) != fingerprint.policy_fingerprint(edited)


def test_a_new_policy_file_changes_the_fingerprint(tmp_path):
    root = tree(tmp_path, b"x = 1\n")
    before = fingerprint.policy_fingerprint(root)
    (root / "agent/policy/extra.py").write_bytes(b"y = 1\n")
    assert fingerprint.policy_fingerprint(root) != before


def test_the_real_policy_files_are_the_ones_that_decide():
    names = {p.relative_to(fingerprint.ROOT).as_posix() for p in fingerprint.policy_files()}
    assert {"agent/policy/router.py", "agent/policy/desk.py", "agent/tools/account_tools.py",
            "agent/core/orchestrator.py"} <= names


def test_editing_a_message_template_changes_the_fingerprint(tmp_path):
    # the judge compares replies to render.MSG: a reworded template must invalidate the committed reports
    root = tree(tmp_path, b"x = 1\n")
    (root / "agent/core").mkdir(parents=True, exist_ok=True)
    render = root / "agent/core/render.py"
    render.write_bytes(b'MSG = {"abstain": {"es": "Eso no lo resuelvo."}}\n')
    before = fingerprint.policy_fingerprint(root)
    render.write_bytes(b'MSG = {"abstain": {"es": "Eso no lo puedo resolver."}}\n')
    assert fingerprint.policy_fingerprint(root) != before


def test_the_real_fingerprint_covers_templates_traces_and_the_other_inputs_of_the_evaluation():
    names = {p.relative_to(fingerprint.ROOT).as_posix() for p in fingerprint.policy_files()}
    assert {"agent/core/render.py", "agent/tools/traces.py", "agent/tools/errors.py", "agent/llm/privacy.py",
            "agent/llm/prompts.py", "agent/session/auth.py", "agent/resilience.py",
            "eval/models/intent_clf.joblib", "eval/models/intent_clf_meta.json"} <= names


def test_editing_the_judge_or_the_gold_changes_the_fingerprint(tmp_path):
    # what the evaluation measures also depends on how it judges and on what it expects: not only on the system
    for rel in ("eval/run_system_eval.py", "eval/workload/cases_test.jsonl", "eval/heldout/cases_failures.jsonl",
                "eval/fake_llm.py", "eval/categories.py"):
        root = tree(tmp_path / rel.replace("/", "_"), b"x = 1\n")
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b'{"expected": "ESCALATE"}\n')
        before = fingerprint.policy_fingerprint(root)
        target.write_bytes(b'{"expected": "AUTO_RESOLVE"}\n')
        assert fingerprint.policy_fingerprint(root) != before, rel


def test_the_real_fingerprint_covers_the_judge_the_simulated_models_and_the_gold():
    names = {p.relative_to(fingerprint.ROOT).as_posix() for p in fingerprint.policy_files()}
    assert {"eval/run_system_eval.py", "eval/categories.py", "eval/failure_eval.py", "eval/heldout.py", "eval/workload.py",
            "eval/stats.py", "eval/baseline_bot.py", "eval/fake_llm.py",
            "eval/workload/cases_test.jsonl", "eval/heldout/cases_failures.jsonl", "eval/heldout/cases_failures_2.jsonl",
            "tests/fixtures/raw/customers.csv"} <= names
    assert not any(n.startswith("eval/reports/") or n in ("eval/gate.py", "eval/tracking.py") for n in names)


def test_a_binary_file_is_hashed_as_it_is_and_only_text_gets_its_line_endings_normalised(tmp_path):
    # two different models can differ exactly where a CRLF pair sits in their bytes; they must not share a fingerprint
    a = tree(tmp_path / "a", b"x = 1\n")
    b = tree(tmp_path / "b", b"x = 1\n")
    for root, blob in ((a, b"\x00\x01\r\n\x02"), (b, b"\x00\x01\n\x02")):
        model = root / "eval/models/intent_clf.joblib"
        model.parent.mkdir(parents=True, exist_ok=True)
        model.write_bytes(blob)
    assert fingerprint.policy_fingerprint(a) != fingerprint.policy_fingerprint(b)

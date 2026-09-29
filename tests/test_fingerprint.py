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

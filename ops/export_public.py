"""Export this repository for public submission: a fresh clone, history rewritten, every blob scanned.

    python ops/export_public.py SOURCE_REPO TARGET_DIR REDACTIONS_FILE

- Removes from every commit what is organizer row-level data, what carries the human-written messages, or what is
  out of date: everything under eval/workload/ (the generated workloads, and every file of the human set: the
  form's answers, the labeling sheet, each labeler's page and labels, the final labels, the cases and their
  provenance; customer ids, digits of real products, and every message, of which the consent lets the report
  quote only some), the label agreement report (it lists each disagreement word for word), every per-case eval
  JSON (eval/reports/system_eval*.json, whatever its name), and the v2 demo video (dataset customers on screen), at
  the root or under any folder, since the history also has them under x-payments-agent/. The generated ones are
  rebuilt with `make workload eval`; the human set's report (eval/reports/HUMAN_SET.md) stays.
- Removes CLAVES_CONSOLA.md from every commit: the team's read and operator keys for the live console, which the scan
  below does not recognize by shape (KEY=value, no quotes). The redactions file carries the same keys as a second net.
- Removes every PDF from every commit: the organizer's documents were committed once, and the complete data
  dictionary carries their AWS keys as compressed text, which the scan below cannot read. A PDF that survives
  fails the export.
- Replaces the strings listed in REDACTIONS_FILE (git filter-repo format, "value==>***REMOVED***"), kept outside
  any repository: the organizer's bucket name and account id, which early commits carried, and the links to
  their documents.
- Scans every blob of every commit by shape, not by known prefix (keys, tokens, JWTs, private keys, credential
  assignments, env-var fallbacks with a literal, S3 URIs, 12-digit numbers, real dataset ids), prints what it
  finds for a person to read, and fails if a redacted value or a real dataset id survives.

Publish the result as a NEW repository: a force-push over an old one leaves the old blobs reachable. Needs
git-filter-repo (pip install git-filter-repo); GIT_FILTER_REPO overrides its path.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

# Each pattern also runs under any folder ("*/" prefix, fnmatch's * crosses "/"): the history carries these files at
# the root and under x-payments-agent/, where the subtree import put them before the move to the root.
REMOVE_GLOBS = [p for g in ("docs/demo/demo_app.webm", "eval/workload/*",  # by pattern: a new file too
                            "eval/reports/system_eval*.json", "eval/reports/human_set_agreement.json", "CLAVES_CONSOLA.md")
                for p in (g, "*/" + g)] + ["*.pdf"]
SHAPES = {
    "aws_access_key": r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b",
    "anthropic_key": r"sk-ant-[A-Za-z0-9_-]{10,}",
    "groq_key": r"\bgsk_[A-Za-z0-9]{20,}",
    "github_token": r"\bgh[pousr]_[A-Za-z0-9]{20,}",
    "jwt": r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}",
    "private_key": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    "assignment": r"(?:const|let|var|^\s*\$?\w+)\s*=\s*['\"`][A-Za-z0-9_\-./+=]{24,}['\"`]",
    "env_fallback": r"(?:\|\||getenv\([^)]*,|\.get\([^)]*,)\s*['\"][A-Za-z0-9_\-./]{24,}['\"]",
    "s3_uri": r"s3://[a-z0-9.-]{3,}",
    "twelve_digits": r"(?<!\d)\d{12}(?!\d)",
    "real_dataset_id": r"\b(?:CLI|PRD|TXN|SUC)-(?!FIX)(?![A-Z]*FIX)[0-9A-Z]{8,}\b",
}
# Ids the team made up for tests and docs: none is in the organizer's data (checked against the full warehouse on
# 2026-10-02). Only these exact strings pass; any other id of that shape still stops the export.
INVENTED_IDS = {"CLI-AB12CD34EF56", "PRD-AB12CD34EF56", "PRD-ZZ99ZZ99ZZ99", "PRD-00AB12CD"}


def found(name: str, text: str) -> set[str]:
    """What one shape finds in a blob; an invented id is not a real one."""
    return {m.group(0)[:32] for m in re.finditer(SHAPES[name], text, re.M)} - (INVENTED_IDS if name == "real_dataset_id" else set())


def git(*args: str, cwd: Path) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          check=True).stdout


def main(src: Path, target: Path, redactions: Path) -> int:
    if target.exists():  # never delete a directory someone may have passed by mistake
        sys.exit(f"{target} already exists: pick a new directory")
    git("clone", "--no-local", "--quiet", str(src), str(target), cwd=Path.cwd())
    for ref in git("branch", "-r", "--format=%(refname:short)", cwd=target).split():  # a local branch per remote one
        if "/" in ref and not ref.endswith("/HEAD"):
            subprocess.run(["git", "branch", "--quiet", ref.split("/", 1)[1], ref], cwd=target, capture_output=True)
    filtered = subprocess.run([os.environ.get("GIT_FILTER_REPO", "git-filter-repo"), "--force", "--invert-paths",
                               *[a for g in REMOVE_GLOBS for a in ("--path-glob", g)], "--replace-text", str(redactions)],
                              cwd=target, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if filtered.returncode:  # say why: the history was not rewritten, so nothing here may be published
        sys.exit(f"git-filter-repo failed (exit {filtered.returncode}); {target} must not be published:\n"
                 f"{filtered.stderr or filtered.stdout}")

    redacted = [line.split("==>")[0] for line in redactions.read_text(encoding="utf-8").splitlines() if "==>" in line]
    blobs: dict[str, tuple[str, int]] = {}
    commits = git("rev-list", "--all", cwd=target).split()
    for rev in commits:
        for line in git("ls-tree", "-r", "-l", rev, cwd=target).splitlines():
            meta, path = line.split("\t", 1)
            _, _, sha, size = meta.split()
            blobs.setdefault(sha, (path, int(size) if size.isdigit() else 0))
    print(f"{len(commits)} commits, {len(blobs)} distinct blobs, branches {git('branch', '--format=%(refname:short)', cwd=target).split()}")
    survived, real_ids = 0, 0
    for name in [*SHAPES, "large_blob"]:
        hits = set()
        for sha, (path, size) in blobs.items():
            if name == "large_blob":
                if size > 1_000_000:
                    hits.add((path, f"{size:,} bytes"))
                continue
            text = git("cat-file", "-p", sha, cwd=target)
            hits |= {(path, v) for v in found(name, text)}
        print(f"{name}: {len(hits)}" + "".join(f"\n    {p}: {v}" for p, v in sorted(hits)[:12]))
        real_ids = len(hits) if name == "real_dataset_id" else real_ids
    for sha, (path, _) in blobs.items():
        text = git("cat-file", "-p", sha, cwd=target)
        survived += sum(v in text for v in redacted)
    print(f"redacted values still present: {survived}")
    pdfs = sorted({path for path, _ in blobs.values() if path.lower().endswith(".pdf")})
    print(f"PDF files still present: {len(pdfs)}" + "".join(f"\n    {p}" for p in pdfs))
    # A real dataset id is organizer row-level data: the files that carry them are removed above, so one left means a
    # pattern missed a copy (as the x-payments-agent/ one did) and nothing here may be published.
    return 1 if survived or pdfs or real_ids else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])))

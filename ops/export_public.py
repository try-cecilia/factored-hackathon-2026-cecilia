"""Export this repository for public submission: a fresh clone, history rewritten, every blob scanned.

    python ops/export_public.py SOURCE_REPO TARGET_DIR REDACTIONS_FILE

- Removes from every commit what is organizer row-level data or out of date: every case file under eval/workload
  (the generated workloads and any other set, such as the human one: customer ids, digits of real products),
  every per-case eval JSON (eval/reports/system_eval*.json, whatever its name), and the v2 demo video (dataset
  customers on screen). The generated ones are rebuilt with `make workload eval`.
- Replaces the strings listed in REDACTIONS_FILE (git filter-repo format, "value==>***REMOVED***"), kept outside
  any repository: the organizer's bucket name and account id, which early commits carried.
- Scans every blob of every commit by shape, not by known prefix (keys, tokens, JWTs, private keys, credential
  assignments, env-var fallbacks with a literal, S3 URIs, 12-digit numbers, real dataset ids), prints what it
  finds for a person to read, and fails if a redacted value survives.

Publish the result as a NEW repository: a force-push over an old one leaves the old blobs reachable. Needs
git-filter-repo (pip install git-filter-repo); GIT_FILTER_REPO overrides its path.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

REMOVE = ["docs/demo/demo_app.webm"]
REMOVE_GLOBS = ["eval/workload/*.jsonl", "eval/reports/system_eval*.json"]  # by pattern: a new case file or report too
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
                               *[a for p in REMOVE for a in ("--path", p)], *[a for g in REMOVE_GLOBS for a in ("--path-glob", g)],
                               "--replace-text", str(redactions)],
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
    survived = 0
    for name in [*SHAPES, "large_blob"]:
        hits = set()
        for sha, (path, size) in blobs.items():
            if name == "large_blob":
                if size > 1_000_000:
                    hits.add((path, f"{size:,} bytes"))
                continue
            text = git("cat-file", "-p", sha, cwd=target)
            hits |= {(path, m.group(0)[:32]) for m in re.finditer(SHAPES[name], text, re.M)}
        print(f"{name}: {len(hits)}" + "".join(f"\n    {p}: {v}" for p, v in sorted(hits)[:12]))
    for sha, (path, _) in blobs.items():
        text = git("cat-file", "-p", sha, cwd=target)
        survived += sum(v in text for v in redacted)
    print(f"redacted values still present: {survived}")
    return 1 if survived else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])))

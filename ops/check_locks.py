"""Fails when a lock file no longer matches the pins it was compiled from (`make lock-check`, run by CI).

requirements.in and requirements-tracking.in hold the exact pins a person edits; requirements.txt and
requirements-tracking.txt are the compiled locks (`make lock`: every transitive package, each with the sha256 of its
files, so pip refuses anything else). Checked here, with no network and only the standard library:
- every package pinned in a .in is locked at that same version;
- every locked package has at least one hash and an exact version;
- the tracking lock contains every package of the serving lock, at the same version.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PIN = re.compile(r"^([A-Za-z0-9_.\-]+)==([^\s;\\]+)")


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def pins(path: Path) -> dict[str, str]:
    found = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = PIN.match(line.strip())
        if m:
            found[_norm(m.group(1))] = m.group(2)
    return found


def locked(path: Path) -> tuple[dict[str, str], list[str]]:
    """Package versions of a lock file, and the packages listed without a hash."""
    versions, unhashed, current = {}, [], None
    for line in path.read_text(encoding="utf-8").splitlines():
        m = PIN.match(line)
        if m and not line.startswith((" ", "#")):
            current = _norm(m.group(1))
            versions[current] = m.group(2)
            unhashed.append(current)
        elif "--hash=sha256:" in line and current in unhashed:
            unhashed.remove(current)
    return versions, unhashed


def problems(root: Path = ROOT) -> list[str]:
    out = []
    serving, unhashed = locked(root / "requirements.txt")
    tracking, unhashed_t = locked(root / "requirements-tracking.txt")
    out += [f"requirements.txt: {n} has no hash" for n in unhashed]
    out += [f"requirements-tracking.txt: {n} has no hash" for n in unhashed_t]
    for source, lock, versions in (("requirements.in", "requirements.txt", serving),
                                   ("requirements-tracking.in", "requirements-tracking.txt", tracking)):
        for name, version in pins(root / source).items():
            if versions.get(name) != version:
                out.append(f"{lock}: {name} is {versions.get(name)}, {source} pins {version} (run `make lock`)")
    for name, version in serving.items():
        if tracking.get(name) != version:
            out.append(f"requirements-tracking.txt: {name} is {tracking.get(name)}, the serving lock has {version}")
    return out


if __name__ == "__main__":
    found = problems()
    print("\n".join(found) if found else "lock files match their pins")
    sys.exit(1 if found else 0)

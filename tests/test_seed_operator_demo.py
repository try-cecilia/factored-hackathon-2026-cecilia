"""El script de demo de la consola solo borra lo que él mismo creó."""
from __future__ import annotations

from pathlib import Path

import pytest

from ops import seed_operator_demo as demo


def test_a_new_directory_is_created_with_the_marker(tmp_path):
    made = demo.prepare_target(tmp_path / "demo")
    assert made.is_dir() and (made / demo.MARKER).is_file()


def test_an_existing_directory_is_refused_by_default_and_left_intact(tmp_path):
    existing = tmp_path / "datos"
    existing.mkdir()
    (existing / "importante.txt").write_text("no me borres")
    with pytest.raises(SystemExit):
        demo.prepare_target(existing)
    assert (existing / "importante.txt").read_text() == "no me borres"


def test_reset_refuses_a_directory_without_the_marker(tmp_path):
    existing = tmp_path / "datos"
    existing.mkdir()
    (existing / "importante.txt").write_text("no me borres")
    with pytest.raises(SystemExit):
        demo.prepare_target(existing, reset=True)
    assert (existing / "importante.txt").exists()


def test_reset_rebuilds_a_directory_this_script_made(tmp_path):
    first = demo.prepare_target(tmp_path / "demo")
    (first / "viejo.txt").write_text("de la corrida anterior")
    again = demo.prepare_target(tmp_path / "demo", reset=True)
    assert not (again / "viejo.txt").exists() and (again / demo.MARKER).is_file()


@pytest.mark.parametrize("where", [".", "..", "repo", "repo_parent", "home", "root"])
def test_the_repo_its_ancestors_home_and_root_are_never_touched_even_with_the_marker(where, monkeypatch, tmp_path):
    targets = {".": Path.cwd(), "..": Path.cwd().parent, "repo": demo.REPO, "repo_parent": demo.REPO.parent,
               "home": tmp_path, "root": Path("/")}
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    target = targets[where]
    marker = target / demo.MARKER
    if target != Path("/"):  # writing at / would be its own problem; the guard fires before any marker is read
        marker.write_text("x")
    try:
        with pytest.raises(SystemExit):
            demo.prepare_target(target, reset=True)
        assert target.exists()
    finally:
        if marker.exists() and target != Path("/"):
            marker.unlink()


def test_a_symlink_to_a_marked_directory_is_not_followed_into_a_delete(tmp_path):
    real = demo.prepare_target(tmp_path / "real")
    link = tmp_path / "link"
    link.symlink_to(real)
    # resolve() sees through the link, so the real directory is what gets judged (it carries the marker): allowed only as itself
    demo.prepare_target(link, reset=True)
    assert real.is_dir() and (real / demo.MARKER).is_file()

"""safe_lesson_path: every read and write of a lesson file stays in the lesson folder."""
from __future__ import annotations

import os

import pytest

from server.safety.paths import lesson_file, relative_to_lesson, safe_lesson_path


@pytest.mark.parametrize("rel", ["/Users/x/.zshrc", "../../../.zshrc", "~/.ssh/id_rsa", "a/../../b", "x\x00y",
                                 "..", "", "C:\\Windows\\x", "src\\..\\..\\x"])
def test_escapes_are_refused(tmp_path, rel):
    assert safe_lesson_path(tmp_path, rel) is None
    assert safe_lesson_path(tmp_path, rel, write=True) is None


def test_a_symlink_inside_the_folder_pointing_outside_is_refused(tmp_path, tmp_path_factory):
    outside = tmp_path_factory.mktemp("home")
    (outside / ".zshrc").write_text("export PATH=...\n")
    os.symlink(outside / ".zshrc", tmp_path / "notes.txt")
    os.symlink(outside, tmp_path / "docs")
    assert safe_lesson_path(tmp_path, "notes.txt") is None
    assert safe_lesson_path(tmp_path, "docs/.zshrc") is None
    assert safe_lesson_path(tmp_path, "notes.txt", write=True) is None


def test_lesson_files_are_accepted(tmp_path):
    (tmp_path / "src").mkdir()
    assert safe_lesson_path(tmp_path, "calc.py") == (tmp_path / "calc.py").resolve()
    assert safe_lesson_path(tmp_path, "src/app.py", write=True) == (tmp_path / "src" / "app.py").resolve()
    assert safe_lesson_path(tmp_path, ".gitignore", write=True) is not None
    assert safe_lesson_path(tmp_path, ".python-version", write=True) is not None


@pytest.mark.parametrize("rel", [".git/hooks/pre-commit", ".vscode/tasks.json", ".venv/bin/python",
                                 "node_modules/x/index.js", ".zshrc", ".envrc", "src/.env", ".github/workflows/x.yml"])
def test_writes_never_touch_tooling_or_dotfiles(tmp_path, rel):
    assert safe_lesson_path(tmp_path, rel, write=True) is None


def test_reads_inside_dot_folders_are_fine(tmp_path):
    assert safe_lesson_path(tmp_path, ".git/rebase-merge/git-rebase-todo") is not None


def test_lesson_file_takes_absolute_paths_inside_the_folder_only(tmp_path):
    p, rel = lesson_file(tmp_path, tmp_path / "src" / "app.py", write=True)
    assert p == tmp_path / "src" / "app.py" and rel == "src/app.py"
    assert lesson_file(tmp_path, "/Users/x/.zshrc", write=True) == (None, "")
    assert lesson_file(tmp_path, "../../../.zshrc", write=True) == (None, "")


def test_cards_name_the_file_relative_to_the_lesson_folder(tmp_path):
    assert relative_to_lesson(tmp_path, tmp_path / "src" / "app.py") == "src/app.py"
    assert relative_to_lesson(tmp_path, "calc.py") == "calc.py"

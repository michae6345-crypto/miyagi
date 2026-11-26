"""A check's "the step's command made it" proof reads the lesson folder the way the learner's Mac does (case-insensitive
by default), so a workspace gets the same verdict on a Mac and on a case-sensitive disk (Linux CI)."""
from __future__ import annotations

import os

from server.checks.evaluator import _exists_case_aside


def test_a_folder_named_in_another_case_is_the_same_folder(tmp_path):
    (tmp_path / "MyRepo").mkdir()
    (tmp_path / "MyRepo" / "README.md").write_text("hi\n")
    assert _exists_case_aside(str(tmp_path), str(tmp_path / "MyRepo" / "README.md"))
    assert _exists_case_aside(str(tmp_path), str(tmp_path / "myrepo" / "readme.MD"))
    assert _exists_case_aside(str(tmp_path), str(tmp_path / "myrepo"))


def test_a_missing_file_is_missing_in_any_case(tmp_path):
    (tmp_path / "MyRepo").mkdir()
    assert not _exists_case_aside(str(tmp_path), str(tmp_path / "myrepo" / "index.html"))
    assert not _exists_case_aside(str(tmp_path), str(tmp_path / "other" / "index.html"))


def test_never_follows_a_link_out_of_the_lesson_folder(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret").write_text("x")
    lesson = tmp_path / "lesson"
    lesson.mkdir()
    os.symlink(outside, lesson / "Out")
    assert not _exists_case_aside(str(lesson), str(lesson / "Out" / "secret"))
    assert not _exists_case_aside(str(lesson), str(lesson / "out" / "secret"))
    assert not _exists_case_aside(str(lesson), str(tmp_path / "outside" / "secret"))

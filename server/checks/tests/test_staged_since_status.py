"""A "staged" terminal check and the git status listings on screen (evaluator._staged_since_status).

git-basics s4: s3 left a `git status` in the scrollback, then the learner edits learning.py and runs
`git add learning.py` again. That add is newer than every listing, so the listing can't say the file isn't staged.
A listing made after the add still decides, and a command that isn't `git add` never counts as staging.
"""

from __future__ import annotations

from server.checks import RunContext, evaluate_gate

STEP = {"id": "s4", "instructions": "Add a print to learning.py, then stage it with git add learning.py.",
        "targets": [{"app": "Terminal", "match": "git add learning.py"}],
        "checks": [{"id": "s4c2", "type": "screen_contains", "label": "Updated file staged", "app": "Terminal",
                    "pattern": r"git\s+add\s+learning"}]}

S3 = ["me@mac project1 % touch hello.md learning.py waiting.py",
      "me@mac project1 % git add hello.md",
      "me@mac project1 % git add learning.py",
      "me@mac project1 % git status",
      "On branch main",
      "Changes to be committed:",
      "        new file:   hello.md",
      "        new file:   learning.py",
      "Untracked files:",
      "        waiting.py"]


def _passed(step: dict, *rows: str) -> bool:
    return evaluate_gate(step, RunContext(screen={"Terminal": list(rows)}))["passed"]


def test_a_new_add_after_an_old_listing_stages_it():
    assert _passed(STEP, *S3, "me@mac project1 % git add learning.py", "me@mac project1 % ")


def test_only_the_old_add_from_before_the_listing_does_not_count():
    """The failed `git add learnig.py` mistake: s3's add is still on screen, but s4's own add never ran."""
    assert not _passed(STEP, *S3, "me@mac project1 % git add learnig.py",
                       "fatal: pathspec 'learnig.py' did not match any files", "me@mac project1 % ")


def test_a_listing_after_the_add_still_decides():
    step = {**STEP, "checks": [{"id": "c", "type": "screen_contains", "label": "learning.py staged", "app": "Terminal",
                                "pattern": r"learning\.py"}]}
    rows = ["me@mac project1 % git add learning.py", "me@mac project1 % git status", "On branch main",
            "Untracked files:", "        learning.py", "me@mac project1 % "]
    assert not _passed(step, *rows)


def test_a_command_that_is_not_git_add_never_stages():
    step = {"id": "s3", "targets": [{"app": "Terminal", "match": "touch learning.py"}],
            "checks": [{"id": "c", "type": "screen_contains", "label": "Staged learning.py file", "app": "Terminal",
                        "pattern": r"learning\.py"}]}
    rows = ["me@mac p % git status", "Untracked files:", "        hello.md", "me@mac p % touch learning.py",
            "me@mac p % "]
    assert not _passed(step, *rows)

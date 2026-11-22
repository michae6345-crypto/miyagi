"""eng-agency fix round 4 (offline: no model, keys unset, no network, no process)."""
from __future__ import annotations

import io
import zipfile

import pytest

from server.lesson.schema import MAX_LESSON_PATTERNS, MAX_STEP_TARGETS, validate_untrusted_lesson
from server.safety import packages
from server.workspace import resources


# ------------------------------------------------------------------ 3. targets count toward the lesson's patterns

def _slow_target(i: int) -> dict:
    return {"app": "Code", "file": "main.py", "match": f"(?:tg{i})?" + "a?" * 24 + "a" * 24 + "!"}


def test_validation_caps_targets_per_step():
    g = {"lesson": {"id": "x"}, "steps": [{"id": "s0", "targets": [_slow_target(i) for i in range(500)]}]}
    notes = validate_untrusted_lesson(g)
    assert len(g["steps"][0]["targets"]) == MAX_STEP_TARGETS
    assert any("targets per step" in n for n in notes)


def test_target_matches_count_toward_the_lessons_patterns():
    steps = [{"id": f"s{k}", "targets": [_slow_target(k * 100 + i) for i in range(MAX_STEP_TARGETS)],
              "checks": [{"id": f"s{k}c0", "type": "file_contains", "label": "x", "file": "main.py",
                          "pattern": f"name_{k}"}]} for k in range(30)]  # 720 target matches + 30 check patterns
    g = {"lesson": {"id": "x"}, "steps": steps}
    validate_untrusted_lesson(g)
    matches = sum(1 for s in g["steps"] for t in s["targets"] if "match" in t)
    checks = sum(len(s["checks"]) for s in g["steps"])
    assert matches + checks == MAX_LESSON_PATTERNS
    # a target over the budget keeps its file / app (the box still has a place), never its regex
    assert all(len(s["targets"]) == MAX_STEP_TARGETS for s in g["steps"])


def test_a_real_lessons_targets_are_untouched():
    g = {"lesson": {"id": "x"}, "steps": [{"id": "s1", "targets": [{"app": "Code", "file": "calc.py",
                                                                    "match": "# add goes here"}]}]}
    assert validate_untrusted_lesson(g) == []
    assert g["steps"][0]["targets"] == [{"app": "Code", "file": "calc.py", "match": "# add goes here"}]


# ------------------------------------------------------------------ 8. near misses: narrower

@pytest.mark.parametrize("name,near", [("reqeust", "requests"), ("numpyy", "numpy"), ("boto4", "boto3"),
                                       ("scikitlearn", "scikit-learn")])
def test_typos_inside_a_name_are_still_refused(name, near):
    v = packages.verdict(name)
    assert v.kind == packages.REFUSE and v.near == near


@pytest.mark.parametrize("name,near", [("boto", "boto3"), ("requests-x", "requests"), ("pyopenai", "openai")])
def test_a_name_extended_at_one_end_is_a_confirm_naming_the_look_alike(name, near):
    v = packages.verdict(name)
    assert v.kind == packages.CONFIRM and v.near == near and near in v.reason


def test_known_real_near_names_are_listed():
    assert packages.verdict("pyautogen").kind == packages.ALLOW
    assert packages.verdict("pyautogui").kind == packages.ALLOW


# ------------------------------------------------------------------ 9. a downloaded repo's harmless dotfiles

def test_a_downloaded_repo_keeps_its_example_dotfiles_and_drops_config(tmp_path):
    buf = io.BytesIO()
    names = ["main.py", ".gitignore", ".env.example", "config/.env.sample", ".streamlit/config.toml",
             ".pre-commit-config.yaml", ".gitattributes",
             # still never unpacked: editor / CI / shell / package-manager configuration, secrets, pip shadows
             ".vscode/tasks.json", ".github/workflows/ci.yml", ".github/.env.example", ".envrc", ".npmrc", ".env",
             ".streamlit/secrets.toml", ".vscode/config.toml", "pip.py", ".git/config", ".venv/.env.example"]
    with zipfile.ZipFile(buf, "w") as z:
        for name in names:
            z.writestr("repo-main/" + name, "x\n")
    dest = tmp_path / "tutorial" / "repo"
    n = resources._extract_zip(buf.getvalue(), dest)
    got = sorted(p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file())
    assert got == sorted([".env.example", ".gitattributes", ".gitignore", ".pre-commit-config.yaml",
                          ".streamlit/config.toml", "config/.env.sample", "main.py"]) and n == len(got)

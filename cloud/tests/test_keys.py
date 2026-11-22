"""Upstream keys pasted with a trailing newline, spaces or quotes are trimmed, so httpx can send the header.

An untrimmed key made every AI call a 502 (h11 LocalProtocolError, "upstream anthropic unreachable") on Nov 21.
"""
from __future__ import annotations

import importlib
import sys

import pytest


@pytest.mark.parametrize("raw", ["sk-test-key\n", "  sk-test-key ", '"sk-test-key"', "sk-test-key\r\n"])
def test_keys_are_trimmed(tmp_path, monkeypatch, raw):
    monkeypatch.syspath_prepend(str(__import__("pathlib").Path(__file__).resolve().parents[1]))
    monkeypatch.setenv("ADMIN_TOKEN", "admin-test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "miyagi.db"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", raw)
    monkeypatch.setenv("GEMINI_API_KEY", raw)
    sys.modules.pop("app", None)
    sys.modules.pop("store", None)
    app = importlib.import_module("app")
    assert app.ANTHROPIC_KEY == "sk-test-key"
    assert app.GEMINI_KEY == "sk-test-key"


def test_clean_key_is_unchanged(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(__import__("pathlib").Path(__file__).resolve().parents[1]))
    monkeypatch.setenv("ADMIN_TOKEN", "admin-test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "miyagi.db"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-clean")
    sys.modules.pop("app", None)
    sys.modules.pop("store", None)
    app = importlib.import_module("app")
    assert app.ANTHROPIC_KEY == "sk-clean"

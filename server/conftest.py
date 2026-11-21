"""Every server test: the Tiger spool is a temp folder, never ~/.miyagi/tiger-spool. The engine uploads that spool to
Tiger Data on its next connection, so a test's sessions and runs would show up on /stats as real learning events and
real learner runs."""

import os

import pytest


@pytest.fixture(autouse=True, scope="session")
def _private_tiger_spool(tmp_path_factory):
    old = os.environ.get("TUT_SPOOL_DIR")
    os.environ["TUT_SPOOL_DIR"] = str(tmp_path_factory.mktemp("tiger-spool"))
    from server.checks import tiger

    tiger._writer = None  # the writer reads TUT_SPOOL_DIR when it is made
    yield
    tiger._writer = None
    if old is None:
        os.environ.pop("TUT_SPOOL_DIR", None)
    else:
        os.environ["TUT_SPOOL_DIR"] = old


@pytest.fixture(autouse=True, scope="session")
def _private_engine_tokens(tmp_path_factory):
    """Engine tokens (server/engine_token.py) go to a temp folder: a test never reads the live engine's token from
    ~/.miyagi/engine-tokens, and a companion a test starts (vscode-ext/test/serve-fake.js) inherits this folder."""
    old = os.environ.get("MIYAGI_ENGINE_TOKEN_DIR")
    os.environ["MIYAGI_ENGINE_TOKEN_DIR"] = str(tmp_path_factory.mktemp("engine-tokens"))
    yield
    if old is None:
        os.environ.pop("MIYAGI_ENGINE_TOKEN_DIR", None)
    else:
        os.environ["MIYAGI_ENGINE_TOKEN_DIR"] = old


@pytest.fixture(autouse=True)
def _no_live_web(monkeypatch):
    """The coach grounds fixes in DuckDuckGo + the docs pages (server/coach/web.py). Tests never reach them: a test
    that needs the web fakes web.fetch, one that replays recordings sets COACH_REPLAY_DIR."""
    monkeypatch.setenv("COACH_WEB", "0")

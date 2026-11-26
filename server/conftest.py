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


@pytest.fixture(autouse=True)
def _no_lesson_regex_budget():
    """A LessonSession makes its lesson the regex worker's fallback budget (regex_worker.set_fallback): a later
    test's searches outside any budget() never count against (or are stopped by) an earlier test's session."""
    yield
    from server.safety import regex_worker

    regex_worker.set_fallback(None)


_HERO_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "demo", "pinn-lab")


def _hero_names() -> set[str]:
    try:
        return set(os.listdir(_HERO_DIR))
    except OSError:
        return set()


@pytest.fixture(autouse=True)
def _hero_workdir_untouched(request):
    """demo/pinn-lab is fingerprinted by its file NAMES (server.lesson.builder.workdir_fingerprint): one extra file and
    the hero lesson misses demo/cache/lessons/aebc6b8fba02dac5.json and builds live (a stray empty pinn_convection.py,
    the kind a lesson-mode session's _ensure_step_file makes, was committed once in 36bbf6bf). A test that leaves a new
    file there gets a warning naming it, and an empty leftover is removed so it can't be committed again."""
    before = _hero_names()
    yield
    new = _hero_names() - before
    if not new:
        return
    import warnings

    for name in sorted(new):
        p = os.path.join(_HERO_DIR, name)
        try:
            if os.path.isfile(p) and os.path.getsize(p) == 0:
                os.remove(p)
        except OSError:
            pass
    warnings.warn(f"{request.node.nodeid} left {sorted(new)} in demo/pinn-lab (the hero workdir)", stacklevel=1)

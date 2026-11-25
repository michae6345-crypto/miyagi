"""From recorded frames to error.seen: which rows are read, debounce (on screen 1 s), one id, again, 5 s pacing,
clear, dismiss, muted apps, the 10 minute memory, and the payload's privacy (home as ~, secrets masked)."""

from __future__ import annotations

import pytest

from server.ambient_errors.tests.helpers import empty_frame, frame
from server.ambient_errors.watcher import ErrorWatcher, apps_on_screen, scan
from shared.contracts.events import ENGINE_EVENTS, SeenError

KINDS = {"python_traceback": "python_traceback", "node_stack": "js_error", "tsc_error": "compiler",
         "pip_failure": "shell_exit", "npm_failure": "shell_exit", "git_error": "shell_exit",
         "jupyter_cell": "notebook_cell"}


class Clock:
    def __init__(self) -> None:
        self.t = 100.0

    def __call__(self) -> float:
        return self.t


@pytest.fixture
def clock():
    return Clock()


def watcher(clock):
    return ErrorWatcher(clock=clock, now_iso=lambda: "2026-11-24T10:42:05-08:00")


def feed(w, obs, muted=()):
    return w.frame(scan(obs, muted), apps_on_screen(obs))


@pytest.mark.parametrize("name", sorted(KINDS))
def test_each_recorded_frame_becomes_one_valid_error_seen(name, clock):
    w = watcher(clock)
    assert feed(w, frame(name)) == []  # not yet: on screen for less than 1 s
    clock.t += 1.2
    out = w.tick()
    assert len(out) == 1 and out[0][0] == "error.seen"
    p = out[0][1]
    SeenError.model_validate(p)
    ENGINE_EVENTS["error.seen"].validate_python(p)
    assert p["kind"] == KINDS[name] and p["id"].startswith("err-")
    assert p["rect"]["via"] == "ocr" and p["rect"]["w"] > 100 and p["rect"]["label"] == "The error"
    assert 1 <= len(p["lines"]) <= 8 and len(p["title"]) <= 80
    assert "/Users/" not in " ".join(p["lines"]) + p.get("file", "")  # the home folder reads ~


def test_screen_fixtures_without_errors_stay_quiet(clock):
    w = watcher(clock)
    for name in ("clean_run", "vscode_terminal_flat", "vscode_window_calc_hover", "vscode_fullscreen_top",
                 "vscode_lesson_calculator"):
        assert scan(frame(name)) == [], name
        feed(w, frame(name))
    clock.t += 10
    assert w.tick() == []


def test_vscode_reads_only_its_terminal_panel():
    obs = frame("tsc_error")
    assert [s.found.kind for s in scan(obs)] == ["compiler"]
    # the same window without its panel: the editor is never read as output
    from server.screen.types import Block, Rect

    code = frame("tsc_error")
    code.blocks = [b for b in code.blocks if b.rect.y < 200] + [
        Block("ModuleNotFoundError: No module named 'x'", Rect(80, 150, 300, 15), 1.0, "Code", code.windows[0].title),
        Block("fatal: this is a string in the code", Rect(80, 170, 300, 15), 1.0, "Code", code.windows[0].title)]
    assert scan(code) == []


def test_a_flash_shorter_than_a_second_is_never_news(clock):
    w = watcher(clock)
    feed(w, frame("python_traceback"))
    clock.t += 0.5
    assert feed(w, empty_frame()) == []
    clock.t += 5
    assert w.tick() == [] and w.held == {}


def test_printed_again_keeps_the_id_and_counts_up(clock):
    w = watcher(clock)
    feed(w, frame("python_traceback"))
    clock.t += 1.1
    first = w.tick()[0][1]
    # the learner runs it again: the terminal shows the traceback twice
    twice = frame("python_traceback")
    from server.screen.types import Block, Rect

    twice.blocks = twice.blocks + [Block(b.text, Rect(b.rect.x, b.rect.y + 200, b.rect.w, b.rect.h), b.confidence,
                                         b.app, b.window) for b in twice.blocks if b.rect.y > 140]
    clock.t += 1
    assert feed(w, twice) == []  # still inside the 5 s gap
    clock.t += 5
    again = w.tick()[0][1]
    assert again["id"] == first["id"] and again["again"] == 1
    clock.t += 10
    assert w.tick() == []  # nothing new


def test_one_peek_every_five_seconds(clock):
    w = watcher(clock)
    obs = frame("python_traceback")
    other = frame("git_error")
    obs.blocks += other.blocks
    obs.windows += other.windows
    feed(w, obs)
    clock.t += 1.1
    assert len(w.tick()) == 1
    clock.t += 2
    assert w.tick() == []
    clock.t += 3.1
    assert len(w.tick()) == 1


def test_gone_from_its_app_clears_it_and_another_app_in_front_does_not(clock):
    w = watcher(clock)
    feed(w, frame("node_stack"))
    clock.t += 1.1
    eid = w.tick()[0][1]["id"]
    clock.t += 1
    assert feed(w, empty_frame(app="Safari", title="Docs")) == []  # Terminal hidden: the error may still be there
    clock.t += 10
    assert w.tick() == [] and w.get(eid) is not None
    feed(w, empty_frame(app="Terminal"))  # Terminal on screen, the error is not (cleared, or the next run was fine)
    clock.t += 2
    assert w.tick() == []
    clock.t += 1.1
    assert w.tick() == [("error.seen", {"id": eid, "clear": True})]
    assert w.get(eid) is None


def test_dismiss_forgets_it_and_stays_quiet_until_it_comes_back(clock):
    w = watcher(clock)
    feed(w, frame("pip_failure"))
    clock.t += 1.1
    eid = w.tick()[0][1]["id"]
    w.dismiss(eid)
    assert w.get(eid) is None
    clock.t += 6
    assert feed(w, frame("pip_failure")) == [] and w.tick() == []
    feed(w, empty_frame())  # gone
    feed(w, frame("pip_failure"))  # printed again later: news again
    clock.t += 1.1
    assert w.tick()[0][1]["id"] == eid


def test_held_ten_minutes_at_most(clock):
    w = watcher(clock)
    feed(w, frame("tsc_error"))
    clock.t += 1.1
    eid = w.tick()[0][1]["id"]
    clock.t += 601
    assert w.tick() == [] and w.get(eid) is None
    clock.t += 10
    assert feed(w, frame("tsc_error")) == [] and w.tick() == []  # still the same one on screen: no second peek


def test_muted_and_private_apps_are_never_read(clock):
    assert scan(frame("npm_failure"), muted=["iTerm2"]) == []
    assert scan(frame("npm_failure"), muted=["iterm"]) == []
    assert len(scan(frame("npm_failure"), muted=["1Password"])) == 1
    own = frame("python_traceback")
    own.blocks = [b.__class__(b.text, b.rect, b.confidence, "Miyagi", b.window) for b in own.blocks]
    assert scan(own) == []


def test_accessibility_text_beats_ocr_and_keeps_the_ocr_rect(clock):
    from server.ambient_errors.tests.make_error_fixtures import FIXTURES

    ax = {"app": "Terminal", "terminal_tail": FIXTURES["git_error"].text.splitlines(), "document": None}
    got = scan(frame("git_error", ax=ax))
    assert len(got) == 1
    s = got[0]
    assert s.via == "ax" and s.found.title == "error: failed to push some refs to 'github.com:sam/api.git'"
    assert s.rect is not None  # where OCR saw it


def test_payload_masks_secrets_and_the_home_folder(clock):
    from server.ambient_errors.detect import Row, find_errors
    from server.ambient_errors.watcher import Held, Spotted, seen_payload

    rows = [Row("Traceback (most recent call last):"),
            Row('  File "/Users/sam/code/app.py", line 2, in <module>'),
            Row('    client = OpenAI(api_key="sk-proj-abcdefghijklmnopqrstuvwxyz0123456789")'),
            Row("openai.AuthenticationError: Error code: 401 - key sk-proj-abcdefghijklmnopqrstuvwxyz0123456789")]
    f = find_errors(rows)[0]
    h = Held(id=f.key("Terminal"), spotted=Spotted("Terminal", f), first_t=0, last_t=0, at="2026-11-24T10:42:05-08:00")
    p = seen_payload(h)
    SeenError.model_validate(p)
    text = p["title"] + " ".join(p["lines"]) + p["file"]
    assert "sk-proj" not in text and "••••" in text and p["file"] == "~/code/app.py"

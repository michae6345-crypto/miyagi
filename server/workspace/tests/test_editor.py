"""Editor choice (Cursor > VS Code, MIYAGI_EDITOR), open + frontmost, and the Accessibility arrangement (fakes)."""

from __future__ import annotations

import pytest

from server.workspace import editor as E
from server.workspace import setup as S
from server.workspace.tests.test_setup import FakeMac, reqs_reply
from server.workspace.tests.test_workspace import FakeClient, load

CURSOR = {"id": "cursor", "label": "Cursor", "app": "Cursor", "app_path": "/Applications/Cursor.app", "cli": "/opt/homebrew/bin/cursor"}
VSCODE = {"id": "vscode", "label": "Visual Studio Code", "app": "Visual Studio Code", "app_path": "/Applications/Visual Studio Code.app",
          "cli": "/usr/local/bin/code"}


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("MIYAGI_LESSONS_DIR", str(tmp_path / "lessons"))
    monkeypatch.delenv("MIYAGI_EDITOR", raising=False)
    monkeypatch.delenv("MIYAGI_ARRANGE", raising=False)


@pytest.mark.parametrize("installed,env,want", [
    ([CURSOR, VSCODE], None, "cursor"),          # Cursor preferred when installed
    ([VSCODE], None, "vscode"),
    ([CURSOR, VSCODE], "code", "vscode"),        # MIYAGI_EDITOR overrides
    ([CURSOR, VSCODE], "vscode", "vscode"),
    ([VSCODE], "cursor", "vscode"),              # override not installed -> fall back
    ([], None, None),
])
def test_preferred_editor(monkeypatch, installed, env, want):
    if env:
        monkeypatch.setenv("MIYAGI_EDITOR", env)
    got = E.preferred_editor(installed)
    assert (got or {}).get("id") == want


def test_editor_id_and_label_follow_the_preference(monkeypatch):
    monkeypatch.setattr(E, "installed_editors", lambda: [CURSOR, VSCODE])
    assert E.editor_id() == "cursor" and E.editor_label() == "Cursor"
    assert E.goto_argv("/l/main.py", 7) == ["/opt/homebrew/bin/cursor", "-r", "-g", "/l/main.py:7"]
    monkeypatch.setattr(E, "installed_editors", list)
    monkeypatch.setenv("MIYAGI_EDITOR", "cursor")
    expected = "cursor" if E.ALLOW_CURSOR else "vscode"  # Cursor is banned unless MIYAGI_ALLOW_CURSOR=1
    assert E.editor_id() == expected


def test_cursor_is_banned_by_default():
    if E.ALLOW_CURSOR:
        return
    assert E.PREFERENCE == ["vscode"] and "cursor" not in E.ENV_NAMES


def opener(tmp_path, ok=lambda a: True):
    (tmp_path / "main.py").write_text("")
    calls = []
    return calls, (lambda a: calls.append(a) or ok(a))


def test_open_with_cursor_cli_then_frontmost_without_accessibility(tmp_path):
    calls, run = opener(tmp_path)
    rep = E.open_editor_report(tmp_path, "main.py", runner=run, editor=CURSOR, trusted=lambda: False, previous=None)
    assert calls[0] == ["/opt/homebrew/bin/cursor", str(tmp_path.resolve()), "-g", str((tmp_path / "main.py").resolve())]
    assert calls[1] == ["open", "-a", "Cursor"]
    assert rep["opened"] and rep["frontmost"] and rep["label"] == "Cursor"
    assert rep["arrange"] == "skipped: Accessibility not granted" and "unfullscreened" not in rep


def test_cli_failure_falls_back_to_open_a(tmp_path):
    calls, run = opener(tmp_path, ok=lambda a: a[0] == "open")
    assert E.open_editor(tmp_path, "main.py", runner=run, editor=CURSOR, trusted=lambda: False, previous=None)
    assert calls[1][:3] == ["open", "-a", "Cursor"] and calls[1][-1].endswith("main.py")


def test_no_editor_installed(tmp_path, monkeypatch):
    monkeypatch.setattr(E, "installed_editors", list)
    rep = E.open_editor_report(tmp_path, runner=lambda a: True, previous=None)
    assert rep["opened"] is False and "no supported editor" in rep["error"]


def test_arrange_off_by_env(tmp_path, monkeypatch):
    monkeypatch.setenv("MIYAGI_ARRANGE", "0")
    _, run = opener(tmp_path)
    rep = E.open_editor_report(tmp_path, runner=run, editor=CURSOR, trusted=lambda: True, previous=None)
    assert rep["arrange"].startswith("off")


class FakeAX:
    def __init__(self, fullscreen_prev=True, fullscreen_editor=False):
        self.wins = {"prev": {"fs": fullscreen_prev}, "ed": {"fs": fullscreen_editor}}
        self.log = []

    def focused_window(self, pid):
        return "prev" if pid == 111 else "ed"

    def is_fullscreen(self, w):
        return self.wins[w]["fs"]

    def exit_fullscreen(self, w):
        self.log.append(("exit_fs", w))
        self.wins[w]["fs"] = False
        return True

    def set_frame(self, w, x, y, wd, h):
        self.log.append(("frame", w, x, y, wd, h))
        return True


def test_arrange_unfullscreens_previous_and_docks_editor_left(monkeypatch):
    monkeypatch.setattr(E, "find_pid", lambda name, bundle=None: 222)
    monkeypatch.setattr(E, "left_frame", lambda fraction=0.6: (0, 38, round(1728 * fraction), 1079))
    ax, rep = FakeAX(fullscreen_prev=True, fullscreen_editor=True), {}
    E.arrange(CURSOR, {"pid": 111, "name": "Safari"}, rep, ax=ax, sleep=lambda s: None)
    assert ax.log == [("exit_fs", "prev"), ("exit_fs", "ed"), ("frame", "ed", 0, 38, 1037, 1079 - E.BAR_CLEARANCE)]  # E22: above the bar
    assert rep == {"unfullscreened": "Safari", "arranged": True, "frame": [0, 38, 1037, round(1079 - E.BAR_CLEARANCE)], "arrange": "done"}


def test_arrange_leaves_windowed_apps_alone(monkeypatch):
    monkeypatch.setattr(E, "find_pid", lambda name, bundle=None: 222)
    monkeypatch.setattr(E, "left_frame", lambda fraction=0.6: (0, 0, 600, 800))
    ax, rep = FakeAX(fullscreen_prev=False), {}
    E.arrange(CURSOR, {"pid": 111, "name": "Terminal"}, rep, ax=ax, sleep=lambda s: None)
    assert ("exit_fs", "prev") not in ax.log and "unfullscreened" not in rep and rep["arranged"]


def test_arrange_gives_up_without_an_editor_window(monkeypatch):
    monkeypatch.setattr(E, "find_pid", lambda name, bundle=None: None)
    rep = {}
    E.arrange(CURSOR, None, rep, ax=FakeAX(), wait_s=0.01, sleep=lambda s: None)
    assert rep["arrange"].startswith("skipped: no Cursor window")


def test_open_with_accessibility_runs_arrange(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(E, "arrange", lambda ed, prev, rep, **k: seen.update(ed=ed["id"], prev=prev) or rep.update(arrange="done"))
    _, run = opener(tmp_path)
    rep = E.open_editor_report(tmp_path, runner=run, editor=CURSOR, trusted=lambda: True, previous={"pid": 1, "name": "Keynote"}, wait=True)
    assert seen == {"ed": "cursor", "prev": {"pid": 1, "name": "Keynote"}} and rep["arrange"] == "done" and rep["ax_trusted"]


def test_setup_card_names_cursor(monkeypatch):
    monkeypatch.setattr(E, "editor_id", lambda: "cursor")
    m = FakeMac(apps={"com.todesktop.230313mzl4w4u92": "/Applications/Cursor.app"})
    monkeypatch.setattr(S.shutil, "which", m.which)
    monkeypatch.setattr(S, "find_app", lambda bundle, name, run=None: m.apps.get(bundle))
    items = S.requirements(load("pandas_pokemon.json"), client=FakeClient(reqs_reply()), run=m.run)
    assert items[0]["tool"] == "cursor" and items[0]["label"] == "Cursor" and items[0]["installed"]
    card = S.setup_card(items)
    assert card["setup"]["editorLabel"] == "Cursor" and card["setup"]["actionLabels"]["open_editor"] == "Open Cursor"
    assert "Open the lesson folder in Cursor?" in card["body"] and card["actions"][0] == "open_editor"


def test_cursor_missing_offers_the_cask(monkeypatch):
    monkeypatch.setattr(E, "editor_id", lambda: "cursor")
    m = FakeMac()
    monkeypatch.setattr(S.shutil, "which", m.which)
    monkeypatch.setattr(S, "find_app", lambda bundle, name, run=None: None)
    monkeypatch.setattr(S, "brew_path", lambda: "/opt/homebrew/bin/brew")
    items = S.requirements(load("pandas_pokemon.json"), client=FakeClient(reqs_reply()), run=m.run)
    assert items[0]["install"]["command"] == "brew install --cask cursor"


def test_ax_trusted_is_a_bool():
    assert isinstance(E.ax_trusted(), bool)


# --------------------------------------------------------------------------- "Just teach me": full screen

def test_fullscreen_without_accessibility_says_so(tmp_path):
    calls, run = opener(tmp_path)
    rep = E.open_editor_report(tmp_path, "main.py", runner=run, editor=CURSOR, trusted=lambda: False, previous=None, fullscreen=True)
    assert rep["opened"] and rep["frontmost"] and calls[1] == ["open", "-a", "Cursor"]
    assert rep["fullscreen"].startswith("skipped: Accessibility not granted") and rep["arrange"].startswith("off")


def test_fullscreen_with_accessibility(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(E, "make_fullscreen", lambda ed, rep, **k: seen.update(ed=ed["id"]) or rep.update(fullscreen="done"))
    monkeypatch.setattr(E, "arrange", lambda *a, **k: pytest.fail("no left-60% layout in full-screen mode"))
    _, run = opener(tmp_path)
    rep = E.open_editor_report(tmp_path, runner=run, editor=VSCODE, trusted=lambda: True, previous={"pid": 1, "name": "Safari"},
                               fullscreen=True, wait=True)
    assert seen == {"ed": "vscode"} and rep["fullscreen"] == "done"


def test_make_fullscreen_sets_axfullscreen(monkeypatch):
    class AXF(FakeAX):
        def enter_fullscreen(self, w):
            self.log.append(("enter_fs", w))
            return True
    monkeypatch.setattr(E, "find_pid", lambda name, bundle=None: 222)
    monkeypatch.setattr(E, "NATIVE_FULLSCREEN", True)  # MIYAGI_FULLSCREEN=native (the default maximizes)
    ax, rep = AXF(fullscreen_editor=False), {}
    E.make_fullscreen(CURSOR, rep, ax=ax, sleep=lambda s: None)
    assert ax.log == [("enter_fs", "ed")] and rep["fullscreen"] == "done"
    ax2, rep2 = AXF(fullscreen_editor=True), {}
    E.make_fullscreen(CURSOR, rep2, ax=ax2, sleep=lambda s: None)
    assert ax2.log == [] and rep2["fullscreen"].startswith("done (already")


# --------------------------------------------------------------------------- editor_line_rect

def snap(tmp_path, **kw):
    f = tmp_path / "main.py"
    f.write_text("a\nb\nc\nd\ne\n")
    base = {"document": f"file://{f}", "caret_line": 3, "line_rect": {"x": 300.0, "y": 400.0, "w": 600.0, "h": 18.0},
            "line_height": 18.0, "window": {"x": 0.0, "y": 33.0, "w": 1728.0, "h": 1000.0}}
    base.update(kw)
    return f, (lambda: base)


def test_line_rect_from_caret_anchor(tmp_path):
    f, s = snap(tmp_path)
    assert E.editor_line_rect(f, 3, snapshot=s) == {"x": 300.0, "y": 400.0, "w": 600.0, "h": 18.0, "line": 3, "source": "ax"}
    assert E.editor_line_rect(f, 5, snapshot=s)["y"] == 436.0 and E.editor_line_rect(f, 1, snapshot=s)["y"] == 364.0


def test_line_rect_none_cases(tmp_path, monkeypatch):
    import builtins
    real_import = builtins.__import__
    monkeypatch.setattr(builtins, "__import__", lambda n, *a, **k: (_ for _ in ()).throw(ImportError(n)) if n == "server.screen" else real_import(n, *a, **k))
    f, s = snap(tmp_path)
    assert E.editor_line_rect(tmp_path / "other.py", 3, snapshot=s) is None          # another file in front
    assert E.editor_line_rect(f, 400, snapshot=s) is None                            # scrolled out of the window
    _, off = snap(tmp_path, line_rect=None, line_height=None)
    assert E.editor_line_rect(f, 3, snapshot=off) is None                            # caret off-screen
    assert E.editor_line_rect(f, 3, snapshot=lambda: None) is None                   # no Accessibility / no editor


def test_line_rect_without_accessibility_is_none(tmp_path, monkeypatch):
    monkeypatch.setattr(E, "ax_trusted", lambda: False)
    assert E.editor_line_rect(tmp_path / "main.py", 1, screen_locate=lambda f, ln: None) is None


class Loc:
    def __init__(self, **d):
        self.d = d

    def to_dict(self):
        return self.d


def test_falls_back_to_e6_screen_locate(tmp_path):
    f, _ = snap(tmp_path)
    e6 = lambda file, line: Loc(rect={"x": 10, "y": 200, "w": 900, "h": 18}, reason=None, visible_lines=[1, 40], line_height=18)
    assert E.editor_line_rect(f, 7, snapshot=lambda: None, screen_locate=e6) == {"x": 10, "y": 200, "w": 900, "h": 18, "line": 7, "source": "screen"}
    off = lambda file, line: Loc(rect=None, reason="not_visible", direction="down", visible_lines=[1, 40])
    loc = E.editor_line_location(f, 90, snapshot=lambda: None, screen_locate=off)
    assert loc["rect"] is None and loc["reason"] == "not_visible" and loc["direction"] == "down"
    boom = lambda file, line: (_ for _ in ()).throw(RuntimeError("no screen permission"))
    assert E.editor_line_location(f, 1, snapshot=lambda: None, screen_locate=boom)["reason"] == "unavailable"


def test_ax_wins_over_screen(tmp_path):
    f, s = snap(tmp_path)
    called = []
    assert E.editor_line_rect(f, 3, snapshot=s, screen_locate=lambda *a: called.append(a))["source"] == "ax" and called == []


def test_page_start_for_big_files(tmp_path):
    f = tmp_path / "big.py"
    f.write_text("\n".join(f"line {i}" for i in range(1, 1201)))
    assert E._page_start("line 501\nline 502\nline 503", f) == 501
    assert E._page_start("x", tmp_path / "missing.py") == 1


# --------------------------------------------------------------------------- open once, never steal focus (Michael:
# "it's also opening up multiple VS Codes after a little bit of time"; the launcher collapsing while typing)

MIYAGI = ("dev.sandhacks.miyagi", "Miyagi")
CODE = ("com.microsoft.VSCode", "Code")
VSC = {"id": "vscode", "label": "Visual Studio Code", "app": "Visual Studio Code", "cli": "/usr/local/bin/code",
       "bundle": "com.microsoft.VSCode", "process": "Code"}


@pytest.fixture
def fresh(monkeypatch):
    E.reset_open_state()
    monkeypatch.setattr(E, "preferred_editor", lambda installed=None: VSC)
    monkeypatch.setattr(E, "frontmost_app", lambda skip=None: None)
    # the lesson's window is still up (56cb5ca's reopen check): never this machine's real VS Code windows, which made
    # the explicit "Open VS Code" below a fresh open whenever VS Code had no window on the test's tmp folder
    monkeypatch.setattr(E, "_lesson_window_alive", lambda folder: True)
    yield
    E.reset_open_state()


def kw():
    return {"trusted": lambda: False, "previous": None, "arrange_windows": False, "windows": lambda: []}


def test_open_once_per_lesson_and_folder_never_dash_n(tmp_path, fresh, monkeypatch):
    # the explicit open below passes no window list: never ask the real VS Code (56cb5ca): its window is still there
    monkeypatch.setattr(E, "_lesson_window_alive", lambda folder: True)
    calls, run = opener(tmp_path)
    for _ in range(5):  # lesson-mode open, auto-open after the setup check, resume, retries…
        E.open_lesson_editor(tmp_path, "main.py", lesson_id="L1", runner=run, focus=lambda: CODE, **kw())
    opens = [c for c in calls if c[0] == VSC["cli"]]
    assert len(opens) == 1 and "-n" not in opens[0] and opens[0][1] == str(tmp_path.resolve())
    # the learner presses "Open VS Code": bring that folder's window forward, still no -n, no second arrange
    rep = E.open_lesson_editor(tmp_path, "main.py", lesson_id="L1", runner=run, explicit=True, focus=lambda: MIYAGI)
    assert rep["already"] and calls[-1] == [VSC["cli"], str(tmp_path.resolve()), "-g", str((tmp_path / "main.py").resolve())]
    # a new lesson in the same folder: one more open (VS Code focuses the existing window: still no -n)
    E.open_lesson_editor(tmp_path, None, lesson_id="L2", runner=run, focus=lambda: CODE, **kw())
    assert len([c for c in calls if c[0] == VSC["cli"]]) == 3 and not any("-n" in c for c in calls)


def test_rerun_reopens_the_editor_only_when_its_window_is_gone(tmp_path, fresh, monkeypatch):
    """56cb5ca (Michael, Nov 15 5:11 AM): the same lesson + folder again after VS Code was quit opens it again; while
    its window is up, the at-most-once rule holds (no second `code <folder>`)."""
    calls, run = opener(tmp_path)
    alive = {"v": True}
    monkeypatch.setattr(E, "_lesson_window_alive", lambda folder: alive["v"])
    # no `windows` (the real-call path that checks the window); reuse=False: never this machine's window list
    rep = {"trusted": lambda: False, "previous": None, "arrange_windows": False, "reuse": False}
    E.open_lesson_editor(tmp_path, "main.py", lesson_id="L1", runner=run, focus=lambda: CODE, **rep)
    E.open_lesson_editor(tmp_path, "main.py", lesson_id="L1", runner=run, focus=lambda: CODE, **rep)
    assert len([c for c in calls if c[0] == VSC["cli"]]) == 1
    alive["v"] = False  # VS Code was quit since
    E.open_lesson_editor(tmp_path, "main.py", lesson_id="L1", runner=run, focus=lambda: CODE, **rep)
    opens = [c for c in calls if c[0] == VSC["cli"]]
    assert len(opens) == 2 and not any("-n" in c for c in opens)


def test_concurrent_open_calls_open_once(tmp_path, fresh):
    import threading as th

    calls, run = opener(tmp_path)
    ts = [th.Thread(target=E.open_lesson_editor, args=(tmp_path,), kwargs={"lesson_id": "L", "runner": run,
                    "focus": lambda: CODE, **kw()}) for _ in range(8)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert len([c for c in calls if c[0] == VSC["cli"]]) == 1


def test_arrange_and_fullscreen_run_once(tmp_path, fresh, monkeypatch):
    n = {"arrange": 0, "fs": 0}
    monkeypatch.setattr(E, "arrange", lambda *a, **k: n.__setitem__("arrange", n["arrange"] + 1))
    monkeypatch.setattr(E, "make_fullscreen", lambda *a, **k: n.__setitem__("fs", n["fs"] + 1))
    _, run = opener(tmp_path)
    for _ in range(4):
        E.open_lesson_editor(tmp_path, lesson_id="A", runner=run, focus=lambda: CODE, trusted=lambda: True, previous=None,
                             wait=True, windows=lambda: [])
        E.open_lesson_editor(tmp_path, lesson_id="F", runner=run, focus=lambda: CODE, trusted=lambda: True, fullscreen=True,
                             wait=True, windows=lambda: [])
    assert n == {"arrange": 1, "fs": 1}


def test_auto_open_waits_while_miyagi_has_focus(tmp_path, fresh):
    calls, run = opener(tmp_path)
    front = {"app": MIYAGI}
    rep = E.open_lesson_editor(tmp_path, lesson_id="L", runner=run, focus=lambda: front["app"], background=False,
                               wait_s=0.05, sleep=lambda s: None, **kw())
    assert rep == {"opened": False, "deferred": True, "gave_up": True} and calls == []
    assert E.open_state(tmp_path, "L") is None  # gave up: a later call may open it
    # typing in another app also defers; once Miyagi lets go, it opens (once)
    seq = iter([MIYAGI, MIYAGI, CODE, CODE, CODE])
    rep = E.open_lesson_editor(tmp_path, lesson_id="L", runner=run, focus=lambda: next(seq), background=False,
                               sleep=lambda s: None, **kw())
    assert rep["opened"] and len([c for c in calls if c[0] == VSC["cli"]]) == 1


def test_auto_open_in_background_does_not_block(tmp_path, fresh):
    import time as _t

    calls, run = opener(tmp_path)
    front = {"app": MIYAGI}
    rep = E.open_lesson_editor(tmp_path, lesson_id="L", runner=run, focus=lambda: front["app"], **kw())
    assert rep == {"opened": False, "deferred": True} and E.open_state(tmp_path, "L")["state"] == "waiting"
    assert E.open_lesson_editor(tmp_path, lesson_id="L", runner=run, focus=lambda: CODE, **kw())["already"]  # no 2nd waiter
    front["app"] = ("com.apple.Terminal", "Terminal")
    for _ in range(40):
        if E.open_state(tmp_path, "L")["state"] == "open":
            break
        _t.sleep(0.05)
    assert E.open_state(tmp_path, "L")["state"] == "open" and len([c for c in calls if c[0] == VSC["cli"]]) == 1


def test_explicit_open_ignores_focus(tmp_path, fresh):
    calls, run = opener(tmp_path)
    rep = E.open_lesson_editor(tmp_path, lesson_id="L", runner=run, explicit=True, focus=lambda: MIYAGI, **kw())
    assert rep["opened"] and calls


def test_auto_jumps_never_steal_focus_or_race_startup(tmp_path, fresh):
    f = tmp_path / "main.py"
    f.write_text("x\n")
    calls = []
    run = lambda a: calls.append(a) or True  # noqa: E731
    up = lambda ed: True  # noqa: E731
    assert not E.jump(f, 3, runner=run, focus=lambda: MIYAGI, window_up=up)                       # learner in Miyagi
    assert not E.jump(f, 3, runner=run, focus=lambda: ("com.apple.Safari", "Safari"), window_up=up)  # elsewhere
    assert not E.jump(f, 3, runner=run, focus=lambda: CODE, window_up=lambda ed: False)           # no window yet
    E._opened[("L", str(tmp_path))] = {"state": "opening", "t": 0}
    assert not E.jump(f, 3, runner=run, focus=lambda: CODE, window_up=up)                         # still opening
    E._opened[("L", str(tmp_path))]["state"] = "open"
    assert E.jump(f, 3, runner=run, focus=lambda: CODE, window_up=up)                             # in VS Code already
    assert E.jump(f, 4, runner=run, focus=lambda: MIYAGI, window_up=lambda ed: False, explicit=True)  # Do it for me
    assert calls == [["/usr/local/bin/code", "-r", "-g", f"{f}:3"], ["/usr/local/bin/code", "-r", "-g", f"{f}:4"]]


def test_miyagi_focus_detection():
    assert E.miyagi_focused(MIYAGI) and E.miyagi_focused(("com.github.Electron", "Electron"))
    assert not E.miyagi_focused(CODE) and not E.miyagi_focused(None)
    assert E.editor_focused(VSC, CODE) and not E.editor_focused(VSC, MIYAGI)


def test_orchestrator_workspace_opens_once_and_guards_jumps(tmp_path, fresh):
    """The orchestrator's lesson flow: lesson-mode open + auto-open + resume + 8 spotlight retries -> one open."""
    from server.orchestrator.workspace import Workspace

    calls = []
    w = Workspace(enabled=True, runner=lambda a: calls.append(a) or True)
    w.lesson_key = "lesson-1"
    (tmp_path / "main.py").write_text("x\n")
    w.open(str(tmp_path), True, True)          # _open_editor_full
    w.open(str(tmp_path), True)                # _auto_open_editor
    w.open(str(tmp_path), True, True)          # resume / replaced provisional lesson
    opens = [c for c in calls if str(tmp_path.resolve()) in c and "-r" not in c]
    assert len(opens) == 1 and "-n" not in opens[0]
    w.open(str(tmp_path), force=True, explicit=True)  # the learner's button: brought forward
    assert len([c for c in calls if str(tmp_path.resolve()) in c and "-r" not in c]) == 2
    for _ in range(8):
        w.goto(str(tmp_path / "main.py"), 1)   # test runner: VS Code counts as frontmost, window up
    assert all(c[1:3] == ["-r", "-g"] for c in calls if "-g" in c and c[1] == "-r")

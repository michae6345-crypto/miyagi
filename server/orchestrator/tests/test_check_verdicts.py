"""Check results tell the truth (live test 3, E1 / E18 / E19): a step with broken or incomplete code never passes,
rows and status aren't re-sent without a real change, Check shows "thinking" until its card, and "Not yet" bodies
are whole sentences with the step's exact command. Run: python -m pytest server/orchestrator/tests/test_check_verdicts.py"""

from __future__ import annotations

import asyncio

from server.orchestrator.modules import Modules
from server.orchestrator.screen_bridge import FakeScreen
from server.orchestrator.tests.test_session import Rig, run


def _core(p):
    """step.passed without the ui-v4 skill tree fields (key, assisted, skillIds, proofId: test_skill_hooks covers them)."""
    if isinstance(p, list):
        return [_core(x) for x in p]
    return {k: v for k, v in p.items() if k not in ("key", "assisted", "skillIds", "proofId")}

DICE = 'import random\n\nroll = random.randint(1, 6)\nprint("You rolled:", roll)\n'
DICE_BROKEN = 'import random\n\n\n\nroll = random.randint(1, 6)\nprint("You rolled:" roll)\n'  # frame 012000
WEATHER = ('import requests\n\n\ndef get_weather(city):\n'
           '    response = requests.get(f"https://wttr.in/{city}", params={"format": "j1"}, timeout=10)\n'
           '    response.raise_for_status()\n    return response.json()\n')
WEATHER_LOOSE = ('import requests\n\n\ndef get_weather(city):\n    # ask wttr.in\n'  # frames 010902 / 011225
                 '    response = requests.get(f"https://wttr.in/{city}", timeout=10)\n    return response\n')


def _code(cid: str, pattern: str, label: str) -> dict:
    return {"id": cid, "type": "screen_contains", "app": "Code", "pattern": pattern, "label": label}


def _lesson() -> dict:
    """The live test's two lessons as one: dice step 1 (print comma), weather step 2 (params / raise_for_status),
    a python3 run step. Checks as loose as the builder's (s1c3 print\\(\\s*"You rolled:", s2c2 requests\\.get\\s*\\()."""
    return {"lesson": {"id": "lesson-t3", "title": "Dice and weather", "goal": "dice and weather", "mode": "lesson",
                       "complete": True, "builtBy": "claude"},
            "sources": [],
            "steps": [
                {"id": "s1", "index": 1, "title": "Roll a die", "instructions": "Print a random roll.",
                 "file": "main.py", "code": DICE, "targets": [{"app": "Code", "file": "main.py", "match": "import"}],
                 "checks": [_code("s1c1", r"import random", "Imports random"),
                            _code("s1c2", r"random\.randint", "Rolls a number"),
                            _code("s1c3", r'print\(\s*"You rolled:"', "Prints the roll")],
                 "precision_checks": [{"id": "s1p2", "type": "file_contains", "label": "prints roll",
                                       "file": "main.py", "pattern": r"print\(.*roll"}]},
                {"id": "s2", "index": 2, "title": "Fetch the weather", "instructions": "Write get_weather(city).",
                 "file": "weather.py", "code": WEATHER,
                 "targets": [{"app": "Code", "file": "weather.py", "match": "import"}],
                 "checks": [_code("s2c1", r"def get_weather\(", "Function defined"),
                            _code("s2c2", r"requests\.get\s*\(", "Requests.get call written"),
                            _code("s2c3", r"return response", "Returns the response")]},
                {"id": "s3", "index": 3, "title": "Run it", "instructions": "Run the dice in the terminal.",
                 "file": "main.py", "code": "python3 main.py\n",
                 "targets": [{"app": "Code", "file": "main.py", "match": "main\\.py"}], "checks": []}]}


def _rig(tmp_path, monkeypatch, judge=None) -> tuple[Rig, FakeScreen]:
    """A lesson-mode session on the REAL checks (server.checks), the rest stubbed; no model is ever called."""
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    monkeypatch.setenv("TUT_SPOOL_DIR", str(tmp_path / "spool"))  # the real checks' learning-event spool: not ~/
    monkeypatch.delenv("DEMO", raising=False)
    from server.orchestrator.workspace import Workspace

    screen = FakeScreen()
    rig = Rig(tmp_path, modules=Modules(demo=False, force_stubs="lesson,coach,finder,diagrams"), screen=screen)
    rig.s.workspace = Workspace(enabled=False, runner=lambda argv: True)
    rig.s.check_wait_s = 0

    async def build(goal, workdir, on_update=None, **kw):
        return _lesson()

    rig.s.m.build_text_lesson = build

    async def no_judge(step, screen=None, files=None, **kw):
        return None

    rig.s.m.judge_step = judge or no_judge
    return rig, screen


async def _save(rig: Rig, screen: FakeScreen, name: str, text: str) -> None:
    """The learner saves `name`; VS Code shows it (OCR reads every line, as in the live frames)."""
    (rig.workdir / name).write_text(text, encoding="utf-8")
    screen.text["Code"] = [name] + text.splitlines()
    await rig.s.on_file_change([str(rig.workdir / name)])
    await rig.settle()


def _rows(rig: Rig, cid: str) -> list[dict]:
    return [p for p in rig.of("check.updated") if p["checkId"] == cid]


def test_a_syntax_error_never_passes_the_step_and_names_its_line(tmp_path, monkeypatch):
    """Dice step 1 (01:19:59): every pattern matched print("You rolled:" roll), VS Code said 1 error, and the step
    passed 'confirmed by your files'. Now the file must compile: a fail row with the line, then green once fixed."""
    rig, screen = _rig(tmp_path, monkeypatch)
    spoke = []  # the coach is asked to explain it at once (here: recorded, not run, so Check's card shows)
    rig.s._consider_speaking = lambda reason, step, failed, ctx: spoke.append((reason, [r["checkId"] for r in failed]))

    async def go():
        await rig.s.learn("dice", mode="lesson")
        await rig.settle()
        await _save(rig, screen, "main.py", DICE_BROKEN)
        assert not rig.of("step.passed")
        row = _rows(rig, "s1-syntax")[-1]
        assert row["status"] == "fail" and row["label"] == "main.py has no syntax errors"
        assert row["detail"] == "line 6: invalid syntax. Perhaps you forgot a comma?"
        assert spoke == [("breakpoint", ["s1-syntax"])]
        await rig.s.action("check_step")  # still not done; the card says why, the error on its own line
        await rig.settle()
        assert not rig.of("step.passed")
        card = [c for c in rig.of("card") if c["title"] == "Not yet"][-1]
        assert card["body"].split("\n")[-1] == "main.py line 6: invalid syntax. Perhaps you forgot a comma?"
        await _save(rig, screen, "main.py", DICE)

    run(go())
    assert rig.of("step.passed")[0]["stepId"] == "s1"
    assert [r["status"] for r in _rows(rig, "s1-syntax")] == ["fail", "pass"]


def test_requests_get_without_params_or_raise_for_status_does_not_pass(tmp_path, monkeypatch):
    """Weather step 2: 'Requests.get call written' showed Passed with no params={"format": "j1"} and no
    raise_for_status() (010902 .. 011635), so the later .json() step crashed on wttr.in's plain text."""
    judged = []

    async def judge(step, screen=None, files=None, **kw):  # Claude "sees" it done: it must not pass it either
        judged.append(step["id"])
        return {"done": True, "missing": "", "checks": {c["id"]: {"verdict": "done"} for c in step["checks"]}}

    rig, screen = _rig(tmp_path, monkeypatch, judge)

    async def go():
        await rig.s.learn("weather", mode="lesson")
        await rig.settle()
        await rig.s.goto_step(1)
        await rig.settle()
        await _save(rig, screen, "weather.py", WEATHER_LOOSE)
        assert not rig.of("step.passed")
        last = {r["checkId"]: r for r in rig.s.last_results}
        assert last["s2c1"]["status"] == "pass"
        assert last["s2c2"]["status"] == "fail"
        assert last["s2c2"]["detail"] == 'line 6 still needs params={"format": "j1"}'
        assert last["s2c3"]["status"] == "fail"  # "return response" matched; the step returns response.json()
        assert last["s2c3"]["detail"] == "line 7 still needs response.json()"
        assert last["s2-code"]["detail"] == "still needs response.raise_for_status()"  # no row claims that line
        assert _rows(rig, "s2c2")[-1]["status"] == "fail"  # the drawer says it, not just the engine
        assert not all(r["status"] == "pass" for r in rig.s.last_results)
        for _ in range(2):
            await rig.s.action("check_step")
            await rig.settle()
            rig.clock.t += 3  # a real second try, not a double press
        assert not rig.of("step.passed") and judged == ["s2", "s2"]
        first, again = [c for c in rig.of("card") if c["title"] == "Not yet"][-2:]
        assert first["actions"] == ["hint", "show_me", "explain", "skip_step"]  # teach first
        assert again["actions"] == ["apply_fix", "hint", "show_me", "explain", "skip_step"]  # Do it for me after a repeat
        assert 'params={"format": "j1"}' in first["body"] and "…" not in first["body"]
        assert first["body"].endswith(".")
        await _save(rig, screen, "weather.py", WEATHER)

    run(go())
    assert _core(rig.of("step.passed")[-1]) == {"stepId": "s2", "nextStepId": "s3"}


def test_the_judges_done_never_passes_rows_the_code_gate_fails(tmp_path, monkeypatch):
    """Review of E1: rows that fail on their own (tight) patterns aren't code-gate rows on Check's first pass, so
    the judge's "done" reached them; the gate failed them again, the drawer showed them red, and the step still
    passed. Now that is a "Not yet" saying what's missing."""
    async def judge(step, screen=None, files=None, **kw):
        return {"done": True, "missing": "", "checks": {c["id"]: {"verdict": "done"} for c in step["checks"]}}

    rig, screen = _rig(tmp_path, monkeypatch, judge)
    lesson = _lesson()
    lesson["steps"][1]["checks"][1:] = [_code("s2c2", r'params=\{"format":\s*"j1"\}', "Asks wttr.in for JSON"),
                                        _code("s2c3", r"raise_for_status\(\)", "Stops on a bad status")]

    async def build(goal, workdir, on_update=None, **kw):
        return lesson

    rig.s.m.build_text_lesson = build
    bare = WEATHER.replace(', params={"format": "j1"}', "").replace("    response.raise_for_status()\n", "")

    async def go():
        await rig.s.learn("weather", mode="lesson")
        await rig.settle()
        await rig.s.goto_step(1)
        await rig.settle()
        await _save(rig, screen, "weather.py", bare)
        await rig.s.action("check_step")
        await rig.settle()

    run(go())
    assert not rig.of("step.passed")
    last = {r["checkId"]: r for r in rig.s.last_results}
    assert last["s2c2"]["status"] == last["s2c3"]["status"] == "fail"
    assert _rows(rig, "s2c2")[-1]["status"] == "fail"
    card = [c for c in rig.of("card") if c["title"] == "Not yet"][-1]
    assert 'params={"format": "j1"}' in card["body"] and "raise_for_status()" in card["body"]


def test_not_yet_body_is_whole_sentences_with_the_steps_python3(tmp_path, monkeypatch):
    """01:21:48: the run step's card said "run python main.py" (only python3 on this Mac); 012054: the body was
    cut to 12 words with an ellipsis."""
    from server.coach.judge import card_text
    from server.orchestrator import code_gate

    long = ("Wrap roll in def roll_die(), add a call, fix the print comma, then run python main.py again and read "
            "what it prints in the terminal before you go on to the next step of the lesson")
    assert card_text(long, {"code": "python3 main.py\n"}) == "Wrap roll in def roll_die(), add a call, fix the print comma"
    assert card_text("Then run python main.py again.", {"code": "python3 main.py\n"}) == "Then run python3 main.py again"
    assert code_gate.not_yet_body("Run python main.py in the terminal", [], sid="s3", cmd="python3 main.py") == \
        "Run python3 main.py in the terminal."
    labelled = [{"checkId": "s2c4", "label": "Prints the forecast", "status": "fail", "detail": "not found"}]
    assert code_gate.not_yet_body('Call get_weather("Paris") and print it', labelled, sid="s2") == \
        'Call get_weather("Paris") and print it.'  # a label is a finished fact: the judge's sentence says it better
    assert code_gate.not_yet_body("", labelled, sid="s2") == "Still to do: Prints the forecast."

    async def judge(step, screen=None, files=None, **kw):
        return {"done": False, "missing": "Run python main.py in the terminal", "checks": {}}

    rig, screen = _rig(tmp_path, monkeypatch, judge)
    rig.s.has_python = False  # this Mac: Homebrew's python3 only

    async def go():
        await rig.s.learn("dice", mode="lesson")
        await rig.settle()
        (rig.workdir / "main.py").write_text(DICE, encoding="utf-8")
        await rig.s.goto_step(2)
        await rig.settle()
        await rig.s.action("check_step")
        await rig.settle()

    run(go())
    card = [c for c in rig.of("card") if c["title"] == "Not yet"][-1]
    assert "python3 main.py" in card["body"] and "python main.py" not in card["body"]
    assert "…" not in card["body"] and card["body"].endswith(".")


def test_replayed_rows_and_status_are_sent_once_per_real_change(tmp_path, monkeypatch):
    """01:12:23-:29: s2c1 re-sent 20 times flipping 'found in weather.py' / 'seen in VS Code' (011225 vs 011230);
    'watching' sent 16 times between 01:21:54 and 01:22:16."""
    rig, screen = _rig(tmp_path, monkeypatch)

    async def go():
        await rig.s.learn("weather", mode="lesson")
        await rig.settle()
        await rig.s.goto_step(1)
        await rig.settle()
        step, m = rig.s.step, rig.mark()
        for detail in ["seen in VS Code", "found in weather.py", "seen in VS Code", "found in weather.py",
                       "seen in VS Code", "found in weather.py"]:
            await rig.s._publish(step, [{"checkId": "s2c1", "label": "Function defined", "status": "pass",
                                         "detail": detail}])
        sent = [e["payload"] for e in rig.since(m) if e["type"] == "check.updated"]
        assert [p["detail"] for p in sent] == ["seen in VS Code", "found in weather.py"]  # pass, then the file's word
        m = rig.mark()
        for state in ["watching"] * 16 + ["thinking", "thinking", "watching"]:
            await rig.s._status(state)
        return [e["payload"]["state"] for e in rig.since(m) if e["type"] == "status"]

    assert run(go()) == ["thinking", "watching"]  # "watching" was already up


def test_check_keeps_thinking_until_its_card_arrives(tmp_path, monkeypatch):
    """01:20:45,725: Check -> thinking, 'diagnosis cancelled: the learner acted' -> watching 1 ms later, the Not
    yet card only at 01:20:50,207 with nothing showing a check was running."""
    async def judge(step, screen=None, files=None, **kw):
        await rig.s._status("watching")  # the cancelled diagnosis' reset, while the judge still runs
        await asyncio.sleep(0.01)
        return {"done": False, "missing": "Add the roll_die function from the drawer", "checks": {}}

    rig, screen = _rig(tmp_path, monkeypatch, judge)

    async def go():
        await rig.s.learn("dice", mode="lesson")
        await rig.settle()
        m = rig.mark()
        await rig.s.action("check_step")
        await rig.settle()
        return [(e["type"], e["payload"].get("state") or e["payload"].get("title")) for e in rig.since(m)
                if e["type"] in ("status", "card")]

    seq = run(go())
    card = seq.index(("card", "Not yet"))
    assert seq[0] == ("status", "thinking") and ("status", "watching") not in seq[:card]
    assert seq[card + 1:] == [("status", "watching")]


def test_a_readable_lesson_file_never_asks_to_open_vs_code(tmp_path):
    """s2c3 said 'Open VS Code so I can check it.' while the rows above it said 'found in weather.py' (011558)."""
    from server.checks.evaluator import screen_check_on_file

    c = _code("s2c3", r"raise_for_status\(\)", "Raises for status")
    (tmp_path / "weather.py").write_text(WEATHER_LOOSE, encoding="utf-8")
    r = screen_check_on_file(c, tmp_path / "weather.py", window_open=False)
    assert r["status"] == "fail" and r["detail"] == "not in weather.py yet"
    r = screen_check_on_file(c, tmp_path / "missing.py", window_open=False)
    assert r["detail"] == "Open VS Code so I can check it."

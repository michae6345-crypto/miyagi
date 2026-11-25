"""Explain: what leaves the Mac (redacted text, cut paths, <= 6 context lines, never a screenshot), the local answer
(no model), the model's answer (a mocked client: these tests never call a model), and the hourly cap."""

from __future__ import annotations

import asyncio
import json

import pytest

from server import ambient_cap
from server.ambient_errors import explain as ex
from server.ambient_errors.detect import Row, find_errors
from server.ambient_errors.tests.helpers import frame, text_rows
from server.ambient_errors.watcher import Held, Spotted, scan
from shared.contracts.events import AMBIENT_CONTEXT_LINES_MAX, ErrorExplanation


def held_from(found, app="Terminal", rect=None, doc=None) -> Held:
    s = Spotted(app, found, rect, "ocr", doc)
    return Held(id=s.id, spotted=s, first_t=0, last_t=0, at="2026-11-24T10:42:05-08:00", shown=True)


def held_of(name: str) -> Held:
    s = scan(frame(name))[0]
    return Held(id=s.id, spotted=s, first_t=0, last_t=0, at="2026-11-24T10:42:05-08:00", shown=True)


class FakeLLM:
    """Stands in for server.coach.llm.structured_call: records the request, answers `data` (or raises)."""

    def __init__(self, data=None, exc=None):
        self.data, self.exc, self.calls = data, exc, []

    async def __call__(self, **kw):
        from server.coach.llm import CallResult

        self.calls.append(kw)
        if self.exc is not None:
            raise self.exc
        return CallResult(data=self.data, model="claude-haiku-5-5")


@pytest.fixture
def fake_llm(monkeypatch):
    from server.coach import llm

    fake = FakeLLM({"title": "config has no port yet!", "why": "server.js reads config.port on line 12, but config "
                    "is undefined there because nothing assigned it before that line.",
                    "fix": "Load the config before reading config.port.", "diff": "", "command": ""})
    monkeypatch.setattr(llm, "structured_call", fake)
    return fake


def test_context_cuts_paths_masks_secrets_and_reads_six_source_lines(tmp_path):
    src = tmp_path / "proj" / "app.py"
    src.parent.mkdir()
    body = [f"x{i} = {i}" for i in range(1, 21)]
    body[9] = 'API_KEY = "sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456789abcd"'
    src.write_text("\n".join(body) + "\n")
    rows = [Row("Traceback (most recent call last):"),
            Row(f'  File "{src}", line 11, in <module>'),
            Row("    x11 = boom()"),
            Row("NameError: name 'boom' is not defined")]
    ctx = ex.context(held_from(find_errors(rows)[0]))
    assert ctx["file"] == "app.py" and ctx["line"] == 11
    assert len(ctx["context"]) == AMBIENT_CONTEXT_LINES_MAX and ctx["context_is"] == "source"
    assert any(c.startswith("  11| ") for c in ctx["context"])
    blob = json.dumps(ctx, ensure_ascii=False)
    assert "sk-ant" not in blob and "••••" in blob
    assert str(tmp_path) not in blob and "/Users/" not in blob


def test_a_secret_file_is_never_read(tmp_path):
    env = tmp_path / ".env"
    env.write_text("A=1\nB=2\nC=3\n")
    f = find_errors([Row("Traceback (most recent call last):"), Row(f'  File "{env}", line 2, in <module>'),
                     Row("SyntaxError: invalid syntax")])[0]
    assert ex.context(held_from(f))["context"] == []


def test_relative_file_only_through_the_open_editor(tmp_path):
    f = find_errors(text_rows("tsc_error"))[0]
    src = tmp_path / "web" / "src" / "index.ts"
    src.parent.mkdir(parents=True)
    src.write_text("\n".join(f"// {i}" for i in range(1, 14)) + '\nconst total: number = "42";\n')
    assert ex.context(held_from(f))["context_is"] == "command"  # no editor: the command before it instead
    ctx = ex.context(held_from(f, doc=str(src)))
    assert ctx["context_is"] == "source" and ctx["context"][-1].endswith('const total: number = "42";')


def test_command_context_for_a_failed_command():
    ctx = ex.context(held_of("pip_failure"))
    assert ctx["context"] in (["$ pip install"], ["$ pip install tensorflow==2.3"]) and ctx["context_is"] == "command"
    text = ex.user_text(ex.context(held_from(find_errors(text_rows("git_error"))[0])))
    assert "<untrusted" in text and "$ git push" in text and "KIND: a command that failed" in text


def test_local_answer_for_a_missing_curated_package_needs_no_model(fake_llm):
    h = held_of("python_traceback")
    out = ex.local_answer(h)
    assert out is not None
    ErrorExplanation.model_validate(out)
    assert out["title"] == "pandas isn't installed here" and out["command"] == "pip install pandas"
    assert out["install"]["tool"] == "pandas" and out["install"]["install"]["method"] == "pip"
    assert out["file"] == "~/code/weather-app/app.py" and out["line"] == 3 and out["target"]["via"] == "ocr"
    assert len(out["title"].split()) <= 8 and len(out["why"].split()) <= 40 and len(out["fix"].split()) <= 25
    assert fake_llm.calls == []
    # a typosquat or an unknown package gets no Install row and no local answer
    typo = find_errors([Row("Traceback (most recent call last):"), Row('  File "/x/a.py", line 1, in <module>'),
                        Row("ModuleNotFoundError: No module named 'reqeusts'")])[0]
    assert ex.local_answer(held_from(typo)) is None and ex.install_item(held_from(typo)) is None


def test_model_answer_is_haiku_redacted_and_clamped(fake_llm):
    h = held_of("node_stack")
    out = asyncio.run(ex.explain(h))
    ErrorExplanation.model_validate(out)
    assert out["title"] == "config has no port yet" and "!" not in out["title"]
    assert out["id"] == h.id and out["line"] == 12 and "diff" not in out and "command" not in out
    (call,) = fake_llm.calls
    assert call["model"] == "claude-haiku-5-5" and call["purpose"] == "explain_error"
    assert call["thinking"] == {"type": "disabled"} and "user_content" not in call  # text only, never an image
    assert "/Users/sam" not in call["user_text"] and "server.js" in call["user_text"]


def test_model_command_and_diff_are_filtered(fake_llm, tmp_path):
    h = held_from(find_errors(text_rows("python_traceback"))[0])
    fake_llm.data = {"title": "pandas missing", "why": "w", "fix": "f", "command": "pip install pandas && rm -rf ~",
                     "diff": "--- a/app.py\n+++ b/app.py\n@@ -3 +3 @@\n-import pandas as pd\n+import csv\n"}
    out = asyncio.run(ex.explain(h))
    assert "command" not in out and out["diff"].startswith("--- a/app.py")
    fake_llm.data = {**fake_llm.data, "command": "pip install requests", "diff": "rm -rf /"}
    out = asyncio.run(ex.explain(h))
    assert "command" not in out and "diff" not in out  # a package the error never named; not a diff
    fake_llm.data = {**fake_llm.data, "command": "pip install pandas"}
    assert asyncio.run(ex.explain(h))["command"] == "pip install pandas"


def test_failures_map_to_calm_errors(monkeypatch):
    from server.coach import llm

    h = held_of("git_error")
    for exc, want in ((llm.CoachLLMError("x: connection error", "connection"), "offline"),
                      (llm.CoachLLMError("no ANTHROPIC_API_KEY", "no_key"), "offline"),
                      (llm.CoachLLMError("x: API 529: overloaded", "api"), "busy"),
                      (llm.CoachLLMError("x: stop_reason=refusal", "refusal"), "failed"),
                      (RuntimeError("boom"), "failed")):
        monkeypatch.setattr(llm, "structured_call", FakeLLM(exc=exc))
        monkeypatch.setattr(ex, "RETRY_DELAYS_S", ())
        out = asyncio.run(ex.explain(h))
        assert out == {"id": h.id, "error": want}
        ErrorExplanation.model_validate(out)


def test_hourly_cap_rolls_and_persists(tmp_path):
    t = [1000.0]
    path = tmp_path / "ambient_calls.json"
    cap = ambient_cap.HourlyCap(limit=3, path=path, clock=lambda: t[0])
    assert [cap.take() for _ in range(3)] == [None, None, None]
    wait = cap.take()
    assert wait == 3600
    again = ambient_cap.HourlyCap(limit=3, path=path, clock=lambda: t[0])  # an engine restart keeps the hour
    t[0] += 1800
    assert again.take() == 1800
    again.refund()
    assert again.used() == 2 and json.loads(path.read_text())["calls"]
    t[0] += 1801
    assert again.take() is None
    assert "error" not in path.read_text() and oct(path.stat().st_mode)[-3:] == "600"

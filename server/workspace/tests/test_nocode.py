"""The no-code lesson from Michael's live run: "Build AI Customer Support Agents Across Three Platforms"
(OpenAI Agent Builder / Botpress / Zapier, video zE2MJ3_muNQ), searched for as "build chat gpt".
Fixture = the engine's cached step graph (demo/cache/lessons/6bec8b3a171601ed.json)."""

from __future__ import annotations

import json

import pytest

from server.workspace import (
    editor_needed,
    missing,
    prepare,
    read_state,
    requirements,
    setup_card,
)
from server.workspace import setup as S
from server.workspace.core import goal_match_note
from server.workspace.tests.test_setup import FakeMac, reqs_reply, tool
from server.workspace.tests.test_workspace import FakeClient, load, reply

ASKED = "build chat gpt"


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("MIYAGI_LESSONS_DIR", str(tmp_path / "lessons"))
    for k in ("ORCH_HERO_WORKDIR", "ORCH_HERO_LESSON_IDS", "ORCH_LESSON_URL"):
        monkeypatch.delenv(k, raising=False)


@pytest.fixture
def mac(monkeypatch):
    m = FakeMac(apps={"com.microsoft.VSCode": "/Applications/Visual Studio Code.app"})
    monkeypatch.setattr(S.shutil, "which", m.which)
    monkeypatch.setattr(S, "find_app", lambda bundle, name, run=None: m.apps.get(bundle))
    monkeypatch.setattr(S, "brew_path", lambda: "/opt/homebrew/bin/brew")
    return m


def graph():
    g = load("nocode_support_agents.json")
    assert g["lesson"]["goal"] == ASKED and g["sources"][0]["videoId"] == "zE2MJ3_muNQ"
    return g


def test_scaffold_prompt_is_the_video_not_the_goal():
    fc = FakeClient(reply(kind="no_code", stack="OpenAI Agent Builder, Botpress, Zapier"))
    prepare(graph(), ASKED, client=fc)
    prompt = fc.calls[0]["messages"][0]["content"]
    assert ASKED not in prompt and "Create OpenAI FAQ Support Agent" in prompt and "lesson_kind" in prompt


def test_no_code_lesson_never_gets_code_files(tmp_path):
    # even if Claude hands back files and a git history, a no-code lesson gets none of them
    git = {"init": True, "default_branch": "main", "ops": [{"op": "commit", "name": "", "message": "x", "files": [{"path": "bot.py", "content": "# bot\n"}]}]}
    fc = FakeClient(reply([("agent.py", "# agent\n"), ("prompt.md", "FAQ\n")], kind="no_code", stack="Botpress, Zapier",
                          setup=["npm i -g botpress"], open_file="agent.py", git=git))
    wd = prepare(graph(), ASKED, client=fc)
    assert sorted(p.name for p in wd.iterdir()) == ["README.md"]
    st = read_state(wd)
    assert st["lesson_kind"] == "no_code" and st["files"] == [] and st["setup"] == [] and st["open_file"] == ""
    assert any("no-code lesson gets no starter files" in d for d in st["dropped"])


def test_conceptual_lesson_never_gets_files():
    fc = FakeClient(reply([("notes.py", "# x\n")], kind="conceptual"))
    wd = prepare(graph(), ASKED, client=fc)
    assert sorted(p.name for p in wd.iterdir()) == ["README.md"]
    assert "explains ideas" in (wd / "README.md").read_text()


def test_readme_leads_with_the_video_topic():
    wd = prepare(graph(), ASKED, client=FakeClient(reply(kind="no_code", stack="OpenAI Agent Builder, Botpress, Zapier")))
    readme = (wd / "README.md").read_text()
    assert readme.startswith("# Build AI Customer Support Agents Across Three Platforms\n")
    assert "Goal:" not in readme and "<sub>You asked for: build chat gpt</sub>" in readme
    assert "https://www.youtube.com/watch?v=zE2MJ3_muNQ" in readme and "1. Create OpenAI FAQ Support Agent (1:10)" in readme
    assert "step 1 creates the project" not in readme and "every step is yours to write" not in readme
    # "Agent Builder" would satisfy step 1's screen check if the README were on screen, so the apps aren't named
    assert "Nothing to set up here: this lesson happens in the apps the video uses, not in code files." in readme
    assert "Heads-up" not in readme  # no goalMatch yet


@pytest.mark.parametrize("gm,shown", [
    (0.2, "(match 20%)"), (35, "(match 35%)"), ({"score": 0.3, "note": "It builds support bots, not a ChatGPT clone."}, "not a ChatGPT clone"),
    ({"level": "low"}, "only partly matches"), ("partial", "only partly matches"),
    (0.9, None), ({"score": 0.8, "level": "high"}, None), (None, None), (True, None),
])
def test_goal_match_note(gm, shown):
    note = goal_match_note(gm)
    assert (shown in note) if shown else note == ""


def test_low_goal_match_goes_in_readme():
    g = graph()
    g["lesson"]["goalMatch"] = {"score": 0.25, "note": "The video builds support agents in no-code tools."}
    wd = prepare(g, ASKED, client=FakeClient(reply(kind="no_code")))
    assert "> Heads-up: this video only partly matches what you asked for (match 25%). The video builds" in (wd / "README.md").read_text()


def test_reused_folder_gets_its_readme_refreshed_without_claude():
    g = graph()
    wd = prepare(g, ASKED, client=FakeClient(reply(kind="no_code")))
    (wd / "README.md").write_text((wd / "README.md").read_text().replace("You asked for", "Goal"))
    g["lesson"]["goalMatch"] = 0.1
    again = FakeClient()
    prepare(g, ASKED, client=again)
    readme = (wd / "README.md").read_text()
    assert again.calls == [] and "You asked for" in readme and "(match 10%)" in readme


def test_requirements_no_editor_and_web_apps_with_links(mac):
    fc = FakeClient(reqs_reply(editor=False, why="All the work happens in OpenAI, Botpress and Zapier in the browser.", tools=[
        tool("OpenAI Agent Builder", "web_app", url="https://platform.openai.com/agent-builder", why="Steps 1-2: build the FAQ agent"),
        tool("Botpress", "web_app", url="https://botpress.com", why="Steps 3-4 and 7-9"),
        tool("Zapier Agents", "web_app", url="https://agents.zapier.com", why="Steps 5-6"),
        tool("Google Sheets", "web_app", url="https://sheets.google.com", why="Step 6 logs leads"),
        tool("WhatsApp", "web_app", url="javascript:alert(1)", why="optional channel"),  # not https -> dropped
    ]))
    items = requirements(graph(), client=fc, run=mac.run)
    assert ASKED not in fc.calls[0]["messages"][0]["content"]
    assert not editor_needed(items) and items[0]["why"].startswith("No editor needed: all the work happens")
    web = {it["tool"]: it for it in items if it["kind"] == "web_app"}
    assert list(web) == ["openai-platform", "botpress", "zapier", "google-sheets"]
    assert web["botpress"]["install"] == {"method": "open", "command": "", "url": "https://app.botpress.cloud"}
    assert all(it["ok"] and it["install"]["url"].startswith("https://") for it in web.values())
    assert missing(items) == []
    card = setup_card(items)
    assert card["actions"] == ["open_in_browser", "skip_setup"]  # no VS Code, nothing to install
    assert "OpenAI Platform, Botpress, Zapier, Google Sheets" in card["body"] and "No editor needed" in card["body"]
    assert not any(a[0] in ("brew", "pip") for a in mac.argv)
    json.dumps(card)


def test_install_refuses_web_apps():
    res = S.install({"tool": "zapier", "kind": "web_app", "label": "Zapier"}, popen=None)
    assert res["ok"] is False and res["url"] == "https://zapier.com/app/home"


def test_editor_why_keeps_proper_nouns():
    assert S._lower_first("Blender is a GUI app.") == "Blender is a GUI app."
    assert S._lower_first("All work happens in Figma.") == "all work happens in Figma."

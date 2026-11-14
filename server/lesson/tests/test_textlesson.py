"""Offline tests for no-video lessons: Claude and research are faked; no network."""

import asyncio
import json

import pytest

from server.lesson import builder, claude, textlesson
from server.lesson.schema import schema_errors

LESSONS = {
    "build a calculator in Python": {
        "plan": {"title": "Python calculator", "libraries": [{"name": "python", "version": "3.12"}], "steps": [
            {"title": "Create calc.py", "instructions": "Create calc.py with an add function.", "file": "calc.py"},
            {"title": "Add the other operations", "instructions": "Add subtract, multiply and divide.", "file": "calc.py"},
            {"title": "Read input and print", "instructions": "Ask for two numbers and an operator, then print the result.", "file": "calc.py"}]},
        "steps": [
            {"file": "calc.py", "code": "def add(a, b):\n    return a + b\n",
             "checks": [{"type": "screen_contains", "label": "add defined", "app": "Code", "pattern": r"def\s+add\(\s*a,\s*b\s*\)"}],
             "precision_checks": [{"type": "file_contains", "label": "add in file", "file": "calc.py", "pattern": r"def\s+add\("}],
             "targets": [{"file": "calc.py", "match": "def add(", "caption": "type the add function here"}], "hints": ["Start with def"]},
            {"file": "calc.py", "code": "def divide(a, b):\n    if b == 0:\n        raise ValueError('division by zero')\n    return a / b\n",
             "checks": [{"type": "screen_contains", "label": "divide guards zero", "app": "Code", "pattern": r"if\s+b\s*==\s*0"}],
             "targets": [{"file": "calc.py", "match": "def divide(", "caption": "divide"}], "hints": ["What happens when b is 0?"]},
            {"file": "calc.py", "code": "a = float(input('a: '))\nb = float(input('b: '))\nprint(add(a, b))\n", "run_command": "python calc.py",
             "checks": [{"type": "screen_contains", "label": "asks for input", "app": "Code", "pattern": r"float\(\s*input\("},
                        {"type": "screen_contains", "label": "prints the result", "app": "Terminal", "pattern": r"Result:\s*-?\d+(\.\d+)?"}],
             "targets": [{"file": "calc.py", "match": "print(add(", "caption": "print it"}], "hints": ["input() returns a string"]}]},
    "make a todo list in React": {
        "plan": {"title": "React todo list", "libraries": [{"name": "react", "version": "19.x"}, {"name": "vite", "version": "6.x"}], "steps": [
            {"title": "Create the Vite app", "instructions": "Scaffold a React app with Vite and start it.", "file": ""},
            {"title": "Hold todos in state", "instructions": "Store the todos with useState in App.jsx.", "file": "src/App.jsx"},
            {"title": "Add and list todos", "instructions": "Add an input that appends a todo and render the list.", "file": "src/App.jsx"},
            {"title": "Mark todos done", "instructions": "Toggle a todo when it is clicked.", "file": "src/App.jsx"}]},
        "steps": [
            {"file": "", "code": "npm create vite@latest todo -- --template react\ncd todo && npm install && npm run dev", "run_command": "npm run dev",
             "checks": [{"type": "screen_contains", "label": "dev server running", "app": "Terminal", "pattern": r"Local:\s+http://localhost:\d+"}],
             "targets": [{"file": "package.json", "match": "\"dev\"", "caption": "the dev script"}], "hints": ["Use the react template"]},
            {"file": "src/App.jsx", "code": "const [todos, setTodos] = useState([])",
             "checks": [{"type": "screen_contains", "label": "todos state", "app": "Code", "pattern": r"useState\(\s*\[\s*\]\s*\)"}],
             "targets": [{"file": "src/App.jsx", "match": "function App(", "caption": "inside App"}], "hints": ["useState returns a pair"]},
            {"file": "src/App.jsx", "code": "{todos.map(t => <li key={t.id}>{t.text}</li>)}",
             "checks": [{"type": "screen_contains", "label": "renders the list", "app": "Code", "pattern": r"todos\.map\("}],
             "targets": [{"file": "src/App.jsx", "match": "<ul>", "caption": "the list"}], "hints": ["Give each item a key"]},
            {"file": "src/App.jsx", "code": "onClick={() => toggle(t.id)}",
             "checks": [{"type": "screen_contains", "label": "toggle on click", "app": "Code", "pattern": r"onClick=\{\s*\(\)\s*=>\s*toggle"}],
             "targets": [{"file": "src/App.jsx", "match": "<li", "caption": "make items clickable"}], "hints": ["Copy the array before changing it"]}]},
    "write a CLI that renames files": {
        "plan": {"title": "File-renaming CLI", "libraries": [{"name": "python", "version": "3.12"}], "steps": [
            {"title": "Parse arguments", "instructions": "Use argparse to take a folder and a pattern.", "file": "rename.py"},
            {"title": "List matching files", "instructions": "Print the files that match the pattern.", "file": "rename.py"},
            {"title": "Rename with a dry run", "instructions": "Rename them, with --dry-run printing old -> new.", "file": "rename.py"}]},
        "steps": [
            {"file": "rename.py", "code": "import argparse\np = argparse.ArgumentParser()\np.add_argument('folder')\n",
             "checks": [{"type": "screen_contains", "label": "argparse set up", "app": "Code", "pattern": r"argparse\.ArgumentParser\("}],
             "targets": [{"file": "rename.py", "match": "import argparse", "caption": "top of the file"}], "hints": ["argparse is in the standard library"]},
            {"file": "rename.py", "code": "for f in sorted(Path(args.folder).glob(args.pattern)):\n    print(f.name)", "run_command": "python rename.py . '*.txt'",
             "checks": [{"type": "screen_contains", "label": "globs files", "app": "Code", "pattern": r"\.glob\(\s*args\.pattern"},
                        {"type": "screen_contains", "label": "lists .txt files", "app": "Terminal", "pattern": r"\w+\.txt"}],
             "targets": [{"file": "rename.py", "match": "for f in", "caption": "the loop"}], "hints": ["Path.glob takes a pattern"]},
            {"file": "rename.py", "code": "print(f'{f.name} -> {new}')\nif not args.dry_run:\n    f.rename(f.with_name(new))", "run_command": "python rename.py . '*.txt' --dry-run",
             "checks": [{"type": "screen_contains", "label": "shows old -> new", "app": "Terminal", "pattern": r"\S+\.txt\s*->\s*\S+"}],
             "targets": [{"file": "rename.py", "match": "f.rename(", "caption": "the rename"}], "hints": ["Check --dry-run before renaming"]}]},
}


@pytest.fixture
def fake_claude(monkeypatch, tmp_path):
    monkeypatch.setattr(builder, "CACHE_DIR", tmp_path / "cache")
    current = {}

    async def gen(system, prompt, schema, *, role=None, check=None, **kw):
        data = current["lesson"]
        if schema is textlesson.PLAN_SCHEMA:
            out = data["plan"]
        else:
            idx = int(prompt.split("Write step ", 1)[1].split(":", 1)[0])
            await asyncio.sleep(0.01 * idx)  # later steps finish at different times
            out = data["steps"][idx - 1]
        assert check is None or check(out) is None
        return json.loads(json.dumps(out))

    async def research(goal):
        return {"notes": "Use the current docs.", "sources": [{"url": "https://docs.python.org/3/library/argparse.html", "title": "argparse"}]}

    monkeypatch.setattr(claude, "_generate_json", gen)
    monkeypatch.setattr(textlesson, "research", research)
    return current


@pytest.mark.parametrize("goal", list(LESSONS))
def test_text_lessons_are_valid_and_arrive_step_by_step(fake_claude, tmp_path, goal):
    fake_claude["lesson"] = LESSONS[goal]
    updates = []
    g = asyncio.run(textlesson.build_text_lesson(goal, str(tmp_path / "work"), on_update=lambda gr, c: updates.append((c, len(gr["steps"])))))
    assert schema_errors(g) == []
    assert g["lesson"]["mode"] == "lesson" and g["lesson"]["complete"] is True and g["lesson"]["builtBy"] == "claude"
    assert updates[0] == (False, 1) and updates[-1][0] is True  # step 1 first, then the rest, then complete
    assert [n for _, n in updates] == sorted(n for _, n in updates)  # steps only ever appended
    n = len(LESSONS[goal]["plan"]["steps"])
    assert [s["id"] for s in g["steps"]] == [f"s{i}" for i in range(1, n + 1)]
    for s in g["steps"]:
        assert "video" not in s and s["code"].strip() and s["checks"] and s["hints"]
        assert all(t["file"] and t["match"] and t["app"] == "Code" for t in s["targets"]), s["targets"]
    assert [x["url"] for x in g["sources"]] == ["https://docs.python.org/3/library/argparse.html"]  # only tool results
    assert "cost" in g["build"]


def test_research_failure_never_blocks_the_lesson(fake_claude, tmp_path, monkeypatch):
    fake_claude["lesson"] = LESSONS["build a calculator in Python"]

    async def boom(goal):
        raise RuntimeError("web search unavailable")

    monkeypatch.setattr(textlesson, "research", boom)
    g = asyncio.run(textlesson.build_text_lesson("build a calculator in Python", str(tmp_path / "w")))
    assert len(g["steps"]) == 3 and g["sources"] == []


def test_cached_text_lesson_is_reused(fake_claude, tmp_path):
    fake_claude["lesson"] = LESSONS["write a CLI that renames files"]
    wd = str(tmp_path / "w2")
    g1 = asyncio.run(textlesson.build_text_lesson("write a CLI that renames files", wd))
    fake_claude["lesson"] = None  # any model call now would crash
    g2 = asyncio.run(textlesson.build_text_lesson("Write a CLI that renames files", wd))
    assert g2["steps"] == g1["steps"]


def test_research_cites_only_tool_result_urls_and_resumes_pause_turn(monkeypatch):
    from types import SimpleNamespace as NS

    turns = [
        NS(stop_reason="pause_turn", usage=NS(input_tokens=100, output_tokens=20), content=[
            NS(type="web_search_tool_result", content=[NS(type="web_search_result", url="https://react.dev/learn", title="Quick Start")]),
            NS(type="text", text="Notes part 1, see https://made-up.example/never-searched")]),
        NS(stop_reason="end_turn", usage=NS(input_tokens=150, output_tokens=60), content=[
            NS(type="web_search_tool_result", content=NS(type="web_search_tool_result_error", error_code="max_uses_exceeded")),
            NS(type="web_fetch_tool_result", content=NS(type="web_fetch_result", url="https://vite.dev/guide/")),
            NS(type="text", text="Notes part 2.")]),
    ]
    sent = []

    class Stream:
        def __init__(self, msg):
            self.msg = msg

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get_final_message(self):
            return self.msg

    class Messages:
        def stream(self, **kw):
            sent.append(kw)
            return Stream(turns[len(sent) - 1])

    monkeypatch.setattr(claude, "client", lambda: NS(messages=Messages()))
    r = asyncio.run(textlesson.research("make a todo list in React"))
    assert [s["url"] for s in r["sources"]] == ["https://react.dev/learn", "https://vite.dev/guide/"]  # not the made-up one
    assert "Notes part 1" in r["notes"] and "Notes part 2" in r["notes"]
    assert len(sent) == 2 and sent[1]["messages"][1]["role"] == "assistant"  # the paused turn was sent back as-is
    assert sent[0]["tools"][0]["type"] == "web_search_20260209"

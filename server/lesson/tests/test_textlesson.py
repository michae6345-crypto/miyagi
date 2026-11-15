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
            {"file": "rename.py", "code": "import argparse\nfrom pathlib import Path\np = argparse.ArgumentParser()\np.add_argument('folder')\n",
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
            title = prompt.split("Write step ", 1)[1].split('"', 2)[1]  # the plan may have been reordered: match by title
            k = next(j for j, st in enumerate(data["plan"]["steps"]) if st["title"] == title)
            await asyncio.sleep(0.01 * idx)  # later steps finish at different times
            out = data["steps"][k]
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
    n = len(LESSONS[goal]["plan"]["steps"]) + sum(  # a step with code AND a command becomes two
        1 for x in LESSONS[goal]["steps"] if x.get("run_command") and x.get("file") and x.get("code", "").strip() != x["run_command"])
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
    assert len(g["steps"]) == 4 and g["sources"] == []  # step 3 had code + a run command: split in two


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


def test_setup_noise_and_absolute_paths_are_stripped():
    wd = "/Users/tripi/miyagi/lessons/_new"
    step = {"id": "s1", "index": 1, "title": "Create calculator.py", "file": "calculator.py",
            "instructions": f"In your terminal run: mkdir -p {wd} && cd {wd} && touch calculator.py. Then define add in calculator.py.",
            "code": f"mkdir -p {wd}\ncd {wd}\ntouch calculator.py\ndef add(a, b):\n    return a + b",
            "run_command": f"mkdir -p {wd} && cd {wd}",
            "checks": [{"id": "s1c1", "type": "screen_contains", "label": "dir made", "app": "Terminal", "pattern": "calculator"}],
            "precision_checks": [], "targets": [{"file": "calculator.py", "match": "def add(", "caption": "here", "app": "Code"}],
            "hints": ["h"], "common_mistakes": [], "explanations": []}
    s = textlesson.sanitize_step(step, wd)
    blob = json.dumps(s)
    assert "/Users/" not in blob and "mkdir" not in blob and "touch" not in blob and "_new" not in blob
    assert s["instructions"] == "Then define add in calculator.py." and s["code"] == "def add(a, b):\n    return a + b"
    assert "run_command" not in s and s["checks"][0]["app"] == "Code"  # the Terminal check is gone
    fc = s["precision_checks"][0]
    assert fc["type"] == "file_contains" and fc["file"] == "calculator.py" and fc["id"] == "s1p1"
    import re as _re
    assert _re.search(fc["pattern"], "def add(a,  b):")  # spacing-tolerant literal


def test_prompts_never_see_the_absolute_workdir(fake_claude, tmp_path, monkeypatch):
    fake_claude["lesson"] = LESSONS["build a calculator in Python"]
    seen = []
    orig = claude._generate_json

    async def spy(system, prompt, schema, **kw):
        seen.append(prompt)
        return await orig(system, prompt, schema, **kw)

    monkeypatch.setattr(claude, "_generate_json", spy)
    wd = tmp_path / "lessons" / "_new"
    wd.mkdir(parents=True)
    (wd / "calculator.py").write_text("")
    asyncio.run(textlesson.build_text_lesson("build a calculator in Python", str(wd)))
    assert seen and all(str(wd) not in p for p in seen)


# ---- Michael's rules for text-lesson steps -------------------------------------------------

def test_plan_order_code_first_and_run_after_its_code():
    plan = [{"title": "Run the calculator", "instructions": "Run calculator.py in the terminal.", "file": ""},
            {"title": "Write add", "instructions": "Add an add function.", "file": "calculator.py"},
            {"title": "Read input", "instructions": "Ask for two numbers.", "file": "calculator.py"},
            {"title": "Install pytest", "instructions": "Run pip install pytest.", "file": ""}]
    out = textlesson.order_plan(plan)
    assert out[0]["title"] == "Write add"  # step 1 types code, never the terminal
    run_at = [s["title"] for s in out].index("Run the calculator")
    assert run_at > [s["title"] for s in out].index("Read input")  # runs only after the code it runs exists


def test_step_wording_and_run_step_checks():
    code = textlesson.shape_step({"id": "s1", "file": "calculator.py", "code": "def add(a, b):\n    return a + b",
                                  "instructions": "Open calculator.py (the file on the left) and type this in the VS Code terminal: the add function, carefully.",
                                  "checks": [], "precision_checks": []})
    assert code["instructions"] == "In calculator.py, type the code below."  # had 'terminal' and a parenthetical
    short = textlesson.shape_step({"id": "s2", "file": "calculator.py", "code": "x = 1", "instructions": "Add a subtract function (like add).",
                                   "checks": [], "precision_checks": []})
    assert short["instructions"] == "Add a subtract function." and len(short["instructions"].split()) <= 10
    run = textlesson.shape_step({"id": "s3", "file": "", "code": "", "run_command": "python calculator.py",
                                 "instructions": "Type this in the VS Code terminal (use python3 on a Mac):",
                                 "checks": [{"id": "s3c1", "type": "screen_contains", "label": "result", "app": "Terminal", "pattern": r"Result:\s*\d"}],
                                 "precision_checks": []})
    assert run["instructions"] == "Run your calculator in the terminal."  # 'terminal' for the command, no file name
    assert run["code"] == "python calculator.py" and run["file"] == "calculator.py"
    steps = [code, short, run]
    textlesson.link_run_steps(steps)
    fc = run["precision_checks"][0]
    import re
    assert fc["type"] == "file_contains" and fc["file"] == "calculator.py" and fc["id"] == "s3p1"
    assert re.search(fc["pattern"], "x = 1") and not re.search(fc["pattern"], "")  # needs the code in the file


def test_built_text_lesson_follows_the_rules(fake_claude, tmp_path):
    lesson = json.loads(json.dumps(LESSONS["build a calculator in Python"]))
    lesson["plan"]["steps"].insert(0, {"title": "Run it", "instructions": "Type this in the VS Code terminal (use python…", "file": ""})
    lesson["steps"].insert(0, {"file": "", "code": "", "run_command": "python calc.py", "hints": ["h"],
                               "checks": [{"type": "screen_contains", "label": "runs", "app": "Terminal", "pattern": r"Result:\s*\d+"}],
                               "targets": [{"file": "calc.py", "match": "def add(", "caption": "c"}]})
    fake_claude["lesson"] = lesson

    # the fake answers by step index; after reordering, step 1 must be a code step
    g = asyncio.run(textlesson.build_text_lesson("build a calculator in Python", str(tmp_path / "w")))
    s1 = g["steps"][0]
    assert not s1.get("run_command") and "terminal" not in s1["instructions"].lower()
    for s in g["steps"]:
        assert "(" not in s["instructions"] and len(s["instructions"].split()) <= 10, s["instructions"]



# ---- S11's rehearsal fixes ----------------------------------------------------------------

def test_python3_on_macos(monkeypatch):
    monkeypatch.delenv("LESSON_PYTHON", raising=False)
    monkeypatch.setattr(textlesson.shutil, "which", lambda name: None if name == "python" else f"/usr/bin/{name}")
    st = textlesson.use_python3({"id": "s4", "file": "calculator.py", "code": "python calculator.py", "run_command": "python calculator.py",
                                 "instructions": "Run python calculator.py.", "checks": [],
                                 "precision_checks": [{"type": "command_exit_ok", "command": "python calculator.py"}]})
    assert st["run_command"] == st["code"] == "python3 calculator.py" and st["precision_checks"][0]["command"] == "python3 calculator.py"
    assert textlesson.use_python3({"id": "s1", "file": "a.py", "code": "import python_helpers", "checks": [], "precision_checks": []})["code"] == "import python_helpers"


def test_code_and_run_are_split_and_the_run_step_has_real_checks():
    st = {"id": "s3", "index": 3, "title": "Print a sum", "file": "calculator.py", "code": "print(add(2, 3))",
          "run_command": "python3 calculator.py", "expected_output": "5", "instructions": "Type print(add(2, 3)) and run it.",
          "checks": [{"id": "c", "type": "screen_contains", "label": "x", "app": "Terminal", "pattern": r"\b5\b"}],
          "precision_checks": [{"id": "p", "type": "command_exit_ok", "label": "runs", "command": "python3 calculator.py"}],
          "targets": [], "hints": ["h"], "common_mistakes": []}
    code, run = textlesson.split_code_and_run(st)
    assert "run_command" not in code and code["code"] == "print(add(2, 3))" and all(c.get("app") != "Terminal" for c in code["checks"])
    assert run["run_command"] == run["code"] == "python3 calculator.py"
    steps = [dict(code, id="s3"), dict(textlesson.shape_step(run), id="s4")]
    textlesson.link_run_steps(steps)
    r = steps[1]
    import re
    fc = r["precision_checks"][0]
    assert fc["type"] == "file_contains" and re.search(fc["pattern"], "print(add(2, 3))")
    out = [c for c in r["checks"] if c["pattern"].startswith("^")][0]  # exact stdout line
    assert re.search(out["pattern"], "$ python3 calculator.py\n5\n", re.M) and not re.search(out["pattern"], "15\n", re.M)
    from server.lesson.schema import is_weak
    assert not is_weak(out)  # an exact whole line is specific enough


def test_each_code_step_gets_a_literal_anchor():
    st = {"file": "calculator.py", "code": "def add(a, b):\n    return a + b", "targets": [{"match": "the add function", "caption": "c"}]}
    textlesson.exact_anchor(st, "def add(a, b):\n    return a + b\n")
    assert st["targets"] == [{"app": "Code", "file": "calculator.py", "match": "def add(a, b):", "caption": "type here"}]
    keep = {"file": "calculator.py", "code": "x = 1", "targets": [{"match": "def add(a, b):", "caption": "c"}]}
    textlesson.exact_anchor(keep, "def add(a, b):\n    return a + b\nx = 1")
    assert keep["targets"][0]["match"] == "def add(a, b):"  # a real line already: kept


def test_contradictions_with_the_file_so_far_are_caught():
    state = {"calculator.py": "def add(a, b):\n    return a + b\n"}
    p = textlesson.consistency_problem
    assert "already written" in p("calculator.py", "def add(x, y):\n    return x + y", "", state)  # re-adds add
    assert "not written yet" in p("calculator.py", "print(multiply(2, 3))", "", state)  # calls what doesn't exist
    assert p("calculator.py", "def subtract(a, b):\n    return a - b\nprint(add(2, 3))", "", state) is None
    assert p("calculator.py", "import math\nprint(math.sqrt(add(2, 2)))", "", state) is None


def test_strings_are_not_calls():
    state = {"calculator.py": "def add(a, b):\n    return a + b\n"}
    assert textlesson.consistency_problem("calculator.py", 'op = input("Operator (+, -): ")\nprint(add(1, 2))', "", state) is None


def test_contradicting_step_is_rewritten_with_the_problem_spelled_out(fake_claude, tmp_path, monkeypatch):
    lesson = json.loads(json.dumps(LESSONS["build a calculator in Python"]))
    lesson["steps"][1]["code"] = "def add(a, b):\n    return a + b\ndef divide(a, b):\n    return a / b\n"  # re-adds add
    fake_claude["lesson"] = lesson
    orig = claude._generate_json
    prompts = []

    async def gen(system, prompt, schema, *, role=None, **kw):
        if role == "escalate":
            prompts.append(prompt)
            return {"file": "calc.py", "code": "def divide(a, b):\n    return a / b\n", "hints": ["h"],
                    "checks": [{"type": "screen_contains", "label": "divide", "app": "Code", "pattern": r"def\s+divide\("}],
                    "targets": [{"file": "calc.py", "match": "return a + b", "caption": "after add"}]}
        return await orig(system, prompt, schema, role=role, **kw)

    monkeypatch.setattr(claude, "_generate_json", gen)
    g = asyncio.run(textlesson.build_text_lesson("build a calculator in Python", str(tmp_path / "w")))
    assert prompts and "already written" in prompts[0] and "Never re-type" in prompts[0]
    s2 = g["steps"][1]
    assert s2["code"].count("def add") == 0 and "def divide" in s2["code"]
    assert s2["targets"][0]["match"] == "return a + b"  # anchored to the existing line it goes after

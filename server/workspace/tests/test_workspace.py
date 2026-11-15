"""server.workspace with a fake Claude client (offline). Live runs: tests/live_run.py."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from server.workspace import (
    core,
    folder_name,
    hero_workdir,
    open_editor,
    open_file_for,
    prepare,
    read_state,
    scaffold,
)
from server.workspace.paths import REPO_ROOT

FIX = Path(__file__).parent / "fixtures"
CACHE = REPO_ROOT / "demo" / "cache" / "lessons"


def load(name: str) -> dict:
    p = FIX / name if (FIX / name).exists() else CACHE / name
    return json.loads(p.read_text())


class FakeClient:
    """Mimics anthropic.Anthropic().messages.create; returns queued JSON replies."""

    def __init__(self, *replies: dict):
        self.replies = list(replies)
        self.calls: list[dict] = []
        self.messages = self

    def create(self, **kw):
        self.calls.append(kw)
        reply = self.replies.pop(0) if self.replies else {}
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=json.dumps(reply))])


def reply(files=(), *, stack="python", setup=(), open_file="", git=None, kind="code") -> dict:
    return {
        "lesson_kind": kind, "stack": stack, "summary": "starter", "setup": list(setup), "open_file": open_file,
        "files": [{"path": p, "content": c} for p, c in files],
        "git": git or {"init": False, "default_branch": "", "ops": []},
    }


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("MIYAGI_LESSONS_DIR", str(tmp_path / "lessons"))
    for k in ("ORCH_HERO_WORKDIR", "ORCH_HERO_LESSON_IDS", "ORCH_LESSON_URL"):
        monkeypatch.delenv(k, raising=False)


def test_pandas_starter_files_readme_and_state(tmp_path):
    g = load("pandas_pokemon.json")
    csv = "#,Name,Type 1,Type 2,HP,Attack,Defense,Sp. Atk,Sp. Def,Speed,Generation,Legendary\n1,Bulbasaur,Grass,Poison,45,49,49,65,65,45,1,False\n"
    fc = FakeClient(reply([("main.py", '"""Pokemon data analysis with pandas."""\n# Step 1: load the CSV\n'),
                           ("requirements.txt", "pandas\n"), ("pokemon_data.csv", csv)],
                          setup=["pip install -r requirements.txt"], open_file="main.py"))
    wd = prepare(g, "learn pandas", client=fc)
    assert scaffold.SYSTEM and "lesson.libraries" in fc.calls[0]["messages"][0]["content"]
    assert wd.parent == tmp_path / "lessons"
    assert wd.name == folder_name(g) and wd.name.startswith("complete-python-pandas-data-science-tutorial-")
    assert (wd / "main.py").read_text().startswith('"""Pokemon')
    assert (wd / "pokemon_data.csv").exists() and (wd / "requirements.txt").exists()
    readme = (wd / "README.md").read_text()
    assert "https://www.youtube.com/watch?v=vmEHCJofslg" in readme
    assert "1. Load the Pokemon CSV" in readme and "6. Group by type" in readme
    assert "pip install -r requirements.txt" in readme and "not the original dataset" in readme
    st = read_state(wd)
    assert st["files"] == ["main.py", "pokemon_data.csv", "requirements.txt"] and st["error"] == ""
    assert open_file_for(wd) == "main.py"
    # the prompt carried the lesson, and asked for structured output
    call = fc.calls[0]
    assert "Load the Pokemon CSV" in call["messages"][0]["content"]
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert "filtered.csv" in call["messages"][0]["content"]  # learner-created file is listed as forbidden


def test_reuse_never_calls_claude_twice_nor_overwrites(tmp_path):
    g = load("pandas_pokemon.json")
    wd = prepare(g, "", client=FakeClient(reply([("main.py", "# start\n")])))
    (wd / "main.py").write_text("import pandas as pd  # learner's work\n")
    again = FakeClient(reply([("main.py", "# other\n")]))
    assert prepare(g, "", client=again) == wd
    assert again.calls == []
    assert "learner's work" in (wd / "main.py").read_text()


def test_existing_files_are_not_replaced_on_first_scaffold(tmp_path):
    g = load("pandas_pokemon.json")
    wd = tmp_path / "lessons" / folder_name(g)
    wd.mkdir(parents=True)
    (wd / "main.py").write_text("mine\n")
    prepare(g, "", client=FakeClient(reply([("main.py", "# start\n"), ("notes.txt", "hi\n")])))
    assert (wd / "main.py").read_text() == "mine\n" and (wd / "notes.txt").exists()


def test_solution_leak_is_sent_back_then_dropped():
    g = load("pandas_pokemon.json")
    leaky = reply([("main.py", "import pandas as pd\ndf = pd.read_csv('pokemon_data.csv')\n")])
    still_leaky = reply([("main.py", "df = pd.read_csv('pokemon_data.csv')\n"), ("helper.py", "# ok\n")])
    fc = FakeClient(leaky, still_leaky)
    sc = scaffold.generate(g, "", client=fc)
    assert len(fc.calls) == 2
    assert "s1c1" in fc.calls[1]["messages"][-1]["content"]  # feedback names the check
    assert "main.py" not in sc.files and "helper.py" in sc.files
    assert any("gives away" in d for d in sc.dropped)


def test_leak_fixed_on_retry_is_kept():
    g = load("pandas_pokemon.json")
    fc = FakeClient(reply([("main.py", "x.groupby(['Type 1'])\n")]), reply([("main.py", '"""Pokemon by type."""\n# Step 6: group by type\n')]))
    sc = scaffold.generate(g, "", client=fc)
    assert sc.files == {"main.py": '"""Pokemon by type."""\n'} and sc.dropped == []  # E26: no step-numbered placeholder


def test_starter_files_have_no_step_numbered_placeholders():
    """E26: '# Step 1: start building the weather CLI here' stayed under the learner's step-2 code."""
    raw = reply([("weather.py", '"""Weather CLI."""\n\nimport sys\n\n# Step 1: start building the weather CLI here\n'),
                 ("app.js", "// step 2 - fetch\nconst a = 1;\n"), ("notes.md", "# Step 1: Install\n")])
    sc, _ = scaffold.vet(raw, {"steps": []})
    assert sc.files["weather.py"] == '"""Weather CLI."""\n\nimport sys\n'
    assert sc.files["app.js"] == "const a = 1;\n" and sc.files["notes.md"] == "# Step 1: Install\n"  # Markdown: a heading
    assert "No step-numbered placeholder" in scaffold.PROMPT


def test_learner_created_and_unsafe_files_are_dropped():
    g = load("pandas_pokemon.json")
    raw = reply([("filtered.py", "# ok\n"), ("../escape.py", "x"), ("/etc/passwd", "x"), (".git/config", "x"),
                 ("README.md", "x"), ("logo.png", "x"), ("big.txt", "x" * 30_000)])
    g["steps"][4]["precision_checks"].append({"id": "s5p2", "type": "file_exists", "label": "x", "file": "filtered.py"})
    sc, _ = scaffold.vet(raw, g)
    assert sc.files == {}
    assert len(sc.dropped) == 7


def test_learner_created_data_file_is_allowed():
    g = load("pandas_pokemon.json")
    g["steps"][0]["precision_checks"].append({"id": "s1p2", "type": "file_exists", "label": "csv", "file": "pokemon_data.csv"})
    sc, _ = scaffold.vet(reply([("pokemon_data.csv", "a,b\n1,2\n")]), g)
    assert "pokemon_data.csv" in sc.files


def test_terminal_screen_checks_are_not_leaks():
    g = load("8b6203eb5ec8c6f6.json")  # git basics: checks read the Terminal
    sc, leaks = scaffold.vet(reply([("notes.txt", "git config --global user.name")]), g)
    assert leaks == [] and "notes.txt" in sc.files


def test_react_lesson_that_scaffolds_itself_gets_readme_only(tmp_path):
    g = load("516197461c0dacf3.json")  # step 1: npm create vite -> my-react-app/
    fc = FakeClient(reply([("my-react-app/package.json", "{}")], stack="node/react", setup=["node -v"]))
    wd = prepare(g, "learn react", client=fc)
    assert sorted(p.name for p in wd.iterdir()) == [".vscode", "README.md"]  # + our workspace settings
    assert "my-react-app/package.json" in fc.calls[0]["messages"][0]["content"]  # told it's learner-created
    assert any("learner create" in d for d in read_state(wd)["dropped"])


def test_git_history_is_scripted(tmp_path):
    g = load("git_rebase.json")
    git = {"init": True, "default_branch": "main", "ops": [
        {"op": "commit", "name": "", "message": "Add greet", "files": [{"path": "app.py", "content": "def greet(name):\n    return 'hi ' + name\n"}]},
        {"op": "branch", "name": "feature", "message": "", "files": []},
        {"op": "commit", "name": "", "message": "Shout", "files": [{"path": "app.py", "content": "def greet(name):\n    return 'HI ' + name\n"}]},
        {"op": "checkout", "name": "main", "message": "", "files": []},
        {"op": "commit", "name": "", "message": "Exclaim", "files": [{"path": "app.py", "content": "def greet(name):\n    return 'hi ' + name + '!'\n"}]},
        {"op": "checkout", "name": "feature", "message": "", "files": []},
    ]}
    wd = prepare(g, "", client=FakeClient(reply(stack="git", git=git, open_file="app.py")))
    log = subprocess.run(["git", "log", "--oneline", "--all"], cwd=wd, capture_output=True, text=True, check=True).stdout
    assert len(log.strip().splitlines()) == 3
    branch = subprocess.run(["git", "branch", "--show-current"], cwd=wd, capture_output=True, text=True, check=True).stdout.strip()
    assert branch == "feature"
    assert "3 commits" in (wd / "README.md").read_text()
    assert open_file_for(wd) == "app.py"
    assert subprocess.run(["git", "status", "--porcelain"], cwd=wd, capture_output=True, text=True, check=True).stdout.strip() == "?? README.md"


def test_no_git_history_when_a_step_runs_git_init():
    g = load("8b6203eb5ec8c6f6.json")  # s2: file_exists project1/.git
    sc, _ = scaffold.vet(reply(git={"init": True, "default_branch": "main", "ops": []}), g)
    assert sc.git_init is False and any("git init itself" in d for d in sc.dropped)


def test_no_key_gives_readme_only_and_retries_later(monkeypatch, tmp_path):
    monkeypatch.setattr(scaffold, "make_client", lambda: None)
    g = load("pandas_pokemon.json")
    wd = prepare(g, "")
    assert sorted(p.name for p in wd.iterdir()) == [".vscode", "README.md"]  # + our workspace settings
    assert "no Anthropic key" in read_state(wd)["error"]
    fc = FakeClient(reply([("main.py", "# start\n")]))
    prepare(g, "", client=fc)  # a failed scaffold is retried on the next prepare
    assert (wd / "main.py").exists() and len(fc.calls) == 1


def test_api_error_never_raises(tmp_path):
    class Boom(FakeClient):
        def create(self, **kw):
            raise RuntimeError("529 overloaded")

    wd = prepare(load("pandas_pokemon.json"), "", client=Boom())
    assert (wd / "README.md").exists() and "overloaded" in read_state(wd)["error"]


def test_schema_fallback_to_prompt_json():
    class NoStructured(FakeClient):
        def create(self, **kw):
            if "output_config" in kw:
                raise RuntimeError("output_config.format: json_schema not supported for this model")
            return super().create(**kw)

    fc = NoStructured(reply([("main.py", "# hi\n")]))
    sc = scaffold.generate(load("pandas_pokemon.json"), "", client=fc)
    assert sc.files == {"main.py": "# hi\n"} and "JSON Schema" in fc.calls[-1]["messages"][-1]["content"]


def test_readme_titles_never_satisfy_editor_checks(tmp_path):
    g = load("pandas_pokemon.json")
    g["steps"][2]["checks"].append({"id": "s3c2", "type": "screen_contains", "label": "x", "app": "Code", "pattern": "Sort by name"})
    wd = prepare(g, "", client=FakeClient(reply()))
    readme = (wd / "README.md").read_text()
    assert "Sort by name" not in readme and "3. Step 3" in readme


# --------------------------------------------------------------------------- hero

def test_hero_by_cached_lesson_id_and_video(monkeypatch, tmp_path):
    hero = load("aebc6b8fba02dac5.json")
    fc = FakeClient()
    assert prepare(hero, "", client=fc) == (REPO_ROOT / "demo" / "pinn-lab").resolve()
    assert fc.calls == [] and not (tmp_path / "lessons").exists()
    other = load("e29a5128eb0e7fe1.json")  # same video, other lesson id
    assert hero_workdir(other) == (REPO_ROOT / "demo" / "pinn-lab").resolve()
    monkeypatch.setenv("ORCH_HERO_WORKDIR", str(tmp_path / "hero"))
    assert hero_workdir(hero) == (tmp_path / "hero").resolve()


def test_hero_from_orch_lesson_url(monkeypatch):
    g = load("pandas_pokemon.json")
    assert hero_workdir(g) is None
    monkeypatch.setenv("ORCH_LESSON_URL", "https://youtu.be/vmEHCJofslg")
    assert hero_workdir(g) is not None


def test_non_hero_cached_lessons_are_not_hero():
    for name in ("516197461c0dacf3.json", "8b6203eb5ec8c6f6.json", "8032bf0cabe0e287.json"):
        assert hero_workdir(load(name)) is None, name


# --------------------------------------------------------------------------- editor

def test_open_editor_missing_folder(tmp_path):
    assert open_editor(tmp_path / "nope", runner=lambda a: True, editor={"id": "vscode", "label": "VS Code", "app": "Visual Studio Code", "cli": "/x/code"}) is False


def test_slug_and_hash_are_stable():
    g = load("pandas_pokemon.json")
    assert folder_name(g) == folder_name(json.loads(json.dumps(g)))
    g2 = {**g, "lesson": {**g["lesson"], "id": "other"}}
    assert folder_name(g2) != folder_name(g)
    assert core._fmt_t(3725) == "1:02:05" and core._fmt_t(93) == "1:33"


def test_build_workdir(tmp_path):
    from server.workspace import build_workdir

    assert build_workdir("https://www.youtube.com/watch?v=AXXnSzmpyoI") == str((REPO_ROOT / "demo" / "pinn-lab").resolve())
    other = build_workdir("https://www.youtube.com/watch?v=vmEHCJofslg")
    assert other == str(tmp_path / "lessons" / "_new") and not Path(other).exists()

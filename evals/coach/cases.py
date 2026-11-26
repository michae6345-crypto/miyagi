"""Nine realistic beginner mistakes (React useEffect cleanup, pandas groupby, git interactive rebase).

Every terminal / notebook output here is REAL: git runs the rebase, nbclient executes the notebook with
the pandas the lesson's requirements.txt installs today (pandas>=2.0 -> 3.1.x), and the React component
runs under react-test-renderer (react_check.mjs). Only the CRA dev-server banner is written from its
known format (react-scripts 5), with the line/column of the undefined name computed from the file.

`build(case, root)` makes the learner's folder and the screen (PNG + sidecar in the fixture format);
`verify(case, built, new_text, command)` applies the coach's fix the way the learner would and re-runs
the real check, returning the post-fix terminal/notebook state for the after-screen.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .screens import MENU_H, Screen, centre

HERE = Path(__file__).resolve().parent
LESSONS = HERE / "lessons"
REACT_ENV = Path(os.environ.get("REACT_ENV", ""))  # folder with node_modules: react@18 react-test-renderer@18 esbuild


@dataclass
class Case:
    id: str
    topic: str  # react | pandas | git
    lesson: str  # file in lessons/
    step: str
    mistake: str  # what the learner did
    truth: str  # the real cause + the right fix (for grading)
    cause_rx: list[str]  # every regex must match title+body (case-insensitive) for "diagnosis correct"
    target_rx: str  # the OCR line the coach should point at
    fix: str  # code | command | either
    cursor_on: tuple[str, str]  # (kind, regex) where the learner's pointer rests
    front: str = "Code"
    notes: str = ""

    def graph(self) -> dict:
        return json.loads((LESSONS / self.lesson).read_text())

    def step_dict(self) -> dict:
        return next(s for s in self.graph()["steps"] if s["id"] == self.step)


@dataclass
class Built:
    workdir: Path
    file: str  # path (relative to workdir) of the file the fix belongs in
    file_text: str
    screen: Screen
    cursor: tuple[float, float]
    cursor_text: str
    terminal: list[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict)


CASES: list[Case] = [
    # ------------------------------------------------------------------ React (useEffect cleanup)
    Case("R1", "react", "react-useeffect-cleanup.json", "s3",
         "Wrote `return clearInterval(intervalId);`: calls clearInterval during the effect instead of returning a cleanup function",
         "clearInterval runs immediately, so the timer never ticks (stays at 0) and nothing is cleaned up on unmount. Fix: `return () => { ...; clearInterval(intervalId); };`",
         [r"(return|returns|returning).{0,80}(function|\(\)\s*=>|arrow)|(function|\(\)\s*=>|arrow).{0,80}(return)",
          r"immediately|right away|at once|on mount|when the effect runs|during the effect|calls? clearInterval|invok|executes?|stops? the (timer|interval)"],
         r"return\s+clearInterval", "code", ("editor", r"return\s+clearInterval"),
         notes="screen checks for s3 only look for `clearInterval(` → the gate PASSES on this bug"),
    Case("R2", "react", "react-useeffect-cleanup.json", "s3",
         "Kept the s1 name `interval` but the cleanup calls `clearInterval(intervalId)`",
         "`intervalId` is not defined (eslint no-undef → Failed to compile). Fix: use the same name, e.g. `const intervalId = setInterval(...)` or `clearInterval(interval)`.",
         [r"intervalId", r"not defined|undefined|doesn.t exist|no variable|never declared|isn.t declared|named `?interval`?"],
         r"clearInterval\(intervalId\)|const interval = setInterval|is not defined", "code", ("terminal", r"is not defined"), front="Terminal"),
    Case("R3", "react", "react-useeffect-cleanup.json", "s1",
         "Imported only useState: `import React, { useState } from 'react';` then called useEffect",
         "useEffect is not imported (no-undef → Failed to compile). Fix: `import React, { useState, useEffect } from 'react';`",
         [r"useEffect", r"import"],
         r"import React|is not defined", "code", ("editor", r"useEffect\(")),
    # ------------------------------------------------------------------ pandas (groupby)
    Case("P1", "pandas", "pandas-groupby.json", "s2",
         "`df.groupby(\"Department\").mean()` on the whole frame (it has the text column Employee)",
         "mean() over every column hits the string column Employee → TypeError. Fix: select the column first: `df.groupby(\"Department\")[\"Salary\"].mean()` (or numeric_only=True).",
         [r"Employee|string|str\b|text|non-numeric|object", r"Salary|numeric_only"],
         r"groupby\(\"Department\"\)\.mean|^TypeError", "code", ("editor", r"groupby\(\"Department\"\)\.mean")),
    Case("P2", "pandas", "pandas-groupby.json", "s3",
         "`df.groupby(\"Department\", \"Experience_Years\")`: two strings instead of one list",
         "The second positional argument is `level`, so pandas looks for an index level named Experience_Years → ValueError. Fix: `df.groupby([\"Department\", \"Experience_Years\"])`.",
         [r"list|\[\s*\"?Department", r"level|second (positional )?argument|positional|index"],
         r"groupby\(\"Department\", \"Experience_Years\"\)|^ValueError", "code", ("editor", r"Experience_Years\"\)\[")),
    Case("P3", "pandas", "pandas-groupby.json", "s4",
         "`.agg({\"Salary\": [mean, max, min], ...})`: bare names instead of strings",
         "`mean` is not a Python name (max/min are builtins) → NameError. Fix: quote them: `[\"mean\", \"max\", \"min\"]`, `[\"mean\", \"count\"]`.",
         [r"mean", r"string|quot|\"mean\"|'mean'"],
         r"\.agg\(|NameError", "code", ("editor", r"\.agg\(")),
    # ------------------------------------------------------------------ git (interactive rebase)
    Case("G1", "git", "git-interactive-rebase.json", "s5",
         "Changed the FIRST todo line to `squash` instead of the Cleanup line",
         "squash melds a commit into the one above it; the first line has none → `cannot 'squash' without a previous commit`. Fix: line 1 back to `pick`, `squash` on the Cleanup line, then `git rebase --continue`.",
         [r"squash", r"first|top|previous|above|nothing (before|above)"],
         r"^squash", "either", ("editor", r"^squash")),
    Case("G2", "git", "git-interactive-rebase.json", "s3",
         "At the `edit` stop, removed the debug line in index.js but ran `git rebase --continue` without `git add`",
         "The edit is unstaged; git refuses with the (misleading) 'You must edit all merge conflicts ... using git add'. There is no conflict. Fix: `git add index.js` then `git rebase --continue`.",
         [r"git add|stage|unstaged", r"index\.js|change|edit"],
         r"You must edit all merge conflicts|git rebase --continue$|console\.log\('DEBUG|app\.post\('/login'", "command", ("terminal", r"You must edit all merge conflicts"), front="Terminal"),
    Case("G3", "git", "git-interactive-rebase.json", "s5",
         "Moved `Cleanup` above `Add logout endpoint` to squash it into the login commit → CONFLICT, then ran `git rebase --continue` with the markers still in index.js",
         "Cleanup edits the logout route, which does not exist yet at that point → conflict; continuing without resolving fails ('needs merge'). Fix: `git rebase --abort` and squash Cleanup where it was (right under Add logout endpoint), or resolve the markers and `git add index.js`.",
         [r"conflict", r"marker|<<<<<<<|resolve|abort|logout|order|reorder|moved"],
         r"<<<<<<<|=======|>>>>>>>", "either", ("editor", r"^<<<<<<<")),
]

BY_ID = {c.id: c for c in CASES}


# ===================================================================================== React

TIMER_OK = """import React, { useState, useEffect } from 'react';

function Timer() {
  const [seconds, setSeconds] = useState(0);

  useEffect(() => {
    const intervalId = setInterval(() => {
      console.log('Interval running');
      setSeconds((prev) => prev + 1);
    }, 1000);

    return () => {
      console.log('clean up called');
      clearInterval(intervalId);
    };
  }, []);

  return <h1>Seconds: {seconds}</h1>;
}

export default Timer;
"""

REACT_FILES = {
    "R1": TIMER_OK.replace("""    return () => {
      console.log('clean up called');
      clearInterval(intervalId);
    };""", """    console.log('clean up called');
    return clearInterval(intervalId);"""),
    "R2": TIMER_OK.replace("const intervalId = setInterval", "const interval = setInterval"),
    "R3": """import React, { useState } from 'react';

function Timer() {
  const [seconds, setSeconds] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => {
      console.log('Interval running');
      setSeconds((prev) => prev + 1);
    }, 1000);
  }, []);

  return <h1>Seconds: {seconds}</h1>;
}

export default Timer;
""",
}

APP_JS = """import { useState } from 'react';
import Timer from './Components/Timer';

function App() {
  const [showTimer, setShowTimer] = useState(false);

  return (
    <div className="App">
      <button onClick={() => setShowTimer(!showTimer)}>Toggle Timer</button>
      {showTimer && <Timer />}
    </div>
  );
}

export default App;
"""

CRA_OK = ["Compiled successfully!", "", "You can now view demo-app in the browser.", "",
          "  Local:            http://localhost:3000", "  On Your Network:  http://192.168.1.23:3000", "",
          "Note that the development build is not optimized.", "To create a production build, use npm run build.", "",
          "webpack compiled successfully"]


def cra_failed(file: str, line: int, col: int, msg: str) -> list[str]:
    err = [f"src/{file}", f"  Line {line}:{col}:  {msg}  no-undef", "", "Search for the keywords to learn more about each error."]
    return ["Failed to compile.", "", "[eslint] ", *err, "ERROR in [eslint] ", *err, "", "webpack compiled with 1 error"]


def undefined_names(text: str) -> list[tuple[str, int, int]]:
    """(name, line, col) for the two no-undef names these cases can have (eslint reports the first use)."""
    out = []
    for name in ("useEffect", "intervalId"):
        declared = re.search(rf"(import[^;]*\b{name}\b|const {name}\b|let {name}\b)", text)
        if declared:
            continue
        for i, ln in enumerate(text.splitlines(), 1):
            m = re.search(rf"\b{name}\b", ln)
            if m:
                out.append((name, i, m.start() + 1))
                break
    return out


def react_terminal(text: str) -> list[str]:
    bad = undefined_names(text)
    if bad:
        name, line, col = bad[0]
        return cra_failed("Components/Timer.js", line, col, f"'{name}' is not defined")
    return list(CRA_OK)


def react_check(timer_text: str, workdir: Path, step: str = "s3") -> dict:
    """Mount <StrictMode><Timer/></StrictMode>, tick 3 times, unmount; count live intervals (react_check.mjs).
    s1/s2 only need a ticking timer (the leak is what s2 demonstrates); s3+ also need the cleanup."""
    if not (REACT_ENV / "node_modules" / "react-test-renderer").is_dir():
        return {"ok": None, "error": "REACT_ENV not set up (npm i react@18.3.1 react-dom@18.3.1 react-test-renderer@18.3.1 esbuild@0.24.2)"}
    src = workdir / "_check_Timer.js"
    src.write_text(timer_text)
    p = subprocess.run(["node", str(HERE / "react_check.mjs"), str(src)], capture_output=True, text=True, timeout=60,
                       cwd=REACT_ENV, env={**os.environ, "NODE_PATH": str(REACT_ENV / "node_modules")})
    src.unlink(missing_ok=True)
    try:
        res = json.loads(p.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        return {"ok": False, "error": (p.stderr or p.stdout)[-600:]}
    lint = undefined_names(timer_text)
    res["no_undef"] = [f"{n} (line {l})" for n, l, _ in lint]
    if step in ("s1", "s2"):
        res["ok"] = not res.get("error") and res.get("seconds_after_3_ticks") == 3 and not lint
    else:
        res["ok"] = bool(res.get("ok")) and not lint
    return res


def build_react(case: Case, root: Path) -> Built:
    wd = root / "demo-app"
    (wd / "src" / "Components").mkdir(parents=True, exist_ok=True)
    text = REACT_FILES[case.id]
    (wd / "src" / "Components" / "Timer.js").write_text(text)
    (wd / "src" / "App.js").write_text(APP_JS)
    (wd / "package.json").write_text(json.dumps({"name": "demo-app", "version": "0.1.0", "private": True,
                                                 "dependencies": {"react": "^18.3.1", "react-dom": "^18.3.1", "react-scripts": "5.0.1"},
                                                 "scripts": {"start": "react-scripts start"}}, indent=2))
    term = react_terminal(text)  # CRA clears the screen on every recompile: only the latest result is visible
    return _react_screen(case, wd, text, term)


def _react_screen(case: Case, wd: Path, text: str, term: list[str], after: bool = False) -> Built:
    s = Screen(front_app=case.front)
    lines = text.splitlines()
    cur_line = next((i for i, l in enumerate(lines, 1) if re.search(case.cursor_on[1], l)), 1) if case.cursor_on[0] == "editor" else 6
    s.vscode((0, MENU_H, 1000, 1117 - MENU_H), folder="demo-app",
             tree=[(0, "node_modules"), (0, "public"), (0, "src"), (1, "Components"), (2, "Timer.js"), (1, "App.css"),
                   (1, "App.js"), (1, "index.js"), (0, ".gitignore"), (0, "package.json"), (0, "README.md")],
             tabs=["App.js", "Timer.js"], active="Timer.js", file_path="src/Components/Timer.js",
             lines=lines, lang="js", cursor_line=cur_line)
    check = react_check(text, wd, case.step) if after or case.id == "R1" else {}
    if term[0].startswith("Failed"):
        body = [("Compiled with problems:", 18), ("ERROR", 13), ("[eslint]", 12.5), (term[3], 12.5), (term[4].strip(), 12.5),
                ("Search for the keywords to learn more about each error.", 12)]
    else:
        secs = check.get("seconds_after_3_ticks", 3) if check else 3
        body = [("Toggle Timer", 13), (f"Seconds: {secs}", 26), ("", 6), ("Console", 12),
                *[(ln, 11.5) for ln in (check.get("console") or ["Interval running   Timer.js:8"])[-6:]]]
    s.chrome((1004, MENU_H, 724, 520), tab="React App", url="localhost:3000", body=body)
    s.terminal((1004, MENU_H + 524, 724, 1117 - MENU_H - 524), title="demo-app — node ◂ npm start — 100×34", lines=term)
    cur = s.find(case.cursor_on[1], app="Code" if case.cursor_on[0] == "editor" else "Terminal")
    return Built(wd, "src/Components/Timer.js", text, s, centre(cur) if cur else (500, 500), cur.text if cur else "",
                 term, {"react_check": check} if check else {})


# ===================================================================================== pandas

PD_DATA = '''np.random.seed(42)
data = {
    "Department": np.random.choice(["Engineering", "Marketing", "Sales", "HR"], 50),
    "Employee": [f"Emp_{i}" for i in range(1, 51)],
    "Salary": np.random.randint(40000, 120000, 50),
    "Experience_Years": np.random.randint(1, 20, 50),
}
df = pd.DataFrame(data)
df.head()'''
PD_S2 = ['avg_salary = df.groupby("Department")["Salary"].mean()\navg_salary.head(2)',
         'avg_salary.sort_values()', 'avg_salary.reset_index()']
PD_S3 = ['grouped = df.groupby(["Department", "Experience_Years"])["Salary"].mean()\ngrouped.head(10)']

PD_CELLS = {
    "P1": ["import pandas as pd\nimport numpy as np", PD_DATA,
           'avg_salary = df.groupby("Department").mean()\navg_salary'],
    "P2": ["import pandas as pd\nimport numpy as np", PD_DATA, *PD_S2,
           'grouped = df.groupby("Department", "Experience_Years")["Salary"].mean()\ngrouped.head(10)'],
    "P3": ["import pandas as pd\nimport numpy as np", PD_DATA, *PD_S2, *PD_S3,
           'agg_result = df.groupby("Department").agg({"Salary": [mean, max, min], "Experience_Years": [mean, count]})\nagg_result'],
}
LINE_LIMIT = 30  # VS Code notebook.output.textLineLimit default: longer outputs show their first 30 lines + a notice
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _learner_paths(s: str) -> str:
    """This checkout's venv in tracebacks -> the learner's lesson venv (IPython prints ~-relative paths)."""
    import sys

    prefix = str(Path(sys.prefix))
    home = str(Path.home())
    for p in (prefix, prefix.replace(home, "~", 1)):
        s = s.replace(p + "/", "~/miyagi/lessons/pandas-groupby/.venv/")
    return s


def run_notebook(cells: list[str], path: Path) -> list[dict]:
    """Execute for real (nbclient, allow_errors) and save the .ipynb the way Jupyter does. -> cells as dicts."""
    import nbformat
    from nbclient import NotebookClient

    nb = nbformat.v4.new_notebook(cells=[nbformat.v4.new_code_cell(c) for c in cells])
    nb.metadata["kernelspec"] = {"name": "python3", "display_name": ".venv (Python 3.12.7)", "language": "python"}
    NotebookClient(nb, timeout=120, kernel_name="python3", allow_errors=True, cwd=str(path.parent)).execute()
    for c in nb.cells:  # learner's venv path in tracebacks, not this checkout's
        for o in c.outputs:
            if o.output_type == "error":
                o.traceback = [_learner_paths(t) for t in o.traceback]
    nbformat.write(nb, str(path))
    return [nb_cell_view(c) for c in nb.cells]


def nb_cell_view(c) -> dict:
    outs = []
    for o in c.outputs:
        if o.output_type == "error":
            outs.append("\n".join(ANSI.sub("", t) for t in o.traceback))
        elif o.output_type == "stream":
            outs.append(o.text.rstrip("\n"))
        elif "data" in o:
            outs.append(o.data.get("text/plain", ""))
    shown = []
    for t in outs:
        ls = t.splitlines()
        if len(ls) > LINE_LIMIT:
            ls = ls[:LINE_LIMIT] + ["Output is truncated. View as a scrollable element or open in a text editor. Adjust cell output settings..."]
        shown.append("\n".join(ls))
    err = next((o for o in c.outputs if o.output_type == "error"), None)
    return {"source": c.source, "count": c.execution_count, "outputs": shown,
            "error": f"{err.ename}: {err.evalue}" if err else None, "text": "\n".join(outs)}


def build_pandas(case: Case, root: Path) -> Built:
    wd = root / "pandas-groupby"
    wd.mkdir(parents=True, exist_ok=True)
    (wd / "requirements.txt").write_text("pandas>=2.0\nnumpy>=1.26\nipykernel>=6.29\njupyter>=1.0\n")
    cells = run_notebook(PD_CELLS[case.id], wd / "groupby.ipynb")
    text = (wd / "groupby.ipynb").read_text()
    return _pandas_screen(case, wd, cells, text)


def _pandas_screen(case: Case, wd: Path, cells: list[dict], text: str, after: bool = False) -> Built:
    s = Screen(front_app=case.front)
    shown = cells[1:] if case.id == "P1" else cells[-2:]  # scrolled to the cell being worked on
    s.vscode((0, MENU_H, 1150, 1117 - MENU_H), folder="pandas-groupby",
             tree=[(0, ".venv"), (0, "groupby.ipynb"), (0, "requirements.txt"), (0, "README.md")],
             tabs=["groupby.ipynb"], active="groupby.ipynb", file_path="groupby.ipynb", lines=[], lang="ipynb",
             notebook=shown)
    term = ["(.venv) learner@MacBook-Pro pandas-groupby % pip install -r requirements.txt",
            "Successfully installed pandas-3.1.1 numpy-2.3.4 ipykernel-7.1.0 jupyter-1.1.1",
            "(.venv) learner@MacBook-Pro pandas-groupby % "]
    s.terminal((1154, 640, 574, 1117 - 640), title="pandas-groupby — -zsh — 78×30", lines=term)
    cur = s.find(case.cursor_on[1], app="Code")
    return Built(wd, "groupby.ipynb", text, s, centre(cur) if cur else (500, 500), cur.text if cur else "", term,
                 {"cells": [{k: v for k, v in c.items() if k != "outputs"} for c in cells]})


def pandas_check(case: Case, new_text: str, wd: Path) -> dict:
    """Re-run the patched notebook top to bottom; the step's cell must run clean."""
    import nbformat

    try:
        nb = nbformat.reads(new_text, as_version=4)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"patched .ipynb is not valid JSON/nbformat: {e}"[:300]}
    tmp = wd / "_check.ipynb"
    cells = run_notebook([c.source for c in nb.cells], tmp)
    tmp.unlink(missing_ok=True)
    last = cells[-1]
    return {"ok": last["error"] is None, "error": last["error"], "output": last["text"][:400], "cells": cells}


# ===================================================================================== git

GENV = {"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1", "GIT_AUTHOR_DATE": "2026-11-14T10:00:00",
        "GIT_COMMITTER_DATE": "2026-11-14T10:00:00", "GIT_AUTHOR_NAME": "Learner", "GIT_AUTHOR_EMAIL": "learner@example.com",
        "GIT_COMMITTER_NAME": "Learner", "GIT_COMMITTER_EMAIL": "learner@example.com"}
PROMPT = "learner@MacBook-Pro git-rebase-lab % "

INDEX_BASE = "const express = require('express');\nconst app = express();\napp.use(express.json());\n\napp.listen(3000, () => console.log('Server running on port 3000'));\n"
LOGIN = "app.post('/login', (req, res) => {\n  console.log('DEBUG: LOGIN', req.body);\n  res.json({ ok: true });\n});\n\n"
LOGOUT = "app.post('/logout', (req, res) => {\n  // TODO: clear the session\n  res.json({ ok: true  });\n});\n\n"


def git(repo: Path, *args: str, env: dict | None = None, inp: str | None = None) -> tuple[int, str]:
    e = {k: v for k, v in os.environ.items() if k not in ("GIT_EDITOR", "GIT_SEQUENCE_EDITOR")}
    e.update(GENV)
    e.update(env or {})
    p = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, env=e, input=inp)
    return p.returncode, (p.stdout + p.stderr)


def tty_view(out: str) -> list[str]:
    """What a terminal shows: progress lines ("Rebasing (1/4)") are overwritten in place by the next text."""
    out = re.sub(r"Rebasing \(\d+/\d+\)\r?", "", out)
    return [ln.rstrip() for ln in out.rstrip("\n").splitlines()]


def make_repo(repo: Path, split: bool) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    w = lambda name, s: (repo / name).write_text(s)  # noqa: E731
    git(repo, "init", "-q", "-b", "main")
    w(".gitignore", "node_modules\n")
    w("index.js", INDEX_BASE)
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "Initial commit")
    git(repo, "checkout", "-qb", "feature/login")
    w("README.md", "# Login Demo\n\nA tiny Express app with login and logout endpoints.\n")
    if split:
        git(repo, "add", "README.md")
        git(repo, "commit", "-qm", "Add README")
    w("index.js", INDEX_BASE.replace("app.listen", LOGIN + "app.listen"))
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "Add login endpoint" if split else "Add README and login endpoint")
    w("index.js", INDEX_BASE.replace("app.listen", LOGIN + LOGOUT + "app.listen"))
    git(repo, "commit", "-qam", "Add logout endpoint")
    w("index.js", INDEX_BASE.replace("app.listen", LOGIN + LOGOUT.replace("  // TODO: clear the session\n", "").replace("true  }", "true }") + "app.listen"))
    git(repo, "commit", "-qam", "Cleanup")
    git(repo, "commit", "-q", "--allow-empty", "-m", "Add authentication middleware")


def todo_lines(repo: Path, n: int) -> list[tuple[str, str]]:
    _, out = git(repo, "log", "--reverse", "--format=%h %s", f"HEAD~{n}..HEAD")
    return [tuple(l.split(" ", 1)) for l in out.strip().splitlines()]  # type: ignore[misc]


def seq_editor(repo: Path, todo: str) -> dict:
    f = repo.parent / f"{repo.name}.todo"
    f.write_text(todo)
    ed = repo.parent / f"{repo.name}-editor.sh"
    ed.write_text(f'#!/bin/sh\ncp "{f}" "$1"\n')
    ed.chmod(0o755)
    return {"GIT_SEQUENCE_EDITOR": str(ed), "GIT_EDITOR": "true"}


def edit_todo_text(repo: Path) -> str:
    """The real `git rebase --edit-todo` buffer (todo + git's help block)."""
    cap = repo.parent / f"{repo.name}.captured"
    ed = repo.parent / f"{repo.name}-cap.sh"
    ed.write_text(f'#!/bin/sh\ncp "$1" "{cap}"\n')
    ed.chmod(0o755)
    git(repo, "rebase", "--edit-todo", env={"GIT_EDITOR": str(ed), "GIT_SEQUENCE_EDITOR": str(ed)})
    return cap.read_text()


def build_git(case: Case, root: Path) -> Built:
    repo = root / "git-rebase-lab"
    term: list[str] = []
    if case.id == "G2":  # s3: edit the README+login commit, forget `git add`
        make_repo(repo, split=False)
        t = todo_lines(repo, 4)
        todo = "\n".join(("edit " if i == 0 else "pick ") + f"{h} {s}" for i, (h, s) in enumerate(t)) + "\n"
        _, out = git(repo, "rebase", "--interactive", "HEAD~4", env=seq_editor(repo, todo))
        term += [PROMPT + "git rebase --interactive HEAD~4", *tty_view(out)]
        (repo / "index.js").write_text((repo / "index.js").read_text().replace("  console.log('DEBUG: LOGIN', req.body);\n", ""))
        _, out = git(repo, "rebase", "--continue")
        term += [PROMPT + "git rebase --continue", *tty_view(out), PROMPT]
        file, shown, lang, tab = "index.js", (repo / "index.js").read_text(), "js", "index.js"
    else:  # s5 on the split history (after s4)
        make_repo(repo, split=True)
        t = todo_lines(repo, 5)
        acts = {"G1": ["squash", "pick", "pick", "pick", "pick"], "G3": None}[case.id]
        if case.id == "G1":
            todo = "\n".join(f"{a} {h} {s}" for a, (h, s) in zip(acts, t)) + "\n"
        else:  # Cleanup moved up under the login commit, as squash
            order = [t[0], t[1], t[3], t[2], t[4]]
            todo = "\n".join(("squash " if s == "Cleanup" else "pick ") + f"{h} {s}" for h, s in order) + "\n"
        _, out = git(repo, "rebase", "--interactive", "HEAD~5", env=seq_editor(repo, todo))
        term += [PROMPT + "git rebase --interactive HEAD~5", *tty_view(out)]
        if case.id == "G1":
            shown = edit_todo_text(repo)
            term += [PROMPT + "git rebase --edit-todo", "hint: Waiting for your editor to close the file..."]
            file, lang, tab = ".git/rebase-merge/git-rebase-todo", "todo", "git-rebase-todo"
        else:
            _, out = git(repo, "rebase", "--continue")
            term += [PROMPT + "git rebase --continue", *tty_view(out), PROMPT]
            file, shown, lang, tab = "index.js", (repo / "index.js").read_text(), "js", "index.js"
    return _git_screen(case, repo, file, shown, lang, tab, term)


def _git_screen(case: Case, repo: Path, file: str, shown: str, lang: str, tab: str, term: list[str]) -> Built:
    s = Screen(front_app=case.front)
    lines = shown.splitlines()
    cur_line = next((i for i, l in enumerate(lines, 1) if re.search(case.cursor_on[1], l)), 1) if case.cursor_on[0] == "editor" else 1
    s.vscode((0, MENU_H, 940, 1117 - MENU_H), folder="git-rebase-lab",
             tree=[(0, ".gitignore"), (0, "index.js"), (0, "README.md")], tabs=[tab] if tab == "index.js" else ["index.js", tab],
             active=tab, file_path=tab if tab != "index.js" else "index.js", lines=lines, lang=lang, cursor_line=cur_line)
    s.terminal((944, MENU_H, 784, 1117 - MENU_H), title="git-rebase-lab — -zsh — 108×70", lines=term)
    cur = s.find(case.cursor_on[1], app="Code" if case.cursor_on[0] == "editor" else "Terminal")
    text = (repo / file).read_text() if (repo / file).is_file() else shown
    return Built(repo, file, text, s, centre(cur) if cur else (500, 500), cur.text if cur else "", term)


def git_check(case: Case, built: Built, new_text: str | None, command: str | None, sandbox: Path) -> dict:
    """Apply the fix in a copy of the stuck repo, finish the rebase as the learner would, check the history."""
    repo = sandbox / "git-rebase-lab"
    if repo.exists():
        shutil.rmtree(repo)
    shutil.copytree(built.workdir, repo, symlinks=True)
    log: list[str] = []
    if new_text is not None:
        (repo / built.file).write_text(new_text)
        log.append(f"# wrote {built.file}")
    for cmd in [c.strip() for c in re.split(r"&&|;|\n", command or "") if c.strip()]:
        if not cmd.startswith("git "):
            log.append(f"# skipped non-git command: {cmd}")
            continue
        import shlex

        _, out = git(repo, *shlex.split(cmd)[1:], env={"GIT_EDITOR": "true"})
        log += [PROMPT + cmd, *tty_view(out)]
    if (repo / ".git" / "rebase-merge").is_dir() and "--abort" not in (command or ""):
        if case.id == "G3" and new_text is not None and "git add" not in (command or ""):
            _, out = git(repo, "add", "index.js")  # the card's own instructions say to stage the resolution
            log.append(PROMPT + "git add index.js")
        for _ in range(4):  # a reorder can conflict again on the next pick: stop there and report it
            _, out = git(repo, "rebase", "--continue", env={"GIT_EDITOR": "true"})
            log += [PROMPT + "git rebase --continue", *tty_view(out)]
            if "Successfully rebased" in out or "CONFLICT" in out or "error" in out.lower():
                break
    in_progress = (repo / ".git" / "rebase-merge").is_dir()
    _, subjects = git(repo, "log", "--format=%s", "main..feature/login")
    subjects_l = subjects.strip().splitlines()[::-1]
    _, tip_index = git(repo, "show", "feature/login:index.js")
    res = {"in_progress": in_progress, "commits": subjects_l, "log": log}
    if case.id == "G1":
        res["ok"] = not in_progress and "Cleanup" not in subjects_l and subjects_l[:2] == ["Add README", "Add login endpoint"]
        res["why"] = "rebase finished, Cleanup squashed, README/login kept" if res["ok"] else "history not as intended"
    elif case.id == "G2":
        res["ok"] = not in_progress and len(subjects_l) == 4 and "DEBUG: LOGIN" not in tip_index
        res["why"] = "rebase finished; debug line gone from history" if res["ok"] else "rebase not finished or debug line kept"
    else:
        aborted = not in_progress and subjects_l == ["Add README", "Add login endpoint", "Add logout endpoint", "Cleanup", "Add authentication middleware"]
        clean = not in_progress and "<<<<<<<" not in tip_index and "app.post('/logout'" in tip_index and "Cleanup" not in subjects_l
        res["ok"] = clean
        res["recovered_by_abort"] = aborted
        res["why"] = "rebase finished cleanly with Cleanup squashed" if clean else ("aborted: back to the original history (redo needed)" if aborted else "not finished / markers left")
    res["terminal"] = log
    res["index_after"] = (repo / "index.js").read_text() if (repo / "index.js").is_file() else ""
    return res


# ===================================================================================== dispatch

def build(case: Case, root: Path) -> Built:
    root.mkdir(parents=True, exist_ok=True)
    return {"react": build_react, "pandas": build_pandas, "git": build_git}[case.topic](case, root)


def after_screen(case: Case, built: Built, new_text: str | None, check: dict) -> Screen:
    """The screen after the fix, from the real post-fix state (file, terminal/notebook output)."""
    if case.topic == "react":
        text = new_text if new_text is not None else built.file_text
        b = _react_screen(case, built.workdir, text, react_terminal(text) if check.get("ok") is not False or undefined_names(text) else list(CRA_OK), after=True)
        return b.screen
    if case.topic == "pandas":
        cells = check.get("cells") or []
        return _pandas_screen(case, built.workdir, cells, new_text or built.file_text, after=True).screen
    term = built.terminal + check.get("terminal", [])
    if built.file == "index.js":
        shown, lang, tab = check.get("index_after") or new_text or built.file_text, "js", "index.js"
    else:
        shown, lang, tab = new_text or built.file_text, "todo", "git-rebase-todo"
    return _git_screen(case, built.workdir, built.file, shown, lang, tab, term[-60:]).screen

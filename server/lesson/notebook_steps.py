"""A video's notebook lesson, done in the lesson's own notebook in VS Code (desktop test 10, Nov 15, CP3/CP4/CP6/CP10/CP15).

Kie Codes' TensorFlow lesson (demo/cache/lessons/5c0ea8a49f419487.json) makes `Untitled.ipynb` in a browser Jupyter: step 1
says "start Jupyter and create a new notebook", the later steps target `Untitled.ipynb`. Miyagi runs a Jupyter (not Colab)
lesson in VS Code, with the lesson's .venv as the kernel, so in test 10:
- step 1 said "Run source .venv/bin/activate && jupyter notebook in the VS Code terminal" (a browser Jupyter server: pointless);
- nothing ever made the notebook, so step 2's "Run the cell (Shift+Enter) in the notebook" had nothing to run;
- s5 / s7 said "In VS Code, create Untitled.ipynb and type …", the s2 hint "Open Untitled.ipynb in Jupyter or Colab".

use_lesson_notebook(graph) runs on every lesson load (a cached lesson too) and before a new build is cached, right after
use_lesson_venv (server/lesson/venv_steps.py). For a Jupyter notebook lesson that isn't a Colab one:
- the lesson's notebook gets a real name (lesson["notebook"]): the video's own name when it isn't an incidental
  Untitled*.ipynb, else from the lesson (mnist.ipynb when the steps use MNIST, else notebook.ipynb); Miyagi creates that
  empty notebook (.venv kernel) in the lesson folder when the lesson starts and opens it in VS Code;
- every `Untitled*.ipynb` (targets, file checks, instructions, hints, captions) names that notebook, "In your notebook"
  names it too;
- the step that starts a browser Jupyter server (`jupyter notebook` / `jupyter lab`) becomes the real setup: "Select the
  .venv kernel in mnist.ipynb". Its check ids stay (s1c2 now waits for VS Code's kernel picker to read ".venv (Python 3…",
  s1c3 for no kernel error), its box points at the notebook.
Idempotent: a second pass changes nothing. Returns the ids of the steps it changed."""

from __future__ import annotations

import re

VENV = ".venv"
UNTITLED = re.compile(r"\bUntitled[-_ ]?\d*\.ipynb\b", re.I)
_NB_FILE = re.compile(r"^[\w.-]+\.ipynb$")
_JUPYTER_SERVER = re.compile(r"^(?:jupyter(?:-|\s+)(?:notebook|lab)|python3?\s+-m\s+(?:notebook|jupyterlab|jupyter\s+(?:notebook|lab)))\b",
                             re.I)
_ACTIVATE = re.compile(r"^(?:source|\.)\s+[\w.~/-]+/bin/activate(?:\.\w+)?$")
_SPLIT = re.compile(r"\s*(?:&&|;|\n)\s*")
_YOUR_NOTEBOOK = re.compile(r"\b(in|to|into|from|open)\s+(?:your|the|a\s+new)\s+(?:jupyter\s+)?notebook\b", re.I)
_APP_WORDS = re.compile(r"\bin\s+(?:Jupyter(?:\s+Notebook)?\s+or\s+(?:Google\s+)?Colab|(?:Google\s+)?Colab\s+or\s+Jupyter(?:\s+Notebook)?)\b",
                        re.I)
# what VS Code's notebook kernel picker reads with the lesson's .venv selected: ".venv (Python 3.12.16)" (older builds:
# "Python 3.12.16 ('.venv': venv)"); never the Explorer's bare .venv folder
KERNEL_PATTERN = r"\.?venv\s*\(\s*Python\s*3|['‘’]\.?venv['‘’]\s*:\s*venv"
KERNEL_ERRORS = r"Failed\s+to\s+start\s+the\s+[Kk]ernel|[Kk]ernel\s+died|Traceback"
# a notebook named after what the lesson works on (MNIST -> mnist.ipynb), else notebook.ipynb
_TOPICS = ("fashion_mnist", "mnist", "cifar10", "cifar", "iris", "titanic", "imdb")


def _blob(graph: dict) -> str:
    out = [str((graph.get("lesson") or {}).get(k) or "") for k in ("title", "goal")]
    for st in graph.get("steps") or []:
        if isinstance(st, dict):
            out += [str(st.get(k) or "") for k in ("title", "instructions", "code", "run_command")]
    return " ".join(out)


def _files(step: dict) -> list[str]:
    return [str(x.get("file") or "") for x in (step.get("targets") or []) + (step.get("checks") or [])
            + (step.get("precision_checks") or []) if isinstance(x, dict)] + [str(step.get("file") or "")]


def is_colab(graph: dict) -> bool:
    blob = _blob(graph) + " " + " ".join(str(s.get("url") or "") for s in graph.get("sources") or [] if isinstance(s, dict))
    return "colab" in blob.lower()


def is_notebook(graph: dict) -> bool:
    if (graph.get("lesson") or {}).get("notebook"):
        return True
    if "jupyter" in _blob(graph).lower():
        return True
    return any(f.endswith(".ipynb") for st in graph.get("steps") or [] if isinstance(st, dict) for f in _files(st))


def notebook_name(graph: dict) -> str:
    """The lesson's notebook: lesson["notebook"] once set; the video's own .ipynb name unless it's an incidental
    Untitled*.ipynb; else after the lesson's data set (mnist.ipynb), else notebook.ipynb."""
    lesson = graph.get("lesson") or {}
    if isinstance(lesson.get("notebook"), str) and _NB_FILE.match(lesson["notebook"]):
        return lesson["notebook"]
    for st in graph.get("steps") or []:
        if isinstance(st, dict):
            for f in _files(st):
                name = f.rsplit("/", 1)[-1]
                if name.endswith(".ipynb") and _NB_FILE.match(name) and not UNTITLED.fullmatch(name):
                    return name
    blob = _blob(graph).lower()
    topic = next((t for t in _TOPICS if re.search(rf"\b{t}\b|\.{t}\b|{t}\.", blob)), None)
    return f"{'mnist' if topic == 'fashion_mnist' else topic}.ipynb" if topic else "notebook.ipynb"


def fix_copy(text: str, nb: str) -> str:
    """Learner copy for a VS Code notebook lesson: the video's Untitled.ipynb names the lesson's notebook, and never
    "in Jupyter or Colab" (the notebook is open in VS Code)."""
    if not text or not isinstance(text, str):
        return text
    out = UNTITLED.sub(nb, text)
    return _APP_WORDS.sub("in VS Code", out)


def _your_notebook(text: str, nb: str) -> str:
    return _YOUR_NOTEBOOK.sub(lambda m: f"{m.group(1)} {nb}", fix_copy(text, nb))


def _starts_server(step: dict) -> bool:
    cmd = str(step.get("run_command") or "")
    return any(_JUPYTER_SERVER.match(p) for p in _SPLIT.split(cmd.strip()) if p)


def _setup_step(step: dict, nb: str, libs: list[str]) -> None:
    """The step that started a browser Jupyter server: select the .venv kernel in the lesson's notebook instead."""
    rest = [p for p in _SPLIT.split(str(step.get("run_command") or "").strip())
            if p and not _JUPYTER_SERVER.match(p) and not _ACTIVATE.match(p)]
    if rest:
        step["run_command"] = " && ".join(rest)
    else:
        step.pop("run_command", None)
    step["title"] = f"Open {nb} with the {VENV} kernel"
    where = (f"{', '.join(libs[:-1])} and {libs[-1]}" if len(libs) > 1 else libs[0]) if libs else ""
    step["instructions"] = (
        f"Select the {VENV} kernel in {nb} (top right of the notebook in VS Code: Select Kernel, then {VENV}). "
        f"Miyagi made {nb} in your lesson folder and opened it in VS Code"
        + (f"; the setup card installs {where} into the lesson's {VENV}" if where else "")
        + ", so there is no Jupyter server to start. If the kernel already reads " + VENV + ", you're set.")
    step["hints"] = [f"Click Select Kernel at the top right of {nb}, then Python Environments, then {VENV}.",
                     f"Pick {VENV}, not another Python: the lesson's packages are installed only there."]
    step["common_mistakes"] = [f"Running {nb} on another Python kernel, where the lesson's packages are not installed."]
    step["targets"] = [{"app": "Code", "file": nb, "caption": f"Select the {VENV} kernel here"}]
    checks = []
    for c in step.get("checks") or []:
        c = dict(c)
        pat = str(c.get("pattern") or "")
        if c.get("type") == "screen_contains" and re.search(r"localhost|jupyter|127\\?\.0", pat, re.I):
            c.update(label=f"Notebook kernel is {VENV}", pattern=KERNEL_PATTERN)
            c.pop("app", None)
        elif c.get("type") == "screen_absent" and str(c.get("app") or "").lower() == "terminal":
            c.update(label="No kernel errors", pattern=KERNEL_ERRORS)
            c.pop("app", None)
        checks.append(c)
    step["checks"] = checks
    step["file"] = nb


def use_lesson_notebook(graph: dict) -> list[str]:
    """Rewrite `graph` in place (see the module doc). -> ids of the steps it changed."""
    if not isinstance(graph, dict) or not is_notebook(graph) or is_colab(graph):
        return []
    lesson = graph.setdefault("lesson", {})
    nb = notebook_name(graph)
    lesson["notebook"] = nb
    libs = [k for k in (lesson.get("libraries") or {}) if isinstance(k, str) and k.strip() and k.lower() != "jupyter"]
    changed: list[str] = []
    for step in graph.get("steps") or []:
        if not isinstance(step, dict):
            continue
        before = repr(step)
        if _starts_server(step):
            _setup_step(step, nb, libs)
        for k in ("instructions", "details", "action", "title"):
            if isinstance(step.get(k), str):
                step[k] = _your_notebook(step[k], nb) if k != "title" else fix_copy(step[k], nb)
        for k in ("hints", "common_mistakes"):
            if isinstance(step.get(k), list):
                step[k] = [fix_copy(h, nb) if isinstance(h, str) else h for h in step[k]]
        for key in ("targets", "checks", "precision_checks"):
            for x in step.get(key) or []:
                if not isinstance(x, dict):
                    continue
                if isinstance(x.get("file"), str) and UNTITLED.fullmatch(x["file"].rsplit("/", 1)[-1]):
                    x["file"] = nb
                for k in ("caption", "label"):
                    if isinstance(x.get(k), str):
                        x[k] = fix_copy(x[k], nb)
        if isinstance(step.get("file"), str) and UNTITLED.fullmatch(step["file"].rsplit("/", 1)[-1]):
            step["file"] = nb
        if repr(step) != before:
            changed.append(step.get("id") or "?")
    return changed


def empty_notebook() -> dict:
    """An empty notebook (one empty code cell) on the lesson's .venv kernel (what VS Code writes for a venv kernel)."""
    return {"cells": [{"cell_type": "code", "execution_count": None, "id": "miyagi-first-cell", "metadata": {},
                       "outputs": [], "source": []}],
            "metadata": {"kernelspec": {"display_name": VENV, "language": "python", "name": "python3"},
                         "language_info": {"name": "python"}},
            "nbformat": 4, "nbformat_minor": 5}

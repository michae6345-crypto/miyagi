"""Curated "Just teach me" lessons: written by hand, served instantly, no lesson build (no model call to build them).

One today: build a neural network from scratch (1-4-4-1, NumPy, learns y = sin(x) on [-pi, pi]), made by
scripts/make_nn_demo.py: demo/cache/lessons/text-nn-from-scratch.json + its cards and live network diagrams.

    lesson_for(goal)              the curated step graph for a "Just teach me" goal, or None (tight match, no LLM / fine-tune hits)
    prepare_folder(graph)         ~/miyagi/lessons/<slug>/ with nn.py's clean starter (an old attempt is kept in .miyagi-state)
    forget_saved(graph)           a fresh start drops this lesson's save (an engine restart mid-lesson), so it starts at step 1
    active(session)               this session runs a curated lesson (also after a resume: lesson.curated in the graph)
    prepare_step(session, step)   a run step says `python3 nn.py` (the drawer, the ▷ caption, the check row)
    run_for_me_command(session, step, cmd)   Run it for me runs the lesson .venv's python once NumPy is in it
    on_step_started / on_step_passed / after_evaluate / on_command_end   the pushed diagrams and the real run's numbers
    diagram_for_action / hint_card / explain_card   the Diagram button, the hint ladder and Explain, from the cached files

The off-track coach stays live (real Claude); the hints and Explain come from the files (instant, the same every time).
MIYAGI_CURATED=0 turns all of it off ("Just teach me" builds a lesson as before). DEMO=1 uses the same lesson.

Pushed diagrams (one `diagram` event each, kind "network" with data.frames, stepId = the current step): the app shows
them in the drawer's right-hand panel (adrian/shell PR #94). When a step starts: its own picture (forward pass, backprop,
training). After every run that prints losses, from the loop step on (Run it for me, the terminal, VS Code's ▶ Run Python
File): identical hidden neurons when the loss is stuck at STUCK_LOSS, else the learner's own run (their printed losses,
and their weights once nn.py prints them; a run that isn't the lesson's own run says the weights drawn are the lesson's).

The payload (data): layers [1, 4, 4, 1], labels {input: ["x"], output: ["y"]}, placement "drawer", activation "tanh"
(hidden; the output is linear), samples / targets (x = -π/2, 0, π/2 and sin(x)), target (sin(π/2) = 1), mode, frames:
    {epoch, loss, input: x, target: sin(x), W: [W1 1x4, W2 4x4, W3 4x1], b: [b1[4], b2[4], b3[1]], a: [[x], [4], [4], [y]]}
W[k][i][j] is the weight from neuron i of layer k to neuron j of layer k+1; `a` is every neuron's activation for that
frame's input (the app fires the neurons from it). Train frames all fire x = π/2 (the panel's prediction climbs to its
target 1); forward frames are the same weights once per sample, π/2 last (the frame the app keeps up).
"""

from __future__ import annotations

import ast
import asyncio
import copy
import json
import logging
import math
import os
import re
import time
from pathlib import Path
from typing import Any

from . import config

log = logging.getLogger("orchestrator.curated")

KEY = "nn-from-scratch"
LESSON_FILE = config.DEMO_CACHE / "lessons" / "text-nn-from-scratch.json"
STARTER_FILE = config.REPO_ROOT / "demo" / "nn-start.py"
FILE = "nn.py"
LAYERS = (1, 4, 4, 1)
TRAIN_STEP, TEST_STEP = "nn4", "nn6"  # the run steps: training (the stuck moment), and the run that prints the weights
# All weights 0: every hidden neuron outputs tanh(0) = 0 and gets the same (zero) update, so the output stays 0 for every
# x -> MSE = mean(sin(x)^2) over the lesson's 50 points (linspace(-pi, pi, 50)) = 49/100.
STUCK_LOSS = 0.49
LOSS_RX = re.compile(r"epoch\s+(?P<step>\d+)\s+loss\s+(?P<value>[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)")
WEIGHT_RX = re.compile(r"^\s*(?P<name>W1|b1|W2|b2|W3|b3)\b\s*[=:]?\s*(?P<rest>(?:array\()?\[.*)$")
# W<k> is (layer k-1) x (layer k), the way nn.py's X @ W1 uses it; b<k> is layer k's biases.
SHAPES = {f"{p}{k}": ((LAYERS[k - 1], LAYERS[k]) if p == "W" else (LAYERS[k],))
          for k in range(1, len(LAYERS)) for p in ("W", "b")}
SIZES = {name: math.prod(shape) for name, shape in SHAPES.items()}
ADOPT_AFTER_S = 1.0  # Run it for me's own wait polls every 0.3 s: it takes its runs first
# python3 nn.py, .venv/bin/python nn.py, python3 ./nn.py, tut run python nn.py, and VS Code's ▷ Run Python File (the
# Python extension types the interpreter and the file as absolute paths, quoted when they hold a space:
# "/a b/.venv/bin/python" "/a b/nn.py"). Never `cat nn.py`, never nn.pyc / nn.py.bak.
RUN_RX = re.compile(rf"""(?:^|[\s/"'])python[\d.]*["']?\s+(?:-\S+\s+)*["']?(?:[^"'\s]*/|"[^"]*/|'[^']*/)?"""
                    rf"""{re.escape(FILE)}(?![\w.])""")
LOOP_STEP = "nn3"  # the step that writes the training loop: from here on a run prints losses the panel can draw

# ---------------------------------------------------------------------------------------------------------- matching

# A neural network, by name. "nn" alone counts ("build a nn"); nn.Module-style PyTorch goals fall to _NOT.
_NN = re.compile(r"\bneural[\s-]*net(?:work)?s?\b|\bnn\b|\bmulti[\s-]*layer[\s-]*perceptrons?\b|\bmlp\b", re.I)
# Anything that asks for a different lesson: another architecture, a framework, an LLM, a dataset or task, another
# language. Tight on purpose: the curated lesson is a NumPy 1-4-4-1 net that learns y = sin(x) (so XOR is another task).
_NOT = re.compile(
    r"\b(?:llms?|gpt\w*|chat\s*gpt|chatbots?|transformers?|attention|bert|language\s+models?|tokeni[sz]\w*|xor|"
    r"fine[\s-]*tun\w*|finetun\w*|lora|rlhf|diffusion|gans?|autoencoders?|vaes?|"
    # conv: never "converge" / "convert"; graph: a graph neural network, never "graph the loss"
    r"cnns?|conv(?:olution\w*|nets?|s)?|rnns?|lstms?|grus?|recurrent|graph\s+(?:neural|nets?|networks?|conv\w*)|"
    r"gnns?|spiking|bayesian|quantum|evolution\w*|"
    r"reinforcement|q[\s-]*learning|dqn|pytorch|torch|tensorflow|keras|jax|flax|scikit|sklearn|"
    r"mnist|cifar|imagenet|images?|vision|digits?|style\s+transfer|text|sentiment|nlp|speech|audio|"
    r"stocks?|prices?|forecast\w*|time\s+series|physics|pinns?|"
    r"javascript|typescript|js|node\.?js|rust|java|golang|swift|kotlin|julia|ruby|php|excel|"
    r"pure\s+python|without\s+numpy|no\s+numpy|no[\s-]*code)\b|(?<!\w)(?:c\+\+|c#)(?!\w)",
    re.I)


def enabled() -> bool:
    return os.environ.get("MIYAGI_CURATED", "1").strip().lower() not in ("0", "false", "off", "no")


def _edits(a: str, b: str) -> int:
    """Edit distance with a swap of two neighbours counting as one edit ("nueral" -> "neural": 1)."""
    d = [[i + j if i * j == 0 else 0 for j in range(len(b) + 1)] for i in range(len(a) + 1)]
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (a[i - 1] != b[j - 1]))
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[-1][-1]


def _typo_nn(goal: str) -> bool:
    """"neural network" typed fast on stage: "nueral network", "neural netowrk", "nerual net"."""
    words = re.findall(r"[a-z]+", goal.lower())
    net = lambda w: w in ("net", "nets") or min(_edits(w, "network"), _edits(w, "networks")) <= 2  # noqa: E731
    return any(_edits(w, "neural") <= 1 and net(nxt) for w, nxt in zip(words, words[1:]))


def matches(goal: str) -> bool:
    """Is this "Just teach me" goal "build a neural network" (and nothing more specific)?"""
    g = " ".join(str(goal or "").split())
    return bool(g) and (_NN.search(g) is not None or _typo_nn(g)) and _NOT.search(g) is None


def lesson_for(goal: str, force: bool = False) -> dict | None:
    """The curated step graph for `goal`, or None (no match, MIYAGI_CURATED=0, or the file is missing).
    force: whatever the goal (the launcher's Demo option, stage.py)."""
    if not force and (not enabled() or not matches(goal)):
        return None
    try:
        g = json.loads(LESSON_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        log.warning("curated lesson unreadable (%s): building one instead", e)
        return None
    g.setdefault("lesson", {})["curated"] = KEY
    g["lesson"]["mode"] = "lesson"
    g["lesson"]["asked"] = str(goal).strip()  # what the learner typed (the lesson keeps its own goal and folder)
    for st in g.get("steps", []):
        st.pop("video", None)
    return g


def active(session: Any) -> bool:
    lesson = (getattr(session, "graph", None) or {}).get("lesson") or {}
    return (enabled() or bool(lesson.get("stage"))) and lesson.get("curated") == KEY  # a Demo lesson: always


# ---------------------------------------------------------------------------------------------------------- folder

def _starter() -> str:
    try:
        return STARTER_FILE.read_text(encoding="utf-8")
    except OSError:
        return "import numpy as np\n"


def prepare_folder(graph: dict, fresh: bool = False) -> str:
    """The lesson's folder with a clean nn.py, ready at once (never asks Claude for starter files).

    LIVE: <lessons root>/<slug>-<hash> (the same folder every time, so a NumPy installed into its .venv stays). A fresh
    start puts the clean starter back; the learner's earlier nn.py is kept in <lessons root>/.miyagi-state/attempts/.
    TUT_WORKDIR pins the folder (dev, scripts/miyagi-nn-demo.sh): nn.py is only created there when it's missing or empty,
    unless fresh (a Demo lesson's restart: the clean starter back there too, the last attempt kept).
    Blocking (file I/O): run it in a thread."""
    pinned = bool(os.environ.get("TUT_WORKDIR"))
    try:
        from server.workspace import paths
    except Exception:  # noqa: BLE001 - S2 missing: the engine's own default folder
        paths = None
    if pinned:
        folder = config.default_workdir()
    elif paths is not None:
        folder = paths.lessons_root() / paths.folder_name(graph)
    else:
        folder = config.lesson_workdir("", (graph.get("lesson") or {}).get("title") or "neural-net")
    folder = Path(folder).expanduser().resolve()
    folder.mkdir(parents=True, exist_ok=True)
    starter, p = _starter(), folder / FILE
    try:
        cur = p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""
    except OSError:
        cur = ""
    if not cur.strip():
        p.write_text(starter, encoding="utf-8")
    elif cur != starter and (not pinned or fresh):
        root = paths.lessons_root() if paths is not None else folder.parent
        keep = root / ".miyagi-state" / "attempts" / folder.name / f"nn-{time.strftime('%Y%m%d-%H%M%S')}.py"
        try:
            keep.parent.mkdir(parents=True, exist_ok=True)
            keep.write_text(cur, encoding="utf-8")
            p.write_text(starter, encoding="utf-8")
            log.info("curated lesson: fresh nn.py (the last attempt is in %s)", keep)
        except OSError as e:
            log.warning("could not keep the last nn.py (%s): leaving it as it is", e)
    if not pinned:
        _folder_extras(folder, graph)
    return str(folder)


def forget_saved(graph: dict) -> bool:
    """Typing the goal again starts the curated lesson over: prepare_folder puts the clean starter back, so a save of
    THIS lesson (made before an engine restart, its resume card not answered) must not restore a later step onto that
    blank nn.py. Built lessons don't need this (their files are never reset). The resume card's Continue still goes
    back to the saved step: it reloads the saved graph and never comes through here. Blocking (file I/O)."""
    lid = (graph.get("lesson") or {}).get("id")
    try:
        from server.sessions import store

        saved = store.load()
        if lid and saved is not None and saved.get("lessonId") == lid:
            store.clear()
            log.info("curated lesson: starting over (dropped the save at step %s)", saved.get("stepIndex"))
            return True
    except Exception:  # noqa: BLE001 - never blocks the lesson
        log.exception("curated lesson: could not drop the old save")
    return False


def _folder_extras(folder: Path, graph: dict) -> None:
    """README, VS Code settings, S2's state file (so S2 never re-scaffolds this folder with Claude) and the setup
    check's requirements (python + numpy, so the "Install NumPy" card needs no Claude call). Best effort."""
    readme = folder / "README.md"
    if not readme.exists():
        readme.write_text("# A neural net from scratch\n\nA 1-4-4-1 neural network in NumPy that learns the curve "
                          "y = sin(x). Miyagi walks you through nn.py one step at a time.\n", encoding="utf-8")
    try:
        from server.workspace import core

        core._write_vscode_settings(folder)
        sp = folder / ".vscode" / "settings.json"
        cur = json.loads(sp.read_text()) if sp.exists() else {}
        if isinstance(cur, dict) and "python.defaultInterpreterPath" not in cur:
            # Pylance resolves `import numpy` once Miyagi installed it into the lesson's .venv (the setup card)
            cur["python.defaultInterpreterPath"] = "${workspaceFolder}/.venv/bin/python"
            sp.parent.mkdir(parents=True, exist_ok=True)
            sp.write_text(json.dumps(cur, indent=2) + "\n")
        sf = core._state_file(folder)
        if not sf.exists():
            sf.parent.mkdir(parents=True, exist_ok=True)
            sf.write_text(json.dumps({
                "scaffolded": True, "created": time.strftime("%Y-%m-%dT%H:%M:%S"), "curated": KEY,
                "lesson_id": (graph.get("lesson") or {}).get("id"), "title": (graph.get("lesson") or {}).get("title"),
                "lesson_kind": "code", "stack": "python", "summary": "A NumPy neural network that learns y = sin(x).",
                "setup": [], "open_file": FILE, "files": [FILE], "readme": "README.md",
                "git": {"init": False, "ops": 0, "commits": 0}, "dropped": [], "model": "", "error": "", "seconds": 0,
            }, indent=1))
    except Exception:  # noqa: BLE001
        log.exception("curated lesson: VS Code settings / state file")
    try:
        from server.workspace import setup

        cache = setup._cache_file(graph)
        if not cache.exists():
            cache.parent.mkdir(parents=True, exist_ok=True)
            tool = {"needed": True, "min_version": "", "binary": "", "import_name": "", "pip_name": "", "brew": "",
                    "brew_cask": False, "url": ""}
            cache.write_text(json.dumps({
                "editor": {"needed": True, "why": "You write nn.py in VS Code."},
                "tools": [
                    {**tool, "tool": "python", "kind": "runtime", "why": "Runs nn.py.", "min_version": "3.9",
                     "binary": "python3", "brew": "python", "url": "https://www.python.org/downloads/"},
                    {**tool, "tool": "numpy", "kind": "python_package", "why": "Every array and weight in nn.py.",
                     "import_name": "numpy", "pip_name": "numpy", "brew": "numpy", "url": "https://numpy.org/install/"},
                ]}, indent=1))
    except Exception:  # noqa: BLE001
        log.exception("curated lesson: requirements cache")


# ---------------------------------------------------------------------------------------------------------- steps

def _venv_python(workdir: str | Path) -> Path | None:
    """The lesson .venv's python, only when NumPy is installed in it (a .venv without NumPy runs nn.py with python3)."""
    venv = Path(workdir) / ".venv"
    p = venv / "bin" / "python"
    if not p.exists():
        return None
    return p if any(venv.glob("lib/python*/site-packages/numpy/__init__.py")) else None


def prepare_step(session: Any, step: dict) -> None:
    """A run step's command is the learner's: `python3 nn.py` (the drawer, "Run python3 nn.py in the VS Code terminal",
    the "Ran python3 nn.py" row, the completion screen). The lesson folder's VS Code settings put .venv/bin first on
    PATH in its terminals (server.workspace.core.PYTHON_TERMINAL), so python3 there is the .venv's, and VS Code's ▷
    runs the .venv's python (python.defaultInterpreterPath); a run of either counts (checks.command_matches). t6: this
    used to become `.venv/bin/python nn.py` once NumPy was installed; a step saved like that is put back."""
    if not active(session) or not (step.get("run_command") or "").strip():
        return
    cmd = f"python3 {FILE}"
    if step.get("run_command") != cmd and RUN_RX.search(step["run_command"]):
        step["run_command"] = cmd
        step["code"] = cmd


def run_for_me_command(session: Any, step: dict, cmd: str) -> str:
    """What Run it for me types for a run step's `cmd`: `.venv/bin/python nn.py` once the setup card installed NumPy
    into the lesson's .venv (a terminal VS Code made before that, or restored from an earlier session, may still find
    a python3 without NumPy), else `cmd` as it is. Only for the lesson's own `python nn.py` run."""
    if (not active(session) or len((cmd or "").strip().splitlines()) != 1 or not RUN_RX.search(cmd)
            or _venv_python(session.workdir) is None):
        return cmd
    return f".venv/bin/python {FILE}"


def _cache_json(*parts: str) -> dict | None:
    try:
        return json.loads(config.DEMO_CACHE.joinpath(*parts).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _state(session: Any) -> dict:
    st = getattr(session, "_curated", None)
    lesson_id = ((session.graph or {}).get("lesson") or {}).get("id")
    if not isinstance(st, dict) or st.get("lesson") != lesson_id or st.get("epoch") != getattr(session, "lesson_epoch", 0):
        st = {"lesson": lesson_id, "epoch": getattr(session, "lesson_epoch", 0), "runs": {}, "losses": [],
              "final": None, "stuck": False, "stuck_step": None}
        session._curated = st
    return st


# ---------------------------------------------------------------------------------------------------------- the run

def _numbers(text: str) -> list[float] | None:
    """A printed array (a .tolist() list or NumPy's repr, one or more lines) as a flat list of floats."""
    s = text.strip()
    if s.startswith("array("):
        s = s[len("array("):].rsplit(")", 1)[0]
    s = re.sub(r",\s*dtype=\w+\)?\s*$", "", s)
    s = re.sub(r"(?<=[\d.\]])\s+(?=[-+\d.\[])", ",", s)  # NumPy's repr: "[[ 6.39  0.72]\n [ 6.26 ...]]"
    try:
        val = ast.literal_eval(s)
    except (ValueError, SyntaxError, MemoryError, RecursionError):
        return None

    def flat(v: Any) -> list[float]:
        if isinstance(v, (list, tuple)):
            return [x for item in v for x in flat(item)]
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return [float(v)]
        raise ValueError(v)

    try:
        out = flat(val)
    except ValueError:
        return None
    return out if all(math.isfinite(x) for x in out) else None


def _rows(vals: list[float], shape: tuple[int, ...]) -> list:
    """A flat row-major list as `shape` (2-D: rows of columns; 1-D: as is), -0.0 printed by NumPy read as 0.0."""
    vals = [v + 0.0 for v in vals]
    if len(shape) == 1:
        return vals
    cols = shape[1]
    return [vals[r * cols:(r + 1) * cols] for r in range(shape[0])]


def parse_output(lines: list[str]) -> dict:
    """{losses: [(epoch, loss)], final: {W: [W1, W2, W3], b: [b1, b2, b3]} | None} from a run's output: the loop's
    `epoch N  loss X` lines, and W1 / b1 / W2 / b2 / W3 / b3 when nn.py prints them (lists or NumPy arrays, any line
    layout). W<k> comes back as rows (W1 1x4, W2 4x4, W3 4x1: W[k][i][j] is neuron i of layer k -> neuron j of layer
    k+1), b<k> flat (4, 4, 1)."""
    losses: dict[int, float] = {}
    weights: dict[str, list[float]] = {}
    pending: tuple[str, str] | None = None
    for raw in [str(x) for x in lines or []]:
        if pending is not None:  # a NumPy array printed over several lines
            name, buf = pending
            buf += " " + raw.strip()
            if buf.count("[") <= buf.count("]"):
                vals = _numbers(buf)
                if vals is not None:
                    weights[name] = vals
                pending = None
            else:
                pending = (name, buf)
            continue
        if (m := LOSS_RX.search(raw)) is not None:
            try:
                v = float(m.group("value"))
            except ValueError:
                continue
            if math.isfinite(v):
                losses[int(m.group("step"))] = v
            continue
        if (m := WEIGHT_RX.match(raw)) is not None:
            name, rest = m.group("name"), m.group("rest").strip()
            if rest.count("[") > rest.count("]"):
                pending = (name, rest)
                continue
            vals = _numbers(rest)
            if vals is not None:
                weights[name] = vals
    final = None
    if all(len(weights.get(k) or []) == n for k, n in SIZES.items()):
        n_w = len(LAYERS) - 1
        final = {"W": [_rows(weights[f"W{k}"], SHAPES[f"W{k}"]) for k in range(1, n_w + 1)],
                 "b": [_rows(weights[f"b{k}"], SHAPES[f"b{k}"]) for k in range(1, n_w + 1)]}
    return {"losses": sorted(losses.items()), "final": final}


def is_stuck(losses: list[tuple[int, float]]) -> bool:
    """The loss sat at STUCK_LOSS (0.49) the whole run: every hidden neuron is the same neuron (the weights started
    equal, e.g. zeros: each outputs tanh(0) = 0, so the network answers 0 for every x)."""
    return (len(losses) >= 2 and max(e for e, _ in losses) >= 1000
            and all(abs(v - STUCK_LOSS) <= 0.0015 for _, v in losses))


def _run_lines(run: Any) -> list[str]:
    return [str(x) for x in (getattr(run, "output_tail", None) or [])]


def _read_run(session: Any) -> tuple[str, dict] | None:
    """The newest run of this step that printed something we can draw: (run id + a fingerprint, parsed). A run's
    exact output (VS Code's terminal via the companion, Run it for me, `tut run`) beats loss values read off the
    screen; a screen run only has its losses."""
    runs = list(getattr(session, "step_runs", None) or [])
    for run in reversed([r for r in runs if not r.run_id.startswith("screen-")]):
        parsed = parse_output(_run_lines(run))
        if parsed["losses"] or parsed["final"]:
            return f"{run.run_id}:{len(parsed['losses'])}:{bool(parsed['final'])}", parsed
    ran = getattr(session, "_step_ran", None)
    if callable(ran) and not ran():  # t6: loss lines on screen when the step began (a restored terminal) aren't theirs
        return None
    for run in reversed([r for r in runs if r.run_id.startswith("screen-")]):
        pts = [(int(s), float(v)) for s, v in (run.metrics or {}).get("loss") or [] if v is not None]
        if pts:
            dedup = dict(pts)  # the screen re-reads the same lines: one value per epoch, the latest
            losses = sorted(dedup.items())
            return f"{run.run_id}:{json.dumps(losses)}", {"losses": losses, "final": None}
    return None


# ---------------------------------------------------------------------------------------------------------- frames

def _ref(name: str) -> dict | None:
    return _cache_json("diagrams", f"{name}.json")


def _with_frames(d: dict, frames: list[dict], mode: str | None = None, caption: str | None = None) -> dict:
    d = copy.deepcopy(d)
    d["data"]["frames"] = frames
    if mode:
        d["data"]["mode"] = mode
    if caption:
        d["caption"] = caption
    return d


def activations(W: list, b: list, x: float) -> list[list[float]] | None:
    """Every neuron's activation for input x: [[x], tanh layer 1, tanh layer 2, linear output] (rounded to 4 places).
    W[k][i][j] is neuron i of layer k -> neuron j of layer k+1. None when the weights don't fit together."""
    try:
        acts = [[float(x)]]
        for k, (Wk, bk) in enumerate(zip(W, b)):
            prev = acts[-1]
            z = [float(bk[j]) + sum(prev[i] * float(Wk[i][j]) for i in range(len(prev))) for j in range(len(bk))]
            acts.append([math.tanh(v) for v in z] if k < len(W) - 1 else z)
    except (TypeError, IndexError, ValueError, KeyError):
        return None
    return [[round(v, 4) + 0.0 for v in layer] for layer in acts]


def _fire(f: dict, x: float) -> dict:
    """`f` with its input set to x, its target sin(x) (the panel's "Prediction … target …") and `a` computed from its
    own weights (in place)."""
    f["input"] = round(float(x), 4)
    f["target"] = round(math.sin(float(x)), 4) + 0.0
    a = activations(f.get("W") or [], f.get("b") or [], x)
    if a is not None:
        f["a"] = a
    return f


def _lerp(a: Any, b: Any, t: float) -> Any:
    """a -> b at t, element by element through nested lists."""
    if isinstance(a, list):
        return [_lerp(x, y, t) for x, y in zip(a, b)]
    return round(float(a) + (float(b) - float(a)) * t, 4)


def _sample_xs(ref: list[dict], samples: list | None) -> list[float]:
    """The inputs frames cycle through: data.samples ([[x], ...]), else the reference frames' own inputs, else 0."""
    xs = [s[0] if isinstance(s, (list, tuple)) else s for s in samples or []]
    if not xs:
        xs = list(dict.fromkeys(f["input"] for f in ref if isinstance(f.get("input"), (int, float))))
    return [float(x) for x in xs if isinstance(x, (int, float))] or [0.0]


def forward_frames(frame: dict, samples: list | None) -> list[dict]:
    """The trained network answering every sample: `frame`'s weights once per input x (each with its own `a`)."""
    return [_fire(copy.deepcopy(frame), x) for x in _sample_xs([frame], samples)]


def live_frames(ref: list[dict], losses: list[tuple[int, float]], final: dict | None,
                samples: list | None = None) -> tuple[list[dict], bool]:
    """The training frames for the learner's run -> (frames, same_as_reference).

    Their run printed the same losses as the reference run (the lesson's code, seed 0): it IS the reference run, so
    every reference frame is theirs (the weights are exact), with their printed losses and, when nn.py printed them,
    their final weights (its `a` recomputed from them). Otherwise one frame per printed epoch with their loss; the
    weights end on theirs when printed (drawn as a straight path from the reference start), else they are the
    reference's. Each new frame fires the reference's own input (x = π/2: the app shows its prediction next to
    data.target while it tweens frames, so the input never changes under it) and its `a` comes from its weights."""
    ref = [f for f in ref if isinstance(f, dict) and "epoch" in f]
    if not ref:
        return [], False
    by_epoch = {int(f["epoch"]): f for f in ref}
    # The epochs both printed (every 1,000 in the reference) must agree; a loop printing every 100 or every epoch is
    # still the reference run when they do (at least two shared epochs: epoch 0 alone only says the start matches).
    shared = [(e, v) for e, v in losses if e in by_epoch]
    same = len(shared) >= 2 and all(abs(float(by_epoch[e]["loss"]) - v) <= max(6e-4, 0.02 * v) for e, v in shared)
    xs = _sample_xs(ref, samples)
    if same or not losses:
        frames = copy.deepcopy(ref)
        real = dict(losses)
        for f in frames:
            if int(f["epoch"]) in real:
                f["loss"] = real[int(f["epoch"])]
        if final:
            last = frames[-1]
            last["W"], last["b"] = copy.deepcopy(final["W"]), copy.deepcopy(final["b"])
            _fire(last, last.get("input", xs[(len(frames) - 1) % len(xs)]))
        return frames, same
    last = max(e for e, _ in losses)
    nearest = lambda e: min(ref, key=lambda f: abs(int(f["epoch"]) - e))  # noqa: E731
    start = ref[0]
    x_ref = ref[-1].get("input")
    x_ref = float(x_ref) if isinstance(x_ref, (int, float)) else xs[-1]
    frames = []
    for e, v in losses:
        if final:
            t = e / last if last else 1.0
            f = {"epoch": e, "loss": v, "W": _lerp(start["W"], final["W"], t), "b": _lerp(start["b"], final["b"], t)}
        else:
            n = nearest(e)
            f = {"epoch": e, "loss": v, "W": copy.deepcopy(n["W"]), "b": copy.deepcopy(n["b"])}
        frames.append(_fire(f, x_ref))
    return frames, False


def _fmt(v: float) -> str:
    return f"{v:.4f}" if v >= 1e-4 else f"{v:.1e}"


def _train_caption(losses: list[tuple[int, float]], final: dict | None, same: bool = True) -> str:
    """Never passes the lesson's weights off as theirs: a run that isn't the lesson's own run (another seed, lr, ...)
    only has its printed losses (and, once nn.py prints them, its end weights)."""
    if not losses:
        return "Your trained network, from the weights it printed."
    (e0, v0), (e1, v1) = losses[0], losses[-1]
    tail = (" Drawn from the weights it printed." if same else " It ends on the weights it printed.") if final \
        else "" if same else " The lines are the lesson's own weights until nn.py prints yours."
    return f"Your run: loss {_fmt(v0)} at epoch {e0} → {_fmt(v1)} at epoch {e1}.{tail}"


def _live(session: Any, kind: str) -> dict | None:
    """The diagram drawn from the learner's latest training run: 'train' (weights moving, loss falling), 'forward'
    (the trained network answering -π/2, 0 and π/2) or 'stuck' (identical hidden neurons, their flat loss)."""
    st = _state(session)
    losses, final = st.get("losses") or [], st.get("final")
    if kind == "stuck" or st.get("stuck"):  # a stuck run (also after Skip): the picture is the stuck one
        base = _ref(f"{TRAIN_STEP}-gradients")
        if base is None:
            return None
        frames, _ = live_frames(base["data"]["frames"], losses, None, base["data"].get("samples"))
        v = losses[-1][1] if losses else STUCK_LOSS
        return _with_frames(base, frames, caption=f"Your run: the loss sits at {v:.4f}. All eight hidden neurons are "
                                                  "the same neuron: same start, same update, so nothing moves.")
    base = _ref(f"{TRAIN_STEP}-network")
    if base is None:
        return None
    if not losses and not final:
        return None
    samples = base["data"].get("samples")
    frames, same = live_frames(base["data"]["frames"], losses, final, samples)
    if not frames:
        return None
    if kind == "forward":
        return _with_frames(base, forward_frames(frames[-1], samples), mode="forward",
                            caption="Your trained network: x goes in, sin(x) comes out. Drawn from the weights it printed."
                            if final else "Your trained network: x goes in, sin(x) comes out." if same
                            else "The lesson's trained network drawing sin(x): run nn.py to draw yours.")
    return _with_frames(base, frames, mode="train", caption=_train_caption(losses, final, same))


def _step_ids(session: Any) -> list[str]:
    return [s.get("id") for s in getattr(session, "steps", None) or []]


def _after(session: Any, step: dict, sid: str) -> bool:
    """Is `step` this step or a later one?"""
    ids = _step_ids(session)
    try:
        return ids.index(step.get("id")) >= ids.index(sid)
    except ValueError:
        return False


def step_diagram(session: Any, step: dict, kind: str | None = None) -> dict | None:
    """What the right-hand panel / the Diagram button shows for this step now. kind "gradients" asks for the stuck
    picture; None picks: the stuck picture while this step's run is stuck, else the learner's own run once there is
    one (the loop, training and test steps), else the step's precomputed network. Always with stepId."""
    sid = step.get("id")
    st = _state(session)
    d = None
    if kind == "gradients" or (kind is None and st.get("stuck") and st.get("stuck_step") == sid):
        d = _live(session, "stuck") or _ref(f"{sid}-gradients")
    elif _after(session, step, LOOP_STEP) and (st.get("losses") or st.get("final")):
        d = _live(session, "forward" if sid == TEST_STEP else "train")
    if d is None:
        d = _ref(f"{sid}-network")
    if d is None:
        return None
    d = dict(d)
    d["stepId"] = sid
    return d


# ---------------------------------------------------------------------------------------------------------- hooks

async def _push(session: Any, step: dict, d: dict | None) -> None:
    if d is None or session.step is not step or getattr(session, "passed", False):
        return  # a passed step's own push is on_step_passed's
    key = json.dumps([d.get("caption"), d["data"].get("mode"), len(d["data"].get("frames") or []),
                      (d["data"].get("frames") or [{}])[-1].get("loss")], sort_keys=True)
    pushed = _state(session).setdefault("pushed", {})
    if pushed.get(step.get("id")) == key:
        return  # the panel already shows this one
    pushed[step.get("id")] = key
    log.info("curated: push %s diagram (%s) for %s", d["data"].get("mode"), (d.get("caption") or "")[:50], step.get("id"))
    await session.emit("diagram", d)


async def on_step_started(session: Any, step: dict) -> None:
    """Every step of the curated lesson starts with its network in the right-hand panel."""
    if not active(session) or session.step is not step:
        return
    _state(session).setdefault("pushed", {}).pop(step.get("id"), None)  # a new start (Back, resume) pushes again
    await _push(session, step, step_diagram(session, step))


async def on_step_passed(session: Any, step: dict) -> None:
    """The training run passed: the panel shows their run (weights moving, loss falling); the next step's start
    pushes it again under that step's id, so it stays up. The last run passed: their trained network answering,
    drawn from the weights it printed (it stays up: there is no next step)."""
    if not active(session) or step.get("id") not in (TRAIN_STEP, TEST_STEP):
        return
    _ingest_latest(session)
    if step.get("id") == TEST_STEP:  # the last step: their network answering, from the weights nn.py printed
        d = _live(session, "forward")
        if d is not None and _state(session).get("final"):
            d["caption"] = ("Your network draws sin(x): -1, 0, 1 at -π/2, 0, π/2. Drawn from the weights your nn.py "
                            "printed.")
    else:
        d = _live(session, "train")
    if d is not None:
        d["stepId"] = step.get("id")
        log.info("curated: %s passed (%s)", step.get("id"), d.get("caption"))
        await session.emit("diagram", d)


def _ingest_latest(session: Any) -> bool:
    """Read this step's newest run into the lesson's live numbers. True when it was new."""
    got = _read_run(session)
    if got is None:
        return False
    fp, parsed = got
    st = _state(session)
    if st["runs"].get(fp):
        return False
    st["runs"][fp] = True
    if parsed["losses"]:
        was = st.get("stuck") and st.get("stuck_step")
        st["losses"] = parsed["losses"]
        st["stuck"] = is_stuck(parsed["losses"])
        st["stuck_step"] = session.step.get("id") if (st["stuck"] and session.step) else None
        if st["stuck"] and was != st["stuck_step"]:  # just got stuck: the stuck ladder starts at its first hint
            st["stuck_hints_from"] = int(getattr(session, "hint_level", 0) or 0)
    if parsed["final"]:
        st["final"] = parsed["final"]
    return True


def after_evaluate(session: Any, step: dict, trigger: str) -> None:
    """After a run (or new loss lines on screen): the right-hand panel follows the learner's real run. Stuck at
    STUCK_LOSS -> identical hidden neurons; otherwise their losses (and weights) redraw the step's network."""
    if not active(session) or trigger not in ("run_end", "metric", "check") or not _after(session, step, LOOP_STEP):
        return
    if not _ingest_latest(session):
        return
    session._spawn(_push(session, step, step_diagram(session, step)))


async def on_command_end(session: Any, ev: dict) -> None:
    """VS Code's own report of a command that ended (the companion's command_end, shell integration): a run of
    nn.py in the lesson's folder becomes a run with its exact output, exit code and loss lines, so the run steps
    pass on what the terminal really printed (not OCR) and the diagrams use the real numbers."""
    step = getattr(session, "step", None)
    if not active(session) or step is None or getattr(session, "passed", False):
        return
    c = ev.get("command") if isinstance(ev, dict) else None
    if not isinstance(c, dict):
        return
    line = str(c.get("commandLine") or "")
    if not RUN_RX.search(line):  # python3 nn.py, .venv/bin/python nn.py, tut run python nn.py (never `cat nn.py`)
        return
    mine = os.path.realpath(session.workdir)
    cwd = os.path.realpath(str(c["cwd"])) if c.get("cwd") else ""
    here = (cwd == mine or cwd.startswith(mine + os.sep) or str(session.workdir) in line
            or (not cwd and any(os.path.realpath(str(f)) == mine for f in ev.get("folders") or [])))
    started = (c.get("startedAt") or 0) / 1000 or float(ev.get("received") or 0)
    if not here or started < getattr(session, "_step_wall_t0", 0.0) - 1.0:
        return
    from . import stage  # (stage imports this module)

    if stage.on(session):  # a Demo lesson: the terminal's own output stays on screen, the recorded run grades it
        if stage._is_run(session, step):  # (a run typed on a typing step passes nothing)
            await stage.run(session, step, typed=True)
        return
    # The same id as Run it for me's own wait for this run (session._terminal_run_result, which also posts the result
    # card): give it a moment; whichever ingests first owns the run, the other stands back.
    run_id = f"vscode-{c.get('id')}-{c.get('startedAt')}" if c.get("id") is not None \
        else f"vscode-{ev.get('seq') or int(time.time() * 1000)}"
    await asyncio.sleep(ADOPT_AFTER_S)
    if session.step is not step or getattr(session, "passed", False) or run_id in (getattr(session, "runs", None) or {}):
        return
    lines = [str(x) for x in c.get("outputTail") or []]
    code = c.get("exitCode")
    if not isinstance(code, int):  # shell integration couldn't tell: a crash in the output says it failed
        try:
            from server.checks.evaluator import run_output

            code = 1 if run_output(lines)[0] else 0
        except Exception:  # noqa: BLE001
            code = 0
    parsed = parse_output(lines)
    await session.ingest({"kind": "run_started", "run_id": run_id, "command": line,
                          "cwd": c.get("cwd") or session.workdir, "started_at": started})
    if lines:
        await session.ingest({"kind": "output", "run_id": run_id, "lines": lines[-200:]})
    if parsed["losses"]:
        await session.ingest({"kind": "metrics", "run_id": run_id,
                              "metrics": [{"step": e, "name": "loss", "value": v} for e, v in parsed["losses"]]})
    await session.ingest({"kind": "run_ended", "run_id": run_id, "exit_code": code})


def diagram_for_action(session: Any, step: dict, want: str) -> dict | None:
    """The Diagram button / ⌃⌥D: the step's network (with the learner's run once there is one), or the stuck picture
    (want "gradients", or while the loss is stuck). None for a concept picture (text names a concept): S4 draws it."""
    if not active(session) or (want and want not in ("network", "gradients")):
        return None
    _ingest_latest(session)
    return step_diagram(session, step, want or None)


def _stuck_here(session: Any, step: dict) -> bool:
    st = _state(session)
    return bool(st.get("stuck")) and st.get("stuck_step") == step.get("id")


def hint_card(session: Any, step: dict, level: int) -> dict | None:
    """The step's cached hint ladder (instant; the same every time). On the training step, while the loss is stuck at
    STUCK_LOSS, the stuck ladder (look at how W1, W2 and W3 start -> start them random), from its first hint even when
    the learner used hints before the run got stuck. None past the ladder's end: the live coach takes the next hint."""
    if not active(session):
        return None
    sid = step.get("id")
    if _stuck_here(session, step):  # counted from the moment it got stuck (hints used before don't skip the ladder)
        name = f"{sid}-stuck-hint{max(0, level - int(_state(session).get('stuck_hints_from') or 0))}"
    else:
        name = f"{sid}-hint{level}"
    card = _cache_json("cards", f"{name}.json")
    if card is None:
        return None
    card = dict(card)
    card["stepId"] = sid
    return card


def explain_card(session: Any, step: dict) -> dict | None:
    """Explain (no question, no selection): the step's cached card; while stuck, why zeros can't learn."""
    if not active(session):
        return None
    sid = step.get("id")
    card = (_cache_json("cards", f"{sid}-stuck-explain.json") if _stuck_here(session, step) else None) \
        or _cache_json("cards", f"{sid}-explain.json")
    if card is None:
        return None
    card = dict(card)
    card["stepId"] = sid
    return card

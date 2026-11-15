"""Skill map for the lesson-complete card (mockup 10, "Your skills"): what this lesson taught, on one track.

    skill_map(graph, results)        -> {track, headline, nodes, edges, cross, next}   (pure: no I/O, no model call)
    session_results(session)         -> {"passed": [stepId], "skipped": [stepId]} from a live Session
    attach_skill_map(card, session)  -> the completion card with card["skillMap"] (kind "complete", or the lesson finished)

Hook: server/orchestrator/lesson_end.card() (branch claude/t5fix-lesson-end) returns its card through
attach_skill_map(card, s), which covers its three senders (send_later, Check / Skip after the end, the reconnect replay).

The engine supplies the data; the app draws it (concept nodes left to right on the track, mastered = check,
learning = ring, next = dashed; `cross` = dashed links from another track, the "shared idea"). Contract:
SkillMap in shared/contracts/events.ts (card.skillMap) and events.py.

Two sources:
- The curated "build a neural network" lesson (lesson.curated == "nn-from-scratch", or a goal that names a neural
  network and nothing more specific): a hand-written Machine learning track. Each concept names the curated steps
  that teach it; another neural-network lesson maps a concept to the steps whose text names it, and a concept no
  step teaches is left out.
- Any other lesson: a track named by the lesson (lesson.track / stack, "... in React", its libraries, else its
  title); one node per step (a run step joins the step it runs); next from lesson.nextTopics / learnFirst.

Progress is never invented: a node is mastered only when every step behind it passed (results), learning when one
of them was skipped, next when none of that is known (results None, or not reached yet).
"""

from __future__ import annotations

import logging
import re
from typing import Any, Iterable

log = logging.getLogger("lesson.skillmap")

MASTERED, LEARNING, NEXT = "mastered", "learning", "next"
MAX_NEXT = 5
MAX_LABEL_WORDS, MAX_DETAIL_WORDS = 6, 12

# ------------------------------------------------------------------------------------- the curated NN lesson
NN_KEY = "nn-from-scratch"  # server/orchestrator/curated.py KEY (lesson.curated in the graph)
NN_TRACK = "Machine learning"
NN_LEAD = "You built a neural network from scratch."

# (id, label, detail, the curated steps that teach it, words that name it in another NN lesson's steps)
_NN_CONCEPTS: tuple[tuple[str, str, str, tuple[str, ...], str], ...] = (
    ("numpy-arrays", "NumPy arrays", "X, y and every weight are arrays", ("nn1",),
     r"np\.(?:array|zeros|random)|\bnumpy\b|\barrays?\b"),
    ("neurons-activations", "Neurons & activations", "sigmoid squishes a weighted sum", ("nn1",),
     r"\bsigmoid\b|\brelu\b|\btanh\b|\bactivations?\b|\bneurons?\b"),
    ("forward-pass", "Forward pass", "sigmoid(X @ W1 + b1), layer by layer", ("nn1",),
     r"\bforward\b"),
    ("loss-mse", "Loss (MSE)", "mean((out - y) ** 2)", ("nn2", "nn3"),
     r"\bmse\b|mean[\s_-]*squared|\(\s*out\s*-\s*y\s*\)\s*\*\*\s*2"),
    ("backpropagation", "Backpropagation", "the chain rule, one layer at a time", ("nn2",),
     r"\bbackprop\w*|\bbackward\b|\bchain rule\b"),
    ("training-loop", "Training loop (gradient descent)", "W -= lr * dW, epoch after epoch", ("nn3", "nn4"),
     r"\btraining loop\b|\bfor epoch\b|\bgradient descent\b"),
    ("symmetry-breaking", "Symmetry breaking (random init)", "random weights, so the neurons differ", ("nn1", "nn4"),
     r"random\.randn|\brandom (?:init\w*|weights)\b|\bsymmetr\w*"),
)

# (id, label, detail, launcher goal). Goals never re-open the curated XOR lesson (curated.matches() is False).
_NN_NEXT: tuple[tuple[str, str, str, str], ...] = (
    ("lr-optimizers", "Learning rate & optimizers (Adam)", "how big each step downhill is",
     "implement gradient descent with momentum and Adam from scratch in NumPy"),
    ("mini-batches", "Mini-batches", "learn from a few examples at a time",
     "train a model with mini-batch gradient descent in NumPy"),
    ("classification", "Classification (softmax + cross-entropy)", "pick one of many classes",
     "build a softmax classifier with cross-entropy loss in NumPy"),
    ("pytorch-autograd", "PyTorch autograd", "backprop done for you",
     "build a neural network in PyTorch"),
    ("cnns", "CNNs", "networks that see images",
     "build a CNN that classifies MNIST digits in PyTorch"),
)

_NN_CROSS: tuple[dict[str, str], ...] = (
    {"track": "Math", "label": "Derivatives (chain rule)", "to": "backpropagation",
     "note": "backprop multiplies slopes back through the layers"},
    {"track": "Math", "label": "Matrix multiply", "to": "forward-pass",
     "note": "X @ W1 runs every hidden neuron at once"},
)

# A goal that names a neural network and nothing more specific (mirrors server/orchestrator/curated.matches, kept
# local so this module stays import-light: curated.py's config import reads .env).
_NN_GOAL = re.compile(r"\bneural[\s-]*net(?:work)?s?\b|\bnn\b|\bmulti[\s-]*layer[\s-]*perceptrons?\b|\bmlp\b", re.I)
_NN_OTHER = re.compile(
    r"\b(?:llms?|gpt\w*|transformers?|attention|bert|language\s+models?|fine[\s-]*tun\w*|lora|diffusion|gans?|"
    r"autoencoders?|vaes?|cnns?|conv\w*|rnns?|lstms?|recurrent|graph|gnns?|reinforcement|pytorch|torch|tensorflow|"
    r"keras|jax|scikit|sklearn|mnist|cifar|images?|vision|text|nlp|speech|audio|pinns?|javascript|typescript|rust|"
    r"java|swift|julia|no[\s-]*code)\b",
    re.I)

# ------------------------------------------------------------------------------------------ track names
_PRETTY = {
    "python": "Python", "py": "Python", "javascript": "JavaScript", "js": "JavaScript", "typescript": "TypeScript",
    "ts": "TypeScript", "node": "Node.js", "nodejs": "Node.js", "node.js": "Node.js", "react": "React",
    "nextjs": "Next.js", "next.js": "Next.js", "vue": "Vue", "svelte": "Svelte", "html": "HTML", "css": "CSS",
    "sql": "SQL", "sqlite": "SQLite", "postgres": "Postgres", "postgresql": "Postgres", "git": "Git", "rust": "Rust",
    "go": "Go", "golang": "Go", "swift": "Swift", "swiftui": "SwiftUI", "java": "Java", "kotlin": "Kotlin",
    "c++": "C++", "cpp": "C++", "c#": "C#", "ruby": "Ruby", "rails": "Rails", "php": "PHP", "bash": "Bash",
    "shell": "Shell", "docker": "Docker", "flask": "Flask", "django": "Django", "fastapi": "FastAPI",
    "numpy": "NumPy", "pandas": "pandas", "matplotlib": "Matplotlib", "pytorch": "PyTorch", "torch": "PyTorch",
    "tensorflow": "TensorFlow", "excel": "Excel", "sheets": "Google Sheets", "figma": "Figma",
}
_LEAD_VERB = re.compile(r"^(?:build|make|create|write|code|learn|teach me(?: how)? to)\s+(?:(?:a|an|the|your)\s+)?",
                        re.I)
_TRAILING_TECH = re.compile(r"\b(?:in|with|using)\s+([\w.+#-]+(?:\s+[\w.+#-]+)?)\s*$", re.I)


# =================================================================================================== public
def skill_map(graph: dict, results: dict | None = None) -> dict:
    """The skill map for `graph` (a step graph). results: which steps the learner passed / skipped, either
    {"passed": [stepId], "skipped": [stepId]} or {stepId: "passed" | "skipped"}. None = nothing is known, so
    nothing shows as mastered (a step's own "status" field still counts)."""
    graph = graph if isinstance(graph, dict) else {}
    lesson = graph.get("lesson") if isinstance(graph.get("lesson"), dict) else {}
    steps = [s for s in graph.get("steps") or [] if isinstance(s, dict) and s.get("id")]
    status = _statuses(steps, results)
    if _is_nn(lesson, steps):
        return _nn_map(lesson, steps, status)
    return _lesson_map(lesson, steps, status)


def session_results(session: Any) -> dict:
    """{"passed", "skipped"} step ids from a live Session: every step before the current one, plus the current one
    once it has passed (the last step just passed when the completion card goes out). Skipped steps never pass."""
    steps = [s for s in (getattr(session, "steps", None) or []) if isinstance(s, dict) and s.get("id")]
    idx = getattr(session, "idx", -1)
    idx = idx if isinstance(idx, int) else -1
    done = steps[: idx + 1] if getattr(session, "passed", False) else steps[: max(idx, 0)]
    skipped = set(getattr(session, "skipped_steps", None) or [])
    return {"passed": [s["id"] for s in done if s["id"] not in skipped],
            "skipped": [s["id"] for s in done if s["id"] in skipped]}


def finished(session: Any) -> bool:
    """The lesson ran to its end: phase done, its last step passed, nothing more being built (the same test as
    server/orchestrator/lesson_end.finished)."""
    return (getattr(session, "phase", None) == "done" and isinstance(getattr(session, "graph", None), dict)
            and bool(getattr(session, "passed", False)) and not getattr(session, "waiting_more", False))


def attach_skill_map(card: dict, session: Any) -> dict:
    """The completion card with card["skillMap"] added: a card of kind "complete", or any card sent once the lesson
    has finished (lesson_end.card() sends kind "step"). Mid-lesson cards come back unchanged. Never raises: a skill
    map that can't be made leaves the card as it was."""
    if not isinstance(card, dict) or card.get("skillMap"):
        return card
    if card.get("kind") != "complete" and not finished(session):
        return card
    graph = getattr(session, "graph", None)
    if not isinstance(graph, dict) or not graph.get("steps"):
        return card
    try:
        return {**card, "skillMap": skill_map(graph, session_results(session))}
    except Exception:  # noqa: BLE001 - the congratulations card must go out without its map rather than not at all
        log.exception("skill map failed; sending the completion card without it")
        return card


# ================================================================================================= helpers
def _statuses(steps: list[dict], results: dict | None) -> dict[str, str]:
    """stepId -> "passed" | "skipped" for the steps we know about (others are absent: not reached / unknown)."""
    out: dict[str, str] = {}
    for st in steps:  # a graph that carries its own step status (resume / tests)
        if st.get("status") in ("passed", "skipped"):
            out[st["id"]] = st["status"]
    if not isinstance(results, dict):
        return out
    if isinstance(results.get("passed"), (list, tuple, set)) or isinstance(results.get("skipped"), (list, tuple, set)):
        for sid in results.get("passed") or ():
            out[str(sid)] = "passed"
        for sid in results.get("skipped") or ():
            out[str(sid)] = "skipped"  # skipped wins: Skip is never a pass
        return out
    for sid, v in results.items():
        if v in ("passed", "skipped"):
            out[str(sid)] = v
        elif v is True:
            out[str(sid)] = "passed"
    return out


def _state(step_ids: Iterable[str], status: dict[str, str]) -> str:
    got = [status.get(s) for s in step_ids]
    if got and all(g == "passed" for g in got):
        return MASTERED
    if any(g == "skipped" for g in got):
        return LEARNING
    return NEXT


def _is_nn(lesson: dict, steps: list[dict]) -> bool:
    if lesson.get("curated") == NN_KEY:
        return True
    if lesson.get("curated"):  # another curated lesson: its own track, not this one
        return False
    goal = " ".join(str(lesson.get(k) or "") for k in ("asked", "goal", "title"))
    return bool(_NN_GOAL.search(goal)) and not _NN_OTHER.search(goal)


def _step_text(st: dict) -> str:
    return " ".join(str(st.get(k) or "") for k in ("title", "what", "why", "instructions", "code"))


def _nn_map(lesson: dict, steps: list[dict], status: dict[str, str]) -> dict:
    ids = {s["id"] for s in steps}
    nodes: list[dict] = []
    for cid, label, detail, curated_steps, words in _NN_CONCEPTS:
        cover = [s for s in curated_steps if s in ids]
        if not cover:  # not the curated graph: the steps whose text names the concept
            rx = re.compile(words, re.I)
            cover = [s["id"] for s in steps if rx.search(_step_text(s))]
        if not cover:
            continue  # no step taught it: never shown as learned
        state = _state(cover, status)
        nodes.append(_node(cid, label, state, detail if state != LEARNING else _skipped_detail(cover, steps, status)))
    taught = len(nodes)
    for nid, label, detail, _goal in _NN_NEXT:
        nodes.append(_node(nid, label, NEXT, detail))
    present = {n["id"] for n in nodes}
    cross = [dict(c) for c in _NN_CROSS if c["to"] in present]
    nxt = [{"title": label, "goal": goal} for _nid, label, _d, goal in _NN_NEXT]
    all_mastered = taught > 0 and all(n["state"] == MASTERED for n in nodes[:taught])
    lead = NN_LEAD if all_mastered else _lead(lesson, nodes[:taught])
    return _finish(NN_TRACK, lead, nodes, cross, nxt)


def _lesson_map(lesson: dict, steps: list[dict], status: dict[str, str]) -> dict:
    groups: list[dict] = []  # {label, detail, steps}
    for i, st in enumerate(steps):
        if st.get("kind") == "run" and groups:
            groups[-1]["steps"].append(st["id"])  # "Run it" proves the step before it
            continue
        label = _words(str(st.get("keyIdea") or st.get("concept") or st.get("title") or st.get("what")
                           or f"Step {i + 1}"), MAX_LABEL_WORDS)
        same = next((g for g in groups if g["label"].lower() == label.lower()), None)
        if same is not None:
            same["steps"].append(st["id"])
            continue
        what = _words(str(st.get("what") or ""), MAX_DETAIL_WORDS)
        groups.append({"label": label, "detail": what if what and what.lower() != label.lower() else "",
                       "steps": [st["id"]]})
    nodes: list[dict] = []
    taken: set[str] = set()
    for g in groups:
        state = _state(g["steps"], status)
        detail = g["detail"] if state != LEARNING else _skipped_detail(g["steps"], steps, status)
        nodes.append(_node(_slug(g["label"], taken), g["label"], state, detail))
    taught = len(nodes)
    nxt = _next_topics(lesson)
    for item in nxt:
        nodes.append(_node(_slug(item["title"], taken), _words(item["title"], MAX_LABEL_WORDS), NEXT,
                           item.pop("_detail", "")))
    track = _track_name(lesson)
    return _finish(track, _lead(lesson, nodes[:taught]), nodes, [], nxt)


def _next_topics(lesson: dict) -> list[dict]:
    """lesson.nextTopics (strings or {title, goal}) then lesson.learnFirst (gaps not covered yet), at most MAX_NEXT."""
    out: list[dict] = []
    seen: set[str] = set()

    def add(title: Any, goal: Any = None, detail: str = "") -> None:
        t = " ".join(str(title or "").split())
        if not t or t.lower() in seen or len(out) >= MAX_NEXT:
            return
        seen.add(t.lower())
        out.append({"title": t, "goal": " ".join(str(goal or t).split()), "_detail": detail})

    for item in lesson.get("nextTopics") or []:
        if isinstance(item, str):
            add(item)
        elif isinstance(item, dict):
            add(item.get("title") or item.get("goal"), item.get("goal") or item.get("query"),
                _words(str(item.get("why") or item.get("detail") or ""), MAX_DETAIL_WORDS))
    passed = {p.get("id") for p in lesson.get("prerequisites") or [] if isinstance(p, dict) and p.get("status") == "passed"}
    for item in lesson.get("learnFirst") or []:
        if isinstance(item, dict) and item.get("covers") not in passed:
            mins = item.get("minutes")
            add(item.get("title"), item.get("title"), f"{mins} min" if isinstance(mins, int) and mins > 0 else "")
    return out


def _track_name(lesson: dict) -> str:
    for key in ("track", "stack"):
        v = lesson.get(key)
        if isinstance(v, str) and v.strip():
            return _pretty(v.strip().split("/")[-1].strip())
    title = " ".join(str(lesson.get("title") or lesson.get("goal") or "").split())
    m = _TRAILING_TECH.search(title)
    if m:
        return _pretty(m.group(1))
    libs = lesson.get("libraries")
    names = list(libs) if isinstance(libs, (dict, list)) else []
    for name in names:
        if isinstance(name, str) and name.lower() in _PRETTY:
            return _PRETTY[name.lower()]
    name = _LEAD_VERB.sub("", title).strip()
    return (name[:1].upper() + name[1:]) if name else "This lesson"


def _pretty(name: str) -> str:
    key = name.strip().lower()
    if key in _PRETTY:
        return _PRETTY[key]
    if " " in key and key.split()[0] in _PRETTY:  # "react hooks" -> React
        return _PRETTY[key.split()[0]]
    return name[:1].upper() + name[1:]


def _lead(lesson: dict, taught: list[dict]) -> str:
    title = " ".join(str(lesson.get("title") or lesson.get("goal") or "this lesson").split())
    if re.match(r"^(?:a|an|the)\s", title, re.I):
        title = title[:1].lower() + title[1:]
    if taught and any(n["state"] == MASTERED for n in taught):
        return f"You finished {title}."
    return f"You reached the end of {title}."


def _finish(track: str, lead: str, nodes: list[dict], cross: list[dict], nxt: list[dict]) -> dict:
    counts = [(sum(n["state"] == s for n in nodes), word)
              for s, word in ((MASTERED, "mastered"), (LEARNING, "learning"), (NEXT, "up next"))]
    tally = ", ".join(f"{c} {w}" for c, w in counts if c)
    where = "" if track.lower() in lead.lower() else f" in {track}"  # "...a to-do app in React. 3 mastered." once
    headline = f"{lead} {tally}{where}." if tally else lead
    edges = [{"from": a["id"], "to": b["id"]} for a, b in zip(nodes, nodes[1:])]
    return {"track": track, "headline": headline, "nodes": nodes, "edges": edges, "cross": cross,
            "next": [{"title": n["title"], "goal": n["goal"]} for n in nxt]}


def _node(nid: str, label: str, state: str, detail: str = "") -> dict:
    n = {"id": nid, "label": label, "state": state}
    if detail:
        n["detail"] = detail
    return n


def _skipped_detail(step_ids: list[str], steps: list[dict], status: dict[str, str]) -> str:
    pos = {s["id"]: i + 1 for i, s in enumerate(steps)}
    nums = [str(pos[s]) for s in step_ids if status.get(s) == "skipped" and s in pos]
    if not nums:
        return ""
    return f"Step {nums[0]} skipped" if len(nums) == 1 else f"Steps {', '.join(nums)} skipped"


def _words(text: str, n: int) -> str:
    w = " ".join(text.split()).split(" ")
    out = " ".join(w[:n]).rstrip(".,;:")
    return out if len(w) <= n else out + "…"


def _slug(text: str, taken: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40].strip("-") or "node"
    sid, k = base, 2
    while sid in taken:
        sid, k = f"{base}-{k}", k + 1
    taken.add(sid)
    return sid

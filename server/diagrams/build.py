"""diagrams.build(): Claude draws one small explanatory diagram for the current step.

Input is the step (title, instructions, targets...) plus what is on screen (code / OCR text) and the
learner's question. Output is a `diagram` event payload:

  kind "network"  the existing contract shape (layers / activation / derivatives / residual), used only
                  when the code on screen gives the real layer sizes. Renders in the app today.
  kind "graph"    nodes + edges with a layout family (flow, sequence, tree, data, architecture, git) and
                  grid positions from layout.py. PROPOSED contract addition, see README.md.

`gradients` and `heatmap` are never produced here: they need real training numbers, which come from
the run (metrics), not from a language model.

No canned fallback: any failure raises DiagramError with a message that is safe to show.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import time
from collections import OrderedDict
from typing import Any

from . import layout

log = logging.getLogger("diagrams")

MODEL = os.environ.get("DIAGRAMS_MODEL", "claude-sonnet-5-5")  # steadier than Haiku 5.5 here: 3-5 s vs 2-8 s
FALLBACK_BETA = "server-side-fallback-2026-07-01"
EFFORT = os.environ.get("DIAGRAMS_EFFORT", "low")
TIMEOUT_S = float(os.environ.get("DIAGRAMS_TIMEOUT", "15"))
MAX_NODES = 12
CODE_CHARS = 6000
SCREEN_CHARS = 3000
LAYOUTS = ("flow", "sequence", "tree", "data", "architecture", "git")


class DiagramError(RuntimeError):
    """build() could not produce a real diagram. `str(e)` is safe to show the learner."""


# ---------------------------------------------------------------- prompt + schema

SYSTEM = """You draw ONE small explanatory diagram for a learner following a coding tutorial step by step in an overlay tutor. It pops up beside their editor when they press Option-D, so it must make the idea behind the CURRENT step clear at a glance.

Choose the form that fits the topic:
- kind "network": ONLY for a neural network whose layer sizes are explicitly written in the code or step (e.g. `layers = [2, 32, 32, 1]`, `nn.Linear(2, 32)`). network.layers = those exact sizes, input first, output last. activation, inputs and output names come from the code. derivatives = at most 2 autograd derivatives the step computes, written like "u_t" or "u_xx". residual = the PDE residual written compactly (<= 13 chars, e.g. "u_t - u_xx"). If the step is about a network but the sizes are not visible, use kind "graph" with layout "architecture" instead.
- kind "graph" for everything else, with one layout:
  - "flow": control or data flow, pipelines, lifecycles (render -> effect -> cleanup; request -> handler -> DB). Edges follow the real order things happen; put conditions and "why" in node.detail or edge.label, not in extra nodes.
  - "sequence": messages between 2-5 participants over time (component <-> hook, client <-> server, local <-> remote). nodes = participants, left to right. edges = the messages IN TIME ORDER, each with a short label.
  - "tree": hierarchies (component tree, file tree, class hierarchy).
  - "data": how data changes shape (DataFrame -> groupby -> groups -> agg -> result). Put the shape or the real column names in node.detail.
  - "architecture": the layers or modules of a system or model.
  - "git": a commit graph. nodes = commits, oldest first. node.group = branch name. node.label = the short hash from the screen or "C1", "C2"... (<= 8 chars); node.detail = the commit message cut to <= 16 chars. edges = parent -> child (a merge has two parents). When commits are rewritten (rebase, amend, cherry-pick), put the originals on a lane named "<branch> (old)" and the copies on the branch, with a dashed edge from each original to its copy.

Rules:
- 4 to 10 nodes; never more than 12. Fewer, clearer nodes beat completeness. Keep any left-to-right chain to 5 nodes or fewer (branch or group instead of making it longer).
- Use the real names from the code and topic on screen: variables, functions, components, columns, branches. label <= 16 chars. detail <= 22 chars or "": what happens at that node in plain words ("checks b == 0", "returns a / b", "prints the result"), or a shape like "(N, 2)" or a value that APPEARS in the context. Never syntax trivia ("two equals signs", "ends with a colon", "uses parentheses").
- Never invent numbers, data values or results that are not in the context.
- emphasis = true on the 1-2 nodes or edges that carry the step's key idea; false elsewhere.
- Edge labels: a short verb phrase (<= 18 chars) or "".
- node.id: short unique slug. edge.from / edge.to must be node ids. group: "" unless the layout uses groups (git branches, or clusters you name in groups).
- title: 1-3 words naming the view, e.g. "Effect lifecycle", "Rebase", "Split-apply-combine".
- direction: "TB" for trees, "LR" otherwise.
- caption: ONE plain sentence of 12 words or fewer saying what to notice. If the learner asked a question, the caption answers it. Use the same names as the diagram.
Set whichever of network / graph you did not use to null."""

_NODE = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "label": {"type": "string"},
        "detail": {"type": "string"},
        "group": {"type": "string"},
        "shape": {"type": "string", "enum": ["box", "round", "circle", "data", "commit"]},
        "emphasis": {"type": "boolean"},
    },
    "required": ["id", "label", "detail", "group", "shape", "emphasis"],
    "additionalProperties": False,
}
_EDGE = {
    "type": "object",
    "properties": {
        "from": {"type": "string"},
        "to": {"type": "string"},
        "label": {"type": "string"},
        "style": {"type": "string", "enum": ["solid", "dashed"]},
        "emphasis": {"type": "boolean"},
    },
    "required": ["from", "to", "label", "style", "emphasis"],
    "additionalProperties": False,
}
SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": ["network", "graph"]},
        "caption": {"type": "string"},
        "network": {
            "anyOf": [
                {"type": "null"},
                {
                    "type": "object",
                    "properties": {
                        "layers": {"type": "array", "items": {"type": "integer"}},
                        "activation": {"type": "string"},
                        "inputs": {"type": "array", "items": {"type": "string"}},
                        "output": {"type": "string"},
                        "derivatives": {"type": "array", "items": {"type": "string"}},
                        "residual": {"type": "string"},
                    },
                    "required": ["layers", "activation", "inputs", "output", "derivatives", "residual"],
                    "additionalProperties": False,
                },
            ]
        },
        "graph": {
            "anyOf": [
                {"type": "null"},
                {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "layout": {"type": "string", "enum": list(LAYOUTS)},
                        "direction": {"type": "string", "enum": ["LR", "TB"]},
                        "nodes": {"type": "array", "items": _NODE},
                        "edges": {"type": "array", "items": _EDGE},
                        "groups": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {"id": {"type": "string"}, "label": {"type": "string"}},
                                "required": ["id", "label"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": ["title", "layout", "direction", "nodes", "edges", "groups"],
                    "additionalProperties": False,
                },
            ]
        },
    },
    "required": ["kind", "caption", "network", "graph"],
    "additionalProperties": False,
}


# ---------------------------------------------------------------- context -> prompt


def _screen_text(screen: Any) -> str:
    """Accepts `ScreenObservation.lines_by_app()` ({app: [lines]}), a list of lines, or a string."""
    if not screen:
        return ""
    if isinstance(screen, str):
        return screen
    if isinstance(screen, dict):
        parts = []
        for app, lines in screen.items():
            body = "\n".join(lines) if isinstance(lines, (list, tuple)) else str(lines)
            parts.append(f"[{app or 'screen'}]\n{body}")
        return "\n".join(parts)
    if isinstance(screen, (list, tuple)):
        return "\n".join(str(x) for x in screen)
    return str(screen)


def _question(context: dict) -> str:
    return str(context.get("question") or "").strip()


def _code(context: dict) -> str:
    return str(context.get("code") or "")


def user_prompt(step: dict, context: dict) -> str:
    lesson = context.get("lesson") or {}
    parts = []
    if lesson.get("title") or lesson.get("goal"):
        parts.append(f"Tutorial: {lesson.get('title', '')}" + (f" (goal: {lesson['goal']})" if lesson.get("goal") else ""))
    parts.append(f"Current step: {step.get('title', '')}")
    if step.get("instructions"):
        parts.append(f"What the learner does: {step['instructions']}")
    caps = [t.get("caption") for t in step.get("targets") or [] if t.get("caption")]
    if caps:
        parts.append("Key places: " + "; ".join(caps))
    topics = [e.get("topic") for e in step.get("explanations") or [] if e.get("topic")]
    if topics:
        parts.append("Concepts the video explains here: " + "; ".join(topics))
    if step.get("common_mistakes"):
        parts.append("Common mistakes: " + "; ".join(step["common_mistakes"][:3]))
    off = context.get("offtrack")
    if isinstance(off, dict) and (off.get("title") or off.get("body")):
        parts.append(f"The learner is currently stuck: {off.get('title', '')} {off.get('body', '')}".strip())
    code = _code(context)
    if code:
        name = context.get("file") or "file"
        parts.append(f"Code in {name}:\n```\n{code[:CODE_CHARS]}\n```")
    screen = _screen_text(context.get("screen"))
    if screen:
        parts.append(f"Text on the learner's screen (OCR):\n{screen[-SCREEN_CHARS:]}")
    if not code and not screen:
        parts.append("(Nothing readable on screen; base the diagram on the step itself.)")
    q = _question(context)
    if q:
        parts.append(f"The learner asked: {q}")
    if context.get("kind") in ("network", "graph"):
        parts.append(f"Preferred kind: {context['kind']} (if it fits the rules).")
    return "\n\n".join(parts)


# ---------------------------------------------------------------- validation


def _clip(s: Any, n: int) -> str:
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


CAPTION_WORDS = 12  # BRAND: the caption is one sentence of <= 12 words (E12)
_TRAILING = re.compile(r"\s+(a|an|the|of|to|and|or|in|on|for|with|by|at|from|into|is|are)$", re.I)


def _caption(s: Any, limit: int = 240) -> str:
    """ONE sentence of <= CAPTION_WORDS words: the first sentence; a longer one ends at its last clause break
    (, ; : —) when that keeps at least half of it, else at the word limit with "…"."""
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    s = re.split(r"(?<=[.!?])\s+", s, maxsplit=1)[0] if s else ""
    words = s.split(" ")
    if len(words) <= CAPTION_WORDS:
        return _clip(s, limit)
    cut = " ".join(words[:CAPTION_WORDS])
    at = max(cut.rfind(p) for p in (", ", "; ", ": ", " — ", " – "))
    if at > 0 and len(cut[:at].split()) >= CAPTION_WORDS // 2:
        return cut[:at].rstrip() + "."
    cut = cut.rstrip(",;:—–- ")
    while _TRAILING.search(cut):
        cut = _TRAILING.sub("", cut)
    return cut + "…"


def to_payload(raw: dict, step: dict) -> dict:
    """Validate the model's JSON and turn it into the event payload. Raises DiagramError."""
    kind = raw.get("kind")
    caption = _caption(raw.get("caption"))
    if not caption:
        raise DiagramError("Diagram came back without a caption")

    if kind == "network":
        net = raw.get("network") or {}
        layers = net.get("layers") or []
        if not (2 <= len(layers) <= 10) or not all(isinstance(n, int) and n > 0 for n in layers):
            raise DiagramError(f"Diagram network has unusable layer sizes: {layers}")
        data = {
            "layers": layers,
            "activation": _clip(net.get("activation"), 16) or "?",
            "derivatives": [_clip(d, 10) for d in (net.get("derivatives") or [])][:2],
            "residual": _clip(net.get("residual"), 24),
        }
        if net.get("inputs"):
            data["inputs"] = [_clip(x, 6) for x in net["inputs"]][: layers[0]]
        if net.get("output"):
            data["output"] = _clip(net["output"], 6)
        return {"kind": "network", "caption": caption, "data": data}

    if kind != "graph":
        raise DiagramError(f"Diagram came back with an unknown kind: {kind!r}")
    g = raw.get("graph") or {}
    nodes = g.get("nodes") or []
    if not nodes:
        raise DiagramError("Diagram came back with no nodes")
    if len(nodes) > MAX_NODES:
        raise DiagramError(f"Diagram has {len(nodes)} nodes (max {MAX_NODES})")
    seen: set[str] = set()
    out_nodes = []
    for n in nodes:
        nid = str(n.get("id") or "").strip()
        if not nid or nid in seen:
            raise DiagramError(f"Diagram has a missing or duplicate node id: {nid!r}")
        seen.add(nid)
        node = {"id": nid, "label": _clip(n.get("label"), 22) or nid, "shape": n.get("shape") or "box",
                "emphasis": bool(n.get("emphasis"))}
        if n.get("detail"):
            node["detail"] = _clip(n["detail"], 28)
        if n.get("group"):
            node["group"] = _clip(n["group"], 24)
        out_nodes.append(node)
    out_edges = []
    for e in g.get("edges") or []:
        a, b = str(e.get("from") or ""), str(e.get("to") or "")
        if a not in seen or b not in seen:
            log.warning("diagrams: dropping edge with unknown endpoint %r -> %r", a, b)
            continue
        edge = {"from": a, "to": b, "style": e.get("style") or "solid", "emphasis": bool(e.get("emphasis"))}
        if e.get("label"):
            edge["label"] = _clip(e["label"], 22)
        out_edges.append(edge)
    lay = g.get("layout") if g.get("layout") in LAYOUTS else "flow"
    data = {
        "title": _clip(g.get("title"), 28) or step.get("title", ""),
        "layout": lay,
        "direction": "TB" if g.get("direction") == "TB" and lay not in ("git", "sequence") else "LR",
        "nodes": out_nodes,
        "edges": out_edges,
    }
    groups = [{"id": str(x["id"]), "label": _clip(x.get("label"), 24)} for x in g.get("groups") or [] if x.get("id")]
    if groups:
        data["groups"] = groups
    layout.apply(data)
    return {"kind": "graph", "caption": caption, "data": data}


# ---------------------------------------------------------------- Claude call

_client = None
_client_key: str | None = None


def _get_client():
    """AsyncAnthropic bound to the current key (app key > env); rebuilt when the key changes."""
    global _client, _client_key
    try:
        from server.config import get_key
        key = get_key("anthropic")
    except ImportError:  # pragma: no cover
        key = os.environ.get("ANTHROPIC_API_KEY")
    if _client is None or key != _client_key:
        import anthropic

        kw: dict[str, Any] = {"max_retries": 0, "timeout": TIMEOUT_S}
        if key:
            kw["api_key"] = key
        try:
            _client = anthropic.AsyncAnthropic(**kw)
        except anthropic.AnthropicError as e:
            raise DiagramError("No Anthropic key: add one in Settings or set ANTHROPIC_API_KEY") from e
        _client_key = key
    return _client


async def _call(client, step: dict, context: dict) -> tuple[dict, dict]:
    import anthropic

    prompt = user_prompt(step, context)
    t0 = time.monotonic()
    try:
        kwargs: dict[str, Any] = {
            "model": MODEL,
            "max_tokens": 4000,
            "system": SYSTEM,
            "messages": [{"role": "user", "content": prompt}],
            "output_config": {"effort": EFFORT, "format": {"type": "json_schema", "schema": SCHEMA}},
        }
        if MODEL.startswith(("claude-sonnet-5-5", "claude-opus-5")):
            # server-side refusal fallback (routes a policy decline to a fallback model)
            resp = await client.beta.messages.create(betas=[FALLBACK_BETA], fallbacks="default", **kwargs)
        else:
            resp = await client.messages.create(**kwargs)
    except anthropic.AuthenticationError as e:
        raise DiagramError("Anthropic key was rejected (check Settings)") from e
    except anthropic.RateLimitError as e:
        raise DiagramError("Claude is rate-limited right now; try the diagram again in a moment") from e
    except anthropic.APITimeoutError as e:
        raise DiagramError(f"Claude took longer than {TIMEOUT_S:.0f}s to draw the diagram") from e
    except anthropic.APIStatusError as e:
        raise DiagramError(f"Claude API error {e.status_code} while drawing the diagram") from e
    except anthropic.APIConnectionError as e:
        raise DiagramError("Could not reach Claude to draw the diagram") from e
    latency = time.monotonic() - t0
    if resp.stop_reason == "refusal":
        raise DiagramError("Claude declined to draw this diagram")
    if resp.stop_reason == "max_tokens":
        raise DiagramError("Diagram answer was cut off (max_tokens)")
    text = next((b.text for b in resp.content if getattr(b, "type", "") == "text"), None)
    if not text:
        raise DiagramError("Claude returned no diagram")
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as e:
        raise DiagramError("Claude returned an unreadable diagram") from e
    u = getattr(resp, "usage", None)
    meta = {"model": getattr(resp, "model", MODEL), "latency_s": round(latency, 2),
            "input_tokens": getattr(u, "input_tokens", 0), "output_tokens": getattr(u, "output_tokens", 0)}
    log.info("diagrams: %s %.2fs in=%s out=%s", meta["model"], latency, meta["input_tokens"], meta["output_tokens"])
    return raw, meta


# ---------------------------------------------------------------- cache + entry point

_CACHE_MAX = 64
_cache: OrderedDict[tuple, dict] = OrderedDict()
_inflight: dict[tuple, asyncio.Future] = {}
last_meta: dict = {}


def cache_key(step: dict, context: dict) -> tuple:
    """(step id, hash of code + screen text, normalized question, kind hint)."""
    h = hashlib.sha256((_code(context) + "\x00" + _screen_text(context.get("screen"))).encode()).hexdigest()[:16]
    q = re.sub(r"\s+", " ", _question(context).lower())
    return (str(step.get("id") or step.get("title") or ""), h, q, context.get("kind") or "")


def clear_cache() -> None:
    _cache.clear()


async def build(step: dict, context: dict | None = None, *, client=None) -> dict:
    """One explanatory diagram for `step` -> `diagram` event payload ({kind, caption, data, stepId}).

    context keys (all optional): code, file, screen ({app: [lines]} | [lines] | str), question,
    lesson ({title, goal}), offtrack ({title, body}), kind ("network" | "graph" preference).
    Cached by (step id, code+screen hash, question). Raises DiagramError; never returns canned data.
    """
    if not isinstance(step, dict) or not (step.get("title") or step.get("instructions")):
        raise DiagramError("No current step to draw a diagram for")
    context = dict(context or {})
    key = cache_key(step, context)
    if key in _cache:
        _cache.move_to_end(key)
        last_meta.clear()
        last_meta.update({"cached": True})
        return json.loads(json.dumps(_cache[key]))
    if key in _inflight:  # double-press while the first request is still running
        return json.loads(json.dumps(await asyncio.shield(_inflight[key])))

    fut: asyncio.Future = asyncio.get_running_loop().create_future()
    _inflight[key] = fut
    try:
        raw, meta = await _call(client or _get_client(), step, context)
        payload = to_payload(raw, step)
        if step.get("id"):
            payload["stepId"] = str(step["id"])
        _cache[key] = payload
        while len(_cache) > _CACHE_MAX:
            _cache.popitem(last=False)
        last_meta.clear()
        last_meta.update(meta, cached=False)
        fut.set_result(payload)
        return json.loads(json.dumps(payload))
    except BaseException as e:
        if not fut.done():
            fut.set_exception(e if isinstance(e, Exception) else DiagramError("cancelled"))
            fut.exception()  # mark retrieved so asyncio doesn't warn when nobody else awaited it
        raise
    finally:
        _inflight.pop(key, None)

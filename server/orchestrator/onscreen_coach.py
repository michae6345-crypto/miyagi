"""On-screen coach (Nov 24): in a desktop-app lesson, miyagi circles the thing to act on and writes the step there.

Michael: "i just really want it to be able to see and circle shit on screen and type there; it would remove the
complexity of the interface on the side". In an app lesson (graph.lesson.app set by server.lesson.app_lesson: Blender,
AutoCAD...; never VS Code or a code lesson) the engine sends ONE annotate mark

    {id: "os-<stepId>-<n>", why: "point", stepId, label (<= 4 words), text (<= 12 words), keys (<= 3), x, y, w, h}

at a step start, on a "Not yet" for the current step, and on Show me (the "where?" ask, and a short typed "where ...?").
Placing it is free: server.screen.app_target finds the rect (the app's bridge, then AX, then OCR) with no model call,
off the event loop. No rect -> no mark (a wrong circle is worse than none); Show me then sends its where card (words).

Rules: one mark per annotate; never from idle, the evaluate loop or ticks; never the same mark twice in a row (same
step + rect within 12 pt + same text is skipped on a step-start retry, and on a Not yet within 8 s of the last send);
where? always re-sends with a new id. annotate {clear} goes once, only while a mark is up, on step.passed / a skip /
lesson.ended / a new lesson. While a step's mark is up (for at most 20 s after its last send: the app fades it unseen
on a click or Esc) the session sends no spotlight rect for it (one pointer). A Not yet re-circles only for a learner's
press (pressed = not auto, like _emit_card's `mine`), never for the judge's auto card. Show me with nothing to circle
sends where_card (the words, naming the app) and never reaches the model path.

Hooks in LessonSession (each 1-3 lines, like ui_targets): _lesson_ready_payload (lesson.app), start_step (on_step),
_emit_card (not_yet_card), the show_me branch (on_where), the ask branch (on_where_ask), _pass_step / _end_lesson /
load_graph (clear), _show_spot (holds_spot).
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from server.screen import app_target

log = logging.getLogger("orchestrator.session")

FIRST_TRY_S = 0.8            # the first look, after the step's own events went out
STEP_DELAYS_S = (FIRST_TRY_S, 1.0, 1.0, 1.2)   # the first try + 3 retries, ~4 s in all
HOLD_POLL_S = 0.5            # "Before you start" / "Continue?" up: wait for it to go, then look
HOLD_WAIT_MAX_S = 600.0
SAME_PT = 12.0               # a rect within this of the last one is the same mark
NOT_YET_REPEAT_S = 8.0       # a Not yet re-sends the identical mark only after this
HOLD_SPOT_S = 20.0           # a mark holds spotlights back this long at most: the app fades it on a click / Esc unseen
TEXT_WORDS = 12
LABEL_WORDS = 4
MAX_KEYS = 3
CODE_TOOLS = frozenset({"vscode", "code", "vs code", "visual studio code", "vscodium", "xcode", "pycharm", "jupyter",
                        "jupyterlab", "colab", "terminal", "iterm", "arduino-ide"})


# ------------------------------------------------------------------ state

def _state(s) -> dict:
    st = getattr(s, "_onscreen", None)
    if not isinstance(st, dict):
        st = {"live": None, "last": None, "n": 0}
        s._onscreen = st
    return st


def _app(s) -> dict | None:
    app = ((getattr(s, "graph", None) or {}).get("lesson") or {}).get("app")
    return app if isinstance(app, dict) and str(app.get("tool") or "").strip() else None


def _web_app(app: dict) -> bool:
    """The lesson's app, or the one the learner really uses, is a website (Tinkercad, Onshape, Photopea): its window
    is the browser's, so nothing in it can be circled (the 'another app in front' gate would always refuse)."""
    try:
        from server.workspace import apps
    except Exception:  # noqa: BLE001 - unsure: treat it as a website (no circles, the words still come)
        return True
    web = {str(k).lower() for k in apps.WEB_APPS} | {str(e.get("label") or "").lower() for e in apps.WEB_APPS.values()}
    for k in ("tool", "using"):
        v = str(app.get(k) or "").strip()
        if v and (v.lower() in web or (apps.canonical(v) or "") in apps.WEB_APPS):
            return True
    return False


def is_app_lesson(s) -> bool:
    """graph.lesson.app is a dict with a tool, the tool is no code / VS Code app nor a website (apps.WEB_APPS, for the
    lesson's tool or the `using` alternative), the app's window has a name to find it by, and no step writes or runs
    code. Only then does lesson.ready carry lesson.app (the app collapses its panel for the on-screen coach)."""
    app = _app(s)
    if app is None:
        return False
    names = {str(app.get(k) or "").strip().lower() for k in ("tool", "label", "using")} - {""}
    try:
        from .session import CODE_APP_NAMES
    except Exception:  # noqa: BLE001
        CODE_APP_NAMES = set()  # noqa: N806
    if names & (CODE_TOOLS | set(CODE_APP_NAMES)):
        return False
    if _web_app(app) or not app_target._names(app):
        return False
    try:
        from server.lesson import app_lesson

        return not app_lesson.has_code(getattr(s, "graph", None) or {})
    except Exception:  # noqa: BLE001 - unsure: no circles (the words still come)
        return False


def ready_app(s) -> dict | None:
    """lesson.ready's lesson.app ({tool, label, using?}): only for an app lesson (is_app_lesson), and only with a
    non-empty string tool and label (LessonApp requires both: a bad value would fail the whole lesson.ready)."""
    app = _app(s)
    if app is None or not is_app_lesson(s):
        return None
    out = {k: app[k].strip() for k in ("tool", "label", "using") if isinstance(app.get(k), str) and app[k].strip()}
    return out if out.get("tool") and out.get("label") else None


def holds_spot(s) -> bool:
    """A mark is up for the current step: the session sends no spotlight rect for it (one pointer at a time). Only
    for HOLD_SPOT_S after its last send: the app fades a text mark when the learner reaches it or presses Esc and the
    engine never hears of it, so an older mark must not mute that step's off-track boxes for good."""
    live = _state(s)["live"]
    step = getattr(s, "step", None)
    if not live or step is None or live.get("stepId") != step.get("id") or live.get("gen") != getattr(s, "step_gen", None):
        return False
    now = s.clock() if callable(getattr(s, "clock", None)) else None
    return now is None or now - float(live.get("t") or 0.0) < HOLD_SPOT_S


# ------------------------------------------------------------------ copy: text, label, keys

_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")


def _first_sentence(instructions: str) -> str:
    """The instructions' first sentence: all the mark shows (short_text), so all its keycaps come from (keys)."""
    return _SENTENCE.split(" ".join(str(instructions or "").split()))[0]


def short_text(instructions: str) -> str:
    """The step's action in <= 12 words, cut at a clause boundary when it is longer."""
    first = _first_sentence(instructions)
    if not first:
        return ""
    words = first.split()
    if len(words) <= TEXT_WORDS:
        return first.rstrip(" ,;:-")
    head = " ".join(words[:TEXT_WORDS])
    floor = len(" ".join(words[:4]))
    cut = max(head.rfind(", "), head.rfind("; "), head.rfind(": "), head.rfind(" - "), head.rfind(" then "),
              head.rfind(" and "), head.rfind(" to "))
    if cut >= floor:
        head = head[:cut]
    return head.rstrip(" ,;:-")


def short_label(phrase: str) -> str:
    return " ".join(str(phrase or "").split()[:LABEL_WORDS])


_MODS = {"ctrl": "⌃", "control": "⌃", "alt": "⌥", "option": "⌥", "opt": "⌥", "shift": "⇧", "cmd": "⌘",
         "command": "⌘"}
_ORDER = "⌃⌥⇧⌘"
_NAMED = {"tab": "Tab", "esc": "Esc", "escape": "Esc", "return": "Return", "enter": "Return", "space": "Space",
          "spacebar": "Space", "delete": "Delete", "backspace": "Delete", "del": "Delete"}
_KEY = r"(?:numpad\s*\d|f1[0-2]|f[1-9]|tab|escape|esc|return|enter|spacebar|space|delete|backspace|del|[a-z0-9])"
_CHORD = re.compile(rf"\b((?:(?:shift|ctrl|control|alt|option|opt|cmd|command)\s*[+\-]\s*)+)({_KEY})(?![\w])", re.I)
_GLYPH = re.compile(r"[⌃⌥⇧⌘]+\s*(?:Numpad\s*\d|F1[0-2]|F[1-9]|Tab|Esc|Return|Space|Delete|[←→↑↓]|[A-Za-z0-9])(?![a-z])")
_PKEY = r"(?:[Nn]umpad\s*\d|F1[0-2]|F[1-9]|[Tt]ab|[Ee]sc(?:ape)?|[Rr]eturn|[Ee]nter|[Ss]pace(?:bar)?|[Dd]elete|" \
        r"[Bb]ackspace|[A-Z0-9])"
_NOT_NUM = r"(?![\w+\-]|[.,]\d)"  # "0.5", "1,000": a number, never a key
_ONE_KEY = re.compile(rf"(?<![\w]){_PKEY}{_NOT_NUM}")
_SEP = r"(?:\s*,\s*(?i:then\s+|and\s+then\s+|and\s+)?|\s+(?i:then|and then|followed by|and)\s+)"
# a chained key without its own "press" is capitalized ("press X, then Delete"; "press X, then delete it" is a verb)
_CKEY = r"(?:Numpad\s*\d|F1[0-2]|F[1-9]|Tab|Esc(?:ape)?|Return|Enter|Space(?:bar)?|Delete|Backspace|[A-Z0-9])"
_PRESS = re.compile(rf"\b((?i:press|hit|tap|type))\s+({_PKEY}){_NOT_NUM}"
                    rf"((?:{_SEP}(?:(?i:press\s+){_PKEY}|{_CKEY}){_NOT_NUM})*)")
_BARE = re.compile(r"\b(Numpad\s*\d|F1[0-2]|F[1-9])\b")
# "Press Numpad 1 for front view, then Tab to enter Edit Mode": a named key (capitalized: "then delete it" is a verb)
# after ", then" counts once a key was pressed before it in the instructions
_THEN_KEY = re.compile(r",\s*(?i:and\s+)?(?i:then)\s+(Numpad\s*\d|F1[0-2]|F[1-9]|Tab|Esc(?:ape)?|Return|Enter|"
                       r"Space(?:bar)?|Delete|Backspace)(?![\w+\-])")


def _key_label(k: str) -> str:
    k = " ".join(k.split())
    low = k.lower().replace(" ", "")
    if low.startswith("numpad"):
        return f"Numpad {low[6:]}"
    if re.fullmatch(r"f\d{1,2}", low):
        return low.upper()
    return _NAMED.get(low, k.upper() if len(k) == 1 else k)


def keys(instructions: str) -> list[str]:
    """The shortcut, one keycap label per key pressed, in order, <= 3, spelled as bridge.platform.keys spells Mac keys:
    "Shift+A" -> "⇧A", "Ctrl+Shift+Z" -> "⌃⇧Z", "⌘S" stays, "press G then Z" -> ["G", "Z"], "Numpad 1", Tab, F12.
    Only the first sentence's keys: the mark's text is that sentence (short_text), so "Press Tab. Then press A." shows
    "Press Tab." with Tab alone."""
    text = _first_sentence(instructions)
    found: list[tuple[int, int, str]] = []

    def add(a: int, b: int, label: str) -> None:
        if not any(a < y and x < b for x, y, _ in found):
            found.append((a, b, label))

    for m in _CHORD.finditer(text):
        mods = {_MODS[x.lower()] for x in re.findall(r"[A-Za-z]+", m.group(1))}
        add(m.start(), m.end(), "".join(g for g in _ORDER if g in mods) + _key_label(m.group(2)))
    for m in _GLYPH.finditer(text):
        add(m.start(), m.end(), re.sub(r"^([⌃⌥⇧⌘]+)\s+", r"\1", m.group(0).strip()))
    for m in _PRESS.finditer(text):
        if not (m.group(1).lower() == "type" and len(m.group(2)) == 1):  # "Type 2": a value typed, not a key
            add(m.start(2), m.end(2), _key_label(m.group(2)))
        off = m.start(3)
        for k in _ONE_KEY.finditer(m.group(3)):
            add(off + k.start(), off + k.end(), _key_label(k.group(0)))
    for m in _BARE.finditer(text):
        add(m.start(), m.end(), _key_label(m.group(1)))
    for m in _THEN_KEY.finditer(text):
        if any(b <= m.start() for _, b, _ in found):
            add(m.start(1), m.end(1), _key_label(m.group(1)))
    return [lb for _, _, lb in sorted(found)][:MAX_KEYS]


# ------------------------------------------------------------------ resolving (free, off the loop)

def _frame(s) -> Any:
    """A frame at most MAX_FRAME_AGE_S old (blocking: called in the worker thread). The reader keeps its latest frame
    until the screen changes, so on a still screen (a learner reading the step) it is often older than that:
    ScreenBridge.fresh captures + OCRs a new one then, and gives None while capture is paused or down. Only without a
    ScreenBridge: the reader's latest frame / the session's last one (resolve still refuses a stale one)."""
    scr = getattr(s, "screen", None)
    if scr is not None and callable(getattr(scr, "fresh", None)):
        try:
            obs = scr.fresh(app_target.MAX_FRAME_AGE_S)
        except Exception:  # noqa: BLE001
            log.exception("on-screen coach: fresh frame failed")
            return None
        return obs if hasattr(obs, "blocks") else None
    reader = getattr(scr, "reader", None)
    try:
        obs = reader.latest() if reader is not None and hasattr(reader, "latest") else None
    except Exception:  # noqa: BLE001
        obs = None
    if obs is None or not hasattr(obs, "blocks"):
        obs = getattr(s, "last_obs", None) if hasattr(getattr(s, "last_obs", None), "blocks") else None
    return obs


def _observe(s) -> tuple[list, str]:
    """(miyagi's overlay rects, the app in front now) from the session's reader; missing parts empty."""
    reader = getattr(getattr(s, "screen", None), "reader", None)
    overlay: list = []
    try:
        overlay = list(reader.overlay_rects()) if reader is not None and hasattr(reader, "overlay_rects") else []
    except Exception:  # noqa: BLE001
        overlay = []
    front = ""
    try:
        front = s._live_front() if hasattr(s, "_live_front") else ""
    except Exception:  # noqa: BLE001
        front = ""
    return overlay, front


async def _resolve(s, step: dict, phrase_list: list | None = None) -> app_target.Target | None:
    app = _app(s)
    if app is None:
        return None
    overlay, front = _observe(s)
    app = dict(app)

    def work() -> app_target.Target | None:  # the capture + OCR, AX walk and OCR match: all off the event loop
        return app_target.resolve(step, app, _frame(s), overlay, front=front, phrase_list=phrase_list)

    try:
        return await asyncio.to_thread(work)
    except Exception:  # noqa: BLE001 - no circle, never a crash
        log.exception("on-screen coach: resolve failed")
        return None


def _current(s, gen: int, step: dict) -> bool:
    return getattr(s, "step_gen", None) == gen and getattr(s, "step", None) is step \
        and not getattr(s, "passed", False) and is_app_lesson(s)


def _held(s) -> bool:
    return bool(getattr(s, "awaiting_start", False) or getattr(s, "awaiting_resume", False))


def _mark(s, step: dict, t: app_target.Target) -> dict:
    st = _state(s)
    st["n"] += 1
    r = t.rect.rounded()
    m: dict[str, Any] = {"id": f"os-{step.get('id')}-{st['n']}", "why": "point", "stepId": step.get("id"),
                         "x": r.x, "y": r.y, "w": r.w, "h": r.h}
    if label := short_label(t.label):
        m["label"] = label
    if text := short_text(step.get("instructions") or step.get("title") or ""):
        m["text"] = text
    if ks := keys(" ".join(str(step.get(k) or "") for k in ("instructions",))):
        m["keys"] = ks
    return m


def _same(last: dict | None, step: dict, mark: dict) -> bool:
    if not last or last.get("stepId") != step.get("id") or last.get("text") != mark.get("text"):
        return False
    return all(abs(float(last[k]) - float(mark[k])) <= SAME_PT for k in ("x", "y", "w", "h"))


async def _drop_spot(s) -> None:
    """A spotlight box already up for this step (an off-track box, an earlier box) goes, through the session's own
    spotlight clear (emit resets spot_rect), so the mark is the one pointer. spot_rect is cleared at every step start,
    so one that is up belongs to this step."""
    if getattr(s, "spot_rect", None) is None:
        return
    lock = s._spot_lock() if callable(getattr(s, "_spot_lock", None)) else None
    if lock is not None:
        async with lock:
            if getattr(s, "spot_rect", None) is None:
                return
            if callable(getattr(s, "clock", None)):
                s._spot_t = s.clock()
            await s.emit("spotlight", {"clear": True})
        return
    await s.emit("spotlight", {"clear": True})


async def _send(s, step: dict, mark: dict, why: str, t: app_target.Target, gen: int | None = None) -> bool:
    """Send the ONE mark. gen: the step_gen it was resolved for; a pass / step change that lands while the spotlight
    clear waits on its lock sends nothing (no mark may outlive its step). -> whether it went out."""
    st = _state(s)
    await _drop_spot(s)
    if gen is not None and not _current(s, gen, step):
        return False
    await s.emit("annotate", {"marks": [mark]})
    now = s.clock() if callable(getattr(s, "clock", None)) else 0.0
    st["live"] = {**mark, "gen": getattr(s, "step_gen", None), "t": now}
    st["last"] = {**mark, "gen": getattr(s, "step_gen", None), "t": now}
    log.info("on-screen coach (%s): circled %r via %s at %s", why, mark.get("label"), t.via,
             {k: mark[k] for k in ("x", "y", "w", "h")})
    return True


# ------------------------------------------------------------------ triggers

async def on_step(s, gen: int, step: dict) -> None:
    """A step start: look ~0.8 s in, retry up to 3 times within ~4 s; stop once the step changes or passes. Never for
    a replay or a restore; under "Before you start" / "Continue?" it waits for the learner first."""
    st = _state(s)
    if st["live"] and st["live"].get("stepId") != step.get("id"):
        st["live"] = None  # the app fades marks on a step change
    if getattr(s, "restoring", False) or step.get("replay"):
        return
    waited = 0.0
    while _held(s):
        if not _current(s, gen, step) or waited >= HOLD_WAIT_MAX_S:
            return
        await asyncio.sleep(HOLD_POLL_S)
        waited += HOLD_POLL_S
    for delay in STEP_DELAYS_S:
        await asyncio.sleep(delay)
        if not _current(s, gen, step) or _held(s):
            return
        t = await _resolve(s, step)
        if not _current(s, gen, step):
            return
        if t is None:
            continue
        mark = _mark(s, step, t)
        last = st["last"]
        if last is not None and last.get("gen") == gen and _same(last, step, mark):
            return
        await _send(s, step, mark, "step", t, gen)
        return


def not_yet_card(s, card: dict, pressed: bool) -> None:
    """_emit_card hook: a "Not yet" for the current step, answering a learner's press (never the idle / evaluate /
    tick paths), re-circles the step's target in the background."""
    if not pressed or not isinstance(card, dict):
        return
    if card.get("title") != "Not yet" and card.get("verdict") != "not_done":
        return
    step = getattr(s, "step", None)
    if step is None or card.get("stepId") not in (None, step.get("id")) or not is_app_lesson(s):
        return
    s._spawn(on_not_yet(s, step))


async def on_not_yet(s, step: dict) -> bool:
    gen = getattr(s, "step_gen", None)
    if not _current(s, gen, step):
        return False
    t = await _resolve(s, step)
    if t is None or not _current(s, gen, step):
        return False
    mark = _mark(s, step, t)
    last = _state(s)["last"]
    now = s.clock() if callable(getattr(s, "clock", None)) else 0.0
    if last is not None and _same(last, step, mark) and now - float(last.get("t") or 0.0) < NOT_YET_REPEAT_S:
        return True  # the identical mark went out moments ago: it is still the answer
    return await _send(s, step, mark, "not yet", t, gen)


async def on_where(s, step: dict, phrase_list: list | None = None) -> bool:
    """Show me / "where?": circle it now, always with a new id. False: nothing found (the where card goes instead).
    True also when the step changed or passed while it looked: no mark and no words about a step that is gone."""
    if step is None or not is_app_lesson(s):
        return False
    gen = getattr(s, "step_gen", None)
    if not _current(s, gen, step):
        return False
    t = await _resolve(s, step, phrase_list)
    if not _current(s, gen, step):  # the step changed or passed meanwhile (clear() has run): nothing to say about it
        return True
    if t is None:
        return False
    await _send(s, step, _mark(s, step, t), "where", t, gen)  # sends nothing if the step moves on meanwhile
    return True


def where_card(s, step: dict) -> dict:
    """Show me in an app lesson found nothing to circle: the where card in words (free, never a model). The words name
    the app (the panel may be collapsed for the coach, so the step is said here); the screen is down: say why."""
    sid = step.get("id")
    try:
        reason = s.screen_down_reason(include_ax=False) if hasattr(s, "screen_down_reason") else None
    except Exception:  # noqa: BLE001
        reason = None
    if reason:
        return {"stepId": sid, "kind": "hint", "title": "I can't see your screen", "body": s.screen_down_message(reason)}
    app = _app(s) or {}
    name = str(app.get("using") or app.get("label") or "the app").strip()
    text = short_text(step.get("instructions") or step.get("title") or "")
    return {"stepId": sid, "kind": "where", "title": "Where to work",
            "body": f"In {name}: {text}" if text else f"Bring {name} to the front so I can see it."}


_WHERE = re.compile(r"^\s*where(?:'s|\s+is|\s+are|\s+do\s+i\s+(?:find|click|go)|\s+can\s+i\s+find|\s+should\s+i\s+"
                    r"(?:click|look))?\b\s*(.*?)\s*\??\s*$", re.I)
_VAGUE = re.compile(r"^(?:it|this|that|they|them|there|i|to|do i|i click|to click|i go|is it|now|next|the thing)?$",
                    re.I)
_GENERIC = re.compile(r"\s+(?:button|menu|tab|panel|option|icon|item|field|setting|tool)s?$", re.I)


def where_phrases(text: str) -> list[app_target.Phrase] | None:
    """A short typed "where ...?" ask (<= 8 words) -> the phrases to find: what it names ("where is the Add menu?" ->
    "Add menu", "Add"; a place by its tab / area / region: "where is the Modifier tab?" -> tab MODIFIER and area
    PROPERTIES, never the bare word "Modifier"), or [] for a vague one ("where?", "where do I click?": the step's own
    target). None: not a where ask, or a place miyagi doesn't know ("where is the Transform panel?")."""
    t = " ".join(str(text or "").split())
    if not t or len(t.split()) > 8:
        return None
    m = _WHERE.match(t)
    if m is None:
        return None
    what = re.sub(r"^(?:the|a|an|my)\s+", "", m.group(1).strip(" ?.!"), flags=re.I)
    if _VAGUE.match(what):
        return []
    placed = app_target.place_phrases(what)
    if placed is not None:
        # "the Modifier tab", "the properties editor": a place, never a control's words ("Modifier" would be found
        # inside the "Add Modifier" button); a place miyagi doesn't know ("the Transform panel"): not a where ask
        out = list(placed)
    else:
        out = [app_target.Phrase(what, "ui")]
        if (bare := _GENERIC.sub("", what)) and bare != what:
            out.append(app_target.Phrase(bare, "ui"))
    extra = [app_target.Phrase(t, "tab") for t in app_target.tab_contexts(what)]
    extra += [app_target.Phrase(r, "region") for r in app_target.region_types(what)]
    extra += [app_target.Phrase(a, "area") for a in app_target.area_types(what)]
    out += [p for p in extra if p not in out]
    return out or None


async def on_where_ask(s, step: dict | None, text: str | None) -> bool:
    """The ask branch: a short typed "where ...?" in an app lesson circles it like Show me. False: not one / not found
    (the ask is answered as before)."""
    if step is None or not is_app_lesson(s):
        return False
    plist = where_phrases(text or "")
    if plist is None:
        return False
    return await on_where(s, step, plist or None)


async def clear(s) -> None:
    """step.passed / a skip / lesson.ended / a new lesson: annotate {clear} once, only while a mark is up."""
    st = _state(s)
    if not st["live"]:
        return
    st["live"] = None
    await s.emit("annotate", {"clear": True})

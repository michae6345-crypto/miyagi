"""The setup card's app rows: "I have it", "Get it", "Try <free alternative>", and noticing the app (Nov 22).

Michael's AutoCAD lesson: the card said "Missing: autocad. Install now?" with only Skip, and nothing could get AutoCAD.
server.workspace.apps now classifies every row (package / free_app / licensed_app / web_app); a licensed app is never
installed. Its row offers:

  have_it      re-check this Mac (folders + Spotlight). Found: the row flips to installed. Not found: the learner's
               word stands (haveIt), kept per Mac for apps.HAVE_IT_DAYS so later lessons don't ask again
  get_it       open the vendor's own download / trial page, only through the host allowlist
               (server.safety.browser_url_allowed); the app is noticed when it comes to the front
  alternative  the free alternative: a web app (Tinkercad, Google Sheets) opens in the browser; a free desktop app
               (FreeCAD, GIMP) becomes its own row with Install (the learner's Install press is the confirm)

on_front: when an app row's app comes to the front, re-check it and flip the row. Nothing here installs anything.
`text` on each action is the row's tool id; without one, the first app row still waiting.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

log = logging.getLogger("orchestrator.setup_apps")

ACTIONS = frozenset({"have_it", "get_it", "alternative"})
APP_KINDS = ("licensed_app", "free_app")
NOTE_MS = 4000  # the passing note ("AutoCAD found") closes itself
FRONT_RECHECK_S = 5.0  # one re-check per app per this long while it stays in front


def _apps():
    from server.workspace import apps

    return apps


def _rows(s: Any) -> list[dict]:
    """The setup check's items (the lesson's, else the preflight card's before a lesson exists)."""
    if s.reqs:
        return list(s.reqs)
    return list((((getattr(s, "pending_pick", None) or {}).get("card")) or {}).get("items") or [])


def _kind(it: dict) -> str:
    return it.get("setupKind") or _apps().classify(it)


def _waiting(it: dict) -> bool:
    return (it.get("needed", True) and not it.get("ok") and not it.get("haveIt") and not it.get("using")
            and _kind(it) in APP_KINDS and it.get("kind") != "editor")


def pick(s: Any, tool: str | None) -> dict | None:
    rows = _rows(s)
    tool = (tool or "").strip()
    if tool:
        return next((it for it in rows if it.get("tool") == tool), None)
    return next((it for it in rows if _waiting(it) and _kind(it) == "licensed_app"), None) \
        or next((it for it in rows if _waiting(it)), None)


async def act(s: Any, kind: str, tool: str | None) -> None:
    item = pick(s, tool)
    if item is None:
        log.info("%s: no app row for %r", kind, tool)
        return
    if kind == "have_it":
        await have_it(s, item)
    elif kind == "get_it":
        await get_it(s, item)
    elif kind == "alternative":
        await use_alternative(s, item)


async def _recheck(item: dict) -> dict:
    """setup.check on a copy (folders, Spotlight, Info.plist): read-only, a second at most. Run in a thread."""
    from server.workspace import setup as S

    probe = {k: v for k, v in item.items() if k in ("tool", "label", "kind", "min_version", "binary")}
    probe.setdefault("kind", "app")
    try:
        return await asyncio.to_thread(S.check, probe)
    except Exception:  # noqa: BLE001 - a failed look is "not found", never a crash
        log.exception("app re-check failed")
        return {**probe, "installed": False}


def _flip(item: dict, found: dict) -> None:
    item.update(installed=True, ok=bool(found.get("ok", True)), version=found.get("version") or "",
                where=found.get("where") or "")
    item.pop("haveIt", None)


async def have_it(s: Any, item: dict) -> None:
    apps = _apps()
    found = await _recheck(item)
    label = item.get("label") or item.get("tool")
    if found.get("installed"):
        _flip(item, found)
        apps.remember(item["tool"], installed=True, version=item.get("version") or "", where=item.get("where") or "")
        note = f"{label} found"
    else:  # the learner's word stands (another folder, a VM, a school machine): not asked again on this Mac
        # for apps.HAVE_IT_DAYS (a mistaken press expires)
        item["haveIt"] = True
        apps.remember(item["tool"], haveIt=True)
        await repin_and_tell(s)  # checks pinned to an app this Mac can't see would wait forever
        note = f"Got it. I'll use {label} when it opens."
    await refresh(s, note)


async def get_it(s: Any, item: dict) -> None:
    apps = _apps()
    lic = apps.licensed(item.get("tool") or "")
    url = (lic or {}).get("vendor_url") or ((item.get("install") or {}).get("url") or "")
    if not url:
        await refresh(s, None)
        return
    opened = await open_url(s, url, item.get("label") or item.get("tool") or "the app")
    item["gettingIt"] = True
    apps.remember(item["tool"], choice="get_it")
    if opened:
        whose = f"{lic['vendor']}'s" if lic else "the download"
        await status(s, f"Opened {whose} page. I'll notice when {item.get('label')} opens.")


async def use_alternative(s: Any, item: dict) -> None:
    apps = _apps()
    alt = apps.alternative(item.get("tool") or "")
    if not alt:
        return
    item["using"] = alt["name"]
    apps.remember(item["tool"], choice=f"alternative:{alt['tool']}")
    await repin_and_tell(s)  # the lesson's AutoCAD checks look at FreeCAD now, and its steps say "in FreeCAD"
    from server.workspace import setup as S

    cat = S.CATALOG.get(alt["tool"], {})
    if cat.get("kind") == "web_app" or not cat:  # Tinkercad, Google Sheets: open it, nothing to install
        await open_url(s, alt["url"], alt["name"])
        await refresh(s, f"Using {alt['name']} instead")
        return
    rows = s.reqs if s.reqs is not None else None
    for r in rows or []:  # its offered row (setup.offer_alternatives) is chosen now: missing until it is installed
        if r.get("tool") == alt["tool"]:
            r.pop("altFor", None)
    if rows is not None and not any(r.get("tool") == alt["tool"] for r in rows):  # its own row, with Install
        row = {"tool": alt["tool"], "label": alt["name"], "kind": cat.get("kind") or "app", "needed": True, "addedRow": True,
               "why": f"Free stand-in for {item.get('label')}.", "min_version": "", "binary": cat.get("bin", ""),
               "import_name": "", "pip_name": "", "brew": "", "brew_cask": False, "url": ""}
        checked = await asyncio.to_thread(S.check, dict(row))
        row.update({k: checked.get(k) for k in ("installed", "ok", "version", "where")})
        row["install"] = {k: v for k, v in S.recipe(row, S.brew_path()).items() if k not in ("package", "licensed")}
        S.annotate([row])
        rows.append(row)
    await refresh(s, None)


async def open_url(s: Any, url: str, label: str) -> bool:
    """The vendor's / alternative's page in the default browser: https on an allowlisted host only (else the link is
    shown as text, never opened). The same rule as the setup card's Open in browser."""
    from server.safety import browser_url_allowed
    from server.safety.commands import visible

    if not url.startswith("https://") or not browser_url_allowed(url):
        log.info("setup app link not opened (not a known host): %s", url[:120])
        await s.emit("card", {**({"stepId": s.step["id"]} if s.step else {}), "kind": "answer",
                              "title": "Check this link first",
                              "body": f"I only open sites I know. Copy it if it's {label}'s page.",
                              "output": visible(url)})
        return False
    ws = getattr(s, "workspace", None)
    if ws is None:
        return False
    if os.name == "nt" and ws.run == getattr(ws, "_spawn", None):
        try:
            os.startfile(url)  # noqa: S606 - an allowlisted https URL only
        except OSError as e:
            log.warning("could not open %s: %s", url, e)
            return False
        return True
    ws.run(["open", url])
    return True


async def status(s: Any, text: str) -> None:
    """The waiting card with `text` as its body (the rows keep their own state)."""
    base = (s.pending_pick or {}).get("card") if getattr(s, "pending_pick", None) else s._setup_card
    if base:
        await s.emit("card", {**base, "body": text})


async def refresh(s: Any, note: str | None) -> None:
    """Rebuild the setup card from the same rows (their new state). Nothing left to wait on: a short passing note that
    closes itself (no buttons), and the card is no longer pending."""
    from . import setup_rows
    from . import workspace as wsmod

    if getattr(s, "pending_pick", None) and not s.reqs:  # the preflight card: same card, rows flipped
        card = (s.pending_pick or {}).get("card")
        if card:
            await s.emit("card", {**card, **({"body": note} if note else {})})
        return
    old = s._setup_card
    shown = {str(r.get("tool")) for r in (((old or {}).get("setup") or {}).get("items") or [])}
    rows = [it for it in s.reqs or [] if not shown or str(it.get("tool")) in shown or it.get("addedRow")]
    new = wsmod.setup_card(rows) if rows else None
    waiting = bool(new) and any(a in (new.get("actions") or []) for a in ("install", "have_it", "get_it", "alternative"))
    if not waiting:
        s._setup_card = None
        if note:  # Nov 24: Blender just found / installed for a Blender lesson: Open in Blender instead of the note
            from . import open_in_app

            offer = await asyncio.to_thread(open_in_app.open_card, s, list(s.reqs or []))
            await s.emit("card", offer or note_card(note))
        return
    s._setup_card = setup_rows.with_install_all(setup_rows.carry(old, new, rows) if old else new)
    if s._setup_card and getattr(s, "editor_open", False):
        wsmod.editor_opens(s._setup_card, rows)
    card = dict(s._setup_card)
    if note:
        card["body"] = note + " " + (card.get("body") or "")
    await s.emit("card", card)


def note_card(note: str) -> dict:
    """A short passing setup note ("AutoCAD found"): no buttons, so nothing waits on it, and it closes itself."""
    return {"kind": "setup", "title": note, "body": "", "actions": [], "dismissAfterMs": NOTE_MS}


def _app_rows(items: list[dict]) -> list[dict]:
    return [it for it in items if it.get("kind") != "editor" and not it.get("altFor") and it.get("needed", True)
            and _kind(it) in APP_KINDS]


def app_lesson(items: list[dict]) -> bool:
    """A lesson done in a desktop app (AutoCAD, FreeCAD...): an app row it needs, and no website to open (a web row's
    card carries Open in browser, which is worth keeping)."""
    return bool(_app_rows(items)) and not any(it.get("kind") == "web_app" for it in items)


def ready_note(items: list[dict]) -> str | None:
    """The passing note for an app lesson with nothing missing: which app it will use. None when no app row is
    settled (nothing worth saying)."""
    for it in _app_rows(items):
        label = it.get("label") or it.get("tool")
        if it.get("using"):
            return f"Using {it['using']} for this lesson"
        if it.get("ok"):
            return f"{label} is ready"
        if it.get("haveIt"):
            return f"Using your {label}"
    return None


def after_install(s: Any, tool: str) -> bool:
    """Install finished for `tool`. When it is the free alternative offered beside a licensed app (FreeCAD's own row
    beside AutoCAD, setup.offer_alternatives), the learner has chosen it: the licensed row is `using` it, remembered on
    this Mac (the next requirements scan says so too). -> True when a choice was made. Never raises."""
    try:
        apps = _apps()
        rows = _rows(s)
        alt_row = next((r for r in rows if r.get("tool") == tool and r.get("altFor")), None)
        lic = next((r for r in rows if alt_row and r.get("tool") == alt_row["altFor"]), None)
        alt = apps.alternative(str((lic or {}).get("tool") or ""))
        if not lic or not alt or alt["tool"] != tool or lic.get("installed") or lic.get("using"):
            return False
        lic["using"] = alt["name"]
        alt_row.pop("altFor", None)
        apps.remember(lic["tool"], choice=f"alternative:{tool}")
        return True
    except Exception:  # noqa: BLE001 - a refinement: the rows keep their state
        log.exception("after_install choice failed")
        return False


async def on_front(s: Any, app: str) -> bool:
    """An app came to the front: if it is a setup row still waiting (AutoCAD after Get it), re-check and flip it.
    One re-check per app per FRONT_RECHECK_S, kept on the session (a new session or lesson re-checks at once).
    -> True when a row flipped."""
    if not app or s._setup_card is None:
        return False
    apps = _apps()
    hits = [it for it in s.reqs or [] if _waiting(it) and apps.matches_front(it, app)]
    flipped = False
    now = s.clock()
    epoch = getattr(s, "lesson_epoch", None)
    held = getattr(s, "_app_front_t", None)  # (lesson epoch, {tool: last re-check time})
    if not (isinstance(held, tuple) and held[0] == epoch):
        held = s._app_front_t = (epoch, {})
    last: dict[str, float] = held[1]
    for it in hits:
        key = str(it.get("tool"))
        if now - last.get(key, -1e9) < FRONT_RECHECK_S:
            continue
        last[key] = now
        found = await _recheck(it)
        if found.get("installed"):
            _flip(it, found)
            apps.remember(key, installed=True, version=it.get("version") or "", where=it.get("where") or "")
            flipped = True
            await refresh(s, f"{it.get('label') or key} found")
    return flipped


def apply_choice(s: Any) -> bool:
    """What the learner chose moves the lesson's app pin (app_lesson.repin): `using` FreeCAD -> checks and targets
    pinned to "AutoCAD" look at FreeCAD and the copy says "in FreeCAD"; "I have it" with no AutoCAD found -> the pin
    goes (the judge decides). Called after each choice, after the setup scan, and at each step start (a progressive
    build's new steps arrive pinned to AutoCAD). Idempotent; never raises. -> True when the lesson changed."""
    g = getattr(s, "graph", None)
    if not g:
        return False
    try:
        from server.lesson import app_lesson

        apps = _apps()
        changed = False
        for it in s.reqs or []:
            if _kind(it) not in APP_KINDS or it.get("kind") == "editor":
                continue
            tool = str(it.get("tool") or "")
            if it.get("using"):
                alt = apps.alternative(tool) or {}
                changed |= app_lesson.repin(g, tool, app_lesson.alternative_window(alt.get("tool") or ""), str(it["using"]))
            elif it.get("haveIt") and not it.get("installed"):
                changed |= app_lesson.repin(g, tool, None, None)
        return changed
    except Exception:  # noqa: BLE001 - a refinement: the lesson runs with its pins as they were
        log.exception("app choice re-pin failed")
        return False


async def repin_and_tell(s: Any) -> None:
    """apply_choice, then the drawer's step titles follow (lesson.updated merges steps by id). Never raises."""
    if not apply_choice(s):
        return
    try:
        steps = list(getattr(s, "steps", None) or [])
        lesson = (s.graph or {}).get("lesson") or {}
        await s.emit("lesson.updated", {"steps": [s._step_summary(st, i) for i, st in enumerate(steps)],
                                        "complete": lesson.get("complete") is not False})
    except Exception:  # noqa: BLE001
        log.exception("lesson.updated after an app choice failed")


def context_line(s: Any) -> str:
    """apps.context_line for the coach: which app this lesson works in and what this Mac has ("" for a code lesson)."""
    try:
        return _apps().context_line(list(s.reqs or []))
    except Exception:  # noqa: BLE001
        return ""

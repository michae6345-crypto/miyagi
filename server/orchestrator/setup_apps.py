"""The setup card's app rows: "I have it", "Get it", "Try <free alternative>", and noticing the app (Nov 22).

Michael's AutoCAD lesson: the card said "Missing: autocad. Install now?" with only Skip, and nothing could get AutoCAD.
server.workspace.apps now classifies every row (package / free_app / licensed_app / web_app); a licensed app is never
installed. Its row offers:

  have_it      re-check this Mac (folders + Spotlight). Found: the row flips to installed. Not found: the learner's
               word stands (haveIt), kept per Mac so the next lesson doesn't ask again
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
    else:  # the learner's word stands (another folder, a VM, a school machine): never asked again on this Mac
        item["haveIt"] = True
        apps.remember(item["tool"], haveIt=True)
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
    from server.workspace import setup as S

    cat = S.CATALOG.get(alt["tool"], {})
    if cat.get("kind") == "web_app" or not cat:  # Tinkercad, Google Sheets: open it, nothing to install
        await open_url(s, alt["url"], alt["name"])
        await refresh(s, f"Using {alt['name']} instead")
        return
    rows = s.reqs if s.reqs is not None else None
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
        if note:
            await s.emit("card", {"kind": "setup", "title": note, "body": "", "actions": [], "dismissAfterMs": NOTE_MS})
        return
    s._setup_card = setup_rows.with_install_all(setup_rows.carry(old, new, rows) if old else new)
    if s._setup_card and getattr(s, "editor_open", False):
        wsmod.editor_opens(s._setup_card, rows)
    card = dict(s._setup_card)
    if note:
        card["body"] = note + " " + (card.get("body") or "")
    await s.emit("card", card)


_last_front: dict[str, float] = {}


async def on_front(s: Any, app: str) -> bool:
    """An app came to the front: if it is a setup row still waiting (AutoCAD after Get it), re-check and flip it.
    -> True when a row flipped."""
    if not app or s._setup_card is None:
        return False
    apps = _apps()
    hits = [it for it in s.reqs or [] if _waiting(it) and apps.matches_front(it, app)]
    flipped = False
    now = s.clock()
    for it in hits:
        key = str(it.get("tool"))
        if now - _last_front.get(key, -1e9) < FRONT_RECHECK_S:
            continue
        _last_front[key] = now
        found = await _recheck(it)
        if found.get("installed"):
            _flip(it, found)
            apps.remember(key, installed=True, version=it.get("version") or "", where=it.get("where") or "")
            flipped = True
            await refresh(s, f"{it.get('label') or key} found")
    return flipped


def context_line(s: Any) -> str:
    """apps.context_line for the coach: which app this lesson works in and what this Mac has ("" for a code lesson)."""
    try:
        return _apps().context_line(list(s.reqs or []))
    except Exception:  # noqa: BLE001
        return ""

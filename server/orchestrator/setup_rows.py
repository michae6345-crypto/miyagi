"""t9 V12: the setup card's rows stay put while it installs, and "Install all".

Test 9: the setup card installed one package at a time and its rows moved while installing, so the next Install button
slid out from under the cursor. A re-sent setup card now keeps the rows it was first sent with (same tools, same
order; each row's ok / installed / version flips in place) and, while it still offers Install, the body above them
(the progress is on the rows: setup.progress). `install_all` installs every missing row one after another.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("orchestrator.session")

INSTALL_METHODS = ("pip", "brew", "brew_cask", "vscode_ext")  # vscode_ext: a notebook lesson's VS Code extensions  # what Install runs here (download / open / none have no Install)
# needed: a free alternative's offered row (FreeCAD beside AutoCAD) hides once AutoCAD is found or "I have it"
ROW_STATE = ("installed", "ok", "version", "unknown", "needed")
APP_STATE = ("actions", "haveIt", "using")  # setup_apps: a row's buttons and what the learner chose


def installable(card: dict | None) -> list[dict]:
    """The card's rows that Install (all) would install: needed, not ok, a real install recipe. Never a licensed app's
    free alternative the learner hasn't chosen (FreeCAD beside AutoCAD: only its own Install press gets it)."""
    rows = ((card or {}).get("setup") or {}).get("items") or []
    offered = {str((r.get("alternative") or {}).get("tool")) for r in rows
               if isinstance(r.get("alternative"), dict) and not r.get("using")}
    return [r for r in rows if r.get("needed") and not r.get("ok") and str(r.get("tool")) not in offered
            and ((r.get("install") or {}).get("method") in INSTALL_METHODS)]


def carry(old: dict | None, new: dict | None, status: list[dict] | None) -> dict | None:
    """The re-built card `new`, with `old`'s rows (status from `status`, the full fresh setup check) and, while it still
    offers Install, `old`'s body."""
    if not old or not new or old.get("kind") != "setup" or new.get("kind") != "setup":
        return new
    orows = ((old.get("setup") or {}).get("items")) or []
    nsetup = dict(new.get("setup") or {})
    if not orows or not nsetup:
        return new
    fresh = {str(it.get("tool")): it for it in list(status or []) + list(nsetup.get("items") or [])}
    rows = []
    for r in orows:
        f = fresh.get(str(r.get("tool")))
        row = {**r, **{k: f.get(k) for k in ROW_STATE if f is not None and k in f}} if f is not None else dict(r)
        if f is not None:  # apps.py's row fields follow the fresh row, and go when it no longer has them
            for k in APP_STATE:
                if k in f:
                    row[k] = f[k]
                else:
                    row.pop(k, None)
        rows.append(row)
    known = {str(r.get("tool")) for r in orows}
    rows += [r for r in nsetup.get("items") or [] if str(r.get("tool")) not in known]
    nsetup["items"] = rows
    out = {**new, "setup": nsetup}
    if "install" in (out.get("actions") or []) and old.get("body"):
        out["body"] = old["body"]
    return out


def with_install_all(card: dict | None) -> dict | None:
    """"Install all" on a setup card with two or more rows to install (the app's own rule, desktop test 9 A8)."""
    if not card or card.get("kind") != "setup":
        return card
    acts = [a for a in card.get("actions") or [] if a != "install_all"]
    if len(installable(card)) >= 2 and "install" in acts:
        acts.insert(acts.index("install"), "install_all")
        setup = dict(card.get("setup") or {})
        setup["actionLabels"] = {**(setup.get("actionLabels") or {}), "install_all": "Install all"}
        return {**card, "actions": acts, "setup": setup}
    return {**card, "actions": acts}


async def install_all(s: Any) -> None:
    """Every row the setup card would install, one after another (the same path as each row's Install; one install per
    tool). Rows waiting their turn say so. Stops when the card is skipped."""
    tools = [r["tool"] for r in installable(s._setup_card) if r.get("tool") not in s._installing]
    log.info("install all: %s", tools)
    from . import setup_gate

    gated = setup_gate.applies(s)
    if tools and gated:  # Nov 25: the gate counts them all from the start ("2/4")
        g = setup_gate.gate(s)
        for t in tools:
            item = next((it for it in s.reqs or [] if it.get("tool") == t), None)
            g.queue(t, (item or {}).get("label") or t, setup_gate.optional(item))
        await setup_gate.publish(s)
    for t in tools[1:]:
        await s.emit("setup.progress", {"tool": t, "line": "Waiting to install"})
    for t in tools:
        if s._setup_card is None:  # Skip: the rest stay as they are
            for rest in tools[tools.index(t):]:
                await s.emit("setup.progress", {"tool": rest, "done": True})
            if gated:
                g = setup_gate.gate(s)
                for rest in tools[tools.index(t):]:
                    g.finish(rest, {"skipped": True, "cancelled": True})
                await setup_gate.publish(s)
            return
        item = next((it for it in s.reqs or [] if it.get("tool") == t), None)
        if item is not None and item.get("ok"):
            if gated:
                await setup_gate.settle(s, t)
            continue
        await s._install(t, item=item)
        if gated:  # an install that returned early (unknown tool...) leaves no row waiting
            await setup_gate.settle(s, t)

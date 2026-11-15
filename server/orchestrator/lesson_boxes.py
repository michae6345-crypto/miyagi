"""LessonSession's lesson-mode boxes after desktop test 5 (Nov 15): ONE box on screen, on the line that matters.

Test 5 ("Build a neural network in Python", Just teach me): Explain put FOUR boxes up ("Type it here" on a blank line
+ three "Change this line"); the fix box on line 20 alternated with the step's "Type it here" for 16 s; Show me dimmed
the screen over a blank line with no card; step 3's box sat inside the sigmoid_slope block and step 6's on W2's line.
The Haiku targeter "moved" the engine's boxes with confidence 0.7-0.85 every time, and it was wrong every time.

- (a) _one_box: a lesson's card / off-track carries no `targets` (the app draws each as one more box beside the
  spotlight); the engine's spotlight is the one box. Explain keeps the one line _show_where boxed (session.action).
- (b) _fix_active / _fix_box / _fix_follow: while a fix / off-track / Not-yet target is active, the line to fix is THE
  box (owner "offtrack", file-exact, no targeter) and the step's own box never replaces it; it follows the fix.
- (c) _lesson_show_me: Show me on a code step = at most one box on the right line + ALWAYS an answer card.
- (d) _insert_plan / _insert_spot: the step's box goes where the file says new code goes (spot_lines.insert_line);
  the targeter may move it only when LINE_MOVE_CONF sure and never into a def / block or onto code
  (_line_move_ok, target.verdict move_conf); a vision pick obeys the same rule (_vision_ok). t4's step-start box
  (_start_box) takes that row too (_start_line_box) and its Haiku refine obeys the same rule (_refine_start_box).

A mixin: every method runs on the LessonSession (self._show_spot, self._code_progress, ...).
"""
from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path

from . import spot_lines

log = logging.getLogger("orchestrator.session")


class LessonBoxes:
    # t5 (desktop test 5): ONE box at a time, on the line that matters. The insertion box comes from the file (after
    # its last line, or below the step anchor's block); the Haiku targeter may move a line box the file decided only
    # when it is LINE_MOVE_CONF sure and never into a def / block or onto code (test 5's moves were 0.7-0.85 sure and
    # all wrong); a fix / off-track / Not-yet line outranks the step's own box (_fix_active).
    LINE_MOVE_CONF = 0.9
    BELOW_CAPTION = "Type below this line"
    # a target that says where new code goes relative to it: "Type below sigmoid_slope", "Type below this line",
    # the curated lesson's "Paste the network under this line"; not "Loop goes here" / "Type add() here"
    _BELOW_WORDS = re.compile(r"^\s*(?:\w+\s+){0,3}(?:below|under|after)\b", re.I)

    @staticmethod
    def _line_meta(prog: dict, pitch: float) -> dict:
        """A file line box's facts for _show_spot and Show me's card; popped before the box is sent. Only an insertion
        row ("insert") may be moved by the targeter; the line to change / where typing goes on / the line above are
        exact (no Haiku check at all)."""
        return {"path": str(prog["path"]), "line": int(prog["line"]), "pitch": max(14.0, min(40.0, pitch or 20.0)),
                "move": prog.get("kind") == "insert", "kind": prog.get("kind"),
                "expect": prog.get("expect") or ""}

    def _step_lines(self, step: dict) -> tuple[Path | None, list[str]]:
        """The step's file and its lines: VS Code's unsaved buffer when the companion has it, else the file on disk."""
        from . import workspace as wsmod

        file = self._step_file(step)
        p = wsmod.resolve_file(self.workdir, file) if file and self._real_file(file) else None
        if p is None:
            return None, []
        try:
            return p, (self._unsaved_texts([p])[0] or p.read_text(errors="replace")).splitlines()
        except OSError:
            return p, []

    def _insert_anchor(self, step: dict, lines: list[str]) -> int | None:
        """t5 (d): the file line of the step's "Type below <x>" target (one whose text isn't the step's own code, e.g.
        step 3's `return s * (1 - s)`); None when no such target is in the file (the code goes after its last line);
        -1 when the first such target marks another kind of place ("Loop goes here": that target's own box decides)."""
        from . import workspace as wsmod

        code = re.sub(r"\s+", "", step.get("code") or "")
        for t in step.get("targets") or []:
            m = (t.get("match") or "").strip()
            if not m or re.sub(r"\s+", "", m) in code:
                continue
            n = wsmod.anchor_line("\n".join(lines), m)
            if n is None:
                continue  # not in the file (yet, or mistyped): after the file's last line
            return n if self._BELOW_WORDS.match(t.get("caption") or "") else -1
        return None

    def _insert_plan(self, step: dict) -> dict | None:
        """t5 (d): where a lesson code step none of whose code is typed yet goes, from the file alone: the row after
        the step anchor's block (step 3: below sigmoid_slope, never inside it), else after the file's last non-blank
        line (step 6: the end of the file, not W2's line). {path, lines, ins, above} (1-based; above 0 = empty file).
        None: not such a step (a run step, its code is typed, no file, a target of another kind)."""
        if (not self.lesson_mode or self._run_command(step) or not (step.get("code") or "").strip()
                or self._code_progress(step) is not None):
            return None
        p, lines = self._step_lines(step)
        anchor = self._insert_anchor(step, lines) if p is not None else -1
        if anchor == -1:
            return None
        ins, above = spot_lines.insert_line(lines, anchor)
        return {"path": p, "lines": lines, "ins": ins, "above": above}

    async def _insert_spot(self, step: dict, show_me: bool = False, plan: dict | None = None) -> dict | None:
        """t5 (d): the box at _insert_plan's row: "Type it here". When that row already holds code, or for Show me
        (never a dim over an empty row), the line above it: "Type below this line". None: not such a step, or the
        row isn't on screen (gutter and OCR both missed; no model call here)."""
        plan = plan or self._insert_plan(step)
        if plan is None:
            return None
        p, lines, ins, above = plan["path"], plan["lines"], plan["ins"], plan["above"]
        below = bool(above) and (show_me or (ins <= len(lines) and bool(lines[ins - 1].strip())))
        line, kind, cap = (above, "below", self.BELOW_CAPTION) if below else (ins, "insert", self.TYPE_CAPTION)
        prog = {"path": p, "line": line, "kind": kind, "expect": lines[above - 1].strip() if above else ""}
        spot = await self._progress_spot(step, prog, caption=cap)
        if spot is None and above and (txt := spot_lines.unique_text(lines, above)):
            spot = self._row_spot(step, txt, cap, prog, down=not below)  # the gutter missed (a short file)
        return spot

    async def _start_line_box(self, gen: int, step: dict, plan: dict) -> bool:
        """t5 (d), t4's _start_box for a step whose new code goes where the file says (_insert_plan): THE row from the
        file (_insert_spot: Accessibility / gutter, else OCR of the unique line above), shown at once; then
        _refine_start_box lets the targeter move only an insertion row, only LINE_MOVE_CONF sure, only onto an empty
        row outside every def / block. Test 5: step 3's start box was a fuzzy OCR hit of `return s * (1 - s)` (line
        24, inside sigmoid_slope), and Haiku moved step 6's right box (line 43) onto W2's line at 0.8.
        -> placed (or already up)."""
        spot = await self._insert_spot(step, plan=plan)
        if spot is None or gen != self.step_gen or self.passed or self._offtrack_box() == "up" or self._fix_active():
            return False
        pane = await asyncio.to_thread(self._code_pane)
        if gen != self.step_gen or self.passed:
            return False
        r = spot["rect"]
        if pane is not None:  # E3: a code step's line box stays inside the editor pane (never the terminal / Chat)
            if not self._in_pane(r, pane):
                return False
            x, x2 = max(r["x"], pane["x"]), min(r["x"] + r["w"], pane["x"] + pane["w"])
            r = {**r, "x": x, "w": max(8.0, x2 - x)}
        spot = {**spot, "rect": r}
        old = self.spot_rect
        if old and self._spot_caption == spot.get("caption") and all(
                abs(r[k] - old[k]) <= self.SPOT_MOVE_PX for k in ("x", "y", "w", "h")):
            return True  # the same box is already up: no re-send, no second Haiku question
        await self._show_spot(spot, owner="step")  # at once: not after the ~2 s Haiku check
        if self.spot_rect is not r:
            return False
        await self._refine_start_box(gen, spot, pane)
        return True

    def _row_spot(self, step: dict, text: str, caption: str, prog: dict, down: bool) -> dict | None:
        """The editor row of `text` (a line of the file no other line repeats, OCR'd in VS Code), or the row under it
        (`down`). No model call; real reader only."""
        if getattr(self.screen, "reader", None) is None or self._editor_off_screen():
            return None
        hit = self.screen.locate(re.escape(text), "Code")
        if not hit or "\n" in (hit.get("matched") or "") or self._chrome_hit(hit) or self._long_hit(hit, text):
            return None
        r = hit["rect"]
        lh = max(14.0, float(r["h"]) - 3.0)  # E24: the row pitch (locate_match's box is the row + 3 pt)
        rect = {"x": float(r["x"]), "y": float(r["y"]) + (lh if down else 0.0),
                "w": max(float(r["w"]), 320.0) if down else float(r["w"]), "h": float(r["h"])}
        return {"rect": rect, "caption": caption, "app": "Code", **self._snippet(step),
                "_line": self._line_meta(prog, lh)}

    def _line_move_ok(self, meta: dict, det: dict, moved: dict) -> bool:
        """t5 (d): may the targeter's pick replace a line box the file decided? Only an insertion row (never the line to
        change or the line above), one row high, landing on an empty row outside every def / block of the file (test
        5: blank lines 16-17 above the typed sigmoid, line 24 inside sigmoid_slope, W2's line 33 for step 6)."""
        if not meta.get("move"):
            return False
        pitch = float(meta.get("pitch") or 20.0)
        if moved["h"] > 1.8 * pitch:
            return False
        dl = round(((moved["y"] + moved["h"] / 2) - (det["y"] + det["h"] / 2)) / pitch)
        try:
            p = Path(meta["path"])
            lines = (self._unsaved_texts([p])[0] or p.read_text(errors="replace")).splitlines()
        except OSError:
            return False
        return not spot_lines.inside_block(lines, int(meta["line"]) + dl)

    def _vision_ok(self, step: dict, res: dict) -> bool:
        """t5 (d): a Haiku pick boxes a lesson code step's line only when it is LINE_MOVE_CONF sure and its row (the
        gutter's line number) is an empty row outside every def / block."""
        conf = float(res.get("confidence") or 0.0)
        line = res.get("line")
        _p, lines = self._step_lines(step)
        if conf < self.LINE_MOVE_CONF or (isinstance(line, int) and lines and spot_lines.inside_block(lines, line)):
            log.info("vision spot: %s (%.2f) is unsure or inside a block; no box", res.get("label"), conf)
            return False
        return True

    def _fix_active(self) -> bool:
        """t5 (b): a fix / off-track / Not-yet target is active on this lesson step while checks still fail: the
        diagnosis stands, a "Not yet" card covers checks that still fail, or a diagnosis's streamed box is up while
        it runs. The step's own box ("Type it here", "Finish this function") waits: one box, no alternation."""
        if not self.lesson_mode or self.step is None or self.passed:
            return False
        failing = {r.get("checkId") for r in self.last_failed or [] if r.get("checkId")}
        if not failing:
            return False
        if self.last_offtrack:
            return True
        ny = getattr(self, "_notyet", None)
        if ny is not None and ny[0] == self.step_gen and (not ny[1] or ny[1] & failing):
            return True
        own = getattr(self, "_spot_owner", None)
        return bool(self.coaching and self.spot_rect is not None and own is not None and own[0] == "offtrack"
                    and own[1] == self.step_gen)

    async def _fix_box(self, gen: int, step: dict) -> bool:
        """t5 (b): while a fix is active the line to fix is THE box (owner "offtrack", file-exact, no targeter). ->
        handled: that box is up, or the step's code is typed and no line to fix is found (no box beats the step's
        "Type it here" over the fix). Nothing typed yet: the step's own box is the answer (-> False)."""
        if not self._fix_active():
            return False
        spot = await self._change_spot(step)
        if spot is None:
            return self._code_progress(step) is not None
        if gen == self.step_gen and not self.passed:
            self._fix_at = (gen, spot["_line"]["line"], spot.get("caption"))  # _fix_follow keeps it on the right line
            await self._show_spot(spot, steady=True, owner="offtrack", verify=False)
        return True

    def _fix_follow(self) -> None:
        """t5 (b), on a frame, at most every 3 s, no model call: a fix / off-track / Not-yet target became active while
        the step's own box is up -> the line to fix replaces it; the fix box _fix_box put up is on a line that's fixed
        now (the next one differs) or the fix is over -> it goes and _lesson_spot places the right box."""
        step, own = self.step, getattr(self, "_spot_owner", None)
        if (not self.lesson_mode or step is None or self.passed or self.spot_rect is None or own is None
                or own[1] != self.step_gen or getattr(self, "_lesson_spot_gen", None) == self.step_gen
                or self.clock() - getattr(self, "_fix_follow_t", -1e9) < 3.0):
            return
        at = getattr(self, "_fix_at", None)
        if own[0] == "step":
            if not self._fix_active() or self._code_progress(step) is None:
                return
            clear = False
        elif own[0] == "offtrack" and at is not None and at[0] == self.step_gen and self._spot_caption == at[2]:
            t = self._fix_target(step) if self._fix_active() else None
            if t is not None and t["line"] == at[1]:
                return  # still the line to fix
            clear = True
        else:
            return
        self._fix_follow_t = self.clock()
        self._spawn(self._refix(self.step_gen, step, clear), timer=True)

    async def _refix(self, gen: int, step: dict, clear: bool) -> None:
        if clear:
            async with self._spot_lock():
                if self.spot_rect is not None and gen == self.step_gen:
                    await self.emit("spotlight", {"clear": True})
        await self._lesson_spot(gen, step, tries=1)

    def _one_box(self, type_: str, payload: dict) -> dict:
        """t5 (a), lesson mode: ONE box on screen, the engine's spotlight. A card's / off-track's `targets` are not sent
        (the app draws each as one more box while a spotlight is up: Explain's three "Change this line" boxes beside
        "Type it here"); the engine already spotlights the one that matters. A "Not yet" card marks its checks."""
        if type_ == "card" and self.step is not None and payload.get("stepId") in (None, self.step["id"]) and (
                payload.get("title") == "Not yet" or payload.get("verdict") == "not_done"):
            self._notyet = (self.step_gen, {r.get("checkId") for r in self.last_failed or [] if r.get("checkId")})
        if "targets" in payload:
            payload = {k: v for k, v in payload.items() if k != "targets"}
        return payload

    async def _lesson_show_me(self, gen: int, step: dict) -> None:
        """t5 (c) Show me on a lesson code step: at most ONE box, on the line that matters, and ALWAYS an answer card
        saying what goes there (test 5: a dim over a blank line and no card). The line to change, else where typing
        goes on, else the line the step's code goes below; all from the file, no model call."""
        prog = self._code_progress(step)
        spot = await self._change_spot(step) if (prog is not None or self._fix_active()) else None
        if spot is None and prog is None:
            spot = await self._insert_spot(step, show_me=True)
        if gen != self.step_gen or self.passed:
            return
        meta = dict((spot or {}).get("_line") or {})
        if not meta and prog is not None:  # the line isn't on screen: the card still says where, from the file
            meta = {"kind": prog["kind"], "line": prog["line"], "expect": prog["expect"]}
        elif not meta:
            plan = self._insert_plan(step)
            if plan is None:
                _p, lines = self._step_lines(step)
                plan = {"lines": lines, "ins": spot_lines.last_code_line(lines) + 1,
                        "above": spot_lines.last_code_line(lines)}
            above = plan["above"]
            meta = {"kind": "below" if above else "insert", "line": above or plan["ins"],
                    "expect": plan["lines"][above - 1].strip() if above else ""}
        name = Path(self._step_file(step) or "").name or "your file"
        kind, n, expect = meta.get("kind"), meta.get("line"), spot_lines.clip(meta.get("expect") or "", 10)
        actions = ["apply_fix"]
        if kind == "done":
            title, actions = "It's all typed", ["check_step"]
            body = f"All of this step's code is in {name}. Save it, then press Check."
        elif kind == "change":
            title = f"Fix line {n}"
            body = f"Line {n} of {name} should read: `{expect}`" if expect else f"Delete line {n} of {name}."
        elif kind == "next":
            title, body = f"Type line {n} next", f"Line {n} of {name} comes next: `{expect}`"
        elif kind == "below":
            title = f"Type below line {n}"
            body = f"Start a new line under line {n} of {name}" + (f" (`{expect}`)" if expect else "") + \
                " and type this step's code there."
        else:
            title, body = f"Type on line {n}", f"Type this step's code on line {n} of {name}."
        if spot is not None:
            self._action_spot = True
            await self._show_spot(spot, owner="answer")
        await self._emit_card({"stepId": step["id"], "kind": "answer", "title": title, "body": body,
                               "actions": actions}, window_s=2.0)

    def _fix_target(self, step: dict) -> dict | None:
        """_change_spot's line from the files alone: {path, line, kind, expect, caption[, yours]} or None."""
        clip = spot_lines.clip  # the caption stays <= 8 words (short_caption would swap it for a pointer)
        diff = (self.last_offtrack or {}).get("diff") or {}
        pair = spot_lines.first_change(diff.get("yours"), diff.get("expected"))
        if pair is not None:
            p, lines = self._step_lines(step)
            n = spot_lines.find_line(lines, pair[0]) if p is not None else None
            if n is not None:  # the diagnosed line is still in the file (not fixed yet)
                return {"path": p, "line": n, "kind": "change", "expect": pair[1] or "", "yours": pair[0],
                        "caption": f"Change to: {clip(pair[1])}" if pair[1] else "Delete this line"}
        prog = self._code_progress(step)
        if prog is None or prog["kind"] == "done":
            return None
        lead = "Change to" if prog["kind"] == "change" else "Type next"
        return {**prog, "caption": f"{lead}: {clip(prog['expect'])}"}

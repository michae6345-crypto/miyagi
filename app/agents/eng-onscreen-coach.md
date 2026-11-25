# eng-onscreen-coach (on-screen coach: circle it, write the step there)

**Status:** implemented, pushed, not merged · **Branch:** `claude/eng-onscreen-coach` (from `origin/integration/live`) · **Engine only** (no app code, no port)

## Goal
In a desktop-app lesson (Blender, AutoCAD, Photoshop...: `graph.lesson.app`, never VS Code or a code lesson) miyagi finds the thing to act on, circles it on screen and writes the step beside it, so the learner never has to read the side panel. It does this at a step start, on a "Not yet", and on Show me (the "where?" ask, plus a short typed "where ...?"). One `annotate {marks: [{id, why: "point", stepId, label, text, keys, x, y, w, h}]}` in screen points. Placing the circle is free: no model call.

## Files
- `shared/contracts/events.ts` / `.py` (commit 1, additive): `LessonApp {tool, label, using?}`; `Annotation.text` / `keys`; `lesson.ready lesson.app`; a text mark ignores `holdMs`.
- `server/screen/app_target.py` (new): the free resolver chain, bridge -> AX -> OCR -> None, behind a confidence gate.
- `server/orchestrator/onscreen_coach.py` (new): the policy (when to mark, dedupe, clear, copy: text / label / keys).
- `server/orchestrator/session.py`: 1-3 line hooks (`lesson.ready lesson.app`, start_step, `_emit_card` Not yet, Show me, the ask branch, `_pass_step` / `_end_lesson` / `load_graph` clear, `_show_spot` one pointer). `annotate` counts as an answer to a press.
- `server/screen/README.md` ("App targets"), `server/coach/README.md` (why "point" marks now exist).
- Tests: `server/screen/tests/test_app_target.py`, `server/orchestrator/tests/test_onscreen_coach.py`.

## Contract
- **Out** (engine -> app): `lesson.ready.lesson.app {tool, label, using?}` for an app lesson only; `annotate {marks: [ONE mark]}` with `why: "point"`, `stepId`, `label` (<= 4 words), `text` (<= 12 words), `keys` (<= 3, Mac keycaps: "⇧A", "⌘S", "Tab", "Numpad 1"); `annotate {clear: true}` once on step.passed / skip / lesson.ended / a new lesson while a mark is up.
- A mark with `text` is not timed: it stays until the step passes or changes, the learner reaches it, Esc, lesson.ended or a clear.

## Rules
- One mark per annotate. Never from idle, the evaluate loop or ticks (a Not yet re-circles only when it answers a press).
- Step start: first look at ~0.8 s, up to 3 retries within ~4 s; stops on a step change / pass; never for a replay or a restore; waits out "Before you start".
- Never the same mark twice in a row: same step + rect within 12 pt + same text is skipped on a step-start retry, and on a Not yet within 8 s. Show me always re-sends with a new id.
- No rect -> no mark. Show me then sends the existing where card (words).
- While a step's mark is up the session sends no spotlight rect for it (one pointer at a time).
- Resolves run off the loop (`asyncio.to_thread`).

## Blender bridge
`origin/claude/eng-blender-bridge` landed while this lane ran: `blender_ext.ui_rects()` returns Blender's raw `/ui` (`{origin: "bottom-left", pixel_size, windows: [{x, y, width, height, areas: [{type, ui_type, x, y, width, height}]}]}` in Blender pixels). `app_target.bridge_shape` places those areas on the Blender window from the frame (bottom-aligned, scale from the width) and also takes the points shape `{window, areas, objects}`. The import is inside a function; absent / None / a raise skips to AX.

## Done when
1. First commit is `contract:` touching only `shared/contracts/events.ts` and `.py`.
2. py_compile of the contract, session, onscreen_coach and app_target passes.
3. The two new test files pass offline; the orchestrator / screen / coach / shared suites show no new failures against `origin/integration/live`.

## Core requests
_None._ The app lane (`app-onscreen-coach`) reads `lesson.app` and the new Annotation fields defensively.

## Notes
- Out of scope: `server/lesson/app_lesson.py`, `server/workspace/blender*.py`, `blender-addon/`, `server/screen/ax.py` / `reader.py` / `lines.py`, `features/buddy`, any app code.
- Later (`claude/eng-blender-targets`): richer bridge targets (object rects, header buttons) extend `app_target.bridge_target` only.

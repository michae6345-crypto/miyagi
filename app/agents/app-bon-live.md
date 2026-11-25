# app-bon-live

**Status:** app part done (Nov 24) · **Branch:** `michael/app-bon-live` (from `michael/app-ui-v4`) · **Lane:** bon-live-app

## Goal
In a real lesson, bon follows the learner: it flies to each step's target, perches beside it, points and circles it
(held about 10 s), and moves to the next step's target when the step changes. Every piece of Adrian's buddy UI that is
meant to show in a lesson is wired into the real overlay, not only the stage. One bon, calm, reduced motion respected.

## Why it did not happen live (trace, Nov 24)
The **engine** stopped sending spotlight boxes on Nov 21: its screen reader never starts (`screen_bridge.py:75`
subscribes from a worker thread without the loop), so in a VS Code lesson it sends only `spotlight {clear}` at each
step start. bon only flies on a spotlight box or an engine `annotate`. That fix is the engine lane's (integration/live),
not this branch. The stage hid it because its mock sends a box straight after `step.started`.
This branch is the **app part** of the trace's fix plan (section D).

## What changed (app only; no contract change)
1. **On-screen coach text with bon drawing (B4).** `annotate/BuddyLayer.tsx` no longer returns `null` when bon is in
   the build: it draws only the coach's text box (no stroke, no label; `drawnParts`, `buddyInBuild`), placed with no
   island branch to dodge (`alone`). Its store already has the right lifetime (untimed, step-scoped, hidden while quiet).
   bon (`buddy/pointing.ts`, `buddy/marks.ts`) now keeps a mark's `text` and matches that store:
   - a text mark is not timed (no 6 s / holdMs fade); plain marks beside it still fade (`timedMarks`);
   - it goes on step.passed, another step, Esc, annotate {clear}, lesson end, or the learner reaching it;
   - a text mark for a step that is not running is not drawn and does not replace what is;
   - quiet (lesson.paused, a blocker, status idle) hides text marks and live again brings them back with no re-send;
   - "Not yet" for this step (card verdict not_done) or a Show me press lets the next annotate draw a reached mark
     again (`askAgain`, wire.ts).
   For a text mark bon perches on the **left** (`trip.ts perchPrefer`), so the text box keeps the right, and bon does
   not also say the label (`markWords`): one set of words per mark, as before.
2. **bon no longer hides the line numbers the engine reads (B6).** The body span in `Companion.tsx` is no longer
   `data-ui` (it has no words). `overlay.bounds` made the engine's reader drop and black out every line under it, and
   bon perches left of a code row, on that row's gutter. The bubble (words) stays `data-ui`. The perch side for
   spotlight boxes is unchanged (left: the spotlight caption has the right).
3. **Diagnostics.** `data-buddy-why` on bon's layer root: `no-mark` (nothing reached bon: engine silence),
   `off-display` (marks came, none on this display), `stand-down`, `held`, `follow` (`trip.ts buddyWhy`). Perf
   counters in `spotlit`: `buddy.spotlit`, `buddy.spotlit.engine-up` / `.undrawable` / `.same`, and `buddy.annotate`
   (read with `__miyagiPerf()` in devtools, or `?perf=1`).
4. **A test that would have caught the gap.** `test/bonLive.test.ts` loads the real `features/annotate` and
   `features/buddy` feature definitions (as the registry mounts them) and drives them with the event shapes the live
   engine sends:
   - VS Code: `step.started`, `spotlight {clear}`, `spotlight {rect, caption, app:"Code", matched, snippet}` with VS
     Code in front gives one bridged mark, held 10 s; the next step's box moves it; another app in front gives none;
   - engine silence (only `{clear}`, as on Nov 21-24) gives no mark, no `buddy.spotlit`, and `buddy-why` = `no-mark`;
   - app lesson: the coach's annotate (`id, why:point, stepId, label, text, keys`, no holdMs) stays past 6 s in both
     bon and the text box, pause/resume hides and restores both, step.passed clears both.
   Plus unit cases in `test/buddyDraws.test.ts` (the coach's text mark).

## Not changed (decisions for Michael, not bugs)
- `PTT_ENABLED` stays false (`common/flags.ts`): push to talk and circle-to-ask stay off until consent covers them.
  bon's listen/think/answer and circle-to-ask marks need it.
- Multi-display: the overlay still covers the primary display only. bon now says `off-display` when that is why.
- Spotlight boxes still carry no label, so bon says nothing at a step target (the caption speaks).

## Live check after the engine fix lands
In a VS Code lesson, devtools on the overlay: `document.querySelector('[data-buddy]').dataset.buddyWhy` should go
`held` at each step start, and `__miyagiPerf()['buddy.spotlit']` should grow. `no-mark` with `buddy.spotlit` at 0 is
the engine not sending boxes (check engine.log for "screen up …: True", Accessibility for the engine, the VS Code
companion at 0.0.7+). `off-display` is VS Code on a second display.

## Checks run (offline)
- `npm run typecheck`: clean.
- Full node suite: 1121 / 1121 pass.
- Headless stage shots (Playwright, `~/miyagi/tools/playwright/bon-live.mjs 5293 app/agents/shots`):
  - `shots/bon-live-vscode-{light,dark}.png`: a lesson step; the engine-shaped `{clear}` then box with
    `app:"Code"` on the next row; bon has followed to it, perched and circling (bridged, `held`, body not data-ui).
  - `shots/bon-live-coach-{light,dark}.png`: the on-screen coach's mark; bon circles it from the left, the text box
    ("Press G to move the cube", keycap G) on the right, no island stroke; still up 8 s after it came.

## Core requests
_None._ (Reads `core/perf` only.)

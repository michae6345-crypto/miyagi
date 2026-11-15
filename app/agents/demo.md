# Feature: demo (offline "neural net from scratch")

Branch `adrian/demo-nn` · worktree `wt/demo-nn` · stage port 5193

## What it is
A small **Demo** button that turns the app into the in-person demo, with no engine, no API keys and no network.
Everything on screen is the real app (island, launcher, drawer, spotlight, checks, cards, diagrams, shortcut bar).
Only the engine is scripted (`mock/scenarios/demo.json`), and the topic is already chosen: **a neural net from scratch**
(NumPy, 2-4-1 network, learns XOR).

The story has one real bug in it: in step 2 the learner takes a shortcut and starts the weights at **zero**. The shapes are
right, so every check passes. Then training sits at **loss 0.2500** for all 5,000 epochs, because every hidden neuron
computes the same thing and gets the same update. miyagi catches it from the training curve, asks a guiding question,
climbs the hint ladder to the exact line, and **Fix it** retrains it down to 0.0009 → `[0 1 1 0]`.
Every number on screen comes from running the code (Python 3.12, NumPy 2.5).

## Run it
```bash
npm run dev:web
```
Open `http://localhost:5173/` and click **Demo** (menu bar, right half), or go straight to
`http://localhost:5173/?scenario=demo&clean`. Full-screen the browser (F11 / ⌃⌘F). Add `&os=win` for Windows keycaps.

## Controls (bottom-left panel)
| Key | Does |
|---|---|
| → · Space · PageDown (a clicker works) | next beat |
| A | autoplay on/off (hands-free loop for the judging table) |
| R | start over (empty desktop) |
| × | leave the demo |

You can take over at any beat: ⌘K / Ctrl+K, ⌥E / ⌥D / ⌥S / ⌥H, Check, Skip step, Fix it all answer like the real engine.
Typing any topic in the launcher builds this lesson.

## The walkthrough (talk track)
| # | Beat | What happens | Say |
|---|---|---|---|
| 1 | Ask miyagi | Launcher grows out of the island, types the topic | Say what you want to learn. |
| 2 | Just teach me | "Claude is writing your lesson" → 6 steps | Any video becomes a graded lab, or miyagi just teaches you. |
| 3 | Before you start | Drawer: what we're building, 5 concepts, the plan | The big picture first. |
| 4 | Step 1 · the data | Spotlight on where to type; code types; checks go green | It watches the screen. Right code, green. |
| 5 | Step 2 · a shortcut | Learner types `np.zeros` weights; checks pass | Shapes are right, so it passes. Remember this. |
| 6 | Step 3 · forward pass | sigmoid + forward | Two layers of weighted sums and sigmoids. |
| 7 | Ask anything | ⌘K mid-step: "why sigmoid and not relu?" → answer | Answers about this step. |
| 8 | Step 4 · explained | ⌥E: the chain rule, in this code | The hard part, in plain words. |
| 9 | Diagram | ⌥D: forward, then backward | Any step becomes a picture. |
| 10 | Step 4 · type it | backward types; green | |
| 11 | Step 5 · train | Loop types, `python nn.py` runs, loss prints 0.2500 ×5 | Every check passed. Watch the loss. |
| 12 | Off track | "Loss is stuck at 0.25", guiding question, yours vs tutorial curve, spotlight on the zeros | A question first, not the answer. |
| 13 | Hint | ⌥H → level 3: the exact line (yours vs expected), Fix it, citation | The hint ladder. |
| 14 | Fix it | Lines 8 and 10 rewrite, retrain 0.2691 → 0.0009, "Good. Now the next one." | Back on track. |
| 15 | Step 6 · test it | `[0 1 1 0]`; all six green; "You built a neural net from scratch" | Every step checked. |
| 16 | What you learned | ⌥D: skill map, what you built and what's next | Where it leads. |

About 4 minutes at a talking pace; autoplay runs it in about 3.

## How it's built
- `features/demo/lesson.ts`: the one source of truth (the file, the steps, the bug, real loss curves, the fake desktop's geometry).
- `features/demo/scenario.ts` → `scripts/demo-scenario.ts` writes `mock/scenarios/demo.json`. **Edit lesson.ts, then run
  `npx tsx scripts/demo-scenario.ts`.** Every message is a contract message; per-step triggers cover check_step,
  skip_step, explain, diagram, show_me, ask, hint (step 5: level 3) and apply_fix (step 5).
- `Desktop.tsx` + `syntax.tsx`: the learner's VS Code (Dark Modern, terminal docked right), an overlay layer at z -100,
  only when `?scenario=demo`. The terminal prints from the engine's `metric` events, so it stays in step with the curve.
- `store.ts`: the ghost learner (types code, runs the command) and reactions to real presses (Check fills a step in,
  Fix it rewrites the zeros and reruns).
- `walkthrough.ts` + `drive.ts`: the beats. They drive the real UI (launcher field, keys, the Fix it button). After the
  ghost types, a beat sends `check_step` straight to the mock, standing in for "the engine saw the code".
- `Presenter.tsx`: the Demo chip and the walkthrough panel. Hidden in Electron.

No core files changed. One fix outside the folder: `cards/index.tsx` no longer says "The video picks up from here"
on a Just teach me lesson (there's no video).

## Status
- ✅ Browser stage: all 16 beats run end to end (walkthrough, autoplay, restart, and by hand).
- ⏳ Electron: `DEMO=1 SCENARIO=demo` plays the scripted engine, but the fake desktop only shows in the browser stage
  (it keys off the URL). On the Mac, present from the browser stage in full screen.
- Not built (Michael's mockups that need new surfaces): the 560px concept sidebar, the experiment run table, the skill-map home.
  The skill map is shown as a diagram at the end instead.

## Core requests
None needed. Nice to have: an `npm run demo` script (`dev:web -- --open "/?scenario=demo&clean"`).

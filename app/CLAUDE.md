# app/: rules for every Claude session working here

You are one of several agents building the overlay in parallel, **one feature each, one branch each** (`adrian/<feature>`, its own git worktree). Your brief is `app/agents/<feature>.md`. Read it, then `app/README.md` (how the app works) and `shared/contracts/events.ts` (the engine contract).

## What you may edit
- `app/src/renderer/src/features/<feature>/**`: your renderer code (UI, store, hooks)
- `app/src/main/features/<feature>.ts`: your main-process code, if the brief needs a window, IPC or safeStorage
- `app/mock/scenarios/<feature>.json`: your mock scenario (auto-merged into `full`)
- `app/agents/<feature>.md`: your brief (update Status / Notes as you go)

## What you must NOT edit (core, owned by the integrator)
`core/`, `bridge.ts`, `main.tsx`, `dev/`, `src/main/index.ts|engine.ts|platform.ts|context.ts`, `src/preload/`, `src/common/`, `mock/engine.ts`, `mock/scenarios/{happy,offtrack}.json`, `package.json`, configs, and `shared/contracts/` (Michael's, changed only through a `contract:` PR).
Need a core change (a new field in `core/lesson.ts`, a new bus event, a new npm package, a contract field)? Write it under **Core requests** in your brief, keep going with a local workaround, and say so in your final report. Don't edit core yourself: parallel agents would collide.

## How features plug in (no shared lists to edit)
- `features/<feature>/index.tsx` default-exports `defineFeature({ id, islandModes?, overlayLayers?, windows? })`. It's discovered automatically (`core/registry.ts`).
  - **islandModes**: states of the Dynamic-Island pill. `priority` decides who wins (0–9 pill-sized · 20 hover · 40–79 cards · 80+ diagram). `width` set = a card that grows out of the pill; omitted = pill-sized.
  - **overlayLayers**: full-screen layers in the click-through overlay (`z`; the island is z 50).
  - **windows**: a route for your own Electron window (`index.html#/<route>`); `stage` places it in the browser stage.
- State: your own zustand store in `features/<feature>/store.ts`. Subscribe to engine messages with `onMessage('<type>', fn)` and UI events with `onUi('dismiss' | 'reset' | 'shortcut', fn)` from `core/bus.ts`, at module top level.
- Read shared lesson state from `core/lesson.ts` (`useLesson`, `useProgress`, `useStatus`). Other features' stores are read-only imports.
- Send to the engine: `bridge.send(cmd('<type>', payload))` (`common/wire.ts`). Shortcuts go through `triggerShortcut(kind)` (`core/shortcuts.ts`); return `true` from an `onUi('shortcut')` handler to claim one.
- Main process: `src/main/features/<feature>.ts` default-exports `defineMainFeature({ id, setup(ctx) })`; see `src/main/context.ts` (createWindow, handle ↔ `bridge.invoke`, broadcast ↔ `bridge.onFeature`, `engine.onOpen`). In the browser stage, stand in for main handlers with `registerWebHandler(channel, fn)` from `bridge.ts`.
- Interactive overlay elements need `data-hit` (stops click-through); visible-but-passive ones need `data-ui`. Both are reported to the engine as `overlay.bounds` so its screen reader ignores them.
- **Brand: read `app/brand/BRAND.md` before touching anything visible** (Miyagi brand kit, its rules are not optional):
  - Green (`color.green`) ONLY means passed. Amber (`color.amber`) ONLY means off track. Gray = watching. No red.
  - **Pastels for options only**, by the mapping in BRAND.md (`theme.actionTone`): sky = Explain / Diagram / Watch, lilac = Show me, pink = Hint; source kinds via `theme.kindTone`. Use `OptionButton` for options and `PrimaryButton` for the ONE primary action per surface (`core/ui/atoms.tsx`); chrome and navigation stay neutral. Never pastel for status, never for chrome. Status dots have no glow.
  - **No blue anywhere else.** `color.accent` is now white: buttons are white on dark (`color.accent` fill + `color.onAccent` text), never blue, green or amber.
  - No gradients, glows, purple, neon, sparkles, emoji or hand-drawn annotations. Every sparkle icon becomes the bonsai: `<MiyagiMark size={14} />` from `core/ui/Mark.tsx` (it picks the right cut for the size). In the app the tree is **monochrome** (white on dark) by default; don't pass `mono={false}`.
  - App text uses the system font (SF Pro / Segoe). No Inter. Copy is calm and short (≤12 words per card); the launcher placeholder is "Ask Miyagi anything"; the passed line is "Good. Now the next one."
- Colors, radii, the spring: `core/theme.ts` tokens only (brand palette in `brand`, HUD in `hud`). No new hard-coded colors.
- **Every surface is born from the notch island and returns to it** (Michael, Sat ~2 PM): the launcher, cards, diagrams, settings. Nothing pops up mid-screen. Surfaces that need typing (launcher, settings) live in their own focusable window but start from the island's exact shape (`launcher:open` carries `{from:{w,h}}`) and collapse back into it.
- **Nothing PINN-specific** (generality rule): PINN-on-convection is only the demo lesson. Labels come from the data (metric names, check labels, step titles); never hardcode 'loss', 'β' or 'PINN' in UI code.
- Animation: the one spring `{stiffness 420, damping 34, mass 0.9}`; animate transform/opacity; never resize windows during an animation.

## Run and check
```bash
npm run typecheck                                  # must pass before every commit
npm run dev:web -- --port <your port>              # ports: agents/ports.json → http://localhost:<port>/?scenario=<feature>
```
**Restart the dev server after adding a new feature folder or a new `mock/scenarios/*.json` file** (Vite caches the folder scans; otherwise your new scenario or feature silently doesn't load). The browser stage runs the mock inline (no server needed): `?scenario=<name>` picks `mock/scenarios/<name>.json` (`full` = everything merged). Ctrl+K opens the launcher; Alt+E/D/S/H/V and Alt+← are the shortcuts; Esc dismisses. Electron (`npm run dev`) can't run on Adrian's Windows laptop (Smart App Control); Michael checks Electron on the Mac.

## Git and review
Commit small and often on `adrian/<feature>`. **Don't push or open a PR until Adrian has reviewed your pass**; the integrator pushes after review (PRs then target `main`, or `adrian/shell` until that's merged). Never commit `.env`, keys, `node_modules`, `out/`, `dist/`.

## When you finish a pass, report
1. What works, and what's left (update **Status** in your brief).
2. How to see it: the stage URL with your port and scenario, and which keys/clicks to press.
3. Screenshots in `app/agents/shots/<feature>-*.png` (they help Adrian review fast).
4. Your **Core requests**, if any.

If the Browser pane is hidden, animations freeze (0 frames). Check state through the DOM, and say what you couldn't see.

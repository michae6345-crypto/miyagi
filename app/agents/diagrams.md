# diagrams

**Status:** v1 (network + gradients) · pass 2 · **Priority:** P1 · **Port:** 5180 · **Branch:** `adrian/diagrams`

## Goal
Intuition diagrams that morph out of the pill (⌥D). The generic **graph** is the one that matters most: it's the only diagram any non-PINN lesson gets (React, git, pandas, diffusion). Michael P1-4.

## Owns
- `app/src/renderer/src/features/diagrams/`
- `app/mock/scenarios/diagrams.json` (graph examples + heatmap data)

## Contract
- **In:** `diagram {kind: network | gradients | heatmap | graph, data, caption, stepId?}`. Exact shapes in `shared/contracts/events.ts` (`GraphDiagramData`).
- **graph:** `{title, layout: flow|sequence|tree|data|architecture|git, direction: LR|TB, grid:{cols,rows}, nodes:[{id,label,detail?,group?,shape: box|round|circle|data|commit, emphasis?, col,row}], edges:[{from,to,label?,style: solid|dashed, emphasis?, order?}], groups?:[{id,label}]}`. Map `(col,row)` to pixels on the grid; `order` is for the sequence layout only; groups optional. Reference renderer: `server/diagrams/render_svg.py`; examples: `server/diagrams/examples/*.svg`; spec: `server/diagrams/README.md` (read all three; they're on `origin/integration/live` if not in your checkout: `git show origin/integration/live:server/diagrams/README.md`).
- **heatmap:** `{x:number[], t:number[], predicted:number[][], exact?:number[][]}` on a canvas, or hide it. Never show "heatmap (coming)".
- **Out:** `action {kind:"diagram"}` via the shortcut (core).

## Adrian's spec (pass 2)
- Black island, white strokes (`color.text` / `color.label` / `fill.rule`). **Emphasis = white at full strength, others at label alpha.** Amber only for what's off track, green only for passed, nothing else colored. Pastels only if a node is an option (it never is today).
- **Generality rule:** remove every PINN literal ('5k epochs', '|∇|', '→ 0 · residual', default labels). Labels come from `data`.
- Gradient chart: layers 0–1 not amber (neutral or sky); the residual pill is an outline, neutral.
- One caption line, clamped. No axis clutter. Lines draw in (350 ms, 30 ms stagger), the one spring.
- Tabs only when the engine has sent more than one kind for this step.
- SVG neutrals → tokens.

## Done when
- graph renders every example layout in `server/diagrams/examples/` legibly at 640 wide
- heatmap renders or is hidden; no PINN strings left in the UI code

## Test
`npm run dev:web -- --port 5180` → `http://localhost:5180/?scenario=diagrams`, Alt+D. Restart the dev server after adding the scenario file.

## Core requests
_None yet._

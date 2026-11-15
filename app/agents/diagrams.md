# diagrams

**Status:** pass 2 done and merged with UI polish (efed46a): graph (all 6 layouts) · heatmap canvas · tabs, under their sky KindTile header with the 2-line caption clamp · **Priority:** P1 · **Port:** 5180 · **Branch:** `adrian/diagrams`

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

## Pass 2 notes (diagrams agent)
- **Files:** `Graph.tsx` (kind graph), `Heatmap.tsx` (kind heatmap), `Tabs.tsx` (tabs + `titleOf`), `store.ts` (per-step `byKind` / `kinds`, `showKind`). `Diagram.tsx` only got wiring lines (imports, `titleOf`, `<DiagramTabs fallback>`, the two kind branches).
- **graph, layered (flow · data · architecture · tree):** LR columns are sized to their labels (canvas-measured), S-curves between columns, edge labels on the curve with a black backing; a one-row chain (pandas) puts edge labels above the arrows and lets details wrap to 2 lines. TB (trees): curves down, back edges (child → parent callbacks) arc on the right. Groups named in `groups` draw as a faint cluster with their label. Text shrinks to 10 px, then truncates; the full label and detail are in the hover title.
- **graph, sequence:** participants on top, dashed lifelines, one arrow per message by `order`, self-calls as a small loop.
- **graph, git:** rendered as a vertical log (like `git log --graph`), not horizontal lanes: lanes are columns on the left, hash + message + branch tag (at each lane's newest commit) on the right. Reason: horizontal lanes put commit labels in the band every cross-lane curve must cross (labels got cut in the rebase example), and 12 commits don't fit 600 px across. Lines fork into the child's lane right after the parent (or merge right before the child); dashed copy edges leave between lanes and point at the copy from the side. Emphasized commits are filled white.
- **heatmap:** canvas, t left → right, x bottom → top (engine order `grid[t][x]`, a transposed `[x][t]` grid is accepted). Predicted and exact side by side on one shared scale, from `fill.thumb` to `color.text` (no hues); 8-step scale with min/max; hover shows `t · x · values`. Malformed or empty data renders nothing (no placeholder).
- **Tabs:** only when the engine sent more than one kind for the same step (payload `stepId`, else the lesson's current step). They take the title's place next to the sky KindTile (13 px, selected semibold). Neutral chrome, the selected tab slides on the one spring.
- **Motion:** edges draw in 350 ms, 30 ms stagger by rank / message order; dashed edges draw through a mask (pathLength can't animate a dashed stroke); heatmap panels sweep in along t.
- **Color (Adrian, Sat: "a little more colorful with the pastels, a tad"):** emphasized nodes and edges in deep sky (`brand.pastel.skyDeep`, a soft sky wash inside emphasized boxes); named groups take the pastel trio (sky, lilac, pink) as a 10% wash with a tinted label; git lanes take the same trio (lines, commits, branch tags); the heatmap ramp runs from `fill.thumb` to sky. Everything else stays white / label alpha; green and amber stay status-only. Note for the integrator: BRAND.md still says pastels are for options only; this is Adrian's exception for diagrams.
- **Caption:** `Diagram.tsx` (polish) clamps it to 2 lines in `color.label`, which fits the engine's ~200-character graph captions.
- **Mock:** `?scenario=diagrams`: Alt+D shows flow (React effect), then Alt+D/Esc closes; the next Alt+D shows sequence (login), tree (components), data (pandas), architecture (cache, with groups), git (rebase), then network + heatmap with tabs, and loops. Flow, data and git are the engine's live examples verbatim (`server/diagrams/examples/`); sequence, tree and architecture are hand-made to `layout.py`'s rules.
- **Shots:** `agents/shots/diagrams-{flow,sequence,tree,data,architecture,git,git-12,heatmap,heatmap-hover,heatmap-single,tabs-network}.png`.

## Core requests
_None._ (The contract already has `GraphDiagramData`, and `events.py` has `GraphDiagram` on `main` and `integration/live`, so graph payloads reach the app.)

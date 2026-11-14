# diagrams

**Status:** v1 (no heatmap) · **Priority:** P1 · **Port:** 5180 · **Branch:** `adrian/diagrams`

## Goal
Intuition diagrams that morph out of the pill (⌥D), mockup 05: **Architecture** (the real model's layers, autograd arrows to u_t and u_x → residual), **Gradient flow** (gradient norm per layer over training: shows why the PINN stalls), **Solution** heatmap (predicted vs exact u(x,t)), and the new generic **Graph** (concepts and how they connect, for any tutorial). Tabs switch between them; lines draw in (350ms, 30ms stagger). Brand: black island, white strokes, amber only for what's off track, green only for passed; pastels only if a node is an *option*.

## Owns
- `app/src/renderer/src/features/diagrams/`
- `app/mock/scenarios/diagrams.json` (heatmap data)

## Contract
- **In** (engine → app): `diagram {kind: network | gradients | heatmap | graph, data, caption, stepId?}`. **`graph` is new (contract PR #14)**: a generic concept graph for ANY tutorial (generality rule): read its exact `data` shape in `shared/contracts/events.ts`
- **Out** (app → engine): `action {kind:"diagram"}` (via the shortcut)

## Plugs in as
islandModes: diagram (80, width 640)

## Done when
- Network matches mockup 05
- Heatmap renders on a canvas from `{x, t, predicted, exact}`
- Tabs
- One caption line, no axis clutter

## Test
`npm run dev:web -- --port 5180` → `http://localhost:5180/?scenario=full` (or `?scenario=diagrams` once you add `mock/scenarios/diagrams.json`)

## Adrian's spec
**First pass (no spec from Adrian yet):** build to the mockups in `docs/mockups/` (01–05 are the target look; 06–07 are earlier explorations to restyle in the Apple look) and the animation + placement spec in `docs/FRONTEND-HANDOFF.md`. Don't spend time on colors (Adrian's theme comes later). Adrian reviews after this pass and writes his spec here for pass 2.

## Core requests
_None yet._

## Notes
-

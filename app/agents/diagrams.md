# diagrams

**Status:** v1 (no heatmap) · **Priority:** P1 · **Port:** 5180 · **Branch:** `adrian/diagrams`

## Goal
Intuition diagrams that morph out of the pill (⌥D), mockup 05: **Architecture** (the real model's layers, autograd arrows to u_t and u_x → residual), **Gradient flow** (gradient norm per layer over training: shows why the PINN stalls), **Solution** heatmap (predicted vs exact u(x,t)). Tabs switch between them; lines draw in (350ms, 30ms stagger).

## Owns
- `app/src/renderer/src/features/diagrams/`
- `app/mock/scenarios/diagrams.json` (heatmap data)

## Contract
- **In** (engine → app): `diagram {kind: network | gradients | heatmap, data, caption}`
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
_TBD: Adrian fills this in._

## Core requests
_None yet._

## Notes
-

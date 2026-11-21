# bundle (A12)

**Status:** in progress · **Branch:** `michael/app-bundle` (from `michael/app-core-v2`) · **PR:** draft into `adrian/shell`

## Goal
One download that works offline on first launch: the Mac app carries a standalone Python 3.12 with the engine's
packages already installed, plus the VS Code companion `.vsix`. First launch copies the engine source to
`~/miyagi/engine/src` and starts it with the bundled Python in seconds; no uv, no Python download, no Terminal.
DISTRIBUTION-PLAN.md section 2 ("The bundle").

## Owns
- `app/scripts/bundle-engine.mjs`
- `app/electron-builder.yml` (`mac.extraResources`)
- `app/src/main/localEngine.ts`
- `app/agents/bundle.md`

## Mockups
None of its own (no UI). It feeds the rows other lanes draw: Onb-Setup-Full, Onb-Checklist-Mixed and
Onb-Setup-Ready ("miyagi engine" and "VS Code companion" rows, A3) and Err-VSCodeSetup (helper sheet, A2).

## Core requests
_None yet._

## Notes

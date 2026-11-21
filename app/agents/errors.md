# errors (A7)

**Status:** in progress (lane claimed) · **Priority:** P1 · **Port:** 5192 · **Branch:** `michael/app-errors` (from `michael/app-core-v2`)

## Goal
Every way a lesson can stall, said calmly from the island: the engine reconnecting and then offline, the network gone,
the AI busy, a build that failed, VS Code closed, no kernel, and the crash consent card at launch.

## Owns
- `app/src/renderer/src/features/errors/**`
- `app/src/main/features/errors.ts`
- `app/mock/scenarios/errors.json`
- `app/agents/errors.md`

## Mockups
Err-EngineReconnect, Err-OfflineAndLimits (pill lines), Err-LessonBuildFailed, Err-VSCodeClosed, Err-KernelInContext (pill line), Err-CrashConsent.

## Core requests
_None yet._

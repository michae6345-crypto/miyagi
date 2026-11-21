# library

**Status:** in progress (lane claimed) · **Priority:** P1 · **Port:** 5191 · **Branch:** `michael/app-library` (plan A6)

## Goal
The Library app window (Home-Library) and a lesson's preview inside it (Home-LessonDetail): the lessons cached on this Mac, a Continue row for the ones left mid-way, a filter by tool, search, and Start lesson, which starts a cached lesson with zero model calls.

## Owns
- `app/src/renderer/src/features/library/**`
- `app/src/main/features/library.ts`
- `app/agents/library.md`

## Contract
- **In** (engine → app): `library {items}`, `library.item {item, steps?, overview?}`, `lesson.ready`, `error`
- **Out** (app → engine): `library.list`, `library.get {id}`, `library.start {id}` (only when `engine.hello.capabilities` lists them). Without the capability: HTTP GET `/library`, `/library/{id}` on the engine, `[]` on failure.

## Plugs in as
`windows: [{ route: 'library', kind: 'app' }]`; opened with `openLibrary(id?)` from `core/surfaces.ts`.

## Core requests
_None yet._

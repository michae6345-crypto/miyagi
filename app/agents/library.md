# library

**Status:** pass 1 done (plan A6): Library window + lesson preview, main data path, stage stand-in; typecheck green, brand lint clean, stage checked headless. Draft PR #168 into `adrian/shell`. Not verified in Electron. · **Priority:** P1 · **Port:** 5191 · **Branch:** `michael/app-library`

## Goal
The Library app window (Home-Library) and a lesson's preview inside it (Home-LessonDetail): the lessons cached on this Mac, a Continue row for the ones left mid-way, a filter by tool, search, and Start lesson, which starts a cached lesson with zero model calls.

## Owns
- `app/src/renderer/src/features/library/**` (index, LibraryWindow, Library, Detail, parts, store, sanitize, web)
- `app/src/main/features/library.ts`
- `app/agents/library.md`, `app/agents/shots/library-*.png`

## Contract
- **In** (engine → app): `library {items}`, `library.item {item, steps?, overview?}`, `lesson.ready`, `error`
- **Out** (app → engine): `library.list`, `library.get {id}`, `library.start {id}`, only when `engine.hello.capabilities` lists them. Never `learn`.
- Without the capability: HTTP GET `/library` and `/library/{id}` on the engine's http origin (ENGINE_URL with ws→http; loopback or https only; `X-Miyagi-Token` header; 3 s timeout; 1 MB cap; no redirects). Any failure = `[]` (list) or `null` (preview). Both `{items: [...]}` and a bare array are read.

## Plugs in as
`windows: [{ route: 'library', kind: 'app', size: windowSize.library }]`; opened with `openLibrary(id?)` from `core/surfaces.ts` (main/appWindows.ts allowlists the route). Main IPC (`ctx.handle`, sender-checked):

| Channel | Returns |
|---|---|
| `library:caps` | `{list, get, start}` from `EngineLink.can()` |
| `library:list` | cleaned `LibraryItem[]`, `[]` on failure |
| `library:get` (id) | `{item, steps, overview?}` or `null` |
| `library:start` (id) | `true` when `library.start` went out |

Why main owns the data: the engine's replay log drops `engine.hello` at `lesson.ready`, so a Library window opened mid-lesson would never see the capabilities in its own renderer; main keeps them for the whole connection.

## What it does
- **List** (1280x820): sidebar (bonsai + wordmark, Library / Continue, Tools filter rows, Excel "Soon"), header (search, New lesson = the one primary, launcher keycap from `platform.keys`), Continue cards (white meter on the track, round Resume = `library.start`), Ready to run grid with All / VS Code / Jupyter / Terminal chips and a disabled "Excel, soon", a dashed "Have a tutorial in mind?" card (Paste a link opens the launcher). Skeletons until the first answer; "No lessons on this Mac yet." when empty; "No lessons match." + Show all when a filter hides everything.
- **Preview**: back bar (Esc too), kicker from `source.kind`, title, overview, numbered steps, video box when the source is a YouTube https link (i.ytimg.com thumbnail, opens via `open:external`), Time / Steps / Made by, Works in, "Ready instantly. Saved on this Mac.", Start lesson (Enter too). Start waits for `lesson.ready` (15 s), then closes the window so the lesson panel has the screen; an `error` or the timeout shows fixed copy under the button, never the engine's text.
- **Safety**: every answer goes through `sanitize.ts` twice (main and renderer): ids `^[A-Za-z0-9_-]{1,64}$`, known fields only (no `workdir`, nothing else), strings that look like a home path dropped, lists and strings capped, `source.url` kept only for a YouTube https link.

## Deviations from the mockups (and why)
- No Free plan box (plan: hidden). No "Your lessons" nav: a `LibraryItem` doesn't say who built it.
- "Built once, shared with everyone" / "Built once, shared." → "Saved on this Mac" / "Ready instantly. Saved on this Mac." (plan: no cross-user sharing claim; the library is this Mac's cache).
- "⌘K" on New lesson is the platform's launcher key (`keyName="launcher"`); no ↵ keycap on Start lesson (no Enter in `platform.keys`; Enter still works).
- No Level row and no per-step check name (not in the contract); a step shows its minutes when the engine sends `estMinutes`. A Steps row was added to the facts list.
- Sidebar and preview aside use `scrim.launcher` (black .22) for the mockups' black .24 (no `surface.sidebar` token yet, see Core requests). Selected chip: `fill.trackSoft` + `fill.trackNextMini` border (the mockup's white .14 / .24).
- "Sits beside VS Code. Never covers your files." only when the lesson works in VS Code or Jupyter; otherwise "Sits beside your work."
- Detail lives inside the Library window (1280x820), not its own 960x700 window.

## Test
`npm run dev:web -- --port 5191`, then:
- `http://localhost:5191/?scenario=home&window=library&size=1440x900&clean` (list; `home` falls back to `full`, whose core-v2 triggers answer library.*)
- `&id=mnist_intro` (preview), `&library=empty` (empty state), `&library=nocaps` (Start disabled, "This engine can't start saved lessons yet."), `&scenario=happy` (no library trigger: the stage's own fixture items)
- Checked headless (Chromium, CDP): cards render; search "pandas" leaves one card; Terminal chip filters; card click opens the preview; Esc goes back; Start lesson shows the spinner, the mock answers `lesson.ready`, the window closes. Sanitizer run on hostile input (path ids, home paths, bad progress, duplicate ids, non-YouTube URLs): all dropped.
- Shots: `shots/library-list.png`, `library-detail.png`, `library-empty.png`, `library-detail-nocaps.png`, `library-fixture.png`.
- Not verified: Electron (`npm run dev`), the HTTP fallback against a real engine (E1/E2 not merged; cost freeze), real window chrome placement of the hiddenInset traffic lights.

## Core requests
1. **mock/engine.ts** (integrator): the default `engine.hello` in `start()` is lost in the browser stage for scenarios without their own hello (`?scenario=happy`, `home`, `full`: `useLesson.hello` stays undefined, so `canSend()` is false everywhere). It is emitted synchronously during `startInline`, apparently before the renderer is listening; core-v2 only works because it scripts its own hello 100 ms later. Fix: emit it on a 0 ms timer, or have the web bridge replay it on `ready()`. Workaround here: `web.ts` treats the inline mock as capable, like main's DEMO link.
2. **home.json** (A5) or the integrator: add `library.list`, `library.get`, `library.start` triggers to `mock/scenarios/home.json` so the plan's scenario URL (`?scenario=home&window=library`) answers from its own file once `home.json` exists (today `home` falls back to `full`, which gets them from core-v2).
3. **core/theme.ts** (integrator): a `surface.sidebar` token (black .24, Home-Library sidebar and Home-LessonDetail aside); this lane uses `scrim.launcher` until then.
4. **main/engine.ts** (integrator, optional): keep `engine.hello` in the replay log across `lesson.ready` / `lesson.ended`, so any app window opened mid-lesson knows the capabilities without asking main. This lane does not depend on it (main answers `library:caps`).
5. **E2** (engine): `GET /library` → `{items: LibraryItem[]}` and `GET /library/{id}` → `{item, steps?, overview?}` as JSON (`application/json`), the same shapes as the WS events; accept `X-Miyagi-Token`. The app reads a bare array too.
6. **Launcher** (A5): "New lesson" and "Paste a link" send `launcher:toggle`; if the launcher is already open it closes. A `launcher:open` signal any window may emit would be cleaner.

# library

**Status (Home dashboard, branch `michael/app-home`, Nov 20):** Home is now the full miyagi home dashboard (see "Home" below). Typecheck green, brand lint clean, checked in the stage headless at 1440x900 (shots `miyagi-v2/screens/round3/home-*.jpg`). Not verified in Electron. Fix round 2 (Nov 20): finished lessons never read as new (hero skips them, Ready to run lists them last as "Done · run again"); Finish setup is the white primary when setup is left; the empty hero has its own job; first run gets one welcome card; a failed Cloud row opens setup; the lesson/video radio is gone ("Pick a video instead" link); the field arrow is out of the tab order; building line "Finding the steps"; one start at a time across the library and dashboard stores. Shots `screens/round3/home-r2-*.jpg`.
Fix round 3 (Nov 20): setup left with a lesson to resume makes Finish setup the white primary, the hero line says what's missing ("Turn on Accessibility to start.") and Continue waits quiet and disabled with that reason as its title; the page is a container (hero over ask below 1000 px, the rail under the skills below 900, the band two by two below 900, Ready to run / Recent stacked below 760); Ready to run and Recent activity moved above the skills (first screen at 1280x820); the core buttons get a local white focus ring (`Ring`, motion.tsx) until Core request 0(a); Teach me / Build lesson stay readable while sending (busy, not disabled); "Pick a video instead" works once per text; offline says "miyagi is offline" once; the help meter hides while the cloud is "Not used". Shots `screens/round3/home-r3-*.jpg`.

**Earlier status:** pass 1 done (plan A6): Library window + lesson preview, main data path, stage stand-in; typecheck green, brand lint clean, stage checked headless. Draft PR #168 into `adrian/shell`. Fix round 1 done: a preview that got no answer is asked again on refresh, caps load on their own (no "can't start" until known), the video opens only the canonical watch link, the step count follows the step list, raw style literals moved to tokens, the HTTP body cap counts bytes as they arrive. Fix round 2 done: the window drags by the sidebar's traffic-light spacer, the list header and the preview back bar (`data-drag`; buttons, inputs and the search box stay clickable); a path anywhere in a string drops that string (`"/Users/…"`, `(/home/…)`, `file:///Users/…`, `'~/…'`, `=C:\…`); shots re-captured from this branch, plus a YouTube preview with its thumbnail. Not verified in Electron. · **Priority:** P1 · **Port:** 5191 · **Branch:** `michael/app-library`

## Home (the home dashboard, Nov 20)
The window's first view (the Dock click, the tray and `openLibrary()` land here). Files: `Home.tsx` (the page),
`homeModel.ts` (hero pick, recent activity, the ask field's send path), `Status.tsx` (sidebar status), `motion.tsx`
(rise / stagger / Press, the polish spec's numbers), plus `Library.tsx` (greeting header, sidebar status, Tools jump
to the Library list) and `features/dashboard/Dashboard.tsx` (exports `useDashView` and `Milestones`, no behavior change).

| Part | What | Rules |
|---|---|---|
| Hero | "Continue where you left off": newest saved lesson in progress (engine `progress.inProgress` with a `libraryId`, else a library row with `progress`), step line, tools, a ring with the share done | **The one white primary** on Home: Continue = `library.start {id}` (zero model calls; waits for lesson.ready, then the window steps aside). Other states: a lesson open now ("Back to the lesson" closes this window), building (spinner line, no button), nothing in progress but a lesson ready and not finished ("Start lesson"), nothing at all (welcome: "Learn by doing, checked step by step", bonsai; "Finish setup" is the white primary when setup is left, and the ask card's action goes quiet), loading skeleton, offline line. Setup left (connected) with a lesson to resume or start: Finish setup is the white primary, the line is the setup hint with the Not yet ring, Continue / Start lesson are quiet and disabled with the hint as their title. Disabled while any start is in flight (library store or the dashboard store's Up next / skills). |
| Ask | "ask miyagi anything" (`copy.launcherPlaceholder`), the launcher keycap from `platform.keys` | Sent exactly like the launcher: a goal = "Teach me" = `learn {query, mode:"lesson"}` (no lesson/video radio). Under it a quiet "Pick a video instead" link with the launcher keycap puts the goal on the clipboard and opens the launcher (`launcher:toggle` when closed; nothing is sent): "Paste it in the launcher to pick a video." Until Core request 0(b). Once per text: in Electron this window's `useSearch` never sees the launcher window open, so a second click would toggle it shut; the link stays spent (dimmed, disabled, titled) until the text changes. While sending, the action keeps its label with the spinner (busy, never disabled; `submitAsk` drops a second send). The field's arrow is a pointer shortcut only (`tabIndex -1`, `aria-hidden`), so the labeled button is the one tab stop. A YouTube link = `library.start` when that video is already a saved lesson (`libraryMatch`), else `learn_url {url}`. Then the window steps aside so the island has the build. Offline: nothing is sent, "miyagi is offline. Your text stays here." Its action is quiet while the hero has the primary, white when it doesn't. Idle shows three neutral idea chips (not pastel: they aren't help options). |
| Band | Today, This week, Reps, Rhythm | `features/dashboard` as is; below 900 px of page width Home wraps its four tiles two by two (one column below 480) from outside (Core request 7). |
| Ready to run | Up to 3 saved lessons not under way, unfinished first, then finished ones (engine `completed[].libraryId`) captioned "Done · run again"; "See all N" (N counts both) goes to the Library list | Click opens the preview. Skeletons, empty ("No lessons on this Mac yet. Ask miyagi above."). |
| First run | Connected, nothing saved, nothing completed, in progress or tracked | One calm card ("Your streak, skills and reviews show up after your first lesson.", bonsai, three beats: Ask, Do each step, miyagi checks it) replaces the band, constellation, rail, Ready to run, Recent and Milestones. |
| Recent activity | Last 5 lessons (finished and in progress), steps passed, skipped, when | Green check only for a finished lesson whose steps all passed; otherwise a white progress ring. Never invents a number. Sits beside Ready to run, above the skills, so "what can I run now" is on the first screen. |
| Skills + rail | The constellation, Review and Up next | Up next gets no primary (all quiet): the hero holds it. Below 900 px of page width the rail moves under the constellation (two columns, one below 600). |
| Offline | Engine away, nothing cached | One card: "Your streak, skills and reviews are safe." It adds "miyagi is offline…" only when the hero's caption doesn't already say it. |
| Milestones | Footer | `features/dashboard`. |
| Sidebar status | Setup (onboarding rows: "All set" / "N of M ready", click = guided setup), Engine (the engine row), Cloud (cloud:get + config.status.cloud; when it failed, click = guided setup), Plan and help meter (v2Cloud only, mock in the stage; click = account sheet; the meter counts cloud help, so it hides while Cloud reads "Not used") | Reads only, refreshed on open / focus / reconnect; never prompts. Shared status glyphs. |

Motion: every block rises 6 px and fades in, 35 ms apart (first 8), on the house spring; cards and rows take the
hover tint (opacity layer) and the 0.97 press dip; the ask field's area crossfades between idle, goal and link.
Reduced motion keeps the fades only (MotionConfig in main.tsx). Focus: focus-visible white ring, no transition (the
core buttons through the local `Ring` wrapper until Core request 0(a)).
Layout: `[data-home]` is a Tailwind container: hero and ask side by side from 1000 px of page width (the Library window
goes down to 560 px), the 300 px rail beside the skills from 900, Ready to run and Recent side by side from 760.

Stage (port 5401): `?scenario=home-dashboard&window=library&size=1440x900&clean` (new scenario: engine hello, progress,
library, health, library.start answers, a video search and a build). Also `&perm=accessibility-off` (setup left),
`?scenario=settings&window=library&library=empty` (empty: no progress, no lessons), `?window=library&engine=ws://127.0.0.1:9&fallback=0`
(offline), `?scenario=dashboard&window=progress` (the Progress window, unchanged).
Checked headless: goal + Enter sends learn {mode:lesson}, the build card grows from the island and the window closes;
Continue sends library.start:hd_mnist, lesson.ready, the window closes; a pasted link to a saved video offers Start
lesson, another link Build lesson; reduced motion leaves every block at opacity 1 with no transform.
Not verified: Electron, the launcher window over the Library window (in the stage it opens behind the app window).

## Goal
The Library app window (Home-Library) and a lesson's preview inside it (Home-LessonDetail): the lessons cached on this Mac, a Continue row for the ones left mid-way, a filter by tool, search, and Start lesson, which starts a cached lesson with zero model calls.

## Owns
- `app/src/renderer/src/features/library/**` (index, LibraryWindow, Library, Detail, parts, store, sanitize, web)
- `app/src/main/features/library.ts`
- `app/agents/library.md`, `app/agents/shots/library-*.png`

## Contract
- **In** (engine → app): `library {items}`, `library.item {item, steps?, overview?}`, `lesson.ready`, `error`
- **Out** (app → engine): `library.list`, `library.get {id}`, `library.start {id}`, only when `engine.hello.capabilities` lists them. Never `learn`.
- Without the capability: HTTP GET `/library` and `/library/{id}` on the engine's http origin (ENGINE_URL with ws→http; loopback or https only; `X-Miyagi-Token` header; 3 s timeout; 1 MB cap checked on content-length and counted in bytes while reading; no redirects). Any failure = `[]` (list). For a preview, an engine that answered without one = `null`; no answer at all (not connected, WS timeout, HTTP down) = the invoke rejects, nothing is cached, and the window asks again on its next refresh (connect, hello, focus). Both `{items: [...]}` and a bare array are read.

## Plugs in as
`windows: [{ route: 'library', kind: 'app', size: windowSize.library }]`; opened with `openLibrary(id?)` from `core/surfaces.ts` (main/appWindows.ts allowlists the route). Main IPC (`ctx.handle`, sender-checked):

| Channel | Returns |
|---|---|
| `library:caps` | `{list, get, start}` from `EngineLink.can()` |
| `library:list` | cleaned `LibraryItem[]`, `[]` on failure |
| `library:get` (id) | `{item, steps, overview?}`, `null` (answered, none), rejects (no answer) |
| `library:start` (id) | `true` when `library.start` went out |

Why main owns the data: the engine's replay log drops `engine.hello` at `lesson.ready`, so a Library window opened mid-lesson would never see the capabilities in its own renderer; main keeps them for the whole connection.

## What it does
- **List** (1280x820): sidebar (bonsai + wordmark, Library / Continue, Tools filter rows, Excel "Soon"), header (search, New lesson = the one primary, launcher keycap from `platform.keys`), Continue cards (white meter on the track, round Resume = `library.start`), Ready to run grid with All / VS Code / Jupyter / Terminal chips and a disabled "Excel, soon", a dashed "Have a tutorial in mind?" card (Paste a link opens the launcher). Skeletons until the first answer; "No lessons on this Mac yet." when empty; "No lessons match." + Show all when a filter hides everything.
- **Preview**: back bar (Esc too), kicker from `source.kind`, title, overview, numbered steps, video box when the source is a YouTube https link (i.ytimg.com thumbnail, opens via `open:external`), Time / Steps / Made by, Works in, "Ready instantly. Saved on this Mac.", Start lesson (Enter too). Start waits for `lesson.ready` (15 s), then closes the window so the lesson panel has the screen; an `error` or the timeout shows fixed copy under the button, never the engine's text.
- **Safety**: every answer goes through `sanitize.ts` twice (main and renderer): ids `^[A-Za-z0-9_-]{1,64}$`, known fields only (no `workdir`, nothing else), a string with a home path anywhere in it dropped (`/Users/`, `/home/`, `/private/`, `/var/`, `/tmp/`, `/opt/`, `~/`, a drive letter `X:\`, whatever comes before it), lists and strings capped, `source.url` kept only for a YouTube video and rebuilt as `https://www.youtube.com/watch?v=<id>` from the checked id (a `youtube.com/redirect?v=…&q=…` link never leaves the app); the video button opens that canonical link only.

## Deviations from the mockups (and why)
- No Free plan box (plan: hidden). No "Your lessons" nav: a `LibraryItem` doesn't say who built it.
- "Built once, shared with everyone" / "Built once, shared." → "Saved on this Mac" / "Ready instantly. Saved on this Mac." (plan: no cross-user sharing claim; the library is this Mac's cache).
- "⌘K" on New lesson is the platform's launcher key (`keyName="launcher"`); no ↵ keycap on Start lesson (no Enter in `platform.keys`; Enter still works).
- No Level row and no per-step check name (not in the contract); a step shows its minutes when the engine sends `estMinutes`. A Steps row was added to the facts list.
- Sidebar and preview aside use `scrim.launcher` (black .22) for the mockups' black .24 (no `surface.sidebar` token yet, see Core requests). Selected chip: `fill.trackSoft` + `fill.trackNextMini` border (the mockup's white .14 / .24).
- "Sits beside VS Code. Never covers your files." only when the lesson works in VS Code or Jupyter; otherwise "Sits beside your work."
- Detail lives inside the Library window (1280x820), not its own 960x700 window.
- Token discipline: preview title `type2.xxl` (28) for the mockup's 26; 20 px tool tile `radius2.keycap` (6) and `type2.micro` (11) for 5 / 9; chips `radius2.group`; circles and the meter `radius2.round`.

## Test
`npm run dev:web -- --port 5191`, then:
- `http://localhost:5191/?scenario=home&window=library&size=1440x900&clean` (list; `home` falls back to `full`, whose core-v2 triggers answer library.*)
- `&id=mnist_intro` (preview), `&library=empty` (empty state), `&library=nocaps` (Start disabled, "This engine can't start saved lessons yet."), `&scenario=happy` (no library trigger: the stage's own fixture items)
- Checked headless (Chromium, CDP): cards render; search "pandas" leaves one card; Terminal chip filters; card click opens the preview; Esc goes back; Start lesson shows the spinner, the mock answers `lesson.ready`, the window closes. Sanitizer run on hostile input (path ids, home paths, bad progress, duplicate ids, non-YouTube URLs): all dropped.
- `&scenario=happy&id=stage_mnist`: a YouTube-sourced preview (the stage fixture carries a watch link, so the i.ytimg.com thumbnail shows; the thumbnail is the project's demo video, not a TensorFlow one). `&library=nocaps&id=stage_venv` for the nocaps preview (nocaps reads the stage fixture, which has no `mnist_intro`).
- Shots (fix round 2, headless Chromium 1440x900 from this branch): `shots/library-list.png`, `library-detail.png` (3 steps, Steps 3), `library-detail-nocaps.png`, `library-empty.png`, `library-fixture.png`, `library-detail-youtube.png` (video box with thumbnail).
- Not verified: Electron (`npm run dev`), the HTTP fallback against a real engine (E1/E2 not merged; cost freeze), real window chrome placement of the hiddenInset traffic lights.

## Core requests
0a. **Lesson preview steps (Nov 21, engine, optional)**: the lesson detail now lists each step from `library.item.steps[]` as numbered rows: `title`, plus `what` (<= 12 words, one quiet line under the title) and `estMinutes` when sent; folded after six rows with "Show all N steps". All three fields are already in the contract (`OutlineStep`); nothing new is required, but `library.get` / `GET /library/{id}` should fill `what` and `estMinutes` on every step so the rows carry a line. Absent fields render nothing (title only; no steps = the old one-line note).
0. **Home (Nov 20)**: (a) **blocking**: `QuietButton` / `PrimaryButton` (core/ui/buttons.tsx) have no focus ring of their own, so Chromium draws its default orange/amber outline on them (yellow is banned); give them the white focus-visible ring (2 px solid, offset 2, no transition) and the hover tint. Home wraps every one it renders in a local `Ring` (motion.tsx) until then; other surfaces still show the amber ring. Also move `features/library/motion.tsx` (rise, stagger, Press, Ring) into `core/ui/motion.ts` once the polish lane lands it; (b) a `launcher:open {text?, mode?}` signal so Home's "Pick a video instead" can hand the typed goal to the launcher instead of copying it to the clipboard and toggling the launcher open (the link works once per text until then: this window can't see the launcher window's state, so a second toggle would close it); (c) a `surface.well` token for the ask field (it uses `scrim.launcher` with an inset hairline now); (d) dev/Stage: the launcher layer sits under app windows in the stage, so the video rows Home opens are hidden there; (e) a generic `clipboard:write` handler in main: Home's "Pick a video instead" borrows `diagnostics:copy` (scrubbed, capped) because Chromium refuses `navigator.clipboard` in an unfocused document. Side effect until then: `diagnostics:copy` runs `scrub()` (errors.ts), so a goal with text that looks like a path (`~/data/sales.csv`, `C:\…`) can reach the clipboard rewritten.
1. **mock/engine.ts** (integrator): the default `engine.hello` in `start()` is lost in the browser stage for scenarios without their own hello (`?scenario=happy`, `home`, `full`: `useLesson.hello` stays undefined, so `canSend()` is false everywhere). It is emitted synchronously during `startInline`, apparently before the renderer is listening; core-v2 only works because it scripts its own hello 100 ms later. Fix: emit it on a 0 ms timer, or have the web bridge replay it on `ready()`. Workaround here: `web.ts` treats the inline mock as capable, like main's DEMO link.
2. **home.json** (A5) or the integrator: add `library.list`, `library.get`, `library.start` triggers to `mock/scenarios/home.json` so the plan's scenario URL (`?scenario=home&window=library`) answers from its own file once `home.json` exists (today `home` falls back to `full`, which gets them from core-v2).
3. **core/theme.ts** (integrator): a `surface.sidebar` token (black .24, Home-Library sidebar and Home-LessonDetail aside); this lane uses `scrim.launcher` until then.
4. **main/engine.ts** (integrator, optional): keep `engine.hello` in the replay log across `lesson.ready` / `lesson.ended`, so any app window opened mid-lesson knows the capabilities without asking main. This lane does not depend on it (main answers `library:caps`).
5. **E2** (engine): `GET /library` → `{items: LibraryItem[]}` and `GET /library/{id}` → `{item, steps?, overview?}` as JSON (`application/json`), the same shapes as the WS events; accept `X-Miyagi-Token`. The app reads a bare array too.
6. **Launcher** (A5): "New lesson" and "Paste a link" send `launcher:toggle`; if the launcher is already open it closes. A `launcher:open` signal any window may emit would be cleaner.
7. **Dashboard lane** (`features/dashboard/Band.tsx`): the band's grid is a fixed inline `1.15fr 1.3fr 0.8fr 1.1fr`, so in a narrow window This week's day cells spill into Reps. Home overrides it from outside below 900 px (`[&>[data-band]]:grid-cols-2!` on its wrapper); a responsive band (container query or a `columns` prop) would let Home drop that.

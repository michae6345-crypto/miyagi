# App vs engine contract audit

Does the Electron app handle everything the engine sends, and send what the engine expects?

- **Date:** 2026-11-14. **Read-only code audit**: nothing was run, Electron was not launched. Every status below comes from reading the code.
- **Contract:** `shared/contracts/events.ts` + `events.py` on `integration/live` @ `148433b`. Engine emit sites: `server/orchestrator/session.py` and `main.py` at the same commit.
- **App:** `origin/adrian/shell` @ `fea89e0`. `app/` is identical on `origin/main` @ `ce6eff1` and on `integration/live` (`git diff --stat` is empty), so this is the app that ships.
- All `file:line` references are under `app/` on that ref. Status words: **handled**, **partial** (the fields it drops are listed), **MISSING**.

## TL;DR

Three things break the demo (P0), all on the hero path or on any restart:

1. **Cards never draw their buttons or their diff.** "Apply this fix?" (`diff` + `confirm`) can't be confirmed, so "Do it for me" is a dead end. "Looks done?", "Open VS Code?", "Fix applied / Undo" and "Continue where you left off?" have no buttons either. The resume card is worse: the engine freezes the lesson until it is answered.
2. **`lesson.ended` is thrown away** by the wire parser (not in `KNOWN`). After "Start a new lesson" the pill, player, cards and launcher keep the old lesson, and a build cancelled by a new search leaves the pill on "Building…" forever.
3. **The "Open VS Code?" card is wiped within milliseconds** by `step.started` (the engine emits the card right before step 1 starts), so even with a button nobody could press it.

Then, invisible features (P1): voice audio can't play (relative URL), `error` and build-failure text are never shown, the `graph` diagram has no view, the offline state is only a word in the launcher footer, `guidingQuestion` / step `instructions` / `status thinking` are not shown.

## 1. Engine → app (every event and optional field)

| Event / field | Status | Where (app) | What happens / what is ignored |
|---|---|---|---|
| `search.result` `id kind title meta reason thumbnail` | handled | `features/launcher/store.ts:41-53`, `Rows.tsx:45-101`, `Launcher.tsx:375` | `reason` matching `/best/i` picks the "best" row. `score` unused. A re-sent row (same `id`) merges in place (`store.ts:44-49`). |
| `search.result` extras `warnings[]`, `verified` | handled / partial | `store.ts:11`, `Rows.tsx:59-101` | Warnings quoted on the row. `verified: 'indexed'` draws no mark (only `true`, `Rows.tsx:101`). |
| `search.result` extras `comments` (status string), `url source videoId durationS channel scoredBy watched prerequisites codeNotes` | ignored (all optional) | `store.ts:11` types only `warnings`/`verified` | Nothing needed for the demo. |
| `search.done` `total` | handled | `store.ts:55` | |
| `lesson.building` `message progress` | handled | `core/lesson.ts:89-92`, `features/pill/index.tsx:42-59` | Pill "building" mode with spinner and progress line. |
| `lesson.building` `failed: true` | partial | `core/lesson.ts:91` | Clears `building`, so the pill falls back to idle. The failure message is **not shown anywhere**, and `pill/store.ts:45` keeps it as `buildMessage` (shows as the first text of the next build). |
| `lesson.ready` `lesson{id,title,sources} steps[]` | handled | `core/lesson.ts:93`, `player/store.ts:385`, `cards/store.ts:91`, `spotlight/store.ts:33`, `pill/store.ts:40`, `main/index.ts:193`, `main/features/player.ts:100` | Player window is shown here. `sources[].videoId` (extra) unused. `lesson.builtBy` is not on the wire (see §5). |
| `step.started` `stepId index title video` | handled | `core/lesson.ts:94-109`, `player/store.ts:393` | |
| `step.started` `instructions` | **partial** | `core/lesson.ts:103` | Stored, **never displayed** anywhere (overview card shows title + checks only). |
| `check.updated` | handled | `core/lesson.ts:110-116`, `core/ui/atoms.tsx:98-113` | `detail` shown. Dropped when `stepId` ≠ current step (`:112`). |
| `step.passed` `stepId nextStepId` | handled | `core/lesson.ts:117`, `pill/store.ts:48`, `cards/store.ts:96`, `spotlight/store.ts:35`, `player/store.ts:408` | |
| `offtrack` `stepId title body actions diff(expected,yours,line,file) citation` | handled | `core/lesson.ts:127`, `features/cards/index.tsx:150-201` | Buttons for `explain show_me hint apply_fix` are drawn (`:166-187`). |
| `offtrack` `severity level targets guidingQuestion`, `citation.url`, `diff.command` | **ignored** | — | `level` is harmless (the engine only adds `apply_fix` at level 3, and the app draws whatever `actions` says). `guidingQuestion` is a visible feature that is missing. `citation` shows its label only, no link (`:189-196`). |
| `spotlight` `rect caption app? matched?` / `{clear:true}` | handled | `features/spotlight/store.ts:40-48` | |
| `screen.seen` | handled (not shown) | `core/lesson.ts:144` | Stored for a debug HUD that doesn't exist. Fine. |
| `video.seek` / `video.pause` / `video.play` | handled | `core/lesson.ts:128-131`, `player/store.ts:423-444` | |
| `card` `kind title body videoJump` | handled | `cards/store.ts:94`, `cards/index.tsx:317-352` | Draws title, body, video jump. Kind `resume` falls back to the "Answer" header (`:321`). |
| `card` `actions diff targets guidingQuestion` (+ engine extra `requirements`) | **MISSING** | `cards/index.tsx:317-352` | **None of these are drawn.** No button, no diff, no targets, no guiding question. |
| `diagram` `kind: network` / `gradients` | handled | `features/diagrams/Diagram.tsx:29-30` | |
| `diagram` `kind: heatmap` | **MISSING** | `Diagram.tsx:31` | Placeholder text "heatmap (coming)". |
| `diagram` `kind: graph` | **MISSING** | `Diagram.tsx:18` | Opens with header "· Solution" and only the caption. |
| `speak` `audioUrl text` | **partial** | `voice/store.ts:16`, `voice/index.tsx:13-17` | Played with `new Audio(url)` only while voice is on. `audioUrl` is relative (`/tts/<hash>.mp3`), so it resolves against the Vite/file origin and fails (§3). |
| `metric` `runId step name value` | handled | `cards/store.ts:112-133` | |
| `status` `state` | **partial** | `core/lesson.ts:143` | Stored as `engineState`; **nothing reads it**. No "thinking" feedback, and `idle` does not clear the building UI. |
| `lesson.ended` `lessonId? reason` | **MISSING** | `common/wire.ts:25-46` (not in `KNOWN`), dropped at `wire.ts:60` | No handler anywhere. TypeScript can't catch it: the `satisfies` on `KNOWN` doesn't require every event. |
| `error` `message` | **partial** | `core/lesson.ts:146`, `launcher/store.ts:56-59` | Stored; no component reads `useLesson.error`. Shown only while a search is pending or the launcher is open. Does not drop the building UI. |
| `config.status` | handled (not shown) | `core/lesson.ts:145` | There is no Settings feature to show it. |

## 2. App → engine (every command and action kind)

| Command / action kind | Status | Where (app) | Notes |
|---|---|---|---|
| `learn {query}` | handled | `launcher/Launcher.tsx:249` | |
| `learn_url {url}` | handled | `Launcher.tsx:254` | |
| `build_lesson {resultIds}` | handled | `Launcher.tsx:258` | Picked id first, then the rest. |
| `action` `back explain diagram show_me hint voice_toggle` | handled | `core/shortcuts.ts:14-17`; 6 global shortcuts `main/index.ts:127-131`; shortcut-bar clicks and launcher chips use the same path | |
| `action` `ask {text}` | handled | `Launcher.tsx:266` | |
| `action` `apply_fix` (and `show_me explain hint`) from the off-track card | handled | `cards/store.ts:68-71` | |
| `action` `confirm` | **MISSING** | — | No button sends it. |
| `action` `undo` | **MISSING** | — | |
| `action` `open_editor` | **MISSING** | — | |
| `action` `resume` | **MISSING** | — | |
| `action` `end_lesson` and top-level `end_lesson {}` | **MISSING** | — | Never sent. The engine accepts both (`main.py` dispatch; `session.py:1180`). |
| `video.state {t, playing}` | handled | `player/store.ts:157-166` | On change and every second while playing. |
| `overlay.bounds {rects}` | handled | `core/Overlay.tsx:45-71`, `main/index.ts:134-143` | Sampled every 300 ms, sent on change, unioned with the player window's rect, re-sent on reconnect (`main/engine.ts:57,71`). The launcher panel is not included (P2). |
| `config.keys {...}` | **MISSING** | — | No settings feature exists on the branch (`app/agents/settings.md` is a spec only). `EngineLink.onOpen` (`main/engine.ts:49`) is ready for it. The engine falls back to its `.env`, so the demo Mac works. |

## 3. Risky behaviour: direct answers

| Question | Answer |
|---|---|
| Drops the building UI on `lesson.building.failed`? | **Yes.** `core/lesson.ts:91` sets `building:false`, so the pill goes back to "Ask Miyagi". But the message is not shown anywhere: the learner sees the spinner vanish with no explanation. |
| …on `error`? | **No.** `core/lesson.ts:146` only stores it and nothing reads it (the launcher shows it only while a search is pending or the panel is open). A failed build is therefore silent. |
| …on `status idle`? | **No.** `engineState` has no reader. Today this is covered only because the engine always sends `lesson.building{failed:true}` before `status idle` (`session.py:579-581`). |
| Resets on `lesson.ended`? | **No, it never reaches a handler.** `wire.ts:60` returns `null` for types missing from `KNOWN`. Every store already has `onUi('reset')`, but only the dev stage ever emits it (`dev/Stage.tsx:89`). Effects: after `end_lesson` the pill, player window (`main/features/player.ts` only ever shows it, `:100`), cards and launcher mode (`Launcher.tsx:142`, `ask` when a lesson exists) keep the old lesson. A build cancelled by a new search ("new lesson") never clears `building`, because `lesson.ended` is the only event the engine sends for it. |
| Mocks or fakes engine data when offline? | **Electron, default: no.** `EngineLink` retries with backoff (`main/engine.ts:64-86`) and shows nothing invented. **`DEMO=1`: yes**, by design: scripted events play in the main process and the real socket is never opened (`main/index.ts:28`, `main/engine.ts:30-38`). Make sure no launch script exports `DEMO`. **Browser stage `npm run dev:web`: yes**, it falls back to an inline mock 900 ms after no engine answers (`renderer/src/bridge.ts:53-69,83,89-91`); dev only. |
| Shows an offline state? | **Partially.** Only the launcher footer: "Offline" + a Wi-Fi-off icon (`Launcher.tsx:353,373,507`). The pill, cards and player don't change when the socket drops, so a mid-lesson drop looks like a live lesson. |
| Queues commands while offline? | **Yes, unbounded, and replays them.** `main/engine.ts:55-62` queues every command and `:72` flushes on reconnect, including `build_lesson`, `apply_fix`, `end_lesson`. Pressing Build while the engine is down shows the spinner forever, then fires a stale `build_lesson` whose `resultIds` the restarted engine doesn't know. |
| Clears stale state after a reconnect? | **No.** The engine sends a snapshot on every connect (`main.py` `ws_endpoint` → `session.snapshot`): either `lesson.ready` + `step.started` + `check.updated`* + `offtrack`? + `status`, or only `status idle` when it has no lesson, or the resume card. After an engine restart the app keeps showing the lesson the engine no longer has. |
| Sends `overlay.bounds`? | **Yes** (§2). |
| Plays `speak.audioUrl`? | **Tries, but it fails.** The engine sends a relative URL (`server/coach/voice.py:105`, `ROUTE = "/tts"` → `/tts/<20 hex>.mp3`); the engine comment at `main.py:171` says "the app prefixes ENGINE_HTTP", and the app doesn't (no `ENGINE_HTTP` anywhere in `app/`). `new Audio('/tts/…')` hits the wrong origin. Voice is off by default and both sides start at `voice=false`, so this only shows when someone turns voice on. |

## 4. To-do for Adrian

Order is by impact. Payloads are exactly what the engine sends today (integration/live `148433b`).

### P0: breaks the demo

**P0-1. Draw the card's `actions` and `diff`** (`features/cards/index.tsx:317-352`, `cards/store.ts:68-71`).
Each button sends `{"type":"action","payload":{"kind":"<action>"}}`. Cards the engine really sends:

```jsonc
// "Do it for me" preview (after the off-track card's Apply fix). `diff` is a unified diff string.
{"type":"card","payload":{"stepId":"s3","kind":"answer","title":"Apply this fix?","body":"<summary>","diff":"--- a/pinn.py\n+++ b/pinn.py\n@@ …","actions":["confirm"]}}
// after confirm; Undo restores the file and the engine answers with a card {title:"Undone"}
{"type":"card","payload":{"stepId":"s3","kind":"answer","title":"Fix applied","body":"Re-run to check it. Undo if you'd rather type it yourself.","actions":["undo"]}}
// checks pass but the engine never saw the learner act: without Confirm the step can't pass
{"type":"card","payload":{"stepId":"s3","kind":"hint","title":"Looks done?","body":"The checks pass. Confirm and I'll move on.","actions":["confirm"]}}
// lesson start, when the lesson needs an editor. No stepId. `requirements` is an extra (see §5)
{"type":"card","payload":{"kind":"hint","title":"Open VS Code?","body":"This lesson works in VS Code. Open the <folder> folder there?","actions":["open_editor"],"requirements":[{"name":"VS Code","installed":true}]}}
// the app came back after >= 10 s away (or the lesson is parked): the engine freezes the lesson and pauses the video until answered
{"type":"card","payload":{"kind":"resume","title":"Continue where you left off?","body":"<lesson title> · step 3: <step title>","actions":["resume","end_lesson"]}}
```

- Buttons: `confirm` → "Apply" on a diff card, "Yes, move on" otherwise; `undo` → "Undo"; `apply_fix` → "Do it for me"; `open_editor` → "Open VS Code"; `resume` → "Continue"; `end_lesson` → "Start a new lesson". The labels are yours to choose; the sent kinds are fixed.
- Render `diff` (monospace, +/- lines) when present. Add `resume` to the `KIND` map (`:311-315`) with its own header instead of "Answer".
- Clear `fixing` when the "Apply this fix?" card arrives: after Apply fix the engine answers with that card, but `cards/store.ts:94` leaves `fixing` true, so hovering the pill shows the "Waiting for the fix" view (priority 70) over the card (priority 50).
- The engine does not send a "dismiss": close the card locally after a button press; the engine's next event (`card`, `step.passed`, `lesson.ready`, `lesson.ended`) takes over.

**P0-2. Handle `lesson.ended`** (`common/wire.ts:25-46`, `core/lesson.ts`, every lesson-side store, `main/index.ts`, `main/features/player.ts`).
```json
{"type":"lesson.ended","payload":{"lessonId":"abc123","reason":"end_lesson"}}
```
`reason` is `"end_lesson"` (the resume card's "Start a new lesson": the saved progress is discarded), `"stopped"` (the top-level `end_lesson` command, i.e. the bar's / launcher's End: the saved progress is kept and offered back by the resume card when the app next connects), `"POST /end"` (a terminal) or `"new lesson"` (sent at the start of every `learn` / `learn_url` / `build_lesson` that finds a lesson running or building). `lessonId` is omitted when no lesson was loaded yet. Order on the wire: `spotlight {clear:true}` and `video.pause {}` (only if a lesson was loaded), then `lesson.ended`, then `status {state:"idle"}`.
- Add `'lesson.ended'` to `KNOWN` (`wire.ts:25`). Add a test so every key of `EngineEvents` is in `KNOWN` (the current `satisfies` doesn't check that).
- On it, blank every **lesson-side** store: core lesson (`building` too), cards, spotlight, diagrams, pill, player (pause + blank), voice `last`. The stores already have `onUi('reset')` handlers; reuse them.
- **Do not reset the search/launcher store on `reason:"new lesson"`.** That event arrives while the learner is typing the new query. `launcher/store.ts:39` and `Launcher.tsx:155-162` close the panel and wipe the results on `reset`, so a blanket `emitUi('reset')` would collapse the launcher mid-search.
- Main: clear `EngineLink.log` (`main/engine.ts:18`) so a reloaded window doesn't replay the dead lesson, and hide the player window (`main/features/player.ts:100` only ever shows it).

**P0-3. Don't wipe a card that carries `actions` on `step.started`** (`cards/store.ts:92`).
`load_graph` emits `lesson.ready`, then the "Open VS Code?" card, then `step.started` for step 1 within milliseconds (`session.py:596-599`). The card is cleared before it can be seen, so VS Code never opens. Keep the card when `actions` is non-empty and its `stepId` is absent or equals the step that just started. (Michael can also move the offer after `step.started`; do the app side anyway.)

### P1: feature invisible or failure silent

**P1-1. Voice URL** (`main/engine.ts` dispatch, or `voice/index.tsx:13`).
```json
{"type":"speak","payload":{"audioUrl":"/tts/3fa9c1d27be0415a9c02.mp3","text":"Nice, step passed."}}
```
Resolve against the engine's HTTP origin: `new URL(audioUrl, ENGINE_URL.replace(/^ws/, 'http')).href` → `http://localhost:8787/tts/<hash>.mp3`. Do it once in main so every window gets an absolute URL. No CSP blocks it (`renderer/index.html` has none).

**P1-2. Show errors.** Two payloads, both need a visible message (pill line or toast, ~5 s):
```json
{"type":"error","payload":{"message":"Could not open pinn.py: …"}}
{"type":"lesson.building","payload":{"message":"<human error>","progress":0.0,"failed":true}}
```
`error` also carries "No lesson is running yet.", "Coach unavailable: …", "Search failed: … Paste a YouTube link instead.". The `failed` build is always preceded by an `error` with the same text, then `status idle`. Today a failed build just makes the pill fall back to idle. Also stop `pill/store.ts:45` from keeping a failed message as `buildMessage`.

**P1-3. Offline and reconnect** (`main/engine.ts:55-86`, `pill/index.tsx`, `core/lesson.ts`).
- Show "Offline" on the idle pill and mid-lesson when `connected` is false (today only `Launcher.tsx:507`).
- While disconnected, don't queue `learn`, `learn_url`, `build_lesson` or `action`; fail them visibly. Only `overlay.bounds` and `config.keys` should be remembered (`lastBounds` already is).
- On every socket open, the engine sends a full snapshot. Clear lesson-side state on (re)connect, then let the snapshot refill it. After an engine restart the snapshot is just `{"type":"status","payload":{"state":"idle"}}`, which should leave an empty idle pill.
- On disconnect while `building`, drop the building UI (no `failed` event can arrive).

**P1-4. `graph` diagram view** (`Diagram.tsx:18,29-31`; spec `server/diagrams/README.md`, reference renderer `server/diagrams/render_svg.py`, examples `server/diagrams/examples/*.svg`).
```json
{"type":"diagram","payload":{"kind":"graph","caption":"…","stepId":"abc:s2",
 "data":{"title":"…","layout":"flow|sequence|tree|data|architecture|git","direction":"LR|TB",
         "grid":{"cols":4,"rows":2},
         "nodes":[{"id":"a","label":"…","detail":"…","group":"g1","shape":"box|round|circle|data|commit","emphasis":false,"col":0,"row":0}],
         "edges":[{"from":"a","to":"b","label":"…","style":"solid|dashed","emphasis":false,"order":1}],
         "groups":[{"id":"g1","label":"…"}]}}}
```
Map `(col,row)` to pixels; `order` is sequence-layout only; `groups` is optional. This is the only diagram any non-PINN lesson gets (React, git, pandas, diffusion). Also give `heatmap` a real view (`data: {x:number[], t:number[], predicted:number[][], exact?:number[][]}`), or hide the button for it.

**P1-5. `guidingQuestion`** on `offtrack` and `card`: a Socratic line, ≤ 24 words, shown under the body (contract: "show under the body"). Example: `"guidingQuestion":"What if β started small?"`.

**P1-6. Step `instructions`** (`core/lesson.ts:103`): stored and never shown. Show them in the hover overview card (`features/overview/index.tsx`). It is the only "what do I do now" text besides the title.

**P1-7. `status {state:"thinking"}`** drives nothing. The engine sends it for 2-5 s model calls (explain, diagram, coach). Show a small spinner on the pill, or the learner presses ⌥E / ⌥D and sees nothing.

### P2: polish

- **Settings / BYOK (P1 if bring-your-own-key is part of the pitch):** no settings window exists, so `config.keys` is never sent and `config.status` is shown nowhere. Spec: `app/agents/settings.md`. The engine falls back to `.env` meanwhile.
- `offtrack.level` (2 = concept, 3 = fix): optional "Hint 2 of 3" label. `severity` is ignored (fine: amber for both).
- `offtrack.targets` / `card.targets`: `[{boxId, label, text, rect:{x,y,w,h}}]` in screen points. The engine already sends a `spotlight` for `targets[0]`, so this is only for multi-box highlights.
- `citation.url`: make the label a link (`cards/index.tsx:189-196`; open with `shell.openExternal`).
- `search.result`: `verified:"indexed"` mark; (YouTube comment warnings were removed with the scraping service; no `comments` string is sent.)
- `screen.seen`: debug HUD (optional).
- Add the launcher panel to `overlay.bounds` (`reportBounds` it while open).
- `EngineLink.log` (`main/engine.ts:18`) grows without bound (every `metric` is kept for replay); cap it or skip `metric`.
- Voice toggle desync: app `useVoice.on` persists across an engine restart while the engine restarts with `voice=false`. Send `action voice_toggle` only when they differ, or let the engine report it.
- Dev guards: log or show a banner when the inline mock or `DEMO=1` is active, so a demo can't run on canned data by accident.

## 5. For Michael: contract and engine side (not app work)

- **`lesson.builtBy` never reaches the app.** It is set on the step graph (`server/lesson/builder.py:135`), but `_lesson_ready_payload` (`session.py:601-616`) forwards only `lesson.id/title/sources`. Add `builtBy` to `lesson.ready.lesson` in the contract and the payload if the app is to show it.
- **Engine sends fields `events.ts` doesn't declare** (the models allow extras, so nothing breaks): `card.requirements` (`session.py:310`), `search.result` extras (`url source videoId durationS channel verified warnings scoredBy watched prerequisites codeNotes comments`, `server/finder/core.py:48-52`), `lesson.ready.lesson.sources[].videoId`, `offtrack.diff.command`. The S7 resume branch adds `card.resume` (`{lessonId,title,stepIndex,stepCount,stepTitle?,lastActiveAt?}`), which `events.ts` doesn't have either; the integration/live resume card (`session.py:1443-1448`) has no `resume` field.
- **Order of the editor offer:** emit `_offer_editor` after `start_step(0)` (`session.py:598-599`) so it survives even without P0-3.
- **Voice URL:** either send absolute URLs or keep the contract "relative, app prefixes the engine origin" and tell Adrian (P1-1).
- **`lesson.ended` for a cancelled build** is the only signal (no `failed`), so P0-2 matters beyond `end_lesson`.

## 6. Method and limits

- Compared every event and optional field in `events.ts` (+ `events.py`) with `onMessage(...)` handlers, `bridge.send(cmd(...))` call sites, `wire.ts`, `main/*` and the feature stores, using `git show` / `git grep` against `origin/adrian/shell`. Nothing was checked out over another tree.
- Engine payload shapes were read from the emit sites in `session.py`, `main.py`, `coach/voice.py`, `finder/core.py`, not captured from a live run.
- Not verified: anything that needs a running Electron app (window stacking, whether the overlay really draws over the card, real audio playback). The `file:line` claims about drops are static: a field marked "ignored" has no reader in the code.

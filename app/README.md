# app/: the overlay (Adrian)

Electron + React + TypeScript + Tailwind + Motion. Screen-first: no VS Code extension; the engine watches the screen and sends rects. Speaks **only** `shared/contracts/events.ts` over one WebSocket (`ENGINE_URL`, default `ws://localhost:8787`). Every message is `{type, payload}`, both directions.

## Run it

```bash
npm install                     # npm 11: if asked, `npm install-scripts approve esbuild`
npm run web:all                 # mock engine + browser stage → http://localhost:5173  (Ctrl+K opens the launcher)
npm run dev:web                 # stage alone; with no engine on :8787 it runs the mock inline
npm run mock -- full            # mock engine only: happy | offtrack | full
npm run dev                     # Electron (ENGINE_URL=…, DEMO=1 replays the scripted run in-process, no network)
npm run typecheck && npm run build
npm run dist:mac                # unsigned .app in dist/ (CI does this on every push to main)
```

Stage URL options: `?scenario=happy|offtrack|full` · `?engine=inline` · `?os=win` (Windows key labels) · `?clean` (hide the dev HUD) · `#/launcher` (open on load).

> **Windows + Smart App Control:** SAC blocks the unsigned `electron.exe`, so on a SAC machine you design in the browser stage and the Electron shell gets checked on the Mac (CI build or `npm run dev`).

## Layout of the code

```
src/main/index.ts       windows, global shortcuts, click-through, launcher→pill handoff, IPC relay
src/main/platform.ts    EVERY Mac/Windows difference (hotkeys, pill y, window flags, glass, focus return)
src/main/engine.ts      the single engine socket (or DEMO=1 in-process mock), relayed to all windows
src/preload/            the window.tut bridge (typed in api.ts)
src/common/wire.ts      parse {type,payload}, cmd('learn', {...}) builder
src/renderer/src/
  store.ts              reduces engine messages into lesson state (zustand)
  bridge.ts             Electron IPC, or browser: local bus + WebSocket + inline-mock fallback
  overlay/Island.tsx    the Dynamic-Island pill: every state is one morphing black object
  overlay/ShortcutBar   Ask anything · Back · Explain · Diagram · Show me · Hint · Voice
  overlay/Spotlight     dim + animated cut-out at the engine's screen rect + caption
  overlay/Diagram       network · gradients (heatmap TODO)
  launcher/Launcher     Spotlight-style search, streaming results, Build lesson → shrinks into the pill
  dev/Stage             browser stage over a fake Mac desktop at the mockups' 1600×1000 coordinates
  theme.ts              tokens (spring, radii, colors): the theme gets swapped here later
mock/                   engine.ts (scenario player), replay.ts (ws server), scenarios/*.json (exact wire messages)
```

## Windows (Electron)

Two preloaded windows, both covering the whole display, both always-on-top (`screen-saver` level), transparent, never resized:

- **overlay**: pill, cards, diagram, shortcut bar, dim/spotlight. Click-through (`setIgnoreMouseEvents(true, {forward:true})`); the renderer flips it off only while the cursor is over an element marked `data-hit`. Every `data-hit` / `data-ui` element is reported to the engine as `overlay.bounds` (screen points, sampled every 300ms, sent on change and on reconnect) so its screen reader ignores our own UI.
- **launcher**: focusable; shown on the hotkey. Because it covers the same display, its panel can morph onto the pill's exact pixels before the windows swap.

That's a deliberate change from "one small BrowserWindow per surface": the spec's morphs (card grows out of the pill, launcher shrinks into the pill) can't cross window boundaries, and a pre-sized window with native vibrancy would show a glass rectangle. Native blur behind the launcher is behind `TUT_NATIVE_GLASS=1` until it's checked on the Mac.

## How each feature works, end to end

| Feature | Trigger | Wire | What the app does | Status |
|---|---|---|---|---|
| **Search** | ⌥Space (Win: Ctrl+Shift+Space), type, ↵ | → `learn {query}` · ← `search.result` ×N, `search.done` | Rows stream in (40ms stagger); ↑↓ moves the highlight; label = `reason` | ✅ |
| **Paste a link** | Paste a YouTube URL, ↵ | → `learn_url {url}` · ← `lesson.building`… `lesson.ready` | Same launcher, skips the results list | ✅ (sends; engine path) |
| **Build lesson** | ↵ / button | → `build_lesson {resultIds}` (picked one first) · ← `lesson.building {message,progress}` → `lesson.ready` → `step.started` | Launcher panel morphs into the pill; pill shows the `lesson.building` message with a spinner, then "Step N · title" | ✅ |
| **Pill status** | Always on during a lesson | `step.started`, `check.updated`, `step.passed`, `offtrack` | Ring = lesson progress (steps + checks within the step). Dot: gray watching · amber off-track · green passed. Green flash on pass | ✅ |
| **Step overview** | Hover the pill (150ms) | – | Morphs into a card: thumbnail, "Step 4 of 7", segments, live checks | ✅ |
| **Checks** | Engine evaluates (`tut run`, file watch, metrics → Tiger) | ← `check.updated {checkId,label,status,detail}` | Renders only. First pending check = spinner; pass draws the checkmark | ✅ render · engine evaluates |
| **Video gating** | Every step | ← `step.started.video {videoId,start,end}`, `video.seek/pause/play` · → `video.state {t,playing}` | **Player window (F4):** YouTube IFrame API. Plays the step's segment, pauses itself at `end` until `step.passed`, then resumes 400ms later; reports position back. Engine sends seek/pause/play only for Back, Show me, video jumps | ⏳ F4 (store already tracks it) |
| **Spotlight** (screen-first) | Engine's screen reader (Apple Vision OCR, any app) | ← `spotlight {rect:{x,y,w,h}, caption, app?, matched?}` (screen points) or `{clear:true}` · → `overlay.bounds {rects}` | Dims the screen, cuts a rounded glowing hole at the rect (springs when it moves), glass caption beside it (flips left at the edge). No VS Code extension | ✅ |
| **Off-track** | Engine (check fails / loss flat) | ← `offtrack {title,body,diff,citation,actions}` + `video.pause` · → `action {kind:show_me/explain/apply_fix/hint}` | Dot pulses amber twice; pill morphs into the amber card (diff "expected vs yours", checks, buttons). Apply fix collapses it; on `step.passed` a green "Back on track" card shows, then auto-hides | ✅ |
| **Explain / Hint / Ask** | ⌥E / ⌥H / "Ask anything" | → `action {kind, text?}` · ← `card {kind,title,body,videoJump?}` | Card morphs out of the pill; `videoJump` button seeks the player | ✅ cards · ⏳ "ask" mode in the launcher during a lesson |
| **Diagram** | ⌥D | → `action {kind:"diagram"}` · ← `diagram {kind,data,caption}` | Morphs out of the pill; lines draw in. network + gradients done | ✅ · heatmap ⏳ |
| **Voice** | ⌥V | → `action {kind:"voice_toggle"}` · ← `speak {audioUrl,text}` | Plays the audio while voice is on; equalizer on the Voice button | ✅ (untested with real ElevenLabs audio) |
| **Back / Show me** | ⌥← / ⌥S | → `action` · ← `video.seek` | Player follows | ⏳ F4 |
| **Live curve** | Training run | ← `metric {runId,step,name,value}` | Stored per metric (capped). The off-track card's yours-vs-tutorial curve should switch to this | ⏳ (mock uses an optional `offtrack.curve`) |
| **Settings (your own keys)** | ⌘, / gear in the expanded pill / first run | → `config.keys {anthropic,gemini,brightdata,elevenlabs,tigerUrl}` on every connect · ← `config.status` (ok / missing / invalid / env per key) | Apple-style sheet; keys encrypted with Electron `safeStorage` in userData, never logged; green dot + Test per key | ⏳ next (store already keeps `config.status`; mock answers it) |
| **Demo mode** | `DEMO=1` | – | Scripted run plays inside Electron, no network | ✅ |
| **Global shortcuts** | ⌥E/D/S/H/V, ⌥← | main → engine `action` + overlay button animates | Registered after `lesson.ready` (so they don't steal keys before a lesson) | ✅ written · not run on hardware yet |

## Open questions for the engine

1. `step.started.index`: 0- or 1-based? (The UI derives "Step N" from the order of `lesson.ready.steps`, so either works.)
2. **Apply fix**: who edits the file? Proposal: the engine writes it on disk (VS Code reloads), then re-runs the check.
3. **Video gating**: OK that the player enforces the pause at `video.end` itself and reports `video.state`, with the engine only sending seek/pause/play for exceptions?
4. **Tutorial reference curve** for the off-track card: an optional `offtrack.curve {label, yours[], tutorial[]}`, or `metric` with `runId:"tutorial"`?
5. **Ask during a lesson**: launcher sends `action {kind:"ask", text}` and the answer comes back as `card {kind:"answer"}`?

## Mac checklist (needs Michael's machine)

- Pill sits at `y = 6` hugging the notch; overlay covers the menu bar.
- After the launcher hides, focus returns to VS Code without the pill flickering (`returnFocus` in platform.ts).
- `TUT_NATIVE_GLASS=1` vibrancy behind the launcher: does it look right?
- ⌥Space, ⌥E/D/S/H/V and ⌥← don't collide with anything.
- Click-through: you can type in VS Code under the overlay; hovering the pill/bar makes them clickable.
- Spotlight rects from the engine's OCR line up with the cut-out (points vs pixels, multi-display origin).

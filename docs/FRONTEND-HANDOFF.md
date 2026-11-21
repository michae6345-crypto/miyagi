# Frontend handoff (Adrian): the overlay app

**You own:** `app/` (the Electron overlay). **Update Sat 1 PM: the VS Code extension is DROPPED.** The engine now watches the whole screen (Apple Vision text recognition) and sends `spotlight` as a screen rectangle; you just draw it. Works over any app.
**You don't own:** `server/`, `cli/` (engine: me) or `finder/`, `diagrams data`, `demo/` (third teammate).
**Mockups:** `visuals/apple/01–05` (the target look) and `visuals/mockups/` (earlier explorations, including the off-track and success states).
**Overall plan:** `PLAN.md`.

## What we're building (30 seconds)
A macOS overlay that turns any tutorial into an auto-graded lab. You press ⌥Space and type *"train a PINN on the convection equation"*. It finds the best tutorial and breaks it into steps. The video plays one step, then **pauses until your own code, terminal or training run passes that step's check**. It dims the screen onto where you should work, explains things, and draws intuition diagrams. The hero moment: the training loss goes flat → the step turns red → it explains the known PINN failure → the user fixes it → green → the video resumes by itself.

**The UI must feel like a first-party Apple feature:** Spotlight, Dynamic Island, Control Center. Simple, quiet, few words. The engine does the heavy lifting; the UI only shows state.

---

## Stack
- **Electron 33+**, **electron-vite**, **React + TypeScript**, **Tailwind**, **Framer Motion** for the spring animations.
- **Native macOS glass:** `vibrancy: 'hud'` (or `'popover'`) + `visualEffectState: 'active'` + `backgroundColor: '#00000000'`. Use this instead of CSS blur; it looks like the real thing.
- Fonts: `-apple-system, "SF Pro Text", system-ui`. Icons: lucide (thin stroke, 1.5px).
- Reference for overlay tricks: `~/cue/main.js` (lines ~330–380 for window flags, ~1734 for click-through, ~1809 for global shortcuts). **Read it, don't copy it:** it's GPL, and the hackathon bans code written before Saturday 10:30am.

## Mac + Windows: one codebase, demo on Mac
Electron runs on both. Adrian can build on Windows and Michael runs it on the Mac. **The demo happens on Mac, so the Mac look is the one that has to be perfect.** Put every OS difference in **one file, `app/src/main/platform.ts`**, so nothing else branches on the OS.

| Thing | macOS (demo) | Windows (dev) |
|---|---|---|
| Glass material | `vibrancy: 'hud'` / `'popover'` + `visualEffectState: 'active'` | `backgroundMaterial: 'acrylic'` (Win 11). On Win 10, fall back to a CSS translucent fill |
| Pill placement | Top-center around the notch: `y = 6`, inside the menu-bar height (`screen.getPrimaryDisplay().workArea.y`) | Top-center, `y = 8` from the top edge |
| Launcher hotkey | `Alt+Space` (shown as ⌥Space) | `Ctrl+Shift+Space`. **Alt+Space is the Windows system menu; don't bind it** |
| Other shortcuts | `Alt+E/D/S/H/V`, `Alt+Left` | Same with `Alt`. Test each one for conflicts with `globalShortcut.isRegistered` |
| Show on all desktops / over fullscreen | `setVisibleOnAllWorkspaces(true,{visibleOnFullScreen:true})` | Not needed (no-op) |
| Always-on-top level | `'screen-saver'` | `'screen-saver'` works; also `skipTaskbar: true` |
| Font | `-apple-system` (SF Pro) | `"Segoe UI Variable"`. **Or bundle Inter for both** so spacing matches exactly |
| Permissions | None for the app (the engine needs Screen Recording) | None |
| Click-through overlay | `setIgnoreMouseEvents(true,{forward:true})` | Same |

**Keeping the Mac look right while developing on Windows:**
1. **Design in the browser first.** The renderer is plain React, so `npm run dev:web` serves every screen at `localhost:5173/#/pill`, `#/launcher` and so on, with a fake Mac-desktop background screenshot behind it. Most of the visual work happens here and looks the same on both machines.
2. **CI builds a Mac app on every push to `main`** (a GitHub Actions `macos-latest` runner + `electron-builder --mac --dir`, uploaded as an artifact). Michael downloads and runs it at each sync and posts a screen recording back.
3. **Saturday night and Sunday morning, the final polish happens on the Mac** (pair on Michael's machine, or Adrian remotes in).

## Windows (each one is a separate BrowserWindow)
| Window | Where / size | Behavior | Mockup |
|---|---|---|---|
| **Pill** | Top-center, around the notch. ~300×34 collapsed → ~420×230 on hover | Always on top, frameless, glass. Shows step, progress ring, status dot (gray watching / amber off-track / green passed). Hover expands it Dynamic-Island style. | 01, 02 |
| **Launcher** | Centered, ~740×460 | ⌥Space toggles it; Esc or losing focus hides it. Input, streaming results, "Build lesson". Background dims/blurs behind it. | 03 |
| **Shortcut bar** | Bottom-center, ~740×80 | "Ask anything" field plus Back / Explain / Diagram / Show me / Hint / Voice, with their shortcuts. Only visible during a lesson. | 04 |
| **Card / diagram popup** | Under the pill | Coach cards (amber off-track, green success) and diagrams. Auto-hides; pinnable. | 05 |
| **Dim overlay** | Full screen | Transparent black at ~55% with a rounded **hole at the `spotlight.rect`** the engine sends (screen points). Click-through (`setIgnoreMouseEvents(true, {forward:true})`) so the user can still type. | 04 |
| **Lesson player** | Right half of the screen (or docked) | YouTube IFrame Player API, chapter list = our steps. **We need to control the video** (pause / seek / resume), so it lives in our window, not the user's browser. | 04 right side |

**Flags on every overlay window:** `frame:false, transparent:true, hasShadow:false, resizable:false, alwaysOnTop:true` → `setAlwaysOnTop(true,'screen-saver')`, `setVisibleOnAllWorkspaces(true,{visibleOnFullScreen:true})`. **Do NOT call `setContentProtection(true)`.** We want the overlay to show up in the demo recording.

## The spotlight (screen-first, no extension)
- The engine's screen reader finds the target text on screen (Apple Vision OCR gives each line's box) and sends `spotlight {rect, caption}` in **screen points**.
- You draw the full-screen dim with a rounded cut-out at that rect (one SVG mask path, animated with the spring) and place the caption beside it.
- **Report your own UI's position:** send `overlay.bounds {rects}` whenever the pill, cards or shortcut bar move, so the engine's OCR ignores our own UI.
- Multi-display: use `screen.getAllDisplays()`; rects are relative to the primary display's top-left. Retina is already handled (points, not pixels).

## The contract with the engine (WebSocket `ws://localhost:8787`)
**Server → app events:**
```
lesson.ready        {lesson:{id,title,sources[]}, steps:[{id,title,video:{start,end}}]}
step.started        {stepId, title, instructions, video:{start,end}}
check.updated       {stepId, checkId, label, status:"pending|pass|fail", detail?}
step.passed         {stepId}
offtrack            {stepId, severity:"warn|fail", title, body, diff?, actions:["explain","show_me","apply_fix"]}
spotlight           {rect:{x,y,w,h}, caption} | {clear:true}   → screen points; draw the cut-out
overlay.bounds      (app → engine) {rects[]}   → so OCR ignores our UI
video.seek          {t, play:boolean}
video.pause         {}
diagram             {kind:"network|gradients|heatmap", data:{...}, caption}
speak               {audioUrl}                             → play if voice is on
search.result       {id, kind:"video|notebook|paper|blog", title, meta, score, reason}
search.done         {}
```
**App → server commands:**
```
learn {query} | learn_url {youtubeUrl} | build_lesson {resultIds[]}
action {kind:"back|explain|diagram|show_me|hint|voice_toggle|ask", text?}
```
If a payload needs to change, tell me first. These will live in `shared/contracts/events.ts`.

## Build against a mock, not the real server
Your first Claude session writes `app/mock/replay.ts`, which plays `app/mock/scenario.json` (a scripted timeline of the events above) over the same WebSocket. Then you never wait on me. The scenarios to script:
1. `happy.json`: learn → results → lesson.ready → step 4 → spotlight → checks pass → step.passed → video resumes.
2. `offtrack.json`: step 8 → check fails (loss flat) → offtrack card → diagram (gradients) → apply fix → pass.

Switching between mock and real is one env var: `ENGINE_URL`.

## Placement (where everything sits)
Always compute from `screen.getDisplayNearestPoint(cursor).workArea`, never hard-coded pixels.
- **Pill:** horizontally centered. On Mac it sits inside the menu-bar band hugging the notch (`y = 6`, height 34). On Windows `y = 8`. When collapsed it never covers app content.
- **Expanded pill / cards / diagram popup:** grow **downward from the pill's center**, the same transform origin, so it reads as one object morphing. Top edge at `pill.bottom + 10`. Max width 520.
- **Launcher (UPDATED Sat ~2 PM, Michael's call): it opens OUT OF THE NOTCH.** ⌥Space makes the top-center pill expand downward, Dynamic-Island style, into the launcher (anchored top-center at the notch, width ~640, grows down as results stream in). "Build lesson" collapses it back up into the pill. **Every surface (launcher, cards, diagram, settings) is born from and returns to the notch island**; nothing pops up mid-screen. See mockups 01, 02 and 05 for the look.
- **Shortcut bar:** bottom-center, `24px` above the dock or taskbar (`workArea.bottom - 24 - height`). Width hugs its content, about 740.
- **Right-edge tab:** vertically centered, 6px from the right edge. Click it to open the lesson drawer.
- **Lesson player:** docked to the right **40%** of the screen at lesson start. The user can drag it; remember its position.
- **Spotlight caption:** right of the highlighted block, vertically aligned to its first line; flip to the left if it would go off-screen.

## Animation spec (the part that makes it feel like Apple)
Framer Motion everywhere. **Default spring: `{type:'spring', stiffness:420, damping:34, mass:0.9}`.** Respect `prefers-reduced-motion` (crossfades only).

| Moment | Motion |
|---|---|
| **Pill → expanded card (hover, 150ms delay)** | Dynamic-Island morph: animate `width`, `height` and `borderRadius` (17 → 24) together on the spring. **Content crossfades**: old content fades out over 80ms, new content fades in and rises 4px with a 60ms delay. The Electron window is pre-sized to the max; animate the inner div, never `setBounds` (it janks). |
| **Collapse (mouse leaves, 300ms delay)** | The reverse, slightly faster (damping 38). |
| **Launcher open (⌥Space)** | Backdrop: the desktop dim fades 0 → 0.35 over 160ms. Panel: `scale 0.96 → 1`, `opacity 0 → 1`, `y -8 → 0` on the spring. Caret focuses immediately. |
| **Search results streaming** | Each row slides in `y 6 → 0` + fade, **staggered 40ms**. The best result gets a soft blue highlight that glides between rows on arrow keys (shared `layoutId`). |
| **Build lesson** | The launcher **shrinks into the pill** (shared layout transition toward the top-center), then the pill shows "Step 1". About 450ms total. This is the signature transition; make it beautiful. |
| **Dim overlay + spotlight** | Dim fades in over 280ms. The cut-out rectangle **animates its position and size** with the spring when the target moves to another block (one animated SVG mask path, not a re-render). Glow ring pulses once (opacity 0.6 → 1 → 0.6, 1.2s) and then stays still. |
| **Check passes** | The check circle fills; the checkmark **draws its stroke** (`pathLength 0 → 1`, 250ms). |
| **Step passes** | The pill's progress ring advances (spring); the pill **flashes green** (background tint 0 → 0.25 → 0 over 600ms); the text crossfades to the next step; the video resumes 400ms later. |
| **Off-track** | The status dot turns amber and pulses twice (scale 1 → 1.35 → 1). The card drops down from the pill (morph). **No shaking, no red flashes.** Calm. |
| **Diagram popup** | Morph out of the pill like the card. The diagram's lines **draw in** (`pathLength`, 350ms, stagger 30ms per layer). |
| **Shortcut bar** | Appears when a lesson starts: `y 16 → 0` + fade. Pressed button: `scale 0.94` for 90ms. |
| **Voice speaking** | A 3-bar equalizer in the Voice button animates while audio plays. |

**Performance rules:** only animate `transform` and `opacity` (plus the pill's size via a transform-friendly wrapper); target 60fps; never call `setBounds` during an animation; preload every window at startup and toggle `show()`/`hide()` + opacity so nothing cold-starts during the demo.

## Settings: bring your own keys (like cue)
- A small Apple-style **Settings sheet** (⌘, or the gear in the expanded pill; also shown on first run): fields for **Anthropic** and **Gemini** (required), **ElevenLabs** (optional voice), **Tiger Data URL** (optional).
- Store them **encrypted with Electron `safeStorage`** (macOS Keychain / Windows DPAPI) in `app.getPath('userData')`. Never in plain text, never in the repo, never logged.
- On every WebSocket connect, send `config.keys {...}`; the engine replies `config.status` with ok / missing / invalid / env per key. Show a green dot per key and a "Test" button.
- If a key is empty, the engine falls back to its own `.env` (shown as "env"). That's how the demo Mac runs.

## Keyboard shortcuts (global; Windows: launcher is Ctrl+Shift+Space)
⌥Space ask/launcher · ⌥← back (rewind the step) · ⌥E explain more · ⌥D diagram · ⌥S show me (play the step's clip) · ⌥H hint · ⌥V voice toggle · Esc hide card.

## Diagrams (three React components; the server sends the data)
- `network`: layers from the real model (`[2,50,50,50,50,1]`, `tanh`), plus autograd arrows to u_t and u_x → residual.
- `gradients`: bars of gradient norm per layer over time. This shows the PINN failure visually.
- `heatmap`: predicted vs. exact u(x,t) on a canvas.

Keep each one minimal: one caption line, no axes clutter.

## Design tokens (`app/src/theme.ts`)
- **Radius:** 14 (chips), 20 (cards), 28 (launcher).
- **Text:** 13/15/20/28px, weights 400/500/600, labels at 60% white.
- **Accent:** system blue `#0A84FF`. **Status colors:** amber `#FFB020`, green `#30D158`.
- **Shadow:** `0 20px 60px rgba(0,0,0,.45)`. **Hairline border:** `rgba(255,255,255,.12)`.
- **Motion:** spring `{stiffness: 420, damping: 32}`. Expand/collapse 180–240ms. No bouncy toys.
- **Copy rule:** any card should be readable in 2 seconds, with at most about 12 words of body text.

## macOS permissions (do this early; it eats time)
- **Screen Recording:** granted to the terminal running the engine (not the app).
- **Screen Recording:** only if we take screenshots.
- Running unsigned from `npm run dev` is fine. No Apple developer account needed.

## Your Claude sessions (each in its own git worktree / branch)
- **F1 Shell:** windows, flags, global shortcuts, the WebSocket client, the mock replay.
- **F2 Components:** pill, launcher, shortcut bar, cards (match mockups 01–04).
- **F3 Spotlight:** full-screen dim overlay with an animated cut-out at `spotlight.rect`, plus `overlay.bounds` reporting.
- **F4 Player + voice + diagrams:** YouTube IFrame gating, audio playback, the 3 diagram components.

## Milestones
- **3:00 PM:** pill + launcher + shortcut bar visible and animating, driven by the mock.
- **6:00 PM:** the full `happy.json` plays end to end on screen. **Checkpoint 1.**
- **9:00 PM:** wired to the real engine; `offtrack.json` flow works. **Checkpoint 2.**
- **Overnight:** polish, diagrams, voice.
- **9:00 AM:** freeze. Demo mode = mock replay of the final run, as a safety net.

## Cut order if you're behind
Voice → heatmap diagram → dim overlay (fall back to a glowing outline at the rect) → the pill's hover expansion. **Never cut** the launcher, the pill status, the off-track card or video gating.

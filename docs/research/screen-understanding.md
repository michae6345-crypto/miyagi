# Screen understanding, cursor awareness and computer control: research (Sat Nov 14)

## Synthesis

MIYAGI: SCREEN UNDERSTANDING AND CONTROL PLAN (Sat ~1:45 PM)

**Today:** miyagi does 1 fps whole-screen OCR (about 240 ms per frame), spotlights via locate(text)→rect, and coaches with Opus. It has four gaps:
- It doesn't know where the cursor is.
- It has no exact element or line data.
- The overlay may be OCR'd in its own captures.
- Nothing confirms a step happened, and it can't control anything.

## 1. How Clicky works, and what we do better
- **Push-to-talk only.** On Ctrl+Option it takes one ScreenCaptureKit still per display, leaving out its own windows. Each is downscaled to 1280 px on the long edge and saved as JPEG at 0.8. There is no continuous loop.
- **Cursor awareness is just a label.** The screen under the cursor is sorted first and tagged "cursor is on this screen". The x,y position is never sent.
- **Pointing.** Claude ends its reply with `[POINT:x,y:label:screenN]`. The app clamps it, scales image pixels to points, flips Y and adds the display origin. Only one point per reply.
- **Overlay.** One click-through window per display at screen-saver level. A buddy follows the cursor (60 Hz poll) and flies a Bezier arc to the target, taking clamp(d/800, 0.6, 1.4) s. Moving the mouse cancels the flight.
- **Latency.** It warms TLS at startup, streams replies (SSE) and cancels on new speech. The open repo never checks whether a step happened. The closed HeyClicky added walkthroughs that detect clicks, and an "approve, then drive" mode that hands control back when you move the mouse or press Esc.

**What we do better:**
- Sense continuously and cheaply (cursor plus the accessibility tree) instead of only on a hotkey.
- Send the cursor's x,y and the element under it.
- Point at OCR or accessibility boxes, not raw model pixels.
- Put the point tag first and allow several targets.
- Confirm steps from both the input event and the screen.
- Gate proactive coaching so it doesn't nag.

## 2. Screen understanding stack (cheapest layer first)

**L0 Cursor.** `CGEventGetLocation` in the engine, or `screen.getCursorScreenPoint()` in Electron. Needs no permission, runs at 30-60 Hz and takes under 1 ms.

**L1 Events.** A listen-only CGEventTap catches mouse-down. App switches, typing pauses (800-1500 ms), scroll stops and terminal changes act as capture triggers. Debounce to at least 1.5 s between captures, as screenpipe does.

**L2 Accessibility tree, the main source for VS Code and Terminal.**
- Turn it on: set `AXManualAccessibility=true` once per VS Code process, then wait about 1 s. Never set it every frame, because that makes Chromium rebuild its whole tree.
- What it gives us:
  - The focused editor's `AXValue`: the live, unsaved buffer, a 500-line page.
  - `AXSelectedTextRange`: caret and selection.
  - `AXPosition` / `AXSize`: the exact rect of the cursor's line. Other lines are at `y + Δline × lineHeight`.
  - The window's `AXDocument`: the file path. A leading "●" in the title means unsaved changes.
  - `AXUIElementCopyElementAtPosition`: the element under the mouse.
  - Terminal output: xterm.js rows, or Terminal.app's `AXValue`.
- How to run it: one serial worker thread at 10 Hz with a 0.1-0.25 s messaging timeout. Estimated 5-30 ms per read.

**L3 OCR fallback.** Vision `.fast` with language correction off, on a crop of the focused window. Run it only on a trigger and when the frame hash changes (hash at no less than 480 px wide), or when the accessibility text is under about 100 characters.

**L4 Vision model, only at checkpoints.** That means a failed step check, a stuck learner, or a question. Send:
- a 1280-wide crop with a drawn cursor marker,
- a full-resolution 400×400 crop around the cursor,
- the accessibility/OCR text,
- "cursor at (x,y) over <element / line 42>".

Use set-of-mark: number the OCR or accessibility boxes and have the model return box IDs, which we turn into rects. Use Gemini flash-lite for quick "where is X" questions and Opus for coaching.

**Targets:**

| Signal | Target |
|---|---|
| Hover → line or element | under 100 ms |
| Step confirmed after the action | 600 ms or less |
| Spotlight moves after the model points | under 300 ms |
| First coach token | under 3 s |

**Must-dos:**
- Exclude the overlay from capture with `setContentProtection(true)`, and check that it actually works with our capture path.
- On the demo Mac, set `"editor.accessibilitySupport": "on"`. Clicking "No" on VS Code's screen-reader prompt switches it off for good.
- Grant Accessibility to the process that launches the engine.

## 3. Computer control ("do it for me")
Every action follows preview → confirm → act → undo.
- **Code edits:** the vscode-ext shows a diff preview, then applies a `WorkspaceEdit` (one Cmd+Z undoes it), then reveals and spotlights the change. Never type keystrokes into the editor; autocomplete and auto-closing brackets corrupt them.
- **Terminal:** `terminal.sendText(cmd, false)` stages the command and the learner presses Enter. For Terminal.app, paste with the clipboard plus Cmd+V and never send Return.
- **Navigation:** `code -g file:line`.
- **Clicks:**
  - By default a ghost cursor flies to the target and the user clicks.
  - A real `CGEventPost` click happens only after a "Take the wheel?" confirmation, and only inside a VS Code or Terminal window.
  - It stops on real mouse movement, Esc, or a change of frontmost app.
  - It never types into password fields (`AXSecureTextField`).
  - Convert pixels to points; Retina is 2x.
- **Claude computer use** is only a fallback for finding icons. Clicky's `computer_20251124` returns a 400 error on Opus 5.5, so use `computer_toolset_20260801`.
- **Skip OmniParser and UI-TARS:** no NVIDIA GPU, AGPL licensing, 7B+ models.

## 4. Six UX rules
1. **Quiet by default, with a hint ladder.** Step title, then spotlight, then a concept hint, then the exact fix plus "Do it for me". Rate-limit each step up the ladder.
2. **Speak only at breakpoints or when stuck.** Breakpoints: the terminal prompt returns, or a file is saved. Stuck: no progress for 45-60 s, the same error seen twice, or 3 s idle after the user acted. Never speak while the learner is typing (a keystroke in the last 2 s).
3. **Point at one thing.** Label it in three words or fewer. Show an edge arrow when the target is off-screen, and fade the dim when the cursor enters the target.
4. **Confirm with an event plus the screen.** If only one of the two fires, show "Looks done? Confirm" instead of asserting it.
5. **Use the cursor.** A hover hotkey explains what's under it. After 600 ms hovering on a known wrong target, pulse amber on the right one. Never block a click.
6. **Show exactly what will happen before acting.** Esc or a mouse move cancels, and one undo reverts it.

## 5. Build list (~10 h)

**P0**

| # | Item | Owner | Size |
|---|---|---|---|
| 1 | Cursor x,y plus the OCR box under it in every frame and coach payload | E6 | S |
| 2 | Overlay excluded from capture | Adrian | S |
| 3 | `ax.py`: VS Code enable-once, editor text/caret/line rect, path and dirty flag, element under cursor, terminal rows, serial worker, OCR fallback. Spike on the demo Mac in the first hour. | E6 | L |
| 4 | Event triggers, click tap and hash-gated OCR, replacing the 1 fps loop | E6 | M |
| 5 | Step confirm (event in target rect plus screen change), with "Confirm?" fallback | E4 | M |
| 6 | Hint ladder plus breakpoint/stuck state machine | E4 | M |
| 7 | Coach payload: cursor crop, set-of-mark IDs, point tag first with several targets, streaming, cancel on user action, warm connection | E5 | M |
| 8 | "Do it for me" through vscode-ext: diff → WorkspaceEdit, `sendText(cmd, false)`, `code -g`. E5 generates the patch, E4 wires the extension. | E5 + E4 | M |
| 9 | Ghost-cursor Bezier flight, hint card, "Take the wheel?" with Esc, green check | Adrian | M |

**P1**

| # | Item | Owner | Size |
|---|---|---|---|
| 10 | Confirmed CGEvent click or paste, with the guards above | E6 | M |
| 11 | PII regexes (card, SSN, email, phone) plus excluded apps (password managers, Messages) | E6 | S |
| 12 | Accessibility permission screen on first run | Adrian | S |

**Cut:** the ML confusion classifier, proactive voice, and local grounding models.

**Main risk:** none of the accessibility code has been run yet, because no session had the Accessibility grant. If the spike fails, the OCR-only stack already works; it just gets the cursor data from item 1.

**Sources:**
- github.com/farzaa/clicky: `CompanionScreenCaptureUtility.swift` L30-131, `CompanionManager.swift` L562-821, `OverlayWindow.swift` L411-554
- github.com/screenpipe/screenpipe: `event_driven_capture.rs`, `paired_capture.rs`, `tree/macos.rs`
- github.com/trycua/cua/pull/1756
- electronjs.org/docs/latest/tutorial/accessibility
- VS Code `screenReaderSupport.ts` L129-175
- platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool
- heyclicky.com/changelog

**Scratch files:**
- Source copies: `/private/tmp/claude-501/-Users-tripi-sand-hacks/310883d9-ce6c-4528-b04a-f5ddfa45fe76/scratchpad/clicky`, `/private/tmp/claude-501/-Users-tripi-sand-hacks/310883d9-ce6c-4528-b04a-f5ddfa45fe76/scratchpad/danpeg`
- Accessibility probe: `/private/tmp/claude-501/-Users-tripi-sand-hacks/310883d9-ce6c-4528-b04a-f5ddfa45fe76/scratchpad/axprobe/probe.py`


---

## Report: clicky

CLICKY DEEP-DIVE (source read from farzaa/clicky@main, danpeg/clicky, tryskilly/skilly; HeyClicky changelog)

1. Screen capture: `leanring-buddy/CompanionScreenCaptureUtility.swift` `captureAllScreensAsJPEG()` (lines 30-131)
- It uses ScreenCaptureKit and takes one still per display: `SCShareableContent.excludingDesktopWindows` → `SCScreenshotManager.captureImage` (line 94). It does not open a stream.
- Capture happens only on a push-to-talk turn. There is no continuous loop.
- Clicky leaves its own overlay out of the image with `SCContentFilter(display:, excludingWindows: ownAppWindows)` (lines 43-45, 81).
- The long side is downscaled to 1280px, keeping the aspect ratio (lines 84-92). The result is saved as JPEG at quality 0.8.
- Multi-monitor: it maps SCDisplay to NSScreen through `NSScreenNumber`, so frames are in AppKit coordinates with a bottom-left origin (lines 47-58). It then sorts so the screen holding the cursor comes first. Each image gets a label: "screen N of M — cursor is on this screen (primary focus)". That label is the only cursor information the model gets. Clicky never sends the cursor's x,y.
- danpeg fork, `captureFocusedWindowAsJPEG()` (CompanionScreenCaptureUtility.swift ~136-200): captures only the frontmost app's window with `SCContentFilter(desktopIndependentWindow:)`, giving a sharper image. Model coordinates are then relative to that window.

2. Coordinate mapping, the `[POINT:x,y:label:screenN]` tag
- System prompt: `CompanionManager.swift` lines 562-576. The model is told to use pixel coordinates of the image, with the dimensions written into the image label (line 604: "image dimensions: 1280x831 pixels"). The tag must come at the end of the reply, and `[POINT:none]` means no pointing.
- Parser `parsePointingCoordinates` (lines 784-821), regex `\[POINT:(?:none|(\d+)\s*,\s*(\d+)(?::([^\]:\s][^\]:]*?))?(?::screen(\d+))?)\]\s*$`.
- Mapping (lines 650-675): clamp to image size → multiply by displayPoints/imagePixels → flip Y (`displayHeight - y`) → add `displayFrame.origin`. `screenN` picks the capture by index and falls back to the cursor screen.
- Only one point per reply is supported.
- `ElementLocationDetector.swift` is dead code; nothing references it. It is still worth reading. It calls the Claude computer-use tool (`computer_20251124`, beta `computer-use-2025-11-24`, lines 160-185). It resizes to the recommended resolution closest in aspect ratio (1024x768, 1280x800 or 1366x768; lines 32-36) because the code comments say this gives better pixel accuracy than plain vision prompting.

3. Flying cursor overlay: `OverlayWindow.swift`
- There is one borderless, full-screen `NSWindow` per screen (lines 14-30), set to `level = .screenSaver`, `ignoresMouseEvents = true`, `collectionBehavior = [.canJoinAllSpaces, .stationary, .fullScreenAuxiliary]` and `canBecomeKey=false`. `OverlayWindowManager.showOverlay(onScreens:)` is at line 783.
- Following the cursor: a 16 ms `Timer` polls `NSEvent.mouseLocation` and places the buddy at cursor +35,+25 with a SwiftUI spring (`startTrackingCursor`, line 411).
- Flight: `animateBezierFlightArc` (line 495) moves along a quadratic Bezier at 60 fps. Duration is `clamp(dist/800, 0.6, 1.4)` s and the arc height is `min(dist*0.2, 80)`. The triangle rotates along the tangent.
- `startPointingAtElement` (line 572) streams the bubble text one character at a time, holds for 3 s, then flies back. On the return flight, moving the mouse more than 100 px cancels it (lines 418-428).

4. Latency
- `ClaudeAPI.swift`: one HEAD request at startup warms up TLS (lines 64-97). It uses a `.default` URLSession to cache TLS tickets and SSE streaming with `max_tokens` 1024.
- `CompanionManager.sendTranscriptToClaudeWithScreenshot` (line 586) cancels any earlier task when the user speaks again. It shows a spinner until TTS audio actually starts. It keeps the last 10 exchanges and strips POINT tags from history (lines 690-705).
- Weak spot: it waits for the full reply before flying, because the tag is at the end.
- HeyClicky later added a fast/frontier model router (1.0.45, Jul 31), streaming STT at about 450 ms (1.0.37) and warm-up (1.0.46).

5. Proactive tutoring (danpeg fork) and Skilly "live tutor"
- danpeg `UserActivityIdleDetector.swift` uses `NSEvent.addGlobalMonitorForEvents` on mouse, key and scroll events and checks every 0.5 s. It fires after 3 s idle, and only if `hasUserActedSinceLastObservation`, which prevents spam (lines 32-87).
- `bindTutorIdleObservation` (CompanionManager ~841) runs only when the voice state is idle, TTS is not playing and no observation is already in flight.
- The tutor prompt (~609) says to point aggressively, acknowledge a finished step and then give the next one, and not repeat itself.
- Skilly (`docs/superpowers/plans/2026-04-12-live-tutor-mode.md`): an always-on mic over OpenAI Realtime with `server_vad` (silence 700 ms). It takes screenshots on `speech_started`, not continuously, and the mic auto-sleeps after 5 min of silence.
- Skilly's step progress (`CurriculumEngine.swift` lines 19-29) is a case-insensitive keyword match of "completion signals" against the transcript and reply text. It never checks the screen. Avoid this.

6. HeyClicky features that are not open source (https://heyclicky.com/changelog)
- 1.0.26 (Jun 19): walkthroughs with on-screen drawing that "detects when you click where it told you to, and moves you to the next step". There is no click-detection code in any open repo. The obvious design is a global mouse-down monitor plus a hit test against the target rect, which danpeg already uses for idle detection.
- 1.0.48: walkthroughs raised to 15 steps, keeping the goal and completed steps across pauses.
- 1.0.53: walkthroughs keep a running log of actions, wait for slow pages to load, and release the cursor once you move the mouse.
- Computer control history: Cua at first (1.0.12, "sometimes buggy"), then a native driver whose "background clicks stay scoped to the target window and never move your real cursor" (1.0.48). "HeyClicky drive" (1.1.1) moves the real mouse and types after approval, and "Moving the mouse, speaking, or pressing Escape returns control to you."
- Lessons: blocking accessibility queries caused cursor lag (1.0.27). They later removed all accessibility-data collection over privacy (1.0.39, 1.0.46).

COPY
- The labeled image dimensions, the clamp-then-scale-then-flip mapping, and the cursor-screen-first ordering.
- Excluding your own windows from capture.
- Bezier flight timing and the spring follow.
- Idle plus "user acted since last observation" gating.
- Capture on a trigger, not continuously, for the expensive LLM call.
- Cancelling an in-flight request when the user acts.
- Pointing at a resolution matched to the aspect ratio, or using the computer-use tool, for pixel accuracy.

AVOID
- The POINT tag at the end of the reply. Emit it first so the cursor moves while text streams.
- Only one point per reply.
- Keyword-match step completion (Skilly).
- Accessibility (AX) calls on the UI thread.
- Moving the user's real pointer without a visible takeover mode and an instant way to cancel.

RECOMMENDATIONS FOR MIYAGI
- **Cursor as first-class state, 60 Hz and free.** In Electron, poll `screen.getCursorScreenPoint()` and `screen.getDisplayNearestPoint()`, which avoids Clicky's AppKit Y-flip because Electron uses top-left DIP coordinates. Send the engine `{x, y, display}` with each frame. Find what is under the cursor by intersecting the cursor with the Apple Vision OCR rects you already have. Add `AXUIElementCopyElementAtPosition` through pyobjc on a worker thread with `AXUIElementSetMessagingTimeout` around 50 ms, which avoids HeyClicky's lag bug. Also feed the model a 400x400 crop around the cursor at full resolution, since a 1280px downscale makes code text unreadable.
- **Step completion from the screen, never from keywords.** Keep the current check of each step against what is on screen. Add HeyClicky-style click detection: a listen-only `CGEventTap` or pynput mouse-down event, hit-tested against the spotlight rect inflated by about 16 pt. The event plus an OCR re-check about 600 ms later advances the step. Trigger coaching with danpeg's gate: 3 s idle and the user acted since the last observation.
- **Point at OCR boxes, not raw model pixels.** Have Claude return a target text or line, then resolve it with `locate(text)→rect`. Fall back to a Clicky-style `[POINT:x,y]` in a 1280-wide image, snapped to the nearest OCR box. Put the tag first and allow several targets per reply.
- **Overlay in Electron is the same recipe as Clicky.** One transparent window per display: `setAlwaysOnTop(true,'screen-saver')`, `setIgnoreMouseEvents(true,{forward:true})`, `setVisibleOnAllWorkspaces(true,{visibleOnFullScreen:true})`, `focusable:false`. Port the Bezier flight (`clamp(d/800,0.6,1.4)` s, arc `min(0.2d,80)`) with requestAnimationFrame for a "fly to the spotlight" moment. Exclude the overlay from capture, or blank the dim layer during the frame grab, so OCR doesn't read your own UI.
- **"Do it for me" safely in about 12 h.** For code fixes, don't synthesize keystrokes. Write the file or a patch directly, then run `code --goto file:line` and spotlight the change. That is reliable and easy to undo. For terminal or GUI actions, follow HeyClicky drive: an explicit "Take the wheel?" confirmation in the pill. Use `CGEventPost` to click and paste through the clipboard plus Cmd+V. Give control back immediately on any real mouse movement or Escape, which the same event tap can detect. Show the agent's cursor separately from the user's.
- **Latency.** Warm the API connection at boot and stream replies. Cancel in-flight calls when the user acts. Route quick "is this step done?" checks to OCR rules or a fast model, and send only the coaching reply to Opus, as HeyClicky's router does.

Sources: https://github.com/farzaa/clicky (CompanionScreenCaptureUtility.swift, CompanionManager.swift, OverlayWindow.swift, ElementLocationDetector.swift, ClaudeAPI.swift), https://github.com/danpeg/clicky (UserActivityIdleDetector.swift, CompanionScreenCaptureUtility.swift, CompanionManager.swift), https://github.com/tryskilly/skilly (CurriculumEngine.swift, docs/superpowers/plans/2026-04-12-live-tutor-mode.md), https://heyclicky.com/changelog. Downloaded copies of the source are in /private/tmp/claude-501/-Users-tripi-sand-hacks/310883d9-ce6c-4528-b04a-f5ddfa45fe76/scratchpad/clicky, /private/tmp/claude-501/-Users-tripi-sand-hacks/310883d9-ce6c-4528-b04a-f5ddfa45fe76/scratchpad/danpeg and /private/tmp/claude-501/-Users-tripi-sand-hacks/310883d9-ce6c-4528-b04a-f5ddfa45fe76/scratchpad/skilly.

---

## Report: computer-use

TOPIC: Computer-use grounding and control on macOS, and what miyagi can ship tonight

**1. Claude computer use (current state)**
- **Toolset:** the current tool is `{"type":"computer_toolset_20260801"}`. It is GA, needs no beta header, and takes no `name` or display size. It has 17 member tools: screenshot, zoom, left/right/middle/double/triple_click, left_click_drag, mouse_move, left_mouse_down/up, cursor_position, scroll, type, key, hold_key, wait. Each call arrives as a `tool_use` block whose `name` is the action and which carries `toolset_name:"computer"`. Every result must echo `toolset_name`.
- **Batches:** Claude can send several actions in one turn. Run them in order and stop at the first failure. Answer every later action with "Not executed: an earlier computer action in this turn failed." and `is_error: true`.
- **Older tool versions:** `computer_20251124` returns a 400 on Opus 5.5, Sonnet 5.5 and Haiku 5.5 on the Claude API. Source: https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool.md
- **Screenshot scaling:** the API does not downscale for you. Oversized images are rejected.
  - Limit on Opus 4.7 and later: 2,576 px long edge and 4,784 visual tokens (`ceil(w/28)*ceil(h/28)`, about 3.75 MP).
  - Recommended sizes: 1280x720 to 1366x768. Avoid going above 1920x1080.
  - Coordinates come back in the pixel space of the screenshot you sent, so divide by your scale factor before clicking.
  - The docs warn that Retina captures at 2x, so halve the coordinates or downscale the image first.
- **Zoom:** takes `region:[x0,y0,x1,y1]` and returns that region at full resolution. Coordinates stay in full-screenshot space. It is on by default; turn it off with `configs:{"zoom":{"enabled":false}}`. Use it for small text such as error lines and line numbers.
- **Accuracy (from the docs):** take a screenshot after each step to verify. Prefer keyboard shortcuts over dropdowns. Put the instruction text before the image.
- **Cost:**
  - Each screenshot is about 1,000 to 1,800 input tokens.
  - That is roughly $0.004 to $0.007 per screenshot on Opus 5.5 ($4/$20 per MTok), $0.002 to $0.004 on Sonnet 5.5, and about $0.0002 on Haiku 5.5 (my arithmetic from published prices).
  - When a request carries more than 20 images, each image gets a stricter size limit.
  - Opus 5.5 defaults to effort `medium` and its thinking cannot be disabled.
- **Latency:** the docs give no figure. My estimate is several seconds per step for Opus with an image. That is too slow to run every frame, which is fine for one-off grounding.
- **Security (from the docs):** run in a VM with least privilege, keep credentials away from the model, and have a human confirm consequential actions. Anthropic runs prompt-injection classifiers on screenshots.

**2. OpenAI**
- The Responses API exposes a GA `{type:"computer"}` tool. It returns `computer_call` items whose ordered `actions[]` are click, double_click, drag, move, scroll, keypress, type, wait and screenshot, with pixel coordinates.
- The current guide's example model is `gpt-6.1-sol`. For GPT-6 Astra the guide recommends code execution over the computer tool. The desktop sample uses PyAutoGUI with its fail-safe on. Source: https://developers.openai.com/api/docs/guides/tools-computer-use
- `computer-use-preview` is legacy.

**3. Gemini**
- Computer-use models listed: gemini-4-carbon, gemini-4-argon, gemini-4-hydrogen, gemini-3.8-flash, gemini-3.5-flash-lite, gemini-3-flash-preview.
- There is an `ENVIRONMENT_DESKTOP` with OS-level cursor actions (click, hotkey, drag_and_drop, and so on).
- Coordinates are normalized 0–999 (pixel = x/1000 × width), so retina scaling never trips it up.
- `excluded_predefined_functions` removes actions you don't want it to take.
- Each call carries a `safety_decision` of allowed, `require_confirmation` or blocked. For `require_confirmation` you prompt the user and send back `safety_acknowledgement`. Source: https://aistudio.google.com/docs/computer-use
- The team already uses Gemini, so it is a cheap "where is X" grounder (flash-lite).

**4. Open grounding models**
- **OmniParser v2** (microsoft/OmniParser, 25.6k stars): a YOLOv8 icon detector plus Florence-2 captions. About 0.6 s/frame on an A100 and 0.8 s on a 4090. 39.6% on ScreenSpot-Pro. The icon detector is AGPL. Not practical on a Mac with no NVIDIA GPU.
- **UI-TARS-1.5:** 61.6% on ScreenSpot-Pro (7B: 49.6%). bytedance/UI-TARS-desktop (39.6k stars) runs a local operator on macOS.
- **Others:**
  - UI-Venus-1.5 8B: about 68%.
  - GTA1-32B: 63.6%.
  - Holo2-235B: 78.5%.
  - OS-Atlas-7B: 18.9% (older).
  - ShowUI: no recent score found.
- **Frontier models** reportedly score about 88 to 93% on ScreenSpot-Pro (self-reported aggregator figures, unverified).
- **Set-of-Mark** (microsoft/SoM): draw numbered boxes over candidate elements and have the LLM pick a number. Miyagi already has OCR boxes from Vision, so this is nearly free: overlay numbered OCR or AX boxes and ask Claude "which box?". That removes pixel-regression error entirely.
- **Accessibility-tree agents** (trycua/cua at 32k stars, MIT; Browser Use macOS harness; Ghost OS; Vercel agent-desktop) read the macOS accessibility tree for exact element rects and labels and use pixels only as a fallback.
  - The catch: Electron and Chromium apps, VS Code included, expose an empty tree until you set `AXManualAccessibility=true` on the app's AXUIElement. Cua merged exactly this fix in PR #1756 on 2026-05-31. See also https://electronjs.org/docs/latest/tutorial/accessibility

**5. Reading the cursor and sending input on macOS**
- **Cursor position:** no permission is needed to read it.
  - Python: `Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))` gives global points with the origin at top-left.
  - `NSEvent.mouseLocation()` uses a bottom-left origin.
  - Electron: `screen.getCursorScreenPoint()` (DIP).
  - Poll at 30–60 Hz; it costs nothing.
- **The cursor is missing from our screenshots** (my understanding of `CGDisplayCreateImage`, not tested here). The current capture in `server/screen/macos.py:60-68` would then send screenshots without the pointer, so the model can't "see" where the user is pointing. Draw a synthetic cursor marker onto any frame sent to an LLM, and pass `cursor=(x,y)` along with the nearest OCR block as text.
- **What is under the cursor:** `AXUIElementCopyElementAtPosition(AXUIElementCreateSystemWide(), x, y)` returns role, title, value and AXSelectedText. It needs Accessibility permission, plus `AXManualAccessibility` for VS Code.
- **Sending input:**
  - Use `CGEventCreateMouseEvent` / `CGEventCreateKeyboardEvent` + `CGEventPost(kCGHIDEventTap, …)`. Use `CGEventKeyboardSetUnicodeString` to type strings.
  - pyautogui does exactly this (pyautogui/_pyautogui_osx.py:247, 255; position via NSEvent at :296), in points, not pixels.
  - AppleScript `System Events keystroke` additionally needs the Automation permission.
  - Avoid robotjs and nut.js in Electron; do input from the Python engine.
- **Permissions:**
  - Screen Recording for capture.
  - Accessibility for posting events and AX reads. It is granted to the responsible process (Terminal or iTerm in dev, the Electron app if it spawns Python), and grants are tied to code signing.
  - On Sequoia, `CGPreflightPostEventAccess` and `AXIsProcessTrusted` can disagree.
  - The scale factor (2.0 on Retina) must be applied when converting screenshot pixels to event points. `macos.py` already computes `Frame.scale`.

**6. Safe "do it for me" design**
Don't let an LLM drive raw clicks across the desktop. Instead:
- **Editor edits:** apply them through the VS Code extension (`vscode-ext/`, which the plan already has reporting line rects).
  - Show the proposed change as a diff or inline ghost text first.
  - On confirm, apply it with `WorkspaceEdit` / `editor.edit`. That is one undo stop, so Cmd+Z reverts it, and it is scoped to the active file.
- **Terminal commands:** use `terminal.sendText(cmd, false)` so the command is staged but not run, and the learner presses Enter.
- **Clicks:** keep them to "move cursor and highlight" (spotlight plus an animated ghost cursor). Allow a real click via CGEvent only after an explicit confirm, and only when the target is inside a VS Code or Terminal window rect from `list_windows()`.
- **Guardrails:**
  - Log every action.
  - Give the user an Esc kill-switch.
  - Never type into password fields (check the AX subrole AXSecureTextField).
  - Pause automatically if the frontmost app changes mid-action.

RECOMMENDATIONS FOR MIYAGI
- **Cursor awareness tonight (about 1 h):** poll `CGEventGetLocation` in the engine. Attach `{cursor_pt, ocr_block_under_cursor, nearest_text_lines}` to every coach call, and draw a cursor marker on any screenshot sent to Claude or Gemini. Cheap, and it makes "you're pointing at the wrong line" feedback possible.
- **Ground with set-of-mark over existing OCR boxes, not raw pixels:** number the Vision blocks in the frame and ask Claude to return box IDs, then map them to rects with the existing locate(). Use `computer_toolset_20260801` only as a fallback for icon or non-text targets. Downscale to 1280-wide and divide the coordinates by the scale.
- **Enable the AX tree for VS Code** (`AXManualAccessibility`, copy cua's approach), and use `AXUIElementCopyElementAtPosition` for exact element info under the cursor. Use OCR only as the fallback.
- **Ship "Do it for me" through the VS Code extension:** a diff preview, then `WorkspaceEdit` (undoable with Cmd+Z), plus `terminal.sendText(cmd, false)` (staged, not executed). This is safer, more precise and demo-reliable compared with pixel clicking, and buildable in about 3 to 4 h.
- **Keep any real CGEvent clicks or typing behind an explicit confirm,** scoped to the VS Code or Terminal window rect, with an Esc abort and a check that the frontmost app hasn't changed. Grant Accessibility to the process that actually posts the events.
- **Skip OmniParser and UI-TARS tonight:** no NVIDIA GPU, AGPL licensing, and a 7B+ local model. Mention them as "future: local private grounding".

---

## Report: macos-ax

## macOS Accessibility (AX) for miyagi: research findings

### Summary
AX can tell miyagi which app and window are focused, which element is focused, where the mouse is and what is under it, and what text is in the editor. It needs no OCR to do this. The catch for VS Code is that you only get its tree if you switch it on yourself. A frame read takes a few milliseconds, against about 240 ms for OCR. Screenpipe ships a "walk the AX tree first, use OCR only if that fails" pipeline built this way.

### Permissions (tested on this Mac, macOS 26 / Darwin 25.6)
I ran a probe script from this session, and the process is not yet trusted for Accessibility.
- **Mouse position needs no permission.** Both `NSEvent.mouseLocation()` and `CGEventGetLocation(CGEventCreate(None))` returned a position. They use different origins: Cocoa's is bottom-left, CG's is top-left.
- **Element under the cursor needs Accessibility.** `AXUIElementCopyElementAtPosition` returned -25211 (`kAXErrorAPIDisabled`) because Accessibility is not granted.
  - Accessibility covers all AX reads and writes and also `CGEventPost`, i.e. synthetic clicks and keys (`CGPreflightPostEventAccess`).
  - A keyboard event tap needs Input Monitoring (`CGPreflightListenEventAccess`).
  - Pixels need Screen Recording.
- **Who gets the grant:** permissions attach to the "responsible" app. If the Python engine is launched by the Electron overlay or by Terminal, that app needs the grant. Prompt for it with `AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True})`.
- **Coordinates line up:** AX frames are top-left global points, the same as CGWindowList and Electron `screen` coordinates (DIP). Spotlight rects can go to the overlay without conversion.

### Electron and VS Code: the tree is off by default
Chromium and Electron only build their AX tree when an assistive client asks for it.
- **How to turn it on:** set `AXManualAccessibility=true` on the app element; this is Electron's documented hook (https://www.electronjs.org/docs/latest/tutorial/accessibility). Fall back to `AXEnhancedUserInterface`.
- **Settle time:** wait about 500 ms the first time (trycua/cua PR #1756, https://github.com/trycua/cua/pull/1756). Without this, VS Code returns an empty or title-bar-only tree.
- **Set it once per process, not every frame.** Screenpipe found that re-setting the flag on every frame makes Chromium rebuild its tree and can commit "phantom text" into the focused field.
  - Source: https://github.com/screenpipe/screenpipe/blob/main/crates/screenpipe-a11y/src/tree/macos.rs, lines 712-724 and 845-895.
  - Screenpipe also raises the walk depth to 40 for Code and its forks, because terminal rows sit about 37 levels deep (lines 129-150 and 955-970).

### What VS Code exposes (from source; not tried live, since this session has no Accessibility grant)
With `editor.accessibilitySupport: "on"` (or auto-detected), the focused editor is a `role=textbox aria-multiline` div.
- **Text:** its `AXValue` is a page of lines around the cursor. `editor.accessibilityPageSize` defaults to 500 lines (`src/vs/editor/common/config/editorOptions.ts`, line about 6145; `native/screenReaderContentSimple.ts`, lines 41-66).
- **Cursor:** `AXSelectedTextRange` gives the caret offset within that page, and `AXSelectedText` gives the selection.
- **The cursor line's rectangle:** VS Code positions this hidden div exactly on the caret's line, with the editor's font and one line-height tall (`native/screenReaderSupport.ts`, lines 129-175). So the focused element's `AXPosition` plus `AXSize` is roughly the pixel rectangle of the cursor's line. If the caret is out of view, the div is parked at the top-left with height 1. Treat that as "unknown".
- **Character-level rectangles:** Chromium implements `AXBoundsForRange`, `AXLineForIndex`, `AXRangeForLine`, `AXInsertionPointLineNumber` and `AXVisibleCharacterRange` for editable nodes. Source: https://chromium.googlesource.com/chromium/src/+/main/ui/accessibility/platform/browser_accessibility_cocoa.mm, lines 2559-2563 and 3008-3021.
- **Caveats on those rectangles:**
  - Chromium's own TODO at line 1126 says `AXInsertionPointLineNumber` is wrong for contenteditable. It is also relative to the page, not the file.
  - My inference (not tested): for characters on the caret line, `AXBoundsForRange` should match the screen. For other lines it will be offset by `scrollTop` inside the clipped div, and it breaks with word wrap or folding.
  - Practical fix: anchor on the cursor-line rect and add (line difference × line height), or check against OCR.
- **File line number:** the status-bar item ("Ln 42, Col 7") and the window title (file name) are plain AX text. They are more reliable than computing the line number.
- **Integrated terminal:** with accessibility on, xterm.js renders each visible row as a `listitem` sized to the cell height (https://github.com/xtermjs/xterm.js/blob/master/src/browser/AccessibilityManager.ts, lines 68 and 394-401). That gives row text plus row rectangles, so the last N lines of terminal output come without OCR.

### Terminal.app and iTerm2
- Both expose the scrollback as an `AXTextArea`, with `AXValue` holding the text.
- iTerm2 implements bounds-for-range in `sources/Accessibility/iTermTextViewAccessibilityHelper.m`, so exact character and line rectangles are possible there.

### Working pyobjc code
The calls were checked against pyobjc 12 on this Mac. The `AXValue` round-trip works; reads that need the Accessibility grant were not tried. Install `pyobjc-framework-ApplicationServices` plus Quartz and Cocoa.

```python
import HIServices as AX, Quartz
from AppKit import NSWorkspace

def attr(el, name):
    err, v = AX.AXUIElementCopyAttributeValue(el, name, None)
    return v if err == 0 else None

def rect_of(el):
    p, s = attr(el, "AXPosition"), attr(el, "AXSize")
    if p is None or s is None:
        return None
    _, pt = AX.AXValueGetValue(p, AX.kAXValueCGPointType, None)
    _, sz = AX.AXValueGetValue(s, AX.kAXValueCGSizeType, None)
    return (pt.x, pt.y, sz.width, sz.height)        # top-left global points

def bounds_for_range(el, loc, length):
    rng = AX.AXValueCreate(AX.kAXValueCFRangeType, AX.CFRange(loc, length))
    err, v = AX.AXUIElementCopyParameterizedAttributeValue(el, "AXBoundsForRange", rng, None)
    return AX.AXValueGetValue(v, AX.kAXValueCGRectType, None)[1] if err == 0 else None

pid = NSWorkspace.sharedWorkspace().frontmostApplication().processIdentifier()
app = AX.AXUIElementCreateApplication(pid)
AX.AXUIElementSetMessagingTimeout(app, 0.25)        # stop a hung app from stalling the walk
AX.AXUIElementSetAttributeValue(app, "AXManualAccessibility", True)   # do this once per pid

focused = attr(app, "AXFocusedUIElement")
text = attr(focused, "AXValue")                     # the page of lines around the cursor
_, sel = AX.AXValueGetValue(attr(focused, "AXSelectedTextRange"), AX.kAXValueCFRangeType, None)
caret_line_rect = rect_of(focused)                  # VS Code: the cursor line's rect

m = Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
err, under = AX.AXUIElementCopyElementAtPosition(AX.AXUIElementCreateSystemWide(), m.x, m.y, None)
```

**Change events.** Use `AXObserverCreate(pid, callback)` and `AXObserverAddNotification(obs, app, "AXFocusedUIElementChanged" | "AXSelectedTextChanged" | "AXValueChanged", None)`. Then attach `AXObserverGetRunLoopSource(obs)` to a `CFRunLoop` running on its own thread.

**Clicks.** Use a listen-only `CGEventTapCreate` for `kCGEventLeftMouseDown`. Mouse taps work with the Accessibility grant; keyboard taps need Input Monitoring.

### Apple references
- `AXUIElementCopyElementAtPosition`: https://developer.apple.com/documentation/applicationservices/1462077-axuielementcopyelementatposition
- `AXIsProcessTrustedWithOptions`: https://developer.apple.com/documentation/applicationservices/1459186-axisprocesstrustedwithoptions
- `AXObserverCreate`: https://developer.apple.com/documentation/applicationservices/1460133-axobservercreate
- `kAXBoundsForRangeParameterizedAttribute`: https://developer.apple.com/documentation/applicationservices/kaxboundsforrangeparameterizedattribute
- `CGPreflightListenEventAccess`: https://developer.apple.com/documentation/coregraphics/cgpreflightlisteneventaccess

### Control ("do it for me")
- **Buttons and controls:** `AXPress` works on real buttons.
- **Code edits:** synthetic typing with `CGEventPost` / `CGEventKeyboardSetUnicodeString` is fragile in Monaco (autocomplete and auto-close brackets interfere). Setting `AXValue` on the hidden div does not edit the file. The repo already has `vscode-ext/`; a `WorkspaceEdit` plus `revealRange` through that extension is far more reliable.
- **Terminal:** paste or type with `CGEventPost`, or use AppleScript `do script` (Terminal) or iTerm2's Python API.

### Other projects that do this
- **Screenpipe:** AX walk first, Vision OCR as fallback. The Mintlify docs call OCR about 10-50x slower.
- **trycua cua-driver:** AX plus Chromium enablement for computer use.
- **Talon and Raycast:** read the focused element and selection through AX.

I could not find public source for Highlight or Rewind.

### RECOMMENDATIONS FOR MIYAGI
- **Add an `ax.py` alongside `server/screen/macos.py`, run as a 10-20 Hz poll.** Each tick reads the frontmost pid, the focused element's role, value, selected range and frame, the mouse location, and `ElementAtPosition`'s role and value. Set `AXManualAccessibility` once per pid with `SetMessagingTimeout(0.25)`. Keep OCR at 1 Hz as a fallback and for checking the AX results.
- **Spotlight from the cursor-line rect.** In the onboarding doc, set `"editor.accessibilitySupport": "on"` (the auto-detect does not reliably fire for a non-VoiceOver client), and spotlight the focused editor's AX frame. Compute other lines' rects from it (line-height × line difference) and check them against OCR's `locate()`.
- **Read terminal output from xterm.js rows.** Use the VS Code integrated terminal rows, or Terminal.app / iTerm2 `AXValue`. This catches tracebacks and loss values instantly, without OCR.
- **Use AXObserver events to trigger checks.** Fire step checks and coaching on `AXValueChanged` / `AXFocusedUIElementChanged` instead of polling frames. Add a listen-only mouse-click event tap so the coach can see "they clicked the wrong thing" and point at what is under the cursor.
- **Route "do it for me" by target.** Send code edits through the `vscode-ext` `WorkspaceEdit` API. Use `AXPress` and `CGEventPost` only for buttons and terminal input, and gate them behind an explicit confirm in the pill.
- **Add an Accessibility gate to first-run.** Call `AXIsProcessTrustedWithOptions` with the prompt next to the existing Screen Recording gate. Pre-grant the demo machine, and note which app is "responsible" for the engine process.

### Files
Scratch probe scripts on this Mac:
- /private/tmp/claude-501/-Users-tripi-sand-hacks/310883d9-ce6c-4528-b04a-f5ddfa45fe76/scratchpad/axprobe/probe.py
- /private/tmp/claude-501/-Users-tripi-sand-hacks/310883d9-ce6c-4528-b04a-f5ddfa45fe76/scratchpad/axprobe/v.py

Existing screen code to extend: /Users/tripi/sand hacks/sandhacks-tutor/.claude/worktrees/michael-orchestrator-0aded6/server/screen/macos.py

---

## Report: realtime-pipelines

TOPIC: How production "always-watching" screen apps build fast, cheap, accurate pipelines, and what miyagi should copy

The strongest source is screenpipe (mediar-ai/screenpipe, about 22k stars, pushed today). It is open source, macOS-first, and solves the same problem miyagi has. The other products are mostly closed, so what's known about them is thinner and noted as such.

1. Capture on events, not on a fixed 1 fps loop (screenpipe)
- `crates/screenpipe-engine/src/event_driven_capture.rs` L343-370: the `CaptureTrigger` enum is AppSwitch, WindowFocus, Click{x,y}, TypingPause, ScrollStop, KeyPress, Clipboard, VisualChange, Idle and Manual. A click trigger carries the cursor coordinates.
- Defaults at L594-606: `min_capture_interval_ms: 200` (debounce), `idle_capture_interval_ms: 30_000`, a visual-change check every 3,000 ms, and `visual_change_threshold: 0.05` (about 5% pixel difference).
- L636: `CHECKPOINT_MIN_INTERVAL_MS = 1_500`. The comment says that firing a capture on every keystroke caused a "capture storm", because each one ran screenshot + tree walk + OCR + DB write. Typing therefore triggers on a typing pause, with a floor of 1.5 s between captures.
- Input comes from a CGEventTap (`crates/screenpipe-a11y/src/platform/macos.rs`). It needs the Input Monitoring permission and falls back to polling when that is denied.
- Their architecture docs claim under 0.5% CPU on a static screen for event-driven capture, versus 3-5% for continuous 1 fps (https://mintlify.com/screenpipe/screenpipe/architecture). Overall they claim 5-10% CPU. These are the project's own numbers, not independent benchmarks.
- Microsoft Recall uses the same idea: "Snapshots are taken every five seconds while content on the screen is different from the previous snapshot" (https://learn.microsoft.com/windows/client-management/manage-recall).

2. Cheap change detection before any expensive work
- `crates/screenpipe-screen/src/frame_comparison.rs` L1-36: first a hash of a frame downscaled 4x, which exits early on identical frames and saves 30-50% in static scenes. Then a single histogram metric; they dropped SSIM, which saves another 40-50%.
- L103-106: downscaling 6x (to 320 px) caused hash collisions on dense text, so scrolling log files went undetected. For text-heavy screens like a terminal, don't downscale below about 480 px wide.
- On macOS, ScreenCaptureKit already skips most of this: `SCFrameStatusIdle` means no new frame when nothing changed, and `SCStreamFrameInfo.dirtyRects` lists the changed regions (https://developer.apple.com/documentation/screencapturekit/scstreamframeinfo, WWDC22 10155). Caveat from the Apple forums: idle frames can arrive with nothing visibly changing (https://developer.apple.com/forums/thread/718356).

3. Read text from the accessibility tree first, and OCR only where needed
- `crates/screenpipe-capture/src/paired_capture.rs`: each capture pairs a screenshot with an accessibility (AX) tree walk, which takes about 10-50 ms on macOS according to their docs. OCR runs only when the AX text is missing or thin (L367-388).
- "Thin" is defined at L1040-1117: fewer than 100 characters in total, or less than 30% of characters coming from content roles as opposed to toolbar/menu chrome.
- Terminals with poor AX output always use OCR: WezTerm, Alacritty, kitty, Hyper and Warp (L344-360). Terminal.app, iTerm2 and Ghostty were removed from that list because their AX text is good enough.
- `crates/screenpipe-capture/src/ocr_gate.rs` L1-40 is the OCR gate. It crops the screenshot to the focused window, finds text regions (about 10-20 ms), and takes the union of those boxes. It pixel-hashes that crop (1-3 ms) and runs OCR only if the hash changed; otherwise it reuses the cached text. The comment says earlier heuristics (stability waits, per-region hashes) "produced wrong skips" and were removed.
- VS Code is an Electron app, so its AX tree is empty unless you set `AXManualAccessibility` / `AXEnhancedUserInterface` on the app. Rebuilding that tree is expensive. Setting the flag on every walk "kept WindowServer pegged", so screenpipe sets it at most once per process every 60 s (`crates/screenpipe-a11y/src/tree/enhanced_mode_cache.rs` L1-35).
- Apple Vision OCR speed: `.fast` took about 0.25 s versus about 2 s for `.accurate` on Apple's WWDC19 sample (https://devstreaming-cdn.apple.com/videos/wwdc/2019/234rye7511ohnx5dmvl/234/234_text_recognition_in_vision_framework.pdf). screenpipe turns language correction off (`crates/screenpipe-screen/src/apple.rs` L181).

4. Cursor and the element under it (what the lead asked for)
- `AXUIElementCopyElementAtPosition(systemWide, x, y)` returns the UI element under the pointer: its role, value/text and frame. That is exact, and cheaper than OCR.
- screenpipe warns that concurrent calls to it can SIGABRT AppKit, so they run all AX queries one at a time behind a lock. They also cap every AX call at 1 s (0.1 s for metadata), because an AX read blocks the target app's main thread (`platform/macos.rs` L37-55).
- The cursor position itself is free: `NSEvent.mouseLocation`, or the CGEventTap they already run.

5. What Cluely, its clones, Highlight and Rewind actually do
- Cluely and its clones are much simpler than they look: a screenshot on a hotkey, then one LLM call.
- free-cluely (`electron/shortcuts.ts`) takes a screenshot on Cmd+H and keeps at most 5 (`ScreenshotHelper.ts` L12). It hides its own window before capturing, and the window uses `transparent`, `alwaysOnTop` and `setContentProtection(true)` (`WindowHelper.ts` L87-109).
- An open-interview-coder author who reverse-engineered Cluely says it is built on that one Electron call, `setContentProtection` (https://github.com/phulelouch/open-interview-coder).
- Lesson for miyagi: if the dim/spotlight overlay is not excluded from capture, miyagi will OCR its own pill and spotlight. Use `setContentProtection(true)` or exclude the app in ScreenCaptureKit.
- Highlight: its docs say it captures the "focused window" when you open the assistant and extracts text, so it is on-demand and scoped to one window. Whether it reads AX data or runs OCR isn't documented.
- Rewind/Limitless: no reliable public technical documentation. One user measured CPU going from about 15% to 30% with it running (https://numericcitizen.me/rewinding-30-days-of-my-experience-with-rewind-for-mac/). This is the cautionary example of continuous capture.

6. Privacy filters
- screenpipe redacts text with regexes before storing it: credit cards, SSNs, emails, formatted phone numbers (`crates/screenpipe-core/src/pii_removal.rs` L10-27). It also detects incognito windows from accessibility identifiers and window titles (`screenpipe-a11y/src/incognito/macos.rs`) and has app/window exclusion lists (`capture_exclusions.rs`).
- Recall runs an on-device classifier that drops a snapshot when it sees passwords, national IDs or card numbers (https://support.microsoft.com/en-us/windows/filtering-apps-websites-and-sensitive-information-in-recall-a4c28bee-e200-4a4a-b60d-c0522b404a5b).
- For a hackathon, regex redaction plus a short list of excluded apps (1Password, Keychain Access, Messages) is enough.

7. Batching VLM calls
None of these products sends every frame to a vision model. The pattern is: a cheap local text/AX representation always, and the model only at checkpoints (step-done check, typing pause, error text appears, user asks). When the model is called, send the focused-window crop plus a text diff, not the full screen. screenpipe sends only text and frame metadata downstream. Cluely sends one screenshot per hotkey.

RECOMMENDATIONS FOR MIYAGI
- Replace the 1 fps whole-screen OCR loop with event triggers. Capture on app/window focus change, a typing pause of 800-1500 ms, a click, a scroll stop, and a terminal content change, plus a 5 s visual-diff backstop and debounce. Start with a downscaled hash (about 480 px wide, not smaller) and skip the frame when it is unchanged. This should cut OCR calls by 5-10x and make step checks react in about 300 ms after a pause, not up to 1 s.
- Read the accessibility tree before OCR. Set `AXManualAccessibility=true` on VS Code's process once per minute, then read the focused editor's `AXValue`/selected text and the terminal's `AXTextArea`. Terminal.app and iTerm2 expose their buffer through AX. Fall back to Vision OCR (`.fast`, language correction off) only when AX text is under about 100 characters, and run it on the focused-window crop only.
- Add a cursor sense. Each tick (or on a CGEventTap mouse-move with debounce), get `NSEvent.mouseLocation`, call `AXUIElementCopyElementAtPosition` behind a single lock with a 0.1 s timeout, and record `{role, text, frame}`. If AX returns nothing, OCR about a 400x200 crop around the cursor. Pass "user is hovering X" to the coach. Use the AX `frame` directly as the spotlight rect, which is more precise than OCR's locate().
- Exclude miyagi's own overlay from capture. Use `setContentProtection(true)` on the Electron windows, or `excludingApplications` in ScreenCaptureKit, so the pill and dimming never get OCR'd or sent to the coach.
- Call Claude/Gemini only at checkpoints, with focused-window crop + AX text + recent diff, and with no other model calls in flight. Keep the deterministic step check local: a string or regex match on AX/OCR text, which costs 0 ms of model time.
- Before anything leaves the machine, run screenpipe's four PII regexes (card, SSN, email, phone) and skip capture for password-manager and Messages windows. This takes about 30 minutes and is worth mentioning in the demo pitch.
- Buildable in about 12 h: triggers + hash diff (2-3 h), the AX-first reader with OCR fallback including the Electron flag (3-4 h, a small Swift or pyobjc helper), cursor AX hit-test (1-2 h), overlay exclusion + PII (1 h).

---

## Report: tutor-ux

TOPIC: Real-time on-screen guidance UX: when to step in, how to point, how to confirm a step, how not to nag

1. WHEN PRODUCTS INTERVENE
Almost every product waits for the user to ask. The ones that step in on their own keep it subtle and tune how eager they are.
- Clicky (farzaa/clicky, MIT) is push-to-talk only. The user holds Ctrl+Option, and it screenshots every display, sorting the screen with the cursor first and labeling it "cursor is here" (leanring-buddy/CompanionScreenCaptureUtility.swift L38-108). Claude is told to point only when it helps, and to append `[POINT:none]` otherwise (CompanionManager.swift L561-576). https://github.com/farzaa/clicky
- Spotit uses hold-Ctrl+Option to ask. It "lights up where to click", and listings say it can also click for you. Its site does not say whether it detects that a step was completed. https://getspotit.com, https://www.producthunt.com/posts/spotit-3
- Ourguide only screenshots when the user asks for the next step. Moving forward is the user's job. https://hn.svelte.dev/item/46769422
- Copilot Vision Highlights: the user shares one app window and says "show me how". Copilot highlights where to click, and the user does the clicking. Highlights works in one app at a time and has an explicit Stop button. https://blogs.windows.com/windows-insider/2025/05/12/copilot-on-windows-windows-insiders-can-now-use-vision-with-2-apps-and-new-highlights-feature-with-1-app/
- Gemini Live has a "proactive audio" setting that lets the model decide not to respond when the input isn't relevant. This is built-in support for staying quiet. https://cloud.google.com/vertex-ai/generative-ai/docs/live-api/proactive-audio
- Copilot and Augment next-edit suggestions are the closest match to a tutor that speaks up unasked. In VS Code's long-distance next-edit work, the first model jumped too eagerly. The team retrained it to favor "no jump" and added RL penalties for badly timed jumps. Far-away suggestions were rejected more often. https://code.visualstudio.com/blogs/2026/02/26/long-distance-nes. Augment found its hover UI "deeply polarizing". Tuning it to interrupt less overshot and made it too passive. https://www.augmentcode.com/blog/next-edit-user-centric-design

2. HOW THEY POINT
- Clicky has a blue triangle cursor that follows the mouse with a spring. When it points, it flies along a quadratic bezier arc (arc height = min(0.2·dist, 80px)) at 60fps, and moving the mouse cancels the return flight (OverlayWindow.swift L412-554, L651). It also shows a short speech-bubble label and speaks the answer. To get coordinates it calls Claude's Computer Use tool on a screenshot downscaled to the nearest supported aspect ratio (1280x800 for 16:10). The code comments say this is far more accurate than asking the plain vision API for coordinates (ElementLocationDetector.swift L1-40).
- Pendo, WalkMe and Tango anchor a tooltip or highlight box on a DOM element and add a side panel listing the steps.
- VS Code's next-edit work puts a compact preview widget in empty space near the cursor (line ends, gaps between blocks) instead of moving the user's attention.
- Pattern: one target at a time, a label of three words or fewer, and an indicator for off-screen or other-monitor targets (Clicky's `:screenN`).

3. HOW THEY CONFIRM A STEP HAPPENED
- Web guide tools use events. Pendo has "Advance on Element Click/Hover" (https://support.pendo.io/hc/en-us/community/posts/5196016635291). WalkMe's step triggers are Click, Type, Hover, Delay and Refresh, plus "Wait For" rule conditions. Its own troubleshooting article names the click trigger as a common reason a flow stops (https://support.walkme.com/?p=54439, https://support.walkme.com/knowledge-base/smart-walk-thru-is-breaking/). Tango moves on when the highlighted box is clicked (https://help.tango.us/en/articles/7885279-what-is-guidance).
- Desktop AI tools (Clicky, Ourguide, Copilot Highlights) mostly don't verify. The user asks again.
- Lesson for miyagi: an event says the user did something, and the screen says whether it worked. Use both. A click or keystroke inside the target rectangle followed by an OCR change (new text in the terminal, the expected token in the editor) is much more reliable than either signal alone.

4. RESEARCH ON TIMING AND NAGGING
- Assistance dilemma: help cuts frustration and wasted time but can lead to shallow learning. Withholding it does the reverse (Koedinger & Aleven 2007). https://learnlab.org/research/wiki/index.php/Assistance_dilemma
- Razzaq & Heffernan (ITS 2010): students "learned reliably more with hints-on-demand than proactive hints" given after an error. The effect was strongest for students who ask for many hints. Murray & VanLehn (2006), cited in the same paper, found proactive help better for students who are floundering. https://web.cs.wpi.edu/~nth/pubs_and_grants/papers/2010/ITS/Razzaq%20Hints%20Is%20It%20Better%20to%20Give%20or%20Wait.pdf
- Help abuse: students click through to the final hint that states the answer. Aleven et al. measured hint abuse on 36% of actions in one geometry tutor unit, or 14% when rapid repeated requests count as one. https://learnlab.org/research/wiki/index.php/Help_abuse
- Interruption timing (Iqbal & Bailey): an interruption at a random moment can make people take up to 30% longer to resume and make up to twice the errors. Waiting until a breakpoint between subtasks lowers the cost, and coarser breakpoints lower it more. https://interruptions.net/literature/Iqbal-CHI06-p741-iqbal.pdf
- Horvitz's mixed-initiative principles: take the user's attention into account when timing help, match how much the system does to how sure it is, keep the cost of wrong guesses low, and make invoking and dismissing help cheap. https://erichorvitz.com/chi99horvitz.pdf
- Cursor signals: one study detected confusion from mouse-log features (33 features, SVM, F≈0.95, but in a clicking game; Pentel, PALE 2015). Long idle periods and erratic back-and-forth movement are the common markers. https://ceurspt.wikidata.dbis.rwth-aachen.de/Vol-1388/PALE2015-paper5.pdf
- Feedback timing: ManyClasses (38 classes) found no overall difference between immediate and delayed feedback. Low-knowledge learners lean toward immediate feedback. https://ifp.nyu.edu/2021/journal-article-abstracts/manyclasses-1-assessing-the-generalizable-effect-of-immediate-feedback-versus-delayed-feedback-across-many-college-classes/

5. SIX UX RULES FOR MIYAGI (pill + spotlight + coach card)
1. Quiet by default, with an escalating hint ladder. Level 0: the pill shows the step title and a progress dot. Level 1: a soft spotlight on the target rectangle. Level 2: a coach card with a conceptual hint. Level 3: the exact fix plus a "Do it for me" button. Each level appears only on request, or when a stuck signal fires. Rate-limit requests so the learner can't race to level 3.
2. Speak up only at breakpoints or when the learner is truly stuck. Breakpoints: a command just ran (the terminal prompt came back), a file was saved, a cell finished. Stuck signals: no progress for about 45-60 s, the same error OCR'd twice, or erratic or idle cursor movement. Never interrupt while the learner is typing (any keystroke in the last 2 s).
3. Point at one thing. The spotlight cut-out goes on the single target rectangle from locate(text), with a label of three words or fewer. If the target is off-screen or on another monitor, show an edge arrow instead of moving the spotlight. Fade the dim when the cursor enters the target so it doesn't block the click.
4. Confirm with an event plus the screen. A step counts as done when (a) a mouse or keyboard event lands in or near the target rectangle and (b) the next OCR frame shows the expected change. Show a brief green check on the pill, Duolingo style, then move straight to the next spotlight. If only one of the two signals fires, show "Looks done? Confirm" instead of asserting.
5. Use the cursor. Every frame, record what is under the mouse: the OCR word nearest the cursor, and the accessibility element if available via AXUIElementCopyElementAtPosition. Behaviors: (a) hold Ctrl+Option while hovering to get a one-line explanation of that thing. (b) "Wrong target" warning: if the cursor has rested over 600 ms on a clickable that matches a known wrong choice (the wrong file or run button, the wrong terminal), pulse an amber outline on the correct target. Never block the click.
6. Ask before acting, and make it easy to undo. "Do it for me" previews exactly what will be typed or clicked in the coach card, needs one click or ⏎ to confirm, then runs. Moving the mouse cancels it (as with Clicky's cancel-on-move). Always keep a visible Stop or Esc.

RECOMMENDATIONS FOR MIYAGI
- Build the hint ladder and breakpoint gating first, in about 2-3 hours in the Python engine. It is mostly a state machine: idle, stuck_timer, at_breakpoint, then the hint level. This feature makes the tutor feel smart instead of naggy, and it matches the hints-on-demand evidence.
- Add global input events for step confirmation, in about 2 hours: uiohook-napi in Electron or a Python CGEventTap. Pair each click or keystroke with the next OCR diff inside the step's expected rectangle. Fall back to "Confirm?" when only one signal fires.
- Get the cursor position every tick (Electron screen.getCursorScreenPoint()) and attach "cursor at (x,y), nearest OCR text = '...'" to every coach prompt, as Clicky does with its "cursor is here" label. Hover-to-explain via hotkey takes about 1 hour on top of that.
- Copy Clicky's pointing recipe: use a Computer Use-style screenshot sized to the display's aspect ratio when locate(text) OCR misses (icons, unlabeled buttons), and an animated arc to the target that cancels when the mouse moves. The code is MIT, so read OverlayWindow.swift L491-560 directly.
- Ship "Do it for me" only as previewed and confirmed: type the fix into the focused editor, or click the spotlighted rectangle. Keep it out of the default flow so the demo still shows teaching rather than doing.
- Cut for the hackathon: the ML confusion classifier (use idle time plus a repeated-error heuristic instead) and proactive voice. Text in the coach card is enough.

---

## Report: editor-deep

TOPIC: Understanding a VS Code / Jupyter session from outside, with nothing installed

Status: I verified everything below against source code (VS Code main, Electron, xterm.js). I did not run any of it live, because this shell does not have Accessibility permission (`AXIsProcessTrusted() == False`). The speeds are estimates, not measurements.

**1. The AX tree is the main source of truth, once you switch it on**
- Electron apps such as VS Code build no AX tree for web content until assistive tech asks for one. An outside app can force it by setting `AXManualAccessibility=true` on the app element. Electron handles this in `shell/browser/mac/electron_application.mm` (~L249-265): it turns on the complete AX mode and fires `OnAccessibilitySupportChanged()`. Docs: https://www.electronjs.org/docs/latest/tutorial/accessibility. Shipping apps do the same: nchudleigh/vimac `ViMac-Swift/Accessibility/AXManualAccessibilityActivator.swift`, and stablyai/orca `native/computer-use-macos/.../main.swift` L1621-1627, which falls back to `AXEnhancedUserInterface`.
- VS Code passes that event on to its windows (`src/vs/code/electron-main/app.ts` L557-558). With the default `editor.accessibilitySupport: auto`, the editor then counts as "screen reader optimized" (`platform/accessibility/browser/accessibilityService.ts` L145-147).
- **Catch:** VS Code then shows a sticky prompt, "Screen reader usage detected…" (`contrib/accessibility/browser/accessibilityStatus.ts` L53-66). Clicking **No** writes `editor.accessibilitySupport: "off"` to user settings. In that state the hidden editor text is cleared and never written again (`screenReaderContentSimple.ts` L46-47, L71). On the demo machine, click **Yes** or set `"editor.accessibilitySupport": "on"`. That is a settings change, not an install.
- What you get once it is on (Monaco, `editor/browser/controller/editContext/native/`):
  - The focused element is a `role=textbox` with roledescription "editor".
  - Its text holds up to `accessibilityPageSize` lines (default 500, `editorOptions.ts` L6145). Pages are aligned to multiples of 500 lines (`screenReaderUtils.ts` L40-47).
  - The text is the **live, unsaved buffer**. The 500-character trim only applies while support is "Unknown" (`screenReaderContentSimple.ts` L161-165).
  - `AXSelectedTextRange` gives the caret and the selection.
  - **Main finding:** that element sits exactly on the cursor line, with `top` = the cursor line's offset, `left` = contentLeft and `height` = lineHeight (`screenReaderSupport.ts` L131-157, L165-173). So its `AXPosition`/`AXSize` is the pixel rect of the current line, and `AXSize.height` is the line height. If the cursor is scrolled out of view, it moves to the top-left instead.
- The window's `AXDocument` gives the full path of the active file. VS Code calls `setRepresentedFilename(file.fsPath)` whenever the active editor changes (`workbench/electron-browser/window.ts` L476-480).
- The window `AXTitle` (or `kCGWindowName`) has a leading "●" when the file has unsaved changes. That tells you whether the copy on disk is out of date.
- Notebooks in VS Code: each cell is its own Monaco editor, so the same approach works for the focused cell. Cell outputs live in a webview; reaching them through AX is possible but I have not verified it.

**2. Comparison**

| Need | AX (on) | File on disk + AXDocument | git diff | `code -g` | OCR |
|---|---|---|---|---|---|
| (1) Lines being edited, text caret | Exact, unsaved buffer, est. 5-30 ms | Only after save, no caret | Changed hunks since a baseline, after save, ~20 ms | Cannot read anything | Approximate; the caret is invisible to OCR; ~240 ms |
| (2) Pixel rect of line N | Current line exact; line N ≈ `y + (N-cur)*h`. Breaks with folding, word wrap, inline widgets | n/a | n/a | Can scroll N into view first | Good: fuzzy-match the expected text, then use its rect |
| (3) Latest terminal output | VS Code terminal (xterm.js) exposes one element per visible row (`xterm.js src/browser/AccessibilityManager.ts` L68-73) | Log file if the script writes one: best | n/a | n/a | Fine for loss numbers via regex |

- `code -g file:line[:col]` and `-r` are **write-only**: they navigate the editor and report no state (https://code.visualstudio.com/docs/configure/command-line). This is the safest "show me" control: jump the user to the line, then spotlight it.
- Terminal.app: AppleScript `tell application "Terminal" to get history of selected tab of front window` returns the full scrollback (one-time Automation prompt). AX `AXTextArea.AXValue` also works.
- iTerm2: `contents of current session`.
- Browser JupyterLab: read the `.ipynb` on disk (only updated on autosave), or the Jupyter server REST API. The token comes from `jupyter server list --json`.

**3. pyobjc sketch**
```python
from ApplicationServices import *; from AppKit import NSWorkspace; import Quartz
def ax(e,a): err,v=AXUIElementCopyAttributeValue(e,a,None); return v if err==0 else None
IDS={"com.microsoft.VSCode"}
pid=next(a.processIdentifier() for a in NSWorkspace.sharedWorkspace().runningApplications() if a.bundleIdentifier() in IDS)
app=AXUIElementCreateApplication(pid)
AXUIElementSetAttributeValue(app,"AXManualAccessibility",True)   # once, then wait ~1-2 s
win=ax(app,"AXFocusedWindow"); path=ax(win,"AXDocument"); dirty=ax(win,"AXTitle").startswith("●")
ed=ax(app,"AXFocusedUIElement")                                   # the editor textbox
text=ax(ed,"AXValue")
_,sel=AXValueGetValue(ax(ed,"AXSelectedTextRange"),kAXValueCFRangeType,None)
_,pos=AXValueGetValue(ax(ed,"AXPosition"),kAXValueCGPointType,None)
_,sz =AXValueGetValue(ax(ed,"AXSize"),kAXValueCGSizeType,None)
cur_line=page_start+text[:sel.location].count("\n")   # page_start=1 for files under 500 lines
line_h=sz.height; rect=lambda n:(pos.x,pos.y+(n-cur_line)*line_h,sz.width,line_h)
m=Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))          # mouse, same top-left global coords
hover_line=cur_line+int((m.y-pos.y)//line_h)
_,under=AXUIElementCopyElementAtPosition(AXUIElementCreateSystemWide(),m.x,m.y,None)  # role/title under mouse
```
- Poll this at 5-10 Hz. You can also register `AXObserver` for `kAXFocusedUIElementChangedNotification` and `kAXSelectedTextChangedNotification` so updates arrive as events.
- For files over 500 lines, find `page_start` by matching the AX text against the disk file with difflib.
- Permissions: Accessibility is separate from Screen Recording. It is granted to whichever process is responsible for the engine (the Electron app, or Terminal in dev). AX permission is also needed for clicking and typing, so request it once.

RECOMMENDATIONS FOR MIYAGI
- **Make AX the main signal for VS Code.** Set `AXManualAccessibility` at startup and turn on `editor.accessibilitySupport: "on"` on the demo Mac, so nobody hits the "No" trap. Read file path, dirty flag, unsaved buffer, caret line and current-line rect from AX. Keep OCR as the cross-check and as the fallback when the AX value is empty.
- **Spotlight with this order:** AX current-line rect, then the offset formula for line N, then OCR fuzzy-match on the expected line text to confirm it. If line N is off screen, run `code -g path:N` first, wait about 300 ms, then re-read.
- **Mouse awareness:** use `CGEventGetLocation` plus `AXUIElementCopyElementAtPosition` for UI chrome (buttons, terminal rows, file tree). Inside the editor, map mouse y to a line with the AX anchor and line height. That gives "you're hovering line 42 (`loss = …`)" for free.
- **Check steps with an owned baseline:** watch the project folder for saves (FSEvents or `watchdog`). On each save, run `git --git-dir ~/.miyagi/shadow.git --work-tree <proj> diff -U0` against a snapshot taken at lesson start, so the user's own repo is never touched. Grade the hunks, not OCR text.
- **Training loss:** best is to have the lesson's `train.py` also append to `.miyagi/loss.log` and tail it. Next, read VS Code terminal rows via AX, or Terminal.app `history` via AppleScript. Last, OCR a crop of the terminal rect with a `loss[=:]\s*([\d.e+-]+)` regex.
- **Budget about 3-4 hours for the AX module.** Test early on the actual demo Mac in VS Code: no code here was run live.


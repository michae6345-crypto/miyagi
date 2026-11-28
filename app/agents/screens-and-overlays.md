# screens-and-overlays (plan)

**Status:** plan only, no code · **Owners:** Michael (engine, main process, display handling), Adrian (§4 gestures,
look, motion) · **Branch:** `claude/plan-screens-overlays` · **Asked by:** Michael, Nov 28

How miyagi's overlays (island, cards, spotlight / circle, lesson panel, player) should behave across real Mac screen
setups, how the taught app (VS Code first) should be laid out so pointing lands, and how learners can move and lock
overlays. Every "today" claim cites the code on `origin/main` (Nov 28). Things marked **verify on the Mac** were not
run here (no Electron run in this lane).

---

## 1. TL;DR

1. **The biggest bug is a display mismatch.** The overlay and the VS Code layout are pinned to the *primary* display, but
   the engine's screen reader captures *whichever display holds the frontmost window*. On a laptop + external setup with
   VS Code on the external display, the engine finds targets on a screen the overlay isn't on. Fix first: one
   "lesson display" shared by app and engine (§3.1).
2. **A display plug / unplug looks like the learner moved VS Code.** macOS moves the window, the engine's ownership check
   sees a new frame and stops managing the window for the rest of the lesson. The app never tells the engine that
   displays changed (§3.2).
3. **Layout recommendation:** keep miyagi's **managed zoom** (VS Code fills the work area beside the panel, same Space)
   as the default. Offer **native full screen** as a setting, not the default. Reasons in §4. Michael's instinct
   ("VS Code full screen") is met visually by managed zoom without the Space switch that caused the Nov 25 "back and
   forth".
4. **Don't fight the learner's window.** If they move or resize VS Code mid-lesson, **re-locate the targets** at once and
   keep going. Pause and ask only when the target can't be seen: a different display, minimized, covered, or too small.
5. **Movable overlays:** iOS Picture-in-Picture-style anchors (corners, edge middles, notch/top centre). Fling or drop,
   then a spring to the nearest anchor using the release velocity. Positions are saved per display as *anchor + nudge*
   in `prefs.json`. Double-click, menu or Settings resets them. A keyboard "move mode" is the alternative to dragging.
6. **Persistence bug to fix on the way:** the lesson panel's saved drag offset lives in `localStorage`, which a packaged
   app loses on every launch (random port origin) (§5.6).

---

## 2. How it works today (map)

| Piece | Where | What it does |
|---|---|---|
| Overlay display | `app/src/main/index.ts:149` `displayNow()` | Always `screen.getPrimaryDisplay()`. Comment: "v1: the engine watches the PRIMARY display only". |
| Overlay window | `app/src/main/platform.ts:108-140` `overlayWindowOptions`, `:430` `overlayBounds` | A transparent, non-focusable NSPanel covering the display's full `bounds` (menu bar included). |
| Floats over everything | `platform.ts:291` `followSpaces`, `:309` `raise` | `setVisibleOnAllWorkspaces(true, {visibleOnFullScreen: true})` + `setAlwaysOnTop('screen-saver')`. So the overlay already shows over full-screen Spaces and on every desktop. |
| Display events | `platform.ts:337-412` `trackOverlayLifecycle` | On `display-added/removed/metrics-changed`: fade to opacity 0, refit after 150 ms (`OVERLAY_RESTORE_MS`), re-raise. Hides on lock-screen. Re-raises on `NSWorkspaceActiveSpaceDidChange` (`:404`). |
| Work-area-only changes | `platform.ts:425` `workAreaOnly`, `index.ts:784-810` | Menu bar / Dock show-hide (and full-screen Space transitions) don't fade or collapse anything; the layout is re-sent 600 ms after the burst, only if it really changed. |
| Refit | `index.ts:761-770` `applyDisplay` | Re-applies primary bounds to the overlay and launcher, recomputes `pillTop`, sends `layout`. |
| Island top | `index.ts:131-139` `belowTopNow`, `app/src/main/notch.ts` | Island sits under the menu bar (or in the notch band). A secondary display with no menu bar gets the very top. |
| Layout sent to renderers | `index.ts:330-337` `layoutFor` | `{notch, origin, width, height, pillTop, displayId, scaleFactor, workArea (window-local)}`. |
| Click-through | `app/src/main/features/overlay-raise.ts:1-30, 105-140` | Overlay ignores the mouse; main polls the cursor every 25 ms and grabs it over reported UI rects. "Away" mode (another app in front) makes it fully click-through. |
| App windows | `app/src/main/appWindows.ts:51` | Library / Settings / Onboarding open on the display under the **cursor**: a different rule from the overlay's. |
| Player | `app/src/main/features/player.ts:68, 101` | Restores saved bounds if they still land on *any* display, else docks on the **primary** work area. |
| Settings window | `app/src/main/features/settings.ts:156` | Copies the overlay's bounds after a metrics change. |
| Lesson panel drag | `app/src/renderer/src/features/drawer/v2/drag.ts`, `LessonPanel.tsx:180` | Panel moves by its header; offset from its dock, clamped to the work area, double-click goes home. Saved in `localStorage` (`drag.ts:83`). |
| Card placement | `app/src/renderer/src/core/islandPlace.ts:1-25` | An open card steps off the spotlight hole / avoid rects (cost function), then holds its spot. |
| Island place pref | `app/src/common/prefs.ts:47` | `island.place`: notch or below the menu bar. |
| Reduced motion | `core/Island.tsx:94`, `core/ui/motion.ts:14-121`, `styles.css:482` | Honoured for the island and app UI. |
| VS Code layout policy | `server/workspace/layout.py:19-29, 156, 206` | Pure policy. Full screen = learner's, leave it. Moved by learner = theirs, leave it. Otherwise fill the visible frame left of the panel, under the notch / menu band (+44 pt island row on non-notch Macs). Video lessons: left 60%. |
| Lesson screen (engine) | `server/workspace/editor.py:590-633` `lesson_screen` | `NSScreen.screens()[0]` (primary), cross-checked against Quartz because NSScreen goes stale without a run loop. |
| Open layout | `editor.py:645-692` `make_fullscreen` | Default: managed zoom in the current Space. `MIYAGI_FULLSCREEN=native` (`:57-59`) → `AXFullScreen=true`. |
| Follow-ups | `editor.py:694-772` `fit_beside_drawer` | Re-plans only when the panel moved and the window is still where miyagi put it. |
| Ownership | `editor.py:475-495` `_ownership` | Frame changed since miyagi set it → released for the rest of the lesson. |
| Screen reader display | `server/screen/macos.py:102-119` `target_display_id`, `server/screen/reader.py:827` | Captures the display holding the **frontmost window**, else the one under the cursor, else main. |
| Capture scale | `server/screen/sck.py:152-155` | Pixel width from the display mode ÷ point width, so non-integer scaled modes ("More Space") are handled. |

---

## 3. Screen variety

Legend: **Today** = what the code does now. **Should** = target behaviour. **Detect** = how.

### 3.1 The rule everything else hangs on: one *lesson display*

Today, three different rules pick a display:

- the overlay and the VS Code layout use the **primary** display;
- the reader uses the display with the **frontmost window**;
- app windows use the display under the **cursor**.

They agree on a single-display Mac and can disagree on any multi-display setup.

**Should:** main owns one `lessonDisplay`, chosen at lesson start:

1. the display holding most of the lesson's VS Code window, if it is already open;
2. else the display the learner launched the lesson from (cursor);
3. else primary.

Main moves the overlay, player and panel there and sends the engine a new `display.state {id, bounds, workArea,
scaleFactor, safeTop, epoch}` (new wire event). The engine's `lesson_screen()` and the reader's capture use that id
instead of `CGMainDisplayID` / `target_display_id` while a lesson runs. Outside a lesson the reader can keep its
frontmost-window rule (circle to ask).

**Detect:** Electron `screen.getDisplayMatching(vscodeFrame)` (main gets the frame from the engine's `editor` report or
its own AX read); `display.id` is the CGDirectDisplayID the engine uses, so ids match across processes.

### 3.2 Per setup

| Setup | Today | Should | Detect |
|---|---|---|---|
| **Retina laptop, default scaling** (e.g. 1470×956 pt @2x) | Works; this is the tested case. | No change. | `display.scaleFactor === 2`, `internal: true`. |
| **"More Space" scaled modes** (1710×1112, 1800×1169 pt) | Overlay and layout work in points; capture uses the real backing width (`sck.py:155`). UI text is smaller, so OCR targets are smaller and circles get tight. | Minimum hit and circle size in **points** (≥ 28 pt), rings never thinner than 2 pt. OCR confidence threshold reviewed for small text. Panel width stays 360 pt but should drop to ~320 on screens under 1300 pt wide. | `display.size` (points) vs `display.scaleFactor`; small text = `size.width ≥ 1700` on an internal display. |
| **"Larger Text" scaled modes** (1024×640 … 1280×800 pt) | `layout.py` keeps `MIN_W 560`; on 1024 pt wide the 360 panel + 16 gap leaves ~630 pt for VS Code: cramped. | Under ~1200 pt wide: panel collapses to the Mini pill by default (cards come from the island), VS Code takes the full work area. | `workArea.width < 1200`. |
| **Non-Retina** (1080p external, `scaleFactor 1`) | Overlay fine. Capture is 1×, so OCR has half the pixels: weaker matching on small UI text. | Engine raises its capture upscale for OCR on `scale == 1` (reader concern), and the overlay draws 1 px hairlines snapped to whole pixels (no blurry half-pixel rings). | `scaleFactor === 1`. |
| **4K at "looks like 2560×1440"** | Electron reports `scaleFactor 2`; the backing store is downsampled by macOS. Fine. | No change. | — |
| **Notch MacBook** | Island lives in the notch band (`notch.ts`, `belowTopNow`); editor top under `safe_top` (`layout.py:156`). Good. | Keep. | `safeAreaInsets.top > 0` (engine), notch helper (app). |
| **No-notch Mac** | Island hangs under the menu bar; editor reserves `PILL_CLEARANCE` 44 pt. Good. | Keep. | `safe_top == 0`. |
| **External set as main display** (laptop open, notch on the *secondary*) | Overlay goes to the external (primary). Island is top-centre under the menu bar there. VS Code is moved to the external too (`lesson_screen` = primary), even if the learner keeps it on the laptop. | Lesson display rule (§3.1): follow VS Code. If VS Code is on the laptop, the island uses the laptop's notch. | `display.internal`, `primary.id !== internal.id`. |
| **Clamshell** (lid closed, external only) | Single display; same as non-notch. Good. | Keep. | `getAllDisplays().length === 1 && !internal`. |
| **Laptop + external, side by side** (x > 0 or x < 0) | Overlay on primary only. Reader may capture the other display → circles for a target the overlay can't reach (rect outside its window, drawn off-screen or clamped). **Likely bug, verify on the Mac.** | §3.1. Engine rects stay in global points. The renderer drops (and logs) any rect outside the overlay's display instead of drawing it. | `display.bounds.x < 0` etc. Global coords are top-left of primary, so negative x/y are normal. |
| **External above the laptop** (y < 0) | Same as above. `pillTop` math is per display, fine. | Same. | `bounds.y < 0`. |
| **Mixed DPI** (Retina laptop + 1× external) | The overlay is on one display, so no cross-DPI window. If the lesson display is the 1× one, see non-Retina. | Overlay never spans displays: one overlay window per lesson display. | `scaleFactor` differs between displays. |
| **Dock left / right** | `workArea` and `NSScreen.visibleFrame` exclude it; `layout.py` and `core/dock.ts panelRect` use the visible frame, so the panel sits inside the Dock. Good. | Keep. Cards placed by `islandPlace` already stay in the work area; check the player's `dockRect` with the Dock on the right. | `workArea.x > bounds.x` (left) or `workArea.x + width < bounds.x + width` (right). |
| **Dock bottom, auto-hide** | Visible frame takes nothing, editor fills to the bottom, Dock pops over it on hover. Work-area-only events are ignored (`platform.ts:425`). Good. | Keep. Never put a step card or the shortcut row in the bottom 6 pt (the Dock trigger zone). | `workArea.height === bounds.height - menuBar`. |
| **Menu bar auto-hide** | Island keeps a 24 pt band (`MENU_BAND`, `layout.py`). On a notch Mac the menu bar slides over the island area on hover. | Keep. When the menu bar is revealed (`workArea.y` grows), fade the island out (200 ms) instead of drawing over the menu; back when it hides. | `display-metrics-changed` with `['workArea']`, `workArea.y` change. |
| **Stage Manager** | Not handled anywhere (no reference in the code). The strip on the left isn't excluded from `visibleFrame`. When miyagi zooms VS Code over the strip, macOS hides the strip; the strip comes back when VS Code is un-zoomed. miyagi's own panels are `type: 'panel'` at screen-saver level and don't join stages (**verify on the Mac**). | Accept the strip hiding. With Stage Manager on, don't zoom: keep VS Code's own frame and narrow it beside the panel (`fit_beside_drawer`'s "narrow" path). Zooming over the strip feels like miyagi took over the desktop. | `defaults read com.apple.WindowManager GloballyEnabled` (engine, once per lesson). No Electron API. |
| **Native full-screen Space** (VS Code full screen) | Overlay follows (`visibleOnFullScreen`). Policy leaves the window alone. The panel and player float over the right of VS Code's content. | See §4. When the learner (not miyagi) put VS Code in full screen, keep the panel collapsed to Mini by default, so it doesn't cover the editor's top-right buttons. | AX `AXFullScreen` (engine, `editor.py:374`). |
| **Mission Control / App Exposé** | The overlay is at screen-saver level on all Spaces. During Mission Control the circles can float over the shrunken window grid at stale positions (**verify on the Mac**). | Hide target-bound layers (spotlight, circle, buddy ink) while Mission Control is open. The island stays. | No public event. Heuristic in main: a `Dock`-owned full-display window at layer ≥ 20 in `CGWindowListCopyWindowInfo` (engine already lists windows, `macos.list_windows`). Low priority. |
| **Multiple Spaces (desktops)** | The overlay shows on every Space. If the learner swipes to a Space without VS Code, the spotlight / circle stay at VS Code's old spot. "Away" mode (`overlay-raise.ts`, A8) makes it click-through after a few seconds of another app in front, but the drawing remains. | When the lesson window isn't on screen (not in the on-screen window list), hide target-bound layers and show the pill line "Back to VS Code" (click: activate it). | `NSWorkspaceActiveSpaceDidChange` (already subscribed, `platform.ts:404`) → ask the engine whether the lesson window is on screen (`kCGWindowListOptionOnScreenOnly`). |
| **Plug / unplug mid-lesson** | Overlay fades and refits to primary (good). The island collapses. Engine isn't told. macOS moves VS Code; `_ownership` sees a new frame and **releases the window as if the learner moved it** (`editor.py:490-494`), so it is never re-laid out. Panel offset is clamped to the new work area (good). Player bounds restored only if still visible (good). | App sends `display.state` with a bumped `epoch`. The engine treats a frame change within ~2 s of an epoch bump as the system's move: re-claim and re-plan once. Lesson display re-picked by §3.1. If the lesson display went away, pause the step with "Your screen changed. Continue on this screen?" | Electron `display-added/removed`, `display-metrics-changed` with anything other than `workArea`. |
| **Resolution change mid-lesson** | Same as plug: fade, refit. The engine's NSScreen can be stale; `lesson_screen` already cross-checks Quartz (`editor.py:617-624`). | Same epoch rule. | `display-metrics-changed` with `bounds` / `scaleFactor`. |
| **`pillTop` after display change** | Recomputed in `applyDisplay`; launch-ease's core request 2 (`agents/launch-ease.md`) asks to re-run it live. Now done via `resendLayout` / `belowTopNow`. | Keep. | — |

---

## 4. Laying out the taught app (VS Code first)

### 4.1 Options

| | Native full screen (own Space) | **Managed zoom** (today's default) | Tiled split (VS Code + miyagi column) |
|---|---|---|---|
| What | `AXFullScreen = true` (`MIYAGI_FULLSCREEN=native`) | VS Code fills the work area left of the panel, same Space (`layout.py plan`) | Same as managed zoom, but the panel is a real column, never over code |
| Overlay joins it? | Yes, already: `followSpaces` + `visibleOnFullScreen` (`platform.ts:291`) | Nothing to join | Nothing to join |
| Start cost | ~0.7 s Space animation. The overlay fades on the transition (the Nov 25 MacBook Neo "back and forth", now damped by `workAreaOnly`). | One frame set, instant | Instant |
| Room | Most: no menu bar, no Dock. But the panel then sits *over* the code's right edge (minimap, Run ▷, top-right buttons). | Menu bar and Dock stay; panel has its own column | Same as zoom |
| Pointing stability | Very stable: the window can't be dragged | Stable until the learner drags it | Stable until the learner drags it |
| Other apps (browser, Terminal, Finder) | Leave the Space; overlay follows to every Space, so targets go stale (§3.2 Spaces) | One swipe-free ⌘Tab; overlay stays valid | Same |
| Video lessons | Player has to float over VS Code | Left 60% / right column (`common/screenLayout.ts`) | Same |
| Undo at lesson end | Exit full screen (another Space animation) | `restore_frames` back to the learner's frame | Same |
| Learner's own full screen | — | Left alone (`layout.py` rule 1) | Left alone |

### 4.2 Recommendation

**Default: managed zoom.** It is what `layout.py` already does, it looks full screen (VS Code edge to edge beside the
panel, under the notch, down to the Dock), it never switches Spaces, and it leaves the panel its own column so it
never covers code. Native full screen's real benefit (the learner can't move the window) is better served by the soft
lock below.

**Offer native full screen as a setting:** Settings > Lessons > "Open lessons in full screen". It suits learners who
like a distraction-free Space. In that mode the lesson panel starts collapsed (Mini pill + cards), and cards avoid the
top-right 200×60 pt of VS Code (Run ▷, kernel picker). The engine already supports it (`NATIVE_FULLSCREEN`). Only the
setting and the app-side panel default are new.

**Not a tiled split as a separate mode:** managed zoom *is* the split when the panel is docked. The only difference
is whether the panel may overlap code. Keep it docked by default.

### 4.3 "Screen lock": keeping pointing accurate

We can't truly lock another app's window, and snapping it back after the learner moves it would feel hostile. Instead:

1. **Watch the lesson window during a lesson.** The engine registers an `AXObserver` for `kAXMovedNotification`,
   `kAXResizedNotification`, `kAXWindowMiniaturizedNotification` and `kAXUIElementDestroyedNotification` on the lesson
   window. Fallback: a 500 ms frame poll while a step has a target. Today `_ownership` only checks on follow-ups.
2. **On move / resize (window still on the lesson display, still big enough):** re-locate silently. Clear the
   current circle at once (no stale ring for even one frame), re-read the target (AX first, OCR fallback) once the
   frame has been still for 250 ms, draw again. No dialog. Mark the window as the learner's (`_release`), as today.
3. **Pause and ask** (pill line, never a modal) only when the target can't be shown:
   - moved to another display → "VS Code moved to the other screen. **Follow it** · Put it back". Follow re-picks the
     lesson display (§3.1); Put it back re-plans the layout;
   - minimized or hidden → "VS Code is minimized. **Show it**";
   - smaller than `MIN_W×MIN_H` (560×400) or target scrolled out of view → step stays; the card says "Make VS Code
     bigger to see this" with **Fit it** (one click re-plans);
   - another window covers the target (on-screen window list z-order) → "Something's covering the spot. **Bring VS
     Code forward**".
4. **A "Put it back" everywhere:** the pill's right-click menu gets "Re-arrange windows" (re-claim + re-plan), the
   same as the engine's first layout.

---

## 5. Movable overlays that lock

Scope: the **island** (pill + cards born from it), the **lesson panel** (already movable), the **player** (a normal
window, already movable). The spotlight / circle are never movable: they mark the target.

### 5.1 Anchors (snap targets)

Per display, in work-area points:

| Anchor | Island | Panel | Notes |
|---|---|---|---|
| `notch` / `top-centre` | home | – | Notch on notch Macs, under the menu bar otherwise (today's spot) |
| `top-left`, `top-right` | yes | yes | 16 pt inset from the work area |
| `bottom-left`, `bottom-right` | yes | yes | 16 pt above the Dock / work area bottom; never in the bottom 6 pt |
| `left-middle`, `right-middle` | yes | `right` = home | Panel home is right, full height |
| `free` | no | yes (today's offset) | The panel keeps free placement plus magnetic edges |

Cards always open from the island's current anchor and grow *into the screen* (a bottom-right island grows up and
left). `islandPlace`'s avoid logic still runs, from the anchored spot.

### 5.2 Gestures

- **Grab:** press and hold 150 ms on the pill (or on a card's header) **or** drag past `DRAG_SLOP` (4 pt, `drag.ts`)
  → the item lifts: scale 1.03, the existing open shadow (`NOTCH_SHADOW`), the cursor becomes a closed hand. The overlay
  holds the mouse with a lease (`index.ts:345 leaseInteractive`) so the grab survives the 25 ms hit poll.
- **While dragging:** 1:1 with the pointer, no lag. The anchors fade in as 8 pt dots at 40 % opacity; the nearest one
  grows to a soft 44 pt ring.
- **Release:** project the release velocity (iOS PiP: `projected = pos + v * 0.2 s`) and spring to the anchor nearest
  the projected point, so a short flick toward a corner lands there. Spring: the app's one spring from
  `core/theme.ts` (`{stiffness 420, damping 34, mass 0.9}`, app/CLAUDE.md), transform only, initial velocity = release
  velocity. (The notch shape has its own near-critically damped springs, `islandRest.ts:12`; leaving the notch can use
  `NOTCH_SPRING.close` for the first frames so the island doesn't wobble out of it. Adrian's call.)
- **Locked state:** after landing, a small pin glyph shows at the item's edge for 1.2 s then fades; the item no longer
  follows layout defaults (it stays put across lessons). The right-click menu shows "Locked here ✓".
- **Unlock / reset:** double-click the pill or panel header (the panel already does this) → spring home. Right-click
  menu: "Move…" (keyboard mode), "Reset position". Settings > General: "Reset overlay positions" (all displays).
- **Clicks stay clicks:** a press with < 4 pt of travel is a click (`dragClickGuard`, `drag.ts`), so tapping the pill
  still opens it.

### 5.3 Never cover the target

A locked item keeps its anchor *unless* it overlaps the current spotlight hole / circle (plus `CARD_GAP`). Then it
slides to the next free anchor clockwise for that step only, leaving a 1 pt dashed outline at home, and springs back
when the step ends. Same cost function as `islandPlace` (`HOLE_COST` dominates), so there's one rule, not two.

### 5.4 Per-display memory

- Key: a display fingerprint, `internal|external` + `size` (points) + `label` (Electron `display.label`). Not `id`
  alone: CGDirectDisplayIDs can change after a reconnect.
- Value: `{ anchor, nudge: {dx, dy} }`. A position is anchor + small offset, never absolute pixels, so a resolution
  change keeps "bottom-right" bottom-right.
- An unknown display gets defaults (island at notch / top-centre, panel right).
- Stored in `prefs.json` via main (`common/prefs.ts`, a new `overlay.positions` map, sanitized like `island`).

### 5.5 Accessibility and keyboard

- **Reduced motion** (`useReducedMotion`, already used in `Island.tsx:94`): no lift scale, no spring; the item
  cross-fades to its anchor in 120 ms. Anchor dots appear without growing.
- **Keyboard move mode:** "Move…" from the right-click menu or Settings, or a global chord (proposal ⌃⌥⌘M, to be
  checked against `common/shortcuts.ts`; it is registered only while move mode can start, not all the time).
  - Arrows jump between anchors (spring or cross-fade).
  - ⇧ + arrows nudge 8 pt.
  - Return locks.
  - Esc cancels back to where it was.
  - 0 resets.
  - The overlay takes keys the same way the launcher does (`holdKeyboard` without activating miyagi).
- **VoiceOver:** while in move mode, each anchor is a button ("Move miyagi to bottom right"); the result is announced
  ("miyagi locked at bottom right").
- Targets ≥ 28 pt; the grab area is the whole pill.

### 5.6 Fix on the way: panel offset persistence

`drag.ts:83` saves the panel offset in `localStorage`. The packaged renderer is served from
`http://127.0.0.1:<random port>` (`main/serve.ts:86`, `listen(0)`), so its origin, and its storage, changes on every
launch. The overlay-gate lane found the same for tips (`agents/overlay-gate.md`, follow-ups). Move the offset into
`prefs.json` as part of §5.4. The panel's position then survives restarts as promised.

---

## 6. Test matrix

### 6.1 Display presets (one list, shared by both test suites)

Add `shared/display-cases.json`, next to `shared/layout-cases.json` (which both suites already check the video layout
against):

| Preset | bounds (pt) | scale | notch (safe_top) | Dock | Extra |
|---|---|---|---|---|---|
| `mba13-default` | 1470×956 | 2 | 32 | bottom | — |
| `mbp14-more-space` | 1800×1169 | 2 | 38 | bottom | small text |
| `mbp16-larger-text` | 1312×848 | 2 | 32 | bottom | narrow → Mini panel |
| `intel-mbp13` | 1440×900 | 2 | 0 | bottom | menu bar 24 |
| `smallest` | 1024×640 | 2 | 0 | bottom | — |
| `ext-1080p` | 1920×1080 | 1 | 0 | bottom | non-Retina |
| `ext-ultrawide` | 3440×1440 | 1 | 0 | left | Dock left |
| `dock-right-autohide-menu` | 1470×956 | 2 | 32 | right | menu bar hidden |
| `pair-right` | laptop 1470×956 @0,0 + ext 2560×1440 @1470,-200 | 2/2 | 32/0 | bottom | VS Code on ext |
| `pair-above` | laptop @0,0 + ext 1920×1080 @-225,-1080 | 2/1 | 32/0 | bottom | negative y |
| `ext-primary` | ext 2560×1440 @0,0 + laptop 1470×956 @-1470,300 | 2/2 | 0/32 | bottom | notch on secondary |
| `clamshell` | 2560×1440 | 2 | 0 | bottom | — |

### 6.2 Layers

| Layer | What | How | Cost |
|---|---|---|---|
| Engine policy | `layout.plan`, `pick_display`, lesson-display choice, epoch re-claim | pytest over `display-cases.json` (pure functions, no AppKit) | light |
| Main | `trackOverlayLifecycle`, lesson display pick, `display.state` sends, fingerprint keys | node test with a **fake `screen`**: an EventEmitter with `getAllDisplays / getPrimaryDisplay / getDisplayMatching / getCursorScreenPoint`, loaded from the presets. Extends `test/overlayLifecycle.test.ts`, which already fakes the emitters. | light |
| Renderer | anchor math, velocity projection, clamp, avoid-target slide, prefs round-trip | pure tests like `test/panelDrag.test.ts` | light |
| Stage (visual) | island / panel / cards at each preset, anchors, move mode, reduced motion, dark + light | Playwright (headless, `~/miyagi/tools/playwright`) against `npm run dev:web` with `?size=WxH` (exists) plus new `?notch=0\|32&dock=left\|right\|bottom\|hidden&menubar=hidden&scale=1\|2`. One dev server, one headless browser, shots into `app/agents/shots/screens/`. `emulateMedia({reducedMotion:'reduce'})` for the reduced-motion pass. | one server + one browser |
| Mac checklist (manual, Michael) | Spaces, full screen, Mission Control, Stage Manager, plug / unplug, a real external display | Short scripted checklist in `SHIP.md` style; run on the installed app once per phase, never by an agent | Michael's time |

Things the stage can't simulate (Spaces, Mission Control, Stage Manager, real AX moves) stay on the Mac checklist. Don't
fake them in tests.

---

## 7. Phased rollout

| Phase | What | Owner | Rough effort |
|---|---|---|---|
| **P0: correctness** | (a) Lesson display (§3.1): main picks it, sends `display.state`; engine capture + `lesson_screen` use its id during lessons. (b) Epoch re-claim on display change (§3.2 plug / unplug). (c) Renderer drops rects outside its display, with a log line. (d) Panel offset → `prefs.json` (§5.6). Fake-`screen` tests + pytest presets. | Michael | 2–3 days |
| **P1: window watch** | AX observer / poll on the lesson window; silent re-locate; the pause-and-ask pill lines (§4.3); "Re-arrange windows" menu item; Spaces: hide target layers off the lesson Space; menu-bar-reveal fade. | Michael (engine + main), Adrian (pill copy) | 3–4 days |
| **P2: movable island** | Anchors, drag + fling + spring, lock state, reset, per-display memory in prefs, avoid-target slide, reduced motion, keyboard move mode, VoiceOver labels. Panel gets anchors + magnetic edges on top of its free drag. | Adrian (design, motion), Michael (main lease, prefs) | 4–6 days |
| **P3: modes and edges** | Settings toggle for native full screen + Mini-panel default there; small-screen Mini default (< 1200 pt); Stage Manager "narrow, don't zoom"; Mission Control hide heuristic; non-Retina OCR upscale. | split | 3–4 days |

Ship P0 alone first: it fixes wrong pointing on every multi-display Mac and adds no new UI.

---

## 8. Open decisions for Michael

1. **Default layout:** managed zoom (recommended) or native full screen? Native stays available as a setting either way.
2. **Lesson display:** follow VS Code's display (recommended) or keep "always primary" and move VS Code there (today)?
3. **When the learner moves VS Code:** silently re-locate (recommended) or pause every time?
4. **Island leaves the notch:** allow dragging the island to corners on notch Macs (recommended, notch stays home), or
   keep it notch-only and make just the cards and panel movable?
5. **Move-mode shortcut:** ⌃⌥⌘M, or menu-only (no new global shortcut)?
6. **Positions stored per display** (recommended) or one global position?
7. **Mission Control / Stage Manager work (P3):** worth doing before beta, or wait for testers' reports?

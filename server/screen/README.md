# server/screen (E6): the whole-screen reader

Watches the primary display during a lesson, OCRs it on-device with Apple Vision, and gives the
rest of the engine text + positions in **screen points (top-left origin)**, the same space as the
`spotlight` event and Electron's `screen` API.

```python
from server.screen import get_reader, screen_contains
reader = get_reader().start()                 # background thread; capture ~every 2s, OCR only on change
reader.set_overlay_bounds(msg["rects"])       # forward the app's `overlay.bounds`; text under our UI is ignored
obs = reader.latest()                         # ScreenObservation{t, app, windows[{app,title,rect}], blocks[{text,rect,confidence,app,window}]}
unsub = reader.subscribe(cb)                  # cb(obs) per new frame; async def cb is scheduled on the running loop
res = reader.locate_match("def pde_residual", app="Code")   # -> LocateResult{rect, app, matched, score} | None
rect = reader.locate("def pde_residual")      # -> Rect | None  (rect.to_dict() == {"x","y","w","h"})
screen_contains(obs, r"u_t\s*\+\s*beta", app="Code")        # for screen_contains / screen_absent checks
evaluate_step(step, ctx, screen=obs.lines_by_app())          # E3: pass whole rows, not raw blocks
m = reader.watch_metrics(lesson_id, {"loss": check["metric_pattern"]}, on_metric, app=None,
                         on_restart=lambda run_id: ...)     # on_metric(name, step, value); m.reset() on step change
answer = await reader.describe("Is this loss curve converging?", region=None)  # Claude Opus 5.5, rate-limited
res = await reader.where("the Run button")            # Claude Haiku 5.5 picks among numbered OCR lines -> exact rect
reader.poke()                                 # capture now (e.g. right after a run ended)
```

- **app names** are window owner names (`Code`, `Terminal`, `iTerm2`, `Google Chrome`…); matching is
  case-insensitive with aliases (`vscode`, `VS Code` → `Code`).
- **locate** accepts a substring, a regex, or a multi-line snippet; it is whitespace-insensitive, fuzzy
  (rapidfuzz) for OCR noise, handles long lines cut off by a narrow pane, drops editor line numbers from
  the rect, and unions matching consecutive lines. Pad is 6pt.
- **`obs.lines_by_app()`** → `{app: [line, ...]}`: Vision splits a terminal row like
  `epoch 2500 | loss 2.5e-01` into 3 blocks, so regexes over raw blocks miss it. Give the evaluator this.
- **metrics**: each OCR row is parsed with E3's shared `server.checks.extract_metrics` (local fallback
  with the same contract until PR #3 is on main), so the evaluator and the reader agree. New rows are parsed each frame, de-duplicated by step. If the learner re-runs
  training (steps repeat with different values), a restart is detected: `run_id` becomes
  `screen-<lesson>-r2` and `on_restart(run_id)` fires, so curves don't mix runs. Points go to Tiger Data
  `training_metrics` (`run_id = "screen-<lesson>"`) when `TIGER_DATABASE_URL` is a real URL; otherwise
  it logs once and carries on.
- **env**: loads `TUT_ENV` (default `/Users/tripi/sand hacks/sandhacks-tutor/.env`).
  `ANTHROPIC_API_KEY` for describe/where (Claude only: the screen is never sent to Gemini),
  `TUT_SCREEN_COACH_MODEL` / `TUT_SCREEN_QUICK_MODEL` (defaults `claude-opus-5-5` / `claude-haiku-5-5`), `TUT_SCREEN_FIXTURE=path.png` to
  replay a saved screenshot instead of the live screen.
- **permission**: the app running the engine needs *System Settings › Privacy & Security › Screen &
  System Audio Recording*. Without it capture raises `ScreenPermissionError` (see `reader.status` / `on_error`);
  fixture PNGs are used only when asked for (`TUT_SCREEN_FIXTURE`, `--image`) or under `DEMO=1`.
- **perf** (M5 Pro, 3456×2234 Retina, accurate mode, language correction off): capture ~17 ms;
  OCR ~100–220 ms per frame warm depending on how much text is on screen, ~250–350 ms on the first
  frame (Vision warm-up). Static screens aren't re-OCR'd.

## Debug CLI
```bash
python -m server.screen watch [--app Terminal] [--json]      # frontmost app + OCR blocks per frame
python -m server.screen locate "def pde_residual" --out locate.png [--all]   # rect + PNG with it drawn
python -m server.screen metrics 'epoch\s+(?P<step>\d+).*?loss\s+(?P<value>[0-9.eE+-]+)'
python -m server.screen bench -n 8                           # capture + OCR latency
python -m server.screen describe "what is on screen?"           # Claude Opus 5.5
python -m server.screen where "the Run button"                   # Claude Haiku 5.5, set-of-mark
python -m server.screen fixture NAME --apps Code Terminal --titles pinn   # compose a fixture from only those windows
python -m server.screen --image server/screen/fixtures/vscode_terminal_flat.png locate "beta * u_x"
```

## Tests
`pytest server/screen/tests`: pure logic runs anywhere; `test_fixtures.py` runs real Vision OCR on
the two fixture screenshots (VS Code + Terminal, flat loss at β=30 vs. dropping loss), macOS only.

## AX, cursor, events (PR "screen: ax + cursor + events")
- **AX (`ax.py`)**: exact VS Code/Terminal state. Needs **Accessibility** for the app that runs the engine,
  and in VS Code `"editor.accessibilitySupport": "on"`. `reader.ax_reader.latest()` gives an `AXSnapshot`:
  `editor` (buffer page, caret, `caret_line`, `line_rect`, `rect_for_line(n)`, `line_at_y(y)`),
  `document`, `dirty`, `terminal_lines`, and `under_mouse`. AX text of at least 100 chars is merged into `obs.text()`/`lines_by_app()`.
- **Cursor**: `obs.cursor`, `obs.under_cursor`, `reader.cursor_context()` →
  `{x, y, app, window, ocr_line, ocr_rect, ax, caret_line, editor_line, editor_line_text, editor_line_rect}`.
- **Triggers**: click / typing_pause / scroll_stop / app_switch / AX changes → capture (>= 1.5 s apart,
  hash-gated OCR); `obs.trigger` says which. `reader.events.typing_recently()` for the don't-nag gate.
- **Overlay exclusion**: ScreenCaptureKit leaves out `com.github.Electron` (dev overlay), names matching
  `miyagi|sandhacks`, `TUT_OVERLAY_BUNDLES`, our pid, and password managers/Messages. `obs.overlay_excluded`.
- **Privacy**: emails, SSNs, phone and card numbers are redacted in OCR and AX text.
```bash
python -m server.screen ax --seconds 20 [--prompt]   # AX spike: frontmost app's editor/terminal state
python -m server.screen cursor --seconds 20          # what's under the mouse
```

## Editor lines: where to type ("Just teach me")
```python
from server.screen import locate_line, locate_anchor
loc = locate_line("pinn_demo/pinn_convection.py", 48)          # LineLocation, truthy when on screen
loc.rect            # Rect: full-width row of the editor text area (points, top-left, primary display)
loc.visible_lines   # (first, last) file lines visible in that editor pane
loc.direction       # "up" / "down" when the line is scrolled off (rect None): scroll, then ask again
loc.reason          # None | no_editor | file_not_active | not_visible | not_found
loc = locate_anchor("def pde_residual(", file="pinn_demo/pinn_convection.py")
loc.line, loc.rect, loc.match_rect   # its file line, the full row, and the anchor text itself
```
- **OCR** (always): finds the line-number gutter (a right-aligned column of increasing integers),
  fits row centres and line height, and fills rows Vision didn't number (it skips lone digits
  1–9, and blank lines have no text) up to the breadcrumbs above and the panel below. Width: from
  the code's left edge to the minimap. Works for full-screen windows (no menu-bar offset) and any
  font size; the terminal panel's `epoch 100, 200, …` column is rejected (wrong spacing).
- **The right file**: the breadcrumb above the pane, else the window title. Tabs don't count
  (inactive tabs are listed too). Another file in front gives `reason="file_not_active"`.
- **Off-screen anchors**: from the AX buffer when Accessibility is granted (unsaved text too), or
  from `file` on disk; `line` + `direction` come back with `rect=None`.
- **AX** (when granted): the focused file, exact buffer text, and the caret-line rect. A row that
  agrees with OCR within half a line takes AX's y (`source="ax+ocr"`). If they disagree, OCR wins
  (folding and word wrap break AX's extrapolation from the caret). AX alone is used only when OCR
  finds no editor. **AX is not verified live yet** (no Accessibility grant on the dev Mac).
- `obs=` runs on a given observation (pure, any OS); without it the live reader uses a frame at
  most 1 s old.
```bash
python -m server.screen line pinn_demo/pinn_convection.py 48 --out line.png
python -m server.screen --image server/screen/fixtures/cursor_fullscreen_bigfont.ocr.json line x.py 100
python -m server.screen anchor "def pde_residual(" --file pinn_demo/pinn_convection.py
```
Tests: `server/screen/tests/test_lines.py` runs on recorded Vision OCR of three rendered
full-screen editors: VS Code at the top of a file, VS Code scrolled to lines 44–84, and Cursor at
14 pt scrolled to 70–115. Each fixture has ground truth for every row; all rows land within 2 pt.
Regenerate them with `python -m server.screen.tests.make_editor_fixtures`.

## Capture backends and replayd stalls
Order: **ScreenCaptureKit** (overlay left out of our frames) → **`screencapture`** (Apple's tool;
overlay text masked via `set_overlay_bounds`) → **CGDisplayCreateImage**. `obs.capture` says which one
made the frame (`sck` / `cli` / `cg` / `fixture`). `TUT_CAPTURE=cli` skips SCK; `TUT_CAPTURE=cg` is the
old CG-only path.

Why: on macOS 26, replayd (the daemon behind SCK) sometimes drops a third-party process's connection
in a loop. Our process then logs `XPC_ERROR_CONNECTION_INTERRUPTED` thousands of times a second, and
ReplayKit burns ~15% CPU. No SCK completion handler fires, and `CGDisplayCreateImage` (built on SCK)
blocks 5 s and returns nil. Before this fix that surfaced as `ScreenUnavailableError: display returned
no image`, and the coach went blind. Apple's `screencapture` uses a private path and keeps working
(~130–180 ms + ~15 ms decode). It isn't caused by full-screen Spaces or a changing display ID (the main
display stays ID 1, awake and unlocked). SCK calls now time out after 1.5 s. A stall makes the
reader use `screencapture` for that same frame, then skip SCK for 10 s, 20 s, … up to 5 min. A
recovery resets the backoff. An interrupted SCK connection is no longer reported as `no_permission`.

## Regions for lesson spotlights
```python
from server.screen import locate_region, get_reader
locate_region("terminal")   # VS Code's integrated terminal panel, or None if it isn't open
locate_region("editor")     # the editor text area (below the tab bar + breadcrumb, above the panel)
locate_region("explorer")   # the side bar (Explorer)
locate_region("run_button") # editor-title Run action: Accessibility only, None without it (unverified live)
get_reader().locate_regions()   # {"terminal": {x,y,w,h} | None, "editor": ..., ...} from one frame
```
Rects are in points, top-left origin of the primary display (same space as `locate()` and the
spotlight). They're stable: edges snap to a 4-point grid, the last rect is kept while every edge moved
< 12 points, and one missed OCR frame is bridged (no blinking spotlight).
- **terminal**: from the panel tab header (`PROBLEMS  OUTPUT  DEBUG CONSOLE  TERMINAL  PORTS`) down to
  the status bar, as wide as the editor area. If the header isn't readable, from the first shell
  prompt below the editor. Code with `%` in it doesn't count as a prompt. With `app="Terminal"`
  (or iTerm2) you get that app's window content instead.
- **editor**: the left edge comes from the tab row or the line-number gutter. The right edge is the
  window, or VS Code's secondary side bar (Chat / Copilot), which is detected as a separate text
  column with its own header. `locate_line` rows stop there too.
- **explorer**: under the `EXPLORER` header (or the OUTLINE / TIMELINE / OPEN EDITORS sections),
  from the side bar's left edge to the editor's.
- **Breadcrumbs are never targets**: `locate()` / `locate_match()` skip the breadcrumb row
  (`pinn_demo › pinn_convection.py › pde_residual`), so a file name there can't be spotlighted.
- Pure, one frame: `find_region(obs, name, app=None)` -> `Region(name, rect, app, source)`.
  CLI: `python -m server.screen region all` (or `--image <fixture>.ocr.json`).
- Tests: `tests/test_regions.py` uses the three rendered full-screen editors (panel at y=800, editor
  x=300) and a recorded real windowed VS Code with Explorer, a Chat side panel and Terminal.app.

## VS Code window, frontmost app, menu bar, hover tooltips
```python
r = get_reader()
r.vscode_window()     # {app, title, folder, file, path, symbol, dirty, sources} | None
r.frontmost()         # {app, pid, title, window_id, rect} of the window in front on the current Space
r.is_frontmost("Code")
unsub = r.on_frontmost_change(lambda new, old: ...)    # fires within ~0.25 s (app switch, Space swipe)
r.locate_region("terminal_menu")   # "Terminal" in the macOS menu bar while VS Code is in front
r.locate_region("menu:Run")        # any menu-bar item
```
- **vscode_window**: the folder comes from the command center and the window title
  (`● calculator.py — python-calculator-e430dc`), else the Explorer header or the breadcrumb root.
  The file comes from the title, and the path from the breadcrumb (`src/calculator.py`), spelled as
  on the tab when OCR drops the dot. Dirty comes from the title's `●` (VS Code's default title
  includes it; OCR rarely reads the dot on the tab), or from AX when granted. Pure version:
  `server.screen.vscode.vscode_window(obs)`.
- **frontmost**: the first normal on-screen window from the window server (`CGWindowListCopyWindowInfo`,
  ~0.3 ms, no permission needed). It follows Space swipes and full screen at once; our overlay never
  counts. `on_frontmost_change` runs one 0.25 s poller and also pokes a capture.
- **terminal_menu**: AX (`AXMenuBar > AXMenuBarItem "Terminal"`) when trusted, else OCR of the menu
  strip. The strip must show ≥3 VS Code menus and VS Code must be in front. It's None in full screen
  (menu bar hidden) or when another app is in front.
- **Hover tooltips** (Pylance `(function) def add(`, diagnostics): their blocks get `role="hover"`
  and are left out of `text()`, `lines_by_app()`, `locate()` and line reading. `obs.hovers()` has their
  text. Rows under a hover come back with `LineLocation.occluded=True`. Before this, a hover over
  `def subtract(a, b):` read as `def b: Any`.
- **Split coloured words**: Vision splits a line at colour changes (`def` | `add(a, b):`).
  Touching blocks on one row are re-joined into one block, so the coach's numbered boxes say
  `def add(a, b):`. A row that still reads like `def(a, b):` (name missing) is OCR'd again on its own
  and replaced only if the second read has the name.

## Set-of-marks candidates (for a model to pick a target by id)
```python
from server.screen import candidates, marks
cs = candidates("the line that defines add")   # live; or candidates(intent, obs=obs) on an observation
prompt = marks.listing(cs)    # "2 [region] editor\n10 [code L4] def add(a, b):\n..."
pick = marks.by_id(cs, 10)    # Candidate(id, kind, text, rect, app, line, region, score, occluded)
```
- **Regions** keep fixed ids: 1 terminal, 2 editor, 3 explorer, 4 terminal_menu. Absent ones are
  left out. Live, they are the same stabilized rects `locate_region` returns.
- **Lines** start at id 10. Editor code rows come first, in file-line order, as full-width rows
  with `line`. Then every other OCR line in reading order, tagged with the region it's in
  (`terminal` / `explorer` / ...).
- **Left out:** hover tooltips, the breadcrumb, the editor tab bar and title bar (command center),
  and gutter numbers. Rows partly under a tooltip are `occluded` and say so in the listing.
- **Stable ids:** the same observation always numbers the same way, whatever the intent.
- **`intent`:** only adds a `score` and, past `max_lines`, keeps the most relevant lines, still in
  id order.

## Haiku target picker (`target.py`): what to box

```python
from server.screen.target import pick_target, pick_on_screen, confirm_on_screen, stats
res = await pick_target(frame, obs, "the VS Code integrated terminal panel")   # pure: PIL frame + its obs
res = await pick_on_screen("the line where the learner types `def add(a, b):`")  # live reader
# -> {"rect": {x,y,w,h}, "box_ids": [11], "label": "code L4: def add(a, b):", "kind": "code" | "blank" |
#     "region" | "text" | "toolbar", "line": 4, "region": "editor", "confidence": 0.9, "reason": "...",
#     "ms", "api_ms", "cached", "input_tokens", "output_tokens", "cost_usd"}  or None
rect, why = await confirm_on_screen(box_rect, intent)   # verifier: agree | moved | none | kept:<outcome>
```
- **Candidates:** `marks.candidates()` (ids 1-4 regions, 10+ lines), plus ids from 500 up:
  - blank editor rows, for "type here";
  - icons on the tab row (the ▷ run button OCRs as "D •");
  - the AX run button;
  - a no-gutter fallback for when Vision misses the line numbers of a short new file. It drops the tab, breadcrumb and side-panel text and adds the blank row under the last line.
- **Request:** the frame is cropped to the front window, scaled to ≤ 1280 px each way, and gets numbered tags (yellow = lines, cyan = regions, pink = icons). It goes out as ONE `claude-haiku-5-5` call: thinking off, effort low, max_tokens 160, strict JSON `{"ids", "confidence", "why"}`. No `temperature`, since Haiku 5.5 rejects it.
- **No box (None) when:** confidence < `MIYAGI_VISION_MIN_CONF` (0.6), no ids, a timeout (`MIYAGI_VISION_TIMEOUT_S`, 2.5 s), an API error, no key, or the budget `MIYAGI_VISION_MAX_CALLS_PER_MIN` (6) is spent.
- **Outcomes:** `pick_with_outcome()` says which case it was. The verifier keeps the engine's own box unless Haiku *answered*: a confident pick elsewhere moves the box, and a sure "nothing" (≥ 0.75) removes it.
- **Cache:** keyed by (the candidate-set hash = what Haiku is shown, snapped to 4 pt; intent; app), 120 s, including "nothing" answers.
- **Logging:** each call logs its tokens and a running $ estimate (Haiku 5.5: $0.10 / $0.50 per MTok); `stats()` gives the totals and p50/p95.
- **Orchestrator:** `ScreenBridge.pick()` / `.confirm()`. `MIYAGI_VISION_TARGET=0` turns both off.
- **Tests:** `tests/test_target.py`, offline with a stub client. The fixture `vscode_lesson_calculator` is Michael's real screen: no line numbers OCR'd, Chat panel, run icon.

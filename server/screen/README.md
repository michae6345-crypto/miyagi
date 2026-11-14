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

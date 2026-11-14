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
answer = await reader.describe("Is this loss curve converging?", region=None)  # Gemini, rate-limited
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
- **env**: loads `TUT_ENV` (default `/Users/tripi/sand hacks/sandhacks-tutor/.env`). `GEMINI_API_KEY`
  for describe, `GEMINI_VISION_MODEL` (default `gemini-2.5-flash`), `TUT_SCREEN_FIXTURE=path.png` to
  replay a saved screenshot instead of the live screen.
- **permission**: the app running the engine needs *System Settings › Privacy & Security › Screen &
  System Audio Recording*. Without it the reader prints exactly that and falls back to the fixture PNGs.
- **perf** (M5 Pro, 3456×2234 Retina, accurate mode, language correction off): capture ~17 ms;
  OCR ~100–220 ms per frame warm depending on how much text is on screen, ~250–350 ms on the first
  frame (Vision warm-up). Static screens aren't re-OCR'd.

## Debug CLI
```bash
python -m server.screen watch [--app Terminal] [--json]      # frontmost app + OCR blocks per frame
python -m server.screen locate "def pde_residual" --out locate.png [--all]   # rect + PNG with it drawn
python -m server.screen metrics 'epoch\s+(?P<step>\d+).*?loss\s+(?P<value>[0-9.eE+-]+)'
python -m server.screen bench -n 8                           # capture + OCR latency
python -m server.screen describe "what is on screen?"
python -m server.screen fixture NAME --apps Code Terminal --titles pinn   # compose a fixture from only those windows
python -m server.screen --image server/screen/fixtures/vscode_terminal_flat.png locate "beta * u_x"
```

## Tests
`pytest server/screen/tests`: pure logic runs anywhere; `test_fixtures.py` runs real Vision OCR on
the two fixture screenshots (VS Code + Terminal, flat loss at β=30 vs. dropping loss), macOS only.

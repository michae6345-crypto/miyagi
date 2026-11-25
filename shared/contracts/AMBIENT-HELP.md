# Ambient help contract: errors, project setup, how-do-I

Nov 24 2026. Help outside a lesson, in whatever app the learner is in. There are three parts:

1. **Explain this error.** Miyagi spots an error on screen. Explain says why it happened and what the likely fix is.
2. **Set up this project.** Miyagi checks the open project for missing tools, runtimes and packages, then installs one when asked.
3. **How do I.** Miyagi answers a question about the frontmost app with a few short steps. bon points at each step's control.

The types live in `events.ts` (app) and `events.py` (engine). Both files are the same on `michael/app-ui-v4` and `integration/live`. Everything here is additive and optional. An app that ignores it keeps today's behaviour, and so does an engine that never sends it.

- **Gate.** The app sends an ambient command only when `engine.hello.capabilities` lists its type. This is the rule for every v2 and ui-v4 command (`core/lesson.ts canSend`). The engine lists a command only once it answers it. `events.py AMBIENT_CAPABILITIES` holds the seven commands. The app's `common/wire.ts` lists the new events in `KNOWN` and the new commands in `V2_COMMANDS`, so each lane only adds its `onMessage` handler and its `canSend` check.
- **Mock.** `app/mock/scenarios/ambient-help.json` sends every event below. Run it with `npm run mock -- ambient-help`, or open the browser stage with `?scenario=ambient-help`.
  - `ambient.set` shows a pandas traceback in Terminal, then a notebook `NameError` 9 s later.
  - `error.explain` answers about pandas.
  - `setup.scan` reports a project with 4 of 7 items missing.
  - `setup.fix` installs pandas, which clears the traceback.
  - `help.ask` walks through "Export as STL" in Blender, and `help.nav` moves it on to the end.
- **Parity.** `python3 scripts/test_contract_parity.py` checks four things:
  - both files list the same events and commands;
  - the four constants match;
  - this file names every ambient message and constant;
  - the mock validates, sends every ambient event and answers every ambient command.
- **Existing parts reused.** Screen reading is `server/screen` (ax, sck, on-device OCR). The install path is action `install` and `setup.progress` (`server/workspace/setup.py`). Rows are `SetupItem`. Model calls go through `server/models.py` and the guarded client via miyagi-cloud. Pointing uses the buddy stroke and spotlight (`features/buddy`, `features/annotate`), and peeks use the notch island (`core/Island.tsx`, `features/notch-home`, `features/pill`).

## Who sends what

| Message | Direction | When |
|---|---|---|
| `ambient.set` | app to engine | On every connect, and when Settings changes "Spot errors" or the muted apps |
| `error.seen` | engine to app | An error is spotted outside a lesson (at most one every 5 s), or one is gone (`clear`) |
| `error.explain` | app to engine | The learner presses Explain on the error's peek |
| `error.explanation` | engine to app | `pending` at once, then the explanation or an `error` |
| `error.dismiss` | app to engine | The learner closes the peek. There is no reply |
| `setup.scan` | app to engine | "Check this project" (the island, Settings, or the learner opening a project) |
| `setup.report` | engine to app | A quick `scanning` answer, then the full one. It comes again after each `setup.fix` |
| `setup.fix` | app to engine | Install on one row |
| `setup.progress` | engine to app | As today: install lines for that `tool`, then `{done, ok}` |
| `help.ask` | app to engine | "How do I ..." asked outside a lesson, typed or spoken |
| `help.steps` | engine to app | `pending`, then the steps. It is sent again as `current` moves or targets move |
| `help.nav` | app to engine | Next, Back, or close on the help card |

## Privacy and cost

These rules apply to the whole feature. The engine lanes implement them and the app lanes rely on them.

- **Spotting errors is local.** The engine reads the screen with the accessibility tree and on-device OCR (`server/screen`). It makes no model call and no network call. Nothing about an error leaves the Mac until the learner presses Explain. The engine keeps a spotted error's lines and context in memory only, for at most 10 minutes, or until `error.dismiss` or `clear`. It never writes them to disk or to logs.
- **Explain sends text, never pixels.** On `error.explain` the engine sends the model:
  - the error's `title` and `lines`;
  - at most `AMBIENT_CONTEXT_LINES_MAX` (6) lines of context, which are the source lines around `file:line` read from the file on this Mac, or the command before a failed one;
  - the app name and the `kind`.

  Paths are cut to the file name or to a path inside the project. Secret-looking values (API keys, tokens, passwords in URLs, `.env` lines) are masked first. A screenshot, a crop or a whole window is never sent.
- **How-do-I sends the question and labels.** On `help.ask` the engine sends the question, the app's name, and the labels of the frontmost window's controls from the accessibility tree, redacted the same way. It never sends a screenshot. Targets are found on this Mac (`via` `ax` or `ocr`). Ambient help never uses the vision pick.
- **Setup makes no model call.** `setup.scan` reads the project's own files on this Mac.
- **Cost.** A model call happens only on a click (Explain, or a sent `help.ask`). Each is one Haiku call (`server/models.py`, never Opus) through the guarded client via miyagi-cloud. Ambient help makes at most `AMBIENT_CALLS_PER_HOUR` (20) calls in any rolling hour on this Mac, for Explain and How-do-I together. The next call is answered at once with `error: "cap"` and `retryInS`. Explaining the same error `id` again answers from memory and costs nothing. Watching a help card's steps advance makes no model call.
- **Off by default in the engine.** The engine watches for errors only after `ambient.set {errors: true}` on that connection. The app's Settings toggle decides, and the app sends the toggle on every connect. While a lesson runs the engine sends no `error.seen`, because the lesson's own off-track card covers errors. The engine never watches apps in `mutedApps`, or Miyagi's own windows (`overlay.bounds`).

## Shared shapes

- `AmbientTarget {x, y, w, h, displayId?, label?, app?, via?}` is a place for bon to point at. It uses screen points with a top-left origin, which is the `ScreenRegion` and `spotlight.rect` space. `displayId` absent means the primary display. `label` is at most 4 words. `via` is `ax` (the accessibility tree, exact) or `ocr`.
- `AmbientFail` says why an answer has nothing:

  | Value | Meaning |
  |---|---|
  | `cap` | The hourly cap was reached. `retryInS` says when to try again |
  | `offline` | There is no network or no cloud |
  | `busy` | The AI provider is overloaded |
  | `gone` | The engine no longer holds that error or help |
  | `no_app` | There is no app to help with |
  | `failed` | Anything else |

  The copy stays calm: "Couldn't explain that just now. Try again in a minute."
- The constants are the same in both files:

  | Constant | Value | What it limits |
  |---|---|---|
  | `AMBIENT_ERROR_LINES_MAX` | 8 | Lines in `error.seen.lines` |
  | `AMBIENT_CONTEXT_LINES_MAX` | 6 | Context lines sent with Explain |
  | `HELP_STEPS_MAX` | 5 | Steps in `help.steps` |
  | `AMBIENT_CALLS_PER_HOUR` | 20 | Model calls per rolling hour |

## 1. Explain this error

```json
{"type": "ambient.set", "payload": {"errors": true, "mutedApps": ["1Password"]}}
```

```json
{"type": "error.seen", "payload": {
  "id": "err-7c1e09", "app": "Terminal", "kind": "python_traceback",
  "title": "ModuleNotFoundError: No module named 'pandas'",
  "lines": ["Traceback (most recent call last):", "  File \"~/code/weather-app/app.py\", line 3, in <module>",
            "    import pandas as pd", "ModuleNotFoundError: No module named 'pandas'"],
  "file": "~/code/weather-app/app.py", "line": 3, "lang": "python",
  "rect": {"x": 212, "y": 618, "w": 520, "h": 72, "label": "The error", "app": "Terminal", "via": "ax"},
  "at": "2026-11-24T10:42:05-08:00"}}
```

- **Kinds.** `kind` is one of:

  | Kind | What it is |
  |---|---|
  | `python_traceback` | A Python traceback |
  | `js_error` | A browser console or Node error |
  | `compiler` | tsc, gcc, rustc, javac and similar |
  | `shell_exit` | A command that ended non-zero, with `exitCode` |
  | `notebook_cell` | A Jupyter or VS Code notebook cell error |
  | `app_dialog` | A frontmost app's error sheet or alert, read from its accessibility tree |

- **id.** The `id` is stable for the same app, kind, title and `file:line`. The same error printed again keeps its `id` and counts up `again`. It never becomes a second peek.
- **title and lines.** `title` is at most 80 characters, usually the error's own last line. `lines` holds the first `AMBIENT_ERROR_LINES_MAX` lines as read, with the home folder shortened to `~` and secrets masked as `••••`.
- **rect.** `rect` is where the error is on screen. The peek grows from the island toward it, and bon can point at it.
- **clear.** `{"id": "err-7c1e09", "clear": true}` means the error is gone: the next run printed no error, or the dialog closed. The app fades that peek. The app may also fade a peek it has shown for a while.
- **Copy.** The peek is calm, with no hue, as in BRAND.md: off track never uses red. Use a short line such as "Python stopped at line 3" with Explain as its one primary action, and nothing alarming.

```json
{"type": "error.explain", "payload": {"id": "err-7c1e09", "reqId": "x1"}}
```

```json
{"type": "error.explanation", "payload": {"id": "err-7c1e09", "pending": true}}
{"type": "error.explanation", "payload": {
  "id": "err-7c1e09", "title": "pandas isn't installed here",
  "why": "app.py imports pandas, but the Python running it has never installed pandas, so the import stops on line 3.",
  "fix": "Install pandas into this project's .venv, then run app.py again.",
  "command": "pip install pandas",
  "install": {"tool": "pandas", "label": "pandas", "kind": "python_package", "why": "app.py reads the weather data with it",
              "needed": true, "installed": false, "ok": false, "install": {"method": "pip", "command": "pip install pandas"},
              "from": "requirements.txt:3", "setupKind": "package", "actions": ["install"]},
  "file": "~/code/weather-app/app.py", "line": 3,
  "target": {"x": 212, "y": 618, "w": 520, "h": 72, "label": "The error", "app": "Terminal", "via": "ax"}}}
```

- **Text fields.** `title` is at most 8 words. `why` says in plain words what went wrong, in at most 40 words. `fix` gives the likely fix in at most 25 words.
- **Optional parts.** Each optional part shows only when present:
  - `diff` is a unified diff for `file`. The app shows it and never applies it on its own.
  - `command` is a terminal fix the app offers to copy.
  - `install` is the `SetupItem` to install. Its Install button sends `setup.fix {tool}`, and the progress comes as `setup.progress`.
  - `target` is the place bon points at: the line in the editor, or a dialog's button.
- **When there is no answer.** The answer is `{"id": "err-7c1e09", "error": "cap", "retryInS": 1200}`. After a dismiss or after 10 minutes it is `error: "gone"`.

```json
{"type": "error.dismiss", "payload": {"id": "err-7c1e09"}}
```

## 2. Set up this project

```json
{"type": "setup.scan", "payload": {"reqId": "scan-1"}}
```

```json
{"type": "setup.report", "payload": {
  "reqId": "scan-1", "root": "~/code/weather-app", "name": "weather-app",
  "files": ["requirements.txt", ".python-version", "package.json", ".nvmrc", "Dockerfile"],
  "env": {"python": "~/code/weather-app/.venv (Python 3.12.4)", "node": "node 18.19.0"},
  "items": [
    {"tool": "pandas", "label": "pandas", "kind": "python_package", "why": "app.py reads the weather data with it", "needed": true,
     "installed": false, "ok": false, "install": {"method": "pip", "command": "pip install pandas"}, "from": "requirements.txt:3",
     "setupKind": "package", "actions": ["install"]},
    {"tool": "node", "label": "Node.js 20", "kind": "runtime", "why": ".nvmrc asks for Node 20; this Mac has 18.19", "needed": true,
     "installed": false, "ok": false, "version": "18.19.0", "minVersion": "20", "install": {"method": "brew", "command": "brew install node@20"},
     "from": ".nvmrc", "setupKind": "package", "actions": ["install"]},
    {"tool": "node_modules", "label": "Node packages (14)", "kind": "node_package", "why": "package.json lists them; none installed yet",
     "needed": true, "installed": false, "ok": false, "install": {"method": "npm", "command": "npm install"}, "from": "package.json",
     "setupKind": "package", "actions": ["install"]},
    {"tool": "requests", "label": "requests", "kind": "python_package", "why": "app.py fetches the forecast with it", "needed": true,
     "installed": true, "ok": true, "version": "2.32.3", "install": {"method": "pip"}, "from": "requirements.txt:1", "actions": []}
  ],
  "ready": 3, "total": 7}}
```

- **Which project.** `path` is the project folder. When it is absent, the engine uses the folder open in the frontmost editor (VS Code's workspace). With neither, the answer is `error: "no_project"`.
- **What it reads.** The engine reads only the project's own files, on this Mac, with no model call: `requirements.txt`, `pyproject.toml`, `Pipfile`, `environment.yml`, `.python-version`, `package.json`, `.nvmrc`, `.node-version`, `Dockerfile` and `docker-compose.yml`. The engine may read more manifest kinds later, and they show up in `files`. It never runs a script from the project.
- **Rows.** Each row is today's `SetupItem` plus three additions:
  - `from`: the file and line that asked for it;
  - kind `node_package`: all of `package.json`'s dependencies as one row;
  - install method `npm`.

  Missing rows come first. A long requirements file sends the missing rows and the first ready ones, and `more` counts the rows left out. `env` names the interpreters the checks used, so "installed" means installed in that `.venv`.
- **Quick first answer.** A first answer with `scanning: true` (and no items) may come within about 100 ms, so the card can open at once.
- **Licensed apps.** These rows behave exactly as on the lesson setup card: `have_it`, `get_it` and `alternative`, and they are never installed.

```json
{"type": "setup.fix", "payload": {"tool": "pandas", "root": "/Users/<you>/code/weather-app"}}
```

- **How it installs.** `setup.fix` takes the same install path as action `install`:
  - brew formulas, and casks on the existing allowlist only;
  - pip into the project's own `.venv` when it has one, never `sudo`;
  - `npm install` in `root` for `node_package`.
- **What comes back.** The answer is `setup.progress {tool, line}` lines, then `{tool, done, ok, version | error}`, then a fresh `setup.report`.
- **Consent.** The row's Install button is the learner's yes. The engine never installs a row that the learner did not press.

## 3. How do I

```json
{"type": "help.ask", "payload": {"text": "How do I export this as an STL?", "reqId": "help-1", "app": "Blender", "source": "typed"}}
```

```json
{"type": "help.steps", "payload": {"reqId": "help-1", "app": "Blender", "goal": "", "steps": [], "current": 0, "pending": true}}
{"type": "help.steps", "payload": {"reqId": "help-1", "app": "Blender", "goal": "Export as STL", "current": 0, "steps": [
  {"id": "h1", "text": "Click File in the top bar", "advance": "click",
   "target": {"x": 34, "y": 31, "w": 38, "h": 22, "label": "File", "app": "Blender", "via": "ax"}},
  {"id": "h2", "text": "Point to Export", "detail": "It is near the bottom of the File menu.", "advance": "screen",
   "target": {"x": 34, "y": 418, "w": 220, "h": 24, "label": "Export", "app": "Blender", "via": "ax"}},
  {"id": "h3", "text": "Choose Stl (.stl)", "advance": "click",
   "target": {"x": 258, "y": 610, "w": 180, "h": 24, "label": "Stl (.stl)", "app": "Blender", "via": "ax"}},
  {"id": "h4", "text": "Pick a folder, then click Export STL", "detail": "Turn on Selection Only to export just your mug.", "advance": "click",
   "target": {"x": 1140, "y": 742, "w": 132, "h": 30, "label": "Export STL", "app": "Blender", "via": "ax"}}]}}
```

- **Where help.ask comes from.** The island's ask field or push-to-talk sends `help.ask` for a "how do I ..." asked outside a lesson. A circled region stays with circle to ask (action `ask` with `region`). `text` is at most 300 characters. `app` is the app that was frontmost before the ask field took focus; the app records it, because by the time the engine looks, Miyagi's own window is in front.
- **Steps.** There are 1 to `HELP_STEPS_MAX` (5) steps. Each `text` is one action in at most 12 words, and `detail` is at most 25 words. A step's `target` may be missing at first, for example a menu item that is not open yet. A later `help.steps` fills it in when the engine finds it.
- **Moving on.** `current` is the step to do now, 0-based. The engine watches the frontmost app on this Mac and sends `help.steps` again (same `reqId`) when the step is done. `advance` says what counts:

  | `advance` | The step is done when |
  |---|---|
  | `click` | The target is clicked |
  | `screen` | The screen changes as the step says (a menu, sheet or window opens) |
  | `next` | The learner presses Next |

  When the window moves, a re-send carries the new target rects. After the last step it sends `done: true`, and the app closes the card a moment later ("Good. Now the next one." is for lessons; here a quiet "Done" is enough).
- **Ending.** The engine stops watching on any of these:
  - `done`;
  - `help.nav {to: "close"}`;
  - a new `help.ask`, which replaces the one before;
  - a lesson starting;
  - 5 minutes without progress.

  Watching makes no model call. If the screen goes somewhere the steps did not expect, the engine may plan again once. That counts against the hourly cap.
- **One card at a time.** There is only one help card at a time. bon points at `steps[current].target`, using the buddy stroke from the island and the existing pointing.

```json
{"type": "help.nav", "payload": {"reqId": "help-1", "to": "next"}}
```

- **Next and Back.** `next` and `back` move `current` and are answered with `help.steps`. `close` gets no reply.

## Lanes

- **App.** `features/ambient` (new) holds the peek, the explanation card, the project setup card and the help card. It reuses the setup rows from `features/cards`, and the buddy stroke and spotlight for targets. Circle to ask (`features/circle-ask`) belongs to another lane: reuse its answer card through its exports and do not edit its files. Settings gains "Spot errors" and muted apps (`ambient.set`).
- **Engine.** `server/ambient` (new) does three jobs:
  - error spotting from `server/screen`, local only;
  - Explain through the coach's model client with a Haiku route in `server/models.py`, the hourly cap and redaction;
  - help steps planned from the accessibility labels, with targets resolved by ax or OCR and advanced by screen changes.

  `server/workspace` gets the project scan and `setup.fix`. Each command goes into `engine.hello.capabilities` only once it is answered.
- **Tests.** Engine tests are offline and mock the model client. App tests use the mock scenario.

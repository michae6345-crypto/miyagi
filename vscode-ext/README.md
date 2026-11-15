# Miyagi Companion (VS Code extension)

A tiny VS Code extension that lets the Miyagi engine **read and drive VS Code exactly** instead of guessing from OCR:
which folder and file are open, unsaved edits, the cursor, the terminal's last command with its exit code and output.
It can also open a file at a line, open the terminal, run a command in it, and apply a fix and save it.

**It draws nothing in VS Code.** Miyagi's own overlay (the white spotlight box, the drawer, the cards) is the only
UI, so a lesson looks the same with or without the extension. The only things you see in VS Code are the lesson
file being opened and the one terminal named "Miyagi" that "Run it for me" uses. No status bar item, no
notification, no webview, no editor decoration, no diff tab, and no command palette entry. The `/highlight` box
and `/diff` tab exist only behind the `miyagi.editorUi` setting (default `false`).

It is plain JavaScript (`extension.js` + `package.json`) with no build step and no dependencies. It needs
VS Code 1.90 or newer; exit codes need 1.93 or newer. It starts on VS Code startup (`onStartupFinished`) and serves
HTTP on **127.0.0.1 only**, port 8791. Every VS Code window runs its own copy, so a second window takes 8792, and
so on up to 8799.

The engine side is `server/workspace/vscode_ext.py`. Every call there returns `None` when the extension isn't
running, so the engine falls back to its OCR path.

## Install (not done yet: waiting for Michael's OK)

From the repo root, copy the folder into VS Code's extensions folder:

```bash
rm -rf ~/.vscode/extensions/miyagi.companion-0.0.1 && cp -R vscode-ext ~/.vscode/extensions/miyagi.companion-0.0.1
```

Then reload each open VS Code window: **Cmd+Shift+P → "Developer: Reload Window"**. To check it:

```bash
curl -s 127.0.0.1:8791/health
```

The output channel "Miyagi Companion" (Output panel, never opened by the extension) logs the port and each
`terminal/run`.

- **Update:** run the same copy command again, then reload the window.
- **Uninstall:** `rm -rf ~/.vscode/extensions/miyagi.companion-0.0.1`, then reload the window.
- **If it doesn't show up** under Extensions → `@installed miyagi`, you can try it without installing. This opens
  a separate "Extension Development Host" window with the extension loaded (`code` isn't on PATH on this Mac,
  hence the full path):
  `"/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code" --extensionDevelopmentPath="$PWD/vscode-ext" <lesson folder>`

## API

All bodies are JSON. Lines and columns are **1-based**. File paths are absolute; relative paths resolve against the
window's first folder, and `~` is expanded.

| Request | Body | Answer |
|---|---|---|
| `GET /health` | | `{ok, name, version, port, pid}` |
| `GET /state` | | see below |
| `GET /text?file=<path>` | (no file: the active editor) | `{file, text, dirty, version, languageId, lineCount}`. The editor's text, **unsaved edits included** |
| `POST /open` | `{file, line?, column?, preserveFocus?}` | `{ok, file, line, languageId, dirty}`. Opens in **this** window (never a new one), keeps the column the file is already shown in, and centers the line |
| `POST /highlight` | `{file, startLine, endLine?, focus?, reveal?}` | `{ok, file, startLine, endLine}`. Centers the lines in view and records them in `/state.highlight`. Draws nothing unless `miyagi.editorUi` is on: then one white 2px box (faint white fill) around the lines, one per window, repainted when the file becomes visible again |
| `POST /highlight` | `{clear: true}` | `{ok, cleared: true}` |
| `POST /terminal` | `{show: true, cwd?, preserveFocus?}` | `{ok, shown, terminal, created}`. Shows the "Miyagi" terminal, else the active one, else creates "Miyagi" |
| `POST /terminal` | `{show: false}` | Closes the panel |
| `POST /terminal/run` | `{cmd, cwd?, preserveFocus?}` | `{ok, terminal: "Miyagi", created, sent, shellIntegration, reportsExitCode}`. Reuses one "Miyagi" terminal: shows it, then `sendText(cmd)`. When `cwd` is given and the shell is somewhere else, it sends `cd '<cwd>' && cmd`. The exit code and output arrive later in `/state.lastCommand` and as a `command_end` event |
| `POST /apply` | `{file, newText \| edits, save = true, reveal = true}` | `{ok, file, created, saved, dirty, version, lineCount}`. Edits through a `WorkspaceEdit`, so an **unsaved buffer** is edited and not overwritten on disk behind VS Code's back. Then it saves. `newText` on a missing file creates the file |
| `POST /diff` | `{file, newText, title?}` | `{ok, file, title, proposed}`. Only with `miyagi.editorUi` on (else 409 `editor_ui_off`): runs `vscode.diff` with the file (as the editor has it) on the left and `newText` on the right. Changes nothing |

`edits` is a list. Each edit takes one of these forms:

- `{find, replace}`: the first line equal to `find` (trimmed) becomes `replace`, keeping that line's indentation.
  This matches E5's `apply_fix`.
- `{startLine, endLine?, text}`: replaces whole lines, inclusive. `endLine = startLine - 1` inserts before
  `startLine`, and a `startLine` past the end appends.
- `{startLine, startColumn, endLine, endColumn, text}`: replaces an exact character range (the end is exclusive).

Errors come back as `{ok: false, error}` with an HTTP status:

| Status | `error` values |
|---|---|
| 400 | `file_required`, `bad_json`, `cmd_required`, `newText_or_edits_required`, `bad_edit` |
| 403 | `origin_not_allowed`, `browser_not_allowed`, `host_not_allowed` |
| 404 | `not_found`, `no_route` |
| 409 | `find_not_found`, `edit_rejected`, `editor_ui_off` |
| 415 | `json_required` |

**Slow actions:** an action that takes longer than 250 ms answers `{ok: true, pending: true, id}`. It still
finishes, and its result is posted as an `action_done` event. The engine's client gives up after 300 ms.

### `GET /state`

```jsonc
{
  "ok": true, "app": "vscode", "extension": "0.0.1", "vscodeVersion": "1.146.0", "pid": 123, "port": 8791,
  "folders": ["/Users/me/miyagi/lessons/python-calculator-e430dc"], "workspaceName": "python-calculator-e430dc",
  "file": "/Users/me/miyagi/lessons/python-calculator-e430dc/calculator.py", "relPath": "calculator.py",
  "dirty": true, "languageId": "python", "lineCount": 4,
  "cursor": {"line": 3, "column": 1}, "selection": null,
  "visibleRanges": [{"startLine": 1, "endLine": 4}],
  "dirtyFiles": ["/Users/me/.../calculator.py"],
  "openFiles": [{"file": "/Users/me/.../calculator.py", "dirty": true, "active": true}],
  "terminalOpen": true, "activeTerminal": "Miyagi",
  "terminals": [{"name": "Miyagi", "active": true, "shellIntegration": true}],
  "lastCommand": {"id": 7, "commandLine": "python calculator.py", "exitCode": 1, "running": false,
                  "terminal": "Miyagi", "cwd": "/Users/me/.../python-calculator-e430dc",
                  "outputTail": ["Traceback (most recent call last):", "NameError: name 'add' is not defined"],
                  "startedAt": 1763160000000, "endedAt": 1763160000400},
  "shellIntegrationApi": true,
  "windowFocused": true, "lastFocusedAt": 1763160000000,
  "highlight": {"file": "/Users/me/.../calculator.py", "startLine": 3, "endLine": 3}
}
```

`lastCommand` covers **every** command run in any terminal of that window, including ones the learner types. It
needs VS Code shell integration, which is on by default for zsh and bash on VS Code 1.93 or newer.
`outputTail` is the last 40 lines, with ANSI codes stripped and `\r` progress bars collapsed.

## Events → engine

The extension makes a best-effort `POST <miyagi.engineUrl>/vscode/event` (default `http://127.0.0.1:8787`,
300 ms timeout). Errors are ignored. Every event carries `{type, ts, port, pid, folders, windowFocused}` plus:

| `type` | Extra fields | When |
|---|---|---|
| `ready` | `version, file, languageId, dirty` | The extension started |
| `editor` | `file, languageId, dirty` | The active editor changed (120 ms debounce) |
| `dirty` | `file, dirty, languageId` | A buffer became dirty or clean (flips only, not every keystroke) |
| `save` | `file, languageId` | A file was saved |
| `focus` | `focused` | The window gained or lost focus |
| `terminal` | `opened` or `closed` (a name) | A terminal was opened or closed |
| `command_start` | `command` | A command started (needs shell integration) |
| `command_end` | `command` (with `exitCode` and `outputTail`) | A command ended (needs shell integration) |
| `action_done` | `action, id, result` | A slow action (see above) finished |

The engine stores these with `server.workspace.vscode_ext.record_event`. To react to them, use
`vscode_ext.subscribe(cb)`.

## Engine client (`server/workspace/vscode_ext.py`)

```python
from server.workspace import vscode_ext as vx
st = vx.state(folder=lesson_dir)                 # None = no extension -> use OCR
vx.open_file(lesson_dir / "calculator.py", 3)
vx.highlight(lesson_dir / "calculator.py", 3, 5); vx.clear_highlight()
vx.run_in_terminal("python calculator.py", cwd=lesson_dir); vx.last_command()
vx.replace_line(path, yours, expected)           # "Do it for me", saved, unsaved buffer safe
vx.diff(path, new_text)
vx.buffer_text(path)["text"]                     # checks can see unsaved code
vx.active_editor()                               # pass as active= to server.workspace.active.wrong_folder
```

Calls go to the window whose folder holds the file (or the given `folder`). Otherwise they go to the focused window,
then the last focused one. Ports come from `MIYAGI_VSCODE_PORTS` (default `8791-8799`). Every call is synchronous
and takes at most 300 ms. From async code, use `await asyncio.to_thread(...)`.

## Safety

- The server binds `127.0.0.1` only.
- A web page in a browser can also reach 127.0.0.1, so the extension refuses these requests:
  - any request with an `Origin` header;
  - any request with a `Sec-Fetch-Site` header other than `none`;
  - any request whose `Host` isn't `127.0.0.1`, `localhost` or `[::1]` (this blocks DNS rebinding);
  - any POST that isn't `application/json` (this forces a CORS preflight, which is never answered).

  The engine's plain HTTP client sends none of these headers.
- The extension never opens a new window, never installs anything, and makes no network calls except to the
  engine on localhost.

## Limits

- `terminalOpen` means "a terminal exists". VS Code's API doesn't expose whether the panel is visible.
- There is no API to bring the VS Code window to the front. Use `open -a "Visual Studio Code"`, as
  `server.workspace.editor` does.
- Without shell integration (VS Code before 1.93, or an unusual shell), `/terminal/run` still runs the command, but
  `exitCode` and `outputTail` aren't reported. `reportsExitCode: false` tells you when that's the case.

## Tests (offline)

```bash
cd vscode-ext && npm test                                        # extension.js against a stubbed `vscode`
python -m pytest server/workspace/tests/test_vscode_ext.py      # client + engine route + end-to-end with node
```

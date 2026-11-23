# server/workspace: what the lesson needs, one folder per lesson, starter files, VS Code

Every lesson except the demo hero gets its own folder, `~/miyagi/lessons/<slug-of-title>-<hash>/`,
scaffolded from the lesson's step graph by Claude and opened in VS Code. The hero (Toscano's PINN
diffusion video) keeps `demo/pinn-lab`.

## Interface

```python
from server.workspace import build_workdir, prepare, open_editor, open_file_for, read_state

wd_for_build = build_workdir(url)            # hero video -> demo/pinn-lab; else a not-yet-existing path
graph = await build_lesson(url, goal, wd_for_build)
wd = prepare(graph, goal)                    # Path (sync; blocking Claude call: use asyncio.to_thread)
ok = open_editor(wd, open_file_for(wd))      # bool
```

| function | does |
|---|---|
| `prepare(lesson, goal, *, root=None, client=None) -> Path` | Hero → its folder, untouched. Else creates/reuses `<root>/<slug>-<sha1(lesson.id)[:6]>/`, asks Claude for starter files, writes them + `README.md`. Never raises on API trouble (README only, `read_state(wd)["error"]` says why, and the next `prepare` retries). Never overwrites a file; a folder already scaffolded is returned as is. |
| `open_editor(path, file=None, *, runner=None) -> bool` | `code -n <dir> -g <file>` (`code` on PATH, else the CLI inside `/Applications/Visual Studio Code.app`); fallback `open -a "Visual Studio Code" <dir> [<file>]`. |
| `open_file_for(path) -> str \| None` | The starter file to show first (Claude's `open_file`), else `README.md`. |
| `read_state(path) -> dict \| None` | What `prepare` did: `stack, summary, setup, open_file, files, git, dropped, model, error, seconds`. Kept in `<root>/.miyagi-state/<folder>.json`, so the learner's folder holds only their files. |
| `build_workdir(url) -> str` | The workdir to hand `build_lesson` before the folder exists. Non-hero lessons get a path that doesn't exist, so the builder plans for a fresh start instead of adapting checks to `demo/pinn-lab`'s files. |
| `hero_workdir(graph) -> Path \| None` | The hero's folder if `graph` is the hero, else None. |

## Setup check: `requirements()` and `install()` (setup.py)

Before anything opens, find out what the lesson needs and whether this Mac has it.

```python
from server.workspace import requirements, editor_needed, missing, install, setup_card

items = requirements(graph, workdir=wd)    # read-only; Claude's list cached per lesson, local checks every call
editor_needed(items)                       # False for Blender / Figma / browser-only lessons
card = setup_card(items)                   # payload for the proposed card {kind: "setup"}
res = install(item, workdir=wd, on_line=cb)  # ONLY after the learner tapped Install for that item
```

- `requirements(lesson, *, workdir=None, client=None) -> list[item]`. `WORKSPACE_REQ_MODEL` (default `claude-haiku-5-5`,
  structured output) reads the step graph and returns `{editor: {needed, why}, tools: [...]}`. Item 0 is always the editor
  (`vscode`; for a lesson that doesn't need one, `needed: false` and `why` starts with "No editor needed:").
  Items: `{tool, label, kind (editor|app|runtime|cli|python_package|web_app), why, needed, installed, ok, version, min_version, where,
  install: {method (brew|brew_cask|pip|download|open|none), command, url}}`. `web_app` items (OpenAI Platform,
  Botpress, Zapier, Google Sheets, ...) are always `ok`, method `open` + an https URL, and never count as missing. `ok` = installed and `>= min_version`.
  Returns `[]` with no key or on API failure (the lesson still runs). Claude's list is cached by **video id** (the prompt
  never sees the goal), so S8's preflight (`preflight-<videoId>`) warms the real lesson's setup card.
- Local checks are fast and read-only: `/Applications/<App>.app` then `mdfind kMDItemCFBundleIdentifier == '<id>'` for apps
  (+ `defaults read .../Info CFBundleShortVersionString`), `which <bin>` + `<bin> --version` for CLIs/runtimes (python = the
  newest `python3.x` on PATH, since Apple's `/usr/bin/python3` is 3.9), `<python> -c "import <module>"` for Python packages
  (the lesson's `.venv` if it exists).
- Install recipes: Homebrew formula/cask from a small catalog (vscode, python, node, git, rust, go, java, docker, blender,
  figma, unity, jupyter; every name verified with `brew info`) or Claude's validated suggestion; Python packages via pip into the
  lesson's `.venv`. A pip spec keeps only the name and a `>=` floor (old pins like `pandas<2` have no wheels for current Python).
  Without Homebrew, the official download URL.
- `install(item, *, workdir=None, on_line=None) -> {ok, tool, method, error?, url?, version?}`. It runs
  `brew install [--cask] <name>` (`HOMEBREW_NO_AUTO_UPDATE=1`, stdin closed, so a cask that wants a sudo password fails with
  that error instead of hanging) or `<workdir>/.venv/bin/python -m pip install <pkg>` (the venv is created with the newest python3 if missing).
  Output lines stream to `on_line`; afterwards the tool is re-checked. Never installs Homebrew; without it, returns `url`.
  The argv is rebuilt from method + a validated name: no shell, never a command string from Claude or the app.
  It is synchronous: run it in a thread and bridge `on_line` with `loop.call_soon_threadsafe`.

### The video decides, not the search text

Both Claude prompts (starter files and requirements) get the video's steps, title and libraries, never `lesson.goal`
(what the learner typed). The scaffold also classifies the lesson (`lesson_kind`: `code | no_code | conceptual`);
no-code and conceptual lessons never get files, git history or setup commands, whatever Claude returns. The README leads
with the video's title, shows `<sub>You asked for: …</sub>` when the request differs, and a "Heads-up: this video only
partly matches what you asked for (match N%). <note>" line when `lesson.goalMatch` (E2: `{score: 0..1 | null, note}`;
1 = achieves the goal, 0.5 = related but a different project/tool, 0 = unrelated) has `score < 0.7`. `score: null` means
unknown (no goal given / not scored) and shows nothing. Also accepted: a bare number, a level string, `{level, reason}`.
A reused folder gets its README rewritten (no Claude call), so wording fixes reach existing folders.

### Proposed contract (additive, for E4 / the app)

```ts
// EngineEvents
"card": { ...; kind: "explain" | "hint" | "answer" | "setup";
          actions?: Array<"confirm" | "undo" | "apply_fix" | "open_editor" | "open_in_browser" | "install" | "skip_setup">;
          setup?: { editorNeeded: boolean; items: SetupItem[] } };
"setup.progress": { tool: string; line?: string; done?: boolean; ok?: boolean; error?: string; url?: string; version?: string };
interface SetupItem { tool: string; label: string; kind: "editor" | "app" | "runtime" | "cli" | "python_package" | "web_app"; why: string;
  needed: boolean; installed: boolean; ok: boolean; version?: string; minVersion?: string;
  install: { method: "brew" | "brew_cask" | "pip" | "download" | "open" | "none"; command?: string; url?: string } }
// AppCommands "action" kinds: + "open_editor" | "install" (text = tool id; one Install button per missing item) | "skip_setup"
// "open_in_browser" can be handled by the app alone: open each web_app item's install.url (or one link per item).
```

`setup_card(items)` builds this card: `title` "Before you start" / "Ready to go", `body` lists what's missing (plus the
"No editor needed" line), `actions` = `open_editor` (editor needed and installed) + `open_in_browser` (web apps) + `install` (something missing) + `skip_setup`.
For a `download` item the app opens `install.url` instead of sending `install`.

Orchestrator flow: on lesson.ready, run `requirements(graph, workdir=wd)` in a thread and emit the setup card (skip it when
the list is empty). Don't auto-open VS Code any more. `action install {text: tool}` → `install(item, workdir=wd, on_line=…)` →
`setup.progress` lines, then `{done, ok, error|version}`, then re-run `requirements` (cached list, fresh checks) and re-emit the card.
`action open_editor` → `open_editor(wd, open_file_for(wd))`. `action skip_setup` → dismiss.

### Smart setup: packages, free apps, licensed apps, web apps (apps.py, Nov 22)

Michael's "AutoCAD - Toy Car Creation for 3D Printer" card said "Missing: autocad. Install now?" with only Skip. Every
row now has a `setupKind` (`apps.classify`):

| setupKind | examples | what the row offers |
|---|---|---|
| `package` | python, git, numpy (pip / brew formula) | Install (the existing allowlisted installers) |
| `free_app` | Blender, FreeCAD, GIMP, Inkscape, PrusaSlicer (`apps.FREE_APPS`) | Install via an allowlisted Homebrew cask (`setup.ALLOWED_CASKS`; a model's cask off the list gets the download page), I have it |
| `licensed_app` | AutoCAD, Fusion, Photoshop, Excel, MATLAB, SOLIDWORKS (`apps.LICENSED`) | never installed: I have it, Get it (the vendor's own page, host on `apps.VENDOR_HOSTS`), the free alternative (FreeCAD, GIMP, Onshape...) |
| `web_app` | Tinkercad, Botpress, Google Sheets | Open |

- A licensed row's `install` is `{method: "download", url: <vendor page>}` (older apps show "Get it"); `install()` refuses it.
  A model's link or cask for it is never used.
- Detection (`apps.detect`, read-only): `/Applications` and `~/Applications`, one folder down too
  (`/Applications/Autodesk/AutoCAD 2025/AutoCAD 2025.app`, newest year wins), then `mdfind` by bundle-id prefix
  (`com.autodesk.AutoCAD*`), version from Info.plist. `noMac` for Windows-only apps.
- A title that names its app (`apps.app_in_text`: "AutoCAD - ..." → autocad) adds the row even offline or when Claude
  left it out, for no-code lessons only (a pandas lesson about Excel files is still a code lesson).
- Card copy for a missing licensed app, two modes (fix round 2):
  - **Today's app** (`setup.APP_RENDERS_APP_ACTIONS = False`, the default until the app's claim PR lands): the app's
    CardActions drops `have_it` / `get_it` / `alternative`, so the card says only what its visible buttons do. The
    installable free alternative gets its own row (`setup.offer_alternatives`: FreeCAD, `install.method` brew_cask,
    `altFor` engine-only, never "missing", never in Install all). Body "AutoCAD is paid. Get it, install FreeCAD free,
    or skip." (no installable alternative: "AutoCAD is a paid app. Get it, or skip to watch."), actions `install`,
    `skip_setup`. Installing that row is the learner's choice: the AutoCAD row becomes `using` FreeCAD
    (`setup_apps.after_install`), remembered, checks re-pinned. "I have it" / AutoCAD found hides the offered row.
  - **App draws the buttons** (`APP_RENDERS_APP_ACTIONS = True`): title "This lesson uses AutoCAD", body "Have AutoCAD
    already? Or try FreeCAD, free.", actions `have_it`, `get_it`, `alternative`, `skip_setup` (labels in
    `setup.actionLabels`); the alternative's row is added when chosen. " Watch while you decide." is added only once the
    app honours `setup.holdVideo` (`setup.APP_HONOURS_HOLD_VIDEO`). Flip both flags with the app PR.
  No "Install now?", no long "No editor needed: ..." line either way.
- An app lesson with nothing missing (AutoCAD found, or a remembered "I have it" / FreeCAD choice) gets no waiting card,
  only a passing note ("AutoCAD is ready", "Using your AutoCAD", "Using FreeCAD for this lesson"; `actions: []`,
  `dismissAfterMs`): today's app holds the video under any setup card with actions, Skip included. Lesson mode and the
  session's other setup filters use `setup.missing()` (haveIt / using / altFor rows are not missing).
- `setup.holdVideo`: False unless the current step truly needs a missing tool Install can get now (`setup_card(...,
  hold_for=step.requires)`). Setup is a companion: an app that reads holdVideo keeps the video playing. App side:
  draft claim PR #252 (`michael/app-setup-actions` into adrian/shell): CardActions lists `have_it` / `get_it` /
  `alternative`, player/store.ts setupWaiting holds only when `holdVideo === true` (old rule when the field is
  missing), and the Drawer's "Waiting on setup" skips `haveIt` / `using` rows and holdVideo=false cards. Flip
  `APP_RENDERS_APP_ACTIONS` and `APP_HONOURS_HOLD_VIDEO` once it merges.
- Learner works in the alternative (`using`), or said "I have it" but the app was not found: the lesson's app pin
  moves (`app_lesson.repin`): screen checks and targets pinned to "AutoCAD" look at FreeCAD's window (a web
  alternative, or an unfound "I have it": no pin, the judge decides), and step copy "in AutoCAD" reads "in FreeCAD".
- Per-row additive fields: `setupKind`, `actions` (`install | have_it | get_it | alternative | skip`), `vendorUrl`,
  `vendorName`, `alternative {name, url, tool}`, `haveIt`, `using`, `noMac` (contract: events.ts SetupItem).
- What the learner said is kept per Mac in `<lessons root>/.miyagi-state/mac-apps.json` (`apps.remember / recall`):
  "I have it" (`haveIt`) and "use FreeCAD" (`using`) are not missing next lesson either. "I have it" lasts
  `apps.HAVE_IT_DAYS` (14) from the press (`haveItAt`, `apps.have_it_fresh`), so a mistaken press undoes itself and
  the card asks again. A bare ambiguous name from the model ("rhino", "word", "maya") is the paid app only with kind
  "app" (`apps.canonical(name, kind)`; otherwise `setup._canonical` gives "rhino-pkg"). Each scan's app rows are kept
  too, and `apps.context_line(items)` ("Apps on this Mac: AutoCAD 25.0 is installed.") goes into the coach's explain
  context as an `<untrusted source="setup">` block (code lessons: nothing added).
- Session side: `server/orchestrator/setup_apps.py` (have_it re-checks, get_it opens the vendor page through
  `server.safety.browser_url_allowed`, alternative opens a web alternative or adds the free app's own Install row,
  `on_front` re-checks a row when its app comes to the front). App lessons' wording and checks:
  `server/lesson/app_lesson.py` ("in AutoCAD", screen checks scoped to the app, no file / command checks).

## Editor: VS Code, frontmost, room for the video (editor.py)

- **Which editor:** VS Code (`com.microsoft.VSCode`, `code`); Miyagi only ever opens, names or offers VS Code
  (`ALLOW_CURSOR` in editor.py is a local opt-out). Detection: `/Applications/<App>.app`, else `mdfind` by
  bundle id; the CLI is found on PATH or inside the .app. `preferred_editor()`, `installed_editors()`, `editor_label()`
  ("Visual Studio Code"), and `goto_argv(file, line)` → `[<cli>, "-r", "-g", "file:line"]` for step jumps.
- **The setup card names it:** item 0 is `vscode` (`brew install --cask visual-studio-code` if it is missing);
  `card.setup.editor`, `card.setup.editorLabel` ("Visual Studio Code"), `card.setup.actionLabels.open_editor`
  ("Open Visual Studio Code"), and the body asks "Open the lesson folder in Visual Studio Code?".
- **`open_editor_report(path, file)`** → `{opened, editor, label, command, frontmost, ax_trusted, arrange, unfullscreened?, arranged?, frame?}`
  (`open_editor` = its `opened`).

| | without Accessibility (always) | with Accessibility (`AXIsProcessTrusted`) and `MIYAGI_ARRANGE` ≠ 0 |
|---|---|---|
| open | `<cli> -n <dir> -g <file>`, fallback `open -a <App> <dir> <file>` | same |
| front | `open -a <App>`: the editor is frontmost; macOS switches away from a full-screen app to the editor's window | same |
| full screen | the app you were in stays full screen in its own space | its focused window leaves full screen (`AXFullScreen=false`). It is never closed or quit |
| layout | the editor keeps its own size | the editor's window moves to the left 60% of the screen's visible area (`MIYAGI_EDITOR_FRACTION`), so the video docked on the right 40% stays visible |

The Accessibility part runs in a background thread (it waits up to 8 s for the editor's window), so `open_editor` returns
right away. "The app you were in" = the owner of the frontmost normal window that isn't our overlay (`Miyagi`,
`miyagi-overlay`, `Electron`; `MIYAGI_OVERLAY_APPS`) or the editor itself. Trust is read through ctypes, with no prompt; window
moves use `pyobjc-framework-ApplicationServices` (added to `server/pyproject.toml`). Keeping the overlay above full-screen
spaces is the app's job (Electron `setVisibleOnAllWorkspaces(true, {visibleOnFullScreen: true})`).

### "Just teach me" mode: full screen, and where to type

- `open_editor(path, file, fullscreen=True)` opens VS Code as usual (CLI, then `open -a` so it's frontmost). With
  Accessibility, a background thread then maximizes the lesson folder's window in the current Space (`MIYAGI_FULLSCREEN=native`:
  `AXFullScreen=true`, macOS full screen in its own Space), instead of the left-60% layout. `MIYAGI_ARRANGE=0` turns it off.
  The maximized window stops `MIYAGI_DRAWER_W` (436) pt short of the right edge so the overlay's lesson drawer (420 pt
  plus its 8 pt inset) doesn't cover it.
  In both layouts the editor's windows of OTHER `~/miyagi/lessons/*` folders are then minimized (never the learner's own
  projects, never a full-screen window) and the lesson's window is raised last (`put_away_other_lessons`).
  Without Accessibility, `report["fullscreen"]` = "skipped: Accessibility not granted (the learner can press Ctrl+Cmd+F)" and
  the editor stays a normal frontmost window. AppleScript keystrokes or menu clicks need the same permission, so there is no
  permission-free full screen.
- `editor_line_rect(file, line) -> {x, y, w, h, line, source: "ax"} | None`, in top-left global screen points. The technique is
  E6's (server/screen/ax.py): turn the Electron AX tree on once per process (`AXManualAccessibility`); read the focused hidden
  textarea's text, caret (`AXSelectedTextRange`) and rect (it sits on the caret line); map the 500-line AX page to file lines;
  shift by whole lines. That's a handful of AX reads, no tree walk.
- It returns None without Accessibility, while the tree is being built (first call per editor process; ask again after ~1 s),
  when another file is in front (`AXDocument`), when the caret is off-screen, or when the line is outside the window. Then
  use OCR locate. Folding and word wrap shift lines, so treat the result as a hint to cross-check.
- Without Accessibility (or when AX can't see the line), `editor_line_rect` falls back to E6's screen reader
  (`server.screen.locate_line`, PR #9; imported only if present) and returns its full-width row with `source: "screen"`.
  `editor_line_location(file, line)` returns the full answer: `{rect, source: "ax"|"screen"|None, reason, direction?,
  visible_lines?, line_height?}`. When `direction` is "up"/"down", jump with `goto_argv()` and ask again.

## Download the tutorial's own materials (resources.py)

```python
found = find_resources(graph)                 # [{name, url, kind, fetch}]: cheap, cached per video
saved = download_resources(graph)             # ONLY when the learner presses Download
download_summary(saved)                       # "Saved … to ~/miyagi/lessons/<slug>/tutorial." | NO_RESOURCES
```

- **Where links come from:** the video description (watch page, fetched once per video and cached in
  `.miyagi-state/resources/`, or passed as `description=`), plus non-video `sources[]` in the step graph.
- **Kept:** GitHub repos → zip from `codeload.github.com` (no git, so no hooks; a `/tree/<ref>` link keeps its ref);
  GitHub `blob`/raw file links; Colab notebooks (GitHub-backed → raw `.ipynb`; Drive-backed → Drive download, named
  from the server's filename); gists (API); direct `.csv .tsv .json .jsonl .parquet .xlsx .txt .ipynb .py .zip .r .sql .md`;
  Google Drive files and Sheets (CSV export). A file inside a repo that's already being downloaded is skipped. At most 8.
- **Ignored:** socials, playlists, papers, sponsors, personal sites.
- **Safety:** each download ≤ `MIYAGI_DOWNLOAD_MAX_MB` (50). A web page where a file was expected (sign-in or Drive
  confirmation) counts as an error, with the link to open instead. Zips are extracted with no symlinks, no `..`, no `.git/`,
  ≤ 5000 files and ≤ 4×50 MB. Files are written `rw-r--r--`. **Nothing downloaded is run, imported or installed.**
- **Returns:** `[{name, url, kind, path, bytes|files, cached?}]` or `{…, path: None, error}`; `[]` →
  `NO_RESOURCES` ("No downloadable code linked from this video"). A second press reuses what's already there.
- `setup_card(items, resources=found)` adds the `download` action, `setup.resources`, and
  `setup.actionLabels.download` ("Download tutorial files").

Live: Karpathy `kCc8FmEb1nY` → `gpt-dev.ipynb` (the Colab, 39 cells), `karpathy-ng-video-lecture` (5 files),
`karpathy-nanoGPT` (26 files) in 2.2 s. The cached React lesson's video links only nodejs.org, code.visualstudio.com and
react.dev → "No downloadable code linked from this video". `python -m server.workspace.tests.live_resources --fresh`.

## Hero detection

A lesson is the hero if its `lesson.id` is one of the cached hero ids (`lesson-aebc6b8f`,
`lesson-9649077b`, plus `ORCH_HERO_LESSON_IDS`, comma-separated) or one of its sources is the hero
video (`AXXnSzmpyoI`, or the video in `ORCH_LESSON_URL`, which `scripts/miyagi-engine.sh` autostarts).
Its folder is `ORCH_HERO_WORKDIR`, else `demo/pinn-lab`.

## What Claude produces, and the guards

Model: `WORKSPACE_CLAUDE_MODEL` (default `claude-sonnet-5-5`), key from `server.config.get_key("anthropic")`.
Structured output (`SCAFFOLD_SCHEMA` in `scaffold.py`): `stack, summary, setup[], open_file, files[{path, content}],
git{init, default_branch, ops[commit|branch|checkout]}`. Language and tooling come from the step graph, so any topic works.
`setup` commands only go in the README; nothing is installed or run for the learner. The git ops let a lesson
that starts from an existing history (rebase, merge, bisect) get a real repo; they run with a local
`miyagi` identity and never touch global git config.

Applied in code after Claude answers:

- Relative paths inside the folder only, text file types, at most 12 files, 20 KB each, 100 KB total.
  No `README.md` (we write it), `.git/`, `node_modules/`, venvs.
- Files a step's `file_exists` check expects the learner to create are dropped (small `.csv/.tsv/.jsonl`
  data files are the exception). If a step creates a whole project (`my-app/package.json`, `project1/.git`, ...),
  nothing goes inside that folder, and no git history is made when a step runs `git init`.
- **No solution leaks.** Content that already satisfies a check (a `file_contains` on that file, or a
  `screen_contains` outside Terminal/browser apps, since VS Code shows the file) would pass a step before
  the learner did it. Claude gets the offending check ids back once; anything still leaking is dropped.
  README lines (step titles) that would match an editor check are left out too.
- Sample data files are labelled in the README as samples with the tutorial's columns, not the original dataset.

## Tests

```bash
.venv/bin/python -m pytest server/workspace -q                         # offline, fake Claude client
.venv/bin/python -m server.workspace.tests.live_run --fresh            # live: React, git, pandas
.venv/bin/python -m server.workspace.tests.live_run --open pandas      # + open VS Code
.venv/bin/python -m server.workspace.tests.live_setup --fresh          # live: what React / pandas / Blender need on this Mac
```

Live graphs: React (`demo/cache/lessons/516197461c0dacf3.json`), git basics (`8b6203eb5ec8c6f6.json`), and a
hand-written pandas graph (`tests/fixtures/pandas_pokemon.json`, Keith Galli's pandas tutorial, no timestamps).
`tests/fixtures/git_rebase.json` exercises the scripted git history.

## Orchestrator hook (for E4)

In `Session._build` (`server/orchestrator/session.py`):

```python
graph = await self.m.build_lesson(url, goal, workspace.build_workdir(url))
graph.setdefault("lesson", {})["workdir"] = str(await asyncio.to_thread(workspace.prepare, graph, goal))
# load_graph(): open with workspace.open_editor(new_wd, workspace.open_file_for(Path(new_wd))) instead of Workspace.open
```

`config.resolve_workdir` gives `TUT_WORKDIR` priority over `lesson.workdir`, and `scripts/miyagi-engine.sh` exports
`TUT_WORKDIR=demo/pinn-lab`, so with the hook in place, the script should export `ORCH_HERO_WORKDIR` instead
(or `resolve_workdir` should prefer an absolute `lesson.workdir`). Otherwise every lesson still lands in pinn-lab.

## Which window is the learner in? (active.py)

- `active_editor()` → `{folder, folder_name, file, path, dirty, title, miyagi_lesson, source}` for the frontmost VS Code
  window. It uses Accessibility (`AXDocument`, works for any folder), else the window title, "● file — folder" (CGWindowList,
  Screen Recording only; or pass E6's `titles`). A title's folder name resolves to a path only under ~/miyagi/lessons.
- `wrong_folder(lesson_folder, lesson_files)` → `{learner_folder, learner_folder_name, lesson_folder, file, dirty,
  can_adopt, …}` when the learner edits a lesson file (same name) in another folder. The default `lesson_files` is the
  lesson folder's files.
- `adopt_folder(lesson_folder, learner_folder)` ("use this folder") copies the files the learner's folder lacks
  (not .git/.venv/node_modules/tutorial, ≤ 5 MB each). It never overwrites or deletes, and refuses `/`, home, and the
  lessons root itself. It records a redirect, so `prepare()` returns the learner's folder for that lesson from then on.
- New lesson: if the frontmost VS Code window shows an OLDER Miyagi lesson folder, `open_lesson_editor` reuses it
  (`code -r <new folder>`). Windows outside ~/miyagi/lessons are never reused. If a window already has the new folder,
  plain `code <folder>` focuses it.
- The active app comes from `lsappinfo` (Launch Services, live). `NSWorkspace.frontmostApplication` goes stale in the
  engine (no AppKit run loop).

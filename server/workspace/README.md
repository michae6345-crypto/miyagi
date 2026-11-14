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
  Returns `[]` with no key or on API failure (the lesson still runs).
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

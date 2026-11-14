# server/workspace: one folder per lesson, starter files, VS Code

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

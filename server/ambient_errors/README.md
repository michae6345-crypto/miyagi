# server/ambient_errors: explain this error (ambient help, part 1)

The engine side of `shared/contracts/AMBIENT-HELP.md` section 1: spot an error on screen outside a lesson, then
explain it when the learner presses Explain. The wiring (commands, frames, ticks) is `server/orchestrator/ambient.py`.

| File | What it does |
|---|---|
| `detect.py` | Pure parser: rows of one window -> error blocks (`python_traceback`, `notebook_cell`, `js_error`, `compiler`, `shell_exit`), with title, first lines, file:line, the command typed before it, the missing module. Tolerant of OCR noise (no indentation, lost quotes, `NameFrror`) |
| `watcher.py` | `scan(obs, muted)`: which rows of a frame are read (a terminal app; VS Code's terminal panel, or a whole notebook; a browser's notebook or console `Uncaught`; never a muted / private app or Miyagi). `ErrorWatcher`: on screen 1 s before `error.seen`, one id per app + kind + title + file:line, `again` when printed again, one peek per 5 s, `clear` when gone from its app for 3 s, held 10 min at most, dismissed ids quiet until they go and come back |
| `text.py` | `for_app` (home as `~`, secrets as `••••`) for `error.seen`; `for_model` (also every path cut to its file name, or the path inside a package) for Explain |
| `explain.py` | `context()` (title, lines, at most 6 source lines read on this Mac or the command before it; never pixels), `local_answer()` (a missing package on the curated list: no model call, with the Install row and `pip install`), `explain()` (one Haiku call, `coach.explain_error` in `server/models.py`, through the guarded coach client; answer clamped, `command` only through the coach's allowlist, `diff` only for the error's file) |
| `../ambient_cap.py` | `shared_cap()`: 20 model calls per rolling hour on this Mac, for Explain and How-do-I together (`help.ask` should take from it too). Call times only, in `<state dir>/ambient_calls.json` |

## Wire

- `ambient.set {errors, mutedApps}`: per connection, off until the app turns it on. While any connection has it on
  and no lesson runs (`phase` not building / preflight / active), `session._sync_screen_soon` keeps the screen reader
  running and `Engine.on_screen` sends its frames here instead of to the lesson.
- `error.seen` goes only to connections with errors on, with `hub.send_to` (not in `/events` history, never logged).
  A lesson start clears every shown peek; nothing is spotted while it runs.
- `error.explain {id, reqId}`: `{id, pending}` at once, then the answer: from memory for an id explained before, from
  this Mac when it knows, else one model call counted against the cap (`{error: "cap", retryInS}` when full; a call
  that never reached a model, `offline`, is not counted). An id no longer held answers `{error: "gone"}`.
- `error.dismiss {id}`: forgotten (lines and explanation), no reply.

Not done here: `app_dialog` (an app's error sheet from the accessibility tree) is never sent yet.

## Tests

```bash
env -u ANTHROPIC_API_KEY -u GEMINI_API_KEY .venv/bin/python -m pytest server/ambient_errors server/orchestrator/tests/test_ambient_errors.py -q
python -m server.ambient_errors.tests.make_error_fixtures [name ...] [--png DIR]   # re-record the OCR fixtures (macOS)
```

`tests/fixtures/*.ocr.json` are recorded Apple Vision reads of a rendered window per kind (Python traceback, Node
stack, tsc in VS Code's terminal panel, pip, npm, git, a Jupyter cell in VS Code, and a clean run). The exact text of
each is in `make_error_fixtures.FIXTURES` (the Accessibility path). The model client is always a fake.

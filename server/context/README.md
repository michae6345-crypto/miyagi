# server/context: lesson memory

Short notes of what the engine saw and did in a lesson, kept on this Mac, so the coach stops re-asking and reacts to
what happened before ("you already installed torch", "this NameError came back after the fix", "you skipped setup").

```python
from server.context import ContextStore, FileScanner, what_we_know, wipe_all
st = ContextStore(lesson_id, session=engine_session)
st.add("check", "s2", "s2 checks: 1 passed, 1 not yet (Run nn.py)", {"failing": ["Run nn.py"]}, step="s2")
FileScanner(lesson_id).scan(workdir)              # incremental: only new / changed files are outlined
block = what_we_know(lesson_id, "s2", purpose="explain", budget=1200)
prompt += f"WHAT WE KNOW SO FAR:\n{wrap('memory', block)}"   # always as untrusted data
```

| file | does |
|---|---|
| `store.py` | one JSON-lines file per lesson at `~/miyagi/state/context/<lesson>.jsonl` (0600, folder 0700). Entry: kind, source, time, 1-3 line summary, key facts, step, session, hash. Redacted with `server.screen.privacy.redact` (secrets via `redact_secrets`, plus emails / phones / cards) before saving. Private apps (`screen/privacy.py`) are never summarized. Deduped per slot (kind + source + step). Capped at 400 entries / 256 KB per lesson and 40 lessons; a lesson untouched for 14 days goes (`prune`). |
| `extract.py` | rule-based summaries, no model: a file outline (Python by syntax tree, notebooks by cell incl. error outputs, JS/TS imports and functions), error lines, app + window title, check results, a card's title + first sentence, setup progress, learner actions |
| `scan.py` | incremental workspace scan: `(mtime, size)` unchanged = reused without a read; same content hash = reused without an outline. Skips `.venv`, `node_modules`, `.git`, hidden folders, secret files (`.env`, keys), binaries; 200 KB per file, 300 files, 3 MB a scan |
| `recall.py` | the newest note per slot, this step's first, then newest first, whole lines up to the budget (1200 characters, ~300 tokens). Per purpose: the judge never hears what a model said |

## Wiring (server/orchestrator/context_memory.py)

- **Saved from** `LessonSession.emit` (cards, off-tracks, check rows, step passes, setup progress, `screen.seen`),
  `LessonSession.action` (Skip setup, I have it, Run it for me ...) and file saves / step starts (a scan in a thread).
- **Model summaries only piggyback:** the coach's own cards (diagnose, explain, answer) are the model summary; no
  extra paid call is ever made for memory.
- **Read by** `coach.explain` (`context["memory"]`), `coach.diagnose` and `coach.judge_step` (`memory=`), each inside
  `<untrusted source="memory">` with DATA_RULE in the system prompt.
- **Expires:** a completed lesson's notes go at `lesson.ended`; `prune()` at each `lesson.ready`.
- **Delete my data:** the app's Settings > Privacy delete sends a `config.keys` with every key empty; when the engine
  held a key before, `wipe_all()` removes every lesson's notes and scan cache (orchestrator/main.py). App follow-up:
  send an explicit wipe command, and list `PRIVACY_FACT` in the privacy panel's facts.

Off with `MIYAGI_CONTEXT_MEMORY=0`; under pytest off unless a test sets it to `1` (replay fixtures are keyed by prompt
text). `MIYAGI_CONTEXT_DIR` moves the folder (tests).

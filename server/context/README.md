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
- **Saved as intent:** a button press is noted before its action runs, so it reads "asked to download the tutorial
  files", "pressed Apply fix"; what really happened comes from the outcome events (setup.progress done/ok, check rows).
- **Expires:** a completed lesson's notes go at `lesson.ended`; `prune()` at each `lesson.ready`.
- **A fresh start forgets the earlier run:** `LessonSession.load_graph` calls `lesson_loaded`, which wipes the lesson's
  notes and scan cache unless the Resumer is restoring a saved place (`s.restoring`: an engine restart's save, the
  resume card's Continue). End then start again, Start new, a curated fresh folder and every Demo take start empty.
- **Delete my data:** `wipe_all()` removes every lesson's notes and scan cache and bumps the wipe generation
  (`store.generation`), so a `FileScanner` still holding outlines in memory drops them instead of writing them back.
  Triggered by the v2 command `data.delete` (listed in `engine.hello.capabilities`), and by a `config.keys` whose BYOK
  keys (anthropic, gemini, elevenlabs) all went empty while the engine held one (`miyagiToken` / `miyagiCloud`, which
  the app folds into every send and keeps, are ignored). App follow-ups: `settings:delete` sends `data.delete` when the
  engine lists it (a cloud-only learner's all-empty keys look like any connect), and the privacy panel lists
  `PRIVACY_FACT`.

Off with `MIYAGI_CONTEXT_MEMORY=0`; under pytest off unless a test sets it to `1` (replay fixtures are keyed by prompt
text). `MIYAGI_CONTEXT_DIR` moves the folder (tests).

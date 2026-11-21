# eng-harden (ROADMAP 5.3 engine hardening + 5.2 secret redaction)

**Status:** implemented, pushed, not merged · **Branch:** `claude/eng-harden` (from `origin/integration/live`) · **Engine + companion + `tut`** (no app files, no port)

## Goal
The engine on this Mac answers only this Mac, only its own clients may change a lesson, dev routes never ship, and no
key or token on the learner's screen or in their files ever leaves in a model request.

## What changed
- **Bind** (`server/orchestrator/main.py` `run()`): 127.0.0.1 unless `--host` / `ENGINE_HOST` says otherwise; an empty
  `ENGINE_HOST` is now loopback too (before, `ENGINE_HOST=` passed `""` to uvicorn).
- **Token on writes**: with `MIYAGI_ENGINE_TOKEN` set (the app's per-launch token), every POST/PUT/PATCH/DELETE needs
  a matching `X-Miyagi-Token`, from this Mac too: `/ingest`, `/vscode/event`, `/end`, `/stage/*`, `/debug/*`,
  `/demo/*` (403 otherwise). The WebSocket already required it; requests from another machine still need it on every
  route. Loopback GETs (`/health`, `/state`, `/library`, `/progress`) need none. There is no HTTP library write
  (library.start is a WebSocket command, covered by the WebSocket token). A token-less `/vscode/event` (a companion
  older than 0.0.7) is named once in the log. Without `MIYAGI_ENGINE_TOKEN` (an engine started by hand, every test
  and script) nothing changes: `curl -X POST localhost:8787/end` still works.
- **Token file** (`server/engine_token.py`): `run()` publishes the token (the app's, else a fresh random one per
  launch) to `~/.miyagi/engine-tokens/<port>.json` (`{token, pid, port}`, dir 0700, file 0600,
  `MIYAGI_ENGINE_TOKEN_DIR` moves it) and removes it on exit. One file per port, so a stage runner's engine never
  replaces the main one. A file whose pid is gone is ignored everywhere. Readers: the companion, `tut run`
  (`cli/tut/sinks.py`, only for a loopback ingest URL), the dev CLI (`server/orchestrator/client.py`, also honours an
  exported `MIYAGI_ENGINE_TOKEN`).
- **Dev routes off in release**: `/debug/*`, `/demo/*` and `GET /events` answer 404 unless `MIYAGI_DEBUG_ROUTES=1`
  or `DEMO=1`. `/events` returns the hub's whole history (cards, selections, run and terminal output) and, as a
  loopback GET, needs no token, so a local program the WebSocket refuses could otherwise read the session there.
  `localEngine.ts` sets neither (and never starts with DEMO=1). Turned on for `scripts/stage.py`, `scripts/rehearse.py`
  and `scripts/miyagi-demo.sh` (DEMO.md's `/debug/goto/7` backup). The dev CLI prints a hint on a 404.
- **VS Code companion 0.0.7** (`vscode-ext/extension.js`):
  - events go only to an `engineUrl` on this Mac (`http://127.0.0.1|localhost|[::1]`); any other URL, e.g. from a
    repo's `.vscode/settings.json`, gets nothing (it would have received file names, selections, terminal output);
  - events carry `X-Miyagi-Token` for the engine on that port;
  - its own API requires one of the live engines' tokens on every route but `GET /` and `GET /health` while any live
    engine has published one (401 `token_required`); none published (older engine): open to loopback as before;
  - requests from a non-loopback remote address are refused (403 `not_loopback`).
  - Engine side: `server/workspace/vscode_ext.py` sends `X-Miyagi-Token` on every call (`set_link_token` from
    `run()`; another process reads a live engine's token file). Old companions ignore the header.
- **Secret redaction** (`server/redact.py`, 5.2): `redact_secrets` replaces known token formats (Anthropic / OpenAI
  `sk-`, Google `AIza`, GitHub `ghp_`/`github_pat_`, Slack `xox?-`/`xapp-`, Stripe, ElevenLabs, AWS `AKIA`,
  HuggingFace `hf_`, npm `npm_`, GitLab `glpat-`, PyPI `pypi-`, JWTs, PEM private keys, `scheme://user:password@`,
  `Bearer ...`, `Basic <base64 of user:password>`), long values after KEY/TOKEN/SECRET/PASSWORD/AUTH names anywhere
  in a line (a command `API_KEY=... python app.py`, `HF_TOKEN=...;`, a URL query `?apiKey=...&x=1`, a header
  `"x-api-key: ..."`, a flag `--token=...`), and the exact keys the engine holds, with `[secret]`. `.env` files (and `.env.*`, `.envrc`) keep their names with every value hidden; `.npmrc` hides everything
  after `=` on every line and `.pypirc` everything after `=` or `:`; `.netrc`, `.pgpass` and key files are withheld whole
  (`redact_file_text`). Every pattern is linear in the text (names before `=` are bounded and possessive): a 100 KB
  adversarial line redacts in well under 0.2 s. It errs toward hiding: an identifier-like string with a digit after a
  key-sounding name (`const key = 'user_profile_settings_v2'`) is redacted too. Wired at the boundaries, never into
  grading:
  - screen OCR blocks and AX text (`server/screen/privacy.redact`, which every reader path already used);
  - every coach request (`server/coach/llm._request` redacts the user message; `common.number_lines` too) and
    recorded fixtures (`COACH_RECORD_DIR`);
  - every screenshot that leaves the Mac blacks out the rows whose OCR / AX text held a secret: the screen describe /
    where calls (`server/screen/describe.py`), the target picker (`server/screen/target.py`), the scene look
    (`server/orchestrator/scene_watch._mask_args`, beside private apps' windows) and the diagnose / actions screenshots
    (`server/coach/screen.ScreenContext.pil`, so `overview()` and `crop()` carry the mask);
  - "Explain this" selections from VS Code and the drawer (`server/orchestrator/selection.py` via
    `server/workspace/core.text_for_model`): the card title, the coach and the session record see the redacted text;
  - a step file that is a secret file (`.env`, `.env.local`, `.npmrc` ...) reaches diagnose, explain, diagrams and
    "Explain this" as its names with every value hidden (`session._coach_excerpt` / `_for_coach`), and Do it for me's
    numbered file too (`coach/actions.do_it_for_me` via `redact_file_text`); grading and patching read the real text;
  - `coach/hints.apply_fix` refuses a patch whose new text holds more `[secret]` than the file did (the coach echoing
    `api_key="[secret]"` would write the placeholder into the learner's file): no patch, the fix-it-by-hand card;
  - web grounding (`coach/web.gather` and `serp_url`): the learner's question, the error line and the symbol go
    through `search_safe` (redacted, `[secret]` dropped) before they become DuckDuckGo search words.
- **Tests**: `server/orchestrator/tests/test_hardening.py` (11), `server/tests/test_redact.py` (78),
  `cli/tests/test_engine_token.py` (2), 3 new companion tests in `vscode-ext/test/extension.test.js`. Stale tests fixed:
  `test_session.py::test_ws_and_ingest_roundtrip` and `::test_post_end_endpoint`, and
  `test_vscode_ext.py::test_engine_route_records_events` patch `host_allowed` (TestClient's Host is `testserver`), as
  `server/sessions/tests/test_sessions.py::_restarted_engine` does; the WS test now reads `engine.hello` first.
  The lane task listed "test_session.py ws tests (5)": only those 2 failed because of the Host header (fixed, with the
  companion test above). The other test_session.py failures are not Host-related and still fail, identically on
  `origin/integration/live` (see Notes).
  `server/conftest.py` points `MIYAGI_ENGINE_TOKEN_DIR` at a temp folder for every server test.

## Core requests
1. **App (Adrian, `app/src/main/localEngine.ts` + the engine link)**: generate a per-launch token
   (`crypto.randomBytes(32).toString('base64url')`), pass it as `MIYAGI_ENGINE_TOKEN` in the engine's env, and send
   `X-Miyagi-Token` on the WebSocket and on `features/presenter.ts`'s `POST /stage/{cmd}`. Until then the engine runs
   token-less exactly as today (only the companion link token is active).
2. **Before (1) ships**: install / update the companion to 0.0.7 (the `install_companion` fix). A 0.0.6 companion's
   events are refused by an engine that has `MIYAGI_ENGINE_TOKEN` (the engine logs it once).
3. **eng-cloud-client (`server/config.py`)**: add `MIYAGI_ENGINE_TOKEN` to `safe_env()` (eng-wire core request 2;
   main.py already pops it at import).
4. **Michael's run-live engine / `update-engine.sh`**: export `MIYAGI_DEBUG_ROUTES=1` where `/debug/pass` or
   `/debug/goto` are used on the live engine (desktop tests). `scripts/miyagi-engine.sh` is left alone in case the
   installer's launcher wraps it.

## Notes
- Known pre-existing failures on `origin/integration/live`, unchanged here: `test_session.py`
  `::test_build_progress_ticks_with_real_stages_then_fails_humanly` and `::test_build_success_still_loads_the_lesson`
  (payload shape drift: `detail`, `phases`), `test_coach::test_models_by_purpose`, and the others listed in the lane
  task.
- `GET /state` (session state for the dev CLI's simulator) is still a token-free loopback GET; it holds less than
  `/events` did (no history), but a later round could gate it on the token when one is set.
- Screenshots still carry pixels: on every path that sends one (describe, target picker, scene look, diagnose /
  actions) only rows whose OCR / AX text held a secret are masked, so a key OCR misread can still appear in an image
  sent to Claude vision.
- The companion link token is the app's `MIYAGI_ENGINE_TOKEN`, which is also the WebSocket token, and
  `vscode_ext._http` sends it to whatever answers on 127.0.0.1:8791-8799. A process from another macOS account that
  binds those ports first could collect it, which defeats the 0600 token file. A later round could use a separate
  random link token for engine-to-companion calls (not done here: it changes the companion's token check).
- `cli/tests/test_engine_token.py` fails to collect with the run-live venv (its editable `tut` points at
  `run-live/cli`); it passes with `PYTHONPATH=cli`. An environment issue, not this lane's.
- Redaction errs toward hiding mid-line too: `tokenizer_path=bert-base-uncased-v2` reads `tokenizer_path=[secret]`.

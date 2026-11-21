# errors (A7)

**Status:** fix round 1 done (7 review fixes), typecheck green, stage shots taken (`agents/shots/A7-*.png`). Draft PR #169 into `adrian/shell` · **Priority:** P1 · **Port:** 5192 · **Branch:** `michael/app-errors` (from `michael/app-core-v2`)

## Goal
Every way a lesson can stall, said calmly from the island: the engine reconnecting and then offline, the network gone,
the AI busy, a build that failed, VS Code closed, no kernel, and the crash consent card at launch. No hue anywhere
(a white ring, the gray arc, a white tick for a recovery: never green), one white primary per card.

## Owns
- `app/src/renderer/src/features/errors/**` (index, store, lines, cards, parts, scrub, web)
- `app/src/main/features/errors.ts`
- `app/mock/scenarios/errors.json`
- `app/agents/errors.md`

## Island modes (agents/README.md table)
| Priority | Mode | What | Mockup |
|---|---|---|---|
| 90 | `err-crash` (440) | "miyagi closed unexpectedly last time." Only with no lesson and no build; a lesson starting hides it (main keeps the report, next launch asks again) | Err-CrashConsent |
| 72 | `err-engine-offline` (296) | after 5 failed tries: Restart engine (`engine-local:restart`) / Copy details; a Terminal engine gets "Try again" and "Restart it in Terminal" | Err-EngineReconnect 02 |
| 66 | `err-editor-closed` (352) | `blocker editor_closed` or `lesson.paused editor_closed`: "Your place is saved." Reopen in VS Code (`open_editor`) / End lesson for now; Esc folds it into the pill line | Err-VSCodeClosed |
| 62 | `err-build-failed` (520) | `lesson.building failed` (not `silent`): source row, reason, Try transcript only (`learn_url {transcriptOnly}`), library rows (`library.start`, only with the capability and a valid id); no transcript alternative = "Find another video" (opens the launcher). The source link stands in for a transcript option only when the engine sent no `alternatives` at all (an older engine) and the failCode is not `no_captions` | Err-LessonBuildFailed |
| 58 | `err-limit` (336) | `config.status.cloud === 'quota'`, **v2Cloud only**: off in Electron, `&v2Cloud=1` in the stage. See plans (`openAccount('upgrade')`) / Use your own API key (`openSettings('account')`) | Err-OfflineAndLimits |
| 7 | `err-reconnecting` | "Reconnecting to engine  N of 5" (main's LinkInfo failures + 1), then "Back. Picking up where you were." for 3.5 s | Err-EngineReconnect 01 |
| 7 | `err-blocker` | "VS Code closed. Lesson paused.  Step 3 of 6", "Opening VS Code", "Back on Build the model"; kernel: "Pick a kernel so your cells can run  [Select Kernel ▷]" | Err-VSCodeClosed, Err-KernelInContext |
| 6 | `err-net-offline` | `navigator.onLine` false or `blocker network`: "Offline. Steps work, checks wait.", then "Online. Checking your work now." | Err-OfflineAndLimits |
| 6 | `err-busy` | `status busy`: "Busy right now. Retrying in  20s" (counts down from `retryInS`) | Err-OfflineAndLimits |

"5 tries" is a UI threshold only: main keeps retrying, and the card goes the moment the link opens. Reconnecting shows
only after the engine was connected once this launch (a first-launch "can't reach" stays the pill's own line).

## Copy details and crash reports (BUILD-PLAN section 6)
- `scrub.ts` (pure, shared with main): API keys (`sk-ant-`, `sk-`, `AIza`, `xi-`, `sk_`, our `mi_` token), `postgres://` URLs, Bearer tokens, key/token query params, emails, home paths (`/Users/<name>`, `/home/<name>`, `C:\Users\<name>` become `~`), long opaque runs, control characters; capped.
- Copy details: `buildDetails()` writes only the allowlisted fields (app, system, engine link, engine state, engine version, contract, lesson title, step N of M, status, last error, time), each scrubbed; main's `diagnostics:copy` scrubs again, caps and writes the clipboard. No logs, no code, no paths.
- Crash: `main/features/errors.ts` writes `userData/errors/session.json` (with its `pid`) at launch and removes it on `will-quit`; found at the next launch = no clean quit, unless its pid is still alive (`process.kill(pid, 0)`, EPERM counts as alive): then this is a second instance (Windows packaged exits in windows.ts right after this setup, or a second copy from the dmg), which neither calls it a crash, nor overwrites the marker, nor asks. Only the overlay window (`#/overlay` or no hash) asks `errors:crash-pending` and sends `errors:context`, so a feature window with other lesson state can't overwrite the marker. The report: app version, OS version, last start, lesson name and step (from `errors:context`, sanitized), and the error log this app wrote (`render-process-gone`, `child-process-gone`, `uncaughtExceptionMonitor`, scrubbed as written). `crashReports` 'never' drops it, 'always' saves it silently, 'ask' (default) waits for the card. Saved reports go to `userData/crash-reports/` (mode 600). Nothing is uploaded.

## Test
`npm run typecheck` (green). Stage: `npm run dev:web -- --port 5192` then
`http://localhost:5192/?scenario=errors&size=1440x900&clean&err=<state>`, state one of
`reconnect` (holds at 2 of 5), `back` (2 of 5, then Back.), `engine-offline` (press Restart: the fake engine comes back), `offline`, `online`, `busy`, `kernel`, `editor-closed` (press Reopen: Opening, then Back on Build the model), `build-failed`, `limit` (add `&v2Cloud=1`), `crash`.
`&engine-local=external` with `engine-offline` shows the Terminal variant. `?err=` sends a dev-only `dev.err.<state>` trigger to the inline mock; every segment is err-prefixed except the scoped step segment `step_err` (the mock only scopes `@` triggers to segments named `step*`).

## Deviations (and why)
- **Crash consent says Save, not Send** ("Save a crash report on this Mac? Nothing is sent.", Don't save / Save report, "Always save without asking"): crash upload is deferred and reports are local only (BUILD-PLAN section 1 and 6), so the mockup's "Send report" would not be honest. View report expands the scrubbed text inside the card. The caption is "Saved on this Mac only.", not "Asked once. Change it later in Settings, Privacy.": Settings has no crashReports control yet (Core request 5), and an unanswered card asks again at the next launch.
- Restart engine and Reopen in VS Code wait at most 20 s: a restart whose link never opens says "Restart did not work. Quit and reopen miyagi.", and an `open_editor` the engine ignores drops "Opening VS Code" and brings the card back.
- Build-failed card is 520 wide (`pill.maxCardWidth`), not the mockup's 560.
- Editor-closed: the pill line and the card are one island (the card is the pill grown), so the card's header carries the pill line (ring, "VS Code closed. Lesson paused.", Step N of M, Esc) instead of the bonsai and lesson title. The file chip ("first-neural-net/mnist.ipynb, 3 cells") is left out: no contract field carries it (Core request 1).
- Limit card: "See plans" and "Free checks reset tomorrow" instead of the mockup's [PLAN NAME] / [RESET TIME] placeholders.
- Pill lines are 34 high (core `pill.height`; the mockups' 40 is wave 2).
- Kernel pill line: the chip is a label pointing at the real control (`Select Kernel ▷`), not a button; the card footer ("Watching for a kernel to start") is A2's.

## Shots (fix round 1)
Stage on 5192, `?scenario=errors&size=1440x900&clean&err=<state>`, taken in headless Chromium over CDP (no windows opened):
`agents/shots/A7-reconnect.png`, `A7-back.png`, `A7-engine-offline.png`, `A7-engine-offline-external.png` (`&engine-local=external`),
`A7-offline.png`, `A7-online.png`, `A7-busy.png`, `A7-kernel.png`, `A7-editor-closed.png`, `A7-editor-closed-opening.png` (after Reopen),
`A7-build-failed.png`, `A7-limit.png` (`&v2Cloud=1`), `A7-crash.png`.
Seen against the mockups: one white primary per card, ring glyphs with no hue, recovery lines with a white tick, Esc keycaps, copy as specified.
Gaps seen in the shots: the build-failed card shows no library rows in the stage (the inline mock's hello does not grant
`library.start`, so the rows are correctly hidden); the editor-closed header truncates "VS Code closed. Lesson paused." next to
"Step 3 of 6" at 352 wide; the lesson panel on the right says "Step 3 of 3" while the island says "of 6" (the panel counts
loaded steps, the island the outline: not this lane's code).

## Not verified
- Electron: the crash marker (and its pid check), clipboard, `engine-local:restart`, the 20 s timeouts and `render-process-gone` paths are typechecked only.
- The library rows on the build-failed card were not seen rendered (see Shots).

## Core requests
1. **contract** (Michael): `blocker` / `lesson.paused` for `editor_closed` could carry the file to reopen (`file?: string` relative to the lesson folder, `detail?: string` like "3 cells") for the Err-VSCodeClosed chip and "Opening mnist.ipynb". Until then the card has no chip and the line says "Opening VS Code".
2. **core** (`common/wire.ts`): a typed dev-only trigger (`{ type: 'dev.trigger', payload: { name } }`, dropped by main's allowlist) so stage switches like `?err=` don't cast an `Outgoing`. Today `features/errors/web.ts` casts `dev.err.<state>`; it runs only in the browser stage with the inline mock.
3. **core / pill** (`main/features/pill.ts` or core): an `engine-link:get` that returns the LinkInfo without forcing a reconnect, so a window loaded mid-outage knows the link state at once. Today errors reads `feat:engine-link` changes plus core's `connected`.
4. **core**: one `v2Cloud` flag (registry or prefs) for A7 and A9. Today `err-limit` reads `?v2Cloud=1` in the stage and is off in Electron.
5. **A4 settings**: Privacy should show the `crashReports` choice (ask / always / never). Today "Always save without asking" has no way back. Once it ships, the crash caption can say "Change it later in Settings, Privacy." again.
6. **E2/E3 engine**: send `lesson.building {failed, failCode, failReason, alternatives}` with `alternatives[].url` on the transcript option (or `source.url`), library alternatives only with ids that pass `^[A-Za-z0-9_-]{1,64}$`, and `blocker {kind:'network'}` / `status {state:'busy', retryInS}` as specified; `editor_closed` blockers with an `action` of at most 3 words.
7. **integrator**: `npm run dev` restarts that kill Electron leave the crash marker, so the next dev launch asks about a "crash". If that's noisy, skip the marker when `!app.isPackaged` (one line in `main/features/errors.ts`), or set crashReports to never on dev Macs.

## Notes
- Esc closes only our card that is on the island (`visible` in store.ts); the crash card's Esc is "Don't save".
- Reads core/lesson (`blockers`, `paused`, `busy`, `buildFailed`, `localEngine`, `keyStatus`, `hello`) and core prefs; edits no other feature's store.
- The lane was claimed with the draft PR; the coordination email to Adrian was not sent from this session.

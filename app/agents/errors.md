# errors (A7)

**Status:** fix round 2 done (5 review fixes), typecheck green, stage shots taken (`agents/shots/A7-*.png`; build-failed and editor-closed retaken in round 2). Draft PR #169 into `adrian/shell` · **Priority:** P1 · **Port:** 5192 · **Branch:** `michael/app-errors` (from `michael/app-core-v2`)

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
| 62 | `err-build-failed` (520) | `lesson.building failed` (not `silent`): source row, reason, Try transcript only (`learn_url {url, transcriptOnly}`) only when `alternatives[]` has an entry of kind `transcript`; library rows (`library.start`, only with the capability and a valid id). No `alternatives` at all (today's engine, which reads no `transcriptOnly` flag) or none of kind `transcript` = "Find another video" only (opens the launcher, never closes it); we never guess a transcript option | Err-LessonBuildFailed |
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
- Engine offline treats a local engine in state `off` (main does not manage it: dev without MIYAGI_AUTOSTART, DEMO=1, a non-local URL) like `external`: the card says Try again and "Restart it in Terminal.", not "Quit and reopen miyagi.".
- Restart engine and Reopen in VS Code wait at most 20 s: a restart whose link never opens says "Restart did not work. Quit and reopen miyagi.", and an `open_editor` the engine ignores drops "Opening VS Code" and brings the card back.
- Build-failed card is 520 wide (`pill.maxCardWidth`), not the mockup's 560.
- Editor-closed: the pill line and the card are one island (the card is the pill grown), so the card's header carries the pill line (ring, "VS Code closed. Lesson paused.", Esc; "Step N of M" moves to a mono line under the title so the header never truncates at 352) instead of the bonsai and lesson title. The file chip ("first-neural-net/mnist.ipynb, 3 cells") is left out: no contract field carries it (Core request 1).
- Limit card: "See plans" and "Free checks reset tomorrow" instead of the mockup's [PLAN NAME] / [RESET TIME] placeholders.
- Pill lines are 34 high (core `pill.height`; the mockups' 40 is wave 2).
- Crash detection: a leftover marker counts as a crash only when the app is packaged and something was logged since that launch started (a window or child process went away, or main threw). Force Quit, SIGKILL, power loss and `npm run dev` restarts leave a marker with nothing logged, so it is dropped silently and no card opens (the desktop test protocol force-quits miyagi before every test).
- Kernel pill line: the chip is a label pointing at the real control (`Select Kernel ▷`), not a button; the card footer ("Watching for a kernel to start") is A2's.

## Shots (fix rounds 1 and 2)
Stage on 5192, `?scenario=errors&size=1440x900&clean&err=<state>`, taken in headless Chromium over CDP (no windows opened):
`agents/shots/A7-reconnect.png`, `A7-back.png`, `A7-engine-offline.png`, `A7-engine-offline-external.png` (`&engine-local=external`),
`A7-offline.png`, `A7-online.png`, `A7-busy.png`, `A7-kernel.png`, `A7-editor-closed.png`, `A7-editor-closed-opening.png` (after Reopen),
`A7-build-failed.png` (round 2: with the two library rows), `A7-limit.png` (`&v2Cloud=1`), `A7-crash.png`.
Seen against the mockups: one white primary per card, ring glyphs with no hue, recovery lines with a white tick, Esc keycaps, copy as specified.
Round 2: `err_build_failed` now sends an `engine.hello` with `library.start` first, so the shot shows both rows under
"Or start a library lesson"; the editor-closed header is ring + "VS Code closed. Lesson paused." + Esc with no truncation,
and "Step 3 of 6" is a mono line under the title. Gap still seen: the lesson panel on the right says "Step 3 of 3" while the island says "of 6" (the panel counts
loaded steps, the island the outline: not this lane's code).

## Not verified
- Electron: the crash marker (and its pid check), clipboard, `engine-local:restart`, the 20 s timeouts and `render-process-gone` paths are typechecked only.
- The busy line's countdown kept out of the live region (`aria-hidden` on the mono count) was not checked with VoiceOver.

## Core requests
1. **contract** (Michael): `blocker` / `lesson.paused` for `editor_closed` could carry the file to reopen (`file?: string` relative to the lesson folder, `detail?: string` like "3 cells") for the Err-VSCodeClosed chip and "Opening mnist.ipynb". Until then the card has no chip and the line says "Opening VS Code".
2. **core** (`common/wire.ts`): a typed dev-only trigger (`{ type: 'dev.trigger', payload: { name } }`, dropped by main's allowlist) so stage switches like `?err=` don't cast an `Outgoing`. Today `features/errors/web.ts` casts `dev.err.<state>`; it runs only in the browser stage with the inline mock.
3. **core / pill** (`main/features/pill.ts` or core): an `engine-link:get` that returns the LinkInfo without forcing a reconnect, so a window loaded mid-outage knows the link state at once. Today errors reads `feat:engine-link` changes plus core's `connected`.
4. **core**: one `v2Cloud` flag (registry or prefs) for A7 and A9. Today `err-limit` reads `?v2Cloud=1` in the stage and is off in Electron.
5. **A4 settings**: Privacy should show the `crashReports` choice (ask / always / never). Today "Always save without asking" has no way back. Once it ships, the crash caption can say "Change it later in Settings, Privacy." again.
6. **E2/E3 engine**: send `lesson.building {failed, failCode, failReason, alternatives}` with `alternatives[].url` on the transcript option (or `source.url`), library alternatives only with ids that pass `^[A-Za-z0-9_-]{1,64}$`, and `blocker {kind:'network'}` / `status {state:'busy', retryInS}` as specified; `editor_closed` blockers with an `action` of at most 3 words.

## Notes
- Busy line: the 1 s countdown runs only while `busy.retryInS` is set, and its mono count is `aria-hidden`, so screen readers hear "Busy right now. Retrying in" once, not every second.
- Esc closes only our card that is on the island (`visible` in store.ts); the crash card's Esc (and the round close button) only hides it for this launch, so the report is asked about again next launch; only "Don't save" discards it.
- Reads core/lesson (`blockers`, `paused`, `busy`, `buildFailed`, `localEngine`, `keyStatus`, `hello`) and core prefs; edits no other feature's store.
- The lane was claimed with the draft PR; the coordination email to Adrian was not sent from this session.

## Round 3 (surfaces lane, michael/app-surfaces-feel)

**Landed**
- `gate.ts`: the lesson panel follows the link. `wait` (reconnecting, offline, busy): Check my work becomes "Check when miyagi is back" / "Check when back online" / "Check when miyagi is free"; pressed, it queues (spinner, the button reads "Queued" and the caption says once when it runs: "Runs when miyagi is back" / "Runs when you are back online" / "Runs when miyagi is free") and sends `check_step` by itself once the gate is ok. `paused` (engine offline, VS Code closed, onboarding recovery card): the panel body dims to 50 % and is `inert`, its primary disabled with "Paused until miyagi restarts", so the card's action is the only primary. Help tiles wait with it, captioned from the gate (`Gate.help`: "Help waits until miyagi is back", "Help waits until you are back online", "Help waits a moment", "Help waits until miyagi restarts"); Watch waits only when the Mac is offline. While paused the panel's keys line (Esc hide) dims and goes inert with the body, so the card's Esc keycap is the only live Esc hint. Captions spring in and out.
- Esc: an error card on the island counts as open for the panel (drawer `othersOpen`), so one Esc closes only the card. The engine-offline card folds into a persistent `err-stopped` pill line "miyagi stopped responding [Restart]" (Restart brings the card back); the outage is never hidden. Crash card: Esc = Don't save (keycap on that button), confirmed on the pill: "Not saved"; Save says "Report kept on this Mac".
- Copy: "miyagi" instead of "engine" ("miyagi stopped responding", "Restart miyagi", "miyagi offline"), "Reconnecting to miyagi  try 2 of 5" and "miyagi is busy. Trying again in 18 s" in the body font (mono N of M is the step counter's only), titles without trailing periods, "Your own key" on the limit card. Crash: "Keep a report so you can share it if it happens again? It stays on this Mac.", no duplicate footer, View report is a neutral text button.
- Cards enter calmly: header, title, body and each block settle in 40 ms apart on the house spring (opacity only with reduced motion). Pill lines fade up.

**Stage:** `?scenario=errors&err=<offline|reconnect|busy|engine-offline|crash>&clean`. Shots: `/Users/tripi/sand hacks/miyagi-v2/screens/round3/surfaces-err-*.jpg`.

**Core requests (round 3)**
1. `core/bus` dismiss as a stack (card, then window, then panel) instead of every handler on one Esc. The drawer now checks `useErrors.visible`, which covers our cards; account / pricing windows still close together with the panel (account lane).
2. `core/shortcuts`: the ⌥E / ⌥H / ⌥S / ⌥D keys should respect the gate (today the keys still send while the tiles are disabled). Suggest `triggerShortcut` consults a registered gate.
3. Onboarding lane: the recovery card should read the same gate copy, and its permission rows should use `features/settings/words.ts` (one name and one caption per permission).

**Fix round 1 (surfaces)**
- Gate copy comes from `Gate` only: `help` (the Need help caption) and `queued` (the caption under a queued Check, and the pill line "Check queued. Runs when ..."). No more "miyagi is back" while the Mac is the one offline, and "Queued" is no longer said three ways.
- `CardFrame` keys its blocks by the child's own key (the Children.toArray slot), so View report / Hide report no longer remounts the blocks after it and replays their entrance.

**Cross-lane edits (drawer owner, please sign off)**
This lane edited `features/drawer/**`, outside its declared scope (settings, errors, progress, complete). The edits are minimal and only wire the gate:
- `drawer/v2/LessonPanel.tsx`: `Body` reads `useLinkGate()`; while paused the body and the keys line dim to 50 % and go `inert`; `GatedCheck` replaces the bare Check my work.
- `drawer/v2/Help.tsx`: takes `gate`, disables the tiles while it waits, caption from `gate.help`.
- `drawer/store.ts`: `othersOpen` counts a visible error card, so one Esc closes only the card.

**Core requests (fix round 1)**
4. **err-crash covers the VS Code tab bar** (stage x 522-918, y 36-380, over the editor tabs). Island cards always grow straight down from the pill and core/Island owns that placement, so this lane can't move the card. Ask: an `IslandMode` option (e.g. `clearChrome: true` or `offsetY`) that keeps the card attached to the island (born from it, same center x) but places its body below the editor's tab bar and toolbar (the editor rect from the layout, else about 84 pt from the top at 1440x900). err-crash first, then any other tall launch-time card. Until then the crash card only shows at launch with no lesson on screen, and Esc (Don't save) or Save report closes it.

**Fix round 2 (surfaces)**
- The folded pill's Restart now restarts: it calls the same `restartEngine()` as the card's primary (`engine-local:restart`, or `engine-link:retry` when the engine runs in Terminal, where the pill says "Try again") and unfolds the card, which shows "Restarting. This takes a few seconds." One press, not two. Stage: `?scenario=errors&err=engine-offline&clean`, Esc, then Restart on the pill: the mock engine comes back and the pill says "Back. Picking up where you were." Shots: `surfaces-err-stopped-pill.jpg`, `surfaces-err-stopped-restart.jpg`.
- **Core request 2 is still open** (QA's "nothing visible happens"): the ⌃⌥E / H / S / D shortcuts still send while the gate disables the help tiles. `core/shortcuts` `triggerShortcut` should consult the gate (refuse and show `gate.help` on the pill, e.g. "Help waits until miyagi is back"). This lane can't edit core; the ui-polish session owns it.

## Round 5: calm status (`michael/app-calm-status`, port 6012)

Michael: "Engine Connecting" and "Cloud Waiting" read like an alarm while miyagi was simply starting. One model now says whether miyagi is ready, and every surface reads it.

- **`features/errors/startup.ts`** (pure `bootOf()` + a small clock): `checking` (first 700 ms, nothing new shows, so a fast connect never flashes), `starting` "miyagi is getting ready", `reconnecting`, `ready` "Ready", `limited` (cloud used up / paused / off / offline: a plain line, white ring), `failed` "miyagi couldn't start" only after a real failure (local engine `failed` / `missing`, cloud access `failed`, five failed tries after it was up) or `BOOT_MS` = 45 s. Retry restarts what failed (`restartEngine()`: `engine-local:restart`, or `engine-link:retry` for a Terminal engine; `cloud:retry` for the cloud) and starts the wait over. Copy details: main's `engine-local:details` (state, reason, end of engine.log, keys hidden) when the local engine failed, otherwise the card's allowlisted, scrubbed summary plus the new `cloud` and `startup` fields (scrub.ts).
- **`features/errors/boot.tsx`**: `BootRow` (the home rail's first row) and `BootLine`, the soft progress line: a neutral segment gliding along a 2 px hairline track at the row's foot (absolute, no layout shift). On Ready it runs out to the full track and fades, the green check draws in and "Ready" rises into place (only after a wait the learner saw: a window that opens on an engine already up shows Ready settled). Failed: the block (reason, Retry, Copy details) rises in under the line and the rows below glide (section `layout`, transforms only). Reduced motion: the segment fills the track and breathes (opacity), never frozen. House spring, transform/opacity only, green only for Ready.
- **Home rail** (`features/library/Status.tsx`): Ready row + Setup row (+ Plan when v2Cloud). The Engine and Cloud rows are gone; the engine-start lane's `EngineFailed` block folds into the Ready row's failed state. A short window keeps the Ready row only (`Sidebar.tsx` status block: `setup={!short}`).
- **Quiet start** (`useQuietStart`): with no lesson on screen, while first-run setup is not finished (onboarding `loaded && !done`, read only) or the app's own engine is in its first start, `err-engine-offline`, `err-stopped`, `err-reconnecting` and `err-net-offline` stay off. The idle pill says "miyagi is getting ready" with the same progress line along its foot (the keycap rises in when it's up), and after a real failure "miyagi couldn't start · Retry". A lesson on screen is never quiet: mid-lesson errors are unchanged.

**Stage:** `http://localhost:6012/?scenario=home&window=library&size=1440x900&clean&boot=<fixture>`, fixtures `starting`, `installing`, `slow` (Ready at 3.5 s), `timeout` (`&bootMs=` shortens the 45 s), `failed` (Retry comes back in 1.6 s), `reconnecting`, `cloud`, `cloud-failed`. Stage only, never in Electron. Shots: `/Users/tripi/sand hacks/miyagi-v2/screens/round5/status-*.jpg`.

**Core requests:**
1. **onboarding lane**: the setup flow's engine step can read `useBoot()` (startup.ts) so setup and Home say the same words; its row still uses its own words ("Couldn't start", "Connecting") today.
2. **core**: `localEngine.reason` could carry a short plain-language class (`spawn`, `exit`, `timeout`, `install`) so the rail's second line can be more specific without parsing `line`.

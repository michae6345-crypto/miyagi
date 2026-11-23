# miyagi desktop app: bug risks from user behaviour and environment changes

Audited against `michael/v2-integration` at commit 5f04f998 (5f04f998d2be488fa8960fa3cd51a32d88c10a4f), read-only, Nov 21.
Scope: `app/src/main` (index, appWindows, engine, localEngine, identity, permissions, prefs, serve, features/), `app/src/preload`, and the renderer surfaces (lesson panel, pill, Mini, launcher, home, sign-in, Settings privacy, update card). Paths below are relative to `app/src/` unless they start with another top folder.

`vscode-ext/` in this checkout holds only a README, so the companion's reconnect behaviour could not be read. The app only learns about VS Code through engine events (`blockers.editor_closed`, `lesson.paused reason editor_closed`).

Severity: P0 = crash, data loss or stuck UI. P1 = wrong behaviour real users will hit. P2 = polish or niche.
"(confirmed in code)" means the code path is there to read. "(suspected)" means the trigger or the outcome depends on something outside this code (the engine, macOS, timing) and was inferred.

## Summary

| ID | Sev | Title | Status |
|----|-----|-------|--------|
| R01 | P0 | Every relaunch of the built app wipes all localStorage state (random renderer port) | confirmed in code |
| R02 | P0 | "Checking" can spin forever: no socket heartbeat and no client timeout | confirmed (trigger suspected) |
| R03 | P1 | Lesson shortcuts (⌥E, ⌥H, ⌥S...) stay grabbed after the engine dies or the lesson resets without `lesson.ended` | confirmed in code |
| R04 | P1 | Force quit or crash of miyagi leaves the engine running and watching the screen | confirmed in code |
| R05 | P1 | Engine crash mid-lesson is never restarted automatically | confirmed in code |
| R06 | P1 | Restart of a hung engine sends SIGTERM only; after that Retry does nothing | confirmed in code |
| R07 | P1 | Double click or double Enter on Check my work sends two `check_step` | confirmed in code |
| R08 | P1 | prefs.json is written in place; a crash or full disk mid-write resets every preference | confirmed in code |
| R09 | P1 | Monitor unplugged, clamshell, or primary display change: overlay stays on the old frame | confirmed in code |
| R10 | P1 | Engine and overlay only cover the primary display; VS Code on a second monitor is invisible | confirmed in code |
| R11 | P1 | First launch after an update on a low disk: engine never starts, although the old engine copy is fine | confirmed in code |
| R12 | P1 | Ad-hoc signed updates can silently break Screen Recording and Accessibility grants | suspected |
| R13 | P1 | Delete my data leaves the Google session, install token, lesson cache and local state | confirmed in code |
| R14 | P1 | First-run cloud token mint has a 10 s timeout against a host that cold-starts | suspected |
| R15 | P1 | Building pill has no timeout while the socket stays open | confirmed (trigger suspected) |
| R16 | P1 | Engine event log grows without bound and is replayed into every window that opens | confirmed in code |
| R17 | P2 | Second launch on Windows (and `open -n` on Mac) opens the launcher and home at once | confirmed in code |
| R18 | P2 | Single-instance lock is taken late, after windows, shortcuts and the engine link exist | confirmed in code |
| R19 | P2 | Sign-in started from two windows: the second silently cancels the first; stale tab gets a bare 404 | confirmed in code |
| R20 | P2 | Two copies (dev + packaged) share userData and one rotating refresh token | suspected |
| R21 | P2 | Update Download has no in-flight guard in main (two windows open two downloads) | confirmed in code |
| R22 | P2 | Library Start lesson: wrong message offline, and any unrelated `error` or `lesson.ready` settles it | confirmed in code |
| R23 | P2 | v2 commands are dropped silently between reconnect and `engine.hello` | confirmed in code |
| R24 | P2 | Launcher hotkey pressed during the close animation is swallowed | confirmed in code |
| R25 | P2 | Reconnect hold is 2 s; a slow engine replay resets and re-animates the lesson panel | suspected |
| R26 | P2 | Permission revoked mid-lesson: the app only polls while a settings/onboarding window watches | suspected |
| R27 | P2 | Pill top (notch band) is computed once at launch | confirmed in code |
| R28 | P2 | engine.log is appended forever, no rotation | confirmed in code |
| R29 | P2 | Launcher field has no length cap (a pasted file goes to the engine as the query) | confirmed in code |
| R30 | P2 | Overlay polls every data-hit rect every 100 ms (slow machines, battery) | suspected |
| R31 | P2 | Windows global hotkeys may auto-repeat when held | suspected |
| R32 | P2 | Quit mid-lesson: resume depends entirely on the engine saving on SIGTERM | suspected |

Counts: P0 2, P1 14, P2 16 (32 total).

## Details

### R01 (P0) Every relaunch of the built app wipes all localStorage state (confirmed in code)
- Reproduce: built app. Turn sounds on (or dismiss tips, move the drawer side, collapse the Mini coach, set player volume). Quit and reopen. Everything is back to defaults, tips show again, and the home window shows a blank "pending" frame before the first-run check.
- Evidence: `main/serve.ts:81` listens on port 0, so the origin is `http://127.0.0.1:<new port>` every launch; `main/index.ts:181` loads every window from it. localStorage is per origin (scheme, host and port). Users of it: `renderer/src/features/sound/settings.ts:49,129`, `features/tips/store.ts:51`, `features/shell/flow/store.ts:51,58` (its own comment says it exists to avoid the blank first frame), `features/drawer/store.ts:65,79`, `features/pill/index.tsx:522,530`, `features/player/store.ts:63,74`, `features/dashboard/store.ts:41,52`, `features/reminders/store.ts:169`, `features/diagrams/store.ts:165,177`. `tips` and `sounds` are not in `DEFAULT_PREFS` (`common/prefs.ts:30`), so they fall back to localStorage. Each launch also leaves one more dead origin in the LevelDB store.
- Fix: pick a fixed loopback port (try a known one, fall back and remember it in userData), or serve from a custom privileged scheme (`protocol.registerSchemesAsPrivileged` with `standard: true`, e.g. `miyagi://app`), so the origin never changes. Move durable state (tips, sound) into main prefs.

### R02 (P0) "Checking" can spin forever: no heartbeat, no client timeout (confirmed in code; trigger suspected)
- Reproduce: start a lesson, press Check my work, then make the engine stop answering without closing the socket (Python deadlock, a model call that never returns, a laptop that sleeps while a wss engine is remote). The button stays "Checking", its click is a no-op and Enter is disabled.
- Evidence: `main/engine.ts:219-267` has no ping/pong or idle timeout; `renderer/src/core/ui/atoms.tsx:124-128` `useChecking` = thinking and pressed, cleared only by an engine message (`core/shortcuts.ts:29-39`); `features/drawer/v2/LessonPanel.tsx:302` makes the button inert while checking; `LessonPanel.tsx:229` turns Enter off. No powerMonitor `resume` handling in `engine.ts`.
- Fix: ws ping every 15 s with terminate on a missed pong; a renderer timeout (for example 60 s) that clears `pressed`, notifies "No answer yet" and re-enables Check; reconnect on `powerMonitor` resume.

### R03 (P1) Lesson shortcuts stay grabbed after the engine dies or the UI resets (confirmed in code)
- Reproduce: start a lesson (⌥E, ⌥D, ⌥S, ⌥H, ⌥← get registered). Kill the engine, or let the renderer reset the lesson after a reconnect. In any other app ⌥E (é dead key on Mac) and the others do nothing, until a later `lesson.ended`.
- Evidence: `main/index.ts:404-405` registers on `lesson.ready` and unregisters only on `lesson.ended`. Nothing unregisters on `engine.onStatus(false)` or on the renderer's reconnect reset (`renderer/src/core/lesson.ts:166-181`).
- Fix: also unregister when the link drops for longer than the reconnect hold, and when the overlay's lesson store resets (a `ui:emit` signal).

### R04 (P1) Force quit or crash leaves the engine running and watching the screen (confirmed in code)
- Reproduce: start a lesson, Force Quit miyagi (or it crashes). The engine keeps running in the background with screen capture and cloud calls until miyagi is opened again (step 7 reclaims it). If the learner never reopens, it never stops.
- Evidence: `main/localEngine.ts:490,501` spawn with `detached: true` (own process group); stop only happens in `will-quit` (`main/index.ts:543-546`, `localEngine.ts:719-728`). The reclaim is only on the next launch (`localEngine.ts` header step 7).
- Fix: have the engine watch its parent (pass the app pid in env and exit when it is gone, or keep a stdin pipe open and exit on EOF). Keep `detached` for the group kill.

### R05 (P1) Engine crash mid-lesson is never restarted automatically (confirmed in code)
- Reproduce: kill the engine process during a lesson. The pill goes "reconnecting", then the offline card; the learner has to press Restart.
- Evidence: `main/localEngine.ts:642-652`: an exit while running goes straight to `fail(... 'The engine stopped.')`, no restart.
- Fix: auto-restart once or twice with backoff (for example 1 s, 5 s) before showing the card; keep the card for repeated crashes.

### R06 (P1) Restart of a hung engine: SIGTERM only, then Retry is dead (confirmed in code)
- Reproduce: engine hung (state `failed` after START_TIMEOUT, process alive). Press Retry. If the process ignores SIGTERM, nothing happens; every later Retry returns `ok` because `restarting` is already true.
- Evidence: `main/localEngine.ts:669-676` (`restarting = true`, `killGroup` SIGTERM, return); line 672 returns early forever while `restarting`. `killGroup` (`:660-667`) never escalates. Compare `reclaimOwnLeftover`, which does escalate to SIGKILL.
- Fix: after 5 s without `exit`, send SIGKILL to the group; clear `restarting` on timeout.

### R07 (P1) Double click or double Enter on Check my work sends two `check_step` (confirmed in code)
- Reproduce: double click Check my work (or press Enter twice fast) on a working step. Two checks go to the engine before the first `status thinking` arrives; the engine may judge twice, spend two model calls, and show two cards.
- Evidence: `renderer/src/features/drawer/v2/LessonPanel.tsx:195` `check = () => sendAction('check_step')`; the guard `checking` (`:225`, `:302`) only turns true once the engine says thinking (`core/ui/atoms.tsx:124-128`). `core/shortcuts.ts:45-51` `sendAction` has no dedupe. Same pattern for the shortcut bar's Check (`features/shortcut-bar/ShortcutBar.tsx:58`) and the Teach drawer (`features/drawer/Teach.tsx:458`).
- Fix: in `sendAction`, ignore the same kind pressed again within about 800 ms or while `usePressed.kind === kind` and no engine answer yet; or mark checking locally on press.

### R08 (P1) prefs.json written in place; a crash or full disk resets every preference (confirmed in code)
- Reproduce: change a setting while the disk is full, or crash during the write. On the next launch prefs.json is empty or truncated, so everything (appearance, launch at login, panelCollapsed, crashReports, onboarded) is back to defaults.
- Evidence: `main/prefs.ts:45` `writeFileSync(file, ...)` directly; `:25-29` falls back to defaults on any parse error. Same pattern in `main/features/reminders.ts:72` and `main/features/player.ts:100`. auth, cloud, settings, updates, onboarding already use tmp + rename. No prefs schema version, so a future rename of a field has no migration path.
- Fix: tmp + rename like `auth.ts:269-271`; keep a `.bak`; add a `version` field and a migrate step in `sanitizePrefs`.

### R09 (P1) Monitor unplugged, clamshell, primary display change: overlay stays on the old frame (confirmed in code)
- Reproduce: MacBook with an external display set as primary. Close the lid, or unplug the display, or change "main display" in System Settings. The full-screen overlay and launcher keep the old size and origin; the pill lands in the wrong place or partly off screen, and the rects sent to the engine no longer match its primary display.
- Evidence: `main/index.ts:491-496` handles only `display-metrics-changed`, and resizes to `getDisplayMatching(w.getBounds())` (the display the window is on), while everything else assumes the primary (`index.ts:62`). No `display-added` / `display-removed` handlers anywhere (grep).
- Fix: on `display-added`, `display-removed` and `display-metrics-changed`, set both core windows to `overlayBounds(screen.getPrimaryDisplay())`, recompute `pillTop`, and send the new layout.

### R10 (P1) Only the primary display is watched; VS Code on a second monitor (confirmed in code)
- Reproduce: drag VS Code to a second monitor mid-lesson. The pill and lesson panel stay on the primary, and the engine cannot see the editor, so checks and off-track judgement fail.
- Evidence: `main/index.ts:61-62` ("v1: the engine watches the PRIMARY display only"); `features/player.ts:60` docks on the overlay's display.
- Fix: short term, detect VS Code's window on a non-primary display (the engine knows its bounds) and say "Move VS Code to the main display"; long term, follow the editor's display.

### R11 (P1) First launch after an update on a low disk: engine never starts (confirmed in code)
- Reproduce: update the app with little free disk. `copySource` copies the full bundled source and then merges `demo/cache` and `demo/runs` into `src.new`, so it briefly needs about twice the space. It fails with ENOSPC, `boot()` returns, and the engine is `failed` even though the previous `src` is intact. Every launch retries the same copy.
- Evidence: `main/localEngine.ts:407-432` (copy then merge), `:697` (`if (!(await copySource())) return`), marker never updated so `fresh` stays false.
- Fix: on a copy failure with a working old `src`, start the old engine and say "Free some disk space to finish the update"; check free space first; move the kept dirs with `rename` instead of copying them.

### R12 (P1) Ad-hoc signed updates can break Screen Recording and Accessibility grants (suspected)
- Reproduce: grant Screen Recording and Accessibility, install the next version. macOS ties TCC grants of ad-hoc signed apps to the code hash, so the toggle in System Settings can still look on while the new build is denied. The engine (started by the app, so attributed to it) sees a black screen.
- Evidence: `main/features/updates.ts:2` ("the app is ad-hoc signed"); grants read in `main/permissions.ts:36-47`, polled only while a window watches (`:63-71`).
- Fix: sign with a stable Developer ID; until then, on the first launch of a new version compare `permissions:get` with the last saved state and, if it went from granted to not granted, open the recovery step that says "remove miyagi from the list and add it again".

### R13 (P1) Delete my data leaves the Google session, install token, lesson cache and local state (confirmed in code)
- Reproduce: Settings, Privacy, Delete my data, Delete. Keys and prefs are cleared, but the learner is still signed in with Google, the cloud install token stays, cached lessons and transcripts and "Do it for me" backups stay in `~/miyagi/engine/src/demo`, crash reports and localStorage stay. The prefs reset also sets `onboarded: false` while `onboarding.json` still says done, so the two flags disagree.
- Evidence: `main/features/settings.ts:168-180` only clears keys; `renderer/src/features/settings/sections/Privacy.tsx:32-40` then `setPrefs(DEFAULT_PREFS)`. Session in `main/features/auth.ts:229` (`auth.bin`) and `login.json` (`:231`); install token `main/features/cloud.ts` (`install.bin`); engine cache `main/localEngine.ts:400-405` (KEPT_DIRS). `features/launch.ts:85` reads either flag.
- Fix: make Delete call auth sign-out and cloud forget, clear the renderer storage (`session.clearStorageData`), and either delete the engine's cache or say plainly that lessons stay; keep the copy honest about what is removed.

### R14 (P1) First-run cloud token mint: 10 s timeout against a cold-starting host (suspected)
- Reproduce: fresh install, the hosted proxy has been idle. The first POST /v1/install takes longer than 10 s, the mint fails, and the boot screen says "Couldn't set up access for this Mac." The next automatic try is up to 5 minutes away.
- Evidence: `main/features/cloud.ts:35` (`MINT_TIMEOUT_MS = 10_000`), `:36` (`RETRY_MS = 5 min`), default host `:44` is on onrender.com; `renderer/src/features/errors/startup.ts:108` shows the failure.
- Fix: 30 to 45 s timeout for the first mint, one automatic retry after 5 s, and keep "setting up" on screen while it retries.

### R15 (P1) Building pill has no timeout while the socket stays open (confirmed in code; trigger suspected)
- Reproduce: Build lesson, then the engine stalls without closing the socket. The building pill stays.
- Evidence: `renderer/src/core/lesson.ts:143,152-153`: building only ends on `lesson.building failed`, `lesson.ready` or a socket drop. `features/launcher/Launcher.tsx:549,582,595` set the phase to building right after sending.
- Fix: a watchdog that turns "building" into the build-failed card after N minutes without any `lesson.building` progress event.

### R16 (P1) Engine event log grows without bound and is replayed into every window (confirmed in code; impact suspected)
- Reproduce: a long lesson (status, check.updated, offtrack, metrics events every few seconds), then open Library or Account, or let a renderer reload. Each opening window receives the whole log in one burst.
- Evidence: `main/engine.ts:57,297` pushes every event; it is trimmed only on `lesson.ready`, `lesson.ended`, open and learn (`:169,239,294-296`). `main/index.ts:441` replays all of it on every `ui:ready`.
- Fix: keep only the latest event per type (or per id) plus a small tail, and cap the length.

### R17 (P2) Second launch opens the launcher and home at once (confirmed in code)
- Reproduce: Windows, open miyagi from the Start menu while it runs (or `open -n` on Mac). Both the launcher and the home window come up; the launcher then loses focus to home and closes, so it flickers.
- Evidence: `main/index.ts:485` (`second-instance` opens the launcher) and `main/features/launch.ts:179` (`second-instance` opens home).
- Fix: remove one handler; keep launch.ts's `openHome`.

### R18 (P2) Single-instance lock is taken late (confirmed in code)
- Reproduce: launch twice quickly. The second process creates the overlay and launcher windows, starts an engine link with its own token, tries the global shortcuts and starts `setupLocalEngine` before `launch.ts` / `windows.ts` call `requestSingleInstanceLock` and `app.exit(0)`.
- Evidence: `main/index.ts:43` (EngineLink connects at module load), `:394-395`, `:481`, `:502`, then `loadFeatures` at `:513`; lock in `main/features/launch.ts:76` and `main/features/windows.ts:78`. On Mac the lock is packaged only.
- Fix: call `requestSingleInstanceLock()` at the top of `index.ts`, before `whenReady`, and quit there.

### R19 (P2) Sign-in from two windows; stale browser tab gets a bare 404 (confirmed in code)
- Reproduce: start Google sign-in in the home window's login, then start it again from the Account page. The first window shows "cancelled". Finishing in the first browser tab hits a 404 with no page.
- Evidence: `main/features/auth.ts:429` (a new flow stops the old one), `:447-449` (state mismatch answers a bare 404). In-window guard only: `renderer/src/features/auth/store.ts:50`.
- Fix: if a flow is running, return the same pending promise to the second caller; answer a stale state with the "Sign-in did not finish, try again in miyagi" page instead of 404.

### R20 (P2) Dev and packaged copies share userData and one rotating refresh token (suspected)
- Reproduce: run `npm run dev` and the installed app on the same Mac, both signed in. Supabase rotates the refresh token, so whichever refreshes second gets a 400 and is signed out.
- Evidence: `main/identity.ts:7-8,21` (same userData name in dev); `main/features/auth.ts:336-367` (refresh, 400/401 signs out).
- Fix: separate userData for unpackaged runs (`app.setPath('userData', ...-dev)`), or re-read auth.bin before a refresh.

### R21 (P2) Update Download has no in-flight guard in main (confirmed in code)
- Reproduce: the update card in the overlay and Settings' "Check for updates" view both show Download; click both. Two browser downloads.
- Evidence: `main/features/updates.ts:166-171` (no guard); the renderer guard is per window (`renderer/src/features/updates/store.ts:51-57`).
- Fix: an `opening` promise in main, returned to the second caller.

### R22 (P2) Library Start lesson: wrong message offline, unrelated events settle it (confirmed in code)
- Reproduce: engine offline, press Start lesson: it says "This engine can't start saved lessons yet." Or start a lesson while some other `error` event arrives: the start reads as failed while the lesson then starts anyway.
- Evidence: `main/features/library.ts:164-167` returns false for offline and for missing capability alike; `renderer/src/features/library/store.ts:143-158` resolves on any `lesson.ready` or `error`.
- Fix: return a reason (`offline` / `unsupported`); match `lesson.ready` on the started id.

### R23 (P2) v2 commands dropped silently between reconnect and `engine.hello` (confirmed in code)
- Reproduce: engine restarts; within the first moments after the socket opens, `panel.state` or `library.*` goes out. It is dropped with no error, so the engine may not know where the panel is.
- Evidence: `main/engine.ts:240` clears caps on open; `:172` returns early for v2 commands without caps.
- Fix: queue the latest v2 command per type until hello, then flush; or resend `panel.state` on hello.

### R24 (P2) Launcher hotkey pressed during the close animation is swallowed (confirmed in code)
- Reproduce: press ⌥Space to close the launcher and press it again right away. Nothing reopens; a third press is needed.
- Evidence: `main/index.ts:481` and `:268-270` (still "open" until `launcher:hidden`, so it sends close again); renderer ignores close unless phase is `open` (`renderer/src/features/launcher/Launcher.tsx:265-267`).
- Fix: in main, remember a reopen request while closing and run `openLauncher` on `launcher:hidden`.

### R25 (P2) Reconnect hold is 2 s; a slow replay resets the panel (suspected)
- Reproduce: slow Mac, engine restarts and takes more than 2 s to send the lesson snapshot. The lesson resets, then comes back as a "new" lesson: the panel slides in again, an open hint and the Mini collapse are lost.
- Evidence: `renderer/src/core/lesson.ts:163` (`REPLAY_WAIT_MS = 2000`), `:166-181`.
- Fix: hold until `engine.hello` plus a short grace, or longer (for example 8 s) when the engine says `restored`.

### R26 (P2) Permission revoked mid-lesson (suspected)
- Reproduce: during a lesson turn off Screen Recording or Accessibility for miyagi. The app only polls permissions while onboarding or the Settings section asks for it, so the only signal is the engine's `lesson.paused reason permission`.
- Evidence: `main/permissions.ts:63-71,75-95`; recovery hook `renderer/src/features/onboarding/store.ts:333`.
- Fix: poll at a low rate (every 10 s) while a lesson is running and raise the recovery card from the app too.

### R27 (P2) Pill top is computed once at launch (confirmed in code)
- Reproduce: launch on a notched MacBook, then make a non-notch external display primary (or the reverse). The pill sits too low or under the menu bar.
- Evidence: `main/index.ts:393` (`fitPillTop` once, before windows exist; passed in launch arguments).
- Fix: recompute on display changes and send it with `layout`.

### R28 (P2) engine.log is appended forever (confirmed in code)
- Evidence: `main/localEngine.ts:288-294` (`appendFileSync`) and `:494-505` (the engine's stdout and stderr appended to the same file every launch). No size check.
- Fix: rotate at start when over a few MB (keep one `.1`).

### R29 (P2) Launcher field has no length cap (confirmed in code)
- Reproduce: paste a whole source file into the launcher and press Enter. It is sent as `learn {query}`.
- Evidence: no `maxLength` in `renderer/src/features/launcher/`; `Launcher.tsx:545` sends the trimmed query as is.
- Fix: cap at a few hundred characters and say "Keep it to a sentence".

### R30 (P2) Overlay polls every data-hit rect every 100 ms (suspected)
- Evidence: `renderer/src/core/Overlay.tsx:95-115` (querySelectorAll, getBoundingClientRect, two JSON.stringify per tick, always on), plus the click-catching poll in `main/features/overlay-raise.ts`. On slow machines this competes with VS Code and the engine; it runs with no lesson too.
- Fix: run only while something is on screen, and drive it with ResizeObserver plus animation-end events instead of a fixed interval.

### R31 (P2) Windows global hotkeys may auto-repeat when held (suspected)
- Reproduce: hold Alt+H on Windows. RegisterHotKey repeats unless MOD_NOREPEAT is set, so several hint actions go out.
- Evidence: `main/index.ts:318` registers with no repeat guard; `renderer/src/core/shortcuts.ts:45-51` has no dedupe.
- Fix: the same dedupe as R07 (same kind within about 500 ms ignored).

### R32 (P2) Quit mid-lesson: resume depends on the engine saving on SIGTERM (suspected)
- Reproduce: quit with ⌃⌥Q mid-step, reopen. Whether "Continue where you left off?" appears and lands on the exact step depends on the engine writing its state in its SIGTERM handler before the app exits. App-side, only `panelCollapsed` is kept; an open hint, the not-yet card and a queued check are lost.
- Evidence: `main/index.ts:487-489,543-546` (quit sends SIGTERM and exits without waiting); `main/localEngine.ts:719-728`. Resume card contract in `shared/contracts/events.ts:85-88,138,144`.
- Fix: on quit, hold the exit (`before-quit` preventDefault) for up to 2 s until the engine child has exited, so it can save; test the resume path on the Mac.

## Checked and fine
- Google PKCE: a callback arriving twice is ignored (`main/features/auth.ts:447`, `f.exchanging`); Cancel, Esc and leaving the screen stop the listener (`renderer/src/features/auth/Login.tsx`); browser closed halfway times out after 5 min (`auth.ts:503-505`); an expired or reused code gets a plain message (`auth.ts:172-173`); refresh is single-flight and re-run on wake (`auth.ts:336-382`). Session file writes are atomic.
- Engine reconnect has no storm: 1 s for 30 s, then 2, 4, 5 s capped (`main/engine.ts:269-276`); Retry is idempotent (`engine.ts:130-136`).
- Offline learner commands fail visibly instead of being queued and replayed stale (`main/engine.ts:183-186`); a Check pressed while offline is queued once per step and sent when the link is back (`renderer/src/features/errors/gate.ts:115-139`).
- Launcher submit paths check `phaseRef` synchronously, so a double Enter does not build twice (`renderer/src/features/launcher/Launcher.tsx:193-194,545-597`).
- Library Start, the companion install and the update card have per-window in-flight guards.
- A renderer that dies is reloaded and gets the replay (`main/features/recover.ts`); the overlay goes back to click-through on reload (`main/index.ts:438`) and has a watchdog for a control vanishing under the cursor (`renderer/src/core/Overlay.tsx:141-146`).
- The player window only restores saved bounds that still land on a display (`main/features/player.ts:40-54`).
- Two instances do not call each other a crash (`main/features/errors.ts:121-167`).

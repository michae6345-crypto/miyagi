# Later

Every area's "Later" section, merged and deduped, plus the register rows that wait until after launch. One line
each. The tag at the end says which area it came from. Items that a risk in [`RISKS.md`](RISKS.md) already covers
were dropped from this list and are named at the bottom.

## Register rows that wait

- Capture only the editor and tutorial windows instead of the whole display (R18, D8). [B]
- The false passes after E18: stale output passes (E19), commented-out code and `def` without a call pass (E21),
  text from any VS Code window latches a pass (E22), "Looks done?" skips the code gate (E23) (R32). [E]
- A signed update manifest on miyagi.study with a minimum version (R26). [C]
- Licenses and third-party notices in every build (R48). [B]
- Site polish: words before 3D, contrast, skip link, a download block after the story (R49). [D]
- Hint ladder in lesson mode: a question or pointer first, "Do it for me" only after a real attempt (E26, R36). [E]
- GitHub Pages terms don't allow an "online business": move the site (Cloudflare Pages, Netlify or Vercel) before
  charging (C43). [C]
- The engine reinstall marker is compared with `!==`, so a rollback re-copies an older engine; cached lessons have no
  schema version (`app/src/main/localEngine.ts:689-707`) (C44). [C]

## App shell

- `main/index.ts:153-160`: put the security flags after `...options.webPreferences`, so no feature can override
  `sandbox`. [A]
- `main/features/player.ts:90-93`: the player's window-open handler calls `shell.openExternal` on any https URL,
  skipping `isBrowserLink`. [A]
- `main/index.ts:74`: in the `file://` fallback, any `file:` URL counts as our own origin. [A]
- `main/safeOpen.ts:25`: still allows `elevenlabs.io`, though no ElevenLabs option exists. [A, D]
- `main/localEngine.ts:69`: the copied "install the engine" `curl | bash` points at a mutable branch where the script
  doesn't exist. [A]
- `main/prefs.ts:45`, `main/features/reminders.ts:72`: written in place, not temp-then-rename; a crash mid-write resets
  prefs and turns launch at login off. [A; #202 R08]
- The single-instance lock is taken inside features that load after auth, cloud and the windows
  (`main/features/launch.ts:76`, `windows.ts:78`); dev runs share userData with the installed app (`main/identity.ts:21`). [A; #202 R18, R20]
- The ⌥Space launcher key often belongs to Alfred, Raycast or ChatGPT; registration fails with only a log line
  (`main/index.ts:481-482`), and `prefs.shortcuts` is never applied. [A]
- Lesson shortcut keys stay registered when the engine drops without `lesson.ended` (`main/index.ts:402-406`). [A; #202 R03]
- After an engine crash the app stays on "external" and needs a manual Retry; restart it automatically once or twice
  (`main/localEngine.ts:641-651, 670, 685-688`). [A, E; #202 R05]
- One listener or `onOpen` hook that throws stops the fan-out to the rest (`main/engine.ts:242, 298`); the `whenReady`
  chain has no catch (`main/index.ts:379`). [A]
- `main/features/recover.ts:32-35` stops reloading a crashed renderer after 3 tries a minute and never tries again. [A]
- Displays: unplugging a monitor, closing the lid or changing the primary display leaves the overlay and launcher on
  the old frame, so the pill lands in the wrong place and the rects sent to the engine stop matching (only
  `display-metrics-changed` is handled, `main/index.ts:491-496`); `pillTop` is set once (`:393`); no `display-added` or
  `display-removed` handlers; the player isn't re-docked. Fix: refit both core windows to the primary display on all
  three events and recompute `pillTop`. [A; #202 R09, R27]
- `main/features/overlay-raise.ts:132`: a 15 ms cursor poll runs for the app's whole life. [A]
- The in-memory engine event log grows for the whole lesson and is replayed into every window on `ui:ready`
  (`main/engine.ts:297`, `main/index.ts:441`). [A; #202 R16]
- Settings: other windows keep showing the old key state after Delete or Save (no broadcast,
  `main/features/settings.ts:168-187`). [A]
- Truncation can split an emoji in titles and names (`renderer/src/features/library/sanitize.ts:213`,
  `main/features/auth.ts:104`). [A]
- Double click or double Enter on Check my work sends two `check_step` (#202 R07); dedupe in `sendAction`. [E]
- "Connected to VS Code" shows when the companion is merely installed, even if disabled or in another profile
  (`renderer/src/features/onboarding/rows.ts:83`, `server/orchestrator/health.py:64-86`). [E]
- Offer `app.moveToApplicationsFolder()` on first launch (App Translocation leaves venvs pointing at a vanished
  path). [C]
- One network timeout (about 30 s) for mint, auth and updates instead of 10 s and 15 s. [C]
- First launch after an update on a low disk: the engine copy fails with ENOSPC and the engine never starts, though the
  old copy is intact (`main/localEngine.ts:407-432, 697`). Start the old engine and say "Free some disk space to finish
  the update"; check free space first; rename the kept folders instead of copying them. [#202 R11]
- A second launch (Windows, or `open -n` on a Mac) opens the launcher and Home at once (`main/index.ts:485`,
  `main/features/launch.ts:179`). [#202 R17]
- Update Download has no in-flight guard in main, so two windows open two downloads (`main/features/updates.ts:166-171`). [#202 R21]
- Library's Start lesson says the wrong thing offline, and any unrelated `error` or `lesson.ready` settles it
  (`main/features/library.ts:164-167`, `renderer/src/features/library/store.ts:143-158`). [#202 R22]
- v2 commands are dropped silently between a reconnect and `engine.hello` (`main/engine.ts:172, 240`). [#202 R23]
- The launcher hotkey pressed during the close animation is swallowed (`main/index.ts:268-270, 481`,
  `renderer/src/features/launcher/Launcher.tsx:265-267`). [#202 R24]
- The reconnect hold is 2 s, so a slow engine replay resets and re-animates the lesson panel
  (`renderer/src/core/lesson.ts:163-181`, suspected). [#202 R25]
- The launcher field has no length cap, so a pasted file goes to the engine as the query (`Launcher.tsx:545`). [#202 R29]
- The overlay polls every data-hit rect every 100 ms, even with no lesson (`renderer/src/core/Overlay.tsx:95-115`); it
  competes with VS Code and the engine on slow machines (suspected). [#202 R30]
- Windows: global hotkeys may auto-repeat when held (`main/index.ts:318`, `renderer/src/core/shortcuts.ts:45-51`,
  suspected). [#202 R31]

## Sign-in

- A refresh that gets any 400 or 401 signs the learner out silently, including one about a rotated key
  (`main/features/auth.ts:352-357`). [A, C]
- Signing in as someone else doesn't revoke the old session (`main/features/auth.ts:479`). [A]
- Closing the sign-in window mid-wait doesn't cancel the loopback listener (the 5-minute timeout still applies). [A]
- A stale or late sign-in tab gets a blank 404 (`main/features/auth.ts:447-449`); token expiry uses the Mac's clock
  (`:124`, `cloudLink.ts:117`); reopening the login window clears "Waiting" mid-flow (`renderer/src/features/auth/AuthView.tsx:37`,
  `store.ts:63-64`); starting sign-in from a second window silently cancels the first (`auth.ts:429`). [A; #202 R19]
- `/v1/link` isn't in `cloud/app.py` yet, so `cloudLink.ts` resends the Supabase token on every launch while it 404s. [C]
- Split the Google Cloud project into dev and prod. [C]
- If Sign in with Apple is ever added, rotate Supabase's Apple secret every 6 months. [B]

## Engine and grading

- `segment_done` never reaches the checks, so a hidden terminal's "No errors" passes while the clip plays
  (`server/orchestrator/modules.py:382-392`). [E]
- The background judge passes pending checks at 0.8 or more with no press, for example a metric whose pattern didn't
  parse (`server/coach/judge.py:361-365`). [E]
- Video steps with no checks auto-pass at the end of the clip (`server/orchestrator/session.py:3513-3515`). [E]
- Browser-scoped checks lose their app scope and match any window (`server/lesson/builder.py:959-962`). [E]
- OCR misreads (`!=` as `≠`, `l` and `1`, quotes, clipped lines) still decide video-mode code checks when the file is
  outside the lesson folder. [E]
- A learner coding in their own folder with the same file name is blocked until they press "Use this folder"
  (`server/orchestrator/session.py:4180-4186`). [E]
- Text lessons end early after an engine restart, because nothing extends them (`server/orchestrator/session.py:4032-4046`). [E]
- A renamed step file isn't found and nothing asks "did you rename it?" (`server/orchestrator/workspace.py:60-80`). [E]
- Package checks don't pass `--only-binary`, so a package with no wheel builds from source and may pop the
  developer-tools dialog. [E]
- Skip step records "skipped" with no way to say "this check is wrong"; add "Report this check" once there's somewhere
  to send it. [E]
- `server/workspace/resources.py:100-105`: downloads follow redirects with no host recheck (GET only, on a press). [A]
- Build lesson venvs from a copy of Python outside the app, so the shipped app keeps library validation. [C]

## VS Code companion

- The Output channel logs the full text of commands the engine runs and saved file paths. [A]
- Notebook cells report the wrong active file; notebook saves send no events; Run it for me types into a busy
  terminal; "Do it for me" can overwrite keystrokes typed in between; only Visual Studio Code.app is found (not
  Insiders, Cursor or VSCodium). [A]
- A 10th VS Code window gets no companion port (`vscode-ext/extension.js:740-762`); conda `base` from `.zshrc` may
  override the lesson `.venv`. [E]

## Cloud and cost

- Three more small cloud items are in Michael's private notes. [A]
- Move tokens and usage from SQLite to Postgres through `store.py`, drop the disk, and run more than one instance with
  a shared rate-limit store. [C]
- A second region or host for the cloud, and a remote config to switch cloud URLs without shipping a build. [C]
- Move `step_detail` to a cheaper Gemini model or a lower frame rate before Jan 1, 2027, and plan to replace
  `gemini-3.1-flash-lite` (shutdown no earlier than May 7, 2027), if D1 keeps Gemini. [C]
- Use the Batch API (50% off) for demo-cache and eval builds. [C]
- Cache a stable checker prompt prefix; cache reads don't count toward ITPM. [C]

## Release and signing

- Once signed: split entitlements so only the interpreter gets library-validation relief; electron-updater in-place
  updates; a Homebrew cask (Homebrew disabled casks that fail Gatekeeper on 2026-09-01). [C]
- Before electron-builder 27: its defaults drop library-validation relief and unsigned memory, and `notarize: true`
  fails without credentials, so keep explicit plists. [C]
- Evaluate `SCContentSharingPicker` to avoid the recurring screen-recording alert. [C]
- An engine port chosen at launch instead of a fixed 8787, and fallback ports for the 47217 sign-in loopback (R47
  step 2). [C]
- Windows: a screen-less engine first, then the Microsoft Store (MSIX), then a signed direct download built in CI
  (R19). [C]
- Windows: no app menu, so Electron's default menu (and probably DevTools on Ctrl+Shift+I) is reachable (inferred);
  Alt+F4 closes the launcher or player for good and `display-metrics-changed` then throws (`main/index.ts:491-496`);
  Alt+Q quits instantly (`main/index.ts:488-489`). [A]

## Site, domain and support

- `<title>` is just "miyagi"; add a few words for search and tabs. [D]
- No `robots.txt`, sitemap or custom 404. [D]
- The "scroll" hint overlaps the "see it work" button on phones mid-fade. [D]
- Cloudflare Web Analytics on the site, only after the cookie page is re-checked. [D]
- A Tally form for learners without GitHub accounts. [D]
- A real status page once traffic justifies it. [D]
- Push the domain to a shared Porkbun account; a CAA record and DNSSEC for miyagi.study. [C]
- A Google Workspace seat for support@ once replies go out from the domain. [C]
- A "for schools" page with the Google admin setting and, after signing, the PPPC payload. [C]
- WCAG 2.1 AA on miyagi.study, keyboard support in the overlay, and an accessibility contact. [B]

## Company upkeep (from `lawsuit-protection.md` steps 16-18)

- Join LOT Network once the LLC exists (free under $25M revenue). [B]
- Pay the $800 California LLC tax on time and file the Statement of Information every two years; no wages without a
  payroll service. [B]
- Each founder signs a ratification of the operating agreement and IP assignment within days of turning 18, and asks
  the lawyer about AI-tool accounts with 18+ terms. [B]
- When investors get close: consider a Delaware C-corp and D&O insurance. [B]

## Law and policy to watch

- CCPA/CPRA and the other state comprehensive privacy laws: miyagi is below their thresholds today; recheck when users
  or revenue grow. [B; #202 legal 13]
- California AB 1043 / AB 1856: from 2027-01-01 desktop apps must request the OS age signal; check whether direct
  downloads are covered. [B]
- California AB 2246 (replaces the AADC, 2027-01-01) and Vermont's design code: "likely accessed by" under-18s;
  private defaults, no profiling. [B]
- SB 243 / SB 1119 companion-chatbot rules: stay out by keeping the coach task-focused (no friend persona, no
  relationship memory). [B; #202 legal 18]
- EU AI Act Art. 50: machine-readable marking of AI text if EU use grows (the disclosure itself is R05); Annex III
  high-risk only with credentials or school grading. [B]
- UK Data (Use and Access) Act 2025: a complaints process with a 30-day acknowledgement if UK users are served; the
  ICO fee question. [B]
- Microsoft Store build: opt-in before sending personal data to third parties (10.5.2), a generative-AI disclosure and
  report button (11.16), an IARC rating, a EULA URL in Partner Center. [B]
- Mac App Store, if ever: sandbox, no self-updater, a privacy manifest, consent before sending to third-party AI
  (5.1.2(i)), Sign in with Apple. [B]
- Paid plans: California's auto-renewal law (AB 2863) at checkout; the FTC click-to-cancel rule is vacated but
  restarting. [B]
- Export: a free public download is "published" and outside the EAR; keep a one-paragraph memo; no custom crypto. [B]
- VPPA: watch *Salazar v. Paramount* (Supreme Court, argued 2026-10-14); keep video ids out of any third-party
  analytics. [B]
- Washington MHMDA: the policy says we don't seek or infer health data and discard incidental captures (already in
  the draft). [B]
- School deals: FERPA school-official terms, the SDPC National Data Privacy Agreement, SOPIPA if marketed for K-12. [B; #202 legal 16]

## Dropped because a risk covers them

| Later item | Covered by |
|---|---|
| Fixed loopback port 47217 (A) | R47 |
| Cloud log lines carry the user id; tables never pruned (A) | R28 |
| `access_denied` always reads "account isn't allowed" (A) | R20 |
| `tips` prefs dropped by `sanitizePrefs` (A); Home's blank frame on every open (E) | R14 |
| Team member's macOS username in fixture paths (B) | R41 |
| Developer ID signing lane, notarize and staple the DMG (C) | R15 |
| `cloud/app.py:295` "the operators have been notified" (C) | R01 |
| The paused verdict's 120 s TTL (C) | R30 |
| Every build mints with `app: "0.1.0"` (C) | R08 |
| The update check's unauthenticated GitHub API limit (D) | R08 |
| Delete my data removes keys and settings only (D) | R28 |
| `engine.log` rotation at 5 MB (D) | R45 |
| Gemini Flash list prices double on 2027-01-01 (D) | R02 |
| Anything else on port 8787 reads as an external engine (E) | R47 |
| SHIP.md says ⌥Q instead of ⌃⌥Q (E) | R04 |
| Unfinished lessons that can never be continued from Home (E) | R14 |

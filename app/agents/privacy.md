# privacy (ROADMAP 5.4)

**Status:** done, ready for review (v2-integration merged in, telemetry and the account link included; Adrian's policy edits folded in) · **Priority:** P1 (before strangers install) · **Port:** 5615 · **Branch:** `michael/app-privacy` (from `michael/v2-integration`) · **PR:** draft into `adrian/shell`

## Goal
Settings > Privacy tells the learner, plainly and honestly, what miyagi sees, what leaves the Mac and where it goes,
and lets them erase it. A "What miyagi sees" panel lists each source (screen, code, editor, account) with one calm
line each. A link opens the privacy policy. Delete my data erases everything miyagi keeps on this Mac, sign-in included.

## Owns
- `app/src/renderer/src/features/settings/sections/Privacy.tsx` (extend; keep the telemetry lane's switches as merged)
- `app/src/renderer/src/features/settings/privacy/` (new: `Sees.tsx` the panel, `facts.ts` the single list of facts)
- `app/src/main/features/settings.ts` only for `settings:delete` (also remove `login.json`, `auth.bin`, sign out)
- `web/privacy.md` a DRAFT policy for Michael and Adrian to review. Not published, not linked from the site.
- `app/mock/scenarios/privacy.json` if a stage view needs one

## Rules
- Honest subset only: say only what the code does today. Read `server/screen/privacy.py`, `server/coach/common.py`,
  `server/workspace/core.py`, `app/src/main/features/cloud.ts`, `telemetry.ts` before writing a fact.
  5.1 (cropping) is NOT done: do not claim it. 5.2 (key redaction) landed in the engine (integration/live 742ab87a) but
  matches by shape: the policy describes it with that caveat, the panel never promises it.
- Facts live in `facts.ts` once; the panel and `web/privacy.md` say the same things.
- Copy ≤12 words per line, calm, lowercase "miyagi". No red for delete: the existing two-step confirm stays.
- The policy link opens through the existing external-link path (no new window type). URL: `https://miyagi.study/privacy`.

## Done when
- The panel shows screen, code, editor, account, crash and usage rows, each with "stays on this Mac" or where it goes.
- Delete my data also signs out and clears login files; the confirm copy says so.
- `web/privacy.md` covers: what we collect, why, where it goes (Anthropic and Google Gemini through miyagi-cloud,
  Supabase for sign-in), retention, deletion, 13+ only, contact. Marked DRAFT at the top.
- Typecheck green, brand lint clean, stage shots in `app/agents/shots/privacy-*.png`.

## Not in this lane (follow-ups)
- Deleting a cloud account (needs a miyagi-cloud endpoint and a Render deploy: Michael).
- "See what was sent" log (needs engine support).

## Test
`npm run dev:web -- --port 5615 --strictPort` → `http://localhost:5615/?scenario=settings&settings=privacy`
(`&confirm=delete` opens on the delete confirm). Use the `settings` scenario, not `full`: `full` merges the player.
Unit: `cd app && node --import tsx --test src/renderer/src/features/settings/privacy/facts.test.ts src/renderer/src/features/settings/privacy/erase.test.ts src/main/features/settings/erase.test.ts`

## Notes (first pass)
- `privacy/facts.ts` is the one list (screen, code, editor, searches, videos, sign-in, keys, progress, crash, usage).
  Its header names the engine file behind every line (engine read from `origin/integration/live`; the server/ folder
  on this branch is a stub). `facts.test.ts` checks the copy rules and that `web/privacy.md` quotes every line.
- `privacy/Sees.tsx` renders it; Privacy.tsx keeps the telemetry switch as merged, adds the policy row (auth
  `openLegal('privacy')`, the existing allowlisted external-link path) and the new delete copy.
- Delete my data: main `settings:delete` removes keys.bin, then auth.bin and login.json (`settings/erase.ts`);
  the renderer resets prefs and calls `auth:sign-out` (auth.ts owns the session in memory and revokes it).
  `signIn: false` (a sign-in file stayed) shows "Keys and settings deleted. Couldn't clear sign-in." with Delete again.
- `web/privacy.md`: DRAFT with [TBD] for retention on miyagi-cloud, contact address, last-updated date.
- Stage shots: `shots/privacy-panel.png`, `privacy-data.png`, `privacy-confirm.png` (headless, no window).

## Notes (fix round 1, after review)
- Gemini: the policy no longer says "Gemini gets nothing else". `gemini.watch_video` sends the link, the learner's
  goal and the YouTube page text; `step_detail` a step's title and time. The panel line is now "The video link and
  what you want to learn, to Google Gemini." `gemini.adapt_checks` (own Gemini key: draft steps + workdir summary)
  is not called on integration/live: `builder.py` calls `claude.adapt_checks`, so the policy says those go to
  Anthropic. The facts.ts header says to change both if Gemini adapts again.
- Screen: the line claims only the text ("Text from password apps dropped."). Only `scene_watch.py` (the step
  check) blacks out private-app windows; the pointing path (`screen_bridge` → `target.pick_on_screen` →
  `reader.latest_frame` → `render_marks`) does not, and the policy says so.
- Delete my data: the flow lives in `privacy/erase.ts` (`eraseData`, `eraseStep`), tested by `privacy/erase.test.ts`.
  It awaits `auth:sign-out` and shows "partial" unless it answers `true`; the signed-in user is cleared in this
  window only when the sign-out is confirmed. auth.ts is untouched (the sign-in-gate lane owns it).

## Notes (fix round 2)
- `shots/privacy-panel.png` retaken headlessly (headless Chromium, no window, muted, `settings` scenario, no player):
  `?scenario=settings&settings=privacy` at 1440x900 @2x, after the dialog is visible plus 1.5 s for the sheet to
  settle. It shows the current copy: "Text from password apps dropped." and "The video link and what you want to
  learn, to Google Gemini." `privacy-data.png` and `privacy-confirm.png` show unchanged copy and stay as they are.

## Open
- Engine follow-up (not this lane, no server/ edits here): mask private apps in `reader.latest_frame` (pointing
  screenshots), the same way `scene_watch._mask_args` does, and in `reader._vision_input` (`describe`, unused live).
  Then the screen line can say "Password apps blacked out." again.
- Not deleted by Delete my data (said so in the confirm and policy): ~/miyagi (lessons, progress: engine side),
  the anonymous install token (install.bin), the account link on miyagi-cloud, the local error log and saved crash
  reports, onboarding.json, telemetry/state.json.
- miyagi-cloud /v1/link and /v1/events are on claude/eng-proxy, not on integration/live or Render yet: the policy
  describes them with [CHECK] markers. Cloud follow-up: drop the user id from proxy log lines (app.py sets
  request.state.user on every proxied call), and a delete endpoint for the link and counts.
- auth.ts keeps `decided` in memory, so the login shows again on the next launch, not right away.

## Notes (finish round: telemetry merged, Adrian's edits, account link)
- Merged origin/michael/v2-integration (telemetry 3e54ecc7, cloud link, reconnect). One conflict, the Privacy.tsx header
  comment: kept this lane's code, took the integration wording for the telemetry switch.
- web/privacy.md: Adrian's text from 06330ea0 (adrian/legal-privacy) taken as written in its own commit, then
  re-checked against the code. Changed only where the code says otherwise:
  - key and token redaction (5.2) landed in the engine (integration/live 742ab87a, server/redact.py): screen text,
    coach requests, Explain this, step files; every screenshot blacks out rows that held a key. It matches by shape, so
    the policy says it can miss some. Help and pointing screenshots still do NOT black out password apps.
  - the lesson-folder scan (lesson/workdir.py, sent by claude.adapt_checks) is not redacted: said so.
  - crash sharing sends only {kind, app_version} (telemetry/core.ts crashEvent), never error lines; usage has no cost
    prop; /v1/events keeps daily counts per install (cloud/store.py events, claude/eng-proxy).
  - the account link: what /v1/link keeps (token hash + Supabase user id), sign-out never unlinks, another account
    signing in replaces it. The [DECIDE] on unlinking stays as a question.
  - the IP: used in memory to rate-limit installs, not stored (Adrian said "up to an hour": the key can stay longer).
  - one word that trips the brand lint (the editor's text caret) is reworded.
  Not taken: his other legal files (COOKIES, RISKS, TERMS, site cookie check). All his [TBD] / [DECIDE] / [CHECK]
  markers stay; DRAFT stays on line 1.
- facts.ts: two new rows, Account link ("When you sign in, miyagi’s server ties this Mac to your account.") and
  miyagi’s server ("Passes AI calls on. Keeps counts and cost, never your work."). Crash is now "Only the kind of
  error, never its text. Off unless you share."; usage "Lesson and step counts. Never your code or screen."
  The policy table has one row per panel row; facts.test.ts checks label and line together and the link and
  telemetry wording.
- Delete my data also removes userData/cloud-link.json (the local note of the link, no token). The cloud row stays.
- Stage shots not retaken this round (no visible windows allowed): privacy-panel.png shows the old crash and usage
  lines and lacks the two new rows. Retake headlessly before merge.

## Merge status
- v2-integration is merged into this branch; it can merge into michael/v2-integration after review. Draft PR #199
  (michael/app-privacy -> adrian/shell) stays open.

## Core requests
_None._ (settings.ts: one comment line for settings:delete, the lane's own handler.)

# funnel: activation analytics (branch `michael/app-funnel`)

Funnel: download → **first_launch → signed_in → permissions_granted → lesson_started → step_passed →
lesson_finished**, with the time between each. Download is counted on the site / GitHub release side (the app does
not exist yet); every first launch is also an install minted on the cloud (`tokens`).

## What it does
- `src/main/features/funnel.ts` (main only, no renderer, no handles) records, on this Mac, the FIRST time each
  milestone happened in `userData/funnel/state.json` (`{at: {name: iso}, sent: {name: iso}}`). Names and times only.
  - first_launch: the feature's first setup. signed_in: `cloud-link.json` linkedAt (cloudLink.ts).
    permissions_granted: Screen Recording and Accessibility both granted, read without prompting.
    lesson_started / step_passed / lesson_finished: engine events, through telemetry/core's lesson tracking (no
    replays, no skipped steps).
- It sends them to miyagi-cloud `POST /v1/funnel` (`funnel/core.ts` has the contract) only when ALL hold: Settings ›
  Privacy "Share crash reports and usage" is on (off by default), MIYAGI_TELEMETRY isn't off, the launch gate is
  open, the install is linked to a signed-in learner, and an install token exists. No user id is sent: the cloud
  joins install → Supabase user through its `links` table. Never screen content, keystrokes, titles, paths or emails.
- 202 marks those times sent; 404 / 400 / 413 / 422 stop for the run; anything else retries next tick (30 s).

Cloud side: branch `claude/eng-proxy-funnel` (PR into `claude/eng-proxy-next`): `POST /v1/funnel`,
`GET /admin/funnel?days=N`, table `funnel` (earliest time per install and name), deleted with the account;
`cloud/migrations/20261122_funnel.sql` (Supabase, file only) and `cloud/sql/funnel.sql` (dashboard queries).

## Tests
- `test/funnel.test.ts`: 7 offline tests (order and shape, gating, MIYAGI_TELEMETRY, resend rules, 404, skips and
  replays, core helpers). Full app suite: 578 passed. `npm run typecheck` green.

## Core requests
1. **Account delete**: add `'funnel'` to `USER_DATA_DIRS` in `main/features/accountDelete/wipe.ts` (and its test), so
   `userData/funnel/` is wiped with the account (the cloud rows already are).
2. **Privacy facts**: one line under "usage" in `renderer/src/features/settings/privacy/facts.ts`: "With usage on and
   signed in: when you first launched, signed in, granted permissions, and started, passed and finished a lesson.
   Times only." (+ facts.test.ts).
3. `auth.ts onSignedIn` holds one hook (cloudLink.ts uses it). A multi-listener version would let funnel.ts record
   signed_in at the sign-in instant instead of at the link time (seconds apart today).

## Decisions (Michael, Nov 22)
- The funnel stays on the existing "Share crash reports and usage" switch: no separate toggle (Core request 3 dropped).
- Milestones recorded before opt-in may be sent after opt-in (names and times only).
- Cloud side merged into `claude/eng-proxy-next` (staging, #244, 07852563): POST /v1/funnel, GET /admin/funnel,
  35-day retention into `funnel_daily`, deleted with the account (every linked install).

## Still needs Michael's yes
- Promoting the cloud to `claude/eng-proxy` (the Render prod deploy).
- Applying the Postgres migration (file only; no Postgres move is planned).
- This app PR stays a draft into `adrian/shell` for Adrian's review.

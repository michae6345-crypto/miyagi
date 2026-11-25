# signincard (Linear MIC-17, app side)

**Status:** v1 built, stage-checked; `cloud.notice` wired end to end (Nov 24) · **Port:** 5201 (stage only) · **Branch:** `michael/app-signin-card`

## Goal
When the engine's shared-lesson-cache client (`server/lesson/cloud_cache.py`, `on_notice`) hears that the cloud refused a
lesson build claim, the island says so calmly. The lesson still builds on this Mac either way.

- **401 `signin_required`** → sign-in card: "Sign in to build new lessons" / "Lessons you've opened still work."
  **Sign in** (the one primary) starts the existing Google flow (`features/auth` `signInWith('google')`); **Not now**
  and **Esc** close it. Sign in spins while the browser is out; a landed sign-in closes the card and the pill says
  "You're signed in." A failure shows auth's own line under the buttons.
- **429** → one cap line with the reset time in the learner's local time, from `resets_at`, told apart by `limit`:
  `anon_daily_cap` (guest help), `user_daily_cap`, `daily_requests`/`daily_spend`, `daily_usd` (global brake),
  `lesson_builds` (month), `*_hourly` (rate), `new_installs` (full), anything else. Esc closes it; it leaves after 10 s.
- Any other 401 (unknown install token: the token self-heal owns it) and 403 get no UI.
- **451 `region_unavailable`** (the cloud's region block, eng-proxy-next PR #267) → the region line: "miyagi isn't
  available in your region yet." No Sign in (it would not help), **Not now** and **Esc** close it, once per launch; no
  sign-in card after it. It comes from the engine's `cloud.notice {reason: "region_unavailable", status: 451}` (once
  per engine run) or from main's install mint (`cloud.ts` CloudView.region: POST /v1/install answered 451, so no
  engine token exists). It shares the 56 slot with the cap line. Main never re-mints or auto-retries after a 451
  (cloud.ts), and `cloudSession` returns `region` with no heal and no backoff. Onboarding and the startup status show
  the same words instead of "Couldn't set up access".

## Owns
- `app/src/renderer/src/features/signincard/` (notice.ts pure parsing/formatting, store.ts, Card.tsx, index.tsx, web.ts)
- `app/mock/scenarios/signincard.json`, `app/test/signincard.test.ts`, `app/agents/shots/signincard-*.png`

## Contract
- **In** (engine → app), the dict `on_notice` yields: `{reason, status, resets_at?}`, sent as
  - `cloud.notice {reason, status, resets_at?}`: the main path (in the contract and `wire.ts` KNOWN), or
  - `error {message, notice: {reason, status, resets_at?}}`: the fallback, kept (`Error` allows extra fields,
    `wire.ts` passes the payload through). The store drops that error's generic pill line.
- **Engine** (`integration/live`): `Engine.watch_cloud` registers `cloud_cache.on_notice` and emits `cloud.notice`
  with only reason, status and resets_at (no token, no user id), once per refused claim, never also as an `error`
  (`server/tests/test_cloud_notice.py`).
- **Out**: none (Sign in goes through main's `auth:google`, the same IPC the login window uses).

## Plugs in as
islandModes: `signin-card` 57 (width 336), `cap-line` 56 (width 480). Above the build card (45, the notice lands
mid-build), below `err-limit` 58 and the off-track card 70. Both gated on `core/gate` like the errors cards.

## Test
`npm run dev:web -- --port 5201 --strictPort` → `http://localhost:5201/?scenario=signincard&size=1440x900&clean&nt=<v>`,
`v` = `signin | signin-error | anon | user | daily | global | builds | rate | full | token | region`. Shots:
`~/miyagi/tools/playwright/signincard.mjs 5201 app/agents/shots` (headless).
Unit: `test/signincard.test.ts` (parsing, classify, local reset time in fixed zones, copy ≤12 words, store paths).

## Core requests (done Nov 24)
1. **Done.** **Contract + wire:** add `"cloud.notice": { reason: string; status: number; resets_at?: string }` to
   `shared/contracts/events.ts` (+ `CloudNotice` in `events.py`) and `'cloud.notice'` to `KNOWN` in
   `app/src/common/wire.ts`. The store now subscribes without a cast; the `error {notice}` transport stays as a
   fallback.
2. **Done.** README island priority table: add 56 `cap-line` and 57 `signin-card` (signincard).

## Notes
- No hue anywhere (no red, no amber): the bonsai, white text, a quiet + a primary button.
- Reset time: `Intl.DateTimeFormat` in the system zone: "at 4:00 PM" today, "tomorrow at 9:30 AM", else "on Nov 30";
  none (→ "It resets soon." / "Try again later.") when missing, bad or past. "4:00 PM" never wraps apart.

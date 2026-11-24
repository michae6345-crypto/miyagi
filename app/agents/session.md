# session: the app side of miyagi-cloud's POST /v1/session (Linear MIC-30)

**Status:** v1 built, offline-tested, stage-checked (Nov 24) · **Port:** 5262 (stage only) · **Branch:** `michael/app-session`

## Goal
After a Google sign-in and on every launch while signed in, the app asks miyagi-cloud for the account's state
(`POST /v1/session`, merged on `claude/eng-proxy-next` in PR #264). Settings › Your own key shows the plan and today's
use ("$0.42 of $3.00 today · resets 4:00 PM", local time). When the cloud wants an account to build (`signin_mode`
"build" or "all") and the learner is a guest, the sign-in card shows as a new lesson build starts.

## Owns
- `app/src/main/features/cloudSession.ts` (triggers, IPC) and `cloudSession/client.ts` (protocol, retries, cache)
- `app/src/renderer/src/features/session/` (model.ts pure, store.ts, web.ts stage stand-in, index.tsx)
- `app/mock/scenarios/session.json`, `app/test/cloudSession.test.ts`, `app/test/session.test.ts`,
  `app/agents/shots/session-*.png`, `~/miyagi/tools/playwright/session.mjs`
- Small edits: `cloudLink.ts` (triggers moved out; createLinker kept for the 404 fallback), `cloud.ts` (`healInstall()`),
  `auth.ts` (`onSignedOut`, `isSignedIn`), `accountDelete/wipe.ts` + `settings/erase.ts` (session.json), Settings
  `sections/Account.tsx` (the plan group), `signincard/store.ts` (the build-start hook), `test/harness.ts` (FakeCloud
  serves /v1/session when `session` is set)

## Contract
```
POST <cloud>/v1/session   Authorization: Bearer <mi_ install token>   {"access_token": "<Supabase JWT>"}
200 {account: {id, email_verified}, plan, caps: {daily_usd, used_usd, tokens, used_tokens, resets_at}, linked: true,
     signin_mode: "off" | "build" | "all"}   ("0" is read as off too)
401 bad_install_token → cloud.ts healInstall() (the self-heal), retry once
403 bad_access_token  → auth.ts refreshedAccessToken(), retry once (403 too_many_installs: no retry)
503 / 5xx / offline   → keep the cache, retry 30 s, 2 min, 10 min, 30 min
404                   → an older cloud: POST /v1/link (cloudLink.ts createLinker)
```
- Cache: memory + `userData/session.json` = `{plan, caps, signinMode, linked, fetchedAt}`. Never a token, the email or
  the account id. On the Delete account list (`USER_DATA_FILES`) and Delete my data (`SIGN_IN_FILES`).
- Sign-out: plan and caps leave the cache; the mode and the link stay (sign-out never unlinks on the cloud).
- Renderer: `session:get` → `SessionView {signedIn, linked, signinMode, plan?, caps?, fetchedAt?}` (main `viewOf`,
  renderer `cleanSession`: bounded, plan/caps only while signed in); `feat:session` on every change. Opening the
  section refreshes in the background when the answer is over 5 minutes old.

## Test
`npm run dev:web -- --port 5262 --strictPort`, then
- `/?scenario=settings&window=library&page=settings&auth=signedin&session=caps` › Your own key (also `session=pro`)
- `/?scenario=session&session=build` (or `all`, or `none` = off): a build starts after 1.5 s; the card shows for
  build/all, not for off
Shots: `node ~/miyagi/tools/playwright/session.mjs 5262 app/agents/shots` (headless).

## Core requests
_None._ (No contract, core, preload or theme change was needed.)

## Open
- A learner who has never signed in has no session answer, so the app doesn't know `signin_mode` yet: the card then
  waits for the cloud's notice (`cloud.notice` 401 signin_required), as before. Once signed in once, the mode stays
  cached through sign-out. If the build-start card should reach first-time guests, the cloud's `GET /healthz` already
  says `require_signin`; reading it on launch is a small follow-up (a decision for Michael: one more call per launch).
- cloud/README says `signin_mode` "off"; the brief said "0". Both read as off.
- UNVERIFIED in Electron and against the real miyagi-cloud (offline only, cost freeze).

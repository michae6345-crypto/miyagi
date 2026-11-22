# age-delete (compliance: age step at sign-up, delete account)

**Status:** pass 1 done: typecheck green, app tests 444/444 + src tests 77/77, build green, brand lint clean, stage
walked headlessly (38 checks, animation sampled per frame). Electron not run (no visible windows in this lane); the
cloud endpoint is mocked (miyagi-cloud's /v1/account/delete is being built in parallel) · **Priority:** P0 (before
strangers install) · **Port:** 5733 · **Branch:** `michael/app-age-delete` (from `michael/v2-integration` 833ff93c) ·
**PR:** #240, draft into `adrian/shell`

## Goal
1. **Age step.** Before Google sign-in and before "Continue without an account": a neutral "When's your birthday?"
   screen. Under 13: a calm final screen, nothing sent, a block flag kept. 13 to 17: a parent or guardian step. 18+:
   straight to sign-in. Only the result is stored, never the date.
2. **Delete account.** Settings › Privacy: a two-step delete that asks miyagi-cloud to delete the account and this
   install, then wipes everything miyagi keeps on this Mac and starts again from the first-run screen.

## Owns
- `app/src/renderer/src/features/agegate/` (new): `age.ts` (maths + the record, pure, shared with main), `AgeFirst.tsx`
  (the step machine and its motion), `Steps.tsx` (Birthday, Guardian, Blocked), `store.ts`, `web.ts` (stage).
- `app/src/main/features/agegate.ts` + `agegate/store.ts` (userData/age.json), `accountDelete.ts` +
  `accountDelete/server.ts` (the cloud call) + `accountDelete/wipe.ts` (the erase list) (new).
- `settings/sections/Privacy.tsx` (the delete row), `settings/privacy/erase.ts` (now the Delete account flow),
  `privacy/deleteWeb.ts` (stage), `privacy/facts.ts` DELETE copy, `web/privacy.md` "Deleting your data".
- `app/mock/scenarios/agegate.json`, `test/ageDelete.test.ts`, shots `agents/shots/age-*.png`, `delete-*.png`.

## Done when
- [x] Birthday: month/day/year pickers, nothing pre-filled, no default year, no cut-off hint, no "over 13" box;
      Continue off until a real, not-future date. "By continuing you agree to the Terms and Privacy" (openLegal).
- [x] Under 13: final screen; only `{blockedUntil}` saved; Esc, Back, reload and re-entry can't get past it.
- [x] 13 to 17: guardian step, box unchecked, Continue off until checked; Back and Esc return to the birthday.
- [x] 18+: straight to sign-in. Sign-in says "Google shares your name, email and photo with miyagi."
- [x] Only `{band, confirmed}` or `{blockedUntil}` stored; never the birth date (tests check the file).
- [x] Guest path gated: the age step wraps the whole login screen; main refuses auth:google / auth:continue before it.
- [x] Transitions animate (sampled per frame, below), reduced motion is fades only.
- [x] Delete account: two-step, no red, lesson folders unchecked, server first, unreachable deletes nothing and offers
      Try again, pending says 30 days, full local wipe, sign-out, restart to the first-run screen.

## The age step
- Hook (the smallest change): `features/auth/Login.tsx` now exports `Login` as `<AgeFirst><SignIn/></AgeFirst>` (the
  old body renamed `SignIn`), so both hosts get it: the home window's flow (login phase, before #237's consent) and the
  standalone login window (the Account page's Sign in). No change to the flow's phases or store.
- Record (`age.ts`): `{band: '13-17' | '18+', confirmed: 'YYYY-MM-DD'}` or `{blockedUntil}`. blockedUntil is the
  **first of the month after the 13th birthday**, so the file can't be turned back into the birth date and errs late.
  Feb 29 birthdays count on Mar 1 in common years. main's `mergeRecord`: a block in force wins over any later write;
  a lapsed block is dropped and the step asks again; main stamps `confirmed` with its own clock; stray fields dropped.
- Main (`main/features/agegate.ts`): `agegate:get`, `agegate:set`, broadcast `feat:agegate`; `ageStepCleared()` for
  auth.ts. Esc: Guardian and a just-reached sign-in go back to the birthday (never while Google is pending); Esc on the
  birthday clears the pickers; Blocked has no way past.
- Terms/Privacy overlap with #237: the birthday screen carries the "By continuing you agree" line (every age group sees
  it, before sign-in); #237's consent step after the login keeps its own line unchanged. Not merged into one: the
  consent step is stamped per policy version by main (`prefs.consent`), this line is the sign-up agreement.

### Motion (house tokens; proof)
Forward: the old screen slides 16 px left and fades (`fade.out`, 120 ms); the new one comes 24 px from the right on the
spring with a 180 ms fade, 3 beats late; the bonsai (MARK_ID) stays put. Back runs the other way. Blocked rises 8 px
with `fade.slow`. Reduced motion: `useReducedMotion` sets the travel to 0 (MotionConfig alone snapped the exit's x).
Headless sampling of `[data-age-view]` computed opacity/transform every frame for 900 ms:

| Transition | frames | out: moved / max x | in: moved / mid-opacity / max x,y | settled |
|---|---|---|---|---|
| birthday → guardian | 54 | 33 / 16 | 22 / 5 / 24, 0 | 457 ms |
| guardian → sign-in | 53 | 32 / 16 | 22 / 4 / 24, 0 | 476 ms |
| birthday → sign-in (18+) | 56 | 34 / 16 | 25 / 6 / 24, 0 | 497 ms |
| birthday → blocked | 53 | 31 / 16 | 19 / 6 / 0, 8 | 453 ms |
| reduced: birthday → guardian | 55 | 0 / 0 | 0 / 6 / 0, 0 | 338 ms |

## Delete account
- Row "Delete account and data" (replaces Delete my data). Confirm: "Delete your miyagi account?" + "Deletes your
  account, what our server keeps, and this Mac's data. Cannot be undone." + "Also delete my lesson folders in
  ~/miyagi" (unchecked each time it opens). Cancel is the focused white primary, Delete an outline, Esc backs out.
- Main `account:delete {lessons}` (`accountDelete.ts`): `POST {cloud}/v1/account/delete`, Bearer = install token
  (`cloud.ts installToken()`), body `{access_token}` (`auth.ts accessToken()`) or `{}`. 200 → account
  deleted/none/pending; 401 → install already gone = success; 403 bad_access_token → `refreshedAccessToken()` once and
  resend, still refused → `{}`; anything else/offline/timeout → `{ok:false}` and NOTHING is deleted ("Couldn't reach
  miyagi's server. Nothing was deleted." + Try again). No install token: signed out = nothing on the server, go on;
  signed in = unreachable. Tokens never reach the renderer; logs carry status only.
- Then the wipe (`accountDelete/wipe.ts`, every path read from the code): userData keys.bin, auth.bin, login.json,
  cloud-link.json, install.bin, onboarding.json, age.json, prefs.json, reminders.json, updates.json, player-bounds.json
  (+ each `.tmp`), errors/ (error log, marker, pending report), crash-reports/, telemetry/; the logs folder's contents;
  Crashpad; the engine's demo/cache/{search,lessons,transcripts}, demo/runs, logs, ~/miyagi/state (state-dev in dev),
  ~/.cache/sandhacks-tutor/tts; ~/miyagi/lessons only when ticked. Electron's default session: clearStorageData,
  clearCache, clearAuthCache (the YouTube iframe's cookies and storage, the app's localStorage). The built-in lessons
  the bundle ships are copied back into the engine cache. A guard removes only paths strictly inside userData, logs,
  Crashpad, ~/miyagi or ~/.cache/sandhacks-tutor (an env override like `MIYAGI_LESSONS_DIR=/` is skipped).
  `cloud.ts forgetInstall()` drops the token from memory, the engine and disk.
- Renderer (`privacy/erase.ts deleteAccount`): account:delete → settings:delete (keys in memory and on the engine) →
  auth:sign-out (awaited) → the line ("Your account and this Mac's data are deleted." / "Deleted from this Mac. Your
  account goes within 30 days." / "Account deleted. Some files on this Mac stayed.") → `account:restart` after 2.6 s:
  a built app relaunches at the first-run screen (intro, age step, login); `npm run dev` can't relaunch itself (it logs
  and stays signed out at the login).
- Kept on purpose: userData/engine.json (which engine to run, no personal data), the engine itself, VS Code and its
  extensions. privacy.md's "Open" list (install token, account link, error log, crash reports, onboarding.json,
  telemetry state) is now all covered.

## Test
`npm run dev:web -- --port 5733 --strictPort`, then
- `http://localhost:5733/?scenario=agegate&flow=1&step=login&size=1440x900&clean` (birthday; `&age=blocked|teen|adult|keep`)
- `http://localhost:5733/?scenario=settings&settings=privacy&confirm=delete` (`&delete=pending|offline|partial`)
- Unit: `cd app && node --import tsx --import ./test/setup.mjs --test --test-force-exit test/*.test.ts`
  (`test/ageDelete.test.ts` imports age.test, agegate/store.test, accountDelete/server.test, wipe.test and checks the
  IPC gate; `test/privacy.test.ts` runs the new privacy/erase.test).
- Shots (headless_shell over CDP: no window, muted, 1440x900 @2x, dark unless named): `age-birthday`, `-birthday-filled`,
  `-birthday-light`, `-to-guardian-during`, `-guardian`, `-guardian-checked`, `-to-signin-during`, `-signin`,
  `-blocked-during`, `-blocked`, `-reduced-during`; `delete-row`, `-confirm`, `-deleting`, `-done`, `-offline`, `-pending`.

## Core requests (edits made outside the lane, kept minimal)
1. `src/main/features/auth.ts` (auth lane), +14 lines: import `ageStepCleared`; `auth:google` answers
   `{ok:false, reason:'age'}` and `auth:continue` answers `{next:'none'}` before the age step; new export
   `refreshedAccessToken()` (one forced refresh, for the 403 retry).
2. `src/main/features/cloud.ts` (cloud lane), +22 lines: new export `forgetInstall()` (token out of memory, engine and
   install.bin; no re-mint for RETRY_MS).
3. `src/renderer/src/features/auth/Login.tsx` (auth lane): the `AgeFirst` wrapper (old body renamed `SignIn`) and the
   "Google shares your name, email and photo with miyagi." line in the idle slot under the button.
4. `web/privacy.md` (privacy lane): "Deleting your data" rewritten to match (facts.test.ts requires the quotes).
5. Asks (not done): the policy's "Children and teens" [CHECK] can go once this merges; `agents/ports.json` could list
   5733.

## Audit (report only)
- Pre-checked consent/sharing/marketing: none found. shareTelemetry false, usageCounts false, crashReports 'ask',
  launchAtLogin false, voice off, reminders off, the crash card's "Always save" unchecked, no marketing opt-in exists.
  `ptt.enabled` defaults true (push-to-talk, on-device; not a sharing switch).
- Cancellable: Settings (Esc, Cancel), Upgrade (Not now + Esc), crash card (Don't save + Esc), guided setup (Back from
  step 2, Set up later; Esc only when reopened over home). #237's consent step has no Back, Cancel or Esc by design
  ("quit miyagi to leave"); the first screen of the flow (now the birthday) has nothing before it.
- "Cancel anytime." in `account/Pricing.tsx` (v2Cloud flag, off in normal builds): no cancel path exists (no billing).

## Open
- Not run in Electron: the relaunch after delete, the session API clears, the real engine paths, the main IPC gate.
- miyagi-cloud's /v1/account/delete is mocked to the stated contract; check the real answers once it deploys.
- Signed-in sessions from before this lane, and `MIYAGI_LOGIN=0` / `MIYAGI_SKIP_LOGIN=1` runs, never pass the login
  screen, so they never see the age step.
- The engine may write ~/miyagi/state again between the wipe and the relaunch if a lesson is running.
- 401 with a signed-in learner reports success though the account itself was not part of that call (per the contract).

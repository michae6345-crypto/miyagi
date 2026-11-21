# cloud-link: tie this Mac's install token to the signed-in learner (branch `michael/app-cloud-link`)

Ends `TODO(cloud-link)` from agents/auth.md. Main process only, no UI.

## What shipped
- `src/main/features/cloudLink.ts` (new feature). After a Google sign-in, and on launch, it sends
  `POST <cloud>/v1/link` with `Authorization: Bearer <mi_ install token>` and `{"access_token": "<Supabase JWT>"}`.
  - When: right after each successful sign-in (always, the cloud makes it idempotent); once on launch, 4 s after start
    (never on the UI's path); whenever the install token appears or changes (first mint, self-heal). The launch and
    token-change checks skip when `userData/cloud-link.json` already says this install (host + token id) is linked to
    this learner (the JWT's `sub`, read unverified, only to compare).
  - The access token comes from `auth.ts accessToken()`, which refreshes an expiring session first. A token still
    expired after that (offline) is not sent.
  - 200 `{ok: true, user_id}`: `userData/cloud-link.json` = `{userId, linkedAt, host, tokenId?}`. Never a token.
  - 404 (an older cloud): skipped silently. 401 / 403 / 503 / other / offline / timeout (10 s): one log line, status
    only, never a token or a body. Nothing is saved on a failure, so the next launch tries again.
  - Sign-out never unlinks and never touches cloud-link.json; the install keeps working anonymously.
  - Calls run one after another (a sign-in during the launch check cannot race it). `link()` never throws.
- `src/main/features/auth.ts`: the TODO block is gone; new `onSignedIn(fn)` export and a one-line
  `signedInHook?.()` where the sign-in succeeds. Nothing else changed.
- `src/main/features/cloud.ts`: `installToken()` and `onInstallToken(fn)` exports (main only), fed from `apply()`.
- Offline tests, `app/test/` (no network: a fake Supabase and a fake miyagi-cloud behind a stubbed `fetch`; only the
  auth loopback on 127.0.0.1:47217 is reached for real; `electron` and `publicConfig` resolve to fakes):
  ```bash
  cd app && node --import tsx --import ./test/setup.mjs --test --test-force-exit test/*.test.ts
  ```
  29 tests: PKCE success (verifier matches the challenge, renderer sees no token), state mismatch / wrong path (404,
  flow survives), refused code (expired, other msg, wrong verifier), callback errors (access_denied, provider misconfig,
  Google's code never shown), cancel then retry, expired-token refresh (rotation saved), refused refresh signs out,
  offline refresh keeps the session, another project's session dropped, corrupt auth.bin, sign-out revoke (and
  refresh-before-revoke); link 200 / already / re-link for another learner or token / 404 / 403 / 401 / 503 / 500 /
  offline / timeout / untrusted 200 / signed out / no install / expired; sign-in links end to end; expired session
  refreshes then links; sign-out keeps working anonymously.

## Core requests
1. `package.json`: a `"test"` script, `node --import tsx --import ./test/setup.mjs --test --test-force-exit test/*.test.ts`
   (no new package: tsx is already a devDependency; `test/setup.mjs` uses Node's `module.registerHooks`, Node 22.15+).
2. `tsconfig.node.json`: add `"test/**/*"` to `include` so `npm run typecheck` covers the tests (they typecheck clean
   today with a temporary config that does exactly that).

## Open
- UNVERIFIED in Electron and against the real miyagi-cloud (offline only, by the cost freeze). The cloud side of
  `/v1/link` must match the contract above.
- A 401 from `/v1/link` (the cloud forgot the install token) only logs; the proxy's own 401 already triggers
  cloud.ts's self-heal, and the new token is linked through `onInstallToken`.

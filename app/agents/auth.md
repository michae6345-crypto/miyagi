# auth: first-run login (branches `michael/app-login`, then `michael/app-login-wire`)

Flow: **branded intro** (the bonsai grows up out of its pot in the middle of the window, the wordmark settles under it)
→ **Sign in to miyagi** → **guided setup** (onboarding) → home.

**One window (lane oneflow, Nov 21):** on a first launch all of this happens inside the home window (the shell's flow
layer, `features/shell/flow/`, see agents/onboarding.md "One window"); the login window below is now only a fallback
(the Account page's Sign in). The login is lighter: one big white **Continue with Google**, a quiet line "Apple ·
GitHub · coming soon", **Continue without an account** under it; no New / Returning toggle. While the browser is open
the button morphs into "Waiting for Google…" (spinner, a faint band crossing it) with "Finish in your browser ·
Cancel"; a failure's plain-words reason fades in under the button with Try again (no shake, no hue).
`Login({onContinue})` moves the flow on; `auth:continue` opens nothing in the flow (onboarding.ts `onLoginDone`
returns nothing while no login window is open).

- **On by default**: `LOGIN_ENABLED = true` in `src/common/flags.ts`, separate from v2Cloud. `MIYAGI_LOGIN=0` turns it
  off for one run. The plans, pricing and usage mock stays behind v2Cloud=false.
- **Backend config is committed** (`src/main/publicConfig.ts`): the Supabase project URL and its publishable key, both
  public by design. A packaged build needs no `.env`. Override at build time with `MAIN_VITE_SUPABASE_URL` /
  `MAIN_VITE_SUPABASE_ANON_KEY`; the same names in the process environment count only for an unpackaged dev run (a
  shipped app never lets an env var send the sign-in or the refresh token to another host). No client secret or service
  key anywhere in the app: Supabase holds the Google secret.
- **Google**: live, through the main process. System browser + OAuth 2.0 PKCE (S256) via **Supabase Auth**, one-shot
  loopback redirect `http://127.0.0.1:47217/auth/callback?state=<random>`. A callback whose state does not match is
  ignored (404) and cannot end or hijack the flow. The browser opens through `safeOpenExternal` (the project host is on
  the allowlist). No webview, no secret. Esc, Cancel or closing the window cancels, also during the code exchange.
  Esc and leaving the login mid-wait are handled in Login.tsx itself (`useCancelOnEsc`), so the home window's flow
  and the standalone login window behave the same.
- **Session**: only in `userData/auth.bin`, encrypted with safeStorage (Keychain), with an absolute expiry and the
  project URL it belongs to (a session for another project is dropped unsent). The access token is refreshed ~5 min
  before it expires (`grant_type=refresh_token`, one at a time because Supabase rotates the refresh token), on launch
  when due, and on wake. A refused refresh (400/401) signs out; a network failure retries with a backoff. Sign-out
  forgets it at once and revokes it best effort (`/logout?scope=local`).
- **The renderer only ever sees `{name, email, avatarInitial}`** (plus `signedIn`), from `auth:get` and the
  `feat:auth:changed` broadcast. Never a token, code, verifier or URL.
- **Continue without an account** is always there (Cancel takes its place only while a browser sign-in is pending). It
  goes straight to setup. Signed in, or continued without one: the choice is saved (`userData/login.json`, non-secret)
  and the login never shows on launch again. Closing the login with the red button opens setup too (the login shows
  again next launch, since nothing was chosen).
- Apple and GitHub: placeholders. A click says "<Provider> sign-in is coming soon. Nothing was sent."
- **Account page (shell)**: signed in: avatar initial, name, email, Sign out, Use your own key. Signed out: "Sign in to
  sync your progress across Macs" with Sign in (opens the login window). The sidebar chip follows: initial + name +
  email, or "Not signed in / Sign in to sync".

## Files
- `src/renderer/src/features/auth/`: `AuthView` (the `auth` window: onboarding's branded `Intro`, then `Login`, in one
  LayoutGroup so the tree flies into the header), `Login`, `Avatar`, `store` (also the signed-in user for the shell),
  `model`, `web` (stage stand-ins), `index` (registers the `auth` window). The placeholder `Intro.tsx` is gone.
- `src/main/features/auth.ts`: `auth:get`, `auth:google`, `auth:cancel`, `auth:continue`, `auth:sign-out`; broadcast
  `feat:auth:changed`; exports `loginEnabled`, `needsLogin`, `onLoginDone`, `accessToken` for main.
- `src/main/publicConfig.ts`: the public Supabase config.
- Also touched (other lanes, small): `main/features/onboarding.ts` (first-run order), `main/features/launch.ts` (a Dock
  click brings the login forward), `features/shell/pages/AccountPage.tsx`, `features/shell/Sidebar.tsx`,
  `features/shell/Shell.tsx` (Account caption), `features/shell/store.ts` (`openPage` via `openLibrary`),
  `features/account/AccountWindow.tsx` (the `login` early return removed), `features/account/model.ts` (stage
  `?v2Cloud=0`).

## Core changes made (minimal, additive; Michael's go-ahead, Nov 20)
1. **`auth` app route**: `theme.windowSize.auth = { w: 944, h: 640 }` (the first-run size, so intro → login → setup stays
   in one spot), `'auth'` in `core/surfaces.ts` `AppRoute`, in `main/appWindows.ts` `APP_ROUTES` and in `bridge.ts`'s
   stage `APP_ROUTES`. The account window's `login` view is gone.
2. **`openLogin(view?)`** in `core/surfaces.ts` (`'intro'` | `'login'`).
3. **`openLibrary(target?)`** in `core/surfaces.ts` now also takes `{id?, page?, section?}` (shell core request 1).
   `openLibrary()` and `openLibrary(id)` work as before.
4. **First-run order** in `main/features/onboarding.ts` (auth core request 2): while `needsLogin()`, the login window opens
   first (view `intro`, or `login` if the intro already played) at the first-run size and spot; `onLoginDone` opens
   setup without the intro and marks it seen. The intro hands off to login inside the login window.
5. **safeOpen allowlist**: the committed Supabase project host (`SUPABASE_HOST` from `publicConfig.ts`, the exact
   project, not all of `supabase.co`), so the sign-in uses the strict `safeOpenExternal`.
6. **`LOGIN_ENABLED`** in `src/common/flags.ts`.
7. `main/publicConfig.ts` (new file, main only).

## See it (stage)
`npm run dev:web -- --port 5951`, then (`&v2Cloud=0` shows the shipped Account page instead of the plans mock):
- `http://localhost:5951/?window=auth&view=intro&size=1440x900&clean&v2Cloud=0`: intro, then login. Continue without an
  account opens setup; walk it to Start, which opens home.
- `…?window=auth&view=login…`: the login without the intro
- `…?scenario=home&window=library&page=account&size=1440x900&clean&v2Cloud=0`: Account signed out; add `&auth=signedin`
  for signed in
- `&auth=fail` (timeout line), `&auth=unset` (not configured line)

The stage's Google box "signs in" a fixture after ~1.6 s. Shots: `miyagi-v2/screens/login/login-*.png`. In the stage the
setup window opens at the stage's onboarding size (720×560); Electron opens it at the first-run size (944×640).

## Status
- Done: login wired to the real Supabase project, on by default; first-run order; Account page and chip; session in
  safeStorage with refresh and sign-out; `npm run typecheck` green; walked in the stage (headless).
- UNVERIFIED in Electron: the real browser round trip, token exchange, refresh, sign-out revoke, the window hand-offs
  (login → setup with no gap), and the Dock click during the login. Google OAuth is in testing mode: only test users
  can sign in.

## For Michael to test (real app)
1. Fresh first run (move `~/Library/Application Support/miyagi/{onboarding.json,login.json,auth.bin}` aside): the intro
   plays in the login window, the tree flies into "miyagi login".
2. Continue without an account → setup opens in the same spot, no intro; finish → home. Relaunch: no login.
3. Fresh again, Google (a test user): browser opens on Supabase/Google, the tab says "Back to miyagi", the app shows
   "Signed in as …", Continue → setup. Home's Account page and chip show the initial, name, email.
4. Esc / Cancel while the browser is open; try again (the second try must work).
5. Leave it over an hour (or sleep the Mac), then quit and relaunch: still signed in (refresh). Sign out: the page and
   chip flip to signed out; relaunch: still signed out, no login on launch.
6. Account page signed out → Sign in → the login window (no intro) → Google → Continue closes it.

## Sign-in errors (Nov 21, `michael/app-login-fix`)
Every OAuth error that comes back on the loopback (`?error=…&error_code=…&error_description=…`, which Supabase also
puts in the #fragment) is now explained in plain words, in the browser tab AND in the app (the line stays until the next
click; miyagi comes forward): `access_denied` → "This Google account isn't allowed yet. Ask to be added as a tester, or
continue without an account."; Supabase's "Unable to exchange external code" → reason `provider` (the Google client
secret in Supabase does not match the Google client); anything else shows Supabase's `error_description`; a refused
code exchange shows Supabase's `msg` (expired / already used → "Try again."). Before this, every one of these showed the
same "Sign-in did not finish … try again in miyagi" and the app dropped the reason.

## Core requests (still open)
- `MiyagiWordmark`'s `height` prop loses to the preflight's `img { height: auto }`; callers pin it with a class. Worth
  fixing in `core/ui/Mark.tsx` (`style={{ height }}`).

## Cloud link (shipped, `michael/app-cloud-link`)
The old `TODO(cloud-link)` seam is done: `main/features/cloudLink.ts` sends `POST /v1/link` (install token as Bearer,
`{"access_token": <Supabase JWT>}`) after each sign-in (auth.ts `onSignedIn`) and on launch while signed in and not
linked yet. Sign-out does not unlink. The JWT never goes to the engine or a renderer, and is never logged. Details,
tests and Core requests: agents/cloud-link.md.

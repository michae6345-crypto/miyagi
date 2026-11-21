# auth: first-run login (branch `michael/app-login`)

Flow: **intro** (the bonsai grows up out of its pot in the middle of the window, the wordmark settles under it) →
**miyagi login** (New user / Returning user, three sign-on boxes at the bottom) → **guided setup** (onboarding) → home.

- Google: live, through the main process. System browser + OAuth 2.0 PKCE via **Supabase Auth**, one-shot loopback
  redirect `http://127.0.0.1:47217/auth/callback`. No webview (Google blocks embedded sign-in), no client secret in
  the app: Supabase holds it. The session is kept in `userData/auth.bin`, encrypted with safeStorage (Keychain), like
  the BYOK keys. The renderer only ever sees `{name, email}`.
- Apple and GitHub: placeholders. A click says "<Provider> sign-in is coming soon. Nothing was sent."
- "Continue without an account" goes straight to setup (the app stays local-first).
- Behind the same switch as the account sheet: v2Cloud (`VITE_MIYAGI_V2_CLOUD=1` build + `MIYAGI_V2_CLOUD=1` run).

## Files
- `src/renderer/src/features/auth/`: `AuthView` (LayoutGroup: intro → login), `Intro`, `Login`, `store`, `model`,
  `web` (stage stand-ins), `index` (registers the feature, no window of its own yet).
- `src/main/features/auth.ts`: `auth:get`, `auth:google`, `auth:cancel`, `auth:sign-out`.
- `features/account/AccountWindow.tsx`: one early return mounts `AuthView` for view `login` / `login-now`.

## See it (stage)
`npm run dev:web -- --port 5700`, then:
- `http://localhost:5700/?window=account&view=login`: intro, then login
- `…&view=login-now`: login without the intro
- `&auth=signedin` (already signed in), `&auth=fail` (timeout line), `&auth=unset` (not configured line)

The stage's Google box "signs in" a fixture after ~1.6 s. Shots: `agents/shots/auth-1-intro.png`, `auth-2-login.png`,
`auth-3-signed-in.png`.

## Status
- Done: intro placeholder, login UI, New/Returning switch, three provider boxes, waiting + Cancel, signed-in card,
  Continue → onboarding, main-side PKCE flow and encrypted session. `npm run typecheck` green. Checked on the stage.
- UNVERIFIED in Electron: the real browser round trip and token exchange (needs the Supabase project below).
- Intro is a placeholder: swap in the intro lane's animated miyagi intro (features/onboarding) once it merges.

## One-time setup (Michael does the account steps and pastes any secret himself)
1. Redeem the YC Supabase deal ($300 / 12 months) on deals.ycombinator.com, then create a Supabase project.
2. Google Cloud Console → APIs & Services → OAuth consent screen (External, app name miyagi, support email),
   then Credentials → Create OAuth client ID → **Web application**:
   Authorized redirect URI = `https://<project-ref>.supabase.co/auth/v1/callback`.
3. Supabase → Authentication → Providers → Google: on, paste the client ID and secret (in the dashboard only).
4. Supabase → Authentication → URL Configuration → Redirect URLs: add `http://127.0.0.1:47217/auth/callback`.
5. Build/run config (public values, not secrets): `MAIN_VITE_SUPABASE_URL=https://<project-ref>.supabase.co`,
   `MAIN_VITE_SUPABASE_ANON_KEY=<publishable key>` (or `MIYAGI_SUPABASE_URL` / `MIYAGI_SUPABASE_ANON_KEY` for a dev run).

## Core requests
1. **An `auth` app route** so the login has its own window instead of the account window's `login` view:
   `theme.windowSize.auth = { w: 720, h: 560 }`, `'auth'` in `core/surfaces.ts` `AppRoute`, in `main/appWindows.ts`
   `APP_ROUTES` and in `bridge.ts`'s stage `APP_ROUTES`. Then drop the early return in `AccountWindow.tsx`.
2. **First-run order**: `main/features/onboarding.ts` should open the login first when v2Cloud is on and nobody is
   signed in (and the learner hasn't chosen "Continue without an account"), then onboarding after `continueToSetup`.
   Today the login is reached with `openWindow('account', {view: 'login'})`.
3. **safeOpen allowlist**: add `supabase.co` to `ALLOWED_HOSTS` (reason: Google sign-in start page) so `auth.ts` can
   use `safeOpenExternal` instead of its own validated `shell.openExternal`.
4. Note for core: `MiyagiWordmark`'s `height` prop loses to the preflight's `img { height: auto }`; the intro pins it
   with a class. Worth fixing in `core/ui/Mark.tsx` (`style={{ height }}`).

## Follow-up (not in this branch)
Tie the anonymous install token (`main/features/cloud.ts`, `POST /v1/install`) to the signed-in Supabase user on
miyagi-cloud (verify the Supabase JWT there), so quotas and history follow the account.

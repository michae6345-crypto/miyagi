# account

**Status:** in progress (lane claimed) · **Plan:** A9 · **Port:** 5194 · **Branch:** `michael/app-account` · **Flag:** `v2Cloud`

## Goal
The account surfaces from the miyagi v2 mockups, shipped as UI on mock data behind `v2Cloud` (off in a normal build): the account menu (plan, monthly help meter, Upgrade, My lessons, Settings, Use your own key, Sign out), the Upgrade sheet, Sign in, and Pricing on the paper tokens. No network, no auth, no billing, no quota that blocks a lesson.

## Owns
- `app/src/renderer/src/features/account/**`
- `app/src/main/features/account.ts` (allowlisted URLs only, no tokens, no protocol handler)
- `app/mock/scenarios/account.json`
- `app/agents/account.md`

## Mockups
Plan-AccountMenu, Plan-Upgrade, Plan-SignIn, Plan-Pricing.

## Done when
- typecheck green; no network; nothing blocks a lesson.
- "Use my own key" calls `openSettings('account')`.
- Meters are white (dark) or ink (paper), never green.
- Pricing on the paper tokens.

## Test
`npm run dev:web -- --port 5194` then `?scenario=account&account=menu|upgrade|signin|pricing&size=1440x900&clean`.

## Core requests
_None yet._

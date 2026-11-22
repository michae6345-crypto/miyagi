# age-delete (compliance: age step at sign-up, delete account)

**Status:** in progress (lane claimed) · **Priority:** P0 (before strangers install) · **Port:** 5733 · **Branch:** `michael/app-age-delete` (from `michael/v2-integration` 833ff93c) · **PR:** draft into `adrian/shell`

## Goal
1. **Age step.** Before Google sign-in (and before "Continue without an account"), a neutral "When's your birthday?"
   screen: month, day and year pickers, nothing pre-filled. Under 13: a calm final screen, nothing sent, a block flag
   kept. 13 to 17: a parent or guardian step. 18+: straight to sign-in. Only the age band is stored, never the date.
2. **Delete account.** Settings › Privacy: a two-step delete that asks miyagi-cloud to delete the install and the
   account, then wipes everything miyagi keeps on this Mac, and returns to the first-run screen.

## Owns
- `app/src/renderer/src/features/agegate/` (new)
- `app/src/main/features/agegate.ts`, `app/src/main/features/accountDelete.ts`, `app/src/main/features/accountDelete/` (new)
- `app/src/renderer/src/features/settings/sections/Privacy.tsx`, `settings/privacy/erase.ts` (the delete row)
- `app/mock/scenarios/agegate.json`, `app/agents/shots/age-*.png`, `delete-*.png`

## Done when
- typecheck green, the app unit tests green, brand lint clean, stage shots taken headlessly.

## Core requests
_Filled in as the lane goes._

## Notes

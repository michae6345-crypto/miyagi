# privacy (ROADMAP 5.4)

**Status:** claimed, not started (builds on `claude/telemetry`, which edits `settings/sections/Privacy.tsx`) · **Priority:** P1 (before strangers install) · **Port:** 5615 · **Branch:** `michael/app-privacy` (from `michael/v2-integration`) · **PR:** draft into `adrian/shell`

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
  5.1 and 5.2 (cropping, secret redaction) are NOT done: do not claim them.
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
`npm run dev:web -- --port 5615 --strictPort` → `http://localhost:5615/?scenario=full&settings=privacy`
(adjust to the settings stage params in `features/settings/env.ts`)

## Core requests
_None expected._

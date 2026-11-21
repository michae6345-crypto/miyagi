# privacy (ROADMAP 5.4)

**Status:** first pass done (on top of `claude/telemetry`; its switch is unchanged) · **Priority:** P1 (before strangers install) · **Port:** 5615 · **Branch:** `michael/app-privacy` (from `michael/v2-integration`) · **PR:** draft into `adrian/shell`

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
`npm run dev:web -- --port 5615 --strictPort` → `http://localhost:5615/?scenario=settings&settings=privacy`
(`&confirm=delete` opens on the delete confirm). Use the `settings` scenario, not `full`: `full` merges the player.
Unit: `cd app && node --import tsx --test src/renderer/src/features/settings/privacy/facts.test.ts src/main/features/settings/erase.test.ts`

## Notes (first pass)
- `privacy/facts.ts` is the one list (screen, code, editor, searches, videos, sign-in, keys, progress, crash, usage).
  Its header names the engine file behind every line (engine read from `origin/integration/live`; the server/ folder
  on this branch is a stub). `facts.test.ts` checks the copy rules and that `web/privacy.md` quotes every line.
- `privacy/Sees.tsx` renders it; Privacy.tsx keeps the telemetry switch as merged, adds the policy row (auth
  `openLegal('privacy')`, the existing allowlisted external-link path) and the new delete copy.
- Delete my data: main `settings:delete` removes keys.bin, then auth.bin and login.json (`settings/erase.ts`);
  the renderer resets prefs and calls `auth:sign-out` (auth.ts owns the session in memory and revokes it).
  `signIn: false` (a sign-in file stayed) shows "Keys and settings deleted. Couldn't clear sign-in." with Delete again.
- `web/privacy.md`: DRAFT with [TBD] for retention on miyagi-cloud, contact address, last-updated date.
- Stage shots: `shots/privacy-panel.png`, `privacy-data.png`, `privacy-confirm.png` (headless, no window).

## Open
- Not deleted by Delete my data (said so in the confirm and policy): ~/miyagi (lessons, progress: engine side),
  the anonymous install token (install.bin), the local error log and saved crash reports, onboarding.json.
- auth.ts keeps `decided` in memory, so the login shows again on the next launch, not right away.

## Core requests
_None expected._

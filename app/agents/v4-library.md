# v4-library: Library v4 and Plans

Branch `michael/v4-library` (from `origin/michael/app-ui-v4`). Design source: Adrian's `docs/ui-next` on `origin/adrian/ui-next` (mock screens `library`, `library-empty`, `plans`, `plan`, `plan-playlist`, `plan-goal`; README trim pass of Nov 24).

## Status

Done:
- **Library** (`features/library/Library.tsx`, the shell's Lessons page): full-width (1040) page. Tabs with counts (All, In progress, Ready, Finished, Plans) and a search toggle; Your plans (picture, next lesson, lessons left, a progress line); In progress / Ready to start / Finished tables (Lesson, Plan, Works in, Grows, Time, Progress, Opened; columns drop as the pane narrows, and a column with nothing on any row is left out); Start a plan (four plans with All 40 plans). The header's right side is New plan + New lesson (the one primary).
- **First run** (-27): one line, From a playlist / From a goal, eight plans to start, five short lessons (start one with `learn {query: goal, mode: "lesson"}`).
- **Browse plans** (-29, `features/plans/PlansPage.tsx`): entry rows, topic tabs with counts, search, Start here, and the three tables (Coding languages 13, Apps and tools 16, Going further 11; After = the plan's `needs`).
- **Plan page** (`PlanPage.tsx`): facts (works in, length, ends with, checked by, grows), picture + Start plan, the lessons table (passes when, grows, steps, time), The project (three checks), Rather follow a video (the plan's playlists), After this plan.
- **Plan from a playlist / from a goal** (`Dialogs.tsx`, 23-lesson-plans-10..17): playlist link → videos → lessons (each grows a skill), Ends with a project toggle, Just the first video / Add plan. Goal → Work in option chips (pastels: options only) → lessons from one or two catalog plans + the project.
- **Blender / CAD cards**: `Thumb.tsx` draws each plan's picture (code, mug, plate, web, table, plot, network, terminal), neutral only.
- **Catalog** (`features/plans/catalog.json`, `playlists.json` copied from `docs/ui-next/catalog`): replaces `presets/packs.ts` for these pages.

Not done:
- The lesson page (`lesson`, `lesson-blender` mock screens) is still the old `Detail.tsx` preview.
- `presets/packs.ts` still feeds Home's packs row (`Home.tsx`, not this lane's file).

## Wiring (contract)

The ui-v4 contract (`shared/contracts/UI-V4.md`, `app/mock/scenarios/ui-v4.json`) had not landed on `origin/michael/app-ui-v4` when this pass ended. Local typed placeholders, in one place each:
- `plans/store.ts` `MyPlan` / `mine` (the learner's plans) and `startPlan` / `addPlan`: today they send `learn {query: lesson.goal, mode: "lesson"}`; swap in the plan messages when they land.
- `library/Library.tsx` `V4Item` (`planId`, `passed`, `passedAt`, `openedAt`): read when present; Plan falls back to matching the title against the catalog, Opened to `updatedAt`.

## How to see it

`cd app && npm run dev:web -- --port 5253 --strictPort`, then `http://localhost:5253/?window=library&page=lessons` plus:
- `&plans=demo` (the mock's two plans), `&library=empty` (first run), `&plans=browse`, `&plan=intro-blender`, `&dialog=playlist` / `&dialog=goal`, `&appearance=light|dark`.

Shots: `agents/shots/v4-library-r4-ours-*.png` next to `v4-library-r4-mock-*.png` (light and dark; library also at 1024 and 1728).

## Remaining differences vs the mock

- Page title, header row, background and sidebar are the shell's: the title still says "Lessons" and sits on the 720 column (`shell/Shell.tsx` `pageWidth` gives `lessons` 720), so it is left of the 1040 content and the New plan / New lesson buttons. On Browse plans and a plan page the shell title stays above our breadcrumb and h1.
- Thumbnails are neutral grays (brand: pastels only on options), the mock's code lines are colored.
- No "Connected" tag on Works in (no connection state for the tool yet), no Share or ⋯ menu, no grid/list toggle.
- Lesson rows use the stage's sample items, so their Plan/Opened cells are empty until the engine (contract) sends plan and dates.
- Playlist skills come from matching video titles to the plan's skills (offline); the goal plan keeps the base plan's lessons in order (the mock picks Fillets over Add the hook).

## Core requests

1. Shell: give `lessons` the wide column (`pageWidth`), title it "Library", and let a page hide the header title for its sub-views (Browse plans, a plan).
2. Contract: plan messages (start plan, add plan from playlist/goal, my plans with progress) and `LibraryItem.planId / passed / openedAt`.

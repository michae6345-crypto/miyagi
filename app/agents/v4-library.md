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

Wired to the ui-v4 contract (`shared/contracts/UI-V4.md` "Plans", `events.ts`, mock `app/mock/scenarios/ui-v4.json`), merged at aa69cd90:
- **Types**: `plans/catalog.ts` re-exports `Catalog`, `CatalogPlan`, `CatalogLesson`, `CatalogSkill`, `CatalogProject`, `CatalogPlaylist`, `PlanLessonRef` from the contract; no local copies. `playlists.json` is now Adrian's full file (playlist `url`, video `id`s for `learn_url`).
- **Your plans** (`plans/store.ts`): the Library sends `plans.list {}` when it mounts; `mine` is the `plans` answer (`PlanState`: lessons with state, steps, openedAt/doneAt; nextIndex; minutesLeft), and every later `plans` push replaces it.
- **Starting**: a catalog plan sends `plan.start {catalogId, reqId}`, then its next lesson once `plans` answers (or locally after 2.5 s). Every plan lesson starts with `plan: {id, index}`: `library.start {id: libraryId, plan}` once built, `learn_url {url: watch?v=<videoId>, plan}` for a playlist lesson, else `learn {query: goal, mode: "lesson", plan}`. Remove plan sends `plan.remove {id}`. A plan page's lesson rows start that lesson.
- **Playlist dialog**: a pasted link sends `playlist.get {url, reqId}` and draws both answers (videos with "Matching skills to the videos", then the proposal's skills). Add plan sends `plan.start {playlistId, url, proposal}`; each unchecked video goes as `proposal.lessons[i].skip: true` (the contract's way: `plan.start` has no `skips` field), and `project: null` when "Ends with a project" is off. "Just the first video" skips every other video.
- **Goal dialog**: Enter sends `plan.propose {goal, tool?, reqId}`; "Putting a plan together" rows while `proposing: true`; then the proposal (lessons with skill, From = `from.planId`, minutes; the tools as option chips, picking one asks again with `tool`; `note` under the table). Add plan sends `plan.start {goal, proposal}`.
- **Library rows**: a lesson's plan, passed state and dates come from the PlanLesson whose `libraryId` (or `lessonId`) is the item's id: Plan = that plan, Finished = `state: "done"`, Opened = `openedAt` / `doneAt`. Lessons no plan claims match their title against the catalog and use `updatedAt`.
- **Fallbacks**: when no engine answers within 1.5 s the dialogs draw the catalog's playlist / `planFromGoal` through the same `PlaylistInfo` / `PlanProposal` shapes (`catalog.ts` `playlistInfoFromCatalog`, `proposalFromGoal`); `library:list` that never answers stops the skeleton after 4 s (`library/store.ts`), and Your plans shows as soon as `plans` arrives, even before the lessons.

## How to see it

`cd app && npm run dev:web -- --port 5253 --strictPort`, then `http://localhost:5253/?window=library&page=lessons&scenario=ui-v4` plus:
- nothing (Library with the contract's plans), `&plans=browse`, `&plan=intro-blender` (catalog plan), `&plan=neural-networks` (a plan in progress: passed lessons, Continue lesson 4), `&dialog=playlist` (paste `https://www.youtube.com/playlist?list=PLjEaoINr3zgGUwGwXlj9kBe7TrVWNjkyv`), `&dialog=goal` (type a goal, press Return), `&appearance=light|dark`.
- First run: `&library=empty&scenario=happy` (no plans answer). `&plans=demo` still seeds two plans when no engine answers.

Shots r6 (Nov 24): `agents/shots/v4-library-r6-ours-{library,first,plans,plan,mine,playlist,goal}[-1728]-{light,dark}.png` (1280x800 and 1728x1080) next to `v4-library-r6-mock-*-{light,dark}.png` (Adrian's `docs/ui-next/shots`).

## Remaining differences vs the mock

- Thumbnails are neutral grays (brand: pastels only on options), the mock's code lines are colored.
- No "Connected" tag on Works in (no connection state for the tool yet), no Share or ⋯ menu, no grid/list toggle.
- The stage's sample lessons (`library/web.ts`, the ui-v4 scenario has no `library` answer) carry no `teaches`, so the Grows column is left out there; their Plan/Opened cells fill once a plan lesson's `libraryId` matches.
- The shell's top-bar crumbs are plain text; the Library makes its earlier parts go back (delegated click, `Library.tsx useCrumbBack`).

Fix pass r6 (Nov 24): all three views render in the shell's v4 frame (PageFrame + PageHeader): one title on the content's left edge, New plan / New lesson flush right with the content, the shell's breadcrumb (Library / Browse plans / plan) instead of the in-page one and its second "Library" title. Contract wired (above). Skeleton rows no longer stay forever under `?scenario=ui-v4`.

## Core requests

1. Shell / styles.css: `.mg-page-frame:has([data-v4-frame]) > [data-legacy-header] { display: none }` sits in `@layer base`, so Tailwind's `flex` utility on LegacyPageHeader wins and the legacy title never hides. The Library repeats the rule unlayered (`plans/ui.tsx RowStyle`); the shell should move it out of the layer (it affects every v4 page).
2. Shell: `TopBar` crumbs could take an `onClick` per part (setCrumbs with `{label, onClick}`), so the Library's delegated click can go.
3. Shell: `LessonSearch` (the legacy header's Library actions) now renders nothing; Shell.tsx can drop it.

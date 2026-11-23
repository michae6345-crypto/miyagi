# skills

**Status:** design done (research, mockups in light and dark, PDF), sent to Michael Nov 22 for a yes before code · **Priority:** P1 (Michael: "a priority") · **Port:** see ports.json · **Branch:** `adrian/skills-tree`

## Goal
The Skills page becomes a real skill tree. A node is a skill ("Broadcasting", "Extrude") built up across lessons, not a lesson's steps. A real prerequisite graph runs underneath, across tracks. On top, the default **Path** view shows only the skills on the way to the learner's goal: a project at the right end, drawn left to right. **Map** shows every track grown up from one trunk. **List** shows one card per track. One NEXT and one primary button tell you what to do now. A new learner starts by picking what to make first.

Research with sources: `docs/skills/RESEARCH.md`. Mockups: `app/agents/shots/skills-01..07-{light,dark}.png`. Their source is `docs/skills/mock/index.html` (`?s=path|map|panel|list|empty|unlock|extras&t=light|dark`). Render with `node docs/skills/render.mjs <out> 1440 900 2 name=file:///...`. The PDF is built from `docs/skills/doc.html`.

## Owns
- `app/src/renderer/src/features/skills/**` (new): graph layout, nodes, the Path, Map and List views, the skill panel, the dock (NEXT, also ready, keep fresh), the goal picker, the unlock motion.
- `app/src/renderer/src/features/shell/pages/SkillsPage.tsx`: renders the new feature.
- `app/src/renderer/src/features/dashboard/Constellation.tsx`: retired from the Skills page. Its model (`features/dashboard/model.ts`: edges, cross, reviews, the four node states) is reused rather than rewritten.
- `app/mock/scenarios/skills.json`: the learner in the mockups.
- Later: skill chips on Library cards, the lesson-end recap and the weekly recap on Progress. These are small edits in those features, listed here when they happen.

## States (no legend; words sit on the nodes)
| State | Look |
|---|---|
| locked | dashed faint ring; says what it needs ("needs 3 skills") |
| ready | solid ink ring |
| practicing | ink ring with an inner ink arc (evidence so far, "2 of 4 steps") |
| mastered | green fill with an ink check. The only green |
| review (modifier) | mastered but due: a hollow green ring. Never demoted |
| capstone | rounded square with the bonsai, same state rules |
NEXT is a focus marker on exactly one node: a ring offset 3px plus the word. The page's one primary button points at it.

## Contract (asked of Michael, Nov 22)
- **In:** per skill `id, label, summary, track, kind, state, evidence, masteredAt, lastPracticedAt, review{dueAt}, lessons[{lessonId, stepIds, role}], example`. Per edge `from, to, kind: requires|helps, weight`. Per capstone `brief, requires, checks, starterFile, estMinutes, completedAt, artifact`. Per learner `goal, next, alsoReady[≤3], keepFresh[≤3], events[] + ack, week, portfolio`. Library items `teaches, uses, unlocks`. Steps `skillIds[]`.
- **Out:** `set_goal {capstoneId}`, `skills.ack {until}`, and the existing `learn` / `library.start` for NEXT.
- Fallback until the fields land: today's `Progress.skills[]`, with each track drawn as a short chain.
- **Landed (Nov 22, `contract:` commit on `michael/app-skills-tree`)**, all optional and additive in `shared/contracts/events.ts` + `events.py`: the graph rides on `progress` as `Progress.graph?: SkillGraphInfo` (`skills: SkillInfo[]`, `edges: SkillGraphEdge[]`, `capstones?: SkillCapstone[]`, `goal`, `next?: SkillPick`, `alsoReady`, `keepFresh`, `events?: SkillEvent[]` + `ackedUntil`, `week?: SkillWeek`, `portfolio?: PortfolioItem[]`). Nested, so it never collides with the existing `Progress.week` or the dashboard's `next[]`. `StepSummary.skillIds` / `OutlineStep.skillIds`, `LibraryItem.teaches / uses / unlocks`. Commands `set_goal {capstoneId}` and `skills.ack {until}` are in `AppCommands`; send them only when `engine.hello.capabilities` lists them (not in `V2_CAPABILITIES` until the engine handles them).
- App side: `features/skills/model.ts` `buildSkillGraph(raw, now)` turns either shape into one `SkillGraph` view model.

## Core requests
- If the unlock motion needs a shared stroke-draw helper, it goes in `core/ui/motion.ts` through the integrator.
- **`skills:artifact-image` (main handler, Nov 22).** The portfolio card shows a picture of the learner's own file (`PortfolioItem.artifact {kind: "image", path}`; the contract says the path is local, never a URL). The renderer's CSP (`src/renderer/index.html` img-src `'self' data: blob: https://i.ytimg.com`) and webSecurity block `file://`, so the renderer can't show it. Ask: a main handler `skills:artifact-image (path: string) → string | undefined` that returns a `data:image/(png|jpeg|gif|webp);base64,…` URL. It should only read a path the engine reported in the latest `progress.graph` (capstones[].artifact or portfolio[].artifact), only an absolute path with an image extension, real path resolved (no symlink escape), at most ~2 MB on disk (downscale or skip anything larger), and return undefined on any error. The renderer side is done (`features/skills/extras/Portfolio.tsx` `usePicture`): it calls `bridge.invoke('skills:artifact-image', path)`, accepts only a data: image of at most 2.8 MB, stops asking once the handler is missing, and keeps the file icon and name as the fallback. Until the handler lands, every card shows the icon.

## Done when
- Path, Map and List render the mock learner in light and dark at 1024, 1280 and 1728 wide, in one centered column where the view is a list.
- One primary button on the page. Green appears only on mastered. No pastels except option buttons.
- The skill panel opens from any node. Esc closes it.
- The unlock plays once per event and respects reduced motion.
- typecheck passes, and the stage at `?scenario=skills` shows each view.

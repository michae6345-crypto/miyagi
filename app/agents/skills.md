# skills

**Status:** built on `michael/app-skills-tree` (Nov 22): Path, Map, List, the panel, the dock, the goal header and picker, the unlock motion, zoom/pan/fit and search, in light and dark. Later extras (Library chips, recaps) are another lane · **Priority:** P1 (Michael: "a priority") · **Port:** see ports.json · **Branch:** `adrian/skills-tree`

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

## Build (Nov 22, `michael/app-skills-tree`)
- **Where:** `features/skills/` — `layout.ts` (pure layered layout: flat rows for a track's chain (`findRows`), longest-path layers with a balancing pass, way points for long edges, port-aware barycenter + transpose ordering, links set aside until nothing crosses and the layers taken again without them when that's shorter, isotonic packing on a half-slot grid with way points kept between their edge's ends, the trunk and the goal on the middle, no unlinked pair sharing a column; `placeGraph` with per-layer bands and an edge channel between them; `edgeRoute` straight through bands, one cubic per channel), `graphInput.ts` (what each view lays out, measured label lines, node geometry, bands), `TreeCanvas.tsx` (Path and Map), `SkillNode.tsx`, `ListView.tsx`, `Panel.tsx`, `Dock.tsx`, `Goal.tsx`, `SkillsView.tsx`, `store.ts`, `copy.ts`. Tests: `layout.test.ts` (zero crossings, grid and gaps, trunk and goal centered, rows, way points inside their span, no unlinked column sharing, no label overlap and no edge through any node or label at 1024 / 1280 / 1728 for the mock and the real-engine fallback, Path scale >= 0.85 at 1280 and 1728). Run from `app/`: `node --import tsx --test src/renderer/src/features/skills/*.test.ts`.
- **Zero crossings:** the mock's prerequisite graph cannot be drawn flat in layers (Path: loops→neuron and dot→neuron wrap the arrays chain; Map: one more). `layoutGraph` sets aside the fewest links (`hidden`: the one in most crossings, never a node's last drawn way in) and the canvas draws them only while their node is hovered or open. The resting tree has no crossings.
- **Michael's rules:** columns by prerequisite depth on an even grid; one curve style (a cubic per channel, tangents along the flow; straight through a layer's band); one label rule (name centered under the node, up to two lines, measured; state line under it); on the Map an edge leaves a node's top and arrives under its target's label block, so no edge runs through words; nodes 44 px (Map 42) on a lifted surface with the theme's shadow; the goal is the hero card with the bonsai, alone on the top layer of the Map and the right end of the Path, centered; the trunk centered under the tree; a chain alone in its track (pandas, git) lies flat as a branch; track names are not floated over the tree (the panel and the node's tooltip name the track).
- **Fit:** both trees open whole and centered (the open-on-NEXT branch is gone); the gaps stretch first and the tree scales only past their minimum. Path: 1.0 at 1280x800, 0.83 at 1024x700 (36 px nodes), 1.0 at 1728. Map (mock: 27 nodes, 7 layers after the flat rows; the critical chain setup > vars > lists > vec > dot > neuron > layers > fit crosses three tracks, so it can't get shorter without breaking rule 1): about 0.55 at 1280x800, 0.45 at 1024x700, 0.9 at 1728x1080. Seven rows of a node, a two-line label and an edge channel need ~800 px; the 1280 canvas is 482 px tall. Getting 36 px nodes on the whole Map at 1280 needs one of: labels beside nodes on the Map, a Map that grows right, or a smaller default Map (by track); that's a call for Michael.
- **Window:** the goal is one 36 px line and the dock 56 px, so the stage canvas is 1008x482 at 1280x800 (was 445) and 788x382 at 1024x700.
- **Shell:** `SkillsPage.tsx` renders `SkillsView`; the shell's page header gets `SkillsHeaderTools` (Path | Map | List and "Find a skill") through a one-line change in `Shell.tsx`. The Constellation is untouched (still used by the dashboard).
- **Actions:** Continue / Start → `library.start` through the dashboard store's `startSaved` (the saved lesson), else `learn {mode: "lesson"}`; Start project → `learn` with the brief; Make this my goal → `set_goal` when the engine lists it, kept in localStorage (`miyagi.skills.goal`) either way until the engine's goal agrees; unlock events play once per view and only on a view that shows their skill (`miyagi.skills.played`), so an event the Path can't show still plays on the Map; when every event has played somewhere they're acked (`skills.ack` when listed, local mark `miyagi.skills.acked`). View choice persists in `miyagi.skills.view`.
- **Stage:** `?scenario=skills&window=library&page=skills&size=1280x800&clean` (`&appearance=dark`); the goal picker: `?scenario=new-learner&...` (named to sort before `progress.json`, so it never answers `progress.get` in `full`). To replay the unlock: `localStorage.removeItem('miyagi.skills.acked'); localStorage.removeItem('miyagi.skills.played')`. Labels drop inline code marks (`groupby` shows as groupby).
- **Shots:** `agents/shots/skills-build-*.png` (800 px wide captures of the Browser pane: 1280 / 1024 / 1728 viewports scaled to fit).

## Core requests
- None needed. Stage note (dev/, integrator): app windows on the stage are capped at their `windowSize` (Library 1280x820), so the 1728 shots resized the window frame in the DOM; a `?window-size=fill` stage option would make that repeatable.

## Done when
- Path, Map and List render the mock learner in light and dark at 1024, 1280 and 1728 wide, in one centered column where the view is a list.
- One primary button on the page. Green appears only on mastered. No pastels except option buttons.
- The skill panel opens from any node. Esc closes it.
- The unlock plays once per event and respects reduced motion.
- typecheck passes, and the stage at `?scenario=skills` shows each view.

# v4 lane: skills (Adrian's skill tree round 3, flat Notion style)

Branch `michael/v4-skills` (from `origin/michael/app-ui-v4`). Stage port 5256.

## What is done
- `features/skills/flat/`: the round 3 page. `layout.ts` (pure: Path, Map, Tracks, Steps layouts; square-turn edges),
  `parts.tsx` (state mark, skill / fold / project / track cards, the stage), `views.tsx` (lede, tabs, Path with
  "Still to go" and "Keep fresh", Map with Tracks / Skills / Steps zoom, the peek), `copy.ts` (lines and the rules:
  mastered = passed on 2 days without help; reviews at 3, 7, 21 and 60 days), `layout.test.ts`.
- `SkillsView.tsx` uses the flat views; the header's right side is now the page's one primary (Continue <skill>).
  The old canvas (TreeCanvas, Dock, Panel, SkillNode, layout.ts) stays in the folder, unused by the page.
- `store.ts`: the Map zoom (`zoom`, `setZoom`).

## Stage
`http://localhost:5256/?scenario=skills&window=library&page=skills&size=1440x900&clean` (`&appearance=dark`). Map tab,
then Tracks / Skills / Steps. Click a card for the peek; Esc closes it.

## Shots
`agents/shots/v4-skills-r{1..4}-{ours,mock}-<view>-<theme>.png` (mock = Adrian's HTML mock at 1440x900),
`agents/shots/v4-skills-w{1024,1280,1728}-{path,map}.png`.

## Remaining differences vs the mock
- Title to lede spacing comes from the shell's PageHeader (shell lane).
- No "about N hours left, around <date>" in the lede and no Time per locked row: no per-skill minutes in the payload yet.
- No "The check it passed" in the peek, and Steps cards say "Step 1..n": no step titles or passed check per skill yet.
- The project card shows the bonsai, not the learner's artifact (the sin plot in the mock is sample art).
- No ↩ keycap on Continue (no Enter key in `bridge.platform.keys`).
- The mock learner's Map is deeper (Set up Python, git) so it scrolls a little at 900 tall.

## Core / contract requests
- Per skill: `estMinutes`, step titles (`steps: {title, passed}[]`), the passing check's label and date. Will wire to
  `contract: ui-v4` once it lands (`shared/contracts/UI-V4.md`).

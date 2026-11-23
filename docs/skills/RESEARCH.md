# miyagi skill tree: research and recommendation

Nov 22, 2026. Written for the Skills page redesign. Sources are linked inline. Where a source is a forum post, a fan wiki or a company's own claims, I say so.

**Short version.** Keep a real prerequisite graph underneath and show a path on top. A node is a skill ("Extrude"), not a lesson step. Use four states told apart by stroke and fill, not hue: locked, ready, practicing, mastered (green). Add one modifier, review due. Exactly one node is marked Next, and the page's single primary button points to it. Every branch ends in a capstone project. Mastery means you showed the skill on two separate days. Review comes from using the skill in later lessons, and a skill never loses its mastered state. New users pick a goal first. They don't start in front of 100 dashed circles.

---

## 1. What others do

### Edtech

**Duolingo, tree to path (2022)** ([blog](https://blog.duolingo.com/new-duolingo-home-screen-design), [NBC](https://www.nbcnews.com/tech/tech-news/duolingos-update-redesign-luis-von-ahn-interview-rcna44655), [backlash](https://piunikaweb.com/blog/duolingo-app-update-with-path-ui-faces-backlash-from-users), [streaks](https://blog.duolingo.com/how-duolingo-streak-builds-habit))
- The tree had skills with five crown levels, and you chose the next branch. The path is one line in which each circle is one level. Levels from different skills are mixed, practice and stories sit in the line, and units have plain names.
- Their reasons: learners were "not sure whether they're using Duolingo the correct or best way". Von Ahn named two goals, "decreasing confusion and increasing learning outcomes". Reviews that used to be optional are now spaced out along the path, so nobody goes back to "cracked" skills. They tested on new users first and got only "equivalent engagement". They published no data on learning gains.
- What was lost: choice (an easy lesson when tired, stories on demand), per-skill strength (crowns), and the course at a glance. There were petitions, and von Ahn refused to keep both versions.
- Streaks: 7-day-streak learners are 3.6x more likely to finish a course, but Duolingo admits a break "can... feel quite demotivating".

**Khan Academy** ([levels](https://support.khanacademy.org/hc/en-us/articles/5548760867853), [metric](https://blog.khanacademy.org/?p=13201), [streaks](https://blog.khanacademy.org/?p=17224), [map retired](https://support.khanacademy.org/hc/da/community/posts/360027982751/comments/360004311611))
- Each skill moves Attempted, then Familiar, Proficient and Mastered, worth 50, 80 and 100 points. Only a unit test or the course challenge can make a skill Mastered, and scoring under 70% drops it back to Familiar.
- Progress counts only Proficient and above, because "skills to proficient" correlates with MAP Growth test scores.
- The streak is weekly, and you keep it only by bringing a skill to proficient. Watching videos doesn't count.
- What failed: the zoomable Knowledge Map of all math was retired around 2020. Users still ask for it back.

**Math Academy** ([how it works](https://mathacademy.com/how-it-works), [FIRe](https://justinmath.com/individualized-spaced-repetition-in-hierarchical-knowledge-structures/))
- A graph of thousands of topics. A 30-45 minute diagnostic finds your "knowledge frontier", and you choose from a small set of unlocked tasks. Darker nodes mean more stable knowledge.
- Practicing an advanced topic counts as implicit review of the simpler topics inside it, and failures flow back up. Without this, students would face about 60 reviews a day.
- XP is roughly a minute of focused work. Weekly leagues can be turned off.

**ALEKS** ([arXiv](https://arxiv.org/pdf/1511.06757), [pie](https://www.mheducation.com/support/aleks-support-center/knowledge/what-is-the-aleks-pie.html)): "Ready to learn" is the outer fringe, the topics whose prerequisites are all known. ALEKS data puts success on those at about 93%. This is the formal case for showing the frontier rather than the whole map.

**Exercism** ([v3 rationale](https://github.com/exercism/v3/blob/master/docs/rationale-for-v3.md), [unlocking](https://exercism.org/docs/building/product/unlocking-exercises), [forum](https://forum.exercism.org/t/some-exercises-for-a-concept-remain-locked-after-the-learning-exercise-has-been-solved/1044))
- Concept exercises teach and practice exercises apply. Unlocks come from tags ("teaches X", "needs X"), and the UI says "Learn X to unlock Y".
- Learning Mode gates exercises and Practice Mode opens everything, so gating is optional.
- What failed: exercises that need several concepts stay locked, and users can't tell why.

**Brilliant** ([paths](https://brilliant.org/help/features/what-are-learning-paths)): a path is a recommended order, but topics don't have to be taken in order. Each concept ends with a skill check, and unit checks mix in earlier material.

**Codecademy** ([help](https://help.codecademy.com/hc/en-us/articles/360007997593-Difference-Between-Career-Paths-and-Skill-Paths), [comparison](https://scrimba.com/articles/scrimba-vs-codecademy-which-is-better-for-learning-to-code/)): skill paths are short and aimed at one outcome. Career paths are 50-100 hour foundations for a role, with portfolio projects. Progress is a completion percentage, not a skill measure.

**Boot.dev** ([May 2024 patch](https://boot.dev/blog/news/bootdev-beat-2024-05), [review](https://coddy.tech/blog/comparison/coddy-vs-boot-dev-casual-learning-vs-backend-mastery)): an RPG layer. Exercises earn XP toward levels, daily quests and bosses pay out chests, Seer Stones reveal a solution, and there are leaderboards. In 2024 random chests became the main reward. Some learners find it distracting. It suits a hype brand, not a calm one.

**DataCamp** ([XP](https://support.datacamp.com/hc/en-us/articles/34043400793495-Understanding-XP-and-Progress-on-DataCamp), [streaks](https://support.datacamp.com/hc/en-us/articles/360014799594-DataCamp-s-Daily-Streaks)): skill tracks cover one tool and career tracks cover a job. Repeating content earns no XP and hints cost XP. A streak day needs 250 XP.

**Sololearn / Mimo** ([Sololearn](https://medium.com/sololearn/ready-to-rise-up-our-leaderboard-get-rewarded-for-learning-8b23738e38d0), [Mimo path](https://mimo.org/blog/meet-your-new-learning-path), [Mimo listing](https://apps.apple.com/app/mimo-learn-coding/id1133960732)): Sololearn has six planet leagues. Mimo found that learners who learn a concept, practice it, move on and come back reach mastery, while those who finish whole sections in one go or skip practice struggle. Mimo then made challenges mandatory and moved to a guided path. Its hearts system is resented.

**roadmap.sh** ([repo](https://github.com/kamranahmedse/developer-roadmap), [profile](https://roadmap.sh/u/hugh)): huge community node charts with about 372k stars. You click a node for resources, and signed-in users mark topics as learning or done. A full-stack chart works as a reference poster, but it doesn't say what to do next.

**Trailhead / LinkedIn Learning** ([ranks](https://trailhead.salesforce.com/content/learn/modules/trailhead-road-to-ranger/learn-about-trailblazer-ranks), [superbadges](https://www.salesforceben.com/trailhead-superbadges-what-are-they-how-can-they-help/), [LinkedIn](https://www.linkedin.com/help/learning/answer/a1433885)): Trailhead superbadges are 8-14 hour applied challenges behind prerequisite modules, which makes them capstones. LinkedIn asks you to add the skills from a finished path to your profile, so the proof ends up somewhere public.

### Games

**Path of Exile** ([Mein-MMO](https://mein-mmo.de/en/scaring-new-players-to-death-former-blizzard-developer-explains-the-biggest-problem-of-path-of-exile-2,1216865), [forum](https://www.pathofexile.com/forum/view-thread/3596912)): a web of about 1,300 nodes. Experts love it and newcomers find it "daunting". Players ask for node hiding and highlighting, and most use outside build guides.

**FFX sphere grid** ([Kotaku](https://kotaku.com/final-fantasy-x-was-less-complex-than-it-seemed-5766535)): it looks like an 828-node web, but normal play is "extremely linear", with 50+ node stretches and no branch. Points arrive in small steps, so players don't notice how rarely they choose. A web on screen can hide a path underneath.

**Skyrim** ([UESP](https://en.uesp.net/wiki/Skyrim:Leveling)): skills are constellations, and they grow by real use. Hitting with a sword counts and swinging at the air doesn't, which is miyagi's own principle.

**Civilization** ([Game Developer](https://www.gamedeveloper.com/design/techs-of-civilization)): you get a new tech every few turns, and strong techs visible far ahead give you direction. What fails is the front-loaded complexity for new players.

**Hades** ([Tom's Guide](https://www.tomsguide.com/features/hades-exclusive-interview-supergiant), [mechanics](https://saschb2b.github.io/game-mechanics/games/hades/meta-progression), [Source Gaming](https://sourcegaming.info/2025/11/05/holism-why-hades-mattered/)): the Mirror is a short list of slots, each with two swappable options. Failed runs still pay out, so no attempt is wasted. It is close to maxed after about 100 runs, so it has no long tail.

**Factorio** ([FFF #376](https://factorio.com/blog/post/fff-376), [forum](https://forums.factorio.com/viewtopic.php?p=638694)): "trigger" techs complete when you do the thing, such as crafting steel. Players couldn't find which action triggers each one, so an unlock-by-doing node must say what to do.

**Diablo IV / Ori** ([PC Gamer](https://pcgamer.com/blizzard-overhauls-diablo-4-skill-system-to-enable-more-distinct-character-builds), [Ori](https://kb.speeddemosarchive.com/Ori/Skills_and_Abilities)): Diablo IV's simple tree was reworked to add real forks. Ori has three short optional branches. Small trees work, but they need some choice.

### Motivation research
- **Goal gradient.** People speed up near a reward, and a 12-stamp card with 2 stamps already filled beat a blank 10-stamp card ([Kivetz et al. 2006](https://business.columbia.edu/sites/default/files-efs/pubfiles/1200/goalgradient.pdf)).
- **Endowed progress.** 34% vs 19% completion with a head start, and the head start needs a reason ([Nunes & Drèze](https://knowledge.wharton.upenn.edu/?p=5630)).
- **Small area.** Early on, focusing on what's done motivates more. Near the end, focusing on what's left does ([Koo & Fishbach 2012](https://ideas.repec.org/a/oup/jconrs/doi10.1086-663827.html)).
- **Progress bars.** Slow early progress increases drop-off ([Villar et al. 2013](https://research.google/pubs/where-am-i-a-meta-analysis-of-experiments-on-the-effects-of-progress-indicators-for-web-surveys/)). "1 of 300" is slow early progress.
- **Streaks.** A broken streak lowers later engagement, less so when it can be repaired, so don't highlight breaks ([Silverman & Barasch 2023](https://www.colorado.edu/business/news/2023/04/20/research-streaks-marketing-tech-barasch)).
- **Mastery over completion.** Mastery-learning programs gain about 0.5 SD ([Kulik et al. 1990](https://www.academia.edu/81783373/Effectiveness_of_Mastery_Learning_Programs_A_Meta_Analysis); the figure comes from a summary).
- **Spacing and mixing.** The best review gap grows with how long you need to remember ([Cepeda 2006](https://pubmed.ncbi.nlm.nih.gov/16719566/)). Mixed practice beat blocked practice 72% to 38% ([Rohrer et al. 2014](https://link.springer.com/article/10.3758/s13423-014-0588-3)).
- **Visible goals.** Specific, hard goals beat vague ones ([Locke & Latham 2002](https://goal-lab.psych.umn.edu/orgpsych/2020/readings/5.%20Motivation/Locke%20&%20Latham%20(2002).pdf)).
- **Choice overload.** It grows with set complexity and unclear preferences ([Chernev et al. 2015](https://www.kellogg.northwestern.edu/faculty/research/detail/2015/when-product-assortment-leads-to-choice-overload-a-conceptual)), which describes a novice facing a big tree.
- **Rewards.** Expected rewards tied to completion undermine intrinsic motivation (d = -0.36, [Deci et al. 1999](https://pubmed.ncbi.nlm.nih.gov/10589297/)), and gamification's effects are small ([Sailer & Homner 2020](https://link.springer.com/article/10.1007/s10648-019-09498-w)). Feedback that says "you can do this now" beats loot.

---

## 2. Patterns and anti-patterns

**What works**
1. **A graph underneath, a path on top.** Duolingo, Math Academy, Brilliant and FFX all do this.
2. **One next step, a few alternatives.** That's the Math Academy menu and the ALEKS fringe: choice, but never blank-page choice.
3. **Mastery is spaced evidence, not completion** (Khan, Mimo).
4. **Using a skill reviews it** (FIRe, Skyrim, Factorio). This is miyagi's natural edge, since it already watches real use of the app.
5. **A visible goal at the end of each branch** (Trailhead, Civ, Codecademy projects).
6. **An honest head start.** Count what's done early and what's left late.
7. **Rhythm over streak:** weekly, repairable, never shaming.
8. **Gating as a default, not a wall** (Exercism Practice Mode).

**Anti-patterns**
- **Sprawl** (Path of Exile, roadmap.sh, Khan's old map). A novice can't value the nodes, every node competes for attention, the eye has no place to start, and progress looks tiny. Big maps suit experts who already know what they want.
- **Why Duolingo went linear.** Learners were confused, skipped optional reviews, and a fixed order let Duolingo build spacing and mixing in. Engagement held steady, and the cost was choice and overview. So make the path the default, and keep a map and a "test out" check.
- **States that look alike.** miyagi's current five hollow circles are an example.
- **Review debt piles** and **demotion.** Khan drops a mastered skill to Familiar, and Duolingo had cracked skills. Both feel like losing.
- **Hidden unlock rules** (Factorio, Exercism). **Hearts, leagues and loot.**
- **Reshuffling progress when content changes** (Duolingo, Mimo). Keep skill ids stable.

---

## 3. Recommendation for miyagi

### 3.1 What a node is
A node is a **skill** named in the app's own vocabulary: "Extrude", "Loop cut", "XLOOKUP", "Autograd", "Auto layout". It's built across lessons. A lesson teaches 1-3 skills and uses others. Steps carry skill tags, and every unassisted pass on a tagged step is evidence. A track has about 12-25 skills. Fewer feels thin, more becomes sprawl.

**Mastery rule:** unassisted passes in **2 sessions on different days**, ideally from two different lessons. This builds spacing into the definition of mastered.

### 3.2 Layout: Path by default, Map on demand
- **Path view (default):** only the subgraph leading to the learner's chosen **goal** (a capstone), usually 6-15 nodes. It's a layered DAG laid out left to right, with the capstone as the large node at the right end. Prerequisites converge into it, so it reads as a tree, not a row. The rest of the graph is hidden, and each node shows at most one faint "also unlocks" hint.
- **Map view (toggle):** every track, one region per app, with nodes shrunk to dots. Only capstones, the frontier and the hovered node get labels, and there's a search box. Clicking a capstone offers "Set as goal" as a secondary button.
- **Cross-track edges stay sparse and meaningful**, e.g. Python "Lists and loops" to PyTorch "Tensors", or Excel "Formulas" to Python "pandas". In Path view, a node from another track looks like any other node, with its app's name in small type.

### 3.3 Node states: four, plus one modifier
States are told apart by stroke and fill, so they work in grayscale, in dark mode and for color-blind users. Green appears only on mastered nodes.

| State | Means | Look |
|---|---|---|
| Locked | a required skill isn't mastered | 1px **dashed** outline, tertiary ink. Hover says "Needs Extrude, Inset" |
| Ready | requirements met, not started | 1.5px **solid** outline, primary ink |
| Practicing | some evidence, not yet mastered | solid outline plus an **inner ink arc** for the evidence (1 of 2 days) |
| Mastered | met the mastery rule | **solid green fill** with a check |
| *Review due* (modifier) | mastered, interval passed | **green ring** with a hollow center and a small "review" caption. Back to full fill after any passing use |

- **Next** is a focus marker, not a state, and it goes on exactly one node: a 2px ink ring offset by 3px, with the caption "Next".
- **Capstones** use a different shape (a larger rounded square) and follow the same state rules.
- No legend is needed. Focus or hover gives the state in words.

### 3.4 Capstones
- Each branch ends in a real project in the real app, checked by the engine: "Model a chair" (Blender), "Draw a floor plan" (AutoCAD), "Train an MNIST classifier" (PyTorch, reusing the neural-net demo), "Build a budget sheet" (Excel).
- A capstone is visible from day one, even while locked: the one locked thing you want. Its card shows the skills it needs as chips, and the count is the goal gradient ("3 of 5 skills ready").
- When finished, it shows a thumbnail of the learner's own file and goes into the portfolio.

### 3.5 Next step
- The page has **one primary button**, e.g. "Continue: Bevel basics", with the line "Teaches Bevel · unlocks Chair · 12 min" under it.
- The engine picks in this order:
  1. A lesson already in progress.
  2. A frontier lesson on the goal path that also uses a due skill, so review happens without a separate trip.
  3. The frontier lesson closest to the goal.
  4. A short review.
- Under the button, up to three "Also ready" text links keep some choice without a blank page.
- Ready nodes offer **"Know this already? Check it"**: a 2-3 step check in the app, like Khan's course challenge or Duolingo's jump test. Passing it marks the skill mastered.

### 3.6 The unlock moment (motion only)
It plays once per event: at the end of a lesson, or on the next visit to Skills if the learner hasn't seen it yet.
1. The node fills green from the center (about 280ms, ease-out), and the check draws in (160ms).
2. Edges to the nodes that depend on it draw along their length (about 360ms, 60ms apart).
3. Nodes whose last requirement this was close their dashes into a solid outline (about 240ms).
4. The Next ring glides to the new node, and the button text crossfades.
5. One line of copy appears, e.g. "Bevel is ready." Sound stays opt-in.

With reduced motion, each change is a 150ms crossfade. Later, the bonsai can grow from these events, with a leaf per skill and a branch per capstone. Leaves never fall.

### 3.7 Review and decay
- Intervals are 3, 7, 21 and 60 days, which the draft dashboard model already uses. Any unassisted pass on a tagged step, in any lesson, counts as a review. Credit also flows down weighted edges: passing a Bevel step refreshes "Select edges".
- **Never demote.** Mastered stays mastered, and freshness is a separate fact. A missed review resets the interval to 3 days.
- The page shows at most three due reviews, under "Keep fresh", and never a total. A review is a 2-3 step task on a starter file.

### 3.8 Empty state for a new user
- Don't draw a field of dashed nodes. Show one line, "What do you want to make first?", with 3-4 capstone **option buttons**, where pastels are allowed, based on the apps the learner has installed.
- Picking one sets the goal and draws its path. The first node is Ready and Next, and the primary button reads "Start: Blender basics · 8 min".
- Give an honest head start: lessons done before the tree existed count, and "Check it" lets people test out. No fake pre-stamps.
- The counter follows the small-area rule: "1 skill mastered" early on, "2 skills to Chair" once past halfway.

### 3.9 Features around the tree
1. **Skill chips on lesson cards** in the Library and on lesson start, e.g. "Teaches Extrude, Inset · unlocks Bevel".
2. **Lesson-end recap:** which skills moved, what's newly ready, and what's next. The unlock animation plays here first.
3. **Weekly recap** on Monday: skills mastered and kept fresh, plus minutes. It uses the existing weekly goal with pause and never mentions a broken streak.
4. **Portfolio:** finished capstones with a screenshot of the learner's own file, the date and the skills used, with share or export.
5. **Practice mode toggle** per track, to unlock everything for experienced users while still showing states honestly.

---

## 4. Data the engine needs to provide

Today's contract (`shared/contracts/events.ts`: `Progress.skills[] = {track, mastered, total, items[{label, state}]}`, with states `mastered | practicing | not_started`) can't draw a graph. A draft dashboard model in a worktree already reads `edges`, `cross`, `reps`, `masteredAt` and `review.dueAt`, and its `NodeState` already has the four states above (`.claude/worktrees/agent-a2bd5768445c910f1/app/src/renderer/src/features/dashboard/`). Everything below adds to what exists.

**Per skill**
- `id` (stable, never reused), `label` (1-3 words), `summary` (one line), `track`, `kind: skill | capstone`.
- `state: locked | ready | practicing | mastered`, computed by the engine.
- `evidence: {unassisted, assisted, sessions, days, need: {days: 2}}`, which drives the practicing arc.
- `masteredAt`, `lastPracticedAt`.
- `review: {dueAt, intervalDays, lastResult, lastAt} | null`.
- `lessons: [{lessonId, stepIds[], role: teaches | uses}]`.
- `testOut: {checkId, estMinutes} | null`, `estMinutesToMaster`.
- `layout: {layer, lane}` (optional hints that keep positions stable between visits).
- `replacedBy` (for curriculum changes).

**Per edge**
- `from`, `to`.
- `kind: requires | helps`. Only `requires` gates. `helps` is drawn as a faint line.
- `weight` (0-1): how much of `from` gets exercised when practicing `to`. This is the implicit review credit.
- `note`, e.g. "NumPy arrays become tensors". Whether an edge crosses tracks comes from its two skills.

**Per capstone** (a skill with `kind: capstone`, plus)
- `brief`, `requires[]`, `deliverable`, `checks[{id, title}]`.
- `starterFile`, `estMinutes`.
- `completedAt`, `artifact: {thumbnail, file}`.

**Per track**
- `id`, `app`, `title`, `order`, `installed`, `version`.
- `capstones[]`.
- `counts: {mastered, practicing, ready, locked, total}`.

**Per learner**
- `goal: capstoneId | null`, set by the user.
- `next: {kind: continue | lesson | review | capstone | test_out, lessonId, title, teaches[], unlocks[], refreshes[], estMinutes, reason}`.
- `alsoReady[]`: up to 3, in the same shape.
- `events[{id, at, skillId, from, to, lessonId}]` since `seenAt`, plus an acknowledge call, so each unlock animates once.
- `week: {mastered[], refreshed[], minutes, lessons, goal, paused}`.
- `portfolio[]`.

**Per lesson** (for Library cards): `teaches[]`, `uses[]`, `unlocks[]`, `estMinutes`.

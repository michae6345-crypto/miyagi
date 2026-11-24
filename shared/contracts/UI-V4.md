# ui-v4 contract: activity, bon, plans, skill tree, your data

Nov 24 2026. The data behind Adrian's v4 pages (`docs/ui-next` on `adrian/ui-next`), the skill tree round 3 and bon the buddy. The types live in `events.ts` (app) and `events.py` (engine). Both files are the same on `michael/app-ui-v4` and `integration/live`. Everything here is additive and optional. An app that ignores it keeps today's behaviour, and so does an engine that never sends it.

- **Gate.** The app sends a ui-v4 command only when `engine.hello.capabilities` lists its type, the same rule as every v2 command (`core/lesson.ts canSend`). The engine lists a command only once it answers it.
- **Mock.** `app/mock/scenarios/ui-v4.json` sends every event below with real catalog plans. Run it with `npm run mock -- ui-v4` or open the browser stage with that scenario. On connect it replays lesson 7 of Intro to Blender. `progress.get` answers the round 3 skill graph. The step's "Can I move on?" (`action check_step`) passes step 3, which grows bon to Budding and pushes `activity` and `plans`.
- **Times.** Times are ISO 8601 text with the learner's UTC offset (`"2026-11-22T16:12:00-08:00"`). Days are the learner's local date (`"2026-11-22"`).
- **Parity.** `python3 scripts/test_contract_parity.py` checks that the two files list the same events and commands, that the shared constants match, and that the mock validates.
- **Wire.** The app's `common/wire.ts` already lists the new events in `KNOWN` and the new commands in `V2_COMMANDS`. A lane only adds its `onMessage` handler and its `canSend` check.

## Who sends what

| Message | Direction | When |
|---|---|---|
| `activity.get` | app to engine | Home or Progress opens |
| `activity` | engine to app | The answer, then a push on each change (at most one every 10 s) to a connection that asked |
| `bon.get` | app to engine | Any window that draws bon, on start |
| `bon.import` | app to engine | Once per Mac: the count `growth.ts` kept in localStorage |
| `bon` | engine to app | The answer to both, then a push after every counted pass |
| `step.passed` (new fields) | engine to app | As today, now with `key`, `counted`, `assisted`, `skillIds` and `proofId` |
| `plans.list`, `plan.start`, `plan.remove` | app to engine | Library, Browse plans, a plan page, the two plan dialogs |
| `plans` | engine to app | The answer, then a push when a plan lesson starts or finishes |
| `learn` / `learn_url` / `library.start` with `plan` | app to engine | Starting a lesson of a plan |
| `playlist.get` | app to engine | "New plan from a playlist": a link is pasted |
| `playlist` | engine to app | Twice: the videos first, then the proposal |
| `plan.propose` | app to engine | "New plan from a goal": Enter |
| `plan.proposal` | engine to app | "Working" first, then the proposal |
| `link.get` | app to engine | A link is pasted in the ask field |
| `link.preview` | engine to app | A fast answer, then the full one |
| `progress` (new `graph` fields) | engine to app | As today (`progress.get`), now with tracks, steps, mastery and review rounds |
| `proof.get` | app to engine | The skill panel opens (r3 07) |
| `proof` | engine to app | The answer |
| `data.get`, `data.delete` | app to engine | Settings, Your data |
| `data` | engine to app | The answer to both |
| `review.start` | app to engine | "Keep fresh" or "Practice again" (already in the engine; new in the contract) |

## 1. Activity

`activity.get {}` is answered with `activity`. Home's week bars and numbers, Progress's 12 weeks, the totals line, and "Recently passed" all read from it.

```json
{"type": "activity", "payload": {
  "asOf": "2026-11-22T19:40:00-08:00", "tz": "America/Los_Angeles", "minutesTracked": true,
  "days": [{"date": "2026-08-31", "minutes": 0, "steps": 0}, "... 84 days, oldest first ...",
           {"date": "2026-11-21", "minutes": 12, "steps": 1}, {"date": "2026-11-22", "minutes": 15, "steps": 1}],
  "week": {"minutes": 108, "stepsPassed": 6, "skillsMastered": 2},
  "totals": {"lessonsFinished": 4, "stepsPassed": 58, "minutes": 959, "skillsMastered": 11},
  "recent": [{"key": "lesson-3f9a21c0:s4", "lessonId": "lesson-3f9a21c0", "lessonTitle": "The forward pass",
              "stepId": "s4", "stepTitle": "Add one row to every row", "at": "2026-11-22T16:12:00-08:00",
              "skillIds": ["nn.forward"], "skills": ["Forward pass"], "planId": "neural-networks"}],
  "milestones": [{"id": "m-first-lesson", "kind": "first_lesson", "title": "First lesson finished", "at": "2026-09-10T19:31:00-08:00"}]
}}
```

- `days` has exactly `ACTIVITY_DAYS` (84) days. Every day is present, the last one is today. The 12-week chart sums them Monday to Sunday. The week chart is the last 7.
- A practice minute is a minute in which a lesson is running and the learner does something: an edit, a save, a run, a check, or the lesson video playing. Idle minutes are not counted.
- `minutesTracked: false` means this engine does not record minutes yet. Every minute value is then 0 or null. The page shows steps and leaves out "0 min".
- `recent` holds at most `RECENT_PASSED_MAX` (20) passes, newest first. Each one is a counted pass (see bon). `skills` are the labels of `skillIds`, in the same order.
- `milestones` is optional. Adrian's Nov 24 trim took milestones off Progress, so an engine may send none.

## 2. bon

The engine owns bon's count. `bon.get {}` is answered with `bon`, which is then pushed after every counted pass.

```json
{"type": "bon", "payload": {"steps": 25, "level": 5, "name": "Budding", "fraction": 0.0,
  "next": {"level": 6, "name": "In bloom", "at": 40, "left": 15}, "grew": true, "lastKey": "lesson-5c7e2b90:s3"}}
```

```json
{"type": "bon.import", "payload": {"steps": 24, "seen": ["lesson-5c7e2b90:s1", "lesson-5c7e2b90:s2"]}}
```

- **Levels.** `BON_LEVELS` is the same table in both files, taken from `features/buddy/growth.ts`. The levels are Seed 0, Sprout 3, Shoot 8, Sapling 15, Budding 25, In bloom 40, Young tree 60 and Bonsai 90 passed steps. `events.py bon_state(steps)` builds the payload.
- **What counts.** A `step.passed` counts when it is not `skipped`, not `already` (pasted ahead, or Do it for me), and has a `key` that has never been counted. An `assisted` pass (after Show me's snippet or a level-3 hint) counts for bon but not toward mastery. The engine sets `counted: true` on that `step.passed`, then pushes `bon`. `grew: true` marks the pass that crossed into a new level: the level-up moment plays then.
- **The key.** `step.passed.key` is `"<lessonId>:<stepId>"`. Adrian asked whether `step.passed` can repeat under a different id. Within one lesson it cannot: step ids are `s1`, `s2` and so on, and they never change once sent. Across lessons it can.
  - The same video built in another folder or with another goal gets a new lesson id (`lesson-<hash of url, goal, folder>`), so its passes have new keys.
  - A progressive build numbers steps by position.
  - A review (`review.start`) replays a skill's steps under `review-<skill>-<lesson>`.
  - The engine therefore counts each key once, ever, and a replay of the same pass is never counted twice. A reconnect never re-sends `step.passed` today. If it ever does, the key makes that harmless.
- **Moving off localStorage.** The first time the engine lists `bon.import`, the app sends its localStorage count once. The engine keeps the larger count, adds `seen` (at most 400 keys) to the keys it has counted, and answers `bon`. From then on the app reads only `bon`, and every window agrees.

## 3. Plans

The catalog (`docs/ui-next/catalog/catalog.json`, `SCHEMA.md`) ships with the app and replaces `features/library/presets/packs.ts`. Its types are `Catalog`, `CatalogPlan`, `CatalogLesson`, `CatalogSkill`, `CatalogProject` and `CatalogPlaylist`. A catalog lesson has no id: a plan lesson is `{id: <plan id>, index: <0-based>}` (`PlanLessonRef`).

**Plans in progress.** `plans.list {}`, `plan.start {...}` and `plan.remove {id}` are all answered with `plans`.

```json
{"type": "plan.start", "payload": {"catalogId": "intro-python", "reqId": "r-plan-1"}}
```

```json
{"type": "plans", "payload": {"items": [{
  "id": "intro-blender", "title": "Intro to Blender", "source": "preset", "catalogId": "intro-blender", "track": "blender",
  "tool": {"id": "blender", "label": "Blender"},
  "lessons": [
    {"index": 5, "title": "Build the handle", "goal": "Teach ...", "minutes": 20, "stepCount": 6, "check": "scene",
     "passes": "The handle joins the mug and the mesh is one piece.", "skillIds": ["bl.extrude", "bl.loops"],
     "state": "done", "lessonId": "lesson-intr05aa", "doneAt": "2026-11-19T20:00:00-08:00"},
    {"index": 6, "title": "Subdivision and smooth shading", "skillIds": ["bl.modifiers"], "state": "in_progress",
     "lessonId": "lesson-5c7e2b90", "steps": {"done": 2, "total": 5}, "openedAt": "2026-11-22T19:31:00-08:00"},
    {"index": 7, "title": "Give it a material", "skillIds": ["bl.materials"], "state": "todo"}],
  "project": {"title": "A desk lamp, modeled and rendered", "brief": "...", "checks": ["...", "...", "..."], "state": "locked"},
  "done": 6, "total": 10, "nextIndex": 6, "minutesLeft": 105, "startedAt": "2026-10-30T18:00:00-08:00"}]}}
```

- **Ids.** `id` is the catalog id for a preset, `pl-<playlistId>` for a playlist and `goal-<8 hex>` for a goal.
- **Lesson states.** `state` is one of `done`, `in_progress`, `next`, `todo` or `skipped`. Exactly one lesson is `next` or `in_progress` until the plan is done; `nextIndex` points at it.
- **Starting a lesson.** The app sends `learn {query: lesson.goal, mode: "lesson", plan: {id, index}}`. A playlist plan uses `learn_url {url: "https://www.youtube.com/watch?v=<videoId>", plan}`. A lesson built before uses `library.start {id: libraryId, plan}`. The engine then marks the plan lesson `in_progress`, and `done` when its last step passes, and pushes `plans` each time.
- **Adding a plan.** `plan.start` with `catalogId` adds a preset. A playlist plan sends `playlistId`, `url` and the accepted `proposal`, with any skips. A goal plan sends `goal` and `proposal`. Adding the same `catalogId` again answers with the plan already there.

**From a playlist.** `playlist.get {url}` is answered twice. The first `playlist` comes fast: the videos, read from the playlist page with no model call, and `proposing: true`. The second carries `proposal` (the lessons and skills matched to the videos) and `proposing: false`.

```json
{"type": "playlist.get", "payload": {"url": "https://www.youtube.com/playlist?list=PLjEaoINr3zgGUwGwXlj9kBe7TrVWNjkyv", "reqId": "r-pl-1"}}
```

```json
{"type": "playlist", "payload": {"url": "https://www.youtube.com/playlist?list=PLjEaoINr3zgGUwGwXlj9kBe7TrVWNjkyv", "reqId": "r-pl-1",
  "playlistId": "PLjEaoINr3zgGUwGwXlj9kBe7TrVWNjkyv", "title": "Blender Donut Tutorial (2025)", "channel": "Blender Guru",
  "videoCount": 8, "totalSeconds": 15578, "videos": [{"id": "...", "title": "...", "seconds": 1290}], "proposing": false,
  "proposal": {"title": "Blender Donut Tutorial (2025)", "source": "playlist", "tool": {"id": "blender", "label": "Blender"},
    "lessons": [{"title": "...", "videoId": "...", "seconds": 1290, "minutes": 32, "grows": ["bl.navigate"], "skills": ["Viewport"]}],
    "skills": [{"id": "bl.navigate", "label": "Viewport", "needs": []}], "project": {"title": "A desk lamp, modeled and rendered", "brief": "...", "checks": ["..."]},
    "have": {"done": 2, "of": 6}, "minutes": 434, "note": "miyagi pauses each video until your scene passes the step."}}}
```

**From a goal.** `plan.propose {goal, tool?}` is answered with `plan.proposal`: first `proposing: true`, then the proposal. Catalog lessons are used first, and each one says where it came from.

```json
{"type": "plan.proposal", "payload": {"goal": "I want to 3D print a stand for my phone", "reqId": "r-goal-1", "proposing": false,
  "proposal": {"title": "3D print a phone stand", "source": "goal", "tool": {"id": "freecad", "label": "FreeCAD"},
    "tools": [{"id": "freecad", "label": "FreeCAD"}, {"id": "fusion", "label": "Fusion"}, {"id": "onshape", "label": "Onshape"}],
    "lessons": [{"title": "Your first sketch", "goal": "Teach ...", "minutes": 15, "grows": ["cad.sketch"], "skills": ["Sketching"],
                 "from": {"planId": "intro-cad", "index": 1}}],
    "fromPlans": ["intro-cad", "cad-3d-printing"], "minutes": 170, "note": "Built from two plans. Lessons you would not need are left out."}}}
```

- **Errors.** `error` is one of `not_found`, `private`, `unsupported`, `offline`, `too_long`, `busy` or `unknown` (`LookupError`).
- **`reqId`.** It is echoed back so a dialog can drop an answer meant for an earlier paste.

## 4. Skill tree

The tree still rides on `progress.graph` (`SkillGraphInfo`). Round 3 adds optional fields.

```json
{"id": "np.indexing", "label": "Indexing, slicing", "track": "numpy", "catalogId": "np.indexing", "state": "mastered",
 "evidence": {"done": 3, "total": 3}, "masteredAt": "2026-11-19T18:15:00-08:00",
 "mastery": {"need": 2, "days": ["2026-11-14", "2026-11-19"]},
 "schedule": {"dueAt": "2026-11-26T00:00:00-08:00", "round": 1, "interval": 7, "lastAt": "2026-11-19T18:15:00-08:00", "lastResult": "pass"},
 "steps": [{"key": "lesson-c41e9a02:s5", "lessonId": "lesson-c41e9a02", "lessonTitle": "Indexing and slicing", "stepId": "s5",
            "title": "Slice rows and columns", "passed": true, "at": "2026-11-19T18:15:00-08:00"}],
 "proofIds": ["pf-c41e9a02-s5"], "planIds": []}
```

- **Tracks, skills, steps.** `graph.tracks` (`SkillTrackInfo`: mastered of total, the next skill, last practiced) is the Tracks zoom and Progress's Tracks table. `skills` is the Skills zoom. `SkillInfo.steps` is the Steps zoom: every step behind a skill, passed or not.
- **Skill tags.** A step's skill tags are `StepSummary.skillIds` (already in `lesson.ready`) and `step.passed.skillIds`. Catalog lessons tag with catalog ids (`py.loops`). `SkillInfo.catalogId` ties a graph node to its catalog skill.
- **Mastery.** A skill is mastered when it has been passed unassisted on `MASTERY_DAYS` (2) different local days. `mastery.days` lists those days and `mastery.assisted` counts the passes that did not count. `graph.masteryDays` says which rule the engine uses.
- **Review.** `REVIEW_DAYS` holds Adrian's 3, 7, 21 and 60 days. `graph.reviewDays` says what the engine really uses; `sessions/review.py` uses 1, 3, 7, 14 and 30 today. `schedule.round` indexes into it, and a miss starts over at round 0. `review.dueAt` stays as it was.

**Proof.** `proof.get {id}` returns one pass, and `proof.get {skillId}` returns a skill's newest five. Both are answered with `proof`.

```json
{"type": "proof", "payload": {"skillId": "np.indexing", "reqId": "r-proof-1", "items": [{
  "id": "pf-c41e9a02-s5", "kind": "cell", "key": "lesson-c41e9a02:s5", "skillIds": ["np.indexing"],
  "lessonId": "lesson-c41e9a02", "lessonTitle": "Indexing and slicing", "stepId": "s5", "stepTitle": "Slice rows and columns",
  "at": "2026-11-19T18:15:00-08:00", "check": {"label": "corner equals [[1 2] [5 6]]"},
  "text": "img = np.arange(12).reshape(3, 4)\ncorner = img[:2, 1:3]\ncorner", "output": "array([[1, 2],\n       [5, 6]])",
  "lang": "python", "file": "indexing.ipynb"}]}}
```

A Blender pass carries `"kind": "scene"`, with `text` set to the scene facts the check read and `file` set to `mug.blend`.

- **Size.** `text` is at most `PROOF_TEXT_MAX` (2000) characters and `output` at most `PROOF_OUTPUT_MAX` (1000). Longer work is cut and `truncated` is set.
- **Where it lives.** Proofs are stored on this Mac only and never sent anywhere. `file` is relative to the lesson folder. No screenshot is ever kept: a `screen` proof is the check's words only.

**Link preview.** `link.get {url}` is answered with `link.preview`. The first answer comes fast (`pending: true`: title, channel and length from the page or oEmbed). The full answer adds `grows`, `have` and `catalogId`.

```json
{"type": "link.preview", "payload": {"url": "https://www.youtube.com/playlist?list=PLZHQObOWTQDNU6R1_67000Dx_ZCJB-3pi", "reqId": "r-link-1",
  "kind": "playlist", "pending": false, "title": "Neural networks", "channel": "3Blue1Brown", "playlistId": "PLZHQObOWTQDNU6R1_67000Dx_ZCJB-3pi",
  "videoCount": 10, "totalSeconds": 13054, "thumbnail": "https://i.ytimg.com/vi/aircAruvnKk/hqdefault.jpg",
  "grows": [{"id": "nn.forward", "label": "Forward pass"}, {"id": "nn.backprop", "label": "Backpropagation"}],
  "have": {"done": 8, "of": 13}, "finishesGoal": true, "catalogId": "neural-networks"}}
```

`thumbnail` is only ever an `https://i.ytimg.com/` URL; `events.py` rejects anything else.

## 5. Your data

`data.get {}` and `data.delete {what?}` are both answered with `data`.

```json
{"type": "data", "payload": {"canDelete": ["notes"], "totalBytes": 265895936, "items": [
  {"id": "lesson_folder", "label": "Lesson folder", "where": "this_mac", "path": "~/miyagi/lessons", "bytes": 48211968, "count": 14, "delete": null},
  {"id": "lesson_cache", "label": "Lesson cache", "where": "this_mac", "path": "~/miyagi/cache/lessons", "bytes": 212336640, "count": 31, "delete": "lesson_cache"},
  {"id": "progress", "label": "Lesson history and skills", "where": "this_mac", "path": "~/miyagi/state", "bytes": 1843200, "count": 58, "delete": "progress"},
  {"id": "notes", "label": "Lesson notes", "where": "this_mac", "path": "~/miyagi/state/context", "bytes": 3407872, "count": 14, "delete": "notes"},
  {"id": "screenshots", "label": "Screenshots", "where": "not_kept", "detail": "Used to check a step, then dropped.", "delete": null}]}}
```

```json
{"type": "data.delete", "payload": {"what": ["notes"]}}
```

What the engine can do today, so the page never promises more:

| Kind | What it removes | Today |
|---|---|---|
| `notes` | Lesson notes and file-scan cache (`server/context`, `~/miyagi/state/context`) | Yes. `data.delete` already does this, whatever `what` says |
| `lesson_cache` | Built lessons (`MIYAGI_LIBRARY_DIR`, else the builder's cache folder) | Not yet |
| `progress` | `history.json`, `mastery.json`, `review.json`, `skills.json`, `recent.json`, and activity, bon and plans once they exist | Not yet |
| `proofs` | Stored proofs | Not yet: proofs are not stored yet |
| `all` | Every kind above | Not yet |

- **What the app may offer.** `canDelete` lists only the kinds this engine really deletes, so the app shows a Clear button only for those. `deleted` on the answer lists what was really removed.
- **Older engines.** `data.delete` gets no reply from an older engine, so the app keeps its own "erased" sheet as it does today.
- **Never deleted.** The lesson folder (`~/miyagi/lessons`) is the learner's own work. It has no delete kind, and the page offers Open only.
- **Your account.** Rows marked "Kept in your account" in the mock are not engine data. Today the engine keeps history and skills on this Mac only, and the account, and deleting it, belong to miyagi-cloud.

## The Nov 24 contract sync

`michael/app-ui-v4` and `integration/live` had drifted (Linear MIC-9). Both now carry the union:

- **From the app branch.** The v2 build checklist fields on `lesson.building`, `step.started.where` and `then`, `step.passed.summary`, the v2 card fields (`hintStep`, `missingLines`, `fixCaption`, `waiting`, `result`, card kind `complete` in `events.py`), `status` `busy` with `retryInS`, and the v2 events registered in `ENGINE_EVENTS`.
- **From the engine branch.** `epoch` and `gen` on cards, statuses, errors, off-tracks and check updates; `lesson.ready.buildS`; `answer.done`; `ask.warm.source`; and the circle-ask timing note.
- **`answer.delta`.** It has both readings: the app's `done` and the engine's `seq`. `text` defaults to "". The TypeScript side keeps `askId` required (the app keys on it), and `events.py` lets it be absent.
- **Newly in the contract.** `review.start` and `data.delete`, which the engine already answered.

## Not built yet (engine)

Every ui-v4 command above. The engine lists each one in `engine.hello` once it answers it:

- **Minutes.** Practice minutes need a recorder. Until there is one, send `minutesTracked: false`.
- **Counter and proofs.** The bon counter and the proof store go in `~/miyagi/state`.
- **Mastery and review.** The two-day mastery rule and the review rounds belong in `sessions/skills_graph.py` and `sessions/review.py`.
- **Plans.** The plans store, and `playlist.get` / `link.get`, which can read the playlist page and oEmbed with no model call.
- **Proposals.** `plan.propose` and the playlist proposal, catalog first.
- **Your data.** The `data` inventory and the delete kinds beyond `notes`.

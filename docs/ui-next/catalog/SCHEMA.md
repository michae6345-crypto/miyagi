# miyagi lesson plans: the file format

One JSON file per plan in `plans/<id>.json`. `node build.mjs` checks every file and writes `catalog.json`, `catalog.js` (for the mock) and `CATALOG.md`.

A plan is a set of lessons in order that ends in a project the learner makes alone.

## Fields

| Field | Type | Rule |
|---|---|---|
| `id` | string | kebab-case, same as the file name |
| `title` | string | "Intro to X" for a first plan. At most 34 characters |
| `group` | `language` \| `environment` \| `topic` | language = a coding language. environment = an app or tool you work in. topic = a library or subject on top of one |
| `topic` | `code` \| `data` \| `ai` \| `3d` \| `cad` \| `design` \| `tools` | the filter tab it shows under |
| `track` | string | the skill-tree track name, lowercase ("python", "blender") |
| `tool` | `{id, label}` | where the learner works. ids: vscode, jupyter, terminal, browser, blender, freecad, fusion, onshape, figma, excel, sheets, unity, godot, xcode, arduino, docker, rstudio |
| `also` | string[] | other things that must be installed ("Python 3", "Node.js"). May be empty |
| `level` | `start` \| `next` | start = no experience needed. next = builds on another plan |
| `needs` | string[] | plan ids to finish first. Empty when level is start |
| `line` | string | one or two short sentences, at most 70 characters, no colon |
| `project` | `{title, brief, checks[3]}` | what the learner makes alone at the end. Not something a lesson already built. brief at most 190 characters. Exactly 3 checks a machine could verify |
| `skills` | `{id, label, needs[]}[]` | 6 to 10. id is `<prefix>.<name>`. label at most 18 characters, so a skill card never cuts its name. needs = skill ids in this plan, or in a plan listed in `needs`. No cycles. At least one skill has no needs inside the plan |
| `lessons` | see below | 6 to 12, in the order a learner does them |

### A lesson

| Field | Type | Rule |
|---|---|---|
| `title` | string | at most 40 characters |
| `goal` | string | the text the engine builds the lesson from (`learn {query: goal, mode: "lesson"}`). Starts with "Teach". Names the tool, the concept and the small thing the learner makes. At most 200 characters |
| `grows` | string[] | 1 or 2 skill ids from this plan |
| `minutes` | number | 10, 15, 20, 25 or 30 |
| `steps` | number | 4 to 7 |
| `check` | `run` \| `code` \| `scene` \| `file` \| `screen` | run = reads what the program prints. code = reads the file the learner typed. scene = reads the model through the app (Blender, CAD). file = a saved file exists and is right. screen = looks at the app window |
| `passes` | string | one plain sentence a machine could verify. At most 90 characters |

Every skill is grown by at least one lesson. A lesson never grows a skill before a lesson that grows what that skill needs.

## Writing rules

- Plain words. No hype, no exclamation marks, no "master", "unlock", "journey", "dive".
- No colons in `line`. Sentence case everywhere.
- Each lesson makes one small concrete thing (a tip calculator, a mug, a bracket). Say what it is in the goal.
- `passes` states a fact about the learner's work, not an activity ("The plate is 5 mm thick", not "Learner pads the sketch").
- Mac first. Only tools that run on a Mac.

# evals/replay: scripted learners on cached lessons

Roadmap 4.1. `evals/lesson` grades how lessons are BUILT (5 tutorials, live builds). This folder grades how a built
lesson BEHAVES with a learner: 15 more cases across 14 topics, each with an expected step outline, expected checks and
a learner script (edits, commands, mistakes). Together they make the 20-tutorial eval set.

Offline and free: nothing builds a lesson, calls a model, opens a window or touches the network.

```sh
python -m evals.replay.harness                 # replay the cached cases, dry-run the rest, print findings
python -m evals.replay.harness --only git-basics -v
python -m evals.replay.harness --dry           # grade every script on its own expected checks only
python -m evals.replay.harness --needs-build   # cases whose lesson is not cached yet
python -m pytest evals/replay -q -p no:cacheprovider
```

## How a replay works

`harness.py` makes a fresh temp lesson folder and plays the case's actions into it. Files are real files on disk.
The stub modules are:
- **Terminal**: prompt rows plus output, last 30 rows visible.
- **VS Code**: the open file, with a 60-line viewport around the last edit. A notebook shows its cells and outputs.
- **Browser**: a window with the lines the page shows.
- **Runs**: each run sets the command, exit code, output tail and `::metric::` points, as `tut run` / VS Code's
  `command_end` do.

After every action it asks the real `server.checks.evaluate_gate` whether the step passes, the way `LessonSession`
does:
- precision mode is on;
- a failing `screen_absent` row vetoes the files-only route;
- a `screen_contains` pass latches for the step.

The session's other gates (code_gate, run evidence, the judge) are not replayed. The replay grades the lesson's checks.

The session moves on at the first passing gate, so each step reports its status at that gate (`first_status`):
- `pass`: screen checks opened it.
- `pass-precision`: only the files-only route opened it.
- `fail` or `pending`: it never opened (the last status is reported).

The harness still plays the rest of the step, because the expected checks and the mistakes need it. The best status
reached is `best_status`, which the session never sees. A step that goes green via precision before its last correct
action is `early_precision`: the learner is moved on before the step's work is done. A `pass-precision` step with no
`finding` in its case is a problem, so every one is written down.

Each mistake reports whether it was **caught**, meaning the step was not passing right after it. A mistake can also
name the rows that should catch it: `caught_by` (the lesson's check ids, replay) and `caught_by_spec_rows` (the
expected checks, `x0`, `x1`, ..., dry run). Each named row must fail right after the mistake. Without them, a mistake
can count as caught only because the step is unfinished. git s1's `user.nmae` in the dry run is one: its rows wait
for `git config --list`. Mistakes like that carry no row names.

Command output comes from one of three sources, and every run says which:
- `real`: the learner's stdlib-only Python script, really run (calculator, SQLite). The script path must be relative
  and inside the lesson folder, and the run gets only PATH, HOME, LANG, LC_* and TMPDIR from the environment.
- `recorded`: real output from `demo/cache/stage/nn-runs.json`.
- `format`: the tool's verbatim output format, written by hand. Values are plausible, not measured.

## Case format (`cases/<id>.json`)

```jsonc
{
  "id": "git-basics", "topic": "git", "stack": "...",
  "tutorial": {"kind": "video" | "text", "goal": "...", "video_id": "...", "url": "...", "video_query": "..."},
  // a video tutorial needs video_id or video_query (the search to pick one before its build)
  "lesson": "demo/cache/lessons/<key>.json" | null,   // null: needs one paid build
  "learner": {"folder": "git-lab", "seed": "demo/nn-lab", "files": {"path": "text"}},
  "outline": [{
    "step": "s1",                 // the cached lesson's step id (omit when not cached)
    "about": "...", "match": "regex the lesson step's title + instructions should match",
    "expect_checks": [ /* checks in the lesson format; every one must pass for a correct learner */ ],
    "expect": "pass" | "pass-precision" | "fail" | ["fail", "pass-precision"],
    "finding": "why a correct learner does not get pass (a lesson bug)",
    "actions": [
      {"do": "write|edit|insert|append|open|scroll|mkdir", "file": "...", ...},
      {"do": "run", "cmd": "...", "output": [...] | "output_ref": "file#key.path" | "real": true, "stdin": "...",
       "exit": 0, "running": false, "creates": {"path": "text", "dir/": ""}, "deletes": [...]},
      {"do": "cell", "file": "x.ipynb", "source": "...", "outputs": [...], "error": {...}, "index": 0},
      {"do": "browser", "lines": [...]}, {"do": "clear"},
      {"do": "mistake", "note": "...", "caught": true, "caught_by_spec": true, "finding": "...",
       "caught_by": ["s4c2"], "caught_by_spec_rows": ["x1"], "actions": [...]}
    ]
  }]
}
```

`caught: false` with a `finding` records a mistake the lesson's checks miss. The test suite keeps it as expected, so
a fix shows up as a change, never as noise.

## Cases

| case | topic | lesson | steps | source of outputs |
|---|---|---|---|---|
| `git-basics` | git | cached (rE2zRhZdjFU) | 10 | format |
| `react-components` | react | cached (hn80mWvP-9g) | 8 | format |
| `python-calculator` | python-basics | cached (text) | 8 | real |
| `nn-from-scratch` | neural-nets | cached (text) | 6 | recorded |
| `tf-mnist-notebook` | deep-learning | cached (VPlFpvLOgtQ) | 7 | format (notebook) |
| `pinn-diffusion` | physics-ml | cached (AXXnSzmpyoI) | 9 | format |
| `pinn-convection` | physics-ml | cached (unBU1PwCnvQ) | 7 | format |
| `sql-sqlite-joins` | sql | needs build | 4 | real |
| `flask-todo-api` | web-backend | needs build | 4 | format |
| `docker-compose-basics` | docker | needs build | 4 | format |
| `typescript-basics` | typescript | needs build | 4 | format |
| `css-flexbox-grid` | css | needs build | 5 | browser + files |
| `go-http-server` | go | needs build | 4 | format |
| `bash-scripting` | shell | needs build | 4 | format |
| `pytest-unit-tests` | testing | needs build | 4 | format |

`gen/pinn_diffusion.py` and `gen/pinn_convection.py` write the two PINN cases. Their run output is generated.

## Needs one paid build

These cases have no cached lesson. Each one needs one text-lesson build (`build_text_lesson` from the goal). A video
build also works after picking a video for the case's `video_query`. Set the case's `lesson` to the cached file, then
map each outline item to its step id. No case was built here.

| case | goal |
|---|---|
| `sql-sqlite-joins` | learn SQL joins with SQLite: create tables, insert rows, INNER JOIN and LEFT JOIN with GROUP BY |
| `flask-todo-api` | build a small todo REST API with Flask: GET a list, POST JSON, 404 for a missing id |
| `docker-compose-basics` | containerize a tiny web app with a Dockerfile, run it on a port, then add Redis with docker compose |
| `typescript-basics` | learn TypeScript basics: tsc setup, interfaces, type errors, generics, an npm build script |
| `css-flexbox-grid` | lay out a web page with CSS flexbox and grid, then make it responsive with a media query |
| `go-http-server` | write a Go HTTP server with net/http: a hello handler, a JSON endpoint and a test with httptest |
| `bash-scripting` | write a bash backup script: shebang and chmod, arguments with defaults, a loop over files, strict mode |
| `pytest-unit-tests` | unit test a small Python module with pytest: asserts, pytest.raises, parametrize and the tmp_path fixture |

## Findings on the cached lessons (replay of 2026-11-21)

Counted by the route of each step's first passing gate, 47 of 55 steps go green on screen checks. 7 go green via
precision, all of them before the step's actions are done, and 1 never passes.

- **pinn-convection s7 can never pass.** Its `metric_trend` rows have `window: 5` (training steps). A trend needs at
  least 8 points in the window, so even a metric logged every step gives 6 at most.
- **git-basics s6 fails its screen check for a correct learner.** The clone makes `GitGoing/`, and tab completion types
  `cd GitGoing`, but the check's pattern `cd\s+.*gitgoing` is case-sensitive. The step passes only through precision's
  `gitgoing/index.html`, and only on a case-insensitive disk. That route opens right after the clone, before the `cd`.

Six more steps would go green on screen checks later, but precision moves a correct learner on first:
- **git-basics s5**, after action 2 of 4: its one precision row is `def my_function`, so writing the function passes
  the step before `git add .` and the second commit.
- **git-basics s8**, after action 1 of 4: its one precision row is the edited heading, so the edit passes it before the
  add, the commit and the push.
- **git-basics s9**, after action 1 of 3: its one precision row is `command_exit_ok` for `git ... show`, and
  `_script_tokens` keeps only `git`, so `git checkout main` passes it before the pull or `git show`.
- **git-basics s10**, after action 1 of 3: the same, for `git ... branch`. `git checkout main` passes it before
  either branch is deleted.
- **react-components s1**, after action 1 of 3: its one precision row is `my-react-app/package.json`, so
  `npm create vite@latest` passes it before the dev server runs.
- **tf-mnist-notebook s1**, after action 1 of 4: its one precision row is `venv/bin/activate`, so
  `python3 -m venv venv` passes it before activate, pip install or Jupyter.

Precision checks are much weaker than screen checks. In precision mode, these mistakes still pass the step:
- `return a - b` (calculator s1);
- `git config user.nmae` (git s1): `command_exit_ok` keeps only `git config`;
- pushing `main` (git s8);
- no `export default Footer` (react s5);
- no JSX fragment (react s6): Vite shows a compile error;
- venv made but nothing installed (mnist s1);
- no softmax (mnist s4);
- no `create_graph=True` (pinn-diffusion s6);
- rerunning beta 1.0 for the beta -1 step (pinn-convection s5): flags are dropped.

The terminal scrollback causes two problems:
- An old `git add learning.py` passes git s4 after a failed `git add learnig.py`.
- Stale `npm ERR!` lines fail react s1's `screen_absent` row after the fix. That fail also vetoes the precision route,
  so the step stays stuck until the learner clears the terminal. Today precision opens s1 before this can happen;
  it shows up once s1's precision row is tightened.

Two pinn-convection step titles don't match their instructions:
- s6 "sharper Gaussian IC" only runs `--beta 2.0`.
- s7 "non-dimensionalized PINN" only runs 4000 epochs.

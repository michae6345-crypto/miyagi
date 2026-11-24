# server/evals/checks: offline eval set for step checks

How good is the engine at deciding a learner's step is done? Each case in `cases/` is one moment of a real lesson
in the repo: a step, the learner's workspace at that moment, and the verdict a careful tutor would give
(`pass` or `not_yet`). The runner calls `server.checks.evaluate_gate` the way the orchestrator does and scores it.
No model call, no network, no screen capture: files go into a temp lesson folder, and the screen is a fixed
OCR reading.

```
python -m server.evals.checks            # scores + wrong verdicts, worst first
python -m server.evals.checks -v         # plus every case
python -m server.evals.checks -k jupyter # only ids containing "jupyter"
python -m server.evals.checks --json
python -m server.evals.checks --held-out # also the held-out wrong verdicts' rows (reviewing the set, not fixing)
python -m server.evals.checks --write-baseline   # after the checks improve or cases are added
python -m pytest server/evals/checks -q  # fails below baseline.json or on a new wrong verdict (training cases)
```

**Held-out cases** (`"heldOut": true`, about a third of each new batch) are scored and reported on their own and are
**never used to tune a fix**. The train set (every other case) is what the scores, `failures`, `known_wrong` and the
per-case pytest guard work on. The held-out set gets its own score line and the ids of its wrong verdicts only (no
rows, no `why`, unless `--held-out`), its own block in `baseline.json` (`held_out`), and one aggregate pytest guard
(accuracy / precision / recall must not drop) that names no case. A fix loop reads the train report; the held-out
score says whether the fix generalises. A case never moves between the two sets.

`pass` is the positive class. **Precision** = of the steps the checks passed, the share that were really done
(a miss here is a *false pass*: the learner moves on with broken work, the worse error). **Recall** = of the steps
that were done, the share the checks passed (a miss is a *false not-yet*: the learner gets stuck on finished work).
`fpr` = false passes / steps not done.

## Case format

```jsonc
{
  "id": "jupyter-mnist-s2-typed-not-run",   // = file name
  "kind": "jupyter",                        // jupyter | vscode | terminal | metric | blender | cad
  "trap": "false_pass",                     // none | false_pass (a near miss that looks done) | false_fail (done, but looks odd)
  "heldOut": true,                          // optional: a held-out case (see below); default false = train
  "expected": "not_yet",                    // pass | not_yet
  "why": "T10-CP7: the cell is typed but never run ...",
  "precision_mode": false,                  // optional: evaluate_gate(precision_mode=...)
  "step": {"lesson": "demo/cache/lessons/5c0ea8a49f419487.json", "id": "s2"},  // or an inline step with "checks"
                                            // optional "patch": {...}, "drop_checks": [ids], "adapt": true
                                            // (adapt: run the lesson through app_lesson.adapt, as the engine
                                            // runs an app lesson: file/command checks dropped, app pinned)
  "workspace": {
    "files": {
      "calculator.py": "def add(a, b): ...",          // a text file
      "project1/.git": {"dir": true},                 // a folder
      "mug.scene.json": {"json": {"objects": [...]}},  // a JSON document (indent 1): a headless dump, see below
      "mnist.ipynb": {"notebook": {"from": "server/tests/fixtures/t10_mnist.ipynb", "keep_cells": 1,
                                   "unrun": [0], "replace": [[0, "old", "new"]], "append": [cell],
                                   "counts": [16, 17, null]}},   // execution counts in cell order (run order)
      "Untitled.ipynb": {"notebook": {"cells": [{"source": "...", "stdout": "...", "error": "NameError: ...",
                                                 "image": true, "run": false, "count": 4}],
                                      "kernel": ".venv (3.12.16)", "kernel_version": "3.12.16"}}
    },
    "screen": {"Code": ["line", ...], "Terminal": [...]},   // or a ScreenObservation {windows, blocks}; null = no frame
    "run": {"command": "python3 calculator.py", "exit_code": 0, "output_tail": ["5"], "running": false},
    "metrics": {"loss": [[0, 1.2], [100, 1.08]]},          // "nan" / "inf" for NaN / inf
    "segment_done": true, "editor": "Code"
  }
}
```

Lessons used: the MNIST Jupyter video lesson (`5c0ea8a49f419487`, with the learner's real notebook from desktop
test 10), the calculator and NN-from-scratch text lessons, the Git, React/Vite and convection-PINN video lessons,
and two fixture lessons in `lessons/` written in the same step shape for multi-file projects: `py-modules.json` (the
calculator split into operations.py / main.py / test_operations.py: an import, an F2 rename, pytest) and
`ts-shop.json` (a React + TypeScript Vite app with a shared src/utils.ts: a named import, `npm run build`, Jest),
and the coach eval's git interactive-rebase lesson (`evals/coach/lessons/git-interactive-rebase.json`).
Inline steps follow lessons in Adrian's catalog plans (`docs/ui-next/catalog/plans`, commit 213c9238): Intro to
Jupyter ("Run order and what the kernel keeps", "Install a package and draw a chart", "Restart and run all") and
PyTorch ("Write the training loop"), written in the shape the lesson builder gives the MNIST lesson.

## Round 2: Jupyter notebooks and ML training runs (Nov 24 2026, `claude/eng-evals-r2-0`)

19 new cases (12 train, 7 held out), no engine change. Steps from the MNIST video lesson (`5c0ea8a49f419487`: s5
fit, s6 predict) and, inline, from Adrian's catalog plans (`origin/adrian/ui-next`,
`docs/ui-next/catalog/plans/`): Intro to Jupyter ("Write notes in Markdown cells", "Help, tab completion and
magics", "Install a package and draw a chart", "Restart and run all", "Export and share the notebook"), PyTorch
("Write the training loop", "Hold out data and measure accuracy", "Save and load a model", the sine-wave project's
validation loss) and scikit-learn ("Score a classifier", "Cross-validation"), plus a "plot the training loss" step
in the MNIST lesson's shape. Cell sources in the Markdown cases are saved as VS Code saves them (a list of lines).

The traps: a fit the kernel crashed in (epoch 3's 0.9771 on screen, the model gone), a fit interrupted in epoch 2,
accuracy that peaks above the bar then collapses (no NaN), a kernel restart that skipped the training cell before
predict (its stale `[19]` beside `[1]`-`[4]`), headings typed as `#` comments in a code cell, a second `%timeit`
cell never run, an HTML export with no outputs whose chart title is only in the code, validation loss that falls
then climbs (overfitting). Done-but-odd: Run All with an empty trailing cell, `###` headings and `*` bullets, a loss
printed with `print(epoch, loss.item())`, a confusion matrix drawn with `ConfusionMatrixDisplay`.

| before any fix | acc | prec | rec | FP | FN |
|---|---|---|---|---|---|
| train (120: 108 earlier + 12 new) | 0.925 | 0.895 | 0.944 | 6 | 3 |
| train, the 12 new | 0.250 | | | 6 | 3 |
| held-out (34: 27 earlier + 7 new) | 0.382 | 0.318 | 0.538 | 15 | 6 |
| held-out, the 7 new | 0.143 | | | 3 | 3 |

Train wrong verdicts (all new; the 108 earlier train cases still score right):

- **FP `jupyter-mnist-s5-kernel-crashed-epoch3`**: the metric is read from the notebook's last saved epoch line;
  "The Kernel crashed while executing code" on screen and a fit that stops at `Epoch 4/5` are never weighed.
- **FP `jupyter-mnist-s5-keyboard-interrupt-epoch2`**: the running accuracy of a half-done epoch passes; the cell's
  `KeyboardInterrupt` error output is not read (s5 has no error check of its own).
- **FP `jupyter-mnist-s6-restart-skipped-fit`**: nothing compares run counts across the cells the step depends on:
  the predict cell's `[4]` after a training cell still at `[19]` means the model that predicted was never trained.
- **FP `jupyter-markdown-headings-in-code-cell`**: `file_contains` over the raw .ipynb finds `"# ...` / `"## ...` in a
  code cell's source; nothing ties a Markdown pattern to a Markdown cell.
- **FP `jupyter-timeit-second-cell-not-run`**: the step's cells are found by its target (the first `%timeit` cell);
  the second cell of the step's own code, typed but never run, is not one of them.
- **FP `jupyter-export-html-chart-not-run`**: "Chart in the export" matches the chart's title in the exported code;
  an export whose cells have no outputs (`jp-mod-noOutputs`, no `<img`) passes.
- **FN `jupyter-markdown-level3-headings`**: `##\s` refuses `### The data`; heading level is not what the step asks.
- **FN `jupyter-pytorch-xor-loss-printed-bare`**: the loss rows `0 0.2614...` don't fit `epoch N loss V`, so the
  trend waits forever on a finished run.
- **FN `jupyter-sklearn-confusion-matrix-plotted`**: an output check for numpy's `[[..]]` text can't see the same
  3 by 3 counts drawn by `ConfusionMatrixDisplay` (an image output, OCR'd as rows of numbers).

Seen right (train): the collapse to 0.1062 fails on the last epoch; the overfit sine run fails its trend (0.1585 ->
0.1675); the empty trailing cell doesn't break "Restart and run all".

Held-out wrong verdicts (ids only, in `baseline.json` → `held_out.known_wrong`):
`jupyter-pytorch-save-untrained-after-restart`, `jupyter-pytorch-val-acc-on-train-loader`,
`jupyter-timeit-second-uses-time` (FP); `jupyter-mnist-loss-curve-pandas-plot`,
`jupyter-pip-resolver-notice-installed`, `jupyter-sklearn-cv-kfold-object` (FN).

## Round 1 fixes (Nov 24 2026, `claude/eng-check-fixes-r1`)

The four round-1 case sets merged: 135 cases, 108 train + 27 held out. Every fix is general (no lesson ids, no case
text); each has a regression test in `server/checks/tests/test_round1_fixes.py`. Fixed against the train cases only;
the held-out wrong verdicts were never read (ids only) while fixing.

| | acc | prec | rec | FP | FN |
|---|---|---|---|---|---|
| train (108), before | 0.694 | 0.639 | 0.780 | 22 | 11 |
| train (108), after | 1.000 | 1.000 | 1.000 | 0 | 0 |
| held-out (27), before | 0.222 | 0.200 | 0.444 | 16 | 5 |
| held-out (27), after | 0.444 | 0.333 | 0.667 | 12 | 3 |

What changed in `server/checks`:

- **A terminal read per command** (`blocks.py`): prompt rows (zsh / bash / fish / oh-my-zsh, and AutoCAD's
  `Command:`) split the history into a command and its own output. A `screen_contains` match counts only in a
  command's newest run whose output shows no failure (`fatal:`, `error:`, `! [rejected]`, `nothing added to commit`,
  `*Cancel*`, `cd: no such file`), unless that failure is what the pattern wants; the step's Terminal target command
  must be among the commands that ran (program + subcommand; `git switch` for `git checkout`; `python -m <mod>` for
  `<mod>`; any JS runner's script or `npx` binary for `npm run <script>`); a clean run plus the
  step's `file_exists` proofs passes other wording. A `screen_absent` match is dropped when the command got past it
  (pip's resolver `ERROR:`, then `Successfully installed`), was run again since, or repeats an already-successful
  command with a "nothing to do" refusal. Error forms gained `1 failed`, `FAILED`, `error TS2305:`, `Found 1 error`.
  (git s2-s8, pytest, tsc build, pip, rebase, AutoCAD STLOUT.)
- **Notebooks and metrics**: "restart and run all" needs the run counts in order from [1]; a `nan` / `inf` beside
  the checked metric on its own lines in the newest run fails it as diverged; a value printed inside `tensor(...)` is read.
- **Equivalent code** (`code_equiv.py`): import aliases, `import mod` + `mod.f()`, several names per import, a
  renamed default import, `import * as`, `<Fragment>` for `<>`. A JSX tag pattern on a component file is a code
  check. A VS Code line that is on disk in another lesson file (a split editor) doesn't count for the check's file.
  A step whose files import a name their own module no longer defines / exports fails ("Imports resolve").
- **App files** (`model_files.py`): a scene dump is read for the objects the step names (and what is attached to
  them), long decimals are read at 4 places (float32 noise), "every / all / each" labels hold for every instance of
  the key, an STL / OBJ with no geometry fails, a number in a DXF text group (a dimension override) is not a
  measurement, and an export / render the step never named may have any name (same extension, same folder; image,
  mesh and CAD export kinds only, never code or notebooks; a file counts for one check, a name holding the check's own
  word first; never a file older than the step when the context gives its start). A word seen only as
  an item of an open "Add..." menu is not added.

Held-out wrong after the fixes (15): ids in `baseline.json` → `held_out.known_wrong`; not read.

## Round 1: Jupyter notebooks and ML training runs (Nov 24 2026)

20 new cases (13 training, 7 held out): NaN / inf divergence, a recovered loss spike, a run still mid-epoch, cell
run order (evaluate before fit, an edited cell not re-run, counts out of order), kernel restarts (Run All from [1],
only one cell re-run), plots (an imshow error after the prints, a figure saved but not shown), the lesson's own
common mistakes (wrong loss, `probabilities` not indexed, evaluating on the training set) and done-but-odd work
(compile and fit in two cells, a separate Softmax layer, a loss printed as a tensor).

Training cases wrong at the start of the round (all fixed, see "Round 1 fixes"):

- **FP `jupyter-mnist-s5-nan-loss-high-acc`**: the metric is `accuracy`; the same Keras line's `loss: nan` is never
  read, so an epoch-averaged 0.9563 passes a run whose weights went NaN.
- **FP `jupyter-restart-run-all-out-of-order`**: a `[1]` on screen and no error pass "Restart and run all" while the
  counts read [1], [5], [4]; nothing reads the notebook's execution order.
- **FN `jupyter-pytorch-xor-loss-printed-as-tensor`**: `loss tensor(0.2614, grad_fn=...)` doesn't fit the value
  class, so the loss trend waits forever on a finished run.

Held out: 7 cases, 4 wrong (ids in `baseline.json` → `held_out`). Seen, not a verdict error: a notebook cell that
raised before printing any metric (`jupyter-mnist-s5-categorical-crossentropy-error`) leaves the metric row
`pending`, never `fail`, so stuck-help can't fire.

## Round 1: multi-file VS Code projects (Nov 24 2026, 19 new cases, 6 held out)

Imports across files, renamed symbols, tests passing, build output and dev servers, in Python and JS/TS/React.
Train 69 (56 earlier + 13 new), held-out 6. Before any fix:

| | acc | prec | rec | FP | FN |
|---|---|---|---|---|---|
| train (69) | 0.855 | 0.857 | 0.857 | 5 | 5 |
| held-out (6) | 0.333 | 0.333 | 1.000 | 4 | 0 |

Train wrong verdicts before any fix (all fixed, see "Round 1 fixes"):

- **FP `terminal-pymod-m5-pytest-one-failed`** / **FP `terminal-tsshop-t3-build-error-under-old-success`**: a bare
  `failed` / `error` in a `screen_absent` pattern is exempted unless its line is an error form (`_absent_hit`), so
  pytest's `1 failed, 2 passed` and tsc's `- error TS2305:` don't count; and `built in` from an earlier build in the
  scrollback passes the newest (failed) one.
- **FP `vscode-pymod-m2-import-in-test-tab`**: the two code patterns are matched on the whole VS Code window, so a
  split editor supplies the import from test_operations.py and the call from main.py.
- **FP `vscode-pymod-m4-stale-import`** / **FP `vscode-react-s3-no-default-export`**: per-line code patterns can't
  see that a cross-file symbol no longer resolves (stale `import add` after the def was renamed; a default import of
  a file with only a named export). The ImportError / browser console error on screen is not consulted.
- **FN `vscode-pymod-m2-import-alias`**, **`-module-import`**, **`vscode-react-s3-aliased-import`**,
  **`vscode-tsshop-t2-multi-named-import`**, **`vscode-react-s6-named-fragment`**: equivalent import forms
  (`import x as y`, `import mod` + `mod.f()`, a default import under another name, several names in one `{ }`,
  `<Fragment>` for `<>`) fail patterns that hard-code the video's form. (s3c2 "Header component rendered" is also
  read as an output check because of the word "rendered".)

## Round 1: terminal and git (Nov 24 2026, 20 new cases, 7 held out)

Round 1 of the accuracy loop added 20 terminal / git cases (13 train, 7 held out): commands typed vs run, a
command's own echo vs its result (errors after `git add`, `git commit`, `git clone`, `git push`), branches created
vs switched, multi-step shells (`cd x; git init`), package installs (pip resolver notice, venv not activated,
npm 10's `npm error`), exit codes on a hidden terminal.

| | acc | prec | rec | FP | FN |
|---|---|---|---|---|---|
| train (69) | 0.855 | 0.811 | 0.909 | 7 | 3 |
| train terminal (29) | 0.655 | 0.588 | 0.769 | 7 | 3 |
| held out (7) | 0.143 | 0.167 | 0.500 | 5 | 1 |

Train wrong verdicts before any fix (all fixed, see "Round 1 fixes"), worst first:

- **FP `terminal-git-s2-init-wrong-folder-chain`**: `cd projct1; git init` initialised `~`; "Initialized empty"
  is on screen, so it passes.
- **FP `terminal-git-s3-touch-ls-not-staged`**: the file names in an `ls` listing pass "Staged learning.py".
- **FP `terminal-git-s4-add-not-a-repo`**, **`-s5-commit-nothing-added`**, **`-s6-clone-not-found`**,
  **`-s8-push-rejected`**: the pattern matches the command line itself (or the `[rejected]` ref line), and the
  error that follows (`fatal:`, `nothing added to commit`, `! [rejected]`) is never weighed.
- **FP `terminal-git-s7-branch-created-not-switched`**: `update-name` in `git branch`'s list, HEAD still on main.
- **FN `terminal-git-s2-reinitialized`**: "Reinitialized existing Git repository" is not "Initialized empty".
- **FN `terminal-mnist-s1-pip-resolver-error-installed`**: pip's `ERROR: pip's dependency resolver ...` notice
  fails "No terminal errors" although "Successfully installed" follows.
- **FN `terminal-rebase-s3-continue-twice`**: a later, harmless `fatal: No rebase in progress?` fails
  "No rebase conflicts" after "Successfully rebased".

Held-out wrong verdicts (ids only): `terminal-calc-s2-hidden-exit-1-after-5`,
`terminal-git-s7-fish-typed-not-run`, `terminal-git-s7-pathspec-error`, `terminal-mnist-s1-forgot-activate`,
`terminal-react-s1-npm10-error` (FP); `terminal-git-s8-push-ligature-arrow` (FN).

## Round 1: Blender and CAD (Nov 24 2026, 20 new cases, 7 held out)

From Adrian's plans on `origin/adrian/ui-next` (`docs/ui-next/catalog/plans/intro-blender`, `intro-cad`,
`intro-fusion`: each lesson's `passes` line) and `docs/ui-next/INTEGRATIONS.md`, plus the app-lesson fixtures in
`server/workspace/tests/fixtures` (`blender_donut.json`, `autocad_toy_car.json`, run through `app_lesson.adapt`).
Two levels, both graded by today's check types:

- **Screen** (what app lessons do today): `screen_contains` pinned to `Blender` / `AutoCAD` on a fixed OCR reading
  of the app window (menus open, the command line's history).
- **File** (INTEGRATIONS.md "file level"): the facts a headless run reads from the saved model, recorded as fixtures.
  `Blender --background mug.blend --python dump_scene.py` prints objects (location, `rotation_deg`, scale,
  dimensions, hidden), mesh counts / smooth / `islands`, modifiers (type, levels, render_levels), materials
  (users, Principled roughness / metallic) and lights; `FreeCADCmd` prints bodies, features in order (type,
  Length, `valid`, error), sketches (constraints, `dof`, closed / open wires), the final shape and
  `recompute_errors`. The dump sits next to the model as `<name>.scene.json` and the steps grade it with
  `file_contains`. AutoCAD cases read the ASCII DXF the learner saves (layer table, entity layers in group 8,
  DIMENSION measurement in group 42, text override in group 1); exports are STL files (ASCII, `solid` /
  `facet normal`).

The traps are the ones a regex over a whole scene or drawing can't see: the right fact on the wrong object (the
default Cube kept the modifier or the material), a menu item read as the thing added, a command typed then
cancelled, a feature present in the tree but failed to recompute, a dimension's text typed over the real length,
an export with no triangles, and the done-but-odd side: float32 noise (`90.00000250447816` degrees,
`119.9999999999999` mm), another command for the same result, a file named differently from the one the step
guessed.

Before any fix: The 56 cases before Nov 24 all score right (their Nov 22 wrong verdicts were fixed). The new Blender and CAD
training cases (13) score:

| training | acc | prec | rec | FP | FN |
|---|---|---|---|---|---|
| overall (69) | 0.855 | 0.795 | 0.939 | 8 | 2 |
| blender (8) | 0.250 | 0.333 | 0.500 | 4 | 2 |
| cad (5) | 0.200 | 0.200 | 1.000 | 4 | 0 |
| jupyter, metric, terminal, vscode (56) | 1.000 | 1.000 | 1.000 | 0 | 0 |

Held-out (7): acc 0.000 (4 FP, 3 FN). Not listed here on purpose (`--held-out`).

Training wrong verdicts before any fix (all fixed, see "Round 1 fixes"), worst first:

- **FP `blender-mug-subsurf-on-default-cube`, `blender-material-glossy-on-cube`**: `file_contains` over the whole
  scene dump can't tie a fact to the object the step is about; the Subdivision modifier / the glossy material is on
  the default Cube, not the Mug.
- **FP `freecad-plate-80mm-pocket-broken`**: `"valid": true` finds the valid Sketch and Pad; the Pocket and
  Sketch001 failed to recompute (`recompute_errors` is not empty).
- **FP `freecad-hook-stl-empty-export`**: `file_exists` + `^solid` pass an STL with no facets.
- **FP `autocad-dxf-dimension-text-overridden`**: `120` is the dimension's typed text override; the measured length
  (group 42) and the geometry say 118.5.
- **FP `blender-donut-s3-add-modifier-menu`, `blender-light-add-menu-open`**: the word is on screen only as an item
  of an open menu (Add Modifier > Generate, Shift+A > Light).
- **FP `autocad-toy-car-s3-stlout-cancelled`**: `STLOUT` on the command line, followed by `*Cancel*`.
- **FN `blender-transform-cone-rotation-float`**: R X 90 is stored as float32 radians; the dump reads
  90.00000250447816 degrees, which `90(?:\.0+)?\s*[,\]]` refuses.
- **FN `blender-render-saved-as-untitled-png`**: the render is saved as Blender's default `untitled.png`; the check
  guessed `mug.png`.

## First baseline (56 cases, Nov 22 2026)

All eight wrong verdicts fixed in 2b86a0db. Not verdict errors, but seen in the rows (Nov 22): a finished notebook cell below a metric bar
(`jupyter-mnist-s5-low-accuracy`, `-s7-below-95`) stays `pending`, never `fail`, so stuck-help can't fire.

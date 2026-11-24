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
      "base.stl": {"base64": "U1RM..."},              // a binary file, byte for byte (a binary STL)
      "mnist.ipynb": {"notebook": {"from": "server/tests/fixtures/t10_mnist.ipynb", "keep_cells": 1,
                                   "unrun": [0], "replace": [[0, "old", "new"]], "append": [cell],
                                   "counts": [16, 17, null]}},   // execution counts in cell order (run order)
      "Untitled.ipynb": {"notebook": {"cells": [{"source": "...", "stdout": "...", "error": "NameError: ...",
                                                 "image": true, "run": false, "count": 4}],
                                      "kernel": ".venv (3.12.16)", "kernel_version": "3.12.16"}},
      // more cell outputs: "stderr": "...UserWarning..." (a warning stream), "result": "np.float64(3.4e-11)"
      // (Out[n], the last expression's repr), "image": "<Figure size 640x480 with 1 Axes>" (a figure with that text)
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

## Round 5: Jupyter notebooks and ML training runs (Nov 24 2026, `claude/eng-evals-r5-0`)

17 new cases (11 train, 6 held out), no engine change (the runner already scores `heldOut` apart). Steps: the MNIST
video lesson (s5 fit, s7 evaluate), the NN-from-scratch text lesson (nn4, terminal) and, inline in the lesson
builder's shape, lessons from Adrian's catalog plans (`origin/adrian/ui-next`, `docs/ui-next/catalog/plans/`):
PyTorch ("Datasets and DataLoader" `pt6s4`, "Hold out data and measure accuracy" `pt7s3`, "Use the Mac GPU"
`pt8s4`), NumPy ("Random numbers with a seed" `np7s4`), Neural networks ("Train a tiny network on XOR" `nn9s5`),
Plotting ("Subplots side by side" `pl6s4`), pandas ("Plot from a DataFrame" `pd9s4`) and Intro to Jupyter ("Install
a package and draw a chart" `jup6s5`, "Restart and run all" `jup7s3`).

The traps: a DataLoader without `shuffle=True` over points made in linspace order; `xb.to(device)` not assigned
(`mps:0 cpu`); held-out accuracy that sits above 0.9 for epochs and ends at 0.865; a seeded generator made in an
earlier cell and the rolls cell re-run (a new count); `plt.subplots(2, 1)` where the step wants one row; a groupby on
`item` instead of `weekday` with sales.png saved; a notebook whose `goal` cell was deleted, restarted and never run
again (old counts [1], [3], [4]); a cell skipped after a restart ([1], [2], [ ], [3]); Keras accuracy above 0.95 for
three epochs while the loss doubles and the last epoch reads 0.9102. Done-but-odd: `print(len(loader),
tuple(xb.shape))` -> `32 (32, 2)`; Out[3] `(device(type='mps', index=0), ...)`; a seeded cell run twice ([1], [3]);
XOR's loss flat at 0.2500 for half the run, then falling to 0.0051; a stale ModuleNotFoundError above the chart cell
from before `%pip install`; `model.fit` re-run (epoch 1 already at 0.9874); `model.evaluate(..., verbose=0)` (no
progress line); a stale unsaved-file run in the terminal scrollback above the run that converged.

| before any fix | acc | prec | rec | FP | FN |
|---|---|---|---|---|---|
| train (268: 257 earlier + 11 new) | 0.974 | 0.966 | 0.974 | 4 | 3 |
| train, the 11 new | 0.364 | | | 4 | 3 |
| held-out (114: 108 earlier + 6 new) | 0.447 | 0.318 | 0.500 | 43 | 20 |
| held-out, the 6 new | 0.667 | | | 1 | 1 |

Train wrong verdicts (all new; the 257 earlier train cases still score right), in `baseline.json` → `known_wrong`:

- **FP `jupyter-numpy-dice-rng-in-earlier-cell-rerun`**: the seed, the roll and a printed count are all there; nothing
  sees that the generator lives in an earlier cell than the one the step re-runs.
- **FP `jupyter-plot-subplots-stacked-two-rows`**: `plt.subplots(` matches; the (rows, cols) the instructions give
  are not compared.
- **FP `jupyter-pytorch-device-batch-not-reassigned`**: the output pattern accepts any two device names; a bare
  `xb.to(device)` (result dropped) and two different devices are not weighed.
- **FP `jupyter-restart-run-all-restarted-not-run`**: a [1] and no error; the old counts skip [2] and no cell defines
  `goal` any more.
- **FN `jupyter-chart-old-import-error-above`**: `No cell error` reads the stale ModuleNotFoundError of an earlier
  cell that an install below it has since fixed.
- **FN `jupyter-mnist-s7-evaluate-verbose0`**: s7c3 wants evaluate's progress line, which `verbose=0` never prints.
- **FN `jupyter-pytorch-device-repr-out`**: the device pair shown as Out[n] (`device(type='mps', index=0)`) does not
  read as `mps:0`.

Held-out wrong verdicts (ids only): `jupyter-pandas-plot-by-item-not-weekday` (FP),
`jupyter-pytorch-loader-shape-tuple` (FN).

## Round 5: multi-file VS Code projects, Python and JS/TS/React (Nov 24 2026, `claude/eng-evals-r5-1`)

20 new cases (13 train, 7 held out), no engine change. Steps from `py-modules.json` (m2, m4, m5), `ts-shop.json`
(t2, t4), the React/Vite lesson (s7, s8) and the earlier inline TypeScript step `ts4s3`, plus new inline steps in
the lesson builder's shape from Adrian's catalog plans (`origin/adrian/ui-next`, `docs/ui-next/catalog/plans/`):
Intro to TypeScript "Compile your first TypeScript file" (`ts1s4`) and "Set up tsconfig with strict on" (`ts2s1`,
rootDir / outDir), React "Render a list" (`re7s3`), "Forms and controlled inputs" (`re8s4`), "Share state between
components" (`re9s4`), "Effects" (`re10s3`) and "Write JSX" (`re2s4`, dev server running), and Intro to VS Code
"Settings and format on save" (`vs8s3`).

Traps: the module file named `Operations.py` (macOS ignores case, Python's import does not:
`ModuleNotFoundError`), a JSX expression typed without braces (`&copy; new Date().getFullYear()` and
`<span>formatPrice(item.price)</span>` render as text), `return clearInterval(id)` (called at once, not a cleanup),
`key="todo"` on every item, the key inside the child component instead of on the mapped element, a SearchBox that
keeps its own `useState` copy of the lifted query, a form handler with no `e.preventDefault()` (the page reloads), a
run-time `TypeError` in the browser while Vite's terminal is clean, `settings.json` at the folder root instead of
`.vscode/`, a type error silenced with `qty: any`, `// "outDir": "./dist"` left commented, tsc's `Found 1 error`
with greet.js emitted anyway, and `4 passed` from another project's folder. Done-but-odd: `total = add(2, 3)` then
`print(total)`, a `"add:"` label string after an F2 rename, a test function still named `test_add`, a star import
after the rename, `export default function Food()`, and Jest's "worker process has failed to exit gracefully"
notice under `5 passed`.

| before any fix | acc | prec | rec | FP | FN |
|---|---|---|---|---|---|
| train (270: 257 earlier + 13 new) | 0.967 | 0.942 | 0.983 | 7 | 2 |
| train, the 13 new | 0.308 | | | 7 | 2 |
| held-out (115: 108 earlier + 7 new) | 0.435 | 0.292 | 0.500 | 46 | 19 |
| held-out, the 7 new | 0.429 | | | 4 | 0 |

Train wrong verdicts (all new; the 257 earlier train cases still score right), in `baseline.json` → `known_wrong`:
FP `vscode-pymod-m2-module-file-capitalised`, `vscode-react-card-runtime-error-blank-page`,
`vscode-react-effect-cleanup-called-at-once`, `vscode-react-list-same-key-every-item`,
`vscode-react-s7-year-without-braces`, `vscode-settings-json-in-project-root`, `vscode-ts-invoice-silenced-with-any`;
FN `vscode-pymod-m2-result-in-variable` (m2c2 wants `print(add(2, 3))` literally),
`vscode-react-s8-export-default-function` (s8c4 wants a separate `export default Food`).

## Round 5: terminal and Git workflows (Nov 24 2026, `claude/eng-evals-r5-2`)

20 new `terminal` cases (13 train, 7 held out; 8 pass, 12 not_yet), no engine change and no runner change (the
held-out split already exists). Steps from the repo's lessons (Git video lesson s8 / s9, MNIST s1, calculator s2) and
inline steps in the lesson builder's shape from Adrian's catalog plans (`docs/ui-next/catalog/plans/`, commit
213c9238): Intro to Git (undo, .gitignore, log and diff, merge, push, SSH key), Intro to the Terminal (make files,
wildcards, pipes and grep), Intro to Docker (first container, Compose), Intro to JavaScript (first run), a
scikit-learn venv setup step and a package added to the ts-shop project.

The traps: .gitignore committed by `git add .` together with the .DS_Store it ignores; a `git pull` that stopped on a
CONFLICT, with "insertion" from the learner's own commit above it and `git show` of that commit; a commit on a detached
HEAD (`[detached HEAD 7e8f9a0]`, still "working tree clean"); `grep -h` without the step's `-i` (rain.txt misses the
capitalised line); `cp notes/day*` where the step says `?` (the backup note copied too); `pip install` interrupted with
^C, then a pip upgrade's "Successfully installed" and a Jupyter from outside the venv; `docker pull` instead of `docker
run`, with another container's "Exited (0)"; `npm install` in the parent folder (clean output, shop/package.json
untouched). Held out: a merge ref typo with `git log --all` showing the branch; `master` pushed after "src refspec main
does not match any"; `ssh-keygen` waiting at its passphrase prompt; Compose's "Running 1/2" over "port is already
allocated". Done-but-odd: `git checkout -- file` for `git restore`; `git push` with no upstream, then the
`--set-upstream` push git suggested; `touch notes/day{1,2,3}.txt` checked with `ls | wc -l`; `pip install sklearn`
(deprecated name, errors) then `pip install scikit-learn`; `python` not found, then `python3`. Held out: zsh "no
matches found" then the right glob; `brew install tree` when it is already installed; `node hello` without `.js`.

| | acc | prec | rec | FP | FN |
|---|---|---|---|---|---|
| train (13 new) | 0.385 | 0.333 | 0.600 | 6 | 2 |
| held-out (7 new) | 0.286 | 0.000 | 0.000 | 2 | 3 |

Wrong verdicts. Train: `terminal-dockercat-hello-world-pulled-not-run`, `terminal-git-s9-pull-conflict-local-commit-
insertion`, `terminal-gitcat-commit-on-detached-head`, `terminal-gitcat-gitignore-committed-with-ds-store`,
`terminal-pkg-npm-install-outside-project`, `terminal-shellcat-grep-missed-capitalised-rain` (FP);
`terminal-pkg-sklearn-deprecated-then-scikit-learn`, `terminal-shellcat-touch-brace-expansion-counted` (FN). Held out:
5 (ids in `baseline.json`). `baseline.json` rewritten: train 270 cases (acc 0.970, the 8 in `known_wrong`), held out
115 (acc 0.426).

## Round 4 fixes (Nov 24 2026, `claude/eng-check-fixes-r4`)

The four round-4 case sets merged: 365 cases, 257 train + 108 held out (75 new: 49 train, 26 held out). Every fix is
general (no lesson ids, no case text); each has a regression test in `server/checks/tests/test_round4_fixes.py` (all
31 fail on the engine before these fixes, and each also checks the finished form still passes). Fixed against the
train cases only; the held-out cases were never read while fixing (ids only).

| | acc | prec | rec | FP | FN |
|---|---|---|---|---|---|
| train (257), before | 0.875 | 0.820 | 0.909 | 22 | 10 |
| train (257), after | 1.000 | 1.000 | 1.000 | 0 | 0 |
| held-out (108), before | 0.417 | 0.276 | 0.432 | 42 | 21 |
| held-out (108), after | 0.435 | 0.300 | 0.486 | 42 | 19 |
| held-out, the 26 new, before / after | 0.346 / 0.346 | | | 12 / 12 | 5 / 5 |

Honest generalisation: the 17 round-4 held-out wrong verdicts are all still wrong; two earlier-round held-out cases
are now right (`gh repo clone` read as `git clone`, and a git failure the learner got past with the same subcommand),
and no held-out case got worse. A broader "N mm tall" rule (no body measures N) also caught one more held-out case,
but it was narrowed to the Symmetric extrude before that was known, because it would false-fail a boss "10 mm high"
on a plate; it stays narrow.

What changed (server/checks):

- **Scene / drawing claims** (`model_files.claims`, `dxf_claims`, `alt_views`): a modifier off in both viewport and
  render; overlapping UV islands when the step says none overlap; a curve that never rises above its last key when the
  step asks for an overshoot; a Shell that removed no face when the step opens one; a Symmetric extrude of N (one side)
  for "N mm tall"; the step's entities on another layer than "On layer X" (a layer only in the table holds nothing).
  Read another way: a rotation by its size (R X -90 is turned 90 degrees) and a bound box with X / Y swapped, unless
  the step gives a direction or names an axis; numbers a step gives only "for example" (any value), with a label's
  relation checked on the two named values ("Slot 0.3 mm wider than the arm": SlotWidth - ArmWidth).
- **Exports**: a render named for its frames (`0001-0048.mp4`) when the step renders another range is not the step's
  file (`_claim_any_names`).
- **Terminal** (`blocks`, `_on_blocks`): `git merge` / `rebase` with another branch than the step's is another command;
  `gh repo create --source --remote --push` runs `git remote add` and `git push`, and its `HEAD -> main` is `main ->
  main` when git says main tracks origin/main; a git failure followed by a successful run of the same subcommand is
  history; `cargo run` with nothing to compile (`Finished`, no `Compiling`) matches the `Compiling <pkg> v<ver>` row from
  the lesson's Cargo.toml; a dev server's own error rows (`[vite] Internal server error`, `Pre-transform error`,
  webpack `ERROR in`) fail a "no errors" check until a later `hmr update`; a scaffolder prompt answered with none of the
  step's chosen words (`✔ Select a framework: › Vanilla`) fails the step (`scaffold_choices`).
- **Code** (`code_equiv`, `evaluate_gate`): a type-hinted def reads as the plain def; a list callback that destructures
  its element (`items.map(({ price }) => ...)`) reads as `item.price`; a rename step after which a lesson file still
  binds the old name (a copy, or `export const scale = scaleRecipe`) fails (`renamed_leftover`); an import beside a
  top-level declaration of the same name (TS2440); a `return (...)` with two JSX roots side by side; a code check whose
  label says a method is "called" and whose pattern is only its name needs the call's `(`.
- **Notebooks** (`evaluate_gate`, `_screen`): a metric value group that insists on decimals also reads a whole number
  (`98%`); a printed NumPy vector (`[[0.] [0.] [0.] [1.]]`) also reads as a list `[0, 0, 0, 1]`; an output check never
  passes on another cell's output on screen (cells holding a line of the step's code count as the step's); an output
  printed before a later run rebound what it reads (non-constant) is stale; `backward()` without zeroing, run again
  since the cell that made the tensors, accumulated the gradient; a keyword the instructions spell out left out of the
  call (`bins=`), or a slice of the data where the step passes all of it (`fit(train_images[:1000], ...)`); drawing on
  axes made in an earlier cell with no figure in the cell's output (inline backend); a value printed after an update
  (`optimizer.step()`) that was computed before it, where the step's code computes it again.

`baseline.json`: train 1.000 with no `known_wrong`; held-out 0.435 (61 known wrong, ids only).

## Round 4: Jupyter notebooks and ML training runs (Nov 24 2026, `claude/eng-evals-r4-0`)

18 new cases (12 train, 6 held out), no engine change. The runner's notebook cells gained `stderr`, `result`
(Out[n]) and a text `image` so a case can show a bare expression's repr (`np.float64(...)`, `[<Line2D ...>]`,
`<BarContainer object of 10 artists>`) the way Jupyter saves it. Steps: the MNIST video lesson (s5 fit, s7
evaluate) and, inline, lessons from Adrian's catalog plans (`origin/adrian/ui-next`, `docs/ui-next/catalog/plans/`)
in the lesson builder's shape: Neural networks ("Gradients by hand", "Gradient descent" on AND), PyTorch
("Autograd", "Loss functions and optimizers"), scikit-learn ("Fit and predict", "Cross-validation", "Compare two
models") and Plotting ("Your first line plot", "Histograms", "Save a figure").

The traps: `val_accuracy: 0.95..` beside a training accuracy of 0.9431 (sgd, `validation_split`); fit on
`train_images[:1000]` run twice (0.995 on 1000 images); the model cell re-run after fit; predictions printed in an
older cell than the training run that changed the weights; `loss.backward()` run twice so `w.grad` reads 12 beside
a hand value of 6; an "after" loss that re-prints the tensor from before the step; `predict(X_train)` while the 45 on
screen is the split cell's `(45, 13)`; `cv=3` where five folds are asked; a flipped comparison that names the lower
model; `ax.hist(sums)` with 10 default bins; `ax.plot` in a later cell than `plt.subplots` (no image); `plt.savefig`
in a new cell after `plt.show()` (a blank 1280 px PNG). Done-but-odd: `validation_split` columns, `{acc:.0%}` ->
`98%`, a `(4, 1)` column of rounded predictions, `np.float64(3.44e-11)` as Out[3], `bins=range(2, 14)`.

| before any fix | acc | prec | rec | FP | FN |
|---|---|---|---|---|---|
| train (220: 208 earlier + 12 new) | 0.959 | 0.931 | 0.979 | 7 | 2 |
| train, the 12 new | 0.250 | | | 7 | 2 |
| held-out (88: 82 earlier + 6 new) | 0.420 | 0.306 | 0.469 | 34 | 17 |
| held-out, the 6 new | 0.167 | | | 4 | 1 |

Train wrong verdicts (all new; the 208 earlier train cases still score right): FP
`jupyter-mnist-s5-fit-on-1000-image-slice`, `jupyter-nn-gd-and-stale-predictions`, `jupyter-plot-hist-ten-bins`,
`jupyter-plot-line-later-cell-no-image`, `jupyter-pytorch-autograd-backward-rerun-accumulated`,
`jupyter-pytorch-optim-step-loss-unchanged`, `jupyter-sklearn-predict-on-train-45-elsewhere`; FN
`jupyter-mnist-s7-whole-percent` (the metric pattern wants `NN.NN%`; s7c4 stays pending), `jupyter-nn-gd-and-column-array`
(the `[0, 0, 0, 1]` pattern never sees NumPy's column print). `baseline.json` records them in `known_wrong`.

## Round 4: multi-file VS Code projects, Python and JS/TS/React (Nov 24 2026, `claude/eng-evals-r4-1`)

20 new cases (13 train, 7 held out), no engine change (the runner already scores `heldOut` apart). Steps from
`py-modules.json` (m2, m4, m5), `ts-shop.json` (t2, t3, t4) and the React/Vite lesson (s1, s3, s6, s8), plus inline
steps in the lesson builder's shape from Adrian's catalog plans (`origin/adrian/ui-next`,
`docs/ui-next/catalog/plans/`): React "Pass data with props" (`re4s3`, MenuItem with name and price) and "Write JSX"
with the dev server running (`re2s4`), and Intro to VS Code "Jump around and rename safely" as an ES module project
(`vs6s4`, rename then `node scale.js`).

Traps: add copied to add_numbers instead of renamed (both defined, the test still uses add), a relative
`from .operations import add` in a script, pytest.ini's `addopts = -k "not divide"` (`2 passed, 1 deselected`), an
old local `formatPrice` left below the import (TS2440), a `formatPrice` in utils.ts that lost its `export`, a build
script edited down to `vite build` to get past a tsc error, `npm create vite` answered Vanilla (no react in
package.json, no App.jsx), `<Header />` only inside a JSX comment, `<Footer/>` beside the fragment (two roots),
`{food2.toUpperCase}` never called, `function MenuItem(name, price)` without braces, Vite's `[vite] Internal server
error` (not `ERR!`), and an old export re-exported (`export const scale = scaleRecipe`) instead of renaming the import.
Done-but-odd: a type-hinted `def add_numbers(a: int, b: int) -> int:`, a destructured map callback
(`formatPrice(price)`), Vite's sourcemap "Error when using sourcemap" warning above `✓ built in`, a passing test's
`console.error('formatPrice failed: ...')` in Jest's output, `props.name` instead of destructuring, a Vite error fixed
by a later `hmr update`, and F2's real `{ scaleRecipe as scale }` import alias.

| before any fix | acc | prec | rec | FP | FN |
|---|---|---|---|---|---|
| train (221: 208 earlier + 13 new) | 0.959 | 0.931 | 0.979 | 7 | 2 |
| train, the 13 new | 0.308 | | | 7 | 2 |
| held-out (89: 82 earlier + 7 new) | 0.461 | 0.326 | 0.469 | 31 | 17 |
| held-out, the 7 new | 0.714 | | | 1 | 1 |

Train wrong verdicts (all new; the 208 earlier train cases still score right), in `baseline.json` → `known_wrong`:

- **FP `vscode-pymod-m4-duplicated-not-renamed`**: both m4 rows are on screen; nothing sees that operations.py still
  defines `add` and test_operations.py still imports it.
- **FP `vscode-tsshop-t2-local-formatprice-conflicts`**: the import and the call match; a local `function formatPrice`
  in the same file (and `⊗ 1`) is not weighed.
- **FP `vscode-recipe-rename-old-name-reexported`**: recipe-utils.js defines scaleRecipe and the run prints; scale.js
  (not on screen) still imports `scale`, and the precision row on scale.js isn't in the gate.
- **FP `vscode-react-s6-footer-outside-fragment`**: `<>`, `import Footer` and `<Footer` all match; the second root
  after `</>` (and Vite's "Adjacent JSX elements" pre-transform error) is not read.
- **FP `vscode-react-s8-touppercase-not-called`**: `toUpperCase` matches without its call parentheses.
- **FP `terminal-react-s1-vanilla-template`**: "ready in" + "localhost:"; package.json without react is not checked.
- **FP `terminal-react-jsx-vite-internal-server-error`**: `ERR!|Failed to compile` misses Vite's own
  "Internal server error" / "Pre-transform error" wording.
- **FN `vscode-pymod-m4-type-hinted-def`**: `def\s+add_numbers\(a,\s*b\):` refuses type hints on the same def.
- **FN `vscode-tsshop-t2-destructured-price`**: `formatPrice\(\s*item\.price\s*\)` refuses `formatPrice(price)` from
  a destructured item.

Seen right (train): the sourcemap warning build, Jest's captured `console.error` with "failed" in it, F2's import
alias, `MenuItem(name, price)`. Held-out: ids of the new wrong verdicts in `baseline.json` →
`held_out.known_wrong`; not listed here on purpose.

## Round 4: terminal and Git workflows (Nov 24 2026, `claude/eng-evals-r4-2`)

18 new `terminal` cases (12 train, 6 held out; 7 pass, 11 not_yet), no engine change. All inline steps in the shape
the lesson builder gives the Git video lesson, from Adrian's catalog plans (`origin/adrian/ui-next`,
`docs/ui-next/catalog/plans/`): Intro to Git and GitHub (the cookbook project: set up, stage and commit, log and diff,
ignore files, merge, fix a conflict, push), Intro to the terminal (trail-log: make files, chmod, a script with an
argument), Intro to Docker (hello-world, port mapping, stop and remove, build and tag), Intro to Python ("Read an
error message", three scripts run in one shell line) and Intro to Rust (`cargo run`).

The traps: a merge run the wrong way round (`git merge main` on the branch, "Already up to date.") and the unmerged
branch then forced away with `-D`; a merge commit typed before `git add` ("Committing is not possible because you have
unmerged files": the pattern is only the typed message); `git add` misspelt in an `&&` chain, so the commit never ran;
`git commit -am` with the new .gitignore untracked; "working tree clean" from before an edit, with `git log` showing
two commits; `./count.sh` run without its word (`grep -ci ""` counts every line); notes touched one folder too high;
a Docker name conflict under a stale `docker ps` row; `docker tag 1.0 1.1` instead of a build (same IMAGE ID, old
page); `docker stop web` printing the same `web` as `docker rm web`; three scripts joined with `;`, so the chain exits
0 past a TypeError. Done-but-odd: a commit by path that failed before the add + commit that worked; `gh repo create
--push` (`HEAD -> main`, not `main -> main`); plain `git init` with the `master` hint, renamed with `git branch -m
main`; `chmod u=rw,go=` checked with `stat` (`600`); Docker's daemon error before the run that worked; `cargo run`
after `cargo build` (no `Compiling` line).

| | acc | prec | rec | FP | FN |
|---|---|---|---|---|---|
| train (12 new) | 0.667 | 0.667 | 0.400 | 1 | 3 |
| held-out (6 new) | 0.333 | 0.000 | 0.000 | 2 | 2 |

Wrong verdicts. Train: `terminal-gitcat-merge-wrong-way-force-delete` (FP), `terminal-gitcat-commit-pathspec-then-add`,
`terminal-gitcat-push-gh-repo-create-head-main`, `terminal-rust-cargo-run-already-built` (FN). Held out: 4 (ids in
`baseline.json`). `baseline.json` rewritten: train 220 cases (acc 0.982, the 4 in `known_wrong`), held out 88 (acc
0.432).

## Round 4: Blender and CAD / AutoCAD / Fusion files (Nov 24 2026, `claude/eng-evals-r4-3`, 19 new cases, 7 held out)

No engine change and no runner change (the held-out split already exists). Steps from Adrian's plans on
`origin/adrian/ui-next` (`docs/ui-next/catalog/plans`: `intro-blender` 2 and 7, `blender-materials` 2, 4 and 9,
`blender-animation` 4, 6, 8 and 9, `intro-fusion` 4, 5 and 6, `cad-3d-printing` 5, 6 and 9, each lesson's `passes`
line) and `docs/ui-next/INTEGRATIONS.md` (headless `dump_scene.py` / `dump_fcstd.py` facts as fixtures, the Fusion
add-in's design JSON), plus the AutoCAD toy car as ASCII DXF. Dump fields new this round, read by name: a modifier's
`show_viewport` / `show_render`, an object's `constraints` (type, target, `is_valid`), a mesh's `seams` / `uv_layers` /
`uv` (islands, `overlapping_islands`), an fcurve's `handle_types` / `handles` / `evaluated_range`, a Fusion feature's
`extent` / `edge_directions` / `faces_removed`, a body's `open_faces`, a FreeCAD chamfer's `edges`, a hole pattern's
`centres`, and a Cycles render's PNG metadata (`cycles.ViewLayer.samples`).

Traps: a Subdivision modifier at level 2 switched off in viewport and render, IOR 1.52 typed on the glow material
instead of the glass one, U > Reset (all UV islands stacked), a Cycles PNG rendered at 4096 samples before the scene
was set to 128, a bounce whose last peak is higher, a Track To with no target, Graph Editor handles edited but no
overshoot, a stale `0001-0048.mp4` after the range became 96, a symmetric 30 mm extrude (60 tall), a fillet on the four
top edges instead of the vertical ones, a Shell with no face removed, a chamfer on an outer edge not the pocket rim,
lid holes on a 50 x 30 pattern over posts on 52 x 32, a dimension on layer 0 while DIMS sits empty. Done-but-odd:
R X -90 for "turned 90 degrees", `bounce0001-0096.mp4`, an 80 x 50 x 30 body with the long side on Y, a 1.7 mm arm in
a 2.0 mm slot where the instructions' example says 2 / 2.3, wheels as a block inserted twice on WHEELS.

Before any fix (the engine is the round-3 fix state):

| | acc | prec | rec | FP | FN |
|---|---|---|---|---|---|
| train (220 = 208 + 12 new) | 0.955 | 0.930 | 0.969 | 7 | 3 |
| train, the 12 new | 0.167 | 0.125 | 0.250 | 7 | 3 |
| train blender (28) | 0.821 | 0.714 | 0.909 | 4 | 1 |
| train cad (22) | 0.773 | 0.625 | 0.714 | 3 | 2 |
| held-out (89 = 82 + 7 new) | 0.416 | 0.286 | 0.452 | 35 | 17 |
| held-out, the 7 new | 0.143 | | | 5 | 1 |

Train wrong verdicts (10 of the 12 new; the 208 earlier train cases stay right):

- **FP `blender-subsurf-modifier-toggled-off`**: `SUBSURF` and `levels: 2` match; `show_viewport` / `show_render`
  false is not read, so a modifier that does nothing passes.
- **FP `blender-crate-uv-reset-overlap`**: seams and `UVMap` match; `overlapping_islands: 6` against "do not overlap"
  in the step is not read.
- **FP `blender-graph-handles-no-overshoot`**: an `ALIGNED` handle matches; the curve never rises above its last key
  (`evaluated_range` max 5.0 = the final value).
- **FP `blender-anim-mp4-stale-48-frames`**: `0001-0048.mp4` counts as `bounce.mp4` ("any name will do") though
  Blender's own range name says 48 frames against the scene's 96.
- **FP `fusion-extrude-symmetric-60-tall`**: `distance: 30` matches; `extent: symmetric` makes the body 60 tall
  (bound box 80 x 50 x 60).
- **FP `fusion-shell-no-face-removed`**: the Shell with thickness 2 matches; `faces_removed: 0` (closed on top) is
  not weighed against "open on top".
- **FP `autocad-dxf-dimension-on-layer-0`**: `DIMS` matches the layer table row; the DIMENSION's own group 8 is `0`.
- **FN `blender-cone-turned-minus-90`**: `rotation_deg` -90 fails a pattern for 90.
- **FN `freecad-snapfit-arm-1p7-slot-2p0`**: the example numbers (2, 2.3) are wanted; the 0.3 mm difference the
  step is about (1.7 / 2.0) is not computed, and only the first body (Hook) is read.
- **FN `fusion-block-bound-box-50-by-80`**: a bound box `[50, 80, 30]` fails a pattern for `[80, 50, 30]`.

Seen right (train): the bounce with a higher last peak fails "Each peak lower than the last"; `bounce0001-0096.mp4`
passes as the MP4.

Held out: 7 new cases, 6 wrong (ids in `baseline.json` → `held_out.known_wrong`). Not listed here on purpose.

## Round 3 fixes (Nov 24 2026, `claude/eng-check-fixes-r3`)

The four round-3 case sets merged: 290 cases, 208 train + 82 held out. Every fix is general (no lesson ids, no case
text); each has a regression test in `server/checks/tests/test_round3_fixes.py` (all 31 fail on the engine before
these fixes). Fixed against the train cases only; the held-out cases were never read while fixing (ids only).

| | acc | prec | rec | FP | FN |
|---|---|---|---|---|---|
| train (208), before | 0.851 | 0.802 | 0.880 | 20 | 11 |
| train (208), after | 1.000 | 1.000 | 1.000 | 0 | 0 |
| held-out (82), before | 0.427 | 0.311 | 0.467 | 31 | 16 |
| held-out (82), after | 0.439 | 0.318 | 0.467 | 30 | 16 |

The held-out set barely moved (one case, `terminal-tsshop-t4-failing-test-skipped`, now right): the round-3 traps
are mostly one of a kind, so a fix for one rarely covers another. Read that as the honest generalisation number.

What changed (server/checks):

- **Notebook kernel state** (`evaluate_gate`): `undone_setup` (a cell that changes a name, `model.fit`, ran, then a
  cell above it that binds the name afresh ran again before the step's cell); `rerun_self_update` (a cell computing a
  name from itself with arithmetic, `x = x.astype(...) / 255`, ran more than once since the cell that made it: the
  counts between are on no cell); Run All fails on any cell's error output, on screen or not; `cell_not_run` trusts a
  `[N]` run count the editor shows above the cell over an unsaved file.
- **Metrics** (`_metric_view`, `_as_fraction`): Keras's short names (`acc`, `mse`, `mae`) read as the long ones; when
  several step cells print the metric, only the newest-run cell counts; a single-argument print of the metric
  (`print(history.history['accuracy'][-1])`) is its value; an accuracy-like metric against a 0..1 bar reads 1..100 as
  a percentage and above 100 as a count (fail).
- **Terminal** (`blocks`): a command at a continuation prompt (`dquote>`) never ran; `git config <key>` with no value
  and no output set nothing; a `--dry-run` / `git push -n` is not the step's command; a test summary with skipped
  tests is not "every test passes"; a commit row on another branch than the one the step's command makes, before it
  was made, fails; a rebasing / merging `git pull` counts where "Fast-forward" is expected; a failure from before the
  repo was set up (`git log` before the first commit, `not a git repository` before `git init`) is history once the
  setup succeeded.
- **Code** (`code_equiv`, `_file_contains`, `editor_problems`): a top-level def / class / assignment below
  `from mod import name` that rebinds it; a React component whose block body holds JSX and never returns it; a
  relative import naming the module's extension (`'../utils.ts'`) is the import without it; JSON (tsconfig) is read
  without its comments; a TypeScript / tsc step fails while VS Code's status bar counts errors (`⊗ 1`).
- **App files** (`model_files`): DXF claims (a profile the step closes whose polylines are all open; a dimension that
  should read N whose group 42 measures something else); scene claims from the step's words and file-check labels
  ("Cube at X 2", "Keys end on frame 97" for every channel, a separate object touching a part that must be one piece,
  a Hole through a short / long wall, a component the step activates and builds a body in that has none); the last
  key's interpolation reads as the key before it; Blender 4.x Principled BSDF names read as 3.x ones and back
  (`transmission_weight` / `transmission`); a timeline feature's health `warning` is not an error for an "every"
  check; G-code is an export a slicer names itself (`base_0.2mm_PLA_MK4_1h12m.gcode` for `base.gcode`).

`baseline.json`: train 1.000 with no `known_wrong`; held-out 0.439 (46 known wrong, ids only).

## Round 3: Jupyter notebooks and ML training runs (Nov 24 2026, `claude/eng-evals-r3-0`)

18 new cases (12 train, 6 held out), no engine change. Steps from the MNIST video lesson (`5c0ea8a49f419487`: s2
load, s5 fit, s6 predict, s7 evaluate) and, inline, the step shapes earlier rounds took from Adrian's catalog plans
(`origin/adrian/ui-next`, `docs/ui-next/catalog/plans/`): Intro to Jupyter ("Run order and what the kernel keeps",
"Restart and run all"), PyTorch ("Write the training loop", "Hold out data and measure accuracy", "Save and load a
model", the sine-wave project's validation loss) and the MNIST "plot the training loss" step. One new inline step:
PyTorch "Restart the kernel and load the saved model" (`pt9s3`).

The traps: a normalise cell run three times (`/ 255` again each time, its own print says max `1.53787e-05`), the
model cell re-run after training so predict ran on a fresh network (counts `[5]` model, `[4]` fit, `[6]` predict,
no restart), held-out accuracy printed as a count (`val acc 121.0` of 200), Restart + Run All whose last cell
raised `NameError: name 'plt'` below the fold. Done-but-odd: a NaN fit left in an old cell above a rebuilt model's
clean refit, `metrics=['acc']` (`acc: 0.9858`), a fit that finished on screen in a notebook not saved since it was
typed (no Cmd+S chores), `fit(..., verbose=0)` then `print(history.history['accuracy'][-1])`, an XOR loss with one
spike that recovers, a noisy sine validation loss that ends below a quarter, goal-cell re-runs that leave count gaps.

| before any fix | acc | prec | rec | FP | FN |
|---|---|---|---|---|---|
| train (171: 159 earlier + 12 new) | 0.953 | 0.948 | 0.948 | 4 | 4 |
| train, the 12 new | 0.333 | | | 4 | 4 |
| held-out (61: 55 earlier + 6 new) | 0.508 | 0.406 | 0.542 | 19 | 11 |
| held-out, the 6 new | 0.167 | | | 3 | 2 |

Train wrong verdicts (all new; the 159 earlier train cases still score right):

- **FP `jupyter-mnist-s2-normalize-cell-rerun`**: every s2 row is about code on screen or an error; a cell that
  rewrites its own input (`x = x.astype(...) / 255`) run again without the cell that loads `x` is not weighed, nor
  its printed max.
- **FP `jupyter-mnist-s6-predict-after-model-rebuilt`**: `stale_inputs` only blames cells above with a count after
  the step's cell; a cell that rebinds `model` (count `[5]`) after the cell that trained it (`[4]`) and before the
  predict (`[6]`) is not seen.
- **FP `jupyter-pytorch-val-acc-count-not-fraction`**: `metric_threshold > 0.9` takes `121.0` as an accuracy; a
  value outside 0..1 for an accuracy (a count) is never questioned.
- **FP `jupyter-restart-run-all-last-cell-error-offscreen`**: "No cell error after Run All" reads the screen only;
  the notebook's own error output in its last cell is not read.
- **FN `jupyter-mnist-s5-nan-then-rebuilt-refit`**: `_sibling_divergence` reads every output of the step's cells,
  so the old cell's `loss: nan` fails the newer cell's clean run.
- **FN `jupyter-mnist-s5-metrics-acc-alias`**: `accuracy:\s*...` refuses `acc: 0.9858`, so s5c3 waits forever.
- **FN `jupyter-mnist-s5-trained-notebook-unsaved`**: `cell_not_run` trusts the saved file (no count, no output)
  over the screen showing `[4]` and all five epochs.
- **FN `jupyter-mnist-s5-verbose0-history-printed`**: no epoch lines, so the metric waits; the printed
  `history.history['accuracy'][-1]` value is not read as the accuracy.

Seen right (train): the XOR spike (0.2203 -> 0.4917 -> 0.0061) still reads as falling; the noisy sine validation
loss passes; an empty validation split's `val nan` rows fail; count gaps from re-runs pass.

Held-out wrong verdicts among the 6 new (ids only, all in `baseline.json` → `held_out.known_wrong`):
`jupyter-mnist-loss-curve-from-nan-history`, `jupyter-mnist-s5-fit-on-test-set`,
`jupyter-pytorch-sine-val-loss-not-a-quarter` (FP); `jupyter-mnist-s7-test-acc-printed-as-fraction`,
`jupyter-pytorch-save-load-after-restart` (FN).
## Round 3: multi-file VS Code projects, Python and JS/TS/React (Nov 24 2026, `claude/eng-evals-r3-1`)

19 new cases (12 train, 7 held out), no engine change. Steps from `py-modules.json` (m2, m4, m5), `ts-shop.json`
(t2, t3, t4) and the React/Vite lesson (s1, s3), plus inline steps in the lesson builder's shape from Adrian's catalog
plans (`origin/adrian/ui-next`, `docs/ui-next/catalog/plans/`): Intro to TypeScript ("Set up tsconfig with strict
on", "Read and fix type errors" with invoice.ts importing prices.ts, "Interfaces" with an F2 rename of Animal to Pet),
Intro to VS Code ("Jump around and rename safely", as an ES module project) and React ("Split a page into
components").

Traps: an old `def add` left below `from operations import add` (the local copy shadows the import and still prints
5), `from operator import add` (the standard library, also prints 5), a Find and Replace rename that leaves
`operations.add(...)` in a module that isn't open, a `formatPrice(item.price)` only inside a JSX comment, the
checkout page's Cart.tsx edited instead of the component's, a `test.only` / `test.skip` left in the Jest file
(`2 skipped, 1 passed` / `1 skipped, 2 passed`, exit 0), a Header arrow function with a block body and no `return`,
`// "strict": true,` commented out in a `tsc --init` tsconfig, a type error left in invoice.ts while tsc still emitted
dist/invoice.js (the terminal cleared, `⊗ 1` in the status bar), a stale `import type { Animal }`, and an ESM import
without `.js` (`ERR_MODULE_NOT_FOUND`). Done-but-odd: `3 passed, 1 xfailed`, `pytest -q` for `python3 -m pytest -q`,
`'../utils.ts'` under `allowImportingTsExtensions`, `npm run preview` running after a finished build, Vitest in watch
mode, the dev server running in another terminal tab, and three components imported through a `components/index.js`.

Before any fix (the engine is the round-2 fix state):

| | acc | prec | rec | FP | FN |
|---|---|---|---|---|---|
| train (171 = 159 + 12 new) | 0.965 | 0.937 | 0.987 | 5 | 1 |
| train, the 12 new | 0.500 | | | 5 | 1 |
| held-out (62 = 55 + 7 new) | 0.516 | 0.406 | 0.542 | 19 | 11 |
| held-out, the 7 new | 0.286 | | | 3 | 2 |

Train wrong verdicts (all new; the 159 earlier train cases still score right), in `baseline.json` → `known_wrong`:

- **FP `terminal-tsshop-t4-test-only-left-in`**: `\d+\s+passed` finds `1 passed` and nothing reads
  `2 skipped` or the `test.only` in the test file: a run that skipped tests is read as the whole suite.
- **FP `vscode-pymod-m2-old-def-shadows-import`**: both code rows match; nothing notices that main.py defines `add`
  again after importing it, so the call uses the local copy.
- **FP `vscode-react-s3-header-body-never-returns`**: `import Header` and `<Header` are on screen; Header.jsx's arrow
  function has a block body with no `return`, so the component renders nothing.
- **FP `vscode-ts-invoice-type-error-left`**: dist/invoice.js exists and the total prints; the type error is gone
  from the terminal (cleared), and invoice.ts on disk (and `⊗ 1` in the status bar) is not compared with the step's
  code.
- **FP `vscode-ts-tsconfig-strict-commented-out`**: `"strict"\s*:\s*true` matches inside a `//` comment of a JSONC
  tsconfig.
- **FN `vscode-tsshop-t2-ts-extension-import`**: `'../utils.ts'` fails the `'../utils'` pattern although the
  project's tsconfig allows importing .ts extensions.

Seen right (train): `3 passed, 1 xfailed`, bare `pytest -q`, a preview server after a build, Vitest's watch mode, a
call only inside a JSX comment, a stale `import type`.

Held-out: ids of the new wrong verdicts in `baseline.json` → `held_out.known_wrong`; not listed here on purpose.
## Round 3: terminal and git workflows (Nov 24 2026, `claude/eng-evals-r3-2`)

20 new terminal cases (13 train, 7 held out), no engine change. Steps from the Git video lesson
(`8b6203eb5ec8c6f6`: s1 config, s2 init, s5 commit, s7 branch, s8 push, s9 pull, s10 delete), the coach eval's
interactive-rebase lesson (s1, s3, s4), `ts-shop.json` t4 (Jest) and `py-modules.json` m5 (pytest), and, inline,
from Adrian's catalog plans (`origin/adrian/ui-next`, `docs/ui-next/catalog/plans/`): Intro to Git and GitHub ("Set
up Git and make a repository", "Stage and commit", "Work on a branch", "Fix a merge conflict", "Connect to GitHub
with an SSH key") and Intro to the terminal ("Write a shell script", "Pipes and grep").

The traps (typed vs run, wrong order, a command that looks like the real one): `git config` keys typed without
values (read, not set), a commit left at zsh's `dquote>` prompt, `git push --dry-run`, a waffles commit made on main
before `git switch -c`, a remote delete typed but not run under a local "Deleted branch" line, a rebase whose todo
kept every `pick` (it finishes at once; the debug line stays), `git reset --hard` at an edit stop (the commit is
dropped, not split), `git switch` without -c, "Already up to date." beside a `git show --stat` diffstat, a merge
committed with `=======` left in the file, `> rain.txt | sort` (saved unsorted), curly quotes in `git commit -m`.
Done-but-odd: `git init project1` from ~, a rebasing pull (no Fast-forward, no diffstat), a `git log` fatal before
the first commit, Jest's watch menu ("Press f to run only failed tests"), PEP 668's `externally-managed-environment`
before a venv, "permission denied" before `chmod +x`, `git init -b` unknown to an older Git, `ssh -T` exiting 1 on
success.

| before any fix | acc | prec | rec | FP | FN |
|---|---|---|---|---|---|
| train (172: 159 earlier + 13 new) | 0.965 | 0.949 | 0.974 | 4 | 2 |
| train, the 13 new | 0.538 | | | 4 | 2 |
| held-out (62: 55 earlier + 7 new) | 0.516 | 0.412 | 0.583 | 20 | 10 |
| held-out, the 7 new | 0.286 | | | 4 | 1 |

Train wrong verdicts (all new; the 159 earlier train cases still score right): FP
`terminal-git-s1-config-keys-without-values`, `terminal-git-s5-commit-unclosed-quote`, `terminal-git-s8-push-dry-run`,
`terminal-gitcat-branch-commit-on-main`; FN `terminal-git-s9-pull-rebased-no-diffstat`,
`terminal-rebase-s1-log-fatal-before-first-commit`. Held-out wrong: ids in `baseline.json` → `held_out.known_wrong`;
not read while fixing.
## Round 3: Blender and CAD / AutoCAD / Fusion files (Nov 24 2026, `claude/eng-evals-r3-3`, 19 new cases, 7 held out)

From Adrian's plans on `origin/adrian/ui-next` (`docs/ui-next/catalog/plans`: `intro-blender`, `blender-materials`,
`blender-animation`, `intro-fusion`, `cad-3d-printing`, each lesson's `passes` line) and
`docs/ui-next/INTEGRATIONS.md` (headless `dump_scene.py` / `dump_fcstd.py` facts as fixtures, the STL reader), plus
the AutoCAD toy-car steps as ASCII DXF. Two shapes are new: the Fusion live add-in's design JSON
(`box.design.json`: `components` with their `bodies` and bound boxes, one `timeline` with each item's `health`,
`features` such as a Hole's diameter, centre and axis), and binary files (`{"base64": ...}`, a binary STL as Fusion
saves one by default). Blender 4.2 dumps read inputs by their 4.x names (`transmission_weight`); a scene with two
cameras lists them in `cameras` and names the render camera in `scene.camera`.

Traps: a handle that is a separate torus (the mug is one island, unjoined), the cube moved on Y instead of X, only
the Z curve retimed in the Graph Editor, an open PLINE closed by clicking the start point, a dimension that measures
102 while the body's 120 is a vertex, a Fusion lid body made in Base (Lid component empty), an 8 mm hole in a long
wall, Depth of Field on a second camera that never renders. Done-but-odd: Transmission Weight (Blender 4.x name),
the last key left Bezier (it shapes nothing), PrusaSlicer's default G-code names, a yellow Fusion warning (not an
error).

Before any fix (no engine change in this step; the runner learned `{"base64": ...}` files):

| | acc | prec | rec | FP | FN |
|---|---|---|---|---|---|
| train (171 = 159 + 12 new) | 0.936 | 0.909 | 0.946 | 7 | 4 |
| train blender (21) | 0.762 | 0.700 | 0.778 | 3 | 2 |
| train cad (17) | 0.647 | 0.429 | 0.600 | 4 | 2 |
| held-out (62 = 55 + 7 new) | 0.484 | 0.382 | 0.542 | 21 | 11 |

Train wrong verdicts (11 of the 12 new train cases; the 159 earlier train cases stay right):

- **FP `blender-handle-separate-torus-not-joined`**: the Mug is one island; the handle is a separate Torus.
- **FP `blender-transform-cube-moved-on-y`**: location (0, 2, 0); "a 2 in the location" is read, not the X axis.
- **FP `blender-dopesheet-only-z-scaled`**: Z keys end on 97, the X travel keys still end on 49.
- **FP `autocad-dxf-profile-open-polyline`**: LWPOLYLINE with group 70 = 0 passes "a closed polyline".
- **FP `autocad-dxf-length-dimension-wrong-points`**: the DIMENSION measures 102 (group 42); 120.0 is a vertex.
- **FP `fusion-lid-body-in-base-component`**: Base has two bodies, Lid none; both names and an 80 x 50 x 3 body exist.
- **FP `fusion-hole-on-long-wall`**: Hole1 is 8 mm, its axis along Y (a long wall), not X.
- **FN `blender-glass-transmission-weight-42`**: `transmission_weight: 1.0` vs a pattern on `"transmission"`.
- **FN `blender-clock-last-key-bezier`**: CONSTANT x4 then BEZIER on the last key, which shapes no segment.
- **FN `freecad-slicer-gcode-default-names`**: base_0.2mm_PLA_MK4_1h12m.gcode is the base's G-code.
- **FN `fusion-timeline-fillet-warning-done`**: "every feature rebuilds" fails on a `warning` health.

Held out: 7 new cases, 7 wrong (ids in `baseline.json` → `held_out.known_wrong`). Not listed here on purpose.

## Round 2 fixes (Nov 24 2026, `claude/eng-check-fixes-r2`)

The four round-2 case sets merged: 214 cases, 159 train + 55 held out. Every fix is general (no lesson ids, no case
text); each has a regression test in `server/checks/tests/test_round2_fixes.py`. Fixed against the train cases only;
the held-out wrong verdicts were never read (ids only) while fixing.

| | acc | prec | rec | FP | FN |
|---|---|---|---|---|---|
| train (159), before | 0.780 | 0.706 | 0.857 | 25 | 10 |
| train (159), after | 1.000 | 1.000 | 1.000 | 0 | 0 |
| held-out (55), before | 0.455 | 0.382 | 0.591 | 21 | 9 |
| held-out (55), after | 0.545 | 0.448 | 0.591 | 16 | 9 |

Held-out: 5 wrong verdicts became right (one of the 15 new round-2 ones, four from round 1), none became wrong.

What changed in `server/checks`:

- **Scene dumps as the app evaluates them** (`model_files.scene_view`): an animated channel holds its keyframe's
  value at the current frame (an unkeyed move is lost on the next frame change); a material in a slot no face uses
  is not on the object; a body's sketch that is neither its tip nor used by a feature is an abandoned try; an Edit
  mode step reads each object's mesh size (dimensions at scale 1). A second reading (`alt_views`): a primitive whose
  scale was applied (scale 1, dimensions changed) has the scale its size means; a Radius r is a Diameter 2r. The step's
  own comparison between two named things ("the Key at least twice the Fill's power") is checked on the dump
  (`claims`, a gate row "Scene matches the step"). An STL the step prints must be a closed shell (`open_mesh`).
  AutoCAD names (layer, block, style groups of a DXF) match in any case.
- **Terminal history** (`blocks.py`): "is not a git command" is a failure; AutoCAD's UNDO takes back the commands it
  names ("Everything has been undone": all of them); a match under a `git status` section other than the one the
  label names ("untracked", "staged") doesn't count once a status listing is on screen; the step's command run with
  the prompt in another folder of the lesson than its files' (and not one an earlier command made) doesn't count; a
  test run that selects some tests (`::name`, `-k`, `--lf`, jest `-t`) is not the suite; a home-folder label wants
  the prompt user's folder; an every / each / per label holds for every row of the pattern's shape; a command the
  step names that failed last and never ran again (`git commit` -> "no changes added to commit") fails the step;
  text the learner quoted in a command (a commit message) matches in any case.
- **Notebooks**: a Markdown pattern (`"# `, `"## `, `"- `) on a Markdown step reads Markdown cells only, and a
  "headings" label counts any level below the title; an exported notebook's HTML is read without its code inputs
  unless the label is about code; a Keras fit whose last `Epoch k/N` has k < N is unfinished (pending; fail after an
  error or a kernel crash); "The Kernel crashed" on screen fails a notebook step; a cell run after a restart without a
  cell above it that sets up what it reads (the counts before its own all on cells above) fails ("The kernel has what
  the cell needs"); a step whose code spans cells needs all of them run; a metric printed as bare `step value` rows
  by the step's own `print(epoch, loss.item())` is read; a matrix drawn as a figure (`ConfusionMatrixDisplay`) reads
  as numpy's printout from its OCR rows.
- **Code across files** (`code_equiv.py`): a Python name used but never imported, defined in another lesson module,
  fails "Imports resolve"; CommonJS `const { x } = require('./m')` is checked against `module.exports`; a relative
  import of a file that doesn't exist fails; `const f = (a) =>` / `function` expressions read as `function f(a)`;
  an import through a tsconfig `paths` alias reads as the relative import it means; a label naming a file that isn't
  open on screen is read from that file on disk; a JSON config key the step's code puts in a section
  (`compilerOptions.strict`) fails when it sits elsewhere.

Held-out wrong after the fixes (25): ids in `baseline.json` → `held_out.known_wrong`; not read.

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

## Round 2: multi-file VS Code projects, Python and JS/TS/React (Nov 24 2026, `claude/eng-evals-r2-1`)

20 new cases (13 train, 7 held out), no engine change: imports across files, renamed symbols, tests passing, build
output and dev servers. Steps from `py-modules.json` (m2, m4, m5), `ts-shop.json` (t2, t3, t4), the React/Vite
lesson (s1, s3, s6), and two inline steps written from Adrian's catalog plans in the lesson builder's shape: Intro
to VS Code "Jump around and rename safely" (scaleRecipe defined in recipe-utils.js, called from scale.js, CommonJS)
and Intro to TypeScript "Set up tsconfig with strict on" (strict true, `npx tsc` writes dist/index.js).

Traps: a name called but not imported (a wrapper added instead of a rename), a `require` that still destructures the
old name, a named import of a default-only export, a component imported from where it isn't (`./Header` vs
`src/components/`), `"strict": true` outside `compilerOptions` (tsc ignores it), `npx vite build` run by hand to get
past a tsc error, a Vite server from another project, a Jest suite that failed to compile under an all-green
`Tests:` line, a pytest collection error under an older green run. Done-but-odd: a parenthesised multi-line import,
a path alias (`@/utils`), a utils folder with an `index.ts`, an arrow-function definition, a rename finished in a
file that isn't on screen, `Error` inside a passing test's name, `error` as a chunk file name, tsc's silent success
after an earlier error.

| | acc | prec | rec | FP | FN |
|---|---|---|---|---|---|
| train (121 = 108 + 13 new), before any fix | 0.934 | 0.914 | 0.946 | 5 | 3 |
| train, the 13 new cases | 0.385 | 0.000 | 0.500 | 5 | 3 |
| held-out (34 = 27 + 7 new) | 0.529 | 0.409 | 0.750 | 13 | 3 |

Train wrong verdicts (in `baseline.json` → `known_wrong`), worst first:

- **FP `terminal-react-s1-other-project-server`**: `ready in` / `localhost:` from a Vite server started in another
  project (`~/shop`, `> shop@0.0.0 dev`); the lesson's project folder was never created.
- **FP `vscode-pymod-m4-wrapper-not-imported`**: main.py calls `add_numbers` but imports only `add` (NameError on
  screen); `_broken_imports` checks that imported names exist, not that called names are imported.
- **FP `vscode-react-s3-header-in-components-unresolved`**: `import Header from './Header'` with the file in
  `src/components/`; the unresolved path (and Vite's "Failed to resolve import" in the terminal) isn't weighed.
- **FP `vscode-recipe-rename-require-stale`**: `const { scale } = require('./recipe-utils')` after the export became
  `scaleRecipe`; CommonJS `require` destructuring isn't read as an import.
- **FP `vscode-ts-tsconfig-strict-outside-compileroptions`**: the `"strict": true` regex matches a top-level key
  tsc ignores.
- **FN `vscode-pymod-m4-main-off-screen`**: F2 renamed every file on disk; `main.py calls add_numbers(2, 3)` is
  graded on the screen (only operations.py open), not on main.py.
- **FN `vscode-recipe-rename-arrow-fn`**: `const scaleRecipe = (recipe, factor) =>` fails `function\s+scaleRecipe`.
- **FN `vscode-tsshop-t2-path-alias`**: `from '@/utils'` (a tsconfig / Vite alias for src/) fails the `'../utils'`
  pattern.

Held-out wrong verdicts: ids in `baseline.json` → `held_out.known_wrong` (one new); not read while fixing.

## Round 2: terminal and git (Nov 24 2026, `claude/eng-evals-r2-2`, 20 new cases, 7 held out)

Added after the round 1 fixes. These cases cover what round 1 did not: the Git lesson's s1 (config), s9 (pull + show) and s10
(delete branches), `git add .` staging a file the step keeps untracked, a commit stopped by "Author identity
unknown", a clone nested inside project1 (the lesson's own common mistake), a push of a branch whose commit
never happened, a pull that failed on divergent branches, pytest run on one selected test, pip dropping
tensorflow, a Jupyter server shut down after it started, and two inline steps in the form of Adrian's
`intro-terminal` plan ("Find where you are": the *last* pwd is /Users/Shared; "Read files": wc -l shows 2
for one note). Done-but-odd: `git config set` / `git config list` (git 2.46+), `gh repo clone`, a
capitalised commit message, `git switch -c` on an existing branch and then `git switch`, a remote branch
GitHub already deleted, `git branch -D` after a squash merge, pip "already satisfied" with Jupyter on port 8889,
npm warnings and audit notices before Vite's ready line, and `cd ~ && pwd`.

Before any fix (the engine is the round 1 fix state). Train is 121 cases (108 + 13 new) and held-out is 34 (27 + 7 new):

| | acc | prec | rec | FP | FN |
|---|---|---|---|---|---|
| train (121) | 0.934 | 0.885 | 0.982 | 7 | 1 |
| train terminal (46) | 0.826 | 0.731 | 0.950 | 7 | 1 |
| train, new terminal cases only (13) | 0.385 | | | 7 | 1 |
| held-out (34) | 0.471 | 0.391 | 0.692 | 14 | 4 |
| held-out, new terminal cases only (7) | 0.571 | | | 2 | 1 |

Wrong train verdicts, worst first. `baseline.json` → `known_wrong` lists them so the pytest guard stays green until a fix:

- **FP `terminal-git-s1-alias-typo-not-a-command`**: `alias.i` matches only in `git confg ... alias.i init`, the
  command line git refused ("is not a git command"). The `git config --list` that follows has no `alias.i`.
- **FP `terminal-git-s3-add-dot-staged-waiting`**: `waiting.py` matches under "Changes to be committed". The check
  wants it under "Untracked files".
- **FP `terminal-git-s6-cloned-inside-project1`**: the clone ran with the prompt in project1. Both patterns match.
- **FP `terminal-git-s8-pushed-without-committing`**: "no changes added to commit", then `* [new branch]
  update-name -> update-name`. The push succeeded, but the edited heading was never committed.
- **FP `terminal-pymod-m5-ran-one-test-only`**: `pytest test_operations.py::test_add` printed "1 passed" with exit 0.
  A test that is never selected can't fail.
- **FP `terminal-shell-pwd-last-is-users-shared`**: `^/Users/[^/\s]+$` matches the last pwd's `/Users/Shared`
  (and the first pwd's home folder).
- **FP `terminal-shell-wc-one-note-two-lines`**: one `3 notes/day1.txt` row is enough. The `2 notes/summit.txt`
  row is never weighed.
- **FN `terminal-git-s5-commit-capitalised-message`**: "Add waiting file" vs the pattern `add\s+waiting\s+file`.

Held-out: new wrong verdicts are in `baseline.json` → `held_out.known_wrong` (ids only, not read when fixing).

## Round 2: Blender and CAD file checks (Nov 24 2026, `claude/eng-evals-r2-3`, 20 new cases, 7 held out)

From Adrian's plans on `origin/adrian/ui-next` (`docs/ui-next/catalog/plans`: `intro-blender`, `blender-materials`,
`blender-animation`, `intro-cad`, `cad-3d-printing`, `intro-fusion`, each lesson's `passes` line) and
`docs/ui-next/INTEGRATIONS.md` (file level: headless `dump_scene.py` / `dump_fcstd.py` facts recorded as fixtures,
the STL reader, AutoCAD's DXF), plus the donut and toy-car app-lesson fixtures at screen level. The dumps keep the
round-1 shape; two fields are new and read by name: an object's `material_slots` (material, face count) and
`animation` (an action's fcurves: data path, index, `[frame, value]` keyframes, interpolation), and the scene's
`fps_base` / `frame_current` / FFmpeg output.

Traps: the right numbers on the wrong sketch or body (an abandoned fully constrained sketch beside the 60 x 40 one
that still slides; a 30 mm pad in a new Body, not joined), a material in a slot with no faces, light names right but
the power ratio wrong, a key inserted before the move (the unkeyed location is saved), 23.98 fps stored as fps 24 +
fps_base 1.001, a box stretched in Object mode read as a raised edge, a pattern that fails to recompute, an open
STL with facets, the whole design in one STL, an UNDO > Back after LINE, a menu-search popup. Done-but-odd: scale
applied (dimensions halved, scale 1), the mug never renamed from Cylinder, holes sized by Radius, a layer typed
`Wheels`, fillets split over two features, an MP4 with Blender's frame-range name, EXPORT > Lithography for STLOUT.

Before any fix (no engine change in this step):

| | acc | prec | rec | FP | FN |
|---|---|---|---|---|---|
| train (121 = 108 + 13 new) | 0.917 | 0.881 | 0.945 | 7 | 3 |
| train blender (15) | 0.667 | 0.600 | 0.857 | 4 | 1 |
| train cad (11) | 0.545 | 0.250 | 0.333 | 3 | 2 |
| held-out (34 = 27 + 7 new) | 0.412 | 0.286 | 0.545 | 15 | 5 |

Train wrong verdicts (all 10 are new cases; the 108 earlier train cases stay right):

- **FP `blender-material-glossy-in-empty-slot`**: the glossy material is on the mug, in a slot with 0 faces.
- **FP `blender-lights-key-not-twice-fill`**: Key 400 W, Fill 300 W; the names and types are all that is read.
- **FP `blender-anim-second-key-before-move`**: both keys hold X 0; the saved location X 5 is an unkeyed edit.
- **FP `blender-edit-wedge-cube-scaled-z`**: S Z 1.5 in Object mode gives the wedge's 2 x 2 x 3 and 8 vertices.
- **FP `freecad-sketch-60x40-in-second-sketch`**: `"dof": 0` from the abandoned sketch, 60 / 40 from the other.
- **FP `freecad-hook-stl-open-faces-only`**: an STL with 10 facets and an open top passes "watertight".
- **FP `autocad-toy-car-s1-profile-undone`**: LINE in the history, then UNDO > Back, "Everything has been undone".
- **FN `blender-transform-sphere-scale-applied`**: scale applied, so `[0.5, 0.5, 0.5]` is gone; dimensions are 1 m.
- **FN `freecad-clearance-holes-by-radius`**: Radius 5.1 / 5.2 are the 10.2 / 10.4 mm holes.
- **FN `autocad-dxf-wheels-layer-mixed-case`**: AutoCAD layer names ignore case; the DXF says `Wheels`.

Held out: 7 new cases, 5 wrong (ids in `baseline.json` → `held_out.known_wrong`). Not listed here on purpose.

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

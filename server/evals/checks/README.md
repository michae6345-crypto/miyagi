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
python -m server.evals.checks --show-held-out    # also the held-out wrong verdicts' rows (read, never tune on)
python -m server.evals.checks --write-baseline   # after the checks improve or cases are added
python -m pytest server/evals/checks -q  # fails below baseline.json or on a new wrong verdict
```

`pass` is the positive class. **Precision** = of the steps the checks passed, the share that were really done
(a miss here is a *false pass*: the learner moves on with broken work, the worse error). **Recall** = of the steps
that were done, the share the checks passed (a miss is a *false not-yet*: the learner gets stuck on finished work).
`fpr` = false passes / steps not done.

## Case format

```jsonc
{
  "id": "jupyter-mnist-s2-typed-not-run",   // = file name
  "kind": "jupyter",                        // jupyter | vscode | terminal | metric
  "trap": "false_pass",                     // none | false_pass (a near miss that looks done) | false_fail (done, but looks odd)
  "heldOut": true,                          // optional: a held-out case (see below); default false = train
  "expected": "not_yet",                    // pass | not_yet
  "why": "T10-CP7: the cell is typed but never run ...",
  "precision_mode": false,                  // optional: evaluate_gate(precision_mode=...)
  "step": {"lesson": "demo/cache/lessons/5c0ea8a49f419487.json", "id": "s2"},  // or an inline step with "checks"
                                            // optional "patch": {...}, "drop_checks": [ids]
  "workspace": {
    "files": {
      "calculator.py": "def add(a, b): ...",          // a text file
      "project1/.git": {"dir": true},                 // a folder
      "mnist.ipynb": {"notebook": {"from": "server/tests/fixtures/t10_mnist.ipynb", "keep_cells": 1,
                                   "unrun": [0], "replace": [[0, "old", "new"]], "append": [cell]}},
      "Untitled.ipynb": {"notebook": {"cells": [{"source": "...", "stdout": "...", "error": "NameError: ...",
                                                 "image": true, "run": false}],
                                      "kernel": ".venv (3.12.16)", "kernel_version": "3.12.16"}}
    },
    "screen": {"Code": ["line", ...], "Terminal": [...]},   // or a ScreenObservation {windows, blocks}; null = no frame
    "run": {"command": "python3 calculator.py", "exit_code": 0, "output_tail": ["5"], "running": false},
    "metrics": {"loss": [[0, 1.2], [100, 1.08]]},          // "nan" for NaN
    "segment_done": true, "editor": "Code"
  }
}
```

Lessons used: the MNIST Jupyter video lesson (`5c0ea8a49f419487`, with the learner's real notebook from desktop
test 10), the calculator and NN-from-scratch text lessons, the Git, React/Vite and convection-PINN video lessons,
and the coach eval's git interactive-rebase lesson (`evals/coach/lessons/git-interactive-rebase.json`).

## Train and held-out

About a third of each new round's cases carry `"heldOut": true`. They are scored and reported on their own (the
`held-out` line; `summary()["held_out"]`, `baseline.json` → `held_out` / `known_wrong_held_out`), never mixed into
the train numbers, and they are **never used to tune a fix**: fixes are made against train cases only, and the
held-out score says whether a fix generalises. The report lists a held-out wrong verdict by id only;
`--show-held-out` prints its rows, for reading after a fix round, not for picking the next fix. The pytest gate
still fails when a held-out case newly goes wrong (a regression guard, not a tuning target). Every held-out case's
trap kind also has train cases.

## Baseline (76 cases: 69 train + 7 held out, Nov 24 2026, origin/integration/live)

Round 1 of the accuracy loop added 20 terminal / git cases (13 train, 7 held out): commands typed vs run, a
command's own echo vs its result (errors after `git add`, `git commit`, `git clone`, `git push`), branches created
vs switched, multi-step shells (`cd x; git init`), package installs (pip resolver notice, venv not activated,
npm 10's `npm error`), exit codes on a hidden terminal.

| | acc | prec | rec | FP | FN |
|---|---|---|---|---|---|
| train (69) | 0.855 | 0.811 | 0.909 | 7 | 3 |
| train terminal (29) | 0.655 | 0.588 | 0.769 | 7 | 3 |
| held out (7) | 0.143 | 0.167 | 0.500 | 5 | 1 |

Known wrong train verdicts (`known_wrong`), worst first:

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

Held-out wrong verdicts (`known_wrong_held_out`), ids only: `terminal-calc-s2-hidden-exit-1-after-5`,
`terminal-git-s7-fish-typed-not-run`, `terminal-git-s7-pathspec-error`, `terminal-mnist-s1-forgot-activate`,
`terminal-react-s1-npm10-error` (FP); `terminal-git-s8-push-ligature-arrow` (FN).

## First baseline (56 cases, Nov 22 2026; all eight fixed in 2b86a0db)

| | acc | prec | rec | FP | FN |
|---|---|---|---|---|---|
| overall | 0.857 | 0.833 | 0.893 | 5 | 3 |
| jupyter (19) | 1.000 | 1.000 | 1.000 | 0 | 0 |
| terminal (16) | 0.875 | 0.800 | 1.000 | 2 | 0 |
| vscode (12) | 0.750 | 0.714 | 0.833 | 2 | 1 |
| metric (9) | 0.667 | 0.750 | 0.600 | 1 | 2 |

Known wrong verdicts (`baseline.json` → `known_wrong`), worst first:

- **FP `metric-nn4-diverged-nan`**: the NN lesson's `metric_pattern` value class `[0-9Oo.eE+-]+` can't read `nan`,
  so `epoch 13000 loss nan` is skipped and the stale 0.0032 passes "Loss falls below 0.01". The divergence guard
  never sees the NaN.
- **FP `terminal-calc-s2-hidden-other-script`**: with the terminal hidden, a Terminal `screen_contains` is graded on
  the last run's output (`_on_run_output`) without checking the run was the step's command; `python3 scratch.py`
  printing 5 passes "The program prints 5".
- **FP `terminal-git-s7-typed-not-run`**: `update-name` matches the command typed at the prompt, before Enter.
  Any Terminal check whose pattern is a word of the command itself passes on the typed line.
- **FP `vscode-calc-s1-commented-out`**: code checks match commented-out lines (`# def add(a, b):`).
- **FP `vscode-calc-s4-guard-in-wrong-function`**: regex checks can't see where the code is; the zero guard in
  `multiply()` passes "divide() raises a ValueError".
- **FN `metric-pinn-s4-prints-l2-error`**: the generated `screen_absent` pattern `Traceback|Error` fails on a
  result line, `Relative L2 Error: 3.1e-02`.
- **FN `metric-pinn-s7-decreasing`**: the lesson's `metric_trend` has `window: 5` (steps) with loss logged every 100
  steps, so the window never holds 8 points: it can never pass. (`metric-pinn-s7-flat` is a TN for the same wrong
  reason.)
- **FN `vscode-calc-s1-other-param-names`**: `def add(x, y): return x + y` fails patterns that hard-code `a, b`.

Not verdict errors, but seen in the rows: a finished notebook cell below a metric bar
(`jupyter-mnist-s5-low-accuracy`, `-s7-below-95`) stays `pending`, never `fail`, so stuck-help can't fire; and
details name the video's `Untitled.ipynb` where the learner's notebook is `mnist.ipynb`.

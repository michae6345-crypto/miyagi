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
python -m server.evals.checks --write-baseline   # after the checks improve or cases are added
python -m pytest server/evals/checks -q  # fails below baseline.json or on a new wrong verdict
```

`pass` is the positive class. **Precision** = of the steps the checks passed, the share that were really done
(a miss here is a *false pass*: the learner moves on with broken work, the worse error). **Recall** = of the steps
that were done, the share the checks passed (a miss is a *false not-yet*: the learner gets stuck on finished work).
`fpr` = false passes / steps not done.

**Held-out cases** (`"heldOut": true`, about a third of each new round) are scored and reported on their own and
never gate anything: `baseline.json`'s scores and `known_wrong`, the pytest gate and the detailed wrong-verdict list
are the training cases only. A held-out wrong verdict is printed by id and label, without its check rows. Never tune
a fix to a held-out case (don't read its rows, don't add a rule for its shape): they measure whether a fix made on
the training cases generalises. `baseline.json` → `held_out` records their scores for comparison only.

## Case format

```jsonc
{
  "id": "jupyter-mnist-s2-typed-not-run",   // = file name
  "kind": "jupyter",                        // jupyter | vscode | terminal | metric
  "trap": "false_pass",                     // none | false_pass (a near miss that looks done) | false_fail (done, but looks odd)
  "expected": "not_yet",                    // pass | not_yet
  "why": "T10-CP7: the cell is typed but never run ...",
  "precision_mode": false,                  // optional: evaluate_gate(precision_mode=...)
  "heldOut": false,                         // optional: true = held out (scored separately, never tunes a fix)
  "step": {"lesson": "demo/cache/lessons/5c0ea8a49f419487.json", "id": "s2"},  // or an inline step with "checks"
                                            // optional "patch": {...}, "drop_checks": [ids]
  "workspace": {
    "files": {
      "calculator.py": "def add(a, b): ...",          // a text file
      "project1/.git": {"dir": true},                 // a folder
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
test 10), the calculator and NN-from-scratch text lessons, the Git, React/Vite and convection-PINN video lessons.
Inline steps follow lessons in Adrian's catalog plans (`docs/ui-next/catalog/plans`, commit 213c9238): Intro to
Jupyter ("Run order and what the kernel keeps", "Install a package and draw a chart", "Restart and run all") and
PyTorch ("Write the training loop"), written in the shape the lesson builder gives the MNIST lesson.

## Round 1: Jupyter notebooks and ML training runs (Nov 24 2026)

20 new cases (13 training, 7 held out): NaN / inf divergence, a recovered loss spike, a run still mid-epoch, cell
run order (evaluate before fit, an edited cell not re-run, counts out of order), kernel restarts (Run All from [1],
only one cell re-run), plots (an imshow error after the prints, a figure saved but not shown), the lesson's own
common mistakes (wrong loss, `probabilities` not indexed, evaluating on the training set) and done-but-odd work
(compile and fit in two cells, a separate Softmax layer, a loss printed as a tensor).

Training cases wrong at the start of the round (`known_wrong`):

- **FP `jupyter-mnist-s5-nan-loss-high-acc`**: the metric is `accuracy`; the same Keras line's `loss: nan` is never
  read, so an epoch-averaged 0.9563 passes a run whose weights went NaN.
- **FP `jupyter-restart-run-all-out-of-order`**: a `[1]` on screen and no error pass "Restart and run all" while the
  counts read [1], [5], [4]; nothing reads the notebook's execution order.
- **FN `jupyter-pytorch-xor-loss-printed-as-tensor`**: `loss tensor(0.2614, grad_fn=...)` doesn't fit the value
  class, so the loss trend waits forever on a finished run.

Held out: 7 cases, 4 wrong (ids in `baseline.json` → `held_out`). Seen, not a verdict error: a notebook cell that
raised before printing any metric (`jupyter-mnist-s5-categorical-crossentropy-error`) leaves the metric row
`pending`, never `fail`, so stuck-help can't fire.

## First baseline (56 cases, Nov 22 2026, origin/integration/live; all fixed by Nov 24, see baseline.json)

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

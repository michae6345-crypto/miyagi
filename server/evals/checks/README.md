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
python -m server.evals.checks --held-out # also the held-out cases' wrong verdicts (to judge a fix, never to tune one)
python -m server.evals.checks --write-baseline   # after the checks improve or cases are added
python -m pytest server/evals/checks -q  # fails below baseline.json or on a new wrong verdict (training cases)
```

**Held-out cases** (`"heldOut": true`, about a third of each new batch) are scored and reported apart and are
never used to tune the checks. The default report, `-v`, `baseline.json`'s `known_wrong` and the pytest gate cover
the training cases only; held-out cases show as one `held-out` score line. Their wrong verdicts are listed only with
`--held-out`, which is for whoever judges a fix after it is made. A fix that is right for the training cases and
general should move the held-out score too; one that doesn't was fitted to the cases.

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
  "expected": "not_yet",                    // pass | not_yet
  "why": "T10-CP7: the cell is typed but never run ...",
  "heldOut": false,                         // optional: true = scored apart, never used to tune the checks
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
test 10), the calculator and NN-from-scratch text lessons, the Git, React/Vite and convection-PINN video lessons.

### Blender and CAD cases (`kind: blender | cad`, Nov 24)

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

## Baseline (69 training + 7 held-out cases, Nov 24 2026, origin/integration/live)

The 56 cases before Nov 24 all score right (their Nov 22 wrong verdicts were fixed). The new Blender and CAD
training cases (13) score:

| training | acc | prec | rec | FP | FN |
|---|---|---|---|---|---|
| overall (69) | 0.855 | 0.795 | 0.939 | 8 | 2 |
| blender (8) | 0.250 | 0.333 | 0.500 | 4 | 2 |
| cad (5) | 0.200 | 0.200 | 1.000 | 4 | 0 |
| jupyter, metric, terminal, vscode (56) | 1.000 | 1.000 | 1.000 | 0 | 0 |

Held-out (7): acc 0.000 (4 FP, 3 FN). Not listed here on purpose (`--held-out`).

Known wrong verdicts in the training cases (`baseline.json` → `known_wrong`), worst first:

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

Not verdict errors, but seen in the rows (Nov 22): a finished notebook cell below a metric bar
(`jupyter-mnist-s5-low-accuracy`, `-s7-below-95`) stays `pending`, never `fail`, so stuck-help can't fire.

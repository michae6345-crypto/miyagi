# pinn-lab: the learner's workspace for the hero lesson

Toscano, "Learning Physics Informed Machine Learning Part 1 - PINNs" (YouTube `AXXnSzmpyoI`): a PINN for the 1D diffusion equation.
`pinn_diffusion.py` follows the video's sections (1. libraries … 8. results), each one a TODO. Nothing the lesson's checks look
for is in it yet (verified against E2's Toscano lessons). `report(i, loss, test_loss)` is given: it prints `step N | loss X | test Y`
for the screen reader and `::metric::` lines for `tut run`. E2's cached lesson (`demo/cache/lessons/aebc6b8fba02dac5.json`) is
fingerprinted on this folder's file NAMES (README.md + pinn_diffusion.py), so don't add or rename files here without telling E2.

`scripts/miyagi-engine.sh` opens this folder in VS Code when the lesson starts and jumps to each step's target.

## Hero failure: `lr = 0.3` (real, measured, and the coach finds it on its own)

Measured on this Mac's CPU with the lesson's training step (Adam, check "loss < 1e-2 by step 2000", median of the last 5 points):

| learning rate | seeds | result |
|---|---|---|
| **0.3** or 1.0 | 3 + 3 | loss diverges and sits **flat at ~17** → check **fails 6/6** ✅ reliable hero |
| 1e-1 | 3 | bounces 1e-3…1e-1 and dips under 1e-2 → check **passes 3/3** ❌ not a reliable failure |
| **1e-3** (the video's value) | 3 | under 1e-2 by step **836–1078** (~15 s) → **passes 3/3** ✅ the fix |

End to end with the real checks and the live coach (E5): a run at `lr = 0.3` goes amber, and at the run's end the coach card says
"Learning rate 0.3 is far too high: Adam's updates overshoot, so the tanh units saturate and loss sticks near 17 … Set lr to 1e-3".
Changing it to `1e-3` and re-running turns the step green and the video resumes. If the learner re-runs at 0.3, or stays stuck,
the next card adds the exact fix and a "Do it for me" button.

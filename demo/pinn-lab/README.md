# pinn-lab: the learner's workspace for the hero lesson

Hero video: SimCom, "S5 Solving Linear convection equation using PINNs" (YouTube `unBU1PwCnvQ`), du/dt + c·du/dx = 0.
`pinn_convection.py` is a starter: the network, collocation sampling and PDE residual are TODOs (the lesson's checks look for them);
the IC/BC losses, training loop and logging (`epoch N | beta B | loss X` + `::metric::` lines) are given.
`scripts/miyagi-engine.sh` opens this folder in VS Code when the lesson starts and jumps to each step's target.

## Measured on a laptop CPU (Apple Silicon, torch 2.x, 4×50 tanh MLP, Adam, 1000 resampled points/step)

Real runs of this file with the TODOs filled in; relative L2 error vs the exact sin(x − βt).

| setup | epochs | time | final loss | rel. L2 error |
|---|---|---|---|---|
| β = 1, lr 1e-3 | 3000–4000 | ~20 s | 1e-4 | **1.1 %** ✅ |
| β = 10, lr 1e-3 | 4000 | ~24 s | 4e-4 | **1.2 %** ✅ |
| β = 20, lr 1e-3 | 6000 | ~40 s | 2e-4 | **1.9 %** ✅ |
| β = 30, lr 1e-3 | 4000 / 8000 | 24 / 60 s | 4e-2 / 2e-2 | **80 % / 64 %** ❌ (the known failure mode) |
| β = 30 via curriculum 1→5→10→20→30 (or 7 stages, persistent Adam, fixed points, + LBFGS) | 4000–10500 | 24–70 s | 4e-2 – 1e-1 | **82–96 %** ❌ |
| β = 20 via curriculum 1→10→20 | 6000 | ~40 s | 1e-1 | **93 %** ❌ (worse than training directly) |
| **lr 1e-1** (β = 1 or 10) | 3000–4000 | ~20 s | **0.500, flat** | **100 %** ❌ |

**Takeaways:** the β = 30 failure is real, but a β curriculum does **not** fix it in a ~1-minute CPU budget (in this setup it makes things
worse), so "β = 30 → curriculum → green" can't be shown truthfully live. A too-high learning rate is a real, common mistake whose fix
turns green in ~20 s: the loss sits flat at exactly 0.500, and the coach diagnoses it from the code and the curve (verified end to end with the live
coach on the diffusion lesson: "Learning rate 1e-1 is too high").

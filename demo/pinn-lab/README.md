# pinn-lab: the learner's workspace for the hero lesson

Toscano, "Learning Physics Informed Machine Learning Part 1 - PINNs" (YouTube `AXXnSzmpyoI`): a PINN for the 1D diffusion equation.
`pinn_diffusion.py` follows the video's sections (1. libraries … 8. results), with every section a TODO. Nothing the lesson's checks look
for is in it yet (verified against the 56 contains-checks of E2's Toscano lessons). `report(i, loss, test_loss)` is given: it prints
`step N | loss X | test Y` for the screen reader and `::metric::` lines for `tut run`.

`scripts/miyagi-engine.sh` opens this folder in VS Code when the lesson starts and jumps to each step's target.

**Hero failure (real, not scripted):** training with Adam at `lr = 1e-1` makes the loss bounce or blow up (it never drops below 1e-2 by
step 2000; some seeds get stuck flat at ~17.4). The "loss < 1e-2" check fails, and the live coach reads the code and the curve and says the
learning rate is too high. With `lr = 1e-3` (the video's value) the loss is below 1e-2 by step ~1000 (~15 s on a laptop CPU), the step
goes green and the video resumes. Verified end to end with the real checks and the live coach.

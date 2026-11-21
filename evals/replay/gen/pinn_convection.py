"""Generator for evals/replay/cases/pinn-convection.json (synthetic run output in the script's own format)."""
import json
import math
import sys
from pathlib import Path

out_path = sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).resolve().parents[1] / "cases" / "pinn-convection.json")
F = "pinn_convection.py"


def run(beta, epochs, scale=1.0, stop_at=None):
    lines = []
    for ep in range(0, epochs, 100):
        if stop_at is not None and ep > stop_at:
            lines += ["^CTraceback (most recent call last):", '  File "/Users/me/pinn-lab/pinn_convection.py", line 62, in <module>',
                      "    main()", '  File "/Users/me/pinn-lab/pinn_convection.py", line 54, in main', "    loss.backward()", "KeyboardInterrupt"]
            return lines
        wiggle = 1 + 0.03 * math.sin(ep / 70)
        loss = scale * (0.9 * math.exp(-ep / 60) + 0.002 * math.exp(-ep / 1500) * wiggle)
        lines.append(f"epoch {ep} | beta {beta} | loss {loss:.4e}")
        lines.append(f'::metric:: {{"step": {ep}, "name": "loss", "value": {loss:.6g}}}')
    return lines


HEAD = '''"""PINN for the 1D linear convection equation u_t + beta * u_x = 0, x in [0, 2 pi], t in [0, 1], u(x, 0) = sin(x)."""
import argparse
import math

import torch
import torch.nn as nn


def log_metric(step, name, value):
    print(f'::metric:: {{"step": {step}, "name": "{name}", "value": {value}}}', flush=True)


class PINN(nn.Module):
    def __init__(self, hidden=50, depth=4):
        super().__init__()
        layers = [nn.Linear(2, hidden), nn.Tanh()]
        for _ in range(depth - 1):
            layers += [nn.Linear(hidden, hidden), nn.Tanh()]
        layers.append(nn.Linear(hidden, 1))
        self.net = nn.Sequential(*layers)

    def forward(self, x, t):
        return self.net(torch.cat([x, t], dim=1))
'''

RESIDUAL = '''

def pde_residual(model, x, t, beta):
    u = model(x, t)
    du_dt = torch.autograd.grad(u, t, torch.ones_like(u), create_graph=True)[0]
    du_dx = torch.autograd.grad(u, x, torch.ones_like(u), create_graph=True)[0]
    return du_dt + beta * du_dx
'''

LOOP = '''

def sample_points(n):
    x = (torch.rand(n, 1) * 2 * math.pi).requires_grad_(True)
    t = torch.rand(n, 1).requires_grad_(True)
    return x, t


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--beta", type=float, default=1.0)
    p.add_argument("--epochs", type=int, default=4000)
    args = p.parse_args()
    torch.manual_seed(0)
    model = PINN()
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    x0 = torch.rand(256, 1) * 2 * math.pi
    t0 = torch.zeros_like(x0)
    u0 = torch.sin(x0)
    for epoch in range(args.epochs):
        x, t = sample_points(1000)
        loss = pde_residual(model, x, t, args.beta).pow(2).mean() + (model(x0, t0) - u0).pow(2).mean()
        opt.zero_grad()
        loss.backward()
        opt.step()
        if epoch % 100 == 0:
            print(f"epoch {epoch} | beta {args.beta} | loss {loss.item():.4e}", flush=True)
            log_metric(epoch, "loss", loss.item())


if __name__ == "__main__":
    main()
'''

case = {
    "id": "pinn-convection",
    "topic": "physics-ml",
    "stack": "PyTorch (VS Code + its terminal)",
    "tutorial": {"kind": "video", "video_id": "unBU1PwCnvQ", "url": "https://www.youtube.com/watch?v=unBU1PwCnvQ",
                 "goal": "train a PINN on the convection equation"},
    "lesson": "demo/cache/lessons/8032bf0cabe0e287.json",
    "learner": {
        "folder": "pinn-lab",
        "notes": "Writes pinn_convection.py from an empty folder (demo/pinn-lab no longer has it). Training output is in that script's own print + ::metric:: format; the loss values are synthetic, not recorded."
    },
    "outline": [
        {"step": "s1", "about": "a PINN class: linear layers with Tanh", "match": "PINN|network",
         "expect_checks": [{"type": "file_contains", "file": F, "pattern": "self\\.net = nn\\.Sequential\\(\\*layers\\)"}],
         "actions": [{"do": "write", "file": F, "text": HEAD}]},
        {"step": "s2", "about": "pde_residual with autograd du/dt and du/dx", "match": "residual|physics loss",
         "expect_checks": [{"type": "file_contains", "file": F, "pattern": "return du_dt \\+ beta \\* du_dx"}],
         "actions": [{"do": "append", "file": F, "text": RESIDUAL.lstrip("\n")}]},
        {"step": "s3", "about": "sample_points with requires_grad, and the training loop", "match": "sample|training loop",
         "expect_checks": [{"type": "file_contains", "file": F, "pattern": "\\.requires_grad_\\(True\\)"},
                           {"type": "command_exit_ok", "command": "python3 pinn_convection.py --epochs 10"}],
         "actions": [{"do": "append", "file": F, "text": LOOP.lstrip("\n")},
                     {"do": "run", "cmd": "python3 pinn_convection.py --epochs 10", "output": run(1.0, 10)}]},
        {"step": "s4", "about": "train with beta = 1 and see the loss drop below 0.1", "match": "run training|beta=1",
         "expect_checks": [{"type": "metric_threshold", "metric": "loss", "op": "<", "value": 0.01, "by_step": 3900}],
         "actions": [{"do": "run", "cmd": "python pinn_convection.py", "output": run(1.0, 4000)}]},
        {"step": "s5", "about": "train with beta = -1", "match": "negative|beta -1",
         "expect_checks": [{"type": "screen_contains", "app": "Terminal", "pattern": "beta -1\\.0"}],
         "actions": [
             {"do": "mistake", "note": "drops the minus sign and reruns beta 1.0", "caught": False, "caught_by_spec_rows": ["x0"],
              "finding": "s5's precision rows can't tell which beta ran (command_exit_ok drops the flags, the loss threshold is the same), so rerunning beta 1.0 passes in precision mode",
              "actions": [{"do": "run", "cmd": "python pinn_convection.py --beta 1.0 --epochs 500", "output": run(1.0, 500)}]},
             {"do": "run", "cmd": "python pinn_convection.py --beta -1.0 --epochs 500", "output": run(-1.0, 500)}]},
        {"step": "s6", "about": "train with beta = 2", "match": "beta 2|higher convection",
         "finding": "the title says 'Train on sharper Gaussian IC' but the instructions and checks only rerun with --beta 2.0",
         "expect_checks": [{"type": "screen_contains", "app": "Terminal", "pattern": "beta 2\\.0"}],
         "actions": [{"do": "run", "cmd": "python pinn_convection.py --beta 2.0 --epochs 500", "output": run(2.0, 500, scale=1.3)}]},
        {"step": "s7", "about": "a full 4000-epoch run, loss still decreasing", "match": "4000|converg",
         "expect": "fail",
         "finding": "a correct learner can never pass s7: its metric_trend rows have window 5 (training steps), and a trend needs >= 8 points in the window, so even a metric logged every step gives 6 at most (also: the title says 'Compare with non-dimensionalized PINN' but the step only reruns 4000 epochs)",
         "expect_checks": [{"type": "screen_contains", "app": "Terminal", "pattern": "epoch 3900 \\| beta 1\\.0"}],
         "actions": [
             {"do": "mistake", "note": "stops the run with Ctrl+C at epoch 1500 (KeyboardInterrupt traceback)",
              "caught_by": ["s7c1", "s7c2"], "caught_by_spec_rows": ["x0"], "actions": [
                 {"do": "run", "cmd": "python pinn_convection.py --epochs 4000", "exit": 130, "output": run(1.0, 4000, stop_at=1500)}]},
             {"do": "run", "cmd": "python pinn_convection.py --epochs 4000", "output": run(1.0, 4000)}]},
    ],
}
with open(out_path, "w") as fh:
    json.dump(case, fh, indent=1, ensure_ascii=False)
    fh.write("\n")

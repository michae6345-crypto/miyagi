"""PINN lab: the 1D convection equation  du/dt + beta du/dx = 0  on x in [0, 2pi], t in [0, 1].

Exact solution: u(x, t) = sin(x - beta * t)  (initial condition sin(x), periodic in x).
Fill in the TODOs as the lesson goes; the engine watches this file and your terminal.

Run:   python pinn_convection.py --beta 1          (or through the wrapper: tut run python pinn_convection.py --beta 1)
Prints `epoch N loss X` for the screen reader and `::metric::` lines for `tut run`.
"""

import argparse
import math

import torch
from torch import nn


def log_metric(step, name, value):
    print(f'::metric:: {{"step": {step}, "name": "{name}", "value": {value}}}', flush=True)


# ----------------------------------------------------------------------------- step 2: the network
class PINN(nn.Module):
    """Maps (x, t) -> u. Two inputs, one output, a few hidden layers with a smooth activation."""

    def __init__(self, width=50, depth=4):
        super().__init__()
        # TODO: build self.net, a fully connected stack: 2 -> width -> ... -> width -> 1
        self.net = None

    def forward(self, x, t):
        return self.net(torch.cat([x, t], dim=1))


# ----------------------------------------------------------------------------- step 3: collocation points
def sample_points(n=1000):
    """Random (x, t) points inside the domain where the PDE residual is enforced."""
    # TODO: x uniform in [0, 2pi], t uniform in [0, 1], both shaped (n, 1),
    #       and both tracked by autograd (the residual differentiates through them)
    raise NotImplementedError("sample_points")


# ----------------------------------------------------------------------------- step 4: the PDE residual
def pde_residual(model, x, t, beta):
    """Residual of the convection equation at the collocation points."""
    u = model(x, t)
    # TODO: derivatives of u with respect to t and x (keep the graph so the loss can backprop),
    #       then return the convection residual
    raise NotImplementedError("pde_residual")


# ----------------------------------------------------------------------------- given: initial + boundary losses
def ic_loss(model, n=256):
    x = torch.linspace(0, 2 * math.pi, n).reshape(-1, 1)
    t = torch.zeros_like(x)
    return (model(x, t) - torch.sin(x)).pow(2).mean()


def bc_loss(model, n=256):
    t = torch.linspace(0, 1, n).reshape(-1, 1)
    left, right = torch.zeros_like(t), torch.full_like(t, 2 * math.pi)
    return (model(left, t) - model(right, t)).pow(2).mean()


# ----------------------------------------------------------------------------- step 5/6: training
def train(model, beta, epochs, lr=1e-3, offset=0):
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    for epoch in range(epochs):
        x, t = sample_points()
        loss = pde_residual(model, x, t, beta).pow(2).mean() + ic_loss(model) + bc_loss(model)
        opt.zero_grad()
        loss.backward()
        opt.step()
        if epoch % 100 == 0:
            step = offset + epoch
            print(f"epoch {step} | beta {beta} | loss {loss.item():.4e}", flush=True)
            log_metric(step, "loss", loss.item())
    return model


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--beta", type=float, default=1.0)
    ap.add_argument("--epochs", type=int, default=4000)
    args = ap.parse_args()
    torch.manual_seed(0)
    model = PINN()
    train(model, args.beta, args.epochs)


if __name__ == "__main__":
    main()

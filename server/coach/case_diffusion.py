"""Hero lesson: 1D diffusion PINN (tutorial video AXXnSzmpyoI). Three real learner mistakes;
the hero moment is mistake 2 (lr=0.3, loss oscillates).

PDE: y_t = y_xx + q(x, t) on x in [-1, 1], t in [0, 1], exact solution y = exp(-t) sin(pi x),
so q = -exp(-t) (sin(pi x) - pi^2 sin(pi x)). Code follows the tutorial's structure
(FCN with lossBC / lossPDE / loss, Adam loop) and logs ::metric:: lines.

Used by `python -m server.coach demo` and the tests; nothing here is read by the coach itself.
"""

from __future__ import annotations

LESSON = {
    "lesson": {
        "id": "pinn-diffusion",
        "title": "Physics-informed neural network for the 1D diffusion equation",
        "goal": "Train a PINN that solves y_t = y_xx + q(x, t) with initial and boundary conditions",
        "workdir": "demo/pinn",
        "libraries": {"torch": "2.1"},
    },
    "sources": [
        {"id": "yt", "kind": "video", "title": "Learning Physics Informed Machine Learning Part 1 – PINNs", "url": "https://www.youtube.com/watch?v=AXXnSzmpyoI", "videoId": "AXXnSzmpyoI"},
        {"id": "code", "kind": "repo", "title": "NABLA-SciML tutorials (PINNs)", "url": "https://github.com/jdtoscano94/NABLA-SciML/tree/main/Learning-PIML-in-Python-PINNs-DeepONets-RBA"},
    ],
    "steps": [],
}

STEP = {
    "id": "d6",
    "index": 6,
    "title": "Train the PINN",
    "instructions": "Train with Adam for 5000 iterations until the relative L2 error against the exact solution is below 5%.",
    "video": {"sourceId": "yt", "start": 1096, "end": 1414},
    "checks": [
        {"id": "d6a", "type": "metric_threshold", "label": "rel. L2 error < 5%", "metric": "rel_l2", "op": "<", "value": 0.05, "by_step": 5000},
        {"id": "d6b", "type": "metric_threshold", "label": "loss < 1e-3", "metric": "loss", "op": "<", "value": 0.001, "by_step": 5000},
    ],
    "targets": [{"file": "pinn_diffusion.py", "match": "def loss", "caption": "total loss"}],
    "explanations": [
        {"topic": "initial and boundary condition data", "t": 446, "sourceId": "yt"},
        {"topic": "coding the PINN: boundary loss and PDE residual loss", "t": 902, "sourceId": "yt"},
        {"topic": "training loop and results", "t": 1096, "sourceId": "yt"},
    ],
    "hints": ["Which conditions make the solution of a PDE unique?", "Print each loss term separately.", "The total loss combines two terms."],
}
LESSON["steps"] = [STEP]

_CODE_TEMPLATE = '''import torch
import torch.nn as nn

device = "mps" if torch.backends.mps.is_available() else "cpu"


class FCN(nn.Module):
    def __init__(self, layers):
        super().__init__()
        self.activation = nn.Tanh()
        self.loss_function = nn.MSELoss(reduction="mean")
        self.linears = nn.ModuleList([nn.Linear(layers[i], layers[i + 1]) for i in range(len(layers) - 1)])

    def forward(self, x):
        a = x.float()
        for linear in self.linears[:-1]:
            a = self.activation(linear(a))
        return self.linears[-1](a)

    def lossBC(self, x_BC, y_BC):
        return self.loss_function(self.forward(x_BC), y_BC)

    def lossPDE(self, x_PDE):
        g = {pde_input}
        f = self.forward(g)
        f_x_t = torch.autograd.grad(f, g, torch.ones_like(f), create_graph=True)[0]
        f_x, f_t = f_x_t[:, [0]], f_x_t[:, [1]]
        f_xx = torch.autograd.grad(f_x, g, torch.ones_like(f_x), create_graph=True)[0][:, [0]]
        x, t = g[:, [0]], g[:, [1]]
        q = -torch.exp(-t) * (torch.sin(torch.pi * x) - torch.pi**2 * torch.sin(torch.pi * x))
        return self.loss_function(f_t - f_xx, q)

    def loss(self, x_BC, y_BC, x_PDE):
        {total_loss}


model = FCN([2, 32, 32, 32, 1]).to(device)
optimizer = torch.optim.Adam(model.parameters(), lr={lr})

for i in range(5000):
    optimizer.zero_grad()
    loss = model.loss(X_BC, Y_BC, X_PDE)
    loss.backward()
    optimizer.step()
    if i % 250 == 0:
        log_metric(i, "loss", loss.item())
        log_metric(i, "rel_l2", rel_l2(model, X_test, Y_test))
'''

GOOD = {"pde_input": "x_PDE.clone().requires_grad_(True)", "total_loss": "return self.lossBC(x_BC, y_BC) + self.lossPDE(x_PDE)", "lr": "1e-3"}


def code(**mistake: str) -> str:
    return _CODE_TEMPLATE.format(**{**GOOD, **mistake})


def _series(vals):
    return [(i * 250, v) for i, v in enumerate(vals)]


# ---------- mistake 1: IC/BC loss computed but never added --------------------------
MISSING_BC_CODE = code(total_loss="return self.lossPDE(x_PDE)")
MISSING_BC_FAILED = [{"checkId": "d6a", "label": "rel. L2 error < 5%", "status": "fail", "detail": "rel_l2 0.97 at step 5000"}]
_loss = [2.1, 0.62, 0.21, 0.074, 0.031, 0.014, 0.0072, 0.0041, 0.0026, 0.0017, 0.0012, 0.00091, 0.00074, 0.00062, 0.00053, 0.00047, 0.00042, 0.00039, 0.00037, 0.00035, 0.00034]
_err = [1.02, 0.99, 0.98, 0.98, 0.97, 0.97, 0.97, 0.97, 0.97, 0.97, 0.97, 0.97, 0.97, 0.97, 0.97, 0.97, 0.97, 0.97, 0.97, 0.97, 0.97]
MISSING_BC_METRICS = {"loss": _series(_loss), "rel_l2": _series(_err)}

# ---------- mistake 2 (hero): learning rate 0.3, far too high → loss oscillates ----------------------
HIGH_LR_CODE = code(lr="0.3")
HIGH_LR_FAILED = [
    {"checkId": "d6b", "label": "loss < 1e-3", "status": "fail", "detail": "loss 0.84 at step 5000, oscillating between 0.3 and 2.4"},
    {"checkId": "d6a", "label": "rel. L2 error < 5%", "status": "fail", "detail": "rel_l2 0.71 at step 5000"},
]
HIGH_LR_METRICS = {
    "loss": _series([2.1, 0.92, 1.71, 0.64, 2.38, 0.55, 1.46, 0.31, 1.93, 0.48, 2.12, 0.62, 1.37, 0.39, 1.88, 0.57, 2.05, 0.44, 1.52, 0.36, 0.84]),
    "rel_l2": _series([1.02, 0.88, 0.95, 0.74, 1.06, 0.69, 0.91, 0.62, 0.98, 0.66, 1.01, 0.71, 0.86, 0.6, 0.97, 0.68, 0.99, 0.63, 0.9, 0.61, 0.71]),
}

# ---------- mistake 3: collocation points without requires_grad → autograd error -----------
NO_GRAD_CODE = code(pde_input="x_PDE")
NO_GRAD_ERROR = """Traceback (most recent call last):
  File "pinn_diffusion.py", line 52, in <module>
    loss = model.loss(X_BC, Y_BC, X_PDE)
  File "pinn_diffusion.py", line 29, in lossPDE
    f_x_t = torch.autograd.grad(f, g, torch.ones_like(f), create_graph=True)[0]
RuntimeError: One of the differentiated Tensors does not require grad"""
NO_GRAD_FAILED = [{"checkId": "d6b", "label": "loss < 1e-3", "status": "fail", "detail": "run crashed"}]

# defaults used by `python -m server.coach demo` (the hero)
CODE, FAILED_CHECKS, METRICS = HIGH_LR_CODE, HIGH_LR_FAILED, HIGH_LR_METRICS

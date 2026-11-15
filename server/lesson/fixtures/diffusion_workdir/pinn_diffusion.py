"""PINN for the 1D diffusion equation, written to follow Toscano's "Learning PIML Part 1"
(https://www.youtube.com/watch?v=AXXnSzmpyoI) step by step. Used as a sample learner
workdir for the lesson builder's precision report.

    y_t = y_xx - e^{-t} (sin(pi x) - pi^2 sin(pi x)),  x in [-1, 1], t in [0, 1]
    y(x, 0) = sin(pi x),  y(-1, t) = y(1, t) = 0,  exact: y = e^{-t} sin(pi x)
"""

import argparse
import time

import numpy as np
import torch
import torch.autograd as autograd
import torch.nn as nn
try:
    from pyDOE import lhs  # Latin hypercube sampling (as in the video)
except ImportError:  # pyDOE >= 1.6 renamed the module
    from pydoe import lhs

torch.set_default_dtype(torch.float)
torch.manual_seed(1234)
np.random.seed(1234)
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")


def log_metric(step, name, value):
    print(f'::metric:: {{"step": {step}, "name": "{name}", "value": {value}}}', flush=True)


# --- tuning parameters -------------------------------------------------------
ap = argparse.ArgumentParser()
ap.add_argument("--steps", type=int, default=20000)
ap.add_argument("--lr", type=float, default=1e-3)
args = ap.parse_args()
steps, lr = args.steps, args.lr
layers = np.array([2, 32, 32, 1])
x_min, x_max, t_min, t_max = -1, 1, 0, 1
total_points_x, total_points_t = 200, 100
Nu, Nf = 100, 10000


def f_real(x, t):
    return torch.exp(-t) * torch.sin(np.pi * x)


# --- data generation -----------------------------------------------------------
x = torch.linspace(x_min, x_max, total_points_x).view(-1, 1)
t = torch.linspace(t_min, t_max, total_points_t).view(-1, 1)
X, T = torch.meshgrid(x.squeeze(1), t.squeeze(1), indexing="ij")
y_real = f_real(X, T)

# --- data preparation ----------------------------------------------------------
x_test = torch.hstack((X.transpose(1, 0).flatten()[:, None], T.transpose(1, 0).flatten()[:, None]))
y_test = y_real.transpose(1, 0).flatten()[:, None]
lb, ub = x_test[0], x_test[-1]

# --- training data: initial + boundary conditions -----------------------------
left_X = torch.hstack((X[:, 0][:, None], T[:, 0][:, None]))  # t = 0
left_Y = torch.sin(np.pi * left_X[:, 0]).unsqueeze(1)
bottom_X = torch.hstack((X[0, :][:, None], T[0, :][:, None]))  # x = -1
bottom_Y = torch.zeros(bottom_X.shape[0], 1)
top_X = torch.hstack((X[-1, :][:, None], T[-1, :][:, None]))  # x = 1
top_Y = torch.zeros(top_X.shape[0], 1)
X_train = torch.vstack([left_X, bottom_X, top_X])
Y_train = torch.vstack([left_Y, bottom_Y, top_Y])
idx = np.random.choice(X_train.shape[0], Nu, replace=False)
X_train_Nu, Y_train_Nu = X_train[idx, :], Y_train[idx, :]

# --- collocation points ------------------------------------------------------
X_train_Nf = lb + (ub - lb) * torch.from_numpy(lhs(2, Nf)).float()
X_train_Nf = torch.vstack((X_train_Nf, X_train_Nu))


# --- the PINN ------------------------------------------------------------------
class FCN(nn.Module):
    def __init__(self, layers):
        super().__init__()
        self.activation = nn.Tanh()
        self.loss_function = nn.MSELoss(reduction="mean")
        self.linears = nn.ModuleList([nn.Linear(layers[i], layers[i + 1]) for i in range(len(layers) - 1)])
        for lin in self.linears:
            nn.init.xavier_normal_(lin.weight.data, gain=1.0)
            nn.init.zeros_(lin.bias.data)

    def forward(self, x):
        a = x.float()
        for lin in self.linears[:-1]:
            a = self.activation(lin(a))
        return self.linears[-1](a)

    def lossBC(self, x_BC, y_BC):
        return self.loss_function(self.forward(x_BC), y_BC)

    def lossPDE(self, x_PDE):
        g = x_PDE.clone()
        g.requires_grad = True
        f = self.forward(g)
        f_x_t = autograd.grad(f, g, torch.ones([g.shape[0], 1]).to(device), retain_graph=True, create_graph=True)[0]
        f_xx_tt = autograd.grad(f_x_t, g, torch.ones(g.shape).to(device), create_graph=True)[0]
        f_t = f_x_t[:, [1]]
        f_xx = f_xx_tt[:, [0]]
        f = f_t - f_xx + torch.exp(-g[:, 1:]) * (torch.sin(np.pi * g[:, 0:1]) - np.pi**2 * torch.sin(np.pi * g[:, 0:1]))
        return self.loss_function(f, torch.zeros_like(f))

    def loss(self, x_BC, y_BC, x_PDE):
        return self.lossBC(x_BC, y_BC) + self.lossPDE(x_PDE)


# --- training ------------------------------------------------------------------
X_train_Nu, Y_train_Nu, X_train_Nf = X_train_Nu.to(device), Y_train_Nu.to(device), X_train_Nf.to(device)
X_test, Y_test = x_test.to(device), y_test.to(device)
PINN = FCN(layers).to(device)
optimizer = torch.optim.Adam(PINN.parameters(), lr=lr, amsgrad=False)
start_time = time.time()
for i in range(steps):
    loss = PINN.loss(X_train_Nu, Y_train_Nu, X_train_Nf)
    optimizer.zero_grad()
    loss.backward()
    optimizer.step()
    if i % max(1, steps // 100) == 0 or i == steps - 1:
        with torch.no_grad():
            test_loss = PINN.lossBC(X_test, Y_test)
        log_metric(i, "loss", loss.item())
        log_metric(i, "test_loss", test_loss.item())
print(f"trained {steps} steps in {time.time() - start_time:.1f}s")

# --- results -------------------------------------------------------------------
if steps >= 1000:
    import matplotlib.pyplot as plt

    y1 = PINN(X_test).detach().cpu().reshape(100, 200).T
    fig, ax = plt.subplots(1, 2, figsize=(10, 4))
    ax[0].contourf(T, X, y1, 20, cmap="rainbow")
    ax[0].set_title("PINN")
    ax[1].contourf(T, X, y_real, 20, cmap="rainbow")
    ax[1].set_title("exact")
    plt.savefig("results.png")

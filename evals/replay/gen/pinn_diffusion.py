"""Generator for evals/replay/cases/pinn-diffusion.json (synthetic run output in report()'s format)."""
import json
import math
import sys
from pathlib import Path

out_path = sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).resolve().parents[1] / "cases" / "pinn-diffusion.json")


def report(i, loss, test):
    return [f"step {i} | loss {loss:.4e} | test {test:.4e}",
            f'::metric:: {{"step": {i}, "name": "loss", "value": {loss}}}',
            f'::metric:: {{"step": {i}, "name": "test_loss", "value": {test}}}']


def run(loss_fn, test_fn, steps=5000, every=250):
    lines = []
    for i in range(0, steps, every):
        lines += report(i, round(loss_fn(i), 6), round(test_fn(i), 6))
    return lines


good = run(lambda i: 1.18 * math.exp(-i / 180) + 2.1e-4 * (1 + 0.3 * math.cos(i / 400)),
           lambda i: 0.41 * math.exp(-i / 200) + 6e-5)
diverged = run(lambda i: 17.03 + 0.04 * math.sin(i / 300) if i else 1.18,
               lambda i: 0.52 + 0.01 * math.cos(i / 300))

SEC1 = """import torch
import torch.autograd as autograd
from torch import Tensor
import torch.nn as nn
import torch.optim as optim
import numpy as np
from pyDOE import lhs

torch.set_default_dtype(torch.float)
torch.manual_seed(1234)
np.random.seed(1234)
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')"""

SEC2 = """steps = 5000
lr = 1e-3
layers = np.array([2, 32, 64, 1])
x_min, x_max = -1, 1
t_min, t_max = 0, 1
total_points_x = 200
total_points_t = 100
Nu = 100
Nf = 10000

def f_real(x, t):
    return torch.exp(-t) * (torch.sin(np.pi * x))

x = torch.linspace(x_min, x_max, total_points_x).view(-1, 1)
t = torch.linspace(t_min, t_max, total_points_t).view(-1, 1)
X, T = torch.meshgrid(x.squeeze(1), t.squeeze(1), indexing='ij')
y_real = f_real(X, T)"""

SEC3 = """X_test = torch.hstack((X.transpose(1, 0).flatten()[:, None], T.transpose(1, 0).flatten()[:, None]))
y_test = y_real.transpose(1, 0).flatten()[:, None]
lb = X_test[0]
ub = X_test[-1]"""

SEC4 = """left_X = torch.hstack((X[:, 0][:, None], T[:, 0][:, None]))
left_Y = torch.sin(np.pi * left_X[:, 0]).unsqueeze(1)
bottom_X = torch.hstack((X[0, :][:, None], T[0, :][:, None]))
bottom_Y = torch.zeros(bottom_X.shape[0], 1)
top_X = torch.hstack((X[-1, :][:, None], T[-1, :][:, None]))
top_Y = torch.zeros(top_X.shape[0], 1)
X_train = torch.vstack([left_X, bottom_X, top_X])
Y_train = torch.vstack([left_Y, bottom_Y, top_Y])
idx = np.random.choice(X_train.shape[0], Nu, replace=False)
X_train_Nu = X_train[idx, :]
Y_train_Nu = Y_train[idx, :]"""

SEC5 = """X_train_Nf = lb + (ub - lb) * lhs(2, Nf)
X_train_Nf = torch.vstack((X_train_Nf, X_train_Nu))
f_hat = torch.zeros(X_train_Nf.shape[0], 1).to(device)
X_train_Nu = X_train_Nu.float().to(device)
Y_train_Nu = Y_train_Nu.float().to(device)
X_train_Nf = X_train_Nf.float().to(device)
X_test = X_test.float().to(device)
y_test = y_test.float().to(device)"""

SEC6 = """class FCN(nn.Module):
    def __init__(self, layers):
        super().__init__()
        self.activation = nn.Tanh()
        self.loss_function = nn.MSELoss(reduction='mean')
        self.linears = nn.ModuleList([nn.Linear(layers[i], layers[i + 1]) for i in range(len(layers) - 1)])
        for i in range(len(layers) - 1):
            nn.init.xavier_normal_(self.linears[i].weight.data, gain=1.0)
            nn.init.zeros_(self.linears[i].bias.data)

    def forward(self, x):
        a = x.float()
        for i in range(len(self.linears) - 1):
            a = self.activation(self.linears[i](a))
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
        f = f_t - f_xx + torch.exp(-g[:, 1:]) * (torch.sin(np.pi * g[:, 0:1]) - np.pi ** 2 * torch.sin(np.pi * g[:, 0:1]))
        return self.loss_function(f, f_hat)

    def loss(self, x_BC, y_BC, x_PDE):
        return self.lossBC(x_BC, y_BC) + self.lossPDE(x_PDE)"""

SEC7 = """PINN = FCN(layers)
PINN.to(device)
optimizer = torch.optim.Adam(PINN.parameters(), lr=lr, amsgrad=False)"""

LOOP = """for i in range(steps):
    loss = PINN.loss(X_train_Nu, Y_train_Nu, X_train_Nf)
    optimizer.zero_grad()
    loss.backward()
    optimizer.step()
    if i % 250 == 0:
        with torch.no_grad():
            test_loss = PINN.lossBC(X_test, y_test)
        report(i, loss.item(), test_loss.item())"""

SEC8 = """y1 = PINN(X_test)
x1 = X_test[:, 0]
t1 = X_test[:, 1]
arr_x1 = x1.reshape(shape=[100, 200]).transpose(1, 0).detach().cpu()
arr_T1 = t1.reshape(shape=[100, 200]).transpose(1, 0).detach().cpu()
arr_y1 = y1.reshape(shape=[100, 200]).transpose(1, 0).detach().cpu()
arr_y_test = y_test.reshape(shape=[100, 200]).transpose(1, 0).detach().cpu()"""

F = "pinn_diffusion.py"


def ins(after, text):
    return {"do": "insert", "file": F, "after": after, "text": text}


case = {
    "id": "pinn-diffusion",
    "topic": "physics-ml",
    "stack": "PyTorch + pyDOE (VS Code + its terminal)",
    "tutorial": {"kind": "video", "video_id": "AXXnSzmpyoI", "url": "https://www.youtube.com/watch?v=AXXnSzmpyoI",
                 "goal": "train a physics-informed neural network in PyTorch"},
    "lesson": "demo/cache/lessons/aebc6b8fba02dac5.json",
    "learner": {
        "folder": "pinn-lab",
        "seed": "demo/pinn-lab",
        "notes": "Fills demo/pinn-lab/pinn_diffusion.py section by section (Toscano's code). Training output is written in report()'s exact format (step/loss/test + ::metric:: lines); the values are synthetic, shaped like demo/pinn-lab/README.md's measurements (lr 1e-3 under 1e-2 near step 900; lr 0.3 flat near 17)."
    },
    "outline": [
        {"step": "s1", "about": "install pyDOE; imports, seeds and device", "match": "pyDOE|import",
         "expect_checks": [{"type": "file_contains", "file": F, "pattern": "^from pyDOE import lhs$"},
                           {"type": "file_contains", "file": F, "pattern": "^device = torch\\.device\\("},
                           {"type": "screen_contains", "app": "Terminal", "pattern": "Successfully installed pyDOE-0\\.3\\.8"}],
         "actions": [
             {"do": "run", "cmd": "pip install pyDOE", "output": ["Collecting pyDOE", "  Downloading pyDOE-0.3.8.zip (22 kB)",
                                                                  "Building wheels for collected packages: pyDOE", "Successfully built pyDOE",
                                                                  "Installing collected packages: pyDOE", "Successfully installed pyDOE-0.3.8"]},
             {"do": "mistake", "note": "types the imports and seeds but not the device line", "caught_by": ["s1c2"], "caught_by_spec_rows": ["x1"],
              "actions": [ins("# TODO: make 32-bit floats", SEC1.rsplit("\n", 1)[0])]},
             {"do": "insert", "file": F, "after": "np.random.seed(1234)", "text": SEC1.rsplit("\n", 1)[1]},
         ]},
        {"step": "s2", "about": "parameters, f_real and the meshgrid", "match": "exact solution|meshgrid",
         "expect_checks": [{"type": "file_contains", "file": F, "pattern": "return torch\\.exp\\(-t\\) \\* \\(torch\\.sin\\(np\\.pi \\* x\\)\\)"}],
         "actions": [ins("# TODO: a function giving the exact solution", SEC2)]},
        {"step": "s3", "about": "flatten the grid into X_test / y_test, keep lb and ub", "match": "flatten|test",
         "expect_checks": [{"type": "file_contains", "file": F, "pattern": "^ub = X_test\\[-1\\]$"}],
         "actions": [ins("# TODO: stack the flattened grid", SEC3)]},
        {"step": "s4", "about": "initial and boundary training data, Nu samples", "match": "boundary|initial",
         "expect_checks": [{"type": "file_contains", "file": F, "pattern": "idx = np\\.random\\.choice\\(X_train\\.shape\\[0\\], Nu, replace=False\\)"}],
         "actions": [ins("# TODO: points on t = 0", SEC4)]},
        {"step": "s5", "about": "Latin-hypercube collocation points", "match": "collocation|lhs",
         "expect_checks": [{"type": "file_contains", "file": F, "pattern": "X_train_Nf = lb \\+ \\(ub - lb\\) \\* lhs\\(2, Nf\\)"}],
         "actions": [ins("# TODO: sample interior points", SEC5)]},
        {"step": "s6", "about": "the FCN class with lossBC, lossPDE and loss", "match": "FCN|network",
         "expect_checks": [{"type": "file_contains", "file": F, "pattern": "f_xx_tt = autograd\\.grad\\(f_x_t, g, .*create_graph=True\\)"}],
         "actions": [
             {"do": "mistake", "note": "no create_graph=True in either autograd.grad (the PDE loss can't train)", "caught": False, "caught_by_spec_rows": ["x0"],
              "finding": "s6's only precision check is class FCN(nn.Module), so precision mode passes lossPDE without create_graph=True",
              "actions": [
                 ins("# TODO: a fully connected network class", SEC6.replace(", retain_graph=True, create_graph=True)", ", retain_graph=True)").replace(", create_graph=True)", ")"))]},
             {"do": "edit", "file": F, "find": "torch.ones([g.shape[0], 1]).to(device), retain_graph=True)",
              "replace": "torch.ones([g.shape[0], 1]).to(device), retain_graph=True, create_graph=True)"},
             {"do": "edit", "file": F, "find": "torch.ones(g.shape).to(device))[0]", "replace": "torch.ones(g.shape).to(device), create_graph=True)[0]"},
         ]},
        {"step": "s7", "about": "PINN = FCN(layers) and an Adam optimizer", "match": "adam|instantiate",
         "expect_checks": [{"type": "file_contains", "file": F, "pattern": "optimizer = torch\\.optim\\.Adam\\(PINN\\.parameters\\(\\), lr=lr"}],
         "actions": [ins("# TODO: build the model and an Adam optimizer", SEC7)]},
        {"step": "s8", "about": "train and see loss < 1e-2 by step 2000", "match": "train",
         "expect_checks": [{"type": "metric_threshold", "metric": "loss", "op": "<", "value": 0.01, "by_step": 2000},
                           {"type": "screen_absent", "app": "Terminal", "pattern": "Traceback"}],
         "actions": [
             {"do": "insert", "file": F, "after": "optimizer = torch.optim.Adam(", "text": "\n" + LOOP},
             {"do": "mistake", "note": "lr = 0.3: the loss diverges and sits near 17 (the demo's hero failure)",
              "caught_by": ["s8c4"], "caught_by_spec_rows": ["x0"], "actions": [
                 {"do": "edit", "file": F, "find": "lr = 1e-3", "replace": "lr = 0.3"},
                 {"do": "run", "cmd": "python pinn_diffusion.py", "output": diverged}]},
             {"do": "edit", "file": F, "find": "lr = 0.3", "replace": "lr = 1e-3"},
             {"do": "run", "cmd": "python pinn_diffusion.py", "output": good},
         ]},
        {"step": "s9", "about": "evaluate PINN on the test grid for the plots", "match": "evaluate|plot",
         "expect_checks": [{"type": "file_contains", "file": F, "pattern": "^y1 = PINN\\(X_test\\)$"}],
         "actions": [ins("# TODO: evaluate on the test grid", SEC8)]},
    ],
}
with open(out_path, "w") as fh:
    json.dump(case, fh, indent=1, ensure_ascii=False)
    fh.write("\n")

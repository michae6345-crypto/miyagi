"""The hero case: PINN on the convection equation at β=30, loss flat. Shared by the demo and tests."""

LESSON = {
    "lesson": {
        "id": "pinn-convection",
        "title": "Physics-informed neural network for the convection equation",
        "goal": "Train a PINN that solves u_t + β u_x = 0 on a periodic domain",
        "workdir": "demo/pinn",
        "libraries": {"torch": "2.1"},
    },
    "sources": [
        {"id": "yt", "kind": "video", "title": "PINNs from scratch in PyTorch", "url": "https://www.youtube.com/watch?v=DEMO", "videoId": "DEMO"},
        {"id": "paper", "kind": "paper", "title": "Characterizing possible failure modes in physics-informed neural networks", "url": "https://arxiv.org/abs/2109.01050"},
    ],
    "steps": [],  # filled below
}

STEP = {
    "id": "s5",
    "index": 5,
    "title": "Train at β = 30",
    "instructions": "Raise β to 30 and train until the loss is below 1e-2.",
    "video": {"sourceId": "yt", "start": 512, "end": 590},
    "checks": [
        {"id": "c5a", "type": "metric_threshold", "label": "loss < 1e-2", "metric": "loss", "op": "<", "value": 0.01, "by_step": 4000},
        {"id": "c5b", "type": "metric_trend", "label": "loss still dropping", "metric": "loss", "trend": "not_flat", "window": 1500},
    ],
    "targets": [{"file": "pinn_convection.py", "match": "def train", "caption": "training loop"}],
    "explanations": [
        {"topic": "why large beta makes PINN training hard", "t": 548, "sourceId": "yt"},
        {"topic": "residual loss with autograd", "t": 301, "sourceId": "yt"},
    ],
    "hints": ["Compare the loss curve at β=1 and β=30.", "The tutorial trains β in stages.", "Warm-start from a model trained at smaller β."],
}
LESSON["steps"] = [STEP]

FAILED_CHECKS = [
    {"checkId": "c5a", "label": "loss < 1e-2", "status": "fail", "detail": "loss 0.183 at step 4000"},
    {"checkId": "c5b", "label": "loss still dropping", "status": "fail", "detail": "changed 0.6% over the last 1500 steps"},
]

# loss plateaus at ~0.18 after a fast initial drop (what the real run looks like at β=30)
_curve = [1.02, 0.61, 0.38, 0.27, 0.22, 0.199, 0.191, 0.187, 0.185, 0.184, 0.1836, 0.1834, 0.1832, 0.1831, 0.1830, 0.1830, 0.1829]
METRICS = {
    "loss": [(i * 250, v) for i, v in enumerate(_curve)],
    "loss/residual": [(i * 250, v * 0.7) for i, v in enumerate(_curve)],
    "loss/ic": [(i * 250, v * 0.3) for i, v in enumerate(_curve)],
}

CODE = '''import torch
import torch.nn as nn

beta = 30.0
device = "mps" if torch.backends.mps.is_available() else "cpu"

class PINN(nn.Module):
    def __init__(self, width=50, depth=4):
        super().__init__()
        layers, d = [], 2
        for _ in range(depth):
            layers += [nn.Linear(d, width), nn.Tanh()]
            d = width
        layers.append(nn.Linear(d, 1))
        self.net = nn.Sequential(*layers)

    def forward(self, x, t):
        return self.net(torch.cat([x, t], dim=1))

def residual(model, x, t):
    u = model(x, t)
    u_t = torch.autograd.grad(u, t, torch.ones_like(u), create_graph=True)[0]
    u_x = torch.autograd.grad(u, x, torch.ones_like(u), create_graph=True)[0]
    return u_t + beta * u_x

def train(model, epochs=4000, lr=1e-3):
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    for step in range(epochs):
        opt.zero_grad()
        x, t = sample_collocation(device)
        loss_r = residual(model, x, t).pow(2).mean()
        loss_ic = (model(x0, t0) - torch.sin(x0)).pow(2).mean()
        loss = loss_r + loss_ic
        loss.backward()
        opt.step()
        if step % 250 == 0:
            log_metric(step, "loss", loss.item())

model = PINN().to(device)
train(model)
'''

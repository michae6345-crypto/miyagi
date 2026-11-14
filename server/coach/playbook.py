"""Domain playbook: known ML failure modes the coach can draw on.

Each entry is curated by hand (citations checked) so the coach never invents a
paper. The LLM may only cite ids from `CITATIONS`; anything else is dropped.

`match()` is a cheap deterministic matcher used for triage and as the offline
fallback card when the API is unavailable (the demo must never show a blank).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# --- citations the coach is allowed to use -----------------------------------
CITATIONS: dict[str, dict[str, str]] = {
    "krishnapriyan2021": {
        "label": "Krishnapriyan et al., NeurIPS 2021",
        "url": "https://arxiv.org/abs/2109.01050",
    },
    "wang2021_gradpath": {
        "label": "Wang, Teng & Perdikaris, SIAM J. Sci. Comput. 2021",
        "url": "https://arxiv.org/abs/2001.04536",
    },
    "torch_zero_grad": {
        "label": "PyTorch recipe: zeroing out gradients",
        "url": "https://pytorch.org/tutorials/recipes/recipes/zeroing_out_gradients.html",
    },
    "torch_mps": {
        "label": "PyTorch docs: MPS backend",
        "url": "https://pytorch.org/docs/stable/notes/mps.html",
    },
    "smith2017_clr": {
        "label": "Smith, Cyclical Learning Rates (LR range test), WACV 2017",
        "url": "https://arxiv.org/abs/1506.01186",
    },
    "torch_autograd_grad": {
        "label": "PyTorch docs: torch.autograd.grad",
        "url": "https://pytorch.org/docs/stable/generated/torch.autograd.grad.html",
    },
}


@dataclass(frozen=True)
class FailureMode:
    id: str
    name: str
    symptoms: str  # what the learner sees
    cause: str  # why, in one or two sentences an expert would agree with
    fix: str  # what to do
    citation_id: str
    # deterministic signals ------------------------------------------------
    code_patterns: tuple[str, ...] = ()  # regexes that should be present
    code_absent: tuple[str, ...] = ()  # regexes whose absence is a signal
    metric_signals: tuple[str, ...] = ()  # "plateau" | "diverging" | "nan"
    error_patterns: tuple[str, ...] = ()  # regexes over error/output text
    card_title: str = ""
    card_body: str = ""
    diff_expected: str = ""
    diff_yours_hint: str = ""  # regex to pull the learner's offending line
    tags: tuple[str, ...] = field(default_factory=tuple)


PLAYBOOK: tuple[FailureMode, ...] = (
    FailureMode(
        id="pinn_convection_large_beta",
        name="PINN on convection fails at large beta",
        symptoms=(
            "Training a PINN on u_t + beta*u_x = 0 with large beta (roughly beta >= 10, "
            "e.g. 30): loss falls a little then plateaus around 1e-1 to 1e-2; the "
            "predicted solution is smooth/near-constant instead of the advected wave."
        ),
        cause=(
            "Not a capacity or bug problem: the PDE residual term makes the loss "
            "landscape much harder to optimize as beta grows, so gradient descent "
            "stalls in a poor region (Krishnapriyan et al. 2021)."
        ),
        fix=(
            "Curriculum regularization: train first at small beta (e.g. 1), then "
            "warm-start from those weights while increasing beta in stages up to "
            "the target (e.g. 1 -> 5 -> 10 -> 20 -> 30). Seq2seq time-marching is the "
            "paper's other remedy."
        ),
        citation_id="krishnapriyan2021",
        code_patterns=(r"\bbeta\b|β", r"[uf]_t\b|du_dt|\but\b", r"[uf]_x\b|du_dx|\bux\b"),
        metric_signals=("plateau",),
        card_title="Known PINN failure at large β",
        card_body=(
            "At β=30 the residual makes the loss landscape hard to optimize, so "
            "training stalls. Train at small β first, then warm-start while raising "
            "β to 30."
        ),
        diff_expected=(
            "for beta in [1.0, 5.0, 10.0, 20.0, 30.0]:  # curriculum on β, warm-started\n"
            "    train(model, epochs=1000)"
        ),
        diff_yours_hint=r"^\s*train\(model.*\)\s*$",
        tags=("pinn", "convection", "curriculum"),
    ),
    FailureMode(
        id="pinn_loss_imbalance",
        name="PINN loss terms out of balance",
        symptoms=(
            "Residual loss goes down but boundary/initial-condition loss stays high "
            "(or vice versa); solution satisfies the PDE but ignores the IC/BC."
        ),
        cause=(
            "Gradients of the residual term dominate the boundary terms, a stiffness "
            "in the gradient flow (Wang, Teng & Perdikaris 2021)."
        ),
        fix="Weight the IC/BC loss terms up (fixed weight or adaptive, gradient-norm based).",
        citation_id="wang2021_gradpath",
        metric_signals=("imbalance",),
        card_title="Boundary loss is being ignored",
        card_body=(
            "The residual's gradients drown out the initial-condition term. Weight "
            "the IC/BC loss up so both terms actually train."
        ),
        tags=("pinn",),
    ),
    FailureMode(
        id="missing_zero_grad",
        name="Forgot optimizer.zero_grad()",
        symptoms="Loss jumps around or blows up after a few steps; gets worse over time.",
        cause=(
            "PyTorch accumulates .grad across backward() calls; without zeroing, each "
            "step uses the sum of all past gradients."
        ),
        fix="Call optimizer.zero_grad() once per iteration before loss.backward().",
        citation_id="torch_zero_grad",
        code_patterns=(r"\.backward\(", r"\.step\("),
        code_absent=(r"zero_grad\(",),
        metric_signals=("diverging", "noisy"),
        card_title="Gradients are piling up",
        card_body=(
            "PyTorch adds new gradients to old ones until you clear them. Call "
            "optimizer.zero_grad() each iteration, before loss.backward()."
        ),
        diff_expected="optimizer.zero_grad()\nloss.backward()\noptimizer.step()",
        diff_yours_hint=r"^.*\.backward\(.*$",
        tags=("pytorch",),
    ),
    FailureMode(
        id="cuda_on_mac",
        name="CUDA device on a Mac (use MPS or CPU)",
        symptoms=(
            "AssertionError: Torch not compiled with CUDA enabled, or tensors on "
            "different devices, when the tutorial was recorded on an NVIDIA box."
        ),
        cause="Apple Silicon has no CUDA; PyTorch's GPU backend on Mac is 'mps'.",
        fix=(
            'device = "cuda" if torch.cuda.is_available() else '
            '"mps" if torch.backends.mps.is_available() else "cpu"; '
            "then move model and every tensor with .to(device)."
        ),
        citation_id="torch_mps",
        code_patterns=(r"cuda",),
        error_patterns=(
            r"not compiled with CUDA",
            r"Expected all tensors to be on the same device",
            r"cuda.*(unavailable|not available)",
        ),
        card_title="This Mac has no CUDA",
        card_body=(
            "The tutorial ran on an NVIDIA GPU. On Apple Silicon use the 'mps' device "
            "(or CPU), and move the model and every tensor to it."
        ),
        diff_expected=(
            'device = "mps" if torch.backends.mps.is_available() else "cpu"'
        ),
        diff_yours_hint=r"^.*cuda.*$",
        tags=("pytorch", "mac"),
    ),
    FailureMode(
        id="lr_too_high",
        name="Learning rate too high: loss explodes",
        symptoms="Loss rises, oscillates wildly, or becomes nan/inf within the first few hundred steps.",
        cause="Step size overshoots the minimum; updates grow instead of shrink.",
        fix="Lower the learning rate ~10x (Adam: start near 1e-3), or run an LR range test.",
        citation_id="smith2017_clr",
        code_patterns=(r"lr\s*=\s*(?:[1-9]\d*(?:\.\d*)?|0?\.[1-9]|[1-9](?:\.\d+)?e-0?1)\b",),
        metric_signals=("diverging", "nan"),
        error_patterns=(r"\bnan\b", r"\binf\b"),
        card_title="Learning rate is too high",
        card_body=(
            "Each update overshoots, so the loss grows instead of shrinking. Drop the "
            "learning rate about 10x; for Adam, 1e-3 is a safe start."
        ),
        diff_expected="optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)",
        diff_yours_hint=r"^.*\blr\s*=.*$",
        tags=("optimization",),
    ),
    FailureMode(
        id="pinn_inputs_no_grad",
        name="PINN inputs missing requires_grad",
        symptoms=(
            "RuntimeError: One of the differentiated Tensors does not require grad, "
            "when computing u_x / u_t with torch.autograd.grad."
        ),
        cause="autograd can only differentiate u w.r.t. x and t if they were created with requires_grad=True.",
        fix="Create collocation points with requires_grad=True (or call .requires_grad_()).",
        citation_id="torch_autograd_grad",
        error_patterns=(r"does not require grad",),
        card_title="x and t need requires_grad",
        card_body=(
            "To take u_x and u_t, autograd needs x and t marked as differentiable. "
            "Create the collocation points with requires_grad=True."
        ),
        diff_expected="x = x.clone().requires_grad_(True)\nt = t.clone().requires_grad_(True)",
        tags=("pinn", "pytorch"),
    ),
)

BY_ID: dict[str, FailureMode] = {m.id: m for m in PLAYBOOK}


def playbook_text() -> str:
    """Stable rendering for the (cached) system prompt."""
    parts = []
    for m in PLAYBOOK:
        c = CITATIONS[m.citation_id]
        parts.append(
            f"### {m.id}: {m.name}\n"
            f"- Symptoms: {m.symptoms}\n"
            f"- Cause: {m.cause}\n"
            f"- Fix: {m.fix}\n"
            f"- citation_id: {m.citation_id} ({c['label']}, {c['url']})"
        )
    return "\n\n".join(parts)


# --- deterministic matcher ----------------------------------------------------

def _search(pattern: str, text: str) -> bool:
    return re.search(pattern, text or "", re.IGNORECASE | re.MULTILINE) is not None


def match(
    code_excerpt: str = "",
    metric_flags: set[str] | None = None,
    error_text: str = "",
) -> tuple[FailureMode | None, float]:
    """Best playbook entry and a 0..1 confidence from cheap signals."""
    flags = metric_flags or set()
    best: FailureMode | None = None
    best_score = 0.0
    for m in PLAYBOOK:
        score = 0.0
        if m.error_patterns and any(_search(p, error_text) for p in m.error_patterns):
            score += 0.6
        if m.code_patterns:
            hits = sum(_search(p, code_excerpt) for p in m.code_patterns)
            score += 0.3 * hits / len(m.code_patterns)
        if m.code_absent and code_excerpt and all(not _search(p, code_excerpt) for p in m.code_absent):
            score += 0.3
        if m.metric_signals and flags & set(m.metric_signals):
            score += 0.4
        if score > best_score:
            best, best_score = m, score
    return best, min(best_score, 1.0)


def offending_line(mode: FailureMode, code_excerpt: str) -> tuple[str, int | None]:
    """The learner's line that the fix replaces (for the diff), with its 1-based line number."""
    if not mode.diff_yours_hint or not code_excerpt:
        return "", None
    rx = re.compile(mode.diff_yours_hint, re.IGNORECASE)
    for i, line in enumerate(code_excerpt.splitlines(), start=1):
        if rx.match(line):
            return line.strip(), i
    return "", None

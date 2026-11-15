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
    "raissi2019": {
        "label": "Raissi, Perdikaris & Karniadakis, J. Comput. Phys. 2019",
        "url": "https://doi.org/10.1016/j.jcp.2018.10.045",
    },
    "torch_autograd_grad": {
        "label": "PyTorch docs: torch.autograd.grad",
        "url": "https://pytorch.org/docs/stable/generated/torch.autograd.grad.html",
    },
    "git_rebase_docs": {
        "label": "Git docs: git rebase (interactive mode)",
        "url": "https://git-scm.com/docs/git-rebase",
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
    requires: tuple[str, ...] = ()  # code regexes that must ALL match, else the entry scores 0
    context_signals: tuple[str, ...] = ()  # metric flags that count only when a code pattern matched
    card_title: str = ""
    card_body: str = ""
    diff_expected: str = ""
    diff_yours_hint: str = ""  # regex to pull the learner's offending line
    tags: tuple[str, ...] = field(default_factory=tuple)


PLAYBOOK: tuple[FailureMode, ...] = (
    FailureMode(
        id="pinn_missing_ic_bc",
        name="PINN total loss is missing the initial/boundary-condition term",
        symptoms=(
            "Any PINN (heat/diffusion, Burgers, wave, ...): the training loss drops nicely, "
            "but the error against the exact or reference solution stays high (or the "
            "plotted solution has the wrong shape or offset); or the loss plateaus."
        ),
        cause=(
            "The PDE residual alone does not determine the solution: infinitely many "
            "functions satisfy the equation. The initial and boundary conditions pick the "
            "unique one, so a loss without the IC/BC term (or with it computed but never "
            "added to the total) trains toward the wrong function."
        ),
        fix=(
            "Make the total loss the sum of the IC/BC data loss and the PDE residual loss "
            "(e.g. loss = loss_bc + loss_pde) and check both terms are logged and decreasing."
        ),
        citation_id="raissi2019",
        code_patterns=(r"autograd\.grad",),
        # the IC/BC loss term appears in a sum (either side of "+"); its absence is the signal
        code_absent=(
            r"(?i)\w*(?:loss_?(?:bc|ic|bnd|boundary|init)|(?:bc|ic|bnd|boundary|init\w*)_?loss)\w*\s*(?:\([^)]*\))?\s*\+",
            r"(?i)\+\s*[\w.]*(?:loss_?(?:bc|ic|bnd|boundary|init)|(?:bc|ic|bnd|boundary|init\w*)_?loss)",
        ),
        metric_signals=("low_loss_wrong_solution",),
        card_title="Loss has no boundary-condition term",
        card_body=(
            "The PDE residual alone is satisfied by many functions; the initial and "
            "boundary conditions pick the right one. Add the IC/BC loss to the total."
        ),
        tags=("pinn",),
    ),
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
        requires=(r"\bbeta\b|β",),  # no β in the code → not this failure (S11: the lr=0.3 hero scored 0.5 here)
        metric_signals=("plateau",),
        card_title="Known PINN failure at large β",
        card_body=(
            "At large β the residual makes the loss landscape hard to optimize, so "
            "training stalls. Train at small β first, then warm-start while raising "
            "β to the target."
        ),
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
        name="Learning rate too high: loss oscillates or explodes",
        symptoms=(
            "Loss oscillates (jumps up and down without settling), rises, or becomes nan/inf; or, with "
            "saturating activations (tanh, sigmoid), it drops once then sits flat at a high value; error "
            "metrics never settle."
        ),
        cause=(
            "The step size is too large for the loss curvature, so each update overshoots "
            "the minimum: the iterate bounces across the valley (oscillation) or grows (divergence)."
        ),
        fix="Lower the learning rate ~10x (Adam: start near 1e-3), or run an LR range test; a decaying schedule also damps oscillation.",
        citation_id="smith2017_clr",
        code_patterns=(r"lr\s*=\s*(?:[1-9]\d*(?:\.\d*)?|0?\.[1-9]|[1-9](?:\.\d+)?e-0?1)\b",),
        metric_signals=("diverging", "nan", "noisy"),
        # a high lr can also saturate tanh units: loss stalls high and flat (S11: hero lr=0.3 takes)
        context_signals=("plateau",),
        error_patterns=(r"\bnan\b", r"\binf\b"),
        card_title="Learning rate is too high",
        card_body=(
            "Each update overshoots the minimum, so the loss bounces or grows instead of "
            "settling. Lower the learning rate about 10x; for Adam, 1e-3 is a safe start."
        ),
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
        cause=(
            "autograd can only differentiate u with respect to x and t if those input "
            "tensors require grad and u was computed from them (not from a detached copy)."
        ),
        fix="Create collocation points with requires_grad=True (or call .requires_grad_()).",
        citation_id="torch_autograd_grad",
        error_patterns=(
            r"does not require grad",
            r"element 0 of tensors does not require grad",
            r"One of the differentiated Tensors appears to not have been used in the graph",
        ),
        card_title="x and t need requires_grad",
        card_body=(
            "To take u_x and u_t, autograd needs x and t marked as differentiable. "
            "Create the collocation points with requires_grad=True."
        ),
        diff_expected="x = x.clone().requires_grad_(True)\nt = t.clone().requires_grad_(True)",
        tags=("pinn", "pytorch"),
    ),
    FailureMode(
        id="git_squash_above_its_commit",
        name="Interactive rebase: squash/fixup placed above the commit whose code it edits",
        symptoms=(
            "During `git rebase -i`, a squash/fixup (or a reordered pick) stops with a CONFLICT in code "
            "that only a later commit introduces; after resolving and `git rebase --continue`, the next "
            "pick fails again (\"could not apply <sha>...\")."
        ),
        cause=(
            "A squash/fixup is applied on top of the commit directly above it in the todo list. Moved above "
            "the commit that creates the code it changes, its changes have nothing to apply to, and every "
            "manual resolution pushes the conflict into the next pick."
        ),
        fix=(
            "Don't resolve it commit by commit: `git rebase --abort`, run `git rebase -i` again, and put the "
            "squash/fixup line directly below the commit it amends (never `git add` + `--continue` while "
            "conflict markers remain)."
        ),
        citation_id="git_rebase_docs",
        code_patterns=(r"(?m)^(squash|fixup|s|f)\s+[0-9a-f]{7,}",),
        card_title="Squash sits above its parent commit",
        card_body=(
            "A squash folds into the commit right above it, but this one edits code a later commit creates, "
            "so it conflicts. Run git rebase --abort, then move the squash under that commit."
        ),
        tags=("git",),
    ),
)

BY_ID: dict[str, FailureMode] = {m.id: m for m in PLAYBOOK}

# guiding question (hint level 0) per entry: Socratic, about the cause, never the answer
GUIDING_QUESTIONS: dict[str, str] = {
    "git_squash_above_its_commit": "Which commit does a squash line fold into, and does that commit already contain the code it edits?",
    "pinn_missing_ic_bc": "Many functions satisfy the PDE. What information tells the network which one you want?",
    "pinn_convection_large_beta": "Large β is the hard version of this PDE. Could the network learn an easier β first and carry those weights forward?",
    "pinn_loss_imbalance": "Look at each loss term separately. Is one of them barely moving?",
    "missing_zero_grad": "What happens to .grad between two calls to loss.backward()?",
    "cuda_on_mac": "Which GPU does this laptop actually have, and what does PyTorch call it?",
    "lr_too_high": "What happens to Adam's steps when the learning rate is large compared with the curvature of the loss?",
    "pinn_inputs_no_grad": "How does autograd know it should track derivatives with respect to x and t?",
}


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
        if m.requires and not all(_search(p, code_excerpt) for p in m.requires):
            continue
        score = 0.0
        if m.error_patterns and any(_search(p, error_text) for p in m.error_patterns):
            score += 0.6
        hits = sum(_search(p, code_excerpt) for p in m.code_patterns) if m.code_patterns else 0
        if m.code_patterns:
            score += 0.3 * hits / len(m.code_patterns)
        # "X is missing" only means something in the entry's own context (PINN code, a training loop)
        if m.code_absent and code_excerpt and (hits or not m.code_patterns):
            # the thing this entry says is missing: absent → evidence for; present → evidence against
            score += 0.3 if all(not _search(p, code_excerpt) for p in m.code_absent) else -0.5
        if (m.metric_signals and flags & set(m.metric_signals)) or (m.context_signals and hits and flags & set(m.context_signals)):
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

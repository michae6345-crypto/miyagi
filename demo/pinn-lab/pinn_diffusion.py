"""PINN lab: the 1D diffusion equation, following Toscano's "Learning Physics Informed
Machine Learning Part 1 - PINNs" (https://www.youtube.com/watch?v=AXXnSzmpyoI).

    PDE:   y_t = y_xx - e^(-t) (sin(pi x) - pi^2 sin(pi x)),   x in [-1, 1],  t in [0, 1]
    IC/BC: y(x, 0) = sin(pi x),   y(-1, t) = y(1, t) = 0
    exact: y(x, t) = e^(-t) sin(pi x)

Fill in each section as the video goes; the overlay watches this file and your terminal.
Run it with:   python pinn_diffusion.py          (or: tut run python pinn_diffusion.py)
"""


def log_metric(step, name, value):
    """Machine-readable metric line (picked up by `tut run`)."""
    print(f'::metric:: {{"step": {step}, "name": "{name}", "value": {value}}}', flush=True)


def report(i, loss, test_loss=None):
    """Call this every few hundred training iterations."""
    line = f"step {i} | loss {loss:.4e}"
    if test_loss is not None:
        line += f" | test {test_loss:.4e}"
    print(line, flush=True)
    log_metric(i, "loss", loss)
    if test_loss is not None:
        log_metric(i, "test_loss", test_loss)


# =============================================================================
# 1. Libraries and setup
# =============================================================================
# TODO: import the deep-learning library, its autograd and nn modules, numpy,
#       and the Latin-hypercube sampler from the design-of-experiments package.
# TODO: make 32-bit floats the default, fix the random seeds, pick cpu or cuda.


# =============================================================================
# 2. Tuning parameters and the exact solution
# =============================================================================
# TODO: number of training iterations, learning rate, network layer sizes,
#       domain bounds, grid sizes, and how many boundary / collocation points.
# TODO: a function giving the exact solution at (x, t), evaluated on a meshgrid.


# =============================================================================
# 3. Test data: flatten the grid into (x, t) pairs
# =============================================================================
# TODO: stack the flattened grid into an N x 2 test input and an N x 1 target;
#       keep the lower and upper corners of the domain.


# =============================================================================
# 4. Training data: initial and boundary conditions
# =============================================================================
# TODO: points on t = 0 with their initial values, and on x = -1 / x = 1 with zeros;
#       stack them and pick a random subset as the boundary training set.


# =============================================================================
# 5. Collocation points
# =============================================================================
# TODO: sample interior points with the Latin-hypercube sampler, scaled to the
#       domain, add the boundary points, and move every tensor to the device.


# =============================================================================
# 6. The PINN
# =============================================================================
# TODO: a fully connected network class with tanh activations and three losses:
#       the boundary/initial-condition loss, the PDE residual loss (autograd for
#       the first and second derivatives), and their sum.


# =============================================================================
# 7. Train
# =============================================================================
# TODO: build the model and an Adam optimizer, then loop: loss, zero_grad,
#       backward, step. Every few hundred iterations call report(i, loss, test_loss).


# =============================================================================
# 8. Results
# =============================================================================
# TODO: evaluate on the test grid and plot prediction vs exact side by side.

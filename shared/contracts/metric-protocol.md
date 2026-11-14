# Metric line protocol

The learner runs their code through the wrapper: `tut run python pinn_convection.py`.
The wrapper passes stdout and stderr through untouched, and also parses any line that starts with `::metric::`:

```
::metric:: {"step": 1200, "name": "loss", "value": 0.2504}
::metric:: {"step": 1200, "name": "grad_norm/layer3", "value": 1.3e-4}
```

- `step` is an int (training step/epoch), `name` is a string (use `/` for groups), `value` is a float.
- The wrapper writes each metric to Tiger Data `training_metrics(time, run_id, step, name, value)` and to the engine, which forwards it as a `metric` event for live curves.
- The wrapper also records `run_id`, `command`, `exit_code`, start/end time and the last 200 lines of output into `runs`.
- The tutorial's own reference curve is stored as a run with `source='tutorial'` so curves can be compared.

Demo repos print these lines with a 1-line helper:
```python
def log_metric(step, name, value): print(f'::metric:: {{"step": {step}, "name": "{name}", "value": {value}}}', flush=True)
```

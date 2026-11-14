"""Run state the orchestrator accumulates from `tut run` ingest events.

`RunContext` matches what engine-internal.md says `checks.evaluate_step(step, ctx)` gets:
workdir, the last run (exit_code, output_tail) and metrics: dict[name, list[(step, value)]].
It exposes both flat attributes (ctx.exit_code) and a nested `last_run` so either
reading style works.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

OUTPUT_TAIL = 200


@dataclass
class RunInfo:
    run_id: str
    command: str = ""
    cwd: str = ""
    exit_code: int | None = None  # None while running
    output_tail: list[str] = field(default_factory=list)
    metrics: dict[str, list[tuple[int, float]]] = field(default_factory=dict)

    @property
    def running(self) -> bool:
        return self.exit_code is None

    def add_output(self, lines: list[str]) -> None:
        self.output_tail.extend(lines)
        if len(self.output_tail) > OUTPUT_TAIL:
            del self.output_tail[: len(self.output_tail) - OUTPUT_TAIL]

    def add_metric(self, step: int, name: str, value: float) -> None:
        self.metrics.setdefault(name, []).append((int(step), float(value)))


@dataclass
class RunContext:
    workdir: str
    last_run: RunInfo | None = None
    runs: list[RunInfo] = field(default_factory=list)  # all runs this step, oldest first

    @property
    def exit_code(self) -> int | None:
        return self.last_run.exit_code if self.last_run else None

    @property
    def output_tail(self) -> list[str]:
        return self.last_run.output_tail if self.last_run else []

    @property
    def command(self) -> str | None:
        return self.last_run.command if self.last_run else None

    @property
    def metrics(self) -> dict[str, list[tuple[int, float]]]:
        return self.last_run.metrics if self.last_run else {}

    @property
    def workpath(self) -> Path:
        return Path(self.workdir)


def metrics_summary(metrics: dict[str, list[tuple[int, float]]]) -> dict:
    out = {}
    for name, pts in metrics.items():
        if not pts:
            continue
        vals = [v for _, v in pts]
        out[name] = {
            "first": vals[0],
            "last": vals[-1],
            "min": min(vals),
            "last_step": pts[-1][0],
            "n": len(pts),
        }
    return out

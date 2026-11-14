"""Step checks (E3). See README.md in this folder."""
from .evaluator import (
    FILE_CHECK_TYPES,
    RUN_CHECK_TYPES,
    SCREEN_CHECK_TYPES,
    CheckResult,
    RunContext,
    StepGate,
    evaluate_check,
    evaluate_gate,
    evaluate_step,
    step_passed,
    trend_stats,
)
from .screen import extract_metrics, screen_text

__all__ = [
    "FILE_CHECK_TYPES",
    "RUN_CHECK_TYPES",
    "SCREEN_CHECK_TYPES",
    "CheckResult",
    "RunContext",
    "StepGate",
    "evaluate_check",
    "evaluate_gate",
    "evaluate_step",
    "extract_metrics",
    "screen_text",
    "step_passed",
    "trend_stats",
]

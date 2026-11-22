"""ReDoS guard for lesson patterns (server.safety.patterns) and every place the engine runs one. Offline."""
from __future__ import annotations

import re
import time

import pytest

from server.safety.patterns import pattern_problem, safe_compile, safe_search

# Review round 1: each of these was ACCEPTED by the first guard and stalled the engine for seconds
# ('(?:a?){30}a{30}' 13.5 s on 30 characters).
REVIEW_BYPASSES = [r"(?:a?){30}a{30}", r"(a{1,32}){1,32}$", r".*.*.*.*.*=", r"\s*\s*\s*\s*\s*x$",
                   r"\d+\.?\d*\.?\d*\.?\d*\.?\d*\.?\d*z", r"\w*\w*\w*!"]
CATASTROPHIC = REVIEW_BYPASSES + [
    r"(x+)+y", r"(a|aa)+$", r"(a|a?)+$", r"(\d+){3}", r"(a*)*$", r"(?:(?:a+)?)+", r"(\w+\s?)+$", r"(?:\s*\w*)+x",
    r"(?:x{1,9}){1,9}", r"(?:a|b|ab)+c", r"[\s\S]*[\s\S]*!", r".*.*=", r"\S*\S*x", r"(?s).*.*!",
    r".{0,500}.{0,500}.{0,500}!", r"abc.*.*.*=", r"(?i)[a-z]*[A-Z]*[a-z]*!",
]
# real lesson patterns (shipped demo lessons, eval lessons, engine metric patterns) that must keep working
LESSON_PATTERNS = [
    r"\d+\.?\d*", r"loss[=:]\s*(?P<value>\d+\.?\d*)", r"(\d{1,3}\.){3}\d{1,3}", r"def\s+\w+\s*\(",
    r"\[\s*-\s*1\.[0O]\s*,?\s*-?\s*[0O]\.[0O]\s*,?\s*1\.[0O]\s*\]", r"\d+/\d+\s*\S*\s*\d+ms/step|Epoch|ms/step",
    r"useEffect\(|\[\s*\]\s*\)\s*;?\s*\n?.*useEffect", r"print\(.*\)", r"(\w+\.)?\w+\(",
    r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?", r"Epoch\s+(?P<step>\d+).*loss[=:]\s*(?P<value>[\d.]+)",
    r"Usage:\s*\S+.*\[PATH\]", r"\bimport\s+numpy\s+as\s+np\b", r"name.{0,3}:.{0,3}\S+.{0,40}modified",
    r"\*\s*\S+[\s\S]{0,200}(main|master)|(main|master)[\s\S]{0,200}\*\s*\S+",
    r"h1\s*=\s*np\.tanh\(\s*X\s*(?:@\s*W1|\.dot\(\s*W1\s*\))\s*\+\s*b1\s*\)[\s\S]*h2\s*=",
    r"loss\s*=\s*np\.mean\(\s*\(\s*(?:out\s*-\s*y|y\s*-\s*out)\s*\)\s*\*\*\s*2\s*\)",
]


@pytest.mark.parametrize("pattern", CATASTROPHIC)
def test_catastrophic_patterns_are_refused(pattern):
    assert pattern_problem(pattern)
    with pytest.raises(re.error):
        safe_compile(pattern)


@pytest.mark.parametrize("pattern", LESSON_PATTERNS)
def test_lesson_patterns_still_run(pattern):
    assert pattern_problem(pattern) is None
    safe_compile(pattern, re.MULTILINE)


def test_ignorecase_widens_overlap():
    assert pattern_problem(r"[a-z]+[A-Z]+[a-z]+!") is None
    assert pattern_problem(r"[a-z]+[A-Z]+[a-z]+!", re.IGNORECASE)


def test_too_long_and_not_a_pattern():
    assert pattern_problem("a" * 401)
    assert pattern_problem(None)
    assert pattern_problem("(unclosed").startswith("invalid pattern")


def test_accepted_patterns_stay_fast_on_capped_text():
    """The text a pattern sees is capped (screen 4 KB, files 64 KB with 2 KB lines); accepted lesson patterns finish
    quickly on it, including text built from their own repeated characters."""
    from server.checks.evaluator import FILE_SCAN_CHARS, scan_text

    texts = [scan_text("x = 1\n" * 20000), scan_text(("    " * 30 + "\n") * 2000), scan_text("1/2 " * 20000),
             scan_text("a" * 100_000)]
    assert all(len(t) <= FILE_SCAN_CHARS * 1.15 for t in texts)  # long lines split with a 256-character overlap
    assert all(len(ln) <= 2048 for t in texts for ln in t.split("\n"))
    t0 = time.perf_counter()
    for p in LESSON_PATTERNS:
        for t in texts:
            safe_search(p, t, re.MULTILINE)
    assert time.perf_counter() - t0 < 5.0


# ---------------------------------------------------------------- every sink refuses one


BAD = r"(?:a?){30}a{30}"
TEXT = "a" * 30


def test_build_coverage_never_runs_one():
    from server.lesson import coverage

    assert coverage._spans(BAD, TEXT) == []


def test_build_lint_and_literal_check_never_run_one():
    from server.lesson import builder, schema

    assert schema._search(BAD, TEXT) is False
    assert builder.looks_like_literal(r"(?:a?){30}a{30}(x)") is True  # treated as not a working regex


def test_precision_and_venv_steps_never_run_one():
    from server.lesson import precision, venv_steps

    assert precision._regex_accepts(BAD, TEXT) is None
    assert venv_steps._pip_check({"type": "screen_contains", "pattern": BAD}) is False


def test_checks_screen_helpers_refuse_one():
    from server.checks import screen

    for fn in (screen.search_screen, screen.search_wrapped, screen.extract_metrics):
        with pytest.raises(re.error):
            fn(BAD, TEXT)


def test_screen_matcher_and_metrics_refuse_one():
    from server.screen import match, metrics

    assert match._as_regex(r"(?:a?){30}a{30}") is None
    with pytest.raises(re.error):
        metrics._local_extract_metrics(BAD, TEXT)


def test_notebook_coach_lesson_end_scaffold_and_anchor_skip_one():
    from server.orchestrator import lesson_end, nb_coach
    from server.orchestrator.workspace import anchor_line
    from server.workspace import scaffold

    step = {"checks": [{"type": "screen_contains", "pattern": BAD, "label": "x typed"}]}
    assert nb_coach.step_cells([{"type": "code", "source": TEXT}], step) == []

    class S:
        steps = [{"checks": [{"metric": "loss", "metric_pattern": r"(?P<value>(?:\d?){30}\d{30})"}]}]

    assert lesson_end._patterns(S()) == []
    assert scaffold._compile(BAD) is None
    assert anchor_line(TEXT, BAD) is None


def test_the_evaluator_refuses_one_and_caps_what_a_file_check_reads(tmp_path):
    from server.checks.evaluator import LINE_SCAN_CHARS, RunContext, evaluate_check, scan_text

    (tmp_path / "a.py").write_text(TEXT)
    r = evaluate_check({"id": "c", "type": "file_contains", "file": "a.py", "pattern": BAD, "label": "x"},
                       RunContext(workdir=str(tmp_path)))
    assert r["status"] == "fail" and "pattern" in r["detail"]
    big = "x = 0\n" * 30_000 + "needle = 1\n"
    (tmp_path / "big.py").write_text(big)
    r = evaluate_check({"id": "c", "type": "file_contains", "file": "big.py", "pattern": r"needle\s*=", "label": "x"},
                       RunContext(workdir=str(tmp_path)))
    assert r["status"] == "pass" and r["detail"] == "found in big.py:30001"  # line numbers survive the cap
    assert max(len(ln) for ln in scan_text("y" * 10_000 + "\nz").split("\n")) == LINE_SCAN_CHARS


def test_long_lines_are_split_with_overlap_never_cut_and_lines_map_back():
    from server.checks.evaluator import scan

    text = "a\n" + "x" * 5000 + "model.evaluate(" + "y" * 3000 + "\nlast = 1\n"
    sc = scan(text)
    m = re.search(r"model\.evaluate\(", sc.text)
    assert m and sc.line_of(m.start()) == 2
    assert sc.line_of(sc.text.index("last")) == 3
    assert max(len(ln) for ln in sc.text.split("\n")) <= 2048


def test_a_big_one_line_notebook_keeps_its_code_for_file_checks(tmp_path):
    import base64
    import json
    import os as _os

    from server.checks.evaluator import RunContext, evaluate_check

    png = base64.b64encode(_os.urandom(150_000)).decode()
    nb = {"cells": [{"cell_type": "code", "source": ["model.evaluate(test_images, test_labels)\n"],
                     "outputs": [{"output_type": "display_data", "data": {"image/png": png, "text/plain": ["<Fig>"]}}]},
                    {"cell_type": "code", "source": ["plt.show()\n"], "outputs": []}]}
    (tmp_path / "mnist.ipynb").write_text(json.dumps(nb))  # one line, ~200 KB
    r = evaluate_check({"id": "c", "type": "file_contains", "file": "mnist.ipynb", "label": "x",
                        "pattern": r"model\.evaluate\("}, RunContext(workdir=str(tmp_path)))
    assert r["status"] == "pass", r

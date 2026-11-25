"""Score link lessons (lessons from any link: a docs page, a blog tutorial, a GitHub README) on the saved pages in pages/.

Each case in cases/*.json is one link: the saved page, the URL it came from, and the outline a careful tutor expects:

    {"id": "python-venv", "url": "https://docs.python.org/3/tutorial/venv.html", "page": "python-venv.html",
     "status": 200,                       # optional: what the site answered (401 / 403 / 451 -> blocked)
     "expect": {
       "refusal": null,                   # or "not_teachable" | "blocked" | "no_content": the page must be refused
       "steps": [3, 8],                   # the built lesson's step count, inclusive
       "code": ["python3 -m venv tutorial-env", ...],  # one fragment per code block that must land in a step
       "never": ["python3 scene_tools.py"],  # a command or code no step may carry (optional)
       "title": "...", "site": "...", "author": "...",  # what link.preview shows (optional)
       "absent": ["Accept all cookies"],  # page chrome that must never reach the readable text
       "same_hash_as": "python-venv"      # the same page with other chrome: the same content hash / cache key
     },
     "notes": "why this case is here"}

Per case the runner reads the page (reader.read), asks the fake Haiku for the verdict (fake_model.verdict) and, for a
teachable page, builds the lesson through the engine's no-video build (server.lesson.textlesson.build_text_lesson, the
"Just teach me" path the contract builds link lessons on) with the fake model in place of Claude and the page in place
of the research notes. No network, no model call, no cost. Then it checks the expectations:

  verdict        the page is refused for the expected reason, or accepted
  built          a teachable page built a lesson that passes the lesson schema (schema_errors)
  steps          the step count is in range
  code           every expected fragment (whitespace-insensitive) is in some step's code or run command
  never          no step carries a `never` fragment (a bpy script run with python3, say)
  live           every step has code to type or a command to run (a step the engine emptied is a dead end)
  checked        every step that types code has at least one check, and so does every run step
  reader         title / site / author as expected, chrome absent from the text, same hash as its twin

Metrics (micro averages over the cases that have them) go to the report and to baseline.json; the pytest gate
(test_link_evals.py) fails when a metric drops below the baseline or a case that passed in the baseline fails.

    python -m server.evals.links                 # metrics + failing cases
    python -m server.evals.links -v              # plus every case
    python -m server.evals.links -k git          # only ids containing "git"
    python -m server.evals.links --json
    python -m server.evals.links --write-baseline
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
CASES_DIR = HERE / "cases"
PAGES_DIR = HERE / "pages"
BASELINE = HERE / "baseline.json"
REFUSALS = ("not_teachable", "blocked", "no_content")
METRICS = ("verdict_accuracy", "refusal_precision", "refusal_recall", "build_rate", "steps_in_range", "code_landed",
           "live_steps", "code_steps_checked", "run_steps_checked", "portable_checks", "reader_ok", "cases_passed")
# a check that asks for what only the page author's screen showed: their home folder, a commit id, a clock time, the
# exact version pip printed that day. It never passes on the learner's Mac (scored as a metric, not per case).
_BRITTLE = re.compile(r"/Users/|/home/|C:\\\\|(?<![0-9A-Za-z])(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}(?![0-9A-Za-z])|"
                      r"\d{1,2}:\d{2}:\d{2}|(?<![\d.])\d+\\?\.\d+\\?\.\d+(?!\\?\.\d)")  # (an IP address is not a version)
EPS = 1e-9


@dataclass
class Result:
    id: str
    expected_refusal: str | None
    refusal: str | None = None
    why: str = ""
    title: str = ""
    site: str = ""
    cache_key: str = ""
    content_hash: str = ""
    built: bool | None = None  # None: not built (refused)
    build_error: str = ""
    n_steps: int = 0
    steps_range: tuple[int, int] | None = None
    code_expected: int = 0
    code_landed: list[str] = field(default_factory=list)
    code_missed: list[str] = field(default_factory=list)
    never_found: list[str] = field(default_factory=list)
    dead_steps: list[str] = field(default_factory=list)  # steps with neither code nor a command: nothing to do
    checks: int = 0
    brittle_checks: list[str] = field(default_factory=list)
    code_steps: int = 0
    code_steps_checked: int = 0
    run_steps: int = 0
    run_steps_checked: int = 0
    reader_checks: list[tuple[str, bool, str]] = field(default_factory=list)  # (name, ok, detail)
    warnings: list[str] = field(default_factory=list)
    seconds: float = 0.0

    @property
    def verdict_ok(self) -> bool:
        return self.refusal == self.expected_refusal

    @property
    def steps_ok(self) -> bool | None:
        if not self.built or not self.steps_range:
            return None
        lo, hi = self.steps_range
        return lo <= self.n_steps <= hi

    def failures(self) -> list[str]:
        out = []
        if not self.verdict_ok:
            out.append(f"verdict: expected {self.expected_refusal or 'teachable'}, got {self.refusal or 'teachable'}"
                       + (f" ({self.why})" if self.why else ""))
        if self.expected_refusal is None and self.refusal is None:
            if not self.built:
                out.append(f"build failed: {self.build_error[:200]}")
            else:
                if self.steps_ok is False:
                    out.append(f"steps: {self.n_steps}, expected {self.steps_range[0]}-{self.steps_range[1]}")
                if self.code_steps_checked < self.code_steps:
                    out.append(f"checks: {self.code_steps - self.code_steps_checked} of {self.code_steps} code steps have none")
                if self.dead_steps:
                    out.append("steps with nothing to type or run: " + "; ".join(self.dead_steps))
                if self.run_steps_checked < self.run_steps:
                    out.append(f"checks: {self.run_steps - self.run_steps_checked} of {self.run_steps} run steps have none")
            if self.code_missed:
                out.append("code not in any step: " + "; ".join(repr(x) for x in self.code_missed))
            if self.never_found:
                out.append("a step carries what it never should: " + "; ".join(repr(x) for x in self.never_found))
        out += [f"reader {name}: {detail}" for name, ok, detail in self.reader_checks if not ok]
        return out

    @property
    def passed(self) -> bool:
        return not self.failures()


# ------------------------------------------------------------------ loading

def load_cases(k: str | None = None) -> list[dict]:
    cases = []
    for p in sorted(CASES_DIR.glob("*.json")):
        c = json.loads(p.read_text(encoding="utf-8"))
        c.setdefault("id", p.stem)
        if k and k not in c["id"]:
            continue
        cases.append(c)
    return cases


def page_text(case: dict) -> str:
    return (PAGES_DIR / case["page"]).read_text(encoding="utf-8")


# ------------------------------------------------------------------ one case

_PY = re.compile(r"(?<![\w./-])python(?![\w.])")


def _norm(s: str) -> str:
    return " ".join(str(s or "").split())


def _code_norm(s: str) -> str:
    """Whitespace collapsed, and `python` read as `python3` (the engine writes python3 on macOS: use_python3)."""
    return _PY.sub("python3", _norm(s))


def _step_text(st: dict) -> str:
    return _code_norm((st.get("code") or "") + "\n" + (st.get("run_command") or ""))


@contextlib.contextmanager
def _patched(fake, cache_dir: Path):
    """The fake model and research in place of Claude's, the lesson cache in a temp folder; restored after."""
    from server.lesson import builder, claude, textlesson

    saved = (claude._generate_json, textlesson.research, builder.CACHE_DIR, os.environ.get("LESSON_PYTHON"))
    claude._generate_json = fake.generate_json
    textlesson.research = fake.research
    builder.CACHE_DIR = cache_dir
    os.environ["LESSON_PYTHON"] = "python3"  # the same commands on every machine
    try:
        yield
    finally:
        claude._generate_json, textlesson.research, builder.CACHE_DIR, py = saved
        if py is None:
            os.environ.pop("LESSON_PYTHON", None)
        else:
            os.environ["LESSON_PYTHON"] = py


def build(page, fake=None) -> dict:
    """The lesson for a teachable page, through the engine's no-video build with the fake model. Raises on failure."""
    from server.lesson import textlesson

    from .fake_model import FakeModel

    fake = fake or FakeModel(page)
    with tempfile.TemporaryDirectory(prefix="link-eval-") as tmp:
        work = Path(tmp) / "work"
        work.mkdir()
        with _patched(fake, Path(tmp) / "cache"):
            return asyncio.run(textlesson.build_text_lesson(page.title or page.site, str(work), cache=False))


def run_case(case: dict, read=None, verdict=None, builder_fn=None) -> Result:
    """One case. `read`, `verdict` and `builder_fn` default to this package's reader, fake verdict and build: the engine
    lane can pass its own (read(text, url, kind, status=, fmt=) -> Page-like; verdict(page) -> {teachable, why};
    builder_fn(page) -> lesson graph)."""
    from server.lesson.schema import schema_errors

    from . import fake_model, reader

    read = read or reader.read
    verdict = verdict or fake_model.verdict
    builder_fn = builder_fn or build
    exp = case.get("expect") or {}
    t0 = time.time()
    r = Result(id=case["id"], expected_refusal=exp.get("refusal"))
    page = read(page_text(case), case["url"], case.get("kind", ""), status=int(case.get("status", 200)),
                fmt="md" if case["page"].endswith(".md") else "html")
    r.title, r.site = page.title, page.site
    r.content_hash, r.cache_key = page.content_hash, page.cache_key
    if page.refusal:
        r.refusal = page.refusal
    else:
        v = verdict(page)
        r.why = v.get("why", "")
        if not v.get("teachable"):
            r.refusal = "not_teachable"
    # reader expectations
    for key in ("title", "site", "author"):
        if key in exp:
            got = getattr(page, key, "")
            r.reader_checks.append((key, _norm(got) == _norm(exp[key]), f"expected {exp[key]!r}, got {got!r}"))
    for s in exp.get("absent") or []:
        r.reader_checks.append(("absent", s.lower() not in page.text.lower(), f"page chrome {s!r} is in the readable text"))
    if r.refusal is None and r.expected_refusal is None:
        r.steps_range = tuple(exp["steps"]) if exp.get("steps") else None
        r.code_expected = len(exp.get("code") or [])
        try:
            g = builder_fn(page)
            errs = schema_errors(g)
            if errs:
                raise RuntimeError("schema: " + "; ".join(errs[:3]))
            r.built = True
        except Exception as e:  # noqa: BLE001  a failed build is a scored outcome
            r.built, r.build_error, g = False, f"{type(e).__name__}: {e}", {"steps": []}
        steps = g.get("steps") or []
        r.n_steps = len(steps)
        r.warnings = list((g.get("build") or {}).get("warnings") or [])
        texts = [_step_text(st) for st in steps]
        for frag in exp.get("code") or []:
            (r.code_landed if any(_code_norm(frag) in t for t in texts) else r.code_missed).append(frag)
        r.never_found = [frag for frag in exp.get("never") or [] if any(_code_norm(frag) in t for t in texts)]
        for st in steps:
            for c in (st.get("checks") or []) + (st.get("precision_checks") or []):
                r.checks += 1
                pat = str(c.get("pattern") or "") + " " + str(c.get("command") or "")
                if _BRITTLE.search(pat):
                    r.brittle_checks.append(f"{st.get('id')}: {pat.strip()[:80]}")
            is_run = bool((st.get("run_command") or "").strip()) and (st.get("code") or "").strip() in ("", st["run_command"].strip())
            has_code = bool((st.get("code") or "").strip())
            if is_run:
                r.run_steps += 1
                r.run_steps_checked += bool(st.get("checks"))
            elif has_code:
                r.code_steps += 1
                r.code_steps_checked += bool(st.get("checks"))
            else:
                r.dead_steps.append(f"{st.get('id')} {st.get('title')!r}")
    elif r.expected_refusal is None and exp.get("code"):  # refused by mistake: its code never landed
        r.code_expected = len(exp["code"])
        r.code_missed = list(exp["code"])
    r.seconds = round(time.time() - t0, 2)
    return r


def _twin_checks(cases: list[dict], results: list[Result]) -> None:
    by_id = {r.id: r for r in results}
    for c in cases:
        twin = (c.get("expect") or {}).get("same_hash_as")
        if not twin:
            continue
        r = by_id[c["id"]]
        other = by_id.get(twin)
        if other is None:
            r.reader_checks.append(("same_hash_as", False, f"twin case {twin!r} not run (use -k on both)"))
            continue
        r.reader_checks.append(("same_hash_as", r.content_hash == other.content_hash,
                                f"content hash differs from {twin}: the page's chrome reached the readable text"))
        r.reader_checks.append(("same_cache_key", r.cache_key == other.cache_key, f"cache key differs from {twin}"))


# ------------------------------------------------------------------ scoring

def _ratio(n: int, d: int) -> float | None:
    return round(n / d, 4) if d else None


def score(results: list[Result]) -> dict[str, Any]:
    refused = [r for r in results if r.refusal]
    should = [r for r in results if r.expected_refusal]
    teach = [r for r in results if r.expected_refusal is None and r.refusal is None]
    built = [r for r in teach if r.built]
    ranged = [r for r in built if r.steps_ok is not None]
    reader = [ok for r in results for _, ok, _ in r.reader_checks]
    return {
        "cases": len(results),
        "verdict_accuracy": _ratio(sum(r.verdict_ok for r in results), len(results)),
        "refusal_precision": _ratio(sum(r.refusal == r.expected_refusal for r in refused), len(refused)),
        "refusal_recall": _ratio(sum(r.refusal == r.expected_refusal for r in should), len(should)),
        "build_rate": _ratio(len(built), len(teach)),
        "steps_in_range": _ratio(sum(bool(r.steps_ok) for r in ranged), len(ranged)),
        "code_landed": _ratio(sum(len(r.code_landed) for r in results), sum(r.code_expected for r in results)),
        "live_steps": _ratio(sum(r.n_steps - len(r.dead_steps) for r in built), sum(r.n_steps for r in built)),
        "code_steps_checked": _ratio(sum(r.code_steps_checked for r in built), sum(r.code_steps for r in built)),
        "run_steps_checked": _ratio(sum(r.run_steps_checked for r in built), sum(r.run_steps for r in built)),
        "portable_checks": _ratio(sum(r.checks - len(r.brittle_checks) for r in built), sum(r.checks for r in built)),
        "reader_ok": _ratio(sum(reader), len(reader)),
        "cases_passed": _ratio(sum(r.passed for r in results), len(results)),
        "code_fragments": sum(r.code_expected for r in results),
        "passed": sorted(r.id for r in results if r.passed),
        "failed": sorted(r.id for r in results if not r.passed),
    }


def run_all(k: str | None = None, **kw) -> tuple[dict, list[Result]]:
    cases = load_cases(k)
    results = [run_case(c, **kw) for c in cases]
    _twin_checks(cases, results)
    return score(results), results


def baseline_from(summary: dict) -> dict:
    return {"metrics": {m: summary[m] for m in METRICS}, "cases": summary["cases"], "passed": summary["passed"],
            "note": "written by python -m server.evals.links --write-baseline; the pytest gate fails below these"}


def regressions(summary: dict, base: dict) -> list[str]:
    """What got worse than the baseline: a metric below it, or a case that passed there failing now."""
    out = []
    for m, b in (base.get("metrics") or {}).items():
        now = summary.get(m)
        if b is not None and (now is None or now < b - EPS):
            out.append(f"{m}: {now} < baseline {b}")
    gone = sorted(set(base.get("passed") or []) & set(summary["failed"]))
    out += [f"case {cid} passed in the baseline and fails now" for cid in gone]
    return out


# ------------------------------------------------------------------ report

def _fmt(v) -> str:
    return "n/a" if v is None else f"{v:.3f}"


def report(summary: dict, results: list[Result], *, verbose: bool = False, base: dict | None = None) -> str:
    lines = [f"link lesson evals: {summary['cases']} cases, {summary['code_fragments']} code fragments (fake model, offline)"]
    for m in METRICS:
        b = ((base or {}).get("metrics") or {}).get(m)
        lines.append(f"  {m:20s} {_fmt(summary[m])}" + (f"   (baseline {_fmt(b)})" if base else ""))
    bad = [r for r in results if not r.passed]
    if bad:
        lines.append("")
        lines.append(f"failing cases ({len(bad)}):")
        for r in bad:
            lines.append(f"- {r.id}")
            lines += [f"    {f}" for f in r.failures()]
    if verbose:
        lines.append("")
        lines.append("all cases:")
        for r in results:
            state = "refused " + r.refusal if r.refusal else (f"{r.n_steps} steps" if r.built else "build failed")
            lines.append(f"  {'ok  ' if r.passed else 'FAIL'} {r.id:32s} {state:24s} code {len(r.code_landed)}/{r.code_expected}"
                         f"  title={r.title!r}  {r.seconds:.2f}s")
            for b in r.brittle_checks[:4]:
                lines.append(f"         brittle check: {b}")
            for w in r.warnings[:6]:
                lines.append(f"         warning: {w[:160]}")
    if base is not None:
        reg = regressions(summary, base)
        lines.append("")
        lines.append("regressions vs baseline: " + ("none" if not reg else ""))
        lines += [f"  {x}" for x in reg]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    import argparse
    import logging

    ap = argparse.ArgumentParser(prog="python -m server.evals.links", description=__doc__.split("\n\n")[0])
    ap.add_argument("-k", help="only cases whose id contains this")
    ap.add_argument("-v", "--verbose", action="store_true", help="list every case")
    ap.add_argument("--json", action="store_true", help="print the summary as JSON")
    ap.add_argument("--write-baseline", action="store_true", help=f"write {BASELINE.name} from this run")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.ERROR)
    summary, results = run_all(a.k)
    base = json.loads(BASELINE.read_text(encoding="utf-8")) if BASELINE.is_file() else None
    if a.write_baseline:
        if a.k:
            print("--write-baseline needs the whole set (no -k)", file=sys.stderr)
            return 2
        BASELINE.write_text(json.dumps(baseline_from(summary), indent=2) + "\n", encoding="utf-8")
        print(f"wrote {BASELINE}")
    if a.json:
        print(json.dumps({**summary, "results": [{"id": r.id, "passed": r.passed, "failures": r.failures()}
                                                 for r in results]}, indent=2))
    else:
        print(report(summary, results, verbose=a.verbose, base=None if a.k else base))
    return 0 if base is None or a.k or not regressions(summary, base) else 1


if __name__ == "__main__":
    sys.exit(main())

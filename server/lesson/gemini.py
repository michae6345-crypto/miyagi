"""Gemini calls: watch the video (pass 1 + per-step detail) and adapt checks (pass 2)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", category=SyntaxWarning)  # SDK docstring escapes

from google import genai
from google.genai import types

from .schema import ADAPTED_SCHEMA, DETAIL_SCHEMA, VIDEO_DRAFT_SCHEMA, standard_outputs_for_prompt

log = logging.getLogger("server.lesson")

# Override with LESSON_MODEL / LESSON_FAST_MODEL. Video pass wants the strongest
# video model; the per-step detail and adapt passes are cheaper.
DEFAULT_MODEL = "gemini-4-hydrogen"
DEFAULT_FAST_MODEL = "gemini-3.8-flash"


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    root = Path(__file__).resolve().parents[2]
    candidates = [Path(p) for p in [os.environ.get("TUT_ENV")] if p] + [root / ".env"]
    # inside a worktree (<main>/.claude/worktrees/<name>) also try the main checkout
    if root.parent.name == "worktrees" and root.parent.parent.name == ".claude":
        candidates.append(root.parents[2] / ".env")
    for p in candidates:
        if p.is_file():
            load_dotenv(p, override=False)


_clients: dict[str, genai.Client] = {}
_override_key: str | None = None  # bring-your-own-key from the app (config.keys.gemini)


def set_api_key(key: str | None) -> None:
    """Use this key instead of .env (the orchestrator forwards config.keys.gemini). Never logged."""
    global _override_key
    _override_key = key or None


def client() -> genai.Client:
    _load_env()
    key = _override_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not set (app settings, or .env at the repo root / $TUT_ENV)")
    if key not in _clients:
        _clients[key] = genai.Client(api_key=key)
    return _clients[key]


def model(fast: bool = False) -> str:
    _load_env()
    if fast:
        return os.environ.get("LESSON_FAST_MODEL", DEFAULT_FAST_MODEL)
    return os.environ.get("LESSON_MODEL", DEFAULT_MODEL)


YOUTUBE_ID = re.compile(r"(?:v=|youtu\.be/|/shorts/|/embed/|/live/)([\w-]{11})")


def youtube_id(url: str) -> str | None:
    m = YOUTUBE_ID.search(url)
    return m.group(1) if m else None


def _video_part(url: str, start: float | None = None, end: float | None = None, fps: float | None = None) -> types.Part:
    meta = None
    if start is not None or end is not None or fps is not None:
        meta = types.VideoMetadata(
            start_offset=f"{int(start)}s" if start is not None else None,
            end_offset=f"{int(end)}s" if end is not None else None,
            fps=fps,
        )
    return types.Part(file_data=types.FileData(file_uri=url), video_metadata=meta)


def fallback_models() -> list[str]:
    """Tried in order when a model is overloaded (503) or out of quota (free tier: per-model daily caps)."""
    _load_env()
    raw = os.environ.get("LESSON_FALLBACK_MODELS", "gemini-3.7-flash,gemini-3.6-flash,gemini-3.5-flash")
    return [m.strip() for m in raw.split(",") if m.strip()]


last_model: str | None = None  # model that served the most recent successful call (for build.model)
_RETRY_IN = re.compile(r"retry in ([\d.]+)s", re.I)
MAX_RATE_WAIT_S = 45.0
_exhausted: set[str] = set()  # models whose daily quota is gone, skipped for the rest of the process


def _classify(e: Exception) -> tuple[str, float]:
    """-> (kind, wait_seconds). kind: 'daily'/'gone' (skip model), 'rate' (wait, same model), 'busy', 'other'."""
    msg = str(e)
    code = getattr(e, "code", None)
    if code in (401, 403) or "PERMISSION_DENIED" in msg or "UNAUTHENTICATED" in msg or "API_KEY_INVALID" in msg:
        return "auth", 0.0
    if code == 404 or "NOT_FOUND" in msg:
        return "gone", 0.0
    if code == 429 or "RESOURCE_EXHAUSTED" in msg:
        if "PerDay" in msg or "per day" in msg.lower():
            return "daily", 0.0
        m = _RETRY_IN.search(msg)
        return "rate", float(m.group(1)) + 1 if m else 20.0
    if code in (500, 503) or "UNAVAILABLE" in msg:
        return "busy", 3.0
    return "other", 2.0


async def _generate_json(model_id: str, parts: list[types.Part], schema: dict, *, system: str, media_low: bool = False, retries: int = 2) -> dict:
    cfg = types.GenerateContentConfig(
        system_instruction=system,
        response_mime_type="application/json",
        response_json_schema=schema,
        temperature=0.2,
        media_resolution=types.MediaResolution.MEDIA_RESOLUTION_LOW if media_low else None,
    )
    chain = [m for m in dict.fromkeys([model_id, *fallback_models()]) if m not in _exhausted]
    last: Exception | None = None
    for mid in chain:
        for attempt in range(retries + 1):
            try:
                resp = await client().aio.models.generate_content(model=mid, contents=types.Content(role="user", parts=parts), config=cfg)
                if mid != model_id:
                    log.warning("used fallback model %s (wanted %s)", mid, model_id)
                out = json.loads(resp.text or "")
                global last_model
                last_model = mid
                return out
            except json.JSONDecodeError as e:
                last = e
                continue
            except Exception as e:  # noqa: BLE001  network / 429 / 5xx
                last = e
                kind, wait = _classify(e)
                if kind == "auth":  # bad/blocked key: every model will fail the same way
                    raise RuntimeError(f"Gemini rejected the API key: {str(e)[:200]}") from e
                if kind in ("daily", "gone"):
                    _exhausted.add(mid)
                    log.warning("%s: %s, trying next model", mid, "daily quota exhausted" if kind == "daily" else "model not available")
                    break
                if kind == "rate" and wait > MAX_RATE_WAIT_S:
                    break
                if kind == "busy" and attempt == retries:
                    break
                await asyncio.sleep(wait * (1 if kind == "rate" else attempt + 1))
    raise RuntimeError(f"Gemini call failed on {chain}: {str(last)[:300]}") from last


# --------------------------------------------------------------------------- #
# Pass 1: watch the whole video
# --------------------------------------------------------------------------- #

STACK_GUIDE = """Fit the checks to the tutorial's stack: grade what that stack visibly produces.
- Web / React / JS: the component or function in the editor (app "Code"), the dev server line in the
  terminal (e.g. "Local:\\s+http://localhost:\\d+"), text the page renders in the browser (app "Google Chrome"
  or "Safari"), and test-runner counts as a metric (metric "tests_passed", metric_pattern
  "(?P<value>\\d+)\\s+passed").
- git / shell / CLI tools: the command's own terminal output, e.g. `git log --oneline` lines
  "[0-9a-f]+\\s+<commit message>", "On branch \\S+", "Switched to branch", "Initialized empty Git repository".
- Data / pandas / notebooks: printed results such as a DataFrame's header row of column names, ".shape" output
  "\\(\\d+,\\s*\\d+\\)", "dtype: \\w+", or a printed statistic as a metric.
- ML / training: per-epoch or per-step lines (loss, accuracy, val metrics) as metric checks with metric_pattern.
- Anything else: the most distinctive thing the step makes appear on screen (output text, a file name in the
  editor tab, a UI label), never a judgement call.
Identifiers that only exist in the tutorial's off-camera starting code (constants like DEFAULT_USER, routes the
learner never wrote in an earlier step) are demo literals too: precision_checks only.
Every step needs at least one check that passes for ANY learner doing the step with their own names and data:
tool output ("Successfully rebased", "CONFLICT", "RangeIndex: \\d+ entries", "Compiled successfully", "Finished")
or API/keyword names ("useState\\(", "groupby\\(", "@app\\.get"). Literals that only exist in the tutorial's demo
(its branch names, usernames, dataset values, commit messages) go in precision_checks, never as the only check.
A Terminal check must match the command's OUTPUT, never the command the learner types (that passes on typing):
for a step that runs something, include one check on what it prints ("Local:\\s+http", "Uvicorn running on",
"Finished", a test count). Standard output lines you can use as-is:
""" + standard_outputs_for_prompt()


WATCH_SYSTEM = """You turn a coding tutorial video into an auto-graded lab.
A learner codes along in their own project; the video pauses at the end of each step
until machine-checkable checks pass. Be precise about timestamps and about what code is
actually written on screen. Never invent steps the video does not show."""

WATCH_PROMPT = """Learner's goal: {goal}

Break this tutorial into 4-10 sequential steps a learner can code along with.
Rules:
- One step = one concrete thing the learner builds or runs (e.g. "Create the Counter component", "Add the fetch call", "Commit the first change", "Define the model", "Run the tests"). Skip intros, outros, sponsor segments and pure theory unless they end in code or a command. A step shorter than ~20 s belongs to its neighbour.
- Each step's instructions state any state it depends on that no earlier step created (e.g. "first make two commits on main that change the same line"), so a learner who follows only the instructions gets there.
- The lesson must be playable from an EMPTY folder: if the tutorial starts from code, data or repo state prepared off camera, step 1 sets it up (the link from the description, or exact commands to recreate it, e.g. git init + branches + the conflicting commits, or creating/downloading the CSV).
- start/end are MM:SS (or H:MM:SS). end is the moment the step's code is complete or its run finished. Steps must not overlap and must be in order.
- title: imperative, at most 6 words. instructions: at most 2 sentences, concrete.
- code: transcribe the key lines written in the step exactly as on screen (keep variable names).
- checks: machine-checkable from the learner's SCREEN (on-device OCR of their editor, terminal and browser). Use
  * screen_contains with app "Code" (editor) and a SHORT regex (< 60 chars) for a distinctive fragment of
    the step's code, tolerant to OCR spacing, e.g. "useState\\(" or "def\\s+handler" or "git\\s+commit\\s+-m",
  * screen_contains with app "Terminal" (or the browser) for output the step should produce,
    e.g. "Compiled successfully", "\\d+ passed", "\\[main \\w+\\]", "Listening on",
  * screen_absent with app "Terminal" and pattern "Traceback|Error:|ERR!" for "it runs",
  * metric_threshold / metric_trend for any number the tutorial prints and the learner should reach
    (loss, accuracy, tests passed, build time, latency, error count...), with a metric_pattern: a regex
    with a named group value (and step when the number is printed per step/epoch/iteration) that parses
    the line EXACTLY as the video's code prints it (copy the print format into expected_output).
    Thresholds: values the tutorial's own run clearly reaches.
  Never use a "visual" check. Every step needs at least one check.
  {stack_guide}
- targets: where the learner should look/edit: app ("Code"/"Terminal"), file, and `match` = a short literal
  substring that will be visible on screen, e.g. "function TodoList" or "git merge", plus a caption.
- explanations: moments (MM:SS) where the presenter explains a concept relevant to the step.
- hints: a ladder of 2-4 hints, gentlest first (a guiding question -> a pointer -> nearly the answer).
- common_mistakes: concrete mistakes learners make in this step (e.g. forgetting to export the component, committing before staging, mutating a DataFrame copy, skipping optimizer.zero_grad()).
- libraries: every library used, with the version if shown (pip output, requirements, import of a versioned API); otherwise your best estimate from the API style and upload date, e.g. "react": "18.x".
"""


async def watch_video(url: str, goal: str, *, fps: float | None = None, context: str = "") -> dict:
    # 0.5 fps halves the frames of the default 1 fps; long videos otherwise miss the 45 s cap
    fps = fps if fps is not None else float(os.environ.get("LESSON_GEMINI_FPS", "0.5"))
    prompt = WATCH_PROMPT.format(goal=goal, stack_guide=STACK_GUIDE)
    if context:  # title/description/chapters: the video alone never shows the repo/data links
        prompt += "\n\nAbout this video (from its YouTube page):\n" + context
    parts = [_video_part(url, fps=fps), types.Part(text=prompt)]
    return await _generate_json(model(), parts, VIDEO_DRAFT_SCHEMA, system=WATCH_SYSTEM)


# --------------------------------------------------------------------------- #
# Pass 1b: per-step detail. Clip to the step and sample more frames so the
# on-screen code is legible (default sampling is 1 fps).
# --------------------------------------------------------------------------- #

DETAIL_PROMPT = """This clip is one step of a coding tutorial: "{title}".
Transcribe exactly the code visible in the editor/notebook at the END of the clip that
belongs to this step (keep the presenter's variable names and file name). Also give the
command run, any training/progress lines printed (verbatim, they are parsed by regex),
the names of values printed during training, and any library versions shown."""


async def step_detail(url: str, start: float, end: float, title: str, *, fps: float = 2.0) -> dict:
    parts = [_video_part(url, start=start, end=end, fps=fps), types.Part(text=DETAIL_PROMPT.format(title=title))]
    return await _generate_json(model(fast=True), parts, DETAIL_SCHEMA, system=WATCH_SYSTEM)


# --------------------------------------------------------------------------- #
# Pass 2: adapt checks to the learner's real workdir (text only, cheap)
# --------------------------------------------------------------------------- #

ADAPT_SYSTEM = """You write executable checks for an auto-graded coding lab. The engine reads
the learner's SCREEN with on-device OCR (Apple Vision) and evaluates checks literally:
- `checks` (screen-first, graded from the screen in any setup):
  * screen_contains / screen_absent: Python regex (re.search) over the OCR text of windows of `app`
    ("Code" = editor, "Terminal" = terminal). OCR drops/merges spaces and may misread quotes, so match a
    SHORT distinctive fragment (< 60 chars) with \\s* between tokens, avoid quotes, ^/$ anchors and long literals.
    Use screen_absent app "Terminal" pattern "Traceback|Error" for "the script runs".
  * metric_threshold / metric_trend with `metric` (a name) and `metric_pattern`: a regex with a named group
    (?P<value>...) (plus (?P<step>...) when the number is printed per step/epoch/iteration; required for
    metric_trend) that matches ONE printed line (training loss, accuracy, "Tests: 12 passed", build time,
    latency) exactly as the learner's code prints it (for ::metric:: JSON lines, match the JSON keys).
- `precision_checks` (backup, only when the workdir is known): file_contains / file_exists with paths relative
  to the workdir, command_exit_ok with a quick command that exists (small --epochs/--steps flag), metric_* by
  the ::metric:: name the code prints.
Never emit "visual".
"""
ADAPT_SYSTEM += STACK_GUIDE

ADAPT_PROMPT = """Learner's goal: {goal}

Tutorial steps (from the video), with the tutorial's own code, printed output and draft checks:
{steps}

The learner's workdir:
{workdir}

For EVERY step (keep the same `index`), write `checks` (screen-first, at least one per step), `precision_checks`
(file/command backups; empty list if the workdir is unknown) and `targets` (app + short on-screen `match`
substring + caption; include `file` when known). Use the learner's real names where they differ from the tutorial.
Keep labels <= 6 words. You may tighten `instructions` to mention the learner's file/function names (<= 2 sentences).
{feedback}"""


def adapt_prompt(goal: str, draft_steps: list[dict], workdir_summary: str, feedback: list[str] | None = None) -> str:
    fb = ""
    if feedback:
        fb = "\nYour previous answer had these problems; fix all of them:\n- " + "\n- ".join(feedback[:40])
    steps_txt = json.dumps(
        [
            {k: s.get(k) for k in ("index", "title", "instructions", "file", "code", "run_command", "expected_output", "terminal_output", "checks", "targets")}
            for s in draft_steps
        ],
        indent=1,
    )
    return ADAPT_PROMPT.format(goal=goal, steps=steps_txt, workdir=workdir_summary, feedback=fb)


async def adapt_checks(goal: str, draft_steps: list[dict], workdir_summary: str, feedback: list[str] | None = None) -> dict:
    prompt = adapt_prompt(goal, draft_steps, workdir_summary, feedback)
    return await _generate_json(model(fast=True), [types.Part(text=prompt)], ADAPTED_SCHEMA, system=ADAPT_SYSTEM)

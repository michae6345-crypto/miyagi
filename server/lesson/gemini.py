"""Gemini calls: watch the video (pass 1 + per-step detail) and adapt checks (pass 2)."""

from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path

from google import genai
from google.genai import types

from .schema import ADAPTED_SCHEMA, DETAIL_SCHEMA, VIDEO_DRAFT_SCHEMA

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
    candidates = [root / ".env"]
    # inside a worktree (<main>/.claude/worktrees/<name>) also try the main checkout
    if root.parent.name == "worktrees" and root.parent.parent.name == ".claude":
        candidates.append(root.parents[2] / ".env")
    for p in candidates:
        if p.is_file():
            load_dotenv(p, override=False)


_client: genai.Client | None = None


def client() -> genai.Client:
    global _client
    if _client is None:
        _load_env()
        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY is not set (put it in .env at the repo root)")
        _client = genai.Client(api_key=key)
    return _client


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


async def _generate_json(model_id: str, parts: list[types.Part], schema: dict, *, system: str, media_low: bool = False, retries: int = 2) -> dict:
    cfg = types.GenerateContentConfig(
        system_instruction=system,
        response_mime_type="application/json",
        response_json_schema=schema,
        temperature=0.2,
        media_resolution=types.MediaResolution.MEDIA_RESOLUTION_LOW if media_low else None,
    )
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = await client().aio.models.generate_content(model=model_id, contents=types.Content(role="user", parts=parts), config=cfg)
            text = resp.text or ""
            return json.loads(text)
        except json.JSONDecodeError as e:
            last = e
        except Exception as e:  # network / 429 / 5xx: back off and retry
            last = e
            await asyncio.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Gemini call failed after {retries + 1} attempts: {last}") from last


# --------------------------------------------------------------------------- #
# Pass 1: watch the whole video
# --------------------------------------------------------------------------- #

WATCH_SYSTEM = """You turn a coding tutorial video into an auto-graded lab.
A learner codes along in their own project; the video pauses at the end of each step
until machine-checkable checks pass. Be precise about timestamps and about what code is
actually written on screen. Never invent steps the video does not show."""

WATCH_PROMPT = """Learner's goal: {goal}

Break this tutorial into 4-10 sequential steps a learner can code along with.
Rules:
- One step = one concrete thing the learner builds or runs (e.g. "Define the MLP", "Compute the PDE residual with autograd", "Write the training loop", "Train and watch the loss drop"). Skip intros, outros, sponsor segments and pure theory unless they end in code.
- start/end are MM:SS (or H:MM:SS). end is the moment the step's code is complete or its run finished. Steps must not overlap and must be in order.
- title: imperative, at most 6 words. instructions: at most 2 sentences, concrete.
- code: transcribe the key lines written in the step exactly as on screen (keep variable names).
- checks: machine-checkable only. Prefer
  * file_contains with a Python regex that matches the essential code but tolerates whitespace and naming variations (e.g. r"torch\\.autograd\\.grad\\(" or r"nn\\.Linear\\(\\s*\\w+\\s*,"),
  * command_exit_ok for "the script runs" (e.g. "python pinn.py --epochs 1"),
  * metric_threshold / metric_trend for training steps, using the loss values the video shows (be conservative: a threshold the tutorial's own run clearly reaches),
  * output_contains for printed results.
  Never use a "visual" check. Every step needs at least one check.
- targets: where the learner should look/edit (file + a regex or substring for the block, e.g. "def pde_residual" + caption).
- explanations: moments (MM:SS) where the presenter explains a concept relevant to the step.
- hints: a ladder of 2-4 hints, gentlest first (a guiding question -> a pointer -> nearly the answer).
- common_mistakes: concrete mistakes learners make in this step (e.g. forgetting requires_grad=True on inputs, create_graph=True for second derivatives).
- libraries: every library used, with the version if shown (pip output, requirements, import of a versioned API); otherwise your best estimate from the API style and upload date, e.g. "torch": "2.x".
"""


async def watch_video(url: str, goal: str, *, fps: float | None = None) -> dict:
    parts = [_video_part(url, fps=fps), types.Part(text=WATCH_PROMPT.format(goal=goal))]
    return await _generate_json(model(), parts, VIDEO_DRAFT_SCHEMA, system=WATCH_SYSTEM)


# --------------------------------------------------------------------------- #
# Pass 1b: per-step detail. Clip to the step and sample more frames so the
# on-screen code is legible (default sampling is 1 fps).
# --------------------------------------------------------------------------- #

DETAIL_PROMPT = """This clip is one step of a coding tutorial: "{title}".
Transcribe exactly the code visible in the editor/notebook at the END of the clip that
belongs to this step (keep the presenter's variable names and file name). Also list the
command run, the names of values printed during training, and any library versions shown."""


async def step_detail(url: str, start: float, end: float, title: str, *, fps: float = 2.0) -> dict:
    parts = [_video_part(url, start=start, end=end, fps=fps), types.Part(text=DETAIL_PROMPT.format(title=title))]
    return await _generate_json(model(fast=True), parts, DETAIL_SCHEMA, system=WATCH_SYSTEM)


# --------------------------------------------------------------------------- #
# Pass 2: adapt checks to the learner's real workdir (text only, cheap)
# --------------------------------------------------------------------------- #

ADAPT_SYSTEM = """You write executable checks for an auto-graded coding lab. A checks engine
evaluates them literally, so every check must be runnable as written:
- file / command paths are relative to the learner's workdir;
- file_contains patterns are Python regexes (re.search, MULTILINE) that match the learner's
  actual code style, not the tutorial's variable names when they differ;
- metric names must be ones the learner's code prints via ::metric:: lines;
- command_exit_ok commands must exist in the workdir and finish quickly (use a small
  --epochs/--steps flag if the script has one)."""

ADAPT_PROMPT = """Learner's goal: {goal}

Tutorial steps (from the video), with the tutorial's own code and draft checks:
{steps}

The learner's workdir:
{workdir}

For EVERY step (keep the same `index`), rewrite `checks` and `targets` so they run against
this workdir. Keep the intent of each check. Use the real file names, function names and
metric names above. If the workdir is empty, use the tutorial's file names and the metric
name "loss". Keep check labels <= 6 words. You may tighten `instructions` to mention the
learner's file/function names (<= 2 sentences). No "visual" checks.
{feedback}"""


async def adapt_checks(goal: str, draft_steps: list[dict], workdir_summary: str, feedback: list[str] | None = None) -> dict:
    fb = ""
    if feedback:
        fb = "\nYour previous answer had these problems; fix all of them:\n- " + "\n- ".join(feedback[:40])
    steps_txt = json.dumps(
        [
            {k: s.get(k) for k in ("index", "title", "instructions", "file", "code", "run_command", "expected_output", "checks", "targets")}
            for s in draft_steps
        ],
        indent=1,
    )
    prompt = ADAPT_PROMPT.format(goal=goal, steps=steps_txt, workdir=workdir_summary, feedback=fb)
    return await _generate_json(model(fast=True), [types.Part(text=prompt)], ADAPTED_SCHEMA, system=ADAPT_SYSTEM)

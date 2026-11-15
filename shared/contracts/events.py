"""Python mirror of shared/contracts/events.ts (App <-> Engine WebSocket protocol).

Every message is JSON: {"type": <string>, "payload": <object>}.
RULE: add fields freely; never rename or remove one without a `contract:` PR + a ping.
Keep this file in sync with events.ts. Models allow extra fields so additive changes
on either side never break validation.

Usage:
    from shared.contracts.events import engine_message, parse_app_message
    msg = engine_message("step.passed", {"stepId": "s1", "nextStepId": "s2"})  # -> dict, validated
    cmd = parse_app_message(raw_json_dict)  # -> AppMessage(type, payload model)
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

# ---------- shared shapes ----------
StepStatus = Literal["locked", "active", "passed", "failed"]
CheckStatus = Literal["pending", "pass", "fail"]
SourceKind = Literal["video", "blog", "notebook", "paper", "repo"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="allow")


class VideoSegment(_Model):
    videoId: str
    start: float
    end: float


class Source(_Model):
    id: str
    kind: SourceKind
    title: str
    url: str
    meta: str | None = None
    videoId: str | None = None


StepKind = Literal["code", "run", "read"]


class StepSummary(_Model):
    id: str
    index: int
    title: str
    video: VideoSegment | None = None
    kind: StepKind | None = None  # code = type in the file, run = run a command, read = learn a concept first
    what: str | None = None  # what this step builds, <= 12 words (shown in the step list as the plan)


class PrimerItem(_Model):
    """'Before you start' concept card for a Just teach me lesson (the pre-knowledge for the steps)."""
    id: str
    title: str  # <= 6 words, e.g. "What a function is"
    body: str  # <= 40 words, plain language
    code: str | None = None  # a tiny example
    diagramPrompt: str | None = None  # if set, the app may ask for a picture: action {kind:"diagram", text:"primer:<id>"}


# ---------- Engine -> App events ----------
class SearchResult(_Model):
    id: str
    kind: SourceKind
    title: str
    meta: str
    score: float
    reason: str
    thumbnail: str | None = None
    style: Literal["coding", "no-code", "conceptual"] | None = None
    durationLabel: str | None = None
    long: bool | None = None
    chapters: int | None = None
    captions: bool | None = None
    url: str | None = None
    source: str | None = None
    videoId: str | None = None
    durationS: float | None = None
    channel: str | None = None
    verified: bool | None = None
    warnings: list[str] | None = None
    scoredBy: str | None = None
    watched: str | None = None
    prerequisites: list[str] | None = None
    codeNotes: str | None = None
    comments: str | None = None


class SearchDone(_Model):
    total: int


class LessonBuilding(_Model):
    message: str
    progress: float  # 0..1
    failed: bool | None = None  # the build ended in error; drop the building UI
    elapsedS: float | None = None  # seconds since the build started (heartbeat); `message` changes only with the stage


class GoalMatch(_Model):
    score: float | None = None
    note: str = ""


class LessonInfo(_Model):
    id: str
    title: str
    sources: list[Source]
    complete: bool | None = None  # False: a long video is still building (lesson.updated follows)
    builtBy: Literal["gemini", "claude", "mixed", "chapters", "unknown"] | None = None  # chapters = provisional quick start
    goalMatch: GoalMatch | None = None
    mode: Literal["video", "lesson"] | None = None  # "lesson": no video ("Just teach me")
    provisional: bool | None = None  # True: a placeholder from the chapter list; a fresh lesson.ready replaces it
    primer: list[PrimerItem] | None = None  # "Before you start": the concepts the steps rely on (lesson mode)
    overview: str | None = None  # "What we're building": the project and the plan in plain words, <= 60 words


class LessonReady(_Model):
    lesson: LessonInfo
    steps: list[StepSummary]


class PartsProgress(_Model):
    done: int
    failed: int
    total: int


class LessonUpdated(_Model):
    steps: list[StepSummary]
    complete: bool
    parts: PartsProgress | None = None


class StepStarted(_Model):
    stepId: str
    index: int
    title: str
    instructions: str
    video: VideoSegment | None = None
    details: str | None = None  # the full explanation; `instructions` is one concrete action
    kind: StepKind | None = None  # code / run / read
    what: str | None = None  # what you're building in this step, <= 12 words ("A function named add that returns a + b")
    why: str | None = None  # what it means / why it matters, <= 25 words
    concepts: list[str] | None = None  # primer ids this step uses
    code: str | None = None  # the exact code to type (code steps) or command to run (run steps), in full


class CheckUpdated(_Model):
    stepId: str
    checkId: str
    label: str
    status: CheckStatus
    detail: str | None = None


class StepPassed(_Model):
    stepId: str
    nextStepId: str | None = None
    pending: bool | None = None  # no next step yet: the next part is still building
    skipped: bool | None = None  # the learner skipped it (action skip_step): not passed, never shown green


class OfftrackDiff(_Model):
    expected: str
    yours: str
    file: str | None = None
    line: int | None = None
    command: str | None = None  # a terminal fix (clipboard-staged, never run)


class Citation(_Model):
    label: str
    url: str


OfftrackAction = Literal["explain", "show_me", "apply_fix", "hint"]


class Offtrack(_Model):
    stepId: str
    severity: Literal["warn", "fail"]
    title: str  # <= 8 words
    body: str  # <= ~30 words
    diff: OfftrackDiff | None = None
    citation: Citation | None = None
    actions: list[OfftrackAction]
    level: Literal[2, 3] | None = None  # hint ladder: 2 concept, 3 exact fix + Do it for me
    targets: list[Target] | None = None
    guidingQuestion: str | None = None


class ScreenRect(_Model):
    """Screen POINTS, TOP-LEFT origin, relative to the primary display's full frame."""

    x: float
    y: float
    w: float
    h: float


class Target(_Model):
    boxId: int | None = None
    label: str = ""
    text: str = ""
    rect: ScreenRect


class SpotlightTarget(_Model):
    rect: ScreenRect
    caption: str
    app: str | None = None
    matched: str | None = None
    snippet: str | None = None  # code to type at the rect (lesson mode / Show me)


class SpotlightClear(_Model):
    clear: Literal[True]


Spotlight = SpotlightTarget | SpotlightClear


class ScreenSeen(_Model):
    app: str
    summary: str
    t: float


class VideoSeek(_Model):
    t: float
    play: bool


class Empty(_Model):
    pass


class VideoJump(_Model):
    t: float
    label: str


class SetupInstall(_Model):
    method: Literal["brew", "brew_cask", "pip", "download", "open", "none"]
    command: str | None = None
    url: str | None = None


class SetupItem(_Model):
    tool: str
    label: str
    kind: Literal["editor", "app", "runtime", "cli", "python_package", "web_app"]
    why: str
    needed: bool
    installed: bool
    ok: bool
    version: str | None = None
    minVersion: str | None = None
    install: SetupInstall


class SetupResource(_Model):
    name: str
    url: str
    kind: Literal["repo", "notebook", "gist", "file"]


class Setup(_Model):
    editorNeeded: bool
    items: list[SetupItem]
    editorLabel: str | None = None  # "Cursor"
    resources: list[SetupResource] | None = None  # files the video links (action download)
    actionLabels: dict[str, str] | None = None


class SetupProgress(_Model):
    tool: str
    line: str | None = None
    done: bool | None = None
    ok: bool | None = None
    error: str | None = None
    url: str | None = None
    version: str | None = None


class PreflightGoalMatch(_Model):
    score: float | None = None  # 0..1; None when there was no goal
    note: str


class PreflightChapter(_Model):
    index: int
    lastIndex: int
    title: str
    start: float
    end: float
    window: bool | None = None  # a time window (the video has no chapters)


class HandsOn(_Model):
    index: int
    title: str
    start: float


class SkippedIntro(_Model):
    start: float
    end: float


class BuildPlan(_Model):
    strategy: Literal["whole", "chapters"]
    estSecondsToFirstSteps: float
    firstChapter: PreflightChapter | None = None  # the window E2 builds first
    firstHandsOn: HandsOn | None = None  # Claude: first chapter where the learner does something
    windows: int | None = None
    skippedIntro: "SkippedIntro | None" = None  # a talk-only intro part 1 skips


class PreflightInfo(_Model):
    videoId: str | None = None
    url: str
    style: Literal["coding", "no-code", "conceptual"] | None = None  # search.result.style vocabulary (E7); None = unknown in time
    styleFrom: Literal["claude", "finder"] | None = None  # finder = Claude was late, the picked row's style was used
    topic: str | None = None
    durationS: float | None = None
    chapters: int = 0
    goalMatch: PreflightGoalMatch | None = None
    buildPlan: BuildPlan
    editorNeeded: bool | None = None
    partial: bool = False


CardAction = Literal["confirm", "undo", "apply_fix", "open_editor", "resume", "end_lesson", "install", "skip_setup",
                     "open_in_browser", "build", "pick_another", "download", "skip_step", "check_step", "use_this_folder", "run_command",
                     "retry"]  # retry: "Couldn't reach Claude" card -> action retry (the engine re-asks the question that failed)


class Card(_Model):
    stepId: str | None = None
    kind: Literal["explain", "hint", "answer", "resume", "setup", "preflight"]  # resume: "Continue where you left off?"
    title: str
    body: str
    videoJump: VideoJump | None = None
    actions: list[CardAction] | None = None  # buttons -> action {kind}
    diff: str | None = None  # unified diff preview ("Apply this fix?")
    targets: list[Target] | None = None
    guidingQuestion: str | None = None
    setup: Setup | None = None  # kind "setup"
    items: list[SetupItem] | None = None  # kind "preflight": early tool check
    warning: str | None = None  # kind "preflight": the video doesn't fit the goal (goalMatch < 0.5)
    recommended: Literal["build", "pick_another"] | None = None
    preflight: PreflightInfo | None = None  # kind "preflight"
    where: str | None = None  # coach: where to go when the place isn't on screen (no dim)
    output: str | None = None  # monospace output block (e.g. "Run it for me")


class NetworkDiagram(_Model):
    layers: list[int]
    activation: str
    derivatives: list[str]
    residual: str


class GradientsDiagram(_Model):
    layers: list[str]
    epochs: list[float]
    norms: list[list[float]]  # norms[layer][epochIdx]


class HeatmapDiagram(_Model):
    x: list[float]
    t: list[float]
    predicted: list[list[float]]
    exact: list[list[float]] | None = None


class GraphNode(_Model):
    id: str
    label: str
    detail: str | None = None
    group: str | None = None
    shape: Literal["box", "round", "circle", "data", "commit"]
    emphasis: bool
    col: float
    row: float


class GraphEdge(_Model):
    model_config = ConfigDict(extra="allow", populate_by_name=True)
    from_: str = Field(alias="from")
    to: str
    label: str | None = None
    style: Literal["solid", "dashed"]
    emphasis: bool
    order: int | None = None  # sequence layouts only


class GraphGrid(_Model):
    cols: int
    rows: int


class GraphGroup(_Model):
    id: str
    label: str


class GraphDiagram(_Model):
    title: str
    layout: Literal["flow", "sequence", "tree", "data", "architecture", "git"]
    direction: Literal["LR", "TB"]
    grid: GraphGrid
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    groups: list[GraphGroup] | None = None


class Diagram(_Model):
    kind: Literal["network", "gradients", "heatmap", "graph"]
    caption: str
    stepId: str | None = None
    data: NetworkDiagram | GradientsDiagram | HeatmapDiagram | GraphDiagram


class Speak(_Model):
    audioUrl: str  # relative (/tts/<hash>.mp3): resolve against the engine's http origin
    text: str


class Metric(_Model):
    runId: str
    step: int
    name: str
    value: float


class Status(_Model):
    state: Literal["idle", "watching", "offtrack", "passed", "thinking"]


class Error(_Model):
    message: str


class LessonEnded(_Model):
    lessonId: str | None = None
    reason: str


KeyState = Literal["ok", "missing", "invalid", "env"]  # "env" = falling back to the engine's .env


class ConfigStatus(_Model):
    anthropic: KeyState
    gemini: KeyState
    brightdata: KeyState
    elevenlabs: KeyState
    tigerUrl: KeyState


ENGINE_EVENTS: dict[str, Any] = {
    "search.result": SearchResult,
    "search.done": SearchDone,
    "lesson.building": LessonBuilding,
    "lesson.ready": LessonReady,
    "lesson.updated": LessonUpdated,
    "step.started": StepStarted,
    "check.updated": CheckUpdated,
    "step.passed": StepPassed,
    "offtrack": Offtrack,
    "spotlight": TypeAdapter(Spotlight),
    "screen.seen": ScreenSeen,
    "video.seek": VideoSeek,
    "video.pause": Empty,
    "video.play": Empty,
    "card": Card,
    "diagram": Diagram,
    "speak": Speak,
    "metric": Metric,
    "status": Status,
    "error": Error,
    "lesson.ended": LessonEnded,
    "setup.progress": SetupProgress,
    "config.status": ConfigStatus,
}

EngineEventType = Literal[
    "search.result", "search.done", "lesson.building", "lesson.ready", "step.started",
    "check.updated", "step.passed", "offtrack", "spotlight", "video.seek", "video.pause",
    "video.play", "card", "diagram", "speak", "metric", "status", "error", "screen.seen", "config.status", "lesson.ended", "setup.progress", "lesson.updated",
]


# ---------- App -> Engine commands ----------
class Learn(_Model):
    query: str
    mode: Literal["video", "lesson"] | None = None  # "lesson" = "Just teach me": no video search


class LearnUrl(_Model):
    url: str


class BuildLesson(_Model):
    resultIds: list[str]


ActionKind = Literal["back", "explain", "diagram", "show_me", "hint", "voice_toggle", "ask", "apply_fix",
                     "confirm", "undo", "open_editor", "resume", "end_lesson", "install", "skip_setup", "open_in_browser",
                     "build", "pick_another", "download", "skip_step", "check_step", "use_this_folder", "run_command",
                     "retry"]


class Action(_Model):
    kind: ActionKind
    text: str | None = None


class VideoState(_Model):
    t: float
    playing: bool


class EndLesson(_Model):
    pass


class OverlayBounds(_Model):
    rects: list[ScreenRect]


class ConfigKeys(_Model):
    """Bring-your-own-key. Keep in memory only; never log or echo these."""

    anthropic: str | None = None
    gemini: str | None = None
    brightdata: str | None = None
    elevenlabs: str | None = None
    tigerUrl: str | None = None


APP_COMMANDS: dict[str, type[_Model]] = {
    "learn": Learn,
    "learn_url": LearnUrl,
    "build_lesson": BuildLesson,
    "action": Action,
    "video.state": VideoState,
    "overlay.bounds": OverlayBounds,
    "config.keys": ConfigKeys,
    "end_lesson": EndLesson,
}

AppCommandType = Literal["learn", "learn_url", "build_lesson", "action", "video.state", "overlay.bounds", "config.keys", "end_lesson"]


class AppMessage(BaseModel):
    type: str
    payload: Any


def _dump(model: Any) -> dict:
    if isinstance(model, BaseModel):
        return model.model_dump(mode="json", exclude_none=True, by_alias=True)
    return model


def validate_engine_payload(type_: str, payload: Any) -> dict:
    """Validate an Engine->App payload; returns the JSON-ready dict. Raises on bad shape."""
    validator = ENGINE_EVENTS.get(type_)
    if validator is None:
        raise ValueError(f"unknown engine event type: {type_}")
    if isinstance(validator, TypeAdapter):
        return _dump(validator.validate_python(payload))
    return _dump(validator.model_validate(payload))


def engine_message(type_: str, payload: Any | None = None) -> dict:
    """Build a validated {type, payload} Engine->App message."""
    return {"type": type_, "payload": validate_engine_payload(type_, payload or {})}


def parse_app_message(raw: dict) -> AppMessage:
    """Parse an App->Engine {type, payload} message; payload becomes the typed model."""
    type_ = raw.get("type")
    model = APP_COMMANDS.get(type_)  # type: ignore[arg-type]
    if model is None:
        raise ValueError(f"unknown app command type: {type_}")
    return AppMessage(type=type_, payload=model.model_validate(raw.get("payload") or {}))

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


class StepSummary(_Model):
    id: str
    index: int
    title: str
    video: VideoSegment | None = None


# ---------- Engine -> App events ----------
class SearchResult(_Model):
    id: str
    kind: SourceKind
    title: str
    meta: str
    score: float
    reason: str
    thumbnail: str | None = None


class SearchDone(_Model):
    total: int


class LessonBuilding(_Model):
    message: str
    progress: float  # 0..1
    failed: bool | None = None  # the build ended in error; drop the building UI


class LessonInfo(_Model):
    id: str
    title: str
    sources: list[Source]


class LessonReady(_Model):
    lesson: LessonInfo
    steps: list[StepSummary]


class StepStarted(_Model):
    stepId: str
    index: int
    title: str
    instructions: str
    video: VideoSegment | None = None


class CheckUpdated(_Model):
    stepId: str
    checkId: str
    label: str
    status: CheckStatus
    detail: str | None = None


class StepPassed(_Model):
    stepId: str
    nextStepId: str | None = None


class OfftrackDiff(_Model):
    expected: str
    yours: str
    file: str | None = None
    line: int | None = None


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


CardAction = Literal["confirm", "undo", "apply_fix", "open_editor", "resume", "end_lesson"]


class Card(_Model):
    stepId: str | None = None
    kind: Literal["explain", "hint", "answer", "resume"]  # resume: "Continue where you left off?"
    title: str
    body: str
    videoJump: VideoJump | None = None
    actions: list[CardAction] | None = None  # buttons -> action {kind}
    diff: str | None = None  # unified diff preview ("Apply this fix?")
    targets: list[Target] | None = None
    guidingQuestion: str | None = None


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
    audioUrl: str
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
    "config.status": ConfigStatus,
}

EngineEventType = Literal[
    "search.result", "search.done", "lesson.building", "lesson.ready", "step.started",
    "check.updated", "step.passed", "offtrack", "spotlight", "video.seek", "video.pause",
    "video.play", "card", "diagram", "speak", "metric", "status", "error", "screen.seen", "config.status", "lesson.ended",
]


# ---------- App -> Engine commands ----------
class Learn(_Model):
    query: str


class LearnUrl(_Model):
    url: str


class BuildLesson(_Model):
    resultIds: list[str]


ActionKind = Literal["back", "explain", "diagram", "show_me", "hint", "voice_toggle", "ask", "apply_fix",
                     "confirm", "undo", "open_editor", "resume", "end_lesson"]


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

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

from typing import Any, Literal, Union

from pydantic import BaseModel, ConfigDict, TypeAdapter

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


class SpotlightTarget(_Model):
    file: str
    startLine: int
    endLine: int
    caption: str


class SpotlightClear(_Model):
    clear: Literal[True]


Spotlight = Union[SpotlightTarget, SpotlightClear]


class VideoSeek(_Model):
    t: float
    play: bool


class Empty(_Model):
    pass


class VideoJump(_Model):
    t: float
    label: str


class Card(_Model):
    stepId: str | None = None
    kind: Literal["explain", "hint", "answer"]
    title: str
    body: str
    videoJump: VideoJump | None = None


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


class Diagram(_Model):
    kind: Literal["network", "gradients", "heatmap"]
    caption: str
    data: NetworkDiagram | GradientsDiagram | HeatmapDiagram


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
    "video.seek": VideoSeek,
    "video.pause": Empty,
    "video.play": Empty,
    "card": Card,
    "diagram": Diagram,
    "speak": Speak,
    "metric": Metric,
    "status": Status,
    "error": Error,
}

EngineEventType = Literal[
    "search.result", "search.done", "lesson.building", "lesson.ready", "step.started",
    "check.updated", "step.passed", "offtrack", "spotlight", "video.seek", "video.pause",
    "video.play", "card", "diagram", "speak", "metric", "status", "error",
]


# ---------- App -> Engine commands ----------
class Learn(_Model):
    query: str


class LearnUrl(_Model):
    url: str


class BuildLesson(_Model):
    resultIds: list[str]


ActionKind = Literal["back", "explain", "diagram", "show_me", "hint", "voice_toggle", "ask", "apply_fix"]


class Action(_Model):
    kind: ActionKind
    text: str | None = None


class VideoState(_Model):
    t: float
    playing: bool


APP_COMMANDS: dict[str, type[_Model]] = {
    "learn": Learn,
    "learn_url": LearnUrl,
    "build_lesson": BuildLesson,
    "action": Action,
    "video.state": VideoState,
}

AppCommandType = Literal["learn", "learn_url", "build_lesson", "action", "video.state"]


class AppMessage(BaseModel):
    type: str
    payload: Any


def _dump(model: Any) -> dict:
    if isinstance(model, BaseModel):
        return model.model_dump(mode="json", exclude_none=True)
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

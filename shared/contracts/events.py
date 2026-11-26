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

import hashlib
import re
from typing import Any, Literal
from urllib.parse import parse_qsl, urlencode, urlsplit

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator

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


class PageRef(_Model):
    """Any link (Nov 24, ANY-LINK.md): where a web / github lesson's step comes from. Never a copy of the page's words."""
    url: str  # the page (a #fragment when the engine knows the heading's anchor)
    heading: str | None = None  # that section's heading text


class StepSummary(_Model):
    id: str
    index: int
    title: str
    video: VideoSegment | None = None
    kind: StepKind | None = None  # code = type in the file, run = run a command, read = learn a concept first
    what: str | None = None  # what this step builds, <= 12 words (shown in the step list as the plan)
    estMinutes: int | None = None  # about how long this step takes, whole minutes ("about 35 min left" = sum over steps not passed)
    skillIds: list[str] | None = None  # Nov 22 (Skills page): the SkillInfo ids this step builds evidence for
    pageRef: PageRef | None = None  # any link (Nov 24): a web / github lesson's step: the part of the page it comes from


class PrimerItem(_Model):
    """'Before you start' concept card for a Just teach me lesson (the pre-knowledge for the steps)."""
    id: str
    title: str  # <= 6 words, e.g. "What a function is"
    body: str  # <= 40 words, plain language
    code: str | None = None  # a tiny example
    diagramPrompt: str | None = None  # if set, the app may ask for a picture: action {kind:"diagram", text:"primer:<id>"}


# Learn-anything screens (Just teach me; mockups 01 drawer v2, 02 concept panel, 03 "Before you start"). All optional.
# Concept diagrams are NOT pre-built: the app asks on demand with action {kind:"diagram", text:"<concept title>"}.
class LessonBuild(_Model):
    summary: str  # what you'll build, <= 20 words
    outcome: str  # what the finished result looks like / does, <= 25 words
    estMinutes: int | None = None  # the whole lesson (= the sum of the steps' estMinutes)


class FlowBox(_Model):
    """One box of the "How it works" diagram (3-6 boxes, left to right)."""
    label: str  # <= 3 words
    detail: str | None = None  # a formula or <= 4 words
    stepIndex: int | None = None  # StepSummary.index of the step that builds this box


class Prerequisite(_Model):
    id: str
    title: str  # <= 4 words
    why: str  # <= 12 words
    status: Literal["passed", "unknown"]  # passed: a lesson completed on this Mac covered it; unknown: not seen yet
    evidence: str | None = None  # "Passed in Python Calculator"


class LearnFirstItem(_Model):
    """A short mini-lesson for a prerequisite not passed yet."""
    title: str
    minutes: int
    kind: Literal["notebook", "interactive", "video", "read"]
    covers: str  # Prerequisite.id


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


BuildStage = Literal["watching", "steps", "checks", "ready"]  # v2 Home-Building rows
BuildFailCode = Literal["unreadable_code", "no_steps", "too_long", "no_captions", "network", "provider", "unknown",
                        "no_content", "blocked"]  # no_content / blocked (any link): no readable text on the page / the site refused (sign-in, paywall, robots, 4xx)


class BuildPhase(_Model):
    """v2 (Home-Building): one row of the build checklist."""
    id: BuildStage
    label: str
    state: Literal["done", "active", "next"]
    detail: str | None = None  # "6 steps found", "Step 4 of 6"


BuildSourceKind = Literal["youtube", "goal", "library", "web", "github"]  # web / github: any link (Nov 24, ANY-LINK.md)


class BuildSource(_Model):
    """v2: what the lesson is built from. kind "web" (an article / docs page) or "github" (a repo's README or docs folder): url
    always set, site ("docs.python.org", "github.com/pallets/flask"), author when the page names one."""
    kind: BuildSourceKind
    title: str
    channel: str | None = None
    durationS: float | None = None
    url: str | None = None
    site: str | None = None
    author: str | None = None


class BuildAlternative(_Model):
    """v2 (Err-LessonBuildFailed): transcript only (learn_url transcriptOnly) or a cached library lesson (library.start)."""
    kind: Literal["transcript", "library"]
    title: str
    meta: str | None = None
    id: str | None = None
    url: str | None = None


class LessonBuilding(_Model):
    message: str
    progress: float  # 0..1
    failed: bool | None = None  # the build ended in error; drop the building UI
    elapsedS: float | None = None  # seconds since the build started (heartbeat); `message` changes only with the stage
    # v2 (all optional)
    stage: BuildStage | None = None
    phases: list[BuildPhase] | None = None
    etaS: float | None = None  # about how long is left, seconds
    source: BuildSource | None = None
    failCode: BuildFailCode | None = None  # with failed
    failReason: str | None = None  # with failed: one plain sentence
    alternatives: list[BuildAlternative] | None = None  # with failed
    silent: bool | None = None  # with failed: the learner moved on; no failure card


class GoalMatch(_Model):
    score: float | None = None
    note: str = ""


class OutlineStep(_Model):
    """One row of lesson.outline: a step of the lesson, built or still being written."""
    index: int
    title: str
    kind: StepKind | None = None
    what: str | None = None
    estMinutes: int | None = None
    skillIds: list[str] | None = None  # as StepSummary.skillIds


class LessonOutline(_Model):
    """E23: every step from the first lesson.ready on (count = the final step count), so "Step 1 of N" never jumps."""
    count: int
    steps: list[OutlineStep]
    estMinutes: int | None = None  # the whole lesson, when every row has one


# ---------- v2 shapes (BUILD-PLAN W0-1) ----------
HealthState = Literal["ok", "missing", "off", "checking", "unknown"]  # unknown: can't tell without prompting (gray)
PermissionKind = Literal["screen", "accessibility", "automation"]
PauseReason = Literal["editor_closed", "kernel", "network", "permission", "user"]
BlockerKind = Literal["kernel", "editor_closed", "network"]
LessonTool = Literal["vscode", "jupyter", "terminal", "excel"]
SkillProgressState = Literal["mastered", "practicing", "not_started"]
LIBRARY_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"  # library ids: never a path


class MissingLine(_Model):
    text: str
    state: Literal["ok", "missing"]


class HintStep(_Model):
    n: int
    of: int


class LessonResult(_Model):
    """card kind "complete": what the lesson counted. Skips are skips, never passes."""
    passed: int
    skipped: int
    total: int
    minutes: int | None = None
    lessonId: str | None = None
    title: str | None = None


class HealthItem(_Model):
    id: str  # vscode / companion / python / jupyter / engine / cloud
    label: str
    state: HealthState
    detail: str | None = None
    fix: str | None = None  # the action kind that fixes it


class LibraryProgress(_Model):
    stepIndex: int
    stepTitle: str
    total: int


class LibraryItem(_Model):
    id: str = Field(pattern=LIBRARY_ID_PATTERN)
    title: str
    by: str | None = None
    steps: int
    estMinutes: int | None = None
    tools: list[LessonTool] = []
    ready: bool = True
    progress: LibraryProgress | None = None
    source: BuildSource | None = None
    updatedAt: str | None = None
    # Nov 22 (Skills page), SkillInfo ids: teaches = skills it builds; uses = skills it needs; unlocks = skills ready once it is done
    teaches: list[str] | None = None
    uses: list[str] | None = None
    unlocks: list[str] | None = None


class SkillProgressItem(_Model):
    label: str
    state: SkillProgressState


class SkillTrackProgress(_Model):
    track: str
    mastered: int
    total: int
    items: list[SkillProgressItem]


class CompletedLesson(_Model):
    lessonId: str
    title: str
    at: str  # ISO date


class WeekActivity(_Model):
    minutes: int | None = None
    streak: int | None = None
    days: list[bool] = []


class ReviewItem(_Model):
    label: str
    file: str | None = None
    checks: int
    when: str


class ReviewQueue(_Model):
    due: int
    items: list[ReviewItem]


class LessonApp(_Model):
    """On-screen coach (Nov 24): the desktop app a no-code lesson is done in (server.lesson.app_lesson.adapt). tool: the
    server.workspace.apps id ("blender"); label: its name ("Blender"); using: the app the learner really works in when it
    isn't the one the lesson names ("FreeCAD"). Never set for a code or VS Code lesson."""

    tool: str
    label: str
    using: str | None = None


class LessonInfo(_Model):
    id: str
    title: str
    sources: list[Source]
    complete: bool | None = None  # False: a long video is still building (lesson.updated follows)
    builtBy: Literal["gemini", "claude", "mixed", "chapters", "unknown", "curated"] | None = None  # chapters = provisional quick start; curated = written by hand (curated.py), no model
    goalMatch: GoalMatch | None = None
    mode: Literal["video", "lesson"] | None = None  # "lesson": no video ("Just teach me")
    provisional: bool | None = None  # True: a placeholder from the chapter list; a fresh lesson.ready replaces it
    primer: list[PrimerItem] | None = None  # "Before you start": the concepts the steps rely on (lesson mode)
    overview: str | None = None  # "What we're building": the project and the plan in plain words, <= 60 words
    build: LessonBuild | None = None  # learn-anything: what you'll build + the finished result + minutes
    flow: list[FlowBox] | None = None  # learn-anything: the "How it works" diagram
    prerequisites: list[Prerequisite] | None = None  # learn-anything: "You'll need" / the "Needs" chip
    learnFirst: list[LearnFirstItem] | None = None  # learn-anything: mini-lessons for the gaps
    outline: LessonOutline | None = None  # every step from the start (absent: a build whose step count isn't known yet)
    origin: BuildSource | None = None  # any link (Nov 24): what it was built from (web / github: mode "lesson", no video)
    app: LessonApp | None = None  # on-screen coach: a desktop-app lesson (absent: a code / VS Code lesson)


class LessonReady(_Model):
    lesson: LessonInfo
    steps: list[StepSummary]
    replay: bool | None = None  # the SAME lesson again (reconnect / restore): keep its progress, no "Before you start"
    buildS: float | None = None  # seconds from the learner's command (learn / learn_url / build_lesson) to this lesson.ready; only on a build's first lesson.ready


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
    estMinutes: int | None = None  # about how long this step takes ("about 4 min")
    replay: bool | None = None  # a reconnect's / restore's replay of the step already running (not a new step)
    where: str | None = None  # v2 (Les-Working): the line above the code ("Type this in the new cell")
    then: str | None = None  # v2: the line under it ("Then run it with the arrow beside the cell.")


class CheckUpdated(_Model):
    epoch: int | None = None  # lesson / step generation it was sent under (optional, additive)
    gen: int | None = None
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
    already: bool | None = None  # its code was already in the file: passed without starting (one "You already did" card)
    summary: str | None = None  # v2: what the learner just did, <= 12 words
    # ui-v4 (Nov 24), all optional; see events.ts step.passed
    key: str | None = None  # "<lessonId>:<stepId>": the pass's stable id (bon, activity.recent and mastery de-dupe on it)
    counted: bool | None = None  # this pass grew bon's count (a `bon` push follows)
    assisted: bool | None = None  # passed after Show me's snippet, a level-3 hint or Do it for me: counts for bon, not toward mastery
    skillIds: list[str] | None = None  # the SkillInfo ids it is evidence for
    proofId: str | None = None  # the Proof kept for it (proof.get)


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
    epoch: int | None = None  # lesson / step generation it was sent under (optional, additive)
    gen: int | None = None


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
    zoom: bool | None = None  # a VS Code control under 32 pt (Run ▷, Toggle Panel, unsaved dot): the app's loupe


class SpotlightClear(_Model):
    clear: Literal[True]


Spotlight = SpotlightTarget | SpotlightClear


class ScreenSeen(_Model):
    app: str
    summary: str
    t: float


class AvoidRect(_Model):
    """Screen POINTS, TOP-LEFT origin (the spotlight.rect space): a VS Code control Miyagi's UI must not cover."""

    kind: Literal["quickpick"]
    x: float
    y: float
    w: float
    h: float


class ScreenAvoid(_Model):
    rects: list[AvoidRect]  # [] = nothing to avoid any more (the picker closed): the app clears it



class ScreenRegion(_Model):
    """Circle to ask (Nov 22): the bounding box of the ink the learner drew while holding Fn+Control.

    Screen POINTS, TOP-LEFT origin, in Electron's global screen space (the spotlight.rect space: the primary display's
    frame starts at 0,0; another display has its own offset, maybe negative). displayId: Electron's Display.id, which on
    macOS is the CGDirectDisplayID (server/screen/sck.py capture(display_id)). scale: that display's pixels per point.
    """

    x: float
    y: float
    w: float
    h: float
    displayId: int
    scale: float


class Annotation(_Model):
    """Buddy draws (Nov 22): one thing the app circles with a hand-drawn stroke grown from the island (event annotate).

    x / y / w / h: screen points, the ScreenRegion space. displayId None = the primary display (spotlight.rect).
    why "answer": the thing a circle-to-ask answer names, inside the circled region (askId = that ask).
    why "point" (Nov 24, on-screen coach): only in an app lesson (lesson.app), ONE mark at a step start, a "Not yet" or
    Show me ("where?"), with text (+ keys). A mark with text is not timed (holdMs does not apply to it): it stays until
    the step passes or changes, the learner reaches it, Esc, lesson.ended or annotate {clear}. Other pointing still
    reaches the app as spotlight {rect, caption}, card.targets and offtrack targets, and is not repeated as annotate.
    label: <= 4 words. id: stable per mark, so a re-sent annotate keeps a circle still drawn instead of drawing it again.
    """

    id: str | None = None
    x: float
    y: float
    w: float
    h: float
    displayId: int | None = None
    label: str | None = None
    why: Literal["point", "answer"]
    askId: str | None = None
    stepId: str | None = None
    text: str | None = None  # on-screen coach, why "point" only: the step's action, <= 12 words, drawn next to the circle
    keys: list[str] | None = None  # the shortcut: one keycap label per key, in order (<= 3), spelled as bridge.platform.keys spells keys ("⇧A", "⌘S", "Tab")


class AnnotateMarks(_Model):
    """annotate: circle these. A new annotate replaces the marks drawn before; the overlay stays click-through. The app
    fades them on a click inside one, a step change, lesson.ended, or after holdMs (None: the app's default, a few s);
    a mark with text ignores holdMs."""

    marks: list[Annotation]
    holdMs: int | None = None


class AnnotateClear(_Model):
    clear: Literal[True]  # fade every mark now


Annotate = AnnotateMarks | AnnotateClear


class AnswerDelta(_Model):
    """answer.delta (Circle to ask, streamed, Nov 22; fast circle to ask, server/coach/fast_ask.py): the next words of a
    streamed answer. Append `text` (the NEW text, never the whole text so far) to the answer for askId; seq counts up
    from 0 per ask. The model's first-line [DRAW:...] tag never reaches the app (the engine sends it as annotate). The
    answer card {kind: "answer", askId} still follows answer.done with the same text, so an app that ignores these events
    loses nothing; nothing streamed: only the card comes, as before. Union of both readings (Nov 24 contract sync):
    done True marks the last delta for an app that predates answer.done; an engine that sends answer.done need not set
    it. askId None: an ask that carried no id (the app drops it)."""

    askId: str | None = None
    seq: int | None = None
    text: str = ""
    done: bool | None = None


class AnswerDone(_Model):
    """answer.done: the streamed answer for askId is over. `text` is the whole answer, cleaned: the app MUST replace
    what the deltas built with it. Deltas are sent as the words arrive, so a sentence the engine flags as a prompt
    injection may have shown in them; done.text never has it. complete False: cut short (reason "refusal" |
    "max_tokens" | "error" | "moved_on", a plain str; moved_on: the step changed, a "moved on" card follows; refusal:
    text is "" so the declined words leave the screen, and a failed answer card follows).
    fallback True: the stream failed and a non-streaming retry answered."""

    askId: str | None = None
    text: str
    complete: bool = True
    fallback: bool | None = None
    reason: str | None = None


class VideoSeek(_Model):
    t: float
    play: bool


class Empty(_Model):
    pass


class VideoJump(_Model):
    t: float
    label: str


class SetupInstall(_Model):
    method: Literal["brew", "brew_cask", "pip", "npm", "download", "open", "none"]  # npm: ambient help (Nov 24), setup.fix only
    command: str | None = None
    url: str | None = None


class SetupAlternative(_Model):
    name: str
    url: str
    tool: str | None = None


class SetupItem(_Model):
    tool: str
    label: str
    kind: Literal["editor", "app", "runtime", "cli", "python_package", "node_package", "web_app"]  # node_package: ambient help (Nov 24)
    why: str
    needed: bool
    installed: bool
    ok: bool
    version: str | None = None
    minVersion: str | None = None
    install: SetupInstall
    # Nov 22, additive (server/workspace/apps.py): a licensed app (AutoCAD...) is never installed; see events.ts
    setupKind: Literal["package", "free_app", "licensed_app", "web_app"] | None = None
    actions: list[Literal["install", "have_it", "get_it", "alternative", "skip"]] | None = None
    vendorUrl: str | None = None
    vendorName: str | None = None
    alternative: SetupAlternative | None = None
    haveIt: bool | None = None
    using: str | None = None
    noMac: bool | None = None
    # ambient help (Nov 24), setup.report: the project file (and line) that asked for it ("requirements.txt:4", ".nvmrc")
    from_: str | None = Field(default=None, alias="from")


class SetupResource(_Model):
    name: str
    url: str
    kind: Literal["repo", "notebook", "gist", "file"]


class Setup(_Model):
    editorNeeded: bool
    items: list[SetupItem]
    editorLabel: str | None = None  # "Visual Studio Code"
    resources: list[SetupResource] | None = None  # files the video links (action download)
    actionLabels: dict[str, str] | None = None
    holdVideo: bool | None = None  # Nov 22: hold the video only when the current step truly needs a missing tool


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


SkillState = Literal["mastered", "learning", "next"]


class SkillNode(_Model):
    """A concept on the skill map's track. mastered: every step behind it passed; learning: one was skipped; next: not learned yet."""
    id: str
    label: str  # <= 6 words
    state: SkillState
    detail: str | None = None  # a formula / "Step 2 skipped" / why it's next, under the label


class SkillEdge(_Model):
    model_config = ConfigDict(extra="allow", populate_by_name=True)
    from_: str = Field(alias="from")  # SkillNode.id
    to: str


class SkillCross(_Model):
    """A dashed "shared idea" link from another track's concept to SkillNode `to`."""
    track: str  # "Math"
    label: str  # "Matrix multiply"
    to: str  # SkillNode.id
    note: str | None = None  # the link's caption


class SkillNext(_Model):
    title: str
    goal: str  # launcher text: learn {query: goal, mode: "lesson"}


class SkillMap(_Model):
    """card.skillMap on the lesson-complete card (mockup 10 "Your skills"), from server/lesson/skillmap.py."""
    track: str
    headline: str
    nodes: list[SkillNode]
    edges: list[SkillEdge]
    cross: list[SkillCross]
    next: list[SkillNext]


# ---------- Skills page: the skill graph (Nov 22, additive; app/agents/skills.md "Contract") ----------
# A node is a skill built up across lessons, never one lesson's step. Times: ISO text or epoch seconds.
SkillGraphState = Literal["locked", "ready", "practicing", "mastered"]  # review is a modifier on mastered, never a demotion
SkillInfoKind = Literal["skill", "capstone"]
Moment = str | int | float


class SkillLessonRef(_Model):
    lessonId: str
    libraryId: str | None = None
    title: str | None = None
    stepIds: list[str] | None = None  # the steps of that lesson that build this skill
    role: Literal["teaches", "uses", "practices"] | None = None


class SkillEvidence(_Model):
    done: int
    total: int


class SkillReview(_Model):
    dueAt: Moment


class SkillExample(_Model):
    code: str | None = None
    caption: str | None = None


# ui-v4 (Nov 24, skill tree round 3: tracks -> skills -> steps). A step's skills: StepSummary.skillIds / step.passed.skillIds.
MASTERY_DAYS = 2  # mastered = passed unassisted on this many different local days (Adrian's rule)
REVIEW_DAYS: tuple[int, ...] = (3, 7, 21, 60)  # Adrian's review schedule, days after mastery per round; SkillGraphInfo.reviewDays says what the engine uses (sessions/review.py INTERVALS today)


class SkillStepRef(_Model):
    """The Steps zoom: one step behind a skill, passed or not. key: step.passed.key once passed."""
    key: str | None = None
    lessonId: str
    lessonTitle: str | None = None
    stepId: str
    title: str
    passed: bool
    at: str | None = None
    assisted: bool | None = None


class SkillMastery(_Model):
    """days: the distinct local dates with an unassisted pass (mastered when len(days) >= need)."""
    need: int
    days: list[str] = []
    assisted: int | None = None  # passes that did not count toward it


class SkillReviewInfo(_Model):
    """round: 0-based into reviewDays; interval: the days this round waits; a miss starts over at round 0."""
    dueAt: str
    round: int
    interval: int
    lastAt: str | None = None
    lastResult: Literal["pass", "miss"] | None = None


class SkillTrackInfo(_Model):
    id: str
    label: str
    mastered: int
    total: int
    next: str | None = None  # the SkillInfo id to do next on this track; None (with mastered == total): the track is done
    lastPracticedAt: str | None = None
    planIds: list[str] | None = None


class SkillInfo(_Model):
    id: str
    label: str  # <= 4 words
    track: str  # the group header ("numpy")
    summary: str | None = None  # one line, <= 12 words
    kind: SkillInfoKind | None = None  # capstone: details in SkillGraphInfo.capstones by the same id
    state: SkillGraphState | None = None
    evidence: SkillEvidence | None = None  # steps passed of the steps behind it
    masteredAt: Moment | None = None
    lastPracticedAt: Moment | None = None
    review: SkillReview | None = None
    lessons: list[SkillLessonRef] | None = None
    example: SkillExample | None = None
    # ui-v4 (Nov 24), all optional
    catalogId: str | None = None  # the catalog skill id ("py.loops")
    steps: list[SkillStepRef] | None = None  # every step behind it, passed or not, in lesson order
    mastery: SkillMastery | None = None
    schedule: SkillReviewInfo | None = None  # the spaced-review schedule in full (review keeps only dueAt)
    proofIds: list[str] | None = None  # Proofs kept for its passes, newest first
    planIds: list[str] | None = None  # PlanState ids that grow it


class SkillGraphEdge(_Model):
    model_config = ConfigDict(extra="allow", populate_by_name=True)
    from_: str = Field(alias="from")  # SkillInfo.id
    to: str
    kind: Literal["requires", "helps"] | None = None  # None = requires
    weight: float | None = None  # 0..1, helps only


class SkillArtifact(_Model):
    kind: Literal["image", "file"]
    path: str | None = None  # local, never a URL
    caption: str | None = None


class SkillCapstone(_Model):
    id: str  # the SkillInfo id of the capstone node
    brief: str | None = None
    requires: list[str] | None = None  # the skill ids the goal counts; None = every skill upstream of it
    checks: list[str] | None = None
    starterFile: str | None = None
    estMinutes: int | None = None
    completedAt: Moment | None = None
    artifact: SkillArtifact | None = None


class SkillPick(_Model):
    """What to do now: one skill and the lesson step that moves it (library.start {libraryId} or learn {query: goal})."""
    skillId: str
    lessonId: str | None = None
    libraryId: str | None = None
    lessonTitle: str | None = None
    stepIndex: int | None = None  # 0-based, as LibraryItem.progress.stepIndex
    stepCount: int | None = None
    estMinutes: int | None = None
    goal: str | None = None
    why: str | None = None  # <= 12 words


class SkillEvent(_Model):
    id: str
    kind: Literal["mastered", "unlocked", "review_due", "capstone_done"]
    skillId: str
    at: Moment
    from_: str | None = Field(default=None, alias="from")  # the skill whose mastery unlocked this one
    lessonId: str | None = None
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class SkillWeek(_Model):
    mastered: int | None = None
    keptFresh: int | None = None
    minutes: int | None = None
    days: list[bool] | None = None  # Monday first
    weeklyGoal: int | None = None
    goalAway: int | None = None  # skills left to the goal


class PortfolioItem(_Model):
    capstoneId: str
    title: str
    at: Moment
    track: str | None = None
    skillIds: list[str] | None = None
    artifact: SkillArtifact | None = None


class SkillGraphInfo(_Model):
    skills: list[SkillInfo] = []
    edges: list[SkillGraphEdge] = []
    capstones: list[SkillCapstone] | None = None
    goal: str | None = None  # a capstone id (set_goal); None = no goal picked yet
    next: SkillPick | None = None
    alsoReady: list[str] | None = None  # <= 3 skill ids
    keepFresh: list[str] | None = None  # <= 3 skill ids
    events: list[SkillEvent] | None = None
    ackedUntil: Moment | None = None  # events newer than this play once; the app then sends skills.ack {until}
    week: SkillWeek | None = None
    portfolio: list[PortfolioItem] | None = None
    # ui-v4 (Nov 24), all optional
    tracks: list[SkillTrackInfo] | None = None  # the Tracks zoom and Progress's Tracks table, in display order
    masteryDays: int | None = None  # the mastery rule in use (MASTERY_DAYS)
    reviewDays: list[int] | None = None  # the review schedule in use (REVIEW_DAYS is the proposal)


CardAction = Literal["confirm", "undo", "apply_fix", "open_editor", "resume", "end_lesson", "install", "install_all", "skip_setup",
                     "open_in_browser", "build", "pick_another", "download", "skip_step", "check_step", "use_this_folder", "run_command",
                     "retry", "hint", "show_me", "have_it", "get_it", "alternative",
                     "open_in_app"]  # open_in_app (Nov 24): an app lesson's setup card: open the lesson's scene in its desktop app (Blender, with the miyagi bridge); label setup.actionLabels.open_in_app; text? = tool id; holdVideo false
# have_it / get_it / alternative (Nov 22): a licensed app row. retry: "Couldn't reach Claude" card -> action retry; hint / show_me: the off-track card's actions, on a judge "Not yet" card


class Card(_Model):
    epoch: int | None = None  # lesson / step generation it was sent under (optional, additive)
    gen: int | None = None
    stepId: str | None = None
    # resume: "Continue where you left off?"; step: a step-control / judge card the engine raises itself ("Run it",
    # "Save X", "X is still empty", "Wrong folder?", "Looks done?", "Not yet"), never an answer; where: the
    # where-to-work card ("Open calc.py", "Where to work") when there is no box to draw (Show me, or Hint before the
    # step's code is on screen). See events.ts.
    kind: Literal["explain", "hint", "answer", "resume", "setup", "preflight", "step", "where", "complete"]  # complete (v2): the last step passed
    title: str
    body: str
    videoJump: VideoJump | None = None
    actions: list[CardAction] | None = None  # buttons -> action {kind}
    diff: str | None = None  # unified diff preview ("Apply this fix?")
    targets: list[Target] | None = None
    guidingQuestion: str | None = None
    askId: str | None = None  # Circle to ask (Nov 22): kind "answer" to action ask {askId}: the app matches it to its circle
    region: ScreenRegion | None = None  # Circle to ask: the circled region, echoed back so the card sits next to it
    setup: Setup | None = None  # kind "setup"
    items: list[SetupItem] | None = None  # kind "preflight": early tool check
    warning: str | None = None  # kind "preflight": the video doesn't fit the goal (goalMatch < 0.5)
    recommended: Literal["build", "pick_another"] | None = None
    preflight: PreflightInfo | None = None  # kind "preflight"
    where: str | None = None  # coach: where to go when the place isn't on screen (no dim)
    output: str | None = None  # monospace output block (e.g. "Run it for me")
    dismissAfterMs: int | None = None  # the app closes the card on its own after this long (one-line success, no buttons)
    source: Literal["judge"] | None = None  # E5's step judge made it: a step-status card (kind "step"), never an answer
    verdict: Literal["done", "not_done"] | None = None  # source "judge": the WHOLE step. done = "Looks done?", not_done = "Not yet"
    checkIds: list[str] | None = None  # source "judge": the checks it is about (done: what Yes vouches for; not_done: still missing)
    skillMap: SkillMap | None = None  # the lesson-complete card: the skill map to draw (mockup 10), server/lesson/skillmap.py
    # v2 (all optional)
    hintStep: HintStep | None = None  # kind "hint": rung n of the ladder ("Hint 1 of 2")
    missingLines: list[MissingLine] | None = None  # Not yet: the step's lines, each there or missing
    fixCaption: str | None = None  # Not yet: what to do about them
    waiting: str | None = None  # footer while the engine waits ("Watching for a kernel to start")
    result: LessonResult | None = None  # kind "complete"


class NetworkDiagram(_Model):
    layers: list[int]
    activation: str
    derivatives: list[str]
    residual: str
    # True: a preview of the lesson's own network before the learner's first run (server/orchestrator/curated.py), not
    # a run: frames without epoch / loss, never a training run (mode forward / backward / stuck). The app shows
    # "Preview", no Epoch / Loss / sparkline, and keeps it out of the completion charts. Absent: a real run.
    preview: bool | None = None


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
    state: Literal["idle", "watching", "offtrack", "passed", "thinking", "busy"]  # busy (v2): the AI provider is overloaded
    detail: str | None = None  # v2: what the engine does right now, <= 6 words
    retryInS: float | None = None  # v2, with busy: retrying in this many seconds
    epoch: int | None = None  # lesson / step generation it was sent under (optional, additive)
    gen: int | None = None


class Error(_Model):
    message: str
    epoch: int | None = None
    gen: int | None = None


class LessonEnded(_Model):
    lessonId: str | None = None
    reason: str


CloudState = Literal["ok", "missing", "paused", "quota", "unauthorized", "offline", "off"]  # v2: missing = a proxy but no token yet; off = no proxy (BYOK or the engine's .env)
KeyState = Literal["ok", "missing", "invalid", "env"]  # "env" = falling back to the engine's .env


# ---------- v2 events (BUILD-PLAN W0-1) ----------
class EngineHello(_Model):
    """First message on every connect. capabilities: the v2 commands this engine understands."""
    version: str
    contract: str
    capabilities: list[str] = []
    restored: bool | None = None


class Health(_Model):
    items: list[HealthItem]
    ready: int
    total: int


class LessonPaused(_Model):
    reason: PauseReason
    title: str | None = None
    body: str | None = None
    stepId: str | None = None


class LessonResumed(_Model):
    reason: PauseReason | None = None
    stepId: str | None = None


class Blocker(_Model):
    kind: BlockerKind
    title: str | None = None
    body: str | None = None
    action: str | None = None
    rect: ScreenRect | None = None  # the real control to point at (spotlight.rect space)
    clear: bool | None = None  # it's gone


class Library(_Model):
    items: list[LibraryItem]


class LibraryItemEvent(_Model):
    item: LibraryItem
    steps: list[OutlineStep] | None = None
    overview: str | None = None


class ProgressEvent(_Model):
    """Every number from passed checks; None = not tracked yet (the app shows an empty state)."""
    skills: list[SkillTrackProgress] = []
    completed: list[CompletedLesson] = []
    week: WeekActivity | None = None
    review: ReviewQueue | None = None
    graph: SkillGraphInfo | None = None  # Nov 22 (Skills page), additive; None = the app draws `skills` tracks as chains


class ConfigStatus(_Model):
    anthropic: KeyState
    gemini: KeyState
    elevenlabs: KeyState
    tigerUrl: KeyState
    miyagiToken: KeyState | None = None  # v2: the install token
    cloud: CloudState | None = None  # v2: what the proxy said about it


class CloudTokenInvalid(_Model):
    """cloud.token_invalid: the proxy does not know this install's token (401). Never carries the token."""

    reason: Literal["unknown_token"] | None = None


class CloudNotice(_Model):
    """cloud.notice: the cloud would not take a shared lesson build claim (401 signin_required, 429 a cap). The lesson is
    built locally either way. Never carries the token or a user id."""

    reason: str  # the cloud's error or cap name: "signin_required", "lesson_builds", "anon_daily_cap", ...
    status: int  # its HTTP status: 401, 403 or 429
    resets_at: str | None = None  # ISO time the cap resets, when the cloud says


# ---------- ui-v4 (Nov 24): Adrian's v4 pages, skill tree round 3, bon. All additive; see events.ts and UI-V4.md ----------
# Times are ISO 8601 text with the learner's UTC offset; days are the learner's local date ("2026-11-24").
ACTIVITY_DAYS = 84  # Activity.days covers 12 weeks, ending today
RECENT_PASSED_MAX = 20  # Activity.recent carries at most this many


class ActivityDay(_Model):
    """One local day. minutes: practice minutes (a minute with a lesson running and the learner doing something in it);
    steps: counted passes that day."""
    date: str
    minutes: int = 0
    steps: int | None = None


class PassedStep(_Model):
    """One counted pass ("Recently passed"). key: step.passed.key; skills: the labels of skillIds, same order."""
    key: str
    lessonId: str
    lessonTitle: str
    stepId: str
    stepTitle: str
    at: str
    skillIds: list[str] | None = None
    skills: list[str] | None = None
    planId: str | None = None
    assisted: bool | None = None
    proofId: str | None = None


MilestoneKind = Literal["first_step", "first_lesson", "skill_mastered", "track_done", "plan_finished", "project_done", "steps"]


class Milestone(_Model):
    """Optional (the Nov 24 trim took milestones off Progress). count: for kind "steps"."""
    id: str
    kind: MilestoneKind
    title: str
    at: str
    skillId: str | None = None
    planId: str | None = None
    count: int | None = None


class ActivityTotals(_Model):
    lessonsFinished: int
    stepsPassed: int
    minutes: int | None = None  # None: not recorded yet
    skillsMastered: int | None = None


class ActivityWeek(_Model):
    minutes: int | None = None
    stepsPassed: int
    skillsMastered: int


class Activity(_Model):
    """activity: answer to activity.get, pushed again on change (at most every 10 s) to a connection that asked."""
    asOf: str
    tz: str | None = None
    minutesTracked: bool  # False: minutes are not recorded yet: every minutes is 0 / None
    days: list[ActivityDay]  # ACTIVITY_DAYS days, oldest first, every day present, the last is today
    week: ActivityWeek
    totals: ActivityTotals
    recent: list[PassedStep] = Field(default_factory=list, max_length=RECENT_PASSED_MAX)  # newest first
    milestones: list[Milestone] | None = None


class BonLevel(_Model):
    level: int
    name: str
    at: int
    has: str


# bon's eight levels (app features/buddy/growth.ts LEVELS): at = the passed steps where the level starts. Same table as events.ts.
BON_LEVELS: tuple[dict, ...] = (
    {"level": 1, "name": "Seed", "at": 0, "has": "one leaf"},
    {"level": 2, "name": "Sprout", "at": 3, "has": "two leaves"},
    {"level": 3, "name": "Shoot", "at": 8, "has": "a third leaf"},
    {"level": 4, "name": "Sapling", "at": 15, "has": "four leaves"},
    {"level": 5, "name": "Budding", "at": 25, "has": "a bud"},
    {"level": 6, "name": "In bloom", "at": 40, "has": "a blossom"},
    {"level": 7, "name": "Young tree", "at": 60, "has": "its first pad"},
    {"level": 8, "name": "Bonsai", "at": 90, "has": "a shaped tree"},
)


def bon_state(steps: int, *, grew: bool | None = None, last_key: str | None = None) -> dict:
    """The BonState payload for this many counted passes (the same rule as growth.ts progressOf)."""
    n = max(0, int(steps))
    i = max(k for k, lv in enumerate(BON_LEVELS) if n >= lv["at"])
    here = BON_LEVELS[i]
    out: dict[str, Any] = {"steps": n, "level": here["level"], "name": here["name"], "fraction": 1.0}
    if i + 1 < len(BON_LEVELS):
        up = BON_LEVELS[i + 1]
        out["next"] = {"level": up["level"], "name": up["name"], "at": up["at"], "left": up["at"] - n}
        out["fraction"] = round((n - here["at"]) / (up["at"] - here["at"]), 4)
    if grew is not None:
        out["grew"] = grew
    if last_key:
        out["lastKey"] = last_key
    return out


class BonNext(_Model):
    level: int
    name: str
    at: int
    left: int


class BonState(_Model):
    """bon's count, kept by the engine: lifetime passes counted, each step.passed.key at most once, never a skipped or
    already-done step. level / name from BON_LEVELS. grew: True only on the push from the pass that crossed a level."""
    steps: int = Field(ge=0)
    level: int = Field(ge=1, le=len(BON_LEVELS))
    name: str
    next: BonNext | None = None
    fraction: float | None = None
    grew: bool | None = None
    lastKey: str | None = None


# Plans: the catalog's shape (docs/ui-next/catalog/SCHEMA.md; catalog.json ships with the app and replaces packs.ts).
PlanGroup = Literal["language", "environment", "topic"]
PlanTopic = Literal["code", "data", "ai", "3d", "cad", "design", "tools"]
PlanCheckKind = Literal["run", "code", "scene", "file", "screen"]
PLAN_TOOL_IDS: tuple[str, ...] = ("vscode", "jupyter", "terminal", "browser", "blender", "freecad", "fusion", "onshape", "figma",
                                  "excel", "sheets", "unity", "godot", "xcode", "arduino", "docker", "rstudio")


class PlanTool(_Model):
    id: str  # one of PLAN_TOOL_IDS (a plain str, so a new tool is not rejected)
    label: str


class CatalogSkill(_Model):
    id: str  # "<prefix>.<name>" ("py.loops"), stable
    label: str
    needs: list[str] = []


class CatalogProject(_Model):
    title: str
    brief: str
    checks: list[str] = []


class CatalogLesson(_Model):
    title: str
    goal: str  # build it with learn {query: goal, mode: "lesson"}
    grows: list[str]
    minutes: int
    steps: int
    check: PlanCheckKind
    passes: str


class PlaylistVideo(_Model):
    id: str  # the YouTube video id
    title: str
    seconds: int | None = None


class CatalogPlaylist(_Model):
    planId: str
    title: str
    channel: str
    playlistId: str
    url: str
    videoCount: int
    totalSeconds: int
    videos: list[PlaylistVideo] = []


class CatalogPlan(_Model):
    id: str
    title: str
    group: PlanGroup
    topic: PlanTopic
    track: str
    tool: PlanTool
    also: list[str] = []
    level: Literal["start", "next"]
    needs: list[str] = []
    line: str
    project: CatalogProject
    skills: list[CatalogSkill]
    lessons: list[CatalogLesson]
    minutes: int | None = None  # added by build.mjs
    playlists: list[CatalogPlaylist] | None = None  # added by build.mjs from playlists.json


class Catalog(_Model):
    version: int
    plans: list[CatalogPlan]


class PlanLessonRef(_Model):
    """Which plan lesson a learn / learn_url / library.start is. index: 0-based in PlanState.lessons."""
    id: str
    index: int = Field(ge=0)


PlanSource = Literal["preset", "playlist", "goal"]
PlanLessonState = Literal["done", "in_progress", "next", "todo", "skipped"]


class PlanLessonSteps(_Model):
    done: int
    total: int


class PlanLesson(_Model):
    index: int
    title: str
    goal: str | None = None  # preset / goal plans: the learn query
    videoId: str | None = None  # playlist plans
    seconds: int | None = None
    minutes: int | None = None
    stepCount: int | None = None
    check: PlanCheckKind | None = None
    passes: str | None = None
    skillIds: list[str] | None = None
    state: PlanLessonState
    lessonId: str | None = None
    libraryId: str | None = None
    steps: PlanLessonSteps | None = None
    openedAt: str | None = None
    doneAt: str | None = None


class PlanProject(CatalogProject):
    state: Literal["locked", "ready", "done"] | None = None
    on: bool | None = None  # False: the learner switched the project off


class PlanState(_Model):
    """A plan in progress. id: the catalog id for a preset; "pl-<playlistId>"; "goal-<8 hex>"."""
    id: str
    title: str
    source: PlanSource
    catalogId: str | None = None
    playlistId: str | None = None
    url: str | None = None
    goal: str | None = None
    track: str | None = None
    tool: PlanTool | None = None
    lessons: list[PlanLesson]
    project: PlanProject | None = None
    done: int
    total: int
    nextIndex: int | None = None
    minutesLeft: int | None = None
    startedAt: str | None = None
    updatedAt: str | None = None
    finishedAt: str | None = None


LookupError_ = Literal["not_found", "private", "unsupported", "offline", "too_long", "busy", "unknown",
                       "blocked"]  # events.ts LookupError. blocked (any link): sign-in, paywall, robots.txt, or 401 / 403 / 451


class ProposedFrom(_Model):
    planId: str
    index: int


class ProposedLesson(_Model):
    title: str
    goal: str | None = None
    videoId: str | None = None
    seconds: int | None = None
    minutes: int | None = None
    grows: list[str] | None = None  # skill ids
    skills: list[str] | None = None  # their labels, same order
    from_: ProposedFrom | None = Field(default=None, alias="from")
    skip: bool | None = None
    why: str | None = None
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class HaveCount(_Model):
    done: int
    of: int


class PlanProposal(_Model):
    title: str
    source: Literal["playlist", "goal"]
    tool: PlanTool | None = None
    tools: list[PlanTool] | None = None
    lessons: list[ProposedLesson]
    skills: list[CatalogSkill] | None = None
    project: CatalogProject | None = None
    minutes: int | None = None
    fromPlans: list[str] | None = None
    have: HaveCount | None = None
    note: str | None = None


class Plans(_Model):
    items: list[PlanState] = []
    reqId: str | None = None


class PlaylistInfo(_Model):
    url: str
    reqId: str | None = None
    playlistId: str | None = None
    title: str | None = None
    channel: str | None = None
    videoCount: int | None = None
    totalSeconds: int | None = None
    videos: list[PlaylistVideo] = []
    proposing: bool | None = None
    proposal: PlanProposal | None = None
    error: LookupError_ | None = None


class PlanProposalEvent(_Model):
    goal: str
    reqId: str | None = None
    proposing: bool | None = None
    proposal: PlanProposal | None = None
    error: LookupError_ | None = None


class LinkSkill(_Model):
    id: str | None = None
    label: str


LinkKind = Literal["video", "playlist", "unsupported", "web", "github"]  # web / github: any link (Nov 24, ANY-LINK.md)
LINK_ANY_CAPABILITY = "link.any"  # listed in engine.hello.capabilities (a feature, not a command) once link.get / learn_url take any http(s) link


class LinkTeachable(_Model):
    """Why a web / github link can or cannot become a lesson. teachable = steps or code."""
    steps: bool  # it walks through things to do
    code: bool  # it has code to type or run


class LinkPreview(_Model):
    url: str
    reqId: str | None = None
    kind: LinkKind
    pending: bool | None = None
    title: str | None = None
    channel: str | None = None
    seconds: int | None = None
    videoId: str | None = None
    playlistId: str | None = None
    videoCount: int | None = None
    totalSeconds: int | None = None
    thumbnail: str | None = Field(default=None, pattern=r"^https://i\.ytimg\.com/")  # an i.ytimg.com URL only
    grows: list[LinkSkill] | None = None
    have: HaveCount | None = None
    finishesGoal: bool | None = None
    catalogId: str | None = None
    error: LookupError_ | None = None
    # any link (Nov 24, ANY-LINK.md): kinds web / github
    site: str | None = None  # "docs.python.org", "github.com/pallets/flask"
    author: str | None = None
    estMinutes: int | None = None  # about how long the lesson takes
    teachable: bool | None = None  # steps or code: Start; not teachable: why + "Just teach me" on its title
    teach: LinkTeachable | None = None
    why: str | None = None  # one plain line on why it is (not) teachable
    tools: list[LessonTool] | None = None  # the lesson tools it would use
    cached: bool | None = None  # this exact page (normalized URL + content) is already built: Start is instant
    finalUrl: str | None = None  # where the link ended after redirects (normalized), when that differs from url


# ---------- any link (Nov 24, ANY-LINK.md): the shared lesson cache key for a web / github source ----------
# A video is cached by its 11-character id; a page by (link_cache_key(normalized URL, content hash), LESSON_SCHEMA_VERSION), so
# the same page read through another link shape hits the same lesson, and an edited page (new content) builds a new one.
LINK_TRACKING_PARAMS = frozenset({"fbclid", "gclid", "dclid", "msclkid", "mc_cid", "mc_eid", "igshid", "ref", "ref_src", "_hsenc", "_hsmkt"})
LINK_CACHE_KEY_RE = re.compile(r"^[wg]_[0-9a-f]{32}$")  # w_: web, g_: github


def normalize_link_url(url: str) -> str:
    """The one spelling of an http(s) link used for cache keys: https, lower-case host without www. or a default port, no
    user info, no fragment, no tracking parameters (utm_* and LINK_TRACKING_PARAMS), the other parameters sorted, no trailing
    slash (but "/"); on github.com the owner and repo are lower case and ".git" is dropped. Raises ValueError for anything
    that is not an http(s) link with a host."""
    parts = urlsplit(url.strip())
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        raise ValueError("not an http(s) link")
    host = parts.hostname.lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    port = parts.port
    if port and port not in (80, 443):
        host = f"{host}:{port}"
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if len(path) > 1:
        path = path.rstrip("/") or "/"
    if host == "github.com":
        segs = path.split("/")
        if len(segs) > 1:
            segs[1] = segs[1].lower()
        if len(segs) > 2:
            segs[2] = segs[2].lower().removesuffix(".git")
        path = "/".join(segs)
    query = sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                   if not k.lower().startswith("utm_") and k.lower() not in LINK_TRACKING_PARAMS)
    return f"https://{host}{path}" + (f"?{urlencode(query)}" if query else "")


def link_content_hash(text: str) -> str:
    """sha256 hex of a page's readable text (what the lesson is built from, not the raw HTML), whitespace collapsed."""
    return hashlib.sha256(" ".join(text.split()).encode("utf-8")).hexdigest()


def link_cache_key(kind: Literal["web", "github"], url: str, content_hash: str) -> str:
    """The shared lesson cache id of a web / github source: w_ / g_ + 32 hex of sha256(normalized url + newline + content
    hash). The schema version rides beside it as for a video (?schema=LESSON_SCHEMA_VERSION)."""
    if kind not in ("web", "github"):
        raise ValueError(f"not a link kind: {kind!r}")
    digest = hashlib.sha256(f"{normalize_link_url(url)}\n{content_hash}".encode("utf-8")).hexdigest()
    return f"{kind[0]}_{digest[:32]}"


PROOF_TEXT_MAX = 2000  # characters of Proof.text
PROOF_OUTPUT_MAX = 1000  # characters of Proof.output
ProofKind = Literal["code", "cell", "command", "scene", "file", "screen"]


class ProofCheck(_Model):
    label: str
    detail: str | None = None


class Proof(_Model):
    """The learner's own work when a step passed. Kept on this Mac (~/miyagi/state) only, never sent anywhere; no
    screenshot is ever kept (kind "screen" carries the check's words only). file: relative to the lesson folder."""
    id: str
    kind: ProofKind
    key: str
    skillIds: list[str] = []
    lessonId: str
    lessonTitle: str | None = None
    stepId: str
    stepTitle: str
    at: str
    check: ProofCheck
    text: str | None = Field(default=None, max_length=PROOF_TEXT_MAX)
    output: str | None = Field(default=None, max_length=PROOF_OUTPUT_MAX)
    lang: str | None = None
    file: str | None = None
    line: int | None = None
    truncated: bool | None = None


class ProofEvent(_Model):
    items: list[Proof] = []
    skillId: str | None = None
    reqId: str | None = None


DataItemId = Literal["lesson_folder", "lesson_cache", "progress", "activity", "bon", "plans", "proofs", "notes", "screenshots", "logs"]
DataDeleteKind = Literal["notes", "lesson_cache", "progress", "proofs", "all"]  # the lesson folder is never deleted (the learner's own work)


class DataItem(_Model):
    """One row of Settings, Your data. path: "~/..." (home shortened). delete None: miyagi does not delete it."""
    id: str  # a DataItemId (a plain str, so a new row is not rejected)
    label: str
    where: Literal["this_mac", "not_kept", "account"]
    path: str | None = None
    bytes: int | None = None
    count: int | None = None
    detail: str | None = None
    delete: DataDeleteKind | None = None


class DataInventory(_Model):
    items: list[DataItem] = []
    totalBytes: int | None = None
    deleted: list[DataDeleteKind] | None = None  # a data.delete answer: the kinds really removed
    canDelete: list[DataDeleteKind] | None = None  # the kinds this engine can really delete today


# ---------- ambient help (Nov 24): help outside a lesson, in any app. See events.ts and AMBIENT-HELP.md ----------
AMBIENT_ERROR_LINES_MAX = 8  # error.seen.lines: the error's first lines as read on screen
AMBIENT_CONTEXT_LINES_MAX = 6  # on Explain: the most lines of context sent with the error
HELP_STEPS_MAX = 5  # help.steps carries 1 to this many steps
AMBIENT_CALLS_PER_HOUR = 20  # model calls (error.explain + help.ask, Haiku only) per rolling hour on this Mac; then error "cap"
AmbientErrorKind = Literal["python_traceback", "js_error", "compiler", "shell_exit", "notebook_cell", "app_dialog"]
AmbientFail = Literal["cap", "offline", "busy", "gone", "no_app", "failed"]
SetupScanError = Literal["no_project", "unreadable", "too_big"]


class AmbientTarget(_Model):
    """A place for bon to point at. Screen points, top-left origin (the ScreenRegion space); displayId None = the primary
    display. via: how the engine found it on this Mac (ax: accessibility tree, ocr: on-device text recognition). Ambient
    help never sends a screenshot or a crop."""

    x: float
    y: float
    w: float
    h: float
    displayId: int | None = None
    label: str | None = None  # <= 4 words
    app: str | None = None
    via: Literal["ax", "ocr"] | None = None


class SeenError(_Model):
    """error.seen: an error spotted on screen outside a lesson, read on this Mac only (nothing leaves it before Explain).

    id: stable for the same app + kind + title + file:line. title <= 80 characters. lines: as read, home shortened to ~,
    secret-looking values masked. rect: where the error text is. at: ISO time first seen; again: times seen again since.
    """

    id: str = Field(min_length=1, max_length=80)
    app: str
    kind: AmbientErrorKind
    title: str = Field(max_length=80)
    lines: list[str] = Field(default_factory=list, max_length=AMBIENT_ERROR_LINES_MAX)
    file: str | None = None
    line: int | None = None
    col: int | None = None
    exitCode: int | None = None  # shell_exit
    lang: str | None = None
    rect: AmbientTarget | None = None
    at: str
    again: int | None = None


class SeenErrorClear(_Model):
    id: str
    clear: Literal[True]  # the error is gone: fade its peek


ErrorSeen = SeenError | SeenErrorClear


class ErrorExplanation(_Model):
    """error.explanation: {id, pending: True} at once, then the explanation, or error (AmbientFail) + retryInS.
    title <= 8 words; why <= 40 words; fix <= 25 words. diff: unified diff for file (shown, never applied by itself).
    command: a terminal fix to copy. install: the row to install (Install -> setup.fix). target: where bon points."""

    id: str
    reqId: str | None = None
    pending: bool | None = None
    title: str | None = None
    why: str | None = None
    fix: str | None = None
    diff: str | None = None
    file: str | None = None
    line: int | None = None
    command: str | None = None
    install: SetupItem | None = None
    target: AmbientTarget | None = None
    error: AmbientFail | None = None
    retryInS: int | None = None


class HelpStep(_Model):
    """One step: text = one action (<= 12 words); detail <= 25 words. advance: click (the target is clicked), screen (the
    screen changes as the step says), next (only the learner's Next)."""

    id: str
    text: str
    detail: str | None = None
    target: AmbientTarget | None = None
    advance: Literal["click", "screen", "next"] | None = None


class HelpSteps(_Model):
    """help.steps: {pending: True} first, then 1..HELP_STEPS_MAX steps; re-sent (same reqId) as current moves or targets
    move. current: 0-based. done: the last step happened."""

    reqId: str | None = None
    app: str = ""
    goal: str = ""
    steps: list[HelpStep] = Field(default_factory=list, max_length=HELP_STEPS_MAX)
    current: int = Field(default=0, ge=0)
    done: bool | None = None
    pending: bool | None = None
    error: AmbientFail | None = None
    retryInS: int | None = None


class SetupEnv(_Model):
    python: str | None = None  # "~/code/app/.venv (Python 3.12.4)"
    node: str | None = None  # "node 20.11.1"


class SetupReport(_Model):
    """setup.report: what the open project needs on this Mac, read from its own files (no model call). root: home
    shortened. items: missing first; more: rows left out. scanning: a first quick answer, the full one follows."""

    reqId: str | None = None
    root: str | None = None
    name: str | None = None
    files: list[str] = Field(default_factory=list)
    items: list[SetupItem] = Field(default_factory=list)
    ready: int = 0
    total: int = 0
    more: int | None = None
    env: SetupEnv | None = None
    scanning: bool | None = None
    error: SetupScanError | None = None


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
    "screen.avoid": ScreenAvoid,
    "annotate": TypeAdapter(Annotate),  # Buddy draws (Nov 22)
    "answer.delta": AnswerDelta,  # Circle to ask, streamed (Nov 22)
    "answer.done": AnswerDone,  # fast circle to ask (Nov 22): the stream is over
    "video.seek": VideoSeek,
    "video.pause": Empty,
    "video.play": Empty,
    "card": Card,
    "diagram": Diagram,
    "speak": Speak,
    "metric": Metric,
    "status": Status,
    "error": Error,
    "cloud.token_invalid": CloudTokenInvalid,
    "cloud.notice": CloudNotice,
    "lesson.ended": LessonEnded,
    "setup.progress": SetupProgress,
    "config.status": ConfigStatus,
    # v2
    "engine.hello": EngineHello,
    "health": Health,
    "lesson.paused": LessonPaused,
    "lesson.resumed": LessonResumed,
    "blocker": Blocker,
    "library": Library,
    "library.item": LibraryItemEvent,
    "progress": ProgressEvent,
    # ui-v4 (Nov 24)
    "activity": Activity,
    "bon": BonState,
    "plans": Plans,
    "playlist": PlaylistInfo,
    "plan.proposal": PlanProposalEvent,
    "link.preview": LinkPreview,
    "proof": ProofEvent,
    "data": DataInventory,
    # ambient help (Nov 24)
    "error.seen": TypeAdapter(ErrorSeen),
    "error.explanation": ErrorExplanation,
    "setup.report": SetupReport,
    "help.steps": HelpSteps,
}

EngineEventType = Literal[
    "annotate",
    "answer.delta", "answer.done",
    "cloud.token_invalid", "cloud.notice",
    "search.result", "search.done", "lesson.building", "lesson.ready", "step.started",
    "check.updated", "step.passed", "offtrack", "spotlight", "video.seek", "video.pause",
    "video.play", "card", "diagram", "speak", "metric", "status", "error", "screen.seen", "config.status", "lesson.ended", "setup.progress", "lesson.updated",
    "screen.avoid",
    "engine.hello", "health", "lesson.paused", "lesson.resumed", "blocker", "library", "library.item", "progress",
    "activity", "bon", "plans", "playlist", "plan.proposal", "link.preview", "proof", "data",
    "error.seen", "error.explanation", "setup.report", "help.steps",
]


# ---------- App -> Engine commands ----------
class Learn(_Model):
    query: str
    mode: Literal["video", "lesson", "demo"] | None = None  # "lesson" = "Just teach me": no video search; "demo": the staged neural-net lesson (server/orchestrator/stage.py)
    plan: PlanLessonRef | None = None  # ui-v4: this lesson is lesson `index` of plan `id`


class LearnUrl(_Model):
    url: str
    transcriptOnly: bool | None = None  # the Build failed card's "Try transcript only": build from the transcript + title/chapters, no video model
    plan: PlanLessonRef | None = None  # ui-v4: this video is lesson `index` of plan `id` (a playlist plan)


class BuildLesson(_Model):
    resultIds: list[str]


ActionKind = Literal["back", "explain", "diagram", "show_me", "hint", "voice_toggle", "ask", "apply_fix",
                     "confirm", "undo", "open_editor", "resume", "end_lesson", "install", "install_all", "skip_setup", "open_in_browser",
                     "build", "pick_another", "download", "skip_step", "check_step", "use_this_folder", "run_command",
                     "retry", "start", "have_it", "get_it", "alternative",
                     "open_in_app"]  # open_in_app (Nov 24): an app lesson's setup card: open the lesson's scene in its desktop app (Blender, with the miyagi bridge); label setup.actionLabels.open_in_app; text? = tool id; holdVideo false
# have_it / get_it / alternative: a licensed app setup row (text = tool). start: "Start the lesson" on "Before you start" (step 1 waits for it)


class AskCapture(_Model):
    """Circle to ask, fast path (Nov 22): the circled region, already captured by the app's helper (miyagi-listen) while
    the keys were still held, so the engine skips its own capture after release. Rides on action ask with a region.

    path: a 0600 JPEG, cap-<uuid>.jpg in the per-user temp folder miyagi-capture (0700). The engine checks it (realpath
    inside that folder, that name, a regular file of this user with mode 0600), reads it and deletes it; the helper
    deletes it anyway about 30 s after writing. w / h: its pixels (long edge <= 1092). rect: the box really captured,
    in screen points (margin added, clamped to the display): crop pixel (px, py) -> screen point
    (rect.x + px * rect.w / w, rect.y + py * rect.h / h). None, or a file that is gone or fails a check: the engine
    captures as before. Used for this one ask only, never stored or logged. Reader: shared/capture_file.py.
    """

    path: str
    w: int
    h: int
    rect: ScreenRect
    displayId: int


class Action(_Model):
    kind: ActionKind
    # explain + text: text = the learner's selection (the drawer's "Explain more"): the engine answers with a card
    # {kind: "explain", title: "About `<start of the selection>`", body}. explain without text: the current step.
    text: str | None = None
    # ask + region (Circle to ask, Nov 22): the learner held Fn+Control and circled part of the screen. text = the
    # spoken words, or "What is this?" when nothing was said (also the engine's default for empty text). Works with
    # or without a lesson. The engine crops region, reads the text boxes inside it, answers with a card
    # {kind: "answer", askId, region}, then maybe annotate {marks: [{why: "answer", askId, ...}]}. The crop is used
    # for this one ask only, never stored or logged. Timing: the engine answers each circle ask within about 25 s
    # (circle_ask.ANSWER_WITHIN_S): one deadline, 22 s after the action arrives (circle_ask.ASK_DEADLINE_S), covers the
    # streamed answer, its one retry and the one-shot fallback (each starts only when enough of it is left, else the
    # failed card goes), so the app's pending-circle timeout (ASK_MAX_MS 30 s) stays above that. The overlay's click-through hard timeout covers only the drawing: it
    # goes back to click-through on release, without waiting for the answer.
    region: ScreenRegion | None = None
    source: str | None = None  # "typed" | "voice" | "circle"; a plain str so a new tag from the app is not rejected
    askId: str | None = None  # the app's id for this ask; the answer card echoes it
    capture: AskCapture | None = None  # ask + region (circle to ask): the region the app already captured (AskCapture)


class VideoState(_Model):
    t: float
    playing: bool


class EndLesson(_Model):
    pass


class OverlayBounds(_Model):
    rects: list[ScreenRect]


class ConfigKeys(_Model):
    """Bring-your-own-key. Keep in memory only; never log or echo these. Unknown names (from older app builds) are ignored."""

    model_config = ConfigDict(extra="ignore")

    anthropic: str | None = None
    gemini: str | None = None
    elevenlabs: str | None = None
    tigerUrl: str | None = None
    miyagiToken: str | None = None  # v2: the app's anonymous install token ("mi_...") for the miyagi cloud proxy; memory only
    miyagiCloud: str | None = None  # v2: the cloud proxy's https base URL


class CardShown(_Model):
    """card.shown: a `card` / the `offtrack` card became visible in the app's card slot (E14)."""

    stepId: str | None = None
    title: str = ""
    kind: str | None = None  # the card's kind, or "offtrack"


class CardClosed(_Model):
    """card.closed: that card left the slot. by: "user" | "replaced" | "timeout" | "hidden" (kept a plain str here so
    a new reason from the app is logged, not rejected). "user" / "timeout" lift the hold this card (matched by title)
    caused; "replaced" / "hidden" lift nothing."""

    stepId: str | None = None
    title: str = ""
    kind: str | None = None
    by: str | None = None


# ---------- v2 commands: the app sends one only when engine.hello.capabilities lists its type ----------
class HealthGet(_Model):
    pass


class PermissionOpen(_Model):
    """The engine reports the grant it needs; the APP opens System Settings itself (fixed URLs), never a URL from here."""

    kind: PermissionKind


class LibraryList(_Model):
    pass


class LibraryGet(_Model):
    id: str = Field(pattern=LIBRARY_ID_PATTERN)


class LibraryStart(_Model):
    """Start a cached lesson: zero model calls."""

    id: str = Field(pattern=LIBRARY_ID_PATTERN)
    plan: PlanLessonRef | None = None  # ui-v4: as Learn.plan


class ProgressGet(_Model):
    pass


class SetGoal(_Model):
    """Nov 22 (Skills page): the learner picked a capstone; answer with a fresh progress."""

    capstoneId: str


class SkillsAck(_Model):
    """Nov 22 (Skills page): the unlock events up to `until` (an event's `at`) have played."""

    until: str | int | float


class PanelState(_Model):
    """The lesson panel docked beside the editor (screen points); rect None = closed."""

    open: bool
    rect: ScreenRect | None = None


class AskWarm(_Model):
    """Nov 22 (push to talk speed): the push-to-talk hold passed the minimum and the mic is open; open or reuse the
    keep-alive links and warm the prompt cache for the ask. The app sends it on every hold that passes the minimum
    (never for a tap or an aborted chord). The engine always opens or reuses the links (free; keep-alive links close
    seconds after their last use) and throttles only the paid prompt-cache write (under the 5-minute cache lifetime).
    No reply. pttId: the hold's id, for logs only."""

    pttId: str | None = Field(default=None, max_length=64)
    source: str | None = Field(default=None, max_length=32)  # optional tag ("keydown"), for logs only


# ---------- engine commands the contract did not list yet (Nov 24 sync with server/orchestrator/main.py V2_COMMANDS) ----------
def _text80(v: Any) -> str:
    return " ".join(v.split())[:80] if isinstance(v, str) else ""


class ReviewStart(_Model):
    """Start review (sessions/review.py): replay the steps behind one mastered skill, no build, no model call. Both
    optional (none: the first review due); a value of the wrong type reads as absent, as the engine always did."""
    skillId: str = ""
    label: str = ""

    @field_validator("skillId", "label", mode="before")
    @classmethod
    def _clean(cls, v: Any) -> str:
        return _text80(v)


class DataDelete(_Model):
    """Delete my data, engine part. Today: the lesson notes (server/context), whatever `what` says. what (ui-v4): the
    DataDeleteKind values to remove; plain strs so an older engine never rejects a newer kind."""
    what: list[str] | None = None


# ---------- ui-v4 commands (Nov 24): sent only when engine.hello.capabilities lists the type ----------
class ActivityGet(_Model):
    pass


class BonGet(_Model):
    pass


class BonImport(_Model):
    """Once per Mac: the count growth.ts kept in localStorage. The engine keeps max(its count, steps) and adds seen."""
    steps: int = Field(ge=0, le=1_000_000)
    seen: list[str] | None = Field(default=None, max_length=400)


class PlansList(_Model):
    pass


class PlanStart(_Model):
    """Add a plan: catalogId (preset), playlistId + proposal (playlist), or proposal (goal)."""
    catalogId: str | None = Field(default=None, max_length=64)
    playlistId: str | None = Field(default=None, max_length=64)
    url: str | None = Field(default=None, max_length=500)
    goal: str | None = Field(default=None, max_length=300)
    proposal: PlanProposal | None = None
    reqId: str | None = Field(default=None, max_length=64)


class PlanRemove(_Model):
    id: str = Field(max_length=80)


class PlaylistGet(_Model):
    url: str = Field(max_length=500)
    reqId: str | None = Field(default=None, max_length=64)


class PlanPropose(_Model):
    goal: str = Field(min_length=1, max_length=300)
    tool: str | None = Field(default=None, max_length=32)
    reqId: str | None = Field(default=None, max_length=64)


class LinkGet(_Model):
    url: str = Field(max_length=500)
    reqId: str | None = Field(default=None, max_length=64)


class ProofGet(_Model):
    id: str | None = Field(default=None, max_length=80)
    skillId: str | None = Field(default=None, max_length=120)
    reqId: str | None = Field(default=None, max_length=64)


class DataGet(_Model):
    pass


# ---------- ambient help commands (Nov 24): sent only when engine.hello.capabilities lists the type ----------
class AmbientSet(_Model):
    """Spot errors on / off (None: unchanged; the engine starts with it off). mutedApps: app names never watched."""
    errors: bool | None = None
    mutedApps: list[str] | None = Field(default=None, max_length=50)


class ErrorExplain(_Model):
    """Explain pressed: the one moment the error leaves the Mac (redacted text, never a screenshot). -> error.explanation"""
    id: str = Field(min_length=1, max_length=80)
    reqId: str | None = Field(default=None, max_length=64)


class ErrorDismiss(_Model):
    id: str = Field(min_length=1, max_length=80)


class SetupScan(_Model):
    """path None: the folder open in the frontmost editor. -> setup.report"""
    path: str | None = Field(default=None, max_length=1024)
    reqId: str | None = Field(default=None, max_length=64)


class SetupFix(_Model):
    """Install one setup.report row through the existing install path. -> setup.progress, then setup.report"""
    tool: str = Field(min_length=1, max_length=80)
    root: str | None = Field(default=None, max_length=1024)
    reqId: str | None = Field(default=None, max_length=64)


class HelpAsk(_Model):
    """"How do I X" in the frontmost app, outside a lesson. app: the app frontmost before the ask field took focus."""
    text: str = Field(min_length=1, max_length=300)
    reqId: str | None = Field(default=None, max_length=64)
    app: str | None = Field(default=None, max_length=120)
    source: str | None = None  # "typed" | "voice" | "circle" (AskSource); a plain str, as Action.source


class HelpNav(_Model):
    """next / back -> help.steps with current moved; close: stop watching, no reply."""
    reqId: str | None = Field(default=None, max_length=64)
    to: Literal["next", "back", "close"]


APP_COMMANDS: dict[str, type[_Model]] = {
    "learn": Learn,
    "learn_url": LearnUrl,
    "build_lesson": BuildLesson,
    "action": Action,
    "video.state": VideoState,
    "overlay.bounds": OverlayBounds,
    "config.keys": ConfigKeys,
    "end_lesson": EndLesson,
    "card.shown": CardShown,
    "card.closed": CardClosed,
    # v2
    "health.get": HealthGet,
    "permission.open": PermissionOpen,
    "library.list": LibraryList,
    "library.get": LibraryGet,
    "library.start": LibraryStart,
    "progress.get": ProgressGet,
    "panel.state": PanelState,
    "set_goal": SetGoal,
    "skills.ack": SkillsAck,
    "ask.warm": AskWarm,
    "review.start": ReviewStart,
    "data.delete": DataDelete,
    # ui-v4 (Nov 24)
    "activity.get": ActivityGet,
    "bon.get": BonGet,
    "bon.import": BonImport,
    "plans.list": PlansList,
    "plan.start": PlanStart,
    "plan.remove": PlanRemove,
    "playlist.get": PlaylistGet,
    "plan.propose": PlanPropose,
    "link.get": LinkGet,
    "proof.get": ProofGet,
    "data.get": DataGet,
    # ambient help (Nov 24)
    "ambient.set": AmbientSet,
    "error.explain": ErrorExplain,
    "error.dismiss": ErrorDismiss,
    "setup.scan": SetupScan,
    "setup.fix": SetupFix,
    "help.ask": HelpAsk,
    "help.nav": HelpNav,
}

AppCommandType = Literal["learn", "learn_url", "build_lesson", "action", "video.state", "overlay.bounds", "config.keys", "end_lesson",
                         "card.shown", "card.closed",
                         "health.get", "permission.open", "library.list", "library.get", "library.start", "progress.get", "panel.state",
                         "set_goal", "skills.ack", "ask.warm", "review.start", "data.delete",
                         "activity.get", "bon.get", "bon.import", "plans.list", "plan.start", "plan.remove", "playlist.get", "plan.propose",
                         "link.get", "proof.get", "data.get",
                         "ambient.set", "error.explain", "error.dismiss", "setup.scan", "setup.fix", "help.ask", "help.nav"]

# v2: the command types an engine may list in engine.hello.capabilities.
V2_CAPABILITIES: tuple[str, ...] = ("health.get", "permission.open", "library.list", "library.get", "library.start", "progress.get", "panel.state",
                                    "ask.warm", "set_goal", "skills.ack", "review.start", "data.delete")
# ui-v4 (Nov 24): the commands an engine lists in engine.hello.capabilities once it answers them.
UI_V4_CAPABILITIES: tuple[str, ...] = ("activity.get", "bon.get", "bon.import", "plans.list", "plan.start", "plan.remove", "playlist.get",
                                       "plan.propose", "link.get", "proof.get", "data.get")
# ambient help (Nov 24, AMBIENT-HELP.md): the commands an engine lists in engine.hello.capabilities once it answers them.
AMBIENT_CAPABILITIES: tuple[str, ...] = ("ambient.set", "error.explain", "error.dismiss", "setup.scan", "setup.fix", "help.ask", "help.nav")
CONTRACT_VERSION = "2026-11-20"


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

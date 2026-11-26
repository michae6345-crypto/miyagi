/**
 * App <-> Engine contract. WebSocket at ws://localhost:8787 (override with ENGINE_URL).
 * Every message is JSON: { "type": <string>, "payload": <object> }.
 * RULE: add fields freely; never rename or remove one without a `contract:` PR + a ping to everyone.
 * Python mirror: shared/contracts/events.py (keep both in sync).
 */

// ---------- shared shapes ----------
export type StepStatus = "locked" | "active" | "passed" | "failed";
export type CheckStatus = "pending" | "pass" | "fail";
export type SourceKind = "video" | "blog" | "notebook" | "paper" | "repo";

export interface VideoSegment { videoId: string; start: number; end: number } // seconds
export interface Source { id: string; kind: SourceKind; title: string; url: string; meta?: string; videoId?: string }
export type StepKind = "code" | "run" | "read";   // code: type in the file · run: run a command · read: learn a concept first
/** Any link (Nov 24, ANY-LINK.md): where a web / github lesson's step comes from. url: the page (a #fragment when the engine knows the
 *  heading's anchor); heading: that section's heading text. Never a copy of the page's words. */
export interface PageRef { url: string; heading?: string }
/** One row of the setup gate. status: queued | installing | done | failed | skipped. phase (installing): starting | preparing | resolving | downloading | installing | retrying | verifying.
 *  pct / bytes / totalBytes: the current download (pip raw progress). errorCode: network | timeout | no_wheel | python_version | disk_full | conflict | build_failed |
 *  permission | broken_import | cancelled | skipped_incompatible | no_python | unknown. log: the installer's last lines (failed rows), for "Show details". */
export interface SetupGateItem { tool: string; label: string; status: "queued" | "installing" | "done" | "failed" | "skipped"; optional: boolean;
  phase?: string; pct?: number; bytes?: number; totalBytes?: number; attempt?: number; line?: string; elapsedS?: number;
  error?: string; errorCode?: string; note?: string; log?: string }
export interface SetupGate { phase: "idle" | "running" | "failed" | "done"; holds: boolean; items: SetupGateItem[]; done: number; total: number;
  current?: string; elapsedS?: number; startedAt?: number }   // startedAt: epoch ms the current round of installs began (the app counts elapsed time from it)
export interface StepSummary { id: string; index: number; title: string; video?: VideoSegment | null; kind?: StepKind; what?: string; estMinutes?: number; skillIds?: string[]; pageRef?: PageRef }   // pageRef (any link, Nov 24): a web / github lesson's step: the part of the page it comes from (ANY-LINK.md); the app may offer "Open this part"   // skillIds (Nov 22, Skills page): the SkillInfo ids this step builds evidence for   // what: what this step builds (<= 12 words), the plan line in the step list   // estMinutes: about how long this step takes (whole minutes); "about 35 min left" = the sum over the steps not passed yet
/** "Before you start" concept card (Just teach me): the pre-knowledge the steps rely on. diagramPrompt set = the app may ask for a picture with action {kind:"diagram", text:"primer:<id>"}. */
export interface PrimerItem { id: string; title: string; body: string; code?: string; diagramPrompt?: string }   // null/absent: no video (a "lesson" mode lesson)
/** Learn-anything screens (Just teach me; mockups 01 drawer v2, 02 concept panel, 03 "Before you start"). All optional: the app hides a part that is absent.
 *  Concept diagrams are NOT pre-built: for a concept chip / panel the app asks on demand with action {kind:"diagram", text:"<concept title>"} and gets a `diagram` event (kind "graph", server/diagrams). */
export interface LessonBuild { summary: string; outcome: string; estMinutes?: number }   // summary: what you'll build (<= 20 words); outcome: what the finished result looks like / does (<= 25 words); estMinutes: the whole lesson (= the sum of the steps' estMinutes)
export interface FlowBox { label: string; detail?: string; stepIndex?: number }   // one box of the "How it works" diagram (3-6, left to right): label <= 3 words; detail: a formula or <= 4 words; stepIndex: StepSummary.index of the step that builds this box (absent: no single step)
export interface Prerequisite { id: string; title: string; why: string; status: "passed" | "unknown"; evidence?: string }   // title <= 4 words; why <= 12 words; passed: a lesson completed on this Mac covered it (evidence "Passed in Python Calculator"); unknown: not seen yet (never a failure)
/** lesson.ready's outline (E23): EVERY step of the lesson from the first lesson.ready on, while the rest is still being written
 *  (lesson.updated then delivers the steps themselves), so "Step 1 of N · about M min" is right from the start and never jumps.
 *  count = the number of steps the lesson ends with; a row's index = that StepSummary.index once it arrives. */
export interface OutlineStep { index: number; title: string; kind?: StepKind; what?: string; estMinutes?: number; skillIds?: string[] }   // skillIds: as StepSummary.skillIds
export interface LessonOutline { count: number; steps: OutlineStep[]; estMinutes?: number }   // estMinutes: the whole lesson (the sum of the rows'), when every row has one
export interface LearnFirstItem { title: string; minutes: number; kind: "notebook" | "interactive" | "video" | "read"; covers: string }   // a short mini-lesson for a prerequisite not passed yet; covers: Prerequisite.id; the app starts one with learn {query: title, mode: "lesson"} ("video" kind: mode "video")
/** Circle to ask (Nov 22): the bounding box of the ink the learner drew while holding the push-to-talk keys (Fn+Control).
 *  Screen POINTS, TOP-LEFT origin, in Electron's global screen space (the spotlight.rect space: the primary display's frame
 *  starts at 0,0; another display has its own offset, maybe negative). displayId: Electron's Display.id, which on macOS is the
 *  CGDirectDisplayID the engine captures (server/screen/sck.py capture(display_id)). scale: that display's scaleFactor (pixels per point). */
export interface ScreenRegion { x: number; y: number; w: number; h: number; displayId: number; scale: number }
/** Where an ask came from. Absent: typed (or an older app). "circle": a circled region (action ask with region). */
export type AskSource = "typed" | "voice" | "circle"
/** On-screen coach (Nov 24): the desktop app a no-code lesson is done in (server/lesson/app_lesson.py: Blender, AutoCAD,
 *  Photoshop...). tool: the server.workspace.apps id ("blender"); label: its name ("Blender"); using: the app the learner
 *  really works in when it isn't the one the lesson names ("FreeCAD" for AutoCAD). Never set for a code or VS Code lesson. */
export interface LessonApp { tool: string; label: string; using?: string }
/** Buddy draws (Nov 22): one thing the app circles on screen with a hand-drawn stroke grown from the island (event `annotate`).
 *  x / y / w / h: screen points, the ScreenRegion space. displayId absent = the primary display (the spotlight.rect convention).
 *  why "answer": the thing a circle-to-ask answer names, inside the circled region (askId = that ask).
 *  why "point" (Nov 24, on-screen coach): only in an app lesson (lesson.app), ONE mark at a step start, a "Not yet" or Show me
 *  ("where?"), with text (+ keys). A mark with text is not timed (holdMs does not apply to it): it stays until the step passes
 *  or changes, the learner reaches it, Esc, lesson.ended or annotate {clear}. Other pointing still reaches the app as
 *  spotlight {rect, caption}, card.targets and offtrack targets, and is not repeated as annotate.
 *  label: <= 4 words, optional; the app may show it by the circle.
 *  id: stable per mark, so a re-sent annotate can keep a circle still drawn instead of drawing it again. */
export interface Annotation { id?: string; x: number; y: number; w: number; h: number; displayId?: number; label?: string;
                              why: "point" | "answer"; askId?: string; stepId?: string;
                              text?: string; keys?: string[] }   // on-screen coach (Nov 24), why "point" only: text = the step's action (<= 12 words), drawn next to the circle; keys = the shortcut, one keycap label per key pressed, in order (<= 3), spelled as bridge.platform.keys spells keys on this platform (Mac: modifier glyphs + key, e.g. "⇧A", "⌘S", "Tab", "G", "Numpad 1")

// ---------- Engine -> App events ----------
export interface EngineEvents {
  "search.result": { id: string; kind: SourceKind; title: string; meta: string; score: number; reason: string; thumbnail?: string;
                     style?: "coding" | "no-code" | "conceptual"; durationLabel?: string; long?: boolean;   // finder (E7): what kind of tutorial, "1 h 56 min · 30 chapters", > 45 min
                     chapters?: number; captions?: boolean;                                                // chapter count; YouTube captions available
                     url?: string; source?: string; videoId?: string; durationS?: number; channel?: string;   // finder extras (all optional)
                     verified?: boolean; warnings?: string[]; scoredBy?: string; watched?: string;
                     prerequisites?: string[]; codeNotes?: string; comments?: string };
  "search.done": { total: number };
  "lesson.building": { message: string; progress: number; failed?: boolean; elapsedS?: number;
                        stage?: BuildStage; phases?: BuildPhase[]; etaS?: number; source?: BuildSource;              // v2 (Home-Building): the current stage, the checklist rows, about how long is left (seconds), what it is built from
                        failCode?: BuildFailCode; failReason?: string; alternatives?: BuildAlternative[];             // v2 (Err-LessonBuildFailed), with failed: why in one plain sentence, and what to try instead
                        silent?: boolean };                                                                            // v2, with failed: the learner already moved on: drop the building UI, no failure card   // message = the stage (changes only with the stage); elapsedS = seconds since the build started (the 1 s heartbeat)   // progress 0..1 for the launcher; ~1/s while building; failed: true = the build ended in error (an `error` + status idle follow): drop the building UI
  "lesson.ready": { lesson: { id: string; title: string; sources: Source[]; complete?: boolean; builtBy?: "gemini" | "claude" | "mixed" | "chapters" | "unknown" | "curated"; provisional?: boolean;
                              goalMatch?: { score: number | null; note: string };
                              mode?: "video" | "lesson"; primer?: PrimerItem[]; overview?: string;
                              build?: LessonBuild; flow?: FlowBox[]; prerequisites?: Prerequisite[]; learnFirst?: LearnFirstItem[];
                              outline?: LessonOutline; origin?: BuildSource; app?: LessonApp };   // app (Nov 24): the desktop app of a no-code lesson, for the on-screen coach (absent: a code / VS Code lesson)
                   steps: StepSummary[]; replay?: boolean; buildS?: number };   // origin (any link, Nov 24): what the lesson was built from (kind "web" / "github": mode "lesson", no video; the app may show "From <site>" with an Open link)   // buildS: seconds from the learner's command (learn / learn_url / build_lesson) to this lesson.ready, only on a build's first lesson.ready (engine build metrics; optional, the app may ignore it)   // builtBy "curated": written by hand (the curated "Just teach me" / Demo lessons, server/orchestrator/curated.py), no model wrote it: no "Claude wrote this lesson" line   // replay: the SAME lesson again (an app reconnect / engine restore): keep its progress, never a new start or "Before you start"   // outline: every step from the start (absent: a build whose step count isn't known yet)   // build / flow / prerequisites / learnFirst: the learn-anything screens (see LessonBuild above)   // overview: "What we're building" (<= 60 words)   // primer: "Before you start" concepts (lesson mode)   // mode "lesson" ("Just teach me"): no video, no player events; the editor is full screen and each step spotlights where to type   // complete false = a long video is still building (see lesson.updated)
  /** a long video's next part was built: new steps APPENDED (ids never change, earlier steps never edited) */
  "lesson.updated": { steps: StepSummary[]; complete: boolean; parts?: { done: number; failed: number; total: number } };
  "step.started": { stepId: string; index: number; title: string; instructions: string; video?: VideoSegment | null; details?: string; kind?: StepKind; what?: string; why?: string; concepts?: string[]; code?: string; estMinutes?: number; replay?: boolean;
                    where?: string; then?: string };   // v2 (Les-Working): where = the line above the code ("Type this in the new cell"); then = the line under it ("Then run it with the arrow beside the cell.")   // replay: a reconnect's / restore's replay of the step already running (not a new step)   // estMinutes: about how long this step takes ("about 4 min")   // code: the exact code to type / command to run, in full (never truncated)   // what: what you build in this step (<= 12 words); why: what it means (<= 25 words); concepts: primer ids   // instructions: ONE concrete action ("Create calculator.py and type print(…)"); details: the full explanation; video null/absent: no player for this step
  "check.updated": { stepId: string; checkId: string; label: string; status: CheckStatus; detail?: string; epoch?: number; gen?: number };   // epoch / gen: the lesson and step generation the engine sent it under (optional, additive)
  "step.passed": { stepId: string; nextStepId?: string; pending?: boolean; skipped?: boolean; already?: boolean; summary?: string;
                   key?: string; counted?: boolean; assisted?: boolean; skillIds?: string[]; proofId?: string };   // ui-v4 (Nov 24), all optional: key = "<lessonId>:<stepId>", the pass's stable id (bon, activity.recent and mastery de-dupe on it); counted: this pass grew bon's count (not skipped, not already, never a key counted before; a `bon` push follows); assisted: passed after Show me's snippet, a level-3 hint or Do it for me (it counts for bon, not toward mastery); skillIds: the SkillInfo ids it is evidence for (as StepSummary.skillIds); proofId: the Proof kept for it (proof.get)   // summary (v2, Les-Passed / Prog-Step-Passed): what the learner just did, <= 12 words   // already: its code was already in the file (pasted ahead / Do it for me): passed without starting; ONE card "You already did steps 2–3" follows   // skipped: the learner pressed Skip (action skip_step): not a pass, never green  // pending: no next step YET (the next part is still building); the engine continues on lesson.updated
  "offtrack": {
    stepId: string;
    severity: "warn" | "fail";
    title: string;             // <= 8 words
    body: string;              // <= ~30 words
    diff?: { expected: string; yours: string; file?: string; line?: number; command?: string };   // command: a terminal fix ("Do it for me" copies it to the clipboard)
    citation?: { label: string; url: string };
    actions: Array<"explain" | "show_me" | "apply_fix" | "hint">;   // apply_fix = "Do it for me" (only at level 3)
    level?: 2 | 3;             // hint ladder: 2 = concept (no fix yet), 3 = exact fix + diff + apply_fix
    targets?: Array<{ boxId: number; label: string; text: string; rect: { x: number; y: number; w: number; h: number } }>;  // what the coach points at (screen points)   // lesson mode: ONE target, boxId 0 = the culprit lines the engine measured (label: the box's caption, text: those lines); it may come in a re-sent off-track (same card) once the box is measured; never in a reconnect's replay
    guidingQuestion?: string;  // a Socratic nudge to show under the body
    epoch?: number; gen?: number;   // the lesson and step generation the engine sent it under (optional, additive)
  };
  /** Screen-first: rect is in screen POINTS, TOP-LEFT origin (Electron convention), relative to the PRIMARY display's FULL frame (y=0 is the very top, menu bar included). v1 watches the primary display only. Same convention for overlay.bounds. */
  "spotlight": { rect: { x: number; y: number; w: number; h: number }; caption: string; app?: string; matched?: string; snippet?: string; zoom?: boolean } | { clear: true };   // snippet: code to type there (lesson mode / Show me), shown monospace under the caption   // zoom: the target is one of VS Code's own controls under 32 pt (the Run ▷, Toggle Panel, a tab's unsaved dot): show the loupe
  /** What the engine currently sees (debug HUD / optional). */
  "screen.seen": { app: string; summary: string; t: number };
  /** t9: VS Code's quick-pick (the input box at the top centre: command palette, kernel picker, "Select Interpreter") is open under Miyagi's
   *  overlay: move the card and the step pill off these rects. Same space as spotlight.rect (screen points, top-left origin). Sent only while a
   *  lesson is active and only when the set changes; rects [] = it closed: clear it (also drop it on lesson.ended). */
  "screen.avoid": { rects: { kind: "quickpick"; x: number; y: number; w: number; h: number }[] };
  /** Buddy draws (Nov 22): circle these on screen. The app draws a thin stroke from the island to each mark and a loose circle
   *  around it; the overlay stays click-through. A new annotate replaces the marks drawn before. The app fades them when the
   *  learner clicks inside one, the step changes, lesson.ended, or after holdMs (absent: the app's default, a few seconds).
   *  { clear: true }: fade every mark now. An app that ignores this event loses nothing (spotlight / targets still come).
   *  A mark with text (on-screen coach) ignores holdMs (see Annotation). */
  "annotate": { marks: Annotation[]; holdMs?: number } | { clear: true };
  /** Circle to ask, streamed (Nov 22; fast circle to ask, server/coach/fast_ask.py): the answer to action ask {askId} as the model
   *  writes it, so the first words show about 1 s after release. answer.delta: text = the NEW text to append to what came before
   *  for this askId (never the whole text so far), plain prose; seq counts up from 0 per ask. In order on the socket; the first
   *  delta for an askId opens the answer card, next to the circle. The model's first-line [DRAW:...] tag never reaches the app: it
   *  comes as `annotate`. answer.done: the stream is over; its `text` is the whole cleaned answer and the app MUST replace what the
   *  deltas built with it (deltas go out as the words arrive, so a sentence the engine flags as a prompt injection may have shown in
   *  them; done.text never has it). complete false: cut short (reason "refusal" | "max_tokens" | "error" | "moved_on"; moved_on: the
   *  step changed, a "moved on" card follows; refusal: text is "" so the declined words leave the screen, and a failed answer card
   *  follows). fallback true: the stream failed and a non-streaming retry answered. The full answer still comes after as the normal
   *  card {kind: "answer", askId, region}: it REPLACES the streamed text (title, body, actions), even when it differs (a fallback
   *  such as "Couldn't reach Claude"); a streaming app keeps its streamed card for that askId. Drop deltas for an askId the app no
   *  longer waits for, or that come after its card. The engine may send none (a slow or buffering cloud, a fallback card): the card
   *  alone is enough. An app that ignores these events loses nothing.
   *  Union of both readings (Nov 24 contract sync): delta.done true marks the last delta for an app that predates answer.done; an
   *  engine that sends answer.done never needs to set it. text may be missing (events.py AnswerDelta defaults it to ""): read a
   *  missing text as "". askId: the ask's own id; events.py also lets it be absent (an ask that carried none), which the app drops. */
  "answer.delta": { askId: string; text?: string; done?: boolean; seq?: number };
  "answer.done": { askId?: string; text: string; complete?: boolean; fallback?: boolean; reason?: string };
  "video.seek": { t: number; play: boolean };
  "video.pause": {};
  "video.play": {};
  /** card.kind (tile per kind, A15): explain / hint / answer = what the learner pressed or asked (Explain, Hint, a typed question); resume / setup / preflight: see their fields.
   *  "step": a step-control / step-status card the engine raises itself, never an answer: "Run it" (run_command), "Save calc.py", "calc.py is still empty", "Wrong folder?",
   *          "Looks done?" and every judge card (source "judge": "Not yet", "Already ahead?", "Save so I can check"). A neutral step tile, not the pink Hint one.
   *  "where": where to work when there is no box to draw ("Open calc.py", "Where to work", "Save it as calc.py"), usually with open_editor: Show me's answer, and Hint's
   *          when the step's code isn't on screen yet. The lilac Show me tile.
   *  "complete" (v2, Prog-Completion): the last step passed; carries skillMap + result. Typed as CardKindV2 (below), not in this union,
   *  so the app's exhaustive per-kind tables keep compiling; the engine sends it only when the app said so (a future capability). */
  "card": { epoch?: number; gen?: number; stepId?: string; kind: "explain" | "hint" | "answer" | "resume" | "setup" | "preflight" | "step" | "where"; title: string; body: string; videoJump?: { t: number; label: string };
            output?: string;              // monospace output block (e.g. the last lines of "Run it for me")
            dismissAfterMs?: number;      // the app closes the card on its own after this long (a one-line success: "requests installed ✓", no buttons)
            actions?: Array<"confirm" | "undo" | "apply_fix" | "open_editor" | "resume" | "end_lesson" | "install" | "install_all" | "skip_setup" | "open_in_browser" | "build" | "pick_another" | "download" | "skip_step" | "check_step" | "use_this_folder" | "run_command" | "retry" | "hint" | "show_me" | "explain" | "have_it" | "get_it" | "alternative" | "open_in_app">;    // open_in_app (Nov 24): an app lesson's setup card: open the lesson's scene in its desktop app (Blender: <lesson folder>/<stem>.blend, made from Blender's factory scene when missing, opened with the miyagi bridge so no add-on install is needed); label in setup.actionLabels.open_in_app ("Open in Blender"); action open_in_app {text?: the app's tool id, absent = the lesson's app}; the card sends setup.holdVideo false   // have_it / get_it / alternative (Nov 22): a licensed app row (AutoCAD): "I have it" (engine re-checks this Mac), "Get it" (vendor page), "Try <free alternative>"; text = the row tool, optional   // explain (Nov 25): on a "Not yet" / "Couldn't check" card, the same Explain as the off-track card (action explain, no text: the step explained)   // buttons on the card -> send `action {kind}`; retry ("Try again"): on the "Couldn't reach Claude" answer card; hint / show_me: the same actions as on the off-track card (judge "Not yet" card)
            items?: SetupItem[];          // kind "preflight": early tool check (a second card of the same kind replaces the first)
            warning?: string;             // kind "preflight": shown in amber when the video doesn't fit the goal (goalMatch.score < 0.5)
            recommended?: "build" | "pick_another";   // which button to make primary
            preflight?: PreflightInfo;    // kind "preflight": what the picked video is, before anything is built
            where?: string;               // coach (E5): where to go when the place isn't on screen ("Open app.py in VS Code"); shown without a dim
            setup?: { editorNeeded: boolean; items: SetupItem[];
                      editorLabel?: string | null;                       // "Visual Studio Code": the open_editor button reads "Open Visual Studio Code"
                      resources?: Array<{ name: string; url: string; kind: "repo" | "notebook" | "gist" | "file" }>;   // files the video links (action download)
                      actionLabels?: { [action: string]: string };       // button labels, e.g. download: "Download tutorial files"   // kind "setup": what the lesson needs on this Mac (one Install button per missing item -> action install {text: tool})
                      holdVideo?: boolean };   // Nov 22 (additive): true only when the current step truly needs a missing tool Install can get now. Otherwise false: setup is a companion, the video keeps playing while the card waits (no "Set up first" over the player, no "Waiting on setup" in the drawer)
            diff?: string;               // unified diff to preview ("Apply this fix?" -> confirm)
            targets?: Array<{ boxId: number; label: string; text: string; rect: { x: number; y: number; w: number; h: number } }>;
            guidingQuestion?: string;
            askId?: string;               // Circle to ask (Nov 22): kind "answer" to action ask {askId}: the app matches the answer to its circle
            region?: ScreenRegion;        // Circle to ask: the circled region the answer is about, echoed back so the card sits next to it
            source?: "judge";              // E5's step judge made it ("Looks done?" / "Not yet" / "Already ahead?" / "Save so I can check"): a step-status card, never an answer to the learner (sent as kind "step"); don't let it replace an answer card
            verdict?: "done" | "not_done"; // source "judge": Claude's verdict on the WHOLE step. done -> "Looks done?" (confirm = Yes); not_done -> "Not yet" (hint / show_me)
            checkIds?: string[];           // source "judge": the checks it is about (done: what Yes vouches for; not_done: what is still missing)
            skillMap?: SkillMap;           // the lesson-complete card (last step passed): the skill map to draw under "Congratulations" (mockup 10)
            hintStep?: { n: number; of: number };   // v2 (Les-Hint): kind "hint" is rung n of the ladder ("Hint 1 of 2")
            missingLines?: MissingLine[];  // v2 (Les-NotYet): the step's lines in order, each there or missing
            fixCaption?: string;           // v2 (Les-NotYet): what to do about them ("Add the first line, then run the cell")
            waiting?: string;              // v2 (Err-KernelInContext): the footer while the engine waits ("Watching for a kernel to start")
            checkIssue?: CheckIssue;       // Nov 25 (Check again): what a manual Check couldn't see (Screen Recording off, the checks failed, the cloud, the VS Code extension). blocking: the card is "Couldn't check" (title/body/next say why and what to do), never "Not yet"; else a note on the "Not yet"
            checkedAt?: number;            // Nov 25: epoch ms of the manual Check this card answers (a "Not yet" / "Couldn't check"): each press is a new answer, even with the same words
            result?: LessonResult };       // v2: kind "complete": what the lesson counted (never invented)
  "diagram": {
    kind: "network" | "gradients" | "heatmap" | "graph";
    caption: string;
    stepId?: string;
    data:
      | { layers: number[]; activation: string; derivatives: string[]; residual: string; preview?: boolean }   // network   // preview true: a picture of the lesson's own network before the learner's first run (curated.py), not a run: its frames have no epoch / loss and it never plays training (mode forward / backward / stuck); show a "Preview" label, no Epoch / Loss / loss sparkline, and keep it out of the completion screen's charts. Absent: a real run (the learner's terminal, Run it for me, the Demo's recorded runs), frames carry epoch + loss
      | { layers: string[]; epochs: number[]; norms: number[][] }                                     // gradients: norms[layer][epochIdx]
      | { x: number[]; t: number[]; predicted: number[][]; exact?: number[][] }                      // heatmap
      | GraphDiagramData;                                                                             // graph (any topic; server/diagrams)
  };
  "speak": { audioUrl: string; text: string };   // audioUrl is RELATIVE (e.g. /tts/<hash>.mp3): resolve it against the engine's http origin
  "metric": { runId: string; step: number; name: string; value: number };   // live curve feed
  "status": { state: "idle" | "watching" | "offtrack" | "passed" | "thinking" | "busy"; detail?: string; retryInS?: number; epoch?: number; gen?: number };   // epoch / gen: the lesson and step generation the engine sent it under (optional, additive)   // v2: detail = what the engine does right now ("Checking your cell", <= 6 words); busy = the AI provider is overloaded, the engine retries in retryInS seconds (no hue)
  /** install progress for one setup item (action install): lines while it runs, then {done, ok, error|version|url} */
  "setup.progress": { tool: string; line?: string; done?: boolean; ok?: boolean; error?: string; url?: string; version?: string; errorCode?: string; note?: string };   // errorCode / note (Nov 25): see SetupGateItem
  /** Setup gate (Nov 25, server/orchestrator/setup_gate.py): while the lesson's environment installs, the lesson waits. Sent on every change
   *  (progress at most twice a second). holds: the app keeps the video paused (and shows the loading panel) while true; when it turns false
   *  after holding, the step's clip starts. phase "idle" never holds. Buttons: action setup_retry {text?: tool} (failed rows), setup_continue
   *  ("Continue anyway"), setup_skip {text: tool} (optional rows only; cancels it if installing). */
  "setup.gate": SetupGate;
  /** Install token self-heal: the miyagi cloud does not know this install's token (the proxy answered 401, e.g. its database was
   *  reset). Sent once per token, and again when config.keys repeats that token. Never carries the token or its hash. The app drops
   *  the token, mints a new one (POST <host>/v1/install) and sends config.keys again, at most once per 5 minutes; a config.status
   *  with cloud "ok" (the new token's answer) cancels a heal still waiting. Not sent for an install an operator disabled (403):
   *  config.status.cloud says "unauthorized" instead. */
  "cloud.token_invalid": { reason?: "unknown_token" };
  /** The miyagi cloud would not take a shared lesson build claim (server/lesson/cloud_cache.py on_notice). The lesson is built on
   *  this Mac either way. reason: the cloud's error or cap name ("signin_required", "lesson_builds", "anon_daily_cap", ...);
   *  status: its HTTP status (401 sign-in required, 403, 429 a cap); resets_at: ISO time a cap resets, when the cloud says.
   *  The app shows its sign-in card (401) or cap line (429). Never carries the token or a user id. */
  "cloud.notice": { reason: string; status: number; resets_at?: string };
  /** the lesson was ended (end_lesson, a new learn, or POST /end): clear the pill, video, spotlight and cards */
  "lesson.ended": { lessonId?: string; reason: string };
  "error": { message: string; epoch?: number; gen?: number };

  // ---------- v2 (miyagi-v2 BUILD-PLAN W0-1). All additive; an app that ignores them keeps today's behaviour. ----------
  /** First message on every connect. contract: the contract date this engine speaks ("2026-11-20"); capabilities: the v2 COMMANDS it
   *  understands (e.g. "health.get", "library.start", "panel.state"). The app sends a v2 command only when it is listed here.
   *  restored: this connect resumed a lesson the engine kept (a restart / reconnect), not a fresh start. */
  "engine.hello": { version: string; contract: string; capabilities: string[]; restored?: boolean };
  /** Onboarding / Settings rows the ENGINE can probe (companion, VS Code, Python, cloud). Polled only on health.get, never prompts. */
  "health": { items: HealthItem[]; ready: number; total: number };   // ready = items with state "ok"
  /** The lesson waits for something outside it (VS Code closed, no kernel, offline): no checks run, nothing counts as Not yet. */
  "lesson.paused": { reason: PauseReason; title?: string; body?: string; stepId?: string };
  "lesson.resumed": { reason?: PauseReason; stepId?: string };
  /** One thing in the learner's way, shown in context (Err-KernelInContext / Err-VSCodeClosed / offline pill line).
   *  clear: true = it is gone (the same kind). rect: the real control to point at (screen points, spotlight.rect space). */
  "blocker": { kind: BlockerKind; title?: string; body?: string; action?: string; rect?: { x: number; y: number; w: number; h: number }; clear?: boolean };
  /** Answer to library.list: lessons built once and cached on this Mac (ready to start with zero model calls). */
  "library": { items: LibraryItem[] };
  /** Answer to library.get: one lesson's preview (Home-LessonDetail). */
  "library.item": { item: LibraryItem; steps?: OutlineStep[]; overview?: string };
  /** Answer to progress.get (Prog-Progress-Window). Every number comes from passed checks; null fields = not tracked yet. */
  "progress": Progress;

  // ---------- ui-v4 (Nov 24): Adrian's v4 pages, skill tree round 3, bon. All additive; shared/contracts/UI-V4.md has an example
  // of each. The app sends a ui-v4 command only when engine.hello.capabilities lists it (as every v2 command); an app that
  // ignores these events keeps today's behaviour. ----------
  /** Answer to activity.get, and pushed again when it changes (a counted step.passed, a lesson finished, practice minutes
   *  tallied: at most one push every 10 s), only to a connection that sent activity.get. Home's week, Progress's 12 weeks,
   *  the numbers under them and "Recently passed". */
  "activity": Activity;
  /** bon (the buddy): the engine's count of steps passed by doing them, and the level it makes (BON_LEVELS). Answer to bon.get
   *  and bon.import; pushed after every counted step.passed (grew: that pass crossed into a new level: the level-up moment). */
  "bon": BonState;
  /** The learner's plans (catalog presets, playlists, goals) with each lesson's state. Answer to plans.list / plan.start /
   *  plan.remove, and pushed when a plan lesson changes state (it started, its last step passed). */
  "plans": { items: PlanState[]; reqId?: string };
  /** Answer to playlist.get. Comes twice: first the videos (fast: the playlist page, no model call) with proposing true, then
   *  the same url again with proposal (lessons and skills matched to the videos) and proposing false. error: nothing to show. */
  "playlist": PlaylistInfo;
  /** Answer to plan.propose: a plan for a goal, drawn from catalog lessons first. proposing true: still working (an answer
   *  with the proposal follows). */
  "plan.proposal": { goal: string; reqId?: string; proposing?: boolean; proposal?: PlanProposal | null; error?: LookupError };
  /** Answer to link.get: what a pasted link is, for the preview card under the ask field (skill tree r3, home-link). Like
   *  playlist, a fast first answer (pending true: title and length only) may be followed by the full one. */
  "link.preview": LinkPreview;
  /** Answer to proof.get: the learner's own work behind passes (the skill panel's "The code you wrote" / "The check it
   *  passed"). Kept on this Mac only, never sent to the cloud. */
  "proof": { items: Proof[]; skillId?: string; reqId?: string };
  /** Answer to data.get and data.delete: what the engine keeps on this Mac, how big, and what it can delete (Settings, Your
   *  data). deleted: on a data.delete answer, the kinds really removed (a kind this engine cannot delete yet is left out). */
  "data": DataInventory;

  // ---------- ambient help (Nov 24): help outside a lesson, in any app. shared/contracts/AMBIENT-HELP.md has an example of
  // each. All additive; the app sends an ambient command only when engine.hello.capabilities lists it. ----------
  /** An error Miyagi spotted on screen outside a lesson (a traceback, a failed command, a dialog), read on this Mac only: nothing
   *  leaves the Mac until the learner presses Explain (error.explain). Sent only after ambient.set {errors: true}, never while a
   *  lesson runs (its off-track covers that), at most one every 5 s. The same error again (same id) sets `again`, never a new
   *  card. { id, clear: true }: it is gone (the next run printed no error, the dialog closed): fade its peek. */
  "error.seen": SeenError | { id: string; clear: true };
  /** Answer to error.explain: { id, pending: true } at once, then the explanation (or error: why there is none). */
  "error.explanation": ErrorExplanation;
  /** Answer to setup.scan, and sent again after each setup.fix finishes: what the open project needs on this Mac. Read from the
   *  project's own files on this Mac (requirements.txt, pyproject.toml, package.json, .nvmrc, Dockerfile ...), no model call. */
  "setup.report": SetupReport;
  /** Answer to help.ask: 1 to HELP_STEPS_MAX short steps in the frontmost app, each with a place for bon to point at. { pending:
   *  true } first, then the steps; sent again (same reqId) as the learner goes: current moves on when the step's target is
   *  clicked or the screen changes the way the step expects, and target rects move when the window does. done: the last step
   *  happened. */
  "help.steps": HelpSteps;
}

// ---------- v2 shapes ----------
/** card.kind including the v2 "complete" card (Prog-Completion). Read a card's kind as this where you handle it. */
export type CardKindV2 = EngineEvents["card"]["kind"] | "complete";
export type BuildStage = "watching" | "steps" | "checks" | "ready";   // Home-Building: Watching the video · Finding the steps · Writing the checks · Ready to start
export interface BuildPhase { id: BuildStage; label: string; state: "done" | "active" | "next"; detail?: string }   // detail: "6 steps found", "Step 4 of 6"
/** kind "web" (an article / docs page) and "github" (a repo's README or docs folder): any link (Nov 24, ANY-LINK.md), with url always set,
 *  site ("docs.python.org", "github.com/pallets/flask") and author when the page names one. An older app that only knows the first three
 *  kinds shows title and url. */
export type BuildSourceKind = "youtube" | "goal" | "library" | "web" | "github"
export interface BuildSource { kind: BuildSourceKind; title: string; channel?: string; durationS?: number; url?: string; site?: string; author?: string }
export type BuildFailCode = "unreadable_code" | "no_steps" | "too_long" | "no_captions" | "network" | "provider" | "unknown" | "no_content" | "blocked";   // no_content / blocked (any link): the page had no readable text (a script-only page, an image) / the site refused (sign-in, paywall, robots, 4xx)
/** A way out of a failed build: transcript only (learn_url {url, transcriptOnly: true}) or a cached library lesson (library.start {id}). */
export interface BuildAlternative { kind: "transcript" | "library"; title: string; meta?: string; id?: string; url?: string }
export interface MissingLine { text: string; state: "ok" | "missing" }
/** Nov 25: the engine's self-check on a manual Check (server/orchestrator/check_health.py; GET /health selfCheck, GET /selfcheck).
 *  No paid call: cloud is GET <cloud>/healthz. screen: is capture returning frames; ocr: does the frame have text; vscode: is the companion extension connected. */
export interface SelfCheck {
  screen?: "ok" | "off" | "error" | "paused" | "asleep" | "stale" | "none";
  ocr?: "ok" | "empty" | "unknown";
  vscode?: "connected" | "not_connected" | "unknown";
  cloud?: "ok" | "unreachable" | "unauthorized" | "paused" | "quota" | "missing" | "off" | "not_used" | "unknown";
}
/** Nov 25: card.checkIssue. kind -> the app's fix button: screen_off = Screen Recording settings; the rest = Check again. */
export interface CheckIssue {
  kind: "screen_off" | "screen_error" | "screen_stale" | "check_failed" | "cloud_unreachable" | "cloud_auth" | "vscode_ext";
  title: string;      // "Can't see your screen"
  body: string;       // what it couldn't do, in one sentence
  next: string;       // the next action, in one sentence ("Turn on Screen Recording for miyagi in System Settings, then press Check again.")
  blocking?: boolean; // true: the check couldn't run (the card is "Couldn't check"); false: a note under the "Not yet"
  selfCheck?: SelfCheck;
}
/** card kind "complete": what the lesson counted. Skips are counted as skips, never as passes. */
export interface LessonResult { passed: number; skipped: number; total: number; minutes?: number; lessonId?: string; title?: string }
export type HealthState = "ok" | "missing" | "off" | "checking" | "unknown";   // unknown = cannot tell without prompting (gray, never a failure)
export interface HealthItem { id: "vscode" | "companion" | "python" | "jupyter" | "engine" | "cloud" | string; label: string; state: HealthState; detail?: string; fix?: string }   // fix: the action kind that fixes it ("install", "open_editor")
export type PermissionKind = "screen" | "accessibility" | "automation";
export type PauseReason = "editor_closed" | "kernel" | "network" | "permission" | "user";
export type BlockerKind = "kernel" | "editor_closed" | "network";
export type LessonTool = "vscode" | "jupyter" | "terminal" | "excel";
/** A cached lesson. id matches ^[A-Za-z0-9_-]{1,64}$; never a path. progress: where the learner left it on this Mac. */
export interface LibraryItem { id: string; title: string; by?: string; steps: number; estMinutes?: number; tools: LessonTool[]; ready: boolean;
                               progress?: { stepIndex: number; stepTitle: string; total: number }; source?: BuildSource; updatedAt?: string;
                               teaches?: string[]; uses?: string[]; unlocks?: string[] }   // Nov 22 (Skills page), SkillInfo ids: teaches = skills this lesson builds; uses = skills it needs; unlocks = skills that become ready once it is done
export type SkillProgressState = "mastered" | "practicing" | "not_started";
export interface Progress {
  skills: Array<{ track: string; mastered: number; total: number; items: Array<{ label: string; state: SkillProgressState }> }>;
  completed: Array<{ lessonId: string; title: string; at: string }>;   // at: ISO date
  week?: { minutes?: number | null; streak?: number | null; days: boolean[] } | null;   // absent / null: activity not tracked yet (empty state)
  review?: { due: number; items: Array<{ label: string; file?: string; checks: number; when: string }> } | null;   // absent / null: no review scheduler yet
  /** Nov 22 (Skills page, app/agents/skills.md "Contract"), additive. absent / null: the app draws today's `skills` tracks as short chains. */
  graph?: SkillGraphInfo | null;
}

/** one tool a lesson needs (server/workspace setup check). For install.method "download" the app opens install.url instead of sending `install`. */
export interface SetupItem {
  tool: string; label: string; kind: "editor" | "app" | "runtime" | "cli" | "python_package" | "node_package" | "web_app"; why: string;   // node_package (ambient help, Nov 24): a project's package.json dependencies as one row
  needed: boolean; installed: boolean; ok: boolean; version?: string; minVersion?: string;
  install: { method: "brew" | "brew_cask" | "pip" | "npm" | "download" | "open" | "none"; command?: string; url?: string };  // web_app: method "open" + https url (nothing to install)   // npm (ambient help): `npm install` in the project folder (setup.fix only)
  from?: string;       // ambient help (Nov 24), setup.report: the project file (and line) that asked for it: "requirements.txt:4", ".nvmrc", "Dockerfile"
  // Nov 22, additive (server/workspace/apps.py). A licensed app (AutoCAD, Photoshop, Excel, MATLAB...) is never installed:
  // install.method is "download" with the vendor's page, and the row offers actions instead of Install.
  setupKind?: "package" | "free_app" | "licensed_app" | "web_app";   // package: pip / brew formula; free_app: allowlisted Homebrew cask (Install, confirm); licensed_app: never installed; web_app: Open
  actions?: Array<"install" | "have_it" | "get_it" | "alternative" | "skip">;   // this row's buttons; [] when it is ready. install -> action install {text: tool}; have_it / get_it / alternative -> action of that kind {text: tool}; skip -> skip_setup
  vendorUrl?: string;  vendorName?: string;          // licensed_app: the official download / trial page ("Get it") and its maker ("Autodesk")
  alternative?: { name: string; url: string; tool?: string };   // licensed_app: a free alternative ("FreeCAD"); action alternative {text: tool} (a desktop one then gets its own row with Install)
  haveIt?: boolean;    // the learner said "I have it" (kept per Mac) and the scan didn't find it: not missing, no buttons
  using?: string;      // the learner chose the free alternative instead (its name): not missing
  noMac?: boolean;     // the app has no macOS version (SOLIDWORKS, 3ds Max): offer the alternative
}

/** card kind "preflight" (server/preflight, <= 5 s after the pick, BEFORE build): build -> the lesson build starts; pick_another -> back to the results */
export interface PreflightInfo {
  videoId?: string; url: string;
  style?: "coding" | "no-code" | "conceptual";   // same vocabulary as search.result.style (E7); absent = unknown in time
  styleFrom?: "claude" | "finder";               // finder = Claude was late, the picked row's style was used
  topic?: string; durationS?: number; chapters: number;
  goalMatch?: { score: number | null; note: string };      // score 0..1, null when there was no goal
  buildPlan: { strategy: "whole" | "chapters"; estSecondsToFirstSteps: number;
               firstChapter: { index: number; lastIndex: number; title: string; start: number; end: number; window?: boolean } | null;
               firstHandsOn?: { index: number; title: string; start: number };
               windows?: number;
               skippedIntro?: { start: number; end: number } };   // a talk-only intro part 1 skips (seconds)
  editorNeeded?: boolean | null; partial: boolean;
}

/** kind "graph": nodes on a fixed grid (the app maps (col,row) to pixels); reference renderer: server/diagrams/render_svg.py */
export interface GraphDiagramData {
  title: string;
  layout: "flow" | "sequence" | "tree" | "data" | "architecture" | "git";
  direction: "LR" | "TB";
  grid: { cols: number; rows: number };
  nodes: Array<{ id: string; label: string; detail?: string; group?: string;
                 shape: "box" | "round" | "circle" | "data" | "commit"; emphasis: boolean; col: number; row: number }>;
  edges: Array<{ from: string; to: string; label?: string; style: "solid" | "dashed"; emphasis: boolean; order?: number }>;  // order: sequence only
  groups?: Array<{ id: string; label: string }>;
}

/** card.skillMap (server/lesson/skillmap.py): what the finished lesson taught, on one track (mockup 10 "Your skills").
 *  Nodes left to right in track order; edges connect them (arrows). Progress is never invented: mastered = every step behind
 *  the node passed (a check), learning = one of them was skipped (a ring), next = not learned yet (dashed). */
export type SkillState = "mastered" | "learning" | "next";
export interface SkillNode { id: string; label: string; state: SkillState; detail?: string }   // label <= 6 words; detail: a formula / "Step 2 skipped" / why it's next (<= 12 words), shown under the label
export interface SkillEdge { from: string; to: string }                                         // SkillNode ids
export interface SkillCross { track: string; label: string; to: string; note?: string }       // a dashed "shared idea" link from another track's concept (track "Math", label "Matrix multiply") to SkillNode.id `to`; note: the link's caption
export interface SkillNext { title: string; goal: string }                                     // an up-next lesson; goal = launcher text: start it with learn {query: goal, mode: "lesson"}
export interface SkillMap { track: string; headline: string; nodes: SkillNode[]; edges: SkillEdge[]; cross: SkillCross[]; next: SkillNext[] }   // track: "Neural networks"; headline: "A 1-4-4-1 network that learns the shape of sin(x). 8 mastered, 5 up next in Neural networks."

// ---------- Skills page: the skill graph (Nov 22, additive; app/agents/skills.md "Contract") ----------
/** A node is a skill built up across lessons ("Broadcasting"), never one lesson's step. Times are ISO text or epoch seconds.
 *  Every field but id / label / track is optional: the app derives what is missing (state from edges, review from review.dueAt). */
export type SkillGraphState = "locked" | "ready" | "practicing" | "mastered";   // review is a modifier on mastered (review.dueAt has come), never a demotion
export type SkillInfoKind = "skill" | "capstone";                                // capstone: a project node; its details are in SkillGraphInfo.capstones by the same id
export interface SkillLessonRef { lessonId: string; libraryId?: string; title?: string; stepIds?: string[]; role?: "teaches" | "uses" | "practices" }   // stepIds: the steps of that lesson that build this skill
export interface SkillInfo {
  id: string; label: string; track: string;                // label <= 4 words; track: the group header ("numpy")
  summary?: string;                                          // one line, <= 12 words
  kind?: SkillInfoKind; state?: SkillGraphState;
  evidence?: { done: number; total: number };                // steps passed of the steps behind it ("2 of 4 steps")
  masteredAt?: string | number; lastPracticedAt?: string | number;
  review?: { dueAt: string | number } | null;                // spaced review; due once dueAt has come
  lessons?: SkillLessonRef[];
  example?: { code?: string; caption?: string };             // "You'll be able to": a one-line example and its caption
  // ui-v4 (Nov 24, skill tree round 3), all optional:
  catalogId?: string;                                        // the catalog skill id this node is ("py.loops", catalog.json plans[].skills[].id)
  steps?: SkillStepRef[];                                    // the Steps zoom: every step behind it, passed or not, in lesson order
  mastery?: SkillMastery;                                    // how close to mastered under the two-day rule
  schedule?: SkillReviewInfo | null;                         // the spaced-review schedule in full (review above keeps only dueAt)
  proofIds?: string[];                                       // Proofs kept for its passes, newest first (proof.get {skillId} returns them)
  planIds?: string[];                                        // PlanState ids that grow it
}
export interface SkillGraphEdge { from: string; to: string; kind?: "requires" | "helps"; weight?: number }   // SkillInfo ids; kind absent = requires; weight 0..1 (helps only)
export interface SkillCapstone {
  id: string;                                                // the SkillInfo id of the capstone node
  brief?: string; requires?: string[];                       // requires: the skill ids the goal counts ("6 of 11 skills"); absent = every skill upstream of it
  checks?: string[]; starterFile?: string; estMinutes?: number;
  completedAt?: string | number | null;
  artifact?: { kind: "image" | "file"; path?: string; caption?: string } | null;   // the learner's own result; path is local, never a URL
}
/** What to do now: one skill and the lesson step that moves it. The app starts it with library.start {libraryId} or learn {query: goal, mode: "lesson"}. */
export interface SkillPick { skillId: string; lessonId?: string; libraryId?: string; lessonTitle?: string; stepIndex?: number; stepCount?: number; estMinutes?: number; goal?: string; why?: string }   // stepIndex: 0-based, as LibraryItem.progress.stepIndex; why <= 12 words ("gets you closer to Layers")
export interface SkillEvent { id: string; kind: "mastered" | "unlocked" | "review_due" | "capstone_done"; skillId: string; at: string | number; from?: string; lessonId?: string }   // from: the skill whose mastery unlocked this one
export interface SkillWeek { mastered?: number; keptFresh?: number; minutes?: number | null; days?: boolean[]; weeklyGoal?: number; goalAway?: number }   // days: Monday first; goalAway: skills left to the goal
export interface PortfolioItem { capstoneId: string; title: string; at: string | number; track?: string; skillIds?: string[]; artifact?: SkillCapstone["artifact"] }
export interface SkillGraphInfo {
  skills: SkillInfo[]; edges: SkillGraphEdge[]; capstones?: SkillCapstone[];
  goal?: string | null;                                      // a capstone id (set_goal); null = no goal picked yet (the goal picker shows)
  next?: SkillPick | null; alsoReady?: string[]; keepFresh?: string[];   // alsoReady, keepFresh: <= 3 skill ids each
  events?: SkillEvent[]; ackedUntil?: string | number | null;           // events newer than ackedUntil play once; the app then sends skills.ack {until}
  week?: SkillWeek | null; portfolio?: PortfolioItem[];
  // ui-v4 (Nov 24), all optional:
  tracks?: SkillTrackInfo[];                                 // the Tracks zoom and Progress's Tracks table, in display order
  masteryDays?: number;                                      // the mastery rule in use: passed unassisted on this many different local days (MASTERY_DAYS)
  reviewDays?: number[];                                     // the review schedule in use, days after mastery for each round (REVIEW_DAYS is the proposal)
}

/** Circle to ask, fast path (Nov 22): the circled region, already captured by the app's helper (miyagi-listen) while the keys
 *  were still held, so the engine skips its own capture after release. Rides on action ask {region, source: "circle", askId}.
 *  path: a 0600 JPEG, cap-<uuid>.jpg in the per-user temp folder miyagi-capture (0700). The engine checks it (realpath inside
 *  that folder, that name, a regular file of this user with mode 0600), reads it and deletes it; the helper deletes it anyway
 *  about 30 s after writing. w / h: its pixels (long edge <= 1092). rect: the box really captured, in screen points (the
 *  ScreenRegion space: margin added, clamped to the display), so crop pixel (px, py) is screen point
 *  (rect.x + px * rect.w / w, rect.y + py * rect.h / h). Absent, or a file that is gone or fails a check: the engine captures
 *  as before. Used for this one ask only, never stored or logged. */
export interface AskCapture { path: string; w: number; h: number; rect: { x: number; y: number; w: number; h: number }; displayId: number }

// ---------- ui-v4 shapes (Nov 24). Times are ISO 8601 text with the learner's UTC offset ("2026-11-24T16:12:00-08:00");
// days are the learner's local date ("2026-11-24"). shared/contracts/UI-V4.md: who sends each message, when, with examples. ----------

/** Activity: how many local days `days` covers (12 weeks, ending today). */
export const ACTIVITY_DAYS = 84
/** Activity: how many passed steps `recent` carries at most. */
export const RECENT_PASSED_MAX = 20
/** One local day. minutes: practice minutes that day (a minute with a lesson running and the learner doing something in it:
 *  an edit, a save, a run, a check, the lesson video playing); steps: steps passed that day (counted passes only). */
export interface ActivityDay { date: string; minutes: number; steps?: number }
/** One counted pass, for "Recently passed" (Home, Progress) and the skill panel. key: step.passed.key. skills: the labels of
 *  skillIds, in the same order (the table's Skill tag). planId: the plan the lesson belongs to, when it does. */
export interface PassedStep { key: string; lessonId: string; lessonTitle: string; stepId: string; stepTitle: string; at: string;
                              skillIds?: string[]; skills?: string[]; planId?: string; assisted?: boolean; proofId?: string }
export type MilestoneKind = "first_step" | "first_lesson" | "skill_mastered" | "track_done" | "plan_finished" | "project_done" | "steps"
/** A dated first or a round number ("First lesson finished", "50 steps passed"). Optional: the Nov 24 trim took milestones off
 *  Progress, so an app may ignore them and an engine may send none. count: for kind "steps". */
export interface Milestone { id: string; kind: MilestoneKind; title: string; at: string; skillId?: string; planId?: string; count?: number }
export interface ActivityTotals { lessonsFinished: number; stepsPassed: number; minutes: number | null; skillsMastered?: number }   // all time on this Mac; minutes null: not recorded yet
export interface Activity {
  asOf: string;                                              // when this snapshot was made
  tz?: string;                                               // the IANA zone the days are cut in ("America/Los_Angeles")
  minutesTracked: boolean;                                   // false: this engine does not record minutes yet: every minutes is 0 / null; show steps, never "0 min"
  days: ActivityDay[];                                       // ACTIVITY_DAYS days, oldest first, every day present (0 = nothing), the last is today
  week: { minutes: number | null; stepsPassed: number; skillsMastered: number };   // this week, Monday to today (Home's rail, Progress's "This week")
  totals: ActivityTotals;
  recent: PassedStep[];                                      // newest first, at most RECENT_PASSED_MAX
  milestones?: Milestone[];                                  // oldest first
}

/** bon's eight levels (features/buddy/growth.ts LEVELS, Adrian Nov 23): at = the passed steps where the level starts. The engine
 *  computes BonState.level from these; both files carry the same table (the contract parity test checks it). */
export interface BonLevel { level: number; name: string; at: number; has: string }
export const BON_LEVELS: readonly BonLevel[] = [
  { level: 1, name: "Seed", at: 0, has: "one leaf" },
  { level: 2, name: "Sprout", at: 3, has: "two leaves" },
  { level: 3, name: "Shoot", at: 8, has: "a third leaf" },
  { level: 4, name: "Sapling", at: 15, has: "four leaves" },
  { level: 5, name: "Budding", at: 25, has: "a bud" },
  { level: 6, name: "In bloom", at: 40, has: "a blossom" },
  { level: 7, name: "Young tree", at: 60, has: "its first pad" },
  { level: 8, name: "Bonsai", at: 90, has: "a shaped tree" }
]
/** bon's count, kept by the engine (~/miyagi/state) so it survives the app's storage and every window agrees.
 *  steps: lifetime passes counted, each step.passed.key at most once, never a skipped or already-done step (an assisted pass counts).
 *  level / name: BON_LEVELS for steps. next: the level after it (absent at Bonsai); fraction: 0..1 through this level (1 at the last).
 *  grew: true only on the push from the pass that crossed into `level`; lastKey: that pass's key. */
export interface BonState { steps: number; level: number; name: string; next?: { level: number; name: string; at: number; left: number };
                            fraction?: number; grew?: boolean; lastKey?: string }

// Plans. The catalog (Adrian's docs/ui-next/catalog, SCHEMA.md) ships with the app as catalog.json and replaces
// features/library/presets/packs.ts; these types are its shape, so the engine can read the same file for plan.propose.
export type PlanGroup = "language" | "environment" | "topic"                   // a coding language · an app or tool you work in · a library or subject on top of one
export type PlanTopic = "code" | "data" | "ai" | "3d" | "cad" | "design" | "tools"   // the filter tab
export type PlanToolId = "vscode" | "jupyter" | "terminal" | "browser" | "blender" | "freecad" | "fusion" | "onshape" | "figma" | "excel"
                       | "sheets" | "unity" | "godot" | "xcode" | "arduino" | "docker" | "rstudio"
export type PlanCheckKind = "run" | "code" | "scene" | "file" | "screen"     // reads what the program prints · the file typed · the model in the app · a saved file · the window
export interface PlanTool { id: PlanToolId | string; label: string }
export interface CatalogSkill { id: string; label: string; needs: string[] }  // id "<prefix>.<name>" ("py.loops"), stable; label <= 18 characters
export interface CatalogProject { title: string; brief: string; checks: string[] }   // made alone at the end; exactly 3 checks a machine could verify
export interface CatalogLesson { title: string; goal: string; grows: string[]; minutes: number; steps: number; check: PlanCheckKind; passes: string }   // goal: build it with learn {query: goal, mode: "lesson"}
export interface PlaylistVideo { id: string; title: string; seconds?: number }   // id: the YouTube video id
export interface CatalogPlaylist { planId: string; title: string; channel: string; playlistId: string; url: string; videoCount: number; totalSeconds: number; videos: PlaylistVideo[] }
export interface CatalogPlan { id: string; title: string; group: PlanGroup; topic: PlanTopic; track: string; tool: PlanTool; also: string[];
                               level: "start" | "next"; needs: string[]; line: string; project: CatalogProject; skills: CatalogSkill[]; lessons: CatalogLesson[];
                               minutes?: number; playlists?: CatalogPlaylist[] }   // minutes / playlists: added by build.mjs (the lessons' sum; catalog/playlists.json)
export interface Catalog { version: number; plans: CatalogPlan[] }

/** Which plan lesson a learn / learn_url / library.start is. index: 0-based in PlanState.lessons. */
export interface PlanLessonRef { id: string; index: number }
export type PlanSource = "preset" | "playlist" | "goal"
export type PlanLessonState = "done" | "in_progress" | "next" | "todo" | "skipped"   // next: the one Continue starts (exactly one, until the plan is done)
export interface PlanLesson {
  index: number; title: string;
  goal?: string;                                             // preset / goal plans: the learn query
  videoId?: string; seconds?: number;                        // playlist plans: the video (learn_url https://www.youtube.com/watch?v=<videoId>)
  minutes?: number; stepCount?: number; check?: PlanCheckKind; passes?: string;   // from the catalog lesson, when there is one
  skillIds?: string[];                                       // the skills it grows (catalog ids for presets)
  state: PlanLessonState;
  lessonId?: string; libraryId?: string;                     // once built: the engine's lesson id, and its library id (library.start resumes it)
  steps?: { done: number; total: number };                   // in_progress: "step 3 of 4"
  openedAt?: string; doneAt?: string;
}
export interface PlanState {
  id: string;                                                // the catalog id for a preset ("intro-blender"); "pl-<playlistId>"; "goal-<8 hex>"
  title: string; source: PlanSource;
  catalogId?: string; playlistId?: string; url?: string; goal?: string;
  track?: string; tool?: PlanTool;
  lessons: PlanLesson[];
  project?: (CatalogProject & { state?: "locked" | "ready" | "done"; on?: boolean }) | null;   // on false: the learner switched the project off (playlist plans)
  done: number; total: number;                               // lessons done of lessons in the plan (skipped lessons are not done)
  nextIndex?: number | null;                                 // the next lesson; null: every lesson is done
  minutesLeft?: number | null;                               // the lessons not done, by their minutes (or video length)
  startedAt?: string; updatedAt?: string; finishedAt?: string | null;
}
export type LookupError = "not_found" | "private" | "unsupported" | "offline" | "too_long" | "busy" | "unknown" | "blocked"   // unsupported: not a link the engine can read (before any link: not a YouTube video / playlist link; with "link.any": not http(s), or a file type it cannot read such as a zip); busy: the AI provider is overloaded, try again; blocked (any link): the site needs a sign-in, a paywall, robots.txt says no, or it answered 401 / 403 / 451
/** A lesson a playlist or goal plan would have. from: the catalog lesson it is (goal plans draw from the catalog first). skip: the
 *  engine suggests leaving it out (a talk-only intro, a video for another OS); the learner can flip it. */
export interface ProposedLesson { title: string; goal?: string; videoId?: string; seconds?: number; minutes?: number;
                                  grows?: string[]; skills?: string[]; from?: { planId: string; index: number }; skip?: boolean; why?: string }   // grows: skill ids; skills: their labels, same order
export interface PlanProposal {
  title: string; source: "playlist" | "goal";
  tool?: PlanTool; tools?: PlanTool[];                       // the tool the plan uses; tools: the choices offered ("Work in FreeCAD / Fusion / Onshape")
  lessons: ProposedLesson[];
  skills?: CatalogSkill[];                                   // the skills it grows, with needs (the skill tree draws them)
  project?: CatalogProject | null;
  minutes?: number;                                          // lessons + project
  fromPlans?: string[];                                      // catalog plan ids it drew from
  have?: { done: number; of: number };                       // skills the learner already has of the ones it uses ("You already have 8 of the 13")
  note?: string;                                             // one line under the table ("Built from two plans. Lessons you would not need are left out.")
}
export interface PlaylistInfo {
  url: string; reqId?: string;
  playlistId?: string; title?: string; channel?: string; videoCount?: number; totalSeconds?: number;
  videos: PlaylistVideo[];                                   // in playlist order; [] with error
  proposing?: boolean;                                       // true: proposal follows in a second playlist event
  proposal?: PlanProposal | null;
  error?: LookupError;
}

// Skill tree (round 3: tracks -> skills -> steps). A step's skills are StepSummary.skillIds / step.passed.skillIds.
/** Mastered = passed unassisted on MASTERY_DAYS different local days (Adrian's rule). */
export const MASTERY_DAYS = 2
/** Adrian's review schedule: days after mastery for each review round. The engine says which it uses in SkillGraphInfo.reviewDays
 *  (sessions/review.py has 1, 3, 7, 14, 30 today). */
export const REVIEW_DAYS: readonly number[] = [3, 7, 21, 60]
export interface SkillStepRef { key?: string; lessonId: string; lessonTitle?: string; stepId: string; title: string; passed: boolean; at?: string; assisted?: boolean }   // key: step.passed.key once passed
export interface SkillMastery { need: number; days: string[]; assisted?: number }   // days: the distinct local dates with an unassisted pass (mastered when days.length >= need); assisted: passes that did not count toward it
export interface SkillReviewInfo { dueAt: string; round: number; interval: number; lastAt?: string; lastResult?: "pass" | "miss" }   // round: 0-based into reviewDays; interval: days this round waits; a miss starts over at round 0
export interface SkillTrackInfo { id: string; label: string; mastered: number; total: number; next?: string | null; lastPracticedAt?: string; planIds?: string[] }   // next: the SkillInfo id to do next on this track; null: the track is done
/** The most a Proof's text carries (characters); output gets PROOF_OUTPUT_MAX. Longer work is cut and truncated is true. */
export const PROOF_TEXT_MAX = 2000
export const PROOF_OUTPUT_MAX = 1000
export type ProofKind = "code" | "cell" | "command" | "scene" | "file" | "screen"
/** The learner's own work at the moment a step passed: the code they wrote (code), a notebook cell and what it printed (cell), the
 *  command and its output (command), the scene facts read from the app (scene), a saved file's name and size (file), or only the
 *  check's words (screen: no screenshot is ever kept). Stored on this Mac (~/miyagi/state), never sent anywhere, removed by
 *  data.delete "proofs" or "progress". file: relative to the lesson folder; line: 1-based where text starts in it. */
export interface Proof { id: string; kind: ProofKind; key: string; skillIds: string[]; lessonId: string; lessonTitle?: string; stepId: string; stepTitle: string; at: string;
                         check: { label: string; detail?: string }; text?: string; output?: string; lang?: string; file?: string; line?: number; truncated?: boolean }
/** link.get's answer. kind "playlist": the full plan comes from playlist.get. grows: the skills it would grow (labels, with ids
 *  when they match the learner's graph). thumbnail: an https://i.ytimg.com URL only. catalogId: a catalog plan it matches. */
export interface LinkPreview { url: string; reqId?: string; kind: LinkKind; pending?: boolean;
                               title?: string; channel?: string; seconds?: number; videoId?: string; playlistId?: string; videoCount?: number; totalSeconds?: number;
                               thumbnail?: string; grows?: Array<{ id?: string; label: string }>; have?: { done: number; of: number };
                               finishesGoal?: boolean; catalogId?: string; error?: LookupError;
                               site?: string; author?: string; estMinutes?: number; teachable?: boolean; teach?: LinkTeachable; why?: string;
                               tools?: LessonTool[]; cached?: boolean; finalUrl?: string }
/** Any link (Nov 24, ANY-LINK.md). link.preview kind "web": an article or docs page; "github": a github.com repo (its README, or a
 *  docs folder / file in it). The engine sends these only when engine.hello.capabilities lists LINK_ANY_CAPABILITY; an older
 *  engine answers kind "unsupported" for a link that is not YouTube. */
export type LinkKind = "video" | "playlist" | "unsupported" | "web" | "github"
/** engine.hello.capabilities lists this (a feature, not a command) once link.get and learn_url take any http(s) link. */
export const LINK_ANY_CAPABILITY = "link.any"
/** Why a web / github link can or cannot become a lesson. steps: it walks through things to do; code: it has code to type or
 *  run. teachable = steps || code. A page with neither (news, an essay, a landing page) is not teachable: the launcher says why
 *  (LinkPreview.why, one plain line) and offers "Just teach me" on its title instead of Start. */
export interface LinkTeachable { steps: boolean; code: boolean }
//  LinkPreview (any link): site: "docs.python.org" / "github.com/pallets/flask"; author: when the page names one; estMinutes: about
//  how long the lesson takes (whole minutes, from the page's length and code); teachable / teach / why: see LinkTeachable; tools:
//  the lesson tools it would use; cached: a lesson for this exact page (same normalized URL and content) is already built, on this
//  Mac or in the shared lesson cache, so Start is instant; finalUrl: where the link ended after redirects (normalized) when that
//  differs from url. thumbnail stays i.ytimg.com only: the app never loads an image from a pasted site.

// Settings, Your data.
export type DataItemId = "lesson_folder" | "lesson_cache" | "progress" | "activity" | "bon" | "plans" | "proofs" | "notes" | "screenshots" | "logs"
export type DataDeleteKind = "notes" | "lesson_cache" | "progress" | "proofs" | "all"   // progress: history, skills, reviews, activity, bon and plans; all: every kind (the lesson folder is never deleted: it is the learner's own work)
/** One row of "Your data". where "this_mac": stored at path; "not_kept": used and dropped (screenshots: path absent); "account":
 *  kept by miyagi-cloud (the engine never says this about its own data). bytes / count: null when unknown. delete: the
 *  data.delete kind that removes it; null: miyagi does not delete it (the lesson folder: the app shows Open, not Clear). */
export interface DataItem { id: DataItemId | string; label: string; where: "this_mac" | "not_kept" | "account"; path?: string; bytes?: number | null; count?: number | null;
                            detail?: string; delete?: DataDeleteKind | null }
export interface DataInventory { items: DataItem[]; totalBytes?: number | null; deleted?: DataDeleteKind[]; canDelete?: DataDeleteKind[] }   // path: "~/..." (home shortened); canDelete: the kinds this engine can really delete today

// ---------- ambient help shapes (Nov 24, shared/contracts/AMBIENT-HELP.md) ----------
/** The most lines error.seen.lines carries: the error's first lines as read on screen. */
export const AMBIENT_ERROR_LINES_MAX = 8
/** On Explain, the most lines around the error (source lines at file:line, or the command before a failed one) sent with it. */
export const AMBIENT_CONTEXT_LINES_MAX = 6
/** help.steps carries 1 to this many steps. */
export const HELP_STEPS_MAX = 5
/** Model calls ambient help may make in any rolling hour on this Mac (error.explain and help.ask together, Haiku only). The
 *  next one is answered with error "cap" and retryInS. */
export const AMBIENT_CALLS_PER_HOUR = 20
export type AmbientErrorKind = "python_traceback" | "js_error" | "compiler" | "shell_exit" | "notebook_cell" | "app_dialog"
/** Why an ambient answer has nothing: cap = AMBIENT_CALLS_PER_HOUR reached (retryInS says when); offline = no network / cloud;
 *  busy = the AI provider is overloaded; gone = the error id or help reqId is no longer held (dismissed, cleared, too old);
 *  no_app = help.ask found no app to help with; failed = anything else. */
export type AmbientFail = "cap" | "offline" | "busy" | "gone" | "no_app" | "failed"
/** A place on screen for bon to point at (the buddy stroke / spotlight). x / y / w / h: screen points, top-left origin, the
 *  ScreenRegion space; displayId absent = the primary display. label <= 4 words. via: how the engine found it, on this Mac:
 *  ax = the app's accessibility tree (exact), ocr = on-device text recognition. Ambient help never sends a screenshot or a crop. */
export interface AmbientTarget { x: number; y: number; w: number; h: number; displayId?: number; label?: string; app?: string; via?: "ax" | "ocr" }
/** error.seen. id: stable for the same app + kind + title + file:line ("err-" + a short hash), so the same error again keeps its
 *  id. title: <= 80 characters, usually the error's own last line ("ModuleNotFoundError: No module named 'pandas'").
 *  lines: up to AMBIENT_ERROR_LINES_MAX, as read, with the home folder shortened to ~ and secret-looking values masked (••••).
 *  file / line / col: where it points, when the error says (file as shown, home shortened). exitCode: shell_exit only.
 *  rect: where the error text is on screen (the peek sits by it, bon points at it). at: ISO time first seen; again: times
 *  seen again since. */
export interface SeenError { id: string; app: string; kind: AmbientErrorKind; title: string; lines: string[]; file?: string; line?: number; col?: number;
                             exitCode?: number; lang?: string; rect?: AmbientTarget; at: string; again?: number }
/** error.explanation. title <= 8 words; why: what went wrong in plain words (<= 40); fix: the likely fix (<= 25 words).
 *  diff: an optional unified diff for file (shown, never applied by itself). command: an optional terminal fix to copy
 *  ("pip install pandas"). install: when the fix is installing a tool, its row (Install -> setup.fix {tool}). target: where
 *  to look (the line in the editor, a dialog's button) for bon to point at. error + retryInS: no explanation (AmbientFail). */
export interface ErrorExplanation { id: string; reqId?: string; pending?: boolean; title?: string; why?: string; fix?: string; diff?: string; file?: string; line?: number;
                                    command?: string; install?: SetupItem; target?: AmbientTarget; error?: AmbientFail; retryInS?: number }
/** One help step: text = one action, <= 12 words ("Click File, then Save As"); detail: optional, <= 25 words. advance: what
 *  moves on from it: click = the target is clicked, screen = the screen changes as the step says (a menu / sheet / window
 *  opens), next = only the learner's Next (help.nav). target absent: nothing to point at (or not found yet). */
export interface HelpStep { id: string; text: string; detail?: string; target?: AmbientTarget; advance?: "click" | "screen" | "next" }
/** help.steps. app: the app the steps are for ("Blender"); goal: the question as a title (<= 8 words, "Export as STL").
 *  current: 0-based index of the step to do now. */
export interface HelpSteps { reqId?: string; app: string; goal: string; steps: HelpStep[]; current: number; done?: boolean; pending?: boolean;
                             error?: AmbientFail; retryInS?: number }
export type SetupScanError = "no_project" | "unreadable" | "too_big"   // no_project: no folder given and none open in the frontmost editor; too_big: over the scan's file limit
/** setup.report. root: the project folder (home shortened); name: its folder name. files: the project files read ("requirements.txt",
 *  ".nvmrc"). items: one SetupItem per thing they ask for (from: the file and line), missing ones first; more: rows left out
 *  (a long requirements file). env: the interpreters the checks used ("~/code/app/.venv (Python 3.12.4)", "node 20.11.1").
 *  ready / total: items ok / items. scanning: a first quick answer, the full one follows. */
export interface SetupReport { reqId?: string; root?: string; name?: string; files: string[]; items: SetupItem[]; ready: number; total: number; more?: number;
                               env?: { python?: string; node?: string }; scanning?: boolean; error?: SetupScanError }

// ---------- App -> Engine commands ----------
export interface AppCommands {
  "learn": { query: string; mode?: "video" | "lesson" | "demo"; plan?: PlanLessonRef };   // plan (ui-v4): this lesson is lesson `index` of plan `id` (start it with query = that lesson's goal, mode "lesson"); the engine marks the plan lesson in_progress, then done when its last step passes   // launcher text; mode "lesson" = "Just teach me": no video search, a text lesson built for the goal (default "video"); mode "demo": the launcher's Demo option, the staged neural-net lesson for any goal (server/orchestrator/stage.py: typing steps pass on a save or Check my work, runs are recorded, one planned off-track on Train it)
  "learn_url": { url: string; transcriptOnly?: boolean; plan?: PlanLessonRef };   // pasted YouTube link; with "link.any" in engine.hello.capabilities, any http(s) link: an article / docs page (BuildSource kind "web") or a github.com repo ("github"), built into a text lesson (mode "lesson", no video; ANY-LINK.md); transcriptOnly is ignored for those   // transcriptOnly (v2, Err-LessonBuildFailed "Try transcript only"): skip the video model, build from the transcript + title/chapters (offered by lesson.building.alternatives kind "transcript"; optional, older engines ignore it)   // plan (ui-v4): this video is lesson `index` of plan `id` (a playlist plan): the engine marks that plan lesson when it starts and passes
  "build_lesson": { resultIds: string[] };
  /** explain: no text = explain the current step (Explain button / shortcut, unchanged). text = the learner's selection (the drawer's "Explain more" pop-up on selected lesson text):
   *  the engine answers with a card {kind: "explain", title: "About `<start of the selection>`", body}: the selection explained, the current step as context. VS Code's "Miyagi: Explain this" gives the same card (it reaches the engine over POST /vscode/event, not this socket).
   *  ask + region (Circle to ask, Nov 22): the learner held Fn+Control and circled part of the screen. text = the spoken words, or
   *  "What is this?" when nothing was said (the engine uses that too when text is empty). source "circle". askId: the app's id for
   *  this ask; the answer card echoes it. Works with or without a lesson. The engine crops region, reads the text boxes inside it,
   *  and answers with a card {kind: "answer", askId, region}, then maybe annotate {marks: [{why: "answer", askId, ...}]}. The crop is
   *  used for this one ask only, never stored or logged. Timing: the engine answers each circle ask within about 25 s: one deadline,
   *  22 s after the action arrives, covers the streamed answer, its one retry and the one-shot fallback (each starts only when
   *  enough of it is left, else the failed card goes), so the app's pending-circle timeout (ASK_MAX_MS 30 s) stays above that. The overlay's
   *  click-through hard timeout covers only the drawing: it goes back to click-through on release, without waiting for the answer. */
  "action": { kind: "back" | "explain" | "diagram" | "show_me" | "hint" | "voice_toggle" | "ask" | "apply_fix" | "confirm" | "undo" | "open_editor" | "resume" | "end_lesson" | "install" | "install_all" | "skip_setup" | "open_in_browser" | "build" | "pick_another" | "download" | "skip_step" | "check_step" | "use_this_folder" | "run_command" | "retry" | "start" | "have_it" | "get_it" | "alternative" | "open_in_app" | "setup_retry" | "setup_continue" | "setup_skip"; text?: string;
              region?: ScreenRegion; source?: AskSource; askId?: string; capture?: AskCapture };  // open_in_app (Nov 24): an app lesson's setup card: open the lesson's scene in its desktop app (Blender: <lesson folder>/<stem>.blend, made from Blender's factory scene when missing, opened with the miyagi bridge so no add-on install is needed); label in setup.actionLabels.open_in_app ("Open in Blender"); action open_in_app {text?: the app's tool id, absent = the lesson's app}; the card sends setup.holdVideo false  // region / source / askId / capture: Circle to ask (kind "ask", see above)   // have_it / get_it / alternative: a setup row of a licensed app (text = its tool id; none: the first app row waiting)  // install_all (t9 V12): the setup card's "Install all": every missing row, one after another (each row gets its own setup.progress)  // start: "Start the lesson" on the "Before you start" sheet: a "Just teach me" lesson with build / flow / prerequisites / learnFirst holds step 1 (VS Code opens under the sheet; no checks, boxes, idle timers, stuck cards or off-tracks) from a lesson.ready whose first step.started is step 1 until this, a key / click with the lesson's editor in front (the sheet's own Start / Esc land there, the overlay can't take focus), the first edit of the step file, or a step control (show_me, hint, check_step, skip_step, run_command, open_editor ...); optional for the app  // retry: the "Couldn't reach Claude" card's Try again: the engine re-sends the learner's last ask / explain / hint (no text needed)  // run_command: "Run it for me" on a run step (the engine runs the step's command in the lesson folder, max 10 s, and shows the output)  // use_this_folder: the learner is editing the lesson file in another folder; adopt that folder as the lesson folder (copies only missing files, never overwrites)  // check_step: "Can I move on?" -> the engine re-runs the checks now and Claude judges the screen; replies with check.updated + step.passed, or a card saying what is missing  // skip_step: leave the current step unfinished and start the next one  // download: the video's linked files -> <lesson folder>/tutorial/  // build / pick_another: the preflight card  // install / open_in_browser: text = setup item tool id  // resume / end_lesson: the "Continue where you left off?" card  // open_editor: the learner accepted "Open VS Code?"  // confirm: "Looks done?" card; undo: revert the last "Do it for me"
  "video.state": { t: number; playing: boolean };   // player reports its position
  "end_lesson": {};                                  // stop everything; the engine answers lesson.ended + status idle
  "overlay.bounds": { rects: Array<{ x: number; y: number; w: number; h: number }> };
  /** Bring-your-own-key (like cue): sent on every connect from the app's Settings. Engine uses these over its .env, keeps them in memory only, never logs them. */
  "config.keys": { anthropic?: string; gemini?: string; elevenlabs?: string; tigerUrl?: string;
                   miyagiToken?: string; miyagiCloud?: string };   // v2 (DISTRIBUTION-PLAN): the anonymous install token ("mi_...") and the proxy's https base URL; memory only, never logged, never on a command line
  /** What the learner really has on screen (E14: the engine assumed every card it sent was visible). Optional: an app that never sends these keeps today's behaviour.
   *  card.shown: a `card` or the `offtrack` card became visible in the card slot (not while the sheet / launcher covers the slot or the window is hidden; send it when it shows).
   *  card.closed: it left the slot. by: "user" (✕ / Esc / a video jump), "replaced" (another card / diagram / off-track took the slot), "timeout" (it closed itself, e.g. a pressed button gave up), "hidden" (the sheet / launcher covered the slot, the window hid).
   *  title / kind / stepId: copied from the card's payload; kind "offtrack" for the off-track card. On by "user" / "timeout" the engine lifts the off-track hold that this card (matched by title) caused; "replaced" / "hidden" lift nothing (the engine knows what it sent; a covered card shows again). */
  "card.shown": { stepId?: string; title: string; kind?: string };
  "card.closed": { stepId?: string; title: string; kind?: string; by: "user" | "replaced" | "timeout" | "hidden" };

  // ---------- v2 commands: send one only when engine.hello.capabilities lists its type ----------
  "health.get": {};                                  // -> health
  "permission.open": { kind: PermissionKind };       // the engine reports the grant it needs; the APP opens System Settings (main/permissions.ts), never a URL from here
  "library.list": {};                                // -> library
  "library.get": { id: string };                     // -> library.item
  "library.start": { id: string; plan?: PlanLessonRef };   // start a cached lesson: zero model calls; -> lesson.ready (or error)   // plan (ui-v4): as learn.plan
  "progress.get": {};                                // -> progress
  /** The lesson panel docked beside the editor (screen points): the engine keeps boxes and VS Code clear of it. rect absent = closed. */
  "panel.state": { open: boolean; rect?: { x: number; y: number; w: number; h: number } };
  /** Nov 22 (Skills page). set_goal: the learner picked a capstone (the engine answers a fresh `progress`). skills.ack: the unlock events up to `until` (an event's `at`) have played. */
  "set_goal": { capstoneId: string };
  "skills.ack": { until: string | number };
  /** Nov 22 (push to talk speed): the learner is holding the push-to-talk keys (Fn+Control) past the minimum hold and
   *  the mic is open, so an ask (spoken, or a circle) is likely within a few seconds. The engine gets ready for it: open
   *  or reuse its keep-alive links (app to engine to cloud to Anthropic) and warm the prompt cache for the fixed ask
   *  system prompt. No reply event, no card, never a learner-visible effect; safe to ignore or repeat. pttId: the hold's
   *  id (the helper's ptt.id), for logs only. The app sends it on every hold that passes the minimum (never for a tap
   *  or an aborted chord), and only when engine.hello lists "ask.warm". The engine always opens or reuses the links
   *  (free; keep-alive links close seconds after their last use) and throttles only the paid prompt-cache write (at
   *  most once per few minutes, under the 5-minute cache lifetime). */
  "ask.warm": { pttId?: string; source?: string };   // source: optional tag ("keydown"), for logs only

  // ---------- engine commands the contract did not list yet (Nov 24 sync with server/orchestrator/main.py V2_COMMANDS) ----------
  /** Start review (sessions/review.py): replay the steps behind one mastered skill from its lesson's cached graph, no build and
   *  no model call. skillId / label both optional (none: the first review due). -> lesson.ready, or error when nothing is due. */
  "review.start": { skillId?: string; label?: string };
  /** Delete my data, engine part. Today it removes the lesson notes (server/context) whatever `what` says. what (ui-v4,
   *  optional): which local data to remove (DataDeleteKind); an engine that cannot delete a kind yet skips it and leaves it out
   *  of the `data` answer's `deleted`. Older engines send no reply; ui-v4 engines answer `data`. */
  "data.delete": { what?: DataDeleteKind[] };

  // ---------- ui-v4 commands (Nov 24): send one only when engine.hello.capabilities lists its type ----------
  "activity.get": {};                                // -> activity (then pushes while it changes)
  "bon.get": {};                                     // -> bon
  /** Once per Mac, the first time the engine lists bon.import: the count growth.ts kept in localStorage before the engine kept it.
   *  The engine keeps max(its count, steps), adds seen (the app's "<lessonId>:<stepId>" keys, <= 400) to the keys it has counted,
   *  and answers bon. After that the app reads bon only. */
  "bon.import": { steps: number; seen?: string[] };
  "plans.list": {};                                  // -> plans
  /** Add a plan: a catalog preset (catalogId), a playlist (playlistId, with the proposal the learner accepted, skips included) or
   *  a goal (proposal from plan.proposal). Starting its first lesson is a separate learn / learn_url / library.start with plan.
   *  -> plans (the new plan first). The same catalogId twice answers the plan already there. */
  "plan.start": { catalogId?: string; playlistId?: string; url?: string; goal?: string; proposal?: PlanProposal; reqId?: string };
  "plan.remove": { id: string };                     // -> plans. The lessons it started stay in the library
  "playlist.get": { url: string; reqId?: string };   // a youtube.com playlist link (or a watch link with list=) -> playlist (twice)
  "plan.propose": { goal: string; tool?: string; reqId?: string };   // goal text; tool: a PlanTool id the learner picked ("freecad") -> plan.proposal
  "link.get": { url: string; reqId?: string };       // a link pasted in the ask field -> link.preview (with "link.any": any http(s) link, kinds "web" / "github" too; ANY-LINK.md)
  "proof.get": { id?: string; skillId?: string; reqId?: string };   // one Proof by id, or a skill's (newest first, <= 5) -> proof
  "data.get": {};                                    // -> data

  // ---------- ambient help commands (Nov 24, AMBIENT-HELP.md): send one only when engine.hello.capabilities lists its type ----------
  /** Turn spotting errors on or off (Settings; the app sends it on every connect). errors: watch for errors outside a lesson
   *  (absent: unchanged; the engine starts with it off). mutedApps: app names never watched ("1Password"), <= 50. Local only. */
  "ambient.set": { errors?: boolean; mutedApps?: string[] };
  /** The learner pressed Explain on an error.seen peek. -> error.explanation. The one moment the error leaves the Mac: its
   *  title, lines and up to AMBIENT_CONTEXT_LINES_MAX lines of context, redacted (paths cut to the file name, secrets masked),
   *  plus the app name and kind; never a screenshot. One Haiku call, counted against AMBIENT_CALLS_PER_HOUR; the same id
   *  again answers from the engine's memory. */
  "error.explain": { id: string; reqId?: string };
  /** The learner closed the peek: the engine forgets what it held for this id and does not send it again this session. */
  "error.dismiss": { id: string };
  /** Check a project for missing tools, runtimes and packages. path: the folder (absent: the folder open in the frontmost editor).
   *  -> setup.report. */
  "setup.scan": { path?: string; reqId?: string };
  /** Install one setup.report row through the existing install path (action install's: brew, allowlisted casks, pip into the
   *  project's own .venv when it has one, npm install in root; a licensed app is never installed). The row's button is the
   *  learner's yes. -> setup.progress {tool} lines, then {done, ok}, then a fresh setup.report. */
  "setup.fix": { tool: string; root?: string; reqId?: string };
  /** "How do I X" about the app the learner is in, outside a lesson. text <= 300 characters. app: the app that was frontmost
   *  before the ask field took focus (absent: the engine reads the frontmost app). -> help.steps. A new help.ask replaces the
   *  one before. Sends the question, the app's name and the labels of its window's controls (accessibility tree, redacted),
   *  never a screenshot; one Haiku call, counted against AMBIENT_CALLS_PER_HOUR. */
  "help.ask": { text: string; reqId?: string; app?: string; source?: AskSource };
  /** The help card's Next / Back / close. next / back -> help.steps with current moved; close: the engine stops watching, no reply. */
  "help.nav": { reqId?: string; to: "next" | "back" | "close" };
}
// Engine -> app answer to config.keys: which keys are present and valid (never echo the keys themselves)
export interface KeyStatusEvent { "config.status": { anthropic: KeyState; gemini: KeyState; elevenlabs: KeyState; tigerUrl: KeyState;
                                                     miyagiToken?: KeyState; cloud?: CloudState } } // same key names as config.keys   // v2: cloud = what the proxy said about this install's token
export type CloudState = "ok" | "missing" | "paused" | "quota" | "unauthorized" | "offline" | "off";   // missing = a proxy but no token yet; off = no token / no proxy configured (BYOK or the engine's .env)
export type KeyState = "ok" | "missing" | "invalid" | "env";   // "env" = falling back to the engine's .env

export type EngineMessage = { [K in keyof EngineEvents]: { type: K; payload: EngineEvents[K] } }[keyof EngineEvents];
export type AppMessage = { [K in keyof AppCommands]: { type: K; payload: AppCommands[K] } }[keyof AppCommands];

// ---------- App -> Engine: overlay bounds (so the screen reader ignores our own UI) ----------
export interface AppOverlayReport {
  "overlay.bounds": { rects: Array<{ x: number; y: number; w: number; h: number }> }; // send whenever pill/cards/bar move or resize
}
// NOTE: the VS Code extension is dropped. The engine watches the whole screen (any app) and sends spotlight rects.

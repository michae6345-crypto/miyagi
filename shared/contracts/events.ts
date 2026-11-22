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
export interface StepSummary { id: string; index: number; title: string; video?: VideoSegment | null; kind?: StepKind; what?: string; estMinutes?: number }   // what: what this step builds (<= 12 words), the plan line in the step list   // estMinutes: about how long this step takes (whole minutes); "about 35 min left" = the sum over the steps not passed yet
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
export interface OutlineStep { index: number; title: string; kind?: StepKind; what?: string; estMinutes?: number }
export interface LessonOutline { count: number; steps: OutlineStep[]; estMinutes?: number }   // estMinutes: the whole lesson (the sum of the rows'), when every row has one
export interface LearnFirstItem { title: string; minutes: number; kind: "notebook" | "interactive" | "video" | "read"; covers: string }   // a short mini-lesson for a prerequisite not passed yet; covers: Prerequisite.id; the app starts one with learn {query: title, mode: "lesson"} ("video" kind: mode "video")

// ---------- Engine -> App events ----------
export interface EngineEvents {
  "search.result": { id: string; kind: SourceKind; title: string; meta: string; score: number; reason: string; thumbnail?: string;
                     style?: "coding" | "no-code" | "conceptual"; durationLabel?: string; long?: boolean;   // finder (E7): what kind of tutorial, "1 h 56 min · 30 chapters", > 45 min
                     chapters?: number; captions?: boolean;                                                // chapter count; YouTube captions available
                     url?: string; source?: string; videoId?: string; durationS?: number; channel?: string;   // finder extras (all optional)
                     verified?: boolean; warnings?: string[]; scoredBy?: string; watched?: string;
                     prerequisites?: string[]; codeNotes?: string; comments?: string };
  "search.done": { total: number };
  "lesson.building": { message: string; progress: number; failed?: boolean; elapsedS?: number };   // message = the stage (changes only with the stage); elapsedS = seconds since the build started (the 1 s heartbeat)   // progress 0..1 for the launcher; ~1/s while building; failed: true = the build ended in error (an `error` + status idle follow): drop the building UI
  "lesson.ready": { lesson: { id: string; title: string; sources: Source[]; complete?: boolean; builtBy?: "gemini" | "claude" | "mixed" | "chapters" | "unknown" | "curated"; provisional?: boolean;
                              goalMatch?: { score: number | null; note: string };
                              mode?: "video" | "lesson"; primer?: PrimerItem[]; overview?: string;
                              build?: LessonBuild; flow?: FlowBox[]; prerequisites?: Prerequisite[]; learnFirst?: LearnFirstItem[];
                              outline?: LessonOutline }; steps: StepSummary[]; replay?: boolean; buildS?: number };   // buildS: seconds from the learner's command (learn / learn_url / build_lesson) to this lesson.ready, only on a build's first lesson.ready (engine build metrics; optional, the app may ignore it)   // builtBy "curated": written by hand (the curated "Just teach me" / Demo lessons, server/orchestrator/curated.py), no model wrote it: no "Claude wrote this lesson" line   // replay: the SAME lesson again (an app reconnect / engine restore): keep its progress, never a new start or "Before you start"   // outline: every step from the start (absent: a build whose step count isn't known yet)   // build / flow / prerequisites / learnFirst: the learn-anything screens (see LessonBuild above)   // overview: "What we're building" (<= 60 words)   // primer: "Before you start" concepts (lesson mode)   // mode "lesson" ("Just teach me"): no video, no player events; the editor is full screen and each step spotlights where to type   // complete false = a long video is still building (see lesson.updated)
  /** a long video's next part was built: new steps APPENDED (ids never change, earlier steps never edited) */
  "lesson.updated": { steps: StepSummary[]; complete: boolean; parts?: { done: number; failed: number; total: number } };
  "step.started": { stepId: string; index: number; title: string; instructions: string; video?: VideoSegment | null; details?: string; kind?: StepKind; what?: string; why?: string; concepts?: string[]; code?: string; estMinutes?: number; replay?: boolean };   // replay: a reconnect's / restore's replay of the step already running (not a new step)   // estMinutes: about how long this step takes ("about 4 min")   // code: the exact code to type / command to run, in full (never truncated)   // what: what you build in this step (<= 12 words); why: what it means (<= 25 words); concepts: primer ids   // instructions: ONE concrete action ("Create calculator.py and type print(…)"); details: the full explanation; video null/absent: no player for this step
  "check.updated": { stepId: string; checkId: string; label: string; status: CheckStatus; detail?: string; epoch?: number; gen?: number };
  "step.passed": { stepId: string; nextStepId?: string; pending?: boolean; skipped?: boolean; already?: boolean };   // already: its code was already in the file (pasted ahead / Do it for me): passed without starting; ONE card "You already did steps 2–3" follows   // skipped: the learner pressed Skip (action skip_step): not a pass, never green  // pending: no next step YET (the next part is still building); the engine continues on lesson.updated
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
  "video.seek": { t: number; play: boolean };
  "video.pause": {};
  "video.play": {};
  /** card.kind (tile per kind, A15): explain / hint / answer = what the learner pressed or asked (Explain, Hint, a typed question); resume / setup / preflight: see their fields.
   *  "step": a step-control / step-status card the engine raises itself, never an answer: "Run it" (run_command), "Save calc.py", "calc.py is still empty", "Wrong folder?",
   *          "Looks done?" and every judge card (source "judge": "Not yet", "Already ahead?", "Save so I can check"). A neutral step tile, not the pink Hint one.
   *  "where": where to work when there is no box to draw ("Open calc.py", "Where to work", "Save it as calc.py"), usually with open_editor: Show me's answer, and Hint's
   *          when the step's code isn't on screen yet. The lilac Show me tile. */
  "card": { epoch?: number; gen?: number; stepId?: string; kind: "explain" | "hint" | "answer" | "resume" | "setup" | "preflight" | "step" | "where"; title: string; body: string; videoJump?: { t: number; label: string };
            output?: string;              // monospace output block (e.g. the last lines of "Run it for me")
            dismissAfterMs?: number;      // the app closes the card on its own after this long (a one-line success: "requests installed ✓", no buttons)
            actions?: Array<"confirm" | "undo" | "apply_fix" | "open_editor" | "resume" | "end_lesson" | "install" | "install_all" | "skip_setup" | "open_in_browser" | "build" | "pick_another" | "download" | "skip_step" | "check_step" | "use_this_folder" | "run_command" | "retry" | "hint" | "show_me">;    // buttons on the card -> send `action {kind}`; retry ("Try again"): on the "Couldn't reach Claude" answer card; hint / show_me: the same actions as on the off-track card (judge "Not yet" card)
            items?: SetupItem[];          // kind "preflight": early tool check (a second card of the same kind replaces the first)
            warning?: string;             // kind "preflight": shown in amber when the video doesn't fit the goal (goalMatch.score < 0.5)
            recommended?: "build" | "pick_another";   // which button to make primary
            preflight?: PreflightInfo;    // kind "preflight": what the picked video is, before anything is built
            where?: string;               // coach (E5): where to go when the place isn't on screen ("Open app.py in VS Code"); shown without a dim
            setup?: { editorNeeded: boolean; items: SetupItem[];
                      editorLabel?: string | null;                       // "Visual Studio Code": the open_editor button reads "Open Visual Studio Code"
                      resources?: Array<{ name: string; url: string; kind: "repo" | "notebook" | "gist" | "file" }>;   // files the video links (action download)
                      actionLabels?: { [action: string]: string } };     // button labels, e.g. download: "Download tutorial files"   // kind "setup": what the lesson needs on this Mac (one Install button per missing item -> action install {text: tool})
            diff?: string;               // unified diff to preview ("Apply this fix?" -> confirm)
            targets?: Array<{ boxId: number; label: string; text: string; rect: { x: number; y: number; w: number; h: number } }>;
            guidingQuestion?: string;
            source?: "judge";              // E5's step judge made it ("Looks done?" / "Not yet" / "Already ahead?" / "Save so I can check"): a step-status card, never an answer to the learner (sent as kind "step"); don't let it replace an answer card
            verdict?: "done" | "not_done"; // source "judge": Claude's verdict on the WHOLE step. done -> "Looks done?" (confirm = Yes); not_done -> "Not yet" (hint / show_me)
            checkIds?: string[];           // source "judge": the checks it is about (done: what Yes vouches for; not_done: what is still missing)
            skillMap?: SkillMap };         // the lesson-complete card (last step passed): the skill map to draw under "Congratulations" (mockup 10)
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
  "status": { state: "idle" | "watching" | "offtrack" | "passed" | "thinking"; detail?: string; epoch?: number; gen?: number };   // epoch / gen: the lesson and step generation the engine sent it under (optional, additive)
  /** install progress for one setup item (action install): lines while it runs, then {done, ok, error|version|url} */
  "setup.progress": { tool: string; line?: string; done?: boolean; ok?: boolean; error?: string; url?: string; version?: string };
  /** Install token self-heal: the miyagi cloud does not know this install's token (the proxy answered 401, e.g. its database was
   *  reset). Sent once per token, and again when config.keys repeats that token. Never carries the token or its hash. The app drops
   *  the token, mints a new one (POST <host>/v1/install) and sends config.keys again, at most once per 5 minutes; a config.status
   *  with cloud "ok" (the new token's answer) cancels a heal still waiting. Not sent for an install an operator disabled (403):
   *  config.status.cloud says "unauthorized" instead. */
  "cloud.token_invalid": { reason?: "unknown_token" };
  /** the lesson was ended (end_lesson, a new learn, or POST /end): clear the pill, video, spotlight and cards */
  "lesson.ended": { lessonId?: string; reason: string };
  "error": { message: string; epoch?: number; gen?: number };
}

/** one tool a lesson needs (server/workspace setup check). For install.method "download" the app opens install.url instead of sending `install`. */
export interface SetupItem {
  tool: string; label: string; kind: "editor" | "app" | "runtime" | "cli" | "python_package" | "web_app"; why: string;
  needed: boolean; installed: boolean; ok: boolean; version?: string; minVersion?: string;
  install: { method: "brew" | "brew_cask" | "pip" | "download" | "open" | "none"; command?: string; url?: string };  // web_app: method "open" + https url (nothing to install)
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

// ---------- App -> Engine commands ----------
export interface AppCommands {
  "learn": { query: string; mode?: "video" | "lesson" | "demo" };   // launcher text; mode "lesson" = "Just teach me": no video search, a text lesson built for the goal (default "video"); mode "demo": the launcher's Demo option, the staged neural-net lesson for any goal (server/orchestrator/stage.py: typing steps pass on a save or Check my work, runs are recorded, one planned off-track on Train it)
  "learn_url": { url: string; transcriptOnly?: boolean };   // pasted YouTube link; transcriptOnly: the Build failed card's "Try transcript only": skip the video model, build from the transcript + title/chapters (offered by lesson.building.alternatives kind "transcript"; optional, older engines ignore it)
  "build_lesson": { resultIds: string[] };
  /** explain: no text = explain the current step (Explain button / shortcut, unchanged). text = the learner's selection (the drawer's "Explain more" pop-up on selected lesson text):
   *  the engine answers with a card {kind: "explain", title: "About `<start of the selection>`", body}: the selection explained, the current step as context. VS Code's "Miyagi: Explain this" gives the same card (it reaches the engine over POST /vscode/event, not this socket). */
  "action": { kind: "back" | "explain" | "diagram" | "show_me" | "hint" | "voice_toggle" | "ask" | "apply_fix" | "confirm" | "undo" | "open_editor" | "resume" | "end_lesson" | "install" | "install_all" | "skip_setup" | "open_in_browser" | "build" | "pick_another" | "download" | "skip_step" | "check_step" | "use_this_folder" | "run_command" | "retry" | "start"; text?: string };  // install_all (t9 V12): the setup card's "Install all": every missing row, one after another (each row gets its own setup.progress)  // start: "Start the lesson" on the "Before you start" sheet: a "Just teach me" lesson with build / flow / prerequisites / learnFirst holds step 1 (VS Code opens under the sheet; no checks, boxes, idle timers, stuck cards or off-tracks) from a lesson.ready whose first step.started is step 1 until this, a key / click with the lesson's editor in front (the sheet's own Start / Esc land there, the overlay can't take focus), the first edit of the step file, or a step control (show_me, hint, check_step, skip_step, run_command, open_editor ...); optional for the app  // retry: the "Couldn't reach Claude" card's Try again: the engine re-sends the learner's last ask / explain / hint (no text needed)  // run_command: "Run it for me" on a run step (the engine runs the step's command in the lesson folder, max 10 s, and shows the output)  // use_this_folder: the learner is editing the lesson file in another folder; adopt that folder as the lesson folder (copies only missing files, never overwrites)  // check_step: "Can I move on?" -> the engine re-runs the checks now and Claude judges the screen; replies with check.updated + step.passed, or a card saying what is missing  // skip_step: leave the current step unfinished and start the next one  // download: the video's linked files -> <lesson folder>/tutorial/  // build / pick_another: the preflight card  // install / open_in_browser: text = setup item tool id  // resume / end_lesson: the "Continue where you left off?" card  // open_editor: the learner accepted "Open VS Code?"  // confirm: "Looks done?" card; undo: revert the last "Do it for me"
  "video.state": { t: number; playing: boolean };   // player reports its position
  "end_lesson": {};                                  // stop everything; the engine answers lesson.ended + status idle
  "overlay.bounds": { rects: Array<{ x: number; y: number; w: number; h: number }> };
  /** Bring-your-own-key (like cue): sent on every connect from the app's Settings. Engine uses these over its .env, keeps them in memory only, never logs them. */
  "config.keys": { anthropic?: string; gemini?: string; elevenlabs?: string; tigerUrl?: string; miyagiToken?: string; miyagiCloud?: string };
  /** What the learner really has on screen (E14: the engine assumed every card it sent was visible). Optional: an app that never sends these keeps today's behaviour.
   *  card.shown: a `card` or the `offtrack` card became visible in the card slot (not while the sheet / launcher covers the slot or the window is hidden; send it when it shows).
   *  card.closed: it left the slot. by: "user" (✕ / Esc / a video jump), "replaced" (another card / diagram / off-track took the slot), "timeout" (it closed itself, e.g. a pressed button gave up), "hidden" (the sheet / launcher covered the slot, the window hid).
   *  title / kind / stepId: copied from the card's payload; kind "offtrack" for the off-track card. On by "user" / "timeout" the engine lifts the off-track hold that this card (matched by title) caused; "replaced" / "hidden" lift nothing (the engine knows what it sent; a covered card shows again). */
  "card.shown": { stepId?: string; title: string; kind?: string };
  "card.closed": { stepId?: string; title: string; kind?: string; by: "user" | "replaced" | "timeout" | "hidden" };
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

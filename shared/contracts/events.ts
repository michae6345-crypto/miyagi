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
export interface Source { id: string; kind: SourceKind; title: string; url: string; meta?: string }
export interface StepSummary { id: string; index: number; title: string; video?: VideoSegment }

// ---------- Engine -> App events ----------
export interface EngineEvents {
  "search.result": { id: string; kind: SourceKind; title: string; meta: string; score: number; reason: string; thumbnail?: string };
  "search.done": { total: number };
  "lesson.building": { message: string; progress: number; failed?: boolean };   // progress 0..1 for the launcher; ~1/s while building; failed: true = the build ended in error (an `error` + status idle follow): drop the building UI
  "lesson.ready": { lesson: { id: string; title: string; sources: Source[] }; steps: StepSummary[] };
  "step.started": { stepId: string; index: number; title: string; instructions: string; video?: VideoSegment };
  "check.updated": { stepId: string; checkId: string; label: string; status: CheckStatus; detail?: string };
  "step.passed": { stepId: string; nextStepId?: string };
  "offtrack": {
    stepId: string;
    severity: "warn" | "fail";
    title: string;             // <= 8 words
    body: string;              // <= ~30 words
    diff?: { expected: string; yours: string; file?: string; line?: number };
    citation?: { label: string; url: string };
    actions: Array<"explain" | "show_me" | "apply_fix" | "hint">;   // apply_fix = "Do it for me" (only at level 3)
    level?: 2 | 3;             // hint ladder: 2 = concept (no fix yet), 3 = exact fix + diff + apply_fix
    targets?: Array<{ boxId: number; label: string; text: string; rect: { x: number; y: number; w: number; h: number } }>;  // what the coach points at (screen points)
    guidingQuestion?: string;  // a Socratic nudge to show under the body
  };
  /** Screen-first: rect is in screen POINTS, TOP-LEFT origin (Electron convention), relative to the PRIMARY display's FULL frame (y=0 is the very top, menu bar included). v1 watches the primary display only. Same convention for overlay.bounds. */
  "spotlight": { rect: { x: number; y: number; w: number; h: number }; caption: string; app?: string; matched?: string } | { clear: true };
  /** What the engine currently sees (debug HUD / optional). */
  "screen.seen": { app: string; summary: string; t: number };
  "video.seek": { t: number; play: boolean };
  "video.pause": {};
  "video.play": {};
  "card": { stepId?: string; kind: "explain" | "hint" | "answer" | "resume"; title: string; body: string; videoJump?: { t: number; label: string };
            actions?: Array<"confirm" | "undo" | "apply_fix" | "open_editor" | "resume" | "end_lesson">;    // buttons on the card -> send `action {kind}`
            diff?: string;               // unified diff to preview ("Apply this fix?" -> confirm)
            targets?: Array<{ boxId: number; label: string; text: string; rect: { x: number; y: number; w: number; h: number } }>;
            guidingQuestion?: string };
  "diagram": {
    kind: "network" | "gradients" | "heatmap" | "graph";
    caption: string;
    stepId?: string;
    data:
      | { layers: number[]; activation: string; derivatives: string[]; residual: string }            // network
      | { layers: string[]; epochs: number[]; norms: number[][] }                                     // gradients: norms[layer][epochIdx]
      | { x: number[]; t: number[]; predicted: number[][]; exact?: number[][] }                      // heatmap
      | GraphDiagramData;                                                                             // graph (any topic; server/diagrams)
  };
  "speak": { audioUrl: string; text: string };
  "metric": { runId: string; step: number; name: string; value: number };   // live curve feed
  "status": { state: "idle" | "watching" | "offtrack" | "passed" | "thinking" };
  /** the lesson was ended (end_lesson, a new learn, or POST /end): clear the pill, video, spotlight and cards */
  "lesson.ended": { lessonId?: string; reason: string };
  "error": { message: string };
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

// ---------- App -> Engine commands ----------
export interface AppCommands {
  "learn": { query: string };                       // launcher text
  "learn_url": { url: string };                     // pasted YouTube link
  "build_lesson": { resultIds: string[] };
  "action": { kind: "back" | "explain" | "diagram" | "show_me" | "hint" | "voice_toggle" | "ask" | "apply_fix" | "confirm" | "undo" | "open_editor" | "resume" | "end_lesson"; text?: string };  // resume / end_lesson: the "Continue where you left off?" card  // open_editor: the learner accepted "Open VS Code?"  // confirm: "Looks done?" card; undo: revert the last "Do it for me"
  "video.state": { t: number; playing: boolean };   // player reports its position
  "end_lesson": {};                                  // stop everything; the engine answers lesson.ended + status idle
  "overlay.bounds": { rects: Array<{ x: number; y: number; w: number; h: number }> };
  /** Bring-your-own-key (like cue): sent on every connect from the app's Settings. Engine uses these over its .env, keeps them in memory only, never logs them. */
  "config.keys": { anthropic?: string; gemini?: string; brightdata?: string; elevenlabs?: string; tigerUrl?: string };
}
// Engine -> app answer to config.keys: which keys are present and valid (never echo the keys themselves)
export interface KeyStatusEvent { "config.status": { anthropic: KeyState; gemini: KeyState; brightdata: KeyState; elevenlabs: KeyState; tigerUrl: KeyState } } // same key names as config.keys
export type KeyState = "ok" | "missing" | "invalid" | "env";   // "env" = falling back to the engine's .env

export type EngineMessage = { [K in keyof EngineEvents]: { type: K; payload: EngineEvents[K] } }[keyof EngineEvents];
export type AppMessage = { [K in keyof AppCommands]: { type: K; payload: AppCommands[K] } }[keyof AppCommands];

// ---------- App -> Engine: overlay bounds (so the screen reader ignores our own UI) ----------
export interface AppOverlayReport {
  "overlay.bounds": { rects: Array<{ x: number; y: number; w: number; h: number }> }; // send whenever pill/cards/bar move or resize
}
// NOTE: the VS Code extension is dropped. The engine watches the whole screen (any app) and sends spotlight rects.

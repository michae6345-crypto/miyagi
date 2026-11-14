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
  "lesson.building": { message: string; progress: number };   // 0..1, for the launcher spinner
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
    actions: Array<"explain" | "show_me" | "apply_fix" | "hint">;
  };
  /** Screen-first: rect is in macOS screen POINTS (top-left origin of the primary display), from the engine's screen reader. */
  "spotlight": { rect: { x: number; y: number; w: number; h: number }; caption: string; app?: string; matched?: string } | { clear: true };
  /** What the engine currently sees (debug HUD / optional). */
  "screen.seen": { app: string; summary: string; t: number };
  "video.seek": { t: number; play: boolean };
  "video.pause": {};
  "video.play": {};
  "card": { stepId?: string; kind: "explain" | "hint" | "answer"; title: string; body: string; videoJump?: { t: number; label: string } };
  "diagram": {
    kind: "network" | "gradients" | "heatmap";
    caption: string;
    data:
      | { layers: number[]; activation: string; derivatives: string[]; residual: string }            // network
      | { layers: string[]; epochs: number[]; norms: number[][] }                                     // gradients: norms[layer][epochIdx]
      | { x: number[]; t: number[]; predicted: number[][]; exact?: number[][] };                     // heatmap
  };
  "speak": { audioUrl: string; text: string };
  "metric": { runId: string; step: number; name: string; value: number };   // live curve feed
  "status": { state: "idle" | "watching" | "offtrack" | "passed" | "thinking" };
  "error": { message: string };
}

// ---------- App -> Engine commands ----------
export interface AppCommands {
  "learn": { query: string };                       // launcher text
  "learn_url": { url: string };                     // pasted YouTube link
  "build_lesson": { resultIds: string[] };
  "action": { kind: "back" | "explain" | "diagram" | "show_me" | "hint" | "voice_toggle" | "ask" | "apply_fix"; text?: string };
  "video.state": { t: number; playing: boolean };   // player reports its position
  "overlay.bounds": { rects: Array<{ x: number; y: number; w: number; h: number }> };
}

export type EngineMessage = { [K in keyof EngineEvents]: { type: K; payload: EngineEvents[K] } }[keyof EngineEvents];
export type AppMessage = { [K in keyof AppCommands]: { type: K; payload: AppCommands[K] } }[keyof AppCommands];

// ---------- App -> Engine: overlay bounds (so the screen reader ignores our own UI) ----------
export interface AppOverlayReport {
  "overlay.bounds": { rects: Array<{ x: number; y: number; w: number; h: number }> }; // send whenever pill/cards/bar move or resize
}
// NOTE: the VS Code extension is dropped. The engine watches the whole screen (any app) and sends spotlight rects.

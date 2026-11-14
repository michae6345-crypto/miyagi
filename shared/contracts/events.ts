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
  "spotlight": { file: string; startLine: number; endLine: number; caption: string } | { clear: true };
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
}

export type EngineMessage = { [K in keyof EngineEvents]: { type: K; payload: EngineEvents[K] } }[keyof EngineEvents];
export type AppMessage = { [K in keyof AppCommands]: { type: K; payload: AppCommands[K] } }[keyof AppCommands];

// ---------- App <-> VS Code extension (ws://localhost:8788) ----------
export interface ExtensionMessages {
  "spotlight": { file: string; startLine: number; endLine: number; caption: string } | { clear: true };
  "editor.state": { file: string; visibleStart: number; visibleEnd: number; cursorLine: number }; // ext -> app
}

'use strict';
// Miyagi companion: a localhost-only HTTP API so the Miyagi engine reads and drives VS Code exactly
// instead of guessing from OCR. Plain JavaScript, no build step, no dependencies. API: README.md.
//
// Every VS Code window runs its own copy of this extension, so each window takes the next free port
// from 8791 (8791..8799). The engine scans that range and picks the window it needs (see
// server/workspace/vscode_ext.py).

const crypto = require('crypto');
const http = require('http');
const fs = require('fs');
const os = require('os');
const path = require('path');
const vscode = require('vscode');

const VERSION = '0.0.7';
const DEFAULT_PORT = 8791;
const PORT_SPAN = 9;
const ACTION_DEADLINE_MS = 250; // the engine's client gives up after 300 ms
const EVENT_TIMEOUT_MS = 300;
const VISIBLE_DEBOUNCE_MS = 80; // `visible`: the engine's type box follows a scroll within ~0.2 s (t7)
const MAX_BODY = 4 * 1024 * 1024;
const TAIL_CHARS = 16000;
const TAIL_LINES = 40;
const TERMINAL_NAME = 'Miyagi';
const EXPLAIN_MAX_CHARS = 2000; // "Miyagi: Explain this": the selection sent to the engine (the rest is cut)
const EXPLAIN_AROUND_LINES = 12; // ...plus this many lines above and below it, so Claude reads it in context
const EXPLAIN_AROUND_CHARS = 3000;
const EXPLAIN_REPEAT_MS = 1000; // the same selection again within this of the last press: dropped (a held key)
const PROPOSED_SCHEME = 'miyagi-proposed';
const PENDING = Symbol('pending');
// .ipynb opens in VS Code's notebook editor (its built-in ipynb notebook type; the Jupyter extension runs the cells),
// never as raw JSON in a text editor (t9 V11). No such editor: VS Code's default for the file (vscode.open).
const NOTEBOOK_TYPE = 'jupyter-notebook';
const NOTEBOOK_WAIT_MS = 1500; // the notebook editor shows up in visibleNotebookEditors shortly after openWith
// The engine's per-launch token (server/engine_token.py): <dir>/<port>.json {token, pid, port}, 0600. While a live
// engine has written one, every call to this API must carry one of the live tokens; events to the engine carry its.
const TOKEN_HEADER = 'x-miyagi-token';
const TOKEN_TTL_MS = 1000;

const S = {
  server: null,
  port: null,
  seq: 0,
  lastFocusedAt: 0,
  lastCommand: null,
  running: new Map(), // TerminalShellExecution -> command record
  highlight: null, // {file, startLine, endLine}
  decorations: null, // {single, top, middle, bottom}
  proposed: new Map(), // miyagi-proposed uri -> text (for /diff)
  proposedEmitter: null,
  dirty: new Map(), // document key -> last isDirty seen
  editorTimer: null,
  visibleTimer: null,
  visibleKey: null, // file|ranges|lineCount of the last `visible` event
  lastExplain: null, // {text, at} of the last "Miyagi: Explain this" press
  tokens: null, // {at, byPort: Map(port -> token)} of the live engines (TOKEN_TTL_MS cache)
  warnedEngineUrl: false,
  log: null,
};

// ---------------------------------------------------------------- helpers

function cfg(key, fallback) {
  try {
    const v = vscode.workspace.getConfiguration('miyagi').get(key);
    return v === undefined || v === null ? fallback : v;
  } catch (_) {
    return fallback;
  }
}

// Miyagi's own overlay (white spotlight box, drawer, cards) is the only UI. The extension draws nothing in VS Code
// (no highlight box, no diff tab) unless miyagi.editorUi is turned on; opening the lesson file and the "Miyagi"
// terminal stay on.
function editorUi() {
  return cfg('editorUi', false) === true;
}

function log(msg) {
  try {
    if (S.log) S.log.appendLine(`[${new Date().toISOString()}] ${msg}`);
  } catch (_) { /* logging must never break anything */ }
}

class HttpError extends Error {
  constructor(status, code, detail) {
    super(code);
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

function folders() {
  return (vscode.workspace.workspaceFolders || []).map((f) => f.uri.fsPath);
}

function docKey(doc) {
  return doc.uri.scheme === 'file' ? doc.uri.fsPath : doc.uri.toString();
}

function samePath(a, b) {
  return !!a && !!b && path.resolve(a) === path.resolve(b);
}

function resolveFile(file) {
  if (typeof file !== 'string' || !file.trim()) throw new HttpError(400, 'file_required');
  let f = file.trim();
  if (f.startsWith('file://')) f = vscode.Uri.parse(f).fsPath;
  if (f === '~' || f.startsWith('~/')) f = path.join(os.homedir(), f.slice(1));
  if (path.isAbsolute(f)) return path.normalize(f);
  const root = folders()[0];
  if (!root) throw new HttpError(400, 'relative_path_without_folder');
  return path.join(root, f);
}

function pos1(p) {
  return { line: p.line + 1, column: p.character + 1 };
}

function int(v) {
  const n = Number(v);
  return Number.isFinite(n) ? Math.trunc(n) : null;
}

function clampLine(line, doc) {
  const n = int(line);
  if (!n) return null;
  return Math.min(Math.max(n, 1), Math.max(doc.lineCount, 1));
}

function shq(s) {
  return `'${String(s).replace(/'/g, `'\\''`)}'`;
}

function editorFor(fsPath) {
  return vscode.window.visibleTextEditors.find((e) => samePath(docKey(e.document), fsPath));
}

async function show(doc, opts) {
  const shown = editorFor(docKey(doc));
  const o = { preview: false, ...opts };
  if (shown && shown.viewColumn && o.viewColumn === undefined) o.viewColumn = shown.viewColumn; // never split
  return vscode.window.showTextDocument(doc, o);
}

// ANSI/OSC escapes out, carriage-return progress bars collapsed to their last state.
function cleanOutput(raw) {
  const s = String(raw || '')
    .replace(/\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)/g, '')
    .replace(/\x1b\[[0-?]*[ -/]*[@-~]/g, '')
    .replace(/\x1b[@-Z\\-_]/g, '')
    .replace(/\r\n/g, '\n');
  return s.split('\n').map((l) => {
    const parts = l.split('\r').filter((p) => p.length);
    return parts.length ? parts[parts.length - 1] : '';
  });
}

function tailLines(raw) {
  const lines = cleanOutput(raw);
  while (lines.length && !lines[lines.length - 1].trim()) lines.pop();
  return lines.slice(-TAIL_LINES);
}

// ---------------------------------------------------------------- state

function openTabs() {
  const out = [];
  const groups = (vscode.window.tabGroups && vscode.window.tabGroups.all) || [];
  for (const g of groups) {
    for (const t of g.tabs || []) {
      const uri = t.input && t.input.uri;
      if (!uri) continue;
      out.push({ file: uri.scheme === 'file' ? uri.fsPath : uri.toString(), dirty: !!t.isDirty,
        active: !!(t.isActive && g.isActive) });
      if (out.length >= 30) return out;
    }
  }
  return out;
}

function hasShellApi() {
  return typeof vscode.window.onDidStartTerminalShellExecution === 'function'
    && typeof vscode.window.onDidEndTerminalShellExecution === 'function';
}

function publicCommand(rec) {
  if (!rec) return null;
  return {
    id: rec.id,
    commandLine: rec.commandLine,
    exitCode: rec.exitCode,
    running: rec.running,
    terminal: rec.terminal,
    cwd: rec.cwd,
    outputTail: tailLines(rec.out),
    startedAt: rec.startedAt,
    endedAt: rec.endedAt,
  };
}

function snapshot() {
  const ed = vscode.window.activeTextEditor;
  const doc = ed && ed.document;
  const term = vscode.window.activeTerminal;
  const winState = vscode.window.state || {};
  return {
    ok: true,
    app: 'vscode',
    extension: VERSION,
    vscodeVersion: vscode.version,
    pid: process.pid,
    port: S.port,
    folders: folders(),
    workspaceName: vscode.workspace.name || null,
    file: doc ? docKey(doc) : null,
    relPath: doc && doc.uri.scheme === 'file' ? vscode.workspace.asRelativePath(doc.uri, false) : null,
    dirty: doc ? !!doc.isDirty : false,
    languageId: doc ? doc.languageId : null,
    lineCount: doc ? doc.lineCount : 0,
    cursor: ed ? pos1(ed.selection.active) : null,
    selection: ed && !ed.selection.isEmpty ? { start: pos1(ed.selection.start), end: pos1(ed.selection.end) } : null,
    visibleRanges: ed ? ed.visibleRanges.map((r) => ({ startLine: r.start.line + 1, endLine: r.end.line + 1 })) : [],
    dirtyFiles: vscode.workspace.textDocuments.filter((d) => d.isDirty).map(docKey),
    openFiles: openTabs(),
    terminalOpen: vscode.window.terminals.length > 0,
    activeTerminal: term ? term.name : null,
    terminals: vscode.window.terminals.map((t) => ({ name: t.name, active: t === term, shellIntegration: !!t.shellIntegration })),
    lastCommand: publicCommand(S.lastCommand),
    shellIntegrationApi: hasShellApi(),
    windowFocused: !!winState.focused,
    lastFocusedAt: S.lastFocusedAt,
    highlight: S.highlight,
  };
}

async function readText(query) {
  const want = query.get('file');
  let doc;
  if (want) {
    const fsPath = resolveFile(want);
    doc = vscode.workspace.textDocuments.find((d) => samePath(docKey(d), fsPath));
    if (!doc) {
      if (!fs.existsSync(fsPath)) throw new HttpError(404, 'not_found');
      doc = await vscode.workspace.openTextDocument(vscode.Uri.file(fsPath));
    }
  } else {
    const ed = vscode.window.activeTextEditor;
    if (!ed) throw new HttpError(404, 'no_active_editor');
    doc = ed.document;
  }
  return { ok: true, file: docKey(doc), text: doc.getText(), dirty: !!doc.isDirty, version: doc.version,
    languageId: doc.languageId, lineCount: doc.lineCount };
}

// ---------------------------------------------------------------- actions

function isNotebook(fsPath) {
  return path.extname(String(fsPath || '')).toLowerCase() === '.ipynb';
}

function notebookDoc(fsPath) {
  return (vscode.workspace.notebookDocuments || [])
    .find((nb) => nb.uri && nb.uri.scheme === 'file' && samePath(nb.uri.fsPath, fsPath));
}

function notebookEditorFor(fsPath) {
  const mine = (e) => e && e.notebook && e.notebook.uri.scheme === 'file' && samePath(e.notebook.uri.fsPath, fsPath);
  const a = vscode.window.activeNotebookEditor;
  return mine(a) ? a : (vscode.window.visibleNotebookEditors || []).find(mine);
}

async function waitForNotebookEditor(fsPath) {
  const until = Date.now() + NOTEBOOK_WAIT_MS;
  for (;;) {
    const ne = notebookEditorFor(fsPath);
    if (ne || Date.now() > until) return ne;
    await new Promise((r) => setTimeout(r, 25));
  }
}

// The engine's line for a notebook is a line of the raw .ipynb JSON on disk (server/orchestrator/workspace.py
// target_location; past the end = "where new code goes"). -> 0-based index of the cell that line belongs to, or null.
function notebookCellForLine(text, line) {
  let nb;
  try { nb = JSON.parse(text); } catch (_) { return null; }
  const cells = nb && Array.isArray(nb.cells) ? nb.cells : [];
  if (!cells.length || !(line >= 1)) return null;
  const lines = text.split('\n');
  if (line > lines.length) return cells.length - 1;
  let at = -1; // nbformat writes each cell's keys sorted, so a cell starts at its "cell_type" key
  for (let i = 0; i < line; i++) if (/^\s*"cell_type"\s*:/.test(lines[i])) at++;
  const src = (c) => (Array.isArray(c.source) ? c.source.join('') : String(c.source || ''));
  let want = null; // the source text on that line, if it is one (e.g. `   "x = mnist.load_data()\n",`)
  try { want = JSON.parse(lines[line - 1].trim().replace(/,$/, '')); } catch (_) { want = null; }
  if (typeof want === 'string' && want.trim()) {
    want = want.trim();
    if (at >= 0 && at < cells.length && src(cells[at]).includes(want)) return at;
    const hit = cells.findIndex((c) => src(c).includes(want));
    if (hit >= 0) return hit;
  }
  return at >= 0 && at < cells.length ? at : null;
}

async function openNotebook(fsPath, body) {
  const uri = vscode.Uri.file(fsPath);
  const opts = { preserveFocus: !!body.preserveFocus, preview: false };
  const shown = notebookEditorFor(fsPath);
  if (shown && shown.viewColumn) opts.viewColumn = shown.viewColumn; // never split
  let ne;
  try {
    await vscode.commands.executeCommand('vscode.openWith', uri, NOTEBOOK_TYPE, opts);
    ne = await waitForNotebookEditor(fsPath);
  } catch (err) {
    log(`open: ${fsPath} in the notebook editor failed: ${(err && err.message) || err}`);
  }
  const line = int(body.line) > 0 ? int(body.line) : null;
  if (!ne) { // no notebook editor (no ipynb support): whatever VS Code opens .ipynb with
    await vscode.commands.executeCommand('vscode.open', uri, opts);
    return { ok: true, file: fsPath, line, notebook: false, cell: null, languageId: null, dirty: false };
  }
  let cell = null;
  if (line) {
    let text = null;
    try { text = fs.readFileSync(fsPath, 'utf8'); } catch (_) { text = null; }
    cell = text === null ? null : notebookCellForLine(text, line);
    const count = ne.notebook.cellCount || 0;
    if (cell !== null && cell >= count) cell = count ? count - 1 : null; // the buffer has fewer cells than the disk
    if (cell !== null && vscode.NotebookRange) {
      const r = new vscode.NotebookRange(cell, cell + 1);
      ne.selections = [r];
      const how = vscode.NotebookEditorRevealType;
      ne.revealRange(r, how ? how.InCenterIfOutsideViewport : undefined);
    }
  }
  return { ok: true, file: fsPath, line, notebook: true, cell, languageId: null, dirty: !!ne.notebook.isDirty };
}

async function openFile(body) {
  const fsPath = resolveFile(body.file);
  if (!fs.existsSync(fsPath) && !vscode.workspace.textDocuments.some((d) => samePath(docKey(d), fsPath))) {
    throw new HttpError(404, 'not_found');
  }
  if (isNotebook(fsPath)) return openNotebook(fsPath, body);
  const doc = await vscode.workspace.openTextDocument(vscode.Uri.file(fsPath));
  const line = clampLine(body.line, doc);
  const opts = { preserveFocus: !!body.preserveFocus };
  if (line) {
    const p = new vscode.Position(line - 1, Math.max(0, (int(body.column) || 1) - 1));
    opts.selection = new vscode.Range(p, p);
  }
  const ed = await show(doc, opts);
  if (line && ed) ed.revealRange(new vscode.Range(line - 1, 0, line - 1, 0), vscode.TextEditorRevealType.InCenter);
  return { ok: true, file: fsPath, line, languageId: doc.languageId, dirty: !!doc.isDirty };
}

function decorationTypes() {
  if (!S.decorations) {
    const base = { isWholeLine: true, borderColor: '#ffffff', borderStyle: 'solid',
      backgroundColor: 'rgba(255,255,255,0.08)', overviewRulerColor: 'rgba(255,255,255,0.8)' };
    if (vscode.OverviewRulerLane) base.overviewRulerLane = vscode.OverviewRulerLane.Full;
    const make = (borderWidth, borderRadius) => vscode.window.createTextEditorDecorationType({ ...base, borderWidth, borderRadius });
    // one continuous box around the block: top line, middle lines, bottom line (or a single line)
    S.decorations = {
      single: make('2px', '4px'),
      top: make('2px 2px 0 2px', '4px 4px 0 0'),
      middle: make('0 2px 0 2px', '0'),
      bottom: make('0 2px 2px 2px', '0 0 4px 4px'),
    };
  }
  return S.decorations;
}

function paintHighlight(editor) {
  const draw = editorUi();
  if (!draw && !S.decorations) return; // invisible by default: no decoration types, nothing painted
  const d = decorationTypes();
  const h = S.highlight;
  const on = draw && h && samePath(docKey(editor.document), h.file);
  const ranges = { single: [], top: [], middle: [], bottom: [] };
  if (on) {
    const line = (n) => new vscode.Range(n - 1, 0, n - 1, 0);
    if (h.startLine === h.endLine) ranges.single.push(line(h.startLine));
    else {
      ranges.top.push(line(h.startLine));
      for (let n = h.startLine + 1; n < h.endLine; n++) ranges.middle.push(line(n));
      ranges.bottom.push(line(h.endLine));
    }
  }
  for (const k of Object.keys(d)) editor.setDecorations(d[k], ranges[k]);
}

function clearHighlight() {
  S.highlight = null;
  if (!S.decorations) return;
  for (const ed of vscode.window.visibleTextEditors) paintHighlight(ed);
}

async function highlight(body) {
  if (body.clear) {
    clearHighlight();
    return { ok: true, cleared: true };
  }
  const fsPath = resolveFile(body.file);
  const start = int(body.startLine !== undefined ? body.startLine : body.line);
  if (!start) throw new HttpError(400, 'startLine_required');
  const doc = await vscode.workspace.openTextDocument(vscode.Uri.file(fsPath));
  const s = clampLine(start, doc);
  const e = Math.max(s, clampLine(int(body.endLine) || start, doc));
  let ed = editorFor(fsPath);
  if (!ed || body.focus) ed = await show(doc, { preserveFocus: !body.focus });
  for (const other of vscode.window.visibleTextEditors) if (other !== ed) paintHighlight(other);
  S.highlight = { file: fsPath, startLine: s, endLine: e };
  paintHighlight(ed);
  if (body.reveal !== false) ed.revealRange(new vscode.Range(s - 1, 0, e - 1, 0), vscode.TextEditorRevealType.InCenter);
  return { ok: true, ...S.highlight };
}

function findTerminal(name) {
  return vscode.window.terminals.find((t) => t.name === name && !t.exitStatus);
}

// A terminal Miyagi just created: text sent before its shell prints the first prompt is echoed twice (once raw by
// the tty, once after the prompt). Commands wait for shell integration to come up (the prompt is there), or
// SHELL_READY_MS when it never does (shell integration off). Without the API (VS Code < 1.93): sent at once.
const SHELL_READY_MS = 3000;
const shellReady = new WeakMap(); // Terminal -> Promise, resolved once its shell can take a command

function waitForShell(t) {
  return new Promise((resolve) => {
    const on = vscode.window.onDidChangeTerminalShellIntegration;
    if (t.shellIntegration || typeof on !== 'function') return resolve();
    let sub = null;
    const done = () => { clearTimeout(timer); if (sub) sub.dispose(); resolve(); };
    const timer = setTimeout(done, SHELL_READY_MS);
    sub = on((e) => { if (e.terminal === t) done(); });
  });
}

function miyagiTerminal(cwd) {
  const t = findTerminal(TERMINAL_NAME);
  if (t) return { t, created: false };
  const opts = { name: TERMINAL_NAME };
  const dir = cwd ? path.resolve(cwd) : folders()[0];
  if (dir && fs.existsSync(dir)) opts.cwd = dir;
  const nt = vscode.window.createTerminal(opts);
  shellReady.set(nt, waitForShell(nt));
  return { t: nt, created: true };
}

async function terminal(body) {
  if (body.show === false) {
    await vscode.commands.executeCommand('workbench.action.closePanel');
    return { ok: true, shown: false };
  }
  let created = false;
  let t = findTerminal(TERMINAL_NAME) || vscode.window.activeTerminal;
  if (!t) ({ t, created } = miyagiTerminal(body.cwd));
  t.show(!!body.preserveFocus);
  return { ok: true, shown: true, terminal: t.name, created };
}

async function terminalRun(body) {
  const cmd = String(body.cmd || body.command || '').trim();
  if (!cmd) throw new HttpError(400, 'cmd_required');
  const { t, created } = miyagiTerminal(body.cwd);
  let text = cmd;
  if (body.cwd && !created) {
    const here = t.shellIntegration && t.shellIntegration.cwd ? t.shellIntegration.cwd.fsPath : null;
    if (!samePath(here, body.cwd)) text = `cd ${shq(path.resolve(body.cwd))} && ${cmd}`;
  }
  t.show(!!body.preserveFocus);
  // answer now (the engine waits 300 ms at most); a new terminal gets the command once its shell is ready
  const send = () => { t.sendText(text, true); log(`terminal/run: ${text}`); };
  const ready = shellReady.get(t);
  if (ready && !t.shellIntegration) ready.then(send).catch((e) => log(`terminal/run failed: ${e}`));
  else send();
  return { ok: true, terminal: t.name, created, sent: text, shellIntegration: !!t.shellIntegration,
    reportsExitCode: hasShellApi() };
}

function fullRange(doc) {
  const last = doc.lineAt(Math.max(doc.lineCount - 1, 0));
  return new vscode.Range(0, 0, last.range.end.line, last.range.end.character);
}

// One edit -> [range, text]. Lines/columns are 1-based. Forms:
//   {find, replace}                                   the first line equal to `find` (trimmed), indentation kept
//   {startLine, endLine?, text}                       whole lines, inclusive; endLine = startLine - 1 inserts before startLine
//   {startLine, startColumn, endLine, endColumn, text} exact character range (end exclusive)
function editToReplace(doc, e) {
  if (typeof e.find === 'string') {
    const want = e.find.trim();
    for (let i = 0; i < doc.lineCount; i++) {
      const line = doc.lineAt(i);
      if (line.text.trim() !== want) continue;
      const indent = line.text.slice(0, line.text.length - line.text.trimStart().length);
      const repl = String(e.replace === undefined ? '' : e.replace).split('\n')
        .map((l) => (l.length && !/^\s/.test(l) ? indent + l : l)).join('\n');
      return [line.range, repl];
    }
    throw new HttpError(409, 'find_not_found', e.find);
  }
  const start = int(e.startLine);
  if (!start || start < 1) throw new HttpError(400, 'bad_edit', e);
  const text = String(e.text === undefined ? '' : e.text);
  if (e.startColumn !== undefined || e.endColumn !== undefined) {
    const end = int(e.endLine) || start;
    const r = new vscode.Range(start - 1, Math.max((int(e.startColumn) || 1) - 1, 0),
      end - 1, Math.max((int(e.endColumn) || 1) - 1, 0));
    return [doc.validateRange(r), text];
  }
  const end = e.endLine === undefined ? start : int(e.endLine);
  const nl = text.length && !text.endsWith('\n') ? '\n' : '';
  if (start > doc.lineCount) { // append after the last line
    const endPos = fullRange(doc).end;
    const lead = doc.getText().length && !doc.getText().endsWith('\n') ? '\n' : '';
    return [new vscode.Range(endPos, endPos), lead + text];
  }
  if (end < doc.lineCount) return [new vscode.Range(start - 1, 0, end, 0), text + nl];
  return [new vscode.Range(new vscode.Position(start - 1, 0), fullRange(doc).end), text];
}

async function apply(body) {
  const fsPath = resolveFile(body.file);
  // A notebook's text is its JSON: a text edit would fight the notebook editor's own copy (and open raw JSON on
  // reveal). The engine writes .ipynb cell by cell on disk, and asks to save (POST /save) before that.
  if (isNotebook(fsPath)) throw new HttpError(409, 'notebook_unsupported', 'edit notebooks cell by cell, not as text');
  const uri = vscode.Uri.file(fsPath);
  const known = fs.existsSync(fsPath) || vscode.workspace.textDocuments.some((d) => samePath(docKey(d), fsPath));
  const we = new vscode.WorkspaceEdit();
  if (!known) {
    if (typeof body.newText !== 'string') throw new HttpError(404, 'not_found');
    we.createFile(uri, { ignoreIfExists: true });
    we.insert(uri, new vscode.Position(0, 0), body.newText);
  } else {
    const doc = await vscode.workspace.openTextDocument(uri);
    if (typeof body.newText === 'string') we.replace(uri, fullRange(doc), body.newText);
    else if (Array.isArray(body.edits) && body.edits.length) {
      for (const e of body.edits) {
        const [range, text] = editToReplace(doc, e || {});
        we.replace(uri, range, text);
      }
    } else throw new HttpError(400, 'newText_or_edits_required');
  }
  const applied = await vscode.workspace.applyEdit(we);
  if (!applied) throw new HttpError(409, 'edit_rejected');
  const doc = await vscode.workspace.openTextDocument(uri);
  let saved = false;
  if (body.save !== false) saved = !!(await doc.save());
  if (body.reveal !== false) await show(doc, { preserveFocus: true });
  return { ok: true, file: fsPath, created: !known, saved, dirty: !!doc.isDirty, version: doc.version,
    lineCount: doc.lineCount };
}

function proposedUri(fsPath, text) {
  const uri = vscode.Uri.from({ scheme: PROPOSED_SCHEME, path: fsPath, query: String(++S.seq) });
  S.proposed.set(uri.toString(), text);
  while (S.proposed.size > 20) S.proposed.delete(S.proposed.keys().next().value);
  return uri;
}

async function diff(body) {
  const fsPath = resolveFile(body.file);
  if (typeof body.newText !== 'string') throw new HttpError(400, 'newText_required');
  if (!editorUi()) throw new HttpError(409, 'editor_ui_off'); // no diff tab: Miyagi's card shows the diff
  const exists = fs.existsSync(fsPath) || vscode.workspace.textDocuments.some((d) => samePath(docKey(d), fsPath));
  const left = exists ? vscode.Uri.file(fsPath) : proposedUri(fsPath, '');
  const right = proposedUri(fsPath, body.newText);
  const title = body.title || `${path.basename(fsPath)}: yours ↔ Miyagi's fix`;
  await vscode.commands.executeCommand('vscode.diff', left, right, title,
    { preview: true, preserveFocus: !!body.preserveFocus });
  return { ok: true, file: fsPath, title, proposed: right.toString() };
}

// After Miyagi pip-installs a package into the lesson's <folder>/.venv (E20): Pylance resolved `import requests` when
// the folder opened, before the .venv existed, and kept its "could not be resolved" warning. Select that .venv as
// this folder's interpreter (Python extension API) and restart the Python language server so it re-reads the
// packages. Best effort: either part may be unavailable (no Python extension, an older API).
async function pythonRefresh(body) {
  const root = body && body.folder ? path.resolve(String(body.folder)) : folders()[0];
  if (!root) throw new HttpError(400, 'folder_required');
  const wf = typeof vscode.workspace.getWorkspaceFolder === 'function'
    ? vscode.workspace.getWorkspaceFolder(vscode.Uri.file(root)) : undefined;
  const py = process.platform === 'win32'
    ? path.join(root, '.venv', 'Scripts', 'python.exe')
    : path.join(root, '.venv', 'bin', 'python');
  const out = { ok: true, folder: root, interpreter: null, restarted: false };
  if (fs.existsSync(py)) {
    try {
      const ext = vscode.extensions.getExtension('ms-python.python');
      const api = ext ? (ext.isActive ? ext.exports : await ext.activate()) : null;
      const envs = api && api.environments;
      if (envs && typeof envs.updateActiveEnvironmentPath === 'function') {
        if (typeof envs.refreshEnvironments === 'function') await envs.refreshEnvironments();
        await envs.updateActiveEnvironmentPath(py, wf ? wf.uri : vscode.Uri.file(root));
        out.interpreter = py;
      }
    } catch (err) {
      log(`python/refresh: selecting ${py} failed: ${(err && err.message) || err}`);
    }
  }
  try {
    await vscode.commands.executeCommand('python.analysis.restartLanguageServer');
    out.restarted = true;
  } catch (err) {
    log(`python/refresh: restarting the language server failed: ${(err && err.message) || err}`);
  }
  log(`python/refresh: ${JSON.stringify(out)}`);
  return out;
}

// Save one file the way Cmd+S does (its unsaved edits go to disk). The engine saves the lesson file before Run it for
// me and Check on a run step, so the code that runs is the code the editor shows. A file with no open buffer, or a
// clean one, is left alone. No file: the active editor's.
async function save(body) {
  const fsPath = body && body.file ? resolveFile(body.file) : null;
  const ed = vscode.window.activeTextEditor;
  // A notebook saves as a notebook (its cells and outputs), never through a raw JSON text buffer.
  const nbe = vscode.window.activeNotebookEditor;
  const nb = fsPath ? (isNotebook(fsPath) ? notebookDoc(fsPath) : null)
    : (ed && ed.document.uri.scheme === 'vscode-notebook-cell' && nbe ? nbe.notebook : null);
  if (nb) {
    const was = !!nb.isDirty;
    const saved = was ? !!(await (typeof nb.save === 'function' ? nb.save() : vscode.workspace.save(nb.uri))) : false;
    if (was) log(`save: notebook ${nb.uri.fsPath} -> ${saved}`);
    return { ok: true, file: nb.uri.fsPath, open: true, notebook: true, saved, wasDirty: was, dirty: !!nb.isDirty };
  }
  const doc = fsPath ? vscode.workspace.textDocuments.find((d) => samePath(docKey(d), fsPath)) : ed && ed.document;
  if (!doc) return { ok: true, file: fsPath, open: false, saved: false, dirty: false };
  const was = !!doc.isDirty;
  const saved = was ? !!(await doc.save()) : false;
  if (was) log(`save: ${docKey(doc)} -> ${saved}`);
  return { ok: true, file: docKey(doc), open: true, saved, wasDirty: was, dirty: !!doc.isDirty };
}

const ACTIONS = {
  'POST /open': openFile,
  'POST /highlight': highlight,
  'POST /terminal': terminal,
  'POST /terminal/run': terminalRun,
  'POST /apply': apply,
  'POST /save': save,
  'POST /diff': diff,
  'POST /python/refresh': pythonRefresh,
};

// Answer within ACTION_DEADLINE_MS. A slower action still finishes: the reply says {pending, id} and the
// result arrives as an `action_done` event.
async function runAction(name, fn, body) {
  const p = Promise.resolve().then(() => fn(body));
  let timer;
  const deadline = new Promise((r) => { timer = setTimeout(() => r(PENDING), ACTION_DEADLINE_MS); });
  try {
    const first = await Promise.race([p, deadline]);
    if (first !== PENDING) return first;
  } finally {
    clearTimeout(timer);
  }
  const id = ++S.seq;
  p.then((result) => postEvent('action_done', { action: name, id, result }),
    (err) => postEvent('action_done', { action: name, id, result: errorBody(err) }));
  return { ok: true, pending: true, id, action: name };
}

// ---------------------------------------------------------------- engine token

function tokenDir() {
  return process.env.MIYAGI_ENGINE_TOKEN_DIR || path.join(os.homedir(), '.miyagi', 'engine-tokens');
}

function pidAlive(pid) {
  if (!Number.isInteger(pid) || pid <= 0) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch (err) {
    return !!(err && err.code === 'EPERM');
  }
}

// port -> token of every live engine (a file whose engine is gone is ignored: an engine crash never locks us out)
function liveTokens() {
  const now = Date.now();
  if (S.tokens && now - S.tokens.at < TOKEN_TTL_MS) return S.tokens.byPort;
  const byPort = new Map();
  let names = [];
  try {
    names = fs.readdirSync(tokenDir()).filter((n) => /^\d+\.json$/.test(n));
  } catch (_) { /* no engine has written one: older engines, or none running */ }
  for (const n of names) {
    try {
      const d = JSON.parse(fs.readFileSync(path.join(tokenDir(), n), 'utf8'));
      if (d && typeof d.token === 'string' && d.token && pidAlive(d.pid)) byPort.set(Number(d.port) || 0, d.token);
    } catch (_) { /* half-written or unreadable: skip */ }
  }
  S.tokens = { at: now, byPort };
  return byPort;
}

function sameToken(a, b) {
  const x = Buffer.from(String(a));
  const y = Buffer.from(String(b));
  return x.length === y.length && crypto.timingSafeEqual(x, y);
}

// ---------------------------------------------------------------- HTTP

const LOCAL_HOST = /^(127\.0\.0\.1|localhost|\[::1\])(:\d+)?$/i;
const LOOPBACK_ADDR = /^(127\.\d+\.\d+\.\d+|::1|::ffff:127\.\d+\.\d+\.\d+)$/;
const LOOPBACK_NAME = /^(127\.0\.0\.1|localhost|\[::1\]|::1)$/i;

// Browsers can reach 127.0.0.1 too: refuse anything a web page could send (Origin, Sec-Fetch-Site,
// non-JSON simple POSTs) and DNS-rebinding Hosts. The engine's plain HTTP client sends none of these.
// While a live engine has written its token, every route but GET / and /health needs it (0.0.7): another local
// program can't open files, run terminal commands or edit buffers through us. No live engine token (an older
// engine, an engine started without one): open to loopback as before.
function refuse(req, route) {
  const remote = String((req.socket && req.socket.remoteAddress) || '');
  if (remote && !LOOPBACK_ADDR.test(remote)) return [403, 'not_loopback'];
  if (req.headers.origin) return [403, 'origin_not_allowed'];
  const site = req.headers['sec-fetch-site'];
  if (site && site !== 'none') return [403, 'browser_not_allowed'];
  if (!LOCAL_HOST.test(String(req.headers.host || ''))) return [403, 'host_not_allowed'];
  if (req.method === 'POST' && !/^application\/json\b/i.test(String(req.headers['content-type'] || ''))) {
    return [415, 'json_required'];
  }
  if (route !== 'GET /' && route !== 'GET /health') {
    const live = [...liveTokens().values()];
    const given = req.headers[TOKEN_HEADER];
    if (live.length && !(typeof given === 'string' && live.some((t) => sameToken(t, given.trim())))) {
      return [401, 'token_required'];
    }
  }
  return null;
}

function send(res, status, body) {
  const data = JSON.stringify(body);
  res.writeHead(status, { 'content-type': 'application/json; charset=utf-8', 'content-length': Buffer.byteLength(data),
    'cache-control': 'no-store' });
  res.end(data);
}

function errorBody(err) {
  if (err instanceof HttpError) {
    const b = { ok: false, error: err.code };
    if (err.detail !== undefined) b.detail = err.detail;
    return b;
  }
  return { ok: false, error: 'internal', detail: String((err && err.message) || err) };
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    let size = 0;
    const chunks = [];
    req.on('data', (c) => {
      size += c.length;
      if (size > MAX_BODY) {
        reject(new HttpError(413, 'body_too_large'));
        req.destroy();
      } else chunks.push(c);
    });
    req.on('end', () => {
      const raw = Buffer.concat(chunks).toString('utf8');
      if (!raw.trim()) return resolve({});
      try {
        const v = JSON.parse(raw);
        resolve(v && typeof v === 'object' && !Array.isArray(v) ? v : {});
      } catch (_) {
        reject(new HttpError(400, 'bad_json'));
      }
    });
    req.on('error', reject);
  });
}

async function handle(req, res) {
  const url = new URL(req.url || '/', 'http://127.0.0.1');
  const route = `${req.method} ${url.pathname.replace(/\/+$/, '') || '/'}`;
  const no = refuse(req, route);
  if (no) return send(res, no[0], { ok: false, error: no[1] });
  try {
    if (route === 'GET /' || route === 'GET /health') {
      return send(res, 200, { ok: true, name: 'miyagi-companion', version: VERSION, port: S.port, pid: process.pid });
    }
    if (route === 'GET /state') return send(res, 200, snapshot());
    if (route === 'GET /text') return send(res, 200, await readText(url.searchParams));
    const fn = ACTIONS[route];
    if (!fn) return send(res, 404, { ok: false, error: 'no_route', route });
    const body = await readBody(req);
    return send(res, 200, await runAction(route.slice(5), fn, body));
  } catch (err) {
    if (!(err instanceof HttpError)) log(`${route} failed: ${(err && err.stack) || err}`);
    return send(res, err instanceof HttpError ? err.status : 500, errorBody(err));
  }
}

function listen(base) {
  return new Promise((resolve) => {
    let port = base;
    let tries = 0;
    const attempt = () => {
      const srv = http.createServer((req, res) => {
        handle(req, res).catch((err) => {
          try { send(res, 500, errorBody(err)); } catch (_) { /* socket gone */ }
        });
      });
      srv.once('error', (err) => {
        if (err && err.code === 'EADDRINUSE' && base !== 0 && ++tries < PORT_SPAN) {
          port += 1;
          attempt();
        } else {
          log(`no port: ${(err && err.message) || err}`);
          resolve(null);
        }
      });
      srv.listen(port, '127.0.0.1', () => resolve(srv));
    };
    attempt();
  });
}

// ---------------------------------------------------------------- events -> engine

// Events go to the engine on this Mac only: a workspace's .vscode/settings.json could point miyagi.engineUrl
// elsewhere and collect file names, selections and terminal output (0.0.7). Non-loopback URLs are dropped.
function engineTarget() {
  let u;
  try {
    u = new URL('/vscode/event', String(cfg('engineUrl', 'http://127.0.0.1:8787')));
  } catch (_) {
    return null;
  }
  if (u.protocol !== 'http:' || !LOOPBACK_NAME.test(u.hostname)) {
    if (!S.warnedEngineUrl) {
      S.warnedEngineUrl = true;
      log(`miyagi.engineUrl is not on this Mac (${u.protocol}//${u.hostname}): events are not sent`);
    }
    return null;
  }
  return u;
}

function postEvent(type, extra) {
  const u = engineTarget();
  if (!u) return;
  const body = JSON.stringify({ type, ts: Date.now(), port: S.port, pid: process.pid, folders: folders(),
    windowFocused: !!(vscode.window.state && vscode.window.state.focused), ...extra });
  const headers = { 'content-type': 'application/json', 'content-length': Buffer.byteLength(body) };
  const token = liveTokens().get(Number(u.port || 80));
  if (token) headers[TOKEN_HEADER] = token;
  try {
    const req = http.request({ hostname: u.hostname.replace(/^\[|\]$/g, ''), port: u.port || 80, path: u.pathname,
      method: 'POST', timeout: EVENT_TIMEOUT_MS, headers });
    req.on('timeout', () => req.destroy());
    req.on('error', () => { /* engine not running: fine */ });
    req.on('response', (r) => r.resume());
    req.end(body);
  } catch (_) { /* best effort */ }
}

function editorPayload() {
  const ed = vscode.window.activeTextEditor;
  const doc = ed && ed.document;
  return { file: doc ? docKey(doc) : null, languageId: doc ? doc.languageId : null, dirty: doc ? !!doc.isDirty : false };
}

function cmdLine(execution) {
  const c = execution && execution.commandLine;
  if (typeof c === 'string') return c;
  return c && typeof c.value === 'string' ? c.value : '';
}

async function drain(execution, rec) {
  try {
    for await (const chunk of execution.read()) rec.out = (rec.out + chunk).slice(-TAIL_CHARS);
  } catch (_) { /* stream closed */ }
}

function onCommandStart(e) {
  const rec = { id: ++S.seq, commandLine: cmdLine(e.execution), exitCode: null, running: true,
    terminal: e.terminal ? e.terminal.name : null,
    cwd: e.execution && e.execution.cwd ? e.execution.cwd.fsPath : null,
    out: '', startedAt: Date.now(), endedAt: null };
  S.running.set(e.execution, rec);
  S.lastCommand = rec;
  rec.drained = drain(e.execution, rec);
  postEvent('command_start', { command: publicCommand(rec) });
}

function onCommandEnd(e) {
  let rec = S.running.get(e.execution);
  S.running.delete(e.execution);
  if (!rec) {
    rec = { id: ++S.seq, commandLine: cmdLine(e.execution), terminal: e.terminal ? e.terminal.name : null,
      cwd: e.execution && e.execution.cwd ? e.execution.cwd.fsPath : null, out: '', startedAt: null };
  }
  rec.exitCode = e.exitCode === undefined ? null : e.exitCode;
  rec.running = false;
  rec.endedAt = Date.now();
  S.lastCommand = rec;
  // the output stream can still be flushing its last chunk when the end event fires
  const flushed = Promise.race([rec.drained || Promise.resolve(), new Promise((r) => setTimeout(r, 150))]);
  return flushed.then(() => postEvent('command_end', { command: publicCommand(rec) }));
}

function onDocChange(e) {
  const doc = e.document;
  const key = docKey(doc);
  const act = vscode.window.activeTextEditor;
  if (act && act.document === doc) onVisible({ textEditor: act }); // the line count may have changed (a paste, a reload)
  const was = S.dirty.get(key);
  if (was === !!doc.isDirty) return;
  S.dirty.set(key, !!doc.isDirty);
  if (was === undefined && !doc.isDirty) return;
  postEvent('dirty', { file: key, dirty: !!doc.isDirty, languageId: doc.languageId });
}

function onSave(doc) {
  S.dirty.set(docKey(doc), false);
  postEvent('save', { file: docKey(doc), languageId: doc.languageId });
}

function onEditor() {
  clearTimeout(S.editorTimer);
  S.editorTimer = setTimeout(() => postEvent('editor', editorPayload()), 120);
}

function visiblePayload() {
  const ed = vscode.window.activeTextEditor;
  const doc = ed && ed.document;
  return { file: doc ? docKey(doc) : null, lineCount: doc ? doc.lineCount : 0,
    visibleRanges: ed ? ed.visibleRanges.map((r) => ({ startLine: r.start.line + 1, endLine: r.end.line + 1 })) : [] };
}

// t7: the active editor scrolled or its line count changed -> `visible` (80 ms debounce; only real changes), so the
// engine's "Type it here" box follows its row at once instead of on its next screen frame.
function onVisible(e) {
  const ed = e && e.textEditor;
  if (!ed || ed !== vscode.window.activeTextEditor) return;
  clearTimeout(S.visibleTimer);
  S.visibleTimer = setTimeout(() => {
    const p = visiblePayload();
    const key = `${p.file}|${p.visibleRanges.map((r) => `${r.startLine}-${r.endLine}`).join(',')}|${p.lineCount}`;
    if (key === S.visibleKey) return;
    S.visibleKey = key;
    postEvent('visible', p);
  }, VISIBLE_DEBOUNCE_MS);
}

function onWindowState(st) {
  if (st && st.focused) S.lastFocusedAt = Date.now();
  postEvent('focus', { focused: !!(st && st.focused) });
}

// ---------------------------------------------------------------- "Miyagi: Explain this"

// The lines around [startLine, endLine] (1-based), capped, so the engine can explain the selection in context.
function aroundText(doc, startLine, endLine) {
  const first = Math.max(1, startLine - EXPLAIN_AROUND_LINES);
  const last = Math.min(doc.lineCount, endLine + EXPLAIN_AROUND_LINES);
  const lines = [];
  for (let n = first; n <= last; n++) lines.push(doc.lineAt(n - 1).text);
  return { startLine: first, text: lines.join('\n').slice(0, EXPLAIN_AROUND_CHARS) };
}

// The selection, else the cursor's line, as {file, text, startLine, endLine, languageId, ...}; null without an editor.
function selectionPayload(ed) {
  if (!ed || !ed.document) return null;
  const doc = ed.document;
  const sel = ed.selection;
  let text;
  let startLine;
  let endLine;
  if (!sel || sel.isEmpty) {
    const line = sel ? sel.active.line : 0;
    text = doc.lineAt(line).text;
    startLine = line + 1;
    endLine = line + 1;
  } else {
    text = doc.getText(new vscode.Range(sel.start, sel.end));
    startLine = sel.start.line + 1;
    // a selection that ends at column 0 of the next line (a triple-click / whole-line select) ends on the line above
    endLine = sel.end.line + (sel.end.character === 0 && sel.end.line > sel.start.line ? 0 : 1);
  }
  return {
    file: docKey(doc),
    relPath: doc.uri.scheme === 'file' ? vscode.workspace.asRelativePath(doc.uri, false) : null,
    languageId: doc.languageId,
    text: text.slice(0, EXPLAIN_MAX_CHARS),
    truncated: text.length > EXPLAIN_MAX_CHARS,
    fromCursorLine: !sel || sel.isEmpty,
    startLine,
    endLine,
    around: aroundText(doc, startLine, endLine),
  };
}

// Posts `explain_selection` to the engine, which answers with an Explain card in Miyagi's overlay. Shows nothing in
// VS Code (no toast, no webview), whatever miyagi.editorUi says; it only reads the editor, so it works in Restricted
// Mode. An empty line still goes out (text ""): the engine's card says to select something. VS Code repeats a held
// keybinding, so presses of the same selection under EXPLAIN_REPEAT_MS apart count as one (the engine also drops a
// press while it is still answering, or right after it answered the same selection).
function explainSelection() {
  const payload = selectionPayload(vscode.window.activeTextEditor);
  if (!payload) {
    log('explain: no active editor');
    return false;
  }
  const now = Date.now();
  const last = S.lastExplain;
  S.lastExplain = { text: payload.text, at: now };
  if (last && last.text === payload.text && now - last.at < EXPLAIN_REPEAT_MS) return false;
  log(`explain: ${payload.file}:${payload.startLine}-${payload.endLine} (${payload.text.length} chars)`);
  postEvent('explain_selection', payload);
  return true;
}

// ---------------------------------------------------------------- lifecycle

async function activate(context) {
  const subs = context.subscriptions;
  try {
    S.log = vscode.window.createOutputChannel('Miyagi Companion');
    subs.push(S.log);
  } catch (_) { /* optional */ }
  if (vscode.window.state && vscode.window.state.focused) S.lastFocusedAt = Date.now();

  S.proposedEmitter = new vscode.EventEmitter();
  subs.push(vscode.workspace.registerTextDocumentContentProvider(PROPOSED_SCHEME, {
    onDidChange: S.proposedEmitter.event,
    provideTextDocumentContent: (uri) => S.proposed.get(uri.toString()) || '',
  }));

  const w = vscode.window;
  const ws = vscode.workspace;
  subs.push(w.onDidChangeActiveTextEditor(onEditor));
  subs.push(w.onDidChangeVisibleTextEditors((eds) => { if (S.highlight) for (const ed of eds) paintHighlight(ed); }));
  subs.push(w.onDidChangeWindowState(onWindowState));
  if (typeof w.onDidChangeTextEditorVisibleRanges === 'function') subs.push(w.onDidChangeTextEditorVisibleRanges(onVisible));
  subs.push(ws.onDidSaveTextDocument(onSave));
  subs.push(ws.onDidChangeTextDocument(onDocChange));
  if (typeof w.onDidOpenTerminal === 'function') subs.push(w.onDidOpenTerminal((t) => postEvent('terminal', { opened: t.name })));
  if (typeof w.onDidCloseTerminal === 'function') subs.push(w.onDidCloseTerminal((t) => postEvent('terminal', { closed: t.name })));
  if (hasShellApi()) { // VS Code 1.93+: exit codes and output of every command, the learner's included
    subs.push(w.onDidStartTerminalShellExecution(onCommandStart));
    subs.push(w.onDidEndTerminalShellExecution(onCommandEnd));
  }
  subs.push(vscode.commands.registerCommand('miyagi.companion.explainSelection', explainSelection));
  subs.push(vscode.commands.registerCommand('miyagi.companion.refreshPython', () => pythonRefresh({}))); // E20 (also POST /python/refresh)
  subs.push(vscode.commands.registerCommand('miyagi.companion.status', () => { // no toast; GET /health instead
    log(S.port ? `status: listening on 127.0.0.1:${S.port}` : 'status: no free port (8791-8799)');
    return S.port;
  }));

  const base = int(cfg('port', DEFAULT_PORT));
  S.server = await listen(base === null ? DEFAULT_PORT : base);
  S.port = S.server ? S.server.address().port : null;
  log(S.port ? `listening on 127.0.0.1:${S.port}` : 'not listening');
  subs.push({ dispose: () => deactivate() });
  if (S.port) postEvent('ready', { version: VERSION, ...editorPayload() });
  return { port: S.port, state: snapshot };
}

function deactivate() {
  const srv = S.server;
  S.server = null;
  if (srv) {
    try { srv.close(); } catch (_) { /* already closed */ }
    if (typeof srv.closeAllConnections === 'function') srv.closeAllConnections();
  }
  if (S.decorations) {
    for (const d of Object.values(S.decorations)) {
      try { d.dispose(); } catch (_) { /* gone */ }
    }
  }
  clearTimeout(S.editorTimer);
  clearTimeout(S.visibleTimer);
  Object.assign(S, { visibleKey: null, port: null, decorations: null, highlight: null, lastCommand: null, running: new Map(),
    proposed: new Map(), dirty: new Map(), lastFocusedAt: 0 });
}

module.exports = { activate, deactivate, _internal: { S, cleanOutput, tailLines, editToReplace, refuse, selectionPayload, notebookCellForLine,
  engineTarget, liveTokens } };

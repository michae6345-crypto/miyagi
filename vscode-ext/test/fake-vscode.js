'use strict';
// A small in-memory stand-in for the `vscode` module: just what extension.js touches. Documents are
// backed by real files in a temp folder so save() and createFile() can be checked on disk.

const fs = require('fs');
const path = require('path');
const Module = require('module');

class EventEmitter {
  constructor() { this.listeners = new Set(); this.event = (fn) => { this.listeners.add(fn); return { dispose: () => this.listeners.delete(fn) }; }; }
  fire(v) { for (const fn of [...this.listeners]) fn(v); }
  dispose() { this.listeners.clear(); }
}

class Uri {
  constructor(scheme, p, query) { this.scheme = scheme; this.path = p; this.query = query || ''; this.fsPath = p; }
  static file(p) { return new Uri('file', path.resolve(p)); }
  static from({ scheme, path: p, query }) { return new Uri(scheme, p, query); }
  static parse(s) { return s.startsWith('file://') ? Uri.file(decodeURIComponent(s.slice(7))) : new Uri(s.split(':')[0], s.slice(s.indexOf(':') + 1)); }
  toString() { return this.scheme === 'file' ? `file://${this.path}` : `${this.scheme}:${this.path}${this.query ? `?${this.query}` : ''}`; }
}

class Position {
  constructor(line, character) { this.line = line; this.character = character; }
}

class Range {
  constructor(a, b, c, d) {
    if (a instanceof Position) { this.start = a; this.end = b; } else { this.start = new Position(a, b); this.end = new Position(c, d); }
  }
  get isEmpty() { return this.start.line === this.end.line && this.start.character === this.end.character; }
}

class Selection extends Range {
  constructor(a, b, c, d) { super(a, b, c, d); this.active = this.end; }
}

class FakeDocument {
  constructor(uri, text, languageId) {
    this.uri = uri; this.text = text; this.languageId = languageId; this.isDirty = false; this.version = 1;
  }
  get lines() { return this.text.split('\n'); }
  get lineCount() { return this.lines.length; }
  lineAt(i) {
    const t = this.lines[i];
    return { text: t, range: new Range(i, 0, i, t.length), lineNumber: i };
  }
  getText() { return this.text; }
  offsetAt(p) {
    const lines = this.lines;
    let off = 0;
    for (let i = 0; i < Math.min(p.line, lines.length); i++) off += lines[i].length + 1;
    const line = lines[Math.min(p.line, lines.length - 1)] || '';
    return Math.min(off + Math.min(p.character, line.length), this.text.length);
  }
  validateRange(r) {
    const clamp = (p) => {
      const line = Math.min(Math.max(p.line, 0), this.lineCount - 1);
      return new Position(line, Math.min(Math.max(p.character, 0), this.lines[line].length));
    };
    return new Range(clamp(r.start), clamp(r.end));
  }
  async save() {
    fs.writeFileSync(this.uri.fsPath, this.text);
    this.isDirty = false;
    this._fake.ws.save.fire(this);
    return true;
  }
}

class WorkspaceEdit {
  constructor() { this.ops = []; }
  replace(uri, range, text) { this.ops.push({ kind: 'replace', uri, range, text }); }
  insert(uri, pos, text) { this.ops.push({ kind: 'replace', uri, range: new Range(pos, pos), text }); }
  createFile(uri, opts) { this.ops.push({ kind: 'create', uri, opts }); }
}

const LANG = { '.py': 'python', '.js': 'javascript', '.md': 'markdown', '.txt': 'plaintext' };

class NotebookRange {
  constructor(start, end) { this.start = start; this.end = end; }
}

// notebooks: true -> 'vscode.openWith' (jupyter-notebook) opens a notebook editor; false -> it throws (no ipynb support).
function createFakeVscode({ folders = [], config = {}, shellApi = true, openDelayMs = 0, notebooks = true } = {}) {
  const calls = { commands: [], shown: [], reveals: [], info: [], nbReveals: [] };
  const notebookDocs = [];
  const notebookEditors = [];
  const docs = [];
  const editors = [];
  const terminals = [];
  const providers = {};
  const registered = {};
  const decorationTypes = [];
  const ev = {
    activeEditor: new EventEmitter(), visibleEditors: new EventEmitter(), windowState: new EventEmitter(),
    visibleRanges: new EventEmitter(),
    openTerminal: new EventEmitter(), closeTerminal: new EventEmitter(),
    shellStart: new EventEmitter(), shellEnd: new EventEmitter(),
  };
  const ws = { save: new EventEmitter(), change: new EventEmitter() };
  const fake = { ws };

  function docFor(fsPath) { return docs.find((d) => d.uri.scheme === 'file' && d.uri.fsPath === path.resolve(fsPath)); }

  const vscode = {
    version: '1.146.0',
    EventEmitter, Uri, Position, Range, Selection, WorkspaceEdit, NotebookRange,
    TextEditorRevealType: { Default: 0, InCenter: 2 },
    NotebookEditorRevealType: { Default: 0, InCenter: 1, InCenterIfOutsideViewport: 2 },
    OverviewRulerLane: { Full: 7 },
    window: {
      activeTextEditor: undefined,
      visibleTextEditors: editors,
      activeNotebookEditor: undefined,
      visibleNotebookEditors: notebookEditors,
      terminals,
      activeTerminal: undefined,
      state: { focused: true },
      tabGroups: { all: [] },
      onDidChangeActiveTextEditor: ev.activeEditor.event,
      onDidChangeVisibleTextEditors: ev.visibleEditors.event,
      onDidChangeWindowState: ev.windowState.event,
      onDidChangeTextEditorVisibleRanges: ev.visibleRanges.event,
      onDidOpenTerminal: ev.openTerminal.event,
      onDidCloseTerminal: ev.closeTerminal.event,
      createOutputChannel: () => ({ lines: [], appendLine(l) { this.lines.push(l); }, dispose() {} }),
      showInformationMessage: (m) => { calls.info.push(m); },
      createTextEditorDecorationType: (opts) => {
        const t = { id: decorationTypes.length, opts, disposed: false, dispose() { this.disposed = true; } };
        decorationTypes.push(t);
        return t;
      },
      async showTextDocument(doc, opts = {}) {
        calls.shown.push({ file: doc.uri.fsPath, opts });
        let ed = editors.find((e) => e.document === doc);
        if (!ed) {
          ed = {
            document: doc,
            viewColumn: opts.viewColumn || 1,
            selection: new Selection(0, 0, 0, 0),
            visibleRanges: [new Range(0, 0, Math.min(doc.lineCount, 40) - 1, 0)],
            decorations: new Map(),
            setDecorations(type, ranges) { this.decorations.set(type.id, ranges); },
            revealRange(range, how) { calls.reveals.push({ file: doc.uri.fsPath, startLine: range.start.line, endLine: range.end.line, how }); },
          };
          editors.push(ed);
          ev.visibleEditors.fire(editors);
        }
        if (opts.selection) ed.selection = new Selection(opts.selection.start, opts.selection.end);
        vscode.window.activeTextEditor = ed;
        ev.activeEditor.fire(ed);
        return ed;
      },
      createTerminal(opts) {
        const t = {
          name: opts.name, creationOptions: opts, exitStatus: undefined, shellIntegration: undefined,
          shown: [], sent: [],
          show(preserveFocus) { this.shown.push(!!preserveFocus); vscode.window.activeTerminal = this; },
          sendText(text, addNewLine) { this.sent.push({ text, addNewLine }); },
        };
        terminals.push(t);
        ev.openTerminal.fire(t);
        return t;
      },
    },
    workspace: {
      name: folders.length ? path.basename(folders[0]) : undefined,
      workspaceFolders: folders.map((f, i) => ({ uri: Uri.file(f), name: path.basename(f), index: i })),
      textDocuments: docs,
      notebookDocuments: notebookDocs,
      onDidSaveTextDocument: ws.save.event,
      onDidChangeTextDocument: ws.change.event,
      getConfiguration: () => ({ get: (k) => config[k] }),
      asRelativePath: (uri) => {
        const root = folders[0];
        return root && uri.fsPath.startsWith(root + path.sep) ? uri.fsPath.slice(root.length + 1) : uri.fsPath;
      },
      registerTextDocumentContentProvider(scheme, provider) { providers[scheme] = provider; return { dispose() {} }; },
      async openTextDocument(uri) {
        if (openDelayMs) await new Promise((r) => setTimeout(r, openDelayMs));
        const have = docFor(uri.fsPath);
        if (have) return have;
        if (!fs.existsSync(uri.fsPath)) throw new Error(`cannot open ${uri.fsPath}`);
        const doc = new FakeDocument(uri, fs.readFileSync(uri.fsPath, 'utf8'), LANG[path.extname(uri.fsPath)] || 'plaintext');
        doc._fake = fake;
        docs.push(doc);
        return doc;
      },
      async applyEdit(we) {
        for (const op of we.ops.filter((o) => o.kind === 'create')) {
          if (!fs.existsSync(op.uri.fsPath)) fs.writeFileSync(op.uri.fsPath, '');
        }
        const byDoc = new Map();
        for (const op of we.ops.filter((o) => o.kind === 'replace')) {
          const doc = await vscode.workspace.openTextDocument(op.uri);
          if (!byDoc.has(doc)) byDoc.set(doc, []);
          byDoc.get(doc).push(op);
        }
        for (const [doc, ops] of byDoc) {
          const spans = ops.map((o) => ({ s: doc.offsetAt(o.range.start), e: doc.offsetAt(o.range.end), text: o.text }))
            .sort((a, b) => b.s - a.s);
          for (let i = 1; i < spans.length; i++) if (spans[i].e > spans[i - 1].s) return false; // overlap
          for (const sp of spans) doc.text = doc.text.slice(0, sp.s) + sp.text + doc.text.slice(sp.e);
          doc.isDirty = true;
          doc.version += 1;
          ws.change.fire({ document: doc, contentChanges: ops });
        }
        return true;
      },
    },
    commands: {
      async executeCommand(id, ...args) {
        calls.commands.push({ id, args });
        if (id !== 'vscode.openWith' || args[1] !== 'jupyter-notebook') return undefined;
        if (!notebooks) throw new Error("There is no editor for 'jupyter-notebook'");
        const uri = args[0];
        let ne = notebookEditors.find((e) => e.notebook.uri.fsPath === uri.fsPath);
        if (!ne) {
          let nb = notebookDocs.find((d) => d.uri.fsPath === uri.fsPath);
          if (!nb) {
            const cells = JSON.parse(fs.readFileSync(uri.fsPath, 'utf8')).cells || [];
            nb = { uri, notebookType: 'jupyter-notebook', cellCount: cells.length, isDirty: false, saves: 0,
              async save() { this.saves += 1; this.isDirty = false; return true; } };
            notebookDocs.push(nb);
          }
          ne = { notebook: nb, viewColumn: (args[2] && args[2].viewColumn) || 1, selections: [new NotebookRange(0, 1)],
            revealRange(r, how) { calls.nbReveals.push({ file: uri.fsPath, start: r.start, end: r.end, how }); } };
          notebookEditors.push(ne);
        }
        vscode.window.activeNotebookEditor = ne;
        return undefined;
      },
      registerCommand(id, fn) { registered[id] = fn; return { dispose() {} }; },
    },
  };
  if (shellApi) {
    vscode.window.onDidStartTerminalShellExecution = ev.shellStart.event;
    vscode.window.onDidEndTerminalShellExecution = ev.shellEnd.event;
  }

  const ctl = {
    calls, docs, editors, notebookDocs, notebookEditors, terminals, providers, registered, decorationTypes, ev, ws,
    // Simulate the learner typing in a buffer (dirty, not saved).
    type(doc, text) {
      doc.text = text; doc.isDirty = true; doc.version += 1;
      ws.change.fire({ document: doc, contentChanges: [] });
    },
    // A shell-integration command: start, stream `chunks`, end with `exitCode`.
    startCommand(terminal, commandLine, chunks, cwd) {
      let release;
      const done = new Promise((r) => { release = r; });
      const execution = {
        commandLine: { value: commandLine, isTrusted: true, confidence: 2 },
        cwd: cwd ? Uri.file(cwd) : undefined,
        async *read() { for (const c of chunks) { await new Promise((r) => setImmediate(r)); yield c; } await done; },
      };
      ev.shellStart.fire({ terminal, execution, shellIntegration: terminal.shellIntegration });
      return {
        execution,
        end(exitCode) { release(); ev.shellEnd.fire({ terminal, execution, shellIntegration: terminal.shellIntegration, exitCode }); },
      };
    },
  };
  return { vscode, ctl };
}

// require('../extension.js') with `vscode` resolved to the given fake (fresh module state each time).
function loadExtension(vscode) {
  const extPath = require.resolve('../extension.js');
  delete require.cache[extPath];
  const orig = Module._load;
  Module._load = function load(request, parent, isMain) {
    if (request === 'vscode') return vscode;
    return orig.call(this, request, parent, isMain);
  };
  try {
    return require(extPath);
  } finally {
    Module._load = orig;
  }
}

module.exports = { createFakeVscode, loadExtension, Uri, Position, Range };

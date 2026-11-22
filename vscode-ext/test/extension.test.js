'use strict';
// Offline tests: extension.js runs against a stubbed `vscode` module; a fake engine collects the events.
// Run: cd vscode-ext && npm test   (node --test test/*.test.js)

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const http = require('http');
const { createFakeVscode, loadExtension } = require('./fake-vscode');

// Engine tokens (../extension.js liveTokens) come from a temp folder, never the live engine's ~/.miyagi/engine-tokens.
const TOKEN_DIR = fs.mkdtempSync(path.join(os.tmpdir(), 'miyagi-tokens-'));
process.env.MIYAGI_ENGINE_TOKEN_DIR = TOKEN_DIR;

const CALC = '"""A simple Python calculator."""\n\n# Step 1: Start building your calculator here\n';

function request(port, method, p, body, headers = {}) {
  return new Promise((resolve, reject) => {
    const data = body === undefined ? '' : (typeof body === 'string' ? body : JSON.stringify(body));
    const h = { host: `127.0.0.1:${port}`, ...headers };
    if (method === 'POST' && !('content-type' in h)) h['content-type'] = 'application/json';
    if (data) h['content-length'] = Buffer.byteLength(data);
    for (const k of Object.keys(h)) if (h[k] === null) delete h[k];
    const req = http.request({ host: '127.0.0.1', port, method, path: p, headers: h, setHost: false }, (res) => {
      let raw = '';
      res.on('data', (c) => { raw += c; });
      res.on('end', () => resolve({ status: res.statusCode, body: raw ? JSON.parse(raw) : null }));
    });
    req.on('error', reject);
    req.end(data);
  });
}

async function fakeEngine() {
  const events = [];
  const srv = http.createServer((req, res) => {
    let raw = '';
    req.on('data', (c) => { raw += c; });
    req.on('end', () => {
      if (req.url === '/vscode/event') events.push({ ...JSON.parse(raw), _token: req.headers['x-miyagi-token'] || null });
      res.end('{"ok":true}');
    });
  });
  await new Promise((r) => srv.listen(0, '127.0.0.1', r));
  const port = srv.address().port;
  return { events, port, url: `http://127.0.0.1:${port}`, close: () => new Promise((r) => srv.close(r)) };
}

async function waitFor(fn, ms = 1500) {
  const until = Date.now() + ms;
  for (;;) {
    const v = fn();
    if (v) return v;
    if (Date.now() > until) throw new Error('timed out waiting');
    await new Promise((r) => setTimeout(r, 10));
  }
}

async function setup(t, opts = {}) {
  const dir = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'miyagi-ext-')));
  fs.writeFileSync(path.join(dir, 'calculator.py'), CALC);
  const engine = await fakeEngine();
  const { vscode, ctl } = createFakeVscode({ folders: [dir], config: { port: 0, engineUrl: engine.url, ...(opts.config || {}) }, ...opts.fake });
  const ext = loadExtension(vscode);
  const context = { subscriptions: [] };
  const api = await ext.activate(context);
  t.after(async () => {
    for (const d of context.subscriptions) d.dispose();
    ext.deactivate();
    await engine.close();
    fs.rmSync(dir, { recursive: true, force: true });
  });
  const port = api.port;
  return { ext, vscode, ctl, dir, engine, port, file: path.join(dir, 'calculator.py'),
    req: (method, p, body, headers) => request(port, method, p, body, headers) };
}

test('binds 127.0.0.1 and serves /state with no editor open', async (t) => {
  const s = await setup(t);
  assert.ok(s.port > 0);
  const r = await s.req('GET', '/state');
  assert.equal(r.status, 200);
  const st = r.body;
  assert.deepEqual(st.folders, [s.dir]);
  assert.equal(st.file, null);
  assert.equal(st.dirty, false);
  assert.equal(st.cursor, null);
  assert.deepEqual(st.visibleRanges, []);
  assert.equal(st.terminalOpen, false);
  assert.equal(st.lastCommand, null);
  assert.equal(st.windowFocused, true);
  assert.equal(st.port, s.port);
  assert.equal(st.shellIntegrationApi, true);
  const ready = await waitFor(() => s.engine.events.find((e) => e.type === 'ready'));
  assert.equal(ready.port, s.port);
});

test('takes the next port when the first is busy (one server per VS Code window)', async (t) => {
  const blocker = http.createServer();
  await new Promise((r) => blocker.listen(0, '127.0.0.1', r));
  t.after(() => new Promise((r) => blocker.close(r)));
  const busy = blocker.address().port;
  const s = await setup(t, { config: { port: busy } });
  assert.ok(s.port > busy && s.port < busy + 9, `${s.port} after ${busy}`);
});

test('POST /open reveals the line in this window and /state reports it exactly', async (t) => {
  const s = await setup(t);
  const r = await s.req('POST', '/open', { file: 'calculator.py', line: 3 });
  assert.equal(r.status, 200, JSON.stringify(r.body));
  assert.equal(r.body.file, s.file);
  assert.equal(r.body.line, 3);
  assert.equal(s.ctl.calls.shown.length, 1);
  assert.ok(!s.ctl.calls.commands.some((c) => /openFolder|newWindow/.test(c.id)), 'never a new window');
  assert.deepEqual(s.ctl.calls.reveals.at(-1), { file: s.file, startLine: 2, endLine: 2, how: 2 });
  const st = (await s.req('GET', '/state')).body;
  assert.equal(st.file, s.file);
  assert.equal(st.relPath, 'calculator.py');
  assert.equal(st.languageId, 'python');
  assert.deepEqual(st.cursor, { line: 3, column: 1 });
  assert.equal(st.visibleRanges[0].startLine, 1);
  // the editor-change event reaches the engine (debounced)
  const ev = await waitFor(() => s.engine.events.find((e) => e.type === 'editor' && e.file === s.file));
  assert.equal(ev.languageId, 'python');
  // missing file -> 404, nothing opened
  const miss = await s.req('POST', '/open', { file: 'nope.py' });
  assert.equal(miss.status, 404);
  assert.equal(miss.body.error, 'not_found');
});

test('POST /highlight draws nothing by default: Miyagi\'s overlay is the only UI (it still reveals and records)', async (t) => {
  const s = await setup(t);
  fs.writeFileSync(s.file, 'a\nb\nc\nd\ne\n');
  const r = await s.req('POST', '/highlight', { file: s.file, startLine: 2, endLine: 4 });
  assert.equal(r.status, 200, JSON.stringify(r.body));
  assert.deepEqual(r.body, { ok: true, file: s.file, startLine: 2, endLine: 4 });
  assert.equal(s.ctl.decorationTypes.length, 0, 'no decoration types, so no box and no overview-ruler mark');
  assert.ok(s.ctl.editors.every((ed) => ed.decorations.size === 0));
  assert.deepEqual(s.ctl.calls.reveals.at(-1), { file: s.file, startLine: 1, endLine: 3, how: 2 });
  assert.deepEqual((await s.req('GET', '/state')).body.highlight, { file: s.file, startLine: 2, endLine: 4 });
  assert.deepEqual((await s.req('POST', '/highlight', { clear: true })).body, { ok: true, cleared: true });
  assert.equal(s.ctl.decorationTypes.length, 0);
});

test('POST /highlight with miyagi.editorUi draws one white box around the block and {clear:true} removes it', async (t) => {
  const s = await setup(t, { config: { editorUi: true } });
  fs.writeFileSync(s.file, 'a\nb\nc\nd\ne\n');
  const r = await s.req('POST', '/highlight', { file: s.file, startLine: 2, endLine: 4 });
  assert.equal(r.status, 200, JSON.stringify(r.body));
  assert.deepEqual(r.body, { ok: true, file: s.file, startLine: 2, endLine: 4 });
  const types = s.ctl.decorationTypes;
  assert.equal(types.length, 4);
  for (const ty of types) {
    assert.equal(ty.opts.borderColor, '#ffffff');
    assert.equal(ty.opts.isWholeLine, true);
    assert.match(ty.opts.backgroundColor, /rgba\(255,255,255,0\.0\d\)/);
  }
  assert.equal(types[0].opts.borderWidth, '2px'); // single-line style
  const ed = s.ctl.editors[0];
  const lines = (id) => (ed.decorations.get(id) || []).map((rg) => rg.start.line + 1);
  assert.deepEqual(lines(1), [2]); // top
  assert.deepEqual(lines(2), [3]); // middle
  assert.deepEqual(lines(3), [4]); // bottom
  assert.deepEqual(lines(0), []);
  assert.deepEqual(s.ctl.calls.reveals.at(-1), { file: s.file, startLine: 1, endLine: 3, how: 2 }); // centered
  assert.deepEqual((await s.req('GET', '/state')).body.highlight, { file: s.file, startLine: 2, endLine: 4 });

  await s.req('POST', '/highlight', { file: s.file, startLine: 5 });
  assert.deepEqual(lines(0), [5]);
  assert.deepEqual(lines(1), []);

  const c = await s.req('POST', '/highlight', { clear: true });
  assert.deepEqual(c.body, { ok: true, cleared: true });
  for (const id of [0, 1, 2, 3]) assert.deepEqual(lines(id), []);
  assert.equal((await s.req('GET', '/state')).body.highlight, null);
});

test('terminal: /terminal shows one, /terminal/run reuses the "Miyagi" terminal and sends the command', async (t) => {
  const s = await setup(t);
  const shown = await s.req('POST', '/terminal', { show: true });
  assert.deepEqual(shown.body, { ok: true, shown: true, terminal: 'Miyagi', created: true });
  assert.equal(s.ctl.terminals[0].creationOptions.cwd, s.dir);

  const r1 = await s.req('POST', '/terminal/run', { cmd: 'python calculator.py' });
  assert.equal(r1.body.created, false);
  assert.equal(r1.body.sent, 'python calculator.py');
  assert.equal(r1.body.reportsExitCode, true);
  const r2 = await s.req('POST', '/terminal/run', { cmd: 'ls', cwd: '/tmp/other lesson' });
  assert.equal(r2.body.sent, "cd '/tmp/other lesson' && ls");
  assert.equal(s.ctl.terminals.length, 1, 'reused, not a second terminal');
  assert.deepEqual(s.ctl.terminals[0].sent.map((x) => x.text), ['python calculator.py', "cd '/tmp/other lesson' && ls"]);
  assert.ok(s.ctl.terminals[0].sent.every((x) => x.addNewLine === true));
  assert.equal((await s.req('GET', '/state')).body.terminalOpen, true);

  const bad = await s.req('POST', '/terminal/run', {});
  assert.equal(bad.status, 400);

  const hide = await s.req('POST', '/terminal', { show: false });
  assert.equal(hide.body.shown, false);
  assert.equal(s.ctl.calls.commands.at(-1).id, 'workbench.action.closePanel');
});

test('shell integration: exit code + clean output tail of any command (the learner\'s too)', async (t) => {
  const s = await setup(t);
  await s.req('POST', '/terminal', { show: true });
  const term = s.ctl.terminals[0];
  const run = s.ctl.startCommand(term, 'python calculator.py',
    ['\x1b[32mstarting\x1b[0m\r\n', 'progress 10%\rprogress 100%\r\n', 'Traceback (most recent call last):\r\n',
      "NameError: name 'add' is not defined\r\n"], s.dir);
  await waitFor(() => s.engine.events.find((e) => e.type === 'command_start'));
  const mid = (await s.req('GET', '/state')).body.lastCommand;
  assert.equal(mid.running, true);
  assert.equal(mid.exitCode, null);
  await new Promise((r) => setTimeout(r, 30));
  run.end(1);
  const ev = await waitFor(() => s.engine.events.find((e) => e.type === 'command_end'));
  assert.equal(ev.command.commandLine, 'python calculator.py');
  assert.equal(ev.command.exitCode, 1);
  assert.equal(ev.command.cwd, s.dir);
  assert.deepEqual(ev.command.outputTail, ['starting', 'progress 100%', 'Traceback (most recent call last):',
    "NameError: name 'add' is not defined"]);
  const st = (await s.req('GET', '/state')).body.lastCommand;
  assert.equal(st.exitCode, 1);
  assert.equal(st.running, false);
});

test('POST /apply writes over an unsaved buffer and saves; edits keep indentation; new files are created', async (t) => {
  const s = await setup(t);
  await s.req('POST', '/open', { file: s.file });
  const doc = s.ctl.docs[0];
  s.ctl.type(doc, 'def add(a, b):\n    return a - b\n'); // learner typed, did not save
  assert.equal((await s.req('GET', '/state')).body.dirty, true);
  const dirtyEv = await waitFor(() => s.engine.events.find((e) => e.type === 'dirty' && e.dirty === true));
  assert.equal(dirtyEv.file, s.file);
  // /text sees the unsaved buffer, which the file on disk doesn't have
  const txt = (await s.req('GET', `/text?file=${encodeURIComponent(s.file)}`)).body;
  assert.equal(txt.text, 'def add(a, b):\n    return a - b\n');
  assert.equal(txt.dirty, true);

  const r = await s.req('POST', '/apply', { file: s.file, edits: [{ find: 'return a - b', replace: 'return a + b' }] });
  assert.equal(r.status, 200, JSON.stringify(r.body));
  assert.equal(r.body.saved, true);
  assert.equal(r.body.dirty, false);
  assert.equal(fs.readFileSync(s.file, 'utf8'), 'def add(a, b):\n    return a + b\n');
  await waitFor(() => s.engine.events.find((e) => e.type === 'save' && e.file === s.file));

  await s.req('POST', '/apply', { file: s.file, edits: [{ startLine: 3, endLine: 2, text: '\nprint(add(2, 3))' }] });
  assert.equal(fs.readFileSync(s.file, 'utf8'), 'def add(a, b):\n    return a + b\n\nprint(add(2, 3))\n');
  await s.req('POST', '/apply', { file: s.file, edits: [{ startLine: 4, startColumn: 11, endLine: 4, endColumn: 15, text: '7, 8' }] });
  assert.equal(fs.readFileSync(s.file, 'utf8'), 'def add(a, b):\n    return a + b\n\nprint(add(7, 8))\n');
  await s.req('POST', '/apply', { file: s.file, newText: 'x = 1\n', save: false });
  assert.equal(doc.text, 'x = 1\n');
  assert.equal(doc.isDirty, true);
  assert.equal(fs.readFileSync(s.file, 'utf8'), 'def add(a, b):\n    return a + b\n\nprint(add(7, 8))\n');

  const miss = await s.req('POST', '/apply', { file: s.file, edits: [{ find: 'not there', replace: 'x' }] });
  assert.equal(miss.status, 409);
  assert.equal(miss.body.error, 'find_not_found');

  const created = await s.req('POST', '/apply', { file: 'ops.py', newText: 'def sub(a, b):\n    return a - b\n' });
  assert.equal(created.body.created, true);
  assert.equal(fs.readFileSync(path.join(s.dir, 'ops.py'), 'utf8'), 'def sub(a, b):\n    return a - b\n');
});

test('POST /diff opens no diff tab by default (409 editor_ui_off)', async (t) => {
  const s = await setup(t);
  const r = await s.req('POST', '/diff', { file: s.file, newText: 'x = 1\n' });
  assert.equal(r.status, 409);
  assert.deepEqual(r.body, { ok: false, error: 'editor_ui_off' });
  assert.equal(s.ctl.calls.commands.length, 0, 'nothing opened');
});

test('POST /diff with miyagi.editorUi opens vscode.diff: the file on the left, the proposed text on the right', async (t) => {
  const s = await setup(t, { config: { editorUi: true } });
  const r = await s.req('POST', '/diff', { file: s.file, newText: 'def add(a, b):\n    return a + b\n' });
  assert.equal(r.status, 200, JSON.stringify(r.body));
  const call = s.ctl.calls.commands.find((c) => c.id === 'vscode.diff');
  assert.ok(call);
  const [left, right, title] = call.args;
  assert.equal(left.fsPath, s.file);
  assert.equal(right.scheme, 'miyagi-proposed');
  assert.match(title, /calculator\.py/);
  assert.equal(s.ctl.providers['miyagi-proposed'].provideTextDocumentContent(right), 'def add(a, b):\n    return a + b\n');
  assert.equal(fs.readFileSync(s.file, 'utf8'), CALC, 'a preview only: the file is untouched');
});

test('refuses browsers and DNS rebinding; requires JSON', async (t) => {
  const s = await setup(t);
  const origin = await s.req('POST', '/terminal/run', { cmd: 'echo pwned' }, { origin: 'https://evil.example' });
  assert.equal(origin.status, 403);
  const site = await s.req('GET', '/state', undefined, { 'sec-fetch-site': 'cross-site' });
  assert.equal(site.status, 403);
  const host = await s.req('GET', '/state', undefined, { host: 'evil.example:8791' });
  assert.equal(host.status, 403);
  const form = await s.req('POST', '/terminal/run', 'cmd=echo', { 'content-type': 'text/plain' });
  assert.equal(form.status, 415);
  assert.equal(s.ctl.terminals.length, 0, 'nothing ran');
  const okLocal = await s.req('GET', '/health', undefined, { host: `localhost:${s.port}` });
  assert.equal(okLocal.status, 200);
  const badJson = await s.req('POST', '/open', '{nope');
  assert.equal(badJson.status, 400);
  assert.equal((await s.req('GET', '/nope')).status, 404);
});

function writeToken(port, token, pid = process.pid) {
  const f = path.join(TOKEN_DIR, `${port}.json`);
  fs.writeFileSync(f, JSON.stringify({ token, pid, port }), { mode: 0o600 });
  return f;
}

test('engine token: required on the API while a live engine wrote one; events to the engine carry it', async (t) => {
  const s = await setup(t);
  const f = writeToken(s.engine.port, 'tok-live-123');
  t.after(() => fs.rmSync(f, { force: true }));
  s.ext._internal.S.tokens = null; // drop the 1 s cache
  assert.equal((await s.req('GET', '/state')).status, 401);
  assert.equal((await s.req('POST', '/terminal/run', { cmd: 'echo pwned' }, { 'x-miyagi-token': 'wrong' })).status, 401);
  assert.equal(s.ctl.terminals.length, 0, 'nothing ran');
  assert.equal((await s.req('GET', '/health')).status, 200, 'liveness stays open');
  assert.equal((await s.req('GET', '/state', undefined, { 'x-miyagi-token': 'tok-live-123' })).status, 200);
  const r = await s.req('POST', '/open', { file: 'calculator.py', line: 1 }, { 'x-miyagi-token': 'tok-live-123' });
  assert.equal(r.status, 200, JSON.stringify(r.body));
  const ev = await waitFor(() => s.engine.events.find((e) => e.type === 'editor' && e._token));
  assert.equal(ev._token, 'tok-live-123');
});

test('engine token: a file whose engine is gone (crash) is ignored, so the API stays open as before', async (t) => {
  const s = await setup(t);
  const f = writeToken(s.engine.port, 'tok-dead', 2 ** 22 + 12345);
  t.after(() => fs.rmSync(f, { force: true }));
  s.ext._internal.S.tokens = null;
  assert.equal((await s.req('GET', '/state')).status, 200);
});

test('events go to an engine on this Mac only (a workspace setting can\'t send them elsewhere)', async (t) => {
  const s = await setup(t);
  const { engineTarget } = s.ext._internal;
  assert.ok(engineTarget(), 'the default 127.0.0.1 engine');
  for (const url of ['http://evil.example:8787', 'https://127.0.0.1:8787', 'http://10.0.0.5:8787', 'not a url']) {
    s.vscode.workspace.getConfiguration = () => ({ get: (k) => (k === 'engineUrl' ? url : undefined) });
    assert.equal(engineTarget(), null, url);
  }
  for (const url of ['http://localhost:8787', 'http://[::1]:8787']) {
    s.vscode.workspace.getConfiguration = () => ({ get: (k) => (k === 'engineUrl' ? url : undefined) });
    assert.ok(engineTarget(), url);
  }
});

test('a slow action answers {pending} within the deadline and reports the result as an event', async (t) => {
  const s = await setup(t, { fake: { openDelayMs: 400 } });
  const t0 = Date.now();
  const r = await s.req('POST', '/open', { file: s.file, line: 2 });
  assert.ok(Date.now() - t0 < 380, `answered in ${Date.now() - t0} ms`);
  assert.equal(r.body.pending, true);
  const done = await waitFor(() => s.engine.events.find((e) => e.type === 'action_done' && e.id === r.body.id));
  assert.equal(done.action, '/open');
  assert.equal(done.result.ok, true);
  assert.equal(done.result.line, 2);
});

test('a scroll or a line-count change of the active editor posts one `visible` event (t7: the type box follows)', async (t) => {
  const s = await setup(t);
  await s.req('POST', '/open', { file: 'calculator.py', line: 3 });
  const ed = s.vscode.window.activeTextEditor;
  assert.ok(ed, 'an active editor');
  ed.visibleRanges = [new s.vscode.Range(7, 0, 34, 0)];
  s.ctl.ev.visibleRanges.fire({ textEditor: ed, visibleRanges: ed.visibleRanges });
  s.ctl.ev.visibleRanges.fire({ textEditor: ed, visibleRanges: ed.visibleRanges }); // debounced: one event
  const ev = await waitFor(() => s.engine.events.find((e) => e.type === 'visible'));
  assert.equal(ev.file, s.file);
  assert.deepEqual(ev.visibleRanges, [{ startLine: 8, endLine: 35 }]);
  assert.equal(ev.lineCount, ed.document.lineCount);
  assert.deepEqual(ev.folders, [s.dir]);
  await new Promise((r) => setTimeout(r, 150));
  s.ctl.ev.visibleRanges.fire({ textEditor: ed, visibleRanges: ed.visibleRanges }); // the same view again: no event
  await new Promise((r) => setTimeout(r, 150));
  assert.equal(s.engine.events.filter((e) => e.type === 'visible').length, 1);
});

test('window focus and dirty flips post events; the status command reports the port without a toast', async (t) => {
  const s = await setup(t);
  s.ctl.ev.windowState.fire({ focused: false });
  s.ctl.ev.windowState.fire({ focused: true });
  await waitFor(() => s.engine.events.filter((e) => e.type === 'focus').length >= 2);
  assert.ok((await s.req('GET', '/state')).body.lastFocusedAt > 0);
  assert.equal(await s.ctl.registered['miyagi.companion.status'](), s.port);
  assert.deepEqual(s.ctl.calls.info, [], 'no notification');
});

test('works without the shell-integration API (VS Code < 1.93): commands still run, no exit code', async (t) => {
  const s = await setup(t, { fake: { shellApi: false } });
  const r = await s.req('POST', '/terminal/run', { cmd: 'python calculator.py' });
  assert.equal(r.body.ok, true);
  assert.equal(r.body.reportsExitCode, false);
  assert.equal((await s.req('GET', '/state')).body.shellIntegrationApi, false);
});

test('cleanOutput strips ANSI/OSC and collapses carriage returns', () => {
  const { vscode } = createFakeVscode();
  const { _internal } = loadExtension(vscode);
  assert.deepEqual(_internal.cleanOutput('\x1b]633;C\x07a\x1b[1mb\x1b[0m\r\nx\ry\n'), ['ab', 'y', '']);
  assert.deepEqual(_internal.tailLines('1\n2\n\n'), ['1', '2']);
});

// t9 V11: mnist.ipynb opened as raw JSON in a text editor. A notebook opens in the notebook editor, the engine's line
// (a line of the .ipynb JSON) selects its cell, and /apply + /save never go through a raw JSON text buffer.
const NB = JSON.stringify({
  cells: [
    { cell_type: 'markdown', metadata: {}, source: ['# MNIST\n'] },
    { cell_type: 'code', execution_count: null, metadata: {}, outputs: [],
      source: ['import tensorflow as tf\n', '(x_train, y_train), (x_test, y_test) = tf.keras.datasets.mnist.load_data()\n'] },
    { cell_type: 'code', execution_count: null, metadata: {}, outputs: [], source: ['print(x_train.shape)\n'] },
  ],
  metadata: {}, nbformat: 4, nbformat_minor: 5,
}, null, 1) + '\n';

function nbLine(text, needle) {
  return text.split('\n').findIndex((l) => l.includes(needle)) + 1;
}

test('POST /open on an .ipynb opens the notebook editor (never raw JSON) and selects the cell for the line', async (t) => {
  const s = await setup(t);
  const nb = path.join(s.dir, 'mnist.ipynb');
  fs.writeFileSync(nb, NB);
  const line = nbLine(NB, 'load_data()');
  const r = await s.req('POST', '/open', { file: nb, line, preserveFocus: true });
  assert.equal(r.status, 200);
  assert.equal(r.body.ok, true);
  assert.equal(r.body.notebook, true);
  assert.equal(r.body.cell, 1);
  const open = s.ctl.calls.commands.find((c) => c.id === 'vscode.openWith');
  assert.equal(open.args[0].fsPath, nb);
  assert.equal(open.args[1], 'jupyter-notebook');
  assert.equal(open.args[2].preserveFocus, true);
  assert.equal(s.ctl.calls.shown.length, 0, 'no text editor');
  assert.equal(s.ctl.docs.length, 0, 'no raw JSON text document either');
  assert.deepEqual(s.ctl.notebookEditors[0].selections.map((x) => [x.start, x.end]), [[1, 2]]);
  assert.deepEqual(s.ctl.calls.nbReveals.map((x) => [x.start, x.end]), [[1, 2]]);
  // No line: just open (no cell moved). A line past the end ("where new code goes"): the last cell.
  const plain = await s.req('POST', '/open', { file: nb });
  assert.equal(plain.body.cell, null);
  assert.equal(s.ctl.calls.nbReveals.length, 1);
  assert.equal((await s.req('POST', '/open', { file: nb, line: 9999 })).body.cell, 2);
  assert.equal(s.ctl.notebookEditors.length, 1, 'reuses the open notebook editor');
});

test('POST /open on an .ipynb without a notebook editor falls back to vscode.open', async (t) => {
  const s = await setup(t, { fake: { notebooks: false } });
  const nb = path.join(s.dir, 'mnist.ipynb');
  fs.writeFileSync(nb, NB);
  const r = await s.req('POST', '/open', { file: nb, line: 5 });
  assert.equal(r.body.ok, true);
  assert.equal(r.body.notebook, false);
  assert.deepEqual(s.ctl.calls.commands.map((c) => c.id), ['vscode.openWith', 'vscode.open']);
  assert.equal(s.ctl.calls.shown.length, 0);
});

test('notebookCellForLine maps a line of the .ipynb JSON to its cell', () => {
  const { vscode } = createFakeVscode();
  const { _internal } = loadExtension(vscode);
  const f = _internal.notebookCellForLine;
  assert.equal(f(NB, nbLine(NB, '# MNIST')), 0);
  assert.equal(f(NB, nbLine(NB, 'load_data()')), 1);
  assert.equal(f(NB, nbLine(NB, 'print(x_train')), 2);
  assert.equal(f(NB, nbLine(NB, '"outputs"')), 1, 'a non-source line: the cell around it');
  assert.equal(f(NB, 1), null, 'before the first cell');
  assert.equal(f(NB, 10000), 2);
  assert.equal(f('not json', 3), null);
});

test('POST /apply refuses an .ipynb (409); POST /save saves the open notebook, not a JSON text buffer', async (t) => {
  const s = await setup(t);
  const nb = path.join(s.dir, 'mnist.ipynb');
  fs.writeFileSync(nb, NB);
  const a = await s.req('POST', '/apply', { file: nb, newText: '{}' });
  assert.equal(a.status, 409);
  assert.equal(a.body.error, 'notebook_unsupported');
  assert.equal(fs.readFileSync(nb, 'utf8'), NB);
  assert.equal(s.ctl.docs.length, 0);
  await s.req('POST', '/open', { file: nb });
  await s.req('GET', `/text?file=${encodeURIComponent(nb)}`); // the engine's buffer_text: a hidden raw JSON model
  const doc = s.ctl.notebookDocs[0];
  doc.isDirty = true;
  const r = await s.req('POST', '/save', { file: nb });
  assert.equal(r.body.ok, true);
  assert.equal(r.body.notebook, true);
  assert.equal(r.body.saved, true);
  assert.equal(r.body.wasDirty, true);
  assert.equal(doc.saves, 1);
  assert.equal(fs.readFileSync(nb, 'utf8'), NB, 'the JSON text model was not written');
  const again = await s.req('POST', '/save', { file: nb });
  assert.equal(again.body.saved, false);
  assert.equal(doc.saves, 1, 'a clean notebook is left alone');
});

test('engineUrl and port are machine settings, ignored in a workspace and in Restricted Mode (A03)', () => {
  const pkg = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'package.json'), 'utf8'));
  const props = pkg.contributes.configuration.properties;
  assert.equal(props['miyagi.engineUrl'].scope, 'machine', 'a cloned repo\'s .vscode/settings.json must not repoint the engine');
  assert.equal(props['miyagi.port'].scope, 'machine');
  assert.deepEqual(pkg.capabilities.untrustedWorkspaces.restrictedConfigurations.sort(), ['miyagi.engineUrl', 'miyagi.port']);
});

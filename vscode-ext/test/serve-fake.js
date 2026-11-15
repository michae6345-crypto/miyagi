'use strict';
// For the engine's cross-language test (server/workspace/tests/test_vscode_ext.py): runs the real extension.js
// against the fake `vscode` module in a folder, prints {"port", "dir"} on one line, and stops when stdin closes.
// Commands sent to a terminal "run" at once: output "ran: <cmd>", exit code 0 (or 3 when the command has "fail").
//
//   node vscode-ext/test/serve-fake.js <folder> [engineUrl]

const path = require('path');
const { createFakeVscode, loadExtension } = require('./fake-vscode');

async function main() {
  const dir = path.resolve(process.argv[2] || process.cwd());
  const engineUrl = process.argv[3] || 'http://127.0.0.1:9';
  const { vscode, ctl } = createFakeVscode({ folders: [dir], config: { port: 0, engineUrl } });
  const create = vscode.window.createTerminal;
  vscode.window.createTerminal = (opts) => {
    const t = create(opts);
    const send = t.sendText.bind(t);
    t.sendText = (text, addNewLine) => {
      send(text, addNewLine);
      const run = ctl.startCommand(t, text, [`ran: ${text}\r\n`], dir);
      setTimeout(() => run.end(/fail/.test(text) ? 3 : 0), 20);
    };
    return t;
  };
  const ext = loadExtension(vscode);
  const context = { subscriptions: [] };
  const api = await ext.activate(context);
  process.stdout.write(`${JSON.stringify({ port: api.port, dir })}\n`);
  process.stdin.resume();
  process.stdin.on('end', () => {
    for (const d of context.subscriptions) d.dispose();
    ext.deactivate();
    process.exit(0);
  });
}

main().catch((err) => {
  process.stderr.write(`${(err && err.stack) || err}\n`);
  process.exit(1);
});

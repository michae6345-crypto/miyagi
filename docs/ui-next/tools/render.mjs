// Headless Chrome over CDP: PNG screenshots and a PDF.
// usage: node render.mjs <outdir> <w> <h> <dpr> name=url [name=url ...]      (name ending in .pdf prints a PDF)
import { spawn } from 'node:child_process';
import { writeFileSync, mkdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
const [out, W, H, DPR, ...jobs] = process.argv.slice(2);
mkdirSync(out, { recursive: true });
const CH = 'C:/Program Files/Google/Chrome/Application/chrome.exe', PORT = 9347;
const ch = spawn(CH, ['--headless=new', '--hide-scrollbars', '--allow-file-access-from-files', `--remote-debugging-port=${PORT}`,
  `--user-data-dir=${tmpdir()}/skills-mock-chrome`, `--window-size=${W},${H}`, 'about:blank'], { stdio: 'ignore' });
const sleep = ms => new Promise(r => setTimeout(r, ms));
let tgt;
for (let i = 0; i < 60 && !tgt; i++) { await sleep(250); try { tgt = (await (await fetch(`http://127.0.0.1:${PORT}/json`)).json()).find(t => t.type === 'page'); } catch {} }
const ws = new WebSocket(tgt.webSocketDebuggerUrl); await new Promise(r => ws.onopen = r);
let id = 0; const wait = new Map();
ws.onmessage = e => { const m = JSON.parse(e.data); if (m.id && wait.has(m.id)) { wait.get(m.id)(m); wait.delete(m.id); } };
const send = (method, params = {}) => new Promise(r => { const i = ++id; wait.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
await send('Emulation.setDeviceMetricsOverride', { width: +W, height: +H, deviceScaleFactor: +DPR, mobile: false });
for (const job of jobs) {
  const k = job.indexOf('='), name = job.slice(0, k), [url, act] = job.slice(k + 1).split('|');
  await send('Page.navigate', { url });
  await sleep(1400);
  if (act) { const r = await send('Runtime.evaluate', { expression: act, awaitPromise: true, returnByValue: true }); console.log(JSON.stringify(r.result?.exceptionDetails?.exception?.description ?? r.result?.result?.value ?? r, null, 1)); }
  if (name.endsWith('.pdf')) {
    const r = await send('Page.printToPDF', { printBackground: true, preferCSSPageSize: true, marginTop: 0, marginBottom: 0, marginLeft: 0, marginRight: 0 });
    if (!r.result) { console.error(name, JSON.stringify(r.error)); continue; }
    writeFileSync(`${out}/${name}`, Buffer.from(r.result.data, 'base64'));
  } else {
    const r = await send('Page.captureScreenshot', { format: 'png' });
    writeFileSync(`${out}/${name}.png`, Buffer.from(r.result.data, 'base64'));
  }
  console.log(name);
}
ws.close(); ch.kill();

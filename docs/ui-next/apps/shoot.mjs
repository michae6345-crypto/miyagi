// Renders the apps screens (MIC-87) to ../shots/apps, light and dark, at 2x.
// usage, from ui-next/:   node apps/shoot.mjs [screen ...] [--probe] [--light]     (no names: all of them)
// Its own Chrome profile and a port Chrome picks, so it can run while another session renders. Each shot is checked:
// the tab must be on the screen that was asked for, or the run stops. (Same method as social/shoot.mjs.)
import { spawn } from 'node:child_process';
import { writeFileSync, mkdirSync, mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const OUT = join(here, '..', 'shots', 'apps');
const BASE = pathToFileURL(join(here, '..', 'mock', 'index.html')).href;
// screen: height in px (the window is 1440 wide). Taller than 900 where the page runs longer.
export const SCREENS = {
  'apps-home-first': 966, 'apps-home-first-10': 1190, 'apps-home-first-none': 966, 'apps-home': 1102, 'apps-home-10': 1102,
  'apps-app-blender': 1000, 'apps-app-vscode': 1440, 'apps-app-fusion': 900,
  'apps-b-home-first': 992, 'apps-b-home-first-10': 1019, 'apps-b-home': 1137, 'apps-b-home-10': 1164
};
const args = process.argv.slice(2), want = args.filter(a => !a.startsWith('--'));
const names = want.length ? want : Object.keys(SCREENS);
const probe = args.includes('--probe'), themes = args.includes('--light') ? ['light'] : ['light', 'dark'];

mkdirSync(OUT, { recursive: true });
const CH = 'C:/Program Files/Google/Chrome/Application/chrome.exe', PROFILE = mkdtempSync(join(tmpdir(), 'miyagi-apps-'));
const ch = spawn(CH, ['--headless=new', '--hide-scrollbars', '--allow-file-access-from-files', '--remote-debugging-port=0',
  `--user-data-dir=${PROFILE}`, '--window-size=1440,900', 'about:blank'], { stdio: 'ignore' });
const sleep = ms => new Promise(r => setTimeout(r, ms));
let tgt, PORT;
for (let i = 0; i < 80 && !tgt; i++) { await sleep(250); try { PORT = PORT || +readFileSync(join(PROFILE, 'DevToolsActivePort'), 'utf8').split('\n')[0]; tgt = (await (await fetch(`http://127.0.0.1:${PORT}/json`)).json()).find(t => t.type === 'page'); } catch {} }
if (!tgt) { ch.kill(); throw new Error('Chrome did not start'); }
const ws = new WebSocket(tgt.webSocketDebuggerUrl); await new Promise(r => ws.onopen = r);
let id = 0; const wait = new Map(), errors = [];
ws.onmessage = e => { const m = JSON.parse(e.data); if (m.id && wait.has(m.id)) { wait.get(m.id)(m); wait.delete(m.id); } else if (m.method === 'Runtime.exceptionThrown') errors.push(m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text); };
const send = (method, params = {}) => new Promise(r => { const i = ++id; wait.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
await send('Runtime.enable');
for (const name of names) {
  const h = SCREENS[name] || 900;
  for (const t of themes) {
    errors.length = 0;
    await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: h, deviceScaleFactor: 2, mobile: false });
    await send('Page.navigate', { url: `${BASE}?s=${name}&t=${t}${h !== 900 ? `&h=${h}` : ''}` });
    await sleep(900);
    if (errors.length) { ws.close(); ch.kill(); throw new Error(`script error on ${name}-${t}: ${errors.join(' | ')}`); }
    const at = await send('Runtime.evaluate', { returnByValue: true, expression: `JSON.stringify({ q: location.search, mock: location.pathname.endsWith('/mock/index.html'), cls: document.documentElement.className, shell: !!document.querySelector('.win, .flow'), mine: !!document.querySelector('.tbl.apps, .appline, .apphead') || document.body.innerHTML.includes('Learn in') })` });
    const pg = JSON.parse(at.result?.result?.value || '{}');
    if (!pg.mock || !pg.shell || !pg.mine || !pg.q.includes(`s=${name}&t=${t}`) || !pg.cls.includes(t)) { ws.close(); ch.kill(); throw new Error(`wrong page for ${name}-${t}: ${JSON.stringify(pg)}`); }
    if (probe && t === 'light') {
      // how tall the page really is, and any text that is cut or spills out of its box
      const r = await send('Runtime.evaluate', { returnByValue: true, expression: `(() => { const c = document.querySelector('.scroll > div'); const b = c ? Math.round(c.getBoundingClientRect().bottom) : 0;
        const rail = document.querySelector('.rail'); const rb = rail ? Math.round(rail.getBoundingClientRect().bottom) : 0;
        const cut = [...document.querySelectorAll('.main *')].filter(e => e.children.length === 0 && e.scrollWidth > e.clientWidth + 1 && e.clientWidth > 0).slice(0, 8).map(e => (e.className || e.tagName) + ':' + e.textContent.slice(0, 34));
        return JSON.stringify({ bottom: b, rail: rb, cut }); })()` });
      console.log(name, r.result?.result?.value ?? JSON.stringify(r.result));
    }
    const r = await send('Page.captureScreenshot', { format: 'png' });
    writeFileSync(join(OUT, `${name}-${t}.png`), Buffer.from(r.result.data, 'base64'));
  }
  console.log('shot', name);
}
ws.close(); ch.kill();
await sleep(400); try { rmSync(PROFILE, { recursive: true, force: true }); } catch {}

// Renders the social screens (Friends and the leaderboard) to ../shots/social, light and dark, at 2x.
// usage, from ui-next/:   node social/shoot.mjs [screen ...]      (no names: all of them)
// Its own Chrome profile and a port Chrome picks, so it can run while another session renders. Each shot is checked:
// the tab must be on the screen that was asked for, or the run stops.
import { spawn } from 'node:child_process';
import { writeFileSync, mkdirSync, mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const OUT = join(here, '..', 'shots', 'social');
const BASE = pathToFileURL(join(here, '..', 'mock', 'index.html')).href;
// screen: height in px (the window is 1440 wide). Taller than 900 where the page runs longer.
export const SCREENS = {
  friends: 1010, 'friends-first': 900, 'friends-on': 900, 'friends-empty': 940, 'home-friends': 1102, 'friends-list': 940, friend: 940, 'friends-menu': 940, 'friends-remove': 940, 'friends-block': 940,
  'friends-add': 1010, 'friends-add-found': 1010, 'friends-add-miss': 1010, 'friends-offline': 1066, 'friends-off': 900, 'friends-guest': 900,
  'settings-friends': 900, 'friends-teen-on': 900, 'friends-teen-add': 1010, 'settings-friends-teen': 900
};
const want = process.argv.slice(2).filter(a => !a.startsWith('--'));
const names = want.length ? want : Object.keys(SCREENS);
const probe = process.argv.includes('--probe');

mkdirSync(OUT, { recursive: true });
// Chrome picks a free port itself (port 0) and writes it into its own profile folder, so this can only ever talk to
// the Chrome it started. A fixed port once collided with another session's Chrome and each drove the other's tab.
const CH = 'C:/Program Files/Google/Chrome/Application/chrome.exe', PROFILE = mkdtempSync(join(tmpdir(), 'miyagi-social-'));
const ch = spawn(CH, ['--headless=new', '--hide-scrollbars', '--allow-file-access-from-files', '--remote-debugging-port=0',
  `--user-data-dir=${PROFILE}`, '--window-size=1440,900', 'about:blank'], { stdio: 'ignore' });
const sleep = ms => new Promise(r => setTimeout(r, ms));
let tgt, PORT;
for (let i = 0; i < 80 && !tgt; i++) { await sleep(250); try { PORT = PORT || +readFileSync(join(PROFILE, 'DevToolsActivePort'), 'utf8').split('\n')[0]; tgt = (await (await fetch(`http://127.0.0.1:${PORT}/json`)).json()).find(t => t.type === 'page'); } catch {} }
if (!tgt) { ch.kill(); throw new Error('Chrome did not start'); }
const ws = new WebSocket(tgt.webSocketDebuggerUrl); await new Promise(r => ws.onopen = r);
let id = 0; const wait = new Map();
ws.onmessage = e => { const m = JSON.parse(e.data); if (m.id && wait.has(m.id)) { wait.get(m.id)(m); wait.delete(m.id); } };
const send = (method, params = {}) => new Promise(r => { const i = ++id; wait.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
await send('Runtime.enable');
for (const name of names) {
  const h = SCREENS[name] || 900;
  for (const t of ['light', 'dark']) {
    await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: h, deviceScaleFactor: 2, mobile: false });
    await send('Page.navigate', { url: `${BASE}?s=${name}&t=${t}${h !== 900 ? `&h=${h}` : ''}` });
    await sleep(900);
    // The page in the tab must be the screen that was asked for, in the mock, with the Friends work on it.
    const at = await send('Runtime.evaluate', { returnByValue: true, expression: `JSON.stringify({ q: location.search, mock: location.pathname.endsWith('/mock/index.html'), cls: document.documentElement.className, shell: !!document.querySelector('.win, .flow') })` });
    const pg = JSON.parse(at.result?.result?.value || '{}');
    if (!pg.mock || !pg.shell || !pg.q.includes(`s=${name}&t=${t}`) || !pg.cls.includes(t)) { ws.close(); ch.kill(); throw new Error(`wrong page for ${name}-${t}: ${JSON.stringify(pg)}`); }
    if (probe && t === 'light') {
      // how tall the page really is, and anything that overflows its box sideways
      const r = await send('Runtime.evaluate', { returnByValue: true, expression: `(() => { const c = document.querySelector('.scroll > div'); const b = c ? Math.round(c.getBoundingClientRect().bottom) : 0;
        const over = [...document.querySelectorAll('.main *')].filter(e => e.scrollWidth > e.clientWidth + 1 && getComputedStyle(e).overflow === 'visible' && e.children.length === 0).slice(0, 6).map(e => e.className + ':' + e.textContent.slice(0, 30));
        return JSON.stringify({ bottom: b, over, title: document.querySelector('h1,h2') && document.querySelector('h1,h2').textContent }); })()` });
      console.log(name, r.result?.result?.value ?? JSON.stringify(r.result));
    }
    const r = await send('Page.captureScreenshot', { format: 'png' });
    writeFileSync(join(OUT, `${name}-${t}.png`), Buffer.from(r.result.data, 'base64'));
  }
  console.log('shot', name);
}
ws.close(); ch.kill();
await sleep(400); try { rmSync(PROFILE, { recursive: true, force: true }); } catch {}

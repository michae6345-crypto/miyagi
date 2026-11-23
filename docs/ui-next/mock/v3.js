// v3 (Nov 22 night): Home, Progress, Settings and Library redone; plans (preset, from a playlist, from a goal);
// Blender and CAD lessons. Loaded after app.js. Plan data comes from ../catalog/catalog.js (window.CATALOG).
Object.assign(I, {
  back: '<path d="m15 6-6 6 6 6"/>',
  plug: '<path d="M9 7V3M15 7V3M7 7h10v4a5 5 0 0 1-10 0zM12 16v5"/>',
  cube: '<path d="M12 3l8 4.5v9L12 21l-8-4.5v-9zM12 12l8-4.5M12 12v9M12 12L4 7.5"/>',
  user: '<circle cx="12" cy="8" r="3.6"/><path d="M5 20c.8-3.6 3.6-5.4 7-5.4s6.2 1.8 7 5.4"/>',
  card: '<rect x="3" y="6" width="18" height="12" rx="2.5"/><path d="M3 10.5h18"/>',
  key: '<rect x="3" y="7" width="18" height="10" rx="2.5"/><path d="M7 11h.01M11 11h.01M15 11h.01M8 14h8"/>',
  bell: '<path d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15zM10 20.5h4"/>',
  lock: '<rect x="5" y="11" width="14" height="9" rx="2.5"/><path d="M8.5 11V8a3.5 3.5 0 0 1 7 0v3"/>',
  eye: '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z"/><circle cx="12" cy="12" r="2.8"/>',
  info: '<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5M12 8h.01"/>',
  sliders: '<path d="M4 7h10M18 7h2M4 17h4M12 17h8"/><circle cx="16" cy="7" r="2"/><circle cx="10" cy="17" r="2"/>',
  grid: '<rect x="4" y="4" width="7" height="7" rx="1.5"/><rect x="13" y="4" width="7" height="7" rx="1.5"/><rect x="4" y="13" width="7" height="7" rx="1.5"/><rect x="13" y="13" width="7" height="7" rx="1.5"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  dn: '<path d="m7 10 5 5 5-5"/>'
});
const CAT = (window.CATALOG && window.CATALOG.plans) || [];
const PL = id => CAT.find(p => p.id === id) || { id, title: id, line: '', lessons: [], skills: [], project: { title: '', brief: '', checks: [] }, tool: { label: '' }, minutes: 0, playlists: [] };
const hrs = m => m < 90 ? `${m} min` : `${Math.round(m / 30) / 2} hr`;
const tick = '<span class="cb"><svg viewBox="0 0 12 12"><path d="m2.6 6.3 2.3 2.3 4.6-4.9"/></svg></span>';

// ---------- covers for 3D and CAD (stand-ins for a real render or screenshot) ----------
Object.assign(THUMB, {
  mug: () => { let s = '<rect width="160" height="90" fill="#2A2B2F"/>';
    for (let i = -6; i <= 6; i++) s += `<path d="M${80 + i * 9} 52L${80 + i * 30} 96" stroke="#3B3D43" stroke-width=".7"/>`;
    for (let j = 0; j < 5; j++) s += `<path d="M0 ${54 + j * j * 2.4 + j * 3}H160" stroke="#3B3D43" stroke-width=".7"/>`;
    return s + '<path d="M101 40c12-2 17 4 16 11s-8 11-17 9" fill="none" stroke="#C9CBD1" stroke-width="5" stroke-linecap="round"/>' +
      '<path d="M58 32v28c0 6 10 10 22 10s22-4 22-10V32z" fill="#DADCE1"/><ellipse cx="80" cy="32" rx="22" ry="6.5" fill="#F1F2F5"/><ellipse cx="80" cy="33" rx="17.5" ry="4.6" fill="#8D9099"/>'; },
  part: () => { let s = '<rect width="160" height="90" fill="#FAFAF8"/>';
    s += '<path d="M40 56l48-16 36 12-48 16z" fill="#E4E3DE" stroke="#2B2A27" stroke-width="1.2" stroke-linejoin="round"/><path d="M40 56v7l36 12v-7zM76 68v7l48-16v-7z" fill="#CFCEC8" stroke="#2B2A27" stroke-width="1.2" stroke-linejoin="round"/>';
    s += '<ellipse cx="62" cy="54" rx="5" ry="2.2" fill="#FAFAF8" stroke="#2B2A27" stroke-width="1"/><ellipse cx="102" cy="52" rx="5" ry="2.2" fill="#FAFAF8" stroke="#2B2A27" stroke-width="1"/>';
    return s + '<path d="M40 32l48-16" stroke="#8C8B85" stroke-width=".8"/><path d="M40 28v8M88 12v8" stroke="#8C8B85" stroke-width=".8"/><text x="60" y="20" font-size="7" fill="#6B6A65" transform="rotate(-18 60 20)">60</text>'; },
  lamp: () => '<rect width="160" height="90" fill="#2A2B2F"/><ellipse cx="80" cy="74" rx="24" ry="5" fill="#8D9099"/><path d="M78 74V40h4v34z" fill="#C9CBD1"/><path d="M62 42l10-22h16l10 22z" fill="#F1F2F5"/><path d="M62 42h36" stroke="#8D9099"/>',
  web: () => '<rect width="160" height="90" fill="#FFFFFF"/><rect width="160" height="14" fill="#EDEDE9"/><circle cx="8" cy="7" r="2" fill="#C8C7C1"/><circle cx="15" cy="7" r="2" fill="#C8C7C1"/><rect x="14" y="24" width="60" height="6" rx="3" fill="#2B2A27"/><rect x="14" y="36" width="84" height="3.6" rx="1.8" fill="#C8C7C1"/><rect x="14" y="44" width="70" height="3.6" rx="1.8" fill="#C8C7C1"/><rect x="14" y="56" width="30" height="10" rx="5" fill="#2B2A27"/><rect x="108" y="24" width="38" height="46" rx="4" fill="#F3F3F0"/>'
});
const COVER = { 'intro-python': 'code', 'intro-blender': 'mug', 'intro-cad': 'part', 'intro-javascript': 'web', 'intro-html-css': 'web', 'neural-networks': 'net', pandas: 'table', plotting: 'plot', numpy: 'nb', 'intro-terminal': 'term' };

// ---------- shell: Plans in the sidebar; Settings swaps the sidebar for its own list ----------
const MYPLANS = [['Neural networks from scratch', '3 of 8'], ['Intro to Blender', '1 of 10']];
function shell3(active, crumbs, actions, body, o = {}) {
  const nav = (id, icon, label, right = '') => `<div class="sr${active === id ? ' on' : ''}">${ic(icon)}<span class="t">${label}</span>${right ? `<span class="r">${right}</span>` : ''}</div>`;
  const pg = (mark, label, right = '', on = false) => `<div class="sr${on ? ' on' : ''}"><span class="sdot">${mark}</span><span class="t">${label}</span>${right ? `<span class="r">${right}</span>` : ''}</div>`;
  const crumb = crumbs.map((c, i) => i === crumbs.length - 1 ? `<b>${c}</b>` : `${c}<i>/</i>`).join('');
  const plans = o.plans || MYPLANS, recent = o.recent || [['c', 'Code your first neural network'], ['c', 'Move, rotate and scale'], ['d', 'numpy arrays from scratch']];
  return `<div class="win"><aside class="side">
    <div class="ws"><img class="t" src="${asset('tree-small')}"><img class="w" src="${asset('wordmark')}"><div class="new">${ic('compose')}</div></div>
    ${nav('search', 'search', 'Search', '⌥ Space')}${nav('home', 'home', 'Home')}${nav('library', 'lib', 'Library')}${nav('skills', 'skills', 'Skills')}${nav('progress', 'progress', 'Progress')}
    <div class="slabel">Plans</div>${plans.map((p, i) => pg(ic('list'), p[0], p[1], o.plan === i)).join('')}
    <div class="slabel">Recent</div>${recent.map((r, i) => pg(r[0] === 'd' ? gk : '<span class="ring cur"></span>', r[1], '', o.lesson === i)).join('')}
    <div class="grow"></div>${nav('settings', 'settings', 'Settings')}
    <div class="acct"><div class="av">S</div><b>Sam Rivera</b><span>Free</span></div>
  </aside><main class="main"><div class="top"><div class="crumb">${crumb}</div><div class="sp"></div>${actions || ''}<div class="tbtn">${ic('more')}</div></div>${body}</main></div>`;
}
function shellSet(active, body) {
  const it = (id, icon, label) => `<div class="sr${active === id ? ' on' : ''}">${ic(icon)}<span class="t">${label}</span></div>`;
  return `<div class="win"><aside class="side">
    <div class="sback">${ic('back')}Settings</div>
    ${it('account', 'user', 'Account')}${it('plan', 'card', 'Plan and usage')}
    <div class="slabel">App</div>${it('general', 'sliders', 'General')}${it('keys', 'key', 'Shortcuts')}${it('notify', 'bell', 'Notifications')}
    <div class="slabel">Learning</div>${it('lessons', 'lib', 'Lessons')}${it('apps', 'plug', 'Apps')}
    <div class="slabel">Privacy</div>${it('perms', 'lock', 'Permissions')}${it('data', 'eye', 'Your data')}
    <div class="grow"></div>${it('about', 'info', 'About')}
  </aside><main class="main"><div class="top"><div class="crumb">Settings<i>/</i><b>${{ general: 'General', apps: 'Apps', data: 'Your data' }[active]}</b></div><div class="sp"></div></div>${body}</main></div>`;
}
const sec = (t, link = '') => `<div class="sec">${t}${link ? `<a>${link} ${ic('chev')}</a>` : ''}</div>`;
const pbar = (d, n, green) => `<div class="pb"><div class="bar${green ? ' g' : ''}"><i style="width:${d / n * 100}%"></i></div><span>${d} of ${n}</span></div>`;

// ---------- Home ----------
function home3() {
  const plan = (t, d, n, next, left) => `<div class="lrow plan"><div class="nm"><b>${t}</b></div>${pbar(d, n)}<div class="m">Next · ${next}</div>${chevRow}</div>`;
  const nx = (t, meta) => `<div class="lrow next"><div class="nm"><b>${t}</b></div><div class="r">${meta}</div>${chevRow}</div>`;
  return shell3('home', ['Home'], '', page(`
    <div class="hello"><h1>Good evening, Sam</h1><span>Sunday, November 22</span></div>
    <div class="lede">1 h 48 min this week. About 3 hours to <b>Fit sin(x) with a network</b>.</div>
    <div style="margin-top:8px">${askField()}</div>
    <div style="margin-top:14px">${contCard().replace('Continue · Step 4 of 7', 'Step 4 of 7')}</div>
    ${sec('Plans', 'Browse plans')}
    ${plan('Neural networks from scratch', 3, 8, 'Broadcasting')}${plan('Intro to Blender', 1, 10, 'Move, rotate and scale')}
    ${sec('Up next', 'Library')}
    ${nx('Plot your data with matplotlib', 'Jupyter · 6 steps · 15 min')}${nx('Matrices as layers', 'Jupyter · 5 steps · 25 min')}${nx('Summarize sales with pandas', 'Jupyter · 6 steps · 20 min')}
    ${sec('Keep fresh')}
    <div class="lrow next"><div class="nm">${ic('refresh')}<b>Functions, DataFrames</b></div><div class="r">2 skills · 4 min</div>${chevRow}</div>`));
}

// ---------- Progress ----------
function weekChart() {
  const D = [['M', 0], ['T', 22], ['W', 41], ['T', 0], ['F', 18], ['S', 12], ['S', 15]], W = 440, H = 150, base = 118, top = 22, max = 45, bw = 34, gap = (W - 30 - 7 * bw) / 6;
  let s = `<path d="M0 ${base}H${W}" stroke="var(--hair2)"/><path d="M0 ${base - 30 / max * (base - top)}H${W}" stroke="var(--hair)" stroke-dasharray="2 4"/><text x="${W}" y="${base - 30 / max * (base - top) - 5}" text-anchor="end">30 min</text>`;
  D.forEach(([d, m], i) => {
    const x = i * (bw + gap), h = Math.max(m / max * (base - top), 0), today = i === 6;
    s += m ? `<path d="M${x} ${base}V${base - h + 4}a4 4 0 0 1 4-4h${bw - 8}a4 4 0 0 1 4 4V${base}z" fill="${today ? 'var(--ink)' : 'var(--ghost)'}"/>` : `<rect x="${x}" y="${base - 2}" width="${bw}" height="2" fill="var(--track)"/>`;
    if (today || m === 41) s += `<text class="v${today ? ' on' : ''}" x="${x + bw / 2}" y="${base - h - 7}" text-anchor="middle">${m}</text>`;
    s += `<text class="${today ? 'on' : ''}" x="${x + bw / 2}" y="${base + 18}" text-anchor="middle">${d}</text>`;
  });
  return `<svg viewBox="0 0 ${W} ${H}">${s}</svg>`;
}
function progress3() {
  const tree = bonsai().replace(/<text[\s\S]*?<\/text>/g, '').replace(/<circle[^>]*stroke-dasharray[^>]*\/>/g, '').replace('viewBox="0 0 640 400" style="width:640px;height:400px;display:block;margin:0 auto"', 'viewBox="170 24 300 366" style="width:164px;height:200px"');
  const T = [['python', 4, 4, '', 'Nov 12'], ['numpy', 2, 3, 'Broadcasting', 'Today'], ['math', 2, 3, 'Matrices', 'Yesterday'], ['pandas', 2, 4, 'Cleaning rows', 'Nov 18'], ['plotting', 1, 4, 'Scatter plots', 'Nov 16'], ['neural networks', 0, 3, 'Needs Broadcasting and Matrices', '']];
  const R = [['Today, 4:12 PM', 'Add one row to every row', 'Broadcasting', 'numpy for networks'], ['Today, 4:03 PM', 'Shapes and axes', 'Broadcasting', 'numpy for networks'], ['Yesterday', 'With numpy', 'Dot product', 'The dot product'], ['Wednesday', 'Slice rows and columns', 'Indexing', 'numpy for networks']];
  return shell3('progress', ['Progress'], `<div class="tbtn">${ic('share')}Share</div>`, page(`
    <div class="titlerow"><h1>Progress</h1><div class="sp"></div><button class="btn primary">${ic('play')}Continue Broadcasting ${kbd('↩')}</button></div>
    <div class="lede">11 of 20 skills mastered. About 3 hours to <b>Fit sin(x) with a network</b>, around Dec 4 at your pace.</div>
    <div class="wkrow"><div class="wk"><div class="hd">This week<span>minutes a day</span></div>${weekChart()}</div><div class="grove">${tree}<div>11 leaves, one for each skill</div></div></div>
    <div class="stats"><div><b>1<small>h</small> 48<small>min</small></b><span>practiced this week</span></div><div><b>6</b><span>steps passed</span></div><div><b>2</b><span>skills mastered</span></div><div><b>5</b><span>days of 7</span></div></div>
    ${sec('Goal')}
    <div class="lrow plan" style="grid-template-columns:minmax(0,1.25fr) 150px minmax(0,1fr) 14px"><div class="nm">${ic('flag')}<b>Fit sin(x) with a network</b></div>${pbar(8, 13)}<div class="m">about 3 hours left · around Dec 4</div>${chevRow}</div>
    ${sec('Tracks', 'Skills')}
    <table class="tbl sm"><tr><th>Track</th><th style="width:150px">Mastered</th><th>Next</th><th class="r">Last practiced</th></tr>
      ${T.map(([t, d, n, nx, last]) => `<tr><td><b class="t">${t}</b></td><td>${pbar(d, n, true)}</td><td class="${d === n || !d ? 'mu' : ''}">${d === n ? 'Done' : nx}</td><td class="r mu">${last}</td></tr>`).join('')}</table>
    ${sec('Recently passed', 'All')}
    <table class="tbl sm"><tr><th style="width:150px">When</th><th>Step</th><th>Skill</th><th>Lesson</th></tr>
      ${R.map(r => `<tr><td class="mu nw">${r[0]}</td><td><div class="vt">${gk}<b>${r[1]}</b></div></td><td><span class="tag">${r[2]}</span></td><td class="mu">${r[3]}</td></tr>`).join('')}</table>
    ${sec('Keep fresh')}
    <div class="lrow next"><div class="nm">${ic('refresh')}<b>Functions, DataFrames</b></div><div class="r">2 skills · 4 min</div>${chevRow}</div>
    <div style="height:60px"></div>`));
}

// ---------- Settings ----------
const frow = (l, d, right) => `<div class="frow"><div><div class="l">${l}</div>${d ? `<div class="d">${d}</div>` : ''}</div><span class="sp"></span>${right}</div>`;
const sel = t => `<span class="sel">${t}${ic('dn')}</span>`;
const seg3 = (items, on) => `<div class="seg">${items.map((t, i) => `<b class="${i === on ? 'on' : ''}">${t}</b>`).join('')}</div>`;
const tog = on => `<span class="tog${on ? ' on' : ''}"></span>`;
const okv = t => `<span class="v ok">${gk}${t}</span>`;
function settings3() {
  return shellSet('general', page(`
    <h1>General</h1>
    <div class="shd" style="margin-top:26px">Appearance</div>
    ${frow('Theme', '', seg3(['System', 'Light', 'Dark'], 0))}
    ${frow('Where miyagi lives', 'The pill sits in the notch, or under the menu bar on a Mac without one.', sel('In the notch'))}
    <div class="shd">Startup</div>
    ${frow('Open miyagi', 'From anywhere on this Mac.', `<span class="keys">${kbd('⌥')}${kbd('Space')}</span>`)}
    ${frow('Launch at login', 'miyagi waits in the pill until you need it.', tog(true))}
    ${frow('Open to', '', sel('Home'))}
    <div class="shd">Lessons</div>
    ${frow('Read steps aloud', 'Uses the voice built into this Mac.', tog(false))}
    ${frow('Code editor', '', sel('VS Code'))}
    ${frow('Lesson folder', '~/miyagi', '<button class="btn quiet sm">Change</button>')}
    <div class="shd">Updates</div>
    ${frow('miyagi 0.9.2', 'Up to date. Checked today at 6:40 PM.', '<button class="btn quiet sm">Check for updates</button>')}
    ${frow('Update automatically', '', tog(true))}`));
}
function settingsApps() {
  const app = (n, d, right) => frow(n, d, right);
  const con = '<button class="btn quiet sm">Connect</button>', scr = '<span class="v">Screen only</span>';
  return shellSet('apps', page(`
    <h1>Apps</h1>
    <div class="lede">The apps miyagi can check your work in. Connected apps are read exactly. In the rest it looks at the window.</div>
    <div class="shd" style="margin-top:26px">Code</div>
    ${app('VS Code', 'Reads your files and the terminal.', okv('Connected'))}
    ${app('Jupyter', 'Reads each cell and what it printed.', okv('Connected'))}
    ${app('Terminal', 'Reads commands and their output.', okv('Connected'))}
    <div class="shd">3D and CAD</div>
    ${app('Blender', 'Reads your scene. Objects, modifiers, materials, lights. Blender 4.2 · add-on 1.0', okv('Connected'))}
    ${app('FreeCAD', 'Reads your model. Sketches, constraints, features, dimensions.', con)}
    ${app('Fusion', 'Reads your timeline and bodies.', con)}
    ${app('Onshape', 'Reads your Part Studio after you sign in.', con)}
    <div class="shd">Everything else</div>
    ${app('Figma, Excel, Google Sheets', 'miyagi looks at the window. It cannot read the file yet.', scr)}
    ${app('Any other app', 'Lessons still work. Checks use what is on screen.', scr)}`));
}
function settingsData() {
  return shellSet('data', page(`
    <h1>Your data</h1>
    <div class="lede">What miyagi sees, what it keeps, and how to remove it.</div>
    <div class="shd" style="margin-top:26px">During a lesson</div>
    ${frow('What miyagi sees', 'Only the lesson window, and only while a lesson is running.', `<span class="v">See an example ${chevRow}</span>`)}
    ${frow('Screenshots', 'Used to check a step, then deleted. Never used to train models.', '<span class="v">Not kept</span>')}
    ${frow('Your code and files', 'Stay on this Mac. The step being checked is sent, nothing else.', '<span class="v">On this Mac</span>')}
    <div class="shd">Kept in your account</div>
    ${frow('Lesson history and skills', '14 lessons, 11 skills.', '<button class="btn quiet sm">Download</button>')}
    ${frow('Clear lesson history', 'Your skills and plans start over.', '<button class="btn quiet sm">Clear</button>')}
    <div class="shd">Account</div>
    ${frow('Delete my account', 'Removes your account and everything in it within 30 days.', '<button class="btn quiet sm">Delete account</button>')}`));
}

// ---------- Library ----------
function library3() {
  const L = [['net', 'Code your first neural network', 'Jupyter', 'Single neuron|Layers', [4, 7], 'Today'], ['mug', 'Move, rotate and scale', 'Blender', 'Transforms', [2, 6], 'Today'], ['table', 'Clean a CSV with pandas', 'Jupyter', 'Cleaning rows', [3, 6], 'Yesterday'],
    ['code', 'numpy for networks', 'VS Code', 'Broadcasting', [3, 4], 'Yesterday'], ['plot', 'Plot your data with matplotlib', 'Jupyter', 'Line plots', [0, 6], ''], ['term', 'Set up a Python environment', 'Terminal', 'Running a script', [0, 5], '']];
  const plan = (cover, t, d, n, next) => `<div class="lc" style="display:flex;gap:14px;align-items:center">${th(cover, { style: 'width:132px;flex:none;margin:0' })}<div style="min-width:0;flex:1"><b>${t}</b><span>Next · ${next}</span><div style="margin-top:9px">${pbar(d, n)}</div></div></div>`;
  return shell3('library', ['Library'], '', page(`
    <div class="titlerow"><h1>Library</h1><div class="sp"></div><button class="btn quiet">${ic('list')}New plan</button><button class="btn primary">${ic('compose')}New lesson</button></div>
    <div class="tabs"><b class="on">All</b><b>Lessons</b><b>Plans</b><b>Finished</b><div class="sp"></div><div class="tbtn">${ic('grid')}</div><div class="tbtn">${ic('search')}</div></div>
    ${sec('Plans', 'Browse plans').replace('class="sec"', 'class="sec" style="margin-top:22px"')}
    <div class="grid2 lrow-reset">${plan('net', 'Neural networks from scratch', 3, 8, 'Broadcasting')}${plan('mug', 'Intro to Blender', 1, 10, 'Move, rotate and scale')}</div>
    ${sec('Lessons')}
    <table class="tbl"><tr><th>Lesson</th><th>Works in</th><th>Grows</th><th style="width:130px">Progress</th><th class="r">Opened</th></tr>
      ${L.map(([k, t, tool, grows, [d, n], when]) => `<tr><td><div class="vt">${th(k)}<b>${t}</b></div></td><td class="mu">${tool}</td><td>${grows.split('|').map(g => `<span class="tag">${g}</span>`).join(' ')}</td><td>${d ? pbar(d, n) : '<span style="color:var(--muted);font-size:13px">Ready</span>'}</td><td class="r mu">${when}</td></tr>`).join('')}</table>`));
}

// ---------- Plans: the catalog ----------
const WAYS = `<div class="two"><div class="way">${ic('yt')}<div><b>From a playlist</b><span>Paste a YouTube playlist link</span></div>${chevRow}</div><div class="way">${ic('sprout')}<div><b>From a goal</b><span>Say what you want to make</span></div>${chevRow}</div></div>`;
function plansPage(o = {}) {
  const T = [['All', CAT.length], ['Code', 0], ['Data', 0], ['AI', 0], ['3D', 0], ['CAD', 0], ['Design', 0], ['Tools', 0]];
  T.slice(1).forEach(t => { t[1] = CAT.filter(p => p.topic === t[0].toLowerCase()).length; });
  const card = id => { const p = PL(id); return `<div class="pc">${th(COVER[id] || 'code')}<b>${p.title}</b><span>${p.tool.label} · ${p.lessons.length} lessons · about ${hrs(p.minutes)}</span><span>Ends with ${p.project.title.charAt(0).toLowerCase() + p.project.title.slice(1)}</span></div>`; };
  const table = (g, name) => { const rows = CAT.filter(p => p.group === g); if (!rows.length) return '';
    return `${sec(`${name}<span class="cnt">${rows.length}</span>`)}<table class="tbl sm"><tr><th style="width:206px">Plan</th><th style="width:112px">Works in</th><th class="r" style="width:62px">Lessons</th><th class="r" style="width:62px">Time</th><th style="padding-left:28px">Ends with</th></tr>
      ${rows.map(p => `<tr><td class="nw"><b class="t">${p.title}</b></td><td class="mu nw">${p.tool.label}</td><td class="r mu">${p.lessons.length}</td><td class="r mu nw">${hrs(p.minutes)}</td><td class="mu" style="padding-left:28px">${p.project.title}</td></tr>`).join('')}</table>`; };
  return shell3('library', ['Library', 'Browse plans'], '', `<div class="scroll"><div class="col">
    <h1>Plans</h1><div class="lede">A plan is a set of lessons in order that ends in something you made.</div>
    ${WAYS}
    <div class="tabs">${T.map(([t, n], i) => `<b class="${i === 0 ? 'on' : ''}">${t}<span class="cnt" style="margin-left:0">${n}</span></b>`).join('')}<div class="sp"></div><div class="tbtn">${ic('search')}</div></div>
    ${sec('Start here').replace('class="sec"', 'class="sec" style="margin-top:22px"')}
    <div class="grid3">${card('intro-python')}${card('intro-blender')}${card('intro-cad')}</div>
    ${table('language', 'Coding languages')}${table('environment', 'Apps and tools')}${table('topic', 'Going further')}
    <div style="height:60px"></div></div>${o.after || ''}</div>`);
}
const plans3 = () => plansPage();

// ---------- a small skill diagram for any plan: columns by depth, hairline elbows ----------
function dag(plan, st, o = {}) {
  const S = plan.skills, own = new Set(S.map(s => s.id)), depth = {}, by = Object.fromEntries(S.map(s => [s.id, s]));
  const dep = id => depth[id] != null ? depth[id] : (depth[id] = Math.max(-1, ...by[id].needs.filter(n => own.has(n)).map(dep)) + 1);
  S.forEach(s => dep(s.id));
  const cols = []; S.forEach(s => (cols[depth[s.id]] = cols[depth[s.id]] || []).push(s.id));
  const rows = o.rows || {}, maxR = Math.max(...cols.map(c => c.length)), RH = o.rh || 52, W = o.w || 740;
  const cws = cols.map(c => Math.max(84, ...c.map(id => Math.ceil(by[id].label.length * 7.1 + 43)))), gapX = (W - (o.end || 0) - cws.reduce((a, b) => a + b, 0)) / Math.max(1, cols.length - 1 + (o.end ? 1 : 0));
  const cwOf = id => cws[depth[id]], X = id => cws.slice(0, depth[id]).reduce((a, b) => a + b, 0) + depth[id] * gapX, Y = id => 20 + (rows[id] != null ? rows[id] : (cols[depth[id]].indexOf(id) + (maxR - cols[depth[id]].length) / 2)) * RH;
  const H = 40 + (maxR - 1) * RH, state = id => st[id] || 'k', isD = s => s === 'm';
  let svg = '', html = '';
  const E = []; S.forEach(s => s.needs.filter(n => own.has(n)).forEach(n => E.push([n, s.id])));
  E.map(([a, b]) => ({ a, b, k: isD(state(a)) && isD(state(b)) ? 'done' : isD(state(a)) && state(b) !== 'k' ? 'open' : 'locked' })).sort((p, q) => ORDER[p.k] - ORDER[q.k])
    .forEach(e => { svg += line(elbowH(X(e.a) + cwOf(e.a), Y(e.a), X(e.b), Y(e.b), X(e.b) - gapX / 2), e.k); });
  S.forEach(s => { const k = state(s.id), n = { s: k[0], f: [1, 2] };
    html += `<div class="nd${k === 'k' ? ' k' : ''}${k === 'pn' ? ' next' : ''}" style="left:${X(s.id)}px;top:${Y(s.id) - 16}px;width:${cwOf(s.id)}px">${mk(n)}<span class="nt">${s.label}</span></div>`; });
  if (o.end) { const leaf = S.filter(s => !S.some(t => t.needs.includes(s.id))); leaf.forEach(s => { svg += line(elbowH(X(s.id) + cwOf(s.id), Y(s.id), W - o.end, H / 2), 'locked'); }); html += o.endHtml(W - o.end, H); }
  return `<div class="stg dagwrap" style="width:${W}px;height:${H}px"><svg viewBox="0 0 ${W} ${H}">${svg}</svg>${html}</div>`;
}

// ---------- a preset plan ----------
function plan3() {
  const p = PL('intro-blender'), pl = p.playlists[0];
  const CK = { scene: 'Reads your scene', file: 'Checks the saved file', run: 'Reads the output', code: 'Reads your code', screen: 'Looks at the window' };
  const rows = p.lessons.map((l, i) => `<tr><td class="n">${i + 1}</td><td class="nw"><b class="t">${l.title}</b></td><td>${l.grows.map(g => `<span class="tag">${(p.skills.find(s => s.id === g) || {}).label}</span>`).join(' ')}</td><td class="mu nw">${CK[l.check]}</td><td class="r mu nw">${l.minutes} min</td></tr>`).join('');
  return shell3('library', ['Library', 'Browse plans', p.title], `<div class="tbtn">${ic('share')}Share</div>`, `<div class="scroll"><div class="col">
    <div class="split"><div class="a"><h1>${p.title}</h1><div class="lede">${p.line}</div>
      <dl class="props"><dt>${ic('tool')}Works in</dt><dd>Blender 4.2 or newer <span class="tag ok">${ic('check').replace('class="ic "', 'class="ic" style="width:12px;height:12px;stroke-width:2.4"')}Connected</span></dd>
        <dt>${ic('list')}Length</dt><dd>${p.lessons.length} lessons · about ${hrs(p.minutes)}</dd>
        <dt>${ic('flag')}Ends with</dt><dd>${p.project.title}</dd>
        <dt>${ic('eye')}Checked by</dt><dd>Reading your scene through the miyagi add-on</dd>
        <dt style="align-self:start">${ic('skills')}Grows</dt><dd><div class="tags" style="padding:6px 0">${p.skills.map(s => `<span class="tag">${s.label}</span>`).join('')}</div></dd></dl></div>
      <div class="b">${th('mug')}<button class="btn primary lg" style="width:100%;margin-top:12px">${ic('play')}Start plan ${kbd('↩')}</button></div></div>
    ${sec('Lessons')}
    <table class="tbl sm"><tr><th></th><th>Lesson</th><th>Grows</th><th>Check</th><th class="r">Time</th></tr>${rows}
      <tr><td class="n">${ic('flag')}</td><td class="nw"><b class="t">Project · ${p.project.title}</b></td><td colspan="2" class="mu">On your own. ${p.project.checks.length} checks.</td><td class="r mu nw">about 45 min</td></tr></table>
    ${sec('Rather follow a video')}
    <div class="lrow next"><div class="nm">${ic('yt')}<b>${pl ? pl.title : 'Start from a YouTube playlist'}</b></div><div class="r">${pl ? `${pl.channel} · ${pl.videoCount} videos` : 'Paste a link'}</div>${chevRow}</div>
    <div style="height:60px"></div></div></div>`, { plans: [MYPLANS[0]], recent: [['c', 'Code your first neural network'], ['c', 'Clean a CSV with pandas'], ['d', 'numpy arrays from scratch']] });
}

// ---------- new plan from a playlist ----------
function planPlaylist() {
  const p = PL('intro-blender'), pl = p.playlists[0];
  const vids = pl ? pl.videos.slice(0, 6).map(v => [v.title, Math.round(v.seconds / 60) + ' min']) : p.lessons.slice(0, 6).map(l => [l.title, l.minutes + ' min']);
  // a stand-in for the engine's answer: the skill a video grows, guessed from its title
  const KEYS = [[/uv/i, 'UV unwrapping'], [/textur/i, 'Texturing'], [/material/i, 'Materials'], [/organic|sculpt/i, 'Edit mode'], [/model/i, 'Transforms'], [/light/i, 'Light and camera'], [/render/i, 'Rendering'], [/anim/i, 'Keyframes'], [/geometry node/i, 'Geometry nodes']];
  const skillOf = (t, i) => (KEYS.find(([re]) => re.test(t)) || [0, ['Viewport', 'Transforms', 'Edit mode', 'Modifiers', 'Materials', 'Rendering'][Math.min(i, 5)]])[1];
  const nSkills = pl ? new Set(pl.videos.map((v, i) => skillOf(v.title, i))).size : 9;
  const total = pl ? `${pl.videoCount} videos · ${Math.floor(pl.totalSeconds / 3600)} h ${Math.round(pl.totalSeconds % 3600 / 60)} min` : '14 videos';
  const modal = `<div class="scrim"><div class="pop modal big"><div class="titlerow"><h2>New plan from a playlist</h2><div class="sp"></div><div class="tbtn">${ic('x')}</div></div>
    <div class="field" style="margin-top:14px">${ic('link')}<span>${pl ? pl.url.replace('https://www.', '') : 'youtube.com/playlist?list=…'}<span class="caret"></span></span></div>
    <div class="srcline">${th('mug')}<div><b>${pl ? pl.title : 'Blender beginner series'}</b><span>${pl ? pl.channel + ' · ' : ''}${total}</span></div><span style="flex:1"></span>
      <div style="text-align:right"><b>${vids.length < 6 ? vids.length : (pl ? pl.videoCount : 14)} lessons · ${nSkills} skills</b><span>You have none of these skills yet</span></div></div>
    <table class="tbl sm" style="margin-top:12px"><tr><th style="width:26px"></th><th>Video</th><th>Becomes a lesson that grows</th><th class="r">Length</th></tr>
      ${vids.map((v, i) => `<tr><td>${tick}</td><td class="nw" style="max-width:330px;overflow:hidden;text-overflow:ellipsis"><b class="t">${v[0]}</b></td><td><span class="tag">${skillOf(v[0], i)}</span></td><td class="r mu nw">${v[1]}</td></tr>`).join('')}
      <tr><td></td><td colspan="3" class="mu">${pl ? pl.videoCount - 6 : 8} more videos</td></tr></table>
    <div class="lrow next" style="margin-top:6px">${''}<div class="nm">${ic('flag')}<b>Ends with a project</b><span class="m" style="margin-left:6px">A desk lamp, modeled and rendered on your own</span></div><div class="r">${tog(true)}</div><span></span></div>
    <div class="mfoot"><span class="m">miyagi pauses each video until your scene passes the step.</span><span style="flex:1"></span><button class="btn quiet">Just the first video</button><button class="btn primary">Add plan ${kbd('↩')}</button></div></div></div>`;
  return plansPage({ after: modal });
}

// ---------- new plan from a goal ----------
function planGoal() {
  const a = PL('intro-cad'), b = PL('cad-3d-printing');
  const pick = [...a.lessons.slice(0, 5).map(l => [l, a.title]), ...a.lessons.slice(6, 7).map(l => [l, a.title]), ...(b.lessons || []).slice(0, 2).map(l => [l, b.title])];
  const min = pick.reduce((s, [l]) => s + l.minutes, 0);
  const modal = `<div class="scrim"><div class="pop modal big"><div class="titlerow"><h2>New plan from a goal</h2><div class="sp"></div><div class="tbtn">${ic('x')}</div></div>
    <div class="field" style="margin-top:14px"><img src="${asset('tree-small')}" style="width:18px;height:18px"><span>I want to 3D print a stand for my phone<span class="caret"></span></span></div>
    <div style="display:flex;align-items:center;gap:8px;margin-top:14px"><span style="font-size:13px;color:var(--muted);margin-right:4px">Work in</span><span class="chip sky on">FreeCAD</span><span class="chip lilac">Fusion</span><span class="chip pink">Onshape</span>
      <span style="flex:1"></span><b style="font-size:14px;font-weight:600;color:var(--ink)">${pick.length} lessons · about ${hrs(min + 45)}</b></div>
    <table class="tbl sm" style="margin-top:10px"><tr><th style="width:26px"></th><th>Lesson</th><th>Grows</th><th>From</th><th class="r">Time</th></tr>
      ${pick.map(([l, from], i) => `<tr><td class="n">${i + 1}</td><td class="nw"><b class="t">${l.title}</b></td><td>${l.grows.slice(0, 1).map(g => `<span class="tag">${([...a.skills, ...(b.skills || [])].find(s => s.id === g) || {}).label}</span>`).join('')}</td><td class="mu nw">${from}</td><td class="r mu nw">${l.minutes} min</td></tr>`).join('')}
      <tr><td class="n">${ic('flag')}</td><td class="nw"><b class="t">Project · ${a.project.title}</b></td><td colspan="2" class="mu">Fits a phone 75 mm wide. Saved as an STL.</td><td class="r mu nw">45 min</td></tr></table>
    <div class="mfoot"><span class="m">Built from two plans. Lessons you would not need are left out.</span><span style="flex:1"></span><button class="btn quiet">Change it</button><button class="btn primary">Add plan ${kbd('↩')}</button></div></div></div>`;
  return plansPage({ after: modal });
}

// ---------- a Blender lesson ----------
function lessonBlender() {
  const st = [['Open your mug', 'mug.blend is open', 'd'], ['Add a Subdivision Surface modifier', 'The mug has a Subdivision modifier', 'd'], ['Set the viewport level to 2', 'Levels Viewport is 2', 'c'], ['Shade smooth', 'Smooth shading is on', ''], ['Save the file', 'The file is saved', '']];
  return shell3('library', ['Library', 'Intro to Blender', 'Subdivision and smooth shading'], '', page(`
    <div class="split"><div class="a"><h1>Subdivision and smooth shading</h1>
      <dl class="props"><dt>${ic('tool')}Works in</dt><dd>Blender <span class="tag ok">${ic('check').replace('class="ic "', 'class="ic" style="width:12px;height:12px;stroke-width:2.4"')}Connected</span></dd>
        <dt>${ic('list')}Length</dt><dd>5 steps · about 15 min</dd>
        <dt>${ic('skills')}Grows</dt><dd><div class="tags"><span class="tag">Modifiers</span></div></dd>
        <dt>${ic('eye')}Checked by</dt><dd>Reading your scene. No screenshots.</dd>
        <dt>${ic('lib')}Plan</dt><dd>Intro to Blender · lesson 7 of 10</dd></dl></div>
      <div class="b">${th('mug', { pg: 40 })}<button class="btn primary lg" style="width:100%;margin-top:12px">${ic('play')}Continue step 3 ${kbd('↩')}</button></div></div>
    <div class="sec" style="margin-top:26px">Steps<a style="font-weight:450">Passes when</a></div>
    ${st.map(([t, pass, s]) => `<div class="lrow next${s === 'c' ? ' cur' : ''}"><div class="nm">${s === 'd' ? gk : `<span class="ring${s === 'c' ? ' cur' : ''}"></span>`}<b style="${s === 'c' ? '' : s ? 'font-weight:500' : 'font-weight:450;color:var(--muted)'}">${t}</b></div><div class="r">${pass}</div><span></span></div>`).join('')}
    ${sec('What miyagi reads in Blender')}
    <div class="lrow next"><div class="nm"><b style="font-weight:500">Objects and their modifiers, materials and sizes</b></div><div class="r">Through the add-on</div><span></span></div>
    <div class="lrow next"><div class="nm"><b style="font-weight:500">Your screen</b></div><div class="r">Only to point at a button</div><span></span></div>`), { plan: 1 });
}

// ---------- Skills for a CAD learner: the same tree, another subject ----------
function skillsCad() {
  const p = PL('intro-cad');
  const st = { 'cad.navigate': 'm', 'cad.sketch': 'm', 'cad.constrain': 'm', 'cad.pad': 'pn' };
  const end = (x, H) => `<div class="proj" style="left:${x}px;top:${H / 2 - 74}px;width:168px;height:148px"><svg viewBox="0 0 160 90" style="width:100%;height:auto;display:block;border-radius:6px">${THUMB.part()}</svg><div class="pl">Project</div><b>${p.project.title}</b><div class="bar g" style="margin-top:auto"><i style="width:33%"></i></div></div>`;
  const tree = dag(p, st, { w: 1104, rh: 82, end: 168, endHtml: end, rows: { 'cad.pocket': 0, 'cad.fillet': 1, 'cad.pattern': 0, 'cad.parametric': 1, 'cad.export': 1, 'cad.navigate': 0.5, 'cad.sketch': 0.5, 'cad.constrain': 0.5, 'cad.pad': 0.5 } });
  const TG = [['cad.pad', '1 of 2 lessons', 'Add the hook', '20 min', 'p'], ['cad.pocket', 'Needs Pad', 'Sketch on a face and cut holes', '20 min', 'k'], ['cad.fillet', 'Needs Pad', 'Fillets and chamfers', '15 min', 'k'], ['cad.pattern', 'Needs Pockets', 'Mirror and pattern', '15 min', 'k'], ['cad.parametric', 'Needs Pockets and Fillets', 'Change a dimension', '15 min', 'k'], ['cad.export', 'Needs Changing sizes', 'Export an STL to print', '10 min', 'k']];
  const lab = id => (p.skills.find(s => s.id === id) || {}).label;
  const rows = TG.map(([id, stt, les, min, k], i) => `<tr class="${i === 0 ? 'cur' : 'dim'}"><td><div class="vt">${mk({ s: k, f: [1, 2] })}<b>${lab(id)}</b></div></td><td><span class="tag">cad</span></td><td>${stt}</td><td>${les}</td><td style="text-align:right">${min}</td></tr>`).join('');
  const head = `<div class="shead"><div class="titlerow"><h1>Skills</h1><div class="sp"></div><button class="btn primary">${ic('play')}Continue Pad ${kbd('↩')}</button></div>
    <div class="lede">Goal <b>${p.project.title}</b> · 3 of 9 skills · about 2 hours left, around Nov 29 at your pace · <a>Change</a></div>
    <div class="tabs"><b class="on">Path</b><b>Map</b><b>List</b><div class="sp"></div><div class="tbtn" style="margin-left:6px">${ic('search')}</div></div></div>`;
  return shell3('skills', ['Skills', 'Path'], skillsActs, head + `<div class="scroll"><div class="col wide" style="padding-top:44px">${tree}
    <div class="sec" style="margin-top:44px">Still to go</div><table class="tbl"><tr><th>Skill</th><th>Track</th><th>Status</th><th>Lesson</th><th style="text-align:right">Time</th></tr>${rows}</table></div></div>`,
    { plans: [['Intro to CAD', '4 of 10']], plan: -1, recent: [['c', 'Add the hook'], ['d', 'Pad it into a plate'], ['d', 'Constrain it fully']] });
}

Object.assign(SCREENS, { home: home3, progress: progress3, settings: settings3, 'settings-apps': settingsApps, 'settings-data': settingsData, library: library3,
  plans: plans3, plan: plan3, 'plan-playlist': planPlaylist, 'plan-goal': planGoal, 'lesson-blender': lessonBlender, 'skills-cad': skillsCad });
RENDER();

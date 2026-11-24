// v4 (Nov 23): fuller pages, 1040 px wide. Home and Progress are two columns (the work on the left, the numbers
// in a rail on the right); Settings is two columns of groups; Library and Plans use the full width; first run shows
// plans and lessons to start. Loaded after v3.js. Same rules as v3 otherwise: no tiles, no extra hues, rows and hairlines.
// These are the live pages: the plain screen names (home, progress, ...) load them. The Nov 22 one-column pages
// stay under <name>-v3.
const weekMini = () => {
  const D = [['M', 0], ['T', 22], ['W', 41], ['T', 0], ['F', 18], ['S', 12], ['S', 15]], W = 284, H = 96, base = 70, top = 16, max = 45, bw = 26, gap = (W - 7 * bw) / 6;
  let s = `<path d="M0 ${base}H${W}" stroke="var(--hair2)"/>`;
  D.forEach(([d, m], i) => {
    const x = i * (bw + gap), h = m / max * (base - top), today = i === 6;
    s += m ? `<path d="M${x} ${base}V${base - h + 3}a3 3 0 0 1 3-3h${bw - 6}a3 3 0 0 1 3 3V${base}z" fill="${today ? 'var(--ink)' : 'var(--ghost)'}"/>` : `<rect x="${x}" y="${base - 2}" width="${bw}" height="2" fill="var(--track)"/>`;
    if (m) s += `<text class="v${today ? ' on' : ''}" x="${x + bw / 2}" y="${base - h - 5}" text-anchor="middle">${m}</text>`;
    s += `<text class="${today ? 'on' : ''}" x="${x + bw / 2}" y="${base + 17}" text-anchor="middle">${d}</text>`;
  });
  return `<div class="wk"><svg viewBox="0 0 ${W} ${H}">${s}</svg></div>`;
};
const planCard = id => { const p = PL(id); return `<div class="pc">${th(COVER[id] || 'code')}<b>${p.title}</b><span>${p.tool.label} · ${p.lessons.length} lessons · about ${hrs(p.minutes)}</span></div>`; };
const PASSED = [['Today, 4:12 PM', 'Add one row to every row', 'Broadcasting', 'numpy for networks'], ['Today, 4:03 PM', 'Shapes and axes', 'Broadcasting', 'numpy for networks'],
  ['Yesterday', 'With numpy', 'Dot product', 'The dot product'], ['Wednesday', 'Slice rows and columns', 'Indexing', 'numpy for networks'], ['Tuesday', 'Scale the mug on one axis', 'Transforms', 'Move, rotate and scale']];

// ---------- Home, fuller ----------
function homeFull() {
  const plan = (t, d, n, next) => `<div class="lrow plan"><div class="nm"><b>${t}</b></div>${pbar(d, n)}<div class="m">Next · ${next}</div>${chevRow}</div>`;
  const nx = (k, t, grows, meta) => `<div class="lrow nx4"><div class="nm">${th(k)}<b>${t}</b></div><span class="tag">${grows}</span><div class="r">${meta}</div>${chevRow}</div>`;
  const TR = [['python', 4, 4], ['numpy', 2, 3], ['math', 2, 3], ['pandas', 2, 4], ['plotting', 1, 4], ['neural networks', 0, 3]];
  const key = (l, k) => `<div class="rrow"><span class="l" style="font-weight:450;color:var(--text)">${l}</span>${kbd(k)}</div>`;
  const main = `<div>
    <div class="hello"><h1>Good evening, Sam</h1><span>Sunday, November 22</span></div>
    <div class="lede">1 h 48 min this week. About 3 hours to <b>Fit sin(x) with a network</b>.</div>
    <div style="margin-top:8px">${askField()}</div>
    <div style="margin-top:14px">${contCard().replace('Continue · Step 4 of 7', 'Step 4 of 7')}</div>
    ${sec('Plans', 'Browse plans')}
    ${plan('Neural networks from scratch', 3, 8, 'Broadcasting')}${plan('Intro to Blender', 1, 10, 'Move, rotate and scale')}
    ${sec('Up next', 'Library')}
    ${nx('plot', 'Plot your data with matplotlib', 'Line plots', 'Jupyter · 6 steps · 15 min')}${nx('nb', 'Matrices as layers', 'Matrices', 'Jupyter · 5 steps · 25 min')}
    ${nx('table', 'Summarize sales with pandas', 'groupby', 'Jupyter · 6 steps · 20 min')}${nx('mug', 'Add a modifier', 'Modifiers', 'Blender · 5 steps · 15 min')}
    ${sec('Start a plan', `All ${CAT.length} plans`)}
    <div class="grid3">${planCard('pandas')}${planCard('plotting')}${planCard('intro-cad')}</div>
    ${sec('Recently passed', 'Progress')}
    <table class="tbl sm"><tr><th style="width:132px">When</th><th>Step</th><th>Skill</th></tr>
      ${PASSED.map(r => `<tr><td class="mu nw">${r[0]}</td><td><div class="vt">${gk}<b>${r[1]}</b></div></td><td><span class="tag">${r[2]}</span></td></tr>`).join('')}</table>
    <div style="height:60px"></div></div>`;
  const rail = `<div class="rail">
    ${sec('This week', 'Progress')}
    ${weekMini()}
    <div class="stats sm"><div><b>1<small>h</small> 48<small>min</small></b><span>practiced</span></div><div><b>6</b><span>steps passed</span></div><div><b>5</b><span>days of 7</span></div></div>
    ${sec('Goal')}
    <div class="goal"><div class="nm">${ic('flag')}<b>Fit sin(x) with a network</b></div><div class="bar"><i style="width:${8 / 13 * 100}%"></i></div><div class="m"><span>8 of 13 skills</span><span>about 3 hours left</span></div></div>
    ${sec('Skills', '11 of 20 mastered')}
    ${TR.map(([t, d, n]) => `<div class="rrow"><span class="l">${t}</span><div class="bar g"><i style="width:${d / n * 100}%"></i></div><span class="r n">${d} of ${n}</span></div>`).join('')}
    ${sec('Keep fresh', '4 min')}
    <div class="rrow">${ic('refresh')}<span class="l">Functions</span><span class="r">12 days ago</span></div>
    <div class="rrow">${ic('refresh')}<span class="l">DataFrames</span><span class="r">9 days ago</span></div>
    ${sec('Keys')}
    ${key('Ask miyagi', '⌥ Space')}${key('Explain this step', '⌥ E')}${key('Hint', '⌥ H')}${key('Show me', '⌥ S')}
  </div>`;
  return shell3('home', ['Home'], '', `<div class="scroll"><div class="dash">${main}${rail}</div></div>`);
}

// ---------- Library, fuller ----------
function libraryFull() {
  const NN = 'Neural networks', BL = 'Intro to Blender';
  const IN = [['net', 'Code your first neural network', NN, 'Jupyter', 'Single neuron|Layers', 25, [4, 7], 'Today'], ['mug', 'Move, rotate and scale', BL, 'Blender', 'Transforms', 15, [2, 6], 'Today'],
    ['table', 'Clean a CSV with pandas', '', 'Jupyter', 'Cleaning rows', 20, [3, 6], 'Yesterday'], ['code', 'numpy for networks', NN, 'VS Code', 'Broadcasting', 20, [3, 4], 'Yesterday']];
  const RD = [['plot', 'Plot your data with matplotlib', '', 'Jupyter', 'Line plots', 15, [0, 6], ''], ['nb', 'Matrices as layers', NN, 'Jupyter', 'Matrices', 25, [0, 5], ''],
    ['table', 'Summarize sales with pandas', '', 'Jupyter', 'groupby', 20, [0, 6], ''], ['mug', 'Add a modifier', BL, 'Blender', 'Modifiers', 15, [0, 5], ''], ['term', 'Set up a Python environment', '', 'Terminal', 'Running a script', 10, [0, 5], '']];
  const FN = [['nb', 'The dot product', NN, 'Jupyter', 'Dot product', 15, 'done', 'Nov 21'], ['code', 'numpy arrays from scratch', NN, 'Jupyter', 'Arrays|Indexing', 15, 'done', 'Nov 20'],
    ['mug', 'Find your way around Blender', BL, 'Blender', 'Viewport', 10, 'done', 'Nov 19'], ['code', 'Write your first Python program', '', 'VS Code', 'Functions', 15, 'done', 'Nov 12']];
  const cols = '<colgroup><col><col class="c-plan"><col class="c-tool"><col class="c-grow"><col class="c-time"><col class="c-prog"><col class="c-when"></colgroup>';
  const row = ([k, t, pl, tool, grows, min, pr, when]) => `<tr><td><div class="vt">${th(k)}<b>${t}</b></div></td><td class="mu">${pl}</td><td class="mu">${tool}</td><td>${grows.split('|').map(g => `<span class="tag">${g}</span>`).join(' ')}</td><td class="mu">${min} min</td>
    <td>${pr === 'done' ? `<span class="vt" style="gap:7px;font-size:13px;color:var(--muted)">${gk}Passed</span>` : pr[0] ? pbar(pr[0], pr[1]) : '<span style="color:var(--muted);font-size:13px">Ready</span>'}</td><td class="r mu">${when}</td></tr>`;
  const table = (rows, head) => `<table class="tbl fx">${cols}${head ? '<tr><th>Lesson</th><th>Plan</th><th>Works in</th><th>Grows</th><th>Time</th><th>Progress</th><th class="r">Opened</th></tr>' : ''}${rows.map(row).join('')}</table>`;
  const plan = (cover, t, d, n, next, left) => `<div class="lc" style="display:flex;gap:14px;align-items:center">${th(cover, { style: 'width:132px;flex:none;margin:0' })}<div style="min-width:0;flex:1"><b>${t}</b><span>Next · ${next}</span><span>${left}</span><div style="margin-top:9px">${pbar(d, n)}</div></div></div>`;
  const n = IN.length + RD.length + FN.length;
  return shell3('library', ['Library'], '', page(`
    <div class="titlerow"><h1>Library</h1><div class="sp"></div><button class="btn quiet">${ic('list')}New plan</button><button class="btn primary">${ic('compose')}New lesson</button></div>
    <div class="lede">${n} lessons, 2 plans. ${IN.length} in progress, ${RD.length} ready to start, ${FN.length} finished.</div>
    <div class="tabs"><b class="on">All<span class="cnt" style="margin-left:0">${n}</span></b><b>In progress<span class="cnt" style="margin-left:0">${IN.length}</span></b><b>Ready<span class="cnt" style="margin-left:0">${RD.length}</span></b><b>Finished<span class="cnt" style="margin-left:0">${FN.length}</span></b><b>Plans<span class="cnt" style="margin-left:0">2</span></b><div class="sp"></div><div class="tbtn">${ic('grid')}</div><div class="tbtn">${ic('search')}</div></div>
    ${sec('Your plans', 'Browse plans').replace('class="sec"', 'class="sec" style="margin-top:22px"')}
    <div class="grid2">${plan('net', 'Neural networks from scratch', 3, 8, 'Broadcasting', '5 lessons left · about 2 hr')}${plan('mug', 'Intro to Blender', 1, 10, 'Move, rotate and scale', '9 lessons left · about 2.5 hr')}</div>
    ${sec(`In progress<span class="cnt">${IN.length}</span>`)}${table(IN, true)}
    ${sec(`Ready to start<span class="cnt">${RD.length}</span>`)}${table(RD)}
    ${sec(`Finished<span class="cnt">${FN.length}</span>`)}${table(FN)}
    ${sec('Start a plan', `All ${CAT.length} plans`)}
    <div class="grid4">${planCard('pandas')}${planCard('plotting')}${planCard('intro-cad')}${planCard('intro-javascript')}</div>
    <div style="height:60px"></div>`).replace('class="col"', 'class="col w2"'));
}

// ---------- charts at the width of the main column ----------
const bars = (D, o) => {
  const { W, H, base, top = 18, max, bw, goal, goalLabel, on, labels = {}, values = () => false } = o, gap = (W - D.length * bw) / (D.length - 1);
  let s = `<path d="M0 ${base}H${W}" stroke="var(--hair2)"/>`;
  if (goal) { const y = base - goal / max * (base - top); s += `<path d="M0 ${y}H${W}" stroke="var(--hair)" stroke-dasharray="2 4"/><text x="${o.goalLeft ? 0 : W}" y="${y - 5}" text-anchor="${o.goalLeft ? 'start' : 'end'}">${goalLabel}</text>`; }
  D.forEach((m, i) => {
    const x = i * (bw + gap), h = m / max * (base - top), now = i === on;
    s += m ? `<path d="M${x} ${base}V${base - h + 4}a4 4 0 0 1 4-4h${bw - 8}a4 4 0 0 1 4 4V${base}z" fill="${now ? 'var(--ink)' : 'var(--ghost)'}"/>` : `<rect x="${x}" y="${base - 2}" width="${bw}" height="2" fill="var(--track)"/>`;
    if (m && values(i, m)) s += `<text class="v${now ? ' on' : ''}" x="${x + bw / 2}" y="${base - h - 7}" text-anchor="middle">${values(i, m)}</text>`;
    if (labels[i]) s += `<text class="${now ? 'on' : ''}" x="${x + bw / 2}" y="${base + 18}" text-anchor="middle">${labels[i]}</text>`;
  });
  return `<div class="wk"><svg viewBox="0 0 ${W} ${H}">${s}</svg></div>`;
};
const weekBig = (D = [0, 22, 41, 0, 18, 12, 15], low) => bars(D, { W: 684, H: low ? 96 : 150, base: low ? 66 : 120, max: 45, bw: 60, goal: 30, goalLabel: '30 min', on: 6, labels: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'], values: (i, m) => m });
const weeks12 = () => bars([0, 35, 62, 48, 90, 75, 110, 84, 96, 130, 121, 108], { W: 684, H: 122, base: 92, max: 140, bw: 40, goal: 120, goalLabel: '2 hr', goalLeft: true, on: 11, labels: { 0: 'Sep 6', 4: 'Oct 4', 8: 'Nov 1', 11: 'Now' }, values: (i, m) => i === 11 || i === 9 ? m : '' });
const railTree = () => bonsai().replace(/<text[\s\S]*?<\/text>/g, '').replace(/<circle[^>]*stroke-dasharray[^>]*\/>/g, '').replace('viewBox="0 0 640 400" style="width:640px;height:400px;display:block;margin:0 auto"', 'viewBox="170 24 300 366" style="width:148px;height:180px"');
const noPlans = h => h.replace(/<div class="slabel">Plans[\s\S]*?<div class="grow">/, '<div class="grow">');
const planCardEnd = id => { const p = PL(id); return `<div class="pc">${th(COVER[id] || 'code')}<b>${p.title}</b><span>${p.tool.label} · ${p.lessons.length} lessons · about ${hrs(p.minutes)}</span><span>Ends with ${p.project.title.charAt(0).toLowerCase() + p.project.title.slice(1)}</span></div>`; };
const KEYS = () => { const key = (l, k) => `<div class="rrow"><span class="l" style="font-weight:450;color:var(--text)">${l}</span>${kbd(k)}</div>`; return key('Ask miyagi', '⌥ Space') + key('Explain this step', '⌥ E') + key('Hint', '⌥ H') + key('Show me', '⌥ S'); };
const quietLink = h => h.replace(/<a>([^<]*)<svg[\s\S]*?<\/a>/, '<a style="color:var(--faint)">$1</a>');

// ---------- Progress, fuller ----------
function progressFull() {
  const T = [['python', 4, 4, '', 'Nov 12'], ['numpy', 2, 3, 'Broadcasting', 'Today'], ['math', 2, 3, 'Matrices', 'Yesterday'], ['pandas', 2, 4, 'Cleaning rows', 'Nov 18'], ['plotting', 1, 4, 'Scatter plots', 'Nov 16'], ['neural networks', 0, 3, 'Needs Broadcasting and Matrices', '']];
  const R = PASSED.concat([['Tuesday', 'Move the mug with G', 'Transforms', 'Move, rotate and scale'], ['Nov 16', 'Label both axes', 'Line plots', 'Plot your data with matplotlib'], ['Nov 16', 'Plot a line from two lists', 'Line plots', 'Plot your data with matplotlib']]);
  const F = [['nb', 'The dot product', 'Neural networks', 'Dot product', 'Nov 21'], ['code', 'numpy arrays from scratch', 'Neural networks', 'Arrays, Indexing', 'Nov 20'], ['mug', 'Find your way around Blender', 'Intro to Blender', 'Viewport', 'Nov 19'], ['code', 'Write your first Python program', '', 'Functions', 'Nov 12']];
  const near = (t, d, n) => `<div class="rrow"><span class="l">${t}</span><div class="bar"><i style="width:${d / n * 100}%"></i></div><span class="r" style="width:74px;text-align:right">${d} of ${n} steps</span></div>`;
  const ms = (t, when) => `<div class="rrow">${gk}<span class="l">${t}</span><span class="r">${when}</span></div>`;
  const main = `<div>
    <div class="titlerow"><h1>Progress</h1><div class="sp"></div><button class="btn primary">${ic('play')}Continue Broadcasting ${kbd('↩')}</button></div>
    <div class="lede">11 of 20 skills mastered. About 3 hours to <b>Fit sin(x) with a network</b>, around Dec 4 at your pace.</div>
    ${quietLink(sec('This week', 'minutes a day'))}
    ${weekBig()}
    <div class="stats" style="margin-top:14px"><div><b>1<small>h</small> 48<small>min</small></b><span>practiced this week</span></div><div><b>6</b><span>steps passed</span></div><div><b>2</b><span>skills mastered</span></div><div><b>5</b><span>days of 7</span></div></div>
    ${quietLink(sec('Last 12 weeks', 'minutes a week'))}
    ${weeks12()}
    <div class="stats" style="margin-top:14px"><div><b>16<small>h</small> 39<small>min</small></b><span>practiced in all</span></div><div><b>58</b><span>steps passed</span></div><div><b>4</b><span>lessons finished</span></div><div><b>11</b><span>weeks of 12</span></div></div>
    ${sec('Tracks', 'Skills')}
    <table class="tbl sm"><tr><th>Track</th><th style="width:150px">Mastered</th><th>Next</th><th class="r">Last practiced</th></tr>
      ${T.map(([t, d, n, nx, last]) => `<tr><td><b class="t">${t}</b></td><td>${pbar(d, n, true)}</td><td class="${d === n || !d ? 'mu' : ''}">${d === n ? 'Done' : nx}</td><td class="r mu">${last}</td></tr>`).join('')}</table>
    ${sec('Recently passed', 'All 58')}
    <table class="tbl sm"><tr><th style="width:132px">When</th><th>Step</th><th>Skill</th><th>Lesson</th></tr>
      ${R.map(r => `<tr><td class="mu nw">${r[0]}</td><td><div class="vt">${gk}<b>${r[1]}</b></div></td><td><span class="tag">${r[2]}</span></td><td class="mu nw">${r[3]}</td></tr>`).join('')}</table>
    ${sec('Finished lessons', 'Library')}
    <table class="tbl sm"><tr><th>Lesson</th><th>Plan</th><th>Grew</th><th class="r">Finished</th></tr>
      ${F.map(([k, t, pl, g, w]) => `<tr><td><div class="vt">${th(k)}<b>${t}</b></div></td><td class="mu nw">${pl}</td><td class="mu nw">${g}</td><td class="r mu nw">${w}</td></tr>`).join('')}</table>
    <div style="height:60px"></div></div>`;
  const rail = `<div class="rail">
    <div class="grove" style="width:auto;margin-top:2px">${railTree()}<div>11 leaves, one for each skill</div></div>
    ${sec('Goal', 'Change')}
    <div class="goal"><div class="nm">${ic('flag')}<b>Fit sin(x) with a network</b></div><div class="bar"><i style="width:${8 / 13 * 100}%"></i></div><div class="m"><span>8 of 13 skills</span><span>around Dec 4</span></div></div>
    ${sec('Closest to mastered')}
    ${near('Matrices', 3, 5)}${near('Broadcasting', 2, 4)}${near('Cleaning rows', 1, 3)}
    ${sec('Plans', 'Browse plans')}
    <div class="rrow"><span class="l">Neural networks from scratch</span><span class="r">3 of 8</span></div><div class="rrow"><span class="l">Intro to Blender</span><span class="r">1 of 10</span></div>
    ${sec('Keep fresh', '4 min')}
    <div class="rrow">${ic('refresh')}<span class="l">Functions</span><span class="r">12 days ago</span></div><div class="rrow">${ic('refresh')}<span class="l">DataFrames</span><span class="r">9 days ago</span></div>
    ${sec('Milestones')}
    ${ms('10 skills mastered', 'Nov 21')}${ms('5 days in a row', 'Nov 21')}${ms('python track finished', 'Nov 12')}${ms('First lesson finished', 'Nov 10')}
  </div>`;
  return shell3('progress', ['Progress'], `<div class="tbtn">${ic('share')}Share</div>`, `<div class="scroll"><div class="dash">${main}${rail}</div></div>`);
}

// ---------- Settings, fuller: two columns of groups, every row a setting the app already has ----------
const setPage = (active, head, left, right) => shellSet(active, `<div class="scroll"><div class="col w2">${head}<div class="sgrid"><div>${left}</div><div>${right}</div></div><div style="height:60px"></div></div></div>`);
const shd = t => `<div class="shd">${t}</div>`;
const qb = t => `<button class="btn quiet sm">${t}</button>`;
function settingsFull() {
  return setPage('general', '<h1>General</h1>',
    `${shd('Appearance')}
    ${frow('Theme', '', seg3(['System', 'Light', 'Dark'], 0))}
    ${frow('Text size', '', seg3(['Small', 'Default', 'Large'], 1))}
    ${frow('Density', 'How much room each row gets.', seg3(['Comfortable', 'Compact'], 0))}
    ${frow('Compact sidebar', 'Icons only, until you hover.', tog(false))}
    ${frow('Reduce motion', '', tog(false))}
    ${shd('Startup')}
    ${frow('Open miyagi', 'From anywhere on this Mac.', `<span class="keys">${kbd('⌥')}${kbd('Space')}</span>`)}
    ${frow('Launch at login', 'miyagi waits in the pill until you need it.', tog(true))}
    ${frow('Start page', '', sel('Home'))}
    ${frow('Where miyagi lives', 'The notch, or under the menu bar.', sel('In the notch'))}
    ${shd('Language')}
    ${frow('Language', 'Lessons and the app. English for now.', sel('English'))}`,
    `${shd('Sound')}
    ${frow('Sounds', 'A soft tick when a step passes.', tog(true))}
    ${frow('Sound on the main button', '', tog(false))}
    ${frow('Read steps aloud', 'Uses the voice built into this Mac.', tog(false))}
    ${shd('Help as you learn')}
    ${frow('Show tips as you learn', '', tog(true))}
    ${frow('Show setup status', 'The Ready line at the foot of the sidebar.', tog(true))}
    ${frow('Reset onboarding tips', 'See the first-run tips again.', qb('Reset'))}
    ${shd('Updates')}
    ${frow('miyagi 0.9.2', 'Up to date. Checked today at 6:40 PM.', qb('Check for updates'))}
    ${frow('Update automatically', '', tog(true))}
    ${shd('Reset')}
    ${frow('Restore default settings', 'Your lessons and skills stay.', qb('Restore'))}`);
}
function settingsAppsFull() {
  const used = l => { const n = CAT.filter(p => p.tool.label === l).length; return n ? ` Used by ${n} ${n === 1 ? 'plan' : 'plans'}.` : ''; };
  const con = qb('Connect'), scr = '<span class="v">Screen only</span>', ok = okv('Connected');
  return setPage('apps', '<h1>Apps</h1><div class="lede">The apps miyagi can check your work in. Connected apps are read exactly. In the rest it looks at the window.</div>',
    `${shd('Code')}
    ${frow('VS Code', `Reads your files and the terminal.${used('VS Code')}`, ok)}
    ${frow('Jupyter', `Reads each cell and what it printed.${used('Jupyter')}`, ok)}
    ${frow('Terminal', `Reads commands and their output.${used('Terminal')}`, ok)}
    ${frow('Xcode', `miyagi looks at the window.${used('Xcode')}`, scr)}
    ${shd('Sheets and design')}
    ${frow('Excel', `miyagi looks at the window. It cannot read the file yet.${used('Excel')}`, scr)}
    ${frow('Google Sheets', `miyagi looks at the window.${used('Google Sheets')}`, scr)}
    ${frow('Figma', `miyagi looks at the window.${used('Figma')}`, scr)}`,
    `${shd('3D and CAD')}
    ${frow('Blender', `Reads your scene. Objects, modifiers, materials, lights. Blender 4.2 · add-on 1.0.${used('Blender')}`, ok)}
    ${frow('FreeCAD', `Reads your model. Sketches, constraints, features, dimensions.${used('FreeCAD')}`, con)}
    ${frow('Fusion', `Reads your timeline and bodies.${used('Fusion')}`, con)}
    ${frow('Onshape', `Reads your Part Studio after you sign in.${used('Onshape')}`, con)}
    ${shd('Games')}
    ${frow('Unity', `miyagi looks at the window.${used('Unity')}`, scr)}
    ${frow('Godot', `miyagi looks at the window.${used('Godot')}`, scr)}
    ${shd('Everything else')}
    ${frow('Any other app', 'Lessons still work. Checks use what is on screen.', scr)}`);
}
function settingsDataFull() {
  return setPage('data', '<h1>Your data</h1><div class="lede">What miyagi sees, what it keeps, and how to remove it.</div>',
    `${shd('During a lesson')}
    ${frow('What miyagi sees', 'Only the lesson window, and only while a lesson is running.', `<span class="v">See an example ${chevRow}</span>`)}
    ${frow('Screenshots', 'Used to check a step, then deleted. Never used to train models.', '<span class="v">Not kept</span>')}
    ${frow('Your code and files', 'Stay on this Mac. The step being checked is sent, nothing else.', '<span class="v">On this Mac</span>')}
    ${shd('On this Mac')}
    ${frow('Lesson folder', '~/miyagi · 14 lessons', qb('Open'))}
    ${frow('Lesson cache', 'Built lessons kept so they open fast. 212 MB.', qb('Clear'))}`,
    `${shd('Kept in your account')}
    ${frow('Lesson history and skills', '14 lessons, 11 skills, 58 passed steps.', qb('Download'))}
    ${frow('Export my progress', 'One file you can read or share.', qb('Export'))}
    ${frow('Clear lesson history', 'Your skills and plans start over.', qb('Clear'))}
    ${shd('Account')}
    ${frow('Signed in as', 'sam@example.com', '<span class="v">Free</span>')}
    ${frow('Delete my account', 'Removes your account and everything in it within 30 days.', qb('Delete account'))}`);
}

// ---------- first run: nothing learned yet, and still a lot to start from ----------
const FIRST = ['intro-python', 'intro-sheets', 'plotting', 'intro-blender', 'intro-terminal'];
const firstLesson = id => { const p = PL(id), l = p.lessons[0], sk = p.skills.find(s => s.id === l.grows[0]); return [COVER[id] || (id === 'intro-sheets' ? 'table' : 'code'), l.title, sk ? sk.label : '', `${p.tool.label} · ${l.steps} steps · ${l.minutes} min`]; };
const GOALS = [['Fit sin(x) with a network', '13 skills · about 6 hours'], ['A sales report from a CSV', '9 skills · about 4 hours'], ['A budget in Google Sheets', '8 skills · about 3 hours'], ['A 3D-printable part', '11 skills · about 5 hours']];
const goalRows = () => GOALS.map(([t, m]) => `<div class="rrow tall"><div class="l2"><b>${t}</b><span>${m}</span></div>${chevRow}</div>`).join('');
const nx4 = ([k, t, grows, meta]) => `<div class="lrow nx4"><div class="nm">${th(k)}<b>${t}</b></div><span class="tag">${grows}</span><div class="r">${meta}</div>${chevRow}</div>`;
function homeFirst() {
  const step = (n, t) => `<div class="rrow"><span class="num">${n}</span><span class="l" style="font-weight:450;color:var(--text)">${t}</span></div>`;
  const main = `<div>
    <div class="hello"><h1>Welcome, Sam</h1><span>Sunday, November 22</span></div>
    <div class="lede">Pick a plan, paste a video, or ask for anything you want to learn.</div>
    <div style="margin-top:8px">${askField().replace('Boolean masks in numpy', 'Clean a messy CSV with pandas').replace('groupby in pandas', 'Build a tiny web server').replace('Merge and join in pandas', 'Train an image classifier')}</div>
    ${sec('Start here', `All ${CAT.length} plans`)}
    <div class="grid3">${planCardEnd('intro-python')}${planCardEnd('intro-blender')}${planCardEnd('intro-cad')}</div>
    ${sec('Or one short lesson', 'Library')}
    ${FIRST.slice(0, 4).map(id => nx4(firstLesson(id))).join('')}
    ${sec('Make your own')}
    ${WAYS.replace('class="two"', 'class="two" style="margin-top:0"')}
    <div style="height:60px"></div></div>`;
  const rail = `<div class="rail">
    ${sec('Set up', '3 of 4')}
    <div class="rrow">${gk}<span class="l">Signed in</span><span class="r">sam@example.com</span></div>
    <div class="rrow">${gk}<span class="l">Screen Recording</span><span class="r">Granted</span></div>
    <div class="rrow"><span class="ring"></span><span class="l">Accessibility</span>${qb('Turn on')}</div>
    <div class="rrow">${gk}<span class="l">VS Code</span><span class="r">Found</span></div>
    ${sec('How a lesson works')}
    ${step(1, 'miyagi shows one step.')}${step(2, 'You do it in the real app.')}${step(3, 'It checks your work, then the next.')}
    ${sec('Pick a goal', 'Skills')}
    ${goalRows()}
    ${sec('Keys')}
    ${KEYS()}
  </div>`;
  return noPlans(shell3('home', ['Home'], '', `<div class="scroll"><div class="dash">${main}${rail}</div></div>`));
}
function libraryFirst() {
  const rows = FIRST.map(firstLesson);
  return noPlans(shell3('library', ['Library'], '', page(`
    <div class="titlerow"><h1>Library</h1><div class="sp"></div><button class="btn quiet">${ic('list')}New plan</button><button class="btn primary">${ic('compose')}New lesson</button></div>
    <div class="lede">Nothing here yet. Start a plan, try one lesson, or make your own.</div>
    ${WAYS}
    ${sec('Start a plan', `All ${CAT.length} plans`)}
    <div class="grid4">${['intro-python', 'intro-blender', 'intro-cad', 'intro-javascript', 'pandas', 'plotting', 'neural-networks', 'intro-terminal'].map(planCardEnd).join('')}</div>
    ${sec('Or one short lesson')}
    <table class="tbl"><tr><th>Lesson</th><th>Grows</th><th class="r">Works in</th></tr>
      ${rows.map(([k, t, g, m]) => `<tr><td><div class="vt">${th(k)}<b>${t}</b></div></td><td><span class="tag">${g}</span></td><td class="r mu nw">${m}</td></tr>`).join('')}</table>
    <div style="height:60px"></div>`).replace('class="col"', 'class="col w2"')));
}
function progressFirst() {
  const will = (t, d) => `<div class="lrow next" style="min-height:48px"><div class="nm"><b>${t}</b></div><div class="r">${d}</div><span></span></div>`;
  const main = `<div>
    <div class="titlerow"><h1>Progress</h1><div class="sp"></div><button class="btn primary">${ic('compose')}Start a lesson ${kbd('↩')}</button></div>
    <div class="lede">Nothing passed yet. Your first step starts the tree.</div>
    ${quietLink(sec('This week', 'minutes a day'))}
    ${weekBig([0, 0, 0, 0, 0, 0, 0], true)}
    ${sec('What fills this page')}
    ${will('This week', 'Minutes a day, against a 30 minute goal')}${will('Tracks', 'Skills mastered in each subject, and what comes next')}${will('Recently passed', 'Every step you pass, with the skill it grew')}${will('Milestones', 'First lesson, first track, days in a row')}
    ${sec('Start with ten minutes', 'Library')}
    ${FIRST.slice(0, 3).map(id => nx4(firstLesson(id))).join('')}
    <div style="height:60px"></div></div>`;
  const rail = `<div class="rail">
    <div class="grove" style="width:auto;margin-top:2px">${bonsai(true).replace('viewBox="0 0 640 400" style="width:640px;height:400px"', 'viewBox="220 262 200 124" style="width:200px;height:124px"')}<div>One leaf for each skill you master</div></div>
    ${sec('Pick a goal', 'Skills')}
    ${goalRows()}
    ${sec('Start a plan', `All ${CAT.length}`)}
    ${['intro-python', 'intro-blender', 'intro-cad'].map(id => { const p = PL(id); return `<div class="rrow"><span class="l">${p.title}</span><span class="r">${p.lessons.length} lessons</span></div>`; }).join('')}
  </div>`;
  return noPlans(shell3('progress', ['Progress'], '', `<div class="scroll"><div class="dash">${main}${rail}</div></div>`));
}

// ---------- Plans catalog at the wider width ----------
function plansFull(o = {}) {
  const T = [['All', CAT.length], ['Code', 0], ['Data', 0], ['AI', 0], ['3D', 0], ['CAD', 0], ['Design', 0], ['Tools', 0]];
  T.slice(1).forEach(t => { t[1] = CAT.filter(p => p.topic === t[0].toLowerCase()).length; });
  const table = (g, name) => { const rows = CAT.filter(p => p.group === g); if (!rows.length) return '';
    return `${sec(`${name}<span class="cnt">${rows.length}</span>`)}<table class="tbl sm fx"><tr><th style="width:232px">Plan</th><th style="width:124px">Works in</th><th class="r" style="width:62px">Lessons</th><th class="r" style="width:56px">Skills</th><th class="r" style="width:62px">Time</th><th style="padding-left:28px">Ends with</th><th style="width:236px">Starts with</th></tr>
      ${rows.map(p => `<tr><td><b class="t">${p.title}</b></td><td class="mu">${p.tool.label}</td><td class="r mu">${p.lessons.length}</td><td class="r mu">${p.skills.length}</td><td class="r mu">${hrs(p.minutes)}</td><td class="mu" style="padding-left:28px">${p.project.title}</td><td class="mu">${p.lessons[0].title}</td></tr>`).join('')}</table>`; };
  return shell3('library', ['Library', 'Browse plans'], '', `<div class="scroll"><div class="col w2">
    <h1>Plans</h1><div class="lede">A plan is a set of lessons in order that ends in something you made. ${CAT.length} plans, ${CAT.reduce((n, p) => n + p.lessons.length, 0)} lessons.</div>
    ${WAYS}
    <div class="tabs">${T.map(([t, n], i) => `<b class="${i === 0 ? 'on' : ''}">${t}<span class="cnt" style="margin-left:0">${n}</span></b>`).join('')}<div class="sp"></div><div class="tbtn">${ic('search')}</div></div>
    ${sec('Start here').replace('class="sec"', 'class="sec" style="margin-top:22px"')}
    <div class="grid4">${['intro-python', 'intro-blender', 'intro-cad', 'intro-javascript'].map(planCardEnd).join('')}</div>
    ${table('language', 'Coding languages')}${table('environment', 'Apps and tools')}${table('topic', 'Going further')}
    <div style="height:60px"></div></div>${o.after || ''}</div>`);
}

// ---------- make the fuller pages the live ones ----------
// The playlist and goal dialogs call plansPage() for the page behind them, so point that at the wide catalog too.
const plansPageV3 = plansPage;
plansPage = o => plansFull(o);
const LIVE = { home: homeFull, progress: progressFull, library: libraryFull, settings: settingsFull, 'settings-apps': settingsAppsFull, 'settings-data': settingsDataFull, plans: plansFull,
  'home-empty': homeFirst, 'library-empty': libraryFirst, 'progress-empty': progressFirst };
for (const k in LIVE) { SCREENS[k + '-v3'] = SCREENS[k]; SCREENS[k] = LIVE[k]; }
SCREENS['plans-v3'] = () => plansPageV3();
// the names used while these were drafts still work
Object.assign(SCREENS, { 'home-full': homeFull, 'library-full': libraryFull, 'progress-full': progressFull, 'settings-full': settingsFull, 'settings-apps-full': settingsAppsFull, 'settings-data-full': settingsDataFull,
  'home-first': homeFirst, 'library-first': libraryFirst, 'progress-first': progressFirst, 'plans-full': plansFull });
RENDER();

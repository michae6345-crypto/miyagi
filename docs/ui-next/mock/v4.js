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
  const main = `<div>
    <div class="hello"><h1>Good evening, Sam</h1><span>Sunday, November 22</span></div>
    <div style="margin-top:14px">${askField()}</div>
    <div style="margin-top:14px">${contCard().replace('Continue · Step 4 of 7', 'Step 4 of 7')}</div>
    ${sec('Plans', 'Browse plans')}
    ${plan('Neural networks from scratch', 3, 8, 'Broadcasting')}${plan('Intro to Blender', 1, 10, 'Move, rotate and scale')}
    ${sec('Up next', 'Library')}
    ${nx('plot', 'Plot your data with matplotlib', 'Line plots', 'Jupyter · 6 steps · 15 min')}${nx('nb', 'Matrices as layers', 'Matrices', 'Jupyter · 5 steps · 25 min')}
    ${nx('table', 'Summarize sales with pandas', 'groupby', 'Jupyter · 6 steps · 20 min')}${nx('mug', 'Add a modifier', 'Modifiers', 'Blender · 5 steps · 15 min')}
    ${sec('Recently passed', 'Progress')}
    <table class="tbl sm"><tr><th style="width:132px">When</th><th>Step</th><th>Skill</th></tr>
      ${PASSED.map(r => `<tr><td class="mu nw">${r[0]}</td><td><div class="vt">${gk}<b>${r[1]}</b></div></td><td><span class="tag">${r[2]}</span></td></tr>`).join('')}</table>
    <div style="height:60px"></div></div>`;
  const rail = `<div class="rail">
    ${sec('This week', 'Progress')}
    ${weekMini()}
    <div class="stats sm"><div><b>1<small>h</small> 48<small>min</small></b><span>practiced</span></div><div><b>6</b><span>steps passed</span></div><div><b>2</b><span>skills mastered</span></div></div>
    ${sec('Goal')}
    <div class="goal"><div class="nm">${ic('flag')}<b>Fit sin(x) with a network</b></div><div class="bar"><i style="width:${8 / 13 * 100}%"></i></div><div class="m"><span>8 of 13 skills</span><span>about 3 hours left</span></div></div>
    ${sec('Skills', '11 of 20 mastered')}
    ${TR.map(([t, d, n]) => `<div class="rrow"><span class="l">${t}</span><div class="bar g"><i style="width:${d / n * 100}%"></i></div><span class="r n">${d} of ${n}</span></div>`).join('')}
    ${sec('Keep fresh', '4 min')}
    <div class="rrow">${ic('refresh')}<span class="l">Functions</span><span class="r">12 days ago</span></div>
    <div class="rrow">${ic('refresh')}<span class="l">DataFrames</span><span class="r">9 days ago</span></div>
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
    <div class="tabs" style="margin-top:18px"><b class="on">All<span class="cnt" style="margin-left:0">${n}</span></b><b>In progress<span class="cnt" style="margin-left:0">${IN.length}</span></b><b>Ready<span class="cnt" style="margin-left:0">${RD.length}</span></b><b>Finished<span class="cnt" style="margin-left:0">${FN.length}</span></b><b>Plans<span class="cnt" style="margin-left:0">2</span></b><div class="sp"></div><div class="tbtn">${ic('grid')}</div><div class="tbtn">${ic('search')}</div></div>
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
const quietLink = h => h.replace(/<a>([^<]*)<svg[\s\S]*?<\/a>/, '<a style="color:var(--faint)">$1</a>');

// ---------- Progress, fuller ----------
function progressFull() {
  const T = [['python', 4, 4, '', 'Nov 12'], ['numpy', 2, 3, 'Broadcasting', 'Today'], ['math', 2, 3, 'Matrices', 'Yesterday'], ['pandas', 2, 4, 'Cleaning rows', 'Nov 18'], ['plotting', 1, 4, 'Scatter plots', 'Nov 16'], ['neural networks', 0, 3, 'Needs Broadcasting and Matrices', '']];
  const R = PASSED.concat([['Tuesday', 'Move the mug with G', 'Transforms', 'Move, rotate and scale'], ['Nov 16', 'Label both axes', 'Line plots', 'Plot your data with matplotlib'], ['Nov 16', 'Plot a line from two lists', 'Line plots', 'Plot your data with matplotlib']]);
  const near =(t, d, n) => `<div class="rrow"><span class="l">${t}</span><div class="bar"><i style="width:${d / n * 100}%"></i></div><span class="r" style="width:74px;text-align:right">${d} of ${n} steps</span></div>`;
  const main = `<div>
    <div class="titlerow"><h1>Progress</h1><div class="sp"></div><button class="btn primary">${ic('play')}Continue Broadcasting ${kbd('↩')}</button></div>
    <div class="lede">11 of 20 skills mastered.</div>
    ${quietLink(sec('This week', 'minutes a day'))}
    ${weekBig()}
    <div class="stats" style="margin-top:14px"><div><b>1<small>h</small> 48<small>min</small></b><span>practiced this week</span></div><div><b>6</b><span>steps passed</span></div><div><b>2</b><span>skills mastered</span></div></div>
    ${quietLink(sec('Last 12 weeks', 'minutes a week'))}
    ${weeks12()}
    <div class="stats" style="margin-top:14px"><div><b>16<small>h</small> 39<small>min</small></b><span>practiced in all</span></div><div><b>58</b><span>steps passed</span></div><div><b>4</b><span>lessons finished</span></div></div>
    ${sec('Tracks', 'Skills')}
    <table class="tbl sm"><tr><th>Track</th><th style="width:150px">Mastered</th><th>Next</th><th class="r">Last practiced</th></tr>
      ${T.map(([t, d, n, nx, last]) => `<tr><td><b class="t">${t}</b></td><td>${pbar(d, n, true)}</td><td class="${d === n || !d ? 'mu' : ''}">${d === n ? 'Done' : nx}</td><td class="r mu">${last}</td></tr>`).join('')}</table>
    ${sec('Recently passed', 'All 58')}
    <table class="tbl sm"><tr><th style="width:132px">When</th><th>Step</th><th>Skill</th><th>Lesson</th></tr>
      ${R.map(r => `<tr><td class="mu nw">${r[0]}</td><td><div class="vt">${gk}<b>${r[1]}</b></div></td><td><span class="tag">${r[2]}</span></td><td class="mu nw">${r[3]}</td></tr>`).join('')}</table>
    <div style="height:60px"></div></div>`;
  const rail = `<div class="rail">
    <div class="grove" style="width:auto;margin-top:2px">${railTree()}<div>11 leaves, one for each skill</div></div>
    ${sec('Goal', 'Change')}
    <div class="goal"><div class="nm">${ic('flag')}<b>Fit sin(x) with a network</b></div><div class="bar"><i style="width:${8 / 13 * 100}%"></i></div><div class="m"><span>8 of 13 skills</span><span>about 3 hours, around Dec 4</span></div></div>
    ${sec('Closest to mastered')}
    ${near('Matrices', 3, 5)}${near('Broadcasting', 2, 4)}${near('Cleaning rows', 1, 3)}
    ${sec('Plans', 'Browse plans')}
    <div class="rrow"><span class="l">Neural networks from scratch</span><span class="r">3 of 8</span></div><div class="rrow"><span class="l">Intro to Blender</span><span class="r">1 of 10</span></div>
    ${sec('Keep fresh', '4 min')}
    <div class="rrow">${ic('refresh')}<span class="l">Functions</span><span class="r">12 days ago</span></div><div class="rrow">${ic('refresh')}<span class="l">DataFrames</span><span class="r">9 days ago</span></div>
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
    ${frow('Where miyagi lives', 'The notch, or under the menu bar.', sel('In the notch'))}`,
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
  // "Screen only" on the right already says how the app is checked, so those rows carry only what uses them.
  const used = l => { const n = CAT.filter(p => p.tool.label === l).length; return n ? ` Used by ${n} ${n === 1 ? 'plan' : 'plans'}.` : ''; };
  const con = qb('Connect'), scr = '<span class="v">Screen only</span>', ok = okv('Connected');
  return setPage('apps', '<h1>Apps</h1><div class="lede">Connected apps are read exactly. In the rest miyagi looks at the window.</div>',
    `${shd('Code')}
    ${frow('VS Code', `Reads your files and the terminal.${used('VS Code')}`, ok)}
    ${frow('Jupyter', `Reads each cell and what it printed.${used('Jupyter')}`, ok)}
    ${frow('Terminal', `Reads commands and their output.${used('Terminal')}`, ok)}
    ${frow('Xcode', used('Xcode').trim(), scr)}
    ${shd('Sheets and design')}
    ${frow('Excel', used('Excel').trim(), scr)}
    ${frow('Google Sheets', used('Google Sheets').trim(), scr)}
    ${frow('Figma', used('Figma').trim(), scr)}`,
    `${shd('3D and CAD')}
    ${frow('Blender', `Reads your scene. Objects, modifiers, materials, lights. Blender 4.2 · add-on 1.0.${used('Blender')}`, ok)}
    ${frow('FreeCAD', `Reads your model. Sketches, constraints, features, dimensions.${used('FreeCAD')}`, con)}
    ${frow('Fusion', `Reads your timeline and bodies.${used('Fusion')}`, con)}
    ${frow('Onshape', `Reads your Part Studio after you sign in.${used('Onshape')}`, con)}
    ${shd('Games')}
    ${frow('Unity', used('Unity').trim(), scr)}
    ${frow('Godot', used('Godot').trim(), scr)}
    ${shd('Everything else')}
    ${frow('Any other app', 'Lessons still work.', scr)}`);
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
  const main = `<div>
    <div class="titlerow"><h1>Progress</h1><div class="sp"></div><button class="btn primary">${ic('compose')}Start a lesson ${kbd('↩')}</button></div>
    <div class="lede">Nothing passed yet. Your first step starts the tree.</div>
    ${quietLink(sec('This week', 'minutes a day'))}
    ${weekBig([0, 0, 0, 0, 0, 0, 0], true)}
    ${sec('Start with ten minutes', 'Library')}
    ${FIRST.slice(0, 4).map(id => nx4(firstLesson(id))).join('')}
    ${sec('Or start a plan', `All ${CAT.length} plans`)}
    <div class="grid3">${planCardEnd('intro-python')}${planCardEnd('intro-blender')}${planCardEnd('intro-cad')}</div>
    <div style="height:60px"></div></div>`;
  const rail = `<div class="rail">
    <div class="grove" style="width:auto;margin-top:2px">${bonsai(true).replace('viewBox="0 0 640 400" style="width:640px;height:400px"', 'viewBox="220 262 200 124" style="width:200px;height:124px"')}<div>One leaf for each skill you master</div></div>
    ${sec('Pick a goal', 'Skills')}
    ${goalRows()}
  </div>`;
  return noPlans(shell3('progress', ['Progress'], '', `<div class="scroll"><div class="dash">${main}${rail}</div></div>`));
}

// ---------- Plans catalog at the wider width ----------
function plansFull(o = {}) {
  const T = [['All', CAT.length], ['Code', 0], ['Data', 0], ['AI', 0], ['3D', 0], ['CAD', 0], ['Design', 0], ['Tools', 0]];
  T.slice(1).forEach(t => { t[1] = CAT.filter(p => p.topic === t[0].toLowerCase()).length; });
  // The last column is the plan to finish first, and only the "Going further" plans have one.
  const table = (g, name) => { const rows = CAT.filter(p => p.group === g); if (!rows.length) return '';
    const after = rows.some(p => p.needs.length);
    return `${sec(`${name}<span class="cnt">${rows.length}</span>`)}<table class="tbl sm fx"><tr><th style="width:${after ? 232 : 280}px">Plan</th><th style="width:${after ? 124 : 150}px">Works in</th><th class="r" style="width:62px">Lessons</th><th class="r" style="width:56px">Skills</th><th class="r" style="width:62px">Time</th><th style="padding-left:28px">Ends with</th>${after ? '<th style="width:200px">After</th>' : ''}</tr>
      ${rows.map(p => `<tr><td><b class="t">${p.title}</b></td><td class="mu">${p.tool.label}</td><td class="r mu">${p.lessons.length}</td><td class="r mu">${p.skills.length}</td><td class="r mu">${hrs(p.minutes)}</td><td class="mu" style="padding-left:28px">${p.project.title}</td>${after ? `<td class="mu">${p.needs.map(id => PL(id).title).join(', ')}</td>` : ''}</tr>`).join('')}</table>`; };
  return shell3('library', ['Library', 'Browse plans'], '', `<div class="scroll"><div class="col w2">
    <h1>Plans</h1><div class="lede">A plan is a set of lessons in order that ends in something you made.</div>
    ${WAYS}
    <div class="tabs">${T.map(([t, n], i) => `<b class="${i === 0 ? 'on' : ''}">${t}<span class="cnt" style="margin-left:0">${n}</span></b>`).join('')}<div class="sp"></div><div class="tbtn">${ic('search')}</div></div>
    ${sec('Start here').replace('class="sec"', 'class="sec" style="margin-top:22px"')}
    <div class="grid4">${['intro-python', 'intro-blender', 'intro-cad', 'intro-javascript'].map(planCardEnd).join('')}</div>
    ${table('language', 'Coding languages')}${table('environment', 'Apps and tools')}${table('topic', 'Going further')}
    <div style="height:60px"></div></div>${o.after || ''}</div>`);
}

// ---------- the pages behind the main ones, at the wider width ----------
const twoUp = (a, b) => `<div class="sgrid up2"><div>${a}</div><div>${b}</div></div>`;
const checkRows = list => list.map(c => `<div class="rrow"><span class="ring"></span><span class="l" style="font-weight:450;color:var(--text)">${c}</span></div>`).join('');
const okTag = t => `<span class="tag ok">${ic('check').replace('class="ic "', 'class="ic" style="width:12px;height:12px;stroke-width:2.4"')}${t}</span>`;
const planRow = id => { const q = PL(id); return `<div class="rrow"><span class="l">${q.title}</span><span class="r">${q.lessons.length} lessons · about ${hrs(q.minutes)}</span>${chevRow}</div>`; };

// a preset plan
function planFull() {
  const p = PL('intro-blender'), lab = id => (p.skills.find(s => s.id === id) || {}).label;
  const rows = p.lessons.map((l, i) => `<tr><td class="n">${i + 1}</td><td class="nw"><b class="t">${l.title}</b></td><td class="pw">${l.passes}</td><td>${l.grows.map(g => `<span class="tag">${lab(g)}</span>`).join(' ')}</td><td class="r mu">${l.steps}</td><td class="r mu nw">${l.minutes} min</td></tr>`).join('');
  const vids = p.playlists.map(pl => `<div class="rrow">${ic('yt')}<span class="l">${pl.title}</span><span class="r">${pl.channel} · ${pl.videoCount} videos</span>${chevRow}</div>`).join('');
  return shell3('library', ['Library', 'Browse plans', p.title], `<div class="tbtn">${ic('share')}Share</div>`, `<div class="scroll"><div class="col w2">
    <div class="split"><div class="a"><h1>${p.title}</h1><div class="lede">${p.line}</div>
      <dl class="props"><dt>${ic('tool')}Works in</dt><dd>Blender 4.2 or newer ${okTag('Connected')}</dd>
        <dt>${ic('list')}Length</dt><dd>${p.lessons.length} lessons · about ${hrs(p.minutes)}</dd>
        <dt>${ic('flag')}Ends with</dt><dd>${p.project.title}</dd>
        <dt>${ic('eye')}Checked by</dt><dd>Reading your scene through the miyagi add-on</dd>
        <dt style="align-self:start">${ic('skills')}Grows</dt><dd><div class="tags" style="padding:6px 0">${p.skills.map(s => `<span class="tag">${s.label}</span>`).join('')}</div></dd></dl></div>
      <div class="b" style="width:316px">${th('mug')}<button class="btn primary lg" style="width:100%;margin-top:12px">${ic('play')}Start plan ${kbd('↩')}</button></div></div>
    ${quietLink(sec(`Lessons<span class="cnt">${p.lessons.length}</span>`, `about ${hrs(p.minutes)}`))}
    <table class="tbl sm lsn"><tr><th></th><th>Lesson</th><th>Passes when</th><th style="width:150px">Grows</th><th class="r">Steps</th><th class="r">Time</th></tr>${rows}</table>
    ${twoUp(`${shd('The project')}<div class="pj"><b>${p.project.title}</b><p>${p.project.brief}</p></div>${checkRows(p.project.checks)}<div class="note">On your own, about 45 minutes.</div>`,
      `${shd('Rather follow a video')}${vids}${shd('After this plan')}${planRow('blender-materials')}${planRow('blender-animation')}`)}
    <div style="height:60px"></div></div></div>`, { plans: [MYPLANS[0]], recent: [['c', 'Code your first neural network'], ['c', 'Clean a CSV with pandas'], ['d', 'numpy arrays from scratch']] });
}

// a playlist as a plan
function courseFull() {
  const V = [['Vectors, the 5 minute version', 'Vectors', '6:12', 'd', 'plot', 4, 'Nov 18'], ['The dot product', 'Dot product', '9:40', 'd', 'code', 5, 'Nov 21'], ['numpy indexing', 'Indexing', '11:05', 'd', 'nb', 4, 'Wednesday'],
    ['Broadcasting', 'Broadcasting', '14:20', 'n', 'code', 4, 'Today'], ['Matrices as layers', 'Matrices', '12:48', '', 'nb', 5, ''], ['Build one neuron', 'Single neuron', '16:02', '', 'net', 6, ''],
    ['Stack neurons into layers', 'Layers', '18:30', '', 'net', 6, ''], ['Gradient descent from scratch', 'Gradient descent', '22:15', '', 'plot', 7, '']];
  const step = 104, x0 = 44; let strip = '';
  V.forEach((v, i) => {
    const x = x0 + i * step, n = { s: v[3] === 'd' ? 'm' : v[3] === 'n' ? 'p' : 'k', f: [2, 4] };
    if (i) strip += edge(`M${x - step} 40H${x}`, v[3] === 'd' ? 'done' : v[3] === 'n' ? 'open' : 'locked');
    V[i].svg = mark(n, x, 40, 13) + `<text x="${x}" y="76" text-anchor="middle" class="sub" ${v[3] === 'n' ? 'style="fill:var(--ink);font-weight:600"' : ''}>${v[1]}</text>`;
  });
  strip += edge(`M${x0 + 7 * step} 40H850`, 'locked') + V.map(v => v.svg).join('');
  const rows = V.map((v, i) => `<tr class="${v[3] === 'n' ? 'cur' : v[3] ? '' : 'dim'}"><td class="n">${i + 1}</td><td><div class="vt">${th(v[4])}<b>${v[0]}</b></div></td>
    <td><span class="tag">${v[1]}</span></td><td class="r mu">${v[5]}</td><td class="r mu">${v[2]}</td>
    <td style="padding-left:28px">${v[3] === 'd' ? `<span style="display:inline-flex;gap:7px;align-items:center">${gk}Done</span>` : v[3] === 'n' ? '<span class="tag ink">Next</span> <span style="color:var(--muted);font-size:13px;margin-left:4px">step 3 of 4</span>' : ''}</td><td class="r mu nw">${v[6]}</td></tr>`).join('');
  return shell3('library', ['Library', 'Neural networks from scratch'], `<div class="tbtn">${ic('share')}Share</div>`, `<div class="scroll"><div class="col w2">
    <div class="titlerow"><h1>Neural networks from scratch</h1><div class="sp"></div><button class="btn primary">${ic('play')}Continue video 4 ${kbd('↩')}</button></div>
    <div class="lede">Eight videos, each one a lesson. 3 done. About 2 hours left, around Dec 4 at your pace.</div>
    <div style="position:relative;height:92px;margin-top:26px"><svg viewBox="0 0 1040 92" style="position:absolute;inset:0;width:1040px;height:92px;overflow:visible">${strip}</svg>
      <div class="hero" style="left:850px;top:6px;width:190px;height:68px;padding:10px 14px;border-radius:12px;box-shadow:var(--e2)"><div class="eye">Project</div><div style="font-size:13.5px;font-weight:620;color:var(--ink);line-height:1.25;margin-top:2px">Fit sin(x) with a network</div></div></div>
    ${quietLink(sec(`Videos<span class="cnt">${V.length}</span>`, '1 h 51 min'))}
    <table class="tbl"><tr><th></th><th>Video</th><th style="width:170px">Grows</th><th class="r" style="width:60px">Steps</th><th class="r" style="width:70px">Length</th><th style="width:200px;padding-left:28px">Status</th><th class="r" style="width:100px">Opened</th></tr>${rows}</table>
    ${twoUp(`${shd('The project')}<div class="pj"><b>Fit sin(x) with a network</b><p>Build a two-layer network on your own and train it on 200 points of sin(x). Plot the fit over the points.</p></div>${checkRows(['The loss ends below 0.01', 'The plot shows the fit over the points', 'The training loop is your own code'])}<div class="note">Opens after video 8. About 45 minutes.</div>`,
      `${shd('Source')}<div class="rrow">${ic('yt')}<span class="l">YouTube playlist</span><span class="r">Open on YouTube</span>${chevRow}</div><div class="rrow">${ic('flag')}<span class="l">Ends with a project</span>${tog(true)}</div>${shd('After this plan')}${planRow('pytorch')}${planRow('scikit-learn')}`)}
    <div style="height:60px"></div></div></div>`, { plan: 0 });
}

// a lesson
function lessonWide(o) {
  const steps = o.steps.map(([t, pass, s, when]) => `<tr class="${s === 'c' ? 'cur' : ''}"><td class="nw"><div class="vt">${s === 'd' ? gk : `<span class="ring${s === 'c' ? ' cur' : ''}"></span>`}<b style="${s === 'c' ? '' : s ? 'font-weight:500' : 'font-weight:450;color:var(--muted)'}">${t}</b></div></td><td class="mu">${pass}</td><td class="r mu nw">${when || ''}</td></tr>`).join('');
  return shell3('library', o.crumbs, '', `<div class="scroll"><div class="col w2">
    <div class="split"><div class="a"><h1>${o.title}</h1><div class="lede">${o.line}</div><dl class="props">${o.props}</dl></div>
      <div class="b" style="width:316px">${o.cover}<button class="btn primary lg" style="width:100%;margin-top:12px">${ic('play')}${o.cta} ${kbd('↩')}</button></div></div>
    ${sec(`Steps<span class="cnt">${o.steps.length}</span>`)}
    <table class="tbl sm"><tr><th style="width:320px">Step</th><th>Passes when</th><th class="r" style="width:160px">You</th></tr>${steps}</table>
    ${twoUp(`${shd(o.readsTitle)}${o.reads.map(([a, b]) => frow(a, b, '')).join('')}`,
      `${shd('Grows')}${o.grows.map(([t, d, n]) => `<div class="rrow"><span class="l">${t}</span><div class="bar"><i style="width:${d / n * 100}%"></i></div><span class="r" style="width:74px;text-align:right">${d} of ${n} steps</span></div>`).join('')}${shd(o.nextTitle)}${o.next.map(([t, m]) => `<div class="rrow"><span class="l">${t}</span><span class="r">${m}</span>${chevRow}</div>`).join('')}`)}
    <div style="height:60px"></div></div></div>`, o.shell);
}
const lessonFull = () => lessonWide({
  crumbs: ['Library', 'Code your first neural network'], title: 'Code your first neural network', line: 'Train a small network to read handwritten digits, one step at a time.',
  props: `<dt>${ic('tool')}Works in</dt><dd>Jupyter ${okTag('Connected')}</dd><dt>${ic('list')}Length</dt><dd>7 steps · about 30 min</dd>
    <dt>${ic('skills')}Grows</dt><dd><div class="tags"><span class="tag">Single neuron</span><span class="tag">Layers</span></div></dd>
    <dt>${ic('yt')}From</dt><dd>YouTube · 24:10</dd><dt>${ic('eye')}Checked by</dt><dd>Reading each cell and what it printed</dd>`,
  cover: th('net', { dur: '24:10', pg: 50 }), cta: 'Continue step 4',
  steps: [['Load the digits', 'X has 1,797 rows and 64 columns', 'd', 'Today, 3:41 PM'], ['Split train and test', 'The test set holds 20 percent of the rows', 'd', 'Today, 3:48 PM'], ['Build the model', 'The model has an input, one hidden layer and an output', 'd', 'Today, 3:57 PM'],
    ['Train it', 'The loss falls for five epochs in a row', 'c', 'You are here'], ['Check the accuracy', 'Test accuracy is above 0.9', ''], ['Plot the loss', 'A line plot shows the loss for each epoch', ''], ['Save the model', 'The model file is saved next to the notebook', '']],
  readsTitle: 'What miyagi reads in Jupyter', reads: [['Each cell and what it printed', 'As text, through the notebook.'], ['The video', 'It pauses at each step until yours passes.'], ['Your screen', 'Only to point at a button.']],
  grows: [['Single neuron', 2, 4], ['Layers', 0, 3]], nextTitle: 'Up next', next: [['Plot your data with matplotlib', 'Jupyter · 15 min'], ['Matrices as layers', 'Jupyter · 25 min'], ['Summarize sales with pandas', 'Jupyter · 20 min']],
  shell: { lesson: 0 } });
const lessonBlenderFull = () => { const p = PL('intro-blender'); return lessonWide({
  crumbs: ['Library', 'Intro to Blender', 'Subdivision and smooth shading'], title: 'Subdivision and smooth shading', line: 'Make the mug smooth with a modifier, without adding a single vertex by hand.',
  props: `<dt>${ic('tool')}Works in</dt><dd>Blender ${okTag('Connected')}</dd><dt>${ic('list')}Length</dt><dd>5 steps · about 15 min</dd>
    <dt>${ic('skills')}Grows</dt><dd><div class="tags"><span class="tag">Modifiers</span></div></dd>
    <dt>${ic('eye')}Checked by</dt><dd>Reading your scene. No screenshots.</dd><dt>${ic('lib')}Plan</dt><dd>Intro to Blender · lesson 7 of 10</dd>`,
  cover: th('mug', { pg: 40 }), cta: 'Continue step 3',
  steps: [['Open your mug', 'mug.blend is open', 'd', 'Today, 2:10 PM'], ['Add a Subdivision Surface modifier', 'The mug has a Subdivision modifier', 'd', 'Today, 2:14 PM'], ['Set the viewport level to 2', 'Levels Viewport is 2', 'c', 'You are here'], ['Shade smooth', 'Smooth shading is on', ''], ['Save the file', 'The file is saved', '']],
  readsTitle: 'What miyagi reads in Blender', reads: [['Objects and their modifiers, materials and sizes', 'Through the add-on.'], ['Your screen', 'Only to point at a button.']],
  grows: [['Modifiers', 2, 5]], nextTitle: 'Next in this plan', next: p.lessons.slice(7, 10).map(l => [l.title, `${l.minutes} min`]),
  shell: { plan: 1 } }); };

// ---------- setup, wider: the step on the left, what it leads to on the right ----------
function flowWide(n, left, right) {
  const st = ['Sign in', 'Permissions', 'First lesson'];
  return `<div class="flow"><div class="lights"><i></i><i></i><i></i></div><div class="wide"><div>${left}</div><div class="rail2">${right}</div></div>
    <div class="steps">${st.map((t, i) => `<b class="${i === n ? 'on' : i < n ? 'done' : ''}">${i < n ? gk : ''}${t}</b>`).join('<i></i>')}</div></div>`;
}
const twoLine = (t, d, lead = '') => `<div class="rrow tall">${lead}<div class="l2"><b>${t}</b><span>${d}</span></div></div>`;
const numLine = (n, t, d) => twoLine(t, d, `<span class="num">${n}</span>`);
function onboard1Wide() {
  const tools = new Set(CAT.map(p => p.tool.label)).size, app = (t, d) => `<div class="rrow"><span class="l">${t}</span><span class="r">${d}</span></div>`;
  return flowWide(0, `<img src="${asset('tree-small')}" style="width:56px;height:56px"><h1 style="margin-top:18px">learn by doing.</h1><p>Setup takes about five minutes and ends inside your first lesson.</p>
    <button class="btn primary lg" style="margin-top:28px;width:280px">Continue with Google</button>
    <div style="font-size:12.5px;color:var(--faint);margin-top:14px">By continuing you agree to the terms and privacy policy.</div>`,
    `${sec('Works in', `${tools} apps`)}${app('VS Code', 'Reads your files and the terminal')}${app('Jupyter', 'Reads each cell')}${app('Blender', 'Reads your scene')}${app('FreeCAD', 'Reads your model')}
    ${sec('To learn', 'Browse')}${app('Plans', `${CAT.length}, each ending in a project`)}${app('Lessons', `${CAT.reduce((s, p) => s + p.lessons.length, 0)}`)}${app('Any YouTube video', 'Paste a link')}`);
}
function onboard2Wide() {
  return flowWide(1, `<h1>Let miyagi see your work</h1><p>It looks only while a lesson is running.</p>
    <div class="group" style="margin-top:26px">
      <div class="srow" style="min-height:60px"><div><div class="l">Screen Recording</div><div class="d">To check each step you do.</div></div><span class="sp"></span><span class="v" style="color:var(--green-text)">${gk}Granted</span></div>
      <div class="srow" style="min-height:60px"><div><div class="l">Accessibility</div><div class="d">To point at the right button.</div></div><span class="sp"></span><button class="btn primary">Open System Settings</button></div></div>`,
    `${sec('To turn on Accessibility')}${numLine(1, 'Open System Settings', 'The button on the left takes you there.')}${numLine(2, 'Privacy &amp; Security, then Accessibility', 'miyagi is in the list.')}${numLine(3, 'Switch miyagi on', 'Come back here. Nothing to restart.')}
    ${sec('What miyagi sees')}${twoLine('Only the lesson window', 'And only while a lesson is running.')}${twoLine('Screenshots', 'Used to check a step, then deleted.')}${twoLine('Your code and files', 'Stay on this Mac.')}`);
}
function onboard3Wide() {
  const ids = ['intro-python', 'intro-sheets', 'plotting'], p = PL(ids[0]), l = p.lessons[0], sk = p.skills.find(s => s.id === l.grows[0]);
  const c = (id, on) => { const [k, t, , m] = firstLesson(id); return `<div class="lc" style="padding:8px;border-radius:14px;${on ? 'box-shadow:0 0 0 2px var(--ink)' : ''}">${th(k)}<b>${t}</b><span>${m.split(' · ')[0]} · ${m.split(' · ')[2]}</span></div>`; };
  const row = (t, r) => `<div class="rrow"><span class="l">${t}</span><span class="r">${r}</span></div>`;
  return flowWide(2, `<h1>Pick your first lesson</h1><p>Each one is ten to fifteen minutes.</p>
    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:22px -8px 0">${ids.map((id, i) => c(id, i === 0)).join('')}</div>
    ${sec('Or start a plan', `All ${CAT.length}`)}${['intro-python', 'intro-blender', 'intro-cad'].map(id => { const q = PL(id); return row(q.title, `${q.lessons.length} lessons · about ${hrs(q.minutes)}`); }).join('')}
    <div style="font-size:12.5px;color:var(--faint);margin-top:14px">Or paste a YouTube link.</div>`,
    `${sec(l.title)}<div class="rrow"><span class="l">Works in</span><span class="r" style="display:inline-flex;align-items:center;gap:7px;color:var(--green-text)">${gk}${p.tool.label} found</span></div>
    ${row('Length', `${l.steps} steps · ${l.minutes} min`)}${row('Grows', sk ? sk.label : '')}${row('Plan', `${p.title} · lesson 1 of ${p.lessons.length}`)}
    ${twoLine('Passes when', l.passes)}
    <button class="btn primary lg" style="margin-top:22px;width:100%">Start lesson ${kbd('↩')}</button>
    <div style="font-size:12.5px;color:var(--faint);margin-top:12px">It opens ${p.tool.label} and shows the first step.</div>`);
}

// ---------- make the fuller pages the live ones ----------
// The playlist and goal dialogs call plansPage() for the page behind them, so point that at the wide catalog too.
const plansPageV3 = plansPage;
plansPage = o => plansFull(o);
const LIVE = { home: homeFull, progress: progressFull, library: libraryFull, settings: settingsFull, 'settings-apps': settingsAppsFull, 'settings-data': settingsDataFull, plans: plansFull,
  'home-empty': homeFirst, 'library-empty': libraryFirst, 'progress-empty': progressFirst,
  plan: planFull, course: courseFull, lesson: lessonFull, 'lesson-blender': lessonBlenderFull, 'onboard-1': onboard1Wide, 'onboard-2': onboard2Wide, 'onboard-3': onboard3Wide };
for (const k in LIVE) { SCREENS[k + '-v3'] = SCREENS[k]; SCREENS[k] = LIVE[k]; }
SCREENS['plans-v3'] = () => plansPageV3();
// the names used while these were drafts still work
Object.assign(SCREENS, { 'home-full': homeFull, 'library-full': libraryFull, 'progress-full': progressFull, 'settings-full': settingsFull, 'settings-apps-full': settingsAppsFull, 'settings-data-full': settingsDataFull,
  'home-first': homeFirst, 'library-first': libraryFirst, 'progress-first': progressFirst, 'plans-full': plansFull });
RENDER();

// apps (Nov 24): the apps miyagi teaches in, for MIC-87. Loaded last. It adds screens and changes none.
// A (recommended): on a new learner's Home the "Start here" section is one table, a row per app. A returning learner
//   gets the same list as a short block in the rail. A row opens the app's page (apps-app-*).
// B (alternative): one line of app names under the ask field, the same on both Homes. Home is otherwise unchanged.
// Names only: no third-party logos are drawn here. `mark` is the slot an owner's icon would take once its use is cleared.
// Note and the asks for the engine: ../apps/NOTE.md and ../apps/linear-MIC-87.md.
(() => {
  Object.assign(I, { ext: '<path d="M9 7h8v8M17 7 7 17"/>' });

  // ---------- the apps: name, what it is for, the plan a new learner starts with, where to get it ----------
  const APPS = {
    vscode: { n: 'VS Code', full: 'Visual Studio Code', kind: 'Code', start: 'intro-python', reads: 'Reading your files and what they print' },
    blender: { n: 'Blender', kind: '3D', start: 'intro-blender', ver: '4.2', reads: 'Reading your scene' },
    fusion: { n: 'Fusion', full: 'Autodesk Fusion', kind: 'CAD', start: 'intro-fusion', reads: 'Looking at the Fusion window' },
    freecad: { n: 'FreeCAD', kind: 'CAD', start: 'intro-cad', reads: 'Looking at the FreeCAD window' },
    onshape: { n: 'Onshape', kind: 'CAD', start: 'intro-onshape' },
    figma: { n: 'Figma', kind: 'Design', start: 'intro-figma' },
    sheets: { n: 'Google Sheets', kind: 'Sheets', start: 'intro-sheets' },
    excel: { n: 'Excel', kind: 'Sheets', start: 'intro-excel' },
    unity: { n: 'Unity', kind: 'Games', start: 'intro-unity' },
    godot: { n: 'Godot', kind: 'Games', start: 'intro-godot' }
  };
  // A state per app: on = installed, web = runs in the browser, get = not installed, soon = not supported yet.
  // Four apps (today), ten (the list grown), and a Mac with none of them. Today's list has no "Soon" line (Adrian,
  // Nov 24): it appears when an app is really coming, as on the ten-app screens.
  const ST4 = { vscode: 'on', blender: 'on', fusion: 'get', freecad: 'get' };
  const ST4_BACK = { vscode: 'on', blender: 'on', freecad: 'on', fusion: 'get' };
  const ST10 = { vscode: 'on', blender: 'on', figma: 'on', sheets: 'web', onshape: 'web', freecad: 'get', fusion: 'get', excel: 'get', unity: 'soon', godot: 'soon' };
  const ST_NONE = { vscode: 'get', blender: 'get', fusion: 'get', freecad: 'get' };
  const RANK = { on: 0, web: 1, get: 2, soon: 3 };
  const order = S => Object.keys(S).sort((a, b) => RANK[S[a]] - RANK[S[b]]);
  const live = S => order(S).filter(id => S[id] !== 'soon'), soon = S => order(S).filter(id => S[id] === 'soon');
  const plansIn = id => CAT.filter(p => p.tool.id === id);
  const COV = { ...COVER, 'intro-figma': 'web', 'intro-sheets': 'table', 'intro-excel': 'table', 'intro-fusion': 'part', 'intro-onshape': 'part' };
  const first = id => { const r = firstLesson(id); r[0] = COV[id] || 'code'; return nx4(r); };
  const mark = () => '';   // names only for now; see the note
  const ext = `<svg class="ic" viewBox="0 0 24 24">${I.ext}</svg>`;
  const stateCell = (id, s) => s === 'on' ? `<span class="ast">${gk}Installed</span>` : s === 'web' ? '<span class="ast q">In your browser</span>' : `<a class="ast">Get ${APPS[id].n}${ext}</a>`;

  // ---------- A: the table ----------
  function appsTable(S) {
    const row = id => { const a = APPS[id], n = plansIn(id).length - 1;
      return `<tr><td class="app">${mark(id)}<b>${a.n}</b></td><td class="mu">${a.kind}</td><td><b class="t">${PL(a.start).title}</b>${n > 0 ? `<span class="more">and ${n} more ${n === 1 ? 'plan' : 'plans'}</span>` : ''}</td><td>${stateCell(id, S[id])}</td><td class="go">${chevRow}</td></tr>`; };
    const later = soon(S);
    return `<table class="tbl apps"><tr><th class="c-app">App</th><th class="c-for">For</th><th>Start with</th><th class="c-mac">On this Mac</th><th class="c-go"></th></tr>
      ${live(S).map(row).join('')}${later.length ? `<tr class="soon"><td>Soon</td><td colspan="4">${later.map(id => APPS[id].n).join(', ')}</td></tr>` : ''}</table>`;
  }
  const chips = h => h.replace('Boolean masks in numpy', 'Clean a messy CSV with pandas').replace('groupby in pandas', 'Build a tiny web server').replace('Merge and join in pandas', 'Train an image classifier');
  const numStep = (n, t) => `<div class="rrow"><span class="num">${n}</span><span class="l" style="font-weight:450;color:var(--text)">${t}</span></div>`;

  // Home for a new learner. "Start here" (three plan cards, one per app) becomes the table, and the "VS Code · Found"
  // row leaves Set up, because the table says it for every app.
  function homeFirstA(S = ST4, short = ['intro-python', 'intro-javascript', 'intro-html-css', 'intro-blender']) {
    const main = `<div>
      <div class="hello"><h1>Welcome, Sam</h1><span>Sunday, November 22</span></div>
      <div class="lede">Pick a plan, paste a video, or ask for anything you want to learn.</div>
      <div style="margin-top:8px">${chips(askField())}</div>
      ${sec('Learn in', `All ${CAT.length} plans`)}
      ${appsTable(S)}
      ${sec('Or one short lesson', 'Library')}
      ${short.map(first).join('')}
      ${sec('Make your own')}
      ${WAYS.replace('class="two"', 'class="two" style="margin-top:0"')}
      <div style="height:60px"></div></div>`;
    const rail = `<div class="rail">
      ${sec('Set up', '2 of 3')}
      <div class="rrow">${gk}<span class="l">Signed in</span><span class="r">sam@example.com</span></div>
      <div class="rrow">${gk}<span class="l">Screen Recording</span><span class="r">Granted</span></div>
      <div class="rrow"><span class="ring"></span><span class="l">Accessibility</span>${qb('Turn on')}</div>
      ${sec('How a lesson works')}
      ${numStep(1, 'miyagi shows one step.')}${numStep(2, 'You do it in the real app.')}${numStep(3, 'It checks your work, then the next.')}
      ${sec('Pick a goal', 'Skills')}
      ${goalRows()}
    </div>`;
    return noPlans(shell3('home', ['Home'], '', `<div class="scroll"><div class="dash">${main}${rail}</div></div>`));
  }

  // Home for a returning learner: the list is one block at the foot of the rail. Used apps first, with the lessons
  // the learner has there; the rest name the plan they start with, or where to get the app. Never more than five rows.
  // The sample lessons on this page said "Jupyter"; here notebooks count as VS Code, the only editor the list names.
  const inVSCode = h => h.replace(/Jupyter · /g, 'VS Code · ');
  const MINE = { vscode: '10 lessons', blender: '3 lessons' };
  function railApps(S) {
    const ids = order(S).filter(id => S[id] !== 'soon'), used = ids.filter(id => MINE[id]), rest = ids.filter(id => !MINE[id]), show = [...used, ...rest].slice(0, 5);
    const right = id => MINE[id] ? `<span class="r">${MINE[id]}</span>` : S[id] === 'get' ? `<a class="r">Get ${APPS[id].n}${ext}</a>` : `<span class="r">${PL(APPS[id].start).title}</span>`;
    return `${sec('Learn in', ids.length > show.length ? `All ${Object.keys(S).length}` : '')}${show.map(id => `<div class="rrow">${mark(id)}<span class="l">${APPS[id].n}</span>${right(id)}</div>`).join('')}`;
  }
  const lastRail = '<span class="l">DataFrames</span><span class="r">9 days ago</span></div>';
  const put = (html, at, add, before) => { if (!html.includes(at)) throw new Error('apps.js: anchor not found: ' + at.slice(0, 40)); return html.replace(at, before ? add + at : at + add); };
  const homeBackA = (S = ST4_BACK) => put(inVSCode(SCREENS.home()), lastRail, railApps(S));

  // ---------- B: one line of names ----------
  function appLine(S) {
    const one = id => S[id] === 'get' ? `<b class="get">${mark(id)}${APPS[id].n}${ext}</b>` : `<b class="${S[id] === 'soon' ? 'soon' : ''}">${mark(id)}${APPS[id].n}</b>`;
    const later = soon(S);
    return `<div class="appline"><span class="k">Learn in</span>${live(S).map(one).join('')}${later.length ? `<span class="grp"><span class="k">Soon</span>${later.map(one).join('')}</span>` : ''}</div>`;
  }
  const homeFirstB = (S = ST4) => put(SCREENS['home-empty'](), '<div class="sec">Start here', appLine(S), true);
  const homeBackB = (S = ST4_BACK) => put(inVSCode(SCREENS.home()), '<div style="margin-top:14px"><div class="card cont">', appLine(S), true);

  // ---------- the page behind a row: the app, its first plan ready to start, and everything else in it ----------
  function appPage(id, s) {
    const a = APPS[id], all = plansIn(id), p = PL(a.start), rest = all.filter(q => q.id !== p.id), on = s === 'on';
    const lab = g => (p.skills.find(x => x.id === g) || {}).label;
    const lessons = all.reduce((n, q) => n + q.lessons.length, 0), mins = all.reduce((n, q) => n + q.minutes, 0);
    const rows = p.lessons.slice(0, 5).map((l, i) => `<tr><td class="n">${i + 1}</td><td class="nw"><b class="t">${l.title}</b></td><td class="pw">${l.passes}</td><td>${l.grows.map(g => `<span class="tag">${lab(g)}</span>`).join(' ')}</td><td class="r mu">${l.steps}</td><td class="r mu nw">${l.minutes} min</td></tr>`).join('');
    const after = rest.some(q => q.needs.length);
    const more = rest.length ? `${sec(`More in ${a.n}<span class="cnt">${rest.length}</span>`)}<table class="tbl sm fx"><tr><th style="width:${after ? 250 : 300}px">Plan</th><th class="r" style="width:62px">Lessons</th><th class="r" style="width:56px">Skills</th><th class="r" style="width:62px">Time</th><th style="padding-left:28px">Ends with</th>${after ? '<th style="width:200px">After</th>' : ''}</tr>
      ${rest.map(q => `<tr><td><b class="t">${q.title}</b></td><td class="r mu">${q.lessons.length}</td><td class="r mu">${q.skills.length}</td><td class="r mu">${hrs(q.minutes)}</td><td class="mu" style="padding-left:28px">${q.project.title}</td>${after ? `<td class="mu">${q.needs.map(n => PL(n).title).join(', ')}</td>` : ''}</tr>`).join('')}</table>` : '';
    const way = (icon, t, d) => `<div class="way">${ic(icon)}<div><b>${t}</b><span>${d}</span></div>${chevRow}</div>`;
    const side = on
      ? `<button class="btn primary lg" style="width:100%;margin-top:12px">${ic('play')}Start ${p.title} ${kbd('↩')}</button><div class="under">It opens ${a.n} and shows the first step.</div>`
      : `<div class="btnrow"><button class="btn primary lg">Get ${a.n}${ext.replace('class="ic"', 'class="ic" style="width:14px;height:14px"')}</button><button class="btn quiet lg">I have it</button></div><div class="under">miyagi finds ${a.n} once it is on this Mac.</div>`;
    return shell3('library', ['Library', 'Browse plans', a.n], '', `<div class="scroll"><div class="col w2">
      <div class="split"><div class="a apphead"><h1>${mark(id)}${a.full || a.n}</h1>
        <dl class="props"><dt>${ic('tool')}On this Mac</dt><dd>${on ? `${gk}Installed${a.ver ? ` · ${a.n} ${a.ver}` : ''}` : 'Not installed'}</dd>
          <dt>${ic('list')}To learn</dt><dd>${all.length} ${all.length === 1 ? 'plan' : 'plans'} · ${lessons} lessons · about ${hrs(mins)}</dd>
          <dt>${ic('eye')}Checked by</dt><dd>${a.reads}</dd>
          <dt>${ic('flag')}Starts with</dt><dd>${p.title}, which ends with ${p.project.title.charAt(0).toLowerCase() + p.project.title.slice(1)}</dd></dl></div>
        <div class="b" style="width:316px">${th(COV[p.id] || 'code')}${side}</div></div>
      ${sec(`${p.title}<span class="cnt">${p.lessons.length} lessons</span>`, 'The whole plan')}
      <table class="tbl sm lsn"><tr><th></th><th>Lesson</th><th>Passes when</th><th style="width:150px">Grows</th><th class="r">Steps</th><th class="r">Time</th></tr>${rows}</table>
      ${more}
      ${sec(`Make your own in ${a.n}`)}
      <div class="two" style="margin-top:0">${way('yt', 'From a video', `Paste any ${a.n} tutorial from YouTube`)}${way('sprout', 'From a goal', `Say what you want to make in ${a.n}`)}</div>
      <div style="height:60px"></div></div></div>`, { plans: [], recent: [] }).replace(/<div class="slabel">Plans[\s\S]*?<div class="grow">/, '<div class="grow">');
  }

  Object.assign(SCREENS, {
    'apps-home-first': () => homeFirstA(), 'apps-home-first-10': () => homeFirstA(ST10, ['intro-python', 'intro-blender', 'intro-figma', 'intro-sheets']), 'apps-home-first-none': () => homeFirstA(ST_NONE),
    'apps-home': () => homeBackA(), 'apps-home-10': () => homeBackA(ST10),
    'apps-app-blender': () => appPage('blender', 'on'), 'apps-app-vscode': () => appPage('vscode', 'on'), 'apps-app-fusion': () => appPage('fusion', 'get'),
    'apps-b-home-first': () => homeFirstB(), 'apps-b-home-first-10': () => homeFirstB(ST10), 'apps-b-home': () => homeBackB(), 'apps-b-home-10': () => homeBackB(ST10)
  });
  RENDER();
})();

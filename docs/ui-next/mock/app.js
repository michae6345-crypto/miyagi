// miyagi app mock: shell + pages. ?s=<screen>&t=light|dark&paper=white|cream
const q = new URLSearchParams(location.search);
const S = q.get('s') || 'home', T = q.get('t') || 'light', PAPER = q.get('paper') || 'white';
document.documentElement.className = T + ' paper-' + PAPER;
const dark = T === 'dark';
const asset = n => `assets/${n}${dark ? '-dark' : ''}.svg`;

const I = {
  search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  home: '<path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/>',
  lib: '<path d="M5 4v16M10 4v16M15 4.5l4.5 15"/>',
  skills: '<circle cx="6" cy="18.5" r="2"/><circle cx="18" cy="5.5" r="2"/><circle cx="6" cy="5.5" r="2"/><path d="M6 7.5v9M6 13c0-3 3-4 6-4h4"/>',
  progress: '<path d="M5 20v-7M12 20V5M19 20v-10"/>',
  settings: '<circle cx="12" cy="12" r="3"/><path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3M5.3 5.3l2.1 2.1M16.6 16.6l2.1 2.1M5.3 18.7l2.1-2.1M16.6 7.4l2.1-2.1"/>',
  compose: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/>',
  chev: '<path d="m9 6 6 6-6 6"/>',
  play: '<path d="M7 5v14l12-7z"/>',
  refresh: '<path d="M20 12a8 8 0 1 1-2.3-5.6"/><path d="M20 4v5h-5"/>',
  share: '<path d="M12 15V4M8 8l4-4 4 4M5 13v6h14v-6"/>',
  more: '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
  yt: '<rect x="3" y="6" width="18" height="12" rx="3"/><path d="m10.5 9.5 4 2.5-4 2.5z"/>',
  link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
  clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
  tool: '<rect x="3" y="5" width="18" height="14" rx="2.5"/><path d="m7.5 10 3 2.5-3 2.5M13 15h4"/>',
  list: '<path d="M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01"/>',
  flag: '<path d="M5 21V4M5 4h11l-2 4 2 4H5"/>',
  copy: '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>',
  down: '<path d="M12 4v12M7 11l5 5 5-5M5 20h14"/>',
  x: '<path d="M6 6l12 12M18 6 6 18"/>',
  peek: '<path d="m6 6 6 6-6 6M13 6l6 6-6 6"/>',
  sprout: '<path d="M12 21v-9M12 12c0-3.5-2.5-6-7-6 0 4 2.5 6 7 6ZM12 15c0-3 2.2-5 6.5-5 0 3.4-2.2 5-6.5 5Z"/>',
  check: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
  bars: '<path d="M4 7h16M4 12h10M4 17h13"/>'
};
const ic = (n, cls = '') => `<svg class="ic ${cls}" viewBox="0 0 24 24">${I[n]}</svg>`;
const gk = '<span class="gk"><svg viewBox="0 0 12 12"><path d="m2.6 6.3 2.3 2.3 4.6-4.9"/></svg></span>';
const kbd = t => `<kbd>${t}</kbd>`;

// ---------- video thumbnails (stand-ins for the real YouTube frame) ----------
const THUMB = {
  net: () => { let s = '<rect width="160" height="90" fill="#17181C"/>'; const L = [[36, [24, 45, 66]], [80, [16, 35, 54, 73]], [124, [34, 56]]];
    for (let i = 0; i < 2; i++) for (const a of L[i][1]) for (const b of L[i + 1][1]) s += `<path d="M${L[i][0]} ${a}L${L[i + 1][0]} ${b}" stroke="#5B606B" stroke-width=".7"/>`;
    for (const [x, ys] of L) for (const y of ys) s += `<circle cx="${x}" cy="${y}" r="5" fill="#E9EAEE"/>`; return s; },
  code: () => { let s = '<rect width="160" height="90" fill="#1D1F24"/><rect width="26" height="90" fill="#17181C"/>'; const c = ['#8FB4F2', '#C6A8F5', '#E7E8EC', '#9BD0A0', '#E7C48A'];
    [[0, 44], [1, 70], [2, 52], [2, 86], [1, 38], [0, 60], [2, 74], [1, 30]].forEach(([ind, w], i) => { s += `<rect x="${34 + ind * 10}" y="${12 + i * 9}" width="${w * .9}" height="3.6" rx="1.8" fill="${c[i % 5]}" opacity=".9"/>`; }); return s; },
  plot: () => { let s = '<rect width="160" height="90" fill="#FBFBF9"/><path d="M22 12V72H146" stroke="#C9C8C2" fill="none"/>', d = '';
    for (let i = 0; i <= 24; i++) { const x = 26 + i * 4.9, y = 60 - Math.pow(i / 24, 1.7) * 40 + Math.sin(i * 2.1) * 3; d += (i ? 'L' : 'M') + x.toFixed(1) + ' ' + y.toFixed(1); if (i % 3 === 0) s += `<circle cx="${x.toFixed(1)}" cy="${(y + Math.cos(i) * 7).toFixed(1)}" r="2" fill="#8C8B85"/>`; }
    return s + `<path d="${d}" fill="none" stroke="#2B2A27" stroke-width="1.8"/>`; },
  table: () => { let s = '<rect width="160" height="90" fill="#FFFFFF"/><rect width="160" height="16" fill="#EDEDE9"/>';
    for (let r = 0; r < 6; r++) for (let c = 0; c < 4; c++) s += `<rect x="${8 + c * 38}" y="${5 + r * 14}" width="${[22, 28, 18, 24][(r + c) % 4]}" height="4" rx="2" fill="${r ? '#C8C7C1' : '#8C8B85'}"/>`;
    for (let r = 1; r < 6; r++) s += `<path d="M0 ${16 + (r - 1) * 14 + 14}H160" stroke="#EFEFEB"/>`; return s; },
  term: () => { let s = '<rect width="160" height="90" fill="#121316"/>'; [[60, '#E7E8EC'], [96, '#8C8F98'], [44, '#9BD0A0'], [78, '#8C8F98'], [52, '#E7E8EC'], [30, '#9BD0A0']].forEach(([w, c], i) => { s += `<rect x="12" y="${14 + i * 11}" width="${w}" height="3.6" rx="1.8" fill="${c}"/>`; }); return s; },
  nb: () => { let s = '<rect width="160" height="90" fill="#FFFFFF"/><rect x="10" y="10" width="140" height="20" rx="3" fill="#F3F3F0"/><rect x="16" y="15" width="60" height="3.6" rx="1.8" fill="#8C8B85"/><rect x="16" y="22" width="88" height="3.6" rx="1.8" fill="#C8C7C1"/><rect x="10" y="36" width="140" height="44" rx="3" fill="#FAFAF8" stroke="#EFEFEB"/>', d = '';
    for (let i = 0; i <= 26; i++) d += (i ? 'L' : 'M') + (18 + i * 4.8).toFixed(1) + ' ' + (58 - Math.sin(i / 26 * 6.283) * 15).toFixed(1); return s + `<path d="${d}" fill="none" stroke="#2B2A27" stroke-width="1.6"/>`; }
};
function th(kind, o = {}) {
  return `<div class="th" ${o.style ? `style="${o.style}"` : ''}><svg viewBox="0 0 160 90" preserveAspectRatio="xMidYMid slice">${THUMB[kind]()}</svg>` +
    (o.dur ? `<span class="dur">${o.dur}</span>` : '') + (o.pg != null ? `<span class="pg"><i style="width:${o.pg}%"></i></span>` : '') + '</div>';
}

// ---------- shell ----------
function shell(active, crumbs, actions, body) {
  const nav = (id, icon, label, right = '') => `<div class="sr${active === id ? ' on' : ''}">${ic(icon)}<span class="t">${label}</span>${right ? `<span class="r">${right}</span>` : ''}</div>`;
  const page = (mark, label, right = '', on = false) => `<div class="sr${on ? ' on' : ''}"><span class="sdot">${mark}</span><span class="t">${label}</span>${right ? `<span class="r">${right}</span>` : ''}</div>`;
  const crumb = crumbs.map((c, i) => i === crumbs.length - 1 ? `<b>${c}</b>` : `${c}<i>/</i>`).join('');
  return `<div class="win">
  <aside class="side">
    <div class="ws"><img class="t" src="${asset('tree-small')}"><img class="w" src="${asset('wordmark')}"><div class="new">${ic('compose')}</div></div>
    ${nav('search', 'search', 'Search', '⌥ Space')}${nav('home', 'home', 'Home')}${nav('library', 'lib', 'Library')}${nav('skills', 'skills', 'Skills')}${nav('progress', 'progress', 'Progress')}
    <div class="slabel">Plans</div>
    ${page(ic('yt'), 'Neural networks from scratch', '3 of 8', active === 'course')}${page(ic('yt'), 'pandas in 10 videos', '0 of 10')}
    <div class="slabel">Recent</div>
    ${page('<span class="ring cur"></span>', 'Code your first neural network', '', active === 'lesson')}${page('<span class="ring cur"></span>', 'Clean a CSV with pandas')}${page(gk, 'numpy arrays from scratch')}
    <div class="grow"></div>
    ${nav('settings', 'settings', 'Settings')}
    <div class="acct"><div class="av">S</div><b>Sam Rivera</b><span>Free</span></div>
  </aside>
  <main class="main">
    <div class="top"><div class="crumb">${crumb}</div><div class="sp"></div>${actions || ''}<div class="tbtn">${ic('more')}</div></div>
    ${body}
  </main></div>`;
}
const page = (inner, wide) => `<div class="scroll"><div class="col${wide ? ' wide' : ''}">${inner}</div></div>`;
const lcard = (kind, title, meta, o = {}) => `<div class="lc">${th(kind, o)}<b>${title}</b><span>${meta}</span>${o.grows ? `<span class="grows">Grows ${o.grows}</span>` : ''}</div>`;
const chevRow = `<svg class="ic ch" viewBox="0 0 24 24">${I.chev}</svg>`;

// ---------- Home ----------
function contCard() {
  return `<div class="card cont">${th('net')}<div><div class="k">Continue · Step 4 of 7</div><h3>Code your first neural network</h3><div class="k">Train it</div></div><div class="sp"></div>
    <button class="btn primary lg">${ic('play')}Continue ${kbd('↩')}</button><div class="edge"><i style="width:50%"></i></div></div>`;
}
const askField = (value, chips = true) => `<div class="ask"><div class="f"><img src="${asset('tree-small')}">${value || 'ask miyagi, or paste a YouTube link'}<span class="sp"></span>${kbd('⌥ Space')}</div>
  ${chips ? `<div class="ch"><span class="chip sky">Boolean masks in numpy</span><span class="chip lilac">groupby in pandas</span><span class="chip pink">Merge and join in pandas</span></div>` : ''}</div>`;
function home() {
  return shell('home', ['Home'], '', page(`
    <div style="text-align:center;margin:10px 0 22px"><img src="${asset('tree-small')}" style="width:44px;height:44px"></div>
    ${contCard()}${askField()}
    <div class="sec">Up next<a>Library ${ic('chev')}</a></div>
    <div class="grid3">
      ${lcard('plot', 'Plot your data with matplotlib', 'Jupyter · 6 steps · 15 min', { dur: '18:20' })}
      ${lcard('net', 'Your first convolutional network', 'Jupyter · 8 steps · 30 min', { dur: '31:04' })}
      ${lcard('table', 'Summarize sales with pandas', 'Jupyter · 6 steps · 20 min', { dur: '22:47' })}
    </div>
    <div class="sec" style="margin-top:26px">Keep fresh</div>
    <div class="row">${ic('refresh')}<b>Functions, DataFrames</b><span class="m">2 skills · 4 min</span><span class="sp"></span>${chevRow}</div>`));
}
function homeLink() {
  const grow = new Set(['broad', 'mat', 'neuron', 'layers', 'gd']);
  const pop = `<div class="pop" style="position:absolute;left:50%;top:300px;width:740px;transform:translateX(-50%);padding:18px 20px;display:flex;gap:24px">
    <div style="width:250px;flex:none">
      ${th('net', { dur: '8 videos' })}
      <h2 style="font-size:17px;margin-top:12px">Neural networks from scratch</h2>
      <div class="lede" style="font-size:13px;margin-top:3px">YouTube playlist · about 3 h 20 min</div>
    </div>
    <div style="flex:1;min-width:0;display:flex;flex-direction:column">
      <div class="lab" style="margin:0 0 4px">Grows 5 skills and finishes your project</div>
      <svg viewBox="60 110 990 530" style="width:100%;height:170px;display:block">${miniMap(grow)}</svg>
      <div class="tags" style="margin-top:6px">${['Broadcasting', 'Matrices', 'Single neuron', 'Layers', 'Gradient descent'].map(t => `<span class="tag">${t}</span>`).join('')}</div>
      <div class="lede" style="font-size:13px;margin-top:10px">You already have 8 of the 13 skills it uses.</div>
      <div style="display:flex;gap:8px;margin-top:14px"><button class="btn primary">Add as a course ${kbd('↩')}</button><button class="btn quiet">Just the first video</button></div>
    </div></div>`;
  return shell('home', ['Home'], '', `<div class="scroll"><div class="col">
    <div style="text-align:center;margin:10px 0 22px"><img src="${asset('tree-small')}" style="width:44px;height:44px"></div>
    ${contCard()}
    <div class="ask" style="box-shadow:inset 0 0 0 1.5px var(--ink)"><div class="f">${ic('link')}<span class="v">youtube.com/playlist?list=PLZHQObOWTQDNU6R1_67000Dx_ZCJB-3pi<span class="caret"></span></span><span class="sp"></span>${kbd('↩')}</div></div>
    <div class="dim"><div class="sec">Up next</div><div class="grid3">${lcard('plot', 'Plot your data with matplotlib', 'Jupyter · 6 steps · 15 min')}${lcard('net', 'Your first convolutional network', 'Jupyter · 8 steps · 30 min')}${lcard('table', 'Summarize sales with pandas', 'Jupyter · 6 steps · 20 min')}</div></div>
  </div>${pop}</div>`);
}
function homeEmpty() {
  return shell('home', ['Home'], '', `<div class="scroll"><div class="col" style="padding-top:200px;text-align:center">
    <img src="${asset('tree-small')}" style="width:56px;height:56px">
    <h1 style="margin-top:18px">Learn anything by doing.</h1>
    <div style="text-align:left;margin-top:26px">${askField('ask miyagi, or paste a YouTube link', false)}</div>
    <div style="display:flex;gap:8px;justify-content:center;margin-top:14px"><span class="chip sky">Clean a messy CSV with pandas</span><span class="chip lilac">Build a tiny web server</span><span class="chip pink">Train an image classifier</span></div>
  </div></div>`).replace(/<div class="slabel">Plans[\s\S]*?<div class="grow">/, '<div class="grow">');
}

// ---------- Library ----------
function library() {
  const course = (kind, title, meta, pg, n) => `<div class="lc" style="display:flex;gap:14px;align-items:center">${th(kind, { style: 'width:150px;flex:none;margin:0', dur: n + ' videos' })}
      <div style="min-width:0;flex:1"><b>${title}</b><span>${meta}</span><div class="bar" style="margin-top:10px;width:150px"><i style="width:${pg}%"></i></div></div></div>`;
  return shell('library', ['Library'], '', page(`
    <div class="titlerow"><h1>Library</h1><div class="sp"></div><button class="btn primary">${ic('compose')}New lesson</button></div>
    <div class="tabs"><b class="on">All</b><b>In progress</b><b>Finished</b><b>Courses</b><div class="sp"></div><div class="tbtn">${ic('search')}</div></div>
    <div class="sec" style="margin-top:22px">Courses</div>
    <div class="grid2">${course('net', 'Neural networks from scratch', '3 of 8 done · next: Broadcasting', 38, 8)}${course('table', 'pandas in 10 videos', 'Not started', 0, 10)}</div>
    <div class="sec">In progress</div>
    <div class="grid3">
      ${lcard('net', 'Code your first neural network', 'Jupyter · step 4 of 7', { pg: 50, dur: '24:10' })}
      ${lcard('table', 'Clean a CSV with pandas', 'Jupyter · step 3 of 6', { pg: 42, dur: '16:32' })}
      ${lcard('code', 'numpy for networks', 'VS Code · step 3 of 4', { pg: 66, dur: '14:20' })}
    </div>
    <div class="sec">Ready to run</div>
    <div class="grid3">
      ${lcard('term', 'Set up a Python environment', 'Terminal · 5 steps · 10 min', { dur: '9:48' })}
      ${lcard('plot', 'Plot your data with matplotlib', 'Jupyter · 6 steps · 15 min', { dur: '18:20' })}
      ${lcard('nb', 'Your first convolutional network', 'Jupyter · 8 steps · 30 min', { dur: '31:04' })}
    </div>`));
}
function libraryEmpty() {
  return shell('library', ['Library'], '', `<div class="scroll"><div class="empty">${ic('lib', '').replace('class="ic "', 'class="ic" style="width:34px;height:34px;color:var(--faint);stroke-width:1.3"')}
    <h2>No lessons yet.</h2><p>Paste a YouTube link or ask for anything.</p><button class="btn primary lg">${ic('compose')}New lesson</button></div></div>`)
    .replace(/<div class="slabel">Plans[\s\S]*?<div class="grow">/, '<div class="grow">');
}

// ---------- Course (a playlist) ----------
function course() {
  const V = [['Vectors, the 5 minute version', 'Vectors', '6:12', 'd', 'plot'], ['The dot product', 'Dot product', '9:40', 'd', 'code'], ['numpy indexing', 'Indexing', '11:05', 'd', 'nb'],
    ['Broadcasting', 'Broadcasting', '14:20', 'n', 'code'], ['Matrices as layers', 'Matrices', '12:48', '', 'nb'], ['Build one neuron', 'Single neuron', '16:02', '', 'net'],
    ['Stack neurons into layers', 'Layers', '18:30', '', 'net'], ['Gradient descent from scratch', 'Gradient descent', '22:15', '', 'plot']];
  let strip = '';
  V.forEach((v, i) => {
    const x = 20 + i * 78, n = { s: v[3] === 'd' ? 'm' : v[3] === 'n' ? 'p' : 'k', f: [2, 4] };
    if (i) strip += edge(`M${x - 78} 46H${x}`, v[3] === 'd' ? 'done' : v[3] === 'n' ? 'open' : 'locked');
    V[i].svg = mark(n, x, 46, 13) + `<text x="${x}" y="82" text-anchor="middle" class="sub" ${v[3] === 'n' ? 'style="fill:var(--ink);font-weight:600"' : ''}>${i + 1}</text>`;
  });
  strip += edge('M566 46H612', 'locked') + V.map(v => v.svg).join('');
  const rows = V.map((v, i) => `<tr class="${v[3] === 'n' ? 'cur' : v[3] ? '' : 'dim'}"><td class="n">${i + 1}</td><td><div class="vt">${th(v[4])}<b>${v[0]}</b></div></td>
    <td><span class="tag">${v[1]}</span></td><td style="color:var(--muted)">${v[2]}</td>
    <td>${v[3] === 'd' ? `<span style="display:inline-flex;gap:7px;align-items:center">${gk}Done</span>` : v[3] === 'n' ? '<span class="tag ink">Next</span> <span style="color:var(--muted);font-size:13px;margin-left:4px">step 3 of 4</span>' : ''}</td></tr>`).join('');
  return shell('course', ['Library', 'Neural networks from scratch'], `<div class="tbtn">${ic('share')}Share</div>`, page(`
    <div class="titlerow"><h1>Neural networks from scratch</h1><div class="sp"></div><button class="btn primary">${ic('play')}Continue video 4 ${kbd('↩')}</button></div>
    <dl class="props">
      <dt>${ic('yt')}Source</dt><dd>YouTube playlist · 8 videos</dd>
      <dt>${ic('bars')}Progress</dt><dd>3 of 8 videos<span class="bar"><i style="width:38%"></i></span></dd>
      <dt>${ic('clock')}Time left</dt><dd>About 2 hours · around Dec 4 at your pace</dd>
    </dl>
    <div style="position:relative;height:96px;margin-top:14px"><svg viewBox="0 0 740 96" style="position:absolute;inset:0;width:740px;height:96px;overflow:visible">${strip}</svg>
      <div class="hero" style="left:612px;top:14px;width:128px;height:64px;padding:9px 12px;border-radius:12px;box-shadow:var(--e2)"><div class="eye">Project</div><div style="font-size:13px;font-weight:620;color:var(--ink);line-height:1.25;margin-top:1px">Fit sin(x) with a network</div></div></div>
    <table class="tbl" style="margin-top:6px"><tr><th></th><th>Video</th><th>Grows</th><th>Length</th><th style="width:170px">Status</th></tr>${rows}</table>`));
}

// ---------- Lesson preview ----------
function lesson() {
  const st = [['Load the digits', 'd'], ['Split train and test', 'd'], ['Build the model', 'd'], ['Train it', 'c'], ['Check the accuracy', ''], ['Plot the loss', '']];
  return shell('lesson', ['Library', 'Code your first neural network'], '', page(`
    <div style="display:flex;gap:24px;align-items:flex-start"><div style="flex:1;min-width:0">
      <h1>Code your first neural network</h1>
      <dl class="props"><dt>${ic('tool')}Tool</dt><dd>Jupyter</dd><dt>${ic('list')}Length</dt><dd>7 steps · about 30 min</dd>
        <dt>${ic('skills')}Grows</dt><dd><div class="tags"><span class="tag">Single neuron</span><span class="tag">Layers</span></div></dd>
        <dt>${ic('yt')}From</dt><dd>YouTube · 24:10</dd></dl></div>
      <div style="width:250px;flex:none;margin-top:6px">${th('net', { dur: '24:10', pg: 50 })}<button class="btn primary lg" style="width:100%;margin-top:12px">${ic('play')}Continue step 4 ${kbd('↩')}</button></div></div>
    <div class="sec" style="margin-top:26px">Steps</div>
    ${st.map(([t, s], i) => `<div class="row">${s === 'd' ? gk : `<span class="ring${s === 'c' ? ' cur' : ''}"></span>`}<span style="${s === 'c' ? 'font-weight:600;color:var(--ink)' : s ? '' : 'color:var(--muted)'}">${t}</span><span class="sp"></span><span class="m">${s === 'c' ? 'You are here' : ''}</span></div>`).join('')}
    <div class="row" style="color:var(--muted)"><span style="width:16px"></span>1 more step<span class="sp"></span>${chevRow.replace('<path d="m9 6 6 6-6 6"/>', '<path d="m6 9 6 6 6-6"/>')}</div>`));
}

// ---------- Skills ----------
function skillsHead(view, zoom, goal = true) {
  const tab = (v, l) => `<b class="${view === v ? 'on' : ''}">${l}</b>`, z = (v, l) => `<b class="${zoom === v ? 'on' : ''}">${l}</b>`;
  return `<div class="shead"><div class="titlerow"><h1>Skills</h1><div class="sp"></div>${goal ? `<button class="btn primary">${ic('play')}Continue Broadcasting ${kbd('↩')}</button>` : ''}</div>
    ${goal ? `<div class="lede">Goal <b>Fit sin(x) with a network</b> · 8 of 13 skills · about 3 hours left, around Dec 4 at your pace · <a>Change</a></div>` : '<div class="lede">&nbsp;</div>'}
    <div class="tabs">${tab('path', 'Path')}${tab('map', 'Map')}${tab('list', 'List')}<div class="sp"></div>${zoom ? `<div class="zl">${z('tracks', 'Tracks')}${z('skills', 'Skills')}${z('steps', 'Steps')}</div>` : ''}<div class="tbtn" style="margin-left:6px">${ic('search')}</div></div></div>`;
}
const skillsActs = `<div class="tbtn">${ic('share')}Share</div>`;
const stageWrap = (inner, after = '') => `<div class="canvas"><div class="stgwrap">${inner}</div>${after}</div>`;
const TOGO = [['broad', 'numpy', '2 of 4 steps', 'numpy for networks, step 3', '12 min'], ['mat', 'math', 'Ready', 'Matrices as layers', '25 min'],
  ['neuron', 'neural networks', 'Needs Broadcasting and Matrices', 'Build one neuron', '30 min'], ['layers', 'neural networks', 'Needs Single neuron', 'Stack neurons into layers', '35 min'],
  ['gd', 'neural networks', 'Needs Single neuron', 'Gradient descent from scratch', '40 min']];
// Path is a page, not a canvas: the diagram, then what is left as a table.
function pathBody(o = {}) {
  const rows = TOGO.map(([id, t, st, les, min], i) => `<tr class="${i === 0 ? 'cur' : SK[id].s === 'k' ? 'dim' : ''}"><td><div class="vt">${mk(SK[id])}<b>${SK[id].l}</b></div></td><td><span class="tag">${t}</span></td><td>${st}</td><td>${les}</td><td style="text-align:right">${min}</td></tr>`).join('');
  return `<div class="scroll"><div class="col wide" style="padding-top:36px">${pathStage(o)}
    <div class="${o.hot ? 'dim' : ''}"><div class="sec" style="margin-top:36px">Still to go</div>
    <table class="tbl"><tr><th>Skill</th><th>Track</th><th>Status</th><th>Lesson</th><th style="text-align:right">Time</th></tr>${rows}</table>
    <div class="row" style="margin-top:8px">${ic('refresh')}<b>Keep fresh</b><span class="m">Functions · 4 min</span><span class="sp"></span>${chevRow}</div></div>
  </div>${o.after || ''}</div>`;
}
function skillsPath() { return shell('skills', ['Skills', 'Path'], skillsActs, skillsHead('path') + pathBody()); }
function skillsMap() { return shell('skills', ['Skills', 'Map'], skillsActs, skillsHead('map', 'skills') + stageWrap(mapStage())); }
function skillsTracks() { return shell('skills', ['Skills', 'Map'], skillsActs, skillsHead('map', 'tracks') + stageWrap(tracksStage())); }
function skillsSteps() {
  const C = [
    { id: 'index', x: 0, y: 30, st: ['Pick one item', 'Slice a range', 'Slice rows and columns'], done: 3 },
    { id: 'funcs', x: 0, y: 218, st: ['Define and call', 'Arguments', 'Return values'], done: 3, note: 'review due' },
    { id: 'dot', x: 0, y: 406, st: ['Multiply and add', 'With a loop', 'With numpy'], done: 3 },
    { id: 'broad', x: 290, y: 16, st: ['Shapes and axes', 'Add one row to every row', 'Stretch a column to fit', 'Normalize a whole image'], done: 2, cur: 2, note: '2 of 4' },
    { id: 'mat', x: 290, y: 392, st: ['Rows and columns', 'Shape and transpose', 'Matrix times vector', 'Matrix times matrix'], done: 0, note: 'ready' },
    { id: 'neuron', x: 580, y: 218, st: ['Weights and bias', 'Weighted sum', 'Activation'], done: 0, locked: 1 },
    { id: 'layers', x: 868, y: 50, st: ['Many neurons at once', 'Stack two layers', 'Shapes that fit'], done: 0, locked: 1 },
    { id: 'gd', x: 868, y: 386, st: ['Loss', 'Slope', 'Step downhill'], done: 0, locked: 1 }
  ];
  const h = c => 60 + c.st.length * 28, P = Object.fromEntries(C.map(c => [c.id, c]));
  const E = (a, b, k) => line(elbowH(P[a].x + 236, P[a].y + h(P[a]) / 2, P[b].x, P[b].y + h(P[b]) / 2), k);
  const svg = E('funcs', 'neuron', 'locked') + E('broad', 'neuron', 'locked') + E('mat', 'neuron', 'locked') + E('neuron', 'layers', 'locked') + E('neuron', 'gd', 'locked') + E('index', 'broad', 'open') + E('dot', 'mat', 'open');
  const cards = C.map(c => {
    const n = SK[c.id];
    return `<div class="scard${c.id === 'broad' ? ' next' : ''}${c.locked ? ' locked' : ''}" style="left:${c.x}px;top:${c.y}px"><div class="hd">${mk(n)}<b>${n.l}</b><span>${c.note || ''}</span></div>` +
      c.st.map((t, i) => `<div class="st${i < c.done ? '' : i === c.cur ? ' cur' : ' todo'}">${i < c.done ? gk : `<span class="ring${i === c.cur ? ' cur' : ''}"></span>`}${t}</div>`).join('') + '</div>';
  }).join('');
  return shell('skills', ['Skills', 'Map'], skillsActs, skillsHead('map', 'steps') + stageWrap(`<div class="stg" style="width:1104px;height:600px"><svg viewBox="0 0 1104 600">${svg}</svg>${cards}</div>`));
}
function skillsProof() {
  const hot = new Set(['arrays', 'index', 'broad']);
  const peek = `<div class="peek"><div class="ptop"><div class="tbtn">${ic('peek')}</div><span>numpy</span><i style="font-style:normal;color:var(--ghost)">/</i><b style="font-weight:500;color:var(--text)">Indexing</b><span style="flex:1"></span><div class="tbtn">${ic('share')}Share</div></div>
    <h2>Indexing</h2>
    <div class="tags"><span class="tag ok">${ic('check').replace('class="ic "', 'class="ic" style="width:12px;height:12px;stroke-width:2.4"')}Mastered</span><span class="tag">Nov 14</span><span class="tag">numpy</span></div>
    <div class="lab">The code you wrote</div>
    <div class="code"><span class="c"># rows 0 to 1, columns 1 to 2</span>
img = np.arange(12).reshape(3, 4)
corner = img[:2, 1:3]</div>
    <div class="lab">The check it passed</div>
    <div class="row" style="align-items:flex-start;padding-top:10px;padding-bottom:10px">${gk}<div><b>corner equals [[1 2] [5 6]]</b><div class="m" style="margin-top:2px">Step 3 of 3 · numpy for networks · Nov 14</div></div></div>
    <div class="lab">Steps</div>
    ${['Pick one item', 'Slice a range', 'Slice rows and columns'].map(t => `<div class="row" style="min-height:36px">${gk}${t}</div>`).join('')}
    <div class="lab">Opens</div><div class="tags"><span class="tag">Broadcasting</span></div>
    <div style="flex:1"></div>
    <div style="display:flex;gap:8px"><button class="btn quiet">${ic('refresh')}Practice again</button><button class="btn quiet">Open lesson</button></div></div>`;
  return shell('skills', ['Skills', 'Path'], skillsActs, skillsHead('path') + pathBody({ hot, sel: 'index', after: peek }));
}
function skillsShare() {
  const cardBg = dark ? 'rgb(25,24,22)' : '#F6F6F3';
  const modal = `<div class="scrim"><div class="pop modal"><div class="titlerow"><h2>Share your tree</h2><div class="sp"></div><div class="tbtn">${ic('x')}</div></div>
    <div style="margin-top:14px;height:310px;border-radius:10px;background:${cardBg};box-shadow:inset 0 0 0 1px var(--hair2);position:relative;overflow:hidden">
      <div style="position:absolute;left:28px;top:26px;display:flex;align-items:center;gap:7px"><img src="${asset('tree-small')}" style="width:20px;height:20px"><img src="${asset('wordmark')}" style="height:14px"></div>
      <div style="position:absolute;left:28px;bottom:26px"><div style="font-size:26px;font-weight:700;letter-spacing:-.02em;color:var(--ink);line-height:1.15">Sam's skill tree</div>
        <div style="font-size:14px;color:var(--muted);margin-top:6px">11 skills mastered · 3 projects ahead</div><div style="font-size:12.5px;color:var(--faint);margin-top:16px">miyagi.study</div></div>
      <svg viewBox="60 110 990 530" style="position:absolute;right:16px;top:26px;width:340px;height:258px">${miniMap()}</svg></div>
    <div style="display:flex;align-items:center;gap:8px;margin-top:16px"><span class="chip sky on">Whole tree</span><span class="chip lilac">Finished project</span><span class="chip pink">This week</span>
      <span style="flex:1"></span><div class="seg"><b class="${dark ? '' : 'on'}">Light</b><b class="${dark ? 'on' : ''}">Dark</b></div></div>
    <div style="display:flex;gap:8px;margin-top:18px"><button class="btn primary">${ic('copy')}Copy image</button><button class="btn quiet">${ic('down')}Save PNG</button><span style="flex:1"></span><button class="btn quiet">LinkedIn</button><button class="btn quiet">X</button></div></div></div>`;
  return shell('skills', ['Skills', 'Map'], skillsActs, skillsHead('map', 'skills') + stageWrap(mapStage()) + modal);
}
function skillsEmpty() {
  const g = (title, meta, on) => `<div class="card" style="padding:14px 14px 12px;${on ? 'box-shadow:0 0 0 2px var(--ink),var(--e2)' : ''}"><svg viewBox="0 0 180 84" style="width:100%;height:auto;display:block;margin-bottom:10px">${on ? sinPlot() : '<rect width="180" height="84" rx="8" fill="var(--fill)"/>' + meta[2]}</svg>
    <b style="display:block;font-size:14.5px;font-weight:620;color:var(--ink);line-height:1.3">${title}</b><span style="font-size:12.5px;color:var(--muted)">${meta[0]} · ${meta[1]}</span></div>`;
  const bars = '<g fill="var(--faint)">' + [30, 52, 40, 64, 46].map((h, i) => `<rect x="${32 + i * 26}" y="${74 - h}" width="14" height="${h}" rx="3"/>`).join('') + '</g>';
  const grid = '<g fill="var(--ghost)">' + Array.from({ length: 15 }, (_, i) => `<rect x="${22 + (i % 5) * 28}" y="${16 + Math.floor(i / 5) * 20}" width="22" height="12" rx="3"/>`).join('') + '</g>';
  const box = '<g fill="none" stroke="var(--faint)" stroke-width="1.6"><path d="M62 30l28-12 28 12v26l-28 12-28-12zM62 30l28 12 28-12M90 42v26"/></g>';
  return shell('skills', ['Skills'], '', `<div class="shead"><h1>Skills</h1></div><div class="canvas"><div class="empty" style="padding-bottom:90px">
    <h2 style="font-size:24px;margin-top:0">Pick something to build.</h2><p>Your tree grows toward it, one skill at a time.</p>
    <div style="display:grid;grid-template-columns:repeat(4,206px);gap:14px;text-align:left">
      ${g('Fit sin(x) with a network', ['13 skills', 'about 6 hours'], true)}${g('A sales report from a CSV', ['9 skills', 'about 4 hours', bars], false)}${g('A budget in Google Sheets', ['8 skills', 'about 3 hours', grid], false)}${g('A 3D-printable part', ['11 skills', 'about 5 hours', box], false)}</div>
    <button class="btn primary lg" style="margin-top:26px">Start with this goal ${kbd('↩')}</button>
    <div class="lede" style="font-size:13px;margin-top:12px">Or paste a YouTube link and build toward that.</div></div></div>`)
    .replace(/<div class="slabel">Plans[\s\S]*?<div class="grow">/, '<div class="grow">');
}

// ---------- Progress: the bonsai, one branch per track ----------
function bonsai(empty) {
  const G = 'var(--green)', K = 'var(--trunk)';
  if (empty) return `<svg viewBox="0 0 640 400" style="width:640px;height:400px"><g fill="var(--pot)"><rect x="262" y="330" width="116" height="11" rx="4"/><path d="M270 341H370L360 376H280Z"/></g>
    <path d="M320 330V296" stroke="${K}" stroke-width="5" stroke-linecap="round"/><path d="M320 300c0-12-9-20-24-20 0 13 9 20 24 20ZM320 310c0-10 8-17 21-17 0 11-8 17-21 17Z" fill="none" stroke="var(--faint)" stroke-width="1.6" stroke-dasharray="3 3.5"/></svg>`;
  // pads: [track, cx, cy, mastered, total, side]
  const pads = [['python', 226, 262, 4, 4, 'l'], ['pandas', 434, 238, 2, 4, 'r'], ['numpy', 214, 170, 2, 3, 'l'], ['math', 426, 144, 2, 3, 'r'], ['plotting', 250, 88, 1, 4, 'l'], ['neural networks', 372, 52, 0, 3, 'r']];
  let s = `<g fill="var(--pot)"><rect x="262" y="340" width="116" height="11" rx="4"/><path d="M270 351H370L360 384H280Z"/></g>`;
  const br = (d, w) => `<path d="${d}" fill="none" stroke="${K}" stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round"/>`;
  s += br('M316 300C296 300 268 300 262 268', 8) + br('M330 262C360 262 392 266 398 244', 8) + br('M326 212C298 212 250 208 240 176', 7) + br('M336 168C362 168 396 170 402 150', 7) + br('M338 128C320 128 292 122 286 94', 6);
  s += br('M318 342C300 296 344 270 330 226', 17) + br('M330 226C318 188 350 160 340 122', 12) + br('M340 122C334 100 352 84 362 60', 8);
  for (const [t, cx, cy, m, n, side] of pads) {
    const R = 17, step = 25, x0 = cx - (n - 1) * step / 2;
    s += `<clipPath id="pad-${t.replace(/ /g, '')}"><rect x="${x0 - R - 3}" y="${cy - 60}" width="${(n - 1) * step + 2 * R + 6}" height="${60 + 9}"/></clipPath><g clip-path="url(#pad-${t.replace(/ /g, '')})">`;
    for (let i = 0; i < n; i++) {
      const x = x0 + i * step, y = cy - Math.sin(Math.PI * (i + .5) / n) * 9, on = side === 'l' ? i >= n - m : i < m;
      s += on ? `<circle cx="${x}" cy="${y}" r="${R}" fill="${G}"/>` : `<circle cx="${x}" cy="${y}" r="${R - 1}" fill="var(--page)" stroke="var(--ghost)" stroke-width="1.6" stroke-dasharray="3 3.5"/>`;
    }
    s += '</g>';
    const lx = side === 'l' ? x0 - R - 14 : x0 + (n - 1) * step + R + 14, anchor = side === 'l' ? 'end' : 'start';
    s += `<text x="${lx}" y="${cy - 8}" text-anchor="${anchor}" class="lbl" style="font-size:14px">${t}</text><text x="${lx}" y="${cy + 9}" text-anchor="${anchor}" class="sub" style="font-size:12.5px">${m} of ${n}</text>`;
  }
  return `<svg viewBox="0 0 640 400" style="width:640px;height:400px;display:block;margin:0 auto">${s}</svg>`;
}
function progress() {
  return shell('progress', ['Progress'], `<div class="tbtn">${ic('share')}Share</div>`, page(`
    <div class="titlerow"><h1>Progress</h1><div class="sp"></div><button class="btn primary">${ic('play')}Continue Broadcasting ${kbd('↩')}</button></div>
    <div class="lede">11 skills mastered. The next leaf is <b>Broadcasting</b>.</div>
    <div style="margin-top:8px">${bonsai()}</div>
    <div class="row">${ic('flag')}<b>Fit sin(x) with a network</b><span class="m">about 3 hours left · around Dec 4 at your pace</span><span class="sp"></span>${chevRow}</div>
    <div class="row">${ic('refresh')}<b>Keep fresh</b><span class="m">Functions, DataFrames · 4 min</span><span class="sp"></span>${chevRow}</div>
    <div class="row">${gk}<b>Finished</b><span class="m">numpy arrays from scratch, Group and summarize sales with pandas</span><span class="sp"></span>${chevRow}</div>`));
}
function progressEmpty() {
  return shell('progress', ['Progress'], '', `<div class="scroll"><div class="empty" style="padding-bottom:40px">${bonsai(true).replace('width:640px;height:400px', 'width:320px;height:200px')}
    <h2 style="margin-top:4px">Your tree starts with one passed step.</h2><p>Each skill you master adds a leaf.</p><button class="btn primary lg">${ic('compose')}Start a lesson</button></div></div>`)
    .replace(/<div class="slabel">Plans[\s\S]*?<div class="grow">/, '<div class="grow">');
}

// ---------- Settings ----------
function settings() {
  const row = (l, right, d = '') => `<div class="srow"><div><div class="l">${l}</div>${d ? `<div class="d">${d}</div>` : ''}</div><span class="sp"></span>${right}</div>`;
  const seg = (items, on) => `<div class="seg">${items.map((t, i) => `<b class="${i === on ? 'on' : ''}">${t}</b>`).join('')}</div>`;
  const granted = `<span class="v" style="color:var(--green-text)">${gk}Granted</span>`;
  return shell('settings', ['Settings'], '', page(`
    <h1>Settings</h1>
    <div class="sec" style="margin-top:22px">General</div>
    <div class="group">${row('Appearance', seg(['System', 'Light', 'Dark'], 0))}${row('Open miyagi', `<span class="v">${kbd('⌥ Space')}</span>`)}${row('Open at login', '<span class="tog on"></span>')}</div>
    <div class="sec">Lessons</div>
    <div class="group">${row('Read steps aloud', '<span class="tog"></span>', 'Uses the voice built into this Mac.')}${row('Code editor', `<span class="v">VS Code ${chevRow}</span>`)}</div>
    <div class="sec">Permissions</div>
    <div class="group">${row('Screen Recording', granted, 'So miyagi can check your work.')}${row('Accessibility', granted, 'So miyagi can point at the right button.')}</div>
    <div class="sec">Privacy</div>
    <div class="group">${row('What miyagi sees', chevRow)}${row('Delete my account', chevRow)}</div>
    <div class="sec">About</div>
    <div class="group">${row('Version 0.9.2', '<button class="btn quiet" style="height:28px;font-size:13px">Check for updates</button>')}</div>`));
}

// ---------- Setup: five minutes, ends inside the first lesson ----------
function flow(n, body) {
  const st = ['Sign in', 'Permissions', 'First lesson'];
  return `<div class="flow"><div class="lights"><i></i><i></i><i></i></div><div class="box">${body}</div>
    <div class="steps">${st.map((t, i) => `<b class="${i === n ? 'on' : i < n ? 'done' : ''}">${i < n ? gk : ''}${t}</b>`).join('<i></i>')}</div></div>`;
}
function onboard1() {
  return flow(0, `<img src="${asset('tree-small')}" style="width:64px;height:64px"><h1>learn by doing.</h1><p>Setup takes about five minutes and ends inside your first lesson.</p>
    <button class="btn primary lg" style="margin-top:28px;width:280px">Continue with Google</button>
    <div style="font-size:12.5px;color:var(--faint);margin-top:14px">By continuing you agree to the terms and privacy policy.</div>`);
}
function onboard2() {
  return flow(1, `<h1 style="margin-top:0">Let miyagi see your work</h1><p>It looks only while a lesson is running.</p>
    <div class="group" style="width:460px;margin-top:26px;text-align:left">
      <div class="srow" style="min-height:60px"><div><div class="l">Screen Recording</div><div class="d">To check each step you do.</div></div><span class="sp"></span><span class="v" style="color:var(--green-text)">${gk}Granted</span></div>
      <div class="srow" style="min-height:60px"><div><div class="l">Accessibility</div><div class="d">To point at the right button.</div></div><span class="sp"></span><button class="btn primary">Open System Settings</button></div></div>
    <div style="font-size:12.5px;color:var(--faint);margin-top:14px">The check turns green here as soon as you switch it on.</div>`);
}
function onboard3() {
  const c = (kind, t, m, on) => `<div class="lc" style="text-align:left;padding:8px;border-radius:14px;${on ? 'box-shadow:0 0 0 2px var(--ink)' : ''}">${th(kind)}<b>${t}</b><span>${m}</span></div>`;
  return flow(2, `<h1 style="margin-top:0">Pick your first lesson</h1><p>Each one takes about five minutes.</p>
    <div style="display:grid;grid-template-columns:repeat(3,200px);gap:8px;margin-top:22px">${c('code', 'Your first Python program', 'VS Code', true)}${c('table', 'Clean a messy spreadsheet', 'Google Sheets')}${c('plot', 'Plot your first chart', 'Jupyter')}</div>
    <button class="btn primary lg" style="margin-top:22px;width:280px">Start lesson ${kbd('↩')}</button>
    <div style="font-size:12.5px;color:var(--faint);margin-top:14px">Or paste a YouTube link.</div>`).replace('class="box"', 'class="box" style="width:640px"');
}

const SCREENS = { home, 'home-link': homeLink, 'home-empty': homeEmpty, library, 'library-empty': libraryEmpty, course, lesson,
  'skills-path': skillsPath, 'skills-map': skillsMap, 'skills-tracks': skillsTracks, 'skills-steps': skillsSteps, 'skills-proof': skillsProof, 'skills-share': skillsShare, 'skills-empty': skillsEmpty,
  progress, 'progress-empty': progressEmpty, settings, 'onboard-1': onboard1, 'onboard-2': onboard2, 'onboard-3': onboard3 };
window.RENDER = () => { document.body.innerHTML = (SCREENS[S] || SCREENS.home)(); const H = +q.get("h"); if (H) { document.documentElement.style.height = document.body.style.height = H + "px"; } };

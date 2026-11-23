// Skill tree drawing for the mock, Notion style: a skill is a small flat card, an edge is a hairline with square turns.
// No bands, no shadows, no dots. Green is only the check and the line between two mastered skills.
// States: m mastered, r mastered + review due, p practicing, y ready, k locked.
const SK = {
  vars:   { l: 'Variables', t: 'python', s: 'm' },
  loops:  { l: 'Loops', t: 'python', s: 'm' },
  funcs:  { l: 'Functions', t: 'python', s: 'r' },
  lists:  { l: 'Lists', t: 'python', s: 'm' },
  arrays: { l: 'Arrays', t: 'numpy', s: 'm' },
  index:  { l: 'Indexing', t: 'numpy', s: 'm' },
  broad:  { l: 'Broadcasting', t: 'numpy', s: 'p', f: [2, 4], next: 1 },
  vec:    { l: 'Vectors', t: 'math', s: 'm' },
  dot:    { l: 'Dot product', t: 'math', s: 'm' },
  mat:    { l: 'Matrices', t: 'math', s: 'y' },
  neuron: { l: 'Single neuron', t: 'neural networks', s: 'k' },
  layers: { l: 'Layers', t: 'neural networks', s: 'k' },
  gd:     { l: 'Gradient descent', t: 'neural networks', s: 'k' },
  csv:    { l: 'Reading CSVs', t: 'pandas', s: 'm' },
  df:     { l: 'DataFrames', t: 'pandas', s: 'r' },
  clean:  { l: 'Cleaning rows', t: 'pandas', s: 'y' },
  group:  { l: 'Group by', t: 'pandas', s: 'k' },
  line:   { l: 'Line plots', t: 'plotting', s: 'm' },
  scat:   { l: 'Scatter plots', t: 'plotting', s: 'p', f: [1, 3] },
  subp:   { l: 'Subplots', t: 'plotting', s: 'k' },
  style:  { l: 'Styling', t: 'plotting', s: 'k' },
  py:     { l: 'python', t: 'python', s: 'm', count: 4 }      // the four python skills, folded into one card on the path
};
const isDone = s => s === 'm' || s === 'r';
const edgeKind = (a, b) => isDone(a.s) && isDone(b.s) ? 'done' : isDone(a.s) && (b.s === 'p' || b.s === 'y') ? 'open' : 'locked';
const EDGE = { done: 'var(--green)', open: 'var(--edge)', locked: 'var(--edge-lock)' };
const ORDER = { locked: 0, open: 1, done: 2 };
const line = (d, kind, extra = '', w = 1.5) => `<path d="${d}" fill="none" stroke="${EDGE[kind]}" stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round" ${extra}/>`;
const edge = line;
// one edge style: straight runs with a small rounded turn
function elbowH(x1, y1, x2, y2, mx) {
  if (y1 === y2) return `M${x1} ${y1}H${x2}`;
  mx = mx == null ? (x1 + x2) / 2 : mx;
  const r = Math.min(8, Math.abs(y2 - y1) / 2, Math.abs(mx - x1), Math.abs(x2 - mx)), s = y2 > y1 ? 1 : -1;
  return `M${x1} ${y1}H${mx - r}Q${mx} ${y1} ${mx} ${y1 + s * r}V${y2 - s * r}Q${mx} ${y2} ${mx + r} ${y2}H${x2}`;
}
function elbowV(x1, y1, x2, y2, my) {
  if (x1 === x2) return `M${x1} ${y1}V${y2}`;
  my = my == null ? (y1 + y2) / 2 : my;
  const r = Math.min(8, Math.abs(x2 - x1) / 2, Math.abs(my - y1), Math.abs(y2 - my)), s = x2 > x1 ? 1 : -1, v = y2 > y1 ? 1 : -1;
  return `M${x1} ${y1}V${my - v * r}Q${x1} ${my} ${x1 + s * r} ${my}H${x2 - s * r}Q${x2} ${my} ${x2} ${my + v * r}V${y2}`;
}
function arc(cx, cy, r, f) {
  const a = f * 2 * Math.PI - Math.PI / 2, x = cx + r * Math.cos(a), y = cy + r * Math.sin(a);
  return `M${cx} ${cy - r}A${r} ${r} 0 ${f > .5 ? 1 : 0} 1 ${x.toFixed(2)} ${y.toFixed(2)}`;
}
// the 14 px state mark inside a card: check, filling ring, open ring, lock
function mk(n) {
  let s;
  if (isDone(n.s)) s = '<circle cx="7" cy="7" r="7" fill="var(--green)"/><path d="M4 7.3l2.1 2.1 4-4.4" stroke="var(--on-green)" stroke-width="1.6" fill="none" stroke-linecap="round" stroke-linejoin="round"/>';
  else if (n.s === 'p') s = `<circle cx="7" cy="7" r="5.6" fill="none" stroke="var(--track)" stroke-width="1.8"/><path d="${arc(7, 7, 5.6, n.f[0] / n.f[1])}" fill="none" stroke="var(--ink)" stroke-width="1.8" stroke-linecap="round"/>`;
  else if (n.s === 'y') s = '<circle cx="7" cy="7" r="5.7" fill="none" stroke="var(--ink)" stroke-width="1.5"/>';
  else s = '<rect x="3.2" y="6.3" width="7.6" height="5.6" rx="1.4" fill="var(--faint)"/><path d="M4.9 6.3V4.7a2.1 2.1 0 0 1 4.2 0v1.6" fill="none" stroke="var(--faint)" stroke-width="1.3"/>';
  return `<svg class="mk" viewBox="0 0 14 14">${s}</svg>`;
}
// a larger flat mark, for the course strip and step cards
function mark(n, x, y, r) {
  const k = r / 22;
  if (isDone(n.s)) return `<circle cx="${x}" cy="${y}" r="${r}" fill="var(--green)"/><path d="M${x - 7 * k} ${y + .6 * k}l${4.6 * k} ${4.6 * k}l${9 * k} ${-9.6 * k}" stroke="var(--on-green)" stroke-width="${Math.max(1.5, 2.6 * k)}" fill="none" stroke-linecap="round" stroke-linejoin="round"/>`;
  if (n.s === 'p') return `<circle cx="${x}" cy="${y}" r="${r - 1}" fill="var(--card)" stroke="var(--track)" stroke-width="2"/><path d="${arc(x, y, r - 1, n.f[0] / n.f[1])}" fill="none" stroke="var(--ink)" stroke-width="2" stroke-linecap="round"/>`;
  if (n.s === 'y') return `<circle cx="${x}" cy="${y}" r="${r - 1}" fill="var(--card)" stroke="var(--ink)" stroke-width="1.6"/>`;
  return `<circle cx="${x}" cy="${y}" r="${r}" fill="var(--fill2)"/><rect x="${x - 5 * k}" y="${y - 1.5 * k}" width="${10 * k}" height="${8 * k}" rx="${2 * k}" fill="var(--faint)"/><path d="M${x - 3 * k} ${y - 1.5 * k}v${-2.6 * k}a${3 * k} ${3 * k} 0 0 1 ${6 * k} 0v${2.6 * k}" fill="none" stroke="var(--faint)" stroke-width="${Math.max(1.1, 1.7 * k)}"/>`;
}
const REFRESH = '<svg class="rf" viewBox="0 0 24 24"><path d="M20 12a8 8 0 1 1-2.3-5.6"/><path d="M20 4v5h-5"/></svg>';
const CHEV = '<svg class="rf" viewBox="0 0 24 24"><path d="m9 6 6 6-6 6"/></svg>';
// the skill card. x is its left edge, or its centre when o.center is set.
function chip(id, x, y, w, o = {}) {
  const n = SK[id];
  const cls = ['nd', n.s === 'k' ? 'k' : '', n.next && !o.noNext ? 'next' : '', o.dim ? 'dim' : '', o.sel ? 'sel' : ''].filter(Boolean).join(' ');
  const tail = n.count ? `<span class="nx">${n.count}</span>${CHEV}` : n.s === 'r' ? REFRESH : '';
  return `<div class="${cls}" style="left:${o.center ? x - w / 2 : x}px;top:${y - 16}px;width:${w}px">${mk(n)}<span class="nt">${n.l}</span>${tail}</div>`;
}
const tlabel = (x, y, t, right) => `<div class="tl" style="${right ? `right:${1104 - x}px` : `left:${x}px`};top:${y}px">${t}</div>`;
function sinPlot(H = 84) {
  let pts = '', d = '';
  const mid = H / 2, amp = H * .31;
  for (let i = 0; i <= 30; i++) {
    const x = 8 + i * 5.47, y = mid - Math.sin(i / 30 * Math.PI * 2) * amp;
    d += (i ? 'L' : 'M') + x.toFixed(1) + ' ' + y.toFixed(1);
    if (i % 2 === 0) pts += `<circle cx="${x.toFixed(1)}" cy="${(y + Math.sin(i * 7.3) * H * .07).toFixed(1)}" r="1.8" fill="var(--faint)"/>`;
  }
  return `<rect width="180" height="${H}" rx="6" fill="var(--fill)"/><path d="M8 ${mid}H172" stroke="var(--hair2)"/>${pts}<path d="${d}" fill="none" stroke="var(--ink)" stroke-width="1.6" stroke-linecap="round"/>`;
}

// ---------- PATH: what stands between you and the goal, left to right, three even rows ----------
const PCOL = [[0, 104], [140, 92], [268, 118], [422, 126], [584, 126], [746, 146]], PROJ = [928, 176], PROW = [44, 126, 208];
const PN = { py: [0, 1], arrays: [1, 0], vec: [1, 2], index: [2, 0], dot: [2, 2], broad: [3, 0], mat: [3, 2], neuron: [4, 1], layers: [5, 0], gd: [5, 2] };
const PE = [['py', 'arrays'], ['py', 'vec'], ['py', 'neuron'], ['arrays', 'index'], ['vec', 'dot'], ['index', 'broad'], ['dot', 'mat'], ['broad', 'neuron'], ['mat', 'neuron'], ['neuron', 'layers'], ['neuron', 'gd']];
function pathStage(o = {}) {
  const hot = o.hot || null, L = id => PCOL[PN[id][0]][0], R = id => L(id) + PCOL[PN[id][0]][1], Y = id => PROW[PN[id][1]];
  const E = PE.map(([a, b]) => ({ a, b, k: edgeKind(SK[a], SK[b]), d: elbowH(R(a), Y(a), L(b), Y(b)) }));
  E.push({ a: 'layers', b: '', k: 'locked', d: elbowH(R('layers'), Y('layers'), PROJ[0], PROW[1]) }, { a: 'gd', b: '', k: 'locked', d: elbowH(R('gd'), Y('gd'), PROJ[0], PROW[1]) });
  E.sort((p, q) => ORDER[p.k] - ORDER[q.k]);
  const svg = E.map(e => line(e.d, e.k, hot && !(hot.has(e.a) && hot.has(e.b)) ? 'opacity=".3"' : '')).join('');
  let html = '';
  for (const id in PN) html += chip(id, L(id), Y(id), PCOL[PN[id][0]][1], { dim: hot && !hot.has(id), sel: o.sel === id, noNext: !!hot });
  const tl = hot ? '' : tlabel(L('arrays'), PROW[0] - 40, 'numpy') + tlabel(L('vec'), PROW[2] - 40, 'math') + tlabel(L('neuron'), PROW[1] - 40, 'neural networks');
  const proj = `<div class="proj${hot ? ' dim' : ''}" style="left:${PROJ[0]}px;top:${PROW[1] - 74}px;width:${PROJ[1]}px;height:148px">
    <svg viewBox="0 0 180 54" style="width:100%;height:auto;display:block">${sinPlot(54)}</svg>
    <div class="pl">Project</div><b>Fit sin(x) with a network</b>
    <div class="bar g" style="margin-top:auto"><i style="width:62%"></i></div></div>`;
  return `<div class="stg" style="width:1104px;height:240px"><svg viewBox="0 0 1104 240">${svg}</svg>${html}${tl}${proj}</div>`;
}

// ---------- MAP: everything you know as one tree growing up from Variables. Columns mirror each other. ----------
const MROW = [586, 512, 438, 364, 290, 216, 142];
const MCOL = { pl: [150, 128], np: [400, 122], c: [552, 128], ma: [704, 122], pa: [954, 132], la: [456, 146], gr: [648, 146] };
const MN = { vars: ['c', 0], loops: ['np', 1], funcs: ['c', 1], lists: ['ma', 1], arrays: ['np', 2], index: ['np', 3], broad: ['np', 4], vec: ['ma', 2], dot: ['ma', 3], mat: ['ma', 4], neuron: ['c', 5],
  layers: ['la', 6], gd: ['gr', 6], line: ['pl', 2], scat: ['pl', 3], subp: ['pl', 4], style: ['pl', 5], csv: ['pa', 2], df: ['pa', 3], clean: ['pa', 4], group: ['pa', 5] };
const ME = [['vars', 'loops'], ['vars', 'funcs'], ['vars', 'lists'], ['loops', 'arrays'], ['lists', 'vec'], ['arrays', 'index'], ['vec', 'dot'], ['index', 'broad'], ['dot', 'mat'], ['funcs', 'neuron'], ['broad', 'neuron'], ['mat', 'neuron'],
  ['neuron', 'layers'], ['neuron', 'gd'], ['loops', 'line'], ['line', 'scat'], ['scat', 'subp'], ['subp', 'style'], ['lists', 'csv'], ['csv', 'df'], ['df', 'clean'], ['clean', 'group']];
const MX = id => MCOL[MN[id][0]][0], MW = id => MCOL[MN[id][0]][1], MYY = id => MROW[MN[id][1]];
function mapEdges() {
  const E = ME.map(([a, b]) => ({ k: edgeKind(SK[a], SK[b]), d: elbowV(MX(a), MYY(a) - 16, MX(b), MYY(b) + 16) }));
  for (const id of ['layers', 'gd']) E.push({ k: 'locked', d: `M${MX(id)} ${MYY(id) - 16}V98` });
  for (const id of ['style', 'group']) E.push({ k: 'locked', d: `M${MX(id)} ${MYY(id) - 16}V166` });
  E.push({ k: 'done', d: `M${MX('vars')} ${MYY('vars') + 16}V620` });
  return E.sort((p, q) => ORDER[p.k] - ORDER[q.k]);
}
function mapStage() {
  const svg = mapEdges().map(e => line(e.d, e.k)).join('');
  let html = '';
  for (const id in MN) html += chip(id, MX(id), MYY(id), MW(id), { center: 1 });
  const tl = (id, t) => tlabel(MX(id) - MW(id) / 2 - 10, MYY(id) - 9, t, true);
  html += tl('vars', 'python') + tl('arrays', 'numpy') + tl('vec', 'math') + tl('line', 'plotting') + tl('csv', 'pandas') + tl('neuron', 'neural networks');
  const side = (x, w, t) => `<div class="proj" style="left:${x - w / 2}px;top:118px;width:${w}px;height:48px;padding:7px 10px"><div class="pl" style="margin:0">Project</div><b style="font-size:13.5px">${t}</b></div>`;
  html += `<div class="proj" style="left:422px;top:22px;width:260px;height:76px;flex-direction:row;align-items:center;gap:12px">
    <svg viewBox="0 0 180 84" style="width:84px;height:auto;flex:none">${sinPlot(84)}</svg><div><div class="pl" style="margin:0">Project</div><b>Fit sin(x) with a network</b></div></div>`;
  html += side(150, 150, 'Chart your results') + side(954, 150, 'Sales report');
  return `<div class="stg" style="width:1104px;height:620px"><svg viewBox="0 0 1104 620">${svg}</svg>${html}</div>`;
}

// ---------- TRACKS (zoomed out): one card per track with its share done ----------
const TR = [['python', 552, 520, 4, 4], ['plotting', 150, 388, 1, 4], ['numpy', 400, 388, 2, 3], ['math', 704, 388, 2, 3], ['pandas', 954, 388, 2, 4], ['neural networks', 552, 256, 0, 3]];
function tracksStage() {
  const T = Object.fromEntries(TR.map(t => [t[0], t])), H = 27;
  const up = (a, b, k) => line(elbowV(T[a][1], T[a][2] - H, T[b][1], T[b][2] + H), k);
  let svg = up('numpy', 'neural networks', 'locked') + up('math', 'neural networks', 'locked') + line(`M552 ${520 - H}V${256 + H}`, 'locked');
  svg += ['plotting', 'numpy', 'math', 'pandas'].map(t => up('python', t, 'done')).join('') + line(`M552 ${256 - H}V124`, 'locked') + line(`M552 ${520 + H}V620`, 'done');
  let html = '';
  for (const [t, x, y, d, n] of TR) html += `<div class="trk" style="left:${x - 82}px;top:${y - H}px"><div><b>${t}</b><span>${d} of ${n}</span></div><div class="bar g"><i style="width:${d / n * 100}%"></i></div></div>`;
  html += `<div class="proj" style="left:422px;top:48px;width:260px;height:76px;flex-direction:row;align-items:center;gap:12px">
    <svg viewBox="0 0 180 84" style="width:84px;height:auto;flex:none">${sinPlot(84)}</svg><div><div class="pl" style="margin:0">Project</div><b>Fit sin(x) with a network</b></div></div>`;
  return `<div class="stg" style="width:1104px;height:620px"><svg viewBox="0 0 1104 620">${svg}</svg>${html}</div>`;
}

// a small tree with no words, for previews (share card, link preview)
function miniMap(grow) {
  let s = mapEdges().map(e => line(e.d, e.k, '', 4)).join('');
  for (const id in MN) {
    const n = SK[id], x = MX(id), y = MYY(id), g = grow && grow.has(id);
    s += `<rect x="${x - 50}" y="${y - 15}" width="100" height="30" rx="9" ${g ? 'fill="var(--ink)"' : isDone(n.s) ? 'fill="var(--green)"' : 'fill="var(--card)" stroke="var(--edge-lock)" stroke-width="4"'}/>`;
  }
  return s;
}

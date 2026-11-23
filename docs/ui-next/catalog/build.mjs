// Checks every plan in plans/ against SCHEMA.md, then writes catalog.json, catalog.js and CATALOG.md.
// usage: node build.mjs            (exit code 1 when any plan breaks a rule)
//        node build.mjs --check    (check only, write nothing)
import { readdirSync, readFileSync, writeFileSync, existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const dir = join(here, 'plans');
const GROUPS = ['language', 'environment', 'topic'];
const TOPICS = ['code', 'data', 'ai', '3d', 'cad', 'design', 'tools'];
const TOOLS = ['vscode', 'jupyter', 'terminal', 'browser', 'blender', 'freecad', 'fusion', 'onshape', 'figma', 'excel', 'sheets', 'unity', 'godot', 'xcode', 'arduino', 'docker', 'rstudio'];
const CHECKS = ['run', 'code', 'scene', 'file', 'screen'];
const MINUTES = [10, 15, 20, 25, 30];
const BANNED = /\b(master|unlock|journey|dive|delve|seamless|powerful|supercharge)\w*\b|!/i;

const errs = [];
const plans = [];
for (const f of readdirSync(dir).filter(f => f.endsWith('.json')).sort()) {
  let p;
  try { p = JSON.parse(readFileSync(join(dir, f), 'utf8')); } catch (e) { errs.push(`${f}: not valid JSON (${e.message})`); continue; }
  p._file = f;
  plans.push(p);
}
const byId = Object.fromEntries(plans.map(p => [p.id, p]));
const str = (v, max) => typeof v === 'string' && v.trim().length > 0 && v.length <= max;

for (const p of plans) {
  const E = m => errs.push(`${p._file}: ${m}`);
  if (p.id + '.json' !== p._file) E(`id "${p.id}" does not match the file name`);
  if (!/^[a-z0-9]+(-[a-z0-9]+)*$/.test(p.id || '')) E('id is not kebab-case');
  if (!str(p.title, 34)) E(`title missing or over 34 characters (${(p.title || '').length})`);
  if (!GROUPS.includes(p.group)) E(`group "${p.group}"`);
  if (!TOPICS.includes(p.topic)) E(`topic "${p.topic}"`);
  if (!str(p.track, 24) || p.track !== p.track.toLowerCase()) E('track missing or not lowercase');
  if (!p.tool || !TOOLS.includes(p.tool.id) || !str(p.tool.label, 20)) E(`tool ${JSON.stringify(p.tool)}`);
  if (!Array.isArray(p.also)) E('also must be an array');
  if (!['start', 'next'].includes(p.level)) E(`level "${p.level}"`);
  if (!Array.isArray(p.needs)) E('needs must be an array');
  else {
    for (const n of p.needs) if (!byId[n]) E(`needs unknown plan "${n}"`);
    if (p.level === 'start' && p.needs.length) E('a start plan cannot need another plan');
    if (p.level === 'next' && !p.needs.length) E('a next plan must name the plan it builds on');
  }
  if (!str(p.line, 70)) E(`line missing or over 70 characters (${(p.line || '').length})`);
  if (/:/.test(p.line || '')) E('line has a colon');
  const pr = p.project || {};
  if (!str(pr.title, 44)) E('project.title missing or over 44 characters');
  if (!str(pr.brief, 190)) E(`project.brief missing or over 190 characters (${(pr.brief || '').length})`);
  if (!Array.isArray(pr.checks) || pr.checks.length !== 3 || !pr.checks.every(c => str(c, 90))) E('project.checks must be exactly 3 lines of at most 90 characters');

  const skills = Array.isArray(p.skills) ? p.skills : [];
  if (skills.length < 6 || skills.length > 10) E(`${skills.length} skills (6 to 10)`);
  const own = new Set(skills.map(s => s.id));
  if (own.size !== skills.length) E('duplicate skill id');
  const outside = new Set((p.needs || []).flatMap(n => (byId[n]?.skills || []).map(s => s.id)));
  for (const s of skills) {
    if (!/^[a-z0-9]+\.[a-z0-9_]+$/.test(s.id || '')) E(`skill id "${s.id}"`);
    if (!str(s.label, 18)) E(`skill ${s.id}: label missing or over 18 characters`);
    for (const n of s.needs || []) if (!own.has(n) && !outside.has(n)) E(`skill ${s.id} needs unknown "${n}"`);
  }
  if (!skills.some(s => !(s.needs || []).some(n => own.has(n)))) E('no root skill');
  // cycles
  const seen = {};
  const walk = id => { if (seen[id] === 1) return true; if (seen[id] === 2) return false; seen[id] = 1; const s = skills.find(x => x.id === id);
    for (const n of s?.needs || []) if (own.has(n) && walk(n)) return true; seen[id] = 2; return false; };
  if (skills.some(s => walk(s.id))) E('skills have a cycle');

  const lessons = Array.isArray(p.lessons) ? p.lessons : [];
  if (lessons.length < 6 || lessons.length > 12) E(`${lessons.length} lessons (6 to 12)`);
  const grown = new Set();
  lessons.forEach((l, i) => {
    const L = m => E(`lesson ${i + 1}: ${m}`);
    if (!str(l.title, 40)) L(`title missing or over 40 characters (${(l.title || '').length})`);
    if (!str(l.goal, 200) || !/^Teach\b/.test(l.goal || '')) L(`goal must start with "Teach" and be at most 200 characters (${(l.goal || '').length})`);
    if (!Array.isArray(l.grows) || l.grows.length < 1 || l.grows.length > 2) L('grows must list 1 or 2 skills');
    for (const g of l.grows || []) {
      if (!own.has(g)) { L(`grows unknown skill "${g}"`); continue; }
      const s = skills.find(x => x.id === g);
      for (const n of s.needs || []) if (own.has(n) && !grown.has(n) && !(l.grows || []).includes(n)) L(`grows ${g} before anything grew ${n}`);
    }
    (l.grows || []).forEach(g => grown.add(g));
    if (!MINUTES.includes(l.minutes)) L(`minutes ${l.minutes}`);
    if (!(Number.isInteger(l.steps) && l.steps >= 4 && l.steps <= 7)) L(`steps ${l.steps}`);
    if (!CHECKS.includes(l.check)) L(`check "${l.check}"`);
    if (!str(l.passes, 90)) L(`passes missing or over 90 characters (${(l.passes || '').length})`);
  });
  for (const s of skills) if (!grown.has(s.id)) E(`no lesson grows ${s.id}`);
  const text = JSON.stringify([p.title, p.line, pr, lessons.map(l => [l.title, l.goal, l.passes])]);
  const bad = text.match(BANNED);
  if (bad) E(`banned word or mark "${bad[0]}"`);
}
// skill ids must be unique across the whole catalog
const where = {};
for (const p of plans) for (const s of p.skills || []) { if (where[s.id] && where[s.id] !== p.id) errs.push(`${p._file}: skill id ${s.id} is already used by ${where[s.id]}`); where[s.id] = p.id; }

if (errs.length) { console.error(errs.join('\n')); console.error(`\n${errs.length} problem(s) in ${plans.length} plans`); process.exit(1); }
const sum = p => p.lessons.reduce((a, l) => a + l.minutes, 0);
console.log(`${plans.length} plans, ${plans.reduce((a, p) => a + p.lessons.length, 0)} lessons, ${plans.reduce((a, p) => a + p.skills.length, 0)} skills: all rules pass`);
if (process.argv.includes('--check')) process.exit(0);

const ORDER = { language: 0, environment: 1, topic: 2 };
plans.sort((a, b) => ORDER[a.group] - ORDER[b.group] || (a.level === b.level ? 0 : a.level === 'start' ? -1 : 1) || a.title.localeCompare(b.title));
const playlistsFile = join(here, 'playlists.json');
const playlists = existsSync(playlistsFile) ? JSON.parse(readFileSync(playlistsFile, 'utf8')) : [];
const out = plans.map(({ _file, ...p }) => ({ ...p, minutes: sum(p), playlists: playlists.filter(x => x.planId === p.id && x.verified) }));
writeFileSync(join(here, 'catalog.json'), JSON.stringify({ version: 1, plans: out }, null, 1));
writeFileSync(join(here, 'catalog.js'), 'window.CATALOG = ' + JSON.stringify({ version: 1, plans: out }) + ';\n');
const hr = m => m < 90 ? `${m} min` : `${Math.round(m / 30) / 2} hr`;
let md = `# miyagi lesson plans\n\n${plans.length} plans, ${plans.reduce((a, p) => a + p.lessons.length, 0)} lessons. Generated by build.mjs from plans/*.json. Do not edit by hand.\n`;
for (const [g, name] of [['language', 'Coding languages'], ['environment', 'Apps and tools'], ['topic', 'Going further']]) {
  md += `\n## ${name}\n\n| Plan | Works in | Lessons | Time | Ends with |\n|---|---|---|---|---|\n`;
  for (const p of out.filter(p => p.group === g)) md += `| ${p.title} | ${p.tool.label} | ${p.lessons.length} | ${hr(p.minutes)} | ${p.project.title} |\n`;
}
for (const p of out) {
  md += `\n### ${p.title}\n\n${p.line} Works in ${p.tool.label}.${p.needs.length ? ` After ${p.needs.map(n => byId[n].title).join(', ')}.` : ''}\n\n| # | Lesson | Grows | Min | Passes when |\n|---|---|---|---|---|\n`;
  p.lessons.forEach((l, i) => { md += `| ${i + 1} | ${l.title} | ${l.grows.map(g => p.skills.find(s => s.id === g).label).join(', ')} | ${l.minutes} | ${l.passes} |\n`; });
  md += `\nProject: **${p.project.title}**. ${p.project.brief}\n`;
  if (p.playlists.length) md += `\nPlaylists to start from: ${p.playlists.map(x => `[${x.title}](${x.url}) by ${x.channel} (${x.videoCount} videos)`).join('; ')}\n`;
}
writeFileSync(join(here, 'CATALOG.md'), md);
console.log('wrote catalog.json, catalog.js, CATALOG.md');

// social (Nov 24): Friends and the leaderboard, for MIC-84 and MIC-85. Loaded after v4.js. It adds screens and
// changes none: the Friends item in the sidebar appears only on the screens below (and on home-friends, which shows
// where the board sits on Home). Specs: ../social/LEADERBOARD.md and ../social/FRIENDS.md.
// Rules the screens follow: friends only, by code or link; a learner is their bon, in their color, at its level
// (no photos, no bios, no messages); the board counts steps passed this week; a week with no steps has no place.
(() => {
  Object.assign(I, {
    people: '<circle cx="9" cy="8.5" r="3.2"/><path d="M3 19.5c.6-3.2 3-4.9 6-4.9s5.4 1.7 6 4.9"/><circle cx="17.2" cy="9.6" r="2.4"/><path d="M17.6 14.5c2 .3 3.3 1.6 3.7 3.9"/>',
    userplus: '<circle cx="10" cy="8.5" r="3.4"/><path d="M3.5 20c.7-3.5 3.3-5.3 6.5-5.3 1.5 0 2.8.4 3.9 1.2M18.5 14v6M15.5 17h6"/>',
    userminus: '<circle cx="10" cy="8.5" r="3.4"/><path d="M3.5 20c.7-3.5 3.3-5.3 6.5-5.3 1.5 0 2.8.4 3.9 1.2M15.5 17h6"/>',
    ban: '<circle cx="12" cy="12" r="8.5"/><path d="m6 6 12 12"/>',
    offline: '<path d="M7 18h10a4 4 0 0 0 1.6-7.7M9.3 6.4A6 6 0 0 1 17.8 10M5.8 9.8A4 4 0 0 0 7 18M4 4l16 16"/>',
    mail: '<rect x="3" y="5.5" width="18" height="13" rx="2.5"/><path d="m4 7.5 8 6 8-6"/>'
  });

  // ---------- bon, drawn as the app draws it (features/buddy/Character.tsx: the sprout, calm, levels 1 to 8) ----------
  const INK = '#141414', PAD = '#30D158', BARK = '#A07A5C';
  const SKIN = { sand: ['#E9DFC6', '#F6F6F3', '#F4A7BF'], butter: ['#F6DE8E', '#FBEDBE', '#F4A7BF'], peach: ['#FFC4A3', '#FBD5BE', '#F4A7BF'], pink: ['#F4A7BF', '#F9C5D5', '#E98BA8'],
    lilac: ['#D9D2FF', '#ECE8FF', '#F9C5D5'], sky: ['#9CCFF2', '#C5E4F9', '#F9C5D5'], mint: ['#96E4C8', '#BFE6DA', '#F9C5D5'] };
  const LEVELS = [['Seed', 0], ['Sprout', 3], ['Shoot', 8], ['Sapling', 15], ['Budding', 25], ['In bloom', 40], ['Young tree', 60], ['Bonsai', 90]];
  const levelFor = n => LEVELS.reduce((l, [, at], i) => n >= at ? i + 1 : l, 1);
  const leafD = (d, ax, ay, s = 1) => `M${ax} ${ay} C${ax + 4.4 * s * d} ${ay + s} ${ax + 8.6 * s * d} ${ay - 1.2 * s} ${ax + 9.8 * s * d} ${ay - 5.4 * s} C${ax + 5.2 * s * d} ${ay - 7 * s} ${ax + s * d} ${ay - 4.8 * s} ${ax} ${ay} Z`;
  const upD = (ax, ay, s = 1) => `M${ax} ${ay} C${ax - 3.4 * s} ${ay - 2.2 * s} ${ax - 3.1 * s} ${ay - 6.6 * s} ${ax} ${ay - 9.4 * s} C${ax + 3.1 * s} ${ay - 6.6 * s} ${ax + 3.4 * s} ${ay - 2.2 * s} ${ax} ${ay} Z`;
  const padD = (cx, by, w, h) => `M${cx - w / 2} ${by} a${w * .22} ${h * .5} 0 0 1 ${w * .2} ${-h * .62} a${w * .3} ${h * .55} 0 0 1 ${w * .6} 0 a${w * .22} ${h * .5} 0 0 1 ${w * .2} ${h * .62} Z`;
  const ROUND = 'M24 12.6 C33.6 12.6 40.4 19.6 40.4 29.4 C40.4 37.8 33.8 43.2 24 43.2 C14.2 43.2 7.6 37.8 7.6 29.4 C7.6 19.6 14.4 12.6 24 12.6 Z';
  const TRUNK = 'M24 14 C21.6 10.4 26.8 7.4 24.4 3.4 C23.2 1 24.4 -1.4 24 -3.2', STEM_TOP = [8.2, 8.2, 4.4, 3.2, 3.2, 2.6, 3.8, -3.2];
  function bon(level, skin = 'sand', w = 30) {
    const [body, skinLeaf, blush] = SKIN[skin], tree = level >= 7, leaf = tree ? PAD : skinLeaf, wood = tree ? BARK : skinLeaf, O = 1.7, wide = tree ? 2.4 : 1.5;
    const part = d => `<path d="${d}" fill="${leaf}" stroke="${INK}" stroke-width="${O}" stroke-linejoin="round"/>`;
    const twig = (d, sw) => `<path d="${d}" fill="none" stroke="${INK}" stroke-width="${O * 2 + sw}" stroke-linecap="round"/><path d="${d}" fill="none" stroke="${wood}" stroke-width="${sw}" stroke-linecap="round"/>`;
    const low = level <= 2 ? [8.6, 1] : level === 3 ? [9.4, 1] : level <= 6 ? [9.8, 1] : [10.4, .84];
    let s = twig(level === 8 ? TRUNK : `M24 14 L24 ${STEM_TOP[level - 1]}`, wide);
    if (level === 8) s += twig('M23 10.8 L18.4 9', 1.4) + twig('M25.8 6.4 L30.2 5', 1.4) + part(padD(16.6, 9.2, 11, 5.6)) + part(padD(31.6, 5.2, 11, 5.6)) + part(padD(24.2, -2.4, 14, 7));
    if (level >= 2 && level <= 7) s += part(leafD(-1, 24, low[0], low[1]));
    if (level <= 7) s += part(leafD(1, 24, low[0], low[1]));
    if (level === 3) s += part(upD(24, 4.8, .84));
    if (level >= 4 && level <= 6) s += part(leafD(-1, 24, 3.8, .72)) + part(leafD(1, 24, 3.8, .72));
    if (level === 5) s += `<circle cx="24" cy=".6" r="2.8" fill="#F4A7BF" stroke="${INK}" stroke-width="${O}"/>`;
    if (level === 6) { for (let k = 0; k < 5; k++) { const t = (-90 + k * 72) * Math.PI / 180; s += `<circle cx="${(24 + 3.1 * Math.cos(t)).toFixed(2)}" cy="${(-.8 + 3.1 * Math.sin(t)).toFixed(2)}" r="2.4" fill="#F9C5D5" stroke="${INK}" stroke-width="1.3"/>`; }
      s += `<circle cx="24" cy="-.8" r="1.7" fill="#F4A7BF" stroke="${INK}" stroke-width="1.1"/>`; }
    if (level === 7) s += part(padD(24, 4.6, 17, 8.6));
    s += `<path d="${ROUND}" fill="${body}" stroke="${INK}" stroke-width="${O}" stroke-linejoin="round"/>`;
    s += `<ellipse cx="14.6" cy="31.8" rx="2.5" ry="1.5" fill="${blush}"/><ellipse cx="33.4" cy="31.8" rx="2.5" ry="1.5" fill="${blush}"/>`;
    for (const x of [18.4, 29.6]) s += `<ellipse cx="${x}" cy="27.2" rx="2.3" ry="3.1" fill="${INK}"/><circle cx="${x + .9}" cy="26" r=".8" fill="#fff"/>`;
    s += `<path d="M21.6 32.8 Q24 35.4 26.4 32.8" fill="none" stroke="${INK}" stroke-width="1.6" stroke-linecap="round"/>`;
    return `<svg class="bon" viewBox="-1 -11 50 56" style="width:${w}px;height:${(w * 1.12).toFixed(1)}px">${s}</svg>`;
  }

  // ---------- the people in the mock: [name, color, steps passed in all, this week, today, last week, skills mastered, plan id, friends since] ----------
  const ME = { n: 'Sam', skin: 'sand', all: 58, wk: 6, td: 2, lw: 9, sk: 11, plan: 'neural-networks', me: true };
  const F = [
    { n: 'Maya', skin: 'pink', all: 71, wk: 14, td: 3, lw: 11, sk: 16, plan: 'intro-blender', since: 'Nov 3' },
    { n: 'Leo', skin: 'sky', all: 19, wk: 9, td: 0, lw: 4, sk: 5, plan: 'intro-python', since: 'Nov 12' },
    { n: 'Priya', skin: 'lilac', all: 33, wk: 6, td: 1, lw: 12, sk: 8, plan: '', since: 'Oct 28' },
    { n: 'Jonah', skin: 'mint', all: 5, wk: 2, td: 0, lw: 3, sk: 1, plan: 'intro-cad', since: 'Nov 18' },
    { n: 'Ava', skin: 'butter', all: 2, wk: 0, td: 0, lw: 2, sk: 0, plan: null, since: 'Nov 20' }
  ];
  const NOOR = { n: 'Noor', skin: 'peach', all: 9 }, THEO = { n: 'Theo', skin: 'butter', all: 44 }, ELI = { n: 'Eli', skin: 'mint', all: 27 }, KAI = { n: 'Kai', skin: 'sky', all: 16 };
  const lv = p => levelFor(p.all), lvName = p => LEVELS[lv(p) - 1][0];
  const av = (p, w = 30) => bon(lv(p), p.skin, w);
  const who = (p, sub) => `<div class="who">${av(p)}<b>${p.n}</b>${p.me ? '<span class="you">you</span>' : ''}${sub || ''}</div>`;
  const planOf = p => p.plan ? PL(p.plan).title : p.plan === '' ? 'A lesson of their own' : '';
  const CODE = 'K7M2-Q9XD', LINK = 'miyagi.study/add/K7M2Q9XD';
  // Places: the same number of steps is the same place, and the next place skips. No steps this week, no place.
  const placed = (list, key) => { const s = [...list].sort((a, b) => b[key] - a[key]); let last = -1, place = 0;
    return s.map((p, i) => { if (p[key] !== last) { place = i + 1; last = p[key]; } return { p, place: p[key] ? place : 0 }; }); };
  const ord = n => n + (['th', 'st', 'nd', 'rd'][n % 100 > 10 && n % 100 < 14 ? 0 : n % 10] || 'th');

  // ---------- the shell, with Friends under Progress ----------
  const navF = (on, badge) => `<div class="sr${on ? ' on' : ''}">${ic('people')}<span class="t">Friends</span>${badge ? `<span class="r">${badge}</span>` : ''}</div>`;
  const withNav = (html, on, badge) => html.replace('<span class="t">Progress</span></div>', m => m + navF(on, badge));
  const shellF = (crumbs, actions, body, o = {}) => withNav(shell3('friends', crumbs, actions, body, o), true, o.badge);
  const dash = (main, rail, after = '') => `<div class="scroll"><div class="dash"><div>${main}<div style="height:60px"></div></div><div class="rail">${rail}</div></div>${after}</div>`;
  const wide = (inner, after = '') => `<div class="scroll"><div class="col w2">${inner}<div style="height:60px"></div></div>${after}</div>`;
  const tabs = (on, o = {}) => { const T = [['board', 'Leaderboard'], ['list', 'Friends', o.friends != null ? o.friends : F.length]];
    return `<div class="tabs">${T.map(([id, t, n]) => `<b class="${id === on ? 'on' : ''}">${t}${n != null ? `<span class="cnt" style="margin-left:0">${n}</span>` : ''}</b>`).join('')}<div class="sp"></div>${o.right || ''}</div>`; };
  const title = (o = {}) => `<div class="titlerow"><h1>Friends</h1><div class="sp"></div><button class="btn quiet">${ic('userplus')}Add a friend</button>${o.cont === false ? '' : `<button class="btn primary">${ic('play')}Continue Broadcasting ${kbd('↩')}</button>`}</div>`;
  const moreBtn = `<svg class="ic" viewBox="0 0 24 24">${I.more}</svg>`;
  const copyBtn = `<div class="tbtn">${ic('copy')}</div>`;

  // ---------- the board ----------
  function boardTable(o = {}) {
    const all = [ME, ...(o.friends || F)], rows = placed(all, 'wk'), top = Math.max(...all.map(p => p.wk), 1);
    const tr = ({ p, place }) => `<tr class="${p.me ? 'me' : ''}${place ? '' : ' rest'}"><td class="rk${place ? '' : ' no'}">${place || ''}</td><td>${who(p)}</td>
      <td>${place ? `<div class="wkb"><div class="bar"><i style="width:${p.wk / top * 100}%"></i></div><b>${p.wk}</b></div>` : '<span style="font-size:13px">No steps yet this week</span>'}</td>
      <td class="td r">${p.td ? '+' + p.td : ''}</td><td class="r mu nw">${lvName(p)}</td></tr>`;
    return `<table class="tbl lb${o.stale ? ' stale' : ''}"><tr><th class="rk"></th><th>Learner</th><th style="width:236px">Steps passed</th><th class="r" style="width:64px">Today</th><th class="r" style="width:104px">bon</th></tr>${rows.map(tr).join('')}</table>`;
  }
  function lastWeekTable(o = {}) {
    const all = [ME, ...(o.friends || F)], rows = placed(all, 'lw'), top = Math.max(...all.map(p => p.lw), 1);
    return `<table class="tbl lb fin"><tr><th class="rk"></th><th>Learner</th><th style="width:236px">Steps passed</th><th class="r" style="width:168px"></th></tr>
      ${rows.map(({ p, place }) => `<tr class="${p.me ? 'me' : ''}"><td class="rk">${place}</td><td>${who(p).replace(/width:30px;height:33.6px/, 'width:24px;height:26.9px')}</td><td><div class="wkb"><div class="bar"><i style="width:${p.lw / top * 100}%"></i></div><b>${p.lw}</b></div></td><td></td></tr>`).join('')}</table>`;
  }
  const railMe = () => `<div class="mybon">${bon(lv(ME), ME.skin, 76)}<div><b>${lvName(ME)}</b><span>Level ${lv(ME)} of 8 · ${ME.all} steps passed</span><div class="bar"><i style="width:${(ME.all - 40) / 20 * 100}%"></i></div><span style="margin-top:7px">2 steps to Young tree</span></div></div>`;
  const reqRail = (p, when, dis) => `<div class="rrow tall">${av(p, 26)}<div class="l2"><b>${p.n}</b><span>${when}</span></div><span class="acts"><button class="btn primary sm${dis ? ' dis' : ''}">Accept</button><button class="btn quiet sm${dis ? ' dis' : ''}">Decline</button></span></div>`;
  const codeRail = teen => `${teen ? `<div class="rrow"><span class="l">Invite link</span><span class="r">1 waiting · 6 days left</span></div><div class="rrow"><span class="l">New link, for one friend</span>${chevRow}</div>` : `<div class="rrow"><span class="l">Your code</span><span class="fcode">${CODE}</span>${copyBtn}</div><div class="rrow"><span class="l">Invite link</span>${copyBtn}</div>`}<div class="rrow"><span class="l">Enter a friend's code</span>${chevRow}</div>`;

  function board(o = {}) {
    const main = `${title()}${tabs('board')}
      ${o.state || ''}
      ${quietLink(sec('This week', o.stale ? 'Nov 16 to 22' : 'Nov 16 to 22 · ends tonight')).replace('class="sec"', 'class="sec" style="margin-top:22px"')}
      ${boardTable(o)}
      ${quietLink(sec('Last week', 'Nov 9 to 15'))}
      ${lastWeekTable(o)}`;
    const rail = `${railMe()}
      ${sec('Your week', 'Progress')}
      <div class="rrow"><span class="l">Place</span><span class="r">3rd, tied with Priya</span></div>
      <div class="rrow"><span class="l">To pass Leo</span><span class="r">4 steps</span></div>
      <div class="rrow"><span class="l">Last week</span><span class="r">3rd · 9 steps</span></div>
      <div class="rrow"><span class="l">All six of you</span><span class="r">37 steps · 41 last week</span></div>
      ${sec('Requests', 'All 2')}
      ${reqRail(NOOR, 'Today', o.stale)}
      ${sec('Add a friend')}
      ${codeRail(o.teen)}`;
    return shellF(['Friends'], '', dash(main, rail), { badge: 2 });
  }

  // Your own weeks: what the page has to show before anyone else is on it. It comes from this Mac, so it needs no server.
  const myWeeks = () => { const W = [['This week', 6, 'Nov 16 to 22'], ['Last week', 9, 'Nov 9 to 15'], ['Nov 2 to 8', 14, 'Your best week'], ['Oct 26 to Nov 1', 7, ''], ['Oct 19 to 25', 5, ''], ['Oct 12 to 18', 8, ''], ['Oct 5 to 11', 3, ''], ['Sep 28 to Oct 4', 4, '']];
    return `${quietLink(sec('Your weeks', 'steps passed'))}<table class="tbl lb fin"><tr><th style="width:150px">Week</th><th>Steps passed</th><th class="r" style="width:120px"></th></tr>
      ${W.map(([t, n, d], i) => `<tr class="${i ? '' : 'me'}"><td class="${i < 2 ? '' : 'mu'}" style="padding-left:0">${i < 2 ? `<b class="t">${t}</b>` : t}</td><td><div class="wkb"><div class="bar"><i style="width:${n / 14 * 100}%"></i></div><b>${n}</b></div></td><td class="r mu nw">${d}</td></tr>`).join('')}</table>`; };
  const seesRows = (o = {}) => `<div class="rrow"><span class="l">Name</span><span class="r">Sam</span></div>
      <div class="rrow"><span class="l">bon</span><span class="r">Sand · In bloom</span></div>
      <div class="rrow"><span class="l">Steps passed each week</span><span class="r">6 this week</span></div>
      <div class="rrow"><span class="l">Skills mastered</span><span class="r">11</span></div>
      <div class="rrow"><span class="l">Your plan</span><span class="r">${o.teen ? 'Not shared under 18' : 'Neural networks from scratch'}</span></div>`;
  const codeGrid = quiet => `<div class="addgrid" style="margin-top:${quiet ? 4 : 26}px"><div><div class="lab">Your code</div><div class="bigcode">${CODE}</div><div class="btns"><button class="btn ${quiet ? 'quiet' : 'primary'}">${ic('copy')}Copy code</button><button class="btn quiet">${ic('link')}Copy link</button></div></div>
        <div><div class="lab">A friend's code</div><div class="bigcode blank">XXXX-XXXX</div><div class="btns"><button class="btn quiet dis">Send request</button></div></div></div>`;

  // First run: Friends is off until the learner turns it on. Until then nothing about them is sent or shown.
  function first(o = {}) {
    const main = `<div class="titlerow"><h1>Friends</h1></div>
      <div class="lede">${o.lede || 'Friends is off. Nobody sees your name, your bon or your steps.'}</div>
      <div style="margin-top:18px">${o.cta || `<button class="btn primary">Turn on Friends ${kbd('↩')}</button>`}</div>
      ${myWeeks()}`;
    const rail = `${railMe()}${sec('A friend would see')}${seesRows(o)}`;
    return shellF(['Friends'], '', dash(main, rail, o.after || ''));
  }
  // On, and nobody added yet.
  function empty() {
    const main = `${title()}<div class="lede">Add a friend to see your week next to theirs.</div>${codeGrid()}${myWeeks()}`;
    const rail = `${railMe()}${sec('A friend sees', 'Settings')}${seesRows()}`;
    return shellF(['Friends'], '', dash(main, rail));
  }
  // Not signed in: friends need an account.
  const guest = () => first({ lede: 'Friends needs an account. Your steps so far come with you.', cta: '<button class="btn primary">Continue with Google</button>' })
    .replace('<b>Sam Rivera</b><span>Free</span>', '<b>Not signed in</b><span></span>').replace('<div class="av">S</div>', '<div class="av"></div>');

  // ---------- Friends: requests waiting, the list, adding ----------
  const inc = (p, when) => `<div class="frq"><div class="who">${av(p, 34)}<div><b>${p.n}</b><span>${lvName(p)}</span></div></div><span class="m">${when}</span><span class="acts"><button class="btn primary sm">Accept</button><button class="btn quiet sm">Decline</button></span><div class="tbtn">${ic('more')}</div></div>`;
  const out = (p, when) => `<div class="frq"><div class="who">${av(p, 34)}<div><b>${p.n}</b><span>${lvName(p)}</span></div></div><span class="m">${when}</span><span class="acts"><button class="btn quiet sm">Cancel request</button></span></div>`;
  const reqBlock = () => `<div class="sgrid rq"><div>${sec('Requests<span class="cnt">2</span>')}${inc(NOOR, 'Today')}${inc(THEO, 'Friday')}</div><div>${sec('Sent<span class="cnt">1</span>')}${out(ELI, 'Thursday')}</div></div>`;
  const rowMenu = p => `<div class="menu"><div>${ic('user')}See ${p.n}</div><hr><div class="hov">${ic('userminus')}Remove friend</div><div>${ic('ban')}Block</div></div>`;
  function listTable(o = {}) {
    return `<table class="tbl"><tr><th>Friend</th><th style="width:118px">bon</th><th class="r" style="width:92px">This week</th><th class="r" style="width:92px">Skills</th><th style="width:250px;padding-left:36px">Plan</th><th style="width:118px">Friends since</th><th></th></tr>
      ${F.map(p => `<tr class="${o.sel === p.n ? 'pick' : ''}"><td>${who(p)}</td><td class="mu">${lvName(p)}</td><td class="r mu">${p.wk}</td><td class="r mu">${p.sk}</td><td class="mu" style="padding-left:36px">${planOf(p)}</td><td class="mu">${p.since}</td><td class="more">${moreBtn}${o.menu === p.n ? rowMenu(p) : ''}</td></tr>`).join('')}</table>`;
  }
  const listPage = (o = {}) => `${title({ cont: false })}${tabs('list')}
      ${reqBlock()}
      ${sec(`Friends<span class="cnt">${F.length}</span>`)}${listTable(o)}
      ${sec('Add a friend')}
      ${codeGrid(true)}`;
  const list = () => shellF(['Friends'], '', wide(listPage()), { badge: 2 });

  // the menu on a friend's row
  const listMenu = () => shellF(['Friends'], '', wide(listPage({ sel: 'Maya', menu: 'Maya' })), { badge: 2 });
  const confirm = (p, h, body, yes, extra = '') => `<div class="scrim"><div class="pop modal ask2">${who(p).replace('width:30px;height:33.6px', 'width:40px;height:44.8px')}<h2>${h}</h2><p>${body}</p>${extra}
    <div class="mfoot"><button class="btn quiet">Cancel</button><button class="btn primary">${yes}</button></div></div></div>`;
  const removeAsk = () => shellF(['Friends'], '', wide(listPage({ sel: 'Maya' }), confirm(F[0], 'Remove Maya?', 'You leave each other\'s boards. Maya is not told. Either of you can send a new request later.', 'Remove')), { badge: 2 });
  const blockAsk = () => shellF(['Friends'], '', wide(listPage({ sel: 'Maya' }), confirm(F[0], 'Block Maya?', 'Maya is removed and can no longer send you a request or find you by code. Maya is not told.', 'Block',
    `<div class="opt"><span class="cb off"><svg viewBox="0 0 12 12"><path d="m2.6 6.3 2.3 2.3 4.6-4.9"/></svg></span>Also report this name to miyagi</div>`)), { badge: 2 });

  // ---------- a friend: the side panel holds everything a friend can see ----------
  function friend() {
    const p = F[0], W = [['This week', p.wk, ME.wk], ['Last week', p.lw, ME.lw], ['Nov 2 to 8', 9, 14], ['Oct 26 to Nov 1', 6, 7]];
    const peek = `<div class="peek"><div class="ptop"><div class="tbtn">${ic('peek')}</div><span>Friends</span><i style="font-style:normal;color:var(--ghost)">/</i><b style="font-weight:500;color:var(--text)">${p.n}</b><span style="flex:1"></span><div class="tbtn">${ic('more')}</div></div>
      <div class="pbon">${bon(lv(p), p.skin, 84)}<div><h2>${p.n}</h2><span>${lvName(p)} · level ${lv(p)} of 8</span></div></div>
      <dl class="props"><dt>${ic('progress')}This week</dt><dd>${p.wk} steps passed · 1st</dd>
        <dt>${ic('check')}Steps in all</dt><dd>${p.all}</dd>
        <dt>${ic('skills')}Skills mastered</dt><dd>${p.sk}</dd>
        <dt>${ic('list')}Plan</dt><dd>${planOf(p)}</dd>
        <dt>${ic('people')}Friends since</dt><dd>${p.since}</dd></dl>
      <div class="lab">Steps passed, week by week</div>
      <table class="tbl sm"><tr><th>Week</th><th class="r" style="width:80px">${p.n}</th><th class="r" style="width:80px">You</th></tr>
        ${W.map(([t, a, b]) => `<tr><td class="mu">${t}</td><td class="n2">${a >= b ? `<b>${a}</b>` : a}</td><td class="n2">${b > a ? `<b>${b}</b>` : b}</td></tr>`).join('')}</table>
      <div style="flex:1"></div>
      <div class="pfoot"><button class="btn quiet">${ic('userminus')}Remove friend</button><button class="btn quiet">${ic('ban')}Block</button></div></div>`;
    return shellF(['Friends', p.n], '', wide(listPage({ sel: 'Maya' }), peek), { badge: 2 });
  }

  // ---------- add a friend ----------
  function addModal(o = {}) {
    const typed = o.typed, found = o.found;
    const right = `<div class="lab">A friend's code</div><div class="bigcode ${typed ? 'in' : 'blank'}">${typed ? `${typed}<span class="caret"></span>` : 'XXXX-XXXX'}</div>
      ${found ? `<div class="found">${who(found, '').replace('width:30px;height:33.6px', 'width:36px;height:40.3px').replace(`<b>${found.n}</b>`, `<div><b>${found.n}</b><span>${lvName(found)}</span></div>`)}<button class="btn primary">Send request ${kbd('↩')}</button></div>
        <div class="note">${found.n} sees your name and your bon, and can accept or decline.</div>`
        : o.miss ? `<div class="note" style="color:var(--text)">No one has that code. Check it with your friend.</div><div class="btns"><button class="btn quiet dis">Send request</button></div>`
        : `<div class="btns"><button class="btn quiet dis">Send request</button></div>`}`;
    const left = o.teen
      ? `<div class="lab">Invite one friend</div><div class="linkrow">${ic('link')}<span>miyagi.study/add/T4VW8HJN</span><em>1 use · 7 days</em></div>
        <div class="btns"><button class="btn primary">${ic('copy')}Copy link</button><button class="btn quiet">New link</button></div>
        <div class="note">A link works once, for one friend, then stops. You still accept their request.</div>`
      : `<div class="lab">Your code</div><div class="bigcode">${CODE}</div>
        <div class="btns"><button class="btn primary">${ic('copy')}Copy code</button><button class="btn quiet">${ic('link')}Copy link</button></div>
        <div class="note">A friend types it here, or opens the link. You still accept their request. <a>Get a new code</a></div>`;
    return `<div class="scrim"><div class="pop modal add"><div class="titlerow"><h2>Add a friend</h2><div class="sp"></div><div class="tbtn">${ic('x')}</div></div>
      <div class="addgrid"><div>${left}</div><div>${right}</div></div></div></div>`;
  }
  const add = () => shellF(['Friends'], '', dashBoard() + addModal(), { badge: 2 });
  const addFound = () => shellF(['Friends'], '', dashBoard() + addModal({ typed: 'R3HT-6WNC', found: ELI }), { badge: 2 });
  const addMiss = () => shellF(['Friends'], '', dashBoard() + addModal({ typed: 'R3HT-6WNG', miss: true }), { badge: 2 });
  // the board, as the page behind a dialog
  function dashBoard(o) { const html = board(o); return html.slice(html.indexOf('<div class="scroll">'), html.lastIndexOf('</main>')); }

  // ---------- states ----------
  const offline = () => board({ stale: true, state: `<div class="state">${ic('offline')}You're offline. This is the board from 4:12 PM.<span class="sp"></span><a>Your own steps still count</a></div>` });
  // Turned off after having friends: they are kept, and nothing is shared until it is on again.
  function off() {
    const main = `<div class="titlerow"><h1>Friends</h1></div>
      <div class="lede">Friends is off. Nobody sees your name, your bon or your steps.</div>
      <div style="margin-top:18px"><button class="btn primary">Turn on Friends ${kbd('↩')}</button></div>
      ${myWeeks()}`;
    const rail = `${railMe()}
      ${sec('While it is off')}
      <div class="rrow"><span class="l">Your 5 friends</span><span class="r">Kept, hidden from you</span></div>
      <div class="rrow"><span class="l">Their boards</span><span class="r">You are not on them</span></div>
      <div class="rrow"><span class="l">Your code</span><span class="r">Does not work</span></div>
      <div class="rrow"><span class="l">New requests</span><span class="r">Not received</span></div>`;
    return shellF(['Friends'], '', dash(main, rail));
  }

  // ---------- Home: where the board sits day to day ----------
  function homeFriends() {
    const rows = placed([ME, ...F], 'wk').filter(r => r.place).slice(0, 4).map(({ p, place }) => `<div class="rrow${p.me ? ' me' : ''}"><span class="rk">${place}</span>${av(p, 22)}<span class="l">${p.me ? 'You' : p.n}</span><span class="r">${p.td ? `+${p.td} today · ` : ''}${p.wk}</span></div>`).join('');
    const block = `${sec('Friends this week', 'Leaderboard')}${rows}`;
    return withNav(SCREENS.home(), false, 2).replace('<div class="sec">Goal</div>', block + '<div class="sec">Goal</div>');
  }

  // ---------- Settings > Friends ----------
  const lockv = t => `<span class="lockv">${ic('lock')}${t}</span>`;
  function setShell(body) {
    return shellSet('friends', body).replace('<b>undefined</b>', '<b>Friends</b>')
      .replace(/(<span class="t">Your data<\/span><\/div>)/, `$1<div class="sr on">${ic('people')}<span class="t">Friends</span></div>`);
  }
  function settingsFriends(o = {}) {
    const teen = o.teen, never = t => frow(t, '', '<span class="v">Never shown</span>');
    const left = `${shd('Sharing')}
      ${frow('Friends', teen ? 'On since Nov 14. A parent or guardian agreed.' : 'Add friends and put your week next to theirs.', tog(true))}
      ${frow('Name friends see', 'A first name or a nickname.', `<span class="v">Sam</span>${qb('Change')}`)}
      ${teen ? frow('Invite links', 'Each link works once, for one friend, for 7 days.', '<span class="v">1 waiting</span>' + qb('Cancel it')) : frow('Your code', 'Anyone with it can send you a request.', `<span class="fcode">${CODE}</span>${qb('New code')}`)}
      ${frow('bon', 'Friends see its color and its level.', `<span class="v">${bon(lv(ME), ME.skin, 22)}Sand · In bloom</span>`)}
      ${shd('What friends see')}
      ${frow('Steps passed each week', 'This week and the weeks before it.', '<span class="v">Always, with Friends on</span>')}
      ${frow('Skills mastered', 'The number. Not which ones.', tog(true))}
      ${teen ? frow('The plan you are on', 'Not shared under 18.', lockv('Off')).replace('class="frow"', 'class="frow off"') : frow('The plan you are on', 'Its name. A lesson you made yourself is never named.', tog(true))}
      ${frow('Sit out the leaderboard', 'Keep your friends. Your steps are left off every board.', tog(false))}`;
    const right = `${shd('Never shown to anyone')}
      ${never('Your email and last name')}${never('Your age and birthday')}${never('Minutes, times of day, and when you were last here')}${never('Your lessons, code, screen and questions')}${never('Steps you skipped or did not pass')}
      ${shd('Blocked<span class="cnt">1</span>')}
      ${frow(`<div class="who">${av(KAI, 24)}<b>Kai</b></div>`, '', qb('Unblock'))}
      ${shd('Leave')}
      ${frow('Remove all friends', teen ? 'Your board empties and waiting links stop working.' : 'Your board empties and your code is replaced.', qb('Remove all'))}`;
    return setShell(`<div class="scroll"><div class="col w2"><h1>Friends</h1><div class="sgrid"><div>${left}</div><div>${right}</div></div><div style="height:60px"></div></div></div>`);
  }

  // ---------- 13 to 17 ----------
  // The same page and the same rules, with three differences: turning Friends on asks for the same "My parent or
  // guardian agrees" the birthday step asks for at setup; invites are single links, not a standing code; and the plan
  // is not shared. The app holds only an age band (13 to 17, or 18 and over), never a birthday.
  const onDialog = teen => `<div class="scrim"><div class="pop modal ask2" style="width:452px"><h2>Turn on Friends</h2>
      <div class="lab" style="margin-top:16px">A friend sees</div>${seesRows({ teen })}
      <p style="font-size:13px">These are kept by miyagi while Friends is on, so your friends' apps can show them.</p>
      ${teen ? `<div class="opt">${tick}My parent or guardian agrees</div>` : ''}
      <div class="mfoot"><button class="btn quiet">Not now</button><button class="btn primary">Turn on ${kbd('↩')}</button></div></div></div>`;
  const turnOn = () => first({ after: onDialog(false) });
  const teenOn = () => first({ teen: true, after: onDialog(true) });
  const teenAdd = () => shellF(['Friends'], '', dashBoard({ teen: true }) + addModal({ teen: true }), { badge: 2 });
  const teenSettings = () => settingsFriends({ teen: true });

  Object.assign(SCREENS, { friends: board, 'friends-first': first, 'friends-on': turnOn, 'friends-empty': empty, 'friends-guest': guest, 'friends-list': list, 'friends-menu': listMenu, 'friends-remove': removeAsk, 'friends-block': blockAsk, friend,
    'friends-add': add, 'friends-add-found': addFound, 'friends-add-miss': addMiss, 'friends-offline': offline, 'friends-off': off,
    'home-friends': homeFriends, 'settings-friends': settingsFriends, 'friends-teen-on': teenOn, 'friends-teen-add': teenAdd, 'settings-friends-teen': teenSettings });
  RENDER();
})();

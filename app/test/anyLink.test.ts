// Any link (ANY-LINK.md), the app side: which pasted text is a page, how a page is named, the card's one action,
// and the library keeping a page lesson's source (features/anylink/link.ts, features/library/sanitize.ts).
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { linkKey, lookupLine, pageAction, pageSource, parseWebLink, safeWebUrl, sameLink, siteOf } from '../src/renderer/src/features/anylink/link'
import { cleanItem } from '../src/renderer/src/features/library/sanitize'

test('a pasted page is a link: docs, articles, GitHub repos, with or without https', () => {
  assert.deepEqual(parseWebLink('https://docs.python.org/3/tutorial/venv.html'), { url: 'https://docs.python.org/3/tutorial/venv.html', kind: 'web', site: 'docs.python.org' })
  assert.deepEqual(parseWebLink('  github.com/pallets/flask  '), { url: 'https://github.com/pallets/flask', kind: 'github', site: 'github.com/pallets/flask' })
  assert.equal(parseWebLink('https://github.com/Pallets/Flask.git')?.site, 'github.com/pallets/flask')
  assert.equal(parseWebLink('www.example.co/blog')?.kind, 'web')
  assert.equal(parseWebLink('realpython.com')?.url, 'https://realpython.com/')
  assert.equal(parseWebLink('developer.mozilla.org/en-US/docs/Web')?.site, 'developer.mozilla.org')
})

test('typed goals with a dot stay goals, and YouTube stays with the video flow', () => {
  for (const t of ['numpy.array', 'node.js', 'learn pandas', 'pd.read_csv', 'fix my code.', '3.14', 'install.sh', 'deploy.sh', 'Notes.app', 'about.me'])
    assert.equal(parseWebLink(t), null, t)
  // Those TLDs still count with a path, a "www." or a scheme.
  assert.equal(parseWebLink('bun.sh/docs')?.url, 'https://bun.sh/docs')
  assert.equal(parseWebLink('www.vercel.app')?.kind, 'web')
  assert.equal(parseWebLink('https://deno.sh')?.url, 'https://deno.sh/')
  for (const t of ['https://www.youtube.com/watch?v=dQw4w9WgXcQ', 'youtu.be/dQw4w9WgXcQ', 'https://m.youtube.com/playlist?list=x'])
    assert.equal(parseWebLink(t), null, t)
})

test('local, private, odd-port and credentialed links are never pages', () => {
  for (const t of ['http://localhost:3000', 'https://printer.local/', 'http://192.168.1.4/admin', 'https://user:pw@example.com/',
    'https://example.com:8443/x', 'file:///Users/me/notes.html', 'javascript:alert(1)', 'mailto:a@b.co', 'ftp://example.com/x'])
    assert.equal(parseWebLink(t), null, t)
  assert.equal(safeWebUrl('https://example.com:443/a'), 'https://example.com/a')
  assert.equal(safeWebUrl('https://exa mple.com'), undefined)
})

test('github.com pages that are not a repo read as a web page', () => {
  assert.equal(parseWebLink('https://github.com/settings/profile')?.kind, 'web')
  assert.equal(siteOf('https://github.com/explore'), 'github.com')
  assert.equal(siteOf('https://github.com/pallets/flask/tree/main/docs'), 'github.com/pallets/flask')
})

test('two spellings of one page match (so a preview finds the link that asked)', () => {
  assert.ok(sameLink('http://www.docs.python.org/3/tutorial/venv.html/#creating', 'https://docs.python.org/3/tutorial/venv.html?utm_source=x'))
  assert.ok(sameLink('https://github.com/Pallets/Flask.git', 'https://github.com/pallets/flask'))
  assert.ok(sameLink('https://a.com/x?b=2&a=1', 'https://a.com/x?a=1&b=2'))
  assert.ok(!sameLink('https://a.com/x', 'https://a.com/y'))
  assert.equal(linkKey('not a link'), undefined)
})

test('the card does what ANY-LINK.md says: build, start cached, teach the title, wait, or nothing', () => {
  assert.deepEqual(pageAction(undefined), { kind: 'wait', label: 'Reading the page…' })
  assert.deepEqual(pageAction({ pending: true, title: 'Flask' }), { kind: 'wait', label: 'Reading the page…' })
  assert.deepEqual(pageAction({ teachable: true }), { kind: 'build', label: 'Build lesson' })
  assert.deepEqual(pageAction({ teachable: true, cached: true }), { kind: 'build', label: 'Start lesson' })
  assert.deepEqual(pageAction({ teachable: false, title: 'Why I switched editors' }, 'Just teach me'), { kind: 'teach', label: 'Just teach me', goal: 'Why I switched editors' })
  assert.deepEqual(pageAction({ teachable: false }), { kind: 'none', label: '' })
  assert.deepEqual(pageAction({ error: 'blocked', teachable: true }), { kind: 'none', label: '' })
  assert.equal(lookupLine('blocked'), 'That site won’t let miyagi read it.')
  assert.equal(lookupLine(undefined), lookupLine('unknown'))
})

test('the library keeps a page lesson’s source, with a safe link only', () => {
  const base = { id: 'web-w_4f1c0e9a', title: 'Virtual environments and pip', steps: 4, tools: ['terminal'], ready: true }
  const web = cleanItem({ ...base, source: { kind: 'web', title: 'Venv', url: 'https://docs.python.org/3/tutorial/venv.html', site: 'docs.python.org', author: 'PSF' } })
  assert.deepEqual(web?.source, { kind: 'web', title: 'Venv', url: 'https://docs.python.org/3/tutorial/venv.html', site: 'docs.python.org', author: 'PSF' })
  const gh = cleanItem({ ...base, source: { kind: 'github', title: 'Flask', url: 'https://github.com/pallets/flask' } })
  assert.equal(gh?.source?.site, 'github.com/pallets/flask')
  assert.equal(cleanItem({ ...base, source: { kind: 'web', title: 'x', url: 'http://localhost:8000/' } })?.source, undefined)
  assert.equal(cleanItem({ ...base, source: { kind: 'web', title: 'x', url: 'javascript:alert(1)' } })?.source, undefined)
  assert.equal(cleanItem({ ...base, source: { kind: 'web', title: 'x' } })?.source, undefined)
  assert.equal(pageSource(web?.source)?.kind, 'web')
  assert.equal(pageSource({ kind: 'youtube', title: 'v', url: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ' }), undefined)
})

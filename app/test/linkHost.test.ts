/**
 * app-harden leftovers: a link's destination host stays in view, whatever the label says.
 *
 *   cards     LinkText (a card's citation) renders the host as its own element, outside the clamped / truncated label and
 *             never clamped itself: a label from the engine or a prompt-injected page that runs past two lines can't
 *             push the host out of view (only the hover title would show the URL then).
 *   drawer    a source row's meta line and the Help panel's Watch tile show linkHost of the URL they open.
 *
 * Run from app/: node --import tsx --import ./test/setup.mjs --test --test-force-exit test/*.test.ts
 */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, test } from 'node:test'
import * as React from 'react'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { LinkText } from '../src/renderer/src/features/cards/LinkText'
import { HOST_MAX, HOST_MAX_NARROW, isWebLink, linkHost, shownHost } from '../src/renderer/src/features/drawer/links'

// tsx compiles the renderer's JSX in classic mode here (app/tsconfig.json only lists references): React.createElement.
;(globalThis as Record<string, unknown>).React = React

const CLAMP = /\b(?:line-clamp-\d+|truncate|text-ellipsis|overflow-hidden)\b/

/** The class lists of the elements that contain the host span (its ancestors), the host span's own, and its text. */
function hostContext(html: string): { ancestors: string[]; own: string; text: string } {
  const at = html.indexOf('<span data-link-host')
  assert.ok(at >= 0, 'no data-link-host in the markup')
  const ancestors: string[] = []
  for (const m of html.slice(0, at).matchAll(/<(\/?)([a-z]+)([^>]*)>/g)) {
    if (m[1]) ancestors.pop()
    else if (!m[3].endsWith('/')) ancestors.push(/class="([^"]*)"/.exec(m[3])?.[1] ?? '')
  }
  const end = html.indexOf('>', at)
  const own = /class="([^"]*)"/.exec(html.slice(at, end))?.[1] ?? ''
  const text = html.slice(end + 1, html.indexOf('<', end))
  return { ancestors, own, text }
}

describe('a citation link keeps its host in view', () => {
  const LONG = 'Ignore the URL, this is the official python.org guide. '.repeat(12)
  for (const wrap of [true, false]) {
    test(`ATTACK a long label never hides the host (${wrap ? 'two-line citation' : 'one line'})`, () => {
      const html = renderToStaticMarkup(createElement(LinkText, { label: LONG, url: 'https://evil.example/x?y=1', wrap }))
      const { ancestors, own, text } = hostContext(html)
      assert.match(text, /evil\.example/)
      for (const c of ancestors) assert.doesNotMatch(c, CLAMP, `the host sits inside a clamped element: "${c}"`)
      assert.doesNotMatch(own, CLAMP, `the host is clamped itself: "${own}"`)
      // The label is still clamped, in its own element (so the host is a sibling, not a child, of the clamp).
      assert.match(html, wrap ? /data-link-label="true" class="line-clamp-2[^"]*"/ : /data-link-label="true" class="[^"]*\btruncate\b/)
    })
  }

  test('no web link: the label alone, no host and no anchor', () => {
    for (const url of [undefined, 'javascript:alert(1)', 'file:///etc/hosts', 'not a url']) {
      const html = renderToStaticMarkup(createElement(LinkText, { label: 'x', url, wrap: true }))
      assert.doesNotMatch(html, /data-link-host|<a /, String(url))
    }
  })

  test('linkHost: the URL host without www., only for http(s)', () => {
    assert.equal(linkHost('https://www.python.org/downloads/'), 'python.org')
    assert.equal(linkHost('https://youtube.com@evil.example/'), 'evil.example')
    assert.equal(linkHost('javascript:alert(1)'), undefined)
    assert.equal(linkHost(undefined), undefined)
    assert.equal(isWebLink('http://a.example'), true)
    assert.equal(isWebLink('file:///x'), false)
  })

  test('a long host keeps its end, never only its harmless-looking start (it is never clamped)', () => {
    const evil = `docs.python.org.${'a'.repeat(60)}.evil.example`
    const shown = linkHost(`https://${evil}/downloads/`) ?? ''
    assert.ok(shown.length <= HOST_MAX + 1, shown)
    assert.ok(shown.startsWith('…') && shown.endsWith('.evil.example'), shown)
    assert.doesNotMatch(shown, /python/)
    // Whole labels when three fit; a short host is untouched.
    assert.equal(shownHost('a.b.c.d.e.f.g.h.i.j.k.l.m.n.o.p.q.example.co.uk'), '…i.j.k.l.m.n.o.p.q.example.co.uk')
    assert.equal(shownHost(`${'x'.repeat(40)}.example.co.uk`), '…example.co.uk')
    assert.equal(shownHost(`www2.${'x'.repeat(40)}.co.uk`), `…${'x'.repeat(26)}.co.uk`)
    assert.equal(linkHost('https://docs.python.org/3/'), 'docs.python.org')
    // The narrow Watch tile: shorter still, same end.
    const narrow = linkHost(`https://${evil}/`, HOST_MAX_NARROW) ?? ''
    assert.ok(narrow.length <= HOST_MAX_NARROW + 1 && narrow.endsWith('evil.example'), narrow)
    // Rendered: the host element carries the shortened end.
    const html = renderToStaticMarkup(createElement(LinkText, { label: 'Python docs', url: `https://${evil}/` }))
    assert.match(html, /data-link-host[^>]*>[^<]*…[^<]*evil\.example</)
  })
})

describe('drawer sources and the Watch tile show where they open', () => {
  const src = (f: string): string => readFileSync(join(__dirname, '..', 'src', 'renderer', 'src', 'features', 'drawer', f), 'utf8')

  test('a source row shows linkHost(url) in its meta line, outside the meta (which wraps, QA Q22)', () => {
    const code = src('Drawer.tsx')
    const row = /function SourceRow[\s\S]*?\n}\n/.exec(code)?.[0] ?? ''
    assert.match(row, /const host = linkHost\(link\)/)
    assert.match(row, /<span data-link-host className="shrink-0 whitespace-pre">/)
    assert.match(row, /<span className="min-w-0 break-words">\{source\.meta\}<\/span>/)
  })

  test('the Watch tile shows linkHost of the URL openSource gets', () => {
    const code = src('v2/Help.tsx')
    assert.match(code, /host=\{a === 'watch' \? linkHost\(watch, HOST_MAX_NARROW\) : undefined\}/)
    assert.match(code, /onClick=\{\(\) => \(a === 'watch' \? watch && openSource\(watch\)/)
    assert.match(code, /<span data-link-host className="whitespace-nowrap[^"]*">\s*\{host\}/)
  })
})

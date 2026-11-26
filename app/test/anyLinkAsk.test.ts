/**
 * features/anylink/store.ts with a fake bridge, offline: how often the app asks the engine about a page. Each link.get
 * on a web link costs the engine a page fetch, a robots.txt fetch and a model call (ANY-LINK.md), so typing a URL key
 * by key sends at most one link.get (for the settled link, never for its prefixes), a paste or drop asks at once, an
 * older waiting link is never sent once a newer one replaced it, nothing is sent without link.any + link.get, and the
 * store keeps a bounded number of links.
 */
import assert from 'node:assert/strict'
import { mkdtempSync, writeFileSync } from 'node:fs'
import { registerHooks } from 'node:module'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, beforeEach, mock, test } from 'node:test'
import { pathToFileURL } from 'node:url'

// Vite-only modules (import.meta.glob scenarios, the feature registry, assets) resolve to small stand-ins.
const dir = mkdtempSync(join(tmpdir(), 'anylink-ask-'))
const stub = (name: string, source: string): string => (writeFileSync(join(dir, name), source), pathToFileURL(join(dir, name)).href)
const EMPTY = stub('empty.mjs', 'export const scenarios = {}\nexport const defineFeature = (f) => f\nexport default ""')
registerHooks({
  resolve(specifier, context, next) {
    if (/(^|\/)mock\/scenarios$/.test(specifier) || (context.parentURL?.includes('/src/renderer/') && /(^|\/)registry$/.test(specifier))) return { url: EMPTY, shortCircuit: true }
    if (/\.(svg|png|jpe?g|webp|css|mp3|wav|woff2?)(\?.*)?$|\?(raw|url|inline)$/.test(specifier)) return { url: EMPTY, shortCircuit: true }
    return next(specifier, context)
  }
})

const sends: { type: string; payload: Record<string, unknown> }[] = []
const g = globalThis as unknown as Record<string, unknown>
const noop = (): (() => void) => () => {}
const tut = {
  platform: { os: 'darwin', keys: {}, pillTop: 0 },
  onEvent: noop,
  onStatus: noop,
  on: noop,
  onFeature: noop,
  emit: () => {},
  ready: () => {},
  send: (m: { type: string; payload: Record<string, unknown> }) => void sends.push(m),
  invoke: () => Promise.resolve(null)
}
g.window = { tut, devicePixelRatio: 2, innerWidth: 1440, innerHeight: 900, addEventListener: () => {}, removeEventListener: () => {}, matchMedia: () => ({ matches: false, addEventListener: () => {}, removeEventListener: () => {} }) }
g.document = { documentElement: { dataset: { route: 'launcher' } }, getElementById: () => ({}), createElement: () => ({}), head: { prepend: () => undefined }, addEventListener: () => {}, hidden: false }
g.location = { search: '' }

const { dispatch } = require('../src/renderer/src/core/bus') as typeof import('../src/renderer/src/core/bus')
const { parseWebLink } = require('../src/renderer/src/features/anylink/link') as typeof import('../src/renderer/src/features/anylink/link')
const store = require('../src/renderer/src/features/anylink/store') as typeof import('../src/renderer/src/features/anylink/store')
const { askLink, askLinkNow, askLinkSoon, dropLink, useAnyLink, LINK_SETTLE_MS, MAX_LINKS } = store

const hello = (capabilities: string[]): void => dispatch({ type: 'engine.hello', payload: { version: 'test', capabilities } } as never)
const gets = (): string[] => sends.filter((m) => m.type === 'link.get').map((m) => String(m.payload.url))

/** The launcher's effect on each keystroke: what's typed → parseWebLink → askLinkSoon(page?.url). */
function typeKeys(text: string, gapMs: number, from = 0): void {
  for (let i = from + 1; i <= text.length; i++) {
    askLinkSoon(parseWebLink(text.slice(0, i))?.url)
    mock.timers.tick(gapMs)
  }
}

beforeEach(() => {
  mock.timers.enable({ apis: ['setTimeout', 'Date'] })
  sends.length = 0
  askLinkSoon(undefined)
  useAnyLink.setState({ previews: {}, asked: {}, dropped: undefined })
  hello(['link.get', 'link.any', 'learn_url'])
})
afterEach(() => mock.timers.reset())

test('typing a URL key by key sends at most one link.get, for the settled link', () => {
  typeKeys('docs.python.org/3/tutorial/venv.html', 40)
  assert.deepEqual(gets(), [])
  mock.timers.tick(LINK_SETTLE_MS)
  assert.deepEqual(gets(), ['https://docs.python.org/3/tutorial/venv.html'])
  // Nothing more later, and the same link settling again is free.
  askLinkSoon('https://docs.python.org/3/tutorial/venv.html')
  mock.timers.tick(LINK_SETTLE_MS * 4)
  assert.equal(gets().length, 1)
})

test('a slow typist pausing mid-link asks only about where they paused, never every prefix', () => {
  typeKeys('docs.python.org', 40)
  mock.timers.tick(LINK_SETTLE_MS) // a pause long enough to settle on "docs.python.org"
  typeKeys('docs.python.org/3/tutorial/venv.html', 40, 'docs.python.org'.length)
  mock.timers.tick(LINK_SETTLE_MS)
  assert.deepEqual(gets(), ['https://docs.python.org/', 'https://docs.python.org/3/tutorial/venv.html'])
})

test('a newer link replaces the one waiting: the older one is never sent', () => {
  askLinkSoon('https://example.com/a')
  mock.timers.tick(LINK_SETTLE_MS - 1)
  askLinkSoon('https://example.com/b')
  mock.timers.tick(LINK_SETTLE_MS - 1)
  assert.deepEqual(gets(), [])
  mock.timers.tick(1)
  assert.deepEqual(gets(), ['https://example.com/b'])
  // Clearing the box (no link) cancels the waiting one.
  askLinkSoon('https://example.com/c')
  askLinkSoon(undefined)
  mock.timers.tick(LINK_SETTLE_MS * 2)
  assert.deepEqual(gets(), ['https://example.com/b'])
})

test('a paste (or a drop, or Enter) asks at once and cancels a typed link still waiting', () => {
  askLinkSoon('https://docs.python.org/3/tut')
  assert.equal(askLinkNow('https://github.com/pallets/flask'), true)
  assert.deepEqual(gets(), ['https://github.com/pallets/flask'])
  // The launcher's effect then sees the pasted link: already asked, so no second link.get.
  askLinkSoon('https://github.com/pallets/flask')
  mock.timers.tick(LINK_SETTLE_MS * 2)
  assert.deepEqual(gets(), ['https://github.com/pallets/flask'])
})

test('no link.get at all unless the engine lists link.any and link.get', () => {
  hello(['link.get', 'learn_url'])
  typeKeys('docs.python.org/3/', 10)
  mock.timers.tick(LINK_SETTLE_MS)
  assert.equal(askLinkNow('https://example.com/x'), false)
  assert.deepEqual(gets(), [])
})

test('the store keeps at most MAX_LINKS links (oldest go first), and keeps the dropped one', () => {
  dropLink('https://dropped.example.com/page')
  askLink('https://dropped.example.com/page')
  for (let i = 0; i < MAX_LINKS * 3; i++) {
    const url = `https://example.com/p${i}`
    askLink(url)
    const reqId = sends.at(-1)?.payload.reqId
    dispatch({ type: 'link.preview', payload: { url, reqId, kind: 'web', pending: false, title: `P${i}`, teachable: true } } as never)
  }
  const s = useAnyLink.getState()
  assert.ok(Object.keys(s.asked).length <= MAX_LINKS + 1, `asked: ${Object.keys(s.asked).length}`)
  assert.ok(Object.keys(s.previews).length <= MAX_LINKS + 1, `previews: ${Object.keys(s.previews).length}`)
  assert.ok('https://dropped.example.com/page' in s.asked, 'the dropped link stays')
  assert.ok(`https://example.com/p${MAX_LINKS * 3 - 1}` in s.previews, 'the newest stays')
  assert.ok(!('https://example.com/p0' in s.asked), 'the oldest went')
})

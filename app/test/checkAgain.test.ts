/**
 * Check again (Nov 25, a real learner on a MacBook Neo): every press showed the same bare "Not yet", nothing showed a
 * check running, no Explain / Hint was in reach, and each press brought the miyagi home window forward over VS Code.
 *
 *   - the panel says Checking from the press until the check's own answer, even when another card arrives on the way
 *   - "Not yet" / "Couldn't check" cards (verdict not_done, checkIssue, checkedAt) are the panel's, with their reason
 *   - a press hands the keyboard back to the lesson's app ONCE (open -b), and never opens or focuses a miyagi window
 * Offline: no engine, no window, no `open` is ever run.
 */
import assert from 'node:assert/strict'
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { registerHooks } from 'node:module'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { beforeEach, describe, mock, test } from 'node:test'
import { pathToFileURL } from 'node:url'

const dir = mkdtempSync(join(tmpdir(), 'check-again-'))
const stub = (name: string, source: string): string => (writeFileSync(join(dir, name), source), pathToFileURL(join(dir, name)).href)
const EMPTY = stub('empty.mjs', 'export const scenarios = {}\nexport const defineFeature = (f) => f\nexport default ""')
registerHooks({
  resolve(specifier, context, next) {
    if (/(^|\/)mock\/scenarios$/.test(specifier) || (context.parentURL?.includes('/src/renderer/') && /(^|\/)registry$/.test(specifier))) return { url: EMPTY, shortCircuit: true }
    if (/\.(svg|png|jpe?g|webp|css|mp3|wav|woff2?)(\?.*)?$|\?(raw|url|inline)$/.test(specifier)) return { url: EMPTY, shortCircuit: true }
    return next(specifier, context)
  }
})

const invokes: { channel: string; args: unknown[] }[] = []
const features = new Map<string, (p: unknown) => void>()
const g = globalThis as unknown as Record<string, unknown>
const noop = (): (() => void) => () => {}
const tut = {
  platform: { os: 'darwin', keys: {}, pillTop: 0 },
  onEvent: noop,
  onStatus: noop,
  on: noop,
  onFeature: (channel: string, fn: (p: unknown) => void) => (features.set(channel, fn), () => {}),
  emit: () => {},
  ready: () => {},
  send: () => {},
  invoke: (channel: string, ...args: unknown[]): Promise<unknown> => (invokes.push({ channel, args }), Promise.resolve(null))
}
g.window ??= { tut, devicePixelRatio: 2, innerWidth: 1440, innerHeight: 900, addEventListener: () => {}, removeEventListener: () => {}, matchMedia: () => ({ matches: false, addEventListener: () => {}, removeEventListener: () => {} }) }
g.document ??= { documentElement: { dataset: { route: 'overlay' } }, getElementById: () => ({}), createElement: () => ({}), head: { prepend: () => undefined }, addEventListener: () => {}, hidden: false }
g.location ??= { search: '' }

mock.timers.enable({ apis: ['setTimeout', 'Date'], now: 5_000_000 })

const { dispatch } = require('../src/renderer/src/core/bus') as typeof import('../src/renderer/src/core/bus')
const { sendAction } = require('../src/renderer/src/core/shortcuts') as typeof import('../src/renderer/src/core/shortcuts')
const { useLesson } = require('../src/renderer/src/core/lesson') as typeof import('../src/renderer/src/core/lesson')
const panel = require('../src/renderer/src/features/drawer/v2/panelStore') as typeof import('../src/renderer/src/features/drawer/v2/panelStore')
const focus = require('../src/renderer/src/features/drawer/checkFocus') as typeof import('../src/renderer/src/features/drawer/checkFocus')
const { createHandBack, validBundle, ONCE_MS } = require('../src/main/features/checkFocus') as typeof import('../src/main/features/checkFocus')

const ev = (type: string, payload: Record<string, unknown>): void => dispatch({ type, payload } as never)

describe('Checking holds until the check answers', () => {
  beforeEach(() => {
    ev('lesson.ended', {})
    mock.timers.runAll()
    useLesson.setState({ stepId: 's1' } as never)
  })

  test('another card on the way does not end Checking; the check\'s own card does', () => {
    sendAction('check_step')
    assert.equal(panel.checkingNow(), true)
    ev('status', { state: 'thinking', detail: 'Checking your work' })
    ev('card', { stepId: 's1', kind: 'hint', title: 'Tip', body: 'unrelated' }) // clears the press in core/shortcuts
    mock.timers.tick(5000)
    assert.equal(panel.checkingNow(), true, 'still checking: that card was not the answer')
    ev('card', { stepId: 's1', kind: 'answer', title: 'Not yet', body: 'Add `return a + b` on line 2.', verdict: 'not_done', checkedAt: Date.now() })
    assert.equal(panel.checkingNow(), false)
    assert.equal(panel.usePanel.getState().notYet.card?.body, 'Add `return a + b` on line 2.', 'the panel shows the reason')
  })

  test('a second answer counts as "checked again", and "Couldn\'t check" is the panel\'s too', () => {
    sendAction('check_step')
    ev('card', { stepId: 's1', kind: 'answer', title: 'Not yet', body: 'x', verdict: 'not_done', checkedAt: 1 })
    sendAction('check_step')
    const issue = { kind: 'screen_off', title: "Can't see your screen", body: 'Screen Recording is off for miyagi.', next: 'Turn it on, then press Check again.', blocking: true }
    const card = { stepId: 's1', kind: 'step', title: issue.title, body: `${issue.body}\n${issue.next}`, checkIssue: issue, checkedAt: 2 }
    assert.equal(panel.isNotYetCard(card as never), true)
    ev('card', card)
    assert.equal(panel.checkingNow(), false)
    assert.equal(panel.usePanel.getState().notYet.n, 2)
    assert.equal(panel.usePanel.getState().notYet.card?.checkIssue?.kind, 'screen_off')
  })

  test('the engine\'s thinking ending answers a press that got no card; no answer at all ends as stuck', () => {
    sendAction('check_step')
    ev('status', { state: 'thinking' })
    ev('status', { state: 'watching' })
    assert.equal(panel.checkingNow(), false)
    sendAction('check_step')
    mock.timers.tick(panel.CHECK_MAX_MS + 1)
    assert.equal(panel.checkingNow(), false)
    assert.equal(panel.usePanel.getState().flight?.stuck, true, 'the panel says there was no answer')
  })
})

describe('a Check press hands focus back, never home', () => {
  test('the lesson app is the last front app that was one of the lesson\'s, never miyagi', () => {
    let t = focus.nextTarget(undefined, { known: true, bundle: 'com.microsoft.VSCode', lesson: true })
    t = focus.nextTarget(t, { known: true, bundle: 'dev.sandhacks.miyagi', miyagi: true, lesson: true })
    t = focus.nextTarget(t, { known: true, bundle: 'com.apple.Safari', lesson: false })
    assert.equal(t, 'com.microsoft.VSCode')
    assert.equal(focus.nextTarget(t, { known: true, bundle: 'org.blenderfoundation.blender', lesson: true }), 'org.blenderfoundation.blender')
  })

  test('the press asks main for check:handback with that bundle and nothing else', () => {
    features.get('front:app')?.({ known: true, bundle: 'com.microsoft.VSCode', lesson: true, miyagi: false })
    invokes.length = 0
    focus.handBackAfterCheck()
    assert.deepEqual(invokes, [{ channel: 'check:handback', args: ['com.microsoft.VSCode'] }])
  })

  test('main activates the app once per press, falls back to the last other app, refuses miyagi and junk', () => {
    const activated: string[] = []
    let now = 0
    const hb = createHandBack({ activate: (b) => activated.push(b), previous: () => 'com.apple.Terminal', allowed: () => true, now: () => now })
    assert.equal(hb('com.microsoft.VSCode'), 'com.microsoft.VSCode')
    now += 200
    assert.equal(hb('com.microsoft.VSCode'), undefined, 'a double press is one activation, never a loop')
    now += ONCE_MS
    assert.equal(hb(undefined), 'com.apple.Terminal', 'no hint: the last non-miyagi app')
    now += ONCE_MS
    assert.equal(hb('dev.sandhacks.miyagi'), 'com.apple.Terminal', 'miyagi itself is never the target')
    assert.deepEqual(activated, ['com.microsoft.VSCode', 'com.apple.Terminal', 'com.apple.Terminal'])
    assert.equal(validBundle('com.github.Electron'), undefined)
    assert.equal(validBundle('-a /Applications/Calculator.app'), undefined)
    assert.equal(validBundle('com.microsoft.VSCode; rm -rf ~'), undefined)
    const off = createHandBack({ activate: (b) => activated.push(b), previous: () => 'com.apple.Terminal', allowed: () => false })
    assert.equal(off('com.microsoft.VSCode'), undefined, 'gate closed / not macOS: nothing moves')
  })

  test('the check flow never opens, shows or focuses a miyagi window', async () => {
    const feature = (require('../src/main/features/checkFocus') as typeof import('../src/main/features/checkFocus')).default
    const handlers = new Map<string, (...a: unknown[]) => unknown>()
    const touched: string[] = []
    const spy = (name: string) => () => void touched.push(name)
    const ctx = new Proxy(
      { handle: (channel: string, fn: (...a: unknown[]) => unknown) => void handlers.set(channel, fn) },
      { get: (t, k) => (k in t ? (t as Record<string | symbol, unknown>)[k] : spy(String(k))) }
    )
    const prev = process.env.MIYAGI_HAND_BACK
    process.env.MIYAGI_HAND_BACK = '0' // never run a real `open -b` from a test
    try {
      await feature.setup(ctx as never)
      assert.deepEqual([...handlers.keys()], ['check:handback'])
      assert.equal(handlers.get('check:handback')!('com.microsoft.VSCode'), null)
    } finally {
      if (prev === undefined) delete process.env.MIYAGI_HAND_BACK
      else process.env.MIYAGI_HAND_BACK = prev
    }
    assert.deepEqual(touched, [], `the check flow touched ${touched.join(', ')}`)
    // Nothing on the press path opens the home window (openWindow / openLibrary / window:open / focus).
    const src = ['src/main/features/checkFocus.ts', 'src/renderer/src/features/drawer/checkFocus.ts']
      .map((f) => readFileSync(join(__dirname, '..', f), 'utf8').replace(/\/\*[\s\S]*?\*\/|\/\/[^\n]*/g, ''))
      .join('\n')
    assert.doesNotMatch(src, /openWindow|openLibrary|window:open|window:focus|\.show\(|\.focus\(|app\.focus/)
  })
})

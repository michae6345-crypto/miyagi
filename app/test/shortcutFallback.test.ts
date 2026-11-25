/**
 * A saved shortcut another app owns when main registers it (startup, a lesson starting, the gate opening): main binds
 * the platform default instead (or nothing when that fails too), keeps the override in prefs, tells the windows, and
 * every keycap shows the key really bound (main/shortcutKeys.ts, common/shortcuts.ts, renderer core/keys.ts, Settings).
 * Offline, no Electron: a fake globalShortcut that can refuse keys, and a fake window bridge for the renderer half.
 */
import assert from 'node:assert/strict'
import { mkdtempSync, writeFileSync } from 'node:fs'
import { registerHooks } from 'node:module'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { describe, test } from 'node:test'
import { pathToFileURL } from 'node:url'
import type { ShortcutPrefs } from '../src/common/prefs'
import { effectiveLabel, sanitizeFallbacks, SHORTCUT_KINDS, type ShortcutFallbacks } from '../src/common/shortcuts'
import { describePlatform, type ShortcutKind } from '../src/main/platform'
import { createShortcutKeys, rebind, type KeyOps } from '../src/main/shortcutKeys'

const mac = describePlatform('darwin')

// The renderer's bridge imports mock/scenarios (import.meta.glob, Vite only): an empty stand-in.
const dir = mkdtempSync(join(tmpdir(), 'shortcut-fallback-'))
writeFileSync(join(dir, 'empty.mjs'), 'export const scenarios = {}\nexport default ""')
const EMPTY = pathToFileURL(join(dir, 'empty.mjs')).href
registerHooks({
  resolve(specifier, context, next) {
    if (/(^|\/)mock\/scenarios(\/index)?(\.ts)?$/.test(specifier)) return { url: EMPTY, shortCircuit: true }
    return next(specifier, context)
  }
})

/** A fake globalShortcut: `taken` keys belong to another app (register returns false) until freed. */
function fakeKeys(taken: string[] = []): KeyOps & { held: Map<string, () => void>; taken: Set<string> } {
  const held = new Map<string, () => void>()
  const other = new Set(taken)
  return {
    held,
    taken: other,
    register(acc, fn) {
      if (other.has(acc) || held.has(acc)) return false
      held.set(acc, fn)
      return true
    },
    unregister(acc) {
      held.delete(acc)
    }
  }
}
const noPress = () => () => undefined

describe('rebind with a fallback (pure)', () => {
  test('startup: a taken override falls back to the default', () => {
    const ops = fakeKeys(['Control+Alt+J'])
    const r = rebind({}, { explain: 'Control+Alt+J' }, ops, noPress, { explain: 'Control+Alt+E' })
    assert.deepEqual(r, { bound: { explain: 'Control+Alt+E' }, failed: ['explain'] })
    assert.ok(ops.held.has('Control+Alt+E'))
  })
  test('both taken: left unbound', () => {
    const ops = fakeKeys(['Control+Alt+J', 'Control+Alt+E'])
    assert.deepEqual(rebind({}, { explain: 'Control+Alt+J' }, ops, noPress, { explain: 'Control+Alt+E' }), { bound: {}, failed: ['explain'] })
    assert.equal(ops.held.size, 0)
  })
  test('the old key still comes first (a live swap that fails keeps what worked)', () => {
    const ops = fakeKeys(['Control+Alt+K'])
    const r1 = rebind({}, { explain: 'Control+Alt+J' }, ops, noPress)
    const r2 = rebind(r1.bound, { explain: 'Control+Alt+K' }, ops, noPress, { explain: 'Control+Alt+E' })
    assert.deepEqual(r2.bound, { explain: 'Control+Alt+J' })
    assert.ok(!ops.held.has('Control+Alt+E'))
  })
  test('a fallback another kind holds now is never taken from it', () => {
    const ops = fakeKeys(['Control+Alt+J'])
    const r = rebind({}, { hint: 'Control+Alt+E', explain: 'Control+Alt+J' }, ops, noPress, { explain: 'Control+Alt+E' })
    assert.deepEqual(r.bound, { hint: 'Control+Alt+E' })
  })
})

describe('createShortcutKeys: saved keys another app owns', () => {
  function setup(taken: string[], init: ShortcutPrefs) {
    const ops = fakeKeys(taken)
    const state = { gate: true, launcher: true, lesson: false, overrides: { ...init } }
    const pressed: ShortcutKind[] = []
    const told: ShortcutFallbacks[] = []
    const keys = createShortcutKeys({
      ops,
      defaults: mac.accelerators,
      mac: true,
      kinds: SHORTCUT_KINDS.filter((k) => k !== 'voice_toggle'),
      overrides: () => state.overrides,
      live: (k) => state.gate && (k === 'launcher' ? state.launcher : k !== 'voice_toggle' && state.lesson),
      press: (k) => void pressed.push(k),
      onTaken: (t) => void told.push(t),
      warn: () => undefined
    })
    return { ops, state, keys, pressed, told }
  }

  test('startup: the launcher override is taken, the default works and runs the launcher', () => {
    const { ops, keys, pressed, told, state } = setup(['Control+Alt+Space'], { launcher: 'Control+Alt+Space' })
    keys.sync()
    assert.deepEqual(keys.bound(), { launcher: 'Alt+Space' })
    assert.deepEqual(keys.taken(), { launcher: 'default' })
    assert.deepEqual(told, [{ launcher: 'default' }], 'the windows are told once')
    ops.held.get('Alt+Space')!()
    assert.deepEqual(pressed, ['launcher'])
    assert.deepEqual(state.overrides, { launcher: 'Control+Alt+Space' }, 'the learner’s choice stays saved')
  })

  test('a lesson starting: a taken action key falls back; the lesson ending keeps what was learned', () => {
    const { keys, state, told } = setup(['Control+Alt+J'], { explain: 'Control+Alt+J' })
    keys.sync()
    assert.deepEqual(keys.taken(), {}, 'not registered yet: nothing known')
    state.lesson = true
    keys.sync()
    assert.equal(keys.bound().explain, 'Control+Alt+E')
    assert.deepEqual(keys.taken(), { explain: 'default' })
    state.lesson = false
    keys.sync()
    assert.equal(keys.bound().explain, undefined)
    assert.deepEqual(keys.taken(), { explain: 'default' })
    assert.equal(told.length, 1)
  })

  test('both taken: no key, and the windows hear "none"', () => {
    const { keys, told } = setup(['Control+Alt+Space', 'Alt+Space'], { launcher: 'Control+Alt+Space' })
    keys.sync()
    assert.deepEqual(keys.bound(), {})
    assert.deepEqual(told.at(-1), { launcher: 'none' })
  })

  test('a default another shortcut uses is not a fallback (no two shortcuts on one key)', () => {
    // Explain on ⌃⌥J (taken), Hint on ⌃⌥E (Explain's default): Explain gets no key, Hint keeps ⌃⌥E.
    const { keys, state } = setup(['Control+Alt+J'], { explain: 'Control+Alt+J', hint: 'Control+Alt+E' })
    state.lesson = true
    keys.sync()
    assert.equal(keys.bound().hint, 'Control+Alt+E')
    assert.equal(keys.bound().explain, undefined)
    assert.deepEqual(keys.taken(), { explain: 'none' })
  })

  test('the override comes back once the other app lets it go', () => {
    const { ops, keys, told } = setup(['Control+Alt+Space'], { launcher: 'Control+Alt+Space' })
    keys.sync()
    assert.deepEqual(keys.bound(), { launcher: 'Alt+Space' })
    ops.taken.delete('Control+Alt+Space')
    keys.sync()
    assert.deepEqual(keys.bound(), { launcher: 'Control+Alt+Space' })
    assert.ok(!ops.held.has('Alt+Space'), 'the default goes back to the other apps')
    assert.deepEqual(keys.taken(), {})
    assert.deepEqual(told.at(-1), {})
  })

  test('a later start with the key free: the override just works', () => {
    const { keys } = setup([], { launcher: 'Control+Alt+Space' })
    keys.sync()
    assert.deepEqual(keys.bound(), { launcher: 'Control+Alt+Space' })
    assert.deepEqual(keys.taken(), {})
  })

  test('Reset on a taken row clears it; the default stays bound', () => {
    const { ops, keys, state, told } = setup(['Control+Alt+Space'], { launcher: 'Control+Alt+Space' })
    keys.sync()
    const r = keys.accept({}, state.overrides)
    assert.deepEqual(r, { accepted: {}, refused: [] })
    state.overrides = r.accepted
    keys.sync()
    assert.deepEqual(keys.bound(), { launcher: 'Alt+Space' })
    assert.ok(ops.held.has('Alt+Space'))
    assert.deepEqual(keys.taken(), {})
    assert.deepEqual(told.at(-1), {})
  })

  test('a new key on a taken row replaces the record; another row’s change leaves it', () => {
    const { keys, state } = setup(['Control+Alt+Space'], { launcher: 'Control+Alt+Space' })
    keys.sync()
    const other = keys.accept({ ...state.overrides, explain: 'Control+Alt+J' }, state.overrides)
    assert.deepEqual(other.accepted, { launcher: 'Control+Alt+Space', explain: 'Control+Alt+J' })
    assert.deepEqual(keys.taken(), { launcher: 'default' }, 'still taken, still on the default')
    assert.deepEqual(keys.bound(), { launcher: 'Alt+Space' })
    state.overrides = other.accepted
    const mine = keys.accept({ ...state.overrides, launcher: 'Control+Alt+K' }, state.overrides)
    assert.equal(mine.accepted.launcher, 'Control+Alt+K')
    assert.deepEqual(keys.bound(), { launcher: 'Control+Alt+K' })
    assert.deepEqual(keys.taken(), {})
  })

  test('a lesson key not live: a new override clears what was learned about the old one', () => {
    const { keys, state } = setup(['Control+Alt+J'], { explain: 'Control+Alt+J' })
    state.lesson = true
    keys.sync()
    state.lesson = false
    keys.sync()
    assert.deepEqual(keys.taken(), { explain: 'default' })
    const r = keys.accept({ explain: 'Control+Alt+K' }, state.overrides)
    assert.deepEqual(r.accepted, { explain: 'Control+Alt+K' })
    assert.deepEqual(keys.taken(), {})
  })
})

describe('the live label shows the key really bound', () => {
  const overrides: ShortcutPrefs = { explain: 'Control+Alt+J', launcher: 'Control+Alt+Space' }
  test('effectiveLabel: override, default or nothing', () => {
    assert.equal(effectiveLabel('explain', mac, overrides), '⌃⌥J')
    assert.equal(effectiveLabel('explain', mac, overrides, { explain: 'default' }), '⌃⌥E')
    assert.equal(effectiveLabel('explain', mac, overrides, { explain: 'none' }), undefined)
    assert.equal(effectiveLabel('launcher', mac, overrides, { explain: 'none' }), '⌃⌥Space', 'other kinds untouched')
    assert.equal(effectiveLabel('hint', mac, {}, { hint: 'none' }), '⌃⌥H', 'no override: the fallback means nothing')
  })
  test('sanitizeFallbacks keeps known kinds and values only', () => {
    assert.deepEqual(sanitizeFallbacks({ explain: 'default', hint: 'none', nope: 'none', back: 'yes' }), { explain: 'default', hint: 'none' })
    assert.deepEqual(sanitizeFallbacks(null), {})
    assert.deepEqual(sanitizeFallbacks('explain'), {})
  })

  test('core/keys and the Settings row follow main’s broadcast', async () => {
    const feature = new Map<string, (p: unknown) => void>()
    const g = globalThis as unknown as Record<string, unknown>
    const noop = (): (() => void) => () => {}
    const tut = {
      platform: { ...mac },
      onEvent: noop,
      onStatus: noop,
      on: noop,
      emit: () => {},
      ready: () => {},
      send: () => {},
      onFeature: (ch: string, cb: (p: unknown) => void) => (feature.set(ch, cb), () => feature.delete(ch)),
      invoke: (ch: string) => Promise.resolve(ch === 'prefs:get' ? { shortcuts: overrides } : ch === 'shortcuts:taken' ? { launcher: 'default' } : null)
    }
    g.window = { tut, addEventListener: () => {}, removeEventListener: () => {}, matchMedia: () => ({ matches: false, addEventListener: () => {}, removeEventListener: () => {} }) }
    g.document = { documentElement: { dataset: {} }, getElementById: () => ({}), createElement: () => ({}), head: { prepend: () => undefined } }
    g.location = { search: '' }

    const { liveKeyLabel, useTaken } = require('../src/renderer/src/core/keys') as typeof import('../src/renderer/src/core/keys')
    const { takenLine } = require('../src/renderer/src/features/settings/shortcuts') as typeof import('../src/renderer/src/features/settings/shortcuts')
    await new Promise((r) => setImmediate(r))
    assert.deepEqual(useTaken.getState(), { launcher: 'default' }, 'a window that opens late asks main')
    assert.equal(liveKeyLabel('launcher'), '⌥Space')
    assert.equal(liveKeyLabel('explain'), '⌃⌥J')

    feature.get('shortcuts:taken')!({ explain: 'none', bogus: 'default' })
    assert.deepEqual(useTaken.getState(), { explain: 'none' }, 'the broadcast replaces the map')
    assert.equal(liveKeyLabel('explain'), undefined)
    assert.equal(liveKeyLabel('launcher'), '⌃⌥Space', 'free again: the override shows')

    assert.equal(takenLine('default', mac.keys.explain), 'Another app uses that key. Using ⌃⌥E.')
    assert.equal(takenLine('none', mac.keys.explain), 'Another app uses that key.')
  })
})

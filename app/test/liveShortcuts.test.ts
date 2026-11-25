/**
 * Live custom shortcuts: the label of an accelerator, the key in effect per shortcut, the clash check, main's rebind
 * (main/shortcutKeys.ts, with a fake globalShortcut that can refuse a key) and prefs sanitizing. Offline, no Electron.
 */
import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { join } from 'node:path'
import { describe, test } from 'node:test'
import { DEFAULT_PREFS, isAccelerator, sanitizePrefs, type ShortcutPrefs } from '../src/common/prefs'
import { acceleratorLabel, clashOf, effectiveAccelerators, effectiveLabel, normalizeAccelerator, quitAccelerator, sameAccelerator, SHORTCUT_KINDS } from '../src/common/shortcuts'
import { describePlatform, type ShortcutKind } from '../src/main/platform'
import { patchPrefs, resetPrefsForTests, setShortcutCheck } from '../src/main/prefs'
import { createShortcutKeys, rebind, type KeyOps } from '../src/main/shortcutKeys'
import { clashLine, conflictWith, record, withShortcut } from '../src/renderer/src/features/settings/shortcuts'

const mac = describePlatform('darwin')
const win = describePlatform('win32')

describe('acceleratorLabel', () => {
  test('a Mac writes ⌃⌥⇧⌘ before the key, like the platform labels', () => {
    for (const k of SHORTCUT_KINDS) assert.equal(acceleratorLabel(mac.accelerators[k], true), mac.keys[k], k)
    assert.equal(acceleratorLabel('Control+Alt+J', true), '⌃⌥J')
    assert.equal(acceleratorLabel('Shift+Command+K', true), '⇧⌘K', 'Apple order, whatever the spelling')
    assert.equal(acceleratorLabel('Command+Control+Alt+Shift+F5', true), '⌃⌥⇧⌘F5')
    assert.equal(acceleratorLabel('Option+Up', true), '⌥↑')
    assert.equal(acceleratorLabel('Control+Alt+Enter', true), '⌃⌥↵')
  })
  test('Windows joins words with +', () => {
    for (const k of ['explain', 'diagram', 'show_me', 'hint', 'voice_toggle'] as const) assert.equal(acceleratorLabel(win.accelerators[k], false), win.keys[k], k)
    assert.equal(acceleratorLabel('Control+Shift+Space', false), 'Ctrl+Shift+Space')
    assert.equal(acceleratorLabel('Alt+Left', false), 'Alt+←')
    assert.equal(acceleratorLabel('Super+Alt+k', false), 'Alt+Win+K')
  })
  test('not an accelerator: shown as is', () => {
    assert.equal(acceleratorLabel('E', true), 'E')
  })
})

describe('the key in effect', () => {
  test('override, else default', () => {
    const eff = effectiveAccelerators(mac.accelerators, { explain: 'Control+Alt+J' })
    assert.equal(eff.explain, 'Control+Alt+J')
    assert.equal(eff.hint, mac.accelerators.hint)
    assert.deepEqual(effectiveAccelerators(mac.accelerators, undefined), mac.accelerators)
  })
  test('labels follow the override; fixed keys never change', () => {
    assert.equal(effectiveLabel('explain', mac, {}), '⌃⌥E')
    assert.equal(effectiveLabel('explain', mac, { explain: 'Control+Alt+J' }), '⌃⌥J')
    assert.equal(effectiveLabel('launcher', win, { launcher: 'Alt+K' }), 'Alt+K')
    assert.equal(effectiveLabel('dismiss', mac, { explain: 'Control+Alt+J' }), 'Esc')
    assert.equal(effectiveLabel('settings', mac, {}), '⌘,')
    assert.equal(effectiveLabel('ptt', mac, {}), mac.keys.ptt)
  })
  test('one spelling per key', () => {
    assert.equal(normalizeAccelerator('Option+Ctrl+e'), 'Control+Alt+E')
    assert.ok(sameAccelerator('CmdOrCtrl+K', 'Command+K'))
    assert.ok(!sameAccelerator('Control+Alt+E', 'Control+Shift+E'))
  })
})

describe('clash', () => {
  test('with a default, with an override, with quit', () => {
    assert.equal(clashOf('Control+Alt+H', 'explain', mac.accelerators, {}, true), 'hint')
    assert.equal(clashOf('Option+Control+h', 'explain', mac.accelerators, {}, true), 'hint', 'spelling does not matter')
    assert.equal(clashOf('Control+Alt+J', 'explain', mac.accelerators, { hint: 'Control+Alt+J' }, true), 'hint')
    assert.equal(clashOf('Control+Alt+H', 'explain', mac.accelerators, { hint: 'Control+Alt+J' }, true), undefined, 'hint moved off it')
    assert.equal(clashOf(quitAccelerator(true), 'explain', mac.accelerators, {}, true), 'quit')
    assert.equal(clashOf('Control+Alt+E', 'explain', mac.accelerators, {}, true), undefined, 'its own key is no clash')
  })
  test('the settings page leaves out voice while voice is off', () => {
    assert.equal(conflictWith('Control+Alt+V', 'explain', mac.accelerators, {}, true), undefined)
    assert.equal(conflictWith('Control+Alt+D', 'explain', mac.accelerators, {}, true), 'diagram')
    assert.equal(clashLine('diagram'), 'Diagram already uses that.')
    assert.equal(clashLine('taken'), 'Another app uses that key.')
  })
  test('withShortcut sets or removes one override', () => {
    assert.deepEqual(withShortcut({ hint: 'Alt+J' }, 'explain', 'Alt+K'), { hint: 'Alt+J', explain: 'Alt+K' })
    assert.deepEqual(withShortcut({ hint: 'Alt+J', explain: 'Alt+K' }, 'explain', undefined), { hint: 'Alt+J' })
  })
  test('the recorder makes accelerators, never a bare key', () => {
    const ev = (code: string, key: string, m: Partial<Record<'ctrlKey' | 'altKey' | 'shiftKey' | 'metaKey', boolean>> = {}) => ({ code, key, ctrlKey: false, altKey: false, shiftKey: false, metaKey: false, ...m })
    assert.deepEqual(record(ev('KeyJ', '∆', { ctrlKey: true, altKey: true }), true), { kind: 'accelerator', value: 'Control+Alt+J' })
    assert.equal(record(ev('KeyJ', 'j'), true).kind, 'invalid')
    assert.equal(record(ev('ShiftLeft', 'Shift', { shiftKey: true }), true).kind, 'modifiers')
  })
})

/** A fake globalShortcut: `taken` keys belong to another app; a key registered twice is refused, like Electron. */
function fakeKeys(taken: string[] = []): KeyOps & { held: Map<string, () => void>; log: string[] } {
  const held = new Map<string, () => void>()
  const log: string[] = []
  return {
    held,
    log,
    register(acc, fn) {
      log.push(`+${acc}`)
      if (taken.includes(acc) || held.has(acc)) return false
      held.set(acc, fn)
      return true
    },
    unregister(acc) {
      log.push(`-${acc}`)
      held.delete(acc)
    }
  }
}
const noPress = () => () => undefined

describe('rebind (pure)', () => {
  test('only changed keys move; new keys register', () => {
    const ops = fakeKeys()
    const r1 = rebind({}, { explain: 'Alt+E', hint: 'Alt+H' }, ops, noPress)
    assert.deepEqual(r1, { bound: { explain: 'Alt+E', hint: 'Alt+H' }, failed: [] })
    ops.log.length = 0
    const r2 = rebind(r1.bound, { explain: 'Alt+J', hint: 'Alt+H' }, ops, noPress)
    assert.deepEqual(r2, { bound: { explain: 'Alt+J', hint: 'Alt+H' }, failed: [] })
    assert.deepEqual(ops.log, ['-Alt+E', '+Alt+J'])
    assert.deepEqual([...ops.held.keys()].sort(), ['Alt+H', 'Alt+J'])
  })
  test('a taken key fails and the old key comes back', () => {
    const ops = fakeKeys(['Command+Space'])
    const r1 = rebind({}, { launcher: 'Alt+Space' }, ops, noPress)
    const r2 = rebind(r1.bound, { launcher: 'Command+Space' }, ops, noPress)
    assert.deepEqual(r2, { bound: { launcher: 'Alt+Space' }, failed: ['launcher'] })
    assert.ok(ops.held.has('Alt+Space'))
  })
  test('a failed key with no old key stays unbound', () => {
    const ops = fakeKeys(['Alt+E'])
    assert.deepEqual(rebind({}, { explain: 'Alt+E' }, ops, noPress), { bound: {}, failed: ['explain'] })
  })
  test('two shortcuts can trade keys', () => {
    const ops = fakeKeys()
    const r1 = rebind({}, { explain: 'Alt+E', hint: 'Alt+H' }, ops, noPress)
    const r2 = rebind(r1.bound, { explain: 'Alt+H', hint: 'Alt+E' }, ops, noPress)
    assert.deepEqual(r2, { bound: { explain: 'Alt+H', hint: 'Alt+E' }, failed: [] })
  })
  test('dropping a kind unregisters it', () => {
    const ops = fakeKeys()
    const r1 = rebind({}, { explain: 'Alt+E', launcher: 'Alt+Space' }, ops, noPress)
    const r2 = rebind(r1.bound, { launcher: 'Alt+Space' }, ops, noPress)
    assert.deepEqual(r2.bound, { launcher: 'Alt+Space' })
    assert.deepEqual([...ops.held.keys()], ['Alt+Space'])
  })
})

describe('createShortcutKeys (main controller)', () => {
  function setup(taken: string[] = [], init: ShortcutPrefs = {}) {
    const ops = fakeKeys(taken)
    const state = { gate: false, launcher: false, lesson: false, overrides: { ...init } }
    const pressed: ShortcutKind[] = []
    const keys = createShortcutKeys({
      ops,
      defaults: mac.accelerators,
      mac: true,
      kinds: SHORTCUT_KINDS.filter((k) => k !== 'voice_toggle'),
      overrides: () => state.overrides,
      live: (k) => state.gate && (k === 'launcher' ? state.launcher : k !== 'voice_toggle' && state.lesson),
      press: (k) => void pressed.push(k),
      warn: () => undefined
    })
    return { ops, state, keys, pressed }
  }

  test('nothing registers while the gate is shut; the launcher after it, lesson keys only in a lesson, never voice', () => {
    const { ops, state, keys } = setup()
    state.launcher = true
    keys.sync()
    assert.equal(ops.held.size, 0, 'gate shut: no keys at all')
    state.gate = true
    keys.sync()
    assert.deepEqual(keys.bound(), { launcher: 'Alt+Space' })
    state.lesson = true
    keys.sync()
    assert.equal(keys.bound().explain, 'Control+Alt+E')
    assert.equal(keys.bound().voice_toggle, undefined)
    assert.ok(!ops.held.has('Control+Alt+V'))
    state.lesson = false
    keys.sync()
    assert.deepEqual(keys.bound(), { launcher: 'Alt+Space' })
    state.gate = false
    keys.sync()
    assert.equal(ops.held.size, 0)
  })

  test('startup uses the saved override, and a press reaches its kind', () => {
    const { ops, state, keys, pressed } = setup([], { launcher: 'Control+Alt+Space' })
    Object.assign(state, { gate: true, launcher: true })
    keys.sync()
    assert.deepEqual(keys.bound(), { launcher: 'Control+Alt+Space' })
    ops.held.get('Control+Alt+Space')!()
    assert.deepEqual(pressed, ['launcher'])
  })

  test('accept: a live key swaps at once; a taken one keeps the old key and is not saved', () => {
    const { ops, state, keys } = setup(['Command+Space'])
    Object.assign(state, { gate: true, launcher: true })
    keys.sync()
    const ok = keys.accept({ launcher: 'Control+Alt+Space' }, {})
    assert.deepEqual(ok, { accepted: { launcher: 'Control+Alt+Space' }, refused: [] })
    assert.ok(ops.held.has('Control+Alt+Space') && !ops.held.has('Alt+Space'))
    state.overrides = ok.accepted

    const no = keys.accept({ launcher: 'Command+Space' }, state.overrides)
    assert.deepEqual(no.accepted, { launcher: 'Control+Alt+Space' }, 'the previous override stays')
    assert.deepEqual(no.refused, [{ kind: 'launcher', accelerator: 'Command+Space', reason: 'taken' }])
    assert.deepEqual(keys.bound(), { launcher: 'Control+Alt+Space' })
    assert.ok(ops.held.has('Control+Alt+Space'))
  })

  test('accept: a key not live now is tried once and let go', () => {
    const { ops, state, keys } = setup(['Control+Alt+K'])
    Object.assign(state, { gate: true, launcher: true })
    keys.sync()
    const ok = keys.accept({ explain: 'Control+Alt+J' }, {})
    assert.deepEqual(ok.accepted, { explain: 'Control+Alt+J' })
    assert.ok(!ops.held.has('Control+Alt+J'), 'probed, not kept: no lesson is running')
    const no = keys.accept({ explain: 'Control+Alt+K' }, {})
    assert.deepEqual(no.accepted, {})
    assert.equal(no.refused[0]?.reason, 'taken')
  })

  test('accept: a clash with another shortcut or quit is refused', () => {
    const { keys } = setup()
    assert.deepEqual(keys.accept({ explain: 'Control+Alt+H' }, {}).refused, [{ kind: 'explain', accelerator: 'Control+Alt+H', reason: 'clash' }])
    assert.equal(keys.accept({ explain: 'Control+Alt+Q' }, {}).refused[0]?.reason, 'clash')
    assert.deepEqual(keys.accept({ explain: 'Control+Alt+V' }, {}).accepted, { explain: 'Control+Alt+V' }, 'voice is off: its key is free')
  })

  test('accept: reset goes back to the default live', () => {
    const { ops, state, keys } = setup([], { explain: 'Control+Alt+J' })
    Object.assign(state, { gate: true, lesson: true })
    keys.sync()
    assert.ok(ops.held.has('Control+Alt+J'))
    const r = keys.accept({}, state.overrides)
    assert.deepEqual(r, { accepted: {}, refused: [] })
    assert.ok(ops.held.has('Control+Alt+E') && !ops.held.has('Control+Alt+J'))
  })

  test('accept: a reset whose default another shortcut now has is refused (no lesson)', () => {
    // Explain to ⌃⌥J, then Hint to ⌃⌥E (free then), then Reset on Explain: ⌃⌥E would be on two shortcuts.
    const { ops, keys } = setup([], {})
    const a = keys.accept({ explain: 'Control+Alt+J' }, {})
    const b = keys.accept({ ...a.accepted, hint: 'Control+Alt+E' }, a.accepted)
    assert.deepEqual(b.accepted, { explain: 'Control+Alt+J', hint: 'Control+Alt+E' })
    const r = keys.accept({ hint: 'Control+Alt+E' }, b.accepted)
    assert.deepEqual(r.accepted, { explain: 'Control+Alt+J', hint: 'Control+Alt+E' }, 'explain keeps its override')
    assert.deepEqual(r.refused, [{ kind: 'explain', accelerator: 'Control+Alt+E', reason: 'clash' }])
    assert.equal(ops.held.size, 0, 'nothing is left registered with no lesson')
  })

  test('accept: the same reset during a lesson is refused and every key stays as it was', () => {
    const { ops, state, keys, pressed } = setup([], { explain: 'Control+Alt+J', hint: 'Control+Alt+E' })
    Object.assign(state, { gate: true, lesson: true })
    keys.sync()
    const r = keys.accept({ hint: 'Control+Alt+E' }, state.overrides)
    assert.deepEqual(r.accepted, { explain: 'Control+Alt+J', hint: 'Control+Alt+E' })
    assert.equal(r.refused[0]?.kind, 'explain')
    assert.equal(keys.bound().explain, 'Control+Alt+J')
    assert.equal(keys.bound().hint, 'Control+Alt+E')
    ops.held.get('Control+Alt+E')!()
    ops.held.get('Control+Alt+J')!()
    assert.deepEqual(pressed, ['hint', 'explain'], 'each key still runs its own shortcut')
  })

  test('accept: a reset to a free default still goes through', () => {
    const { keys } = setup([], { explain: 'Control+Alt+J', hint: 'Control+Alt+K' })
    assert.deepEqual(keys.accept({ hint: 'Control+Alt+K' }, { explain: 'Control+Alt+J', hint: 'Control+Alt+K' }), { accepted: { hint: 'Control+Alt+K' }, refused: [] })
  })

  test('the settings page checks a reset the same way (conflictWith on the default)', () => {
    const stored = { explain: 'Control+Alt+J', hint: 'Control+Alt+E' }
    assert.equal(conflictWith(mac.accelerators.explain, 'explain', mac.accelerators, stored, true), 'hint')
    assert.equal(clashLine('hint'), 'Hint already uses that.')
    assert.equal(conflictWith(mac.accelerators.hint, 'hint', mac.accelerators, stored, true), undefined)
  })
})

describe('prefs', () => {
  test('sanitize keeps valid accelerators only', () => {
    const p = sanitizePrefs({ shortcuts: { explain: 'Control+Alt+J', hint: 'J', back: 'Control+Nope+X', nope: 'Alt+K', launcher: 7 } })
    assert.deepEqual(p.shortcuts, { explain: 'Control+Alt+J' })
    assert.deepEqual(DEFAULT_PREFS.shortcuts, {})
  })
  test('Shift alone is not a modifier: it would take capital letters from every app', () => {
    const p = sanitizePrefs({ shortcuts: { explain: 'Shift+E', hint: 'Shift+Shift+H', back: 'Shift+Left', diagram: 'Control+Shift+D' } })
    assert.deepEqual(p.shortcuts, { diagram: 'Control+Shift+D' })
    assert.equal(isAccelerator('Shift+E'), false)
    assert.equal(isAccelerator('Alt+Shift+E'), true)
  })
  test('a prefs:set patch with Shift alone never reaches main', () => {
    resetPrefsForTests()
    const seen: ShortcutPrefs[] = []
    setShortcutCheck((next) => (seen.push(next), next))
    assert.deepEqual(patchPrefs({ shortcuts: { explain: 'Shift+E' } }).shortcuts, {})
    assert.ok(seen.every((n) => !n.explain))
    resetPrefsForTests()
  })
  test('main checks a shortcuts patch before it is kept', () => {
    resetPrefsForTests()
    setShortcutCheck((next, prev) => (next.explain === 'Control+Alt+K' ? prev : next))
    assert.deepEqual(patchPrefs({ shortcuts: { explain: 'Control+Alt+J' } }).shortcuts, { explain: 'Control+Alt+J' })
    assert.deepEqual(patchPrefs({ shortcuts: { explain: 'Control+Alt+K' } }).shortcuts, { explain: 'Control+Alt+J' }, 'refused: the old key stays')
    assert.equal(patchPrefs({ voiceOnStart: true }).shortcuts.explain, 'Control+Alt+J', 'other prefs leave shortcuts alone')
    resetPrefsForTests()
  })
})

test('the login gate still holds every launcher and lesson key (main/loginFirst.check.ts)', () => {
  const out = execFileSync(process.execPath, ['--import', 'tsx', join(__dirname, '..', 'src', 'main', 'loginFirst.check.ts')], { encoding: 'utf8' })
  assert.match(out, /loginFirst\.check: ok/)
})

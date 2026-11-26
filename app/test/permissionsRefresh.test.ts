/**
 * Permissions refresh (Nov 25, MacBook Neo: a learner switched on Accessibility and Screen Recording and setup still said
 * "Not yet"). main/permissionProbe.ts reads a fresh process's grants from miyagi-listen --screens; main/permissions.ts
 * marks the kinds only a restart picks up (`relaunch`), keeps polling while a window watches, and reads again when miyagi
 * comes back to the front.
 * Run from app/: node --import tsx --import ./test/setup.mjs --test test/permissionsRefresh.test.ts
 */
import { describe, test } from 'node:test'
import assert from 'node:assert/strict'
import { parseFreshPerms, relaunchKinds, throttledProbe, type Fresh } from '../src/main/permissionProbe'

// The shared electron fake has no ipcMain (engineIsolation.test.ts adds its own the same way): record the handlers here.
// eslint-disable-next-line @typescript-eslint/no-require-imports
const electron = require('electron') as Record<string, unknown> & { appListeners: [string, (...a: unknown[]) => void][]; BrowserWindow: Record<string, unknown> }
const handlers = new Map<string, (e: unknown, ...a: unknown[]) => unknown>()
if (!electron.ipcMain) Object.defineProperty(electron, 'ipcMain', { value: { handle: (ch: string, fn: (e: unknown, ...a: unknown[]) => unknown) => handlers.set(ch, fn) }, enumerable: true })
if (!electron.BrowserWindow.fromWebContents) electron.BrowserWindow.fromWebContents = () => undefined

describe('permissionProbe (pure)', () => {
  test('parseFreshPerms reads the helper line; an older helper (no perms) answers undefined', () => {
    const line = '{"perms":{"accessibility":"granted","screen":"granted"},"screens":[{"id":1}]}\n'
    assert.deepEqual(parseFreshPerms(line), { screen: 'granted', accessibility: 'granted' })
    assert.equal(parseFreshPerms('{"screens":[]}'), undefined)
    assert.equal(parseFreshPerms(''), undefined)
    assert.equal(parseFreshPerms('garbage'), undefined)
    assert.deepEqual(parseFreshPerms('{"perms":{"screen":"maybe","accessibility":"denied"}}'), { accessibility: 'denied' })
  })

  test('relaunchKinds: granted in a fresh process, not here', () => {
    assert.deepEqual(relaunchKinds({ screen: 'denied', accessibility: 'granted' }, { screen: 'granted', accessibility: 'granted' }), ['screen'])
    assert.deepEqual(relaunchKinds({ screen: 'not-determined', accessibility: 'denied' }, { screen: 'granted', accessibility: 'granted' }), ['screen', 'accessibility'])
    // Off in both: still "Not yet", not a restart.
    assert.deepEqual(relaunchKinds({ screen: 'denied', accessibility: 'denied' }, { screen: 'denied', accessibility: 'denied' }), [])
    // No answer (old helper, missing, timeout): never a guess.
    assert.deepEqual(relaunchKinds({ screen: 'denied' }, undefined), [])
    // An engine in Terminal: unknown here stays unknown.
    assert.deepEqual(relaunchKinds({ screen: 'unknown' }, { screen: 'granted' }), [])
  })

  test('throttledProbe spawns at most once per window and shares one call in flight', async () => {
    let calls = 0
    let t = 0
    const p = throttledProbe(async () => (calls++, { screen: 'granted' } as Fresh), 3000, () => t)
    await Promise.all([p.get(), p.get()])
    assert.equal(calls, 1)
    t = 2999
    assert.deepEqual(await p.get(), { screen: 'granted' })
    assert.equal(calls, 1)
    t = 3000
    await p.get()
    assert.equal(calls, 2)
    p.reset()
    await p.get()
    assert.equal(calls, 3)
  })

  test('a probe that throws reads as no answer', async () => {
    const p = throttledProbe(async () => {
      throw new Error('spawn failed')
    })
    assert.equal(await p.get(), undefined)
  })
})

describe('main/permissions.ts', { skip: process.platform !== 'darwin' && 'macOS reads only' }, () => {
  test('a watched window gets `relaunch` when only a fresh process sees the grant, and a read on coming to the front', async () => {
    const { setupPermissions } = await import('../src/main/permissions')
    const sent: unknown[] = []
    let fresh: Fresh | undefined = { screen: 'denied', accessibility: 'denied' }
    let probes = 0
    const perms = setupPermissions({
      engineExternal: () => false,
      broadcast: (ch, p) => ch === 'permissions' && sent.push(p),
      trusted: () => true,
      probe: async () => (probes++, fresh)
    })
    // The fake reads Screen Recording as not-determined and Accessibility as off.
    const first = await perms.readFull()
    assert.equal(first.screen, 'not-determined')
    assert.equal(first.relaunch, undefined)

    // permissions:get answers the full read (async), and a watch starts the poll.
    const sender = { id: 7, once: () => undefined }
    await handlers.get('feat:permissions:watch')!({ sender }, true)
    await new Promise((r) => setTimeout(r, 20))
    assert.equal(sent.length, 1)

    // The learner switches both on in System Settings: this process still reads them off, a fresh one sees them.
    fresh = { screen: 'granted', accessibility: 'granted' }
    await new Promise((r) => setTimeout(r, 3100)) // past the probe's 3 s window
    const focus = electron.appListeners.filter(([ev]) => ev === 'browser-window-focus').map(([, fn]) => fn)
    assert.ok(focus.length >= 1, 'listens for miyagi coming back to the front')
    for (const fn of focus) fn()
    await new Promise((r) => setTimeout(r, 20))
    const last = sent.at(-1) as { relaunch?: string[] }
    assert.deepEqual(last.relaunch, ['screen', 'accessibility'])
    const got = (await handlers.get('feat:permissions:get')!({ sender })) as { relaunch?: string[] }
    assert.deepEqual(got.relaunch, ['screen', 'accessibility'])
    assert.ok(probes >= 2)

    await handlers.get('feat:permissions:watch')!({ sender }, false)
  })
})

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
  test('one source: relaunch when only a fresh process sees the grant; front events and the AX notification read at once; the poll stops once granted', async () => {
    // The fake's reads, switchable; count the reads to see the poll stop.
    const sp = electron.systemPreferences as Record<string, unknown>
    let screen = 'not-determined'
    let ax = false
    let reads = 0
    sp.getMediaAccessStatus = () => (reads++, screen)
    sp.isTrustedAccessibilityClient = () => ax
    const subs = new Map<string, () => void>()
    sp.subscribeNotification = (name: string, fn: () => void) => (subs.set(name, fn), 1)

    const { setupPermissions } = await import('../src/main/permissions')
    const sent: Array<{ screen: string; accessibility: string; relaunch?: string[] }> = []
    let fresh: Fresh | undefined = { screen: 'denied', accessibility: 'denied' }
    let probes = 0
    const perms = setupPermissions({
      engineExternal: () => false,
      broadcast: (ch, p) => ch === 'permissions' && sent.push(p as (typeof sent)[number]),
      trusted: () => true,
      probe: async () => (probes++, fresh)
    })
    const wait = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms))
    const first = await perms.readFull()
    assert.equal(first.screen, 'not-determined')
    assert.equal(first.relaunch, undefined)

    // A watch reads at once and publishes to every window.
    const sender = { id: 7, once: () => undefined }
    await handlers.get('feat:permissions:watch')!({ sender }, true)
    await wait(20)
    assert.equal(sent.length, 1)

    // Both switched on in System Settings: this process still reads Screen Recording off, a fresh one sees both.
    fresh = { screen: 'granted', accessibility: 'granted' }
    ax = true
    await wait(2300) // past the probe rate limit
    const front = electron.appListeners.filter(([ev]) => ev === 'did-become-active').map(([, fn]) => fn)
    assert.ok(front.length >= 1, 'reads when miyagi comes back to the front')
    for (const fn of front) fn()
    await wait(20)
    assert.equal(sent.at(-1)!.accessibility, 'granted')
    assert.deepEqual(sent.at(-1)!.relaunch, ['screen'])
    // permissions:get answers the same full read.
    const got = (await handlers.get('feat:permissions:get')!({ sender })) as { relaunch?: string[] }
    assert.deepEqual(got.relaunch, ['screen'])
    assert.ok(probes >= 2)

    // The Accessibility notification reads without waiting for the poll.
    assert.ok(subs.has('com.apple.accessibility.api'))
    ax = false
    subs.get('com.apple.accessibility.api')!()
    await wait(1300) // both settle reads (250 and 1200 ms) are done
    assert.equal(sent.at(-1)!.accessibility, 'denied')

    // After a restart both read granted here: no relaunch, and the poll stops (no more reads while nothing changes).
    screen = 'granted'
    ax = true
    await handlers.get('feat:permissions:get')!({ sender })
    assert.equal(sent.at(-1)!.relaunch, undefined)
    const before = reads
    await wait(2300)
    assert.equal(reads, before, 'no polling once both grants read granted')

    await handlers.get('feat:permissions:watch')!({ sender }, false)
  })
})

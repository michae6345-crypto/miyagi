/**
 * Permissions refresh (Nov 25, MacBook Neo: a learner switched on Accessibility and Screen Recording and setup still said
 * "Not yet"). main/permissionProbe.ts reads a fresh process's grants from miyagi-listen --screens; main/permissions.ts
 * marks the kinds only a restart picks up (`relaunch`), keeps polling while a window watches, and reads again when miyagi
 * comes back to the front.
 * Run from app/: node --import tsx --import ./test/setup.mjs --test test/permissionsRefresh.test.ts
 */
import { describe, test } from 'node:test'
import assert from 'node:assert/strict'
import { mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { BACKOFF_AFTER, BACKOFF_MS, parseFreshPerms, relaunchKinds, throttledProbe, type Fresh } from '../src/main/permissionProbe'

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

  test('ten answers that change nothing slow the probe to 10 s, twenty to 30 s; a change speeds it up again', async () => {
    let t = 0
    let calls = 0
    let answer: Fresh = { screen: 'granted' }
    const p = throttledProbe(async () => (calls++, answer), 1000, () => t)
    for (let i = 0; i <= BACKOFF_AFTER; i++) {
      await p.get()
      t += 1000
    }
    const before = calls
    await p.get() // 1 s after the last: backed off, no new call
    assert.equal(calls, before)
    t += BACKOFF_MS[0]
    await p.get()
    assert.equal(calls, before + 1)
    answer = { screen: 'denied' }
    t += BACKOFF_MS[0]
    await p.get() // a change resets the count
    t += 1000
    await p.get()
    assert.equal(calls, before + 3)
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
    await wait(1200) // past the probe rate limit (PROBE_MIN_MS)
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

  type Sent = { screen: string; accessibility: string; relaunch?: string[]; hint?: Record<string, string> }
  const fakeReads = (state: { screen: string; ax: boolean }): void => {
    const sp = electron.systemPreferences as Record<string, unknown>
    sp.getMediaAccessStatus = () => state.screen
    sp.isTrustedAccessibilityClient = () => state.ax
  }
  const wait = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms))

  test('Accessibility never flashes "Restart needed": main is live, a restart is flagged only after 2 s of disagreement', async () => {
    const state = { screen: 'granted', ax: false }
    fakeReads(state)
    const { setupPermissions } = await import('../src/main/permissions')
    const sent: Sent[] = []
    const perms = setupPermissions({ engineExternal: () => false, broadcast: (_c, p) => sent.push(p as Sent), trusted: () => true, probe: async () => ({ screen: 'granted', accessibility: 'granted' }), build: 'b1', place: 'applications' })
    const sender = { id: 21, once: () => undefined }
    await handlers.get('feat:permissions:watch')!({ sender }, true)
    // The fresh process sees Accessibility on a moment before main does: no restart offer.
    let p = await perms.refresh()
    assert.equal(p.relaunch, undefined)
    // main catches up: plain granted.
    state.ax = true
    p = await perms.refresh()
    assert.equal(p.accessibility, 'granted')
    assert.equal(p.relaunch, undefined)
    // A real, lasting disagreement (rare): flagged only once it has lasted 2 s.
    state.ax = false
    assert.equal((await perms.refresh()).relaunch, undefined)
    await wait(2100)
    assert.deepEqual((await perms.refresh()).relaunch, ['accessibility'])
    await handlers.get('feat:permissions:watch')!({ sender }, false)
  })

  test('restart-loop guard: still not seen after one restart on this build → the off-and-on hint, not Restart again', async () => {
    const state = { screen: 'denied', ax: true }
    fakeReads(state)
    const { setupPermissions } = await import('../src/main/permissions')
    const grantsFile = join(mkdtempSync(join(tmpdir(), 'miyagi-perm-')), 'perm-grants.json')
    let relaunched = 0
    const deps = { engineExternal: () => false, broadcast: () => undefined, trusted: () => true, probe: async (): Promise<Fresh> => ({ screen: 'granted', accessibility: 'granted' }), grantsFile, build: 'b1', place: 'applications' as const, relaunch: () => void relaunched++ }
    const sender = { id: 31, once: () => undefined }
    const first = setupPermissions(deps)
    await handlers.get('feat:permissions:watch')!({ sender }, true)
    assert.deepEqual((await first.refresh()).relaunch, ['screen'])
    assert.equal(await handlers.get('feat:permissions:relaunch')!({ sender }), true)
    assert.equal(relaunched, 1)
    await handlers.get('feat:permissions:watch')!({ sender }, false)

    // "After the restart" (same build, same file): macOS still says no here.
    const second = setupPermissions(deps)
    await handlers.get('feat:permissions:watch')!({ sender }, true)
    const p = await second.refresh()
    assert.equal(p.relaunch, undefined)
    assert.equal(p.hint?.screen, 'reset')
    // Granted for real later: the guard is cleared and a later build may offer a restart again.
    state.screen = 'granted'
    assert.equal((await second.refresh()).hint, undefined)
    await handlers.get('feat:permissions:watch')!({ sender }, false)
  })

  test('no probe once every off kind is known to need a restart, and none while no window watches; restricted is its own state', async () => {
    const state = { screen: 'denied', ax: true }
    fakeReads(state)
    const { setupPermissions } = await import('../src/main/permissions')
    let probes = 0
    const perms = setupPermissions({ engineExternal: () => false, broadcast: () => undefined, trusted: () => true, probe: async () => (probes++, { screen: 'granted', accessibility: 'granted' } as Fresh), build: 'b1', place: 'applications' })
    await perms.refresh()
    assert.equal(probes, 0, 'nobody watches: no spawn')
    const sender = { id: 41, once: () => undefined }
    await handlers.get('feat:permissions:watch')!({ sender }, true)
    await perms.refresh()
    assert.equal(probes, 1)
    await wait(1100)
    await perms.refresh()
    assert.equal(probes, 1, 'screen is already known to need a restart: nothing new to learn')
    state.screen = 'restricted'
    const p = await perms.refresh()
    assert.equal(p.screen, 'restricted')
    assert.equal(p.relaunch, undefined)
    assert.equal(p.hint?.screen, 'managed')
    await handlers.get('feat:permissions:watch')!({ sender }, false)
  })

  test('running from the disk image: hint move, never a restart offer', async () => {
    fakeReads({ screen: 'denied', ax: false })
    const { setupPermissions } = await import('../src/main/permissions')
    const perms = setupPermissions({ engineExternal: () => false, broadcast: () => undefined, trusted: () => true, probe: async () => ({ screen: 'denied', accessibility: 'denied' }), build: 'b1', place: 'dmg' })
    const sender = { id: 51, once: () => undefined }
    await handlers.get('feat:permissions:watch')!({ sender }, true)
    const p = await perms.refresh()
    assert.equal(p.place, 'dmg')
    assert.deepEqual(p.hint, { screen: 'move', accessibility: 'move' })
    await handlers.get('feat:permissions:watch')!({ sender }, false)
  })
})

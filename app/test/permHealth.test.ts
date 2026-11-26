// Permission failure-mode matrix (PR #286, hardening for #282), encoded against main/permHealth.ts. No OS calls: each
// case is what Electron, a fresh `miyagi-listen --probe-perms` and the engine would report on that Mac.
import { describe, it } from 'node:test'
import assert from 'node:assert/strict'
import {
  AX_NOTE_RECHECKS_MS,
  FAST_WINDOW_MS,
  POLL_FAST_MS,
  POLL_IDLE_MS,
  appBundlePath,
  installPlace,
  judgePermission,
  nextPollMs,
  type PermEvidence
} from '../src/main/permHealth'
import { PROBE_MIN_MS, parseFreshPerms, relaunchKinds, throttledProbe, type Fresh } from '../src/main/permissionProbe'

const base: PermEvidence = { main: 'denied', place: 'applications', build: '0.9.3' }

describe('install place (App Translocation / disk image)', () => {
  it('finds the bundle from the executable path', () => {
    assert.equal(appBundlePath('/Applications/miyagi.app/Contents/MacOS/miyagi'), '/Applications/miyagi.app')
    assert.equal(
      appBundlePath('/Applications/miyagi.app/Contents/Frameworks/miyagi Helper.app/Contents/MacOS/miyagi Helper'),
      '/Applications/miyagi.app'
    )
  })
  it('tells translocated, dmg, Applications and elsewhere apart', () => {
    assert.equal(installPlace('/private/var/folders/xy/abc/T/AppTranslocation/1B2C-3D/d/miyagi.app'), 'translocated')
    assert.equal(installPlace('/Volumes/miyagi 0.9.3-arm64/miyagi.app'), 'dmg')
    assert.equal(installPlace('/Applications/miyagi.app'), 'applications')
    assert.equal(installPlace('/Users/sam/Applications/miyagi.app'), 'applications')
    assert.equal(installPlace('/Users/sam/Downloads/miyagi.app'), 'other') // not translocated (quarantine cleared): grants stick
    assert.equal(installPlace(''), 'other')
  })
})

describe('#282 probe (miyagi-listen --screens perms): matrix cases', () => {
  it('helper log noise before the JSON line is skipped', () => {
    assert.deepEqual(parseFreshPerms('objc[123]: Class X is implemented in both\n{"perms":{"screen":"granted","accessibility":"denied"},"screens":[]}'), {
      screen: 'granted',
      accessibility: 'denied'
    })
  })
  it('MDM restricted is read as denied in main and never offered a restart', () => {
    assert.deepEqual(relaunchKinds({ screen: 'denied' }, { screen: 'denied' }), [])
  })
  it('stale TCC row after an ad-hoc re-sign: fresh process denied too, so no restart is offered (needs reset-entry copy)', () => {
    assert.deepEqual(relaunchKinds({ accessibility: 'denied' }, { accessibility: 'denied' }), [])
    assert.equal(judgePermission('accessibility', { main: 'denied', probe: 'denied', place: 'applications', build: '2', lastGrantedBuild: '1' }).action, 'reset-entry')
  })
  it(
    'a probe timeout (slow Mac, first Gatekeeper scan) keeps the last good answer instead of dropping the restart offer',
    { todo: 'patch for #282: throttledProbe sets last = r ?? last' },
    async () => {
      let t = 0
      let answer: Fresh | undefined = { screen: 'granted' }
      const p = throttledProbe(async () => answer, 1000, () => t)
      assert.deepEqual(await p.get(), { screen: 'granted' })
      answer = undefined // execFile timed out
      t = 1000
      assert.deepEqual(await p.get(), { screen: 'granted' })
    }
  )
  it('a switch flip shows within about a second while the learner is still in System Settings', { todo: 'patch for #282: POLL_MS 500 while watched, PROBE_MIN_MS 1000' }, () => {
    assert.ok(PROBE_MIN_MS <= 1000)
  })
})

describe('verdicts: the matrix', () => {
  it('screen granted in System Settings while miyagi runs: Electron still says denied, the fresh probe wins', () => {
    const v = judgePermission('screen', { ...base, main: 'denied', probe: 'granted' })
    assert.deepEqual(v, { state: 'granted', action: 'none' })
  })
  it('screen granted but miyagi itself captures in-process: relaunch the app', () => {
    const v = judgePermission('screen', { ...base, main: 'denied', probe: 'granted', mainNeedsIt: true })
    assert.deepEqual(v, { state: 'granted', action: 'relaunch-app' })
  })
  it('screen granted, engine started before the grant still cannot capture: restart the engine, not the app', () => {
    const v = judgePermission('screen', { ...base, main: 'denied', probe: 'granted', engine: false })
    assert.deepEqual(v, { state: 'granted', action: 'restart-engine' })
  })
  it('accessibility is read live in main: no probe needed', () => {
    assert.deepEqual(judgePermission('accessibility', { ...base, main: 'granted' }), { state: 'granted', action: 'none' })
  })
  it('accessibility on but the engine says no for a while: restart the engine', () => {
    const v = judgePermission('accessibility', { ...base, main: 'granted', engine: false })
    assert.equal(v.action, 'restart-engine')
  })
  it('still off, installed properly: open System Settings', () => {
    assert.deepEqual(judgePermission('screen', { ...base, probe: 'denied' }), { state: 'denied', action: 'open-settings' })
    assert.deepEqual(judgePermission('accessibility', { ...base, main: 'not-determined' }), {
      state: 'not-determined',
      action: 'open-settings'
    })
  })
  it('running from the disk image or translocated: move to Applications first', () => {
    for (const place of ['dmg', 'translocated'] as const) {
      assert.equal(judgePermission('screen', { ...base, place, probe: 'denied' }).action, 'move-to-applications')
      assert.equal(judgePermission('accessibility', { ...base, place, main: 'denied' }).action, 'move-to-applications')
    }
  })
  it('granted under an earlier build, denied now (ad-hoc signature changed, stale TCC row): remove and re-add', () => {
    const v = judgePermission('accessibility', { ...base, main: 'denied', lastGrantedBuild: '0.9.2' })
    assert.deepEqual(v, { state: 'denied', action: 'reset-entry' })
  })
  it('same build lost it (user turned it off): just open settings', () => {
    assert.equal(judgePermission('accessibility', { ...base, main: 'denied', lastGrantedBuild: '0.9.3' }).action, 'open-settings')
  })
  it('MDM profile denies (restricted): say it is managed, do not send the user to a switch they cannot flip', () => {
    assert.deepEqual(judgePermission('screen', { ...base, main: 'restricted', probe: 'denied' }), { state: 'denied', action: 'managed' })
  })
  it('unknown stays unknown (external engine, call threw): no nagging', () => {
    assert.deepEqual(judgePermission('screen', { ...base, main: 'unknown' }), { state: 'unknown', action: 'none' })
  })
  it('a translocated copy that IS granted is still reported granted (it works this run)', () => {
    assert.equal(judgePermission('screen', { ...base, place: 'translocated', probe: 'granted' }).state, 'granted')
  })
})

describe('poll schedule: fast while it matters, nothing otherwise', () => {
  const s = { visible: true, pending: ['screen' as const], sinceOpenMs: 1000, focused: false }
  it('polls fast right after the user opened System Settings', () => {
    assert.equal(nextPollMs(s), POLL_FAST_MS)
    assert.ok(POLL_FAST_MS <= 500)
  })
  it('slows down after the fast window or when no step was clicked', () => {
    assert.equal(nextPollMs({ ...s, sinceOpenMs: FAST_WINDOW_MS + 1 }), POLL_IDLE_MS)
    assert.equal(nextPollMs({ ...s, sinceOpenMs: null }), POLL_IDLE_MS)
  })
  it('stops when the screen is hidden or everything is granted', () => {
    assert.equal(nextPollMs({ ...s, visible: false }), null)
    assert.equal(nextPollMs({ ...s, pending: [] }), null)
  })
  it('re-reads after the accessibility distributed note, including after tccd commits', () => {
    assert.equal(AX_NOTE_RECHECKS_MS[0], 0)
    assert.ok(AX_NOTE_RECHECKS_MS.some((ms) => ms >= 250))
  })
})

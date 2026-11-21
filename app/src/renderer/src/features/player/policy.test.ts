/**
 * The play rules (policy.ts). Offline, no player, no window: `npx tsx --test src/renderer/src/features/player/policy.test.ts`
 */
import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { BOOT_QUIET_MS, decidePlay, DEFER_MS, panelVisible, resumesAfterPass, showsPlayGlyph, startDeferred, stepStartPlays, type PlayCause } from './policy'

const causes: PlayCause[] = ['learner', 'step', 'resume', 'setup', 'engine', 'jump']

describe('panelVisible', () => {
  it('Electron trusts main, not the page (a window created hidden still reports visible)', () => {
    assert.equal(panelVisible({ electron: true, windowShown: false, pageVisible: true }), false)
    assert.equal(panelVisible({ electron: true, windowShown: true, pageVisible: true }), true)
  })
  it('the browser stage follows the page', () => {
    assert.equal(panelVisible({ electron: false, windowShown: false, pageVisible: true }), true)
    assert.equal(panelVisible({ electron: false, windowShown: true, pageVisible: false }), false)
  })
})

describe('decidePlay', () => {
  it('plays for every cause while the panel is on screen', () => {
    for (const cause of causes) assert.equal(decidePlay({ visible: true, cause }), 'play', cause)
  })
  it('never plays unseen: a live step defers, everything else is refused', () => {
    for (const cause of causes) assert.equal(decidePlay({ visible: false, cause }), cause === 'step' ? 'defer' : 'refuse', cause)
  })
  it('a play intent from another window or the engine does not start a hidden player', () => {
    assert.equal(decidePlay({ visible: false, cause: 'jump' }), 'refuse')
    assert.equal(decidePlay({ visible: false, cause: 'engine' }), 'refuse')
  })
  it('the pass resume and the end of setup do not start a hidden player', () => {
    assert.equal(decidePlay({ visible: false, cause: 'resume' }), 'refuse')
    assert.equal(decidePlay({ visible: false, cause: 'setup' }), 'refuse')
  })
})

describe('stepStartPlays', () => {
  const live = { restoring: false, sinceBootMs: BOOT_QUIET_MS + 10_000, setupHold: false }
  it('a live step rolls the video', () => {
    assert.equal(stepStartPlays(live), true)
  })
  it('a replayed step (reconnect) only cues', () => {
    assert.equal(stepStartPlays({ ...live, replay: true }), false)
  })
  it('an engine restore (engine.hello restored) only cues: launching miyagi never continues a lesson out loud', () => {
    assert.equal(stepStartPlays({ ...live, restoring: true }), false)
  })
  it('the engine log a window gets as it loads only cues', () => {
    assert.equal(stepStartPlays({ ...live, sinceBootMs: 50 }), false)
    assert.equal(stepStartPlays({ ...live, sinceBootMs: BOOT_QUIET_MS - 1 }), false)
    assert.equal(stepStartPlays({ ...live, sinceBootMs: BOOT_QUIET_MS }), true)
  })
  it('a waiting setup card holds it', () => {
    assert.equal(stepStartPlays({ ...live, setupHold: true }), false)
  })
})

describe('startDeferred', () => {
  const base = { deferredAt: 1000, now: 1000 + DEFER_MS - 1, sameStep: true, pausedBy: 'hidden' as const }
  it('the window shows right after the step started: play', () => {
    assert.equal(startDeferred(base), true)
  })
  it('too late: the learner starts it', () => {
    assert.equal(startDeferred({ ...base, now: 1000 + DEFER_MS + 1 }), false)
  })
  it('another step by now, or nothing deferred: no', () => {
    assert.equal(startDeferred({ ...base, sameStep: false }), false)
    assert.equal(startDeferred({ ...base, deferredAt: undefined }), false)
  })
  it('something else paused it meanwhile (the learner, the gate, setup): no', () => {
    for (const pausedBy of ['user', 'gate', 'setup', 'engine', 'ended', 'start', undefined] as const) assert.equal(startDeferred({ ...base, pausedBy }), false, String(pausedBy))
  })
})

describe('resumesAfterPass', () => {
  it('resumes after the gate or the engine pause', () => {
    assert.equal(resumesAfterPass({ playing: false, pausedBy: 'gate', setupHold: false }), true)
    assert.equal(resumesAfterPass({ playing: false, pausedBy: 'engine', setupHold: false }), true)
    assert.equal(resumesAfterPass({ playing: false, pausedBy: undefined, setupHold: false }), true)
  })
  it('never resumes what the learner paused, the end, a hidden panel or a replayed step never started', () => {
    for (const pausedBy of ['user', 'ended', 'hidden', 'start'] as const) assert.equal(resumesAfterPass({ playing: false, pausedBy, setupHold: false }), false, pausedBy)
  })
  it('not while a part is building, a setup card waits, or it already plays', () => {
    assert.equal(resumesAfterPass({ playing: false, pausedBy: 'gate', setupHold: false, pending: true }), false)
    assert.equal(resumesAfterPass({ playing: false, pausedBy: 'gate', setupHold: true }), false)
    assert.equal(resumesAfterPass({ playing: true, pausedBy: undefined, setupHold: false }), false)
  })
})

describe('showsPlayGlyph', () => {
  it('the plain play glyph for the learner, a hidden panel and a replayed step; gate states keep their own', () => {
    assert.deepEqual(
      (['user', 'hidden', 'start', 'gate', 'engine', 'setup', 'ended', undefined] as const).map(showsPlayGlyph),
      [true, true, true, false, false, false, false, false]
    )
  })
})

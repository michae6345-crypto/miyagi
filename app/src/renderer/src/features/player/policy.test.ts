/**
 * The play rules (policy.ts). Offline, no player, no window: `npx tsx --test src/renderer/src/features/player/policy.test.ts`
 */
import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import {
  BOOT_QUIET_MS,
  decidePlay,
  DEFER_MS,
  engineIntentPlays,
  GATE_ZONE_S,
  lessonReadyResets,
  panelVisible,
  replayKeepsVideo,
  resumesAfterPass,
  showsPlayGlyph,
  startDeferred,
  stepStartPlays,
  type PlayCause
} from './policy'

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
  it('a card jump (in this window or relayed from another) or an engine intent does not start a hidden player', () => {
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

describe('engineIntentPlays', () => {
  const live = { sinceBootMs: BOOT_QUIET_MS + 10_000, restoring: false }
  it('a live engine video.play or video.seek {play} may play', () => {
    assert.equal(engineIntentPlays(live), true)
  })
  it('the engine log a recovered window gets as it loads keeps its seeks but not their play', () => {
    assert.equal(engineIntentPlays({ ...live, sinceBootMs: 50 }), false)
    assert.equal(engineIntentPlays({ ...live, sinceBootMs: BOOT_QUIET_MS - 1 }), false)
    assert.equal(engineIntentPlays({ ...live, sinceBootMs: BOOT_QUIET_MS }), true)
  })
  it('an engine restore does not play a stale intent', () => {
    assert.equal(engineIntentPlays({ ...live, restoring: true }), false)
  })
})

describe('replay of the same lesson keeps position and playback', () => {
  // Engine reconnect while step 4 plays at 3:20 (its clip 3:00 to 4:00): lesson.ready {replay}, then step.started {replay}.
  const step4 = { start: 180, end: 240 }
  it('lesson.ready {replay} of the lesson already held neither stops nor cues the first clip', () => {
    assert.equal(lessonReadyResets({ replay: true, sameLesson: true }), false)
  })
  it('a new lesson, or a first load of this one, still stops the last video and cues', () => {
    assert.equal(lessonReadyResets({ replay: false, sameLesson: true }), true)
    assert.equal(lessonReadyResets({ replay: undefined, sameLesson: false }), true)
    assert.equal(lessonReadyResets({ replay: true, sameLesson: false }), true)
  })
  it('the step.started {replay} after it leaves step 4 at 3:20 as it is, playing', () => {
    assert.equal(stepStartPlays({ replay: true, restoring: true, sinceBootMs: BOOT_QUIET_MS + 10_000, setupHold: false }), false)
    assert.equal(replayKeepsVideo({ sameVideo: true, t: 200, ...step4 }), true)
    // and the resume after a pass still follows the learner's state (nothing set it to 'start')
    assert.equal(resumesAfterPass({ playing: false, pausedBy: 'gate', setupHold: false }), true)
  })
  it('held at the step end (gate zone) stays too; outside the clip, or another video, it cues', () => {
    assert.equal(replayKeepsVideo({ sameVideo: true, t: step4.end + GATE_ZONE_S - 0.1, ...step4 }), true)
    assert.equal(replayKeepsVideo({ sameVideo: true, t: step4.end + GATE_ZONE_S, ...step4 }), false)
    assert.equal(replayKeepsVideo({ sameVideo: true, t: 30, ...step4 }), false)
    assert.equal(replayKeepsVideo({ sameVideo: false, t: 200, ...step4 }), false)
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

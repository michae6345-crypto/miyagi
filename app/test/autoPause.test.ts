/**
 * Auto-pause (user test Nov 25: "the video keeps playing for no reason" while the learner works in VS Code). Pure rules
 * in features/player/policy.ts: rule 6 (away: lock, sleep, page hidden), rule 7 (the setup gate), and the resume after
 * a passed check never undoing them. The engine half (a check-less step that asks for work waits at its end) is
 * server/orchestrator/tests/test_setup_gate.py.
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { onAway, resumesAfterPass, setupHolds, showsPlayGlyph, stepStartPlays, type PausedBy } from '../src/renderer/src/features/player/policy'

test('away: a playing (or about to play) video pauses on lock, sleep and a hidden page', () => {
  for (const signal of ['lock', 'sleep', 'page-hidden'] as const) {
    assert.equal(onAway({ playing: true, wantPlay: true, signal }), 'pause')
    assert.equal(onAway({ playing: false, wantPlay: true, signal }), 'pause') // a deferred / wanted play is stopped too
    assert.equal(onAway({ playing: false, wantPlay: false, signal }), 'ignore')
  }
})

test('away is only undone by the learner: a passed check does not resume it', () => {
  assert.equal(resumesAfterPass({ playing: false, pausedBy: 'away', setupHold: false }), false)
  assert.equal(showsPlayGlyph('away'), true)
  // the step gate still resumes on a pass (that is the lesson moving on)
  assert.equal(resumesAfterPass({ playing: false, pausedBy: 'gate', setupHold: false }), true)
})

test('setup holds the video for a waiting card or a holding gate', () => {
  assert.equal(setupHolds({ cardWaiting: false, gateHolds: false }), false)
  assert.equal(setupHolds({ cardWaiting: true, gateHolds: false }), true)
  assert.equal(setupHolds({ cardWaiting: false, gateHolds: true }), true)
  // a live step that starts while setup holds waits (it starts when the gate lets go)
  assert.equal(stepStartPlays({ restoring: false, sinceBootMs: 1e6, setupHold: true }), false)
  assert.equal(resumesAfterPass({ playing: false, pausedBy: 'setup' as PausedBy, setupHold: true }), false)
})

test('nothing else resumes over the learner, the end, a hidden panel or a replayed step', () => {
  for (const pausedBy of ['user', 'ended', 'hidden', 'start', 'away'] as const)
    assert.equal(resumesAfterPass({ playing: false, pausedBy, setupHold: false }), false, pausedBy)
})

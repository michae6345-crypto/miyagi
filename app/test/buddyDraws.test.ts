/**
 * Who draws a mark (marks.ts standsDown), and today's pointing: the spotlight's boxes (pointing.ts spotlit).
 * Run: node --import tsx --import ./test/setup.mjs --test test/buddyDraws.test.ts
 */
import assert from 'node:assert/strict'
import { afterEach, beforeEach, describe, mock, test } from 'node:test'
import { dispatch, emitUi } from '../src/renderer/src/core/bus'
import { HOLD, standsDown, type Registered } from '../src/renderer/src/features/buddy/marks'
import { reached, SPOT_HOLD_MS, spotlit, usePointing } from '../src/renderer/src/features/buddy/pointing'

const buddy: Registered = { id: 'buddy', overlayLayers: [{ id: 'buddy-reach' }, { id: 'buddy' }] }
const send = (type: string, payload: unknown = {}): void => dispatch({ type, payload } as never)
const shown = (): { x: number; y: number; w: number; h: number; why: string; label?: string }[] => usePointing.getState().marks.map((m) => ({ ...m.rect, why: m.why, label: m.label }))
const box = { x: 100, y: 500, w: 240, h: 22 }

describe('one stroke per mark: who draws (marks.ts standsDown)', () => {
  test('the character draws when it is the only one in the build', () => {
    assert.equal(standsDown([buddy, { id: 'spotlight', overlayLayers: [{}] }]), false)
    assert.equal(standsDown([]), false)
  })

  test('it stands down for features/annotate as it was: that one still draws, and knows nothing of this one', () => {
    assert.equal(standsDown([{ id: 'annotate', overlayLayers: [{ id: 'annotate' }] }, buddy]), true)
  })

  test('the character draws once features/annotate says it yields', () => {
    assert.equal(standsDown([{ id: 'annotate', overlayLayers: [{ id: 'annotate' }], yieldsToBuddy: true }, buddy]), false)
  })

  test('a features/annotate with no layer draws nothing, so the character draws', () => {
    assert.equal(standsDown([{ id: 'annotate', overlayLayers: [] }, buddy]), false)
    assert.equal(standsDown([{ id: 'annotate' }, buddy]), false)
  })
})

describe('today’s pointing: the spotlight’s boxes (pointing.ts spotlit)', () => {
  beforeEach(() => {
    mock.timers.enable({ apis: ['setTimeout', 'Date'] })
    emitUi('reset')
  })
  afterEach(() => {
    emitUi('reset')
    mock.timers.reset()
  })

  test('a spotlight box gets a mark: a point, with no label (the spotlight says its own words)', () => {
    spotlit(box)
    assert.deepEqual(shown(), [{ ...box, why: 'point', label: undefined }])
    // The spotlight's caption is on the right of its box: the buddy reads this to sit on the left.
    assert.equal(usePointing.getState().bridged, true)
  })

  test('the engine re-reading the same box, a few px off, does not mark it again', () => {
    spotlit(box)
    const born = usePointing.getState().marks[0].born
    mock.timers.tick(1000)
    spotlit({ ...box, x: box.x + 5, w: box.w - 4 })
    assert.equal(usePointing.getState().marks.length, 1)
    assert.equal(usePointing.getState().marks[0].born, born)
  })

  test('the spotlight hides: the mark goes with it, and may come back', () => {
    spotlit(box)
    spotlit(undefined)
    assert.equal(shown().length, 0)
    spotlit(box)
    assert.equal(shown().length, 1)
  })

  test('the spotlight fading on its own (calm) leaves bon pointing until its hold is up', () => {
    spotlit(box)
    mock.timers.tick(4000)
    spotlit(undefined, false, true)
    assert.equal(shown().length, 1)
    spotlit(box) // the engine re-sends the same box: still one mark, same deadline
    assert.equal(usePointing.getState().marks.length, 1)
    mock.timers.tick(SPOT_HOLD_MS - 4000 + 10)
    assert.equal(shown().length, 0)
  })

  test('a box the learner reached stays gone when the spotlight shows it again, until Show me asks for it', () => {
    spotlit(box)
    reached(usePointing.getState().marks.map((m) => m.key))
    assert.equal(shown().length, 0)
    spotlit(undefined)
    spotlit(box)
    assert.equal(shown().length, 0)
    spotlit(box, true)
    assert.equal(shown().length, 1)
  })

  test('the mark holds long enough to be seen (longer than the 6 s default), then goes', () => {
    assert.ok(SPOT_HOLD_MS > HOLD.base)
    spotlit(box)
    mock.timers.tick(SPOT_HOLD_MS - 10)
    assert.equal(shown().length, 1)
    mock.timers.tick(20)
    assert.equal(shown().length, 0)
  })

  test('the engine’s own marks win while they are up: spotlight boxes wait', () => {
    send('annotate', { marks: [{ id: 'a', x: 600, y: 200, w: 80, h: 20, why: 'answer', label: 'Here' }] })
    spotlit(box)
    assert.deepEqual(
      shown().map((m) => m.label),
      ['Here']
    )
    assert.equal(usePointing.getState().bridged, false)
    // And a spotlight that hides does not take the engine's marks away.
    spotlit(undefined)
    assert.equal(shown().length, 1)
  })

  test('once the engine’s marks are gone, spotlight boxes are marked again (a circle-to-ask does not end the pointing)', () => {
    send('annotate', { marks: [{ id: 'a', x: 600, y: 200, w: 80, h: 20, why: 'answer', label: 'Here' }], holdMs: 2000 })
    spotlit(box)
    assert.deepEqual(
      shown().map((m) => m.label),
      ['Here']
    )
    mock.timers.tick(2100)
    assert.equal(shown().length, 0)
    spotlit(box)
    assert.equal(shown().length, 1)
    assert.equal(usePointing.getState().bridged, true)
    send('annotate', { clear: true })
    spotlit({ ...box, x: box.x + 200 })
    assert.equal(shown().length, 1)
  })

  test('a new step lets the same box be marked afresh', () => {
    spotlit(box)
    send('step.started', { stepId: 's2' })
    assert.equal(shown().length, 0)
    spotlit(box)
    assert.equal(shown().length, 1)
  })

  test('a box that is not a box is ignored', () => {
    spotlit({ x: 10, y: 10, w: 0, h: 20 })
    spotlit({ x: Number.NaN, y: 10, w: 30, h: 20 })
    assert.equal(shown().length, 0)
  })
})

describe('the on-screen coach’s text mark (an app lesson): bon circles it for the whole step', () => {
  const coach = { id: 'os-s1-1', why: 'point', stepId: 's1', label: 'Move it', text: 'Press  G to move   the cube', keys: ['G'], x: 700, y: 400, w: 120, h: 90 }
  const texts = (): (string | undefined)[] => usePointing.getState().marks.map((m) => m.text)
  beforeEach(() => {
    mock.timers.enable({ apis: ['setTimeout', 'Date'] })
    emitUi('reset')
    send('step.started', { stepId: 's1' })
  })
  afterEach(() => {
    emitUi('reset')
    mock.timers.reset()
  })

  test('kept with its text (cleaned), and not timed: no 6 s fade, no holdMs fade', () => {
    send('annotate', { marks: [coach], holdMs: 2000 })
    assert.deepEqual(texts(), ['Press G to move the cube'])
    mock.timers.tick(HOLD.max + 1000)
    assert.equal(shown().length, 1)
  })

  test('a text mark beside a plain one: only the plain one fades at the hold', () => {
    send('annotate', { marks: [coach, { id: 'p2', why: 'point', x: 100, y: 100, w: 50, h: 20 }] })
    mock.timers.tick(HOLD.base + 10)
    assert.deepEqual(texts(), ['Press G to move the cube'])
  })

  test('it goes on step.passed, on another step, on Esc, on annotate {clear}, and when the learner gets there', () => {
    send('annotate', { marks: [coach] })
    send('step.passed', { stepId: 's1' })
    assert.equal(shown().length, 0)
    send('step.started', { stepId: 's1' })
    send('annotate', { marks: [coach] })
    send('step.started', { stepId: 's2' })
    assert.equal(shown().length, 0)
    send('step.started', { stepId: 's1' })
    send('annotate', { marks: [coach] })
    emitUi('dismiss')
    assert.equal(shown().length, 0)
    send('step.started', { stepId: 's1' })
    send('annotate', { marks: [coach] })
    send('annotate', { clear: true })
    assert.equal(shown().length, 0)
    send('step.started', { stepId: 's1' })
    send('annotate', { marks: [coach] })
    reached([usePointing.getState().marks[0].key])
    assert.equal(shown().length, 0)
  })

  test('a late text mark for a step that is not running draws nothing and leaves what is drawn', () => {
    send('annotate', { marks: [{ id: 'a', why: 'answer', x: 10, y: 10, w: 80, h: 30 }] })
    send('annotate', { marks: [{ ...coach, stepId: 's0' }] })
    assert.deepEqual(
      shown().map((m) => m.why),
      ['answer']
    )
  })

  test('quiet (a blocker, idle) hides it and live again brings it back with no re-send', () => {
    send('annotate', { marks: [coach] })
    send('blocker', { kind: 'save' })
    assert.equal(shown().length, 0)
    send('blocker', { kind: 'save', clear: true })
    assert.equal(shown().length, 1)
    send('status', { state: 'idle' })
    assert.equal(shown().length, 0)
    send('status', { state: 'watching' })
    assert.equal(shown().length, 1)
    // A text mark that came while quiet waits, and shows once live.
    send('annotate', { clear: true })
    send('lesson.paused', { reason: 'user' })
    send('annotate', { marks: [{ ...coach, id: 'os-s1-2', text: 'Now press Tab' }] })
    assert.equal(shown().length, 0)
    send('lesson.resumed', {})
    assert.deepEqual(texts(), ['Now press Tab'])
  })

  test('“Not yet” for this step: the engine’s re-send is circled again, though the learner got there', () => {
    send('annotate', { marks: [coach] })
    reached([usePointing.getState().marks[0].key])
    send('annotate', { marks: [coach] })
    assert.equal(shown().length, 0, 'a re-send with no ask stays gone')
    send('card', { verdict: 'not_done', stepId: 's1', kind: 'step' })
    send('annotate', { marks: [coach] })
    assert.equal(shown().length, 1)
  })
})

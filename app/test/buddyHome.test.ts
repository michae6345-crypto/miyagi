/**
 * bon's home in the corner, offline: features/buddy/home.ts (where it sits) and the click on it in talk.ts (wake, the
 * Ask in its bubble, and going back to rest). Through the real bus.
 */
import assert from 'node:assert/strict'
import { afterEach, beforeEach, describe, mock, test } from 'node:test'
import { dispatch, emitUi } from '../src/renderer/src/core/bus'
import { cornerPoint, DEFAULT_HOME, HOME, placeFrom } from '../src/renderer/src/features/buddy/home'
import { forget } from '../src/renderer/src/features/buddy/pointing'
import { ask, ASK_WAIT_MS, engineThinking, LINGER_MS, sendHome, setActivity, setAsker, summon, useTalk, wake } from '../src/renderer/src/features/buddy/talk'

const talk = useTalk.getState
const send = (type: string, payload: unknown = {}): void => dispatch({ type, payload } as never)

describe('where bon lives (home.ts)', () => {
  test('the corner is the bottom right of the work area, inset the same both ways', () => {
    // A 1512 x 982 display with a 38 px menu bar and a 70 px Dock at the bottom.
    const p = cornerPoint({ x: 0, y: 38, w: 1512, h: 874 })
    assert.deepEqual(p, { x: 1512 - HOME.inset, y: 38 + 874 - HOME.inset })
  })

  test('a Dock on the right moves it with the work area', () => {
    assert.equal(cornerPoint({ x: 0, y: 38, w: 1442, h: 944 }).x, 1442 - HOME.inset)
  })

  test('the click target covers its body and stays on the screen', () => {
    assert.ok(HOME.hit >= 54, 'at least the body')
    assert.ok(HOME.inset >= HOME.hit / 2, 'the whole target is inside the work area')
  })

  test('the corner is the default, and anything unknown falls back to it', () => {
    assert.equal(DEFAULT_HOME, 'corner')
    assert.equal(placeFrom('notch'), 'notch')
    assert.equal(placeFrom('corner'), 'corner')
    assert.equal(placeFrom(null), 'corner')
    assert.equal(placeFrom('desk'), 'corner')
  })
})

describe('a click on bon in its corner (talk.ts)', () => {
  let opened = 0
  beforeEach(() => {
    mock.timers.enable({ apis: ['setTimeout', 'Date'] })
    opened = 0
    setAsker(() => {
      opened++
    })
    forget()
    sendHome()
  })
  afterEach(() => {
    setAsker(undefined)
    forget()
    sendHome()
    mock.timers.reset()
  })

  test('it wakes where it is and offers Ask and talking', () => {
    wake()
    assert.deepEqual([talk().summoned, talk().woken, talk().menu], [true, true, true])
  })

  test('a second click while it is offering puts it back to rest', () => {
    wake()
    wake()
    assert.deepEqual([talk().summoned, talk().woken, talk().menu], [false, false, false])
  })

  test('left alone, the offer closes by itself', () => {
    wake()
    mock.timers.tick(LINGER_MS)
    assert.deepEqual([talk().summoned, talk().woken, talk().menu], [false, false, false])
  })

  test('Ask opens the ask field once, closes the offer, and it waits for the question', () => {
    wake()
    ask()
    assert.equal(opened, 1)
    assert.deepEqual([talk().woken, talk().menu], [true, false])
    mock.timers.tick(LINGER_MS * 3)
    assert.equal(talk().woken, true, 'still waiting while the learner types')
    mock.timers.tick(ASK_WAIT_MS)
    assert.equal(talk().woken, false, 'but not for ever')
  })

  test('Ask does nothing when it was not woken', () => {
    ask()
    assert.equal(opened, 0)
  })

  test('after Ask the engine thinking is its thinking, and the answer is said where it is', () => {
    wake()
    ask()
    engineThinking(true)
    assert.equal(talk().activity, 'thinking')
    send('card', { kind: 'answer', title: 'Answer', body: 'Each pixel is one input. There are 784 of them.' })
    engineThinking(false)
    assert.deepEqual([talk().activity, talk().say, talk().woken], ['idle', 'Each pixel is one input.', true])
    mock.timers.tick(LINGER_MS)
    assert.deepEqual([talk().say, talk().woken], [undefined, false])
  })

  test('talking to it closes the offer and it listens where it is', () => {
    wake()
    setActivity('listening', 'why 784')
    assert.deepEqual([talk().woken, talk().menu, talk().activity, talk().heard], [true, false, 'listening', 'why 784'])
  })

  test('Esc puts it back to rest', () => {
    wake()
    emitUi('dismiss')
    assert.deepEqual([talk().summoned, talk().woken, talk().menu], [false, false, false])
  })

  test('called by talking alone (no click) it is not woken: it goes to the pointer as before', () => {
    summon()
    assert.deepEqual([talk().summoned, talk().woken], [true, false])
  })
})

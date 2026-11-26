/**
 * The buddy's back and forth, offline: features/buddy/talk.ts. When it is out on the screen and when it goes home,
 * what it is doing (listening, thinking), what it says, and what the chips in its bubble do. Through the real bus.
 */
import assert from 'node:assert/strict'
import { afterEach, beforeEach, describe, mock, test } from 'node:test'
import { dispatch, emitUi } from '../src/renderer/src/core/bus'
import type { Mark } from '../src/renderer/src/features/buddy/marks'
import { annotate, fade, forget, usePointing } from '../src/renderer/src/features/buddy/pointing'
import { canExplain, engineThinking, LINGER_MS, reply, say, sendHome, setActivity, setEngine, setResponder, summon, useTalk, type ReplyKind } from '../src/renderer/src/features/buddy/talk'

const mark = (over: Partial<Mark> = {}): Mark => ({ x: 100, y: 500, w: 200, h: 20, why: 'point', ...over })
const shown = (): string[] => usePointing.getState().marks.map((m) => m.key)
const talk = useTalk.getState
const send = (type: string, payload: unknown = {}): void => dispatch({ type, payload } as never)

describe('the back and forth (talk.ts)', () => {
  beforeEach(() => {
    mock.timers.enable({ apis: ['setTimeout', 'Date'] })
    forget()
    sendHome()
  })
  afterEach(() => {
    setResponder(undefined)
    forget()
    sendHome()
    mock.timers.reset()
  })

  test('called, it stays by the pointer a while, then goes home on its own', () => {
    assert.equal(talk().summoned, false)
    summon()
    assert.equal(talk().summoned, true)
    mock.timers.tick(LINGER_MS - 1)
    assert.equal(talk().summoned, true)
    mock.timers.tick(1)
    assert.equal(talk().summoned, false)
  })

  test('it does not leave in the middle of something: listening, thinking, or a mark still up', () => {
    setActivity('listening', 'where do I')
    assert.deepEqual([talk().summoned, talk().activity, talk().heard], [true, 'listening', 'where do I'])
    mock.timers.tick(LINGER_MS * 2)
    assert.equal(talk().summoned, true, 'still listening')

    setActivity('thinking')
    mock.timers.tick(LINGER_MS * 2)
    assert.equal(talk().summoned, true, 'still thinking')

    annotate({ marks: [mark({ id: 'a', why: 'answer' })], holdMs: 30_000 })
    setActivity('idle')
    mock.timers.tick(LINGER_MS * 2)
    assert.equal(talk().summoned, true, 'an answer is still circled')

    fade(['id:a'])
    mock.timers.tick(LINGER_MS - 1)
    assert.equal(talk().summoned, true, 'the clock starts when the mark goes')
    mock.timers.tick(1)
    assert.equal(talk().summoned, false)
  })

  test('what it hears replaces what it was saying', () => {
    say('The learning rate is set right here.')
    assert.equal(talk().say, 'The learning rate is set right here.')
    setActivity('listening', 'and')
    assert.equal(talk().say, undefined)
  })

  test('it says one sentence, and that calls it out', () => {
    say('Smaller is steadier. It is also slower, so start at 1e-3 and go down.')
    assert.equal(talk().say, 'Smaller is steadier.')
    assert.equal(talk().summoned, true)
    say()
    assert.equal(talk().say, undefined)
  })

  test('what it said about a mark goes when the mark goes', () => {
    annotate({ marks: [mark({ id: 'a', why: 'answer' })], holdMs: 30_000 })
    say('It is set right here.', 'id:a')
    assert.deepEqual([talk().say, talk().sayFor], ['It is set right here.', 'id:a'])
    fade(['id:a'])
    assert.deepEqual([talk().say, talk().sayFor], [undefined, undefined])
  })

  test('an answer card while it is out: it says the first sentence, beside the mark the answer points at', () => {
    send('card', { kind: 'answer', body: 'Not while it is home.' })
    assert.equal(talk().say, undefined, 'home: the card is the cards feature’s alone')

    summon()
    annotate({ marks: [mark({ id: 'p' }), mark({ id: 'q', x: 700, why: 'answer' })], holdMs: 30_000 })
    send('card', { kind: 'answer', body: 'The optimizer takes it. You can also pass a schedule.' })
    assert.deepEqual([talk().say, talk().sayFor], ['The optimizer takes it.', 'id:q'])

    send('card', { kind: 'hint', body: 'A hint is not an answer.' })
    assert.equal(talk().say, 'The optimizer takes it.')
  })

  test('Got it: the mark goes with a cheer. Next: it goes without one', () => {
    annotate({ marks: [mark({ id: 'a' }), mark({ id: 'b', x: 700 })], holdMs: 30_000 })
    const cheers = usePointing.getState().cheer
    reply('next', 'id:a')
    assert.deepEqual(shown(), ['id:b'])
    assert.equal(usePointing.getState().cheer, cheers)
    reply('got', 'id:b')
    assert.deepEqual(shown(), [])
    assert.equal(usePointing.getState().cheer, cheers + 1)
  })

  test('a stand-in for the engine gets the reply first, and can leave it to the buddy', () => {
    const got: Array<[ReplyKind, string]> = []
    setResponder((kind, key) => {
      got.push([kind, key])
      return kind === 'explain'
    })
    annotate({ marks: [mark({ id: 'a' })], holdMs: 30_000 })
    reply('explain', 'id:a')
    assert.deepEqual(shown(), ['id:a'], 'taken by the stand-in: nothing else happens')
    reply('got', 'id:a')
    assert.deepEqual(got, [
      ['explain', 'id:a'],
      ['got', 'id:a']
    ])
    assert.deepEqual(shown(), [], 'not taken: the buddy does it')
  })

  test('Explain with the engine there: the engine is asked, with the mark’s label, and the buddy thinks', () => {
    annotate({ marks: [mark({ id: 'a', label: 'The optimizer' })], holdMs: 30_000 })
    assert.equal(canExplain(), false, 'no engine, no stand-in: no Explain chip')
    reply('explain', 'id:a')
    assert.equal(talk().activity, 'idle', 'and the reply does nothing')

    const asked: Array<string | undefined> = []
    setEngine({ canExplain: () => true, explain: (label) => asked.push(label) })
    assert.equal(canExplain(), true)
    reply('explain', 'id:a')
    assert.deepEqual(asked, ['The optimizer'])
    assert.deepEqual([talk().summoned, talk().activity], [true, 'thinking'])
    engineThinking(true)
    assert.equal(talk().activity, 'thinking')
    engineThinking(false)
    assert.equal(talk().activity, 'idle', 'the engine stopped: so does the buddy')
    setEngine(undefined)
  })

  test('the engine thinking about something else is not the buddy’s thinking', () => {
    summon()
    engineThinking(true) // a check running, a build: nobody asked the buddy
    assert.equal(talk().activity, 'idle')
    setActivity('listening', 'why')
    setActivity('thinking') // the learner let go of the keys
    engineThinking(true)
    assert.equal(talk().activity, 'thinking')
    engineThinking(false)
    assert.equal(talk().activity, 'idle')
    engineThinking(true) // the next thing the engine does on its own
    assert.equal(talk().activity, 'idle')
  })

  test('Esc, a reset and the end of the lesson send it home at once', () => {
    for (const go of [() => void emitUi('dismiss'), () => void emitUi('reset'), () => send('lesson.ended')]) {
      setActivity('listening', 'where')
      say('Here.')
      go()
      assert.deepEqual([talk().summoned, talk().activity, talk().heard, talk().say], [false, 'idle', '', undefined])
    }
  })
})

/** main/pttProtocol.ts, offline: the capture answer parser, the request check, the commands and the admission rule. */
import assert from 'node:assert/strict'
import { describe, test } from 'node:test'
import {
  CAPTURE_MARGIN,
  captureAdmit,
  captureCommand,
  captureLogLine,
  captureReleaseCommand,
  captureRequest,
  isCaptureId,
  MAX_PENDING_CAPTURES,
  MAX_CAPTURE_EDGE,
  parseCaptureLine,
  parseCaptureWarmLine,
  parseLine
} from '../src/main/pttProtocol'

const j = (o: object): string => JSON.stringify(o)
const PATH = '/var/folders/xy/T/miyagi-capture/cap-1b4e28ba-2fa1-11d2-883f-0016d3cca427.jpg'
const ok = { type: 'capture', id: 'cap-1', path: PATH, w: 1092, h: 546, pxPerPoint: 0.91, rect: { x: 0, y: 0, w: 1200, h: 600 }, displayId: 1, ms: 142 }

describe('parseCaptureLine', () => {
  test('a good answer parses', () => {
    assert.deepEqual(parseCaptureLine(j(ok)), { ok: true, id: 'cap-1', path: PATH, w: 1092, h: 546, pxPerPoint: 0.91, rect: { x: 0, y: 0, w: 1200, h: 600 }, displayId: 1, ms: 142 })
  })

  test('the sim flag and unknown fields are ignored', () => {
    assert.equal(parseCaptureLine(j({ ...ok, sim: true, extra: 1 }))?.ok, true)
  })

  test('every helper error code parses; message is cleaned and capped', () => {
    for (const error of ['screen_denied', 'no_display', 'bad_rect', 'unsupported', 'failed']) {
      assert.deepEqual(parseCaptureLine(j({ type: 'capture', id: 'c', error, message: 'no\nway', ms: 3 })), { ok: false, id: 'c', error, message: 'no way', ms: 3 })
    }
    assert.deepEqual(parseCaptureLine(j({ type: 'capture', id: 'c', error: 'failed', message: 'x'.repeat(301) })), { ok: false, id: 'c', error: 'failed', message: '' })
  })

  test("main's own codes and unknown codes from the helper are dropped", () => {
    for (const error of ['timeout', 'unavailable', 'bad_request', 'oops', 7]) assert.equal(parseCaptureLine(j({ type: 'capture', id: 'c', error })), undefined)
  })

  test('malformed answers are dropped', () => {
    const bad: object[] = [
      { ...ok, id: '' },
      { ...ok, id: 'a b' },
      { ...ok, path: 'relative/cap-1b4e28ba.jpg' },
      { ...ok, path: '/tmp/../etc/cap-1b4e28ba.jpg' },
      { ...ok, path: '/tmp/photo.jpg' },
      { ...ok, path: '/tmp/cap-1b4e28ba.png' },
      { ...ok, path: '/tmp/x\u0000/cap-1b4e28ba.jpg' },
      { ...ok, w: 0 },
      { ...ok, w: MAX_CAPTURE_EDGE + 1 },
      { ...ok, h: 10.5 },
      { ...ok, pxPerPoint: 0 },
      { ...ok, pxPerPoint: Number.POSITIVE_INFINITY },
      { ...ok, pxPerPoint: 40 },
      { ...ok, rect: { x: 0, y: 0, w: 0, h: 5 } },
      { ...ok, rect: { x: 0, y: 0, w: 5 } },
      { ...ok, rect: null },
      { ...ok, displayId: -1 },
      { ...ok, displayId: 1.5 },
      { ...ok, type: 'final' }
    ]
    for (const b of bad) assert.equal(parseCaptureLine(j(b)), undefined, JSON.stringify(b))
    for (const s of ['', 'not json', '[1]', 'null', '{"type":"capture"}', 'x'.repeat(20_000)]) assert.equal(parseCaptureLine(s), undefined, s.slice(0, 20))
  })

  test('a missing ms reads as 0 on success', () => {
    const { ms: _ms, ...rest } = ok
    assert.equal((parseCaptureLine(j(rest)) as { ms: number }).ms, 0)
  })

  test('parseLine never turns a capture answer into a push-to-talk event', () => {
    assert.equal(parseLine(j(ok)), undefined)
    assert.equal(parseLine(j({ type: 'capture', id: 'c', error: 'failed' })), undefined)
  })
})

describe('captureRequest', () => {
  test('a ScreenRegion passes; scale is dropped; margin defaults to 15%', () => {
    assert.deepEqual(captureRequest({ x: 10, y: -20.5, w: 300, h: 200, displayId: 69733378, scale: 2 }), { x: 10, y: -20.5, w: 300, h: 200, displayId: 69733378, margin: CAPTURE_MARGIN })
  })

  test('margin is capped at 0..0.5', () => {
    assert.equal(captureRequest({ x: 0, y: 0, w: 10, h: 10, displayId: 1, margin: 3 })?.margin, 0.5)
    assert.equal(captureRequest({ x: 0, y: 0, w: 10, h: 10, displayId: 1, margin: -1 })?.margin, 0)
    assert.equal(captureRequest({ x: 0, y: 0, w: 10, h: 10, displayId: 1, margin: 0 })?.margin, 0)
  })

  test('junk is not a request', () => {
    const bad: unknown[] = [
      undefined,
      null,
      'x',
      [1, 2],
      { x: 0, y: 0, w: 10, h: 10 },
      { x: 0, y: 0, w: 10, h: 10, displayId: -1 },
      { x: 0, y: 0, w: 10, h: 10, displayId: '1' },
      { x: 0, y: 0, w: 10, h: 10, displayId: 2 ** 33 },
      { x: 0, y: 0, w: 0, h: 10, displayId: 1 },
      { x: Number.NaN, y: 0, w: 10, h: 10, displayId: 1 },
      { x: 0, y: 0, w: 1e9, h: 10, displayId: 1 },
      { x: 0, y: 0, w: 10, h: 10, displayId: 1, margin: 'big' },
      { x: 0, y: 0, w: 10, h: 10, displayId: 1, margin: Number.NaN }
    ]
    for (const b of bad) assert.equal(captureRequest(b), undefined, JSON.stringify(b))
  })
})

describe('captureCommand', () => {
  test('one JSON line the helper reads', () => {
    const lineOut = captureCommand('cap-3', { x: 1, y: 2, w: 3, h: 4, displayId: 5, margin: 0.1 })
    assert.ok(lineOut.endsWith('\n') && !lineOut.slice(0, -1).includes('\n'))
    assert.deepEqual(JSON.parse(lineOut), { cmd: 'capture', id: 'cap-3', rect: { x: 1, y: 2, w: 3, h: 4 }, displayId: 5, margin: 0.1 })
  })

  test('margin falls back to the default', () => {
    assert.equal(JSON.parse(captureCommand('c', { x: 1, y: 2, w: 3, h: 4, displayId: 5 })).margin, CAPTURE_MARGIN)
  })
})

describe('captureReleaseCommand', () => {
  test('one JSON line with the id', () => {
    const out = captureReleaseCommand('cap-7')
    assert.ok(out.endsWith('\n') && !out.slice(0, -1).includes('\n'))
    assert.deepEqual(JSON.parse(out), { cmd: 'capture-release', id: 'cap-7' })
  })
})

describe('captureAdmit', () => {
  test('the helper down: unavailable', () => {
    assert.equal(captureAdmit(0, false), 'unavailable')
  })
  test(`at most ${MAX_PENDING_CAPTURES} waiting, then busy`, () => {
    for (let n = 0; n < MAX_PENDING_CAPTURES; n++) assert.equal(captureAdmit(n, true), undefined)
    assert.equal(captureAdmit(MAX_PENDING_CAPTURES, true), 'busy')
    assert.equal(captureAdmit(MAX_PENDING_CAPTURES + 5, true), 'busy')
  })
})

describe('isCaptureId', () => {
  test("main's own ids only", () => {
    assert.ok(isCaptureId('cap-1'))
    assert.ok(isCaptureId('cap-123456'))
    for (const bad of ['', 'cap-', 'cap-x', 'circle-1', '../cap-1', 'cap-1/..', 7, null, 'cap-1234567890123']) assert.equal(isCaptureId(bad), false, String(bad))
  })
})

describe('capture timing logs', () => {
  test('the warm-up line is read, anything else is not', () => {
    assert.deepEqual(parseCaptureWarmLine(j({ type: 'capture-warm', ok: true, ms: 181.6 })), { ok: true, ms: 182 })
    assert.deepEqual(parseCaptureWarmLine(j({ type: 'capture-warm', ok: false, ms: 0 })), { ok: false, ms: 0 })
    for (const bad of [j({ type: 'capture-warm', ok: 'yes', ms: 3 }), j({ type: 'capture-warm', ok: true, ms: -1 }), j({ type: 'capture-warm', ok: true }), j(ok), 'nope', ''])
      assert.equal(parseCaptureWarmLine(bad), undefined, bad)
    assert.equal(parseLine(j({ type: 'capture-warm', ok: true, ms: 3 })), undefined) // never a push-to-talk event
    assert.equal(parseCaptureLine(j({ type: 'capture-warm', ok: true, ms: 3 })), undefined)
  })
  test('one line per capture: the helper ms and the round trip, never a path', () => {
    const r = parseCaptureLine(j(ok))
    assert.ok(r)
    const line = captureLogLine(r, 171.4)
    assert.equal(line, 'capture 1092x546 helper 142 ms, round trip 171 ms')
    assert.ok(!line.includes('/'))
    assert.equal(captureLogLine({ ok: false, id: 'cap-2', error: 'timeout', message: 'x' }, 2001), 'capture failed: timeout helper - ms, round trip 2001 ms')
    assert.equal(captureLogLine({ ok: false, id: 'cap-3', error: 'screen_denied', message: 'x', ms: 3 }, -4), 'capture failed: screen_denied helper 3 ms, round trip 0 ms')
  })
})

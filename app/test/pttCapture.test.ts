/** main/pttProtocol.ts, offline: the capture answer parser, the request check, the command and the crop mapping. */
import assert from 'node:assert/strict'
import { describe, test } from 'node:test'
import {
  CAPTURE_MARGIN,
  captureCommand,
  captureRequest,
  cropToScreen,
  MAX_CAPTURE_EDGE,
  parseCaptureLine,
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

describe('cropToScreen', () => {
  const cap = { rect: { x: 70, y: 85, w: 260, h: 130 }, w: 520, h: 260 }
  test('screen point = rect origin + px * (rect.w / w)', () => {
    assert.deepEqual(cropToScreen(cap, 0, 0), { x: 70, y: 85 })
    assert.deepEqual(cropToScreen(cap, 260, 130), { x: 200, y: 150 })
    assert.deepEqual(cropToScreen(cap, 520, 260), { x: 330, y: 215 })
  })
  test('clamped to the crop; junk reads as 0', () => {
    assert.deepEqual(cropToScreen(cap, -50, 9999), { x: 70, y: 215 })
    assert.deepEqual(cropToScreen(cap, Number.NaN, Number.POSITIVE_INFINITY), { x: 70, y: 85 })
  })
  test('a second display to the left (negative origin)', () => {
    assert.deepEqual(cropToScreen({ rect: { x: -1000, y: 0, w: 400, h: 300 }, w: 400, h: 300 }, 100, 50), { x: -900, y: 50 })
  })
})

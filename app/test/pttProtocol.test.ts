/** main/pttProtocol.ts, offline: the parser, command builders, terms and backoff. */
import assert from 'node:assert/strict'
import { describe, test } from 'node:test'
import {
  backoffMs,
  BACKOFF_MS,
  cleanTerms,
  configCommand,
  contextCommand,
  contextTerms,
  libraryNames,
  lineBuffer,
  MAX_TEXT,
  parseLine,
  permissionsCommand,
  tccResetArgs
} from '../src/main/pttProtocol'

const j = (o: object): string => JSON.stringify(o)

describe('parseLine', () => {
  test('every helper event type parses', () => {
    assert.deepEqual(parseLine(j({ type: 'ready', stt: 'speechanalyzer', locale: 'en-US', chord: 'fn+control' })), { type: 'ready', stt: 'speechanalyzer', locale: 'en-US', chord: 'fn+control' })
    assert.deepEqual(parseLine(j({ type: 'perm', mic: 'undetermined', input: 'granted', assets: 'missing' })), { type: 'perm', mic: 'undetermined', input: 'granted', assets: 'missing' })
    assert.deepEqual(parseLine(j({ type: 'ptt', state: 'down', id: 'a1' })), { type: 'ptt', state: 'down', id: 'a1' })
    assert.deepEqual(parseLine(j({ type: 'listening', id: 'a1' })), { type: 'listening', id: 'a1' })
    assert.deepEqual(parseLine(j({ type: 'partial', id: 'a1', text: 'why does' })), { type: 'partial', id: 'a1', text: 'why does' })
    assert.deepEqual(parseLine(j({ type: 'final', id: 'a1', text: 'why does it' })), { type: 'final', id: 'a1', text: 'why does it' })
    assert.deepEqual(parseLine(j({ type: 'cancelled', id: 'a1', reason: 'short' })), { type: 'cancelled', id: 'a1', reason: 'short' })
    assert.deepEqual(parseLine(j({ type: 'error', code: 'mic_denied', message: 'no' })), { type: 'error', code: 'mic_denied', message: 'no' })
  })

  test('perm without assets is fine; a bad assets value is dropped, not fatal', () => {
    assert.deepEqual(parseLine(j({ type: 'perm', mic: 'granted', input: 'denied' })), { type: 'perm', mic: 'granted', input: 'denied' })
    assert.deepEqual(parseLine(j({ type: 'perm', mic: 'granted', input: 'denied', assets: 'weird' })), { type: 'perm', mic: 'granted', input: 'denied' })
  })

  test('every cancel reason is accepted, an unknown one is not', () => {
    for (const reason of ['esc', 'keypress', 'short', 'empty', 'timeout', 'disabled']) assert.equal(parseLine(j({ type: 'cancelled', id: 'x', reason }))?.type, 'cancelled')
    assert.equal(parseLine(j({ type: 'cancelled', id: 'x', reason: 'because' })), undefined)
    assert.equal(parseLine(j({ type: 'cancelled', id: 'x' })), undefined)
  })

  test('every error code is accepted, an unknown one is not', () => {
    for (const code of ['input_denied', 'mic_denied', 'mic_undetermined', 'assets_missing', 'no_stt', 'tap_failed']) assert.equal(parseLine(j({ type: 'error', code, message: '' }))?.type, 'error')
    assert.equal(parseLine(j({ type: 'error', code: 'boom', message: '' })), undefined)
  })

  test('garbage, wrong shapes and unknown types are dropped', () => {
    for (const bad of ['', 'not json', '[]', 'null', '42', j({ type: 'nope' }), j({ nottype: 1 }), j({ type: 'ptt', state: 'sideways', id: 'a' }), j({ type: 'ptt', state: 'up' }), j({ type: 'partial', id: 'a', text: 5 }), j({ type: 'ready', stt: 'cloud', locale: 'x', chord: 'y' })]) {
      assert.equal(parseLine(bad), undefined, bad)
    }
  })

  test('an id must be a short token', () => {
    assert.equal(parseLine(j({ type: 'listening', id: '' })), undefined)
    assert.equal(parseLine(j({ type: 'listening', id: 'a b' })), undefined)
    assert.equal(parseLine(j({ type: 'listening', id: 'x'.repeat(65) })), undefined)
    assert.equal(parseLine(j({ type: 'listening', id: '3f2c-9a.1:7' }))?.type, 'listening')
  })

  test('text is cleaned (controls, runs of spaces) and a runaway text is refused', () => {
    assert.deepEqual(parseLine(j({ type: 'final', id: 'a', text: '  why\tdoes \n it  work ' })), { type: 'final', id: 'a', text: 'why does it work' })
    assert.equal(parseLine(j({ type: 'final', id: 'a', text: 'x'.repeat(MAX_TEXT + 1) })), undefined)
    assert.equal(parseLine('x'.repeat(20_000)), undefined)
  })

  test('an empty final still parses (the reducer decides it is nothing)', () => {
    assert.deepEqual(parseLine(j({ type: 'final', id: 'a', text: '' })), { type: 'final', id: 'a', text: '' })
  })
})

describe('lineBuffer', () => {
  test('joins chunks and yields whole lines', () => {
    const b = lineBuffer()
    assert.deepEqual(b.push('{"a":1}\n{"b"'), ['{"a":1}'])
    assert.deepEqual(b.push(':2}\r\n\n{"c":3}\n'), ['{"b":2}', '{"c":3}'])
    assert.deepEqual(b.push('half'), [])
    b.reset()
    assert.deepEqual(b.push('x\n'), ['x'])
  })
  test('a runaway line without a newline is dropped, not buffered forever', () => {
    const b = lineBuffer()
    assert.deepEqual(b.push('x'.repeat(40_000)), [])
    assert.deepEqual(b.push('{"ok":1}\n'), ['{"ok":1}'])
  })
})

describe('commands', () => {
  test('config carries the design defaults', () => {
    assert.deepEqual(JSON.parse(configCommand({ enabled: true, chord: 'fn+control' })), { cmd: 'config', enabled: true, chord: 'fn+control', minHoldMs: 250, maxHoldMs: 60000, locale: 'en-US' })
    assert.equal(JSON.parse(configCommand({ enabled: false, chord: 'control+option' })).chord, 'control+option')
    assert.ok(configCommand({ enabled: true, chord: 'fn+control' }).endsWith('\n'))
  })
  test('permissions and context', () => {
    assert.deepEqual(JSON.parse(permissionsCommand('mic')), { cmd: 'permissions', request: 'mic' })
    assert.deepEqual(JSON.parse(contextCommand(['numpy', 'NumPy', ' ', 'TensorFlow'])), { cmd: 'context', terms: ['numpy', 'TensorFlow'] })
  })
})

describe('terms', () => {
  test('cleanTerms trims, dedupes case-insensitively, caps length and count', () => {
    assert.deepEqual(cleanTerms(['  numpy ', 'NUMPY', '', 5, null, 'torch']), ['numpy', 'torch'])
    assert.equal(cleanTerms(['x'.repeat(100)])[0].length, 48)
    assert.equal(cleanTerms(Array.from({ length: 200 }, (_, i) => `t${i}`)).length, 80)
  })
  test('contextTerms: lesson, step, libraries, concepts, in that order', () => {
    assert.deepEqual(contextTerms({ lessonTitle: 'Train a network', stepTitle: 'Pick a loss', libraries: ['keras'], concepts: ['optimizer'] }), ['Train a network', 'Pick a loss', 'keras', 'optimizer'])
    assert.deepEqual(contextTerms({}), [])
  })
  test('libraryNames reads imports and pip installs', () => {
    assert.deepEqual(libraryNames('import numpy as np\nfrom torch import nn\n  import os\npip install pandas'), ['numpy', 'torch', 'os', 'pandas'])
    assert.deepEqual(libraryNames('print("import me")'), [])
  })
})

describe('respawn backoff', () => {
  test('grows, then holds at the last step; never negative', () => {
    assert.equal(backoffMs(0), BACKOFF_MS[0])
    assert.ok(backoffMs(3) > backoffMs(1))
    assert.equal(backoffMs(99), BACKOFF_MS[BACKOFF_MS.length - 1])
    assert.equal(backoffMs(-4), BACKOFF_MS[0])
  })
})

describe("tccResetArgs", () => {
  test("resets miyagi and its helper for exactly one service", () => {
    assert.deepEqual(tccResetArgs("input"), [
      ["reset", "ListenEvent", "dev.sandhacks.miyagi"],
      ["reset", "ListenEvent", "dev.sandhacks.miyagi.listen"]
    ])
    assert.deepEqual(tccResetArgs("mic").map((a) => a[1]), ["Microphone", "Microphone"])
  })
})

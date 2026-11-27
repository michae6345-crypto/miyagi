/**
 * MIC-90, the lesson-complete chime (features/sound), offline: it plays once per completion on the completion card,
 * never for a card the engine replays (reconnect, a finished lesson reopened, Check after the end), never with Sounds
 * Off, and the bundled file is exactly what assets/make-chime.ts renders. A fake AudioContext counts what would reach
 * the speakers; a stubbed fetch serves the committed WAV file.
 */
import assert from 'node:assert/strict'
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { registerHooks } from 'node:module'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, beforeEach, mock, test } from 'node:test'
import { pathToFileURL } from 'node:url'

// Vite-only modules (import.meta.glob scenarios, the feature registry, assets) resolve to small stand-ins.
const dir = mkdtempSync(join(tmpdir(), 'lesson-chime-'))
const stub = (name: string, source: string): string => (writeFileSync(join(dir, name), source), pathToFileURL(join(dir, name)).href)
const EMPTY = stub('empty.mjs', 'export const scenarios = {}\nexport const defineFeature = (f) => f\nexport default "chime.wav"')
registerHooks({
  resolve(specifier, context, next) {
    if (/(^|\/)mock\/scenarios$/.test(specifier) || (context.parentURL?.includes('/src/renderer/') && /(^|\/)registry$/.test(specifier))) return { url: EMPTY, shortCircuit: true }
    if (/\.(svg|png|jpe?g|webp|css|mp3|wav|woff2?)(\?.*)?$|\?(raw|url|inline)$/.test(specifier)) return { url: EMPTY, shortCircuit: true }
    return next(specifier, context)
  }
})

const SOUND = join(__dirname, '../src/renderer/src/features/sound')
const WAV = readFileSync(join(SOUND, 'assets/lesson-complete.wav'))

// ---- a fake audio device ---------------------------------------------------------------------------------------------

type Played = { from: 'file' | 'spec'; seconds: number }
const played: Played[] = []
let fetched = 0
class FakeBuffer {
  constructor(
    readonly from: 'file' | 'spec',
    readonly length: number,
    readonly sampleRate: number
  ) {}
  get duration(): number {
    return this.length / this.sampleRate
  }
  copyToChannel(): void {}
}
class FakeAudioContext {
  state = 'running'
  sampleRate = 48000
  destination = {}
  createBuffer(_ch: number, length: number, rate: number): FakeBuffer {
    return new FakeBuffer('spec', length, rate)
  }
  decodeAudioData(bytes: ArrayBuffer): Promise<FakeBuffer> {
    assert.equal(Buffer.from(bytes).subarray(0, 4).toString('ascii'), 'RIFF', 'the bytes handed to decode are the WAV file')
    return Promise.resolve(new FakeBuffer('file', (bytes.byteLength - 44) / 2, 44100))
  }
  createBufferSource(): Record<string, unknown> {
    const src: Record<string, unknown> = {
      connect: () => undefined,
      disconnect: () => undefined,
      start: () => {
        const b = src.buffer as FakeBuffer
        played.push({ from: b.from, seconds: b.duration })
      }
    }
    return src
  }
  resume(): Promise<void> {
    return Promise.resolve()
  }
  suspend(): Promise<void> {
    return Promise.resolve()
  }
}

const g = globalThis as unknown as Record<string, unknown>
const noop = (): (() => void) => () => {}
const store = new Map<string, string>()
const tut = { platform: { os: 'darwin', keys: {}, pillTop: 0 }, onEvent: noop, onStatus: noop, on: noop, onFeature: noop, emit: () => {}, ready: () => {}, send: () => {}, invoke: () => Promise.resolve(null) }
g.window = { tut, AudioContext: FakeAudioContext, addEventListener: () => {}, removeEventListener: () => {}, matchMedia: () => ({ matches: false, addEventListener: () => {}, removeEventListener: () => {} }) }
g.document = { documentElement: { dataset: {} }, getElementById: () => ({}), createElement: () => ({}), head: { prepend: () => undefined }, addEventListener: () => {}, hidden: false }
g.location = { search: '' }
g.localStorage = { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v), removeItem: (k: string) => void store.delete(k) }
g.fetch = (url: unknown) => {
  fetched++
  assert.equal(url, 'chime.wav', 'the chime is read from the bundled asset, never the network')
  return Promise.resolve(new Response(new Uint8Array(WAV)))
}

const { dispatch, emitUi } = require('../src/renderer/src/core/bus') as typeof import('../src/renderer/src/core/bus')
const { attachSound, useSoundLog } = require('../src/renderer/src/features/sound/store') as typeof import('../src/renderer/src/features/sound/store')
const { setSoundMode } = require('../src/renderer/src/features/sound/settings') as typeof import('../src/renderer/src/features/sound/settings')
const { CUES, CHIME_MAX_MS, gainToDb, MAX_PEAK_DBFS, peakOf } = require('../src/renderer/src/features/sound/synth') as typeof import('../src/renderer/src/features/sound/synth')
const { decodeWav } = require('../src/renderer/src/features/sound/wav') as typeof import('../src/renderer/src/features/sound/wav')
const { chimeBytes } = require('../src/renderer/src/features/sound/assets/make-chime') as typeof import('../src/renderer/src/features/sound/assets/make-chime')

attachSound() // this process is the overlay: the one window that plays engine cues

const send = (type: string, payload: unknown = {}): void => dispatch({ type, payload } as never)
const STEPS = [
  { id: 's1', title: 'One' },
  { id: 's2', title: 'Two' }
]
const ready = (id = 'lesson-a', extra: object = {}): void =>
  send('lesson.ready', { lesson: { id, title: 'A lesson', sources: [] }, steps: STEPS, ...extra })
const pass = (stepId: string, extra: object = {}): void => send('step.passed', { stepId, ...extra })
const completeCard = (extra: object = {}): void => send('card', { kind: 'complete', title: 'Done', body: 'All 2 steps done.', ...extra })
const flush = async (): Promise<void> => {
  for (let i = 0; i < 5; i++) await new Promise((r) => setImmediate(r))
}
const chimes = (): Played[] => played.filter((p) => p.seconds > 0.5)
/** Let every held cue and the gap run out (the fake clock). */
const later = async (ms = 3000): Promise<void> => {
  await flush() // sound:idle answers first (a few ms in the app), then the clock moves
  mock.timers.tick(ms)
  await flush()
}

beforeEach(() => {
  mock.timers.enable({ apis: ['setTimeout', 'Date'], now: 5_000_000 })
  emitUi('reset')
  played.length = 0
  setSoundMode('subtle')
})
afterEach(() => {
  emitUi('reset')
  mock.timers.reset()
})

test('finishing a lesson plays the chime once, from the bundled file, on the completion card', async () => {
  ready()
  pass('s1')
  await later()
  pass('s2') // the last step: no tick of its own, the chime is the lesson's one sound at the end
  await later()
  assert.equal(chimes().length, 0, 'nothing before the completion card')
  completeCard()
  await later()
  assert.equal(chimes().length, 1, 'one chime on the completion card')
  assert.equal(chimes()[0].from, 'file', 'played from assets/lesson-complete.wav')
  assert.ok(fetched >= 1)
  assert.equal(played.length, 2, 'one tick for step 1, then the chime: no tick for the last step')
  assert.equal(useSoundLog.getState().last?.cue, 'chime')

  completeCard() // Check or Skip after the end: the engine sends the ending again
  completeCard({ kind: 'answer', skillMap: { headline: 'x' } }) // a card after the end that carries the skill map
  await later()
  assert.equal(chimes().length, 1, 'never a second chime for the same completion')
})

test('a completion card with only a skill map (the older kind) chimes too, once', async () => {
  ready()
  pass('s2')
  send('card', { kind: 'step', title: 'Done', body: '', skillMap: { headline: 'Two skills' } })
  await later()
  assert.equal(chimes().length, 1)
})

test('never when a finished lesson is reopened or replayed', async () => {
  // Reconnect / engine restore of a finished lesson: replayed lesson.ready, then the ending card.
  ready('lesson-a', { replay: true })
  send('step.started', { stepId: 's2', index: 1, title: 'Two', instructions: '', replay: true })
  completeCard()
  await later()
  // The finished lesson opened again (library / a re-sent learn): a fresh lesson.ready, then the ending card.
  ready('lesson-a')
  completeCard()
  await later()
  assert.equal(chimes().length, 0, 'no step passed live: no chime')
})

test('a reconnect between the last pass and the card replays it: no chime (the safe side)', async () => {
  ready()
  pass('s2')
  // The engine's snapshot. Core drops the replayed lesson.ready of the lesson already loaded before any feature sees
  // it (core/lesson setGate), so the replayed step.started is what tells the guard.
  ready('lesson-a', { replay: true })
  send('step.started', { stepId: 's2', index: 1, title: 'Two', instructions: '', replay: true })
  completeCard()
  await later()
  assert.equal(chimes().length, 0)
})

test('a pass in one lesson never arms the next lesson', async () => {
  ready('lesson-a')
  pass('s1')
  ready('lesson-b')
  completeCard()
  await later()
  assert.equal(chimes().length, 0)
})

test('finishing the same lesson again later (from step 1) is a new completion', async () => {
  ready()
  pass('s2')
  completeCard()
  await later()
  ready()
  pass('s1')
  await later()
  pass('s2')
  completeCard()
  await later()
  assert.equal(chimes().length, 2)
})

test('Sounds Off in Settings silences it', async () => {
  setSoundMode('off')
  ready()
  pass('s1')
  pass('s2')
  completeCard()
  await later()
  assert.equal(played.length, 0, 'nothing reaches the speakers')
  const last = useSoundLog.getState().last
  assert.equal(last?.cue, 'chime')
  assert.deepEqual(last?.verdict, { play: false, reason: 'off' })
})

test('the bundled file is what make-chime.ts renders: under 1 s, quiet, starts and ends on silence', () => {
  assert.ok(Buffer.from(chimeBytes()).equals(WAV), 'assets/lesson-complete.wav is stale: run assets/make-chime.ts')
  const wav = decodeWav(new Uint8Array(WAV))
  assert.ok(wav)
  const ms = (wav.samples.length / wav.sampleRate) * 1000
  assert.ok(ms > 300 && ms < CHIME_MAX_MS && ms === CUES.chime.durationMs, `length ${ms} ms`)
  const peak = gainToDb(peakOf(wav.samples))
  assert.ok(peak <= MAX_PEAK_DBFS && Math.abs(peak - CUES.chime.peakDbfs) < 0.05, `peak ${peak} dBFS`)
  assert.equal(wav.samples[0], 0)
  assert.equal(wav.samples[wav.samples.length - 1], 0)
})

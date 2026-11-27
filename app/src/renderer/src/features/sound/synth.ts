/**
 * Feature: sound. The cues, synthesized as plain sample arrays: no network, no WebAudio nodes beyond one buffer
 * source. The same function renders the samples the app plays and the samples the Node check (sound.check.ts)
 * measures, so "under -24 dBFS and under 250 ms" is checked on exactly what the learner hears.
 *
 *   tick   a step passed: one soft, woody tick (about 70 ms)
 *   done   setup finished: two gentle notes a fifth apart (about 240 ms)
 *   tap    a primary press (optional sub-toggle): barely there (about 35 ms)
 *   chime  a lesson completed (MIC-90): two soft bell notes a fifth apart, ringing out (900 ms). The app plays it
 *          from the bundled file assets/lesson-complete.wav, which assets/make-chime.ts renders from this spec
 *          (a test checks the file still matches); renderCue('chime') is the fallback when the file can't load.
 *
 * Pure module: no imports, so Node runs it directly (npx tsx).
 */

export type Cue = 'tick' | 'done' | 'tap' | 'chime'

/** Hard ceilings (Michael: subtle, short). The check fails if any cue crosses them. */
export const MAX_PEAK_DBFS = -24
export const MAX_DURATION_MS = 250
/** The lesson-complete chime alone may ring longer (MIC-90: "under 1 s"). */
export const CHIME_MAX_MS = 1000
/** The longest a cue may run: every cue but the chime stays under MAX_DURATION_MS. */
export const maxDurationMs = (cue: Cue): number => (cue === 'chime' ? CHIME_MAX_MS : MAX_DURATION_MS)

type Overtone = { ratio: number; gain: number; tau: number }
type Note = { freq: number; at: number; tau: number; partials: Overtone[] }
type CueSpec = { durationMs: number; peakDbfs: number; attackMs: number; notes: Note[]; /** tail fade, default 12 ms */ fadeMs?: number }

/*
 * Each note is a sine with a short raised-cosine attack and an exponential decay (tau, seconds), plus quieter upper
 * partials that die faster, which is what makes a struck wood or glass sound soft rather than beepy. The whole cue is
 * then scaled so its peak lands exactly on peakDbfs, and the tail (12 ms, or the cue's fadeMs) fades to zero so it
 * never ends on a click.
 */
export const CUES: Record<Cue, CueSpec> = {
  tick: {
    durationMs: 70,
    peakDbfs: -30,
    attackMs: 1.5,
    notes: [{ freq: 1244.5, at: 0, tau: 0.016, partials: [{ ratio: 2.76, gain: 0.16, tau: 0.006 }] }]
  },
  done: {
    durationMs: 240,
    peakDbfs: -27,
    attackMs: 4,
    notes: [
      // G5 then D6 (a rising fifth): resolved, not a fanfare.
      { freq: 783.99, at: 0, tau: 0.075, partials: [{ ratio: 2, gain: 0.12, tau: 0.03 }] },
      { freq: 1174.66, at: 0.085, tau: 0.07, partials: [{ ratio: 2, gain: 0.1, tau: 0.028 }] }
    ]
  },
  tap: {
    durationMs: 35,
    peakDbfs: -36,
    attackMs: 1,
    notes: [{ freq: 680, at: 0, tau: 0.0065, partials: [] }]
  },
  chime: {
    // MIC-90: one calm chime on the completion screen, not a "level up". D5 then A5 (a rising fifth, like done, a
    // register lower and slower), each a soft bell: the octave and a slightly sharp twelfth die quickly, the
    // fundamental rings out. Quieter than a notification, under 1 s, no fanfare.
    durationMs: 900,
    peakDbfs: -26,
    attackMs: 6,
    fadeMs: 160,
    notes: [
      { freq: 587.33, at: 0, tau: 0.26, partials: [{ ratio: 2, gain: 0.16, tau: 0.12 }, { ratio: 3.01, gain: 0.05, tau: 0.05 }] },
      { freq: 880.0, at: 0.14, tau: 0.24, partials: [{ ratio: 2, gain: 0.14, tau: 0.11 }, { ratio: 3.01, gain: 0.04, tau: 0.045 }] }
    ]
  }
}

const FADE_OUT_S = 0.012

export const dbToGain = (db: number): number => Math.pow(10, db / 20)
export const gainToDb = (g: number): number => (g <= 0 ? -Infinity : 20 * Math.log10(g))

/** Render one cue at a sample rate. Mono, Float32, peak exactly at the cue's peakDbfs. */
export function renderCue(cue: Cue, sampleRate: number): Float32Array<ArrayBuffer> {
  const spec = CUES[cue]
  const n = Math.round((spec.durationMs / 1000) * sampleRate)
  const out = new Float32Array(n)
  const attack = spec.attackMs / 1000
  for (const note of spec.notes) {
    const start = Math.round(note.at * sampleRate)
    const voices = [{ ratio: 1, gain: 1, tau: note.tau }, ...note.partials]
    for (let i = start; i < n; i++) {
      const t = (i - start) / sampleRate
      const rise = t < attack ? 0.5 - 0.5 * Math.cos((Math.PI * t) / attack) : 1
      let s = 0
      for (const v of voices) s += v.gain * Math.exp(-t / v.tau) * Math.sin(2 * Math.PI * note.freq * v.ratio * t)
      out[i] += rise * s
    }
  }
  // Tail: a raised-cosine fade to exactly zero.
  const fade = Math.min(n, Math.round((spec.fadeMs !== undefined ? spec.fadeMs / 1000 : FADE_OUT_S) * sampleRate))
  for (let k = 0; k < fade; k++) out[n - fade + k] *= 0.5 + 0.5 * Math.cos((Math.PI * (k + 1)) / fade)
  // Normalize the peak to the cue's level.
  const peak = peakOf(out)
  if (peak > 0) {
    const g = dbToGain(spec.peakDbfs) / peak
    for (let i = 0; i < n; i++) out[i] *= g
  }
  return out
}

export function peakOf(buf: Float32Array): number {
  let p = 0
  for (let i = 0; i < buf.length; i++) {
    const a = Math.abs(buf[i])
    if (a > p) p = a
  }
  return p
}

/** A coarse loudness outline (max |sample| per bucket, 0..1 of the cue's own peak), for the stage monitor's bars. */
export function outline(buf: Float32Array, buckets: number): number[] {
  const peak = peakOf(buf) || 1
  const size = Math.max(1, Math.floor(buf.length / buckets))
  const bars: number[] = []
  for (let b = 0; b < buckets; b++) {
    let m = 0
    for (let i = b * size; i < Math.min(buf.length, (b + 1) * size); i++) m = Math.max(m, Math.abs(buf[i]))
    bars.push(m / peak)
  }
  return bars
}

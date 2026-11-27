/**
 * Feature: sound. Plays a rendered cue through WebAudio: one AudioContext, made on the first cue (never at startup),
 * one cached AudioBuffer per cue, one buffer source per play straight to the speakers. The context suspends after
 * two quiet seconds so an idle miyagi costs no audio thread.
 *
 * The lesson-complete chime (MIC-90) plays the bundled file assets/lesson-complete.wav (a Vite asset: no network,
 * the renderer's own origin), decoded once. If the file can't be read or decoded, the same sound is rendered from
 * its spec in synth.ts (the file is made from that spec, so both sound the same).
 *
 * dry (stage ?sound=dry): no context is ever created; the monitor still shows what would have played.
 */
import chimeUrl from './assets/lesson-complete.wav?url'
import { renderCue, type Cue } from './synth'

let ctx: AudioContext | undefined
const buffers = new Map<Cue, AudioBuffer>()
let idle: ReturnType<typeof setTimeout> | undefined
const IDLE_MS = 2000

function context(): AudioContext | undefined {
  if (ctx) return ctx
  const Ctor = typeof window !== 'undefined' ? (window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext) : undefined
  if (!Ctor) return undefined
  try {
    ctx = new Ctor({ latencyHint: 'interactive' })
  } catch {
    return undefined
  }
  return ctx
}

function buffer(c: AudioContext, cue: Cue): AudioBuffer {
  let b = buffers.get(cue)
  if (b && b.sampleRate === c.sampleRate) return b
  const samples = renderCue(cue, c.sampleRate)
  b = c.createBuffer(1, samples.length, c.sampleRate)
  b.copyToChannel(samples, 0)
  buffers.set(cue, b)
  return b
}

/** The chime file, decoded once per context (undefined: not read yet; null: unreadable, use the spec). */
let chimeFile: Promise<AudioBuffer | null> | undefined
function fileChime(c: AudioContext): Promise<AudioBuffer | null> {
  if (!chimeFile) {
    chimeFile = fetch(chimeUrl)
      .then((r) => (r.ok ? r.arrayBuffer() : Promise.reject(new Error(String(r.status)))))
      .then((bytes) => c.decodeAudioData(bytes))
      .catch(() => null)
  }
  return chimeFile
}

function start(c: AudioContext, b: AudioBuffer): boolean {
  try {
    if (c.state === 'suspended') void c.resume().catch(() => undefined)
    const src = c.createBufferSource()
    src.buffer = b
    src.connect(c.destination)
    src.onended = () => src.disconnect()
    src.start()
  } catch {
    return false
  }
  if (idle) clearTimeout(idle)
  // The chime rings 900 ms: never suspend under it.
  idle = setTimeout(() => void ctx?.suspend().catch(() => undefined), Math.max(IDLE_MS, b.duration * 1000 + 500))
  return true
}

/** Play one cue now. Returns false when audio isn't available (no context, or it refused to start). */
export function playCue(cue: Cue, dry = false): boolean {
  if (dry) return true
  const c = context()
  if (!c) return false
  if (cue === 'chime') {
    // A local asset decodes in a few ms; only an unreadable file falls back to the rendered spec.
    void fileChime(c).then((b) => {
      try {
        start(c, b ?? buffer(c, cue))
      } catch {
        /* no audio */
      }
    })
    return true
  }
  try {
    return start(c, buffer(c, cue))
  } catch {
    return false
  }
}

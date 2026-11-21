/**
 * Feature: sound. Plays a rendered cue through WebAudio: one AudioContext, made on the first cue (never at startup),
 * one cached AudioBuffer per cue, one buffer source per play straight to the speakers. The context suspends after
 * two quiet seconds so an idle miyagi costs no audio thread.
 *
 * dry (stage ?sound=dry): no context is ever created; the monitor still shows what would have played.
 */
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

/** Play one cue now. Returns false when audio isn't available (no context, or it refused to start). */
export function playCue(cue: Cue, dry = false): boolean {
  if (dry) return true
  const c = context()
  if (!c) return false
  try {
    if (c.state === 'suspended') void c.resume().catch(() => undefined)
    const src = c.createBufferSource()
    src.buffer = buffer(c, cue)
    src.connect(c.destination)
    src.onended = () => src.disconnect()
    src.start()
  } catch {
    return false
  }
  if (idle) clearTimeout(idle)
  idle = setTimeout(() => void ctx?.suspend().catch(() => undefined), IDLE_MS)
  return true
}

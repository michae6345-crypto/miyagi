/**
 * Feature: sound. A 16-bit PCM mono WAV encoder for the bundled chime (assets/make-chime.ts writes the file with it,
 * test/lessonChime.test.ts checks the committed file is byte for byte what it writes today). No dither, so the same
 * samples always give the same bytes.
 *
 * Pure module: no imports.
 */

/** The chime file's sample rate. decodeAudioData resamples to the context's rate (44.1 or 48 kHz). */
export const WAV_RATE = 44100

export function encodeWav(samples: Float32Array, sampleRate: number): Uint8Array<ArrayBuffer> {
  const data = samples.length * 2
  const out = new Uint8Array(44 + data)
  const v = new DataView(out.buffer)
  const ascii = (at: number, s: string): void => {
    for (let i = 0; i < s.length; i++) out[at + i] = s.charCodeAt(i)
  }
  ascii(0, 'RIFF')
  v.setUint32(4, 36 + data, true)
  ascii(8, 'WAVE')
  ascii(12, 'fmt ')
  v.setUint32(16, 16, true) // fmt chunk size
  v.setUint16(20, 1, true) // PCM
  v.setUint16(22, 1, true) // mono
  v.setUint32(24, sampleRate, true)
  v.setUint32(28, sampleRate * 2, true) // byte rate
  v.setUint16(32, 2, true) // block align
  v.setUint16(34, 16, true) // bits per sample
  ascii(36, 'data')
  v.setUint32(40, data, true)
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]))
    v.setInt16(44 + i * 2, Math.round(s * 32767), true)
  }
  return out
}

/** Read back the samples of a file encodeWav wrote (16-bit PCM mono only), for the check. */
export function decodeWav(bytes: Uint8Array): { sampleRate: number; samples: Float32Array } | undefined {
  if (bytes.length < 44) return undefined
  const v = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength)
  const tag = (at: number): string => String.fromCharCode(...bytes.subarray(at, at + 4))
  if (tag(0) !== 'RIFF' || tag(8) !== 'WAVE' || tag(36) !== 'data') return undefined
  if (v.getUint16(20, true) !== 1 || v.getUint16(22, true) !== 1 || v.getUint16(34, true) !== 16) return undefined
  const n = Math.floor(v.getUint32(40, true) / 2)
  const samples = new Float32Array(n)
  for (let i = 0; i < n; i++) samples[i] = v.getInt16(44 + i * 2, true) / 32767
  return { sampleRate: v.getUint32(24, true), samples }
}

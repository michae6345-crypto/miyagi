/**
 * Writes assets/lesson-complete.wav, the lesson-complete chime (MIC-90), from the `chime` spec in ../synth.ts:
 *
 *   npx tsx src/renderer/src/features/sound/assets/make-chime.ts      (from app/)
 *
 * Change the sound by changing CUES.chime in synth.ts, then run this again and commit both files.
 * test/lessonChime.test.ts fails if the committed file no longer matches what this writes.
 */
import { writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { renderCue } from '../synth'
import { encodeWav, WAV_RATE } from '../wav'

export const CHIME_FILE = 'lesson-complete.wav'

export function chimeBytes(): Uint8Array {
  return encodeWav(renderCue('chime', WAV_RATE), WAV_RATE)
}

if (process.argv[1] && /make-chime\.ts$/.test(process.argv[1].split('\\').join('/'))) {
  const out = join(__dirname, CHIME_FILE)
  const bytes = chimeBytes()
  writeFileSync(out, bytes)
  console.log(`wrote ${out} (${bytes.length} bytes, ${WAV_RATE} Hz, 16-bit mono)`)
}

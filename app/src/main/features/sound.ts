/**
 * Feature: sound (main). One question for the renderer: is macOS in Do Not Disturb / a Focus right now?
 *
 *   bridge.invoke('sound:dnd') -> boolean   true only when it can be read AND a Focus is on; false otherwise
 *
 * macOS keeps the manually turned-on Focus in ~/Library/DoNotDisturb/DB/Assertions.json (macOS 12+): one record per
 * active assertion. On newer macOS that file can need Full Disk Access; any read or parse failure answers false
 * ("not detectable: ignore"), never an error and never a prompt. A scheduled Focus with no assertion isn't seen.
 * Cached for 15 s, read without blocking. Windows: always false.
 *
 * UNVERIFIED in Electron (no app runs during this lane): typechecked, and the parse is covered by sound.check.ts.
 */
import { readFile } from 'node:fs/promises'
import { homedir } from 'node:os'
import { join } from 'node:path'
import { defineMainFeature } from '../context'

const CACHE_MS = 15_000
let cached: { at: number; on: boolean } | undefined

/** Exported for the check: does an Assertions.json body say a Focus is on? */
export function focusOn(json: unknown): boolean {
  const data = (json as { data?: unknown } | null)?.data
  if (!Array.isArray(data)) return false
  return data.some((d) => Array.isArray((d as { storeAssertionRecords?: unknown })?.storeAssertionRecords) && (d as { storeAssertionRecords: unknown[] }).storeAssertionRecords.length > 0)
}

async function readFocus(): Promise<boolean> {
  if (process.platform !== 'darwin') return false
  if (cached && Date.now() - cached.at < CACHE_MS) return cached.on
  let on = false
  try {
    on = focusOn(JSON.parse(await readFile(join(homedir(), 'Library/DoNotDisturb/DB/Assertions.json'), 'utf8')))
  } catch {
    on = false
  }
  cached = { at: Date.now(), on }
  return on
}

export default defineMainFeature({
  id: 'sound',
  setup(ctx) {
    ctx.handle('sound:dnd', () => readFocus())
  }
})

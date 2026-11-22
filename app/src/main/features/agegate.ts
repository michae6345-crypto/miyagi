/**
 * Main-process feature: the age step's record (renderer: features/agegate/). No window of its own.
 *
 *   agegate:get   → AgeRecord | null    {band, confirmed} | {blockedUntil}; a lapsed block reads as null
 *   agegate:set   (record) → AgeRecord | null   merged with what is on file: a block in force wins, so going back,
 *                 quitting or relaunching and picking another date can't lift it (agegate/store.ts, age.ts mergeRecord)
 *   broadcast feat:agegate (AgeRecord | null) after every change, and after Delete account wipes it (accountDelete.ts)
 *
 * The renderer sends only the result: the birth date never leaves the screen's memory. auth.ts asks ageStepCleared()
 * before a Google sign-in or "Continue without an account", so nothing gets past the step through IPC either.
 */
import { join } from 'node:path'
import { defineMainFeature } from '../context'
import { ageCleared, todayOf } from '../../renderer/src/features/agegate/age'
import { AGE_FILE, readAge, writeAge } from './agegate/store'

let file: string | undefined
let publish: (() => void) | undefined

/**
 * The step is through on this Mac: a band on file and no block in force. auth.ts refuses a sign-in or the guest path
 * otherwise. True before this feature is set up (the offline auth tests drive auth.ts alone).
 */
export function ageStepCleared(): boolean {
  return !file || ageCleared(readAge(file, todayOf()), todayOf())
}

/** accountDelete.ts: age.json is gone; tell the windows (the next login asks again). */
export function ageForgotten(): void {
  publish?.()
}

export default defineMainFeature({
  id: 'agegate',
  setup(ctx) {
    const f = join(ctx.app.getPath('userData'), AGE_FILE)
    file = f
    const now = (): ReturnType<typeof readAge> | null => readAge(f, todayOf()) ?? null
    publish = () => ctx.broadcast('agegate', now())
    ctx.handle('agegate:get', () => now())
    ctx.handle('agegate:set', (next) => {
      writeAge(f, next, todayOf())
      publish?.()
      return now()
    })
  }
})

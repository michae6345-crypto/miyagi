/**
 * Settings › Privacy › Delete my data, the file part (main/features/settings.ts settings:delete). No Electron here, so
 * erase.test.ts runs it with node --test.
 *
 *   SIGN_IN_FILES        what auth.ts keeps in userData: the encrypted session (auth.bin), the "made a choice at the
 *                        login" flag (login.json), and their write-then-rename leftovers
 *   removeFiles(dir, …)  unlink each one that exists → true when none is left behind
 *
 * The session in auth.ts's memory is forgotten by auth:sign-out (the renderer calls it right after), so a later
 * refresh can't write auth.bin back.
 */
import { existsSync, unlinkSync } from 'node:fs'
import { join } from 'node:path'

export const SIGN_IN_FILES = ['auth.bin', 'auth.bin.tmp', 'login.json', 'login.json.tmp'] as const

type Fs = { existsSync(p: string): boolean; unlinkSync(p: string): void }

/** Remove every file that exists; one that can't be removed doesn't stop the others. → true: none is left. */
export function removeFiles(dir: string, names: readonly string[], fs: Fs = { existsSync, unlinkSync }): boolean {
  let ok = true
  for (const name of names) {
    const file = join(dir, name)
    try {
      if (fs.existsSync(file)) fs.unlinkSync(file)
    } catch {
      ok = false // never log the path's error: it names the user's home folder
    }
  }
  return ok
}

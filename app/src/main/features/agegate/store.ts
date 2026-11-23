/**
 * The age step's record on disk (userData/age.json), apart from Electron so store.test.ts runs it with node --test.
 * The shapes and the merge rule live in the renderer's pure module (features/agegate/age.ts), shared with the screen.
 *
 *   readAge(file, today)          the record, cleaned; a block that has lapsed reads as none
 *   writeAge(file, next, today)   merge with what is on file (a block in force wins), write atomically, 0600
 *
 * Never the birth date: only {band, confirmed} or {blockedUntil} ever reach the file (cleanRecord drops the rest).
 */
import { existsSync, readFileSync, renameSync, rmSync, writeFileSync } from 'node:fs'
import { blockActive, cleanRecord, mergeRecord, type AgeRecord, type Day } from '../../../renderer/src/features/agegate/age'

export const AGE_FILE = 'age.json'

export function readAge(file: string, today: Day): AgeRecord | undefined {
  if (!existsSync(file)) return undefined
  try {
    const r = cleanRecord(JSON.parse(readFileSync(file, 'utf8')))
    if (r && 'blockedUntil' in r && !blockActive(r, today)) return undefined
    return r
  } catch {
    return undefined
  }
}

/** → the record now on file (the old one when `next` changed nothing or the write failed). */
export function writeAge(file: string, next: unknown, today: Day): AgeRecord | undefined {
  const prev = readAge(file, today)
  const merged = mergeRecord(prev, next, today)
  if (!merged || merged === prev) return prev
  try {
    const tmp = `${file}.tmp`
    writeFileSync(tmp, JSON.stringify(merged), { mode: 0o600 })
    renameSync(tmp, file)
    return merged
  } catch {
    rmSync(`${file}.tmp`, { force: true })
    return prev
  }
}

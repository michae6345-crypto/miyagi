/**
 * Feature: agegate. Browser-stage stand-ins for main/features/agegate.ts (nothing here runs in Electron). Like main,
 * the stage keeps ONLY the result (localStorage 'miyagi.stage.age'), merged by the same rule (age.ts mergeRecord), so a
 * reload can't get past a block either.
 *   ?age=reset     start with nothing on record (the birthday screen)
 *   ?age=blocked   a block in force (the under-13 screen)
 *   ?age=teen | adult   the step already through (straight to the sign-in)
 *   ?age=keep      keep what the stage remembered
 *   default        reset on every load, so the shots always start on the birthday screen
 */
import { isElectron, registerWebHandler } from '../../bridge'
import { bandRecord, cleanRecord, iso, mergeRecord, todayOf, type AgeRecord } from './age'

const KEY = 'miyagi.stage.age'

function read(): AgeRecord | undefined {
  try {
    return cleanRecord(JSON.parse(localStorage.getItem(KEY) ?? 'null'))
  } catch {
    return undefined
  }
}
function write(r: AgeRecord | undefined): void {
  try {
    if (r) localStorage.setItem(KEY, JSON.stringify(r))
    else localStorage.removeItem(KEY)
  } catch {
    /* no storage: memory only */
  }
}

if (!isElectron) {
  const v = new URLSearchParams(location.search).get('age')
  const today = todayOf()
  let mem: AgeRecord | undefined
  if (v === 'blocked') mem = { blockedUntil: iso({ y: today.y + 2, m: 1, d: 1 }) }
  else if (v === 'teen') mem = bandRecord('13-17', today)
  else if (v === 'adult') mem = bandRecord('18+', today)
  else if (v === 'keep') mem = read()
  write(mem)
  registerWebHandler('agegate:get', () => mem ?? null)
  registerWebHandler('agegate:quit', () => {
    console.log('[stage] agegate:quit (a built app quits here)')
    return true
  })
  registerWebHandler('agegate:set', (next) => {
    const merged = mergeRecord(mem, next, todayOf())
    if (merged) mem = merged
    write(mem)
    return mem ?? null
  })
}

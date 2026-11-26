/**
 * Main: "switched on in System Settings, but miyagi must restart to use it". No electron import (tested offline).
 *
 * macOS caches a process's Screen Recording answer: after the learner switches miyagi on, this (long-running) main
 * process keeps reading "denied" from getMediaAccessStatus('screen') until it relaunches, and so does the engine it
 * started (server/screen preflights in its own long-running process). A FRESH process reads the grant as it is now, and
 * macOS answers for the process it holds responsible: miyagi, which spawned it. So main asks a fresh `miyagi-listen
 * --screens` (one-shot, no prompts; its `perms` field, native/listen/Screens.swift) and compares: granted there, not
 * granted here = restart needed. An older helper prints no `perms`: no answer, nothing changes (never a guess).
 */
import { execFile } from 'node:child_process'
import { existsSync } from 'node:fs'

export type RelaunchKind = 'screen' | 'accessibility'
export type Fresh = Partial<Record<RelaunchKind, 'granted' | 'denied'>>

const KINDS: readonly RelaunchKind[] = ['screen', 'accessibility']
/** A warm probe answers in ~30-40 ms; this is the ceiling. */
export const PROBE_TIMEOUT_MS = 2000
/** The first probe of a run: Gatekeeper's first scan of a freshly installed helper can take longer than 2 s (#286). */
export const FIRST_PROBE_TIMEOUT_MS = 4000
/** A probe spawns a process: at most this often, and only while something is not granted (#286: 1 s). */
export const PROBE_MIN_MS = 1000

/** The `perms` field of the helper's --screens line. Never throws; undefined when there is none (an older helper). */
export function parseFreshPerms(text: string): Fresh | undefined {
  try {
    const line = text.split('\n').find((l) => l.trim().startsWith('{')) ?? ''
    const p = (JSON.parse(line) as { perms?: unknown }).perms
    if (!p || typeof p !== 'object') return undefined
    const out: Fresh = {}
    for (const k of KINDS) {
      const v = (p as Record<string, unknown>)[k]
      if (v === 'granted' || v === 'denied') out[k] = v
    }
    return Object.keys(out).length ? out : undefined
  } catch {
    return undefined
  }
}

/** The kinds a fresh process sees as granted while this one doesn't: only a relaunch picks them up. */
export function relaunchKinds(here: Partial<Record<RelaunchKind, string>>, fresh: Fresh | undefined): RelaunchKind[] {
  if (!fresh) return []
  return KINDS.filter((k) => here[k] !== undefined && here[k] !== 'granted' && here[k] !== 'unknown' && here[k] !== 'restricted' && fresh[k] === 'granted')
}

/** Run the helper's --screens and read its `perms`. Resolves undefined on any failure (missing, timeout, old helper). */
export function probeFreshPerms(bin: string, timeoutMs: number = PROBE_TIMEOUT_MS): Promise<Fresh | undefined> {
  return new Promise((resolve) => {
    try {
      if (!bin || !existsSync(bin)) return resolve(undefined)
      execFile(bin, ['--screens'], { timeout: timeoutMs, maxBuffer: 1 << 20 }, (err, stdout) => resolve(err ? undefined : parseFreshPerms(String(stdout))))
    } catch {
      resolve(undefined)
    }
  })
}

/** After this many probes with the same answer, wait longer between probes: BACKOFF_MS[0], then [1] after twice as many. */
export const BACKOFF_AFTER = 10
export const BACKOFF_MS = [10_000, 30_000] as const

/**
 * A rate-limited probe: answers the last result when asked again within `minMs`, one call in flight at a time. A probe
 * that gives no answer (a timeout on a slow Mac) keeps the last good one, so "Restart miyagi" doesn't flicker away (#286).
 * Ten answers in a row that change nothing slow it to every 10 s, twenty to every 30 s; a change speeds it up again.
 * `peek()` is the last answer without probing; `reset()` forgets it (everything is granted now: nothing to ask).
 */
export function throttledProbe(
  probe: () => Promise<Fresh | undefined>,
  minMs = PROBE_MIN_MS,
  now: () => number = Date.now
): { get(): Promise<Fresh | undefined>; peek(): Fresh | undefined; reset(): void } {
  let last: Fresh | undefined
  let at = -Infinity
  let same = 0
  let inflight: Promise<Fresh | undefined> | undefined
  const gap = (): number => (same >= 2 * BACKOFF_AFTER ? BACKOFF_MS[1] : same >= BACKOFF_AFTER ? BACKOFF_MS[0] : minMs)
  return {
    get() {
      if (inflight) return inflight
      if (now() - at < gap()) return Promise.resolve(last)
      inflight = probe()
        .catch(() => undefined)
        .then((r) => {
          const next = r ?? last
          same = JSON.stringify(next) === JSON.stringify(last) ? same + 1 : 0
          last = next
          at = now()
          return last
        })
        .finally(() => (inflight = undefined))
      return inflight
    },
    peek: () => last,
    reset() {
      last = undefined
      at = -Infinity
      same = 0
    }
  }
}

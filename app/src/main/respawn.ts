/**
 * ROADMAP 1.4: how often main may start a crashed (or hung) engine again on its own (features/recover.ts). Pure, no
 * Electron, so it can be tested with plain node.
 *
 * Each respawn waits a little longer (DELAYS_MS). At most MAX_RESPAWNS inside WINDOW_MS: an engine that keeps dying
 * is a real failure, so the next crash is reported and the learner gets Retry (which starts over with a fresh budget).
 */
export const DELAYS_MS = [500, 2000, 5000] as const
export const MAX_RESPAWNS = 3
export const WINDOW_MS = 3 * 60_000

export class RespawnBudget {
  private times: number[] = []

  constructor(
    private readonly delays: readonly number[] = DELAYS_MS,
    private readonly max = MAX_RESPAWNS,
    private readonly windowMs = WINDOW_MS
  ) {}

  /** May it start again now? The wait before it does, or undefined when the budget is spent. */
  next(now = Date.now()): number | undefined {
    this.times = this.times.filter((t) => now - t < this.windowMs)
    if (this.times.length >= this.max) return undefined
    const delay = this.delays[Math.min(this.times.length, this.delays.length - 1)]
    this.times.push(now)
    return delay
  }

  /** A fresh budget (the learner pressed Retry, or the engine stayed up long enough). */
  reset(): void {
    this.times = []
  }

  /** Respawns counted in the window right now. */
  used(now = Date.now()): number {
    return this.times.filter((t) => now - t < this.windowMs).length
  }
}

/**
 * Hung, not dead: the engine this app started is still alive but the link has been down this long while the Mac is
 * awake. Then main restarts it (same budget). Longer than a sleep's reconnect and an engine's busy spell.
 */
export const HUNG_MS = 30_000

/** What superviseEngine needs from main (features/recover.ts wires the real engine link and localEngine.ts). */
export type SuperviseIo = {
  /** The engine link is open right now. */
  connected(): boolean
  onStatus(fn: (up: boolean) => void): void
  /** The engine this app started is running and its process is alive (never one the user runs in Terminal). */
  ownEngineAlive(): boolean
  /** The same restart as the offline card's Restart (localEngine.ts restartLocalEngine). */
  restart(): void
  /** localEngine.ts setRespawnPolicy: asked when the app's engine dies mid-run. */
  setPolicy(policy: (why: string) => number | undefined): void
  warn?(line: string): void
  error?(line: string): void
}

/**
 * The engine side of recovery, one budget for both ways an engine stops answering:
 *   crashed  localEngine asks the policy: the next wait from the budget, or undefined (spent: reported, Retry).
 *   hung     ours, alive, but the link has been down hungMs while the Mac is awake: restart it (same budget).
 * An engine that answers again after a spent budget earns a fresh one. suspend() / resume() follow the Mac's sleep:
 * no hung verdict across a sleep (the link's own wake probe and reconnect handle that).
 */
export function superviseEngine(io: SuperviseIo, budget = new RespawnBudget(), hungMs = HUNG_MS): { suspend(): void; resume(): void } {
  const warn = io.warn ?? ((l: string): void => console.warn(l))
  const error = io.error ?? ((l: string): void => console.error(l))
  io.setPolicy((why) => {
    const delay = budget.next()
    if (delay === undefined) error(`[recover] engine ${why} again; it keeps stopping, so it is reported (Retry starts it)`)
    else warn(`[recover] engine ${why}; starting it again in ${delay} ms (${budget.used()} of ${MAX_RESPAWNS})`)
    return delay
  })
  let hung: ReturnType<typeof setTimeout> | undefined
  let asleep = false
  const watchHung = (open: boolean): void => {
    clearTimeout(hung)
    hung = undefined
    if (open || asleep) return
    hung = setTimeout(() => {
      hung = undefined
      if (io.connected() || asleep || !io.ownEngineAlive()) return
      if (budget.next() === undefined) return error('[recover] engine alive but not answering, and the restart budget is spent')
      warn(`[recover] engine alive but not answering for ${Math.round(hungMs / 1000)} s; restarting it`)
      io.restart()
    }, hungMs)
    hung.unref?.()
  }
  io.onStatus((up) => {
    if (up && budget.used() >= MAX_RESPAWNS) budget.reset()
    watchHung(up)
  })
  return {
    suspend() {
      asleep = true
      watchHung(true)
    },
    resume() {
      asleep = false
      watchHung(io.connected())
    }
  }
}

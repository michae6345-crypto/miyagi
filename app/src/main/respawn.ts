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

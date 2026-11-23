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
 * The hung clock starts when the link goes from up (or never up) to down. The link reports "down" again on every failed
 * attempt (each close, each 1 s retry, each handshake timeout), and those repeats must not restart the clock, or a hung
 * engine is never caught. Still down hungMs after a restart: checked again, until the budget is spent.
 * A spent budget (reported) is fresh again once an engine answers: Retry, or one the user started. An engine that
 * answers and then crashes again keeps spending the same budget, so a crash loop still ends in Retry.
 * suspend() / resume() follow the Mac's sleep: no hung verdict across a sleep (the link's own wake probe and reconnect
 * handle that); resume() starts the clock again if the link is still down.
 */
export function superviseEngine(io: SuperviseIo, budget = new RespawnBudget(), hungMs = HUNG_MS): { suspend(): void; resume(): void } {
  const warn = io.warn ?? ((l: string): void => console.warn(l))
  const error = io.error ?? ((l: string): void => console.error(l))
  /** The budget ran out and the failure was reported. */
  let spent = false
  io.setPolicy((why) => {
    const delay = budget.next()
    if (delay === undefined) {
      spent = true
      error(`[recover] engine ${why} again; it keeps stopping, so it is reported (Retry starts it)`)
    } else warn(`[recover] engine ${why}; starting it again in ${delay} ms (${budget.used()} of ${MAX_RESPAWNS})`)
    return delay
  })
  let hung: ReturnType<typeof setTimeout> | undefined
  let asleep = false
  /** The link is down and the hung clock already runs for it (repeated "down" reports leave it alone). */
  let down = false
  const stop = (): void => {
    clearTimeout(hung)
    hung = undefined
  }
  const arm = (): void => {
    stop()
    if (asleep) return
    hung = setTimeout(check, hungMs)
    hung.unref?.()
  }
  function check(): void {
    hung = undefined
    if (io.connected() || asleep) return
    // Not ours (Terminal, another build) or not running yet: look again later, never restart it.
    if (!io.ownEngineAlive()) return arm()
    if (budget.next() === undefined) {
      spent = true
      return error('[recover] engine alive but not answering, and the restart budget is spent')
    }
    warn(`[recover] engine alive but not answering for ${Math.round(hungMs / 1000)} s; restarting it`)
    io.restart()
    arm()
  }
  io.onStatus((up) => {
    if (!up && down) return
    down = !up
    if (up) {
      stop()
      if (spent) {
        budget.reset()
        spent = false
      }
      return
    }
    arm()
  })
  return {
    suspend() {
      asleep = true
      stop()
    },
    resume() {
      asleep = false
      down = !io.connected()
      if (down) arm()
      else stop()
    }
  }
}

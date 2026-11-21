/**
 * Dead-socket detection for the engine link (main/engine.ts). A laptop that sleeps, a Wi-Fi change or a hung engine
 * leaves a TCP connection half open: no 'close' ever arrives, so the pill looked connected while nothing came back.
 * The `ws` library answers a protocol ping with a pong by itself, so this needs no engine change.
 *
 *   every PING_MS  : no sign of life (pong or any message) for DEAD_MS -> dead(); otherwise ping()
 *   a late tick    : the timer itself fired SLEPT_TICKS beats late, so the Mac slept (timers froze), not the engine.
 *                    Silence across a sleep says nothing: probe() instead of dead(), so a healthy socket is kept.
 *   probe(ms)      : ping now (after a wake, a network change); dead() unless something answers within `ms`
 *   alive()        : call on every pong and every message
 */
export const PING_MS = 5000
/** An engine busy with OCR, a model call or a lesson build can leave its event loop blocked for many seconds; a late pong is not a dead socket. */
export const DEAD_MS = 30_000
/** Wake / network change only: a healthy engine answers at once, but a busy one may need a few seconds. A miss redials (the held reset keeps the same lesson on screen). */
export const PROBE_MS = 8000
/** A tick this many beats late means the machine slept (see the header). */
export const SLEPT_TICKS = 3

export type HeartbeatIo = { ping(): void; dead(): void }

export class Heartbeat {
  private seen: number
  private lastTick: number
  private answered = true
  private timer?: ReturnType<typeof setInterval>
  private probeTimer?: ReturnType<typeof setTimeout>
  constructor(
    private io: HeartbeatIo,
    private pingMs = PING_MS,
    private deadMs = DEAD_MS,
    private probeMs = PROBE_MS,
    private now: () => number = Date.now
  ) {
    this.seen = this.lastTick = now()
  }

  start(): void {
    this.stop()
    this.seen = this.lastTick = this.now()
    this.timer = setInterval(() => this.tick(), this.pingMs)
    this.timer.unref?.()
  }

  stop(): void {
    clearInterval(this.timer)
    clearTimeout(this.probeTimer)
    this.timer = this.probeTimer = undefined
  }

  alive(): void {
    this.answered = true
    this.seen = this.now()
  }

  probe(ms = this.probeMs): void {
    if (!this.timer) return
    this.answered = false
    this.io.ping()
    clearTimeout(this.probeTimer)
    this.probeTimer = setTimeout(() => {
      if (!this.answered) this.fail()
    }, ms)
    this.probeTimer.unref?.()
  }

  /** One beat (the interval; exposed for tests that drive a fake clock). */
  tick(): void {
    const now = this.now()
    const slept = now - this.lastTick > this.pingMs * SLEPT_TICKS
    this.lastTick = now
    if (slept) {
      this.seen = now
      return this.probe()
    }
    if (now - this.seen > this.deadMs) return this.fail()
    this.io.ping()
  }

  private fail(): void {
    this.stop()
    this.io.dead()
  }
}

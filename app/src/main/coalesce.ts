/**
 * Trailing coalescer: many calls inside `ms` become one run with the last value. Used where a burst of identical
 * work (window move/resize events, the renderer's overlay.bounds samples) used to hit the engine socket every time.
 */
export function coalesce<T>(fn: (v: T) => void, ms: number): { push(v: T): void; flush(): void; stats: { pushed: number; ran: number } } {
  let timer: ReturnType<typeof setTimeout> | undefined
  let last: T
  const stats = { pushed: 0, ran: 0 }
  const run = (): void => {
    timer = undefined
    stats.ran++
    fn(last)
  }
  return {
    stats,
    push(v: T) {
      last = v
      stats.pushed++
      if (!timer) timer = setTimeout(run, ms)
    },
    flush() {
      if (!timer) return
      clearTimeout(timer)
      run()
    }
  }
}

/**
 * Tiny counters for "is this chatty?" questions. `perf.count('bounds.sampled')` costs one add; read them in the stage
 * console with `__miyagiPerf()` (or add `?perf=1` to the URL to mirror them into <html data-perf> every second). No timers run without ?perf=1.
 */
const counts: Record<string, number> = {}
export const perf = {
  count(name: string, n = 1): void {
    counts[name] = (counts[name] ?? 0) + n
  },
  snapshot(): Record<string, number> {
    return { ...counts }
  }
}
if (typeof window !== 'undefined') {
  ;(window as unknown as { __miyagiPerf: () => Record<string, number> }).__miyagiPerf = perf.snapshot
  if (/[?&]perf=1/.test(location.search)) setInterval(() => (document.documentElement.dataset.perf = JSON.stringify(counts)), 1000)
}

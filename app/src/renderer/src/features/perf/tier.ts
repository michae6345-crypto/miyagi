/**
 * Low-power tier (Nov 25, MacBook Neo / 8 GB Macs: "the app is slow and laggy"). Pure, shared by main
 * (main/features/perf.ts reads the machine) and the renderer (features/perf/index.tsx sets <html data-low-power>).
 *
 * Low when the Mac has <= 8 GB of RAM, <= 6 cores (A-series: 2 performance + 4 efficiency) or Low Power Mode is on.
 * Battery alone is NOT low (the look would flip every time a charger is unplugged). MIYAGI_PERF_TIER=low|normal forces
 * it, here and in the engine (server/screen/perf_tier.py, which counts performance cores: <= 2).
 *
 * What low turns off (perf.css): decorative endless loops (the buddy's float / blink / sway, the bonsai's sway),
 * backdrop-filter glass and blur-in filters. Spinners and thinking dots stay: a frozen indicator reads as a hang.
 */
export type PerfTier = 'low' | 'normal'
export type PerfState = { tier: PerfTier; reason: string }
export type PerfInput = { memBytes?: number; cores?: number; lowPowerMode?: boolean; override?: string }

const GB = 1024 ** 3
/** <= 8 GB (+ slack: os.totalmem() of an 8 GB Mac is exactly 8 GiB). */
export const LOW_MEM_BYTES = 8 * GB + 256 * 1024 ** 2
export const LOW_CORES = 6

export function perfTier(i: PerfInput): PerfState {
  const o = (i.override ?? '').trim().toLowerCase()
  if (o === 'low' || o === 'normal') return { tier: o, reason: `MIYAGI_PERF_TIER=${o}` }
  const why: string[] = []
  if (i.memBytes && i.memBytes <= LOW_MEM_BYTES) why.push(`${Math.round((i.memBytes / GB) * 10) / 10} GB RAM`)
  if (i.cores && i.cores <= LOW_CORES) why.push(`${i.cores} cores`)
  if (i.lowPowerMode) why.push('Low Power Mode')
  return why.length ? { tier: 'low', reason: why.join(', ') } : { tier: 'normal', reason: '' }
}

export const NORMAL: PerfState = { tier: 'normal', reason: '' }

/** The <html> attribute the renderer sets: present = low tier. */
export function applyTier(root: { dataset: Record<string, string | undefined> }, s: PerfState): void {
  if (s.tier === 'low') root.dataset.lowPower = s.reason || 'on'
  else delete root.dataset.lowPower
}

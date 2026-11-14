import type { Scenario } from '../engine'

/**
 * Every mock/scenarios/*.json is a scenario, named after its file.
 * "full" = all of them merged (happy, offtrack, then the rest A→Z), so a feature agent adds its own
 * triggers/segments by dropping in <feature>.json, without editing the shared files.
 */
export function buildScenarios(files: Record<string, Scenario>): Record<string, Scenario> {
  const first = ['happy', 'offtrack']
  const rank = (n: string): number => (first.includes(n) ? first.indexOf(n) : first.length)
  const names = Object.keys(files).sort((a, b) => rank(a) - rank(b) || a.localeCompare(b))
  const full: Scenario = { name: 'full', on: {}, segments: {} }
  for (const n of names) {
    Object.assign(full.on, files[n].on)
    Object.assign(full.segments, files[n].segments)
  }
  full.on.connect = '' // the full demo starts idle: drive it from the launcher
  return { ...files, full }
}

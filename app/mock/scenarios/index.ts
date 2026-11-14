/** Scenarios for Vite contexts (renderer inline mock, Electron main DEMO=1). replay.ts reads the folder with fs. */
import type { Scenario } from '../engine'
import { buildScenarios } from './build'

const files = import.meta.glob<Scenario>('./*.json', { eager: true, import: 'default' })

export const scenarios: Record<string, Scenario> = buildScenarios(
  Object.fromEntries(Object.entries(files).map(([path, s]) => [path.replace(/^.*\/([^/]+)\.json$/, '$1'), s]))
)

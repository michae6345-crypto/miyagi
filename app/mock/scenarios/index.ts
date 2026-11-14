import type { Scenario } from '../engine'
import happyJson from './happy.json'
import offtrackJson from './offtrack.json'

const happy = happyJson as unknown as Scenario
const offtrack = offtrackJson as unknown as Scenario

/** happy path, then straight into the off-track hero moment at step 6. */
const full: Scenario = {
  name: 'full',
  on: { ...offtrack.on, ...happy.on, connect: '' },
  segments: { ...happy.segments, ...offtrack.segments }
}

export const scenarios = { happy, offtrack, full } satisfies Record<string, Scenario>
export type ScenarioName = keyof typeof scenarios

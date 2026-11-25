/**
 * Test stand-in for mock/scenarios/index.ts, which uses Vite's import.meta.glob (plain node can't run it). main/engine.ts
 * needs the scenarios only in DEMO, so the tests get an empty map.
 */
import type { Scenario } from '../../mock/engine'

export const scenarios: Record<string, Scenario> = {}

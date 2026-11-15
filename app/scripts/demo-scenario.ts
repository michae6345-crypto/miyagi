/**
 * Writes mock/scenarios/demo.json (the offline "neural net from scratch" demo) from
 * src/renderer/src/features/demo/lesson.ts. Run after editing the lesson:  npx tsx scripts/demo-scenario.ts
 */
import { writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { buildDemoScenario } from '../src/renderer/src/features/demo/scenario'

const out = fileURLToPath(new URL('../mock/scenarios/demo.json', import.meta.url))
const scenario = buildDemoScenario()
writeFileSync(out, JSON.stringify(scenario, null, 2) + '\n')
console.log(`wrote ${out}: ${Object.keys(scenario.on).length} triggers, ${Object.keys(scenario.segments).length} segments`)

// Test-only loader: mock/scenarios/index.ts uses Vite's import.meta.glob, which plain node can't run. The engine link
// needs the scenarios only in DEMO, so the tests get an empty map.
// Usage (from app/): node --import tsx --import ./tests/stub-scenarios.mjs --test tests/*.test.ts
import { register } from 'node:module'

register(
  'data:text/javascript,' +
    encodeURIComponent(`
export async function load(url, context, next) {
  if (/\\/mock\\/scenarios\\/index\\.ts$/.test(url)) return { format: 'module', source: 'export const scenarios = {}', shortCircuit: true }
  return next(url, context)
}`),
  import.meta.url
)

// Offline unit tests for main-process features: `electron`, main/publicConfig.ts and mock/scenarios resolve to fakes in test/fakes/.
// Run from app/: npm test (node --import tsx --import ./test/setup.mjs --test --test-force-exit --test-timeout=60000 test/*.test.ts).
// --test-timeout is optional but recommended: with it no single test can block the run forever, whatever holds a port it needs.
// Synchronous hooks (Node 22.15+), so they also catch require() (tsx loads these .ts files as CommonJS).
import { registerHooks } from 'node:module'

const fakes = new URL('./fakes/', import.meta.url)

registerHooks({
  resolve(specifier, context, next) {
    if (specifier === 'electron') return { url: new URL('electron.ts', fakes).href, shortCircuit: true }
    // main/publicConfig.ts reads import.meta.env (Vite only); the fake points at a made-up https project.
    if (/(^|\/)publicConfig(\.ts)?$/.test(specifier) && context.parentURL?.includes('/src/main/')) {
      return { url: new URL('publicConfig.ts', fakes).href, shortCircuit: true }
    }
    // mock/scenarios/index.ts uses import.meta.glob (Vite only); main/engine.ts needs it only in DEMO: an empty map.
    if (/(^|\/)mock\/scenarios(\/index)?(\.ts)?$/.test(specifier) && context.parentURL?.includes('/src/main/')) {
      return { url: new URL('scenarios.ts', fakes).href, shortCircuit: true }
    }
    return next(specifier, context)
  }
})

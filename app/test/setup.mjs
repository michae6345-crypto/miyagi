// Offline unit tests for main-process features: `electron` and main/publicConfig.ts resolve to fakes in test/fakes/.
// Run from app/: node --import tsx --import ./test/setup.mjs --test --test-force-exit test/*.test.ts
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
    return next(specifier, context)
  }
})

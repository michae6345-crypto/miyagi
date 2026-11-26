/**
 * The browser stage's mock data, in one module that only a dev build loads (bridge.ts, through a dynamic import behind
 * import.meta.env.DEV). `npm run build` drops the import, so the packaged app carries no mock engine, no scenarios and
 * no fixture learner (test/stageBundle.test.ts holds the source to that; `grep "Sam Rivera" out/renderer` finds nothing).
 *
 *   createMockEngine, scenarios   the inline mock engine (bridge.ts startInline)
 *   auth, account, circle web.ts  the stand-ins that carry fixture people or scenario words; they register their
 *                                 handlers on import (bridge.invoke waits for this module before it looks one up)
 */
export { createMockEngine } from '../../../../mock/engine'
export { scenarios } from '../../../../mock/scenarios'
import '../features/auth/web'
import '../features/account/web'
import '../features/circle/web'

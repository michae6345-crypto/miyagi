/**
 * The pill's view of the engine socket (Michael's review A16): whether an attempt has actually failed, so the pill
 * never says "Can't reach miyagi" while the first attempt is still in flight, and a Retry that connects now.
 *
 *   bridge.invoke('engine-link:retry')  try now + fast retries again (the pill's Retry, and every window on load:
 *                                       "connect as soon as the renderer loads"); returns the LinkInfo
 *   bridge.onFeature('engine-link')     every change of the LinkInfo ({open, attempting, failures})
 *
 * The browser stage stands in for both in bridge.ts. UNVERIFIED in Electron (typechecked on Windows).
 */
import { defineMainFeature } from '../context'

export default defineMainFeature({
  id: 'pill',
  setup(ctx) {
    ctx.handle('engine-link:retry', () => {
      ctx.engine.reconnect()
      return ctx.engine.link()
    })
    ctx.engine.onLink((l) => ctx.broadcast('engine-link', l))
  }
})

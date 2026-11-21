/**
 * Browser stage stand-ins for main/features/progress.ts. The stage is one window, so the capabilities are this
 * window's own engine.hello (core/lesson canSend) and the last answer is this window's store.
 */
import { isElectron, registerWebHandler } from '../../bridge'
import { canSend } from '../../core/lesson'
import { useProgress } from './store'

if (!isElectron) {
  registerWebHandler('progress:caps', () => ({ progress: canSend('progress.get'), review: canSend('review.start'), library: canSend('library.start') }))
  registerWebHandler('progress:last', () => useProgress.getState().data ?? null)
}

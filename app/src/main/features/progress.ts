/**
 * Main-process side of Progress (renderer: src/renderer/src/features/progress/). No window code here: the Progress
 * window is an app window (main/appWindows.ts, route `progress`, opened with core/surfaces openProgress()).
 *
 * Why main: the renderer of an app window that opens mid-lesson never saw this connection's engine.hello (the replay
 * log keeps only search rows after lesson.ready), so it can't tell on its own whether the engine answers progress.get.
 * Main's EngineLink knows (and drops a v2 command the engine didn't list, whatever a renderer sends).
 *
 * Handles (bridge.invoke from any window):
 *   progress:caps   → { progress, review, library }: does the engine take progress.get / review.start / library.start?
 *   progress:last   → the last `progress` payload this connection saw (or null), so the window paints at once
 * Nothing here talks to the network, opens a URL or touches a file.
 */
import { defineMainFeature } from '../context'

export default defineMainFeature({
  id: 'progress',
  setup(ctx) {
    let last: unknown = null
    ctx.engine.onEvent((e) => {
      if (e.type === 'progress') last = e.payload
    })
    // A new connection may be another engine (or the same one restarted): what the old one said no longer holds.
    ctx.engine.onStatus((connected) => {
      if (!connected) last = null
    })
    ctx.handle('progress:caps', () => ({
      progress: ctx.engine.can('progress.get'),
      review: ctx.engine.can('review.start'),
      library: ctx.engine.can('library.start')
    }))
    ctx.handle('progress:last', () => last)
  }
})

/**
 * Skills "around the tree" (mockup skills-07-extras): the one SkillGraph the extras read, kept from every `progress`
 * the engine sends (features/skills/model.ts buildSkillGraph, either wire shape). The dashboard store keeps only
 * DashData, which drops `progress.graph`, so this store keeps the view model itself.
 *
 *   ensureSkillGraph()   a page that shows chips or the week: paint what main last saw, then ask once (requestProgress
 *                        does the capability check)
 *   refreshSkillGraph()  the lesson-end recap: the lesson just changed what is mastered, so ask again
 */
import { create } from 'zustand'
import { cmd } from '../../../../../common/wire'
import { bridge } from '../../../bridge'
import { onMessage } from '../../../core/bus'
import { canSend } from '../../../core/lesson'
import { stageRebase } from '../../dashboard/stage'
import { requestProgress } from '../../progress/store'
import { buildSkillGraph, type SkillGraph } from '../model'

/**
 * `at`: when the engine last sent a `progress` (ms, this window's clock); 0 until it has. Main's cached copy
 * (progress:last) paints the graph but leaves `at` alone: it can be from before the lesson ended, so the lesson-end
 * recap never counts it as fresh.
 */
type State = { graph?: SkillGraph; at: number }
export const useSkillGraph = create<State>(() => ({ graph: undefined, at: 0 }))
const get = useSkillGraph.getState

function take(raw: unknown, fresh: boolean): void {
  const graph = buildSkillGraph(stageRebase(raw))
  if (graph) useSkillGraph.setState(fresh ? { graph, at: Date.now() } : { graph })
}
onMessage('progress', (raw) => take(raw, true))

async function fromMain(): Promise<void> {
  if (get().graph) return
  const last = await bridge.invoke<unknown>('progress:last').catch(() => undefined)
  if (last && !get().graph) take(last, false)
}

let asked = false
/** Once per window: main's last answer at once, then progress.get when the engine lists it. */
export function ensureSkillGraph(): void {
  if (asked) return
  asked = true
  void fromMain().then(() => {
    if (!get().graph) void requestProgress()
  })
}

// A page asked before this connection's engine.hello (no capabilities yet, so nothing was sent): ask again now.
onMessage('engine.hello', () => {
  if (asked && !get().graph) void requestProgress()
})

/** The lesson just ended: ask for the graph again (zero model calls), only when the engine lists progress.get. */
export function refreshSkillGraph(): void {
  void fromMain()
  if (canSend('progress.get')) bridge.send(cmd('progress.get', {}))
}

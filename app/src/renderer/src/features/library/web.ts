/**
 * Feature: library. Browser-stage stand-in for src/main/features/library.ts (does nothing in Electron).
 *
 * Same channels, same rules: v2 commands only to an engine that lists them in engine.hello, answers cleaned by
 * sanitize.ts, nothing ever sends `learn`. The inline mock counts as capable, like main's DEMO link (main/engine.ts
 * lets every v2 command through to the mock): its default hello is not always seen by the renderer (Core requests). When the scenario has no library trigger (e.g. ?scenario=home), the stage
 * serves STAGE_ITEMS below so the window has something to show; these never exist in Electron, where a missing answer
 * is [] (an empty library). Stage extras: ?library=empty forces the empty state, ?library=nocaps hides the engine's
 * library capabilities (Start disabled).
 */
import { cmd, type Incoming } from '../../../../common/wire'
import type { LibraryItem } from '../../../../../../shared/contracts/events'
import { bridge, engineMode, isElectron, registerWebHandler } from '../../bridge'
import { onMessage } from '../../core/bus'
import { canSend } from '../../core/lesson'
import { cleanDetail, cleanList, isLibraryId, type LibraryDetail } from './sanitize'

const STAGE_ITEMS: LibraryItem[] = [
  { id: 'stage_mnist', title: 'Code your first neural network with TensorFlow', by: '[CREATOR NAME]', steps: 7, estMinutes: 25, tools: ['jupyter', 'vscode'], ready: true, progress: { stepIndex: 3, stepTitle: 'Train it', total: 7 } },
  { id: 'stage_pandas', title: 'Clean a CSV with pandas', by: '[CREATOR NAME]', steps: 6, estMinutes: 20, tools: ['jupyter'], ready: true, progress: { stepIndex: 2, stepTitle: 'Drop the empty rows', total: 6 } },
  { id: 'stage_venv', title: 'Set up Python with a virtual environment', by: '[ORG NAME]', steps: 5, estMinutes: 10, tools: ['terminal', 'vscode'], ready: true },
  { id: 'stage_plot', title: 'Plot your data with matplotlib', by: '[CREATOR NAME]', steps: 6, estMinutes: 15, tools: ['jupyter'], ready: true },
  { id: 'stage_func', title: 'Write your first Python function', by: '[CREATOR NAME]', steps: 4, estMinutes: 10, tools: ['vscode'], ready: true },
  // The one stage lesson from a video: the demo video, under its own title (it used to sit on the TensorFlow lesson,
  // so that preview showed another video's thumbnail).
  { id: 'stage_video', title: 'Learning PIML Part 1: PINNs', by: '[CREATOR NAME]', steps: 7, estMinutes: 30, tools: ['jupyter'], ready: true, source: { kind: 'youtube', title: 'Learning PIML Part 1: PINNs', channel: '[CREATOR NAME]', durationS: 1420, url: 'https://www.youtube.com/watch?v=AXXnSzmpyoI' } }
]
const STAGE_STEPS: [string, string][] = [
  ['Open the project', 'Start in the folder you will work in'],
  ['Set things up', 'Install what the lesson needs'],
  ['Write the first part', 'Type the opening lines'],
  ['Run it', 'See it work once'],
  ['Read the output', 'Match each line to its code'],
  ['Change one thing', 'Edit a value and run it again'],
  ['Try it on new input', 'Feed it something fresh']
]

function stageDetail(id: string): LibraryDetail | undefined {
  const item = STAGE_ITEMS.find((i) => i.id === id)
  if (!item) return undefined
  return {
    item,
    // Only a lesson built from a video talks about the video.
    overview: item.source?.kind === 'youtube' ? 'Follow the video one step at a time. miyagi checks each step you run.' : 'One step at a time. miyagi checks each step you run.',
    steps: STAGE_STEPS.slice(0, item.steps).map(([title, what], index) => ({ index, title, what, estMinutes: 3 }))
  }
}

/** Send a command to the inline mock and wait for the first matching answer (undefined after `ms`). */
function ask<T>(send: () => void, type: Incoming['type'], match: (payload: unknown) => T | undefined, ms = 1500): Promise<T | undefined> {
  return new Promise((resolve) => {
    let off = (): void => undefined
    const timer = setTimeout(() => {
      off()
      resolve(undefined)
    }, ms)
    off = onMessage(type, (p) => {
      const v = match(p)
      if (v === undefined) return
      clearTimeout(timer)
      off()
      resolve(v)
    })
    send()
  })
}

function setupWeb(): void {
  const mode = new URLSearchParams(location.search).get('library')
  const can = (t: string): boolean => mode !== 'nocaps' && (canSend(t) || engineMode() === 'inline')

  registerWebHandler('library:caps', () => ({ list: can('library.list'), get: can('library.get'), start: can('library.start') }))

  registerWebHandler('library:list', async () => {
    if (mode === 'empty') return []
    if (can('library.list')) {
      const items = await ask(() => bridge.send(cmd('library.list', {})), 'library', (p) => cleanList(p))
      if (items) return items
    }
    return STAGE_ITEMS
  })

  registerWebHandler('library:get', async (id) => {
    if (!isLibraryId(id)) return null
    if (can('library.get')) {
      const d = await ask(() => bridge.send(cmd('library.get', { id })), 'library.item', (p) => cleanDetail(p, id))
      if (d) return d
    }
    return stageDetail(id) ?? null
  })

  registerWebHandler('library:start', (id) => {
    if (!isLibraryId(id) || !can('library.start')) return false
    bridge.send(cmd('library.start', { id }))
    return true
  })
}

if (!isElectron) setupWeb()

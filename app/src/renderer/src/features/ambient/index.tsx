/**
 * Feature: ambient (help outside a lesson, in any app; shared/contracts/AMBIENT-HELP.md, brief app/agents/app-ambient.md).
 *
 * Island modes (the notch island; README priority table):
 *   ambient-chip     22  pill-sized: "Error in Terminal · Explain". Above the notch hover home (21), so the pointer can
 *                        reach Explain without the home panel taking the island; below every card (40+).
 *   ambient-help     23  pill-sized: the how-do-I step line while bon points at each step's control.
 *   ambient-explain  46  card: the explanation, the fix, Copy fix, Show me.
 *   ambient-setup    47  card: "Set up this project" rows with Fix.
 * In the notch the two lines drop under the notch row ('drop'); below the menu bar they are the pill. None of them
 * shows while a lesson is loaded, building or on a step: the lesson's own cards cover errors and setup there.
 *
 * Elsewhere: the Settings rows (Settings.tsx, Settings > General), and the launcher's two commands (commands.ts).
 */
import { useLesson } from '../../core/lesson'
import { defineFeature } from '../../core/registry'
import { EXPLAIN_W, ExplainCard, SETUP_W, SetupCard } from './Cards'
import { ErrorChip, HelpLine } from './Lines'
import { useAmbient } from './store'
import './prefs'

/** No lesson on screen (loaded, building or on a step). */
const useNoLesson = (): boolean => useLesson((s) => !s.lesson && !s.building && !s.stepId)

export default defineFeature({
  id: 'ambient',
  islandModes: [
    {
      id: 'ambient-setup',
      priority: 47,
      width: SETUP_W,
      useActive: () => {
        const open = useAmbient((s) => s.setupOpen && !!s.report)
        return useNoLesson() && open
      },
      Content: SetupCard
    },
    {
      id: 'ambient-explain',
      priority: 46,
      width: EXPLAIN_W,
      useActive: () => {
        const open = useAmbient((s) => s.explainOpen && !!s.error)
        return useNoLesson() && open
      },
      Content: ExplainCard
    },
    {
      id: 'ambient-help',
      priority: 23,
      useActive: () => {
        const open = useAmbient((s) => s.helpOpen && !!s.help)
        return useNoLesson() && open
      },
      Content: HelpLine,
      notch: { useView: () => 'drop' }
    },
    {
      id: 'ambient-chip',
      priority: 22,
      useActive: () => {
        const on = useAmbient((s) => s.chip && !!s.error)
        const connected = useLesson((s) => s.connected)
        return useNoLesson() && on && connected
      },
      Content: ErrorChip,
      notch: { useView: () => 'drop' }
    }
  ]
})

export { AmbientSettings } from './Settings'
export { ambientCommand, runAmbientCommand, type AmbientCommand } from './commands'

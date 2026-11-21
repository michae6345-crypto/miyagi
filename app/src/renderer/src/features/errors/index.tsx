/**
 * Feature: errors (BUILD-PLAN A7). Every stall said calmly from the island; priorities from agents/README.md:
 *
 *   90 err-crash           crash consent, at launch only (never with a lesson on screen)
 *   72 err-engine-offline  after 5 tries (a UI threshold; main keeps retrying)
 *   66 err-editor-closed   VS Code closed: "Your place is saved." (Esc folds it into the blocker line)
 *   62 err-build-failed    the build stopped: transcript only, or a cached library lesson
 *   58 err-limit           free checks used up (v2Cloud only: off in Electron, ?v2Cloud=1 in the stage)
 *    7 err-reconnecting    "Reconnecting… (try N)", then "Back."
 *    7 err-blocker         VS Code closed / opening / back in place, no kernel
 *    6 err-net-offline     offline, then "Online."
 *    6 err-busy            the AI provider is busy, retrying in N s
 */
import { isElectron } from '../../bridge'
import { useLesson } from '../../core/lesson'
import { defineFeature } from '../../core/registry'
import { pill } from '../../core/theme'
import { BuildFailedCard, CrashCard, EditorClosedCard, EngineOfflineCard, LimitCard } from './cards'
import { BlockerLine, BusyLine, OfflineLine, ReconnectLine } from './lines'
import { engineOffline, reconnectTry, useErrors, useNetOffline } from './store'

/** v2Cloud is off this push (BUILD-PLAN section 1): the limit card only shows in the stage with ?v2Cloud=1. */
const V2_CLOUD = !isElectron && typeof location !== 'undefined' && new URLSearchParams(location.search).get('v2Cloud') === '1'

const useEditorClosed = (): boolean => useLesson((s) => !!s.blockers.editor_closed || s.paused?.reason === 'editor_closed')

export default defineFeature({
  id: 'errors',
  islandModes: [
    {
      id: 'err-crash',
      priority: 90,
      width: 440,
      useActive: () => {
        const crash = useErrors((s) => !!s.crash)
        const quiet = useLesson((s) => !s.lesson && !s.building)
        return crash && quiet
      },
      Content: CrashCard
    },
    { id: 'err-engine-offline', priority: 72, width: 296, useActive: () => useErrors(engineOffline), Content: EngineOfflineCard },
    {
      id: 'err-editor-closed',
      priority: 66,
      width: 352,
      useActive: () => {
        const closed = useEditorClosed()
        const folded = useErrors((s) => s.editorDismissed || s.reopening)
        return closed && !folded
      },
      Content: EditorClosedCard
    },
    {
      id: 'err-build-failed',
      priority: 62,
      width: pill.maxCardWidth,
      useActive: () => {
        const dismissedAt = useErrors((s) => s.buildDismissedAt)
        return useLesson((s) => !!s.buildFailed && !s.buildFailed.silent && s.buildFailed.at !== dismissedAt && !s.building && !s.stepId)
      },
      Content: BuildFailedCard
    },
    {
      id: 'err-limit',
      priority: 58,
      width: 336,
      useActive: () => {
        const quota = useLesson((s) => s.keyStatus?.cloud === 'quota')
        const dismissed = useErrors((s) => s.limitDismissed)
        return V2_CLOUD && quota && !dismissed
      },
      Content: LimitCard
    },
    // Pill lines. Same priority: the first listed wins (the registry's sort is stable).
    { id: 'err-reconnecting', priority: 7, useActive: () => useErrors((s) => reconnectTry(s) !== undefined || s.flash?.id === 'back'), Content: ReconnectLine },
    {
      id: 'err-blocker',
      priority: 7,
      useActive: () => {
        const closed = useEditorClosed()
        const kernel = useLesson((s) => !!s.blockers.kernel)
        const inPlace = useErrors((s) => s.flash?.id === 'in-place')
        return closed || kernel || inPlace
      },
      Content: BlockerLine
    },
    {
      id: 'err-net-offline',
      priority: 6,
      useActive: () => {
        const offline = useNetOffline()
        const online = useErrors((s) => s.flash?.id === 'online')
        return offline || online
      },
      Content: OfflineLine
    },
    { id: 'err-busy', priority: 6, useActive: () => useLesson((s) => !!s.busy), Content: BusyLine }
  ]
})

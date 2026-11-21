/**
 * Feature: errors. The pill lines (pill-sized island modes, no card, no sound):
 *
 *   err-reconnecting (7)  "Reconnecting to engine  2 of 5", then "Back. Picking up where you were."   Err-EngineReconnect
 *   err-blocker (7)       "VS Code closed. Lesson paused.  Step 3 of 6", "Opening VS Code", "Back on Build the model",
 *                         "Pick a kernel so your cells can run  [Select Kernel ▷]"                  Err-VSCodeClosed, Err-KernelInContext
 *   err-net-offline (6)   "Offline. Steps work, checks wait.", then "Online. Checking your work now." Err-OfflineAndLimits
 *   err-busy (6)          "Busy right now. Retrying in  20s"                                         Err-OfflineAndLimits
 */
import { useEffect, useState, type ReactNode } from 'react'
import { copy } from '../../core/theme'
import { useCurrentStep, useLesson } from '../../core/lesson'
import { PillLine } from './parts'
import { reconnectTry, TRIES, useErrors, useNetOffline } from './store'

/** Engine copy goes through the editor-name guard: a line naming an unsupported editor falls back to ours. */
export function guard(text: string | undefined, fallback: string): string {
  const t = (text ?? '').trim()
  return !t || copy.editorName(t) !== t ? fallback : t
}

export function ReconnectLine(): ReactNode {
  const n = useErrors(reconnectTry)
  const back = useErrors((s) => (s.flash?.id === 'back' ? s.flash.text : undefined))
  if (n) return <PillLine id="reconnecting" glyph="arc" text="Reconnecting to engine" mono={`${n} of ${TRIES}`} />
  return <PillLine id="back" glyph="tick" text={back ?? 'Back. Picking up where you were.'} />
}

export function BlockerLine(): ReactNode {
  const editor = useLesson((s) => s.blockers.editor_closed)
  const pausedEditor = useLesson((s) => (s.paused?.reason === 'editor_closed' ? s.paused : undefined))
  const kernel = useLesson((s) => s.blockers.kernel)
  const reopening = useErrors((s) => s.reopening)
  const inPlace = useErrors((s) => (s.flash?.id === 'in-place' ? s.flash.text : undefined))
  const step = useCurrentStep()
  const name = copy.editorName()
  const count = step.index >= 0 && step.total > 0 ? `Step ${step.index + 1} of ${step.total}` : undefined
  if (editor || pausedEditor) {
    if (reopening) return <PillLine id="reopening" glyph="arc" text={`Opening ${name}`} />
    return <PillLine id="editor-closed" glyph="ring" text={guard(editor?.title, `${name} closed. Lesson paused.`)} mono={count} />
  }
  if (kernel) {
    const action = guard(kernel.action, '')
    return <PillLine id="kernel" glyph="ring" text={guard(kernel.title, 'Pick a kernel so your cells can run')} chip={action ? `${action} ▷` : undefined} />
  }
  return <PillLine id="in-place" glyph="tick" text={inPlace ?? 'Back in place'} />
}

export function OfflineLine(): ReactNode {
  const offline = useNetOffline()
  const inLesson = useLesson((s) => !!s.stepId)
  const online = useErrors((s) => (s.flash?.id === 'online' ? s.flash.text : undefined))
  if (offline) return <PillLine id="offline" glyph="wifi-off" text={inLesson ? 'Offline. Steps work, checks wait.' : 'Offline. Lessons need a connection to build.'} />
  return <PillLine id="online" glyph="wifi" text={online ?? 'Online again.'} />
}

export function BusyLine(): ReactNode {
  const busy = useLesson((s) => s.busy)
  const counting = busy?.retryInS !== undefined
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!counting) return
    setNow(Date.now())
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [counting, busy?.at])
  const left = busy?.retryInS !== undefined ? Math.max(0, Math.ceil(busy.retryInS - (now - busy.at) / 1000)) : undefined
  if (left === undefined || left === 0) return <PillLine id="busy" glyph="arc" text="Busy right now. Retrying" />
  return <PillLine id="busy" glyph="arc" text="Busy right now. Retrying in" mono={`${left}s`} monoHidden />
}

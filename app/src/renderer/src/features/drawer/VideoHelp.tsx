/**
 * Feature: drawer. The video lesson's help row, at the foot of the steps drawer (it replaces the bottom shortcut bar).
 *
 * Row 1: Explain, Diagram, Show me, Hint, the pastel options (BRAND.md mapping through core OptionButton), each with
 * its keycap from bridge.platform.keys, sent through triggerShortcut like the keys and the "Just teach me" panel's
 * Help row (drawer/v2/Help.tsx). Row 2: neutral chrome, Back (previous step) and Skip step. No Check my work here:
 * the player's "Check my work" is the surface's only one (MIC-61).
 * End lesson and "ask miyagi" are in the launcher (the notch island, the launcher key).
 *
 * Never looks dead: the pressed option's icon turns into the Spinner from the press itself (v2/Help.tsx useWaitingOn,
 * as the "Just teach me" panel's tiles; QA Q23: before, it waited for the engine's "thinking", so a press showed
 * nothing at all until the answer), until the answer or ANSWER_MS of silence. Hidden under the lesson-complete panel,
 * which has its own End lesson.
 */
import { ArrowLeft, SkipForward } from 'lucide-react'
import type { ReactNode } from 'react'
import { bridge } from '../../bridge'
import { useKeys } from '../../core/keys'
import { useLesson, useThinking } from '../../core/lesson'
import { sendAction, triggerShortcut, usePressed, type ActionShortcut } from '../../core/shortcuts'
import { glass, type OptionAction } from '../../core/theme'
import { OptionButton } from '../../core/ui/atoms'
import { GlassQuiet } from '../../core/ui/glass'
import { useComplete } from '../complete/store'
import { guardSkip, skipLabel, useSkipArmed } from '../settings/guard'
import { useWaitingOn } from './v2/Help'

type Option = Extract<ActionShortcut, OptionAction>
const OPTIONS: ReadonlyArray<{ kind: Option; label: string }> = [
  { kind: 'explain', label: 'Explain' },
  { kind: 'diagram', label: 'Diagram' },
  { kind: 'show_me', label: 'Show me' },
  { kind: 'hint', label: 'Hint' }
]

/** The row shows for a video lesson with a step on, never over the completion panel. */
export function useVideoHelp(): boolean {
  const video = useLesson((s) => !!s.lesson && s.lesson.mode !== 'lesson' && !!s.stepId)
  const completing = useComplete((c) => !!c.card)
  return video && !completing
}

export function VideoHelp(): ReactNode {
  const thinking = useThinking()
  const pressed = usePressed((p) => p.kind)
  // The one caller here (the v2 panel, its other caller, never shows with this row): its timer notifies.
  const waiting = useWaitingOn()
  const keys = useKeys() // live: a rebound shortcut shows its own key
  const skipping = thinking && pressed === 'skip_step'
  useSkipArmed()
  return (
    <div data-part="drawer-video-help" className="flex shrink-0 flex-col gap-[8px] border-t px-[14px] pb-[12px] pt-[10px]" style={{ borderColor: glass.rule }}>
      <div role="group" aria-label="Need help" className="flex flex-wrap gap-[6px]">
        {OPTIONS.map(({ kind, label }) => (
          <OptionButton
            key={kind}
            action={kind}
            label={label}
            kbd={keys[kind]}
            busy={waiting === kind}
            onClick={() => triggerShortcut(kind)}
          />
        ))}
      </div>
      <div className="flex flex-wrap gap-[6px]">
        <GlassQuiet label="Back" icon={ArrowLeft} onClick={() => triggerShortcut('back')} />
        <GlassQuiet label={skipLabel('Skip step')} icon={SkipForward} busy={skipping} onClick={() => guardSkip() && sendAction('skip_step')} />
      </div>
    </div>
  )
}

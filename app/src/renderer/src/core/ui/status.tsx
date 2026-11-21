/**
 * Core (v2, W0-3): status glyphs and words, the same everywhere (lesson panel, Mini pill, onboarding rows, progress).
 *
 *   passed    a filled green circle with an ink tick. The ONLY green.
 *   notyet    a hollow ring in white (ink on paper) and the words "Not yet". No hue, no shake.
 *   watching  a dashed gray ring (decision 5: never a spinner).
 *   checking  the spinner: a check is in flight (the one state that moves).
 *   next      a faint ring: not reached yet.
 *   skipped   a faint ring with a bar: done, never green.
 *   unknown   a gray dashed ring: can't tell without prompting (a permission behind an external engine).
 */
import { motion } from 'motion/react'
import type { ReactNode } from 'react'
import { Spinner } from './atoms'
import { color, fill, paper, spring, status as tone, type2 } from '../theme'

export type StatusState = 'passed' | 'notyet' | 'watching' | 'checking' | 'next' | 'skipped' | 'unknown'
export type StatusSurface = 'dark' | 'paper'

export const STATUS_WORD: Record<StatusState, string> = {
  passed: 'Passed',
  notyet: 'Not yet',
  watching: 'Watching',
  checking: 'Checking',
  next: 'Up next',
  skipped: 'Skipped',
  unknown: 'Not sure yet'
}

/** The watching ring's dashes (12 around r 8.2, the same as CheckIcon's). */
const DASH = '2.4 1.9'

export function StatusGlyph({ state, size = 18, surface = 'dark' }: { state: StatusState; size?: number; surface?: StatusSurface }): ReactNode {
  const onPaper = surface === 'paper'
  if (state === 'passed')
    return (
      <motion.svg data-status-glyph={state} width={size} height={size} viewBox="0 0 18 18" className="shrink-0" initial={{ scale: 0.6 }} animate={{ scale: 1 }} transition={spring}>
        <circle cx="9" cy="9" r="9" fill={onPaper ? tone.passedOnPaper : tone.passed} />
        <path d="M5.2 9.3 L7.8 11.8 L12.9 6.4" fill="none" stroke={onPaper ? paper.surface : color.onGreen} strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" />
      </motion.svg>
    )
  if (state === 'checking') return <Spinner size={size} c={onPaper ? paper.ink : color.accent} track={onPaper ? paper.group : fill.trackSoft} />
  const ring = onPaper ? paper.faint : tone.ring
  const stroke =
    state === 'notyet' ? (onPaper ? tone.notYetOnPaper : tone.notYet) : state === 'watching' || state === 'unknown' ? tone.watching : ring
  const dashed = state === 'watching' || state === 'unknown'
  return (
    <svg data-status-glyph={state} width={size} height={size} viewBox="0 0 18 18" className="shrink-0">
      <circle cx="9" cy="9" r="8.2" fill="none" stroke={stroke} strokeWidth={state === 'notyet' ? 1.6 : 1.4} strokeDasharray={dashed ? DASH : undefined} />
      {state === 'skipped' && <path d="M5.5 9 H12.5" stroke={stroke} strokeWidth="1.4" strokeLinecap="round" />}
    </svg>
  )
}

/** The status word. Green only for Passed; Not yet is plain text (white / ink); the rest are the gray. */
export function StatusWord({ state, surface = 'dark' }: { state: StatusState; surface?: StatusSurface }): ReactNode {
  const onPaper = surface === 'paper'
  const c =
    state === 'passed'
      ? onPaper
        ? tone.passedOnPaper
        : tone.passed
      : state === 'notyet' || state === 'checking'
        ? onPaper
          ? paper.ink
          : color.text
        : onPaper
          ? paper.faint
          : tone.watching
  return (
    <span data-status-word={state} className="shrink-0 whitespace-nowrap font-medium" style={{ color: c, fontSize: type2.xs }}>
      {STATUS_WORD[state]}
    </span>
  )
}

/** One row: glyph, label (and an optional detail under it), the status word on the right (or `right`). */
export function StatusRow({
  state,
  label,
  detail,
  right,
  surface = 'dark',
  hideWord
}: {
  state: StatusState
  label: ReactNode
  detail?: ReactNode
  right?: ReactNode
  surface?: StatusSurface
  hideWord?: boolean
}): ReactNode {
  const onPaper = surface === 'paper'
  const strong = state === 'notyet' || state === 'checking'
  return (
    <div data-status-row={state} className="flex items-start gap-3" style={{ fontSize: type2.md, lineHeight: '18px' }}>
      <StatusGlyph state={state} surface={surface} />
      <div className="min-w-0 flex-1">
        <div className="break-words" style={{ color: onPaper ? paper.ink : strong ? color.text : color.label }}>
          {label}
        </div>
        {detail && (
          <div className="mt-[1px] break-words" style={{ fontSize: type2.xs, lineHeight: '16px', color: onPaper ? paper.faint : color.faint }}>
            {detail}
          </div>
        )}
      </div>
      {right ?? (!hideWord && <StatusWord state={state} surface={surface} />)}
    </div>
  )
}

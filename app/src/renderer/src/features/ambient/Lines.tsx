/**
 * Feature: ambient. The two pill-sized lines (the notch drops them under the notch row; below the menu bar they are
 * the pill itself):
 *
 *   ErrorChip  "[bonsai] Error in Terminal · Explain ✕". Explain is the option's pastel (sky, BRAND.md mapping), the ✕
 *              is neutral chrome. No hue for the error itself: nothing red, nothing alarming.
 *   HelpLine   "[bon] 2 of 4 · Point to Export   Back  Next  ✕" while bon points at the step's control. Waiting for
 *              the steps: the spinner and "Looking at Blender". Done: "Done". A fail: the calm line.
 */
import { motion } from 'motion/react'
import { X } from 'lucide-react'
import type { ReactNode } from 'react'
import { actionTone, color, fill, spring } from '../../core/theme'
import { Spinner } from '../../core/ui/atoms'
import { MiyagiMark } from '../../core/ui/Mark'
import { fade, press } from '../../core/ui/motion'
import { Buddy } from '../buddy/store'
import { chipLine, clip, failLine, stepCount } from './model'
import { dismissChip, explain, helpNav, holdChip, useAmbient } from './store'

/** A small chip in the line (Explain, Back, Next): pastel for an option, the neutral button fill for chrome. */
function Chip({ label, onClick, tone, disabled, data }: { label: string; onClick: () => void; tone?: string; disabled?: boolean; data?: string }): ReactNode {
  return (
    <motion.button
      type="button"
      data-hit
      data-ambient-chip={data}
      disabled={disabled}
      className="ml-[4px] h-[22px] shrink-0 cursor-pointer rounded-full px-[10px] text-[12px] font-medium disabled:cursor-default"
      style={{ backgroundColor: tone ?? fill.button, color: tone ? color.onPastel : color.text, opacity: disabled ? 0.4 : 1 }}
      whileHover={disabled ? undefined : tone ? { opacity: 0.88 } : { backgroundColor: fill.chipHover }}
      whileTap={disabled ? undefined : { scale: press.scale }}
      transition={{ ...spring, backgroundColor: fade.tint, opacity: fade.tint }}
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
    >
      {label}
    </motion.button>
  )
}

function Close({ onClick, label }: { onClick: () => void; label: string }): ReactNode {
  return (
    <motion.button
      type="button"
      data-hit
      aria-label={label}
      className="ml-[4px] grid h-[22px] w-[22px] shrink-0 cursor-pointer place-items-center rounded-full"
      style={{ color: color.label }}
      whileHover={{ backgroundColor: fill.chipHover, color: color.text }}
      whileTap={{ scale: press.scale }}
      transition={{ ...spring, backgroundColor: fade.tint }}
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
    >
      <X size={12} strokeWidth={2.2} />
    </motion.button>
  )
}

export function ErrorChip(): ReactNode {
  const e = useAmbient((s) => s.error)
  if (!e) return null
  return (
    <div
      data-hit
      data-ambient="chip"
      role="status"
      aria-live="polite"
      className="flex h-[34px] items-center whitespace-nowrap pl-[13px] pr-[6px] text-[13px] font-medium"
      style={{ color: color.text }}
      title={e.title}
      onMouseEnter={() => holdChip(true)}
      onMouseLeave={() => holdChip(false)}
    >
      <MiyagiMark size={16} className="mr-[8px]" />
      <span>{chipLine(e)}</span>
      <span style={{ color: color.label }}>&nbsp;·&nbsp;</span>
      <Chip label="Explain" tone={actionTone.explain} onClick={explain} data="explain" />
      <Close label="Not now" onClick={dismissChip} />
    </div>
  )
}

export function HelpLine(): ReactNode {
  const h = useAmbient((s) => s.help)
  if (!h) return null
  const step = h.steps[h.current]
  const total = h.steps.length
  const app = (h.app ?? '').trim()
  let body: ReactNode
  if (h.error) {
    body = (
      <>
        <MiyagiMark size={16} className="mr-[8px]" />
        <span className="block max-w-[380px] truncate">{failLine(h.error, h.retryInS, 'help')}</span>
      </>
    )
  } else if (h.pending || !step) {
    body = (
      <>
        <span className="mr-[8px] grid w-[16px] place-items-center">
          <Spinner size={14} />
        </span>
        <span>{app ? `Looking at ${clip(app, 24)}` : 'Looking at your app'}</span>
      </>
    )
  } else if (h.done) {
    body = (
      <>
        <MiyagiMark size={16} className="mr-[8px]" />
        <span>Done</span>
        {h.goal && <span style={{ color: color.label }}>&nbsp;· {clip(h.goal, 40)}</span>}
      </>
    )
  } else {
    const last = h.current >= total - 1
    body = (
      <>
        <span className="mr-[8px] grid w-[16px] place-items-center">
          <Buddy size={16} />
        </span>
        <span className="tabular-nums" style={{ color: color.label }}>
          {stepCount(h.current, total)}
        </span>
        <span style={{ color: color.label }}>&nbsp;·&nbsp;</span>
        <span className="block max-w-[320px] truncate" data-ambient-step={step.id}>
          {step.text}
        </span>
        <span className="w-[6px]" />
        <Chip label="Back" disabled={h.current === 0} onClick={() => helpNav('back')} data="back" />
        <Chip label={last ? 'Done' : 'Next'} onClick={() => helpNav(last ? 'close' : 'next')} data="next" />
      </>
    )
  }
  return (
    <div
      data-hit
      data-ambient="help"
      role="status"
      aria-live="polite"
      className="flex h-[34px] items-center whitespace-nowrap pl-[13px] pr-[6px] text-[13px] font-medium"
      style={{ color: color.text }}
      title={step?.detail ?? h.goal}
    >
      {body}
      <Close label="Close help" onClick={() => helpNav('close')} />
    </div>
  )
}

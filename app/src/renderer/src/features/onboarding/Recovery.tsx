/**
 * Feature: onboarding (A3). Onb-Permission-Recovery: a permission went away mid-lesson. The card grows out of the pill
 * (island mode, priority 75), says which one, keeps the learner's place (core useCurrentStep), shows every row live,
 * and offers the one fix: Open System Settings (core permissions:open, after the macOS prompt on this click only).
 * Accessibility can be skipped ("Keep going without pointing"); Screen Recording can't (miyagi can't see without it),
 * so its second button is Relaunch (macOS often applies that grant only after one).
 * It closes on its own when the grant is back or the engine resumes the lesson.
 */
import { motion } from 'motion/react'
import type { ReactNode } from 'react'
import { color, fill, radius2, type2 } from '../../core/theme'
import { useCurrentStep } from '../../core/lesson'
import { PrimaryButton } from '../../core/ui/buttons'
import { pressMotion } from '../../core/ui/motion'
import { StatusGlyph, StatusWord } from '../../core/ui/status'
import { Row } from './Row'
import { useRows } from './rows'
import { keepGoing, runAction, useOnboarding } from './store'

export const RECOVERY_W = 368

const NAME = { screen: 'Screen Recording', accessibility: 'Accessibility' } as const

/** "Step 3 of 6  ·  Build the model", or nothing before the first step. */
export function savedPlace(step: { index: number; total: number; title: string }): string | undefined {
  if (step.index < 0 || !step.title) return undefined
  return `Step ${step.index + 1}${step.total > 0 ? ` of ${step.total}` : ''}  ·  ${step.title}`
}

/** Polish: hover is the .mg-press tint and press the core dip, so nothing animates a filter. */
function TextButton({ label, onClick }: { label: string; onClick: () => void }): ReactNode {
  return (
    <motion.button
      type="button"
      {...pressMotion()}
      className="mg-press h-[44px] w-full cursor-pointer"
      style={{ borderRadius: radius2.card, background: fill.clear, color: color.label, fontSize: type2.sm, fontWeight: 500 }}
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
    >
      {label}
    </motion.button>
  )
}

export function Recovery(): ReactNode {
  const rec = useOnboarding((s) => s.recovery)
  const asked = useOnboarding((s) => (rec ? s.asked[rec.kind] : undefined))
  const rows = useRows()
  const step = useCurrentStep()
  if (!rec) return null
  const place = savedPlace(step)
  const name = NAME[rec.kind]
  return (
    <div data-onb-recovery={rec.kind} role="alertdialog" aria-labelledby="onb-rec-title" className="flex flex-col gap-[24px] p-[24px]" style={{ width: RECOVERY_W }}>
      <div className="flex flex-col gap-[16px]">
        <div className="flex items-center gap-[8px]">
          <StatusGlyph state="notyet" size={18} />
          <StatusWord state="notyet" />
        </div>
        <div className="flex flex-col gap-[8px]">
          <h2 id="onb-rec-title" className="m-0" style={{ fontSize: type2.xl, lineHeight: '28px', fontWeight: 600, color: color.text }}>
            {name} was turned off
          </h2>
          <p className="m-0" style={{ fontSize: type2.body, lineHeight: '22px', color: color.label }}>
            Turn it back on. The lesson resumes on its own.
          </p>
        </div>
      </div>

      {place && (
        <div data-onb-place className="flex flex-col gap-[4px] px-[16px] py-[12px]" style={{ borderRadius: radius2.card, background: fill.tile }}>
          <span style={{ fontSize: type2.xs, color: color.label }}>Your place is saved</span>
          <span className="truncate" style={{ fontSize: type2.sm, fontWeight: 500, color: color.text }}>
            {place}
          </span>
        </div>
      )}

      <div role="list" className="flex flex-col" style={{ borderTop: `1px solid ${fill.hairline}` }}>
        {rows.map((r, i) => (
          <Row key={r.id} row={r} variant="line" last={i === rows.length - 1} />
        ))}
      </div>

      <div className="flex flex-col gap-[8px]">
        <PrimaryButton size="lg" block label="Open System Settings" onClick={() => void runAction(rec.kind === 'screen' ? 'allow-screen' : 'open-accessibility')} />
        {rec.kind === 'accessibility' ? (
          <TextButton label="Keep going without pointing" onClick={keepGoing} />
        ) : (
          asked && <TextButton label="Relaunch miyagi" onClick={() => void runAction('relaunch')} />
        )}
      </div>
    </div>
  )
}

/**
 * Prog-Step-Passed: the island grown into a small passed card while the lesson panel is collapsed (Mini). Which step
 * passed and of how many, the engine's one-line summary, a stable track (never reshuffles) and what comes next. One
 * primary: Continue (folds it back into the pill; so does the timer, Esc, or the panel opening).
 */
import type { ReactNode } from 'react'
import { PrimaryButton } from '../../core/ui/buttons'
import { MiyagiMark, MiyagiWordmark } from '../../core/ui/Mark'
import { StatusGlyph } from '../../core/ui/status'
import { StepDots } from '../../core/ui/StepDots'
import { color, copy, fill, radius2, status, type2 } from '../../core/theme'
import { closeStep, useProgress, type StepCard } from './store'

export const STEP_W = 368
const PAD_X = 20
/** Up to this many steps get one bar each; past it, the proportional track (core StepDots). */
const BARS_MAX = 24

/** One bar per step: passed green, skipped the faint ring tone (never green), the next one brighter than the rest. */
function Track({ card }: { card: StepCard }): ReactNode {
  const n = card.total
  const passed = new Set(card.passed)
  const skipped = new Set(card.skipped)
  if (n > BARS_MAX) return <StepDots total={n} current={card.index + 1} passed={card.passed} skipped={card.skipped} cap={0} width={STEP_W - 2 * PAD_X} />
  return (
    <div role="img" aria-label={`${passed.size} of ${n} steps passed`} data-step-track={n} className="grid" style={{ gridTemplateColumns: `repeat(${n}, 1fr)`, gap: 4 }}>
      {Array.from({ length: n }, (_, i) => {
        const state = skipped.has(i) ? 'skipped' : passed.has(i) ? 'passed' : i === card.index + 1 ? 'next' : 'later'
        const bg = state === 'passed' ? color.green : state === 'skipped' ? fill.ring : state === 'next' ? status.ring : fill.hairline
        return <span key={i} data-bar={state} className="block" style={{ height: 4, borderRadius: radius2.round, background: bg }} />
      })}
    </div>
  )
}

export function StepPassedCard(): ReactNode {
  const card = useProgress((s) => s.step)
  if (!card) return null
  return (
    <section aria-label="Step passed" data-progress="step-passed" className="flex flex-col" style={{ width: STEP_W, padding: `16px ${PAD_X}px 20px`, gap: 16 }}>
      <div className="flex items-center justify-between" style={{ height: 24 }}>
        <div className="flex items-center gap-[8px]">
          <MiyagiMark size={16} />
          <MiyagiWordmark height={13} />
        </div>
        <span className="tabular-nums" style={{ fontSize: type2.xs, color: color.label }}>
          Step {card.index + 1} of {card.total}
        </span>
      </div>

      <div className="flex items-center gap-[12px]">
        <StatusGlyph state="passed" size={40} />
        <div className="flex min-w-0 flex-col gap-[2px]">
          <span className="font-semibold" style={{ fontSize: type2.lg, lineHeight: '22px', color: color.text }}>
            {copy.passed}
          </span>
          <span className="truncate" style={{ fontSize: type2.sm, lineHeight: '18px', color: color.label }} title={card.summary ?? card.title}>
            {card.summary ?? `${card.title} passed`}
          </span>
        </div>
      </div>

      <Track card={card} />

      <div className="flex items-center justify-between gap-[12px]">
        {card.next ? (
          <div className="flex min-w-0 flex-col gap-[2px]">
            <span style={{ fontSize: type2.xs, color: color.label }}>Next</span>
            <span className="truncate font-semibold" style={{ fontSize: type2.md, color: color.text }}>
              {card.next}
            </span>
          </div>
        ) : (
          <span />
        )}
        <PrimaryButton label="Continue" size="lg" onClick={closeStep} />
      </div>
    </section>
  )
}

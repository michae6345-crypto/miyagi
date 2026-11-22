/**
 * Prog-Review-Reminder: "Time to review <skill>", grown out of the island at launch while no lesson runs. Only the
 * engine's review queue opens it (no scheduler exists yet, so only fixture data today). Start review is the one
 * primary when the engine lists review.start (else Open Progress, never a dead button); Later (Esc) puts it away.
 */
import { FileCode2 } from 'lucide-react'
import type { ReactNode } from 'react'
import { CodeText } from '../../core/ui/atoms'
import { PrimaryButton, QuietButton } from '../../core/ui/buttons'
import { Keycap } from '../../core/ui/Keycap'
import { MiyagiMark } from '../../core/ui/Mark'
import { openProgress } from '../../core/surfaces'
import { color, font, type2 } from '../../core/theme'
import { closeReview, startReview, useProgress } from './store'
import { whenWord } from './types'

export const REVIEW_W = 432

/** "3 quick checks in your own notebook." Counted from the queue item; the place from its file. */
function checksLine(checks: number, file?: string): string {
  const where = file && /\.ipynb$/i.test(file) ? 'notebook' : 'code'
  if (checks <= 0) return `Quick checks in your own ${where}.`
  return `${checks} quick check${checks === 1 ? '' : 's'} in your own ${where}.`
}

export function ReviewReminderCard(): ReactNode {
  const review = useProgress((s) => s.review)
  const canStart = useProgress((s) => s.caps.review)
  if (!review) return null
  const { item } = review
  const due = item.when ? ` Due ${whenWord(item.when)}.` : ''
  // Overlay round: the same shape as every island card (bonsai + label + Esc, title, one body line, a pair of buttons).
  // No chips on the island (no gray fills there); the file is a quiet mono line. Never a dead button: when this engine
  // can't start a review, the primary opens Progress instead.
  return (
    <section aria-labelledby="progress-review-title" data-progress="review" className="flex flex-col" style={{ width: REVIEW_W, padding: 20, gap: 16 }}>
      <div className="flex min-h-[22px] items-center justify-between gap-3">
        <span className="flex items-center gap-[8px]" style={{ fontSize: type2.xs, color: color.label }}>
          <MiyagiMark size={14} />
          Spaced review
        </span>
        <Keycap k="dismiss" />
      </div>

      <div className="flex flex-col" style={{ gap: 6 }}>
        <h1 id="progress-review-title" className="m-0 font-semibold" style={{ fontSize: type2.lg, lineHeight: '22px', letterSpacing: '-0.01em', color: color.text }}>
          Time to review <CodeText text={item.label} />
        </h1>
        <p className="m-0" style={{ fontSize: type2.sm, lineHeight: '18px', color: color.label }}>
          {checksLine(item.checks, item.file)}
          {due}
        </p>
        {item.file && (
          <span className="flex min-w-0 items-center gap-[6px]" style={{ fontFamily: font.mono, fontSize: type2.micro, lineHeight: '16px', color: color.label }}>
            <FileCode2 size={12} strokeWidth={1.8} aria-hidden />
            <span className="truncate">{item.file}</span>
          </span>
        )}
      </div>

      <div className="grid grid-cols-2 gap-[8px]">
        <QuietButton label="Later" size="lg" block onClick={closeReview} />
        {canStart ? (
          <PrimaryButton label="Start review" size="lg" block onClick={() => startReview(item)} />
        ) : (
          <PrimaryButton
            label="Open Progress"
            size="lg"
            block
            onClick={() => {
              closeReview()
              void openProgress()
            }}
          />
        )}
      </div>
    </section>
  )
}

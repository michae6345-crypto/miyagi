/**
 * Prog-Review-Reminder: "Time to review <skill>", grown out of the island at launch while no lesson runs. Only the
 * engine's review queue opens it (no scheduler exists yet, so only fixture data today). Start review is the one
 * primary and stays disabled unless the engine lists review.start; Later (Esc) puts it away for this session.
 */
import { FileCode2 } from 'lucide-react'
import type { ReactNode } from 'react'
import { CodeText } from '../../core/ui/atoms'
import { PrimaryButton, QuietButton } from '../../core/ui/buttons'
import { MiyagiWordmark } from '../../core/ui/Mark'
import { color, font, radius2, surface, type2 } from '../../core/theme'
import { closeReview, startReview, useProgress } from './store'
import { whenWord } from './types'

export const REVIEW_W = 432

function Chip({ children, mono }: { children: ReactNode; mono?: boolean }): ReactNode {
  return (
    <span
      className="inline-flex h-[28px] min-w-0 items-center gap-[6px] px-[10px]"
      style={{ borderRadius: radius2.control, background: surface.row, boxShadow: `inset 0 0 0 1px ${surface.border}`, fontSize: type2.xs, color: color.text, fontFamily: mono ? font.mono : undefined }}
    >
      {children}
    </span>
  )
}

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
  const { item, due } = review
  return (
    <section aria-labelledby="progress-review-title" data-progress="review" className="flex flex-col" style={{ width: REVIEW_W, padding: 20, gap: 12 }}>
      <div className="flex items-center gap-[8px]" style={{ height: 28, fontSize: type2.xs, color: color.label }}>
        <MiyagiWordmark height={13} className="h-[13px] w-auto" />
        <span aria-hidden>·</span>
        <span>Spaced review</span>
      </div>

      <div className="flex flex-col gap-[4px]">
        <h1 id="progress-review-title" className="m-0 font-semibold" style={{ fontSize: 18, lineHeight: '24px', letterSpacing: '-0.01em', color: color.text }}>
          Time to review <CodeText text={item.label} />
        </h1>
        <p className="m-0" style={{ fontSize: type2.sm, lineHeight: '18px', color: color.label }}>
          {checksLine(item.checks, item.file)}
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-[8px]">
        {item.file && (
          <Chip mono>
            <FileCode2 size={13} strokeWidth={1.8} aria-hidden />
            <span className="truncate">{item.file}</span>
          </Chip>
        )}
        {item.when && <Chip>Due {whenWord(item.when)}</Chip>}
        {due > 1 && <Chip>{due} due</Chip>}
      </div>

      <div className="mt-[4px] flex items-center gap-[8px]">
        <div className="min-w-0 flex-1">
          <PrimaryButton
            label="Start review"
            size="lg"
            block
            disabled={!canStart}
            title={canStart ? undefined : 'miyagi can’t start reviews yet'}
            onClick={() => startReview(item)}
          />
        </div>
        <QuietButton label="Later" size="lg" keyName="dismiss" onClick={closeReview} />
      </div>
    </section>
  )
}

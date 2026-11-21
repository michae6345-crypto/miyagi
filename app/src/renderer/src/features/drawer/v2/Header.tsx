/**
 * Feature: drawer (v2, A1). The panel's header (Les-Anatomy "Collapse to pill" and "Step dots"): the tree and the
 * lowercase wordmark text, the collapse button, the lesson's title, the step dots and "Step N of M".
 */
import type { ReactNode } from 'react'
import { ChevronUp } from 'lucide-react'
import { copy, fill, font, radius2, type2 } from '../../../core/theme'
import { MiyagiMark } from '../../../core/ui/Mark'
import { StepDots } from '../../../core/ui/StepDots'
import { motion } from 'motion/react'
import { Tip, tone } from './ui'

export function Header({
  lessonTitle,
  total,
  index,
  passed,
  skipped,
  onCollapse
}: {
  lessonTitle: string
  total: number
  index: number
  passed: number[]
  skipped: number[]
  onCollapse: () => void
}): ReactNode {
  const n = Math.min(total, Math.max(1, index + 1))
  return (
    <div data-part="panel-header" className="shrink-0">
      <div className="flex items-center gap-[8px]" style={{ padding: '12px 12px 0 20px' }}>
        <MiyagiMark size={20} />
        <span className="flex-1 truncate" style={{ fontFamily: font.brand, fontSize: type2.body, fontWeight: 600, letterSpacing: '-0.02em' }}>
          {copy.name}
        </span>
        <Tip label="Collapse to the pill" k="dismiss">
          <motion.button
            type="button"
            data-part="panel-collapse"
            aria-label="Collapse to the pill"
            className="grid h-[32px] w-[32px] shrink-0 cursor-pointer place-items-center"
            style={{ borderRadius: radius2.control, color: tone.label }}
            whileHover={{ backgroundColor: fill.chipHover, color: tone.text }}
            whileTap={{ scale: 0.92 }}
            transition={{ duration: 0.12 }}
            onMouseDown={(e) => e.preventDefault()}
            onClick={onCollapse}
          >
            <ChevronUp size={16} strokeWidth={1.6} aria-hidden />
          </motion.button>
        </Tip>
      </div>
      <div className="flex flex-col gap-[8px]" style={{ padding: '8px 20px 16px' }}>
        {lessonTitle && (
          <span className="truncate" title={lessonTitle} style={{ fontSize: type2.xs, lineHeight: '16px', color: tone.label }}>
            {lessonTitle}
          </span>
        )}
        {total > 0 && (
          <div className="flex items-center gap-[12px]">
            <StepDots total={total} current={index} passed={passed} skipped={skipped} />
            <span className="whitespace-nowrap" style={{ fontSize: type2.xs, color: tone.label }}>
              Step {n} of {total}
            </span>
          </div>
        )}
      </div>
    </div>
  )
}

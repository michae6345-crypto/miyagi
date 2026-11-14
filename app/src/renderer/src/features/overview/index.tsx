/**
 * Feature: overview. Hovering the pill morphs it into the step card (mockup 02):
 * thumbnail, "Step 4 of 7", segmented progress, live checks, footer.
 */
import { motion } from 'motion/react'
import type { ReactNode } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { bridge } from '../../bridge'
import { useLesson, useProgress, useStatus, type Status } from '../../core/lesson'
import { defineFeature } from '../../core/registry'
import { CheckList, Kbd, StatusDot, Thumb } from '../../core/ui/atoms'
import { clock, color, fill } from '../../core/theme'

function Segments({ total, index, status }: { total: number; index: number; status: Status }): ReactNode {
  const current = status === 'offtrack' ? color.amber : status === 'passed' ? color.green : color.accent
  return (
    <div className="mt-[10px] flex gap-[5px]">
      {Array.from({ length: total }, (_, i) => (
        <motion.div
          key={i}
          className="h-[3px] flex-1 rounded-full"
          initial={false}
          animate={{ backgroundColor: i < index ? color.text : i === index ? current : fill.track }}
          transition={{ duration: 0.3 }}
        />
      ))}
    </div>
  )
}

function Overview(): ReactNode {
  const s = useLesson(useShallow((x) => ({ title: x.stepTitle, checks: x.checks, video: x.stepVideo })))
  const { index, total } = useProgress()
  const status = useStatus()
  const start = s.video ? clock(s.video.start) : undefined
  const end = s.video ? clock(s.video.end) : undefined
  // One short fact, no sentence: where the video waits (or that this step passed).
  const footer = status === 'passed' ? 'Passed' : end ? `Video waits at ${end}` : undefined
  return (
    <div className="px-[22px] pb-[16px] pt-[20px]">
      <div className="flex gap-[16px]">
        <Thumb w={120} h={68} time={start} />
        <div className="min-w-0 flex-1 pt-[2px]">
          <div className="flex items-center gap-[7px] text-[13px]" style={{ color: color.label }}>
            Step {index + 1} of {total} <StatusDot status={status} />
          </div>
          <div className="mt-[2px] truncate text-[20px] font-semibold tracking-[-0.015em]">{s.title}</div>
          <Segments total={total} index={index} status={status} />
        </div>
      </div>
      {s.checks.length > 0 && (
        <div className="mt-[18px]">
          <CheckList checks={s.checks} />
        </div>
      )}
      <div className="mt-[16px] flex items-center justify-between gap-[8px] border-t pt-[12px] text-[13px]" style={{ borderColor: fill.rule, color: color.faint }}>
        <span className="truncate">{footer}</span>
        <span className="flex shrink-0 items-center gap-[8px]" style={{ color: color.label }}>
          Ask <Kbd>{bridge.platform.keys.launcher}</Kbd>
        </span>
      </div>
    </div>
  )
}

export default defineFeature({
  id: 'overview',
  islandModes: [
    {
      id: 'overview',
      priority: 20,
      width: 440,
      useActive: (hover) => useLesson((s) => hover && !!s.stepId && !s.offtrack),
      Content: Overview
    }
  ]
})

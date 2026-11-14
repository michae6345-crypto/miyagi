/**
 * Feature: overview. Hovering the pill morphs it into the step card (mockup 02):
 * thumbnail, "Step 4 of 7", segmented progress, live checks, footer.
 */
import { AnimatePresence, motion } from 'motion/react'
import type { ReactNode } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { bridge } from '../../bridge'
import { useLesson, useProgress, useStatus, type Status } from '../../core/lesson'
import { defineFeature } from '../../core/registry'
import { CheckList, StatusDot, Thumb } from '../../core/ui/atoms'
import { clock, color } from '../../core/theme'
import { Gear } from './Gear'
import { GoalNote, Instructions, Meta } from './Lines'

function Segments({ total, index, status }: { total: number; index: number; status: Status }): ReactNode {
  const current = status === 'offtrack' ? color.amber : status === 'passed' ? color.green : color.accent
  return (
    <div className="mt-[10px] flex gap-[5px]">
      {/* lesson.updated appends steps: existing segments keep their key and state; only the new ones fade in. */}
      <AnimatePresence initial={false}>
      {Array.from({ length: total }, (_, i) => (
        <motion.div
          key={i}
          className="h-[3px] flex-1 rounded-full"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1, background: i < index ? 'rgba(255,255,255,.88)' : i === index ? current : 'rgba(255,255,255,.18)' }}
          transition={{ duration: 0.3 }}
        />
      ))}
      </AnimatePresence>
    </div>
  )
}

function Overview(): ReactNode {
  const s = useLesson(useShallow((x) => ({ title: x.stepTitle, checks: x.checks, video: x.stepVideo })))
  const { index, total } = useProgress()
  const status = useStatus()
  const start = s.video ? clock(s.video.start) : undefined
  return (
    <div className="px-[22px] pb-[16px] pt-[20px]">
      <div className="flex gap-[16px]">
        <Thumb w={120} h={68} time={start} />
        <div className="min-w-0 flex-1 pt-[2px]">
          <div className="flex items-center gap-[7px] text-[13px] text-white/55">
            Step {index + 1} of {total} <StatusDot status={status} />
          </div>
          <div className="mt-[2px] truncate text-[20px] font-semibold tracking-[-0.015em]">{s.title}</div>
          <GoalNote />
          <Segments total={total} index={index} status={status} />
        </div>
      </div>
      <Instructions />
      {s.checks.length > 0 && (
        <div className="mt-[18px]">
          <CheckList checks={s.checks} />
        </div>
      )}
      <Meta />
      <div className="mt-[16px] flex items-center justify-between border-t pt-[12px] text-[13px] text-white/45" style={{ borderColor: 'rgba(255,255,255,.08)' }}>
        <span>Ask {bridge.platform.keys.launcher}</span>
        <Gear />
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

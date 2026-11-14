/**
 * Feature: pill. The island's pill-sized states (34px tall, width hugs content):
 *   idle      no lesson yet: "✧ Learn anything ⌥Space" (click opens the launcher)
 *   building  between Build lesson and the first step: spinner + lesson.building message
 *   compact   during a lesson: "✧ Step 4 · Define the residual  ◔ ●" (ring = progress, dot = status)
 */
import { AnimatePresence, motion } from 'motion/react'
import type { ReactNode } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { Sparkles } from 'lucide-react'
import { bridge } from '../../bridge'
import { useLesson, useProgress, useStatus } from '../../core/lesson'
import { defineFeature } from '../../core/registry'
import { Kbd, ProgressRing, Spinner, StatusDot } from '../../core/ui/atoms'

function Idle(): ReactNode {
  return (
    <button
      className="flex h-[34px] cursor-pointer items-center gap-[8px] whitespace-nowrap pl-[13px] pr-[7px] text-[13px] font-medium text-white/85"
      onClick={() => bridge.emit('launcher:toggle')}
    >
      <Sparkles size={14} strokeWidth={1.75} />
      <span>Learn anything</span>
      <Kbd className="!h-[20px]">{bridge.platform.keys.launcher}</Kbd>
    </button>
  )
}

function Building(): ReactNode {
  const msg = useLesson((x) => x.buildingMessage)
  return (
    <div className="flex h-[34px] items-center gap-[9px] whitespace-nowrap px-[14px] text-[13px] font-medium">
      <Spinner size={14} />
      <AnimatePresence mode="popLayout" initial={false}>
        <motion.span key={msg ?? 'x'} className="text-white/85" initial={{ opacity: 0, y: 5 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -5 }}>
          {msg ?? 'Building your lesson'}
        </motion.span>
      </AnimatePresence>
    </div>
  )
}

function Compact(): ReactNode {
  const { stepId, title } = useLesson(useShallow((x) => ({ stepId: x.stepId, title: x.stepTitle })))
  const { index, fraction } = useProgress()
  const status = useStatus()
  return (
    <div className="flex h-[34px] items-center gap-[9px] whitespace-nowrap pl-[14px] pr-[12px] text-[13px] font-medium">
      <Sparkles size={14} strokeWidth={1.75} className="shrink-0" />
      <AnimatePresence mode="popLayout" initial={false}>
        <motion.span key={stepId} initial={{ opacity: 0, y: 5 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -5 }} transition={{ duration: 0.22 }}>
          <span className="text-white/70">Step {index + 1}</span>
          <span className="text-white/40"> · </span>
          <span>{title}</span>
        </motion.span>
      </AnimatePresence>
      <span className="ml-[3px] flex items-center gap-[7px]">
        <ProgressRing fraction={fraction} />
        <StatusDot status={status} />
      </span>
    </div>
  )
}

export default defineFeature({
  id: 'pill',
  islandModes: [
    { id: 'idle', priority: 0, useActive: () => useLesson((s) => !s.lesson && !s.building), Content: Idle },
    { id: 'building', priority: 1, useActive: () => useLesson((s) => s.building && !s.stepId), Content: Building },
    { id: 'compact', priority: 2, useActive: () => useLesson((s) => !!s.stepId), Content: Compact }
  ]
})

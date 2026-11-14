/**
 * Feature: pill. The island's pill-sized states (34px tall, width hugs content), to mockup 01:
 *   idle      no lesson yet: "✧ Learn anything ⌥Space" (click opens the launcher)
 *   building  between Build lesson and the first step: spinner + lesson.building message + progress line
 *   compact   during a lesson: "✧ Step 4 · Define the residual  ◔ ●" (ring = steps done, dot = status)
 *
 * Measured from mockup 01 (1×): pad 15 left / 14 right · icon → text 10 · text → ring 15 · ring → dot 9 ·
 * 13px medium · "Step 4 ·" at 55% white, title at 100%.
 * The step-pass moment (check → ring → flash → crossfade) is driven by ./store.ts.
 */
import { AnimatePresence } from 'motion/react'
import type { ReactNode } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { Sparkles } from 'lucide-react'
import { bridge } from '../../bridge'
import { useLesson } from '../../core/lesson'
import { defineFeature } from '../../core/registry'
import { Kbd, Spinner } from '../../core/ui/atoms'
import { BuildLine, PillRing, StatusMark, SwapText, type Mark } from './parts'
import { usePill } from './store'

function Idle(): ReactNode {
  return (
    <button
      className="flex h-[34px] cursor-pointer items-center gap-[10px] whitespace-nowrap pl-[15px] pr-[7px] text-[13px] font-medium text-white/85 transition-colors duration-150 hover:text-white"
      onClick={() => bridge.emit('launcher:toggle')}
      aria-label="Learn anything: open the launcher"
    >
      <Sparkles size={14} strokeWidth={1.75} className="shrink-0" />
      <span>Learn anything</span>
      {/* Concentric with the pill: 7px inset, fully round (radius 10 inside radius 17). */}
      <Kbd className="!h-[20px] !rounded-full !px-[8px]">{bridge.platform.keys.launcher}</Kbd>
    </button>
  )
}

function Building(): ReactNode {
  const { message, progress } = useLesson(
    useShallow((s) => ({ message: s.buildingMessage, progress: s.lesson ? 1 : s.buildingProgress }))
  )
  const kept = usePill((s) => s.buildMessage)
  const text = message ?? kept ?? 'Building your lesson'
  return (
    <div className="relative flex h-[34px] items-center gap-[10px] whitespace-nowrap pl-[15px] pr-[17px] text-[13px] font-medium">
      <Spinner size={14} />
      <SwapText id={text} className="text-white/85">
        {text}
      </SwapText>
      <AnimatePresence>{progress !== undefined && <BuildLine progress={progress} />}</AnimatePresence>
    </div>
  )
}

type Shown = { key: string; index: number; title: string; mark: Mark; done: number }

/** What the pill shows: the engine's step, except during/after a pass, where the pill runs ahead. */
function useShown(): Shown & { total: number } {
  const l = useLesson(
    useShallow((s) => ({ stepId: s.stepId, title: s.stepTitle, steps: s.steps, passed: s.passed, offtrack: !!s.offtrack }))
  )
  const { celebrating, advanced } = usePill(useShallow((s) => ({ celebrating: s.celebrating, advanced: s.advanced })))
  const total = Math.max(1, l.steps.length)
  const at = (id?: string): number => l.steps.findIndex((x) => x.id === id)
  const titleOf = (i: number, fallback = ''): string => l.steps[i]?.title ?? fallback

  // 1) The check is showing: hold the passed step on screen (even if step.started already moved on).
  if (celebrating) {
    const i = at(celebrating)
    return { key: celebrating, index: Math.max(0, i), title: titleOf(i, l.title), mark: 'check', done: i + 1, total }
  }
  // 2) After a pass, before the engine's step.started: the next step (or the end of the lesson).
  if (advanced && advanced.from === l.stepId) {
    if (!advanced.to || at(advanced.to) < 0) return { key: 'complete', index: total, title: 'Lesson complete', mark: 'done', done: total, total }
    const j = at(advanced.to)
    return { key: advanced.to, index: j, title: titleOf(j), mark: 'watching', done: j, total }
  }
  // 3) Normal: the engine's current step.
  const i = Math.max(0, at(l.stepId))
  const passed = !!l.stepId && l.passed.includes(l.stepId)
  return {
    key: l.stepId ?? '',
    index: i,
    title: l.title,
    mark: l.offtrack ? 'offtrack' : passed ? 'passed' : 'watching',
    done: i + (passed ? 1 : 0),
    total
  }
}

function Compact(): ReactNode {
  const s = useShown()
  return (
    <div className="flex h-[34px] items-center whitespace-nowrap pl-[15px] pr-[14px] text-[13px] font-medium" data-step={s.key}>
      <Sparkles size={14} strokeWidth={1.75} className="mr-[10px] shrink-0" />
      <SwapText id={s.key} className="flex">
        {s.mark === 'done' ? (
          <span>{s.title}</span>
        ) : (
          <>
            <span className="text-white/55">Step {s.index + 1} ·&nbsp;</span>
            <span className="max-w-[240px] truncate">{s.title}</span>
          </>
        )}
      </SwapText>
      <span className="ml-[15px] flex items-center gap-[9px]">
        <PillRing fraction={Math.min(1, s.done / s.total)} complete={s.mark === 'done'} />
        <StatusMark mark={s.mark} />
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

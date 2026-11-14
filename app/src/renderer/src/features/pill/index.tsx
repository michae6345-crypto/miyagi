/**
 * Feature: pill. The island's pill-sized states (34px tall, width hugs content), to mockup 01 + the
 * Miyagi brand (app/brand/BRAND.md): always black and white, the bonsai as a one-color glyph on the left
 * (it shows its colors once the island opens), the status on the right.
 *   idle      no lesson yet: "[bonsai] Ask Miyagi ⌥Space" (click opens the launcher)
 *   building  between Build lesson and the first step: lesson.building message + spinner + progress line
 *   compact   during a lesson: "[bonsai] Step 4 · Define the residual  ◔ ●" (ring = steps done, dot = status)
 *
 * Measured from mockup 01 (1×): art 15 from the left edge, 11 before the text (= pad 13 + 16px mark box + gap 8) ·
 * 14 right · text → ring 15 · ring → dot 9 ·
 * 13px medium · "Step 4 ·" in the muted label color, title in the text color.
 * The step-pass moment (check → ring → flash → crossfade) is driven by ./store.ts.
 */
import { AnimatePresence } from 'motion/react'
import type { ReactNode } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { bridge } from '../../bridge'
import { useLesson } from '../../core/lesson'
import { defineFeature } from '../../core/registry'
import { color } from '../../core/theme'
import { Kbd, Spinner } from '../../core/ui/atoms'
import { BuildLine, MonoMark, PillRing, StatusMark, SwapText, type Mark } from './parts'
import { usePill } from './store'

function Idle(): ReactNode {
  return (
    <button
      className="group flex h-[34px] cursor-pointer items-center whitespace-nowrap pl-[13px] pr-[7px]"
      style={{ color: color.text }}
      onClick={() => bridge.emit('launcher:toggle')}
      aria-label="Ask Miyagi: open the launcher"
    >
      <MonoMark className="mr-[8px]" />
      {/* Type on the span: styles.css's unlayered `button { font: inherit }` beats Tailwind's text-/font- utilities on <button>. */}
      <span className="text-[13px] font-medium opacity-90 transition-opacity duration-150 group-hover:opacity-100">Ask Miyagi</span>
      {/* Concentric with the pill: 7px inset, fully round (radius 10 inside radius 17). */}
      <Kbd className="ml-[10px] !h-[20px] !rounded-full !px-[8px]">{bridge.platform.keys.launcher}</Kbd>
    </button>
  )
}

/**
 * The stage part of a lesson.building message: drops a trailing timer ("· 0:15", "(0:15)", "· 15s")
 * and the "Gemini is " lead-in, so "Gemini is watching the video · 0:15" → "Watching the video".
 */
function buildingStage(message?: string): string {
  if (!message) return ''
  const s = message
    .replace(/\s*(?:[·•|–—-]\s*)?\(?\d{1,2}:\d{2}(?::\d{2})?\)?\s*$/, '')
    .replace(/\s*(?:[·•|–—-]\s*)?\(?\d+(?:\.\d+)?\s*s\)?\s*$/, '')
    .replace(/^\s*gemini\s+is\s+/i, '')
    .replace(/[\s·•|–—-]+$/, '')
    .trim()
  return s ? s[0].toUpperCase() + s.slice(1) : ''
}

function Building(): ReactNode {
  const { message, progress } = useLesson(
    useShallow((s) => ({ message: s.buildingMessage, progress: s.lesson ? 1 : s.buildingProgress }))
  )
  const kept = usePill((s) => s.buildMessage)
  // Calm: show only the stage. The text (and so the crossfade + width spring) changes on a real stage change,
  // never on the timer tick; the progress line carries the motion.
  const text = buildingStage(message ?? kept) || 'Building your lesson'
  return (
    <div className="relative flex h-[34px] items-center whitespace-nowrap pl-[13px] pr-[14px] text-[13px] font-medium" style={{ color: color.text }}>
      <MonoMark className="mr-[8px]" />
      <SwapText id={text}>{text}</SwapText>
      {/* Where the ring will be once the lesson starts, so building → compact keeps its shape. */}
      <span className="ml-[15px]">
        <Spinner size={16} />
      </span>
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
    <div className="flex h-[34px] items-center whitespace-nowrap pl-[13px] pr-[14px] text-[13px] font-medium" style={{ color: color.text }} data-step={s.key}>
      <MonoMark className="mr-[8px]" />
      <SwapText id={s.key} className="flex">
        {s.mark === 'done' ? (
          <span>{s.title}</span>
        ) : (
          <>
            <span style={{ color: color.label }}>Step {s.index + 1} ·&nbsp;</span>
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

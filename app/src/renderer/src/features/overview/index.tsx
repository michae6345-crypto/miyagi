/**
 * Feature: overview. Hovering the pill morphs it into the step card (mockup 02):
 * thumbnail, "Step 4 of 7", segmented progress, live checks, footer.
 * When it may open (drawer, spotlight holes): ./clear.ts. It collapses when the pointer leaves, the window
 * loses focus or a shortcut fires (core/Island.tsx). Michael's audit A8.
 */
import { AnimatePresence, motion } from 'motion/react'
import { useLayoutEffect, useRef, type ReactNode } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { bridge } from '../../bridge'
import { useLesson, useProgress, useStatus, type Status } from '../../core/lesson'
import { defineFeature } from '../../core/registry'
import { CheckList, Kbd, StatusDot, Thumb } from '../../core/ui/atoms'
import { clock, color, fill } from '../../core/theme'
import { useDrawer } from '../drawer/store'
import { parseYouTube, thumbnailFor } from '../launcher/youtube'
import { CARD_W, LayoutProbe, setCardHeight, useOverviewActive } from './clear'
import { Gear } from './Gear'
import { GoalNote, Instructions, Meta, StepSnippet } from './Lines'
import { Stats } from './Stats'
import './snippet'
import { fade } from '../../core/ui/motion'

/**
 * Done steps white, this step gray (watching; green once it passes), the rest a dim track. A skipped step is
 * dashed: done, but never passed (Michael's audit A8: current and skipped were white like the done ones).
 */
function Segments({ total, index, status, skipped, passed }: { total: number; index: number; status: Status; skipped: boolean[]; passed: boolean[] }): ReactNode {
  const current = status === 'passed' ? color.green : color.gray
  // A passed step is green, as in the pill's bars and the panel's dots (persona QA: it was white here).
  const doneColor = (i: number): string => (passed[i] ? color.green : color.text)
  return (
    <div className="mt-[10px] flex gap-[5px]">
      {/* lesson.updated appends steps: existing segments keep their key and state; only the new ones fade in. */}
      <AnimatePresence initial={false}>
      {Array.from({ length: total }, (_, i) => {
        const dashed = i !== index && !!skipped[i]
        const bg = dashed ? fill.clear : i < index ? doneColor(i) : i === index ? current : fill.track
        return (
          <motion.div
            key={i}
            className="relative h-[3px] flex-1 overflow-hidden rounded-full"
            data-segment={dashed ? 'skipped' : i < index ? 'done' : i === index ? 'current' : 'todo'}
            initial={{ opacity: 0, backgroundColor: bg }}
            animate={{ opacity: 1, backgroundColor: bg }}
            transition={fade.slow}
          >
            {dashed && <Dashes />}
          </motion.div>
        )
      })}
      </AnimatePresence>
    </div>
  )
}

/** A skipped step's segment: short white dashes on the same 3px line. */
function Dashes(): ReactNode {
  return (
    <svg className="absolute inset-0 h-full w-full" aria-hidden>
      <line x1="0" y1="1.5" x2="100%" y2="1.5" stroke={color.text} strokeWidth={3} strokeDasharray="4 3" />
    </svg>
  )
}

function Overview(): ReactNode {
  const s = useLesson(useShallow((x) => ({ title: x.stepTitle, checks: x.checks, video: x.stepVideo, textLesson: x.lesson?.mode === 'lesson' })))
  const skipped = useLesson(useShallow((x) => x.steps.map((st) => x.skipped.includes(st.id))))
  const passedSteps = useLesson(useShallow((x) => x.steps.map((st) => x.passed.includes(st.id) && !x.skipped.includes(st.id))))
  const { index, total } = useProgress()
  const status = useStatus()
  // Don't repeat what's already on screen: the drawer has who built the lesson (Meta), the bar has Ask. Stats goes
  // with Meta. The shortcut bar is up for the whole lesson (features/shortcut-bar shows it while a lesson is on).
  const drawerOpen = useDrawer((x) => x.open)
  const barUp = useLesson((x) => !!x.lesson)
  // Measure for ./clear.ts (is there room for the card next time?).
  const root = useRef<HTMLDivElement>(null)
  useLayoutEffect(() => {
    const el = root.current
    if (!el) return
    const measure = (): void => setCardHeight(el.offsetHeight)
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  const start = s.video ? clock(s.video.start) : undefined
  // The lesson's real video thumbnail, not the placeholder slide (Michael's test 12, item 7).
  const videoId = useLesson((x) => {
    const v = x.lesson?.sources.find((src) => src.kind === 'video')
    return v ? (v.videoId ?? parseYouTube(v.url)?.videoId) : undefined
  })
  const end = s.video ? clock(s.video.end) : undefined
  // One short fact, no sentence: where the video waits (or that this step passed).
  // "Just teach me" lessons have no player, so nothing waits (persona QA: "Video waits at 3:00" in a text lesson).
  const footer = status === 'passed' ? 'Passed' : end && !s.textLesson ? `Video waits at ${end}` : undefined
  return (
    <div ref={root} className="px-[22px] pb-[16px] pt-[20px]">
      <div className="flex gap-[16px]">
        {/* "Just teach me" lessons have no video: no thumbnail, no timestamps. */}
        {!s.textLesson && <Thumb w={120} h={68} time={start} src={videoId ? thumbnailFor(videoId) : undefined} />}
        <div className="min-w-0 flex-1 pt-[2px]">
          <div className="flex items-center gap-[7px] text-[13px]" style={{ color: color.label }}>
            Step {index + 1} of {total} <StatusDot status={status} />
          </div>
          <div className="mt-[2px] line-clamp-2 text-[20px] font-semibold tracking-[-0.015em]" title={s.title}>{s.title}</div>
          <GoalNote />
          <Segments total={total} index={index} status={status} skipped={skipped} passed={passedSteps} />
        </div>
      </div>
      <Instructions />
      <StepSnippet />
      {s.checks.length > 0 && (
        <div className="mt-[18px]">
          <CheckList checks={s.checks} />
        </div>
      )}
      {!drawerOpen && <Meta />}
      <div className="mt-[16px] flex items-center justify-between gap-[8px] border-t pt-[12px] text-[13px]" style={{ borderColor: fill.rule, color: color.faint }}>
        <span className="truncate">{footer}</span>
        <span className="flex shrink-0 items-center gap-[8px]" style={{ color: color.label }}>
          {!drawerOpen && <Stats />}
          {!drawerOpen && !barUp && <span className="h-[12px] w-px" style={{ background: fill.rule }} />}
          {!barUp && (
            <>
              Ask <Kbd>{bridge.platform.keys.launcher}</Kbd>
            </>
          )}
          <Gear />
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
      width: CARD_W,
      useActive: useOverviewActive,
      Content: Overview
    }
  ],
  // Renders nothing: hands the overlay's layout to ./clear.ts.
  overlayLayers: [{ id: 'overview-layout', z: 0, Component: LayoutProbe }]
})

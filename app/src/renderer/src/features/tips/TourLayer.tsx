/**
 * Feature: tips. The first-lesson walkthrough layer (overlay, z 72). A sample lesson panel docks beside the real pill,
 * and five coach marks (tourMarks.ts) point at the real pill and at the sample panel's steps, Check my work, Hint and
 * Explain, and End lesson. The sample is drawn here and wired to nothing: no engine command, no lesson, so it works
 * offline and in the stage with mock data. It is the same CoachMark card as the real tips, with Skip and Next.
 *
 * Starts from startTour() (tourStore.ts). Skip, Done and Esc end it for good. A real lesson on screen ends it (the
 * real panel is the thing to learn then). Overlay clicks stay with the sample's own marks (data-hit).
 */
import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import type { Layout } from '../../../../preload/api'
import { bridge } from '../../bridge'
import { useIslandBox } from '../../core/Island'
import { useLesson } from '../../core/lesson'
import { brand, color, dock, elevation, fill, highlight, radius2, surface, type2 } from '../../core/theme'
import { OptionButton, PrimaryButton } from '../../core/ui/atoms'
import { QuietButton } from '../../core/ui/buttons'
import { MiyagiMark } from '../../core/ui/Mark'
import { enter, fade, springOut } from '../../core/ui/motion'
import { StatusGlyph } from '../../core/ui/status'
import { CoachMark, MARK_W } from './CoachMark'
import { place, type Rect } from './place'
import { endTour, nextMark, useTour } from './tourStore'
import { SAMPLE, TOUR, type TourTarget } from './tourMarks'

const PANEL_H = 392

/** The sample lesson panel: the real one's shape (steps, Check my work, Hint and Explain, End lesson), all inert. */
function SamplePanel({ x, y }: { x: number; y: number }): ReactNode {
  const keys = bridge.platform.keys
  return (
    <motion.div
      data-hit
      data-part="tour-panel"
      className="pointer-events-auto absolute flex flex-col"
      style={{ left: x, top: y, width: dock.w, height: PANEL_H, padding: 16, borderRadius: radius2.panel, background: surface.panel, boxShadow: `${highlight.top}, inset 0 0 0 1px ${surface.border}, ${elevation.panel}` }}
      initial={{ opacity: 0, x: 16 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 16, transition: { ...springOut, opacity: fade.out } }}
      transition={enter(0, fade.slow)}
    >
      <div className="flex items-center gap-[8px]">
        <MiyagiMark size={16} />
        <span className="flex-1" style={{ fontSize: type2.sm, fontWeight: 600, color: color.text }}>
          {SAMPLE.title}
        </span>
        <span style={{ fontSize: type2.xs, fontWeight: 500, color: color.text, padding: '2px 8px', borderRadius: radius2.round, background: `color-mix(in srgb, ${brand.pastel.lilac} 22%, transparent)` }}>Sample</span>
      </div>

      <div data-tour="steps" className="mt-[14px] flex flex-col gap-[2px]" style={{ borderRadius: radius2.card, background: fill.group, padding: 6, boxShadow: `inset 0 0 0 1px ${fill.hairline}` }}>
        {SAMPLE.steps.map((s, i) => (
          <div key={s} className="flex h-[34px] items-center gap-[10px] px-[8px]" style={{ borderRadius: radius2.row, background: i === 0 ? surface.row : undefined }}>
            <StatusGlyph state={i === 0 ? 'watching' : 'next'} size={16} />
            <span style={{ fontSize: type2.sm, fontWeight: i === 0 ? 600 : 400, color: i === 0 ? color.text : color.label }}>{s}</span>
          </div>
        ))}
      </div>

      <p className="m-0 mt-[14px]" style={{ fontSize: type2.sm, lineHeight: '20px', color: color.label }}>
        {SAMPLE.hint}
      </p>
      <div className="flex-1" />

      <span data-tour="check" className="block self-start">
        <PrimaryButton label="Check my work" onClick={() => undefined} />
      </span>
      <div data-tour="help" className="mt-[12px] flex items-center gap-[8px]">
        <OptionButton action="hint" label="Hint" kbd={keys.hint} onClick={() => undefined} />
        <OptionButton action="explain" label="Explain" kbd={keys.explain} onClick={() => undefined} />
      </div>
      <span data-tour="end" className="mt-[10px] block self-start">
        <QuietButton label="End lesson" onClick={() => undefined} />
      </span>
    </motion.div>
  )
}

export function TourLayer({ layout }: { layout: Layout }): ReactNode {
  const open = useTour((s) => s.open)
  const index = useTour((s) => s.index)
  const lessonOn = useLesson((s) => !!s.lesson)
  const island = useIslandBox()
  const root = useRef<HTMLDivElement>(null)
  const card = useRef<HTMLDivElement>(null)
  const [rects, setRects] = useState<Partial<Record<TourTarget | 'panel', Rect>>>({})
  const [size, setSize] = useState({ w: MARK_W, h: 150 })

  // A real lesson is the real thing to learn: the sample steps aside.
  useEffect(() => {
    if (open && lessonOn) endTour()
  }, [open, lessonOn])

  // Esc ends it (the overlay can't take focus in Electron: there, Skip is the way out).
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent): void => {
      if (e.key !== 'Escape' || e.defaultPrevented) return
      e.preventDefault()
      e.stopImmediatePropagation()
      endTour()
    }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [open])

  const panelX = layout.width - dock.w - dock.inset
  const panelY = Math.max(dock.top + 40, Math.round(layout.height * 0.2))

  // Read where the sample's parts are (overlay coordinates; the stage scales the overlay with CSS).
  useLayoutEffect(() => {
    if (!open) return
    const measure = (): void => {
      const el = root.current
      if (!el) return
      const box = el.getBoundingClientRect()
      const k = el.offsetWidth ? box.width / el.offsetWidth : 1
      const next: Partial<Record<TourTarget | 'panel', Rect>> = {}
      for (const t of ['steps', 'check', 'help', 'end'] as const) {
        const n = el.querySelector(`[data-tour="${t}"]`)
        if (!n) continue
        const r = n.getBoundingClientRect()
        next[t] = { x: (r.left - box.left) / k, y: (r.top - box.top) / k, w: r.width / k, h: r.height / k }
      }
      const p = el.querySelector('[data-part="tour-panel"]')
      if (p) {
        const r = p.getBoundingClientRect()
        next.panel = { x: (r.left - box.left) / k, y: (r.top - box.top) / k, w: r.width / k, h: r.height / k }
      }
      setRects(next)
    }
    const t1 = setTimeout(measure, 60)
    const t2 = setTimeout(measure, 450) // after the panel's spring settles
    return () => {
      clearTimeout(t1)
      clearTimeout(t2)
    }
  }, [open, layout.width, layout.height])

  useLayoutEffect(() => {
    const el = card.current
    if (!el) return
    const measure = (): void => setSize((s) => (s.w === el.offsetWidth && s.h === el.offsetHeight ? s : { w: el.offsetWidth, h: el.offsetHeight }))
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [open, index])

  const mark = TOUR[index]
  const pillRect: Rect = island.visible && island.w > 0 ? { x: island.x, y: island.y, w: island.w, h: island.h } : { x: layout.width / 2 - 100, y: 8, w: 200, h: 34 }
  const panel = rects.panel
  const target = mark ? (mark.target === 'island' ? pillRect : rects[mark.target]) : undefined
  const at = mark && target ? place(mark.side, target, mark.target === 'island' ? target : (panel ?? target), size, { w: layout.width, h: layout.height }) : undefined

  return (
    <div ref={root} className="pointer-events-none absolute inset-0" data-tour-layer={open ? mark?.id : undefined}>
      <AnimatePresence>{open && <SamplePanel key="panel" x={panelX} y={panelY} />}</AnimatePresence>
      <AnimatePresence mode="wait">
        {open && mark && at && (
          <div key={mark.id} className="pointer-events-none absolute" style={{ left: at.x, top: at.y }}>
            <CoachMark
              ref={card}
              title={mark.title}
              body={mark.body}
              caret={at.caret}
              caretAt={at.caretAt}
              menu={false}
              onMenu={() => undefined}
              onGotIt={nextMark}
              onOff={endTour}
              tour={{ progress: `${index + 1} of ${TOUR.length}`, last: index === TOUR.length - 1, onNext: nextMark, onSkip: endTour }}
            />
          </div>
        )}
      </AnimatePresence>
    </div>
  )
}

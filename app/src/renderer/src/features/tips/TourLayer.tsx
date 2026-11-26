/**
 * Feature: tips. The first-lesson walkthrough layer (overlay, z 72). A sample lesson panel docks beside the real pill,
 * and five coach marks (tourMarks.ts) point at the real pill and at the sample panel's step dots, Check my work, Need
 * help and its keys line. The sample is drawn here and wired to nothing: no engine command, no lesson, so it works
 * offline and in the stage with mock data. It is the same CoachMark card as the real tips, with Skip and Next.
 *
 * The sample has the real lesson panel's shape (features/drawer/v2: header with the tree, step dots and "Step 1 of 3",
 * the step with its code well, the one white Check my work, Need help as pastel tiles, the keys line), built from core
 * pieces only, so the walkthrough shows what the first lesson will look like, on a Mac or a PC (keys from
 * bridge.platform.keys).
 *
 * Starts from startTour() (tourStore.ts). Skip, Done and Esc end it for good. A real lesson on screen closes it (the
 * real panel is the thing to learn then; the tour stays owed). Overlay clicks stay with the sample's own marks (data-hit).
 *
 * Resilient (Nov 25, a fresh install: "Show me around" did nothing): the sample's parts are measured for as long as the
 * tour is open (not twice right after it opens), and a mark whose target isn't on screen is waited for
 * TARGET_GRACE_MS, then skipped (tourMarks.ts planMark); with nothing left to point at the tour ends instead of stalling.
 */
import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { ChevronUp } from 'lucide-react'
import type { Layout } from '../../../../preload/api'
import { useIslandBox } from '../../core/Island'
import { useLesson } from '../../core/lesson'
import { color, copy, dock, fill, font, highlight, radius2, surface, type2 } from '../../core/theme'
import { PrimaryButton } from '../../core/ui/buttons'
import { GlassCard } from '../../core/ui/GlassCard'
import { HelpRow } from '../../core/ui/HelpRow'
import { Keycap, keyLabel, type KeyName } from '../../core/ui/Keycap'
import { useKey } from '../../core/keys'
import { MiyagiMark } from '../../core/ui/Mark'
import { enter, fade, springOut } from '../../core/ui/motion'
import { StepDots } from '../../core/ui/StepDots'
import { CoachMark, MARK_W } from './CoachMark'
import { place, type Rect } from './place'
import { endTour, goToMark, nextMark, useTour } from './tourStore'
import { planMark, SAMPLE, TOUR, type TourTarget } from './tourMarks'

const TARGETS = ['steps', 'check', 'help', 'keys'] as const
/** How often the sample's parts are measured while the tour is open (they move as the panel springs in). */
const MEASURE_MS = 250

type Rects = Partial<Record<TourTarget | 'panel', Rect>>
const sameRects = (a: Rects, b: Rects): boolean => {
  const ka = Object.keys(a) as (keyof Rects)[]
  if (ka.length !== Object.keys(b).length) return false
  return ka.every((k) => {
    const x = a[k]
    const y = b[k]
    return !!x && !!y && Math.abs(x.x - y.x) < 0.5 && Math.abs(x.y - y.y) < 0.5 && Math.abs(x.w - y.w) < 0.5 && Math.abs(x.h - y.h) < 0.5
  })
}
const noop = (): void => undefined

function Rule(): ReactNode {
  return <div aria-hidden className="h-px shrink-0" style={{ background: fill.hairline }} />
}

/** One quiet item of the keys line: "[Esc] hide", "[launcher key] ask miyagi", "Back [key]". Inert. */
function KeyItem({ k, label, keyFirst = true }: { k: KeyName; label: string; keyFirst?: boolean }): ReactNode {
  if (!keyLabel(k)) return null
  return (
    <span className="flex h-[28px] shrink-0 items-center gap-[6px] px-[6px]">
      {keyFirst && <Keycap k={k} size="sm" />}
      <span>{label}</span>
      {!keyFirst && <Keycap k={k} size="sm" />}
    </span>
  )
}

/** The sample lesson panel: the real one's shape and spacing, every part inert. */
function SamplePanel({ x, y }: { x: number; y: number }): ReactNode {
  const launch = useKey('launcher')
  // Same rule as the real keys line (drawer/v2/KeysRow): a long launcher key leaves room for "ask miyagi" only.
  const askLabel = launch && launch.length > 3 ? copy.ask : copy.launcherPlaceholder
  return (
    <motion.div
      data-part="tour-panel"
      className="pointer-events-auto absolute"
      style={{ left: x, top: y, width: dock.w }}
      initial={{ opacity: 0, x: 16 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 16, transition: { ...springOut, opacity: fade.out } }}
      transition={enter(0, fade.slow)}
    >
      <GlassCard hit surface="panel" width={dock.w} className="flex flex-col">
        <div data-tour="steps">
          <div className="flex items-center gap-[8px]" style={{ padding: '12px 12px 0 20px' }}>
            <MiyagiMark size={20} />
            <span className="flex-1 truncate" style={{ fontFamily: font.brand, fontSize: type2.body, fontWeight: 600, letterSpacing: '-0.02em', color: color.text }}>
              {copy.name}
            </span>
            <span aria-hidden className="grid h-[32px] w-[32px] shrink-0 place-items-center" style={{ color: color.label }}>
              <ChevronUp size={16} strokeWidth={1.6} />
            </span>
          </div>
          <div className="flex flex-col gap-[8px]" style={{ padding: '8px 20px 16px' }}>
            <span className="flex items-center gap-[8px]" style={{ fontSize: type2.xs, lineHeight: '16px', color: color.label }}>
              <span className="truncate">{SAMPLE.title}</span>
              <span style={{ fontSize: type2.micro, fontWeight: 600, color: color.text, padding: '1px 7px', borderRadius: radius2.round, background: fill.navActive }}>Sample</span>
            </span>
            <div className="flex items-center gap-[12px]">
              <StepDots total={SAMPLE.total} current={0} passed={[]} />
              <span className="whitespace-nowrap" style={{ fontSize: type2.xs, color: color.label }}>
                Step 1 of {SAMPLE.total}
              </span>
            </div>
          </div>
        </div>
        <Rule />
        <div className="flex flex-col" style={{ padding: '20px 20px 16px' }}>
          <h2 className="m-0" style={{ fontSize: type2.xl, lineHeight: '24px', fontWeight: 600, letterSpacing: '-0.01em', color: color.text }}>
            {SAMPLE.step}
          </h2>
          <p className="m-0 mt-[4px]" style={{ fontSize: type2.md, lineHeight: '20px', color: fill.keycapText }}>
            {SAMPLE.line}
          </p>
          <span className="mt-[16px] block" style={{ fontSize: type2.xs, lineHeight: '16px', color: color.label }}>
            {SAMPLE.where}
          </span>
          <div className="mt-[8px]" style={{ background: surface.well, boxShadow: `inset 0 0 0 1px ${surface.border}, ${highlight.well}`, borderRadius: radius2.card, padding: '12px 16px' }}>
            <p className="m-0" style={{ fontFamily: font.mono, fontSize: type2.sm, lineHeight: '20px', color: color.text }}>
              {SAMPLE.code}
            </p>
          </div>
        </div>
        <div style={{ padding: '0 20px 20px' }}>
          <span data-tour="check" className="block">
            <PrimaryButton label="Check my work" block onClick={noop} />
          </span>
        </div>
        <Rule />
        <div data-tour="help" style={{ padding: '16px 20px' }}>
          <HelpRow
            options={[
              { action: 'explain', onClick: noop },
              { action: 'hint', onClick: noop },
              { action: 'show_me', onClick: noop },
              { action: 'diagram', onClick: noop }
            ]}
          />
        </div>
        <div data-tour="keys" className="flex items-center gap-[4px]" style={{ padding: '0 12px 12px 14px', fontSize: type2.xs, color: color.label }}>
          <KeyItem k="dismiss" label="hide" />
          <KeyItem k="launcher" label={askLabel} />
          <span className="flex-1" />
          <KeyItem k="back" label="Back" keyFirst={false} />
        </div>
      </GlassCard>
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
  const [rects, setRects] = useState<Rects>({})
  const [size, setSize] = useState({ w: MARK_W, h: 150 })

  // A real lesson is the real thing to learn: the sample steps aside (still owed: it isn't marked seen).
  useEffect(() => {
    if (open && lessonOn) endTour({ seen: false })
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
    if (!open) return setRects((cur) => (Object.keys(cur).length ? {} : cur))
    const measure = (): void => {
      const el = root.current
      if (!el) return
      const box = el.getBoundingClientRect()
      const k = el.offsetWidth ? box.width / el.offsetWidth : 1
      const next: Rects = {}
      for (const t of TARGETS) {
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
      setRects((cur) => (sameRects(cur, next) ? cur : next))
    }
    // At once, then all the while the tour is open: the panel springs in, and a hidden window may paint late.
    const t1 = setTimeout(measure, 60)
    const id = setInterval(measure, MEASURE_MS)
    return () => {
      clearTimeout(t1)
      clearInterval(id)
    }
  }, [open, layout.width, layout.height])

  // When the current mark came up, and a clock while it waits for its target (planMark's grace).
  // Keyed by the mark itself, so a new mark never inherits the last one's wait.
  const markKey = open ? index : -1
  const since = useRef({ key: markKey, at: Date.now() })
  if (since.current.key !== markKey) since.current = { key: markKey, at: Date.now() }
  const [now, setNow] = useState(() => Date.now())
  const plan = open ? planMark(index, (t) => !!rects[t], now - since.current.at) : undefined
  const waiting = plan?.kind === 'wait'
  useEffect(() => {
    if (!waiting) return
    const id = setInterval(() => setNow(Date.now()), MEASURE_MS)
    return () => clearInterval(id)
  }, [waiting])
  useEffect(() => {
    if (plan?.kind === 'skip') goToMark(plan.to)
    else if (plan?.kind === 'end') endTour({ seen: false }) // nothing could be shown: still owed
  }, [plan?.kind, plan?.kind === 'skip' ? plan.to : -1]) // eslint-disable-line react-hooks/exhaustive-deps

  useLayoutEffect(() => {
    const el = card.current
    if (!el) return
    const measure = (): void => setSize((s) => (s.w === el.offsetWidth && s.h === el.offsetHeight ? s : { w: el.offsetWidth, h: el.offsetHeight }))
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [open, index])

  const mark = plan?.kind === 'show' ? TOUR[index] : undefined
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
              onOff={() => endTour()}
              tour={{ progress: `${index + 1} of ${TOUR.length}`, last: index === TOUR.length - 1, onNext: nextMark, onSkip: () => endTour() }}
            />
          </div>
        )}
      </AnimatePresence>
    </div>
  )
}

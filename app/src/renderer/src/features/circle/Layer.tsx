/**
 * Feature: circle. The overlay layer: the drawing surface while the push-to-talk keys are held, the ink, the "looking"
 * chip while the engine thinks, and the answer card beside the circle.
 *
 *   drawing surface  full screen, only while armed. It takes pointerdown with ctrlKey (on a Mac, Control + click is a
 *                    right click: button 2 counts too) and swallows contextmenu. Not data-hit: core would then report
 *                    the whole screen as miyagi's own UI (overlay.bounds) and the engine would read nothing under it.
 *                    store.ts takes the mouse for it instead, and data-grab keeps core's hover tracking from saying
 *                    click-through while the pointer is on it (core/Overlay useClickThrough; never reported).
 *   ink              brand mint (tone.mint.solid, the notch's mint, never the pass green), round caps, over a thin
 *                    neutral casing (brand ink, a plain stroke: no blur, no glow) so it reads on white pages and VS Code
 *                    Light too (mint alone is about 1.3:1 on white). Passive: no pointer events, and NOT data-ui:
 *                    the svg is the whole overlay and its stroke box is exactly the circled region, so reporting either
 *                    in overlay.bounds would make the engine's reader skip (and black out) what was circled.
 *   answer card      the island's coach-mark surface, kept inside the screen edges (geometry placeCard). It opens on
 *                    the first streamed words (answer.delta) and the final card replaces its text in place (same key:
 *                    no second entrance). "Looking" shows only until the first words.
 */
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { X } from 'lucide-react'
import { useEffect, useLayoutEffect, useRef, useState, type PointerEvent, type ReactNode } from 'react'
import type { Layout } from '../../../../preload/api'
import { ThinkingDots } from '../../core/ui/atoms'
import { pressMotion } from '../../core/ui/motion'
import { duration, ease } from '../../core/ui/motionTokens'
import { brand, color, elevation, fill, highlight, radius2, surface, tone, type2 } from '../../core/theme'
import { inkPath, placeCard, toOverlay, type Box, type Pt } from './geometry'
import { inkOf, shown, type CircleState } from './machine'
import { cancelCircle, layerGone, pointerDown, pointerMove, pointerUp, setLayout, useCircle } from './store'

/** The answer card's width. */
export const CARD_W = 300
/** Its height before it is measured. */
const CARD_H0 = 140
/** The "looking" chip's size. */
const CHIP = { w: 104, h: 30 }
/**
 * The drawing surface's fill (fill.catch): next to nothing, but not fully clear, so macOS hit-tests the transparent
 * window as ours while it is interactive (a fully clear pixel can let a click through). UNVERIFIED in Electron.
 */
const CATCH = fill.catch
/** The ink's casing under the mint: brand ink, faint, the same on every appearance (the screen under it is the learner's). */
const CASING = { stroke: brand.ink, opacity: 0.55, width: 5.4 }

export function CircleLayer({ layout }: { layout: Layout }): ReactNode {
  const state = useCircle((s) => s.state)
  // Gone (the feature switched off, the overlay torn down): the store goes inert and gives the mouse back.
  useEffect(() => layerGone, [])
  return <CircleView state={state} layout={layout} />
}

/** The layer for one state (test/circleStore.test.ts renders it on its own). */
export function CircleView({ state, layout }: { state: CircleState; layout: Layout }): ReactNode {
  const root = useRef<HTMLDivElement>(null)
  useEffect(() => setLayout(layout), [layout])
  const armed = state.k === 'armed'

  // Control + click is a right click on a Mac: no menu while drawing (anywhere in this window).
  useEffect(() => {
    if (!armed) return
    const stop = (e: Event): void => e.preventDefault()
    window.addEventListener('contextmenu', stop, true)
    return () => window.removeEventListener('contextmenu', stop, true)
  }, [armed])

  const at = (e: PointerEvent<HTMLDivElement>): Pt => {
    const r = root.current?.getBoundingClientRect()
    const k = r && r.width ? layout.width / r.width : 1 // the browser stage's CSS scale (1 in Electron)
    return toOverlay(e.clientX, e.clientY, r ?? { left: 0, top: 0 }, k)
  }

  const ink = inkOf(state)
  const first = ink[0]?.[0]
  const inkKey = first ? `${first.x},${first.y}` : 'none'
  const box: Box | undefined = state.k === 'idle' || state.k === 'armed' ? undefined : state.box
  const streamed = shown(state)
  // The card: the final answer, or the words streamed so far. One key per ask, so the final card swaps the text in place.
  const card =
    state.k === 'answered'
      ? { askId: state.askId, box: state.box, question: state.text, title: state.answer.title, body: state.answer.body, streaming: false }
      : state.k === 'asking' && streamed
        ? { askId: state.askId, box: state.box, question: state.text, title: undefined, body: streamed, streaming: !state.stream?.done }
        : undefined

  return (
    // data-theme auto: the chip and the answer card follow Settings > Appearance, like the lesson panel (the overlay root
    // pins the island's dark set). The ink's colours are fixed brand tokens either way.
    <div ref={root} data-theme="auto" data-part="circle" data-circle={state.k} className="pointer-events-none absolute inset-0">
      {armed && (
        <div
          data-part="circle-surface"
          data-grab
          className="pointer-events-auto absolute inset-0 select-none"
          style={{ cursor: 'crosshair', background: CATCH, touchAction: 'none' }}
          onPointerDown={(e) => {
            if (e.button !== 0 && e.button !== 2) return
            e.preventDefault()
            try {
              e.currentTarget.setPointerCapture(e.pointerId)
            } catch {
              // a synthetic event (the stage's script) has no capture to take
            }
            pointerDown(at(e))
          }}
          onPointerMove={(e) => pointerMove(at(e))}
          onPointerUp={() => pointerUp()}
          onPointerCancel={() => pointerUp()}
          onLostPointerCapture={() => pointerUp()}
          onContextMenu={(e) => e.preventDefault()}
        />
      )}
      <AnimatePresence>{ink.length > 0 && <Ink key={inkKey} strokes={ink} width={layout.width} height={layout.height} />}</AnimatePresence>
      <AnimatePresence>{state.k === 'asking' && box && !streamed && <Looking key={state.askId} box={box} area={layout} />}</AnimatePresence>
      <AnimatePresence>{card && <AnswerCard key={card.askId} box={card.box} area={layout} question={card.question} title={card.title} body={card.body} streaming={card.streaming} />}</AnimatePresence>
    </div>
  )
}

function Ink({ strokes, width, height }: { strokes: Pt[][]; width: number; height: number }): ReactNode {
  return (
    <motion.svg
      data-part="circle-ink"
      className="absolute inset-0"
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      initial={{ opacity: 1 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0, transition: { duration: duration.slow, ease: ease.out } }}
      style={{ overflow: 'visible' }}
      aria-hidden
    >
      {strokes.map((s, i) => {
        const d = inkPath(s)
        return (
          <g key={i}>
            <path data-part="circle-casing" d={d} fill="none" stroke={CASING.stroke} strokeWidth={CASING.width} strokeLinecap="round" strokeLinejoin="round" strokeOpacity={CASING.opacity} />
            <path d={d} fill="none" stroke={tone.mint.solid} strokeWidth={3.2} strokeLinecap="round" strokeLinejoin="round" />
          </g>
        )
      })}
    </motion.svg>
  )
}

function Looking({ box, area }: { box: Box; area: { width: number; height: number } }): ReactNode {
  const p = placeCard(box, CHIP, { w: area.width, h: area.height }, 10)
  return (
    <motion.div
      data-ui
      data-part="circle-looking"
      role="status"
      aria-live="polite"
      className="absolute flex items-center justify-center gap-[8px]"
      style={{ left: p.x, top: p.y, width: CHIP.w, height: CHIP.h, borderRadius: radius2.round, background: surface.sheet, boxShadow: `${highlight.top}, inset 0 0 0 1px ${surface.border}, ${elevation.overlay}`, color: color.label, fontSize: type2.xs }}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0, transition: { duration: duration.fast } }}
      transition={{ duration: duration.base, ease: ease.out }}
    >
      <ThinkingDots label={null} />
      Looking
    </motion.div>
  )
}

function AnswerCard({ box, area, question, title, body, streaming }: { box: Box; area: { width: number; height: number }; question: string; title?: string; body: string; streaming: boolean }): ReactNode {
  const ref = useRef<HTMLDivElement>(null)
  const [h, setH] = useState(CARD_H0)
  const reduced = useReducedMotion()
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const measure = (): void => setH(el.offsetHeight || CARD_H0)
    measure()
    const ro = typeof ResizeObserver === 'function' ? new ResizeObserver(measure) : undefined
    ro?.observe(el)
    return () => ro?.disconnect()
  }, [])
  const p = placeCard(box, { w: CARD_W, h }, { w: area.width, h: area.height })
  const from = reduced ? {} : p.side === 'right' ? { x: -8 } : p.side === 'left' ? { x: 8 } : p.side === 'below' ? { y: -8 } : { y: 8 }
  return (
    <motion.div
      ref={ref}
      data-hit
      data-part="circle-answer"
      data-side={p.side}
      data-streaming={streaming ? '' : undefined}
      aria-busy={streaming || undefined}
      role="dialog"
      aria-label={title ?? question}
      className="pointer-events-auto absolute"
      style={{ left: p.x, top: p.y, width: CARD_W, maxHeight: Math.max(120, area.height - 32), overflowY: 'auto', padding: '12px 14px 14px 16px', borderRadius: radius2.chip, background: surface.sheet, boxShadow: `${highlight.top}, inset 0 0 0 1px ${surface.border}, ${elevation.overlay}` }}
      initial={{ opacity: 0, ...from }}
      animate={{ opacity: 1, x: 0, y: 0 }}
      exit={{ opacity: 0, transition: { duration: duration.fast } }}
      transition={{ duration: duration.slow, ease: ease.out }}
    >
      <div className="flex items-start gap-[8px]">
        <div className="min-w-0 flex-1 truncate" style={{ fontSize: type2.xs, lineHeight: '18px', color: color.faint }}>
          {question}
        </div>
        <motion.button
          type="button"
          aria-label="Close"
          className="mg-press grid h-[20px] w-[20px] shrink-0 cursor-pointer place-items-center"
          style={{ borderRadius: radius2.round, background: fill.key, color: fill.keyText }}
          {...pressMotion()}
          onClick={cancelCircle}
        >
          <X size={11} strokeWidth={2.2} />
        </motion.button>
      </div>
      {title && (
        <div className="mt-[4px] font-semibold" style={{ fontSize: type2.sm, lineHeight: '18px', color: color.text }}>
          {title}
        </div>
      )}
      <div className="mt-[4px] whitespace-pre-line" style={{ fontSize: type2.sm, lineHeight: '20px', color: color.label, textWrap: 'pretty' }}>
        {body}
      </div>
    </motion.div>
  )
}

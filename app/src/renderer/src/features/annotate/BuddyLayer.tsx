/**
 * Feature: annotate (buddy draws), the overlay layer. For each mark: ONE thin stroke that grows out of the island's
 * bottom middle along a smooth curve and flows into a loose, hand-drawn loop around the box. Then it holds, and fades
 * (store.ts says when).
 *
 *   - Stroke: the brand mint (the notch glow's family; never green, green means passed) over a faint island-black casing,
 *     so it reads on a light editor and a dark one alike. No glow, no blur, no gradient.
 *   - The branch's root is frozen when a mark is born: a card that grows out of the island afterwards does not drag the
 *     line around. When the island shrinks above it (a card it was born under closed), the root moves up with it.
 *   - Reduced motion: no grow, the finished stroke fades in.
 *   - Click-through always: no data-hit anywhere. The stroke is not data-ui either (that would hide the circled text
 *     from the engine's screen reader); only the small label is, so the engine never reads miyagi's own words as the
 *     learner's screen. Since the text under the label is hidden from the reader too, it sits beside the loop on the
 *     circled line, not over the lines under it (geometry.ts labelSpot).
 *   - Below the island (z 48), so the branch slips out from under it.
 *   - On-screen coach (Nov 24): a mark with text gets ONE text box beside the loop (the step's action, then its keycaps),
 *     instead of the label. It never covers the target or the loop and stays 16 pt inside the display (geometry.ts
 *     textSpot); at most 280 pt wide and 2 lines. data-ui like the label, never data-hit. Neutral: island black, HUD text;
 *     never the pass color (it means passed). The keycaps are the engine's labels in the core Kbd atom.
 */
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import type { Layout } from '../../../../preload/api'
import { isElectron } from '../../bridge'
import { useIslandBox } from '../../core/Island'
import { islandBottom } from '../../core/islandEdge'
import { notchOf } from '../../core/notchGeometry'
import { getFeatures } from '../../core/registry'
import { brand, color, ease, fade as fades, radius2, spring, type2 } from '../../core/theme'
import { Kbd } from '../../core/ui/atoms'
import { buddyPath, drawSeconds, hashSeed, islandAnchor, labelSpot, labelWidth, onOverlay, rootFor, textSpot, toOverlay, TEXT_MAX_W, type Pt, type Rect, type Side } from './geometry'
import { createReach, type DrawMark } from './marks'
import { fade, useAnnotate } from './store'

/** Stroke widths (pt): the line, and the casing under it. */
const STROKE = 2.25
const CASING = 4.5
const CASING_OPACITY = 0.28

/** Browser stage only: `?draw=slow` draws 8 times slower, so a screenshot can catch the stroke mid-grow. */
const SLOW = !isElectron && typeof location !== 'undefined' && new URLSearchParams(location.search).get('draw') === 'slow' ? 8 : 1

type Drawn = { mark: DrawMark; local: Rect; from: Pt }

/**
 * One stroke per mark: when features/buddy's character is in the build (its overlay layer 'buddy'), it flies to each
 * mark and draws the loop itself, and this layer draws nothing (Adrian, Nov 23). Read on first render, not at import:
 * the registry fills in while features load. index.tsx tells that feature this layer yields.
 */
export function BuddyLayer({ layout }: { layout: Layout }): ReactNode {
  const buddyDraws = useMemo(() => getFeatures().some((f) => f.id === 'buddy' && f.overlayLayers?.some((l) => l.id === 'buddy')), [])
  return buddyDraws ? null : <Strokes layout={layout} />
}

function Strokes({ layout }: { layout: Layout }): ReactNode {
  const marks = useAnnotate((s) => s.marks)
  const box = useIslandBox()
  const reduced = useReducedMotion()
  const root = useRef<HTMLDivElement>(null)
  const nm = notchOf(layout)
  const anchorNow = islandAnchor(box.w > 0 && box.h > 0 ? box : undefined, { centerX: nm ? nm.x + nm.width / 2 : layout.width / 2, restBottom: islandBottom(layout) })

  // Each mark's root, frozen at birth (keyed by mark key; dropped with the mark). Frozen against growth only: when the
  // island's bottom moves up past the root (a tall card it was born under went back into the pill), the root follows
  // it up, so a mark that stays the whole step (a text mark) never starts in mid-air below the island.
  const roots = useRef(new Map<string, Pt>())
  const drawn: Drawn[] = []
  const live = new Set<string>()
  for (const mark of marks) {
    const local = toOverlay(mark.rect, layout.origin)
    if (!onOverlay(local, layout)) continue // on another display: the overlay only covers this one
    live.add(mark.key)
    const was = roots.current.get(mark.key)
    const at = rootFor(was, anchorNow)
    if (at !== was) roots.current.set(mark.key, at)
    drawn.push({ mark, local, from: roots.current.get(mark.key)! })
  }
  for (const k of [...roots.current.keys()]) if (!marks.some((m) => m.key === k)) roots.current.delete(k)

  useReachFade(root, layout, drawn)

  return (
    <div ref={root} className="pointer-events-none absolute inset-0" data-part="buddy-draw" aria-hidden>
      <svg width={layout.width} height={layout.height} className="absolute inset-0" style={{ overflow: 'visible' }}>
        <AnimatePresence>
          {drawn.map((d) => (
            <Stroke key={d.mark.key} d={d} reduced={!!reduced} />
          ))}
        </AnimatePresence>
      </svg>
      <AnimatePresence>
        {drawn
          .filter((d) => d.mark.label && !d.mark.text)
          .map((d) => (
            <Label key={d.mark.key} d={d} layout={layout} reduced={!!reduced} />
          ))}
      </AnimatePresence>
      <AnimatePresence>
        {drawn
          .filter((d) => d.mark.text)
          .map((d) => (
            <TextBox key={d.mark.key} d={d} layout={layout} reduced={!!reduced} />
          ))}
      </AnimatePresence>
    </div>
  )
}

function Stroke({ d, reduced }: { d: Drawn; reduced: boolean }): ReactNode {
  const p = useMemo(() => buddyPath(d.from, d.local, hashSeed(d.mark.key)), [d.from, d.local.x, d.local.y, d.local.w, d.local.h, d.mark.key]) // eslint-disable-line react-hooks/exhaustive-deps
  const secs = drawSeconds(p.branchLength + p.loopLength) * SLOW
  const grow = reduced
    ? { initial: { opacity: 0 }, animate: { opacity: 1 }, transition: fades.in }
    : { initial: { pathLength: 0, opacity: 0 }, animate: { pathLength: 1, opacity: 1 }, transition: { pathLength: { duration: secs, ease: ease.out }, opacity: fades.instant } }
  const common = { d: p.d, fill: 'none', strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const }
  return (
    <motion.g data-mark={d.mark.key} data-why={d.mark.why} initial={{ opacity: 1 }} animate={{ opacity: 1 }} exit={{ opacity: 0, transition: fades.slow }}>
      <motion.path {...common} stroke={color.island} strokeOpacity={CASING_OPACITY} strokeWidth={CASING} {...grow} />
      <motion.path {...common} stroke={brand.pastel.mint} strokeWidth={STROKE} {...grow} />
    </motion.g>
  )
}

function Label({ d, layout, reduced }: { d: Drawn; layout: Layout; reduced: boolean }): ReactNode {
  const spot = useMemo(() => labelSpot(buddyPath(d.from, d.local, hashSeed(d.mark.key)).ring, layout, labelWidth(d.mark.label ?? '')), [d, layout])
  const delay = reduced ? 0 : 0.45 * SLOW
  return (
    <motion.span
      data-ui
      className="absolute whitespace-nowrap"
      style={{
        left: spot.x,
        top: spot.y,
        x: spot.align === 'start' ? 0 : spot.align === 'end' ? '-100%' : '-50%',
        padding: '2px 8px',
        borderRadius: radius2.round,
        background: color.island,
        color: color.text,
        fontSize: type2.xs,
        lineHeight: '18px'
      }}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1, transition: { ...fades.in, delay } }}
      exit={{ opacity: 0, transition: fades.out }}
    >
      {d.mark.label}
    </motion.span>
  )
}

/** The text box's look (pt): type, line, padding, the gap to the keycaps. */
const TEXT_LINE = 18
const TEXT_PAD = { x: 10, y: 7 } as const
const TEXT_GAP = 8
const KEY_W = 30

/** A first guess at the box's size (before it is measured): about 7 pt a character, wrapped at TEXT_MAX_W, 2 lines at most. */
function guessSize(text: string, keys: number): { w: number; h: number } {
  const keysW = keys ? keys * KEY_W + TEXT_GAP : 0
  const one = text.length * 7 + keysW + TEXT_PAD.x * 2
  const lines = one > TEXT_MAX_W ? 2 : 1
  return { w: Math.min(TEXT_MAX_W, one), h: lines * TEXT_LINE + TEXT_PAD.y * 2 }
}

/** The way the box comes in: a few points out from the loop, toward where it sits. */
const nudge: Record<Side, { x?: number; y?: number }> = { right: { x: -6 }, left: { x: 6 }, below: { y: -6 }, above: { y: 6 } }

/** The coach's text beside the loop: the step's action, then its keycaps (engine labels in the core Kbd atom). */
function TextBox({ d, layout, reduced }: { d: Drawn; layout: Layout; reduced: boolean }): ReactNode {
  const el = useRef<HTMLDivElement>(null)
  const text = d.mark.text ?? ''
  const keys = d.mark.keys ?? []
  const [size, setSize] = useState(() => guessSize(text, keys.length))
  // Measured before paint (offsetWidth/Height are layout sizes, unscaled by the stage), so it never shows at the guess.
  useLayoutEffect(() => {
    const n = el.current
    if (!n) return
    const w = n.offsetWidth
    const h = n.offsetHeight
    if (w > 0 && h > 0 && (Math.abs(w - size.w) > 0.5 || Math.abs(h - size.h) > 0.5)) setSize({ w, h })
  }, [text, keys.join(' '), size.w, size.h]) // eslint-disable-line react-hooks/exhaustive-deps
  const path = useMemo(() => buddyPath(d.from, d.local, hashSeed(d.mark.key)), [d.from, d.local.x, d.local.y, d.local.w, d.local.h, d.mark.key]) // eslint-disable-line react-hooks/exhaustive-deps
  const spot = textSpot(path.ring, d.local, layout, size, path.branch)
  const delay = reduced ? 0 : 0.45 * SLOW
  const from = reduced ? { opacity: 0 } : { opacity: 0, ...nudge[spot.side] }
  return (
    // Placed by transform from the layer's corner, so its width never shrinks against the right edge while measured.
    <div className="absolute left-0 top-0" style={{ transform: `translate(${spot.x}px, ${spot.y}px)` }}>
      <motion.div
        ref={el}
        data-ui
        data-theme="dark"
        data-part="coach-text"
        data-side={spot.side}
        className="flex items-center"
        style={{
          width: 'max-content',
          maxWidth: TEXT_MAX_W,
          gap: TEXT_GAP,
          padding: `${TEXT_PAD.y}px ${TEXT_PAD.x}px`,
          borderRadius: radius2.card,
          background: color.island,
          color: color.text,
          fontSize: type2.sm,
          lineHeight: `${TEXT_LINE}px`
        }}
        initial={from}
        animate={{ opacity: 1, x: 0, y: 0, transition: reduced ? { ...fades.in, delay } : { opacity: { ...fades.in, delay }, x: { ...spring, delay }, y: { ...spring, delay } } }}
        exit={{ opacity: 0, transition: fades.out }}
      >
        <span className="min-w-0" style={{ display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
          {text}
        </span>
        {keys.length > 0 && (
          <span className="flex shrink-0 items-center gap-1">
            {keys.map((k, i) => (
              <Kbd key={`${i}-${k}`}>{k}</Kbd>
            ))}
          </span>
        )}
      </motion.div>
    </div>
  )
}

/**
 * Fade a mark when the learner goes there: the pointer coming into its box and resting (Electron forwards mouse moves
 * to the click-through overlay, never clicks), or a real click inside (the browser stage). Window coordinates: the
 * stage scales the overlay with CSS, so client points are mapped back through the layer's own box.
 */
function useReachFade(root: React.RefObject<HTMLDivElement | null>, layout: Layout, drawn: Drawn[]): void {
  const boxes = useRef<{ key: string; rect: Rect }[]>([])
  boxes.current = drawn.map((d) => ({ key: d.mark.key, rect: d.local }))
  const reach = useMemo(() => createReach(), [])
  const any = drawn.length > 0
  useEffect(() => {
    if (!any) {
      reach.reset()
      return
    }
    const local = (e: MouseEvent): Pt | undefined => {
      const r = root.current?.getBoundingClientRect()
      if (!r || !r.width) return undefined
      const k = layout.width / r.width
      return { x: (e.clientX - r.left) * k, y: (e.clientY - r.top) * k }
    }
    const move = (e: MouseEvent): void => {
      const p = local(e)
      if (!p) return
      const hit = reach.move(p, boxes.current, Date.now())
      if (hit.length) fade(hit)
    }
    const press = (e: MouseEvent): void => {
      const p = local(e)
      if (!p) return
      const hit = reach.press(p, boxes.current)
      if (hit.length) fade(hit)
    }
    window.addEventListener('mousemove', move)
    window.addEventListener('pointerdown', press, true)
    return () => {
      window.removeEventListener('mousemove', move)
      window.removeEventListener('pointerdown', press, true)
    }
  }, [any, layout.width, reach, root])
}

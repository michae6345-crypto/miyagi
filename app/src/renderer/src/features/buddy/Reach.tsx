/**
 * Feature: buddy, pass 2: the loops the buddy draws. An overlay layer under the island (z 30).
 *
 * The buddy itself is in Pod.tsx: it flies out of the notch and sits beside the first mark. Once it is there
 * (pointing.ts trip 'perched'), this layer draws each mark's loop FROM the buddy's tree: one mint stroke, shaped like
 * a branch (thick at the tree, fine at the tip), that wraps the target once and lets go, so only the loop is left.
 * The loop presses in as it lands, firms up when the learner's pointer comes onto it, and is taken off the way it
 * was put on. The buddy says the first mark's label; a second or third mark gets its name on an island-black chip
 * beside its own loop.
 *
 * One stroke per mark, ever: Michael's features/annotate (michael/app-buddy-draw) draws the same `annotate` event.
 * When that feature is mounted this layer and the pod draw NOTHING and only the bonsai's point pose (the lean) is
 * kept going, so the two can be merged in either order without a mark being circled twice. Which one draws in the
 * end is one line here (STAND_DOWN_FOR).
 *
 * Look: deep mint, the mint of the notch's glow (Adrian's pick from the renders, Nov 22). No glow, no gradient, no
 * arrowhead. Like the spotlight's ring it sits on an ink keyline so it reads over a light app. It never takes a
 * click (no data-hit) and is not reported as our UI, or the engine would stop reading the very thing it points at;
 * only the label chips are (data-ui).
 *
 * Reduced motion: nothing travels. The loops and the labels fade in and out in place.
 */
import { animate, AnimatePresence, motion, useMotionValue, usePresence, useReducedMotion, useTransform } from 'motion/react'
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode, type RefObject } from 'react'
import type { Layout } from '../../../../preload/api'
import { overlapShare, toLocal, type Point, type Rect } from '../../core/geometry'
import { islandTop } from '../../core/islandEdge'
import { notchOf } from '../../core/notchGeometry'
import { getFeatures } from '../../core/registry'
import { color, pill, radius, shadows, text } from '../../core/theme'
import { ease, fade as fades, spring } from '../../core/ui/motion'
import { createReach, DRAW, drawTime, labelAt, reach, ribbon, type Reach, type Shown } from './marks'
import { reached, usePointing } from './pointing'

/**
 * The stroke's mint: the mint of the notch's glow (hud.notchGlow, rgb 150 228 200), deeper than brand.pastel.mint so
 * it holds up over a light app. Not the pass green. It has no theme token yet (brief, Core requests).
 */
export const MINT = '#96E4C8'
/** The ink keyline under the stroke, so it reads over a light app: this much wider than the stroke, this opaque. */
const KEYLINE = { wider: 2.8, opacity: 0.5 } as const
/**
 * The stroke's full width (px): where it leaves the tree, where it meets the loop, and round the loop.
 *   press  the loop swells by this share for a moment as it lands, like a pen pressed down
 *   near   and is this much wider (px) while the learner's pointer is on the mark: it knows they are there
 */
const WIDTH = { root: 3.4, join: 2.1, loop: 2.1, press: 0.45, near: 0.9 } as const
/** Over how many px the stroke comes to a point at its head and at its tail. */
const ENDS = { head: 26, tail: 34 } as const
/** The landing press: how long it takes (seconds). */
const PRESS_S = 0.34
/** How far off its upright the bonsai leans toward a mark this many px to its side (LivingMark's lean, -1 to 1). */
const LEAN_REACH = 520
/** At least this share of a mark must be on this display to draw it here (the rest is another display's). Same as features/annotate. */
const MIN_ON_SCREEN = 0.5
/** The feature that also draws `annotate`. While it is mounted, the buddy's layers draw nothing. */
const STAND_DOWN_FOR = 'annotate'

/** Michael's layer is mounted: the buddy's own layers stand down. Read on first render, not at import: the registry fills in while features load. */
export function useStandDown(): boolean {
  return useMemo(() => getFeatures().some((f) => f.id === STAND_DOWN_FOR), [])
}

/**
 * The marks in this window's coordinates, and only the ones really on this display. Engine marks are screen points
 * from the primary display's top-left, like spotlight.rect.
 */
export function useHere(marks: Shown[], layout: Layout): Shown[] {
  const { x: ox, y: oy } = layout.origin
  return useMemo(() => {
    const screen = { x: 0, y: 0, w: layout.width, h: layout.height }
    return marks.map((m) => ({ ...m, rect: toLocal(m.rect, { x: ox, y: oy }) })).filter((m) => overlapShare(m.rect, screen) >= MIN_ON_SCREEN)
  }, [marks, ox, oy, layout.width, layout.height])
}

/** A mark, its stroke, and how long after the buddy lands its stroke starts (seconds). */
type Drawn = { mark: Shown; r: Reach; delay: number }

export function ReachLayer({ layout }: { layout: Layout }): ReactNode {
  const marks = usePointing((s) => s.marks)
  const pose = usePointing((s) => s.pose)
  const trip = usePointing((s) => s.trip)
  const el = useRef<HTMLDivElement>(null)
  const reduced = useReducedMotion() ?? false
  const standDown = useStandDown()
  const here = useHere(marks, layout)
  const home = useBonsaiPoint(el, layout, here.length > 0 || !!pose)
  // The buddy draws once it is sitting beside the first mark, from where its tree is then: it goes there first, then
  // circles. A stroke keeps the start it was born with, so when the buddy hops on to the next mark the loops it
  // already drew stay as they are.
  const births = useRef(new Map<string, { from: Point; heading: Point; delay: number }>())
  const tree = trip.phase === 'perched' && trip.at === here[0]?.key ? trip.tree : undefined
  const tx = tree?.x
  const ty = tree?.y
  const drawn = useMemo(() => {
    const live = new Set(here.map((m) => m.key))
    for (const k of [...births.current.keys()]) if (!live.has(k)) births.current.delete(k)
    const screen = { x: 0, y: 0, w: layout.width, h: layout.height }
    const out: Drawn[] = []
    let born = 0
    for (const mark of here) {
      let b = births.current.get(mark.key)
      if (!b) {
        if (tx === undefined || ty === undefined) continue
        // It throws each loop from its tree toward the mark, one a beat after the other.
        b = { from: { x: tx, y: ty }, heading: { x: mark.rect.x + mark.rect.w / 2 - tx, y: mark.rect.y + mark.rect.h / 2 - ty }, delay: born++ * DRAW.stagger }
        births.current.set(mark.key, b)
      }
      out.push({ mark, r: reach(b.from, mark.rect, mark.key, b.heading, screen), delay: b.delay })
    }
    return out
  }, [here, tx, ty, layout.width, layout.height])

  // The point pose of the tree at home: it leans toward the first mark, or toward the box another layer asked for
  // (pointAt). The buddy's own lean while it is out is the pod's business.
  const { x: ox, y: oy } = layout.origin
  const first = here[0]?.rect ?? (pose && toLocal(pose, { x: ox, y: oy }))
  const lean = first ? Math.round(Math.max(-1, Math.min(1, (first.x + first.w / 2 - home.x) / LEAN_REACH)) * 20) / 20 : 0
  useEffect(() => {
    if (usePointing.getState().lean !== lean) usePointing.setState({ lean })
  }, [lean])

  const near = usePointer(el, here)

  const wa = layout.workArea
  const bounds = { x: wa.x, y: wa.y, w: wa.width, h: wa.height }
  const show = standDown ? [] : drawn
  return (
    <div ref={el} className="pointer-events-none absolute inset-0" data-buddy-reach={show.length || undefined} data-stand-down={standDown || undefined}>
      <svg className="absolute inset-0 h-full w-full" style={{ overflow: 'visible' }} aria-hidden>
        <AnimatePresence>
          {show.map((d) => (
            <Stroke key={d.mark.key} {...d} near={near === d.mark.key} reduced={reduced} />
          ))}
        </AnimatePresence>
      </svg>
      {/* The buddy says the first mark's label itself (Pod.tsx); the others get a chip until it comes over to them. */}
      <AnimatePresence>{show.map(({ mark, r, delay }) => mark.key !== here[0]?.key && mark.label && <Label key={mark.key} label={mark.label} r={r} delay={delay} bounds={bounds} reduced={reduced} />)}</AnimatePresence>
    </div>
  )
}

/**
 * One stroke. Its outline is rebuilt each frame from a few numbers (marks.ts ribbon): how far its head and its tail
 * have got, how hard it is pressed, and whether the pointer is on it. So it has a fine tip while it grows, and its
 * tail can run after its head. Four fills: the branch and the loop, each over its keyline.
 */
function Stroke({ mark, r, delay, near, reduced }: Drawn & { near: boolean; reduced: boolean }): ReactNode {
  const [present, safeToRemove] = usePresence()
  // These run 0 to 1 and are turned into shares of THIS render's stroke below, so a stroke whose start or target
  // moved still ends exactly where its loop begins.
  /** How far the head has got along the stroke. */
  const head = useMotionValue(reduced ? 1 : 0)
  /** How far the tail has followed the head toward the start of the loop. */
  const follow = useMotionValue(reduced ? 1 : 0)
  /** Leaving: how far the tail has run on from there up to the head. */
  const eat = useMotionValue(0)
  /** The landing: 0 until the head arrives, then to 1; the press is the hump in between. */
  const landed = useMotionValue(reduced ? 1 : 0)
  /** 1 while the learner's pointer is on the mark. */
  const held = useMotionValue(0)
  const alpha = useMotionValue(reduced ? 0 : 1)

  useEffect(() => {
    if (!present) {
      // Leaving: it fades while its tail runs up to its head, so the loop is taken off the way it was put on.
      const go = reduced ? fades.out : { duration: DRAW.leave, ease: ease.out }
      const runs = [animate(alpha, 0, go), ...(reduced ? [] : [animate(eat, 1, go)])]
      void runs[0].then(() => safeToRemove?.())
      return () => runs.forEach((x) => x.stop())
    }
    if (reduced) {
      const run = animate(alpha, 1, fades.in)
      return () => run.stop()
    }
    const t = drawTime(r.length)
    const runs = [
      animate(head, 1, { duration: t, ease: ease.out, delay }),
      animate(landed, 1, { duration: PRESS_S, ease: ease.out, delay: delay + t * 0.92 }),
      // The tail sets off when the head is well on its way and arrives a moment after it.
      animate(follow, 1, { duration: t * 0.75, ease: ease.inOut, delay: delay + t * 0.4 })
    ]
    return () => runs.forEach((x) => x.stop())
    // Once per arrival and once per leaving: a mark that only moved keeps its stroke where it has got to.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [present])

  useEffect(() => {
    if (reduced) return held.jump(near ? 1 : 0)
    const run = animate(held, near ? 1 : 0, spring)
    return () => run.stop()
  }, [near, reduced, held])

  /** [head, follow, eat, landed, held] → the outline of one part of the stroke, `wider` px wider than the stroke. */
  const outline =
    (wider: number, part: readonly [number, number]) =>
    ([h, f, e, l, n]: number[]): string => {
      const from = f * r.split
      const press = 1 + WIDTH.press * Math.sin(Math.PI * l)
      const width = (t: number): number => {
        if (t >= r.split) return WIDTH.loop * press + WIDTH.near * n + wider
        const k = r.split > 0 ? t / r.split : 1
        return WIDTH.root + (WIDTH.join - WIDTH.root) * (k * k * (3 - 2 * k)) + wider
      }
      return ribbon(r, width, [from + (h - from) * e, h], ENDS, part)
    }
  const state = [head, follow, eat, landed, held]
  const arm = useTransform(state, outline(0, [0, r.split]))
  const loop = useTransform(state, outline(0, [r.split, 1]))
  const armKey = useTransform(state, outline(KEYLINE.wider, [0, r.split]))
  const loopKey = useTransform(state, outline(KEYLINE.wider, [r.split, 1]))
  return (
    <motion.g data-part="branch" data-why={mark.why} data-mark={mark.key} data-near={near || undefined} style={{ opacity: alpha }}>
      <motion.path data-part="keyline" d={armKey} style={{ fill: color.onAccent, opacity: KEYLINE.opacity }} />
      <motion.path data-part="keyline" d={loopKey} style={{ fill: color.onAccent, opacity: KEYLINE.opacity }} />
      <motion.path data-part="arm" d={arm} style={{ fill: MINT }} />
      <motion.path data-part="bark" d={loop} style={{ fill: MINT }} />
    </motion.g>
  )
}

/** A later mark's name: a chip on the island's black, like the spotlight's caption, beside its loop. */
function Label({ label, r, delay: start, bounds, reduced }: { label: string; r: Reach; delay: number; bounds: Rect; reduced: boolean }): ReactNode {
  const ref = useRef<HTMLDivElement>(null)
  const [size, setSize] = useState({ w: 96, h: 26 })
  useLayoutEffect(() => {
    const node = ref.current
    if (!node) return
    const measure = (): void => setSize((s) => (s.w === node.offsetWidth && s.h === node.offsetHeight ? s : { w: node.offsetWidth, h: node.offsetHeight }))
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(node)
    return () => ro.disconnect()
  }, [])
  // To the right, on the circled line, like the spotlight's caption.
  const at = labelAt(r.ring, size, bounds, 'right')
  // It arrives as the loop closes, from the loop's side.
  const delay = reduced ? 0 : start + drawTime(r.length) * 0.6
  const slide = reduced ? 0 : at.side === 'right' ? -8 : at.side === 'left' ? 8 : 0
  const rise = reduced ? 0 : at.side === 'below' ? -8 : at.side === 'above' ? 8 : 0
  return (
    <motion.div
      ref={ref}
      data-ui
      data-part="mark-label"
      data-side={at.side}
      className="absolute left-0 top-0 whitespace-nowrap px-[11px] py-[4px] font-medium leading-[18px]"
      style={{ borderRadius: radius.chip, background: color.island, boxShadow: shadows.card, fontSize: text.xs, color: color.text }}
      initial={{ opacity: 0, x: at.x + slide, y: at.y + rise }}
      animate={{ opacity: 1, x: at.x, y: at.y, transition: reduced ? fades.in : { ...spring, delay, opacity: { ...fades.in, delay } } }}
      exit={{ opacity: 0, transition: fades.out }}
    >
      {label}
    </motion.div>
  )
}

/** The overlay root a layer sits in, and the scale that undoes the browser stage's CSS scale (1 in Electron). */
export function frame(el: HTMLElement | null): { root: HTMLElement; box: DOMRect; k: number } | undefined {
  const root = el?.parentElement
  const box = root?.getBoundingClientRect()
  return root && box && box.width ? { root, box, k: root.offsetWidth / box.width } : undefined
}

/** Where the bonsai is when the DOM can't say: inside the notch's left end, or the left of the pill below the menu bar. */
function restingBonsai(layout: Layout): Point {
  const n = notchOf(layout)
  return n ? { x: n.x + 14, y: n.height / 2 } : { x: layout.width / 2 - 40, y: islandTop(layout) + pill.height / 2 }
}

/**
 * Where the living mark is right now, in the overlay window's coordinates: the bonsai in the island's left ear when
 * the ears are out (`ear` true: there is a tree to see there), else the left of whatever the island is showing, else
 * restingBonsai. `el`: any element that is a direct child of the overlay root (a layer's own root).
 */
export function bonsaiPoint(el: HTMLElement | null, layout: Layout): Point & { ear: boolean } {
  const fr = frame(el)
  if (fr) {
    const at = (r: DOMRect, dx: number, dy: number): Point => ({ x: (r.left - fr.box.left) * fr.k + dx, y: (r.top - fr.box.top) * fr.k + dy })
    const ear = fr.root.querySelector<HTMLElement>('[data-ears] > span')?.getBoundingClientRect()
    if (ear && ear.width > 0) return { ...at(ear, (ear.width * fr.k) / 2, (ear.height * fr.k) / 2), ear: true }
    const shown = fr.root.querySelector<HTMLElement>('[data-island-layer]')?.getBoundingClientRect()
    if (shown && shown.width > 0 && !notchOf(layout)) return { ...at(shown, Math.min(17, (shown.width * fr.k) / 2), Math.min(17, (shown.height * fr.k) / 2)), ear: false }
  }
  return { ...restingBonsai(layout), ear: false }
}

/**
 * bonsaiPoint as state: read from the DOM (the island moves and morphs) while `on`; the point changes only when it
 * really moved. This is the buddy's home, where its trips start and end.
 * Exported for a layer that draws its own stroke and wants it to start from the bonsai (Michael's features/annotate).
 */
export function useBonsaiPoint(el: RefObject<HTMLElement | null>, layout: Layout, on: boolean): Point {
  const [p, setP] = useState<Point>(() => restingBonsai(layout))
  useLayoutEffect(() => {
    if (!on) return
    const read = (): void => {
      const next = bonsaiPoint(el.current, layout)
      setP((prev) => (Math.abs(prev.x - next.x) < 1 && Math.abs(prev.y - next.y) < 1 ? prev : { x: next.x, y: next.y }))
    }
    read()
    const id = setInterval(read, 250)
    return () => clearInterval(id)
  }, [on, el, layout])
  return p
}

/** How often a resting pointer is checked against the marks (ms): moves stop arriving once it rests. */
const REST_TICK = 70

/**
 * The learner's pointer and the marks (marks.ts createReach): coming onto a mark's box from outside and resting
 * there fades that mark; so does a press inside it. In Electron the click-through overlay never sees the press, so
 * there the rest is what counts. Runs even while this layer stands down, so the pose ends when the mark does.
 * Returns the key of the mark the pointer is on now, so its loop can answer at once, before the rest is up.
 */
function usePointer(el: RefObject<HTMLElement | null>, here: Shown[]): string | undefined {
  const boxes = useRef<{ key: string; rect: Rect }[]>([])
  boxes.current = here.map((m) => ({ key: m.key, rect: m.rect }))
  const on = here.length > 0
  const [near, setNear] = useState<string>()
  useEffect(() => {
    if (!on) return setNear(undefined)
    const tracker = createReach()
    let last: Point | undefined
    const local = (e: MouseEvent): Point | undefined => {
      const fr = frame(el.current)
      return fr ? { x: (e.clientX - fr.box.left) * fr.k, y: (e.clientY - fr.box.top) * fr.k } : undefined
    }
    const check = (): void => {
      if (!last) return
      setNear(tracker.press(last, boxes.current)[0])
      reached(tracker.move(last, boxes.current, Date.now()))
    }
    const move = (e: MouseEvent): void => {
      last = local(e)
      check()
    }
    const down = (e: MouseEvent): void => {
      const p = local(e)
      if (p) reached(tracker.press(p, boxes.current))
    }
    const id = setInterval(check, REST_TICK)
    window.addEventListener('mousemove', move)
    window.addEventListener('mousedown', down, true)
    return () => {
      clearInterval(id)
      window.removeEventListener('mousemove', move)
      window.removeEventListener('mousedown', down, true)
    }
  }, [on, el])
  return near
}

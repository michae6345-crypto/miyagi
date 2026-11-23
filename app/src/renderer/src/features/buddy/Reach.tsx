/**
 * Feature: buddy, pass 2: the pointing branch, drawn. An overlay layer under the island (z 30), so the branch comes
 * out from behind the notch.
 *
 * For each mark (pointing.ts): one mint stroke leaves the bonsai in the notch, flies to the mark and wraps once round
 * it (marks.ts reach). It is shaped like a branch, thick at the tree and fine at the tip, and its tail follows its
 * head in, so once it has landed only the loop is left around the target: no line stays across the screen. The
 * loop presses in as it lands, firms up when the learner's pointer comes onto it, and is taken off the way it was
 * put on. The mark's short name sits on an island-black chip to its right, on the circled line. Several marks fork
 * off one branch.
 *
 * One stroke per mark, ever: Michael's features/annotate (michael/app-buddy-draw) draws the same `annotate` event.
 * When that feature is mounted this layer draws NOTHING and only keeps the bonsai's point pose (the lean) going, so
 * the two can be merged in either order without a mark being circled twice. Which one draws in the end is one line
 * here (STAND_DOWN_FOR).
 *
 * Look: mint, the color Michael chose for the buddy's stroke and Adrian picked from the renders (Nov 22). No glow,
 * no gradient, no arrowhead. Like the spotlight's ring it sits on an ink keyline so it reads over a light app.
 * It never takes a click (no data-hit) and is not reported as our UI, or the engine would stop reading the very
 * thing it points at; only the label chip is (data-ui).
 *
 * Reduced motion: nothing travels. The loop and the label fade in and out in place.
 */
import { animate, AnimatePresence, motion, useMotionValue, usePresence, useReducedMotion, useTransform } from 'motion/react'
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode, type RefObject } from 'react'
import type { Layout } from '../../../../preload/api'
import { overlapShare, toLocal, type Point, type Rect } from '../../core/geometry'
import { islandTop } from '../../core/islandEdge'
import { notchOf } from '../../core/notchGeometry'
import { getFeatures } from '../../core/registry'
import { brand, color, pill, radius, shadows, text } from '../../core/theme'
import { ease, fade as fades, spring } from '../../core/ui/motion'
import { createReach, DRAW, drawTime, forkFor, labelAt, reach, ribbon, timeToDraw, type Reach, type Shown } from './marks'
import { fade, usePointing } from './pointing'

/**
 * The stroke's mint. `pale` is brand.pastel.mint, what features/annotate uses. `deep` is the mint of the notch's glow
 * (hud.notchGlow, rgb 150 228 200): more color, so it holds up better over a light app. Neither is the pass green.
 * Which one is still Adrian's to pick: ?mint=pale or ?mint=deep in the browser stage. `deep` has no theme token yet
 * (brief, Core requests).
 */
const MINT = { pale: brand.pastel.mint, deep: '#96E4C8' } as const
const STROKE_COLOR = typeof location !== 'undefined' && new URLSearchParams(location.search).get('mint') === 'pale' ? MINT.pale : MINT.deep
/** The ink keyline under the stroke, so it reads over a light app: this much wider than the stroke, this opaque. */
const KEYLINE = { wider: 2.8, opacity: 0.5 } as const
/**
 * The stroke's full width (px): at the bonsai, where the branch meets the loop, and round the loop. A branch thins
 * as it goes.
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
/** The feature that also draws `annotate`. While it is mounted, this layer draws nothing. */
const STAND_DOWN_FOR = 'annotate'

/** A mark, its stroke, and how long after the marks arrive its stroke starts (seconds). */
type Drawn = { mark: Shown; r: Reach; delay: number }

export function ReachLayer({ layout }: { layout: Layout }): ReactNode {
  const marks = usePointing((s) => s.marks)
  const pose = usePointing((s) => s.pose)
  const el = useRef<HTMLDivElement>(null)
  const reduced = useReducedMotion() ?? false
  // Read when the layer first renders, not at import: the registry is still filling in while features load.
  const standDown = useMemo(() => getFeatures().some((f) => f.id === STAND_DOWN_FOR), [])
  const { x: ox, y: oy } = layout.origin
  // Engine marks are screen points from the primary display's top-left, like spotlight.rect. Draw only what is
  // really on this display.
  const here = useMemo(() => {
    const screen = { x: 0, y: 0, w: layout.width, h: layout.height }
    return marks.map((m) => ({ ...m, rect: toLocal(m.rect, { x: ox, y: oy }) })).filter((m) => overlapShare(m.rect, screen) >= MIN_ON_SCREEN)
  }, [marks, ox, oy, layout.width, layout.height])
  const from = useBonsaiPoint(el, layout, here.length > 0 || !!pose)
  // The first mark's branch is the trunk. A later mark forks off it where it can (starting as the trunk's stroke
  // passes that point), so several marks read as one branch; a mark behind the trunk gets its own, a beat later.
  const drawn = useMemo(() => {
    const screen = { x: 0, y: 0, w: layout.width, h: layout.height }
    const out: Drawn[] = []
    here.forEach((mark, i) => {
      const trunk = out[0]
      const fork = trunk && forkFor(trunk.r, mark.rect)
      if (trunk && fork) out.push({ mark, r: reach(fork.at, mark.rect, mark.key, fork.heading, screen), delay: trunk.delay + drawTime(trunk.r.length) * timeToDraw(fork.t * trunk.r.split) })
      else out.push({ mark, r: reach(from, mark.rect, mark.key, undefined, screen), delay: i * DRAW.stagger })
    })
    return out
  }, [here, from, layout.width, layout.height])

  // The point pose: the tree leans toward the first mark, or toward the box another layer asked for (pointAt).
  const first = here[0]?.rect ?? (pose && toLocal(pose, { x: ox, y: oy }))
  const lean = first ? Math.round(Math.max(-1, Math.min(1, (first.x + first.w / 2 - from.x) / LEAN_REACH)) * 20) / 20 : 0
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
      <AnimatePresence>{show.map(({ mark, r, delay }) => mark.label && <Label key={mark.key} label={mark.label} r={r} delay={delay} bounds={bounds} reduced={reduced} />)}</AnimatePresence>
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
  // moved (the bonsai is found a frame after the first render) still ends exactly where its loop begins.
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
      <motion.path data-part="arm" d={arm} style={{ fill: STROKE_COLOR }} />
      <motion.path data-part="bark" d={loop} style={{ fill: STROKE_COLOR }} />
    </motion.g>
  )
}

/** The mark's name: a chip on the island's black, like the spotlight's caption, beside the loop. */
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
  // To the right, on the circled line, like the spotlight's caption: the branch is gone by the time it shows.
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

/** The overlay root this layer sits in, and the scale that undoes the browser stage's CSS scale (1 in Electron). */
function frame(el: HTMLElement | null): { root: HTMLElement; box: DOMRect; k: number } | undefined {
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
 * Where the living mark is, in the overlay window's coordinates: the bonsai in the island's left ear when the ears
 * are out, else the left of whatever the island is showing, else restingBonsai. This is where a branch starts.
 * `el`: any element that is a direct child of the overlay root (a layer's own root). Read from the DOM (the island
 * moves and morphs) while `on`; the point changes only when it really moved.
 * Exported for a layer that draws its own stroke and wants it to start from the bonsai (Michael's features/annotate).
 */
export function useBonsaiPoint(el: RefObject<HTMLElement | null>, layout: Layout, on: boolean): Point {
  const [p, setP] = useState<Point>(() => restingBonsai(layout))
  useLayoutEffect(() => {
    if (!on) return
    const read = (): void => {
      const fr = frame(el.current)
      let next = restingBonsai(layout)
      if (fr) {
        const at = (r: DOMRect, dx: number, dy: number): Point => ({ x: (r.left - fr.box.left) * fr.k + dx, y: (r.top - fr.box.top) * fr.k + dy })
        const ear = fr.root.querySelector<HTMLElement>('[data-ears] > span')?.getBoundingClientRect()
        const shown = fr.root.querySelector<HTMLElement>('[data-island-layer]')?.getBoundingClientRect()
        if (ear && ear.width > 0) next = at(ear, (ear.width * fr.k) / 2, (ear.height * fr.k) / 2)
        else if (shown && shown.width > 0 && !notchOf(layout)) next = at(shown, Math.min(17, (shown.width * fr.k) / 2), Math.min(17, (shown.height * fr.k) / 2))
      }
      setP((prev) => (Math.abs(prev.x - next.x) < 1 && Math.abs(prev.y - next.y) < 1 ? prev : next))
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
      const hit = tracker.move(last, boxes.current, Date.now())
      if (hit.length) fade(hit)
    }
    const move = (e: MouseEvent): void => {
      last = local(e)
      check()
    }
    const down = (e: MouseEvent): void => {
      const p = local(e)
      const hit = p ? tracker.press(p, boxes.current) : []
      if (hit.length) fade(hit)
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

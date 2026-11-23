/**
 * Feature: buddy, pass 2: the pointing branch, drawn. An overlay layer under the island (z 30), so the branch comes
 * out from behind the notch.
 *
 * For each mark (pointing.ts): one stroke in the bonsai's bark, from the bonsai in the notch to the mark and once
 * round it (marks.ts reach), drawn on in one motion; then the mark's short name on an island-black chip beside it.
 * Leaving, the stroke runs back into the notch, quicker than it came. Several marks fork off one branch.
 *
 * One stroke per mark, ever: Michael's features/annotate (michael/app-buddy-draw) draws the same `annotate` event.
 * When that feature is mounted this layer draws NOTHING and only keeps the bonsai's point pose (the lean) going, so
 * the two can be merged in either order without a mark being circled twice. Which one draws in the end is one line
 * here (STAND_DOWN_FOR).
 *
 * Look (app/brand/BRAND.md): the stroke is the tree's own branch, so it is bark and nothing else: no glow, no
 * gradient, no arrowhead. Like the spotlight's ring it sits on a faint ink keyline so it reads over a light app.
 * It never takes a click (no data-hit) and is not reported as our UI, or the engine would stop reading the very
 * thing it points at; only the label chip is (data-ui).
 *
 * Reduced motion: nothing travels. The stroke and the label fade in and out in place.
 */
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode, type RefObject } from 'react'
import type { Layout } from '../../../../preload/api'
import { overlapShare, toLocal, type Point, type Rect } from '../../core/geometry'
import { islandTop } from '../../core/islandEdge'
import { notchOf } from '../../core/notchGeometry'
import { getFeatures } from '../../core/registry'
import { color, pill, radius, shadows, text } from '../../core/theme'
import { ease, fade as fades, spring } from '../../core/ui/motion'
import { createReach, DRAW, drawTime, forkFor, labelAt, reach, timeToDraw, type Reach, type Shown } from './marks'
import { fade, usePointing } from './pointing'

/**
 * The brand kit's Bark on dark (BRAND.md: "#A07A5C on dark"), the color of the trunk in the dark cut of the mark. The
 * overlay is always the dark HUD. There is no theme token for it yet (brief, Core requests).
 */
const BARK = '#A07A5C'
const STROKE = { width: 2.25, keyline: 4.75, keylineOpacity: 0.35 } as const
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

  usePointer(el, here)

  const wa = layout.workArea
  const bounds = { x: wa.x, y: wa.y, w: wa.width, h: wa.height }
  const show = standDown ? [] : drawn
  return (
    <div ref={el} className="pointer-events-none absolute inset-0" data-buddy-reach={show.length || undefined} data-stand-down={standDown || undefined}>
      <svg className="absolute inset-0 h-full w-full" style={{ overflow: 'visible' }} aria-hidden>
        <AnimatePresence>
          {show.map((d) => (
            <Branch key={d.mark.key} {...d} reduced={reduced} />
          ))}
        </AnimatePresence>
      </svg>
      <AnimatePresence>{show.map(({ mark, r, delay }) => mark.label && <Label key={mark.key} label={mark.label} r={r} delay={delay} bounds={bounds} reduced={reduced} />)}</AnimatePresence>
    </div>
  )
}

/** One stroke: the keyline and the bark on the same path, drawn on together. */
function Branch({ mark, r, delay, reduced }: Drawn & { reduced: boolean }): ReactNode {
  const come = reduced ? fades.in : { duration: drawTime(r.length), ease: ease.out, delay }
  const go = reduced ? fades.out : { duration: DRAW.leave, ease: ease.out }
  const path = (width: number, style: CSSProperties, part: string): ReactNode => (
    <motion.path
      d={r.d}
      data-part={part}
      fill="none"
      strokeWidth={width}
      strokeLinecap="round"
      strokeLinejoin="round"
      style={style}
      initial={{ pathLength: reduced ? 1 : 0 }}
      animate={{ pathLength: 1, transition: come }}
      exit={{ pathLength: reduced ? 1 : 0, transition: go }}
    />
  )
  return (
    // Leaving, it fades as it runs back, so a fork never hangs in the air after its trunk has passed it.
    <motion.g data-part="branch" data-why={mark.why} data-mark={mark.key} initial={{ opacity: reduced ? 0 : 1 }} animate={{ opacity: 1, transition: fades.in }} exit={{ opacity: 0, transition: go }}>
      {path(STROKE.keyline, { stroke: color.onAccent, strokeOpacity: STROKE.keylineOpacity }, 'keyline')}
      {path(STROKE.width, { stroke: BARK }, 'bark')}
    </motion.g>
  )
}

/** The mark's name: a chip on the island's black, like the spotlight's caption, beside the loop and away from the branch. */
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
  // Away from where its branch comes from (the bonsai, or the fork it left the trunk at).
  const at = labelAt(r.ring, size, bounds, r.curve[0].x > r.ring.x + r.ring.w / 2 ? 'left' : 'right')
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
 */
function usePointer(el: RefObject<HTMLElement | null>, here: Shown[]): void {
  const boxes = useRef<{ key: string; rect: Rect }[]>([])
  boxes.current = here.map((m) => ({ key: m.key, rect: m.rect }))
  const on = here.length > 0
  useEffect(() => {
    if (!on) return
    const tracker = createReach()
    let last: Point | undefined
    const local = (e: MouseEvent): Point | undefined => {
      const fr = frame(el.current)
      return fr ? { x: (e.clientX - fr.box.left) * fr.k, y: (e.clientY - fr.box.top) * fr.k } : undefined
    }
    const check = (): void => {
      if (!last) return
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
}

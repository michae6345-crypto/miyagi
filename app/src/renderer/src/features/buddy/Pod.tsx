/**
 * Feature: buddy. The buddy itself, out on the screen. An overlay layer over the island (z 55).
 *
 * The buddy is a character with a home, not a highlighter. When the coach points at something:
 *   1. The bonsai leaves the notch in a small island-black pod (a droplet of the island, so it reads on any app) and
 *      flies to the thing on an arc, leaning into the flight and growing from the ear's size to its own.
 *   2. It lands beside the thing with a little squash, leans toward it, and draws the mint loop round it (Reach.tsx
 *      draws that, from where the tree now is).
 *   3. The pod opens and the buddy says the mark's label, one letter at a time.
 *   4. It is alive while it waits: it sways while the engine thinks, blooms when a step passes (store.tsx), and
 *      turns to look at the learner's pointer when it comes near.
 *   5. When the learner gets there it hops. When the next mark comes it hops over to it. When there is nothing
 *      left to point at it flies home, shrinks back into the notch, and the ear's tree is there again.
 * Trips, perches and speech timing are pure and in trip.ts.
 *
 * While it is away its place in the ear is empty: a patch of island black covers the ear's own mark (core draws
 * that one; when the ear uses <Buddy /> it hides itself and the patch can go: brief, Core requests).
 *
 * It never takes a click (no data-hit). The pod is data-ui, so the engine never reads the buddy's words as the
 * learner's screen; it sits beside the thing, not on it.
 *
 * Reduced motion: no flight. The pod fades in where it would have landed, with its words whole, and fades out.
 * Stands down with the loops when features/annotate is mounted (Reach.tsx).
 */
import { animate, motion, useMotionValue, useReducedMotion, useTransform } from 'motion/react'
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import type { Layout } from '../../../../preload/api'
import type { Point } from '../../core/geometry'
import { color, shadows, text } from '../../core/theme'
import { ease, fade as fades, spring } from '../../core/ui/motion'
import { LivingMark } from './LivingMark'
import { ringBox } from './marks'
import { setTrip, usePointing } from './pointing'
import { bonsaiPoint, frame, useHere, useStandDown } from './Reach'
import { useBuddy } from './store'
import { along, flight, leanToward, NOTICE_PX, perch, POD, podWidth, said, scaleAt, tiltAt } from './trip'

/** Landing: it squashes this much (wider, shorter) and springs back. The hop when the learner gets there: this high, this long. */
const SQUASH = { wide: 0.07, short: 0.12 } as const
const HOP = { px: 9, seconds: 0.34 } as const
/** Going home it waits for the loop to come off; a little longer when it has a hop to finish. */
const LEAVE_MS = { plain: 140, afterHop: 380 } as const
/** The patch over the ear's mark while the buddy is away: the mark is 16 px. */
const COVER = 20

export function PodLayer({ layout }: { layout: Layout }): ReactNode {
  const marks = usePointing((s) => s.marks)
  const trip = usePointing((s) => s.trip)
  const cheer = usePointing((s) => s.cheer)
  const { state, bloom } = useBuddy()
  const el = useRef<HTMLDivElement>(null)
  const reduced = useReducedMotion() ?? false
  const standDown = useStandDown()
  const here = useHere(marks, layout)
  const first = standDown ? undefined : here[0]
  const key = first?.key
  const label = first?.label

  // The words' width, measured in a layout effect, so the perch is planned with it before the flight starts.
  const ruler = useRef<HTMLSpanElement>(null)
  const [textW, setTextW] = useState(0)
  useLayoutEffect(() => {
    setTextW(label && ruler.current ? Math.ceil(ruler.current.offsetWidth) : 0)
  }, [label])

  const wa = layout.workArea
  const rx = first?.rect.x
  const ry = first?.rect.y
  const rw = first?.rect.w
  const rh = first?.rect.h
  const spot = useMemo(() => {
    if (rx === undefined || ry === undefined || rw === undefined || rh === undefined) return undefined
    const ring = ringBox({ x: rx, y: ry, w: rw, h: rh }, { x: 0, y: 0, w: layout.width, h: layout.height })
    return { ...perch(ring, textW, { x: wa.x, y: wa.y, w: wa.width, h: wa.height }), ring }
  }, [rx, ry, rw, rh, textW, layout.width, layout.height, wa.x, wa.y, wa.width, wa.height])
  const tx = spot?.tree.x
  const ty = spot?.tree.y

  /** Where the tree is, in this window's coordinates. */
  const x = useMotionValue(0)
  const y = useMotionValue(0)
  const scale = useMotionValue(1)
  const tilt = useMotionValue(0)
  /** 1 at the moment it lands, back to 0 on the spring. */
  const squash = useMotionValue(0)
  /** The hop: px up. */
  const hop = useMotionValue(0)
  /** 0 closed (just the tree), 1 open (its words showing). */
  const open = useMotionValue(0)
  const alpha = useMotionValue(0)
  /** The ear's mark to cover while it is away, when there is one to see. */
  const [cover, setCover] = useState<Point>()
  const cheeredAt = useRef(0)

  // To a mark: from home, from another mark, or (the same mark moved) just follow it.
  useEffect(() => {
    if (key === undefined || tx === undefined || ty === undefined) return
    const to = { x: tx, y: ty }
    const now = usePointing.getState().trip
    if (now.phase === 'perched' && now.at === key) {
      setTrip({ phase: 'perched', at: key, tree: to })
      if (reduced) {
        x.set(to.x)
        y.set(to.y)
        return
      }
      const runs = [animate(x, to.x, spring), animate(y, to.y, spring)]
      return () => runs.forEach((r) => r.stop())
    }
    const land = (): void => {
      x.set(to.x)
      y.set(to.y)
      scale.set(1)
      tilt.set(0)
      setTrip({ phase: 'perched', at: key, tree: to })
      if (!reduced) {
        squash.set(1)
        animate(squash, 0, spring)
      }
    }
    const fromHome = now.phase === 'home'
    let from: Point
    if (fromHome) {
      const home = bonsaiPoint(el.current, layout)
      from = { x: home.x, y: home.y }
      setCover(home.ear ? from : undefined)
      x.set(from.x)
      y.set(from.y)
    } else from = { x: x.get(), y: y.get() }
    setTrip({ phase: 'out' })
    if (reduced) {
      land()
      const run = animate(alpha, 1, fades.in)
      return () => run.stop()
    }
    alpha.set(1)
    const f = flight(from, to, fromHome ? 'out' : 'hop')
    // A flight that was turned round mid-air goes on from the size it had got to.
    const start = fromHome ? undefined : scale.get()
    const step = (t: number): void => {
      const p = along(f, t)
      x.set(p.x)
      y.set(p.y)
      scale.set(scaleAt(f, t, start))
      tilt.set(tiltAt(f, t))
    }
    step(0)
    const run = animate(0, 1, { duration: f.seconds, ease: ease.inOut, onUpdate: step, onComplete: land })
    return () => run.stop()
    // The trip is planned from the mark and its perch; the motion values and the layout are read as they are then.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, tx, ty, reduced])

  // The learner got there: a hop. (Before the effect below, which reads when the last hop was.)
  useEffect(() => {
    if (!cheer) return
    cheeredAt.current = Date.now()
    if (reduced || usePointing.getState().trip.phase === 'home') return
    const run = animate(hop, [0, -HOP.px, 0], { duration: HOP.seconds, ease: ease.out, times: [0, 0.4, 1] })
    return () => run.stop()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cheer])

  // Nothing left to point at: home.
  useEffect(() => {
    if (key !== undefined) return
    if (usePointing.getState().trip.phase === 'home') return
    setTrip({ phase: 'back' })
    let run: ReturnType<typeof animate> | undefined
    const arrive = (): void => {
      setTrip({ phase: 'home' })
      alpha.set(0)
      setCover(undefined)
    }
    const go = (): void => {
      if (reduced) {
        run = animate(alpha, 0, fades.out)
        void run.then(arrive)
        return
      }
      const home = bonsaiPoint(el.current, layout)
      const f = flight({ x: x.get(), y: y.get() }, { x: home.x, y: home.y }, 'home')
      const start = scale.get()
      run = animate(0, 1, {
        duration: f.seconds,
        ease: ease.inOut,
        onUpdate: (t) => {
          const p = along(f, t)
          x.set(p.x)
          y.set(p.y)
          scale.set(scaleAt(f, t, start))
          tilt.set(tiltAt(f, t))
        },
        onComplete: arrive
      })
    }
    const id = setTimeout(go, Date.now() - cheeredAt.current < 400 ? LEAVE_MS.afterHop : LEAVE_MS.plain)
    return () => {
      clearTimeout(id)
      run?.stop()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, reduced])

  // Its words: the pod opens once it has landed and the label is said one letter at a time.
  const perched = key !== undefined && trip.phase === 'perched' && trip.at === key
  const [letters, setLetters] = useState(0)
  useEffect(() => {
    if (!perched || !label) {
      setLetters(0)
      if (reduced) return open.jump(0)
      const run = animate(open, 0, fades.out)
      return () => run.stop()
    }
    if (reduced) {
      open.jump(1)
      setLetters(label.length)
      return
    }
    const run = animate(open, 1, spring)
    const t0 = performance.now()
    const id = setInterval(() => {
      const n = said(performance.now() - t0, label.length)
      setLetters(n)
      if (n >= label.length) clearInterval(id)
    }, 17)
    return () => {
      run.stop()
      clearInterval(id)
    }
  }, [perched, label, reduced, open])

  // It notices the learner: while the pointer is near, the tree turns to it.
  const away = trip.phase !== 'home'
  const [look, setLook] = useState<number>()
  useEffect(() => {
    if (!away) return setLook(undefined)
    const move = (e: MouseEvent): void => {
      const fr = frame(el.current)
      if (!fr) return
      const dx = (e.clientX - fr.box.left) * fr.k - x.get()
      const dy = (e.clientY - fr.box.top) * fr.k - y.get()
      setLook(Math.hypot(dx, dy) < NOTICE_PX ? Math.round(Math.max(-1, Math.min(1, dx / 50)) * 5) / 5 : undefined)
    }
    window.addEventListener('mousemove', move)
    return () => window.removeEventListener('mousemove', move)
  }, [away, x, y])
  const lean = look ?? (perched && spot ? leanToward(spot.tree, spot.ring) : 0)

  // Left of the loop the pod is mirrored (tree at its right end). It keeps the way it faced on the flight home.
  const facing = useRef(false)
  if (spot) facing.current = spot.mirrored
  const end = (v: number): CSSProperties => (facing.current ? { right: v } : { left: v })
  const width = useTransform(open, (o) => POD.h + o * (podWidth(textW) - POD.h))
  const wide = useTransform(squash, (q) => 1 + SQUASH.wide * q)
  const short = useTransform(squash, (q) => 1 - SQUASH.short * q)
  const inset = (POD.h - POD.tree) / 2

  return (
    <div ref={el} className="pointer-events-none absolute inset-0" data-buddy-pod={standDown ? 'stand-down' : trip.phase} data-letters={letters || undefined}>
      <span ref={ruler} aria-hidden className="invisible absolute left-0 top-0 whitespace-nowrap font-medium" style={{ fontSize: text.xs }}>
        {label}
      </span>
      {away && cover && <div data-part="home-cover" className="absolute" style={{ left: cover.x - COVER / 2, top: cover.y - COVER / 2, width: COVER, height: COVER, background: color.island }} />}
      {away && (
        <motion.div className="absolute left-0 top-0" style={{ x, y, opacity: alpha }}>
          <motion.div style={{ scale, rotate: tilt, y: hop }}>
            <motion.div style={{ scaleX: wide, scaleY: short, transformOrigin: `0px ${POD.h / 2}px` }}>
              <motion.div
                data-ui
                data-part="pod"
                data-side={spot?.side}
                className="absolute overflow-hidden"
                style={{ top: -POD.h / 2, ...end(-POD.h / 2), height: POD.h, width, borderRadius: POD.h / 2, background: color.island, boxShadow: shadows.pill }}
              >
                <span className="absolute" style={{ top: inset, ...end(inset), lineHeight: 0 }}>
                  <LivingMark size={POD.tree} tone="dark" state={state} bloom={bloom} lean={lean} />
                </span>
                {label && (
                  <span data-part="pod-words" className="absolute whitespace-nowrap font-medium" style={{ top: 0, ...end(POD.textAt), width: textW, lineHeight: `${POD.h}px`, fontSize: text.xs, color: color.text, textAlign: 'left' }}>
                    {label.slice(0, letters)}
                  </span>
                )}
              </motion.div>
            </motion.div>
          </motion.div>
        </motion.div>
      )}
    </div>
  )
}

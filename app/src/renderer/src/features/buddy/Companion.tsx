/**
 * Feature: buddy. The buddy itself, out on the screen. An overlay layer over the island (z 55).
 *
 * It is a character of its own (Character.tsx), not the logo: the bonsai stays in the notch, and the buddy lives in
 * the island beside it. What it does:
 *   - It comes when the learner talks to it. While they hold the push-to-talk keys it flies to their pointer, perks
 *     up and shows what it hears; when they let go it thinks; then it answers (talk.ts).
 *   - It keeps the pointer company while it is called (Clicky's cursor does this), and goes home when it has been
 *     quiet a while.
 *   - It shows things. When the coach points at something it flies there on an arc, lands beside it, throws a
 *     loop round it (Reach.tsx draws that, from where the buddy sits), points at it with a little arm, and says what
 *     it is, one letter at a time, in a bubble.
 *   - It takes the learner through several things one at a time: "2 of 3", a Next button, and it hops on.
 *   - The learner can answer back from the bubble: Explain (ask for more) or Got it.
 *   - It is alive: it blinks, floats, looks where it is going, looks at what it points at, turns to the learner's
 *     pointer when it comes near, and hops and beams when they get there.
 * Trips, perches and timing are pure and in trip.ts.
 *
 * The bubble is island black, like the pill. It is data-ui, so the engine never reads the buddy's words as the
 * learner's screen. The body is not: it has no words, and data-ui would make the engine's reader drop the lines under
 * it (beside a code row: that row's line number, which the engine reads to place the box). Only a bubble with buttons
 * takes the mouse (data-hit); nothing else here does.
 *
 * Where it lives (home.ts): in the bottom right corner of the screen by default, always there, full size (Adrian,
 * Nov 24). Its trips start and end there, and a click on it wakes it: its bubble offers Ask (the ask field) and how to
 * talk to it, and what it hears, thinks and answers shows there (talk.ts woken). At home in the corner its body takes
 * the mouse (data-hit, a 60 px square): the one place it does, so beside a code row it still hides nothing from the
 * engine's reader. With home 'notch' it is tucked in the island as before and takes no click.
 *
 * Reduced motion: no flights. It fades in where it would have landed, with its words whole, and fades out.
 * The character is the one that draws (Adrian, Nov 23). It stands down, with its loops, only for a cut of Michael's
 * features/annotate that still draws (Reach.tsx useStandDown, marks.ts standsDown).
 */
import { animate, AnimatePresence, motion, useMotionValue, useReducedMotion, useTransform } from 'motion/react'
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import type { Layout } from '../../../../preload/api'
import type { Point } from '../../core/geometry'
import { useKey } from '../../core/keys'
import { color, fill, shadows, text } from '../../core/theme'
import { OptionButton, PrimaryButton } from '../../core/ui/atoms'
import { ease, fade as fades, spring } from '../../core/ui/motion'
import { Character, CHARACTERS, DEFAULT_CHARACTER, type CharacterKind, type Mood } from './Character'
import { useGrowth } from './growth'
import { cornerPoint, HOME, useHome } from './home'
import { NAME } from './name'
import { useSkin } from './skin'
import { ringBox } from './marks'
import { setTrip, usePointing } from './pointing'
import { bonsaiPoint, frame, useHere, useStandDown } from './Reach'
import { ask, canExplain, reply, useTalk, wake, type ReplyKind } from './talk'
import { along, beside, BODY, buddyWhy, catchUp, flight, gazeAt, gazeOf, markWords, NOTICE_PX, perch, perchPrefer, said, scaleAt, tiltAt, type Flight } from './trip'

/** Landing: it squashes this much (wider, shorter) and springs back. The hop when the learner gets there: this high, this long. */
const SQUASH = { wide: 0.08, short: 0.13 } as const
const HOP = { px: 11, seconds: 0.36, beamMs: 1100 } as const
/** Going home it waits for the loop to come off; a little longer when it has a hop to finish. */
const LEAVE_MS = { plain: 160, afterHop: 520 } as const
/** The bubble: its words wrap at this width; `line` is their line height. Its first line is level with the buddy and it grows downward. */
const BUBBLE = { maxText: 236, padX: 13, padY: 9, radius: 16, line: 18, edge: 12 } as const
/** A soft drop under the buddy, so it sits above the screen. Not a glow. */
const DROP = 'drop-shadow(0 2px 3px rgba(0,0,0,.34))'
/** It pops out of, and back into, the island over this share of the flight. */
const POP = 0.14
/** Where it waits when it is called and has not seen the pointer yet: under the notch. */
const WAIT_BELOW = 112

/** A level-up, in front of the learner: it comes out as it was, and this long after (ms) what is on its head grows. */
const GROW_AFTER_MS = 1150
/** How long the growing takes to play (buddy.css ch-unfurl, and a beat to look at it). */
const GROW_SHOW_MS = 1500

/**
 * The level the buddy on the screen shows. It follows the learner's count (growth.ts), except at a level-up that
 * happened here: then it keeps the old look until it has come out, and grows where the learner can see it.
 */
function useGrown(): { level: number; grew: boolean } {
  const level = useGrowth((g) => g.level)
  const ups = useGrowth((g) => g.grew)
  const [shown, setShown] = useState({ level, grew: false })
  const seen = useRef(ups)
  useEffect(() => {
    if (ups === seen.current) {
      setShown((s) => (s.level === level && !s.grew ? s : { level, grew: false }))
      return
    }
    seen.current = ups
    const a = setTimeout(() => setShown({ level, grew: true }), GROW_AFTER_MS)
    const b = setTimeout(() => setShown({ level, grew: false }), GROW_AFTER_MS + GROW_SHOW_MS)
    return () => {
      clearTimeout(a)
      clearTimeout(b)
    }
  }, [level, ups])
  return shown
}

/** Which character it is. The browser stage's ?char=<kind> shows one of the others. */
const KIND: CharacterKind = (() => {
  const q = typeof location !== 'undefined' ? new URLSearchParams(location.search).get('char') : null
  return CHARACTERS.find((k) => k === q) ?? DEFAULT_CHARACTER
})()

/** What is in its bubble. */
type Model =
  | { kind: 'words'; text: string; footer: 'tour' | 'reply' | 'none'; step: number; total: number; forKey?: string }
  | { kind: 'listening'; heard: string }
  | { kind: 'thinking' }
  /** Woken in its corner: Ask, and how to talk to it. */
  | { kind: 'menu' }

const ghost: CSSProperties = { height: 26, padding: '0 11px', borderRadius: 13, background: fill.chip, border: `1px solid ${fill.chipBorder}`, color: fill.chipText, fontSize: text.xs, fontWeight: 500, cursor: 'pointer', whiteSpace: 'nowrap' }

/**
 * The bubble's insides. `letters`: how much of its words it has said (the rest keeps its room, unseen). `open`: its
 * buttons are showing (they fold out under the words once it has said them). `measure`: the unseen copy the bubble
 * is sized from: everything open, nothing live.
 */
function Says({ model, letters, open, onReply, onAsk, measure = false }: { model: Model; letters: number; open: boolean; onReply?: (kind: ReplyKind) => void; onAsk?: () => void; measure?: boolean }): ReactNode {
  const skin = useSkin()
  const askKey = useKey('launcher')
  const talkKey = useKey('ptt')
  if (model.kind === 'menu') {
    return (
      <span data-part={measure ? undefined : 'buddy-menu'} className="flex items-center gap-[10px] whitespace-nowrap">
        <PrimaryButton label="Ask" kbd={askKey} onClick={() => onAsk?.()} />
        {talkKey && <span style={{ color: color.faint }}>or hold {talkKey} and talk</span>}
      </span>
    )
  }
  if (model.kind === 'thinking') {
    return (
      <span className="bd-dots">
        <i />
        <i />
        <i />
      </span>
    )
  }
  if (model.kind === 'listening') {
    return (
      <span className="flex items-center gap-[9px] whitespace-nowrap">
        <span className="bd-bars" style={{ color: skin.stroke }}>
          <i />
          <i />
          <i />
          <i />
        </span>
        {model.heard && <span>{model.heard.length > 44 ? `…${model.heard.slice(-44)}` : model.heard}</span>}
      </span>
    )
  }
  const last = model.step >= model.total
  return (
    <>
      {model.text && (
        <span data-part={measure ? undefined : 'buddy-words'} className="block">
          {model.text.slice(0, letters)}
          <span style={{ opacity: 0 }}>{model.text.slice(letters)}</span>
        </span>
      )}
      {model.footer !== 'none' && (
        <span className="bd-foot" data-open={open || measure || undefined}>
          <span>
            <span data-part={measure ? undefined : 'buddy-replies'} className="flex items-center gap-[8px]" style={{ paddingTop: model.text ? 8 : 0 }}>
              {model.footer === 'tour' ? (
                <>
                  <span style={{ color: color.faint, marginRight: 4 }}>
                    {model.step} of {model.total}
                  </span>
                  <PrimaryButton label={last ? 'Done' : 'Next'} onClick={() => onReply?.(last ? 'got' : 'next')} />
                </>
              ) : (
                <>
                  {canExplain() && <OptionButton action="explain" label="Explain" onClick={() => onReply?.('explain')} />}
                  <button type="button" style={ghost} onMouseDown={(e) => e.preventDefault()} onClick={() => onReply?.('got')}>
                    Got it
                  </button>
                </>
              )}
            </span>
          </span>
        </span>
      )}
    </>
  )
}

const bubbleBox: CSSProperties = { padding: `${BUBBLE.padY}px ${BUBBLE.padX}px`, borderRadius: BUBBLE.radius, background: color.island, boxShadow: shadows.pill, color: color.text, fontSize: text.xs, fontWeight: 500, lineHeight: `${BUBBLE.line}px` }

export function CompanionLayer({ layout }: { layout: Layout }): ReactNode {
  const marks = usePointing((s) => s.marks)
  const total = usePointing((s) => s.total)
  const trip = usePointing((s) => s.trip)
  const cheer = usePointing((s) => s.cheer)
  const grown = useGrown()
  /** A spotlight box, not the engine's own mark: the spotlight's caption has the right of it, so the buddy takes the left. */
  const bridged = usePointing((s) => s.bridged)
  const talk = useTalk()
  const el = useRef<HTMLDivElement>(null)
  const reduced = useReducedMotion() ?? false
  const standDown = useStandDown()
  const here = useHere(marks, layout)
  const first = standDown ? undefined : here[0]
  const key = first?.key
  /** It lives in the corner of the screen (home.ts), not tucked in the island. */
  const corner = useHome((h) => h.place) === 'corner' && !standDown
  // Woken in its corner it stays there: it does not go to the pointer.
  const goal: 'mark' | 'follow' | 'home' = key !== undefined ? 'mark' : talk.summoned && !standDown && !(corner && talk.woken) ? 'follow' : 'home'

  // What it has to say right now.
  // A mark's own words first; a mark with none (a spotlight box) lets it say what it has to say anyway (it grew).
  const line = first ? (talk.sayFor === first.key && talk.say ? talk.say : (markWords(first) ?? (talk.sayFor ? undefined : talk.say))) : talk.sayFor ? undefined : talk.say
  const model = useMemo((): Model | undefined => {
    if (goal === 'home' && !(corner && talk.woken)) return undefined
    if (talk.activity === 'thinking') return { kind: 'thinking' }
    if (goal === 'home' && talk.menu && talk.activity === 'idle') return { kind: 'menu' }
    if (talk.activity === 'listening' && !key) return { kind: 'listening', heard: talk.heard }
    if (key !== undefined) {
      const footer = total > 1 ? 'tour' : line ? 'reply' : 'none'
      return line || footer === 'tour' ? { kind: 'words', text: line ?? '', footer, step: Math.max(1, total - marks.length + 1), total, forKey: key } : undefined
    }
    return line ? { kind: 'words', text: line, footer: 'none', step: 1, total: 1 } : undefined
  }, [goal, corner, talk.woken, talk.menu, talk.activity, talk.heard, key, line, total, marks.length])
  const modelKey = model ? (model.kind === 'words' ? `w:${model.forKey ?? ''}:${model.text}:${model.footer}:${model.step}/${model.total}` : model.kind) : ''
  const heardLen = model?.kind === 'listening' ? Math.min(model.heard.length, 45) : 0

  // The bubble's size, measured from an unseen copy in a layout effect, so the perch is planned with it before the
  // flight starts and the words never reflow as they are said.
  const ruler = useRef<HTMLDivElement>(null)
  const [size, setSize] = useState({ w: 0, h: 0 })
  useLayoutEffect(() => {
    const n = ruler.current
    const next = model && n ? { w: n.offsetWidth + 1, h: n.offsetHeight } : { w: 0, h: 0 }
    setSize((s) => (s.w === next.w && s.h === next.h ? s : next))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modelKey, heardLen])

  const wa = layout.workArea
  const nest = cornerPoint({ x: wa.x, y: wa.y, w: wa.width, h: wa.height })
  const cx = nest.x
  const cy = nest.y
  const rx = first?.rect.x
  const ry = first?.rect.y
  const rw = first?.rect.w
  const rh = first?.rect.h
  /** The on-screen coach's mark: its text box (features/annotate) takes the right of the loop, so the buddy the left. */
  const coach = !!first?.text
  const spot = useMemo(() => {
    if (rx === undefined || ry === undefined || rw === undefined || rh === undefined) return undefined
    const ring = ringBox({ x: rx, y: ry, w: rw, h: rh }, { x: 0, y: 0, w: layout.width, h: layout.height })
    return { ...perch(ring, size, { x: wa.x, y: wa.y, w: wa.width, h: wa.height }, perchPrefer(coach, bridged)), ring }
  }, [rx, ry, rw, rh, size, layout.width, layout.height, wa.x, wa.y, wa.width, wa.height, bridged, coach])
  const bx = spot?.body.x
  const by = spot?.body.y

  /** Where the buddy's body is, in this window's coordinates. */
  const x = useMotionValue(0)
  const y = useMotionValue(0)
  const scale = useMotionValue(1)
  const tilt = useMotionValue(0)
  /** 1 at the moment it lands, back to 0 on the spring. */
  const squash = useMotionValue(0)
  /** The hop: px up. */
  const hop = useMotionValue(0)
  const alpha = useMotionValue(0)
  const [flying, setFlying] = useState(false)
  /** Where it is headed, for its eyes. */
  const [heading, setHeading] = useState<Point>({ x: 0, y: 0 })
  const [beaming, setBeaming] = useState(false)
  const cheeredAt = useRef(0)
  /** The learner's pointer, in this window's coordinates, once it has moved. */
  const pointer = useRef<Point | undefined>(undefined)

  /** Put it in the island, small and unseen, ready to pop out. In the corner it is already there, full size. */
  const tuckIn = (): void => {
    if (corner) {
      x.set(cx)
      y.set(cy)
      scale.set(1)
      tilt.set(0)
      alpha.set(1)
      return
    }
    const home = bonsaiPoint(el.current, layout)
    x.set(home.x)
    y.set(home.y + 6)
    scale.set(BODY.home)
    tilt.set(0)
    alpha.set(0)
  }

  /** Fly from where it is to `to`. Returns how to stop it. */
  const fly = (to: Point, kind: Flight['kind'], done: () => void): (() => void) => {
    const f = flight({ x: x.get(), y: y.get() }, to, kind)
    const start = kind === 'out' ? undefined : scale.get()
    const step = (t: number): void => {
      const p = along(f, t)
      x.set(p.x)
      y.set(p.y)
      scale.set(scaleAt(f, t, start))
      tilt.set(tiltAt(f, t))
      // Out of the island and back into it: it fades in over the first steps, and out over the last.
      if (kind === 'out') alpha.set(Math.min(1, t / POP))
      else if (kind === 'home') alpha.set(Math.min(1, (1 - t) / POP))
      else alpha.set(1)
    }
    setHeading(gazeOf(f))
    setFlying(true)
    step(0)
    const run = animate(0, 1, {
      duration: f.seconds,
      ease: ease.inOut,
      onUpdate: step,
      onComplete: () => {
        setFlying(false)
        done()
      }
    })
    return () => {
      run.stop()
      setFlying(false)
    }
  }

  // To a mark: from home, from the pointer, from another mark, or (the same mark moved) just follow it.
  useEffect(() => {
    if (key === undefined || bx === undefined || by === undefined) return
    const to = { x: bx, y: by }
    const now = usePointing.getState().trip
    if (now.phase === 'perched' && now.at === key) {
      setTrip({ phase: 'perched', at: key, body: to })
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
      alpha.set(1)
      setTrip({ phase: 'perched', at: key, body: to })
      if (!reduced) {
        squash.set(1)
        animate(squash, 0, spring)
      }
    }
    const fromHome = now.phase === 'home'
    if (fromHome) tuckIn()
    setTrip({ phase: 'out' })
    if (reduced) {
      land()
      alpha.set(0)
      const run = animate(alpha, 1, fades.in)
      return () => run.stop()
    }
    return fly(to, fromHome && !corner ? 'out' : 'hop', land)
    // The trip is planned from the mark and its perch; the motion values and the layout are read as they are then.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, bx, by, reduced])

  // Called, with nothing to point at: over to the learner's pointer.
  useEffect(() => {
    if (goal !== 'follow') return
    const now = usePointing.getState().trip
    if (now.phase === 'follow') return
    const screen = { x: 0, y: 0, w: layout.width, h: layout.height }
    const to = beside(pointer.current ?? { x: layout.width / 2 - 60, y: WAIT_BELOW }, screen)
    const arrive = (): void => {
      scale.set(1)
      tilt.set(0)
      alpha.set(1)
      setTrip({ phase: 'follow' })
    }
    const fromHome = now.phase === 'home'
    if (fromHome) tuckIn()
    setTrip({ phase: 'out' })
    if (reduced) {
      x.set(to.x)
      y.set(to.y)
      arrive()
      alpha.set(0)
      const run = animate(alpha, 1, fades.in)
      return () => run.stop()
    }
    return fly(to, fromHome && !corner ? 'out' : 'hop', arrive)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [goal, reduced])

  // By the pointer: it catches up with it, a little behind, every frame.
  const following = trip.phase === 'follow' && goal === 'follow'
  useEffect(() => {
    if (!following) return
    const screen = { x: 0, y: 0, w: layout.width, h: layout.height }
    let raf = 0
    let last = performance.now()
    const tick = (now: number): void => {
      const dt = Math.min(0.05, (now - last) / 1000)
      last = now
      if (pointer.current) {
        const to = beside(pointer.current, screen)
        const p = reduced ? to : catchUp({ x: x.get(), y: y.get() }, to, dt)
        x.set(p.x)
        y.set(p.y)
      }
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [following, reduced, layout.width, layout.height, x, y])

  // The learner got there: a hop, and it beams. (Before the effect below, which reads when the last hop was.)
  useEffect(() => {
    if (!cheer) return
    cheeredAt.current = Date.now()
    if (usePointing.getState().trip.phase === 'home') return
    setBeaming(true)
    const off = setTimeout(() => setBeaming(false), HOP.beamMs)
    const run = reduced ? undefined : animate(hop, [0, -HOP.px, 0], { duration: HOP.seconds, ease: ease.out, times: [0, 0.4, 1] })
    return () => {
      clearTimeout(off)
      run?.stop()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cheer])

  // Nothing left to do: home.
  useEffect(() => {
    if (goal !== 'home') return
    if (usePointing.getState().trip.phase === 'home') return
    setTrip({ phase: 'back' })
    let stop: (() => void) | undefined
    const arrive = (): void => {
      setTrip({ phase: 'home' })
      if (!corner) return alpha.set(0)
      x.set(cx)
      y.set(cy)
      scale.set(1)
      tilt.set(0)
      alpha.set(1)
    }
    const go = (): void => {
      if (reduced) {
        const run = animate(alpha, 0, fades.out)
        void run.then(arrive)
        stop = () => run.stop()
        return
      }
      // To the corner it hops, full size all the way; into the island it shrinks and fades.
      if (corner) {
        stop = fly({ x: cx, y: cy }, 'hop', arrive)
        return
      }
      const home = bonsaiPoint(el.current, layout)
      stop = fly({ x: home.x, y: home.y + 6 }, 'home', arrive)
    }
    const id = setTimeout(go, Date.now() - cheeredAt.current < 600 ? LEAVE_MS.afterHop : LEAVE_MS.plain)
    return () => {
      clearTimeout(id)
      stop?.()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [goal, reduced, corner, cx, cy])

  // At home in the corner it is simply there (and follows the corner when the screen or the Dock changes). With its
  // home in the island it is unseen until it pops out.
  useLayoutEffect(() => {
    if (usePointing.getState().trip.phase !== 'home') return
    if (!corner) return alpha.set(0)
    x.set(cx)
    y.set(cy)
    scale.set(1)
    tilt.set(0)
    alpha.set(1)
  }, [corner, cx, cy, x, y, scale, tilt, alpha])

  // It is where it means to be: its bubble can open.
  const perched = key !== undefined && trip.phase === 'perched' && trip.at === key
  const nested = corner && goal === 'home' && trip.phase === 'home'
  const settled = perched || (goal === 'follow' && trip.phase === 'follow') || nested
  const words = model?.kind === 'words' ? model.text : ''
  const [letters, setLetters] = useState(0)
  useEffect(() => {
    if (!settled || !words) return setLetters(0)
    if (reduced) return setLetters(words.length)
    setLetters(0)
    const t0 = performance.now()
    const id = setInterval(() => {
      const n = said(performance.now() - t0, words.length)
      setLetters(n)
      if (n >= words.length) clearInterval(id)
    }, 17)
    return () => clearInterval(id)
  }, [settled, words, reduced])
  const talking = settled && !!words && letters < words.length

  // It notices the learner: the pointer is tracked always, and while it is near the buddy turns to look at it.
  const away = trip.phase !== 'home'
  const cornered = useRef(corner)
  cornered.current = corner
  const [glance, setGlance] = useState<Point>()
  useEffect(() => {
    const move = (e: MouseEvent): void => {
      const fr = frame(el.current)
      if (!fr) return
      const p = { x: (e.clientX - fr.box.left) * fr.k, y: (e.clientY - fr.box.top) * fr.k }
      pointer.current = p
      if (usePointing.getState().trip.phase === 'home' && !cornered.current) return
      const dx = p.x - x.get()
      const dy = p.y - y.get()
      const d = Math.hypot(dx, dy)
      setGlance((g) => {
        const next = d < NOTICE_PX && d > 1 ? { x: Math.round((dx / d) * 5) / 5, y: Math.round((dy / d) * 5) / 5 } : undefined
        return g?.x === next?.x && g?.y === next?.y ? g : next
      })
    }
    window.addEventListener('mousemove', move)
    return () => window.removeEventListener('mousemove', move)
  }, [x, y])

  // Its face.
  const mood: Mood = beaming ? 'happy' : talk.activity === 'thinking' ? 'thinking' : talk.activity === 'listening' ? 'listening' : glance && !flying ? 'curious' : 'calm'
  const look = flying ? heading : (glance ?? (perched && spot ? gazeAt(spot.body, spot.ring) : { x: 0, y: 0 }))
  // Left of the loop it is mirrored (its bubble runs off to the left). It keeps the way it faced on the flight home.
  const facing = useRef(false)
  if (spot) facing.current = spot.mirrored
  // In its corner (bottom right) the bubble runs off to the left too.
  const mirrored = key !== undefined ? facing.current : nested
  const point: -1 | 0 | 1 = perched && !beaming && spot && (spot.side === 'right' || spot.side === 'left') ? (spot.mirrored ? 1 : -1) : 0
  const end = (v: number): CSSProperties => (mirrored ? { right: v } : { left: v })
  const wide = useTransform(squash, (q) => 1 + SQUASH.wide * q)
  const short = useTransform(squash, (q) => 1 - SQUASH.short * q)
  const ready = (model?.kind === 'menu' && settled) || (model?.kind === 'words' && model.footer !== 'none' && settled && letters >= words.length)
  // The bubble hangs from the buddy's line: its first line is level with the buddy, and it is pulled up only when it
  // would run off the bottom of the screen.
  const hang = Math.min(-(BUBBLE.line / 2 + BUBBLE.padY), wa.y + wa.height - BUBBLE.edge - y.get() - size.h)
  const onReply = (kind: ReplyKind): void => {
    if (key !== undefined) reply(kind, key)
  }
  /** A click on it at home: it wakes with a small hop (or, already offering, goes back to rest). */
  const onWake = (): void => {
    const waking = !(talk.woken && talk.menu)
    wake()
    if (!waking) return
    setBeaming(true)
    setTimeout(() => setBeaming(false), 700)
    if (!reduced) animate(hop, [0, -HOP.px, 0], { duration: HOP.seconds, ease: ease.out, times: [0, 0.4, 1] })
  }
  // Its body sits low in its 48-unit box (the sprout needs the room above): put the body, not the box, on the spot.
  const lift = BODY.size * (28 / 48)

  return (
    <div
      ref={el}
      className="pointer-events-none absolute inset-0"
      data-buddy={standDown ? 'stand-down' : trip.phase}
      data-buddy-why={buddyWhy({ standDown, marks: marks.length, here: here.length, summoned: talk.summoned })}
      data-buddy-mood={away || corner ? mood : undefined}
      data-buddy-home={corner ? 'corner' : 'notch'}
      data-letters={letters || undefined}
    >
      {model && (
        <div ref={ruler} aria-hidden className="pointer-events-none absolute left-0 top-0" style={{ ...bubbleBox, visibility: 'hidden', width: 'max-content', maxWidth: BUBBLE.maxText + BUBBLE.padX * 2 }}>
          <Says model={model} letters={words.length} open measure />
        </div>
      )}
      {(away || corner) && (
        <motion.div className="absolute left-0 top-0" style={{ x, y, opacity: alpha }}>
          <motion.div style={{ scale, rotate: tilt, y: hop }}>
            <motion.div style={{ scaleX: wide, scaleY: short, transformOrigin: `0px ${BODY.size * 0.3}px` }}>
              {/* Not data-ui (live trace B6): the body has no words, and overlay.bounds makes the engine's reader drop and
                  black out every line under it. Perched left of a code row it sat on that row's line number, the very
                  thing the engine reads to keep the box on its line. Its bubble (words) stays data-ui. */}
              <span data-part="buddy-body" className="absolute" style={{ left: -BODY.size / 2, top: -lift, lineHeight: 0, filter: DROP }}>
                <Character kind={KIND} size={BODY.size} mood={mood} look={look} talking={talking} flying={flying} point={point} level={grown.level} grew={grown.grew} />
              </span>
            </motion.div>
          </motion.div>
          {nested && (
            <button
              type="button"
              data-hit
              data-part="buddy-home"
              aria-label={`Ask ${NAME ?? 'bon'}`}
              aria-expanded={talk.woken}
              className="pointer-events-auto absolute cursor-pointer"
              style={{ left: -HOME.hit / 2, top: -HOME.hit / 2, width: HOME.hit, height: HOME.hit, borderRadius: HOME.hit / 2, background: 'transparent', border: 0, padding: 0 }}
              onMouseDown={(e) => e.preventDefault()}
              onClick={onWake}
            />
          )}
          <AnimatePresence>
            {model && settled && size.w > 0 && (
              <motion.div
                key={modelKey}
                data-ui
                data-hit={ready || undefined}
                data-part="bubble"
                data-side={spot?.side}
                className={`absolute ${ready ? 'pointer-events-auto' : ''}`}
                style={{ ...bubbleBox, top: hang, ...end(BODY.size / 2 + BODY.gap), width: size.w, transformOrigin: mirrored ? '100% 18px' : '0% 18px' }}
                initial={reduced ? { opacity: 0 } : { opacity: 0, scale: 0.6 }}
                animate={reduced ? { opacity: 1 } : { opacity: 1, scale: 1 }}
                exit={{ opacity: 0, transition: fades.out }}
                transition={reduced ? fades.in : { ...spring, opacity: fades.in }}
              >
                {/* Its tail, toward the buddy. */}
                <span aria-hidden className="absolute" style={{ top: -hang - 4.5, ...end(-3.5), width: 9, height: 9, borderRadius: 2, background: color.island, transform: 'rotate(45deg)' }} />
                <span className="relative block">
                  <Says model={model} letters={letters} open={!!ready} onReply={onReply} onAsk={ask} />
                </span>
              </motion.div>
            )}
          </AnimatePresence>
        </motion.div>
      )}
    </div>
  )
}

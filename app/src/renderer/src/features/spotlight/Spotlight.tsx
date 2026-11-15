/**
 * Building mode, screen-first (mockup 04, Miyagi brand): the engine's screen reader (Apple Vision OCR)
 * finds the target on screen and sends `spotlight {rect, caption}`. We dim everything around it and cut a
 * rounded hole at that rect, edged with a crisp hairline, with a glass caption beside it. Works over
 * any app; never takes a click except on the voice button.
 *
 * Two dims (Michael's audit A6): a text lesson's "type here" target gets the soft one (`scrim.spotlightSoft`), so
 * the learner's own code and terminal stay readable around it; Show me (and video lessons) keep the strong one
 * (`scrim.spotlight`). The two crossfade (opacity only) when a target changes kind.
 *
 * Brand (app/brand/BRAND.md) + Adrian ("less like AI slop, more precise"): the cut-out is edged by ONE white
 * hairline, whatever the state (the pill and the card already carry status color), over a faint
 * `color.onAccent` keyline so it reads over light apps. The caption is a chip on the island's black, one line when
 * it fits (two at most), to the right of the cut-out and centered on it (mockup 01; Michael's audit A7): no eyebrow,
 * no dot. The speaker shows only while voice is on (tap to turn it off).
 *
 * Michael's tests 2-3 (A10: captions and the code popup covered code): ONE rect per spotlight, the latest message's
 * (the coach's other targets are no longer drawn); the caption always takes the empty lane right of the box, wrapping
 * to fit it, and only goes below / above when that lane is too narrow, never left over the gutter (place.ts). The
 * snippet under it is sized to its code with the missing line highlighted (Snippet).
 *
 * Animation (FRONTEND-HANDOFF → "Dim overlay + spotlight"):
 *   - the dim fades in over 280ms;
 *   - the hole is ONE set of motion values (x, y, w, h) driven by the spring. The mask cut-out and the
 *     ring read those same values, written straight to the SVG attributes every frame: no React
 *     re-render while it moves;
 *   - the ring pulses once in opacity per new target or state (→ 1 → rest, 1.2s), then stays still;
 *   - reduced motion: no spring, no pulse, crossfades only.
 */
import { AnimatePresence, animate, motion, useMotionValue, useReducedMotion } from 'motion/react'
import { useCallback, useEffect, useId, useLayoutEffect, useMemo, useRef, useState, type ReactNode, type RefObject } from 'react'
import { Volume2 } from 'lucide-react'
import { useLesson, useStatus, type Rect } from '../../core/lesson'
import { useDrawer } from '../drawer/store'
import { useLauncherOpen } from '../launcher/store'
import { color, fill, font, radius, scrim, shadows, spring, text } from '../../core/theme'
import { toggleVoice, useVoice } from '../voice/store'
import { CodeText } from '../../core/ui/atoms'
import { closeTicks, missingLines, plain } from './code'
import { EDGE_MARGIN, hole, holeRadius, placeCaption, rightLane, type Side } from './place'
import type { SpotlightMode, SpotlightTarget } from './store'

/** The caption chip hugs its text, up to this width, wrapping to at most CAPTION_LINES lines (one is the aim). */
const CAPTION_MAX_W = 420
const CAPTION_LINES = 2
/**
 * The narrowest lane right of the box the caption takes (wrapping to it, a third line allowed) before it goes below
 * the box instead; a chip with a snippet needs more room for its code.
 */
const CAPTION_MIN_ROOM = 120
const SNIPPET_MIN_ROOM = 320
/** Until the caption has been measured: one line. */
const CAPTION_GUESS = { w: 240, h: 26 }
/** The dim: `scrim.spotlight` (black at .66, Adrian's "more contrast") or `scrim.spotlightSoft`, fading in over 280ms. */
const DIM = { strong: scrim.spotlight, soft: scrim.spotlightSoft, fade: 0.28 } as const
/** The ring: a crisp hairline (no blur) over a faint dark keyline for contrast on light apps. */
const RING = { width: 1, keyline: 3, keylineOpacity: 0.35 } as const
const PULSE = { from: 0.45, peak: 1, rest: 0.9, duration: 1.2 } as const
/** While the ask panel (the launcher) is open, the caption and target labels step back so the panel reads (A13). */
const ASKING_OPACITY = 0.3

type Props = {
  target?: SpotlightTarget
  /** The target in THIS window's coordinates (already offset by layout.origin), unpadded. */
  rect?: Rect
  /** Where the caption may go: the window's work area, in window coordinates. */
  bounds: Rect
  mode: SpotlightMode
  /** The soft dim: a text lesson's "type here" target. false = the strong dim (Show me, video lessons). */
  soft: boolean
  /** Only one window draws the caption when a target straddles two displays. */
  showCaption: boolean
  /** UI outside this window the caption must not cover (the lesson player's window), window coordinates. */
  avoid: Rect[]
  /**
   * Other text the engine boxed on screen (the coach's targets), window coordinates. Never drawn (one rect per
   * spotlight, A10): the caption only reads them to start past the longest line beside the box.
   */
  text: Rect[]
}

export function Spotlight({ target, rect, ...rest }: Props): ReactNode {
  return <AnimatePresence>{target && rect && <Scene key="spotlight" target={target} rect={rect} {...rest} />}</AnimatePresence>
}

/**
 * One rect per spotlight (Michael's tests 2-3, A10: "replaced rather than stacked"): the scene draws the hole of the
 * latest spotlight message and nothing else. A new message springs that same hole to its new place (one set of
 * motion values, the scene never remounts), so two boxes are never on screen at once.
 */
function Scene({ target, rect, bounds, mode, soft, showCaption, avoid, text }: Props & { target: SpotlightTarget; rect: Rect }): ReactNode {
  const reduced = useReducedMotion() ?? false
  const cut = hole(rect)
  const register = useAnimatedHole(cut, reduced)
  const status = useStatus()
  // Pulse per new target or state, not per move: a moving ring that re-pulses reads as flicker.
  const pulse = usePulse(`${status}|${target.caption}`, reduced)
  const id = useId().replace(/[^a-zA-Z0-9_-]/g, '')
  // Fallback (cut order): the same hairline, no dim.
  const outline = mode === 'outline'
  const asking = useLauncherOpen()

  return (
    <motion.div
      className="pointer-events-none absolute inset-0"
      data-spotlight={mode}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: DIM.fade, ease: 'easeOut' }}
    >
      <svg className="absolute inset-0 h-full w-full" aria-hidden>
        {!outline && (
          <defs>
            <mask id={`${id}-hole`} maskUnits="userSpaceOnUse" x="0" y="0" width="100%" height="100%">
              {/* Mask luminance: white keeps the dim, black cuts the hole. */}
              <rect width="100%" height="100%" fill="#fff" />
              <rect ref={register} data-part="hole" fill="#000" />
              {/* The docked video panel stays undimmed: the playing video and its gate button (test 10 polish, item 2). */}
              {avoid.map((r, i) => (
                <rect key={i} x={r.x} y={r.y} width={r.w} height={r.h} rx={12} fill="#000" data-part="dock-cut" />
              ))}
            </mask>
          </defs>
        )}
        {!outline &&
          (['strong', 'soft'] as const).map((k) => (
            <motion.rect
              key={k}
              width="100%"
              height="100%"
              fill={DIM[k]}
              mask={`url(#${id}-hole)`}
              data-part="dim"
              data-dim={k}
              initial={false}
              animate={{ opacity: (k === 'soft') === soft ? 1 : 0 }}
              transition={{ duration: DIM.fade, ease: 'easeOut' }}
            />
          ))}
        <motion.g style={{ opacity: pulse }} data-part="ring">
          <rect ref={register} data-part="keyline" fill="none" style={{ stroke: color.onAccent }} strokeOpacity={RING.keylineOpacity} strokeWidth={RING.keyline} />
          <rect ref={register} data-part="hairline" data-status={status} fill="none" style={{ stroke: color.text }} strokeWidth={RING.width} />
        </motion.g>
      </svg>
      <motion.div className="absolute inset-0" initial={false} animate={{ opacity: asking ? ASKING_OPACITY : 1 }} transition={{ duration: 0.2 }}>
        {showCaption && <Caption target={target} hole={cut} bounds={bounds} avoid={avoid} text={text} reduced={reduced} />}
      </motion.div>
    </motion.div>
  )
}

/**
 * The hole's x/y/w/h as motion values, sprung to each new target. Returns a ref callback: every SVG
 * rect registered with it (mask cut-out, keyline, hairline) gets the current values written to its
 * attributes on each animation frame, so they move as one object without re-rendering React.
 */
function useAnimatedHole(to: Rect, reduced: boolean): (el: SVGRectElement | null) => void | (() => void) {
  const x = useMotionValue(to.x)
  const y = useMotionValue(to.y)
  const w = useMotionValue(to.w)
  const h = useMotionValue(to.h)
  const els = useRef(new Set<SVGRectElement>())

  const write = useCallback((): void => {
    const r = { x: x.get(), y: y.get(), w: Math.max(0, w.get()), h: Math.max(0, h.get()) }
    const rr = String(holeRadius(r))
    for (const el of els.current) {
      el.setAttribute('x', String(r.x))
      el.setAttribute('y', String(r.y))
      el.setAttribute('width', String(r.w))
      el.setAttribute('height', String(r.h))
      el.setAttribute('rx', rr)
      el.setAttribute('ry', rr)
    }
  }, [x, y, w, h])

  // One spring per axis, same target and timing → the rect moves as one. A new target mid-flight
  // starts from the current values and velocity, so retargeting stays smooth.
  useEffect(() => {
    const goal = [to.x, to.y, to.w, to.h]
    const values = [x, y, w, h]
    if (reduced) {
      values.forEach((v, i) => v.jump(goal[i]))
      return
    }
    const runs = values.map((v, i) => animate(v, goal[i], spring))
    return () => runs.forEach((r) => r.stop())
  }, [to.x, to.y, to.w, to.h, reduced, x, y, w, h])

  useEffect(() => {
    const offs = [x, y, w, h].map((v) => v.on('change', write))
    return () => offs.forEach((off) => off())
  }, [x, y, w, h, write])

  return useCallback(
    (el: SVGRectElement | null) => {
      if (!el) return
      els.current.add(el)
      write()
      return () => {
        els.current.delete(el)
      }
    },
    [write]
  )
}

/** Ring opacity: one pulse (→ 1 → rest over 1.2s) whenever `key` changes, then still. */
function usePulse(key: string, reduced: boolean) {
  const pulse = useMotionValue<number>(PULSE.from)
  useEffect(() => {
    if (reduced) {
      pulse.jump(PULSE.rest)
      return
    }
    const run = animate(pulse, [Math.min(pulse.get(), PULSE.from), PULSE.peak, PULSE.rest], { duration: PULSE.duration, ease: 'easeInOut', times: [0, 0.45, 1] })
    return () => run.stop()
  }, [key, reduced, pulse])
  return pulse
}

/**
 * The overlay's other UI (shortcut bar, pill, cards: everything marked data-hit / data-ui, the same set
 * core reports as overlay.bounds), in window coordinates, so the caption doesn't slide under it.
 * Read from the DOM every 400ms; state changes only when something moved.
 * Local workaround: see "Core requests" in agents/spotlight.md.
 */
function useOtherUi(caption: RefObject<HTMLElement | null>): { rects: Rect[]; drawer?: Rect } {
  const [rects, setRects] = useState<{ rects: Rect[]; drawer?: Rect }>({ rects: [] })
  useLayoutEffect(() => {
    let last = ''
    const read = (): void => {
      const mine = caption.current?.parentElement // the spotlight scene
      const root = mine?.parentElement // the overlay root
      if (!mine || !root) return
      const box = root.getBoundingClientRect()
      if (!box.width) return
      const k = root.offsetWidth / box.width // undo the browser stage's CSS scale (1 in Electron)
      const local = (r: DOMRect): Rect => ({ x: Math.round((r.left - box.left) * k), y: Math.round((r.top - box.top) * k), w: Math.round(r.width * k), h: Math.round(r.height * k) })
      const list = Array.from(root.querySelectorAll<HTMLElement>('[data-hit],[data-ui]'))
        .filter((el) => !mine.contains(el))
        .map((el) => el.getBoundingClientRect())
        .filter((r) => r.width > 1 && r.height > 1)
        .map(local)
      // The open drawer, on whichever side it sits (Michael's #129 lets it move left): captions stay off it.
      const dr = root.querySelector<HTMLElement>('[data-part="drawer"]')?.getBoundingClientRect()
      const next = { rects: list, drawer: dr && dr.width > 40 && dr.height > 40 ? local(dr) : undefined }
      const key = JSON.stringify(next)
      if (key !== last) {
        last = key
        setRects(next)
      }
    }
    read()
    const id = setInterval(read, 400)
    return () => clearInterval(id)
  }, [caption])
  return rects
}

/** `bounds` cut to the side of the drawer the hole is on (by its left edge: a type box may run under the drawer). */
function beside(bounds: Rect, cut: Rect, drawer: Rect): Rect {
  const GAP = 8
  const MIN = 220
  const end = bounds.x + bounds.w
  if (cut.x < drawer.x) {
    const w = Math.min(end, drawer.x - GAP) - bounds.x
    return w >= MIN ? { ...bounds, w } : bounds
  }
  if (cut.x >= drawer.x + drawer.w) {
    const x = Math.max(bounds.x, drawer.x + drawer.w + GAP)
    return end - x >= MIN ? { ...bounds, x, w: end - x } : bounds
  }
  return bounds
}

/** Slide-in direction: from the hole toward where the caption lands. */
const ENTER: Record<Side, { x: number; y: number }> = {
  right: { x: -8, y: 0 },
  left: { x: 8, y: 0 },
  below: { x: 0, y: -8 },
  above: { x: 0, y: 8 },
  inside: { x: 0, y: 0 }
}

/** Snippet rows: one line's height, and the bleed a highlighted row reaches into the padding on each side. */
const SNIPPET = { line: 18, padX: 10, padY: 7, bleed: 4 } as const

/**
 * spotlight.snippet, the code to type at the target (Michael's tests 2-3, A10: "size the popup to its content and
 * highlight the missing line"): sized to the code, every line shown as written (whitespace kept; a line wider than
 * the room wraps instead of being cut). The missing line(s) (code.ts) get the neutral emphasis, `color.text` on
 * `fill.button`, and the rest step back to `color.label`; no hue. Only a snippet taller than the screen is cut, and
 * then it's scrolled so the first missing line shows.
 */
function Snippet({ code, missing, maxHeight }: { code: string; missing: Set<number>; maxHeight: number }): ReactNode {
  const ref = useRef<HTMLPreElement>(null)
  const lines = code.split(/\r?\n/)
  const first = missing.size ? Math.min(...missing) : -1
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const row = first >= 0 ? el.querySelector<HTMLElement>(`[data-line="${first}"]`) : null
    el.scrollTop = row && el.scrollHeight > el.clientHeight ? Math.max(0, row.offsetTop - el.clientHeight / 2) : 0
  })
  return (
    <pre
      ref={ref}
      data-part="snippet"
      className="mb-[3px] mt-[6px] overflow-hidden rounded-[10px] text-[12.5px]"
      style={{
        fontFamily: font.mono,
        background: fill.field,
        lineHeight: `${SNIPPET.line}px`,
        padding: `${SNIPPET.padY}px ${SNIPPET.padX - SNIPPET.bleed}px`,
        whiteSpace: 'pre-wrap',
        overflowWrap: 'anywhere',
        maxHeight
      }}
    >
      {lines.map((l, i) => {
        const hit = missing.has(i)
        return (
          <div
            key={i}
            data-line={i}
            data-missing={hit || undefined}
            className="rounded-[4px]"
            style={{ paddingInline: SNIPPET.bleed, color: hit || !missing.size ? color.text : color.label, background: hit ? fill.button : undefined }}
          >
            {l || ' '}
          </div>
        )
      })}
    </pre>
  )
}

function Caption({ target, hole: cut, bounds: screen, avoid: outside, text: boxed, reduced }: { target: SpotlightTarget; hole: Rect; bounds: Rect; avoid: Rect[]; text: Rect[]; reduced: boolean }): ReactNode {
  const voiceOn = useVoice((s) => s.on)
  // The code lives in one place (Michael's desktop test, item 5): a "Just teach me" lesson or an open drawer has it
  // in the drawer, so the caption shows only the words.
  const textLesson = useLesson((s) => s.lesson?.mode === 'lesson')
  const drawerOpen = useDrawer((s) => s.open)
  const snippet = (!textLesson && !drawerOpen && target.snippet?.replace(/\s+$/, '')) || undefined
  // The step's off-track diff says which line is missing; else the caption may name it in backticks.
  const diff = useLesson((s) => (s.offtrack && s.offtrack.stepId === s.stepId ? s.offtrack.diff : undefined))
  const missing = useMemo(() => (snippet ? missingLines(snippet, diff, target.caption) : new Set<number>()), [snippet, diff, target.caption])
  const ref = useRef<HTMLDivElement>(null)
  const [size, setSize] = useState<{ w: number; h: number }>(CAPTION_GUESS)

  // Measure the real size (the caption hugs its line) so it sits exactly beside the cut-out.
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const measure = (): void => setSize((s) => (s.w === el.offsetWidth && s.h === el.offsetHeight ? s : { w: el.offsetWidth, h: el.offsetHeight }))
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const other = useOtherUi(ref)
  const avoid = [...other.rects, ...outside]
  // Michael's test 8: "Click ▷ to r…" and "Look at how W1,…" ran under the open drawer, and a type box that spans to
  // the drawer's edge showed no caption at all. With the drawer open, the caption's usable area ends at the drawer.
  const bounds = drawerOpen && other.drawer ? beside(screen, cut, other.drawer) : screen
  // Right of the box, in its empty lane: the chip wraps to the lane's width rather than moving to another side.
  // Too narrow a lane (a long line, the docked player): it goes below / above at its own width (place.ts).
  const full = bounds.w - EDGE_MARGIN * 2
  const base = Math.min(snippet ? full : CAPTION_MAX_W, full)
  const lane = rightLane(cut, bounds, avoid, boxed)
  const maxW = lane.room >= (snippet ? SNIPPET_MIN_ROOM : CAPTION_MIN_ROOM) ? Math.min(base, lane.room) : base
  const at = placeCaption(cut, size, bounds, avoid, boxed)
  const from = reduced ? { x: 0, y: 0 } : ENTER[at.side]

  return (
    <motion.div
      ref={ref}
      data-ui
      data-side={at.side}
      className={`absolute left-0 top-0 py-[4px] pl-[11px] ${voiceOn ? 'pr-[4px]' : 'pr-[11px]'}`}
      style={{ maxWidth: maxW, borderRadius: radius.chip, background: color.island, boxShadow: shadows.card }}
      initial={{ opacity: 0, x: at.x + from.x, y: at.y + from.y }}
      animate={{ opacity: 1, x: at.x, y: at.y }}
      transition={reduced ? { duration: 0.2 } : { ...spring, opacity: { duration: 0.2 } }}
    >
      <div className="flex items-center gap-[8px]" style={{ maxWidth: CAPTION_MAX_W }}>
        {/* A one-line chip; up to two lines (three in a narrow lane), then clamped (Michael: one line cut off "Type this in the VS Code terminal (use python…"). */}
        <div
          className="min-w-0 overflow-hidden font-medium leading-[18px]"
          style={{ fontSize: text.xs, color: color.text, display: '-webkit-box', WebkitBoxOrient: 'vertical', WebkitLineClamp: maxW < CAPTION_MAX_W ? CAPTION_LINES + 1 : CAPTION_LINES }}
          title={plain(target.caption)}
        >
          {/* Code in the caption in mono, never literal backticks (A21). */}
          <CodeText text={closeTicks(target.caption)} />
        </div>
        {/* Only while voice is on: white, like every toggle that's on. Tap to turn it off. */}
        {voiceOn && (
          <button
            data-hit
            className="pointer-events-auto -my-[1px] grid h-[20px] w-[20px] shrink-0 cursor-pointer place-items-center rounded-full"
            style={{ background: color.accent, color: color.onAccent }}
            onClick={toggleVoice}
            aria-label="Turn voice off"
          >
            <Volume2 size={12} />
          </button>
        )}
      </div>
      {/* The code to type there (Show me in a video lesson): monospace under the caption, like the cards' diff. */}
      {snippet && <Snippet code={snippet} missing={missing} maxHeight={Math.max(SNIPPET.line * 3, bounds.h - EDGE_MARGIN * 2 - CAPTION_GUESS.h - 16)} />}
    </motion.div>
  )
}

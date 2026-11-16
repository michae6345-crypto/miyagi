/**
 * Feature: loupe. A tiny spotlight target (VS Code's ▷ Run button is ~22 pt) is easy to miss even with the cut-out,
 * so next to it we draw a callout: the target's ring 2.25x bigger with the button's glyph on a keycap, and a short
 * arrow to the real button (Michael, run-step feedback, Sun 3:03 AM).
 *
 * Drawn, not captured: Michael asked for no Screen Recording permission before the demo, so there are no real pixels
 * here, only the ring, the arrow and the glyph taken from the caption ("Click ▷ to run nn.py").
 *
 * When: the spotlight carries `zoom: true` (an additive field the engine sends on the Run-button spotlight), or its
 * target's larger side is under 32 pt. It lives and dies with the spotlight (same store), and steps back while the
 * ask panel is open, like the caption.
 *
 * Its own folder and overlay layer (z 11, just above the spotlight's dim at 10) so it doesn't touch
 * features/spotlight/Spotlight.tsx. The callout is data-ui, so the spotlight caption keeps clear of it.
 */
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import type { ReactNode } from 'react'
import type { Layout } from '../../../../preload/api'
import type { Rect } from '../../core/lesson'
import { defineFeature } from '../../core/registry'
import { color, fill, radius, shadows, spring, text } from '../../core/theme'
import { useLauncherOpen } from '../launcher/store'
import { hole, holeRadius, isUsableRect, MIN_VISIBLE_SHARE, overlapShare, toLocal } from '../spotlight/place'
import { useSpotlight } from '../spotlight/store'
import { arrow, glyphFrom, PAD, placeCallout, ringSize, wantsZoom } from './place'

const ASKING_OPACITY = 0.3
/** The arrow: a white hairline over a faint dark keyline (the spotlight ring's recipe), with a small open head. */
const LINE = { width: 1.5, keyline: 3.5, keylineOpacity: 0.35, head: 7 } as const

function LoupeLayer({ layout }: { layout: Layout }): ReactNode {
  const t = useSpotlight((s) => s.target)
  const asking = useLauncherOpen()
  const reduced = useReducedMotion() ?? false
  const screen = { x: 0, y: 0, w: layout.width, h: layout.height }
  const wa = layout.workArea
  const bounds = { x: wa.x, y: wa.y, w: wa.width, h: wa.height }
  // The same "is it on this display" test as the spotlight layer, so the loupe never shows without its cut-out.
  const local = t && isUsableRect(t.rect) ? toLocal(t.rect, layout.origin) : undefined
  const here = local && overlapShare(hole(local), screen) >= MIN_VISIBLE_SHARE ? local : undefined
  const on = !!(t && here && wantsZoom(here, (t as { zoom?: unknown }).zoom))
  const key = here ? `${Math.round(here.x)},${Math.round(here.y)}` : 'none'

  return (
    <AnimatePresence>
      {on && here && (
        <motion.div
          key={key}
          className="pointer-events-none absolute inset-0"
          data-loupe
          initial={{ opacity: 0 }}
          animate={{ opacity: asking ? ASKING_OPACITY : 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
        >
          <Callout target={here} glyph={glyphFrom(t?.caption)} bounds={bounds} reduced={reduced} />
        </motion.div>
      )}
    </AnimatePresence>
  )
}

function Callout({ target, glyph, bounds, reduced }: { target: Rect; glyph?: string; bounds: Rect; reduced: boolean }): ReactNode {
  const ring = ringSize(target)
  const box = placeCallout(hole(target), { w: ring.w + PAD * 2, h: ring.h + PAD * 2 }, bounds)
  const line = arrow(box, hole(target))
  // Grow out of the real button: start at its center, small, and spring to the callout.
  const from = { x: target.x + target.w / 2 - (box.x + box.w / 2), y: target.y + target.h / 2 - (box.y + box.h / 2) }
  const rr = holeRadius({ x: 0, y: 0, w: ring.w, h: ring.h })

  return (
    <>
      {line && (
        <svg className="absolute inset-0 h-full w-full" aria-hidden data-part="loupe-arrow">
          <motion.g initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.2, delay: reduced ? 0 : 0.12 }}>
            <Arrow from={line.from} to={line.to} stroke={color.onAccent} width={LINE.keyline} opacity={LINE.keylineOpacity} />
            <Arrow from={line.from} to={line.to} stroke={color.text} width={LINE.width} opacity={1} />
          </motion.g>
        </svg>
      )}
      <motion.div
        data-ui
        data-part="loupe"
        className="absolute left-0 top-0 grid place-items-center"
        style={{ width: box.w, height: box.h, background: color.island, borderRadius: radius.card, boxShadow: shadows.card, border: `1px solid ${fill.chipBorder}` }}
        initial={reduced ? { opacity: 0, x: box.x, y: box.y } : { opacity: 0, scale: 0.4, x: box.x + from.x, y: box.y + from.y }}
        animate={{ opacity: 1, scale: 1, x: box.x, y: box.y }}
        transition={reduced ? { duration: 0.2 } : { ...spring, opacity: { duration: 0.15 } }}
      >
        {/* The target, enlarged: the spotlight's hairline ring, with the button's glyph on a keycap inside. */}
        <div
          className="grid place-items-center"
          style={{ width: ring.w, height: ring.h, borderRadius: rr, border: `1px solid ${color.text}` }}
        >
          {glyph && (
            <span
              className="grid place-items-center font-medium"
              style={{
                minWidth: Math.round(Math.min(ring.w, ring.h) * 0.62),
                height: Math.round(Math.min(ring.w, ring.h) * 0.62),
                padding: '0 6px',
                borderRadius: 8,
                background: fill.key,
                color: color.text,
                fontSize: text.md,
                lineHeight: 1
              }}
            >
              {glyph}
            </span>
          )}
        </div>
      </motion.div>
    </>
  )
}

/** A straight line with an open arrowhead at `to`. */
function Arrow({ from, to, stroke, width, opacity }: { from: { x: number; y: number }; to: { x: number; y: number }; stroke: string; width: number; opacity: number }): ReactNode {
  const a = Math.atan2(to.y - from.y, to.x - from.x)
  const h = LINE.head
  const wing = (s: number): string => `${to.x - h * Math.cos(a + s * 0.5)},${to.y - h * Math.sin(a + s * 0.5)}`
  return (
    <g style={{ stroke }} strokeOpacity={opacity} strokeWidth={width} strokeLinecap="round" strokeLinejoin="round" fill="none">
      <line x1={from.x} y1={from.y} x2={to.x} y2={to.y} />
      <polyline points={`${wing(1)} ${to.x},${to.y} ${wing(-1)}`} />
    </g>
  )
}

export default defineFeature({ id: 'loupe', overlayLayers: [{ id: 'loupe', z: 11, Component: LoupeLayer }] })

/**
 * Feature: drawer. The Diagram flyout (Michael, Nov 15 7 AM: "I want to click the diagram button, for that to pop up,
 * and for it to come off of the right side panel"). It opens only from the Diagram button (diagrams/store.ts) and slides
 * out from behind the drawer's inner edge: the left edge when the drawer is on the right, the right edge when it's on
 * the left. Top-aligned with the drawer, the same glass and radius, tucked OVERLAP under it so the two read as one
 * piece. On a run step (drawer tucked to its handle) it slides out from the handle's edge instead, below RUN_DROP so
 * VS Code's Run ▷ stays clear and above the terminal (RUN_SHARE). Transform and opacity only, the one spring.
 *
 * The live network draws in glass ink (NetBody) and redraws in place while open. Every other kind is drawn by the
 * island renderers (dark ink, 600 px wide), so it sits in a dark well scaled to the flyout's width, as the concept
 * panel does. Labels all come from the data.
 */
import { motion } from 'motion/react'
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { Waypoints, X } from 'lucide-react'
import type { Layout } from '../../../../preload/api'
import { bridge } from '../../bridge'
import { islandBottom } from '../../core/islandEdge'
import { useLesson, type Rect } from '../../core/lesson'
import { dockRect } from '../player/dock'
import { actionTone, color, glass, radius, spring, springOut } from '../../core/theme'
import { DiagramBody } from '../diagrams/Diagram'
import { closeDiagram, isLiveNetwork, useDiagram, type DiagramPayload } from '../diagrams/store'
import { DiagramTabs, titleOf } from '../diagrams/Tabs'
import { useBarTop } from '../shortcut-bar/lift'
import { NetBody } from './LiveNet'
import { RUN_DROP, RUN_SHARE } from './runTuck'
import type { Side } from './store'
import { fade } from '../../core/ui/motion'

/** About the width of a lesson's drawer (mockup 01), clamped to the room beside the drawer. */
export const FLY_W = 420
const MIN_W = 260
/** The drawer's inset from the work area's edge; the flyout keeps the same air on its far side. */
const EDGE = 8
/** How far the flyout tucks under the drawer (or the handle): its rounded inner corners hide behind it. */
const OVERLAP = radius.card
const PAD = 16
/** The island renderers draw at the island's content width (640 - 2 x 20). */
const ISLAND_W = 600
/** A run step's box starts where the old floating card did: under the notch band, then RUN_DROP lower. */
const RUN_TOP = 24
/** Air between the box and the shortcut bar's top edge. */
const BAR_GAP = 12
/** The resting step pill: about this far either side of the screen's center, this tall, from the island's top. */
const PILL_HALF = 180
/** The old step pill was 36 tall against the island's 34: the flyout keeps those 2 px of air under it. */
const PILL_SLACK = 2
const PILL_GAP = 10

/**
 * side: the edge the drawer is drawn on. anchor: the drawer panel's rect (its max height), or on a run step the
 * tucked handle's rect.
 */
export function Flyout({ layout, side, anchor, run }: { layout: Layout; side: Side; anchor: Rect; run: boolean }): ReactNode {
  const d = useDiagram((s) => s.diagram)
  const barTop = useBarTop(layout)
  const wa = layout.workArea
  // A video lesson's player is docked on the right (player/dock.ts) and is wider than the drawer: the flyout never
  // covers it. With the drawer on the right it opens beside the player's left edge, toward the code; on the left it
  // stops short of the player.
  const video = useLesson((s) => !!s.lesson && s.lesson.mode !== 'lesson')
  const dock = video ? dockRect(wa) : undefined
  const lo = Math.max(0, wa.x) + EDGE
  const hi = Math.min(layout.width, wa.x + wa.width, dock ? dock.x : Infinity) - EDGE
  // The flyout's inner edge: tucked OVERLAP under the drawer (or the handle), or beside the player's left edge.
  const tucked = side === 'right' ? anchor.x + OVERLAP : anchor.x + anchor.w - OVERLAP
  const inner = side === 'right' && dock ? Math.min(tucked, dock.x - EDGE) : tucked
  const attached = inner === tucked
  const room = side === 'right' ? inner - lo : hi - inner
  const x0 = side === 'right' ? inner - Math.min(FLY_W, room) : inner
  // Top-aligned with the drawer, unless that would put the header under the step pill (centered, at pillTop: on a
  // Mac the pill's band and the drawer's top overlap): then it starts just under the pill.
  const underPill = x0 < layout.width / 2 + PILL_HALF && x0 + Math.min(FLY_W, room) > layout.width / 2 - PILL_HALF
  const pillClear = islandBottom(layout) + PILL_SLACK + PILL_GAP
  const top = run ? wa.y + RUN_TOP + RUN_DROP : underPill ? Math.max(anchor.y, pillClear) : anchor.y
  const bottom = run ? Math.min(wa.y + wa.height * RUN_SHARE, barTop - BAR_GAP) : anchor.y + anchor.h
  const maxH = Math.max(160, bottom - top)
  const base = Math.max(Math.min(MIN_W, room), Math.min(FLY_W, room))
  // Too tall for its box (a run step's room above the terminal): narrower, so the scaled drawing gets shorter.
  const [fit, setFit] = useState<number | undefined>(undefined)
  const w = Math.min(base, fit ?? base)
  const x = side === 'right' ? inner - w : inner
  const content = useRef<HTMLDivElement>(null)
  const kind = d?.kind
  useEffect(() => setFit(undefined), [kind, maxH])
  useLayoutEffect(() => {
    const el = content.current
    if (!el) return
    const check = (): void => {
      const h = el.offsetHeight
      if (h > maxH + 4 && w > MIN_W) setFit(Math.max(MIN_W, Math.floor((w * maxH) / h)))
    }
    check()
    const ro = new ResizeObserver(check)
    ro.observe(el)
    return () => ro.disconnect()
  }, [w, maxH])
  // Out from behind the drawer (or the handle), and back in on close.
  const away = (side === 'right' ? 1 : -1) * (w - OVERLAP)
  const joined = side === 'right' ? 'paddingRight' : 'paddingLeft'
  const far = side === 'right' ? 'paddingLeft' : 'paddingRight'
  if (!d) return null
  return (
    <motion.div
      data-hit
      data-part="diagram-flyout"
      data-side={side}
      data-run={run ? '' : undefined}
      className="absolute overflow-y-auto overflow-x-hidden border"
      style={{
        left: x,
        top,
        width: w,
        maxHeight: maxH,
        borderRadius: radius.card,
        background: glass.bg,
        borderColor: glass.hairline,
        // The drawer's own glass: an inset layer of the same token makes it ~opaque (no blur over other windows).
        boxShadow: `${glass.shadow}, inset 0 0 0 ${w}px ${glass.bg}`,
        color: glass.text,
        [far]: PAD,
        [joined]: attached ? OVERLAP + PAD - 4 : PAD,
        scrollbarWidth: 'thin'
      }}
      initial={{ x: away, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      exit={{ x: away, opacity: 0, transition: { ...springOut, opacity: fade.in } }}
      transition={{ ...spring, opacity: fade.in }}
    >
      <div ref={content} className="pb-[12px] pt-[12px]">
        <div className="flex min-w-0 items-center gap-[10px] pb-[10px]">
          <span className="grid h-[24px] w-[24px] shrink-0 place-items-center rounded-[7px]" style={{ background: actionTone.diagram, color: color.onPastel }}>
            <Waypoints size={13} strokeWidth={1.9} />
          </span>
          <DiagramTabs glassy fallback={<span className="min-w-0 truncate text-[14px] font-semibold" style={{ color: glass.text }}>{titleOf(d)}</span>} />
          {(d.data as Record<string, unknown> | undefined)?.preview === true && (
            <span className="shrink-0 text-[12px]" style={{ color: glass.faint }}>
              Preview
            </span>
          )}
          <span className="flex-1" />
          <button
            type="button"
            data-part="diagram-flyout-close"
            className="grid h-[22px] w-[22px] shrink-0 cursor-pointer place-items-center rounded-full"
            style={{ background: glass.key, color: glass.keyText }}
            onMouseDown={(e) => e.preventDefault()}
            onClick={closeDiagram}
            aria-label="Close diagram"
            title="Close"
          >
            <X size={12} strokeWidth={2.2} />
          </button>
        </div>
        {isLiveNetwork(d) ? <NetBody d={d} /> : <IslandWell d={d} />}
      </div>
    </motion.div>
  )
}

/** An island-ink diagram (graph, gradients, heatmap, a static network) in a dark well, scaled to fit the flyout. */
function IslandWell({ d }: { d: DiagramPayload }): ReactNode {
  const box = useRef<HTMLDivElement>(null)
  const [k, setK] = useState(1)
  useLayoutEffect(() => {
    const el = box.current
    if (!el) return
    // Scale by the drawing's own width (an svg's width attribute; the island's 600 otherwise), so a narrow one
    // isn't shrunk for nothing.
    const measure = (): void => {
      const natural = Number(el.querySelector('svg')?.getAttribute('width')) || ISLAND_W
      setK(Math.min(1, el.clientWidth / natural))
    }
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [d])
  return (
    <>
      <div data-part="diagram-flyout-well" className="overflow-hidden px-[10px] py-[12px]" style={{ background: color.island, borderRadius: radius.chip }}>
        <div ref={box}>
          <div style={{ zoom: k }}>
            <DiagramBody d={d} />
          </div>
        </div>
      </div>
      {d.caption && (
        <div className="mt-[8px] line-clamp-3 break-words text-[12.5px] leading-[17px]" style={{ color: glass.label }}>
          {d.caption}
        </div>
      )}
    </>
  )
}

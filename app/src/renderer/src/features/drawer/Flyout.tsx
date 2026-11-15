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
import type { Rect } from '../../core/lesson'
import { actionTone, color, glass, radius, spring, springOut } from '../../core/theme'
import { DiagramBody } from '../diagrams/Diagram'
import { closeDiagram, isLiveNetwork, useDiagram, type DiagramPayload } from '../diagrams/store'
import { DiagramTabs, titleOf } from '../diagrams/Tabs'
import { useBarTop } from '../shortcut-bar/lift'
import { NetBody } from './LiveNet'
import { RUN_DROP, RUN_SHARE } from './runTuck'
import type { Side } from './store'

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

/**
 * side: the edge the drawer is drawn on. anchor: the drawer panel's rect (its max height), or on a run step the
 * tucked handle's rect.
 */
export function Flyout({ layout, side, anchor, run }: { layout: Layout; side: Side; anchor: Rect; run: boolean }): ReactNode {
  const d = useDiagram((s) => s.diagram)
  const barTop = useBarTop(layout)
  const wa = layout.workArea
  const lo = Math.max(0, wa.x) + EDGE
  const hi = Math.min(layout.width, wa.x + wa.width) - EDGE
  // Room on the inner side of the drawer (or the handle), counting the strip that tucks under it.
  const room = side === 'right' ? anchor.x + OVERLAP - lo : hi - (anchor.x + anchor.w - OVERLAP)
  const top = run ? wa.y + RUN_TOP + RUN_DROP : anchor.y
  const bottom = run ? Math.min(wa.y + wa.height * RUN_SHARE, barTop - BAR_GAP) : anchor.y + anchor.h
  const maxH = Math.max(160, bottom - top)
  const base = Math.max(Math.min(MIN_W, room), Math.min(FLY_W, room))
  // Too tall for its box (a run step's room above the terminal): narrower, so the scaled drawing gets shorter.
  const [fit, setFit] = useState<number | undefined>(undefined)
  const w = Math.min(base, fit ?? base)
  const x = side === 'right' ? anchor.x + OVERLAP - w : anchor.x + anchor.w - OVERLAP
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
        [joined]: OVERLAP + PAD - 4,
        scrollbarWidth: 'thin'
      }}
      initial={{ x: away, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      exit={{ x: away, opacity: 0, transition: { ...springOut, opacity: { duration: 0.18 } } }}
      transition={{ ...spring, opacity: { duration: 0.18 } }}
    >
      <div ref={content} className="pb-[12px] pt-[12px]">
        <div className="flex min-w-0 items-center gap-[10px] pb-[10px]">
          <span className="grid h-[24px] w-[24px] shrink-0 place-items-center rounded-[7px]" style={{ background: actionTone.diagram, color: color.onAccent }}>
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
    const measure = (): void => setK(Math.min(1, el.clientWidth / ISLAND_W))
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
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

/**
 * Feature: skills. The tree views' one canvas (Path and Map differ only in their input and orientation, graphInput.ts).
 *
 *   fit        on open, on a new size and on Fit: the gaps stretch to fill the view (layout.ts placeGraph); a tree too big
 *              even at its tightest opens at the view's lowest readable scale, centered on NEXT, and pans from there
 *   zoom/pan   + / − / fit buttons (bottom right), pinch or Cmd/Ctrl + wheel to zoom at the pointer, wheel or drag to pan
 *   edges      one curve style (layout.ts edgePath) under the nodes: green between two mastered skills, ink into what you
 *              can start, dashed and faint into what is still locked. Links set aside to keep the tree flat (layout
 *              `hidden`) show only while their node is hovered or open
 *   focus      the open skill keeps its prerequisites and what it opens lit; the rest steps back. Search does the same
 *              for the skills it matches
 *   headers    the Map names its tracks in one quiet row across the top, each over its own skills (hover one to light
 *              that track)
 *   unlock     unseen events play once, oldest first: the node fills green and its edges draw out, a dashed ring closes,
 *              and one line says what happened. Then skills.ack. Reduced motion: a short fade, same line
 */
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { Maximize2, Minus, Plus } from 'lucide-react'
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { color, duration, ease, elevation, fill, highlight, radius2, spring, type2 } from '../../core/theme'
import { pressMotion } from '../../core/ui/motion'
import { chainLength, edgePath, isDummy, layoutGraph, placeGraph } from './layout'
import { labelWidth, mapInput, pathInput, PLACE, SIZES, TRUNK, type TreeView } from './graphInput'
import type { SkillGraph, SkillGraphNode } from './model'
import { stateLine, unlockLine } from './copy'
import { SkillNode, TrunkPoint, type NodeAnim } from './SkillNode'
import { ackEvents } from './store'

/** Room for the Map's track names above the tree. */
const HEAD = 34
const ZOOM_MIN = 0.25
/** Room kept for the zoom controls (32 wide, 16 from the edge) on each side of the tree. */
const RESERVE = 40
const ZOOM_MAX = 2.2
/** Per event: the fill (280), the edges drawing out (360), a beat between events. */
const STEP_S = 0.9

/** k, dx, dy: the learner's zoom and pan on top of the fit. all: Fit was pressed (the whole tree, however small). */
type View = { k: number; dx: number; dy: number; smooth: boolean; all?: boolean }
const REST: View = { k: 1, dx: 0, dy: 0, smooth: false }
/** Below this fitted scale a tree opens at its view's readable scale instead (and Fit still shows all of it). */
const OPEN_ALL: Record<TreeView, number> = { path: 0.5, map: 0.6 }

function useBox<T extends HTMLElement>(): [React.RefObject<T | null>, { w: number; h: number }] {
  const ref = useRef<T>(null)
  const [box, setBox] = useState({ w: 0, h: 0 })
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const read = (): void => setBox((b) => (b.w === el.clientWidth && b.h === el.clientHeight ? b : { w: el.clientWidth, h: el.clientHeight }))
    read()
    const ro = new ResizeObserver(read)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  return [ref, box]
}

type EdgeLook = { stroke: string; width: number; dash?: string; opacity: number }
function edgeLook(a: SkillGraphNode | undefined, b: SkillGraphNode | undefined): EdgeLook {
  const from = !a || a.state === 'mastered'
  if (from && b?.state === 'mastered') return { stroke: color.green, width: 2, opacity: 0.85 }
  if (from && b && (b.state === 'ready' || b.state === 'practicing')) return { stroke: color.text, width: 1.75, opacity: 0.5 }
  return { stroke: color.faint, width: 1.5, dash: '3 5', opacity: 0.7 }
}

export function TreeCanvas({ g, view, query, selected, onOpen }: { g: SkillGraph; view: TreeView; query: string; selected?: string; onOpen: (id: string) => void }): ReactNode {
  const reduce = useReducedMotion() ?? false
  const [ref, box] = useBox<HTMLDivElement>()
  const [hover, setHover] = useState<string>()
  const [hoverTrack, setHoverTrack] = useState<string>()
  const [v, setV] = useState<View>(REST)
  const autoPan = useRef(0)
  const size = SIZES[view]

  const input = useMemo(() => (view === 'path' ? pathInput(g) : mapInput(g)), [g, view])
  const layout = useMemo(() => layoutGraph(input.nodes, input.links), [input])
  const head = view === 'map' ? HEAD : 0
  // The zoom controls own the bottom-right corner: the tree keeps RESERVE clear on both sides, so it stays centered.
  const placed = useMemo(() => (box.w && box.h ? placeGraph(layout, { ...PLACE[view]({ w: Math.max(200, box.w - 2 * RESERVE), h: box.h - head }, layout, input), widenFrom: OPEN_ALL[view] }) : undefined), [layout, input, view, box, head])

  // Fit: on a new size, a new view or a new tree (never while the learner is zoomed in on the same one).
  useEffect(() => {
    autoPan.current = 0
    setV(REST)
  }, [box.w, box.h, view, layout])

  const fit = useMemo(() => {
    if (!placed) return { s: 1, tx: 0, ty: 0 }
    const W = placed.w
    const H = placed.h + head
    if (v.all || placed.scale >= OPEN_ALL[view]) return { s: placed.scale, tx: (box.w - W * placed.scale) / 2, ty: (box.h - H * placed.scale) / 2 }
    // Too big to read whole: open at the readable scale between NEXT and the goal, kept inside the content's edges.
    const s = size.minScale
    const a = placed.at[g.next?.skillId ?? ''] ?? placed.at[g.goal?.id ?? '']
    const b = placed.at[g.goal?.id ?? ''] ?? a
    const focus = a && b ? { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 } : { x: W / 2, y: H / 2 }
    const clampT = (t: number, view: number, content: number): number => (content * s <= view ? (view - content * s) / 2 : Math.min(0, Math.max(view - content * s, t)))
    return { s, tx: clampT(box.w / 2 - focus.x * s, box.w, W), ty: clampT(box.h / 2 - (focus.y + head) * s, box.h, H) }
  }, [placed, box, head, size.minScale, g.next, g.goal, v.all, view])

  const scale = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, fit.s * v.k))
  // Zoom keeps the view's center (or the pointer) still: dx/dy are offsets on top of the fitted translate.
  const tx = fit.tx + v.dx
  const ty = fit.ty + v.dy
  const zoomAt = (factor: number, px = box.w / 2, py = box.h / 2, smooth = true): void =>
    setV((cur) => {
      const s0 = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, fit.s * cur.k))
      const s1 = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, s0 * factor))
      const x0 = fit.tx + cur.dx
      const y0 = fit.ty + cur.dy
      const x1 = px - ((px - x0) / s0) * s1
      const y1 = py - ((py - y0) / s0) * s1
      return { ...cur, k: s1 / fit.s, dx: x1 - fit.tx, dy: y1 - fit.ty, smooth }
    })

  // An opened skill never hides under the panel (it covers the view's right, up to 380 px + 16): glide it into the open
  // part, and glide back when the panel closes.
  useEffect(() => {
    if (!selected) {
      const back = autoPan.current
      autoPan.current = 0
      if (back) setV((cur) => ({ ...cur, dx: cur.dx - back, smooth: true }))
      return
    }
    if (!placed?.at[selected]) return
    const p = placed.at[selected]
    const free = box.w - Math.min(396, box.w - 32)
    const sx = tx + p.x * scale
    if (sx > 40 && sx < free - 40) return
    const shift = free / 2 - sx
    autoPan.current += shift
    setV((cur) => ({ ...cur, dx: cur.dx + shift, smooth: true }))
    // Only when the selection changes, not on every pan.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected])

  // Wheel: pan; pinch (ctrlKey) or Cmd/Ctrl + wheel: zoom at the pointer. Non-passive so the page never scrolls instead.
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const onWheel = (e: WheelEvent): void => {
      e.preventDefault()
      const r = el.getBoundingClientRect()
      if (e.ctrlKey || e.metaKey) zoomAt(Math.exp(-e.deltaY * 0.01), e.clientX - r.left, e.clientY - r.top, false)
      else setV((cur) => ({ ...cur, dx: cur.dx - e.deltaX, dy: cur.dy - e.deltaY, smooth: false }))
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  })

  // Drag to pan, from anywhere that isn't a node or a control.
  const drag = useRef<{ x: number; y: number; dx: number; dy: number } | null>(null)
  const onPointerDown = (e: React.PointerEvent): void => {
    if (e.button !== 0 || (e.target as HTMLElement).closest('button')) return
    drag.current = { x: e.clientX, y: e.clientY, dx: v.dx, dy: v.dy }
    ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
  }
  const onPointerMove = (e: React.PointerEvent): void => {
    const d = drag.current
    if (!d) return
    setV((cur) => ({ ...cur, dx: d.dx + e.clientX - d.x, dy: d.dy + e.clientY - d.y, smooth: false }))
  }
  const onPointerUp = (): void => {
    drag.current = null
  }

  // Focus: the open skill (or a hovered track, or the search) keeps its neighbourhood lit.
  const lit = useMemo(() => {
    if (selected && g.byId[selected]) {
      const n = g.byId[selected]
      const out = new Set([n.id, ...n.requires])
      for (const l of g.links) if (l.from === n.id) out.add(l.to)
      return out
    }
    if (hoverTrack) return new Set(g.nodes.filter((n) => n.track === hoverTrack).map((n) => n.id))
    const q = query.trim().toLowerCase()
    if (q) return new Set(g.nodes.filter((n) => n.label.toLowerCase().includes(q)).map((n) => n.id))
    return undefined
  }, [selected, hoverTrack, query, g])

  // The unlock motion: the events whose skills are on this view, oldest first, each one step after the last.
  const [events] = useState(() => g.events)
  const anims = useMemo(() => {
    const m = new Map<string, NodeAnim>()
    events.forEach((e, i) => {
      if (!placed?.at[e.skillId]) return
      if (e.kind === 'mastered' || e.kind === 'capstone_done') m.set(e.skillId, { kind: 'fill', delay: 0.3 + i * STEP_S })
      else if (e.kind === 'unlocked') m.set(e.skillId, { kind: 'close', delay: 0.3 + i * STEP_S })
    })
    return m
  }, [events, placed])
  const lastEvent = events[events.length - 1]
  const lastLine = lastEvent && g.byId[lastEvent.skillId] ? unlockLine(lastEvent.kind, g.byId[lastEvent.skillId].label) : undefined
  const [say, setSay] = useState(false)
  useEffect(() => {
    if (!events.length) return
    const total = 0.3 + events.length * STEP_S
    const show = setTimeout(() => setSay(true), (reduce ? 0.2 : total - 0.4) * 1000)
    const hide = setTimeout(() => setSay(false), (total + 3.2) * 1000)
    const ack = setTimeout(() => ackEvents({ ...g, events }), (total + 0.2) * 1000)
    return () => {
      clearTimeout(show)
      clearTimeout(hide)
      clearTimeout(ack)
    }
    // Once per mount: the events this canvas opened with.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Track names across the top of the Map, each over the mean of its skills, pushed apart so none overlap.
  const headers = useMemo(() => {
    if (view !== 'map' || !placed) return []
    const hs = g.tracks
      .map((t) => {
        const xs = t.nodeIds.map((id) => placed.at[id]?.x).filter((x): x is number => x !== undefined)
        const w = t.label.length * 7 + 44
        return xs.length ? { id: t.id, label: t.label, x: xs.reduce((a, x) => a + x, 0) / xs.length, w, t } : undefined
      })
      .filter((h): h is NonNullable<typeof h> => !!h)
      .sort((a, b) => a.x - b.x)
    for (let pass = 0; pass < 8; pass++)
      for (let i = 1; i < hs.length; i++) {
        const need = (hs[i - 1].w + hs[i].w) / 2 + 12 - (hs[i].x - hs[i - 1].x)
        if (need > 0) {
          hs[i - 1].x -= need / 2
          hs[i].x += need / 2
        }
      }
    return hs
  }, [view, placed, g.tracks])

  const focusIds = new Set([hover, selected].filter((x): x is string => !!x))
  const nodeR = (n: SkillGraphNode): number => (n.id === input.hero ? size.heroR : n.kind === 'capstone' ? size.nodeR + 2 : size.nodeR)
  const nodeLine = (n: SkillGraphNode): string => stateLine(n, g)
  const lw = (hero: boolean): number => (placed ? labelWidth(view, hero, placed) : size.labelW)

  return (
    <div
      ref={ref}
      data-skills-canvas={view}
      className="relative h-full w-full touch-none select-none overflow-hidden"
      style={{ cursor: drag.current ? 'grabbing' : 'grab' }}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
    >
      {placed && (
        <div
          className="absolute left-0 top-0"
          style={{
            width: placed.w,
            height: placed.h + head,
            transformOrigin: '0 0',
            transform: `translate(${tx}px, ${ty}px) scale(${scale})`,
            // Buttons and Fit glide (the house curve); wheel, pinch and drag follow the hand.
            transition: v.smooth && !reduce ? `transform ${duration.slow + 0.1}s cubic-bezier(${ease.out.join(',')})` : undefined
          }}
        >
          {headers.map((h) => (
            <button
              key={h.id}
              type="button"
              data-skills-track={h.id}
              className="absolute flex cursor-default items-baseline justify-center gap-[6px] whitespace-nowrap"
              style={{ left: h.x - h.w / 2, top: 6, width: h.w, height: 22, fontSize: type2.xs, fontWeight: 500, color: hoverTrack === h.id ? color.text : color.label }}
              onPointerEnter={() => setHoverTrack(h.id)}
              onPointerLeave={() => setHoverTrack(undefined)}
            >
              {h.label}
              <span style={{ fontSize: type2.micro, color: color.faint, fontVariantNumeric: 'tabular-nums' }}>
                {h.t.mastered}/{h.t.total}
              </span>
            </button>
          ))}
          <div className="absolute left-0" style={{ top: head, width: placed.w, height: placed.h }}>
            <svg width={placed.w} height={placed.h} className="absolute inset-0 overflow-visible" aria-hidden>
              {layout.edges.map((e) => {
                const pts = e.chain.map((id) => placed.at[id])
                const look = edgeLook(g.byId[e.from], g.byId[e.to])
                const dimmed = lit && !(lit.has(e.from) && lit.has(e.to))
                const a = anims.get(e.from)
                const drawIn = a?.kind === 'fill'
                const len = chainLength(pts)
                return (
                  <motion.path
                    key={`${e.from}>${e.to}`}
                    d={edgePath(pts, size.orientation)}
                    fill="none"
                    stroke={look.stroke}
                    strokeWidth={look.width}
                    strokeDasharray={look.dash}
                    strokeLinecap="round"
                    initial={drawIn ? (reduce ? { opacity: 0 } : { pathLength: 0, opacity: 0 }) : false}
                    // pathLength only while drawing in: it rewrites the dash array, which would erase a dashed edge.
                    animate={drawIn ? { pathLength: 1, opacity: dimmed ? look.opacity * 0.25 : look.opacity } : { opacity: dimmed ? look.opacity * 0.25 : look.opacity }}
                    transition={drawIn ? { duration: reduce ? 0.12 : Math.min(0.6, 0.24 + len / 1600), ease: ease.out, delay: a!.delay + (reduce ? 0 : 0.28), opacity: { duration: 0.1, delay: a!.delay + 0.28 } } : { duration: 0.18 }}
                  />
                )
              })}
              {layout.hidden
                .filter((l) => focusIds.has(l.from) || focusIds.has(l.to))
                .map((l) => {
                  const a = placed.at[l.from]
                  const b = placed.at[l.to]
                  if (!a || !b) return null
                  const look = edgeLook(g.byId[l.from], g.byId[l.to])
                  return <path key={`h-${l.from}>${l.to}`} d={edgePath([a, b], size.orientation)} fill="none" stroke={look.stroke} strokeWidth={look.width} strokeDasharray={look.dash} strokeLinecap="round" opacity={look.opacity} />
                })}
            </svg>
            {Object.values(layout.items).map((it) => {
              if (isDummy(it.id)) return null
              const at = placed.at[it.id]
              if (it.id === TRUNK) return <TrunkPoint key={it.id} x={at.x} y={at.y} />
              const n = g.byId[it.id]
              if (!n) return null
              const hero = it.id === input.hero
              return (
                <SkillNode
                  key={it.id}
                  n={n}
                  x={at.x}
                  y={at.y}
                  r={nodeR(n)}
                  hero={hero}
                  labelW={lw(hero)}
                  lines={hero ? 2 : size.lines}
                  line={nodeLine(n)}
                  dim={!!lit && !lit.has(n.id)}
                  focused={selected === n.id && !n.isNext}
                  anim={anims.get(n.id)}
                  onOpen={onOpen}
                  onHover={setHover}
                />
              )
            })}
          </div>
        </div>
      )}

      <AnimatePresence>
        {say && lastLine && (
          <motion.div
            key="unlock-line"
            role="status"
            data-skills-unlock-line
            className="pointer-events-none absolute left-1/2 whitespace-nowrap"
            style={{ bottom: 20, x: '-50%', padding: '8px 14px', borderRadius: radius2.row, background: color.text, color: 'var(--l-raised)', fontSize: type2.sm, fontWeight: 500, boxShadow: elevation.overlay }}
            initial={reduce ? { opacity: 0 } : { opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={reduce ? { duration: 0.15 } : spring}
          >
            {lastLine}
          </motion.div>
        )}
      </AnimatePresence>

      <ZoomControls onIn={() => zoomAt(1.2)} onOut={() => zoomAt(1 / 1.2)} onFit={() => setV({ ...REST, smooth: true, all: true })} />
    </div>
  )
}

function ZoomButton({ label, onClick, children }: { label: string; onClick: () => void; children: ReactNode }): ReactNode {
  return (
    <motion.button
      type="button"
      aria-label={label}
      title={label}
      className="mg-press flex cursor-pointer items-center justify-center"
      style={{ width: 32, height: 32, color: color.label }}
      onClick={onClick}
      {...pressMotion()}
    >
      {children}
    </motion.button>
  )
}

function ZoomControls({ onIn, onOut, onFit }: { onIn: () => void; onOut: () => void; onFit: () => void }): ReactNode {
  return (
    <div
      data-skills-zoom
      className="absolute flex flex-col overflow-hidden"
      style={{ right: 16, bottom: 16, borderRadius: radius2.row, background: 'var(--l-overlay)', boxShadow: `${highlight.card}, inset 0 0 0 1px var(--l-border), ${elevation.raised}` }}
    >
      <ZoomButton label="Zoom in" onClick={onIn}>
        <Plus size={15} strokeWidth={1.8} />
      </ZoomButton>
      <span className="block" style={{ height: 1, background: fill.hairline }} />
      <ZoomButton label="Zoom out" onClick={onOut}>
        <Minus size={15} strokeWidth={1.8} />
      </ZoomButton>
      <span className="block" style={{ height: 1, background: fill.hairline }} />
      <ZoomButton label="Fit to view" onClick={onFit}>
        <Maximize2 size={13} strokeWidth={1.8} />
      </ZoomButton>
    </div>
  )
}

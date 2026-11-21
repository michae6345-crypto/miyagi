/**
 * Core (v2, W0-5): screen space that v2 surfaces claim, so the island and its cards step around them without
 * importing the feature that owns them.
 *
 *   useDock(s => s.open)            the lesson panel docked beside the editor (A1 owns it, sets it with setDock)
 *   setDock({ open, rect })         rect in SCREEN points; tells the engine with panel.state when it lists that command
 *   panelRect(layout)               where the panel docks (theme.dock: 360 wide, inset 16, top 52), window coordinates
 *   reserveRect(owner, rect|rects)  any surface: "keep cards off this" (screen points); undefined / [] releases it
 *   useReserved(except?)            every reserved rect but `except`'s, screen points (islandPlace avoids them)
 */
import { create } from 'zustand'
import { cmd } from '../../../common/wire'
import type { Layout } from '../../../preload/api'
import { bridge } from '../bridge'
import { onUi } from './bus'
import { isUsableRect, sameRect, toLocal, type Rect } from './geometry'
import { canSend } from './lesson'
import { dock } from './theme'

export type DockState = {
  /** The lesson panel is showing (not collapsed to the Mini pill). */
  open: boolean
  /** Collapsed to the Mini pill (Les-Mini). */
  collapsed: boolean
  /** The panel's rect in screen points while open. */
  rect?: Rect
}

export const useDock = create<DockState>(() => ({ open: false, collapsed: false, rect: undefined }))

let lastSent = ''
export function setDock(patch: Partial<DockState>): void {
  const cur = useDock.getState()
  const next = { ...cur, ...patch }
  if (next.rect && !isUsableRect(next.rect)) next.rect = undefined
  // Motion (docs/MOTION.md): nothing changed, nothing to tell. A new rect object with the same numbers used to
  // re-render every reader (the panel itself, the island) on each frame of the panel's own height spring.
  const sameBox = next.rect === cur.rect || (!!next.rect && !!cur.rect && sameRect(next.rect, cur.rect, 0))
  if (next.open === cur.open && next.collapsed === cur.collapsed && sameBox) return
  useDock.setState(next)
  reserveRect('dock', next.open ? next.rect : undefined)
  // The engine keeps its boxes and VS Code clear of the panel (E2/E3), when it understands panel.state.
  const payload = { open: next.open, ...(next.open && next.rect ? { rect: next.rect } : {}) }
  const key = JSON.stringify(payload)
  if (key !== lastSent && canSend('panel.state')) {
    lastSent = key
    bridge.send(cmd('panel.state', payload))
  }
}

/** Where the lesson panel docks in this window (Les-Working at 1440x900: right 16, top 52, 360 wide). */
export function panelRect(layout: Layout, w: number = dock.w): Rect {
  const wa = layout.workArea
  const x = wa.x + wa.width - dock.inset - w
  const y = Math.max(dock.top, wa.y + dock.gap)
  const bottom = wa.y + wa.height - dock.inset
  return { x, y, w, h: Math.max(120, bottom - y) }
}

/** panelRect in screen points (for setDock / reserveRect). */
export function panelScreenRect(layout: Layout, w: number = dock.w): Rect {
  const r = panelRect(layout, w)
  return { ...r, x: r.x + layout.origin.x, y: r.y + layout.origin.y }
}

// ---- reservations ------------------------------------------------------------------------------------------------

const NONE: Rect[] = []
const useReservations = create<{ by: Record<string, Rect[]> }>(() => ({ by: {} }))

export function reserveRect(owner: string, rect: Rect | Rect[] | undefined): void {
  const list = (Array.isArray(rect) ? rect : rect ? [rect] : []).filter(isUsableRect)
  const by = useReservations.getState().by
  const now = by[owner] ?? NONE
  if (now.length === list.length && now.every((r, i) => sameRect(r, list[i], 0))) return
  const next = { ...by }
  if (list.length) next[owner] = list
  else delete next[owner]
  useReservations.setState({ by: next })
}

/** Every reserved rect (screen points) except the ones `except` holds. Stable while nothing changes. */
export function useReserved(except?: string): Rect[] {
  const by = useReservations((s) => s.by)
  return reservedOf(by, except)
}

const cache = new WeakMap<Record<string, Rect[]>, Map<string, Rect[]>>()
function reservedOf(by: Record<string, Rect[]>, except = ''): Rect[] {
  let m = cache.get(by)
  if (!m) cache.set(by, (m = new Map()))
  let out = m.get(except)
  if (!out) {
    out = Object.entries(by).flatMap(([o, rs]) => (o === except ? [] : rs))
    if (!out.length) out = NONE
    m.set(except, out)
  }
  return out
}

/** Reserved rects in this window's coordinates. */
export function reservedLocal(rects: Rect[], layout: Layout): Rect[] {
  return rects.length ? rects.map((r) => toLocal(r, layout.origin)) : NONE
}

// A new lesson / dev reset: the panel and everything reserved for it goes.
onUi('reset', () => {
  useDock.setState({ open: false, collapsed: false, rect: undefined })
  useReservations.setState({ by: {} })
  lastSent = ''
})

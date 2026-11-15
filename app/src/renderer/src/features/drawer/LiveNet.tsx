/**
 * Feature: drawer. The live network, in the drawer's right-hand panel (Michael, Sun 1:55 AM: the demo is "build a
 * neural network"). When the engine pushes a `network` diagram with real weights for the current step (the forward
 * pass starting, a training run, the stuck-loss off-track), it shows here, under the header, and redraws in place as
 * new ones arrive: never as a card over the code. In train mode the epoch and loss sit right under it.
 *
 * It stays out of the scrolling list so it's on screen while the learner types, and it folds to one row with its
 * chevron. The bar's Diagram / ⌃⌥D unfolds it (Michael, Sun 2:32 AM: never a card at the top); "Full size" opens the
 * island's full diagram.
 *
 * Its header is a drag handle (Michael, Sun 2:57 AM): drag it out of the drawer and it floats over the screen
 * (FloatNet.tsx); the drawer keeps a slim "Network · floating" row, and double-clicking either header docks it again.
 */
import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useLayoutEffect, useRef, useState, type PointerEvent as ReactPointerEvent, type ReactNode } from 'react'
import { ChevronDown, Maximize2, PanelRightClose } from 'lucide-react'
import type { DiagramPayload } from '../diagrams/store'
import { glass, spring } from '../../core/theme'
import { Firing, isFiringNetwork } from '../diagrams/Firing'
import { NeuralNet } from '../diagrams/NeuralNet'
import { SafeDiagram } from '../diagrams/SafeDiagram'
import { openLiveFull, useDiagram, useLiveNetwork } from '../diagrams/store'
import { titleOf } from '../diagrams/Tabs'
import { dock, popOut, setDockAt, useNetFloat } from './netFloat'

/** Movement (px) before a press on the header becomes a drag, so a tap on the chevron stays a tap. */
export const DRAG_SLOP = 4

export function LiveNetSection(): ReactNode {
  const d = useLiveNetwork()
  const [folded, setFolded] = useState(false)
  const out = useNetFloat((s) => s.spot.floating || !!s.pickup)
  const box = useRef<HTMLDivElement>(null)
  // The bar's Diagram / ⌃⌥D in a lesson with a live network: unfold this panel (no card over the code).
  const focus = useDiagram((s) => s.liveFocus)
  useEffect(() => {
    if (focus) setFolded(false)
  }, [focus])
  const grab = useHeaderDrag((e) => {
    const r = box.current?.getBoundingClientRect()
    if (r) popOut({ pointerX: e.clientX, pointerY: e.clientY, x: r.left, y: r.top, w: r.width })
  })
  if (!d) return null
  if (out) return <FloatingRow />
  return (
    <div ref={box} data-part="drawer-live-net" className="shrink-0 border-b px-[18px] pb-[10px]" style={{ borderColor: glass.rule }}>
      <NetHeader d={d} folded={folded} onFold={() => setFolded((f) => !f)} grab={grab} />
      <AnimatePresence initial={false}>
        {!folded && (
          <motion.div
            key="net"
            className="overflow-hidden"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={spring}
          >
            <NetBody d={d} />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

/** The drawer's slim row while the network floats: where a dock lands, and a button to bring it back. */
function FloatingRow(): ReactNode {
  const row = useRef<HTMLDivElement>(null)
  useLayoutEffect(() => {
    const el = row.current
    if (!el) return
    const report = (): void => {
      const r = el.getBoundingClientRect()
      setDockAt({ x: r.left, y: r.top })
    }
    report()
    const id = setInterval(report, 500) // the drawer slides and resizes; a cheap poll keeps the dock target honest
    return () => {
      clearInterval(id)
      setDockAt(undefined)
    }
  }, [])
  return (
    <div ref={row} data-part="drawer-live-net-floating" className="flex shrink-0 items-center gap-[8px] border-b px-[18px] py-[6px]" style={{ borderColor: glass.rule }}>
      <span className="min-w-0 flex-1 truncate text-[12px] font-semibold leading-[16px]" style={{ color: glass.label }}>
        Network <span className="font-normal" style={{ color: glass.faint }}>· floating</span>
      </span>
      <button
        type="button"
        className="grid h-[22px] w-[22px] shrink-0 cursor-pointer place-items-center rounded-full"
        style={{ background: glass.key, color: glass.keyText }}
        onMouseDown={(e) => e.preventDefault()}
        onClick={dock}
        aria-label="Dock in the drawer"
        title="Dock in the drawer"
      >
        <PanelRightClose size={11} strokeWidth={2.2} />
      </button>
    </div>
  )
}

/**
 * A press on the header that moves past DRAG_SLOP calls `start` once (with the move event); the click that ends a
 * drag is swallowed so the chevron doesn't also fold the panel.
 */
export function useHeaderDrag(start: (e: PointerEvent) => void): {
  onPointerDown: (e: ReactPointerEvent) => void
  onClickCapture: (e: React.MouseEvent) => void
} {
  const dragged = useRef(false)
  const startRef = useRef(start)
  startRef.current = start
  return {
    onPointerDown: (e) => {
      if (e.button !== 0) return
      dragged.current = false
      const x0 = e.clientX
      const y0 = e.clientY
      const move = (m: PointerEvent): void => {
        if (Math.hypot(m.clientX - x0, m.clientY - y0) < DRAG_SLOP) return
        dragged.current = true
        stop()
        startRef.current(m)
      }
      const stop = (): void => {
        window.removeEventListener('pointermove', move)
        window.removeEventListener('pointerup', stop)
        window.removeEventListener('pointercancel', stop)
      }
      window.addEventListener('pointermove', move)
      window.addEventListener('pointerup', stop)
      window.addEventListener('pointercancel', stop)
    },
    onClickCapture: (e) => {
      if (!dragged.current) return
      dragged.current = false
      e.stopPropagation()
      e.preventDefault()
    }
  }
}

/** The header row: chevron + title + mode, and Full size. The whole row is the drag handle. */
export function NetHeader(props: {
  d: DiagramPayload
  folded: boolean
  onFold: () => void
  grab: ReturnType<typeof useHeaderDrag>
  dragging?: boolean
  onDoubleClick?: () => void
}): ReactNode {
  const { d, folded, onFold, grab, dragging, onDoubleClick } = props
  const data = d.data as Record<string, unknown>
  const mode = (data.mode as string) ?? 'forward'
  const title = titleOf(d)
  return (
    <div
      data-part="live-net-handle"
      className="flex touch-none select-none items-center gap-[8px] py-[6px]"
      style={{ cursor: dragging ? 'grabbing' : 'grab' }}
      onPointerDown={grab.onPointerDown}
      onClickCapture={grab.onClickCapture}
      onDoubleClick={onDoubleClick ?? (() => undefined)}
    >
      <button
        type="button"
        className="flex min-w-0 flex-1 items-center gap-[6px] text-left text-[12px] font-semibold leading-[16px]"
        style={{ color: glass.label, cursor: 'inherit' }}
        onMouseDown={(e) => e.preventDefault()}
        onClick={onFold}
        aria-expanded={!folded}
      >
        <motion.span animate={{ rotate: folded ? -90 : 0 }} transition={spring} className="grid shrink-0 cursor-pointer place-items-center">
          <ChevronDown size={13} strokeWidth={2.2} />
        </motion.span>
        <span className="truncate">{title || 'Network'}</span>
        <span className="shrink-0 font-normal" style={{ color: glass.faint }}>
          {mode === 'train' ? 'training' : mode === 'backward' ? 'backprop' : mode === 'stuck' ? 'loss stuck' : 'forward pass'}
        </span>
      </button>
      <button
        type="button"
        className="grid h-[22px] w-[22px] shrink-0 cursor-pointer place-items-center rounded-full"
        style={{ background: glass.key, color: glass.keyText }}
        onMouseDown={(e) => e.preventDefault()}
        onPointerDown={(e) => e.stopPropagation()}
        onClick={openLiveFull}
        aria-label="Full size"
        title="Full size"
      >
        <Maximize2 size={11} strokeWidth={2.2} />
      </button>
    </div>
  )
}

/** The network itself (compact: scaled to the panel's width) and its caption. */
export function NetBody({ d }: { d: DiagramPayload }): ReactNode {
  const data = d.data as Record<string, unknown>
  return (
    <>
      <SafeDiagram resetKey={data}>{isFiringNetwork(data) ? <Firing data={data} compact /> : <NeuralNet data={data} compact />}</SafeDiagram>
      {d.caption && (
        <div className="mt-[6px] line-clamp-2 break-words text-[12.5px] leading-[17px]" style={{ color: glass.label }}>
          {d.caption}
        </div>
      )}
    </>
  )
}

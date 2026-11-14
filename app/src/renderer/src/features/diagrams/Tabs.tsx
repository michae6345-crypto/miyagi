/**
 * Tabs between the diagram kinds the engine sent for this step. Only when there is more than one; otherwise
 * `fallback` (the plain title). Chrome, so neutral: white text on a soft fill for the selected tab.
 */
import { motion } from 'motion/react'
import type { ReactNode } from 'react'
import type { GraphDiagramData } from '../../../../../../shared/contracts/events'
import { color, fill, spring } from '../../core/theme'
import { showKind, useDiagram, type DiagramPayload } from './store'

/** The header title for a diagram: graph titles come from the data. */
export function titleOf(d?: DiagramPayload): string {
  if (!d) return ''
  if (d.kind === 'graph') return (d.data as GraphDiagramData).title || 'Diagram'
  return d.kind === 'network' ? 'Architecture' : d.kind === 'gradients' ? 'Gradient flow' : 'Solution'
}

export function DiagramTabs({ fallback }: { fallback: ReactNode }): ReactNode {
  const kinds = useDiagram((s) => s.kinds)
  const byKind = useDiagram((s) => s.byKind)
  const current = useDiagram((s) => s.diagram?.kind)
  if (kinds.length < 2) return fallback
  return (
    <div className="flex items-center gap-[2px] rounded-full p-[2px]" style={{ background: fill.field }}>
      {kinds.map((k) => {
        const on = k === current
        return (
          <button
            key={k}
            data-hit
            onClick={() => showKind(k)}
            className={`relative h-[24px] cursor-pointer rounded-full px-[11px] text-[13px] leading-[24px] ${on ? 'font-semibold' : ''}`}
            style={{ color: on ? color.text : color.label }}
          >
            {on && <motion.span layoutId="diagram-tab" className="absolute inset-0 rounded-full" style={{ background: fill.chipHover }} transition={spring} />}
            <span className="relative">{titleOf(byKind[k])}</span>
          </button>
        )
      })}
    </div>
  )
}

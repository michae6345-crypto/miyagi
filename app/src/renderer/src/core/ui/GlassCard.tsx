/**
 * Core (v2, W0-3): the dark card every v2 surface sits on (the lesson panel, onboarding sheets, the recovery card,
 * the progress window's groups). Not the island: island cards stay black and morph out of the pill (Island.tsx).
 *
 *   surface 'panel'  the docked lesson panel (Les-*: rgba 28,28,30 at .96, hairline, radius 20, the card shadow)
 *   surface 'sheet'  a sheet inside an app window (Onb-Checklist-Mixed)
 *   surface 'group'  a grouped block of rows inside a window (Set-General, Prog-Progress-Window): no shadow
 *
 * Pass `hit` when it is interactive in the click-through overlay (data-hit), `ui` when it is visible but passive.
 */
import { forwardRef, type CSSProperties, type ReactNode } from 'react'
import { fill, radius2, surface as s } from '../theme'

export type GlassSurface = 'panel' | 'sheet' | 'group'

const LOOK: Record<GlassSurface, CSSProperties> = {
  panel: { background: s.panel, boxShadow: `inset 0 0 0 1px ${s.border}, ${s.shadow}`, borderRadius: radius2.panel },
  sheet: { background: s.sheet, boxShadow: `inset 0 0 0 1px ${s.border}, ${s.shadowSmall}`, borderRadius: radius2.sheet },
  group: { background: fill.group, boxShadow: `inset 0 0 0 1px ${fill.hairline}`, borderRadius: radius2.card }
}

type Props = {
  children?: ReactNode
  surface?: GlassSurface
  width?: number | string
  padding?: number | string
  className?: string
  style?: CSSProperties
  hit?: boolean
  ui?: boolean
  id?: string
}

export const GlassCard = forwardRef<HTMLDivElement, Props>(function GlassCard({ children, surface = 'panel', width, padding, className = '', style, hit, ui, id }, ref) {
  return (
    <div
      ref={ref}
      id={id}
      data-glass-card={surface}
      data-hit={hit || undefined}
      data-ui={!hit && ui ? true : undefined}
      className={`relative overflow-hidden text-white ${className}`}
      style={{ ...LOOK[surface], width, padding, ...style }}
    >
      {children}
    </div>
  )
})

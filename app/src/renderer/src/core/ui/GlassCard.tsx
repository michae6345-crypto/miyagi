/**
 * Core (v2, W0-3): the card every v2 surface sits on (dark or light with Settings > Appearance) (the lesson panel, onboarding sheets, the recovery card,
 * the progress window's groups). Not the island: island cards stay black and morph out of the pill (Island.tsx).
 *
 *   surface 'panel'  the docked lesson panel (Les-*: rgba 28,28,30 at .96, hairline, radius 20, the card shadow)
 *   surface 'sheet'  a sheet inside an app window (Onb-Checklist-Mixed)
 *   surface 'group'  a grouped block of rows inside a window (Set-General, Prog-Progress-Window): no shadow
 *
 * Pass `hit` when it is interactive in the click-through overlay (data-hit), `ui` when it is visible but passive.
 *
 * Polish (UI-POLISH-SPEC 2): each surface is a lit object. A hairline all round, a brighter top inner edge (the light
 * comes from above, as on macOS), the layered shadow for its elevation, and on the two big surfaces a faint monochrome
 * grain (.mg-grain: soft-light at .06, see styles.css) so the flat dark fill reads as a material. `grain={false}` turns it off (a canvas behind it, say).
 */
import { forwardRef, type CSSProperties, type ReactNode } from 'react'
import { elevation, fill, highlight, radius2, surface as s } from '../theme'

export type GlassSurface = 'panel' | 'sheet' | 'group'

const LOOK: Record<GlassSurface, CSSProperties> = {
  panel: { background: s.panel, boxShadow: `${highlight.top}, inset 0 0 0 1px ${s.border}, ${elevation.panel}`, borderRadius: radius2.panel },
  sheet: { background: s.sheet, boxShadow: `${highlight.top}, inset 0 0 0 1px ${s.border}, ${elevation.overlay}`, borderRadius: radius2.sheet },
  // A group is a raised layer: it lifts off the window with a soft shadow and a faint top edge (core/theme.ts `layer`).
  group: { background: fill.group, boxShadow: `${highlight.topSoft}, inset 0 0 0 1px ${fill.hairline}, ${elevation.raised}`, borderRadius: radius2.card }
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
  /** The grain on panel and sheet (default on); groups never have it. */
  grain?: boolean
  /** Interactive: moves one elevation level on hover and settles on press (.mg-lift). */
  lift?: boolean
}

export const GlassCard = forwardRef<HTMLDivElement, Props>(function GlassCard({ children, surface = 'panel', width, padding, className = '', style, hit, ui, id, grain = true, lift }, ref) {
  return (
    <div
      ref={ref}
      id={id}
      data-glass-card={surface}
      // Follows Settings > Appearance even inside the always-dark overlay (the lesson panel, account sheets).
      data-theme="auto"
      data-hit={hit || undefined}
      data-ui={!hit && ui ? true : undefined}
      className={`relative overflow-hidden text-white ${lift ? 'mg-lift' : ''} ${grain && surface !== 'group' ? 'mg-grain' : ''} ${className}`}
      style={{ ...LOOK[surface], width, padding, ...style }}
    >
      {children}
    </div>
  )
})

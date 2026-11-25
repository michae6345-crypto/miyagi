/**
 * Core: one layered surface for any page (Home, Lessons, Skills, Settings rows). Pick the level, get the depth.
 *
 *   level 'base'     flat on the window (no fill, no shadow): plain content
 *   level 'raised'   content lifted off the window: a white card in light, a lighter gray in dark, a soft wide shadow
 *   level 'overlay'  a sheet, popover or menu above content
 *
 * `interactive` adds the hover and press behaviour: the surface moves ONE level up on hover (raised to overlay) and
 * settles on press (.mg-lift). It sets no handler of its own; pass `onClick`. Everything follows Settings > Appearance
 * because the tokens are CSS variables (core/theme.ts).
 */
import { forwardRef, type CSSProperties, type MouseEventHandler, type ReactNode } from 'react'
import { layer, radius2, type Layer } from '../theme'

type Props = {
  children?: ReactNode
  level?: Layer
  radius?: number
  padding?: number | string
  interactive?: boolean
  className?: string
  style?: CSSProperties
  onClick?: MouseEventHandler<HTMLDivElement>
}

export const Surface = forwardRef<HTMLDivElement, Props>(function Surface({ children, level = 'raised', radius = radius2.group, padding, interactive, className = '', style, onClick }, ref) {
  return (
    <div
      ref={ref}
      data-surface-level={level}
      onClick={onClick}
      className={`relative ${interactive ? 'mg-lift cursor-pointer' : ''} ${className}`}
      style={{ ...layer[level], borderRadius: level === 'base' ? undefined : radius, padding, ...style }}
    >
      {children}
    </div>
  )
})

/**
 * Feature: library. The one page column for Home, Lessons and a lesson's preview (layout spec, Nov 22: "one shared
 * container for every page"). The column centers in the content pane; text inside it never does.
 *
 *   Pane     the page's scroll root and the container the column measures (a named container, `pane`)
 *   Column   720 of content, centered, 40 gutters (24 when the pane is under 760)
 *
 * 720 is Notion's reading column. Home tried the spec's optional 1040 two-column split in full screen and it read
 * unbalanced (an empty well under the ask, the bonsai off the page's center), so every page stays one column: in full
 * screen it is a calm 720 in the middle of the pane, top-anchored, never centered vertically.
 * Every number here is on the spacing scale (4, 8, 12, 16, 20, 24, 32, 40, 56, 80).
 */
import type { CSSProperties, ReactNode } from 'react'

/** The reading column (content width; the gutters sit outside it). */
export const COLUMN_W = 720
/** Window top to a page's first line (52 drag strip + 28): Home's bonsai and a preview's kicker sit here. */
export const PAGE_TOP = 80
/** Section to section, title to first section, label to content, bottom padding (spec section 4). */
export const rhythm = { section: 40, title: 32, label: 12, bottom: 64 } as const

type Data = Record<`data-${string}`, string | boolean | undefined>

/** The page's scroll root. Container queries in Column read its width (the pane, not the window). */
export function Pane({ children, className = '', style, ...data }: { children: ReactNode; className?: string; style?: CSSProperties } & Data): ReactNode {
  return (
    <div className={`@container/pane min-h-0 w-full ${className}`} style={style} {...data}>
      {children}
    </div>
  )
}

/**
 * The column: max 800 with 40 gutters = 720 of content. The gutter switch is a container variant (a static class
 * string, so Tailwind's scanner sees it). Its own padding is horizontal only; callers set the top and bottom.
 */
export function Column({ children, className = '', style, ...data }: { children: ReactNode; className?: string; style?: CSSProperties } & Data): ReactNode {
  return (
    <div className={`mx-auto w-full max-w-[800px] px-[40px] @max-[760px]/pane:px-[24px] ${className}`} style={style} {...data}>
      {children}
    </div>
  )
}

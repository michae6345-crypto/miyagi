/**
 * Feature: library. The one page column for Home, Lessons and a lesson's preview (layout spec, Nov 22: "one shared
 * container for every page"). The column centers in the content pane; text inside it never does.
 *
 *   Pane          the page's scroll root and the container the column measures (a named container, `pane`)
 *   Column        720 wide with its gutters (640 of content, 40 gutters; 24 when the pane is under 760), centered
 *   pageTitle     a page's h1: 26/32, -0.4px, semibold (the preview's title; the shell's page titles use the same)
 *   SectionLabel  a section's label: 13/18 semibold, secondary, 12 above its content, an optional right-hand slot
 *
 * 720 with the gutters is the same column as the shell's page header and its other pages (shell lane: 640 of content
 * inside 40 px gutters; shell/pages Column.tsx COLUMN_MAX.page), so Home, Lessons, Settings and Progress share one left
 * edge and the Lessons title sits right over its list. Every page stays one column: in full screen it is a calm 720 in
 * the middle of the pane, top-anchored, never centered vertically.
 * Every number here is on the spacing scale (4, 8, 12, 16, 20, 24, 32, 40, 56, 80).
 */
import type { CSSProperties, ReactNode } from 'react'
import { color, type2 } from '../../core/theme'

/** The column's full width, gutters included (640 of content at the 40 px gutter). */
export const COLUMN_W = 720
/** Window top to a page's first line (52 drag strip + 28): Home's bonsai and a preview's kicker sit here. */
export const PAGE_TOP = 80
/** Section to section, title to first section, label to content, bottom padding (spec section 4). */
export const rhythm = { section: 40, title: 32, label: 12, bottom: 64 } as const

/** A page's title (spec section 6). One object, so the page titles can't drift apart again. */
export const pageTitle = { fontSize: 26, lineHeight: '32px', letterSpacing: '-0.4px', fontWeight: 600 } as const satisfies CSSProperties

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
 * The column: max 720 with 40 gutters = 640 of content. The gutter switch is a container variant (a static class
 * string, so Tailwind's scanner sees it). Its own padding is horizontal only; callers set the top and bottom.
 */
export function Column({ children, className = '', style, ...data }: { children: ReactNode; className?: string; style?: CSSProperties } & Data): ReactNode {
  return (
    <div className={`mx-auto w-full max-w-[720px] px-[40px] @max-[760px]/pane:px-[24px] ${className}`} style={style} {...data}>
      {children}
    </div>
  )
}

/**
 * A section's label (spec section 6): 13/18, semibold, secondary, and 12 (rhythm.label) above the content on every
 * page: Home's Up next, Review and Recent, Lessons' In progress and Ready to run, the preview's steps. The row is the
 * label's 18 px line; whatever sits in `right` (a text link, the tool filter) centers on it and overhangs by up to 6 px
 * each way instead of pushing the content down, so the label-to-content gap is 12 whatever the slot holds.
 */
export function SectionLabel({ id, children, right, style }: { id?: string; children: ReactNode; right?: ReactNode; style?: CSSProperties }): ReactNode {
  return (
    <div className="flex items-center gap-[8px]" style={{ minHeight: 18, marginBottom: rhythm.label, ...style }}>
      <h2 id={id} className="m-0 shrink-0 font-semibold" style={{ fontSize: type2.sm, lineHeight: '18px', color: color.label }}>
        {children}
      </h2>
      {right && <div className="ml-auto flex min-w-0 items-center gap-[8px]" style={{ marginBlock: -6 }}>{right}</div>}
    </div>
  )
}

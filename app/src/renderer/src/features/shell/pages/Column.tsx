/**
 * Feature: shell. How the shell's pages (Settings, Account, Skills, Progress) sit on the page column, and the few helpers
 * they share. There is ONE column implementation: features/shell ui.tsx (PageBody, PageColumn, `--page-inset`,
 * GUTTER), sized by core/theme.ts `layout.page` (720 with the 40 px gutters, 1040 for the wide one; 24 px gutters once
 * the pane is under 760). This file adds no centering and no gutters of its own (fix round 1, Nov 22: a second 720
 * column here centered the content twice once merged with the shell lane).
 *
 * Who centers what:
 *   Settings, Account   scroll in the shell's body, which pads in to a centered box (Shell.tsx BODY_BOX); the page is a
 *                       ui.tsx PageBody, which centers the 720 column in it, right under the title.
 *   Skills              scrolls itself (Shell.tsx SELF_SCROLL): a full-pane Scroller (below), so the scrollbar stays at
 *                       the pane's edge, and in it a ui.tsx PageColumn `wide`. The shell gives Skills' title the same
 *                       wide column (Shell.tsx PAGE_W), so the title and the grid share one left edge at every width.
 *   Progress            its scroller belongs to features/dashboard (Overview.tsx), which pins its own 40 px-gutter
 *                       column left. InsetSeat (below) pads that scroller in by `--page-inset`, so the column lands under
 *                       the title. Until Overview can take the shell's column (a dashboard request from the pages lane), its
 *                       scrollbar sits at the column's edge rather than the pane's.
 *
 * Vertical rhythm (layout spec): the title's top 80 below the window's top (52 in full screen; the shell's PageHeader),
 * 32 from the title to the first block (the header's 24 plus the body's 8), SECTION_GAP between sections, LABEL_GAP
 * between a section's label and its group, 64 at the bottom. Top-anchored: no page centers vertically.
 *
 * The one exception to "never center vertically": onboarding's Ready (features/onboarding/Ready.tsx). It is a one-screen
 * completion dialog (the tree, one line, the sample lesson and its two actions) with nothing to scroll and nothing below
 * it, so it centers as one group, as a macOS completion sheet does. Guided setup is top-anchored (Guided.tsx STAGE_TOP).
 */
import type { CSSProperties, ReactNode } from 'react'
import { fill, layout } from '../../../core/theme'

/** Between a page's sections and groups (40). */
export const SECTION_GAP = layout.page.section
/** Between a section's label and its group (12). */
export const LABEL_GAP = layout.page.label
/**
 * Under a page's section control (Settings' segmented control), before the first group: the title's own gap plus the
 * body's top, 32, so the control reads as part of the header and its content starts where any other page's would.
 */
export const UNDER_TABS = layout.page.titleGap + 8

/** A page that scrolls itself: the whole pane scrolls (thin scrollbar at the pane's edge); the column goes inside it. */
export function Scroller({ children, style }: { children: ReactNode; style?: CSSProperties }): ReactNode {
  return (
    <div data-page-scroller className="h-full min-h-0 overflow-y-auto" style={{ scrollbarWidth: 'thin', scrollbarColor: `${fill.track} transparent`, ...style }}>
      {children}
    </div>
  )
}

/**
 * Seats a child that scrolls itself and pins its own 40 px-gutter column left (features/dashboard Overview) under the
 * page title: padded in by `--page-inset`, the same variable the title's header pads by. The percentage inside the
 * variable resolves against this element's containing block, which must be the pane's full width (a self-scrolling
 * page's body, or a window's root): never nest it inside a padded column.
 */
export function InsetSeat({ children, data }: { children: ReactNode; data?: Record<string, string> }): ReactNode {
  return (
    <div className="min-h-0 flex-1" style={{ paddingInline: 'var(--page-inset, 0px)' }} {...data}>
      {children}
    </div>
  )
}

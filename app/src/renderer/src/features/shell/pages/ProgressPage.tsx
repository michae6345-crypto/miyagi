/**
 * Feature: shell. The Progress page (redraft round 3): Review, Up next, the skills as one line per track and the
 * finished lessons, as plain lists (features/dashboard Overview.tsx). The skill graphs live on the Skills page only,
 * so the two pages no longer repeat each other. Each part has its own loading and empty state; the engine away with
 * nothing cached says so once, above it.
 *
 * Layout (Nov 22): the page column (Column.tsx), centered in the panel like every other page. Overview is
 * features/dashboard's (it scrolls itself, so the scrollbar stays at the panel's edge); this page only re-seats its
 * inner column: centered, the shared top / section / bottom rhythm, and the 24 px gutter in a narrow panel.
 */
import { CloudOff } from 'lucide-react'
import type { ReactNode } from 'react'
import { useLesson } from '../../../core/lesson'
import { color, copy, fill, highlight, radius2, surface, type2 } from '../../../core/theme'
import { ProgressOverview } from '../../dashboard/Overview'
import { useDash } from '../../dashboard/store'
import { PageColumn } from './Column'

/**
 * Overview's own column (its first child), re-seated into the page column: 720 like Settings and Account (Progress is
 * lists now, no charts, so the wide 1040 column only stretched its rows and floated "All skills" mid-panel), centered,
 * the same gutters and rhythm. Literal Tailwind classes (Column.tsx: 720, 24 → 40 gutter at 760, top 24, 40 between
 * sections, 64 at the bottom). `!` beats Overview's inline padding.
 */
export const OVERVIEW_SEAT = [
  '[&_[data-progress-overview]>div]:mx-auto',
  '[&_[data-progress-overview]>div]:max-w-[720px]!',
  '[&_[data-progress-overview]>div]:gap-[40px]',
  '[&_[data-progress-overview]>div]:pt-[24px]!',
  '[&_[data-progress-overview]>div]:pb-[64px]!',
  '[&_[data-progress-overview]>div]:px-[24px]!',
  '@min-[760px]:[&_[data-progress-overview]>div]:px-[40px]!'
].join(' ')

export function ProgressPage(): ReactNode {
  const connected = useLesson((s) => s.connected)
  const data = useDash((s) => s.data)
  const offline = !connected && !data
  return (
    <div data-shell-progress className="flex h-full min-h-0 flex-col @container">
      {offline && (
        <PageColumn bottom={0}>
          <div role="status" className="flex shrink-0 items-center gap-[12px]" style={{ padding: '12px 16px', borderRadius: radius2.card, background: fill.group, boxShadow: `${highlight.topSoft}, inset 0 0 0 1px ${surface.border}` }}>
            <CloudOff aria-hidden size={16} strokeWidth={1.8} style={{ color: color.label }} />
            <span style={{ fontSize: type2.sm, color: color.text }}>Your progress is safe.</span>
            <span style={{ fontSize: type2.xs, color: color.label }}>{copy.name} is offline. It shows here when it connects.</span>
          </div>
        </PageColumn>
      )}
      <div data-shell-progress-seat className={`min-h-0 flex-1 ${OVERVIEW_SEAT}`}>
        <ProgressOverview route="library" />
      </div>
    </div>
  )
}

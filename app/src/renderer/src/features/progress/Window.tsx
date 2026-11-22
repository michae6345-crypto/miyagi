/**
 * Prog-Progress-Window: the Progress app window (route `progress`, kind 'app', 1100x760; core/surfaces openProgress()).
 *
 * Nov 22 layout pass: the window speaks the home window's language, so the two Progress views are one design. Its body
 * is the same Overview as the home window's Progress page (features/dashboard Overview.tsx: Review, Up next, the skills
 * one line per track, the finished lessons), in the same centered 720 column (shell/pages/Column.tsx) with the same
 * title. The top is a plain 52 px strip that drags the window and clears the traffic lights; no breadcrumb, no title
 * text in the chrome (the page title does that job, as in Apple Music and System Settings). It used to be a different
 * layout: a breadcrumb bar with an ask hint, and the dashboard left-aligned in a 1040 column.
 * Everything comes from the engine's `progress` answer; a part it doesn't send yet shows that part's empty state.
 */
import type { ReactNode } from 'react'
import type { Layout } from '../../../../preload/api'
import { color, surface } from '../../core/theme'
import { ProgressOverview } from '../dashboard/Overview'
import { PageColumn } from '../shell/pages/Column'
import { OVERVIEW_SEAT } from '../shell/pages/ProgressPage'

export function ProgressWindow(_: { layout: Layout }): ReactNode {
  return (
    <div data-progress="window" className="flex h-full w-full flex-col @container" style={{ background: surface.window, color: color.text }}>
      <div data-drag className="shrink-0" style={{ height: 52 }} />
      <PageColumn top={0} bottom={0}>
        <h1 className="m-0 font-semibold" style={{ fontSize: 22, lineHeight: '28px', letterSpacing: '-0.015em', color: color.text }}>
          Progress
        </h1>
      </PageColumn>
      <div data-progress-seat className={`min-h-0 flex-1 ${OVERVIEW_SEAT}`}>
        <ProgressOverview route="progress" />
      </div>
    </div>
  )
}

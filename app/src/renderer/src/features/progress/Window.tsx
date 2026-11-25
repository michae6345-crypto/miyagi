/**
 * Prog-Progress-Window: the Progress app window (route `progress`, kind 'app', 1100x760; core/surfaces openProgress()).
 *
 * Nov 22 layout pass: the window speaks the home window's language, so the two Progress views are one design. Its body
 * is the same Overview as the home window's Progress page (features/dashboard Overview.tsx: Review, Up next, the skills
 * one line per track, the finished lessons), and its title is the shell's own PageHeader (features/shell ui.tsx), so
 * the title's type, its top (80 from the window's top, 52 in full screen) and its column cannot drift from the shell's
 * pages. No breadcrumb and no title text in the chrome (the page title does that job, as in Apple Music and System
 * Settings). The window sets `--page-inset` itself (the shell sets it per page frame): the header and Overview's seat
 * both pad in by it, so the title and the lists share one centered 720 column.
 * Everything comes from the engine's `progress` answer; a part it doesn't send yet shows that part's empty state.
 */
import type { ReactNode } from 'react'
import type { Layout } from '../../../../preload/api'
import { color, layout } from '../../core/theme'
import { ProgressOverview } from '../dashboard/Overview'
import { InsetSeat } from '../shell/pages/Column'
import { PageHeader, PANEL, pageInset } from '../shell/ui'

export function ProgressWindow(_: { layout: Layout }): ReactNode {
  return (
    <div
      data-progress="window"
      className="flex h-full w-full flex-col"
      // The content canvas, as the home window's Progress page (the shell's PANEL ground: layer.raised and its dot
      // grid), not surface.window (the sidebar's tone): this window has no sidebar, so it is all content (fix round 2).
      style={{
        backgroundColor: PANEL.backgroundColor,
        backgroundImage: PANEL.backgroundImage,
        backgroundSize: PANEL.backgroundSize,
        backgroundPosition: PANEL.backgroundPosition,
        color: color.text,
        ['--page-inset' as string]: pageInset()
      }}
    >
      {/* PageHeader measures its top from the home window's pane, which sits layout.pane.inset below the window's top;
          this window has no pane, so the same strip keeps the title on the same line (80, or 52 in full screen). */}
      <div data-drag className="shrink-0" style={{ height: layout.pane.inset }} />
      <PageHeader title="Progress" />
      <InsetSeat data={{ 'data-progress-seat': '' }}>
        <ProgressOverview route="progress" />
      </InsetSeat>
    </div>
  )
}

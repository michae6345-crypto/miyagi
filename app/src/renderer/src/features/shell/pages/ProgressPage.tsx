/**
 * Feature: shell. The Progress page (redraft round 3): Review, Up next, the skills as one line per track and the
 * finished lessons, as plain lists (features/dashboard Overview.tsx). The skill graphs live on the Skills page only,
 * so the two pages no longer repeat each other. Each part has its own loading and empty state; the engine away with
 * nothing cached says so once, above it.
 *
 * Layout (Nov 22): Overview scrolls itself and pins its own column left; Column.tsx InsetSeat pads it in by the
 * shell's `--page-inset`, so its column sits under the page title (no reaching into Overview's DOM). The offline line
 * sits on the same column.
 */
import { CloudOff } from 'lucide-react'
import type { ReactNode } from 'react'
import { useLesson } from '../../../core/lesson'
import { color, copy, type2 } from '../../../core/theme'
import { ProgressOverview } from '../../dashboard/Overview'
import { useDash } from '../../dashboard/store'
import { CARD, PageColumn } from '../ui'
import { BODY_TOP, InsetSeat } from './Column'

export function ProgressPage(): ReactNode {
  const connected = useLesson((s) => s.connected)
  const data = useDash((s) => s.data)
  const offline = !connected && !data
  return (
    <div data-shell-progress className="flex h-full min-h-0 flex-col">
      {offline && (
        <PageColumn style={{ paddingTop: BODY_TOP, paddingBottom: 0 }}>
          <div role="status" className="flex shrink-0 items-center gap-[12px]" style={{ ...CARD, padding: '12px 16px' }}>
            <CloudOff aria-hidden size={16} strokeWidth={1.8} style={{ color: color.label }} />
            <span style={{ fontSize: type2.sm, color: color.text }}>Your progress is safe.</span>
            <span style={{ fontSize: type2.xs, color: color.label }}>{copy.name} is offline. It shows here when it connects.</span>
          </div>
        </PageColumn>
      )}
      <InsetSeat data={{ 'data-shell-progress-seat': '' }}>
        <ProgressOverview route="library" />
      </InsetSeat>
    </div>
  )
}

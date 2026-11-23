/**
 * Feature: shell. The Progress page (redraft round 3): Review, Up next, the skills as one line per track and the
 * finished lessons, as plain lists (features/dashboard Overview.tsx). The skill graphs live on the Skills page only,
 * so the two pages no longer repeat each other. Each part has its own loading and empty state; the engine away with
 * nothing cached says so once, above it.
 */
import { CloudOff } from 'lucide-react'
import type { ReactNode } from 'react'
import { useLesson } from '../../../core/lesson'
import { color, copy, fill, highlight, radius2, surface, type2 } from '../../../core/theme'
import { ProgressOverview } from '../../dashboard/Overview'
import { useDash } from '../../dashboard/store'

export function ProgressPage(): ReactNode {
  const connected = useLesson((s) => s.connected)
  const data = useDash((s) => s.data)
  const offline = !connected && !data
  return (
    <div data-shell-progress className="flex h-full min-h-0 flex-col">
      {offline && (
        <div role="status" className="flex shrink-0 items-center gap-[12px]" style={{ margin: '8px 40px 0', padding: '12px 16px', borderRadius: radius2.card, background: fill.group, boxShadow: `${highlight.topSoft}, inset 0 0 0 1px ${surface.border}` }}>
          <CloudOff aria-hidden size={16} strokeWidth={1.8} style={{ color: color.label }} />
          <span style={{ fontSize: type2.sm, color: color.text }}>Your progress is safe.</span>
          <span style={{ fontSize: type2.xs, color: color.label }}>{copy.name} is offline. It shows here when it connects.</span>
        </div>
      )}
      <div className="min-h-0 flex-1" style={{ padding: 0 }}>
        <ProgressOverview route="library" />
      </div>
    </div>
  )
}

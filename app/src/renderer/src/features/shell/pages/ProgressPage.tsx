/**
 * Feature: shell. The Progress page: the Progress window's body (features/progress Window.tsx renders the dashboard)
 * inline, so nothing opens a second window from here. Today ring, this week, reps and rhythm on top; the skills with
 * Continue, Review and Up next beside them; milestones at the foot. Each part has its own loading and empty state
 * (features/dashboard); the engine away with nothing cached says so once, above it.
 */
import { CloudOff } from 'lucide-react'
import type { ReactNode } from 'react'
import { useLesson } from '../../../core/lesson'
import { color, copy, fill, highlight, radius2, surface, type2 } from '../../../core/theme'
import { Dashboard } from '../../dashboard/Dashboard'
import { useDash } from '../../dashboard/store'

export function ProgressPage(): ReactNode {
  const connected = useLesson((s) => s.connected)
  const data = useDash((s) => s.data)
  const offline = !connected && !data
  return (
    <div data-shell-progress className="flex h-full min-h-0 flex-col">
      {offline && (
        <div role="status" className="flex shrink-0 items-center gap-[12px]" style={{ margin: '20px 32px 0', padding: '12px 16px', borderRadius: radius2.card, background: fill.group, boxShadow: `${highlight.topSoft}, inset 0 0 0 1px ${surface.border}` }}>
          <CloudOff aria-hidden size={16} strokeWidth={1.8} style={{ color: color.label }} />
          <span style={{ fontSize: type2.sm, color: color.text }}>Your progress is safe.</span>
          <span style={{ fontSize: type2.xs, color: color.label }}>{copy.name} is offline. It shows here when it connects.</span>
        </div>
      )}
      <div className="min-h-0 flex-1" style={{ padding: 0 }}>
        <Dashboard route="library" />
      </div>
    </div>
  )
}

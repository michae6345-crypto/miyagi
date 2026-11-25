/**
 * Feature: shell. The Progress page, v4 (Adrian's ui-next `progress` and `progress-empty`, Nov 24 trim pass): two
 * columns, the work on the left and the numbers in a rail on the right (features/progress/v4/Page.tsx). It scrolls
 * itself (Shell.tsx SELF_SCROLL) on the shell's wide column, so its left edge sits under the title.
 *
 * The engine away with nothing cached says so once, above it.
 */
import { CloudOff } from 'lucide-react'
import type { ReactNode } from 'react'
import { useLesson } from '../../../core/lesson'
import { color, copy, type2 } from '../../../core/theme'
import { useDash } from '../../dashboard/store'
import { ProgressV4 } from '../../progress/v4/Page'
import { CARD, PageColumn } from '../ui'
import { BODY_TOP } from './Column'

export function ProgressPage(): ReactNode {
  const connected = useLesson((s) => s.connected)
  const data = useDash((s) => s.data)
  const offline = !connected && !data
  return (
    <div data-shell-progress className="flex h-full min-h-0 flex-col">
      {offline && (
        <PageColumn wide style={{ paddingTop: BODY_TOP, paddingBottom: 0 }}>
          <div role="status" className="flex shrink-0 items-center gap-[12px]" style={{ ...CARD, padding: '12px 16px' }}>
            <CloudOff aria-hidden size={16} strokeWidth={1.8} style={{ color: color.label }} />
            <span style={{ fontSize: type2.sm, color: color.text }}>Your progress is safe.</span>
            <span style={{ fontSize: type2.xs, color: color.label }}>{copy.name} is offline. It shows here when it connects.</span>
          </div>
        </PageColumn>
      )}
      <div className="min-h-0 flex-1">
        <ProgressV4 />
      </div>
    </div>
  )
}

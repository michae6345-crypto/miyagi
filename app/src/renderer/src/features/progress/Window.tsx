/**
 * Prog-Progress-Window: the Progress app window (route `progress`, kind 'app', 1100x760; core/surfaces openProgress()).
 *
 * Its body is the lesson dashboard (features/dashboard): Today ring, this week, reps and rhythm on top; the skill
 * constellation with Review, Continue and Up next beside it; milestones at the foot. The same view is Library's Home.
 * Everything comes from the engine's `progress` answer; a part it doesn't send yet shows that part's empty state.
 */
import type { ReactNode } from 'react'
import type { Layout } from '../../../../preload/api'
import { bridge } from '../../bridge'
import { Keycap } from '../../core/ui/Keycap'
import { MiyagiMark, MiyagiWordmark } from '../../core/ui/Mark'
import { color, copy, fill, surface, type2 } from '../../core/theme'
import { Dashboard } from '../dashboard/Dashboard'

const caption = { fontSize: type2.xs, color: color.label } as const

function TitleBar(): ReactNode {
  return (
    <div data-drag className="relative flex shrink-0 items-center justify-end px-[20px]" style={{ height: 52, borderBottom: `1px solid ${fill.hairline}` }}>
      <div className="pointer-events-none absolute inset-x-0 flex justify-center">
        <div className="flex items-center gap-[8px]">
          <MiyagiMark size={16} />
          <MiyagiWordmark height={14} className="h-[14px] w-auto" />
          <span style={{ fontSize: type2.md, color: color.faint }}>/</span>
          <span className="font-semibold" style={{ fontSize: type2.md, color: color.text }}>
            Progress
          </span>
        </div>
      </div>
      <button type="button" data-no-drag className="flex cursor-pointer items-center gap-[6px] hover:text-white" style={caption} onClick={() => bridge.emit('launcher:toggle')}>
        <Keycap k="launcher" size="sm" />
        <span>{copy.launcherPlaceholder}</span>
      </button>
    </div>
  )
}

export function ProgressWindow(_: { layout: Layout }): ReactNode {
  return (
    <div data-progress="window" className="flex h-full w-full flex-col text-white" style={{ background: surface.window }}>
      <TitleBar />
      <div className="min-h-0 flex-1">
        <Dashboard route="progress" />
      </div>
    </div>
  )
}

/**
 * Feature: shell. The Skills page: the skill constellation (features/dashboard), grouped by the lesson or track each
 * skill came from, in soft pastel colors, on the page itself with no frame around it. A skill's card opens over the
 * top right (SkillCard: the lessons that teach it). Loading, empty ("No skills yet") and offline states come from the
 * constellation itself. The page scrolls; a skill's name wraps inside its column and a wide row scrolls inside its box.
 */
import type { ReactNode } from 'react'
import { color, fill } from '../../../core/theme'
import { Constellation } from '../../dashboard/Constellation'
import { useDashView } from '../../dashboard/Dashboard'
import { SkillCard } from '../../dashboard/Rail'

export function SkillsPage(): ReactNode {
  const { data, load, now, due } = useDashView()
  return (
    <div data-shell-skills className="relative h-full min-h-0 @container" style={{ color: color.text }}>
      <div className="h-full overflow-y-auto" style={{ padding: '8px 40px 40px', scrollbarWidth: 'thin', scrollbarColor: `${fill.track} transparent` }}>
        <div className="w-full" style={{ maxWidth: 1040 }}>
          <Constellation data={data} review={due} loading={load === 'loading'} bare />
        </div>
      </div>
      <SkillCard data={data} now={now} route="library" />
    </div>
  )
}

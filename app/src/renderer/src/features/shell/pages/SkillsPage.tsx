/**
 * Feature: shell. The Skills page: the skill constellation (features/dashboard), grouped by the lesson or track each
 * skill came from, in soft pastel colors, on the page itself with no frame around it. A skill's card opens over the
 * top right (SkillCard: the lessons that teach it). Loading and offline states come from the constellation itself.
 * The page scrolls; a skill's name wraps inside its column and a wide row scrolls inside its box.
 *
 * Layout (Nov 22): the wide page column (Column.tsx, 1040), centered in the panel like every other page. With no skills
 * yet the page shows one calm empty state (the bonsai, one line, the way to a lesson), not a stray line in a corner.
 */
import type { ReactNode } from 'react'
import { color, fill } from '../../../core/theme'
import { QuietButton } from '../../../core/ui/buttons'
import { MiyagiMark } from '../../../core/ui/Mark'
import { Constellation } from '../../dashboard/Constellation'
import { useDashView } from '../../dashboard/Dashboard'
import { SkillCard } from '../../dashboard/Rail'
import { setPage } from '../store'
import { Empty } from '../ui'
import { PageColumn } from './Column'

export function SkillsPage(): ReactNode {
  const { data, load, now, due } = useDashView()
  const loading = load === 'loading'
  const none = !loading && !(data?.tracks?.length ?? 0)
  return (
    <div data-shell-skills className="relative h-full min-h-0 @container" style={{ color: color.text }}>
      <div className="h-full overflow-y-auto @container" style={{ scrollbarWidth: 'thin', scrollbarColor: `${fill.track} transparent` }}>
        <PageColumn width="wide">
          {none ? (
            <div data-shell-skills-empty>
              <Empty
                mark={<MiyagiMark size={40} />}
                title="No skills yet"
                line="Finish a lesson. The skills its checks proved show up here."
                action={<QuietButton label="Browse lessons" onClick={() => setPage('lessons')} />}
              />
            </div>
          ) : (
            <Constellation data={data} review={due} loading={loading} bare titled={false} />
          )}
        </PageColumn>
      </div>
      <SkillCard data={data} now={now} route="library" />
    </div>
  )
}

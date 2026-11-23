/**
 * Feature: shell. The Skills page: the skill constellation (features/dashboard), grouped by the lesson or track each
 * skill came from, in soft pastel colors, on the page itself with no frame around it. A skill's card opens over the
 * top right (SkillCard: the lessons that teach it). Loading and offline states come from the constellation itself.
 * The page scrolls; a skill's name wraps inside its column and a wide row scrolls inside its box.
 *
 * Layout (Nov 22): the page scrolls itself across the whole pane (Column.tsx Scroller, scrollbar at the pane's edge),
 * and its content is the shell's wide column (ui.tsx PageColumn `wide`, 1040 with the gutters), centered. The shell puts
 * Skills' title on the same wide column (Shell.tsx PAGE_W), so the two share one left edge at every width. With no
 * skills yet the page shows one calm empty state (the bonsai, one line, the way to a lesson).
 */
import type { ReactNode } from 'react'
import { color } from '../../../core/theme'
import { QuietButton } from '../../../core/ui/buttons'
import { MiyagiMark } from '../../../core/ui/Mark'
import { Constellation } from '../../dashboard/Constellation'
import { useDashView } from '../../dashboard/Dashboard'
import { SkillCard } from '../../dashboard/Rail'
import { setPage } from '../store'
import { Empty, PageColumn } from '../ui'
import { Scroller } from './Column'

export function SkillsPage(): ReactNode {
  const { data, load, now, due } = useDashView()
  const loading = load === 'loading'
  const none = !loading && !(data?.tracks?.length ?? 0)
  return (
    <div data-shell-skills className="relative h-full min-h-0" style={{ color: color.text }}>
      <Scroller>
        {/* 8 under the header's 24: the first row sits 32 under the title, as on every page. */}
        <PageColumn wide style={{ paddingTop: 8 }}>
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
      </Scroller>
      <SkillCard data={data} now={now} route="library" />
    </div>
  )
}

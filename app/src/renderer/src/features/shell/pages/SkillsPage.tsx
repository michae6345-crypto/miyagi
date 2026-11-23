/**
 * Feature: shell. The Skills page: the skill constellation (features/dashboard), grouped by the lesson or track each
 * skill came from, in soft pastel colors, on the page itself with no frame around it. A skill's card opens over the
 * top right (SkillCard: the lessons that teach it). Loading and offline states come from the constellation itself.
 * The page scrolls; a skill's name wraps inside its column and a wide row scrolls inside its box.
 *
 * Layout (Nov 22): the page scrolls itself across the whole pane (Column.tsx Scroller, scrollbar at the pane's edge),
 * and its content is the shell's wide column (ui.tsx PageColumn `wide`, 1040 with the gutters), centered. The shell puts
 * Skills' title on the same wide column (Shell.tsx PAGE_W), so the two share one left edge at every width. With no
 * skills yet the page shows one calm empty state (the bonsai, one line, the way to a lesson), left-aligned under the
 * title, 32 below it, so the title and the empty state read as one group (fix round 2: the shared ui.tsx Empty centers
 * itself, which left the wide title alone at the far left and the empty block in the pane's middle).
 */
import type { ReactNode } from 'react'
import { color, type2 } from '../../../core/theme'
import { QuietButton } from '../../../core/ui/buttons'
import { MiyagiMark } from '../../../core/ui/Mark'
import { Constellation } from '../../dashboard/Constellation'
import { useDashView } from '../../dashboard/Dashboard'
import { SkillCard } from '../../dashboard/Rail'
import { setPage } from '../store'
import { PageColumn } from '../ui'
import { Scroller } from './Column'

/** No skills yet: the bonsai, one line, the way to a lesson, on the title's left edge (top-anchored, not centered). */
function NoSkills(): ReactNode {
  return (
    <div data-shell-skills-empty className="flex flex-col items-start" style={{ gap: 8 }}>
      <MiyagiMark size={40} />
      <span className="font-semibold" style={{ marginTop: 8, fontSize: type2.lg, color: color.text }}>
        No skills yet
      </span>
      <span style={{ fontSize: type2.sm, color: color.label, maxWidth: 360 }}>Finish a lesson. The skills its checks proved show up here.</span>
      <div style={{ marginTop: 16 }}>
        <QuietButton label="Browse lessons" onClick={() => setPage('lessons')} />
      </div>
    </div>
  )
}

export function SkillsPage(): ReactNode {
  const { data, load, now, due } = useDashView()
  const loading = load === 'loading'
  const tracks = data?.tracks?.length ?? 0
  const none = !loading && !tracks
  return (
    <div data-shell-skills className="relative h-full min-h-0" style={{ color: color.text }}>
      <Scroller>
        {/* BODY_TOP under the header: the first row sits 32 under the title, as on every page. */}
        {/* The title's column (Shell.tsx pageWidth): wide only while the grid has skills, so an empty state starts on the 720 title's edge. */}
        <PageColumn wide={tracks > 0}>
          {none ? (
            <NoSkills />
          ) : (
            <Constellation data={data} review={due} loading={loading} bare titled={false} />
          )}
        </PageColumn>
      </Scroller>
      <SkillCard data={data} now={now} route="library" />
    </div>
  )
}

/**
 * Feature: shell. The Skills page: the full skill constellation (features/dashboard) with room to breathe, and a side
 * panel for the selected skill's card (SkillCard: lessons that teach it, Resume / Start). With nothing selected the
 * panel lists each track's headline ("3 of 7 skills mastered in Python.") and says how to open a card.
 * Loading, empty ("No skills yet") and offline states come from the constellation itself.
 */
import type { ReactNode } from 'react'
import { color, copy, fill, highlight, radius2, surface, type2 } from '../../../core/theme'
import { Constellation } from '../../dashboard/Constellation'
import { useDashView } from '../../dashboard/Dashboard'
import { trackHeadline } from '../../dashboard/model'
import { SkillCard } from '../../dashboard/Rail'
import { useDash } from '../../dashboard/store'
import { useLesson } from '../../../core/lesson'

const caption = { fontSize: type2.xs, lineHeight: '16px', color: color.label } as const

export function SkillsPage(): ReactNode {
  const { data, load, now, due } = useDashView()
  const selected = useDash((s) => !!s.selected)
  const connected = useLesson((s) => s.connected)
  const loading = load === 'loading'
  const tracks = data?.tracks ?? []
  return (
    <div data-shell-skills className="grid h-full min-h-0 gap-[16px] @container" style={{ padding: '20px 32px 24px', gridTemplateColumns: 'minmax(0, 1fr) 332px' }}>
      <div className="grid min-h-0">
        <Constellation data={data} review={due} loading={loading} />
      </div>
      <aside aria-label="Skill details" className="relative min-h-0 overflow-hidden" style={{ borderRadius: radius2.chip, background: fill.group, boxShadow: `${highlight.topSoft}, inset 0 0 0 1px ${fill.hairline}` }}>
        {/* SkillCard places itself 16 px in from the top right: in this panel that is the panel's own card. */}
        <SkillCard data={data} now={now} route="library" />
        {!selected && (
          <div className="flex h-full flex-col gap-[16px]" style={{ padding: 20 }}>
            <div className="flex flex-col gap-[4px]">
              <h2 className="m-0 font-semibold" style={{ fontSize: type2.body, color: color.text }}>
                Your tracks
              </h2>
              <span style={caption}>Mastered skills, by track.</span>
            </div>
            {loading ? (
              <div className="flex flex-col gap-[8px]" aria-busy aria-label="Loading your tracks">
                {[0, 1, 2].map((i) => (
                  <div key={i} style={{ height: 40, borderRadius: radius2.row, background: fill.skeleton }} />
                ))}
              </div>
            ) : !tracks.length ? (
              <span style={caption}>{!connected && !data ? `${copy.name} is offline. Your skills show when it connects.` : 'Finish a lesson. The skills it proved show up here.'}</span>
            ) : (
              <ul className="m-0 flex list-none flex-col gap-[8px] p-0">
                {tracks.map((t) => (
                  <li key={t.track} className="flex flex-col gap-[6px]" style={{ padding: '10px 12px', borderRadius: radius2.row, background: surface.row, boxShadow: highlight.topSoft }}>
                    <span className="font-medium" style={{ fontSize: type2.sm, color: color.text }}>
                      {t.track}
                    </span>
                    <span style={caption}>{trackHeadline(t)}</span>
                    <span className="relative block w-full overflow-hidden" style={{ height: 4, borderRadius: radius2.round, background: fill.hairline }}>
                      <span className="absolute inset-0 block origin-left" style={{ background: color.text, transform: `scaleX(${t.total ? t.mastered / t.total : 0})`, borderRadius: radius2.round }} />
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </aside>
    </div>
  )
}

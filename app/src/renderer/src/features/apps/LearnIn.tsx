/**
 * Feature: apps. Home's "Learn in" (MIC-87, returning learner): a short block at the foot of Home's rail, one row per
 * app miyagi teaches in, at most five. A row says the learner's lessons there ("10 lessons"), else the plan to start
 * with, or "Get Fusion" when the app isn't on this Mac. A click opens the app's page, never a lesson.
 *
 * The first-run Home (Adrian's table replacing Start here) is left to the Home lane: it reshapes that page.
 */
import { ArrowUpRight } from 'lucide-react'
import { useMemo, type ReactNode } from 'react'
import { color } from '../../core/theme'
import { muted, RailRow, Sec } from '../library/home/bits'
import { useLibrary } from '../library/store'
import { PLANS, planShort, START_HERE } from '../plans/catalog'
import { usePlans } from '../plans/store'
import { appContent, appMeta, APPS } from './model'
import { openApp, useAppStates } from './store'

const MAX_ROWS = 5

export function LearnIn({ first }: { first?: boolean }): ReactNode {
  const items = useLibrary((s) => s.items)
  const mine = usePlans((s) => s.mine)
  const states = useAppStates(false)
  const rows = useMemo(() => APPS.slice(0, MAX_ROWS).map((a) => appContent(a.id, PLANS, items, mine, START_HERE)).filter((c) => c.plans.length > 0), [items, mine])
  if (!rows.length) return null
  return (
    <section aria-labelledby="home-learn-in" data-home-apps>
      <Sec id="home-learn-in" first={first}>
        Learn in
      </Sec>
      <div className="mg-h4-list">
        {rows.map((c) => {
          const missing = states[c.id] === 'missing'
          const right = missing ? (
            <span className="inline-flex items-center gap-[3px]" style={{ ...muted, color: color.text }}>
              {appMeta(c.id)?.getUrl ? `Get ${c.name}` : 'Not installed'}
              {appMeta(c.id)?.getUrl && <ArrowUpRight aria-hidden size={13} strokeWidth={1.8} />}
            </span>
          ) : (
            <span style={muted}>{c.lessons.length ? `${c.lessons.length} ${c.lessons.length === 1 ? 'lesson' : 'lessons'}` : c.start ? planShort(c.start) : ''}</span>
          )
          return (
            <RailRow key={c.id} label={`${c.name}, open its page`} onClick={() => openApp(c.id)} right={right}>
              {c.name}
            </RailRow>
          )
        })}
      </div>
    </section>
  )
}

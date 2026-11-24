/**
 * Feature: plans. Browse plans (Adrian's mock `plans`, -29): the two ways to make a plan, the topic tabs, the four to
 * start with, and every plan in three tables (Coding languages, Apps and tools, Going further). "After" names the plan
 * to finish first (the plan's `needs`). Trim pass (Nov 24): no "Starts with" column and no counts in the top line.
 */
import { Search, X } from 'lucide-react'
import { useMemo, useState, type ReactNode } from 'react'
import { color, radius2, surface, type2 } from '../../core/theme'
import { PageHeader } from '../shell/ui'
import { afterTitles, hoursShort, planById, planMinutes, PLAN_GROUPS, PLANS, START_HERE, TOPIC_TABS, type CatalogPlan, type PlanTopic } from './catalog'
import { showPlan } from './store'
import { CardGrid, EntryCards, meta, PlanCard, SectionLabel, TableHead, TableRow, Tabs, useWidth, type Tab } from './ui'

type TopicTab = PlanTopic | 'all'
/** Up to two lines, then an ellipsis. */
const clamp2 = { display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' } as const

export function PlansPage(): ReactNode {
  const [topic, setTopic] = useState<TopicTab>('all')
  const [query, setQuery] = useState('')
  const [searching, setSearching] = useState(false)
  const [ref, w] = useWidth<HTMLDivElement>()
  const q = query.trim().toLowerCase()
  const shown = useMemo(
    () => PLANS.filter((p) => (topic === 'all' || p.topic === topic) && (!q || `${p.title} ${p.tool.label} ${p.project.title}`.toLowerCase().includes(q))),
    [topic, q]
  )
  const tabs: Tab<TopicTab>[] = TOPIC_TABS.map((t) => ({ id: t.id, label: t.label, count: t.id === 'all' ? PLANS.length : PLANS.filter((p) => p.topic === t.id).length })).filter((t) => t.count > 0)
  const cols = w < 640 ? 2 : 4

  return (
    <div ref={ref} data-plans-page className="flex flex-col" style={{ gap: 28 }}>
      <PageHeader title="Plans" lede="A plan is a set of lessons in order that ends in something you made." />
      <EntryCards />
      <Tabs
        label="Plan topics"
        tabs={tabs}
        value={topic}
        onChange={setTopic}
        right={
          searching ? (
            <span className="relative flex items-center">
              <Search aria-hidden size={14} strokeWidth={1.8} className="pointer-events-none absolute" style={{ left: 8, color: color.label }} />
              <input
                autoFocus
                type="search"
                aria-label="Search plans"
                className="[&::-webkit-search-cancel-button]:hidden"
                placeholder="Search plans"
                value={query}
                onChange={(e) => setQuery(e.target.value.slice(0, 80))}
                onKeyDown={(e) => {
                  if (e.key === 'Escape') {
                    e.stopPropagation()
                    setQuery('')
                    setSearching(false)
                  }
                }}
                style={{ width: 200, height: 28, padding: '0 30px 0 28px', borderRadius: radius2.control, background: surface.well, border: 0, boxShadow: `inset 0 0 0 1px ${surface.border}`, color: color.text, fontSize: type2.sm, outline: 'none' }}
              />
              <button type="button" aria-label="Close search" onClick={() => (setQuery(''), setSearching(false))} className="absolute flex cursor-pointer items-center justify-center" style={{ right: 2, width: 24, height: 24, background: 'none', border: 0, padding: 0, color: color.label }}>
                <X size={14} />
              </button>
            </span>
          ) : (
            <button type="button" aria-label="Search plans" onClick={() => setSearching(true)} className="flex cursor-pointer items-center justify-center" style={{ width: 28, height: 28, background: 'none', border: 0, borderRadius: radius2.control, color: color.label }}>
              <Search size={16} strokeWidth={1.8} />
            </button>
          )
        }
      />
      {topic === 'all' && !q && (
        <section>
          <SectionLabel>Start here</SectionLabel>
          <CardGrid cols={cols}>
            {START_HERE.map((id) => planById(id))
              .filter((p): p is CatalogPlan => !!p)
              .map((p) => (
                <PlanCard key={p.id} plan={p} />
              ))}
          </CardGrid>
        </section>
      )}
      {PLAN_GROUPS.map((g) => {
        const plans = shown.filter(g.match).sort((a, b) => a.title.localeCompare(b.title, 'en', { sensitivity: 'base' }))
        if (!plans.length) return null
        return <PlanTable key={g.id} label={g.label} plans={plans} after={g.after && plans.some((p) => p.needs.length > 0)} width={w} />
      })}
      {!shown.length && (
        <p className="m-0" style={meta}>
          No plans match.
        </p>
      )}
    </div>
  )
}

function PlanTable({ label, plans, after, width }: { label: string; plans: CatalogPlan[]; after: boolean; width: number }): ReactNode {
  const narrow = width < 760
  const showAfter = after && !narrow
  // Plan · Works in · Lessons · Skills · Time · Ends with · After
  // The Plan column gets room for the longest name (about 210 px, 'Working with language models') before the text
  // columns share the rest; a name that still doesn't fit wraps to a second line rather than clipping.
  const template = narrow ? 'minmax(0,1.6fr) minmax(0,1fr) 48px 52px' : `minmax(150px,224px) minmax(0,0.8fr) 56px 48px 52px minmax(0,1.6fr)${showAfter ? ' minmax(0,1.2fr)' : ''}`
  const cols = narrow
    ? [{ label: 'Plan' }, { label: 'Works in' }, { label: 'Lessons', align: 'right' as const }, { label: 'Time', align: 'right' as const }]
    : [{ label: 'Plan' }, { label: 'Works in' }, { label: 'Lessons', align: 'right' as const }, { label: 'Skills', align: 'right' as const }, { label: 'Time', align: 'right' as const }, { label: 'Ends with' }, ...(showAfter ? [{ label: 'After' }] : [])]
  return (
    <section data-plan-group={label}>
      <SectionLabel count={plans.length}>{label}</SectionLabel>
      <div role="table" aria-label={label}>
        <TableHead cols={cols} template={template} />
        {plans.map((p) => (
          <TableRow key={p.id} template={template} onClick={() => showPlan(p.id)} label={p.title} height={44} data={{ 'data-plan-row': p.id }}>
            <span style={{ fontWeight: 600, lineHeight: '18px', ...clamp2 }}>
              {p.title}
            </span>
            <span className="truncate" style={meta}>
              {p.tool.label}
            </span>
            <span style={{ ...meta, textAlign: 'right' }}>{p.lessons.length}</span>
            {!narrow && <span style={{ ...meta, textAlign: 'right' }}>{p.skills.length}</span>}
            <span style={{ ...meta, textAlign: 'right' }}>{hoursShort(planMinutes(p))}</span>
            {!narrow && (
              <span style={{ ...meta, ...clamp2 }}>
                {p.project.title}
              </span>
            )}
            {showAfter && (
              <span style={{ ...meta, ...clamp2 }}>
                {afterTitles(p)}
              </span>
            )}
          </TableRow>
        ))}
      </div>
    </section>
  )
}

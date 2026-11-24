/**
 * Feature: library. The Library page of the home window (features/shell), v4 (Adrian's docs/ui-next mock `library`,
 * Nov 23-24 trim pass; Michael's -22, first run -27). It uses the full width (1040), not the 720 column:
 *
 *   tabs        All · In progress · Ready · Finished · Plans, each with its count (the counts live here, no sentence)
 *   Your plans  the learner's plans: picture, next lesson, lessons left, a progress line ("3 of 8")
 *   tables      In progress / Ready to start / Finished: Lesson · Plan · Works in · Grows · Time · Progress · Opened.
 *               Columns drop as the pane narrows (Plan, Grows, Opened first). Green only on Passed.
 *   Start a plan four catalog plans the learner hasn't added, with All 40 plans
 *
 * First run (no lessons, no plans: -27): one line, the two ways to make a plan, eight plans to start, and five short
 * lessons. Never rows of zeros.
 *
 * The same page also hosts Browse plans and a plan's page (features/plans: store.ts `view`), so the shell's Library
 * entry keeps its place; the two "new plan" dialogs sit over it. The page title is the shell's header; its right side
 * (LessonSearch) carries New plan and New lesson (the one primary).
 *
 * Data: LibraryItem from the engine (library:list). Fields the ui-v4 contract adds (plan, passed, opened) are read
 * when present (`V4Item`); until then Plan comes from matching the title against the catalog and Opened from updatedAt.
 */
import { CloudOff, ListPlus, Search, SquarePen, X, Check } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import type { LibraryItem } from '../../../../../../shared/contracts/events'
import { cmd } from '../../../../common/wire'
import { bridge } from '../../bridge'
import { useLesson } from '../../core/lesson'
import { PrimaryButton, QuietButton } from '../../core/ui/buttons'
import { color, copy, fill, radius2, surface, type2 } from '../../core/theme'
import { Empty, PageColumn } from '../shell/ui'
import { Skeleton, TOOL_NAME } from './parts'
import { openDetail, setQuery, useLibrary } from './store'
import { aboutHours, FIRST_RUN, NEXT_UP, planById, planForLesson, PLANS, planShort, skillLabel, START_HERE, type Plan } from '../plans/catalog'
import { PlanDialogs } from '../plans/Dialogs'
import { PlanPage } from '../plans/PlanPage'
import { PlansPage } from '../plans/PlansPage'
import { openDialog, showPlan, showPlans, usePlans, type MyPlan } from '../plans/store'
import { artFor, artForId, Thumb, type Art } from '../plans/Thumb'
import { CardGrid, EntryCards, meta, MoreLink, PlanCard, RowStyle, SectionLabel, SkillChip, TableHead, TableRow, Tabs, useWidth, type Tab } from '../plans/ui'

/** New lesson: the launcher takes a goal or a pasted YouTube link (it builds; the library never does). */
export const openLauncher = (): void => bridge.emit('launcher:toggle')

/**
 * The right side of the Library's page header (the shell puts it there): New plan, and New lesson as the page's one
 * primary. On Browse plans and a plan's page it is empty (those pages carry their own actions).
 */
export function LessonSearch(): ReactNode {
  const view = usePlans((s) => s.view.kind)
  if (view !== 'library') return null
  return (
    <div data-no-drag data-library-actions className="flex items-center gap-[10px]">
      <QuietButton label="New plan" icon={ListPlus} onClick={showPlans} />
      <PrimaryButton label="New lesson" icon={SquarePen} keyName="launcher" onClick={openLauncher} />
    </div>
  )
}

/** Fields the ui-v4 contract adds to a library item. Read when present; nothing here invents them. */
type V4Item = LibraryItem & { planId?: string; passed?: boolean; passedAt?: string; openedAt?: string }
type LibTab = 'all' | 'progress' | 'ready' | 'finished' | 'plans'

const finished = (i: V4Item): boolean => i.passed === true || (!!i.progress && i.progress.total > 0 && i.progress.stepIndex >= i.progress.total)
const inProgress = (i: V4Item): boolean => !!i.progress && !finished(i)

function planOf(i: V4Item): Plan | undefined {
  return planById(i.planId) ?? planForLesson(i.title)
}
function artOf(i: V4Item): Art {
  const p = planOf(i)
  if (p) return artFor(p)
  const t = i.tools[0]
  return t === 'terminal' ? 'terminal' : t === 'jupyter' ? (/plot|chart/i.test(i.title) ? 'plot' : /csv|pandas|table|sales/i.test(i.title) ? 'table' : /neural|network|layer/i.test(i.title) ? 'network' : 'code') : t === 'excel' ? 'table' : 'code'
}
/** "Today", "Yesterday", "Nov 21". */
function dayLabel(at: string | undefined): string {
  if (!at) return ''
  const d = new Date(at)
  if (Number.isNaN(d.getTime())) return ''
  const today = new Date()
  const days = Math.round((new Date(today.toDateString()).getTime() - new Date(d.toDateString()).getTime()) / 86_400_000)
  if (days <= 0) return 'Today'
  if (days === 1) return 'Yesterday'
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}
/** The skills a lesson grows, as the catalog names them. An id the catalog doesn't know is left out (a raw id's last
 *  segment read as chips like "Wt" or "Vec"). */
const growsOf = (i: LibraryItem): string[] =>
  (i.teaches ?? [])
    .map((id) => skillLabel(id))
    .filter((l): l is string => !!l)
    .slice(0, 2)

/** A short progress line: ink on the track (never green), a fixed width so every row's line lines up. */
function ProgressLine({ done, total }: { done: number; total: number }): ReactNode {
  const f = total ? Math.max(0, Math.min(1, done / total)) : 0
  return (
    <span role="img" aria-label={`${done} of ${total}`} className="relative block shrink-0 overflow-hidden" style={{ width: 86, height: 3, borderRadius: radius2.round, background: fill.track }}>
      <span className="absolute inset-y-0 left-0 block" style={{ width: `${f * 100}%`, background: color.text, borderRadius: radius2.round }} />
    </span>
  )
}

function Passed(): ReactNode {
  return (
    <span className="flex items-center gap-[8px]" style={{ ...meta, color: color.text }}>
      <span aria-hidden className="flex items-center justify-center" style={{ width: 18, height: 18, borderRadius: radius2.round, background: color.green, color: color.onGreen }}>
        <Check size={12} strokeWidth={3} />
      </span>
      Passed
    </span>
  )
}

// ---- lesson tables --------------------------------------------------------------------------------------------------

type Cols = { plan: boolean; grows: boolean; opened: boolean; tool: boolean }
function colsFor(w: number): Cols {
  return { plan: w >= 900, grows: w >= 820, opened: w >= 700, tool: w >= 520 }
}
function template(c: Cols): string {
  return [
    'minmax(0,2.4fr)',
    c.plan ? 'minmax(0,1.2fr)' : '',
    c.tool ? 'minmax(64px,0.8fr)' : '',
    c.grows ? 'minmax(0,1.4fr)' : '',
    '56px',
    '150px',
    c.opened ? '76px' : ''
  ]
    .filter(Boolean)
    .join(' ')
}

function LessonTable({ label, items, cols, head }: { label: string; items: V4Item[]; cols: Cols; head: boolean }): ReactNode {
  const t = template(cols)
  return (
    <section data-lesson-table={label}>
      <SectionLabel count={items.length}>{label}</SectionLabel>
      <div role="table" aria-label={label}>
        {head && (
          <TableHead
            template={t}
            cols={[
              { label: 'Lesson' },
              ...(cols.plan ? [{ label: 'Plan' }] : []),
              ...(cols.tool ? [{ label: 'Works in' }] : []),
              ...(cols.grows ? [{ label: 'Grows' }] : []),
              { label: 'Time' },
              { label: 'Progress' },
              ...(cols.opened ? [{ label: 'Opened', align: 'right' as const }] : [])
            ]}
          />
        )}
        {items.map((i) => (
          <LessonRow key={i.id} item={i} cols={cols} template={t} />
        ))}
      </div>
    </section>
  )
}

function LessonRow({ item, cols, template: t }: { item: V4Item; cols: Cols; template: string }): ReactNode {
  const plan = planOf(item)
  const done = finished(item)
  const going = inProgress(item)
  const opened = dayLabel(done ? (item.passedAt ?? item.updatedAt) : (item.openedAt ?? item.updatedAt))
  return (
    <TableRow template={t} onClick={() => openDetail(item.id)} label={`${item.title}. Open its preview.`} height={48} data={{ 'data-lesson': item.id }}>
      <span className="flex min-w-0 items-center gap-[12px]">
        <Thumb art={artOf(item)} w={56} h={32} radius={radius2.keycap} />
        <span className="truncate" style={{ fontWeight: 600 }}>
          {item.title}
        </span>
      </span>
      {cols.plan && (
        <span className="truncate" style={meta}>
          {plan ? planShort(plan) : ''}
        </span>
      )}
      {cols.tool && (
        <span className="truncate" style={meta}>
          {item.tools[0] ? TOOL_NAME[item.tools[0]] : ''}
        </span>
      )}
      {cols.grows && (
        <span className="flex min-w-0 gap-[4px] overflow-hidden">
          {growsOf(item).map((g) => (
            <SkillChip key={g}>{g}</SkillChip>
          ))}
        </span>
      )}
      <span className="whitespace-nowrap" style={meta}>
        {item.estMinutes ? `${item.estMinutes} min` : ''}
      </span>
      <span className="flex items-center gap-[12px]">
        {done ? (
          <Passed />
        ) : going && item.progress ? (
          <>
            <ProgressLine done={item.progress.stepIndex} total={item.progress.total} />
            <span className="whitespace-nowrap" style={meta}>
              {item.progress.stepIndex} of {item.progress.total}
            </span>
          </>
        ) : (
          <span style={meta}>{item.ready ? 'Ready' : 'Not ready yet'}</span>
        )}
      </span>
      {cols.opened && (
        <span className="truncate" style={{ ...meta, textAlign: 'right' }}>
          {going || done ? opened : ''}
        </span>
      )}
    </TableRow>
  )
}

// ---- plans on the Library -------------------------------------------------------------------------------------------

function MyPlanCard({ p }: { p: MyPlan }): ReactNode {
  const left = Math.max(0, p.total - p.done)
  return (
    <button type="button" data-my-plan={p.id} onClick={() => showPlan(p.id)} className="mg-v4-row flex min-w-0 cursor-pointer items-center gap-[18px] text-left" style={{ background: 'none', border: 0, padding: 0, borderRadius: radius2.card, color: color.text }}>
      <Thumb art={artForId(p.art)} w={132} h={74} radius={radius2.card} />
      <span className="flex min-w-0 flex-1 flex-col" style={{ gap: 2 }}>
        <span className="truncate" style={{ fontSize: type2.md, lineHeight: '20px', fontWeight: 600 }}>
          {p.title}
        </span>
        {p.next && (
          <span className="truncate" style={meta}>
            Next · {p.next}
          </span>
        )}
        <span className="truncate" style={meta}>
          {left} {left === 1 ? 'lesson' : 'lessons'} left · {aboutHours(p.minutesLeft)}
        </span>
        <span className="flex items-center gap-[12px]" style={{ marginTop: 10 }}>
          <ProgressLine done={p.done} total={p.total} />
          <span style={meta}>
            {p.done} of {p.total}
          </span>
        </span>
      </span>
    </button>
  )
}

function YourPlans({ mine, cols }: { mine: MyPlan[]; cols: number }): ReactNode {
  return (
    <section data-your-plans>
      <SectionLabel right={<MoreLink onClick={showPlans}>Browse plans</MoreLink>}>Your plans</SectionLabel>
      <div className="grid" style={{ gridTemplateColumns: `repeat(${cols}, minmax(0,1fr))`, columnGap: 32, rowGap: 20 }}>
        {mine.map((p) => (
          <MyPlanCard key={p.id} p={p} />
        ))}
      </div>
    </section>
  )
}

function StartAPlan({ ids, cols }: { ids: string[]; cols: number }): ReactNode {
  const plans = ids.map((id) => planById(id)).filter((p): p is Plan => !!p)
  return (
    <section data-start-plan>
      <SectionLabel right={<MoreLink onClick={showPlans}>All {PLANS.length} plans</MoreLink>}>Start a plan</SectionLabel>
      <CardGrid cols={cols}>
        {plans.map((p) => (
          <PlanCard key={p.id} plan={p} />
        ))}
      </CardGrid>
    </section>
  )
}

/** First run: five short lessons from the catalog, each one step away from starting. */
const SHORT = [
  ['intro-python', 0],
  ['intro-sheets', 0],
  ['plotting', 0],
  ['intro-blender', 0],
  ['intro-terminal', 0]
] as const

function ShortLessons({ wide }: { wide: boolean }): ReactNode {
  const rows = SHORT.map(([id, n]) => ({ plan: planById(id), n })).filter((r): r is { plan: Plan; n: 0 } => !!r.plan)
  const t = wide ? 'minmax(0,2fr) minmax(0,1.3fr) minmax(0,1.3fr)' : 'minmax(0,1fr) minmax(0,1fr)'
  return (
    <section data-short-lessons>
      <SectionLabel>Or one short lesson</SectionLabel>
      <div role="table" aria-label="Short lessons">
        <TableHead template={t} cols={[{ label: 'Lesson' }, ...(wide ? [{ label: 'Grows' }] : []), { label: 'Works in', align: 'right' as const }]} />
        {rows.map(({ plan, n }) => {
          const l = plan.lessons[n]
          return (
            <TableRow key={plan.id} template={t} height={48} label={`Start ${l.title}`} onClick={() => bridge.send(cmd('learn', { query: l.goal, mode: 'lesson' }))} data={{ 'data-short': plan.id }}>
              <span className="flex min-w-0 items-center gap-[12px]">
                <Thumb art={artFor(plan)} w={56} h={32} radius={radius2.keycap} />
                <span className="truncate" style={{ fontWeight: 600 }}>
                  {l.title}
                </span>
              </span>
              {wide && (
                <span>
                  <SkillChip>{skillLabel(l.grows[0]) ?? l.grows[0]}</SkillChip>
                </span>
              )}
              <span className="truncate" style={{ ...meta, textAlign: 'right' }}>
                {plan.tool.label} · {l.steps} steps · {l.minutes} min
              </span>
            </TableRow>
          )
        })}
      </div>
    </section>
  )
}

function FirstRun({ cols, wide }: { cols: number; wide: boolean }): ReactNode {
  return (
    <>
      <p className="m-0" style={{ fontSize: type2.body, color: color.label }}>
        Nothing here yet. Start a plan, try one lesson, or make your own.
      </p>
      <EntryCards />
      <StartAPlan ids={FIRST_RUN} cols={cols} />
      <ShortLessons wide={wide} />
    </>
  )
}

// ---- the page -------------------------------------------------------------------------------------------------------

function SearchToggle(): ReactNode {
  const query = useLibrary((s) => s.query)
  const [open, setOpen] = useState(query !== '')
  if (!open)
    return (
      <button type="button" aria-label="Search lessons" onClick={() => setOpen(true)} className="flex cursor-pointer items-center justify-center" style={{ width: 28, height: 28, background: 'none', border: 0, borderRadius: radius2.control, color: color.label }}>
        <Search size={16} strokeWidth={1.8} />
      </button>
    )
  return (
    <span className="relative flex items-center">
      <Search aria-hidden size={14} strokeWidth={1.8} className="pointer-events-none absolute" style={{ left: 8, color: color.label }} />
      <input
        autoFocus
        type="search"
        aria-label="Search lessons"
        placeholder="Search lessons"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Escape') {
            e.preventDefault()
            e.stopPropagation()
            setQuery('')
            setOpen(false)
          }
        }}
        style={{ width: 200, height: 28, padding: '0 26px 0 28px', borderRadius: radius2.control, background: surface.well, border: 0, boxShadow: `inset 0 0 0 1px ${surface.border}`, color: color.text, fontSize: type2.sm, outline: 'none' }}
      />
      <button type="button" aria-label="Close search" onClick={() => (setQuery(''), setOpen(false))} className="absolute flex cursor-pointer" style={{ right: 6, background: 'none', border: 0, padding: 0, color: color.label }}>
        <X size={13} />
      </button>
    </span>
  )
}

function LibraryList(): ReactNode {
  const s = useLibrary()
  const mine = usePlans((p) => p.mine)
  const connected = useLesson((st) => st.connected)
  const [tab, setTab] = useState<LibTab>('all')
  const [ref, w] = useWidth<HTMLDivElement>()
  const q = s.query.trim().toLowerCase()
  const items = (s.items as V4Item[]).filter((i) => !q || i.title.toLowerCase().includes(q) || (planOf(i)?.title.toLowerCase().includes(q) ?? false))
  const going = items.filter(inProgress)
  const done = items.filter(finished)
  const ready = items.filter((i) => !inProgress(i) && !finished(i))
  // A column with nothing to say on any row (no lesson from a plan yet, no dates from the engine) is left out.
  const fit = colsFor(w)
  const cols: Cols = { ...fit, plan: fit.plan && items.some((i) => !!planOf(i)), opened: fit.opened && items.some((i) => !!dayLabel(i.openedAt ?? i.passedAt ?? i.updatedAt)) }
  const cardCols = w < 640 ? 2 : 4
  const planCols = w < 760 ? 1 : 2
  const fresh = s.loaded && s.items.length === 0 && mine.length === 0
  // Four the learner hasn't added: the mock's order (data tools first once a plan is going), then the rest of Start here.
  const toStart = (mine.length ? NEXT_UP : START_HERE).concat(FIRST_RUN).filter((id, n, all) => all.indexOf(id) === n && !mine.some((m) => m.id === id)).slice(0, 4)

  const tabs: Tab<LibTab>[] = [
    { id: 'all', label: 'All', count: items.length },
    { id: 'progress', label: 'In progress', count: going.length },
    { id: 'ready', label: 'Ready', count: ready.length },
    { id: 'finished', label: 'Finished', count: done.length },
    { id: 'plans', label: 'Plans', count: mine.length }
  ]
  const show = (t: LibTab): boolean => tab === 'all' || tab === t

  return (
    <div ref={ref} data-library-v4 className="flex flex-col" style={{ gap: 36 }}>
      {!s.loaded ? (
        <div className="flex flex-col gap-[8px]" aria-busy aria-label="Loading your lessons">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} h={48} />
          ))}
        </div>
      ) : fresh ? (
        <FirstRun cols={cardCols} wide={w >= 640} />
      ) : (
        <>
          <Tabs label="Library" tabs={tabs} value={tab} onChange={setTab} right={<SearchToggle />} />
          {s.items.length === 0 && !connected && tab !== 'plans' && (
            <Empty mark={<CloudOff aria-hidden size={28} strokeWidth={1.6} style={{ color: color.label }} />} title={`${copy.name} is offline.`} line="Your saved lessons show here when it connects." />
          )}
          {show('plans') && mine.length > 0 && !q && <YourPlans mine={mine} cols={planCols} />}
          {show('progress') && going.length > 0 && <LessonTable label="In progress" items={going} cols={cols} head />}
          {show('ready') && ready.length > 0 && <LessonTable label="Ready to start" items={ready} cols={cols} head={tab === 'ready' || going.length === 0} />}
          {show('finished') && done.length > 0 && <LessonTable label="Finished" items={done} cols={cols} head={tab === 'finished' || (going.length === 0 && ready.length === 0)} />}
          {q && !going.length && !ready.length && !done.length && (
            <span className="flex items-center gap-[12px]" style={meta}>
              No lessons match.
              <QuietButton label="Show all" onClick={() => setQuery('')} />
            </span>
          )}
          {tab === 'plans' && mine.length === 0 && (
            <div className="flex flex-col" style={{ gap: 16 }}>
              <span style={meta}>No plans yet.</span>
              <EntryCards />
            </div>
          )}
          {(tab === 'all' || tab === 'plans') && !q && <StartAPlan ids={toStart} cols={cardCols} />}
          {s.startError && (
            <span role="status" style={meta}>
              {s.startError.text}
            </span>
          )}
        </>
      )}
    </div>
  )
}

/** The Library page body (the shell scrolls it and keeps its scroll): the list, Browse plans, or one plan. */
export function Lessons(): ReactNode {
  const view = usePlans((s) => s.view)
  return (
    <PageColumn width="wide" data={{ 'data-lessons': '', 'data-view': view.kind }} style={{ color: color.text }}>
      {view.kind === 'plans' ? <PlansPage /> : view.kind === 'plan' || view.kind === 'custom' ? <PlanPage id={view.id} /> : <LibraryList />}
      <PlanDialogs />
      <RowStyle />
    </PageColumn>
  )
}

/** For tests and other surfaces: open the plan dialogs from anywhere in the window. */
export { openDialog as openPlanDialog }

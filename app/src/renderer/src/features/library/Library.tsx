/**
 * Feature: library. The Library page of the home window (features/shell), v4 (Adrian's docs/ui-next mock `library`,
 * Nov 23-24 trim pass; Michael's -22, first run -27). It uses the full width (1040), not the 720 column:
 *
 *   tabs        All · In progress · Ready · Finished · Plans, each with its count (the counts live here, no sentence)
 *   Your plans  the learner's plans: picture, next lesson, lessons left, a progress line ("3 of 8")
 *   tables      In progress / Ready to start / Finished: Lesson · Plan · Works in · Grows · Time · Progress · Opened.
 *               Each column is sized to its content (easing out to the mock's widths when there's room); one every
 *               row lacks is left out. Titles come first: Plan and Grows truncate, then columns drop (Plan, Grows,
 *               Opened, Works in) only when the titles still don't fit (tableCols.ts). Green only on Passed.
 *   Start a plan four catalog plans the learner hasn't added, with All 40 plans
 *
 * First run (no lessons, no plans: -27): one line, the two ways to make a plan, eight plans to start, and five short
 * lessons. Never rows of zeros.
 *
 * The same page also hosts Browse plans and a plan's page (features/plans: store.ts `view`), so the shell's Library
 * entry keeps its place; the two "new plan" dialogs sit over it. All three views render in the shell's v4 frame
 * (PageFrame + PageHeader, features/shell/ui.tsx): one title on the content's left edge, the actions flush right
 * (Library: New plan, and New lesson as the one primary). The shell's top bar carries the breadcrumb
 * (setCrumbs: Library / Browse plans / <plan>); its earlier parts go back a level.
 *
 * Data: LibraryItem from the engine (library:list), and the learner's plans (ui-v4 `plans`, features/plans/store.ts).
 * A lesson's plan, passed state and dates are read as the contract types them: the PlanLesson whose libraryId (or
 * lessonId) is the item's id gives its PlanState, `state: "done"` + doneAt, and openedAt. A lesson no plan claims
 * matches its title against the catalog for the Plan column and uses updatedAt for Opened.
 */
import { CloudOff, ListPlus, Search, SquarePen, X, Check } from 'lucide-react'
import { Fragment, useEffect, useMemo, useState, type ReactNode } from 'react'
import type { LibraryItem, PlanLesson, PlanState } from '../../../../../../shared/contracts/events'
import { cmd } from '../../../../common/wire'
import { bridge, engineMode } from '../../bridge'
import { canSend, useLesson } from '../../core/lesson'
import { PrimaryButton, QuietButton } from '../../core/ui/buttons'
import { color, copy, fill, radius2, surface, type2 } from '../../core/theme'
import { Empty, PageFrame, PageHeader, setCrumbs } from '../shell/ui'
import { useShell } from '../shell/store'
import { Skeleton, TOOL_NAME } from './parts'
import { openDetail, setQuery, useLibrary } from './store'
import { layoutCols, type ColKey, type ColsLayout } from './tableCols'
import { aboutHours, FIRST_RUN, NEXT_UP, planById, planForLesson, PLANS, planShort, skillLabel, START_HERE, type CatalogPlan } from '../plans/catalog'
import { PlanDialogs } from '../plans/Dialogs'
import { primeSkills, useSkills } from '../skills/store'
import { artForState, PlanPage, planTrail } from '../plans/PlanPage'
import { PlansPage } from '../plans/PlansPage'
import { loadPlans, openDialog, showLibrary, showPlan, showPlans, usePlans, type MyPlan } from '../plans/store'
import { artFor, Thumb, type Art } from '../plans/Thumb'
import { CardGrid, EntryCards, meta, MoreLink, PlanCard, RowStyle, SectionLabel, SkillChip, TableHead, TableRow, Tabs, useWidth, type Tab } from '../plans/ui'

/** New lesson: the launcher takes a goal or a pasted YouTube link (it builds; the library never does). */
export const openLauncher = (): void => bridge.emit('launcher:toggle')

/** The Library header's actions: New plan, and New lesson as the page's one primary. */
function LibraryActions(): ReactNode {
  return (
    <div data-no-drag data-library-actions className="flex items-center gap-[10px]">
      <QuietButton label="New plan" icon={ListPlus} onClick={showPlans} />
      <PrimaryButton label="New lesson" icon={SquarePen} keyName="launcher" onClick={openLauncher} />
    </div>
  )
}

/**
 * The shell's legacy page header still asks for this (Shell.tsx). The Library now draws its own v4 header
 * (PageHeader, with LibraryActions), and the shell hides its legacy title on a page with a PageFrame, so: nothing.
 */
export function LessonSearch(): ReactNode {
  return null
}

type LibTab = 'all' | 'progress' | 'ready' | 'finished' | 'plans'

/** A library item with what the learner's plans say about it (contract: PlanLesson.libraryId / lessonId). */
type Item = LibraryItem & { plan?: PlanState; lesson?: PlanLesson }

const finished = (i: Item): boolean => i.lesson?.state === 'done' || (!!i.progress && i.progress.total > 0 && i.progress.stepIndex >= i.progress.total)
const inProgress = (i: Item): boolean => !finished(i) && (!!i.progress || i.lesson?.state === 'in_progress')

function planOf(i: Item): CatalogPlan | undefined {
  return planById(i.plan?.catalogId) ?? planForLesson(i.title)
}
/** The Plan column: the learner's plan's name, else the catalog plan the title belongs to. */
function planName(i: Item): string {
  const c = planOf(i)
  if (c) return planShort(c)
  return i.plan?.title ?? ''
}
function artOf(i: Item): Art {
  if (i.plan && !planOf(i)) return artForState(i.plan)
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
/** Skill labels the engine's progress snapshot names (SkillInfo id → label), for ids the catalog doesn't know. */
function progressLabels(raw: unknown): Map<string, string> {
  const skills = (raw as { skills?: unknown } | undefined)?.skills
  const out = new Map<string, string>()
  // ProgressSnapshot.skills: one entry per track, each with its skills (a flat SkillInfo list reads the same).
  const add = (list: unknown): void => {
    if (!Array.isArray(list)) return
    for (const s of list as { id?: unknown; label?: unknown; skills?: unknown }[]) {
      if (typeof s?.id === 'string' && typeof s.label === 'string' && s.label.trim()) out.set(s.id, s.label.trim())
      if (s && Array.isArray(s.skills)) add(s.skills)
    }
  }
  add(skills)
  return out
}
function useKnownSkills(): Map<string, string> {
  const raw = useSkills((s) => s.raw)
  return useMemo(() => progressLabels(raw), [raw])
}
/** The skills a lesson grows: its own `teaches`, else the plan lesson's skillIds, named by the catalog or the engine's
 *  progress snapshot. An id neither knows is left out (a raw id's last segment read as chips like "Wt" or "Vec"). */
const growsOf = (i: Item, known?: Map<string, string>): string[] =>
  (i.teaches?.length ? i.teaches : (i.lesson?.skillIds ?? []))
    .map((id) => skillLabel(id) ?? known?.get(id))
    .filter((l): l is string => !!l)
    .slice(0, 2)
/** Works in: the lesson's tool, else its plan's (a Blender or FreeCAD plan lesson has no LessonTool of its own). */
const toolOf = (i: Item): string => (i.tools[0] ? TOOL_NAME[i.tools[0]] : (i.plan?.tool?.label ?? planOf(i)?.tool.label ?? ''))

/** A short progress line: ink on the track (never green), a fixed width so every row's line lines up. */
function ProgressLine({ done, total, width = 86 }: { done: number; total: number; width?: number }): ReactNode {
  const f = total ? Math.max(0, Math.min(1, done / total)) : 0
  return (
    <span role="img" aria-label={`${done} of ${total}`} className="relative block shrink-0 overflow-hidden" style={{ width, height: 3, borderRadius: radius2.round, background: fill.track }}>
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

/** The grid's column gap (TableHead / TableRow's default). */
const GAP = 16
/** The row's progress line: the mock's 64 px bar, then "4 of 7". */
const BAR = 64
/** A chip's side padding (SkillChip: 0 6px) and the gap between two chips. */
const CHIP_PAD = 12
const CHIP_GAP = 4
const HEAD = { plan: 'Plan', tool: 'Works in', grows: 'Grows', time: 'Time', progress: 'Progress', opened: 'Opened' } as const satisfies Record<ColKey, string>

/** Text width in the page's own type (Bricolage); an estimate when there is no canvas. */
let ctx: CanvasRenderingContext2D | null | undefined
let family = ''
function textWidth(t: string, size: number, weight = 400): number {
  if (!t) return 0
  if (ctx === undefined) {
    try {
      ctx = document.createElement('canvas').getContext('2d')
      family = getComputedStyle(document.body).fontFamily || 'system-ui'
    } catch {
      ctx = null
    }
  }
  if (!ctx) return Math.ceil(t.length * size * (weight >= 600 ? 0.55 : 0.5))
  ctx.font = `${weight} ${size}px ${family}`
  return Math.ceil(ctx.measureText(t).width)
}
const metaWidth = (t: string): number => textWidth(t, type2.sm)
const chipWidth = (t: string): number => metaWidth(t) + CHIP_PAD

/** When the lesson was opened (or passed): "Today", "Nov 21". Empty for one not started. */
function openedOf(i: Item): string {
  const done = finished(i)
  if (!done && !inProgress(i)) return ''
  return dayLabel(done ? (i.lesson?.doneAt ?? i.updatedAt) : (i.lesson?.openedAt ?? i.updatedAt))
}
/** The Progress cell's text: "Passed", "2 of 6", "Ready". */
function progressText(i: Item): string {
  if (finished(i)) return 'Passed'
  if (inProgress(i) && i.progress) return `${i.progress.stepIndex} of ${i.progress.total}`
  return i.ready ? 'Ready' : 'Not ready yet'
}

/**
 * The tables' layout for the rows on screen: each column sized to its longest cell (the header counts once a row has
 * something), 0 when every row lacks it (left out), and the Lesson column's need from its longest title.
 */
function measureCols(items: Item[], width: number, known: Map<string, string>): ColsLayout {
  const max = (k: ColKey, cell: (i: Item) => number): number => {
    const m = items.reduce((n, i) => Math.max(n, cell(i)), 0)
    return m > 0 ? Math.max(m, metaWidth(HEAD[k])) + 2 : 0
  }
  const title = items.reduce((m, i) => Math.max(m, textWidth(i.title, type2.md, 600)), 0) + 56 + 12 + 4
  return layoutCols({
    width,
    gap: GAP,
    title,
    need: {
      plan: max('plan', (i) => metaWidth(planName(i))),
      tool: max('tool', (i) => metaWidth(toolOf(i))),
      grows: max('grows', (i) => {
        const g = growsOf(i, known)
        return g.length ? g.reduce((n, t) => n + chipWidth(t), 0) + CHIP_GAP * (g.length - 1) : 0
      }),
      time: max('time', (i) => (i.estMinutes ? metaWidth(`${i.estMinutes} min`) : 0)),
      progress: max('progress', (i) => {
        const t = progressText(i)
        return t === 'Passed' ? 18 + 8 + metaWidth(t) : inProgress(i) && i.progress ? BAR + 12 + metaWidth(t) : metaWidth(t)
      }),
      opened: max('opened', (i) => metaWidth(openedOf(i)))
    }
  })
}

/** A Grows chip in a table cell: SkillChip's look, but it truncates instead of spilling over the next column. */
function GrowChip({ children, max }: { children: string; max?: number }): ReactNode {
  return (
    <span title={children} className="inline-block min-w-0 truncate" style={{ height: 22, lineHeight: '22px', padding: '0 6px', maxWidth: max, borderRadius: radius2.keycap, background: fill.chip, color: color.text, fontSize: type2.sm }}>
      {children}
    </span>
  )
}

/** The chips that fit the column: the first always (it truncates), the next only whole. */
function Grows({ skills, width }: { skills: string[]; width: number }): ReactNode {
  let used = 0
  const shown = skills.filter((s, n) => {
    const w = chipWidth(s) + (n ? CHIP_GAP : 0)
    if (n && used + w > width) return false
    used += w
    return true
  })
  return (
    <span className="flex min-w-0 overflow-hidden" style={{ gap: CHIP_GAP }}>
      {shown.map((g, n) => (
        <GrowChip key={g} max={n === 0 ? width : undefined}>
          {g}
        </GrowChip>
      ))}
    </span>
  )
}

function LessonTable({ label, items, layout, head }: { label: string; items: Item[]; layout: ColsLayout; head: boolean }): ReactNode {
  return (
    <section data-lesson-table={label}>
      <SectionLabel count={items.length}>{label}</SectionLabel>
      <div role="table" aria-label={label}>
        {head && <TableHead template={layout.template} gap={GAP} cols={[{ label: 'Lesson' }, ...layout.cols.map((c) => ({ label: HEAD[c.key], align: c.key === 'opened' ? ('right' as const) : undefined }))]} />}
        {items.map((i) => (
          <LessonRow key={i.id} item={i} layout={layout} />
        ))}
      </div>
    </section>
  )
}

function LessonRow({ item, layout }: { item: Item; layout: ColsLayout }): ReactNode {
  const known = useKnownSkills()
  const done = finished(item)
  const going = inProgress(item)
  const cell = (c: { key: ColKey; width: number }): ReactNode => {
    switch (c.key) {
      case 'plan':
        return <span className="truncate" style={meta} title={planName(item) || undefined}>{planName(item)}</span>
      case 'tool':
        return <span className="truncate" style={meta}>{toolOf(item)}</span>
      case 'grows':
        return <Grows skills={growsOf(item, known)} width={c.width} />
      case 'time':
        return <span className="truncate" style={meta}>{item.estMinutes ? `${item.estMinutes} min` : ''}</span>
      case 'progress':
        return (
          <span className="flex min-w-0 items-center gap-[12px]">
            {done ? (
              <Passed />
            ) : going && item.progress ? (
              <>
                <ProgressLine done={item.progress.stepIndex} total={item.progress.total} width={BAR} />
                <span className="whitespace-nowrap" style={meta}>
                  {progressText(item)}
                </span>
              </>
            ) : (
              <span className="truncate" style={meta}>{progressText(item)}</span>
            )}
          </span>
        )
      case 'opened':
        return <span className="truncate" style={{ ...meta, textAlign: 'right' }}>{openedOf(item)}</span>
    }
  }
  return (
    <TableRow template={layout.template} gap={GAP} onClick={() => openDetail(item.id)} label={`${item.title}. Open its preview.`} height={48} data={{ 'data-lesson': item.id }}>
      <span className="flex min-w-0 items-center gap-[12px]">
        <Thumb art={artOf(item)} w={56} h={32} radius={radius2.keycap} />
        <span className="truncate" style={{ fontWeight: 600 }} title={layout.titleFits ? undefined : item.title}>
          {item.title}
        </span>
      </span>
      {layout.cols.map((c) => (
        <Fragment key={c.key}>{cell(c)}</Fragment>
      ))}
    </TableRow>
  )
}

// ---- plans on the Library -------------------------------------------------------------------------------------------

function MyPlanCard({ p }: { p: MyPlan }): ReactNode {
  const left = Math.max(0, p.total - p.done)
  const next = p.nextIndex != null ? p.lessons[p.nextIndex] : undefined
  const minutesLeft = p.minutesLeft ?? p.lessons.filter((l) => l.state !== 'done').reduce((n, l) => n + (l.minutes ?? Math.round((l.seconds ?? 0) / 60)), 0)
  return (
    <button type="button" data-my-plan={p.id} onClick={() => showPlan(p.catalogId && planById(p.catalogId) ? p.catalogId : p.id)} className="mg-v4-row flex min-w-0 cursor-pointer items-center gap-[18px] text-left" style={{ background: 'none', border: 0, padding: 0, borderRadius: radius2.card, color: color.text }}>
      <Thumb art={artForState(p)} w={132} h={74} radius={radius2.card} />
      <span className="flex min-w-0 flex-1 flex-col" style={{ gap: 2 }}>
        <span className="truncate" style={{ fontSize: type2.md, lineHeight: '20px', fontWeight: 600 }}>
          {p.title}
        </span>
        {next && (
          <span style={{ ...meta, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
            Next · {next.title}
          </span>
        )}
        <span className="truncate" style={meta}>
          {left === 0 ? 'Every lesson passed' : `${left} ${left === 1 ? 'lesson' : 'lessons'} left · ${aboutHours(minutesLeft)}`}
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
  const plans = ids.map((id) => planById(id)).filter((p): p is CatalogPlan => !!p)
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
  const rows = SHORT.map(([id, n]) => ({ plan: planById(id), n })).filter((r): r is { plan: CatalogPlan; n: 0 } => !!r.plan)
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
        className="[&::-webkit-search-cancel-button]:hidden"
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
        style={{ width: 200, height: 28, padding: '0 30px 0 28px', borderRadius: radius2.control, background: surface.well, border: 0, boxShadow: `inset 0 0 0 1px ${surface.border}`, color: color.text, fontSize: type2.sm, outline: 'none' }}
      />
      <button type="button" aria-label="Close search" onClick={() => (setQuery(''), setOpen(false))} className="absolute flex cursor-pointer items-center justify-center" style={{ right: 2, width: 24, height: 24, background: 'none', border: 0, padding: 0, color: color.label }}>
        <X size={14} />
      </button>
    </span>
  )
}

/** Each library item with the plan lesson that built it (PlanLesson.libraryId, else lessonId). */
function withPlans(items: LibraryItem[], mine: PlanState[]): Item[] {
  const by = new Map<string, { plan: PlanState; lesson: PlanLesson }>()
  for (const plan of mine)
    for (const lesson of plan.lessons) {
      if (lesson.libraryId) by.set(lesson.libraryId, { plan, lesson })
      if (lesson.lessonId && !by.has(lesson.lessonId)) by.set(lesson.lessonId, { plan, lesson })
    }
  return items.map((i) => ({ ...i, ...by.get(i.id) }))
}

function LibraryList(): ReactNode {
  const s = useLibrary()
  const mine = usePlans((p) => p.mine)
  const connected = useLesson((st) => st.connected)
  const [tab, setTab] = useState<LibTab>('all')
  const [ref, w] = useWidth<HTMLDivElement>()
  const q = s.query.trim().toLowerCase()
  const all = useMemo(() => withPlans(s.items, mine), [s.items, mine])
  const items = all.filter((i) => !q || i.title.toLowerCase().includes(q) || planName(i).toLowerCase().includes(q))
  const going = items.filter(inProgress)
  const done = items.filter(finished)
  const ready = items.filter((i) => !inProgress(i) && !finished(i))
  const known = useKnownSkills()
  // Grows names an engine skill id through the progress snapshot: paint main's last one, ask once if there is none.
  useEffect(() => {
    void primeSkills().then(() => {
      if (!useSkills.getState().raw && (canSend('progress.get') || engineMode() === 'inline')) bridge.send(cmd('progress.get', {}))
    })
  }, [])
  const cardCols = w < 640 ? 2 : 4
  const planCols = w < 760 ? 1 : 2
  const fresh = s.loaded && s.items.length === 0 && mine.length === 0
  // Four the learner hasn't added: the mock's order (data tools first once a plan is going), then the rest of Start here.
  const has = (id: string): boolean => mine.some((m) => m.id === id || m.catalogId === id)
  const toStart = (mine.length ? NEXT_UP : START_HERE).concat(FIRST_RUN).filter((id, n, list) => list.indexOf(id) === n && !has(id)).slice(0, 4)

  // A tab with nothing in it is hidden (All always shows). Counted before the search, so tabs never jump while typing.
  const total: Record<LibTab, number> = { all: all.length, progress: all.filter(inProgress).length, finished: all.filter(finished).length, ready: 0, plans: mine.length }
  total.ready = all.length - total.progress - total.finished
  const tabs = ([
    { id: 'all', label: 'All', count: items.length },
    { id: 'progress', label: 'In progress', count: going.length },
    { id: 'ready', label: 'Ready', count: ready.length },
    { id: 'finished', label: 'Finished', count: done.length },
    { id: 'plans', label: 'Plans', count: mine.length }
  ] as Tab<LibTab>[]).filter((t) => t.id === 'all' || t.id === tab || total[t.id] > 0)
  const show = (t: LibTab): boolean => tab === 'all' || tab === t
  // The tables share one layout, made from the rows on screen: a column every row lacks is left out (no lesson from a
  // plan yet, no dates from the engine), titles get their room first, Plan and Grows give way (tableCols.ts).
  const onScreen = [...(show('progress') ? going : []), ...(show('ready') ? ready : []), ...(show('finished') ? done : [])]
  const layout = measureCols(onScreen, w, known)

  return (
    <div ref={ref} data-library-v4 className="flex flex-col" style={{ gap: 36 }}>
      {!s.loaded ? (
        <>
          {/* The plans can land before the lessons do: show them as soon as they arrive. */}
          {mine.length > 0 && <YourPlans mine={mine} cols={planCols} />}
          <div className="flex flex-col gap-[8px]" aria-busy aria-label="Loading your lessons">
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} h={48} />
            ))}
          </div>
        </>
      ) : fresh ? (
        <FirstRun cols={cardCols} wide={w >= 640} />
      ) : (
        <>
          <Tabs label="Library" tabs={tabs} value={tab} onChange={setTab} right={<SearchToggle />} />
          {s.items.length === 0 && !connected && tab !== 'plans' && (
            <Empty mark={<CloudOff aria-hidden size={28} strokeWidth={1.6} style={{ color: color.label }} />} title={`${copy.name} is offline.`} line="Your saved lessons show here when it connects." />
          )}
          {show('plans') && mine.length > 0 && !q && <YourPlans mine={mine} cols={planCols} />}
          {show('progress') && going.length > 0 && <LessonTable label="In progress" items={going} layout={layout} head />}
          {show('ready') && ready.length > 0 && <LessonTable label="Ready to start" items={ready} layout={layout} head={tab === 'ready' || going.length === 0} />}
          {show('finished') && done.length > 0 && <LessonTable label="Finished" items={done} layout={layout} head={tab === 'finished' || (going.length === 0 && ready.length === 0)} />}
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

/** The trail the shell's top bar draws after "Library" for each view (null: the Library itself). */
function trailFor(view: ReturnType<typeof usePlans.getState>['view'], mineTitle: string | undefined): string[] | null {
  if (view.kind === 'plans') return ['Browse plans']
  if (view.kind === 'plan') return planTrail(view.id)
  if (view.kind === 'custom') return [mineTitle ?? 'Plan']
  return null
}

/**
 * The top bar's crumbs are the shell's (plain text). On a deeper view, its earlier parts go back: "Library" to the
 * list, "Browse plans" to the catalog. Delegated from the page, so the shell's bar needs no Library code.
 */
function useCrumbBack(depth: number): void {
  const here = useShell((s) => s.page === 'lessons')
  useEffect(() => {
    if (depth === 0 || !here) return
    // .mg-crumb-back (plans/ui.tsx RowStyle): the earlier crumbs read as links.
    document.documentElement.classList.add('mg-crumb-back')
    const onClick = (e: MouseEvent): void => {
      const nav = document.querySelector('[data-v4-top] nav')
      const part = (e.target as Element | null)?.closest?.('[data-v4-top] nav > span')
      if (!nav || !part || part.getAttribute('aria-current') === 'page') return
      const i = [...nav.children].indexOf(part)
      if (i === 0) showLibrary()
      else if (i === 1 && depth === 2) showPlans()
    }
    document.addEventListener('click', onClick)
    return () => {
      document.removeEventListener('click', onClick)
      document.documentElement.classList.remove('mg-crumb-back')
    }
  }, [depth, here])
}

/** The Library page (the shell's Library entry): the list, Browse plans, or one plan, in the shell's v4 frame. */
export function Lessons(): ReactNode {
  const view = usePlans((s) => s.view)
  const customTitle = usePlans((s) => (s.view.kind === 'custom' ? s.mine.find((m) => m.id === (s.view as { id: string }).id)?.title : undefined))
  const trail = trailFor(view, customTitle)
  const key = trail?.join('/') ?? ''
  useEffect(() => {
    setCrumbs('lessons', trail)
    return () => setCrumbs('lessons', null)
    // key is the trail's content.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])
  // The learner's plans: asked once per visit (the engine pushes `plans` again when one changes).
  useEffect(() => loadPlans(), [])
  useCrumbBack(trail ? trail.length : 0)
  return (
    <PageFrame data={{ 'data-lessons': '', 'data-view': view.kind }} style={{ color: color.text }}>
      {view.kind === 'plans' ? (
        <PlansPage />
      ) : view.kind === 'plan' || view.kind === 'custom' ? (
        <PlanPage id={view.id} />
      ) : (
        <div className="flex flex-col" style={{ gap: 28 }}>
          <PageHeader title="Library" right={<LibraryActions />} />
          <LibraryList />
        </div>
      )}
      <PlanDialogs />
      <RowStyle />
    </PageFrame>
  )
}

/** For tests and other surfaces: open the plan dialogs from anywhere in the window. */
export { openDialog as openPlanDialog }

/**
 * Feature: plans. One plan (Adrian's mock `plan`): the title and line, five facts (works in, length, ends with,
 * checked by, grows), the picture with the one primary action, the lessons as a full-width table, and under it two
 * blocks side by side: the project, and "Rather follow a video" with "After this plan". Trim pass (Nov 24): one note
 * under the project, no "Added" date, no repeated video count.
 *
 * The Library page puts it in the shell's v4 frame (features/shell/ui.tsx PageFrame); its title is a PageHeader and
 * the shell's top bar carries the breadcrumb ("Library / Browse plans / Intro to Blender", planTrail).
 *
 * A plan the learner made (from a playlist or a goal) uses the same page with the lessons its PlanState carries. A
 * plan the learner has marks its passed lessons and starts any lesson with plan: {id, index} (store.ts startLesson).
 */
import { Check, Circle, Eye, Flag, GitFork, List, Play, SquarePlay, SquareTerminal, ChevronRight } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import type { PlanState } from '../../../../../../shared/contracts/events'
import { PrimaryButton, QuietButton } from '../../core/ui/buttons'
import { color, radius2, type2 } from '../../core/theme'
import { PageHeader } from '../shell/ui'
import { aboutHours, checkedBy, nextPlans, planById, planMinutes, playlistInfoFromCatalog, playlistsFor, skillLabel, type CatalogPlan } from './catalog'
import { addPlaylistPlan, myPlan, removePlan, showPlan, startLesson, startNext, startPlan, usePlans } from './store'
import { artFor, artForId, Thumb, type Art } from './Thumb'
import { hair, meta, SectionLabel, SkillChip, TableHead, TableRow, useWidth } from './ui'

/** One row of the lessons table: a catalog lesson, or a lesson of the learner's plan (PlanState). */
type Row = { title: string; passes?: string; grows: string[]; steps?: number; minutes?: number; passed: boolean }
type Page = { id: string; title: string; line?: string; tool?: string; lessons: Row[]; ends?: string; checked?: string; skills: string[]; art: Art; plan?: CatalogPlan }

function fromPlan(p: CatalogPlan, mine: PlanState | undefined): Page {
  const lessons = p.lessons.map((l, i) => ({ title: l.title, passes: l.passes, grows: l.grows, steps: l.steps, minutes: l.minutes, passed: mine?.lessons[i]?.state === 'done' }))
  return { id: p.id, title: p.title, line: p.line, tool: [p.tool.label, ...p.also].join(' · '), lessons, ends: p.project.title, checked: checkedBy(p), skills: p.skills.map((s) => s.label), art: artFor(p), plan: p }
}

/** A plan's picture when it has no catalog plan: from its tool (a Blender playlist draws the mug). */
export function artForState(m: PlanState): Art {
  const base = planById(m.catalogId)
  if (base) return artFor(base)
  const t = m.tool?.id
  if (t === 'blender' || t === 'unity' || t === 'godot') return 'mug'
  if (t === 'freecad' || t === 'fusion' || t === 'onshape') return 'plate'
  if (t === 'jupyter') return 'plot'
  if (t === 'excel' || t === 'sheets') return 'table'
  if (t === 'terminal' || t === 'docker') return 'terminal'
  return artForId(m.id)
}

function fromMine(m: PlanState): Page {
  const lessons = m.lessons.map((l) => ({ title: l.title, passes: l.passes, grows: l.skillIds ?? [], steps: l.stepCount, minutes: l.minutes ?? (l.seconds ? Math.round(l.seconds / 60) : undefined), passed: l.state === 'done' }))
  const skills = [...new Set(lessons.flatMap((l) => l.grows.map((g) => skillLabel(g) ?? '')).filter(Boolean))]
  return { id: m.id, title: m.title, line: m.goal, tool: m.tool?.label, lessons, ends: m.project?.title, skills, art: artForState(m) }
}

/** The plan page's breadcrumb trail after "Library" (the shell's top bar draws it). */
export function planTrail(id: string): string[] {
  const p = planById(id)
  if (p) return ['Browse plans', p.title]
  return [myPlan(id)?.title ?? 'Plan']
}

/** The plan page's body (the Library page frames it). */
export function PlanPage({ id }: { id: string }): ReactNode {
  const mine = usePlans((s) => s.mine.find((m) => m.id === id || m.catalogId === id))
  const plan = planById(id)
  const page = plan ? fromPlan(plan, mine) : mine ? fromMine(mine) : undefined
  const [ref, w] = useWidth<HTMLDivElement>()
  if (!page) {
    return (
      <div className="flex flex-col" style={{ gap: 16 }}>
        <PageHeader title="Plan" />
        <p style={meta}>That plan isn’t here any more.</p>
      </div>
    )
  }
  const narrow = w < 760
  // Below 760 the picture shrinks beside the title rather than stacking full width above it (QA R2-01); only a very
  // narrow column stacks, and then the title, facts and action come first. Beside the picture the title column can be
  // narrower than a long title (332 px at a 556 px page), so the PageHeader wraps it onto two lines instead of clipping.
  const stack = w < 520
  const side = narrow ? 200 : 300
  const done = mine?.done ?? 0
  const minutes = page.lessons.reduce((n, l) => n + (l.minutes ?? 0), 0)
  const start = (): void => {
    if (mine) startNext(mine)
    else if (plan) startPlan(plan)
  }
  const finished = !!mine && mine.nextIndex === null
  const action = !mine || finished ? 'Start plan' : done > 0 || mine.lessons.some((l) => l.state === 'in_progress') ? `Continue lesson ${(mine.nextIndex ?? done) + 1}` : 'Start plan'

  const facts: Array<[ReactNode, string, ReactNode]> = [
    ...(page.tool ? [[<SquareTerminal key="i" size={15} strokeWidth={1.6} />, 'Works in', page.tool] as [ReactNode, string, ReactNode]] : []),
    [<List key="i" size={15} strokeWidth={1.6} />, 'Length', `${page.lessons.length} lessons · ${aboutHours(minutes)}`],
    ...(page.ends ? [[<Flag key="i" size={15} strokeWidth={1.6} />, 'Ends with', page.ends] as [ReactNode, string, ReactNode]] : []),
    ...(page.checked ? [[<Eye key="i" size={15} strokeWidth={1.6} />, 'Checked by', page.checked] as [ReactNode, string, ReactNode]] : []),
    ...(page.skills.length
      ? [
          [
            <GitFork key="i" size={15} strokeWidth={1.6} />,
            'Grows',
            <span key="g" className="flex flex-wrap gap-[6px]">
              {page.skills.map((s) => (
                <SkillChip key={s}>{s}</SkillChip>
              ))}
            </span>
          ] as [ReactNode, string, ReactNode]
        ]
      : [])
  ]

  return (
    <div ref={ref} data-plan-page={page.id} className="flex flex-col" style={{ gap: 32 }}>
      <div className={stack ? 'flex flex-col' : 'flex items-start'} style={{ gap: narrow ? 24 : 40 }}>
        <div className="flex min-w-0 flex-1 flex-col" style={{ gap: 20 }}>
          <PageHeader title={page.title} lede={page.line} wrap />
          <dl className="m-0 grid" style={{ gridTemplateColumns: `${narrow ? 120 : 148}px minmax(0,1fr)`, rowGap: 12, alignItems: 'start' }}>
            {facts.map(([icon, k, v]) => (
              <div key={k} className="contents">
                <dt className="flex items-center gap-[10px]" style={{ ...meta, fontSize: type2.md, minHeight: 22 }}>
                  <span style={{ color: color.faint, display: 'flex' }}>{icon}</span>
                  {k}
                </dt>
                <dd className="m-0" style={{ fontSize: type2.md, lineHeight: '22px', color: color.text }}>
                  {v}
                </dd>
              </div>
            ))}
          </dl>
        </div>
        <div className="flex shrink-0 flex-col" style={{ width: stack ? Math.min(w, 300) : side, gap: 12 }}>
          <Thumb art={page.art} w="100%" radius={radius2.card} />
          <PrimaryButton label={action} icon={Play} onClick={start} size="lg" block />
          {mine && <RemoveButton id={mine.id} />}
        </div>
      </div>

      <section>
        <SectionLabel count={page.lessons.length} right={<span style={meta}>{aboutHours(minutes)}</span>}>
          Lessons
        </SectionLabel>
        <LessonTable lessons={page.lessons} narrow={narrow} onStart={mine ? (i) => startLesson(mine, i) : undefined} />
      </section>

      {plan && (
        <div className={narrow ? 'flex flex-col' : 'grid'} style={{ gridTemplateColumns: '1fr 1fr', columnGap: 48, rowGap: 32 }}>
          <Project plan={plan} />
          <div className="flex flex-col" style={{ gap: 28 }}>
            <Videos plan={plan} />
            <After plan={plan} />
          </div>
        </div>
      )}
    </div>
  )
}

/** How long Remove plan stays armed for its second click. */
const REMOVE_ARM_MS = 4000

/** Remove plan asks for a second click, as End lesson does (QA R2-04): the first arms it, the next within 4 s removes. */
function RemoveButton({ id }: { id: string }): ReactNode {
  const [armed, setArmed] = useState(false)
  useEffect(() => {
    if (!armed) return
    const t = setTimeout(() => setArmed(false), REMOVE_ARM_MS)
    return () => clearTimeout(t)
  }, [armed])
  return (
    <span className="flex flex-col" data-plan-remove={armed ? 'armed' : 'idle'} aria-live="polite">
      <QuietButton label={armed ? 'Click again to remove' : 'Remove plan'} onClick={() => (armed ? removePlan(id) : setArmed(true))} />
    </span>
  )
}

function LessonTable({ lessons, narrow, onStart }: { lessons: Row[]; narrow: boolean; onStart?: (i: number) => void }): ReactNode {
  const template = narrow ? '28px minmax(0,1fr) 56px' : '28px minmax(0,1.15fr) minmax(0,2.3fr) minmax(0,0.95fr) 44px 56px'
  const cols = narrow
    ? [{ label: '' }, { label: 'Lesson' }, { label: 'Time', align: 'right' as const }]
    : [{ label: '' }, { label: 'Lesson' }, { label: 'Passes when' }, { label: 'Grows' }, { label: 'Steps', align: 'right' as const }, { label: 'Time', align: 'right' as const }]
  return (
    <div role="table" aria-label="Lessons">
      <TableHead cols={cols} template={template} />
      {lessons.map((l, i) => (
        <TableRow key={`${i}-${l.title}`} template={template} label={onStart ? `Start ${l.title}` : l.title} height={52} onClick={onStart ? () => onStart(i) : undefined} data={{ 'data-plan-lesson': String(i + 1) }}>
          <span style={{ ...meta, display: 'flex' }}>
            {l.passed ? (
              <span aria-label="Passed" className="flex items-center justify-center" style={{ width: 16, height: 16, borderRadius: radius2.round, background: color.green, color: color.onGreen }}>
                <Check size={11} strokeWidth={3} />
              </span>
            ) : (
              i + 1
            )}
          </span>
          <span style={{ fontWeight: 600, lineHeight: '20px' }}>{l.title}</span>
          {!narrow && <span style={{ ...meta, fontSize: type2.md, lineHeight: '20px' }}>{l.passes ?? ''}</span>}
          {!narrow && (
            <span className="flex flex-wrap gap-[4px]">
              {l.grows
                .map((g) => skillLabel(g))
                .filter((g): g is string => !!g)
                .map((g) => (
                  <SkillChip key={g}>{g}</SkillChip>
                ))}
            </span>
          )}
          {!narrow && <span style={{ ...meta, textAlign: 'right' }}>{l.steps ?? ''}</span>}
          <span style={{ ...meta, textAlign: 'right' }}>{l.minutes !== undefined ? `${l.minutes} min` : ''}</span>
        </TableRow>
      ))}
    </div>
  )
}

function BlockHead({ children }: { children: ReactNode }): ReactNode {
  return (
    <h2 className="m-0" style={{ fontSize: type2.body, lineHeight: '22px', fontWeight: 600, color: color.text, paddingBottom: 10, borderBottom: hair }}>
      {children}
    </h2>
  )
}

function Project({ plan }: { plan: CatalogPlan }): ReactNode {
  return (
    <section data-plan-project className="flex flex-col">
      <BlockHead>The project</BlockHead>
      <span style={{ marginTop: 14, fontSize: type2.md, lineHeight: '20px', fontWeight: 600, color: color.text }}>{plan.project.title}</span>
      <p className="m-0" style={{ ...meta, fontSize: type2.md, lineHeight: '20px', marginTop: 4, maxWidth: 520 }}>
        {plan.project.brief}
      </p>
      <ul className="m-0 flex list-none flex-col p-0" style={{ marginTop: 12 }}>
        {plan.project.checks.map((c) => (
          <li key={c} className="flex items-center gap-[10px]" style={{ minHeight: 34, borderBottom: hair, fontSize: type2.md, color: color.text }}>
            <Circle aria-hidden size={15} strokeWidth={1.5} style={{ color: color.faint, flexShrink: 0 }} />
            {c}
          </li>
        ))}
      </ul>
      <span style={{ ...meta, marginTop: 12 }}>On your own, about 45 minutes.</span>
    </section>
  )
}

function LinkRow({ icon, title, right, onClick }: { icon?: ReactNode; title: string; right: string; onClick: () => void }): ReactNode {
  return (
    <button type="button" onClick={onClick} className="mg-v4-row flex w-full cursor-pointer items-center gap-[10px] text-left" style={{ minHeight: 36, background: 'none', border: 0, borderBottom: hair, padding: 0, color: color.text }}>
      {icon && <span style={{ color: color.label, display: 'flex' }}>{icon}</span>}
      <span className="min-w-0 flex-1 truncate" style={{ fontSize: type2.md, fontWeight: 600 }}>
        {title}
      </span>
      <span className="shrink-0 truncate" style={meta}>
        {right}
      </span>
      <ChevronRight size={14} strokeWidth={1.8} style={{ color: color.faint, flexShrink: 0 }} />
    </button>
  )
}

/** The plan's playlists: picking one makes a plan from it (plan.start {playlistId, url, proposal}); it isn't started. */
function Videos({ plan }: { plan: CatalogPlan }): ReactNode {
  const lists = playlistsFor(plan.id)
  if (!lists.length) return null
  return (
    <section className="flex flex-col">
      <BlockHead>Rather follow a video</BlockHead>
      {lists.map((l) => (
        <LinkRow
          key={l.playlistId}
          icon={<SquarePlay size={15} strokeWidth={1.6} />}
          title={l.title}
          right={`${l.channel} · ${l.videoCount} videos`}
          onClick={() => {
            const info = playlistInfoFromCatalog(l)
            if (info.proposal) addPlaylistPlan({ playlistId: l.playlistId, url: l.url }, info.proposal, false)
          }}
        />
      ))}
    </section>
  )
}

function After({ plan }: { plan: CatalogPlan }): ReactNode {
  const next = nextPlans(plan)
  if (!next.length) return null
  return (
    <section className="flex flex-col">
      <BlockHead>After this plan</BlockHead>
      {next.map((p) => (
        <LinkRow key={p.id} title={p.title} right={`${p.lessons.length} lessons · ${aboutHours(planMinutes(p))}`} onClick={() => showPlan(p.id)} />
      ))}
    </section>
  )
}

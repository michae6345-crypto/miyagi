/**
 * Feature: apps. One app's page (Adrian's MIC-87 mock `apps-app-*`): everything miyagi has for the app, on the Library
 * page (the shell's top bar reads "Library / Browse plans / Blender").
 *
 *   header    the app's name, four facts (On this Mac, To learn, Checked by, Starts with), the start plan's picture
 *             and the one action:
 *               installed / unknown  Start <plan> (Continue <plan> when the learner has it going). It opens the app.
 *               not installed        Get <app> (where main's setup list allows its page) and I have it. The lessons
 *                                    stay visible.
 *   lessons   the start plan's first five lessons with what passes each ("The whole plan" opens it)
 *   yours     the learner's own lessons in this app (the Library's, inferred per lesson: model.ts lessonApp) and
 *             their own plans here
 *   more      the app's other catalog plans
 *   skills    what the app's plans grow, as chips, with a link to Skills
 *   make      make your own in this app: from a video, or from a goal (the two plan dialogs)
 *
 * Data: the plans catalog, the Library's items, the learner's plans. A click never starts a lesson from here except the
 * one Start button; rows open the plan or the lesson's preview.
 */
import { ArrowUpRight, Check, Eye, Flag, List, Monitor, Play, SquarePlay, Sprout, ChevronRight } from 'lucide-react'
import { useMemo, type ReactNode } from 'react'
import type { LibraryItem, PlanState } from '../../../../../../shared/contracts/events'
import { color, radius2, surface, type2 } from '../../core/theme'
import { PrimaryButton, QuietButton } from '../../core/ui/buttons'
import { openDetail, useLibrary } from '../library/store'
import { aboutHours, afterTitles, checkedBy, endsWith, hoursShort, planMinutes, PLANS, skillLabel, START_HERE, type CatalogPlan } from '../plans/catalog'
import { openDialog, showPlan, showPlans, startNext, startPlan, usePlans } from '../plans/store'
import { artFor, Thumb } from '../plans/Thumb'
import { meta, MoreLink, SectionLabel, SkillChip, TableHead, TableRow, useWidth } from '../plans/ui'
import { PageHeader } from '../shell/ui'
import { setPage } from '../shell/store'
import { appContent, appMeta, type AppContent, type InstallState } from './model'
import { getApp, markHave, useAppStates } from './store'
import { StateLine } from './ui'

/** The start plan's lessons the page shows (the mock's five). */
const FIRST_LESSONS = 5
/** Other plans before "Browse plans" takes over. */
const MORE_MAX = 8
const SKILLS_MAX = 16

/** The app page's trail after "Library" (the shell's top bar draws it). */
export function appTrail(id: string): string[] {
  return ['Browse plans', appContent(id, PLANS, [], []).name]
}

const lower = (s: string): string => s.charAt(0).toLowerCase() + s.slice(1)

export function AppPage({ id }: { id: string }): ReactNode {
  const items = useLibrary((s) => s.items)
  const mine = usePlans((s) => s.mine)
  const states = useAppStates(false)
  const c = useMemo(() => appContent(id, PLANS, items, mine, START_HERE), [id, items, mine])
  const [ref, w] = useWidth<HTMLDivElement>()
  const meta0 = appMeta(id)
  if (!meta0 || !c.plans.length) {
    return (
      <div className="flex flex-col" style={{ gap: 16 }} data-app-page={id}>
        <PageHeader title={c.name} />
        <p style={meta}>miyagi doesn’t teach in this app yet.</p>
      </div>
    )
  }
  const narrow = w < 760
  const stack = w < 520
  const side = narrow ? 220 : 300
  const state = states[id]
  const start = c.start
  const startMine = start ? mine.find((m) => m.catalogId === start.id || m.id === start.id) : undefined

  const facts: Array<[ReactNode, string, ReactNode]> = [
    [<Monitor key="i" size={15} strokeWidth={1.6} />, 'On this Mac', <StateLine key="s" state={state} />],
    [<List key="i" size={15} strokeWidth={1.6} />, 'To learn', `${c.plans.length} ${c.plans.length === 1 ? 'plan' : 'plans'} · ${c.lessonCount} lessons · ${aboutHours(c.minutes)}`],
    ...(start ? [[<Eye key="i" size={15} strokeWidth={1.6} />, 'Checked by', checkedBy(start)] as [ReactNode, string, ReactNode]] : []),
    ...(start ? [[<Flag key="i" size={15} strokeWidth={1.6} />, 'Starts with', `${start.title}, which ${lower(endsWith(start))}`] as [ReactNode, string, ReactNode]] : [])
  ]

  return (
    <div ref={ref} data-app-page={id} data-app-state={state} className="flex flex-col" style={{ gap: 32 }}>
      <div className={stack ? 'flex flex-col' : 'flex items-start'} style={{ gap: narrow ? 24 : 40 }}>
        <div className="flex min-w-0 flex-1 flex-col" style={{ gap: 20 }}>
          <PageHeader title={meta0.fullName ?? c.name} wrap />
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
        {start && (
          <div className="flex shrink-0 flex-col" style={{ width: stack ? Math.min(w, 300) : side, gap: 12 }}>
            <Thumb art={artFor(start)} w="100%" radius={radius2.card} />
            <Action c={c} state={state} start={start} mine={startMine} />
          </div>
        )}
      </div>

      {start && <FirstLessons plan={start} mine={startMine} narrow={narrow} />}
      <Yours c={c} />
      <More c={c} narrow={narrow} />
      <Skills c={c} />
      <MakeYourOwn name={c.name} />
    </div>
  )
}

/** The one action: Start (or Continue) the start plan; Get it and I have it while the app isn't on this Mac. */
function Action({ c, state, start, mine }: { c: AppContent; state: InstallState | undefined; start: CatalogPlan; mine?: PlanState }): ReactNode {
  if (state === 'missing') {
    const canGet = !!appMeta(c.id)?.getUrl
    return (
      <div className="flex flex-col" style={{ gap: 8 }} data-app-action="missing">
        {canGet && <PrimaryButton label={`Get ${c.name}`} icon={ArrowUpRight} onClick={() => getApp(c.id)} size="lg" block />}
        <QuietButton label="I have it" icon={Check} onClick={() => markHave(c.id)} block />
        <span style={meta}>Its lessons wait here until you have it.</span>
      </div>
    )
  }
  const going = !!mine && mine.nextIndex !== null && (mine.done > 0 || mine.lessons.some((l) => l.state === 'in_progress'))
  return (
    <div className="flex flex-col" style={{ gap: 8 }} data-app-action="start">
      <PrimaryButton label={actionLabel(going, start.title)} title={`${going ? 'Continue' : 'Start'} ${start.title}`} icon={Play} onClick={() => (mine ? startNext(mine) : startPlan(start))} size="lg" block />
      <span style={meta}>
        It opens {c.name} and shows the {going ? 'next' : 'first'} step.
      </span>
    </div>
  )
}

/** "Start Intro to Blender"; a plan name too long for the button says "Start plan" (the title is above it). */
const LABEL_MAX = 22
const actionLabel = (going: boolean, title: string): string => (title.length > LABEL_MAX ? `${going ? 'Continue' : 'Start'} plan` : `${going ? 'Continue' : 'Start'} ${title}`)

function FirstLessons({ plan, mine, narrow }: { plan: CatalogPlan; mine?: PlanState; narrow: boolean }): ReactNode {
  const template = narrow ? '28px minmax(0,1fr) 56px' : '28px minmax(0,1.15fr) minmax(0,2.1fr) minmax(0,0.95fr) 44px 56px'
  const cols = narrow
    ? [{ label: '' }, { label: 'Lesson' }, { label: 'Time', align: 'right' as const }]
    : [{ label: '' }, { label: 'Lesson' }, { label: 'Passes when' }, { label: 'Grows' }, { label: 'Steps', align: 'right' as const }, { label: 'Time', align: 'right' as const }]
  return (
    <section data-app-lessons aria-label={plan.title}>
      <SectionLabel count={plan.lessons.length} right={<MoreLink onClick={() => showPlan(plan.id)}>The whole plan</MoreLink>}>
        {plan.title}
      </SectionLabel>
      <div role="table" aria-label={`${plan.title} lessons`}>
        <TableHead cols={cols} template={template} />
        {plan.lessons.slice(0, FIRST_LESSONS).map((l, i) => {
          const passed = mine?.lessons[i]?.state === 'done'
          return (
            <TableRow key={l.title} template={template} label={`${l.title}, open the plan`} onClick={() => showPlan(plan.id)} data={{ 'data-app-lesson': String(i + 1) }}>
              <span style={{ ...meta, display: 'flex' }}>
                {passed ? (
                  <span aria-label="Passed" className="flex items-center justify-center" style={{ width: 16, height: 16, borderRadius: radius2.round, background: color.green, color: color.onGreen }}>
                    <Check size={11} strokeWidth={3} />
                  </span>
                ) : (
                  i + 1
                )}
              </span>
              <span style={{ fontWeight: 600, lineHeight: '20px' }}>{l.title}</span>
              {!narrow && <span style={{ ...meta, fontSize: type2.md, lineHeight: '20px' }}>{l.passes}</span>}
              {!narrow && (
                <span className="flex flex-wrap gap-[4px]">
                  {l.grows
                    .map((g) => skillLabel(g))
                    .filter((g): g is string => !!g)
                    .slice(0, 1)
                    .map((g) => (
                      <SkillChip key={g}>{g}</SkillChip>
                    ))}
                </span>
              )}
              {!narrow && <span style={{ ...meta, textAlign: 'right' }}>{l.steps}</span>}
              <span style={{ ...meta, textAlign: 'right' }}>{l.minutes} min</span>
            </TableRow>
          )
        })}
      </div>
    </section>
  )
}

/** "Step 3 of 5", "Passed", or "Ready". */
function lessonState(i: LibraryItem): string {
  const p = i.progress
  if (p && p.total > 0 && p.stepIndex >= p.total) return 'Passed'
  if (p) return `Step ${p.stepIndex + 1} of ${p.total}`
  return i.ready ? 'Ready' : 'Building'
}

/** The learner's own lessons here, and their plans that aren't in the catalog (from a video or a goal). */
function Yours({ c }: { c: AppContent }): ReactNode {
  const custom = c.mine.filter((m) => !m.catalogId)
  if (!c.lessons.length && !custom.length) return null
  const template = 'minmax(0,1fr) 140px 20px'
  return (
    <section data-app-yours aria-label="Your lessons">
      <SectionLabel count={c.lessons.length + custom.length}>Yours in {c.name}</SectionLabel>
      <div role="table" aria-label={`Yours in ${c.name}`}>
        {custom.map((m) => (
          <TableRow key={m.id} template={template} label={`Open ${m.title}`} onClick={() => showPlan(m.id)} data={{ 'data-app-myplan': m.id }}>
            <span className="truncate" style={{ fontWeight: 600 }}>
              {m.title}
            </span>
            <span style={{ ...meta, textAlign: 'right' }}>
              {m.done} of {m.total}
            </span>
            <ChevronRight aria-hidden size={14} strokeWidth={1.8} style={{ color: color.faint }} />
          </TableRow>
        ))}
        {c.lessons.map((i) => (
          <TableRow key={i.id} template={template} label={`Open ${i.title}`} onClick={() => openDetail(i.id)} data={{ 'data-app-mylesson': i.id }}>
            <span className="truncate" style={{ fontWeight: 600 }}>
              {i.title}
            </span>
            <span style={{ ...meta, textAlign: 'right' }}>{lessonState(i)}</span>
            <ChevronRight aria-hidden size={14} strokeWidth={1.8} style={{ color: color.faint }} />
          </TableRow>
        ))}
      </div>
    </section>
  )
}

function More({ c, narrow }: { c: AppContent; narrow: boolean }): ReactNode {
  const rest = c.plans.slice(1)
  if (!rest.length) return null
  const shown = rest.slice(0, MORE_MAX)
  const template = narrow ? 'minmax(0,1fr) 64px 56px' : 'minmax(0,1.3fr) 64px 52px 56px minmax(0,1.6fr) minmax(0,1fr)'
  const cols = narrow
    ? [{ label: 'Plan' }, { label: 'Lessons', align: 'right' as const }, { label: 'Time', align: 'right' as const }]
    : [{ label: 'Plan' }, { label: 'Lessons', align: 'right' as const }, { label: 'Skills', align: 'right' as const }, { label: 'Time', align: 'right' as const }, { label: 'Ends with' }, { label: 'After' }]
  return (
    <section data-app-more aria-label={`More in ${c.name}`}>
      <SectionLabel count={rest.length} right={rest.length > MORE_MAX ? <MoreLink onClick={showPlans}>Browse plans</MoreLink> : undefined}>
        More in {c.name}
      </SectionLabel>
      <div role="table" aria-label={`More in ${c.name}`}>
        <TableHead cols={cols} template={template} />
        {shown.map((p) => (
          <TableRow key={p.id} template={template} label={`Open ${p.title}`} onClick={() => showPlan(p.id)} data={{ 'data-app-plan': p.id }}>
            <span className="truncate" style={{ fontWeight: 600 }}>
              {p.title}
            </span>
            <span style={{ ...meta, textAlign: 'right' }}>{p.lessons.length}</span>
            {!narrow && <span style={{ ...meta, textAlign: 'right' }}>{p.skills.length}</span>}
            <span style={{ ...meta, textAlign: 'right' }}>{hoursShort(planMinutes(p))}</span>
            {!narrow && (
              <span className="truncate" style={{ ...meta, fontSize: type2.md }}>
                {p.project.title}
              </span>
            )}
            {!narrow && (
              <span className="truncate" style={{ ...meta, fontSize: type2.md }}>
                {afterTitles(p)}
              </span>
            )}
          </TableRow>
        ))}
      </div>
    </section>
  )
}

function Skills({ c }: { c: AppContent }): ReactNode {
  if (!c.skills.length) return null
  return (
    <section data-app-skills aria-label={`Skills in ${c.name}`}>
      <SectionLabel count={c.skills.length} right={<MoreLink onClick={() => setPage('skills')}>Skills</MoreLink>}>
        Skills in {c.name}
      </SectionLabel>
      <div className="flex flex-wrap gap-[6px]">
        {c.skills.slice(0, SKILLS_MAX).map((s) => (
          <SkillChip key={s.id}>{s.label}</SkillChip>
        ))}
        {c.skills.length > SKILLS_MAX && <span style={{ ...meta, alignSelf: 'center' }}>and {c.skills.length - SKILLS_MAX} more</span>}
      </div>
    </section>
  )
}

function MakeYourOwn({ name }: { name: string }): ReactNode {
  const card = (icon: ReactNode, title: string, line: string, onClick: () => void, key: string): ReactNode => (
    <button
      key={key}
      type="button"
      data-app-make={key}
      onClick={onClick}
      className="mg-lift flex min-w-[240px] flex-1 cursor-pointer items-center gap-[12px] text-left"
      style={{ height: 60, padding: '0 16px', borderRadius: radius2.card, background: surface.row, border: 0, boxShadow: `inset 0 0 0 1px ${surface.border}`, color: color.text }}
    >
      <span className="shrink-0" style={{ color: color.label }}>
        {icon}
      </span>
      <span className="flex min-w-0 flex-1 flex-col">
        <span className="truncate" style={{ fontSize: type2.md, fontWeight: 600 }}>
          {title}
        </span>
        <span className="truncate" style={meta}>
          {line}
        </span>
      </span>
      <ChevronRight size={15} strokeWidth={1.8} style={{ color: color.faint }} />
    </button>
  )
  return (
    <section data-app-make-own aria-label={`Make your own in ${name}`}>
      <SectionLabel>Make your own in {name}</SectionLabel>
      <div className="flex flex-wrap gap-[12px]">
        {card(<SquarePlay size={17} strokeWidth={1.7} />, 'From a video', `Paste any ${name} tutorial from YouTube`, () => openDialog('playlist'), 'video')}
        {card(<Sprout size={17} strokeWidth={1.7} />, 'From a goal', `Say what you want to make in ${name}`, () => openDialog('goal'), 'goal')}
      </div>
    </section>
  )
}

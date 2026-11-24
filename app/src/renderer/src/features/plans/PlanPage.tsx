/**
 * Feature: plans. One plan (Adrian's mock `plan`): the title and line, five facts (works in, length, ends with,
 * checked by, grows), the picture with the one primary action, the lessons as a full-width table, and under it two
 * blocks side by side: the project, and "Rather follow a video" with "After this plan". Trim pass (Nov 24): one note
 * under the project, no "Added" date, no repeated video count.
 *
 * A plan the learner made (from a playlist or a goal) uses the same page with the lessons it carries.
 */
import { Check, Circle, Eye, Flag, GitFork, List, Play, SquarePlay, SquareTerminal, ChevronRight } from 'lucide-react'
import type { ReactNode } from 'react'
import { PrimaryButton } from '../../core/ui/buttons'
import { color, radius2, type2 } from '../../core/theme'
import { aboutHours, checkedBy, nextPlans, planById, planMinutes, playlistsFor, skillLabel, type Plan, type PlanLesson } from './catalog'
import { addPlan, showLibrary, showPlan, showPlans, startPlan, usePlans, type MyPlan } from './store'
import { artFor, artForId, Thumb } from './Thumb'
import { Crumbs, hair, meta, SectionLabel, SkillChip, TableHead, TableRow, useWidth } from './ui'

type Page = { id: string; title: string; line?: string; tool?: string; lessons: PlanLesson[]; ends?: string; checked?: string; skills: string[]; art: ReturnType<typeof artFor>; plan?: Plan }

function fromPlan(p: Plan): Page {
  return { id: p.id, title: p.title, line: p.line, tool: [p.tool.label, ...p.also].join(' · '), lessons: p.lessons, ends: p.project.title, checked: checkedBy(p), skills: p.skills.map((s) => s.label), art: artFor(p), plan: p }
}
function fromMine(m: MyPlan): Page {
  const lessons = m.lessons ?? []
  const skills = [...new Set(lessons.flatMap((l) => l.grows.map((g) => skillLabel(g) ?? g)))]
  return { id: m.id, title: m.title, lessons, ends: m.project, skills, art: artForId(m.art) }
}

export function PlanPage({ id }: { id: string }): ReactNode {
  const mine = usePlans((s) => s.mine.find((m) => m.id === id))
  const plan = planById(id)
  const page = plan ? fromPlan(plan) : mine ? fromMine(mine) : undefined
  const [ref, w] = useWidth<HTMLDivElement>()
  if (!page) {
    return (
      <div className="flex flex-col" style={{ gap: 16 }}>
        <Crumbs items={[{ label: 'Library', onClick: showLibrary }, { label: 'Browse plans', onClick: showPlans }]} />
        <p style={meta}>That plan isn’t here any more.</p>
      </div>
    )
  }
  const narrow = w < 760
  const done = mine?.done ?? 0
  const minutes = page.lessons.reduce((n, l) => n + l.minutes, 0)
  const start = (): void => {
    if (plan) startPlan(plan)
    else if (mine) addPlan(mine)
  }
  const action = mine ? (done > 0 ? `Continue lesson ${done + 1}` : 'Start plan') : 'Start plan'

  const facts: Array<[ReactNode, string, ReactNode]> = [
    ...(page.tool ? [[<SquareTerminal key="i" size={15} strokeWidth={1.6} />, 'Works in', page.tool] as [ReactNode, string, ReactNode]] : []),
    [<List key="i" size={15} strokeWidth={1.6} />, 'Length', `${page.lessons.length} lessons · ${aboutHours(minutes)}`],
    ...(page.ends ? [[<Flag key="i" size={15} strokeWidth={1.6} />, 'Ends with', page.ends] as [ReactNode, string, ReactNode]] : []),
    ...(page.checked ? [[<Eye key="i" size={15} strokeWidth={1.6} />, 'Checked by', page.checked] as [ReactNode, string, ReactNode]] : []),
    [
      <GitFork key="i" size={15} strokeWidth={1.6} />,
      'Grows',
      <span key="g" className="flex flex-wrap gap-[6px]">
        {page.skills.map((s) => (
          <SkillChip key={s}>{s}</SkillChip>
        ))}
      </span>
    ]
  ]

  return (
    <div ref={ref} data-plan-page={page.id} className="flex flex-col" style={{ gap: 32 }}>
      <Crumbs items={[{ label: 'Library', onClick: showLibrary }, { label: 'Browse plans', onClick: showPlans }, { label: page.title }]} />
      <div className={narrow ? 'flex flex-col-reverse' : 'flex items-start'} style={{ gap: narrow ? 20 : 40 }}>
        <div className="flex min-w-0 flex-1 flex-col" style={{ gap: 20 }}>
          <div className="flex flex-col" style={{ gap: 6 }}>
            <h1 className="m-0" style={{ fontSize: 30, lineHeight: '36px', fontWeight: 700, letterSpacing: '-0.6px', color: color.text }}>
              {page.title}
            </h1>
            {page.line && <p className="m-0" style={{ fontSize: type2.body, color: color.label }}>{page.line}</p>}
          </div>
          <dl className="m-0 grid" style={{ gridTemplateColumns: '148px minmax(0,1fr)', rowGap: 12, alignItems: 'start' }}>
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
        <div className="flex shrink-0 flex-col" style={{ width: narrow ? '100%' : 300, gap: 12 }}>
          <Thumb art={page.art} w="100%" radius={radius2.card} />
          <PrimaryButton label={action} icon={Play} onClick={start} size="lg" block />
        </div>
      </div>

      <section>
        <SectionLabel count={page.lessons.length} right={<span style={meta}>{aboutHours(minutes)}</span>}>
          Lessons
        </SectionLabel>
        <LessonTable lessons={page.lessons} done={done} narrow={narrow} />
      </section>

      <div className={narrow ? 'flex flex-col' : 'grid'} style={{ gridTemplateColumns: '1fr 1fr', columnGap: 48, rowGap: 32 }}>
        {plan ? <Project plan={plan} /> : <div />}
        <div className="flex flex-col" style={{ gap: 28 }}>
          {plan && <Videos plan={plan} />}
          {plan && <After plan={plan} />}
        </div>
      </div>
    </div>
  )
}

function LessonTable({ lessons, done, narrow }: { lessons: PlanLesson[]; done: number; narrow: boolean }): ReactNode {
  const template = narrow ? '28px minmax(0,1fr) 56px' : '28px minmax(0,1.15fr) minmax(0,2.3fr) minmax(0,0.95fr) 44px 56px'
  const cols = narrow
    ? [{ label: '' }, { label: 'Lesson' }, { label: 'Time', align: 'right' as const }]
    : [{ label: '' }, { label: 'Lesson' }, { label: 'Passes when' }, { label: 'Grows' }, { label: 'Steps', align: 'right' as const }, { label: 'Time', align: 'right' as const }]
  return (
    <div role="table" aria-label="Lessons">
      <TableHead cols={cols} template={template} />
      {lessons.map((l, i) => {
        const passed = i < done
        return (
          <TableRow key={`${i}-${l.title}`} template={template} label={l.title} height={52} data={{ 'data-plan-lesson': String(i + 1) }}>
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
                {l.grows.map((g) => (
                  <SkillChip key={g}>{skillLabel(g) ?? g}</SkillChip>
                ))}
              </span>
            )}
            {!narrow && <span style={{ ...meta, textAlign: 'right' }}>{l.steps}</span>}
            <span style={{ ...meta, textAlign: 'right' }}>{l.minutes} min</span>
          </TableRow>
        )
      })}
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

function Project({ plan }: { plan: Plan }): ReactNode {
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

/** The plan's playlists: picking one makes a plan from it (the playlist dialog's result, straight away). */
function Videos({ plan }: { plan: Plan }): ReactNode {
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
          onClick={() =>
            addPlan(
              {
                id: `playlist:${l.playlistId}`,
                title: l.title,
                total: l.videos.length,
                minutesLeft: Math.round(l.totalSeconds / 60),
                art: plan.id,
                source: 'playlist',
                lessons: l.videos.map((v, i) => ({ ...(plan.lessons[i] ?? plan.lessons[plan.lessons.length - 1]), title: v.title, minutes: Math.round(v.seconds / 60), goal: `Teach me along with the video "${v.title}" by ${l.channel}.` }))
              },
              false
            )
          }
        />
      ))}
    </section>
  )
}

function After({ plan }: { plan: Plan }): ReactNode {
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

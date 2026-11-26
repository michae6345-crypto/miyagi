/**
 * Feature: library. Home, the home window's first page: v4 (Adrian's ui-next mock, Nov 23-24, after the trim pass).
 * The page itself is in home/ (Page.tsx draws it, data.ts is its model, Top.tsx the ask and the Continue card); this file
 * keeps the Continue logic it shares with the rest of the library (which lesson, which one primary action).
 *
 *   returning learner  ask · Continue · Plans · Up next · Recently passed, and a rail with the week, the goal, skills
 *                      and keep fresh when any of them has something to show (else one centered column)
 *   first run          the one thing left to set up · ask · Start here (the featured lesson, one Start lesson) · a few
 *                      short lessons that start on a click · how a lesson works
 *
 * No greeting and no date (Michael, Nov 21: simpler home, no greeting, no numbers).
 *
 * Continue comes from dashboard/continue.ts, the same list Lessons and Progress read. When setup is left, its button is
 * the one setup action instead ("Turn on Accessibility"), never a disabled Continue.
 */
import { ArrowRight, CloudOff, Play } from 'lucide-react'
import type { ReactNode } from 'react'
import { useShallow } from 'zustand/react/shallow'
import type { LibraryItem, PlanState } from '../../../../../../shared/contracts/events'
import { useLesson, useProgress as useLessonProgress } from '../../core/lesson'
import { closeWindow, openOnboarding } from '../../core/surfaces'
import { color, copy } from '../../core/theme'
import { PrimaryButton } from '../../core/ui/buttons'
import { continueList } from '../dashboard/continue'
import { useDashView } from '../dashboard/Dashboard'
import { useDash } from '../dashboard/store'
import type { DashData } from '../dashboard/types'
import { summarize, useRows } from '../onboarding/rows'
import { FEATURED } from './home/catalog'
import { buildHome, coverFor, coverForTool, firstLessons, fromContract, isFirstRun, type CoverKind } from './home/data'
import { FirstRunPage, HomePage, SetupNote } from './home/Page'
import { LearnIn } from '../apps/LearnIn'
import { FIRST_RUN, sampleHome, stageSample } from './home/sample'
import { Ask, ContinueCard, pickIdeas, type ContView } from './home/Top'
import { useAskV4, useV4 } from './home/v4'
import { useSkillGraph } from '../skills/store'
import { finishedIds, pickHero, setupFix, teach, useAsk, type Hero } from './homeModel'
import { Ring } from './motion'
import { start, useLibrary } from './store'

// ---- the continue model -------------------------------------------------------------------------------------------

function useHero(data: DashData | undefined, dashLoading: boolean, items: LibraryItem[]): Hero {
  const lib = useLibrary(useShallow((s) => ({ loaded: s.loaded, canStart: s.caps.start || !s.capsKnown })))
  const lesson = useLesson(useShallow((s) => ({ title: s.lesson?.title, stepTitle: s.stepTitle, building: s.building, msg: s.buildingMessage, bp: s.buildingProgress, src: s.build?.source?.title })))
  const p = useLessonProgress()
  return pickHero({
    loaded: lib.loaded || items.length > 0,
    dashLoading,
    items,
    data,
    cont: continueList(data, items),
    canStart: lib.canStart,
    live: lesson.title && !lesson.building ? { title: lesson.title, stepTitle: lesson.stepTitle, index: p.index, total: p.total, fraction: p.fraction } : undefined,
    building: lesson.building ? { title: lesson.src ?? lesson.title, message: lesson.msg, progress: lesson.bp } : undefined
  })
}

type Fix = { label: string; line: string }

/** "Step 4 of 7 · Train it" → the count for the kicker and the step's own title for the line under the title. */
function splitLine(line: string): { count?: string; sub: string } {
  const m = /^(Step \d+ of \d+)(?: · (.+))?$/.exec(line)
  return m ? { count: m[1], sub: m[2] ?? '' } : { sub: line }
}

/** A lesson's cover from its tool: a saved lesson's tools, else the plan it belongs to (the live lesson by its title). */
function lessonCover(title: string | undefined, tools: readonly string[], plans: PlanState[] | undefined): CoverKind {
  if (tools.length) return coverFor(tools)
  const plan = title ? plans?.find((p) => p.lessons.some((l) => l.title === title)) : undefined
  return coverForTool(plan?.tool?.id)
}

/** What the Continue card says, or null when there is nothing to continue and nothing to fix. */
function contView(hero: Hero, fix: Fix | undefined, connected: boolean, items: LibraryItem[], plans?: PlanState[]): ContView | null {
  if (hero.kind === 'loading') return null
  const startable = hero.kind === 'resume' || hero.kind === 'fresh'
  const blocked = !!fix && connected && (startable || hero.kind === 'empty')
  if (hero.kind === 'empty') return blocked ? { kicker: 'Setup', title: 'Almost ready', sub: fix!.line, cover: 'code' } : null
  const tools = startable ? hero.tools : items.find((i) => i.title === hero.title)?.tools ?? []
  // The demo sample's lesson is the only 'net' (Home below); every real lesson is drawn from its tool.
  const cover = lessonCover(hero.title, tools, plans)
  const { count, sub } = splitLine(hero.line)
  const title = hero.title ?? 'Your next lesson'
  if (hero.kind === 'building') return { kicker: 'Building', title, sub: hero.line, fraction: hero.fraction, cover, building: true }
  if (hero.kind === 'fresh') return { kicker: 'Start', title, sub: blocked ? fix!.line : hero.line, cover }
  return { kicker: count ?? (hero.kind === 'live' ? 'In a lesson' : 'Continue'), title, sub: blocked ? fix!.line : sub, fraction: hero.fraction, cover }
}

/** The one primary action for the Continue card, and its quiet notes. */
function ContAction({ hero, fix }: { hero: Hero; fix?: Fix }): ReactNode {
  const libStarting = useLibrary((s) => s.starting)
  const dashStarting = useDash((s) => s.starting)
  const starting = libStarting ?? dashStarting
  const err = useLibrary((s) => s.startError)
  const connected = useLesson((s) => s.connected)
  const startable = hero.kind === 'resume' || hero.kind === 'fresh'
  const id = startable ? hero.id : undefined
  const busy = !!id && starting === id
  const blocked = !!fix && connected && (startable || hero.kind === 'empty')
  const note = { fontSize: 12.5, color: color.label } as const
  return (
    <>
      {blocked && (
        <Ring>
          <PrimaryButton label={fix!.label} onClick={() => void openOnboarding()} />
        </Ring>
      )}
      {!blocked && startable && (
        <Ring>
          <PrimaryButton
            label={hero.kind === 'resume' ? 'Continue' : 'Start lesson'}
            icon={Play}
            busy={busy}
            disabled={!hero.canStart || (!!starting && !busy)}
            title={hero.canStart ? undefined : 'This engine can’t start saved lessons yet.'}
            onClick={() => void start(hero.id)}
          />
        </Ring>
      )}
      {hero.kind === 'live' && (
        <Ring>
          <PrimaryButton label="Back to the lesson" icon={ArrowRight} onClick={() => void closeWindow('library')} />
        </Ring>
      )}
      {!blocked && startable && !connected && (
        <span role="status" style={note}>
          miyagi is offline.
        </span>
      )}
      {err && err.id === id && (
        <span role="status" style={{ ...note, color: color.text }}>
          {err.text}
        </span>
      )}
    </>
  )
}

/** The first-run card's one primary: start the featured lesson (learn {goal, mode: lesson}, as the ask field sends it). */
function FeaturedAction(): ReactNode {
  const connected = useLesson((s) => s.connected)
  const sending = useAsk((s) => s.sending)
  return (
    <>
      <Ring>
        <PrimaryButton label="Start lesson" icon={Play} busy={sending === 'lesson'} disabled={!!sending} onClick={() => void teach(FEATURED.goal, connected)} />
      </Ring>
      {!connected && (
        <span role="status" style={{ fontSize: 12.5, color: color.label }}>
          miyagi is offline.
        </span>
      )}
    </>
  )
}

const featuredView: ContView = { kicker: 'Start here', title: FEATURED.title, sub: `${FEATURED.tool} · ${FEATURED.steps} steps · ${FEATURED.minutes} min`, cover: FEATURED.cover }

// ---- the page -----------------------------------------------------------------------------------------------------

export function Home(): ReactNode {
  const dash = useDashView()
  const sample = stageSample()
  const now = dash.now
  const demo = sample === 'full' ? sampleHome(now) : undefined
  const data = sample === 'first' ? undefined : (demo?.data ?? dash.data)
  const libItems = useLibrary((s) => s.items)
  const items = sample === 'first' ? [] : (demo?.items ?? libItems)
  // The ui-v4 contract: activity (the week, Recently passed) and plans (Plans, Up next, the goal), asked for on open.
  useAskV4()
  const v4 = useV4()
  const graph = useSkillGraph(now)
  const names = new Map((data?.tracks ?? []).flatMap((t) => t.skills.map((s) => [s.id, s.label.split(String.fromCharCode(96)).join('')] as const)))
  const extra = demo?.extra ?? (sample === 'first' ? {} : fromContract({ activity: v4.activity, plans: v4.plans, names }))
  const hero = useHero(data, dash.load === 'loading' && !sample, items)
  const connected = useLesson((s) => s.connected)
  const rows = useRows()
  const fix = summarize(rows).canStart || sample ? undefined : setupFix(rows)
  const offline = !connected && !data && dash.load !== 'loading' && !sample
  const conts = continueList(data, items)
  const skip = new Set(conts.map((c) => c.libraryId))
  if (!demo && (hero.kind === 'resume' || hero.kind === 'fresh')) skip.add(hero.id)
  const view = demo ? { kicker: 'Step 4 of 7', title: demo.cont.title, sub: 'Train it', fraction: demo.cont.done / demo.cont.total, cover: 'net' as const } : contView(hero, fix, connected, items, v4.plans)
  const action = demo ? (
    <Ring>
      <PrimaryButton label="Continue" icon={Play} onClick={() => undefined} />
    </Ring>
  ) : (
    <ContAction hero={hero} fix={fix} />
  )
  const ask = <Ask ideas={pickIdeas(data)} />
  const notice = offline ? (
    <p role="status" data-home-offline className="m-0 flex items-center gap-[8px]" style={{ fontSize: 12.5, color: color.label, paddingBottom: 12 }}>
      <CloudOff aria-hidden size={14} strokeWidth={1.8} />
      {copy.name} is offline. Your lessons show when it connects.
    </p>
  ) : undefined
  // First run from the learner's record alone: a saved lesson ready to start, or a step of setup left, no longer hides it.
  // A lesson open or building right now always gets its card (the returning page).
  const busy = hero.kind === 'live' || hero.kind === 'building'
  const first = sample === 'first' || (!demo && !busy && dash.load !== 'loading' && isFirstRun(data, items, extra))
  if (first) {
    const lessons = firstLessons(sample ? [] : items, finishedIds(data), FIRST_RUN.shortLessons)
    return (
      <FirstRunPage
        ask={ask}
        notice={notice}
        setup={fix && connected ? <SetupNote label={fix.label} line={fix.line} /> : undefined}
        featured={<ContinueCard view={featuredView} action={<FeaturedAction />} />}
        lessons={lessons}
        onLesson={(r) => void (r.saved ? start(r.id) : teach(r.goal, connected))}
      />
    )
  }
  const m = buildHome({ data, items, extra, now, skip, done: finishedIds(data), plans: demo ? undefined : v4.plans })
  // Keep fresh: the progress's review list, else the skill graph's keepFresh (progress.graph, read-only).
  if (!demo && !m.fresh.length && graph?.keepFresh.length)
    m.fresh = graph.keepFresh.flatMap((id) => {
      const n = graph.byId[id]
      return n ? [{ label: n.label, at: n.lastPracticedAt ?? n.masteredAt }] : []
    })
  return <HomePage m={m} now={now} ask={ask} cont={view ? <ContinueCard view={view} action={action} /> : null} notice={notice} apps={(first) => <LearnIn first={first} />} />
}

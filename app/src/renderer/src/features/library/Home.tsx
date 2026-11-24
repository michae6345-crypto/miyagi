/**
 * Feature: library. Home, the home window's first page: v4 (Adrian's ui-next mock, Nov 23-24, after the trim pass).
 * The page itself is in home/ (Page.tsx draws it, data.ts is its model, Top.tsx the ask and the Continue card); this file
 * keeps the Continue logic it shares with the rest of the library (which lesson, which one primary action).
 *
 *   returning learner  greeting · ask · Continue · Plans · Up next · Recently passed, and a rail with the week, the
 *                      goal, skills and keep fresh
 *   first run          welcome · ask · three plans to start · short lessons · make your own, and a rail with setup,
 *                      how a lesson works and goals to pick
 *
 * Continue comes from dashboard/continue.ts, the same list Lessons and Progress read. When setup is left, its button is
 * the one setup action instead ("Turn on Accessibility"), never a disabled Continue.
 */
import { ArrowRight, CloudOff, Play } from 'lucide-react'
import type { ReactNode } from 'react'
import { useShallow } from 'zustand/react/shallow'
import type { LibraryItem } from '../../../../../../shared/contracts/events'
import { useLesson, useProgress as useLessonProgress } from '../../core/lesson'
import { closeWindow, openOnboarding } from '../../core/surfaces'
import { color, copy } from '../../core/theme'
import { PrimaryButton } from '../../core/ui/buttons'
import { v2Cloud } from '../account/model'
import { useAccount } from '../account/store'
import { authOn } from '../auth/model'
import { useAuth } from '../auth/store'
import { continueList } from '../dashboard/continue'
import { useDashView } from '../dashboard/Dashboard'
import { useDash } from '../dashboard/store'
import type { DashData } from '../dashboard/types'
import { summarize, useRows } from '../onboarding/rows'
import { buildHome, coverFor, greeting, isFirstRun, type V4Extra } from './home/data'
import { FirstRunPage, HomePage } from './home/Page'
import { FIRST_RUN, sampleHome, stageSample } from './home/sample'
import { Ask, ContinueCard, pickIdeas, type ContView } from './home/Top'
import { finishedIds, pickHero, setupFix, type Hero } from './homeModel'
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

/** What the Continue card says, or null when there is nothing to continue and nothing to fix. */
function contView(hero: Hero, fix: Fix | undefined, connected: boolean, items: LibraryItem[]): ContView | null {
  if (hero.kind === 'loading') return null
  const startable = hero.kind === 'resume' || hero.kind === 'fresh'
  const blocked = !!fix && connected && (startable || hero.kind === 'empty')
  if (hero.kind === 'empty') return blocked ? { kicker: 'Setup', title: 'Almost ready', sub: fix!.line, cover: 'code' } : null
  const tools = startable ? hero.tools : items.find((i) => i.title === hero.title)?.tools ?? []
  const cover = hero.kind === 'live' ? 'net' : coverFor(tools)
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

// ---- the page -----------------------------------------------------------------------------------------------------

export function Home(): ReactNode {
  const dash = useDashView()
  const sample = stageSample()
  const now = dash.now
  const demo = sample === 'full' ? sampleHome(now) : undefined
  const data = sample === 'first' ? undefined : (demo?.data ?? dash.data)
  const libItems = useLibrary((s) => s.items)
  const items = sample === 'first' ? [] : (demo?.items ?? libItems)
  // Wire later: the contract's activity minutes, plans, step passes and goal (home/data.ts V4Extra).
  const extra: V4Extra = demo?.extra ?? {}
  const hero = useHero(data, dash.load === 'loading' && !sample, items)
  const connected = useLesson((s) => s.connected)
  // The learner's name, from wherever the sidebar reads it (the cloud account, else the sign-in); none = no name.
  const accountName = useAccount((s) => (s.account?.signedIn ? s.account.name : undefined))
  const authName = useAuth((s) => s.user?.name)
  const name = v2Cloud ? accountName : authOn ? authName : undefined
  const rows = useRows()
  const fix = summarize(rows).canStart || sample ? undefined : setupFix(rows)
  const offline = !connected && !data && dash.load !== 'loading' && !sample
  const conts = continueList(data, items)
  const skip = new Set(conts.map((c) => c.libraryId))
  if (!demo && (hero.kind === 'resume' || hero.kind === 'fresh')) skip.add(hero.id)
  const view = demo ? { kicker: 'Step 4 of 7', title: demo.cont.title, sub: 'Train it', fraction: demo.cont.done / demo.cont.total, cover: 'net' as const } : contView(hero, fix, connected, items)
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
  const first = sample === 'first' || (!demo && dash.load !== 'loading' && isFirstRun(data, items, extra) && !view)
  if (first) return <FirstRunPage now={now} greeting={name ? `Welcome, ${name.trim().split(/\s+/)[0]}` : 'Welcome'} ask={ask} setup={rows} notice={notice} starters={FIRST_RUN.starters} lessons={FIRST_RUN.shortLessons} goals={FIRST_RUN.goals} />
  const m = buildHome({ data, items, extra, now, skip, done: finishedIds(data) })
  return <HomePage m={m} now={now} greeting={greeting(now, name)} ask={ask} cont={view ? <ContinueCard view={view} action={action} /> : null} notice={notice} />
}

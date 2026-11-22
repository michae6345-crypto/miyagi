/**
 * Feature: library. Home, the home window's first page. One calm column on one layered surface, grouped by spacing and
 * quiet headers (no grid of bordered cards, no greeting, no date, no stat boxes):
 *
 *   continue  the ONE most recent unfinished lesson: title, "Step N of M · step title", one primary button. When setup
 *             is left that button is the one setup action instead ("Turn on Accessibility"), never a disabled Continue.
 *   ask       "ask miyagi anything" with three suggestion chips (a goal or a pasted YouTube link, homeModel.ts)
 *   ready     a short list of lessons saved on this Mac, with soft pastel tool tags
 *   recent    one row per lesson, newest state, a green check when finished and a hueless ring while in progress
 *
 * Continue comes from dashboard/continue.ts, the same list Lessons and Progress read. Parts with nothing to show are
 * left out (no "nothing yet" boxes). The window's content is capped at 720 px so a big window stays calm.
 */
import { motion } from 'motion/react'
import { ArrowRight, ChevronRight, CloudOff, Play } from 'lucide-react'
import { useRef, type ReactNode } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { useLesson, useProgress as useLessonProgress } from '../../core/lesson'
import { closeWindow, openOnboarding } from '../../core/surfaces'
import { color, copy, elevation, fill, highlight, radius2, tone, type Tone, type2 } from '../../core/theme'
import { Spinner } from '../../core/ui/atoms'
import { PrimaryButton, QuietButton } from '../../core/ui/buttons'
import { Keycap } from '../../core/ui/Keycap'
import { MiyagiMark } from '../../core/ui/Mark'
import { StatusGlyph } from '../../core/ui/status'
import { continueList } from '../dashboard/continue'
import { useDashView } from '../dashboard/Dashboard'
import { relDay } from '../dashboard/model'
import { useDash } from '../dashboard/store'
import type { DashData } from '../dashboard/types'
import { summarize, useRows } from '../onboarding/rows'
import { finishedIds, pickHero, readAsk, recentActivity, recentLine, setAskText, setupFix, submitAsk, useAsk, type Hero, type Recent } from './homeModel'
import { Press, Ring, Rise } from './motion'
import { Skeleton, ToolTag, minutesLabel, soft, stepsLabel } from './parts'
import { openDetail, setSection, start, useLibrary } from './store'
import { enter, press } from '../../core/ui/motion'

const caption = { fontSize: type2.xs, lineHeight: '16px', color: color.label } as const

/** A quiet section header: small, medium weight, the label gray. */
function Head({ id, children, right }: { id: string; children: ReactNode; right?: ReactNode }): ReactNode {
  return (
    <div className="flex min-h-[24px] items-center gap-[8px]" style={{ marginBottom: 6 }}>
      <h2 id={id} className="m-0 font-medium" style={{ fontSize: type2.xs, letterSpacing: '0.02em', color: color.label }}>
        {children}
      </h2>
      {right && <div className="ml-auto flex items-center">{right}</div>}
    </div>
  )
}

// ---- continue ---------------------------------------------------------------------------------------------------

function useHero(data: DashData | undefined, dashLoading: boolean): Hero {
  const lib = useLibrary(useShallow((s) => ({ loaded: s.loaded, items: s.items, canStart: s.caps.start || !s.capsKnown })))
  const lesson = useLesson(useShallow((s) => ({ title: s.lesson?.title, stepTitle: s.stepTitle, building: s.building, msg: s.buildingMessage, bp: s.buildingProgress, src: s.build?.source?.title })))
  const p = useLessonProgress()
  return pickHero({
    loaded: lib.loaded,
    dashLoading,
    items: lib.items,
    data,
    cont: continueList(data, lib.items),
    canStart: lib.canStart,
    live: lesson.title && !lesson.building ? { title: lesson.title, stepTitle: lesson.stepTitle, index: p.index, total: p.total, fraction: p.fraction } : undefined,
    building: lesson.building ? { title: lesson.src ?? lesson.title, message: lesson.msg, progress: lesson.bp } : undefined
  })
}

function ContinueBlock({ hero, fix }: { hero: Hero; fix?: { label: string; line: string } }): ReactNode {
  const libStarting = useLibrary((s) => s.starting)
  const dashStarting = useDash((s) => s.starting)
  const starting = libStarting ?? dashStarting
  const err = useLibrary((s) => s.startError)
  const connected = useLesson((s) => s.connected)
  if (hero.kind === 'loading')
    return (
      <div aria-busy aria-label="Loading your lessons" className="flex flex-col gap-[10px]">
        <Skeleton h={14} />
        <Skeleton h={26} />
        <Skeleton h={44} />
      </div>
    )
  const id = hero.kind === 'resume' || hero.kind === 'fresh' ? hero.id : undefined
  const busy = !!id && starting === id
  const startable = hero.kind === 'resume' || hero.kind === 'fresh'
  // Setup left: the one button is the one thing to fix. A lesson that can't start yet never shows a dead button beside it.
  const blocked = !!fix && connected && (startable || hero.kind === 'empty')
  const title = hero.kind === 'empty' ? (fix ? 'Almost ready' : 'What do you want to learn?') : (hero.title ?? 'Your next lesson')
  const line = blocked ? fix.line : hero.kind === 'empty' ? '' : hero.line
  const tools = startable ? hero.tools : []
  if (hero.kind === 'empty' && !blocked) return null
  return (
    <section aria-labelledby="home-continue" data-home-hero={hero.kind} className="flex flex-col">
      <Head id="home-continue-head">{hero.kind === 'live' ? 'In a lesson' : hero.kind === 'building' ? 'Building' : hero.kind === 'fresh' ? 'Start' : 'Continue'}</Head>
      <h1 id="home-continue" className="m-0 line-clamp-2 font-semibold" style={{ fontSize: type2.xxl, lineHeight: '34px', letterSpacing: '-0.02em', color: color.text }}>
        {title}
      </h1>
      <div className="flex flex-wrap items-center gap-x-[10px] gap-y-[6px]" style={{ marginTop: 8, fontSize: type2.sm, color: soft }}>
        {line && <span data-hero-line>{line}</span>}
        {!blocked && tools.map((t) => <ToolTag key={t} tool={t} />)}
      </div>
      <div className="flex flex-wrap items-center gap-[12px]" style={{ marginTop: 20 }}>
        {blocked && (
          <Ring>
            <PrimaryButton label={fix.label} size="lg" onClick={() => void openOnboarding()} />
          </Ring>
        )}
        {!blocked && startable && (
          <Ring>
            <PrimaryButton
              label={hero.kind === 'resume' ? 'Continue' : 'Start lesson'}
              icon={Play}
              size="lg"
              busy={busy}
              disabled={!hero.canStart || (!!starting && !busy)}
              title={hero.canStart ? undefined : 'This engine can’t start saved lessons yet.'}
              onClick={() => void start(hero.id)}
            />
          </Ring>
        )}
        {hero.kind === 'live' && (
          <Ring>
            <PrimaryButton label="Back to the lesson" icon={ArrowRight} size="lg" onClick={() => void closeWindow('library')} />
          </Ring>
        )}
        {hero.kind === 'building' && (
          <span className="flex items-center gap-[8px]" style={caption}>
            <Spinner size={14} c={color.text} />
            The island shows each step.
          </span>
        )}
        {!blocked && startable && !connected && (
          <span role="status" style={caption}>
            miyagi is offline.
          </span>
        )}
        {err && err.id === id && (
          <span role="status" style={{ ...caption, color: color.text }}>
            {err.text}
          </span>
        )}
      </div>
    </section>
  )
}

// ---- ask --------------------------------------------------------------------------------------------------------

const IDEAS: Array<{ text: string; tone: Tone }> = [
  { text: 'Clean a messy CSV with pandas', tone: 'sky' },
  { text: 'Build a tiny web server', tone: 'lilac' },
  { text: 'Train an image classifier', tone: 'pink' }
]

function AskBlock({ primary }: { primary: boolean }): ReactNode {
  const ask = useAsk()
  const items = useLibrary((s) => s.items)
  const canStart = useLibrary((s) => s.caps.start)
  const connected = useLesson((s) => s.connected)
  const input = useRef<HTMLInputElement>(null)
  const read = readAsk(ask.text, items, canStart)
  const go = (): void => {
    if (!submitAsk(connected) && !useAsk.getState().sending) input.current?.focus()
  }
  const Btn = primary ? PrimaryButton : QuietButton
  const actionLabel = read.kind === 'link' ? (read.match ? 'Start lesson' : 'Build lesson') : 'Teach me'
  return (
    <section aria-labelledby="home-ask" data-home-ask className="flex flex-col">
      <Head id="home-ask">Learn something new</Head>
      <form
        className="flex items-center gap-[10px]"
        style={{ height: 52, padding: '0 8px 0 16px', borderRadius: radius2.card, background: fill.field, boxShadow: `inset 0 0 0 1px ${fill.fieldBorder}, ${highlight.well}` }}
        onSubmit={(e) => {
          e.preventDefault()
          go()
        }}
      >
        <MiyagiMark size={16} />
        <input
          ref={input}
          aria-label={copy.launcherPlaceholder}
          placeholder={copy.launcherPlaceholder}
          autoComplete="off"
          spellCheck={false}
          value={ask.text}
          disabled={!!ask.sending}
          onChange={(e) => setAskText(e.target.value)}
          className="min-w-0 flex-1 bg-transparent outline-none"
          style={{ fontSize: type2.body, color: color.text }}
        />
        {read.kind === 'idle' ? (
          <span className="flex shrink-0 items-center gap-[6px]" style={{ fontSize: type2.micro, color: color.faint }}>
            anywhere
            <Keycap k="launcher" size="sm" />
          </span>
        ) : (
          <motion.button
            type="submit"
            tabIndex={-1}
            aria-hidden
            title={actionLabel}
            disabled={!!ask.sending}
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            whileTap={{ scale: press.scale }}
            transition={enter()}
            className="flex shrink-0 cursor-pointer items-center justify-center"
            style={{ width: 34, height: 34, borderRadius: radius2.row, background: fill.chip, color: color.text }}
          >
            {ask.sending ? <Spinner size={13} c={color.text} /> : <ArrowRight size={15} strokeWidth={2} aria-hidden />}
          </motion.button>
        )}
      </form>
      <div className="flex flex-wrap items-center gap-[8px]" style={{ marginTop: 12, minHeight: 36 }}>
        {read.kind === 'idle' ? (
          IDEAS.map((t) => (
            <Press
              key={t.text}
              data-idea
              onClick={() => {
                setAskText(t.text)
                input.current?.focus()
              }}
              className="flex items-center"
              style={{ height: 30, padding: '0 12px', borderRadius: radius2.round, background: tone[t.tone].bg, fontSize: type2.xs, color: tone[t.tone].fg }}
            >
              <span className="relative">{t.text}</span>
            </Press>
          ))
        ) : (
          <>
            <Ring>
              <Btn label={actionLabel} icon={read.kind === 'link' && read.match ? Play : ArrowRight} busy={!!ask.sending} onClick={go} />
            </Ring>
            {read.kind === 'link' && read.match && <span style={caption}>{read.match.title}</span>}
            {ask.note ? (
              <span role="status" style={{ ...caption, color: color.text }}>
                {ask.note}
              </span>
            ) : (
              !connected && <span style={caption}>miyagi is offline.</span>
            )}
          </>
        )}
      </div>
    </section>
  )
}

// ---- ready to run, recent ---------------------------------------------------------------------------------------

function ReadyToRun({ skip, done }: { skip: Set<string>; done: Set<string> }): ReactNode {
  const loaded = useLibrary((s) => s.loaded)
  const items = useLibrary((s) => s.items)
  const fresh = items.filter((i) => i.ready && !i.progress && !skip.has(i.id))
  const ready = [...fresh.filter((i) => !done.has(i.id)), ...fresh.filter((i) => done.has(i.id))]
  if (loaded && !ready.length) return null
  return (
    <section aria-labelledby="home-ready" data-home-ready>
      <Head
        id="home-ready"
        right={
          items.length > 3 ? (
            <Press onClick={() => setSection('library')} className="flex items-center gap-[2px]" style={{ height: 24, padding: '0 6px', borderRadius: radius2.control, fontSize: type2.xs, color: soft }}>
              <span className="relative">See all</span>
              <ChevronRight aria-hidden size={12} strokeWidth={1.8} className="relative" />
            </Press>
          ) : undefined
        }
      >
        Ready to run
      </Head>
      {!loaded ? (
        <div className="flex flex-col gap-[8px]" aria-busy aria-label="Loading lessons">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} h={44} />
          ))}
        </div>
      ) : (
        <ul className="m-0 flex list-none flex-col p-0" style={{ marginInline: -10 }}>
          {ready.slice(0, 3).map((i, n) => (
            <Rise key={i.id} as="li" i={n}>
              <Press
                data-lesson={i.id}
                aria-label={`${i.title}. ${done.has(i.id) ? 'Done. ' : ''}${stepsLabel(i.steps)}. Open its preview.`}
                onClick={() => openDetail(i.id)}
                className="flex w-full items-center gap-[12px]"
                style={{ padding: '10px', borderRadius: radius2.row }}
              >
                <span className="relative flex min-w-0 flex-1 flex-col gap-[2px]">
                  <span className="truncate font-medium" style={{ fontSize: type2.sm, color: color.text }}>
                    {i.title}
                  </span>
                  <span style={caption}>{done.has(i.id) ? 'Done' : [stepsLabel(i.steps), minutesLabel(i.estMinutes)?.replace('About ', '')].filter(Boolean).join(' · ')}</span>
                </span>
                <span className="relative flex shrink-0 gap-[6px]">
                  {i.tools.slice(0, 2).map((t) => (
                    <ToolTag key={t} tool={t} />
                  ))}
                </span>
              </Press>
            </Rise>
          ))}
        </ul>
      )}
    </section>
  )
}

/** Finished = the one green check. In progress = a plain hollow ring, whole and still (never a half ring that reads as loading). */
function StateMark({ done }: { done: boolean }): ReactNode {
  return done ? (
    <StatusGlyph state="passed" size={16} still />
  ) : (
    <span aria-hidden className="block shrink-0" style={{ width: 16, height: 16, borderRadius: radius2.round, boxShadow: `inset 0 0 0 1.5px ${fill.ring}` }} />
  )
}

function RecentRow({ r, now, i }: { r: Recent; now: number; i: number }): ReactNode {
  const content = (
    <>
      <span className="relative flex shrink-0">
        <StateMark done={r.done} />
      </span>
      <span className="relative flex min-w-0 flex-1 flex-col gap-[2px]">
        <span className="truncate" style={{ fontSize: type2.sm, color: color.text }}>
          {r.title}
        </span>
        <span style={caption}>{recentLine(r)}</span>
      </span>
      {r.at && (
        <span className="relative shrink-0" style={{ fontSize: type2.xs, color: color.faint }}>
          {relDay(r.at, now)}
        </span>
      )}
    </>
  )
  return (
    <Rise as="li" i={i}>
      {r.libraryId ? (
        <Press data-recent={r.key} onClick={() => openDetail(r.libraryId!)} className="flex w-full items-center gap-[12px]" style={{ padding: '8px 10px', borderRadius: radius2.row }} aria-label={`${r.title}. ${recentLine(r)}. Open its preview.`}>
          {content}
        </Press>
      ) : (
        <div data-recent={r.key} className="flex items-center gap-[12px]" style={{ padding: '8px 10px' }}>
          {content}
        </div>
      )}
    </Rise>
  )
}

function Recents({ rows, now }: { rows: Recent[]; now: number }): ReactNode {
  if (!rows.length) return null
  return (
    <section aria-labelledby="home-recent" data-home-recent>
      <Head id="home-recent">Recent</Head>
      <ul className="m-0 flex list-none flex-col p-0" style={{ marginInline: -10 }}>
        {rows.map((r, i) => (
          <RecentRow key={r.key} r={r} now={now} i={i} />
        ))}
      </ul>
    </section>
  )
}

// ---- the page ---------------------------------------------------------------------------------------------------

export function Home(): ReactNode {
  const { data, load, now } = useDashView()
  const hero = useHero(data, load === 'loading')
  const connected = useLesson((s) => s.connected)
  const items = useLibrary((s) => s.items)
  const rows = useRows()
  const sum = summarize(rows)
  const fix = sum.canStart ? undefined : setupFix(rows)
  const offline = !connected && !data && load !== 'loading'
  const inFlight = new Set(continueList(data, items).map((c) => c.libraryId))
  const heroId = hero.kind === 'resume' || hero.kind === 'fresh' ? hero.id : undefined
  if (heroId) inFlight.add(heroId)
  const heroPrimary = hero.kind === 'resume' || hero.kind === 'fresh' || hero.kind === 'live' || (hero.kind === 'empty' && !!fix)
  return (
    <div data-home className="@container flex min-h-0 flex-1 flex-col overflow-y-auto" style={{ color: color.text }}>
      <div className="mx-auto w-full" style={{ maxWidth: 784, padding: '24px 20px 40px' }}>
        <div className="flex flex-col gap-[30px]" style={{ padding: '28px 32px 24px', borderRadius: radius2.panel, background: fill.group, boxShadow: `${highlight.topSoft}, inset 0 0 0 1px ${fill.hairline}, ${elevation.raised}` }}>
          {offline && (
            <p role="status" data-home-offline className="m-0 flex items-center gap-[8px]" style={caption}>
              <CloudOff aria-hidden size={14} strokeWidth={1.8} />
              {copy.name} is offline. Your lessons show when it connects.
            </p>
          )}
          <Rise i={0}>
            <ContinueBlock hero={hero} fix={fix} />
          </Rise>
          <Rise i={1}>
            <AskBlock primary={!heroPrimary} />
          </Rise>
          <Rise i={2}>
            <ReadyToRun skip={inFlight} done={finishedIds(data)} />
          </Rise>
          <Rise i={3}>
            <Recents rows={load === 'loading' ? [] : recentActivity(data)} now={now} />
          </Rise>
        </div>
      </div>
    </div>
  )
}

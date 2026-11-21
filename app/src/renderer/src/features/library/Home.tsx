/**
 * Feature: library. Home: the miyagi home dashboard, the Library window's first view (the Dock click, the tray and
 * openLibrary() land here). Top to bottom:
 *
 *   hero      Continue where you left off (the ONE white primary on this surface), beside the ask field
 *             ("ask miyagi anything": a goal or a pasted YouTube link, started exactly like the launcher; home.ts)
 *   band      Today ring, This week, Reps, Rhythm (features/dashboard)
 *   skills    the skill constellation, with Review and Up next beside it (every button there is quiet)
 *   lessons   Ready to run (lessons saved on this Mac) and Recent activity (last lessons, steps passed, when)
 *   footer    Milestones
 * Every part has its own loading, empty and offline state, and rises in a beat after the one above (motion.tsx).
 */
import { AnimatePresence, motion } from 'motion/react'
import { ArrowRight, ArrowUpRight, Play, Settings2 } from 'lucide-react'
import { useRef, type ReactNode } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { useLesson, useProgress as useLessonProgress } from '../../core/lesson'
import { closeWindow, openOnboarding } from '../../core/surfaces'
import { color, copy, fill, radius2, scrim, spring, surface, type2 } from '../../core/theme'
import { ProgressRing, Spinner } from '../../core/ui/atoms'
import { PrimaryButton, QuietButton } from '../../core/ui/buttons'
import { Keycap } from '../../core/ui/Keycap'
import { MiyagiMark } from '../../core/ui/Mark'
import { StatusGlyph } from '../../core/ui/status'
import { Band } from '../dashboard/Band'
import { Constellation } from '../dashboard/Constellation'
import { Milestones, useDashView } from '../dashboard/Dashboard'
import { milestones, relDay } from '../dashboard/model'
import { Review, SkillCard, UpNext } from '../dashboard/Rail'
import { TodayRing } from '../dashboard/parts'
import type { DashData } from '../dashboard/types'
import { HOW_LABEL } from '../launcher/parts'
import { thumbnailFor } from '../launcher/youtube'
import { summarize, useRows } from '../onboarding/rows'
import { pickHero, readAsk, recentActivity, setAskText, setHow, stepsPassed, submitAsk, useAsk, type Hero, type How, type Recent } from './homeModel'
import { Press, Rise } from './motion'
import { Skeleton, TOOL_NAME, ToolTile, minutesLabel, soft, stepsLabel } from './parts'
import { openDetail, setSection, start, useLibrary } from './store'

const caption = { fontSize: type2.xs, lineHeight: '16px', color: color.label } as const
/** Cards on the window: a lighter step, a top edge from above, a hairline, then two soft layers under it. */
const card = {
  borderRadius: radius2.panel,
  background: fill.group,
  boxShadow: `inset 0 1px 0 ${fill.chip}, inset 0 0 0 1px ${fill.hairline}, ${surface.shadowSmall}`
} as const

function H2({ id, children, right }: { id: string; children: ReactNode; right?: ReactNode }): ReactNode {
  return (
    <div className="flex min-h-[28px] items-center gap-[8px]">
      <h2 id={id} className="m-0 font-semibold" style={{ fontSize: type2.body, color: color.text }}>
        {children}
      </h2>
      {right && <div className="ml-auto flex items-center gap-[8px]">{right}</div>}
    </div>
  )
}

// ---- hero -------------------------------------------------------------------------------------------------------

function useHero(data: DashData | undefined, dashLoading: boolean): Hero {
  const lib = useLibrary(useShallow((s) => ({ loaded: s.loaded, items: s.items, canStart: s.caps.start || !s.capsKnown })))
  const lesson = useLesson(useShallow((s) => ({ title: s.lesson?.title, stepTitle: s.stepTitle, building: s.building, msg: s.buildingMessage, bp: s.buildingProgress, src: s.build?.source?.title })))
  const p = useLessonProgress()
  return pickHero({
    loaded: lib.loaded,
    dashLoading,
    items: lib.items,
    data,
    canStart: lib.canStart,
    live: lesson.title && !lesson.building ? { title: lesson.title, stepTitle: lesson.stepTitle, index: p.index, total: p.total, fraction: p.fraction } : undefined,
    building: lesson.building ? { title: lesson.src ?? lesson.title, message: lesson.msg, progress: lesson.bp } : undefined
  })
}

const KICKER: Record<Hero['kind'], string> = {
  loading: '',
  live: 'You’re in a lesson',
  building: 'Building your lesson',
  resume: 'Continue where you left off',
  fresh: 'Ready when you are',
  empty: `Welcome to ${copy.name}`
}

function HeroCard({ hero }: { hero: Hero }): ReactNode {
  const starting = useLibrary((s) => s.starting)
  const err = useLibrary((s) => s.startError)
  const rows = useRows()
  const setupLeft = !summarize(rows).canStart
  const connected = useLesson((s) => s.connected)
  if (hero.kind === 'loading')
    return (
      <div aria-busy aria-label="Loading your lessons" className="flex flex-col gap-[12px]" style={{ ...card, padding: 24, height: '100%' }}>
        <div style={{ width: 160, height: 12, borderRadius: radius2.round, background: fill.skeleton }} />
        <div style={{ width: '70%', height: 22, borderRadius: radius2.control, background: fill.skeleton }} />
        <div style={{ width: '45%', height: 12, borderRadius: radius2.round, background: fill.skeleton }} />
        <div className="mt-auto" style={{ width: 140, height: 44, borderRadius: radius2.card, background: fill.skeleton }} />
      </div>
    )
  const id = hero.kind === 'resume' || hero.kind === 'fresh' ? hero.id : undefined
  const busy = !!id && starting === id
  const fraction = hero.kind === 'resume' || hero.kind === 'live' ? hero.fraction : hero.kind === 'building' ? (hero.fraction ?? 0) : undefined
  const title = hero.kind === 'empty' ? 'What do you want to learn?' : (hero.title ?? 'Your next lesson')
  const line = hero.kind === 'empty' ? 'Type a goal or paste a YouTube link. miyagi builds the lesson and checks each step.' : hero.line
  const tools = hero.kind === 'resume' || hero.kind === 'fresh' ? hero.tools : []
  return (
    <section aria-labelledby="home-hero" data-home-hero={hero.kind} className="relative flex h-full gap-[24px]" style={{ ...card, padding: 24 }}>
      <div className="flex min-w-0 flex-1 flex-col">
        <span className="font-medium" style={{ fontSize: type2.xs, color: color.label, letterSpacing: '0.01em' }}>
          {KICKER[hero.kind]}
        </span>
        <h2 id="home-hero" className="m-0 line-clamp-2 font-semibold" style={{ marginTop: 8, fontSize: type2.xl, lineHeight: '26px', letterSpacing: '-0.01em', color: color.text }}>
          {title}
        </h2>
        <div className="flex flex-wrap items-center gap-x-[8px] gap-y-[4px]" style={{ marginTop: 6, fontSize: type2.sm, color: soft }}>
          <span>{line}</span>
          {tools.length > 0 && (
            <span style={{ color: color.label }}>
              {' · '}
              {tools.map((t) => TOOL_NAME[t]).join(', ')}
            </span>
          )}
        </div>
        <div className="mt-auto flex flex-wrap items-center gap-[12px]" style={{ paddingTop: 20 }}>
          {hero.kind === 'resume' && (
            <PrimaryButton
              label="Continue"
              icon={Play}
              size="lg"
              busy={busy}
              disabled={!hero.canStart || (!!starting && !busy)}
              title={hero.canStart ? 'Picks up at your step. Ready instantly.' : 'This engine can’t start saved lessons yet.'}
              onClick={() => void start(hero.id)}
            />
          )}
          {hero.kind === 'fresh' && (
            <PrimaryButton label="Start lesson" icon={Play} size="lg" busy={busy} disabled={!hero.canStart || (!!starting && !busy)} onClick={() => void start(hero.id)} />
          )}
          {hero.kind === 'live' && <PrimaryButton label="Back to the lesson" icon={ArrowRight} size="lg" onClick={() => void closeWindow('library')} />}
          {hero.kind === 'empty' && setupLeft && <QuietButton label="Finish setup" icon={Settings2} size="lg" onClick={() => void openOnboarding()} />}
          {hero.kind === 'building' && (
            <span className="flex items-center gap-[8px]" style={caption}>
              <Spinner size={14} c={color.text} />
              The island shows each step. You can keep working.
            </span>
          )}
          {!connected && (hero.kind === 'resume' || hero.kind === 'fresh') ? (
            <span role="status" style={caption}>
              miyagi is offline. This picks up when it connects.
            </span>
          ) : (
            hero.kind === 'resume' && hero.when && !(err && err.id === hero.id) && <span style={caption}>Last opened {relDay(hero.when, Date.now()).toLowerCase()}</span>
          )}
          {err && err.id === id && (
            <span role="status" style={{ ...caption, color: color.text }}>
              {err.text}
            </span>
          )}
        </div>
      </div>
      <div className="flex shrink-0 items-center justify-center" style={{ width: 112 }}>
        {fraction !== undefined ? (
          <TodayRing fraction={fraction} closed={false} size={104}>
            <span className="flex flex-col items-center">
              <span className="tabular-nums font-semibold" style={{ fontSize: type2.xl, color: color.text }}>
                {Math.round(fraction * 100)}%
              </span>
              <span style={{ fontSize: type2.micro, color: color.label }}>{hero.kind === 'building' ? 'built' : 'done'}</span>
            </span>
          </TodayRing>
        ) : (
          <MiyagiMark size={72} />
        )}
      </div>
    </section>
  )
}

// ---- ask --------------------------------------------------------------------------------------------------------

const IDEAS = ['Clean a messy CSV with pandas', 'Build a tiny web server in Python', 'Train a small image classifier']
const HOW_HINT: Record<How, string> = { lesson: 'miyagi writes a lesson for it, step by step.', video: 'Pick a tutorial video. miyagi turns it into a lesson.' }

function Choice({ how, on }: { how: How; on: boolean }): ReactNode {
  return (
    <Press
      role="radio"
      aria-checked={on}
      data-how={how}
      onClick={() => setHow(how)}
      className="flex flex-1 flex-col gap-[2px]"
      style={{ padding: '10px 12px', borderRadius: radius2.card, background: on ? fill.navActive : surface.row, boxShadow: `inset 0 0 0 1px ${on ? fill.trackNextMini : surface.border}` }}
    >
      <span className="relative flex items-center gap-[8px] font-medium" style={{ fontSize: type2.sm, color: color.text }}>
        <span aria-hidden className="block shrink-0" style={{ width: 12, height: 12, borderRadius: radius2.round, boxShadow: `inset 0 0 0 ${on ? 4 : 1.5}px ${on ? color.text : fill.ring}` }} />
        {HOW_LABEL[how]}
      </span>
      <span className="relative" style={{ ...caption, paddingLeft: 20 }}>
        {HOW_HINT[how]}
      </span>
    </Press>
  )
}

function AskCard({ primary }: { primary: boolean }): ReactNode {
  const ask = useAsk()
  const items = useLibrary((s) => s.items)
  const canStart = useLibrary((s) => s.caps.start)
  const connected = useLesson((s) => s.connected)
  const input = useRef<HTMLInputElement>(null)
  const read = readAsk(ask.text, items, canStart)
  const go = (): void => {
    if (!submitAsk(connected)) input.current?.focus()
  }
  const Btn = primary ? PrimaryButton : QuietButton
  const actionLabel = read.kind === 'link' ? (read.match ? 'Start lesson' : 'Build lesson') : ask.how === 'lesson' ? 'Teach me' : 'Find videos'
  return (
    <section aria-labelledby="home-ask" data-home-ask className="flex h-full flex-col gap-[12px]" style={{ ...card, padding: 20 }}>
      <H2 id="home-ask">Learn something new</H2>
      <form
        className="flex items-center gap-[10px]"
        style={{ height: 48, padding: '0 8px 0 14px', borderRadius: radius2.card, background: scrim.launcher, boxShadow: `inset 0 1px 3px ${scrim.spotlightSoft}, inset 0 0 0 1px ${surface.border}` }}
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
            aria-label={actionLabel}
            disabled={!!ask.sending}
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            whileTap={{ scale: 0.94 }}
            transition={spring}
            className="flex shrink-0 cursor-pointer items-center justify-center outline-offset-2 focus-visible:outline-2 focus-visible:outline-solid"
            style={{ width: 32, height: 32, borderRadius: radius2.control, background: color.accent, color: color.onAccent, outlineColor: color.text }}
          >
            {ask.sending ? <Spinner size={13} c={color.onAccent} track={fill.onAccentKey} /> : <ArrowRight size={15} strokeWidth={2} aria-hidden />}
          </motion.button>
        )}
      </form>
      <div className="relative min-h-[112px]">
        <AnimatePresence mode="wait" initial={false}>
          {read.kind === 'idle' && (
            <motion.div key="idle" className="flex flex-col gap-[8px]" initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, transition: { duration: 0.12 } }} transition={spring}>
              <span style={caption}>Type a goal or paste a YouTube link. Try one:</span>
              <div className="flex flex-wrap gap-[6px]">
                {IDEAS.map((t) => (
                  <Press
                    key={t}
                    data-idea
                    onClick={() => {
                      setAskText(t)
                      input.current?.focus()
                    }}
                    className="flex items-center"
                    style={{ height: 28, padding: '0 10px', borderRadius: radius2.round, background: surface.row, boxShadow: `inset 0 0 0 1px ${surface.border}`, fontSize: type2.xs, color: soft }}
                  >
                    <span className="relative">{t}</span>
                  </Press>
                ))}
              </div>
            </motion.div>
          )}
          {read.kind === 'goal' && (
            <motion.div key="goal" className="flex flex-col gap-[10px]" initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, transition: { duration: 0.12 } }} transition={spring}>
              <div role="radiogroup" aria-label="How to learn it" className="flex gap-[8px]">
                <Choice how="lesson" on={ask.how === 'lesson'} />
                <Choice how="video" on={ask.how === 'video'} />
              </div>
              <div className="flex items-center gap-[12px]">
                <Btn label={actionLabel} icon={ArrowRight} busy={!!ask.sending} disabled={!!ask.sending} onClick={go} />
                {ask.note ? (
                  <span role="status" style={{ ...caption, color: color.text }}>
                    {ask.note}
                  </span>
                ) : (
                  <span style={caption}>{ask.sending ? 'Sending to miyagi' : connected ? 'The island shows the build.' : 'miyagi is offline.'}</span>
                )}
              </div>
            </motion.div>
          )}
          {read.kind === 'link' && (
            <motion.div key="link" className="flex flex-col gap-[10px]" initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, transition: { duration: 0.12 } }} transition={spring}>
              <div className="flex items-center gap-[12px]" style={{ padding: 8, borderRadius: radius2.card, background: surface.row, boxShadow: `inset 0 0 0 1px ${surface.border}` }}>
                <img src={thumbnailFor(read.link.videoId)} alt="" width={80} height={45} className="block shrink-0 object-cover" style={{ borderRadius: radius2.keycap, background: fill.thumb }} />
                <div className="flex min-w-0 flex-col gap-[2px]">
                  <span className="truncate font-medium" style={{ fontSize: type2.sm, color: color.text }}>
                    {read.match ? read.match.title : 'YouTube video'}
                  </span>
                  <span style={caption}>{read.match ? 'Already a lesson. Ready instantly.' : 'miyagi turns it into a lesson with checks.'}</span>
                </div>
              </div>
              <div className="flex items-center gap-[12px]">
                <Btn label={actionLabel} icon={read.match ? Play : ArrowRight} busy={!!ask.sending} disabled={!!ask.sending} onClick={go} />
                {ask.note && (
                  <span role="status" style={{ ...caption, color: color.text }}>
                    {ask.note}
                  </span>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </section>
  )
}

// ---- lessons: ready to run, recent activity ---------------------------------------------------------------------

function ReadyToRun(): ReactNode {
  const loaded = useLibrary((s) => s.loaded)
  const items = useLibrary((s) => s.items)
  const ready = items.filter((i) => i.ready && !i.progress)
  return (
    <section aria-labelledby="home-ready" data-home-ready className="flex h-full flex-col gap-[12px]" style={{ ...card, padding: 20 }}>
      <H2 id="home-ready" right={ready.length > 3 ? <QuietButton label={`See all ${ready.length}`} onClick={() => setSection('library')} /> : <span style={caption}>Saved on this Mac</span>}>
        Ready to run
      </H2>
      {!loaded ? (
        <div className="flex flex-col gap-[8px]" aria-busy aria-label="Loading lessons">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} h={56} />
          ))}
        </div>
      ) : !ready.length ? (
        <div className="flex flex-col items-start gap-[4px]" style={{ padding: 16, borderRadius: radius2.card, border: `1px dashed ${surface.border}` }}>
          <span className="font-medium" style={{ fontSize: type2.sm, color: color.text }}>
            {items.length ? 'Every saved lesson is under way.' : 'No lessons on this Mac yet.'}
          </span>
          <span style={caption}>Ask miyagi above. New lessons are saved here.</span>
        </div>
      ) : (
        <ul className="m-0 flex list-none flex-col gap-[6px] p-0">
          {ready.slice(0, 3).map((i, n) => (
            <Rise key={i.id} as="li" i={n}>
              <Press
                data-lesson={i.id}
                aria-label={`${i.title}. ${stepsLabel(i.steps)}. Open its preview.`}
                onClick={() => openDetail(i.id)}
                className="flex w-full items-center gap-[12px]"
                style={{ padding: '10px 12px', borderRadius: radius2.card, background: surface.row, boxShadow: `inset 0 0 0 1px ${fill.hairline}` }}
              >
                <span className="relative flex shrink-0 gap-[4px]">
                  {i.tools.slice(0, 2).map((t) => (
                    <ToolTile key={t} tool={t} size={28} />
                  ))}
                </span>
                <span className="relative flex min-w-0 flex-1 flex-col gap-[2px]">
                  <span className="truncate font-medium" style={{ fontSize: type2.sm, color: color.text }}>
                    {i.title}
                  </span>
                  <span style={caption}>{[stepsLabel(i.steps), minutesLabel(i.estMinutes)].filter(Boolean).join(' · ')}</span>
                </span>
                <ArrowUpRight aria-hidden size={14} strokeWidth={1.8} className="relative shrink-0" style={{ color: color.faint }} />
              </Press>
            </Rise>
          ))}
        </ul>
      )}
    </section>
  )
}

function RecentRow({ r, now, i }: { r: Recent; now: number; i: number }): ReactNode {
  const allPassed = r.done && r.total > 0 && r.passed + r.skipped >= r.total && r.passed > 0
  const content = (
    <>
      <span className="relative flex shrink-0">
        {allPassed ? (
          <StatusGlyph state="passed" size={18} />
        ) : r.total ? (
          <ProgressRing fraction={r.passed / r.total} size={18} stroke={2} />
        ) : (
          <StatusGlyph state="unknown" size={18} />
        )}
      </span>
      <span className="relative flex min-w-0 flex-1 flex-col gap-[2px]">
        <span className="truncate" style={{ fontSize: type2.sm, color: color.text }}>
          {r.title}
        </span>
        <span style={caption}>
          {r.done ? 'Finished' : 'In progress'} · {stepsPassed(r)}
        </span>
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
        <Press data-recent={r.key} onClick={() => openDetail(r.libraryId!)} className="flex w-full items-center gap-[12px]" style={{ padding: '8px 10px', borderRadius: radius2.row }} aria-label={`${r.title}. ${stepsPassed(r)}. Open its preview.`}>
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

function RecentActivity({ rows, now, loading }: { rows: Recent[]; now: number; loading: boolean }): ReactNode {
  return (
    <section aria-labelledby="home-recent" data-home-recent className="flex h-full flex-col gap-[8px]" style={{ ...card, padding: 20 }}>
      <H2 id="home-recent" right={<span style={caption}>Steps you passed yourself</span>}>
        Recent activity
      </H2>
      {loading ? (
        <div className="flex flex-col gap-[8px]" aria-busy aria-label="Loading activity">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} h={44} />
          ))}
        </div>
      ) : !rows.length ? (
        <div className="flex flex-col gap-[4px]" style={{ padding: '8px 10px' }}>
          <span className="font-medium" style={{ fontSize: type2.sm, color: color.text }}>
            Nothing yet
          </span>
          <span style={caption}>Your lessons and the steps you pass show up here.</span>
        </div>
      ) : (
        <ul className="m-0 flex list-none flex-col p-0">
          {rows.map((r, i) => (
            <RecentRow key={r.key} r={r} now={now} i={i} />
          ))}
        </ul>
      )}
    </section>
  )
}

// ---- the page ---------------------------------------------------------------------------------------------------

export function Home(): ReactNode {
  const { data, load, now, goals, r, t, due, later } = useDashView()
  const hero = useHero(data, load === 'loading')
  const loading = load === 'loading'
  // One primary per surface: the hero's when it has one, else the ask field's action.
  const heroPrimary = hero.kind === 'resume' || hero.kind === 'fresh' || hero.kind === 'live'
  return (
    <div data-home className="flex min-h-0 flex-1 flex-col overflow-y-auto" style={{ color: color.text }}>
      <div className="flex flex-col gap-[16px]" style={{ padding: '20px 32px 32px' }}>
        <div className="grid gap-[16px]" style={{ gridTemplateColumns: 'minmax(0, 1.15fr) minmax(0, 1fr)', minHeight: 224 }}>
          <Rise i={0}>
            <HeroCard hero={hero} />
          </Rise>
          <Rise i={1}>
            <AskCard primary={!heroPrimary} />
          </Rise>
        </div>
        <Rise i={2}>
          <Band data={data} now={now} goals={goals} r={r} t={t} loading={loading} />
        </Rise>
        <div className="grid gap-[16px]" style={{ gridTemplateColumns: 'minmax(0, 1fr) 300px' }}>
          <Rise i={3} className="grid" style={{ minHeight: data?.tracks.length ? 452 : undefined }}>
            <Constellation data={data} review={due} loading={loading}>
              <SkillCard data={data} now={now} route="library" />
            </Constellation>
          </Rise>
          <Rise i={4} className="flex flex-col gap-[12px]" data-rail="">
            {loading ? (
              <>
                <Skeleton h={160} />
                <Skeleton h={200} />
              </>
            ) : (
              <>
                <Review data={data} due={due} later={later} now={now} route="library" />
                <UpNext data={data} route="library" />
              </>
            )}
          </Rise>
        </div>
        <div className="grid gap-[16px]" style={{ gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)' }}>
          <Rise i={5}>
            <ReadyToRun />
          </Rise>
          <Rise i={6}>
            <RecentActivity rows={recentActivity(data)} now={now} loading={loading} />
          </Rise>
        </div>
        <Rise i={7}>
          <Milestones list={loading ? [] : milestones(data, r, now)} />
        </Rise>
      </div>
    </div>
  )
}

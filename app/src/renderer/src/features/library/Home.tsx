/**
 * Feature: library. Home: the miyagi home dashboard, the Library window's first view (the Dock click, the tray and
 * openLibrary() land here). Top to bottom:
 *
 *   hero      Continue where you left off (the ONE white primary on this surface; Finish setup instead whenever setup
 *             is left: then the hero line says what's missing and Continue waits, quiet), beside the ask field ("ask
 *             miyagi anything": a goal or a pasted YouTube link, started exactly like the launcher; homeModel.ts)
 *   band      Today ring, This week, Reps, Rhythm (features/dashboard)
 *   lessons   Ready to run (lessons saved on this Mac, finished ones last) and Recent activity
 *   skills    the skill constellation, with Review and Up next beside it (every button there is quiet)
 *   footer    Milestones
 * The page is a container: narrower windows stack the hero over the ask card and move the rail under the skills.
 * A brand-new learner (nothing saved, nothing done) gets one calm "how it works" card instead of a wall of empty
 * charts; the engine away with nothing cached gets one offline line. Every other part has its own loading and empty
 * state, and rises in a beat after the one above (motion.tsx).
 */
import { AnimatePresence, motion } from 'motion/react'
import { ArrowRight, ChevronRight, CloudOff, Play, RotateCcw, Settings2 } from 'lucide-react'
import { useRef, type ReactNode } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { useLesson, useProgress as useLessonProgress } from '../../core/lesson'
import { closeWindow, openOnboarding } from '../../core/surfaces'
import { color, copy, fill, radius2, scrim, surface, type2 } from '../../core/theme'
import { enter, fade, press } from '../../core/ui/motion'
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
import { useDash } from '../dashboard/store'
import type { DashData } from '../dashboard/types'
import { thumbnailFor } from '../launcher/youtube'
import { summarize, useRows } from '../onboarding/rows'
import { finishedIds, pickHero, pickVideo, readAsk, recentActivity, setAskText, stepsPassed, submitAsk, useAsk, type Hero, type Recent } from './homeModel'
import { Press, Ring, Rise } from './motion'
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

function HeroCard({ hero, setupLeft, setupHint }: { hero: Hero; setupLeft: boolean; setupHint: string }): ReactNode {
  // Either start in flight (this window's library store, or Up next / skills in the dashboard store) holds the hero.
  const libStarting = useLibrary((s) => s.starting)
  const dashStarting = useDash((s) => s.starting)
  const starting = libStarting ?? dashStarting
  const err = useLibrary((s) => s.startError)
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
  // The empty hero says what miyagi is; the ask card beside it is where to type (never the same line twice).
  const title = hero.kind === 'empty' ? 'Learn by doing, checked step by step' : (hero.title ?? 'Your next lesson')
  // A saved lesson can't start while setup is left (Accessibility off, the engine down): the hero says what's missing
  // and Finish setup takes the white primary; the lesson's own button waits, quiet and disabled, saying why.
  // Offline is not setup: the engine row reads Connecting, and the hero's caption already says miyagi is offline.
  const blocked = setupLeft && connected && (hero.kind === 'resume' || hero.kind === 'fresh')
  const line = hero.kind === 'empty' ? (setupLeft ? 'Finish setup first, then ask on the right.' : 'Ask on the right. Your lessons and progress live here.') : blocked ? setupHint : hero.line
  const tools = !blocked && (hero.kind === 'resume' || hero.kind === 'fresh') ? hero.tools : []
  return (
    <section aria-labelledby="home-hero" data-home-hero={hero.kind} className="relative flex h-full gap-[24px]" style={{ ...card, padding: 24 }}>
      <div className="flex min-w-0 flex-1 flex-col">
        <span className="font-medium" style={{ fontSize: type2.xs, color: color.label, letterSpacing: '0.01em' }}>
          {KICKER[hero.kind]}
        </span>
        <h2 id="home-hero" className="m-0 line-clamp-2 font-semibold" style={{ marginTop: 8, fontSize: type2.xl, lineHeight: '26px', letterSpacing: '-0.01em', color: color.text }}>
          {title}
        </h2>
        <div className="flex flex-wrap items-center gap-x-[8px] gap-y-[4px]" style={{ marginTop: 6, fontSize: type2.sm, color: blocked ? color.text : soft }}>
          {blocked && (
            <span className="flex shrink-0">
              <StatusGlyph state="notyet" size={14} />
            </span>
          )}
          <span data-hero-line>{line}</span>
          {tools.length > 0 && (
            <span style={{ color: color.label }}>
              {' · '}
              {tools.map((t) => TOOL_NAME[t]).join(', ')}
            </span>
          )}
        </div>
        <div className="mt-auto flex flex-wrap items-center gap-[12px]" style={{ paddingTop: 20 }}>
          {(blocked || (hero.kind === 'empty' && setupLeft)) && (
            <Ring>
              <PrimaryButton label="Finish setup" icon={Settings2} size="lg" onClick={() => void openOnboarding()} />
            </Ring>
          )}
          {blocked && (
            <Ring>
              <QuietButton label={hero.kind === 'resume' ? 'Continue' : 'Start lesson'} icon={Play} size="lg" disabled title={`${setupHint} Then this lesson is ready.`} onClick={() => undefined} />
            </Ring>
          )}
          {!blocked && hero.kind === 'resume' && (
            <Ring>
              <PrimaryButton
                label="Continue"
                icon={Play}
                size="lg"
                busy={busy}
                disabled={!hero.canStart || (!!starting && !busy)}
                title={hero.canStart ? 'Picks up at your step. Ready instantly.' : 'This engine can’t start saved lessons yet.'}
                onClick={() => void start(hero.id)}
              />
            </Ring>
          )}
          {!blocked && hero.kind === 'fresh' && (
            <Ring>
              <PrimaryButton label="Start lesson" icon={Play} size="lg" busy={busy} disabled={!hero.canStart || (!!starting && !busy)} onClick={() => void start(hero.id)} />
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
              The island shows each step. You can keep working.
            </span>
          )}
          {blocked ? null : !connected && (hero.kind === 'resume' || hero.kind === 'fresh') ? (
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

function AskCard({ primary }: { primary: boolean }): ReactNode {
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
          // A pointer shortcut only: the labeled button below is the one keyboard and screen-reader stop.
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
            className="flex shrink-0 cursor-pointer items-center justify-center outline-offset-2 focus-visible:outline-2 focus-visible:outline-solid"
            style={{ width: 32, height: 32, borderRadius: radius2.control, background: fill.chip, color: color.text, outlineColor: color.text }}
          >
            {ask.sending ? <Spinner size={13} c={color.text} /> : <ArrowRight size={15} strokeWidth={2} aria-hidden />}
          </motion.button>
        )}
      </form>
      {/* Tall enough for the tallest state (a link: the video row and the button), so typing never moves the page. */}
      <div className="relative min-h-[112px]">
        {/* popLayout: the leaving state steps out of the flow at once, so a fast typist never waits on an exit. */}
        <AnimatePresence mode="popLayout" initial={false}>
          {read.kind === 'idle' && (
            <motion.div key="idle" className="flex flex-col gap-[8px]" initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, transition: fade.out }} transition={enter()}>
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
            <motion.div key="goal" className="flex flex-col gap-[12px]" initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, transition: fade.out }} transition={enter()}>
              <div className="flex items-center gap-[12px]">
                {/* Busy, never disabled: the label stays readable while it sends (submitAsk ignores a second send). */}
                <Ring>
                  <Btn label={actionLabel} icon={ArrowRight} busy={!!ask.sending} onClick={go} />
                </Ring>
                {ask.note ? (
                  <span role="status" style={{ ...caption, color: color.text }}>
                    {ask.note}
                  </span>
                ) : (
                  <span style={caption}>{ask.sending ? 'Sending to miyagi' : connected ? 'A lesson, step by step. The island shows the build.' : 'miyagi is offline.'}</span>
                )}
              </div>
              {/* Once per text (homeModel pickVideo): a second click would close the launcher it just opened. */}
              <Press
                data-pick-video
                disabled={!!ask.sending || !!ask.picked}
                title={ask.picked ? 'The launcher has your goal. Its keycap opens it again.' : undefined}
                onClick={() => void pickVideo()}
                className="flex items-center gap-[8px] self-start"
                style={{ height: 28, padding: '0 8px', marginLeft: -8, borderRadius: radius2.control, fontSize: type2.xs, color: soft, opacity: ask.picked ? 0.55 : 1 }}
              >
                <span className="relative">Pick a video instead</span>
                <span className="relative flex">
                  <Keycap k="launcher" size="sm" />
                </span>
              </Press>
            </motion.div>
          )}
          {read.kind === 'link' && (
            <motion.div key="link" className="flex flex-col gap-[10px]" initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, transition: fade.out }} transition={enter()}>
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
                <Ring>
                  <Btn label={actionLabel} icon={read.match ? Play : ArrowRight} busy={!!ask.sending} onClick={go} />
                </Ring>
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

function ReadyToRun({ upNext, done }: { upNext: Set<string>; done: Set<string> }): ReactNode {
  const loaded = useLibrary((s) => s.loaded)
  const items = useLibrary((s) => s.items)
  const saved = items.filter((i) => i.ready && !i.progress)
  // Up next already shows its lessons above: never list one twice on the page. Finished lessons go last, marked as
  // done, so a lesson Recent activity calls finished never reads as not started here.
  const fresh = saved.filter((i) => !upNext.has(i.id))
  const ready = [...fresh.filter((i) => !done.has(i.id)), ...fresh.filter((i) => done.has(i.id))]
  return (
    <section aria-labelledby="home-ready" data-home-ready className="flex h-full flex-col gap-[12px]" style={{ ...card, padding: 20 }}>
      <H2 id="home-ready" right={ready.length > 3 ? <Ring><QuietButton label={`See all ${ready.length}`} onClick={() => setSection('library')} /></Ring> :<span style={caption}>Saved on this Mac</span>}>
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
            {saved.length ? 'Your saved lessons are in Up next.' : items.length ? 'Every saved lesson is under way.' : 'No lessons on this Mac yet.'}
          </span>
          <span style={caption}>Ask miyagi above. New lessons are saved here.</span>
        </div>
      ) : (
        <ul className="m-0 flex list-none flex-col gap-[6px] p-0">
          {ready.slice(0, 3).map((i, n) => (
            <Rise key={i.id} as="li" i={n}>
              <Press
                data-lesson={i.id}
                aria-label={`${i.title}. ${done.has(i.id) ? 'Done. ' : ''}${stepsLabel(i.steps)}. Open its preview.`}
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
                  {done.has(i.id) ? (
                    <span className="flex items-center gap-[6px]" style={caption}>
                      <RotateCcw aria-hidden size={11} strokeWidth={2} />
                      Done · run again
                    </span>
                  ) : (
                    <span style={caption}>{[stepsLabel(i.steps), minutesLabel(i.estMinutes)].filter(Boolean).join(' · ')}</span>
                  )}
                </span>
                <ChevronRight aria-hidden size={13} strokeWidth={1.8} className="relative shrink-0" style={{ color: color.faint }} />
              </Press>
            </Rise>
          ))}
        </ul>
      )}
    </section>
  )
}

function RecentRow({ r, now, i }: { r: Recent; now: number; i: number }): ReactNode {
  // Green only when every step was passed: a skipped step keeps the white ring.
  const allPassed = r.done && r.total > 0 && r.passed >= r.total
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

function RecentActivity({ rows, now, loading, offline }: { rows: Recent[]; now: number; loading: boolean; offline: boolean }): ReactNode {
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
            {offline ? 'Waiting for miyagi' : 'Nothing yet'}
          </span>
          <span style={caption}>{offline ? 'Your recent lessons show when it connects.' : 'Your lessons and the steps you pass show up here.'}</span>
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

// ---- offline ----------------------------------------------------------------------------------------------------

/**
 * The engine is away and nothing is cached: one calm line instead of empty charts that read as "your history is gone".
 * "miyagi is offline" is said once on the page: here, unless the hero's caption already says it (said).
 */
function OfflineDash({ said }: { said: boolean }): ReactNode {
  return (
    <section role="status" data-home-offline className="flex items-center gap-[16px]" style={{ ...card, padding: '20px 24px' }}>
      <span className="flex shrink-0 items-center justify-center" style={{ width: 40, height: 40, borderRadius: radius2.card, background: fill.chip }}>
        <CloudOff aria-hidden size={18} strokeWidth={1.8} style={{ color: color.label }} />
      </span>
      <span className="flex min-w-0 flex-col gap-[2px]">
        <span className="font-medium" style={{ fontSize: type2.sm, color: color.text }}>
          Your streak, skills and reviews are safe.
        </span>
        {!said && <span style={caption}>{copy.name} is offline. They show here when it connects.</span>}
      </span>
    </section>
  )
}

// ---- first run ----------------------------------------------------------------------------------------------------

const HOW_IT_WORKS = [
  { n: 1, title: 'Ask', line: 'A goal, or a YouTube link.' },
  { n: 2, title: 'Do each step', line: 'In your own tools, at your pace.' },
  { n: 3, title: 'miyagi checks it', line: 'Then the next one. Help is a key away.' }
] as const

/**
 * A brand-new learner: nothing saved, nothing done. One calm card instead of empty charts, empty rails and two empty
 * lists (they arrive with the first lesson). Says how a lesson goes, in three beats.
 */
function FirstRun(): ReactNode {
  return (
    <section aria-labelledby="home-first" data-home-first className="flex flex-col gap-[20px]" style={{ ...card, padding: 24 }}>
      <div className="flex items-center gap-[16px]">
        <span className="flex shrink-0 items-center justify-center" style={{ width: 44, height: 44, borderRadius: radius2.card, background: fill.chip }}>
          <MiyagiMark size={24} />
        </span>
        <span className="flex min-w-0 flex-col gap-[2px]">
          <h2 id="home-first" className="m-0 font-medium" style={{ fontSize: type2.body, color: color.text }}>
            Your streak, skills and reviews show up after your first lesson.
          </h2>
          <span style={caption}>Lessons you build are saved on this Mac, ready to run again.</span>
        </span>
      </div>
      <ol className="m-0 grid list-none gap-[12px] p-0" style={{ gridTemplateColumns: 'repeat(3, minmax(0, 1fr))' }}>
        {HOW_IT_WORKS.map((s, i) => (
          <Rise key={s.n} as="li" i={i + 3} className="flex items-start gap-[12px]" data-how-step={String(s.n)}>
            <span
              aria-hidden
              className="flex shrink-0 items-center justify-center tabular-nums font-semibold"
              style={{ width: 24, height: 24, borderRadius: radius2.round, boxShadow: `inset 0 0 0 1.5px ${fill.ring}`, fontSize: type2.xs, color: color.text }}
            >
              {s.n}
            </span>
            <span className="flex min-w-0 flex-col gap-[2px]" style={{ paddingTop: 2 }}>
              <span className="font-medium" style={{ fontSize: type2.sm, color: color.text }}>
                {s.title}
              </span>
              <span style={caption}>{s.line}</span>
            </span>
          </Rise>
        ))}
      </ol>
    </section>
  )
}

// ---- the page ---------------------------------------------------------------------------------------------------

export function Home(): ReactNode {
  const { data, load, now, goals, r, t, due, later } = useDashView()
  const hero = useHero(data, load === 'loading')
  const loading = load === 'loading'
  const connected = useLesson((s) => s.connected)
  const lib = useLibrary(useShallow((s) => ({ loaded: s.loaded, count: s.items.length })))
  const sum = summarize(useRows())
  const setupLeft = !sum.canStart
  // Engine away with nothing to show: the dashboard sections say so once, never "No skills yet".
  const offline = !connected && !data && !loading
  // Nothing saved, nothing done, nothing tracked: one welcome card instead of a wall of empty cards.
  // (No progress answer at all from a connected engine reads the same: there is nothing to chart yet.)
  const firstRun = connected && !loading && lib.loaded && !lib.count && !data?.completed.length && !data?.inProgress.length && !data?.tracks.length
  const upNext = new Set((data?.next ?? []).flatMap((n) => (n.id ? [n.id] : [])))
  const done = finishedIds(data)
  // One primary per surface: the hero's when it has one (Finish setup counts, also when it stands in for Continue),
  // else the ask field's action.
  const heroPrimary = hero.kind === 'resume' || hero.kind === 'fresh' || hero.kind === 'live' || (hero.kind === 'empty' && setupLeft)
  // The hero says "miyagi is offline" when it has a lesson to pick up: then the offline card doesn't say it again.
  const offlineSaid = !connected && (hero.kind === 'resume' || hero.kind === 'fresh')
  /*
   * The page is a container (Tailwind container queries on [data-home]): the Library window goes down to 560 px wide.
   *   >= 1000 px   hero and ask side by side
   *   >= 900 px    the 300 px rail beside the constellation; below it the rail moves under it (two columns, then one)
   *                and the band's four tiles wrap to two by two (features/dashboard Band, overridden from here)
   *   >= 760 px    Ready to run and Recent activity side by side
   * Ready to run and Recent activity sit above the skills: what can I run now is on the first screen at 1280x820.
   */
  return (
    <div data-home className="@container flex min-h-0 flex-1 flex-col overflow-y-auto" style={{ color: color.text }}>
      <div className="flex flex-col gap-[16px] px-[20px] @min-[760px]:px-[32px]" style={{ paddingTop: 20, paddingBottom: 32 }}>
        <div data-home-top className="grid grid-cols-1 gap-[16px] @min-[1000px]:min-h-[224px] @min-[1000px]:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
          <Rise i={0}>
            <HeroCard hero={hero} setupLeft={setupLeft} setupHint={sum.hint} />
          </Rise>
          <Rise i={1}>
            <AskCard primary={!heroPrimary} />
          </Rise>
        </div>
        {offline ? (
          <Rise i={2}>
            <OfflineDash said={offlineSaid} />
          </Rise>
        ) : firstRun ? (
          <Rise i={2}>
            <FirstRun />
          </Rise>
        ) : (
          <Rise i={2} className="@max-[899px]:[&>[data-band]]:grid-cols-2! @max-[479px]:[&>[data-band]]:grid-cols-1!">
            <Band data={data} now={now} goals={goals} r={r} t={t} loading={loading} />
          </Rise>
        )}
        {!firstRun && (
          <div data-home-lessons className="grid grid-cols-1 gap-[16px] @min-[760px]:grid-cols-2">
            <Rise i={3}>
              <ReadyToRun upNext={upNext} done={done} />
            </Rise>
            <Rise i={4}>
              <RecentActivity rows={recentActivity(data)} now={now} loading={loading} offline={offline} />
            </Rise>
          </div>
        )}
        {!offline && !firstRun && (
          <div data-home-skills className="grid grid-cols-1 gap-[16px] @min-[900px]:grid-cols-[minmax(0,1fr)_300px]">
            <Rise i={5} className="grid" style={{ minHeight: data?.tracks.length ? 452 : undefined }}>
              <Constellation data={data} review={due} loading={loading}>
                <SkillCard data={data} now={now} route="library" />
              </Constellation>
            </Rise>
            <Rise i={6} className="flex flex-col gap-[12px] @max-[899px]:grid @max-[899px]:grid-cols-2 @max-[899px]:items-start @max-[599px]:grid-cols-1" data-rail="">
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
        )}
        {!offline && !firstRun && (
          <Rise i={7}>
            <Milestones list={loading ? [] : milestones(data, r, now)} />
          </Rise>
        )}
      </div>
    </div>
  )
}

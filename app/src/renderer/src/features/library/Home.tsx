/**
 * Feature: library. Home, the home window's first page (redraft, Adrian Nov 21, on Michael's brief: fewer boxes, depth,
 * soft pastel, calm copy, one clear next action). No title, no greeting, no date, no stat boxes. Parts with nothing to
 * show are left out.
 *
 *   continue  the ONE most recent unfinished lesson, its steps as a bar, one primary button. When setup is left that
 *             button is the one setup action instead ("Turn on Accessibility"), never a disabled Continue.
 *   ask       "ask miyagi anything" with three suggestion chips (a goal or a pasted YouTube link, homeModel.ts)
 *   ready     lessons saved on this Mac, each with its tool's pastel tile
 *   review    skills due for review (only when the engine lists some), one Start review
 *   recent    one row per lesson, newest state: a green check when finished, a hueless ring while in progress
 *
 * THREE LAYOUTS while Adrian picks (stage: ?home=a|b|c, default a; the unpicked two get deleted):
 *   a  Cover      a lifted Continue card with a big pastel tile, ask, a gallery of ready lessons, review + recent
 *   b  Ask first  the ask field centered under the bonsai, then Continue as one row, then plain lists
 *   c  Lists      no cards at all: every part is a list of rows on the panel, grouped by spacing (Linear)
 *
 * Continue comes from dashboard/continue.ts, the same list Lessons and Progress read.
 */
import { ArrowRight, ChevronRight, CloudOff, Play, RotateCcw } from 'lucide-react'
import { motion } from 'motion/react'
import { useRef, type CSSProperties, type ReactNode } from 'react'
import { useShallow } from 'zustand/react/shallow'
import type { LessonTool } from '../../../../../../shared/contracts/events'
import { useLesson, useProgress as useLessonProgress } from '../../core/lesson'
import { closeWindow, openOnboarding } from '../../core/surfaces'
import { color, copy, fill, radius2, tone, type Tone, type2 } from '../../core/theme'
import { Spinner } from '../../core/ui/atoms'
import { PrimaryButton, QuietButton } from '../../core/ui/buttons'
import { Keycap } from '../../core/ui/Keycap'
import { MiyagiMark } from '../../core/ui/Mark'
import { enter, press } from '../../core/ui/motion'
import { StatusGlyph } from '../../core/ui/status'
import { continueList, type Cont } from '../dashboard/continue'
import { useDashView } from '../dashboard/Dashboard'
import { relDay, relInLine } from '../dashboard/model'
import { canReview, startReview, useDash } from '../dashboard/store'
import type { DashData, ReviewEntry } from '../dashboard/types'
import { summarize, useRows } from '../onboarding/rows'
import { CARD, LessonTile, Row, SectionHead, StepBar, TextAction, caption, lessonIcon, lessonTone } from '../shell/ui'
import { finishedIds, pickHero, readAsk, recentActivity, recentLine, setAskText, setupFix, submitAsk, useAsk, type Hero, type Recent } from './homeModel'
import { Press, Ring, Rise } from './motion'
import { Skeleton, ToolTag, minutesLabel, stepsLabel } from './parts'
import { openDetail, setSection, start, useLibrary } from './store'
import type { LibraryItem } from '../../../../../../shared/contracts/events'

type Look = 'a' | 'b' | 'c'
/** Stage only, while Adrian picks: ?home=a|b|c. Electron has no query, so it shows the default. */
function homeLook(): Look {
  try {
    const v = new URLSearchParams(location.search).get('home')
    return v === 'b' || v === 'c' ? v : 'a'
  } catch {
    return 'a'
  }
}

// ---- the continue model -------------------------------------------------------------------------------------------

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

type Fix = { label: string; line: string }
type View = { head: string; title: string; line: string; tools: LessonTool[]; id: string; blocked: boolean; done?: number; total?: number }

/** What the Continue part says, or null when there is nothing to continue and nothing to fix. */
function useView(hero: Hero, fix: Fix | undefined, conts: Cont[], items: LibraryItem[]): View | null | 'loading' {
  const connected = useLesson((s) => s.connected)
  const p = useLessonProgress()
  if (hero.kind === 'loading') return 'loading'
  const startable = hero.kind === 'resume' || hero.kind === 'fresh'
  const blocked = !!fix && connected && (startable || hero.kind === 'empty')
  if (hero.kind === 'empty' && !blocked) return null
  const id = startable ? hero.id : hero.kind
  const head = blocked && hero.kind === 'empty' ? 'Setup' : hero.kind === 'live' ? 'In a lesson' : hero.kind === 'building' ? 'Building' : hero.kind === 'fresh' ? 'Start' : 'Continue'
  const title = hero.kind === 'empty' ? 'Almost ready' : (hero.title ?? 'Your next lesson')
  const line = blocked ? fix!.line : hero.kind === 'empty' ? '' : hero.line
  let done: number | undefined
  let total: number | undefined
  if (hero.kind === 'resume') {
    const c = conts.find((x) => x.libraryId === hero.id)
    if (c) [done, total] = [c.passed, c.total]
  } else if (hero.kind === 'live' && p.total) [done, total] = [p.index, p.total]
  else if (hero.kind === 'fresh') [done, total] = [0, items.find((x) => x.id === hero.id)?.steps]
  return { head, title, line, tools: startable && !blocked ? hero.tools : [], id, blocked, done, total }
}

/** The one primary action for the Continue part, and its quiet notes. */
function ContAction({ hero, fix, size = 'lg' }: { hero: Hero; fix?: Fix; size?: 'md' | 'lg' }): ReactNode {
  const libStarting = useLibrary((s) => s.starting)
  const dashStarting = useDash((s) => s.starting)
  const starting = libStarting ?? dashStarting
  const err = useLibrary((s) => s.startError)
  const connected = useLesson((s) => s.connected)
  const startable = hero.kind === 'resume' || hero.kind === 'fresh'
  const id = startable ? hero.id : undefined
  const busy = !!id && starting === id
  const blocked = !!fix && connected && (startable || hero.kind === 'empty')
  return (
    <>
      {blocked && (
        <Ring>
          <PrimaryButton label={fix!.label} size={size} onClick={() => void openOnboarding()} />
        </Ring>
      )}
      {!blocked && startable && (
        <Ring>
          <PrimaryButton
            label={hero.kind === 'resume' ? 'Continue' : 'Start lesson'}
            icon={Play}
            size={size}
            busy={busy}
            disabled={!hero.canStart || (!!starting && !busy)}
            title={hero.canStart ? undefined : 'This engine can’t start saved lessons yet.'}
            onClick={() => void start(hero.id)}
          />
        </Ring>
      )}
      {hero.kind === 'live' && (
        <Ring>
          <PrimaryButton label="Back to the lesson" icon={ArrowRight} size={size} onClick={() => void closeWindow('library')} />
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
    </>
  )
}

function Loading({ rows = 3 }: { rows?: number }): ReactNode {
  return (
    <div aria-busy aria-label="Loading your lessons" className="flex flex-col gap-[10px]">
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} h={i === 0 ? 18 : 40} />
      ))}
    </div>
  )
}

// ---- ask --------------------------------------------------------------------------------------------------------

const IDEAS: Array<{ text: string; tone: Tone }> = [
  { text: 'Clean a messy CSV with pandas', tone: 'sky' },
  { text: 'Build a tiny web server', tone: 'lilac' },
  { text: 'Train an image classifier', tone: 'pink' }
]

function Ask({ size = 'md', center = false, primary = false }: { size?: 'sm' | 'md' | 'lg'; center?: boolean; primary?: boolean }): ReactNode {
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
  const h = size === 'lg' ? 56 : size === 'md' ? 50 : 42
  return (
    <section aria-label="Learn something new" data-home-ask className={`flex flex-col ${center ? 'items-stretch' : ''}`}>
      <form
        className="flex items-center gap-[10px]"
        style={{
          height: h,
          padding: `0 8px 0 ${size === 'lg' ? 18 : 14}px`,
          borderRadius: size === 'lg' ? radius2.chip : radius2.card,
          background: 'var(--l-overlay)',
          boxShadow: `inset 0 0 0 1px ${fill.fieldBorder}, var(--e-raised)`
        }}
        onSubmit={(e) => {
          e.preventDefault()
          go()
        }}
      >
        <MiyagiMark size={size === 'lg' ? 18 : 16} />
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
          style={{ fontSize: size === 'lg' ? type2.lg : type2.body, color: color.text }}
        />
        {read.kind === 'idle' ? (
          <span className="flex shrink-0 items-center gap-[6px]" style={{ paddingRight: 4 }}>
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
            style={{ width: h - 16, height: h - 16, borderRadius: radius2.row, background: color.accent, color: color.onAccent }}
          >
            {ask.sending ? <Spinner size={13} c={color.onAccent} /> : <ArrowRight size={15} strokeWidth={2} aria-hidden />}
          </motion.button>
        )}
      </form>
      <div className={`flex flex-wrap items-center gap-[8px] ${center ? 'justify-center' : ''}`} style={{ marginTop: 12, minHeight: 32 }}>
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

// ---- shared lists -------------------------------------------------------------------------------------------------

function useReady(skip: Set<string>, done: Set<string>): { loaded: boolean; ready: LibraryItem[]; more: boolean } {
  const loaded = useLibrary((s) => s.loaded)
  const items = useLibrary((s) => s.items)
  const fresh = items.filter((i) => i.ready && !i.progress && !skip.has(i.id))
  const ready = [...fresh.filter((i) => !done.has(i.id)), ...fresh.filter((i) => done.has(i.id))]
  return { loaded, ready, more: items.length > 3 }
}

const seeAll = (
  <TextAction onClick={() => setSection('library')}>
    <span className="relative">See all</span>
    <ChevronRight aria-hidden size={12} strokeWidth={1.8} className="relative" />
  </TextAction>
)

const readyLine = (i: LibraryItem, done: boolean): string => (done ? 'Done' : [stepsLabel(i.steps), minutesLabel(i.estMinutes)?.replace('About ', '')].filter(Boolean).join(' · '))

function ReadyRows({ skip, done, max = 4 }: { skip: Set<string>; done: Set<string>; max?: number }): ReactNode {
  const { loaded, ready, more } = useReady(skip, done)
  if (loaded && !ready.length) return null
  return (
    <section aria-labelledby="home-ready" data-home-ready>
      <SectionHead id="home-ready" right={more ? seeAll : undefined}>
        Ready to run
      </SectionHead>
      {!loaded ? (
        <Loading />
      ) : (
        <ul className="m-0 flex list-none flex-col p-0" style={{ marginInline: -10 }}>
          {ready.slice(0, max).map((i, n) => (
            <Rise key={i.id} as="li" i={n}>
              <Row onClick={() => openDetail(i.id)} label={`${i.title}. ${readyLine(i, done.has(i.id))}. Open its preview.`} data={{ 'data-lesson': i.id }}>
                <span className="relative flex">
                  <LessonTile tools={i.tools} id={i.id} size={30} />
                </span>
                <span className="relative flex min-w-0 flex-1 flex-col gap-[1px]">
                  <span className="truncate font-medium" style={{ fontSize: type2.sm, color: color.text }}>
                    {i.title}
                  </span>
                  <span style={caption}>{readyLine(i, done.has(i.id))}</span>
                </span>
                <span className="relative flex shrink-0 gap-[6px]">
                  {i.tools.slice(0, 2).map((t) => (
                    <ToolTag key={t} tool={t} />
                  ))}
                </span>
              </Row>
            </Rise>
          ))}
        </ul>
      )}
    </section>
  )
}

/** A gallery of ready lessons (layout a): a pastel cover band with the tool's icon, the title, steps and minutes. */
function ReadyGallery({ skip, done }: { skip: Set<string>; done: Set<string> }): ReactNode {
  const { loaded, ready, more } = useReady(skip, done)
  if (loaded && !ready.length) return null
  return (
    <section aria-labelledby="home-ready" data-home-ready>
      <SectionHead id="home-ready" right={more ? seeAll : undefined}>
        Ready to run
      </SectionHead>
      {!loaded ? (
        <Loading />
      ) : (
        <ul className="m-0 grid list-none p-0" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(196px, 1fr))', gap: 14 }}>
          {ready.slice(0, 3).map((i, n) => {
            const t = tone[lessonTone(i.tools, i.id)]
            const Icon = lessonIcon(i.tools)
            return (
              <Rise key={i.id} as="li" i={n}>
                <Press large data-lesson={i.id} aria-label={`${i.title}. ${readyLine(i, done.has(i.id))}. Open its preview.`} onClick={() => openDetail(i.id)} className="mg-lift flex h-full w-full flex-col" style={{ ...CARD, padding: 0 }}>
                  <span aria-hidden className="relative flex items-end" style={{ height: 76, padding: 14, background: t.cover, color: t.coverFg, borderRadius: `${radius2.group}px ${radius2.group}px 0 0` }}>
                    <Icon size={22} strokeWidth={1.7} />
                  </span>
                  <span className="relative flex flex-1 flex-col gap-[4px]" style={{ padding: '12px 14px 14px' }}>
                    <span className="line-clamp-2 font-medium" style={{ fontSize: type2.sm, lineHeight: '18px', color: color.text }}>
                      {i.title}
                    </span>
                    <span style={caption}>{readyLine(i, done.has(i.id))}</span>
                  </span>
                </Press>
              </Rise>
            )
          })}
        </ul>
      )}
    </section>
  )
}

/** Finished = the one green check. In progress = a plain hollow ring, whole and still. */
function StateMark({ done }: { done: boolean }): ReactNode {
  return done ? <StatusGlyph state="passed" size={16} still /> : <span aria-hidden className="block shrink-0" style={{ width: 16, height: 16, borderRadius: radius2.round, boxShadow: `inset 0 0 0 1.5px ${fill.ring}` }} />
}

function Recents({ rows, now }: { rows: Recent[]; now: number }): ReactNode {
  if (!rows.length) return null
  return (
    <section aria-labelledby="home-recent" data-home-recent>
      <SectionHead id="home-recent">Recent</SectionHead>
      <ul className="m-0 flex list-none flex-col p-0" style={{ marginInline: -10 }}>
        {rows.map((r, i) => (
          <Rise key={r.key} as="li" i={i}>
            <Row onClick={r.libraryId ? () => openDetail(r.libraryId!) : undefined} label={`${r.title}. ${recentLine(r)}. Open its preview.`} data={{ 'data-recent': r.key }}>
              <span className="relative flex shrink-0" style={{ width: 30, justifyContent: 'center' }}>
                <StateMark done={r.done} />
              </span>
              <span className="relative flex min-w-0 flex-1 flex-col gap-[1px]">
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
            </Row>
          </Rise>
        ))}
      </ul>
    </section>
  )
}

/** Skills due for review, when the engine schedules them. One quiet Start review (disabled until review.start exists). */
function Review({ data, now }: { data?: DashData; now: number }): ReactNode {
  const due = (data?.review?.items ?? []).filter((r) => (r.dueAt === undefined ? !!r.when : r.dueAt <= now))
  if (!due.length) return null
  const can = canReview()
  const t = tone.mint
  return (
    <section aria-labelledby="home-review" data-home-review>
      <SectionHead
        id="home-review"
        right={
          <Ring>
            <QuietButton label="Start review" icon={RotateCcw} disabled={!can} title={can ? undefined : 'miyagi can’t start reviews yet'} onClick={() => startReview(due[0], 'library')} />
          </Ring>
        }
      >
        Review
      </SectionHead>
      <ul className="m-0 flex list-none flex-col p-0" style={{ marginInline: -10 }}>
        {due.slice(0, 3).map((r: ReviewEntry, i) => (
          <Rise key={`${r.label}-${i}`} as="li" i={i}>
            <Row data={{ 'data-review': r.label }}>
              <span aria-hidden className="inline-flex shrink-0 items-center justify-center" style={{ width: 30, height: 30, borderRadius: radius2.control, background: t.bg, color: t.fg }}>
                <RotateCcw size={14} strokeWidth={1.8} />
              </span>
              <span className="flex min-w-0 flex-1 flex-col gap-[1px]">
                <span className="truncate" style={{ fontSize: type2.sm, color: color.text }}>
                  {r.label.split(String.fromCharCode(96)).join('')}
                </span>
                <span style={caption}>{[r.track, r.dueAt !== undefined ? `Due ${relInLine(r.dueAt, now)}` : r.when].filter(Boolean).join(' · ')}</span>
              </span>
            </Row>
          </Rise>
        ))}
      </ul>
    </section>
  )
}

/** Lessons in progress besides the one on Continue (rows, each with its step bar and a quiet Resume). */
function AlsoInProgress({ conts, items, skip, title = 'Also in progress' }: { conts: Cont[]; items: LibraryItem[]; skip?: string; title?: string }): ReactNode {
  const rest = conts.filter((c) => c.libraryId !== skip).slice(0, 3)
  if (!rest.length) return null
  return (
    <section aria-labelledby="home-also" data-home-also>
      <SectionHead id="home-also">{title}</SectionHead>
      <ul className="m-0 flex list-none flex-col p-0" style={{ marginInline: -10 }}>
        {rest.map((c, i) => {
          const it = items.find((x) => x.id === c.libraryId)
          return (
            <Rise key={c.key} as="li" i={i}>
              <Row onClick={() => openDetail(c.libraryId)} label={`${c.title}. Step ${c.stepIndex + 1} of ${c.total}. Open its preview.`} data={{ 'data-cont': c.libraryId }}>
                <span className="relative flex">
                  <LessonTile tools={it?.tools} id={c.libraryId} size={30} />
                </span>
                <span className="relative flex min-w-0 flex-1 flex-col gap-[1px]">
                  <span className="truncate font-medium" style={{ fontSize: type2.sm, color: color.text }}>
                    {c.title}
                  </span>
                  <span style={caption}>{`Step ${c.stepIndex + 1} of ${c.total}${c.stepTitle ? ` · ${c.stepTitle}` : ''}`}</span>
                </span>
                <span className="relative hidden @[560px]:flex">
                  <StepBar done={c.passed} total={c.total} width={96} />
                </span>
              </Row>
            </Rise>
          )
        })}
      </ul>
    </section>
  )
}

// ---- layout a: cover --------------------------------------------------------------------------------------------

function ContinueCard({ view, hero, fix }: { view: View; hero: Hero; fix?: Fix }): ReactNode {
  const t = tone[lessonTone(view.tools, view.id)]
  const Icon = lessonIcon(view.tools)
  return (
    <section aria-labelledby="home-continue" data-home-hero={hero.kind}>
      <SectionHead>{view.head}</SectionHead>
      <div className="flex items-stretch" style={{ ...CARD, padding: 16, gap: 20 }}>
        <span aria-hidden className="hidden shrink-0 items-center justify-center @[520px]:flex" style={{ width: 124, borderRadius: radius2.card, background: view.blocked ? fill.tile : t.cover, color: view.blocked ? color.label : t.coverFg }}>
          {view.blocked ? <MiyagiMark size={40} /> : <Icon size={40} strokeWidth={1.5} />}
        </span>
        <div className="flex min-w-0 flex-1 flex-col" style={{ padding: '6px 4px 4px 0' }}>
          <h2 id="home-continue" className="m-0 line-clamp-2 font-semibold" style={{ fontSize: type2.xl, lineHeight: '26px', letterSpacing: '-0.01em', color: color.text }}>
            {view.title}
          </h2>
          {view.line && <span style={{ marginTop: 4, fontSize: type2.sm, color: color.label }}>{view.line}</span>}
          {!view.blocked && view.total ? (
            <div style={{ marginTop: 14 }}>
              <StepBar done={view.done ?? 0} total={view.total} width={220} />
            </div>
          ) : null}
          <div className="flex flex-wrap items-center gap-[10px]" style={{ marginTop: 18 }}>
            <ContAction hero={hero} fix={fix} size="md" />
            <span className="ml-auto flex gap-[6px]">
              {view.tools.map((x) => (
                <ToolTag key={x} tool={x} />
              ))}
            </span>
          </div>
        </div>
      </div>
    </section>
  )
}

function LookA(p: LookProps): ReactNode {
  const { view, hero, fix, conts, items, skip, done, data, now, recent } = p
  return (
    <div className="mx-auto flex w-full flex-col" style={{ maxWidth: 780, padding: '28px 40px 56px', gap: 36 }}>
      {view === 'loading' ? <Loading /> : view && <ContinueCard view={view} hero={hero} fix={fix} />}
      <Ask size="md" primary={!view || view === 'loading'} />
      <AlsoInProgress conts={conts} items={items} skip={view && view !== 'loading' ? view.id : undefined} />
      <ReadyGallery skip={skip} done={done} />
      <Review data={data} now={now} />
      <Recents rows={recent} now={now} />
    </div>
  )
}

// ---- layout b: ask first ------------------------------------------------------------------------------------------

function ContinueRow({ view, hero, fix }: { view: View; hero: Hero; fix?: Fix }): ReactNode {
  return (
    <section aria-labelledby="home-continue" data-home-hero={hero.kind}>
      <SectionHead>{view.head}</SectionHead>
      <div className="flex items-center" style={{ ...CARD, padding: '14px 14px 14px 16px', gap: 14 }}>
        {view.blocked ? (
          <span className="inline-flex shrink-0 items-center justify-center" style={{ width: 44, height: 44, borderRadius: radius2.card, background: fill.tile }}>
            <MiyagiMark size={22} />
          </span>
        ) : (
          <LessonTile tools={view.tools} id={view.id} size={44} />
        )}
        <div className="flex min-w-0 flex-1 flex-col gap-[6px]">
          <h2 id="home-continue" className="m-0 truncate font-semibold" style={{ fontSize: type2.body, color: color.text }}>
            {view.title}
          </h2>
          <div className="flex items-center gap-[12px]">
            {!view.blocked && view.total ? <StepBar done={view.done ?? 0} total={view.total} width={110} /> : null}
            {view.line && (
              <span className="truncate" style={caption}>
                {view.line}
              </span>
            )}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-[10px]">
          <ContAction hero={hero} fix={fix} size="md" />
        </div>
      </div>
    </section>
  )
}

function LookB(p: LookProps): ReactNode {
  const { view, hero, fix, conts, items, skip, done, data, now, recent } = p
  return (
    <div className="mx-auto flex w-full flex-col" style={{ maxWidth: 680, padding: '0 40px 56px', gap: 34 }}>
      <div className="flex flex-col items-center" style={{ paddingTop: 'clamp(28px, 8vh, 84px)', gap: 18 }}>
        <MiyagiMark size={44} />
        <div className="w-full">
          <Ask size="lg" center primary={!view || view === 'loading'} />
        </div>
      </div>
      {view === 'loading' ? <Loading /> : view && <ContinueRow view={view} hero={hero} fix={fix} />}
      <AlsoInProgress conts={conts} items={items} skip={view && view !== 'loading' ? view.id : undefined} />
      <ReadyRows skip={skip} done={done} max={3} />
      <Review data={data} now={now} />
      <Recents rows={recent} now={now} />
    </div>
  )
}

// ---- layout c: lists ----------------------------------------------------------------------------------------------

function ContinueList({ view, hero, fix, conts, items }: { view: View; hero: Hero; fix?: Fix; conts: Cont[]; items: LibraryItem[] }): ReactNode {
  const rest = conts.filter((c) => c.libraryId !== view.id).slice(0, 2)
  const big: CSSProperties = { padding: '12px 10px' }
  return (
    <section aria-labelledby="home-continue" data-home-hero={hero.kind}>
      <SectionHead id="home-continue">{view.head}</SectionHead>
      <ul className="m-0 flex list-none flex-col p-0" style={{ marginInline: -10 }}>
        <Rise as="li" i={0}>
          <Row style={big}>
            {view.blocked ? (
              <span className="inline-flex shrink-0 items-center justify-center" style={{ width: 36, height: 36, borderRadius: radius2.control, background: fill.tile }}>
                <MiyagiMark size={18} />
              </span>
            ) : (
              <LessonTile tools={view.tools} id={view.id} size={36} />
            )}
            <span className="flex min-w-0 flex-1 flex-col gap-[2px]">
              <span className="truncate font-semibold" style={{ fontSize: type2.body, color: color.text }}>
                {view.title}
              </span>
              {view.line && <span style={caption}>{view.line}</span>}
            </span>
            {!view.blocked && view.total ? (
              <span className="hidden @[600px]:flex">
                <StepBar done={view.done ?? 0} total={view.total} width={120} />
              </span>
            ) : null}
            <span className="flex shrink-0 items-center gap-[10px]">
              <ContAction hero={hero} fix={fix} size="md" />
            </span>
          </Row>
        </Rise>
        {rest.map((c, i) => {
          const it = items.find((x) => x.id === c.libraryId)
          return (
            <Rise key={c.key} as="li" i={i + 1}>
              <Row onClick={() => openDetail(c.libraryId)} label={`${c.title}. Open its preview.`} style={big}>
                <span className="relative flex">
                  <LessonTile tools={it?.tools} id={c.libraryId} size={36} />
                </span>
                <span className="relative flex min-w-0 flex-1 flex-col gap-[2px]">
                  <span className="truncate font-medium" style={{ fontSize: type2.body, color: color.text }}>
                    {c.title}
                  </span>
                  <span style={caption}>{`Step ${c.stepIndex + 1} of ${c.total}${c.stepTitle ? ` · ${c.stepTitle}` : ''}`}</span>
                </span>
                <span className="relative hidden @[600px]:flex">
                  <StepBar done={c.passed} total={c.total} width={120} />
                </span>
                <span className="relative flex shrink-0" style={{ width: 92 }} />
              </Row>
            </Rise>
          )
        })}
      </ul>
    </section>
  )
}

function LookC(p: LookProps): ReactNode {
  const { view, hero, fix, conts, items, skip, done, data, now, recent } = p
  return (
    <div className="mx-auto flex w-full flex-col" style={{ maxWidth: 820, padding: '28px 40px 56px', gap: 34 }}>
      <Ask size="sm" primary={!view || view === 'loading'} />
      {view === 'loading' ? <Loading /> : view && <ContinueList view={view} hero={hero} fix={fix} conts={conts} items={items} />}
      <div className="grid gap-x-[40px] gap-y-[34px] @[720px]:grid-cols-2">
        <ReadyRows skip={skip} done={done} max={4} />
        <div className="flex flex-col gap-[34px]">
          <Review data={data} now={now} />
          <Recents rows={recent} now={now} />
        </div>
      </div>
    </div>
  )
}

// ---- the page -----------------------------------------------------------------------------------------------------

type LookProps = {
  view: View | null | 'loading'
  hero: Hero
  fix?: Fix
  conts: Cont[]
  items: LibraryItem[]
  skip: Set<string>
  done: Set<string>
  data?: DashData
  now: number
  recent: Recent[]
}

const LOOKS: Record<Look, (p: LookProps) => ReactNode> = { a: LookA, b: LookB, c: LookC }

export function Home(): ReactNode {
  const { data, load, now } = useDashView()
  const hero = useHero(data, load === 'loading')
  const connected = useLesson((s) => s.connected)
  const items = useLibrary((s) => s.items)
  const rows = useRows()
  const sum = summarize(rows)
  const fix = sum.canStart ? undefined : setupFix(rows)
  const offline = !connected && !data && load !== 'loading'
  const conts = continueList(data, items)
  const view = useView(hero, fix, conts, items)
  const skip = new Set(conts.map((c) => c.libraryId))
  if (hero.kind === 'resume' || hero.kind === 'fresh') skip.add(hero.id)
  const Look = LOOKS[homeLook()]
  return (
    <div data-home data-home-look={homeLook()} className="@container flex min-h-0 flex-1 flex-col overflow-y-auto" style={{ color: color.text }}>
      {offline && (
        <p role="status" data-home-offline className="m-0 mx-auto flex w-full items-center gap-[8px]" style={{ ...caption, maxWidth: 780, padding: '12px 40px 0' }}>
          <CloudOff aria-hidden size={14} strokeWidth={1.8} />
          {copy.name} is offline. Your lessons show when it connects.
        </p>
      )}
      <Look view={view} hero={hero} fix={fix} conts={conts} items={items} skip={skip} done={finishedIds(data)} data={data} now={now} recent={load === 'loading' ? [] : recentActivity(data)} />
    </div>
  )
}

/**
 * Feature: library. Home, the home window's first page (redraft, Adrian Nov 21). Sleek and minimal: type, spacing and
 * one raised surface do the work. Monochrome chrome; the only hues are the suggestion chips (options, BRAND.md) and the
 * green check (passed). No icon tiles, no tool pills on rows, no title, greeting, date or stat boxes. Parts with nothing
 * to show are left out.
 *
 *   continue  the ONE most recent unfinished lesson: title, where it stands, its steps, one primary button. When setup
 *             is left that button is the one setup action instead ("Turn on Accessibility"), never a disabled Continue.
 *   ask       "ask miyagi anything" with three suggestion chips (a goal or a pasted YouTube link, homeModel.ts)
 *   up next   three lessons saved on this Mac, as plain rows
 *   review    one row when skills are due, with Start review
 *   recent    one row per lesson, newest state: a green check when finished, a hueless ring while in progress
 *
 * Layout (Adrian picked A, Nov 21, with the bonsai centered on top): the bonsai, Continue on the page's one lifted card,
 * the ask field under it, then plain lists.
 *
 * Continue comes from dashboard/continue.ts, the same list Lessons and Progress read.
 */
import { ArrowRight, ChevronRight, CloudOff, Play, RotateCcw } from 'lucide-react'
import { motion } from 'motion/react'
import { useRef, useState, type ReactNode } from 'react'
import { useShallow } from 'zustand/react/shallow'
import type { LibraryItem } from '../../../../../../shared/contracts/events'
import { useLesson, useProgress as useLessonProgress } from '../../core/lesson'
import { closeWindow, openOnboarding } from '../../core/surfaces'
import { useAppearance } from '../../core/prefs'
import { color, copy, elevation, fill, highlight, layer, radius2, surface, tone, type Tone, type2 } from '../../core/theme'
import { Spinner } from '../../core/ui/atoms'
import { PrimaryButton, QuietButton } from '../../core/ui/buttons'
import { Keycap } from '../../core/ui/Keycap'
import { MiyagiMark } from '../../core/ui/Mark'
import { enter, press } from '../../core/ui/motion'
import { StatusGlyph } from '../../core/ui/status'
import { continueList, type Cont } from '../dashboard/continue'
import { useDashView } from '../dashboard/Dashboard'
import { groupTracks, nodeStates, relDay } from '../dashboard/model'
import { canReview, startReview, useDash } from '../dashboard/store'
import type { DashData } from '../dashboard/types'
import { summarize, useRows } from '../onboarding/rows'
import { Row, RowChevron, TextAction, caption } from '../shell/ui'
import { finishedIds, pickHero, readAsk, recentActivity, recentLine, setAskText, setupFix, submitAsk, useAsk, type Hero, type Recent } from './homeModel'
import { Column, Pane, SectionLabel, firstLine, rhythm } from './layout'
import { Press, Ring, Rise } from './motion'
import { ProgressRing, Skeleton, TOOL_NAME, minutesLabel, stepsLabel } from './parts'
import { ActivityCard } from './homeActivity'
import { Rail } from './homeRail'
import { PacksRow } from './presets/PresetLibraries'
import { openDetail, setSection, start, useLibrary } from './store'
import { setPage } from '../shell/store'
import { LessonSkills } from '../skills/extras/SkillChips'

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
type View = { head: string; title: string; line: string; id: string; blocked: boolean; done?: number; total?: number }

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
  return { head, title, line, id, blocked, done, total }
}

/** The one primary action for the Continue part, and its quiet notes. */
function ContAction({ hero, fix, size = 'md' }: { hero: Hero; fix?: Fix; size?: 'md' | 'lg' }): ReactNode {
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

/** Suggestion chips are options, so they keep their pastels (BRAND.md); they are the page's only color. */
const IDEAS: Array<{ text: string; tone: Tone }> = [
  { text: 'Clean a messy CSV with pandas', tone: 'sky' },
  { text: 'Build a tiny web server', tone: 'lilac' },
  { text: 'Train an image classifier', tone: 'pink' }
]
const IDEA_TONES: Tone[] = ['sky', 'lilac', 'pink']

/**
 * The chips, personal first (Adrian: "should eventually be personalized based on the lessons"): the skills the
 * learner is ready for next (every prerequisite mastered, not started yet), named with their track ("Broadcasting in
 * numpy"), from the same progress data as the Skills page. Topped up with the general ideas, always three.
 */
function pickIdeas(data: DashData | undefined): Array<{ text: string; tone: Tone }> {
  const mine: string[] = []
  for (const g of groupTracks(data)) {
    const st = nodeStates(g.track)
    const where = g.kicker ?? g.track.track
    for (const s of g.track.skills) {
      if (st[s.id] !== 'available') continue
      const label = s.label.split(String.fromCharCode(96)).join('')
      const text = label.toLowerCase().includes(where.toLowerCase()) ? label : `${label} in ${where}`
      if (!mine.includes(text)) mine.push(text)
    }
  }
  const texts = [...mine.slice(0, 3), ...IDEAS.map((i) => i.text)].slice(0, 3)
  return texts.map((text, i) => ({ text, tone: IDEA_TONES[i % IDEA_TONES.length] }))
}

/**
 * Ask (redraft round 2): one surface, the field on top and the chips centered under it inside the same frame, so the
 * suggestions read as part of the ask. The field is taller, led by the bonsai, with a clearer edge and placeholder,
 * and the frame lights up on focus, so it reads as a place to type.
 */
function Ask({ primary = false, data }: { primary?: boolean; data?: DashData }): ReactNode {
  const ask = useAsk()
  const items = useLibrary((s) => s.items)
  const canStart = useLibrary((s) => s.caps.start)
  const connected = useLesson((s) => s.connected)
  const input = useRef<HTMLInputElement>(null)
  const [focused, setFocused] = useState(false)
  const light = useAppearance() === 'light'
  const [hovered, setHovered] = useState(false)
  const read = readAsk(ask.text, items, canStart)
  const ideas = pickIdeas(data)
  const go = (): void => {
    if (!submitAsk(connected) && !useAsk.getState().sending) input.current?.focus()
  }
  const Btn = primary ? PrimaryButton : QuietButton
  const actionLabel = read.kind === 'link' ? (read.match ? 'Start lesson' : 'Build lesson') : 'Teach me'
  const h = 52
  return (
    <section
      aria-label="Learn something new"
      data-home-ask
      className="flex flex-col overflow-hidden"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      // The same lifted surface as the Continue card (one card treatment on the page, light and dark), radius 12. Its
      // edge brightens on hover and turns into a 2px ring of the text color on focus (never an accent hue).
      style={{ background: SURFACE_BG, borderRadius: radius2.card, boxShadow: surfaceShadow(light, `inset 0 0 0 ${focused ? 2 : 1}px ${focused ? color.faint : hovered ? fill.ring : surface.border}`), transition: 'box-shadow 140ms ease' }}
    >
      <form
        className="flex cursor-text items-center gap-[12px]"
        style={{ height: h, padding: '0 8px 0 16px' }}
        onClick={() => input.current?.focus()}
        onSubmit={(e) => {
          e.preventDefault()
          go()
        }}
      >
        <span aria-hidden className="flex shrink-0">
          <MiyagiMark size={18} />
        </span>
        <input
          ref={input}
          aria-label={copy.launcherPlaceholder}
          placeholder={copy.launcherPlaceholder}
          autoComplete="off"
          spellCheck={false}
          value={ask.text}
          disabled={!!ask.sending}
          onChange={(e) => setAskText(e.target.value)}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          className="min-w-0 flex-1 bg-transparent outline-none placeholder:text-[var(--c-label)]"
          style={{ fontSize: type2.body, color: color.text }}
        />
        {read.kind === 'idle' ? (
          <span className="flex shrink-0 items-center" style={{ paddingRight: 4 }}>
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
            style={{ width: 36, height: 36, borderRadius: radius2.control, background: color.accent, color: color.onAccent }}
          >
            {ask.sending ? <Spinner size={13} c={color.onAccent} /> : <ArrowRight size={15} strokeWidth={2} aria-hidden />}
          </motion.button>
        )}
      </form>
      {/* Left-aligned like the input above it (text in the column never centers): the first chip's edge is the bonsai's. */}
      <div className="flex flex-wrap items-center justify-start gap-[8px]" style={{ padding: '12px 16px', minHeight: 56, borderTop: `1px solid ${fill.hairline}` }}>
        {read.kind === 'idle' ? (
          ideas.map((t) => (
            <Press
              key={t.text}
              data-idea
              onClick={() => {
                setAskText(t.text)
                input.current?.focus()
              }}
              className="flex items-center"
              style={{ height: 32, padding: '0 12px', borderRadius: radius2.round, background: tone[t.tone].bg, fontSize: type2.sm, color: tone[t.tone].fg }}
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

// ---- lists ----------------------------------------------------------------------------------------------------------

const list = { margin: 0, padding: 0, listStyle: 'none', marginInline: -10 } as const
const titleText = { fontSize: type2.md, color: color.text } as const

function useUpNext(skip: Set<string>, done: Set<string>): { loaded: boolean; ready: LibraryItem[]; more: boolean } {
  const loaded = useLibrary((s) => s.loaded)
  const items = useLibrary((s) => s.items)
  const ready = items.filter((i) => i.ready && !i.progress && !skip.has(i.id) && !done.has(i.id))
  return { loaded, ready, more: items.length > 3 }
}

/** "Jupyter · 6 steps · 15 min": the tool in words, never a pill. */
const lessonLine = (i: LibraryItem): string => [i.tools.map((t) => TOOL_NAME[t]).join(', '), stepsLabel(i.steps), minutesLabel(i.estMinutes)?.replace('About ', '')].filter(Boolean).join(' · ')

function UpNext({ skip, done }: { skip: Set<string>; done: Set<string> }): ReactNode {
  const { loaded, ready, more } = useUpNext(skip, done)
  if (loaded && !ready.length) return null
  return (
    <section aria-labelledby="home-next" data-home-ready>
      <SectionLabel id="home-next" right={
          more ? (
            // The rows' chevrons sit on the column's right edge (16 px, the row's 10 px inset under a -10 list); the
            // link steps out by its own 8 px padding and uses the same 16 px chevron, so every chevron shares one edge.
            <span className="flex" style={{ marginRight: -8 }}>
              <TextAction onClick={() => setSection('library')}>
                All lessons
                <ChevronRight aria-hidden size={16} strokeWidth={1.8} />
              </TextAction>
            </span>
          ) : undefined
        }>
        Up next
      </SectionLabel>
      {!loaded ? (
        <Loading />
      ) : (
        <ul style={list}>
          {ready.slice(0, 3).map((i, n) => (
            <Rise key={i.id} as="li" i={n}>
              <Row onClick={() => openDetail(i.id)} label={`${i.title}. ${lessonLine(i)}. Open its preview.`} data={{ 'data-lesson': i.id }}>
                <span className="relative flex min-w-0 flex-1 flex-col gap-[2px]">
                  <span className="truncate" style={titleText}>
                    {i.title}
                  </span>
                  <span className="truncate" style={caption}>
                    {lessonLine(i)}
                  </span>
                  <LessonSkills item={i} />
                </span>
                <RowChevron />
              </Row>
            </Rise>
          ))}
        </ul>
      )}
    </section>
  )
}

/** Finished = the one green check. In progress = a plain hollow ring, whole and still. */
function StateMark({ done }: { done: boolean }): ReactNode {
  return done ? <StatusGlyph state="passed" size={14} still /> : <span aria-hidden className="block shrink-0" style={{ width: 14, height: 14, borderRadius: radius2.round, boxShadow: `inset 0 0 0 1.5px ${fill.ring}` }} />
}

function Recents({ rows, now, max = 4 }: { rows: Recent[]; now: number; max?: number }): ReactNode {
  if (!rows.length) return null
  return (
    <section aria-labelledby="home-recent" data-home-recent>
      <SectionLabel id="home-recent">Recent</SectionLabel>
      <ul style={list}>
        {rows.slice(0, max).map((r, i) => (
          <Rise key={r.key} as="li" i={i}>
            <Row onClick={r.libraryId ? () => openDetail(r.libraryId!) : undefined} label={`${r.title}. ${recentLine(r)}. Open its preview.`} data={{ 'data-recent': r.key }}>
              <span className="relative flex shrink-0">
                <StateMark done={r.done} />
              </span>
              <span className="relative min-w-0 flex-1 truncate" style={titleText}>
                {r.title}
              </span>
              {r.at && (
                <span className="relative shrink-0" style={{ fontSize: type2.xs, color: color.faint, fontVariantNumeric: 'tabular-nums' }}>
                  {relDay(r.at, now)}
                </span>
              )}
              {r.libraryId && <RowChevron />}
            </Row>
          </Rise>
        ))}
      </ul>
    </section>
  )
}

/** One row when skills are due: what they are; it opens Progress (where review lives). Review shows only once the engine can. */
function ReviewLine({ data, now }: { data?: DashData; now: number }): ReactNode {
  const due = (data?.review?.items ?? []).filter((r) => (r.dueAt === undefined ? !!r.when : r.dueAt <= now))
  if (!due.length) return null
  const can = canReview()
  const names = due.map((r) => r.label.split(String.fromCharCode(96)).join(''))
  const title = due.length === 1 ? 'One skill to review' : `${due.length} skills to review`
  return (
    <section aria-labelledby="home-review" data-home-review>
      <SectionLabel id="home-review">Review</SectionLabel>
      <div className="flex items-center gap-[12px]" style={{ marginInline: -10 }}>
        <Row onClick={() => setPage('progress')} label={`${title}: ${names.join(', ')}. Open Progress.`} style={{ flex: 1, minWidth: 0 }}>
          <RotateCcw aria-hidden size={15} strokeWidth={1.8} className="relative shrink-0" style={{ color: color.label }} />
          <span className="relative flex min-w-0 flex-1 flex-col gap-[2px]">
            <span style={titleText}>{title}</span>
            <span className="truncate" style={caption}>
              {names.slice(0, 3).join(', ')}
            </span>
          </span>
          <RowChevron />
        </Row>
        {can && (
          <Ring>
            <QuietButton label="Start review" onClick={() => startReview(due[0], 'library')} />
          </Ring>
        )}
      </div>
    </section>
  )
}

// ---- the continue card ----------------------------------------------------------------------------------

/** "Step 4 of 7 · Train it" → the count for the top line and the step's own title for the line under the title. */
function splitLine(line: string): { count?: string; sub: string } {
  const m = /^(Step \d+ of \d+)(?: · (.+))?$/.exec(line)
  return m ? { count: m[1], sub: m[2] ?? '' } : { sub: line }
}

/**
 * The page's surface for its two cards (Continue, the ask box): the overlay layer (white in light), the top highlight
 * and a hairline. One treatment, so Home never shows a white card over a gray well. The soft raised shadow is light
 * only (spec section 8: dark cards get a border and the top highlight, no drop shadow).
 */
const SURFACE_BG = layer.overlay.background
const surfaceShadow = (light: boolean, edge = `inset 0 0 0 1px ${surface.border}`): string => [highlight.topSoft, edge, light ? elevation.raised : ''].filter(Boolean).join(', ')

/**
 * The one lifted card on the page (redraft round 2, Adrian: "the continue tab doesn't look that good"). One row: where
 * you are on the left (Continue · Step 4 of 7, the lesson, the step you're on), the one action on the right, and the
 * lesson's progress as a hairline along the card's bottom edge instead of a row of dashes. Wraps under a narrow window.
 * Layout spec: radius 16, padding 24, title 17/24 semibold.
 */
function ContinueCard({ view, hero, fix }: { view: View; hero: Hero; fix?: Fix }): ReactNode {
  const { count, sub } = splitLine(view.line)
  // Building (round 3): the status sits under the title with the spinner, the build's own progress rides the bottom
  // edge, and there is no right-hand column (nothing to press until it is ready; the island shows each stage).
  const building = hero.kind === 'building'
  const clamp = (n: number): number => Math.max(0, Math.min(1, n))
  const light = useAppearance() === 'light'
  const frac = building ? (hero.fraction !== undefined ? clamp(hero.fraction) : undefined) : !view.blocked && view.total ? clamp((view.done ?? 0) / view.total) : undefined
  return (
    <section aria-labelledby="home-continue" data-home-hero={hero.kind} className="relative flex flex-col overflow-hidden" style={{ background: SURFACE_BG, boxShadow: surfaceShadow(light), borderRadius: radius2.group, padding: 24 }}>
      <div className="flex flex-wrap items-center gap-x-[20px] gap-y-[16px]">
        {!building && frac !== undefined && (
          <ProgressRing fraction={frac} size={56} label={count ?? `${view.done ?? 0} of ${view.total} steps`}>
            <span className="font-semibold" style={{ fontSize: type2.sm, color: color.text, fontVariantNumeric: 'tabular-nums' }}>
              {view.done ?? 0}/{view.total}
            </span>
          </ProgressRing>
        )}
        <div className="flex min-w-0 flex-1 flex-col" style={{ minWidth: 240 }}>
          <span className="flex items-center gap-[6px]" style={caption}>
            <span>{view.head}</span>
            {count && (
              <>
                <span aria-hidden>·</span>
                <span style={{ fontVariantNumeric: 'tabular-nums' }}>{count}</span>
              </>
            )}
          </span>
          <h2 id="home-continue" className="m-0 line-clamp-2 font-semibold" style={{ marginTop: 4, fontSize: type2.lg, lineHeight: '24px', letterSpacing: '-0.2px', color: color.text }}>
            {view.title}
          </h2>
          {sub && (
            <span className="flex min-w-0 items-center gap-[8px]" style={{ marginTop: building ? 8 : 4, fontSize: type2.sm, lineHeight: '18px', color: color.label }}>
              {building && <Spinner size={12} c={color.label} />}
              <span className="truncate">{sub}</span>
            </span>
          )}
        </div>
        {!building && (
          <div className="flex shrink-0 flex-col items-end gap-[8px]">
            <ContAction hero={hero} fix={fix} />
          </div>
        )}
      </div>
      {building && frac !== undefined && (
        <div role="img" aria-label={count ?? `${view.done ?? 0} of ${view.total} steps`} className="absolute inset-x-0 bottom-0" style={{ height: 3, background: fill.hairline }}>
          <div style={{ width: `${frac * 100}%`, height: '100%', background: color.text, borderRadius: `0 ${radius2.round}px ${radius2.round}px 0` }} />
        </div>
      )}
    </section>
  )
}

// ---- the page body ----------------------------------------------------------------------------------------------

type BodyProps = { goal: number; view: View | null | 'loading'; hero: Hero; fix?: Fix; skip: Set<string>; done: Set<string>; data?: DashData; now: number; recent: Recent[] }

/** The shell's drag strip above Home (Shell.tsx Header: Home has no title, only a 20 px strip) plus the panel inset. */
const SHELL_STRIP = 20 + 8

/**
 * One centered column (layout spec, Nov 22), top-anchored, never centered vertically. The bonsai, Continue and the ask
 * read as one group (12 apart); the lists sit 40 under it and 40 apart. The bonsai's top is 80 from the window's top,
 * where every other page's title sits. The same 720 column at every window size (layout.tsx).
 */
function Body({ goal, view, hero, fix, skip, done, data, now, recent }: BodyProps): ReactNode {
  return (
    <Column wide data-home-column className="mg-first-line" style={{ ...firstLine(SHELL_STRIP), paddingBottom: rhythm.bottom }}>
      {/* Wide pane: the dashboard (main column + a 300 side column). Narrow: one column, the side cards under the lists. */}
      <div className="grid grid-cols-1 gap-x-[32px] gap-y-[40px] @min-[940px]/pane:grid-cols-[minmax(0,1fr)_300px]">
        <div className="flex min-w-0 flex-col" style={{ gap: rhythm.section }}>
          <div data-home-main className="flex min-w-0 flex-col" style={{ gap: 12 }}>
            <div className="flex justify-center @min-[940px]/pane:hidden" style={{ paddingBottom: 12 }}>
              <MiyagiMark size={32} />
            </div>
            {view === 'loading' ? <Loading /> : view && <ContinueCard view={view} hero={hero} fix={fix} />}
            <Ask primary={!view || view === 'loading'} data={data} />
          </div>
          <div data-home-lists className="flex min-w-0 flex-col empty:hidden" style={{ gap: rhythm.section }}>
            <ReviewLine data={data} now={now} />
            <UpNext skip={skip} done={done} />
            <PacksRow />
            <Recents rows={recent} now={now} />
            <ActivityCard data={data} now={now} />
          </div>
        </div>
        <Rail data={data} now={now} goal={goal} />
      </div>
    </Column>
  )
}

// ---- the page -----------------------------------------------------------------------------------------------------

export function Home(): ReactNode {
  const { data, load, now, goals } = useDashView()
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
  return (
    <Pane data-home className="flex flex-1 flex-col overflow-y-auto" style={{ color: color.text, scrollbarWidth: 'thin', scrollbarColor: `${fill.track} transparent` }}>
      {offline && (
        <Column>
          <p role="status" data-home-offline className="m-0 flex items-center gap-[8px]" style={{ ...caption, paddingTop: 12 }}>
            <CloudOff aria-hidden size={14} strokeWidth={1.8} />
            {copy.name} is offline. Your lessons show when it connects.
          </p>
        </Column>
      )}
      <Body goal={goals.daily} view={view} hero={hero} fix={fix} skip={skip} done={finishedIds(data)} data={data} now={now} recent={load === 'loading' ? [] : recentActivity(data)} />
    </Pane>
  )
}

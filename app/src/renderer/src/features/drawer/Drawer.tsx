/**
 * Feature: drawer. The slim tab on the right edge and the lesson drawer it opens: every step as done /
 * current / locked (the current one with its live checks), a quiet "More steps coming" row while a long
 * video is still building part by part, and the lesson's sources.
 *
 * A "Just teach me" lesson adds, top to bottom (Teach.tsx): what we're building, "Before you start", the plan
 * (one line per step from steps[].what), and inside the current step the full code to type with Copy, why,
 * and its concepts.
 *
 * Appended steps (lesson.updated) fade in; rows already on screen never re-animate: a row only gets an
 * entrance when its id wasn't there when the drawer opened. (AnimatePresence initial={false} would do that
 * too, but it also blocks every motion that mounts later inside those rows, like the green tick drawing in.)
 */
import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode, type RefObject } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { ArrowUpRight, FileCode2, FileText, FolderGit2, Newspaper, X, type LucideIcon } from 'lucide-react'
import type { Source, SourceKind, StepSummary } from '../../../../../../shared/contracts/events'
import { builtByLabel, seekVideo, useLesson, useProgress, type CheckItem, type Rect } from '../../core/lesson'
import { useAppearance } from '../../core/prefs'
import { alpha, clock, color, glass, kindTone, radius, spring, springOut } from '../../core/theme'
import { Thumb } from '../../core/ui/atoms'
import { GlassCheck, GlassSpinner } from '../../core/ui/glass'
import { parseYouTube, thumbnailFor } from '../launcher/youtube'
import { TAB } from './geometry'
import { closeDrawer, isWebLink, openSource, setPanelHeight, toggleDrawer } from './store'
import { BuildStrip, minutesLeft, NeedsChip, OverviewText, PrimerSection, StepDetail } from './Teach'

/** skipped: the learner pressed Skip. Done, but not passed, so never green. */
type StepStatus = 'done' | 'skipped' | 'current' | 'locked'

/** Row geometry: icon column, gap, time column. The current step's checks line up with its title. */
const ROW = { h: 38, padX: 10, icon: 18, gap: 11 } as const
/**
 * Every color is a glass token (theme.glass: CSS variables that flip with Settings → Appearance), never color.* /
 * fill.* (those are the black island's). Hover goes through a CSS variable so it stays a token too.
 */
const hoverVar = { '--drawer-hover': glass.field } as CSSProperties
const hoverCls = 'hover:bg-[var(--drawer-hover)]'

// ---------------------------------------------------------------------------
// Tab
// ---------------------------------------------------------------------------

/** 4×40 at glass.track, inside a wider hit box. Hover stretches the bar a little (transform only). */
export function Tab({ rect, shown }: { rect: Rect; shown: boolean }): ReactNode {
  const [hover, setHover] = useState(false)
  return (
    <AnimatePresence>
      {shown && (
        <motion.button
          key="drawer-tab"
          type="button"
          data-hit
          data-part="drawer-tab"
          aria-label="Lesson steps"
          className="absolute cursor-pointer"
          style={{ left: rect.x, top: rect.y, width: rect.w, height: rect.h }}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.18 }}
          onHoverStart={() => setHover(true)}
          onHoverEnd={() => setHover(false)}
          onMouseDown={(e) => e.preventDefault()}
          onClick={toggleDrawer}
        >
          <motion.span
            className="absolute rounded-full"
            style={{ right: TAB.edge, top: (rect.h - TAB.h) / 2, width: TAB.w, height: TAB.h, background: glass.track }}
            animate={{ scaleX: hover ? 1.5 : 1, scaleY: hover ? 1.15 : 1 }}
            transition={spring}
          />
        </motion.button>
      )}
    </AnimatePresence>
  )
}

// ---------------------------------------------------------------------------
// Panel
// ---------------------------------------------------------------------------

export function Panel({ rect }: { rect: Rect }): ReactNode {
  const lesson = useLesson((s) => s.lesson)
  const hasStep = useLesson((s) => !!s.stepId)
  const progress = useProgress()
  // Mockup 01: "about N min left" next to "Step N of M" (steps[].estMinutes over the steps not done yet).
  const left = useLesson((s) => minutesLeft(s.steps, [...s.passed, ...s.skipped]))
  const scroller = useRef<HTMLDivElement>(null)
  const box = useRef<HTMLDivElement>(null)
  const by = builtByLabel(lesson?.builtBy, lesson?.mode)
  const sources = lesson?.sources ?? []
  const overview = lesson?.overview?.trim()
  // A hairline under the header once the list scrolls, so text doesn't run straight into the title.
  const [scrolled, setScrolled] = useState(false)
  const away = rect.w + 24
  // The panel hugs its content (up to rect.h, then the list scrolls). Report the real height so the
  // spotlight check covers only what's on screen. offsetHeight ignores the slide's transform.
  useLayoutEffect(() => {
    const el = box.current
    if (!el) return
    const report = (): void => setPanelHeight(el.offsetHeight)
    report()
    const ro = new ResizeObserver(report)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  return (
    <motion.div
      ref={box}
      data-hit
      data-part="drawer"
      className="absolute flex flex-col overflow-hidden border"
      style={{
        left: rect.x,
        top: rect.y,
        width: rect.w,
        maxHeight: rect.h,
        borderRadius: radius.card,
        background: glass.bg,
        borderColor: glass.hairline,
        // No blur (a window can't blur the windows under it), so at .9 alpha the player's video and text show
        // through. An inset layer of the same glass under the content makes it ~99% opaque, tokens only.
        boxShadow: `${glass.shadow}, inset 0 0 0 ${rect.w}px ${glass.bg}`,
        color: glass.text
      }}
      initial={{ x: away, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      exit={{ x: away, opacity: 0, transition: { ...springOut, opacity: { duration: 0.18 } } }}
      transition={{ ...spring, opacity: { duration: 0.18 } }}
    >
      <div
        className="flex shrink-0 items-start gap-[12px] border-b px-[18px] pb-[6px] pt-[16px]"
        style={{ borderColor: scrolled ? glass.rule : 'transparent', transition: 'border-color 150ms ease-out' }}
      >
        <div className="min-w-0 flex-1">
          <div className="line-clamp-2 text-[15px] font-semibold leading-[20px]">{lesson?.title ?? ''}</div>
          {by && (
            <div className="mt-[2px] truncate text-[12px] leading-[16px]" style={{ color: glass.faint }}>
              {by}
            </div>
          )}
        </div>
        <button
          type="button"
          className="mt-[-1px] grid h-[22px] w-[22px] shrink-0 cursor-pointer place-items-center rounded-full"
          style={{ background: glass.key, color: glass.keyText }}
          onMouseDown={(e) => e.preventDefault()}
          onClick={closeDrawer}
          aria-label="Close"
        >
          <X size={12} strokeWidth={2.2} />
        </button>
      </div>
      <div
        ref={scroller}
        className="relative min-h-0 flex-initial overflow-y-auto px-[8px] pb-[12px]"
        style={{ scrollbarWidth: 'thin', scrollbarColor: `${glass.track} transparent` }}
        onScroll={(e) => setScrolled(e.currentTarget.scrollTop > 2)}
      >
        {lesson?.build ? (
          <>
            <Label>What you're building</Label>
            <BuildStrip />
          </>
        ) : (
          overview && (
            <>
              <Label>What we're building</Label>
              <OverviewText text={overview} />
            </>
          )
        )}
        <NeedsChip />
        <PrimerSection />
        <Label>
          {progress.total > 0 && hasStep ? `Step ${progress.index + 1} of ${progress.total}` : 'Steps'}
          {left !== undefined && left > 0 && <span style={{ color: glass.faint }}>{` · about ${left} min left`}</span>}
        </Label>
        <Steps scroller={scroller} />
        {sources.length > 0 && (
          <>
            <Label>Sources</Label>
            {sources.map((s) => (
              <SourceRow key={s.id} source={s} />
            ))}
          </>
        )}
      </div>
    </motion.div>
  )
}

function Label({ children }: { children: ReactNode }): ReactNode {
  return (
    <div className="px-[10px] pb-[4px] pt-[14px] text-[12px] font-semibold leading-[16px]" style={{ color: glass.label }}>
      {children}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Steps
// ---------------------------------------------------------------------------

function Steps({ scroller }: { scroller: RefObject<HTMLDivElement | null> }): ReactNode {
  const { steps, stepId, passed, skipped, checks, complete, parts, pendingNext, instructions } = useLesson(
    useShallow((s) => ({
      steps: s.steps,
      stepId: s.stepId,
      passed: s.passed,
      skipped: s.skipped,
      checks: s.checks,
      complete: s.complete,
      parts: s.parts,
      pendingNext: s.pendingNext,
      instructions: s.instructions.trim()
    }))
  )
  // Ids on screen when the drawer opened: those rows never animate in. Anything appended later does.
  const atOpen = useRef<Set<string> | null>(null)
  if (!atOpen.current) atOpen.current = new Set(steps.map((s) => s.id))
  const fresh = steps.filter((s) => !atOpen.current!.has(s.id)).map((s) => s.id)

  const cur = steps.findIndex((s) => s.id === stepId)
  const timeW = useTimeWidth(steps, complete)
  useKeepInView(scroller, stepId, checks.length)

  const part = parts && parts.total > 1 ? `Part ${Math.min(parts.total, parts.done + parts.failed + 1)} of ${parts.total}` : undefined
  return (
    <div className="flex flex-col">
      {steps.map((s, i) => {
        const status: StepStatus = skipped.includes(s.id)
          ? 'skipped'
          : passed.includes(s.id) || (cur >= 0 && i < cur)
            ? 'done'
            : s.id === stepId
              ? 'current'
              : 'locked'
        const k = fresh.indexOf(s.id)
        return (
          <StepRow
            key={s.id}
            step={s}
            status={status}
            timeW={timeW}
            checks={status === 'current' ? checks : undefined}
            instructions={status === 'current' ? instructions : undefined}
            enterDelay={k < 0 ? undefined : k * 0.04}
          />
        )
      })}
      <AnimatePresence>{(!complete || pendingNext) && <PendingRow key="pending" waiting={pendingNext} part={part} timeW={timeW} />}</AnimatePresence>
    </div>
  )
}

/**
 * Width of the time column. A lesson that is still building is a long video, so it reserves room for
 * "1:02:00" up front; the width only ever grows, so appended steps never shift the titles of rows on screen.
 */
function useTimeWidth(steps: StepSummary[], complete: boolean): number {
  const widest = useRef(0)
  const timed = steps.some((s) => s.video)
  const w = !timed ? 0 : !complete || steps.some((s) => (s.video?.start ?? 0) >= 3600) ? 50 : 38
  widest.current = Math.max(widest.current, w)
  return widest.current
}

/** Keep the current step (and its checks) in view inside the list, without scrolling anything outside it. */
function useKeepInView(scroller: RefObject<HTMLDivElement | null>, stepId: string | undefined, checkCount: number): void {
  const first = useRef(true)
  useEffect(() => {
    const box = scroller.current
    const el = stepId ? box?.querySelector<HTMLElement>(`[data-step="${CSS.escape(stepId)}"]`) : null
    if (!box || !el) return
    const top = el.offsetTop - 34 // the "Steps" label stays visible above the first rows
    const bottom = el.offsetTop + el.offsetHeight + 46 // and the row after it peeks in
    const behavior: ScrollBehavior = first.current ? 'auto' : 'smooth'
    first.current = false
    if (top < box.scrollTop) box.scrollTo({ top: Math.max(0, top), behavior })
    else if (bottom > box.scrollTop + box.clientHeight) box.scrollTo({ top: Math.min(top, bottom - box.clientHeight), behavior })
  }, [scroller, stepId, checkCount])
}

/** True only during a component's first render (so nothing animates just because the drawer opened). */
function useMounted(): boolean {
  const mounted = useRef(false)
  useEffect(() => {
    mounted.current = true
  }, [])
  return mounted.current
}

function StepRow({
  step,
  status,
  timeW,
  checks,
  instructions,
  enterDelay
}: {
  step: StepSummary
  status: StepStatus
  timeW: number
  checks?: CheckItem[]
  /** The current step's "what to do now" (Michael: a "Just teach me" lesson has no chapter list to read). */
  instructions?: string
  enterDelay?: number
}): ReactNode {
  const mounted = useMounted()
  const v = step.video
  const current = status === 'current'
  const canSeek = status !== 'locked' && !!v
  // The plan line (steps[].what); the title when the engine sent none.
  const line = step.what?.trim() || undefined
  const tone = current ? glass.text : status === 'done' || status === 'skipped' ? glass.label : glass.faint
  const indent = ROW.padX + ROW.icon + ROW.gap + (timeW ? timeW + ROW.gap : 0)
  // No time column (a "Just teach me" lesson): plan lines wrap to two lines instead of being cut off.
  const wrap = timeW === 0
  return (
    <motion.div
      data-step={step.id}
      data-status={status}
      className="rounded-[12px]"
      style={{ background: current ? glass.fieldHover : 'transparent' }}
      initial={enterDelay === undefined ? false : { opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ ...spring, delay: enterDelay ?? 0, opacity: { duration: 0.25, delay: enterDelay ?? 0 } }}
    >
      <button
        type="button"
        className={`flex w-full items-center rounded-[12px] text-left ${canSeek ? `cursor-pointer ${hoverCls}` : 'cursor-default'}`}
        style={{ ...(wrap ? { minHeight: ROW.h, paddingTop: 9, paddingBottom: 9 } : { height: ROW.h }), paddingLeft: ROW.padX, paddingRight: ROW.padX, gap: ROW.gap, ...hoverVar }}
        disabled={!canSeek}
        onMouseDown={(e) => e.preventDefault()}
        onClick={() => v && seekVideo(v.start)}
      >
        <span className="relative grid shrink-0 place-items-center" style={{ width: ROW.icon, height: ROW.icon }}>
          {/* initial={false}: icons already there when the drawer opens (or a row appears) don't draw in; a
              status change does (GlassCheck draws its tick). */}
          <AnimatePresence initial={false} mode="wait">
            <motion.span
              key={status}
              className="grid place-items-center"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0, transition: { duration: 0.08 } }}
              transition={{ duration: 0.15 }}
            >
              <StepIcon status={status} />
            </motion.span>
          </AnimatePresence>
        </span>
        {timeW > 0 && (
          <span className="shrink-0 text-[12.5px] tabular-nums" style={{ width: timeW, color: tone }}>
            {v ? clock(v.start) : ''}
          </span>
        )}
        <span
          className={`min-w-0 flex-1 text-[14px] ${wrap ? 'line-clamp-2 leading-[20px]' : 'truncate'} ${current ? 'font-semibold' : ''}`}
          style={{ color: tone }}
          title={line && line !== step.title ? step.title : undefined}
        >
          {line ?? step.title}
        </span>
      </button>
      {current && <StepDetail stepId={step.id} instructions={instructions} planKind={step.kind} indent={indent} padX={ROW.padX} />}
      {checks && checks.length > 0 && (
        <motion.div
          data-part="drawer-checks"
          className="pb-[12px]"
          style={{ paddingLeft: indent, paddingRight: ROW.padX }}
          initial={mounted ? { opacity: 0 } : false}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.2 }}
        >
          <GlassCheckList checks={checks} />
        </motion.div>
      )}
    </motion.div>
  )
}

/**
 * done = core GlassCheck (glass.pass) · skipped = a ring with a dash in the label color (never green) ·
 * current = a ring with a dot in the text color · locked = an empty faint ring.
 */
function StepIcon({ status }: { status: StepStatus }): ReactNode {
  if (status === 'done') return <GlassCheck />
  if (status === 'skipped')
    return (
      <svg width="18" height="18" viewBox="0 0 18 18" className="shrink-0">
        <circle cx="9" cy="9" r="8.2" fill="none" strokeWidth="1.4" style={{ stroke: glass.label }} />
        <path d="M5.8 9 H12.2" strokeWidth="1.7" strokeLinecap="round" style={{ stroke: glass.label }} />
      </svg>
    )
  if (status === 'current')
    return (
      <svg width="18" height="18" viewBox="0 0 18 18" className="shrink-0">
        <circle cx="9" cy="9" r="8.2" fill="none" strokeWidth="1.6" style={{ stroke: glass.text }} />
        <circle cx="9" cy="9" r="3.4" style={{ fill: glass.text }} />
      </svg>
    )
  return <Ring />
}

/** An empty step / check: a faint ring (core has no glass twin of CheckIcon's pending state). */
function Ring(): ReactNode {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" className="shrink-0">
      <circle cx="9" cy="9" r="8.2" fill="none" strokeWidth="1.4" style={{ stroke: glass.faint }} />
    </svg>
  )
}

/**
 * core CheckList on glass (core's is drawn for the black island: white text, white rings), built from the core
 * glass atoms (core/ui/glass). Same layout: the first pending check spins, a pass draws the tick, a fail is the
 * off-track ring. Local until core has a glass CheckList (Core request 5).
 */
function GlassCheckList({ checks }: { checks: CheckItem[] }): ReactNode {
  const activeId = checks.find((c) => c.status === 'pending')?.id
  return (
    <div className="flex flex-col gap-[11px]">
      {checks.map((c) => {
        const active = c.id === activeId
        const tone = c.status === 'pass' ? glass.label : c.status === 'fail' || active ? glass.text : glass.faint
        return (
          // items-start + break-words: a long check label wraps under itself (never cut off); the icon stays on line one.
          <div key={c.id} data-check={c.id} data-check-status={c.status} className="flex items-start gap-3 text-[14px] leading-[18px]">
            {c.status === 'pass' ? (
              <GlassCheck />
            ) : c.status === 'fail' ? (
              <svg width="18" height="18" viewBox="0 0 18 18" className="shrink-0">
                <circle cx="9" cy="9" r="8.2" fill="none" strokeWidth="1.6" style={{ stroke: glass.offTrack }} />
                <path d="M9 5 V10" strokeWidth="1.7" strokeLinecap="round" style={{ stroke: glass.offTrack }} />
                <circle cx="9" cy="12.8" r="1" style={{ fill: glass.offTrack }} />
              </svg>
            ) : active ? (
              <GlassSpinner c={glass.text} />
            ) : (
              <Ring />
            )}
            <span className="min-w-0 flex-1 break-words" style={{ color: tone, transition: 'color 200ms ease-out' }}>
              {c.label}
            </span>
            {c.detail && (
              // At most ~45% of the row and wrapping: a long engine detail ("loss 0.25 at step 4000, need < 0.01…")
              // must never squeeze the label to one letter per line.
              <span className="max-w-[45%] text-right text-[12px] tabular-nums [overflow-wrap:anywhere]" style={{ color: c.status === 'fail' ? glass.offTrack : glass.faint }}>
                {c.detail}
              </span>
            )}
          </div>
        )
      })}
    </div>
  )
}

/** "More steps coming" (Part 2 of 5) while the video builds; "Next part is still building" when the learner is waiting on it. */
function PendingRow({ waiting, part, timeW }: { waiting: boolean; part?: string; timeW: number }): ReactNode {
  const mounted = useMounted()
  return (
    <motion.div
      data-part="drawer-pending"
      className="flex items-center"
      style={{ height: ROW.h, paddingLeft: ROW.padX, paddingRight: ROW.padX, gap: ROW.gap }}
      initial={mounted ? { opacity: 0 } : false}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0, transition: { duration: 0.18 } }}
      transition={{ duration: 0.25 }}
    >
      <span className="grid shrink-0 place-items-center" style={{ width: ROW.icon, height: ROW.icon }}>
        {waiting ? (
          <GlassSpinner size={16} />
        ) : (
          <svg width="18" height="18" viewBox="0 0 18 18" className="shrink-0">
            <circle cx="9" cy="9" r="8.2" fill="none" style={{ stroke: glass.faint }} strokeWidth="1.4" strokeDasharray="2.2 3.2" />
          </svg>
        )}
      </span>
      {timeW > 0 && <span className="shrink-0" style={{ width: timeW }} />}
      <span className="min-w-0 flex-1 truncate text-[13px]" style={{ color: waiting ? glass.label : glass.faint }}>
        {waiting ? 'Next part is still building' : 'More steps coming'}
      </span>
      {part && (
        <span className="shrink-0 text-[12px] tabular-nums" style={{ color: glass.faint }}>
          {part}
        </span>
      )}
    </motion.div>
  )
}

// ---------------------------------------------------------------------------
// Sources
// ---------------------------------------------------------------------------

const KIND_ICON: Record<Exclude<SourceKind, 'video'>, LucideIcon> = { repo: FolderGit2, notebook: FileCode2, paper: FileText, blog: Newspaper }

function SourceRow({ source }: { source: Source }): ReactNode {
  const link = isWebLink(source.url) ? source.url : undefined
  return (
    <button
      type="button"
      data-source={source.id}
      className={`group flex h-[48px] w-full items-center gap-[12px] rounded-[12px] px-[10px] text-left ${link ? `cursor-pointer ${hoverCls}` : 'cursor-default'}`}
      style={hoverVar}
      disabled={!link}
      onMouseDown={(e) => e.preventDefault()}
      onClick={() => link && openSource(link)}
    >
      <KindTile source={source} />
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[13px] font-medium leading-[17px]" style={{ color: glass.text }}>
          {source.title}
        </span>
        {source.meta && (
          <span className="block truncate text-[12px] leading-[16px]" style={{ color: glass.faint }}>
            {source.meta}
          </span>
        )}
      </span>
      {link && <ArrowUpRight size={13} strokeWidth={1.8} className="shrink-0 opacity-0 transition-opacity group-hover:opacity-100" style={{ color: glass.label }} />}
    </button>
  )
}

/** 44×28: the video's thumbnail, or a 16% wash of the kind's pastel with the pastel glyph (theme.kindTone). */
function KindTile({ source }: { source: Source }): ReactNode {
  const light = useAppearance() === 'light'
  if (source.kind === 'video') {
    const id = source.videoId ?? parseYouTube(source.url)?.videoId
    return <Thumb w={44} h={28} src={id ? thumbnailFor(id) : undefined} />
  }
  const I = KIND_ICON[source.kind]
  const tone = kindTone[source.kind]
  // Dark: the 16% wash with the pastel glyph. Light: a pastel glyph on paper all but disappears, so the tile
  // is the pastel itself with an ink glyph (the shortcut bar's option tiles).
  const style = light ? { background: tone, color: color.onAccent } : { background: alpha(tone, 0.16), color: tone }
  return (
    <span className="grid h-[28px] w-[44px] shrink-0 place-items-center rounded-[7px]" style={style}>
      <I size={14} strokeWidth={1.6} />
    </span>
  )
}

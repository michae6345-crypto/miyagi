/**
 * Feature: drawer. The slim tab on the right edge and the lesson drawer it opens: every step as done /
 * current / locked (the current one with its live checks), a quiet "More steps coming" row while a long
 * video is still building part by part, and the lesson's sources.
 *
 * The header never scrolls (mockup 01): for a "Just teach me" lesson the "Just teach me · <topic>" eyebrow, then the
 * title, then one row: "Step N of M", a thin progress bar (neutral fill: green only means passed), "about N min left"
 * ("Step N · more coming" and no bar or time while a lesson still streams in with no known total, review A14).
 *
 * A "Just teach me" lesson adds, top to bottom (Teach.tsx): what we're building, "Before you start", the plan
 * (numbered, one line per step from steps[].what, "N of M done"), and inside the current step the full code to
 * type with Copy, why, its concepts, its checks and the option row (Explain / Diagram / Show me / Hint + Check my work).
 *
 * Appended steps (lesson.updated) fade in; rows already on screen never re-animate: a row only gets an
 * entrance when its id wasn't there when the drawer opened. (AnimatePresence initial={false} would do that
 * too, but it also blocks every motion that mounts later inside those rows, like the green tick drawing in.)
 */
import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type PointerEvent as ReactPointerEvent, type ReactNode, type RefObject } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { ArrowUpRight, ChevronsLeft, ChevronsRight, FileCode2, FileText, FolderGit2, Newspaper, X, type LucideIcon } from 'lucide-react'
import type { Source, SourceKind, StepSummary } from '../../../../../../shared/contracts/events'
import { builtByLabel, seekVideo, useLesson, useProgress, type CheckItem, type Rect } from '../../core/lesson'
import { useAppearance } from '../../core/prefs'
import { alpha, clock, color, copy, glass, kindTone, radius, spring, springOut } from '../../core/theme'
import { CheckList, Thumb, useChecking } from '../../core/ui/atoms'
import { GlassCheck, GlassSpinner } from '../../core/ui/glass'
import { useCards } from '../cards/store'
import { needsLine } from '../cards/setupPlan'
import { parseYouTube, thumbnailFor } from '../launcher/youtube'
import { HANDLE, TAB } from './geometry'
import { count, lessonOutline, planTotal, useJustEnded, useStepDetail, useStepStatuses, type StepStatus } from './plan'
import { closeDrawer, isWebLink, linkHost, openSource, setDrawerSide, setPanelHeight, toggleDrawer, useDrawer, type Side } from './store'
import { BuildStrip, lessonTopic, minutesLeft, NeedsChip, OverviewText, PrimerSection, StepActions, StepDetail } from './Teach'
import { enter, fade } from '../../core/ui/motion'
import { useVideoHelp, VideoHelp } from './VideoHelp'
import { useLocal } from '../settings/local'

/**
 * Row geometry: icon column, gap, time column. The current step's checks line up with its title. A plan row with no
 * time column (a "Just teach me" lesson) is mockup 01's denser list: at least 32 tall, its line wrapping to two.
 */
const ROW = { h: 38, wrapH: 32, wrapPadY: 6, openPadY: 9, padX: 10, icon: 18, gap: 11 } as const
/** Section labels: mockup 01's small caps (the eyebrow's style), faint. */
/** Section labels: 12 px medium, sentence case, the label color (overlay round: the same as the home window's SectionHead). */
const CAPS = 'text-[12px] font-medium'
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
/** `onOpen`: what a press does instead of toggling (a run step's tucked drawer: show it for that step). */
export function Tab({ rect, shown, labeled = false, onOpen }: { rect: Rect; shown: boolean; labeled?: boolean; onOpen?: () => void }): ReactNode {
  const [hover, setHover] = useState(false)
  const side = useDrawer((s) => s.at)
  if (labeled) return <StepsHandle rect={rect} shown={shown} onOpen={onOpen} />
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
          transition={fade.in}
          onHoverStart={() => setHover(true)}
          onHoverEnd={() => setHover(false)}
          onMouseDown={(e) => e.preventDefault()}
          onClick={onOpen ?? toggleDrawer}
        >
          <motion.span
            className="absolute rounded-full"
            style={{ [side === 'left' ? 'left' : 'right']: TAB.edge, top: (rect.h - TAB.h) / 2, width: TAB.w, height: TAB.h, background: glass.track }}
            animate={{ scaleX: hover ? 1.5 : 1, scaleY: hover ? 1.15 : 1 }}
            transition={spring}
          />
        </motion.button>
      )}
    </AnimatePresence>
  )
}

/**
 * A "Just teach me" lesson's collapsed drawer: a glass "Steps" handle on the right edge, plain to see, so a learner who
 * hid the drawer always has the way back (Michael's live test, Sun 12:55 AM). Neutral chrome: glass tokens, no pastel.
 */
function StepsHandle({ rect, shown, onOpen }: { rect: Rect; shown: boolean; onOpen?: () => void }): ReactNode {
  const left = useDrawer((s) => s.at) === 'left'
  const out = left ? -12 : 12
  return (
    <AnimatePresence>
      {shown && (
        <motion.button
          key="drawer-handle"
          type="button"
          data-hit
          data-part="drawer-tab"
          aria-label="Show lesson steps"
          title="Show lesson steps"
          className="absolute flex cursor-pointer items-center justify-center border text-[12px] font-semibold"
          style={{
            left: left ? rect.x + HANDLE.edge : rect.x,
            top: rect.y,
            width: rect.w - HANDLE.edge,
            height: rect.h,
            borderRadius: radius.card,
            background: glass.bg,
            borderColor: glass.hairline,
            boxShadow: `${glass.shadow}, inset 0 0 0 ${rect.w}px ${glass.bg}`,
            color: glass.label,
            writingMode: 'vertical-rl'
          }}
          initial={{ opacity: 0, x: out }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: out }}
          whileHover={{ x: left ? 2 : -2 }}
          transition={{ ...spring, opacity: fade.in }}
          onMouseDown={(e) => e.preventDefault()}
          onClick={onOpen ?? toggleDrawer}
        >
          Steps
        </motion.button>
      )}
    </AnimatePresence>
  )
}

// ---------------------------------------------------------------------------
// Panel
// ---------------------------------------------------------------------------

/** How far the header must move sideways before it's a drag (a plain press still clicks its buttons). */
const SIDE_DRAG_SLOP = 6

export function Panel({ rect, side = 'right' }: { rect: Rect; side?: Side }): ReactNode {
  const lesson = useLesson((s) => s.lesson)
  const lessonMode = lesson?.mode === 'lesson'
  const plan = usePlanProgress()
  const scroller = useRef<HTMLDivElement>(null)
  const box = useRef<HTMLDivElement>(null)
  const demo = useLesson((s) => s.demo)
  const by = builtByLabel(lesson?.builtBy, lesson?.mode, demo)
  const sources = lesson?.sources ?? []
  const overview = lesson?.overview?.trim()
  const topic = lessonMode && lesson?.title ? lessonTopic(lesson.title) : undefined
  // A hairline under the header once the list scrolls, so text doesn't run straight into the title.
  const [scrolled, setScrolled] = useState(false)
  const away = (side === 'left' ? -1 : 1) * (rect.w + 24)
  const drag = useSideDrag(side)
  const videoHelp = useVideoHelp()
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
      animate={{ x: drag.dx, opacity: 1 }}
      exit={{ x: away, opacity: 0, transition: { ...springOut, opacity: fade.in } }}
      transition={{ ...spring, opacity: fade.in }}
    >
      <div
        data-part="drawer-header"
        className="shrink-0 border-b px-[18px] pb-[12px] pt-[16px]"
        style={{
          borderColor: scrolled ? glass.rule : 'transparent',
          transition: 'border-color 150ms ease-out',
          cursor: drag.dragging ? 'grabbing' : 'grab',
          touchAction: 'none'
        }}
        title="Drag sideways to move the steps to the other edge"
        onPointerDown={drag.onPointerDown}
        onClickCapture={drag.onClickCapture}
      >
        <div className="flex items-start gap-[12px]">
          <div className="min-w-0 flex-1">
            {lessonMode && (
              <div data-part="drawer-eyebrow" className="mb-[3px] truncate text-[12px] font-medium leading-[16px]" style={{ color: glass.label }}>
                {/* Michael, test 7: nothing on screen names the mode (a Demo take read "Just teach me"). */}
                {topic || 'Lesson'}
              </div>
            )}
            {/* Mockup 01: a lesson's title is the header (20 pt); a video's stays 15 next to its player. */}
            <div
              data-part="drawer-title"
              className={`line-clamp-2 font-semibold ${lessonMode ? 'text-[20px] leading-[25px] tracking-[-0.01em]' : 'text-[15px] leading-[20px]'}`}
            >
              {lesson?.title ?? ''}
            </div>
            {by && (
              <div className="mt-[2px] truncate text-[12px] leading-[16px]" style={{ color: glass.faint }}>
                {by}
              </div>
            )}
          </div>
          <button
            type="button"
            className="mt-[-2px] grid h-[24px] w-[24px] shrink-0 cursor-pointer place-items-center rounded-full"
            style={{ background: glass.key, color: glass.keyText }}
            onMouseDown={(e) => e.preventDefault()}
            onClick={closeDrawer}
            aria-label={lessonMode ? 'Hide steps' : 'Close'}
            title={lessonMode ? `Hide steps (the Steps tab on the ${side} brings them back)` : undefined}
          >
            {/* A lesson's drawer collapses to the "Steps" handle: a chevron, so it never reads as a card's ✕. */}
            {lessonMode ? (side === 'left' ? <ChevronsLeft size={13} strokeWidth={2.2} /> : <ChevronsRight size={13} strokeWidth={2.2} />) : <X size={12} strokeWidth={2.2} />}
          </button>
        </div>
        {plan.known > 0 && <ProgressHeader plan={plan} />}
      </div>
      <div
        ref={scroller}
        className="relative min-h-0 flex-initial overflow-y-auto px-[8px] pb-[12px]"
        // The list starts under the fixed header (never behind it). scrollPaddingTop keeps the browser's own scrolls
        // (focus, a drag-select running off the top) clear of the edge by a label's height, like useKeepInView's
        // 34 px (Michael's review A19: the sticky header cut content).
        style={{ scrollbarWidth: 'thin', scrollbarColor: `${glass.track} transparent`, scrollPaddingTop: 34 }}
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
              <Label>What you're building</Label>
              <OverviewText text={overview} />
            </>
          )
        )}
        <NeedsChip />
        <PrimerSection />
        <Label part="drawer-plan" right={plan.skipped ? `${plan.skipped} skipped` : undefined}>
          {lessonMode ? 'The plan' : 'Steps'}
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
      {videoHelp && <VideoHelp />}
    </motion.div>
  )
}

function Label({ children, right, part }: { children: ReactNode; right?: ReactNode; part?: string }): ReactNode {
  return (
    <div data-part={part} className="flex items-baseline justify-between gap-[8px] px-[10px] pb-[4px] pt-[14px] leading-[16px]">
      <span className={CAPS} style={{ color: glass.label }}>
        {children}
      </span>
      {right && (
        <span data-part="drawer-done" className="shrink-0 text-[12px] tabular-nums" style={{ color: glass.faint }}>
          {right}
        </span>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Header progress
// ---------------------------------------------------------------------------

/**
 * known: steps that have arrived. total: how many the lesson has, undefined while it is still streaming in without an
 * outline (plan.ts planTotal, review A14).
 */
type PlanProgress = { done: number; skipped: number; known: number; total?: number; index: number; hasStep: boolean; complete: boolean; left?: number }

/**
 * Steps done: passed (or before the current one), never skipped and never the current step itself (the same rule as
 * the rows, plan.ts stepStatuses; Michael's desktop test 4, Sun 1:42 AM: 2 passes + 2 skips read "4 of 7 done"),
 * where we are, and minutes left.
 */
function usePlanProgress(): PlanProgress {
  const { index: at } = useProgress()
  const statuses = useStepStatuses()
  // Passed, next step.started not here yet: the pill already shows the next step, so the header does too (Michael's
  // test 10, item 9: "Step 4 of 7" under a pill at Step 5). Not after the last step: that reads "All N steps done".
  const ended = useJustEnded()
  const ahead = useLesson((s) => !!ended && (at < s.steps.length - 1 || s.pendingNext || !s.complete))
  const index = ahead ? at + 1 : at
  const p = useLesson(
    useShallow((s) => {
      const done = statuses.filter((x) => x === 'done').length
      const skipped = statuses.filter((x) => x === 'skipped').length
      const outline = lessonOutline(s.lesson)
      const finished = s.steps.filter((_, i) => statuses[i] === 'done' || statuses[i] === 'skipped').map((x) => x.id)
      // Mockup 01: "about N min left" (steps[].estMinutes over the steps still to do: the current one counts, a skipped
      // one doesn't). While steps stream in, the list's sum grows with every part (review A14), so only the outline's
      // estimates count then; with no outline the time shows once the lesson is complete.
      const left = s.complete ? minutesLeft(s.steps, finished) : outline ? minutesLeft(s.steps, finished, outline.rows) : undefined
      return { done, skipped, known: s.steps.length, total: planTotal(s.steps.length, s.complete, outline), hasStep: !!s.stepId, complete: s.complete, left }
    })
  )
  return { ...p, index }
}

/**
 * The header line. Never a total that isn't known yet (review A14): "Step 1 · more coming" until the lesson is complete
 * or the outline (E23) gives the count, then "Step 1 of 6".
 */
function stepLine(plan: PlanProgress): string {
  const { total } = plan
  // Every step passed or skipped: the lesson is over. Skipped steps never read as done.
  if (plan.complete && total && plan.done + plan.skipped >= total) {
    if (plan.skipped) return `${plan.done} of ${total} done · ${plan.skipped} skipped`
    return total === 1 ? 'Step done' : `All ${total} steps done`
  }
  if (plan.hasStep) return total ? `Step ${plan.index + 1} of ${total}` : `Step ${plan.index + 1} · more coming`
  return total ? count(total, 'step') : `${count(plan.known, 'step')} · more coming`
}

/**
 * Mockup 01, one row: "Step N of M", a thin bar (neutral fill, never green: green only means passed), the time left.
 * Never scrolls. No total yet: no bar (a fill over the steps so far would shrink back with every part that lands), and
 * the row keeps its height when the bar comes in.
 */
function ProgressHeader({ plan }: { plan: PlanProgress }): ReactNode {
  const all = plan.complete && !!plan.total && plan.done + plan.skipped >= plan.total
  const line = stepLine(plan)
  // Settings > Lessons > Show time left.
  const showLeft = useLocal((s) => s.timeLeft)
  return (
    <div data-part="drawer-progress" className="mt-[10px] flex items-center gap-[10px] text-[13px] leading-[18px]">
      <span data-part="drawer-step-of" className="shrink-0 font-semibold tabular-nums" style={{ color: glass.text }}>
        {line}
      </span>
      <span className="min-w-[24px] flex-1">
        {!!plan.total && (
          <span className="block h-[4px] overflow-hidden rounded-full" style={{ background: glass.track }}>
            <motion.span
              data-part="drawer-progress-fill"
              className="block h-full w-full"
              style={{ background: glass.text, originX: 0 }}
              initial={false}
              animate={{ scaleX: plan.done / plan.total }}
              transition={spring}
            />
          </span>
        )}
      </span>
      {showLeft && !all && plan.left !== undefined && plan.left > 0 && (
        <span data-part="drawer-left" className="min-w-0 shrink truncate" style={{ color: glass.faint }}>
          about {plan.left} min left
        </span>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Steps
// ---------------------------------------------------------------------------

function Steps({ scroller }: { scroller: RefObject<HTMLDivElement | null> }): ReactNode {
  const { steps, stepId, checks, complete, parts, pendingNext, instructions, lessonMode } = useLesson(
    useShallow((s) => ({
      steps: s.steps,
      stepId: s.stepId,
      checks: s.checks,
      complete: s.complete,
      parts: s.parts,
      pendingNext: s.pendingNext,
      instructions: s.instructions.trim(),
      lessonMode: s.lesson?.mode === 'lesson'
    }))
  )
  // The outline (E23) knows how many steps are still to come: "2 more steps coming".
  const more = useLesson((s) => {
    const o = lessonOutline(s.lesson)
    return o ? o.count - s.steps.length : undefined
  })
  // Ids on screen when the drawer opened: those rows never animate in. Anything appended later does.
  const atOpen = useRef<Set<string> | null>(null)
  if (!atOpen.current) atOpen.current = new Set(steps.map((s) => s.id))
  const fresh = steps.filter((s) => !atOpen.current!.has(s.id)).map((s) => s.id)

  // The current step stays current (expanded) even when core still lists it as passed or skipped (after Back).
  const statuses = useStepStatuses()
  // Just passed, next step.started on its way: the row stays open (its code and green checks) until the next step
  // opens, so the panel doesn't shrink and grow back at every step change (Michael's test 10, item 9). The last
  // step of a finished lesson closes as before.
  const ended = useJustEnded()
  const held = useLesson((s) => {
    if (!ended) return undefined
    const i = s.steps.findIndex((x) => x.id === ended)
    return i >= 0 && (i < s.steps.length - 1 || s.pendingNext || !s.complete) ? ended : undefined
  })
  const setupNote = useSetupNote()
  const timeW = useTimeWidth(steps, complete)
  // The current step's code arriving after step.started grows the row: keep it in view then too.
  const codeLen = useStepDetail((d) => (d.detail && d.detail.stepId === stepId ? (d.detail.code?.length ?? 0) : -1))
  useKeepInView(scroller, stepId, checks, codeLen)

  const part = parts && parts.total > 1 ? `Part ${Math.min(parts.total, parts.done + parts.failed + 1)} of ${parts.total}` : undefined
  return (
    <div className="flex flex-col">
      {steps.map((s, i) => {
        const status: StepStatus = statuses[i] ?? 'locked'
        const k = fresh.indexOf(s.id)
        const open = status === 'current' || s.id === held
        return (
          <StepRow
            key={s.id}
            step={s}
            n={i + 1}
            status={status}
            held={s.id === held}
            timeW={timeW}
            checks={open ? checks : undefined}
            instructions={open ? instructions : undefined}
            actions={open && lessonMode}
            note={status === 'current' ? setupNote : undefined}
            enterDelay={k < 0 ? undefined : k * 0.04}
          />
        )
      })}
      <AnimatePresence>{(!complete || pendingNext) && <PendingRow key="pending" waiting={pendingNext} part={part} more={more} timeW={timeW} />}</AnimatePresence>
    </div>
  )
}

/**
 * A setup card with something still missing is up (Michael's review A17): the current step says what it needs, one
 * quiet line ("Needs AutoCAD"). The setup card is the one place that says "set up first" (Michael, Nov 22); the step
 * list reads as usual. Rows the learner settled ("I have it", a free alternative chosen) need nothing. Read-only from
 * the cards store.
 */
function useSetupNote(): string | undefined {
  return useCards((c) => needsLine(c.card, (x) => (x.kind === 'editor' ? copy.editorName(x.label) : x.label)))
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

/**
 * Keep the current step in view inside the list, without scrolling anything outside it (audit A11: its checks were cut
 * off at the bottom).
 *  - The whole step fits: show all of it, from the label above it down to the row after it peeking in, never stopping
 *    partway through the overview above the plan (clearOfIntro).
 *  - It's taller than the list: a new step starts at its title (what to type); once a check has a result (or a Check
 *    is running), the checks and the option row under them come up from below the fold.
 */
function useKeepInView(scroller: RefObject<HTMLDivElement | null>, stepId: string | undefined, checks: CheckItem[], codeLen: number): void {
  const first = useRef(true)
  const lastStep = useRef<string | undefined>(undefined)
  const checksKey = checks.map((c) => `${c.id}:${c.status}`).join(',')
  const settled = checks.some((c) => c.status !== 'pending')
  const checking = useChecking()
  useEffect(() => {
    const box = scroller.current
    const el = stepId ? box?.querySelector<HTMLElement>(`[data-step="${CSS.escape(stepId)}"]`) : null
    if (!box || !el) return
    const newStep = lastStep.current !== stepId
    lastStep.current = stepId
    // Positions inside the scroller's content (offsetTop would depend on which ancestor is positioned), in layout px:
    // the browser stage scales the whole screen, and client rects are scaled while scrollTop is not.
    const frame = box.getBoundingClientRect()
    const k = box.offsetHeight > 0 ? frame.height / box.offsetHeight : 1
    const at = (n: HTMLElement): { top: number; bottom: number } => {
      const r = n.getBoundingClientRect()
      return { top: (r.top - frame.top) / k + box.scrollTop, bottom: (r.bottom - frame.top) / k + box.scrollTop }
    }
    const view = box.clientHeight
    const now = box.scrollTop
    const step = at(el)
    const top = step.top - 34 // the label above stays visible
    const end = step.bottom + 46 // and the row after it peeks in
    let target: number | undefined
    if (step.bottom + 8 - top <= view) {
      if (top < now) target = top
      else if (end > now + view) target = Math.min(top, end - view)
      if (target !== undefined) target = clearOfIntro(box, at, target, step.bottom + 8 <= view)
    } else if (newStep) {
      target = top
    } else {
      const list = el.querySelector<HTMLElement>('[data-part="drawer-checks"]')
      const tail = el.querySelector<HTMLElement>('[data-part="drawer-actions"]') ?? list
      if (list && tail && (settled || checking)) {
        const c = at(list)
        const bottom = at(tail).bottom + 12
        if (bottom > now + view) target = Math.min(c.top - 12, bottom - view)
        else if (c.top - 12 < now) target = c.top - 12
      }
    }
    reach(box, at, target ?? now)
    if (target === undefined) return
    box.scrollTo({ top: Math.max(0, target), behavior: first.current ? 'auto' : 'smooth' })
    first.current = false
  }, [scroller, stepId, checksKey, settled, checking, codeLen])
}

/** The list's own bottom padding (its pb-[12px] class). */
const LIST_PAD = 12

/**
 * The list only scrolls so far: past its end the browser clamps the scroll, and when the clamp stops inside the intro
 * above the plan, the "What you're building" strip sits cut in half under the header (Michael's tests 8 and 10: from
 * step 5 on the drawer opened scrolled halfway, the flow boxes cut off at the top). Then room at the list's foot lets
 * the scroll land on the block edge clearOfIntro chose. Only while the list overflows (the panel is at its full height,
 * so the extra room never grows it), and recomputed on every pass, so it never piles up.
 */
function reach(box: HTMLElement, at: (n: HTMLElement) => { top: number; bottom: number }, want: number): void {
  const plan = box.querySelector<HTMLElement>('[data-part="drawer-plan"]')
  const extra = Number(box.dataset.reach ?? 0)
  const max = box.scrollHeight - extra - box.clientHeight
  const need = plan && max > 0 && want > max && max < at(plan).top ? Math.ceil(want - max) : 0
  if (need === extra) return
  box.dataset.reach = String(need)
  box.style.paddingBottom = need ? `${LIST_PAD + need}px` : ''
}

/**
 * Never park the list partway through the text above the plan (what we're building, Needs, Before you start): Michael's
 * desktop test 3, item 6, the overview's first lines sat cut off under the fixed header. A target inside that intro
 * becomes 0 when the step still fits from the top (its row-after peek may go), else the next block edge below it,
 * so the intro is either all there or cleanly scrolled away under the header's hairline. The step's top stays in
 * view either way: every candidate is at or above the plan label.
 */
function clearOfIntro(
  box: HTMLElement,
  at: (n: HTMLElement) => { top: number; bottom: number },
  target: number,
  fitsFromTop: boolean
): number {
  const plan = box.querySelector<HTMLElement>('[data-part="drawer-plan"]')
  if (!plan) return target
  const planTop = at(plan).top
  if (target <= 0 || target >= planTop) return target
  if (fitsFromTop) return 0
  const edges = Array.from(box.children, (c) => at(c as HTMLElement).top).filter((t) => t >= target && t <= planTop)
  return Math.min(planTop, ...edges)
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
  n,
  status,
  held = false,
  timeW,
  checks,
  instructions,
  actions,
  note,
  enterDelay
}: {
  step: StepSummary
  /** The step's number in the plan (1-based), drawn in its ring. */
  n: number
  status: StepStatus
  /** Just passed or skipped, the next step not started yet: stays open (done icon) until the next step opens. */
  held?: boolean
  timeW: number
  checks?: CheckItem[]
  /** The current step's "what to do now" (Michael: a "Just teach me" lesson has no chapter list to read). */
  instructions?: string
  /** The option row (Explain / Diagram / Show me / Hint + Check my work): the current step of a "Just teach me" lesson. */
  actions?: boolean
  /** A quiet status under the step's title ("Needs AutoCAD"): faint, no hue. */
  note?: string
  enterDelay?: number
}): ReactNode {
  const mounted = useMounted()
  const v = step.video
  const current = status === 'current'
  const open = current || held
  const canSeek = status !== 'locked' && !!v
  // The plan line (steps[].what); the title when the engine sent none.
  const line = step.what?.trim() || undefined
  const tone = open ? glass.text : status === 'done' || status === 'skipped' ? glass.label : glass.faint
  const indent = ROW.padX + ROW.icon + ROW.gap + (timeW ? timeW + ROW.gap : 0)
  // No time column (a "Just teach me" lesson): plan lines wrap to two lines instead of being cut off.
  const wrap = timeW === 0
  // The open step's line is never cut either: beside a time column it wraps to two lines too (a one-line title keeps
  // the row at ROW.h; the other rows stay one line so the list reads as a list).
  const tall = !wrap && open
  const estimate = typeof step.estMinutes === 'number' && step.estMinutes > 0 ? `about ${Math.round(step.estMinutes)} min` : undefined
  return (
    <motion.div
      data-step={step.id}
      data-status={status}
      className="rounded-[12px]"
      style={{ background: open ? glass.fieldHover : 'transparent' }}
      initial={enterDelay === undefined ? false : { opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={enter(enterDelay ?? 0, fade.slow)}
    >
      <button
        type="button"
        className={`flex w-full ${tall ? 'items-start' : 'items-center'} rounded-[12px] text-left ${canSeek ? `cursor-pointer ${hoverCls}` : 'cursor-default'}`}
        style={{ ...(wrap ? { minHeight: ROW.wrapH, paddingTop: ROW.wrapPadY, paddingBottom: ROW.wrapPadY } : tall ? { minHeight: ROW.h, paddingTop: ROW.openPadY, paddingBottom: ROW.openPadY } : { height: ROW.h }), paddingLeft: ROW.padX, paddingRight: ROW.padX, gap: ROW.gap, ...hoverVar }}
        disabled={!canSeek}
        onMouseDown={(e) => e.preventDefault()}
        onClick={() => v && seekVideo(v.start)}
      >
        {/* tall: the number and the time sit on the title's first line (20 px), not between its two lines. */}
        <span className="relative grid shrink-0 place-items-center" style={{ width: ROW.icon, height: ROW.icon, marginTop: tall ? 1 : undefined }}>
          {/* initial={false}: icons already there when the drawer opens (or a row appears) don't draw in; a
              status change does (GlassCheck draws its tick). */}
          <AnimatePresence initial={false} mode="wait">
            <motion.span
              key={status}
              className="grid place-items-center"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0, transition: fade.instant }}
              transition={fade.in}
            >
              <StepIcon status={status} n={n} />
            </motion.span>
          </AnimatePresence>
        </span>
        {timeW > 0 && (
          <span className={`shrink-0 text-[12.5px] tabular-nums ${tall ? 'leading-[20px]' : ''}`} style={{ width: timeW, color: tone }}>
            {v ? clock(v.start) : ''}
          </span>
        )}
        <span
          className={`min-w-0 flex-1 text-[14px] ${wrap || tall ? 'line-clamp-2 leading-[20px]' : 'truncate'} ${open ? 'font-semibold' : ''}`}
          style={{ color: tone }}
          title={line && line !== step.title ? step.title : undefined}
        >
          {line ?? step.title}
        </span>
        {/* Mockup 01: the current step's "about 4 min" at the row's end. A status note ("Needs AutoCAD") still wins:
            it sits on its own line below and the title takes the whole row. */}
        {current && estimate && !note && (
          <span data-part="drawer-step-est" className="shrink-0 text-[12px]" style={{ color: glass.faint }}>
            {estimate}
          </span>
        )}
      </button>
      {/* A status note ("Needs AutoCAD") gets its own quiet line under the title, so the title is never cut for it
          (fix round 1: "Draw the side p..." at 1440). */}
      {note && (
        <div data-part="drawer-step-note" className="truncate pb-[6px] text-[12px] leading-[16px]" style={{ paddingLeft: indent, paddingRight: ROW.padX, marginTop: -6, color: glass.faint }}>
          {note}
        </div>
      )}
      {open && <StepDetail stepId={step.id} instructions={instructions} planKind={step.kind} indent={indent} padX={ROW.padX} />}
      {checks && checks.length > 0 && (
        <motion.div
          data-part="drawer-checks"
          className="pb-[12px]"
          style={{ paddingLeft: indent, paddingRight: ROW.padX }}
          initial={mounted ? { opacity: 0 } : false}
          animate={{ opacity: 1 }}
          transition={fade.in}
        >
          <CheckList checks={checks} surface="glass" />
        </motion.div>
      )}
      {/* A held (finished) step keeps the row's room but its options are spent: faded and inert until the next opens. */}
      {actions &&
        (held ? (
          <div aria-hidden style={{ opacity: 0.35, pointerEvents: 'none' }}>
            <StepActions padX={ROW.padX} />
          </div>
        ) : (
          <StepActions padX={ROW.padX} />
        ))}
    </motion.div>
  )
}

/**
 * done = core GlassCheck (glass.pass) · skipped = a ring with a dash in the label color (never green) ·
 * current = a ring with the step's number in the text color · locked = a faint ring with its number.
 */
function StepIcon({ status, n }: { status: StepStatus; n: number }): ReactNode {
  if (status === 'done') return <GlassCheck />
  if (status === 'skipped')
    return (
      <svg width="18" height="18" viewBox="0 0 18 18" className="shrink-0">
        <circle cx="9" cy="9" r="8.2" fill="none" strokeWidth="1.4" style={{ stroke: glass.label }} />
        <path d="M5.8 9 H12.2" strokeWidth="1.7" strokeLinecap="round" style={{ stroke: glass.label }} />
      </svg>
    )
  return <NumberRing n={n} current={status === 'current'} />
}

/** A step's number in a ring: the text color for the current step, faint for the ones still to come. */
function NumberRing({ n, current }: { n: number; current: boolean }): ReactNode {
  const c = current ? glass.text : glass.faint
  return (
    <span
      data-part="step-number"
      className={`grid h-[18px] w-[18px] shrink-0 place-items-center rounded-full font-semibold tabular-nums leading-none ${n > 99 ? 'text-[8px]' : 'text-[10px]'}`}
      style={{ border: `${current ? 1.6 : 1.4}px solid ${c}`, color: c }}
    >
      {n}
    </span>
  )
}

/**
 * "More steps coming" (Part 2 of 5) while the video builds, "2 more steps coming" when the outline (E23) gives the count;
 * "Next part is still building" when the learner is waiting on it.
 */
function PendingRow({ waiting, part, more, timeW }: { waiting: boolean; part?: string; more?: number; timeW: number }): ReactNode {
  const mounted = useMounted()
  return (
    <motion.div
      data-part="drawer-pending"
      className="flex items-center"
      style={{ height: timeW ? ROW.h : ROW.wrapH, paddingLeft: ROW.padX, paddingRight: ROW.padX, gap: ROW.gap }}
      initial={mounted ? { opacity: 0 } : false}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0, transition: fade.in }}
      transition={fade.slow}
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
        {waiting ? 'Next part is still building' : more && more > 0 ? `${count(more, 'more step', 'more steps')} coming` : 'More steps coming'}
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
  // Where the click lands, from the URL itself (app-harden): the title and meta are the engine's words. Its own element,
  // never truncated: a long meta gives way first.
  const host = linkHost(link)
  return (
    <button
      type="button"
      data-source={source.id}
      className={`group flex min-h-[48px] w-full items-center gap-[12px] rounded-[12px] px-[10px] py-[6px] text-left ${link ? `cursor-pointer ${hoverCls}` : 'cursor-default'}`}
      style={hoverVar}
      disabled={!link}
      onMouseDown={(e) => e.preventDefault()}
      onClick={() => link && openSource(link)}
    >
      <KindTile source={source} />
      <span className="min-w-0 flex-1">
        {/* QA Q22: the title and meta wrap (two lines at most for the title) instead of cutting off mid-word. */}
        {/* No `block` here: it would override line-clamp's display:-webkit-box and the clamp would never apply. */}
        <span className="line-clamp-2 break-words text-[13px] font-medium leading-[17px]" style={{ color: glass.text }}>
          {source.title}
        </span>
        {(source.meta || host) && (
          <span className="flex min-w-0 flex-wrap gap-x-[0.3em] text-[12px] leading-[16px]" style={{ color: glass.faint }}>
            {/* The separator ends the meta (glued by a no-break space), so when the host wraps no line begins with a dot. */}
            {source.meta && <span className="min-w-0 break-words">{host ? `${source.meta}\u00a0·` : source.meta}</span>}
            {host && (
              <span data-link-host className="shrink-0 whitespace-nowrap">
                {host}
              </span>
            )}
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

/**
 * Drag the panel's header sideways (Michael, Nov 15 5:45 AM: "I should be able to move it right to left, and lock it to
 * that side"). The panel follows the pointer; let go past the screen's middle and it settles on that edge (saved), else
 * it springs back. A press that doesn't travel SIDE_DRAG_SLOP stays a click (the header's buttons still work).
 */
function useSideDrag(side: Side): {
  dx: number
  dragging: boolean
  onPointerDown: (e: ReactPointerEvent) => void
  onClickCapture: (e: React.MouseEvent) => void
} {
  const [dx, setDx] = useState(0)
  const [dragging, setDragging] = useState(false)
  const moved = useRef(false)
  return {
    dx,
    dragging,
    onPointerDown: (e) => {
      if (e.button !== 0) return
      moved.current = false
      const x0 = e.clientX
      const y0 = e.clientY
      const move = (m: PointerEvent): void => {
        const d = m.clientX - x0
        if (!moved.current && Math.hypot(d, m.clientY - y0) < SIDE_DRAG_SLOP) return
        if (!moved.current) {
          moved.current = true
          setDragging(true)
        }
        setDx(d)
      }
      const up = (u: PointerEvent): void => {
        window.removeEventListener('pointermove', move)
        window.removeEventListener('pointerup', up)
        window.removeEventListener('pointercancel', up)
        setDragging(false)
        if (!moved.current) return
        const mid = window.innerWidth / 2
        const to: Side = u.clientX < mid ? 'left' : 'right'
        setDx(0)
        if (to !== side) setDrawerSide(to)
      }
      window.addEventListener('pointermove', move)
      window.addEventListener('pointerup', up)
      window.addEventListener('pointercancel', up)
    },
    onClickCapture: (e) => {
      if (!moved.current) return
      moved.current = false
      e.stopPropagation()
      e.preventDefault()
    }
  }
}

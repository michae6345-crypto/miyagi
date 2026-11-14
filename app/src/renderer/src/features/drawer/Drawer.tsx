/**
 * Feature: drawer. The slim tab on the right edge and the lesson drawer it opens: every step as done /
 * current / locked (the current one with its live checks), a quiet "More steps coming" row while a long
 * video is still building part by part, and the lesson's sources.
 *
 * Appended steps (lesson.updated) fade in; rows already on screen never re-animate: a row only gets an
 * entrance when its id wasn't there when the drawer opened. (AnimatePresence initial={false} would do that
 * too, but it also blocks every motion that mounts later inside those rows, like the green tick drawing in.)
 */
import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useRef, useState, type CSSProperties, type ReactNode, type RefObject } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { ArrowUpRight, FileCode2, FileText, FolderGit2, Newspaper, X, type LucideIcon } from 'lucide-react'
import type { Source, SourceKind, StepSummary } from '../../../../../../shared/contracts/events'
import { builtByLabel, seekVideo, useLesson, type CheckItem, type Rect } from '../../core/lesson'
import { brand, color, fill, kindTone, radius, shadow, spring, springOut } from '../../core/theme'
import { CheckIcon, CheckList, Spinner, Thumb } from '../../core/ui/atoms'
import { parseYouTube, thumbnailFor } from '../launcher/youtube'
import { TAB } from './geometry'
import { closeDrawer, toggleDrawer } from './store'

type StepStatus = 'done' | 'current' | 'locked'

/** Row geometry: icon column, gap, time column. The current step's checks line up with its title. */
const ROW = { h: 38, padX: 10, icon: 18, gap: 11 } as const
/** Hover fill for clickable rows, through a CSS variable so the color stays a token. */
const hoverVar = { '--drawer-hover': fill.chip } as CSSProperties
const hoverCls = 'hover:bg-[var(--drawer-hover)]'

// ---------------------------------------------------------------------------
// Tab
// ---------------------------------------------------------------------------

/** 4×40 white at fill.track, inside a wider hit box. Hover stretches the bar a little (transform only). */
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
            style={{ right: TAB.edge, top: (rect.h - TAB.h) / 2, width: TAB.w, height: TAB.h, background: fill.track }}
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
  const scroller = useRef<HTMLDivElement>(null)
  const by = builtByLabel(lesson?.builtBy)
  const sources = lesson?.sources ?? []
  const away = rect.w + 24
  return (
    <motion.div
      data-hit
      data-part="drawer"
      className="absolute flex flex-col overflow-hidden border"
      style={{
        left: rect.x,
        top: rect.y,
        width: rect.w,
        height: rect.h,
        borderRadius: radius.card,
        background: color.glass,
        borderColor: color.hairline,
        boxShadow: shadow,
        backdropFilter: 'blur(30px) saturate(1.4)',
        color: color.text
      }}
      initial={{ x: away, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      exit={{ x: away, opacity: 0, transition: { ...springOut, opacity: { duration: 0.18 } } }}
      transition={{ ...spring, opacity: { duration: 0.18 } }}
    >
      <div className="flex shrink-0 items-start gap-[12px] px-[18px] pb-[6px] pt-[16px]">
        <div className="min-w-0 flex-1">
          <div className="line-clamp-2 text-[15px] font-semibold leading-[20px]">{lesson?.title ?? ''}</div>
          {by && (
            <div className="mt-[2px] truncate text-[12px] leading-[16px]" style={{ color: color.faint }}>
              {by}
            </div>
          )}
        </div>
        <button
          type="button"
          className="mt-[-1px] grid h-[22px] w-[22px] shrink-0 cursor-pointer place-items-center rounded-full"
          style={{ background: fill.key, color: fill.keyText }}
          onMouseDown={(e) => e.preventDefault()}
          onClick={closeDrawer}
          aria-label="Close"
        >
          <X size={12} strokeWidth={2.2} />
        </button>
      </div>
      <div ref={scroller} className="relative min-h-0 flex-1 overflow-y-auto px-[8px] pb-[12px]" style={{ scrollbarWidth: 'thin', scrollbarColor: `${fill.track} transparent` }}>
        <Label>Steps</Label>
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
    <div className="px-[10px] pb-[4px] pt-[14px] text-[12px] font-semibold leading-[16px]" style={{ color: color.label }}>
      {children}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Steps
// ---------------------------------------------------------------------------

function Steps({ scroller }: { scroller: RefObject<HTMLDivElement | null> }): ReactNode {
  const { steps, stepId, passed, checks, complete, parts, pendingNext } = useLesson(
    useShallow((s) => ({ steps: s.steps, stepId: s.stepId, passed: s.passed, checks: s.checks, complete: s.complete, parts: s.parts, pendingNext: s.pendingNext }))
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
        const status: StepStatus = passed.includes(s.id) || (cur >= 0 && i < cur) ? 'done' : s.id === stepId ? 'current' : 'locked'
        const k = fresh.indexOf(s.id)
        return <StepRow key={s.id} step={s} status={status} timeW={timeW} checks={status === 'current' ? checks : undefined} enterDelay={k < 0 ? undefined : k * 0.04} />
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

function StepRow({ step, status, timeW, checks, enterDelay }: { step: StepSummary; status: StepStatus; timeW: number; checks?: CheckItem[]; enterDelay?: number }): ReactNode {
  const mounted = useMounted()
  const v = step.video
  const current = status === 'current'
  const canSeek = status !== 'locked' && !!v
  const tone = current ? color.text : status === 'done' ? color.label : color.faint
  const indent = ROW.padX + ROW.icon + ROW.gap + (timeW ? timeW + ROW.gap : 0)
  return (
    <motion.div
      data-step={step.id}
      data-status={status}
      className="rounded-[12px]"
      style={{ background: current ? fill.highlight : fill.clear }}
      initial={enterDelay === undefined ? false : { opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ ...spring, delay: enterDelay ?? 0, opacity: { duration: 0.25, delay: enterDelay ?? 0 } }}
    >
      <button
        type="button"
        className={`flex w-full items-center rounded-[12px] text-left ${canSeek ? `cursor-pointer ${hoverCls}` : 'cursor-default'}`}
        style={{ height: ROW.h, paddingLeft: ROW.padX, paddingRight: ROW.padX, gap: ROW.gap, ...hoverVar }}
        disabled={!canSeek}
        onMouseDown={(e) => e.preventDefault()}
        onClick={() => v && seekVideo(v.start)}
      >
        <span className="relative grid shrink-0 place-items-center" style={{ width: ROW.icon, height: ROW.icon }}>
          <motion.span
            key={status}
            className="grid place-items-center"
            initial={mounted ? { opacity: 0, scale: 0.6 } : false}
            animate={{ opacity: 1, scale: 1 }}
            transition={spring}
          >
            <StepIcon status={status} />
          </motion.span>
        </span>
        {timeW > 0 && (
          <span className="shrink-0 text-[12.5px] tabular-nums" style={{ width: timeW, color: tone }}>
            {v ? stamp(v.start) : ''}
          </span>
        )}
        <span className={`min-w-0 flex-1 truncate text-[14px] ${current ? 'font-semibold' : ''}`} style={{ color: tone }}>
          {step.title}
        </span>
      </button>
      {checks && checks.length > 0 && (
        <motion.div
          data-part="drawer-checks"
          className="pb-[12px]"
          style={{ paddingLeft: indent, paddingRight: ROW.padX }}
          initial={mounted ? { opacity: 0 } : false}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.2 }}
        >
          <CheckList checks={checks} />
        </motion.div>
      )}
    </motion.div>
  )
}

/** done = white check · current = white ring with a dot · locked = the empty ring. Green stays for checks only. */
function StepIcon({ status }: { status: StepStatus }): ReactNode {
  if (status === 'done')
    return (
      <svg width="18" height="18" viewBox="0 0 18 18" className="shrink-0">
        <circle cx="9" cy="9" r="9" fill={color.text} />
        <path d="M5.2 9.3 L7.8 11.8 L12.9 6.4" fill="none" stroke={brand.ink} strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    )
  if (status === 'current')
    return (
      <svg width="18" height="18" viewBox="0 0 18 18" className="shrink-0">
        <circle cx="9" cy="9" r="8.2" fill="none" stroke={color.text} strokeWidth="1.6" />
        <circle cx="9" cy="9" r="3.4" fill={color.text} />
      </svg>
    )
  return <CheckIcon status="pending" active={false} />
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
          <Spinner size={16} c={color.label} />
        ) : (
          <svg width="18" height="18" viewBox="0 0 18 18" className="shrink-0">
            <circle cx="9" cy="9" r="8.2" fill="none" stroke={fill.ring} strokeWidth="1.4" strokeDasharray="2.2 3.2" />
          </svg>
        )}
      </span>
      {timeW > 0 && <span className="shrink-0" style={{ width: timeW }} />}
      <span className="min-w-0 flex-1 truncate text-[13px]" style={{ color: waiting ? color.label : color.faint }}>
        {waiting ? 'Next part is still building' : 'More steps coming'}
      </span>
      {part && (
        <span className="shrink-0 text-[12px] tabular-nums" style={{ color: color.faint }}>
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
  const link = /^https?:\/\//i.test(source.url) ? source.url : undefined
  return (
    <button
      type="button"
      data-source={source.id}
      className={`group flex h-[48px] w-full items-center gap-[12px] rounded-[12px] px-[10px] text-left ${link ? `cursor-pointer ${hoverCls}` : 'cursor-default'}`}
      style={hoverVar}
      disabled={!link}
      onMouseDown={(e) => e.preventDefault()}
      // Electron: main denies the new window and opens https links in the default browser.
      onClick={() => link && window.open(link, '_blank', 'noopener,noreferrer')}
    >
      <KindTile source={source} />
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[13px] font-medium leading-[17px]" style={{ color: color.text }}>
          {source.title}
        </span>
        {source.meta && (
          <span className="block truncate text-[12px] leading-[16px]" style={{ color: color.faint }}>
            {source.meta}
          </span>
        )}
      </span>
      {link && <ArrowUpRight size={13} strokeWidth={1.8} className="shrink-0 opacity-0 transition-opacity group-hover:opacity-100" style={{ color: color.label }} />}
    </button>
  )
}

/** 44×28: the video's thumbnail, or a 16% wash of the kind's pastel with the pastel glyph (theme.kindTone). */
function KindTile({ source }: { source: Source }): ReactNode {
  if (source.kind === 'video') {
    const id = source.videoId ?? parseYouTube(source.url)?.videoId
    return <Thumb w={44} h={28} src={id ? thumbnailFor(id) : undefined} />
  }
  const I = KIND_ICON[source.kind]
  const tone = kindTone[source.kind]
  return (
    <span className="grid h-[28px] w-[44px] shrink-0 place-items-center rounded-[7px]" style={{ background: alpha(tone, 0.16), color: tone }}>
      <I size={14} strokeWidth={1.6} />
    </span>
  )
}

// ---------------------------------------------------------------------------

/** A #RRGGBB token at an alpha (the kind tiles' 16% wash). */
function alpha(hex: string, a: number): string {
  const n = parseInt(hex.slice(1, 7), 16)
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`
}

/** 4:05 · 1:56:30. core `clock()` has no hours, and long videos need them (see Core requests). */
function stamp(t: number): string {
  const s = Math.max(0, Math.round(t))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const ss = String(s % 60).padStart(2, '0')
  return h ? `${h}:${String(m).padStart(2, '0')}:${ss}` : `${m}:${ss}`
}

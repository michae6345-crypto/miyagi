/**
 * The player panel: header, the YouTube video with its gate states, our own controls + chapter
 * timeline, and the chapter list (the lesson's steps as done / current / locked).
 *
 * Electron: fills the `player` window (main docks it to the right 40%).
 * Browser stage: drawn by an overlay layer at the same dock rect (see index.tsx for why).
 */
import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useRef, type CSSProperties, type ReactNode } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { Check, Lock, PanelRight, Pause, Play, RotateCcw, SkipBack, SkipForward, Square, VolumeX } from 'lucide-react'
import type { StepSummary, VideoSegment } from '../../../../../../shared/contracts/events'
import type { Layout } from '../../../../preload/api'
import { cmd } from '../../../../common/wire'
import { bridge, isElectron } from '../../bridge'
import { useLesson, useProgress, useStatus, useThinking } from '../../core/lesson'
import { useAppearance } from '../../core/prefs'
import { sendAction, usePressed } from '../../core/shortcuts'
import { clock, color, copy, glass, radius, spring } from '../../core/theme'
import { Spinner } from '../../core/ui/atoms'
import { MiyagiMark } from '../../core/ui/Mark'
import { dockRect } from './dock'
import { GlassCheck, GlassDot, GlassPrimary, GlassQuiet, GlassSpinner } from './glass'
import { attachPlayer, clipStart, inGate, player, usePlayer } from './store'

/** Frameless window: the header drags it; buttons inside opt out. */
const drag = { WebkitAppRegion: 'drag' } as CSSProperties
const noDrag = { WebkitAppRegion: 'no-drag' } as CSSProperties

/** Stop the lesson: the engine answers lesson.ended (every lesson store resets) + status idle. */
const endLesson = (): void => bridge.send(cmd('end_lesson', {}))
/** "Can I move on?": the engine re-runs the checks now and Claude looks at the screen. */
const checkStep = (): void => sendAction('check_step')
/** Leave this step unfinished and start the next one (never shown green). */
const skipStep = (): void => sendAction('skip_step')

/** The open step's clip (undefined once the step has passed). */
function useOpenSegment(): VideoSegment | undefined {
  return useLesson((s) => (!s.stepId || s.passed.includes(s.stepId) ? undefined : (s.stepVideo ?? s.steps.find((x) => x.id === s.stepId)?.video ?? undefined)))
}

// ---------------------------------------------------------------------------

export function PlayerPanel({ framed = false }: { framed?: boolean }): ReactNode {
  const hasLesson = useLesson((s) => !!s.lesson)
  // Electron: focusable only while hovered, so showing it never steals focus from the editor.
  const hover = (on: boolean) => () => isElectron && bridge.invoke('player:hover', on).catch(() => {})
  return (
    <div
      className="flex h-full w-full flex-col overflow-hidden"
      style={{
        // A glass panel: follows Settings → Appearance (theme.glass flips on <html data-appearance>).
        background: glass.bg,
        color: glass.text,
        ...(framed ? { borderRadius: radius.card, boxShadow: glass.shadow, border: `1px solid ${glass.hairline}`, backdropFilter: 'blur(30px) saturate(1.5)' } : {})
      }}
      onPointerEnter={hover(true)}
      onPointerLeave={hover(false)}
    >
      <Header />
      {hasLesson ? (
        <>
          <div className="shrink-0 px-[12px]">
            <Video />
            <div className="px-[4px]">
              <Controls />
              <Timeline />
              <SourceLine />
            </div>
          </div>
          <Chapters />
        </>
      ) : (
        <div className="grid flex-1 place-items-center px-8 text-center text-[13px]" style={{ color: glass.faint }}>
          The tutorial plays here once a lesson starts.
        </div>
      )}
    </div>
  )
}

function Header(): ReactNode {
  const title = useLesson((s) => s.lesson?.title)
  const hasStep = useLesson((s) => !!s.stepId)
  const { index, total } = useProgress()
  const status = useStatus()
  const appearance = useAppearance()
  return (
    <div className="flex h-[44px] shrink-0 items-center gap-[9px] px-[16px]" style={drag}>
      {/* Like the notch pill: the bonsai on the left, the status dot on the right. On light, the dark-trunk cut. */}
      <MiyagiMark size={14} tone={appearance === 'light' ? 'light' : 'dark'} />
      <span className="truncate text-[13px] font-semibold" style={{ color: glass.text }}>
        {title ?? 'Lesson'}
      </span>
      <span className="flex-1" />
      {hasStep && (
        <span className="shrink-0 text-[12px] tabular-nums" style={{ color: glass.faint }}>
          Step {index + 1} of {total}
        </span>
      )}
      <GlassDot status={status} />
      {hasStep && (
        <button
          className="flex h-[24px] shrink-0 cursor-pointer items-center gap-[5px] rounded-[7px] px-[8px] text-[12px] font-medium text-[var(--glass-label)] hover:bg-[var(--glass-field-hover)] hover:text-[var(--glass-text)]"
          style={noDrag}
          onClick={endLesson}
          title="End this lesson"
          aria-label="End lesson"
        >
          <Square size={10} strokeWidth={2.2} /> End lesson
        </button>
      )}
      {isElectron && (
        <button
          className="grid h-[24px] w-[24px] cursor-pointer place-items-center rounded-[7px] text-[var(--glass-label)] hover:bg-[var(--glass-field-hover)] hover:text-[var(--glass-text)]"
          style={noDrag}
          onClick={() => bridge.invoke('player:dock').catch(() => {})}
          title="Dock to the right"
          aria-label="Dock to the right"
        >
          <PanelRight size={14} strokeWidth={1.7} />
        </button>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Video + gate states
// ---------------------------------------------------------------------------

type Mode = 'loading' | 'error' | 'passed' | 'building' | 'waiting' | 'paused' | undefined

function Video(): ReactNode {
  const host = useRef<HTMLDivElement>(null)
  useEffect(() => attachPlayer(host.current!), [])

  const p = usePlayer(useShallow((s) => ({ ready: s.ready, playing: s.playing, pausedBy: s.pausedBy, resuming: s.resuming, error: s.error, muted: s.muted })))
  const stepOpen = useLesson((s) => !!s.stepId && !s.passed.includes(s.stepId))
  // step.passed {pending}: the next part of a long video is still building (not "lesson complete").
  const pendingNext = useLesson((s) => s.pendingNext)

  const mode: Mode = p.error
    ? 'error'
    : p.resuming && !p.playing
      ? 'passed'
      : !p.ready
        ? 'loading'
        : !p.playing && pendingNext
          ? 'building'
          : !p.playing && stepOpen && (p.pausedBy === 'gate' || p.pausedBy === 'engine')
          ? 'waiting'
          : !p.playing && p.pausedBy === 'user'
            ? 'paused'
            : undefined

  return (
    <div className="relative aspect-video w-full overflow-hidden bg-black" style={{ borderRadius: radius.chip }}>
      {/* The iframe never takes clicks: every control goes through us, so the gate can't be skipped and YouTube links can't open windows. */}
      <div ref={host} className="pointer-events-none absolute inset-0" />
      <button className="absolute inset-0 cursor-pointer" onClick={() => player.toggle()} aria-label="Play or pause" />
      <AnimatePresence>
        {mode === 'waiting' && <Waiting key="waiting" />}
        {mode === 'passed' && <Passed key="passed" />}
        {mode === 'building' && <BuildingNext key="building" />}
        {mode === 'paused' && <PausedGlyph key="paused" />}
        {mode === 'loading' && <Loading key="loading" />}
        {mode === 'error' && <ErrorState key="error" message={p.error!} />}
      </AnimatePresence>
      {p.muted && (
        <button
          className="absolute bottom-[10px] left-[10px] flex h-[26px] cursor-pointer items-center gap-[6px] rounded-full bg-black/65 px-[10px] text-[12px] font-medium text-white/85 hover:text-white"
          onClick={() => player.unmute()}
        >
          <VolumeX size={13} strokeWidth={1.8} /> Sound off · Unmute
        </button>
      )}
    </div>
  )
}

const fade = { initial: { opacity: 0 }, animate: { opacity: 1 }, exit: { opacity: 0 }, transition: { duration: 0.28 } }

/**
 * The waiting / building / passed states sit on the video as frosted glass in the panel's appearance
 * (dark: smoked, light: milky), so they read as part of the panel. Blur + the panel color at 80%.
 */
function GlassScrim({ children, strength = 0.8 }: { children: ReactNode; strength?: number }): ReactNode {
  return (
    <motion.div className="pointer-events-none absolute inset-0 grid place-items-center backdrop-blur-[10px]" style={{ color: glass.text }} {...fade}>
      <div className="absolute inset-0" style={{ background: glass.bg, opacity: strength }} />
      <div className="relative">{children}</div>
    </motion.div>
  )
}
const rise = { initial: { opacity: 0, y: 6 }, animate: { opacity: 1, y: 0 }, transition: { ...spring, delay: 0.06 } }

/** Calm "your turn" state: the clip is over, the step's checks decide when it continues. */
function Waiting(): ReactNode {
  const checks = useLesson((s) => s.checks)
  const offtrack = useLesson((s) => !!s.offtrack)
  const thinking = useThinking()
  const pressed = usePressed((s) => s.kind)
  const checking = thinking && pressed === 'check_step'
  const skipping = thinking && pressed === 'skip_step'
  const done = checks.filter((c) => c.status === 'pass').length
  // Apricot only for off track; otherwise Miyagi is watching (gray).
  const tone = offtrack ? glass.offTrack : color.gray
  return (
    <GlassScrim>
      <motion.div className="flex flex-col items-center px-6 text-center" {...rise}>
        {/* One line, the status dot beside it (amber off track, gray watching). No eyebrow. */}
        <div className="flex items-center gap-[8px] text-[19px] font-semibold leading-tight">
          <span className="h-[7px] w-[7px] shrink-0 rounded-full" style={{ background: tone }} />
          Waiting for your checks
        </div>
        {checks.length > 0 && (
          <div className="mt-[10px] flex items-center gap-[8px] text-[13px]" style={{ color: glass.label }}>
            <span className="flex gap-[4px]">
              {checks.map((c) => (
                <motion.span
                  key={c.id}
                  className="h-[7px] w-[7px] rounded-full"
                  initial={false}
                  animate={{ background: c.status === 'pass' ? glass.pass : c.status === 'fail' ? glass.offTrack : glass.faint }}
                  transition={{ duration: 0.25 }}
                />
              ))}
            </span>
            {done} of {checks.length} pass
          </div>
        )}
        <div className="pointer-events-auto mt-[16px] flex flex-wrap items-center justify-center gap-[8px]">
          <GlassPrimary label={checking ? 'Checking…' : 'Check my work'} icon={Check} onClick={checkStep} disabled={checking} />
          <GlassQuiet label="Replay" icon={RotateCcw} onClick={() => player.replayStep()} />
          <GlassQuiet label="Skip step" icon={SkipForward} onClick={skipStep} busy={skipping} />
        </div>
      </motion.div>
    </GlassScrim>
  )
}

/** step.passed with pending: the video holds where it is until the engine adds the next part. */
function BuildingNext(): ReactNode {
  const parts = useLesson((s) => s.parts)
  return (
    <GlassScrim>
      <motion.div className="flex flex-col items-center px-6 text-center" {...rise}>
        <div className="flex items-center gap-[9px] text-[17px] font-semibold leading-tight">
          <GlassSpinner size={16} />
          Next part is still building
        </div>
        {parts && parts.total > 0 && (
          <div className="mt-[8px] text-[13px] tabular-nums" style={{ color: glass.label }}>
            {parts.done} of {parts.total} parts ready
          </div>
        )}
      </motion.div>
    </GlassScrim>
  )
}

function Passed(): ReactNode {
  return (
    <GlassScrim strength={0.7}>
      <motion.div className="flex flex-col items-center" {...rise}>
        <GlassCheck size={38} />
        <div className="mt-[14px] text-[15px] font-semibold">{copy.passed}</div>
      </motion.div>
    </GlassScrim>
  )
}

function PausedGlyph(): ReactNode {
  return (
    <motion.div className="pointer-events-none absolute inset-0 grid place-items-center bg-black/30" {...fade}>
      <div className="grid h-[54px] w-[54px] place-items-center rounded-full bg-black/55 text-white">
        <Play size={22} fill="currentColor" strokeWidth={0} className="ml-[3px]" />
      </div>
    </motion.div>
  )
}

function Loading(): ReactNode {
  return (
    <motion.div className="pointer-events-none absolute inset-0 grid place-items-center" {...fade}>
      <Spinner size={22} />
    </motion.div>
  )
}

function ErrorState({ message }: { message: string }): ReactNode {
  return (
    <motion.div className="pointer-events-none absolute inset-0 grid place-items-center bg-black/70 px-8 text-center" {...fade}>
      <div>
        <div className="text-[11px] font-semibold uppercase tracking-[0.08em]" style={{ color: color.label }}>
          Video unavailable
        </div>
        <div className="mt-[6px] text-[14px] text-white/80">{message}</div>
      </div>
    </motion.div>
  )
}

// ---------------------------------------------------------------------------
// Controls + timeline
// ---------------------------------------------------------------------------

function IconButton({ children, onClick, label, disabled }: { children: ReactNode; onClick: () => void; label: string; disabled?: boolean }): ReactNode {
  return (
    <motion.button
      className="grid h-[30px] w-[30px] cursor-pointer place-items-center rounded-[9px] text-[var(--glass-text)] hover:bg-[var(--glass-field-hover)] disabled:cursor-default disabled:text-[var(--glass-faint)] disabled:hover:bg-transparent"
      whileTap={disabled ? undefined : { scale: 0.94 }}
      transition={{ duration: 0.09 }}
      onClick={onClick}
      disabled={disabled}
      title={label}
      aria-label={label}
    >
      {children}
    </motion.button>
  )
}

function Controls(): ReactNode {
  const p = usePlayer(useShallow((s) => ({ t: s.t, duration: s.duration, playing: s.playing })))
  const seg = useOpenSegment()
  const pendingNext = useLesson((s) => s.pendingNext)
  const held = !p.playing && inGate(p.t)
  const heldLabel = pendingNext ? 'Opens when the next part is ready' : 'Opens when your checks pass'
  return (
    <div className="mt-[8px] flex h-[32px] items-center gap-[2px]">
      <IconButton onClick={() => player.toggle()} label={held ? heldLabel : p.playing ? 'Pause' : 'Play'} disabled={held}>
        {held ? <Lock size={15} strokeWidth={1.8} /> : p.playing ? <Pause size={16} fill="currentColor" strokeWidth={0} /> : <Play size={16} fill="currentColor" strokeWidth={0} />}
      </IconButton>
      <IconButton onClick={() => player.replayStep()} label="Back to the step’s start">
        <SkipBack size={15} strokeWidth={1.8} />
      </IconButton>
      {seg && (
        <IconButton onClick={skipStep} label="Skip this step">
          <SkipForward size={15} strokeWidth={1.8} />
        </IconButton>
      )}
      <span className="ml-[6px] text-[13px] tabular-nums" style={{ color: glass.label }}>
        {clock(p.t)} <span style={{ color: glass.faint }}>/ {p.duration ? clock(p.duration) : '–:––'}</span>
      </span>
      <span className="flex-1" />
      {seg ? (
        <button
          className="flex h-[24px] cursor-pointer items-center gap-[5px] rounded-[7px] px-[6px] text-[12px] tabular-nums text-[var(--glass-faint)] hover:bg-[var(--glass-field-hover)] hover:text-[var(--glass-text)]"
          onClick={checkStep}
          title="The video holds here until the step's checks pass. Click to check now."
        >
          <Lock size={11} strokeWidth={2} /> Checks at {clock(seg.end)} · Check now
        </button>
      ) : (
        pendingNext && (
          <span className="text-[12px]" style={{ color: glass.faint }}>
            Next part building
          </span>
        )
      )}
    </div>
  )
}

/** Chapter timeline: one segment per step, played part filled, a ring where the open step's gate is. */
function Timeline(): ReactNode {
  const { steps, stepId, passed } = useLesson(useShallow((s) => ({ steps: s.steps, stepId: s.stepId, passed: s.passed })))
  const { t, duration } = usePlayer(useShallow((s) => ({ t: s.t, duration: s.duration })))
  const seg = useOpenSegment()
  const span = Math.max(duration, ...steps.map((s) => s.video?.end ?? 0), 1)
  const cur = steps.findIndex((s) => s.id === stepId)
  const pct = (v: number): string => `${(Math.min(Math.max(v, 0), span) / span) * 100}%`

  return (
    <div
      className="relative mt-[6px] h-[16px] cursor-pointer"
      onClick={(e) => {
        const r = e.currentTarget.getBoundingClientRect()
        player.scrub(((e.clientX - r.left) / r.width) * span)
      }}
    >
      <div className="absolute inset-x-0 top-[6px] h-[4px] rounded-full" style={{ background: glass.field }} />
      {steps.map((s, i) => {
        if (!s.video) return null
        const locked = cur >= 0 ? i > cur && !passed.includes(s.id) : true
        const start = clipStart(s.video)
        const played = Math.min(Math.max((t - start) / (s.video.end - start), 0), 1)
        return (
          <div
            key={s.id}
            className="absolute top-[6px] h-[4px] overflow-hidden rounded-full"
            style={{ left: `calc(${pct(start)} + 1px)`, width: `calc(${pct(s.video.end - start)} - 2px)`, background: locked ? glass.rule : glass.track }}
          >
            <div className="h-full origin-left" style={{ background: glass.button, transform: `scaleX(${played})` }} />
          </div>
        )
      })}
      {seg && (
        <div
          className="absolute top-[3px] h-[10px] w-[10px] -translate-x-1/2 rounded-full border-2"
          style={{ left: pct(seg.end), background: glass.bg, borderColor: glass.label }}
          title={`Holds at ${clock(seg.end)}`}
        />
      )}
      <div className="absolute top-[3px] h-[10px] w-[10px] -translate-x-1/2 rounded-full" style={{ left: pct(t), background: glass.button }} />
    </div>
  )
}

function SourceLine(): ReactNode {
  const source = useLesson((s) => s.lesson?.sources.find((x) => x.kind === 'video'))
  const { title, standIn } = usePlayer(useShallow((s) => ({ title: s.title, standIn: s.standIn })))
  return (
    <div className="mt-[10px]">
      <div className="truncate text-[15px] font-semibold">{source?.title ?? title ?? 'Tutorial'}</div>
      <div className="truncate text-[12px]" style={{ color: glass.faint }}>
        {standIn ? (title ? `${title} · stand-in video` : 'Stand-in video') : (source?.meta ?? '')}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Chapters
// ---------------------------------------------------------------------------

type ChapterStatus = 'done' | 'skipped' | 'current' | 'locked'

/**
 * The lesson's steps. A long video builds part by part: lesson.updated replaces `steps` (ids stable,
 * new ones appended), so rows are keyed by id and only rows that weren't there before fade in
 * (AnimatePresence initial={false}: the first list doesn't animate). While the lesson isn't
 * complete, a quiet last row says more steps are coming.
 */
function Chapters(): ReactNode {
  const { steps, stepId, passed, skipped, complete, parts } = useLesson(
    useShallow((s) => ({ steps: s.steps, stepId: s.stepId, passed: s.passed, skipped: s.skipped, complete: s.complete, parts: s.parts }))
  )
  const playing = usePlayer((s) => s.playing)
  const cur = steps.findIndex((s) => s.id === stepId)
  const list = useRef<HTMLDivElement>(null)

  // Keep the current row in view (long lessons scroll). Only this list scrolls, never the page.
  useEffect(() => {
    const box = list.current
    const row = box?.querySelector<HTMLElement>(`[data-step="${CSS.escape(stepId ?? '')}"]`)
    if (!box || !row) return
    const top = row.offsetTop - box.offsetTop
    if (top < box.scrollTop) box.scrollTo({ top, behavior: 'smooth' })
    else if (top + row.offsetHeight > box.scrollTop + box.clientHeight) box.scrollTo({ top: top + row.offsetHeight - box.clientHeight, behavior: 'smooth' })
  }, [stepId])

  return (
    <div className="mt-[14px] flex min-h-0 flex-1 flex-col px-[12px] pb-[12px]">
      <div className="px-[10px] pb-[6px] text-[13px] font-semibold" style={{ color: glass.text }}>
        Chapters
      </div>
      <div ref={list} className="relative min-h-0 flex-1 overflow-y-auto">
        <AnimatePresence initial={false}>
          {steps.map((s, i) => {
            const status: ChapterStatus = skipped.includes(s.id) ? 'skipped' : passed.includes(s.id) || (cur >= 0 && i < cur) ? 'done' : s.id === stepId ? 'current' : 'locked'
            return (
              <motion.div key={s.id} data-step={s.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={spring}>
                <Chapter step={s} status={status} now={s.id === stepId} playing={playing} />
                {s.id === stepId && <NowInstructions />}
              </motion.div>
            )
          })}
          {!complete && (
            <motion.div key="more" layout="position" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.25 }}>
              <MoreComing parts={parts} />
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  )
}

/** The quiet last row while a long video is still building. */
function MoreComing({ parts }: { parts?: { done: number; failed: number; total: number } }): ReactNode {
  return (
    <div className="flex h-[38px] w-full items-center gap-[11px] px-[10px]">
      <span className="grid w-[18px] shrink-0 place-items-center">
        <GlassSpinner size={13} c={glass.faint} />
      </span>
      <span className="flex-1 truncate text-[14px]" style={{ color: glass.faint }}>
        More steps coming
      </span>
      {parts && parts.total > 0 && (
        <span className="shrink-0 text-[12px] tabular-nums" style={{ color: glass.faint }}>
          {parts.done} of {parts.total} parts
        </span>
      )}
    </div>
  )
}

/** Under the current chapter: what to do right now (the step's instructions), so a title alone never leaves you guessing. */
function NowInstructions(): ReactNode {
  const text = useLesson((s) => s.instructions)
  if (!text) return null
  return (
    <div className="px-[10px] pb-[8px] pl-[39px] pt-[2px] text-[13px] leading-[1.45]" style={{ color: glass.label }}>
      {text}
    </div>
  )
}

function Chapter({ step, status, now, playing }: { step: StepSummary; status: ChapterStatus; now: boolean; playing: boolean }): ReactNode {
  const locked = status === 'locked'
  const v = step.video
  return (
    <button
      className={`flex h-[38px] w-full items-center gap-[11px] rounded-[10px] px-[10px] text-left ${now ? 'bg-[var(--glass-field-hover)]' : locked || !v ? '' : 'hover:bg-[var(--glass-field)]'} ${locked || !v ? 'cursor-default' : 'cursor-pointer'}`}
      disabled={locked || !v}
      onClick={() => v && player.seek(clipStart(v), true)}
      title={locked ? 'Unlocks when you get there' : undefined}
    >
      <span className="grid w-[18px] shrink-0 place-items-center">
        {status === 'done' ? (
          <GlassCheck />
        ) : status === 'skipped' ? (
          <SkipForward size={13} strokeWidth={1.8} style={{ color: glass.faint }} />
        ) : status === 'current' ? (
          <NowGlyph playing={playing} />
        ) : (
          <Lock size={13} strokeWidth={1.8} style={{ color: glass.faint }} />
        )}
      </span>
      <span className="w-[40px] shrink-0 text-[13px] tabular-nums" style={{ color: locked ? glass.faint : now ? glass.text : glass.label }}>
        {v ? clock(clipStart(v)) : ''}
      </span>
      <span className={`flex-1 truncate text-[14px] ${now ? 'font-semibold' : ''}`} style={{ color: now ? glass.text : locked ? glass.faint : glass.label }}>
        {step.title}
      </span>
    </button>
  )
}

/** The current chapter: three bars that move while the video plays, still when it's held. */
function NowGlyph({ playing }: { playing: boolean }): ReactNode {
  return (
    <span className="flex h-[14px] items-end gap-[2px]">
      {[0, 1, 2].map((i) => (
        <motion.span
          key={i}
          className="w-[3px] origin-bottom rounded-full"
          style={{ height: 14, background: glass.button }}
          animate={playing ? { scaleY: [0.35, 1, 0.5, 0.85, 0.35] } : { scaleY: [0.45, 0.8, 0.6][i] }}
          transition={playing ? { duration: 1.1, repeat: Infinity, delay: i * 0.18, ease: 'easeInOut' } : spring}
        />
      ))}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Where it renders
// ---------------------------------------------------------------------------

/** Electron: the `player` window's whole content. */
export function PlayerWindow(): ReactNode {
  return <PlayerPanel />
}

/** Browser stage only: the same panel at the dock rect, under the spotlight/cards like in Electron. */
export function StagePlayer({ layout }: { layout: Layout }): ReactNode {
  // No player for a "Just teach me" lesson (lesson.mode "lesson": no video at all).
  const hasLesson = useLesson((s) => !!s.lesson && s.lesson.mode !== 'lesson')
  if (isElectron) return null
  const r = dockRect(layout.workArea)
  return (
    <AnimatePresence>
      {hasLesson && (
        <motion.div
          key="player"
          data-ui
          className="absolute"
          style={{ left: r.x, top: r.y, width: r.width, height: r.height }}
          initial={{ opacity: 0, x: 24 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: 24 }}
          transition={spring}
        >
          <PlayerPanel framed />
        </motion.div>
      )}
    </AnimatePresence>
  )
}

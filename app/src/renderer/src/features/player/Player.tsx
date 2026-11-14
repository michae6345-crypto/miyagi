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
import { Lock, PanelRight, Pause, Play, RotateCcw, SkipBack, VolumeX } from 'lucide-react'
import type { StepSummary, VideoSegment } from '../../../../../../shared/contracts/events'
import type { Layout } from '../../../../preload/api'
import { bridge, isElectron } from '../../bridge'
import { useLesson, useProgress, useStatus } from '../../core/lesson'
import { clock, color, radius, shadow, spring } from '../../core/theme'
import { CheckIcon, Spinner, StatusDot } from '../../core/ui/atoms'
import { dockRect } from './dock'
import { attachPlayer, inGate, player, usePlayer } from './store'

/** Frameless window: the header drags it; buttons inside opt out. */
const drag = { WebkitAppRegion: 'drag' } as CSSProperties
const noDrag = { WebkitAppRegion: 'no-drag' } as CSSProperties

/** The open step's clip (undefined once the step has passed). */
function useOpenSegment(): VideoSegment | undefined {
  return useLesson((s) => (!s.stepId || s.passed.includes(s.stepId) ? undefined : (s.stepVideo ?? s.steps.find((x) => x.id === s.stepId)?.video)))
}

// ---------------------------------------------------------------------------

export function PlayerPanel({ framed = false }: { framed?: boolean }): ReactNode {
  const hasLesson = useLesson((s) => !!s.lesson)
  // Electron: focusable only while hovered, so showing it never steals focus from the editor.
  const hover = (on: boolean) => () => isElectron && bridge.invoke('player:hover', on).catch(() => {})
  return (
    <div
      className="flex h-full w-full flex-col overflow-hidden text-white"
      style={{
        background: color.glass,
        ...(framed ? { borderRadius: radius.card, boxShadow: shadow, border: `1px solid ${color.hairline}`, backdropFilter: 'blur(30px) saturate(1.5)' } : {})
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
        <div className="grid flex-1 place-items-center px-8 text-center text-[13px]" style={{ color: color.faint }}>
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
  return (
    <div className="flex h-[44px] shrink-0 items-center gap-[9px] px-[16px]" style={drag}>
      <StatusDot status={status} />
      <span className="truncate text-[13px] font-semibold text-white/90">{title ?? 'Lesson'}</span>
      <span className="flex-1" />
      {hasStep && (
        <span className="shrink-0 text-[12px] tabular-nums" style={{ color: color.faint }}>
          Step {index + 1} of {total}
        </span>
      )}
      {isElectron && (
        <button
          className="grid h-[24px] w-[24px] cursor-pointer place-items-center rounded-[7px] text-white/55 hover:bg-white/10 hover:text-white"
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

type Mode = 'loading' | 'error' | 'passed' | 'waiting' | 'paused' | undefined

function Video(): ReactNode {
  const host = useRef<HTMLDivElement>(null)
  useEffect(() => attachPlayer(host.current!), [])

  const p = usePlayer(useShallow((s) => ({ ready: s.ready, playing: s.playing, pausedBy: s.pausedBy, resuming: s.resuming, error: s.error, muted: s.muted })))
  const stepOpen = useLesson((s) => !!s.stepId && !s.passed.includes(s.stepId))

  const mode: Mode = p.error
    ? 'error'
    : p.resuming && !p.playing
      ? 'passed'
      : !p.ready
        ? 'loading'
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
const rise = { initial: { opacity: 0, y: 6 }, animate: { opacity: 1, y: 0 }, transition: { ...spring, delay: 0.06 } }

/** Calm "your turn" state: the clip is over, the step's checks decide when it continues. */
function Waiting(): ReactNode {
  const checks = useLesson((s) => s.checks)
  const offtrack = useLesson((s) => !!s.offtrack)
  const done = checks.filter((c) => c.status === 'pass').length
  const tone = offtrack ? color.amber : color.accent
  return (
    <motion.div className="pointer-events-none absolute inset-0 grid place-items-center bg-black/55 backdrop-blur-[10px]" {...fade}>
      <motion.div className="flex flex-col items-center px-6 text-center" {...rise}>
        <div className="flex items-center gap-[7px] text-[11px] font-semibold uppercase tracking-[0.08em]" style={{ color: tone }}>
          <span className="h-[6px] w-[6px] rounded-full" style={{ background: tone }} />
          {offtrack ? 'Something’s off' : 'Your turn'}
        </div>
        <div className="mt-[8px] text-[19px] font-semibold leading-tight">Waiting for your checks</div>
        {checks.length > 0 ? (
          <div className="mt-[10px] flex items-center gap-[8px] text-[13px]" style={{ color: color.label }}>
            <span className="flex gap-[4px]">
              {checks.map((c) => (
                <motion.span
                  key={c.id}
                  className="h-[7px] w-[7px] rounded-full"
                  initial={false}
                  animate={{ background: c.status === 'pass' ? color.green : c.status === 'fail' ? color.amber : 'rgba(255,255,255,.25)' }}
                  transition={{ duration: 0.25 }}
                />
              ))}
            </span>
            {done} of {checks.length} pass
          </div>
        ) : (
          <div className="mt-[10px] text-[13px]" style={{ color: color.label }}>
            The video continues when they pass.
          </div>
        )}
        <button
          className="pointer-events-auto mt-[16px] flex h-[30px] cursor-pointer items-center gap-[6px] rounded-full bg-white/12 px-[13px] text-[13px] font-medium text-white/90 hover:bg-white/20"
          onClick={() => player.replayStep()}
        >
          <RotateCcw size={13} strokeWidth={1.9} /> Replay step
        </button>
      </motion.div>
    </motion.div>
  )
}

function Passed(): ReactNode {
  return (
    <motion.div className="pointer-events-none absolute inset-0 grid place-items-center bg-black/45 backdrop-blur-[10px]" {...fade}>
      <motion.div className="flex flex-col items-center" {...rise}>
        <div style={{ transform: 'scale(2.1)' }}>
          <CheckIcon status="pass" active={false} />
        </div>
        <div className="mt-[16px] text-[15px] font-semibold">Passed</div>
      </motion.div>
    </motion.div>
  )
}

function PausedGlyph(): ReactNode {
  return (
    <motion.div className="pointer-events-none absolute inset-0 grid place-items-center bg-black/30" {...fade}>
      <div className="grid h-[54px] w-[54px] place-items-center rounded-full bg-black/55">
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
        <div className="text-[11px] font-semibold uppercase tracking-[0.08em]" style={{ color: color.amber }}>
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
      className="grid h-[30px] w-[30px] cursor-pointer place-items-center rounded-[9px] text-white/85 hover:bg-white/10 disabled:cursor-default disabled:text-white/35 disabled:hover:bg-transparent"
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
  const held = !p.playing && !!seg && inGate(p.t)
  return (
    <div className="mt-[8px] flex h-[32px] items-center gap-[2px]">
      <IconButton onClick={() => player.toggle()} label={held ? 'Opens when your checks pass' : p.playing ? 'Pause' : 'Play'} disabled={held}>
        {held ? <Lock size={15} strokeWidth={1.8} /> : p.playing ? <Pause size={16} fill="currentColor" strokeWidth={0} /> : <Play size={16} fill="currentColor" strokeWidth={0} />}
      </IconButton>
      <IconButton onClick={() => player.replayStep()} label="Back to the step’s start">
        <SkipBack size={15} strokeWidth={1.8} />
      </IconButton>
      <span className="ml-[6px] text-[13px] tabular-nums text-white/70">
        {clock(p.t)} <span style={{ color: color.faint }}>/ {p.duration ? clock(p.duration) : '–:––'}</span>
      </span>
      <span className="flex-1" />
      {seg && (
        <span className="flex items-center gap-[5px] text-[12px] tabular-nums" style={{ color: color.faint }} title="The video holds here until the step's checks pass">
          <Lock size={11} strokeWidth={2} /> Checks at {clock(seg.end)}
        </span>
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
      <div className="absolute inset-x-0 top-[6px] h-[4px] rounded-full bg-white/[.07]" />
      {steps.map((s, i) => {
        if (!s.video) return null
        const locked = cur >= 0 ? i > cur && !passed.includes(s.id) : true
        const played = Math.min(Math.max((t - s.video.start) / (s.video.end - s.video.start), 0), 1)
        return (
          <div
            key={s.id}
            className="absolute top-[6px] h-[4px] overflow-hidden rounded-full"
            style={{ left: `calc(${pct(s.video.start)} + 1px)`, width: `calc(${pct(s.video.end - s.video.start)} - 2px)`, background: locked ? 'rgba(255,255,255,.1)' : 'rgba(255,255,255,.24)' }}
          >
            <div className="h-full origin-left" style={{ background: color.accent, transform: `scaleX(${played})` }} />
          </div>
        )
      })}
      {seg && (
        <div
          className="absolute top-[3px] h-[10px] w-[10px] -translate-x-1/2 rounded-full border-2"
          style={{ left: pct(seg.end), borderColor: 'rgba(255,255,255,.7)', background: color.glass }}
          title={`Holds at ${clock(seg.end)}`}
        />
      )}
      <div className="absolute top-[3px] h-[10px] w-[10px] -translate-x-1/2 rounded-full bg-white shadow" style={{ left: pct(t) }} />
    </div>
  )
}

function SourceLine(): ReactNode {
  const source = useLesson((s) => s.lesson?.sources.find((x) => x.kind === 'video'))
  const { title, standIn } = usePlayer(useShallow((s) => ({ title: s.title, standIn: s.standIn })))
  return (
    <div className="mt-[10px]">
      <div className="truncate text-[15px] font-semibold">{source?.title ?? title ?? 'Tutorial'}</div>
      <div className="truncate text-[12px]" style={{ color: color.faint }}>
        {standIn ? `Stand-in video${title ? `: ${title}` : ''} (the lesson’s video id is a placeholder)` : (source?.meta ?? '')}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Chapters
// ---------------------------------------------------------------------------

type ChapterStatus = 'done' | 'current' | 'locked'

function Chapters(): ReactNode {
  const { steps, stepId, passed } = useLesson(useShallow((s) => ({ steps: s.steps, stepId: s.stepId, passed: s.passed })))
  const playing = usePlayer((s) => s.playing)
  const cur = steps.findIndex((s) => s.id === stepId)
  return (
    <div className="mt-[14px] flex min-h-0 flex-1 flex-col px-[12px] pb-[12px]">
      <div className="px-[10px] pb-[6px] text-[13px] font-semibold text-white/80">Chapters</div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        {steps.map((s, i) => {
          const status: ChapterStatus = passed.includes(s.id) || (cur >= 0 && i < cur) ? 'done' : s.id === stepId ? 'current' : 'locked'
          return <Chapter key={s.id} step={s} status={status} now={s.id === stepId} playing={playing} />
        })}
      </div>
    </div>
  )
}

function Chapter({ step, status, now, playing }: { step: StepSummary; status: ChapterStatus; now: boolean; playing: boolean }): ReactNode {
  const locked = status === 'locked'
  const v = step.video
  return (
    <button
      className={`flex h-[38px] w-full items-center gap-[11px] rounded-[10px] px-[10px] text-left ${now ? 'bg-white/[.08]' : locked || !v ? '' : 'hover:bg-white/[.05]'} ${locked || !v ? 'cursor-default' : 'cursor-pointer'}`}
      disabled={locked || !v}
      onClick={() => v && player.seek(v.start, true)}
      title={locked ? 'Unlocks when you get there' : undefined}
    >
      <span className="grid w-[18px] shrink-0 place-items-center">
        {status === 'done' ? (
          <CheckIcon status="pass" active={false} />
        ) : status === 'current' ? (
          <NowGlyph playing={playing} />
        ) : (
          <Lock size={13} strokeWidth={1.8} className="text-white/30" />
        )}
      </span>
      <span className="w-[40px] shrink-0 text-[13px] tabular-nums" style={{ color: locked ? color.faint : color.accent }}>
        {v ? clock(v.start) : ''}
      </span>
      <span className={`flex-1 truncate text-[14px] ${now ? 'font-semibold text-white' : locked ? 'text-white/40' : 'text-white/75'}`}>{step.title}</span>
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
          style={{ height: 14, background: color.accent }}
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
  const hasLesson = useLesson((s) => !!s.lesson)
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

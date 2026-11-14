/**
 * The Dynamic-Island pill. ONE black object that morphs between every state:
 *   idle → building → compact  (34px pill hugging the notch)
 *   overview (hover) · offtrack card · success card · diagram  (grow downward from the pill's center)
 * Width, height and radius animate together on the spring; content crossfades
 * (old out in 80ms, new in after 60ms, rising 4px). The window never resizes.
 */
import { AnimatePresence, motion } from 'motion/react'
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { Lightbulb, MessageSquareText, Play, Sparkles, Wand2, X } from 'lucide-react'
import { bridge } from '../bridge'
import { cmd } from '../../../common/wire'
import { useLesson, useProgress, useStatus, type Status } from '../store'
import { CheckList, Kbd, ProgressRing, Spinner, StatusDot, Thumb } from '../ui/atoms'
import { clock, color, pill, spring, springOut } from '../theme'
import { DiagramView } from './Diagram'

type Mode = 'idle' | 'building' | 'compact' | 'overview' | 'offtrack' | 'success' | 'card' | 'diagram'

const WIDTH: Partial<Record<Mode, number>> = { overview: 440, offtrack: 460, success: 420, card: 420, diagram: 640 }
const isPill = (m: Mode): boolean => m === 'idle' || m === 'building' || m === 'compact'

export function Island({ top }: { top: number }): ReactNode {
  const s = useLesson(
    useShallow((x) => ({
      lesson: x.lesson,
      building: x.building,
      stepId: x.stepId,
      offtrack: x.offtrack,
      offtrackOpen: x.offtrackOpen,
      success: x.success,
      card: x.card,
      diagramOpen: x.diagramOpen,
      diagram: x.diagram,
      passFlash: x.passFlash
    }))
  )
  const [hover, setHover] = useState(false)
  const [landing, setLanding] = useState(false)
  const hoverTimer = useRef<ReturnType<typeof setTimeout>>(undefined)

  // The launcher just shrank onto our exact pixels: appear at its size, then spring to ours.
  useEffect(
    () =>
      bridge.on('pill:receive', () => {
        useLesson.getState().startBuild()
        setLanding(true)
        requestAnimationFrame(() => requestAnimationFrame(() => setLanding(false)))
      }),
    []
  )

  // Success card auto-hides.
  useEffect(() => {
    if (!s.success) return
    const t = setTimeout(() => useLesson.setState({ success: undefined }), 3800)
    return () => clearTimeout(t)
  }, [s.success])

  const mode: Mode = !s.lesson && !s.building
    ? 'idle'
    : !s.stepId
      ? 'building'
      : s.diagramOpen && s.diagram
        ? 'diagram'
        : s.offtrackOpen && s.offtrack
          ? 'offtrack'
          : s.success
            ? 'success'
            : s.card
              ? 'card'
              : hover
              ? s.offtrack
                ? 'offtrack'
                : 'overview'
              : 'compact'

  // Measure whichever layer is active; the container springs to its size.
  const [active, setActive] = useState<HTMLDivElement | null>(null)
  const bindActive = useCallback((el: HTMLDivElement | null) => {
    if (el) setActive(el)
  }, [])
  const [size, setSize] = useState<{ w: number; h: number }>({ w: 120, h: pill.height })
  useLayoutEffect(() => {
    if (!active) return
    const measure = (): void => {
      const fixed = WIDTH[mode]
      setSize({ w: fixed ?? Math.ceil(active.offsetWidth), h: fixed ? Math.ceil(active.offsetHeight) : pill.height })
    }
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(active)
    return () => ro.disconnect()
  }, [active, mode])

  const enter = (): void => {
    clearTimeout(hoverTimer.current)
    hoverTimer.current = setTimeout(() => setHover(true), 150)
  }
  const leave = (): void => {
    clearTimeout(hoverTimer.current)
    hoverTimer.current = setTimeout(() => setHover(false), 300)
  }

  const w = landing ? pill.landingWidth : size.w
  const h = landing ? pill.height : size.h

  return (
    <div className="pointer-events-none absolute inset-x-0 flex justify-center" style={{ top }}>
      <motion.div
        data-hit
        className="pointer-events-auto relative overflow-hidden text-white"
        style={{
          background: color.island,
          boxShadow: isPill(mode) ? '0 2px 10px rgba(0,0,0,.25)' : '0 24px 60px rgba(0,0,0,.5)',
          transformOrigin: '50% 0%'
        }}
        initial={false}
        animate={{ width: w, height: h, borderRadius: isPill(mode) ? pill.height / 2 : 24 }}
        transition={landing ? { duration: 0 } : isPill(mode) ? springOut : spring}
        onMouseEnter={enter}
        onMouseLeave={leave}
      >
        {/* Step passed: the pill flashes green (tint 0 → .25 → 0 over 600ms). */}
        <motion.div
          key={s.passFlash}
          className="pointer-events-none absolute inset-0"
          style={{ background: color.green }}
          initial={{ opacity: 0 }}
          animate={{ opacity: s.passFlash ? [0, 0.25, 0] : 0 }}
          transition={{ duration: 0.6, ease: 'easeInOut' }}
        />
        <AnimatePresence initial={false}>
          <motion.div
            key={mode}
            ref={bindActive}
            className="absolute left-1/2 top-0"
            style={{ x: '-50%', width: WIDTH[mode] ?? 'max-content' }}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0, transition: { duration: 0.2, delay: 0.06, ease: 'easeOut' } }}
            exit={{ opacity: 0, transition: { duration: 0.08 } }}
          >
            {mode === 'idle' && <IdleContent />}
            {mode === 'building' && <BuildingContent />}
            {mode === 'compact' && <CompactContent />}
            {mode === 'overview' && <OverviewContent />}
            {mode === 'offtrack' && <OfftrackContent />}
            {mode === 'success' && <SuccessContent />}
            {mode === 'card' && <CardContent />}
            {mode === 'diagram' && <DiagramView />}
          </motion.div>
        </AnimatePresence>
      </motion.div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Pill-sized content (34px tall, width hugs the content)
// ---------------------------------------------------------------------------

function IdleContent(): ReactNode {
  return (
    <button
      className="flex h-[34px] cursor-pointer items-center gap-[8px] whitespace-nowrap pl-[13px] pr-[7px] text-[13px] font-medium text-white/85"
      onClick={() => bridge.emit('launcher:toggle')}
    >
      <Sparkles size={14} strokeWidth={1.75} />
      <span>Learn anything</span>
      <Kbd className="!h-[20px]">{bridge.platform.keys.launcher}</Kbd>
    </button>
  )
}

function BuildingContent(): ReactNode {
  const msg = useLesson((x) => x.buildingMessage)
  return (
    <div className="flex h-[34px] items-center gap-[9px] whitespace-nowrap px-[14px] text-[13px] font-medium">
      <Spinner size={14} />
      <AnimatePresence mode="popLayout" initial={false}>
        <motion.span key={msg ?? 'x'} className="text-white/85" initial={{ opacity: 0, y: 5 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -5 }}>
          {msg ?? 'Building your lesson'}
        </motion.span>
      </AnimatePresence>
    </div>
  )
}

function CompactContent(): ReactNode {
  const { stepId, title } = useLesson(useShallow((x) => ({ stepId: x.stepId, title: x.stepTitle })))
  const { index, fraction } = useProgress()
  const status = useStatus()
  return (
    <div className="flex h-[34px] items-center gap-[9px] whitespace-nowrap pl-[14px] pr-[12px] text-[13px] font-medium">
      <Sparkles size={14} strokeWidth={1.75} className="shrink-0" />
      <AnimatePresence mode="popLayout" initial={false}>
        <motion.span
          key={stepId}
          initial={{ opacity: 0, y: 5 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -5 }}
          transition={{ duration: 0.22 }}
        >
          <span className="text-white/70">Step {index + 1}</span>
          <span className="text-white/40"> · </span>
          <span>{title}</span>
        </motion.span>
      </AnimatePresence>
      <span className="ml-[3px] flex items-center gap-[7px]">
        <ProgressRing fraction={fraction} />
        <StatusDot status={status} />
      </span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Cards (fixed width, height hugs the content)
// ---------------------------------------------------------------------------

function Segments({ total, index, status }: { total: number; index: number; status: Status }): ReactNode {
  const current = status === 'offtrack' ? color.amber : status === 'passed' ? color.green : color.accent
  return (
    <div className="mt-[10px] flex gap-[5px]">
      {Array.from({ length: total }, (_, i) => (
        <motion.div
          key={i}
          className="h-[3px] flex-1 rounded-full"
          initial={false}
          animate={{ background: i < index ? 'rgba(255,255,255,.88)' : i === index ? current : 'rgba(255,255,255,.18)' }}
          transition={{ duration: 0.3 }}
        />
      ))}
    </div>
  )
}

function OverviewContent(): ReactNode {
  const s = useLesson(useShallow((x) => ({ title: x.stepTitle, checks: x.checks, video: x.stepVideo, playing: x.video.playing })))
  const { index, total } = useProgress()
  const status = useStatus()
  const start = s.video ? clock(s.video.start) : undefined
  const end = s.video ? clock(s.video.end) : undefined
  const footer =
    status === 'passed' ? 'Passed · the video picks up from here' : end ? `Video continues past ${end} when all pass` : 'Each step is auto-checked'
  return (
    <div className="px-[22px] pb-[16px] pt-[20px]">
      <div className="flex gap-[16px]">
        <Thumb w={120} h={68} time={start} />
        <div className="min-w-0 flex-1 pt-[2px]">
          <div className="flex items-center gap-[7px] text-[13px] text-white/55">
            Step {index + 1} of {total} <StatusDot status={status} />
          </div>
          <div className="mt-[2px] truncate text-[20px] font-semibold tracking-[-0.015em]">{s.title}</div>
          <Segments total={total} index={index} status={status} />
        </div>
      </div>
      {s.checks.length > 0 && (
        <div className="mt-[18px]">
          <CheckList checks={s.checks} />
        </div>
      )}
      <div className="mt-[16px] flex items-center justify-between border-t pt-[12px] text-[13px] text-white/45" style={{ borderColor: 'rgba(255,255,255,.08)' }}>
        <span>{footer}</span>
        <span>Ask {bridge.platform.keys.launcher}</span>
      </div>
    </div>
  )
}

function Chip({ tone, children }: { tone: string; children: ReactNode }): ReactNode {
  return (
    <span
      className="inline-flex h-[20px] items-center gap-[5px] rounded-[6px] px-[7px] text-[11px] font-semibold uppercase tracking-[0.04em]"
      style={{ color: tone, background: `${tone}26` }}
    >
      {children}
    </span>
  )
}

function CardButton({ children, onClick, primary, tone = color.amber }: { children: ReactNode; onClick: () => void; primary?: boolean; tone?: string }): ReactNode {
  return (
    <motion.button
      className="flex h-[36px] flex-1 cursor-pointer items-center justify-center gap-[7px] rounded-[12px] text-[14px] font-semibold"
      style={primary ? { background: tone, color: '#1a1200' } : { background: 'rgba(255,255,255,.09)', color: '#fff' }}
      whileHover={{ scale: 1.02 }}
      whileTap={{ scale: 0.94 }}
      transition={{ duration: 0.09 }}
      onClick={onClick}
    >
      {children}
    </motion.button>
  )
}

function Curve({ yours, tutorial }: { yours: number[]; tutorial: number[] }): ReactNode {
  const W = 416
  const H = 62
  const all = [...yours, ...tutorial]
  const lo = Math.min(...all)
  const hi = Math.max(...all)
  const path = (v: number[]): string =>
    v.map((y, i) => `${i ? 'L' : 'M'}${((i / (v.length - 1)) * (W - 8)).toFixed(1)},${(4 + ((hi - y) / (hi - lo || 1)) * (H - 8)).toFixed(1)}`).join(' ')
  const last = yours[yours.length - 1]
  return (
    <svg width={W} height={H} className="block overflow-visible">
      <motion.path d={path(tutorial)} fill="none" stroke="rgba(10,132,255,.75)" strokeWidth="1.5" initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 0.6 }} />
      <motion.path d={path(yours)} fill="none" stroke={color.amber} strokeWidth="2" initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 0.6, delay: 0.1 }} />
      <circle cx={W - 8} cy={4 + ((hi - last) / (hi - lo || 1)) * (H - 8)} r="3.5" fill={color.amber} />
    </svg>
  )
}

function OfftrackContent(): ReactNode {
  const s = useLesson(useShallow((x) => ({ o: x.offtrack, checks: x.checks, playing: x.video.playing })))
  const { index } = useProgress()
  if (!s.o) return null
  const o = s.o
  const act = (kind: 'show_me' | 'explain' | 'apply_fix'): void => {
    bridge.send(cmd('action', { kind }))
    if (kind === 'apply_fix') useLesson.setState({ offtrackOpen: false })
  }
  return (
    <div className="px-[20px] pb-[16px] pt-[18px]">
      <div className="flex items-center gap-[8px]">
        <Chip tone={color.amber}>Off-track</Chip>
        {o.reason && <span className="truncate text-[13px] text-white/55">{o.reason}</span>}
        <span className="flex-1" />
        {!s.playing && (
          <span className="flex items-center gap-[5px] text-[12px] text-white/55">
            <span className="h-[6px] w-[6px] rounded-full" style={{ background: color.amber }} /> Video paused
          </span>
        )}
        <CloseButton />
      </div>

      <div className="mt-[12px] text-[12px] font-semibold uppercase tracking-[0.06em]" style={{ color: color.amber }}>
        Step {index + 1} · Something's off
      </div>
      <div className="mt-[3px] text-[20px] font-semibold tracking-[-0.015em]">{o.title}</div>
      <div className="mt-[5px] text-[14px] leading-[20px] text-white/72">{o.body}</div>

      {o.curve && (
        <div className="mt-[14px]">
          <div className="mb-[6px] flex items-center gap-[12px] text-[11px] font-medium uppercase tracking-[0.06em] text-white/42">
            {o.curve.label} · yours vs tutorial
            <span className="flex-1" />
            <span className="flex items-center gap-[5px] normal-case tracking-normal">
              <i className="inline-block h-[2px] w-[10px]" style={{ background: color.amber }} /> yours
            </span>
            <span className="flex items-center gap-[5px] normal-case tracking-normal">
              <i className="inline-block h-[2px] w-[10px]" style={{ background: color.accent }} /> tutorial
            </span>
          </div>
          <Curve yours={o.curve.yours} tutorial={o.curve.tutorial} />
        </div>
      )}

      {o.diff && (
        <div className="mt-[14px] overflow-hidden rounded-[12px] font-mono text-[12.5px]" style={{ background: 'rgba(255,255,255,.05)' }}>
          <div className="flex items-center gap-[12px] px-[12px] py-[8px]">
            <span className="w-[62px] shrink-0 text-[10.5px] font-semibold tracking-[0.06em]" style={{ color: color.green }}>
              EXPECTED
            </span>
            <span className="truncate text-white/90">{o.diff.expected}</span>
          </div>
          <div className="flex items-center gap-[12px] border-t px-[12px] py-[8px]" style={{ borderColor: 'rgba(255,255,255,.06)' }}>
            <span className="w-[62px] shrink-0 text-[10.5px] font-semibold tracking-[0.06em]" style={{ color: color.amber }}>
              YOURS{o.diff.line ? ` · L${o.diff.line}` : ''}
            </span>
            <span className="truncate text-white/90">{o.diff.yours}</span>
          </div>
        </div>
      )}

      {s.checks.length > 0 && (
        <div className="mt-[14px]">
          <CheckList checks={s.checks} />
        </div>
      )}

      <div className="mt-[16px] flex gap-[8px]">
        {o.actions.includes('show_me') && (
          <CardButton onClick={() => act('show_me')}>
            <Play size={13} fill="currentColor" /> Show me
          </CardButton>
        )}
        {o.actions.includes('explain') && (
          <CardButton onClick={() => act('explain')}>
            <Lightbulb size={14} /> Explain
          </CardButton>
        )}
        {o.actions.includes('apply_fix') && (
          <CardButton primary onClick={() => act('apply_fix')}>
            <Wand2 size={14} /> Apply fix
          </CardButton>
        )}
      </div>
      {o.citation && <div className="mt-[10px] truncate text-[12px] text-white/40">Source: {o.citation.label}</div>}
    </div>
  )
}

function SuccessContent(): ReactNode {
  const s = useLesson((x) => x.success)
  if (!s) return null
  return (
    <div className="px-[20px] pb-[18px] pt-[18px]">
      <div className="flex items-center gap-[8px]">
        <Chip tone={color.green}>✓ Step {s.index + 1} done</Chip>
        <span className="flex-1" />
        <CloseButton />
      </div>
      <div className="mt-[10px] text-[20px] font-semibold tracking-[-0.015em]">Back on track.</div>
      {s.summary && <div className="mt-[4px] text-[14px] leading-[20px] text-white/72">{s.summary}</div>}
      {s.checks.length > 0 && (
        <div className="mt-[14px]">
          <CheckList checks={s.checks} />
        </div>
      )}
      <div className="mt-[14px] text-[13px] text-white/45">The video picks up from here.</div>
    </div>
  )
}

function CardContent(): ReactNode {
  const c = useLesson((x) => x.card)
  if (!c) return null
  const tone = c.kind === 'hint' ? color.amber : color.accent
  const Icon = c.kind === 'hint' ? Lightbulb : MessageSquareText
  return (
    <div className="px-[20px] pb-[16px] pt-[16px]">
      <div className="flex items-center gap-[8px]">
        <Icon size={15} style={{ color: tone }} />
        <span className="text-[12px] font-semibold uppercase tracking-[0.06em]" style={{ color: tone }}>
          {c.kind === 'explain' ? 'Explain' : c.kind === 'hint' ? 'Hint' : 'Answer'}
        </span>
        <span className="flex-1" />
        <CloseButton />
      </div>
      <div className="mt-[8px] text-[18px] font-semibold tracking-[-0.01em]">{c.title}</div>
      <div className="mt-[4px] text-[14px] leading-[20px] text-white/75">{c.body}</div>
      {c.videoJump && (
        <motion.button
          className="mt-[12px] flex h-[32px] cursor-pointer items-center gap-[7px] rounded-[10px] px-[12px] text-[13px] font-medium"
          style={{ background: 'rgba(255,255,255,.09)' }}
          whileTap={{ scale: 0.95 }}
          onClick={() => useLesson.setState({ video: { t: c.videoJump!.t, playing: true, at: Date.now() }, card: undefined })}
        >
          <Play size={12} fill="currentColor" /> {c.videoJump.label}
        </motion.button>
      )}
    </div>
  )
}

export function CloseButton(): ReactNode {
  return (
    <button
      className="grid h-[22px] w-[22px] cursor-pointer place-items-center rounded-full text-white/60 hover:text-white"
      style={{ background: 'rgba(255,255,255,.1)' }}
      onClick={() => useLesson.getState().closeCard()}
      aria-label="Close"
    >
      <X size={12} strokeWidth={2.2} />
    </button>
  )
}

/**
 * Feature: errors. The startup status as one calm row (startup.ts says what; this draws it). Used by the home rail
 * (features/library Status.tsx, in the shell's sidebar).
 *
 *   starting / reconnecting   a dashed gray ring, "miyagi is getting ready", and a soft line along the row's foot: a
 *                             short neutral segment gliding across a hairline track (not a spinner). Reduced motion:
 *                             the segment fills the track and breathes instead (never frozen: a frozen bar reads as a hang).
 *   ready                     the line runs to the end and fades, the green circle springs up and its tick draws in,
 *                             "Ready" rises into place. Only after a wait the learner saw: a window that opens on an engine
 *                             that is already up shows Ready as settled (no pop).
 *   limited                   the white ring and a plain line ("Free use is used up").
 *   failed                    the white ring, "miyagi couldn't start", the reason under it, Retry and Copy details. The
 *                             block rises in under the line; the rows below glide down (layout, a transform).
 *
 * Transform and opacity only, on the house spring; text swaps crossfade in one grid cell (old up and out, new up and in)
 * so the row never changes height while the words change. No hue but the one green for Ready.
 */
import { AnimatePresence, motion, useAnimate, useReducedMotion } from 'motion/react'
import { RotateCw } from 'lucide-react'
import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import { color, duration, fill, focus, highlight, radius2, spring, stagger, surface, type2 } from '../../core/theme'
import { ease, pressMotion, riseIn } from '../../core/ui/motion'
import { StatusGlyph, type StatusState } from '../../core/ui/status'
import { Skeleton } from '../../core/ui/Thinking'
import { copyBootDetails, retryBoot, useBoot, useBootClock, type BootPhase } from './startup'

/** Row geometry: glyph column 14 + gap 8 inside 8 px padding, so text starts at 30. */
const ROW_H = 36
const TEXT_X = 30

const waiting = (p: BootPhase): boolean => p === 'starting' || p === 'reconnecting'

function glyphOf(p: BootPhase): StatusState {
  if (p === 'ready') return 'passed'
  if (p === 'failed' || p === 'limited') return 'notyet'
  if (p === 'checking') return 'unknown'
  return 'watching'
}

/**
 * The soft progress line. `done`: the segment runs out to the full track (the spring), then the parent fades it.
 * Positioned along the row's foot (absolute), so it never moves anything around it.
 */
export function BootLine({ done = false, inset = TEXT_X, right = 10, bottom = 5 }: { done?: boolean; inset?: number; right?: number; bottom?: number }): ReactNode {
  const reduce = useReducedMotion()
  // Driven imperatively: a looping keyframe set as `animate` would be skipped (left on its last frame) under a parent
  // AnimatePresence with initial={false}, as the island's modes are.
  const [seg, animate] = useAnimate<HTMLSpanElement>()
  useEffect(() => {
    if (!seg.current) return
    if (done) {
      const c = animate(seg.current, { x: '0%', scaleX: 1, opacity: 1 }, { ...spring, opacity: { duration: duration.fast } })
      return () => c.stop()
    }
    const c = reduce
      ? animate(seg.current, { opacity: [0.22, 0.6, 0.22] }, { duration: 2.4, repeat: Infinity, ease: ease.inOut })
      : animate(seg.current, { x: ['-34%', '100%'] }, { duration: 1.7, repeat: Infinity, repeatDelay: 0.3, ease: ease.inOut })
    return () => c.stop()
  }, [done, reduce, animate, seg])
  return (
    <motion.span
      aria-hidden
      data-boot-line={done ? 'done' : 'run'}
      className="pointer-events-none absolute block overflow-hidden"
      style={{ left: inset, right, bottom, height: 2, borderRadius: radius2.round, background: fill.hairline }}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1, transition: { duration: duration.slow, ease: ease.out } }}
      exit={{ opacity: 0, transition: { duration: duration.slow, delay: 0.14 } }}
    >
      {/* Reduced motion: the segment fills the track and breathes (opacity only), never frozen. */}
      <motion.span
        ref={seg}
        className="absolute inset-0 block origin-left"
        style={{ background: color.label, borderRadius: radius2.round, x: reduce ? '0%' : '-34%', scaleX: reduce ? 1 : 0.34, opacity: reduce ? 0.3 : 1 }}
      />
    </motion.span>
  )
}

/**
 * The line's life around a wait: running while `waiting`; when the wait ends well (`settled`) it runs out to the end
 * (LINE_OUT_MS), then goes; any other end just fades it.
 */
export function useLinePhase(waiting: boolean, settled: boolean): 'run' | 'done' | 'off' {
  const [line, setLine] = useState<'run' | 'done' | 'off'>(waiting ? 'run' : 'off')
  useEffect(() => {
    if (waiting) return setLine('run')
    if (settled) {
      setLine((l) => (l === 'run' ? 'done' : l))
      const t = setTimeout(() => setLine('off'), LINE_OUT_MS)
      return () => clearTimeout(t)
    }
    setLine('off')
  }, [waiting, settled])
  return line
}
const LINE_OUT_MS = 420

/** A small neutral chip button (sidebar chrome: never a hue, never the surface's primary). */
function Chip({ label, icon: I, onClick, strong }: { label: string; icon?: typeof RotateCw; onClick: () => void; strong?: boolean }): ReactNode {
  return (
    <motion.button
      type="button"
      className="mg-press relative flex shrink-0 cursor-pointer items-center whitespace-nowrap outline-offset-2 focus-visible:outline-2 focus-visible:outline-solid"
      style={{
        height: 26,
        gap: 5,
        padding: strong ? '0 10px 0 8px' : '0 8px',
        borderRadius: radius2.control,
        fontSize: type2.xs,
        fontWeight: 500,
        color: strong ? color.text : color.label,
        background: strong ? surface.row : fill.clear,
        boxShadow: strong ? `inset 0 0 0 1px ${surface.border}, ${highlight.top}` : undefined,
        outlineColor: focus.dark
      }}
      {...pressMotion()}
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
    >
      {I && <I aria-hidden size={12} strokeWidth={2} className="relative shrink-0" />}
      <span className="relative">{label}</span>
    </motion.button>
  )
}

/** One line of text that crossfades with a slight rise when its words change (no height change). */
function SwapLine({ id, children, style }: { id: string; children: ReactNode; style?: CSSProperties }): ReactNode {
  return (
    <span className="relative grid min-w-0 flex-1 overflow-hidden" style={{ height: ROW_H, alignItems: 'center' }}>
      <AnimatePresence initial={false}>
        <motion.span
          key={id}
          className="block min-w-0 truncate"
          style={{ gridArea: '1 / 1', ...style }}
          initial={{ opacity: 0, y: stagger.rise }}
          animate={{ opacity: 1, y: 0, transition: { ...spring, opacity: { duration: duration.base, delay: 0.06 } } }}
          exit={{ opacity: 0, y: -stagger.rise / 2, transition: { duration: duration.fast } }}
        >
          {children}
        </motion.span>
      </AnimatePresence>
    </span>
  )
}

/** The status row (layout: the failed block below it grows the row; the parent animates `layout`). */
export function BootRow(): ReactNode {
  const boot = useBoot()
  const copied = useBootClock((s) => s.copied)
  const phase = boot.phase

  // Ready pops (and the line runs out) only after a wait the learner saw.
  const sawWait = useRef(false)
  const still = !sawWait.current
  useEffect(() => {
    if (waiting(phase) || phase === 'failed') sawWait.current = true
  }, [phase])

  // The line: running while waiting; on Ready it runs out to the end, then goes. Failed: it just fades.
  const line = useLinePhase(waiting(phase), phase === 'ready' || phase === 'limited')

  const glyph = glyphOf(phase)
  const label = phase === 'checking' ? 'Checking' : boot.line
  return (
    <div data-boot={phase} className="relative" title={phase === 'failed' ? undefined : boot.detail}>
      <div className="relative flex items-center" style={{ height: ROW_H, padding: '0 8px', gap: 8 }}>
        <span className="relative grid shrink-0" style={{ width: 14, height: 14 }}>
          <AnimatePresence initial={false}>
            <motion.span
              key={glyph}
              className="grid"
              style={{ gridArea: '1 / 1' }}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1, transition: { duration: duration.base } }}
              exit={{ opacity: 0, transition: { duration: duration.fast } }}
            >
              <StatusGlyph state={glyph} size={14} still={glyph !== 'passed' || still} />
            </motion.span>
          </AnimatePresence>
        </span>
        {phase === 'checking' ? (
          <span className="flex min-w-0 flex-1 items-center" style={{ height: ROW_H }}>
            <Skeleton width={104} height={10} radius={radius2.round} />
          </span>
        ) : (
          <SwapLine id={`${phase}:${label}`} style={{ fontSize: type2.sm, color: phase === 'starting' || phase === 'reconnecting' ? color.label : color.text }}>
            <span role="status" aria-live="polite">
              {label}
            </span>
          </SwapLine>
        )}
        <AnimatePresence>{line !== 'off' && <BootLine key="line" done={line === 'done'} />}</AnimatePresence>
      </div>
      <AnimatePresence initial={false}>
        {phase === 'failed' && (
          <motion.div key="failed" data-boot-failed className="flex flex-col" style={{ padding: `0 8px 10px ${TEXT_X}px`, gap: 8 }} {...riseIn}>
            {boot.detail && (
              <span style={{ fontSize: type2.xs, lineHeight: '16px', color: color.label }}>{boot.detail}</span>
            )}
            <span className="flex items-center" style={{ gap: 2 }}>
              <Chip label="Retry" icon={RotateCw} onClick={retryBoot} strong />
              <Chip label={copied === 'yes' ? 'Copied' : copied === 'no' ? "Couldn't copy" : 'Copy details'} onClick={() => void copyBootDetails()} />
            </span>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

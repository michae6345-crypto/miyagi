/**
 * Feature: sound. The browser stage's monitor (only with ?sound=…, never in Electron): the proposed Sounds setting,
 * test cues, and a readout of the last cue so a reviewer can SEE what played without hearing it. The bars are the
 * cue's real loudness outline (synth.outline over the very samples the player uses), swept in left to right.
 */
import { AnimatePresence, motion, type MotionProps } from 'motion/react'
import { useMemo, type ReactNode } from 'react'
import { Segmented, Toggle } from '../../core/ui/controls'
import { PrimaryButton, QuietButton } from '../../core/ui/buttons'
import { riseItem, staggerList } from '../../core/ui/motion'
import { color, duration, elevation, highlight, radius2, spring, stagger, surface, type2 } from '../../core/theme'
import { setSoundMode, setSoundTaps, useSound, type SoundMode } from './settings'
import { request, useSoundLog, type SoundEvent } from './store'
import { CUES, outline, renderCue, type Cue } from './synth'
import type { Verdict } from './gate'

const BARS = 20
const SWEEP_S = 0.36
const NAME: Record<Cue, string> = { tick: 'Tick', done: 'Done', tap: 'Tap' }
const MODES = [
  { value: 'off', label: 'Off' },
  { value: 'subtle', label: 'Subtle' }
] as const

function said(v: Verdict, dry: boolean): string {
  if (v.play) return dry ? 'played, muted' : 'played'
  switch (v.reason) {
    case 'held':
      return `waits ${v.retryInMs} ms`
    case 'off':
      return 'sounds are off'
    case 'taps-off':
      return 'taps are off'
    case 'dnd':
      return 'Do Not Disturb'
    case 'typing':
      return 'typing'
    case 'gap':
      return 'too soon'
    case 'stale':
      return 'dropped'
    case 'outranked':
      return 'a bigger cue waits'
  }
}

function Wave({ ev }: { ev: SoundEvent }): ReactNode {
  const bars = useMemo(() => outline(renderCue(ev.cue, 48000), BARS), [ev.cue])
  const lit = ev.verdict.play
  return (
    <div className="flex h-[22px] shrink-0 items-center gap-[2px]" aria-hidden>
      {bars.map((v, i) => (
        <motion.span
          key={i}
          className="block h-[22px] w-[3px] rounded-full"
          style={{ background: lit ? color.text : color.faint, originY: 0.5 }}
          initial={{ scaleY: 0.08, opacity: 0.25 }}
          animate={{ scaleY: Math.max(0.08, v), opacity: lit ? 1 : 0.5 }}
          transition={{ ...spring, delay: (i / BARS) * SWEEP_S, opacity: { duration: duration.base, delay: (i / BARS) * SWEEP_S } }}
        />
      ))}
    </div>
  )
}

/**
 * The readout swap, as the pill morph does it (UI-POLISH-SPEC 8): the old line leaves fast (80 ms, lifting 3 px) and
 * the new one rises on the house spring with its fade 60 ms late, so the two never read on top of each other.
 */
const swap: MotionProps = {
  initial: { opacity: 0, y: stagger.rise },
  animate: { opacity: 1, y: 0, transition: { ...spring, opacity: { duration: duration.base, delay: 0.06 } } },
  exit: { opacity: 0, y: -stagger.rise / 2, transition: { duration: duration.instant } }
}

function Readout({ ev, dry }: { ev?: SoundEvent; dry: boolean }): ReactNode {
  return (
    <div data-sound-readout className="relative h-[58px] overflow-hidden" style={{ background: surface.well, borderRadius: radius2.row, boxShadow: highlight.well }}>
      <AnimatePresence initial={false} mode="popLayout">
        {ev ? (
          <motion.div key={ev.id} className="absolute inset-0 flex items-center justify-between gap-[12px] px-[12px]" {...swap}>
            <div className="min-w-0 flex-1">
              <div className="flex items-baseline gap-[6px] whitespace-nowrap" style={{ fontSize: type2.sm, color: color.text }}>
                <span className="font-medium">{NAME[ev.cue]}</span>
                <span style={{ color: color.label }}>{said(ev.verdict, dry)}</span>
              </div>
              <div className="mt-[2px] truncate" style={{ fontSize: type2.micro, color: color.label }}>
                {ev.why} · {CUES[ev.cue].peakDbfs} dB · {CUES[ev.cue].durationMs} ms
              </div>
            </div>
            <Wave ev={ev} />
          </motion.div>
        ) : (
          <motion.div key="none" className="absolute inset-0 flex items-center px-[12px]" style={{ fontSize: type2.sm, color: color.label }} {...swap}>
            No cue yet
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

export function SoundMonitor(): ReactNode {
  const { mode, taps, dry } = useSound()
  const last = useSoundLog((s) => s.last)
  return (
    <motion.div
      data-hit
      className="pointer-events-auto fixed bottom-[64px] left-[24px] w-[360px] p-[14px]"
      style={{ background: surface.sheet, borderRadius: radius2.group, boxShadow: `${highlight.top}, 0 0 0 1px ${surface.border}, ${elevation.overlay}` }}
      variants={staggerList}
      initial="hidden"
      animate="shown"
    >
      <motion.div variants={riseItem} className="flex items-center justify-between">
        <span className="font-medium" style={{ fontSize: type2.md, color: color.text }}>
          Sounds
        </span>
        <Segmented<SoundMode> options={MODES} value={mode} onChange={setSoundMode} label="Sounds" />
      </motion.div>
      <motion.div variants={riseItem} className="mt-[10px] flex items-center justify-between" style={{ opacity: mode === 'off' ? 0.4 : 1 }}>
        <span style={{ fontSize: type2.sm, color: color.label }}>Tap on a primary press</span>
        <Toggle on={taps} onChange={setSoundTaps} label="Tap on a primary press" disabled={mode === 'off'} />
      </motion.div>
      <motion.div variants={riseItem} className="mt-[12px]">
        <Readout ev={last} dry={dry} />
      </motion.div>
      <motion.div variants={riseItem} className="mt-[12px] flex gap-[8px]">
        <QuietButton label="Tick" onClick={() => request('tick', 'stage test', { system: true })} />
        <QuietButton label="Done" onClick={() => request('done', 'stage test', { system: true })} />
        <div className="flex-1" />
        <PrimaryButton label="Primary" onClick={() => undefined} />
      </motion.div>
    </motion.div>
  )
}

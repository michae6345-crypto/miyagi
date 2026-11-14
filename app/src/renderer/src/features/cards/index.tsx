/**
 * Feature: cards. Coach cards that grow out of the pill:
 *   offtrack  amber: diagnosis, yours-vs-tutorial curve, expected vs yours, checks, Show me / Explain / Apply fix
 *   success   green "Back on track" after a recovered step (auto-hides)
 *   card      explain / hint / answer from the engine, with an optional video jump
 */
import { motion } from 'motion/react'
import type { ReactNode } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { Lightbulb, MessageSquareText, Play, Wand2 } from 'lucide-react'
import { bridge } from '../../bridge'
import { cmd } from '../../../../common/wire'
import { useLesson, useProgress } from '../../core/lesson'
import { defineFeature } from '../../core/registry'
import { CardButton, CheckList, Chip, CloseButton } from '../../core/ui/atoms'
import { color } from '../../core/theme'
import { useCards } from './store'

function Curve({ yours, tutorial }: { yours: number[]; tutorial: number[] }): ReactNode {
  const W = 416
  const H = 62
  const all = [...yours, ...tutorial]
  const lo = Math.min(...all)
  const hi = Math.max(...all)
  const y = (v: number): number => 4 + ((hi - v) / (hi - lo || 1)) * (H - 8)
  const path = (v: number[]): string => v.map((p, i) => `${i ? 'L' : 'M'}${((i / (v.length - 1)) * (W - 8)).toFixed(1)},${y(p).toFixed(1)}`).join(' ')
  return (
    <svg width={W} height={H} className="block overflow-visible">
      <motion.path d={path(tutorial)} fill="none" stroke="rgba(10,132,255,.75)" strokeWidth="1.5" initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 0.6 }} />
      <motion.path d={path(yours)} fill="none" stroke={color.amber} strokeWidth="2" initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 0.6, delay: 0.1 }} />
      <circle cx={W - 8} cy={y(yours[yours.length - 1])} r="3.5" fill={color.amber} />
    </svg>
  )
}

function Offtrack(): ReactNode {
  const s = useLesson(useShallow((x) => ({ o: x.offtrack, checks: x.checks, playing: x.video.playing })))
  const { index } = useProgress()
  if (!s.o) return null
  const o = s.o
  const act = (kind: 'show_me' | 'explain' | 'apply_fix' | 'hint'): void => {
    bridge.send(cmd('action', { kind }))
    if (kind === 'apply_fix') useCards.setState({ offtrackOpen: false })
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

function Success(): ReactNode {
  const s = useCards((x) => x.success)
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

function Card(): ReactNode {
  const c = useCards((x) => x.card)
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
          onClick={() => {
            useLesson.setState({ video: { t: c.videoJump!.t, playing: true, at: Date.now() } })
            useCards.setState({ card: undefined })
          }}
        >
          <Play size={12} fill="currentColor" /> {c.videoJump.label}
        </motion.button>
      )}
    </div>
  )
}

export default defineFeature({
  id: 'cards',
  islandModes: [
    {
      id: 'offtrack',
      priority: 70,
      width: 460,
      useActive: (hover) => {
        const open = useCards((c) => c.offtrackOpen)
        const has = useLesson((s) => !!s.offtrack)
        return has && (open || hover)
      },
      Content: Offtrack
    },
    { id: 'success', priority: 60, width: 420, useActive: () => useCards((c) => !!c.success), Content: Success },
    { id: 'card', priority: 50, width: 420, useActive: () => useCards((c) => !!c.card), Content: Card }
  ]
})

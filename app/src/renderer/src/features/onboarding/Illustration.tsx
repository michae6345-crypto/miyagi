/**
 * Feature: onboarding. The picture beside each guided step: a small, honest picture of what the learner will see,
 * and it mirrors the live state (the switch turns on when macOS reports the grant, not before).
 *
 *   screen / accessibility  the System Settings list with miyagi in it and its switch (white when on, like core Toggle)
 *   companion               VS Code's extension row for the miyagi companion
 *   engine                  the two things being readied: the engine on this Mac and cloud access
 *
 * Neutral chrome only (no hue except the passed glyph). Transform and opacity only: the knob slides on `x`.
 */
import type { ReactNode } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { ChevronLeft, ChevronRight, Code } from 'lucide-react'
import { useShallow } from 'zustand/react/shallow'
import { useLesson } from '../../core/lesson'
import { color, fill, radius2, spring, surface, type2 } from '../../core/theme'
import { MiyagiMark } from '../../core/ui/Mark'
import { StatusGlyph, type StatusState } from '../../core/ui/status'
import { osNow, shellName, thisDevice } from './device'
import type { Row } from './rows'
import { useOnboarding } from './store'
import { fade } from '../../core/ui/motion'

/** A raised card: lighter step, a brighter top edge, a hairline, a soft two-layer lift (UI-POLISH-SPEC 2). */
export const raisedCard = {
  background: surface.sheet,
  borderRadius: radius2.group,
  boxShadow: `inset 0 1px 0 ${fill.highlight}, inset 0 0 0 1px ${fill.hairline}, ${surface.shadowSmall}`
} as const

function Switch({ on }: { on: boolean }): ReactNode {
  return (
    <span aria-hidden className="relative block shrink-0 overflow-hidden" style={{ width: 34, height: 20, borderRadius: radius2.round, background: fill.toggleOff }}>
      {/* The on track fades over the off one (opacity), the knob slides (x). */}
      <motion.span className="absolute inset-0 block" style={{ background: color.accent }} initial={false} animate={{ opacity: on ? 1 : 0 }} transition={fade.in} />
      <motion.span
        className="absolute left-[2px] top-[2px] block"
        style={{ width: 16, height: 16, borderRadius: radius2.round, background: on ? color.onAccent : color.text }}
        initial={false}
        animate={{ x: on ? 14 : 0 }}
        transition={spring}
      />
    </span>
  )
}

/** A faint placeholder line (another app in the list): shape only, no fake names. */
function Ghost({ w }: { w: number }): ReactNode {
  return (
    <div className="flex h-[40px] items-center gap-[10px] px-[12px]" style={{ opacity: 0.55 }}>
      <span className="block h-[20px] w-[20px] shrink-0" style={{ borderRadius: radius2.keycap, background: fill.tile }} />
      <span className="block h-[8px]" style={{ width: w, borderRadius: radius2.round, background: fill.skeleton }} />
      <span className="flex-1" />
      <Switch on={false} />
    </div>
  )
}

function SettingsPane({ row, pane }: { row: Row; pane: string }): ReactNode {
  const on = row.state === 'passed'
  const focus = row.state === 'notyet' || row.state === 'watching'
  return (
    <div className="flex flex-col p-[16px]" style={raisedCard}>
      <div className="flex items-center gap-[8px]" style={{ color: color.faint }}>
        <ChevronLeft size={14} strokeWidth={1.8} />
        <ChevronRight size={14} strokeWidth={1.8} />
        <span style={{ fontSize: type2.xs }}>Privacy & Security</span>
      </div>
      <span className="mt-[12px]" style={{ fontSize: type2.lg, fontWeight: 600, color: color.text }}>
        {pane}
      </span>
      <div className="mt-[12px] flex flex-col overflow-hidden" style={{ borderRadius: radius2.card, background: fill.group, boxShadow: `inset 0 0 0 1px ${fill.hairline}` }}>
        <motion.div
          data-onb-switch={on ? 'on' : 'off'}
          className="relative flex h-[44px] items-center gap-[10px] px-[12px]"
          style={{ borderBottom: `1px solid ${fill.hairline}` }}
        >
          {/* The row to switch on: outlined while it is the learner's move (no glow, no hue). */}
          <motion.span
            aria-hidden
            className="pointer-events-none absolute inset-[3px] block"
            style={{ borderRadius: radius2.row, boxShadow: `inset 0 0 0 1px ${color.label}` }}
            initial={false}
            animate={{ opacity: focus ? 1 : 0 }}
            transition={fade.in}
          />
          <MiyagiMark size={22} />
          <span style={{ fontSize: type2.sm, fontWeight: 500, color: color.text }}>miyagi</span>
          <span className="flex-1" />
          <Switch on={on} />
        </motion.div>
        <Ghost w={84} />
        <Ghost w={60} />
      </div>
      <span className="mt-[12px]" style={{ fontSize: type2.xs, lineHeight: '16px', color: color.faint }}>
        {on ? 'miyagi is on. You can close System Settings.' : 'Switch miyagi on here.'}
      </span>
    </div>
  )
}

function CompanionCard({ row }: { row: Row }): ReactNode {
  const word = row.state === 'passed' ? 'Installed' : row.state === 'checking' ? row.word : row.action?.id === 'get-vscode' ? 'Needs VS Code' : 'Not installed'
  return (
    <div className="flex flex-col p-[16px]" style={raisedCard}>
      <span style={{ fontSize: type2.xs, color: color.faint }}>VS Code · Extensions</span>
      <div className="mt-[12px] flex items-center gap-[12px] p-[12px]" style={{ borderRadius: radius2.card, background: fill.group, boxShadow: `inset 0 0 0 1px ${fill.hairline}` }}>
        <div className="grid h-[44px] w-[44px] shrink-0 place-items-center" style={{ borderRadius: radius2.row, background: surface.row }}>
          <MiyagiMark size={28} />
        </div>
        <div className="flex min-w-0 flex-1 flex-col gap-[2px]">
          <span style={{ fontSize: type2.sm, fontWeight: 600, color: color.text }}>miyagi companion</span>
          <span className="truncate" style={{ fontSize: type2.xs, color: color.label }}>
            Runs your cells, checks your work
          </span>
        </div>
      </div>
      <div className="mt-[12px] flex items-center gap-[8px]">
        <StatusGlyph state={row.state} size={16} />
        <span style={{ fontSize: type2.xs, color: row.state === 'passed' ? color.greenText : color.label }}>{word}</span>
        <span className="flex-1" />
        <Code size={14} strokeWidth={1.6} color={color.faint} />
      </div>
    </div>
  )
}

type Part = { id: string; label: string; state: StatusState; word: string }

/** The engine row, split back into what the learner is waiting on. */
function useEngineParts(row: Row): Part[] {
  const l = useLesson(useShallow((s) => ({ connected: s.connected, local: s.localEngine?.state })))
  const cloud = useOnboarding((s) => s.cloud)
  // "this Mac" / "this computer" (device.ts). Windows ships no engine yet: a missing one there is gray, not a failure.
  const here = thisDevice()
  const win = osNow() === 'win'
  const label = `Engine on ${here}`
  const engine: Part = l.connected
    ? { id: 'engine', label, state: 'passed', word: l.local === 'external' ? `In ${shellName()}` : 'Running' }
    : l.local === 'failed' || l.local === 'missing'
      ? { id: 'engine', label, state: win ? 'unknown' : 'notyet', word: win ? 'Not running' : 'Not yet' }
      : { id: 'engine', label, state: 'watching', word: l.local === 'external' ? 'Waiting' : 'Starting' }
  const parts = [engine]
  if (cloud?.configured || (cloud && cloud.state !== 'off')) {
    const c = cloud.state
    const state: StatusState = !l.connected ? 'next' : c === 'minting' ? 'checking' : c === 'failed' ? 'notyet' : row.state === 'passed' ? 'passed' : row.state === 'notyet' ? 'notyet' : 'checking'
    const word = state === 'passed' ? 'Ready' : state === 'checking' ? 'Setting up' : state === 'next' ? 'Next' : 'Not yet'
    parts.push({ id: 'cloud', label: `Access for ${here}`, state, word })
  }
  return parts
}

function EngineCard({ row }: { row: Row }): ReactNode {
  const parts = useEngineParts(row)
  return (
    <div className="flex flex-col p-[16px]" style={raisedCard}>
      <span style={{ fontSize: type2.xs, color: color.faint }}>Getting ready</span>
      <div role="list" className="mt-[12px] flex flex-col overflow-hidden" style={{ borderRadius: radius2.card, background: fill.group, boxShadow: `inset 0 0 0 1px ${fill.hairline}` }}>
        {parts.map((p, i) => (
          <div
            key={p.id}
            role="listitem"
            data-onb-part={p.id}
            data-state={p.state}
            className="flex h-[48px] items-center gap-[10px] px-[12px]"
            style={{ borderTop: i ? `1px solid ${fill.hairline}` : undefined }}
          >
            <StatusGlyph state={p.state} size={18} />
            <span className="flex-1" style={{ fontSize: type2.sm, color: color.text }}>
              {p.label}
            </span>
            <AnimatePresence mode="wait" initial={false}>
              <motion.span
                key={p.word}
                style={{ fontSize: type2.xs, color: p.state === 'passed' ? color.greenText : color.label }}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0, transition: fade.instant }}
                transition={fade.in}
              >
                {p.word}
              </motion.span>
            </AnimatePresence>
          </div>
        ))}
      </div>
      <span className="mt-[12px]" style={{ fontSize: type2.xs, lineHeight: '16px', color: color.faint }}>
        {row.state === 'passed' ? 'All set. Moving on.' : row.state === 'notyet' ? row.detail : 'Nothing to do here. This moves on by itself.'}
      </span>
    </div>
  )
}

export function Illustration({ row }: { row: Row }): ReactNode {
  if (row.id === 'screen') return <SettingsPane row={row} pane="Screen Recording" />
  if (row.id === 'accessibility') return <SettingsPane row={row} pane="Accessibility" />
  if (row.id === 'companion') return <CompanionCard row={row} />
  return <EngineCard row={row} />
}

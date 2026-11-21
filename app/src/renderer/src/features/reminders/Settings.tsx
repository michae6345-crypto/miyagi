/**
 * Feature: reminders. The Settings entry: one group the settings lane mounts in General (agents/reminders.md, Core
 * requests): `<RemindersGroup />`. Built from the settings feature's own rows, so it reads as part of that page.
 *
 *   Reminders     on / off; the caption says exactly what will happen ("Next: today at 6:00 PM, if something is due")
 *   Time          a stepper in 30-minute steps, local time
 *   Quiet hours   on / off, with its start and end; a time inside them says plainly that no reminder will come
 *   Pause         Not today / For a week, or Resume while paused
 *
 * Neutral chrome only: an "on" switch is white, never green.
 */
import { Minus, Plus } from 'lucide-react'
import type { ReactNode } from 'react'
import { Toggle } from '../../core/ui/controls'
import { QuietButton } from '../../core/ui/buttons'
import { color, fill, radius2, type2 } from '../../core/theme'
import { Group, Note, PageHeader, Row, TextButton } from '../settings/ui'
import { fmtDay, fmtTime, nextLook, snoozed, stepTime, type Minute, type ReminderState } from './logic'
import { patchReminders, snooze, useReminders } from './store'

function Stepper({ label, value, onChange }: { label: string; value: Minute; onChange: (m: Minute) => void }): ReactNode {
  const btn = (dir: 1 | -1): ReactNode => (
    <button
      type="button"
      aria-label={`${dir < 0 ? 'Earlier' : 'Later'} ${label.toLowerCase()}`}
      className="mg-press grid h-[28px] w-[28px] shrink-0 cursor-pointer place-items-center"
      style={{ borderRadius: radius2.keycap, color: color.text }}
      onMouseDown={(e) => e.preventDefault()}
      onClick={() => onChange(stepTime(value, dir))}
    >
      {dir < 0 ? <Minus size={13} strokeWidth={1.8} aria-hidden /> : <Plus size={13} strokeWidth={1.8} aria-hidden />}
    </button>
  )
  return (
    <div
      role="group"
      aria-label={label}
      className="flex shrink-0 items-center p-[2px]"
      style={{ borderRadius: radius2.control, background: fill.segmentTrack, border: `1px solid ${fill.hairline}` }}
    >
      {btn(-1)}
      <span className="tabular-nums text-center font-medium" aria-live="polite" style={{ minWidth: 72, fontSize: type2.xs, color: color.text }}>
        {fmtTime(value)}
      </span>
      {btn(1)}
    </div>
  )
}

function caption(s: ReminderState, now: number): string {
  if (!s.enabled) return 'Off. miyagi never sends a reminder unless you turn this on.'
  if (snoozed(s, now)) return `Paused until ${fmtDay(s.snoozeUntil!, now)}.`
  if (s.restUntil && s.restUntil > now) return `Resting until ${fmtDay(s.restUntil, now)}, as set on Home.`
  const next = nextLook(s, now)
  if (next === undefined) return `No reminder will come: ${fmtTime(s.time)} is inside quiet hours.`
  const day = fmtDay(next, now)
  return `Next: ${day} at ${fmtTime(s.time)}, only if a review is due or today’s goal is open.`
}

export function RemindersGroup(): ReactNode {
  const s = useReminders((r) => r.s)
  if (!s) return null
  const now = Date.now()
  const paused = snoozed(s, now)
  return (
    <>
      <Group label="Reminders" title="Reminders" caption="At most one a day, and only when something is due.">
        <Row
          tight
          label="Review reminders"
          caption={caption(s, now)}
          right={<Toggle label="Review reminders" on={s.enabled} onChange={(v) => void patchReminders({ enabled: v, offered: true })} />}
        />
        {s.enabled && <Row label="Time" caption="Your local time." right={<Stepper label="Time" value={s.time} onChange={(time) => void patchReminders({ time })} />} />}
        {s.enabled && (
          <Row
            tight
            label="Quiet hours"
            caption={s.quiet.on ? `Nothing from ${fmtTime(s.quiet.from)} to ${fmtTime(s.quiet.to)}.` : 'Off.'}
            right={<Toggle label="Quiet hours" on={s.quiet.on} onChange={(on) => void patchReminders({ quiet: { ...s.quiet, on } })} />}
          />
        )}
        {s.enabled && s.quiet.on && (
          <Row
            label="Quiet from"
            right={
              <div className="flex items-center gap-[8px]">
                <Stepper label="Quiet start" value={s.quiet.from} onChange={(from) => void patchReminders({ quiet: { ...s.quiet, from } })} />
                <span style={{ fontSize: type2.xs, color: color.label }}>to</span>
                <Stepper label="Quiet end" value={s.quiet.to} onChange={(to) => void patchReminders({ quiet: { ...s.quiet, to } })} />
              </div>
            }
          />
        )}
        {s.enabled && (
          <Row
            label="Pause"
            caption={paused ? 'Reminders stay on and pick up after that.' : 'Take a break without turning reminders off.'}
            right={
              paused ? (
                <QuietButton label="Resume" onClick={() => void snooze('clear')} />
              ) : (
                <div className="flex items-center gap-[4px]">
                  <TextButton label="Not today" onClick={() => void snooze('day')} />
                  <TextButton label="For a week" onClick={() => void snooze('week')} />
                </div>
              )
            }
          />
        )}
      </Group>
      {s.enabled && s.preview && <Note>This build shows reminders inside miyagi, not as Mac notifications.</Note>}
    </>
  )
}

/** Browser stage only (`&reminders=settings`): the group as it sits in Settings > General, over the stage. */
export function SettingsPreview(): ReactNode {
  return (
    <div className="absolute inset-0 grid place-items-center" style={{ pointerEvents: 'none' }}>
      <div
        data-hit
        data-reminders="settings"
        className="flex flex-col gap-[16px]"
        style={{ pointerEvents: 'auto', width: 600, padding: 28, borderRadius: radius2.panel, background: color.window, boxShadow: `inset 0 0 0 1px ${fill.hairline}` }}
      >
        <PageHeader title="General" caption="Changes save as you make them." />
        <RemindersGroup />
      </div>
    </div>
  )
}

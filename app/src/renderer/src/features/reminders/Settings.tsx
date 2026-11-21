/**
 * Feature: reminders. The Settings entry: one group the settings lane mounts in General (agents/reminders.md, Core
 * requests): `<RemindersGroup />`, plus one top-level `reachableInSettings()` call (store.ts) that lets the
 * one-time offer show. Built from the settings feature's own rows, so it reads as part of that page.
 *
 *   Reminders     on / off; the caption says exactly what will happen ("Next: today at 6:00 PM, if something is due")
 *   Time          a native picker of half-hour slots, local time
 *   Quiet hours   on / off, and under it its start and end (same pickers); a time inside them says plainly that no
 *                 reminder will come
 *   Pause         Not today / For a week, or Resume while paused
 *
 * Neutral chrome only: an "on" switch is white, never green.
 */
import { ChevronDown } from 'lucide-react'
import type { ReactNode } from 'react'
import { Toggle } from '../../core/ui/controls'
import { QuietButton } from '../../core/ui/buttons'
import { color, fill, radius2, type2 } from '../../core/theme'
import { Group, Note, PageHeader, Row, TextButton } from '../settings/ui'
import { SLOTS, fmtDay, fmtTime, nextLook, snoozed, type Minute, type ReminderState } from './logic'
import { patchReminders, snooze, useReminders } from './store'

/** A native picker of half-hour slots: one click and the Mac's own menu, any time reachable at once (type to jump). */
function TimeSelect({ label, value, onChange }: { label: string; value: Minute; onChange: (m: Minute) => void }): ReactNode {
  return (
    <span className="relative inline-flex shrink-0 items-center">
      <select
        aria-label={label}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="mg-press cursor-pointer appearance-none tabular-nums font-medium outline-none"
        style={{
          height: 32,
          minWidth: 112,
          padding: '0 30px 0 12px',
          borderRadius: radius2.control,
          background: fill.segmentTrack,
          border: `1px solid ${fill.hairline}`,
          color: color.text,
          fontSize: type2.xs,
          fontFamily: 'inherit'
        }}
      >
        {SLOTS.map((m) => (
          <option key={m} value={m}>
            {fmtTime(m)}
          </option>
        ))}
      </select>
      <ChevronDown aria-hidden size={13} strokeWidth={1.8} className="pointer-events-none absolute" style={{ right: 10, color: color.label }} />
    </span>
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
        {s.enabled && <Row label="Time" caption="Your local time." right={<TimeSelect label="Reminder time" value={s.time} onChange={(time) => void patchReminders({ time })} />} />}
        {s.enabled && (
          <div>
            <Row
              tight
              label="Quiet hours"
              caption={s.quiet.on ? 'No reminder between these times.' : 'Off.'}
              right={<Toggle label="Quiet hours" on={s.quiet.on} onChange={(on) => void patchReminders({ quiet: { ...s.quiet, on } })} />}
            />
            {s.quiet.on && (
              <div role="group" aria-label="Quiet hours" className="flex items-center gap-[8px]" style={{ padding: '0 16px 14px' }}>
                <TimeSelect label="Quiet hours start" value={s.quiet.from} onChange={(from) => void patchReminders({ quiet: { ...s.quiet, from } })} />
                <span style={{ fontSize: type2.xs, color: color.label }}>to</span>
                <TimeSelect label="Quiet hours end" value={s.quiet.to} onChange={(to) => void patchReminders({ quiet: { ...s.quiet, to } })} />
              </div>
            )}
          </div>
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
      {s.enabled && s.preview && <Note>This build shows reminders inside miyagi, not as system notifications.</Note>}
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
